"""Reuso LOCAL de OCR idêntico; nunca armazena imagens nem vai ao GitHub.

Chave: bytes das imagens, instrução, texto, modelo, teto e versão do motor.
Resposta inválida/incompleta não entra. O bloqueio por chave vale entre processos.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

VALIDADE = 30 * 86400


@contextmanager
def _trava(caminho):
    with caminho.open("a+b") as arquivo:
        # O Windows permite travar além do EOF. Não escrever um byte aqui:
        # dois leitores podem ver o arquivo vazio e disputar esse primeiro write.
        inicio = time.monotonic()
        while True:
            try:
                arquivo.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() - inicio > 600:
                    raise TimeoutError("Já há uma leitura deste documento em andamento.")
                time.sleep(0.1)
        try:
            yield
        finally:
            arquivo.seek(0)
            if os.name == "nt":
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(arquivo, fcntl.LOCK_UN)


def obter(pasta, *, pedido, chamar, validar):
    """Uma resposta válida por pedido exato; hits têm zero tokens cobrados."""
    chave = hashlib.sha256(json.dumps(
        [1, pedido], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    raiz = Path(pasta) / "cache_ia_leituras" / "v1"
    raiz.mkdir(parents=True, exist_ok=True)
    destino = raiz / (chave + ".json")
    with _trava(raiz / (chave + ".lock")):
        try:
            salvo = json.loads(destino.read_text(encoding="utf-8"))
            resposta = salvo["resposta"]
            if (0 <= time.time() - salvo["quando"] < VALIDADE
                    and isinstance(resposta, dict)
                    and validar(resposta)):
                return {**resposta, "entrada": 0, "saida": 0, "cache": True}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        # Expirado ou inválido: apagar antes de substituir (sem servir resposta ruim).
        destino.unlink(missing_ok=True)
        resposta = chamar()
        if validar(resposta):
            temporario = raiz / (chave + "." + uuid.uuid4().hex + ".tmp")
            try:
                temporario.write_text(json.dumps({"quando": time.time(), "resposta": {
                    k: resposta.get(k) for k in ("texto", "modelo", "parou")}},
                    ensure_ascii=False), encoding="utf-8")
                os.replace(temporario, destino)
            except OSError:
                # A resposta já foi paga. Falha de disco não pode perdê-la e
                # induzir uma nova chamada paga por mero problema do cache.
                logging.getLogger("cartorio.ia").warning("OCR concluído; cache local não gravado.")
            finally:
                try:
                    temporario.unlink(missing_ok=True)
                except OSError:
                    pass  # A falha do cache não perde a resposta já recebida.
        return resposta

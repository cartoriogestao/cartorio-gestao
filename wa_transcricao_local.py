"""A transcrição dos áudios do WhatsApp neste servidor, com o modelo grande. NASCE DESLIGADA.

PLANO DO OFICIAL, 30/10/2026: «vamos trocar de servidor no final do ano. quando trocarmos
vamos ativar o modelo grande. tem como habilitar isso direto pelo sistema?» Hoje o áudio
inteiro sai para a OpenAI (`wa_transcricao`). Com isto ligado, ele não sai da casa.

O QUE FOI MEDIDO, 29/10/2026, na máquina de hoje (15,7 GB, 3,1 GB livres), faster-whisper
1.2.1, CPU, int8, beam 5, dois áudios de 3,7 s e 2,8 s:

    medium           43 s e 38 s     errou um
    large-v3-turbo   64 s e 60 s     acertou os dois
    large-v3         não carregou    mkl_malloc: failed to allocate memory

É POR ISSO QUE A TELA CONFERE ANTES DE LIGAR. Se a escolha ligasse sem medir, o primeiro
cliente a mandar áudio descobriria que o servidor não aguenta. `conferir` mede a memória,
transcreve um áudio de verdade e recusa dizendo o motivo; `escolher` recusa o servidor sem
conferência aprovada. A OpenAI continua a um clique, pela mesma escolha.

PROCESSO SEPARADO (`wa_transcricao_trabalhador`), E POR TRÊS MOTIVOS. Um modelo de 3 GB dentro do servidor tiraria a
memória do balcão o dia inteiro, e aqui ele só existe enquanto há áudio. Quem falha por falta
de memória morre sozinho, sem derrubar o sistema. E o que passa do prazo se mata.

O PROGRAMA E O MODELO NÃO VIAJAM NO PACOTE. `faster-whisper` entra na instalação do servidor
novo, e o modelo se baixa pela tela, uma vez só, para a pasta de dados: fora do banco, fora do
backup do banco e fora do `.cgu`. Sem eles a tela diz o que falta.

O QUE NÃO MUDA. Áudio que não se transcreve vai para uma pessoa, como já vai: quem falha
levanta a mesma `TranscricaoErro`, e o teto do dia (`ia_uso`) continua valendo.

ESTA ROTINA É SÍNCRONA, E A RODADA ESPERA. Com a IA ligada, a resposta precisa da transcrição
na mesma passada; por isso é um áudio por rodada, com prazo (`PRAZO_POR_AUDIO_S`).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable

import ia_uso as USO
import recursos_da_maquina as RM
from wa_transcricao import TETO_DE_BYTES, TranscricaoErro
from wa_transcricao_trabalhador import BAIXANDO, ERRO, PRONTO  # noqa: F401

LOG = logging.getLogger("cartorio.wa_transcricao_local")

OPENAI = "OPENAI"
AQUI = "AQUI"
ESCOLHAS = {OPENAI: "OpenAI", AQUI: "Neste servidor (modelo grande)"}

PROVEDOR = "este-servidor"
MODELO = "large-v3"
TAMANHO_DO_DOWNLOAD_GB = 3
FOLGA_DE_DISCO_GB = 2
PASTA = "modelos_transcricao"
ARQUIVO_DO_MODELO = "model.bin"
ARQUIVO_DE_ESTADO = "estado.json"

# O large-v3 não coube em 3,1 GB livres, medido. Abaixo disto, recusar sai mais barato.
MEMORIA_MINIMA_MB = 6000
PRAZO_POR_AUDIO_S = 180
PRAZO_DA_CONFERENCIA_S = 300
# Lento é passar de dois minutos E de dez vezes a duração: áudio longo pode levar mais.
LENTO_BASE_S = 120
LENTO_FATOR = 10
TEXTO_NA_TELA = 240
# Download que não terminou nesse tempo morreu com o servidor, e pode recomeçar.
PRAZO_DO_DOWNLOAD_H = 6


class TranscricaoLocalErro(ValueError):
    """Recusa da escolha ou do download. Mensagem pronta para a tela."""


def _processo(comando: list[str], prazo: int) -> Any:
    """Roda o trabalhador e espera. Isolado para os testes trocarem por um falso."""
    return subprocess.run(comando, capture_output=True, timeout=prazo, cwd=str(_raiz()),
                          creationflags=_prioridade_baixa())


def _soltar(comando: list[str]) -> None:
    """Solta o trabalhador do download, que leva minutos. Isolado para os testes."""
    subprocess.Popen(comando, cwd=str(_raiz()), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=_prioridade_baixa())


def _raiz() -> Path:
    return Path(__file__).resolve().parent


def _prioridade_baixa() -> int:
    """O balcão vem primeiro: quem transcreve fica abaixo do normal, e sem janela."""
    return (getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _comando(*argumentos: str) -> list[str]:
    return [sys.executable, "-B", str(_raiz() / "wa_transcricao_trabalhador.py"), *argumentos]


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def pasta_do_modelo(pasta_de_dados: Any) -> Path:
    return Path(pasta_de_dados) / PASTA / MODELO


def _estado_em(pasta_de_dados: Any) -> Path:
    return Path(pasta_de_dados) / PASTA / ARQUIVO_DE_ESTADO


def programa_instalado() -> bool:
    return find_spec("faster_whisper") is not None


def modelo_baixado(pasta_de_dados: Any) -> bool:
    """O arquivo existe E o trabalhador disse que terminou: download pela metade não conta."""
    return ((pasta_do_modelo(pasta_de_dados) / ARQUIVO_DO_MODELO).is_file()
            and estado_do_download(pasta_de_dados).get("situacao") == PRONTO)


def estado_do_download(pasta_de_dados: Any) -> dict:
    """Como o download está: o arquivo que o trabalhador escreve. SÓ LÊ."""
    try:
        return json.loads(_estado_em(pasta_de_dados).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _baixando_de_verdade(estado: dict) -> bool:
    """Marca de BAIXANDO velha demais é de um processo que morreu com o servidor."""
    if estado.get("situacao") != BAIXANDO:
        return False
    try:
        inicio = datetime.strptime(str(estado.get("inicio")), "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return (datetime.now() - inicio).total_seconds() < PRAZO_DO_DOWNLOAD_H * 3600


def _gravar_estado(pasta_de_dados: Any, **campos: Any) -> None:
    alvo = _estado_em(pasta_de_dados)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    temporario = alvo.with_suffix(".tmp")
    temporario.write_text(json.dumps(campos, ensure_ascii=False), encoding="utf-8")
    os.replace(temporario, alvo)


def situacao(pasta_de_dados: Any) -> dict:
    """O que a tela mostra: o que já existe neste servidor. SÓ LÊ."""
    return {"programa": programa_instalado(), "baixado": modelo_baixado(pasta_de_dados),
            "download": estado_do_download(pasta_de_dados),
            "baixando": _baixando_de_verdade(estado_do_download(pasta_de_dados)),
            "memoria_livre_mb": RM.memoria_livre_mb(), "memoria_minima_mb": MEMORIA_MINIMA_MB,
            "modelo": MODELO, "tamanho_gb": TAMANHO_DO_DOWNLOAD_GB}


def iniciar_download(pasta_de_dados: Any) -> None:
    """Solta o download do modelo, uma vez só. Recusa dizendo o motivo."""
    if not programa_instalado():
        raise TranscricaoLocalErro(
            "O programa de transcrição (faster-whisper) não está instalado neste servidor. "
            "Ele entra na instalação do servidor novo.")
    if modelo_baixado(pasta_de_dados):
        raise TranscricaoLocalErro("O modelo já está neste servidor. Não se baixa de novo.")
    if _baixando_de_verdade(estado_do_download(pasta_de_dados)):
        raise TranscricaoLocalErro("O download já está em andamento.")
    Path(pasta_de_dados).mkdir(parents=True, exist_ok=True)
    livre_gb = shutil.disk_usage(pasta_de_dados).free / (1024 ** 3)
    if livre_gb < TAMANHO_DO_DOWNLOAD_GB + FOLGA_DE_DISCO_GB:
        raise TranscricaoLocalErro(
            f"Há {livre_gb:.1f} GB livres no disco da pasta de dados, e o modelo pede uns "
            f"{TAMANHO_DO_DOWNLOAD_GB} GB com folga. Nada foi baixado.")
    _gravar_estado(pasta_de_dados, situacao=BAIXANDO, inicio=_agora())
    _soltar(_comando("baixar", str(pasta_do_modelo(pasta_de_dados)),
                     str(_estado_em(pasta_de_dados)), MODELO))


def _sufixo(mime: str) -> str:
    return {"audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/amr": ".amr",
            "audio/wav": ".wav", "audio/webm": ".webm"}.get(str(mime or "").split(";")[0].strip(), ".ogg")


def _transcrever_no_trabalhador(pasta_de_dados: Any, audio: bytes, mime: str, prazo: int) -> dict:
    """Grava o áudio, roda o trabalhador, lê a resposta e apaga os dois arquivos."""
    if len(audio) > TETO_DE_BYTES:
        raise TranscricaoErro("O áudio passa de 16 MB e não foi transcrito.")
    trabalho = Path(pasta_de_dados) / PASTA / "em_andamento"
    trabalho.mkdir(parents=True, exist_ok=True)
    marca = uuid.uuid4().hex
    entrada = trabalho / f"{marca}{_sufixo(mime)}"
    saida = trabalho / f"{marca}.json"
    inicio = time.monotonic()
    try:
        entrada.write_bytes(audio)
        try:
            r = _processo(_comando("transcrever", str(pasta_do_modelo(pasta_de_dados)),
                                   str(entrada), str(saida)), prazo)
        except subprocess.TimeoutExpired as falha:
            raise TranscricaoErro(
                f"A transcrição neste servidor passou de {prazo} s e foi interrompida. "
                "O áudio fica para quem atende ouvir.") from falha
        except OSError as falha:
            raise TranscricaoErro("Não consegui iniciar a transcrição neste servidor. "
                                  "O áudio fica para quem atende ouvir.") from falha
        if r.returncode != 0 or not saida.is_file():
            LOG.warning("o trabalhador da transcrição saiu com %s: %s", r.returncode,
                        (r.stderr or b"")[-300:].decode("utf-8", "replace"))
            raise TranscricaoErro("A transcrição neste servidor falhou, talvez por falta de "
                                  "memória. O áudio fica para quem atende ouvir.")
        dados = json.loads(saida.read_text(encoding="utf-8"))
    except ValueError as falha:
        if isinstance(falha, TranscricaoErro):
            raise
        raise TranscricaoErro("A transcrição neste servidor voltou num formato que eu não "
                              "entendi.") from falha
    finally:
        for arquivo in (entrada, saida):
            arquivo.unlink(missing_ok=True)
    return {"texto": str(dados.get("texto") or "").strip(),
            "segundos": float(dados.get("segundos") or 0),
            "trabalho_s": round(time.monotonic() - inicio, 1)}


def transcrever(pasta_de_dados: Any, audio: bytes, mime: str, *, modelo: str = "",
                preco_por_minuto: float | None = None, modulo: str = "", finalidade: str = "",
                usuario: str = "", referencia: str = "", https: Callable | None = None) -> dict:
    """O texto do áudio, sem o áudio sair da casa. Mesma forma de `wa_transcricao.transcrever`.

    `modelo`, o preço e `https` existem só para a chamada ser igual: aqui não há rede nem
    custo por minuto. A linha de `ia_uso` continua, porque é ela que conta o teto do dia."""
    registro = {"modulo": modulo, "finalidade": finalidade, "usuario": usuario,
                "referencia": referencia, "provedor": PROVEDOR, "modelo": MODELO}
    try:
        r = _transcrever_no_trabalhador(pasta_de_dados, audio, mime, PRAZO_POR_AUDIO_S)
    except TranscricaoErro as falha:
        USO.registrar(pasta_de_dados, **registro, resultado=USO.ERRO, erro=str(falha)[:80])
        raise
    USO.registrar(pasta_de_dados, **registro, resultado=USO.OK)
    return {"texto": r["texto"], "segundos": r["segundos"], "custo_usd": 0.0,
            "modelo": MODELO, "provedor": PROVEDOR}


def conferir(pasta_de_dados: Any, audio: bytes, mime: str, *, agora: str = "", por: str = "") -> dict:
    """A conferência antes de ligar: memória e um áudio de verdade. Recusa dizendo o motivo.

    Devolve {"ok", "motivo", "texto", ...}. **O texto não se guarda**: o áudio de teste pode
    trazer dado de cliente, e por isso `para_guardar` tira ele antes de ir ao banco."""
    resultado = {"ok": False, "motivo": "", "texto": "", "quando": agora, "por": por,
                 "modelo": MODELO, "memoria_livre_mb": RM.memoria_livre_mb(),
                 "segundos": 0.0, "trabalho_s": 0.0}
    if not programa_instalado():
        resultado["motivo"] = ("O programa de transcrição (faster-whisper) não está instalado "
                               "neste servidor. Ele entra na instalação do servidor novo.")
        return resultado
    if not modelo_baixado(pasta_de_dados):
        resultado["motivo"] = "Baixe o modelo antes de conferir."
        return resultado
    livre = resultado["memoria_livre_mb"]
    if livre and livre < MEMORIA_MINIMA_MB:
        resultado["motivo"] = (f"Há {livre} MB de memória livre, e o modelo grande pede uns "
                               f"{MEMORIA_MINIMA_MB} MB. Ele não coube em 3,1 GB na medição "
                               "de 29/10/2026.")
        return resultado
    if not audio:
        resultado["motivo"] = "Escolha um áudio com fala para a conferência."
        return resultado
    try:
        r = _transcrever_no_trabalhador(pasta_de_dados, audio, mime, PRAZO_DA_CONFERENCIA_S)
    except TranscricaoErro as falha:
        resultado["motivo"] = str(falha).replace(" O áudio fica para quem atende ouvir.", "")
        return resultado
    resultado.update(r)
    if not r["texto"]:
        resultado["motivo"] = "O modelo não achou fala nesse áudio. Use um áudio com fala."
        return resultado
    if r["trabalho_s"] > max(LENTO_BASE_S, r["segundos"] * LENTO_FATOR):
        resultado["motivo"] = (f"Levou {r['trabalho_s']:.0f} s para um áudio de "
                               f"{r['segundos']:.0f} s: lento demais para atender. Com a "
                               "transcrição neste servidor, os downloads, a IA das outras "
                               "conversas e o aviso de fora do horário esperam o áudio.")
        return resultado
    resultado["ok"] = True
    return resultado


def para_guardar(conferencia: dict) -> str:
    """A conferência como vai ao banco: sem o texto e sem o motivo cru. Só calcula."""
    return json.dumps({k: conferencia.get(k) for k in (
        "ok", "quando", "por", "modelo", "memoria_livre_mb", "segundos", "trabalho_s")},
        ensure_ascii=False)


def conferencia_guardada(texto: Any) -> dict:
    """A última conferência lida do banco, ou {} se não há. Só calcula."""
    try:
        dados = json.loads(str(texto or ""))
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}


def recado_da_conferencia(conferencia: dict) -> str:
    """A frase da tela. O texto do áudio aparece aqui uma vez, curto, e não se guarda."""
    if not conferencia["ok"]:
        return f"Conferência recusada: {conferencia['motivo']}"
    texto = conferencia["texto"]
    if len(texto) > TEXTO_NA_TELA:
        texto = texto[:TEXTO_NA_TELA] + "…"
    return (f"Conferência aprovada: {conferencia['trabalho_s']:.0f} s para um áudio de "
            f"{conferencia['segundos']:.0f} s, com {conferencia['memoria_livre_mb']} MB livres. "
            f"O que ele entendeu: «{texto}»")


def pode_ligar(pasta_de_dados: Any, conferencia: dict) -> str:
    """Por que não dá para ligar neste servidor, ou "" se dá. SÓ LÊ."""
    if not programa_instalado():
        return "O programa de transcrição não está instalado neste servidor."
    if not modelo_baixado(pasta_de_dados):
        return "O modelo ainda não foi baixado."
    if not conferencia.get("ok"):
        return "Falta a conferência aprovada, com um áudio de verdade."
    return ""

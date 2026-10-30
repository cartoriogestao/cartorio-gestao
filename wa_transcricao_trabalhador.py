"""O trabalhador da transcrição neste servidor: nasce para um áudio, ou para o download, e morre.

SÓ BIBLIOTECA PADRÃO E O PROGRAMA DE TRANSCRIÇÃO. Nada do sistema entra aqui: este processo
não abre banco, não carrega o Flask e não sabe de cliente. Quem o chama, e quem lê o que ele
deixa, é `wa_transcricao_local`.

    python wa_transcricao_trabalhador.py baixar <pasta do modelo> <estado.json> <modelo>
    python wa_transcricao_trabalhador.py transcrever <pasta do modelo> <entrada> <saida.json>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

BAIXANDO = "BAIXANDO"
PRONTO = "PRONTO"
ERRO = "ERRO"


def _gravar(alvo: str, dados: dict) -> None:
    """Grava inteiro ou não grava: quem lê nunca vê metade de um JSON."""
    temporario = Path(alvo).with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(temporario, alvo)


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def baixar(pasta_do_modelo: str, estado: str, modelo: str) -> int:
    inicio = _agora()
    try:
        from faster_whisper import download_model
        download_model(modelo, output_dir=pasta_do_modelo)
    except Exception as falha:                                     # noqa: BLE001
        _gravar(estado, {"situacao": ERRO, "inicio": inicio,
                         "erro": f"{type(falha).__name__}: {str(falha)[:200]}"})
        return 1
    _gravar(estado, {"situacao": PRONTO, "inicio": inicio, "fim": _agora()})
    return 0


def transcrever(pasta_do_modelo: str, entrada: str, saida: str) -> int:
    """Os mesmos parâmetros da medição de 29/10/2026: CPU, int8, beam 5."""
    from faster_whisper import WhisperModel
    modelo = WhisperModel(pasta_do_modelo, device="cpu", compute_type="int8")
    segmentos, info = modelo.transcribe(entrada, language="pt", beam_size=5, vad_filter=False)
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    _gravar(saida, {"texto": texto, "segundos": float(info.duration)})
    return 0


def main(argv: list[str] | None = None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    if len(argumentos) == 4 and argumentos[0] == "baixar":
        return baixar(*argumentos[1:])
    if len(argumentos) == 4 and argumentos[0] == "transcrever":
        return transcrever(*argumentos[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

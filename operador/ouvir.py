"""OUVIR — o áudio que o oficial manda vira texto, pelo caminho que a casa já
usa para os áudios do WhatsApp (`docs/TRANSCRICAO_NO_SERVIDOR.md`).

POR QUE EXISTE: o pedido «do celular, em deslocamento» é quase sempre falado, e
o Claude Code não ouve áudio. A ponte chama este programa num processo à
parte — ele carrega os módulos da casa, transcreve e morre.

    python operador/ouvir.py <arquivo.ogg>      → imprime o texto

A ESCOLHA DO CAMINHO (`OPERADOR_AUDIO` no `operador.cred`):
    auto   (padrão) neste servidor, se o modelo estiver instalado; senão, pela
           OpenAI, com a chave que a casa já tem — é o mesmo caminho dos
           áudios do WhatsApp, e o áudio SAI do cartório;
    local  só neste servidor; sem o modelo, não transcreve;
    nao    não transcreve: o oficial escreve ou dita pelo teclado.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intervencao as INT  # noqa: E402

_MIME = {".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg",
         ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
         ".wav": "audio/wav", ".webm": "audio/webm"}


class NaoOuvi(RuntimeError):
    """Não deu para transcrever, com a frase pronta para o oficial."""


def ouvir(arquivo: Path, escolha: str = "auto") -> str:
    escolha = (escolha or "auto").strip().lower()
    if escolha == "nao":
        raise NaoOuvi("a transcrição de áudio está desligada neste servidor")
    raiz = str(INT.raiz_do_sistema())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    audio = Path(arquivo).read_bytes()
    mime = _MIME.get(Path(arquivo).suffix.lower(), "audio/ogg")
    dados = str(INT.pasta_de_dados())
    de_quem = {"modulo": "superusuario", "finalidade": "pedido do oficial por voz",
               "usuario": INT.LOGIN}
    import wa_transcricao_local as LOCAL
    if LOCAL.programa_instalado() and LOCAL.modelo_baixado(dados):
        return str(LOCAL.transcrever(dados, audio, mime, **de_quem)["texto"]).strip()
    if escolha == "local":
        raise NaoOuvi("o modelo de transcrição não está instalado neste servidor")
    import wa_transcricao as WT
    return str(WT.transcrever(dados, audio, mime, **de_quem)["texto"]).strip()


def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("uso: python operador/ouvir.py <arquivo de áudio>", file=sys.stderr)
        return 2
    INT.carregar_ambiente()
    try:
        texto = ouvir(Path(argv[0]), os.environ.get("OPERADOR_AUDIO") or "auto")
    except Exception as falha:  # noqa: BLE001 — a frase vai para o oficial
        print(str(falha) or type(falha).__name__, file=sys.stderr)
        return 1
    if not texto:
        print("o áudio veio sem fala que eu entendesse", file=sys.stderr)
        return 1
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

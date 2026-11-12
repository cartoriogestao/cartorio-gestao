"""A GUARDA DO SUPERUSUÁRIO — o gancho que roda ANTES de cada ferramenta do
operador (PreToolUse do Claude Code) e que não depende de o modelo lembrar.

O operador tem poder total (ordem do oficial, 12/11/2026). A guarda não tira
poder; ela faz três coisas que prudência por instrução não garante:

1. GUARDA O ORIGINAL. Antes de todo Edit/Write num arquivo do sistema, copia o
   arquivo para a intervenção aberta (`intervencao.guardar`) — e abre uma, se
   não houver. É o que faz o relatório ter o diff.
2. PEDE O «CONFIRMO» PARA O QUE NÃO TEM VOLTA. Comando de shell com DROP,
   TRUNCATE, DELETE/UPDATE sem WHERE, sequência, `assumir.sh`, restauração de
   banco ou apagar pasta inteira só passa com a confirmação do oficial ainda
   válida (a ponte grava quando ele responde CONFIRMO).
3. NÃO DEIXA LER SEGREDO. `*.key`, `*.cred`, a chave privada do reserva, o
   `.pgpass` e a chave de assinatura das atualizações: o conteúdo iria para a
   API, e o operador não precisa dele — os programas da casa leem sozinhos.

Sai com 0 para deixar passar e com 2 para barrar (o texto do stderr é o que o
operador lê). Um erro da própria guarda NÃO barra: ela é cinto de segurança, e
não pode ser o motivo de o servidor ficar sem conserto.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intervencao as INT  # noqa: E402

_RE_SEGREDO = re.compile(
    r"(\.key\b|\.cred\b|\.pem\b|reserva-chave\.privada|\.pgpass\b|pgpass\.conf"
    r"|chave_da_sincronia\b)", re.I)

#: Shell que não tem volta, além do SQL (`intervencao.sem_volta`).
_RE_SHELL_SEM_VOLTA = re.compile(
    r"(\bassumir\.sh\b|\bpg_restore\b|\bdropdb\b|\bdropuser\b"
    r"|\brm\s+(-\w*\s+)*-\w*[rR]\w*\b|\bRemove-Item\b[^|;]*-Recurse"
    r"|\brmdir\s+/s\b|\bdel\s+/s\b|\bgit\s+push\b[^|;]*(--force|-f\b)"
    r"|\bgit\s+reset\s+--hard\b|\bshutdown\b|\bRestart-Computer\b|\bStop-Computer\b"
    r"|\bformat\s+[a-z]:|\bmkfs\b|\bdiskutil\s+erase)", re.I)

_FERRAMENTAS_DE_SHELL = ("Bash", "PowerShell")
_FERRAMENTAS_DE_ARQUIVO = ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit")


def decidir(ferramenta: str, entrada: dict) -> str | None:
    """A frase da recusa, ou None para deixar passar."""
    if ferramenta in _FERRAMENTAS_DE_ARQUIVO:
        caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
        if _RE_SEGREDO.search(caminho):
            return ("Arquivo de segredo: o conteúdo iria para fora do cartório. "
                    "Os programas da casa leem a credencial sozinhos; use-os.")
        if ferramenta != "Read" and caminho:
            INT.guardar([caminho])
        return None
    if ferramenta in _FERRAMENTAS_DE_SHELL:
        comando = str(entrada.get("command") or "")
        if _RE_SEGREDO.search(comando) and re.search(
                r"\b(cat|type|more|less|head|tail|Get-Content|gc|strings|xxd|base64"
                r"|cp|copy|Copy-Item|scp|curl|open)\b", comando, re.I):
            return ("O comando lê ou copia um arquivo de segredo. O conteúdo não "
                    "sai do servidor; use o programa da casa que o lê.")
        perigo = None
        achado = _RE_SHELL_SEM_VOLTA.search(comando)
        if achado:
            perigo = " ".join(achado.group(0).split())
        else:
            perigo = INT.sem_volta(comando)
        if perigo and not INT.confirmacao_valida():
            return (f"Isto não tem volta ({perigo}). Pare, diga ao oficial em "
                    "duas linhas o que vai fazer e o que se perde, e peça que "
                    "ele responda CONFIRMO. A confirmação vale "
                    f"{INT.VALIDADE_DA_CONFIRMACAO // 60} minutos.")
    return None


def main() -> int:
    try:
        chamada = json.loads(sys.stdin.read() or "{}")
        recusa = decidir(str(chamada.get("tool_name") or ""),
                         chamada.get("tool_input") or {})
    except Exception as erro:  # noqa: BLE001 — a guarda nunca é o defeito
        print(f"guarda: erro meu, deixei passar: {erro}", file=sys.stderr)
        return 0
    if recusa:
        print(recusa, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

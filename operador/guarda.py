"""A GUARDA DO SUPERUSUÁRIO — o gancho que roda ANTES de cada ferramenta do
operador (PreToolUse do Claude Code) e que não depende de o modelo lembrar.
Vale para todas as portas: é o posto que a liga (`posto.py`), não a ponte.

O operador tem poder total (ordem do oficial, 12/11/2026). A guarda não tira
poder; ela faz o que prudência por instrução não garante:

1. GUARDA O ORIGINAL. Antes de todo Edit/Write, copia o arquivo para a
   intervenção aberta (`intervencao.guardar`) — o do sistema para o patch, o de
   fora do sistema (configuração, serviço) para a lista à parte.
2. ANOTA CADA COMANDO DE SHELL na intervenção: o ato de informática que não
   muda arquivo nenhum (reiniciar serviço, mexer em tarefa) também fica.
3. PEDE O «CONFIRMO» PARA O QUE NÃO TEM VOLTA. DROP, TRUNCATE, DELETE/UPDATE
   sem WHERE, sequência, `assumir.sh`, restauração de banco, apagar pasta
   inteira — e mexer na própria guarda — só passam com a confirmação do
   oficial ainda válida. Quem grava a confirmação é a porta, quando ELE
   escreve CONFIRMO; o operador não a escreve.
4. MANDA A GRAVAÇÃO NO BANCO PELA FERRAMENTA. `psql` direto com verbo de
   escrita (ou com arquivo, que a guarda não lê) é barrado: gravar é pelo
   `sql`, que copia as tabelas antes; ler é pelo `consulta`.
5. NÃO DEIXA LER SEGREDO. `*.key`, `*.cred`, a chave privada do reserva, o
   `.pgpass` e a chave de assinatura das atualizações: o conteúdo iria para
   fora, e o operador não precisa dele — os programas da casa leem sozinhos.

Sai com 0 para deixar passar e com 2 para barrar (o texto do stderr é o que o
operador lê). Um erro da própria guarda NÃO barra: ela é cinto de segurança, e
não pode ser o motivo de o servidor ficar sem conserto.

A GUARDA NÃO É COFRE: ela reconhece padrões. Um operador com shell pode o que
o oficial pode; por isso só o oficial o aciona, e tudo fica registrado.
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
_RE_LE_OU_COPIA = re.compile(
    r"\b(cat|type|more|less|head|tail|Get-Content|gc|strings|xxd|base64"
    r"|cp|copy|Copy-Item|scp|curl|open|Select-String|grep|findstr)\b", re.I)

#: Shell que não tem volta, além do SQL (`intervencao.sem_volta`).
_RE_SHELL_SEM_VOLTA = re.compile(
    r"(\bassumir\.sh\b|\bemergencia\.sh\b|\bpg_restore\b|\bdropdb\b|\bdropuser\b"
    r"|\brm\s+(-\w*\s+)*-\w*[rR]\w*\b|\bRemove-Item\b[^|;]*-Recurse"
    r"|\brmdir\s+/s\b|\bdel\s+/s\b|\bgit\s+push\b[^|;]*(--force|-f\b)"
    r"|\bgit\s+reset\s+--hard\b|\bshutdown\b|\bRestart-Computer\b|\bStop-Computer\b"
    r"|\bformat\s+[a-z]:|\bmkfs\b|\bdiskutil\s+erase)", re.I)

#: A confirmação é do oficial: a porta a grava quando ele escreve CONFIRMO.
_RE_CONFIRMACAO = re.compile(r"(operador[\\/]+confirmacao\b|registrar_confirmacao)", re.I)
#: A guarda e o posto: mexer neles é mexer no que segura o operador.
_RE_DA_GUARDA = re.compile(
    r"(operador[\\/]+(guarda|posto|intervencao|ponte)\.py$"
    r"|posto[\\/]+\.claude[\\/]+settings[\w.]*\.json$)", re.I)

_RE_PSQL = re.compile(r"\bpsql(\.exe)?\b", re.I)
_RE_PSQL_COM_ARQUIVO = re.compile(r"(\s-f\b|\s--file\b|<\s*[\w./\\~$\"'])")

_FERRAMENTAS_DE_SHELL = ("Bash", "PowerShell")
_FERRAMENTAS_DE_ARQUIVO = ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit")
_FERRAMENTAS_DE_BUSCA = ("Grep", "Glob")

SEGREDO = ("Arquivo de segredo: o conteúdo iria para fora do cartório. Os "
           "programas da casa leem a credencial sozinhos; use-os.")


def _falta_o_confirmo(perigo: str) -> str:
    return (f"Isto não tem volta ({perigo}). Pare, diga ao oficial em duas "
            "linhas o que vai fazer e o que se perde, e peça que ele responda "
            f"CONFIRMO. A confirmação vale {INT.VALIDADE_DA_CONFIRMACAO // 60} minutos.")


def _do_shell(comando: str) -> str | None:
    if _RE_SEGREDO.search(comando) and _RE_LE_OU_COPIA.search(comando):
        return ("O comando lê ou copia um arquivo de segredo. O conteúdo não "
                "sai do servidor; use o programa da casa que o lê.")
    if _RE_CONFIRMACAO.search(comando):
        return ("A confirmação é do oficial: é a porta que a grava quando ele "
                "escreve CONFIRMO. Peça a ele.")
    if _RE_PSQL.search(comando) and (
            INT._RE_ESCRITA.search(comando) or _RE_PSQL_COM_ARQUIVO.search(comando)):
        return ("Gravação no banco não vai por `psql` direto: use a ferramenta "
                "`sql` (arquivo, --tabelas, --motivo), que copia as tabelas "
                "antes e registra. Para ler, use `consulta`.")
    achado = _RE_SHELL_SEM_VOLTA.search(comando)
    perigo = " ".join(achado.group(0).split()) if achado else INT.sem_volta(comando)
    if perigo and not INT.confirmacao_valida():
        return _falta_o_confirmo(perigo)
    return None


def decidir(ferramenta: str, entrada: dict) -> str | None:
    """A frase da recusa, ou None para deixar passar."""
    if ferramenta in _FERRAMENTAS_DE_BUSCA:
        onde = f"{entrada.get('path') or ''} {entrada.get('glob') or ''}"
        return SEGREDO if _RE_SEGREDO.search(onde) else None
    if ferramenta in _FERRAMENTAS_DE_ARQUIVO:
        caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
        if _RE_SEGREDO.search(caminho):
            return SEGREDO
        if ferramenta != "Read" and caminho:
            if _RE_CONFIRMACAO.search(caminho):
                return ("A confirmação é do oficial: é a porta que a grava "
                        "quando ele escreve CONFIRMO. Peça a ele.")
            if _RE_DA_GUARDA.search(caminho) and not INT.confirmacao_valida():
                return _falta_o_confirmo("mexer na guarda ou no posto do operador")
            INT.guardar([caminho])
        return None
    if ferramenta in _FERRAMENTAS_DE_SHELL:
        comando = str(entrada.get("command") or "")
        recusa = _do_shell(comando)
        try:
            INT.registrar_comando(ferramenta, comando, recusa or "")
        except OSError:
            pass            # sem disco para anotar, o comando não deixa de passar
        return recusa
    return None


def main() -> int:
    try:
        chamada = json.loads(sys.stdin.read() or "{}")
        INT.carregar_ambiente()
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

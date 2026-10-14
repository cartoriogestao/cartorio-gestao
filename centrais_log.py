"""O LOG ESTRUTURADO DAS CENTRAIS — por Central e por operação.

Construído em 05/10/2026, marco (a) da base comum das integrações. Dono:
RCPN/Protesto; Notas e RI consomem.

**DOIS DESTINOS, A MESMA LINHA.** Cada registro vai para a tabela
`centrais_log` (é o que o painel `/centrais/status` lê) e para o `logging` do
Python, no logger `cartorio_gestao.centrais`, como uma linha JSON — quem
configurar um handler (arquivo, console do serviço) recebe o mesmo dado sem
ninguém escrever um segundo formato.

**O LOG NUNCA GUARDA SEGREDO, NEM DADO DE GENTE.** Passa tudo por `sanitizar`:

  - chaves que cheiram a segredo (`senha`, `token`, `authorization`,
    `x-api-key`, `client_secret`…) saem como `«omitido»`;
  - CPF e CNPJ — com ou sem máscara — saem mascarados, sobrando só os dois
    últimos dígitos (o bastante para conferir, pouco para identificar);
  - texto longo é cortado: log não é lugar de corpo de remessa.

**O LOG NÃO FALA COM A REDE, E A REDE NÃO ESCREVE NO BANCO.** `centrais_http`
não recebe `con`; quem chamou a Central registra **depois**, numa transação
curta. É a regra do selador: `BEGIN IMMEDIATE` segurado por trinta segundos de
rede põe todo outro balcão no `busy_timeout`.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime
from typing import Any

import centrais_schema as SCH

LOGGER = logging.getLogger("cartorio_gestao.centrais")

FORMATO_DA_HORA = "%Y-%m-%dT%H:%M:%S"   # o mesmo `ISO_DT` de `database.py`
LIMITE_DA_MENSAGEM = 500
LIMITE_DO_DETALHE = 4000
OMITIDO = "«omitido»"

# AS CHAVES QUE NÃO SE ESCREVEM. Comparação sem caixa e sem `-`/`_`.
_CHAVES_SECRETAS = frozenset({
    "senha", "password", "passwd", "secret", "clientsecret", "token",
    "accesstoken", "refreshtoken", "idtoken", "authorization", "xapikey",
    "apikey", "cookie", "setcookie", "chaveprivada", "privatekey",
})

# CPF (NNN.NNN.NNN-NN ou 11 dígitos) e CNPJ (NN.NNN.NNN/NNNN-NN ou 14).
# `(?<!\d)`/`(?!\d)` para não morder pedaço de número maior (chave CENPROT
# de 23 dígitos, protocolo, matrícula de 32).
_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
# Bearer/Basic que escapou para dentro de uma mensagem de erro.
_PORTADOR = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")


def agora() -> str:
    """A hora local no formato da casa. Só calcula."""
    return datetime.now().replace(microsecond=0).strftime(FORMATO_DA_HORA)


def _chave_secreta(nome: Any) -> bool:
    limpo = re.sub(r"[-_\s]", "", str(nome or "")).lower()
    return limpo in _CHAVES_SECRETAS


def _mascarar_numero(achado: re.Match) -> str:
    digitos = re.sub(r"\D", "", achado.group(0))
    return "*" * (len(digitos) - 2) + digitos[-2:]


def mascarar_texto(texto: Any, limite: int = LIMITE_DA_MENSAGEM) -> str:
    """Tira CPF/CNPJ e token de dentro de um texto, e corta. Só calcula."""
    s = str(texto if texto is not None else "")
    s = _PORTADOR.sub(lambda m: f"{m.group(1)} {OMITIDO}", s)
    s = _CNPJ.sub(_mascarar_numero, s)
    s = _CPF.sub(_mascarar_numero, s)
    if len(s) > limite:
        s = s[:limite] + "…"
    return s


def sanitizar(valor: Any, _profundidade: int = 0) -> Any:
    """Copia `valor` sem segredo e sem CPF/CNPJ. Só calcula; não muda o original."""
    if _profundidade > 6:
        return "…"
    if isinstance(valor, dict):
        return {str(k): (OMITIDO if _chave_secreta(k)
                         else sanitizar(v, _profundidade + 1))
                for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [sanitizar(v, _profundidade + 1) for v in list(valor)[:50]]
    if isinstance(valor, (bytes, bytearray)):
        return f"<{len(valor)} bytes>"
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    return mascarar_texto(valor)


def linha_estruturada(**campos: Any) -> str:
    """A linha JSON que vai para o `logging`. Já sanitizada."""
    return json.dumps(sanitizar(campos), ensure_ascii=False, sort_keys=True,
                      default=str)


def registrar(con: sqlite3.Connection, central: str, operacao: str,
              evento: str, *, nivel: str = SCH.INFO,
              ambiente: str | None = None, fila_id: int | None = None,
              status_http: int | None = None, duracao_ms: int | None = None,
              mensagem: str = "", detalhe: Any = None) -> int:
    """Grava uma linha de log (banco + `logging`). Devolve o id.

    Escreve na conexão de quem chamou — **não abre transação nem faz
    commit**; quem chama decide (normalmente dentro de `db.transaction()`,
    DEPOIS da chamada de rede).
    """
    qual = str(central or "").strip().upper() or "?"
    oper = str(operacao or "").strip() or "?"
    niv = str(nivel or SCH.INFO).strip().upper()
    if niv not in SCH.NIVEIS:
        niv = SCH.INFO
    msg = mascarar_texto(mensagem)
    det = None
    if detalhe is not None:
        det = json.dumps(sanitizar(detalhe), ensure_ascii=False, default=str)
        if len(det) > LIMITE_DO_DETALHE:
            det = det[:LIMITE_DO_DETALHE] + "…"
    quando = agora()
    cur = con.execute(
        "INSERT INTO centrais_log (quando, central, operacao, ambiente, nivel,"
        " evento, fila_id, status_http, duracao_ms, mensagem, detalhe)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (quando, qual, oper, (ambiente or None), niv, str(evento or "?"),
         fila_id, status_http, duracao_ms, msg, det))
    nivel_py = {SCH.INFO: logging.INFO, SCH.AVISO: logging.WARNING,
                SCH.ERRO: logging.ERROR}[niv]
    LOGGER.log(nivel_py, linha_estruturada(
        quando=quando, central=qual, operacao=oper, ambiente=ambiente,
        nivel=niv, evento=evento, fila_id=fila_id, status_http=status_http,
        duracao_ms=duracao_ms, mensagem=msg))
    return int(cur.lastrowid)


def registrar_resposta(con: sqlite3.Connection, central: str, operacao: str,
                       resposta: Any, *, ambiente: str | None = None,
                       fila_id: int | None = None) -> int:
    """Registra uma `centrais_http.Resposta` (ou `CentralHttpError`).

    2xx vira INFO; 4xx, AVISO; 5xx e falha de transporte, ERRO. O corpo da
    resposta **não** entra — só o status, a duração e as tentativas.
    """
    if isinstance(resposta, BaseException):
        return registrar(
            con, central, operacao, "FALHA_DE_TRANSPORTE", nivel=SCH.ERRO,
            ambiente=ambiente, fila_id=fila_id, mensagem=str(resposta),
            detalhe={"tentativas": getattr(resposta, "tentativas", None),
                     "tipo": type(resposta).__name__})
    status = int(getattr(resposta, "status", 0) or 0)
    nivel = (SCH.INFO if 200 <= status < 400
             else SCH.AVISO if status < 500 else SCH.ERRO)
    return registrar(
        con, central, operacao, "REQUISICAO", nivel=nivel, ambiente=ambiente,
        fila_id=fila_id, status_http=status,
        duracao_ms=getattr(resposta, "duracao_ms", None),
        mensagem=f"{getattr(resposta, 'metodo', '')} {status}".strip(),
        detalhe={"tentativas": getattr(resposta, "tentativas", None),
                 "url": getattr(resposta, "url", "")})


# ------------------------------------------------- o banco do log, para quem
# não recebe `con` (marco b, 05/10/2026)
#
# **AS `*_api.py` NÃO RECEBEM `con`, DE PROPÓSITO** — a chamada de rede nunca
# acontece dentro de `db.transaction()`. Mas o marco (b) manda registrar cada
# chamada com `registrar_resposta`, e ela precisa de uma conexão. A ponte é
# esta: o app liga o banco UMA vez (`centrais_web.registrar_rotas`), e a API
# anota **depois** da resposta, numa conexão curta própria.
#
# **A ESPERA É CURTA E A FALHA É CALADA, como a auditoria de `database.log`.**
# Com outro balcão segurando o banco, a linha de log desiste em 800 ms e vai
# só para o `logging` — entre devolver a resposta da Central sem a linha no
# painel e não devolver nada, o balcão precisa da resposta.

_BANCO: Any = None
ESPERA_DO_LOG_MS = 800


def ligar_banco(db: Any) -> None:
    """Diz em qual banco `anotar_resposta` grava. O app chama uma vez."""
    global _BANCO
    _BANCO = db


def anotar_resposta(central: str, operacao: str, resposta: Any, *,
                    ambiente: str | None = None,
                    fila_id: int | None = None) -> int | None:
    """`registrar_resposta` no banco ligado, em conexão curta. NUNCA estoura.

    Sem banco ligado (teste, script de linha de comando), vai só para o
    `logging`. Devolve o id da linha, ou None.
    """
    db = _BANCO
    if db is None:
        LOGGER.debug(linha_estruturada(
            central=central, operacao=operacao, ambiente=ambiente,
            evento="SEM_BANCO_LIGADO",
            status_http=getattr(resposta, "status", None)))
        return None
    try:
        if hasattr(db, "connect"):
            con = db.connect()
            try:
                con.execute(f"PRAGMA busy_timeout={int(ESPERA_DO_LOG_MS)}")
                con.execute("BEGIN IMMEDIATE")
                novo = registrar_resposta(con, central, operacao, resposta,
                                          ambiente=ambiente, fila_id=fila_id)
                con.commit()
                return novo
            except Exception:
                con.rollback()
                raise
            finally:
                con.close()
        with db.transaction() as con:
            return registrar_resposta(con, central, operacao, resposta,
                                      ambiente=ambiente, fila_id=fila_id)
    except Exception as erro:  # o log não derruba a resposta da Central
        LOGGER.warning(linha_estruturada(
            central=central, operacao=operacao, ambiente=ambiente,
            evento="LOG_NAO_GRAVADO", erro=f"{type(erro).__name__}: {erro}",
            status_http=getattr(resposta, "status", None)))
        return None


def ultimos(con: sqlite3.Connection, *, central: str | None = None,
            operacao: str | None = None, nivel: str | None = None,
            limite: int = 50) -> list[dict]:
    """As últimas linhas de log, mais novas primeiro. Só LÊ.

    Banco que ainda não tem a tabela (servidor de versão anterior que não
    reabriu o banco) devolve lista vazia, e não erro de tela.
    """
    onde, args = [], []
    if central:
        onde.append("central = ?")
        args.append(str(central).strip().upper())
    if operacao:
        onde.append("operacao = ?")
        args.append(str(operacao).strip())
    if nivel:
        onde.append("nivel = ?")
        args.append(str(nivel).strip().upper())
    sql = "SELECT * FROM centrais_log"
    if onde:
        sql += " WHERE " + " AND ".join(onde)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limite), 1000)))
    try:
        linhas = con.execute(sql, args).fetchall()
    except sqlite3.OperationalError as erro:
        if "no such table" in str(erro).lower():
            return []
        raise
    return [_como_dict(x) for x in linhas]


def _como_dict(linha: Any) -> dict:
    if isinstance(linha, sqlite3.Row):
        return {k: linha[k] for k in linha.keys()}
    return dict(linha)

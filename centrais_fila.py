"""A FILA GENÉRICA DE ENVIO E REPROCESSO DAS CENTRAIS.

Construído em 05/10/2026, marco (a) da base comum das integrações. Dono:
RCPN/Protesto; Notas e RI consomem. Tabela em `centrais_schema`.

**ESTE MÓDULO NÃO FALA COM CENTRAL NENHUMA.** Ele guarda o que espera a vez,
entrega o próximo a quem vai mandar, e anota o que aconteceu. Quem manda é o
módulo de domínio, pela função `enviar` que ele passa a `processar_proximo` —
e quem decide QUE algo vai para a fila é uma rota que o operador clicou, como
manda a regra da CENPROT («o que sai daqui sai porque alguém mandou»).

**PRODUÇÃO SÓ COM PERMISSÃO EXPLÍCITA.** `processar_proximo` recusa item de
`PRODUCAO` a menos que quem chama passe `permitir_producao=True`. Fila que
manda para a Central de verdade por omissão é o defeito que a escolha de
`HOMOLOGACAO` como padrão de fábrica existe para evitar.

**A REDE FICA FORA DA TRANSAÇÃO.** `processar_proximo` faz três passos:
pega o item numa transação curta (marca `PROCESSANDO`), chama `enviar` **sem
transação aberta**, e anota o resultado noutra transação curta. Item que
ficou `PROCESSANDO` porque o processo morreu no meio volta à fila por
`devolver_presos`.

**RETENTATIVA COM ESPERA CRESCENTE.** Falha que se retenta volta a
`PENDENTE` com `proxima_tentativa_em` empurrado (1, 2, 4, 8… minutos, teto de
uma hora); esgotadas as `max_tentativas`, vira `FALHOU` e só volta à mão,
pelo painel (`reprocessar`) — que é reprocesso LOCAL: devolve à fila, não
manda nada.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable

from bd_nativo import banco
import centrais_log as LOG
import centrais_schema as SCH

MAX_TENTATIVAS_PADRAO = 5
ESPERA_INICIAL_MIN = 1
ESPERA_MAXIMA_MIN = 60
MINUTOS_PARA_PRESO = 15

HOMOLOGACAO, PRODUCAO = "HOMOLOGACAO", "PRODUCAO"


class FilaError(ValueError):
    """Erro de regra da fila, com a frase pronta para o balcão."""


class FalhaDefinitiva(Exception):
    """Levantada por `enviar` quando não adianta tentar de novo (4xx de regra).

    O item vai direto para `FALHOU`, sem gastar as tentativas que sobram.
    """


def _hora(quando: datetime) -> str:
    return quando.replace(microsecond=0).strftime(LOG.FORMATO_DA_HORA)


def espera_da_tentativa(tentativas: int) -> int:
    """Minutos até a próxima tentativa, depois de `tentativas` falhas. Só calcula."""
    n = max(1, int(tentativas))
    return min(ESPERA_MAXIMA_MIN, ESPERA_INICIAL_MIN * (2 ** (n - 1)))


def _como_dict(linha: Any) -> dict | None:
    if linha is None:
        return None
    return dict(linha)


def item(con: sqlite3.Connection, item_id: int) -> dict | None:
    """Um item da fila, ou None. Só LÊ."""
    return _como_dict(banco(con).um(
        "SELECT * FROM centrais_fila WHERE id = %s", (int(item_id),)))


def enfileirar(con: sqlite3.Connection, central: str, operacao: str,
               payload_ref: str, *, ambiente: str = HOMOLOGACAO,
               chave: str | None = None,
               max_tentativas: int = MAX_TENTATIVAS_PADRAO,
               por: str | None = None) -> int:
    """Põe um pedido na fila e devolve o id. ESCREVE (na conexão de quem chama).

    Com `chave`, o mesmo pedido (central+operação+ambiente+chave) não entra
    duas vezes: devolve o id do que já está lá. `payload_ref` é a REFERÊNCIA
    do corpo (`tabela:id`, caminho) — nunca o corpo.
    """
    qual = str(central or "").strip().upper()
    oper = str(operacao or "").strip()
    ref = str(payload_ref or "").strip()
    amb = str(ambiente or "").strip().upper() or HOMOLOGACAO
    if not qual or not oper:
        raise FilaError("Informe a Central e a operação.")
    if not ref:
        raise FilaError("Informe a referência do que vai ser enviado.")
    if amb not in (HOMOLOGACAO, PRODUCAO, "TESTES"):
        raise FilaError(f"Ambiente desconhecido: «{ambiente}».")
    chave_limpa = (str(chave).strip() or None) if chave is not None else None
    bd = banco(con)
    if chave_limpa:
        ja = bd.um(
            "SELECT id FROM centrais_fila WHERE central = %s AND operacao = %s"
            " AND ambiente = %s AND chave = %s ORDER BY id",
            (qual, oper, amb, chave_limpa))
        if ja:
            return int(ja["id"])
    quando = LOG.agora()
    novo = int(bd.escrever(
        "INSERT INTO centrais_fila (central, operacao, ambiente, payload_ref,"
        " chave, status, tentativas, max_tentativas, criado_em,"
        " atualizado_em, criado_por) VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s)"
        " RETURNING id",
        (qual, oper, amb, ref, chave_limpa, SCH.PENDENTE,
         max(1, int(max_tentativas)), quando, quando, por))[0]["id"])
    LOG.registrar(con, qual, oper, "ENFILEIRADO", ambiente=amb, fila_id=novo,
                  mensagem=f"referência {ref}")
    return novo


def devolver_presos(con: sqlite3.Connection, *,
                    minutos: int = MINUTOS_PARA_PRESO) -> int:
    """Volta a `PENDENTE` o que ficou `PROCESSANDO` há mais de `minutos`.

    É o processo que morreu no meio. Devolve quantos voltaram. ESCREVE.
    """
    corte = _hora(datetime.now() - timedelta(minutes=int(minutos)))
    bd = banco(con)
    presos = bd.ler(
        "SELECT id, central, operacao, ambiente FROM centrais_fila"
        " WHERE status = %s AND atualizado_em < %s ORDER BY id",
        (SCH.PROCESSANDO, corte))
    quando = LOG.agora()
    for p in presos:
        bd.escrever(
            "UPDATE centrais_fila SET status = %s, atualizado_em = %s"
            " WHERE id = %s AND status = %s",
            (SCH.PENDENTE, quando, p["id"], SCH.PROCESSANDO))
        LOG.registrar(con, p["central"], p["operacao"], "DEVOLVIDO_A_FILA",
                      nivel=SCH.AVISO,
                      ambiente=p["ambiente"], fila_id=p["id"],
                      mensagem=f"ficou processando mais de {minutos} min")
    return len(presos)


def pegar_proximo(con: sqlite3.Connection, *, central: str | None = None,
                  operacao: str | None = None,
                  ambientes: tuple[str, ...] = (HOMOLOGACAO, "TESTES")
                  ) -> dict | None:
    """Marca como `PROCESSANDO` e devolve o próximo da vez, ou None. ESCREVE.

    Chame dentro de `db.transaction()` (BEGIN IMMEDIATE): é a trava que
    impede dois processos de pegarem o mesmo item. `ambientes` filtra —
    por padrão, **produção fica de fora**.
    """
    bd = banco(con)
    onde = ["status = %s", "(proxima_tentativa_em IS NULL"
            " OR proxima_tentativa_em <= %s)"]
    args: list[Any] = [SCH.PENDENTE, LOG.agora()]
    if central:
        onde.append("central = %s")
        args.append(str(central).strip().upper())
    if operacao:
        onde.append("operacao = %s")
        args.append(str(operacao).strip())
    if ambientes:
        onde.append("ambiente IN (" + ",".join(["%s"] * len(ambientes)) + ")")
        args.extend(str(a).upper() for a in ambientes)
    bd._escrita()
    linha = bd.um(
        "SELECT * FROM centrais_fila WHERE " + " AND ".join(onde)
        + " ORDER BY id LIMIT 1 FOR UPDATE", args)
    if linha is None:
        return None
    bd.escrever(
        "UPDATE centrais_fila SET status = %s, tentativas = tentativas + 1,"
        " atualizado_em = %s WHERE id = %s",
        (SCH.PROCESSANDO, LOG.agora(), linha["id"]))
    return item(con, linha["id"])


def marcar_enviado(con: sqlite3.Connection, item_id: int, *,
                   resposta_ref: str | None = None,
                   status_http: int | None = None) -> None:
    """A Central recebeu. **Recebido não é confirmado.** ESCREVE."""
    atual = _exigir(con, item_id)
    quando = LOG.agora()
    banco(con).escrever(
        "UPDATE centrais_fila SET status = %s, erro = NULL, resposta_ref = %s,"
        " enviado_em = %s, atualizado_em = %s, proxima_tentativa_em = NULL"
        " WHERE id = %s",
        (SCH.ENVIADO, resposta_ref, quando, quando, int(item_id)))
    LOG.registrar(con, atual["central"], atual["operacao"], "ENVIADO",
                  ambiente=atual["ambiente"], fila_id=int(item_id),
                  status_http=status_http,
                  mensagem=f"protocolo {resposta_ref}" if resposta_ref else "")


def marcar_confirmado(con: sqlite3.Connection, item_id: int, *,
                      resposta_ref: str | None = None) -> None:
    """A Central confirmou o processamento. ESCREVE."""
    atual = _exigir(con, item_id)
    quando = LOG.agora()
    banco(con).escrever(
        "UPDATE centrais_fila SET status = %s, confirmado_em = %s,"
        " atualizado_em = %s, resposta_ref = COALESCE(%s, resposta_ref)"
        " WHERE id = %s",
        (SCH.CONFIRMADO, quando, quando, resposta_ref, int(item_id)))
    LOG.registrar(con, atual["central"], atual["operacao"], "CONFIRMADO",
                  ambiente=atual["ambiente"], fila_id=int(item_id))


def marcar_falha(con: sqlite3.Connection, item_id: int, erro: Any, *,
                 definitiva: bool = False,
                 status_http: int | None = None) -> str:
    """Anota a falha; volta para a fila com espera, ou vira `FALHOU`. ESCREVE.

    Devolve a situação nova. A mensagem é sanitizada antes de gravar.
    """
    atual = _exigir(con, item_id)
    texto = LOG.mascarar_texto(erro)
    tentativas = int(atual["tentativas"] or 0)
    esgotou = definitiva or tentativas >= int(atual["max_tentativas"] or 1)
    agora_dt = datetime.now()
    if esgotou:
        novo, proxima = SCH.FALHOU, None
    else:
        novo = SCH.PENDENTE
        proxima = _hora(agora_dt + timedelta(
            minutes=espera_da_tentativa(tentativas)))
    banco(con).escrever(
        "UPDATE centrais_fila SET status = %s, erro = %s,"
        " proxima_tentativa_em = %s, atualizado_em = %s WHERE id = %s",
        (novo, texto, proxima, _hora(agora_dt), int(item_id)))
    LOG.registrar(con, atual["central"], atual["operacao"], "FALHA",
                  nivel=SCH.ERRO if esgotou else SCH.AVISO,
                  ambiente=atual["ambiente"], fila_id=int(item_id),
                  status_http=status_http, mensagem=texto,
                  detalhe={"tentativas": tentativas, "situacao": novo,
                           "proxima_tentativa_em": proxima})
    return novo


def reprocessar(con: sqlite3.Connection, item_id: int, *,
                por: str | None = None) -> dict:
    """REPROCESSO LOCAL: devolve à fila um item `FALHOU`/`CANCELADO`. ESCREVE.

    **Não manda nada à Central** — só põe o item de volta em `PENDENTE`, com
    as tentativas zeradas e sem espera. Quem manda é o processador do
    domínio, na próxima passada.
    """
    atual = _exigir(con, item_id)
    if atual["status"] not in SCH.SITUACOES_REPROCESSAVEIS:
        raise FilaError(
            f"O item {item_id} está «{atual['status']}» e não se reprocessa — "
            f"só os que falharam ou foram cancelados voltam à fila.")
    banco(con).escrever(
        "UPDATE centrais_fila SET status = %s, tentativas = 0,"
        " proxima_tentativa_em = NULL, atualizado_em = %s WHERE id = %s",
        (SCH.PENDENTE, LOG.agora(), int(item_id)))
    LOG.registrar(con, atual["central"], atual["operacao"], "REPROCESSO",
                  ambiente=atual["ambiente"], fila_id=int(item_id),
                  mensagem=f"devolvido à fila por {por or 'sistema'}",
                  detalhe={"tentativas_anteriores": atual["tentativas"],
                           "situacao_anterior": atual["status"]})
    return item(con, item_id) or {}


def cancelar(con: sqlite3.Connection, item_id: int, *,
             por: str | None = None, motivo: str = "") -> None:
    """Tira da fila um item que ainda não foi enviado. ESCREVE."""
    atual = _exigir(con, item_id)
    if atual["status"] not in (SCH.PENDENTE, SCH.FALHOU):
        raise FilaError(
            f"O item {item_id} está «{atual['status']}» e não se cancela.")
    banco(con).escrever(
        "UPDATE centrais_fila SET status = %s, atualizado_em = %s WHERE id = %s",
        (SCH.CANCELADO, LOG.agora(), int(item_id)))
    LOG.registrar(con, atual["central"], atual["operacao"], "CANCELADO",
                  ambiente=atual["ambiente"], fila_id=int(item_id),
                  mensagem=f"por {por or 'sistema'}: {motivo}".strip())


def processar_proximo(db: Any, enviar: Callable[[dict], Any], *,
                      central: str | None = None,
                      operacao: str | None = None,
                      permitir_producao: bool = False) -> dict | None:
    """Pega o próximo, chama `enviar(item)` FORA da transação, anota. 

    `enviar` recebe o dict do item e devolve o `resposta_ref` (protocolo) ou
    None; levanta `FalhaDefinitiva` para não retentar, ou qualquer outra
    exceção para retentar com espera. Devolve o item já atualizado, ou None
    se não havia nada na vez.

    `db` é o `database.Database` (precisa de `.transaction()`). Produção só
    entra com `permitir_producao=True` — ver o cabeçalho.
    """
    ambientes = ((HOMOLOGACAO, "TESTES", PRODUCAO) if permitir_producao
                 else (HOMOLOGACAO, "TESTES"))
    with db.transaction() as con:
        devolver_presos(con)
        vez = pegar_proximo(con, central=central, operacao=operacao,
                            ambientes=ambientes)
    if vez is None:
        return None
    try:
        protocolo = enviar(vez)            # <- A REDE, sem transação aberta
    except FalhaDefinitiva as erro:
        with db.transaction() as con:
            marcar_falha(con, vez["id"], erro, definitiva=True,
                         status_http=getattr(erro, "status_http", None))
            return item(con, vez["id"])
    except Exception as erro:              # qualquer outra: retenta
        with db.transaction() as con:
            marcar_falha(con, vez["id"], erro,
                         status_http=getattr(erro, "status_http", None))
            return item(con, vez["id"])
    with db.transaction() as con:
        marcar_enviado(con, vez["id"],
                       resposta_ref=(str(protocolo) if protocolo else None))
        return item(con, vez["id"])


def resumo_por_central(con: sqlite3.Connection) -> list[dict]:
    """Quantos itens por Central e situação, para o painel. Só LÊ.

    Devolve `[{central, total, PENDENTE, PROCESSANDO, …}]`. Banco sem a
    tabela (versão anterior que não reabriu o banco) devolve lista vazia.
    """
    try:
        linhas = banco(con).ler(
            "SELECT central, status, COUNT(*) AS n FROM centrais_fila"
            " GROUP BY central, status ORDER BY central, status")
    except sqlite3.OperationalError as erro:
        if "no such table" in str(erro).lower():
            return []
        raise
    por: dict[str, dict] = {}
    for r in linhas:
        c, s, n = r["central"], r["status"], r["n"]
        d = por.setdefault(c, {"central": c, "total": 0,
                               **{x: 0 for x in SCH.SITUACOES}})
        d[s] = d.get(s, 0) + int(n)
        d["total"] += int(n)
    return list(por.values())


def ultimas_falhas(con: sqlite3.Connection, *, central: str | None = None,
                   limite: int = 20) -> list[dict]:
    """Os itens com erro (FALHOU, ou PENDENTE esperando nova tentativa). Só LÊ."""
    sql = ("SELECT * FROM centrais_fila WHERE (status = %s OR"
           " (status = %s AND erro IS NOT NULL))")
    args: list[Any] = [SCH.FALHOU, SCH.PENDENTE]
    if central:
        sql += " AND central = %s"
        args.append(str(central).strip().upper())
    sql += " ORDER BY atualizado_em DESC, id DESC LIMIT %s"
    args.append(max(1, min(int(limite), 500)))
    try:
        return [_como_dict(x) for x in banco(con).ler(sql, args)]
    except sqlite3.OperationalError as erro:
        if "no such table" in str(erro).lower():
            return []
        raise


def listar(con: sqlite3.Connection, *, central: str | None = None,
           status: str | None = None, limite: int = 100) -> list[dict]:
    """Os itens da fila, mais recentes primeiro, com filtro opcional. Só LÊ."""
    onde, args = [], []
    if central:
        onde.append("central = %s")
        args.append(str(central).strip().upper())
    if status:
        onde.append("status = %s")
        args.append(str(status).strip().upper())
    sql = "SELECT * FROM centrais_fila"
    if onde:
        sql += " WHERE " + " AND ".join(onde)
    sql += " ORDER BY id DESC LIMIT %s"
    args.append(max(1, min(int(limite), 1000)))
    try:
        return [_como_dict(x) for x in banco(con).ler(sql, args)]
    except sqlite3.OperationalError as erro:
        if "no such table" in str(erro).lower():
            return []
        raise


def _exigir(con: sqlite3.Connection, item_id: int) -> dict:
    atual = item(con, item_id)
    if atual is None:
        raise FilaError(f"O item {item_id} não está na fila.")
    return atual

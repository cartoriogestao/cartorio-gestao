# -*- coding: utf-8 -*-
"""Quem age por programa diz quem é e a mando de quem age.

    «obrigação de todo robô se identificar e dizer a mando de quem está
     agindo» — o oficial, 26/10/2026

O QUE SE MEDIU ANTES (produção, só leitura, 26/10/2026)
    Nenhuma conta com `users.eh_robo=1`. Nos últimos 30 dias, ~23,3 mil linhas
    de `audit_logs` gravadas SEM usuário — rotinas, agentes e scripts que gravam
    direto —, e só o texto livre de algumas dizia quem era. Uma auditoria que
    não responde «quem fez» não serve à correição.

O DESENHO, EM DUAS ETAPAS (aprovado pelo oficial)
    1. ESTA. Toda linha de auditoria leva `agente` (quem agiu por programa) e
       `a_mando_de` (a pessoa que responde pela ordem). A conta de robô tem
       responsável (`users.robo_responsavel_id`); a rotina sem conta declara o
       próprio nome e recebe o «responsável pelas rotinas automáticas». A linha
       que chega sem usuário e sem identificação **grava assim mesmo** e é
       contada — a conferência do gestor a mostra ao oficial.
    2. DEPOIS, noutro PR, quando o aviso zerar: a mesma linha é RECUSADA. A
       troca é UMA linha — `MODO = MODO_RECUSAR` — e quem decide é só
       `decidir`. Ninguém mais no sistema pergunta «aviso ou recuso».

O QUE ESTE MÓDULO NÃO FAZ, DE PROPÓSITO
    Não lê texto procurando nome de IA, «bot», cadência ou qualquer marca:
    ordem do oficial, «nada de marca contra robô». A identidade é a que se
    DECLARA — a conta (`eh_robo`) ou o `agente=` de quem grava. Robô usando a
    senha de uma pessoa é proibido por regra escrita (`docs/IDENTIDADE_DOS_ROBOS.md`),
    e não por programa: programa nenhum distingue a mão da pessoa da do robô
    que tem a senha dela.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, timedelta
from typing import Any

from bd_nativo import banco

_LOG = logging.getLogger("cartorio.identidade")

# ------------------------------------------------------------- a regra única

MODO_AVISAR = "AVISAR"
MODO_RECUSAR = "RECUSAR"
#: ETAPA 1 (26/10/2026): grava e avisa. A etapa 2 troca para `MODO_RECUSAR`,
#: noutro PR, quando a conferência «identidade dos robôs» zerar.
MODO = MODO_AVISAR

#: As situações de uma linha de auditoria, do ponto de vista de quem agiu.
PESSOA = "PESSOA"                              # gente, com a própria conta
ROBO = "ROBO"                                  # conta de robô com responsável
ROBO_SEM_RESPONSAVEL = "ROBO_SEM_RESPONSAVEL"  # conta de robô sem responsável
AGENTE = "AGENTE"                              # rotina/agente que se declarou
AGENTE_SEM_MANDANTE = "AGENTE_SEM_MANDANTE"    # declarou o nome, não a ordem
SEM_IDENTIFICACAO = "SEM_IDENTIFICACAO"        # sem usuário e sem agente

#: O que FALTA — avisa na etapa 1, recusa na etapa 2.
EM_FALTA = frozenset({ROBO_SEM_RESPONSAVEL, AGENTE_SEM_MANDANTE, SEM_IDENTIFICACAO})

GRAVAR = "GRAVAR"
AVISAR = "AVISAR"
RECUSAR = "RECUSAR"


class SemIdentificacao(ValueError):
    """Etapa 2: a linha não diz quem agiu nem a mando de quem."""


def decidir(situacao: str, modo: str | None = None) -> str:
    """GRAVAR, AVISAR ou RECUSAR. É o ÚNICO lugar que decide. Só calcula."""
    if situacao not in EM_FALTA:
        return GRAVAR
    return RECUSAR if (modo or MODO) == MODO_RECUSAR else AVISAR


#: Quantas linhas chegaram em falta desde que o processo subiu, por
#: (situação, action, entity_type). A conta que vale é a do banco
#: (`conferencia`); esta é a do processo, para o log do servidor.
CONTADOR: Counter = Counter()

# ------------------------------------------------------------------ o esquema

#: Só `ADD COLUMN` (regra da casa). Sem índice: a conferência lê pela faixa de
#: `ts`, que já tem o `idx_audit_ts`.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("users", "robo_responsavel_id", "INTEGER REFERENCES users(id)"),
    ("audit_logs", "agente", "TEXT"),
    ("audit_logs", "a_mando_de", "TEXT"),
)

#: A configuração «responsável pelas rotinas automáticas» (id de `users`).
#: Vazia — ou apontando para quem não é pessoa ativa — vale o primeiro ADMIN
#: ativo que não é robô.
CHAVE_RESPONSAVEL = "responsavel_rotinas_automaticas"

#: A rotina que é o próprio servidor: backup automático, login recusado,
#: requisição sem ninguém logado.
AGENTE_SERVIDOR = "servidor do Cartório Gestão"

#: Janela da conferência, em dias.
DIAS_DO_AVISO = 30


class _PeloResponsavel:
    """Marca para `a_mando_de=`: «o responsável pelas rotinas automáticas»,
    resolvido na MESMA conexão de quem grava — sem abrir outra só para isso."""

    def __repr__(self) -> str:
        return "PELO_RESPONSAVEL"


#: `registrar(..., agente="backup automático", a_mando_de=PELO_RESPONSAVEL)`.
PELO_RESPONSAVEL = _PeloResponsavel()


def init_identidade_schema(con) -> None:
    """As três colunas. Idempotente; tabela que não existe fica como está."""
    bd = banco(con)
    for tabela, coluna, tipo in MIGRACOES:
        if bd.tem_tabela(tabela) and not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def _colunas(bd) -> set[str]:
    """As colunas da identidade que este banco já tem, numa consulta só."""
    return {f"{r['table_name']}.{r['column_name']}" for r in bd.ler(
        """SELECT table_name, column_name FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND ((table_name = 'audit_logs' AND column_name IN ('agente', 'a_mando_de'))
                OR (table_name = 'users' AND column_name IN ('eh_robo', 'robo_responsavel_id')))""")}


def _nome(linha: Any) -> str:
    if not linha:
        return ""
    return (str(linha.get("full_name") or "").strip()
            or str(linha.get("username") or "").strip())


def _limpo(texto: Any) -> str | None:
    t = " ".join(str(texto or "").split())
    return t[:200] or None


# ------------------------------------------------------------ quem responde

def responsavel_das_rotinas(con) -> dict | None:
    """Quem responde pelas rotinas automáticas: {"id", "nome", "configurado"}.

    A configurada em `settings`, se for pessoa ativa (não robô); senão o
    primeiro ADMIN ativo que não é robô. None só num banco sem ADMIN.
    """
    bd = banco(con)
    if not bd.tem_tabela("users"):
        return None
    tem_robo = bd.tem_coluna("users", "eh_robo")
    pessoa = " AND COALESCE(eh_robo,0)=0" if tem_robo else ""
    valor = (bd.valor("SELECT value FROM settings WHERE key=%s", (CHAVE_RESPONSAVEL,))
             if bd.tem_tabela("settings") else None)
    if str(valor or "").strip().isdigit():
        r = bd.um(f"SELECT id, username, full_name FROM users "
                  f"WHERE id=%s AND active=1{pessoa}", (int(str(valor).strip()),))
        if r:
            return {"id": int(r["id"]), "nome": _nome(r), "configurado": True}
    r = bd.um(f"SELECT id, username, full_name FROM users "
              f"WHERE role='ADMIN' AND active=1{pessoa} ORDER BY id LIMIT 1")
    return {"id": int(r["id"]), "nome": _nome(r), "configurado": False} if r else None


def nome_da_pessoa(con, user_id: Any) -> str | None:
    """O nome de quem está em `users` com este id — para o agente que age em
    nome de alguém e guarda só o id dele. None se não houver."""
    if not str(user_id if user_id is not None else "").strip().isdigit():
        return None
    bd = banco(con)
    if not bd.tem_tabela("users"):
        return None
    r = bd.um("SELECT username, full_name FROM users WHERE id=%s", (int(user_id),))
    return _limpo(_nome(r)) if r else None


def pessoas_que_podem_responder(con) -> list[dict]:
    """As pessoas ativas (não robôs) — quem pode responder por um robô ou
    pelas rotinas. Só lê."""
    bd = banco(con)
    pessoa = " AND COALESCE(eh_robo,0)=0" if bd.tem_coluna("users", "eh_robo") else ""
    return bd.ler(f"SELECT id, username, full_name, role FROM users "
                  f"WHERE active=1{pessoa} ORDER BY full_name, id")


def definir_responsavel_do_robo(con, robo_id: int, responsavel_id: int | None) -> None:
    """Grava quem responde pelo robô. ESCREVE, na transação de quem chama.

    O responsável é pessoa ativa, não robô, e não o próprio robô. None limpa.
    Conta que não é robô não leva responsável (a pessoa responde por si).
    """
    bd = banco(con)
    robo = bd.um("SELECT id, COALESCE(eh_robo,0) AS eh_robo FROM users WHERE id=%s",
                 (int(robo_id),))
    if not robo:
        raise ValueError("Usuário não encontrado.")
    if responsavel_id is not None:
        if not int(robo["eh_robo"] or 0):
            raise ValueError("Só conta de robô tem responsável: a pessoa responde por si.")
        if int(responsavel_id) == int(robo_id):
            raise ValueError("O robô não responde por si mesmo — escolha uma pessoa.")
        resp = bd.um("SELECT id, active, COALESCE(eh_robo,0) AS eh_robo FROM users "
                     "WHERE id=%s", (int(responsavel_id),))
        if not resp or not int(resp["active"] or 0) or int(resp["eh_robo"] or 0):
            raise ValueError("O responsável pelo robô tem de ser uma pessoa com "
                             "cadastro ativo, e não outro robô.")
    bd.escrever("UPDATE users SET robo_responsavel_id=%s WHERE id=%s",
                (int(responsavel_id) if responsavel_id is not None else None, int(robo_id)))


def validar_responsavel_das_rotinas(con, user_id: int | None) -> None:
    """A configuração aceita vazio (vale o primeiro ADMIN) ou pessoa ativa."""
    if user_id is None:
        return
    bd = banco(con)
    r = bd.um("SELECT active, COALESCE(eh_robo,0) AS eh_robo FROM users WHERE id=%s",
              (int(user_id),))
    if not r or not int(r["active"] or 0) or int(r["eh_robo"] or 0):
        raise ValueError("O responsável pelas rotinas automáticas tem de ser uma "
                         "pessoa com cadastro ativo, e não um robô.")


# ------------------------------------------------------------ a identidade

def identidade(con, user_id: Any = None, *, agente: Any = None,
               a_mando_de: Any = None, _cols: set[str] | None = None) -> dict:
    """{"agente", "a_mando_de", "situacao"} de uma linha. Só lê.

    - conta de robô: `agente` = o nome do robô; `a_mando_de` = o declarado, ou
      o responsável cadastrado. Sem responsável cadastrado, a situação é
      ROBO_SEM_RESPONSAVEL, ainda que a linha declare um mandante;
    - conta de pessoa com `agente=` declarado (o agente que age em nome de
      alguém): `a_mando_de` = o declarado, ou a própria pessoa;
    - conta de pessoa sem agente: a pessoa age por si; nada a preencher;
    - sem conta: o que foi declarado; sem nada, SEM_IDENTIFICACAO.
    """
    bd = banco(con)
    if a_mando_de is PELO_RESPONSAVEL:
        resp = responsavel_das_rotinas(bd)
        a_mando_de = resp["nome"] if resp else None
    agente, a_mando_de = _limpo(agente), _limpo(a_mando_de)
    uid = int(user_id) if str(user_id if user_id is not None else "").strip().lstrip("-").isdigit() else None
    if uid is not None:
        cols = _cols if _cols is not None else _colunas(bd)
        robo_col = "COALESCE(u.eh_robo,0)" if "users.eh_robo" in cols else "0"
        if "users.robo_responsavel_id" in cols:
            conta = bd.um(
                f"""SELECT u.username, u.full_name, {robo_col} AS eh_robo,
                           r.username AS r_username, r.full_name AS r_full_name,
                           r.active AS r_active,
                           {"COALESCE(r.eh_robo,0)" if "users.eh_robo" in cols else "0"} AS r_robo
                      FROM users u LEFT JOIN users r ON r.id = u.robo_responsavel_id
                     WHERE u.id = %s""", (uid,))
        elif "users.eh_robo" in cols or bd.tem_tabela("users"):
            conta = bd.um(f"SELECT u.username, u.full_name, {robo_col} AS eh_robo "
                          f"FROM users u WHERE u.id = %s", (uid,))
        else:
            conta = None     # banco mínimo (teste de módulo) sem `users`
        if conta and int(conta.get("eh_robo") or 0):
            responsavel = None
            if (conta.get("r_username") or conta.get("r_full_name")) \
                    and int(conta.get("r_active") or 0) and not int(conta.get("r_robo") or 0):
                responsavel = _nome({"full_name": conta.get("r_full_name"),
                                     "username": conta.get("r_username")})
            return {"agente": _limpo(_nome(conta)) or agente,
                    "a_mando_de": a_mando_de or _limpo(responsavel),
                    "situacao": ROBO if responsavel else ROBO_SEM_RESPONSAVEL}
        if agente:
            return {"agente": agente, "a_mando_de": a_mando_de or _limpo(_nome(conta)),
                    "situacao": AGENTE}
        return {"agente": None, "a_mando_de": None, "situacao": PESSOA}
    if agente:
        return {"agente": agente, "a_mando_de": a_mando_de,
                "situacao": AGENTE if a_mando_de else AGENTE_SEM_MANDANTE}
    return {"agente": None, "a_mando_de": a_mando_de, "situacao": SEM_IDENTIFICACAO}


def registrar(con, *, ts: str, user_id: Any, username: Any, action: str,
              entity_type: Any = None, entity_id: Any = None, details: Any = None,
              ip_address: Any = None, agente: Any = None,
              a_mando_de: Any = None) -> dict:
    """A FUNÇÃO DA CASA para gravar em `audit_logs` dentro da transação de quem
    chama. ESCREVE. Devolve a identidade gravada.

    `db.log` (fora da transação) passa por aqui; os módulos que gravam junto
    com o ato também. O varredor `tests/test_identidade_do_robo.py` cobra que
    nenhum `INSERT INTO audit_logs` do repositório fique de fora.

    `details` vai como veio se já é texto (cada chamador tem a sua
    serialização, e o hash da corrente é do que se grava); dict/list vira JSON.
    """
    bd = banco(con)
    cols = _colunas(bd)
    ident = identidade(bd, user_id, agente=agente, a_mando_de=a_mando_de, _cols=cols)
    veredito = decidir(ident["situacao"])
    if veredito == RECUSAR:
        raise SemIdentificacao(
            f"Auditoria recusada ({action}): quem grava por programa tem de dizer "
            f"quem é (agente=) e a mando de quem age (a_mando_de=). "
            f"Situação: {ident['situacao']}.")
    if veredito == AVISAR:
        chave = (ident["situacao"], action, entity_type)
        if not CONTADOR[chave]:
            _LOG.warning("AUDITORIA EM FALTA DE IDENTIDADE (%s): acao=%s entidade=%s "
                         "— grava (etapa 1); a etapa 2 recusa.",
                         ident["situacao"], action, entity_type)
        CONTADOR[chave] += 1
    if isinstance(details, (dict, list, tuple)):
        details = json.dumps(details, ensure_ascii=False, default=str)
    if {"audit_logs.agente", "audit_logs.a_mando_de"} <= cols:
        bd.escrever(
            """INSERT INTO audit_logs (ts, user_id, username_snapshot, action, entity_type,
                   entity_id, details, ip_address, agente, a_mando_de)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (ts, user_id, username, action, entity_type, entity_id, details, ip_address,
             ident["agente"], ident["a_mando_de"]))
    else:
        # Banco anterior à migração (só o que sobe sem `Database`): grava como
        # sempre gravou. A conferência declara que não mediu.
        bd.escrever(
            """INSERT INTO audit_logs (ts, user_id, username_snapshot, action, entity_type,
                   entity_id, details, ip_address)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (ts, user_id, username, action, entity_type, entity_id, details, ip_address))
    return ident


def frase(agente: Any, a_mando_de: Any) -> str:
    """«praticado pelo agente X, a mando de Y» — a frase das telas. Vazia
    quando a linha não tem agente (a pessoa agiu por si)."""
    agente, a_mando_de = _limpo(agente), _limpo(a_mando_de)
    if not agente:
        return ""
    if not a_mando_de:
        return f"praticado pelo agente {agente}, sem dizer a mando de quem"
    return f"praticado pelo agente {agente}, a mando de {a_mando_de}"


def frase_da_entidade(con, entity_type: str, entity_id: Any,
                      acoes: tuple[str, ...] = ()) -> str:
    """A frase da linha de auditoria MAIS ANTIGA da entidade que tem agente —
    em geral a que a criou ou lavrou. Vazia sem agente ou sem as colunas."""
    bd = banco(con)
    if not str(entity_id or "").isdigit() or not {"audit_logs.agente"} <= _colunas(bd):
        return ""
    filtro, args = "", [entity_type, int(entity_id)]
    if acoes:
        filtro = " AND action IN (" + ",".join(["%s"] * len(acoes)) + ")"
        args.extend(acoes)
    r = bd.um(f"""SELECT agente, a_mando_de FROM audit_logs
                   WHERE entity_type = %s AND entity_id = %s AND agente IS NOT NULL{filtro}
                   ORDER BY id LIMIT 1""", tuple(args))
    return frase(r["agente"], r["a_mando_de"]) if r else ""


# ------------------------------------------------------------- a conferência

def conferencia(con, hoje: date | None = None, dias: int = DIAS_DO_AVISO) -> dict:
    """O que está em falta nos últimos `dias`. Só lê. NÃO olha o texto.

    {"medido", "desde", "sem_identificacao": [{"action","entity_type","n","ultima"}],
     "total_sem_identificacao", "agentes_sem_mandante": [{"agente","n"}],
     "robos_sem_responsavel": [{"id","nome","linhas"}], "modo"}
    """
    bd = banco(con)
    hoje = hoje or date.today()
    desde = (hoje - timedelta(days=dias)).isoformat()
    vazio = {"medido": False, "desde": desde, "sem_identificacao": [],
             "total_sem_identificacao": 0, "agentes_sem_mandante": [],
             "robos_sem_responsavel": [], "modo": MODO}
    if not bd.tem_tabela("audit_logs"):
        return vazio
    cols = _colunas(bd)
    if not {"audit_logs.agente", "audit_logs.a_mando_de"} <= cols:
        return vazio
    sem = bd.ler(
        """SELECT action, entity_type, count(*) AS n, max(ts) AS ultima
             FROM audit_logs
            WHERE ts >= %s AND user_id IS NULL AND agente IS NULL
            GROUP BY action, entity_type
            ORDER BY count(*) DESC, action""", (desde,))
    sem_mandante = bd.ler(
        """SELECT agente, count(*) AS n FROM audit_logs
            WHERE ts >= %s AND user_id IS NULL AND agente IS NOT NULL
              AND a_mando_de IS NULL
            GROUP BY agente ORDER BY count(*) DESC, agente""", (desde,))
    robos: list[dict] = []
    if {"users.eh_robo", "users.robo_responsavel_id"} <= cols:
        for r in bd.ler(
                """SELECT u.id, u.username, u.full_name,
                          (SELECT count(*) FROM audit_logs l
                            WHERE l.user_id = u.id AND l.ts >= %s) AS linhas
                     FROM users u
                     LEFT JOIN users r ON r.id = u.robo_responsavel_id
                    WHERE COALESCE(u.eh_robo,0) = 1 AND u.active = 1
                      AND (r.id IS NULL OR r.active <> 1 OR COALESCE(r.eh_robo,0) = 1)
                    ORDER BY u.id""", (desde,)):
            robos.append({"id": int(r["id"]), "nome": _nome(r), "linhas": int(r["linhas"] or 0)})
    return {"medido": True, "desde": desde,
            "sem_identificacao": [dict(x, n=int(x["n"])) for x in sem],
            "total_sem_identificacao": sum(int(x["n"]) for x in sem),
            "agentes_sem_mandante": [dict(x, n=int(x["n"])) for x in sem_mandante],
            "robos_sem_responsavel": robos, "modo": MODO}

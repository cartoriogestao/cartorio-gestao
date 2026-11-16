"""O pedido do WhatsApp que ninguém atendeu não fica esquecido.

Pedido do oficial em 14/11/2026: o atendimento tem de ser melhor que o humano. O
escrevente do WhatsApp diz ao cliente «ficou encaminhado ao Carlos» — e isso só é
verdade se o Carlos vê. Até 15/11/2026 nada olhava para o pedido depois de aberto:
a tarefa podia ficar dias na lista, e o cliente sem resposta.

O QUE ESTA ROTINA FAZ (rodada pelo vigia, a cada volta)
    O pedido aberto há mais que o prazo de resposta da casa (`wa_fila.prazo_minutos`),
    contado só no horário de atendimento (`wa_horario`), em que ninguém mexeu, é
    cobrado UMA vez: nota na tarefa, prioridade ALTA, e o pedido sobe na lista da
    tela. «Ninguém mexeu» quer dizer: a tarefa continua ABERTA e nenhuma pessoa
    escreveu ao cliente depois que o pedido nasceu.

O QUE ELA NÃO FAZ
    Não manda mensagem ao cliente: quem responde é a IA, quando ele escreve, com o
    tempo de espera que o estado do atendimento lhe mostra (`espera_em_palavras`).
    Não muda o dono da tarefa. Feriado ainda não está no horário do WhatsApp: no
    feriado o relógio corre como em dia útil.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from bd_nativo import banco

import wa_fila as FILA
import wa_pedido as PEDIDO

LOG = logging.getLogger("cartorio.wa_cobranca")

POR = "rotina do WhatsApp"
DIAS_NO_MAXIMO = 60          # pedido mais velho que isso já foi cobrado, ou é do acervo


def minutos_uteis(regra: dict | None, de: datetime, ate: datetime) -> int:
    """Os minutos entre `de` e `ate` dentro do horário de atendimento. Só calcula.

    Sem horário gravado, conta o relógio inteiro: sem saber quando a casa abre,
    não se finge que ela estava fechada."""
    if ate <= de:
        return 0
    if not regra:
        return int((ate - de).total_seconds() // 60)
    total = 0
    dia = de.date()
    fim = min(ate.date(), de.date() + timedelta(days=DIAS_NO_MAXIMO))
    while dia <= fim:
        meia_noite = datetime(dia.year, dia.month, dia.day)
        for inicio, termino in regra.get(dia.weekday(), []):
            a = max(de, meia_noite + timedelta(minutes=inicio))
            b = min(ate, meia_noite + timedelta(minutes=termino))
            if b > a:
                total += int((b - a).total_seconds() // 60)
        dia += timedelta(days=1)
    return total


def espera(pedido: dict, regra: dict | None, agora: str) -> int:
    """Minutos úteis desde que o pedido nasceu. Só calcula."""
    de = FILA._dt(PEDIDO.aberto_desde(pedido))
    ate = FILA._dt(agora)
    return minutos_uteis(regra, de, ate) if de and ate else 0


def espera_em_palavras(minutos: int) -> str:
    if minutos < 60:
        return f"{minutos} min" if minutos else "agora há pouco"
    horas = minutos // 60
    return f"{horas} h de expediente" if horas < 24 else f"{horas // 6} dia(s) de expediente"


def _tarefa(con: Any, pedido_id: int) -> dict | None:
    return banco(con).um(
        """SELECT id, status, priority FROM tasks WHERE source_ref=%s
            ORDER BY id DESC LIMIT 1""", (f"wa_pedido:{int(pedido_id)}",))


def _pessoa_respondeu(con: Any, pedido: dict) -> bool:
    """Alguém da casa escreveu ao cliente depois que o pedido nasceu? SÓ LÊ."""
    return bool(banco(con).um(
        """SELECT 1 AS ha FROM wa_mensagem
            WHERE conversa_id=%s AND direcao='out' AND COALESCE(autor, '') <> 'ia'
              AND COALESCE(tipo, '') <> 'aviso' AND criado_em >= %s LIMIT 1""",
        (int(pedido["conversa_id"]), PEDIDO.aberto_desde(pedido))))


def parados(con: Any, *, agora: str) -> list[dict]:
    """Os pedidos que passaram do prazo sem ninguém mexer, e ainda não cobrados. SÓ LÊ."""
    import wa_rotina as ROTINA
    regra = ROTINA.config(con).get("regra")
    prazo = FILA.prazo_minutos(con)
    corte = ((FILA._dt(agora) or datetime.now()) - timedelta(days=DIAS_NO_MAXIMO)
             ).strftime("%Y-%m-%dT%H:%M:%S")
    saida = []
    for p in banco(con).ler(
            """SELECT * FROM wa_pedido
                WHERE situacao=%s AND cobrado_em IS NULL
                  AND COALESCE(aberto_em, quando) >= %s ORDER BY id""",
            (PEDIDO.ABERTO, corte)):
        p = dict(p)
        minutos = espera(p, regra, agora)
        if minutos < prazo:
            continue
        tarefa = _tarefa(con, p["id"])
        if tarefa and str(tarefa.get("status") or "") != "ABERTA":
            continue                       # alguém já pegou
        if _pessoa_respondeu(con, p):
            continue
        saida.append({**p, "minutos": minutos, "tarefa": dict(tarefa) if tarefa else None})
    return saida


def cobrar(db: Any, *, agora: str) -> int:
    """Cobra, uma vez, cada pedido parado. ESCREVE. Devolve quantos."""
    with db.connect() as con:
        lista = parados(con, agora=agora)
    n = 0
    for p in lista:
        nota = (f"Pedido do WhatsApp sem atendimento há {espera_em_palavras(p['minutos'])}. "
                "O cliente ouviu que o caso foi encaminhado: responda na conversa ou "
                "mude a situação desta tarefa.")
        try:
            tarefa = p.get("tarefa")
            if tarefa:
                db.add_task_note(int(tarefa["id"]), None, nota, tipo="OBSERVACAO")
                if str(tarefa.get("priority") or "") not in ("ALTA", "CRITICA"):
                    db.update_task(int(tarefa["id"]), {"priority": "ALTA"}, None)
            with db.transaction() as con:
                banco(con).escrever("UPDATE wa_pedido SET cobrado_em=%s WHERE id=%s",
                                    (agora, int(p["id"])))
                FILA.registrar_evento(con, int(p["conversa_id"]), FILA.EV_PEDIDO,
                                      quando=agora, por=POR,
                                      nota=f"Pedido {int(p['id'])} cobrado: {nota}")
            n += 1
        except Exception:                           # noqa: BLE001
            LOG.exception("o pedido %s do WhatsApp não foi cobrado", p.get("id"))
    return n

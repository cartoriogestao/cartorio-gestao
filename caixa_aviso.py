"""O CAIXA QUE NÃO FECHA — o aviso grande, vermelho e insistente.

    «crie um aviso grande, vermelho e insistente para obrigar o encerramento
     de caixa após o expediente diário» — o oficial, 06/10/2026

O QUE SE MEDIU ANTES DE ESCREVER
    Desde 15/08/2026, **43 dos 51** caixas fechados foram fechados NO DIA
    SEGUINTE, quase todos às 8h; e o caixa de 14/09 de uma escrevente ficou
    aberto até 06/10 com os usos dos depósitos de setembro dentro. Caixa que
    atravessa a noite mistura o dinheiro de dois dias, e a conferência do
    oficial deixa de saber o que entrou em cada um.

OS DOIS DEGRAUS
    1. **Depois do fim do expediente, com o caixa DE HOJE aberto:** faixa
       vermelha no alto de toda tela e uma janela por cima do conteúdo, que se
       fecha com «Entendi» — e volta na tela seguinte. É o «insistente».
    2. **Caixa de UM DIA ANTERIOR ainda aberto:** a janela NÃO fecha. Só a tela
       do caixa fica livre, porque é nela que se fecha. É o «obrigar»: ninguém
       começa o dia novo sem fechar o de ontem.

    O ADMIN nunca é bloqueado (é quem desfaz), e vê a lista dos caixas de
    outros dias que continuam abertos, de qualquer operador.

O FIM DO EXPEDIENTE É CONFIGURAÇÃO, e não constante: o acervo não guarda o
horário da casa (procurado em 06/10/2026 — `tbSetupBoleto.strHorarioAtendimento`
existe e está vazio). **14h é o horário dito pelo oficial em 06/10/2026**:
«expediente termina 14h, funcionarios vao embora 14h15. avisas 14h pra fechar
o caixa». Eu havia posto 17h pelo movimento medido (lançamentos até 16h–17h) —
o movimento depois das 14h é trabalho interno, e o caixa fecha com o
expediente. Muda-se em `settings.caixa_fim_do_expediente`, sem versão nova —
e desde 29/10/2026 SÓ o oficial muda, com afirmação expressa
(`config_de_cobranca`): de 27 a 28/10 ela foi empurrada de 14h para 21h, por
script, a pedido de quem o aviso cobrava.

O TURNO DE QUEM NÃO É DO EXPEDIENTE (acréscimo do oficial, 29/10/2026)
    «[a escrevente] trabalha de noite e por vezes precisa operar o caixa».
    A hora global é a da equipe do dia; quem tem turno próprio tem
    `settings.caixa_turno:<login>` = «18:00-23:30» (começo e fim), e para ele:
      - o degrau 1 começa no FIM DO TURNO DELE, e não às 14h;
      - o degrau 2 continua valendo: o caixa aberto num DIA DE TRABALHO
        anterior bloqueia. Para o turno, o dia de trabalho não vira à
        meia-noite (o turno da noite pode atravessá-la): vira no MEIO DA
        FOLGA, entre o fim de um turno e o começo do seguinte. Na prática,
        «dia anterior» é o caixa aberto antes do começo do turno atual — com
        meia folga de tolerância, para quem abre o caixa um pouco antes da
        hora não ser trancado quando o turno começa.
    O turno é chave de cobrança como as outras: só o oficial o define, robô
    nunca, e o operador nunca define o próprio.

O MÓDULO SÓ LÊ. Não fecha caixa nenhum — fechar exige contar o dinheiro, e
isso é de quem está com a gaveta.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from bd_nativo import banco

CHAVE_FIM = "caixa_fim_do_expediente"
FIM_PADRAO = "14:00"

#: O turno por operador: `caixa_turno:<login em minúsculas>` = «HH:MM-HH:MM».
PREFIXO_DO_TURNO = "caixa_turno:"

MINUTOS_DO_DIA = 24 * 60

#: Os caixas da carga do E-Ofício (operador «BEATRIZ», datas de 2020 a 2022)
#: entraram como linha de acervo; o aviso é do caixa que este sistema abriu.
INICIO_DO_SISTEMA = "2026-08-01"


def fim_do_expediente(texto: str | None) -> tuple[int, int]:
    """«14:00» → (14, 0). O que não for hora válida volta ao padrão."""
    m = re.fullmatch(r"\s*(\d{1,2})[:h](\d{2})?\s*", texto or "")
    if m and 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2) or 0) <= 59:
        return int(m.group(1)), int(m.group(2) or 0)
    h, mi = FIM_PADRAO.split(":")
    return int(h), int(mi)


# ------------------------------------------------------------- o turno

def chave_do_turno(login: Any) -> str:
    """A chave de `settings` do turno deste login. Só calcula."""
    return PREFIXO_DO_TURNO + str(login or "").strip().casefold()


def turno(texto: Any) -> tuple[int, int] | None:
    """«18:00-23:30» → (1080, 1410), em minutos desde a meia-noite.

    Vazio, torto, ou começo igual ao fim → None: vale o fim do expediente.
    Não há padrão aqui, ao contrário da hora global — turno inventado
    calaria o aviso de quem não tem turno nenhum."""
    if isinstance(texto, tuple):
        return texto if len(texto) == 2 else None
    # O texto vem da tela: corta-se e apara-se ANTES, e a expressão não tem
    # repetição aberta nas pontas (CodeQL, expressão polinomial em dado de fora).
    m = re.fullmatch(r"(\d{1,2}):(\d{2}) {0,3}- {0,3}(\d{1,2}):(\d{2})",
                     str(texto or "").strip()[:40])
    if not m:
        return None
    h1, m1, h2, m2 = (int(x) for x in m.groups())
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
        return None
    ini, fim = h1 * 60 + m1, h2 * 60 + m2
    return None if ini == fim else (ini, fim)


def turno_de(con, login: Any) -> tuple[int, int] | None:
    """O turno gravado para este login, ou None. Só LÊ."""
    if not str(login or "").strip():
        return None
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return None
    return turno(bd.valor("SELECT value FROM settings WHERE key = %s",
                          (chave_do_turno(login),)))


def _hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _virada(ini: int, fim: int) -> int:
    """Onde o dia de trabalho vira: no meio da folga entre o fim e o começo."""
    folga = (ini - fim) % MINUTOS_DO_DIA
    return (fim + folga // 2) % MINUTOS_DO_DIA


def _dia_de_trabalho(instante: datetime, virada: int) -> date:
    return (instante - timedelta(minutes=virada)).date()


def _fim_do_turno(dia: date, ini: int, fim: int, virada: int) -> datetime:
    """Quando acaba o turno do dia de trabalho `dia`: ele começa no primeiro
    `ini` depois da virada, e dura de `ini` até `fim` (que pode ser amanhã)."""
    base = datetime.combine(dia, time()) + timedelta(minutes=virada)
    inicio = datetime.combine(base.date(), time()) + timedelta(minutes=ini)
    if inicio < base:
        inicio += timedelta(days=1)
    return inicio + timedelta(minutes=(fim - ini) % MINUTOS_DO_DIA)


def _aberto_em(caixa: Any) -> datetime:
    """Quando o caixa foi aberto; sem a hora, o meio do dia da data dele."""
    try:
        return datetime.fromisoformat(str(caixa["aberto_em"] or "")[:19])
    except (KeyError, TypeError, ValueError):
        return datetime.fromisoformat(str(caixa["data"])[:10] + "T12:00:00")


def passou_do_fim(caixa: Any, agora: datetime, fim: str | None = None,
                  turno_do_operador: Any = None) -> tuple[bool, str]:
    """O fim (do expediente ou do turno) deste caixa já passou? Só calcula.

    Sem turno, é a hora global de hoje — o caixa de hoje. Com turno, é o fim
    do turno do dia de trabalho em que o caixa foi aberto."""
    t = turno(turno_do_operador)
    if t is None:
        hora, minuto = fim_do_expediente(fim)
        return (agora.hour, agora.minute) >= (hora, minuto), f"{hora:02d}:{minuto:02d}"
    ini, fim_t = t
    virada = _virada(ini, fim_t)
    dia = _dia_de_trabalho(_aberto_em(caixa), virada)
    return agora >= _fim_do_turno(dia, ini, fim_t, virada), _hhmm(fim_t)


# ------------------------------------------------------------- o aviso

def situacao(con, operador_nome: str, agora: datetime,
             fim: str | None = None, *, e_admin: bool = False,
             turno_do_operador: Any = None) -> dict | None:
    """O que o aviso diz a esta pessoa agora, ou None quando não há o que dizer.

    `turno_do_operador` é o texto gravado («18:00-23:30») ou o par em minutos;
    vazio, vale o fim do expediente (`fim`)."""
    hoje = agora.date().isoformat()
    bd = banco(con)
    meus = bd.ler(
        """SELECT id, data, aberto_em FROM cx_caixas
            WHERE operador_nome = %s AND situacao = 'ABERTO' AND data >= %s
            ORDER BY data, id""", (operador_nome or "", INICIO_DO_SISTEMA))
    t = turno(turno_do_operador)
    if t is None:
        de_outros_dias = [m for m in meus if m["data"] < hoje]
        do_dia = [m for m in meus if m["data"] == hoje]
        hora, minuto = fim_do_expediente(fim)
        passou = (agora.hour, agora.minute) >= (hora, minuto)
        fim_texto = f"{hora:02d}:{minuto:02d}"
    else:
        ini, fim_t = t
        virada = _virada(ini, fim_t)
        trabalho = _dia_de_trabalho(agora, virada)
        de_outros_dias = [m for m in meus
                          if _dia_de_trabalho(_aberto_em(m), virada) < trabalho]
        do_dia = [m for m in meus
                  if _dia_de_trabalho(_aberto_em(m), virada) == trabalho]
        passou = agora >= _fim_do_turno(trabalho, ini, fim_t, virada)
        fim_texto = _hhmm(fim_t)
    outros = []
    if e_admin:
        outros = [{"operador": r["operador_nome"], "data": r["data"]} for r in bd.ler(
            """SELECT operador_nome, data FROM cx_caixas
                WHERE situacao = 'ABERTO' AND data >= %s AND data < %s
                  AND operador_nome <> %s ORDER BY data, id""",
            (INICIO_DO_SISTEMA, hoje, operador_nome or ""))]
    if de_outros_dias:
        nivel = "BLOQUEIO" if not e_admin else "VENCIDO"
        dias = [m["data"] for m in de_outros_dias]
    elif passou and do_dia:
        nivel, dias = "FIM_DO_EXPEDIENTE", sorted({m["data"] for m in do_dia})
    elif outros:
        nivel, dias = "OUTROS", []
    else:
        return None
    return {"nivel": nivel, "dias": dias, "fim": fim_texto, "outros": outros,
            "turno": (f"{_hhmm(t[0])}-{_hhmm(t[1])}" if t else None)}

"""«Conferir o Constrijud» sai da mão e entra na cadeia automática (A008).

Pedido do titular (26/11/2026): o item ROT-RI-04 da Rotina da serventia —
«na abertura, a cada 2 horas e no fim» entrar no Constrijud, ver ordem nova
de constrição e passar ao escrevente do RI para prenotar — entra na mesma
lógica da A006: a automação verifica e só avisa quando a rotina para.

As ordens do Constrijud chegam pelo e-Protocolo do ONR (o ONR, 25/05/2026), que
`onr_eprotocolo` já lê. Os testes provam:

  * o processo não sai à rede: lê o que a leitura do e-Protocolo gravou;
  * a leitura do e-Protocolo desligada, ou sem leitura boa nas últimas 2 horas
    (CNN 320-AB), é ERRO — rotina parada;
  * ordem de constrição esperando prenotação é AVISO (tarefa do RI), e diz
    quantas são novas desde a última conferência;
  * a ordem prenotada, ou o título que não é constrição, não conta;
  * a agenda cobre abertura, encerramento e no máximo 2 horas entre uma e outra;
  * a faixa das cadeias acende quando o processo dá ERRO ou não roda, e a
    ordem a prenotar não acende (é trabalho, e não rotina parada).

Datas fixas: quinta 26/11/2026, 10:30, é «agora». Dados inventados.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automacao as AU                     # noqa: E402
import automacao_processos as PROC         # noqa: E402
import automacao_schema as SCH             # noqa: E402
import cadeias_automaticas as CA           # noqa: E402
import onr_eprotocolo as EP                # noqa: E402
import onr_wsoficio as WS                  # noqa: E402
from bd_nativo import banco                # noqa: E402

AGORA = datetime(2026, 11, 26, 10, 30)     # quinta-feira
HOJE = AGORA.date()
AMB = WS.PRODUCAO


def _escrever(db, sql, args=()):
    with db.transaction() as con:
        return banco(con).escrever(sql, args)


def _leitura(db, terminada_em: str, situacao: str = "OK"):
    _escrever(db, """INSERT INTO onr_ep_leituras (ambiente, origem, iniciada_em, terminada_em,
                         situacao, listados) VALUES (%s, 'ROBO', %s, %s, %s, 3)""",
              (AMB, terminada_em, terminada_em, situacao))


def _titulo(db, id_contrato: int, *, constricao: str = "", situacao: str = "A_PRENOTAR",
            remessa: str = "2026-11-26", ficha_lida: int = 1):
    _escrever(db, """INSERT INTO onr_ep_pedidos (ambiente, id_contrato, protocolo, id_status,
                         data_remessa, constricao_tipo, constricao_processo, situacao,
                         ficha_lida, xml_lista, recebido_em, atualizado_em)
                     VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, '<x/>', %s, %s)""",
              (AMB, id_contrato, f"EP-TESTE-{id_contrato}", remessa, constricao,
               "0000000-00.2026.8.00.0000" if constricao else "", situacao, ficha_lida,
               f"{HOJE}T08:00:00", f"{HOJE}T08:00:00"))


def _ligar(db, codigo: str, ligado: int = 1):
    _escrever(db, "UPDATE au_processos SET ativo=%s WHERE codigo=%s", (ligado, codigo))


def _ctx(db, estado: dict | None = None, agora: datetime = AGORA) -> PROC.Contexto:
    with db.connect() as con:
        p = dict(AU.por_codigo(con, "RI_CONSTRIJUD"))
    p["estado"] = estado or {}
    return PROC.Contexto(db=db, agora=agora, pasta_dados=Path("."), raiz=RAIZ, processo=p)


@pytest.fixture
def casa(cg_casa):
    """Uma casa com a leitura do e-Protocolo ligada e lida às 10:15 de hoje."""
    db = cg_casa["db"]
    cg_casa["app"].extensions["backup_checked"] = True
    cg_casa["app"].extensions["cnib_verificado"] = True
    with db.transaction() as con:
        AU.semear(con, AGORA - timedelta(days=30))
        EP.init_schema(con)
    _ligar(db, EP.CODIGO_DO_PROCESSO)
    _leitura(db, f"{HOJE}T10:15:30")
    return cg_casa


# ------------------------------------------------------------ o processo


def test_o_processo_nasce_desligado_e_com_a_agenda_da_norma(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        AU.semear(con, AGORA)
    with db.connect() as con:
        p = AU.por_codigo(con, "RI_CONSTRIJUD")
    assert p is not None and not p["ativo"]
    assert p["setor"] == "RI"
    agenda = AU.normalizar_agenda(p["agenda"])
    assert agenda["dias"] == [0, 1, 2, 3, 4]
    horas = [datetime.strptime(h, "%H:%M") for h in agenda["horarios"]]
    # CNN 320-AB: abertura e encerramento (a leitura do e-Protocolo vai das 8h
    # às 18h), e nunca mais de 2 horas entre uma conferência e a seguinte.
    assert horas[0].strftime("%H:%M") >= "08:00" and horas[0].hour == 8
    assert horas[-1].strftime("%H:%M") >= "18:00"
    assert all(b - a <= timedelta(hours=2) for a, b in zip(horas, horas[1:]))
    # O despachante acha a função pelo alvo: sem isso, o processo nasce quebrado.
    assert PROC.CATALOGO[p["alvo"]] is PROC.verificar_constrijud


def test_sem_ordem_de_constricao_e_ok(casa):
    _titulo(casa["db"], 101)                                   # título comum: não é constrição
    r = PROC.verificar_constrijud(_ctx(casa["db"]))
    assert r["situacao"] == SCH.OK
    assert "nenhuma ordem de constrição" in r["relato"]
    assert r["estado"]["vistas"] == []


def test_ordem_a_prenotar_e_aviso_e_conta_as_novas(casa):
    db = casa["db"]
    _titulo(db, 201, constricao="PENHORA", remessa="2026-11-25")
    _titulo(db, 202, constricao="ARRESTO")
    r = PROC.verificar_constrijud(_ctx(db))
    assert r["situacao"] == SCH.AVISO
    assert "2 ordem(ns) de constrição esperando prenotação (2 nova(s)" in r["relato"]
    assert "25/11/2026" in r["relato"]                         # a primeira na ordem da remessa
    assert "CNN 320-AC" in r["relato"]
    assert [a["id_contrato"] for a in r["achados"]] == [201, 202]
    assert r["estado"]["vistas"] == [201, 202]

    # A rodada seguinte, com as mesmas duas e uma nova: segue AVISO (a tarefa
    # fica aberta até prenotar), e só a nova conta como nova.
    _titulo(db, 203, constricao="PENHORA")
    r = PROC.verificar_constrijud(_ctx(db, r["estado"]))
    assert r["situacao"] == SCH.AVISO
    assert "3 ordem(ns)" in r["relato"] and "(1 nova(s)" in r["relato"]
    assert [a["nova"] for a in r["achados"]] == [False, False, True]


def test_a_ordem_prenotada_nao_conta(casa):
    db = casa["db"]
    _titulo(db, 301, constricao="PENHORA", situacao="EM_ANDAMENTO")
    _titulo(db, 302, constricao="PENHORA", situacao="FECHADO_NO_ONR")
    r = PROC.verificar_constrijud(_ctx(db, {"vistas": [301]}))
    assert r["situacao"] == SCH.OK
    assert "1 já prenotada(s)" in r["relato"]


def test_titulo_sem_ficha_lida_e_lembrado(casa):
    _titulo(casa["db"], 401, ficha_lida=0)
    r = PROC.verificar_constrijud(_ctx(casa["db"]))
    assert r["situacao"] == SCH.OK
    assert "1 título(s) do e-Protocolo ainda sem a ficha lida" in r["relato"]


def test_a_leitura_do_eprotocolo_desligada_e_rotina_parada(casa):
    _ligar(casa["db"], EP.CODIGO_DO_PROCESSO, 0)
    _titulo(casa["db"], 501, constricao="PENHORA")
    r = PROC.verificar_constrijud(_ctx(casa["db"]))
    assert r["situacao"] == SCH.ERRO
    assert "desligada" in r["relato"]
    assert "estado" not in r                                   # não apaga o que já se viu


def test_sem_leitura_boa_nas_ultimas_duas_horas_e_rotina_parada(casa):
    db = casa["db"]
    # A leitura das 10:15 conta às 10:30, e às 12:30 já passou das 2 horas.
    assert PROC.verificar_constrijud(_ctx(db))["situacao"] == SCH.OK
    r = PROC.verificar_constrijud(_ctx(db, agora=AGORA + timedelta(hours=2, minutes=1)))
    assert r["situacao"] == SCH.ERRO
    assert "26/11 às 10:15" in r["relato"] and "CNN 320-AB" in r["relato"]


def test_a_leitura_com_erro_nao_vale_como_conferencia(casa, cg_casa):
    db = casa["db"]
    _escrever(db, "DELETE FROM onr_ep_leituras")
    _leitura(db, f"{HOJE}T10:15:30", "ERRO")
    r = PROC.verificar_constrijud(_ctx(db))
    assert r["situacao"] == SCH.ERRO
    assert "nenhuma leitura boa até hoje" in r["relato"]


def test_o_relato_nao_leva_nome_de_parte(casa):
    db = casa["db"]
    _titulo(db, 601, constricao="PENHORA")
    _escrever(db, "UPDATE onr_ep_pedidos SET apresentante_nome='PESSOA TESTE DA SILVA'")
    r = PROC.verificar_constrijud(_ctx(db))
    assert "PESSOA TESTE" not in r["relato"]
    assert "PESSOA TESTE" not in json.dumps(r["achados"])


# ------------------------------------------------------------ a faixa


def _rodada(db, codigo, iniciada_em, situacao="OK", relato="Rodada de teste."):
    with db.connect() as con:
        p = AU.por_codigo(con, codigo)
    _escrever(db, """INSERT INTO au_execucoes (processo_id, iniciada_em, terminada_em, situacao,
                         relato) VALUES (%s, %s, %s, %s, %s)""",
              (p["id"], iniciada_em, iniciada_em, situacao, relato))


def _elos_do_constrijud(db, agora=AGORA):
    return {e["elo"] for e in CA.aviso(db.connect, agora)["elos"] if e["cadeia"] == CA.CONSTRIJUD}


@pytest.fixture
def cadeia(casa):
    """Os da cadeia rodando: e-Protocolo às 10:15, Constrijud às 10:30 (e o WSOfício às
    08:30, que já não é da cadeia)."""
    db = casa["db"]
    _ligar(db, "RI_CONSTRIJUD")
    _ligar(db, "RI_WSOFICIO")
    _rodada(db, EP.CODIGO_DO_PROCESSO, f"{HOJE}T10:15:00")
    _rodada(db, "RI_CONSTRIJUD", f"{HOJE}T10:30:00")
    _rodada(db, "RI_WSOFICIO", f"{HOJE}T08:30:00")
    return casa


def test_a_cadeia_funcionando_nao_acende(cadeia):
    assert _elos_do_constrijud(cadeia["db"]) == set()


def test_a_instalacao_que_nao_usa_o_constrijud_nao_tem_faixa(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        AU.semear(con, AGORA - timedelta(days=30))
    assert _elos_do_constrijud(db) == set()


def test_ordem_a_prenotar_e_trabalho_e_nao_acende(cadeia):
    _rodada(cadeia["db"], "RI_CONSTRIJUD", f"{HOJE}T10:31:00", "AVISO",
            "Constrijud: 1 ordem(ns) de constrição esperando prenotação.")
    assert _elos_do_constrijud(cadeia["db"]) == set()


def test_o_constrijud_com_erro_acende(cadeia):
    _rodada(cadeia["db"], "RI_CONSTRIJUD", f"{HOJE}T10:31:00", "ERRO",
            "Constrijud: o e-Protocolo do ONR não foi lido nas últimas 2 hora(s).")
    elos = CA.aviso(cadeia["db"].connect, AGORA)["elos"]
    meus = [e for e in elos if e["cadeia"] == CA.CONSTRIJUD]
    assert [e["elo"] for e in meus] == ["PROCESSO_COM_ERRO"]
    assert meus[0]["rotulo_da_cadeia"] == "Constrijud (ordens de constrição)"
    assert "e-Protocolo" in meus[0]["detalhe"]


def test_o_constrijud_que_nao_rodou_acende(cadeia):
    db = cadeia["db"]
    _escrever(db, "DELETE FROM au_execucoes WHERE processo_id=(SELECT id FROM au_processos "
                  "WHERE codigo='RI_CONSTRIJUD')")
    _rodada(db, "RI_CONSTRIJUD", f"{HOJE}T08:30:00")
    # Às 14:31 o horário das 12:30 passou havia mais de 2 horas e não rodou.
    assert _elos_do_constrijud(db, datetime(2026, 11, 26, 14, 31)) >= {"PROCESSO_NAO_RODOU"}


def test_a_penhora_online_saiu_da_cadeia(cadeia):
    """Desde 25/08/2026 a Penhora Online não recebe pedido novo, e a casa não
    tem pedido de penhora aberto nela (consulta de 27/11/2026). O WSOfício
    segue pelos ofícios; o erro dele não acende a faixa do Constrijud."""
    assert "RI_WSOFICIO" not in {c for c, _, _ in CA.PROCESSOS[CA.CONSTRIJUD]}
    _rodada(cadeia["db"], "RI_WSOFICIO", f"{HOJE}T08:31:00", "ERRO", "Não deu para medir.")
    assert _elos_do_constrijud(cadeia["db"]) == set()


def test_a_leitura_do_eprotocolo_desligada_depois_de_rodar_acende(cadeia):
    _ligar(cadeia["db"], EP.CODIGO_DO_PROCESSO, 0)
    assert "PROCESSO_DESLIGADO" in _elos_do_constrijud(cadeia["db"])


def test_a_leitura_de_15_minutos_que_para_no_meio_do_dia_acende(cadeia):
    """A régua «não rodou» mede o horário vencido há mais de 2 horas, e não o
    último da agenda — que, de 15 em 15 minutos, tem sempre menos de duas."""
    db = cadeia["db"]
    _escrever(db, "DELETE FROM au_execucoes WHERE processo_id=(SELECT id FROM au_processos "
                  "WHERE codigo=%s)", (EP.CODIGO_DO_PROCESSO,))
    _rodada(db, EP.CODIGO_DO_PROCESSO, f"{HOJE}T08:00:00")
    assert "PROCESSO_NAO_RODOU" in _elos_do_constrijud(db)            # 10:30
    assert _elos_do_constrijud(db, datetime(2026, 11, 26, 10, 0)) == set()

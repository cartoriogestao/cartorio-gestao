# -*- coding: utf-8 -*-
"""O cronômetro esquecido — aviso às 14h15, fecha às 14h30 com hora de 14h15.

    «crie alertas para cronômetros esquecidos aos usuários (...) avisa
     fechamento 14h15, mas encerra 14h30, com horário retroativo a 14h15,
     se não tivermos confirmação do usuário»      — o oficial, 11/10/2026

Medido antes: de 06 a 09/10/2026 três cronômetros fechados às 23:59 somaram
1.705 minutos que ninguém trabalhou.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import produtividade as PR
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

UID = 7
DIA = datetime(2026, 10, 9)


def _con() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    PR.init_produtividade_schema(con)
    return con


def _as(h: int, m: int, dia: datetime = DIA) -> datetime:
    return dia.replace(hour=h, minute=m)


def _inicia(con, quando, tarefa="REGISTRO DE ÓBITO"):
    return PR.iniciar_cronometro(con, responsavel_user_id=UID, responsavel_nome="Beatriz",
                                 categoria=PR.CATEGORIA_PADRAO, tarefa=tarefa, agora=quando)


def _reg(con, rid):
    return dict(con.execute("SELECT * FROM prod_registros WHERE id=?", (rid,)).fetchone())


def test_antes_das_14h15_nada_acontece():
    con = _con()
    rid = _inicia(con, _as(13, 26))
    s = PR.situacao_do_cronometro(con, _reg(con, rid), _as(14, 10))
    assert s["situacao"] == "NORMAL"
    assert PR.encerrar_esquecidos(con, agora=_as(14, 10)) == []


def test_entre_14h15_e_14h30_avisa_e_nao_fecha():
    con = _con()
    rid = _inicia(con, _as(13, 26))
    s = PR.situacao_do_cronometro(con, _reg(con, rid), _as(14, 20))
    assert s["situacao"] == "AVISO"
    assert s["encerra_as"] == "14:30" and s["retroativo"] == "14:15"
    assert PR.encerrar_esquecidos(con, agora=_as(14, 20)) == []


def test_sem_confirmacao_fecha_as_14h30_com_hora_14h15():
    con = _con()
    rid = _inicia(con, _as(13, 26))
    fechados = PR.encerrar_esquecidos(con, agora=_as(14, 30))
    assert [f["id"] for f in fechados] == [rid]
    r = _reg(con, rid)
    assert r["status"] == PR.STATUS_CONCLUIDA and r["hora_fim"] == "14:15"
    assert PR.MARCA_ENCERRAMENTO_AUTOMATICO in r["observacoes"]
    assert "não foi confirmado" in r["observacoes"]


def test_esquecido_de_sexta_lido_na_segunda_fecha_as_14h15_de_sexta():
    con = _con()
    rid = _inicia(con, _as(13, 38))
    segunda = _as(8, 5, DIA + timedelta(days=3))
    PR.encerrar_esquecidos(con, responsavel_user_id=UID, agora=segunda)
    r = _reg(con, rid)
    assert r["hora_fim"] == "14:15"
    assert PR.calcular_metricas_tempo(hora_inicio=r["hora_inicio"], hora_fim=r["hora_fim"],
                                      pausas_min=r["pausas_min"],
                                      tempo_planejado_min=None)["tempo_liquido_min"] == 37


def test_quem_confirma_segue_aberto_depois_das_14h30():
    con = _con()
    _inicia(con, _as(13, 26))
    PR.confirmar_cronometro(con, responsavel_user_id=UID, agora=_as(14, 20))
    assert PR.encerrar_esquecidos(con, agora=_as(15, 0)) == []
    final = PR.parar_cronometro(con, responsavel_user_id=UID, agora=_as(15, 10))
    assert final["hora_fim"] == "15:10"


def test_confirmar_depois_das_14h30_nao_ressuscita_o_cronometro():
    con = _con()
    rid = _inicia(con, _as(13, 26))
    try:
        PR.confirmar_cronometro(con, responsavel_user_id=UID, agora=_as(14, 35))
        assert False, "devia recusar"
    except LookupError as e:
        assert "14h15" in str(e)
    assert _reg(con, rid)["hora_fim"] == "14:15"


def test_parar_depois_das_14h30_sem_confirmar_grava_14h15_e_diz_por_que():
    con = _con()
    _inicia(con, _as(13, 26))
    final = PR.parar_cronometro(con, responsavel_user_id=UID, agora=_as(14, 50))
    assert final["hora_fim"] == "14:15"
    assert "não foi confirmado" in final["encerrado_automaticamente"]


def test_iniciado_depois_das_14h15_conta_como_confirmado():
    """Quem liga o cronômetro às 15h diz, com o clique, que trabalha depois do
    expediente — fechá-lo às 14h15 daria fim antes do início."""
    con = _con()
    rid = _inicia(con, _as(15, 12))
    assert PR.situacao_do_cronometro(con, _reg(con, rid), _as(17, 0))["situacao"] == "NORMAL"
    assert PR.encerrar_esquecidos(con, agora=_as(17, 0)) == []


def test_confirmado_que_atravessa_a_noite_fecha_na_ultima_acao_do_dia():
    con = _con()
    con.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, ts TEXT, user_id INTEGER, action TEXT)")
    con.execute("INSERT INTO audit_logs(ts, user_id, action) VALUES (?,?,?)",
                ("2026-10-09T19:58:10", UID, "RI_ATO_LAVRADO"))
    con.execute("INSERT INTO audit_logs(ts, user_id, action) VALUES (?,?,?)",
                ("2026-10-09T21:00:00", UID + 1, "OUTRA_PESSOA"))
    rid = _inicia(con, _as(15, 12))
    PR.encerrar_esquecidos(con, agora=_as(9, 0, DIA + timedelta(days=1)))
    r = _reg(con, rid)
    assert r["hora_fim"] == "19:58"
    assert "última ação no sistema" in r["observacoes"]


def test_confirmado_sem_acao_depois_fecha_com_duracao_zero_e_pede_conferencia():
    con = _con()
    rid = _inicia(con, _as(15, 12))
    PR.encerrar_esquecidos(con, agora=_as(9, 0, DIA + timedelta(days=1)))
    r = _reg(con, rid)
    assert r["hora_fim"] == "15:12" and "confira" in r["observacoes"]


def test_pausa_corrente_conta_so_ate_a_hora_retroativa():
    con = _con()
    _inicia(con, _as(13, 0))
    PR.pausar_cronometro(con, responsavel_user_id=UID, agora=_as(13, 45))
    fechados = PR.encerrar_esquecidos(con, agora=_as(14, 30))
    r = _reg(con, fechados[0]["id"])
    assert r["hora_fim"] == "14:15" and r["pausas_min"] == 30


def test_horarios_vem_da_configuracao_quando_houver():
    con = _con()
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO settings VALUES ('produtividade_aviso_expediente', '13:45')")
    con.execute("INSERT INTO settings VALUES ('produtividade_encerramento_automatico', '14:00')")
    con.execute("INSERT INTO settings VALUES ('produtividade_hora_retroativa', '13:45')")
    rid = _inicia(con, _as(13, 0))
    PR.encerrar_esquecidos(con, agora=_as(14, 0))
    assert _reg(con, rid)["hora_fim"] == "13:45"


def test_aviso_fica_ate_a_pessoa_dar_ciencia():
    con = _con()
    _inicia(con, _as(13, 26))
    PR.encerrar_esquecidos(con, agora=_as(14, 31))
    assert len(PR.encerrados_sem_ciencia(con, responsavel_user_id=UID)) == 1
    assert PR.dar_ciencia(con, responsavel_user_id=UID) == 1
    assert PR.encerrados_sem_ciencia(con, responsavel_user_id=UID) == []


def test_status_e_get_e_nao_grava():
    """«GET não abre transação de escrita»: o status só diz ENCERRAR; quem
    fecha é o POST que a tela chama."""
    con = _con()
    rid = _inicia(con, _as(13, 26))
    ativo = PR.cronometro_em_andamento(con, responsavel_user_id=UID)
    assert ativo["expediente"]["situacao"] in ("ENCERRAR", "AVISO", "NORMAL")
    assert not (_reg(con, rid)["hora_fim"] or "")


def test_a_tela_tem_o_aviso_e_as_tres_rotas():
    raiz = Path(__file__).resolve().parent.parent
    html = (raiz / "templates" / "_produtividade_rapida.html").read_text(encoding="utf-8")
    for marca in ("data-prod-alerta", "produtividade_api_crono_confirmar",
                  "produtividade_api_crono_encerrar_esquecidos", "produtividade_api_crono_ciencia",
                  'name="csrf_token"'):
        assert marca in html
    js = (raiz / "static" / "produtividade_rapida.js").read_text(encoding="utf-8")
    assert "tratarExpediente" in js and "setInterval(lerStatus, 60000)" in js


def test_rotas_web_confirmar_e_encerrar(cg_casa_logada):
    c = cg_casa_logada["c"]
    st = c.get("/administrativo/produtividade/api/cronometro/status").get_json()
    assert st["ok"] and "encerrados_sem_ciencia" in st
    html = c.get("/administrativo/produtividade").get_data(as_text=True)
    import re
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/administrativo/produtividade/api/cronometro/encerrar-esquecidos",
               data={"csrf_token": tok}, headers={"X-CSRF-Token": tok}).get_json()
    assert r["ok"] and r["fechados"] == []
    r = c.post("/administrativo/produtividade/api/cronometro/confirmar",
               data={"csrf_token": tok}, headers={"X-CSRF-Token": tok}).get_json()
    assert r["ok"] is False  # nenhum cronômetro aberto
    r = c.post("/administrativo/produtividade/api/cronometro/ciencia",
               data={"csrf_token": tok}, headers={"X-CSRF-Token": tok}).get_json()
    assert r["ok"] and r["ciencia"] == 0

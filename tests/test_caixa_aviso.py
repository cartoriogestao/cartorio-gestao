"""O aviso do caixa que não fecha — pedido do oficial em 06/10/2026.

Depois do expediente, o caixa de hoje aberto chama; caixa de dia anterior
aberto tranca as outras telas até ser fechado. O ADMIN não é trancado.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import caixa_aviso as CA                                         # noqa: E402
from conftest import cg_login                                    # noqa: E402

NOME = "ELISA EXEMPLO LIMA"


def _caixa(con, data, nome=NOME, situacao="ABERTO"):
    con.execute("""INSERT INTO cx_caixas (data, operador_nome, saldo_inicial, aberto_em, situacao)
                   VALUES (?, ?, '0,00', ?, ?)""", (data, nome, data + "T08:00:00", situacao))
    con.commit()


def _con(cg_casa):
    return sqlite3.connect(cg_casa["banco"])


def test_antes_do_fim_do_expediente_nao_ha_aviso(cg_casa):
    con = _con(cg_casa)
    _caixa(con, "2026-10-06")
    assert CA.situacao(con, NOME, datetime(2026, 10, 6, 16, 59), "17:00") is None
    a = CA.situacao(con, NOME, datetime(2026, 10, 6, 17, 0), "17:00")
    assert a["nivel"] == "FIM_DO_EXPEDIENTE" and a["fim"] == "17:00"


def test_caixa_de_ontem_aberto_tranca_quem_nao_e_admin(cg_casa):
    con = _con(cg_casa)
    _caixa(con, "2026-10-05")
    a = CA.situacao(con, NOME, datetime(2026, 10, 6, 8, 5), "17:00")
    assert a["nivel"] == "BLOQUEIO" and a["dias"] == ["2026-10-05"]
    assert CA.situacao(con, NOME, datetime(2026, 10, 6, 8, 5), "17:00",
                       e_admin=True)["nivel"] == "VENCIDO"


def test_o_admin_ve_os_caixas_de_outros_dias_dos_outros(cg_casa):
    con = _con(cg_casa)
    _caixa(con, "2026-09-14", nome="BEATRIZ SANTOS")
    _caixa(con, "2020-03-19", nome="BEATRIZ")          # carga do E-Ofício: fica fora
    a = CA.situacao(con, "MARIO", datetime(2026, 10, 6, 9, 0), "17:00", e_admin=True)
    assert a["nivel"] == "OUTROS" and [o["data"] for o in a["outros"]] == ["2026-09-14"]
    assert CA.situacao(con, "MARIO", datetime(2026, 10, 6, 9, 0), "17:00") is None


def test_hora_torta_na_configuracao_volta_ao_padrao():
    assert CA.fim_do_expediente("25:99") == (14, 0)          # o padrão dito pelo oficial
    assert CA.fim_do_expediente("14h") == (14, 0)
    assert CA.fim_do_expediente("13:30") == (13, 30)


def test_a_tela_trava_mas_a_do_caixa_fica_livre(cg_casa):
    cg_casa["db"].create_user("elisa", NOME, "Senha#12345", "USER")
    con = _con(cg_casa)
    _caixa(con, (date.today() - timedelta(days=1)).isoformat())
    c = cg_casa["c"]
    cg_login(c, "elisa", "Senha#12345")
    outra = c.get("/tarefas", follow_redirects=True).get_data(as_text=True)
    assert "Feche o caixa de ontem antes de continuar" in outra
    # Outros avisos também usam "Entendi"; o bloqueio do caixa não pode
    # oferecer o controle que permite esconder sua própria janela.
    assert 'id="caixa-aviso-ok"' not in outra
    assert 'for="caixa-aviso-ok"' not in outra
    caixa = c.get("/caixa").get_data(as_text=True)
    assert "AINDA ESTÁ ABERTO" in caixa
    assert "Feche o caixa de ontem antes de continuar" not in caixa


def test_sem_configuracao_o_aviso_comeca_as_14h(cg_casa):
    """«avisas 14h pra fechar o caixa» — o oficial, 06/10/2026."""
    con = _con(cg_casa)
    _caixa(con, "2026-10-06")
    assert CA.situacao(con, NOME, datetime(2026, 10, 6, 13, 59)) is None
    assert CA.situacao(con, NOME, datetime(2026, 10, 6, 14, 0))["fim"] == "14:00"

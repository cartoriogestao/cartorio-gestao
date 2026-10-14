"""A tela dos envios às Centrais (06/10/2026).

O que se guarda aqui: quem registra não digita a chave — ela sai do achado, e é
a mesma que a regra procura no dia seguinte. E nada se grava pela metade.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gestor_conferencia as GC                                  # noqa: E402
import gestor_envios as GE                                       # noqa: E402
from gestor_schema import init_gestor_schema                     # noqa: E402

AGORA = "2026-10-06T08:00:00"


def _achado(con, chave, regra="X", titulo="T"):
    con.execute("""INSERT INTO ge_achados (chave, regra, gravidade, setor, titulo,
                       primeiro_visto_em, ultimo_visto_em)
                   VALUES (?, ?, 'VENCIDO', 'RCPN', ?, ?, ?)""",
                (chave, regra, titulo, AGORA, AGORA))


def _con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    init_gestor_schema(c)
    return c


def test_so_o_que_e_envio_aparece_e_com_a_central_certa(cg_casa):
    con = _con(cg_casa)
    _achado(con, "SIRC:rc_assentos:8266:2026-09-15", "SIRC")
    _achado(con, "OBITO_TRE:2026-09", "OBITO_MENSAL")
    _achado(con, "SIRC_CANC:rc_assentos:1231", "SIRC_CANCELAMENTO")
    _achado(con, "CAIXA_CONF:9", "CAIXA_PRONTO_PARA_VISTO")
    con.commit()
    itens = {i["chave"]: i for i in GE.pendentes(con)}
    assert set(itens) == {"SIRC:rc_assentos:8266:2026-09-15", "OBITO_TRE:2026-09",
                          "SIRC_CANC:rc_assentos:1231"}
    assert itens["SIRC_CANC:rc_assentos:1231"]["central"] == "SIRC_CANCELAMENTO"


def test_registrar_pela_chave_apaga_a_cobranca_na_conferencia_seguinte(cg_casa):
    con = _con(cg_casa)
    _achado(con, "OBITO_TRE:2026-09", "OBITO_MENSAL")
    con.commit()
    n = GE.registrar_pelas_chaves(con, ["OBITO_TRE:2026-09"], protocolo="INFODIP-77",
                                  registrado_por="ELISA")
    assert n == 1
    assert GE.pendentes(con)[0]["ja_registrado"] is True
    assert "2026-09" in GC._competencias_enviadas(con, "OBITO_TRE")


def test_marcacao_com_chave_torta_nao_grava_nada(cg_casa):
    con = _con(cg_casa)
    try:
        GE.registrar_pelas_chaves(con, ["OBITO_TRE:2026-09", "OBITO_TRE:setembro"],
                                  protocolo="P1", registrado_por="ELISA")
    except GE.EnvioError:
        pass
    else:
        raise AssertionError("devia recusar")
    assert con.execute("SELECT count(*) FROM ge_envios").fetchone()[0] == 0


def test_a_tela_abre_sem_o_gestor_ter_rodado(cg_casa_logada):
    r = cg_casa_logada["c"].get("/administrativo/gestor/envios")
    assert r.status_code == 200
    assert "Nenhum envio cobrado agora" in r.get_data(as_text=True)


def test_a_tela_registra_o_marcado(cg_casa_logada):
    con = _con(cg_casa_logada)
    _achado(con, "IBGE:2026-T3", "IBGE", "IBGE do 3º trimestre")
    con.commit()
    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/gestor/envios").get_data(as_text=True)
    assert "IBGE do 3º trimestre" in pagina and 'value="IBGE:2026-T3"' in pagina
    with c.session_transaction() as s:
        token = s.get("csrf_token") or s.get("_csrf_token")
    r = c.post("/administrativo/gestor/envios/registrar",
               data={"chave": "IBGE:2026-T3", "protocolo": "IBGE-123", "canal": "PORTAL",
                     "csrf_token": token}, follow_redirects=True)
    assert r.status_code == 200
    linha = con.execute("SELECT central, competencia, protocolo FROM ge_envios").fetchone()
    assert tuple(linha) == ("IBGE", "2026-T3", "IBGE-123")


def test_a_tela_das_leituras_abre_sem_a_leitura_ter_rodado(cg_casa_logada):
    r = cg_casa_logada["c"].get("/administrativo/gestor/leituras")
    assert r.status_code == 200
    assert "Nenhum apontamento esperando" in r.get_data(as_text=True)
    con = sqlite3.connect(cg_casa_logada["banco"])
    assert con.execute("SELECT 1 FROM sqlite_master WHERE name='ge_leituras'").fetchone() is None


def test_a_rodada_diaria_mora_no_pacote_e_escreve_os_relatorios(cg_casa, tmp_path):
    import gestor_rotina as GR
    linhas: list[str] = []
    codigo = GR.rodada_diaria(Path(cg_casa["banco"]), tmp_path / "dados", tmp_path / "rel",
                              date(2026, 10, 6), escrever=linhas.append)
    assert codigo == 0, "\n".join(linhas)
    nomes = sorted(p.name for p in (tmp_path / "rel").iterdir())
    assert "conferencia_2026-10-06.html" in nomes and "financeiro_2026-09.html" in nomes
    assert "erros_2026-10-06.html" in nomes


def test_o_visto_em_lote_so_vale_para_o_caixa_que_fecha(cg_casa_logada):
    con = sqlite3.connect(cg_casa_logada["banco"])
    def caixa(nome, dif):
        return con.execute(
            """INSERT INTO cx_caixas (data, operador_nome, saldo_inicial, aberto_em, fechado_em,
                   situacao, valor_esperado, valor_contado, diferenca)
               VALUES ('2026-09-20', ?, '0,00', '2026-09-20T08:00:00', '2026-09-20T14:00:00',
                       'FECHADO', '0,00', ?, ?)""", (nome, dif.lstrip("-"), dif)).lastrowid
    bom = caixa("ELISA", "0,00")
    torto = caixa("DEBORA", "5,00")
    con.commit()
    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/gestor/caixas").get_data(as_text=True)
    assert "Fecham — falta o visto (1)" in pagina and "diferença de R$ 5,00" in pagina
    with c.session_transaction() as s:
        token = s.get("csrf_token")
    c.post("/administrativo/gestor/caixas/visto",
           data={"caixa_id": [str(bom), str(torto)], "csrf_token": token})
    vistos = {r[0]: r[1] for r in con.execute("SELECT id, conferido_por FROM cx_caixas")}
    assert vistos[bom] is not None and vistos[torto] is None

"""P1 da revisao RI de 24/09/2026 — 3.6.194.

1. Certidao de onus inclui REGISTROS restritivos (hipoteca, AF, usufruto,
   servidao...), e nao so averbacoes — antes saia «NADA CONSTA» indevido.
2. A consulta CNIB fica gravada no ato lavrado (TJMA 506).
3. O prazo da prenotacao pode ser suspenso e retomado (TJMA 452, § 3º).
4. Rotas sensiveis do RI recusam USER, alinhadas ao menu.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_onus as ONUS  # noqa: E402
import ri_prenotacao_prazo as PRAZO  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "oficial": _entrar(cg_casa["app"], "mario"),
            "balcao": _entrar(cg_casa["app"], "balcao")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero, tipo_ficha="ACERVO"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, origem, criado_em, data_abertura, cidade, uf)
           VALUES (?, '2', '2', 'ATIVA', ?, 'MANUAL', '2026-09-24T08:00',
                   '2026-09-01', 'Cidade Exemplo', 'MA')""", (numero, tipo_ficha))
    return int(cur.lastrowid)


def _ato(con, mid, tipo, numero, natureza, teor, cancelado=0):
    con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
               natureza_titulo, teor, cancelado, hash_ato, lavrado_em)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (mid, tipo, numero, "2026-09-10", natureza, teor, cancelado,
         f"h{mid}{tipo}{numero}", "2026-09-10T10:00"))


# ------------------------------------------------------------------ 1. onus

def _a(tipo, natureza, teor="", cancelado=0):
    return {"tipo": tipo, "natureza_titulo": natureza, "teor": teor,
            "cancelado": cancelado}


@pytest.mark.parametrize("natureza", [
    "Hipoteca", "Alienação Fiduciária", "Usufruto", "Servidão",
    "Compromisso de Compra e Venda", "Cédulas de Crédito Rural",
    "Citações de Ações Reais ou Pessoais Reipersecutórias", "Bem de Família"])
def test_registro_restritivo_pela_natureza_entra(natureza):
    achado = ONUS.classificar(_a("R", natureza, "R-3/100 - texto qualquer."))
    assert achado == {"criterio": "natureza", "conferir": False}, natureza


def test_natureza_sem_acento_tambem_e_reconhecida():
    assert ONUS.codigo_da_natureza("ALIENACAO FIDUCIARIA") == 2


def test_registro_cancelado_nao_entra():
    assert ONUS.classificar(_a("R", "Hipoteca", cancelado=1)) is None


def test_compra_e_venda_que_fala_em_onus_no_teor_nao_entra():
    teor = ("R-2/100 - COMPRA E VENDA. O imóvel foi transmitido livre e "
            "desembaraçado de quaisquer ônus, hipotecas ou alienações.")
    assert ONUS.classificar(_a("R", "Compra e Venda", teor)) is None
    assert ONUS.classificar(_a("R", None, teor)) is None, (
        "no R a palavra-chave olha so o titulo do ato, e nao o teor inteiro")


def test_registro_sem_natureza_cai_na_palavra_chave_e_pede_conferencia():
    achado = ONUS.classificar(
        _a("R", None, "R-5/100 - HIPOTECA CEDULAR DE 1º GRAU em favor do banco."))
    assert achado == {"criterio": "palavra-chave", "conferir": True}
    achado = ONUS.classificar(_a("R", "CÉDULA RURAL HIPOTECÁRIA", "..."))
    assert achado and achado["conferir"]


def test_averbacao_de_cancelamento_nao_e_onus():
    assert ONUS.classificar(
        _a("AV", "Cancelamento de Hipoteca", "CANCELAMENTO DA HIPOTECA R-3")) is None


def test_averbacao_restritiva_continua_entrando():
    assert ONUS.classificar(_a("AV", "Penhora"))["criterio"] == "natureza"
    assert ONUS.classificar(
        _a("AV", None, "AV-4 - INDISPONIBILIDADE conforme ordem CNIB"))


def test_onus_vigentes_poe_rotulo():
    saida = ONUS.onus_vigentes(
        [_a("R", "Hipoteca") | {"numero": 3}, _a("R", "Compra e Venda")],
        rotulo=lambda a: f"R-{a['numero']:02d}")
    assert [x["rotulo"] for x in saida] == ["R-03"]


def _emitir_onus(casa, mid) -> str:
    c = casa["oficial"]
    tela = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": "ONUS", "fonte_corpo": "TEXTO",
        "requerente": "FULANO DE TAL"}, follow_redirects=True)
    con = _con(casa)
    linha = con.execute(
        "SELECT corpo FROM ri_certidoes WHERE matricula_id=? "
        "ORDER BY id DESC LIMIT 1", (mid,)).fetchone()
    con.close()
    assert linha, "a certidao de onus nao foi emitida"
    return str(linha["corpo"])


def test_certidao_de_onus_lista_hipoteca_e_usufruto_lavrados_como_R(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, "4101", tipo_ficha="ESTRUTURADA")
        _ato(con, mid, "R", 1, "Compra e Venda",
             "R-1/4101 - COMPRA E VENDA livre de ônus.")
        _ato(con, mid, "R", 2, "Hipoteca", "R-2/4101 - HIPOTECA de 1º grau.")
        _ato(con, mid, "R", 3, "Usufruto", "R-3/4101 - USUFRUTO vitalício.")
    con.close()
    corpo = _emitir_onus(casa, mid)
    assert "NADA CONSTA" not in corpo, (
        "imovel com hipoteca e usufruto registrados saiu com «NADA CONSTA»")
    assert "Hipoteca" in corpo and "Usufruto" in corpo
    assert "Compra e Venda" not in corpo


def test_certidao_de_onus_sem_gravame_continua_nada_consta(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, "4102", tipo_ficha="ESTRUTURADA")
        _ato(con, mid, "R", 1, "Compra e Venda", "R-1/4102 - COMPRA E VENDA.")
        _ato(con, mid, "R", 2, "Hipoteca", "R-2/4102 - HIPOTECA.", cancelado=1)
    con.close()
    assert "NADA CONSTA" in _emitir_onus(casa, mid)


# ------------------------------------------------------------------ 2. CNIB

def _lavrar(casa, mid, *, numero=2, natureza="Hipoteca", cliente=None,
            **extra):
    c = cliente or casa["oficial"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "tipo": "R", "numero": numero,
             "data_ato": "2026-09-24", "natureza_titulo": natureza,
             "teor": f"R-{numero}/X - {natureza.upper()} em favor do credor.",
             "parte_nome": ["MARIA DAS DORES SILVA"],
             "parte_documento": ["52998224725"],
             "parte_papel": ["credor"]}
    dados.update(extra)
    return c.post(f"/registro-imoveis/{mid}/atos", data=dados,
                  follow_redirects=True)


def _semear_cnib(con, documento, protocolo="202609240001"):
    cur = con.execute(
        """INSERT INTO ri_cnib_ordens (protocolo_cnib, data_pedido, processo,
               instituicao, ativa) VALUES (?, '2026-09-01', '0001', 'TJMA', 1)""",
        (protocolo,))
    con.execute(
        """INSERT INTO ri_cnib_pessoas (ordem_id, nome, nome_norm, documento)
           VALUES (?, 'MARIA DAS DORES SILVA', 'MARIA DAS DORES SILVA', ?)""",
        (int(cur.lastrowid), documento))


def test_lavrar_grava_a_consulta_cnib_no_ato(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, "3301")
    con.close()
    html = _lavrar(casa, mid).get_data(as_text=True)

    con = _con(casa)
    ato = con.execute("SELECT id FROM ri_atos WHERE matricula_id=? AND numero=2",
                      (mid,)).fetchone()
    assert ato, "o ato nao foi lavrado"
    linha = con.execute("SELECT * FROM ri_atos_cnib WHERE ato_id=?",
                        (ato["id"],)).fetchone()
    con.close()
    assert linha, "a consulta CNIB nao ficou gravada no ato (TJMA 506)"
    assert linha["fonte"] == "COPIA_LOCAL"
    assert linha["resultado"] == "NADA_CONSTA"
    assert "52998224725" in json.loads(linha["documentos"])
    assert linha["consultado_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert "CNIB consultada e gravada no ato" in html
    ficha = casa["oficial"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "CNIB na lavratura" in ficha


def test_consulta_positiva_e_protocolo_da_central_ficam_gravados(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, "3302")
        _semear_cnib(con, "52998224725")
    con.close()
    html = _lavrar(casa, mid, cnib_protocolo="CNIB-XYZ-123").get_data(as_text=True)
    con = _con(casa)
    linha = con.execute(
        "SELECT * FROM ri_atos_cnib WHERE matricula_id=?", (mid,)).fetchone()
    con.close()
    assert linha["fonte"] == "CENTRAL"
    assert linha["protocolo_consulta"] == "CNIB-XYZ-123"
    assert linha["resultado"] == "POSITIVO"
    assert json.loads(linha["ordens"])[0]["protocolo_cnib"] == "202609240001"
    assert "ordem(ns) ativa(s)" in html


def test_casa_que_exige_protocolo_recusa_oneracao_sem_ele(casa):
    casa["db"].set_settings({"ri_cnib_exigir_protocolo_na_lavratura": "1"})
    con = _con(casa)
    with con:
        mid = _ficha(con, "3303")
    con.close()
    html = _lavrar(casa, mid).get_data(as_text=True)
    con = _con(casa)
    ato = con.execute("SELECT id FROM ri_atos WHERE matricula_id=?",
                      (mid,)).fetchone()
    con.close()
    assert ato is None, "hipoteca sem protocolo CNIB foi lavrada"
    assert "protocolo da consulta" in html

    _lavrar(casa, mid, cnib_protocolo="CNIB-OK-1")
    con = _con(casa)
    assert con.execute("SELECT id FROM ri_atos WHERE matricula_id=?",
                       (mid,)).fetchone()
    con.close()


# ------------------------------------------------------------ 3. prenotacao

def _protocolo(con, numero=9001, limite="2026-10-01"):
    cur = con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               data_limite, situacao, criado_em)
           VALUES (?, '1A', '2026-09-01', ?, 'ABERTO', '2026-09-01T09:00')""",
        (numero, limite))
    return int(cur.lastrowid)


def test_suspender_e_retomar_empurra_o_limite_pelos_dias_parados(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con)
        PRAZO.suspender(con, pid, motivo="DUVIDA", quem="OFICIAL",
                        hoje=date(2026, 9, 21))
    p = con.execute("SELECT * FROM ri_protocolos WHERE id=?", (pid,)).fetchone()
    assert PRAZO.suspensa(p) and p["suscitacao_duvida"] == "2026-09-21"
    with con:
        saida = PRAZO.retomar(con, pid, quem="OFICIAL", hoje=date(2026, 9, 28))
    p = con.execute("SELECT * FROM ri_protocolos WHERE id=?", (pid,)).fetchone()
    con.close()
    assert saida["dias"] == 5
    assert p["data_limite"] == "2026-10-08"
    assert not PRAZO.suspensa(p)
    assert "Prazo suspenso de 2026-09-21 a 2026-09-28" in p["anotacao"]


def test_motivo_fora_do_452_e_recusado(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con, numero=9002)
    with pytest.raises(PRAZO.PrazoError):
        PRAZO.suspender(con, pid, motivo="PORQUE SIM", quem=None,
                        hoje=date(2026, 9, 21))
    con.close()


def test_prenotacao_suspensa_nao_aparece_como_vencida(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con, numero=9003, limite="2026-01-05")
    con.close()
    c = casa["oficial"]
    html = c.get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "prazo vencido" in html
    c.post(f"/registro-imoveis/protocolo/{pid}/prazo",
           data={"csrf_token": _token(html), "acao": "suspender",
                 "motivo": "USUCAPIAO"}, follow_redirects=True)
    html = c.get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "prazo vencido" not in html and "Prazo suspenso desde" in html
    lista = c.get("/registro-imoveis/protocolo").get_data(as_text=True)
    assert "prazo suspenso" in lista


def test_skeleton_usucapiao_retificacao_suspendem_sozinhos():
    pytest.skip("TODO: abrir usucapiao/retificacao ligado ao protocolo deve "
                "suspender o prazo automaticamente (TJMA 452, § 3º, IV)")


# --------------------------------------------------------------- 4. perfis

ROTAS_GET_SO_DO_OFICIAL = [
    "/registro-imoveis/numeracao",
    "/registro-imoveis/delegatarios",
    "/registro-imoveis/onr",
    "/registro-imoveis/onr/next-cloud-sas",
    "/registro-imoveis/imagens/resolver",
    "/registro-imoveis/imagens/do-disco",
]


@pytest.mark.parametrize("rota", ROTAS_GET_SO_DO_OFICIAL)
def test_balcao_nao_abre_rota_sensivel_por_url(casa, rota):
    assert casa["balcao"].get(rota).status_code == 403, rota


def test_balcao_nao_cancela_certidao_nem_baixa_revisao_nem_suspende_prazo(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, "3401")
        pid = _protocolo(con, numero=9004)
    con.close()
    b = casa["balcao"]
    token = _token(b.get(f"/registro-imoveis/{mid}").get_data(as_text=True))
    for rota in ("/registro-imoveis/certidoes/1/cancelar",
                 "/registro-imoveis/revisoes/1/baixar",
                 f"/registro-imoveis/protocolo/{pid}/prazo",
                 "/registro-imoveis/imagens/copiar"):
        r = b.post(rota, data={"csrf_token": token, "motivo": "x" * 20,
                               "decisao": "x" * 20, "acao": "suspender"})
        assert r.status_code == 403, rota


def test_menu_do_balcao_esconde_o_que_a_rota_recusa(casa):
    html = casa["balcao"].get("/registro-imoveis").get_data(as_text=True)
    for texto in ("Fichas digitalizadas", "Exportação ONR", "Delegatários",
                  "Numeração das matrículas"):
        assert texto not in html, texto
    assert "Matrículas em Word" in html

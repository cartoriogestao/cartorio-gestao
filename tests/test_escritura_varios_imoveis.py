"""A escritura de vários imóveis: uma declaração por imóvel na DOI e na CTP.

    «vamos arrumar e fazer as duas declaracoes, tanto pra ctp, como pra doi»
    — o oficial, 16/11/2026, sobre uma escritura de compra e venda de duas
    glebas rurais, cada uma com a sua matrícula, o seu preço e a sua
    avaliação do ITBI. Os dados abaixo são inventados; o caso é o mesmo.

O QUE ESTES TESTES GUARDAM
    **Uma declaração por imóvel**, cada uma com o preço, a área, o CIB e o
    INCRA DAQUELE imóvel, e destinação RURAL quando ele é rural — antes a
    escritura saía sempre urbana, com o valor da escritura inteira.

    **A escritura vai inteira ou fica inteira.** Um imóvel sem preço segura a
    escritura toda: a CTP não se repete depois de aceita, e a metade mandada
    sozinha deixaria a outra sem caminho.

    **O quadro antigo não muda.** Escritura sem lista de imóveis declara como
    sempre declarou.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import censec_api as CA                                          # noqa: E402
import censec_ctp as CTP                                         # noqa: E402
import notas_doi as NDOI                                         # noqa: E402

AGORA = "2026-11-16T22:00:00"
CPF_A, CPF_B = "52998224725", "11144477735"

GLEBA_A = {"matricula": "4101", "rural": 1, "tipo_imovel": None,
          "denominacao": "Chácara Boa Vista",
          "localizacao": "zona rural do município",
          "area": "12,3456", "cib": "9.AB1.CD2-E", "codigo_incra": "950.000.111.222-3",
          "cnm": "000000.2.0004101-00",
          "valor_centavos": 5000000, "base_itbi_centavos": 5000000}
GLEBA_B = {"matricula": "4102", "rural": 1, "tipo_imovel": 69,
                "denominacao": "Fazenda Santa Rita",
                "localizacao": "zona rural do município",
                "area": "30,5162", "cib": "7.XY3.ZW4-F", "codigo_incra": "950.000.444.555-6",
                "cnm": "000000.2.0004102-00",
                "valor_centavos": 15000000, "base_itbi_centavos": 17500000}


def _ato(**c):
    return {"id": 900, "tipo": "ESCRITURA", "data": "2026-11-12", "livro": "12",
            "folha": "34", "doi_transacao": 11, "valor_transacao": 22500000,
            "doi_matricula": "4101", **c}


def _partes():
    return [{"id": 1, "nome": "MARIA", "documento": CPF_A, "qualificacao": "VENDEDOR",
             "participacao": "100,00"},
            {"id": 2, "nome": "JOSE", "documento": CPF_B, "qualificacao": "COMPRADOR",
             "participacao": "100,00"}]


# ------------------------------------------------------------ o montador

def test_duas_glebas_rurais_dao_duas_declaracoes_cada_uma_com_o_seu():
    decls = NDOI.declaracoes_da_escritura(_ato(), _partes(), [GLEBA_A, GLEBA_B],
                                          "999999", "2198765")
    assert [d["problemas"] for d in decls] == [[], []]
    a, b = (d["registro"] for d in decls)
    assert (a["matricula"], b["matricula"]) == ("0004101", "0004102")
    assert a["destinacao"] == b["destinacao"] == "3"          # rural
    assert (a["valorOperacaoImobiliaria"], b["valorOperacaoImobiliaria"]) == (50000.0, 150000.0)
    assert (a["valorBaseCalculoItbiItcmd"], b["valorBaseCalculoItbiItcmd"]) == (50000.0, 175000.0)
    assert (a["areaImovel"], b["areaImovel"]) == (12.35, 30.52)  # duas casas, como pede o layout
    assert (a["denominacao"], b["denominacao"]) == ("Chácara Boa Vista", "Fazenda Santa Rita")
    assert (a["codigoIncra"], b["codigoIncra"]) == ("9500001112223", "9500004445556")
    assert a["tipoImovel"] == "69"                            # rural sem tipo: fazenda/sítio/chácara
    assert "nomeLogradouro" not in a and "tipoLogradouro" not in a


def test_o_cib_alfanumerico_vai_com_as_letras():
    # Até 16/11/2026 só os dígitos passavam: «9.AB1.CD2-E» virava «54».
    decls = NDOI.declaracoes_da_escritura(_ato(), _partes(), [GLEBA_A], "999999", "2198765")
    assert decls[0]["registro"]["cib"] == "9AB1CD2E"
    assert NDOI.cib_valido("9.AB1.CD2-E") is True
    assert NDOI.cib_valido("9.AB1") is False


def test_com_dois_imoveis_cada_um_precisa_do_seu_preco():
    sem_preco = dict(GLEBA_B, valor_centavos=None)
    decls = NDOI.declaracoes_da_escritura(_ato(), _partes(), [GLEBA_A, sem_preco],
                                          "999999", "2198765")
    assert decls[0]["problemas"] == []
    assert decls[1]["registro"] is None
    assert any("4102" in p["motivo"] and "preço" in p["motivo"] for p in decls[1]["problemas"])


def test_imovel_rural_sem_incra_nem_area_diz_o_que_falta():
    ruim = dict(GLEBA_A, codigo_incra=None, area=None)
    (d,) = NDOI.declaracoes_da_escritura(_ato(), _partes(), [ruim], "999999", "2198765")
    motivos = " | ".join(p["motivo"] for p in d["problemas"])
    assert "INCRA" in motivos and "HECTARES" in motivos


def test_um_imovel_so_sem_preco_proprio_usa_o_valor_da_escritura():
    so_um = dict(GLEBA_A, valor_centavos=None)
    (d,) = NDOI.declaracoes_da_escritura(_ato(), _partes(), [so_um], "999999", "2198765")
    assert d["problemas"] == []
    assert d["registro"]["valorOperacaoImobiliaria"] == 225000.0


def test_o_quadro_antigo_declara_como_sempre_declarou():
    ato = _ato(doi_matricula="4004", doi_tipo_imovel=67, doi_endereco="RUA DAS FLORES, 10",
               doi_area="360", valor_transacao=12000000)
    antes, prob = NDOI.declaracao_da_escritura(ato, _partes(), "999999", "2198765")
    (d,) = NDOI.declaracoes_da_escritura(ato, _partes(), [NDOI.imovel_do_quadro_antigo(ato)],
                                         "999999", "2198765")
    assert prob == [] and d["problemas"] == []
    assert d["registro"] == antes
    assert antes["destinacao"] == "1" and antes["nomeLogradouro"] == "RUA DAS FLORES, 10"


def test_matricula_com_dois_numeros_no_quadro_antigo_diz_um_imovel_por_linha():
    # O caso que motivou o conserto: duas matrículas num campo só.
    ato = _ato(doi_matricula="4101 e 4102", doi_endereco="duas áreas")
    _, prob = NDOI.declaracao_da_escritura(ato, _partes(), "999999", "2198765")
    assert any("um imóvel por linha" in p["motivo"] for p in prob)


# ------------------------------------------------------------ na carga da CENSEC

@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].set_settings({"ri_codigo_ibge": "2198765"})
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    ato = c.execute(
        """INSERT INTO nt_atos (tipo, data, situacao, livro, folha, origem, criado_em,
               com_imovel, doi_transacao, doi_matricula, valor_transacao)
           VALUES ('ESCRITURA','2026-11-12','LAVRADO','12','34','MANUAL',?,
                   1, 11, '4101', 22500000)""", (AGORA,)).lastrowid
    for nome, doc, q in (("MARIA", CPF_A, "VENDEDOR"), ("JOSE", CPF_B, "COMPRADOR")):
        c.execute("""INSERT INTO nt_ato_partes (ato_id, nome, documento, qualificacao,
                         participacao, criado_em) VALUES (?,?,?,?,'100,00',?)""",
                  (ato, nome, doc, q, AGORA))
    for ordem, im in enumerate((GLEBA_A, GLEBA_B), 1):
        campos = dict(im, ato_id=ato, ordem=ordem, criado_em=AGORA)
        c.execute(f"INSERT INTO nt_ato_imoveis ({', '.join(campos)}) "
                  f"VALUES ({', '.join('?' * len(campos))})", tuple(campos.values()))
    c.commit()
    yield cg_casa["db"], c, ato
    c.close()


def test_a_carga_leva_duas_declaracoes_e_a_remessa_um_ato(casa):
    db, con, ato = casa
    env = CA.montar_envio(con, 2026, 11, 2, "999999")
    assert [a["id"] for a in env["atos"]["CTP"]] == [ato]
    decl = env["corpo"]["declaracoes"]
    assert [d["matricula"] for d in decl] == ["0004101", "0004102"]
    assert {d["destinacao"] for d in decl} == {"Rural"}
    assert [d["valorOperacaoImobiliaria"] for d in decl] == [50000.0, 150000.0]
    assert CA.conferir_corpo(env["corpo"]) == []


def test_enviada_as_duas_nao_vao_de_novo(casa, monkeypatch):
    db, con, ato = casa
    enviados = []
    resposta = {"doiResult": {"success": True,
                              "carga": {"id": "c-1", "status": "AguardandoValidacao"},
                              "validationResults": []}}

    def bater(ambiente, metodo, caminho, *, corpo=None, prazo=60, pasta=None):
        enviados.append(json.loads(corpo.decode("utf-8")))
        return {"status": 200, "json": resposta, "texto": ""}
    monkeypatch.setattr(CA, "_bater", bater)
    CA.enviar_quinzena(db, 2026, 11, 2, cns="999999", ambiente="PRODUCAO", por="X")
    assert len(enviados[0]["declaracoes"]) == 2
    itens = con.execute("SELECT ato_id FROM nt_remessa_itens").fetchall()
    assert [r["ato_id"] for r in itens] == [ato]
    assert CTP.declaracoes_do_mes(con, 2026, 11, "999999")["aptos"] == []


def test_um_imovel_impedido_segura_a_escritura_inteira(casa):
    db, con, ato = casa
    con.execute("UPDATE nt_ato_imoveis SET valor_centavos = NULL WHERE matricula = '4102'")
    con.commit()
    sep = CTP.declaracoes_do_mes(con, 2026, 11, "999999")
    assert sep["aptos"] == []
    (imp,) = sep["impedidos"]
    assert all(p["motivo"].startswith("matrícula 4102") for p in imp["problemas"])
    assert "declaracoes" not in CA.montar_envio(con, 2026, 11, 2, "999999")["corpo"]


# ------------------------------------------------------------ pela ficha do ato

import re                                                        # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def tela(cg_casa):
    db, c = cg_casa["db"], cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"ri_cns": "999999", "ri_codigo_ibge": "2198765"})
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    with con:
        aid = con.execute(
            """INSERT INTO nt_atos (tipo, data, natureza, livro, folha, situacao, origem,
                   criado_em, valor_transacao, com_imovel, doi_transacao)
               VALUES ('ESCRITURA','2026-11-12','COMPRA E VENDA','12','34','LAVRADO',
                       'MANUAL',?, 22500000, 1, 11)""", (AGORA,)).lastrowid
        for nome, doc, q in (("MARIA", CPF_A, "VENDEDOR"), ("JOSE", CPF_B, "COMPRADOR")):
            con.execute("""INSERT INTO nt_ato_partes (ato_id, nome, documento, qualificacao,
                               participacao, criado_em) VALUES (?,?,?,?,'100,00',?)""",
                        (aid, nome, doc, q, AGORA))
    yield c, con, aid
    con.close()


def _form(im: dict) -> dict:
    reais = lambda c: f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d}"  # noqa: E731
    return {"matricula": im["matricula"], "rural": "1" if im["rural"] else "0",
            "tipo_imovel": str(im["tipo_imovel"] or ""), "area": im["area"],
            "denominacao": im["denominacao"], "localizacao": im["localizacao"],
            "codigo_incra": im["codigo_incra"], "cib": im["cib"], "cnm": im["cnm"],
            "valor": reais(im["valor_centavos"]), "base_itbi": reais(im["base_itbi_centavos"])}


def _postar(c, aid, **dados):
    html = c.get(f"/notas/atos/{aid}").get_data(as_text=True)
    return c.post(f"/notas/atos/{aid}", data={"csrf_token": _token(html), **dados},
                  follow_redirects=True).get_data(as_text=True)


def test_a_ficha_lanca_os_dois_imoveis_e_a_doi_do_mes_declara_os_dois(tela, monkeypatch):
    c, con, aid = tela
    assert "Imóveis desta escritura" in c.get(f"/notas/atos/{aid}").get_data(as_text=True)
    _postar(c, aid, acao="imovel_linha", **_form(GLEBA_A))
    html = _postar(c, aid, acao="imovel_linha", **_form(GLEBA_B))
    assert "matrícula 4102 lançado" in html
    linhas = con.execute("SELECT * FROM nt_ato_imoveis WHERE ato_id=? ORDER BY ordem",
                         (aid,)).fetchall()
    assert [(r["matricula"], r["rural"], r["valor_centavos"], r["base_itbi_centavos"])
            for r in linhas] == [("4101", 1, 5000000, 5000000), ("4102", 1, 15000000, 17500000)]
    assert con.execute("SELECT doi_matricula FROM nt_atos WHERE id=?", (aid,)).fetchone()[0] == "4101"

    # a mesma matrícula duas vezes é recusada
    assert "já está nesta escritura" in _postar(c, aid, acao="imovel_linha", **_form(GLEBA_A))

    # o quadro de cima, salvo de novo, não apaga a matrícula que a lista mantém
    _postar(c, aid, acao="imovel", com_imovel="1", doi_transacao="11",
            participacao_1="100,00", participacao_2="100,00")
    assert con.execute("SELECT doi_matricula FROM nt_atos WHERE id=?", (aid,)).fetchone()[0] == "4101"

    capturados = []
    declarar = NDOI.declarar

    def guardar(dec, *args, **kwargs):
        capturados.append(dec)
        return declarar(dec, *args, **kwargs)
    monkeypatch.setattr(NDOI, "declarar", guardar)
    html = c.get("/registro-imoveis/doi?competencia=2026-11").get_data(as_text=True)
    doa = [d for d in capturados if d.get("ato_id") == aid]
    assert [(d["imovel"]["matricula"], d["imovel"]["rural"], d["valor_operacao"]) for d in doa] == [
        ("4101", True, 5000000), ("4102", True, 15000000)]
    assert "matrícula 4101" in html and "matrícula 4102" in html


def test_retirar_um_imovel_deixa_o_outro(tela):
    c, con, aid = tela
    _postar(c, aid, acao="imovel_linha", **_form(GLEBA_A))
    _postar(c, aid, acao="imovel_linha", **_form(GLEBA_B))
    primeiro = con.execute("SELECT id FROM nt_ato_imoveis WHERE matricula='4101'").fetchone()[0]
    html = _postar(c, aid, acao="imovel_retirar", imovel_id=str(primeiro))
    assert "4101 retirado" in html
    assert [r[0] for r in con.execute("SELECT matricula FROM nt_ato_imoveis WHERE ato_id=?",
                                      (aid,))] == ["4102"]
    assert con.execute("SELECT doi_matricula FROM nt_atos WHERE id=?", (aid,)).fetchone()[0] == "4102"


def test_matricula_com_mais_de_sete_digitos_e_recusada_na_ficha(tela):
    c, con, aid = tela
    html = _postar(c, aid, acao="imovel_linha", **dict(_form(GLEBA_A), matricula="4101 e 4102"))
    assert "passa de 7 dígitos" in html
    assert con.execute("SELECT COUNT(*) FROM nt_ato_imoveis").fetchone()[0] == 0

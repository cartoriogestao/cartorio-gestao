"""O apresentante TAB do XML da CENPROT é um por título — 28/10/2026.

Medido nos XML reais que o E-Ofício mandou à CENPROT: 18 títulos TAB, 8
apresentantes diferentes (nome, CNPJ/CPF e tipos 0, 1 e 4), um bloco
`<apresentante codigo="TAB">` por apresentante real. O cadastro único por
código (`pt_apresentantes`) tem UM nome para o TAB, e o título sairia com o
apresentante de outra pessoa. Estes testes guardam a regra com dados
fictícios:

  - o TAB vai com o apresentante do PRÓPRIO TÍTULO, nunca com o cadastro;
  - sem nome, documento ou tipo no título, ele fica FORA, com o motivo e o
    formulário para informar;
  - o arquivo agrupa por código + documento: dois solicitantes, dois blocos;
  - mesmo documento com tipo diferente não se mistura num bloco;
  - a passada do acervo (`tbAvisoProtesto` → `tbCobrador`) só preenche o que
    está vazio;
  - o aviso e o instrumento também não caem no cadastro do TAB.
"""
from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET

import pytest

import protesto as PT
import protesto_cenprot_xml as X

from test_protesto_aviso_web import _con, _token, s, titulo_apontado  # noqa: F401
from test_protesto_cenprot_xml import _titulo
from test_protesto_cenprot_xml_tela import pronto  # noqa: F401
from test_protesto_instrumento_assinado import chave_e_cert  # noqa: F401

# documentos da lista de fictícios (tests/fixtures/anti_vazamento)
CNPJ_DO_SOLICITANTE = "00000010000127"
CNPJ_DE_OUTRO = "00000011000171"
CPF_DO_SOLICITANTE = "00000001091"


def _tab_no_titulo(s, tid, *, nome="LOJA SOLICITANTE EXEMPLO LTDA",
                   documento=CNPJ_DO_SOLICITANTE, tipo="4"):
    con = _con(s)
    with con:
        con.execute("""UPDATE pt_titulos SET apresentante_codigo='TAB',
                         apresentante_nome=?, apresentante_documento=?,
                         apresentante_tipo=? WHERE id=?""",
                    (nome, documento, tipo, tid))
        # o cadastro único do TAB é de OUTRA pessoa — é o defeito medido
        X.gravar_apresentante(con, codigo="TAB", nome="OUTRA PESSOA EXEMPLO",
                              documento=CNPJ_DE_OUTRO, tipo_apresentante="1",
                              agora="2026-10-28T10:00:00")
    con.close()


# ------------------------------------------------- o título vai com o seu


def test_o_tab_vai_com_o_apresentante_do_proprio_titulo(pronto, s):
    _tab_no_titulo(s, pronto)
    con = _con(s)
    lista = X.pendentes(con, "P")
    assert len(lista["entram"]) == 1 and not lista["fora"], lista["fora"]
    assert lista["entram"][0]["apresentante"] == {
        "codigo": "TAB", "nome": "LOJA SOLICITANTE EXEMPLO LTDA",
        "documento": CNPJ_DO_SOLICITANTE, "tipo_apresentante": "4"}
    with con:
        r = X.gerar(con, "P", uf="MA", comarca="2199999", cartorio="01",
                    dia="2026-10-28", agora="2026-10-28T13:00:00")
    raiz = ET.fromstring(bytes(X.arquivo(con, r["id"])["conteudo"]))
    ap = raiz.find(".//apresentante")
    assert ap.get("codigo") == "TAB"
    assert ap.findtext("nome") == "LOJA SOLICITANTE EXEMPLO LTDA"
    assert ap.findtext("CNPJ") == CNPJ_DO_SOLICITANTE
    assert ap.findtext("tipo_apresentante") == "4"
    assert CNPJ_DE_OUTRO.encode() not in bytes(X.arquivo(con, r["id"])["conteudo"])


@pytest.mark.parametrize("campo,valor,falta", [
    ("apresentante_tipo", None, "o tipo"),
    ("apresentante_documento", None, "o CNPJ ou CPF"),
    ("apresentante_documento", "123", "o CNPJ ou CPF"),
    ("apresentante_nome", "", "o nome"),
])
def test_tab_sem_o_seu_apresentante_fica_fora_mesmo_com_cadastro(
        pronto, s, campo, valor, falta):
    _tab_no_titulo(s, pronto)
    con = _con(s)
    with con:
        con.execute(f"UPDATE pt_titulos SET {campo}=? WHERE id=?", (valor, pronto))
    lista = X.pendentes(con, "P")
    assert not lista["entram"]
    fora = lista["fora"][0]
    assert "um por título" in fora["motivo"] and falta in fora["motivo"]
    assert fora["apresentante_do_titulo"] is True


def test_o_codigo_de_banco_continua_no_cadastro(pronto, s):
    """O 001 do `pronto` não muda: vem do cadastro, e o título não precisa
    de documento nem de tipo próprios."""
    lista = X.pendentes(_con(s), "P")
    assert lista["entram"][0]["apresentante"]["codigo"] == "001"
    assert lista["entram"][0]["apresentante"]["documento"] == "00000001000055"


# --------------------------------------- um bloco por apresentante real


def _tres_protestos(s, monkeypatch, apresentantes):
    """Três atos de protesto, cada um montado com o apresentante dado — o
    resto do título é o fictício do teste do escritor."""
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        for _ in apresentantes:
            con.execute("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em)
                           VALUES (?, 'PROTESTO', '2026-10-28', '2026-10-28')""",
                        (tid,))
        atos = [r[0] for r in con.execute(
            "SELECT id FROM pt_atos WHERE tipo='PROTESTO' ORDER BY id")]
    por_ato = dict(zip(atos, apresentantes))

    def montar(con, ato_id, *, acervo=None, com_instrumento=True):
        return {"letra": "P",
                "titulo": _titulo(id=f"2199999014124330126{ato_id:04d}"),
                "apresentante": dict(por_ato[ato_id])}
    monkeypatch.setattr(X, "montar_titulo", montar)
    return con, atos


def _tab(nome, documento, tipo):
    return {"codigo": "TAB", "nome": nome, "documento": documento,
            "tipo_apresentante": tipo}


def test_dois_solicitantes_tab_saem_em_dois_blocos(s, monkeypatch):
    con, _ = _tres_protestos(s, monkeypatch, [
        _tab("LOJA SOLICITANTE EXEMPLO LTDA", CNPJ_DO_SOLICITANTE, "4"),
        _tab("MARIO EXEMPLO", CPF_DO_SOLICITANTE, "1"),
        _tab("LOJA SOLICITANTE EXEMPLO LTDA", CNPJ_DO_SOLICITANTE, "4")])
    with con:
        r = X.gerar(con, "P", uf="MA", comarca="2199999", cartorio="01",
                    dia="2026-10-28", agora="2026-10-28T13:00:00")
    assert r["titulos"] == 3 and not r["fora"]
    raiz = ET.fromstring(bytes(X.arquivo(con, r["id"])["conteudo"]))
    assert raiz.find(".//apresentantes").get("total") == "2"
    blocos = raiz.findall(".//apresentante")
    assert [b.get("codigo") for b in blocos] == ["TAB", "TAB"]
    assert blocos[0].findtext("CNPJ") == CNPJ_DO_SOLICITANTE
    assert blocos[0].find("titulos").get("total") == "2"
    assert blocos[1].findtext("CPF") == CPF_DO_SOLICITANTE
    assert blocos[1].findtext("tipo_apresentante") == "1"


def test_mesmo_documento_com_tipo_diferente_nao_se_mistura(s, monkeypatch):
    con, atos = _tres_protestos(s, monkeypatch, [
        _tab("LOJA SOLICITANTE EXEMPLO LTDA", CNPJ_DO_SOLICITANTE, "4"),
        _tab("LOJA SOLICITANTE EXEMPLO LTDA", CNPJ_DO_SOLICITANTE, "1")])
    lista = X.pendentes(con, "P")
    assert [i["ato_id"] for i in lista["entram"]] == [atos[0]]
    assert [i["ato_id"] for i in lista["fora"]] == [atos[1]]
    assert "mesmo documento" in lista["fora"][0]["motivo"]
    with con:
        r = X.gerar(con, "P", uf="MA", comarca="2199999", cartorio="01",
                    dia="2026-10-28", agora="2026-10-28T13:00:00")
    assert r["titulos"] == 1
    # o que ficou fora não foi marcado: espera o arquivo seguinte
    assert con.execute("SELECT cenprot_xml_id FROM pt_atos WHERE id=?",
                       (atos[1],)).fetchone()[0] is None


# ------------------------------------------------- a passada do acervo


def _acervo(cobrador_codigo="", tipo=4):
    a = sqlite3.connect(":memory:")
    a.execute("CREATE TABLE tbAvisoProtesto (intChave REAL, intCodigoCobrador REAL)")
    a.execute("""CREATE TABLE tbCobrador (intCodigoCobrador REAL,
                   strRazaoSocial TEXT, strCGC TEXT, strCIC TEXT,
                   intTipoApresentante INTEGER, strCodigoBanco TEXT)""")
    a.execute("INSERT INTO tbAvisoProtesto VALUES (7.0, 40001.0)")
    a.execute("INSERT INTO tbCobrador VALUES (40001.0, 'LOJA SOLICITANTE EXEMPLO "
              "LTDA', '00.000.010/0001-27', NULL, ?, ?)", (tipo, cobrador_codigo))
    return a


def _titulo_tab_do_eoficio(s):
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        con.execute("""UPDATE pt_titulos SET apresentante_codigo='TAB',
                         apresentante_nome='NOME QUE A CARGA GRAVOU',
                         apresentante_documento=NULL, apresentante_tipo=NULL,
                         origem_chave='tbAvisoProtesto:7.0' WHERE id=?""", (tid,))
    return con, tid


def _apresentante(con, tid):
    r = con.execute("""SELECT apresentante_nome, apresentante_documento,
                              apresentante_tipo FROM pt_titulos WHERE id=?""",
                    (tid,)).fetchone()
    return tuple(r)


def test_a_passada_do_acervo_traz_os_tres_juntos_e_troca_o_nome_da_carga(s):
    con, tid = _titulo_tab_do_eoficio(s)
    with con:
        r = X.trazer_apresentantes_dos_titulos(con, _acervo())
    assert r == {"completos": 1, "so_o_tipo": 0, "nome_trocado": 1,
                 "divergentes": [], "sem_fonte": []}
    assert _apresentante(con, tid) == ("LOJA SOLICITANTE EXEMPLO LTDA",
                                       CNPJ_DO_SOLICITANTE, "4")
    # repetível: o que está completo não volta
    with con:
        assert X.trazer_apresentantes_dos_titulos(con, _acervo())["completos"] == 0


def test_a_passada_do_acervo_nao_sobrescreve_quem_informou(s):
    con, tid = _titulo_tab_do_eoficio(s)
    with con:
        con.execute("UPDATE pt_titulos SET apresentante_documento=? WHERE id=?",
                    (CNPJ_DE_OUTRO, tid))
        r = X.trazer_apresentantes_dos_titulos(con, _acervo())
    assert r["divergentes"] == [tid] and r["completos"] == 0
    assert _apresentante(con, tid) == ("NOME QUE A CARGA GRAVOU", CNPJ_DE_OUTRO,
                                       None)
    # mesmo documento: só o tipo, e o nome de quem informou fica
    with con:
        con.execute("UPDATE pt_titulos SET apresentante_documento=? WHERE id=?",
                    (CNPJ_DO_SOLICITANTE, tid))
        r = X.trazer_apresentantes_dos_titulos(con, _acervo())
    assert r["so_o_tipo"] == 1
    assert _apresentante(con, tid) == ("NOME QUE A CARGA GRAVOU",
                                       CNPJ_DO_SOLICITANTE, "4")


@pytest.mark.parametrize("acervo", [
    lambda: _acervo(cobrador_codigo="2IJ"),   # cobrador de outro código da CRA
    lambda: _acervo(tipo=None),               # sem tipo: não se inventa
])
def test_sem_fonte_no_acervo_o_titulo_fica_como_esta(s, acervo):
    con, tid = _titulo_tab_do_eoficio(s)
    with con:
        r = X.trazer_apresentantes_dos_titulos(con, acervo())
    assert r["sem_fonte"] == [tid] and r["completos"] == 0
    assert _apresentante(con, tid) == ("NOME QUE A CARGA GRAVOU", None, None)


# ------------------------------------------------------- a tela


def test_a_tela_oferece_o_formulario_e_grava_o_apresentante_do_titulo(pronto, s):
    _tab_no_titulo(s, pronto, tipo=None)
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "um por título" in html
    assert f"/protesto/cenprot-xml/titulo/{pronto}/apresentante" in html
    assert 'value="LOJA SOLICITANTE EXEMPLO LTDA"' in html     # já preenchido
    r = s["c"].post(f"/protesto/cenprot-xml/titulo/{pronto}/apresentante",
                    data={"csrf_token": _token(html),
                          "nome": "LOJA SOLICITANTE EXEMPLO LTDA",
                          "documento": "00.000.010/0001-27",
                          "tipo_apresentante": "4"}, follow_redirects=True)
    assert f"Apresentante do título {pronto} gravado" in r.get_data(as_text=True)
    lista = X.pendentes(_con(s), "P")
    assert lista["entram"][0]["apresentante"]["tipo_apresentante"] == "4"


def test_o_formulario_do_titulo_recusa_codigo_de_cadastro(pronto, s):
    with pytest.raises(X.CenprotXmlError, match="cadastro"):
        X.gravar_apresentante_do_titulo(_con(s), pronto, nome="X",
                                        documento=CNPJ_DO_SOLICITANTE,
                                        tipo_apresentante="0")


def test_o_formulario_do_titulo_recusa_tipo_que_nao_e_numero(pronto, s):
    _tab_no_titulo(s, pronto)
    with pytest.raises(X.CenprotXmlError, match="tipo"):
        X.gravar_apresentante_do_titulo(_con(s), pronto, nome="X",
                                        documento=CNPJ_DO_SOLICITANTE,
                                        tipo_apresentante="")


# ------------------------------------- o aviso e o instrumento também


def test_o_aviso_e_o_instrumento_nao_caem_no_cadastro_do_tab(s):
    tid = titulo_apontado(s)
    _tab_no_titulo(s, tid, documento=None, tipo=None)
    con = _con(s)
    with con:
        con.execute("UPDATE pt_apresentantes SET endereco='RUA DE OUTRO, 1' "
                    "WHERE codigo='TAB'")
    titulo = dict(con.execute("SELECT * FROM pt_titulos WHERE id=?",
                              (tid,)).fetchone())
    ap = PT.apresentante_do_titulo(con, titulo)
    assert ap["nome"] == "LOJA SOLICITANTE EXEMPLO LTDA"
    assert ap["documento"] == "" and ap["endereco"] == ""

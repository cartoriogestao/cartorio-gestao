"""O XML da CENPROT montado do que o sistema lavrou, e a tela — 15/10/2026.

O escritor foi provado byte a byte contra os 28 arquivos reais; a montagem,
campo a campo contra os 66 títulos deles (77 campos iguais em todos). Estes
testes guardam as regras com um título fictício:

  - o que este sistema lavrou entra; o que falta aparece COM O MOTIVO;
  - o P leva o instrumento assinado, e sem ele o protesto espera;
  - o edital publicado vai como verdadeiro (decisão do oficial);
  - cada ato vai a UM arquivo só, e o segundo do dia ganha o sequencial 02;
  - o arquivo baixa como foi gerado, com o BOM.
"""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

import pytest

import protesto as PT
import protesto_cenprot_xml as X
import protesto_instrumento as PI

from test_protesto_aviso_web import _con, _token, s, titulo_apontado  # noqa: F401
from test_protesto_instrumento_assinado import (PDF, SV, _assinar,  # noqa: F401
                                                chave_e_cert)

CHAVE = "21999990141243301261010"
REGISTRO = {"cedente_nome": "LOJA EXEMPLO LTDA",
            "cedente_nome_2": "FACTORING EXEMPLO SA",
            "cedente_documento": "00000001000055",
            "cedente_endereco": "RUA A, 1", "cedente_cep": "65000000",
            "cedente_cidade": "SAO LUIS", "cedente_uf": "MA",
            "devedor_nome": "JOSÉ DA SILVA", "devedor_tipo_de_documento": 2,
            "devedor_documento": "00004785512388",
            "devedor_endereco": "RUA GRANDE, 10", "devedor_bairro": "CENTRO",
            "devedor_cep": "65936000", "devedor_cidade": "CIDADE EXEMPLO",
            "devedor_uf": "MA", "aceite": "N"}


@pytest.fixture()
def pronto(s, chave_e_cert, tmp_path, monkeypatch):
    """Um protesto lavrado por edital, com chave, instrumento assinado e o
    apresentante cadastrado — o caminho inteiro até o arquivo P."""
    monkeypatch.setattr(X, "registro_da_cra", lambda con, t, acervo=None: REGISTRO)
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        PT.lancar_intimacao(con, tid, modo="EDITAL", codigo_edital="1/2026",
                            agora="2026-10-10T10:00:00")
        con.execute("UPDATE pt_titulos SET motivo_protesto='1', chave_cenprot=? "
                    "WHERE id=?", (CHAVE, tid))
        PT.lancar_protesto(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                           data_extenso="x")
        con.execute("UPDATE pt_atos SET folha=COALESCE(folha, 12), detalhe_json="
                    "'{\"livro_do_acervo\": \"9\"}' WHERE titulo_id=? AND "
                    "tipo='PROTESTO' AND livro_id IS NULL", (tid,))
        ins = PI.emitir(con, tid, serventia=SV["unit_name"],
                        agora="2026-10-14T11:00:00")
        PI.guardar_assinatura(con, ins["id"], pdf=PDF,
                              p7s=_assinar(chave_e_cert, PDF),
                              pasta_de_arquivos=tmp_path,
                              agora="2026-10-14T12:00:00")
        X.gravar_apresentante(con, codigo="001", nome="BANCO DO BRASIL SA",
                              documento="00000001000055", tipo_apresentante="0",
                              agora="2026-10-14T12:00:00")
    con.close()
    return tid


def test_o_protesto_pronto_entra_com_edital_verdadeiro_e_instrumento(pronto, s):
    con = _con(s)
    lista = X.pendentes(con, "P")
    assert len(lista["entram"]) == 1 and not lista["fora"]
    t = lista["entram"][0]["titulo"]
    assert t["id"] == CHAVE and t["endosso"] == "H"
    assert t["cedente"] == {"nome": "LOJA EXEMPLO LTDA", "endereco": {}}
    assert t["sacador"]["documento"] == "00000001000055"
    dev = t["devedores"][0]
    assert dev["documento"] == "04785512388"            # CPF: o tipo manda
    assert dev["edital"] is True and dev["intimado"] is False
    assert t["num_livro"] and t["tipo_livro"] == "G"
    assert t["instrumento"][:1] == b"0"                 # o PKCS#7 assinado


def test_sem_instrumento_assinado_o_protesto_espera_com_o_motivo(pronto, s):
    con = _con(s)
    with con:
        con.execute("UPDATE as_documentos SET caminho_assinado=NULL")
    lista = X.pendentes(con, "P")
    assert not lista["entram"]
    assert "instrumento" in lista["fora"][0]["motivo"]


def test_sem_cadastro_do_apresentante_espera_com_o_motivo(pronto, s):
    con = _con(s)
    with con:
        con.execute("DELETE FROM pt_apresentantes")
    assert "apresentante 001" in X.pendentes(con, "P")["fora"][0]["motivo"]


def test_o_ato_do_eoficio_nao_entra(pronto, s):
    con = _con(s)
    with con:
        con.execute("UPDATE pt_atos SET origem='EOFICIO' WHERE tipo='PROTESTO'")
    assert X.pendentes(con, "P") == {"entram": [], "fora": []}


def test_gerar_guarda_marca_e_nao_repete(pronto, s):
    con = _con(s)
    with con:
        r = X.gerar(con, "P", uf="MA", comarca="2199999", cartorio="01",
                    dia="2026-10-15", agora="2026-10-15T13:00:00")
    assert r["nome"] == "MA-2199999-01-P-20261015-01.xml" and r["titulos"] == 1
    arq = X.arquivo(con, r["id"])
    raiz = ET.fromstring(bytes(arq["conteudo"]))
    ap = raiz.find(".//apresentante")
    assert ap.get("codigo") == "001" and ap.findtext("CNPJ") == "00000001000055"
    assert raiz.find(".//titulo").get("id") == CHAVE
    assert base64.b64decode(raiz.findtext(".//instrumento_eletronico"))[:1] == b"0"
    assert X.pendentes(con, "P") == {"entram": [], "fora": []}
    with pytest.raises(X.CenprotXmlError, match="Não há ato pronto"):
        X.gerar(con, "P", uf="MA", comarca="2199999", cartorio="01",
                dia="2026-10-15", agora="2026-10-15T13:05:00")


def test_o_segundo_arquivo_do_dia_e_o_02(s):
    con = _con(s)
    with con:
        con.execute("""INSERT INTO pt_cenprot_xml(letra, dia, sequencial,
                         nome_arquivo, conteudo, sha256, titulos, gerado_em)
                       VALUES ('P','2026-10-15',1,'x.xml',x'00','h',1,'t')""")
    nome = X.nome_do_arquivo(uf="MA", comarca="2199999", cartorio="01",
                             letra="P", dia="2026-10-15",
                             sequencial=1 + con.execute(
                                 "SELECT COUNT(*) FROM pt_cenprot_xml WHERE "
                                 "letra='P' AND dia='2026-10-15'").fetchone()[0])
    assert nome.endswith("-02.xml")


def test_o_cadastro_recusa_documento_torto(s):
    con = _con(s)
    with pytest.raises(X.CenprotXmlError, match="CNPJ"):
        X.gravar_apresentante(con, codigo="237", nome="BANCO", documento="123",
                              tipo_apresentante="0", agora="t")


# ------------------------------------------------------------- a tela


def test_a_tela_mostra_o_pronto_e_gera_e_baixa(pronto, s):
    con = _con(s)
    with con:
        for k, v in (("ibge_uf", "21"), ("ibge_municipio", "99999"),
                     ("ibge_cartorio", "01")):
            con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)",
                        (k, v))
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "1 pronto(s)" in html and "Gerar o arquivo P" in html
    r = s["c"].post("/protesto/cenprot-xml/gerar",
                    data={"csrf_token": _token(html), "letra": "P"},
                    follow_redirects=True)
    tela = r.get_data(as_text=True)
    assert "gerado com 1 título" in tela
    xml_id = _con(s).execute("SELECT id FROM pt_cenprot_xml").fetchone()[0]
    baixa = s["c"].get(f"/protesto/cenprot-xml/{xml_id}/baixar")
    assert baixa.status_code == 200
    assert baixa.data.startswith("﻿".encode("utf-8"))
    assert "-P-" in baixa.headers["Content-Disposition"]


def test_a_tela_mostra_o_motivo_de_quem_fica_de_fora(s):
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        PT.lancar_intimacao(con, tid, modo="PESSOAL", agora="2026-10-10T10:00:00")
        con.execute("UPDATE pt_titulos SET motivo_protesto='1' WHERE id=?", (tid,))
        PT.lancar_protesto(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                           data_extenso="x")
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "chave do CENPROT" in html


def test_cadastrar_apresentante_pela_tela(s):
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot-xml/apresentantes",
                    data={"csrf_token": _token(html), "codigo": "237",
                          "nome": "BANCO EXEMPLO", "documento": "00.000.001/0000-55",
                          "tipo_apresentante": "0"}, follow_redirects=True)
    assert "Apresentante 237 gravado" in r.get_data(as_text=True)
    assert X.apresentante(_con(s), "237")["documento"] == "00000001000055"


# ------------------------------------- o motivo do edital e a anuência


def test_o_motivo_do_edital_vai_no_devedor(pronto, s):
    """Pedido do oficial, 15/10/2026: o E-Ofício mandava vazio."""
    con = _con(s)
    with con:
        con.execute("""UPDATE pt_atos SET detalhe_json='{"modo": "EDITAL",
                         "motivo": "Ausente"}' WHERE tipo='INTIMACAO'""")
    dev = X.pendentes(con, "P")["entram"][0]["titulo"]["devedores"][0]
    assert dev["edital"] is True and dev["edital_motivo"] == "Ausente"


def test_o_edital_publicado_aqui_leva_o_motivo_do_aviso(s):
    """O edital que ESTE sistema publica guarda o motivo no aviso, e não no
    ato — e o edital eletrônico também passou a achá-lo."""
    import protesto_cenprot as PCEN
    from test_protesto_aviso_web import aviso_id, emitir, registrar
    tid = titulo_apontado(s)
    emitir(s, tid)
    registrar(s, aviso_id(s), entregue="0", motivo="11")
    con = _con(s)
    with con:
        con.execute("UPDATE pt_avisos SET situacao='EDITAL' WHERE id=?",
                    (aviso_id(s),))
        PT.lancar_intimacao(con, tid, modo="EDITAL", codigo_edital="1/2026",
                            agora="2026-10-10T10:00:00")
    assert PCEN._motivo_do_edital(con, tid) == "Ausente"


def test_sem_anuencia_o_flag_vai_falso_e_sem_origem(pronto, s):
    t = X.pendentes(_con(s), "P")["entram"][0]["titulo"]
    assert t["anuencia"] == {"flag": False}
    raiz = ET.fromstring(X.escrever(letra="P", uf="MA", comarca="2199999",
                                    cartorio="01", apresentantes=[{
                                        "codigo": "001", "titulos": [t]}]))
    an = raiz.find(".//anuencia")
    assert [f.tag for f in an] == ["flag"] and an.findtext("flag") == "false"


def test_anuencia_da_cenprot_aprovada_vai_com_origem_2(pronto, s):
    con = _con(s)
    with con:
        con.execute("""INSERT INTO cn_pendencias(especie, ambiente, codigo,
                         chave, titulo_id, teor, baixada_em, situacao, decisao,
                         decidida_em)
                       VALUES ('ANUENCIA','PRODUCAO','9',?,?,'{}','t',
                               'ENVIADA','{"ic_aprovado": true}',
                               '2026-10-14T09:00:00')""", (CHAVE, pronto))
    t = X.pendentes(con, "P")["entram"][0]["titulo"]
    assert t["anuencia"] == {"flag": True, "origem": "2",
                             "origem_datahora": "2026-10-14"}
    raiz = ET.fromstring(X.escrever(letra="P", uf="MA", comarca="2199999",
                                    cartorio="01", apresentantes=[{
                                        "codigo": "001", "titulos": [t]}]))
    an = raiz.find(".//anuencia")
    assert [f.tag for f in an] == ["flag", "origem", "origem_datahora"]
    assert an.findtext("origem") == "2"


def test_cancelamento_por_anuencia_do_credor_vai_com_origem_3(pronto, s):
    con = _con(s)
    with con:
        PT.lancar_cancelamento(con, pronto, hipotese="ANUENCIA_CREDOR",
                               fundamento="carta de anuência do credor "
                                          "apresentada no balcão",
                               agora="2026-10-15T09:00:00")
    d = X.pendentes(con, "D")["entram"][0]["titulo"]
    assert d["ocorrencia"] == "A"
    assert d["anuencia"] == {"flag": True, "origem": "3",
                             "origem_datahora": "2026-10-15"}

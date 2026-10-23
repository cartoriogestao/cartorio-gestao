# -*- coding: utf-8 -*-
"""As certidões pedidas pelo ONR (Ofício Eletrônico, Certidoes.asmx).

    «faça a da onr certidões»                       — o oficial, 11/10/2026

Sem rede: o transporte do WSOficio é simulado. O XML dos pedidos usado aqui é
DE ENSAIO — o formato real não está no manual e se confere na primeira busca.
"""
from __future__ import annotations

import base64
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import onr_certidoes as OC
import onr_wsoficio as WS
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

RAIZ = Path(__file__).resolve().parents[3]
WSDL = RAIZ / "FONTES_EXTERNAS" / "onr_wsoficio" / "producao" / "Certidoes.wsdl"
X = "{http://www.w3.org/2001/XMLSchema}"

XML_ENSAIO = """<?xml version="1.0" encoding="UTF-16"?>
<ROOT>
  <PEDIDO><PROTOCOLO>C2026001</PROTOCOLO><TIPOCERTIDAO>3</TIPOCERTIDAO>
    <STATUS>1</STATUS><NOMESOLICITANTE>BANCO X</NOMESOLICITANTE>
    <MATRICULA>1.234</MATRICULA></PEDIDO>
  <PEDIDO><PROTOCOLO>C2026002</PROTOCOLO><TIPOCERTIDAO>12</TIPOCERTIDAO>
    <STATUS>3</STATUS><NOMESOLICITANTE>FULANO</NOMESOLICITANTE></PEDIDO>
</ROOT>"""


def _con():
    con = conexao_de_teste()
    con.execute("CREATE TABLE ri_matriculas (id INTEGER PRIMARY KEY, numero TEXT)")
    con.execute("INSERT INTO ri_matriculas(id, numero) VALUES (77, '1234')")
    con.execute("""CREATE TABLE attachments (id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT, entity_id INTEGER, original_name TEXT, stored_name TEXT,
        stored_path TEXT, sha256 TEXT, size_bytes INTEGER, description TEXT,
        uploaded_by INTEGER, uploaded_at TEXT)""")
    OC.init_schema(con)
    return con


@pytest.mark.skipif(not WSDL.is_file(), reason="contrato fora da árvore")
def test_a_ordem_dos_campos_e_a_do_wsdl_de_producao():
    raiz = ET.parse(WSDL).getroot()
    tipos = {ct.get("name"): [e.get("name") for e in ct.findall(f"{X}sequence/{X}element")]
             for ct in raiz.iter(X + "complexType") if ct.get("name")}
    req = {e.get("name"): e.find(f"{X}complexType/{X}sequence/{X}element").get("type").split(":")[-1]
           for e in raiz.iter(X + "element")
           if e.get("name") in WS.CAMPOS and e.find(f"{X}complexType/{X}sequence/{X}element") is not None}
    for metodo in ("ObterXMLSolicitacoes_v6", "InformarCustasCertidao", "EnviarAnexoCertidao",
                   "EnviarAnexosListCertidao", "FinalizarRespostaCertidao", "DevolverCertidao"):
        assert tuple(tipos[req[metodo]]) == WS.CAMPOS[metodo], metodo
    item, campos = WS.LISTAS["AnexoList"]
    assert tuple(tipos[item]) == campos


def test_envelope_da_lista_de_anexos():
    corpo = WS.envelope("EnviarAnexosListCertidao", {
        "Hash": "H", "Protocolo": "P1",
        "AnexoList": [{"NomeArquivo": "a.pdf", "ArquivoBase64": "QQ=="},
                      {"NomeArquivo": "a.p7s", "ArquivoBase64": "Qg=="}]}).decode()
    assert ("<AnexoList><AnexoListCertidao_WSReq><NomeArquivo>a.pdf</NomeArquivo>"
            "<ArquivoBase64>QQ==</ArquivoBase64></AnexoListCertidao_WSReq>") in corpo
    assert corpo.index("<Protocolo>") < corpo.index("<AnexoList>")


def test_le_os_pedidos_e_acha_a_matricula():
    pedidos = OC.ler_pedidos(XML_ENSAIO)
    assert [p["protocolo"] for p in pedidos] == ["C2026001", "C2026002"]
    assert pedidos[0]["matricula_numero"] == "1234"
    assert pedidos[0]["solicitante"] == "BANCO X"
    assert pedidos[0]["dados"]["TIPOCERTIDAO"] == "3"


def test_guardar_e_idempotente_congela_o_teor_e_fecha_o_que_o_onr_fechou():
    con = _con()
    r = OC.guardar_pedidos(con, "PRODUCAO", XML_ENSAIO, "2026-10-11T10:00:00")
    assert r == {"novos": 2, "atualizados": 0}
    p1 = con.execute("SELECT matricula_id, situacao FROM onr_cert_pedidos WHERE protocolo='C2026001'").fetchone()
    assert p1 == (77, "NOVO")
    outra = XML_ENSAIO.replace("<STATUS>1</STATUS>", "<STATUS>12</STATUS>").replace("BANCO X", "MUDOU")
    r = OC.guardar_pedidos(con, "PRODUCAO", outra, "2026-10-11T11:00:00")
    assert r == {"novos": 0, "atualizados": 2}
    linha = con.execute("SELECT situacao, solicitante, status_onr FROM onr_cert_pedidos "
                        "WHERE protocolo='C2026001'").fetchone()
    assert linha == ("FECHADO_NO_ONR", "BANCO X", "12")


def test_so_pdf_ou_p7s(tmp_path):
    con = _con()
    OC.guardar_pedidos(con, "PRODUCAO", XML_ENSAIO, "t")
    with pytest.raises(OC.CertidaoOnrError, match="pdf ou .p7s"):
        OC.guardar_anexo(con, 1, nome="certidao.odt", conteudo=b"x", pasta=tmp_path,
                         usuario_id=1, agora="t")


def test_nao_finaliza_sem_enviar_e_devolver_exige_motivo(tmp_path):
    con = _con()
    OC.guardar_pedidos(con, "PRODUCAO", XML_ENSAIO, "t")
    with pytest.raises(OC.CertidaoOnrError, match="erro 17"):
        OC.conferir_finalizacao(con, 1)
    with pytest.raises(OC.CertidaoOnrError, match="dez letras"):
        OC.conferir_devolucao(con, 1, "curto")
    with pytest.raises(OC.CertidaoOnrError, match="Guarde antes"):
        OC.anexos_para_enviar(con, 1)


def test_custas_aceitam_virgula():
    assert OC.conferir_custas("R$ 1.102,15") == "1102.15"
    with pytest.raises(OC.CertidaoOnrError):
        OC.conferir_custas("abc")


class _OnrDeMentira:
    """Responde como o WSOficio: login com 1 token, e RETORNO=true no resto."""

    def __init__(self):
        self.chamadas = []

    def __call__(self, url, corpo, acao):
        metodo = acao.rsplit("/", 1)[-1]
        self.chamadas.append((metodo, corpo.decode()))
        if metodo == "LoginUsuarioCertificado":
            res = "<RETORNO>true</RETORNO><Tokens><string>ABC123</string></Tokens>"
        elif metodo == "ObterXMLSolicitacoes_v6":
            from xml.sax.saxutils import escape
            res = f"<RETORNO>true</RETORNO><XML>{escape(XML_ENSAIO)}</XML>"
        else:
            res = "<RETORNO>true</RETORNO><CODIGOERRO>0</CODIGOERRO>"
        return 200, ('<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                     f'<soap:Body><{metodo}Response xmlns="http://tempuri.org/WSOficio">'
                     f'<{metodo}Result>{res}</{metodo}Result></{metodo}Response></soap:Body></soap:Envelope>')


def _sessao(tmp_path, onr):
    WS.configurar(ambiente=WS.PRODUCAO, pasta=tmp_path, id_parceiro="1234",
                  chave="00000000-0000-0000-0000-000000000000", cpf="00000000191",
                  email="a@b.c")
    cert = {"SUBJECTCN": "TITULAR", "ISSUERO": "ICP-Brasil", "PUBLICKEY": "AB",
            "SERIALNUMBER": "01", "VALIDUNTIL": "01/01/2030"}
    return WS.Sessao(ambiente=WS.PRODUCAO, pasta=tmp_path, transporte=onr, certificado=cert)


def test_o_ciclo_inteiro_com_o_onr_simulado(tmp_path, monkeypatch):
    onr = _OnrDeMentira()
    s = _sessao(tmp_path, onr)
    con = _con()
    r = s.certidoes_a_emitir(de="2026-09-11", ate="2026-10-11")
    OC.guardar_pedidos(con, "PRODUCAO", r["XML"], "t")
    OC.guardar_anexo(con, 1, nome="certidao_1234.pdf", conteudo=b"%PDF-1.4 teste",
                     pasta=tmp_path / "arq", usuario_id=1, agora="t")
    lista = OC.anexos_para_enviar(con, 1)
    assert base64.b64decode(lista[0]["ArquivoBase64"]) == b"%PDF-1.4 teste"
    s.enviar_anexos_da_certidao("C2026001", lista)
    OC.registrar_envio(con, 1, ["certidao_1234.pdf"], "Escrevente Exemplo", "t")
    p = OC.conferir_finalizacao(con, 1)
    s.finalizar_certidao(p["protocolo"], interesse_social=False)
    OC.registrar_finalizacao(con, 1, False, "Escrevente Exemplo", "t")
    assert OC.pedido(con, 1)["situacao"] == "RESPONDIDO"
    metodos = [m for m, _ in onr.chamadas if m != "LoginUsuarioCertificado"]
    assert metodos == ["ObterXMLSolicitacoes_v6", "EnviarAnexoCertidao", "FinalizarRespostaCertidao"]
    final = dict(onr.chamadas)["FinalizarRespostaCertidao"]
    assert "<InteresseSocial>false</InteresseSocial>" in final and "<Matriculas>" not in final


def test_codigo_200_do_onr_e_lista_vazia(tmp_path, monkeypatch):
    class Vazio(_OnrDeMentira):
        def __call__(self, url, corpo, acao):
            if acao.endswith("ObterXMLSolicitacoes_v6"):
                return 200, ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
                             '<ObterXMLSolicitacoes_v6Response xmlns="http://tempuri.org/WSOficio">'
                             '<ObterXMLSolicitacoes_v6Result><RETORNO>false</RETORNO><CODIGOERRO>200</CODIGOERRO>'
                             '<ERRODESCRICAO>Não foram localizados registros para exportação</ERRODESCRICAO>'
                             '</ObterXMLSolicitacoes_v6Result></ObterXMLSolicitacoes_v6Response></soap:Body></soap:Envelope>')
            return super().__call__(url, corpo, acao)
    s = _sessao(tmp_path, Vazio())
    assert s.certidoes_a_emitir()["vazio"] is True


def test_anexo_com_extensao_errada_nao_vai_a_rede(tmp_path):
    onr = _OnrDeMentira()
    s = _sessao(tmp_path, onr)
    with pytest.raises(WS.WSOficioError, match="pdf ou .p7s"):
        s.enviar_anexos_da_certidao("P", [{"NomeArquivo": "x.docx", "ArquivoBase64": "QQ=="}])
    assert onr.chamadas == []


def test_telas(cg_casa_logada, monkeypatch):
    c = cg_casa_logada["c"]
    html = c.get("/ri/onr/certidoes").get_data(as_text=True)
    assert "Buscar pedidos no ONR" in html and 'name="csrf_token"' in html
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)

    class SessaoFalsa:
        def __init__(self, **_):
            pass

        def certidoes_a_emitir(self, **_):
            return {"RETORNO": True, "XML": XML_ENSAIO}

    import onr_certidoes_web as W
    monkeypatch.setattr(W.WS, "Sessao", SessaoFalsa)
    r = c.post("/ri/onr/certidoes/buscar", data={"csrf_token": tok, "dias": "30"},
               follow_redirects=True).get_data(as_text=True)
    assert "C2026001" in r and "2 pedido(s) novo(s)" in r
    ficha = c.get("/ri/onr/certidoes/1").get_data(as_text=True)
    assert "Guardar o arquivo" in ficha and "NOMESOLICITANTE" in ficha


#: O FORMATO MEDIDO EM PRODUÇÃO em 11/10/2026 (97 pedidos) — com valores inventados.
XML_FORMATO_REAL = """<?xml version="1.0" encoding="UTF-16"?><ROOT>
<PEDIDO_CERTIDAO><PROTOCOLO_SOLICITACAO>S99000000001D</PROTOCOLO_SOLICITACAO>
 <DATA_PEDIDO>09/10/2026 11:56:00</DATA_PEDIDO><STATUS_SOLICITACAO>Em aberto</STATUS_SOLICITACAO>
 <TIPO_COBRANCA>1</TIPO_COBRANCA><VALOR>123.06</VALOR>
 <SOLICITANTE><NOME>SOLICITANTE DE ENSAIO</NOME><ENDERECO><UF>MA</UF></ENDERECO></SOLICITANTE>
 <CERTIDAO><TIPO>3</TIPO><PEDIDO_POR>4</PEDIDO_POR><MATRICULA><NUMERO>1234</NUMERO></MATRICULA>
  <PROTOCOLO/><OBSERVACAO/></CERTIDAO><NUMERO_PROCESSO/></PEDIDO_CERTIDAO>
<PEDIDO_CERTIDAO><PROTOCOLO_SOLICITACAO>S99000000002D</PROTOCOLO_SOLICITACAO>
 <DATA_PEDIDO>06/07/2026 10:00:00</DATA_PEDIDO><STATUS_SOLICITACAO>Respondido</STATUS_SOLICITACAO>
 <SOLICITANTE><NOME>OUTRO</NOME></SOLICITANTE><CERTIDAO><TIPO>1</TIPO><PEDIDO_POR>6</PEDIDO_POR>
 <MATRICULA/><PROTOCOLO/></CERTIDAO></PEDIDO_CERTIDAO></ROOT>"""


def test_formato_real_medido_em_producao():
    ps = OC.ler_pedidos(XML_FORMATO_REAL)
    assert [p["protocolo"] for p in ps] == ["S99000000001D", "S99000000002D"]
    p = ps[0]
    assert (p["data_pedido"], p["status_onr"], p["tipo_certidao"], p["pesquisa_por"],
            p["matricula_numero"], p["solicitante"], p["valor"]) == (
        "2026-10-09T11:56:00", "Em aberto", "3", "4", "1234", "SOLICITANTE DE ENSAIO", "123.06")
    assert p["dados"]["SOLICITANTE/ENDERECO/UF"] == "MA"


def test_o_historico_ja_respondido_entra_fora_da_fila():
    con = _con()
    OC.guardar_pedidos(con, "PRODUCAO", XML_FORMATO_REAL, "t")
    fila = OC.fila(con)
    assert [p["protocolo"] for p in fila] == ["S99000000001D"]
    assert fila[0]["matricula_id"] == 77
    assert len(OC.fila(con, todos=True)) == 2

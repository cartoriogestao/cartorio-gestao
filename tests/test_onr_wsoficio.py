"""O WSOficio do ONR — login por certificado, hash por mensagem, e as leituras.

O QUE ESTES TESTES GUARDAM
    **A ordem dos campos é a do WSDL de produção.** Em document/literal o .NET
    ignora calado o campo fora de ordem; o teste abre o contrato e compara.
    **O hash é SHA-1(chave + token)**, e a caixa que o ONR aceitar é a que fica.
    **«Hash já utilizado» não é caixa errada** — não gasta outro token à toa.
    **Este módulo só lê**: nenhuma operação que responda ou importe.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_wsoficio as W                                           # noqa: E402

CONTRATO = RAIZ.parent.parent / "FONTES_EXTERNAS" / "onr_wsoficio" / "producao"
CHAVE = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"
CERT = {"SUBJECTCN": "FULANO DE TAL:00000004421", "ISSUERO": "ICP-Brasil",
        "PUBLICKEY": "3082010A0282010100AB", "SERIALNUMBER": "763222E368FD67A9",
        "VALIDUNTIL": "08/01/2028 16:10:00"}


def _soap(metodo: str, corpo: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap='
            '"http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            f'<{metodo}Response xmlns="{W.NS}"><{metodo}Result>{corpo}</{metodo}Result>'
            f'</{metodo}Response></soap:Body></soap:Envelope>')


class ONRDeMentira:
    """Confere o hash como o ONR confere: token de uso único, chave + token."""

    def __init__(self, *, aceita_maiusculas=True):
        self.aceita_maiusculas = aceita_maiusculas
        self.emitidos, self.usados, self.chamadas = [], set(), []

    def __call__(self, url, corpo, acao):
        metodo = acao.rsplit("/", 1)[-1]
        xml = corpo.decode("utf-8")
        self.chamadas.append((url, metodo, xml))
        if metodo == "LoginUsuarioCertificado":
            novos = [f"TK{len(self.emitidos) + i:04d}" for i in range(5)]
            self.emitidos += novos
            toks = "".join(f"<string>{t}</string>" for t in novos)
            return 200, _soap(metodo, "<RETORNO>true</RETORNO><CODIGOERRO>0</CODIGOERRO>"
                                      "<IDUsuario>7</IDUsuario><IDInstituicao>99</IDInstituicao>"
                                      f"<Ativo>true</Ativo><Tokens>{toks}</Tokens>")
        h = re.search(r"<Hash>(.*?)</Hash>", xml).group(1)
        valido = None
        for t in self.emitidos:
            esperado = hashlib.sha1((CHAVE + t).encode()).hexdigest()
            esperado = esperado.upper() if self.aceita_maiusculas else esperado
            if h == esperado:
                valido = t
        if valido is None:
            return 200, _soap(metodo, "<RETORNO>false</RETORNO><CODIGOERRO>45</CODIGOERRO>"
                                      "<ERRODESCRICAO>Hash inválido.</ERRODESCRICAO>")
        if valido in self.usados:
            return 200, _soap(metodo, "<RETORNO>false</RETORNO><CODIGOERRO>46</CODIGOERRO>"
                                      "<ERRODESCRICAO>Hash inválido: Hash já utilizado."
                                      "</ERRODESCRICAO>")
        self.usados.add(valido)
        if metodo == "ListPedidosPO":
            return 200, _soap(metodo, "<RETORNO>true</RETORNO><QtdeRegistros>1</QtdeRegistros>"
                                      "<QtdePaginas>1</QtdePaginas><Pedidos>"
                                      "<ListPedidosPO_Pedidos_WSResp><IDPedido>123</IDPedido>"
                                      "<Protocolo>PO-1</Protocolo><Vara>1ª Vara</Vara>"
                                      "<IDTipoPedido>3</IDTipoPedido><IDStatus>1</IDStatus>"
                                      "</ListPedidosPO_Pedidos_WSResp></Pedidos>")
        return 200, _soap(metodo, "<RETORNO>true</RETORNO><QtdeRegistros>0</QtdeRegistros>")


@pytest.fixture()
def pasta(tmp_path):
    W.configurar(pasta=tmp_path, id_parceiro="2869", chave=CHAVE, cpf="000.000.044-21",
                 email="oficial@exemplo.org")
    return tmp_path


def _sessao(pasta, onr):
    return W.Sessao(pasta=pasta, transporte=onr, certificado=CERT)


# ------------------------------------------------------------------ o contrato

@pytest.mark.skipif(not CONTRATO.is_dir(), reason="o contrato não está nesta árvore")
def test_a_ordem_dos_campos_e_a_do_wsdl_de_producao():
    X = "{http://www.w3.org/2001/XMLSchema}"
    tipos = {}
    for f in CONTRATO.glob("*.wsdl"):
        raiz = ET.parse(f).getroot()
        for ct in raiz.iter(X + "complexType"):
            if ct.get("name"):
                tipos[ct.get("name")] = tuple(e.get("name") for e in ct.iter(X + "element"))
    # A v6 das certidões usa o tipo da v2 (`ObterXMLSolicitacoesv2_WSReq`) — medido
    # no WSDL de produção em 11/10/2026.
    req = {"LoginUsuarioCertificado": "Login_WSReq",
           "ObterXMLSolicitacoes_v6": "ObterXMLSolicitacoesv2_WSReq"}
    for metodo, campos in W.CAMPOS.items():
        nome = req.get(metodo, f"{metodo}_WSReq")
        assert tipos[nome] == campos, metodo


@pytest.mark.skipif(not CONTRATO.is_dir(), reason="o contrato não está nesta árvore")
def test_o_endereco_de_producao_e_o_do_contrato():
    for chave, asmx in W.SERVICOS.items():
        texto = (CONTRATO / asmx.replace(".asmx", ".wsdl")).read_text(encoding="utf-8")
        assert f'location="{W.BASE[W.PRODUCAO]}/{asmx}"' in texto, chave


#: CONTRATO MUDADO EM 11/10/2026, por ordem do oficial («faça a da onr
#: certidões»): o módulo passou a RESPONDER as certidões a emitir. Só elas — o
#: teste continua recusando qualquer outra operação que não seja leitura.
RESPONDEM_CERTIDAO = {"ObterXMLSolicitacoes_v6", "InformarCustasCertidao", "EnviarAnexoCertidao",
                      "EnviarAnexosListCertidao", "FinalizarRespostaCertidao", "DevolverCertidao"}


def test_so_le_salvo_as_certidoes():
    for metodo in W.CAMPOS:
        assert re.match(r"^(Login|List|Get)", metodo) or metodo in RESPONDEM_CERTIDAO, metodo
    assert all(W.SERVICO_DO_METODO[m] == "certidoes" for m in RESPONDEM_CERTIDAO)


# -------------------------------------------------------------- hash e envelope

def test_hash_e_sha1_da_chave_mais_o_token():
    assert W.hash_da_mensagem("ab", "c") == "A9993E364706816ABA3E25717850C26C9CD0D89D"
    assert W.hash_da_mensagem("ab", "c", maiusculas=False) == \
        "a9993e364706816aba3e25717850c26c9cd0d89d"


def test_envelope_na_ordem_e_recusa_campo_que_nao_existe():
    xml = W.envelope("GetPedidoPO", {"IDPedido": 5, "Hash": "H<&"}).decode()
    assert xml.index("<Hash>") < xml.index("<IDPedido>")
    assert "H&lt;&amp;" in xml
    assert f'<GetPedidoPO xmlns="{W.NS}"><oRequest>' in xml
    with pytest.raises(W.WSOficioError):
        W.envelope("GetPedidoPO", {"Hash": "x", "Pedido": 1})


def test_os_dados_do_login_respeitam_o_manual():
    ok = W.dados_do_login(cpf="000.000.044-21", email="a@b", id_parceiro="2869",
                          certificado=CERT)
    assert ok["CPF"] == "00000004421" and ok["ISSUERO"] == "ICP-Brasil"
    with pytest.raises(W.WSOficioError):
        W.dados_do_login(cpf="123", email="a@b", id_parceiro="2869", certificado=CERT)
    with pytest.raises(W.WSOficioError):
        W.dados_do_login(cpf="00000004421", email="a@b", id_parceiro="2869",
                         certificado=dict(CERT, ISSUERO="ICP-Brasil-X"))


# ------------------------------------------------------------------ a sessão

def test_entra_le_e_cada_chamada_gasta_um_token(pasta):
    onr = ONRDeMentira()
    s = _sessao(pasta, onr)
    r = s.pedidos_de_penhora(de="2026-09-01", ate="2026-10-09")
    assert r["QtdeRegistros"] == "1"
    (p,) = r["Pedidos"]
    assert p["IDPedido"] == "123" and p["Vara"] == "1ª Vara"
    assert s.usuario["IDInstituicao"] == "99" and s.maiusculas is True
    s.pedidos_de_oficio(de="2026-09-01", ate="2026-10-09")
    assert len(onr.usados) == 2
    assert [c[1] for c in onr.chamadas].count("LoginUsuarioCertificado") == 1
    assert onr.chamadas[1][0] == "https://wsoficio.onr.org.br/penhoraonline.asmx"
    assert "IDParceiroWS>2869<" in onr.chamadas[0][2] and CHAVE not in onr.chamadas[0][2]


def test_a_chave_nunca_viaja(pasta):
    onr = ONRDeMentira()
    s = _sessao(pasta, onr)
    s.pedidos_de_oficio(de="2026-09-01", ate="2026-10-09")
    assert all(CHAVE not in xml for _, _, xml in onr.chamadas)


def test_acaba_os_tokens_e_entra_de_novo(pasta):
    onr = ONRDeMentira()
    s = _sessao(pasta, onr)
    for _ in range(6):
        s.pedido_de_penhora(1)
    assert [c[1] for c in onr.chamadas].count("LoginUsuarioCertificado") == 2


def test_se_o_onr_quiser_minusculas_tenta_uma_vez_e_guarda(pasta):
    onr = ONRDeMentira(aceita_maiusculas=False)
    s = _sessao(pasta, onr)
    s.pedido_de_penhora(1)
    assert s.maiusculas is False
    s.pedido_de_penhora(2)
    assert len([c for c in onr.chamadas if c[1] == "GetPedidoPO"]) == 3   # 1 tentativa a mais, só


def test_hash_ja_utilizado_nao_e_caixa_errada(pasta, monkeypatch):
    onr = ONRDeMentira()
    s = _sessao(pasta, onr)
    s.entrar()
    repetido = s._tokens[0]
    onr.usados.add(repetido)
    with pytest.raises(W.WSOficioRecusou) as e:
        s.pedido_de_penhora(1)
    assert e.value.codigo == "46"
    assert len([c for c in onr.chamadas if c[1] == "GetPedidoPO"]) == 1


def test_login_recusado_diz_o_codigo(pasta):
    def recusa(url, corpo, acao):
        return 200, _soap("LoginUsuarioCertificado",
                          "<RETORNO>false</RETORNO><CODIGOERRO>51</CODIGOERRO>"
                          "<ERRODESCRICAO>Usuário não encontrado.</ERRODESCRICAO>")
    with pytest.raises(W.WSOficioRecusou) as e:
        W.Sessao(pasta=pasta, transporte=recusa, certificado=CERT).entrar()
    assert e.value.codigo == "51" and "não encontrado" in str(e.value)


def test_falha_soap_vira_frase(pasta):
    def falha(url, corpo, acao):
        return 500, ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                     '<soap:Body><soap:Fault><faultstring>Acesso negado para o IP'
                     '</faultstring></soap:Fault></soap:Body></soap:Envelope>')
    with pytest.raises(W.WSOficioError, match="Acesso negado para o IP"):
        W.Sessao(pasta=pasta, transporte=falha, certificado=CERT).entrar()


# ------------------------------------------------------------- a credencial

def test_sem_usuario_do_oficio_eletronico_nao_entra(tmp_path):
    W.configurar(pasta=tmp_path, id_parceiro="2869", chave=CHAVE)
    with pytest.raises(W.WSOficioError, match="CPF e o e-mail"):
        W.Sessao(pasta=tmp_path, transporte=ONRDeMentira(), certificado=CERT)


def test_situacao_nao_devolve_a_chave(pasta):
    s = W.situacao(pasta=pasta)
    assert s["tem_chave"] is True and CHAVE not in json.dumps(s)


def test_traz_do_onr_cred_so_o_par_com_a_forma_do_wsoficio(tmp_path):
    onr = tmp_path / "onr.cred"
    onr.write_text(json.dumps({"PRODUCAO": {"usuario": "2869", "senha": CHAVE}}),
                   encoding="utf-8")
    assert W.trazer_do_onr_cred(tmp_path) is True
    assert W.situacao(pasta=tmp_path)["id_parceiro"] == "2869"
    assert json.loads(onr.read_text(encoding="utf-8"))["PRODUCAO"]["usuario"] == "2869"
    outro = tmp_path / "b"
    outro.mkdir()
    (outro / "onr.cred").write_text(json.dumps(
        {"PRODUCAO": {"usuario": "abc-client", "senha": "segredo"}}), encoding="utf-8")
    assert W.trazer_do_onr_cred(outro) is False

# -*- coding: utf-8 -*-
"""O transporte do WSOfício para o e-Protocolo, a e-Intimação e a matrícula
online — RI013 B0, 25/11/2026.

O QUE ESTES TESTES GUARDAM
    **Todo método dos três WSDLs está em `CAMPOS`**, no serviço certo, com o
    nome do tipo e os campos NA ORDEM do WSDL — e nada além deles.
    **O envelope de cada método valida contra o esquema do WSDL** (lxml, XSD),
    com listas de dois itens, base64, datas e decimais; e o dos `pedido_*`
    também.
    **As escritas não saem**: `Sessao.chamar` recusa todo método que espera o
    «pode» do titular, antes do login, e nenhum módulo da casa as monta.
    **As respostas de leitura da e-Intimação** se leem com os nomes do WSDL, a
    lista como lista (vazia, de um ou de vários) e o número no tipo dele.
    **Nenhuma rede**: o transporte é um ONR de mentira.

DE ONDE VEM O CONTRATO
    Do WSDL de produção em `FONTES_EXTERNAS/onr_wsoficio/producao`, dois níveis
    acima do repositório, quando ele está lá (o padrão da P1); senão, da cópia
    mínima e pública em `tests/fixtures/onr_wsoficio` — e, quando os dois
    existem, há teste que diz que a cópia não se afastou do original.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_wsoficio as W                                           # noqa: E402

CONTRATO = RAIZ.parent.parent / "FONTES_EXTERNAS" / "onr_wsoficio" / "producao"
COPIA = Path(__file__).resolve().parent / "fixtures" / "onr_wsoficio"
X = "{http://www.w3.org/2001/XMLSchema}"
WS = "{http://schemas.xmlsoap.org/wsdl/}"
SOAP_WSDL = "{http://schemas.xmlsoap.org/wsdl/soap/}"
CHAVE = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"
CERT = {"SUBJECTCN": "FULANO DE TAL:00000004421", "ISSUERO": "ICP-Brasil",
        "PUBLICKEY": "3082010A0282010100AB", "SERIALNUMBER": "763222E368FD67A9",
        "VALIDUNTIL": "08/01/2028 16:10:00"}

#: serviço do módulo → arquivo do WSDL, e quantos métodos ele tem.
SERVICOS_B0 = {"eprotocolo": ("eprotocolo.wsdl", 30), "intimacoes": ("intimacoes.wsdl", 14),
               "matricula": ("matriculaonline.wsdl", 2)}
#: As leituras que não começam por List/Get.
LEITURAS_SEM_PREFIXO = {"ContratoXMLtoPDF", "ObterXmlSolicitacoes", "ObterXmlSolicitacoesV2"}


def _wsdl(servico: str) -> Path:
    arq = SERVICOS_B0[servico][0]
    return CONTRATO / arq if (CONTRATO / arq).is_file() else COPIA / arq


class Contrato:
    """O que os testes leem de um WSDL."""

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self.raiz = ET.parse(caminho).getroot()
        self.tipos = {ct.get("name"): ct for ct in self.raiz.iter(X + "complexType")
                      if ct.get("name")}
        self.elementos = {el.get("name"): el for sch in self.raiz.iter(X + "schema")
                          for el in sch.findall(X + "element")}
        self.operacoes = [o.get("name") for o in
                          self.raiz.find(WS + "portType").findall(WS + "operation")]

    def sequencia(self, tipo: str) -> list[ET.Element]:
        seq = self.tipos[tipo].find(X + "sequence")
        return [] if seq is None else seq.findall(X + "element")

    def campos(self, tipo: str) -> tuple:
        return tuple(e.get("name") for e in self.sequencia(tipo))

    def tipo_do_pedido(self, metodo: str) -> str:
        interno = self.elementos[metodo].find(f"{X}complexType/{X}sequence/{X}element")
        assert interno.get("name") == "oRequest", metodo
        return interno.get("type").split(":")[-1]

    def tipo_da_resposta(self, metodo: str) -> str:
        interno = self.elementos[metodo + "Response"].find(
            f"{X}complexType/{X}sequence/{X}element")
        assert interno.get("name") == metodo + "Result", metodo
        return interno.get("type").split(":")[-1]


@pytest.fixture(scope="module", params=sorted(SERVICOS_B0))
def contrato(request):
    return request.param, Contrato(_wsdl(request.param))


def _tipo(e: ET.Element) -> str:
    return (e.get("type") or "").split(":")[-1]


# ------------------------------------------------------------------ o contrato

def test_todo_metodo_do_wsdl_esta_em_campos_na_ordem(contrato):
    servico, c = contrato
    assert len(c.operacoes) == SERVICOS_B0[servico][1]
    for m in c.operacoes:
        assert W.SERVICO_DO_METODO.get(m) == servico, m
        tipo = c.tipo_do_pedido(m)
        assert W.TIPO_DO_PEDIDO_NO_WSDL.get(m, f"{m}_WSReq") == tipo, m
        assert W.CAMPOS[m] == c.campos(tipo), m
    assert {m for m, s in W.SERVICO_DO_METODO.items() if s == servico} == set(c.operacoes)
    assert f'location="{W.BASE[W.PRODUCAO]}/{W.SERVICOS[servico]}"' in \
        c.caminho.read_text(encoding="utf-8")


def test_a_soapaction_e_a_que_o_cliente_manda(contrato):
    _, c = contrato
    ligacao = next(b for b in c.raiz.findall(WS + "binding")
                   if b.find(SOAP_WSDL + "binding") is not None)
    acoes = {o.get("name"): o.find(SOAP_WSDL + "operation").get("soapAction")
             for o in ligacao.findall(WS + "operation")}
    assert acoes == {m: f"{W.NS}/{m}" for m in c.operacoes}


def test_cada_lista_do_pedido_esta_declarada_com_o_item_do_wsdl(contrato):
    _, c = contrato
    for m in c.operacoes:
        for e in c.sequencia(c.tipo_do_pedido(m)):
            if not _tipo(e).startswith("ArrayOf"):
                assert (m, e.get("name")) not in W.LISTAS_DO_METODO
                continue
            item = c.sequencia(_tipo(e))[0]
            assert item.get("maxOccurs") == "unbounded"
            declarado = W.LISTAS_DO_METODO[(m, e.get("name"))]
            campos_do_item = c.campos(_tipo(item)) if _tipo(item) in c.tipos else None
            assert declarado == (item.get("name"), campos_do_item), (m, e.get("name"))


def test_nenhum_nome_de_metodo_se_repete_entre_servicos():
    vistos = {}
    for servico in SERVICOS_B0:
        for m in Contrato(_wsdl(servico)).operacoes:
            assert m not in vistos, (m, servico, vistos.get(m))
            vistos[m] = servico


@pytest.mark.skipif(not CONTRATO.is_dir(), reason="o contrato não está nesta árvore")
@pytest.mark.parametrize("servico", sorted(SERVICOS_B0))
def test_a_copia_dos_testes_e_a_do_contrato(servico):
    arq = SERVICOS_B0[servico][0]
    if not (CONTRATO / arq).is_file():
        pytest.skip(f"{arq} não está no contrato")
    original, copia = Contrato(CONTRATO / arq), Contrato(COPIA / arq)
    assert original.operacoes == copia.operacoes
    assert {n: ET.tostring(t) for n, t in original.tipos.items()} == \
        {n: ET.tostring(t) for n, t in copia.tipos.items()}
    sha = hashlib.sha256((CONTRATO / arq).read_bytes()).hexdigest()
    assert sha in (COPIA / arq).read_text(encoding="utf-8")


# ------------------------------------------------- o envelope contra o esquema

try:                                                    # requirements-test.txt
    from lxml import etree as lxml_etree
except ImportError:                                     # pragma: no cover
    lxml_etree = None
precisa_lxml = pytest.mark.skipif(lxml_etree is None, reason="sem lxml não há validação XSD")


def _esquema(c: Contrato):
    raiz = lxml_etree.parse(str(c.caminho))
    (sch,) = raiz.getroot().iter("{http://www.w3.org/2001/XMLSchema}schema")
    return lxml_etree.XMLSchema(lxml_etree.fromstring(lxml_etree.tostring(sch)))


def _validar(esquema, corpo: bytes):
    raiz = lxml_etree.fromstring(corpo)
    corpo_soap = raiz.find(f"{{{W.SOAP}}}Body")
    (metodo,) = list(corpo_soap)
    if not esquema.validate(lxml_etree.ElementTree(metodo)):
        raise AssertionError(str(esquema.error_log))


def _exemplo(servico: str, nome: str, tipo: str):
    """Um valor de exemplo para o campo — o tipo Python que o cliente recebe."""
    if tipo == "int":
        return 7
    if tipo == "boolean":
        return True
    if tipo == "decimal":
        return Decimal("123.456")
    if nome in W.CAMPOS_BASE64:
        return b"%PDF-1.4 exemplo"
    if nome.startswith("Valor"):
        return Decimal("10.5")
    if servico in W.SERVICOS_COM_DATA_ISO and re.search(r"^Data|Vencimento", nome):
        return datetime(2026, 11, 25, 9, 30) if nome == "DataPagamento" else date(2026, 11, 25)
    return f"{nome}-exemplo <&>"


def _campos_de_exemplo(servico: str, c: Contrato, metodo: str, itens: int = 2) -> dict:
    campos = {}
    for e in c.sequencia(c.tipo_do_pedido(metodo)):
        nome, tipo = e.get("name"), _tipo(e)
        if tipo.startswith("ArrayOf"):
            item = c.sequencia(tipo)[0]
            if _tipo(item) in c.tipos:
                campos[nome] = [{s.get("name"): _exemplo(servico, s.get("name"), _tipo(s))
                                 for s in c.sequencia(_tipo(item))} for _ in range(itens)]
            else:
                campos[nome] = [f"https://site-exemplo.invalid/{i}.pdf" for i in range(itens)]
        else:
            campos[nome] = _exemplo(servico, nome, tipo)
    return campos


@precisa_lxml
def test_o_envelope_de_cada_metodo_valida_contra_o_wsdl(contrato):
    servico, c = contrato
    esquema = _esquema(c)
    for m in c.operacoes:
        for itens in (0, 1, 2):
            _validar(esquema, W.envelope(m, _campos_de_exemplo(servico, c, m, itens)))


@precisa_lxml
def test_o_envelope_so_com_os_obrigatorios_valida(contrato):
    """Os campos `minOccurs=0` podem faltar; os `minOccurs=1` (int, bool,
    decimal) nunca — este teste mostra que sem eles o esquema recusa, que é o
    que obriga os `pedido_*` a mandá-los."""
    servico, c = contrato
    esquema = _esquema(c)
    for m in c.operacoes:
        tipo = c.tipo_do_pedido(m)
        obrigatorios = {e.get("name") for e in c.sequencia(tipo) if e.get("minOccurs") == "1"}
        campos = {k: v for k, v in _campos_de_exemplo(servico, c, m).items() if k in obrigatorios}
        _validar(esquema, W.envelope(m, campos))
        if obrigatorios:
            sem_um = dict(campos)
            sem_um.pop(sorted(obrigatorios)[0])
            with pytest.raises(AssertionError):
                _validar(esquema, W.envelope(m, sem_um))


def _pedidos_das_escritas():
    return {
        "SetPrenotacaoAC": W.pedido_prenotacao_ac(10, numero="1234", data=date(2026, 11, 25),
                                                  vencimento=date(2026, 12, 16)),
        "SetPrenotacaoExameCalculoAC": W.pedido_prenotacao_exame_calculo_ac(
            10, numero="1234", data="2026-11-25", senha="ABC123"),
        "SetProrrogarPrenotacaoAC": W.pedido_prorrogar_prenotacao_ac(10, motivo="Exigência"),
        "SetCustasAC": W.pedido_custas_ac(10, "187.4"),
        "SetCustasComplementarAC": W.pedido_custas_ac(10, Decimal("12"), complementar=True),
        "SetContratoExigenciaAC": W.pedido_exigencia_ac(
            10, resposta="Falta a CND.", anexos=[{"nome": "nota.pdf",
                                                  "url": "https://site-exemplo.invalid/n.pdf"}]),
        "SetContratoExigenciaAC_DocID": W.pedido_exigencia_ac(
            10, resposta="Falta a CND.", final=True, por_document_id=True,
            anexos=[{"Nome": "nota.pdf", "DocumentID": "DOC-1"}]),
        "SetContratoCumprimentoExigenciaRI": W.pedido_cumprimento_exigencia_ri(10),
        "SetContratoAverbadoAC": W.pedido_averbado_ac(
            10, resposta="Registrado.", certidoes=[
                {"descricao": "XMLRETORNO", "url": "https://site-exemplo.invalid/r.xml"},
                {"descricao": "Certidão", "url": "https://site-exemplo.invalid/c.pdf"}]),
        "SetContratoAverbadoAC_DocID": W.pedido_averbado_ac(
            10, resposta="Registrado.", por_document_id=True,
            certidoes=[{"Descricao": "Certidão", "DocumentID": "DOC-2"}]),
        "SetContratoDevolvidoAC": W.pedido_devolvido_ac(10, resposta="Fora da circunscrição."),
        "SetFinalizarProtocoloAC": W.pedido_finalizar_protocolo_ac(
            10, resposta="Finalizado.", anexos=[{"nome": "certidao.pdf", "conteudo": b"%PDF"}]),
        "SetBaixaBoletoAC": W.pedido_baixa_boleto_ac(55, convenio=False),
        "SetBaixaCustasAC": W.pedido_baixa_custas_ac(56),
        "AlterarPedidoAC": W.pedido_alterar_ac(10, ApresentanteNome="Fulano de Tal",
                                               EnderecoUF="SP"),
        "ImportarPrenotacaoIN": W.pedido_importar_prenotacao_in(
            ["https://site-exemplo.invalid/p1.xml", "https://site-exemplo.invalid/p2.xml"]),
        "AdicionarMensagemIN": W.pedido_mensagem_in(
            20, status=4, assunto="Prenotado", mensagem="Prenotado sob o nº 1234.",
            numero_prenotacao="1234", data_prenotacao=datetime(2026, 11, 25, 10, 0),
            vencimento_prenotacao=date(2026, 12, 16), valor_prenotacao="45.10",
            destinacao_mutuo=3, urls_anexos=["https://site-exemplo.invalid/a.pdf"]),
        "AdicionarEmolumentoIN": W.pedido_emolumento_in(20, tipo=3, descricao="Intimação",
                                                         valor="30"),
        "ExcluirEmolumentoIN": W.pedido_excluir_emolumento_in(77),
        "CancelamentoJudicialIN": W.pedido_cancelamento_judicial_in(
            20, data_averbacao=date(2026, 11, 25)),
    }


@precisa_lxml
def test_cada_escrita_tem_o_seu_pedido_e_ele_valida_contra_o_wsdl():
    pedidos = _pedidos_das_escritas()
    assert set(pedidos) == set(W.ESPERAM_O_PODE_DO_TITULAR)
    esquemas = {s: _esquema(Contrato(_wsdl(s))) for s in ("eprotocolo", "intimacoes")}
    for metodo, p in pedidos.items():
        assert p.metodo == metodo
        assert "Hash" not in p.campos
        _validar(esquemas[W.SERVICO_DO_METODO[metodo]], p.envelope("HASH"))


# ------------------------------------------------------- listas, base64 e datas

def _req(corpo: bytes, metodo: str) -> ET.Element:
    return ET.fromstring(corpo).find(f".//{{{W.NS}}}{metodo}/{{{W.NS}}}oRequest")


def _filhos(el):
    return [(f.tag.rsplit("}", 1)[-1], f.text) for f in el]


def test_a_lista_aninhada_vai_item_a_item_na_ordem_do_tipo():
    corpo = W.envelope("SetContratoExigenciaAC", {
        "IDContrato": 1, "ExigenciaFinal": False, "Resposta": "r",
        "Anexos": [{"URLArquivo": "https://site-exemplo.invalid/a", "Nome": "a.pdf"}, None,
                   {"Nome": "b.pdf"}]})
    anexos = _req(corpo, "SetContratoExigenciaAC").find(f"{{{W.NS}}}Anexos")
    itens = list(anexos)
    assert [i.tag.rsplit("}", 1)[-1] for i in itens] == ["SetContratoExigenciaAC_Anexo_WSReq"] * 2
    assert _filhos(itens[0]) == [("Nome", "a.pdf"), ("URLArquivo", "https://site-exemplo.invalid/a")]
    assert _filhos(itens[1]) == [("Nome", "b.pdf")]
    with pytest.raises(W.WSOficioError, match="Descricao"):
        W.envelope("SetContratoExigenciaAC", {"Anexos": [{"Descricao": "x"}]})
    with pytest.raises(W.WSOficioError, match="lista"):
        W.envelope("SetContratoExigenciaAC", {"Anexos": {"Nome": "x"}})
    with pytest.raises(W.WSOficioError, match="lista nem tipo"):
        W.envelope("SetCustasAC", {"ValorCustas": [1]})


def test_a_lista_de_texto_vai_em_string():
    corpo = W.envelope("AdicionarMensagemIN", {"URLAnexos": ["https://site-exemplo.invalid/1",
                                                            "https://site-exemplo.invalid/2"]})
    urls = _req(corpo, "AdicionarMensagemIN").find(f"{{{W.NS}}}URLAnexos")
    assert _filhos(urls) == [("string", "https://site-exemplo.invalid/1"),
                             ("string", "https://site-exemplo.invalid/2")]
    with pytest.raises(W.WSOficioError):
        W.envelope("AdicionarMensagemIN", {"URLAnexos": "https://site-exemplo.invalid/1"})


def test_bytes_viram_base64_so_no_campo_do_arquivo():
    corpo = W.envelope("SetFinalizarProtocoloAC", {
        "IDContrato": 1, "Anexos": [{"NomeArquivo": "a.pdf", "ArquivoBase64": b"\x00\xffPDF"}]})
    item = _req(corpo, "SetFinalizarProtocoloAC").find(f".//{{{W.NS}}}ArquivoBase64")
    assert base64.b64decode(item.text) == b"\x00\xffPDF"
    texto = W.envelope("SetFinalizarProtocoloAC", {
        "Anexos": [{"NomeArquivo": "a.pdf", "ArquivoBase64": "QUJD"}]}).decode()
    assert "<ArquivoBase64>QUJD</ArquivoBase64>" in texto
    with pytest.raises(W.WSOficioError, match="não leva arquivo"):
        W.envelope("SetContratoDevolvidoAC", {"Resposta": b"x"})


def test_as_datas_e_os_valores_no_formato_do_manual():
    p = W.pedido_mensagem_in(1, status=14, assunto="a", mensagem="m",
                             data_pagamento=date(2026, 11, 25), valor_pagamento=Decimal("7.005"))
    req = dict(_filhos(_req(p.envelope(), "AdicionarMensagemIN")))
    assert req["DataPagamento"] == "2026-11-25 00:00:00"
    assert req["ValorPagamento"] == "7.01"
    p = W.pedido_prenotacao_ac(1, numero="9", data=datetime(2026, 11, 25, 23, 59),
                               vencimento="2026-12-16")
    req = dict(_filhos(_req(p.envelope(), "SetPrenotacaoAC")))
    assert (req["DataPrenotacao"], req["DataVencimento"]) == ("2026-11-25", "2026-12-16")
    assert "Senha" not in req
    assert W.envelope("SetCustasAC", {"ValorCustas": 12.3}).decode().count("<ValorCustas>12.30<")
    # Onde o formato não foi conferido, objeto de data é recusado.
    with pytest.raises(W.WSOficioError, match="não foi conferido"):
        W.envelope("ListTitulosAT", {"DataProtocoloInicio": date(2026, 11, 25)})
    with pytest.raises(W.WSOficioError):
        W.envelope("SetCustasAC", {"ValorCustas": Decimal("NaN")})


def test_os_pedidos_recusam_o_que_o_manual_recusa():
    with pytest.raises(W.WSOficioError, match="prenotado"):
        W.pedido_mensagem_in(1, status=4, assunto="a", mensagem="m")
    with pytest.raises(W.WSOficioError, match="3.11.15"):
        W.pedido_mensagem_in(1, status=99, assunto="a", mensagem="m")
    with pytest.raises(W.WSOficioError, match="12"):
        W.pedido_importar_prenotacao_in([])
    with pytest.raises(W.WSOficioError, match="3.11.17"):
        W.pedido_emolumento_in(1, tipo=9, descricao="x", valor="1")
    with pytest.raises(W.WSOficioError, match="nome e conteúdo"):
        W.pedido_finalizar_protocolo_ac(1, anexos=[{"nome": "a.pdf"}])
    with pytest.raises(W.WSOficioError, match="não tem o"):
        W.pedido_exigencia_ac(1, resposta="r", anexos=[{"nome": "a", "arquivo": "b"}])
    with pytest.raises(W.WSOficioError):
        W.pedido_alterar_ac(1, Apresentante="x")


# ------------------------------------------------------- as escritas não saem

class ONRDeMentira:
    """Confere o hash e responde a leitura com o corpo que o teste der."""

    def __init__(self, respostas: dict | None = None):
        self.respostas = dict(respostas or {})
        self.emitidos, self.chamadas = [], []

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
        assert any(hashlib.sha1((CHAVE + t).encode()).hexdigest().upper() == h
                   for t in self.emitidos)
        return 200, _soap(metodo, self.respostas.get(metodo, "<RETORNO>true</RETORNO>"))


def _soap(metodo: str, corpo: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap='
            '"http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            f'<{metodo}Response xmlns="{W.NS}"><{metodo}Result>{corpo}</{metodo}Result>'
            f'</{metodo}Response></soap:Body></soap:Envelope>')


@pytest.fixture()
def pasta(tmp_path):
    W.configurar(pasta=tmp_path, id_parceiro="2869", chave=CHAVE, cpf="000.000.044-21",
                 email="oficial@exemplo.org")
    return tmp_path


def test_a_sessao_recusa_toda_escrita_antes_de_ir_a_rede(pasta):
    onr = ONRDeMentira()
    s = W.Sessao(pasta=pasta, transporte=onr, certificado=CERT)
    for metodo, p in _pedidos_das_escritas().items():
        with pytest.raises(W.WSOficioError, match="«pode» do titular"):
            s.chamar(metodo, **p.campos)
    assert onr.chamadas == []


def test_so_as_escritas_estao_presas_e_todas_estao(contrato):
    servico, c = contrato
    for m in c.operacoes:
        leitura = bool(re.match(r"^(List|Get)", m)) or m in LEITURAS_SEM_PREFIXO
        assert (m in W.ESPERAM_O_PODE_DO_TITULAR) is (not leitura), m


def _o_que_o_codigo_usa(texto: str):
    """Os nomes e os textos que o código USA: nomes, atributos, importações e
    textos fora das docstrings. Comentário e docstring são prosa — dizer «a P2a
    não manda o `SetPrenotacaoAC`» não é chamá-lo (27/11/2026, #534)."""
    arvore = ast.parse(texto)
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and no.body and isinstance(no.body[0], ast.Expr) \
                and isinstance(no.body[0].value, ast.Constant) \
                and isinstance(no.body[0].value.value, str):
            docstrings.add(id(no.body[0].value))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            yield no.id
        elif isinstance(no, ast.Attribute):
            yield no.attr
        elif isinstance(no, ast.alias):
            yield no.asname or no.name
            yield no.name.rsplit(".", 1)[-1]
        elif isinstance(no, ast.Constant) and isinstance(no.value, str) \
                and id(no) not in docstrings:
            yield no.value


def test_nenhum_modulo_da_casa_monta_ou_chama_uma_escrita():
    """«Nenhuma rodada, processo, botão ou tela os chama» — até a etapa que
    ganhar o «pode» do titular mudar este teste no mesmo PR."""
    nomes = sorted(W.ESPERAM_O_PODE_DO_TITULAR, key=len, reverse=True)
    funcoes = sorted(n for n in dir(W) if n.startswith("pedido_"))
    padrao = re.compile(r"\b(" + "|".join(map(re.escape, nomes + funcoes)) + r")\b")
    achados = []
    for arq in RAIZ.rglob("*.py"):
        rel = arq.relative_to(RAIZ)
        if rel.parts[0] in ("tests", ".git", "venv", ".venv") or arq.name == "onr_wsoficio.py":
            continue
        try:
            usados = list(_o_que_o_codigo_usa(arq.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        achados += [f"{rel}: {m.group(1)}" for u in usados for m in padrao.finditer(u)]
    assert achados == []


def test_o_varredor_ve_a_chamada_e_ignora_a_prosa():
    """A régua do teste acima: prosa não conta, chamada conta."""
    prosa = '''"""A P2a não manda o `SetPrenotacaoAC`."""
# nem o SetPrenotacaoAC aqui
def f():
    """Nem pedido_prenotacao_ac."""
    return 1
'''
    assert not any("SetPrenotacaoAC" in u or "pedido_prenotacao_ac" in u
                   for u in _o_que_o_codigo_usa(prosa))
    for chamada in ('s.chamar("SetPrenotacaoAC")', "W.pedido_prenotacao_ac()",
                    "from onr_wsoficio import pedido_prenotacao_ac"):
        assert any(re.search(r"\b(SetPrenotacaoAC|pedido_prenotacao_ac)\b", u)
                   for u in _o_que_o_codigo_usa(chamada)), chamada


# ----------------------------------------- as respostas de leitura da e-Intimação

INTIMACOES = Contrato(_wsdl("intimacoes"))


def _xml_de_exemplo(c: Contrato, tipo: str, itens: int) -> str:
    """O corpo de uma resposta, montado do tipo do WSDL com valores de mentira."""
    partes = []
    for e in c.sequencia(tipo):
        nome, t = e.get("name"), _tipo(e)
        if t.startswith("ArrayOf"):
            item = c.sequencia(t)[0]
            filhos = "".join(f"<{item.get('name')}>{_xml_de_exemplo(c, _tipo(item), itens)}"
                             f"</{item.get('name')}>" for _ in range(itens))
            partes.append(f"<{nome}>{filhos}</{nome}>")
        elif t in c.tipos:
            partes.append(f"<{nome}>{_xml_de_exemplo(c, t, itens)}</{nome}>")
        else:
            valor = {"int": "42", "boolean": "true", "decimal": "1234.56"}.get(
                t, f"{nome}-exemplo")
            if nome == "RETORNO":
                valor = "true"
            partes.append(f"<{nome}>{valor}</{nome}>")
    return "".join(partes)


@pytest.mark.parametrize("metodo", ["ListPedidosIN", "GetDetalhesIN_V3", "ListPagamentoIN"])
def test_os_nomes_que_o_leitor_usa_sao_os_do_wsdl(metodo):
    c = INTIMACOES
    tipo = c.tipo_da_resposta(metodo)
    campos = {e.get("name"): e for e in c.sequencia(tipo)}
    if metodo == "GetDetalhesIN_V3":
        assert set(W.CAMPOS_DO_DETALHE_IN) <= set(campos)
        for quem in ("Solicitante", "Credor"):
            assert {quem + s for s in W.SUFIXOS_DE_PESSOA_IN} <= set(campos)
        assert {"PrestacaoAgencia", "PrestacaoEndereco"} <= set(campos)
        for lista, itens in W.LISTAS_DO_DETALHE_IN.items():
            item = c.sequencia(_tipo(campos[lista]))[0]
            assert c.campos(_tipo(item)) == itens, lista
        # Tudo o que a v3 traz o leitor lê — nada fica para trás.
        lidos = (set(W.CAMPOS_DO_DETALHE_IN) | set(W.LISTAS_DO_DETALHE_IN)
                 | {q + s for q in ("Solicitante", "Credor") for s in W.SUFIXOS_DE_PESSOA_IN}
                 | {"PrestacaoAgencia", "PrestacaoEndereco", "RETORNO", "CODIGOERRO",
                    "ERRODESCRICAO"})
        assert set(campos) == lidos
    else:
        lista = "Pedidos" if metodo == "ListPedidosIN" else "Pagamentos"
        item = c.sequencia(_tipo(campos[lista]))[0]
        esperado = W.CAMPOS_DO_PEDIDO_IN if metodo == "ListPedidosIN" else W.CAMPOS_DO_PAGAMENTO_IN
        assert c.campos(_tipo(item)) == esperado


def test_os_tipos_numericos_do_leitor_cobrem_os_do_wsdl():
    c = INTIMACOES
    vistos = {"int": set(), "decimal": set(), "boolean": set()}

    def varrer(tipo, ja=frozenset()):
        if tipo in ja:
            return
        for e in c.sequencia(tipo):
            t = _tipo(e)
            if t in vistos:
                vistos[t].add(e.get("name"))
            elif t in c.tipos:
                varrer(t, ja | {tipo})
    for m in ("ListPedidosIN", "GetDetalhesIN_V3", "ListPagamentoIN"):
        varrer(c.tipo_da_resposta(m))
    assert vistos["int"] <= W.INTEIROS_IN
    assert vistos["decimal"] <= W.DECIMAIS_IN
    assert vistos["boolean"] <= W.BOOLEANOS_IN


@pytest.mark.parametrize("itens", [0, 1, 2])
def test_a_ficha_da_intimacao_se_le_com_qualquer_tamanho_de_lista(pasta, itens):
    corpo = _xml_de_exemplo(INTIMACOES, INTIMACOES.tipo_da_resposta("GetDetalhesIN_V3"), itens)
    onr = ONRDeMentira({"GetDetalhesIN_V3": corpo})
    ficha = W.Sessao(pasta=pasta, transporte=onr, certificado=CERT).detalhes_da_intimacao(9)
    assert [m for _, m, _ in onr.chamadas] == ["LoginUsuarioCertificado", "GetDetalhesIN_V3"]
    assert "<IDPedido>9</IDPedido>" in onr.chamadas[-1][2]
    assert ficha["IDPedido"] == 42 and ficha["TipoCobranca"] == 42
    assert ficha["Protocolo"] == "Protocolo-exemplo"
    assert ficha["credor"]["Nome"] == "Credor-exemplo"
    assert ficha["credor"]["CPFCNPJ"] == "CredorCPFCNPJ-exemplo"
    assert ficha["solicitante"]["Email"] == "SolicitanteEmail-exemplo"
    assert ficha["prestacao"] == {"Agencia": "PrestacaoAgencia-exemplo",
                                  "Endereco": "PrestacaoEndereco-exemplo"}
    for lista in W.LISTAS_DO_DETALHE_IN:
        assert isinstance(ficha[lista], list) and len(ficha[lista]) == itens, lista
    if itens:
        assert ficha["Devedores"][0] == {"Nome": "Nome-exemplo",
                                         "Participacao": "Participacao-exemplo",
                                         "CPFCNPJ": "CPFCNPJ-exemplo", "Email": "Email-exemplo"}
        assert ficha["Imoveis"][0] == {"Matricula": "Matricula-exemplo"}
        assert ficha["PrestacoesVencidas"][0]["Valor"] == Decimal("1234.56")
        assert ficha["Prenotacoes"][0]["ValorServico"] == Decimal("1234.56")
        assert ficha["Purgas"][-1]["DataVencimento"] == "DataVencimento-exemplo"


@pytest.mark.parametrize("itens", [0, 1, 2])
def test_as_listagens_da_intimacao_se_leem(pasta, itens):
    respostas = {m: _xml_de_exemplo(INTIMACOES, INTIMACOES.tipo_da_resposta(m), itens)
                 for m in ("ListPedidosIN", "ListPagamentoIN")}
    onr = ONRDeMentira(respostas)
    s = W.Sessao(pasta=pasta, transporte=onr, certificado=CERT)
    r = s.pedidos_da_intimacao(de=date(2026, 11, 1), ate="2026-11-25", por_pagina=3)
    assert r["qtde_registros"] == 42 and len(r["pedidos"]) == itens
    if itens:
        assert r["pedidos"][0]["IDPedido"] == 42 and r["pedidos"][0]["IDStatus"] == 42
    req = dict(_filhos(ET.fromstring(onr.chamadas[-1][2]).find(f".//{{{W.NS}}}oRequest")))
    assert (req["MaxRowPerPage"], req["IDStatus"], req["TipoDataPesquisa"]) == ("10", "0", "P")
    assert (req["DataInicial"], req["DataFinal"]) == ("2026-11-01", "2026-11-25")
    p = s.pagamentos_da_intimacao(custas_de=date(2026, 11, 1))
    assert len(p["pagamentos"]) == itens
    if itens:
        assert p["pagamentos"][0]["Pago"] is True
        assert p["pagamentos"][0]["Valor"] == Decimal("1234.56")
        assert p["pagamentos"][0]["IDCustas"] == 42


@precisa_lxml
def test_as_outras_leituras_da_intimacao_validam_contra_o_wsdl(pasta):
    esquema = _esquema(INTIMACOES)
    onr = ONRDeMentira({"ListStatusIN": "<RETORNO>true</RETORNO><Status>"
                                        "<ListStatusIN_Status_WSResp><IDStatus>1</IDStatus>"
                                        "<NomeStatus>Em aberto</NomeStatus>"
                                        "</ListStatusIN_Status_WSResp></Status>"})
    s = W.Sessao(pasta=pasta, transporte=onr, certificado=CERT)
    assert s.status_da_intimacao() == [{"IDStatus": 1, "NomeStatus": "Em aberto"}]
    s.mensagens_da_intimacao(9)
    s.mensagem_da_intimacao(3)
    s.emolumentos_da_intimacao(9)
    s.pedidos_da_intimacao()
    s.pagamentos_da_intimacao()
    for _, metodo, xml in onr.chamadas:
        if metodo != "LoginUsuarioCertificado":
            _validar(esquema, xml.encode("utf-8"))


@precisa_lxml
def test_a_matricula_online_tem_30_dias_e_o_14_e_vazio(pasta):
    onr = ONRDeMentira({"ObterXmlSolicitacoesV2":
                        "<RETORNO>false</RETORNO><CODIGOERRO>14</CODIGOERRO>"
                        "<ERRODESCRICAO>Não foram encontrados resultados para o período "
                        "Informado.</ERRODESCRICAO>"})
    s = W.Sessao(pasta=pasta, transporte=onr, certificado=CERT)
    assert s.solicitacoes_da_matricula_online(de="2026-11-01", ate=date(2026, 11, 25))["vazio"]
    _validar(_esquema(Contrato(_wsdl("matricula"))), onr.chamadas[-1][2].encode("utf-8"))
    assert "<DataInicial>2026-11-01</DataInicial>" in onr.chamadas[-1][2]
    assert onr.chamadas[-1][0].endswith("/matriculaonline.asmx")
    antes = len(onr.chamadas)
    with pytest.raises(W.WSOficioError, match="30 dias"):
        s.solicitacoes_da_matricula_online(de="2026-10-01", ate="2026-11-25")
    with pytest.raises(W.WSOficioError, match="aaaa-mm-dd"):
        s.solicitacoes_da_matricula_online(de="01/13/2026", ate="2026-11-25")
    assert len(onr.chamadas) == antes


def test_a_data_do_onr_nas_formas_do_manual():
    assert W.ler_data_do_onr("2026-11-25") == date(2026, 11, 25)
    assert W.ler_data_do_onr("2026-11-2509:30:00") == datetime(2026, 11, 25, 9, 30)
    assert W.ler_data_do_onr("2026-11-25 09:30:01") == datetime(2026, 11, 25, 9, 30, 1)
    assert W.ler_data_do_onr("2026-11-25T09:30:00.123") == datetime(2026, 11, 25, 9, 30)
    assert W.ler_data_do_onr("25/11/2026 09:30:00") == datetime(2026, 11, 25, 9, 30)
    assert W.ler_data_do_onr("25/11/2026") == date(2026, 11, 25)
    assert W.ler_data_do_onr("2026-02-30") is None
    assert W.ler_data_do_onr("") is None and W.ler_data_do_onr(None) is None


def test_como_lista_nas_tres_formas():
    assert W.como_lista("") == [] and W.como_lista(None) == []
    assert W.como_lista({"Nome": "a"}) == [{"Nome": "a"}]
    assert W.como_lista([{"Nome": "a"}, {"Nome": "b"}]) == [{"Nome": "a"}, {"Nome": "b"}]
    assert W.como_lista({"Item_WSResp": {"Nome": "a"}}) == [{"Nome": "a"}]

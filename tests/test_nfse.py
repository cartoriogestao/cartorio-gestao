"""A NFS-e DOS EMOLUMENTOS — do recibo pago à nota, contra um emissor FALSO.

POR QUE ESTES TESTES (LG01, 19/10/2026)
    A nota vai ao fisco: valor errado é imposto errado, nota em dobro é nota
    a cancelar, e senha em rastro é certificado da serventia exposto. Cada
    teste abaixo prova uma dessas promessas sem abrir rede: o emissor é uma
    SEFIN FALSA, na memória, que faz o que a de verdade faz do lado de lá —
    descomprime a DPS, valida contra o leiaute (um XSD mínimo, escrito aqui,
    com os grupos que a casa manda), confere a assinatura com o certificado
    que vem dentro dela e devolve a chave. A conferência da assinatura é
    escrita de novo aqui, e não emprestada de `nfse_dps`: um teste que confere
    a assinatura com o mesmo código que a fez não prova nada.

    Os documentos são os fictícios do varredor anti-vazamento; o certificado
    A1 é gerado na hora, numa pasta temporária, e não existe fora do teste.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from lxml import etree

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import nfse as NFSE  # noqa: E402
import nfse_dps as DPS  # noqa: E402
import nfse_provedor as PROV  # noqa: E402
from bd_nativo import banco  # noqa: E402
from conftest import cg_login  # noqa: E402

SENHA_DO_A1 = "senha-ficticia-do-a1"
PRESTADOR = "00000010000127"          # 00.000.010/0001-27, fictício
TOMADOR = "00000000272"               # 000.000.002-72, fictício
OUTRO_TOMADOR = "00000000353"         # 000.000.003-53, fictício
MUNICIPIO = "2100055"                 # sete dígitos; não é a serventia
NS = {"n": DPS.NS, "ds": DPS.NS_DS}

# --------------------------------------------------------------- o leiaute
#
# O MÍNIMO DO LEIAUTE DA DPS 1.00 QUE A CASA PREENCHE — ordem, obrigatórios
# e formato. Não é o XSD oficial (ele não viaja com o sistema); é o bastante
# para o servidor falso recusar o que a Sefin recusaria: grupo fora de ordem,
# campo obrigatório ausente, dinheiro com vírgula, data sem fuso, documento
# com dígito a mais e DPS sem assinatura.
XSD_DA_DPS = f"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="{DPS.NS}"
           xmlns="{DPS.NS}" elementFormDefault="qualified">
  <xs:simpleType name="Doc11"><xs:restriction base="xs:string"><xs:pattern value="[0-9]{{11}}"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="Doc14"><xs:restriction base="xs:string"><xs:pattern value="[0-9]{{14}}"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="Mun"><xs:restriction base="xs:string"><xs:pattern value="[0-9]{{7}}"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="Dinheiro"><xs:restriction base="xs:string"><xs:pattern value="[0-9]{{1,13}}\\.[0-9]{{2}}"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="Texto"><xs:restriction base="xs:string"><xs:minLength value="1"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="DataHoraComFuso"><xs:restriction base="xs:dateTime">
    <xs:pattern value=".+[+\\-][0-9]{{2}}:[0-9]{{2}}"/></xs:restriction></xs:simpleType>
  <xs:complexType name="TEnd"><xs:sequence>
    <xs:element name="endNac"><xs:complexType><xs:sequence>
      <xs:element name="cMun" type="Mun"/>
      <xs:element name="CEP"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[0-9]{{8}}"/></xs:restriction></xs:simpleType></xs:element>
    </xs:sequence></xs:complexType></xs:element>
    <xs:element name="xLgr" type="Texto"/><xs:element name="nro" type="Texto"/>
    <xs:element name="xCpl" type="Texto" minOccurs="0"/><xs:element name="xBairro" type="Texto"/>
  </xs:sequence></xs:complexType>
  <xs:element name="DPS"><xs:complexType><xs:sequence>
    <xs:element name="infDPS"><xs:complexType><xs:sequence>
      <xs:element name="tpAmb"><xs:simpleType><xs:restriction base="xs:string"><xs:enumeration value="1"/><xs:enumeration value="2"/></xs:restriction></xs:simpleType></xs:element>
      <xs:element name="dhEmi" type="DataHoraComFuso"/>
      <xs:element name="verAplic" type="Texto"/>
      <xs:element name="serie"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[0-9]{{1,5}}"/></xs:restriction></xs:simpleType></xs:element>
      <xs:element name="nDPS"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[1-9][0-9]{{0,14}}"/></xs:restriction></xs:simpleType></xs:element>
      <xs:element name="dCompet" type="xs:date"/>
      <xs:element name="tpEmit"><xs:simpleType><xs:restriction base="xs:string"><xs:enumeration value="1"/></xs:restriction></xs:simpleType></xs:element>
      <xs:element name="cLocEmi" type="Mun"/>
      <xs:element name="prest"><xs:complexType><xs:sequence>
        <xs:choice><xs:element name="CNPJ" type="Doc14"/><xs:element name="CPF" type="Doc11"/></xs:choice>
        <xs:element name="IM" type="Texto" minOccurs="0"/>
        <xs:element name="regTrib"><xs:complexType><xs:sequence>
          <xs:element name="opSimpNac"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[1-3]"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="regEspTrib"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[0-6]"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType></xs:element>
      </xs:sequence></xs:complexType></xs:element>
      <xs:element name="toma"><xs:complexType><xs:sequence>
        <xs:choice><xs:element name="CNPJ" type="Doc14"/><xs:element name="CPF" type="Doc11"/></xs:choice>
        <xs:element name="xNome" type="Texto"/>
        <xs:element name="end" type="TEnd" minOccurs="0"/>
        <xs:element name="email" type="Texto" minOccurs="0"/>
      </xs:sequence></xs:complexType></xs:element>
      <xs:element name="serv"><xs:complexType><xs:sequence>
        <xs:element name="locPrest"><xs:complexType><xs:sequence><xs:element name="cLocPrestacao" type="Mun"/></xs:sequence></xs:complexType></xs:element>
        <xs:element name="cServ"><xs:complexType><xs:sequence>
          <xs:element name="cTribNac"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[0-9]{{6}}"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="cTribMun" type="Texto" minOccurs="0"/>
          <xs:element name="xDescServ"><xs:simpleType><xs:restriction base="xs:string"><xs:minLength value="1"/><xs:maxLength value="2000"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType></xs:element>
      </xs:sequence></xs:complexType></xs:element>
      <xs:element name="valores"><xs:complexType><xs:sequence>
        <xs:element name="vServPrest"><xs:complexType><xs:sequence><xs:element name="vServ" type="Dinheiro"/></xs:sequence></xs:complexType></xs:element>
        <xs:element name="trib"><xs:complexType><xs:sequence>
          <xs:element name="tribMun"><xs:complexType><xs:sequence>
            <xs:element name="tribISSQN"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[1-4]"/></xs:restriction></xs:simpleType></xs:element>
            <xs:element name="tpRetISSQN"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[1-3]"/></xs:restriction></xs:simpleType></xs:element>
            <xs:element name="pAliq" minOccurs="0"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="[0-9]\\.[0-9]{{2}}"/></xs:restriction></xs:simpleType></xs:element>
          </xs:sequence></xs:complexType></xs:element>
          <xs:element name="totTrib"><xs:complexType><xs:sequence><xs:element name="indTotTrib" type="xs:string"/></xs:sequence></xs:complexType></xs:element>
        </xs:sequence></xs:complexType></xs:element>
      </xs:sequence></xs:complexType></xs:element>
    </xs:sequence>
    <xs:attribute name="Id" use="required"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="DPS[0-9]{{42}}"/></xs:restriction></xs:simpleType></xs:attribute>
    </xs:complexType></xs:element>
    <xs:any namespace="{DPS.NS_DS}" processContents="skip"/>
  </xs:sequence>
  <xs:attribute name="versao" type="xs:string" use="required" fixed="1.00"/>
  </xs:complexType></xs:element>
</xs:schema>"""

LEIAUTE = etree.XMLSchema(etree.fromstring(XSD_DA_DPS.encode("utf-8")))


def _assinatura_confere(raiz) -> bool:
    """A conferência da Sefin, escrita aqui de novo (e não a de `nfse_dps`)."""
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    sig = raiz.find("ds:Signature", NS)
    if sig is None:
        return False
    alvo = raiz[0]
    ref = sig.find("ds:SignedInfo/ds:Reference", NS)
    if ref.get("URI") != "#" + alvo.get("Id"):
        return False
    resumo = hashlib.sha256(etree.tostring(alvo, method="c14n")).digest()
    if base64.b64decode(ref.findtext("ds:DigestValue", namespaces=NS)) != resumo:
        return False
    cert = x509.load_der_x509_certificate(base64.b64decode(
        sig.findtext("ds:KeyInfo/ds:X509Data/ds:X509Certificate", namespaces=NS)))
    try:
        cert.public_key().verify(
            base64.b64decode(sig.findtext("ds:SignatureValue", namespaces=NS)),
            etree.tostring(sig.find("ds:SignedInfo", NS), method="c14n"),
            padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return False
    return True


class SefinFalsa:
    """O emissor nacional, na memória. Guarda o que recebeu; nunca abre rede."""

    def __init__(self):
        self.chamadas: list[tuple[str, str]] = []
        # id da DPS -> nota, um cadastro por ambiente: a produção restrita e a
        # produção são sistemas separados, e a mesma DPS nº 1 existe nos dois.
        self.por_ambiente: dict[bool, dict[str, dict]] = {True: {}, False: {}}
        self.emitidas = self.por_ambiente[True]    # o da homologação
        self._agora = self.emitidas
        self.canceladas: set[str] = set()
        self.recusar_com: str | None = None        # código de erro da próxima emissão
        self.perder_a_resposta = False             # emite, e a resposta não chega
        self.fora_do_ar = False
        self.aceita_producao = False               # só o teste da virada liga

    def __call__(self, metodo: str, url: str, corpo=None) -> PROV.Resposta:
        self.chamadas.append((metodo, url))
        homologacao = url.startswith(("https://sefin.producaorestrita.nfse.gov.br/",
                                      "https://adn.producaorestrita.nfse.gov.br/"))
        assert homologacao or self.aceita_producao, \
            "o teste fala com a homologação, e só com ela"
        self._agora = self.por_ambiente[homologacao]
        if self.fora_do_ar:
            raise TimeoutError("timed out")
        caminho = url.split(".gov.br", 1)[1]
        if metodo == "POST" and caminho.endswith("/SefinNacional/nfse"):
            return self._emitir(corpo)
        achado = re.match(r"/SefinNacional/dps/(DPS\d+)$", caminho)
        if metodo == "GET" and achado:
            nota = self._agora.get(achado.group(1))
            return (PROV.Resposta(200, {"chaveAcesso": nota["chave"]}) if nota
                    else PROV.Resposta(404, {}))
        achado = re.match(r"/SefinNacional/nfse/(\d{50})(/eventos)?$", caminho)
        if achado and metodo == "GET":
            nota = next(n for n in self._agora.values() if n["chave"] == achado.group(1))
            return PROV.Resposta(200, {"chaveAcesso": nota["chave"],
                                       "nfseXmlGZipB64": PROV.comprimir(nota["xml"])})
        if achado and metodo == "POST":
            return self._cancelar(achado.group(1), corpo)
        achado = re.match(r"/danfse/(\d{50})$", caminho)
        if achado:
            return PROV.Resposta(200, b"%PDF-1.4 danfse ficticio " + achado.group(1).encode())
        return PROV.Resposta(404, {})

    def _emitir(self, corpo) -> PROV.Resposta:
        xml = gzip.decompress(base64.b64decode(corpo["dpsXmlGZipB64"]))
        raiz = etree.fromstring(xml)
        if not LEIAUTE.validate(raiz):
            return PROV.Resposta(400, {"erros": [{"Codigo": "E1235", "Descricao":
                                                  str(LEIAUTE.error_log.last_error)}]})
        if not _assinatura_confere(raiz):
            return PROV.Resposta(400, {"erros": [{"Codigo": "E0714",
                                                  "Descricao": "Assinatura inválida"}]})
        if self.recusar_com:
            codigo, self.recusar_com = self.recusar_com, None
            return PROV.Resposta(400, {"erros": [{"Codigo": codigo,
                                                  "Descricao": "Recusa de teste"}]})
        ident = raiz[0].get("Id")
        if ident in self._agora:
            return PROV.Resposta(400, {"erros": [{"Codigo": "E0014",
                                                  "Descricao": "DPS já convertida em NFS-e"}]})
        numero = len(self._agora) + 1
        tp_amb = raiz.findtext("n:infDPS/n:tpAmb", namespaces=NS)
        chave = f"{MUNICIPIO}{tp_amb}{numero:042d}"
        nfse = (f'<NFSe xmlns="{DPS.NS}" versao="1.00"><infNFSe Id="NFS{chave}">'
                f"<nNFSe>{numero}</nNFSe></infNFSe></NFSe>").encode("utf-8")
        self._agora[ident] = {"chave": chave, "numero": numero, "xml": nfse, "dps": raiz}
        if self.perder_a_resposta:
            self.perder_a_resposta = False
            raise TimeoutError("timed out")       # emitiu, e a resposta se perdeu
        return PROV.Resposta(201, {"chaveAcesso": chave,
                                   "nfseXmlGZipB64": PROV.comprimir(nfse)})

    def _cancelar(self, chave: str, corpo) -> PROV.Resposta:
        raiz = etree.fromstring(gzip.decompress(base64.b64decode(
            corpo["pedidoRegistroEventoXmlGZipB64"])))
        if not _assinatura_confere(raiz):
            return PROV.Resposta(400, {"erros": [{"Codigo": "E0714",
                                                  "Descricao": "Assinatura inválida"}]})
        if raiz.findtext("n:infPedReg/n:chNFSe", namespaces=NS) != chave:
            return PROV.Resposta(400, {"erros": [{"Codigo": "E1800",
                                                  "Descricao": "Chave diferente"}]})
        self.canceladas.add(chave)
        return PROV.Resposta(201, {})

    def posts_de_dps(self) -> int:
        return sum(1 for m, u in self.chamadas if m == "POST" and u.endswith("/nfse"))


# ----------------------------------------------------------------- a casa

@pytest.fixture(scope="module")
def pfx() -> bytes:
    """Um A1 fictício, autoassinado — gerado uma vez por arquivo."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (BestAvailableEncryption,
                                                              pkcs12)
    from cryptography.x509.oid import NameOID

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "SERVENTIA FICTICIA DE TESTE")])
    agora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(agora - timedelta(days=1))
            .not_valid_after(agora + timedelta(days=365)).sign(chave, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(
        b"a1", chave, cert, None, BestAvailableEncryption(SENHA_DO_A1.encode()))


@pytest.fixture
def sefin(monkeypatch) -> SefinFalsa:
    falsa = SefinFalsa()
    monkeypatch.setattr(PROV, "transporte_https", lambda certificado, prazo=30: falsa)
    return falsa


@pytest.fixture
def credenciais(tmp_path, monkeypatch) -> Path:
    """A pasta fora do banco (o `%PROGRAMDATA%` da máquina), aqui temporária."""
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    return tmp_path / "CartorioGestao"


CONFIG_LIGADA = {
    "nfse_ligada": "1", "nfse_ambiente": "homologacao", "nfse_provedor": "nacional",
    "nfse_municipio": MUNICIPIO, "nfse_prestador_documento": PRESTADOR,
    "nfse_inscricao_municipal": "12345", "nfse_codigo_tributacao": "210101",
    "nfse_aliquota": "5,00", "nfse_optante_simples": "1", "nfse_regime_especial": "4",
    "nfse_serie": "1", "nfse_exige_endereco": "1",
}


@pytest.fixture
def casa(cg_casa_logada, sefin, credenciais, pfx):
    """Casa com NFS-e ligada na homologação, certificado gravado e Sefin falsa."""
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        NFSE.gravar_configuracao(con, CONFIG_LIGADA)
    NFSE.gravar_certificado(pfx, SENHA_DO_A1)
    return {**cg_casa_logada, "sefin": sefin, "pfx": pfx}


def _recibo(db, *, numero: int, documento: str | None = TOMADOR,
            pagador: str = "TOMADORA FICTICIA DE TESTE", total: str = "134,43",
            lancamentos: list[dict] | None = None, data: str = "2026-10-19",
            discriminacao: dict | None = None) -> int:
    """Um recibo pago, com os lançamentos que o pagaram."""
    if lancamentos is None:
        lancamentos = [{"valor": "134,43", "emolumentos": "120,03", "ferc": "3,60",
                        "fadep": "4,80", "femp": "4,80", "ferrfis": "1,20"}]
    disc = discriminacao or {"itens": [{"codigo_ato": "16.3", "descricao":
                                        "Certidão de inteiro teor", "quantidade": 1}]}
    with db.transaction() as con:
        bd = banco(con)
        rid = bd.escrever(
            """INSERT INTO cx_recibos (numero, ano, data_emissao, pagador, pagador_documento,
                   valor_total, discriminacao, corpo, criado_em)
               VALUES (%s, 2026, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (numero, data, pagador, documento, total, json.dumps(disc),
             json.dumps(disc), data + "T10:00:00"))[0]["id"]
        for i, l in enumerate(lancamentos, start=1):
            bd.escrever(
                """INSERT INTO cx_lancamentos (data, natureza, sentido, valor, emolumentos,
                       ferc, fadep, femp, ferrfis, recibo_id, numero, ano, criado_em)
                   VALUES (%s, 'RECEBIMENTO', 'ENTRADA', %s, %s, %s, %s, %s, %s, %s,
                           %s, 2026, %s)""",
                (data, l["valor"], l.get("emolumentos"), l.get("ferc"), l.get("fadep"),
                 l.get("femp"), l.get("ferrfis"), rid, numero * 10 + i, data + "T10:00:00"))
    return int(rid)


def _endereco(db, documento: str = TOMADOR) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO nfse_tomadores (documento, nome, cep, municipio, logradouro,
                   numero, bairro) VALUES (%s, '', '65000000', %s, 'RUA FICTICIA', '10',
                   'CENTRO')""", (documento, MUNICIPIO))


def _token(cliente) -> str:
    cliente.get("/caixa/nfse")
    with cliente.session_transaction() as s:
        return s["csrf_token"]


def _emitir(casa, recibo_id: int):
    c = casa["c"]
    return c.post(f"/caixa/nfse/recibo/{recibo_id}/emitir",
                  data={"csrf_token": _token(c)}, follow_redirects=True)


def _cfg(db) -> dict:
    with db.connect() as con:
        return NFSE.configuracao(con)


def _nota_do_recibo(db, recibo_id: int) -> dict:
    with db.connect() as con:
        notas = NFSE.notas_do_recibo(con, recibo_id)
    assert len(notas) == 1, notas
    return notas[0]


# ------------------------------------------------------------- o XML puro

def test_a_dps_assinada_passa_no_leiaute_e_na_assinatura_do_servidor_falso(pfx):
    cert = DPS.abrir_pfx(pfx, SENHA_DO_A1)
    xml = DPS.assinar(DPS.montar_dps(
        ambiente="homologacao", emitida_em=datetime(2026, 10, 19, 10, 0, tzinfo=timezone(
            timedelta(hours=-3))), serie="1", numero=7,
        prestador=DPS.Prestador(PRESTADOR, "12345", MUNICIPIO),
        tomador=DPS.Tomador(TOMADOR, "TOMADORA FICTICIA", "65000000", MUNICIPIO,
                            "RUA FICTICIA", "10", "", "CENTRO"),
        servico=DPS.Servico("210101", "Emolumentos", 12003, "5,00")), cert)
    raiz = etree.fromstring(xml)
    assert LEIAUTE.validate(raiz), LEIAUTE.error_log
    assert _assinatura_confere(raiz)
    assert raiz[0].get("Id") == f"DPS{MUNICIPIO}2{PRESTADOR}00001{7:015d}"
    assert raiz.findtext("n:infDPS/n:valores/n:vServPrest/n:vServ", namespaces=NS) == "120.03"
    assert raiz.findtext("n:infDPS/n:dhEmi", namespaces=NS) == "2026-10-19T10:00:00-03:00"


def test_dps_mexida_depois_de_assinada_e_recusada_pela_assinatura(pfx):
    cert = DPS.abrir_pfx(pfx, SENHA_DO_A1)
    xml = DPS.assinar(DPS.montar_dps(
        ambiente="homologacao", emitida_em=datetime.now().astimezone(), serie="1", numero=1,
        prestador=DPS.Prestador(PRESTADOR, "", MUNICIPIO),
        tomador=DPS.Tomador(TOMADOR, "TOMADORA FICTICIA"),
        servico=DPS.Servico("210101", "Emolumentos", 1000)), cert)
    mexido = xml.replace(b"<vServ>10.00</vServ>", b"<vServ>1.00</vServ>")
    assert mexido != xml
    assert DPS.conferir_assinatura(xml) and not DPS.conferir_assinatura(mexido)
    assert not _assinatura_confere(etree.fromstring(mexido))


def test_senha_errada_do_a1_nao_abre_e_a_frase_nao_traz_a_senha(pfx):
    with pytest.raises(DPS.DpsError) as erro:
        DPS.abrir_pfx(pfx, "senha-errada-qualquer")
    assert "senha-errada-qualquer" not in str(erro.value)


# ---------------------------------------------------- a base e a pendência

def test_a_base_do_iss_e_o_emolumento_e_os_fundos_ficam_fora_da_nota(casa):
    db = casa["db"]
    rid = _recibo(db, numero=101)
    _endereco(db)
    resposta = _emitir(casa, rid)
    assert resposta.status_code == 200
    nota = _nota_do_recibo(db, rid)
    assert nota["situacao"] == NFSE.EMITIDA, nota["mensagem"]
    assert nota["valor_servico"] == 12003          # R$ 120,03, e não os 134,43
    assert nota["valor_iss"] == 600                # 5% de 120,03 = 6,0015 → 6,00
    dps = casa["sefin"].emitidas[nota["id_dps"]]["dps"]
    assert dps.findtext("n:infDPS/n:valores/n:vServPrest/n:vServ", namespaces=NS) == "120.03"
    descricao = dps.findtext("n:infDPS/n:serv/n:cServ/n:xDescServ", namespaces=NS)
    assert "R$ 14,40" in descricao and "não integram o preço" in descricao
    assert "TOMADORA" not in descricao             # a descrição não leva o nome


def test_recibo_sem_cpf_vira_pendencia_clara_e_nao_chama_o_emissor(casa):
    db = casa["db"]
    rid = _recibo(db, numero=102, documento=None)
    resposta = _emitir(casa, rid)
    assert "Falta o CPF ou CNPJ do tomador" in resposta.get_data(as_text=True)
    assert casa["sefin"].chamadas == []
    with db.connect() as con:
        assert NFSE.notas_do_recibo(con, rid) == []
        grupos = NFSE.fila(con, _cfg(db))
    assert [i["recibo"]["id"] for i in grupos["pendentes"]] == [rid]


def test_falta_de_endereco_e_pendencia_e_o_balcao_completa_sem_mexer_no_recibo(casa):
    db = casa["db"]
    rid = _recibo(db, numero=103)
    c = casa["c"]
    html = c.get(f"/caixa/nfse/recibo/{rid}").get_data(as_text=True)
    assert "Falta o endereço do tomador" in html
    resposta = c.post(f"/caixa/nfse/recibo/{rid}", data={
        "csrf_token": _token(c), "documento": TOMADOR, "nome": "",
        "cep": "65000-000", "municipio": MUNICIPIO, "logradouro": "RUA FICTICIA",
        "numero": "10", "bairro": "CENTRO"}, follow_redirects=True)
    assert "Dados do tomador gravados" in resposta.get_data(as_text=True)
    with db.connect() as con:
        item = NFSE.avaliar_recibo(con, rid, _cfg(db))
        r = NFSE.recibo(con, rid)
    assert item["pendencias"] == []
    assert r["pagador_documento"] == TOMADOR and r["pagador"] == "TOMADORA FICTICIA DE TESTE"
    # o endereço fica pelo CPF, e o próximo recibo da mesma pessoa já sai pronto
    outro = _recibo(db, numero=104)
    with db.connect() as con:
        assert NFSE.avaliar_recibo(con, outro, _cfg(db))["pendencias"] == []


def test_lancamento_que_nao_separa_emolumento_vira_pendencia_e_nao_palpite(casa):
    db = casa["db"]
    rid = _recibo(db, numero=105, total="50,00", lancamentos=[{"valor": "50,00"}])
    _endereco(db)
    with db.connect() as con:
        item = NFSE.avaliar_recibo(con, rid, _cfg(db))
    assert item["base"] == 0
    assert any("não separa o emolumento dos fundos" in p for p in item["pendencias"])
    _emitir(casa, rid)
    assert casa["sefin"].chamadas == []


def test_ato_gratuito_nao_tem_nota_nem_aparece_como_pendencia(casa):
    db = casa["db"]
    rid = _recibo(db, numero=106, total="0,00", lancamentos=[
        {"valor": "0,00", "emolumentos": "0,00", "ferc": "0,00"}])
    with db.connect() as con:
        grupos = NFSE.fila(con, _cfg(db))
    assert rid not in [i["recibo"]["id"] for g in grupos.values() for i in g]


# ------------------------------------------------- a nota e a idempotência

def test_emitir_deixa_rastro_em_audit_logs_e_a_homologacao_nao_marca_o_recibo(casa):
    db = casa["db"]
    rid = _recibo(db, numero=107)
    _endereco(db)
    html = _emitir(casa, rid).get_data(as_text=True)
    assert "NFS-e 1 emitida" in html
    nota = _nota_do_recibo(db, rid)
    with db.connect() as con:
        r = NFSE.recibo(con, rid)
        logs = banco(con).ler(
            "SELECT action, details FROM audit_logs WHERE action LIKE 'NFSE%' ORDER BY id")
    assert len(nota["chave"]) == 50
    # nota de homologação não tem valor fiscal: o recibo não a carrega
    assert (r["nfse_numero"], r["nfse_chave"]) == (None, None)
    assert [l["action"] for l in logs] == ["NFSE_EMITIDA"]
    assert TOMADOR not in logs[0]["details"]          # CPF vai mascarado
    assert "***.000.002-**" in logs[0]["details"]


def test_na_producao_o_numero_e_a_chave_vao_ao_recibo_e_a_nota_de_teste_nao_impede(casa):
    """A virada: o recibo testado na homologação ganha a nota de verdade."""
    db = casa["db"]
    rid = _recibo(db, numero=115)
    _endereco(db)
    _emitir(casa, rid)                                   # a de teste
    with db.transaction() as con:
        NFSE.gravar_configuracao(con, {**CONFIG_LIGADA, "nfse_ambiente": "producao"})
    casa["sefin"].aceita_producao = True
    _emitir(casa, rid)
    with db.connect() as con:
        notas = NFSE.notas_do_recibo(con, rid)
        r = NFSE.recibo(con, rid)
    assert [(n["ambiente"], n["situacao"]) for n in notas] == [
        ("homologacao", NFSE.EMITIDA), ("producao", NFSE.EMITIDA)]
    producao = notas[1]
    assert producao["numero_dps"] == 1                  # a numeração é por ambiente
    assert (r["nfse_numero"], r["nfse_chave"]) == (producao["numero_nfse"], producao["chave"])
    assert casa["sefin"].chamadas[-1][1].startswith("https://sefin.nfse.gov.br/")
    # e a DPS de teste que ficou para trás não vai à produção
    with pytest.raises(NFSE.NfseError, match="homologacao"):
        NFSE.danfse(db, notas[0]["id"], NFSE.provedor_da_casa(
            _cfg(db), NFSE.ler_certificado()), usuario="teste")


def test_clicar_duas_vezes_nao_emite_duas_notas(casa):
    db = casa["db"]
    rid = _recibo(db, numero=108)
    _endereco(db)
    _emitir(casa, rid)
    _emitir(casa, rid)
    assert casa["sefin"].posts_de_dps() == 1
    assert _nota_do_recibo(db, rid)["situacao"] == NFSE.EMITIDA


def test_rede_que_cai_deixa_na_fila_e_o_reenvio_recupera_a_mesma_nota(casa):
    """A Sefin emitiu e a resposta se perdeu: reenviar não pode criar a segunda."""
    db = casa["db"]
    rid = _recibo(db, numero=109)
    _endereco(db)
    casa["sefin"].perder_a_resposta = True
    html = _emitir(casa, rid).get_data(as_text=True)
    assert "ficou na fila" in html
    nota = _nota_do_recibo(db, rid)
    assert nota["situacao"] == NFSE.ENVIANDO and nota["tentativas"] == 1
    with db.connect() as con:
        assert [i["recibo"]["id"] for i in NFSE.fila(con, _cfg(db))["enviando"]] == [rid]
    c = casa["c"]
    c.post(f"/caixa/nfse/nota/{nota['id']}/reenviar", data={"csrf_token": _token(c)})
    depois = _nota_do_recibo(db, rid)
    assert depois["situacao"] == NFSE.EMITIDA
    assert depois["chave"] == casa["sefin"].emitidas[nota["id_dps"]]["chave"]
    assert casa["sefin"].posts_de_dps() == 1          # perguntou, não mandou de novo
    assert depois["xml_dps"] == nota["xml_dps"]       # a mesma DPS, byte a byte


def test_resposta_de_dps_ja_emitida_vira_a_chave_e_nao_recusa(casa, pfx):
    db = casa["db"]
    rid = _recibo(db, numero=110)
    _endereco(db)
    cfg = _cfg(db)
    cert = DPS.abrir_pfx(pfx, SENHA_DO_A1)
    with db.transaction() as con:
        nota = NFSE.preparar(con, rid, cfg=cfg, certificado=cert, usuario="teste")
    provedor = NFSE.provedor_da_casa(cfg, cert)
    provedor.emitir(nota["xml_dps"].encode("utf-8"))   # outra máquina mandou antes
    final = NFSE.enviar(db, nota["id"], provedor, usuario="teste")
    assert final["situacao"] == NFSE.EMITIDA
    assert final["chave"] == casa["sefin"].emitidas[nota["id_dps"]]["chave"]


def test_recusa_do_emissor_fica_na_fila_e_o_reenvio_reusa_o_numero_da_dps(casa):
    db = casa["db"]
    rid = _recibo(db, numero=111)
    _endereco(db)
    casa["sefin"].recusar_com = "E0312"
    html = _emitir(casa, rid).get_data(as_text=True)
    assert "recusou a DPS" in html and "E0312" in html
    recusada = _nota_do_recibo(db, rid)
    assert recusada["situacao"] == NFSE.REJEITADA
    c = casa["c"]
    c.post(f"/caixa/nfse/nota/{recusada['id']}/reenviar", data={"csrf_token": _token(c)})
    depois = _nota_do_recibo(db, rid)
    assert depois["situacao"] == NFSE.EMITIDA
    assert depois["numero_dps"] == recusada["numero_dps"]


def test_dois_recibos_pegam_numeros_de_dps_seguidos(casa):
    db = casa["db"]
    _endereco(db)
    a, b = _recibo(db, numero=112), _recibo(db, numero=113)
    _emitir(casa, a)
    _emitir(casa, b)
    assert (_nota_do_recibo(db, a)["numero_dps"], _nota_do_recibo(db, b)["numero_dps"]) == (1, 2)


def test_o_banco_recusa_duas_notas_vivas_do_mesmo_recibo(casa):
    import sqlite3
    db = casa["db"]
    rid = _recibo(db, numero=114)
    _endereco(db)
    _emitir(casa, rid)
    nota = _nota_do_recibo(db, rid)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as con:
            banco(con).escrever(
                """INSERT INTO nfse_notas (recibo_id, provedor, ambiente, situacao, serie,
                       numero_dps, id_dps, tomador_documento, tomador_nome, valor_servico,
                       xml_dps, criado_em)
                   VALUES (%s, 'nacional', 'homologacao', 'ENVIANDO', '1', 99, 'DPSX',
                           %s, 'X', 1, '<x/>', 'agora')""", (rid, TOMADOR))
    assert _nota_do_recibo(db, rid)["id"] == nota["id"]


def test_lote_do_dia_emite_os_prontos_e_deixa_os_pendentes(casa):
    db = casa["db"]
    _endereco(db)
    prontos = [_recibo(db, numero=n) for n in (120, 121)]
    sem_cpf = _recibo(db, numero=122, documento=None)
    de_outro_dia = _recibo(db, numero=123, data="2026-10-18")
    c = casa["c"]
    html = c.post("/caixa/nfse/lote", data={"csrf_token": _token(c), "data": "2026-10-19"},
                  follow_redirects=True).get_data(as_text=True)
    assert "2 emitida(s)" in html
    for rid in prontos:
        assert _nota_do_recibo(db, rid)["situacao"] == NFSE.EMITIDA
    with db.connect() as con:
        assert NFSE.notas_do_recibo(con, sem_cpf) == []
        assert NFSE.notas_do_recibo(con, de_outro_dia) == []


# ---------------------------------------------- cancelamento e o DANFSe

def test_cancelar_manda_o_evento_assinado_e_limpa_o_recibo(casa):
    db = casa["db"]
    rid = _recibo(db, numero=130)
    _endereco(db)
    _emitir(casa, rid)
    nota = _nota_do_recibo(db, rid)
    c = casa["c"]
    html = c.post(f"/caixa/nfse/nota/{nota['id']}/cancelar", data={
        "csrf_token": _token(c), "motivo": "1",
        "justificativa": "Valor do serviço lançado errado no recibo"},
        follow_redirects=True).get_data(as_text=True)
    assert "NFS-e cancelada" in html
    assert nota["chave"] in casa["sefin"].canceladas
    depois = _nota_do_recibo(db, rid)
    assert depois["situacao"] == NFSE.CANCELADA
    # cancelada por erro, o recibo pode ganhar a nota certa
    _emitir(casa, rid)
    with db.connect() as con:
        assert [n["situacao"] for n in NFSE.notas_do_recibo(con, rid)] == [
            NFSE.CANCELADA, NFSE.EMITIDA]


class ProvedorComClique:
    """O provedor da casa, e outro clique que acontece enquanto ele fala com a rede."""

    def __init__(self, real, *, ao_perguntar=None, ao_emitir=None):
        self.real, self.ao_perguntar, self.ao_emitir = real, ao_perguntar, ao_emitir

    def __getattr__(self, nome):
        return getattr(self.real, nome)

    def consultar_dps(self, id_dps):
        resposta = self.real.consultar_dps(id_dps)
        if self.ao_perguntar:
            self.ao_perguntar()
        return resposta

    def emitir(self, xml):
        if self.ao_emitir:
            self.ao_emitir()
        return self.real.emitir(xml)


def _na_fila(casa, numero: int) -> tuple[int, dict]:
    """Um recibo cuja DPS saiu com a Sefin fora do ar: ENVIANDO, sem chave."""
    db = casa["db"]
    rid = _recibo(db, numero=numero)
    _endereco(db)
    casa["sefin"].fora_do_ar = True
    _emitir(casa, rid)
    casa["sefin"].fora_do_ar = False
    nota = _nota_do_recibo(db, rid)
    assert (nota["situacao"], nota["chave"], nota["tentativas"]) == (NFSE.ENVIANDO, None, 1)
    return rid, nota


def test_cancelar_nao_apaga_a_nota_que_um_reenvio_emitiu_durante_a_pergunta(casa, pfx):
    """O cancelamento lê ENVIANDO e pergunta à Sefin; nesse meio, outro clique
    reenvia e a DPS vira nota. Cancelar só aqui seria NFS-e válida lá sem
    registro na casa — a nota tem de continuar EMITIDA."""
    db = casa["db"]
    rid, nota = _na_fila(casa, 132)
    cfg, cert = _cfg(db), DPS.abrir_pfx(pfx, SENHA_DO_A1)
    real = NFSE.provedor_da_casa(cfg, cert)
    provedor = ProvedorComClique(real, ao_perguntar=lambda: NFSE.enviar(
        db, nota["id"], real, usuario="outro clique"))
    with pytest.raises(NFSE.NfseError, match="A nota mudou enquanto o cancelamento"):
        NFSE.cancelar(db, nota["id"], provedor=provedor, certificado=cert, cfg=cfg,
                      motivo="1", justificativa="Valor do serviço lançado errado",
                      usuario="teste")
    depois = _nota_do_recibo(db, rid)
    assert depois["situacao"] == NFSE.EMITIDA
    assert depois["chave"] == casa["sefin"].emitidas[nota["id_dps"]]["chave"]
    assert casa["sefin"].canceladas == set()


def test_resposta_que_chega_depois_do_cancelamento_e_da_nota_nova_avisa_sem_estourar(casa,
                                                                                      pfx):
    """A DPS em voo vira nota depois de cancelada aqui, e o recibo já tem a nota
    nova: as duas não cabem no índice de uma viva por recibo. Em vez do
    IntegrityError (500 na tela), o balcão lê a chave a cancelar no emissor."""
    db = casa["db"]
    rid, velha = _na_fila(casa, 133)
    cfg, cert = _cfg(db), DPS.abrir_pfx(pfx, SENHA_DO_A1)
    real = NFSE.provedor_da_casa(cfg, cert)

    def cancela_e_emite_outra():
        NFSE.cancelar(db, velha["id"], provedor=real, certificado=cert, cfg=cfg,
                      motivo="1", justificativa="Valor do serviço lançado errado",
                      usuario="teste")
        NFSE.emitir(db, rid, provedor=real, certificado=cert, cfg=cfg, usuario="teste")

    with pytest.raises(NFSE.NfseError, match="Cancele essa chave direto no emissor"):
        NFSE.enviar(db, velha["id"], ProvedorComClique(real, ao_emitir=cancela_e_emite_outra),
                    usuario="teste")
    chave = casa["sefin"].emitidas[velha["id_dps"]]["chave"]
    with db.connect() as con:
        notas = NFSE.notas_do_recibo(con, rid)
        rastro = NFSE.eventos(con, velha["id"])
    assert [n["situacao"] for n in notas] == [NFSE.CANCELADA, NFSE.EMITIDA]
    assert notas[0]["chave"] is None and notas[1]["chave"] != chave
    assert rastro[-1]["resultado"] == "alerta" and chave in rastro[-1]["mensagem"]


def test_danfse_baixa_uma_vez_e_a_segunda_via_sai_do_banco(casa):
    db = casa["db"]
    rid = _recibo(db, numero=131)
    _endereco(db)
    _emitir(casa, rid)
    nota = _nota_do_recibo(db, rid)
    c = casa["c"]
    primeira = c.get(f"/caixa/nfse/nota/{nota['id']}/danfse")
    assert primeira.status_code == 200 and primeira.data.startswith(b"%PDF-")
    casa["sefin"].fora_do_ar = True
    segunda = c.get(f"/caixa/nfse/nota/{nota['id']}/danfse")
    assert segunda.status_code == 200 and segunda.data == primeira.data
    assert sum(1 for _m, u in casa["sefin"].chamadas if "/danfse/" in u) == 1


# ------------------------------------------- desligada, papéis e segredo

def test_emissao_nasce_desligada_e_na_homologacao_e_nao_toca_a_rede(cg_casa_logada, sefin,
                                                                     credenciais):
    db = cg_casa_logada["db"]
    cfg = _cfg(db)
    assert (cfg["nfse_ligada"], cfg["nfse_ambiente"]) == ("0", "homologacao")
    rid = _recibo(db, numero=140)
    html = _emitir(cg_casa_logada, rid).get_data(as_text=True)
    assert "desligada" in html
    assert sefin.chamadas == []


def test_certificado_e_senha_ficam_fora_do_banco_e_do_rastro(cg_casa_logada, credenciais, pfx):
    c = cg_casa_logada["c"]
    from io import BytesIO
    html = c.post("/administrativo/gestor/nfse", data={
        "csrf_token": _token(c), "acao": "certificado", "senha": SENHA_DO_A1,
        "pfx": (BytesIO(pfx), "a1.pfx")}, content_type="multipart/form-data",
        follow_redirects=True).get_data(as_text=True)
    assert "SERVENTIA FICTICIA DE TESTE gravado" in html
    assert SENHA_DO_A1 not in html
    assert (credenciais / NFSE.ARQUIVO_DO_CERTIFICADO).read_bytes() == pfx
    with cg_casa_logada["db"].connect() as con:
        bd = banco(con)
        settings = json.dumps(bd.ler("SELECT key, value FROM settings ORDER BY key"))
        rastro = json.dumps(bd.ler("SELECT action, details FROM audit_logs ORDER BY id"))
    assert SENHA_DO_A1 not in settings and SENHA_DO_A1 not in rastro
    assert "NFSE_CERTIFICADO_GRAVADO" in rastro


def test_a_configuracao_e_do_admin_e_vai_ao_rastro(cg_casa_logada, credenciais):
    c = cg_casa_logada["c"]
    c.post("/administrativo/gestor/nfse", data={
        "csrf_token": _token(c), "acao": "configuracao", **CONFIG_LIGADA})
    db = cg_casa_logada["db"]
    assert _cfg(db)["nfse_ligada"] == "1"
    with db.connect() as con:
        rastro = banco(con).um("SELECT details FROM audit_logs WHERE action = %s "
                               "ORDER BY id DESC LIMIT 1", ("NFSE_CONFIGURACAO_ALTERADA",))
    assert '"nfse_ligada": {"de": "0", "para": "1"}' in rastro["details"]


def test_configuracao_com_aliquota_acima_de_cinco_por_cento_e_recusada(cg_casa_logada):
    with pytest.raises(NFSE.NfseError, match="máximo 5%"):
        NFSE.conferir_configuracao({**CONFIG_LIGADA, "nfse_aliquota": "6"})


def test_quem_nao_e_admin_nao_configura_e_o_auditor_nao_emite(casa):
    db, app = casa["db"], casa["app"]
    db.create_user("escrevente", "ESCREVENTE FICTICIA", "Senha#12345", "USER")
    db.create_user("auditora", "AUDITORA FICTICIA", "Senha#12345", "AUDITOR")
    rid = _recibo(db, numero=150)
    usuario = app.test_client()
    cg_login(usuario, "escrevente", "Senha#12345")
    assert usuario.get("/administrativo/gestor/nfse").status_code == 403
    assert usuario.get("/caixa/nfse").status_code == 200
    auditora = app.test_client()
    cg_login(auditora, "auditora", "Senha#12345")
    assert auditora.get(f"/caixa/nfse/recibo/{rid}").status_code == 200
    assert auditora.post(f"/caixa/nfse/recibo/{rid}/emitir",
                         data={"csrf_token": _token(auditora)}).status_code == 403
    assert casa["sefin"].chamadas == []


def test_post_sem_o_token_do_formulario_e_recusado(casa):
    rid = _recibo(casa["db"], numero=151)
    assert casa["c"].post(f"/caixa/nfse/recibo/{rid}/emitir").status_code == 400
    assert casa["sefin"].chamadas == []


def test_as_telas_abrem_e_a_fila_diz_o_que_falta(casa):
    db = casa["db"]
    _recibo(db, numero=160, documento=None)
    c = casa["c"]
    fila = c.get("/caixa/nfse")
    assert fila.status_code == 200
    assert "Falta o CPF ou CNPJ do tomador" in fila.get_data(as_text=True)
    assert c.get("/administrativo/gestor/nfse").status_code == 200
    assert "Emitir NFS-e" in c.get("/caixa/recibos").get_data(as_text=True)

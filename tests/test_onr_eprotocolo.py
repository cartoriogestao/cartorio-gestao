# -*- coding: utf-8 -*-
"""O e-Protocolo do RI pelo ONR — a ENTRADA dos títulos (RI013, P1, 24/11/2026).

O QUE ESTES TESTES GUARDAM
    **Só leitura.** Toda chamada que sai é `Login`, `List` ou `Get`; os `Set*`
    do serviço nem estão no contrato do módulo.
    **A ordem dos campos é a do WSDL de produção** (quando o contrato está na
    árvore, como nos outros serviços do WSOficio), e os nomes que o leitor usa
    existem nos tipos de resposta.
    **A fila sai na ordem da remessa** (CNN 326), e os avisos de contraditório,
    constrição, mandado e gratuidade se calculam na hora.
    **O XML da ficha se congela**: a segunda leitura não o regrava.
    **Nenhuma rede**: o transporte é um ONR de mentira que confere o hash.
"""
from __future__ import annotations

import contextlib
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import onr_eprotocolo as EP                                        # noqa: E402
import onr_wsoficio as W                                           # noqa: E402
from banco_de_teste import conexao_de_teste                        # noqa: E402
from bd_nativo import banco                                        # noqa: E402

CONTRATO = RAIZ.parent.parent / "FONTES_EXTERNAS" / "onr_wsoficio" / "producao"
WSDL = CONTRATO / "eprotocolo.wsdl"
X = "{http://www.w3.org/2001/XMLSchema}"
CHAVE = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"
CERT = {"SUBJECTCN": "FULANO DE TAL:00000004421", "ISSUERO": "ICP-Brasil",
        "PUBLICKEY": "3082010A0282010100AB", "SERIALNUMBER": "763222E368FD67A9",
        "VALIDUNTIL": "08/01/2028 16:10:00"}
HOJE = date(2026, 11, 24)
LEITURAS = ("ListPedidosAC", "GetPedidoAC_V8", "ListAnexosAC", "ListBoletosAC",
            "ListCustasAC", "GetExtratoXMLAC")


# ------------------------------------------------------------------ o ONR de mentira

def _soap(metodo: str, corpo: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap='
            '"http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            f'<{metodo}Response xmlns="{W.NS}"><{metodo}Result>{corpo}</{metodo}Result>'
            f'</{metodo}Response></soap:Body></soap:Envelope>')


def _item(contrato, protocolo, status, data, tipo=1):
    return (f"<ListPedidosAC_Pedidos_WSResp><IDContrato>{contrato}</IDContrato>"
            f"<Protocolo>{protocolo}</Protocolo><Instituicao>BANCO DE EXEMPLO</Instituicao>"
            f"<IDTipoServico>{tipo}</IDTipoServico><IDStatus>{status}</IDStatus>"
            f"<DataSolicitacao>{data}</DataSolicitacao></ListPedidosAC_Pedidos_WSResp>")


def _ficha(contrato, protocolo, *, remessa, matriculas=("1234",), status=1, extra="",
           prenotacao="", isencao=0):
    imoveis = "".join(f"<GetPedidoAC_Imovel_WSResp><Matricula>{m}</Matricula><Via>RUA</Via>"
                      f"<Endereco>DAS FLORES</Endereco><Numero>10</Numero>"
                      f"<Cidade>CIDADE EXEMPLO</Cidade><Estado>MA</Estado>"
                      f"</GetPedidoAC_Imovel_WSResp>" for m in matriculas)
    return ("<RETORNO>true</RETORNO><CODIGOERRO>0</CODIGOERRO>"
            f"<IDContrato>{contrato}</IDContrato><Protocolo>{protocolo}</Protocolo>"
            f"<IDStatus>{status}</IDStatus><IDCartorio>1234</IDCartorio>"
            f"<DataRemessa>{remessa}</DataRemessa><Solicitante>MARIA EXEMPLO</Solicitante>"
            "<Instituicao>BANCO DE EXEMPLO</Instituicao><TipoDocumento>1</TipoDocumento>"
            "<TipoServico>1</TipoServico><ImportacaoExtratoXML>false</ImportacaoExtratoXML>"
            "<DadosApresentante><Nome>JOAO APRESENTANTE</Nome><CPFCNPJ>00000000191</CPFCNPJ>"
            "</DadosApresentante>"
            f"<PrenotacaoNumero>{prenotacao}</PrenotacaoNumero><PrenotacaoSenha>XYZ</PrenotacaoSenha>"
            "<ValorServico>150.00</ValorServico><TipoCobranca>1</TipoCobranca>"
            "<CertidaoInteiroTeor>0</CertidaoInteiroTeor>"
            f"<TipoIsencao>{isencao}</TipoIsencao>"
            f"<DadosImovel>{imoveis}</DadosImovel>"
            "<Partes><GetPedidoAC_DadosParte_WSResp><Nome>FULANA COMPRADORA</Nome>"
            "<CPFCNPJ>00000000272</CPFCNPJ><Qualidade>Compradores</Qualidade>"
            "</GetPedidoAC_DadosParte_WSResp><GetPedidoAC_DadosParte_WSResp>"
            "<Nome>BELTRANO VENDEDOR</Nome><CPFCNPJ>00000000353</CPFCNPJ>"
            "<Qualidade>Vendedores</Qualidade></GetPedidoAC_DadosParte_WSResp></Partes>"
            + extra)


ANEXOS = ("<RETORNO>true</RETORNO><CODIGOERRO>0</CODIGOERRO>"
          "<AnexosContrato><ListAnexosAC_Anexos_WSResp><IDAnexo>71</IDAnexo>"
          "<Nome>escritura.pdf</Nome><URLAnexo>https://site-exemplo.invalid/a/71</URLAnexo>"
          "<Descricao>Escritura</Descricao><DataInclusao>2026-11-20</DataInclusao>"
          "</ListAnexosAC_Anexos_WSResp></AnexosContrato><AnexosAverbacao />"
          "<AnexosExigencia />")


class ONRDeMentira:
    """Confere o hash como o ONR confere e responde só as leituras."""

    def __init__(self, paginas: list[list[str]], fichas: dict[int, str], *,
                 falha_ficha: set[int] = frozenset(), anexos: str = ANEXOS):
        self.paginas, self.fichas, self.falha_ficha, self.anexos = paginas, fichas, falha_ficha, anexos
        self.emitidos, self.usados, self.chamadas = [], set(), []

    def __call__(self, url, corpo, acao):
        metodo = acao.rsplit("/", 1)[-1]
        xml = corpo.decode("utf-8")
        self.chamadas.append((url, metodo, xml))
        if metodo == "LoginUsuarioCertificado":
            tok = f"TK{len(self.emitidos):04d}"
            self.emitidos.append(tok)
            return 200, _soap(metodo, "<RETORNO>true</RETORNO><CODIGOERRO>0</CODIGOERRO>"
                                      "<IDUsuario>7</IDUsuario><IDInstituicao>99</IDInstituicao>"
                                      f"<Ativo>true</Ativo><Tokens><string>{tok}</string></Tokens>")
        h = re.search(r"<Hash>(.*?)</Hash>", xml).group(1)
        valido = [t for t in self.emitidos
                  if hashlib.sha1((CHAVE + t).encode()).hexdigest().upper() == h]
        assert valido and valido[0] not in self.usados, "hash inválido ou repetido"
        self.usados.add(valido[0])
        if metodo == "ListPedidosAC":
            pagina = int(re.search(r"<PageNumber>(\d+)</PageNumber>", xml).group(1))
            itens = self.paginas[pagina - 1]
            return 200, _soap(metodo, "<RETORNO>true</RETORNO><CODIGOERRO>0</CODIGOERRO>"
                                      f"<QtdeRegistros>{sum(map(len, self.paginas))}</QtdeRegistros>"
                                      f"<QtdePaginas>{len(self.paginas)}</QtdePaginas>"
                                      f"<Pedidos>{''.join(itens)}</Pedidos>")
        contrato = int(re.search(r"<IDContrato>(\d+)</IDContrato>", xml).group(1))
        if metodo == "GetPedidoAC_V8":
            if contrato in self.falha_ficha:
                return 200, _soap(metodo, "<RETORNO>false</RETORNO><CODIGOERRO>51</CODIGOERRO>"
                                          "<ERRODESCRICAO>Não foi possível obter os dados do "
                                          "contrato solicitado.</ERRODESCRICAO>")
            return 200, _soap(metodo, self.fichas[contrato])
        if metodo == "ListAnexosAC":
            return 200, _soap(metodo, self.anexos)
        raise AssertionError(f"método inesperado: {metodo}")

    def metodos(self):
        return [m for _, m, _ in self.chamadas]


class _Db:
    """A conexão de teste no papel de `db`: transação e conexão são a mesma."""

    def __init__(self, con):
        self.con = con

    def transaction(self):
        return contextlib.nullcontext(self.con)

    connect = transaction


def _con():
    con = conexao_de_teste()
    bd = banco(con)
    bd.escrever("CREATE TABLE ri_matriculas (id bigint PRIMARY KEY, numero TEXT, "
                "complemento TEXT NOT NULL DEFAULT '')")
    bd.escrever("INSERT INTO ri_matriculas(id, numero, complemento) VALUES "
                "(77, '1234', ''), (78, '1234', 'A'), (90, '555', '')")
    bd.escrever("CREATE TABLE ri_protocolos (id bigint PRIMARY KEY, numero INTEGER, "
                "data_prenotacao TEXT, matricula_id bigint, matricula_numero TEXT, "
                "natureza_titulo TEXT, situacao TEXT)")
    bd.escrever("CREATE TABLE cx_protocolos (id bigint PRIMARY KEY, numero TEXT, "
                "data_abertura TEXT, atribuicao TEXT, situacao TEXT, ri_protocolo_id bigint, "
                "ri_matricula_id bigint, assunto TEXT, observacao TEXT)")
    EP.init_schema(con)
    return con


@pytest.fixture()
def pasta(tmp_path):
    W.configurar(pasta=tmp_path, id_parceiro="2869", chave=CHAVE, cpf="000.000.044-21",
                 email="oficial@exemplo.org")
    return tmp_path


def _relogio():
    n = iter(range(3600))

    def agora():
        i = next(n)
        return f"2026-11-24T09:{i // 60:02d}:{i % 60:02d}"
    return agora


def _ler(con, pasta, onr, **kw):
    return EP.ler(_Db(con), W.PRODUCAO, hoje=HOJE, agora=_relogio(), pasta=pasta,
                  transporte=onr, certificado=CERT, **kw)


def _tres():
    """Três títulos: o 502 remetido ANTES do 501 (a ordem é a da remessa, não a
    do contrato), e o 503 já registrado (fechado: entra como registro)."""
    paginas = [[_item(501, "EP-501", 1, "2026-11-21"), _item(502, "EP-502", 1, "2026-11-20")],
               [_item(503, "EP-503", 7, "2026-11-10")]]
    fichas = {501: _ficha(501, "EP-501", remessa="2026-11-21", matriculas=("1.234",)),
              502: _ficha(502, "EP-502", remessa="2026-11-20", matriculas=("555",))}
    return paginas, fichas


# ------------------------------------------------------------------ o contrato

def test_os_metodos_sao_so_de_leitura_e_do_eprotocolo():
    for m in LEITURAS:
        assert m in W.CAMPOS and W.SERVICO_DO_METODO[m] == "eprotocolo"
        assert re.match(r"^(List|Get)", m)
    assert not [m for m, s in W.SERVICO_DO_METODO.items()
                if s == "eprotocolo" and not re.match(r"^(List|Get)", m)]
    assert W.SERVICOS["eprotocolo"] == "eprotocolo.asmx"


def test_o_envelope_vai_aninhado_em_orequest_e_na_ordem():
    corpo = W.envelope("ListPedidosAC", {
        "Hash": "H", "MaxRowPerPage": 50, "PageNumber": 1, "Protocolo": "", "Instituicao": "",
        "IDTipoServico": -1, "IDStatus": -1, "DataSolicitacaoInicial": "2026-10-25",
        "DataSolicitacaoFinal": "2026-11-24", "NumeroBanco": -1}).decode()
    raiz = ET.fromstring(corpo)
    metodo = raiz.find(f".//{{{W.NS}}}ListPedidosAC")
    req = metodo.find(f"{{{W.NS}}}oRequest")
    assert [c.tag.rsplit("}", 1)[-1] for c in req] == list(W.CAMPOS["ListPedidosAC"])
    with pytest.raises(W.WSOficioError):
        W.envelope("GetPedidoAC_V8", {"Hash": "H", "IDPedido": 1})


@pytest.mark.skipif(not WSDL.is_file(), reason="o contrato não está nesta árvore")
def test_a_ordem_dos_campos_e_a_do_wsdl_de_producao():
    raiz = ET.parse(WSDL).getroot()
    tipos = {ct.get("name"): tuple(e.get("name") for e in ct.findall(f"{X}sequence/{X}element"))
             for ct in raiz.iter(X + "complexType") if ct.get("name")}
    req = {e.get("name"): e.find(f"{X}complexType/{X}sequence/{X}element").get("type").split(":")[-1]
           for e in raiz.iter(X + "element")
           if e.get("name") in LEITURAS and e.find(f"{X}complexType/{X}sequence/{X}element") is not None}
    for metodo in LEITURAS:
        assert req[metodo] == W.TIPO_DO_PEDIDO_NO_WSDL.get(metodo, f"{metodo}_WSReq"), metodo
        assert tipos[req[metodo]] == W.CAMPOS[metodo], metodo
    assert f'location="{W.BASE[W.PRODUCAO]}/eprotocolo.asmx"' in WSDL.read_text(encoding="utf-8")


@pytest.mark.skipif(not WSDL.is_file(), reason="o contrato não está nesta árvore")
def test_os_nomes_que_o_leitor_usa_existem_na_resposta():
    raiz = ET.parse(WSDL).getroot()
    tipos = {ct.get("name"): {e.get("name") for e in ct.findall(f"{X}sequence/{X}element")}
             for ct in raiz.iter(X + "complexType") if ct.get("name")}
    ficha = tipos["GetPedidoAC_v8_WSResp"]
    assert {"IDContrato", "Protocolo", "IDStatus", "DataRemessa", "Solicitante", "Instituicao",
            "TipoDocumento", "TipoServico", "ImportacaoExtratoXML", "DadosApresentante",
            "PrenotacaoNumero", "PrenotacaoDataInclusao", "PrenotacaoDataVencimento",
            "ValorServico", "TipoCobranca", "TipoIsencao", "FundamentoLegal",
            "UrlArquivoGratuidade", "ProtocoloOrigem", "DadosImovel", "Partes",
            "DadosConstricao", "UrlArquivoMandado", "AverbacaoCDA"} <= ficha
    assert {"Matricula", "Via", "Endereco"} <= tipos["GetPedidoAC_Imovel_WSResp"]
    assert {"Nome", "CPFCNPJ", "Qualidade"} <= tipos["GetPedidoAC_DadosParte_WSResp"]
    assert {"TipoConstricao", "NumeroProcesso", "Vara", "ValorDivida"} <= \
        tipos["GetPedidoAC_DadosConstricao_WSResp"]
    assert {"IDContrato", "Protocolo", "Instituicao", "IDTipoServico", "IDStatus",
            "DataSolicitacao"} == tipos["ListPedidosAC_Pedidos_WSResp"]
    assert {"IDAnexo", "Nome", "URLAnexo", "Descricao", "DataInclusao"} == \
        tipos["ListAnexosAC_Anexos_WSResp"]
    assert set(W.GRUPOS_DE_ANEXO_EPROTOCOLO) <= tipos["ListAnexosAC_WSResp"]


# ------------------------------------------------------------------ a leitura

def test_le_grava_na_ordem_da_remessa_e_liga_a_matricula(pasta):
    con = _con()
    paginas, fichas = _tres()
    onr = ONRDeMentira(paginas, fichas)
    r = _ler(con, pasta, onr)
    assert r["situacao"] == "OK"
    assert (r["listados"], r["novos"], r["fichas"]) == (3, 3, 2)
    # SÓ LEITURA: nada além de Login, List e Get saiu daqui.
    assert all(re.match(r"^(Login|List|Get)", m) for m in onr.metodos())
    # O fechado (503, registrado) não pediu ficha nem anexos.
    assert not [x for _, m, x in onr.chamadas if "<IDContrato>503<" in x]
    lista = EP.fila_com_alertas(con)
    assert [p["protocolo"] for p in lista] == ["EP-502", "EP-501"]
    assert [p["posicao"] for p in lista] == [1, 2]
    ep501 = lista[1]
    assert ep501["imoveis"][0]["matricula_numero"] == "1234"
    assert ep501["imoveis"][0]["matricula_id"] == 77          # a sem complemento
    assert lista[0]["imoveis"][0]["matricula_id"] == 90
    assert ep501["apresentante_nome"] == "JOAO APRESENTANTE"
    todos = EP.fila(con, todos=True)
    assert {p["protocolo"]: p["situacao"] for p in todos}["EP-503"] == "FECHADO_NO_ONR"
    # Duas páginas: a segunda foi pedida.
    assert [re.search(r"<PageNumber>(\d+)<", x).group(1) for _, m, x in onr.chamadas
            if m == "ListPedidosAC"] == ["1", "2"]


def test_o_xml_se_congela_e_os_campos_se_achatam(pasta):
    con = _con()
    paginas, fichas = _tres()
    _ler(con, pasta, ONRDeMentira(paginas, fichas))
    p = EP.pedido(con, [x for x in EP.fila(con) if x["protocolo"] == "EP-501"][0]["id"])
    assert p["xml_pedido"].startswith("<GetPedidoAC_V8Result>")
    assert "<PrenotacaoSenha>XYZ</PrenotacaoSenha>" in p["xml_pedido"]
    assert p["xml_sha256"] == hashlib.sha256(p["xml_pedido"].encode()).hexdigest()
    assert p["dados"]["Partes/2/Nome"] == "BELTRANO VENDEDOR"
    assert p["dados"]["DadosImovel/1/Matricula"] == "1.234"
    assert [a["nome"] for a in p["anexos"]] == ["escritura.pdf"]
    assert p["anexos"][0]["url"] == "https://site-exemplo.invalid/a/71"
    assert p["anexos"][0]["grupo"] == "CONTRATO"
    # A segunda leitura, com a ficha MUDADA no ONR, não regrava o que a casa viu.
    fichas[501] = fichas[501].replace("MARIA EXEMPLO", "OUTRA PESSOA")
    onr = ONRDeMentira(paginas, fichas)
    r = _ler(con, pasta, onr)
    assert (r["novos"], r["fichas"]) == (0, 0)
    assert onr.metodos().count("GetPedidoAC_V8") == 0
    assert EP.pedido(con, p["id"])["xml_pedido"] == p["xml_pedido"]


def test_status_que_muda_atualiza_e_rele_os_anexos(pasta):
    con = _con()
    paginas, fichas = _tres()
    _ler(con, pasta, ONRDeMentira(paginas, fichas))
    paginas[0][0] = _item(501, "EP-501", 6, "2026-11-21")      # nota de exigência
    novo = ANEXOS.replace("<AnexosExigencia />",
                          "<AnexosExigencia><ListAnexosAC_Anexos_WSResp><IDAnexo>80</IDAnexo>"
                          "<Nome>cumprimento.pdf</Nome><URLAnexo>https://site-exemplo.invalid/a/80"
                          "</URLAnexo></ListAnexosAC_Anexos_WSResp></AnexosExigencia>")
    onr = ONRDeMentira(paginas, fichas, anexos=novo)
    r = _ler(con, pasta, onr)
    assert r["atualizados"] == 1 and onr.metodos().count("ListAnexosAC") == 1
    p = [x for x in EP.fila(con) if x["protocolo"] == "EP-501"][0]
    assert p["situacao"] == "EM_ANDAMENTO" and p["id_status"] == 6
    assert sorted(a["id_anexo"] for a in EP.anexos(con, p["id"])) == [71, 80]


def test_ficha_que_falha_nao_leva_as_outras_e_a_leitura_e_parcial(pasta):
    con = _con()
    paginas, fichas = _tres()
    r = _ler(con, pasta, ONRDeMentira(paginas, fichas, falha_ficha={502}))
    assert r["situacao"] == "PARCIAL" and r["fichas"] == 1
    assert "EP-502" in r["falhas"][0] and "51" in r["falhas"][0]
    p502 = [x for x in EP.fila(con) if x["protocolo"] == "EP-502"][0]
    assert not p502["ficha_lida"] and "51" in p502["erro_ficha"]
    # A leitura PARCIAL conta como bem-sucedida: a lista da remessa veio (CNN 325).
    assert EP.ultima_leitura(con)["situacao"] == "PARCIAL"
    # E a próxima leitura pede a ficha que faltou.
    onr = ONRDeMentira(paginas, fichas)
    assert _ler(con, pasta, onr)["fichas"] == 1


def test_o_limite_de_fichas_por_leitura(pasta):
    con = _con()
    paginas, fichas = _tres()
    r = _ler(con, pasta, ONRDeMentira(paginas, fichas), fichas_por_leitura=1)
    assert r["fichas"] == 1 and r["sobraram"] == 1


def test_onr_fora_do_ar_grava_a_leitura_com_erro_e_nada_mais(pasta):
    con = _con()

    def caiu(url, corpo, acao):
        raise W.WSOficioError("O Ofício Eletrônico do ONR não respondeu: tempo esgotado.")

    r = _ler(con, pasta, caiu)
    assert r["situacao"] == "ERRO" and "não respondeu" in r["erro"]
    assert EP.fila(con, todos=True) == []
    assert EP.ultima_leitura(con) is None
    assert EP.ultima_leitura(con, boa=False)["situacao"] == "ERRO"


def test_sem_credencial_nao_chama_ninguem(tmp_path):
    con = _con()
    chamou = []
    r = EP.ler(_Db(con), W.PRODUCAO, hoje=HOJE, agora=_relogio(), pasta=tmp_path,
               transporte=lambda *a: chamou.append(a), certificado=CERT)
    assert r["situacao"] == "ERRO" and "credencial" in r["erro"].lower() and chamou == []


def test_a_data_da_remessa_aceita_as_duas_formas():
    assert EP.data_iso("2026-11-20") == "2026-11-20"
    assert EP.data_iso("2026-11-20 14:05:09") == "2026-11-20T14:05:09"
    assert EP.data_iso("20/11/2026 14:05") == "2026-11-20T14:05"


# ------------------------------------------------------------------ os avisos

def _um(con, pasta, extra="", matriculas=("1234",), prenotacao="", isencao=0):
    paginas = [[_item(600, "EP-600", 1, "2026-11-22")]]
    fichas = {600: _ficha(600, "EP-600", remessa="2026-11-22", matriculas=matriculas,
                          extra=extra, prenotacao=prenotacao, isencao=isencao)}
    _ler(con, pasta, ONRDeMentira(paginas, fichas))
    return EP.fila_com_alertas(con)[0]


def _tipos(p):
    return [a["tipo"] for a in p["alertas"]]


def test_contraditorio_com_prenotacao_aberta_pela_amarracao_e_pelo_numero(pasta):
    con = _con()
    bd = banco(con)
    bd.escrever("INSERT INTO ri_protocolos VALUES (1, 11600, '2026-11-23', 77, NULL, "
                "'COMPRA E VENDA', 'ABERTO')")
    bd.escrever("INSERT INTO ri_protocolos VALUES (2, 11601, '2026-11-21', NULL, '1.234', "
                "NULL, 'DEVOLVIDO')")
    bd.escrever("INSERT INTO ri_protocolos VALUES (3, 11602, '2026-11-21', 77, NULL, NULL, "
                "'REGISTRADO')")
    p = _um(con, pasta)
    textos = [a["texto"] for a in p["alertas"] if a["tipo"] == "CONTRADITORIO_PRENOTACAO"]
    assert len(textos) == 2
    assert "11600" in textos[0] and "depois da remessa" in textos[0]
    assert "11601" in textos[1] and "antes da remessa" in textos[1]
    assert all(a["nivel"] == "perigo" for a in p["alertas"] if a["tipo"].startswith("CONTRA"))


def test_a_prenotacao_do_proprio_titulo_nao_e_contraditorio(pasta):
    con = _con()
    banco(con).escrever("INSERT INTO ri_protocolos VALUES (1, 11600, '2026-11-23', 77, NULL, "
                        "NULL, 'ABERTO')")
    p = _um(con, pasta, prenotacao="11600")
    assert p["situacao"] == "EM_ANDAMENTO"
    assert "CONTRADITORIO_PRENOTACAO" not in _tipos(p)


def test_contraditorio_com_titulo_de_balcao(pasta):
    con = _con()
    bd = banco(con)
    bd.escrever("INSERT INTO cx_protocolos VALUES (1, 'PG-9', '2026-11-22', 'RI', 'ABERTO', "
                "NULL, 77, 'Escritura', NULL)")
    bd.escrever("INSERT INTO cx_protocolos VALUES (2, 'PG-10', '2026-11-20', 'RI', 'ABERTO', "
                "NULL, NULL, 'Hipoteca da matrícula nº 1.234', NULL)")
    bd.escrever("INSERT INTO cx_protocolos VALUES (3, 'PG-11', '2026-11-20', 'NOTAS', 'ABERTO', "
                "NULL, 77, NULL, NULL)")
    bd.escrever("INSERT INTO cx_protocolos VALUES (4, 'PG-12', '2026-11-20', 'RI', 'ABERTO', "
                "5, 77, NULL, NULL)")
    p = _um(con, pasta)
    balcao = [a["texto"] for a in p["alertas"] if a["tipo"] == "CONTRADITORIO_BALCAO"]
    assert len(balcao) == 2
    assert "PG-9" in balcao[0] and "mesma matrícula" in balcao[0]
    assert "PG-10" in balcao[1] and "cita o número" in balcao[1]


def test_contraditorio_entre_dois_titulos_eletronicos(pasta):
    con = _con()
    paginas = [[_item(701, "EP-701", 1, "2026-11-20"), _item(702, "EP-702", 1, "2026-11-21")]]
    fichas = {701: _ficha(701, "EP-701", remessa="2026-11-20"),
              702: _ficha(702, "EP-702", remessa="2026-11-21")}
    _ler(con, pasta, ONRDeMentira(paginas, fichas))
    a, b = EP.fila_com_alertas(con)
    assert "CONTRADITORIO_ELETRONICO" in _tipos(a) and "CONTRADITORIO_ELETRONICO" in _tipos(b)
    assert "depois da remessa" in [x for x in a["alertas"] if x["tipo"] == "CONTRADITORIO_ELETRONICO"][0]["texto"]


def test_constricao_mandado_gratuidade_e_cda(pasta):
    con = _con()
    extra = ("<FundamentoLegal>Lei 1.060/50</FundamentoLegal>"
             "<UrlArquivoGratuidade>https://site-exemplo.invalid/g</UrlArquivoGratuidade>"
             "<DadosConstricao><TipoConstricao>PENHORA</TipoConstricao>"
             "<NumeroProcesso>0000001-00.2026.8.10.0001</NumeroProcesso>"
             "<Vara>1ª Vara de Exemplo</Vara><ValorDivida>1000.00</ValorDivida></DadosConstricao>"
             "<UrlArquivoMandado>https://site-exemplo.invalid/m</UrlArquivoMandado>"
             "<AverbacaoCDA><Dividas><Divida><NumeroCDA>9</NumeroCDA></Divida></Dividas>"
             "</AverbacaoCDA>")
    p = _um(con, pasta, extra=extra, isencao=1)
    tipos = _tipos(p)
    for t in ("CONSTRICAO", "MANDADO", "GRATUIDADE", "CDA"):
        assert t in tipos, t
    constr = [a["texto"] for a in p["alertas"] if a["tipo"] == "CONSTRICAO"][0]
    assert "PENHORA" in constr and "0000001-00.2026.8.10.0001" in constr
    assert "Lei 1.060/50" in [a["texto"] for a in p["alertas"] if a["tipo"] == "GRATUIDADE"][0]


def test_matricula_fora_do_acervo_e_ficha_sem_imovel(pasta):
    con = _con()
    p = _um(con, pasta, matriculas=("99999",))
    assert "MATRICULA_FORA_DO_ACERVO" in _tipos(p)
    assert "CONTRADITORIO_PRENOTACAO" not in _tipos(p)
    con2 = _con()
    p2 = _um(con2, pasta, matriculas=())
    assert "SEM_IMOVEL" in _tipos(p2)


# ------------------------------------------------------------------ o painel e a rodada

def test_o_painel_diz_a_ultima_leitura_boa_e_cobra_a_hora(pasta):
    con = _con()
    paginas, fichas = _tres()
    _ler(con, pasta, ONRDeMentira(paginas, fichas))
    boa = EP.ultima_leitura(con)["terminada_em"]
    quando = datetime.fromisoformat(boa)
    r = EP.resumo_do_painel(con, agora=quando, processo_ligado=True)
    assert r["a_prenotar"] == 2 and r["ultima_boa"]["terminada_em"] == boa
    assert not r["atrasada"]
    tarde = quando.replace(hour=quando.hour + 2)
    assert EP.resumo_do_painel(con, agora=tarde, processo_ligado=True)["atrasada"]
    # Desligado ou fora do expediente, não cobra.
    assert not EP.resumo_do_painel(con, agora=tarde, processo_ligado=False)["atrasada"]
    assert not EP.resumo_do_painel(con, agora=tarde, processo_ligado=True,
                                   no_expediente=False)["atrasada"]


def test_o_processo_nasce_desligado_so_le_e_roda_na_abertura():
    import automacao as AUTO
    import automacao_processos as PROC
    (cat,) = EP.CATALOGO
    assert cat["codigo"] == "RI_ONR_EPROTOCOLO" and cat["setor"] == "RI"
    ag = AUTO.normalizar_agenda(cat["agenda"])
    assert ag["dias"] == [0, 1, 2, 3, 4]                         # dias úteis
    assert ag["intervalo_min"] <= 15                             # CNN 325: ≤ 60
    # A janela é o ponto de partida: o primeiro horário do dia é a abertura.
    slots = AUTO._slots_do_dia(ag, date(2026, 11, 24))
    assert slots[0].strftime("%H:%M") == "08:00" and slots[-1].strftime("%H:%M") == "18:00"
    assert not AUTO._slots_do_dia(ag, date(2026, 11, 22))         # domingo
    assert "pode_agir" not in cat and "ativo" not in cat
    sementes = {s["codigo"]: s for s in PROC.sementes_de_outros_modulos()}
    assert sementes["RI_ONR_EPROTOCOLO"]["alvo"] == "onr_eprotocolo:rodada"


class _Ctx:
    def __init__(self, con, pasta):
        self.db, self.pasta_dados, self.parametros = _Db(con), pasta, {}
        self.hoje, self.agora = HOJE, datetime(2026, 11, 24, 9, 0)
        self.pode_agir = False

    def setting(self, chave, padrao=""):
        return padrao


def test_a_rodada_le_e_avisa_o_que_espera_a_casa(pasta, monkeypatch):
    con = _con()
    paginas, fichas = _tres()
    onr = ONRDeMentira(paginas, fichas)
    # A rodada fala pelo transporte da casa: aqui ele é o ONR de mentira, e o
    # certificado é o de ensaio (sem o PowerShell do Windows).
    monkeypatch.setattr(W, "_transporte_da_casa", onr)
    original = W.Sessao.__init__
    monkeypatch.setattr(W.Sessao, "__init__",
                        lambda self, **kw: original(self, **{**kw, "certificado": CERT}))
    r = EP.rodada(_Ctx(con, pasta))
    assert r["situacao"] == "AVISO"
    assert "2 esperando prenotação" in r["relato"]
    assert [a["protocolo"] for a in r["achados"]] == ["EP-502", "EP-501"]
    assert all(re.match(r"^(Login|List|Get)", m) for m in onr.metodos())


def test_a_rodada_sem_credencial_avisa_e_nao_chama(tmp_path, monkeypatch):
    con = _con()
    monkeypatch.setattr(W, "_transporte_da_casa", lambda *a: pytest.fail("chamou o ONR"))
    r = EP.rodada(_Ctx(con, tmp_path))
    assert r["situacao"] == "AVISO" and "credencial" in r["relato"]


# ------------------------------------------------------------------ as telas

def test_as_telas_mostram_a_fila_a_ficha_e_o_painel(cg_casa_logada, monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    tela = c.get("/ri/onr/eprotocolo").get_data(as_text=True)
    assert "títulos remetidos pelo e-Protocolo" in tela and "nenhuma ainda" in tela
    assert "Ler agora no ONR" in tela and "RI_ONR_EPROTOCOLO" in tela
    # Antes da primeira leitura e com o processo desligado, o painel não fala.
    assert "e-Protocolo do RI (ONR)" not in c.get("/").get_data(as_text=True)

    with db.transaction() as con:
        lid = EP.abrir_leitura(con, W.PRODUCAO, EP.ORIGEM_TELA, "2026-11-24T09:00:00")
        item = EP.itens_da_lista(_soap("ListPedidosAC",
                                       "<RETORNO>true</RETORNO><QtdePaginas>1</QtdePaginas>"
                                       f"<Pedidos>{_item(900, 'EP-900', 1, '2026-11-24')}</Pedidos>"))[0][0]
        pid = EP.guardar_da_lista(con, W.PRODUCAO, item, "2026-11-24T09:00:01")["pedido_id"]
        EP.guardar_ficha(con, pid, EP.resultado_cru(
            _soap("GetPedidoAC_V8", _ficha(900, "EP-900", remessa="2026-11-24",
                                           matriculas=("424242",))), "GetPedidoAC_V8"),
            "2026-11-24T09:00:02")
        EP.guardar_anexos(con, pid, _soap("ListAnexosAC", ANEXOS), "2026-11-24T09:00:03")
        EP.fechar_leitura(con, lid, "OK", "2026-11-24T09:00:04", listados=1, novos=1, fichas=1)

    tela = c.get("/ri/onr/eprotocolo").get_data(as_text=True)
    assert "EP-900" in tela and "1º" in tela and "2026-11-24 09:00" in tela
    ficha = c.get(f"/ri/onr/eprotocolo/{pid}").get_data(as_text=True)
    assert "JOAO APRESENTANTE" in ficha and "escritura.pdf" in ficha
    assert "FULANA COMPRADORA" in ficha and "424242" in ficha and "não achada" in ficha
    painel = c.get("/").get_data(as_text=True)
    assert "e-Protocolo do RI (ONR)" in painel and "Esperando prenotação" in painel
    assert "09:00" in painel

    # O botão chama a MESMA leitura da rodada, com origem TELA.
    visto = {}

    def ler_falso(db_, amb, **kw):
        visto.update(kw, amb=amb)
        return {"situacao": "OK", "leitura_id": 1, "listados": 0, "novos": 0,
                "atualizados": 0, "fichas": 0, "sobraram": 0, "falhas": []}

    import onr_eprotocolo_web as EW
    monkeypatch.setattr(EW.EP, "ler", ler_falso)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', tela).group(1)
    r = c.post("/ri/onr/eprotocolo/ler", data={"csrf_token": tok, "dias": "7"},
               follow_redirects=True).get_data(as_text=True)
    assert "e-Protocolo lido (7 dias)" in r
    assert visto["origem"] == EP.ORIGEM_TELA and visto["dias"] == 7 and visto["amb"] == W.PRODUCAO


def test_o_balcao_ve_mas_nao_le_no_onr(cg_casa):
    from conftest import cg_login
    cg_casa["db"].create_user("ana", "Ana de Exemplo", "Senha#12345", "USER")
    c = cg_casa["c"]
    cg_login(c, "ana", "Senha#12345")
    tela = c.get("/ri/onr/eprotocolo").get_data(as_text=True)
    assert "títulos remetidos pelo e-Protocolo" in tela and "Ler agora no ONR" not in tela
    assert c.post("/ri/onr/eprotocolo/ler", data={}).status_code in (302, 400, 403)

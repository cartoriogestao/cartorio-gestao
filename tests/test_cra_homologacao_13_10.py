"""O que o teste na homologação da CRA (11 e 13/10/2026) ensinou, guardado em teste.

A CRA aceitou (código 0000) a confirmação `C2371609.263` montada assim: o lote
da remessa devolvido em XML, com o protocolo dentro, e o nome FEBRABAN. E
recusou o que o sistema fazia antes: texto de 600 posições («10000»), nome
interno («0002»). O retorno passou de «9999» a «0000» com o cabeçalho e o
rodapé preenchidos como o E-Ofício mandava. E o andamento vai pela
`TituloComplemento`, em `<complementos>` — os 7 títulos voltaram «2322»; pela
`Retorno` a resposta vinha vazia. Ver
DOCUMENTACAO/CRA_HOMOLOGACAO_TESTE_2026-10-13.md.
"""
from __future__ import annotations

import sqlite3
import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED  # noqa: E402
import cra21_api as API  # noqa: E402
import protesto_cra_envio as ENV  # noqa: E402
import protesto_cra_xml as PCX  # noqa: E402
import protesto_remessa as PRM  # noqa: E402
import protesto_retorno as PR  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-08-25T12:00:00"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
EXEMPLO = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    yield c
    c.close()


def _receber(con):
    return PRM.receber(con, EXEMPLO, agora=AGORA,
                       data_extenso="vinte e cinco de agosto", sv=SV)


def _linhas(texto):
    return [x for x in texto.replace("\r", "").split("\n") if x.strip()]


# ------------------------------------------------------------- o XML

def test_o_xml_tem_a_forma_do_exemplo_oficial_da_p21():
    texto = (Path(__file__).parent / "cra_confirmacao_exemplo.txt").read_text(
        encoding="latin-1")
    raiz = ET.fromstring(PCX.escrever_xml(texto, "SDTBFOCRT").encode("latin-1"))
    assert raiz.tag == "confirmacao"
    hd, tl = raiz.find("hd"), raiz.find("tl")
    assert len(hd.attrib) == 17 and len(tl.attrib) == 8
    assert all(len(tr.attrib) == 52 for tr in raiz.findall("tr"))
    # sem o preenchimento de espaços, e os zeros dos numéricos ficam
    assert hd.get("h03") == hd.get("h03").strip() and hd.get("h17") == "0001"


def test_o_andamento_nao_vira_o_arquivo_de_600_em_xml():
    """Pela `Retorno`, o andamento em XML de 600 posições voltou vazio: ele tem
    XML próprio, na `TituloComplemento`."""
    with pytest.raises(PCX.RemessaXmlError, match="TituloComplemento"):
        PCX.escrever_xml("0" * 600, "SDTBFOAND")


# ------------------------------------------------- a confirmação

def test_a_confirmacao_devolve_o_lote_da_remessa_com_o_protocolo(con):
    r = _receber(con)
    conf = con.execute("SELECT * FROM pt_retornos WHERE id=?",
                       (r["confirmacoes"][0],)).fetchone()
    remessa = _linhas(EXEMPLO.decode("latin-1"))
    saida = _linhas(conf["conteudo"])
    # cabeçalho: o da remessa, com SDT/BFO/CRT no lugar de BFO/SDT/TPR
    assert saida[0][52:61] == "SDTBFOCRT"
    assert saida[0][:52] == remessa[0][:52] and saida[0][61:] == remessa[0][61:]
    # rodapé: o da remessa
    assert saida[-1] == remessa[-1]
    # título: o protocolo e a data dele no bloco 446–485
    tit = con.execute("SELECT protocolo FROM pt_titulos").fetchone()["protocolo"]
    linha = saida[1]
    assert linha[445:447] == "01" and linha[447:457].strip() == tit
    assert linha[458:466] == f"{tit[4:6]}{tit[2:4]}20{tit[0:2]}"
    # e o nome FEBRABAN, com a data da REMESSA (cabeçalho)
    dia = remessa[0][44:52]
    assert conf["nome_arquivo"] == f"C001{dia[:4]}.{dia[6:8]}1"


def test_a_sequencia_do_nome_conta_os_arquivos_do_dia(con):
    for i in range(1, 4):
        con.execute("""INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
                           numero_da_remessa, nome_arquivo, conteudo, gerado_em)
                       VALUES ('SDTBFOCRT','237','2026-09-16',1,?,'x','agora')""",
                    (PR.nome_do_arquivo("SDTBFOCRT", "237", "2026-09-16", con=con),))
    nomes = [x[0] for x in con.execute("SELECT nome_arquivo FROM pt_retornos")]
    assert nomes == ["C2371609.261", "C2371609.262", "C2371609.263"]
    with pytest.raises(PR.RetornoError):
        PR.nome_do_arquivo("SDTBFOCRT", "237", "2026-09-16", sequencia=10)


# --------------------------------------------------------- o envio

class _Transacoes:
    """Quem abre a transação, contando se há uma aberta quando a rede corre."""

    def __init__(self, con):
        self.con, self.aberta = con, False

    @contextmanager
    def __call__(self):
        self.aberta = True
        try:
            yield self.con
        finally:
            self.aberta = False


#: O que a homologação respondeu ao andamento (13/10/2026), reduzido a um título.
RESPOSTA_DO_COMPLEMENTO = (
    '<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>'
    "<complementos><apresentantes><apresentante><codigo>001</codigo><titulos>"
    "<titulo><protocolo>{prot}</protocolo><mensagens><andamento>"
    "<codigo>{codigo}</codigo><descricao>Andamento inserido.</descricao>"
    "</andamento></mensagens></titulo></titulos></apresentante></apresentantes>"
    "</complementos>")


def test_a_rede_corre_fora_da_transacao(con, monkeypatch):
    r = _receber(con)
    a = PR.gerar_andamento(con, apresentante_codigo="001", dia="2026-08-25",
                           agora=AGORA)
    prot = con.execute("SELECT protocolo FROM pt_titulos").fetchone()[0]
    tx = _Transacoes(con)
    vistos = []

    def falso_envio(nome, dados, ambiente, pasta=None):
        vistos.append(("Confirmacao", nome, dados[:60], tx.aberta))
        return "<relatorio><codigo>0000</codigo></relatorio>"

    def falsa_chamada(operacao, ambiente, *, o_que, pasta=None, **campos):
        vistos.append((operacao, campos["userArq"], campos["userDados"], tx.aberta))
        return RESPOSTA_DO_COMPLEMENTO.format(prot=prot, codigo="2322")

    monkeypatch.setattr(API, "enviar_confirmacao", falso_envio)
    monkeypatch.setattr(API, "chamar", falsa_chamada)
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)
    # 14/10/2026 («agora é tudo produção»): era HOMOLOGACAO, com o envio
    # automático dela ligado de fábrica; agora é PRODUCAO, com a caixa ligada.
    envio = ENV.enviar_pos_remessa(
        tx, lotes=r["lotes"], andamentos=[("001", a)],
        ambiente=CRED.PRODUCAO, ler_config=lambda k, d: "1")
    assert not envio["falhas"], envio["falhas"]
    assert [v[0] for v in vistos] == ["Confirmacao", "TituloComplemento"]
    assert not any(v[3] for v in vistos)   # nenhuma transação durante a rede
    assert vistos[0][2].startswith('<?xml') and vistos[0][1].startswith("C001")
    assert vistos[1][1].startswith("M001") and "<complementos>" in vistos[1][2]
    for rid in (r["confirmacoes"][0], a["andamento_id"]):
        assert con.execute("SELECT cra_enviado_em FROM pt_retornos WHERE id=?",
                           (rid,)).fetchone()[0]


def test_sem_a_confirmacao_o_andamento_nao_sai(con, monkeypatch):
    r = _receber(con)
    a = PR.gerar_andamento(con, apresentante_codigo="001", dia="2026-08-25",
                           agora=AGORA)
    chamadas = []

    def recusa(nome, dados, ambiente, pasta=None):
        return "<relatorio><codigo>9999</codigo><descricao>erro</descricao></relatorio>"

    monkeypatch.setattr(API, "enviar_confirmacao", recusa)
    monkeypatch.setattr(API, "chamar", lambda *a, **k: chamadas.append(a) or "")
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)
    envio = ENV.enviar_pos_remessa(
        _Transacoes(con), lotes=r["lotes"], andamentos=[("001", a)],
        ambiente=CRED.PRODUCAO, ler_config=lambda k, d: "1")
    assert not chamadas and not envio["enviados"]
    assert {f["operacao"] for f in envio["falhas"]} == {"Confirmacao",
                                                         "TituloComplemento"}


def test_andamento_e_nome_antigo_sao_recusados_antes_da_rede(con):
    con.execute("""INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
                       numero_da_remessa, nome_arquivo, conteudo, gerado_em)
                   VALUES ('SDTBFOAND','001','2026-10-13',1,'M0011310.261','x','agora')""")
    con.execute("""INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
                       numero_da_remessa, nome_arquivo, conteudo, gerado_em)
                   VALUES ('SDTBFOCRT','001','2026-10-13',1,
                           'SDTBFOCRT-001-20261013-001.txt','x','agora')""")
    andamento, antigo = con.execute("SELECT * FROM pt_retornos ORDER BY id").fetchall()
    with pytest.raises(ENV.CraEnvioError, match="conexão"):
        ENV._preparar(andamento)               # o andamento se monta do banco
    with pytest.raises(ENV.CraEnvioError, match="0002"):
        ENV._preparar(antigo)


# ------------------------------------------------------- o andamento

def test_o_cabecalho_do_andamento_leva_o_nome_do_apresentante(con):
    _receber(con)
    cab = con.execute("SELECT apresentante_nome FROM pt_remessas").fetchone()[0]
    a = PR.gerar_andamento(con, apresentante_codigo="001", dia="2026-08-25",
                           agora=AGORA)
    linha = con.execute("SELECT conteudo FROM pt_retornos WHERE id=?",
                        (a["andamento_id"],)).fetchone()[0]
    assert _linhas(linha)[0][4:44].strip() == cab


def test_o_andamento_vai_no_xml_do_manual_da_p21(con):
    _receber(con)
    a = PR.gerar_andamento(con, apresentante_codigo="001", dia="2026-08-25",
                           agora=AGORA)
    xml = ENV.montar_complemento(con, a["andamento_id"], "2026-08-25T12:00:00")
    raiz = ET.fromstring(xml.encode("latin-1"))
    assert raiz.tag == "complementos"
    ap = raiz.find("apresentantes/apresentante")
    assert ap.findtext("codigo") == "001"
    tit = ap.find("titulos/titulo")
    prot = tit.findtext("protocolo")
    assert tit.findtext("data_protocolo") == f"{prot[4:6]}/{prot[2:4]}/20{prot[0:2]}"
    assert "." in tit.findtext("valor") and "," not in tit.findtext("valor")
    assert tit.findtext("andamentos/andamento/codigo") == "AA"
    assert tit.findtext("andamentos/andamento/data") == "25/08/2026 12:00:00"


def test_a_resposta_do_andamento_e_lida_titulo_a_titulo():
    ok = ENV.interpretar_resposta_complemento(
        RESPOSTA_DO_COMPLEMENTO.format(prot="2608250001", codigo="2322"), o_que="x")
    assert ok["ok"] and ok["codigo"] == "2322"
    with pytest.raises(API.CraRecusou, match="2608250001: 2301"):
        ENV.interpretar_resposta_complemento(
            RESPOSTA_DO_COMPLEMENTO.format(prot="2608250001", codigo="2301"),
            o_que="x")
    with pytest.raises(API.CraRecusou, match="sem conteúdo"):
        ENV.interpretar_resposta_complemento("", o_que="x")


# --------------------------------------------------------- o retorno

def test_o_retorno_sai_preenchido_como_o_eoficio_mandava(con):
    """A CRA respondeu «9999» ao retorno com o cabeçalho 68–100 e o rodapé 58–60
    em branco, e «0000» depois do ajuste (homologação, 13/10/2026)."""
    import protesto as PT
    r = _receber(con)
    tid = con.execute("SELECT id FROM pt_titulos").fetchone()[0]
    PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso="hoje")
    g = PR.gerar(con, apresentante_codigo="001", dia="2026-08-25", agora=AGORA)
    texto = con.execute("SELECT conteudo FROM pt_retornos WHERE id=?",
                        (g["retorno_id"],)).fetchone()[0]
    cab, tit, rod = _linhas(texto)[0], _linhas(texto)[1], _linhas(texto)[-1]
    remessa = _linhas(EXEMPLO.decode("latin-1"))[0]
    assert cab[67:71] == "0001" and cab[71:83] == "0" * 12
    assert cab[89:100].strip() == remessa[89:100].strip()   # 043 + IBGE da remessa
    assert tit[507:517] == "0" * 10 and tit[567:577] == "0" * 10
    assert rod[57:75].isdigit()                               # a soma em 18 dígitos
    assert r["confirmacoes"]

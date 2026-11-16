"""A CONFIRMAÇÃO PARCIAL DO LOTE QUE TEM TÍTULO COM MAIS DE UM DEVEDOR.

O QUE FICOU PENDENTE EM 10/11/2026
    A CRA mandou uma remessa em que um título tinha dois devedores: duas linhas de
    transação, e o cabeçalho contando UM título. O leitor recusava («h10 difere»), e
    o PR #396 o consertou: `protesto_cra_xml._quantidade_de_titulos` conta a linha
    que ABRE título (número de controle do devedor «1», o t22), e não a do devedor
    seguinte. A montagem da confirmação PARCIAL ficou contando linhas.

O DEFEITO
    Com recusa no lote, `_contagens_do_que_entrou` punha em h10 a quantidade de
    LINHAS que entraram e fechava h11 + h12 contra o total de linhas. Num lote com
    codevedor a confirmação saía com o cabeçalho que o próprio leitor recusa — e a
    CRA devolve 2122 quando o total do cabeçalho não confere.

O QUE ESTES TESTES GUARDAM
      - a confirmação parcial fecha pela MESMA régua que `protesto_cra_xml.ler`
        cobra da remessa: h10 e h11 + h12 em títulos, t05 como somatório de
        segurança, t06 como soma dos saldos de todas as linhas;
      - recusar só o devedor seguinte não tira título nenhum do cabeçalho;
      - o lote sem codevedor continua saindo como saía (`test_protesto_remessa`).

SEM BANCO, DE PROPÓSITO. A montagem só pede ao banco o protocolo de cada título e
grava o arquivo; aqui um dublê responde as duas coisas, e o que se confere é o
texto que iria à CRA. As linhas são sintéticas: só os campos que a conta lê.

O QUE NÃO ESTÁ MEDIDO, e estes testes não afirmam: o que a CRA faz quando a linha
do primeiro devedor é recusada e a do seguinte entra. A casa conta pela régua do
leitor (a linha que sobra não abre título), e a tela da conferência já avisa esse
caso antes de receber.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protesto_cra_xml as PCX
import protesto_remessa as PRM
import protesto_retorno as PRE

AGORA = "2026-11-16T12:00:00"
SALDO = 148278


# ------------------------------------------------------------- o lote sintético


def _registro(tag: str, campos: dict[int, str]) -> str:
    """Uma linha de 600 posições com os campos dados; o resto em branco."""
    partes = []
    for k, largura in enumerate(PCX.LARGURAS[tag], start=1):
        partes.append(str(campos.get(k, "")).ljust(largura)[:largura])
    linha = "".join(partes)
    assert len(linha) == 600
    return linha


def _lote(controles: str, *, h09: int | None = None, h11_h12: tuple[int, int] | None = None,
          t05: int | None = None) -> str:
    """Um lote como a CRA manda: uma linha por devedor, o cabeçalho contando TÍTULOS.

    `controles` é o número de controle de cada linha, na ordem: "121" são dois
    títulos, o primeiro com dois devedores.
    """
    titulos = controles.count("1")
    h09 = titulos if h09 is None else h09
    h11, h12 = (titulos, 0) if h11_h12 is None else h11_h12
    t05 = h09 + titulos + h11 + h12 if t05 is None else t05
    linhas = [_registro("hd", {1: "0", 2: "001", 3: "APRESENTANTE EXEMPLO", 4: "16112026",
                               5: "BFO", 6: "SDT", 7: "TPR", 8: "000001",
                               9: f"{h09:04d}", 10: f"{titulos:04d}", 11: f"{h11:04d}",
                               12: f"{h12:04d}", 17: "0001"})]
    numero = 0
    for i, controle in enumerate(controles, start=1):
        numero += controle == "1"
        linhas.append(_registro("tr", {
            1: "1", 2: "001", 11: f"TIT-{numero}", 18: f"{SALDO:014d}", 22: controle,
            23: f"DEVEDOR EXEMPLO {i}", 52: f"{i + 1:04d}"}))
    linhas.append(_registro("tl", {1: "9", 2: "001", 3: "APRESENTANTE EXEMPLO", 4: "16112026",
                                   5: f"{t05:05d}", 6: f"{SALDO * len(controles):018d}",
                                   8: f"{len(controles) + 2:04d}"}))
    return "\r\n".join(linhas) + "\r\n"


class _Banco:
    """O dublê do banco: devolve o protocolo do título e guarda o que seria gravado."""

    def __init__(self):
        self.gravado = None

    def um(self, _sql, parametros):
        return {"protocolo": f"2611160{int(parametros[0]):03d}"}

    def escrever(self, _sql, parametros):
        self.gravado = parametros
        return [{"id": 1}]


def _confirmar(monkeypatch, controles: str, entram: tuple[int, ...], **contagens) -> list[str]:
    """A confirmação do lote em que só as linhas `entram` (1, 2, 3…) foram aceitas."""
    banco = _Banco()
    monkeypatch.setattr(PRM, "banco", lambda _con: banco)
    monkeypatch.setattr(PRE, "nome_do_arquivo", lambda *a, **k: "C0011611.261")
    visto = {"titulos": [{"sequencial": i} for i in range(1, len(controles) + 1)],
             "conteudo": _lote(controles, **contagens), "apresentante_codigo": "001",
             "apresentante_nome": "APRESENTANTE EXEMPLO", "dia": "2026-11-16",
             "numero_da_remessa": 1}
    feito = PRM._confirmar(None, remessa_id=1, visto=visto,
                           entraram=[{"titulo_id": i, "sequencial": i} for i in entram],
                           agora=AGORA, marca=None, usuario="teste")
    linhas = [x for x in feito["conteudo"].split("\r\n") if x]
    assert all(len(x) == 600 for x in linhas)
    return linhas


def _pela_regua_do_leitor(linhas: list[str]) -> dict:
    """As contas que `protesto_cra_xml.ler` cobra de um lote, sobre a confirmação."""
    xml = PCX.escrever_xml("\r\n".join(linhas) + "\r\n", "SDTBFOCRT")
    raiz = ET.fromstring(xml.encode("latin-1"))
    hd, trs, tl = raiz.find("hd"), raiz.findall("tr"), raiz.find("tl")
    titulos = PCX._quantidade_de_titulos(trs)
    return {"titulos": titulos, "linhas": len(trs),
            "h09": int(hd.get("h09")), "h10": int(hd.get("h10")),
            "h11": int(hd.get("h11")), "h12": int(hd.get("h12")),
            "t05": int(tl.get("t05")), "t06": int(tl.get("t06")),
            "saldos": sum(int(t.get("t18")) for t in trs),
            "sequencia": [int(hd.get("h17")), *(int(t.get("t52")) for t in trs),
                          int(tl.get("t08"))]}


def _fecha(c: dict) -> None:
    assert c["h10"] == c["titulos"], "h10 conta títulos, e não linhas"
    assert c["h11"] + c["h12"] == c["titulos"], "indicações mais originais fecham nos títulos"
    assert c["t05"] == c["h09"] + c["h10"] + c["h11"] + c["h12"], "somatório de segurança"
    assert c["t06"] == c["saldos"], "o saldo soma todas as linhas"
    assert c["sequencia"] == list(range(1, c["linhas"] + 3))


# ------------------------------------------------------------- o defeito


def test_recusado_o_titulo_simples_fica_um_titulo_com_dois_devedores(monkeypatch):
    """Duas linhas entram, e são UM título: o cabeçalho tem de dizer 1."""
    c = _pela_regua_do_leitor(_confirmar(monkeypatch, "121", entram=(1, 2)))
    assert (c["linhas"], c["titulos"]) == (2, 1)
    _fecha(c)
    assert (c["h09"], c["h10"], c["h11"], c["h12"], c["t05"]) == (1, 1, 1, 0, 3)


def test_recusado_o_titulo_de_dois_devedores_fica_o_simples(monkeypatch):
    """Saem duas linhas e UM título: h09 e h11 descem um, e não dois."""
    c = _pela_regua_do_leitor(_confirmar(monkeypatch, "121", entram=(3,)))
    assert (c["linhas"], c["titulos"]) == (1, 1)
    _fecha(c)
    assert (c["h09"], c["h10"], c["h11"], c["h12"], c["t05"]) == (1, 1, 1, 0, 3)


def test_recusado_so_o_devedor_seguinte_nenhum_titulo_sai_do_cabecalho(monkeypatch):
    c = _pela_regua_do_leitor(_confirmar(monkeypatch, "121", entram=(1, 3)))
    assert (c["linhas"], c["titulos"]) == (2, 2)
    _fecha(c)
    assert (c["h09"], c["h10"], c["h11"], c["h12"], c["t05"]) == (2, 2, 2, 0, 6)


@pytest.mark.parametrize("controles,entram", [
    ("1211", (1, 2, 3)), ("1211", (3, 4)), ("1121", (1, 4)), ("1231", (1, 2, 3)),
    ("12121", (1, 2, 5)), ("12121", (3, 4)),
])
def test_a_parcial_com_codevedor_fecha_pela_regua_do_leitor(monkeypatch, controles, entram):
    _fecha(_pela_regua_do_leitor(_confirmar(monkeypatch, controles, entram=entram)))


@pytest.mark.parametrize("h11_h12", [(2, 0), (0, 2), (1, 1)])
def test_indicacoes_e_originais_fecham_nos_titulos_que_entraram(monkeypatch, h11_h12):
    """A divisão do lote misto continua sem medida: aqui só se cobra a conta."""
    c = _pela_regua_do_leitor(_confirmar(monkeypatch, "121", entram=(1, 2), h11_h12=h11_h12))
    _fecha(c)
    if 0 in h11_h12:                       # quem tem um tipo só continua com ele
        assert (c["h11"] == 0) == (h11_h12[0] == 0)


def test_o_h09_que_veio_contando_linhas_continua_contando_linhas(monkeypatch):
    """O layout chama o h09 de registros. Se a remessa o trouxe em linhas, desce em linhas."""
    c = _pela_regua_do_leitor(_confirmar(monkeypatch, "121", entram=(3,), h09=3))
    _fecha(c)
    assert c["h09"] == 1 and c["h10"] == 1


# ------------------------------------------------------------- o que não muda


def test_lote_sem_codevedor_sai_como_saia(monkeypatch):
    c = _pela_regua_do_leitor(_confirmar(monkeypatch, "111", entram=(1, 3)))
    _fecha(c)
    assert (c["h09"], c["h10"], c["h11"], c["h12"], c["t05"]) == (2, 2, 2, 0, 6)


def test_controle_em_branco_e_arquivo_antigo_e_cada_linha_abre_titulo(monkeypatch):
    """Como no leitor: o arquivo que não traz o controle é lido como sempre foi."""
    linhas = _confirmar(monkeypatch, "   ", entram=(1, 3), h09=3, h11_h12=(3, 0), t05=9)
    assert (linhas[0][67:71], linhas[0][71:75], linhas[0][75:79], linhas[0][79:83]) == (
        "0002", "0002", "0002", "0000")
    assert linhas[-1][52:57] == "00006"


def test_o_rodape_que_conta_registros_continua_contando_registros(monkeypatch):
    """O lote TXT cujo t05 é cabeçalho + linhas + rodapé: 5 viram 4, com codevedor ou sem."""
    linhas = _confirmar(monkeypatch, "121", entram=(1, 2), t05=5)
    assert linhas[-1][52:57] == "00004"
    assert linhas[0][71:75] == "0001"


def test_lote_inteiro_com_codevedor_sai_com_o_cabecalho_da_remessa(monkeypatch):
    remessa = [x for x in _lote("121").split("\r\n") if x]
    linhas = _confirmar(monkeypatch, "121", entram=(1, 2, 3))
    assert linhas[0] == remessa[0][:52] + "SDTBFOCRT" + remessa[0][61:]
    assert linhas[-1] == remessa[-1]


def test_a_linha_que_abre_titulo_e_a_do_controle_um():
    def linha(controle: str) -> str:
        return _registro("tr", {1: "1", 22: controle})
    assert PRM._abre_titulo(linha("1")) and PRM._abre_titulo(linha(" "))
    assert not PRM._abre_titulo(linha("2")) and not PRM._abre_titulo(linha("3"))
    # A mesma posição que o leitor de campos chama de controle do devedor.
    assert linha("2")[296] == "2"

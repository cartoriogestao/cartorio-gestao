"""O selo da materialização de certidão de outra serventia — 26/10/2026.

    «assim como criamos o emissor de selo para certidão eletrônica de registro
     do cartório, preciso que o sistema emita selo para a materialização de
     certidão vinda de outros cartórios para entrega a clientes» — o oficial,
     com o item 14.5.1 e o pagamento no caixa da casa.

O QUE ESTES TESTES GUARDAM
    **O selo sai pelo caminho próprio do contrato** —
    `/selo/civil/certidao/materializacao` —, com os campos obrigatórios do
    `DadosSeloCertidaoMaterializacao` e o item 14.5.1.
    **A trava do selo pago vale aqui como em qualquer selo**: sem protocolo
    pago, o selo não sai e a materialização fica cancelada, com o motivo.
    **O que o selador recusaria se recusa antes**, sem gravar nada.
    **E o aviso do selo mostra o código de validação** (`valorQrCode`) com o
    nome dele, sem despejar a imagem do QR em base64 — na CRC e aqui.

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ato_selado as AS                                              # noqa: E402
import rc_materializacao as RCM                                      # noqa: E402
from test_rc_certidao_web import _con, _semear, _sessao, _token     # noqa: E402

CAMPOS = {"nome_parte": "BEATRIZ EXEMPLO", "requerente": "CARLA EXEMPLO",
          "cartorio_nome": "CARTORIO DE EXEMPLO DO 2 OFICIO",
          "cartorio_cidade": "CIDADE DE EXEMPLO", "cartorio_uf": "pi",
          "funcionario_expedidor": "MARIO EXEMPLO",
          "valor_emolumentos": "53,58", "especie": "NASCIMENTO"}


def _avisos(html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", a).strip() for a in re.findall(
        r'<div class="flash[^"]*"[^>]*>(.*?)<button', html, flags=re.DOTALL)]


def _bancada(cg_casa, protocolo_pago: bool):
    from selador_de_bancada import ligar_o_selador
    return ligar_o_selador(cg_casa, protocolo_pago=protocolo_pago)


@pytest.fixture()
def pago(cg_casa):
    with _bancada(cg_casa, True) as aparelho:
        yield {"s": _sessao(cg_casa), "aparelho": aparelho}


@pytest.fixture()
def sem_pagamento(cg_casa):
    with _bancada(cg_casa, False) as aparelho:
        yield {"s": _sessao(cg_casa), "aparelho": aparelho}


def _selar(s, **campos):
    html = s["c"].get("/rcpn/materializacoes").get_data(as_text=True)
    return s["c"].post("/rcpn/materializacoes",
                       data={"csrf_token": _token(html), **campos},
                       follow_redirects=True)


def _linhas(s):
    con = _con(s)
    try:
        return [dict(x) for x in con.execute(
            "SELECT * FROM rc_materializacoes ORDER BY id").fetchall()]
    finally:
        con.close()


def test_a_tela_abre_e_esta_no_menu(pago):
    s = pago["s"]
    html = s["c"].get("/rcpn/materializacoes").get_data(as_text=True)
    assert "Emitir selo da materialização" in html
    assert 'action="/rcpn/materializacoes"' in html
    assert "Materializar certidão de outra serventia" in html


def test_o_selo_sai_pelo_caminho_da_materializacao_com_o_14_5_1(pago):
    s, aparelho = pago["s"], pago["aparelho"]
    html = _selar(s, **CAMPOS).get_data(as_text=True)
    assert any("Selo da materialização:" in a for a in _avisos(html)), _avisos(html)
    selos = [p for p in aparelho.pedidos if p["caminho"].startswith("/selo/")]
    assert len(selos) == 1, [p["caminho"] for p in aparelho.pedidos]
    assert selos[0]["caminho"].endswith("/selo/civil/certidao/materializacao")
    corpo = json.loads(selos[0]["corpo"])
    corpo.pop("escrevente", None)       # a segunda tranca de `obter_selo`
    assert corpo["codigoAto"] == "14.5.1"
    assert corpo["nomeCartorioExpedidor"] == "CARTORIO DE EXEMPLO DO 2 OFICIO"
    assert corpo["cidadeCartorioExpedidor"] == "CIDADE DE EXEMPLO"
    assert corpo["estadoCartorioExpedidor"] == "PI"
    assert corpo["nomeFuncionarioExpedidor"] == "MARIO EXEMPLO"
    assert corpo["valorEmolumentosCertidao"] == 53.58
    assert corpo["parte"] == {"nome": "BEATRIZ EXEMPLO"}
    assert sorted(corpo["dadosSelo"]) == ["escrevente", "versaoTabelaDeCustas"]
    assert "papelMoeda" not in json.dumps(corpo)
    [linha] = _linhas(s)
    assert linha["selo"] and not linha["cancelada_em"]
    assert linha["valor_emolumentos_centavos"] == 5358
    assert linha["requerente"] == "CARLA EXEMPLO"


def test_sem_protocolo_pago_o_selo_nao_sai_e_fica_cancelada(sem_pagamento):
    s, aparelho = sem_pagamento["s"], sem_pagamento["aparelho"]
    html = _selar(s, **CAMPOS).get_data(as_text=True)
    assert any("NÃO saiu" in a for a in _avisos(html)), _avisos(html)
    assert not [p for p in aparelho.pedidos if p["caminho"].startswith("/selo/")]
    [linha] = _linhas(s)
    assert not linha["selo"]
    assert linha["cancelada_em"] and "Selo não emitido" in linha["cancelada_motivo"]


def test_o_que_o_selador_exige_se_recusa_antes_sem_gravar(pago):
    s, aparelho = pago["s"], pago["aparelho"]
    html = _selar(s, **(CAMPOS | {"cartorio_nome": "", "valor_emolumentos": "x"})
                  ).get_data(as_text=True)
    aviso = " ".join(_avisos(html))
    assert "o nome do cartório que expediu" in aviso
    assert "o valor dos emolumentos" in aviso
    assert _linhas(s) == []
    assert not [p for p in aparelho.pedidos if p["caminho"].startswith("/selo/")]


def test_selo_isento_exige_motivo_e_nao_grava(pago):
    s = pago["s"]
    html = _selar(s, **CAMPOS, selo_gratuito="1").get_data(as_text=True)
    assert any("motivo" in a for a in _avisos(html))
    assert _linhas(s) == []


def test_o_isento_vai_como_a_casa_mandava():
    env = RCM.envelope(RCM.conferir(CAMPOS), escrevente="CARLA EXEMPLO",
                       versao_tabela="0120260101", isento=True,
                       motivo_isencao="art. 30 da lei")
    assert env["dadosSelo"]["isentoGratuito"] == "ISENTO"
    assert env["dadosSelo"]["motivoIsentoGratuito"] == "ART. 30 DA LEI"
    with pytest.raises(RCM.MaterializacaoError, match="motivo"):
        RCM.envelope(RCM.conferir(CAMPOS), escrevente="CARLA EXEMPLO",
                     versao_tabela="0120260101", isento=True)


@pytest.mark.parametrize("texto,centavos", [
    ("53,58", 5358), ("53.58", 5358), ("R$ 1.234,56", 123456), ("0", 0),
    ("", None), ("abc", None), ("-1", None)])
def test_o_valor_digitado_vira_centavos(texto, centavos):
    assert RCM.centavos(texto) == centavos


def test_a_tabela_e_de_ato_do_rcpn_e_tem_caminho():
    assert RCM.TABELA in AS.TABELAS_DE_ATO
    assert AS.atribuicoes_do_ato(RCM.TABELA) == frozenset({"RCPN"})
    assert AS.caminho_do_ato(RCM.TABELA, "MATERIALIZACAO") == RCM.CAMINHO
    import selador
    assert RCM.CAMINHO in selador.ENDPOINTS


def test_o_aviso_mostra_o_codigo_de_validacao_e_nao_a_imagem(pago):
    s, aparelho = pago["s"], pago["aparelho"]
    aparelho.campos_a_mais = {"valorQrCode": "ENSAIO0VALIDACAO0123456",
                              "qrCode": "iVBORw0KGgoAAAANSUhEUgAAA" * 20}
    html = _selar(s, **CAMPOS).get_data(as_text=True)
    aviso = next(a for a in _avisos(html) if "Selo da materialização:" in a)
    assert "Código de validação: ENSAIO0VALIDACAO0123456" in aviso
    assert "iVBORw0KGgo" not in aviso and "qrCode" not in aviso
    [linha] = _linhas(s)
    con = _con(s)
    try:
        guardado = con.execute("SELECT qr_token FROM sd_selos WHERE numero=?",
                               (linha["selo"],)).fetchone()[0]
    finally:
        con.close()
    assert guardado == "ENSAIO0VALIDACAO0123456"


def test_o_aviso_da_crc_tambem_mostra_o_codigo_com_o_nome(cg_casa):
    """A certidão eletrônica da CRC (23/10/2026) mostrava `valorQrCode` e o
    `qrCode` crus; agora sai «Código de validação», sem a imagem."""
    with _bancada(cg_casa, False) as aparelho:
        s = _sessao(cg_casa)
        aparelho.campos_a_mais = {"valorQrCode": "ENSAIO0CRC00VALIDACAO99",
                                  "qrCode": "iVBORw0KGgoAAAANSUhEUgAAA" * 20}
        aid = _semear(s)
        html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
        r = s["c"].post(f"/rcpn/{aid}/certidao-eletronica/selo",
                        data={"csrf_token": _token(html)}, follow_redirects=True)
        aviso = next(a for a in _avisos(r.get_data(as_text=True))
                     if "Selo da certidão eletrônica:" in a)
    assert "Código de validação: ENSAIO0CRC00VALIDACAO99" in aviso
    assert "iVBORw0KGgo" not in aviso

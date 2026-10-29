"""O selo da conferência de documento eletrônico do RI (16.42), a partir do protocolo — 28/10/2026.

    «crie uma PR para podermos emitir selo em um protocolo para conferencia de
     documento digital no RI. [...] a emissao do selo pode ser feita a partir
     do protocolo, gerando uma etiqueta para colar na folha fisica (tipo
     etiqueta de reconhecimento de firma) ou comprovante anexado ao
     arquivamento digital (pdf)» — o oficial

O QUE ESTES TESTES GUARDAM
    **O quadro mora na ficha do protocolo do RI**, e só oferece o botão quando
    há item 16.42 com unidade sobrando.
    **O selo sai pelo caminho do arquivamento do RI** (`/selo/imovel/
    atos-em-geral`), com o item 16.42 e a `quantidade` = documentos — um
    pedido, e não N selos —, e gasta as unidades do item daquele protocolo.
    **A trava do selo pago vale aqui**: item não pago, o selo não sai, a
    conferência fica cancelada com o motivo e as unidades voltam.
    **O que falta se recusa antes**, sem gravar e sem gastar unidade.
    **A etiqueta sai com uma tira por documento**, na bobina de 100 × 30 mm,
    e conta a impressão; **o comprovante é um PDF**, e anexá-lo o põe nos
    documentos do protocolo uma vez só.

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
import ri_conferencia as RC                                          # noqa: E402
from protocolo_de_teste import _protocolo_pago                      # noqa: E402
from test_rc_certidao_web import _con, _sessao, _token              # noqa: E402

DOIS = ("CND de débitos relativos a tributos federais nº EXEMPLO-1\n"
        "Recibo de entrega da DITR 2026, NIRF 0.000.000-0")


def _avisos(html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", a).strip() for a in re.findall(
        r'<div class="flash[^"]*"[^>]*>(.*?)<button', html, flags=re.DOTALL)]


def _bancada(cg_casa):
    # SEM o protocolo pago da bancada: quem paga é o item 16.42 do protocolo
    # que o próprio teste abre — é ele que a conferência gasta.
    from selador_de_bancada import ligar_o_selador
    return ligar_o_selador(cg_casa, protocolo_pago=False)


@pytest.fixture()
def casa(cg_casa):
    with _bancada(cg_casa) as aparelho:
        yield {"s": _sessao(cg_casa), "aparelho": aparelho}


def _protocolo(s, *, pago=True, atribuicao="RI", quantidade=3) -> dict:
    con = _con(s)
    with con:
        p = _protocolo_pago(con, codigos=[RC.CODIGO_ATO], quantidade=quantidade,
                            atribuicao=atribuicao)
        if not pago:
            con.execute("UPDATE cx_protocolo_atos SET quitado = 0 WHERE id = ?",
                        (p["itens"][0],))
    con.close()
    return p


def _emitir(s, protocolo_id, documentos=DOIS):
    html = s["c"].get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)
    return s["c"].post(f"/caixa/protocolos/{protocolo_id}/conferencia-digital",
                       data={"csrf_token": _token(html), "documentos": documentos},
                       follow_redirects=True)


def _linhas(s):
    con = _con(s)
    try:
        return [dict(x) for x in con.execute(
            "SELECT * FROM ri_conferencias ORDER BY id").fetchall()]
    finally:
        con.close()


def _usadas(s, item_id) -> int:
    con = _con(s)
    try:
        return int(con.execute("SELECT coalesce(quantidade_usada, 0) FROM "
                               "cx_protocolo_atos WHERE id = ?", (item_id,)).fetchone()[0])
    finally:
        con.close()


def _selos(aparelho):
    return [p for p in aparelho.pedidos if p["caminho"].startswith("/selo/")]


# ------------------------------------------------------------- o quadro


def test_o_quadro_aparece_na_ficha_do_protocolo_do_ri(casa):
    s = casa["s"]
    p = _protocolo(s)
    html = s["c"].get(f"/caixa/protocolos/{p['protocolo_id']}").get_data(as_text=True)
    assert 'id="conferencia-digital"' in html
    assert "Emitir o selo da conferência" in html
    assert f'action="/caixa/protocolos/{p["protocolo_id"]}/conferencia-digital"' in html


def test_sem_item_16_42_o_quadro_diz_o_que_falta_e_nao_oferece_o_botao(casa):
    s = casa["s"]
    con = _con(s)
    with con:
        p = _protocolo_pago(con, codigos=["16.39"], quantidade=1, atribuicao="RI")
    con.close()
    html = s["c"].get(f"/caixa/protocolos/{p['protocolo_id']}").get_data(as_text=True)
    assert 'id="conferencia-sem-item"' in html
    assert "Emitir o selo da conferência" not in html


# ------------------------------------------------------------- o selo


def test_o_selo_sai_pelo_caminho_do_imovel_com_o_16_42_e_a_quantidade(casa):
    s, aparelho = casa["s"], casa["aparelho"]
    p = _protocolo(s)
    html = _emitir(s, p["protocolo_id"]).get_data(as_text=True)
    assert any("Selo da conferência:" in a for a in _avisos(html)), _avisos(html)
    [pedido] = _selos(aparelho)
    assert pedido["caminho"].endswith(RC.CAMINHO) and RC.CAMINHO == "/selo/imovel/atos-em-geral"
    corpo = json.loads(pedido["corpo"])
    assert corpo["ato"]["codigo"] == "16.42"
    assert corpo["quantidade"] == 2              # um pedido, com dois documentos
    assert corpo["partes"]["parteAto"][0]["nome"] == "CLIENTE DE EXEMPLO"
    [linha] = _linhas(s)
    assert linha["selo"] and not linha["cancelada_em"]
    assert linha["quantidade"] == 2 and linha["documentos"].count("\n") == 1
    assert _usadas(s, p["itens"][0]) == 2        # as unidades do 16.42 deste protocolo


def test_sem_pagamento_o_selo_nao_sai_fica_cancelada_e_as_unidades_voltam(casa):
    s, aparelho = casa["s"], casa["aparelho"]
    p = _protocolo(s, pago=False)
    html = _emitir(s, p["protocolo_id"]).get_data(as_text=True)
    assert any("NÃO saiu" in a for a in _avisos(html)), _avisos(html)
    assert not _selos(aparelho)
    [linha] = _linhas(s)
    assert not linha["selo"]
    assert linha["cancelada_em"] and "Selo não emitido" in linha["cancelada_motivo"]
    assert _usadas(s, p["itens"][0]) == 0


@pytest.mark.parametrize("documentos,atribuicao,frase", [
    ("", "RI", "um por linha"),
    ("a\nb\nc\nd", "RI", "unidade(s) sobrando"),
    (DOIS, "NOTAS", "não é do Registro de Imóveis"),
])
def test_o_que_falta_se_recusa_antes_sem_gravar_nem_gastar(casa, documentos,
                                                            atribuicao, frase):
    s, aparelho = casa["s"], casa["aparelho"]
    p = _protocolo(s, atribuicao=atribuicao)
    html = _emitir(s, p["protocolo_id"], documentos=documentos).get_data(as_text=True)
    assert any(frase in a for a in _avisos(html)), _avisos(html)
    assert _linhas(s) == [] and not _selos(aparelho)
    assert _usadas(s, p["itens"][0]) == 0


# ------------------------------------------------------------- o papel


def _selada(s) -> tuple[dict, dict]:
    p = _protocolo(s)
    _emitir(s, p["protocolo_id"])
    [linha] = _linhas(s)
    return p, linha


def test_a_etiqueta_sai_com_uma_tira_por_documento_e_conta_a_impressao(casa):
    s = casa["s"]
    p, c = _selada(s)
    ficha = s["c"].get(f"/caixa/protocolos/{p['protocolo_id']}").get_data(as_text=True)
    r = s["c"].post(f"/registro-imoveis/conferencias/{c['id']}/etiqueta",
                    data={"csrf_token": _token(ficha)})
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "size: 100.0mm 30.0mm" in html or "size: 100mm 30mm" in html
    assert html.count('class="etiqueta"') == 2 and "Tira 2 de 2" in html
    assert c["selo"] in html and "16.42" in html
    assert 'class="sidebar"' not in html        # a página não herda o layout
    [depois] = _linhas(s)
    assert depois["etiqueta_impressoes"] == 1


def test_o_comprovante_e_um_pdf_e_entra_nos_documentos_do_protocolo_uma_vez(casa):
    s = casa["s"]
    p, c = _selada(s)
    r = s["c"].get(f"/registro-imoveis/conferencias/{c['id']}/comprovante.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.get_data().startswith(b"%PDF")
    ficha = s["c"].get(f"/caixa/protocolos/{p['protocolo_id']}").get_data(as_text=True)
    for _ in range(2):
        s["c"].post(f"/registro-imoveis/conferencias/{c['id']}/anexar",
                    data={"csrf_token": _token(ficha)})
    con = _con(s)
    anexos = con.execute("""SELECT * FROM attachments WHERE entity_type = 'PROTOCOLO'
                              AND entity_id = ? AND documento_tipo = 'CONFERENCIA'""",
                         (p["protocolo_id"],)).fetchall()
    con.close()
    assert len(anexos) == 1
    [depois] = _linhas(s)
    assert depois["comprovante_anexo_id"] == anexos[0]["id"]
    ficha = s["c"].get(f"/caixa/protocolos/{p['protocolo_id']}").get_data(as_text=True)
    assert "anexado ao protocolo" in ficha


def test_conferencia_sem_selo_nao_tem_etiqueta_nem_comprovante(casa):
    s = casa["s"]
    p = _protocolo(s, pago=False)
    _emitir(s, p["protocolo_id"])
    [c] = _linhas(s)
    ficha = s["c"].get(f"/caixa/protocolos/{p['protocolo_id']}").get_data(as_text=True)
    r = s["c"].post(f"/registro-imoveis/conferencias/{c['id']}/etiqueta",
                    data={"csrf_token": _token(ficha)}, follow_redirects=True)
    assert any("cancelada" in a for a in _avisos(r.get_data(as_text=True)))
    r = s["c"].get(f"/registro-imoveis/conferencias/{c['id']}/comprovante.pdf")
    assert r.status_code == 302


# ------------------------------------------------------------- a trava


def test_a_tabela_esta_registrada_onde_a_trava_pergunta():
    assert RC.TABELA in AS.TABELAS_DE_ATO
    assert AS.ATRIBUICOES_DO_ATO[RC.TABELA] == frozenset({"RI"})
    assert AS.caminho_do_ato(RC.TABELA, "CONFERENCIA") == RC.CAMINHO


def test_envelope_e_o_atos_em_geral_com_a_quantidade():
    conferido = {"quantidade": 3, "requerente": "CLIENTE DE EXEMPLO",
                 "requerente_documento": "00000000191"}
    env = RC.envelope(conferido, escrevente="MARIO EXEMPLO", versao_tabela="0220260101")
    assert env == {"escrevente": "MARIO EXEMPLO",
                   "partes": {"nomePartes": [], "parteAto": [
                       {"nome": "CLIENTE DE EXEMPLO", "documento": "00000000191"}]},
                   "quantidade": 3,
                   "ato": {"codigo": "16.42", "codigoTabelaCusta": "0220260101"}}
    assert AS.codigo_do_envelope(env) == "16.42"
    assert AS.quantidade_do_envelope(env) == 3
    with pytest.raises(RC.ConferenciaError, match="versão da tabela"):
        RC.envelope(conferido, escrevente="MARIO EXEMPLO", versao_tabela="")

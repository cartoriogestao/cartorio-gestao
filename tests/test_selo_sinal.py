"""O sinal do selo na tela do ato: verde, vermelho ou amarelo, ANTES de lavrar (P008).

Pedido do oficial em 24/11/2026: «vamos fazer esse sinal verde e vermelho».
Em quatro semanas (26/10 a 23/11/2026), 67 selos não saíram porque o protocolo
não tinha o item do código com unidade sobrando, ou o item não estava pago.

O QUE ESTES TESTES PROTEGEM
    - o verde só com o item do MESMO código, pago (ou pago pelo depósito
      prévio), na quantidade que o ato usa: a firma comum (13.17.2) não fica
      verde com o 13.17.4 pago — era a coluna «Cobre? sim» da lista;
    - sem o código exato (a família «14.*»), nunca verde: amarelo, com o que
      o protocolo tem, para conferir;
    - o vermelho diz o que falta e onde: o item, o pagamento, a unidade já
      gasta, o protocolo da prenotação — e quando o protocolo é o que a
      pessoa já atendia, diz isso;
    - o protocolo marcado na tela vale mais que o atendimento antigo;
    - perguntar o sinal NÃO atende o protocolo nem grava nada.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import ato_selado as AS                         # noqa: E402
import caixa_protocolo as CXP                   # noqa: E402
import selo_sinal as SINAL                      # noqa: E402
from bd_nativo import banco as _banco           # noqa: E402
from test_selo_e_caixa import (                 # noqa: E402,F401
    AGORA, ESCREVENTE, _casa, _deposito, _fechar_as_conexoes, _item, _ligar,
    _protocolo)


def _servicos(con):
    bd = _banco(con)
    for codigo, tj in ((412, "13.17.1"), (413, "13.17.2"), (414, "13.17.3"),
                       (416, "13.17.4")):
        bd.escrever("""INSERT INTO cx_servicos (codigo, codigo_tj, descricao)
                       VALUES (%s,%s,%s) ON CONFLICT (codigo) DO NOTHING""",
                    (codigo, tj, f"Serviço {tj}"))
    con.commit()


def _atender(con, protocolo):
    CXP.atender(con, usuario=ESCREVENTE, protocolo=protocolo["protocolo_id"],
                agora=AGORA)
    con.commit()


def _form(**campos):
    m = MultiDict()
    for chave, valor in campos.items():
        for v in (valor if isinstance(valor, list) else [valor]):
            m.add(chave, v)
    return m


def _sinal(con, tabela, form, pedidos=None):
    return SINAL.sinal_do_formulario(con, tabela=tabela, usuario=ESCREVENTE,
                                     form=form, pedidos_da_macro=pedidos)


def _texto(sinal):
    return " ".join(sinal["linhas"])


# ------------------------------------------- a firma: o código pela espécie


def test_firma_comum_com_13_17_4_pago_e_vermelho_e_diz_o_item():
    """10 dos 14 reconhecimentos suspensos: o protocolo pagava o 13.17.4
    (financeiro), a lista dizia «Cobre? sim», e a firma pedia o 13.17.2."""
    con = _casa()
    _servicos(con)
    p = _protocolo(con, atribuicao="FIRMAS")
    _item(con, p["protocolo_id"], codigo="13.17.4", quitado=1)
    _atender(con, p)
    s = _sinal(con, "nt_reconhecimentos",
               _form(especie="SEMELHANCA", cartao_id=["7"]))
    assert s["cor"] == SINAL.VERMELHO
    assert s["pedidos"] == [("13.17.2", 1)]
    assert "não tem o item 13.17.2" in _texto(s)
    assert s["botoes"] and s["botoes"][0]["protocolo_id"] == p["protocolo_id"]
    # o mesmo protocolo serve para o documento de conteúdo financeiro
    s = _sinal(con, "nt_reconhecimentos",
               _form(especie="SEMELHANCA", financeiro="1", cartao_id=["7"]))
    assert s["cor"] == SINAL.VERDE
    assert "13.17.4" in _texto(s) and "o selo sai" in _texto(s)


def test_um_selo_por_cartao_conta_as_unidades():
    con = _casa()
    _servicos(con)
    p = _protocolo(con, atribuicao="FIRMAS")
    _item(con, p["protocolo_id"], codigo="13.17.2", quitado=1, quantidade=2)
    _atender(con, p)
    dois = _sinal(con, "nt_reconhecimentos", _form(cartao_id=["1", "2"]))
    assert dois["cor"] == SINAL.VERDE
    tres = _sinal(con, "nt_reconhecimentos", _form(cartao_id=["1", "2", "3"]))
    assert tres["cor"] == SINAL.VERMELHO
    assert "faltam 1" in _texto(tres)


def test_a_unidade_ja_gasta_e_dita():
    """O lote de 43 firmas: a 44ª pedia o selo com o item todo gasto."""
    con = _casa()
    _servicos(con)
    p = _protocolo(con, atribuicao="FIRMAS")
    gasto = _item(con, p["protocolo_id"], codigo="13.17.2", quitado=1)
    _ligar(con, gasto, ato_id=5, tabela="nt_reconhecimentos")
    _atender(con, p)
    s = _sinal(con, "nt_reconhecimentos", _form(cartao_id=["1"]))
    assert s["cor"] == SINAL.VERMELHO
    assert "já foi usada por outro ato" in _texto(s)


# --------------------------------------------- pago, depósito, não pago


def test_item_nao_pago_pede_o_pagamento_e_o_deposito_cobre():
    con = _casa()
    _servicos(con)
    p = _protocolo(con, atribuicao="FIRMAS")
    _item(con, p["protocolo_id"], codigo="13.17.1", quitado=0, valor="20,00")
    _atender(con, p)
    s = _sinal(con, "nt_cartoes", _form(nome="CLIENTE"))
    assert s["cor"] == SINAL.VERMELHO
    assert "Falta registrar o pagamento do item 13.17.1" in _texto(s)
    assert s["botoes"][0]["texto"].startswith("Registrar o pagamento")
    _deposito(con, p["protocolo_id"], valor="50,00")
    s = _sinal(con, "nt_cartoes", _form(nome="CLIENTE"))
    assert s["cor"] == SINAL.VERDE
    assert "depósito prévio" in _texto(s)


def test_item_gratuito_nao_paga_selo_pago():
    con = _casa()
    _servicos(con)
    p = _protocolo(con, atribuicao="FIRMAS")
    item = _item(con, p["protocolo_id"], codigo="13.17.1", quitado=1)
    _banco(con).escrever("UPDATE cx_protocolo_atos SET gratuito = 1 WHERE id = %s",
                         (item,))
    con.commit()
    _atender(con, p)
    s = _sinal(con, "nt_cartoes", _form())
    assert s["cor"] == SINAL.VERMELHO and "é gratuito" in _texto(s)


def test_ato_isento_e_trava_desligada_ficam_verdes():
    con = _casa()
    s = _sinal(con, "ri_atos", _form(codigo_tj_selo=[""], codigo_tj="16.3",
                                     isento="1"))
    assert s["cor"] == SINAL.VERDE and "isento" in _texto(s)
    _banco(con).escrever("INSERT INTO settings (key, value) VALUES (%s, %s)",
                         (AS.CHAVE_DA_TRAVA, AS.TRAVA_DESLIGADA))
    con.commit()
    s = _sinal(con, "ri_atos", _form(codigo_tj_selo=[""], codigo_tj="16.3"))
    assert s["cor"] == SINAL.VERDE and "desligada" in _texto(s)


# -------------------------------------------- qual protocolo a tela usa


def test_o_atendimento_antigo_e_dito_e_o_marcado_vale_mais():
    """50 das 67 suspensões: ninguém escolheu, e valeu o protocolo que a
    pessoa atendia antes — de outro cliente, às vezes de outra atribuição."""
    con = _casa()
    _servicos(con)
    antigo = _protocolo(con, atribuicao="FIRMAS")
    _item(con, antigo["protocolo_id"], codigo="13.17.2", quitado=1)
    _atender(con, antigo)
    deste_cliente = _protocolo(con, atribuicao="FIRMAS")
    _item(con, deste_cliente["protocolo_id"], codigo="13.17.1", quitado=1)
    s = _sinal(con, "nt_cartoes", _form())
    assert s["cor"] == SINAL.VERMELHO
    assert "que você já atendia" in _texto(s)
    assert s["protocolo"]["do_atendimento"] is True
    s = _sinal(con, "nt_cartoes",
               _form(protocolo_selo=str(deste_cliente["protocolo_id"])))
    assert s["cor"] == SINAL.VERDE
    assert s["protocolo"]["id"] == deste_cliente["protocolo_id"]


def test_protocolo_de_outra_atribuicao_nao_serve():
    con = _casa()
    _servicos(con)
    protesto = _protocolo(con, atribuicao="PROTESTO")
    _item(con, protesto["protocolo_id"], codigo="17.2", quitado=1)
    _atender(con, protesto)
    s = _sinal(con, "nt_cartoes", _form())
    assert s["cor"] == SINAL.VERMELHO
    assert "não serve para este ato" in _texto(s)


def test_sem_protocolo_nenhum_e_vermelho():
    con = _casa()
    _servicos(con)
    s = _sinal(con, "nt_cartoes", _form())
    assert s["cor"] == SINAL.VERMELHO and "Nenhum protocolo escolhido" in _texto(s)
    s = _sinal(con, "ri_atos", _form(codigo_tj_selo=[""], codigo_tj="16.5"))
    assert s["cor"] == SINAL.VERMELHO
    assert "falta ligar o protocolo à prenotação" in _texto(s)


# ------------------------------------------------- a família nunca é verde


def test_familia_do_grupo_da_amarelo_ou_vermelho_nunca_verde():
    con = _casa()
    p = _protocolo(con, atribuicao="RCPN")
    _item(con, p["protocolo_id"], codigo="14.5.1", quitado=1)
    _atender(con, p)
    s = _sinal(con, "rc_atos", _form(), pedidos=[("14.*", 1)])
    assert s["cor"] == SINAL.AMARELO and s["exato"] is False
    assert "14.5.1" in _texto(s) and "Confira" in _texto(s)

    so_protesto = _protocolo(con, atribuicao="RCPN")
    _item(con, so_protesto["protocolo_id"], codigo="17.3", quitado=1)
    s = _sinal(con, "rc_certidoes",
               _form(protocolo_selo=str(so_protesto["protocolo_id"])),
               pedidos=[("14.*", 1)])
    assert s["cor"] == SINAL.VERMELHO
    assert "grupo 14 (Registro Civil)" in _texto(s)

    nao_pago = _protocolo(con, atribuicao="RCPN")
    _item(con, nao_pago["protocolo_id"], codigo="14.1.1", quitado=0)
    s = _sinal(con, "hc_habilitacoes",
               _form(protocolo_selo=str(nao_pago["protocolo_id"])),
               pedidos=[("14.*", 1)])
    assert s["cor"] == SINAL.VERMELHO
    assert "Falta registrar o pagamento do item 14.1.1" in _texto(s)


# ------------------------------------------------------------ o RI


def test_ato_do_ri_com_item_marcado_e_pago_e_verde():
    con = _casa()
    caixa = _protocolo(con, atribuicao="RI")
    item = _item(con, caixa["protocolo_id"], codigo="16.3", quitado=1)
    form = _form(codigo_tj_selo=[""], qtd_selo=["1"],
                 protocolo_id=str(caixa["protocolo_id"]),
                 protocolo_item_id=[str(item)])
    s = _sinal(con, "ri_atos", form)
    assert s["cor"] == SINAL.VERDE and "16.3" in _texto(s)


def test_ato_do_ri_pelo_catalogo_confere_o_protocolo_em_atendimento():
    """O AV-06 de 28/10: o código escolhido não estava no protocolo atendido;
    o item foi acrescentado e pago depois do terceiro clique."""
    con = _casa()
    p = _protocolo(con, atribuicao="RI")
    _item(con, p["protocolo_id"], codigo="16.39", quitado=1, quantidade=15)
    _atender(con, p)
    form = _form(codigo_tj_selo=["16.5"], qtd_selo=["1"])
    s = _sinal(con, "ri_atos", form)
    assert s["cor"] == SINAL.VERMELHO
    assert "não tem o item 16.5" in _texto(s)
    _item(con, p["protocolo_id"], codigo="16.5", quitado=1)
    assert _sinal(con, "ri_atos", form)["cor"] == SINAL.VERDE


def test_formulario_do_ri_sem_os_campos_de_lavrar_usa_os_pedidos_da_lista():
    """O arquivamento (16.39) também é `ri_atos`, mas não tem «Vários selos»."""
    con = _casa()
    p = _protocolo(con, atribuicao="RI")
    _item(con, p["protocolo_id"], codigo="16.39", quitado=1, quantidade=3)
    _atender(con, p)
    s = _sinal(con, "ri_atos", _form(folhas_arquivamento="2"),
               pedidos=[("16.39", 1)])
    assert s["cor"] == SINAL.VERDE


def test_certidao_de_onus_pede_dois_itens_base():
    con = _casa()
    p = _protocolo(con, atribuicao="RI")
    base = AS.CODIGO_DA_CERTIDAO_DO_RI["ONUS"]
    _item(con, p["protocolo_id"], codigo=base, quitado=1, quantidade=1)
    _atender(con, p)
    s = _sinal(con, "ri_certidoes", _form(tipo="ONUS", folhas="1"))
    assert s["pedidos"] == [(base, 2)]
    assert s["cor"] == SINAL.VERMELHO and "faltam 1" in _texto(s)
    # sem folhas informadas, avisa da folha acrescida
    s = _sinal(con, "ri_certidoes", _form(tipo="INTEIRO_TEOR"))
    assert any("folha" in a for a in s["avisos"])


def test_certidao_negativa_do_indicador_usa_o_codigo_da_lista():
    con = _casa()
    p = _protocolo(con, atribuicao="RI")
    _item(con, p["protocolo_id"], codigo="16.24.1", quitado=1)
    _atender(con, p)
    s = _sinal(con, "ri_certidoes", _form(nome="X"), pedidos=[("16.24.1", 1)])
    assert s["cor"] == SINAL.VERDE


# ------------------------------------------------------ só lê, pela tela


def _token(html):
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def test_a_rota_do_sinal_nao_atende_o_protocolo_nem_grava(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        p = CXP.abrir(con, data_abertura="2026-11-24", agora=AGORA,
                      atribuicao="FIRMAS", interessado="CLIENTE DE EXEMPLO")
    tela = c.get("/notas/cartoes").get_data(as_text=True)
    assert 'data-selo-sinal' in tela and 'data-tabela="nt_cartoes"' in tela
    assert "selo_sinal.js" in tela
    r = c.post("/selo/sinal", data={
        "csrf_token": _token(tela), "_sinal_tabela": "nt_cartoes",
        "protocolo_selo": str(p["protocolo_id"])})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # o cartão pede o 13.17.1, e o protocolo não tem item nenhum
    assert re.search(r'data-cor="(vermelho|amarelo)"', html), html
    with db.connect() as con:
        bd = _banco(con)
        assert bd.valor("SELECT count(*) FROM cx_atendimento") == 0
        assert bd.valor("""SELECT count(*) FROM audit_logs
                            WHERE action = 'SELO_PROTOCOLO_EM_ATENDIMENTO'""") == 0


def test_a_rota_recusa_tabela_que_nao_e_de_ato(cg_casa_logada):
    c = cg_casa_logada["c"]
    tela = c.get("/notas/cartoes").get_data(as_text=True)
    r = c.post("/selo/sinal", data={"csrf_token": _token(tela),
                                    "_sinal_tabela": "users"})
    assert r.status_code == 404


def test_o_script_do_sinal_nao_guarda_nada_no_navegador():
    js = (RAIZ / "static" / "selo_sinal.js").read_text(encoding="utf-8")
    assert "localStorage" not in js and "sessionStorage" not in js
    assert not re.search(r"""fetch\(\s*["']/""", js), \
        "o endereço vem da macro (url_for), não escrito no script"

"""O protocolo que paga o selo é ESCOLHIDO pelo escrevente, e o selo gasta o que pede.

    22/10/2026, primeiro dia da 3.7.0: nenhum selo saiu. A firma com o 13.17.4
    pago e as certidões do RI com o 16.24.4 pago ficaram «aguardando
    cobertura», porque o selo só procura o item no protocolo «em atendimento»
    e esse passo morava escondido em «Selo e caixa».

Decisão do oficial, no mesmo dia: «escrevente confirma». A tela mostra os
protocolos pagos (o único vem marcado), e o sistema NUNCA escolhe sozinho —
com um protocolo pago só na casa, o selo de quem não pagou gastaria o
pagamento de quem pagou.

O QUE ESTES TESTES PROTEGEM
    - a lista de candidatos: só protocolo aberto, da atribuição do ato, do
      mesmo código e com saldo; o que cobre vem antes, e o que não cobre diz
      quanto falta;
    - escolher na tela grava o atendimento, e só então o selo sai;
    - sem escolha, o pagamento de outro cliente não cobre o selo;
    - o passo 3 gasta as unidades que o envelope pede (a folha acrescida da
      certidão do RI), e nunca menos de uma;
    - o item ligado ao ato cobre pelo código quando dá (os dois selos da
      certidão do RI), e qualquer item ligado quando nenhum tem o código.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import ato_selado as AS                         # noqa: E402
import caixa_protocolo as CXP                   # noqa: E402
from bd_nativo import banco as _banco           # noqa: E402
from test_selo_e_caixa import (                 # noqa: E402,F401
    AGORA, ESCREVENTE, PAGO, _casa, _fechar_as_conexoes, _item, _ligar,
    _protocolo, _selar, aparelho)

HOJE = AGORA[:10]


def _pago_com_quantidade(q):
    return {"ato": {"codigo": "16.1", "codigoTabelaCusta": "0320260101"},
            "quantidade": q,
            "selo": {"escrevente": ESCREVENTE, "protocolo": "1"}}


# ------------------------------------------------------------ os candidatos


def test_candidato_e_protocolo_aberto_do_codigo_com_saldo_pago():
    con = _casa()
    bom = _protocolo(con)
    _item(con, bom["protocolo_id"], codigo="16.1", quitado=1)
    outro_codigo = _protocolo(con)
    _item(con, outro_codigo["protocolo_id"], codigo="17.2", quitado=1)
    sem_saldo = _protocolo(con)
    gasto = _item(con, sem_saldo["protocolo_id"], codigo="16.1", quitado=1)
    _ligar(con, gasto, ato_id=3)
    encerrado = _protocolo(con)
    _item(con, encerrado["protocolo_id"], codigo="16.1", quitado=1)
    _banco(con).escrever("UPDATE cx_protocolos SET situacao='CANCELADO' WHERE id=%s",
                         (encerrado["protocolo_id"],))
    de_outra = _protocolo(con, atribuicao="RCPN")
    _item(con, de_outra["protocolo_id"], codigo="16.1", quitado=1)
    con.commit()
    lista = AS.candidatos_do_ato(con, tabela="pt_atos", pedidos=[("16.1", 1)],
                                 hoje=HOJE)
    assert [c["protocolo_id"] for c in lista] == [bom["protocolo_id"]]
    assert lista[0]["cobre_tudo"] is True and lista[0]["faltam"] == []


def test_o_que_nao_cobre_diz_quanto_falta_e_vem_depois():
    con = _casa()
    curto = _protocolo(con)
    _item(con, curto["protocolo_id"], codigo="16.1", quitado=1, quantidade=1)
    nao_pago = _protocolo(con)
    _item(con, nao_pago["protocolo_id"], codigo="16.1", quitado=0, quantidade=3)
    cheio = _protocolo(con)
    _item(con, cheio["protocolo_id"], codigo="16.1", quitado=1, quantidade=3)
    lista = AS.candidatos_do_ato(con, tabela="pt_atos", pedidos=[("16.1", 3)],
                                 hoje=HOJE)
    assert lista[0]["protocolo_id"] == cheio["protocolo_id"]
    faltas = {c["protocolo_id"]: c["faltam"] for c in lista}
    assert faltas[curto["protocolo_id"]][0]["faltam"] == 2
    assert faltas[nao_pago["protocolo_id"]][0]["faltam"] == 3
    assert faltas[nao_pago["protocolo_id"]][0]["saldo"] == 3


def test_o_protocolo_em_atendimento_vem_primeiro():
    con = _casa()
    a = _protocolo(con)
    _item(con, a["protocolo_id"], quitado=1)
    b = _protocolo(con)
    _item(con, b["protocolo_id"], quitado=1)
    lista = AS.candidatos_do_ato(con, tabela="pt_atos", pedidos=[("16.1", 1)],
                                 pre_marcar_protocolo_id=a["protocolo_id"],
                                 hoje=HOJE)
    assert lista[0]["protocolo_id"] == a["protocolo_id"] and lista[0]["pre_marcado"]


def test_pedidos_somam_por_codigo():
    assert CXP.pedidos_do_selo(["16.24.4", ("16.24.4.1", 3), ("16.24.4.1", "2"),
                                ("", 5)]) == [("16.24.4", 1), ("16.24.4.1", 5)]


def test_a_firma_aceita_protocolo_de_firmas_e_de_notas():
    assert AS.atribuicoes_do_ato("nt_reconhecimentos") == {"FIRMAS", "NOTAS"}
    assert AS.atribuicoes_do_ato("ri_certidoes") == {"RI"}
    assert AS.atribuicoes_do_ato("tabela_que_nao_existe") is None


# --------------------------------------------- escolher, e nunca sozinho


def test_sem_escolha_o_pagamento_de_outro_cliente_nao_cobre(aparelho):
    """O caso que decidiu o desenho: um protocolo pago só na casa NÃO paga
    sozinho o selo de outro ato — quem confirma é o escrevente."""
    con = _casa()
    p = _protocolo(con)
    _item(con, p["protocolo_id"], quitado=1)
    r = _selar(con)
    assert r["selado"] is False and aparelho == []


def test_escolher_na_tela_grava_o_atendimento_e_o_selo_sai(aparelho):
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    feito = AS.escolher_protocolo_do_selo(con, usuario=ESCREVENTE,
                                          protocolo=str(p["protocolo_id"]),
                                          agora=AGORA)
    con.commit()
    assert feito["numero"] == p["numero"]
    assert CXP.em_atendimento(con, ESCREVENTE)["id"] == p["protocolo_id"]
    assert _selar(con)["selado"] is True and len(aparelho) == 1
    assert _banco(con).valor("SELECT quantidade_usada FROM cx_protocolo_atos "
                             "WHERE id=%s", (item,)) == 1


def test_escolha_vazia_nao_mexe_no_atendimento():
    con = _casa()
    assert AS.escolher_protocolo_do_selo(con, usuario=ESCREVENTE, protocolo="  ",
                                         agora=AGORA) is None
    assert CXP.em_atendimento(con, ESCREVENTE) is None


def test_escolher_protocolo_encerrado_e_recusado():
    con = _casa()
    p = _protocolo(con)
    _banco(con).escrever("UPDATE cx_protocolos SET situacao='ENTREGUE' WHERE id=%s",
                         (p["protocolo_id"],))
    with pytest.raises(CXP.ProtocoloError, match="já foi encerrado"):
        AS.escolher_protocolo_do_selo(con, usuario=ESCREVENTE,
                                      protocolo=p["numero"], agora=AGORA)


# ------------------------------------------------ a quantidade do envelope


def test_o_selo_gasta_as_unidades_que_o_envelope_pede(aparelho):
    """A folha acrescida da certidão do RI pede folhas − 1 num selo só: as
    outras unidades não podem sobrar «livres» para cobrir outro ato."""
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1, quantidade=5)
    CXP.atender(con, usuario=ESCREVENTE, protocolo=p["numero"], agora=AGORA)
    con.commit()
    r = _selar(con, dados=_pago_com_quantidade(3))
    assert r["selado"] is True
    assert _banco(con).valor("SELECT quantidade_usada FROM cx_protocolo_atos "
                             "WHERE id=%s", (item,)) == 3
    assert _banco(con).valor("SELECT unidades_gastas FROM cx_selo_coberturas "
                             "LIMIT 1") == 3


def test_saldo_menor_que_o_pedido_cobre_com_o_que_ha_e_avisa(aparelho):
    """Como já acontecia (uma unidade por selo): não trava o balcão — e a
    cobertura diz quanto faltou, para a tela pedir o acréscimo."""
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1, quantidade=1)
    CXP.atender(con, usuario=ESCREVENTE, protocolo=p["numero"], agora=AGORA)
    con.commit()
    bd = _banco(con)
    coberto = AS.cobrir_o_selo(con, tabela="pt_atos", ato_id=1,
                               referencia="pt_atos:1", dados=_pago_com_quantidade(3),
                               usuario=ESCREVENTE, agora=AGORA)
    assert coberto["coberto"] is True
    assert coberto["parcial"] == {"codigo": "16.1", "pedidas": 3, "gastas": 1,
                                  "faltam": 2}
    assert bd.valor("SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=%s",
                    (item,)) == 1


def test_envelope_sem_quantidade_gasta_uma():
    assert AS.quantidade_do_envelope(PAGO) == 1
    assert AS.quantidade_do_envelope({"dadosSelo": {"quantidade": "4"}}) == 4


# ----------------------------------------------- o item ligado, pelo código


def test_item_ligado_de_outro_codigo_nao_paga_quando_ha_o_do_codigo(aparelho):
    """Os dois selos da certidão do RI: ligado o 17.2 pago e o 16.1 por pagar,
    o selo do 16.1 não passa pelo 17.2."""
    con = _casa()
    p = _protocolo(con)
    _ligar(con, _item(con, p["protocolo_id"], codigo="17.2", quitado=1))
    _ligar(con, _item(con, p["protocolo_id"], codigo="16.1", quitado=0))
    r = _selar(con)
    assert r["selado"] is False and aparelho == []


def test_sem_item_ligado_do_codigo_vale_qualquer_ligado(aparelho):
    """O ato lavrado do RI leva no envelope o `codigo_tj` do formulário, que
    pode divergir do item que a tela ligou: aí vale o ligado, como antes."""
    con = _casa()
    p = _protocolo(con)
    _ligar(con, _item(con, p["protocolo_id"], codigo="17.2", quitado=1))
    assert _selar(con)["selado"] is True and len(aparelho) == 1


# ------------------------------------------------------------------ o quadro


def test_o_quadro_traz_os_candidatos_e_o_que_falta(aparelho):
    con = _casa()
    p = _protocolo(con)
    _item(con, p["protocolo_id"], quitado=1)
    r = _selar(con)
    quadro = r["quadro"]
    assert [c["protocolo_id"] for c in quadro["candidatos"]] == [p["protocolo_id"]]
    assert quadro["pedidos"] == [("16.1", 1)]
    assert quadro["faltam"][0]["codigo"] == "16.1"


def test_os_quatro_motivos_de_ficar_fora_da_lista():
    """Atribuição, encerrado, item de outro grupo e saldo zerado — cada um
    com a frase que a tela mostra. Quem pode entrar devolve None."""
    pedidos = [("13.17.2", 1), ("13.17.3", 1), ("13.17.4", 1)]
    aceitas = {"FIRMAS", "NOTAS"}
    pago = {"codigo_ato": "13.17.2", "quantidade": 1, "quitado": 1}
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "ABERTO", "atribuicao": "RI"}, [pago], pedidos, aceitas
    ).startswith("atribuição incompatível")
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "ENTREGUE", "atribuicao": "RI"}, [pago], pedidos, aceitas
    ) == "encerrado (Entregue)"
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "CANCELADO", "atribuicao": "FIRMAS"}, [pago], pedidos, aceitas
    ) == "encerrado (Cancelado)"
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "ABERTO", "atribuicao": "FIRMAS"},
        [{"codigo_ato": "16.1", "quantidade": 1, "quitado": 1}],
        pedidos, aceitas) == "sem item do grupo pedido"
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "ABERTO", "atribuicao": "NOTAS"},
        [{"codigo_ato": "13.17.2", "quantidade": 1, "quantidade_usada": 1,
          "quitado": 1}],
        pedidos, aceitas) == "sem saldo do item"
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "ABERTO", "atribuicao": "FIRMAS"}, [pago], pedidos, aceitas
    ) is None
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "ABERTO", "atribuicao": ""}, [pago], pedidos, aceitas
    ) is None
    assert CXP.motivo_de_ficar_fora(
        {"situacao": "ABERTO", "atribuicao": "NOTAS"},
        [{"codigo_ato": "13.17.4", "quantidade": 1, "quitado": 1}],
        [("13.*", 1)], aceitas) is None


def test_o_em_atendimento_de_ri_aparece_sem_virar_candidato():
    """Pago no 13.17.2 e em atendimento, mas aberto como RI: a lista que
    escolhe o selo não o oferece, e a montagem da tela o mostra com o motivo.
    Listar não pede selo."""
    con = _casa()
    ri = _protocolo(con, atribuicao="RI")
    _item(con, ri["protocolo_id"], codigo="13.17.2", quitado=1)
    firmas = _protocolo(con, atribuicao="FIRMAS")
    _item(con, firmas["protocolo_id"], codigo="13.17.4", quitado=1)
    CXP.atender(con, usuario=ESCREVENTE, protocolo=ri["numero"], agora=AGORA)
    con.commit()
    so_os_que_pagam = AS.candidatos_do_ato(
        con, tabela="nt_reconhecimentos", pedidos=[("13.17.2", 1)],
        pre_marcar_protocolo_id=ri["protocolo_id"], hoje=HOJE)
    assert [c["protocolo_id"] for c in so_os_que_pagam] == []
    s = AS.seletor_do_ato(con, tabela="nt_reconhecimentos", usuario=ESCREVENTE,
                          hoje=HOJE)
    por_id = {c["protocolo_id"]: c for c in s["candidatos"]}
    assert por_id[ri["protocolo_id"]]["selecionavel"] is False
    assert "atribuição incompatível" in por_id[ri["protocolo_id"]]["motivo"]
    assert por_id[firmas["protocolo_id"]]["selecionavel"] is True
    assert por_id[firmas["protocolo_id"]]["cobre_tudo"] is True
    assert s["pedidos"] == [("13.*", 1)]


def test_firmas_em_atendimento_continua_candidato_e_o_ri_do_imovel_tambem():
    """FIRMAS paga a firma. RI com item 16 paga a certidão do imóvel. Nenhum
    dos dois vira linha «de fora»."""
    con = _casa()
    firmas = _protocolo(con, atribuicao="FIRMAS")
    _item(con, firmas["protocolo_id"], codigo="13.17.2", quitado=1)
    CXP.atender(con, usuario=ESCREVENTE, protocolo=firmas["numero"], agora=AGORA)
    imovel = _protocolo(con, atribuicao="RI")
    _item(con, imovel["protocolo_id"], codigo="16.24.4", quitado=1)
    con.commit()
    firma = AS.seletor_do_ato(con, tabela="nt_reconhecimentos",
                              usuario=ESCREVENTE, hoje=HOJE)
    assert [c["protocolo_id"] for c in firma["candidatos"]] == [firmas["protocolo_id"]]
    assert firma["candidatos"][0]["selecionavel"] is True
    certidao = AS.candidatos_do_ato(con, tabela="ri_certidoes",
                                    pedidos=[("16.24.4", 1)], hoje=HOJE)
    assert [c["protocolo_id"] for c in certidao] == [imovel["protocolo_id"]]
    assert certidao[0]["selecionavel"] is True


def test_a_macro_marca_o_unico_e_nao_escolhe_quando_ha_dois():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(RAIZ / "templates")))
    macro = env.get_template("_protocolo_do_selo.html").module.protocolo_do_selo
    um = [{"protocolo_id": 7, "numero": "2026.10.60", "interessado": "X",
           "itens": [{"codigo": "13.17.4", "saldo": 1, "pago": True}],
           "cobre_tudo": True, "faltam": [], "pre_marcado": False}]
    html = str(macro(um, [("13.17.4", 1)]))
    assert 'value="7"' in html and "checked" in html
    dois = um + [dict(um[0], protocolo_id=8, numero="2026.10.61")]
    assert "checked" not in str(macro(dois, [("13.17.4", 1)]))
    com_rota = str(macro(um, [("13.17.4", 1)], url_de_selar="/x/1/selar",
                         csrf_token="tok"))
    assert 'action="/x/1/selar"' in com_rota and "selar de novo" in com_rota
    fora = {"protocolo_id": 9, "numero": "2099.10.77",
            "interessado": "CLIENTE DE EXEMPLO",
            "itens": [{"codigo": "13.17.2", "saldo": 1, "pago": True}],
            "cobre_tudo": False, "faltam": [], "pre_marcado": False,
            "selecionavel": False, "motivo": "atribuição incompatível (RI; este ato aceita FIRMAS, NOTAS)"}
    sozinho = str(macro([fora], [("13.17.2", 1), ("13.17.3", 1), ("13.17.4", 1)],
                        atendendo={"id": 9, "numero": "2099.10.77"}))
    assert 'type="radio"' not in sozinho
    assert "atribuição incompatível" in sozinho
    assert "13.17.2" in sozinho and "13.17.3" in sozinho and "13.17.4" in sozinho
    assert "não dá para escolher" in sozinho
    # O outro protocolo, único de verdade, não vem marcado: quem está em
    # atendimento é o que ficou de fora, e escolher o do vizinho gastaria
    # o pagamento dele.
    ao_lado = dict(um[0], protocolo_id=8, numero="2099.10.78")
    junto = str(macro([fora, ao_lado], [("13.17.4", 1)],
                      atendendo={"id": 9, "numero": "2099.10.77"}))
    assert 'value="9"' not in junto and "checked" not in junto
    assert 'value="8"' in junto


# ------------------------------------------- todas as atribuições (22/10, tarde)


def test_a_atribuicao_do_balcao_e_escolha_e_nao_padrao():
    assert CXP.atribuicao_escolhida(" firmas ") == "FIRMAS"
    for atrib in CXP.ATRIBUICOES_DO_BALCAO:
        assert CXP.atribuicao_escolhida(atrib) == atrib
    for vazio in ("", "   ", None, "XYZ"):
        with pytest.raises(CXP.ProtocoloError, match="Escolha a atribuição"):
            CXP.atribuicao_escolhida(vazio)


def test_a_familia_do_codigo_acha_qualquer_item_do_grupo():
    """A tela que ainda não sabe o item exato (a habilitação, o assento) pede
    «14.*», e entram os itens do grupo 14 da tabela — e só eles."""
    con = _casa()
    rcpn = _protocolo(con, atribuicao="RCPN")
    _item(con, rcpn["protocolo_id"], codigo="14.1.1", quitado=1)
    outro = _protocolo(con, atribuicao="RCPN")
    _item(con, outro["protocolo_id"], codigo="13.17.2", quitado=1)
    lista = AS.candidatos_do_ato(con, tabela="hc_habilitacoes",
                                 pedidos=[("14.*", 1)], hoje=HOJE)
    assert [c["protocolo_id"] for c in lista] == [rcpn["protocolo_id"]]
    assert lista[0]["cobre_tudo"] is True


def test_os_pedidos_padrao_sao_a_familia_da_atribuicao():
    assert AS.pedidos_padrao_do_ato("hc_habilitacoes") == [("14.*", 1)]
    assert AS.pedidos_padrao_do_ato("pt_atos") == [("17.*", 1)]
    assert AS.pedidos_padrao_do_ato("at_certidoes") == [("15.*", 1), ("16.*", 1)]
    assert AS.pedidos_padrao_do_ato("tabela_que_nao_existe") == []


def test_o_seletor_junta_as_familias_como_alternativas():
    """A certidão do Livro 3 pode ser paga por item do RTD/RCPJ ou do RI: um
    protocolo que paga UMA das famílias cobre."""
    con = _casa()
    ri = _protocolo(con, atribuicao="RI")
    _item(con, ri["protocolo_id"], codigo="16.24.4", quitado=1)
    s = AS.seletor_do_ato(con, tabela="at_certidoes", usuario=ESCREVENTE, hoje=HOJE)
    assert [c["protocolo_id"] for c in s["candidatos"]] == [ri["protocolo_id"]]
    assert s["candidatos"][0]["cobre_tudo"] is True
    assert s["atendendo"] is None


def test_toda_rota_que_ja_trata_o_campo_esta_fora_do_gancho():
    """As rotas de Notas e do RI tratam `protocolo_selo` por conta própria; o
    gancho de todas as telas pula essas, senão a auditoria sai em dobro. Rota
    nova que passe a tratar o campo tem de entrar na lista."""
    import ast
    fonte = (RAIZ / "gratuidade_comprovante_web.py").read_text(encoding="utf-8")
    lista = None
    for no in ast.walk(ast.parse(fonte)):
        if (isinstance(no, ast.Assign) and getattr(no.targets[0], "id", "") ==
                "JA_ESCOLHEM_O_PROTOCOLO"):
            lista = {e.value for e in no.value.args[0].elts}
    assert lista, "a lista JA_ESCOLHEM_O_PROTOCOLO sumiu"
    tratam = set()
    for arquivo in ("notas_web.py", "ri_web.py"):
        arvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.FunctionDef):
                continue
            rota = any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "route"
                       for d in no.decorator_list)
            corpo = ast.get_source_segment((RAIZ / arquivo).read_text(encoding="utf-8"), no) or ""
            if rota and ("protocolo_selo" in corpo or "_atender_o_protocolo_escolhido(" in corpo):
                tratam.add(no.name)
    assert tratam <= lista, f"rotas que tratam o campo e não estão na lista: {tratam - lista}"

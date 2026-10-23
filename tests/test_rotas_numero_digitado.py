"""O NÚMERO QUE A TELA MANDA NÃO DERRUBA A TELA — LD13, 21/10/2026.

O pedido do oficial foi «nenhuma pendência». A revisão do LD10 achou, no
Registro de Imóveis, `int(...)` direto sobre o que a tela mandou: «abc» virava
`ValueError` e a tela de erro (HTTP 500). O LD13 fez a mesma varredura nos
outros módulos de tela, e este arquivo prova cada ponto trocado, rota a rota.

AS QUATRO FORMAS DO 500, todas medidas antes do conserto:

    «abc»          `int("abc")` sem guarda;
    «²»            passa pelo `isdigit()`, e o `int()` o recusa;
    5.000 dígitos  passa pelos dois guardas e o Python recusa o `int()` (o
                   teto dele é 4.300 dígitos);
    30 dígitos     o `int()` aceita, mas o número não cabe no banco: o
                   OFFSET da página, o INSERT em coluna inteira e o texto
                   cru comparado com coluna `bigint` («invalid input syntax
                   for type bigint» — no SQLite essa comparação só não
                   achava nada; no PostgreSQL ela derruba a consulta).

A régua é UMA, `seguranca_web.numero_digitado` (a do LD10, que mudou de casa).
O que ela recusa segue o caminho que a rota já tinha para «não achei» ou
«nada marcado», ou ganha recado — nunca a tela de erro. Entrada válida se
comporta como antes; isso os testes de cada módulo já cobrem.

DADOS: só os fictícios da casa (`docs/AGENTES.md`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco  # noqa: E402

TELEFONE = "(99) 3000-0000"

RUINS = {
    "abc": "abc",
    "expoente": "²",
    "30-digitos": "9" * 30,
    "5000-digitos": "9" * 5000,
}
# Onde o valor vai para coluna `integer` (int4): 12 dígitos já não cabem.
INT4 = {**RUINS, "12-digitos": "9" * 12}
# Onde o valor vira página: o OFFSET de 18 dígitos passa do `bigint`.
PAGINA = {**RUINS, "18-digitos": "9" * 18}


def _casos(rotas: dict, valores=RUINS) -> list:
    return [pytest.param(rota, valor, id=f"{rota}-{nome}")
            for rota, ruins in rotas.items()
            for nome, valor in (ruins if isinstance(ruins, dict) else valores).items()]


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _post(c, url: str, dados: dict | None = None, **kw):
    return c.post(url, data=dados or {}, headers={"X-CSRF-Token": _token(c)}, **kw)


def _um(db, sql: str, params=()) -> dict | None:
    with db.connect() as con:
        linha = banco(con).um(sql, params)
    return dict(linha) if linha else None


def _nao_caiu(r, onde: str) -> None:
    assert r.status_code < 500, f"{onde}: HTTP {r.status_code}"


# =============================================== caixa_web

def _semear_a_tabela(db) -> None:
    """Uma vigência, um serviço de valor fixo e uma faixa do RI — o mínimo
    para «Acrescentar» chegar ao INSERT do item."""
    import emolumentos as EMOL
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, importado_em)
                       VALUES (10022, 'Período de 2026', 1, '2026-08-21')
                       ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao, ativo)
                       VALUES (900001, '16.1', 'Prenotação (teste)', 1)
                       ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                           ferc, femp, fadep, ferrfis, total)
                       VALUES (900001, 10022, '10,00', '1,00', '1,00', '1,00', '1,00',
                               '14,00') ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_faixas(tabela, vigencia, de, ate, codigo_tj,
                           emolumentos, ferc, femp, fadep, ferrfis, total)
                       VALUES (%s, 10022, '0,00', '1.000.000,00', '16.3.1', '10,00',
                               '1,00', '1,00', '1,00', '1,00', '14,00')""",
                    (EMOL.TABELA_RI,))


@pytest.fixture()
def caixa(cg_casa_logada):
    """O caixa aberto, a tabela semeada e um protocolo geral."""
    casa = cg_casa_logada
    c, db = casa["c"], casa["db"]
    _semear_a_tabela(db)
    _post(c, "/caixa", {"acao": "abrir", "saldo_inicial": "0,00"})
    _post(c, "/caixa/protocolos", {"acao": "novo", "interessado": "PEDRO EXEMPLO DOS SANTOS",
                                   "telefone": TELEFONE, "atribuicao": "OUTROS"})
    p = _um(db, "SELECT id FROM cx_protocolos ORDER BY id DESC LIMIT 1")
    assert p, "o protocolo de teste não abriu"
    import emolumentos as EMOL
    return {**casa, "protocolo_id": int(p["id"]), "tabela_ri": EMOL.TABELA_RI}


def _itens(pid: int) -> str:
    return f"/caixa/protocolos/{pid}/itens"


CAIXA = {
    # abrir o protocolo geral já ligado a uma prenotação do RI
    "abrir-ligado-ao-ri": lambda c, t, v: _post(c, "/caixa/protocolos", {
        "acao": "novo", "interessado": "BEATRIZ EXEMPLO DE SOUZA", "telefone": TELEFONE,
        "atribuicao": "RI", "ri_protocolo_id": v}),
    "pagina-da-lista": lambda c, t, v: c.get("/caixa/protocolos", query_string={"pagina": v}),
    "vincular-ao-ri": lambda c, t, v: _post(c, f"/caixa/protocolos/{t['protocolo_id']}", {
        "acao": "vincular_ri", "ri_protocolo_id": v}),
    "servico-do-item": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "acrescentar", "servico": v}),
    "tabela-do-item": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "acrescentar", "tabela": v, "base_calculo": "100.000,00"}),
    "quantidade-do-item": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "acrescentar", "servico": "900001", "quantidade": v}),
    "imoveis-do-item": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "acrescentar", "tabela": str(t["tabela_ri"]), "base_calculo": "100.000,00",
        "imoveis": v}),
    # cada um cabe no `integer`; o produto (16.31: quantidade × imóveis), não
    "quantidade-vezes-imoveis": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "acrescentar", "tabela": str(t["tabela_ri"]),
        "base_calculo": "100.000.000,00", "quantidade": v, "imoveis": v}),
    "quitar-item": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "quitar", "item_id": v}),
    "desquitar-item": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "desquitar", "item_id": v}),
    "remover-item": lambda c, t, v: _post(c, _itens(t["protocolo_id"]), {
        "acao": "remover", "item_id": v}),
    "tabela-das-faixas": lambda c, t, v: c.get("/caixa/emolumentos", query_string={
        "tabela": v, "valor": "100.000,00"}),
    "conferir-caixa": lambda c, t, v: _post(c, "/caixa", {"acao": "conferir", "caixa_id": v}),
    "estornar-lancamento": lambda c, t, v: _post(c, "/caixa", {
        "acao": "estornar", "lancamento_id": v, "motivo": "Lançado em duplicidade"}),
    "editar-lancamento": lambda c, t, v: _post(c, "/caixa", {
        "acao": "editar", "lancamento_id": v, "valor": "1,00"}),
    "excluir-lancamento": lambda c, t, v: _post(c, "/caixa", {
        "acao": "excluir", "lancamento_id": v, "motivo": "Lançado em duplicidade"}),
    "usar-deposito": lambda c, t, v: _post(c, "/caixa/depositos", {
        "acao": "usar", "deposito_id": v, "valor_usar": "1,00"}),
    "devolver-deposito": lambda c, t, v: _post(c, "/caixa/depositos", {
        "acao": "devolver", "deposito_id": v, "motivo": "Desistência do cliente"}),
}
_VALORES_DO_CAIXA = {"pagina-da-lista": PAGINA, "quantidade-do-item": INT4,
                     "imoveis-do-item": INT4,
                     "quantidade-vezes-imoveis": {"cem-mil": "100000"}}


@pytest.mark.parametrize("rota,valor", _casos(
    {k: _VALORES_DO_CAIXA.get(k, RUINS) for k in CAIXA}))
def test_o_caixa_responde_ao_numero_que_nao_e_numero_sem_cair(caixa, rota, valor):
    """Protocolo geral, itens, lançamentos, depósitos e a tabela de faixas.

    Nos lançamentos, depósitos e no «desquitar/remover», o id ia CRU para o
    `WHERE id=%s`: no SQLite só não achava; no PostgreSQL a consulta cai. A
    quantidade e os imóveis vão para `cx_protocolo_atos.quantidade`
    (`integer`), e a página para o OFFSET. Nada se grava com o número ruim.
    """
    antes = _um(caixa["db"], "SELECT count(*) AS n FROM cx_protocolo_atos")["n"]
    _nao_caiu(CAIXA[rota](caixa["c"], caixa, valor), rota)
    depois = _um(caixa["db"], "SELECT count(*) AS n FROM cx_protocolo_atos")["n"]
    assert depois == antes, f"{rota}: entrou item com o número ruim"


# =============================================== gestor_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in RUINS.items()])
def test_o_visto_do_gestor_ignora_o_caixa_marcado_que_nao_e_numero(cg_casa_logada, valor):
    """`{int(x) ... if x.isdigit()}`: o «²» e os 5.000 dígitos passavam pelo
    guarda e o `int()` caía. Marcado que não é número é como não marcado."""
    r = _post(cg_casa_logada["c"], "/administrativo/gestor/caixas/visto", {"caixa_id": valor})
    _nao_caiu(r, "caixa_id")


# =============================================== gratuidade_comprovante_web

COBERTURA = {
    "quadro-do-ato": lambda c, v: c.get("/selo/cobertura",
                                        query_string={"tabela": "ri_atos", "ato_id": v}),
    "vincular-item": lambda c, v: _post(c, "/selo/cobertura/vincular", {"item_id": v}),
    "vincular-ao-ato": lambda c, v: _post(c, "/selo/cobertura/vincular", {
        "item_id": "1", "tabela": "ri_atos", "ato_id": v}),
    "pagar-com-deposito": lambda c, v: _post(c, "/selo/cobertura/deposito", {"item_id": v}),
    "diferir": lambda c, v: _post(c, "/selo/cobertura/diferir", {"item_id": v}),
}


@pytest.mark.parametrize("rota,valor", _casos(dict.fromkeys(COBERTURA, RUINS)))
def test_a_cobertura_do_selo_recusa_o_item_e_o_ato_que_nao_sao_numero(
        cg_casa_logada, rota, valor):
    """`_ato_do_pedido` e `_item_do_pedido` já recusavam texto (400), mas pelo
    `isdigit()`: o «²» e os 5.000 dígitos chegavam ao `int()`."""
    _nao_caiu(COBERTURA[rota](cg_casa_logada["c"], valor), rota)


# =============================================== nu_avisos_web

@pytest.mark.parametrize("campo,valor", _casos(
    {"recorrencia_dias": RUINS, "recorrencia_dia_semana": RUINS}))
def test_o_aviso_recorrente_recusa_o_dia_que_nao_e_numero(cg_casa_logada, campo, valor):
    """O dia da semana vinha do formulário para `int()` sem guarda. Agora é o
    mesmo recado do dia fora de 0–6, e o aviso não se cria."""
    casa = cg_casa_logada
    r = _post(casa["c"], "/admin/avisos/novo", {
        "titulo": "Aviso de teste", "corpo": "Conferir o caixa do dia.",
        "recorrente": "1", campo: valor})
    _nao_caiu(r, campo)
    assert not _um(casa["db"], "SELECT id FROM nu_avisos WHERE titulo=%s",
                   ("Aviso de teste",)), "o aviso com o dia ruim foi criado"


# =============================================== onr_certidoes_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in RUINS.items()])
def test_a_busca_de_certidoes_do_onr_aceita_qualquer_texto_nos_dias(cg_casa_logada, valor):
    """`int(request.form.get("dias") or 30)` sem guarda. O que não é número
    vale como o campo vazio (30 dias); a consulta segue para a Central."""
    r = _post(cg_casa_logada["c"], "/ri/onr/certidoes/buscar", {"dias": valor})
    _nao_caiu(r, "dias")


# =============================================== protesto_repasse_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in RUINS.items()])
def test_a_guia_do_repasse_recusa_o_pagamento_marcado_que_nao_e_numero(cg_casa_logada, valor):
    """Os marcados guardavam por `isdigit()`, fora do `try`: o «²» e os
    5.000 dígitos caíam. A guia é dinheiro: marcado com cara de número que
    não é pagamento recusa a guia inteira, como o número que não está
    pendente sempre recusou — não vira «todos os pendentes». (O repasse
    direto e a relação diária já apanhavam o `ValueError` nas RECUSAS.)"""
    casa = cg_casa_logada
    _nao_caiu(_post(casa["c"], "/protesto/repasses/guias", {"ato_id": valor}), "ato_id")
    assert not _um(casa["db"], "SELECT id FROM pt_repasse_guias ORDER BY id LIMIT 1"), (
        "a guia saiu com o marcado ruim")


# =============================================== revisao_previa_web

@pytest.fixture()
def revisao_ligada(cg_casa_logada, monkeypatch):
    """A revisão prévia ligada sem a IA: o dossiê é fixo e a leitura em
    segundo plano não sai daqui."""
    import revisao_previa as RV
    monkeypatch.setattr(RV, "ligada", lambda con, pasta: True)
    monkeypatch.setattr(RV, "dossie_ri", lambda *a, **k: "=== ATO A LAVRAR ===\nR teste")
    monkeypatch.setattr(RV, "ler_em_segundo_plano", lambda *a, **k: None)
    return cg_casa_logada


REVISAO = {
    "prenotacao-dos-anexos": lambda c, v: _post(c, "/revisao-previa/ri/1", {
        "tipo": "R", "teor": "REGISTRO DE COMPRA E VENDA de teste.",
        "prenotacao_id_ui": v}),
    "apontamento-suprido": lambda c, v: _post(c, "/revisao-previa/1/suprir", {"indice": v}),
}


@pytest.mark.parametrize("rota,valor", _casos(dict.fromkeys(REVISAO, RUINS)))
def test_a_revisao_previa_ignora_a_prenotacao_e_o_apontamento_que_nao_sao_numero(
        revisao_ligada, rota, valor):
    """A prenotação dos anexos e o índice do apontamento guardavam por
    `isdigit()`. O que não é número vale como não informado."""
    _nao_caiu(REVISAO[rota](revisao_ligada["c"], valor), rota)


# =============================================== ri_revisao_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in RUINS.items()])
def test_a_nota_de_revisao_da_ficha_recusa_o_ato_que_nao_e_numero(cg_casa_logada, valor):
    """`int(ato_id) if ato_id else None` dentro da chamada: «abc» era 500
    antes mesmo de se conferir a matrícula. Agora é o recado de ato não
    achado, e nada se anota."""
    casa = cg_casa_logada
    r = _post(casa["c"], "/registro-imoveis/1/revisoes", {
        "ato_id": valor, "assunto": "Cadeia dominial",
        "nota": "Conferir a cadeia dominial desta ficha."})
    _nao_caiu(r, "ato_id")


# =============================================== acervo_correcao_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in RUINS.items()])
def test_a_correcao_do_acervo_abre_sem_linha_quando_o_id_nao_e_numero(cg_casa_logada, valor):
    """`int(row_id) if row_id.isdigit()`: o «²» e os 5.000 dígitos caíam."""
    r = cg_casa_logada["c"].get("/administrativo/acervo/corrigir",
                                query_string={"tabela": "ri_matriculas", "id": valor})
    _nao_caiu(r, "id")


# =============================================== ajuda_web

AJUDA = {
    "verbete-em-edicao": lambda c, v: c.get("/ajuda/base", query_string={"editar": v}),
    "gravar-verbete": lambda c, v: _post(c, "/ajuda/base/gravar", {
        "id": v, "titulo": "Verbete de teste da casa",
        "texto": "O caixa fecha no fim do dia, com a conferência do oficial."}),
}


@pytest.mark.parametrize("rota,valor", _casos(dict.fromkeys(AJUDA, RUINS)))
def test_a_base_da_ajuda_nao_cai_nem_cria_verbete_com_numero_ruim(cg_casa_logada, rota, valor):
    """«Gravar» com `id` que não é número caía no `int()`; tratá-lo como
    vazio criaria um verbete NOVO no lugar de editar — por isso recusa."""
    casa = cg_casa_logada
    _nao_caiu(AJUDA[rota](casa["c"], valor), rota)
    if rota == "gravar-verbete":
        assert not _um(casa["db"], "SELECT id FROM aj_verbetes WHERE titulo=%s",
                       ("Verbete de teste da casa",)), "virou verbete novo"


# =============================================== modelos_editor_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in RUINS.items()])
def test_restaurar_versao_do_modelo_responde_400_ao_id_que_nao_e_numero(cg_casa_logada, valor):
    """`int(dados.get("versao_id") or 0)` dentro de um `try` que só apanhava
    `EditorError`: «abc» no JSON era 500. A API responde JSON com o erro."""
    c = cg_casa_logada["c"]
    r = c.post("/modelos/editor/api/restaurar", json={"versao_id": valor},
               headers={"X-CSRF-Token": _token(c)})
    _nao_caiu(r, "versao_id")


# =============================================== robo_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in INT4.items()])
def test_o_peso_do_exemplo_do_robo_que_nao_cabe_vale_um(cg_casa_logada, valor):
    """`peso` vai para `robo_exemplo.peso` (`integer`): o `try` só pegava o
    texto, e o número grande derrubava o INSERT. Vale o padrão da tela, 1."""
    import robo_schema as SCH
    casa = cg_casa_logada
    with casa["db"].transaction() as con:
        rid = SCH.criar_robo(con, nome="Robô de teste", ato="TESTE", provedor="nenhum",
                             prompt="Responda curto.", ativo=1, agora="2026-10-21 10:00:00")
    r = _post(casa["c"], f"/robos/{rid}/exemplos", {
        "entrada": "pergunta", "saida_esperada": "resposta", "peso": valor})
    _nao_caiu(r, "peso")
    linha = _um(casa["db"], "SELECT peso FROM robo_exemplo WHERE robo_id=%s", (rid,))
    assert linha and linha["peso"] == 1, linha


# =============================================== selador_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in PAGINA.items()])
def test_a_lista_de_selos_emitidos_volta_a_primeira_pagina_com_pagina_ruim(cg_casa_logada, valor):
    """O `try` pegava o texto; a página de 18 ou 30 dígitos passava e o
    OFFSET dela estourava o `bigint`."""
    _nao_caiu(cg_casa_logada["c"].get("/selos", query_string={"pagina": valor}), "pagina")


# =============================================== rc_pedidos_web

@pytest.fixture()
def pedido_de_registro(cg_casa_logada):
    """Um pedido P13 (registro) da Central, pendente."""
    casa = cg_casa_logada
    with casa["db"].transaction() as con:
        pid = banco(con).escrever(
            """INSERT INTO rc_pedidos(modulo, ambiente, numero_pedido, teor, baixado_em)
               VALUES ('P13', 'HOMOLOGACAO', 'TESTE-LD13-1', '{}', '2026-10-21 09:00:00')
               RETURNING id""")[0]["id"]
    return {**casa, "pedido_id": int(pid)}


PEDIDOS = {
    "assento-registrado": lambda c, t, v: _post(c, f"/rcpn/pedidos/{t['pedido_id']}/registrado",
                                                {"assento_id": v}),
    "volta-da-assinatura": lambda c, t, v: _post(c, "/rcpn/certidao-eletronica/999999/assinar",
                                                 {"volta_para": v}),
}


@pytest.mark.parametrize("rota,valor", _casos(
    {"assento-registrado": INT4, "volta-da-assinatura": RUINS}))
def test_os_pedidos_da_central_nao_caem_com_assento_ou_volta_ruim(
        pedido_de_registro, rota, valor):
    """O assento lavrado ia para `rc_pedidos.assento_id` (`integer`) sem
    conferir o tamanho; o «volte para» guardava por `isdigit()`."""
    t = pedido_de_registro
    _nao_caiu(PEDIDOS[rota](t["c"], t, valor), rota)
    if rota == "assento-registrado":
        assert _um(t["db"], "SELECT assento_id FROM rc_pedidos WHERE id=%s",
                   (t["pedido_id"],))["assento_id"] is None


# =============================================== habilitacao_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in RUINS.items()])
def test_a_habilitacao_aberta_nao_cai_com_a_leitura_que_nao_e_numero(
        cg_casa_logada, monkeypatch, valor):
    """`leitura_id` guardava por `isdigit()`, e o `int()` caía DEPOIS de a
    habilitação já estar aberta — quem abriu via a tela de erro. O abrir é
    um dublê aqui: o que se mede é só a leitura dos anexos."""
    import habilitacao as HAB
    monkeypatch.setattr(HAB, "abrir", lambda con, dados, **k: 1)
    r = _post(cg_casa_logada["c"], "/rcpn/habilitacoes/nova", {
        "nubente1_nome": "PEDRO EXEMPLO DOS SANTOS",
        "nubente2_nome": "BEATRIZ EXEMPLO DE SOUZA", "leitura_id": valor})
    _nao_caiu(r, "leitura_id")


# =============================================== pld_web

@pytest.mark.parametrize("valor", [pytest.param(v, id=k) for k, v in PAGINA.items()])
def test_o_caso_de_pld_nao_cai_com_valor_sem_virgula_que_nao_cabe(cg_casa_logada, valor):
    """Valor sem vírgula é reais inteiros (`int(valor) * 100`): o «²» caía no
    `int()` (que o `except` mostrava cru), e o de 18 ou 30 dígitos, vezes
    100, estourava `valor_centavos` (`bigint`). O que tem cara de número e
    não cabe se recusa com recado: o caso não se abre sem o valor digitado."""
    casa = cg_casa_logada
    r = _post(casa["c"], "/administrativo/pld/abrir", {
        "valor": valor, "referencia": "Livro 1, folha 10", "data": "2026-10-20",
        "motivo": "Pagamento em espécie acima do limite."})
    _nao_caiu(r, "valor")
    if valor.isdigit():
        assert not _um(casa["db"], "SELECT id FROM pld_casos ORDER BY id LIMIT 1"), (
            "o caso se abriu sem o valor digitado")

"""As fichas do RCPJ e do RTD no layout novo, estado por estado.

O QUE DEFENDEM
    A ficha do título tem fases (`rg_titulo_fases`): apresentação, qualificação e registro, e a Central e o
    encerramento como apoio. O risco é a ficha abrir na fase errada, travar o que não devia, esconder o que
    espera ação ou perder o formulário de uma fase. Cada caso abre, com o sistema de pé e no layout novo, a
    ficha que `layout_semente_rcpj` deixou num estado do rito, e confere o que aquele estado promete.

    A tabela de estados é a promessa, escrita à mão. O módulo puro é a referência de quem a página obedece: a
    página tem de dizer o que ele diz, e os dois têm de concordar com a tabela.

    O que o balcão e o auditor veem difere do que o oficial vê, e tem caso próprio.
"""
from __future__ import annotations

import re

import pytest

import layout_ensaio as E
from layout_casa import areas_pedidas, casa  # noqa: F401
import apostila as AP
import rg_notificacao as RN
import rg_titulo as TIT
import rg_titulo_fases as RF

pytestmark = pytest.mark.lento

_F, _L, _T = RF.FEITA, RF.LIBERADA, RF.TRAVADA
SEM_QUALIFICACAO = "Antes, a qualificação positiva"
SAIU = "Este título saiu sem registro"
DO_OFICIAL = "O registro é ato do oficial"
FASES = ["apresentacao", "qualificacao", "registro"]
SO_DO_OFICIAL = {"qualificar", "registrar", "concluir", "encerrar"}

# O que se grava na ficha do título, e em que fase mora cada formulário. `concluir` depende dos atos que o RTD
# tem, e por isso não entra na conta.
_BASE = {"editar": "apresentacao", "arquivo": "qualificacao", "qualificar": "qualificacao",
         "encaminhar": "central", "encerrar": "encerrar"}
_SAIU_DO_RITO = {"arquivo": "qualificacao", "encaminhar": "central"}
_REGISTRAR = {**_BASE, "registrar": "registro"}

#: chave da semente, situação, fase em que a ficha abre, estado das três fases, pendências das três, trava do
#: Registro, passagens pela Central, formulários que o oficial vê (ação -> fase)
ESTADOS = [
    pytest.param("recebido", RF.APRESENTADO, "qualificacao", (_F, _L, _T), (0, 1, 0), SEM_QUALIFICACAO, 1, _BASE,
                 id="recebido"),
    pytest.param("exigencia", RF.EXIGENCIA, "qualificacao", (_F, _L, _T), (0, 0, 0), SEM_QUALIFICACAO, 0, _BASE,
                 id="com-exigencia"),
    pytest.param("qualificado", RF.QUALIFICADO, "registro", (_F, _F, _L), (0, 0, 1), None, 0, _REGISTRAR,
                 id="qualificado"),
    pytest.param("registrado", RF.REGISTRADO, "registro", (_F, _F, _F), (0, 0, 0), None, 0,
                 {"arquivo": "qualificacao", "encaminhar": "central", "teor/previa": "registro"}, id="registrado"),
    pytest.param("devolvido", RF.DEVOLVIDO, "apresentacao", (_F, _F, _T), (0, 0, 0), SAIU, 0, _SAIU_DO_RITO,
                 id="devolvido"),
    pytest.param("cancelado", RF.CANCELADO, "apresentacao", (_F, _L, _T), (0, 0, 0), SAIU, 0, _SAIU_DO_RITO,
                 id="cancelado"),
    pytest.param("rcpj", RF.QUALIFICADO, "registro", (_F, _F, _L), (0, 0, 1), None, 0, _REGISTRAR,
                 id="rcpj-qualificado"),
    pytest.param("rcpj_exigencia", RF.EXIGENCIA, "qualificacao", (_F, _L, _T), (0, 0, 0), SEM_QUALIFICACAO, 0,
                 _BASE, id="rcpj-com-exigencia"),
    pytest.param("da_central", RF.APRESENTADO, "qualificacao", (_F, _L, _T), (0, 1, 0), SEM_QUALIFICACAO, 1, _BASE,
                 id="veio-da-central"),
]


@pytest.fixture(autouse=True)
def _so_com_a_area_semeada():
    if "rcpj" not in areas_pedidas():
        pytest.skip("CG_LAYOUT_AREAS não inclui a área rcpj: não há o que abrir")


# ------------------------------------------------------------------- o que se lê da página


def _abrir(casa, endereco: str, papel: str = "ADMIN"):  # noqa: F811
    r = casa.cliente(papel, "novo").get(endereco)
    assert r.status_code == 200, f"{papel} em {endereco}: HTTP {r.status_code}"
    html = r.get_data(as_text=True)
    return html, E.ler_pagina(html)


def _texto(html: str) -> str:
    sem = re.sub(r"<(script|style|template)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sem))


def _regua(html: str) -> dict[str, dict]:
    """As abas da régua, na ordem: o estado de cada uma, o que ela cobra e a contagem da Central."""
    achadas = {}
    for m in re.finditer(r'<a class="cg-fase([^"]*)"[^>]*data-cg-fase="(\w+)"[^>]*>(.*?)</a>', html, re.S):
        classes, fase, miolo = m.groups()
        pendencias = re.search(r'class="cg-fase-c"[^>]*>(\d+)<', miolo)
        contagem = re.search(r'class="cg-fase-q">(\d+)<', miolo)
        achadas[fase] = {"estado": classes.split()[-1], "pendencias": int(pendencias.group(1)) if pendencias else 0,
                         "contagem": int(contagem.group(1)) if contagem else 0}
    return achadas


def _avisos_da_barra(html: str) -> dict[str, str]:
    achados = re.findall(r'data-fase="(\w+)" data-cg-barra hidden>\s*<span class="cg-acao-aviso[^"]*">([^<]*)<', html)
    return {fase: aviso.strip() for fase, aviso in achados}


def _trava(html: str) -> list[str]:
    return re.findall(r'cg-trava-t">([^<]*)<', html)


def _acoes(p, titulo_id: int) -> dict[str, str]:
    """Os formulários de gravar da ficha do título: ação -> fase em que moram."""
    prefixo = f"/rcpj-rtd/titulo/{titulo_id}/"
    return {f["action"][len(prefixo):]: f["fase"] for f in p.formularios
            if f["method"] == "post" and f["no_conteudo"] and (f["action"] or "").startswith(prefixo)}


def _formularios(p) -> list[str]:
    return [f["action"] for f in p.formularios if f["method"] == "post" and f["no_conteudo"] and f["action"]]


def _o_que_o_modulo_diz(casa, titulo_id: int, pode_decidir: bool) -> dict:  # noqa: F811
    titulo = casa.um("SELECT * FROM rg_titulos WHERE id=%s", (titulo_id,))
    return RF.fases_do_titulo(
        titulo, qualificacoes=casa.ler("SELECT * FROM rg_qualificacoes WHERE titulo_id=%s", (titulo_id,)),
        encaminhamentos=casa.ler("SELECT * FROM rg_encaminhamentos WHERE titulo_id=%s", (titulo_id,)),
        tem_registro=bool(titulo["registro_id"]), pode_decidir=pode_decidir)


# ------------------------------------------------------------------- o título, estado por estado


@pytest.mark.parametrize("chave,situacao,inicial,estados,pendencias,trava,central,acoes", ESTADOS)
def test_a_ficha_do_titulo_em_cada_estado(casa, chave, situacao, inicial, estados, pendencias, trava,  # noqa: F811
                                          central, acoes):
    tid = casa.ids[f"rcpj_titulo_{chave}"]
    assert casa.um("SELECT situacao FROM rg_titulos WHERE id=%s", (tid,))["situacao"] == situacao, (
        "a semente saiu do estado que a ficha promete")
    html, p = _abrir(casa, f"/rcpj-rtd/titulo/{tid}")

    assert p.html_layout == "novo" and p.marcas["cg-ficha"] == 1, "a ficha não abriu no layout novo"
    assert [r["chave"] for r in p.regua] == [f"titulo-rtd-{tid}"], p.regua
    assert p.regua[0]["inicial"] == inicial, "a ficha abriu na fase errada"
    assert p.regua[0]["foco"] == "qualificacao", "o documento mora ao lado da decisão"
    assert TIT.SITUACOES[situacao] in p.cabecalho, "a situação não está no título da página"

    regua = _regua(html)
    terminal = situacao in RF.SITUACOES_TERMINAIS
    assert list(regua) == FASES + ["central"] + ([] if terminal else ["encerrar"]), list(regua)
    assert tuple(regua[f]["estado"] for f in FASES) == estados
    assert tuple(regua[f]["pendencias"] for f in FASES) == pendencias, "o que espera ação não está marcado"
    assert regua["central"]["contagem"] == central, "a passagem pela Central não conta"
    assert [f["fase"] for f in p.fases if f["barra"]] == FASES, "cada fase tem a sua barra de ação"
    assert [f["fase"] for f in p.fases if f["so_trava"]] == (["registro"] if trava else [])
    assert _trava(html) == ([trava] if trava else [])

    # o módulo é a referência: a página diz o que ele diz
    esperado = _o_que_o_modulo_diz(casa, tid, pode_decidir=True)
    assert esperado["inicial"] == inicial
    assert tuple(x["estado"] for x in esperado["fases"]) == estados
    assert tuple(x["pendencias"] for x in esperado["fases"]) == pendencias
    assert esperado["apoio"][0]["contagem"] == central
    assert _avisos_da_barra(html) == {x["chave"]: x["aviso"] for x in esperado["fases"]}
    if trava:
        assert esperado["fases"][2]["trava"]["titulo"] == trava

    feitas = {a: f for a, f in _acoes(p, tid).items() if a != "concluir"}
    assert feitas == acoes, "formulário fora da fase, ou faltando"


def test_a_ficha_do_titulo_escreve_o_plural_de_decisao(casa):  # noqa: F811
    html, _p = _abrir(casa, f"/rcpj-rtd/titulo/{casa.ids['rcpj_titulo_recebido']}")
    assert "decisãoões" not in html, "0 decisãoões"


def test_a_tabela_dos_atos_da_ficha_do_titulo_diz_o_livro_e_o_ato_como_a_pessoa_os_conhece(casa):  # noqa: F811
    rid = casa.ids["rcpj_registro_do_titulo"]
    livro = casa.um("SELECT l.numero FROM rg_atos a JOIN nu_livros l ON l.id = a.livro_id WHERE a.registro_id=%s "
                    "ORDER BY a.id LIMIT 1", (rid,))["numero"]
    html, _p = _abrir(casa, f"/rcpj-rtd/titulo/{casa.ids['rcpj_titulo_registrado']}")
    linhas = re.findall(r"<tr>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>", html.split("O registro lavrado", 1)[1])
    assert linhas, "a ficha não trouxe a tabela dos atos"
    assert [livros for _ato, livros in linhas] == [str(livro)] * len(linhas), "a coluna Livro traz o id do banco"
    assert {ato for ato, _livro in linhas} <= {"Registro", "Averbação", "Cancelamento"}, "o tipo vem como código"


@pytest.mark.parametrize("papel,chave,situacao", [
    ("USER", "recebido", RF.APRESENTADO), ("USER", "qualificado", RF.QUALIFICADO),
    ("USER", "registrado", RF.REGISTRADO), ("USER", "devolvido", RF.DEVOLVIDO),
    ("AUDITOR", "recebido", RF.APRESENTADO), ("AUDITOR", "qualificado", RF.QUALIFICADO),
    ("AUDITOR", "registrado", RF.REGISTRADO),
    ("AUDITOR", "devolvido", RF.DEVOLVIDO)])
def test_quem_nao_qualifica_nao_recebe_cobranca_nem_formulario_do_oficial(casa, papel, chave,  # noqa: F811
                                                                           situacao):
    tid = casa.ids[f"rcpj_titulo_{chave}"]
    html, p = _abrir(casa, f"/rcpj-rtd/titulo/{tid}", papel)
    esperado = _o_que_o_modulo_diz(casa, tid, pode_decidir=False)
    regua = _regua(html)

    assert p.regua[0]["inicial"] == esperado["inicial"], "abriu onde o módulo não manda"
    assert all(regua[f]["pendencias"] == 0 for f in FASES), "a régua cobra de quem não pode fazer"
    assert "encerrar" not in regua, "encerrar é do oficial"
    assert not SO_DO_OFICIAL & set(_acoes(p, tid)), "formulário do oficial na tela de quem não decide"
    assert _avisos_da_barra(html) == {x["chave"]: x["aviso"] for x in esperado["fases"]}
    if situacao == RF.QUALIFICADO:
        assert _trava(html) == [DO_OFICIAL]
        assert p.regua[0]["inicial"] == "qualificacao", "o balcão não abre numa fase travada"
    if papel == "AUDITOR":
        assert not _acoes(p, tid), "o auditor consulta e não pratica"


@pytest.mark.parametrize("chave,pendencia", [("recebido", "qualificacao"), ("qualificado", "registro")])
def test_o_gerente_qualifica_e_registra_como_o_oficial(casa, chave, pendencia):  # noqa: F811
    tid = casa.ids[f"rcpj_titulo_{chave}"]
    html, p = _abrir(casa, f"/rcpj-rtd/titulo/{tid}", "MANAGER")
    assert [f for f in FASES if _regua(html)[f]["pendencias"]] == [pendencia]
    assert {"qualificar", "encerrar"} <= set(_acoes(p, tid)), "a decisão é de quem qualifica"
    assert ("registrar" in _acoes(p, tid)) == (chave == "qualificado")


# ------------------------------------------------------------------- o registro, estado por estado

#: chave da semente, situação, atribuição, os atos na ordem do livro, quantas certidões saíram dele
REGISTROS = [
    pytest.param("registro_do_titulo", "ATIVO", "RTD", ["REGISTRO", "AVERBACAO", "AVERBACAO"], 1,
                 id="ativo-com-averbacoes"),
    pytest.param("registro_cancelado", "CANCELADO", "RTD", ["REGISTRO", "CANCELAMENTO"], 1, id="cancelado"),
    pytest.param("registro_da_pj", "ATIVO", "RCPJ", ["REGISTRO"], 0, id="da-pessoa-juridica"),
]


@pytest.mark.parametrize("chave,situacao,atribuicao,atos,certidoes", REGISTROS)
def test_a_ficha_do_registro_em_cada_estado(casa, chave, situacao, atribuicao, atos, certidoes):  # noqa: F811
    rid = casa.ids[f"rcpj_{chave}"]
    registro = casa.um("SELECT * FROM rg_registros WHERE id=%s", (rid,))
    assert registro["situacao"] == situacao, "a semente saiu do estado que a ficha promete"
    html, p = _abrir(casa, f"/rcpj-rtd/{rid}")
    acoes, ficha = _formularios(p), f"/rcpj-rtd/{rid}"

    assert re.search(rf"<span>O registro</span><small>{situacao}</small>", html), "a situação não está na ficha"
    assert re.findall(r"<td><strong>(REGISTRO|AVERBACAO|CANCELAMENTO)</strong></td>", html) == atos
    assert re.search(r"(\d+) emitida\(s\) deste registro", html).group(1) == str(certidoes)
    # só se averba e se cancela o registro ativo, e cada ato leva a sua etiqueta
    assert acoes.count(f"{ficha}/lancar") == (2 if situacao == "ATIVO" else 0), "lançar averbação e cancelamento"
    assert len([a for a in acoes if a.endswith("/etiqueta")]) == len(atos)
    # o que é do livro de pessoa jurídica e o que é do RTD
    assert (f"{ficha}/dados-pj" in acoes) == (registro["serie"] == "PJ_A")
    assert (f"/rcpj-rtd/notificacoes?registro_id={rid}" in [x["href"] for x in p.links]) == (atribuicao == "RTD"), (
        "a notificação extrajudicial é do RTD")
    assert {f"{ficha}/corrigir-requerente", f"{ficha}/arquivo"} <= set(acoes)
    assert f"/atribuicoes/certidoes/RCPJ_RTD/{rid}" in acoes, "a certidão sai da ficha do registro"


def test_o_balcao_nao_corrige_o_cadastro_do_registro(casa):  # noqa: F811
    rid = casa.ids["rcpj_registro_da_pj"]
    _html, p = _abrir(casa, f"/rcpj-rtd/{rid}", "USER")
    acoes = _formularios(p)
    assert f"/rcpj-rtd/{rid}/lancar" in acoes, "o balcão lavra"
    assert not {f"/rcpj-rtd/{rid}/dados-pj", f"/rcpj-rtd/{rid}/corrigir-requerente"} & set(acoes), (
        "ler o estatuto e corrigir o cadastro são do oficial")


def test_as_rotas_recusam_ao_auditor_o_que_as_fichas_ainda_oferecem(casa):  # noqa: F811
    """A metade dos defeitos abaixo que é do servidor: ele já recusa, e é a tela que não acompanha."""
    rid, tid = casa.ids["rcpj_registro_do_titulo"], casa.ids["rcpj_titulo_registrado"]
    for endereco in (f"/rcpj-rtd/{rid}/lancar", f"/rcpj-rtd/{rid}/teor/previa", f"/rcpj-rtd/titulo/{tid}/teor/previa"):
        r = casa.postar(endereco, papel="AUDITOR", tipo="AVERBACAO")
        assert r.status_code == 403, f"{endereco}: o auditor recebeu HTTP {r.status_code}"


def test_o_auditor_nao_ve_formulario_de_lancar_na_ficha_do_registro(casa):  # noqa: F811
    rid = casa.ids["rcpj_registro_do_titulo"]
    _html, p = _abrir(casa, f"/rcpj-rtd/{rid}", "AUDITOR")
    assert not _formularios(p), "o auditor confere o livro e não lança nele"


def test_a_ficha_do_registro_oferece_o_termo_do_registro_que_a_rota_imprime(casa):  # noqa: F811
    rid, ato = casa.ids["rcpj_registro_do_titulo"], casa.ids["rcpj_ato_do_registro"]
    _html, p = _abrir(casa, f"/rcpj-rtd/{rid}")
    assert f"/rcpj-rtd/ato/{ato}/teor" in [x["href"] for x in p.links], "o termo do registro não tem link na ficha"


def test_a_ficha_so_oferece_o_termo_da_averbacao_que_a_rota_imprime(casa):  # noqa: F811
    rid = casa.ids["rcpj_registro_do_titulo"]
    sem_documento = casa.um(
        "SELECT a.id FROM rg_atos a WHERE a.registro_id=%s AND a.tipo='AVERBACAO' AND NOT EXISTS "
        "(SELECT 1 FROM attachments x WHERE x.entity_type='RG_ATO' AND x.entity_id=a.id) ORDER BY a.id", (rid,))["id"]
    _html, p = _abrir(casa, f"/rcpj-rtd/{rid}")
    endereco = f"/rcpj-rtd/ato/{sem_documento}/teor"
    r = casa.cliente().get(endereco)
    assert r.mimetype == "application/pdf" or endereco not in [x["href"] for x in p.links], (
        "a ficha oferece um termo que a rota não imprime")


def test_a_ficha_do_registro_nao_fala_a_lingua_do_desenvolvedor(casa):  # noqa: F811
    html, _p = _abrir(casa, f"/rcpj-rtd/{casa.ids['rcpj_registro_do_titulo']}")
    achados = re.findall(r"\btb[A-Z]\w+|\brg_[a-z_]+\b|\bRG_(?:ATO|REGISTRO|TITULO)\b", _texto(html))
    assert not achados, f"a tela cita identificadores internos: {sorted(set(achados))}"


# ------------------------------------------------------------------- a notificação, estado por estado

#: chave da semente, situação, o que a ficha oferece a quem qualifica, o que oferece ao balcão
NOTIFICACOES = [
    pytest.param("em_diligencia", "EM_DILIGENCIA", {"diligencia", "selar", "negativa"}, {"diligencia", "selar"},
                 id="em-diligencia"),
    pytest.param("sem_certidao", "POSITIVA", {"certidao"}, set(), id="resultado-sem-certidao"),
    pytest.param("positiva", "POSITIVA", {"averbar"}, set(), id="com-certidao"),
    pytest.param("negativa", "NEGATIVA", set(), set(), id="averbada"),
]


def _acoes_da_notificacao(p, notificacao_id: int) -> set[str]:
    achadas = set()
    for acao in _formularios(p):
        resto = acao.split("/rcpj-rtd/notificacao/", 1)[-1]
        if resto.startswith("selar/"):
            achadas.add("selar")
        elif resto.startswith(f"{notificacao_id}/"):
            achadas.add(resto.split("/", 1)[1])
    return achadas


@pytest.mark.parametrize("chave,situacao,oficial,balcao", NOTIFICACOES)
def test_a_notificacao_em_cada_estado(casa, chave, situacao, oficial, balcao):  # noqa: F811
    nid = casa.ids[f"rcpj_notificacao_{chave}"]
    assert casa.um("SELECT situacao FROM rg_notificacoes WHERE id=%s", (nid,))["situacao"] == situacao
    for papel, esperado in (("ADMIN", oficial), ("USER", balcao), ("AUDITOR", set())):
        html, p = _abrir(casa, f"/rcpj-rtd/notificacao/{nid}", papel)
        assert _acoes_da_notificacao(p, nid) == esperado, f"{papel}: o que a ficha oferece não é o que o estado pede"
    assert RN.SITUACOES[situacao] in _texto(html)
    assert ("ainda não registrado" in html) == (chave == "em_diligencia"), "a certidão espera o registro"
    assert ("— averbado" in html) == (chave == "negativa")
    assert ("Há selo suspenso" in html) == (chave == "em_diligencia"), "o alerta do selo que não saiu"


@pytest.mark.parametrize("chave,peca", [
    ("positiva", "procedi à NOTIFICAÇÃO de Carla Exemplo"), ("negativa", "não o(a) localizei nas 3 diligências")])
def test_a_certidao_da_notificacao_diz_o_resultado_que_a_ficha_deu(casa, chave, peca):  # noqa: F811
    cid = casa.ids[f"rcpj_certidao_da_notificacao_{chave}"]
    html, _p = _abrir(casa, f"/rcpj-rtd/notificacao/certidao/{cid}")
    selo = casa.um("SELECT selo FROM rg_notificacao_certidoes WHERE id=%s", (cid,))["selo"]
    texto = _texto(html)
    assert peca in texto and selo in texto, "o teor congelado e o selo têm de estar no papel"
    assert f"#/resumo/{selo}" in texto, "o selo se confere no portal"


# ------------------------------------------------------------------- as outras fichas da área


@pytest.mark.parametrize("chave,situacao,acoes,papeis", [
    pytest.param("livro_pedido", "Pedido", {"autenticar", "cancelar"}, 0, id="pedido"),
    pytest.param("livro_autenticado", "Autenticado", {"cancelar"}, 3, id="autenticado")])
def test_a_ficha_da_autenticacao_de_livro_em_cada_estado(casa, chave, situacao, acoes, papeis):  # noqa: F811
    lid = casa.ids[f"rcpj_{chave}"]
    html, p = _abrir(casa, f"/rcpj-rtd/livros-contabeis/{lid}")
    base = f"/rcpj-rtd/livros-contabeis/{lid}/"
    assert situacao in _texto(html)
    assert {a[len(base):] for a in _formularios(p) if a.startswith(base)} == acoes
    assert len([x for x in p.links if "/papel/" in x["href"]]) == papeis, "os termos e a certidão só da autenticada"
    _html, balcao = _abrir(casa, f"/rcpj-rtd/livros-contabeis/{lid}", "USER")
    assert not [a for a in _formularios(balcao) if a.startswith(base)], "autenticar e cancelar são do oficial"


def test_a_ficha_do_pedido_de_apostila_tem_um_documento_em_cada_situacao(casa):  # noqa: F811
    pid = casa.ids["rcpj_apostila_pedido"]
    emitida, sem_selo, cancelada, recusada, pendente = (
        casa.ids[f"rcpj_apostila_{k}"] for k in ("emitida", "sem_selo", "cancelada", "recusada", "pendente"))
    html, p = _abrir(casa, f"/apostila/pedido/{pid}")
    esperadas = [AP.SITUACOES[s] for s in ("EMITIDA", "EMITIDA", "CANCELADA", "RECUSADA", "PENDENTE")]
    assert re.findall(r"· <span>([^<]*)</span></h3>", html) == esperadas

    oficial = set(_formularios(p))
    assert oficial == {f"/apostila/{emitida}/cancelar", f"/apostila/{sem_selo}/selo", f"/apostila/{sem_selo}/cancelar",
                       f"/apostila/{pendente}/emitir", f"/apostila/{pendente}/recusar",
                       f"/apostila/pedido/{pid}/documento"}
    _html, balcao = _abrir(casa, f"/apostila/pedido/{pid}", "USER")
    assert set(_formularios(balcao)) == {a for a in oficial if not a.endswith("/cancelar")}, (
        "cancelar apostila emitida é do oficial e do gerente")
    _html, auditor = _abrir(casa, f"/apostila/pedido/{pid}", "AUDITOR")
    assert not _formularios(auditor), "o auditor confere e não pratica"
    for aid in (emitida, sem_selo, cancelada):
        texto = _texto(_abrir(casa, f"/apostila/{aid}/certidao")[0])
        assert "Ofício Único de Cidade Exemplo/MA" in texto and "nº de ordem" in texto
        assert ("foi CANCELADA" in texto) == (aid == cancelada)


@pytest.mark.parametrize("chave,cancelada,registro", [
    pytest.param("certidao", False, True, id="do-registro"),
    pytest.param("certidao_cancelada", True, True, id="cancelada"),
    pytest.param("certidao_negativa", False, False, id="negativa")])
def test_a_ficha_da_certidao_em_cada_estado(casa, chave, cancelada, registro):  # noqa: F811
    cid = casa.ids[f"rcpj_{chave}"]
    html, p = _abrir(casa, f"/atribuicoes/certidoes/{cid}")
    hrefs = [x["href"] for x in p.links]
    assert ("Esta certidão foi cancelada" in html) == cancelada
    assert (f"/atribuicoes/certidoes/{cid}/cancelar" in _formularios(p)) == (not cancelada), (
        "certidão cancelada não se cancela de novo")
    assert any(re.fullmatch(r"/rcpj-rtd/\d+", h) for h in hrefs) == registro, (
        "a negativa não tem registro para abrir")
    assert f"/atribuicoes/certidoes/{cid}/imprimir" in hrefs
    assert f"/atribuicoes/certidoes/{cid}/odt?formato=odt" in hrefs


# ------------------------------------------------------------------- os arquivos


#: endpoint -> o tipo que a rota devolve e como o arquivo começa. A rota que não acha o que imprimir avisa e
#: redireciona, e a varredura passaria por ela sem ver arquivo nenhum.
ARQUIVOS = {
    "rcpj_rtd_titulo_ver": {"application/pdf": b"%PDF", "image/png": b"\x89PNG"},
    "rcpj_rtd_titulo_teor_previa": {"application/pdf": b"%PDF"},
    "rcpj_rtd_certidao_previa": {"application/pdf": b"%PDF"},
    "rcpj_rtd_teor_averbacao_previa": {"application/pdf": b"%PDF"},
    "rcpj_rtd_ato_teor": {"application/pdf": b"%PDF"},
    "atribuicoes_certidao_imprimir": {"application/pdf": b"%PDF", "application/vnd.oasis.opendocument.text": b"PK"},
    "atribuicoes_certidao_odt": {"application/vnd.oasis.opendocument.text": b"PK"},
}


def test_toda_rota_de_arquivo_da_area_devolve_o_arquivo(casa):  # noqa: F811
    c = casa.cliente("ADMIN", "novo")
    por_rota = {endpoint: [] for endpoint in ARQUIVOS}
    for endpoint, endereco in casa.paginas:
        if endpoint in ARQUIVOS:
            por_rota[endpoint].append(endereco)
    assert all(por_rota.values()), f"rota de arquivo sem semente: {[e for e, v in por_rota.items() if not v]}"
    for endpoint, enderecos in por_rota.items():
        for endereco in enderecos:
            r = c.get(endereco)
            corpo = r.get_data()
            assert r.status_code == 200, f"{endereco}: HTTP {r.status_code} {r.headers.get('Location', '')}"
            assert r.mimetype in ARQUIVOS[endpoint], f"{endereco}: devolveu {r.mimetype}"
            assert corpo.startswith(ARQUIVOS[endpoint][r.mimetype]), (
                f"{endereco}: o arquivo não começa como {r.mimetype}")

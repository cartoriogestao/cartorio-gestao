"""As fichas em abas e em fases da área ri, com o sistema de pé: cada estado abre e cumpre o que promete.

O QUE ELES DEFENDEM
    Que a ficha, no layout novo, abre na aba certa para aquele estado, mostra as abas que o
    estado pede com a conta e a marca que o módulo puro diz, põe o que espera ação à vista, e
    traz o formulário que o estado precisa (e não traz o que não cabe), na aba em que ele cabe.

    O que toda página cumpre (quadro com porta, âncora que existe) é da varredura
    (`test_layout_todas_as_telas`), e não se repete aqui: este arquivo cobra o que só o estado sabe.
    No fim, uma conferência da própria semente: o que ela anotou abre com 200, sem recado de erro,
    e o arquivo sai como arquivo (o teste da semente só recusa 404 e 500).

    As sementes estão em `layout_semente_ri.py`: uma ficha em cada estado que muda a régua.
    `CG_LAYOUT_AREAS=ri` olha só esta área.

DUAS CONTAS, E NÃO UMA
    A página tem de dizer o que o módulo puro calcula com os fatos do banco, e o módulo tem de
    dizer o que o estado promete. Só a primeira conta passa quando é o próprio módulo que está
    errado, e por isso cada tabela traz a promessa escrita à mão.
"""
from __future__ import annotations

import re

import pytest

import layout_ensaio as E
import ra_abas as RAA
import ri_abas as RA
import ri_fases_prenotacao as RF
import usucapiao_abas as UA
from layout_casa import area_da_regra, areas_pedidas, casa  # noqa: F401

pytestmark = pytest.mark.lento

if "ri" not in areas_pedidas():
    pytest.skip("o ri não foi semeado nesta rodada (CG_LAYOUT_AREAS)", allow_module_level=True)


# ------------------------------------------------------------------ o que os testes usam

def _id(casa, chave: str) -> int:  # noqa: F811
    assert chave in casa.ids, f"a semente do ri não deixou `{chave}`"
    return casa.ids[chave]


def _abrir(casa, endpoint: str, consulta=None, **args):  # noqa: F811
    endereco = casa.pagina(endpoint, consulta, **args)
    r = casa.cliente("ADMIN", "novo").get(endereco)
    assert r.status_code == 200, f"{endereco}: HTTP {r.status_code} {r.headers.get('Location', '')}"
    html = r.get_data(as_text=True)
    return html, E.ler_pagina(html)


def _marcas(html: str) -> dict[str, dict]:
    """Por aba, o que a régua desenha: a conta (`cg-fase-q`) e a marca de pendência (`cg-fase-c`)."""
    saida = {}
    for tag in re.finditer(r'<a class="(cg-fase[^"]*)"[^>]*data-cg-fase="([a-z-]+)"[^>]*>(.*?)</a>', html, re.S):
        classes, chave, miolo = tag.groups()
        conta = re.search(r'class="cg-fase-q">(\d+)<', miolo)
        marca = re.search(r'class="cg-fase-c"[^>]*>(\d+)<', miolo)
        saida[chave] = {"classes": classes.split(), "contagem": int(conta.group(1)) if conta else 0,
                        "alerta": int(marca.group(1)) if marca else 0}
    return saida


def _espera(html: str) -> list[str]:
    """As linhas do quadro «O que espera ação»."""
    return [" ".join(x.split()) for x in re.findall(
        r'<li class="pendente">\s*<span class="cg-falta-m"[^>]*></span>\s*<span>(.*?)</span>', html, re.S)]


def _acoes(p) -> set[str]:
    return {f["action"] for f in p.formularios if f["action"]}


def _botoes(p) -> set[tuple[str, str]]:
    return {(b["nome"], b["valor"]) for f in p.formularios for b in f["botoes"] if b["nome"]}


def _linhas(casa, comando: str, parametros=()) -> list:  # noqa: F811
    return casa.ler(comando, parametros)


def _n(casa, comando: str, parametros=()) -> int:  # noqa: F811
    return int(casa.um(comando, parametros)["n"])


def _confere_a_regua(html: str, p, esperado: dict, chave_da_regua: str) -> None:
    assert len(p.regua) == 1, f"a ficha devia ter uma régua só, tem {len(p.regua)}"
    assert p.regua[0]["chave"] == chave_da_regua, p.regua[0]["chave"]
    assert p.regua[0]["inicial"] == esperado["inicial"], (
        f"a página abre em «{p.regua[0]['inicial']}», e o módulo manda abrir em «{esperado['inicial']}»")
    marcas = _marcas(html)
    quer = [x["chave"] for x in esperado["fases"] + esperado["apoio"]]
    assert [a["fase"] for a in p.abas] == quer, f"abas da página {[a['fase'] for a in p.abas]}, esperadas {quer}"
    assert not [a["fase"] for a in p.abas if a["travada"]], "nenhuma destas fichas trava aba: o servidor é quem recusa"
    for x in esperado["fases"]:
        assert marcas[x["chave"]]["alerta"] == x["pendencias"], (x["chave"], marcas[x["chave"]], x)
        assert x["estado"] in marcas[x["chave"]]["classes"], (x["chave"], marcas[x["chave"]], x["estado"])
    for x in esperado["apoio"]:
        assert (marcas[x["chave"]]["contagem"], marcas[x["chave"]]["alerta"]) == (x["contagem"], x["alerta"]), (
            f"aba {x['chave']}: a régua desenha {marcas[x['chave']]}, o módulo diz {x}")


def _o_formulario_mora_na_aba(p, action: str, fase: str) -> None:
    """O formulário na aba errada fica escondido de quem abre a ficha na aba certa."""
    achados = [f["fase"] for f in p.formularios if f["action"] == action]
    assert achados, f"a ficha não traz o formulário {action}"
    assert set(achados) == {fase}, f"o formulário {action} está na aba {sorted(set(map(str, achados)))}, e devia estar em «{fase}»"


# ------------------------------------------------------------------ a matrícula (`ri_abas`)

#: O que a semente fez com cada ficha (`fatos`) e o que a ficha promete (o resto): as abas na ordem da régua, a
#: conta e a marca de cada uma, o que espera ação e os formulários. Escrito à mão, da regra, e não tirado do módulo.
MATRICULAS = {
    "estruturada_aberta": {
        "chave": "ri_mat_estruturada_aberta", "fatos": {"atos": 0, "partes": 1, "protocolos": 3, "certidoes": 0},
        "abas": ["resumo", "teor", "partes", "protocolos", "certidoes", "revisar", "novo-ato"],
        "contagem": {"partes": 1, "protocolos": 3}, "alerta": {},
        "espera": [], "lavra": True, "dono": "Mario Exemplo"},
    "estruturada_com_ato": {
        "chave": "ri_mat_estruturada_com_ato", "fatos": {"atos": 2, "partes": 3, "protocolos": 1, "certidoes": 1},
        "abas": ["resumo", "atos", "teor", "partes", "protocolos", "certidoes", "revisar", "novo-ato"],
        "contagem": {"atos": 2, "partes": 3, "protocolos": 1, "certidoes": 1}, "alerta": {},
        "espera": [], "lavra": True, "dono": "Beatriz Exemplo", "ultimos": ["AV-02", "R-01"]},
    "encerrada": {
        "chave": "ri_mat_encerrada", "fatos": {"atos": 1, "encerrada": 1},
        "abas": ["resumo", "atos", "teor", "partes", "certidoes", "revisar", "novo-ato"],
        "contagem": {"atos": 1, "partes": 1}, "alerta": {"atos": 1},
        "espera": ["AV-01 lavrado e sem selo"], "lavra": False, "reabre": True, "sem_selo": ["AV-01"]},
    "com_pendencias": {
        "chave": "ri_mat_com_pendencias", "fatos": {"atos": 0, "minutas": 1, "rascunhos": 1, "revisoes": 1},
        "abas": ["resumo", "teor", "partes", "certidoes", "revisar", "novo-ato"],
        "contagem": {"partes": 1}, "alerta": {"revisar": 1},
        "espera": ["1 ponto(s) a revisar antes de selar", "1 minuta(s) na fila de revisão", "Rascunho de AV guardado"],
        "lavra": True},
    "acervo_aberta": {
        "chave": "ri_mat_acervo_aberta", "fatos": {"atos": 0, "partes": 0, "acervo": 1},
        "abas": ["resumo", "teor", "partes", "certidoes", "revisar", "novo-ato"], "contagem": {}, "alerta": {},
        "espera": [], "lavra": True, "aviso": "Esta ficha não tem atos destacados"},
    "acervo_com_ato_sem_selo": {
        "chave": "ri_mat_acervo_com_ato_sem_selo", "fatos": {"atos": 1, "acervo": 1},
        "abas": ["resumo", "atos", "teor", "partes", "certidoes", "revisar", "novo-ato"],
        "contagem": {"atos": 1}, "alerta": {"atos": 1},
        "espera": ["AV-09 lavrado e sem selo"], "lavra": True, "sem_selo": ["AV-09"],
        "aviso": "Esta ficha não tem atos destacados"},
}


def _ato_do_rotulo(casa, mid: int, rotulo: str) -> int:  # noqa: F811
    tipo, numero = rotulo.split("-")
    return _linhas(casa, "SELECT id FROM ri_atos WHERE matricula_id=%s AND tipo=%s AND numero=%s",
                   (mid, tipo, int(numero)))[0]["id"]


def _confere_a_promessa_da_regua(html: str, p, t: dict) -> None:
    """A régua que o estado promete, escrita à mão: as abas, a conta e a marca. Não passa pelo módulo."""
    assert [a["fase"] for a in p.abas] == t["abas"], f"abas da página {[a['fase'] for a in p.abas]}, o estado promete {t['abas']}"
    marcas = _marcas(html)
    for chave in t["abas"]:
        quer = (t["contagem"].get(chave, 0), t["alerta"].get(chave, 0))
        assert (marcas[chave]["contagem"], marcas[chave]["alerta"]) == quer, (
            f"aba {chave}: a página desenha {marcas[chave]}, o estado promete conta/marca {quer}")


def _fatos_da_matricula(casa, mid: int) -> dict:  # noqa: F811
    return {
        "atos": _n(casa, "SELECT COUNT(*) AS n FROM ri_atos WHERE matricula_id=%s", (mid,)),
        "partes": _n(casa, "SELECT COUNT(*) AS n FROM ri_partes WHERE matricula_id=%s", (mid,)),
        "protocolos": _n(casa, "SELECT COUNT(*) AS n FROM ri_protocolos WHERE matricula_id=%s", (mid,)),
        "certidoes": _n(casa, "SELECT COUNT(*) AS n FROM ri_certidoes WHERE matricula_id=%s", (mid,)),
        "minutas": _n(casa, "SELECT COUNT(*) AS n FROM ri_minutas WHERE matricula_id=%s AND situacao='A_REVISAR'", (mid,)),
        "rascunhos": _n(casa, "SELECT COUNT(*) AS n FROM ri_rascunhos WHERE matricula_id=%s", (mid,)),
        "revisoes": _n(casa, "SELECT COUNT(*) AS n FROM ri_revisoes WHERE matricula_id=%s AND situacao='ABERTA'", (mid,)),
        "encerrada": int(casa.um("SELECT encerrada AS n FROM ri_matriculas WHERE id=%s", (mid,))["n"] or 0),
        "acervo": int(casa.um("SELECT tipo_ficha AS t FROM ri_matriculas WHERE id=%s", (mid,))["t"] == "ACERVO"),
    }


def _esperado_da_matricula(casa, mid: int, foco: str = "") -> dict:  # noqa: F811
    """O que o módulo puro diz da ficha, com os fatos que estão no banco."""
    ficha = dict(casa.um("SELECT * FROM ri_matriculas WHERE id=%s", (mid,)))
    rascunho = casa.um("SELECT tipo FROM ri_rascunhos WHERE matricula_id=%s", (mid,))
    return RA.abas_da_matricula(
        ficha, atos=_linhas(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY numero, tipo", (mid,)),
        partes=_linhas(casa, "SELECT * FROM ri_partes WHERE matricula_id=%s ORDER BY id", (mid,)),
        protocolos=_linhas(casa, "SELECT id FROM ri_protocolos WHERE matricula_id=%s", (mid,)),
        certidoes_emitidas=_n(casa, "SELECT COUNT(*) AS n FROM ri_certidoes WHERE matricula_id=%s", (mid,)),
        revisoes_abertas=_linhas(casa, "SELECT id FROM ri_revisoes WHERE matricula_id=%s AND situacao='ABERTA'", (mid,)),
        minutas=_linhas(casa, "SELECT id FROM ri_minutas WHERE matricula_id=%s AND situacao='A_REVISAR'", (mid,)),
        rascunho=dict(rascunho) if rascunho else None, foco=foco)


@pytest.mark.parametrize("estado", list(MATRICULAS))
def test_a_ficha_da_matricula_cumpre_o_que_o_estado_promete(casa, estado):  # noqa: F811
    t = MATRICULAS[estado]
    mid = _id(casa, t["chave"])
    fatos = _fatos_da_matricula(casa, mid)
    assert {k: fatos[k] for k in t["fatos"]} == t["fatos"], "a semente não deixou a ficha neste estado"

    html, p = _abrir(casa, "ri_ficha", matricula_id=mid)
    esperado = _esperado_da_matricula(casa, mid)
    assert esperado["inicial"] == "resumo", "a ficha abre no resumo"
    _confere_a_regua(html, p, esperado, f"mat-{mid}")
    _confere_a_promessa_da_regua(html, p, t)

    # O que espera ação: a página, o módulo e a promessa dizem a mesma coisa, na mesma ordem.
    assert _espera(html) == [i["texto"] for i in esperado["espera"]] == t["espera"]
    assert ("O que espera ação" in html) == bool(t["espera"]), "o quadro só sai quando há o que fazer"
    if t["espera"]:
        assert html.index("O que espera ação") < html.index("Situação jurídica"), "o que espera ação vem primeiro"
    for rotulo in t.get("sem_selo", []):
        ato = _ato_do_rotulo(casa, mid, rotulo)
        assert p.ids[f"selar-ato-{ato}"] == 1, f"o {rotulo} está sem selo e a ficha não tem onde selá-lo"

    acoes = _acoes(p)
    assert (f"/registro-imoveis/{mid}/atos" in acoes) == t["lavra"], (
        "a ficha " + ("aberta" if t["lavra"] else "encerrada") + " tem de " + ("trazer" if t["lavra"] else "negar")
        + " o formulário de lavrar")
    assert (f"/registro-imoveis/{mid}/reabrir" in acoes) == t.get("reabre", False)
    _o_formulario_mora_na_aba(p, f"/registro-imoveis/{mid}/certidao", "certidoes")
    _o_formulario_mora_na_aba(p, f"/registro-imoveis/{mid}/revisoes", "revisar")
    if t["lavra"]:
        assert p.ids["form-lavrar-ato"] == 1 and p.ids["minutas-para-lavrar"] == 1
        for destino in ("atos", "minuta", "rascunho"):
            _o_formulario_mora_na_aba(p, f"/registro-imoveis/{mid}/{destino}", "novo-ato")
    for rotulo in t.get("sem_selo", []):
        _o_formulario_mora_na_aba(p, f"/registro-imoveis/ato/{_ato_do_rotulo(casa, mid, rotulo)}/selar", "atos")

    if "dono" in t:
        dono = re.search(r"Proprietário hoje:</strong>\s*(.*?)</p>", html, re.S)
        assert dono and t["dono"] in dono.group(1), f"o dono de hoje devia ser {t['dono']}"
        assert "Mario Exemplo" not in dono.group(1) or t["dono"] == "Mario Exemplo", (
            "quem vendeu continua nas partes, mas não é dono hoje")
    if "ultimos" in t:
        resumo = html[html.index("Últimos atos"):]
        achados = re.findall(r"<li><strong>([A-Z]+-\d+)</strong>", resumo)[:len(t["ultimos"])]
        assert achados == t["ultimos"], achados
    if "aviso" in t:
        assert t["aviso"] in html


def test_quem_vem_lavrar_abre_na_aba_novo_ato(casa):  # noqa: F811
    mid = _id(casa, "ri_mat_estruturada_aberta")
    html, p = _abrir(casa, "ri_ficha", {"lavrar": 1}, matricula_id=mid)
    assert p.regua[0]["inicial"] == _esperado_da_matricula(casa, mid, RA.NOVO_ATO)["inicial"] == RA.NOVO_ATO
    assert "novo-ato" in {a["fase"] for a in p.abas}


def test_a_minuta_escolhida_abre_o_formulario_de_lavrar_com_o_texto(casa):  # noqa: F811
    mid = _id(casa, "ri_mat_com_pendencias")
    minuta = _linhas(casa, "SELECT id, teor FROM ri_minutas WHERE matricula_id=%s ORDER BY id", (mid,))[0]
    html, p = _abrir(casa, "ri_ficha", {"minuta": minuta["id"]}, matricula_id=mid)
    assert p.regua[0]["inicial"] == RA.NOVO_ATO, "quem vem revisar a minuta cai onde ela se lavra"
    lavrar = next(f for f in p.formularios if f["action"] == f"/registro-imoveis/{mid}/atos")
    teor = next(c for c in lavrar["campos"] if c["nome"] == "teor")
    assert minuta["teor"] in teor["valor"], "o texto da minuta tem de vir dentro do formulário"
    assert ("minuta_id", str(minuta["id"])) in {(c["nome"], c["valor"]) for c in lavrar["campos"]}


# ------------------------------------------------------------------ a prenotação (`ri_fases_prenotacao`)

#: O que a semente fez com cada prenotação (`fatos`) e o que a ficha promete: a aba em que abre, o estado
#: de cada fase e quais formulários cabem. Em exigência, a nota espera ação: é onde a ficha tem de abrir.
PRENOTACOES = {
    "sem_selo": {
        "chave": "ri_pren_sem_selo", "inicial": "titulo",
        "fatos": {"situacao": "ABERTO", "selo": 0, "ato": 0, "notas_abertas": 0, "documentos": 0},
        "fases": {"titulo": ("liberada", 1), "emolumentos": ("liberada", 0), "qualificacao": ("liberada", 0)},
        "documentos": 0, "notas": 0,
        "selar": True, "encerra": True, "reabre": False},
    "aberta": {
        "chave": "ri_pren_aberta", "inicial": "titulo",
        "fatos": {"situacao": "ABERTO", "selo": 1, "ato": 0, "notas_abertas": 0, "documentos": 0},
        "fases": {"titulo": ("feita", 0), "emolumentos": ("liberada", 0), "qualificacao": ("liberada", 0)},
        "documentos": 0, "notas": 0,
        "selar": False, "encerra": True, "reabre": False},
    "com_documento": {
        "chave": "ri_pren_com_documento", "inicial": "qualificacao",
        "fatos": {"situacao": "ABERTO", "selo": 1, "ato": 0, "notas_abertas": 0, "documentos": 1},
        "fases": {"titulo": ("feita", 0), "emolumentos": ("liberada", 0), "qualificacao": ("liberada", 0)},
        "documentos": 1, "notas": 0,
        "selar": False, "encerra": True, "reabre": False},
    "com_ato": {
        "chave": "ri_pren_com_ato", "inicial": "titulo",
        "fatos": {"situacao": "ABERTO", "selo": 1, "ato": 1, "notas_abertas": 0, "documentos": 0},
        "fases": {"titulo": ("feita", 0), "emolumentos": ("liberada", 0), "qualificacao": ("liberada", 0)},
        "documentos": 0, "notas": 0,
        "selar": False, "encerra": True, "reabre": False},
    "em_exigencia": {
        "chave": "ri_pren_em_exigencia", "inicial": "qualificacao",
        "fatos": {"situacao": "DEVOLVIDO", "selo": 1, "ato": 0, "notas_abertas": 1, "documentos": 0},
        "fases": {"titulo": ("feita", 0), "emolumentos": ("liberada", 0), "qualificacao": ("liberada", 1)},
        "documentos": 0, "notas": 1,
        "selar": False, "encerra": True, "reabre": True, "aviso": "Há nota devolutiva em aberto"},
    "cancelada": {
        "chave": "ri_pren_cancelada", "inicial": "titulo",
        "fatos": {"situacao": "CANCELADO", "selo": 1, "ato": 0, "notas_abertas": 0, "documentos": 0},
        "fases": {"titulo": ("feita", 0), "emolumentos": ("liberada", 0), "qualificacao": ("liberada", 0)},
        "documentos": 0, "notas": 0,
        "selar": False, "encerra": False, "reabre": True},
}


def _fatos_da_prenotacao(casa, pid: int) -> dict:  # noqa: F811
    p = casa.um("SELECT situacao, selo_prenotacao, ato_id FROM ri_protocolos WHERE id=%s", (pid,))
    return {
        "situacao": p["situacao"], "selo": int(bool((p["selo_prenotacao"] or "").strip())), "ato": int(bool(p["ato_id"])),
        "notas_abertas": _n(casa, "SELECT COUNT(*) AS n FROM ri_notas_devolutivas WHERE protocolo_id=%s AND situacao='ABERTA'",
                            (pid,)),
        "documentos": _n(casa, "SELECT COUNT(*) AS n FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=%s",
                         (pid,)),
    }


def _esperado_da_prenotacao(casa, pid: int) -> dict:  # noqa: F811
    """O que o módulo puro diz da ficha, com os fatos que estão no banco."""
    p = dict(casa.um("SELECT * FROM ri_protocolos WHERE id=%s", (pid,)))
    return RF.fases_da_prenotacao(
        p, documentos=_linhas(casa, "SELECT id FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=%s", (pid,)),
        notas=_linhas(casa, "SELECT situacao FROM ri_notas_devolutivas WHERE protocolo_id=%s", (pid,)),
        qualificacoes=_linhas(casa, "SELECT id FROM ri_qualificacoes WHERE protocolo_id=%s", (pid,)),
        historico=_linhas(casa, "SELECT id FROM audit_logs WHERE entity_type='RI_PROTOCOLO' AND entity_id=%s "
                                "ORDER BY id DESC LIMIT 30", (pid,)),
        depositos=_linhas(casa, "SELECT id FROM cx_depositos WHERE ri_protocolo_id=%s", (pid,)),
        tem_onr=bool(_n(casa, "SELECT COUNT(*) AS n FROM onr_at_eventos WHERE protocolo_id=%s", (pid,))))


@pytest.mark.parametrize("estado", list(PRENOTACOES))
def test_a_ficha_da_prenotacao_cumpre_o_que_o_estado_promete(casa, estado):  # noqa: F811
    t = PRENOTACOES[estado]
    pid = _id(casa, t["chave"])
    assert _fatos_da_prenotacao(casa, pid) == t["fatos"], "a semente não deixou a prenotação neste estado"

    html, p = _abrir(casa, "ri_protocolo_ver", protocolo_id=pid)
    esperado = _esperado_da_prenotacao(casa, pid)
    _confere_a_regua(html, p, esperado, f"pren-{pid}")
    assert [f["chave"] for f in esperado["fases"]] == ["titulo", "emolumentos", "qualificacao"]
    for fase in esperado["fases"]:
        assert (fase["estado"], fase["pendencias"]) == t["fases"][fase["chave"]], (
            f"fase {fase['chave']}: o módulo diz {fase['estado']}/{fase['pendencias']}, "
            f"o estado promete {t['fases'][fase['chave']]}")
        assert fase["trava"] is None, "nada trava: o título se confere em qualquer ordem"
    if t.get("aviso"):
        assert t["aviso"] in html
    marcas = _marcas(html)
    assert marcas["documentos"]["contagem"] == t["documentos"], marcas["documentos"]
    assert ("notas" in marcas) == bool(t["notas"]), "a aba Notas só existe com nota devolutiva"
    if t["notas"]:
        assert marcas["notas"]["contagem"] == t["notas"]
    assert "historico" in marcas, "toda prenotação tem o que a auditoria gravou"

    acoes = _acoes(p)
    assert (f"/registro-imoveis/protocolo/{pid}/selar" in acoes) == t["selar"], "só a prenotação sem selo pede para selar"
    assert (("acao", "encerrar") in _botoes(p)) == t["encerra"], "encerrar cabe à aberta e à devolvida"
    assert (("acao", "reabrir") in _botoes(p)) == t["reabre"], "reabrir cabe à que não está aberta"
    _o_formulario_mora_na_aba(p, f"/registro-imoveis/prenotacao/{pid}/documento", "documentos")
    for acao, cabe in (("encerrar", t["encerra"]), ("reabrir", t["reabre"])):
        onde = [f["fase"] for f in p.formularios if any((b["nome"], b["valor"]) == ("acao", acao) for b in f["botoes"])]
        assert onde == (["titulo"] if cabe else []), f"o formulário de {acao} está em {onde}, e devia estar na fase «titulo»"
    assert f"/registro-imoveis/protocolo/{pid}/comprovante" in {x["href"] for x in p.links}


@pytest.mark.parametrize("estado", [
    "sem_selo", "aberta", "com_documento", "com_ato", "em_exigencia", "cancelada"])
def test_a_prenotacao_abre_onde_a_acao_espera(casa, estado):  # noqa: F811
    t = PRENOTACOES[estado]
    html, p = _abrir(casa, "ri_protocolo_ver", protocolo_id=_id(casa, t["chave"]))
    assert p.regua[0]["inicial"] == t["inicial"], (
        f"a ficha {estado} abre em «{p.regua[0]['inicial']}», e a ação espera em «{t['inicial']}»")


# ------------------------------------------------------------------ o usucapião (`usucapiao_abas`)

#: `contagem` é o número que a aba desenha; `andamento` e `relatorio` são as marcas das abas Andamento e Relatório.
PROCESSOS = {
    "autuado": {"chave": "ri_us_autuado", "situacao": "EM_ANDAMENTO", "etapa": "AUTUACAO", "em_curso": True,
                "conferencia_pende": True, "andamento": 0, "relatorio": 0, "registra": False,
                "contagem": {"pecas": 0, "qualificacao": 0, "decisao": 0}},
    "em_curso": {"chave": "ri_us_em_curso", "situacao": "EM_ANDAMENTO", "etapa": "NOTIFICACAO", "em_curso": True,
                 "conferencia_pende": True, "andamento": 1, "relatorio": 1, "registra": False,
                 "contagem": {"pecas": 1, "qualificacao": 1, "decisao": 0}},
    "decidido": {"chave": "ri_us_decidido", "situacao": "EM_ANDAMENTO", "etapa": "DECISAO", "em_curso": True,
                 "conferencia_pende": False, "andamento": 0, "relatorio": 0, "registra": True,
                 "contagem": {"pecas": 0, "qualificacao": 0, "decisao": 1}},
    "registrado": {"chave": "ri_us_registrado", "situacao": "REGISTRADO", "etapa": "REGISTRO", "em_curso": False,
                   "conferencia_pende": False, "andamento": 0, "relatorio": 0, "registra": False,
                   "contagem": {"pecas": 0, "qualificacao": 0, "decisao": 1}},
    # Rejeitado com o checklist inteiro pendente: o processo terminou, e quem terminou não cobra nada.
    "rejeitado": {"chave": "ri_us_rejeitado", "situacao": "REJEITADO", "em_curso": False,
                  "conferencia_pende": False, "andamento": 0, "relatorio": 0, "registra": False,
                  "contagem": {"pecas": 0, "qualificacao": 0, "decisao": 1}},
}
ABAS_DO_USUCAPIAO = ["processo", "conferencia", "pecas", "andamento", "qualificacao", "decisao"]
#: Cada formulário de quem está em curso, e a aba onde ele tem de morar.
FORMULARIO_E_ABA_DO_USUCAPIAO = {"etapa": "processo", "conferencia": "conferencia", "peca": "pecas",
                                 "notificar": "andamento", "movimento": "andamento", "analise": "qualificacao",
                                 "decidir": "decisao"}
FORMULARIOS_DE_QUEM_ESTA_EM_CURSO = tuple(FORMULARIO_E_ABA_DO_USUCAPIAO)


def _esperado_do_processo(casa, pid: int) -> dict:  # noqa: F811
    import usucapiao as US
    p = dict(casa.um("SELECT * FROM us_processos WHERE id=%s", (pid,)))
    with casa.con() as con:
        conferencia = US.conferir(con, pid)
    return UA.abas_do_processo(
        p, conferencia=conferencia, pecas=_linhas(casa, "SELECT id FROM us_pecas WHERE processo_id=%s", (pid,)),
        movimentos=_linhas(casa, "SELECT * FROM us_movimentos WHERE processo_id=%s ORDER BY id", (pid,)),
        analises=_linhas(casa, "SELECT * FROM us_analises WHERE processo_id=%s ORDER BY id", (pid,)),
        decisoes=_linhas(casa, "SELECT id FROM us_decisoes WHERE processo_id=%s", (pid,)), hoje=casa.hoje)


@pytest.mark.parametrize("estado", list(PROCESSOS))
def test_a_ficha_do_usucapiao_cumpre_o_que_o_estado_promete(casa, estado):  # noqa: F811
    t = PROCESSOS[estado]
    pid = _id(casa, t["chave"])
    linha = casa.um("SELECT situacao, etapa FROM us_processos WHERE id=%s", (pid,))
    assert linha["situacao"] == t["situacao"], "a semente não deixou o processo neste estado"
    if "etapa" in t:
        assert linha["etapa"] == t["etapa"]

    html, p = _abrir(casa, "usucapiao_processo", processo_id=pid)
    esperado = _esperado_do_processo(casa, pid)
    assert esperado["inicial"] == "processo"
    _confere_a_regua(html, p, esperado, f"usucapiao-{pid}")
    assert [a["fase"] for a in p.abas] == ABAS_DO_USUCAPIAO

    marcas = _marcas(html)
    assert (marcas["conferencia"]["alerta"] > 0) == t["conferencia_pende"], marcas["conferencia"]
    assert (marcas["andamento"]["alerta"], marcas["qualificacao"]["alerta"]) == (t["andamento"], t["relatorio"]), (
        "prazo vencido e parecer por conferir marcam a aba do processo em curso, e só dele")
    assert {c: marcas[c]["contagem"] for c in t["contagem"]} == t["contagem"]

    acoes = _acoes(p)
    escreve = {a for a in FORMULARIOS_DE_QUEM_ESTA_EM_CURSO if f"/usucapiao/{pid}/{a}" in acoes}
    assert escreve == (set(FORMULARIOS_DE_QUEM_ESTA_EM_CURSO) if t["em_curso"] else set()), (
        f"o processo {t['situacao']} " + ("pede" if t["em_curso"] else "não aceita") + f" os formulários: {sorted(escreve)}")
    assert (f"/usucapiao/{pid}/registrar" in acoes) == t["registra"], "só a decisão procedente sem registro pede o ato"
    if t["em_curso"]:
        for destino, aba in FORMULARIO_E_ABA_DO_USUCAPIAO.items():
            _o_formulario_mora_na_aba(p, f"/usucapiao/{pid}/{destino}", aba)
    if t["registra"]:
        _o_formulario_mora_na_aba(p, f"/usucapiao/{pid}/registrar", "decisao")


# ------------------------------------------------------------------ o registro do Livro 3 (`ra_abas`)

#: Como a das matrículas: o que a semente fez (`fatos`) e o que a ficha promete, escrito à mão.
REGISTROS = {
    "sem_partes_sem_selo": {
        "chave": "ri_l3_sem_partes_sem_selo", "situacao": "ATIVO", "fatos": {"atos": 1, "partes": 0, "minutas": 0},
        "abas": ["resumo", "atos", "teor", "partes", "revisar", "certidoes", "corrigir", "lancar"],
        "contagem": {"atos": 1}, "alerta": {"atos": 1, "partes": 1},
        "espera": ["Este registro não tem partes, e sem elas o selo não sai", "R-1 lavrado e sem selo"], "lanca": True},
    "completo": {
        "chave": "ri_l3_completo", "situacao": "ATIVO", "fatos": {"atos": 2, "partes": 2, "minutas": 0},
        "abas": ["resumo", "atos", "teor", "partes", "revisar", "certidoes", "corrigir", "lancar"],
        "contagem": {"atos": 2, "partes": 2}, "alerta": {},
        "espera": [], "lanca": True},
    "cancelado": {
        "chave": "ri_l3_cancelado", "situacao": "CANCELADO", "fatos": {"atos": 2, "partes": 2, "minutas": 0},
        "abas": ["resumo", "atos", "teor", "partes", "revisar", "certidoes", "corrigir"],
        "contagem": {"atos": 2, "partes": 2}, "alerta": {},
        "espera": [], "lanca": False},
    "com_minuta": {
        "chave": "ri_l3_com_minuta", "situacao": "ATIVO", "fatos": {"atos": 1, "partes": 2, "minutas": 1, "expurgos": 1},
        "abas": ["resumo", "atos", "teor", "partes", "minutas", "revisar", "certidoes", "corrigir", "lancar"],
        "contagem": {"atos": 1, "partes": 2, "minutas": 1}, "alerta": {"minutas": 1, "revisar": 1},
        "espera": ["1 minuta(s) a revisar e lavrar", "1 ponto(s) a revisar antes de selar"], "lanca": True},
}


def _esperado_do_registro(casa, rid: int) -> dict:  # noqa: F811
    import ra_correcoes as CORR
    registro = dict(casa.um("SELECT * FROM ra_registros WHERE id=%s", (rid,)))
    atos = _linhas(casa, "SELECT * FROM ra_atos WHERE registro_id=%s ORDER BY numero", (rid,))
    with casa.con() as con:
        numeracao = CORR.numeracao_dos_atos(con, rid)
    return RAA.abas_do_registro(
        registro, atos=atos, partes=_linhas(casa, "SELECT * FROM ra_partes WHERE registro_id=%s ORDER BY id", (rid,)),
        minutas=_linhas(casa, "SELECT * FROM ra_minutas WHERE registro_id=%s ORDER BY id", (rid,)),
        revisoes=_linhas(casa, "SELECT * FROM ra_revisoes WHERE registro_id=%s ORDER BY id", (rid,)),
        numeracao=numeracao, certidoes=[],
        expurgos=_linhas(casa, "SELECT id FROM ra_expurgos WHERE registro_id=%s", (rid,)), pode_corrigir=True)


@pytest.mark.parametrize("estado", list(REGISTROS))
def test_a_ficha_do_livro3_cumpre_o_que_o_estado_promete(casa, estado):  # noqa: F811
    t = REGISTROS[estado]
    rid = _id(casa, t["chave"])
    assert casa.um("SELECT situacao FROM ra_registros WHERE id=%s", (rid,))["situacao"] == t["situacao"]
    fatos = {"atos": _n(casa, "SELECT COUNT(*) AS n FROM ra_atos WHERE registro_id=%s", (rid,)),
             "partes": _n(casa, "SELECT COUNT(*) AS n FROM ra_partes WHERE registro_id=%s", (rid,)),
             "minutas": _n(casa, "SELECT COUNT(*) AS n FROM ra_minutas WHERE registro_id=%s AND situacao='A_REVISAR'", (rid,)),
             "expurgos": _n(casa, "SELECT COUNT(*) AS n FROM ra_expurgos WHERE registro_id=%s", (rid,))}
    assert {k: fatos[k] for k in t["fatos"]} == t["fatos"], "a semente não deixou o registro neste estado"

    html, p = _abrir(casa, "livro3_registro", registro_id=rid)
    esperado = _esperado_do_registro(casa, rid)
    assert esperado["inicial"] == "resumo"
    _confere_a_regua(html, p, esperado, f"livro3-{rid}")
    _confere_a_promessa_da_regua(html, p, t)
    assert _espera(html) == [i["texto"] for i in esperado["espera"]] == t["espera"]
    assert ("O que espera ação" in html) == bool(t["espera"]), "o quadro só sai quando há o que fazer"

    assert (f"/livro3/{rid}/lancar" in _acoes(p)) == t["lanca"]
    if t["lanca"]:
        _o_formulario_mora_na_aba(p, f"/livro3/{rid}/lancar", "lancar")
    _o_formulario_mora_na_aba(p, f"/livro3/{rid}/partes", "partes")
    _o_formulario_mora_na_aba(p, f"/livro3/{rid}/revisoes", "revisar")


# ------------------------------------------------------------------ o que a semente anotou, aberto de verdade

#: `test_layout_semente` só recusa 404 e 500. Passam por ele o redirecionamento, a recusa, o recado de erro
#: e o arquivo que sai vazio ou que sai como página: a varredura veria uma tela que não é a ficha.
ARQUIVOS_PELO_NOME = (".odt", ".pdf", ".csv", ".json")


def test_toda_tela_semeada_abre_de_verdade(casa):  # noqa: F811
    ruins, vistas = [], set()
    for endpoint, endereco in casa.paginas:
        if area_da_regra(endereco) != "ri":
            continue
        vistas.add(endpoint)
        r = casa.cliente("ADMIN", "novo").get(endereco)
        if r.mimetype == "text/event-stream":
            continue
        corpo = r.get_data()
        if r.status_code != 200:
            ruins.append(f"{endereco} ({endpoint}): HTTP {r.status_code} {r.headers.get('Location', '')}")
        elif not corpo:
            ruins.append(f"{endereco} ({endpoint}): resposta vazia")
        elif r.mimetype == "text/html":
            recados = [t for c, t in E.ler_pagina(corpo.decode("utf-8")).flashes if c == "danger"]
            if recados:
                ruins.append(f"{endereco} ({endpoint}): abre com recado de erro: {recados}")
            if endereco.split("?")[0].endswith(ARQUIVOS_PELO_NOME):
                ruins.append(f"{endereco} ({endpoint}): devia ser arquivo e veio página")
    assert not ruins, "a semente anotou o que não abre como devia:\n  " + "\n  ".join(ruins)
    assert len(vistas) >= 45, f"a semente do ri anotou só {len(vistas)} rotas: o conferidor deixou de olhar (medido: 47)"

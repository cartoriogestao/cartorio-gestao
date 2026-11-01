"""As fichas do Registro Civil, estado por estado, com o sistema de pé.

O QUE DEFENDEM
    A ficha do assento (`rc_abas`) e a da habilitação de casamento (`habilitacao_fases`) abrem no
    layout novo e cumprem o que o estado do registro promete: as abas ou fases que existem, as
    travadas e para onde levam, o que espera ação e o botão que leva até lá, e o formulário que tem de
    estar na fase certa. A conta das duas já tem teste (`test_rc_abas`, `test_habilitacao_fases`);
    aqui se confere que a TELA a desenha, registro por registro da casa de ensaio.

TRÊS CONTAS, E NÃO UMA
    Primeiro, que a semente deixou o registro no estado que diz (`fatos`, lidos do banco). Depois,
    que a página diz o que o módulo puro calcula com esses fatos. E que o módulo diz o que o estado
    promete, escrito à mão da regra: só a segunda conta passa quando é o próprio módulo que está
    errado, e por isso cada tabela traz a promessa.

O QUE NÃO REPETEM
    Régua única, fase inicial que existe, aba sem quadro, quadro sem porta, âncora sem destino e
    formulário sem token são guardas de toda página, e moram em `layout_ensaio.conferir_pagina`.

`CG_LAYOUT_AREAS=civil` semeia só esta área, e é como se roda.
"""
from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict

import pytest

import habilitacao as HAB
import habilitacao_fases as HF
import hc_schema as HCS
import layout_ensaio as E
import rc_abas as RA
import rc_certidao as RCE
import rc_cpf as CPFRC
import rc_digitalizacao as RCDIGI
import rc_paternidade as RP
from bd_nativo import banco
from layout_casa import areas_pedidas, casa  # noqa: F401

pytestmark = pytest.mark.lento

if "civil" not in areas_pedidas():
    pytest.skip("o civil não foi semeado nesta rodada (CG_LAYOUT_AREAS)", allow_module_level=True)

#: O que espera ação, e o endereço que o botão dele tem de levar.
TERMO = ("Termo assinado ainda não digitalizado", "termo-digitalizado")
PATERNIDADE = ("Termo de alegação de paternidade ainda não remetido ao juiz", "paternidade")
REGISTRO_SEM_SELO = ("Registro lavrado e sem selo", r"selar-registro-\d+")
AVERBACAO_SEM_SELO = ("Averbação lavrada e sem selo", r"selar-averbacao-\d+")
AMARRAR = ("Falta amarrar este assento na habilitação", "habilitacao-do-assento")

NUCLEO = ("assento", "filiacao", "certidoes", "termo")


def _abrir(casa, endereco: str):  # noqa: F811
    r = casa.cliente("ADMIN", "novo").get(endereco)
    assert r.status_code == 200, f"{endereco}: HTTP {r.status_code} {r.headers.get('Location', '')}"
    html = r.get_data(as_text=True)
    return html, E.ler_pagina(html)


def _acao(formulario: dict) -> str | None:
    return next((c["valor"] for c in formulario["campos"] if c["nome"] == "acao"), None)


def _o_formulario_mora_na_fase(p, action: str, fase: str) -> None:
    """O formulário na fase errada fica escondido de quem abre a ficha na fase certa."""
    achados = [f["fase"] for f in p.formularios if f["action"] and re.fullmatch(action, f["action"])]
    assert achados, f"a ficha não traz o formulário {action}"
    assert set(achados) == {fase}, f"o formulário {action} está em {sorted(set(map(str, achados)))}, e devia estar em «{fase}»"


def _n(casa, comando: str, parametros=()) -> int:  # noqa: F811
    return int(casa.um(comando, parametros)["n"])


# ---------------------------------------------------------------------------- a ficha do assento

#: estado -> o que a semente fez (`fatos`) e o que a ficha promete: as abas na ordem da régua; o que
#: espera ação, na ordem do quadro; a conta (`contagem`) e a marca de pendência (`alerta`) das abas
#: que as têm; e os formulários que têm de estar na aba, como (aba, endereço que ele manda).
ASSENTOS = {
    "nascimento_sem": dict(
        fatos=dict(averbacoes=0, anotacoes=0, retificacoes=0, certidoes=0, sem_selo=0, digitalizado=1, cpf=1),
        abas=NUCLEO, espera=[], contagem={"certidoes": 0}),
    "nascimento_averbacao": dict(
        fatos=dict(averbacoes=1, anotacoes=0, retificacoes=0, certidoes=0, sem_selo=0, digitalizado=0, cpf=1),
        abas=("assento", "filiacao", "averbacoes", "certidoes", "termo"), espera=[TERMO],
        contagem={"averbacoes": 1}, alerta={"termo": 1, "averbacoes": 0}),
    # Anotação e retificação no mesmo assento: cada aba depende só do bloco dela.
    "nascimento_anotacao": dict(
        fatos=dict(averbacoes=0, anotacoes=1, retificacoes=1, certidoes=0, sem_selo=0, digitalizado=0, cpf=1),
        abas=("assento", "filiacao", "anotacoes", "retificacoes", "certidoes", "termo"), espera=[TERMO],
        contagem={"anotacoes": 1, "retificacoes": 1}, alerta={"termo": 1}),
    # O CPF por averbar abre a aba das averbações sem averbação nenhuma, e o pai ignorado abre a dos
    # documentos: é o termo de paternidade que mora lá.
    "nascimento_pai_ignorado": dict(
        fatos=dict(averbacoes=0, certidoes=0, sem_selo=0, digitalizado=0, cpf=0),
        abas=("assento", "filiacao", "averbacoes", "certidoes", "termo", "documentos"),
        espera=[PATERNIDADE, TERMO], contagem={"averbacoes": 0}, alerta={"documentos": 1, "termo": 1},
        formularios=[("averbacoes", r"/rcpn/{id}/averbar-cpf"),
                     ("documentos", r"/rcpn/{id}/paternidade/remessa")]),
    "nascimento_sem_selo": dict(
        fatos=dict(averbacoes=1, certidoes=0, sem_selo=2, digitalizado=0, cpf=0),
        abas=("assento", "filiacao", "averbacoes", "certidoes", "termo"),
        espera=[REGISTRO_SEM_SELO, AVERBACAO_SEM_SELO, TERMO],
        contagem={"averbacoes": 1}, alerta={"averbacoes": 1, "termo": 1},
        formularios=[("assento", r"/rcpn/ato/\d+/selar"),
                     ("averbacoes", r"/rcpn/averbacao/\d+/selar-novamente")]),
    "obito_sem": dict(
        fatos=dict(averbacoes=0, anotacoes=0, certidoes=0, sem_selo=0, digitalizado=1, cpf=1),
        abas=NUCLEO, espera=[]),
    "obito_averbacao": dict(
        fatos=dict(averbacoes=1, anotacoes=0, certidoes=0, sem_selo=0, digitalizado=0, cpf=1),
        abas=("assento", "filiacao", "averbacoes", "certidoes", "termo"), espera=[TERMO],
        contagem={"averbacoes": 1}),
    "obito_anotacao": dict(
        fatos=dict(averbacoes=0, anotacoes=1, certidoes=0, sem_selo=0, digitalizado=0, cpf=1),
        abas=("assento", "filiacao", "anotacoes", "certidoes", "termo"), espera=[TERMO],
        contagem={"anotacoes": 1}),
    "casamento_sem": dict(
        fatos=dict(averbacoes=0, anotacoes=0, certidoes=0, sem_selo=0, digitalizado=1),
        abas=NUCLEO, espera=[]),
    "casamento_averbacao": dict(
        fatos=dict(averbacoes=1, anotacoes=0, certidoes=0, sem_selo=0, digitalizado=0),
        abas=("assento", "filiacao", "averbacoes", "certidoes", "termo"), espera=[TERMO],
        contagem={"averbacoes": 1}),
    "casamento_anotacao": dict(
        fatos=dict(averbacoes=0, anotacoes=1, certidoes=0, sem_selo=0, digitalizado=0),
        abas=("assento", "filiacao", "anotacoes", "certidoes", "termo"), espera=[TERMO],
        contagem={"anotacoes": 1}),
    "casamento_certidao": dict(
        fatos=dict(averbacoes=0, certidoes=1, digitalizado=0),
        abas=NUCLEO, espera=[TERMO], contagem={"certidoes": 1}),
    # O casamento lavrado pela habilitação desta casa espera ser amarrado a ela; amarrado, não espera.
    "casamento_falta_amarrar": dict(
        fatos=dict(certidoes=0, digitalizado=0, habilitada=1),
        abas=NUCLEO, espera=[TERMO, AMARRAR]),
    "casamento_celebrado": dict(
        fatos=dict(certidoes=0, digitalizado=0, habilitada=1),
        abas=NUCLEO, espera=[TERMO]),
}

#: A base traz o nascimento e o óbito com certidão, lavrados como o sandbox os lavra: as abas que eles
#: têm além do núcleo dependem do que a carga gravou, e só o núcleo e a certidão se exigem deles.
DA_BASE = ("nascimento_certidao", "obito_certidao")


def _fatos_do_assento(casa, assento_id: int) -> dict:  # noqa: F811
    a = casa.um("SELECT cpf_registrado, digi_path, dados_json FROM rc_assentos WHERE id=%s", (assento_id,))
    por_tipo = lambda tipo: _n(casa, "SELECT COUNT(*) AS n FROM rc_atos WHERE assento_id=%s AND tipo=%s",  # noqa: E731
                               (assento_id, tipo))
    return {
        "averbacoes": por_tipo("AVERBACAO"), "anotacoes": por_tipo("ANOTACAO"),
        "retificacoes": por_tipo("RETIFICACAO"),
        "certidoes": _n(casa, "SELECT COUNT(*) AS n FROM rc_certidoes WHERE assento_id=%s", (assento_id,)),
        "sem_selo": _n(casa, "SELECT COUNT(*) AS n FROM rc_atos WHERE assento_id=%s AND COALESCE(selo,'')=''",
                       (assento_id,)),
        "digitalizado": int(bool(a["digi_path"])), "cpf": int(bool((a["cpf_registrado"] or "").strip())),
        "habilitada": int(bool(json.loads(a["dados_json"] or "{}").get("habilitacao_id"))),
    }


def _esperado_do_assento(casa, assento_id: int) -> dict:  # noqa: F811
    """O que o módulo puro diz da ficha, com os fatos que estão no banco."""
    with casa.con() as con:
        bd = banco(con)
        assento = dict(bd.um("SELECT * FROM rc_assentos WHERE id=%s", (assento_id,)))
        atos = [dict(a) for a in bd.ler("SELECT * FROM rc_atos WHERE assento_id=%s ORDER BY id", (assento_id,))]
        pessoas = RCE.pessoas(con, assento_id)
        vinculo = HAB.habilitacao_relacionada_ao_assento(con, assento_id)
        paternidade = RP.do_assento(con, assento_id)
        digi = RCDIGI.situacao(con, assento_id)
        certidoes = RCE.do_assento(con, assento_id)
    return RA.abas_do_assento(
        assento, blocos={t: [a for a in atos if a["tipo"] == t]
                         for t in ("REGISTRO", "AVERBACAO", "ANOTACAO", "RETIFICACAO")},
        pessoas=pessoas, certidoes=certidoes,
        cpf_pendentes=CPFRC.quem_falta_cpf(pessoas, assento["especie"], cpf_registrado=assento["cpf_registrado"]),
        anexos=[dict(x) for x in casa.db.get_attachments("rc_assento", assento_id)],
        paternidade=paternidade, habilitacao=dict(vinculo) if vinculo else None, digi=digi)


def _numeros_da_regua(html: str) -> dict[str, tuple[int, int]]:
    """Por aba: o número que ela mostra e o da marca de pendência."""
    saida = {}
    for m in re.finditer(r'<a class="cg-fase apoio[^"]*" href="#(\w+)" data-cg-fase="\1">(.*?)</a>',
                         html, re.S):
        contagem = re.search(r'class="cg-fase-q">(\d+)<', m.group(2))
        alerta = re.search(r'class="cg-fase-c"[^>]*>(\d+)<', m.group(2))
        saida[m.group(1)] = (int(contagem.group(1)) if contagem else 0, int(alerta.group(1)) if alerta else 0)
    return saida


def _quadro_do_que_espera(html: str) -> list[tuple[str, str]]:
    """Cada item de «O que espera ação»: o texto e o endereço do botão."""
    quadro = re.search(r'<section class="panel cg-falta" data-fase="assento">(.*?)</section>', html, re.S)
    if not quadro:
        return []
    return [(re.sub(r"\s+", " ", t).strip(), ir) for t, ir in re.findall(
        r'<li class="pendente">.*?<span>(.*?)</span>\s*<a class="button small" href="#([^"]+)"',
        quadro.group(1), re.S)]


@pytest.mark.parametrize("estado", sorted(ASSENTOS))
def test_a_ficha_do_assento_cumpre_o_que_o_estado_promete(casa, estado):  # noqa: F811
    t = ASSENTOS[estado]
    assento_id = casa.ids[f"civil_{estado}"]
    fatos = _fatos_do_assento(casa, assento_id)
    assert {k: fatos[k] for k in t["fatos"]} == t["fatos"], "a semente não deixou o assento neste estado"

    html, p = _abrir(casa, f"/rcpn/{assento_id}")
    esperado = _esperado_do_assento(casa, assento_id)
    abas = [a["fase"] for a in p.abas]
    numeros = _numeros_da_regua(html)
    itens = _quadro_do_que_espera(html)

    # A página diz o que o módulo calcula com os fatos do banco.
    assert esperado["inicial"] == p.regua[0]["inicial"] == "assento", "a ficha do assento abre no assento"
    assert abas == [x["chave"] for x in esperado["apoio"]], f"as abas da página e as do módulo ({estado})"
    for x in esperado["apoio"]:
        assert numeros[x["chave"]] == (x["contagem"], x["alerta"]), f"a aba {x['chave']}: página, módulo {x}"
    assert [texto for texto, _ in itens] == [i["texto"] for i in esperado["espera"]]
    assert [ir for _, ir in itens] == [i["ir"] for i in esperado["espera"]]

    # E o módulo diz o que o estado promete.
    assert tuple(abas) == t["abas"], f"as abas de {estado}"
    assert not [a["fase"] for a in p.abas if a["travada"]], "assento lavrado não tem fase travada"
    for aba, n in t.get("contagem", {}).items():
        assert numeros[aba][0] == n, f"a aba {aba} deve contar {n}"
    for aba, n in t.get("alerta", {}).items():
        assert numeros[aba][1] == n, f"a aba {aba} deve marcar {n} pendência(s)"
    assert len(itens) == len(t["espera"]), f"o que espera ação em {estado}: {itens}"
    for (texto, ir), (trecho, ancora) in zip(itens, t["espera"]):
        assert trecho in texto, f"o que espera ação em {estado}: {texto!r}"
        assert re.fullmatch(ancora, ir), f"o botão de «{trecho}» deve levar a {ancora}, e leva a {ir}"
        assert ir in p.ids, f"o botão de «{trecho}» leva a #{ir}, que não existe na ficha"
    assert ("O que espera ação" in html) == bool(t["espera"]), "o quadro só sai quando há o que fazer"

    _o_formulario_mora_na_fase(p, rf"/rcpn/{assento_id}/certidao", "certidoes")
    _o_formulario_mora_na_fase(p, rf"/rcpn/{assento_id}/digitalizacao", "termo")
    for aba, endereco in t.get("formularios", []):
        _o_formulario_mora_na_fase(p, endereco.format(id=assento_id), aba)
    links = {link["href"] for link in p.links}
    for lancar in ("averbar", "anotar", "retificar"):
        assert f"/rcpn/{assento_id}/{lancar}" in links, f"falta o atalho para {lancar}"


def test_a_tabela_mostra_cada_aba_da_ficha_do_assento():
    """Aba que nenhum estado da tabela mostra é aba que ninguém confere."""
    todas = {RA.ASSENTO, RA.FILIACAO, RA.AVERBACOES, RA.ANOTACOES, RA.RETIFICACOES, RA.CERTIDOES, RA.TERMO,
             RA.DOCUMENTOS}
    vistas = {aba for t in ASSENTOS.values() for aba in t["abas"]}
    assert vistas == todas, f"aba sem estado na tabela: {sorted(todas - vistas)}"
    assert {estado.split("_")[0] for estado in ASSENTOS} == {"nascimento", "obito", "casamento"}


@pytest.mark.parametrize("estado", DA_BASE)
def test_o_assento_da_base_traz_a_certidao_e_nao_cobra_nada(casa, estado):  # noqa: F811
    assento_id = casa.ids[f"civil_{estado}"]
    html, p = _abrir(casa, f"/rcpn/{assento_id}")
    esperado = _esperado_do_assento(casa, assento_id)
    abas = [a["fase"] for a in p.abas]
    assert abas == [x["chave"] for x in esperado["apoio"]]
    assert [a for a in abas if a in NUCLEO] == list(NUCLEO)
    assert _numeros_da_regua(html)["certidoes"][0] >= 1, "a certidão da base não aparece na aba"
    assert _quadro_do_que_espera(html) == [] == esperado["espera"], "o assento da base não tem o que esperar"


# ---------------------------------------------------------------------------- a ficha da habilitação

#: estado -> o que a semente fez (`fatos`) e o que a ficha promete: a fase em que abre, o estado e a
#: marca de cada fase, para onde leva cada trava, o que a barra de cada fase diz, os formulários que
#: têm de estar (fase, ação) e os que NÃO podem (`sem`).
FASES = ("habilitacao", "edital", "prontas", "registro")


def _f(*estados: str) -> dict[str, str]:
    return dict(zip(FASES, estados))


HABILITACOES = {
    "sem_documentos": dict(
        fatos=dict(situacao="EM_ANALISE", tipo="CIVIL", edital=0, central=0, selo=0, vencida=0),
        inicial="habilitacao", fases=_f("liberada", "liberada", "travada", "travada"),
        travas={"prontas": "edital", "registro": "edital"},
        aviso={"habilitacao": "documento(s): sem eles, o edital não sai"},
        formularios=[("habilitacao", "documento"), ("habilitacao", "dispensar"), ("edital", "edital"),
                     ("edital", "oposicao"), ("andamento", "arquivar")],
        sem=["habilitar", "celebrado", "eproclamas", "decidir"]),
    "documentos_ok": dict(
        fatos=dict(situacao="EM_ANALISE", tipo="CIVIL", edital=0, falta=0),
        inicial="edital", fases=_f("feita", "liberada", "travada", "travada"),
        pendencias={"habilitacao": 0, "edital": 1},
        travas={"prontas": "edital", "registro": "edital"},
        formularios=[("edital", "edital"), ("edital", "oposicao")],
        sem=["habilitar", "celebrado", "dispensar"]),
    "conversao_sem_uniao": dict(
        fatos=dict(situacao="EM_ANALISE", tipo="CONVERSAO", falta=0),
        inicial="habilitacao", fases=_f("liberada", "liberada", "travada", "travada"),
        pendencias={"habilitacao": 1},
        travas={"prontas": "edital", "registro": "edital"},
        aviso={"habilitacao": "Falta dizer que união estável se converte"},
        formularios=[("habilitacao", "uniao_estavel"), ("edital", "edital")],
        sem=["habilitar", "celebrado"]),
    "edital_sem_central": dict(
        fatos=dict(situacao="EDITAL_PUBLICADO", edital=1, central=0, falta=0),
        inicial="edital", fases=_f("feita", "liberada", "liberada", "travada"),
        pendencias={"edital": 1, "prontas": 1},
        travas={"registro": "prontas"},
        aviso={"edital": "falta publicar na Central"},
        formularios=[("edital", "eproclamas"), ("edital", "oposicao"), ("prontas", "habilitar")],
        sem=["celebrado", "edital"]),
    "edital_na_central": dict(
        fatos=dict(situacao="EDITAL_PUBLICADO", edital=1, central=1, falta=0),
        inicial="prontas", fases=_f("feita", "feita", "liberada", "travada"),
        pendencias={"prontas": 1}, travas={"registro": "prontas"},
        formularios=[("prontas", "habilitar"), ("edital", "oposicao")],
        sem=["eproclamas", "celebrado"]),
    "edital_falta_papel": dict(
        fatos=dict(situacao="EDITAL_PUBLICADO", edital=1, central=1, falta=1),
        inicial="habilitacao", fases=_f("liberada", "feita", "liberada", "travada"),
        pendencias={"habilitacao": 1, "prontas": 0}, travas={"registro": "prontas"},
        aviso={"prontas": "resolva o que falta em Habilitação"},
        formularios=[("habilitacao", "documento"), ("prontas", "habilitar")], sem=["celebrado"]),
    "com_oposicao": dict(
        fatos=dict(situacao="COM_OPOSICAO", edital=1, falta=0),
        inicial="edital", fases=_f("feita", "liberada", "travada", "travada"),
        pendencias={"edital": 1}, travas={"prontas": "edital", "registro": "edital"},
        aviso={"edital": "Há impedimento a decidir"},
        formularios=[("edital", "decidir")], sem=["habilitar", "celebrado", "oposicao"]),
    "habilitado_sem_selo": dict(
        fatos=dict(situacao="HABILITADO", edital=1, central=1, selo=0, vencida=0),
        inicial="prontas", fases=_f("feita", "feita", "liberada", "liberada"),
        pendencias={"prontas": 1, "registro": 1},
        aviso={"prontas": "Falta o selo", "registro": "Lavre o assento"},
        formularios=[("registro", "celebrado")], selar=True, sem=["habilitar", "edital"]),
    "habilitado_com_selo": dict(
        fatos=dict(situacao="HABILITADO", edital=1, central=1, selo=1, vencida=0),
        inicial="registro", fases=_f("feita", "feita", "feita", "liberada"),
        pendencias={"prontas": 0, "registro": 1},
        aviso={"registro": "Lavre o assento"},
        formularios=[("registro", "celebrado")], sem=["habilitar", "edital"]),
    "vencida": dict(
        fatos=dict(situacao="HABILITADO", selo=1, vencida=1),
        inicial="prontas", fases=_f("feita", "feita", "liberada", "travada"),
        pendencias={"prontas": 1}, travas={"registro": "prontas"},
        aviso={"prontas": "A habilitação venceu"}, sem=["celebrado", "habilitar"]),
    "casamento_lavrado": dict(
        fatos=dict(situacao="HABILITADO", selo=1, vencida=0, casamentos=1),
        inicial="registro", fases=_f("feita", "feita", "feita", "liberada"),
        pendencias={"registro": 1}, formularios=[("registro", "celebrado")], com_casamento=True,
        sem=["habilitar"]),
    "celebrado": dict(
        fatos=dict(situacao="CELEBRADO", selo=1, casamentos=1),
        inicial="registro", fases=_f("feita", "feita", "feita", "feita"),
        pendencias={"habilitacao": 0, "edital": 0, "prontas": 0, "registro": 0},
        sem=["habilitar", "celebrado", "edital", "oposicao"]),
    "celebrado_sem_selo": dict(
        fatos=dict(situacao="CELEBRADO", selo=0, casamentos=1),
        inicial="prontas", fases=_f("feita", "feita", "liberada", "feita"),
        pendencias={"prontas": 1, "registro": 0}, aviso={"prontas": "Falta o selo"},
        selar=True, sem=["habilitar", "celebrado", "edital", "oposicao"]),
    "arquivado_sem_edital": dict(
        fatos=dict(situacao="ARQUIVADO", edital=0),
        inicial="habilitacao", fases=_f("liberada", "travada", "travada", "travada"),
        pendencias={"habilitacao": 0}, travas={"edital": "andamento", "prontas": "andamento",
                                              "registro": "andamento"},
        sem=["habilitar", "celebrado", "edital", "arquivar"]),
    "arquivado_com_edital": dict(
        fatos=dict(situacao="ARQUIVADO", edital=1, oposicao=1),
        inicial="habilitacao", fases=_f("feita", "liberada", "travada", "travada"),
        pendencias={"edital": 0}, travas={"prontas": "andamento", "registro": "andamento"},
        sem=["habilitar", "celebrado", "decidir", "arquivar"]),
}


def test_a_tabela_cobre_cada_situacao_e_cada_estado_de_fase_da_habilitacao():
    """Estado que o módulo sabe produzir e nenhuma linha da tabela traz é ficha que ninguém conferiu."""
    assert {t["fatos"]["situacao"] for t in HABILITACOES.values()} == set(HCS.SITUACOES), (
        "situação do processo sem linha na tabela")
    possiveis = set()
    for situacao, tipo, publicado, na_central, com_selo, oposta, vencida, faltam, uniao in itertools.product(
            HCS.SITUACOES, ("CIVIL", "CONVERSAO"), *[(False, True)] * 5, (0, 1), ("", "processo 1")):
        h = {"situacao": situacao, "tipo": tipo, "edital_em": "2026-01-01" if publicado else None,
             "eproclamas_protocolo": "1" if na_central else None, "selo": "SELO" if com_selo else None,
             "oposicao_em": "2026-01-02" if oposta else None}
        for fase in HF.fases_da_habilitacao(h, falta=[0] * faltam, vencida=vencida, uniao_estavel=uniao)["fases"]:
            possiveis.add((fase["chave"], fase["estado"]))
    mostradas = {(fase, estado) for t in HABILITACOES.values() for fase, estado in t["fases"].items()}
    assert possiveis <= mostradas, (
        f"estado de fase que nenhuma habilitação da tabela mostra: {sorted(possiveis - mostradas)}")


def _fatos_da_habilitacao(casa, habilitacao_id: int) -> dict:  # noqa: F811
    h = casa.um("SELECT * FROM hc_habilitacoes WHERE id=%s", (habilitacao_id,))
    return {
        "situacao": h["situacao"], "tipo": h["tipo"], "edital": int(bool(h["edital_em"])),
        "central": int(bool((h["eproclamas_protocolo"] or "").strip())),
        "selo": int(bool((h["selo"] or "").strip())),
        "vencida": int(HAB.habilitacao_vencida(dict(h), casa.hoje)),
        "oposicao": int(bool(h["oposicao_em"])),
        "falta": _n(casa, "SELECT COUNT(*) AS n FROM hc_documentos WHERE habilitacao_id=%s "
                          "AND apresentado=0 AND dispensado=0", (habilitacao_id,)),
        "casamentos": len(_casamentos_da(casa, habilitacao_id)),
    }


def _casamentos_da(casa, habilitacao_id: int) -> list:  # noqa: F811
    with casa.con() as con:
        return HAB.casamentos_da_habilitacao(con, habilitacao_id)


def _esperado_da_habilitacao(casa, habilitacao_id: int) -> dict:  # noqa: F811
    """O que o módulo puro diz da ficha, com os fatos que estão no banco."""
    with casa.con() as con:
        h = dict(banco(con).um("SELECT * FROM hc_habilitacoes WHERE id=%s", (habilitacao_id,)))
        falta, andamento = HAB.o_que_falta(con, habilitacao_id), HAB.andamento_de(con, habilitacao_id)
    return HF.fases_da_habilitacao(h, falta=falta, andamento=andamento,
                                   vencida=HAB.habilitacao_vencida(h, casa.hoje),
                                   uniao_estavel=h.get("uniao_estavel_processo"))


def _regua_da_habilitacao(html: str, p) -> dict:
    estados = {a["fase"]: estado for a in p.abas for estado in ("feita", "liberada", "travada")
               if estado in a["classes"]}
    pendencias = {}
    for m in re.finditer(r'<a class="cg-fase (?:feita|liberada|travada)" href="#(\w+)"[^>]*>(.*?)</a>',
                         html, re.S):
        n = re.search(r'class="cg-fase-c"[^>]*>(\d+)<', m.group(2))
        pendencias[m.group(1)] = int(n.group(1)) if n else 0
    return {"estados": estados, "pendencias": pendencias}


def _travas(html: str) -> dict[str, str]:
    return {fase: ir for fase, ir in re.findall(
        r'<section class="panel cg-trava" data-fase="(\w+)" data-cg-so-trava hidden>.*?'
        r'<a class="button primary" href="#(\w+)">', html, re.S)}


def _avisos(html: str) -> dict[str, str]:
    return {fase: re.sub(r"\s+", " ", texto).strip() for fase, texto in re.findall(
        r'<div class="cg-acao" data-fase="(\w+)" data-cg-barra hidden>\s*'
        r'<span class="cg-acao-aviso[^"]*">(.*?)</span>', html, re.S)}


@pytest.mark.parametrize("estado", sorted(HABILITACOES))
def test_a_ficha_da_habilitacao_cumpre_o_que_o_estado_promete(casa, estado):  # noqa: F811
    t = HABILITACOES[estado]
    habilitacao_id = casa.ids[f"civil_hab_{estado}"]
    fatos = _fatos_da_habilitacao(casa, habilitacao_id)
    assert {k: fatos[k] for k in t["fatos"]} == t["fatos"], "a semente não deixou a habilitação neste estado"

    html, p = _abrir(casa, f"/rcpn/habilitacoes/{habilitacao_id}")
    esperado = _esperado_da_habilitacao(casa, habilitacao_id)
    regua = _regua_da_habilitacao(html, p)
    travas, avisos = _travas(html), _avisos(html)

    # A página diz o que o módulo calcula com os fatos do banco.
    assert p.regua[0]["inicial"] == esperado["inicial"], "a fase em que a ficha abre"
    assert regua["estados"] == {x["chave"]: x["estado"] for x in esperado["fases"]}
    assert regua["pendencias"] == {x["chave"]: x["pendencias"] for x in esperado["fases"]}
    assert travas == {x["chave"]: x["trava"]["ir"] for x in esperado["fases"] if x["trava"]}
    assert avisos == {x["chave"]: x["aviso"] for x in esperado["fases"]}
    assert [(a["fase"], a["travada"]) for a in p.abas] == (
        [(x["chave"], x["estado"] == HF.TRAVADA) for x in esperado["fases"]]
        + [(x["chave"], False) for x in esperado["apoio"]])

    # E o módulo diz o que o estado promete.
    assert p.regua[0]["inicial"] == t["inicial"], f"a fase em que {estado} abre"
    assert regua["estados"] == t["fases"], f"as fases de {estado}"
    assert t["fases"][t["inicial"]] != "travada", "a ficha não pode abrir numa fase travada"
    for fase, n in t.get("pendencias", {}).items():
        assert regua["pendencias"].get(fase, 0) == n, f"as pendências da fase {fase}"
    if estado == "sem_documentos":
        assert fatos["falta"] > 0 and regua["pendencias"]["habilitacao"] == fatos["falta"], (
            "a régua conta os documentos por apresentar")
    assert travas == t.get("travas", {}), f"as travas de {estado}"
    travadas = {f for f, e in t["fases"].items() if e == "travada"}
    assert {f["fase"] for f in p.fases if f["so_trava"]} == travadas, "cada fase travada tem o seu bloco"
    for fase, trecho in t.get("aviso", {}).items():
        assert trecho in avisos.get(fase, ""), f"o aviso da fase {fase}: {avisos.get(fase)!r}"

    presentes = defaultdict(list)
    for f in p.formularios:
        if f["fase"] and _acao(f):
            presentes[f["fase"]].append(_acao(f))
    assert set(presentes) <= {*FASES, "andamento"}, f"formulário numa fase que a régua não tem: {set(presentes)}"
    for fase, acao in t.get("formularios", []):
        assert acao in presentes[fase], f"falta, na fase {fase}, o formulário «{acao}»"
    todas = {a for lista in presentes.values() for a in lista}
    assert not (todas & set(t.get("sem", []))), (
        f"formulário que {estado} não pode oferecer: {todas & set(t.get('sem', []))}")
    selar = [f for f in p.formularios if f["action"] == f"/rcpn/habilitacoes/{habilitacao_id}/selar"]
    assert bool(selar) == bool(t.get("selar")), "o botão de pedir o selo só existe para a habilitação expedida sem selo"
    if selar:
        assert {f["fase"] for f in selar} == {"prontas"}, "o pedido do selo mora em «Prontas para casar»"
    if t.get("com_casamento"):
        celebrar = next(f for f in p.formularios if _acao(f) == "celebrado")
        opcoes = next(c for c in celebrar["campos"] if c["nome"] == "assento_id")["opcoes"]
        assert [o["valor"] for o in opcoes] == [str(casa.ids["civil_casamento_falta_amarrar"])], (
            "o casamento lavrado por esta habilitação tem de vir para escolher")


# ------------------------------------------------------------------- o casamento com habilitação que não vale

@pytest.mark.parametrize("estado", ["sem_documentos", "edital_sem_central", "com_oposicao", "arquivado_sem_edital", "vencida"])
def test_o_casamento_nao_se_lavra_com_habilitacao_que_nao_vale(casa, estado):  # noqa: F811
    """Achado por esta semente: o casamento entrava no livro, e a celebração recusava depois."""
    import layout_semente_civil as SEM

    casa.restaurar()
    try:
        campos = SEM._form_casamento(casa)
        for de_fora in ("habilitacao_serventia", "habilitacao_selo", "proclamas_data", "documentos_apresentados"):
            campos.pop(de_fora)
        antes = _n(casa, "SELECT COUNT(*) AS n FROM rc_assentos")
        r = casa.postar("/rcpn/novo/casamento", acao="lavrar", especie="CASAMENTO", folha_seguranca=SEM._folha(),
                        habilitacao_id=str(casa.ids[f"civil_hab_{estado}"]), **campos)
        assert r.status_code == 200, r.status_code
        assert "Nada foi lavrado" in r.get_data(as_text=True)
        assert _n(casa, "SELECT COUNT(*) AS n FROM rc_assentos") == antes
    finally:
        casa.restaurar()


def test_o_selo_nao_se_pede_de_habilitacao_nao_expedida(casa):  # noqa: F811
    casa.restaurar()
    try:
        h = casa.ids["civil_hab_sem_documentos"]
        r = casa.postar(f"/rcpn/habilitacoes/{h}/selar")
        assert r.status_code == 302
        assert not casa.um("SELECT selo FROM hc_habilitacoes WHERE id=%s", (h,))["selo"]
        assert "/selar" not in casa.cliente().get(f"/rcpn/habilitacoes/{h}").get_data(as_text=True)
    finally:
        casa.restaurar()

"""As fichas do título de Protesto, estado por estado, no layout novo.

O QUE ELES DEFENDEM
    A ficha do título abre em fases (apontar, intimar, desfecho). Cada estado do rito muda onde a
    régua abre, o que trava, o que espera ação e quais formulários estão lá. `protesto_fases`
    calcula; a rota e o molde desenham. O risco é a ficha dizer uma coisa e o título estar noutra,
    ou oferecer o formulário de um ato que o rito já não aceita: protestar título sustado, pagar
    protesto já lavrado.

COMO
    A semente (`layout_semente_protesto`) lavra um título em cada estado, pelas telas. Aqui cada um
    é aberto com o sistema de pé, como o ADMIN no layout novo, e a ficha é lida pelo que o servidor
    entrega. A tabela é o rito escrito à mão, e não a saída de `fases_do_titulo`: se a função e a
    tabela discordarem, o teste acusa.
"""
from __future__ import annotations

import html as _html
import io
import re
import zipfile

import pytest

from layout_casa import area_da_regra, areas_pedidas, casa  # noqa: F401
import layout_ensaio as E
import protesto as PT
import protesto_fases as PF
from layout_semente_protesto import ESTADOS

pytestmark = pytest.mark.lento

FEITA, LIBERADA, TRAVADA = PF.FEITA, PF.LIBERADA, PF.TRAVADA
DEPOIS_DE_APONTAR = {"INTIMACAO", "DESISTENCIA", "PAGAMENTO", "SUSTACAO"}
DEPOIS_DE_INTIMAR = DEPOIS_DE_APONTAR | {"PROTESTO"}
RITO = (PF.APONTAMENTO, PF.INTIMACAO, PF.DESFECHO)

#: Por estado: onde a régua abre, o estado e as pendências das três fases (apontar, intimar,
#: desfecho), os formulários que têm de estar na ficha, os que abrem sem clique, e o que a barra de
#: cada fase diz quando diz alguma coisa.
TABELA = {
    "recebido": dict(
        inicial=PF.APONTAMENTO, fases=(LIBERADA, TRAVADA, LIBERADA), pendencias=(1, 0, 0),
        atos={"APONTAMENTO", "DESISTENCIA", "PAGAMENTO", "SUSTACAO"}, abertos={"APONTAMENTO"},
        barra={PF.APONTAMENTO: "Aponte o título"}),
    "apontado": dict(
        inicial=PF.INTIMACAO, fases=(FEITA, LIBERADA, LIBERADA), pendencias=(0, 1, 0),
        atos=DEPOIS_DE_APONTAR, abertos={"INTIMACAO"},
        barra={PF.INTIMACAO: "Emita o aviso e lance a intimação"}),
    "intimado_no_prazo": dict(
        inicial=PF.INTIMACAO, fases=(FEITA, FEITA, LIBERADA), pendencias=(0, 0, 0),
        atos=DEPOIS_DE_INTIMAR, abertos={"INTIMACAO", "PROTESTO"},
        barra={PF.DESFECHO: "Ainda não é dia de protestar"}),
    "intimado_vencido": dict(
        inicial=PF.DESFECHO, fases=(FEITA, FEITA, LIBERADA), pendencias=(0, 0, 1),
        atos=DEPOIS_DE_INTIMAR, abertos={"INTIMACAO", "PROTESTO"},
        barra={PF.DESFECHO: "O tríduo venceu"}),
    "protestado": dict(
        inicial=PF.DESFECHO, fases=(FEITA, FEITA, LIBERADA), pendencias=(0, 0, 0),
        atos={"CANCELAMENTO", "SUSTACAO", "EFEITO_SUSPENSIVO"}, abertos=set(), barra={}),
    "sustado": dict(
        inicial=PF.INTIMACAO, fases=(FEITA, LIBERADA, LIBERADA), pendencias=(0, 1, 0),
        atos={"INTIMACAO", "REVOGACAO_SUSTACAO"}, abertos={"INTIMACAO", "REVOGACAO_SUSTACAO"}, barra={}),
    "pago": dict(
        inicial=PF.VIDA, fases=(FEITA, LIBERADA, FEITA), pendencias=(0, 0, 0), atos=set(), abertos=set(),
        barra={}),
    "desistido": dict(
        inicial=PF.VIDA, fases=(FEITA, LIBERADA, FEITA), pendencias=(0, 0, 0), atos=set(), abertos=set(),
        barra={}),
    "devolvido": dict(
        inicial=PF.VIDA, fases=(FEITA, LIBERADA, FEITA), pendencias=(0, 0, 0), atos=set(), abertos=set(),
        barra={}),
    "cancelado": dict(
        inicial=PF.VIDA, fases=(FEITA, FEITA, FEITA), pendencias=(0, 0, 0), atos=set(), abertos=set(),
        barra={}),
}

#: O que está errado no título não fica numa aba: sai no alto, em todas. Título lavrado pelas telas,
#: com selo e com a prova da intimação, não tem nenhum destes.
AVISOS_DO_ALTO = ("data-situacao-sem-ato", "data-propostas-de-oficio", "data-pendencias-do-selo",
                  "data-pedidos-cra", "data-credor-a-averbar")

ODT = "application/vnd.oasis.opendocument.text"
#: O que cada rota com número da área entrega ao ADMIN: o estado e o tipo. A pendência da CENPROT
#: manda buscar o PDF da anuência na Central, e sem rede e sem credencial ela volta à pendência.
ENTREGA = {
    "protesto_titulo": (200, ("text/html",)),
    "protesto_aviso_odt": (200, (ODT,)),
    "protesto_avisos_lote_folhas": (200, ("application/pdf",)),
    "protesto_cenprot_xml_baixar": (200, ("application/xml", "text/xml")),
    "protesto_pendencia": (200, ("text/html",)),
    "protesto_pendencia_arquivos": (302, ("text/html",)),
    "protesto_certidao": (200, ("text/html",)),
    "protesto_certidao_odt": (200, (ODT,)),
    "protesto_cra_consulta_arquivo": (200, ("text/plain",)),
    "protesto_desistencia": (200, ("text/html",)),
    "protesto_desistencia_arquivo": (200, ("text/plain",)),
    "protesto_devedor": (200, ("text/html",)),
    "protesto_edital_odt": (200, (ODT,)),
    "protesto_imagem": (200, ("application/pdf",)),
    "protesto_instrumento_odt": (200, (ODT,)),
    "protesto_livro": (200, ("text/html", ODT)),
    "protesto_quitacao_odt": (200, (ODT,)),
    "protesto_relacao_arquivo": (200, ("text/plain",)),
    "protesto_remessa": (200, ("text/html",)),
    "protesto_remessa_arquivo": (200, ("text/plain",)),
    "protesto_remessa_salva": (200, ("application/xml", "text/xml")),
    "protesto_repasse_guia": (200, ("text/html",)),
    "protesto_repasse_guia_relacao": (200, ("text/plain",)),
    "protesto_resolve_ficha": (200, ("text/html",)),
    "protesto_retorno_arquivo": (200, ("text/plain",)),
}
#: A consulta da CRA que veio vazia é guardada vazia, e o arquivo dela sai vazio.
PODE_SAIR_VAZIA = {"protesto_cra_consulta_arquivo"}


@pytest.fixture(autouse=True)
def _so_com_o_protesto_semeado():
    if "protesto" not in areas_pedidas():
        pytest.skip("CG_LAYOUT_AREAS não semeia o protesto")


def _regua(html: str) -> dict[str, dict]:
    """As três fases como a régua as desenha: o estado, as pendências do selo numérico, e o que a
    barra de baixo diz quando a fase abre."""
    fases = {}
    for estado, chave, travada, miolo in re.findall(
            r'<a class="cg-fase (feita|liberada|travada)" href="#(\w+)" data-cg-fase="\w+"( data-travada)?>(.*?)</a>',
            html, re.S):
        numero = re.search(r'class="cg-fase-c"[^>]*>(\d+)<', miolo)
        fases[chave] = {"estado": estado, "travada": bool(travada),
                        "pendencias": int(numero.group(1)) if numero else 0, "barra": ""}
    for chave, aviso in re.findall(
            r'<div class="cg-acao" data-fase="(\w+)" data-cg-barra hidden>\s*<span class="cg-acao-aviso[^"]*">(.*?)</span>',
            html, re.S):
        fases[chave]["barra"] = _html.unescape(aviso).strip()
    return fases


def _quadros_dos_atos(html: str) -> dict[str, bool]:
    """Um quadro por ato, na fase dele: o nome e se já vem aberto, sem clique."""
    return {_html.unescape(resumo).strip(): bool(aberto) for aberto, resumo in re.findall(
        r'<details class="panel cg-ato-do-titulo" data-fase="\w+"( open)?>\s*<summary>(.*?)</summary>', html, re.S)}


def _vida(html: str) -> int:
    achado = re.search(r'data-cg-fase="vida"><span>[^<]*</span>(?:<span class="cg-fase-q">(\d+)</span>)?', html)
    assert achado, "a aba «Vida do título» não saiu na régua"
    return int(achado.group(1) or 0)


def test_toda_situacao_do_titulo_tem_a_sua_ficha_semeada():
    """Situação nova no domínio sem título semeado e sem linha na tabela seria ficha que ninguém abre."""
    assert set(ESTADOS.values()) == set(PT.SITUACOES_TITULO)
    assert set(TABELA) == set(ESTADOS)


@pytest.mark.parametrize("estado", list(TABELA))
def test_a_ficha_de_cada_estado_do_rito(casa, estado):  # noqa: F811
    esperado = TABELA[estado]
    titulo_id = casa.ids[f"protesto_{estado}"]
    # Sem isto o resto mediria outro título: a semente tem de ter deixado este na situação do estado.
    situacao = casa.um("SELECT situacao FROM pt_titulos WHERE id=%s", (titulo_id,))["situacao"]
    assert situacao == ESTADOS[estado], (estado, situacao)

    resposta = casa.cliente("ADMIN", "novo").get(f"/protesto/{titulo_id}")
    assert resposta.status_code == 200, resposta.status_code
    html = resposta.get_data(as_text=True)
    p = E.ler_pagina(html)
    assert p.html_layout == "novo"
    assert situacao in p.cabecalho, p.cabecalho
    assert not [marca for marca in AVISOS_DO_ALTO if marca in html]
    # A ordem judicial sai no alto, em toda fase, e só no título que a tem.
    assert ("PROTESTO SUSTADO POR ORDEM JUDICIAL" in html) == (estado == "sustado")

    # A régua abre onde o título espera ação, e as três fases dizem em que pé estão.
    assert [(r["chave"], r["inicial"]) for r in p.regua] == [(f"protesto-{titulo_id}", esperado["inicial"])]
    fases = _regua(html)
    assert tuple(fases) == RITO, list(fases)
    assert tuple(f["estado"] for f in fases.values()) == esperado["fases"], fases
    assert tuple(f["pendencias"] for f in fases.values()) == esperado["pendencias"], fases
    for fase, trecho in esperado["barra"].items():
        assert trecho in fases[fase]["barra"], (fase, fases[fase]["barra"])
    assert not any(f["pendencias"] for f in fases.values() if f["estado"] != LIBERADA)

    # Só a intimação do título recebido trava, e o bloco que diz onde ir está lá.
    assert [f["fase"] for f in p.fases if f["so_trava"]] == ([PF.INTIMACAO] if estado == "recebido" else [])
    assert [a["fase"] for a in p.abas if a["travada"]] == ([PF.INTIMACAO] if estado == "recebido" else [])

    # A vida e a imagem são apoio de toda ficha, e a vida conta os atos do título.
    assert {PF.VIDA, PF.IMAGEM} <= {a["fase"] for a in p.abas}
    assert _vida(html) == int(casa.um("SELECT COUNT(*) AS n FROM pt_atos WHERE titulo_id=%s", (titulo_id,))["n"])

    # Os formulários: o de cada ato que cabe, e nenhum que o rito recusaria.
    lancar = [f for f in p.formularios if f["id"].startswith("lancar-")]
    assert {f["id"] for f in lancar} == {f"lancar-{ato}" for ato in esperado["atos"]}, sorted(f["id"] for f in lancar)
    for f in lancar:
        campos = {c["nome"]: c for c in f["campos"]}
        assert (f["action"], f["method"]) == (f"/protesto/{titulo_id}/lancar", "post")
        assert campos["ato"]["valor"] == f["id"].removeprefix("lancar-") and campos["csrf_token"]["valor"]
    quadros = _quadros_dos_atos(html)
    assert set(quadros) == {PF.rotulo_do_ato(ato) for ato in esperado["atos"]}, quadros
    assert {nome for nome, aberto in quadros.items() if aberto} == {PF.rotulo_do_ato(a) for a in esperado["abertos"]}

    # O protesto fora do tríduo pede o motivo do atraso, e só ele.
    if "PROTESTO" in esperado["atos"]:
        campos = {c["nome"]: c for c in next(f for f in lancar if f["id"] == "lancar-PROTESTO")["campos"]}
        assert ("motivo_atraso" in campos) == (estado == "intimado_vencido")
        if "motivo_atraso" in campos:
            assert campos["motivo_atraso"]["obrigatorio"]


@pytest.mark.parametrize("estado", ["protestado", "cancelado"])
def test_a_vida_do_titulo_nao_imprime_o_dicionario_do_python(casa, estado):  # noqa: F811
    """Achado por esta semente: a linha do protesto saía com `prova: {'modo': ...}`."""
    html = casa.cliente("ADMIN", "novo").get(f"/protesto/{casa.ids[f'protesto_{estado}']}").get_data(as_text=True)
    assert not re.search(r"<small>[a-z_ ]+: [{\[]", html)
    assert "None" not in re.sub(r"<script.*?</script[^>]*>", "", html, flags=re.S | re.I)
    assert "prova: modo:" in html


def _corpo_defeituoso(tipo: str, corpo: bytes) -> str:
    """Vazio se o arquivo é o que o tipo diz; senão, o defeito."""
    if tipo == ODT:
        try:
            with zipfile.ZipFile(io.BytesIO(corpo)) as z:
                return "" if "content.xml" in z.namelist() else "o .odt não tem content.xml"
        except zipfile.BadZipFile:
            return "o .odt não é um pacote zip"
    if tipo == "application/pdf":
        return "" if corpo.startswith(b"%PDF") else "o PDF não começa por %PDF"
    if tipo in ("application/xml", "text/xml"):
        return "" if corpo.lstrip(b"\xef\xbb\xbf").lstrip().startswith(b"<?xml") else "o XML não começa pela declaração"
    return ""


def test_a_semente_do_protesto_abre_cada_rota_de_verdade(casa):  # noqa: F811
    """O teste geral da semente só barra 404, 500 e a volta ao login: uma rota que redireciona com
    aviso, porque a linha não tinha o que a tela pede, passaria. Aqui cada endereço entrega o que
    diz entregar, e o papel sai de verdade."""
    c = casa.cliente("ADMIN", "novo")
    vistas, ruins = set(), []
    for endpoint, endereco in casa.paginas:
        if area_da_regra(endereco) != "protesto":
            continue
        assert endpoint in ENTREGA, f"rota nova sem linha na tabela: {endpoint} ({endereco})"
        vistas.add(endpoint)
        estado, tipos = ENTREGA[endpoint]
        r = c.get(endereco)
        corpo = r.get_data()
        defeito = ""
        if r.status_code != estado:
            defeito = f"devolveu {r.status_code} e devia devolver {estado} {r.headers.get('Location', '')}"
        elif r.mimetype not in tipos:
            defeito = f"devolveu {r.mimetype} e devia devolver {' ou '.join(tipos)}"
        elif estado == 200:
            defeito = _corpo_defeituoso(r.mimetype, corpo)
            if not defeito and not corpo and endpoint not in PODE_SAIR_VAZIA:
                defeito = "veio vazio"
        elif "/protesto/cenprot/pendencias/" not in r.headers.get("Location", ""):
            defeito = f"redirecionou para {r.headers.get('Location')}"
        if defeito:
            ruins.append(f"{endereco} ({endpoint}): {defeito}")
    assert not ruins, "rota da semente que não entrega:\n  " + "\n  ".join(ruins)
    assert vistas == set(ENTREGA), sorted(set(ENTREGA) - vistas)

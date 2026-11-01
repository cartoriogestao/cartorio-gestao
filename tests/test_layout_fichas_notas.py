"""A ficha do ato de Notas, estado por estado, no layout novo.

O QUE ELES DEFENDEM
    A ficha do ato abre em fases (preparar, partes, teor, DOI, lançar, entrega). Cada estado do
    rito muda a fase em que a régua abre, o que trava, o que espera ação e quais formulários
    estão lá. `notas_fases` calcula; a rota e o molde desenham. O risco é a ficha dizer uma coisa
    e o ato estar noutra, ou oferecer o formulário de um passo que o rito já deu (lançar de novo
    um ato lançado) ou ainda não abriu (pedir o selo de ato em lavratura). E o quadro que fica
    numa fase que a régua não tem some da tela sem erro nenhum.

COMO
    A semente (`layout_semente_notas`) leva um ato a cada estado, pelas rotas de verdade: aberto,
    com partes, com a qualificação ou o teor pela metade, pronto, lançado, selado, lavrado, e as
    variações da DOI, da ata, do ato sem modelo e da comunicação à serventia de origem. Aqui cada um é aberto com o
    sistema de pé, como o ADMIN no layout novo, e a ficha é lida pelo que o servidor entrega.

DUAS CONTAS, E NÃO UMA
    A página tem de dizer o que o módulo puro calcula com os fatos do banco, e o módulo tem de
    dizer o que o estado promete. Só a primeira conta passa quando é o próprio módulo que está
    errado, e por isso a tabela traz a promessa escrita à mão.

`CG_LAYOUT_AREAS=notas` olha só esta área.
"""
from __future__ import annotations

import html as _html
import re
from typing import NamedTuple

import pytest

import layout_ensaio as E
import notas_fases as NF
from layout_casa import areas_pedidas, casa  # noqa: F401
from layout_semente_notas import ATOS_DO_RITO, CHAVES_DO_ATO

pytestmark = pytest.mark.lento

if "notas" not in areas_pedidas():
    pytest.skip("as notas não foram semeadas nesta rodada (CG_LAYOUT_AREAS)", allow_module_level=True)


# ------------------------------------------------------------------ o que cada estado promete

class Promessa(NamedTuple):
    """O que a ficha de um ato, naquele estado, tem de mostrar."""
    situacao: str                    # a situação do ato no banco: sem ela a tabela mediria outro ato
    regua: str                       # fase:estado, com /N quando a bolinha de pendências aparece
    abre_em: str | None              # a fase em que a régua abre (None: decidido à parte)
    falta_lancar: tuple = ()         # trechos que têm de estar em linhas pendentes; vazio: nenhuma
    falta_entregar: tuple = ()
    tem: tuple = ()                  # formulários (`acao`) que têm de estar na ficha
    nao_tem: tuple = ()              # e os que não podem estar
    barras: dict = {}                # fase -> trecho do aviso da barra de baixo
    sem_modelo: bool = False         # sem modelo do sistema: a ficha oferece «Montar com as partes»


# A régua de cada momento do rito. A bolinha de pendências do «Lançar» não entra: ela conta
# também as travas que o servidor recusaria (CENSEC, a procuração sem outorgado), e a frase de
# cada uma está em `falta_lancar`.
ABERTA = "preparar:liberada partes:liberada teor:liberada lancar:travada entrega:travada"
SO_PARTES = "preparar:feita partes:feita teor:liberada lancar:travada entrega:travada"
PARTE_PELA_METADE = "preparar:feita partes:liberada/1 teor:feita lancar:liberada entrega:travada"
TEOR_PELA_METADE = "preparar:feita partes:feita teor:liberada/1 lancar:liberada entrega:travada"
PRONTA = "preparar:feita partes:feita teor:feita lancar:liberada entrega:travada"
FALTA_UM = "preparar:feita partes:feita teor:feita lancar:feita entrega:liberada/1"
FALTAM_DOIS = "preparar:feita partes:feita teor:feita lancar:feita entrega:liberada/2"
LAVRADA = "preparar:feita partes:feita teor:feita lancar:feita entrega:feita"
ESC_ABERTA = "preparar:liberada partes:liberada teor:liberada doi:travada lancar:travada entrega:travada"
ESC_PRONTA = "preparar:feita partes:feita teor:feita doi:liberada/1 lancar:liberada entrega:travada"
ESC_COM_DOI = "preparar:feita partes:feita teor:feita doi:feita lancar:liberada entrega:travada"
ESC_LANCADA = "preparar:feita partes:feita teor:feita doi:feita lancar:feita entrega:liberada/1"
ESC_DOI_ABERTA = "preparar:feita partes:feita teor:feita doi:liberada/1 lancar:feita entrega:feita"
ESC_LAVRADA = "preparar:feita partes:feita teor:feita doi:feita lancar:feita entrega:feita"
ATA_ABERTA = "preparar:liberada partes:liberada documentos:liberada teor:liberada lancar:travada entrega:travada"
ATA_PRONTA = "preparar:feita partes:feita documentos:feita teor:feita lancar:liberada entrega:travada"
ATA_LAVRADA = "preparar:feita partes:feita documentos:feita teor:feita lancar:feita entrega:feita"

# Os formulários de cada momento. Em lavratura não há selo de ato, nota à margem nem depósito
# (a rota recusa o depósito de ato que não foi ao livro); lançado e sem selo, pede-se o selo ou
# digita-se o que saiu do portal; só o ato selado e sem o 13.30 pede o selo de arquivamento.
EM_LAVRATURA = ("parte_nova", "teor", "lancar")
NAO_EM_LAVRATURA = ("selar", "selo_arquivamento", "anotar", "deposito")
SEM_SELO = ("selar", "selo", "anotar", "deposito")
NAO_SEM_SELO = ("lancar", "selo_arquivamento")
SO_FALTA_O_13_30 = ("selo_arquivamento", "anotar")
NAO_SO_FALTA_O_13_30 = ("lancar", "selar", "selo")
JA_LAVRADO = ("anotar",)
NAO_JA_LAVRADO = ("lancar", "selar", "selo")

PARTES = "Incluir as partes"
TEOR = "Escrever o teor"
ARQUIVAR = "Anexar o documento arquivado"
SELO_DO_ATO = "Pedir o selo do ato"
SELO_13_30 = "Pedir o selo de arquivamento (13.30)"
COMUNICAR = "Registrar a comunicação à serventia de origem"
COMPROVANTE = "Juntar o comprovante da comunicação"
BARRA_DA_DOI = "Enquanto faltar, a conferência da DOI continua cobrando"

#: Estado a estado, o rito escrito à mão, e não a saída de `fases_do_ato`: se o módulo e a tabela
#: discordarem, o teste acusa. A DOI é a pergunta de toda escritura; o `origem` e o ofício são
#: do substabelecimento (CN-MA, art. 831, § 1º); `proc_da_base` é a procuração que a carga de
#: demonstração traz, lavrada sem o 13.30.
ESTADOS: dict[str, Promessa] = {
    "proc_aberta": Promessa(
        "EM_LAVRATURA", ABERTA, "preparar", (PARTES, TEOR, ARQUIVAR), (),
        EM_LAVRATURA, NAO_EM_LAVRATURA + ("origem",)),
    "proc_partes": Promessa(
        "EM_LAVRATURA", SO_PARTES, "teor", (TEOR, ARQUIVAR), (),
        EM_LAVRATURA + ("remover_parte", "qualificacao_parte"), NAO_EM_LAVRATURA),
    # o modelo do sistema já traz o comparecimento e a qualificação; sem ele, quem monta é a rota
    # `notas_ato_montar`, e o botão só existe aqui
    "proc_sem_modelo": Promessa(
        "EM_LAVRATURA", SO_PARTES, "teor", (TEOR, ARQUIVAR), (),
        EM_LAVRATURA + ("remover_parte", "qualificacao_parte"), NAO_EM_LAVRATURA, {}, True),
    "proc_partes_incompletas": Promessa(
        "EM_LAVRATURA", PARTE_PELA_METADE, "partes", ("Completar a qualificação: Beatriz Exemplo",), (),
        EM_LAVRATURA + ("qualificacao_parte", "confirmar_arquivamento"), NAO_EM_LAVRATURA,
        {"partes": "Falta qualificar Beatriz Exemplo"}),
    "proc_teor_incompleto": Promessa(
        "EM_LAVRATURA", TEOR_PELA_METADE, "teor", ("Preencher 1 campo(s) em branco do teor",), (),
        EM_LAVRATURA + ("confirmar_arquivamento",), NAO_EM_LAVRATURA,
        {"teor": "[PRAZO DO MANDATO]"}),
    "proc_pronta": Promessa(
        "EM_LAVRATURA", PRONTA, "lancar", (), (),
        EM_LAVRATURA + ("confirmar_arquivamento",), NAO_EM_LAVRATURA),
    "proc_lancada": Promessa(
        "SUSPENSO_SELO", FALTA_UM, "entrega", (), (SELO_DO_ATO,), SEM_SELO, NAO_SEM_SELO + ("origem",)),
    "proc_selada": Promessa(
        "SUSPENSO_SELO", FALTA_UM, "entrega", (), (SELO_13_30,), SO_FALTA_O_13_30, NAO_SO_FALTA_O_13_30),
    "proc_lavrada": Promessa(
        "LAVRADO", LAVRADA, "entrega", (), (), JA_LAVRADO, NAO_JA_LAVRADO + ("selo_arquivamento",)),
    "proc_da_base": Promessa(
        "LAVRADO", FALTA_UM, "entrega", (), (SELO_13_30,), SO_FALTA_O_13_30, NAO_SO_FALTA_O_13_30),
    "proc_do_agente": Promessa(
        "EM_LAVRATURA", "preparar:feita partes:liberada teor:feita lancar:liberada entrega:travada",
        "partes", (PARTES,), (), EM_LAVRATURA + ("confirmar_arquivamento",), NAO_EM_LAVRATURA),

    "subst_aberta": Promessa(
        "EM_LAVRATURA", ABERTA, "preparar", (PARTES, TEOR, ARQUIVAR), (),
        EM_LAVRATURA + ("origem",), NAO_EM_LAVRATURA),
    "subst_pronta": Promessa(
        "EM_LAVRATURA", PRONTA, "lancar", (), (),
        EM_LAVRATURA + ("origem", "confirmar_arquivamento"), NAO_EM_LAVRATURA),
    "subst_com_origem": Promessa(
        "SUSPENSO_SELO", FALTAM_DOIS, "entrega", (), (SELO_DO_ATO, COMUNICAR),
        SEM_SELO + ("origem", "oficio", "comprovante"), NAO_SEM_SELO),
    "subst_com_oficio": Promessa(
        "SUSPENSO_SELO", FALTAM_DOIS, "entrega", (), (SELO_DO_ATO, COMPROVANTE),
        SEM_SELO + ("comprovante",), NAO_SEM_SELO + ("origem", "oficio")),
    "subst_lavrada": Promessa(
        "LAVRADO", LAVRADA, "entrega", (), (), JA_LAVRADO + ("origem",),
        NAO_JA_LAVRADO + ("selo_arquivamento",)),

    "revog_aberta": Promessa(
        "EM_LAVRATURA", ABERTA, "preparar", (PARTES, TEOR, ARQUIVAR), (),
        EM_LAVRATURA, NAO_EM_LAVRATURA + ("origem",)),
    "revog_pronta": Promessa(
        "EM_LAVRATURA", PRONTA, "lancar", (), (),
        EM_LAVRATURA + ("confirmar_arquivamento",), NAO_EM_LAVRATURA + ("origem",)),
    "revog_lavrada": Promessa(
        "LAVRADO", LAVRADA, "entrega", (), (), JA_LAVRADO, NAO_JA_LAVRADO + ("selo_arquivamento", "origem")),

    "esc_aberta": Promessa(
        "EM_LAVRATURA", ESC_ABERTA, "preparar", (PARTES, TEOR), (),
        EM_LAVRATURA + ("imovel",), NAO_EM_LAVRATURA, {"doi": BARRA_DA_DOI}),
    "esc_pronta": Promessa(
        "EM_LAVRATURA", ESC_PRONTA, "doi", (), (),
        EM_LAVRATURA + ("imovel", "papel_doi"), NAO_EM_LAVRATURA, {"doi": BARRA_DA_DOI}),
    "esc_com_doi": Promessa(
        "EM_LAVRATURA", ESC_COM_DOI, "lancar", (), (),
        EM_LAVRATURA + ("imovel", "papel_doi"), NAO_EM_LAVRATURA),
    "esc_lancada": Promessa(
        "SUSPENSO_SELO", ESC_LANCADA, "entrega", (), (SELO_DO_ATO,),
        SEM_SELO + ("imovel",), NAO_SEM_SELO),
    "esc_lavrada_doi_pendente": Promessa(
        "LAVRADO", ESC_DOI_ABERTA, None, (), (),
        JA_LAVRADO + ("imovel", "selo_arquivamento"), NAO_JA_LAVRADO, {"doi": BARRA_DA_DOI}),
    "esc_lavrada": Promessa(
        "LAVRADO", ESC_LAVRADA, "entrega", (), (),
        JA_LAVRADO + ("imovel", "selo_arquivamento"), NAO_JA_LAVRADO),

    "escsi_aberta": Promessa(
        "EM_LAVRATURA", ABERTA, "preparar", (PARTES, TEOR), (),
        EM_LAVRATURA + ("imovel",), NAO_EM_LAVRATURA),
    # o modelo sem imóvel tira a DOI da régua e deixa o quadro ao alcance: a ficha pronta abre no
    # «Lançar», e não na DOI, que é onde abre a escritura de compra e venda
    "escsi_pronta": Promessa(
        "EM_LAVRATURA", PRONTA, "lancar", (), (),
        EM_LAVRATURA + ("imovel", "papel_doi"), NAO_EM_LAVRATURA),

    "ata_aberta": Promessa(
        "EM_LAVRATURA", ATA_ABERTA, "preparar", (PARTES, TEOR), (),
        EM_LAVRATURA, NAO_EM_LAVRATURA, {"documentos": "A descrição de cada evidência é obrigatória"}),
    "ata_pronta": Promessa(
        "EM_LAVRATURA", ATA_PRONTA, "lancar", (), (),
        EM_LAVRATURA, NAO_EM_LAVRATURA, {"documentos": "A descrição de cada evidência é obrigatória"}),
    "ata_lavrada": Promessa(
        "LAVRADO", ATA_LAVRADA, "entrega", (), (),
        JA_LAVRADO + ("selo_arquivamento",), NAO_JA_LAVRADO,
        {"documentos": "A descrição de cada evidência é obrigatória"}),
}

#: Além da régua, o que cada espécie de ato deixa ao alcance, fora das fases.
APOIO = {"PROC": ("documentos", "financeiro"), "SUBST": ("documentos", "financeiro"),
         "REVOG": ("documentos", "financeiro"), "ESC": ("documentos", "financeiro"),
         "ESCSI": ("documentos", "financeiro", "doi"), "ATA": ("financeiro",)}
RITO_DO_ATO = {**{chave: rito for chave, (rito, _) in ATOS_DO_RITO.items()},
               "proc_da_base": "PROC", "proc_do_agente": "PROC"}

#: O recado em cima da ficha, quando o ato ainda não está lavrado.
RECADO_DA_SITUACAO = {"EM_LAVRATURA": "EM LAVRATURA.", "SUSPENSO_SELO": "SUSPENSO — SELO NÃO EMITIDO."}


# ------------------------------------------------------------------ o que os testes usam

@pytest.fixture(scope="module")
def ficha(casa):  # noqa: F811
    """A ficha de cada ato, aberta uma vez só: duas dezenas de páginas pesadas, e vários testes."""
    cliente = casa.cliente("ADMIN", "novo")
    guardadas: dict[str, tuple] = {}

    def abrir(chave: str) -> tuple:
        if chave not in guardadas:
            ato_id = casa.ids[f"notas_ato_{chave}"]
            resposta = cliente.get(f"/notas/atos/{ato_id}")
            assert resposta.status_code == 200, f"/notas/atos/{ato_id}: HTTP {resposta.status_code}"
            html = resposta.get_data(as_text=True)
            guardadas[chave] = (ato_id, html, E.ler_pagina(html))
        return guardadas[chave]
    return abrir


def _regua(html: str, p) -> tuple[list[str], list[str]]:
    """As fases como a régua as desenha, e o apoio. A bolinha do «Lançar» fica de fora (ver acima)."""
    bolinhas = {}
    for fase, miolo in re.findall(r'data-cg-fase="(\w+)"[^>]*>(.*?)</a>', html, re.S):
        achado = re.search(r'class="cg-fase-c"[^>]*>(\d+)<', miolo)
        if achado:
            bolinhas[fase] = achado.group(1)
    fases, apoio = [], []
    for aba in p.abas:
        if "apoio" in aba["classes"]:
            apoio.append(aba["fase"])
            continue
        estado = "travada" if aba["travada"] else next(
            c for c in aba["classes"] if c in (NF.FEITA, NF.LIBERADA, NF.TRAVADA))
        bolinha = f"/{bolinhas[aba['fase']]}" if aba["fase"] in bolinhas and aba["fase"] != "lancar" else ""
        fases.append(f"{aba['fase']}:{estado}{bolinha}")
    return fases, apoio


def _faltas(html: str) -> dict[str, list[tuple[str, str]]]:
    """Os quadros «O que falta»: por fase, cada linha com a marca (ok ou pendente) e o texto."""
    saida = {}
    for fase, miolo in re.findall(r'<section class="panel cg-falta" data-fase="(\w+)">(.*?)</section>', html, re.S):
        itens = re.findall(r'<li class="(ok|pendente)">\s*<span class="cg-falta-m"[^>]*>(?:&#10003;)?</span>'
                           r'\s*<span>(.*?)</span>', miolo, re.S)
        saida[fase] = [(marca, " ".join(_html.unescape(re.sub(r"<[^>]+>", "", texto)).split()))
                       for marca, texto in itens]
    return saida


def _pendentes(faltas: dict, fase: str) -> list[str]:
    return [texto for marca, texto in faltas.get(fase, []) if marca == "pendente"]


def _barras(html: str) -> dict[str, str]:
    return {fase: _html.unescape(aviso).strip() for fase, aviso in re.findall(
        r'<div class="cg-acao" data-fase="(\w+)" data-cg-barra hidden>\s*<span class="cg-acao-aviso[^"]*">(.*?)</span>',
        html, re.S)}


def _travas(html: str) -> dict[str, tuple[str, str, str, str]]:
    """Por fase travada: o título, a explicação, para onde leva e o rótulo do botão."""
    return {fase: (_html.unescape(titulo).strip(), _html.unescape(texto).strip(), ir, _html.unescape(rotulo).strip())
            for fase, titulo, texto, ir, rotulo in re.findall(
                r'<section class="panel cg-trava" data-fase="(\w+)" data-cg-so-trava hidden>\s*'
                r'<p class="cg-trava-t">(.*?)</p>\s*<p class="muted">(.*?)</p>\s*'
                r'<a class="button primary" href="#(\w+)">(.*?)</a>', html, re.S)}


def _acoes(p) -> set[str]:
    """O `acao` de cada formulário da ficha: o botão que o leva (`name="acao"`) ou o campo escondido,
    que é como o quadro da DOI o manda."""
    return {x["valor"] for f in p.formularios if f["no_conteudo"]
            for x in (*f["botoes"], *f["campos"]) if x["nome"] == "acao"}


def _pelo_modulo(casa, ato_id: int) -> dict:  # noqa: F811
    """O que `notas_fases` calcula com os fatos que o banco tem sobre o ato. Sem as travas do
    servidor, que só mexem na bolinha do «Lançar»."""
    import notas_arquivamento as NARQ
    import notas_comunicacao_origem as NCO
    import notas_teor as NT
    from ri_modelos_atos import pendencias as claros_do_teor
    from serventia import dados as dados_da_serventia
    a = casa.um("SELECT * FROM nt_atos WHERE id=%s", (ato_id,))
    partes = casa.ler("SELECT * FROM nt_ato_partes WHERE ato_id=%s ORDER BY testemunha, ordem, id", (ato_id,))
    modelo = (casa.um("SELECT com_imovel FROM nt_modelos WHERE codigo=%s", (a["modelo_codigo"],))
              if a["modelo_codigo"] else None)
    with casa.db.connect() as con:
        arquivamento = NARQ.situacao(con, a)
        comunicacao = NCO.do_ato(con, ato_id)
    r = NF.fases_do_ato(
        a, partes=partes, anexos=casa.db.get_attachments("NT_ATO", ato_id),
        pendencias=claros_do_teor(a["teor"] or ""), falta_qualificar=NT.pendencias_da_qualificacao(partes),
        arquivamento=arquivamento, comunicacao=comunicacao,
        comunicacao_devida=NCO.devida(a, dados_da_serventia(casa.db.get_settings)), depositos=[],
        modelo_com_imovel=bool(modelo["com_imovel"]) if modelo else None)
    return {
        "fases": [f"{x['chave']}:{x['estado']}"
                  + (f"/{x['pendencias']}" if x["pendencias"] and x["chave"] != "lancar" else "")
                  for x in r["fases"]],
        "apoio": [x["chave"] for x in r["apoio"]], "inicial": r["inicial"],
        "rotulos": {x["chave"]: x["rotulo"] for x in r["fases"]}}


# ------------------------------------------------------------------ os testes

def test_toda_ficha_semeada_tem_a_sua_promessa():
    """Estado novo na semente sem linha na tabela passaria sem ninguém medir o que ele promete."""
    assert set(ESTADOS) == set(CHAVES_DO_ATO), set(ESTADOS) ^ set(CHAVES_DO_ATO)


@pytest.mark.parametrize("chave", list(ESTADOS))
def test_a_ficha_de_cada_estado_promete_o_que_o_rito_pede(casa, ficha, chave):  # noqa: F811
    esperado = ESTADOS[chave]
    ato_id, html, p = ficha(chave)
    a = casa.um("SELECT situacao, termo FROM nt_atos WHERE id=%s", (ato_id,))
    # Sem isto o resto mediria outro ato: a semente tem de ter deixado este na situação do estado.
    assert a["situacao"] == esperado.situacao, (chave, a["situacao"])
    assert p.html_layout == "novo"

    # O alto da ficha diz em que pé o ato está: em lavratura, ou o termo do livro.
    if a["situacao"] == "EM_LAVRATURA":
        assert "em lavratura" in p.cabecalho.lower(), p.cabecalho
    else:
        assert f"termo nº {a['termo']}" in p.cabecalho, p.cabecalho
    recado = RECADO_DA_SITUACAO.get(a["situacao"])
    assert (recado in html) if recado else not any(r in html for r in RECADO_DA_SITUACAO.values())

    # A régua: as fases na ordem do rito, em que pé está cada uma, onde ela abre, e o apoio.
    fases, apoio = _regua(html, p)
    assert fases == esperado.regua.split(), fases
    assert apoio == list(APOIO[RITO_DO_ATO[chave]]), apoio
    assert [(r["chave"]) for r in p.regua] == [f"ato-{ato_id}"]
    if esperado.abre_em is not None:
        assert p.regua[0]["inicial"] == esperado.abre_em, p.regua[0]

    # O que espera ação, no quadro «O que falta»: o que está pendente, e nada mais quando não falta.
    faltas = _faltas(html)
    for fase, trechos in (("lancar", esperado.falta_lancar), ("entrega", esperado.falta_entregar)):
        pendentes = _pendentes(faltas, fase)
        for trecho in trechos:
            assert any(trecho in linha for linha in pendentes), (fase, trecho, pendentes)
        if not trechos:
            assert not pendentes, (fase, pendentes)
    # Ato lançado não tem mais o que lançar, e em lavratura não há o que entregar.
    assert ("lancar" in faltas) == (a["situacao"] == "EM_LAVRATURA"), list(faltas)
    assert not (a["situacao"] == "EM_LAVRATURA" and "entrega" in faltas), list(faltas)

    # A trava: um bloco por fase travada, com a frase do módulo e o caminho para destravar.
    travadas = {x.split(":")[0] for x in fases if x.endswith(":travada")}
    travas = _travas(html)
    assert set(travas) == travadas, (sorted(travas), sorted(travadas))
    rotulos = _pelo_modulo(casa, ato_id)["rotulos"]
    for fase, (titulo, texto, ir, botao) in travas.items():
        assert (titulo, texto, ir) == NF.TRAVAS[fase], (fase, titulo, texto, ir)
        assert botao == f"Ir a {rotulos[ir]}", (fase, botao)
    assert {x["fase"] for x in p.abas if x["travada"]} == travadas

    # A barra de baixo de cada fase, quando diz alguma coisa.
    barras = _barras(html)
    for fase, trecho in esperado.barras.items():
        assert trecho in barras.get(fase, ""), (fase, barras)

    # Os formulários: os que o estado pede, e nenhum que o rito não aceita.
    acoes = _acoes(p)
    assert set(esperado.tem) <= acoes, (set(esperado.tem) - acoes, sorted(acoes))
    assert not set(esperado.nao_tem) & acoes, (set(esperado.nao_tem) & acoes, sorted(acoes))
    # «Montar com as partes» não tem `acao`: o formulário se conhece pelo endereço
    montar = [f["action"] for f in p.formularios if f["no_conteudo"] and (f["action"] or "").endswith("/montar")]
    assert bool(montar) == esperado.sem_modelo, (montar, esperado.sem_modelo)


@pytest.mark.parametrize("chave", list(ESTADOS))
def test_a_ficha_diz_o_que_o_modulo_calcula_com_os_fatos_do_banco(casa, ficha, chave):  # noqa: F811
    ato_id, html, p = ficha(chave)
    fases, apoio = _regua(html, p)
    do_modulo = _pelo_modulo(casa, ato_id)
    assert fases == do_modulo["fases"], (fases, do_modulo["fases"])
    assert apoio == do_modulo["apoio"], (apoio, do_modulo["apoio"])
    assert p.regua[0]["inicial"] == do_modulo["inicial"], (p.regua[0]["inicial"], do_modulo["inicial"])


@pytest.mark.parametrize("chave", list(ESTADOS))
def test_a_regua_e_os_quadros_da_ficha_se_encaixam(casa, ficha, chave):  # noqa: F811
    """Quadro numa fase que a régua não tem, ou fase sem endereço na página, some sem erro nenhum."""
    ato_id, html, p = ficha(chave)
    fases, apoio = _regua(html, p)
    chaves = [x.split(":")[0] for x in fases] + apoio
    assert len(p.regua) == 1 and p.regua[0]["inicial"] in chaves, (p.regua, chaves)
    # cada aba leva a um endereço que existe, uma vez só
    assert [c for c in chaves if p.ids[c] != 1] == [], {c: p.ids[c] for c in chaves}
    assert [a["href"] for a in p.abas] == [f"#{c}" for c in chaves]
    # cada quadro mora numa fase da régua desta ficha
    assert {f["fase"] for f in p.fases} <= set(chaves), {f["fase"] for f in p.fases} - set(chaves)
    # a trava só existe onde a fase está travada, e toda fase tem a sua barra
    assert sorted(f["fase"] for f in p.fases if f["so_trava"]) == sorted(
        x.split(":")[0] for x in fases if x.endswith(":travada"))
    assert sorted(f["fase"] for f in p.fases if f["barra"]) == sorted(x.split(":")[0] for x in fases)
    # o script que mostra uma fase de cada vez veio, e a página não está torta
    assert any("fases.js" in r for r in p.recursos), p.recursos
    assert p.tortas == [], p.tortas
    # todo formulário da ficha que grava leva o token
    sem_token = [f["action"] for f in p.formularios
                 if f["no_conteudo"] and f["method"] == "post" and not any(c["nome"] == "csrf_token" for c in f["campos"])]
    assert sem_token == [], sem_token


def test_a_ficha_do_ato_que_o_agente_preparou_mostra_o_pedido(casa, ficha):  # noqa: F811
    """O quadro do agente de minutas é o primeiro da ficha, e leva ao pedido que preencheu o teor."""
    ato_id, html, p = ficha("proc_do_agente")
    pedido = casa.ids["notas_agente_pedido"]
    assert f"/agente-minutas/pedido/{pedido}" in html
    assert (casa.um("SELECT teor FROM nt_atos WHERE id=%s", (ato_id,))["teor"] or "").strip()


def test_a_ficha_lavrada_com_a_doi_em_aberto_abre_na_doi(ficha):
    """Achado por esta semente: abria na Entrega, com a bolinha na DOI: o que espera ação vem primeiro."""
    _ato_id, html, p = ficha("esc_lavrada_doi_pendente")
    fases, _apoio = _regua(html, p)
    assert "doi:liberada/1" in fases and "entrega:feita" in fases
    assert p.regua[0]["inicial"] == "doi", p.regua[0]

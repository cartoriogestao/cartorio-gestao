"""As fases da ficha do ato: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Que a régua muda com o ato sem ninguém configurar nada, e que nenhum quadro fica fora
    de alcance. O risco desta mudança é esse: um quadro sem fase, ou preso numa fase que
    ainda não abre, some da tela sem erro nenhum, e o escrevente conclui que a função acabou.

    Tudo aqui lê arquivo e faz conta. O que precisa do sistema de pé está em
    `tests/test_ficha_em_fases_web.py`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_fases as NF  # noqa: E402

FICHA = (RAIZ / "templates" / "notas_ato.html").read_text(encoding="utf-8")
MACROS = (RAIZ / "templates" / "_fases.html").read_text(encoding="utf-8")
SCRIPT = (RAIZ / "static" / "fases.js").read_text(encoding="utf-8")


def _ato(**campos) -> dict:
    return {"id": 1, "tipo": "PROCURACAO", "situacao": "EM_LAVRATURA", "teor": "", **campos}


def _chaves(r: dict) -> list[str]:
    return [f["chave"] for f in r["fases"]]


def _fase(r: dict, chave: str) -> dict:
    return next(f for f in r["fases"] if f["chave"] == chave)


# ----------------------------------------------------------- a régua muda com o ato

def test_a_procuracao_tem_cinco_fases():
    assert _chaves(NF.fases_do_ato(_ato())) == ["preparar", "partes", "teor", "lancar", "entrega"]


def test_a_escritura_ganha_a_doi_antes_de_lancar():
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA"))
    assert _chaves(r) == ["preparar", "partes", "teor", "doi", "lancar", "entrega"]


def test_o_modelo_sem_imovel_tira_a_doi_da_regua_e_deixa_ao_alcance():
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA"), modelo_com_imovel=False)
    assert "doi" not in _chaves(r)
    assert "doi" in [x["chave"] for x in r["apoio"]]


def test_o_zero_de_com_imovel_nao_tira_a_doi_da_regua():
    """A coluna nasce 0: tirar pelo 0 esconderia a DOI de toda escritura nova."""
    assert "doi" in _chaves(NF.fases_do_ato(_ato(tipo="ESCRITURA", com_imovel=0)))
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA", com_imovel=1), modelo_com_imovel=False)
    assert "doi" in _chaves(r), "quem marcou o imóvel vale mais que o modelo"


def test_quem_vai_lancar_le_que_a_escritura_esta_sem_imovel():
    """É o ponto em que o engano custa: declaração da Receita que deixa de sair."""
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA", teor="x", com_imovel=0))
    linha = next(i for i in r["para_lancar"] if "sem imóvel" in i["texto"])
    assert linha["ir"] == "doi"
    assert not any("sem imóvel" in i["texto"]
                   for i in NF.fases_do_ato(_ato(teor="x"))["para_lancar"])


def test_a_ata_troca_documentos_por_evidencias_e_nao_perde_as_partes():
    """O desenho tirava Partes da ata, mas o quadro existe e a CENSEC lê as partes dela."""
    r = NF.fases_do_ato(_ato(tipo="ATA"))
    assert _chaves(r) == ["preparar", "partes", "documentos", "teor", "lancar", "entrega"]
    assert _fase(r, "documentos")["rotulo"] == "Evidências"
    assert "documentos" not in [x["chave"] for x in r["apoio"]]


def test_toda_ficha_tem_apoio_de_documentos_e_financeiro():
    assert [x["chave"] for x in NF.fases_do_ato(_ato())["apoio"]] == ["documentos", "financeiro"]


def test_no_maximo_oito_subabas():
    r = NF.fases_do_ato(_ato(tipo="ATA"))
    assert len(r["fases"]) + len(r["apoio"]) <= 8


# ----------------------------------------------------------- o que trava

def test_a_doi_trava_sem_teor_e_abre_com_ele():
    """É o exemplo do pedido do oficial, e a trava diz o que falta."""
    sem = NF.fases_do_ato(_ato(tipo="ESCRITURA"))
    assert _fase(sem, "doi")["estado"] == NF.TRAVADA
    assert _fase(sem, "doi")["trava"]["ir"] == "teor"
    com = NF.fases_do_ato(_ato(tipo="ESCRITURA", teor="Saibam quantos"))
    assert _fase(com, "doi")["estado"] == NF.LIBERADA
    assert _fase(com, "doi")["trava"] is None


def test_a_doi_ja_marcada_nao_trava_mesmo_sem_teor():
    """Quem já anotou o imóvel e apagou o teor não pode perder o acesso ao que anotou."""
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA", com_imovel=1))
    assert _fase(r, "doi")["estado"] != NF.TRAVADA


def test_lancar_trava_sem_teor_e_entrega_trava_em_lavratura():
    r = NF.fases_do_ato(_ato())
    assert _fase(r, "lancar")["estado"] == NF.TRAVADA
    assert _fase(r, "entrega")["estado"] == NF.TRAVADA
    assert _fase(r, "entrega")["trava"]["ir"] == "lancar"
    assert _fase(NF.fases_do_ato(_ato(teor="Saibam")), "lancar")["estado"] == NF.LIBERADA


def test_depois_de_lancado_nada_fica_travado():
    r = NF.fases_do_ato(_ato(situacao="LAVRADO", teor="Saibam", livro="31", selo="X", lancado_em="2026"))
    assert {f["estado"] for f in r["fases"]} == {NF.FEITA}


def test_a_doi_continua_cobrando_depois_de_lavrado():
    """Depois de lavrada, a escritura com a DOI em aberto continua com a fase à vista."""
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA", situacao="LAVRADO", teor="Saibam", selo="X",
                             lancado_em="2026", com_imovel=1))
    assert _fase(r, "doi")["pendencias"] == 1
    # sem a marca, e sem nada que diga que há imóvel, o acervo não vira cobrança
    velha = NF.fases_do_ato(_ato(tipo="ESCRITURA", situacao="LAVRADO", teor="Saibam"))
    assert _fase(velha, "doi")["pendencias"] == 0
    assert _fase(velha, "doi")["estado"] == NF.FEITA


def test_o_modelo_de_compra_e_venda_cobra_a_doi_em_lavratura():
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA", teor="x"), partes=[{"nome": "ANA"}],
                        modelo_com_imovel=True)
    assert _fase(r, "doi")["pendencias"] == 1
    assert r["inicial"] == "doi"


def test_a_doi_completa_fica_feita():
    r = NF.fases_do_ato(_ato(tipo="ESCRITURA", teor="x", com_imovel=1, doi_transacao=11,
                             doi_matricula="1234", valor_transacao=100))
    assert _fase(r, "doi")["estado"] == NF.FEITA
    assert _fase(r, "doi")["pendencias"] == 0


# ----------------------------------------------------------- onde a ficha abre

def test_o_ato_novo_abre_em_preparar():
    """O agente de minutas é o primeiro quadro: ordem do oficial de 23/10/2026."""
    assert NF.fases_do_ato(_ato())["inicial"] == "preparar"


def test_abre_na_primeira_fase_pendente():
    parte = {"nome": "ANA EXEMPLO"}
    assert NF.fases_do_ato(_ato(), partes=[parte], falta_qualificar=["ANA"])["inicial"] == "partes"
    assert NF.fases_do_ato(_ato(), partes=[parte])["inicial"] == "teor"
    assert NF.fases_do_ato(_ato(teor="x"), partes=[parte], pendencias=["[PRAZO]"])["inicial"] == "teor"
    assert NF.fases_do_ato(_ato(teor="x"), partes=[parte])["inicial"] == "lancar"
    assert NF.fases_do_ato(_ato(tipo="ESCRITURA", teor="x", com_imovel=1), partes=[parte])["inicial"] == "doi"
    assert NF.fases_do_ato(_ato(tipo="ESCRITURA", teor="x"), partes=[parte])["inicial"] == "lancar"


def test_o_ato_lancado_abre_na_entrega():
    assert NF.fases_do_ato(_ato(situacao="LAVRADO", teor="x"))["inicial"] == "entrega"


def test_o_foco_pedido_pela_tela_vale_se_a_fase_existe():
    assert NF.fases_do_ato(_ato(), foco="partes")["inicial"] == "partes"
    assert NF.fases_do_ato(_ato(), foco="doi")["inicial"] == "preparar"


# ----------------------------------------------------------- onde mora cada quadro

def test_o_que_se_preenche_antes_de_lancar_nao_mora_na_entrega():
    """A Entrega só abre depois do lançamento: lá, o ato anterior ficaria fora de alcance."""
    assert NF.lugar_dos_quadros({"situacao": "EM_LAVRATURA"}) == {
        "antes_de_lancar": "preparar", "selo": "lancar"}
    assert NF.lugar_dos_quadros({"situacao": "LAVRADO"}) == {
        "antes_de_lancar": "entrega", "selo": "entrega"}


# ----------------------------------------------------------- o que falta

def test_o_acervo_nao_vira_pendencia():
    """Só 1 dos 263 atos antigos tem selo anotado: cobrar seria o alarme que soa sempre."""
    velho = _ato(situacao="LAVRADO", teor="x", livro="3")
    assert NF.fases_do_ato(velho)["para_entregar"] == []
    novo = _ato(situacao="LAVRADO", teor="x", livro="31", lancado_em="2026-10-30")
    assert [i["ir"] for i in NF.fases_do_ato(novo)["para_entregar"]] == ["selo-do-ato"]


def test_a_comunicacao_em_aberto_aparece_na_entrega():
    r = NF.fases_do_ato(_ato(situacao="LAVRADO", teor="x", selo="X", lancado_em="2026"),
                        comunicacao={"aberta": True})
    assert [i["ir"] for i in r["para_entregar"]] == ["comunicacao-origem"]


def test_a_trava_do_servidor_aparece_sem_repetir_o_que_ja_foi_dito():
    r = NF.fases_do_ato(
        _ato(teor="x"), partes=[{"nome": "ANA"}], pendencias=["[PRAZO]"], falta_qualificar=["ANA: RG"],
        travas=["o texto tem campo em branco [PRAZO] — edite o teor",
                "cadastro incompleto — ANA: RG: complete no cartão da parte",
                "CENSEC: falta a natureza",
                "procuração sem OUTORGADO (procurador) no quadro «Partes» — inclua o procurador"])
    textos = [i["texto"] for i in r["para_lancar"]]
    assert sum("campo(s) em branco" in t for t in textos) == 1
    assert not any(t.startswith(("o texto tem", "cadastro incompleto")) for t in textos)
    assert "CENSEC: falta a natureza" in textos
    outorgado = next(i for i in r["para_lancar"] if "OUTORGADO" in i["texto"])
    assert outorgado["ir"] == "partes"


def test_o_arquivamento_obrigatorio_entra_no_que_falta():
    falta = NF.fases_do_ato(_ato(teor="x"), arquivamento={"obrigatorio": True, "contagem": {"anexos": 0}})
    assert any(i["ir"] == "documentos" and not i["feito"] for i in falta["para_lancar"])
    pronto = NF.fases_do_ato(_ato(teor="x"), arquivamento={
        "obrigatorio": True, "contagem": {"anexos": 1}, "confirmado": True})
    assert any("confirmadas" in i["texto"] and i["feito"] for i in pronto["para_lancar"])


def test_lancar_nao_tem_avancar_em_lavratura():
    """O botão de lançar é o último do formulário, por ordem de 07/10: a barra não o imita."""
    assert _fase(NF.fases_do_ato(_ato(teor="x")), "lancar")["avancar"] is None


# ----------------------------------------------------------- o que a ficha não pode perder

def _sem_comentarios(html: str) -> str:
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


def test_todo_quadro_da_ficha_diz_em_que_fase_mora():
    """Quadro sem fase ficaria à vista em toda fase. Os fixos estão aqui, com o motivo."""
    corpo = _sem_comentarios(FICHA[FICHA.index("{% block content %}"):])
    abertos = re.findall(r"<(?:section|details)\b[^>]*\bclass=\"panel[^\"]*\"[^>]*>", corpo)
    assert len(abertos) >= 15, "o varredor deixou de achar os quadros"
    sem_fase = [t for t in abertos if "data-fase" not in t]
    # o cabeçalho é o que identifica o ato, e «tornar sem efeito» vale em qualquer situação
    assert sem_fase == ['<section class="panel cg-ato-cabeca">', '<details class="panel">'], sem_fase


def test_a_fase_dos_quadros_existe_na_regua():
    possiveis = {"preparar", "partes", "documentos", "teor", "doi", "lancar", "entrega", "financeiro"}
    literais = set(re.findall(r'data-fase="([a-z]+)"', FICHA))
    assert literais <= possiveis, literais - possiveis
    assert {"preparar", "partes", "documentos", "teor", "doi", "lancar", "entrega", "financeiro"} == literais


def test_toda_fase_tem_endereco_na_pagina():
    """#teor abre direto: sem o alvo, a régua sem script não leva a lugar nenhum."""
    for chave in ("preparar", "partes", "documentos", "teor", "doi", "lancar", "entrega", "financeiro"):
        assert f'id="{chave}"' in FICHA, chave


def test_os_alvos_do_que_falta_existem():
    for alvo in ("selo-do-ato", "comunicacao-origem", "documentos"):
        assert f'id="{alvo}"' in FICHA, alvo


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    """A moldura, a régua e as barras só saem com `f`, e `f` só nasce no layout novo."""
    assert "{% set f = fases_da_ficha() if layout_novo else none %}" in FICHA
    for chamada in ("abre_ficha(VERSION)", "regua(f,", "travas_e_barras(f)"):
        linha = next(x for x in FICHA.splitlines() if chamada in x)
        assert "{% if f %}" in linha, linha
    assert "no fim desta página" in FICHA, "o aviso do layout antigo mudou"


def test_o_papel_na_doi_sai_da_procuracao_so_no_layout_novo():
    trecho = FICHA[FICHA.index('name="doi_lado"') - 400:FICHA.index('name="doi_lado"')]
    assert "{% if a.tipo == 'ESCRITURA' or not f %}" in trecho


def test_o_pdf_assinado_sai_uma_vez_em_cada_layout():
    assert FICHA.count("{{ guardar_pdf_assinado(a, csrf_token) }}") == 2
    assert "{% elif not f %}" in FICHA


def test_o_script_nao_monta_endereco_nem_html():
    """O CodeQL desta casa recusa endereço lido da página (PR #94): a régua usa âncoras."""
    codigo = re.sub(r"/\*.*?\*/", "", SCRIPT, flags=re.S)
    for proibido in ("innerHTML", "location.assign", "location.href", "new URL", "eval(", ".action"):
        assert proibido not in codigo, proibido


def test_a_guarda_da_fase_sobrevive_a_navegador_sem_armazenamento():
    """Janela privada pode recusar: a ficha abre na fase pendente, e não quebra."""
    for uso in re.finditer(r"sessionStorage\.\w+", SCRIPT):
        antes = SCRIPT[max(0, uso.start() - 120):uso.start()]
        assert "try" in antes, antes


def test_trava_e_barra_nascem_escondidas():
    """Sem script, a página sai inteira: a trava não pode tapar o quadro que explica."""
    assert re.search(r'data-cg-so-trava hidden', MACROS)
    assert re.search(r'data-cg-barra hidden', MACROS)

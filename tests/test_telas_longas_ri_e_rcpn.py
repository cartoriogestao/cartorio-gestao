"""As telas longas do Registro de Imóveis e do Registro Civil no layout novo: o que espera vem primeiro.

O QUE ELES DEFENDEM
    A prenotação, a DOI, a habilitação nova, as duas retificações novas e o manual da notificação eram
    telas de rolar. No layout novo o que espera ação e o botão principal ficam à vista, os formulários viram
    passos, e o histórico fica recolhido. Nada disso pode mudar regra nem perder campo, e quem continua no
    layout antigo tem de ver a tela de sempre.

    A armadilha dos passos é o campo obrigatório num passo escondido: o navegador recusa o envio e não tem
    onde pôr o cursor. Quem cuida disso é `static/fases.js`, e aqui se cobra que todo campo more num passo.

    A primeira parte monta os moldes de verdade sobre uma moldura vazia, e roda em qualquer máquina.
    A segunda usa o sistema de pé, e roda na máquina do balcão.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import jinja2
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _url(rota, **parametros):
    return f"/{rota}" + (f"?{urlencode(sorted(parametros.items()))}" if parametros else "")


_AMBIENTE = jinja2.Environment(autoescape=True, loader=jinja2.ChoiceLoader([
    jinja2.DictLoader({"base.html": "{% block heading %}{% endblock %}{% block content %}{% endblock %}"}),
    jinja2.FileSystemLoader(str(RAIZ / "templates"))]))
_AMBIENTE.filters["forte"] = lambda texto: texto
_AMBIENTE.globals["url_for"] = _url     # as macros importadas sem contexto também o procuram


def _montar(molde: str, **contexto) -> str:
    """O molde de verdade sobre uma moldura vazia: o que se confere aqui é o conteúdo da tela."""
    padrao = {"csrf_token": "t", "VERSION": "1", "fmt_date": str, "sv": {}}
    return _AMBIENTE.get_template(molde).render(**{**padrao, **contexto})


class _Leitor(HTMLParser):
    """Anota os formulários, em que passo mora cada campo, e se as caixas fecham na ordem."""

    CAIXAS = {"details", "summary", "section", "div", "form", "table", "nav", "label", "select"}

    def __init__(self):
        super().__init__()
        self.pilha, self.tortas, self.forms, self.passos = [], [], [], []
        self.navegacao, self.blocos, self.form = [], [], None

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if d.get("data-passo-ir"):
            self.navegacao.append(d["data-passo-ir"])
            assert d.get("type") == "button", "botão de passo que envia o formulário"
        if "data-passo" in d:
            self.blocos.append(d["data-passo"])
        if tag == "form":
            self.form = {"metodo": (d.get("method") or "get").lower(), "acao": (d.get("action") or "").split("#")[0],
                         "onsubmit": d.get("onsubmit") or "", "campos": []}
            self.forms.append(self.form)
        elif tag in ("input", "select", "textarea") and d.get("name") and self.form is not None:
            self.form["campos"].append({
                "nome": d["name"], "tipo": d.get("type") or tag, "valor": d.get("value") or "",
                "obrigatorio": "required" in d, "passo": self._passo_atual() or d.get("data-passo")})
        elif tag == "button" and self.form is not None and d.get("type") != "button":
            self.form["campos"].append({"nome": d.get("name") or "", "tipo": "enviar", "valor": d.get("value") or "",
                                        "obrigatorio": False, "passo": "fora", "acao": d.get("formaction") or ""})
        if tag in self.CAIXAS:
            self.pilha.append((tag, d.get("data-passo")))

    def _passo_atual(self):
        for _tag, passo in reversed(self.pilha):
            if passo:
                return passo
        return None

    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None
        if tag in self.CAIXAS and (not self.pilha or self.pilha.pop()[0] != tag):
            self.tortas.append(tag)


def _ler(html: str) -> _Leitor:
    leitor = _Leitor()
    leitor.feed(html)
    return leitor


def _formularios(html: str) -> Counter:
    """Cada formulário, com o que ele manda. O `passo` não entra: ele só diz onde o campo mora na tela."""
    fora = []
    for f in _ler(html).forms:
        campos = sorted(json.dumps({k: v for k, v in c.items() if k != "passo"}, sort_keys=True) for c in f["campos"])
        fora.append(json.dumps({**f, "campos": campos}, sort_keys=True))
    return Counter(fora)


def _posicoes_em_ordem(html: str, *trechos) -> bool:
    posicoes = [html.index(t) for t in trechos]
    return posicoes == sorted(posicoes)


# ---------------------------------------------------------------- a prenotação

def _r(numero, situacao="ABERTO", limite="2026-12-20", apresentante="Mario", suspenso=None):
    return {"id": numero, "numero": numero, "livro": "1A", "livro_destino": "2", "data_prenotacao": "2026-10-01",
            "data_limite": limite, "apresentante": apresentante, "objeto": f"objeto {numero}", "mid": None,
            "matricula_numero": None, "situacao": situacao, "prazo_suspenso_desde": suspenso}


def _nao_chame():
    raise AssertionError("o layout antigo não pode pagar a consulta do que espera ação")


def _protocolo(novo=True, rows=(), restam=None, espera=(), de_cx=None, busca="", situacao=""):
    return _montar(
        "ri_protocolo.html", layout_novo=novo, rows=list(rows), restam=restam or {},
        espera_acao=(lambda: list(espera)) if novo else _nao_chame, de_cx=de_cx, busca=busca, situacao=situacao,
        hoje="2026-10-30", prazo=20, prazo_reurb=40, NATUREZAS_SAUIN=["Hipoteca"],
        MOTIVOS_DA_GRATUIDADE_DO_RI=[{"texto": "t", "rotulo": "r", "fundamento": "f"}],
        resumo={"total": 3, "abertos": 2, "vencidos": 1, "sem_apresentante": 1})


VENCIDO, NO_PRAZO, ENCERRADO = _r(101, limite="2026-10-01"), _r(102), _r(103, situacao="ENCERRADO")
LISTA = {"rows": [ENCERRADO, NO_PRAZO, VENCIDO], "restam": {101: -3, 102: 15}, "espera": [VENCIDO]}
GERAL = {"id": 7, "numero": "2026.10.7", "interessado": "Beatriz", "interessado_documento": "00000000191",
         "telefone": "(00) 0000-0000", "email": "b@exemplo.invalid"}


def test_o_que_espera_vem_antes_do_prenotar_e_da_lista():
    html = _protocolo(**LISTA)
    assert _posicoes_em_ordem(html, 'id="espera"', 'id="prenotar"', 'id="em-aberto"', 'id="historico"', 'id="sobre"')


def test_a_lista_separa_o_que_esta_no_prazo_do_historico():
    html = _protocolo(**LISTA)
    espera = html[html.index('id="espera"'):html.index('id="prenotar"')]
    no_prazo = html[html.index('id="em-aberto"'):html.index('id="historico"')]
    historico = html[html.index('id="historico"'):html.index('id="sobre"')]
    assert "<strong>101</strong>" in espera and "<strong>102</strong>" not in espera
    assert "<strong>102</strong>" in no_prazo and "<strong>101</strong>" not in no_prazo
    assert "<strong>103</strong>" in historico and "<strong>102</strong>" not in historico
    assert "vencida há 3 dia(s) útil(eis)" in espera


def test_o_que_espera_nao_depende_da_lista_que_corta_em_300():
    """O título vencido mais velho que a lista alcança não pode sair da vista."""
    html = _protocolo(rows=[NO_PRAZO], restam={102: 15, 101: -3}, espera=[VENCIDO])
    assert "<strong>101</strong>" in html[html.index('id="espera"'):html.index('id="prenotar"')]


def test_os_quadros_da_lista_abrem_fechados():
    html = _protocolo(**LISTA)
    for quadro in ("em-aberto", "historico", "sobre"):
        assert re.search(rf'<details class="[^"]*" id="{quadro}">', html), quadro


def test_o_aviso_dos_importados_e_a_legenda_foram_para_o_historico():
    html = _protocolo(**LISTA)
    historico = html[html.index('id="historico"'):html.index('id="sobre"')]
    assert "protocolos importados" in historico and "Situações:" in historico
    assert "protocolos importados" not in html[:html.index('id="historico"')]


def test_a_explicacao_da_pagina_fica_no_quadro_dela():
    html = _protocolo(**LISTA)
    sobre = html[html.index('id="sobre"'):]
    assert "Não confunda com o livro de destino" in sobre and "Preencha quem apresentou" in sobre
    assert "Não confunda com o livro de destino" not in html[:html.index('id="sobre"')]


def test_com_a_busca_o_botao_de_prenotar_fica_no_alto_em_qualquer_largura():
    assert 'cg-pren-ir com-busca' in _protocolo(busca="10", **LISTA)
    assert 'cg-pren-ir com-busca' not in _protocolo(**LISTA)


def test_a_busca_traz_o_resultado_primeiro_e_sem_quadros():
    html = _protocolo(busca="10", **LISTA)
    assert _posicoes_em_ordem(html, 'id="resultado"', 'id="espera"', 'id="prenotar"')
    assert 'id="em-aberto"' not in html and 'id="historico"' not in html
    assert "O que a busca achou: <strong>3</strong>" in html
    assert "Limpar" in html and "Limpar" not in _protocolo(**LISTA)


def test_vindo_do_protocolo_geral_o_formulario_vem_antes_dos_prazos():
    com_geral = _protocolo(de_cx=GERAL, **LISTA)
    assert 'id="espera" style="order:2"' in com_geral
    assert 'id="espera" style="order:2"' not in _protocolo(**LISTA)
    assert 'name="cx_protocolo_id" value="7"' in com_geral and "protocolo geral 2026.10.7" in com_geral


def test_sem_nada_esperando_a_tela_diz_isso():
    html = _protocolo(rows=[NO_PRAZO], restam={102: 15})
    assert 'id="espera"' not in html and "Nenhum título com prazo vencido" in html
    assert 'class="cg-pren-duas com-espera"' not in html


@pytest.mark.parametrize("novo", [True, False])
def test_o_timbre_fica_nas_duas_molduras(novo):
    assert "CNS" in _protocolo(novo=novo, **LISTA)


def test_o_telefone_continua_conferido_e_abre_o_passo_dele():
    html = _protocolo(**LISTA)
    assert "Informe o telefone ou o e-mail" in html
    script = html[html.rindex("<script>"):]
    assert '"submit"' in script and '[data-passo-ir="quem"]' in script and "}, true);" in script
    assert "data-passo-ir" not in _protocolo(novo=False, **LISTA)


def test_o_vermelho_do_vencido_so_no_novo():
    assert 'class="stat danger"' in _protocolo(**LISTA)
    assert 'class="stat danger"' not in _protocolo(novo=False, **LISTA)


def test_no_antigo_a_ordem_continua_a_de_sempre():
    html = _protocolo(novo=False, **LISTA)
    assert _posicoes_em_ordem(html, "O que é esta página", "protocolos importados", "Prenotar novo título",
                              "Situações:", 'name="busca"', "Protocolos do livro")
    assert '<details class="panel" open>' in html
    assert 'id="espera"' not in html and 'id="prenotar"' not in html and "<style" not in html


# ---------------------------------------------------------------- a DOI

def _mes(competencia, vencida=True, tem_ato=False):
    return {"competencia": competencia, "tem_ato": tem_ato, "prazo": "2026-01-30", "vencida": vencida}


def _ato(n, entra=False, incluir=True):
    return {"ato": {"data_ato": "2026-09-01"}, "dados": {"operacao": "11"}, "rotulo": f"R-{n}/1", "entra": entra,
            "incluir": incluir, "problemas": [] if entra else [{"motivo": f"falta {n}"}]}


REMESSA = {"negativa": 0, "situacao": "GERADA", "arquivo_nome": "doi.json", "quantidade": 2, "gerado_em": "2026-10-01",
           "arquivo_hash": "abc", "recibo": "", "protocolo": "", "observacao": "", "competencia": "2026-09"}


def _doi(novo=True, em_aberto=(), linhas=(), remessa=None, remessas=(), prontas=0, resumo=(), entregue=False,
         competencia="2026-09", esquema=True):
    return _montar(
        "ri_doi.html", layout_novo=novo, em_aberto=list(em_aberto), linhas=list(linhas), remessa=remessa,
        remessas=list(remessas), prontas=prontas, resumo=list(resumo), entregue=entregue, competencia=competencia,
        esquema_conferido=esquema, prazo="2026-10-30", hoje="2026-10-30", cns="000000",
        meses=[{"c": "2026-09", "qtd": 2}], TIPO_OPERACAO={"11": "Compra e venda"})


CONFERENCIA = [{"declaracoes": 1, "campo": "ctp", "motivo": "falta o valor"}]
MESES_MUITOS = [_mes(f"2025-{m:02d}") for m in range(1, 13)] + [_mes("2026-09", vencida=False)]


def test_na_doi_os_meses_e_a_competencia_vem_antes_do_resto():
    html = _doi(em_aberto=MESES_MUITOS, linhas=[_ato(1), _ato(2, entra=True)], prontas=1, resumo=CONFERENCIA,
                remessas=[REMESSA])
    assert _posicoes_em_ordem(html, 'id="meses"', 'class="panel cg-doi-a-competencia"', "Gerar o arquivo", 'id="atos"',
                              'id="resolvidas"', 'id="sobre"')


def test_a_conferencia_continua_antes_de_gerar():
    html = _doi(linhas=[_ato(1), _ato(2, entra=True)], prontas=1, resumo=CONFERENCIA)
    assert _posicoes_em_ordem(html, "<th>O que falta</th>", "falta o valor", "tela da CTP", "Gerar o arquivo")


@pytest.mark.parametrize("quantos,aberto", [(1, True), (3, True), (4, False), (13, False)])
def test_poucos_meses_abrem_e_muitos_ficam_no_titulo(quantos, aberto):
    html = _doi(em_aberto=[_mes(f"2025-{m:02d}") for m in range(1, quantos + 1)])
    assert bool(re.search(r'id="meses" open>', html)) is aberto
    assert f"Meses que ainda devem satisfação: {quantos}" in html


def test_o_titulo_dos_meses_diz_quantos_venceram_e_quais_ainda_dao():
    html = _doi(em_aberto=MESES_MUITOS)
    titulo = html[html.index('id="meses"'):html.index("</summary>")]
    assert "12 com prazo vencido" in titulo and "Ainda no prazo" in titulo and "2026-09" in titulo


def test_no_novo_o_mes_mais_novo_vem_primeiro_e_no_antigo_o_mais_velho():
    novo = _doi(em_aberto=MESES_MUITOS)
    tabela = novo[novo.index("<thead><tr><th>Competência</th>"):]
    assert tabela.index(">2026-09<") < tabela.index(">2025-01<")
    antigo = _doi(novo=False, em_aberto=MESES_MUITOS)
    assert antigo.index(">2025-01<") < antigo.index(">2026-09<")


def test_registrar_o_mes_volta_ao_quadro_so_no_novo():
    assert '#meses"' in _doi(em_aberto=[_mes("2025-01")])
    assert "#meses" not in _doi(novo=False, em_aberto=[_mes("2025-01")])


def test_o_ato_parado_abre_o_quadro_e_vem_primeiro():
    html = _doi(linhas=[_ato(1, entra=True), _ato(2), _ato(3, incluir=False)])
    assert re.search(r'id="atos" open>', html) and "1 parado" in html
    tabela = html[html.index('id="atos"'):]
    assert tabela.index("R-2/1") < tabela.index("R-1/1") < tabela.index("R-3/1")


def test_sem_ato_parado_o_quadro_abre_fechado():
    assert re.search(r'id="atos">', _doi(linhas=[_ato(1, entra=True)], prontas=1))


def test_muitos_atos_parados_nao_empurram_a_tela():
    html = _doi(linhas=[_ato(n) for n in range(13)])
    assert re.search(r'id="atos">', html) and "13 parados" in html


def test_as_resolvidas_e_o_aviso_ficam_recolhidos():
    html = _doi(remessas=[REMESSA])
    assert re.search(r'id="resolvidas">', html) and re.search(r'id="sobre">', html)
    assert "Multa por Atraso" in html[html.index('id="sobre"'):]


def test_no_antigo_a_doi_continua_a_de_sempre():
    html = _doi(novo=False, em_aberto=[_mes("2025-01")], linhas=[_ato(1)], remessas=[REMESSA], resumo=CONFERENCIA)
    assert _posicoes_em_ordem(html, "Multa por Atraso", "Meses que ainda devem satisfação", "Ver a competência",
                              "falta o valor", "Atos da competência", "Competências já resolvidas")
    assert "<details" not in html and "<style" not in html and '<button class="primary">Ver a competência' in html


# ---------------------------------------------------------------- os três formulários

def _habilitacao(novo=True, v=None, rascunho_id=None, leitura=None):
    return _montar("rcpn_habilitacao_nova.html", layout_novo=novo, v=v or {}, rascunho_id=rascunho_id, hoje="2026-10-30",
                   leitura_origem=leitura, TIPOS={"CIVIL": "Casamento civil", "RELIGIOSO": "Religioso"},
                   REGIMES={"COMUNHAO_PARCIAL": "Comunhão parcial"})


def _retificacao_ri(novo=True):
    return _montar("ri_retificacao_nova.html", layout_novo=novo, matriculas=[{"id": 1, "numero": "10", "livro": "2"}],
                   especies={"GEO": "Georreferenciada"}, fundamentos={"213_I": "De ofício", "213_II": "A requerimento"})


def _retificacao_rcpn(novo=True):
    norma = SimpleNamespace(
        INSTITUTOS=[{"chave": "RETIFICACAO", "nome": "Retificação", "o_que": "corrigir", "artigo": "art. 1", "requisito": "r"},
                    {"chave": "SUPRIMENTO", "nome": "Suprimento", "o_que": "lançar", "artigo": "art. 2", "requisito": "r"}],
        FORMAS_DO_PEDIDO=[{"chave": "ESCRITO", "nome": "Escrito", "inciso": "I", "exige": ""},
                          {"chave": "VERBAL", "nome": "Verbal", "inciso": "III", "exige": "reduzir a termo"}],
        QUEM_ASSINA=("o próprio interessado", "procurador"), PRAZO_DECISAO_DIAS_UTEIS=10)
    return _montar("rcpn_retificacao_nova.html", layout_novo=novo, norma=norma)


LEITURA = {"id": 5, "arquivos": [], "conferencia": [{"gravidade": "ATENÇÃO", "texto": "não fecha", "onde": "nome"}],
           "registro": {}}
PASSOS = {
    "prenotacao": (lambda novo=True: _protocolo(novo=novo, **LISTA), "form-prenotar", ["quem", "titulo"], "Prenotar"),
    "habilitacao": (_habilitacao, "form-do-ato", ["casamento", "nubentes"], "Abrir habilitação"),
    "retificacao_ri": (_retificacao_ri, "form-do-ato", ["processo", "pessoas", "area"], "Autuar o processo"),
    "retificacao_rcpn": (_retificacao_rcpn, "form-do-ato", ["qual", "como", "quem"], "Abrir o processo"),
}


def _o_formulario(html, form_id):
    """O formulário dos passos: é o que tem mais campos, e não o do rascunho nem o da leitura."""
    assert f'data-cg-passos="{form_id}"' in html
    leitor = _ler(html)
    return leitor, max(leitor.forms, key=lambda f: len(f["campos"]))


@pytest.mark.parametrize("tela", sorted(PASSOS))
def test_cada_passo_da_navegacao_tem_o_seu_bloco(tela):
    montar, form_id, passos, _botao = PASSOS[tela]
    leitor, _form = _o_formulario(montar(), form_id)
    assert leitor.navegacao == passos
    assert set(leitor.blocos) == set(passos)


@pytest.mark.parametrize("tela", sorted(PASSOS))
def test_todo_campo_que_se_ve_mora_num_passo(tela):
    """Campo fora de passo ficaria à vista em todos, e o desenho da tela diria outra coisa."""
    montar, form_id, passos, _botao = PASSOS[tela]
    _leitor, form = _o_formulario(montar(), form_id)
    soltos = [c["nome"] for c in form["campos"] if c["tipo"] not in ("hidden", "enviar") and c["passo"] not in passos]
    assert not soltos, soltos


@pytest.mark.parametrize("tela", sorted(PASSOS))
def test_o_botao_de_gravar_e_um_so_e_mora_no_ultimo_passo(tela):
    montar, form_id, passos, botao = PASSOS[tela]
    html = montar()
    _leitor, form = _o_formulario(html, form_id)
    assert len([c for c in form["campos"] if c["tipo"] == "enviar"]) == 1
    assert re.search(rf'<button[^>]*data-passo="{passos[-1]}"[^>]*>{botao}</button>', html)


@pytest.mark.parametrize("tela", sorted(PASSOS))
def test_sem_o_script_a_barra_nao_esconde_o_botao_de_gravar(tela):
    """Sem JavaScript a página sai inteira: a barra fica de pé, e só o avançar e o voltar nascem escondidos."""
    montar, *_resto = PASSOS[tela]
    html = montar()
    barra = html[html.index("data-cg-passos-fim"):]
    assert "data-cg-passos-fim hidden" not in html
    assert "data-passo-voltar hidden" in barra and "data-passo-avancar hidden" in barra


@pytest.mark.parametrize("tela", sorted(PASSOS))
def test_o_script_dos_passos_so_vem_no_novo(tela):
    montar, *_resto = PASSOS[tela]
    assert "fases.js" in montar() and "data-cg-passos=" in montar()
    assert "fases.js" not in montar(False) and "data-cg-passos=" not in montar(False)


@pytest.mark.parametrize("tela", ["habilitacao", "retificacao_ri", "retificacao_rcpn"])
def test_os_botoes_do_rascunho_ficam_fora_dos_passos(tela):
    montar, _form_id, _passos, _botao = PASSOS[tela]
    html = montar()
    assert _posicoes_em_ordem(html, "data-rascunho", "Salvar rascunho", "Não termina hoje", "data-cg-passos=")


def test_o_que_nao_termina_hoje_vai_para_a_rota_certa():
    assert 'formaction="/rascunho_salvar_e_abrir_processo"' in _retificacao_rcpn()


def test_a_habilitacao_mantem_os_nubentes_lado_a_lado_no_mesmo_passo():
    _leitor, form = _o_formulario(_habilitacao(), "form-do-ato")
    passos = {c["nome"]: c["passo"] for c in form["campos"]}
    assert passos["nubente1_nome"] == passos["nubente2_nome"] == "nubentes"
    assert passos["observacao"] == passos["regime"] == "casamento"
    assert '<div class="grid2" data-passo="nubentes">' in _habilitacao()


def test_a_observacao_mora_em_um_lugar_so():
    assert _habilitacao().count('name="observacao"') == 1
    assert _habilitacao(novo=False).count('name="observacao"') == 1


def test_a_habilitacao_volta_com_o_rascunho_e_com_a_leitura():
    html = _habilitacao(v={"observacao": "guardada", "nubente2_nome": "Ana Exemplo"}, rascunho_id=9)
    assert ">guardada</textarea>" in html and 'value="Ana Exemplo"' in html
    assert 'name="_rascunho_id" value="9"' in html and "Aberto do rascunho #9" in html
    com_leitura = _habilitacao(leitura=LEITURA, rascunho_id=9)
    assert "não fecha" in com_leitura and 'name="leitura_id" value="5"' in com_leitura
    assert _posicoes_em_ordem(com_leitura, "não fecha", "data-cg-passos=")


def test_juntar_os_documentos_continua_antes_dos_passos():
    assert _posicoes_em_ordem(_habilitacao(), 'id="juntar-anexos"', "data-cg-passos=")


def test_o_aviso_dos_fundamentos_mora_no_passo_em_que_se_escolhe():
    html = _retificacao_ri()
    assert _posicoes_em_ordem(html, 'data-passo="processo"', "fundamentos do art. 213", 'name="fundamento"',
                              'data-passo="pessoas"')
    assert html.count("fundamentos do art. 213") == 1
    assert _posicoes_em_ordem(_retificacao_ri(False), "fundamentos do art. 213", "Salvar rascunho", 'name="numero"')


def test_cancelar_continua_nas_duas_molduras():
    assert '<a class="button secondary cg-ret-cancelar" href="/ri_retificacoes">Cancelar</a>' in _retificacao_ri()
    assert '<a class="button secondary" href="/ri_retificacoes">Cancelar</a>' in _retificacao_ri(False)


# ---------------------------------------------------------------- o manual

def _manual(novo=True):
    return _montar(
        "usucapiao_manual.html", layout_novo=novo, base={"o_que": "a base", "artigo": "art. 754"},
        manual=[{"passo": n, "o_que": f"passo {n}", "como": f"como {n}", "base": "art. 1"} for n in range(1, 4)],
        formas=[{"forma": "PESSOAL", "o_que": "em mãos", "artigo": "art. 598"}, {"forma": "EDITAL", "o_que": "por edital", "artigo": "art. 598"}],
        onde={"o_que": "no endereço", "artigo": "art. 598"}, silencio={"o_que": "concordância", "base": "art. 216"},
        prazos=[{"de_quem": "CONFRONTANTE", "dias": 15, "uteis": True, "o_que": "impugnar", "procedencia": "m", "base": "art. 599"},
                {"de_quem": "TITULAR", "dias": 15, "uteis": False, "o_que": "consentir", "procedencia": "c", "base": "Lei 6.015"}],
        medido="m", citado="c")


def _texto(html: str) -> str:
    sem_estilo = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    sem_comentario = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sem_estilo))
    return sem_comentario.strip()


def test_o_manual_nao_recolhe_nada_e_diz_as_mesmas_palavras():
    novo = _manual()
    assert "<details" not in novo
    assert _texto(novo) == _texto(_manual(False))


def test_no_antigo_o_manual_nao_ganha_estilo_nem_colunas():
    antigo = _manual(False)
    assert "<style" not in antigo and "cg-man" not in antigo


# ---------------------------------------------------------------- as telas juntas

TELAS = {
    "protocolo": lambda novo: _protocolo(novo=novo, **LISTA),
    "protocolo_vazio": lambda novo: _protocolo(novo=novo),
    "protocolo_busca": lambda novo: _protocolo(novo=novo, busca="10", **LISTA),
    "protocolo_geral": lambda novo: _protocolo(novo=novo, de_cx=GERAL, **LISTA),
    "doi_gerar": lambda novo: _doi(novo=novo, em_aberto=MESES_MUITOS, linhas=[_ato(1), _ato(2, entra=True)], prontas=1,
                                   resumo=CONFERENCIA, remessas=[REMESSA]),
    "doi_recibo": lambda novo: _doi(novo=novo, em_aberto=[_mes("2025-01")], linhas=[_ato(1, entra=True)], prontas=1,
                                    remessa=REMESSA, remessas=[REMESSA]),
    "doi_sem_ato": lambda novo: _doi(novo=novo, em_aberto=[_mes("2025-01", tem_ato=True)]),
    "doi_entregue": lambda novo: _doi(novo=novo, entregue=True, remessa=dict(REMESSA, situacao="ENTREGUE", recibo="R-1")),
    "doi_negativa": lambda novo: _doi(novo=novo, entregue=True, remessa=dict(REMESSA, negativa=1, arquivo_nome="")),
    "doi_sem_conferir": lambda novo: _doi(novo=novo, esquema=False),
    "habilitacao": lambda novo: _habilitacao(novo=novo),
    "habilitacao_rascunho": lambda novo: _habilitacao(novo=novo, v={"observacao": "x", "nubente1_sexo": "F"}, rascunho_id=9),
    "habilitacao_leitura": lambda novo: _habilitacao(novo=novo, leitura=LEITURA, rascunho_id=9),
    "retificacao_ri": _retificacao_ri,
    "retificacao_rcpn": _retificacao_rcpn,
    "manual": _manual,
}


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_os_dois_layouts_mandam_os_mesmos_formularios(tela):
    """Reordenar é só no novo. Campo que some de um layout é dado que deixa de chegar à rota."""
    novo, antigo = _formularios(TELAS[tela](True)), _formularios(TELAS[tela](False))
    assert novo == antigo, (sorted((novo - antigo).elements()), sorted((antigo - novo).elements()))


@pytest.mark.parametrize("tela", sorted(TELAS))
@pytest.mark.parametrize("novo", [True, False])
def test_as_caixas_fecham_na_ordem(tela, novo):
    leitor = _ler(TELAS[tela](novo))
    assert not leitor.pilha and not leitor.tortas, (leitor.pilha, leitor.tortas)


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_no_antigo_nao_sobra_nada_do_novo(tela):
    html = TELAS[tela](False)
    assert "<style" not in html and "cg-" not in html and "data-passo-ir" not in html


@pytest.mark.parametrize("molde", ["ri_protocolo.html", "ri_doi.html", "rcpn_habilitacao_nova.html",
                                   "ri_retificacao_nova.html", "rcpn_retificacao_nova.html", "usucapiao_manual.html"])
def test_o_estilo_so_entra_no_novo(molde):
    fonte = (RAIZ / "templates" / molde).read_text(encoding="utf-8")
    assert fonte.count("<style>") == 1
    assert "{% if layout_novo %}\n<style>" in fonte.replace("\r\n", "\n")
    # Uma contrabarra comida no caminho vira caractere de controle dentro do estilo, e a tela mostra lixo.
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", fonte)


def test_a_consulta_do_que_espera_so_le_e_vai_para_o_molde():
    fonte = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    corpo = fonte[fonte.index("def espera_acao():"):fonte.index("espera_acao=espera_acao")]
    assert "INSERT" not in corpo and "UPDATE" not in corpo and "DELETE" not in corpo and "transaction" not in corpo
    assert "SÓ LÊ" in corpo


# ------------------------------------------------------------- com o sistema de pé

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str = "ADMIN"):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


CAMINHOS_DO_BALCAO = ["/registro-imoveis/protocolo", "/registro-imoveis/protocolo?busca=1", "/rcpn/habilitacoes/nova",
                      "/registro-imoveis/retificacoes/nova", "/rcpn/retificacoes/nova", "/usucapiao/notificacao/manual"]
CAMINHOS_DA_DOI = ["/registro-imoveis/doi", "/registro-imoveis/doi?competencia=2026-05"]


@pytest.mark.parametrize("papel,caminho", [("ADMIN", c) for c in (*CAMINHOS_DO_BALCAO, *CAMINHOS_DA_DOI)]
                         + [("USER", c) for c in CAMINHOS_DO_BALCAO]
                         + [("AUDITOR", c) for c in (*CAMINHOS_DA_DOI, "/registro-imoveis/protocolo")])
def test_a_tela_abre_nos_dois_layouts(cg_app, papel, caminho):
    """Cada papel só nas telas que ele já abria: o balcão não abre a DOI, e o auditor não abre os formulários."""
    c = _entrar(cg_app, f"ri_rcpn_{papel.lower()}", papel)
    for qual in ("novo", "antigo"):
        _layout(c, qual)
        assert c.get(caminho).status_code == 200, (caminho, papel, qual)


def test_na_tela_de_pe_o_vencido_aparece_mesmo_com_o_filtro_so_no_novo(cg_app):
    from bd_nativo import banco

    d = cg_app.extensions["db"]
    with d.transaction() as con:
        banco(con).escrever(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, apresentante, data_limite, situacao, criado_em)
               VALUES (88001, '1A', '2020-01-01', 'Beatriz', '2020-01-30', 'ABERTO', '2020-01-01T10:00:00')""")
    c = _entrar(cg_app, "ri_rcpn_espera")
    _layout(c, "novo")
    html = c.get("/registro-imoveis/protocolo?busca=nada-acha-isto").get_data(as_text=True)
    assert "<strong>88001</strong>" in html[html.index('id="espera"'):html.index('id="prenotar"')]
    _layout(c, "antigo")
    html = c.get("/registro-imoveis/protocolo?busca=nada-acha-isto").get_data(as_text=True)
    assert 'id="espera"' not in html and "<strong>88001</strong>" not in html

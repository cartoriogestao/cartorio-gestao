"""Relato #108 - painel / com overflow horizontal (impressao a5746009ec77de86).

Mario pediu layout fixo no painel geral: tudo cabendo na tela, sem arrastar
para a direita para ver o fim das tabelas.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "app.css"
DASH = RAIZ / "templates" / "dashboard.html"


def test_o_main_da_reforma_nao_perde_min_width():
    css = CSS.read_text(encoding="utf-8")
    # 13/10/2026: o CSS trocou os 300px fixos pela variável da largura do menu
    # (`--sidebar-width`). O que este teste guarda é o `min-width:0` da regra que
    # empurra o conteúdo para o lado do menu — e ele continua lá.
    assert ".main{margin-left:var(--sidebar-width);min-width:0;width:calc(100% - var(--sidebar-width))}" in css


def test_a_grade_do_painel_deixa_encolher_as_colunas():
    css = CSS.read_text(encoding="utf-8")
    assert ".grid2>*{min-width:0}" in css


def test_as_tabelas_do_painel_usam_table_wrap():
    html = DASH.read_text(encoding="utf-8")
    # 4 DESDE 06/10/2026: o quadro «Erros abertos de quem praticou» (só para o
    # ADMIN) é a quarta tabela do painel — e também vem na moldura.
    # 3 DESDE 13/10/2026: o quadro «Expedientes em andamento» saiu do painel por
    # ordem do oficial (substituído por Processos). Ficam processos, atos e erros.
    # 1 DESDE 12/11/2026: na «folha do dia» os processos e os atos deixaram de
    # ser tabela — são linhas em grade, que encolhem e empilham sozinhas
    # (`minmax(0,1fr)`), sem nada para arrastar. Só os erros continuam tabela.
    assert html.count('class="table-wrap"') == 1
    assert "<table" not in html.replace('<div class="table-wrap"><table>', "")


def test_as_linhas_da_folha_deixam_encolher_a_coluna_do_texto():
    css = CSS.read_text(encoding="utf-8")
    assert ".fd-lin{display:grid;grid-template-columns:54px minmax(0,1fr) 112px 128px" in css
    assert ".fd-corpo{display:grid;grid-template-columns:minmax(0,1fr) 290px" in css
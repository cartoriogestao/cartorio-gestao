"""O CABEÇALHO DE TABELA GRUDAVA NA JANELA EM 99 TELAS.

Achado em 02/09/2026, medindo o relato #41 do oficial — *«fica aparecendo umas
letras estranhas no fundo (…) quando seleciono um campo em certidões e rolo a
página»*, com um print que mostra uma faixa de texto repetido atravessando a
tela.

**O TEXTO NÃO VEM DO SERVIDOR** — medido: o HTML de `/rcpn/certidoes` não o
contém, em nenhuma forma. Ele nasce no navegador, ao compor a página.

**E HAVIA UM DEFEITO NOSSO DE COMPOSIÇÃO, INDEPENDENTE DISSO.** O CSS aplicava
`th { position: sticky; top: 0 }` a **toda tabela do sistema**, e
`position: sticky` precisa de um contêiner que role para se apoiar. O contêiner
é `.table-wrap` (`overflow:auto; max-height:68vh`) — e **99 das telas têm
`<table>` sem ele**. Nessas, o cabeçalho não se apoia na tabela: **apoia-se na
janela**, e ao rolar ele flutua sobre o conteúdo, disputando lugar com a
`.topbar`, que também é sticky.

**Cabeçalho sticky sem contêiner é repintura a cada quadro de rolagem** — a
mesma família de defeito que produz arraste de pixels em tela remota e em
composição acelerada.

**O QUE ESTE TESTE NÃO AFIRMA:** que era isto que o oficial via. Não
reproduzi o artefato dele — ele acessa por AnyDesk, de outra máquina, e essa
metade continua em aberto. **Este é um defeito real, medido e consertado; se
ele é O defeito, ainda não se sabe.**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CSS = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
TELAS = sorted((RAIZ / "templates").glob("*.html"))


def test_o_cabecalho_so_gruda_dentro_do_que_rola():
    """`position: sticky` sem contêiner de rolagem apoia-se na JANELA."""
    assert ".table-wrap th{position:sticky" in CSS, (
        "o cabeçalho sticky saiu de dentro do `.table-wrap` — sem o contêiner "
        "ele volta a grudar na janela, em 99 telas")
    # e a regra solta, que valia para TODA tabela, não pode voltar
    for m in re.finditer(r"(^|[};])\s*th\s*\{([^}]*)\}", CSS):
        corpo = m.group(2)
        assert "position:sticky" not in corpo.replace(" ", ""), (
            "voltou um `th { position: sticky }` que vale para toda tabela do "
            "sistema — ele precisa do `.table-wrap` para se apoiar")


def test_o_contentor_que_rola_continua_existindo():
    """Sem ele, a regra nova não gruda coisa nenhuma — e as tabelas longas
    perderiam o cabeçalho ao rolar, que é o motivo de ele existir."""
    assert ".table-wrap{overflow:auto" in CSS.replace(" ", "")


def test_o_cabecalho_grudado_fica_ABAIXO_da_barra_do_topo():
    """**Dois elementos sticky na mesma tela disputam lugar.** A `.topbar` tem
    `z-index:5`; o cabeçalho da tabela recebeu `z-index:1` para passar por cima
    do corpo da tabela e por baixo da barra — sem número, a ordem dependia da
    posição no documento, e mudava de tela para tela."""
    m = re.search(r"\.table-wrap th\{([^}]*)\}", CSS)
    assert m, "a regra do cabeçalho sumiu"
    assert "z-index:1" in m.group(1).replace(" ", "")
    barra = re.search(r"\.topbar\{([^}]*)\}", CSS)
    assert barra and "z-index:5" in barra.group(1).replace(" ", "")


def test_a_impressao_continua_desgrudando_o_cabecalho():
    """No papel não há rolagem, e cabeçalho grudado imprime repetido."""
    impressao = CSS[CSS.find("@media print"):]
    assert "th{position:static}" in impressao.replace(" ", ""), (
        "a regra de impressão perdeu o `position:static` do cabeçalho")


def test_quantas_telas_dependiam_da_regra_solta():
    """**O tamanho do que estava errado, medido e guardado.**

    Se um dia quase toda tela passar a usar `.table-wrap`, esta conta cai — e
    aí a regra solta poderia voltar sem estrago. Enquanto a maioria não usa,
    ela não pode.
    """
    sem_contentor = 0
    for tela in TELAS:
        texto = tela.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"<table", texto):
            if "table-wrap" not in texto[max(0, m.start() - 400):m.start()]:
                sem_contentor += 1
                break
    assert sem_contentor >= 50, (
        f"só {sem_contentor} telas têm tabela sem contêiner de rolagem — se "
        f"esse número caiu muito, releia se a regra ainda precisa ser "
        f"restrita (eram 99 em 02/09/2026)")

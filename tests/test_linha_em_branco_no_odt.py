"""
`<p></p>` E UMA LINHA EM BRANCO, E ELA SUMIA NOS `.odt` DESTA CASA.

COMO APARECEU
    Medindo o relato #27 do oficial — «precisa de mais espaco livre para
    desenvolver a assinatura». Aumentei o espaco da ficha do cartao de tres
    linhas em branco para cinco, e o teste continuou dizendo ZERO.

    Nao era o teste: **as tres nunca tinham chegado ao papel**. O conversor
    `ri_odt.html_para_odf` descartava todo paragrafo cujo texto ficasse vazio
    depois do `.strip()`, e a linha de assinar saia colada no rotulo — que e
    exatamente a queixa dele.

O TAMANHO DISSO
    Sao **80 ocorrencias de `<p></p>` em sete modulos** que geram `.odt`:
    notas_web (30), atribuicoes_web (17), habilitacao_web (13), ri_odt (11),
    caixa_web (4), nucleo_web (3) e ri_web (2). Toda linha em branco que um
    autor escreveu nesses papeis foi jogada fora, sem aviso nenhum.

O QUE ESTES TESTES GUARDAM
      - o paragrafo vazio SAI;
      - `</div>` NAO vira linha em branco — a marca e o fecho de `</p>`, e so
        dele. Sem essa precisao, `<div><p>a</p></div>` ganharia um branco que
        ninguem pediu, porque ali o `</div>` chega com o buffer ja esvaziado
        pelo `</p>`;
      - o alinhamento centralizado nao escorrega para o paragrafo seguinte;
      - e a ficha do cartao — que foi quem denunciou — tem o espaco de
        verdade.

POR QUE ISTO E UM TESTE, E NAO SO UM CONSERTO
    Ninguem olha o XML de dentro do `.odt`; olha-se o papel impresso, e no
    papel «faltam duas linhas em branco» nao grita. Foi preciso um teste que
    medisse ESPACO — e o primeiro que escrevi tambem nao servia, porque lia o
    texto com `" ".join(...split())`, que colapsa justamente o branco que se
    queria medir. **O branco e o conteudo aqui, e tem de sobreviver a
    leitura.**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_odt


def paragrafos(html: str) -> list[str]:
    """Os parágrafos do ODF, na ordem — o vazio conta como um item."""
    odf = ri_odt.html_para_odf(html)
    return re.findall(r"<text:p[^>]*/>|<text:p[^>]*>.*?</text:p>", odf)


def quantos(html: str) -> int:
    return len(paragrafos(html))


# ------------------------------------------------- o parágrafo vazio sai


def test_o_paragrafo_vazio_vira_linha_em_branco():
    assert quantos("<p>a</p><p></p><p>b</p>") == 3


def test_dois_vazios_seguidos_dao_duas_linhas():
    """Quem escreve `<p></p><p></p>` quer duas linhas, e não uma."""
    assert quantos("<p>a</p><p></p><p></p><p>b</p>") == 4


def test_o_vazio_nao_leva_estilo():
    """`P-just` justificaria o nada e `P-centro` o centraria. O que se quer
    ali é altura de linha."""
    p = paragrafos("<p>a</p><p></p>")
    assert p[-1] == "<text:p/>"


# ----------------------------------------- e o que NÃO pode virar branco


def test_div_que_fecha_NAO_vira_linha_em_branco():
    """A marca é o fecho de `</p>`, e só dele.

    Em `<div><p>a</p></div>` o `</div>` chega com o buffer já esvaziado pelo
    `</p>`: tratar todo bloco igual poria ali um branco que ninguém pediu — e
    o teor das matrículas do acervo vem cheio de `div`.
    """
    assert quantos("<div><p>a</p></div>") == 1


def test_div_vazia_nao_vira_linha_em_branco():
    assert quantos("<div></div><p>a</p>") == 1


def test_o_centro_nao_escorrega_para_o_paragrafo_seguinte():
    """`_centro` é estado, e estado que não se limpa contamina o vizinho —
    a linha em branco entre dois parágrafos faria o segundo nascer
    centralizado."""
    p = paragrafos('<p align="center">a</p><p></p><p>b</p>')
    assert "P-centro" in p[0]
    assert "P-just" in p[2]


# -------------------------------------- e a ficha, que foi quem denunciou


def test_a_ficha_do_cartao_tem_o_espaco_que_o_codigo_escreve():
    """O caso que achou tudo isto. O corpo da ficha põe cinco linhas em
    branco entre o rótulo do autógrafo e a linha de assinar; antes de
    31/08/2026 saíam zero."""
    corpo = ('<p><b>Assinatura por extenso</b> (como assina)</p>'
             '<p></p><p></p><p></p><p></p><p></p>'
             '<p>_________________________</p>')
    p = paragrafos(corpo)
    vazios = [x for x in p if x == "<text:p/>"]
    assert len(vazios) == 5


# ------------------- e o `<p>` do E-Ofício continua sendo limpado


def test_o_paragrafo_vazio_COM_ATRIBUTO_continua_sumindo():
    """A LINHA É O `<p></p>` DA CASA, E NÃO TODO PARÁGRAFO VAZIO.

    Medido na produção em 31/08/2026, antes de decidir: se todo parágrafo
    vazio virasse linha, **1.057 das 1.508 matrículas** ganhariam linha em
    branco — 1.757 ao todo, pior caso 15 numa ficha, 11,8% de crescimento
    médio. E elas não são `<p></p>`: são
    `<p lang="pt-BR" style="text-align:justify;...">`, a exportação do editor
    do E-Ofício, que é exatamente o caso para o qual a limpeza do conversor
    foi feita.

    **Se o E-Ofício desenhava aquilo como linha em branco, repô-las é
    reproduzir o livro** — que é o que uma certidão de inteiro teor faz. Se
    eram sobra do editor, é esticar 1.057 certidões sem motivo. Não dá para
    medir: das 369 certidões do acervo, uma só guarda o corpo.

    Então o conserto ficou no que é inequívoco, e a outra metade é pergunta
    para o oficial. **Mudar a cara de 1.057 papéis que a serventia assina,
    calado e por suposição, é o contrário do que esta casa faz.**
    """
    html = ('<p>a</p>'
            '<p lang="pt-BR" style="text-align:justify;text-indent:0pt"></p>'
            '<p>b</p>')
    assert quantos(html) == 2


def test_paragrafo_vazio_centralizado_tambem_continua_sumindo():
    """`<p align="center"></p>` tem atributo: é do editor, e não da casa."""
    assert quantos('<p>a</p><p align="center"></p><p>b</p>') == 2


def test_a_producao_nao_ganha_uma_linha_sequer():
    """O par do teste de cima, medido no conversor e não na regex.

    Antes do conserto o conversor produzia ZERO parágrafos vazios — logo o
    que ele produzir agora **é** o crescimento. Este teste monta o teor na
    forma que o E-Ofício exportou e exige zero.
    """
    teor = "".join(
        f'<p lang="pt-BR" style="text-align:justify;text-indent:0pt;'
        f'margin-left:0pt"></p><p lang="pt-BR">linha {i}</p>'
        for i in range(20))
    p = paragrafos(teor)
    assert [x for x in p if x == "<text:p/>"] == []

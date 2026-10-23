"""LIMPEZA DO TEOR QUE VEIO DO ACERVO — só calcula, não grava nada.

    «o teor da averbacao e da ficha da 3110 segue cheio de espacos, um modelo
     que diz conferencia, nada como preparado antes» — o oficial, 15/09/2026

O QUE ESTÁ NO TEOR DA 3.110, medido linha a linha antes de escrever isto:

    1  'conferida'                          ← palavra solta, do mutirão de conferência
    2  'MATRICULA: 3.110 '                  ← a ficha já imprime isso no cabeçalho
    3  'LIVRO: 2-Q fls. 168'                ← idem
    4  'DATA: 13-08-2009'                   ← idem
    5  ''
    6  'IMÓVEL: UMA GLEBA DE TERRAS…'       ← o teor de verdade começa aqui
    7  'R-1/3.110: …'
    8  '.-.-.-.-.-.-.-.-…'  (121 caracteres) ← separador do E-Ofício
    …

    Mais **quatro** trechos com espaço duplicado dentro do texto:
    `n°9428).   DATA:`, `n°15528462000-0/SSP/MA  e`, `Fontanela  -`,
    `Oficiala.   `.

O QUE ESTE MÓDULO TIRA, E O QUE ELE NÃO ENCOSTA
    Tira: a palavra de conferência solta, o cabeçalho repetido, os separadores
    de pontilhado e o espaço em excesso **entre palavras**.

    **Não encosta no texto do ato.** Não reescreve frase, não corrige
    ortografia, não mexe em número, nome, data nem valor — o teor é o que está
    escrito no livro. O que sai daqui é ruído de importação, e nada mais.

    **E não grava.** Quem grava é `tools/limpar_teor_do_acervo.py`, com
    `--confirmar`, depois de o oficial aprovar o texto.

POR QUE O CABEÇALHO REPETIDO SAI
    A ficha em papel já imprime «MATRÍCULA Nº», «LIVRO» e a data no alto de
    cada folha, do cadastro — e o mesmo texto dentro do teor aparece de novo,
    dois centímetros abaixo. É a mesma razão pela qual o termo do Registro
    Civil não repete livro e folha: repetir cria uma segunda fonte para
    divergir da primeira.
"""
from __future__ import annotations

import re

# A palavra que o mutirão de conferência do E-Ofício deixava na primeira linha.
# Só sai quando está **sozinha** na linha: «conferida» no meio de uma frase do
# ato é palavra do ato.
CONFERENCIA = re.compile(r"^\s*confer(?:ida|ido|encia|ência)\s*$", re.IGNORECASE)

# `MATRICULA: 3.110`, `LIVRO: 2-Q fls. 168`, `DATA: 13-08-2009` — o cabeçalho
# que a ficha já imprime. Só sai nas primeiras linhas: um `DATA:` no meio do
# teor é data de ato.
CABECALHO = re.compile(
    r"^\s*(matr[ií]cula|livro|data|ficha)\s*[:nº°]*\s*[\w\.\-/ ]{0,40}\s*$",
    re.IGNORECASE)

# `.-.-.-.-.-…` e `______…` — os separadores que o E-Ofício desenhava entre
# atos. O sistema desenha a linha de verdade (`ri_odt.separar_atos`), então o
# pontilhado vira sujeira dupla.
SEPARADOR = re.compile(r"^[\s\.\-_=~\*]{12,}$")

# Quantas linhas do começo podem ser cabeçalho. Medido: na 3.110 são três
# (linhas 2 a 4). Seis dá folga para ficha que traga «FICHA Nº» ou a comarca,
# sem alcançar o corpo — a linha 6 já é o `IMÓVEL:`.
LINHAS_DE_CABECALHO = 6


def _sem_espaco_dobrado(linha: str) -> str:
    """Espaço repetido **entre palavras** vira um só. Não toca no recuo.

    O recuo do começo da linha fica: em teor de acervo ele às vezes é o que
    separa um bloco do outro, e tirá-lo mudaria a cara do texto sem pedido.
    """
    recuo = len(linha) - len(linha.lstrip(" "))
    return " " * recuo + re.sub(r"[ \t]{2,}", " ", linha.strip())


def limpar(teor: str | None) -> str:
    """Devolve o teor sem o ruído da importação. SÓ CALCULA."""
    if not teor:
        return ""
    linhas = str(teor).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    saida: list[str] = []
    vistas_de_verdade = 0
    for i, linha in enumerate(linhas):
        if SEPARADOR.match(linha):
            continue
        if CONFERENCIA.match(linha):
            continue
        # O cabeçalho só se tira antes de o corpo começar.
        if vistas_de_verdade == 0 and i < LINHAS_DE_CABECALHO \
                and CABECALHO.match(linha):
            continue
        if linha.strip():
            vistas_de_verdade += 1
        saida.append(_sem_espaco_dobrado(linha))

    # Linha em branco repetida vira uma só, e as das pontas somem.
    texto = "\n".join(saida)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def o_que_sai(teor: str | None) -> list[tuple[int, str, str]]:
    """As linhas que a limpeza tira, com o motivo. SÓ LÊ.

    Existe para a tela mostrar o que vai sumir **antes** de gravar: teor é o
    que está escrito no livro, e ninguém aprova o que não viu.
    """
    if not teor:
        return []
    linhas = str(teor).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fora: list[tuple[int, str, str]] = []
    vistas = 0
    for i, linha in enumerate(linhas):
        if SEPARADOR.match(linha):
            fora.append((i + 1, linha, "separador de pontilhado do sistema antigo"))
            continue
        if CONFERENCIA.match(linha):
            fora.append((i + 1, linha, "palavra de conferência solta"))
            continue
        if vistas == 0 and i < LINHAS_DE_CABECALHO and CABECALHO.match(linha):
            fora.append((i + 1, linha, "cabeçalho que a ficha já imprime"))
            continue
        if linha.strip():
            vistas += 1
        limpa = _sem_espaco_dobrado(linha)
        if limpa != linha:
            fora.append((i + 1, linha, "espaço repetido entre palavras"))
    return fora

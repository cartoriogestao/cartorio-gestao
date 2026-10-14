"""A ETIQUETA COMPLETA DO SELO NÃO SE DIGITA — relato #66, 15/09/2026.

    «tirar a parte do etiqueta completa do selo, nao trabalhamos com essa
     hipótese, selo só no selador pelo sistema»
    detalhe: «ferramenta desatualizada. aplicar para todas atribuicoes que ainda
     tenham ela»

AS DUAS COISAS QUE A FRASE SEPARA, e é delas que trata este arquivo:

  1. **a ETIQUETA COMPLETA** — o texto inteiro que o selo traz (data, ato,
     partes, os fundos e o total), que se digitava à mão num
     `<textarea name="selo_texto">` para quando o aparelho não respondesse.
     Ela saiu da TELA.
  2. **o NÚMERO do selo** — 28 caracteres (`AVESVD000000IFWIQRMJW7CGUA95`), que
     é o que o leitor do selo digita e o que as outras telas pedem
     (`name="selo"`). Esse FICA, e não é a mesma coisa: registrar o número de um
     selo que já existe não é declarar que o selo foi pedido ao aparelho.

ONDE ELA EXISTIA, medido nos templates: nesta ficha, duas vezes (o formulário
de lavrar o ato e o de emitir certidão) e no de abrir matrícula. Em nenhuma
outra tela da casa — o que as outras pedem é o número. **Desde 17/09/2026 há uma
terceira, e ela é outra coisa: `notas_ato.html`, no bloco «Selo tirado no
portal». Está declarada abaixo, com a razão, e não dispensada em silêncio.**

E as três telas que pedem selo digitado NÃO foram tocadas, de propósito:

  * `rcpj_rtd_etiquetas_selos_externos.html` monta a etiqueta de um selo
    **externo** — o número e o texto vêm do papel de outra serventia, e não
    deste aparelho. Não é a hipótese que o relato recusa.
  * `ri_expurgo.html` **mostra** o selo do ato (leitura) e pede o número do
    selo cancelado; nenhuma das duas é a etiqueta completa.
  * `notas_ato.html`, no bloco **«Selo tirado no portal»**: a etiqueta do selo
    que o escrevente tirou **no portal**, com o número dele ao lado. Quem emite
    continua sendo o selador — o portal é ele mesmo —, e é essa etiqueta que o
    razão guarda (`sd_selos.texto`). A hipótese que o relato recusa é outra:
    digitar a etiqueta quando **ninguém emitiu nada**.

O QUE FICA NO LUGAR, e é a saída que já existe: o ato entra SEM SELO, aparece
na lista de «atos sem selo», e o botão «Selar este ato» o sela depois — sem
comprar outro, porque a referência do ato faz o aparelho devolver o mesmo.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TELAS = sorted((RAIZ / "templates").glob("*.html"))

# A etiqueta completa tem dois nomes de campo na casa, e os dois são o mesmo
# caso: `selo_texto` (o ato e a certidão) e `selo_abertura_texto` (a abertura da
# matrícula). A busca é pelo CAMPO — `name="..."` —, e não pela palavra: o
# próprio comentário que explica a retirada cita o campo, e o código tem
# `a.selo_texto` (a leitura da coluna, que continua).
CAMPO_DA_ETIQUETA = re.compile(r"""name\s*=\s*["']selo(?:_abertura)?_texto["']""")

# O NÚMERO do selo, que fica. `name="selo_manual"` é o da etiqueta EXTERNA do
# RCPJ/RTD, declarada acima.
CAMPO_DO_NUMERO = re.compile(r"""name\s*=\s*["']selo["']""")

# AS EXCEÇÕES DECLARADAS — cada uma com a razão ao lado, e nenhuma por
# conveniência. A lista é declarada, e não um `if` escondido na varredura:
# exceção que ninguém escreve é a regra que some. E cada entrada é cobrada por
# dois lados — o campo TEM de estar no template, e a ÂNCORA da razão TEM de
# estar junto —, em `test_as_excecoes_declaradas_continuam_verdadeiras`.
EXCECOES_DECLARADAS = {
    # Nasceu entre a 3.6.139 (17/09, 15h02 — não tem) e a 3.6.141 (17/09,
    # 19h19 — tem), na passada que fez o selo à mão entrar no razão: a rota lê
    # `selo_texto` e grava em `sd_selos.texto`.
    "notas_ato.html": (
        "Bloco «Selo tirado no portal», com o número do selo ao lado "
        "(name=\"selo\"): é a etiqueta do selo que o escrevente tirou NO "
        "PORTAL, e é ela que o razão guarda (sd_selos.texto). Quem emite "
        "continua sendo o selador — o portal é ele mesmo. A hipótese que o "
        "relato recusa é outra: digitar a etiqueta quando NINGUÉM emitiu nada.",
        "Selo tirado no portal"),
}

COMENTARIO_JINJA = re.compile(r"\{#.*?#\}", re.S)
COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.S)


def _sem_prosa(texto: str) -> str:
    """O template sem os comentários — o varredor procura CAMPO, e não prosa.

    **É a régua que este projeto pagou para aprender nove vezes**: o comentário
    que explica a retirada CITA o campo (é ele que diz o que saiu), e um
    varredor que lê a palavra acha no comentário o que o código não tem. Aqui a
    prosa é de quem está consertando, e é a mais fácil de todas de acusar.
    """
    return COMENTARIO_HTML.sub(" ", COMENTARIO_JINJA.sub(" ", texto))


# ------------------------------------------------------------------ o varredor


def test_o_varredor_nao_e_cego():
    """O guarda tem de saber achar o campo — senão ele passa por não olhar.

    Sem esta prova, a varredura de baixo passaria numa casa que tivesse o campo
    em todas as telas: ela diria «nenhum achado» com a mesma cara de «está
    certo».
    """
    com_o_campo = '<textarea name="selo_texto" rows="3"></textarea>'
    assert CAMPO_DA_ETIQUETA.search(_sem_prosa(com_o_campo)), (
        "o varredor não achou um campo que está lá")

    so_prosa = '{# aqui havia um <textarea name="selo_texto"> e ele saiu #}'
    assert not CAMPO_DA_ETIQUETA.search(_sem_prosa(so_prosa)), (
        "comentário não é campo: o varredor bateu na própria prosa")


def test_nenhuma_tela_pede_a_etiqueta_completa():
    """A regra é da CASA, e não de uma atribuição — é o que o detalhe pede."""
    assert len(TELAS) >= 240, (
        f"só {len(TELAS)} telas lidas: a varredura tem de olhar a casa inteira")

    com_o_campo = [t.name for t in TELAS
                   if t.name not in EXCECOES_DECLARADAS
                   and CAMPO_DA_ETIQUETA.search(
                       _sem_prosa(t.read_text(encoding="utf-8", errors="replace")))]
    assert com_o_campo == [], (
        "estas telas voltaram a oferecer a etiqueta completa do selo: "
        f"{com_o_campo}. O relato #66 é de 15/09/2026, e a hipótese é uma só: "
        "«o selo será emitido apenas pelo selador». (A varredura dispensou "
        f"{len(EXCECOES_DECLARADAS)} tela(s) na lista declarada acima, com a "
        "razão escrita — nada além dela passa.)")


def test_as_excecoes_declaradas_continuam_verdadeiras():
    """Exceção que já não existe é dívida declarada que ninguém confere.

    Duas provas, uma para cada lado do que se declarou:

      * o **campo** TEM de estar no template — se saiu de lá, a entrada virou
        mentira, e quem a lesse procuraria um campo que não existe (é a régua
        do teto de portabilidade, de 01/09/2026: **teto que mente é pior que
        teto alto**);
      * a **âncora da razão** («Selo tirado no portal») TEM de estar junto —
        sem ela o campo deixou de ser a etiqueta do portal e passou a ser a
        hipótese que o relato recusa, e o teste fica vermelho em vez de benzer.

    E o campo é **contado**: se aparecer um segundo `selo_texto` na mesma tela,
    a exceção deixou de cobrir o que ela declara.
    """
    assert len(EXCECOES_DECLARADAS) == 1, (
        f"são {len(EXCECOES_DECLARADAS)} exceções declaradas: exceção nova entra "
        "com a razão escrita aqui, porque esta lista diz quanta regra a casa "
        "está dispensando")

    for arquivo, (razao, ancora) in EXCECOES_DECLARADAS.items():
        fonte = _sem_prosa((RAIZ / "templates" / arquivo).read_text(
            encoding="utf-8", errors="replace"))
        campos = CAMPO_DA_ETIQUETA.findall(fonte)

        assert campos, (
            f"`{arquivo}` está na lista de exceções e já não tem o campo da "
            f"etiqueta — tire a entrada. Razão declarada: {razao}")
        assert len(campos) == 1, (
            f"`{arquivo}` tem {len(campos)} campos de etiqueta, e a exceção "
            "declara UM — o do portal. O segundo é campo novo, e campo novo "
            "não entra pela porta da exceção antiga")
        assert ancora in fonte, (
            f"`{arquivo}` continua com o campo, mas a âncora «{ancora}» saiu do "
            "template: sem ela o que sobrou não é o que a exceção declara")


def test_o_numero_do_selo_continua_sendo_pedido():
    """A outra metade, e ela é o que separa este conserto de um estrago.

    Tirar o número do selo das telas tiraria o registro do selo que já existe —
    o que o balcão faz quando o aparelho está fora do ar, e o que a casa fez
    26.134 vezes.
    """
    pedem = [t.name for t in TELAS
             if CAMPO_DO_NUMERO.search(
                 _sem_prosa(t.read_text(encoding="utf-8", errors="replace")))]
    assert len(pedem) >= 15, (
        f"só {len(pedem)} telas pedem o número do selo — ele não foi removido "
        "de lugar nenhum, e o piso existe para o varredor não passar calado")
    for obrigatoria in ("atrib_rcpn_ficha.html", "notas_ato.html",
                        "rcpj_rtd_titulo.html", "protesto_certidoes.html"):
        assert obrigatoria in pedem, (
            f"`{obrigatoria}` pede o número do selo, e continua pedindo")


def test_as_telas_da_etiqueta_externa_nao_foram_tocadas():
    """Elas parecem o caso do relato, e não são.

    Ali se monta a etiqueta de um selo de OUTRA serventia: o número e o texto
    vêm do papel que não é desta casa nem deste aparelho, e o selador não tem o
    que emitir. Tirá-las seria o reflexo certo pelo motivo errado.
    """
    tela = (RAIZ / "templates" / "rcpj_rtd_etiquetas_selos_externos.html")
    fonte = _sem_prosa(tela.read_text(encoding="utf-8"))
    assert 'name="selo_manual"' in fonte and 'name="texto_registro"' in fonte, (
        "a etiqueta do selo EXTERNO do RCPJ/RTD é montada do papel, e continua "
        "sendo digitada")


# ------------------------------------------------------------- a tela, aberta


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero="2700"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, teor, criado_em)
           VALUES (?, '2', '2', 'ATIVO', 'ESTRUTURADA',
                   'R-1/2.700 - IMOVEL: uma area de terras rurais.',
                   '2026-09-15T08:00')""",
        (numero,))
    return int(cur.lastrowid)


def test_a_ficha_da_matricula_nao_oferece_o_campo_e_diz_a_saida(casa):
    """A tela oferece o caminho certo no lugar do campo que saiu.

    Campo que sai e não deixa nada no lugar faz quem está no balcão concluir
    que o sistema deixou de selar — e o que ele faz é o contrário: entra em
    «atos sem selo» e o botão ao lado resolve depois.
    """
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    # O texto é lido com o espaço colapsado: a frase é quebrada em três linhas
    # no template, e comparar a forma mediria a indentação em vez do que a tela
    # diz — a lição do teste que media espaço e colapsava espaço, ao contrário.
    enxuto = " ".join(html.split())

    assert 'name="selo_texto"' not in html, (
        "o relato #66: a ficha não oferece mais a etiqueta completa")
    assert "O selo é pedido ao aparelho da rede local" in enxuto, (
        "e a tela tem de dizer quem sela")
    assert "atos sem selo" in enxuto and "Selar este ato" in enxuto, (
        "a saída que fica é esta — o ato entra sem selo e aparece na lista, com "
        "o botão de selar ao lado")


def test_a_abertura_da_matricula_nao_pede_selo_nenhum(casa):
    """Zero em 1.701: o selo da abertura nunca existiu nesta casa.

    O campo existia «para o caso raro de a abertura ter selo próprio vindo de
    fora», e o caso raro nunca aconteceu — quem sela a matrícula nova é o R-1,
    e ele sela na ficha.
    """
    # A TELA E A DA CASA, E NAO A DE UM BANCO VAZIO. «Numeros menores que
    # 4.015 sao acervo» — regra da serventia, 17/09/2026 —, e num banco vazio
    # o proximo e 1: a tela apresenta a ficha como de ACERVO, que e outro
    # texto. Nesta casa o proximo e 4019.
    from ri_schema import PRIMEIRA_MATRICULA_DO_SISTEMA as PRIMEIRA
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
                   fixado_em)
               VALUES ('2',?,?,'2026-09-17')""", (PRIMEIRA, PRIMEIRA - 1))
    con.close()

    html = casa["cliente"].get("/registro-imoveis/nova").get_data(as_text=True)
    enxuto = " ".join(html.split())

    assert 'name="selo_abertura_texto"' not in html
    assert 'name="selo_texto"' not in html
    assert "O selo do Registro de Imóveis sai no" in enxuto, (
        "a tela diz onde o selo sai, em vez de pedir que se digite um")


def test_a_rota_continua_aceitando_o_numero_do_selo():
    """O que saiu foi a TELA, e não o caminho.

    `selo_texto` é o nome da coluna em `ri_atos` (e em `ri_certidoes`), e é por
    ele que os testes põem um selo à mão. Apagar a leitura da rota seria trocar
    o conserto por um defeito: a guarda do selo digitado — conferido dentro da
    transação do ato, e recusado se repetido — mora ali.
    """
    import ato_selado

    assert ato_selado.COLUNA_DO_SELO.get("ri_atos") == "selo_texto"
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert 'request.form.get("selo_texto")' in codigo, (
        "a rota do RI continua aceitando o número do selo digitado")

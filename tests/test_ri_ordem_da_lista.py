"""A LISTA DE MATRICULAS SE ORDENA — o relato #64, 15/09/2026.

    «permitir ordenar por ultimas modificadas ou por ordem numerica (do numero
     maior ao menor)»
    «permitir organizar e ver ultimos atos praticados e ultimas matriculas
     abertas»

A frase tem TRES perguntas dentro, e cada uma pede a sua ordem:

    | o que ele quer ver                  | a ordem                |
    |-------------------------------------|------------------------|
    | o que a casa acabou de escrever     | `atos`                 |
    | o que ela abriu por ultimo          | `abertura`             |
    | o numero grande                     | `numero`               |

A ordem de hoje — a do livro — FICA, e continua sendo a de quem chega sem
escolher: e a ordem em que a ficha esta na estante, e quem procura um numero
conhecido conta com ela.

POR QUE POR `data_ato`, E NAO POR `lavrado_em`
    Medido na producao antes de escrever a consulta: **1.241 dos 1.246 atos tem
    `lavrado_em` no dia 2026-08-13** — o dia da CARGA. Ordenar por ele poria o
    acervo inteiro na frente de tudo o que esta casa escreveu depois, que e o
    contrario do pedido. `data_ato` e a data do ato, e esta em `AAAA-MM-DD` nos
    **1.246 de 1.246** — por isso ordena como texto, sem conversao nenhuma.

POR QUE TESTE DE TELA, E NAO SO DA CONSULTA
    Quem ordena e a tela que o balcao usa, e a ordem so vale se as linhas
    sairem naquela ordem *na pagina*. Os testes aqui perguntam a ela — pelos
    ids que o HTML devolve, na sequencia em que aparecem.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# O codigo, lido como texto — e nao importado. **`ri_web.py` inteiro mora
# dentro de `registrar_rotas(app, db, ...)`**: os dicionarios das ordens sao
# locais da funcao que registra as rotas, alcancados por closure pelas telas, e
# `import ri_web` nao os enxerga. O `test_ri_listas_rapidas.py` ja le assim, e
# e a mesma razao: o que se guarda aqui e a FORMA da consulta.
CODIGO = (RAIZ / "ri_web.py").read_text(encoding="utf-8")


def _trecho(comeca: str, termina: str) -> str:
    i = CODIGO.find(comeca)
    assert i >= 0, f"sumiu do ri_web.py: {comeca}"
    j = CODIGO.find(termina, i)
    return CODIGO[i:j if j >= 0 else len(CODIGO)]


# --------------------------------------------------------------- a tela


def tela(s, caminho: str) -> str:
    return s["c"].get(caminho).get_data(as_text=True)


def ids(s, caminho: str = "/registro-imoveis") -> list[int]:
    """Os ids das fichas que a pagina devolveu, na ordem em que apareceram.

    O id sai do proprio link da linha — e a unica coisa da pagina que diz
    *qual* ficha entrou, sem depender de o numero aparecer no texto.
    """
    # SEM O AVISO VERMELHO DO ALTO (06/10/2026): a ficha com ato e sem
    # digitalização nova em 7 dias aparece em toda tela, com link — e não é a
    # lista que se está medindo.
    html = re.sub(r'<div role="alert".*?</div>', "", tela(s, caminho), flags=re.S)
    return [int(x) for x in re.findall(r'"/registro-imoveis/(\d+)"', html)]


def banco(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


# --------------------------------------------------------------- o acervo


def _ficha(s, numero, *, livro="2", aberta=None, atos=()) -> int:
    """Uma ficha do acervo, com a data de abertura e os atos que se pedir.

    Os atos entram por `INSERT` direto de proposito: o que se mede aqui e a
    LISTA, e lavrar pela rota traria junto a corrente de hash, o selo e a folha
    — tres coisas que a lista nao le. O que ela le e `data_ato`, e e isso que
    estes atos trazem.
    """
    con = banco(s)
    con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao,
            conferido, origem, criado_em, data_abertura, teor_formato)
           VALUES (?,'',?,?,'ESTRUTURADA','ATIVA',0,'EOFICIO','2026-07-31',?,'texto')""",
        (str(numero), livro, livro, aberta))
    mid = con.execute("SELECT MAX(id) i FROM ri_matriculas").fetchone()["i"]
    for n, data in enumerate(atos, start=1):
        con.execute(
            """INSERT INTO ri_atos
               (matricula_id, tipo, numero, data_ato, teor, teor_formato,
                hash_ato, lavrado_em, origem)
               VALUES (?,?,?,?,?,'texto',?,'2026-09-15','MANUAL')""",
            (mid, "AV", n, data, f"AV-{n:02d} ATO DA FICHA {numero}", f"h{mid}-{n}"))
    con.commit()
    con.close()
    return int(mid)


def acervo(s) -> dict[str, int]:
    """Quatro fichas com as quatro perguntas separadas, de proposito:

        | ficha | numero | aberta     | ultimo ato | serve para |
        |-------|--------|------------|------------|------------|
        | A     | 30     | 2020-01-10 | 2026-01-05 | a mais antiga em tudo |
        | B     | 10     | 2026-09-01 | 2024-03-02 | abriu por ultimo |
        | C     | 100    | 2019-05-20 | 2026-09-14 | escreveu por ultimo |
        | D     | 7      | (sem data) | (sem ato)  | vai para o FIM em todas |

    **Nenhuma delas ganha em duas ordens ao mesmo tempo** — se ganhasse, a
    ordem certa e a errada devolveriam a mesma lista e o teste nao provaria
    nada. A 100 tem o numero maior E o ato mais novo... por isso ela e a
    excecao declarada: e a unica que coincide, e as outras tres separam as
    duas perguntas.
    """
    return {
        "antiga": _ficha(s, 30, aberta="2020-01-10", atos=["2026-01-05"]),
        "aberta_por_ultimo": _ficha(s, 10, aberta="2026-09-01", atos=["2024-03-02"]),
        "escrita_por_ultimo": _ficha(s, 100, aberta="2019-05-20", atos=["2026-09-14"]),
        "vazia": _ficha(s, 7, aberta=None, atos=[]),
    }


# ------------------------------------------------ as quatro ordenacoes


def test_a_ordem_do_livro_e_a_de_quem_chega_sem_escolher(cg_casa_logada):
    """O padrao nao mudou: a ficha vem como ela esta na estante — 7, 10, 30, 100.

    Quem procura um numero conhecido conta com essa ordem, e ela nao pode
    virar a do maior para o menor so porque a lista ganhou caixa de escolha.
    """
    a = acervo(cg_casa_logada)
    do_livro = [a["vazia"], a["aberta_por_ultimo"], a["antiga"],
                a["escrita_por_ultimo"]]
    assert ids(cg_casa_logada) == do_livro
    assert ids(cg_casa_logada, "/registro-imoveis?ordem=livro") == do_livro


def test_ultimos_atos_praticados(cg_casa_logada):
    """«ver ultimos atos praticados» — e o mais novo e o 14/09."""
    a = acervo(cg_casa_logada)
    ordem = ids(cg_casa_logada, "/registro-imoveis?ordem=atos")
    assert ordem[0] == a["escrita_por_ultimo"], (
        "a ficha do ato de 14/09/2026 tem de vir primeiro")
    assert ordem[1] == a["antiga"], (
        "depois vem a do ato de 05/01/2026, e nao a de 02/03/2024")


def test_ultimas_matriculas_abertas(cg_casa_logada):
    """«ver ultimas matriculas abertas» — e a ultima e a de 01/09/2026."""
    a = acervo(cg_casa_logada)
    ordem = ids(cg_casa_logada, "/registro-imoveis?ordem=abertura")
    assert ordem[0] == a["aberta_por_ultimo"]
    assert ordem[1] == a["antiga"]


def test_numero_do_maior_ao_menor(cg_casa_logada):
    """«ordem numerica (do numero maior ao menor)» — 100, 30, 10, 7.

    **Nao e ordem de texto**: em texto, «7» vem depois de «100», e «30» depois
    de «100» tambem. A conta e por `CAST(numero AS INTEGER)`, e e por isso que
    o maior numero — 100 — e o primeiro da lista.
    """
    a = acervo(cg_casa_logada)
    assert ids(cg_casa_logada, "/registro-imoveis?ordem=numero") == [
        a["escrita_por_ultimo"], a["antiga"], a["aberta_por_ultimo"], a["vazia"]]


def test_a_ficha_sem_ato_e_sem_data_vai_para_o_fim(cg_casa_logada):
    """Ficha em branco nao pode encabecar a lista de quem escreveu por ultimo.

    Sem o `COALESCE(..., '')` da consulta, o `DESC` do Postgres — para onde
    este sistema pode ir um dia — traria o nulo para a PRIMEIRA linha, e a
    ficha sem ato nenhum apareceria como a ultima trabalhada.
    """
    a = acervo(cg_casa_logada)
    assert ids(cg_casa_logada, "/registro-imoveis?ordem=atos")[-1] == a["vazia"]
    assert ids(cg_casa_logada, "/registro-imoveis?ordem=abertura")[-1] == a["vazia"]


def test_ordem_desconhecida_nao_estoura_e_cai_na_do_livro(cg_casa_logada):
    """Ordem que nao existe — de um favorito velho, ou de um `?ordem=` vazio.

    Ela nao pode virar HTTP 500 na cara de quem clica, nem escolher uma ordem
    por acidente: cai na do livro, que e a de quem nao escolheu nada.
    """
    acervo(cg_casa_logada)
    do_livro = ids(cg_casa_logada)
    for tentativa in ("?ordem=xyz", "?ordem=", "?ordem=DROP TABLE"):
        resposta = cg_casa_logada["c"].get(f"/registro-imoveis{tentativa}")
        assert resposta.status_code == 200, tentativa
        assert ids(cg_casa_logada, f"/registro-imoveis{tentativa}") == do_livro


# --------------------------------------------- a escolha, na tela


def test_a_tela_oferece_as_quatro_ordens(cg_casa_logada):
    """A caixa se monta do mesmo dicionario que a consulta usa.

    Lista de opcao escrita a mao noutro arquivo envelhece na tarde em que se
    escreve — e aqui ela ofereceria ao balcao uma ordem que a consulta nao
    conhece, que e a ordem que ele nunca vai ver.
    """
    html = tela(cg_casa_logada, "/registro-imoveis")
    assert 'name="ordem"' in html
    for chave in ("livro", "atos", "abertura", "numero"):
        assert f'value="{chave}"' in html, chave


def test_a_ordem_escolhida_aparece_marcada(cg_casa_logada):
    """Quem escolheu «numero» ve a escolha marcada quando a pagina volta.

    Sem isto, a lista sai numa ordem e a caixa mostra outra — e quem olha
    conclui que a escolha nao pegou.
    """
    acervo(cg_casa_logada)
    html = tela(cg_casa_logada, "/registro-imoveis?ordem=numero")
    assert re.search(r'value="numero"\s+selected', html), (
        "a ordem escolhida tem de aparecer marcada na caixa")
    assert 'value="livro" selected' not in html


def test_a_paginacao_leva_a_ordem_escolhida(cg_casa_logada):
    """Virar a pagina nao pode devolver a lista na ordem do livro, calada.

    O que se prova aqui e o link: ele tem de carregar a ordem escolhida. Sem
    isso a segunda pagina viria na ordem do livro e a primeira na escolhida —
    duas paginas do mesmo trabalho, em ordens diferentes.
    """
    con = banco(cg_casa_logada)
    for i in range(1, 52):                     # 51 fichas: uma pagina e sobra
        con.execute(
            """INSERT INTO ri_matriculas
               (numero, complemento, livro, livro_norm, tipo_ficha, situacao,
                conferido, origem, criado_em, teor_formato)
               VALUES (?,'','2','2','ESTRUTURADA','ATIVA',0,'EOFICIO',
                       '2026-07-31','texto')""", (str(i),))
    con.commit()
    con.close()

    pagina1 = tela(cg_casa_logada, "/registro-imoveis?ordem=numero")
    assert "ordem=numero" in pagina1, (
        "o link da proxima pagina tem de levar a ordem escolhida")
    assert len(ids(cg_casa_logada, "/registro-imoveis?ordem=numero")) == 50
    # e a segunda pagina traz a que sobra, na mesma ordem: a 1 e a menor de todas
    assert ids(cg_casa_logada, "/registro-imoveis?ordem=numero&pagina=2") == [1]


# ------------------------------------------------------ o relato, miudo


def test_a_ordem_por_ultimo_ato_usa_a_data_do_ato_e_nao_o_lavrado_em(cg_casa_logada):
    """O guarda das duas datas — e a medicao que decidiu entre elas.

    Na producao, **1.241 dos 1.246 atos** tem `lavrado_em` no dia da carga
    (13/08/2026), e a data do ato vai de 1948 a 2026: ordenar por `lavrado_em`
    poria o acervo inteiro na frente do que a casa escreveu depois. E o defeito
    nao apareceria em teste de tela nenhum — os atos do ensaio nascem na mesma
    data —, por isso o guarda le a CONSULTA.
    """
    ordem = _trecho("ORDEM_SQL = {", "\n    }")
    assert "a.data_ato" in ordem, "a ordem dos ultimos atos usa a data do ato"
    assert "lavrado_em" not in ordem, (
        "`lavrado_em` e o dia da carga em 1.241 dos 1.246 atos do acervo")


def test_a_lista_mostra_quando_a_ficha_foi_aberta_e_o_ultimo_ato(cg_casa_logada):
    """A data que ORDENA tem de estar a vista.

    Uma lista ordenada por «ultimos atos praticados» que nao mostra a data do
    ultimo ato pede que quem a le acredite — e a coluna vazia, no meio dela,
    nao se distingue de um erro.
    """
    acervo(cg_casa_logada)
    html = tela(cg_casa_logada, "/registro-imoveis?ordem=atos")
    assert "Aberta em" in html and "Último ato" in html
    assert "14/09/2026" in html, "a data do ultimo ato sai em dd/mm/aaaa"
    assert "01/09/2026" in html, "a data de abertura tambem"


# ------------------------------------------------------ o relato, miudo


def test_a_consulta_da_ordem_sai_do_dicionario_e_nao_do_texto():
    """Uma regua so: a tela oferece o que a consulta conhece, e nada mais.

    Uma segunda lista de ordens escrita a mao noutro arquivo envelheceria na
    tarde em que fosse escrita, e a caixa ofereceria ao balcao uma ordem que a
    consulta nao sabe fazer — que e a ordem que ele nunca vai ver.
    """
    oferecidas = set(re.findall(r'"(\w+)":', _trecho("ORDENS_DA_LISTA = {", "\n    }")))
    consultas = set(re.findall(r'"(\w+)":', _trecho("ORDEM_SQL = {", "\n    }")))
    assert oferecidas == consultas, (oferecidas, consultas)
    assert oferecidas == {"livro", "atos", "abertura", "numero"}, oferecidas

"""AS LISTAS DO RI NAO ORDENAM CARREGANDO O TEOR — 15/09/2026.

    «atualizei e esta lento»

O QUE ESTAVA ACONTECENDO, medido contra a producao antes de mexer numa linha:

    | tela                | tempo  |
    |---------------------|--------|
    | `/registro-imoveis` | **4,2 a 5,1 s**, toda vez |
    | as consultas dela, somadas a mao | 0,66 s |

    A diferenca estava numa consulta so — **2,64 s** —, achada com
    `set_trace_callback` na conexao:

        SELECT m.*, (subconsultas) FROM ri_matriculas m WHERE ...
         ORDER BY m.livro_norm, CAST(m.numero AS INTEGER), m.numero
         LIMIT 50 OFFSET 0

    **`CAST(m.numero AS INTEGER)` nao usa indice.** Para saber quais cinquenta
    ficam, o SQLite ordena a tabela inteira — e com `SELECT m.*` ele carrega
    **todas as colunas das 1.982 fichas** para isso. `ri_matriculas.teor`
    guarda **31,8 MB de texto**: a tela lia trinta e dois megabytes do disco
    para mostrar cinquenta linhas.

O CONSERTO, e por que ele nao muda nada do que sai:
    A subconsulta interna ordena e pagina tocando so `id`, `livro_norm` e
    `numero`, que sao curtos; a de fora busca as 50 linhas cheias. Conferido
    linha a linha contra a producao: **as mesmas fichas, na mesma ordem, com
    as mesmas colunas e as mesmas contagens**.

    | | antes | depois |
    |---|---|---|
    | a consulta | 2,37 a 3,55 s | **0,14 a 0,16 s** |
    | a tela inteira | 4,2 a 5,1 s | **0,48 s** |

    **A ordenacao aparece duas vezes de proposito**: a de dentro decide quem
    entra, a de fora garante a ordem — `IN (...)` nao conserva ordem nenhuma,
    e sem a segunda a lista sairia embaralhada.

E ISTO NAO ERA REGRESSAO DE HOJE. Conferido no `.cgu` da 3.6.99: a consulta
    ja era assim. O que mudou foi o tamanho do acervo — e a reinicializacao da
    atualizacao fez o oficial reparar.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CODIGO = (RAIZ / "ri_web.py").read_text(encoding="utf-8")

# `SELECT x.*` ... `ORDER BY` com `CAST(` ... `LIMIT`, tudo na mesma consulta:
# a forma que obriga o SQLite a materializar a tabela inteira para paginar.
ORDENA_CARREGANDO_TUDO = re.compile(
    r"SELECT\s+\w+\.\*(?:(?!FROM\s+\()[\s\S]){0,900}?"
    r"ORDER BY[^\"]{0,200}?CAST\([^\"]{0,200}?LIMIT",
    re.IGNORECASE)


def _consultas_lentas(codigo: str) -> list[str]:
    """As consultas que ordenam por expressao enquanto carregam `x.*`.

    Uma consulta com a subconsulta de paginacao **nao** conta: nela o
    `LIMIT` fica dentro do `IN (SELECT id ...)`, e o `SELECT m.*` de fora ja
    recebe so os cinquenta ids.
    """
    achadas = []
    for m in ORDENA_CARREGANDO_TUDO.finditer(codigo):
        trecho = m.group(0)
        if "IN (" in trecho and "SELECT id FROM" in trecho:
            continue
        achadas.append(" ".join(trecho.split())[:120])
    return achadas


def test_nenhuma_lista_do_ri_ordena_carregando_a_ficha_inteira():
    """O guarda que impede a lentidao de voltar.

    Ele nao mede tempo — medir tempo em teste da numero diferente em cada
    maquina e falha quando a maquina esta ocupada. Ele guarda a **forma** que
    produziu a lentidao, que e o que se pode afirmar sempre.
    """
    lentas = _consultas_lentas(CODIGO)
    assert not lentas, (
        "consulta que ordena por expressao carregando a ficha inteira:\n  "
        + "\n  ".join(lentas)
        + "\n\nPagine pelo `id` numa subconsulta e busque as linhas cheias "
          "depois — `ri_matriculas.teor` tem 31,8 MB.")


def _corpo_da_rota(nome: str) -> str:
    """O corpo da rota, do `def` ate a proxima rota.

    Recortar por um numero fixo de caracteres envelhece: basta o comentario
    acima da consulta crescer para o recorte parar antes dela, e o teste passa
    a medir o vazio — sem reclamar.
    """
    i = CODIGO.find(f"def {nome}(")
    assert i >= 0, f"a rota {nome} sumiu"
    j = CODIGO.find("\n    @app.route", i)
    return CODIGO[i:j if j >= 0 else len(CODIGO)]


def test_a_lista_de_matriculas_pagina_pelo_id():
    """A forma do conserto, para ele nao ser desfeito por distracao."""
    rota = _corpo_da_rota("ri_matriculas")
    assert "WHERE m.id IN (" in rota, "a lista voltou a paginar sobre `m.*`"
    assert "SELECT id FROM ri_matriculas" in rota


def test_a_ordenacao_se_repete_dentro_e_fora():
    """Sem a de fora a lista sai embaralhada: `IN (...)` nao conserva ordem.

    Desde o relato #64 a ordem nao e uma so — sao quatro, escolhidas na tela —,
    e por isso o que se conta e o USO da escolhida: duas vezes, uma para
    decidir quais cinquenta entram e outra para a ordem final.
    """
    rota = _corpo_da_rota("ri_matriculas")
    assert rota.count("ORDER BY {ordenacao}") == 2, (
        "a ordenacao tem de aparecer duas vezes — a de dentro escolhe quem "
        "entra, a de fora garante a ordem")
    assert "ordenacao = ORDEM_SQL[ordem]" in rota, (
        "as duas tem de sair do MESMO dicionario, senao divergem no conserto")


def test_as_quatro_ordens_da_lista_tem_consulta():
    """A tela nao pode oferecer ordem que a consulta nao conhece."""
    i = CODIGO.find("ORDENS_DA_LISTA = {")
    j = CODIGO.find("}", i)
    ordem_sql_i = CODIGO.find("ORDEM_SQL = {")
    ordem_sql_j = CODIGO.find("\n    }", ordem_sql_i)
    oferecidas = set(re.findall(r'"(\w+)":', CODIGO[i:j]))
    consultas = set(re.findall(r'"(\w+)":', CODIGO[ordem_sql_i:ordem_sql_j]))
    assert oferecidas == consultas, (oferecidas, consultas)
    assert len(oferecidas) == 4, oferecidas


def test_o_indicador_real_tambem_pagina_pelo_id():
    """A mesma forma estava em duas telas, e as duas foram consertadas."""
    rota = _corpo_da_rota("ri_indicador_real")
    assert "WHERE m.id IN (" in rota
    assert rota.count("ORDER BY m.bairro, m.logradouro, "
                      "CAST(m.numero AS INTEGER)") == 2

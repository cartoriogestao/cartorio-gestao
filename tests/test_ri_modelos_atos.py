"""Texto corrido nos modelos de ato do Registro de Imóveis — 07/09/2026.

    «o corpo de todos os atos do cartorio eh texto corrido, sem espacos.
     arrume isso em todos os modelos» — o oficial.

O QUE ESTE ARQUIVO ACHOU, e por que `notas_modelos.py` não bastava
    O art. 795, § 2º do Código de Normas da CGJ/TJMA — escrituração seguida,
    sem claros ou espaços em branco — não é regra do Tabelionato de Notas: é
    regra de qualquer ato que vai para dentro de um livro, e o Registro de
    Imóveis lavra nos seus. `notas_modelos.py` já cumpria (com `_corpo()` e
    dois testes de forma); `ri_modelos_atos.py` **não** — os 25 modelos
    (`MODELOS`, a averbação e o registro) eram strings triplas cruas, com
    quebra de linha real herdada do jeito como o código foi escrito, quebrado
    em várias linhas para caber na tela de quem mantém o arquivo.

    **E o efeito não era cosmético.** `preencher()` só cuidava de `[CAMPO]`,
    `{ESCOLHA}` e `«SE»` — nunca de `\\n` solto —, e o texto ia assim para o
    banco (`ri_atos.teor`, com `teor_formato='texto'`). Na impressão da
    matrícula, `ri_odt.texto_para_odf()` trata cada quebra de linha como um
    parágrafo NOVO: uma cláusula que devia sair corrida — «pelo preço certo e
    ajustado de [PREÇO], já pago e quitado.» — sairia partida em vários
    parágrafos separados na matrícula impressa, exatamente o «claro» que a
    norma proíbe.

    A correção é a mesma função, com o mesmo nome, que `notas_modelos.py` já
    usa: `_corpo()` colapsa toda quebra de linha do código-fonte num espaço
    único, antes de o texto sair da definição do modelo.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_modelos_atos as RM                                     # noqa: E402


def limpo(texto: str) -> str:
    return re.sub(r"<[^>]+>", "", texto)


# ------------------------------------------------- texto corrido, sem claros

def test_nenhum_modelo_tem_quebra_de_linha():
    # Art. 795, § 2º: a escrituração deve ser seguida. Quebra de linha no
    # corpo vira claro no papel — e aqui virava parágrafo novo na matrícula.
    for m in RM.MODELOS:
        assert "\n" not in m["corpo"], m["codigo"]


def test_nenhum_modelo_tem_espaco_duplo_nem_espaco_antes_de_pontuacao():
    for m in RM.MODELOS:
        assert "  " not in m["corpo"], m["codigo"]
        assert not re.search(r"\s[,.;:]", m["corpo"]), m["codigo"]


def test_o_corpo_de_todo_modelo_comeca_e_termina_no_paragrafo():
    # Não é a forma exigida pela norma — é a convenção desta biblioteca
    # (mesma de `notas_modelos.py`), e vale como guarda de que `_corpo()`
    # não comeu um pedaço do início ou do fim ao colapsar as linhas.
    for m in RM.MODELOS:
        assert m["corpo"].startswith("<p>"), m["codigo"]
        assert m["corpo"].endswith("</p>"), m["codigo"]


# ----------------------------------------------------- sanidade do catálogo

def test_todo_modelo_tem_campo_para_preencher():
    for m in RM.MODELOS:
        assert RM.campos_do_modelo(m), m["codigo"]


def test_preencher_nao_estoura_em_nenhum_modelo():
    for m in RM.MODELOS:
        RM.preencher(m, {})


def test_os_codigos_sao_unicos():
    codigos = [m["codigo"] for m in RM.MODELOS]
    assert len(codigos) == len(set(codigos))


def test_a_lista_nao_encolheu():
    # Varredor que deixa de achar passa calado.
    assert len(RM.MODELOS) >= 25

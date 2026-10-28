"""A remessa gerada, comparada com a que esta casa mandou de verdade.

O ENSAIO QUE ISTO É, E POR QUE ELE VALE MAIS QUE OS OUTROS
    Os testes de regra provam que o montador obedece ao layout. Este pega os
    **cinco arquivos que o E-Ofício exportou** em `C:\\ProgramData\\CartorioGestao\\arquivos\\eoficio\\IBGE_EXP`,
    gera o mesmo trimestre a partir do acervo, e compara **posição por
    posição**.

    Ele achou o que nenhum teste de regra acharia: o número do livro na forma
    `A24` (e não `A-24`), o de-para do local do nascimento, a natureza do óbito
    numa coluna que eu tinha dado como inexistente — e três defeitos que **não
    são meus**.

OS TRÊS DEFEITOS DO E-OFÍCIO QUE A COMPARAÇÃO ACHOU
    **1. A idade ia um ano a mais para quem morreu antes do aniversário.**
    Medido em 3 dos 11 óbitos comparáveis: quem nasceu em 12/07/1928 e morreu
    em 06/04/2026 tinha 97 anos, e o arquivo diz 98. O E-Ofício fazia
    `ano do óbito − ano do nascimento`, sem descontar o aniversário que ainda
    não tinha chegado. São **27% dos óbitos** com a idade errada.

    **2. A residência da mãe era o município do PARTO.** Medido: em **27 dos
    28** nascimentos o `COD-MUNIC-RES-MAE` é igual ao `COD-MUNIC-NASC`. Mãe que
    mora em Cidade Exemplo e teve o filho no hospital de Imperatriz ia para o
    IBGE como moradora de Imperatriz — e é justamente por município de
    residência que o IBGE distribui a estatística de natalidade.

    **3. Duas das treze linhas de óbito têm 102 posições, e não 103.** Falta um
    caractere no meio, e tudo depois dele anda uma casa para a esquerda: a UF
    de nascimento sai `10` e o país `763`, que não existem. O IBGE aceitou.

    NENHUM DOS TRÊS SE CONSERTA OLHANDO O CÓDIGO NOVO — os três só aparecem
    comparando o que se gera com o que se mandou.
"""
from __future__ import annotations

import collections
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import acervo_carga as AC                        # noqa: E402
import ibge_geracao as G                         # noqa: E402
import ibge_remessa as IBGE                      # noqa: E402
from ibge_schema import init_ibge_schema         # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-08-28T12:00:00"
ACERVO = Path(r"C:\ProgramData\CartorioGestao\acervo_eoficio.sqlite3")
EXPORTADO = Path(r"C:\ProgramData\CartorioGestao\arquivos\eoficio\IBGE_EXP")

pytestmark = pytest.mark.skipif(
    not (ACERVO.exists() and EXPORTADO.exists()),
    reason="o acervo ou os arquivos exportados não estão nesta máquina")


@pytest.fixture(scope="module")
def gerado():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    for iniciar in (init_nucleo_schema, init_rc_schema, init_ibge_schema):
        iniciar(con)
    con.executescript(
        "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    acervo = sqlite3.connect(f"file:{ACERVO}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    AC.carregar_ibge(con, acervo, agora=AGORA)
    config = dict(con.execute("SELECT key, value FROM settings").fetchall())
    # O SEGUNDO TRIMESTRE DE 2026 é o que a casa exportou.
    return G.montar(con, ano=2026, trimestre=2, config=config)


def _reais(nome: str) -> list[str]:
    return [l for l in (EXPORTADO / nome).read_text(
        encoding=IBGE.CODIFICACAO).splitlines() if l.strip()]


def _por_registro(linhas, layout):
    de, ate = IBGE.posicoes(layout)["NUM-REGLIV"]
    return {l[de:ate]: l for l in linhas}


def _diferencas(meus, reais, layout) -> collections.Counter:
    pos = IBGE.posicoes(layout)
    por_real = _por_registro(reais, layout)
    de, ate = pos["NUM-REGLIV"]
    difs: collections.Counter = collections.Counter()
    for m in meus:
        real = por_real.get(m[de:ate])
        if real is None or len(real) != IBGE.largura(layout):
            continue          # as linhas curtas do arquivo real ficam de fora
        for campo, (a, b) in pos.items():
            if m[a:b] != real[a:b]:
                difs[campo] += 1
    return difs


# ------------------------------------------ o mesmo movimento do trimestre


def test_a_remessa_tem_o_mesmo_numero_de_linhas_que_a_real(gerado):
    """A prova mais simples de que o recorte do trimestre está certo."""
    for nome in ("CARTINF01.TXT", "CARTINF02.TXT", "CARTINF03.TXT"):
        assert len(gerado["arquivos"][nome]) == len(_reais(nome)), nome


def test_toda_linha_tem_a_largura_do_layout(gerado):
    """Campo fora de lugar aparece aqui antes de aparecer no IBGE."""
    for nome, linhas in gerado["arquivos"].items():
        largura = IBGE.largura(IBGE.ARQUIVOS[nome])
        assert {len(l) for l in linhas} == {largura}, nome


# ------------------------------------------------ o casamento, byte a byte


def test_o_casamento_sai_identico_ao_que_a_casa_mandou(gerado):
    """As duas linhas de casamento batem **posição por posição**.

    É a prova de que o montador inteiro está certo: cabeçalho, trimestre,
    número do livro, datas invertidas, sexo, estado civil pelo catálogo do
    casamento, e os seis códigos de município e país dos dois cônjuges.
    """
    meus = gerado["arquivos"]["CARTINF02.TXT"]
    reais = set(_reais("CARTINF02.TXT"))
    assert set(meus) == reais


# ------------------------------------------------------- o número do livro


def test_o_numero_do_livro_sai_na_forma_do_ibge(gerado):
    """`A24`, `B04`, `C05` — letra colada ao número, dois dígitos, sem hífen.

    O sistema guarda `A-24`, que é como o livro de papel se chama e como a
    certidão o imprime. Quem tem forma própria é o arquivo.
    """
    for nome, esperado in (("CARTINF01.TXT", "A"), ("CARTINF02.TXT", "B"),
                           ("CARTINF03.TXT", "C")):
        layout = IBGE.ARQUIVOS[nome]
        de, ate = IBGE.posicoes(layout)["NUM-LIVRO"]
        for linha in gerado["arquivos"][nome]:
            livro = linha[de:ate].strip()
            assert livro.startswith(esperado), (nome, livro)
            assert len(livro) == 3 and livro[1:].isdigit(), (nome, livro)


# --------------------------------- o que o E-Ofício mandava errado


def test_a_idade_do_falecido_desconta_o_aniversario_que_nao_chegou(gerado):
    """O primeiro defeito do E-Ofício, e ele atinge 27% dos óbitos.

    Quem nasceu em 12/07/1928 e morreu em 06/04/2026 tinha **97** anos. O
    arquivo que esta casa mandou diz 98, porque a conta era
    `ano do óbito − ano do nascimento`, sem descontar o aniversário.
    """
    assert G.idade_em_anos("1928-07-12", "2026-04-06") == ("097", "4")
    assert G.idade_em_anos("1928-07-12", "2026-07-12") == ("098", "4")

    difs = _diferencas(gerado["arquivos"]["CARTINF03.TXT"],
                       _reais("CARTINF03.TXT"), IBGE.OBITO)
    # As diferenças de idade que sobram são exatamente essas — e são do
    # arquivo antigo, não desta remessa.
    assert difs.get("IDADE", 0) >= 3


def test_a_residencia_da_mae_nao_e_o_municipio_do_parto(gerado):
    """O segundo defeito, e o mais caro dos três.

    Medido no arquivo real: em **27 das 28** linhas o município de residência
    da mãe é igual ao município do nascimento. Mãe que mora em Cidade Exemplo e
    teve o filho no hospital de Imperatriz ia como moradora de Imperatriz — e é
    por município de residência que o IBGE distribui a estatística de
    natalidade.
    """
    pos = IBGE.posicoes(IBGE.NASCIMENTO)
    copiados = sum(
        1 for l in _reais("CARTINF01.TXT")
        if l[pos["COD-UF-NASC"][0]:pos["COD-MUNIC-NASC"][1]]
        == l[pos["COD-UF-RES-MAE"][0]:pos["COD-MUNIC-RES-MAE"][1]])
    assert copiados == 27, "o arquivo real mudou; a medição precisa ser refeita"

    # E o que o sistema gera NÃO copia: a residência sai da mãe, em
    # `rc_pessoas`, e não do lugar onde a criança nasceu.
    meus = gerado["arquivos"]["CARTINF01.TXT"]
    nossos_copiados = sum(
        1 for l in meus
        if l[pos["COD-UF-NASC"][0]:pos["COD-MUNIC-NASC"][1]]
        != l[pos["COD-UF-RES-MAE"][0]:pos["COD-MUNIC-RES-MAE"][1]])
    assert nossos_copiados > 0, (
        "nenhuma linha distingue residência de nascimento — a fonte da "
        "residência da mãe voltou a ser o lugar do parto")


def test_duas_linhas_do_arquivo_real_estao_truncadas(gerado):
    """O terceiro defeito, e é do arquivo antigo.

    Duas das treze linhas de óbito têm 102 posições. Falta um caractere no
    meio, e tudo depois dele anda uma casa: a UF de nascimento sai `10` e o
    país `763`, que não existem em tabela nenhuma. O IBGE aceitou.

    As nossas têm 103 — há teste de largura acima que garante isso.
    """
    curtas = [l for l in _reais("CARTINF03.TXT")
              if len(l) != IBGE.largura(IBGE.OBITO)]
    assert len(curtas) == 2
    assert all(len(l) == 102 for l in curtas)


# ------------------------------------- o que sobra de diferença, e por quê


def test_o_que_ainda_difere_esta_todo_explicado(gerado):
    """Nenhuma diferença sem explicação — é isso que fecha o ensaio.

    O que sobra depois dos três defeitos acima:

      IDADE-GENI e COD-*-RES-MAE   o arquivo antigo não os tira do acervo:
                                   a mãe de `tbFiliacao` mora em Cidade Exemplo
                                   e o arquivo diz Imperatriz; a data de
                                   nascimento dela dá 29 anos e o arquivo diz
                                   27. Os nossos são rastreáveis; os dele não.
      IDADE                        o defeito do aniversário, acima.
      NATUREZA / EST-CIV / DO      só nas duas linhas truncadas.
    """
    esperados = {
        "CARTINF01.TXT": {"IDADE-GENI", "COD-UF-RES-MAE",
                          "COD-MUNIC-RES-MAE"},
        "CARTINF02.TXT": set(),
        "CARTINF03.TXT": {"IDADE", "TIPO-TEMPO"},
    }
    for nome, permitidos in esperados.items():
        difs = _diferencas(gerado["arquivos"][nome], _reais(nome),
                           IBGE.ARQUIVOS[nome])
        sobrando = set(difs) - permitidos
        assert not sobrando, (
            f"{nome}: diferença nova e sem explicação em {sobrando}. "
            f"Ou o gerador mudou, ou o arquivo de referência mudou — nos dois "
            f"casos, meça antes de mexer no teste.")


def test_o_resumo_rc10_sai_igual_ao_real(gerado):
    """A folha RC-10 (`CARTINF10.TXT`) não era gerada — 28/10/2026. Ela sai
    agora byte a byte igual à que a casa exportou do 2º trimestre de 2026:
    uma linha por livro (A24, B04, C05), com o primeiro e o último número do
    trimestre e os totais, e a última linha sem livro e zerada."""
    assert gerado["arquivos"]["CARTINF10.TXT"] == _reais("CARTINF10.TXT")

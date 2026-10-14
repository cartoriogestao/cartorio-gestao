"""A remessa do IBGE — o layout, provado pela ida e volta.

DE ONDE SAI ESTE LAYOUT
    Da especificação oficial do IBGE — *Novas instruções para a geração dos
    arquivos dos cartórios informatizados*, Diretoria de Informática,
    COPRE/GESIP, 08/01/2015 —, que o oficial indicou em 28/08/2026.

    E ele foi conferido contra os arquivos que **esta casa** exportou, em
    `C:\\ARPNET\\C11\\IBGE_EXP`.

A PROVA É O IDA E VOLTA, como no leitor da CRA: ler um arquivo real e
    reescrevê-lo tem de sair **idêntico byte a byte**. Foi esse teste que achou
    quatro defeitos no leitor do Protesto que nenhuma outra conferência pegou.

    Aqui ele prova duas coisas ao mesmo tempo: que o layout está certo, e que o
    escritor alinha cada campo como o IBGE aceitou.

O ARQUIVO REAL É OPCIONAL, e os testes que dependem dele se pulam sozinhos.
    Ele mora fora do projeto, na máquina do servidor. O resto dos testes prova
    o módulo sem ele — mas quando ele está lá, é ele que vale.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ibge_remessa as IBGE                                  # noqa: E402

PASTA_REAL = Path(r"C:\ARPNET\C11\IBGE_EXP")

REAIS = (
    ("CARTINF01.TXT", IBGE.NASCIMENTO, 112),
    ("CARTINF02.TXT", IBGE.CASAMENTO, 105),
    ("CARTINF03.TXT", IBGE.OBITO, 103),
    ("CARTINF10.TXT", IBGE.RC10, 68),
)


# ------------------------------------------------------------- os layouts


@pytest.mark.parametrize("nome,layout,esperado", REAIS)
def test_a_largura_do_layout_e_a_do_arquivo_real(nome, layout, esperado):
    """A soma dos campos da especificação bate com a linha que a casa mandou."""
    assert IBGE.largura(layout) == esperado


def test_as_posicoes_medidas_batem_com_a_especificacao():
    """Oito campos foram medidos ANTES de achar a especificação.

    Cruzando 28 linhas do arquivo com 28 assentos do acervo saíram: dia e mês
    do registro, data de nascimento, sexo, os dois municípios e a DN. A
    especificação confirmou os oito, um a um.
    """
    p = IBGE.posicoes(IBGE.NASCIMENTO)
    assert p["DATAREGDIA"] == (33, 35)
    assert p["DATAREGMES"] == (35, 37)
    assert p["DATA-NASC"] == (37, 45)
    assert p["SEXO"] == (54, 55)              # o que a medição acertou sozinha
    assert p["COD-UF-NASC"] == (46, 48)
    assert p["COD-MUNIC-NASC"] == (48, 53)
    assert p["COD-MUNIC-RES-MAE"] == (67, 72)
    assert p["DN"] == (77, 112)


# ------------------------------------------------------------ a ida e volta


def _linhas_reais(nome: str) -> bytes:
    caminho = PASTA_REAL / nome
    if not caminho.is_file():
        pytest.skip(f"{caminho} não está nesta máquina")
    bruto = caminho.read_bytes()
    if not bruto.strip():
        pytest.skip(f"{nome} está vazio nesta casa")
    return bruto


def _sem_espaco_no_fim(bruto: bytes) -> bytes:
    """As linhas sem o espaço sobrando no fim.

    DUAS DAS TREZE LINHAS DE ÓBITO QUE ESTA CASA MANDOU TÊM 102 POSIÇÕES, e não
    103 — falta exatamente **um espaço no fim**, e o campo cortado é o último,
    o número da DO. As outras onze têm as 103 da especificação.

    Não é o nosso layout que está errado: é o arquivo que a casa mandou, com
    duas linhas curtas — algum programa aparou o espaço final ao gravar. O IBGE
    aceitou assim, mas o que se escreve daqui em diante sai completo.

    Por isso a prova de ida e volta compara **sem o espaço do fim**: ela
    continua pegando campo fora de lugar, alinhamento trocado e largura errada,
    e deixa de acusar um defeito que é do arquivo antigo.
    """
    fim = IBGE.FIM_DE_LINHA.encode(IBGE.CODIFICACAO)
    return fim.join(x.rstrip(b" ") for x in bruto.split(fim))


@pytest.mark.parametrize("nome,layout,_", REAIS)
def test_o_arquivo_real_volta_identico(nome, layout, _):
    """Ler e reescrever tem de sair igual, byte a byte.

    É a prova do leitor da CRA aplicada aqui, e ela pega o que nenhuma outra
    conferência pega: campo fora de lugar, alinhamento trocado, largura errada.
    """
    original = _linhas_reais(nome)
    lidas = IBGE.ler(layout, original)
    devolta = IBGE.escrever(layout, lidas)
    assert _sem_espaco_no_fim(devolta) == _sem_espaco_no_fim(original), (
        f"{nome} não voltou idêntico — o layout ou o alinhamento está errado")


def test_o_arquivo_de_obitos_da_casa_tem_duas_linhas_curtas():
    """O achado que a ida e volta produziu, e ele é sobre o arquivo.

    Duas das treze linhas têm 102 posições em vez de 103 — falta um espaço no
    fim. É defeito do que a casa mandou, e não do layout: as outras onze têm as
    103 da especificação. Fica escrito para não se procurar de novo.
    """
    linhas = _linhas_reais("CARTINF03.TXT").decode(
        IBGE.CODIFICACAO).split(IBGE.FIM_DE_LINHA)
    larguras = sorted({len(x) for x in linhas if x.strip()})
    assert larguras == [102, 103]
    curtas = [x for x in linhas if x.strip() and len(x) == 102]
    assert len(curtas) == 2
    # E o que falta é só espaço: o conteúdo dos campos está inteiro.
    assert all(x.ljust(103) == x + " " for x in curtas)


@pytest.mark.parametrize("nome,layout,largura", REAIS)
def test_toda_linha_real_tem_a_largura_do_layout(nome, layout, largura):
    """Com a folga de um espaço, pelo defeito documentado acima."""
    for linha in IBGE.ler(layout, _linhas_reais(nome)):
        assert largura - 1 <= sum(len(v) for v in linha.values()) <= largura


def test_os_valores_do_arquivo_real_sao_os_que_a_casa_declara():
    """A chave do IBGE desta casa, conferida contra o cabeçalho das linhas."""
    linhas = IBGE.ler(IBGE.NASCIMENTO, _linhas_reais("CARTINF01.TXT"))
    # O município da casa sai do próprio arquivo real, e não se escreve aqui
    # (sanitização B3, 11/10/2026): o que se prova é que toda linha declara a
    # MESMA chave, e que ela tem a forma do layout.
    municipios = {l["MUN-PESQUISA"] for l in linhas}
    assert len(municipios) == 1 and next(iter(municipios)).isdigit()
    for l in linhas:
        assert l["UF-PESQUISA"] == "21"        # Maranhão
        assert l["DIST-PESQUISA"] == "05"
        assert l["COD_CARTORIO"] == "01"
        assert l["COD-PAIS-RES-MAE"] == IBGE.BRASIL


def test_o_sexo_do_arquivo_real_esta_no_catalogo():
    """Foi o campo que a medição acertou sozinha, antes da especificação."""
    for l in IBGE.ler(IBGE.NASCIMENTO, _linhas_reais("CARTINF01.TXT")):
        assert int(l["SEXO"]) in IBGE.SEXO


def test_o_resumo_conta_o_que_os_arquivos_trazem():
    """O RC-10 é o que o IBGE confere primeiro: número que não bate, remessa volta."""
    resumo = IBGE.ler(IBGE.RC10, _linhas_reais("CARTINF10.TXT"))
    total = {"TNASCIDOS": 0, "TCASAMENTO": 0, "TOBITOS": 0}
    for l in resumo:
        for k in total:
            total[k] += int(l[k])
    assert total["TNASCIDOS"] == len(IBGE.ler(IBGE.NASCIMENTO,
                                              _linhas_reais("CARTINF01.TXT")))
    assert total["TCASAMENTO"] == len(IBGE.ler(IBGE.CASAMENTO,
                                               _linhas_reais("CARTINF02.TXT")))
    assert total["TOBITOS"] == len(IBGE.ler(IBGE.OBITO,
                                            _linhas_reais("CARTINF03.TXT")))


# ------------------------------------------------------- o escritor, sozinho


def test_char_alinha_a_esquerda_e_num_a_direita():
    linha = IBGE.montar_linha(IBGE.RC10, {
        "UF-PESQUISA": "21", "MUN-PESQUISA": "98765", "DIST-PESQUISA": "05",
        "COD_CARTORIO": "01", "TRIM-PESQUISA": "2", "ANO-PESQUISA": "26",
        "NUM-LIVRO": "A24", "PRI-TRIMES": 19506, "ULT-TRIMES": 19543,
        "TNASCIDOS": 28})
    p = IBGE.posicoes(IBGE.RC10)
    assert linha[slice(*p["NUM-LIVRO"])] == "A24         "    # CHAR à esquerda
    assert linha[slice(*p["PRI-TRIMES"])] == "0019506"        # NUM à direita
    assert linha[slice(*p["TNASCIDOS"])] == "00028"
    assert linha[slice(*p["REPETIDOS"])] == "0000"            # ausente vira zero


def test_o_numero_do_registro_alinha_a_esquerda_nos_modelos():
    """A especificação diz NUM; o arquivo que o IBGE aceitou diz outra coisa.

    Nos três modelos de registro ele vem `'19506  '`, com espaços à direita, e
    no RC-10 vem `'0019506'`. Os dois foram aceitos, e o que vale é o arquivo.
    """
    linha = IBGE.montar_linha(IBGE.NASCIMENTO, {"NUM-REGLIV": 19506})
    p = IBGE.posicoes(IBGE.NASCIMENTO)
    assert linha[slice(*p["NUM-REGLIV"])] == "19506  "


def test_campo_maior_que_o_tamanho_e_erro_e_nao_se_corta():
    """Cortar o número de um registro informa OUTRO registro."""
    with pytest.raises(IBGE.IbgeError, match="cabem"):
        IBGE.montar_linha(IBGE.NASCIMENTO, {"NUM-LIVRO": "A" * 13})


def test_o_arquivo_sai_em_latin1_com_crlf():
    """Acento em dois bytes empurraria todos os campos para a direita."""
    bruto = IBGE.escrever(IBGE.RC10, [{"NUM-LIVRO": "A24"}])
    assert bruto.endswith(b"\r\n")
    assert len(bruto) == IBGE.largura(IBGE.RC10) + 2


# ------------------------------------------------------ as tabelas de código


def test_o_catalogo_e_o_da_especificacao():
    assert IBGE.SEXO == {1: "masculino", 2: "feminino", 9: "ignorado"}
    assert set(IBGE.LOCAL_DO_NASCIMENTO) == {1, 2, 3, 5, 9}
    assert set(IBGE.GEMEO) == {1, 2, 3, 9}
    assert IBGE.BRASIL == "076"


def test_o_trimestre_sai_do_mes():
    assert [IBGE.trimestre_de(m) for m in (1, 3, 4, 6, 7, 9, 10, 12)] == \
        [1, 1, 2, 2, 3, 3, 4, 4]
    with pytest.raises(IBGE.IbgeError):
        IBGE.trimestre_de(13)


def test_idade_fora_da_faixa_vira_ignorada_e_nao_erro():
    """O acervo tem idade `01` em assento de mãe de quarenta e quatro anos.

    Dado velho e errado não pode impedir a remessa do trimestre inteiro.
    Mandar 99 diz a verdade: a casa não sabe.
    """
    assert IBGE.conferir_idade_da_genitora(27) == 27
    assert IBGE.conferir_idade_da_genitora(1) == 99
    assert IBGE.conferir_idade_da_genitora(70) == 99
    assert IBGE.conferir_idade_da_genitora(None) == 99
    assert IBGE.conferir_idade_da_genitora("") == 99


def test_os_dois_codigos_de_excecao_do_dia_estao_registrados():
    """`98` é registro anulado e `97` é adoção — eles não são datas."""
    assert IBGE.DIA_REGISTRO_ANULADO == 98
    assert IBGE.DIA_REGISTRO_ADOCAO == 97
    assert IBGE.TEXTO_DA_ADOCAO == "ADOCAO COM SEGUNDO REGISTRO"

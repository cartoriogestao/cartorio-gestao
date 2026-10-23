"""O MESMO CÓDIGO DO TJ REPETIDO TRÊS VEZES NA BUSCA DO BALCÃO.

ACHADO EM 21/09/2026, ORÇANDO UMA CÉDULA DE VERDADE — o protocolo 2026.09.46,
cédula de crédito bancário do BASA, R$ 695.404,50, garantida por penhor cedular
e alienação fiduciária da Fazenda Vale do Eden II. O item é o **16.45.23**.

O QUE SE MEDIU NO BANCO DA CASA, ANTES DE MEXER:

    servicos ao todo                                   1.317
    códigos do TJ que aparecem mais de uma vez           273
    códigos com MAIS DE UM preço na vigência               0

O `16.45.23` está nos serviços **732, 1064 e 1506**, e só o 1506 tem preço.
Dois efeitos, e o segundo é que trava:

1. **duas das três linhas não funcionam.** Clicar nelas devolve «Não encontrei
   esse ato na tabela vigente. Confira o código ou o valor do negócio» — a
   frase manda conferir o código justamente quando ele está certo;

2. **o ato pedido não aparecia de jeito nenhum.** A tela lista no máximo
   `LIMITE_DA_BUSCA_DE_ATOS = 30`; com três linhas por item, procurar `16.45`
   parava no `16.45.18`. O `16.45.23` ficava fora da lista, e quem estivesse no
   balcão concluiria que a tabela não tem o ato.

A SAÍDA É JUNTAR, E NÃO SUBIR O LIMITE. Subir o limite deixaria as duas linhas
mortas na tela — e a de cima, sem preço, é a que o olho pega primeiro. Juntar é
seguro porque **nenhum código do TJ tem dois preços na vigência**: a escolha
nunca decide entre dois valores.

E O RÓTULO DAS FAIXAS DIZIA A MESMA COISA QUATRO VEZES. As tabelas 6, 7, 8 e 9
saíam todas como «Registro de Imóveis» na caixa do «acrescentar pela faixa» —
quem precisa da faixa do crédito rural não tinha como distinguir da dos
registros torrens.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import emolumentos as EMOL

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

# O caso real, reduzido: o cabeçalho da faixa, três sub-itens, e cada um deles
# repetido três vezes como está no banco da casa. Só o terceiro tem preço.
CODIGOS = ("16.45.1", "16.45.18", "16.45.23")
DESCRICAO = ("Pelo Registro de constituição de direitos reais de garantia "
             "mobiliária e imobiliária destinados ao crédito rural")
PRECO = {"16.45.1": "105,61", "16.45.18": "4.253,21", "16.45.23": "12.976,81"}


def _tabela_com_os_repetidos(caminho) -> sqlite3.Connection:
    """A tabela do tribunal como ela está no banco da casa: cada código do TJ
    em três linhas de serviço, e o preço numa só."""
    con = conexao_de_teste()
    con.execute("""CREATE TABLE cx_vigencias (codigo INTEGER PRIMARY KEY,
                   vigente INTEGER NOT NULL DEFAULT 0)""")
    con.execute("""CREATE TABLE cx_servicos (codigo INTEGER PRIMARY KEY,
                   codigo_tj TEXT, descricao TEXT, descricao_norm TEXT,
                   ativo INTEGER NOT NULL DEFAULT 1)""")
    # Os quatro fundos entram na bancada porque `valor_do_servico` os lê: uma
    # bancada mais curta que a tabela real faria o teste do clique passar ao
    # largo do caminho que o botão «acrescentar» usa.
    con.execute("""CREATE TABLE cx_servico_valores (servico INTEGER,
                   vigencia INTEGER, emolumentos TEXT, ferc TEXT, femp TEXT,
                   fadep TEXT, ferrfis TEXT, total TEXT)""")
    con.execute("INSERT INTO cx_vigencias (codigo, vigente) VALUES (10022, 1)")
    servico = 700
    for codigo_tj in CODIGOS:
        for repeticao in range(3):
            servico += 1
            con.execute(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                            descricao_norm, ativo)
                   VALUES (?,?,?,?,1)""",
                (servico, codigo_tj, DESCRICAO, EMOL._norm(DESCRICAO)))
            if repeticao == 2:
                con.execute(
                    """INSERT INTO cx_servico_valores
                       (servico, vigencia, emolumentos, ferc, femp, fadep,
                        ferrfis, total)
                       VALUES (?, 10022, ?, '0,00','0,00','0,00','0,00', ?)""",
                    (servico, PRECO[codigo_tj], PRECO[codigo_tj]))
    con.commit()
    return con


# ----------------------------------------------------------------- a busca

def test_o_codigo_do_tj_aparece_uma_vez_so(tmp_path):
    """Nove linhas de serviço, três atos — e é isso que o balcão vê."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    achados = EMOL.buscar(con, "16.45")
    assert [a["codigo_tj"] for a in achados] == list(CODIGOS)


def test_a_linha_que_fica_e_a_que_tem_preco(tmp_path):
    """Ficar com a linha sem preço seria pior que repetir: ela é clicável, e o
    clique devolve «não encontrei esse ato»."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    for achado in EMOL.buscar(con, "16.45"):
        assert achado["total"] == PRECO[achado["codigo_tj"]], \
            f"{achado['codigo_tj']} ficou com a linha morta"


def test_a_linha_que_fica_e_a_que_o_clique_calcula(tmp_path):
    """**O guarda que importa.** Não basta a lista mostrar um preço: o número
    do serviço que ela manda no formulário tem de ser o que `calcular_item`
    resolve — é ele que o botão «acrescentar» posta."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    for achado in EMOL.buscar(con, "16.45"):
        item = EMOL.calcular_item(con, servico=achado["codigo"])
        assert item is not None, \
            f"a lista oferece {achado['codigo_tj']} e o clique recusa"
        assert item["total"] == PRECO[achado["codigo_tj"]]


def test_o_limite_conta_atos_e_nao_linhas_repetidas(tmp_path):
    """O que travava o orçamento da cédula: com o limite contando as repetidas,
    o ato pedido ficava fora da lista."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    achados = EMOL.buscar(con, "16.45", limite=3)
    assert len(achados) == 3
    assert "16.45.23" in [a["codigo_tj"] for a in achados], \
        "o último ato da faixa ficou fora do limite por causa das repetidas"


def test_o_limite_continua_valendo(tmp_path):
    """Juntar as repetidas não é devolver a tabela inteira."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    assert len(EMOL.buscar(con, "16.45", limite=2)) == 2


def test_ato_sem_preco_nao_aparece_na_lista(tmp_path):
    """Listar sem preço convida o clique que falha («não encontrei na vigente»).
    Medido em 24/09/2026 com o serviço 713 inativo na busca «nascimento»."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    con.execute(
        """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                    descricao_norm, ativo)
           VALUES (999, '16.45.99', ?, ?, 1)""",
        (DESCRICAO, EMOL._norm(DESCRICAO)))
    achados = {a["codigo_tj"]: a for a in EMOL.buscar(con, "16.45")}
    assert "16.45.99" not in achados


def test_servico_inativo_nao_aparece(tmp_path):
    """ativo=0 (ex.: 713 «1º via nascimento…») não entra na lista do balcão."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    con.execute(
        """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                    descricao_norm, ativo)
           VALUES (713, '14.x', '1 via nascimento/obito/casamento', ?, 0)""",
        (EMOL._norm("1 via nascimento/obito/casamento"),))
    for a in EMOL.buscar(con, "nascimento"):
        assert a["codigo"] != 713
        assert a.get("ativo")


def test_alias_segunda_via_traz_14_5_1(tmp_path):
    """«2 via» / «segunda via» mapeiam para 14.5.1 — descrição TJ é outra."""
    con = _tabela_com_os_repetidos(tmp_path / "tabela.sqlite3")
    con.execute(
        """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                    descricao_norm, ativo)
           VALUES (682, '14.5.1', 'Das certidoes: Com uma folha', ?, 1)""",
        (EMOL._norm("Das certidoes: Com uma folha"),))
    con.execute(
        """INSERT INTO cx_servico_valores
               (servico, vigencia, emolumentos, ferc, femp, fadep, ferrfis, total)
           VALUES (682, 10022, '47,84', '0,00','0,00','0,00','0,00', '53,58')""")
    con.commit()
    for termo in ("2 via", "2a via", "segunda via", "certidao nascimento"):
        codigos = [a["codigo_tj"] for a in EMOL.buscar(con, termo)]
        assert "14.5.1" in codigos, f"{termo!r} nao trouxe 14.5.1: {codigos}"


# ------------------------------------------------------- o rótulo das faixas

def test_cada_tabela_de_faixa_diz_de_que_ato_e():
    """Quatro rótulos iguais numa caixa de escolha não escolhem nada."""
    rotulos = list(EMOL.TABELAS_FAIXA.values())
    assert len(set(rotulos)) == len(rotulos), "há rótulo repetido"
    for codigo, rotulo in EMOL.TABELAS_FAIXA.items():
        depois_do_item = rotulo.split("—", 1)[1]
        assert depois_do_item.strip() != "Registro de Imóveis", \
            f"a tabela {codigo} não diz de que ato é"


def test_a_faixa_do_credito_rural_se_acha_pelo_nome():
    """É a que a cédula usa, e o balcão a procura pelo que ela é — não pelo
    número do item, que é justamente o que ele ainda não sabe."""
    rotulo = EMOL.TABELAS_FAIXA[9].lower()
    assert "crédito rural" in rotulo

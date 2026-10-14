"""O ITEM DO PROTOCOLO SE GASTA POR UNIDADE — 15/09/2026.

    «a prenotacao 11571 e o protocolo 2026.09.23 nao estao permitindo que eu
     use um selo de averbacao para o ato que preciso, ainda que conste no
     protocolo 5 atos de averbacao sem valor»

O QUE ESTAVA ACONTECENDO. O item do protocolo dele é «De ato sem valor
    declarado», código `16.22.2`, **quantidade 5** — R$ 672,15, cinco
    averbações. A tela de lavrar listava os itens com

        WHERE protocolo_id=? AND usado_em IS NULL

    e o consumo marcava `usado_em` na **linha inteira**. A AV-04 gastou o item
    todo: as outras quatro averbações ficaram sem item para apontar, e o
    balcão não conseguia selar.

O TAMANHO, medido na produção antes de escrever uma linha:

    | | |
    |---|---|
    | itens com quantidade > 1 já marcados | **4** |
    | unidades perdidas | **83** |
    | a maior | quantidade **66** (arquivamento do RTD/RCPJ), gasta por um ato |

    Não era um caso: era toda vez que um protocolo trazia mais de uma unidade
    do mesmo item — que é o normal quando se pede cinco averbações de uma vez.

E A REGRA DA CASA JÁ DIZIA ISSO. `CLAUDE.md`: «a conta é por unidade — o
    protocolo 2026.08.103 abriu um item 13.18 com quantidade 10, e saíram 10
    selos». O contador é que faltava.

AS 83 UNIDADES VOLTAM SEM MIGRAR DADO NENHUM, e isso é deliberado: `_usadas`
    lê `usado_em` preenchido com `quantidade_usada` vazio como **uma** unidade
    gasta — o item antigo, marcado antes de o contador existir. Um script de
    reparo teria de adivinhar quantas foram; a leitura não adivinha nada.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import caixa_protocolo as CXPROT


def _banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE cx_protocolo_atos(
            id INTEGER PRIMARY KEY, protocolo_id INTEGER, descricao TEXT,
            codigo_ato TEXT, quantidade INTEGER, valor_total TEXT,
            servico_codigo INTEGER, quantidade_usada INTEGER,
            usado_em TEXT, usado_por_ato_id INTEGER, usado_por_tabela TEXT);
    """)
    return con


def _item(con, **kw):
    campos = {"id": 1, "protocolo_id": 9, "descricao": "De ato sem valor declarado",
              "codigo_ato": "16.22.2", "quantidade": 5, "valor_total": "672,15",
              "servico_codigo": 504, "quantidade_usada": None,
              "usado_em": None, "usado_por_ato_id": None,
              "usado_por_tabela": None}
    campos.update(kw)
    with con:
        con.execute(
            "INSERT INTO cx_protocolo_atos VALUES (:id,:protocolo_id,"
            ":descricao,:codigo_ato,:quantidade,:valor_total,:servico_codigo,"
            ":quantidade_usada,:usado_em,:usado_por_ato_id,:usado_por_tabela)",
            campos)
    return campos["id"]


def _linha(con, item_id):
    return con.execute("SELECT * FROM cx_protocolo_atos WHERE id=?",
                       (item_id,)).fetchone()


# ------------------------------------------------ o caso que fez isto nascer


def test_cinco_averbacoes_servem_a_cinco_atos():
    """O protocolo 2026.09.23, com o item de quantidade 5."""
    con = _banco()
    _item(con)
    for enesima in range(1, 6):
        disponiveis = CXPROT.itens_disponiveis(con, 9)
        assert disponiveis, f"o item sumiu antes da {enesima}ª averbação"
        assert disponiveis[0]["saldo"] == 6 - enesima
        with con:
            assert CXPROT.consumir_item(con, 1, ato_id=100 + enesima,
                                        tabela="ri_atos",
                                        agora="2026-09-15T10:00:00") == 1
    assert CXPROT.itens_disponiveis(con, 9) == [], (
        "gastas as cinco, o item sai da lista — e só então")


def test_o_item_antigo_conta_como_uma_unidade_gasta():
    """As 83 unidades voltam sem migrar dado nenhum.

    `usado_em` preenchido com `quantidade_usada` vazio é o item marcado antes
    de o contador existir: vale UMA, e não o item inteiro.
    """
    con = _banco()
    _item(con, quantidade=66, usado_em="2026-09-11T23:28:33",
          usado_por_ato_id=80, quantidade_usada=None)
    assert CXPROT.saldo_do_item(_linha(con, 1)) == 65
    assert CXPROT.itens_disponiveis(con, 9)[0]["saldo"] == 65


def test_item_de_uma_unidade_continua_saindo_apos_o_primeiro_uso():
    """O caminho de sempre não muda: a maioria dos itens é de um."""
    con = _banco()
    _item(con, quantidade=1)
    with con:
        CXPROT.consumir_item(con, 1, ato_id=7, tabela="ri_atos",
                             agora="2026-09-15T10:00:00")
    assert CXPROT.itens_disponiveis(con, 9) == []
    assert _linha(con, 1)["usado_em"] == "2026-09-15T10:00:00"


# --------------------------------------------------------- o que ele recusa


def test_nao_gasta_mais_do_que_ha():
    """Negativo em contador de unidade só aparece meses depois, ao somar."""
    con = _banco()
    _item(con, quantidade=3)
    with con:
        assert CXPROT.consumir_item(con, 1, ato_id=1, tabela="ri_atos",
                                    agora="x", quantas=10) == 3
    assert CXPROT.saldo_do_item(_linha(con, 1)) == 0
    with con:
        assert CXPROT.consumir_item(con, 1, ato_id=2, tabela="ri_atos",
                                    agora="y") == 0


def test_item_que_nao_existe_nao_estoura():
    con = _banco()
    with con:
        assert CXPROT.consumir_item(con, 999, ato_id=1, tabela="ri_atos",
                                    agora="x") == 0


def test_item_sem_quantidade_vale_uma():
    con = _banco()
    _item(con, quantidade=None)
    assert CXPROT.saldo_do_item(_linha(con, 1)) == 1


# ------------------------------------------------------------- o rastro


def test_o_rastro_guarda_o_PRIMEIRO_ato_e_nao_o_ultimo():
    """`usado_em` e `usado_por_ato_id` dizem quando o item começou a ser gasto.

    Sobrescrevê-los a cada ato faria a data andar e o primeiro sumir do
    rastro — e a ficha do protocolo mostra justamente isso.
    """
    con = _banco()
    _item(con, quantidade=3)
    with con:
        CXPROT.consumir_item(con, 1, ato_id=11, tabela="ri_atos",
                             agora="2026-09-15T10:00:00")
        CXPROT.consumir_item(con, 1, ato_id=22, tabela="ri_atos",
                             agora="2026-09-15T11:00:00")
    r = _linha(con, 1)
    assert r["usado_por_ato_id"] == 11
    assert r["quantidade_usada"] == 2
    assert r["usado_em"] is None, (
        "com saldo, o item ainda não acabou — `usado_em` é a última unidade")
    with con:
        CXPROT.consumir_item(con, 1, ato_id=33, tabela="ri_atos",
                             agora="2026-09-15T12:00:00")
    r = _linha(con, 1)
    assert r["usado_em"] == "2026-09-15T12:00:00", (
        "a última unidade fecha o item, e é aí que `usado_em` vale")
    assert r["usado_por_ato_id"] == 11, "o rastro continua sendo o do primeiro"


# ------------------------------------------- a regra mora num lugar só


def _so_o_codigo(arquivo: str) -> str:
    """O módulo sem comentário nem docstring. Só lê.

    **VARREDOR DE CÓDIGO NÃO PODE LER PROSA** — é a décima terceira vez que
    esta casa tropeça nisso, e desta vez a prosa era minha: o comentário que
    explica o conserto cita `usado_em IS NULL` justamente para dizer que aquilo
    saiu. Procurar a frase no arquivo inteiro acusava a explicação.
    """
    import ast
    árvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
    for nó in ast.walk(árvore):
        if (isinstance(nó, (ast.Module, ast.ClassDef, ast.FunctionDef,
                            ast.AsyncFunctionDef))
                and ast.get_docstring(nó) is not None):
            nó.body = nó.body[1:]
    return ast.unparse(árvore)


def test_o_ri_e_o_rcpj_leem_a_mesma_regra():
    """Duas cópias divergiriam no primeiro conserto — foi assim que nasceu."""
    ri = _so_o_codigo("ri_web.py")
    assert "CXPROT.consumir_item(" in ri, (
        "o RI voltou a marcar `usado_em` na linha inteira")
    assert "SET usado_em=?, usado_por_ato_id=?, usado_por_tabela=?" not in ri, (
        "sobrou no RI o UPDATE que gastava o item inteiro")
    teor = _so_o_codigo("ri_lavrar_teor.py")
    assert "CXPROT.itens_disponiveis(" in teor
    assert "usado_em IS NULL" not in teor, (
        "a lista voltou a esconder o item que ainda tem saldo")


def test_a_coluna_do_contador_esta_declarada_na_migracao():
    esquema = (RAIZ / "caixa_schema.py").read_text(encoding="utf-8")
    assert '("cx_protocolo_atos", "quantidade_usada", "INTEGER")' in esquema, (
        "sem a migração, instalação existente não ganha o contador")

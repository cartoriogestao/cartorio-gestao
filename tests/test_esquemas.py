"""
Guardas sobre os esquemas do banco — as armadilhas que já custaram caro.

POR QUE ESTE ARQUIVO EXISTE
    Em 25/08/2026 eu pus um índice sobre coluna de migração dentro do `SCHEMA`.
    Em banco novo funciona: o `CREATE TABLE` ali em cima já cria a coluna. Em
    banco que **já existia**, o `CREATE TABLE IF NOT EXISTS` não faz nada, a
    coluna só aparece no `ALTER TABLE` mais abaixo — e o `CREATE INDEX` estoura
    com "no such column" **na hora de abrir o banco**.

    Consertei, escrevi o comentário explicando… e repeti o mesmo erro na mesma
    tarde, com outra coluna. Comentário não impede; teste impede.

    Nenhum outro teste do projeto vê isto, porque todos montam banco do zero.
    É o parente do que o ensaio de 25/08 já tinha mostrado: **teste sobre banco
    novo não vê defeito de banco velho.**

O GUARDA É ESTÁTICO, E ISSO FOI ESCOLHA
    Tentei primeiro o caminho dinâmico — montar o banco, arrancar as colunas de
    migração com `ALTER TABLE DROP COLUMN` e subir a atualização por cima. Ele
    esbarra num limite do próprio SQLite: `DROP COLUMN` reescreve o DDL da
    tabela e não sabe lidar com o comentário que vem antes da coluna, e este
    projeto comenta os esquemas de propósito.

    O guarda estático pega exatamente o mesmo defeito — índice do `SCHEMA`
    sobre coluna de migração — sem depender de o SQLite conseguir reescrever
    DDL comentado. Teste frágil que cobre mais é pior que teste firme que cobre
    o que interessa.
"""
from __future__ import annotations

import importlib
import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# A MESMA ORDEM DE `database.py`, e não uma inventada aqui: o núcleo primeiro,
# porque as outras apontam para ele; o Livro 3 depois do RI, de cujo contador
# ele conta; o usucapião depois do RI, para onde ele aponta.
ORDEM = (
    ("nucleo_schema", "init_nucleo_schema"),
    ("pt_schema", "init_pt_schema"),
    ("rc_schema", "init_rc_schema"),
    ("ajuda", "init_ajuda_schema"),
    ("selador_config", "init_selador_schema"),
    ("ri_schema", "init_ri_schema"),
    ("ra_schema", "init_ra_schema"),
    ("us_schema", "init_us_schema"),
    ("caixa_schema", "init_caixa_schema"),
    ("rg_schema", "init_rg_schema"),
    ("atrib_certidao", "init_atrib_certidao_schema"),
    ("notas_schema", "init_notas_schema"),
    ("automacao_schema", "init_automacao_schema"),
)


def _banco_inteiro(tmp_path) -> sqlite3.Connection:
    """O banco como a producao o tem: montado por `Database`, e nao a mao.

    Nao basta chamar os `init_*` em ordem: `users` e as tabelas base nascem no
    proprio `Database`, e ha migracao que as toca — `caixa_schema` acrescenta
    coluna em `users`. Montar a mao daria um banco que nao existe em lugar
    nenhum, e o teste falaria de outra coisa.
    """
    from database import Database
    caminho = tmp_path / "b.sqlite3"
    Database(caminho)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    return con


def _com_migracao():
    for modulo, _funcao in ORDEM:
        mod = importlib.import_module(modulo)
        if getattr(mod, "MIGRACOES", ()):
            yield modulo, mod


def test_o_banco_inteiro_sobe_e_fica_integro(tmp_path):
    con = _banco_inteiro(tmp_path)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not list(con.execute("PRAGMA foreign_key_check"))
    # Rodar de novo não pode estourar: `init_*` é idempotente por contrato.
    for modulo, funcao in ORDEM:
        getattr(importlib.import_module(modulo), funcao)(con)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_indice_do_schema_nao_toca_coluna_de_migracao():
    """A armadilha que estourava ao abrir banco de versão anterior.

    Índice sobre coluna que só existe depois do `ALTER TABLE` tem de morar em
    `INDICES_DEPOIS_DA_MIGRACAO`, e não no `SCHEMA`.
    """
    achados = []
    for nome, mod in _com_migracao():
        schema = getattr(mod, "SCHEMA", "") or ""
        indices = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX[^;]+", schema,
                             re.IGNORECASE)
        for tabela, coluna, _tipo in mod.MIGRACOES:
            for indice in indices:
                if re.search(rf"\b{re.escape(coluna)}\b", indice) \
                        and tabela in indice:
                    achados.append(
                        f"{nome}: o índice sobre `{coluna}` de `{tabela}` está "
                        f"no SCHEMA, e essa coluna só existe depois do "
                        f"ALTER TABLE. Mova para INDICES_DEPOIS_DA_MIGRACAO.")
    assert not achados, "\n".join(achados)


def test_a_migracao_so_acrescenta_coluna():
    """`MIGRACOES` é só `ALTER TABLE ADD COLUMN` — regra da casa.

    O tipo declarado não pode trazer `NOT NULL` sem `DEFAULT`: o SQLite recusa
    acrescentar coluna assim numa tabela que já tem linha, e o banco de
    produção tem 116 MB delas.
    """
    problemas = []
    for nome, mod in _com_migracao():
        for tabela, coluna, tipo in mod.MIGRACOES:
            t = tipo.upper()
            if "NOT NULL" in t and "DEFAULT" not in t:
                problemas.append(
                    f"{nome}: `{coluna}` de `{tabela}` é NOT NULL sem DEFAULT — "
                    f"o ALTER TABLE falha sobre tabela com linhas.")
            if any(p in t for p in ("PRIMARY KEY", "UNIQUE")):
                problemas.append(
                    f"{nome}: `{coluna}` de `{tabela}` pede {t}, e o SQLite não "
                    f"acrescenta coluna com isso.")
    assert not problemas, "\n".join(problemas)


def test_a_migracao_nao_declara_a_mesma_coluna_duas_vezes():
    """Entrada repetida não quebra — o `init_*` a ignora —, mas mente.

    `caixa_schema` declara `cx_depositos.atualizado_em` duas vezes; achado em
    25/08/2026. Lista de migração é registro do que mudou, e registro com linha
    repetida faz quem lê contar errado.
    """
    repetidas = []
    for nome, mod in _com_migracao():
        vistos = set()
        for tabela, coluna, _tipo in mod.MIGRACOES:
            if (tabela, coluna) in vistos:
                repetidas.append(f"{nome}: `{coluna}` de `{tabela}`")
            vistos.add((tabela, coluna))
    assert not repetidas, "declarada duas vezes: " + "; ".join(repetidas)


def test_a_coluna_da_migracao_existe_no_schema_tambem(tmp_path):
    """Banco NOVO tem de nascer com ela, sem depender do `ALTER TABLE`.

    `MIGRACOES` serve ao banco que já existe; o `SCHEMA` serve ao que nasce.
    Faltar num dos dois faz o sistema andar diferente conforme a idade do
    banco — e é a diferença que ninguém testa.
    """
    con = _banco_inteiro(tmp_path)
    faltando = []
    for _nome, mod in _com_migracao():
        for tabela, coluna, _tipo in mod.MIGRACOES:
            colunas = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
            if coluna not in colunas:
                faltando.append(f"`{coluna}` não existe em `{tabela}`")
    assert not faltando, "\n".join(faltando)

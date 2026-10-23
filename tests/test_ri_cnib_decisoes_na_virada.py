"""O UNIQUE de `ri_cnib_decisoes` chega à virada com o nome do código — lote LH10, 21/10/2026.

O QUE O ENSAIO DE 21/10 MOSTROU (banco real, só contagem): a comparação do
esquema (código × migrado), que é por NOME de índice, achou faltando
`ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_documen_key`, o UNIQUE de
`ri_schema.py`. A chave estava lá com outro nome: a carga
(`tools/migrar_para_postgres.py`, `nome_curto`) encurta nome de mais de 63
bytes com um hash, e o PostgreSQL, que nomeia o UNIQUE do CREATE TABLE do
código, corta as colunas e põe `_key`. No schema.sql do servidor de 18/10 ele é
`ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_do_3bbea59d`.

O `tools/ajuste_pos_migracao.sql` (bloco 3b) deixa o UNIQUE com o nome do
código. Estes testes passam por cada caminho dele, pela carga e pelo psql de
verdade, num SQLite de fixture sem dado real (`virada_de_teste.py`):
    - o nome do ajuste é o que o PostgreSQL dá ao UNIQUE do código;
    - UNIQUE com o nome do hash: renomeia, sem tocar em linha;
    - índice único à parte: vira a restrição;
    - sem nada único e sem repetição: cria (no modo padrão);
    - com repetição, no modo padrão: para, diz quantas, e nada muda;
    - com repetição, no modo guardar: fica a de menor id (a que o código lê
      primeiro) e as outras vão INTEIRAS para `cg_ajuste_guardados`;
    - a carga que caiu no índice comum por repetição: o ajuste troca o comum
      pelo UNIQUE.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import virada_de_teste as V  # noqa: E402
from virada_de_teste import virada  # noqa: E402,F401  (a fixture)
from banco_de_teste import conexao_de_teste  # noqa: E402

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402

pytestmark = pytest.mark.skipif(not banco_pg.ativo(), reason="a virada é para o PostgreSQL")

NOME_DO_HASH = "ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_do_3bbea59d"
DEFINICAO = "UNIQUE (matricula_id, protocolo_cnib, pessoa_documento, pessoa_nome)"


def _decisoes(schema: str) -> list[tuple]:
    return [tuple(r.values()) for r in V.sql(schema, "SELECT * FROM ri_cnib_decisoes ORDER BY id")]


def _do_sqlite(arquivo: Path, filtro: str = "") -> list[tuple]:
    """As decisões do arquivo, com bytes lidos como o texto que são."""
    return [tuple(v.decode("utf-8") if isinstance(v, bytes) else v for v in linha)
            for linha in V.ler_sqlite(arquivo, f"SELECT * FROM ri_cnib_decisoes {filtro} ORDER BY id")]


def _unique_do_codigo(schema: str) -> dict:
    return {nome: d for nome, d in V.restricoes(schema, "ri_cnib_decisoes").items()
            if d.startswith("UNIQUE")}


def test_o_nome_no_ajuste_e_o_que_o_postgresql_da_ao_unique_do_codigo():
    import ri_schema
    con = conexao_de_teste()
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    ri_schema.init_ri_schema(con)
    con.commit()
    nomes = [r["conname"] for r in banco(con).ler(
        "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass('ri_cnib_decisoes') "
        "AND contype = 'u' ORDER BY conname")]
    con.close()
    ajuste = V.AJUSTE.read_text(encoding="utf-8")
    no_ajuste = re.findall(r"\('ri_cnib_decisoes', '([^']+)',", ajuste)
    assert nomes == no_ajuste == [V.UNIQUE_DO_CODIGO]


def test_o_nome_que_a_carga_da_e_o_do_esquema_do_servidor_de_18_10(monkeypatch):
    """A causa, medida na ferramenta: o `nome_curto` da carga."""
    spec = importlib.util.spec_from_file_location("migrar_para_postgres_lh10", V.CARGA)
    carga = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, carga)   # as dataclasses dela se procuram ali
    spec.loader.exec_module(carga)
    longo = "ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_documento_pessoa_nome_key"
    assert carga.nome_curto(longo, set()) == NOME_DO_HASH


def test_unique_com_o_nome_do_hash_e_renomeado_sem_tocar_em_linha(virada):
    arquivo = V.montar_sqlite(virada.pasta, "unico")
    assert V.carregar(arquivo, virada.schema, "--recriar").returncode == 0
    assert _unique_do_codigo(virada.schema) == {NOME_DO_HASH: DEFINICAO}

    feito = V.rodar_sql(V.AJUSTE, virada.schema, nao_numericos="guardar")
    assert feito.returncode == 0, feito.saida
    assert f"{NOME_DO_HASH} renomeado para {V.UNIQUE_DO_CODIGO}" in feito.saida
    assert _unique_do_codigo(virada.schema) == {V.UNIQUE_DO_CODIGO: DEFINICAO}
    assert _decisoes(virada.schema) == _do_sqlite(arquivo)
    assert ("ri_cnib_decisoes", "*") not in V.guardados(virada.schema)
    # a decisão repetida é recusada, e o erro diz o nome do código
    with pytest.raises(Exception, match=V.UNIQUE_DO_CODIGO):
        V.sql(virada.schema, "INSERT INTO ri_cnib_decisoes (matricula_id, protocolo_cnib, "
                             "pessoa_nome, pessoa_documento, decisao, decidido_em) VALUES "
                             "(1, 'CNIB-0001', 'PEDRO EXEMPLO DOS SANTOS', '00000000191', 'AVERBADA', "
                             "'2026-10-21T10:00:00')")

    de_novo = V.rodar_sql(V.AJUSTE, virada.schema, nao_numericos="guardar")
    assert de_novo.returncode == 0, de_novo.saida
    assert "renomeado" not in de_novo.saida
    assert _unique_do_codigo(virada.schema) == {V.UNIQUE_DO_CODIGO: DEFINICAO}


def test_indice_unico_a_parte_vira_a_restricao_com_o_nome_do_codigo(virada):
    arquivo, feito = V.ate_o_ajuste(virada, "indice_unico", limpo=True)
    assert feito.returncode == 0, feito.saida
    assert f"o índice único ux_cnib_decisao virou a restrição {V.UNIQUE_DO_CODIGO}" in feito.saida
    assert _unique_do_codigo(virada.schema) == {V.UNIQUE_DO_CODIGO: DEFINICAO}
    assert set(V.indices(virada.schema, "ri_cnib_decisoes")) == {
        "ri_cnib_decisoes_pkey", V.UNIQUE_DO_CODIGO}
    assert _decisoes(virada.schema) == _do_sqlite(arquivo)


def test_sem_repeticao_o_ajuste_no_modo_padrao_cria_o_unique(virada):
    arquivo, feito = V.ate_o_ajuste(virada, "sem_unico", limpo=True)
    assert feito.returncode == 0, feito.saida
    assert f"criado: {V.UNIQUE_DO_CODIGO}" in feito.saida
    assert _unique_do_codigo(virada.schema) == {V.UNIQUE_DO_CODIGO: DEFINICAO}
    assert _decisoes(virada.schema) == _do_sqlite(arquivo)
    assert not V.tem_tabela(virada.schema, "cg_ajuste_guardados")


def test_com_repeticao_o_ajuste_no_modo_padrao_para_diz_quantas_e_nada_muda(virada):
    arquivo, feito = V.ate_o_ajuste(virada, "repetida", limpo=True)
    assert feito.returncode != 0, feito.saida
    assert "AJUSTE ABORTADO, NADA FOI ALTERADO" in feito.saida
    # 3 e 4 repetem a 1; 5 e 6 têm o documento NULL e não repetem nada
    assert ("ri_cnib_decisoes: 2 linha(s) repetida(s) na chave do UNIQUE (matricula_id, "
            "protocolo_cnib, pessoa_documento, pessoa_nome), em 1 grupo(s)") in feito.saida
    assert _decisoes(virada.schema) == _do_sqlite(arquivo)
    assert _unique_do_codigo(virada.schema) == {}
    assert not V.tem_tabela(virada.schema, "cg_ajuste_guardados")


def test_com_repeticao_no_modo_guardar_fica_a_de_menor_id_e_as_outras_sao_guardadas_inteiras(virada):
    arquivo, feito = V.ate_o_ajuste(virada, "repetida", nao_numericos="guardar")
    assert feito.returncode == 0, feito.saida
    s = virada.schema
    assert _unique_do_codigo(s) == {V.UNIQUE_DO_CODIGO: DEFINICAO}
    # a 1 é a que `resolver_ocorrencia` lê (ORDER BY id LIMIT 1); 5 e 6 ficam
    assert _decisoes(s) == _do_sqlite(arquivo, "WHERE id IN (1, 2, 5, 6)")
    guardadas = V.guardados(s)[("ri_cnib_decisoes", "*")]
    assert sorted(guardadas) == [3, 4]
    # a linha inteira, e restaurável: o JSON volta à mesma linha
    colunas = [r["column_name"] for r in V.sql(
        s, "SELECT column_name FROM information_schema.columns WHERE table_schema = "
           "current_schema() AND table_name = 'ri_cnib_decisoes' ORDER BY ordinal_position")]
    originais = _do_sqlite(arquivo, "WHERE id IN (3, 4)")
    assert [json.loads(guardadas[i]) for i in (3, 4)] == [dict(zip(colunas, o)) for o in originais]
    restauradas = [tuple(r.values()) for r in V.sql(
        s, "SELECT (json_populate_record(NULL::ri_cnib_decisoes, valor_original::json)).* "
           "FROM cg_ajuste_guardados WHERE tabela = 'ri_cnib_decisoes' AND coluna = '*' "
           "ORDER BY linha_id")]
    assert restauradas == originais
    assert "guardados: ri_cnib_decisoes.* = 2 linha(s)" in feito.saida

    de_novo = V.rodar_sql(V.AJUSTE, s, nao_numericos="guardar")
    assert de_novo.returncode == 0, de_novo.saida
    assert _decisoes(s) == _do_sqlite(arquivo, "WHERE id IN (1, 2, 5, 6)")
    assert sorted(V.guardados(s)[("ri_cnib_decisoes", "*")]) == [3, 4]


def test_quando_a_carga_cai_no_indice_comum_o_ajuste_poe_o_unique_e_tira_o_comum(virada):
    arquivo = V.montar_sqlite(virada.pasta, "bytes")
    carga = V.carregar(arquivo, virada.schema, "--recriar")
    assert carga.returncode == 0, carga.saida
    relatorio = (virada.pasta / "relatorio_carga.md").read_text(encoding="utf-8")
    assert "| `ri_cnib_decisoes` | matricula_id, protocolo_cnib, pessoa_documento, pessoa_nome | UNIQUE | 1 | 2 |" in relatorio
    assert V.indices(virada.schema, "ri_cnib_decisoes")[NOME_DO_HASH][0] is False

    feito = V.rodar_sql(V.AJUSTE, virada.schema, nao_numericos="guardar")
    assert feito.returncode == 0, feito.saida
    assert f"índice comum {NOME_DO_HASH}" in feito.saida
    assert set(V.indices(virada.schema, "ri_cnib_decisoes")) == {
        "ri_cnib_decisoes_pkey", V.UNIQUE_DO_CODIGO}
    assert _unique_do_codigo(virada.schema) == {V.UNIQUE_DO_CODIGO: DEFINICAO}
    assert _decisoes(virada.schema) == _do_sqlite(arquivo, "WHERE id IN (1, 2)")
    assert sorted(V.guardados(virada.schema)[("ri_cnib_decisoes", "*")]) == [3]

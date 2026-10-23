"""O ajuste da virada roda no banco que a carga deixou — lote LH10, 21/10/2026.

`tools/ajuste_pos_migracao.sql` é o passo B4 do roteiro: depois da carga
(`tools/migrar_para_postgres.py`) e antes de subir o código, ele põe as 13
colunas no tipo do código, recria as 2 FKs para `users`, a collation do login, as
sequências e o UNIQUE de `ri_cnib_decisoes` (este último em
`test_ri_cnib_decisoes_na_virada.py`). Até o LH10 ele só existia fora da branch,
no pacote do servidor, e nunca tinha rodado num teste.

O QUE ESTES TESTES GUARDAM (num SQLite de fixture, sem dado real — ver
`virada_de_teste.py`), pelo psql, como o roteiro roda:
    - no modo padrão (abortar), o texto que não converte PARA o ajuste, diz
      quantos valores e em que coluna, e nada muda;
    - no modo guardar (a decisão do oficial de 18/10), cada valor que não
      converte vai para `cg_ajuste_guardados` com o original e a coluna fica
      NULL; o que converte, converte; o login em `ri_atos.lavrado_por` vira o
      id; as FKs entram validadas;
    - rodar duas vezes não dá erro e não muda nada (nem no modo padrão, depois).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import virada_de_teste as V  # noqa: E402
from virada_de_teste import virada  # noqa: E402,F401  (a fixture)

import banco_pg  # noqa: E402

pytestmark = pytest.mark.skipif(not banco_pg.ativo(), reason="a virada é para o PostgreSQL")

TIPOS_DO_CODIGO = {
    ("nt_ato_partes", "conjuge_tipo"): "bigint", ("nt_atos", "filhos_maiores"): "bigint",
    ("ri_atos", "lavrado_por"): "bigint", ("ri_matriculas", "criado_por"): "bigint",
    ("audit_logs", "entity_id"): "bigint",
    ("cx_depositos", "criado_por"): "text", ("cx_recibos", "cancelado_por"): "text",
    ("nt_autenticacoes", "criado_por"): "text", ("nt_cartoes", "criado_por"): "text",
    ("nt_reconhecimentos", "criado_por"): "text", ("rg_encaminhamentos", "criado_por"): "text",
    ("ri_ctp_itens", "atualizado_por"): "text", ("ri_matriculas", "conferido_por"): "text",
}


def _fotografia(schema: str) -> dict:
    """Tudo o que o ajuste mexe: valores das 13 colunas, guardados, tipos,
    restrições, índices de `users` e de `ri_cnib_decisoes` e o próximo id."""
    valores = {}
    for (tabela, coluna) in TIPOS_DO_CODIGO:
        valores[(tabela, coluna)] = [tuple(r.values()) for r in V.sql(
            schema, f"SELECT id, {coluna} AS v FROM {tabela} ORDER BY id")]
    return {
        "valores": valores,
        "guardados": V.guardados(schema),
        "tipos": {k: V.tipo_da_coluna(schema, *k) for k in TIPOS_DO_CODIGO},
        "restricoes": {t: V.restricoes(schema, t) for t in ("users", "ri_atos", "ri_matriculas",
                                                             "ri_cnib_decisoes")},
        "indices": {t: V.indices(schema, t) for t in ("users", "ri_cnib_decisoes")},
        "sequencias": V.sql(schema, "SELECT sequencename, last_value FROM pg_sequences "
                                    "WHERE schemaname = current_schema() ORDER BY sequencename"),
        "cnib": V.sql(schema, "SELECT * FROM ri_cnib_decisoes ORDER BY id"),
    }


def test_no_modo_padrao_o_texto_que_nao_converte_para_o_ajuste_e_nada_muda(virada):
    _, feito = V.ate_o_ajuste(virada)
    assert feito.returncode != 0, feito.saida
    assert "AJUSTE ABORTADO, NADA FOI ALTERADO" in feito.saida
    assert "ri_matriculas.criado_por: 6 valor(es) que não são número inteiro" in feito.saida
    assert "nt_atos.filhos_maiores: 1 valor(es)" in feito.saida
    assert "audit_logs.entity_id: 1 valor(es)" in feito.saida
    # a transação inteira voltou: a coluna continua texto, com o texto
    assert V.tipo_da_coluna(virada.schema, "ri_matriculas", "criado_por") == "text"
    assert V.tipo_da_coluna(virada.schema, "cx_depositos", "criado_por") == "bigint"
    assert not V.tem_tabela(virada.schema, "cg_ajuste_guardados")
    assert [r["criado_por"] for r in V.sql(
        virada.schema, "SELECT criado_por FROM ri_matriculas WHERE id IN (2, 5) ORDER BY id")] == [
        V.CASA_COM_UM, V.NAO_CASA]
    # e o UNIQUE de ri_cnib_decisoes continua com o nome que a carga deu
    assert V.UNIQUE_DO_CODIGO not in V.restricoes(virada.schema, "ri_cnib_decisoes")


def test_no_modo_guardar_o_que_nao_converte_e_guardado_com_o_original_e_anulado(virada):
    _, feito = V.ate_o_ajuste(virada, nao_numericos="guardar")
    assert feito.returncode == 0, feito.saida
    assert "ajuste_pos_migracao.sql: CONCLUÍDO" in feito.saida
    assert "tipos: 13 de 13 OK" in feito.saida
    assert "guardados: TOTAL = 10 linha(s)" in feito.saida

    assert V.guardados(virada.schema) == V.GUARDAVEIS
    s = virada.schema
    assert {k: V.tipo_da_coluna(s, *k) for k in TIPOS_DO_CODIGO} == TIPOS_DO_CODIGO
    # o guardado ficou NULL; o número converteu
    assert [(r["id"], r["criado_por"]) for r in V.sql(
        s, "SELECT id, criado_por FROM ri_matriculas ORDER BY id")] == [
        (1, 1), (2, None), (3, None), (4, None), (5, None), (6, None), (7, None), (8, None)]
    assert [(r["id"], r["filhos_maiores"]) for r in V.sql(
        s, "SELECT id, filhos_maiores FROM nt_atos ORDER BY id")] == [(1, 2), (2, None)]
    assert [(r["id"], r["entity_id"]) for r in V.sql(
        s, "SELECT id, entity_id FROM audit_logs ORDER BY id")] == [(1, 1), (2, None), (3, 42)]
    # o login de exatamente um usuário virou o id dele, e o original fica guardado
    assert [(r["id"], r["lavrado_por"]) for r in V.sql(
        s, "SELECT id, lavrado_por FROM ri_atos ORDER BY id")] == [(1, 3), (2, 3), (3, None)]
    # o inteiro que o código quer texto virou texto
    assert V.sql(s, "SELECT criado_por FROM cx_depositos ORDER BY id") == [{"criado_por": "2"}]
    # as 2 FKs para users entram validadas
    fks = {r["conname"]: r["convalidated"] for r in V.sql(
        s, "SELECT conname, convalidated FROM pg_constraint WHERE conname IN "
           "('ri_atos_lavrado_por_fkey', 'ri_matriculas_criado_por_fkey') "
           "AND connamespace = current_schema()::regnamespace ORDER BY conname")}
    assert fks == {"ri_atos_lavrado_por_fkey": True, "ri_matriculas_criado_por_fkey": True}
    # o login não distingue maiúscula, e o próximo id passa do maior
    assert V.sql(s, "SELECT a.attcollation::regcollation::text AS c FROM pg_attribute a "
                    "WHERE a.attrelid = to_regclass('users') AND a.attname = 'username'") == [
        {"c": "cg_nocase"}]
    assert V.sql(s, "INSERT INTO users (username, full_name) VALUES ('novo.usuario', "
                    "'Usuário Novo de Exemplo') RETURNING id") == [{"id": 6}]


def test_o_ajuste_roda_duas_vezes_sem_erro_e_sem_mudar_nada(virada):
    _, primeiro = V.ate_o_ajuste(virada, nao_numericos="guardar")
    assert primeiro.returncode == 0, primeiro.saida
    antes = _fotografia(virada.schema)

    segundo = V.rodar_sql(V.AJUSTE, virada.schema, nao_numericos="guardar")
    assert segundo.returncode == 0, segundo.saida
    assert "sequências ajustadas: 0" in segundo.saida
    assert "guardado(s) em cg_ajuste_guardados e anulado(s)" not in segundo.saida
    assert _fotografia(virada.schema) == antes

    # e o modo padrão, depois, também passa: não sobrou texto que não converte
    terceiro = V.rodar_sql(V.AJUSTE, virada.schema)
    assert terceiro.returncode == 0, terceiro.saida
    assert "AJUSTE ABORTADO" not in terceiro.saida
    assert _fotografia(virada.schema) == antes


def test_sem_texto_que_nao_converte_o_modo_padrao_basta_e_nao_cria_a_tabela_dos_guardados(virada):
    _, feito = V.ate_o_ajuste(virada, limpo=True)
    assert feito.returncode == 0, feito.saida
    assert "tipos: 13 de 13 OK" in feito.saida
    assert not V.tem_tabela(virada.schema, "cg_ajuste_guardados")
    assert V.sql(virada.schema, "SELECT entity_id FROM audit_logs ORDER BY id") == [
        {"entity_id": 1}, {"entity_id": None}, {"entity_id": 42}]

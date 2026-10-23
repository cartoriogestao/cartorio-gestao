"""A virada não perde o que o banco da produção já tem — lote LH07, 21/10/2026.

O QUE SE MEDIU (só leitura, `mode=ro`, no banco da produção)
    `pt_avisos.origem`/`origem_chave` e `pt_editais.origem`/`origem_chave`,
    com os índices únicos PARCIAIS `ux_pt_avisos_origem`/`ux_pt_editais_origem`
    e 1.676 avisos com origem 'EOFICIO' — que o código da produção não
    conhecia —, e `rc_assentos.tardio_requerimento`, do registro tardio.

A CARGA DA VIRADA é o `tools/migrar_para_postgres.py` (até o LH10 ele só existia
no pacote da entrega); o `_receber_de_sqlite` não carrega nada no PostgreSQL.
Por isso o aviso de coluna que não veio é a CONFERÊNCIA
(`banco_pg.conferir_carga_de_sqlite`), que roda depois da carga, e os testes do
LH07 fazem a carga como ela é feita: as tabelas que o PostgreSQL ainda não tem
nascem do esquema do arquivo; as que ele já tem recebem as linhas pelas colunas
que existem dos dois lados.

O QUE ESTES TESTES GUARDAM
    - pelo esquema do arquivo, as colunas, os índices parciais e os dados vêm,
      e as contagens batem (avisos por origem, editais, tardio_requerimento);
    - pelo esquema que o código cria, também — as colunas estão nele agora;
    - o índice parcial recusa `origem_chave` repetida e aceita várias vazias;
    - a carga num esquema SEM as colunas não fica calada: a conferência diz
      quais colunas do SQLite não existem no PostgreSQL, e quais vieram vazias.

E, desde o LH10 (21/10/2026), a FERRAMENTA da carga, rodada como o passo B3
(outro processo, num SQLite de fixture sem dado real — `virada_de_teste.py`):
    - copia tudo, e a conferência dela (contagem, sha256 e a corrente de hash
      do RI) fecha, como a da branch;
    - a conferência dela acusa a linha mudada depois da carga;
    - ela não escreve por cima de um schema que já tem tabelas;
    - depois do ajuste (B4) no modo guardar, a conferência da branch separa o
      que o ajuste guardou do que se perdeu: a decisão do oficial não derruba a
      conferência, e uma perda de verdade continua derrubando.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import banco_pg  # noqa: E402
import virada_de_teste as V  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402
from virada_de_teste import virada  # noqa: E402,F401  (a fixture)

pytestmark = pytest.mark.skipif(not banco_pg.ativo(),
                                reason="a virada é para o PostgreSQL")

HOJE = "2026-10-21"
ORDEM = ("pt_titulos", "pt_avisos", "pt_editais", "rc_assentos")

# A FORMA DA PRODUÇÃO, só nas colunas que importam aqui (e nas NOT NULL).
ESQUEMA_DA_PRODUCAO = """
CREATE TABLE pt_titulos (id INTEGER PRIMARY KEY, especie TEXT,
    numero_titulo TEXT, situacao TEXT NOT NULL DEFAULT 'APONTADO',
    origem TEXT, origem_chave TEXT, protocolo TEXT, criado_em TEXT NOT NULL);
CREATE TABLE pt_avisos (id INTEGER PRIMARY KEY, titulo_id INTEGER NOT NULL,
    numero INTEGER NOT NULL, ano INTEGER NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'EMITIDO', emitido_em TEXT NOT NULL,
    criado_em TEXT NOT NULL, origem TEXT, origem_chave TEXT);
CREATE UNIQUE INDEX ux_pt_avisos_origem ON pt_avisos(origem_chave)
    WHERE origem_chave IS NOT NULL;
CREATE TABLE pt_editais (id INTEGER PRIMARY KEY, numero INTEGER NOT NULL,
    ano INTEGER NOT NULL, aviso_id INTEGER NOT NULL, titulo_id INTEGER NOT NULL,
    publicado_em TEXT NOT NULL, teor TEXT NOT NULL, criado_em TEXT NOT NULL,
    origem TEXT, origem_chave TEXT);
CREATE UNIQUE INDEX ux_pt_editais_origem ON pt_editais(origem_chave)
    WHERE origem_chave IS NOT NULL;
CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, especie TEXT,
    tardio_requerimento TEXT);
"""


def _sqlite_da_producao(pasta: Path) -> Path:
    """O arquivo de fixture: 5 avisos do E-Ofício e 2 daqui, 2 editais do
    E-Ofício e 1 daqui, 3 assentos e 1 deles com o requerimento do tardio."""
    arquivo = pasta / "copia_da_producao.sqlite3"
    sq = sqlite3.connect(arquivo)
    try:
        sq.executescript(ESQUEMA_DA_PRODUCAO)
        for i in range(1, 8):
            sq.execute("INSERT INTO pt_titulos VALUES (?, 'DMI', ?, 'APONTADO', "
                       "'CRA', ?, ?, ?)",
                       (i, f"N{i}", f"tbAvisoProtesto:{i}.0", f"26100700{i:02d}", HOJE))
            eoficio = i <= 5
            sq.execute("INSERT INTO pt_avisos VALUES (?, ?, ?, 2026, 'EMITIDO', ?, ?, ?, ?)",
                       (i, i, i, HOJE, HOJE, "EOFICIO" if eoficio else None,
                        f"tbBoletoApto:{100 + i}" if eoficio else None))
        for i, (aviso, chave) in enumerate(((1, "tbEdital:7"), (2, "tbEdital:8"),
                                            (6, None)), start=1):
            sq.execute("INSERT INTO pt_editais VALUES (?, ?, 2026, ?, ?, ?, "
                       "'Edital de exemplo.', ?, ?, ?)",
                       (i, i, aviso, aviso, HOJE, HOJE,
                        "EOFICIO" if chave else None, chave))
        sq.executemany("INSERT INTO rc_assentos VALUES (?, 'NASCIMENTO', ?)",
                       [(1, None), (2, "REQUERIMENTO DE EXEMPLO"), (3, None)])
        sq.commit()
    finally:
        sq.close()
    return arquivo


def _carregar(arquivo: Path, con) -> None:
    """A carga, como a da virada: tabela que falta nasce do esquema do
    arquivo (com os índices dele); tabela que existe recebe as linhas pelas
    colunas que o PostgreSQL tem."""
    sq = sqlite3.connect(arquivo)
    try:
        ddl = dict(sq.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'"))
        indices = sq.execute("SELECT tbl_name, sql FROM sqlite_master "
                             "WHERE type = 'index' AND sql IS NOT NULL ORDER BY name").fetchall()
        for tabela in ORDEM:
            nova = not con.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = "
                "current_schema() AND table_name = ?", (tabela,)).fetchone()
            if nova:
                con.execute(ddl[tabela])
                for de_quem, sql in indices:
                    if de_quem == tabela:
                        con.execute(sql)
            tem = {r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE "
                "table_schema = current_schema() AND table_name = ?", (tabela,))}
            colunas = [d[0] for d in sq.execute(f"SELECT * FROM {tabela} LIMIT 0").description
                       if d[0] in tem]
            linhas = sq.execute(f"SELECT {', '.join(colunas)} FROM {tabela} ORDER BY id").fetchall()
            con.executemany(
                f"INSERT INTO {tabela} ({', '.join(colunas)}) "
                f"VALUES ({', '.join('?' * len(colunas))})", linhas)
        con.commit()
    finally:
        sq.close()


def _por_origem(con, tabela: str) -> dict:
    return {r[0]: r[1] for r in con.execute(
        f"SELECT origem, count(*) FROM {tabela} GROUP BY origem ORDER BY origem")}


def _o_indice_parcial_vale(con) -> None:
    """Recusa a chave repetida e aceita várias vazias."""
    for i in (9001, 9002):
        con.execute("INSERT INTO pt_avisos(id, titulo_id, numero, ano, situacao, "
                    "emitido_em, criado_em) VALUES (?, 7, ?, 2027, 'EMITIDO', ?, ?)",
                    (i, i, HOJE, HOJE))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO pt_avisos(id, titulo_id, numero, ano, situacao, "
                    "emitido_em, criado_em, origem, origem_chave) "
                    "VALUES (9003, 7, 9003, 2027, 'EMITIDO', ?, ?, 'EOFICIO', "
                    "'tbBoletoApto:101')", (HOJE, HOJE))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO pt_editais(id, numero, ano, aviso_id, titulo_id, "
                    "publicado_em, teor, criado_em, origem, origem_chave) "
                    "VALUES (9004, 9004, 2027, 1, 1, ?, 'x', ?, 'EOFICIO', "
                    "'tbEdital:7')", (HOJE, HOJE))
    con.rollback()


def _indice(con, nome: str) -> str | None:
    linha = con.execute("SELECT indexdef FROM pg_indexes WHERE schemaname = "
                        "current_schema() AND indexname = ?", (nome,)).fetchone()
    return linha[0] if linha else None


def test_pelo_esquema_do_arquivo_as_colunas_os_indices_e_os_dados_vem(tmp_path):
    arquivo = _sqlite_da_producao(tmp_path)
    con = conexao_de_teste()
    _carregar(arquivo, con)

    assert _por_origem(con, "pt_avisos") == {"EOFICIO": 5, None: 2}
    assert _por_origem(con, "pt_editais") == {"EOFICIO": 2, None: 1}
    assert con.execute("SELECT count(tardio_requerimento) FROM rc_assentos").fetchone()[0] == 1
    for nome in ("ux_pt_avisos_origem", "ux_pt_editais_origem"):
        assert _indice(con, nome).startswith(f"CREATE UNIQUE INDEX {nome} ON ")
        assert _indice(con, nome).endswith("(origem_chave) WHERE (origem_chave IS NOT NULL)")
    feito = banco_pg.conferir_carga_de_sqlite(arquivo, con.db_path)
    assert feito["ok"], feito
    _o_indice_parcial_vale(con)


def test_pelo_esquema_que_o_codigo_cria_nada_se_perde(tmp_path):
    arquivo = _sqlite_da_producao(tmp_path)
    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_pt_schema(con)
    con.commit()
    _carregar(arquivo, con)

    feito = banco_pg.conferir_carga_de_sqlite(arquivo, con.db_path)
    assert feito["ok"], feito
    assert _por_origem(con, "pt_avisos") == {"EOFICIO": 5, None: 2}
    assert _por_origem(con, "pt_editais") == {"EOFICIO": 2, None: 1}
    # o código, subindo de novo sobre o banco carregado, não cria um segundo
    # índice ao lado do que já está lá
    init_pt_schema(con)
    con.commit()
    assert con.execute(
        "SELECT count(*) FROM pg_indexes WHERE schemaname = current_schema() "
        "AND tablename = 'pt_avisos' AND indexdef LIKE '%(origem_chave)%'").fetchone()[0] == 1
    _o_indice_parcial_vale(con)


def test_a_carga_sem_as_colunas_e_avisada_com_a_lista(tmp_path):
    """O esquema de antes do LH07 (sem `origem`/`origem_chave`) e um
    `rc_assentos` sem o tardio: a carga cabe, e a conferência não fica calada."""
    arquivo = _sqlite_da_producao(tmp_path)
    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_pt_schema(con)
    con.execute("ALTER TABLE pt_avisos DROP COLUMN origem")
    con.execute("ALTER TABLE pt_avisos DROP COLUMN origem_chave")
    con.execute("CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, especie TEXT)")
    con.commit()
    _carregar(arquivo, con)

    feito = banco_pg.conferir_carga_de_sqlite(arquivo, con.db_path)
    assert not feito["ok"]
    assert feito["colunas_que_nao_vieram"] == {
        "pt_avisos": ["origem", "origem_chave"],
        "rc_assentos": ["tardio_requerimento"]}
    assert feito["linhas_diferentes"] == {}
    assert feito["tabelas_que_nao_vieram"] == []


def test_coluna_que_existe_mas_veio_vazia_tambem_e_avisada(tmp_path):
    arquivo = _sqlite_da_producao(tmp_path)
    con = conexao_de_teste()
    _carregar(arquivo, con)
    con.execute("UPDATE pt_avisos SET origem = NULL")
    con.execute("DELETE FROM pt_editais WHERE origem_chave = 'tbEdital:8'")
    con.commit()

    feito = banco_pg.conferir_carga_de_sqlite(arquivo, con.db_path)
    assert not feito["ok"]
    assert feito["valores_diferentes"]["pt_avisos"] == {"origem": {"sqlite": 5, "pg": 0}}
    assert feito["linhas_diferentes"] == {"pt_editais": {"sqlite": 3, "pg": 2}}


def test_tabela_do_arquivo_que_nao_existe_no_postgresql_e_avisada(tmp_path):
    arquivo = _sqlite_da_producao(tmp_path)
    con = conexao_de_teste()
    _carregar(arquivo, con)
    con.execute("DROP TABLE rc_assentos")
    con.commit()
    feito = banco_pg.conferir_carga_de_sqlite(arquivo, con.db_path)
    assert feito["tabelas_que_nao_vieram"] == ["rc_assentos"]
    assert not feito["ok"]


def test_a_linha_de_comando_sai_com_1_quando_algo_nao_veio(tmp_path, capsys):
    arquivo = _sqlite_da_producao(tmp_path)
    con = conexao_de_teste()
    _carregar(arquivo, con)
    assert banco_pg.main(["conferir-carga", str(arquivo), str(con.db_path)]) == 0
    con.execute("DROP TABLE rc_assentos")
    con.commit()
    assert banco_pg.main(["conferir-carga", str(arquivo), str(con.db_path)]) == 1
    assert '"rc_assentos"' in capsys.readouterr().out


# ------------------------------- a ferramenta da carga (LH10, passos B3 e B4)

def test_a_ferramenta_da_carga_copia_tudo_e_a_conferencia_dela_e_a_da_branch_fecham(virada):
    arquivo = V.montar_sqlite(virada.pasta)
    feito = V.carregar(arquivo, virada.schema, "--recriar")
    assert feito.returncode == 0, feito.saida[-4000:]
    s = virada.schema
    relatorio = (virada.pasta / "relatorio_carga.md").read_text(encoding="utf-8")
    assert (f"| Tabelas conferidas OK (contagem **e** soma de verificação) | "
            f"**{len(V.TABELAS)}** |") in relatorio
    assert "| Tabelas divergentes | **0** |" in relatorio
    assert "**O recálculo lendo do PostgreSQL é idêntico, ato por ato" in relatorio
    for tabela in V.TABELAS:
        no_arquivo = V.ler_sqlite(arquivo, f"SELECT count(*) FROM {tabela}")[0][0]
        assert V.sql(s, f"SELECT count(*) AS n FROM {tabela}") == [{"n": no_arquivo}], tabela
    # o texto na coluna INTEGER chega como está, numa coluna texto: quem decide é o ajuste
    assert V.tipo_da_coluna(s, "ri_matriculas", "criado_por") == "text"
    assert V.sql(s, "SELECT criado_por FROM ri_matriculas WHERE id = 5") == [{"criado_por": V.NAO_CASA}]
    # o relatório e a saída da carga voltam para a equipe do Mac: sem nome de pessoa
    for nome in (V.CASA_COM_UM, V.NAO_CASA, V.CASA_COM_DOIS):
        assert nome not in relatorio and nome not in feito.saida
    assert banco_pg.conferir_carga_de_sqlite(arquivo, virada.caminho)["ok"]
    # e o próximo id segue o maior que veio
    assert V.sql(s, "INSERT INTO users (username) VALUES ('novo.usuario') RETURNING id") == [{"id": 6}]


def test_a_conferencia_da_ferramenta_acusa_a_linha_mudada_depois_da_carga(virada):
    arquivo = V.montar_sqlite(virada.pasta)
    assert V.carregar(arquivo, virada.schema, "--recriar").returncode == 0
    V.sql(virada.schema, "UPDATE ri_atos SET teor = teor || ' (mexido)' WHERE id = 2")

    feito = V.carregar(arquivo, virada.schema, "--so-conferir")
    assert feito.returncode == 1, feito.saida[-4000:]
    relatorio = (virada.pasta / "relatorio_carga.md").read_text(encoding="utf-8")
    assert "| Tabelas divergentes | **1** |" in relatorio
    assert "- id=2 — colunas: teor" in relatorio
    assert "| Corrente de hash do RI | **DIVERGE**" in relatorio


def test_a_ferramenta_da_carga_nao_escreve_por_cima_de_um_schema_com_tabelas(virada):
    arquivo = V.montar_sqlite(virada.pasta)
    assert V.carregar(arquivo, virada.schema, "--recriar").returncode == 0
    V.sql(virada.schema, "UPDATE cx_depositos SET criado_por = 3")

    feito = V.carregar(arquivo, virada.schema)
    assert feito.returncode == 2, feito.saida[-4000:]
    assert f"O schema {virada.schema} já tem" in feito.saida
    assert V.sql(virada.schema, "SELECT criado_por FROM cx_depositos") == [{"criado_por": 3}]


def test_depois_do_ajuste_a_conferencia_separa_o_guardado_do_perdido(virada, capsys):
    arquivo, feito = V.ate_o_ajuste(virada, "repetida", nao_numericos="guardar")
    assert feito.returncode == 0, feito.saida
    s = virada.schema

    conferido = banco_pg.conferir_carga_de_sqlite(arquivo, virada.caminho)
    assert conferido["ok"], conferido
    assert conferido["linhas_guardadas_pelo_ajuste"] == {"ri_cnib_decisoes": {"sqlite": 6, "pg": 4}}
    guardados = conferido["valores_guardados_pelo_ajuste"]
    assert guardados["ri_matriculas"] == {"criado_por": {"sqlite": 7, "pg": 1}}
    assert guardados["nt_atos"] == {"filhos_maiores": {"sqlite": 2, "pg": 1}}
    assert guardados["audit_logs"] == {"entity_id": {"sqlite": 3, "pg": 2}}
    assert guardados["ri_cnib_decisoes"]["matricula_id"] == {"sqlite": 6, "pg": 4}
    # o login que virou id não fez falta a ninguém
    assert "ri_atos" not in guardados
    # a linha de comando sai com 0 e diz o que o ajuste guardou
    assert banco_pg.main(["conferir-carga", str(arquivo), str(virada.caminho)]) == 0
    avisos = capsys.readouterr().err
    assert "AVISO: ri_matriculas.criado_por: 6 valor(es) a menos no PostgreSQL" in avisos
    assert "AVISO: ri_cnib_decisoes: 2 linha(s) a menos no PostgreSQL" in avisos

    # o desconto é EXATO: algo a mais na coluna ou na tabela que tem guardados
    # (a subida do código, por exemplo) também não fecha
    V.sql(s, "UPDATE ri_matriculas SET criado_por = 1 WHERE id = 8")
    V.sql(s, "INSERT INTO ri_cnib_decisoes (matricula_id, protocolo_cnib, decisao, decidido_em) "
             "VALUES (8, 'CNIB-0009', 'AVERBADA', '2026-10-21T10:00:00')")
    conferido = banco_pg.conferir_carga_de_sqlite(arquivo, virada.caminho)
    assert not conferido["ok"]
    assert conferido["valores_diferentes"]["ri_matriculas"] == {"criado_por": {"sqlite": 7, "pg": 2}}
    assert conferido["linhas_diferentes"] == {"ri_cnib_decisoes": {"sqlite": 6, "pg": 5}}
    V.sql(s, "UPDATE ri_matriculas SET criado_por = NULL WHERE id = 8")
    V.sql(s, "DELETE FROM ri_cnib_decisoes WHERE protocolo_cnib = 'CNIB-0009'")
    assert banco_pg.conferir_carga_de_sqlite(arquivo, virada.caminho)["ok"]

    # uma perda de verdade, na mesma coluna e na mesma tabela, continua derrubando
    V.sql(s, "UPDATE ri_matriculas SET criado_por = NULL WHERE id = 1")
    V.sql(s, "DELETE FROM ri_cnib_decisoes WHERE id = 5")
    conferido = banco_pg.conferir_carga_de_sqlite(arquivo, virada.caminho)
    assert not conferido["ok"]
    assert conferido["valores_diferentes"]["ri_matriculas"] == {"criado_por": {"sqlite": 7, "pg": 0}}
    assert conferido["linhas_diferentes"] == {"ri_cnib_decisoes": {"sqlite": 6, "pg": 3}}
    assert banco_pg.main(["conferir-carga", str(arquivo), str(virada.caminho)]) == 1

"""O backup na automação e o teste de restauração — contra o PostgreSQL de verdade.

O QUE ESTES TESTES PROVAM (26/10/2026)
    - o manifesto leva as contagens de cada tabela NO MESMO instantâneo do
      pg_dump, e diz que o banco é um pg_dump;
    - o pacote volta num banco DESCARTÁVEL, as contagens batem, o banco
      descartável some, a rodada fica em `bk_restauracoes` — e o banco de origem
      não é tocado;
    - contagem que não bate vira DIVERGENTE (e ERRO na automação), e não OK;
    - o pacote de antes da migração (SQLite) é recusado com a frase, sem criar
      banco nenhum; nome que não é de banco descartável não se cria nem se apaga;
    - o processo de backup gera o pacote do dia, não repete, e a falha vira ERRO
      — que a central da automação transforma em aviso no painel e tarefa;
    - o primeiro acesso do dia continua como reserva, uma vez por DIA, e não
      repete o pacote que a automação já gerou.

    Os de PostgreSQL são lentos (pg_dump e pg_restore de um schema inteiro no
    servidor de teste, que é compartilhado): UM pacote para o módulo e DUAS
    restaurações.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automacao as AU  # noqa: E402
import automacao_processos as PROC  # noqa: E402
import automacao_schema as SCH  # noqa: E402
import backup as BKP  # noqa: E402
import backup_automacao as BA  # noqa: E402
import backup_restauracao as REST  # noqa: E402
import backup_rotina as ROT  # noqa: E402
import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402

pytestmark = [
    pytest.mark.lento,
    pytest.mark.skipif(not banco_pg.ativo(), reason="o teste de restauração é do PostgreSQL"),
]

SENHA = "Senha#12345"


def _contagens_da_origem(db) -> dict[str, int]:
    import psycopg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as pg, pg.cursor() as c:
        return banco_pg.contar_linhas(c, banco_pg.schema_do_caminho(db.db_path))


@pytest.fixture(scope="module")
def pacote(_cg_boot, tmp_path_factory):
    """UM pacote real do módulo (pg_dump do schema de teste), numa pasta de backups."""
    db = _cg_boot["db"]
    if not db.list_users():
        db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    pasta = tmp_path_factory.mktemp("backups")
    destino = pasta / f"backup_banco_{date.today().isoformat()}.zip"
    BKP.gerar_pacote(db, destino, tmp_path_factory.mktemp("arquivos"), com_arquivos=False)
    return destino


def _manifesto(p: Path) -> dict:
    with zipfile.ZipFile(p) as zf:
        return json.loads(zf.read(BKP.NOME_MANIFESTO).decode("utf-8"))


def _com_outro_manifesto(origem: Path, destino: Path, mudar) -> Path:
    """Cópia do pacote com o manifesto trocado (o banco e o SHA dele ficam iguais)."""
    with zipfile.ZipFile(origem) as zo, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zd:
        for item in zo.infolist():
            dado = zo.read(item.filename)
            if item.filename == BKP.NOME_MANIFESTO:
                m = json.loads(dado.decode("utf-8"))
                mudar(m)
                dado = json.dumps(m).encode("utf-8")
            zd.writestr(item.filename, dado)
    return destino


# ------------------------------------------------------------- o manifesto


def test_o_manifesto_leva_as_contagens_do_mesmo_instantaneo(pacote):
    m = _manifesto(pacote)
    assert m["banco_formato"] == BKP.FORMATO_PG_DUMP
    contagens = m["banco_contagens"]
    assert {"users", "settings", "audit_logs", "ri_atos"} <= set(contagens)
    assert contagens["users"] >= 1
    assert BKP.conferir(pacote) is None


# ------------------------------------------------------------- a restauração, de verdade


def test_o_pacote_volta_pela_automacao_e_a_origem_nao_e_tocada(cg_casa, pacote, tmp_path):
    db = cg_casa["db"]
    db.set_settings({"backup_dir": str(pacote.parent)})
    with db.transaction() as con:
        AU.semear(con)
    antes = _contagens_da_origem(db)
    ctx = PROC.Contexto(db=db, agora=datetime.now(), pasta_dados=tmp_path, raiz=RAIZ,
                        processo={"codigo": "BACKUP_TESTE_RESTAURACAO",
                                  "parametros": {"idade_maxima_h": 48}})
    r = BA.rodar_teste_de_restauracao(ctx)
    assert r["situacao"] == "OK", r["relato"]
    assert "todas as contagens batem" in r["relato"]
    achado = r["achados"][0]
    assert achado["tabelas"] == len(_manifesto(pacote)["banco_contagens"])
    assert achado["principais"]["users"] >= 1
    assert achado["sha256"] == BKP._sha256(pacote)
    # o banco descartável sumiu, e a origem continua igual
    assert achado["destino"].split("/")[-1] not in REST.bancos_descartaveis(REST.conexao_de_origem())
    depois = _contagens_da_origem(db)
    # a ÚNICA linha nova na origem é o registro da própria rodada
    assert depois.pop("bk_restauracoes") == antes.pop("bk_restauracoes") + 1
    assert depois == antes
    # e a rodada ficou registrada para a correição
    with db.connect() as con:
        linhas = REST.ultimas(con)
        gravada = banco(con).um("SELECT * FROM bk_restauracoes WHERE id = %s",
                                (achado["restauracao"],))
    assert linhas and linhas[0]["id"] == achado["restauracao"]
    assert gravada["situacao"] == REST.OK and gravada["pacote_sha256"] == achado["sha256"]
    assert json.loads(gravada["contagens"])["users"] == achado["principais"]["users"]
    assert gravada["duracao_s"] > 0


def test_contagem_que_nao_bate_e_divergencia_e_nao_ok(pacote, tmp_path):
    def mais_um(m):
        m["banco_contagens"]["users"] += 1
    adulterado = _com_outro_manifesto(pacote, tmp_path / "backup_banco_2026-10-26.zip", mais_um)
    r = REST.testar(adulterado)
    assert r["situacao"] == REST.DIVERGENTE
    assert {"tabela": "users", "problema": "contagem diferente",
            "esperado": r["contagens"]["users"] + 1,
            "restaurado": r["contagens"]["users"]} in r["divergencias"]
    relato = BA._relato_do_teste(r, 0, adulterado, datetime.now(), 48)
    assert relato["situacao"] == "ERRO" and "NÃO BATE" in relato["relato"]
    assert r["destino"].split("/")[-1] not in REST.bancos_descartaveis(REST.conexao_de_origem())


# ------------------------------------------------------------- as recusas (sem criar banco)


def test_pacote_de_antes_da_migracao_e_recusado_sem_criar_banco(tmp_path, monkeypatch):
    class SqliteFalso:
        def backup_database(self, destino):
            con = sqlite3.connect(destino)
            con.execute("CREATE TABLE t (id INTEGER)")
            con.commit()
            con.close()
            return destino

    p = BKP.gerar_pacote(SqliteFalso(), tmp_path / "backup_banco_2026-09-01.zip", tmp_path / "a",
                         com_arquivos=False)
    criados = []
    monkeypatch.setattr(REST, "_criar_banco", lambda base, nome: criados.append(nome))
    r = REST.testar(p)
    assert r["situacao"] == REST.FALHOU
    assert "antes da migração" in r["erro"] and criados == []
    relato = BA._relato_do_teste(r, 0, p, datetime.now(), 48)
    assert relato["situacao"] == "ERRO" and "NÃO VOLTOU" in relato["relato"]


def test_so_banco_descartavel_se_cria_ou_se_apaga():
    base = REST.conexao_de_origem()
    for nome in ("cartorio", "postgres", "cg_restauro_x", "cg_restauro_20261026143000_ab12cd; DROP",
                 REST._banco_da_conexao(base)):
        assert not REST.e_banco_descartavel(nome)
        with pytest.raises(REST.RestauracaoRecusada):
            REST._apagar_banco(base, nome)
        with pytest.raises(REST.RestauracaoRecusada):
            REST._criar_banco(base, nome)
    assert REST.e_banco_descartavel("cg_restauro_20261026143000_ab12cd")


def test_so_a_sobra_velha_e_apagada(monkeypatch):
    agora = datetime(2026, 10, 26, 12, 0)
    velha = f"cg_restauro_{(agora - timedelta(hours=7)):%Y%m%d%H%M%S}_aaaaaa"
    nova = f"cg_restauro_{(agora - timedelta(minutes=5)):%Y%m%d%H%M%S}_bbbbbb"
    apagados = []
    monkeypatch.setattr(REST, "bancos_descartaveis", lambda base: [velha, nova])
    monkeypatch.setattr(REST, "_apagar_banco", lambda base, nome: apagados.append(nome))
    assert REST.apagar_sobras("host=x dbname=cartorio", agora) == [velha]
    assert apagados == [velha]


def test_a_comparacao_cobra_as_principais_mesmo_sem_contagens():
    sem = REST.comparar(None, {"users": 1})
    assert {d["tabela"] for d in sem} == set(REST.TABELAS_PRINCIPAIS) - {"users"}
    tudo = {t: 1 for t in REST.TABELAS_PRINCIPAIS}
    assert REST.comparar(None, tudo) == []
    assert REST.comparar({**tudo, "x": 2}, {**tudo, "y": 3}) == [
        {"tabela": "x", "problema": "não voltou", "esperado": 2},
        {"tabela": "y", "problema": "voltou sem estar no manifesto", "restaurado": 3}]


# ------------------------------------------------------------- o processo de backup


def _gerar_de_mentira(chamadas, quebrar=False):
    def gerar(db, destino, archive_root, com_arquivos=True, **k):
        chamadas.append((Path(destino).name, com_arquivos))
        if quebrar:
            raise BKP.BackupInvalido("o SHA-256 do banco não bate com o do manifesto")
        Path(destino).write_bytes(b"PK de mentira")
        return destino
    return gerar


def test_o_processo_de_backup_gera_uma_vez_e_a_falha_vira_aviso_da_central(cg_casa, tmp_path,
                                                                          monkeypatch):
    db = cg_casa["db"]
    pasta = tmp_path / "backups"
    db.set_settings({"backup_dir": str(pasta)})
    chamadas = []
    monkeypatch.setattr(BKP, "gerar_pacote", _gerar_de_mentira(chamadas))
    ctx = PROC.Contexto(db=db, agora=datetime.now(), pasta_dados=tmp_path, raiz=RAIZ,
                        processo={"codigo": "BACKUP_DIARIO", "parametros": {}})
    r = BA.rodar_backup(ctx)
    assert r["situacao"] == "OK", r["relato"]
    assert ROT.pacote_diario(pasta, ctx.hoje).exists()
    assert "Backup conferido" in r["relato"]
    r2 = BA.rodar_backup(ctx)
    assert r2["situacao"] == "OK" and "já existia" in r2["relato"]
    assert sum(1 for nome, _ in chamadas if nome.startswith("backup_banco_")) == 1

    # a falha: ERRO com a frase — e a central avisa (painel, tarefa) pelo canal dela
    ROT.pacote_diario(pasta, ctx.hoje).unlink()
    monkeypatch.setattr(BKP, "gerar_pacote", _gerar_de_mentira([], quebrar=True))
    falhou = BA.rodar_backup(ctx)
    assert falhou["situacao"] == "ERRO" and "O BACKUP FALHOU" in falhou["relato"]
    assert "SHA-256" in falhou["relato"]
    with db.transaction() as con:
        AU.semear(con)
        p = AU.por_codigo(con, "BACKUP_DIARIO")
        assert p and not p["ativo"]                      # nasce desligado
        e = AU._criar_execucao(con, p, disparo=SCH.MANUAL, agendada_para=None, quem="t",
                               agora=ctx.agora)
    AU.finalizar(db, e, falhou, agora=ctx.agora)
    with db.connect() as con:
        canais = {a["canal"] for a in banco(con).ler(
            "SELECT canal FROM au_avisos WHERE processo_id = %s", (p["id"],))}
    assert {SCH.PAINEL, SCH.TAREFA} <= canais


def test_as_sementes_do_backup_chegam_a_central_com_os_parametros():
    trazidas = {s["codigo"]: s for s in PROC.sementes_de_outros_modulos()}
    assert trazidas["BACKUP_DIARIO"]["alvo"] == "backup_automacao:rodar_backup"
    teste = trazidas["BACKUP_TESTE_RESTAURACAO"]
    assert teste["alvo"] == "backup_automacao:rodar_teste_de_restauracao"
    assert teste["parametros"] == {"idade_maxima_h": 48}
    assert teste["timeout_s"] == 3 * 3600


# ------------------------------------------------------------- o primeiro acesso, como reserva


def test_o_primeiro_acesso_e_reserva_uma_vez_por_dia_e_nao_repete(cg_casa, tmp_path, monkeypatch):
    app, db, c = cg_casa["app"], cg_casa["db"], cg_casa["c"]
    pasta = tmp_path / "backups"
    db.set_settings({"backup_dir": str(pasta), "auto_backup": "1"})
    chamadas = []
    monkeypatch.setattr(BKP, "gerar_pacote", _gerar_de_mentira(chamadas))
    app.extensions["backup_checked"] = None
    c.get("/login")
    c.get("/login")
    diarios = [n for n, _ in chamadas if n.startswith("backup_banco_")]
    assert diarios == [f"backup_banco_{date.today().isoformat()}.zip"]
    # um dia depois a marca vence; o pacote de hoje (que a automação poderia
    # ter gerado) já existe, e não se repete
    app.extensions["backup_checked"] = date.today() - timedelta(days=1)
    c.get("/login")
    assert [n for n, _ in chamadas if n.startswith("backup_banco_")] == diarios
    assert app.extensions["backup_checked"] == date.today()
    # `True` continua querendo dizer «não rode» (é como os outros testes o desligam)
    app.extensions["backup_checked"] = True
    ROT.pacote_diario(pasta, date.today()).unlink()
    c.get("/login")
    assert [n for n, _ in chamadas if n.startswith("backup_banco_")] == diarios

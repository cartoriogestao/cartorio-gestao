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
      repete o pacote que a automação já gerou;
    - (revisão de segurança, 26/10/2026) só se restaura pacote que a casa gerou
      (nome e SHA-256 em `bk_pacotes`), nunca com papel que tenha poder no
      servidor, e o pacote é aberto na pasta de dados — não na dos backups.
      As restaurações de verdade usam um papel só com LOGIN CREATEDB.

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


@pytest.fixture
def papel_restrito(monkeypatch):
    """Um papel só com LOGIN CREATEDB para o pg_restore — o que a casa deve configurar.

    Desde 26/10/2026 (revisão de segurança, PR #27) o teste de restauração
    RECUSA papel superusuário, e o `cg` do servidor de teste é superusuário:
    sem este papel, as restaurações de verdade terminariam em FALHOU.
    """
    import secrets

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    base = banco_pg.dsn()
    nome = f"cg_restauro_teste_{secrets.token_hex(3)}"
    senha = secrets.token_urlsafe(18)
    try:
        with psycopg.connect(base, autocommit=True) as pg, pg.cursor() as c:
            c.execute(sql.SQL("CREATE ROLE {} LOGIN CREATEDB PASSWORD {}").format(
                sql.Identifier(nome), sql.Literal(senha)))
    except psycopg.Error as erro:
        pytest.skip(f"sem como criar o papel restrito do teste ({erro})")
    monkeypatch.setenv("CG_PG_DSN_RESTAURACAO", make_conninfo(base, user=nome, password=senha))
    yield nome
    try:
        with psycopg.connect(base, autocommit=True) as pg, pg.cursor() as c:
            c.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(nome)))
    except psycopg.Error:
        pass


def _registrar(db, p: Path) -> None:
    """O pacote entra na lista dos que a casa gerou — como a rodada do backup faz."""
    REST.registrar_pacotes_gerados(db, [ROT._descrever(p, "banco")], origem="teste")


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


def test_o_pacote_volta_pela_automacao_e_a_origem_nao_e_tocada(cg_casa, pacote, tmp_path,
                                                               papel_restrito):
    db = cg_casa["db"]
    db.set_settings({"backup_dir": str(pacote.parent)})
    with db.transaction() as con:
        AU.semear(con)
    _registrar(db, pacote)
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


def test_contagem_que_nao_bate_e_divergencia_e_nao_ok(cg_casa, pacote, tmp_path, papel_restrito):
    def mais_um(m):
        m["banco_contagens"]["users"] += 1
    adulterado = _com_outro_manifesto(pacote, tmp_path / "backup_banco_2026-10-26.zip", mais_um)
    # a casa «gerou» este pacote (o que se testa aqui é a contagem, não a origem)
    _registrar(cg_casa["db"], adulterado)
    r = REST.testar(adulterado, db=cg_casa["db"], pasta_dados=tmp_path / "dados")
    assert r["situacao"] == REST.DIVERGENTE
    assert {"tabela": "users", "problema": "contagem diferente",
            "esperado": r["contagens"]["users"] + 1,
            "restaurado": r["contagens"]["users"]} in r["divergencias"]
    relato = BA._relato_do_teste(r, 0, adulterado, datetime.now(), 48)
    assert relato["situacao"] == "ERRO" and "NÃO BATE" in relato["relato"]
    assert r["destino"].split("/")[-1] not in REST.bancos_descartaveis(REST.conexao_de_origem())


# ------------------------------------------------------------- as recusas (sem criar banco)


class SqliteFalso:
    def backup_database(self, destino):
        con = sqlite3.connect(destino)
        con.execute("CREATE TABLE t (id INTEGER)")
        con.commit()
        con.close()
        return destino


def test_pacote_de_antes_da_migracao_e_recusado_sem_criar_banco(cg_casa, tmp_path, monkeypatch):
    p = BKP.gerar_pacote(SqliteFalso(), tmp_path / "backup_banco_2026-09-01.zip", tmp_path / "a",
                         com_arquivos=False)
    _registrar(cg_casa["db"], p)
    monkeypatch.setattr(REST, "conferir_o_papel", lambda base: None)
    criados = []
    monkeypatch.setattr(REST, "_criar_banco", lambda base, nome: criados.append(nome))
    r = REST.testar(p, db=cg_casa["db"], pasta_dados=tmp_path / "dados")
    assert r["situacao"] == REST.FALHOU
    assert "antes da migração" in r["erro"] and criados == []
    relato = BA._relato_do_teste(r, 0, p, datetime.now(), 48)
    assert relato["situacao"] == "ERRO" and "NÃO VOLTOU" in relato["relato"]


# ---------------------------- as recusas da revisão de segurança de 26/10/2026 (PR #27)


def _sem_criar(monkeypatch) -> list:
    criados = []
    monkeypatch.setattr(REST, "_criar_banco", lambda base, nome: criados.append(nome))
    return criados


def test_pacote_que_a_casa_nao_gerou_e_recusado_sem_criar_banco(cg_casa, pacote, tmp_path,
                                                                monkeypatch):
    """O manifesto de dentro do zip não é prova: quem fabrica o pacote fabrica o manifesto."""
    criados = _sem_criar(monkeypatch)
    de_fora = tmp_path / "backups" / "backup_banco_2026-01-01.zip"
    de_fora.parent.mkdir()
    de_fora.write_bytes(pacote.read_bytes())
    r = REST.testar(de_fora, db=cg_casa["db"], pasta_dados=tmp_path / "dados")
    assert r["situacao"] == REST.FALHOU and "não consta entre os que o sistema gerou" in r["erro"]
    assert criados == [] and r["destino"] is None


def test_pacote_trocado_depois_de_registrado_e_recusado(cg_casa, pacote, tmp_path, monkeypatch):
    criados = _sem_criar(monkeypatch)
    trocado = tmp_path / "backups" / "backup_banco_2026-01-02.zip"
    trocado.parent.mkdir()
    trocado.write_bytes(pacote.read_bytes())
    _registrar(cg_casa["db"], trocado)
    _com_outro_manifesto(pacote, trocado, lambda m: m.update({"tipo": "forjado"}))
    r = REST.testar(trocado, db=cg_casa["db"], pasta_dados=tmp_path / "dados")
    assert r["situacao"] == REST.FALHOU and "não consta" in r["erro"] and criados == []


def test_papel_com_poder_no_servidor_e_recusado_sem_criar_banco(cg_casa, pacote, tmp_path,
                                                                 monkeypatch):
    criados = _sem_criar(monkeypatch)
    _registrar(cg_casa["db"], pacote)
    monkeypatch.setattr(REST, "_poder_do_papel", lambda base: ["cg: SUPERUSER"])
    r = REST.testar(pacote, db=cg_casa["db"], pasta_dados=tmp_path / "dados")
    assert r["situacao"] == REST.FALHOU
    assert "poder demais" in r["erro"] and "CG_PG_DSN_RESTAURACAO" in r["erro"]
    assert criados == []


def test_o_papel_restrito_passa_na_conferencia(papel_restrito):
    import os
    assert REST._poder_do_papel(os.environ["CG_PG_DSN_RESTAURACAO"]) == []


def test_o_pacote_aberto_nasce_na_pasta_de_dados_e_o_zip_decifrado_some(cg_casa, tmp_path,
                                                                        monkeypatch):
    """O decifrado e o dump nunca ficam na pasta dos backups, que sai da serventia."""
    pasta = tmp_path / "backups"
    pasta.mkdir()
    p = BKP.gerar_pacote(SqliteFalso(), pasta / "backup_banco_2026-09-01.zip", tmp_path / "a",
                         com_arquivos=False, senha_da_cifra="cifra-de-teste-123")
    assert BKP.e_cifrado(p)
    _registrar(cg_casa["db"], p)
    monkeypatch.setattr(REST, "conferir_o_papel", lambda base: None)
    _sem_criar(monkeypatch)
    vistos = []
    original = REST._tirar_o_dump

    def espiao(pacote, tmp, senha):
        try:
            return original(pacote, tmp, senha)
        finally:
            vistos.append((Path(tmp), sorted(x.name for x in Path(tmp).iterdir())))
    monkeypatch.setattr(REST, "_tirar_o_dump", espiao)
    dados = tmp_path / "dados"
    r = REST.testar(p, db=cg_casa["db"], pasta_dados=dados, senha="cifra-de-teste-123")
    assert r["situacao"] == REST.FALHOU and "antes da migração" in r["erro"]
    (tmp, nomes), = vistos
    assert (dados / REST.NOME_DA_PASTA_DE_TRABALHO).resolve() in tmp.resolve().parents
    assert pasta.resolve() not in tmp.resolve().parents
    assert "pacote.zip" not in nomes                     # o decifrado já saiu
    assert sorted(x.name for x in pasta.iterdir()) == [p.name]   # nada novo ao lado do pacote


def test_a_pasta_de_dados_dentro_da_dos_backups_e_recusada(tmp_path):
    pacote = tmp_path / "backups" / "backup_banco_2026-10-26.zip"
    with pytest.raises(REST.RestauracaoRecusada, match="dentro da pasta dos backups"):
        REST._pasta_de_trabalho(tmp_path / "backups" / "dados", pacote)


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
    # o pacote gerado entrou na lista que o teste de restauração confere (PR #27)
    diario = ROT.pacote_diario(pasta, ctx.hoje)
    with db.connect() as con:
        reg = banco(con).ler("SELECT sha256, origem FROM bk_pacotes WHERE arquivo = %s",
                             (diario.name,))
    assert reg and reg[-1]["sha256"] == BKP._sha256(diario) and reg[-1]["origem"] == "automação"
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
    # a reserva também registra o SHA-256 do que gerou (PR #27)
    with db.connect() as con:
        reg = banco(con).ler("SELECT sha256, origem FROM bk_pacotes WHERE arquivo = %s",
                             (diarios[0],))
    assert reg and reg[-1]["origem"] == "primeiro acesso do dia"
    assert reg[-1]["sha256"] == BKP._sha256(ROT.pacote_diario(pasta, date.today()))
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

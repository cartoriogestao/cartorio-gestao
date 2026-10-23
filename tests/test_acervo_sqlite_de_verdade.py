"""O acervo do E-Ofício fica SQLite, e quem só lê só lê — lote LH09, 21/10/2026.

POR QUE
    O `acervo_eoficio.sqlite3` (229 tabelas `tb*`, cópia estática do sistema
    antigo) NÃO vai para o PostgreSQL. Mas o desvio do `sqlite3.connect` e o
    `banco_pg.conectar` decidem pelo NOME do arquivo: o que termina em
    `cartorio_gestao.sqlite3`, ou foi registrado, cai no PostgreSQL. Medido no
    LH09: o RCPN aceita acervo pronto por upload, pasta digitada ou zip, e
    `instalar_acervo_de_sqlite` conferia o arquivo pelo `sqlite3.connect` — o
    arquivo com o nome do banco da casa ia ao PostgreSQL, achava as tabelas da
    casa, e a cópia seguinte punha a marca vazia do banco no lugar do acervo.

O QUE ESTES TESTES GUARDAM, PARA CADA UM QUE ABRE O ACERVO
    abre pela porta do SQLite (`banco_pg.conectar_sqlite`), e não pelo desvio
    nem pela ponte; quem só lê abre com `mode=ro` (e escrever estoura); quem
    MONTA o acervo — `acervo_eoficio.carregar` e `acervo_eo_vivo` — escreve, e
    também pela porta. O `app.py` só o põe no backup completo, como arquivo,
    sem abrir conexão nenhuma com ele.

Os acervos daqui são de exemplo: tabelas com o nome das do E-Ofício e valores
inventados.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_carga as AC  # noqa: E402
import acervo_eo_vivo as EV  # noqa: E402
import acervo_eoficio as AE  # noqa: E402
import banco_pg  # noqa: E402
import cnib_atualizador as ATZ  # noqa: E402
import selador_config as SC  # noqa: E402

pytestmark = pytest.mark.skipif(not banco_pg.ativo(),
                                reason="o desvio para o PostgreSQL só existe com CG_PG_DSN")

#: O `sqlite3.connect` de fábrica, guardado antes de qualquer espião: é com ele
#: que o teste monta os acervos de exemplo, sem contar como abertura.
_SQLITE_DE_FABRICA = banco_pg._CONNECT_ORIGINAL

TABELAS_DE_EXEMPLO = """
CREATE TABLE _acervo_info (chave TEXT PRIMARY KEY, valor TEXT);
INSERT INTO _acervo_info VALUES ('origem', 'acervo de exemplo');
CREATE TABLE tbCNIB_Registro (intChave INTEGER, DATAPEDIDO TEXT);
INSERT INTO tbCNIB_Registro VALUES (1, '2026-09-30');
CREATE TABLE tbCNIB_Propriedades (Cliente_ID TEXT, Secret_Code TEXT);
INSERT INTO tbCNIB_Propriedades VALUES ('cliente-de-exemplo', 'segredo-de-exemplo');
CREATE TABLE tbSeladorConfiguracao (strUrlSelador TEXT, strUsername TEXT, strPassword TEXT);
INSERT INTO tbSeladorConfiguracao VALUES ('https://selador.exemplo', 'usuario-exemplo',
    'senha-de-exemplo');
CREATE TABLE tbProtocoloGeralCustas (intID REAL, intQte INTEGER, curv_Emolumento REAL,
    curv_Ferc REAL, curValor_MP REAL, curValor_DP REAL, curvalor_ferrfis REAL);
INSERT INTO tbProtocoloGeralCustas VALUES (10.0, 2, 12.5, 0.5, 0.25, 0.25, 0.5);
"""


def _acervo(pasta: Path, nome: str = AE.NOME_BANCO) -> Path:
    """Um acervo de exemplo, SQLite de verdade (aberto sem o desvio)."""
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    sq = _SQLITE_DE_FABRICA(arquivo)
    try:
        sq.executescript(TABELAS_DE_EXEMPLO)
        sq.commit()
    finally:
        sq.close()
    return arquivo


def _mesmo(aberto: str, alvo: Path) -> bool:
    return Path(banco_pg._caminho_e_modo(aberto)[0]).resolve() == alvo.resolve()


@pytest.fixture()
def aberturas(monkeypatch):
    """Quem abriu o quê: pela porta do SQLite (`_CONNECT_ORIGINAL`), pelo desvio
    do `sqlite3.connect` e pela ponte do PostgreSQL (`Conexao`)."""
    feitas: dict[str, list] = {"porta": [], "desvio": [], "ponte": []}
    original = banco_pg._CONNECT_ORIGINAL
    desvio = sqlite3.connect
    abrir_ponte = banco_pg.Conexao.__init__

    def pela_porta(database, *a, **kw):
        feitas["porta"].append((str(database), kw))
        return original(database, *a, **kw)

    def pelo_desvio(database, *a, **kw):
        feitas["desvio"].append(str(database))
        return desvio(database, *a, **kw)

    def pela_ponte(self, db_path, *a, **kw):
        feitas["ponte"].append(str(db_path))
        return abrir_ponte(self, db_path, *a, **kw)

    monkeypatch.setattr(banco_pg, "_CONNECT_ORIGINAL", pela_porta)
    monkeypatch.setattr(sqlite3, "connect", pelo_desvio)
    monkeypatch.setattr(banco_pg.Conexao, "__init__", pela_ponte)
    return feitas


def _so_pela_porta(feitas: dict, arquivo: Path, *, escreve: bool = False) -> None:
    """O arquivo foi aberto pela porta do SQLite, nunca pelo desvio nem pela
    ponte. Quem só lê, sempre com `mode=ro`; quem monta o acervo (`escreve`)
    abre para escrever ao menos uma vez — e pode conferir depois, só lendo."""
    pela_porta = [(d, kw) for d, kw in feitas["porta"] if _mesmo(d, arquivo)]
    assert pela_porta, f"{arquivo.name} não foi aberto pela porta do SQLite: {feitas}"
    assert not [d for d in feitas["desvio"] if _mesmo(d, arquivo)], feitas["desvio"]
    assert not [d for d in feitas["ponte"] if _mesmo(d, arquivo)], feitas["ponte"]
    leituras = [banco_pg._caminho_e_modo(d)[1] and kw.get("uri") is True
                for d, kw in pela_porta]
    if escreve:
        assert not all(leituras), pela_porta
    else:
        assert all(leituras), pela_porta


def _so_le(con) -> None:
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("CREATE TABLE gravou (x)")


# ------------------------------------------------------------------ a porta

def test_a_porta_abre_o_sqlite_de_verdade_mesmo_com_o_nome_do_banco_da_casa(tmp_path):
    arquivo = _acervo(tmp_path, banco_pg.NOME_DO_BANCO_PRINCIPAL)
    antes = arquivo.read_bytes()
    assert banco_pg.e_banco_da_casa(arquivo)       # o desvio o mandaria ao PostgreSQL
    con = banco_pg.conectar_sqlite(arquivo)
    try:
        assert type(con) is sqlite3.Connection
        assert con.execute("SELECT DATAPEDIDO FROM tbCNIB_Registro").fetchone() == ("2026-09-30",)
        _so_le(con)
    finally:
        con.close()
    assert arquivo.read_bytes() == antes
    assert not banco_pg.schema_existe(arquivo)


def test_a_porta_nao_cria_o_arquivo_que_falta(tmp_path):
    falta = tmp_path / AE.NOME_BANCO
    with pytest.raises(sqlite3.OperationalError):
        banco_pg.conectar_sqlite(falta)
    assert not falta.exists()


def test_so_quem_monta_o_acervo_abre_para_escrever(tmp_path):
    arquivo = tmp_path / AE.NOME_BANCO
    con = banco_pg.conectar_sqlite(arquivo, so_leitura=False)
    try:
        assert type(con) is sqlite3.Connection
        con.execute("CREATE TABLE tbExemplo (x)")
        con.commit()
    finally:
        con.close()
    assert arquivo.is_file() and not banco_pg.schema_existe(arquivo)


# ------------------------------------------------------- a carga (acervo_carga)

def test_a_carga_abre_o_acervo_pela_porta_e_so_para_ler(tmp_path, aberturas):
    arquivo = _acervo(tmp_path)
    con = AC.abrir_acervo(tmp_path)               # a pasta: o nome vem da casa
    try:
        assert type(con) is sqlite3.Connection
        assert AC._um_do_acervo(con, "SELECT valor FROM _acervo_info")["valor"] == "acervo de exemplo"
        _so_le(con)
    finally:
        con.close()
    _so_pela_porta(aberturas, arquivo)


def test_o_caminho_digitado_com_o_nome_do_banco_le_o_arquivo_e_nao_o_postgresql(
        tmp_path, aberturas):
    """O Livro 3 aceita o caminho digitado."""
    arquivo = _acervo(tmp_path, banco_pg.NOME_DO_BANCO_PRINCIPAL)
    con = AC.abrir_acervo(arquivo)
    try:
        assert type(con) is sqlite3.Connection
        assert con.execute("SELECT count(*) FROM tbCNIB_Registro").fetchone() == (1,)
    finally:
        con.close()
    _so_pela_porta(aberturas, arquivo)


def test_instalar_acervo_enviado_com_o_nome_do_banco_copia_o_arquivo_certo(
        tmp_path, aberturas):
    origem = _acervo(tmp_path / "envio", banco_pg.NOME_DO_BANCO_PRINCIPAL)
    (tmp_path / "dados").mkdir()                  # a pasta de dados da casa
    feito = AC.instalar_acervo_de_sqlite(origem, tmp_path / "dados")
    destino = tmp_path / "dados" / AE.NOME_BANCO
    assert feito["arquivo"] == str(destino) and feito["tabelas"] == 5
    assert destino.read_bytes() == origem.read_bytes()
    _so_pela_porta(aberturas, origem)
    assert not banco_pg.schema_existe(origem)


def test_instalar_o_proprio_banco_da_casa_como_acervo_e_recusado_e_o_acervo_fica(
        cg_casa, aberturas):
    """O caminho digitado do banco da casa: antes ia à ponte, achava as tabelas
    da casa no PostgreSQL e copiava a marca vazia por cima do acervo."""
    acervo = _acervo(cg_casa["dados"])
    antes = acervo.read_bytes()
    with pytest.raises(AC.CargaError, match="não tem tabelas"):
        AC.instalar_acervo_de_sqlite(cg_casa["banco"], cg_casa["dados"])
    assert acervo.read_bytes() == antes
    _so_pela_porta(aberturas, Path(cg_casa["banco"]))


# ------------------------------------------- a montagem (acervo_eoficio, ao vivo)

def test_a_montagem_do_acervo_escreve_pela_porta_e_a_conferencia_so_le(tmp_path, aberturas):
    pasta = tmp_path / "exportado"
    pasta.mkdir()
    (pasta / "tbCNIB_Registro.jsonl").write_text(
        json.dumps({"intChave": 1, "DATAPEDIDO": "2026-09-30"}) + "\n", encoding="utf-8")
    destino = tmp_path / "dados" / AE.NOME_BANCO
    feito = AE.carregar(pasta, destino)
    assert feito["tabelas"] == 1 and feito["linhas"] == 1
    _so_pela_porta(aberturas, destino.with_suffix(destino.suffix + ".parcial"),
                   escreve=True)
    aberturas["porta"].clear()
    assert AE.conferir(destino) is None
    assert AE.resumo(destino)["problema"] is None
    _so_pela_porta(aberturas, destino)


def test_a_atualizacao_ao_vivo_do_protesto_escreve_pela_porta(tmp_path, aberturas):
    arquivo = _acervo(tmp_path / "dados")
    pasta = tmp_path / "ao_vivo"
    pasta.mkdir()
    (pasta / "tbAvisoProtesto.jsonl").write_text(
        json.dumps({"intChave": 7, "strNome": "FULANO DE TAL EXEMPLO"}) + "\n",
        encoding="utf-8")
    feito = EV.aplicar_jsonl_no_acervo(tmp_path / "dados", pasta)
    assert feito["tabelas"]["tbAvisoProtesto"] == 1 and not feito["novo"]
    _so_pela_porta(aberturas, arquivo, escreve=True)


# ------------------------------------------------------------------- a CNIB

def test_o_retrato_da_cnib_le_o_acervo_pela_porta_so_para_ler(cg_casa, aberturas):
    acervo = _acervo(Path(cg_casa["banco"]).parent)
    con = sqlite3.connect(cg_casa["banco"])
    try:
        assert ATZ.retrato_do_acervo(con) == "2026-09-30"
    finally:
        con.close()
    _so_pela_porta(aberturas, acervo)


def test_a_credencial_da_cnib_le_o_acervo_pela_porta_so_para_ler(
        cg_casa_logada, aberturas, monkeypatch):
    import centrais_cred as CRED
    import cnib_api as API
    gravado = {}
    monkeypatch.setattr(CRED, "gravar", lambda central, **kw: gravado.update(kw, central=central))
    monkeypatch.setattr(API, "esquecer_o_token", lambda: None)
    acervo = _acervo(Path(cg_casa_logada["banco"]).parent)
    c = cg_casa_logada["c"]
    c.get("/registro-imoveis/cnib/central")
    with c.session_transaction() as s:
        token = s.get("csrf_token") or s.get("_csrf_token")
    r = c.post("/registro-imoveis/cnib/central/credencial", data={"csrf_token": token})
    assert r.status_code == 302
    assert (gravado["usuario"], gravado["senha"]) == ("cliente-de-exemplo", "segredo-de-exemplo")
    _so_pela_porta(aberturas, acervo)


# ---------------------------------------------------------------- o selador

def test_o_selador_le_a_configuracao_do_acervo_pela_porta_so_para_ler(tmp_path, aberturas):
    acervo = _acervo(tmp_path)
    assert SC.ler_do_eoficio(acervo) == {"base_url": "https://selador.exemplo",
                                         "usuario": "usuario-exemplo",
                                         "senha": "senha-de-exemplo"}
    _so_pela_porta(aberturas, acervo)


# ---------------------------------------------- a ferramenta das custas (tools/)

def test_a_ferramenta_das_custas_le_o_acervo_pela_porta_so_para_ler(cg_casa, aberturas):
    caminho = RAIZ / "tools" / "quantidade_nas_custas_do_eoficio.py"
    spec = importlib.util.spec_from_file_location("_quantidade_nas_custas", caminho)
    ferramenta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ferramenta)
    acervo = _acervo(cg_casa["dados"] / "fora")
    medido = ferramenta.medir(Path(cg_casa["banco"]), acervo)
    assert medido["a_corrigir"] == [] and medido["recusados"] == []
    _so_pela_porta(aberturas, acervo)


# --------------------------------------------------------- o backup (app.py)

def test_o_backup_completo_leva_o_acervo_como_arquivo_sem_abrir_conexao(
        cg_casa_logada, aberturas, monkeypatch):
    db, dados = cg_casa_logada["db"], cg_casa_logada["dados"]

    def _copia_do_banco(destino: Path) -> Path:
        destino.write_bytes(b"SQLite format 3\x00copia de exemplo")
        return destino

    monkeypatch.setattr(db, "backup_database", _copia_do_banco)
    acervo = _acervo(dados)
    c = cg_casa_logada["c"]
    c.get("/configuracoes")
    with c.session_transaction() as s:
        token = s.get("csrf_token") or s.get("_csrf_token")
    baixado = c.post("/backup", data={"csrf_token": token})
    assert baixado.status_code == 200
    pacote = dados / "baixado.zip"
    pacote.write_bytes(baixado.data)
    with zipfile.ZipFile(pacote) as zf:
        assert zf.read(f"acervo/{AE.NOME_BANCO}") == acervo.read_bytes()
    for por_onde in ("porta", "desvio", "ponte"):
        abertos = [x[0] if isinstance(x, tuple) else x for x in aberturas[por_onde]]
        assert not [x for x in abertos if _mesmo(x, acervo)], (por_onde, abertos)

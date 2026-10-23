"""As ferramentas do lote L022 no PostgreSQL: a trava, a exceção e o «só lê».

RESSALVAS DA REVISÃO DO L022 (17/10/2026), conferidas no L022R:

  1. **`tools/limpar_teor_do_acervo.py`** apanhava `banco_pg.OperationalError`
     onde o código do SQLite apanhava `sqlite3.OperationalError`. O manual
     (armadilha 3) manda não trocar o tipo de exceção nesta etapa; a cópia de
     segurança que falha com o erro do `sqlite3` volta a cair no
     `shutil.copy2`, como antes.
  2. **O mesmo script troca o hash do ato** e só pode trocar o do ÚLTIMO da
     ficha. A conferência «há ato depois dele?» vinha antes da cópia do banco
     e fora de trava; um ato lavrado nesse meio-tempo ficava com o
     `hash_anterior` do hash que o script troca, e a corrente bifurcava. É o
     defeito que o L047R consertou no irmão
     (`limpar_marcador_do_selo_no_teor.py`): a conferência se refaz dentro de
     `ri_atos.numero`, a trava da lavratura em `ri_web`.
  3. **`tools/naturalidade_dos_assentos_do_rcpn.py`** perdera o
     `BEGIN IMMEDIATE` de antes da leitura dos candidatos sem ganhar trava.
  4. **`tools/medir_o_peso_da_conversa.py`** promete «NÃO ESCREVE NADA»: o
     `mode=ro` chega ao PostgreSQL e o servidor recusa a escrita.

Os dados são fictícios (fichas 99xx, teores «de exemplo»).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402
from ri_schema import hash_ato  # noqa: E402
from tools import limpar_teor_do_acervo as LIMPAR_TEOR  # noqa: E402
from tools import medir_o_peso_da_conversa as MEDIR  # noqa: E402
from tools import naturalidade_dos_assentos_do_rcpn as NATURALIDADE  # noqa: E402

pytestmark = pytest.mark.skipif(
    not banco_pg.ativo(),
    reason="ferramenta nativa: só roda com o PostgreSQL ligado (CG_PG_DSN)")


def _assunto_livre(chave: str) -> bool:
    """Outra conexão consegue a trava do assunto agora? Não espera por ela."""
    import psycopg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
        return bool(outra.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))", (chave,)).fetchone()[0])


def _copia_de_mentira(db_path, destino) -> Path:
    """No lugar do pg_dump: o teste é da trava, e não da cópia."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"copia de teste")
    return destino


@pytest.fixture()
def copias(monkeypatch, tmp_path):
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "copias"))
    monkeypatch.setattr(banco_pg, "copiar_para_arquivo", _copia_de_mentira)
    return tmp_path / "copias"


# ------------------------------------------------- o teor do acervo (RI)

FICHA_COM_RUIDO = (
    "conferida\n"
    "MATRICULA: 9.903 \n"
    "IMÓVEL: um lote de exemplo, situado na Rua Fictícia, s/n.\n"
    ".-.-.-.-.-.-.-.-.-.-.-.-.-.-")
FICHA_LIMPA = "IMÓVEL: um lote de exemplo, situado na Rua Fictícia, s/n."
ATO_COM_RUIDO = (
    "conferida\n"
    "R-01 — Registro  de exemplo, lavrado para o teste.\n"
    ".-.-.-.-.-.-.-.-.-.-.-.-.-.-")
ATO_LIMPO = "R-01 — Registro de exemplo, lavrado para o teste."


def _ficha_com_ruido(db) -> tuple[int, int]:
    with db.transaction() as con:
        bd = banco(con)
        mid = int(bd.escrever(
            "INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,"
            " tipo_ficha, teor, criado_em)"
            " VALUES (%s, '2-X', '2-X', 'ATIVO', 'ACERVO', %s, %s) RETURNING id",
            ("9903", FICHA_COM_RUIDO, "2026-10-18T10:00:00"))[0]["id"])
        aid = int(bd.escrever(
            "INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,"
            " hash_ato, hash_anterior, lavrado_em)"
            " VALUES (%s, 'R', 1, '2026-09-15', %s, %s, NULL, %s) RETURNING id",
            (mid, ATO_COM_RUIDO,
             hash_ato("9903", "R", 1, "2026-09-15", ATO_COM_RUIDO, None),
             "2026-09-15T10:00:00"))[0]["id"])
    return mid, aid


def _teores(db, mid: int, aid: int) -> tuple[str, dict]:
    with db.connect() as con:
        bd = banco(con)
        return (bd.valor("SELECT teor FROM ri_matriculas WHERE id=%s", (mid,)),
                bd.um("SELECT teor, hash_ato FROM ri_atos WHERE id=%s", (aid,)))


def _rastros(db) -> int:
    with db.connect() as con:
        return int(banco(con).valor(
            "SELECT count(*) AS n FROM audit_logs WHERE action='RI_TEOR_LIMPO'"))


@pytest.mark.parametrize("erro", [banco_pg.OperationalError, sqlite3.OperationalError],
                         ids=["erro_da_ponte", "erro_do_sqlite3"])
def test_a_copia_que_falha_cai_na_copia_do_arquivo_como_no_sqlite(
        cg_db, cg_db_path, monkeypatch, tmp_path, erro):
    mid, aid = _ficha_com_ruido(cg_db)

    def copia_que_falha(db_path, destino):
        raise erro("falha de exemplo na cópia do banco")

    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "copias"))
    monkeypatch.setattr(banco_pg, "copiar_para_arquivo", copia_que_falha)
    monkeypatch.setattr(sys, "argv", [
        "limpar_teor_do_acervo.py", str(cg_db_path),
        "--matricula", "9903", "--so-a-ficha", "--confirmar"])

    assert LIMPAR_TEOR.main() == 0

    copias = list((tmp_path / "copias").rglob("*.antes-de-limpar-o-teor-*"))
    assert len(copias) == 1, "a cópia de segurança não caiu no shutil.copy2"
    ficha, ato = _teores(cg_db, mid, aid)
    assert ficha == FICHA_LIMPA
    assert ato["teor"] == ATO_COM_RUIDO, "--so-a-ficha não mexe nos atos"


def test_o_teor_do_ato_se_limpa_e_a_ultima_conferencia_e_dentro_da_trava_da_lavratura(
        cg_db, cg_db_path, copias, monkeypatch):
    mid, aid = _ficha_com_ruido(cg_db)
    livre_na_conferencia = []
    original = LIMPAR_TEOR._atos_depois

    def espiao(bd, matricula_id, ato_id):
        livre_na_conferencia.append(_assunto_livre("ri_atos.numero"))
        return original(bd, matricula_id, ato_id)

    monkeypatch.setattr(LIMPAR_TEOR, "_atos_depois", espiao)
    monkeypatch.setattr(sys, "argv", [
        "limpar_teor_do_acervo.py", str(cg_db_path),
        "--matricula", "9903", "--confirmar"])

    assert LIMPAR_TEOR.main() == 0

    assert livre_na_conferencia and livre_na_conferencia[-1] is False, (
        "a conferência «há ato depois dele?» não se refez dentro da trava da "
        f"lavratura: {livre_na_conferencia}")
    assert all(livre_na_conferencia[:-1]), "a trava foi tomada antes da cópia"
    assert _assunto_livre("ri_atos.numero"), "a trava sobrou depois do script"
    ficha, ato = _teores(cg_db, mid, aid)
    assert ficha == FICHA_LIMPA
    assert ato["teor"] == ATO_LIMPO
    assert ato["hash_ato"] == hash_ato("9903", "R", 1, "2026-09-15", ATO_LIMPO, None)
    assert _rastros(cg_db) == 2
    assert len(list(copias.rglob("*.antes-de-limpar-o-teor-*"))) == 1


def test_o_ato_lavrado_depois_dele_durante_a_copia_faz_o_script_recusar(
        cg_db, cg_db_path, copias, monkeypatch, capsys):
    mid, aid = _ficha_com_ruido(cg_db)
    ficha_antes, ato_antes = _teores(cg_db, mid, aid)

    def copia_e_outro_balcao_lavra(db_path, destino):
        _copia_de_mentira(db_path, destino)
        # outro balcão, outra conexão: a AV-02 encadeia no hash de AGORA da R-01
        with cg_db.transaction() as con:
            banco(con).escrever(
                "INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,"
                " hash_ato, hash_anterior, lavrado_em)"
                " VALUES (%s, 'AV', 2, '2026-10-18', %s, %s, %s, %s)",
                (mid, "AV-02 — Averbação lavrada enquanto a cópia era tirada.",
                 "hash-da-av-02", ato_antes["hash_ato"], "2026-10-18T10:00:00"))
        return Path(destino)

    monkeypatch.setattr(banco_pg, "copiar_para_arquivo", copia_e_outro_balcao_lavra)
    monkeypatch.setattr(sys, "argv", [
        "limpar_teor_do_acervo.py", str(cg_db_path),
        "--matricula", "9903", "--confirmar"])

    assert LIMPAR_TEOR.main() == 1

    assert "RECUSA" in capsys.readouterr().err
    ficha, ato = _teores(cg_db, mid, aid)
    assert ato == ato_antes, (
        "o script trocou o hash da R-01 depois de a AV-02 encadear nele — a "
        "corrente de hash da ficha bifurcou")
    assert ficha == ficha_antes, "a recusa é do lote inteiro: nada se grava"
    assert _rastros(cg_db) == 0
    assert _assunto_livre("ri_atos.numero"), "a trava sobrou depois da recusa"


# ------------------------------------------- a naturalidade dos assentos (RCPN)

def test_a_naturalidade_le_os_candidatos_ja_com_o_assunto_travado(
        cg_db, cg_db_path, copias, monkeypatch):
    livre_na_leitura = []
    original = NATURALIDADE._candidatos

    def espiao(bd):
        livre_na_leitura.append(_assunto_livre("rc_pessoas.naturalidade"))
        return original(bd)

    monkeypatch.setattr(NATURALIDADE, "_candidatos", espiao)

    copia, _gravados = NATURALIDADE.aplicar(Path(cg_db_path))

    assert livre_na_leitura == [False], (
        "o script leu os candidatos sem a trava do assunto (era o BEGIN "
        "IMMEDIATE do SQLite): duas execuções ao mesmo tempo gravariam duas "
        "auditorias para o mesmo assento")
    assert _assunto_livre("rc_pessoas.naturalidade"), "a trava sobrou depois do script"
    assert copia.is_file(), "a cópia do banco não foi tirada antes de gravar"


def test_medir_a_naturalidade_nao_trava_nem_grava(cg_db, cg_db_path):
    m = NATURALIDADE.medir(Path(cg_db_path))
    assert set(m) == {"a_gravar", "recusados"}
    assert _assunto_livre("rc_pessoas.naturalidade")


# --------------------------------------------- o peso da conversa (agente)

def test_medir_o_peso_abre_o_banco_so_para_ler(cg_db, cg_db_path, monkeypatch):
    abertas = []
    original = MEDIR.banco

    def espiao(con):
        abertas.append(con)
        return original(con)

    monkeypatch.setattr(MEDIR, "BANCO_PADRAO", str(cg_db_path))
    monkeypatch.setattr(MEDIR, "banco", espiao)

    MEDIR.main(["medir_o_peso_da_conversa.py"])

    assert len(abertas) == 1
    con = abertas[0]
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            banco(con).escrever(
                "INSERT INTO settings (key, value) VALUES (%s, %s)",
                ("chave_de_teste_l022r", "x"))
    finally:
        con.close()
    with cg_db.connect() as outra:
        assert not banco(outra).um(
            "SELECT 1 AS um FROM settings WHERE key=%s", ("chave_de_teste_l022r",))

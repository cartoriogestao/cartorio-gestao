"""As ferramentas do lote L047 gravam sob a trava de quem numera.

RESSALVAS DA REVISÃO DO L047 (17/10/2026), consertadas no L047R. No SQLite o
`BEGIN IMMEDIATE` deixava um escritor por vez no banco inteiro; no PostgreSQL
cada transação trava só o seu assunto (`bd.travar`), e a trava só exclui quem
trava com a MESMA chave.

O QUE ESTES TESTES GUARDAM:

  1. **`tools/livro_e_cancelar_duplicata_116.py`** apaga o contador do Livro E
     (`nu_numeracao` RC_E). Ele travava com uma chave só dele
     (`nu_numeracao.RC_E`), que não exclui quem tira número do contador
     (`escrituracao`, `acervo_carga`: `nu_numeracao.proximo`). A conferência
     «não há outro assento no Livro E», refeita dentro da trava, não valia
     contra um ato numerado ao mesmo tempo.
  2. **`tools/limpar_marcador_do_selo_no_teor.py`** troca o hash do ato. A
     única recusa dele — «há ato depois deste na ficha» — era conferida ANTES
     da cópia do banco e fora de trava; um ato lavrado nesse meio-tempo ficava
     com o `hash_anterior` do hash que o script troca, e a corrente bifurcava.
     A conferência agora se refaz dentro de `ri_atos.numero`, a trava da
     lavratura em `ri_web`.

Os dados são fictícios (nomes «DE TAL EXEMPLO»).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402
from ri_lavrar_teor import MARCA_SELO  # noqa: E402
from ri_schema import hash_ato  # noqa: E402
from tools import limpar_marcador_do_selo_no_teor as LIMPAR  # noqa: E402
from tools import livro_e_cancelar_duplicata_116 as CANCELA_116  # noqa: E402

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


# ------------------------------------------------ o contador do Livro E (116)

def _semear_o_116(db) -> None:
    """O retrato medido em 13/10/2026, com nome fictício."""
    with db.transaction() as con:
        bd = banco(con)
        for ident, serie, especie in ((116, "RC_E", "OUTRO"), (6189, "RC_A", "NASCIMENTO")):
            bd.escrever(
                "INSERT INTO rc_assentos (id, serie, especie, numero, nome, situacao,"
                " origem, livro_volume, criado_em)"
                " VALUES (%s, %s, %s, 8686, %s, 'ATIVO', 'EOFICIO', %s, %s)",
                (ident, serie, especie, "FULANA DE TAL EXEMPLO", "1",
                 "2026-10-13T10:00:00"))
        bd.escrever(
            "INSERT INTO nu_numeracao (serie, proximo, maior_em_uso, semeado_de)"
            " VALUES ('RC_E', 8687, 8686, 'rc_assentos')")


def test_o_116_desfaz_o_contador_sob_a_trava_de_quem_tira_numero(
        cg_db, cg_db_path, copias, monkeypatch):
    _semear_o_116(cg_db)
    livre_na_medida = []
    original = CANCELA_116.medir

    def espiao(con):
        livre_na_medida.append(_assunto_livre("nu_numeracao.proximo"))
        return original(con)

    monkeypatch.setattr(CANCELA_116, "medir", espiao)
    monkeypatch.setattr(sys, "argv", [
        "livro_e_cancelar_duplicata_116.py", "--banco", str(cg_db_path), "--confirmar"])

    assert CANCELA_116.main() == 0

    # a primeira medida é só leitura; a segunda é a de dentro da trava
    assert livre_na_medida == [True, False], (
        "o script mediu e desfez o contador do Livro E sem a trava de quem tira "
        "número dele: um ato numerado ao mesmo tempo passaria pela conferência")
    assert _assunto_livre("nu_numeracao.proximo"), "a trava sobrou depois do script"
    with cg_db.connect() as con:
        bd = banco(con)
        assert bd.valor("SELECT situacao FROM rc_assentos WHERE id=116") == "CANCELADO"
        assert bd.valor("SELECT situacao FROM rc_assentos WHERE id=6189") == "ATIVO"
        assert not bd.um("SELECT 1 AS um FROM nu_numeracao WHERE serie='RC_E'")
        acoes = [r["action"] for r in bd.ler(
            "SELECT action FROM audit_logs WHERE action IN"
            " ('RCPN_ASSENTO_CANCELADO', 'NUMERACAO_SEMENTE_DESFEITA') ORDER BY id")]
    assert acoes == ["RCPN_ASSENTO_CANCELADO", "NUMERACAO_SEMENTE_DESFEITA"]
    assert len(list(copias.rglob("*CANCELA_116*"))) == 1


# ----------------------------------------------- o marcador do selo no teor (RI)

TEOR_COM_O_MARCADOR = (
    "AV-04 — Averbação de exemplo, lavrada para o teste.\n"
    f"{MARCA_SELO}\n"
    "[ selo / verificacao ]                    [ QR / autenticacao ]")


def _ficha_com_o_marcador(db) -> tuple[int, int]:
    with db.transaction() as con:
        bd = banco(con)
        mid = int(bd.escrever(
            "INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,"
            " tipo_ficha, teor, criado_em)"
            " VALUES (%s, '2-X', '2-X', 'ATIVO', 'ACERVO', %s, %s) RETURNING id",
            ("9902", "Teor de exemplo da ficha.", "2026-10-17T10:00:00"))[0]["id"])
        aid = int(bd.escrever(
            "INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,"
            " hash_ato, hash_anterior, lavrado_em)"
            " VALUES (%s, 'AV', 4, '2026-09-15', %s, %s, NULL, %s) RETURNING id",
            (mid, TEOR_COM_O_MARCADOR,
             hash_ato("9902", "AV", 4, "2026-09-15", TEOR_COM_O_MARCADOR, None),
             "2026-09-15T10:00:00"))[0]["id"])
    return mid, aid


def _ato(db, aid: int) -> dict:
    with db.connect() as con:
        return banco(con).um("SELECT teor, hash_ato FROM ri_atos WHERE id=%s", (aid,))


def _correcoes(db, aid: int) -> int:
    with db.connect() as con:
        return int(banco(con).valor(
            "SELECT count(*) AS n FROM audit_logs"
            " WHERE action='RI_ATO_TEOR_CORRIGIDO' AND entity_id=%s", (aid,)))


def test_o_teor_se_limpa_e_a_ultima_conferencia_e_dentro_da_trava_da_lavratura(
        cg_db, cg_db_path, copias, monkeypatch):
    _mid, aid = _ficha_com_o_marcador(cg_db)
    livre_na_conferencia = []
    original = LIMPAR._atos_depois

    def espiao(bd, ato):
        livre_na_conferencia.append(_assunto_livre("ri_atos.numero"))
        return original(bd, ato)

    monkeypatch.setattr(LIMPAR, "_atos_depois", espiao)
    monkeypatch.setattr(sys, "argv", [
        "limpar_marcador_do_selo_no_teor.py", str(cg_db_path),
        "--ato-id", str(aid), "--confirmar"])

    assert LIMPAR.main() == 0

    assert livre_na_conferencia and livre_na_conferencia[-1] is False, (
        "a conferência «há ato depois dele?» não se refez dentro da trava da "
        f"lavratura: {livre_na_conferencia}")
    assert all(livre_na_conferencia[:-1]), "a trava foi tomada antes da cópia"
    assert _assunto_livre("ri_atos.numero"), "a trava sobrou depois do script"
    ato = _ato(cg_db, aid)
    assert ato["teor"] == "AV-04 — Averbação de exemplo, lavrada para o teste."
    assert ato["hash_ato"] == hash_ato("9902", "AV", 4, "2026-09-15", ato["teor"], None)
    assert _correcoes(cg_db, aid) == 1


def test_o_ato_lavrado_depois_dele_durante_a_copia_faz_o_script_recusar(
        cg_db, cg_db_path, copias, monkeypatch, capsys):
    mid, aid = _ficha_com_o_marcador(cg_db)
    antes = _ato(cg_db, aid)

    def copia_e_outro_balcao_lavra(db_path, destino):
        _copia_de_mentira(db_path, destino)
        # outro balcão, outra conexão: a AV-05 encadeia no hash de AGORA da AV-04
        with cg_db.transaction() as con:
            banco(con).escrever(
                "INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,"
                " hash_ato, hash_anterior, lavrado_em)"
                " VALUES (%s, 'AV', 5, '2026-10-17', %s, %s, %s, %s)",
                (mid, "AV-05 — Averbação lavrada enquanto a cópia era tirada.",
                 "hash-da-av-05", antes["hash_ato"], "2026-10-17T10:00:00"))
        return Path(destino)

    monkeypatch.setattr(banco_pg, "copiar_para_arquivo", copia_e_outro_balcao_lavra)
    monkeypatch.setattr(sys, "argv", [
        "limpar_marcador_do_selo_no_teor.py", str(cg_db_path),
        "--ato-id", str(aid), "--confirmar"])

    assert LIMPAR.main() == 1

    assert "RECUSA" in capsys.readouterr().err
    assert _ato(cg_db, aid) == antes, (
        "o script trocou o hash da AV-04 depois de a AV-05 encadear nele — a "
        "corrente de hash da ficha bifurcou")
    assert _correcoes(cg_db, aid) == 0
    assert _assunto_livre("ri_atos.numero"), "a trava sobrou depois da recusa"

"""O protocolo do Protesto não repete o número de outro título (30/10/2026).

`numero_do_protocolo` contava os títulos do dia: com `0001` e `0003` gravados, a
conta dava `0003` outra vez. Agora é o maior do dia mais um, sob trava, e o que já
se emitiu fica em `pt_protocolos_emitidos`.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import bd_nativo                                 # noqa: E402
import protesto as PT                            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402
from test_protesto_chave_calculada import AGORA, SV, _apontar, _titulo  # noqa: E402


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    yield c
    c.close()


def _protocolo(con, tid):
    return con.execute("SELECT protocolo FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()["protocolo"]


def test_o_primeiro_do_dia_e_o_um(con):
    assert PT.numero_do_protocolo(con, AGORA) == "2610300001"


def test_a_sequencia_normal_nao_muda(con):
    tids = [_titulo(con, chave_origem=f"L:{i}") for i in range(3)]
    for tid in tids:
        _apontar(con, tid)
    assert [_protocolo(con, t) for t in tids] == [
        "2610300001", "2610300002", "2610300003"]


def test_buraco_na_sequencia_nao_repete_o_numero(con):
    """O defeito: dois do dia, e a contagem daria o `0003` de outro título."""
    _titulo(con, chave_origem="L:1", protocolo="2610300001")
    _titulo(con, chave_origem="L:2", protocolo="2610300003")
    novo = _titulo(con, chave_origem="L:3")
    _apontar(con, novo)
    assert _protocolo(con, novo) == "2610300004"


def test_dois_titulos_no_mesmo_protocolo_nao_atrapalham(con):
    _titulo(con, chave_origem="L:1", protocolo="2610300001")
    _titulo(con, chave_origem="L:2", protocolo="2610300001")
    novo = _titulo(con, chave_origem="L:3")
    _apontar(con, novo)
    assert _protocolo(con, novo) == "2610300002"


def test_o_numero_nao_volta_depois_que_o_titulo_sai(con):
    primeiro = _titulo(con, chave_origem="L:1")
    _apontar(con, primeiro)
    con.execute("DELETE FROM pt_atos WHERE titulo_id=?", (primeiro,))
    con.execute("DELETE FROM pt_devedores WHERE titulo_id=?", (primeiro,))
    con.execute("DELETE FROM pt_titulos WHERE id=?", (primeiro,))
    assert PT.numero_do_protocolo(con, AGORA) == "2610300002"


def test_o_banco_recusa_emitir_o_mesmo_numero_duas_vezes(con):
    tid = _titulo(con)
    _apontar(con, tid)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            """INSERT INTO pt_protocolos_emitidos(protocolo, titulo_id, emitido_em)
               VALUES (?,?,?)""", (_protocolo(con, tid), tid, AGORA))


def test_numero_do_protocolo_so_le(con):
    PT.numero_do_protocolo(con, AGORA)
    PT.numero_do_protocolo(con, AGORA)
    assert con.execute(
        "SELECT COUNT(*) n FROM pt_protocolos_emitidos").fetchone()["n"] == 0


def test_a_trava_vem_antes_da_leitura(con, monkeypatch):
    ordem = []
    travar = bd_nativo.Banco.travar
    ler = bd_nativo.Banco.ler

    def travar_e_anotar(self, chave):
        ordem.append(chave)
        return travar(self, chave)

    def ler_e_anotar(self, sql, *args, **kw):
        if "pt_protocolos_emitidos" in sql:
            ordem.append("leu")
        return ler(self, sql, *args, **kw)

    tid = _titulo(con)
    monkeypatch.setattr(bd_nativo.Banco, "travar", travar_e_anotar)
    monkeypatch.setattr(bd_nativo.Banco, "ler", ler_e_anotar)
    _apontar(con, tid)
    assert ordem.index("pt_titulos.protocolo") < ordem.index("leu")


def test_quem_ja_tem_protocolo_nao_emite(con):
    tid = _titulo(con, protocolo="7797140001")
    _apontar(con, tid)
    assert _protocolo(con, tid) == "7797140001"
    assert con.execute(
        "SELECT COUNT(*) n FROM pt_protocolos_emitidos").fetchone()["n"] == 0

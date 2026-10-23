"""Efeitos comuns do cancelamento de certidões emitidas."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import cancelamento_certidao as CANC  # noqa: E402
import papel_seguranca as PP  # noqa: E402


def test_confirmacao_aceita_checkbox_e_recusa_campo_ausente():
    assert CANC.declaracao_confirmada("1")
    assert CANC.declaracao_confirmada("on")
    assert CANC.declaracao_confirmada(True)
    assert not CANC.declaracao_confirmada(None)
    assert not CANC.declaracao_confirmada("0")


def test_concluir_cancela_selo_local_e_recupera_folha_do_mesmo_item():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    PP.init_papel_schema(con)
    con.execute(
        """CREATE TABLE sd_selos (
               id INTEGER PRIMARY KEY, numero TEXT, tabela TEXT, ato_id INTEGER,
               cancelado_em TEXT, cancelado_por TEXT,
               motivo_cancelamento TEXT)""")
    PP.receber_remessa(con, fornecedor="ARPENBRASIL", codigo_de="100",
                       codigo_ate="101", agora="2026-09-10T08:00:00")
    PP.usar(con, "100", tabela="rc_certidoes", ato_id=5,
            selo="CERTID000000ABC", agora="2026-09-10T08:10:00")
    PP.usar(con, "101", tabela="rc_certidoes", ato_id=6,
            selo="CERTID000000DEF", agora="2026-09-10T08:11:00")
    con.executemany(
        "INSERT INTO sd_selos VALUES (?,?,?,?,NULL,NULL,NULL)",
        [(1, "CERTID000000ABC", "rc_certidoes", 5),
         (2, "CERTID000000DEF", "rc_certidoes", 6)])

    r = CANC.concluir(
        con, tabela="rc_certidoes", ato_id=5,
        motivo="emitida com o nome incorreto", agora="2026-09-10T09:00:00",
        usuario="BEATRIZ")

    assert r == {"selos_cancelados_localmente": ["CERTID000000ABC"],
                 "folhas_recuperadas": ["100"]}
    selo = con.execute("SELECT * FROM sd_selos WHERE id=1").fetchone()
    assert selo["cancelado_em"] == "2026-09-10T09:00:00"
    assert selo["cancelado_por"] == "BEATRIZ"
    assert PP.ler(con, "100")["situacao"] == "EM BRANCO"
    assert PP.ler(con, "101")["situacao"] == "USADA"
    assert con.execute("SELECT cancelado_em FROM sd_selos WHERE id=2").fetchone()[0] is None

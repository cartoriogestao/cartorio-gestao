"""RCPN obito ensaio ? termo, certidao e seed idempotente."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# `ambiente` mora em SANDBOX\ambiente.py, FORA da pasta sistema, e nao viaja
# quando a arvore e copiada para empacotar - ali a coleta morria com
# ImportError (suite de 14/10/2026). Este ensaio so existe no SANDBOX: sem o
# modulo, pula; com ele, roda exatamente como antes.
import pytest

ambiente = pytest.importorskip(
    "ambiente", reason="ensaio do SANDBOX: SANDBOX\\ambiente.py nao esta nesta arvore")

ambiente.preparar_para_importar()

import rcpn_obito_ensaio as ROE
import rc_termo as RCT
from serventia import dados as dados_serventia


class RcpnObitoEnsaioTests(unittest.TestCase):
    def test_montar_certidao_tem_falecido(self):
        import database as DB

        db = DB.Database(ambiente.DADOS / "cartorio_gestao.sqlite3")
        with db.connect() as con:
            row = con.execute(
                "SELECT id FROM rc_assentos WHERE origem_chave=?", (ROE.MARCADOR,)
            ).fetchone()
        self.assertIsNotNone(row, "rodar semear.py --ensaio-revisao antes")
        with db.connect() as con:
            teor = ROE.montar_teor_certidao(con, db, int(row[0]))
        self.assertIn(ROE.NOME_FALECIDO, teor)
        self.assertIn("BITO", teor.upper())

    def test_termo_congelado_paridade_modelo(self):
        import database as DB

        db = DB.Database(ambiente.DADOS / "cartorio_gestao.sqlite3")
        with db.connect() as con:
            row = con.execute(
                "SELECT id, teor FROM rc_assentos WHERE origem_chave=?", (ROE.MARCADOR,)
            ).fetchone()
        self.assertIsNotNone(row)
        aid, gravado = int(row[0]), row[1] or ""
        self.assertGreater(len(gravado), 600)
        with db.connect() as con:
            previa = RCT.montar(con, aid, serventia=dados_serventia(db.get_settings))
        self.assertIn(ROE.NOME_FALECIDO, previa)
        self.assertIn(ROE.NOME_FALECIDO, gravado)

    def test_ensaio_no_banco(self):
        con = sqlite3.connect(ambiente.DADOS / "cartorio_gestao.sqlite3")
        a = con.execute(
            "SELECT id, especie, LENGTH(teor), origem_chave FROM rc_assentos WHERE origem_chave=?",
            (ROE.MARCADOR,),
        ).fetchone()
        self.assertIsNotNone(a)
        self.assertEqual(a[1], "OBITO")
        self.assertGreater(int(a[2] or 0), 600)
        c = con.execute(
            "SELECT id, especie, LENGTH(teor) FROM rc_certidoes WHERE assento_id=? ORDER BY id LIMIT 1",
            (a[0],),
        ).fetchone()
        self.assertIsNotNone(c)
        self.assertEqual(c[1], "OBITO")
        self.assertGreater(int(c[2] or 0), 400)


if __name__ == "__main__":
    unittest.main()

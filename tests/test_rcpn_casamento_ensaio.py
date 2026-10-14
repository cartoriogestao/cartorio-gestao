"""RCPN casamento ensaio — termo, certidao e seed idempotente."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ambiente

ambiente.preparar_para_importar()

import rcpn_casamento_ensaio as RCEns
import rc_termo as RCT
from serventia import dados as dados_serventia


class RcpnCasamentoEnsaioTests(unittest.TestCase):
    def test_montar_certidao_tem_nubentes(self):
        import database as DB

        db = DB.Database(ambiente.DADOS / "cartorio_gestao.sqlite3")
        with db.connect() as con:
            row = con.execute(
                "SELECT id FROM rc_assentos WHERE origem_chave=?", (RCEns.MARCADOR,)
            ).fetchone()
        self.assertIsNotNone(row, "rodar semear.py --ensaio-revisao antes")
        with db.connect() as con:
            teor = RCEns.montar_teor_certidao(con, db, int(row[0]))
        self.assertIn(RCEns.NOME_NUBENTE1, teor)
        self.assertIn(RCEns.NOME_NUBENTE2, teor)
        self.assertIn("CASAMENTO", teor.upper())

    def test_termo_congelado_paridade_modelo(self):
        import database as DB

        db = DB.Database(ambiente.DADOS / "cartorio_gestao.sqlite3")
        with db.connect() as con:
            row = con.execute(
                "SELECT id, teor FROM rc_assentos WHERE origem_chave=?", (RCEns.MARCADOR,)
            ).fetchone()
        self.assertIsNotNone(row)
        aid, gravado = int(row[0]), row[1] or ""
        self.assertGreater(len(gravado), 600)
        with db.connect() as con:
            previa = RCT.montar(con, aid, serventia=dados_serventia(db.get_settings))
        self.assertIn(RCEns.NOME_NUBENTE1, previa)
        self.assertIn(RCEns.NOME_NUBENTE2, previa)
        self.assertIn(RCEns.NOME_NUBENTE1, gravado)
        self.assertIn(RCEns.NOME_NUBENTE2, gravado)

    def test_ensaio_no_banco(self):
        con = sqlite3.connect(ambiente.DADOS / "cartorio_gestao.sqlite3")
        a = con.execute(
            "SELECT id, especie, LENGTH(teor), origem_chave FROM rc_assentos WHERE origem_chave=?",
            (RCEns.MARCADOR,),
        ).fetchone()
        self.assertIsNotNone(a)
        self.assertEqual(a[1], "CASAMENTO")
        self.assertGreater(int(a[2] or 0), 600)
        c = con.execute(
            "SELECT id, especie, LENGTH(teor) FROM rc_certidoes WHERE assento_id=? ORDER BY id LIMIT 1",
            (a[0],),
        ).fetchone()
        self.assertIsNotNone(c)
        self.assertEqual(c[1], "CASAMENTO")
        self.assertGreater(int(c[2] or 0), 400)


if __name__ == "__main__":
    unittest.main()

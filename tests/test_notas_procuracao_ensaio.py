"""Procuracao ensaio — paridade teor/modelo e traslado."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# `ambiente` mora em SANDBOX\ambiente.py, FORA da pasta sistema, e não viaja
# quando a árvore é copiada para empacotar — ali a coleta morria com
# ImportError (suíte de 14/10/2026). Este ensaio só existe no SANDBOX: sem o
# módulo, pula; com ele, roda exatamente como antes.
import pytest

ambiente = pytest.importorskip(
    "ambiente", reason="ensaio do SANDBOX: SANDBOX\\ambiente.py não está nesta árvore")

ambiente.preparar_para_importar()

import notas_procuracao_ensaio as NPE
import notas_teor as NT


class NotasProcuracaoEnsaioTests(unittest.TestCase):
    def test_montar_teor_tem_poderes_e_fecho_correto(self):
        import database as DB

        db = DB.Database(ambiente.DADOS / "cartorio_gestao.sqlite3")
        with db.connect() as con:
            teor = NPE.montar_teor(con, db)
        self.assertIn("Banco Sandbox", teor)
        self.assertNotIn("presente escritura foi lida", teor.lower())
        self.assertIn("instrumento de procur", teor.lower())

    def test_teor_sem_titulo_duplicado(self):
        titulo = "Procuracao publica"
        teor = (
            "<p><b>PROCURACAO PUBLICA</b></p>"
            "<p>Saibam quantos este publico instrumento virem...</p>"
        )
        limpo = NT.teor_sem_titulos_duplicados(teor, {titulo.upper()})
        self.assertNotIn("PROCURACAO PUBLICA", limpo.upper().split("SAIBAM")[0])

    def test_ensaio_no_banco(self):
        con = sqlite3.connect(ambiente.DADOS / "cartorio_gestao.sqlite3")
        row = con.execute(
            "SELECT id, situacao, LENGTH(teor), selo FROM nt_atos WHERE origem_chave=?",
            (NPE.MARCADOR,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "LAVRADO")
        self.assertGreater(int(row[2] or 0), 1500)
        self.assertTrue(row[3])


if __name__ == "__main__":
    unittest.main()
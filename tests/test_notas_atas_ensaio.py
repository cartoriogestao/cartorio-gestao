"""Ata notarial ensaio — paridade teor/modelo e traslado."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ambiente

ambiente.preparar_para_importar()

import notas_atas_ensaio as NAE
import notas_teor as NT


class NotasAtasEnsaioTests(unittest.TestCase):
    def test_montar_teor_tem_narracao_e_fecho_ata(self):
        import database as DB

        db = DB.Database(ambiente.DADOS / "cartorio_gestao.sqlite3")
        with db.connect() as con:
            teor = NAE.montar_teor(con, db)
        self.assertIn("WhatsApp", teor)
        self.assertNotIn("presente escritura foi lida", teor.lower())
        self.assertIn("ata notarial", teor.lower())

    def test_contexto_jinja_testemunhas(self):
        ctx = NT.contexto_jinja_partes(list(NAE.PARTES))
        self.assertIn("ANA LUCIA", ctx["testemunhas"].upper())
        self.assertNotIn("{{", ctx["testemunhas"])

    def test_teor_sem_titulo_duplicado(self):
        titulo = "Ata notarial"
        teor = (
            "<p><b>ATA NOTARIAL</b></p>"
            "<p>Saibam quantos esta ata notarial virem...</p>"
        )
        limpo = NT.teor_sem_titulos_duplicados(teor, {titulo.upper()})
        self.assertNotIn("ATA NOTARIAL", limpo.upper().split("SAIBAM")[0])

    def test_ensaio_no_banco(self):
        con = sqlite3.connect(ambiente.DADOS / "cartorio_gestao.sqlite3")
        row = con.execute(
            "SELECT id, situacao, LENGTH(teor), selo, tipo FROM nt_atos WHERE origem_chave=?",
            (NAE.MARCADOR,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[4], "ATA")
        self.assertEqual(row[1], "LAVRADO")
        self.assertGreater(int(row[2] or 0), 1200)
        self.assertTrue(row[3])


if __name__ == "__main__":
    unittest.main()

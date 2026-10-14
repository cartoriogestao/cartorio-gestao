"""L2-CERT-01 — certidoes RI ensaio alinhadas ao molde de emissao."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ri_certidao_emissao as RCE
from app import create_app


class Livro2CertidaoEnsaioTests(unittest.TestCase):
    def test_remontar_detecta_html_ensaio_curto(self):
        self.assertTrue(RCE.teor_precisa_remontar_modelo("<p>Certidao de ensaio</p>"))
        self.assertFalse(RCE.teor_precisa_remontar_modelo("<p>CERTIDAO DE INTEIRO TEOR</p>" * 40))

    def test_montar_corpo_apos_registrar_rotas(self):
        with TemporaryDirectory() as tmp:
            td = Path(tmp)
            app = create_app({"TESTING": True, "DATA_DIR": str(td)})
            with app.app_context():
                self.assertTrue(RCE.pronto())
                db = app.extensions["db"]
                with db.transaction() as con:
                    con.execute(
                        """INSERT INTO ri_matriculas (numero, livro, folha, tipo_ficha, situacao,
                           teor, teor_formato, origem, criado_em)
                           VALUES ('9999','2','1','ACERVO','ATIVA','teor teste','html','MANUAL',?)""",
                        (db.now(),),
                    )
                    mid = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
                corpo = RCE.montar_corpo(
                    mid, "INTEIRO_TEOR", certidao_numero=1, data_dir=td
                )
            self.assertIn("CERTID", corpo.upper())


if __name__ == "__main__":
    unittest.main()

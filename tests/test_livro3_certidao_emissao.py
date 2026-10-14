"""L3-CERT-01 - certidao L3 emissao alinhada ao molde da previa."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atrib_certidao as AC
import livro3_modelos_ensaio as L3E
import modelos_elementos as ELEM
import modelos_previa as PREVIA
import ra_registro as RA


class Livro3CertidaoEmissaoTests(unittest.TestCase):

    def _casa(self, td):
        from app import create_app

        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def test_modelo_emissao_igual_previa(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.connect() as con:
                molde_emitir = AC.modelo_certidao_livro3(con)
                partes = ELEM.partes_do_documento(con, "RI_LIVRO3_CERTIDAO")
                molde_previa = PREVIA.montar(partes)
            self.assertEqual(molde_emitir, molde_previa)

    def test_montar_teor_traz_hipoteca_e_banco(self):
        dados = {
            "registro": dict(L3E._REGISTRO),
            "atos": list(L3E._ATOS),
            "partes": list(L3E._PARTES),
        }
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.connect() as con:
                modelo = AC.modelo_certidao_livro3(con)
            teor = AC.montar_teor("LIVRO3", dados, modelo=modelo)
        self.assertIn("HIPOTECA", teor)
        self.assertIn("BANCO DO BRASIL", teor)
        self.assertIn("NATUREZA:", teor)
        self.assertIn("ATOS POSTERIORES AO REGISTRO:", teor)

    def test_remontar_atualiza_certidao_legada(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            agora = db.now()
            hoje = agora[:10]
            with db.transaction() as con:
                r = RA.registrar(
                    con,
                    natureza="HIPOTECA",
                    agora=agora,
                    titulo_tipo=L3E._REGISTRO["titulo_tipo"],
                    titulo_numero=L3E._REGISTRO["titulo_numero"],
                    data_titulo=L3E._REGISTRO["data_titulo"],
                    valor=L3E._REGISTRO["valor_centavos"] / 100,
                    parcelas=L3E._REGISTRO["parcelas"],
                    vencimento_inicial=L3E._REGISTRO["vencimento_inicial"],
                    vencimento_final=L3E._REGISTRO["vencimento_final"],
                    juros=L3E._REGISTRO["juros"],
                    garantia=L3E._REGISTRO["garantia"],
                    condicoes=L3E._REGISTRO["condicoes"],
                    teor=L3E._REGISTRO["teor"],
                    folha=L3E._REGISTRO["folha"],
                    partes=L3E._PARTES,
                    usuario="admin",
                )
                registro_id = int(r["registro_id"])
                emit = AC.emitir(
                    con, "LIVRO3", registro_id, hoje=hoje, agora=agora,
                    requerente="teste", usuario="admin")
                cid = int(emit["certidao_id"])
                con.execute(
                    "UPDATE at_certidoes SET teor=? WHERE id=?",
                    ("SANDBOX - teor legado sem molde.", cid))
            self.assertTrue(
                AC.certidao_livro3_teor_precisa_modelo_novo(
                    "SANDBOX - teor legado sem molde."))
            with db.transaction() as con:
                AC.remontar_teor_certidao_livro3(con, cid, agora=agora)
                lin = AC.certidao(con, cid)
            self.assertIn("HIPOTECA", lin["teor"])
            self.assertIn("BANCO DO BRASIL", lin["teor"])
            self.assertFalse(AC.certidao_livro3_teor_precisa_modelo_novo(
                lin["teor"]))


if __name__ == "__main__":
    unittest.main()

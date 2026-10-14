"""O Livro 3 terminado — notas de revisão, editar, descancelar e renumerar.

    «termine o desenvolvimento do livro 3, falta várias coisas que temos no
     livro 2» — o oficial, 21/09/2026

O QUE ESTES TESTES GUARDAM:

  1. **a nota de revisão não trava nada** — varredura dos nomes públicos, a
     mesma régua do CNIB, das fraudes e do usucapião;
  2. **a regra é a MESMA do Livro 2** — os pisos e as palavras se comparam
     contra `ri_revisao`, para as duas não divergirem no primeiro conserto;
  3. **baixar exige escrever o que se decidiu**, e a baixada não some;
  4. **ato com selo não se renumera** — o selo carrega o número dentro dele;
  5. **corrigir deixa o antes e o depois na auditoria**;
  6. **descancelar exige motivo escrito** e não apaga a averbação.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ra_correcoes as CORR
import ra_revisao as RV
import ri_revisao as RIRV

SENHA = "Senha#12345"


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class LivroTresTerminadoTests(unittest.TestCase):

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _registro(self, db, numero=1243, situacao="ATIVO"):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_registros(numero, livro, natureza, situacao,
                                            titulo_numero, valor_centavos,
                                            criado_em)
                   VALUES (?,'3','CEDULA_CREDITO_RURAL',?,?,?,?)""",
                (numero, situacao, "40/01390-1", 2399999, db.now()))
            return con.execute("SELECT id FROM ra_registros WHERE numero=?",
                               (numero,)).fetchone()[0]

    def _ato(self, db, registro_id, numero, **campos):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                       teor, criado_em)
                   VALUES (?,'AV',?,?,'teor de exemplo do ato',?)""",
                (registro_id, numero, db.now(), db.now()))
            ato_id = con.execute(
                "SELECT id FROM ra_atos WHERE registro_id=? AND numero=?",
                (registro_id, numero)).fetchone()[0]
            for coluna, valor in campos.items():
                con.execute(f"UPDATE ra_atos SET {coluna}=? WHERE id=?",
                            (valor, ato_id))
        return ato_id

    def _entrar(self, app, db):
        db.create_user("admin", "Administrador", SENHA, "ADMIN")
        cliente = app.test_client()
        entrada = cliente.get("/login").get_data(as_text=True)
        cliente.post("/login", data={"username": "admin", "password": SENHA,
                                     "csrf_token": csrf(entrada)},
                     follow_redirects=True)
        return cliente

    # -------------------------------------------------- as notas de revisão

    def test_a_nota_nao_recusa_ato_nenhum(self):
        proibidos = ("recusar", "impedir", "travar", "bloquear", "invalidar",
                     "anular", "lavrar", "selar")
        for nome in [n for n in dir(RV) if not n.startswith("_")]:
            for proibido in proibidos:
                self.assertNotIn(
                    proibido, nome.lower(),
                    f"`ra_revisao.{nome}` tem cara de decidir sobre o ato. A "
                    f"nota avisa — quem decide é quem assina.")

    def test_a_regra_e_a_mesma_do_livro_2(self):
        """Duas cópias divergem no primeiro conserto — por isso se comparam."""
        self.assertIs(RV.ABERTA, RIRV.ABERTA)
        self.assertIs(RV.BAIXADA, RIRV.BAIXADA)
        self.assertEqual(RV.SITUACOES, RIRV.SITUACOES)
        self.assertEqual(RV.ORIGENS, RIRV.ORIGENS)

    def test_baixar_exige_escrever_o_que_se_decidiu(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                nid = RV.anotar(con, registro_id=rid, assunto="Data do título",
                                nota="O cabeçalho diz 2010 e o corpo diz 2011.",
                                agora=db.now())
            for vazio in ("", "ok", "conferi"):
                with db.transaction() as con, self.assertRaises(RV.RevisaoError):
                    RV.baixar(con, nid, decisao=vazio, agora=db.now())
            with db.connect() as con:
                self.assertEqual(len(RV.do_registro(con, rid, so_abertas=True)), 1)

    def test_a_decisao_fica_escrita_e_a_nota_nao_some(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                nid = RV.anotar(con, registro_id=rid, assunto="Data do título",
                                nota="O cabeçalho diz 2010 e o corpo diz 2011.",
                                agora=db.now())
            with db.transaction() as con:
                RV.baixar(con, nid, agora=db.now(),
                          decisao="Conferido no livro de papel: 04/01/2011.")
            with db.connect() as con:
                todas = RV.do_registro(con, rid)
                self.assertEqual(len(todas), 1, "baixada não some")
                self.assertIn("04/01/2011", todas[0]["baixa_decisao"])
                self.assertEqual(RV.do_registro(con, rid, so_abertas=True), [])

    def test_a_nota_nao_cai_na_ficha_de_outro_registro(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            um, outro = self._registro(db, 1243), self._registro(db, 1198)
            ato_do_outro = self._ato(db, outro, 1)
            with db.transaction() as con, self.assertRaises(RV.RevisaoError):
                RV.anotar(con, registro_id=um, assunto="Conferir",
                          nota="Conferir a garantia antes de lavrar.",
                          agora=db.now(), ato_id=ato_do_outro)

    def test_a_nota_pode_ficar_na_minuta(self):
        """É a que mais importa: ela se lê antes de o ato existir."""
        import ra_minuta as MIN
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV",
                                teor="AV-01/1.243 - CANCELAMENTO INTEGRAL.",
                                agora=db.now())
                nid = RV.anotar(con, registro_id=rid, minuta_id=mid,
                                assunto="Partes",
                                nota="Cadastrar as partes antes de lavrar.",
                                agora=db.now())
            with db.connect() as con:
                self.assertEqual(RV.do_registro(con, rid)[0]["minuta_id"], mid)
            self.assertTrue(nid)

    def test_a_ficha_anota_e_baixa(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("Revisar antes de selar", tela)
            self.assertIn("não impede lavrar nem selar", tela)

            cliente.post(f"/livro3/{rid}/revisoes",
                         data={"csrf_token": csrf(tela),
                               "assunto": "Data do título",
                               "nota": "O cabeçalho diz 2010 e o corpo, 2011."},
                         follow_redirects=True)
            with db.connect() as con:
                notas = RV.do_registro(con, rid, so_abertas=True)
            self.assertEqual(len(notas), 1)

            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            cliente.post(f"/livro3/revisao/{notas[0]['id']}/baixar",
                         data={"csrf_token": csrf(tela),
                               "decisao": "Conferido no livro: 04/01/2011."},
                         follow_redirects=True)
            with db.connect() as con:
                self.assertEqual(RV.do_registro(con, rid, so_abertas=True), [])

    def test_a_fila_das_notas_abre_em_instalacao_nova(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            cliente = self._entrar(app, db)
            html = cliente.get("/livro3/revisoes").get_data(as_text=True)
            self.assertIn("Nada esperando conferência no Livro 3", html)

    # ------------------------------------------------------- as correções

    def test_corrigir_deixa_o_antes_e_o_depois_na_auditoria(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("Corrigir o registro", tela)
            cliente.post(f"/livro3/{rid}/editar",
                         data={"csrf_token": csrf(tela),
                               "titulo_numero": "40/01390-2",
                               "data_titulo": "2011-01-04"},
                         follow_redirects=True)
            with db.connect() as con:
                r = con.execute(
                    "SELECT titulo_numero, data_titulo FROM ra_registros "
                    "WHERE id=?", (rid,)).fetchone()
                linha = con.execute(
                    "SELECT details FROM audit_logs WHERE action=? "
                    "ORDER BY id DESC LIMIT 1",
                    ("RA_REGISTRO_CORRIGIDO",)).fetchone()
            self.assertEqual(r["titulo_numero"], "40/01390-2")
            self.assertEqual(r["data_titulo"], "2011-01-04")
            detalhes = json.loads(linha["details"])
            self.assertEqual(detalhes["titulo_numero"]["antes"], "40/01390-1")
            self.assertEqual(detalhes["titulo_numero"]["depois"], "40/01390-2")

    def test_campo_que_nao_se_corrige_por_aqui_e_recusado(self):
        """O número, o livro, a situação e a origem dizem onde o ato está."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            for campo in ("numero", "livro", "situacao", "origem"):
                with db.transaction() as con, self.assertRaises(CORR.CorrecaoError):
                    CORR.editar(con, rid, campos={campo: "x"}, agora=db.now())

    def test_descancelar_exige_motivo_e_nao_apaga_a_averbacao(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db, situacao="CANCELADO")
            self._ato(db, rid, 1)
            with db.transaction() as con, self.assertRaises(CORR.CorrecaoError):
                CORR.descancelar(con, rid, motivo="engano", agora=db.now())
            with db.transaction() as con:
                CORR.descancelar(con, rid, agora=db.now(),
                                 motivo="Cancelado por engano pelo balcão.")
            with db.connect() as con:
                situacao = con.execute(
                    "SELECT situacao FROM ra_registros WHERE id=?",
                    (rid,)).fetchone()[0]
                atos = con.execute(
                    "SELECT COUNT(*) FROM ra_atos WHERE registro_id=?",
                    (rid,)).fetchone()[0]
            self.assertEqual(situacao, "ATIVO")
            self.assertEqual(atos, 1, "a averbação continua no livro")

    def test_registro_que_nao_esta_cancelado_nao_se_descancela(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con, self.assertRaises(CORR.CorrecaoError):
                CORR.descancelar(con, rid, agora=db.now(),
                                 motivo="quero descancelar mesmo assim")

    def test_renumerar_poe_os_atos_na_ordem_da_lavratura(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            self._ato(db, rid, 5)
            self._ato(db, rid, 9)
            with db.connect() as con:
                fora = [a for a in CORR.numeracao_dos_atos(con, rid)
                        if a["fora_do_lugar"]]
            self.assertEqual(len(fora), 2)
            with db.transaction() as con:
                CORR.renumerar(con, rid, agora=db.now())
            with db.connect() as con:
                numeros = [a["numero"] for a in
                           CORR.numeracao_dos_atos(con, rid)]
            self.assertEqual(numeros, [1, 2])

    def test_ato_com_selo_nao_se_renumera(self):
        """O selo carrega o número do ato dentro dele, e não se reescreve."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            self._ato(db, rid, 5, selo="SELO-QUE-JA-SAIU")
            with db.transaction() as con, self.assertRaises(CORR.CorrecaoError) as erro:
                CORR.renumerar(con, rid, agora=db.now())
            self.assertIn("já tem selo", str(erro.exception))

    def test_numeracao_ja_continua_nao_se_renumera(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            self._ato(db, rid, 1)
            self._ato(db, rid, 2)
            with db.transaction() as con, self.assertRaises(CORR.CorrecaoError):
                CORR.renumerar(con, rid, agora=db.now())


if __name__ == "__main__":
    unittest.main()

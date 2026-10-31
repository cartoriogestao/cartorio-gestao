"""A minuta do Livro 3 — item 1 da fila do oficial, 20/09/2026.

    «deixe o livro 3 com as mesmas ferramentas do livro 2»
    «Coloque todos esses itens do livro 3 na fila para fazer imediatamente
     depois de resolver a cnib»

O QUE ESTES TESTES GUARDAM, em ordem de importância:

  1. **a minuta não lavra, não numera, não sela e não cobra** — varredura dos
     nomes públicos, a mesma régua das fraudes, do CNIB e do usucapião;
  2. **ela se marca lavrada na MESMA transação do ato** — ato que não entra
     tem de deixar a minuta esperando;
  3. **descartar exige motivo escrito, e descartada não some** — a pergunta
     que aparece meses depois é «e aquela averbação que estava para sair?»;
  4. **minuta lavrada não se revisa** — mudar o texto faria a prova discordar
     do que está no livro;
  5. **o número é pretendido, e não reservado**;
  6. **a fila existe e a ficha mostra as três situações**.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ra_minuta as MIN

SENHA = "Senha#12345"
TEOR = ("AV-01/1.198 - CANCELAMENTO INTEGRAL DO REGISTRO, à vista do "
        "instrumento de baixa expedido pelo credor.")


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class TipoDaMinutaTests(unittest.TestCase):
    """A tela diz AVERBACAO, e a minuta fala `AV`. Sem isto, os dois botões de guardar sempre recusavam."""

    def test_a_tela_e_o_rascunho_viram_a_lingua_do_livro(self):
        import ra_minuta_web
        for bruto, esperado in (("AVERBACAO", "AV"), ("averbacao", "AV"), ("AV", "AV"), ("", "AV"), (None, "AV"),
                                ("R", "R"), (" r ", "R"), ("CANCELAMENTO", "CANCELAMENTO")):
            self.assertEqual(ra_minuta_web.tipo_da_minuta(bruto), esperado, bruto)

    def test_o_que_a_traducao_devolve_o_dominio_aceita_ou_recusa(self):
        import ra_minuta_web
        self.assertIn(ra_minuta_web.tipo_da_minuta("AVERBACAO"), MIN.TIPOS)
        self.assertNotIn(ra_minuta_web.tipo_da_minuta("CANCELAMENTO"), MIN.TIPOS)


class MinutaDoLivro3Tests(unittest.TestCase):

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _registro(self, db, numero=1198):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_registros(numero, livro, natureza, situacao,
                                            criado_em)
                   VALUES (?,'3','CEDULA_CREDITO_RURAL','ATIVO',?)""",
                (numero, db.now()))
            return con.execute("SELECT id FROM ra_registros WHERE numero=?",
                               (numero,)).fetchone()[0]

    def _ato(self, db, registro_id, numero=1):
        """Um ato de verdade — a chave estrangeira de `ato_id` é real, e é ela
        que impede a minuta apontar para um ato que não existe."""
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                       teor, criado_em)
                   VALUES (?,'AV',?,?,?,?)""",
                (registro_id, numero, db.now(), TEOR, db.now()))
            return con.execute(
                "SELECT id FROM ra_atos WHERE registro_id=? AND numero=?",
                (registro_id, numero)).fetchone()[0]

    def _entrar(self, app, db, papel="ADMIN"):
        db.create_user("admin", "Administrador", SENHA, papel)
        cliente = app.test_client()
        entrada = cliente.get("/login").get_data(as_text=True)
        cliente.post("/login", data={"username": "admin", "password": SENHA,
                                     "csrf_token": csrf(entrada)},
                     follow_redirects=True)
        return cliente

    # ------------------------------------------------ a que mais importa

    def test_o_modulo_nao_lavra_nem_numera_nem_sela_nem_cobra(self):
        proibidos = ("lavrar", "numerar", "selar", "cobrar", "protocolar")
        for nome in [n for n in dir(MIN) if not n.startswith("_")]:
            for proibido in proibidos:
                self.assertNotIn(
                    proibido, nome.lower(),
                    f"`ra_minuta.{nome}` tem cara de praticar ato. Quem lavra "
                    f"é a rota de sempre, com os campos preenchidos.")
        # `marcar_lavrada` é o contrário: ela ANOTA que o ato saiu, e o nome
        # diz isso — por isso a varredura procura o verbo, e não a palavra.
        self.assertTrue(hasattr(MIN, "marcar_lavrada"))

    def test_a_minuta_so_se_marca_lavrada_se_o_ato_entrar(self):
        """A marca vai na mesma transação do ato — e some com ela."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
            ato_id = self._ato(db, rid)
            # uma transação que falha DEPOIS de marcar a minuta
            with self.assertRaises(RuntimeError), db.transaction() as con:
                MIN.marcar_lavrada(con, mid, ato_id=ato_id, agora=db.now())
                raise RuntimeError("o ato não entrou")
            with db.connect() as con:
                self.assertEqual(MIN.uma(con, mid)["situacao"], MIN.A_REVISAR,
                                 "ato que não entra deixa a minuta esperando")

    def test_nao_se_lavra_a_mesma_minuta_duas_vezes(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
            um, outro = self._ato(db, rid, 1), self._ato(db, rid, 2)
            with db.transaction() as con:
                MIN.marcar_lavrada(con, mid, ato_id=um, agora=db.now())
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.marcar_lavrada(con, mid, ato_id=outro, agora=db.now())

    def test_descartar_exige_motivo_escrito_e_a_minuta_nao_some(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
            for vazio in ("", "   ", "não", "não serve"):
                with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                    MIN.descartar(con, mid, motivo=vazio, agora=db.now())
            with db.transaction() as con:
                MIN.descartar(con, mid, agora=db.now(),
                              motivo="O credor recolheu o pedido de baixa.")
            with db.connect() as con:
                todas = MIN.listar(con, rid, situacao=None)
                self.assertEqual(len(todas), 1, "descartada não some")
                self.assertEqual(todas[0]["situacao"], MIN.DESCARTADA)
                self.assertIn("recolheu", todas[0]["observacao"])
                self.assertEqual(MIN.listar(con, rid), [],
                                 "mas sai da fila do que falta revisar")

    def test_minuta_lavrada_nao_se_revisa(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
            ato_id = self._ato(db, rid)
            with db.transaction() as con:
                MIN.marcar_lavrada(con, mid, ato_id=ato_id, agora=db.now())
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.atualizar(con, mid, teor=TEOR + " corrigido",
                              agora=db.now())

    def test_a_revisao_nao_apaga_o_que_nao_veio_no_formulario(self):
        """`None` quer dizer «não mexi», e não «esvazie» — o item do selo é o
        que mais custa perder: é ele que o selo exige."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now(), codigo_tj="16.22.2",
                                natureza_titulo="BAIXA DE HIPOTECA")
            with db.transaction() as con:
                MIN.atualizar(con, mid, teor=TEOR + " revisado",
                              agora=db.now())
            with db.connect() as con:
                m = MIN.uma(con, mid)
            self.assertEqual(m["codigo_tj"], "16.22.2")
            self.assertEqual(m["natureza_titulo"], "BAIXA DE HIPOTECA")
            self.assertIn("revisado", m["teor"])

    def test_o_teor_curto_e_recusado(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.criar(con, registro_id=rid, tipo="AV", teor="cancela",
                          agora=db.now())

    def test_o_tipo_fora_do_vocabulario_e_recusado(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.criar(con, registro_id=rid, tipo="CANCELAMENTO",
                          teor=TEOR, agora=db.now())

    def test_a_minuta_nao_cai_em_registro_que_nao_existe(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.criar(con, registro_id=9999, tipo="AV", teor=TEOR,
                          agora=db.now())

    # ------------------------------------------------------------ as telas

    def test_a_fila_abre_em_instalacao_nova_e_mostra_o_que_espera(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            cliente = self._entrar(app, db)
            html = cliente.get("/livro3/minutas").get_data(as_text=True)
            self.assertIn("Nada esperando revisão no Livro 3", html)

            rid = self._registro(db)
            with db.transaction() as con:
                MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                          agora=db.now())
            html = cliente.get("/livro3/minutas").get_data(as_text=True)
            self.assertIn("1198", html)
            self.assertIn("CANCELAMENTO INTEGRAL", html)

    def test_a_ficha_guarda_a_revisao_sem_lavrar(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("Minutas — a revisar e lavrar", tela)

            cliente.post(f"/livro3/minuta/{mid}/guardar",
                         data={"csrf_token": csrf(tela),
                               "teor": TEOR + " Revisado pelo oficial.",
                               "codigo_tj": "16.22.2"},
                         follow_redirects=True)
            with db.connect() as con:
                m = MIN.uma(con, mid)
                atos = con.execute(
                    "SELECT COUNT(*) FROM ra_atos WHERE registro_id=?",
                    (rid,)).fetchone()[0]
            self.assertIn("Revisado pelo oficial", m["teor"])
            self.assertEqual(m["situacao"], MIN.A_REVISAR)
            self.assertEqual(atos, 0, "guardar a revisão NÃO lavra")

    def test_a_tela_manda_o_tipo_do_lancar_e_a_revisao_grava(self):
        """O POST é o da tela: o formulário leva `tipo=AVERBACAO`, para a rota de lançar."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
                de_registro = MIN.criar(con, registro_id=rid, tipo="R",
                                        teor=TEOR, agora=db.now())
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn('name="tipo" value="AVERBACAO"', tela)

            r = cliente.post(f"/livro3/minuta/{mid}/guardar",
                             data={"csrf_token": csrf(tela), "tipo": "AVERBACAO",
                                   "teor": TEOR + " Revisado."},
                             follow_redirects=True)
            self.assertIn("Revisão guardada", r.get_data(as_text=True))
            cliente.post(f"/livro3/minuta/{de_registro}/guardar",
                         data={"csrf_token": csrf(tela), "tipo": "AVERBACAO",
                               "teor": TEOR + " Revisado."})
            with db.connect() as con:
                self.assertIn("Revisado", MIN.uma(con, mid)["teor"])
                self.assertEqual(MIN.uma(con, de_registro)["tipo"], "R",
                                 "a revisão não troca o tipo da minuta")

    def test_guardar_como_minuta_pelo_formulario_de_lancar(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            r = cliente.post(f"/livro3/{rid}/minuta",
                             data={"csrf_token": csrf(tela), "tipo": "AVERBACAO",
                                   "teor": TEOR},
                             follow_redirects=True)
            self.assertIn("Minuta guardada", r.get_data(as_text=True))
            with db.connect() as con:
                fila = MIN.a_revisar(con)
                atos = con.execute(
                    "SELECT COUNT(*) FROM ra_atos WHERE registro_id=?",
                    (rid,)).fetchone()[0]
            self.assertEqual([m["tipo"] for m in fila], ["AV"])
            self.assertEqual(atos, 0, "guardar como minuta NÃO lavra")

    def test_o_rascunho_de_tela_vira_minuta_por_um_botao(self):
        """A ponte com o que já existia — e ela não é migração calada."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO rascunhos_de_tela
                          (tela, chave, titulo, dados_json, criado_em)
                       VALUES ('livro3_minuta_av','livro3-cancelamento:1198',
                               'Minuta AV cancelamento', ?, ?)""",
                    ('{"tipo": "AVERBACAO", "teor": ' + repr(TEOR).replace("'", '"') + '}',
                     db.now()))
                rascunho_id = con.execute(
                    "SELECT id FROM rascunhos_de_tela ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("Trazer para as minutas", tela)

            cliente.post(f"/livro3/{rid}/minuta/do-rascunho/{rascunho_id}",
                         data={"csrf_token": csrf(tela)},
                         follow_redirects=True)
            with db.connect() as con:
                minutas = MIN.listar(con, rid)
                # O RASCUNHO FICA ONDE ESTAVA: apagar o que outra tela guardou
                # não é desta rota.
                ainda = con.execute(
                    "SELECT COUNT(*) FROM rascunhos_de_tela WHERE id=?",
                    (rascunho_id,)).fetchone()[0]
            self.assertEqual(len(minutas), 1)
            self.assertEqual(minutas[0]["tipo"], "AV",
                             "o rascunho diz AVERBACAO; o livro fala AV")
            self.assertEqual(minutas[0]["origem"], MIN.RASCUNHO_DE_TELA)
            self.assertEqual(ainda, 1)

    def test_lavrar_pela_minuta_marca_ela_lavrada(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            cliente.post(f"/livro3/{rid}/lancar",
                         data={"csrf_token": csrf(tela), "tipo": "AVERBACAO",
                               "teor": TEOR, "minuta_id": str(mid)},
                         follow_redirects=True)
            with db.connect() as con:
                m = MIN.uma(con, mid)
                ato = con.execute(
                    "SELECT id, tipo FROM ra_atos WHERE registro_id=?",
                    (rid,)).fetchone()
            self.assertIsNotNone(ato, "o ato foi lavrado")
            self.assertEqual(m["situacao"], MIN.LAVRADA)
            self.assertEqual(m["ato_id"], ato["id"])


if __name__ == "__main__":
    unittest.main()

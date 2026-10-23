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
  6. **descancelar exige motivo escrito** e não apaga a averbação;
  7. **dois balcões ao mesmo tempo** (ressalvas da revisão do L012,
     consertadas no L012R): a renumeração trava com a chave da lavratura e
     conta o ato lavrado no meio; corrigir e descancelar leem a linha presa
     (`FOR UPDATE`), e o «antes» e a situação são os que valem agora.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import banco_pg
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

    # --------------------------------------------- dois balcões ao mesmo tempo
    #
    # No SQLite a rota abria `BEGIN IMMEDIATE` e ninguém mais escrevia até ela
    # acabar; no PostgreSQL a transação é de cada um, e o que se lê para depois
    # gravar precisa de trava (`bd.travar`) ou de `SELECT ... FOR UPDATE`.
    # DUAS CONEXÕES NO MESMO BANCO são dois balcões: a segunda roda numa thread
    # e fica parada enquanto a primeira não confirma.

    def _segundo_balcao(self, db, chamar):
        resposta: dict = {}

        def rodar():
            con = db.connect()
            try:
                resposta["r"] = chamar(con)
                con.commit()
            except Exception as erro:  # noqa: BLE001 — o teste mostra qual foi
                resposta["erro"] = erro
            finally:
                con.close()

        t = threading.Thread(target=rodar, daemon=True)
        t.start()
        # O segundo chega enquanto o primeiro ainda não confirmou.
        t.join(1.0)
        return t, resposta

    def _esperar(self, t, primeiro):
        primeiro.commit()
        primeiro.close()
        t.join(15)
        self.assertFalse(t.is_alive(), "o segundo balcão ficou preso")

    def test_renumerar_conta_o_ato_lavrado_pelo_outro_balcao_no_meio(self):
        import ra_registro as RAREG
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            self._ato(db, rid, 5)
            self._ato(db, rid, 9)
            primeiro = db.connect()
            lavrado = RAREG.averbar(primeiro, rid, agora=db.now(),
                                    teor="Averbação lavrada pelo outro balcão.")
            self.assertEqual(lavrado["numero"], 10)
            t, resposta = self._segundo_balcao(
                db, lambda c: CORR.renumerar(c, rid, agora=db.now()))
            self._esperar(t, primeiro)
            self.assertNotIn("erro", resposta, resposta.get("erro"))
            with db.connect() as con:
                numeros = [a["numero"] for a in
                           CORR.numeracao_dos_atos(con, rid)]
            self.assertEqual(
                numeros, [1, 2, 3],
                "a renumeração leu a ficha antes do ato lavrado no meio, e a "
                "numeração saiu furada")

    def test_renumerar_trava_com_a_mesma_chave_da_lavratura(self):
        import bd_nativo
        import ra_registro as RAREG
        chaves: list[str] = []
        travar = bd_nativo.Banco.travar

        def anotar(banco_, chave):
            chaves.append(chave)
            return travar(banco_, chave)

        with TemporaryDirectory() as td, \
                mock.patch.object(bd_nativo.Banco, "travar", anotar):
            _, db = self._casa(td)
            rid = self._registro(db)
            self._ato(db, rid, 5)
            with db.transaction() as con:
                RAREG.averbar(con, rid, agora=db.now(),
                              teor="Averbação de teste da trava.")
            da_lavratura = set(chaves)
            chaves.clear()
            with db.transaction() as con:
                CORR.renumerar(con, rid, agora=db.now())
            self.assertIn(f"ra_atos.numero:{rid}", da_lavratura)
            self.assertIn(f"ra_atos.numero:{rid}", chaves)

    def test_corrigir_ao_mesmo_tempo_o_antes_e_o_que_o_outro_gravou(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            primeiro = db.connect()
            CORR.editar(primeiro, rid, campos={"titulo_numero": "40/01390-2"},
                        agora=db.now())
            t, resposta = self._segundo_balcao(
                db, lambda c: CORR.editar(
                    c, rid, campos={"titulo_numero": "40/01390-3"},
                    agora=db.now()))
            self._esperar(t, primeiro)
            self.assertNotIn("erro", resposta, resposta.get("erro"))
            self.assertEqual(
                resposta["r"]["titulo_numero"],
                {"antes": "40/01390-2", "depois": "40/01390-3"},
                "a auditoria do segundo balcão contou um «antes» que o "
                "primeiro já tinha corrigido")

    def test_dois_descancelamentos_ao_mesmo_tempo_o_segundo_e_recusado(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db, situacao="CANCELADO")
            primeiro = db.connect()
            CORR.descancelar(primeiro, rid, agora=db.now(),
                             motivo="Cancelado por engano pelo balcão.")
            t, resposta = self._segundo_balcao(
                db, lambda c: CORR.descancelar(
                    c, rid, agora=db.now(),
                    motivo="O outro balcão viu o mesmo engano."))
            self._esperar(t, primeiro)
            self.assertIsInstance(
                resposta.get("erro"), CORR.CorrecaoError,
                "o segundo descancelamento passou pela conferência com a "
                "situação de antes do primeiro")
            self.assertIn("não está cancelado", str(resposta["erro"]))

    # ------------------------------ o ato que volta a ser minuta, e a minuta
    #
    # Ressalva da revisão do L038: `ra_minuta.voltar_do_ato` contava os atos
    # depois deste e apagava sem trava nem FOR UPDATE, e a minuta conferia «já
    # virou ato?» sem prender a linha. Os dois últimos testes rodam SEM a
    # ponte: com ela, a trava única do banco esconde o FOR UPDATE que falta.

    def _sem_a_ponte(self, db, *, autocommit=False):
        """Uma conexão do psycopg no schema da casa, SEM a ponte — como a
        transação vai ficar quando a ponte sair."""
        import psycopg
        c = db.connect()
        schema = c.schema
        c.close()
        pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
        pg.execute(f'SET search_path TO "{schema}", public')
        if not autocommit:
            pg.commit()
        return pg

    def _segundo_balcao_sem_a_ponte(self, db, primeiro, chamar):
        """O segundo balcão sem a ponte, numa thread. O primeiro só confirma
        quando o segundo está ESPERANDO por ele (ou já acabou)."""
        dois = self._sem_a_ponte(db)
        vigia = self._sem_a_ponte(db, autocommit=True)
        pid = dois.execute("SELECT pg_backend_pid()").fetchone()[0]
        dois.rollback()
        resposta: dict = {}

        def rodar():
            try:
                resposta["r"] = chamar(dois)
                dois.commit()
            except Exception as erro:  # noqa: BLE001 — o teste mostra qual foi
                resposta["erro"] = erro
                dois.rollback()

        t = threading.Thread(target=rodar, daemon=True)
        t.start()
        for _ in range(200):
            if not t.is_alive() or vigia.execute(
                    "SELECT count(*) FROM pg_locks WHERE pid=%s AND NOT granted",
                    (pid,)).fetchone()[0]:
                break
            time.sleep(0.05)
        primeiro.commit()
        t.join(15)
        for c in (primeiro, dois, vigia):
            c.close()
        self.assertFalse(t.is_alive(), "o segundo balcão ficou preso")
        return resposta

    def test_voltar_do_ato_conta_o_ato_lavrado_pelo_outro_balcao_no_meio(self):
        import ra_minuta as MIN
        import ra_registro as RAREG
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            self._ato(db, rid, 1)
            ultimo = self._ato(db, rid, 2)
            primeiro = db.connect()
            RAREG.averbar(primeiro, rid, agora=db.now(),
                          teor="Averbação lavrada pelo outro balcão.")
            t, resposta = self._segundo_balcao(
                db, lambda c: MIN.voltar_do_ato(
                    c, ultimo, agora=db.now(),
                    motivo="Volta para ser selado de novo."))
            self._esperar(t, primeiro)
            self.assertIsInstance(
                resposta.get("erro"), MIN.MinutaError,
                "o AV-2 saiu do livro com o AV-3 lavrado depois dele")
            self.assertIn("não é o último", str(resposta["erro"]))
            with db.connect() as con:
                numeros = [a["numero"] for a in
                           CORR.numeracao_dos_atos(con, rid)]
            self.assertEqual(numeros, [1, 2, 3])

    def test_voltar_do_ato_trava_com_a_mesma_chave_da_lavratura(self):
        import bd_nativo
        import ra_minuta as MIN
        chaves: list[str] = []
        travar = bd_nativo.Banco.travar

        def anotar(banco_, chave):
            chaves.append(chave)
            return travar(banco_, chave)

        with TemporaryDirectory() as td, \
                mock.patch.object(bd_nativo.Banco, "travar", anotar):
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid, 1)
            chaves.clear()
            with db.transaction() as con:
                MIN.voltar_do_ato(con, ato_id, agora=db.now(),
                                  motivo="Volta para ser selado de novo.")
            self.assertIn(f"ra_atos.numero:{rid}", chaves)

    @unittest.skipUnless(banco_pg.ativo(), "sem a ponte: só no PostgreSQL")
    def test_voltar_do_ato_nao_apaga_o_selo_gravado_pelo_outro_balcao(self):
        """O selo chega no meio: sem o FOR UPDATE no ato, o DELETE esperava a
        linha e apagava o ato selado — selo pago e órfão."""
        import bd_nativo
        import ra_minuta as MIN
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid, 1)
            um = self._sem_a_ponte(db)
            bd_nativo.banco(um).escrever(
                "UPDATE ra_atos SET selo=%s WHERE id=%s",
                ("SELO-DE-EXEMPLO-0001", ato_id))
            resposta = self._segundo_balcao_sem_a_ponte(
                db, um, lambda c: MIN.voltar_do_ato(
                    c, ato_id, agora=db.now(),
                    motivo="Volta para ser selado de novo."))
            self.assertIsInstance(resposta.get("erro"), MIN.MinutaError,
                                  "o ato selado saiu do livro")
            self.assertIn("tem selo", str(resposta["erro"]))
            with db.connect() as con:
                linha = con.execute("SELECT selo FROM ra_atos WHERE id=?",
                                    (ato_id,)).fetchone()
                minutas = MIN.listar(con, rid, situacao=None)
            self.assertIsNotNone(linha, "o ato selado foi apagado")
            self.assertEqual(minutas, [])

    @unittest.skipUnless(banco_pg.ativo(), "sem a ponte: só no PostgreSQL")
    def test_a_minuta_lavrada_pelo_outro_balcao_nao_se_descarta_nem_se_revisa(
            self):
        """O primeiro lavrou a minuta e ainda não confirmou; o segundo chega
        para descartá-la, revisá-la ou lavrá-la de novo. Sem o FOR UPDATE, ele
        passava pela conferência e gravava por cima de LAVRADA."""
        import ra_minuta as MIN
        teor = "Averbação de exemplo, escrita para ir ao livro."
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            segundos = {
                "descartar": lambda c, mid, outro: MIN.descartar(
                    c, mid, motivo="Saiu em dobro na fila.", agora=db.now()),
                "revisar": lambda c, mid, outro: MIN.atualizar(
                    c, mid, teor=teor + " Revisada no outro balcão.",
                    agora=db.now()),
                "lavrar de novo": lambda c, mid, outro: MIN.marcar_lavrada(
                    c, mid, ato_id=outro, agora=db.now()),
            }
            for n, (nome, segundo) in enumerate(segundos.items()):
                with self.subTest(nome):
                    ato_id = self._ato(db, rid, 2 * n + 1)
                    outro = self._ato(db, rid, 2 * n + 2)
                    with db.transaction() as con:
                        mid = MIN.criar(con, registro_id=rid, tipo="AV",
                                        teor=teor, agora=db.now())
                    um = self._sem_a_ponte(db)
                    MIN.marcar_lavrada(um, mid, ato_id=ato_id, agora=db.now())
                    resposta = self._segundo_balcao_sem_a_ponte(
                        db, um, lambda c: segundo(c, mid, outro))
                    self.assertIsInstance(
                        resposta.get("erro"), MIN.MinutaError,
                        f"{nome}: passou pela conferência com a minuta de antes")
                    with db.connect() as con:
                        m = MIN.uma(con, mid)
                    self.assertEqual(
                        (m["situacao"], m["ato_id"], m["teor"]),
                        (MIN.LAVRADA, ato_id, teor))


if __name__ == "__main__":
    unittest.main()

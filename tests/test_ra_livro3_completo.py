"""O Livro 3 terminado — ata de ocorrência, «como ficará», conferência e
digitalização.

    «termine o desenvolvimento do livro 3, falta várias coisas que temos no
     livro 2»
    «digitalizacao de imagens deve ter igual ao livro 2»
                                        — o oficial, 21/09/2026

O QUE ESTES TESTES GUARDAM:

  1. **a ata nasce na mesma transação do desfazer** — ata sem ato desfeito, e
     ato desfeito sem ata, são os dois jeitos de isto dar errado;
  2. **a ata guarda o teor inteiro** — é a única cópia do que saiu do livro;
  3. **o «como ficará» não grava nada** e mostra o número que o ato *teria*;
  4. **a conferência guarda quem e quando**, e desmarcar não apaga o carimbo;
  5. **a digitalização usa as regras do Livro 2** e manda o arquivo anterior
     para o histórico — e **não marca nada de ONR**, porque o índice do país é
     de imóvel e este livro registra título de crédito.
"""
from __future__ import annotations

import io
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ra_correcoes as CORR
import ra_digitalizacao as DIGI
import ra_expurgo as EXP
import ra_minuta as MIN

SENHA = "Senha#12345"
TEOR = ("AV-01/1.243 - CANCELAMENTO INTEGRAL DO REGISTRO, à vista do "
        "instrumento de baixa expedido pelo credor.")


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class LivroTresCompletoTests(unittest.TestCase):

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _registro(self, db, numero=1243):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_registros(numero, livro, natureza, situacao,
                                            teor, criado_em)
                   VALUES (?,'3','CEDULA_CREDITO_RURAL','ATIVO',?,?)""",
                (numero, "REGISTRO: Nº 1243. Cédula rural hipotecária.",
                 db.now()))
            return con.execute("SELECT id FROM ra_registros WHERE numero=?",
                               (numero,)).fetchone()[0]

    def _ato(self, db, registro_id, numero=1):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                       teor, criado_em)
                   VALUES (?,'AV',?,?,?,?)""",
                (registro_id, numero, "2026-09-20", TEOR, db.now()))
            return con.execute(
                "SELECT id FROM ra_atos WHERE registro_id=? AND numero=?",
                (registro_id, numero)).fetchone()[0]

    def _entrar(self, app, db):
        db.create_user("admin", "Administrador", SENHA, "ADMIN")
        cliente = app.test_client()
        entrada = cliente.get("/login").get_data(as_text=True)
        cliente.post("/login", data={"username": "admin", "password": SENHA,
                                     "csrf_token": csrf(entrada)},
                     follow_redirects=True)
        return cliente

    # ------------------------------------------------- a ata de ocorrência

    def test_a_ata_nasce_com_o_desfazer_e_guarda_o_teor_inteiro(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid)
            with db.transaction() as con:
                r = MIN.voltar_do_ato(con, ato_id, agora=db.now(),
                                      usuario="Mario",
                                      motivo="o teor precisa ser reescrito")
            with db.connect() as con:
                atas = EXP.listar(con, rid)
            self.assertEqual(len(atas), 1)
            ata = atas[0]
            self.assertEqual(ata["id"], r["expurgo_id"])
            self.assertEqual(ata["ato_rotulo"], "AV-1")
            self.assertIn("CANCELAMENTO INTEGRAL", ata["ato_teor"])
            # o texto da ata diz o que aconteceu, e leva o teor dentro
            self.assertIn("ATA DE OCORRÊNCIA", ata["ata"])
            self.assertIn("CANCELAMENTO INTEGRAL", ata["ata"])
            self.assertIn("o teor precisa ser reescrito", ata["ata"])
            self.assertIn("Mario", ata["ata"])

    def test_ato_que_nao_volta_nao_deixa_ata(self):
        """Ata sem ato desfeito é o outro jeito de isto dar errado."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid)
            with db.transaction() as con:
                con.execute("UPDATE ra_atos SET selo=? WHERE id=?",
                            ("SELO-QUE-JA-SAIU", ato_id))
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.voltar_do_ato(con, ato_id, agora=db.now())
            with db.connect() as con:
                self.assertEqual(EXP.listar(con, rid), [])

    def test_a_ata_sai_em_odt(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid)
            with db.transaction() as con:
                r = MIN.voltar_do_ato(con, ato_id, agora=db.now(),
                                      motivo="desfeito para teste")
            cliente = self._entrar(app, db)
            resposta = cliente.get(f"/livro3/expurgo/{r['expurgo_id']}/ata.odt")
            self.assertEqual(resposta.status_code, 200)
            self.assertIn("opendocument", resposta.headers["Content-Type"])
            self.assertGreater(len(resposta.data), 500)

    # ------------------------------------------------------ o «como ficará»

    def test_o_como_ficara_nao_grava_nada_e_mostra_o_numero_que_teria(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            self._ato(db, rid, 1)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=rid, tipo="AV", teor=TEOR,
                                agora=db.now())
            with db.connect() as con:
                visao = MIN.como_ficara(con, rid, mid)
            self.assertEqual(visao["numero_previsto"], 2,
                             "depois do AV-1 vem o 2 — numeração contínua")
            self.assertEqual(visao["minuta"]["rotulo"], "AV-2")
            self.assertIn("NÃO LAVRADO", visao["minuta"]["marca"].upper())

            cliente = self._entrar(app, db)
            html = cliente.get(
                f"/livro3/{rid}/como-ficara/{mid}").get_data(as_text=True)
            self.assertIn("AV-2", html)
            self.assertGreaterEqual(html.count(MIN.MARCA), 3,
                                    "a marca aparece em três lugares")
            with db.connect() as con:
                atos = con.execute(
                    "SELECT COUNT(*) FROM ra_atos WHERE registro_id=?",
                    (rid,)).fetchone()[0]
            self.assertEqual(atos, 1, "a pré-visualização não lavra nada")

    def test_a_minuta_de_outro_registro_nao_entra_na_previsao(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            um, outro = self._registro(db, 1243), self._registro(db, 1198)
            with db.transaction() as con:
                mid = MIN.criar(con, registro_id=outro, tipo="AV", teor=TEOR,
                                agora=db.now())
            with db.connect() as con, self.assertRaises(MIN.MinutaError):
                MIN.como_ficara(con, um, mid)

    # -------------------------------------------------------- a conferência

    def test_conferir_guarda_quem_e_quando_e_desmarcar_nao_apaga_o_carimbo(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                CORR.conferir(con, rid, conferido=True, agora="2026-09-21T10:00",
                              usuario="Mario", nota="Data conferida no papel.")
            with db.connect() as con:
                r = con.execute(
                    "SELECT conferido, conferido_em, conferido_por, "
                    "conferido_nota FROM ra_registros WHERE id=?",
                    (rid,)).fetchone()
            self.assertEqual(r["conferido"], 1)
            self.assertEqual(r["conferido_por"], "Mario")
            self.assertIn("Data conferida", r["conferido_nota"])

            with db.transaction() as con:
                CORR.conferir(con, rid, conferido=False, agora="2026-09-22T10:00")
            with db.connect() as con:
                r = con.execute(
                    "SELECT conferido, conferido_em, conferido_por "
                    "FROM ra_registros WHERE id=?", (rid,)).fetchone()
            self.assertEqual(r["conferido"], 0)
            self.assertEqual(r["conferido_por"], "Mario",
                             "quem leu naquele dia leu — é fato do passado")

    def test_a_fila_do_que_falta_conferir(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            html = cliente.get("/livro3/conferir").get_data(as_text=True)
            self.assertIn("1243", html)
            with db.transaction() as con:
                CORR.conferir(con, rid, conferido=True, agora=db.now())
            html = cliente.get("/livro3/conferir").get_data(as_text=True)
            self.assertIn("foram conferidos", html)

    def test_a_tela_de_conferir_abre_e_marca(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}/conferir").get_data(as_text=True)
            self.assertIn("O que está escrito", tela)
            self.assertIn("Nenhum arquivo enviado", tela)
            cliente.post(f"/livro3/{rid}/conferir",
                         data={"csrf_token": csrf(tela), "conferido": "1",
                               "nota": "Conferido contra o livro de papel."},
                         follow_redirects=True)
            with db.connect() as con:
                self.assertEqual(
                    con.execute("SELECT conferido FROM ra_registros WHERE id=?",
                                (rid,)).fetchone()[0], 1)

    # ------------------------------------------------------ a digitalização

    def test_a_digitalizacao_usa_as_regras_do_livro_2(self):
        """Extensões, hash e nome seguro são lidos de lá — não reescritos."""
        import ri_digitalizacao as RD
        self.assertIs(DIGI.EXTENSOES_OK, RD.EXTENSOES_OK)
        self.assertIs(DIGI.hash_file, RD.hash_file)
        self.assertIs(DIGI.miniatura_png, RD.miniatura_png)

    def test_o_formato_fora_da_lista_e_recusado(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}/conferir").get_data(as_text=True)
            r = cliente.post(
                f"/livro3/{rid}/digitalizacao",
                data={"csrf_token": csrf(tela),
                      "arquivo": (io.BytesIO(b"nao e um pdf"), "varredura.exe")},
                content_type="multipart/form-data", follow_redirects=True)
            self.assertIn("Formato não aceito", r.get_data(as_text=True))

    def test_a_varredura_sobe_e_a_anterior_vai_ao_historico(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}/conferir").get_data(as_text=True)

            cliente.post(f"/livro3/{rid}/digitalizacao",
                         data={"csrf_token": csrf(tela),
                               "arquivo": (io.BytesIO(b"%PDF-1.4 primeira"),
                                           "registro-1243.pdf")},
                         content_type="multipart/form-data",
                         follow_redirects=True)
            with db.connect() as con:
                primeira = DIGI.atual(con, rid)
            self.assertIsNotNone(primeira)
            self.assertEqual(primeira["digi_nome"], "registro-1243.pdf")
            self.assertTrue(Path(primeira["digi_path"]).is_file())

            # a segunda varredura empurra a primeira para o histórico
            cliente.post(f"/livro3/{rid}/digitalizacao",
                         data={"csrf_token": csrf(tela),
                               "arquivo": (io.BytesIO(b"%PDF-1.4 segunda"),
                                           "registro-1243-v2.pdf")},
                         content_type="multipart/form-data",
                         follow_redirects=True)
            with db.connect() as con:
                segunda = DIGI.atual(con, rid)
            self.assertEqual(segunda["digi_nome"], "registro-1243-v2.pdf")
            self.assertNotEqual(segunda["digi_sha256"], primeira["digi_sha256"])
            historico = Path(segunda["digi_path"]).parent / "historico"
            self.assertTrue(any(historico.iterdir()),
                            "a varredura anterior não some")

            # e o arquivo se baixa e se vê
            r = cliente.get(f"/livro3/{rid}/digitalizacao/arquivo")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"segunda", r.data)
            self.assertIn("attachment", r.headers["Content-Disposition"])
            r = cliente.get(
                f"/livro3/{rid}/digitalizacao/arquivo?visualizar=1")
            self.assertIn("inline", r.headers["Content-Disposition"])
            self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")

    def test_a_pasta_do_livro_3_nao_e_a_do_livro_2(self):
        """Os números dos dois livros se cruzam — há matrícula 1.243 e
        registro 1.243."""
        from pathlib import Path as P
        caminho = DIGI.pasta_do_registro(P("/raiz"), 1243)
        self.assertIn("livro3", str(caminho))
        self.assertIn("registro-1243", str(caminho))


if __name__ == "__main__":
    unittest.main()


class FichaEmPapelDoLivroTresTests(unittest.TestCase):
    """A ficha impressa do Livro 3 — o último item da fila."""

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _entrar(self, app, db):
        db.create_user("admin", "Administrador", SENHA, "ADMIN")
        cliente = app.test_client()
        entrada = cliente.get("/login").get_data(as_text=True)
        cliente.post("/login", data={"username": "admin", "password": SENHA,
                                     "csrf_token": csrf(entrada)},
                     follow_redirects=True)
        return cliente

    def test_o_modelo_esta_no_catalogo_da_casa(self):
        """Relato #28: o oficial edita o papel sem esperar versão nova."""
        import modelos_da_casa as M
        chaves = [c["chave"] for c in M.CATALOGO]
        self.assertIn("RI_LIVRO3_FICHA", chaves)
        entrada = next(c for c in M.CATALOGO if c["chave"] == "RI_LIVRO3_FICHA")
        self.assertEqual(entrada["formato"], "CHAVES")
        # e o padrão aponta para coisa que existe — a régua do catálogo
        modulo, constante = entrada["padrao"]
        import importlib
        self.assertTrue(getattr(importlib.import_module(modulo), constante))

    def test_a_ficha_sai_em_odt_e_nao_se_parece_com_certidao(self):
        import io
        import zipfile

        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ra_registros(numero, livro, natureza,
                                                situacao, teor, criado_em)
                       VALUES (1243,'3','CEDULA_CREDITO_RURAL','ATIVO',?,?)""",
                    ("Cédula rural hipotecária nº 40/01390-1.", db.now()))
                rid = con.execute(
                    "SELECT id FROM ra_registros WHERE numero=1243").fetchone()[0]
            cliente = self._entrar(app, db)
            r = cliente.get(f"/livro3/{rid}/ficha.odt")
            self.assertEqual(r.status_code, 200)
            self.assertIn("opendocument", r.headers["Content-Type"])
            self.assertIn("livro3-1243.odt", r.headers["Content-Disposition"])
            self.assertGreater(len(r.data), 500)
            with zipfile.ZipFile(io.BytesIO(r.data)) as z:
                styles = z.read("styles.xml").decode("utf-8")
            self.assertIn("REGISTRO DE IMÓVEIS", styles)
            self.assertIn("REGISTRO AUXILIAR", styles)
            self.assertIn("1243", styles)

    def test_o_texto_da_ficha_diz_que_nao_e_certidao(self):
        """Papel que se pareça com certidão sem ser uma é o pior papel.

        O «Dou fé» do fecho de CADA ATO (LH13, «15 a») não mora no modelo:
        entra pelo claro `{atos}`, com quem praticou o ato — é o que o livro
        diz do ato, como na ficha do Livro 2, e não uma afirmação da ficha."""
        import ra_ficha_odt as F
        self.assertIn("não é certidão", F.MODELO_FICHA_LIVRO3_PADRAO)
        for proibido in ("confere com o original", "dou fé", "CERTIFICO"):
            self.assertNotIn(proibido, F.MODELO_FICHA_LIVRO3_PADRAO)

    def test_claro_sem_dado_sai_como_traco_e_nao_em_branco(self):
        """Branco no papel se lê como «o registro não diz»."""
        import ra_ficha_odt as F
        claros = F.contexto(registro={"numero": 1243}, atos=[], partes=[],
                            serventia={}, impresso_em="2026-09-21")
        self.assertEqual(claros["titulo_numero"], "—")
        self.assertEqual(claros["valor"], "—")
        self.assertIn("nenhuma parte informada", claros["partes"])
        self.assertIn("nenhum ato lavrado", claros["atos"])
        # e o modelo preenche sem estourar
        self.assertIn("1243", F.MODELO_FICHA_LIVRO3_PADRAO.format(**claros))

    # ---- revisão do L013 (PostgreSQL nativo)

    def test_etiqueta_do_selo_le_o_banco_so_para_ler(self):
        """`_textos_selo` abria o banco em `mode=ro`. A troca para a porta do
        banco o deixara gravável; o `mode=ro` chega ao PostgreSQL e o próprio
        servidor recusa a escrita."""
        import os
        import sqlite3
        from unittest import mock

        import banco_pg
        if not banco_pg.ativo():
            self.skipTest("módulo nativo: só lê com o PostgreSQL ligado (CG_PG_DSN)")
        from bd_nativo import banco
        import ra_ficha_odt as F

        with TemporaryDirectory() as td:
            _app, db = self._casa(td)
            with db.transaction() as con:
                con.execute(
                    "INSERT INTO sd_selos(numero, texto, obtido_em) VALUES (?,?,?)",
                    ("TESTE-L013R-0001", "Etiqueta de teste L013R", db.now()))
            abertos = []
            conectar = banco_pg.conectar

            def espiao(caminho, **kw):
                abertos.append((caminho, kw))
                return conectar(caminho, **kw)

            with mock.patch.dict(os.environ, {"CARTORIO_GESTAO_DATA": td}), \
                    mock.patch.object(banco_pg, "conectar", espiao):
                textos = F._textos_selo(["TESTE-L013R-0001", "TESTE-L013R-0002"])
            self.assertEqual(textos, {"TESTE-L013R-0001": "Etiqueta de teste L013R",
                                      "TESTE-L013R-0002": "TESTE-L013R-0002"})
            self.assertEqual(len(abertos), 1)
            caminho, kw = abertos[0]
            con = conectar(caminho, **kw)
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                    banco(con).escrever(
                        "INSERT INTO settings (key, value) VALUES (%s, %s)",
                        ("chave_de_teste_l013r", "x"))
            finally:
                con.close()

    def test_etiqueta_do_selo_sem_banco_nao_cria_arquivo_vazio(self):
        """Sem o arquivo, a função devolvia o número sem tocar em nada. Com a
        porta do banco sem `mode=ro` e o PostgreSQL desligado, o `sqlite3`
        puro criava um `cartorio_gestao.sqlite3` vazio na pasta de dados."""
        import os
        from unittest import mock

        import banco_pg
        import ra_ficha_odt as F

        with TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {"CARTORIO_GESTAO_DATA": td}), \
                mock.patch.object(banco_pg, "ativo", lambda: False):
            self.assertEqual(F._textos_selo(["TESTE-L013R-0001"]),
                             {"TESTE-L013R-0001": "TESTE-L013R-0001"})
            self.assertFalse((Path(td) / "cartorio_gestao.sqlite3").exists())


class CertidaoDoLivroTresTests(unittest.TestCase):
    """As balizas da certidão — 21/09/2026, «mesmas balizas para emissão de
    certidão» e «teor do registro principal, falta coisa»."""

    def test_a_certidao_traz_as_averbacoes(self):
        """ATÉ 21/09/2026 ELA AS OMITIA, e a tela oferecia escolhê-las.

        Uma certidão do registro 1.243 sairia reproduzindo a cédula **sem
        dizer que ela foi integralmente cancelada** pela AV-01. Quem a lesse
        concluiria que a garantia está de pé.
        """
        import atrib_certidao as AC
        dados = {
            "registro": {"numero": 1243, "teor": "Cédula rural hipotecária."},
            "atos": [
                {"id": 1, "tipo": "R", "numero": 1, "teor": "corpo do registro"},
                {"id": 2, "tipo": "AV", "numero": 1, "data_ato": "2026-09-20",
                 "teor": "CANCELAMENTO INTEGRAL DO REGISTRO."},
            ]}
        teor = AC.montar_teor("LIVRO3", dados)
        self.assertIn("Cédula rural hipotecária", teor)
        self.assertIn("CANCELAMENTO INTEGRAL", teor)
        self.assertIn("AV-1", teor)
        self.assertIn("20/09/2026", teor, "a data sai como a casa escreve")
        self.assertNotIn("corpo do registro", teor,
                         "o ato de registro não se repete — o teor já é ele")

    def test_sem_marcacao_entram_todas_as_averbacoes(self):
        """Certidão que cala uma averbação por omissão de clique é o mesmo
        defeito que ela veio consertar."""
        import atrib_certidao as AC
        dados = {"registro": {"numero": 1, "teor": "t"},
                 "atos": [{"id": 9, "tipo": "AV", "numero": 1, "teor": "uma"},
                          {"id": 10, "tipo": "AV", "numero": 2, "teor": "outra"}]}
        teor = AC.montar_teor("LIVRO3", dados)
        self.assertIn("uma", teor)
        self.assertIn("outra", teor)
        so_uma = AC.montar_teor("LIVRO3", dados, ato_ids=[9])
        self.assertIn("uma", so_uma)
        self.assertNotIn("outra", so_uma)

    def test_averbacao_sem_teor_nao_vira_linha_em_branco(self):
        import atrib_certidao as AC
        dados = {"registro": {"numero": 1, "teor": "t"},
                 "atos": [{"id": 9, "tipo": "AV", "numero": 1, "teor": ""},
                          {"id": 10, "tipo": "AV", "numero": 2,
                           "motivo_cancelamento": "liquidação integral"}]}
        teor = AC.montar_teor("LIVRO3", dados)
        self.assertNotIn("AV-1", teor, "rótulo sozinho não certifica nada")
        self.assertIn("liquidação integral", teor,
                      "o cancelamento escreve o motivo, e ele vale como teor")

    def test_o_modelo_ajustado_sem_o_claro_novo_continua_valendo(self):
        """O claro é aditivo: quem já ajustou o modelo não perde o texto."""
        import atrib_certidao as AC
        dados = {"registro": {"numero": 7, "teor": "meu teor"},
                 "atos": [{"id": 1, "tipo": "AV", "numero": 1, "teor": "av"}]}
        antigo = "Certifico o registro {numero}: {teor}"
        self.assertEqual(AC.montar_teor("LIVRO3", dados, modelo=antigo),
                         "Certifico o registro 7: meu teor")

    def test_a_validade_e_de_trinta_dias_e_sai_da_norma(self):
        """Art. 53 do Código de Normas — o Livro 2 já gravava, aqui faltava."""
        import atrib_certidao as AC
        from ri_schema import VALIDADE_CERTIDAO_DIAS
        self.assertEqual(VALIDADE_CERTIDAO_DIAS, 30)
        self.assertEqual(AC.validade_de("2026-09-21"), "2026-10-21")
        self.assertEqual(AC.validade_de("data ruim"), "",
                         "data que não se entende não vira prazo inventado")

    def test_a_emissao_grava_validade_documento_e_quem_assinou(self):
        with TemporaryDirectory() as td:
            from app import create_app
            app = create_app({"TESTING": True, "DATA_DIR": td})
            app.extensions["backup_checked"] = True
            db = app.extensions["db"]
            import atrib_certidao as AC
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ra_registros(numero, livro, natureza,
                                                situacao, teor, criado_em)
                       VALUES (1243,'3','CEDULA','ATIVO','o teor',?)""",
                    (db.now(),))
                rid = con.execute(
                    "SELECT id FROM ra_registros WHERE numero=1243").fetchone()[0]
                r = AC.emitir(con, "LIVRO3", rid, hoje="2026-09-21",
                              agora="2026-09-21T10:00", requerente="FULANA",
                              requerente_documento="000.000.012-44",
                              usuario="mario", usuario_nome="MARIO EXEMPLO",
                              usuario_funcao="Oficial")
            with db.connect() as con:
                c = con.execute("SELECT * FROM at_certidoes WHERE id=?",
                                (r["certidao_id"],)).fetchone()
            self.assertEqual(c["validade_ate"], "2026-10-21")
            self.assertEqual(c["requerente_documento"], "00000001244",
                             "só os dígitos, como o resto da casa guarda")
            self.assertEqual(c["emitida_por_nome"], "MARIO EXEMPLO")
            self.assertEqual(c["emitida_por_funcao"], "Oficial")


class DigitalizacaoDoTermoTests(unittest.TestCase):
    """«precisa ter digitalizacao do termo» — 21/09/2026."""

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def test_a_pasta_do_termo_fica_dentro_da_do_registro(self):
        from pathlib import Path as P
        caminho = DIGI.pasta_do_ato(P("/raiz"), 58, 17)
        self.assertIn("registro-58", str(caminho))
        self.assertIn("termo-17", str(caminho))

    def test_o_papel_do_termo_nao_e_o_do_registro(self):
        """Duas coisas diferentes, e por isso duas colunas — guardar no mesmo
        lugar faria a segunda apagar a primeira."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ra_registros(numero, livro, natureza,
                                                situacao, criado_em)
                       VALUES (1243,'3','CEDULA','ATIVO',?)""", (db.now(),))
                rid = con.execute(
                    "SELECT id FROM ra_registros WHERE numero=1243").fetchone()[0]
                con.execute(
                    """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                           teor, criado_em)
                       VALUES (?,'AV',1,?,?,?)""",
                    (rid, "2026-09-20", TEOR, db.now()))
                ato_id = con.execute(
                    "SELECT id FROM ra_atos WHERE registro_id=?",
                    (rid,)).fetchone()[0]

            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("anexar o papel do termo", tela)

            cliente.post(f"/livro3/ato/{ato_id}/digitalizacao",
                         data={"csrf_token": csrf(tela),
                               "arquivo": (io.BytesIO(b"%PDF-1.4 baixa"),
                                           "instrumento-de-baixa.pdf")},
                         content_type="multipart/form-data",
                         follow_redirects=True)
            with db.connect() as con:
                do_termo = DIGI.atual_do_ato(con, ato_id)
                do_registro = DIGI.atual(con, rid)
            self.assertIsNotNone(do_termo)
            self.assertEqual(do_termo["digi_nome"], "instrumento-de-baixa.pdf")
            self.assertIsNone(do_registro,
                              "o papel do termo não é a varredura da ficha")

            r = cliente.get(f"/livro3/ato/{ato_id}/digitalizacao/arquivo")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"baixa", r.data)

    def test_a_ficha_oferece_a_varredura_do_registro_e_mostra_a_capa(self):
        """RELATO DO OFICIAL, 21/09/2026: «na 1243 não tem digitalização da
        ficha».

        A rota existia desde a 3.6.158 e **a única tela que a chamava era a de
        conferir** — um clique adiante, atrás de um botão que diz outra coisa.
        No Livro 2 o envio e a capa estão na própria ficha, e é ali que ele foi
        procurar. E `livro3_miniatura_digitalizacao` não tinha chamador nenhum:
        «função pronta que nenhuma tela chama», o defeito mais repetido desta
        casa.
        """
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ra_registros(numero, livro, natureza,
                                                situacao, criado_em)
                       VALUES (1243,'3','CEDULA','ATIVO',?)""", (db.now(),))
                rid = con.execute(
                    "SELECT id FROM ra_registros WHERE numero=1243").fetchone()[0]

            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)

            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn(f"/livro3/{rid}/digitalizacao", tela,
                          "o envio da varredura da ficha tem de estar NA ficha")
            self.assertIn("ainda não tem a varredura da ficha", tela)
            self.assertNotIn("/digitalizacao/miniatura", tela,
                             "capa de arquivo que não existe seria 404 na tela")

            cliente.post(f"/livro3/{rid}/digitalizacao",
                         data={"csrf_token": csrf(tela),
                               "arquivo": (io.BytesIO(b"%PDF-1.4 ficha"),
                                           "ficha-1243.pdf")},
                         content_type="multipart/form-data",
                         follow_redirects=True)

            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("ficha-1243.pdf", tela)
            self.assertIn(f"/livro3/{rid}/digitalizacao/miniatura", tela,
                          "a capa prova que é a ficha CERTA, e não só que "
                          "algo foi salvo")
            with db.connect() as con:
                self.assertIsNone(
                    DIGI.atual_do_ato(con, 0),
                    "a varredura da ficha não é o papel de termo nenhum")


def _png_minimo() -> bytes:
    """Uma folha varrida de mentira, do tamanho de um selo."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


class CertidaoPorReproducaoTests(unittest.TestCase):
    """A CERTIDÃO POR REPRODUÇÃO DA DIGITALIZAÇÃO — 21/09/2026.

    O Livro 2 emite a certidão de inteiro teor de dois modos: pelo **texto**
    do teor e por **reprodução** da varredura da ficha. O Livro 3 só tinha o
    primeiro — e **dois registros vieram do acervo SEM TEOR NENHUM**: o 1.315 e o 1.560, cédulas de crédito rural, com zero caractere no registro e no R-1 (medido em 21/09/2026). Para esses a certidão por texto é recusada — a cópia se tira do livro físico —, e a reprodução da varredura é o caminho que eles passam a ter.
    """

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _registro(self, db, numero=1243, teor="Cédula rural hipotecária."):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_registros(numero, livro, natureza, situacao,
                                            teor, criado_em)
                   VALUES (?,'3','CEDULA','ATIVO',?,?)""",
                (numero, teor, db.now()))
            return con.execute("SELECT id FROM ra_registros WHERE numero=?",
                               (numero,)).fetchone()[0]

    def _logar(self, app, db):
        db.create_user("admin", "Administrador", SENHA, "ADMIN")
        cliente = app.test_client()
        entrada = cliente.get("/login").get_data(as_text=True)
        cliente.post("/login", data={"username": "admin", "password": SENHA,
                                     "csrf_token": csrf(entrada)},
                     follow_redirects=True)
        return cliente

    # ------------------------------------------------------- as recusas

    def test_sem_varredura_a_reproducao_e_recusada_com_o_caminho_da_saida(self):
        """A recusa é no balcão, com o cliente na frente — e não uma certidão
        numerada que depois não se imprime."""
        import atrib_certidao as AC
        with TemporaryDirectory() as td:
            _app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                with self.assertRaises(AC.CertidaoError) as caso:
                    AC.emitir(con, "LIVRO3", rid, hoje="2026-09-21",
                              agora="2026-09-21T10:00",
                              fonte_corpo="DIGITALIZACAO")
            self.assertIn("Envie a varredura", str(caso.exception))

    def test_o_rcpj_rtd_nao_reproduz_e_a_recusa_diz_por_que(self):
        """SÓ O LIVRO 3 TEM VARREDURA DE FICHA. O RCPJ/RTD guarda o documento
        APRESENTADO, que é outra coisa — o papel que o cliente trouxe, e não a
        folha do livro desta casa."""
        import atrib_certidao as AC
        with TemporaryDirectory() as td:
            _app, db = self._casa(td)
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO rg_registros(atribuicao, serie, numero,
                                                volume, situacao, teor,
                                                criado_em)
                       VALUES (3,'PJ_A',7,'5','ATIVO','teor',?)""",
                    (db.now(),))
                gid = con.execute(
                    "SELECT id FROM rg_registros WHERE numero=7").fetchone()[0]
                with self.assertRaises(AC.CertidaoError) as caso:
                    AC.emitir(con, "RCPJ_RTD", gid, hoje="2026-09-21",
                              agora="2026-09-21T10:00",
                              fonte_corpo="DIGITALIZACAO",
                              digitalizacao={"path": "x", "sha256": "y",
                                             "paginas": 1})
            self.assertIn("Livro 3", str(caso.exception))

    def test_fonte_desconhecida_nao_vira_texto_calado(self):
        import atrib_certidao as AC
        with TemporaryDirectory() as td:
            _app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                with self.assertRaises(AC.CertidaoError):
                    AC.emitir(con, "LIVRO3", rid, hoje="2026-09-21",
                              agora="2026-09-21T10:00", fonte_corpo="IMAGEM")

    # ------------------------------------------------------- o teor gravado

    def test_o_teor_gravado_e_o_resumo_e_nao_o_texto_do_registro(self):
        """O PAPEL É A IMAGEM; ISTO É O QUE FICA NO BANCO.

        Gravar o texto do registro faria o banco afirmar um teor que a via
        impressa não traz.
        """
        import atrib_certidao as AC
        with TemporaryDirectory() as td:
            _app, db = self._casa(td)
            rid = self._registro(db)
            folha = Path(td) / "ficha.png"
            folha.write_bytes(_png_minimo())
            with db.transaction() as con:
                r = AC.emitir(con, "LIVRO3", rid, hoje="2026-09-21",
                              agora="2026-09-21T10:00",
                              fonte_corpo="DIGITALIZACAO",
                              digitalizacao={"path": str(folha),
                                             "sha256": "abc123",
                                             "paginas": 2})
            self.assertEqual(r["fonte"], "DIGITALIZACAO")
            self.assertIn("REPRODUÇÃO", r["teor"])
            self.assertIn("2 folha(s)", r["teor"])
            self.assertIn("abc123", r["teor"])
            self.assertNotIn("Cédula rural hipotecária", r["teor"])
            with db.connect() as con:
                linha = AC.certidao(con, r["certidao_id"])
            self.assertEqual(linha["fonte_corpo"], "DIGITALIZACAO")
            self.assertEqual(linha["digi_sha256"], "abc123")

    def test_o_registro_cancelado_continua_dizendo_que_foi(self):
        """A reprodução não pode calar o cancelamento — é a mesma regra da
        certidão por texto, e aqui ela pesa mais: quem lê a folha varrida vê a
        cédula de pé."""
        import atrib_certidao as AC
        with TemporaryDirectory() as td:
            _app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                con.execute("UPDATE ra_registros SET situacao='CANCELADO' "
                            "WHERE id=?", (rid,))
                r = AC.emitir(con, "LIVRO3", rid, hoje="2026-09-21",
                              agora="2026-09-21T10:00",
                              fonte_corpo="DIGITALIZACAO",
                              digitalizacao={"path": "x", "sha256": "s",
                                             "paginas": 1})
            self.assertIn("CANCELADO", r["teor"])

    # ------------------------------------------- o ciclo inteiro, pela tela

    def test_da_ficha_ao_papel_e_a_copia_congela(self):
        """O CICLO: varrer a ficha, emitir por reprodução, imprimir — e a
        cópia congelada, que é o que faz a via de hoje continuar sendo a de
        amanhã."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._logar(app, db)

            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("não há varredura neste registro", tela,
                          "opção que se pode escolher e que recusa depois faz "
                          "o balcão descobrir o buraco com o cliente na frente")

            cliente.post(f"/livro3/{rid}/digitalizacao",
                         data={"csrf_token": csrf(tela),
                               "arquivo": (io.BytesIO(_png_minimo()),
                                           "ficha-1243.png")},
                         content_type="multipart/form-data",
                         follow_redirects=True)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("Reprodução da digitalização da ficha", tela)
            self.assertNotIn("não há varredura neste registro", tela)
            #  AS FOLHAS SE INFORMAM — medido: **92 dos 667** envelopes de
            #  certidão do acervo cobraram mais de uma folha, e até doze; o
            #  sistema mandava uma, sempre.
            self.assertIn('name="folhas"', tela)
            self.assertIn("folha acrescida", tela)

            resposta = cliente.post(
                f"/atribuicoes/certidoes/LIVRO3/{rid}",
                data={"csrf_token": csrf(tela), "fonte_corpo": "DIGITALIZACAO",
                      "requerente": "FULANA"}, follow_redirects=True)
            self.assertEqual(resposta.status_code, 200)
            #  NESTE ENSAIO NÃO HÁ SELADOR, E POR ISSO A CERTIDÃO SAI
            #  CANCELADA — é a regra da casa desde sempre, e ela passou a
            #  valer aqui em 21/09/2026, quando a certidão do Livro 3 ganhou
            #  selo automático: selo que não sai suspende o ato.
            pagina = resposta.get_data(as_text=True)
            self.assertIn("o selo não saiu", pagina)
            self.assertIn("selador", pagina,
                          "a recusa diz a causa, para o balcão corrigir")

            with db.connect() as con:
                con.row_factory = __import__("sqlite3").Row
                c = con.execute("SELECT * FROM at_certidoes "
                                "ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(c, "a certidão tem de ter saído")
            self.assertEqual(c["fonte_corpo"], "DIGITALIZACAO")
            copia = Path(c["digi_path"])
            self.assertTrue(copia.is_file())
            self.assertIn("livro3", str(copia).replace("\\", "/"),
                          "a cópia mora na pasta do LIVRO 3 — `ri_certidoes` e "
                          "`at_certidoes` são tabelas com ids independentes, e "
                          "a pasta do Livro 2 é chaveada só pelo id")
            self.assertIn(f"certidoes/{c['id']}",
                          str(copia).replace("\\", "/"))
            with db.connect() as con:
                da_ficha = DIGI.atual(con, rid)
            self.assertNotEqual(copia, Path(da_ficha["digi_path"]),
                                "a certidão não pode apontar para o arquivo "
                                "que a ficha vai trocar amanhã")

            # VARRER A FICHA DE NOVO NÃO MUDA A CERTIDÃO QUE JÁ SAIU.
            cliente.post(f"/livro3/{rid}/digitalizacao",
                         data={"csrf_token": csrf(tela),
                               "arquivo": (io.BytesIO(_png_minimo()),
                                           "ficha-1243-v2.png")},
                         content_type="multipart/form-data",
                         follow_redirects=True)
            with db.connect() as con:
                c2 = con.execute("SELECT digi_path, digi_sha256 FROM "
                                 "at_certidoes WHERE id=?",
                                 (c["id"],)).fetchone()
            self.assertEqual(c2[0], c["digi_path"])
            self.assertEqual(c2[1], c["digi_sha256"])

            #  A CÓPIA JÁ ESTAVA CONGELADA ANTES DA RECUSA DO SELO — é por
            #  isso que ela existe acima. Para medir o PAPEL, desfaz-se aqui a
            #  marca de cancelada que a falta de selador pôs: o que se testa
            #  desta linha em diante é a impressão da reprodução.
            with db.transaction() as con:
                con.execute("UPDATE at_certidoes SET cancelada=0, "
                            "motivo_cancelamento=NULL WHERE id=?", (c["id"],))
            papel = cliente.get(
                f"/atribuicoes/certidoes/{c['id']}/odt?formato=odt")
            self.assertEqual(papel.status_code, 200)
            self.assertEqual(papel.data[:2], b"PK",
                             "o papel da reprodução é o .odt com as folhas")
            import zipfile
            with zipfile.ZipFile(io.BytesIO(papel.data)) as pacote:
                xml = pacote.read("content.xml").decode("utf-8")
            self.assertIn("Pictures/", str(pacote_nomes(papel.data)),
                          "a folha varrida tem de estar dentro do papel")
            #  SEM SELO NAO HA CARIMBO — e certo: esta certidao do ensaio nao
            #  foi selada. O que NAO pode faltar e QUEM EXPEDIU: sem o nome o
            #  papel terminaria na ultima folha do livro, sem ninguem embaixo.
            #  E O TRACO DA CANETA NAO SAI — ordem de 22/09/2026 («so na
            #  ficha»), com o nome e o titulo sem as linhas em branco desde
            #  23/09, igual ao Livro 2. Este teste cobrava o traço até 23/09.
            self.assertNotIn("________", xml)
            #  MODELO DA CASA — 20/10/2026: o nome sai numa linha só com a
            #  qualificação («Nome — Função»), no estilo do fecho do modelo.
            self.assertIn('<text:p text:style-name="P-repro-fecho-assina">'
                          'Administrador', xml)
            #  E O PAPEL DIZ O QUE REPRODUZ (LH02): o registro e o livro, da
            #  certidão; o cabeçalho, do cadastro fictício da serventia.
            self.assertIn("Registro nº 1243 do Livro nº 3 – Registro "
                          "Auxiliar, em 1 (uma) página.", xml)
            self.assertIn("Mario Exemplo dos Santos — Tabelião e Registrador "
                          "Oficial", xml)
            self.assertNotIn('<text:p text:style-name="P-just"/>'
                             '<text:p text:style-name="P-just"/>', xml)
            self.assertNotIn("SELO DA CERTID", xml)

    def test_a_reproducao_cancelada_nao_se_reimprime(self):
        """CERTIDÃO CANCELADA NÃO SAI POR REPRODUÇÃO.

        A certidão por texto sai com «CERTIDÃO CANCELADA» escrito no alto;
        esta é composta das folhas varridas, e não há onde carimbar sem
        escrever por cima do livro. Na mão de quem a recebe, uma reprodução
        cancelada é indistinguível de uma válida.
        """
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._logar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            cliente.post(f"/livro3/{rid}/digitalizacao",
                         data={"csrf_token": csrf(tela),
                               "arquivo": (io.BytesIO(_png_minimo()),
                                           "ficha.png")},
                         content_type="multipart/form-data",
                         follow_redirects=True)
            cliente.post(f"/atribuicoes/certidoes/LIVRO3/{rid}",
                         data={"csrf_token": csrf(tela),
                               "fonte_corpo": "DIGITALIZACAO"},
                         follow_redirects=True)
            with db.connect() as con:
                cid = con.execute("SELECT id FROM at_certidoes "
                                  "ORDER BY id DESC LIMIT 1").fetchone()[0]
            with db.transaction() as con:
                con.execute("UPDATE at_certidoes SET cancelada=1, "
                            "motivo_cancelamento='erro material' WHERE id=?",
                            (cid,))
            r = cliente.get(f"/atribuicoes/certidoes/{cid}/odt?formato=odt",
                            follow_redirects=True)
            self.assertNotEqual(r.data[:2], b"PK",
                                "reprodução cancelada não vira papel")
            self.assertIn("CANCELADA", r.get_data(as_text=True))
            self.assertIn("erro material", r.get_data(as_text=True))


class PapelDaCertidaoDoLivroTresTests(unittest.TestCase):
    """O PAPEL DA CERTIDÃO DO LIVRO 3 POR TEXTO, IGUAL AO DO LIVRO 2 — 23/09/2026.

        «emiti uma certidao de livro 3 e saiu dois selos»
        «e falta o selo na averbacao»
        «e falta cabecalho do cartorio na certidao. deixe igual a certidao
         equivalente do livro 2»                         — o oficial

    Medido na certidão 1/2026 (registro 1.243): os dois selos estão certos —
    certidão de duas folhas, 16.24.4 mais a folha acrescida 16.24.4.1 —; o que
    faltava era o papel. A AV-1 tinha selo no razão e saía sem ele, e o
    cabeçalho da casa era calado porque «REPÚBLICA FEDERATIVA» aparecia NO MEIO
    do teor, dentro da página do E-Ofício que o registro reproduz.

    TUDO SE DESENHA NA IMPRESSÃO: o teor congelado não muda uma letra, e por
    isso a certidão que já saiu ganha o cabeçalho e o selo sem mudar de hash.
    """

    TEOR_DO_REGISTRO = ("CERTIFICO que no registro consta:\n\n"
                        "REPÚBLICA FEDERATIVA DO BRASIL\n\nESTADO DO MARANHÃO\n"
                        "CEDULA RURAL HIPOTECÁRIA Nr 40/01390-1")
    SELO_DA_AV = "AVESVD0000002KP37IM7S7892Y90"

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _registro_com_averbacao(self, db):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_registros(numero, livro, natureza, situacao,
                                            teor, criado_em)
                   VALUES (1243,'3','CEDULA','ATIVO',?,?)""",
                (self.TEOR_DO_REGISTRO, db.now()))
            rid = con.execute("SELECT id FROM ra_registros WHERE numero=1243"
                              ).fetchone()[0]
            con.execute(
                """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                       teor, criado_em)
                   VALUES (?,'R',1,'2010-01-10',?,?)""",
                (rid, self.TEOR_DO_REGISTRO, db.now()))
            con.execute(
                """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                       teor, selo, criado_em)
                   VALUES (?,'AV',1,'2026-09-22',?,?,?)""",
                (rid, TEOR, self.SELO_DA_AV, db.now()))
            av = con.execute("SELECT id FROM ra_atos WHERE tipo='AV'"
                             ).fetchone()[0]
            con.execute(
                """INSERT INTO sd_selos(numero, texto, caminho, atribuicao,
                                        tabela, ato_id, obtido_em)
                   VALUES (?,?,'/selo/imovel/averbacao','IMOVEL','ra_atos',?,?)""",
                (self.SELO_DA_AV,
                 (f"SELO DIGITAL DO TJMA {self.SELO_DA_AV} Ato: 16.22.2 "
                  "Total R$ 134,43 Emol R$ 120,03 FERC R$ 3,60"),
                 av, db.now()))
        return rid

    def _emitir(self, db, rid):
        import atrib_certidao as AC
        with db.transaction() as con:
            r = AC.emitir(con, "LIVRO3", rid, hoje="2026-09-21",
                          agora="2026-09-21T10:00:00")
        return r

    def test_os_blocos_juntos_sao_o_teor_letra_por_letra(self):
        """O PAPEL PARTE O TEOR, E NÃO O REESCREVE. Se a junção dos trechos
        não for o teor inteiro, a impressão deixou de ser a cópia do que foi
        congelado — e o hash da certidão passaria a certificar outro texto."""
        import atrib_certidao as AC
        with TemporaryDirectory() as td:
            _app, db = self._casa(td)
            rid = self._registro_com_averbacao(db)
            r = self._emitir(db, rid)
            with db.connect() as con:
                con.row_factory = __import__("sqlite3").Row
                atos = [dict(x) for x in con.execute(
                    "SELECT * FROM ra_atos WHERE registro_id=?", (rid,))]
            blocos = AC.blocos_por_ato(r["teor"], atos)
        self.assertEqual("".join(t for t, _a in blocos), r["teor"])
        dos_atos = [a["tipo"] for _t, a in blocos if a]
        self.assertEqual(dos_atos, ["AV"],
                         "o R-1 é o teor do alto, e não ganha trecho próprio")
        trecho_da_av = next(t for t, a in blocos if a)
        self.assertTrue(trecho_da_av.startswith("AV-1"))
        self.assertIn("CANCELAMENTO INTEGRAL", trecho_da_av)

    def test_sem_rotulo_no_teor_nao_se_pendura_selo_no_lugar_errado(self):
        """O QUE NÃO SE ACHA NÃO SE INVENTA: certidão do acervo, montada por
        outro sistema, sai como sempre saiu — um bloco só, sem ato."""
        import atrib_certidao as AC
        blocos = AC.blocos_por_ato("texto antigo sem rótulo nenhum",
                                   [{"id": 9, "tipo": "AV", "numero": 1}])
        self.assertEqual(blocos, [("texto antigo sem rótulo nenhum", None)])

    def test_a_cauda_do_cancelado_nao_fica_com_o_ultimo_ato(self):
        import atrib_certidao as AC
        teor = ("registro\n\nAV-1 — 22/09/2026:-\ncancelado\n\n"
                "CERTIFICO ainda que o referido registro encontra-se CANCELADO.")
        blocos = AC.blocos_por_ato(teor, [{"id": 1, "tipo": "AV",
                                           "numero": 1}])
        self.assertEqual("".join(t for t, _a in blocos), teor)
        self.assertIsNone(blocos[-1][1])
        self.assertIn("CERTIFICO ainda", blocos[-1][0])
        self.assertNotIn("CERTIFICO ainda", blocos[1][0])

    def test_o_papel_tem_cabecalho_selo_da_averbacao_e_fecho(self):
        import zipfile
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.set_settings({"serventia_cnpj": "00.000.010/0001-27"})
            rid = self._registro_com_averbacao(db)
            r = self._emitir(db, rid)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            with db.connect() as con:
                hash_antes = con.execute(
                    "SELECT hash_certidao, teor FROM at_certidoes WHERE id=?",
                    (r["certidao_id"],)).fetchone()
            papel = cliente.get(
                f"/atribuicoes/certidoes/{r['certidao_id']}/odt?formato=odt")
            self.assertEqual(papel.status_code, 200)
            self.assertEqual(papel.data[:2], b"PK")
            with zipfile.ZipFile(io.BytesIO(papel.data)) as pacote:
                xml = pacote.read("content.xml").decode("utf-8")
                estilos = pacote.read("styles.xml").decode("utf-8")
            with db.connect() as con:
                hash_depois = con.execute(
                    "SELECT hash_certidao, teor FROM at_certidoes WHERE id=?",
                    (r["certidao_id"],)).fetchone()

        # O CABEÇALHO DA CASA NO CABEÇALHO DA PÁGINA, como no Livro 2 — e
        # mesmo com «REPÚBLICA FEDERATIVA» no meio do teor.
        self.assertIn("<style:header", estilos)
        self.assertIn("CNS", estilos)
        # O CABEÇALHO COMPLETO, e não o compacto — pedido 23/09/2026 («o
        # cabeçalho não está completo»), aprovado em imagem.
        cabecalho = estilos[estilos.index("<style:header"):]
        for trecho in ("REPÚBLICA FEDERATIVA DO BRASIL",
                       "ESTADO DO MARANHÃO", "COMARCA DE",
                       "SERVENTIA EXTRAJUDICIAL DO", "CNPJ", "Substituta"):
            self.assertIn(trecho, cabecalho, trecho)
        self.assertNotIn("Oficial: ", cabecalho)
        # O SELO DA AVERBAÇÃO LOGO ABAIXO DELA, e antes do fecho.
        self.assertIn(self.SELO_DA_AV, xml)
        pos_av = xml.index("CANCELAMENTO INTEGRAL")
        pos_selo = xml.index(self.SELO_DA_AV)
        pos_fecho = xml.index("Era o que nela continha.")
        self.assertLess(pos_av, pos_selo)
        self.assertLess(pos_selo, pos_fecho)
        # A DATA É A DA EMISSÃO, e não a de hoje.
        self.assertIn("Certidão emitida em 21 de setembro de 2026", xml)
        # a validade pelo art. 553 (LH13, «14 a»): o fecho se monta na
        # impressão, e a segunda via já sai com o artigo vigente
        self.assertIn("art. 553", xml)
        self.assertIn("CERTIDÃO DE INTEIRO TEOR n. 1/2026", xml)
        # E NADA DO QUE FOI CONGELADO MUDOU.
        self.assertEqual(tuple(hash_antes), tuple(hash_depois))


def pacote_nomes(dados: bytes) -> list:
    """Os nomes de dentro do .odt — para provar que a imagem entrou."""
    import zipfile
    with zipfile.ZipFile(io.BytesIO(dados)) as pacote:
        return pacote.namelist()

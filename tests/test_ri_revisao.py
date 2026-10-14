"""As notas de revisão do ato do RI — pedido do oficial em 15/09/2026.

    «Criar um campo (se nao houver) para notas de revisao no sistema a serem
     baixadas antes da lavratura.»

O que estes testes guardam, em ordem de importância:

  1. **a nota não trava nada** — varredura dos nomes públicos, como a do CNIB,
     a das fraudes e a do usucapião;
  2. **baixar exige escrever o que se decidiu** — sem isso a baixa apaga a
     pergunta sem respondê-la;
  3. **a nota não vai para a ficha errada** — ato de outra matrícula é
     recusado, porque ninguém desconfia de uma nota que aparece onde se
     esperava encontrar alguma;
  4. **a ficha mostra o que falta conferir**, que é onde quem sela olha.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ri_revisao as RV  # noqa: E402

SENHA = "Senha#12345"


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class NotaDeRevisaoTests(unittest.TestCase):

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        return app, app.extensions["db"]

    def _matricula(self, db, numero="777"):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ri_matriculas(numero, livro, tipo_ficha, criado_em)
                   VALUES (?,'2','ESTRUTURADA',?)""", (numero, db.now()))
            return con.execute(
                "SELECT id FROM ri_matriculas WHERE numero=?",
                (numero,)).fetchone()[0]

    # ------------------------------------------------ a regra que mais importa

    def test_o_modulo_nao_tem_funcao_que_recuse_ato(self):
        """A nota avisa; quem decide é quem assina.

        Quando a nota existe o ato JÁ está lavrado — travar seria desfazer
        ato, e desfazer ato é do delegatário. Mesma varredura do CNIB, das
        fraudes e do usucapião.
        """
        proibidos = ("recusar", "impedir", "travar", "bloquear", "cancelar",
                     "invalidar", "anular")
        publicos = [n for n in dir(RV) if not n.startswith("_")]
        for nome in publicos:
            for proibido in proibidos:
                self.assertNotIn(
                    proibido, nome.lower(),
                    f"`ri_revisao.{nome}` tem cara de recusar ato. A nota de "
                    f"revisão não decide nada — ela avisa.")

    def test_baixar_exige_escrever_o_que_se_decidiu(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            mid = self._matricula(db)
            with db.transaction() as con:
                nota = RV.anotar(
                    con, matricula_id=mid, assunto="Área retificada",
                    nota="A área cresceu 35%; conferir a anuência.",
                    agora=db.now())
            for vazio in ("", "   ", "ok", "conferi"):
                with db.transaction() as con:
                    with self.assertRaises(RV.RevisaoError):
                        RV.baixar(con, nota["id"], decisao=vazio,
                                  agora=db.now())
            with db.connect() as con:
                self.assertEqual(
                    len(RV.da_matricula(con, mid, so_abertas=True)), 1,
                    "a nota não podia ter sido baixada")

    def test_a_decisao_fica_escrita_e_a_nota_nao_some(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            mid = self._matricula(db)
            with db.transaction() as con:
                nota = RV.anotar(con, matricula_id=mid, assunto="Remanescente",
                                 nota="O remanescente não foi apurado.",
                                 agora=db.now())
            with db.transaction() as con:
                RV.baixar(con, nota["id"],
                          decisao="Apurado em 3.535,6623 ha e declarado na AV-05.",
                          agora=db.now())
            with db.connect() as con:
                linhas = RV.da_matricula(con, mid)
                self.assertEqual(len(linhas), 1, "a nota baixada não some")
                self.assertEqual(linhas[0]["situacao"], RV.BAIXADA)
                self.assertIn("3.535,6623", linhas[0]["baixa_decisao"])

    def test_nao_se_baixa_duas_vezes(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            mid = self._matricula(db)
            with db.transaction() as con:
                nota = RV.anotar(con, matricula_id=mid, assunto="Conferir",
                                 nota="Conferir o memorial com o confrontante.",
                                 agora=db.now())
            with db.transaction() as con:
                RV.baixar(con, nota["id"],
                          decisao="Conferido contra a certificação do SIGEF.",
                          agora=db.now())
            with db.transaction() as con:
                with self.assertRaises(RV.RevisaoError):
                    RV.baixar(con, nota["id"],
                              decisao="Conferido outra vez, por engano.",
                              agora=db.now())

    def test_a_nota_nao_cai_na_ficha_de_outro_imovel(self):
        """Ato de outra matrícula é recusado.

        Sem esta guarda, um id trocado penduraria a nota na ficha de outro
        imóvel — e ninguém desconfia de uma nota que aparece onde se
        esperava encontrar alguma.
        """
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            uma = self._matricula(db, "777")
            outra = self._matricula(db, "888")
            from ri_schema import hash_ato
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ri_atos(matricula_id, tipo, numero, data_ato,
                                           teor, teor_formato, cancelado, acervo,
                                           hash_ato, lavrado_em)
                       VALUES (?,'AV',1,'2026-09-15','teor qualquer','texto',0,0,?,?)""",
                    (outra, hash_ato("888", "AV", 1, "2026-09-15",
                                     "teor qualquer", None), db.now()))
                ato_da_outra = con.execute(
                    "SELECT id FROM ri_atos WHERE matricula_id=?",
                    (outra,)).fetchone()[0]
            with db.transaction() as con:
                with self.assertRaises(RV.RevisaoError):
                    RV.anotar(con, matricula_id=uma, ato_id=ato_da_outra,
                              assunto="Nota trocada",
                              nota="Esta nota é de outro imóvel.",
                              agora=db.now())

    def test_nota_sem_dizer_o_que_conferir_e_recusada(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            mid = self._matricula(db)
            with db.transaction() as con:
                with self.assertRaises(RV.RevisaoError):
                    RV.anotar(con, matricula_id=mid, assunto="X",
                              nota="Conferir isto aqui.", agora=db.now())
                with self.assertRaises(RV.RevisaoError):
                    RV.anotar(con, matricula_id=mid, assunto="Assunto bom",
                              nota="curto", agora=db.now())

    # ---------------------------------------------------------- pelas telas

    def test_a_ficha_mostra_o_que_falta_conferir_e_deixa_baixar(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            mid = self._matricula(db)
            with db.transaction() as con:
                RV.anotar(con, matricula_id=mid, assunto="Três partes de terra",
                          nota="A matrícula de origem descreve três partes em "
                               "condomínio; conferir antes de lavrar.",
                          agora=db.now(), origem="IMPORTACAO")

            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)

            html = cliente.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
            self.assertIn("Revisar antes de selar", html)
            self.assertIn("Três partes de terra", html)
            self.assertIn("impede lavrar ou selar", html,
                          "a ficha precisa dizer que a nota não trava")

            acao = re.search(
                r'action="(/registro-imoveis/revisoes/\d+/baixar)"', html).group(1)
            resposta = cliente.post(
                acao, data={"csrf_token": csrf(html[html.index(acao):]),
                            "decisao": "Conferido no livro: as três partes já "
                                       "estavam unificadas pela AV-02.",
                            "voltar": f"/registro-imoveis/{mid}"},
                follow_redirects=True)
            self.assertEqual(resposta.status_code, 200)
            # a SEÇÃO continua na ficha — é dela que sai o formulário de
            # anotar. O que some é a nota, e no lugar entra a frase que diz
            # que não há o que conferir.
            depois = resposta.get_data(as_text=True)
            self.assertNotIn("Três partes de terra", depois)
            self.assertIn("Nada esperando conferência nesta matrícula", depois)
            with db.connect() as con:
                self.assertEqual(len(RV.da_matricula(con, mid, so_abertas=True)), 0)

    def test_da_para_anotar_pela_ficha(self):
        """A rota de anotar tem tela — senão é função órfã, que é o defeito
        mais repetido deste projeto."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            mid = self._matricula(db)
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            html = cliente.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
            acao = f"/registro-imoveis/{mid}/revisoes"
            self.assertIn(acao, html, "a ficha precisa ter o formulário de anotar")

            resposta = cliente.post(
                acao, data={"csrf_token": csrf(html[html.index(acao):]),
                            "assunto": "Conferir o CCIR",
                            "nota": "O CCIR apresentado é do exercício anterior."},
                follow_redirects=True)
            self.assertEqual(resposta.status_code, 200)
            self.assertIn("Conferir o CCIR", resposta.get_data(as_text=True))
            with db.connect() as con:
                self.assertEqual(len(RV.da_matricula(con, mid, so_abertas=True)), 1)

    def test_a_tela_abre_em_instalacao_nova(self):
        """Regra da casa: instalação nova nasce funcionando."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            resposta = cliente.get("/registro-imoveis/revisoes")
            self.assertEqual(resposta.status_code, 200)
            self.assertIn("Nada esperando conferência",
                          resposta.get_data(as_text=True))

    def test_a_tela_abre_COM_nota_e_o_token_dela_baixa_a_nota(self):
        """A cena do relato #69 — e o buraco por onde aquele defeito passou.

        Em 16/09/2026 a tela `/registro-imoveis/revisoes` respondia HTTP 500
        com `TypeError: 'str' object is not callable`: o formulário de baixar
        escrevia `{{ csrf_token() }}`, e nesta casa `csrf_token` chega ao
        modelo como **valor**, não como a função global do Jinja.

        **Nenhum teste pegou, e o motivo é o que este teste guarda.** O
        formulário mora dentro da linha de cada nota, e o varredor da casa —
        `test_a_tela_abre_em_instalacao_nova`, logo acima — abre esta tela
        **sem nota nenhuma**. Com a lista vazia o `<form>` não é renderizado:
        o pedaço de papel que derrubava a página inteira **não chegava a
        existir**. A tela que quebrava ontem passa limpa hoje, e passa limpa
        pelo mesmo motivo que passou limpa na véspera.

        É a mesma lição do `SUM()` sobre zero linhas, do outro lado: lá o
        número vazio vira defeito na instalação nova; **aqui o número vazio
        esconde o defeito**. Tela que abre vazia prova que a tela abre vazia —
        e mais nada.

        Por isso este teste faz o caminho inteiro com o dado na frente: mede a
        tela vazia, põe a nota, e então confere que o valor do campo é o token
        **da sessão** (não um texto qualquer, que a rota recusaria) e baixa a
        nota com ele.
        """
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)

            # 1) a tela VAZIA — o estado em que o defeito do #69 se escondia.
            vazia = cliente.get("/registro-imoveis/revisoes")
            self.assertEqual(vazia.status_code, 200)
            corpo_vazio = vazia.get_data(as_text=True)
            self.assertIn("Nada esperando conferência", corpo_vazio)
            self.assertNotIn(
                "Baixar a nota", corpo_vazio,
                "a tela vazia não tem o formulário — é POR ISSO que o "
                "varredor de instalação nova passou por cima do relato #69")

            # 2) a mesma tela COM o dado que faz o formulário existir.
            mid = self._matricula(db)
            with db.transaction() as con:
                RV.anotar(con, matricula_id=mid, assunto="Área a conferir",
                          nota="Conferir a área com a certificação do SIGEF.",
                          agora=db.now())

            html = cliente.get(
                "/registro-imoveis/revisoes").get_data(as_text=True)
            self.assertIn("Área a conferir", html)
            self.assertIn("Baixar a nota", html)
            with cliente.session_transaction() as sessao:
                self.assertEqual(
                    csrf(html), sessao["csrf_token"],
                    "o campo tem de levar o token da SESSÃO; um valor "
                    "qualquer estoura na hora de montar a tela")

            acao = re.search(
                r'action="(/registro-imoveis/revisoes/\d+/baixar)"', html).group(1)
            resposta = cliente.post(
                acao,
                data={"csrf_token": csrf(html),
                      "decisao": "Área conferida com a certificação do SIGEF.",
                      "voltar": "/registro-imoveis/revisoes"},
                follow_redirects=True)
            self.assertEqual(resposta.status_code, 200,
                             "o token que a própria tela mandou tem de valer")
            with db.connect() as con:
                self.assertEqual(
                    len(RV.da_matricula(con, mid, so_abertas=True)), 0,
                    "a nota não foi baixada pela tela")


if __name__ == "__main__":
    unittest.main()

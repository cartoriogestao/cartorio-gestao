"""As partes do Livro 3, e o selo que não sai sem elas — 21/09/2026.

    «fui tentar selar o ato do 1243 e deu isso: O ato ficou SEM SELO: Os
     nomes das partes devem ser informados. nao tem campo para partes.
     resolva e coloque o ato em minutas para eu tentar selar novamente»
                                        — o oficial

O QUE ESTES TESTES GUARDAM:

  1. **sem partes o selo é recusado NO BALCÃO**, e não depois de uma viagem
     à rede — e eu havia escrito o contrário em comentário, em 20/09: «a
     lista vazia não impede o selo». Impede. Dedução contra medição do
     balcão: ganha o balcão;
  2. **há campo para partes**, que é o que faltava: a tabela existia desde
     que o livro nasceu e nenhuma tela escrevia nela;
  3. **os papéis são os da casa** — os três medidos nas 25 partes do acervo
     vêm primeiro;
  4. **o ato volta para a minuta com o que ele tinha dentro**, e as três
     recusas que protegem o livro.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ra_minuta as MIN
import ra_parte as PT
import ra_selo as RS

SENHA = "Senha#12345"
TEOR = ("AV-01/1.243 - CANCELAMENTO INTEGRAL DO REGISTRO, à vista do "
        "instrumento de baixa expedido pelo credor.")


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class PartesDoLivro3Tests(unittest.TestCase):

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
                                            condicoes, criado_em)
                   VALUES (?,'3','CEDULA_CREDITO_RURAL','ATIVO',?,?)""",
                (numero, "Emitente: FULANA DE EXEMPLO, CPF 000.000.000-00.",
                 db.now()))
            return con.execute("SELECT id FROM ra_registros WHERE numero=?",
                               (numero,)).fetchone()[0]

    def _ato(self, db, registro_id, numero=1, **campos):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                       teor, criado_em)
                   VALUES (?,'AV',?,?,?,?)""",
                (registro_id, numero, db.now(), TEOR, db.now()))
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

    # ------------------------------------------------ a que mais importa

    def test_sem_partes_o_selo_e_recusado_no_balcao(self):
        """A frase é do aparelho, e a recusa passou a ser antes da viagem."""
        falta = RS.falta_para_selar(natureza="BAIXA", codigo_tj="16.22.2",
                                    versao_tabela="0220260101", partes=[])
        self.assertTrue(falta)
        self.assertIn("Os nomes das partes devem ser informados", falta[0])
        # e com partes ela some
        self.assertEqual(
            RS.falta_para_selar(natureza="BAIXA", codigo_tj="16.22.2",
                                versao_tabela="0220260101",
                                partes=[{"nome": "FULANA DE EXEMPLO"}],
                                protocolo="11548"), [])

    def test_parte_sem_nome_nao_conta_como_parte(self):
        """Linha em branco na tabela não satisfaz o aparelho."""
        falta = RS.falta_para_selar(
            natureza="BAIXA", codigo_tj="16.22.2", versao_tabela="v",
            partes=[{"nome": "  ", "documento": "00000000000"}])
        self.assertTrue(any("partes" in f for f in falta))

    def test_a_tela_tem_campo_para_partes_e_ele_grava(self):
        """Era o que faltava: a tabela existia e nenhuma tela escrevia nela."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("não tem partes informadas", tela)
            self.assertIn("Acrescentar parte", tela)

            cliente.post(f"/livro3/{rid}/partes",
                         data={"csrf_token": csrf(tela),
                               "nome": "HELENA DE EXEMPLO",
                               "documento": "000.000.000-00",
                               "papel": "EMITENTE"},
                         follow_redirects=True)
            with db.connect() as con:
                partes = PT.listar(con, rid)
            self.assertEqual(len(partes), 1)
            self.assertEqual(partes[0]["nome"], "HELENA DE EXEMPLO")
            self.assertEqual(partes[0]["documento_numero"], "00000000000",
                             "o selo quer só os dígitos")
            self.assertEqual(partes[0]["documento_tipo"], "CPF")
            self.assertEqual(partes[0]["papel"], "EMITENTE")

    def test_o_tipo_do_documento_sai_do_tamanho_e_nao_de_uma_caixa(self):
        self.assertEqual(PT.tipo_do_documento("000.000.012-44"), "CPF")
        self.assertEqual(PT.tipo_do_documento("00.000.011/0001-71"), "CNPJ")
        self.assertIsNone(PT.tipo_do_documento("123"),
                          "documento de outro tamanho não vira palpite")
        self.assertIsNone(PT.tipo_do_documento(""))

    def test_os_papeis_medidos_vem_primeiro(self):
        """Os três das 25 partes do acervo, na ordem de uso."""
        codigos = [c for c, _ in PT.PAPEIS]
        self.assertEqual(codigos[:3], ["EMITENTE", "CREDOR", "PROPRIETARIO"])
        self.assertIn("AVALISTA", codigos, "o teor do 1.243 nomeia avalistas")

    def test_papel_fora_do_catalogo_e_recusado(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con, self.assertRaises(PT.ParteError):
                PT.acrescentar(con, registro_id=rid, nome="FULANO DE EXEMPLO",
                               papel="COMPRADOR")

    def test_a_parte_se_retira_e_a_ficha_volta_a_avisar(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            with db.transaction() as con:
                pid = PT.acrescentar(con, registro_id=rid, papel="CREDOR",
                                     nome="BANCO DE EXEMPLO S/A",
                                     documento="00000010000127")
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("BANCO DE EXEMPLO", tela)
            cliente.post(f"/livro3/parte/{pid}/remover",
                         data={"csrf_token": csrf(tela)},
                         follow_redirects=True)
            with db.connect() as con:
                self.assertEqual(PT.listar(con, rid), [])

    def test_a_ficha_mostra_o_que_o_registro_diz_sobre_as_partes(self):
        """Digitar de cabeça é como se erra nome."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("o que o registro diz sobre as partes", tela)
            self.assertIn("FULANA DE EXEMPLO", tela)

    # --------------------------------------------- o ato volta para a minuta

    def test_o_ato_volta_para_a_minuta_com_o_que_tinha_dentro(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid, 1, codigo_tj="16.22.2",
                               natureza_titulo="BAIXA DE HIPOTECA")
            with db.transaction() as con:
                r = MIN.voltar_do_ato(con, ato_id, agora=db.now(),
                                      motivo="o teor precisa ser reescrito")
            with db.connect() as con:
                m = MIN.uma(con, r["minuta_id"])
                sobrou = con.execute("SELECT COUNT(*) FROM ra_atos WHERE id=?",
                                     (ato_id,)).fetchone()[0]
            self.assertEqual(sobrou, 0, "o ato deixou de existir")
            self.assertEqual(m["situacao"], MIN.A_REVISAR)
            self.assertEqual(m["numero_pretendido"], 1)
            self.assertEqual(m["codigo_tj"], "16.22.2")
            self.assertEqual(m["natureza_titulo"], "BAIXA DE HIPOTECA")
            self.assertEqual(m["origem"], MIN.DESFEITO_DE_ATO)
            self.assertIn("reescrito", m["observacao"])

    def test_o_ato_com_selo_nao_volta(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid, 1, selo="SELO-QUE-JA-SAIU")
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.voltar_do_ato(con, ato_id, agora=db.now())

    def test_so_o_ultimo_ato_do_registro_volta(self):
        """A numeração do Livro 3 é contínua — tirar do meio abre buraco."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            primeiro = self._ato(db, rid, 1)
            self._ato(db, rid, 2)
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.voltar_do_ato(con, primeiro, agora=db.now())

    def test_o_ato_com_dinheiro_no_caixa_nao_volta(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid, 1, lancamento_id=77)
            with db.transaction() as con, self.assertRaises(MIN.MinutaError):
                MIN.voltar_do_ato(con, ato_id, agora=db.now())

    def test_o_cancelamento_se_desfaz_com_o_ato_que_o_causou(self):
        """Ficha cancelada por uma averbação que não existe mais é carimbo
        que mente."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid, 1)
            with db.transaction() as con:
                con.execute("UPDATE ra_registros SET situacao='CANCELADO' "
                            "WHERE id=?", (rid,))
            with db.transaction() as con:
                r = MIN.voltar_do_ato(con, ato_id, agora=db.now())
            with db.connect() as con:
                situacao = con.execute(
                    "SELECT situacao FROM ra_registros WHERE id=?",
                    (rid,)).fetchone()[0]
            self.assertTrue(r["descancelou"])
            self.assertEqual(situacao, "ATIVO")

    def test_a_ficha_devolve_o_ato_a_minuta_pelo_botao(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid = self._registro(db)
            ato_id = self._ato(db, rid, 1)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("Devolver à minuta", tela)
            self.assertIn("para selar, use o botão acima", tela,
                          "a tela tem de dizer que selar não exige desfazer")
            cliente.post(f"/livro3/ato/{ato_id}/devolver-a-minuta",
                         data={"csrf_token": csrf(tela),
                               "motivo": "o teor precisa ser reescrito"},
                         follow_redirects=True)
            with db.connect() as con:
                self.assertEqual(len(MIN.listar(con, rid)), 1)


if __name__ == "__main__":
    unittest.main()

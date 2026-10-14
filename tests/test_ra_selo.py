"""O selo do ato do Livro 3 — **contra o envelope que esta casa mandou.**

    «fiz a averbacao da 1243 e nao emitiu selo, deixe o livro 3 com as mesmas
     ferramentas do livro 2» — o oficial, 20/09/2026

O QUE ESTES TESTES GUARDAM, em ordem de importância:

  1. **o envelope é o que a casa mandou** — comparado com a transcrição de um
     envelope real do acervo, e não com a minha ideia dele. Foi assim que o
     `dadosSelo` embrulhado sobreviveu a 37 testes verdes neste projeto: eles
     comparavam a suposição contra ela mesma, dos dois lados;
  2. **a averbação leva a FRASE no lugar da matrícula** — `AV - 1 do Registro
     1332`, medido. Mandar só o número diria ao Tribunal que o selo é do
     registro, e não da averbação dele;
  3. **`registroAverbacao` vai zerado** — medido nos sete atos de Livro 3 que
     a casa selou, inclusive nos que têm AV-1;
  4. **quem escolhe o caminho é o valor declarado**, e não o tipo do ato;
  5. **a tela existe e recusa o segundo selo** do mesmo ato.

O envelope de referência é a **transcrição** do que saiu por
`/selo/imovel/ato-declarado/sem-valor` em 10/07/2020 (registro 1.332). Trocados
apenas o nome e o documento das partes e o nome do escrevente; **o formato
ficou como veio** — inclusive o `'0'` entre aspas e o `126.0` com casa decimal.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ra_selo as RS

SENHA = "Senha#12345"

# A TRANSCRIÇÃO — ver o cabeçalho.
ENVELOPE_REAL_DA_AVERBACAO = {
    "dadosSelo": {
        "codigoTipoAto": "16.22.2",
        "descontoProvimento279": False,
        "descricaoNatureza": ("AVERBAÇÃO SEM VALOR DECLARADO DE ADITIVO NO "
                              "REGISTRO 3-AUX, Nº 1332, SOBE AV-01/1332"),
        "escrevente": "ESCREVENTE DE EXEMPLO",
        "isento": False,
        "livro": "3",
        "naturezaTitulo": 126.0,
        "partes": {"nomePartes": [],
                   "parteAto": [
                       {"documento": "00000010000127",
                        "nome": "BANCO DE EXEMPLO S/A"},
                       {"documento": "00000000000",
                        "nome": "PARTE DE EXEMPLO"}]},
        "percentualDesconto": 0.0,
        "reterIss": False,
        "versaoTabelaDeCustas": "0220201012",
    },
    "matricula": "AV - 1 do Registro 1332",
    "protocolo": "10618",
    "quantidade": 1,
    "registroAverbacao": "0",
}


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class SeloDoLivro3Tests(unittest.TestCase):

    # ------------------------------------------------ a que mais importa

    def test_o_envelope_bate_com_o_que_a_casa_mandou(self):
        """Comparado com a transcrição, e não com a minha ideia do envelope."""
        montado = RS.envelope_do_ato(
            registro_numero="1332", tipo="AV", numero=1,
            escrevente="ESCREVENTE DE EXEMPLO",
            versao_tabela="0220201012",
            natureza=("AVERBAÇÃO SEM VALOR DECLARADO DE ADITIVO NO REGISTRO "
                      "3-AUX, Nº 1332, SOBE AV-01/1332"),
            codigo_tj="16.22.2", protocolo="10618",
            base_calculo_centavos=None,
            partes=[{"nome": "BANCO DE EXEMPLO S/A",
                     "documento": "00.000.010/0001-27"},
                    {"nome": "PARTE DE EXEMPLO", "documento": "000.000.000-00"}])
        self.assertEqual(montado, ENVELOPE_REAL_DA_AVERBACAO)

    def test_a_averbacao_leva_a_frase_no_lugar_da_matricula(self):
        """`AV - 1 do Registro 1332` — o campo identifica o ATO."""
        self.assertEqual(RS.referencia_do_ato("1332", "AV", 1),
                         "AV - 1 do Registro 1332")
        self.assertEqual(RS.referencia_do_ato("1550", "R", 1), "1550")

    def test_o_registro_averbacao_vai_zerado(self):
        """Medido nos sete: `'0'`, e texto, inclusive quando há AV-1."""
        for tipo, numero in (("AV", 1), ("AV", 7), ("R", 1)):
            envelope = RS.envelope_do_ato(
                registro_numero="1243", tipo=tipo, numero=numero,
                escrevente="X", versao_tabela="0220201012",
                natureza="BAIXA", codigo_tj="16.22.2")
            self.assertEqual(envelope["registroAverbacao"], "0")

    def test_o_caminho_sai_do_valor_declarado_e_nao_do_tipo(self):
        """Há averbação com valor e registro sem — medido no Livro 2 e no 3."""
        self.assertTrue(RS.caminho_do_ato(None).endswith("sem-valor"))
        self.assertTrue(RS.caminho_do_ato(0).endswith("sem-valor"))
        self.assertTrue(RS.caminho_do_ato(10061316).endswith("com-valor"))
        # e o envelope muda com ele: `quantidade` num, `baseCalculo` no outro
        sem = RS.envelope_do_ato(registro_numero="1", tipo="AV", numero=1,
                                 escrevente="X", versao_tabela="v",
                                 natureza="n", codigo_tj="16.22.2")
        com = RS.envelope_do_ato(registro_numero="1", tipo="R", numero=1,
                                 escrevente="X", versao_tabela="v",
                                 natureza="n", codigo_tj="16.9",
                                 base_calculo_centavos=10061316)
        self.assertEqual(sem["quantidade"], 1)
        self.assertNotIn("baseCalculo", sem)
        self.assertEqual(com["baseCalculo"], 100613.16)
        self.assertNotIn("quantidade", com)

    def test_o_livro_do_selo_e_o_3(self):
        """E não o volume da matrícula — este ato é do Registro Auxiliar."""
        envelope = RS.envelope_do_ato(
            registro_numero="1243", tipo="AV", numero=1, escrevente="X",
            versao_tabela="v", natureza="n", codigo_tj="16.22.2")
        self.assertEqual(envelope["dadosSelo"]["livro"], "3")

    # ---------------------------------------------------- o que ela recusa

    def test_o_que_falta_para_selar_e_dito_antes_da_rede(self):
        # AS PARTES ENTRARAM NESTA LISTA EM 21/09/2026: o aparelho recusa o
        # envelope sem elas, e eu havia escrito o contrario. Ver
        # `tests/test_ra_parte.py`.
        gente = [{"nome": "PARTE DE EXEMPLO"}]
        # O PROTOCOLO ENTROU EM 28/09/2026 (o Tribunal recusa sem ele): o
        # «nada falta» informa a prenotação.
        self.assertEqual(RS.falta_para_selar(
            natureza="x", codigo_tj="16.22.2", versao_tabela="v",
            partes=gente, protocolo="11548"), [])
        self.assertTrue(any("item da tabela" in f for f in RS.falta_para_selar(
            natureza="x", codigo_tj="", versao_tabela="v", partes=gente)))
        self.assertTrue(any("natureza" in f for f in RS.falta_para_selar(
            natureza="", codigo_tj="16.9", versao_tabela="v", partes=gente)))
        self.assertTrue(any("tabela de custas em vigor" in f
                            for f in RS.falta_para_selar(
                                natureza="x", codigo_tj="16.9",
                                versao_tabela="", partes=gente)))
        self.assertTrue(any("motivo escrito" in f for f in RS.falta_para_selar(
            natureza="x", codigo_tj="16.9", versao_tabela="v", partes=gente,
            isento=True)))

    def test_valor_vazio_e_none_e_nao_zero(self):
        """Zero mandaria toda averbação pelo caminho errado, sem ninguém ver."""
        self.assertIsNone(RS.centavos_do_valor(""))
        self.assertIsNone(RS.centavos_do_valor(None))
        self.assertIsNone(RS.centavos_do_valor("abc"))
        self.assertEqual(RS.centavos_do_valor("1.234,56"), 123456)
        self.assertEqual(RS.centavos_do_valor("0,00"), 0)

    def test_o_registro_sem_numero_e_recusado(self):
        with self.assertRaises(RS.RaSeloError):
            RS.referencia_do_ato("", "AV", 1)

    def test_o_modulo_nao_lavra_nem_numera_nem_cobra(self):
        """A mesma régua do CNIB, das fraudes e do usucapião."""
        proibidos = ("lavrar", "numerar", "cobrar", "cancelar", "decidir")
        for nome in [n for n in dir(RS) if not n.startswith("_")]:
            for proibido in proibidos:
                self.assertNotIn(
                    proibido, nome.lower(),
                    f"`ra_selo.{nome}` tem cara de praticar ato. Este módulo "
                    f"monta o pedido do selo e mais nada.")

    # ------------------------------------------------------------ a tela

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _com_parte(self, db, registro_id):
        """Sem parte, a recusa que aparece primeiro e a DELAS — e estes dois
        testes falam de outra coisa."""
        import ra_parte as PT
        with db.transaction() as con:
            PT.acrescentar(con, registro_id=registro_id, papel="EMITENTE",
                           nome="PARTE DE EXEMPLO", documento="00000000000")

    def _registro_com_averbacao(self, db):
        with db.transaction() as con:
            con.execute(
                """INSERT INTO ra_registros(numero, livro, natureza, situacao,
                                            criado_em)
                   VALUES (1243,'3','CEDULA_CREDITO_RURAL','ATIVO',?)""",
                (db.now(),))
            rid = con.execute("SELECT id FROM ra_registros WHERE numero=1243"
                              ).fetchone()[0]
            con.execute(
                """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato,
                                       teor, criado_em)
                   VALUES (?,'AV',1,?,?,?)""",
                (rid, db.now(), "CANCELAMENTO INTEGRAL DO REGISTRO.", db.now()))
            ato_id = con.execute(
                "SELECT id FROM ra_atos WHERE registro_id=?", (rid,)).fetchone()[0]
        return rid, ato_id

    def _entrar(self, app, db):
        db.create_user("admin", "Administrador", SENHA, "ADMIN")
        cliente = app.test_client()
        entrada = cliente.get("/login").get_data(as_text=True)
        cliente.post("/login", data={"username": "admin", "password": SENHA,
                                     "csrf_token": csrf(entrada)},
                     follow_redirects=True)
        return cliente

    def test_a_ficha_oferece_selar_o_ato_que_nasceu_sem_selo(self):
        """Era o buraco relatado: não havia por onde selar depois."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid, ato_id = self._registro_com_averbacao(db)
            cliente = self._entrar(app, db)
            html = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            self.assertIn("selar este ato", html)
            self.assertIn(f"/livro3/ato/{ato_id}/selar", html)
            self.assertIn("16.22.2", html,
                          "a tela oferece o item que esta casa usou")

    def test_dois_selos_para_o_mesmo_ato_e_recusado(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid, ato_id = self._registro_com_averbacao(db)
            with db.transaction() as con:
                con.execute("UPDATE ra_atos SET selo=? WHERE id=?",
                            ("SELO-JA-EXISTE", ato_id))
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            r = cliente.post(f"/livro3/ato/{ato_id}/selar",
                             data={"csrf_token": csrf(tela),
                                   "natureza_titulo": "BAIXA",
                                   "codigo_tj": "16.22.2"},
                             follow_redirects=True)
            self.assertIn("já tem selo", r.get_data(as_text=True))

    def test_sem_item_da_tabela_a_tela_recusa_antes_da_rede(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid, ato_id = self._registro_com_averbacao(db)
            self._com_parte(db, rid)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            r = cliente.post(f"/livro3/ato/{ato_id}/selar",
                             data={"csrf_token": csrf(tela),
                                   "natureza_titulo": "BAIXA DE HIPOTECA"},
                             follow_redirects=True)
            self.assertIn("item da tabela de custas",
                          r.get_data(as_text=True))
            with db.connect() as con:
                selo = con.execute("SELECT selo FROM ra_atos WHERE id=?",
                                   (ato_id,)).fetchone()[0]
            self.assertIsNone(selo)

    def test_o_que_foi_informado_fica_no_ato_mesmo_sem_selo(self):
        """Se o aparelho não responder, o que se digitou não se perde."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            rid, ato_id = self._registro_com_averbacao(db)
            self._com_parte(db, rid)
            cliente = self._entrar(app, db)
            tela = cliente.get(f"/livro3/{rid}").get_data(as_text=True)
            cliente.post(f"/livro3/ato/{ato_id}/selar",
                         data={"csrf_token": csrf(tela),
                               "natureza_titulo": "BAIXA DE HIPOTECA",
                               "codigo_tj": "16.22.2",
                               "base_calculo": "1.234,56"},
                         follow_redirects=True)
            with db.connect() as con:
                a = con.execute(
                    "SELECT natureza_titulo, codigo_tj, base_calculo_centavos "
                    "FROM ra_atos WHERE id=?", (ato_id,)).fetchone()
            self.assertEqual(a["natureza_titulo"], "BAIXA DE HIPOTECA")
            self.assertEqual(a["codigo_tj"], "16.22.2")
            self.assertEqual(a["base_calculo_centavos"], 123456)


if __name__ == "__main__":
    unittest.main()


class SeloDaCertidaoDoLivroTresTests(unittest.TestCase):
    """O SELO DA CERTIDÃO DO LIVRO 3 — 21/09/2026, «siga desenvolvimento».

    Medido no acervo: as **9** certidões deste livro (`LivroAuxiliarCertidao`)
    têm selo de `/selo/imovel/certidao` no protocolo geral delas — prefixo
    `CERIMV` —, e em duas (protocolos `2020.06.48` e `2020.07.35`) **não há
    outro caminho nenhum** no protocolo inteiro.
    """

    def test_o_caminho_do_livro_3_nao_e_o_do_rtd_pj(self):
        """**ERA O MESMO ATÉ HOJE, E O ESTRAGO ERA DINHEIRO.**

        `at_certidoes` serve as duas atribuições e os dois atos se chamam
        `CERTIDAO`: o par (tabela, tipo) não as separa. A receita de custas
        sai do CAMINHO — e a ficha do Livro 3 oferecia os itens do grupo 15
        (RTD/PJ) onde esta casa cobrou os do 16.24.
        """
        import ato_selado as AS
        self.assertEqual(
            AS.caminho_do_ato("at_certidoes", "CERTIDAO", "LIVRO3"),
            "/selo/imovel/certidao")
        self.assertEqual(
            AS.caminho_do_ato("at_certidoes", "CERTIDAO", "RCPJ_RTD"),
            "/selo/rtdpj/atos-em-geral")
        self.assertNotEqual(
            AS.caminho_do_ato("at_certidoes", "CERTIDAO", "LIVRO3"),
            AS.caminho_do_ato("at_certidoes", "CERTIDAO", "RCPJ_RTD"),
            "o Livro 3 é do Registro de Imóveis, e o RCPJ/RTD não é")

    def test_o_envelope_e_o_do_imovel_com_o_item_da_tabela(self):
        import ra_selo as RS
        envelope = RS.envelope_da_certidao(
            escrevente="JEAN", versao_tabela="0520260101",
            registro_numero=1243, quantidade=3)
        self.assertEqual(envelope["codigoTipoAto"], "16.24.4")
        self.assertEqual(envelope["quantidade"], 3,
                         "a quantidade é o número de FOLHAS, como nos 667")
        self.assertEqual(envelope["partes"]["nomePartes"], [],
                         "vazio, e não ausente — é o que a casa mandou")
        self.assertIs(envelope["isento"], False)
        self.assertEqual(envelope["versaoTabelaDeCustas"], "0520260101")

    def test_sem_requerente_vai_o_que_se_certifica_na_palavra_deste_livro(self):
        """No RI a casa mandou `MATRICULA 1116`. Aqui a coisa certificada
        chama-se **registro** — é assim que este livro a escreve no envelope do
        próprio ato (`AV - 1 do Registro 1332`, medido)."""
        import ra_selo as RS
        parte = RS.envelope_da_certidao(
            escrevente="JEAN", versao_tabela="0520260101",
            registro_numero=1243)["partes"]["parteAto"][0]
        self.assertEqual(parte["documento"], "00000000000")
        self.assertIn("Registro 1243", parte["nome"])
        self.assertIn("Livro 3", parte["nome"])
        self.assertNotIn("MATRICULA", parte["nome"].upper())

    def test_com_requerente_quem_vai_e_o_requerente(self):
        import ra_selo as RS
        parte = RS.envelope_da_certidao(
            escrevente="JEAN", versao_tabela="0520260101",
            registro_numero=1243, requerente="FULANA DE TAL",
            requerente_documento="000.000.012-44")["partes"]["parteAto"][0]
        self.assertEqual(parte["nome"], "FULANA DE TAL")
        self.assertEqual(parte["documento"], "00000001244",
                         "só os dígitos, como o resto da casa guarda")

    def test_sem_a_data_da_tabela_o_envelope_nao_sai(self):
        """A recusa é antes da rede, e diz onde se corrige."""
        import ato_selado as AS
        import ra_selo as RS
        with self.assertRaises(AS.AtoError) as caso:
            RS.envelope_da_certidao(escrevente="JEAN", versao_tabela="",
                                    registro_numero=1243)
        self.assertIn("tabela de custas", str(caso.exception))

    def test_a_procedencia_de_cada_coisa_fica_declarada(self):
        """MEDIDO é o que a casa mandou; TABELA é o que a norma diz. Confundir
        os dois apaga a procedência dos dois."""
        import ra_selo as RS
        self.assertEqual(RS.PROCEDENCIA_DO_CAMINHO_DA_CERTIDAO, "MEDIDO")
        self.assertEqual(RS.PROCEDENCIA_DO_CODIGO_DA_CERTIDAO, "TABELA")

    def test_a_certidao_de_mais_de_uma_folha_sao_dois_itens(self):
        """**MEDIDO NOS 667 ENVELOPES, agrupados pelo protocolo.**

        `16.24.4` + `16.24.4.1` em **99** protocolos; `16.24.1` + `16.24.2` em
        **94**; o item base sozinho em 44, e nesses 44 a quantidade é **1**. E
        nos pares quem carrega o número é a **folha acrescida** — a casa não
        mandou «inteiro teor, quantidade 5»: mandou «inteiro teor, 1» e «folha
        acrescida, 4».
        """
        import ra_selo as RS
        self.assertEqual(RS.itens_da_certidao(1), [("16.24.4", 1)])
        self.assertEqual(RS.itens_da_certidao(5),
                         [("16.24.4", 1), ("16.24.4.1", 4)])
        self.assertEqual(RS.itens_da_certidao(0), [("16.24.4", 1)],
                         "zero folha não existe — a certidão tem ao menos uma")
        for folhas in range(1, 13):
            itens = RS.itens_da_certidao(folhas)
            self.assertEqual(itens[0][1], 1,
                             "o item base vai sempre com uma folha")
            self.assertEqual(sum(q for _, q in itens), folhas,
                             "a soma das quantidades é o número de folhas")

    def test_o_codigo_do_item_manda_no_envelope(self):
        import ra_selo as RS
        envelope = RS.envelope_da_certidao(
            escrevente="JEAN", versao_tabela="0520260101",
            registro_numero=1243, quantidade=4, codigo="16.24.4.1")
        self.assertEqual(envelope["codigoTipoAto"], "16.24.4.1")
        self.assertEqual(envelope["quantidade"], 4)

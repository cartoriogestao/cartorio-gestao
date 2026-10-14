"""O atualizador do CNIB — **o que ele grava, e o que ele se recusa a gravar.**

Pedido do oficial em 19/09/2026: *«vamos fazer tudo e arrumar tudo e baixar
tudo»*, depois de medido que a cópia local era um retrato de 19/03/2023 e que
o transporte (`cnib_api.py`) estava pronto e sem ninguém do outro lado.

O QUE ESTES TESTES GUARDAM, em ordem de importância:

  1. **a leitura não consome a fila da serventia** — é a única coisa aqui que,
     se der errado, tira ordem da frente de alguém sem deixar rastro;
  2. **cancelamento não se desfaz por linha que não fala dele** — a mesma
     janela traz a ordem e o cancelamento, e a ordem pode chegar depois;
  3. **resposta que não se entende não vira «nada mudou»** — `forma_estranha`
     recusa e a janela não anda;
  4. **a janela volta atrás** — o zero da Central não é prova de ausência;
  5. **a tela existe e abre em instalação nova**, dizendo o que falta.

As respostas usadas aqui são a transcrição dos brutos de 18/09/2026
(`brutos_do_cnib.py`). Fixture inventado aqui testaria a minha ideia da
Central, e não a Central.
"""
from __future__ import annotations

import re
import sys
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brutos_do_cnib import (
    ORDEM_DE_CANCELAMENTO,
    ORDEM_DE_CANCELAMENTO_ANTIGA,
    ORDEM_DE_PEDIDO,
)

import cnib_atualizador as ATZ

SENHA = "Senha#12345"


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def resposta(ordens, **mais) -> dict:
    """Uma resposta do `ordens_na_janela`, na forma que ele devolve."""
    base = {"ordens": list(ordens), "lidas": len(ordens), "total": len(ordens),
            "paginas": 1, "forma": "ordens" if ordens else "vazia",
            "mensagem": "", "vazio": not ordens, "forma_estranha": False,
            "parou_no_teto": False}
    base.update(mais)
    return base


class AtualizadorDoCnibTests(unittest.TestCase):

    def _casa(self, td):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        # A ROTINA DIÁRIA NÃO SAI PARA A REDE NO TESTE. Ela já não sairia (sem
        # credencial não roda), mas marcar é o que garante que uma máquina com
        # credencial gravada não vire teste que fala com a Central de verdade.
        app.extensions["cnib_verificado"] = True
        return app, app.extensions["db"]

    def _gravar(self, db, ordens, *, de="2026-09-12", ate="2026-09-19"):
        with db.transaction() as con:
            return ATZ.gravar(con, de=de, ate=ate,
                              leitura=resposta(ordens), agora=db.now())

    # ------------------------------------------------ a que mais importa

    def test_a_leitura_nunca_consome_a_fila(self):
        """`ordens_visualizadas=True`, e **sem parâmetro para mudar**.

        Medido em 18/09/2026: com `False` a leitura consome — 341.697 ordens
        ficaram 341.497 depois de uma página de 200. Um trabalho que roda
        sozinho todo dia com `False` esvaziaria a fila desta serventia sem
        ninguém ver.
        """
        pedidos = []

        def espiao(de, ate, **kwargs):
            pedidos.append(kwargs)
            return resposta([])

        ATZ.ler_da_central("2026-09-01", "2026-09-19",
                           cpf_usuario="00000000000", ler=espiao)
        self.assertTrue(pedidos)
        self.assertIs(pedidos[0]["visualizadas"], True,
                      "a leitura do atualizador não pode consumir a fila")

        assinatura = ATZ.ler_da_central.__doc__ or ""
        self.assertIn("não há parâmetro", assinatura.lower(),
                      "a decisão de não consumir a fila tem de estar escrita")

    def test_o_cancelamento_nao_se_desfaz_pela_ordem_que_chega_depois(self):
        """A mesma janela traz as duas linhas, e a ordem pode vir por último.

        Foi o primeiro defeito que este módulo teve de não ter: um `DO UPDATE`
        ingênuo gravaria `ativa=1` por cima do cancelamento, e a ordem voltaria
        a valer no espelho sem que a Central tivesse dito nada.
        """
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            protocolo = ORDEM_DE_CANCELAMENTO["protocoloindisponibilidade"]
            # a ordem original, com o mesmo protocolo que o cancelamento cita
            original = dict(ORDEM_DE_PEDIDO, protocoloindisponibilidade=protocolo)

            self._gravar(db, [ORDEM_DE_CANCELAMENTO, original])

            with db.connect() as con:
                linha = con.execute(
                    "SELECT ativa, cancelamento_protocolo FROM ri_cnib_ordens "
                    "WHERE protocolo_cnib=?", (protocolo,)).fetchone()
            self.assertEqual(linha["ativa"], 0,
                             "a ordem cancelada não pode voltar a ativa")
            self.assertEqual(linha["cancelamento_protocolo"],
                             ORDEM_DE_CANCELAMENTO["cancelamentodeindisponibilidade"])

    def test_a_forma_que_nao_se_entende_e_recusada_e_a_janela_nao_anda(self):
        """`forma_estranha` não é `vazio`, e confundi-los é o pior defeito.

        Os dois devolvem zero ordens. Anotar «nada mudou» sobre uma resposta
        ilegível é dizer que o espelho está em dia quando ninguém sabe se está.
        """
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con:
                fora = ATZ.gravar(
                    con, de="2026-09-01", ate="2026-09-19",
                    leitura=resposta([], forma="outra", forma_estranha=True),
                    agora=db.now())
            self.assertEqual(fora["situacao"], ATZ.RECUSADA)
            with db.connect() as con:
                self.assertIsNone(ATZ.ultima_leitura(con),
                                  "recusa não pode virar marca de janela lida")

    def test_a_resposta_vazia_fica_anotada_e_a_janela_anda(self):
        """Vazio é resposta: a Central falou e a casa entendeu."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            fora = self._gravar(db, [], de="2026-09-01", ate="2026-09-19")
            self.assertEqual(fora["situacao"], ATZ.VAZIA)
            with db.connect() as con:
                ultima = ATZ.ultima_leitura(con)
            self.assertIsNotNone(ultima)
            self.assertEqual(ultima["ate"], "2026-09-19")

    def test_a_janela_do_dia_volta_uma_semana_atras(self):
        """O zero da Central não é prova de ausência — por isso se relê."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            self._gravar(db, [], de="2026-09-01", ate="2026-09-19")
            with db.connect() as con:
                de, ate = ATZ.janela_do_dia(con, hoje=date(2026, 9, 20))
            self.assertEqual(ate, "2026-09-20")
            self.assertEqual(de, "2026-09-12",
                             "a janela tem de sobrepor o que já foi lido")

    # ------------------------------------------------------ o que ela grava

    def test_a_ordem_entra_com_as_partes_e_a_data_em_iso(self):
        """`dd/mm/aaaa hh:mm:ss` é o que vem; ISO é o que o espelho guarda."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            fora = self._gravar(db, [ORDEM_DE_PEDIDO])
            self.assertEqual(fora["novas"], 1)
            with db.connect() as con:
                linha = con.execute(
                    "SELECT * FROM ri_cnib_ordens WHERE protocolo_cnib=?",
                    (ORDEM_DE_PEDIDO["protocoloindisponibilidade"],)).fetchone()
                pessoas = con.execute(
                    "SELECT * FROM ri_cnib_pessoas WHERE ordem_id=?",
                    (linha["id"],)).fetchall()
            self.assertEqual(linha["data_pedido"], "2026-06-01")
            self.assertEqual(linha["ativa"], 1)
            self.assertEqual(linha["origem"], "CNIB")
            self.assertEqual(len(pessoas), 1)
            self.assertEqual(pessoas[0]["nome"], "PARTE DE EXEMPLO")

    def test_a_ordem_com_duas_partes_guarda_as_duas(self):
        """40% das ordens têm mais de uma parte; o espelho antigo guardava uma."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            self._gravar(db, [ORDEM_DE_CANCELAMENTO_ANTIGA])
            with db.connect() as con:
                pessoas = con.execute(
                    """SELECT p.nome FROM ri_cnib_pessoas p
                        JOIN ri_cnib_ordens o ON o.id = p.ordem_id
                       WHERE o.protocolo_cnib=?""",
                    (ORDEM_DE_CANCELAMENTO_ANTIGA["protocoloindisponibilidade"],)
                ).fetchall()
            self.assertEqual(len(pessoas), 2)

    def test_a_mesma_ordem_em_duas_paginas_nao_vira_duas_linhas(self):
        """As páginas não são disjuntas: 2.996 distintas em 3.000, medido."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            self._gravar(db, [ORDEM_DE_PEDIDO, ORDEM_DE_PEDIDO])
            self._gravar(db, [ORDEM_DE_PEDIDO])
            with db.connect() as con:
                quantas = con.execute(
                    "SELECT COUNT(*) FROM ri_cnib_ordens WHERE protocolo_cnib=?",
                    (ORDEM_DE_PEDIDO["protocoloindisponibilidade"],)).fetchone()[0]
                pessoas = con.execute(
                    "SELECT COUNT(*) FROM ri_cnib_pessoas").fetchone()[0]
            self.assertEqual(quantas, 1)
            self.assertEqual(pessoas, 1,
                             "as partes se substituem, não se somam")

    def test_a_central_escreve_por_cima_do_que_veio_do_eoficio(self):
        """O espelho tem duas origens, e manda a mais nova."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            protocolo = ORDEM_DE_PEDIDO["protocoloindisponibilidade"]
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ri_cnib_ordens
                          (protocolo_cnib, data_pedido, ativa, origem)
                       VALUES (?,?,1,'EOFICIO')""", (protocolo, "2023-01-01"))
            fora = self._gravar(db, [ORDEM_DE_PEDIDO])
            self.assertEqual(fora["novas"], 0, "a ordem já estava lá")
            with db.connect() as con:
                linha = con.execute(
                    "SELECT origem, data_pedido FROM ri_cnib_ordens "
                    "WHERE protocolo_cnib=?", (protocolo,)).fetchone()
            self.assertEqual(linha["origem"], "CNIB")
            self.assertEqual(linha["data_pedido"], "2026-06-01")

    def test_a_ordem_sem_protocolo_e_recusada_com_frase_de_balcao(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with self.assertRaises(ATZ.CnibAtualizadorError):
                self._gravar(db, [dict(ORDEM_DE_PEDIDO,
                                       protocoloindisponibilidade="")])

    # -------------------------------------------------------- a posta em dia

    def test_a_posta_em_dia_anda_mes_a_mes_e_marca_o_que_ja_foi_lido(self):
        """684 páginas não cabem numa varredura; o mês é o pedaço que cabe."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ri_cnib_ordens
                          (protocolo_cnib, data_pedido, ativa, origem)
                       VALUES ('X',?,1,'EOFICIO')""", ("2026-07-19",))
            with db.connect() as con:
                pedacos = ATZ.janelas_da_posta_em_dia(con, hoje=date(2026, 9, 19))
            self.assertEqual([p["titulo"] for p in pedacos],
                             ["07/2026", "08/2026", "09/2026"])
            self.assertEqual(pedacos[0]["de"], "2026-07-01")
            self.assertEqual(pedacos[-1]["ate"], "2026-09-19",
                             "o último pedaço termina hoje, e não no fim do mês")
            self.assertFalse(any(p["feita"] for p in pedacos))

            self._gravar(db, [], de="2026-07-01", ate="2026-07-31")
            with db.connect() as con:
                pedacos = ATZ.janelas_da_posta_em_dia(con, hoje=date(2026, 9, 19))
            self.assertTrue(pedacos[0]["feita"])
            self.assertFalse(pedacos[1]["feita"])

    def test_a_posta_em_dia_nao_encolhe_quando_a_central_manda_ordem_de_hoje(self):
        """O atraso começa no **retrato do acervo**, e não no maior pedido.

        Basta uma ordem pedida hoje para o `MAX(data_pedido)` da tabela pular
        para hoje — e a posta em dia se daria por concluída com três anos e
        meio de buraco por baixo, sem ninguém ver. É o defeito que a primeira
        leitura de verdade criaria.
        """
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con:
                con.execute(
                    """INSERT INTO ri_cnib_ordens
                          (protocolo_cnib, data_pedido, ativa, origem)
                       VALUES ('ACERVO',?,1,'EOFICIO')""", ("2026-06-15",))
            with db.connect() as con:
                antes = ATZ.janelas_da_posta_em_dia(con, hoje=date(2026, 9, 19))

            # a Central manda uma ordem pedida HOJE
            self._gravar(db, [dict(ORDEM_DE_PEDIDO,
                                   datapedido="19/09/2026 10:00:00")])
            with db.connect() as con:
                depois = ATZ.janelas_da_posta_em_dia(con, hoje=date(2026, 9, 19))

            self.assertEqual([p["titulo"] for p in antes],
                             ["06/2026", "07/2026", "08/2026", "09/2026"])
            self.assertEqual([p["titulo"] for p in depois],
                             [p["titulo"] for p in antes],
                             "o atraso a recuperar não pode encolher porque a "
                             "Central respondeu")

    def test_o_erro_de_rede_fica_escrito(self):
        """«Não há ordem nova» e «não falo com a Central há uma semana» são
        coisas diferentes, e a segunda é a que precisa de gente."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con:
                ATZ.anotar(con, de="2026-09-01", ate="2026-09-19",
                           situacao=ATZ.ERRO, agora=db.now(),
                           mensagem="Não deu para falar com o CNIB.")
            with db.connect() as con:
                self.assertIsNone(ATZ.ultima_leitura(con),
                                  "erro não conta como leitura boa")
                self.assertEqual(len(ATZ.leituras(con)), 1,
                                 "mas ele fica na lista")

    # ------------------------------------------------------------ a tela

    def test_a_tela_abre_em_instalacao_nova_e_diz_o_que_falta(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            html = cliente.get("/registro-imoveis/cnib/central").get_data(as_text=True)
            self.assertIn("a cópia local e a Central", html)
            self.assertIn("CPF de quem consulta", html)
            self.assertIn("não consome a fila", html)

    def test_a_consulta_local_aponta_para_a_central(self):
        """Relato #72 — quem abre /cnib precisa achar a atualização manual."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            html = cliente.get("/registro-imoveis/cnib").get_data(as_text=True)
            self.assertIn("/registro-imoveis/cnib/central", html)
            self.assertIn("Atualizar cópia local", html)

    def test_a_tela_recusa_janela_grande_demais_para_uma_ida(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            tela = cliente.get("/registro-imoveis/cnib/central").get_data(as_text=True)
            resposta_web = cliente.post(
                "/registro-imoveis/cnib/central/buscar",
                data={"csrf_token": csrf(tela), "de": "2012-01-01",
                      "ate": "2026-09-19"}, follow_redirects=True)
            self.assertIn("Janela grande demais",
                          resposta_web.get_data(as_text=True))

    def test_o_cpf_de_quem_consulta_se_guarda_pela_tela(self):
        """Sem CPF a Central não responde, e o campo não existia em lugar nenhum."""
        with TemporaryDirectory() as td:
            app, db = self._casa(td)
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            entrada = cliente.get("/login").get_data(as_text=True)
            cliente.post("/login", data={"username": "admin",
                                         "password": SENHA,
                                         "csrf_token": csrf(entrada)},
                         follow_redirects=True)
            tela = cliente.get("/registro-imoveis/cnib/central").get_data(as_text=True)
            cliente.post("/registro-imoveis/cnib/central/ajustes",
                         data={"csrf_token": csrf(tela),
                               "cpf": "000.000.044-21", "rotina": "on"},
                         follow_redirects=True)
            with db.connect() as con:
                self.assertEqual(ATZ.cpf_de_quem_consulta(con), "00000004421")
                self.assertTrue(ATZ.rotina_ligada(con))


if __name__ == "__main__":
    unittest.main()

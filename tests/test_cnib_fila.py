"""A leitura da fila do CNIB e a data honesta da cópia local (23/11/2026).

A leitura por janela, com `ordens_visualizadas=True`, parou de trazer ordem
nova em 12/08/2026, e cada resposta vazia era anotada como janela lida: a ficha
seguiu dizendo «cópia local até hoje». Estes testes guardam o conserto:

  1. **a fila nasce desligada**, e sem a autorização nada sai para a Central;
  2. **cada página fica gravada antes de se pedir a próxima**, porque o que a
     Central manda sai da fila e não volta;
  3. **página que não entrou no banco fica no disco** e entra antes de se pedir
     mais;
  4. **o pedido da fila é o que se mediu em 18/09/2026**: `False`, sem datas,
     sempre a página 1;
  5. **resposta vazia não move a marca**, e a data da base é a menor entre a
     última leitura que trouxe ordem e a ordem mais nova.

As ordens são as transcrições de `brutos_do_cnib.py`, com o protocolo trocado
para haver várias.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brutos_do_cnib import ORDEM_DE_PEDIDO, PAGINACAO_SEM_PROXIMA, envelope

import cnib_api as API
import cnib_atualizador as ATZ

SENHA = "Senha#12345"
CPF = "00000004421"


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def ordens(*protocolos, dia="01/06/2026 10:00:00"):
    return [dict(ORDEM_DE_PEDIDO, protocoloindisponibilidade=p, datapedido=dia)
            for p in protocolos]


def pagina(lista, *, mais=True, restantes=None, forma=None):
    """Uma página na forma que `uma_pagina_da_fila` devolve."""
    return {"ordens": list(lista), "forma": forma or ("ordens" if lista else "vazia"),
            "paginacao": {"tem_proxima_pagina": mais}, "mensagem": "",
            "status": 200, "restantes": restantes}


class Central:
    """A fila de mentira: serve as páginas e anota o que se pediu."""

    def __init__(self, paginas, ao_pedir=None):
        self.paginas = list(paginas)
        self.pedidos: list[dict] = []
        self.ao_pedir = ao_pedir

    def __call__(self, **kwargs):
        self.pedidos.append(kwargs)
        if self.ao_pedir:
            self.ao_pedir(len(self.pedidos))
        return self.paginas.pop(0) if len(self.paginas) > 1 else self.paginas[0]


class FilaDoCnibTests(unittest.TestCase):

    def _casa(self, td, *, autorizada=True):
        from app import create_app
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["cnib_verificado"] = True
        db = app.extensions["db"]
        db.set_settings({ATZ.CHAVE_DO_CPF: CPF,
                         ATZ.CHAVE_DA_FILA: "1" if autorizada else "0"})
        return app, db

    def _ler(self, db, pasta, central, **mais):
        return ATZ.ler_a_fila(db, hoje=date(2026, 11, 23), pasta=pasta,
                              pedir=central, **mais)

    def _protocolos(self, db):
        with db.connect() as con:
            return {r["protocolo_cnib"] for r in con.execute(
                "SELECT protocolo_cnib FROM ri_cnib_ordens").fetchall()}

    # ------------------------------------------------- 1. desligada de fábrica

    def test_a_fila_nasce_desligada_e_nada_sai_para_a_central(self):
        with TemporaryDirectory() as td:
            from app import create_app
            app = create_app({"TESTING": True, "DATA_DIR": td})
            app.extensions["cnib_verificado"] = True
            db = app.extensions["db"]
            db.set_settings({ATZ.CHAVE_DO_CPF: CPF})
            with db.connect() as con:
                self.assertFalse(ATZ.fila_autorizada(con))
            central = Central([pagina(ordens("A"))])
            with self.assertRaises(ATZ.CnibAtualizadorError):
                self._ler(db, Path(td) / "guarda", central)
            self.assertEqual(central.pedidos, [],
                             "sem a autorização, nenhum pedido sai")

    # ------------------------------------------- 2. página a página, e gravada

    def test_cada_pagina_entra_no_banco_antes_de_se_pedir_a_proxima(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            ja_no_banco: list[set] = []
            central = Central(
                [pagina(ordens("A1", "A2")), pagina(ordens("B1", "B2")),
                 pagina(ordens("C1"), mais=False, restantes=0)],
                ao_pedir=lambda n: ja_no_banco.append(self._protocolos(db)))
            fora = self._ler(db, Path(td) / "guarda", central)

            self.assertEqual(fora["situacao"], ATZ.OK)
            self.assertEqual((fora["lidas"], fora["novas"], fora["paginas"]), (5, 5, 3))
            self.assertEqual(ja_no_banco[1], {"A1", "A2"},
                             "a página 1 tem de estar gravada quando se pede a 2")
            self.assertEqual(ja_no_banco[2], {"A1", "A2", "B1", "B2"})
            self.assertEqual(self._protocolos(db), {"A1", "A2", "B1", "B2", "C1"})
            self.assertEqual(ATZ.paginas_guardadas(Path(td) / "guarda"), [],
                             "página gravada não fica no disco")
            with db.connect() as con:
                ultima = ATZ.ultima_leitura(con)
            self.assertEqual(ultima["ate"], "2026-11-23")
            self.assertIn("restavam 0", ultima["mensagem"])

    def test_o_pedido_da_fila_nao_escolhe_pagina_nem_janela(self):
        """Com `False` a página 1 já é a próxima: pedir a 2 pularia ordens."""
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            central = Central([pagina(ordens("A")), pagina(ordens("B"), mais=False)])
            self._ler(db, Path(td) / "guarda", central)
            self.assertEqual(central.pedidos, [{"cpf_usuario": CPF}] * 2)

    # --------------------------------------- 3. o banco falhou depois da Central

    def test_pagina_que_nao_entrou_fica_no_disco_e_entra_antes_de_pedir_mais(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            pasta = Path(td) / "guarda"
            original = ATZ._gravar_pagina
            chamadas = {"n": 0}

            def quebra_na_segunda(con, lista):
                chamadas["n"] += 1
                if chamadas["n"] == 2:
                    raise RuntimeError("disco cheio")
                return original(con, lista)

            central = Central([pagina(ordens("A")), pagina(ordens("B")),
                               pagina(ordens("C"), mais=False)])
            with patch.object(ATZ, "_gravar_pagina", side_effect=quebra_na_segunda):
                fora = self._ler(db, pasta, central)

            self.assertEqual(fora["situacao"], ATZ.ERRO)
            self.assertIn("Parei", fora["mensagem"])
            self.assertEqual(len(central.pedidos), 2,
                             "depois da falha, nada mais se pede à Central")
            guardadas = ATZ.paginas_guardadas(pasta)
            self.assertEqual(len(guardadas), 1)
            self.assertEqual(
                [o["protocoloindisponibilidade"] for o in
                 json.loads(guardadas[0].read_text(encoding="utf-8"))], ["B"])
            self.assertEqual(self._protocolos(db), {"A"})

            # a rodada seguinte grava o que ficou ANTES do primeiro pedido
            visto_antes: list[set] = []
            seguinte = Central([pagina(ordens("C"), mais=False)],
                               ao_pedir=lambda n: visto_antes.append(self._protocolos(db)))
            self._ler(db, pasta, seguinte)
            self.assertEqual(visto_antes[0], {"A", "B"})
            self.assertEqual(self._protocolos(db), {"A", "B", "C"})
            self.assertEqual(ATZ.paginas_guardadas(pasta), [])

    def test_pagina_guardada_que_nao_entra_impede_a_rodada(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            pasta = Path(td) / "guarda"
            pasta.mkdir()
            (pasta / "pagina-00000001-0001.json").write_text("{quebrado", encoding="utf-8")
            central = Central([pagina(ordens("A"))])
            with self.assertRaises(ATZ.CnibAtualizadorError):
                self._ler(db, pasta, central)
            self.assertEqual(central.pedidos, [])

    # ------------------------------------------------------ 4. quando parar

    def test_a_fila_que_nao_anda_para_a_rodada(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            central = Central([pagina(ordens("A", "B"))])   # sempre a mesma
            fora = self._ler(db, Path(td) / "guarda", central)
            self.assertEqual(fora["situacao"], ATZ.ERRO)
            self.assertIn("mesmas ordens", fora["mensagem"])
            self.assertEqual(len(central.pedidos), 2)

    def test_a_rodada_para_no_teto_e_nao_conta_como_base_em_dia(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            central = Central([pagina(ordens("A")), pagina(ordens("B")),
                               pagina(ordens("C"))])
            fora = self._ler(db, Path(td) / "guarda", central, maximo_de_paginas=2)
            self.assertTrue(fora["parou_no_teto"])
            self.assertEqual(len(central.pedidos), 2)
            with db.connect() as con:
                self.assertIsNone(ATZ.ultima_leitura(con))

    def test_a_fila_vazia_na_primeira_pagina_fica_anotada_e_nao_move_a_marca(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            hoje = date.fromisoformat(db.now()[:10])   # o relógio que anota a leitura
            fora = ATZ.ler_a_fila(db, hoje=hoje, pasta=Path(td) / "guarda",
                                  pedir=Central([pagina([], mais=False)]))
            self.assertEqual(fora["situacao"], ATZ.VAZIA)
            with db.connect() as con:
                self.assertIsNone(ATZ.ultima_leitura(con))
                self.assertTrue(ATZ.ja_leu_hoje(con, hoje=hoje),
                                "a vazia conta como tentativa do dia")

    def test_o_erro_de_rede_no_meio_fecha_a_rodada_com_o_que_ja_entrou(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            respostas = [pagina(ordens("A"))]

            def central(**kwargs):
                if respostas:
                    return respostas.pop(0)
                raise API.CnibError("Não consegui falar com o CNIB.")

            fora = self._ler(db, Path(td) / "guarda", central)
            self.assertEqual(fora["situacao"], ATZ.ERRO)
            self.assertEqual(fora["lidas"], 1)
            self.assertEqual(self._protocolos(db), {"A"})

    def test_a_ordem_sem_protocolo_nao_derruba_a_pagina(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            lista = ordens("A", "") + ordens("B")
            fora = self._ler(db, Path(td) / "guarda", Central([pagina(lista, mais=False)]))
            self.assertEqual(fora["situacao"], ATZ.OK)
            self.assertEqual(self._protocolos(db), {"A", "B"})
            self.assertIn("sem protocolo", fora["mensagem"])

    # ---------------------------------------------- 5. a data honesta da base

    def test_a_data_da_base_e_a_menor_entre_a_leitura_e_a_ordem_mais_nova(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con:
                ATZ.gravar(con, de="2026-08-01", ate="2026-08-12",
                           leitura={"ordens": ordens("A", dia="12/08/2026 09:00:00"),
                                    "lidas": 1}, agora=db.now())
                for dia in ("2026-11-20", "2026-11-21", "2026-11-22"):
                    ATZ.anotar(con, de=dia, ate=dia, situacao=ATZ.VAZIA,
                               agora=dia + "T00:00:00")
            with db.connect() as con:
                self.assertEqual(ATZ.data_da_base(con, hoje=date(2026, 11, 23)),
                                 "2026-08-12",
                                 "leitura vazia não diz que a cópia está em dia")

            # a leitura que trouxe ordem antiga não faz a base parecer de hoje
            with db.transaction() as con:
                ATZ.gravar(con, de="2026-11-16", ate="2026-11-23",
                           leitura={"ordens": ordens("CANC", dia="01/03/2012 10:00:00"),
                                    "lidas": 1}, agora=db.now())
            with db.connect() as con:
                self.assertEqual(ATZ.data_da_base(con, hoje=date(2026, 11, 23)),
                                 "2026-08-12")

    def test_a_ordem_com_data_no_futuro_nao_entra_na_data_da_base(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con:
                ATZ.gravar(con, de="2026-11-01", ate="2026-11-22",
                           leitura={"ordens": ordens("A", dia="20/11/2026 09:00:00")
                                    + ordens("ERRADA", dia="01/01/2099 09:00:00"),
                                    "lidas": 2}, agora=db.now())
            with db.connect() as con:
                self.assertEqual(ATZ.data_da_base(con, hoje=date(2026, 11, 23)),
                                 "2026-11-20")

    def test_a_janela_do_dia_nao_passa_de_um_mes(self):
        with TemporaryDirectory() as td:
            _, db = self._casa(td)
            with db.transaction() as con:
                ATZ.gravar(con, de="2026-08-01", ate="2026-08-12",
                           leitura={"ordens": ordens("A"), "lidas": 1}, agora=db.now())
            with db.connect() as con:
                de, ate = ATZ.janela_do_dia(con, hoje=date(2026, 11, 23))
            self.assertEqual((de, ate), ("2026-10-23", "2026-11-23"))

    # ----------------------------------------------------------- 6. a tela

    def _entrar(self, app, db, papel="ADMIN"):
        db.create_user("oficial", "Oficial", SENHA, papel)
        cliente = app.test_client()
        entrada = cliente.get("/login").get_data(as_text=True)
        cliente.post("/login", data={"username": "oficial", "password": SENHA,
                                     "csrf_token": csrf(entrada)},
                     follow_redirects=True)
        return cliente

    def test_ligar_a_fila_pede_o_ciente_e_fica_na_auditoria(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td, autorizada=False)
            cliente = self._entrar(app, db)
            tela = cliente.get("/registro-imoveis/cnib/central").get_data(as_text=True)
            self.assertIn("Ler a fila da serventia", tela)
            self.assertIn("não se desfaz", tela)

            sem = cliente.post("/registro-imoveis/cnib/central/fila/autorizacao",
                               data={"csrf_token": csrf(tela), "ligar": "1"},
                               follow_redirects=True).get_data(as_text=True)
            self.assertIn("marque que está ciente", sem)
            with db.connect() as con:
                self.assertFalse(ATZ.fila_autorizada(con))

            cliente.post("/registro-imoveis/cnib/central/fila/autorizacao",
                         data={"csrf_token": csrf(tela), "ligar": "1", "ciente": "1"},
                         follow_redirects=True)
            with db.connect() as con:
                self.assertTrue(ATZ.fila_autorizada(con))
                acao = con.execute(
                    "SELECT 1 FROM audit_logs WHERE action='CNIB_FILA_AUTORIZACAO'"
                ).fetchone()
            self.assertIsNotNone(acao)

    def test_so_o_admin_liga_a_fila(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td, autorizada=False)
            cliente = self._entrar(app, db, "MANAGER")
            tela = cliente.get("/registro-imoveis/cnib/central").get_data(as_text=True)
            self.assertIn("Só o oficial liga a leitura da fila", tela)
            cliente.post("/registro-imoveis/cnib/central/fila/autorizacao",
                         data={"csrf_token": csrf(tela), "ligar": "1", "ciente": "1"})
            with db.connect() as con:
                self.assertFalse(ATZ.fila_autorizada(con))

    def test_o_botao_da_rodada_nao_sai_com_a_fila_desligada(self):
        with TemporaryDirectory() as td:
            app, db = self._casa(td, autorizada=False)
            cliente = self._entrar(app, db)
            tela = cliente.get("/registro-imoveis/cnib/central").get_data(as_text=True)
            with patch.object(ATZ, "ler_a_fila") as ler:
                html = cliente.post("/registro-imoveis/cnib/central/fila/ler",
                                    data={"csrf_token": csrf(tela)},
                                    follow_redirects=True).get_data(as_text=True)
            self.assertIn("A leitura da fila está desligada", html)
            ler.assert_not_called()

    def test_a_rotina_diaria_le_a_fila_quando_autorizada(self):
        import cnib_web as W
        app = SimpleNamespace(extensions={"usuario_id": lambda: None},
                              route=lambda *a, **k: lambda f: f)
        W.registrar_rotas(app, MagicMock(), lambda f: f, lambda *a: lambda f: f, MagicMock())
        with patch.object(W, "date") as relogio, \
             patch.object(W.threading, "Thread") as thread, \
             patch.object(ATZ, "rotina_ligada", return_value=True), \
             patch.object(ATZ, "ja_leu_hoje", return_value=False), \
             patch.object(ATZ, "esta_pronto", return_value={"pronto": True}), \
             patch.object(ATZ, "fila_autorizada", return_value=True), \
             patch.object(ATZ, "janela_do_dia", return_value=("2026-11-16", "2026-11-23")):
            relogio.today.return_value = date(2026, 11, 23)
            app.extensions["cnib_uma_vez_por_dia"]()
        self.assertEqual(thread.call_count, 1)
        self.assertEqual(thread.call_args.kwargs["name"], "cnib-fila")


# ------------------------------------------------------- o corpo do pedido


def test_o_corpo_da_fila_e_o_que_se_mediu_em_18_09(monkeypatch):
    """`False`, sem datas, página 1 e páginas de 200, como em 18/09/2026."""
    corpos = []

    def central(metodo, caminho, **kw):
        corpos.append(json.loads(kw["corpo"].decode("utf-8")))
        return {"status": 200, "json": envelope(ordens("A"), PAGINACAO_SEM_PROXIMA),
                "texto": "", "bytes": b""}

    monkeypatch.setattr(API, "token", lambda *a, **k: "TOKEN-DE-MENTIRA")
    monkeypatch.setattr(API, "_bater_cru", central)
    p = API.uma_pagina_da_fila(cpf_usuario=CPF)
    assert corpos == [{"cpf_usuario": CPF, "ordens_visualizadas": False,
                       "pagina_inicial": 1, "tamanho_pagina": 200,
                       "proxima_pagina": False}]
    assert p["restantes"] == 0
    assert [o["protocoloindisponibilidade"] for o in p["ordens"]] == ["A"]


def test_a_janela_continua_sem_consumir():
    """O conserto não mexe no padrão da janela: `ler_da_central` segue `True`."""
    pedidos = []
    ATZ.ler_da_central("2026-11-16", "2026-11-23", cpf_usuario=CPF,
                       ler=lambda de, ate, **kw: pedidos.append(kw) or {})
    assert pedidos[0]["visualizadas"] is True


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import io
import json
import re
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


SENHA = "SenhaForte123!"


def csrf(html: str) -> str:
    encontrado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if not encontrado:
        raise AssertionError("a tela nao trouxe token CSRF")
    return encontrado.group(1)


VERSAO_ALVO = "999.999.999"


def pacote() -> tuple[bytes, str]:
    payload = {
        "VERSAO.txt": VERSAO_ALVO.encode("ascii"),
        "app.py": f'VERSION = "{VERSAO_ALVO}"\n'.encode("ascii"),
    }
    manifesto = {
        "product": "CartorioGestao", "format": 1,
        "version": VERSAO_ALVO, "min_version": "0",
        "files": [
            {"path": nome, "sha256": hashlib.sha256(conteudo).hexdigest()}
            for nome, conteudo in payload.items()
        ],
        "delete": [],
    }
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as zf:
        zf.writestr("update_manifest.json", json.dumps(manifesto))
        for nome, conteudo in payload.items():
            zf.writestr(f"payload/{nome}", conteudo)
    dados = saida.getvalue()
    return dados, hashlib.sha256(dados).hexdigest()


class UpdateApprovalWebTests(unittest.TestCase):
    def setUp(self):
        # Pacote montado à mão, sem assinatura. Desde 14/10/2026 há chave
        # cadastrada e o pacote sem assinatura é recusado antes da aprovação;
        # a assinatura tem os testes dela em test_assinatura_da_atualizacao.py.
        # Aqui, o modo de transição — como em test_update_network.py.
        import assinatura_da_atualizacao as ASS
        from unittest import mock
        trava = mock.patch.object(ASS, "CHAVES_CONFIAVEIS", {})
        trava.start()
        self.addCleanup(trava.stop)

    def test_preparar_nao_aplica_e_aprovacao_exige_senha(self):
        from app import create_app

        with TemporaryDirectory() as td:
            dados = Path(td)
            app = create_app({"TESTING": True, "DATA_DIR": str(dados)})
            app.extensions["backup_checked"] = True
            db = app.extensions["db"]
            db.create_user("admin", "Administrador", SENHA, "ADMIN")
            cliente = app.test_client()
            login = cliente.get("/login").get_data(as_text=True)
            resposta = cliente.post(
                "/login",
                data={
                    "username": "admin", "password": SENHA,
                    "csrf_token": csrf(login),
                },
                follow_redirects=True,
            )
            self.assertEqual(resposta.status_code, 200)

            tela = cliente.get("/atualizacoes").get_data(as_text=True)
            arquivo, digest = pacote()
            resposta = cliente.post(
                "/atualizacoes",
                data={
                    "csrf_token": csrf(tela), "action": "prepare",
                    "expected_sha256": digest,
                    "update_file": (io.BytesIO(arquivo), "correcao.cgu"),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            html = resposta.get_data(as_text=True)
            self.assertIn("ainda nao foi aplicada", html)
            self.assertIn("PRONTA PARA APROVAÇÃO", html)
            meta_path = dados / "updates" / "staged" / VERSAO_ALVO / "_update_meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["state"], "READY_FOR_APPROVAL")
            self.assertFalse(list((dados / "backups").glob("backup_pre_atualizacao_*.zip")))
            self.assertFalse((dados / "updates" / "last_result.json").exists())

            resposta = cliente.post(
                "/atualizacoes",
                data={
                    "csrf_token": csrf(html), "action": "approve",
                    "stage_version": VERSAO_ALVO, "approval_sha256": digest,
                    "confirmation": f"APLICAR {VERSAO_ALVO}",
                    "admin_password": "senha errada",
                },
                follow_redirects=True,
            )
            self.assertIn(
                "Senha do administrador incorreta",
                resposta.get_data(as_text=True),
            )
            self.assertEqual(
                json.loads(meta_path.read_text(encoding="utf-8"))["state"],
                "READY_FOR_APPROVAL",
            )

            tela = cliente.get("/atualizacoes").get_data(as_text=True)
            resposta = cliente.post(
                "/atualizacoes",
                data={
                    "csrf_token": csrf(tela), "action": "approve",
                    "stage_version": VERSAO_ALVO, "approval_sha256": digest,
                    "confirmation": f"APLICAR {VERSAO_ALVO}",
                    "admin_password": SENHA, "review_ack": "yes",
                },
                follow_redirects=True,
            )
            #   A RECUSA DIZ QUAL E A PASTA E O QUE FAZER — medido em 15/09/2026.
            #   Antes eram treze caracteres no log, «Acesso negado.», depois de o
            #   servico ter sido parado. Aqui nao ha `install.json` no diretorio de
            #   dados do teste, que e justamente um dos casos que a regua recusa: o
            #   sistema nao tem como saber qual pasta e a instalacao — e a frase diz
            #   isso, e diz por onde se aplica.
            html = resposta.get_data(as_text=True)
            self.assertIn("install.json", html)
            self.assertIn("ATUALIZAR_SISTEMA.cmd", html)
            self.assertEqual(
                json.loads(meta_path.read_text(encoding="utf-8"))["state"],
                "READY_FOR_APPROVAL",
            )


if __name__ == "__main__":
    unittest.main()

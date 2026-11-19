"""O atualizador da tela nao pode nascer dentro da tarefa do servidor.

O `aplicar_atualizacao.ps1` para a tarefa `CartorioGestaoServidor`. O
Agendador encerra o job inteiro. Se o atualizador foi lancado com um
`Popen` comum, ele morre junto — e a troca fica pela metade.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import update_manager


class _Proc:
    def __init__(self, codigo: int, stderr: str = "", stdout: str = "") -> None:
        self.returncode = codigo
        self.stderr = stderr
        self.stdout = stdout


class LancamentoForaDaArvoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.raiz = Path(self._td.name)
        self.instalacao = self.raiz / "programa"
        self.dados = self.raiz / "dados"
        self.preparacao = self.raiz / "staged" / "3.7.18"
        (self.instalacao / "installer").mkdir(parents=True)
        (self.instalacao / "installer" / "aplicar_atualizacao.ps1").write_text(
            "# ps1 de teste\n", encoding="utf-8"
        )
        self.preparacao.mkdir(parents=True)
        self.dados.mkdir()

    def _patches(self, rodar, popen=None, plataforma="win32"):
        empilhar = [
            mock.patch.object(update_manager.sys, "platform", plataforma),
            mock.patch.object(
                update_manager, "installed_app_dir", return_value=self.instalacao
            ),
            mock.patch.object(
                update_manager, "pode_aplicar_sozinho", return_value=(True, "")
            ),
            mock.patch.object(update_manager, "_rodar_schtasks", side_effect=rodar),
        ]
        if popen is None:
            popen = mock.Mock()
        empilhar.append(mock.patch.object(update_manager.subprocess, "Popen", popen))
        for item in empilhar:
            item.start()
            self.addCleanup(item.stop)
        return popen

    def test_dispara_pela_tarefa_propria_e_nao_pela_do_servidor(self):
        chamadas: list[list[str]] = []

        def rodar(args):
            chamadas.append(list(args))
            return _Proc(0)

        popen = self._patches(rodar)
        update_manager.launch_windows_updater(
            self.preparacao, self.dados, 4242, 8765, "CartorioGestaoServidor"
        )

        nomes = [c[c.index("/TN") + 1] for c in chamadas if "/TN" in c]
        self.assertEqual(nomes, [update_manager.TAREFA_DO_ATUALIZADOR] * 2)
        self.assertNotIn("CartorioGestaoServidor", nomes)
        self.assertTrue(any(c[:2] == ["/Create", "/TN"] and "/XML" in c for c in chamadas))
        self.assertTrue(any(c[:2] == ["/Run", "/TN"] for c in chamadas))
        popen.assert_not_called()

        lancador = self.dados / "updates" / "_lancar_atualizacao.cmd"
        self.assertTrue(lancador.is_file())
        texto = lancador.read_text(encoding="ascii")
        self.assertIn("aplicar_atualizacao.ps1", texto)
        self.assertIn("-ParentPid 4242", texto)
        self.assertIn("-Port 8765", texto)
        self.assertIn(str(self.preparacao), texto)
        self.assertIn("CartorioGestaoAtualizar", texto)

        log = (self.dados / "updates" / "update.log").read_text(encoding="utf-8")
        self.assertIn("fora da arvore da tarefa CartorioGestaoServidor", log)
        self.assertIn("CartorioGestaoAtualizar", log)

    def test_a_tarefa_nao_dispara_sozinha_a_meia_noite_nem_no_boot(self):
        xml = update_manager.xml_da_tarefa_do_atualizador(
            cmd_exe=Path(r"C:\Windows\System32\cmd.exe"),
            lancador=Path(r"C:\dados\updates\_lancar_atualizacao.cmd"),
        )
        self.assertIn("2099-01-01T00:00:00", xml)
        self.assertIn("S-1-5-18", xml)
        self.assertIn("AllowStartOnDemand>true", xml)
        self.assertNotIn("ONSTART", xml)
        self.assertIn("_lancar_atualizacao.cmd", xml)

    def test_o_principal_system_e_o_da_tarefa_do_servidor(self):
        """18/11/2026: o Windows 11 da producao recusou `LogonType ServiceAccount`
        numa tarefa 1.2. A `CartorioGestaoServidor`, que ele aceita, e 1.3 com
        so o SID do SYSTEM e o RunLevel."""
        xml = update_manager.xml_da_tarefa_do_atualizador(
            cmd_exe=Path(r"C:\Windows\System32\cmd.exe"),
            lancador=Path(r"C:\dados\updates\_lancar_atualizacao.cmd"),
        )
        self.assertIn('<Task version="1.3"', xml)
        principal = xml[xml.index("<Principal "):xml.index("</Principal>")]
        self.assertIn("<UserId>S-1-5-18</UserId>", principal)
        self.assertIn("<RunLevel>HighestAvailable</RunLevel>", principal)
        self.assertNotIn("LogonType", principal)
        self.assertNotIn("ServiceAccount", xml)

    def test_se_o_agendador_recusa_nada_e_lancado_e_nada_para(self):
        """18/11/2026: o plano B fora do Agendador parou o servico e morreu ao
        abrir a copia e o rollback (0xC0000142). Sem a tarefa propria, recusa."""
        def rodar(_args):
            return _Proc(1, stderr="Acesso negado.")

        popen = self._patches(rodar)
        with self.assertRaises(update_manager.UpdateError) as ctx:
            update_manager.launch_windows_updater(
                self.preparacao, self.dados, 7, 8765
            )
        popen.assert_not_called()
        self.assertIn("NADA FOI ALTERADO", str(ctx.exception))
        self.assertFalse(hasattr(update_manager, "flags_fora_da_arvore"))
        log = (self.dados / "updates" / "update.log").read_text(encoding="utf-8")
        self.assertIn("Acesso negado", log)
        self.assertIn("NADA FOI ALTERADO", log)
        resultado = json.loads(
            (self.dados / "updates" / "last_result.json").read_text(encoding="utf-8"))
        self.assertEqual(resultado["status"], "NAO_APLICADA")
        self.assertEqual(resultado["version"], "3.7.18")
        self.assertIn("NADA FOI ALTERADO", resultado["message"])

    def test_fora_do_windows_continua_recusando(self):
        popen = self._patches(lambda args: _Proc(0), plataforma="linux")
        with self.assertRaises(update_manager.UpdateError):
            update_manager.launch_windows_updater(
                self.preparacao, self.dados, 7, 8765
            )
        popen.assert_not_called()

    def test_aspas_do_cmd_preservam_caminho_com_espaco(self):
        caminho = Path(r"C:\Program Files\CartorioGestao\installer\aplicar_atualizacao.ps1")
        self.assertEqual(
            update_manager._quote_cmd(str(caminho)),
            '"C:\\Program Files\\CartorioGestao\\installer\\aplicar_atualizacao.ps1"',
        )

    def test_tenta_system_e_depois_a_conta_atual(self):
        xmls: list[bytes] = []

        def rodar(args):
            if args[:1] == ["/Create"]:
                xmls.append(Path(args[args.index("/XML") + 1]).read_bytes())
                if len(xmls) == 1:
                    return _Proc(1, stderr="recusou SYSTEM")
            return _Proc(0)

        self._patches(rodar)
        update_manager.launch_windows_updater(
            self.preparacao, self.dados, 1, 8765
        )
        self.assertEqual(len(xmls), 2)
        primeiro = xmls[0].decode("utf-16")
        segundo = xmls[1].decode("utf-16")
        self.assertIn("S-1-5-18", primeiro)
        self.assertNotIn("S-1-5-18", segundo)
        self.assertIn("InteractiveToken", segundo)


if __name__ == "__main__":
    unittest.main()

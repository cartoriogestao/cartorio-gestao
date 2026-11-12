"""O atualizador da tela nao pode nascer dentro da tarefa do servidor.

O `aplicar_atualizacao.ps1` para a tarefa `CartorioGestaoServidor`. O
Agendador encerra o job inteiro. Se o atualizador foi lancado com um
`Popen` comum, ele morre junto — e a troca fica pela metade.
"""
from __future__ import annotations

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

    def test_se_o_agendador_recusa_sai_da_arvore_com_breakaway(self):
        def rodar(_args):
            return _Proc(1, stderr="Acesso negado.")

        popen = self._patches(rodar)
        update_manager.launch_windows_updater(
            self.preparacao, self.dados, 7, 8765
        )
        popen.assert_called_once()
        flags = popen.call_args.kwargs["creationflags"]
        self.assertEqual(flags, update_manager.flags_fora_da_arvore())
        self.assertTrue(flags & update_manager.CREATE_BREAKAWAY_FROM_JOB)
        self.assertTrue(flags & 0x08000000)  # CREATE_NO_WINDOW
        self.assertFalse(flags & 0x00000008)  # DETACHED_PROCESS abre janela
        comando = popen.call_args.args[0]
        self.assertEqual(comando[0], "powershell.exe")
        self.assertIn("-File", comando)
        log = (self.dados / "updates" / "update.log").read_text(encoding="utf-8")
        self.assertIn("CREATE_BREAKAWAY_FROM_JOB", log)
        self.assertIn("Acesso negado", log)

    def test_se_nao_consegue_sair_da_arvore_recusa_e_nao_derruba_o_balcao(self):
        def rodar(_args):
            return _Proc(1, stderr="recusado")

        popen = mock.Mock(side_effect=OSError(5, "Acesso negado"))
        self._patches(rodar, popen=popen)
        with self.assertRaises(update_manager.UpdateError) as ctx:
            update_manager.launch_windows_updater(
                self.preparacao, self.dados, 7, 8765
            )
        self.assertIn("NADA FOI ALTERADO", str(ctx.exception))
        self.assertIn("CartorioGestaoServidor", str(ctx.exception))
        flags = popen.call_args.kwargs["creationflags"]
        self.assertTrue(flags & update_manager.CREATE_BREAKAWAY_FROM_JOB)
        log = (self.dados / "updates" / "update.log").read_text(encoding="utf-8")
        self.assertIn("NADA FOI ALTERADO", log)

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

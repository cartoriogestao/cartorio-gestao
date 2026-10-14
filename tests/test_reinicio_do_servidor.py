"""PARAR O SERVIDOR NAO E TORCER: E MEDIR QUE ELE PAROU — 15/09/2026.

O DEFEITO, medido nesta instalacao em 15/09/2026, com a arvore de processos na mao:

    PID 36120  o python que atende a porta 8765   <- VIVO, com o codigo velho
    pai 31844  runtime\\Scripts\\python.exe         <- o lancador do venv
    avo  1244  cmd.exe da tarefa agendada         <- MORTO

O `runtime` e um venv: o `Scripts\\python.exe` dele e um LANCADOR, que cria um filho
(o interpretador de verdade) e espera. Quem carrega o codigo e segura o socket e o
FILHO.

As duas portas de atualizacao paravam assim:

    schtasks /End /TN CartorioGestaoServidor     (o .cmd)
    Stop-Process -Id $ParentPid -Force           (o .cgu)

e NENHUMA DAS DUAS PARAVA O SERVIDOR. O `schtasks /End` mata o que a tarefa iniciou
— o cmd.exe — e deixa os netos vivos; o `Stop-Process -Id $ParentPid` mata o
LANCADOR, e o filho fica. O resultado medido foi o pior possivel: o servico continuou
no ar com a versao antiga, o `robocopy` copiou por baixo dele, o `/Run` seguinte nao
conseguiu subir (a porta estava ocupada) e as telas do balcao seguiram mostrando
3.6.134 enquanto o disco tinha 3.6.135.

**E O PIOR NAO ERA O SERVIDOR ANTIGO: ERA O AVISO.** As duas portas conferiam
`HTTP 200` no `/saude` para dizer "atualizado" — e quem respondia 200 era o processo
VELHO. O sistema dizia que atualizou, e nao atualizou. Carimbo que mente, na versao
mais cara dele, porque a resposta era sobre o proprio estado do sistema.

O CONSERTO tem uma peca so, `installer/reiniciar_servidor.ps1`, e as duas portas a
chamam. Estes testes guardam o que a medicao fixou:

 1. a morte e CONFERIDA, e nao suposta — `Stop-Process` e `taskkill` que devolvem
    "Acesso negado" nao podem virar "parei o PID";
 2. a espera pela porta e medida: `Parar` devolve 2 quando alguem ficou, e a copia
    NAO acontece — copiar arquivo novo por baixo de servidor vivo e o defeito;
 3. `Subir` compara a versao que responde com a instalada: `HTTP 200` nao basta;
 4. a rotina nao mata quem a chamou nem usa `/T` em ancestral — nas duas portas quem
    tem a porta e ANCESTRAL dela, e o pai e quem ainda vai copiar os arquivos;
 5. as duas portas param de parar do jeito que nao para, e chamam a MESMA rotina;
 6. o componente viaja (o `installer` nao esta excluido) e a instalacao o confere com
    `fc /b`, porque um `ps1` velho na pasta e o defeito de novo.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parent.parent

# O ATUALIZADOR MORA AO LADO DA PASTA INSTALÁVEL (INSTALAR_CARTORIO_GESTAO); no
# SANDBOX ele fica em `SERVIDOR/`, e o repositório público não traz nenhum dos
# dois. Sem ele o teste se declara pulado, em vez de estourar por arquivo ausente.
_ATUALIZADOR = next((p for p in (RAIZ.parent / "ATUALIZAR_SISTEMA.cmd",
                                 RAIZ.parent.parent / "SERVIDOR" / "ATUALIZAR_SISTEMA.cmd")
                     if p.exists()), RAIZ.parent / "ATUALIZAR_SISTEMA.cmd")


def _ler_atualizador() -> str:
    if not _ATUALIZADOR.exists():
        import unittest
        raise unittest.SkipTest("o ATUALIZAR_SISTEMA.cmd não está ao lado desta árvore")
    return _ATUALIZADOR.read_text(encoding="utf-8", errors="replace")
WINDOWS = sys.platform.startswith("win")
PS = ("powershell.exe" if WINDOWS else "pwsh")
COMPONENTE = RAIZ / "installer" / "reiniciar_servidor.ps1"


class ORastroDoDefeitoTests(unittest.TestCase):
    """O que estava escrito no comentario das duas portas, agora medido no codigo."""

    def cmd(self) -> str:
        # O `.cmd` mora em SERVIDOR\, ao lado da pasta do programa.
        return _ler_atualizador()

    def ps1(self) -> str:
        return (RAIZ / "installer" / "aplicar_atualizacao.ps1").read_text(
            encoding="utf-8", errors="replace")

    def rotina(self) -> str:
        return COMPONENTE.read_text(encoding="utf-8", errors="replace")

    def test_o_componente_existe_e_e_um_script_de_verdade(self):
        self.assertTrue(COMPONENTE.is_file(), f"falta {COMPONENTE}")
        texto = self.rotina()
        self.assertIn("param(", texto)
        self.assertIn("ValidateSet('Parar','Subir','Reiniciar')", texto)

    def test_as_duas_portas_chamam_a_mesma_rotina(self):
        """**DUAS VERSOES DO MESMO PEDACO DIVERGEM NO PRIMEIRO CONSERTO** — e este
        pedaco decide se o balcao fica no ar. Por isso a parada e a subida passaram a
        ser UMA rotina, e as duas portas so a chamam."""
        for nome, texto in ((".cmd", self.cmd()), ("aplicar_atualizacao.ps1", self.ps1())):
            with self.subTest(porta=nome):
                self.assertIn("reiniciar_servidor.ps1", texto)
        # O .cmd tem o caminho num lugar so e chama nos degraus certos.
        cmd = self.cmd()
        self.assertIn("call :REINICIAR Parar", cmd)
        self.assertIn("call :REINICIAR Subir", cmd)
        self.assertIn("-File \"%REINICIO%\"", cmd)
        # O ps1 do .cgu tem a funcao que so chama e devolve o codigo.
        self.assertIn("function ReiniciarServico", self.ps1())
        self.assertIn("ReiniciarServico 'Parar'", self.ps1())
        self.assertIn("ReiniciarServico 'Subir'", self.ps1())

    def test_as_portas_deixaram_de_parar_do_jeito_que_nao_para(self):
        """**O DEFEITO EM SI, E NAO A PROSA QUE O EXPLICA.** O `.cmd` nao pode voltar a
        ter `schtasks /End` como quem para o servico, e o `ps1` do `.cgu` nao pode
        voltar a matar so o `$ParentPid` — o lancador do venv — enquanto o filho, que
        tem o socket, continua vivo.

        A varredura e sobre o CODIGO, sem comentario: o comentario das duas portas
        cita as duas linhas justamente para dizer que elas sairam, e um teste que
        olhasse o arquivo inteiro passaria lendo a propria explicacao.
        """
        def codigo(texto: str, comentario: str) -> str:
            return "\n".join(l for l in texto.splitlines()
                             if not l.strip().startswith(comentario))

        cmd = codigo(self.cmd(), "rem")
        self.assertNotIn("schtasks /End /TN %TAREFA%", cmd)
        self.assertNotIn("call :PARAR", cmd)
        ps1 = codigo(self.ps1(), "#")
        self.assertNotIn("Stop-Process -Id $ParentPid", ps1)
        self.assertNotIn("Disable-ScheduledTask -TaskName $TaskName", ps1)
        self.assertNotIn("Stop-ScheduledTask -TaskName $TaskName", ps1)

    def test_a_morte_e_conferida_e_nao_suposta(self):
        """**A PRIMEIRA VERSAO DESTE ARQUIVO DIZIA "parei o PID" SEM OLHAR.** Medido
        minutos depois: o processo estava VIVO e a mensagem engolida era "Acesso
        negado". `rowcount` e resposta; "deu certo" e suposicao — regra desta casa,
        quebrada aqui por mim na primeira versao."""
        texto = self.rotina()
        self.assertIn("function Vivo", texto)
        # Depois do Stop-Process E depois do taskkill, quem decide e o Vivo.
        self.assertIn("if (-not (Vivo $alvo)) { Dizer \"  parei o PID $alvo\"; return $true }", texto)
        self.assertIn("if (-not (Vivo $alvo)) { Dizer \"  parei o PID $alvo (por taskkill)\"; return $true }", texto)
        # E a recusa volta como false, para quem chamou montar a lista do que ficou.
        self.assertIn("return $false", texto)
        self.assertIn("NAO consegui parar o PID", texto)

    def test_a_falta_de_elevacao_e_dita_com_todas_as_letras(self):
        """Numa sessao sem elevacao o `taskkill` responde "Acesso negado" e o processo
        fica. Quem le a lista ve um python vivo e conclui que o sistema travou — quando
        o que faltou foi permissao. Isto aparece porque foi o que aconteceu no primeiro
        ensaio deste script, rodado a mao."""
        texto = self.rotina()
        self.assertIn("Acesso negado", texto)
        self.assertIn("elevada", texto)
        self.assertIn("ATUALIZAR_SISTEMA.cmd ja pede", texto)
        # E a linha da lista serve para ir achar o processo: CommandLine volta VAZIO
        # para processo de outra elevacao, e foi o que saiu no ensaio ("PID : python.exe").
        self.assertIn("Get-Process -Id $p", texto)

    def test_a_porta_ocupada_impede_a_copia(self):
        """**A ORDEM E O CONSERTO.** Se o servidor nao parar, o `.cmd` PARA AQUI: copiar
        arquivo novo por baixo de um servidor vivo e exatamente o defeito que esta
        rotina existe para impedir."""
        cmd = self.cmd()
        parada = cmd.find("call :REINICIAR Parar")
        desiste = cmd.find("NADA FOI COPIADO")
        copia = cmd.find('robocopy "%FONTE%" "%PROG%"')
        self.assertGreater(parada, -1)
        self.assertGreater(desiste, parada, "a desistencia nao vem depois da parada")
        self.assertGreater(copia, desiste, "copia antes de garantir que o servidor parou")
        self.assertIn("exit /b 3", cmd[desiste:copia])

    def test_a_copia_so_acontece_depois_de_a_porta_ser_medida(self):
        """A rotina espera — e espera de verdade, um segundo por vez, olhando quem tem
        a porta. Um `timeout /t 3` que torce deixaria o defeito de pe no dia em que a
        maquina estivesse lenta."""
        texto = self.rotina()
        self.assertIn("function PidsNaPorta", texto)
        self.assertIn("for ($i = 0; $i -lt $EsperaParaLiberar; $i++)", texto)
        self.assertIn('Dizer "Porta $Port livre."', texto)
        self.assertIn("return 2", texto)

    def test_a_subida_confere_a_versao_e_nao_so_o_http_200(self):
        """**O CARIMBO QUE MENTE, NA FORMA MAIS CARA.** Um `HTTP 200` podia ser o
        processo velho respondendo — foi o que aconteceu. Agora quem sobe compara a
        versao que responde com a que esta gravada no `VERSAO.txt` da instalacao."""
        texto = self.rotina()
        self.assertIn("/saude", texto)
        self.assertIn("$noAr -eq $esperada", texto)
        self.assertIn("return 4", texto)
        self.assertIn("return 3", texto)
        # A versao esperada sai do DISCO, e nao de uma constante escrita aqui.
        self.assertIn("VERSAO.txt", texto)
        self.assertIn("function VersaoDaInstalacao", texto)

    def test_o_cmd_confere_a_versao_e_traduz_o_codigo(self):
        """Quem chama decide PELO NUMERO — o `.cmd` nao pode dizer "Pronto" quando o
        codigo diz que quem esta no ar e a versao antiga."""
        cmd = self.cmd()
        self.assertIn('if "%CODIGO_SUBIDA%"=="4"', cmd)
        self.assertIn("NAO e a versao instalada", cmd)
        self.assertIn('if "%CODIGO_SUBIDA%"=="2"', cmd)
        self.assertIn("nao subiu", cmd)
        # E a versao esperada vem do VERSAO.txt da INSTALACAO, depois da copia.
        self.assertIn('if exist "%PROG%\\VERSAO.txt"', cmd)

    def test_a_rotina_nao_mata_quem_a_chamou(self):
        """**NAS DUAS PORTAS QUEM TEM A PORTA E ANCESTRAL DESTE SCRIPT.**

            .cmd   cmd.exe do ATUALIZAR_SISTEMA.cmd  ->  eu
            .cgu   servidor (tem a porta) -> aplicar_atualizacao.ps1 -> eu

        O PAI e quem ainda vai copiar os arquivos e me chamar de volta: mata-lo
        abortaria a atualizacao entre a parada e a copia. E um `taskkill /T` em
        QUALQUER ancestral levaria a minha arvore junto — com os arquivos pela metade."""
        texto = self.rotina()
        self.assertIn("$MeusAncestrais", texto)
        self.assertIn("$NuncaMatar", texto)
        self.assertIn("$NuncaMatar = @([int]$PID)", texto)
        self.assertIn("$NuncaMatar += [int]$MeusAncestrais[0]", texto)
        # E o `/T` so entra quando o alvo NAO e ancestral.
        self.assertIn("$comArvore = -not ($MeusAncestrais -contains $alvo)", texto)
        self.assertIn("if ($comArvore) { $argumentos += '/T' }", texto)
        # E a protecao e do proprio script contra si mesmo.
        self.assertIn("if ($alvo -eq $PID)", texto)

    def test_o_rastro_fica_em_arquivo_proprio(self):
        """Na atualizacao pelo `.cgu` nao existe tela: se o reinicio nao deixasse
        rastro, a pergunta "por que o sistema ficou na versao antiga?" nao teria onde
        ser respondida depois que a janela fechasse."""
        texto = self.rotina()
        self.assertIn("reinicio_do_servidor.log", texto)
        self.assertIn("Add-Content -LiteralPath $logPath", texto)
        # E as duas portas apontam o mesmo log para o oficial.
        self.assertIn("reinicio_do_servidor.log", self.cmd())

    def test_a_porta_e_lida_por_duas_fontes_somadas(self):
        """**ZERO MEDIDO E ZERO POR ENGANO SAO A MESMA TELA** — 15/09/2026.

        O `Get-NetTCPConnection` NAO estoura numa sessao sem elevacao: devolve LISTA
        VAZIA. Enquanto o `netstat` era o plano B do `catch`, ele nunca era consultado
        nesse caso, e a funcao respondia "porta livre" com o servidor antigo VIVO —
        medido na mao, com o `netstat` mostrando `LISTENING 19380` no mesmo instante.

        E o engano cai para o lado que nao avisa: porta declarada livre deixa a copia
        comecar em cima do servidor antigo, que e o defeito que este arquivo existe para
        impedir. Aqui a prova e estrutural: as duas fontes tem de ser SOMADAS, e o
        `netstat` tem de estar FORA do `catch` do modulo."""
        texto = self.rotina()
        corpo = texto[texto.find("function PidsNaPorta"):texto.find("function Arvore")]
        self.assertNotEqual(corpo, "")
        do_modulo = corpo.find("Get-NetTCPConnection")
        do_netstat = corpo.find("netstat.exe")
        self.assertGreater(do_modulo, -1, "PidsNaPorta nao pergunta ao modulo")
        self.assertGreater(do_netstat, -1, "PidsNaPorta nao pergunta ao netstat")
        #   O `} catch {}` que fecha o try do modulo tem de vir ANTES do netstat: se
        #   ele viesse depois, o netstat estaria dentro do plano B outra vez.
        fecha_o_modulo = corpo.find("} catch {}")
        self.assertGreater(fecha_o_modulo, do_modulo)
        self.assertGreater(do_netstat, fecha_o_modulo,
                           "o netstat voltou a ser plano B: com o modulo devolvendo vazio "
                           "sem estourar, ele nunca seria consultado")
        # E as duas entradas somam no mesmo acumulador, em vez de uma escolher a outra.
        self.assertIn("$achados += @(Get-NetTCPConnection", corpo)
        self.assertIn("$achados += [int]$t[4]", corpo)
        self.assertNotIn("$achados = @(Get-NetTCPConnection", corpo,
                         "o modulo esta SOBRESCREVENDO o que o netstat achou")

    def test_a_espera_da_subida_e_em_segundos_e_cumpre_o_que_promete(self):
        """O PARAMETRO SE CHAMA `EsperaSegundos`, E TEM DE VALER SEGUNDOS.

        Aqui havia `for ($i = 0; $i -lt $EsperaSegundos; $i++)`, que conta ITERACOES: cada
        volta leva o `Start-Sleep 1` MAIS o tempo da tentativa de conexao, que e de ~1 s
        quando a porta recusa e de ate 2 s (o `-TimeoutSec`) enquanto a aplicacao carrega.
        O mesmo numero valia 60 s ou 180 s conforme a maquina.

        E o engano cai para o lado ruim: numa maquina rapida em recusar, a espera acabaria
        antes de o servico ficar pronto e a atualizacao diria "nao respondeu" com ele
        subindo — o carimbo que mente ao contrario. Medido nesta instalacao, da criacao do
        processo ate o `/saude` responder certo: cerca de 90 segundos (21:00:28 -> 21:02:00).
        """
        texto = self.rotina()
        self.assertIn("$limite = (Get-Date).AddSeconds($EsperaSegundos)", texto)
        self.assertIn("while ((Get-Date) -lt $limite)", texto)
        #   **A VARREDURA E SOBRE O CODIGO, SEM COMENTARIO** — e nao por preciosismo: a
        #   primeira versao deste teste ficou vermelha lendo a propria explicacao. O
        #   comentario que conta o defeito cita o `for ($i = 0; $i -lt $EsperaSegundos;`
        #   justamente para dizer que ele saiu, e um `assertNotIn` sobre o arquivo inteiro
        #   passava a medir a prosa. **Decima quarta vez que um varredor desta casa mede a
        #   palavra em vez do codigo** — e a terceira vez que a prosa sou eu.
        codigo = "\n".join(l for l in texto.splitlines() if not l.strip().startswith("#"))
        self.assertNotIn("$i -lt $EsperaSegundos", codigo,
                         "a espera da subida voltou a contar iteracoes em vez de segundos")
        # E o padrao cobre o tempo medido, com folga — o dobro dele.
        self.assertIn("[int]$EsperaSegundos = 180", texto)


class OComponenteViajaTests(unittest.TestCase):
    """Um `ps1` velho na pasta e o defeito de novo — e este decide se o balcao volta."""

    def test_a_pasta_installer_nao_e_excluida_da_copia(self):
        """Se `installer` entrar na lista de exclusao, o componente deixa de viajar — e
        sem erro nenhum, que foi como o `aplicar_atualizacao.ps1` ficou de 13/08 a
        15/09 naquela instalacao."""
        import update_manager

        self.assertNotIn("installer", update_manager.PASTAS_IGNORADAS_NA_COPIA)

    def test_o_componente_e_um_caminho_critico_da_atualizacao(self):
        """A lista dos criticos existe para o que **nao pode faltar**: se ele nao
        chegar, a parada e a subida ficam sem quem as faca."""
        import update_manager

        self.assertIn("installer/reiniciar_servidor.ps1", update_manager.CAMINHOS_CRITICOS)
        self.assertIn("installer/aplicar_atualizacao.ps1", update_manager.CAMINHOS_CRITICOS)

    def test_a_instalacao_confere_que_ele_chegou_igual(self):
        """Existir nao basta: `fc /b` contra a origem, como ja se fazia com o
        `aplicar_atualizacao.ps1`."""
        cmd = _ler_atualizador()
        trecho = cmd[cmd.find("reiniciar_servidor.ps1"):]
        self.assertIn("fc /b", trecho)
        self.assertIn("DIFERENTE do da origem", trecho)


class AReguaRodaTests(unittest.TestCase):
    """A rotina e medida em execucao, e nao so lida.

    A porca que roda aqui e de verdade, e nao um duble: um script PowerShell, um
    `schtasks` de verdade contra uma tarefa que nao existe, um `VERSAO.txt` de verdade
    numa pasta temporaria. O que se substitui sao os NUMEROS — porta e tarefa —, para
    nao mexer no servidor do balcao.
    """

    PORTA_LIVRE = 59987
    TAREFA_QUE_NAO_EXISTE = "CartorioGestaoTarefaDeTesteQueNaoExiste"

    def rodar(self, acao: str, *extras, timeout: int = 90) -> subprocess.CompletedProcess:
        with TemporaryDirectory() as td:
            cmd = [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COMPONENTE),
                   "-Acao", acao, "-InstallDir", td, "-DataDir", td,
                   "-TaskName", self.TAREFA_QUE_NAO_EXISTE,
                   "-Port", str(self.PORTA_LIVRE), "-EsperaParaLiberar", "3",
                   "-EsperaSegundos", "3", *extras]
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                  encoding="utf-8", errors="replace")

    @unittest.skipUnless(WINDOWS, "o agendador e a porta sao do Windows")
    def test_porta_livre_devolve_zero_e_nao_inventa_sujeira(self):
        """**O CAMINHO FELIZ, MEDIDO.** Sem ninguem na porta e com a tarefa ausente,
        `Parar` devolve 0 — e nada e escrito fora do `DataDir` que se passou."""
        with TemporaryDirectory() as td:
            r = subprocess.run(
                [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COMPONENTE),
                 "-Acao", "Parar", "-InstallDir", td, "-DataDir", td,
                 "-TaskName", self.TAREFA_QUE_NAO_EXISTE, "-Port", str(self.PORTA_LIVRE),
                 "-EsperaParaLiberar", "3"],
                capture_output=True, text=True, timeout=90,
                encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("Porta", r.stdout)
            self.assertIn("RESULTADO: OK", r.stdout)
            log = Path(td) / "logs" / "reinicio_do_servidor.log"
            self.assertTrue(log.is_file(), "nao ficou rastro do que aconteceu")
            self.assertIn("livre", log.read_text(encoding="utf-8"))

    @unittest.skipUnless(WINDOWS, "o agendador e do Windows")
    def test_tarefa_ausente_nao_sobe_e_diz_que_foi_o_agendador(self):
        """Um `schtasks /Run` que nao inicia coisa nenhuma NAO PODE virar sucesso. O
        codigo 1 diz que foi o agendador, e a frase diz qual tarefa."""
        r = self.rodar("Subir")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("O agendador nao conseguiu iniciar a tarefa", r.stdout)
        self.assertIn(self.TAREFA_QUE_NAO_EXISTE, r.stdout)
        self.assertIn("RESULTADO: ERRO", r.stdout)

    @unittest.skipUnless(WINDOWS, "o agendador e do Windows")
    def test_a_versao_lida_e_a_do_disco_da_instalacao(self):
        """**A VERSAO NAO MORA NO SCRIPT.** Quem copia os arquivos carimba o
        `VERSAO.txt`, e e ele que diz o que acabou de chegar — escrever a versao aqui
        dentro seria o carimbo que mente de novo, agora sobre a rotina que existe para
        pegar o carimbo que mente."""
        with TemporaryDirectory() as td:
            (Path(td) / "VERSAO.txt").write_text("9.9.9\n", encoding="utf-8")
            r = subprocess.run(
                [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COMPONENTE),
                 "-Acao", "Subir", "-InstallDir", td, "-DataDir", td,
                 "-TaskName", self.TAREFA_QUE_NAO_EXISTE, "-Port", str(self.PORTA_LIVRE),
                 "-EsperaSegundos", "2"],
                capture_output=True, text=True, timeout=90,
                encoding="utf-8", errors="replace")
            self.assertIn("versao instalada: 9.9.9", r.stdout, r.stdout + r.stderr)

    @unittest.skipUnless(WINDOWS, "o agendador e do Windows")
    def test_a_falta_do_componente_nao_deixa_o_cmd_copiar(self):
        """O `.cmd` confere que o componente existe ANTES de chamar: sem ele nao ha
        quem pare o servico, e seguir adiante copiaria por baixo de um servidor vivo."""
        cmd = _ler_atualizador()
        self.assertIn('if not exist "%REINICIO%"', cmd)
        self.assertIn("nao encontrei o componente que para e sobe o servico", cmd)

    @unittest.skipUnless(WINDOWS, "a porta e o netstat sao do Windows")
    def test_quem_esta_na_porta_e_visto_mesmo_sem_elevacao(self):
        """**O DEFEITO MEDIDO, E NAO A PROSA QUE O EXPLICA** — 15/09/2026, no mesmo dia.

        O `Get-NetTCPConnection` devolve LISTA VAZIA numa sessao sem elevacao, e o
        `netstat` mostra a mesma porta ocupada no mesmo instante. Enquanto o netstat era
        o plano B do `catch`, ele nunca era consultado nesse caso, e a funcao respondia
        "porta livre" com o servidor VIVO — o engano que deixa a copia comecar por cima
        do servidor antigo, sem um aviso em lugar nenhum.

        Aqui a deteccao e medida com um processo ouvindo de verdade, e SEM ELEVAR NADA.
        O ouvinte e um python de mentira, e o `shell=True` que o lanca nao e enfeite: a
        rotina mata a arvore do PAI de quem tem a porta, e sem esse degrau o pai seria o
        proprio processo da suite no dia em que `sys.executable` nao fosse um lancador.

        **E O QUE SE AFIRMA AQUI E O QUE SE MEDIU, nao o PID que eu supunha ser o certo.**
        A primeira versao deste teste exigia `parei o PID {crianca.pid}` — o `cmd.exe` do
        `shell=True` — e ficou vermelha com a rotina CERTA: quem estava na porta era o
        interpretador de verdade (o `runtime\\Scripts\\python.exe` deste projeto e um
        LANCADOR, que cria um filho e espera), e o `cmd` fica acima na arvore e nunca e
        alvo. O PID de mentira era meu.
        """
        with TemporaryDirectory() as td:
            td = Path(td)
            ouvinte = td / "ouvinte_de_ensaio.py"
            portfile = td / "porta.txt"
            ouvinte.write_text(
                "import pathlib, socket, sys, time\n"
                "s = socket.socket()\n"
                "s.bind(('127.0.0.1', 0))\n"
                "s.listen(5)\n"
                "pathlib.Path(sys.argv[1]).write_text(str(s.getsockname()[1]))\n"
                "time.sleep(120)\n",
                encoding="utf-8")
            crianca = subprocess.Popen(f'"{sys.executable}" "{ouvinte}" "{portfile}"',
                                       shell=True)
            try:
                porta = ""
                for _ in range(60):
                    if portfile.is_file():
                        porta = portfile.read_text(encoding="utf-8").strip()
                        break
                    time.sleep(0.25)
                self.assertTrue(porta.isdigit(), "o ouvinte de ensaio nao subiu")
                r = subprocess.run(
                    [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COMPONENTE),
                     "-Acao", "Parar", "-InstallDir", str(td), "-DataDir", str(td),
                     "-TaskName", self.TAREFA_QUE_NAO_EXISTE, "-Port", porta,
                     "-EsperaParaLiberar", "5"],
                    capture_output=True, text=True, timeout=150,
                    encoding="utf-8", errors="replace")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                #   Sem ninguem para parar, a saida e so "Porta X livre." — logo a
                #   presenca de um "parei o PID" e a prova de que quem estava nela foi
                #   visto. E o "livre." nao pode vir ANTES: e esse o lado perigoso,
                #   porque "livre" nao gera aviso.
                self.assertIn("parei o PID", r.stdout,
                              "a rotina nao viu quem estava na porta: " + r.stdout)
                antes = r.stdout.split("parei o PID")[0]
                self.assertNotIn("livre.", antes,
                                 "a rotina disse 'porta livre' com alguem ouvindo nela")
                # E o fim medido: a porta ficou mesmo livre depois da parada.
                with socket.socket() as sonda:
                    sonda.settimeout(5)
                    self.assertNotEqual(sonda.connect_ex(("127.0.0.1", int(porta))), 0,
                                        "a porta continuou ocupada depois da parada")
            finally:
                try:
                    crianca.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()

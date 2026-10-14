"""A ATUALIZACAO QUE NAO CONSEGUE SE APLICAR PRECISA DIZER ISSO ANTES — E NAO DEPOIS.

MEDIDO EM 15/09/2026, no servidor: a tela de atualizacoes oferecia o botao, o
administrador digitava a senha, o sistema criava o backup, marcava a aprovacao, parava o
servico — e o `robocopy` morria com **«Acesso negado.»**, treze caracteres, sem dizer
qual pasta nem o que fazer. A tela seguia dizendo que atualizava (`last_result.json` de
09/09 as 18h33), o log dizia acesso negado, e o balcao tinha caido no meio do caminho.

A pergunta «esta instalacao consegue aplicar sozinha?» era respondida por dois sinais que
nada provam sobre permissao — **estar no Windows** e **existir o `install.json`** —, e os
dois eram verdade naquele computador. O que faltava medir era a unica coisa que importa:
**esta conta pode gravar na pasta do programa?**

Estes testes guardam as medidas que fecham isso:

 1. a regua RECUSA quando nao se pode gravar — com a negacao de permissao de verdade, e
    nao com um duble do sistema de arquivos;
 2. a regua ACEITA quando se pode, e nao deixa lixo da propria medicao na pasta;
 3. a regua recusa quando o programa que roda NAO e o da instalacao — esse caso aplicaria
    a atualizacao na pasta errada e **relataria sucesso**;
 4. a tela e a rota perguntam a MESMA regua (duas reguas divergem no primeiro conserto);
 5. o `ps1` pergunta antes de parar o servico, e nao deixa programa de fora derrubar o
    script com a mensagem crua dele;
 6. o `.cmd` LEVA o `ps1` novo — que era a metade invisivel: **a correcao do atualizador
    viajava dentro da atualizacao que o atualizador nao conseguia aplicar**;
 7. a montagem da pasta de preparacao NAO leva sobra de quem programa (`tmp`, `output`,
    `dist`, `build`) — e a lista que decide isso e UMA so, a mesma do empacotador. Elas
    ja divergiam, e a divergencia tinha consequencia: `shutil.copytree` PERCORRE o que
    copia, e uma sobra ilegivel derruba a montagem inteira;
 8. o `.cmd` deixou de copiar POR LISTA (`*.py`, `templates\*.html`, ...) e passou a
    espelhar a pasta com as exclusoes do empacotador. Medido em 15/09/2026: a lista
    estava **25 arquivos atras** — `patches_natureza_averbacao.json`,
    `schemas/cargaRegistrosCompleto.xsd`, os 15 de `tools\`, o `pytest.ini` e os `.md`
    da raiz. O pacote `.cgu` levava todos; quem ficava para tras era o `.cmd`, e sem
    erro em lugar nenhum. Agora `PYRT` e definido no alto porque ele roda a conferencia.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
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
USUARIO = os.environ.get("USERNAME") or os.environ.get("USER") or ""


class ReguaDePermissaoTests(unittest.TestCase):
    """A medicao em si, contra o sistema de arquivos de verdade."""

    def test_pode_escrever_aceita_pasta_comum(self):
        from update_manager import pode_escrever_na_instalacao

        if not WINDOWS:
            self.skipTest("a pasta do programa e uma ideia de Windows")
        with TemporaryDirectory() as td:
            pode, motivo = pode_escrever_na_instalacao(Path(td))
            self.assertTrue(pode, motivo)
            self.assertEqual(motivo, "")
            # E NADA FICA NA PASTA: a medicao cria um arquivo e o apaga. Deixar um
            # `.teste_de_escrita_*.tmp` na pasta do programa seria sujeira que alguem
            # encontra meses depois e nao sabe de onde veio.
            self.assertEqual(list(Path(td).iterdir()), [])

    @unittest.skipUnless(WINDOWS, "negar permissao de pasta e do Windows")
    def test_recusa_a_pasta_onde_esta_conta_nao_pode_gravar(self):
        """**O CASO REAL, E NAO UM DUBLE.** A negacao e feita pelo sistema: a conta
        perde o direito de gravar naquela pasta, e a regua tem de perceber. Duble de
        sistema de arquivos mediria a minha suposicao, que e o que esta passando."""
        from update_manager import pode_escrever_na_instalacao

        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            travada = Path(td) / "instalacao"
            travada.mkdir()
            negar = subprocess.run(
                ["icacls", str(travada), "/deny", f"{USUARIO}:(OI)(CI)(W)"],
                capture_output=True, text=True,
            )
            self.assertEqual(negar.returncode, 0, negar.stderr or negar.stdout)
            try:
                pode, motivo = pode_escrever_na_instalacao(travada)
                self.assertFalse(pode, "a regua disse que da para gravar onde nao da")
                self.assertIn(str(travada), motivo)
                self.assertIn(USUARIO, motivo)
                # A FRASE TEM DE DIZER POR ONDE SE APLICA. Recusa sem saida faz quem le
                # concluir que a atualizacao nao existe — e ela existe: e o `.cmd`.
                self.assertIn("ATUALIZAR_SISTEMA.cmd", motivo)
                # E a negacao era de verdade: escrever ali falha mesmo.
                with self.assertRaises(OSError):
                    (travada / "prova.tmp").write_bytes(b"")
            finally:
                subprocess.run(
                    ["icacls", str(travada), "/remove:d", USUARIO],
                    capture_output=True, text=True,
                )

    @unittest.skipUnless(WINDOWS, "comparar caminho do Windows e do Windows")
    def test_o_mesmo_caminho_escrito_de_dois_jeitos_e_o_mesmo(self):
        """`C:\\Program Files\\CartorioGestao` e `c:/program files/cartoriogestao/` sao a
        mesma pasta, e comparar as duas strings diria que nao sao — **duas reguas para a
        mesma medida**. O `install.json` desta casa guarda `C:\\Program Files\\...` e o
        `sys.executable` devolve o caminho como o Windows o deu: sem normalizar, a regua
        recusaria a instalacao de verdade dizendo que ela nao e ela mesma."""
        from update_manager import _mesmo_caminho

        self.assertTrue(_mesmo_caminho(r"C:\Program Files\CartorioGestao",
                                       "c:/program files/cartoriogestao/"))
        self.assertFalse(_mesmo_caminho(r"C:\Program Files\CartorioGestao",
                                        r"C:\Users\fulano\Downloads\CartorioGestao"))

    def test_recusa_quando_o_programa_roda_de_outra_pasta(self):
        """**APLICAR DAQUI TROCARIA OS ARQUIVOS DA PASTA ERRADA E RELATARIA SUCESSO** —
        carimbo que mente no pior lugar, porque quem le a tela conclui que o servidor
        subiu. O `install.json` diz qual pasta e a instalacao; o resto e outra copia."""
        from update_manager import pode_aplicar_sozinho

        if not WINDOWS:
            self.skipTest("sem instalacao convencional nao ha o que comparar")
        with TemporaryDirectory() as td:
            dados = Path(td) / "dados"
            dados.mkdir()
            instalada = Path(td) / "instalada"
            instalada.mkdir()
            copia = Path(td) / "copia"
            copia.mkdir()
            (dados / "install.json").write_text(
                json.dumps({"install_dir": str(instalada)}), encoding="utf-8",
            )
            pode, motivo = pode_aplicar_sozinho(dados, copia)
        self.assertFalse(pode)
        self.assertIn(str(instalada), motivo)
        self.assertIn(str(copia), motivo)

    def test_aceita_quando_e_a_instalacao_e_da_para_gravar(self):
        from update_manager import pode_aplicar_sozinho

        if not WINDOWS:
            self.skipTest("sem instalacao convencional nao ha o que comparar")
        with TemporaryDirectory() as td:
            dados = Path(td) / "dados"
            dados.mkdir()
            instalada = Path(td) / "instalada"
            instalada.mkdir()
            (dados / "install.json").write_text(
                json.dumps({"install_dir": str(instalada)}), encoding="utf-8",
            )
            pode, motivo = pode_aplicar_sozinho(dados, instalada)
        self.assertTrue(pode, motivo)

    def test_sem_install_json_a_recusa_diz_que_nao_da_para_saber_qual_e_a_pasta(self):
        from update_manager import pode_aplicar_sozinho

        if not WINDOWS:
            self.skipTest("sem instalacao convencional nao ha o que procurar")
        with TemporaryDirectory() as td:
            dados = Path(td) / "dados"
            dados.mkdir()
            pode, motivo = pode_aplicar_sozinho(dados, Path(td))
        self.assertFalse(pode)
        self.assertIn("install.json", motivo)
        self.assertIn("ATUALIZAR_SISTEMA.cmd", motivo)


class AsDuasTelasPerguntamAMesmaReguaTests(unittest.TestCase):
    """A TELA E A ROTA NAO PODEM TER REGUAS DIFERENTES.

    Se a tela dissesse «disponivel» e a rota recusasse, o oficial clicaria num botao que
    nao existe para ele — e a frase de recusa chegaria depois de ele ter decidido. Foi
    exatamente o que aconteceu: a tela dizia que sim por dois sinais, e o `robocopy`
    dizia que nao treze caracteres depois.
    """

    def test_a_tela_e_a_rota_chamam_o_update_manager(self):
        texto = (RAIZ / "app.py").read_text(encoding="utf-8")
        self.assertIn("pode_aplicar_sozinho(data_dir)", texto)
        # E NAO SOBROU A CONDICAO ANTIGA, que respondia «sim» sem medir permissao.
        self.assertNotIn('(data_dir / "install.json").exists()', texto)
        # E O LANCADOR CONFERE UMA ULTIMA VEZ: depois dele nao ha mais quem recuse o
        # pedido — o servico e parado e os arquivos sao trocados.
        gerenciador = (RAIZ / "update_manager.py").read_text(encoding="utf-8")
        self.assertIn("pode_aplicar_sozinho(data_dir, install_dir)", gerenciador)


class OsScriptsDaAtualizacaoTests(unittest.TestCase):
    """O `ps1` e o `.cmd` — os dois pedacos que estavam quebrados no servidor."""

    def ps1(self) -> str:
        return (RAIZ / "installer" / "aplicar_atualizacao.ps1").read_text(encoding="utf-8")

    def cmd(self) -> str:
        # O `.cmd` mora em SERVIDOR\, ao lado da pasta do programa.
        return _ler_atualizador()

    def test_o_ps1_pergunta_a_permissao_antes_de_parar_o_servico(self):
        """**A ORDEM E O CONSERTO.** Perguntar depois de parar o servico nao serve de
        nada: o balcao ja caiu, e a recusa vira um segundo defeito em cima do primeiro.
        A medicao da permissao tem de vir antes de marcar APPLYING e antes de mexer em
        qualquer coisa.

        E A PARADA E A CHAMADA DA ROTINA, e nao uma linha escrita aqui — 15/09/2026.
        Este teste procurava `Disable-ScheduledTask -TaskName $TaskName`, que deixou
        de existir como CODIGO neste arquivo; a unica ocorrencia ficou sendo a de um
        comentario que explica por que ela saiu. **O teste passaria lendo a propria
        prosa** — decima segunda vez que um varredor desta casa mede a palavra e nao
        o codigo. Agora ele ancora na chamada de verdade."""
        texto = self.ps1()
        sonda = texto.find("WriteAllText($pista")
        marcar = texto.find("MetaState 'APPLYING'")
        parar = texto.find("$parada=ReiniciarServico 'Parar'")
        self.assertGreater(sonda, -1, "o ps1 nao mede a permissao da pasta")
        self.assertGreater(marcar, -1)
        self.assertGreater(parar, -1, "o ps1 nao chama a rotina que para o servico")
        self.assertLess(sonda, marcar, "mede a permissao depois de dizer que esta aplicando")
        self.assertLess(sonda, parar, "mede a permissao depois de parar o servico")
        # E NAO SOBROU PARADA CRUA. `Stop-Process -Id $ParentPid` matava o lancador do
        # venv e deixava o filho — quem tem o socket — vivo; era ele o servidor antigo
        # que continuava respondendo 200.
        #
        #   **A VARREDURA E SOBRE O CODIGO, SEM COMENTARIO** — corrigido em 15/09/2026,
        #   no mesmo minuto em que este teste ficou vermelho por isso. O comentario da
        #   funcao `ReiniciarServico` cita as duas linhas justamente para dizer que elas
        #   sairam; um `assertNotIn` sobre o arquivo inteiro passava a ler a propria
        #   explicacao. E a decima terceira vez que um varredor desta casa mede a
        #   palavra em vez do codigo — e a segunda dentro deste mesmo teste.
        codigo = "\n".join(linha for linha in texto.splitlines()
                           if not linha.strip().startswith("#"))
        self.assertNotIn("Stop-Process -Id $ParentPid", codigo)
        self.assertNotIn("Disable-ScheduledTask -TaskName $TaskName", codigo)

    def test_a_recusa_do_ps1_diz_que_nada_mudou_e_por_onde_se_aplica(self):
        texto = self.ps1()
        self.assertIn("NADA FOI ALTERADO", texto)
        self.assertIn("use o ATUALIZAR_SISTEMA.cmd", texto)

    def test_o_ps1_nao_deixa_programa_de_fora_derrubar_o_script(self):
        """**«ERRO: Acesso negado.» era tudo o que chegava ao log.** Com
        `$ErrorActionPreference='Stop'`, o stderr do `robocopy` vira excecao e a mensagem
        crua dele — sem dizer qual pasta, qual copia, nem o que fazer — e a que fica no
        `last_result.json`. O que decide se a copia deu certo e o CODIGO DE SAIDA, e e
        ele que passa a ser lido."""
        texto = self.ps1()
        self.assertIn("function Rodar", texto)
        self.assertNotIn("& robocopy.exe", texto, "sobrou chamada crua de robocopy")
        self.assertIn("Rodar \"pip install", texto, "o pip continua sem passar pelo Rodar")
        # e a frase escrita por quem chama diz o que estava sendo feito
        self.assertIn("Copia de seguranca para rollback", texto)

    def test_o_cmd_leva_a_pasta_installer(self):
        """**A METADE INVISIVEL DO DEFEITO.** Medido em 15/09/2026: os catorze arquivos
        de `installer` no servidor sao todos de 13/08, byte a byte os da instalacao — o
        `aplicar_atualizacao.ps1` de 01/09 (que confere hash, testa saude e faz rollback)
        nunca chegou la. E nao havia como sair disso por dentro: quem roda o `.cgu` e a
        tela do sistema, que usa justamente esse arquivo."""
        texto = self.cmd()
        linha = self._linha_da_copia(texto)
        # A PASTA NAO PODE ESTAR NA LISTA DE EXCLUSAO: e isso, e nao um `if exist`
        # separado, que a deixa viajar agora que a copia e uma so.
        self.assertNotIn("installer", self._excluidas(linha))
        # E CONFERE QUE CHEGOU IGUAL, e nao so que chegou: um ps1 velho na pasta e
        # exatamente o que fez a tela mentir dizendo que atualizava.
        self.assertIn("fc /b", texto)
        self.assertIn("aplicar_atualizacao.ps1", texto)

    # A COPIA E UMA SO, E NAO UMA LISTA ESCRITA A MAO. 15/09/2026.
    #
    #   O `.cmd` copiava `*.py`, `templates\*.html`, `static`, `modelos`,
    #   `DOCUMENTACAO`, `installer` e `VERSAO.txt` — e a lista tinha **25 arquivos
    #   de defasagem** contra a instalacao do servidor, medido com a regua do
    #   proprio pacote: `patches_natureza_averbacao.json`, `schemas/*.xsd`, os 15
    #   de `tools\`, o `pytest.ini`, os `.md` da raiz. O pacote `.cgu` levava
    #   todos; quem ficava para tras era o `.cmd`, e sem erro em lugar nenhum —
    #   o sistema subia inteiro e o recurso que lia o arquivo faltante falhava
    #   depois, no balcao.
    #
    #   **Cada defeito consertado ali dentro — o `.css` que virou `static` inteira,
    #   o `VERSAO.txt` que ficou de fora, os documentos que nao viajavam, a pasta
    #   `installer` do «Acesso negado» — foi um remendo NA LISTA.** Agora e a pasta
    #   inteira (`/S`), com as exclusoes do empacotador.
    def _linha_da_copia(self, texto: str) -> str:
        """A unica linha de copia do programa, com as continuacoes ja juntadas."""
        juntas = texto.replace("^\r\n", " ").replace("^\n", " ").replace("^", " ")
        linhas = [l for l in juntas.splitlines()
                  if l.strip().startswith("robocopy") and '"%FONTE%"' in l
                  and '"%PROG%"' in l]
        self.assertEqual(len(linhas), 1,
                         "a copia do programa deixou de ser uma so:\n" + "\n".join(linhas))
        return linhas[0]

    def _excluidas(self, linha: str) -> list:
        """O que a linha manda EXCLUIR de pasta (`/XD`)."""
        if "/XD" not in linha:
            return []
        cauda = linha.split("/XD", 1)[1]
        if "/XF" in cauda:
            cauda = cauda.split("/XF", 1)[0]
        return cauda.split()

    def test_a_copia_do_cmd_e_a_pasta_inteira_e_nao_uma_lista(self):
        """**A LISTA MORREU.** Copiar por lista obriga a lembrar de acrescentar
        arquivo novo a ela, e ninguem lembra: a ultima versao dela estava 25
        arquivos atras. `/S` copia a arvore, e o que nao deve ir sai por exclusao —
        a mesma do empacotador."""
        linha = self._linha_da_copia(self.cmd())
        self.assertIn("/S", linha.split("/XD", 1)[0],
                      "a copia deixou de ser recursiva da raiz")
        # E NAO PODE VOLTAR A FILTRAR POR EXTENSAO: era isso que deixava
        # `patches_natureza_averbacao.json` e os `.xsd` para tras.
        self.assertNotIn("*.py", linha.split("/XD", 1)[0])
        self.assertNotIn("*.html", linha.split("/XD", 1)[0])

    def test_as_pastas_excluidas_pelo_cmd_sao_as_do_empacotador(self):
        """**A REGUA DO PACOTE, E NAO UMA SEGUNDA.** Se o `.cmd` excluir pasta que o
        empacotador leva, o servidor fica sem ela por este caminho; se excluir menos,
        sobra de quem programa entra na pasta do balcao. As duas listas respondem a
        mesma pergunta, e por isso sao a mesma — como ja o sao o `update_manager` e o
        `tools/criar_atualizacao.py`."""
        import update_manager

        excluidas = set(self._excluidas(self._linha_da_copia(self.cmd())))
        self.assertEqual(excluidas, set(update_manager.PASTAS_IGNORADAS_NA_COPIA),
                         "a lista do .cmd divergiu da do empacotador")

    def test_o_cmd_confere_o_que_chegou_com_a_regua_do_pacote(self):
        """**E CONFERE, EM VEZ DE SUPOR.** Havia tres conferencias escritas a mao
        aqui — o `lupa.js`, a pasta `DOCUMENTACAO` e o `fc /b` do `ps1` —, todas
        certas e todas cobrindo so o ultimo defeito que cada uma tinha visto. A
        lista das conferencias envelhecia junto com a lista da copia.

        Agora quem confere e o `tools/conferir_atualizacao.py`, que importa a regua
        de `criar_atualizacao` e diz o que FALTA, o que DIFERE e o que SOBRA."""
        texto = self.cmd()
        self.assertIn("tools\\conferir_atualizacao.py", texto)
        self.assertIn("conferir_atualizacao.py", texto)
        # E ele RODA, e nao so aparece escrito — a chamada usa o python do servidor.
        self.assertIn('"%PYRT%"', texto)
        # O `PYRT` tem de estar definido ANTES da conferencia, senao a variavel
        # vazia faz a linha nao rodar e a conferencia nao acontece — calada.
        self.assertLess(texto.find('set "PYRT="'), texto.find("conferir_atualizacao.py"))


class AMontagemNaoLevaSobraDeQuemProgramaTests(unittest.TestCase):
    """**AS DUAS LISTAS DE PASTAS IGNORADAS JA ESTAVAM DIVERGINDO.**

    Medido em 15/09/2026: o empacotador (`tools/criar_atualizacao.py`) excluia `output`,
    `tmp`, `dist`, `build` e `dist_unico`; a montagem da pasta de preparacao
    (`update_manager`) excluia so `runtime`, `updates` e `tests`. **Duas reguas para a
    mesma pergunta** — e a divergencia nao era teorica:

    `shutil.copytree` PERCORRE o que copia. Uma sobra ilegivel derruba a montagem
    inteira, e a mensagem que chegava era a **lista de tuplas** do `shutil.Error`. Foi o
    que aconteceu nesta arvore: uma pasta de teste com permissao negada fez «validar e
    preparar» falhar. O pacote nunca levou `tmp/`; a preparacao levava.
    """

    def test_as_duas_listas_sao_a_mesma_lista_e_nao_duas_iguais(self):
        """**`assertIs`, e nao `assertEqual`.** Duas listas iguais hoje divergem na
        tarde em que alguem editar uma — que e exatamente o que aconteceu. A regua do
        empacotador tem de SER a do sistema, e nao uma copia que por acaso confere."""
        import update_manager

        modulo = self._ferramenta()
        self.assertIs(modulo.EXCLUDE_DIRS, update_manager.PASTAS_IGNORADAS_NA_COPIA)

    def test_a_lista_ainda_tem_o_que_a_medicao_exigiu(self):
        """A igualdade sozinha nao guarda nada: agora que uma deriva da outra, ela e
        verdadeira mesmo que alguem ESVAZIE a lista. O que a medicao fixou sao estas
        seis — as cinco em que as listas divergiam e a `tests`, que ja estava la."""
        import update_manager

        for pasta in ("tmp", "output", "dist", "build", "dist_unico", "tests"):
            self.assertIn(pasta, update_manager.PASTAS_IGNORADAS_NA_COPIA)

    def test_a_montagem_nao_leva_a_pasta_tmp(self):
        """O caso real, com a montagem de verdade: a pasta de preparacao recebe o
        programa e nenhuma sobra."""
        from update_manager import inspect_staged

        with TemporaryDirectory() as td:
            base = Path(td)
            instalada = base / "instalada"
            instalada.mkdir()
            (instalada / "app.py").write_text('VERSION = "9.9.9"\n', encoding="utf-8")
            (instalada / "VERSAO.txt").write_text("9.9.9", encoding="utf-8")
            (instalada / "tela.html").write_text("<p>oi</p>", encoding="utf-8")
            for sobra in ("tmp", "output", "dist", "build", "__pycache__", "runtime"):
                (instalada / sobra).mkdir()
                (instalada / sobra / "sobra.txt").write_text("x", encoding="utf-8")

            preparacao = base / "preparacao"
            preparacao.mkdir()
            (preparacao / "payload").mkdir()
            (preparacao / "_update_meta.json").write_text(
                json.dumps({
                    "state": "STAGED",
                    "manifest": {"version": "9.9.9"},
                    "checked_files": [],
                    "delete": [],
                }),
                encoding="utf-8",
            )

            inspecao = inspect_staged(preparacao, instalada)

            candidato = preparacao / "candidate"
            self.assertTrue((candidato / "app.py").is_file())
            self.assertTrue((candidato / "tela.html").is_file())
            for sobra in ("tmp", "output", "dist", "build", "__pycache__", "runtime"):
                self.assertFalse(
                    (candidato / sobra).exists(),
                    f"a pasta de preparacao levou {sobra}/ da arvore de quem programa",
                )
            # E o candidato continua um candidato valido: a montagem que nao leva sobra
            # nao pode ser a que nao leva programa.
            self.assertTrue(inspecao["ok"], inspecao["problems"])

    def test_a_copia_que_falha_volta_como_frase_e_nao_como_lista_de_tuplas(self):
        """**O `shutil.Error` carrega uma LISTA**, e ela ia inteira para o `flash`:
        `[('C:\\\\...', 'C:\\\\...', '[WinError 5] Acesso negado')]`. Quem clicasse em
        «validar e preparar» lia isso — e a pergunta que ele tem de responder nao e
        tecnica: **quebrou o sistema, ou so nao deu para ler um arquivo?**

        Aqui o `copytree` e trocado por um que estoura, mas o ERRO e o de verdade, com a
        forma de verdade do `shutil` (`Error([(origem, destino, motivo), ...])`): e ele
        que o meu codigo tem de saber ler.
        """
        import shutil as _shutil
        from unittest.mock import patch

        from update_manager import UpdateError, inspect_staged

        with TemporaryDirectory() as td:
            base = Path(td)
            instalada = base / "instalada"
            instalada.mkdir()
            (instalada / "app.py").write_text('VERSION = "9.9.9"\n', encoding="utf-8")
            preparacao = base / "preparacao"
            preparacao.mkdir()
            (preparacao / "payload").mkdir()
            (preparacao / "_update_meta.json").write_text(
                json.dumps({"state": "STAGED", "manifest": {"version": "9.9.9"}}),
                encoding="utf-8",
            )
            falha = _shutil.Error([(
                str(instalada / "certidao.pdf"),
                str(preparacao / "candidate" / "certidao.pdf"),
                "[WinError 5] Acesso negado",
            )])
            with patch("update_manager.shutil.copytree", side_effect=falha):
                with self.assertRaises(UpdateError) as erro:
                    inspect_staged(preparacao, instalada)

        # O `UpdateError` e o que a rota sabe transformar em frase de tela; o
        # `shutil.Error` NAO era apanhado por ninguem como erro de regra.
        parada = str(erro.exception)
        self.assertIn("certidao.pdf", parada, "a frase nao diz em que arquivo parou")
        self.assertIn("NADA mudou", parada)
        self.assertNotIn("[('", parada, "a lista de tuplas voltou para a tela")
        # E o motivo continua no texto: sem ele, quem administra nao tem por onde
        # comecar a procurar.
        self.assertIn("negado", parada)

    def _ferramenta(self):
        """Carrega `tools/criar_atualizacao.py` sem executar o `main()` dele."""
        import importlib.util

        caminho = RAIZ / "tools" / "criar_atualizacao.py"
        spec = importlib.util.spec_from_file_location("criar_atualizacao_medido", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo


if __name__ == "__main__":
    unittest.main()

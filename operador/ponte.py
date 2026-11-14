"""A PONTE DO SUPERUSUÁRIO — recebe o pedido do oficial (texto, áudio, PDF,
foto), acorda o operador neste servidor e devolve a resposta. Ninguém precisa
entrar no servidor para pedir.

DUAS PORTAS CAEM AQUI, NUMA FILA SÓ (12/11/2026, o oficial: «integração
automatizada», e depois «não só pelo Telegram, também pelo sistema»):

    - o TELEGRAM: um bot por servidor, que só atende o usuário cadastrado em
      `OPERADOR_TELEGRAM_USUARIO`, em conversa privada (e, se houver
      `OPERADOR_FRASE`, só depois da frase);
    - a TELA DO SISTEMA (`/agente/superusuario`): ela deixa o pedido na
      bandeja (`bandeja.py`), e a ponte o colhe.

A terceira porta, o app do Claude, não passa pela ponte: o app abre o Claude
Code direto no posto (`posto.py`), com a mesma guarda e o mesmo diário.

COMO É POR DENTRO
    - LEVE: parada, a ponte é um processo Python esperando a rede e olhando a
      bandeja. O operador (Claude Code sem tela) só existe enquanto atende um
      pedido, e termina. O que carrega os módulos da casa (fechar o relatório,
      transcrever áudio) roda em processo à parte, que nasce e morre.
    - SÓ SAÍDA: a ponte liga para `api.telegram.org`; nada entra.
    - UM PEDIDO POR VEZ: os que chegam no meio esperam na fila, e a fila
      sobrevive ao reinício da ponte.
    - VÁRIAS MENSAGENS, UM PEDIDO: o álbum de fotos e as mensagens mandadas em
      seguida viram um pedido só (espera de 2,5 s).
    - NÃO FICA MUDA: enquanto o operador trabalha, o Telegram mostra
      «digitando» e, a cada dois minutos, o que ele está fazendo.

A CONFIGURAÇÃO fica em `<dados>/operador/operador.cred` (ver
`operador_cred.exemplo`). O token do Telegram e a frase NÃO vão para o
ambiente do operador.

NO TELEGRAM
    /novo      esquece a conversa e começa outra
    /estado    o que está rodando, a fila e as pendências
    /parar     interrompe o pedido em andamento
    /diario    os últimos pedidos, de todas as portas
    /lembrar   guarda um fato na memória do operador
    /abrir     abre com a frase (se houver frase) · /trancar fecha
    CONFIRMO   libera, por 10 minutos, o que não tem volta (a guarda cobra)

Só a biblioteca padrão.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import bandeja as BANDEJA  # noqa: E402
import conhecimento as CONH  # noqa: E402
import intervencao as INT  # noqa: E402
import posto as POSTO  # noqa: E402

MODELO_PADRAO = "claude-opus-5-5"
ESFORCO_PADRAO = "high"
LIMITE_DA_MENSAGEM = 3900              # o Telegram aceita 4096 por mensagem
LIMITE_DO_ARQUIVO = 20 * 1024 * 1024   # o que um bot consegue baixar
LIMITE_DO_ENVIO = 50 * 1024 * 1024     # o que um bot consegue enviar
MINUTOS_POR_PEDIDO = 60
ESPERA_DO_LOTE = 2.5                   # segundos de silêncio que fecham um pedido
AVISO_A_CADA = 120                     # segundos entre os «ainda trabalhando»
HORAS_DA_CONVERSA = 12                 # parada mais que isto, a conversa recomeça
HORAS_DA_FRASE = 12
#: Com que código a ponte sai quando o programa dela muda no disco. Diferente
#: de zero de propósito: é o que faz a tarefa agendada do Windows relançá-la.
CODIGO_DE_REINICIO = 3

AJUDA = (
    "Mande o pedido em texto ou áudio, com PDF ou foto se precisar.\n"
    "/novo — começa outra conversa\n"
    "/estado — o que está rodando e o que está pendente\n"
    "/parar — interrompe o pedido em andamento\n"
    "/diario — os últimos pedidos, de todas as portas\n"
    "/lembrar <fato> — guarda na memória do operador\n"
    "CONFIRMO — libera por 10 minutos o que não tem volta")

_PAROU = {
    "error_max_turns": "Cheguei ao limite de passos deste pedido.",
    "error_max_budget_usd": "Cheguei ao teto de gasto deste pedido.",
    "error_during_execution": "O operador parou com um erro no meio.",
}


def registrar(texto: str) -> None:
    linha = f"{datetime.now().isoformat(timespec='seconds')} {texto}"  # noqa: DTZ005
    try:
        with (INT.base() / "ponte.log").open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")
    except OSError:
        pass
    print(linha, flush=True)


# ------------------------------------------------------------- funções soltas

def ler_configuracao(caminho: Path | None = None) -> dict[str, str]:
    """As linhas CHAVE=valor do `operador.cred`."""
    return BANDEJA.ler_configuracao(caminho or (INT.base() / "operador.cred"))


nome_seguro = BANDEJA.nome_seguro


def partes_da_resposta(texto: str, limite: int = LIMITE_DA_MENSAGEM) -> list[str]:
    """Corta a resposta em mensagens, de preferência no fim de uma linha."""
    texto = (texto or "").strip() or "(sem texto)"
    partes = []
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = limite
        partes.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    partes.append(texto)
    return partes


def pagamento(config: dict[str, str], *, chave_da_casa=None) -> tuple[str, dict[str, str], list[str]]:
    """Como o operador fala com a Anthropic: (a frase, o que entra no ambiente
    dele, o que sai). A ASSINATURA GANHA DA API quando as duas estão ditas — o
    oficial pediu «sem gastar a API» (12/11/2026), e a chave no ambiente
    faria o Claude Code cobrar por ela sem avisar."""
    token = (config.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()
    if token:
        return "assinatura (token)", {"CLAUDE_CODE_OAUTH_TOKEN": token}, ["ANTHROPIC_API_KEY"]
    if (config.get("OPERADOR_ASSINATURA") or "").strip() == "1":
        return "assinatura (login desta conta)", {}, ["ANTHROPIC_API_KEY"]
    chave = (config.get("ANTHROPIC_API_KEY") or "").strip()
    if chave:
        return "API (chave do operador)", {"ANTHROPIC_API_KEY": chave}, []
    if (config.get("OPERADOR_CHAVE_DA_CASA") or "").strip() == "1" and chave_da_casa:
        chave = (chave_da_casa() or "").strip()
        if chave:
            return "API (chave do agente da casa)", {"ANTHROPIC_API_KEY": chave}, []
    return "", {}, []


def comando_do_operador(config: dict[str, str], sessao: str | None) -> list[str]:
    """A linha de comando do Claude Code sem tela. O pedido vai pela entrada
    padrão e a resposta vem em eventos (`stream-json`), para a ponte saber o
    que ele está fazendo. `dontAsk` + lista de ferramentas: nada fica
    esperando alguém aprovar na tela (não há tela). As instruções, a guarda e
    os ganchos NÃO estão aqui: estão no posto, que é a pasta onde ele roda."""
    comando = [
        config.get("OPERADOR_CLAUDE") or shutil.which("claude") or "claude",
        "-p", "--output-format", "stream-json", "--verbose",
        "--model", config.get("OPERADOR_MODELO") or MODELO_PADRAO,
        "--max-turns", config.get("OPERADOR_MAX_TURNOS") or "150",
        "--permission-mode", "dontAsk",
        "--allowedTools", ",".join(POSTO.ferramentas()),
    ]
    esforco = (config.get("OPERADOR_ESFORCO") or ESFORCO_PADRAO).strip().lower()
    if esforco and esforco != "padrao":
        comando += ["--effort", esforco]
    if (config.get("OPERADOR_MODELO_RESERVA") or "").strip():
        comando += ["--fallback-model", config["OPERADOR_MODELO_RESERVA"].strip()]
    if (config.get("OPERADOR_TETO_USD") or "").strip():
        comando += ["--max-budget-usd", config["OPERADOR_TETO_USD"].strip()]
    if sessao:
        comando += ["--resume", sessao]
    return comando


def descrever(evento: dict) -> str:
    """O que o operador está fazendo, numa frase curta, a partir de um evento
    `assistant` do Claude Code. "" quando o evento não diz nada de novo."""
    blocos = (evento.get("message") or {}).get("content") or []
    if not isinstance(blocos, list):
        return ""
    for bloco in reversed(blocos):
        if not isinstance(bloco, dict) or bloco.get("type") != "tool_use":
            continue
        nome, entrada = str(bloco.get("name") or ""), bloco.get("input") or {}
        arquivo = re.split(r"[\\/]", str(entrada.get("file_path") or ""))[-1]
        if nome in ("Bash", "PowerShell"):
            return "rodando: " + " ".join(str(entrada.get("command") or "").split())[:90]
        if nome == "Read":
            return f"lendo {arquivo}"
        if nome in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            return f"editando {arquivo}"
        if nome in ("Grep", "Glob"):
            return "procurando " + str(entrada.get("pattern") or "")[:60]
        if nome == "WebSearch":
            return "pesquisando: " + str(entrada.get("query") or "")[:80]
        if nome == "WebFetch":
            return "abrindo " + str(entrada.get("url") or "")[:80]
        return f"usando {nome}"
    if any(isinstance(b, dict) and b.get("type") == "text" for b in blocos):
        return "escrevendo a resposta"
    return ""


def traduzir_erro(texto: str) -> str:
    """A recusa da Anthropic, na língua do oficial e com o que fazer."""
    baixo = (texto or "").lower()
    if "invalid api key" in baixo or "fix external api key" in baixo or "authentication" in baixo:
        return ("A Anthropic recusou a chave da API. Confira ANTHROPIC_API_KEY no "
                "operador.cred deste servidor.")
    if "not logged in" in baixo or "/login" in baixo or "oauth" in baixo:
        return ("O Claude Code deste servidor não está logado na sua assinatura. "
                "No servidor, rode `claude` e depois `/login`, ou gere o token com "
                "`claude setup-token` e ponha em CLAUDE_CODE_OAUTH_TOKEN.")
    if "credit balance" in baixo or "billing" in baixo:
        return ("A conta da API está sem crédito ou passou do limite de gasto. "
                "Confira em console.anthropic.com.")
    if "usage limit" in baixo or "rate limit" in baixo or "overloaded" in baixo or "529" in baixo:
        return ("A Anthropic recusou por limite de uso ou sobrecarga. Tente de novo "
                f"em alguns minutos. (Ela disse: {texto[:200]})")
    return f"O operador não conseguiu falar com a Anthropic: {texto[:400]}"


def matar(processo: Any) -> None:
    """Derruba o operador E o que ele tiver deixado rodando (o shell, o psql)."""
    pid = getattr(processo, "pid", None)
    try:
        if isinstance(pid, int) and os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        elif isinstance(pid, int) and hasattr(os, "killpg"):
            os.killpg(pid, signal.SIGKILL)
        else:
            processo.kill()
    except (OSError, ProcessLookupError):
        try:
            processo.kill()
        except Exception:  # noqa: BLE001
            pass


def assinatura_do_codigo() -> tuple | None:
    """O retrato dos programas do operador no disco (nome, hora e tamanho), ou
    None se a pasta não está inteira agora (no meio de uma troca)."""
    try:
        return tuple(sorted((a.name, a.stat().st_mtime_ns, a.stat().st_size)
                            for a in AQUI.iterdir() if a.suffix in (".py", ".md")))
    except OSError:
        return None


def _grupo_proprio() -> dict:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


# ------------------------------------------------------------------ o Telegram

class Telegram:
    def __init__(self, token: str):
        self._base = f"https://api.telegram.org/bot{token}/"
        self._arquivos = f"https://api.telegram.org/file/bot{token}/"

    def chamar(self, metodo: str, espera: int = 30, **campos: Any) -> Any:
        corpo = urllib.parse.urlencode(
            {k: v for k, v in campos.items() if v is not None}).encode()
        with urllib.request.urlopen(self._base + metodo, corpo, timeout=espera) as r:
            resposta = json.loads(r.read().decode("utf-8"))
        if not resposta.get("ok"):
            raise RuntimeError(f"Telegram recusou {metodo}: {resposta.get('description')}")
        return resposta["result"]

    def novidades(self, depois_de: int) -> list[dict]:
        return self.chamar("getUpdates", espera=70, offset=depois_de, timeout=50,
                           allowed_updates='["message"]')

    def dizer(self, conversa: int, texto: str) -> None:
        for parte in partes_da_resposta(texto):
            self.chamar("sendMessage", chat_id=conversa, text=parte)

    def agindo(self, conversa: int) -> None:
        """O «digitando…» do Telegram: dura uns 5 segundos."""
        self.chamar("sendChatAction", espera=10, chat_id=conversa, action="typing")

    def apagar(self, conversa: int, mensagem: Any) -> None:
        self.chamar("deleteMessage", espera=10, chat_id=conversa, message_id=mensagem)

    def baixar(self, file_id: str, destino: Path) -> None:
        dados = self.chamar("getFile", file_id=file_id)
        with urllib.request.urlopen(self._arquivos + dados["file_path"], timeout=120) as r, \
                destino.open("wb") as saida:
            shutil.copyfileobj(r, saida)

    def enviar_arquivo(self, conversa: int, caminho: Path) -> None:
        """Devolve um arquivo ao oficial (`sendDocument`, em multipart)."""
        limite = uuid.uuid4().hex
        nome = nome_seguro(caminho.name)
        corpo = b"".join([
            f'--{limite}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n'
            f'{conversa}\r\n'.encode(),
            f'--{limite}\r\nContent-Disposition: form-data; name="document"; '
            f'filename="{nome}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
            caminho.read_bytes(), b"\r\n", f"--{limite}--\r\n".encode()])
        pedido = urllib.request.Request(
            self._base + "sendDocument", data=corpo,
            headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
        with urllib.request.urlopen(pedido, timeout=300) as r:
            resposta = json.loads(r.read().decode("utf-8"))
        if not resposta.get("ok"):
            raise RuntimeError(f"Telegram recusou o arquivo: {resposta.get('description')}")


# ---------------------------------------------------------------------- a ponte

class Ponte:
    def __init__(self, config: dict[str, str], telegram: Any = None, *,
                 rodar_processo=subprocess.Popen, encerrar=None, ouvir=None,
                 relogio=time.time, sair=os._exit):
        self.config = config
        self.telegram = telegram
        self._popen = rodar_processo
        self._encerrar = encerrar or self._encerrar_em_processo
        self._ouvir = ouvir or self._ouvir_em_processo
        self._agora = relogio
        self._sair = sair
        self._codigo = assinatura_do_codigo()
        self._codigo_visto_em = relogio()
        self.dono = int(config.get("OPERADOR_TELEGRAM_USUARIO") or 0)
        self.frase = (config.get("OPERADOR_FRASE") or "").strip()
        self.trava = threading.RLock()
        self.fila: queue.Queue = queue.Queue()
        self.lote: dict | None = None
        self.atual: dict | None = None
        self.processo: Any = None
        self.parado = False
        self._pago: tuple | None = None
        self._colhido_em = self._agindo_em = self._publicado_em = 0.0
        self._arquivo_de_estado = INT.base() / "ponte_estado.json"
        self.estado = self._ler_estado()

    # -- o estado que sobrevive ao reinício: até onde li, a conversa, a fila
    def _ler_estado(self) -> dict:
        try:
            estado = json.loads(self._arquivo_de_estado.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            estado = {}
        return {"depois_de": 0, "sessao": None, "usada_em": 0, "aberto_ate": 0,
                **(estado if isinstance(estado, dict) else {})}

    def _gravar_estado(self) -> None:
        # Dentro da trava do começo ao fim: três linhas de execução gravam (o
        # Telegram, o relógio e o trabalhador), e o arquivo provisório é um só.
        with self.trava:
            atual = self.atual
            retrato = {**self.estado, "fila": list(self.fila.queue),
                       "em_andamento": ({k: atual[k] for k in
                                         ("numero", "porta", "conversa", "texto", "anexos", "tela")}
                                        if atual else None)}
            provisorio = self._arquivo_de_estado.with_name("ponte_estado.json.novo")
            provisorio.write_text(json.dumps(retrato, ensure_ascii=False), encoding="utf-8")
            provisorio.replace(self._arquivo_de_estado)

    def pagamento(self) -> tuple[str, dict[str, str], list[str]]:
        if self._pago is None:
            self._pago = pagamento(self.config, chave_da_casa=self._chave_da_casa)
        return self._pago

    def _chave_da_casa(self) -> str:
        try:
            feito = subprocess.run(
                [sys.executable, str(AQUI / "posto.py"), "chave-da-casa"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return feito.stdout.strip() if feito.returncode == 0 else ""

    def _publicar(self) -> None:
        """O que a tela do sistema lê: o que roda, a fila, se a ponte vive."""
        with self.trava:
            atual = self.atual
            retrato = {
                "servidor": INT.servidor(), "situacao": INT.situacao(),
                "pagamento": self.pagamento()[0], "telegram": bool(self.telegram),
                "conversa": bool(self.estado.get("sessao")),
                "rodando": ({"numero": atual["numero"], "porta": atual["porta"],
                             "texto": atual["texto"][:300], "desde": atual["desde"],
                             "andamento": atual["andamento"], "passos": atual["passos"]}
                            if atual else None),
                "fila": [{"numero": p["numero"], "porta": p["porta"], "texto": p["texto"][:120]}
                         for p in list(self.fila.queue)],
            }
        self._publicado_em = self._agora()
        try:
            BANDEJA.gravar_estado(INT.base(), retrato)
        except OSError:
            pass

    # -- quem pode falar (Telegram)
    def _do_oficial(self, mensagem: dict) -> bool:
        de = (mensagem.get("from") or {}).get("id")
        conversa = mensagem.get("chat") or {}
        return bool(self.dono) and de == self.dono and conversa.get("type") == "private"

    def _aberta(self) -> bool:
        return not self.frase or self._agora() < float(self.estado.get("aberto_ate") or 0)

    def _abrir_com_a_frase(self, conversa: int, mensagem: dict, texto: str) -> None:
        partes = texto.split(None, 1)
        try:        # a frase não fica escrita na conversa
            self.telegram.apagar(conversa, mensagem.get("message_id"))
        except Exception:  # noqa: BLE001
            pass
        confere, recado = BANDEJA.frase_confere(
            INT.base(), partes[1] if len(partes) > 1 else "", self.frase, self._agora())
        if not confere:
            self.telegram.dizer(conversa, recado)
            return
        horas = float(self.config.get("OPERADOR_FRASE_HORAS") or HORAS_DA_FRASE)
        self.estado["aberto_ate"] = self._agora() + horas * 3600
        self._gravar_estado()
        self.telegram.dizer(conversa, f"Aberto por {horas:g} h. Pode mandar o pedido.")

    def receber(self, novidade: dict) -> None:
        """Uma novidade do Telegram: confere quem é, trata comando, junta ao lote."""
        mensagem = novidade.get("message") or {}
        conversa = (mensagem.get("chat") or {}).get("id")
        if not conversa:
            return
        if not self._do_oficial(mensagem):
            de = (mensagem.get("from") or {}).get("id")
            registrar(f"IGNORADO: mensagem do usuário {de} (não é o oficial)")
            if not self.dono and (mensagem.get("chat") or {}).get("type") == "private":
                # primeira instalação: quem escreve aprende o próprio número
                # para o oficial colar em OPERADOR_TELEGRAM_USUARIO. Nada roda.
                self.telegram.dizer(conversa, (
                    f"Este bot ainda não tem dono. O seu número de usuário é {de}. "
                    "Ponha-o em OPERADOR_TELEGRAM_USUARIO no operador.cred do "
                    "servidor e reinicie a ponte."))
            return
        texto = (mensagem.get("text") or mensagem.get("caption") or "").strip()
        comando = texto.split()[0].lower() if texto.startswith("/") else ""
        if self.frase:
            if comando == "/abrir":
                self._abrir_com_a_frase(conversa, mensagem, texto)
                return
            if not self._aberta():
                self.telegram.dizer(conversa, "Trancado. Mande /abrir e a frase.")
                return
        if comando and self._comando_do_telegram(conversa, comando, texto):
            return
        anexos, falas, avisos = self._baixar_anexos(mensagem)
        for aviso in avisos:
            self.telegram.dizer(conversa, aviso)
        if not texto and not anexos and not falas:
            if not avisos:
                self.telegram.dizer(conversa, "Não sei ler esse tipo de mensagem. "
                                    "Mande texto, áudio, PDF ou foto.")
            return
        if texto.upper().startswith("CONFIRMO"):
            INT.registrar_confirmacao(texto)
        with self.trava:
            if self.lote is None:
                self.lote = {"conversa": conversa, "textos": [], "anexos": []}
            if texto:
                self.lote["textos"].append(texto)
            self.lote["textos"] += [f"[áudio transcrito] {fala}" for fala in falas]
            self.lote["anexos"] += [str(a) for a in anexos]
            self.lote["ultima"] = self._agora()

    def _comando_do_telegram(self, conversa: int, comando: str, texto: str) -> bool:
        resto = texto.split(None, 1)[1].strip() if len(texto.split(None, 1)) > 1 else ""
        if comando in ("/ajuda", "/start", "/help"):
            self.telegram.dizer(conversa, AJUDA)
        elif comando == "/novo":
            self.nova_conversa()
            self.telegram.dizer(conversa, "Conversa nova. O que importa continua na "
                                "memória e no diário. Pode mandar o pedido.")
        elif comando == "/estado":
            self.telegram.dizer(conversa, self.texto_do_estado())
        elif comando == "/parar":
            self.telegram.dizer(conversa, self.parar())
        elif comando == "/diario":
            linhas = [CONH._uma_linha(e, 300) for e in CONH.entradas(8)]
            self.telegram.dizer(conversa, "\n\n".join(linhas) or "O diário está vazio.")
        elif comando == "/lembrar":
            self.telegram.dizer(conversa, self.lembrar(resto))
        elif comando == "/trancar":
            self.estado["aberto_ate"] = 0
            self._gravar_estado()
            self.telegram.dizer(conversa, "Trancado." if self.frase else
                                "Não há frase configurada (OPERADOR_FRASE).")
        elif comando == "/abrir":
            self.telegram.dizer(conversa, "Não há frase configurada (OPERADOR_FRASE): já está aberto.")
        else:
            # não é comando da ponte: é um pedido que começa por barra, como
            # «/administrativo/gestor não abre» — segue para o operador
            return False
        return True

    def lembrar(self, texto: str) -> str:
        try:
            return "Guardado na memória." if CONH.lembrar(texto) else "Já estava na memória."
        except (ValueError, OSError) as falha:
            return f"Não guardei: {falha}"

    def nova_conversa(self) -> None:
        self.estado["sessao"] = None
        self._gravar_estado()
        self._publicar()

    def _baixar_anexos(self, mensagem: dict) -> tuple[list[Path], list[str], list[str]]:
        """Os anexos baixados, as falas transcritas e os avisos para o oficial."""
        candidatos = []
        if mensagem.get("document"):
            d = mensagem["document"]
            candidatos.append((d["file_id"], d.get("file_name") or "documento",
                               d.get("file_size") or 0, False))
        if mensagem.get("photo"):
            maior = max(mensagem["photo"], key=lambda f: f.get("file_size") or 0)
            candidatos.append((maior["file_id"], "foto.jpg", maior.get("file_size") or 0, False))
        for tipo, extensao in (("audio", ".mp3"), ("voice", ".ogg")):
            if mensagem.get(tipo):
                a = mensagem[tipo]
                candidatos.append((a["file_id"], a.get("file_name") or tipo + extensao,
                                   a.get("file_size") or 0, True))
        baixados, falas, avisos = [], [], []
        if mensagem.get("video") or mensagem.get("video_note"):
            avisos.append("Vídeo eu não leio. Mande foto, PDF ou áudio.")
        if not candidatos:
            return baixados, falas, avisos
        pasta = INT.base() / "entrada" / datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
        pasta.mkdir(parents=True, exist_ok=True)
        for file_id, nome, tamanho, e_audio in candidatos:
            if tamanho > LIMITE_DO_ARQUIVO:
                avisos.append(f"«{nome}» tem mais de 20 MB: o Telegram não "
                              "deixa o bot baixar. Mande em partes ou menor.")
                continue
            destino = pasta / f"{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}_{nome_seguro(nome)}"  # noqa: DTZ005
            try:
                self.telegram.baixar(file_id, destino)
            except Exception as erro:  # noqa: BLE001 — o oficial precisa saber
                avisos.append(f"Não consegui baixar «{nome}»: {erro}")
                continue
            if not e_audio:
                baixados.append(destino)
                continue
            try:
                falas.append(self._ouvir(destino))
            except Exception as falha:  # noqa: BLE001
                avisos.append(f"Não consegui transcrever o áudio ({falha}). "
                              "Escreva, ou dite pelo microfone do teclado.")
        return baixados, falas, avisos

    def _ouvir_em_processo(self, arquivo: Path) -> str:
        """A fala de um áudio, em texto — num processo à parte (`ouvir.py`)."""
        ambiente = dict(os.environ)
        ambiente["OPERADOR_AUDIO"] = (self.config.get("OPERADOR_AUDIO") or "auto").strip()
        try:
            feito = subprocess.run([sys.executable, str(AQUI / "ouvir.py"), str(arquivo)],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", env=ambiente, timeout=300)
        except subprocess.TimeoutExpired as falha:
            raise RuntimeError("demorou mais de 5 minutos") from falha
        if feito.returncode != 0 or not feito.stdout.strip():
            motivo = (feito.stderr or "").strip().splitlines()
            raise RuntimeError(motivo[-1][:300] if motivo else "sem resposta")
        return feito.stdout.strip()

    # -- o lote: várias mensagens seguidas são um pedido só
    def despejar_lote(self, forcar: bool = False) -> bool:
        with self.trava:
            lote = self.lote
            if not lote or (not forcar and self._agora() - lote["ultima"] < ESPERA_DO_LOTE):
                return False
            self.lote = None
        self.enfileirar(self._pedido("telegram", "\n".join(lote["textos"]),
                                     lote["anexos"], conversa=lote["conversa"]))
        return True

    def _pedido(self, porta: str, texto: str, anexos: list, *, conversa: Any = None,
                tela: str = "", numero: str = "") -> dict:
        return {"numero": numero or BANDEJA._novo_id(), "porta": porta, "conversa": conversa,
                "texto": str(texto or "").strip(), "anexos": [str(a) for a in anexos or []],
                "tela": str(tela or "")}

    def enfileirar(self, pedido: dict) -> None:
        with self.trava:
            na_frente = self.fila.qsize() + (1 if self.atual else 0)
            self.fila.put(pedido)
        self._gravar_estado()
        self._publicar()
        self._dizer(pedido, "Recebido." if not na_frente else
                    f"Recebido. Há {na_frente} pedido(s) na frente.")

    def _dizer(self, pedido: dict, texto: str) -> None:
        if pedido.get("porta") == "telegram" and self.telegram and pedido.get("conversa"):
            self.telegram.dizer(pedido["conversa"], texto)

    # -- a outra porta: o que a tela do sistema deixou na bandeja
    def colher_da_bandeja(self) -> int:
        colhidos = BANDEJA.colher(INT.base())
        for item in colhidos:
            if item.get("tipo") == "comando":
                comando = item.get("comando")
                if comando == "novo":
                    self.nova_conversa()
                elif comando == "parar":
                    self.parar()
                elif comando == "lembrar":
                    self.lembrar(item.get("texto") or "")
            elif item.get("tipo") == "pedido":
                texto = str(item.get("texto") or "")
                if texto.upper().startswith("CONFIRMO"):
                    INT.registrar_confirmacao(texto)
                self.enfileirar(self._pedido("sistema", texto, item.get("anexos") or [],
                                             tela=item.get("tela") or "",
                                             numero=item.get("id") or ""))
        return len(colhidos)

    def texto_do_estado(self) -> str:
        pendentes = [d["id"] for d in INT.listar()
                     if d.get("fechada_em") and not d.get("exportada_em")]
        atual = self.atual
        return "\n".join([
            f"Servidor: {INT.servidor()} — {INT.situacao()}",
            (f"Rodando um pedido agora ({atual['andamento']})." if atual
             else "Parado, esperando pedido."),
            f"Na fila: {self.fila.qsize()}",
            f"Conversa: {'em andamento' if self.estado.get('sessao') else 'nova'}",
            f"Pagamento: {self.pagamento()[0] or 'NÃO CONFIGURADO'}",
            "Relatórios por exportar: " + (", ".join(pendentes) or "nenhum"),
        ])

    def parar(self) -> str:
        processo = self.processo
        if not processo:
            return "Não há pedido rodando."
        self.parado = True
        matar(processo)
        return "Interrompido. O que já tinha sido alterado vai no relatório."

    # -- o atendimento (roda no trabalhador, um pedido por vez)
    def texto_do_pedido(self, pedido: dict) -> str:
        partes = [pedido["texto"] or "(sem texto; veja os anexos)"]
        if pedido.get("tela"):
            partes.append("\n(O oficial estava nesta tela do sistema quando pediu: "
                          f"{pedido['tela']})")
        if pedido["anexos"]:
            partes.append("\nAnexos enviados pelo oficial (leia com Read, pelo caminho inteiro):")
            partes += [f"- {a}" for a in pedido["anexos"]]
        partes.append("\n(Porta: Telegram — responda em texto puro e curto.)"
                      if pedido["porta"] == "telegram" else "\n(Porta: tela do sistema.)")
        return "\n".join(partes)

    def _ambiente(self, pedido: dict) -> dict[str, str]:
        ambiente = dict(os.environ)
        for chave, valor in self.config.items():
            if chave.startswith(("TELEGRAM_", "OPERADOR_TELEGRAM")) or chave in (
                    "OPERADOR_FRASE", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
                continue
            ambiente[chave] = valor
        # o arquivo de ambiente da casa manda no que é do banco (ver
        # `intervencao.carregar_ambiente`): o operador.cred pode estar velho
        for caminho in (ambiente.get("OPERADOR_AMBIENTE") or "").split(os.pathsep):
            if caminho.strip():
                ambiente.update({k: v for k, v in INT.ler_ambiente(caminho.strip()).items()
                                 if k.startswith(INT._PREFIXOS_DO_AMBIENTE)})
        _, entra, sai = self.pagamento()
        for nome in sai:
            ambiente.pop(nome, None)
        ambiente.update(entra)
        ambiente.update({"OPERADOR_NOME": INT.servidor(), "OPERADOR_PORTA": pedido["porta"],
                         "OPERADOR_PELA_PONTE": "1",
                         "OPERADOR_SAIDA": str(INT.base() / "saida" / pedido["numero"])})
        return ambiente

    def _conversa_velha(self) -> bool:
        """A conversa parada há muito tempo recomeça: retomá-la custaria ler
        tudo de novo, e o que importa dela já está no diário."""
        horas = float(self.config.get("OPERADOR_CONVERSA_HORAS") or HORAS_DA_CONVERSA)
        usada = float(self.estado.get("usada_em") or 0)
        if self.estado.get("sessao") and horas > 0 and usada and \
                self._agora() - usada > horas * 3600:
            self.estado["sessao"] = None
            return True
        return False

    def _andou(self, feito: str) -> None:
        with self.trava:
            if not self.atual:
                return
            self.atual["andamento"] = feito
            self.atual["passos"] += 1
        if self._agora() - self._publicado_em >= 2:
            self._publicar()

    def _rodar(self, pedido: dict, ambiente: dict[str, str]) -> dict:
        """Roda o operador e lê os eventos dele. Devolve a resposta e o custo."""
        comando = comando_do_operador(self.config, self.estado.get("sessao"))
        erros = tempfile.TemporaryFile()
        try:
            processo = self._popen(
                comando, cwd=str(POSTO.pasta()), env=ambiente, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=erros, text=True, encoding="utf-8",
                errors="replace", **_grupo_proprio())
        except OSError as falha:
            erros.close()
            return {"custo": None, "resposta": (
                f"Não consegui iniciar o Claude Code ({falha}). Confira "
                "OPERADOR_CLAUDE no operador.cred.")}
        self.processo = processo
        minutos = int(self.config.get("OPERADOR_MINUTOS") or MINUTOS_POR_PEDIDO)
        estourou = threading.Event()

        def estourar() -> None:
            estourou.set()
            matar(processo)
        relogio = threading.Timer(minutos * 60, estourar)
        relogio.daemon = True
        relogio.start()
        final, candidata = None, None
        try:
            try:
                processo.stdin.write(self.texto_do_pedido(pedido))
                processo.stdin.close()
            except (OSError, ValueError):
                pass
            for linha in processo.stdout:
                try:
                    evento = json.loads(linha)
                except ValueError:
                    continue
                if not isinstance(evento, dict):
                    continue
                tipo = evento.get("type")
                if tipo == "system" and evento.get("subtype") == "init":
                    candidata = evento.get("session_id") or candidata
                elif tipo == "assistant":
                    feito = descrever(evento)
                    if feito:
                        self._andou(feito)
                elif tipo == "result":
                    final = evento
            processo.wait()
        finally:
            relogio.cancel()
            self.processo = None
        try:
            erros.seek(0)
            resto = erros.read()[-1500:].decode("utf-8", errors="replace").strip()
        except (OSError, ValueError):
            resto = ""
        erros.close()
        falhou_a_api = False
        if self.parado:
            resposta = "Pedido interrompido por você."
        elif estourou.is_set():
            resposta = (f"Passou de {minutos} minutos e foi interrompido. O que já tinha "
                        "mudado está no relatório; diga «continue» para eu seguir.")
        elif final is None:
            if "No conversation found" in resto:
                candidata, self.estado["sessao"] = None, None
            resposta = (f"O operador terminou sem resposta (código {processo.returncode}).\n"
                        f"{resto}\n\nMande de novo; se repetir, mande /novo antes.")
        else:
            texto = str(final.get("result") or "").strip()
            subtipo = str(final.get("subtype") or "")
            candidata = final.get("session_id") or candidata
            if final.get("is_error") and subtipo in ("", "success"):
                falhou_a_api = True
                resposta = traduzir_erro(texto)
            elif not texto:
                resposta = (_PAROU.get(subtipo, f"Parei antes de terminar ({subtipo or 'sem motivo'}).")
                            + " Diga «continue» para eu seguir de onde parei.")
            else:
                resposta = texto
        if candidata and not falhou_a_api:
            self.estado["sessao"] = candidata
            self.estado["usada_em"] = self._agora()
        custo = final.get("total_cost_usd") if isinstance(final, dict) else None
        return {"resposta": resposta, "custo": custo}

    def _encerrar_em_processo(self, dados: dict, ambiente: dict[str, str]) -> dict:
        """Fecha o relatório, anota no diário e exporta — num processo à parte
        (`posto.py encerrar`), porque isso carrega os módulos da casa."""
        arquivo = INT.base() / f"encerrar_{dados['numero']}.json"
        try:
            arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
            feito = subprocess.run(
                [sys.executable, str(AQUI / "posto.py"), "encerrar", "--dados", str(arquivo)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=ambiente, timeout=900)
            linhas = (feito.stdout or "").strip().splitlines()
            resultado = json.loads(linhas[-1]) if linhas else None
            if not isinstance(resultado, dict):
                return {"erro": "o encerramento não respondeu: "
                        + (feito.stderr or "").strip()[-300:]}
            return resultado
        except (OSError, ValueError, subprocess.TimeoutExpired) as falha:
            return {"erro": f"o encerramento falhou ({falha})"}
        finally:
            try:
                arquivo.unlink()
            except OSError:
                pass

    def _rodape(self, fim: dict, custo: Any, conversa_nova: bool) -> str:
        partes = []
        relatorio = fim.get("relatorio")
        if relatorio:
            frase = (f"Relatório {relatorio['id']}: {relatorio['arquivos']} arquivo(s), "
                     f"{relatorio['sql']} SQL")
            if relatorio.get("de_fora"):
                frase += f", {relatorio['de_fora']} fora do sistema"
            partes.append(frase + "." + (f" {fim['envio'].capitalize()}." if fim.get("envio") else ""))
        if fim.get("erro"):
            partes.append(f"({fim['erro']})")
        if custo and self.pagamento()[0].startswith("API"):
            partes.append("Custo do pedido: US$ " + f"{float(custo):.2f}".replace(".", ",") + ".")
        if conversa_nova:
            partes.append("(Conversa nova: a anterior ficou parada; o que importa "
                          "dela está no diário.)")
        return ("\n\n— " + " ".join(partes)) if partes else ""

    def atender(self, pedido: dict) -> None:
        self.parado = False
        conversa_nova = self._conversa_velha()
        INT.carregar_ambiente()
        ambiente = self._ambiente(pedido)
        try:
            POSTO.montar()
        except OSError as falha:
            registrar(f"ERRO ao montar o posto: {falha!r}")
        INT.abrir(pedido["texto"][:2000] or "(pedido só com anexos)",
                  porta=pedido["porta"], sessao=self.estado.get("sessao") or "")
        with self.trava:
            self.atual = {**pedido, "desde": self._agora(), "andamento": "começando",
                          "passos": 0, "avisado_em": self._agora()}
        self._gravar_estado()
        self._publicar()
        try:
            resultado = self._rodar(pedido, ambiente)
        except Exception as falha:  # noqa: BLE001 — o pedido não some sem resposta
            resultado = {"custo": None, "resposta": f"Erro da ponte ao rodar o operador: {falha}"}
        saida = Path(ambiente["OPERADOR_SAIDA"])
        arquivos = sorted(p for p in saida.iterdir() if p.is_file()) if saida.is_dir() else []
        fim = self._encerrar({
            "porta": pedido["porta"], "pedido": pedido["texto"], "numero": pedido["numero"],
            "resposta": resultado["resposta"], "custo": resultado["custo"],
            "sessao": self.estado.get("sessao") or "",
            "arquivos": [a.name for a in arquivos]}, ambiente) or {}
        with self.trava:
            self.atual = None
        self._gravar_estado()
        self._publicar()
        if resultado["custo"] is not None:
            registrar(f"pedido {pedido['numero']} atendido; custo estimado: "
                      f"US$ {float(resultado['custo']):.2f}")
        texto = resultado["resposta"] + self._rodape(fim, resultado["custo"], conversa_nova)
        if pedido["porta"] != "telegram" or not self.telegram or not pedido.get("conversa"):
            return          # a tela do sistema lê a resposta no diário
        self.telegram.dizer(pedido["conversa"], texto)
        for arquivo in arquivos:
            try:
                if arquivo.stat().st_size > LIMITE_DO_ENVIO:
                    raise RuntimeError("passa de 50 MB")
                self.telegram.enviar_arquivo(pedido["conversa"], arquivo)
            except Exception as falha:  # noqa: BLE001
                self.telegram.dizer(pedido["conversa"],
                                    f"Não consegui enviar «{arquivo.name}» ({falha}). "
                                    f"Ficou em {arquivo}.")

    def trabalhar(self) -> None:
        while True:
            pedido = self.fila.get()
            try:
                self.atender(pedido)
            except Exception as falha:  # noqa: BLE001 — o trabalhador não morre
                registrar(f"ERRO ao atender: {falha!r}")
                with self.trava:
                    self.atual = None
                try:
                    self._dizer(pedido, f"Erro da ponte: {falha}")
                except Exception:  # noqa: BLE001
                    pass

    def pulso(self) -> None:
        """O que a ponte faz a cada meio segundo, fora do atendimento: fecha o
        lote, colhe a bandeja, mostra que o operador está vivo."""
        self.despejar_lote()
        agora = self._agora()
        if agora - self._colhido_em >= 1.5:
            self._colhido_em = agora
            self.colher_da_bandeja()
        atual = self.atual
        if atual and atual["porta"] == "telegram" and self.telegram and atual.get("conversa"):
            if agora - self._agindo_em >= 5:
                self._agindo_em = agora
                self.telegram.agindo(atual["conversa"])
            if agora - atual["avisado_em"] >= AVISO_A_CADA:
                atual["avisado_em"] = agora
                self.telegram.dizer(atual["conversa"], (
                    f"… ainda trabalhando ({int((agora - atual['desde']) // 60)} min, "
                    f"{atual['passos']} passos). Agora: {atual['andamento']}."))
        if agora - self._publicado_em >= 15:
            self._publicar()
        if agora - self._codigo_visto_em >= 60:
            self._codigo_visto_em = agora
            self.voltar_com_o_codigo_novo()

    def voltar_com_o_codigo_novo(self) -> bool:
        """A ponte fica meses no ar, e o programa muda debaixo dela: o pacote
        de atualização no principal, a troca de versão no reserva
        (`reserva_versao`), a correção do próprio operador. Os ganchos e o
        encerramento já rodam o código novo, do disco; a ponte ficaria com o
        velho na memória. Então, PARADA, ela sai — e quem a mantém no ar
        (launchd, a tarefa do Windows) a traz de volta com o novo. No meio de
        um pedido, espera."""
        agora = assinatura_do_codigo()
        if agora is None or self._codigo is None or agora == self._codigo:
            return False
        with self.trava:
            if self.atual or self.lote or not self.fila.empty():
                return False
        registrar("o programa do operador mudou no disco: a ponte sai para voltar com o novo")
        self._gravar_estado()
        self._sair(CODIGO_DE_REINICIO)
        return True

    def _relogio(self) -> None:
        while True:
            try:
                self.pulso()
            except Exception as falha:  # noqa: BLE001 — o relógio não para
                registrar(f"ERRO no pulso: {falha!r}")
            time.sleep(0.5)

    def retomar(self) -> None:
        """Depois de um reinício: a fila volta, e o pedido que estava no meio
        NÃO é refeito sozinho (podia repetir o que já gravou) — o oficial é
        avisado, e o aviso fica no diário."""
        interrompido = self.estado.pop("em_andamento", None)
        for pedido in self.estado.pop("fila", None) or []:
            self.fila.put(pedido)
        if interrompido:
            aviso = ("A ponte reiniciou no meio deste pedido. O que já tinha mudado "
                     "ficou registrado; mande de novo se ainda precisar.")
            try:
                CONH.anotar(interrompido.get("porta") or "", interrompido.get("texto") or "",
                            aviso, numero=interrompido.get("numero") or "")
                self._dizer(interrompido, f"«{(interrompido.get('texto') or '')[:80]}» — {aviso}")
            except Exception as falha:  # noqa: BLE001
                registrar(f"ERRO ao avisar do pedido interrompido: {falha!r}")
        self._gravar_estado()
        self._publicar()

    def escutar(self) -> None:
        self.retomar()
        threading.Thread(target=self.trabalhar, daemon=True).start()
        threading.Thread(target=self._relogio, daemon=True).start()
        registrar(f"ponte no ar — servidor {INT.servidor()}; pagamento: "
                  f"{self.pagamento()[0]}; Telegram: {'sim' if self.telegram else 'não'}")
        pausa = 5
        while True:
            if not self.telegram:
                time.sleep(3600)        # só a tela do sistema: o relógio colhe a bandeja
                continue
            try:
                for novidade in self.telegram.novidades(self.estado.get("depois_de", 0)):
                    self.estado["depois_de"] = int(novidade["update_id"]) + 1
                    self._gravar_estado()
                    try:
                        self.receber(novidade)
                    except Exception as falha:  # noqa: BLE001
                        registrar(f"ERRO ao receber: {falha!r}")
                pausa = 5
            except (urllib.error.URLError, OSError, RuntimeError, ValueError) as falha:
                # sem rede: espera e tenta de novo, cada vez mais devagar
                registrar(f"sem conversa com o Telegram ({falha}); tento em {pausa}s")
                time.sleep(pausa)
                pausa = min(pausa * 2, 300)


def main() -> int:
    INT.carregar_ambiente()
    config = ler_configuracao()
    for chave in ("CG_PG_DSN", "CG_PG_SCHEMA", "CG_PG_BIN", "CG_MODO_RESERVA",
                  "CARTORIO_GESTAO_DATA", "OPERADOR_NOME"):
        if config.get(chave) and not os.environ.get(chave):
            os.environ[chave] = config[chave]
    ponte = Ponte(config)
    if not ponte.pagamento()[0]:
        registrar("Falta dizer como o operador fala com a Anthropic, em "
                  + str(INT.base() / "operador.cred")
                  + ": CLAUDE_CODE_OAUTH_TOKEN ou OPERADOR_ASSINATURA=1 (assinatura), "
                  "ou ANTHROPIC_API_KEY (API).")
        return 2
    token = (config.get("TELEGRAM_TOKEN") or "").strip()
    if token:
        ponte.telegram = Telegram(token)
    else:
        registrar("Sem TELEGRAM_TOKEN: a ponte atende só a tela do sistema.")
    ponte.escutar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

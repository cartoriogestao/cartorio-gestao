"""A PONTE DO SUPERUSUÁRIO — o oficial manda o pedido (texto, PDF, foto) pelo
Telegram, de onde estiver; a ponte acorda o operador neste servidor e devolve
a resposta. Ninguém precisa entrar no servidor para pedir.

POR QUE ASSIM — 12/11/2026, pedido do oficial: «integração automatizada, não
quero acessar o servidor para pedir, e não quero o superusuário pesado na
máquina».

    - LEVE: parada, a ponte é um processo Python esperando uma resposta de
      rede (consulta longa de 50 s). Não há modelo, navegador nem serviço
      rodando. O operador (Claude Code, pela API) só existe enquanto atende um
      pedido, e termina.
    - SÓ SAÍDA: a ponte liga para `api.telegram.org`; nada entra. O servidor
      do cartório continua sem porta aberta para a internet.
    - SÓ O OFICIAL: um bot por servidor, e ele só atende o usuário do Telegram
      cadastrado em `OPERADOR_TELEGRAM_USUARIO`, em conversa privada. Qualquer
      outro é ignorado e fica no registro.
    - UM PEDIDO POR VEZ: os que chegam no meio esperam na fila.

A CONFIGURAÇÃO fica em `<dados>/operador/operador.cred` (linhas CHAVE=valor;
ver `operador_cred.exemplo`). Tudo o que estiver ali vai para o ambiente do
operador — é por onde entram o `CG_PG_DSN` e o `CG_PG_SCHEMA` onde o serviço
não os herda.

OS COMANDOS NO TELEGRAM
    /novo     esquece a conversa e começa outra
    /estado   o que está rodando, a fila e os relatórios por exportar
    /parar    interrompe o pedido em andamento
    /ajuda    esta lista
    CONFIRMO  libera, por 10 minutos, o que não tem volta (a guarda cobra)

Só a biblioteca padrão.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intervencao as INT  # noqa: E402

AQUI = Path(__file__).resolve().parent
MODELO_PADRAO = "claude-opus-5-5"
LIMITE_DA_MENSAGEM = 3900          # o Telegram aceita 4096 por mensagem
LIMITE_DO_ARQUIVO = 20 * 1024 * 1024   # o que um bot consegue baixar
MINUTOS_POR_PEDIDO = 60
FERRAMENTAS = "Bash,PowerShell,Read,Edit,Write,Glob,Grep,WebSearch,WebFetch"

AJUDA = (
    "Mande o pedido em texto, com PDF ou foto se precisar.\n"
    "/novo — começa outra conversa\n"
    "/estado — o que está rodando e os relatórios pendentes\n"
    "/parar — interrompe o pedido em andamento\n"
    "CONFIRMO — libera por 10 minutos o que não tem volta")


def registrar(texto: str) -> None:
    linha = f"{datetime.now().isoformat(timespec='seconds')} {texto}"  # noqa: DTZ005
    try:
        with (INT.base() / "ponte.log").open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")
    except OSError:
        pass
    print(linha, flush=True)


# ------------------------------------------------------------- a configuração

def ler_configuracao(caminho: Path | None = None) -> dict[str, str]:
    """As linhas CHAVE=valor do `operador.cred`. Aspas em volta saem."""
    caminho = caminho or (INT.base() / "operador.cred")
    dados: dict[str, str] = {}
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        return dados
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        dados[chave.strip()] = valor
    return dados


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


def nome_seguro(nome: str) -> str:
    """O nome do anexo, sem caminho e sem caractere que o shell estranhe."""
    nome = Path(str(nome or "").replace("\\", "/")).name
    nome = re.sub(r"[^\w.\-]+", "_", nome, flags=re.UNICODE).strip("._")
    return nome[:80] or "anexo"


def comando_do_operador(config: dict[str, str], sessao: str | None,
                        ajustes: Path, instrucoes: str) -> list[str]:
    """A linha de comando do Claude Code sem tela. O pedido vai pela entrada
    padrão. `dontAsk` + lista de ferramentas: nada fica esperando alguém
    aprovar na tela (não há tela), e a guarda roda do mesmo jeito."""
    comando = [
        config.get("OPERADOR_CLAUDE") or shutil.which("claude") or "claude",
        "-p", "--output-format", "json",
        "--model", config.get("OPERADOR_MODELO") or MODELO_PADRAO,
        "--max-turns", config.get("OPERADOR_MAX_TURNOS") or "150",
        "--permission-mode", "dontAsk",
        "--allowedTools", FERRAMENTAS,
        "--settings", str(ajustes),
        "--add-dir", str(INT.base()),
        "--append-system-prompt", instrucoes,
    ]
    if sessao:
        comando += ["--resume", sessao]
    return comando


def escrever_ajustes(destino: Path | None = None) -> Path:
    """O `settings` do operador: a guarda antes de cada ferramenta, e os
    segredos negados também pela regra do próprio Claude Code (duas travas)."""
    destino = destino or (INT.base() / "ajustes_do_operador.json")
    guarda = f'"{sys.executable}" "{AQUI / "guarda.py"}"'
    ajustes = {
        "hooks": {"PreToolUse": [{
            "matcher": "Bash|PowerShell|Read|Edit|Write|MultiEdit|NotebookEdit",
            "hooks": [{"type": "command", "command": guarda, "timeout": 120}],
        }]},
        "permissions": {"deny": [
            "Read(//**/*.key)", "Read(//**/*.cred)", "Read(//**/*.pem)",
            "Read(//**/reserva-chave.privada)", "Read(//**/.pgpass)",
        ]},
    }
    destino.write_text(json.dumps(ajustes, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return destino


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

    def baixar(self, file_id: str, destino: Path) -> None:
        dados = self.chamar("getFile", file_id=file_id)
        with urllib.request.urlopen(self._arquivos + dados["file_path"], timeout=120) as r, \
                destino.open("wb") as saida:
            shutil.copyfileobj(r, saida)


# ---------------------------------------------------------------------- a ponte

class Ponte:
    def __init__(self, config: dict[str, str], telegram: Any, *,
                 rodar_processo=subprocess.Popen):
        self.config = config
        self.telegram = telegram
        self._popen = rodar_processo
        self.dono = int(config.get("OPERADOR_TELEGRAM_USUARIO") or 0)
        self.fila: queue.Queue = queue.Queue()
        self.processo: subprocess.Popen | None = None
        self.parado = False
        self._arquivo_de_estado = INT.base() / "ponte_estado.json"
        self.estado = self._ler_estado()

    # -- o estado que sobrevive ao reinício: até onde li e qual a conversa
    def _ler_estado(self) -> dict:
        try:
            return json.loads(self._arquivo_de_estado.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"depois_de": 0, "sessao": None}

    def _gravar_estado(self) -> None:
        self._arquivo_de_estado.write_text(json.dumps(self.estado), encoding="utf-8")

    # -- quem pode falar
    def _do_oficial(self, mensagem: dict) -> bool:
        de = (mensagem.get("from") or {}).get("id")
        conversa = mensagem.get("chat") or {}
        return bool(self.dono) and de == self.dono and conversa.get("type") == "private"

    def receber(self, novidade: dict) -> None:
        """Uma novidade do Telegram: confere quem é, trata comando, enfileira."""
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
        if comando in ("/ajuda", "/start", "/help"):
            self.telegram.dizer(conversa, AJUDA)
            return
        if comando == "/novo":
            self.estado["sessao"] = None
            self._gravar_estado()
            self.telegram.dizer(conversa, "Conversa nova. Pode mandar o pedido.")
            return
        if comando == "/estado":
            self.telegram.dizer(conversa, self.texto_do_estado())
            return
        if comando == "/parar":
            self.telegram.dizer(conversa, self.parar())
            return
        anexos, recusados = self._baixar_anexos(mensagem)
        for recusado in recusados:
            self.telegram.dizer(conversa, recusado)
        if not texto and not anexos:
            return
        if texto.upper().startswith("CONFIRMO"):
            INT.registrar_confirmacao(texto)
        self.fila.put({"conversa": conversa, "texto": texto, "anexos": anexos})
        espera = self.fila.qsize() - (0 if self.processo else 1)
        self.telegram.dizer(conversa, "Recebido." if espera <= 0 else
                            f"Recebido. Há {espera} pedido(s) na frente.")

    def _baixar_anexos(self, mensagem: dict) -> tuple[list[Path], list[str]]:
        candidatos = []
        if mensagem.get("document"):
            d = mensagem["document"]
            candidatos.append((d["file_id"], d.get("file_name") or "documento",
                               d.get("file_size") or 0))
        if mensagem.get("photo"):
            maior = max(mensagem["photo"], key=lambda f: f.get("file_size") or 0)
            candidatos.append((maior["file_id"], "foto.jpg", maior.get("file_size") or 0))
        for tipo, extensao in (("audio", ".mp3"), ("voice", ".ogg"), ("video", ".mp4")):
            if mensagem.get(tipo):
                a = mensagem[tipo]
                candidatos.append((a["file_id"], a.get("file_name") or tipo + extensao,
                                   a.get("file_size") or 0))
        baixados, recusados = [], []
        if not candidatos:
            return baixados, recusados
        pasta = INT.base() / "entrada" / datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
        pasta.mkdir(parents=True, exist_ok=True)
        for file_id, nome, tamanho in candidatos:
            if tamanho > LIMITE_DO_ARQUIVO:
                recusados.append(f"«{nome}» tem mais de 20 MB: o Telegram não "
                                 "deixa o bot baixar. Mande em partes ou menor.")
                continue
            destino = pasta / f"{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}_{nome_seguro(nome)}"  # noqa: DTZ005
            try:
                self.telegram.baixar(file_id, destino)
                baixados.append(destino)
            except Exception as erro:  # noqa: BLE001 — o oficial precisa saber
                recusados.append(f"Não consegui baixar «{nome}»: {erro}")
        return baixados, recusados

    def texto_do_estado(self) -> str:
        pendentes = [d["id"] for d in INT.listar()
                     if d.get("fechada_em") and not d.get("exportada_em")]
        return "\n".join([
            f"Servidor: {INT.servidor()}",
            "Rodando um pedido agora." if self.processo else "Parado, esperando pedido.",
            f"Na fila: {self.fila.qsize()}",
            f"Conversa: {'em andamento' if self.estado.get('sessao') else 'nova'}",
            "Relatórios por exportar: " + (", ".join(pendentes) or "nenhum"),
        ])

    def parar(self) -> str:
        processo = self.processo
        if not processo:
            return "Não há pedido rodando."
        self.parado = True
        processo.kill()
        return "Interrompido. O que já tinha sido alterado vai no relatório."

    # -- o atendimento (roda no trabalhador, um pedido por vez)
    def texto_do_pedido(self, pedido: dict) -> str:
        partes = [pedido["texto"] or "(sem texto; veja os anexos)"]
        if pedido["anexos"]:
            partes.append("\nAnexos enviados pelo oficial (leia com Read, pelo caminho inteiro):")
            partes += [f"- {a}" for a in pedido["anexos"]]
        return "\n".join(partes)

    def atender(self, pedido: dict) -> None:
        conversa = pedido["conversa"]
        ambiente = dict(os.environ)
        ambiente.update({k: v for k, v in self.config.items()
                         if not k.startswith(("TELEGRAM_", "OPERADOR_TELEGRAM"))})
        ambiente["OPERADOR_NOME"] = INT.servidor()
        instrucoes = (AQUI / "INSTRUCOES.md").read_text(encoding="utf-8").replace(
            "{SERVIDOR}", INT.servidor().upper())
        comando = comando_do_operador(self.config, self.estado.get("sessao"),
                                      escrever_ajustes(), instrucoes)
        INT.abrir(pedido["texto"][:2000] or "(pedido só com anexos)")
        self.parado = False
        saida, erro, codigo = "", "", -1
        try:
            self.processo = self._popen(
                comando, cwd=str(INT.raiz_do_sistema()), env=ambiente,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace")
            try:
                saida, erro = self.processo.communicate(
                    self.texto_do_pedido(pedido), timeout=MINUTOS_POR_PEDIDO * 60)
            except subprocess.TimeoutExpired:
                self.processo.kill()
                saida, erro = self.processo.communicate()
                erro = f"Passou de {MINUTOS_POR_PEDIDO} minutos e foi interrompido.\n{erro}"
            codigo = self.processo.returncode
        except OSError as falha:
            erro = (f"Não consegui iniciar o Claude Code ({falha}). Confira "
                    "OPERADOR_CLAUDE no operador.cred.")
        finally:
            self.processo = None
        resposta, custo = self._ler_saida(saida, erro, codigo)
        fechada = None
        try:
            fechada = INT.fechar(resposta[:1500])
        except Exception as falha:  # noqa: BLE001
            resposta += f"\n\n(O relatório não fechou: {falha})"
        if fechada:
            resposta += (f"\n\n— Relatório {fechada['id']}: "
                         f"{len(fechada['mudancas'])} arquivo(s), "
                         f"{len(fechada['sql'])} SQL.")
            resposta += self._exportar()
        if custo is not None:
            registrar(f"pedido atendido; custo estimado da conversa: US$ {custo:.2f}")
        self.telegram.dizer(conversa, resposta)

    def _ler_saida(self, saida: str, erro: str, codigo: int) -> tuple[str, float | None]:
        if self.parado:
            return "Pedido interrompido por você.", None
        try:
            dados = json.loads(saida)
            if dados.get("session_id"):
                self.estado["sessao"] = dados["session_id"]
                self._gravar_estado()
            texto = str(dados.get("result") or "").strip()
            if texto:
                return texto, dados.get("total_cost_usd")
        except (ValueError, AttributeError):
            pass
        resto = (erro or saida or "").strip()[-1500:]
        if "No conversation found" in resto or "session" in resto.lower():
            self.estado["sessao"] = None
            self._gravar_estado()
        return (f"O operador terminou sem resposta (código {codigo}).\n{resto}\n\n"
                "Mande de novo; se repetir, mande /novo antes."), None

    def _exportar(self) -> str:
        pasta = (self.config.get("OPERADOR_REPOSITORIO") or "").strip()
        if not pasta:
            return ""
        try:
            levadas = INT.exportar(pasta, enviar=True)
            return " Enviado ao repositório privado." if levadas else ""
        except Exception as falha:  # noqa: BLE001
            return f"\n(O relatório ficou no servidor; o envio falhou: {falha})"

    def trabalhar(self) -> None:
        while True:
            pedido = self.fila.get()
            try:
                self.atender(pedido)
            except Exception as falha:  # noqa: BLE001 — o trabalhador não morre
                registrar(f"ERRO ao atender: {falha!r}")
                try:
                    self.telegram.dizer(pedido["conversa"], f"Erro da ponte: {falha}")
                except Exception:  # noqa: BLE001
                    pass

    def escutar(self) -> None:
        threading.Thread(target=self.trabalhar, daemon=True).start()
        registrar(f"ponte no ar — servidor {INT.servidor()}")
        pausa = 5
        while True:
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
    config = ler_configuracao()
    token = (config.get("TELEGRAM_TOKEN") or "").strip()
    if not token:
        registrar("Falta TELEGRAM_TOKEN em " + str(INT.base() / "operador.cred"))
        return 2
    if not (config.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        registrar("Falta ANTHROPIC_API_KEY no operador.cred")
        return 2
    for chave in ("CG_PG_DSN", "CG_PG_SCHEMA", "CG_PG_BIN", "CG_MODO_RESERVA",
                  "CARTORIO_GESTAO_DATA", "OPERADOR_NOME"):
        if config.get(chave) and not os.environ.get(chave):
            os.environ[chave] = config[chave]
    Ponte(config, Telegram(token)).escutar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

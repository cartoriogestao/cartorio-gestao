"""O POSTO DO SUPERUSUÁRIO — a pasta de onde ele trabalha, qualquer que seja a
porta por onde o oficial chamou.

POR QUE UM POSTO — 12/11/2026, o oficial: «não quero que o superusuário seja
acessível só pelo Telegram, quero acessar também pelo sistema e quero poder
usar ele pelo app do Claude (sem gastar a API), tudo com conhecimento que se
acumule e nada fique avulso». Com as regras dentro da ponte, só o Telegram as
tinha. Então as regras saíram da ponte e foram para uma PASTA:

    <dados>/operador/posto/
        CLAUDE.md                 as instruções (de `INSTRUCOES.md`)
        .claude/settings.json     a guarda, os ganchos, o que pode e o que não
        op, op.cmd                o atalho das ferramentas do operador

Todo Claude Code que abre nessa pasta É o superusuário:

    Telegram ─────────┐
    tela do sistema ──┼─► ponte ──► claude sem tela (API ou assinatura) ─┐
    app do Claude ────────────────► claude aberto pelo app (assinatura) ─┼─► o posto
                                                                         │
            a mesma guarda, o mesmo relatório, a mesma memória e o mesmo diário

OS GANCHOS (o Claude Code os chama; `settings.json` diz quando):
    inicio   ao abrir a conversa: imprime o que o operador já sabe (a situação
             do servidor, a memória, os últimos pedidos, as pendências).
    pedido   a cada pedido do oficial: abre a intervenção e, se ele escreveu
             CONFIRMO, grava a confirmação.
    fim      ao terminar de responder: fecha a intervenção (relatório), anota
             o pedido no diário e manda ao repositório privado.
    (a guarda, antes de cada ferramenta, é o `guarda.py`.)
Quando o pedido vem pela ponte (`OPERADOR_PELA_PONTE=1`), `pedido` e `fim` não
fazem nada: é a ponte que abre e encerra, porque só ela sabe a porta, os
anexos e o custo. O encerramento é o mesmo (`encerrar`).

Só a biblioteca padrão. Os módulos da casa (a máscara, o banco) só são
importados dentro de `encerrar`, que roda num processo que nasce e morre.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import bandeja as BANDEJA  # noqa: E402
import conhecimento as CONH  # noqa: E402
import intervencao as INT  # noqa: E402

PORTA_DO_APP = "app"
FERRAMENTAS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch")
SEGREDOS_NEGADOS = ("Read(//**/*.key)", "Read(//**/*.cred)", "Read(//**/*.pem)",
                    "Read(//**/reserva-chave.privada)", "Read(//**/.pgpass)")


def pasta() -> Path:
    alvo = INT.base() / "posto"
    alvo.mkdir(parents=True, exist_ok=True)
    return alvo


def configuracao() -> dict[str, str]:
    """O `operador.cred` deste servidor."""
    return BANDEJA.ler_configuracao(INT.base() / "operador.cred")


def ferramentas() -> list[str]:
    """O que o operador usa sem ninguém aprovar na tela. O PowerShell só
    existe no Windows."""
    return list(FERRAMENTAS) + (["PowerShell"] if os.name == "nt" else [])


def _chamada(programa: str, *argumentos: str) -> str:
    return " ".join([f'"{sys.executable}"', f'"{AQUI / programa}"', *argumentos])


def ajustes() -> dict:
    """O `settings.json` do posto: o ambiente da casa, a guarda antes de cada
    ferramenta, os três ganchos, e os segredos negados também pela regra do
    próprio Claude Code (duas travas)."""
    ambiente = {"CARTORIO_GESTAO_DATA": str(INT.pasta_de_dados()),
                "OPERADOR_NOME": INT.servidor()}
    for nome in sorted(os.environ):
        if nome.startswith(INT._PREFIXOS_DO_AMBIENTE) or nome in ("OPERADOR_AMBIENTE",
                                                                  "OPERADOR_RAIZ"):
            ambiente[nome] = os.environ[nome]

    def gancho(comando: str, prazo: int) -> list[dict]:
        return [{"hooks": [{"type": "command", "command": comando, "timeout": prazo}]}]
    da_guarda = gancho(_chamada("guarda.py"), 120)
    da_guarda[0]["matcher"] = "Bash|PowerShell|Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob"
    return {
        "env": ambiente,
        "hooks": {
            "PreToolUse": da_guarda,
            "SessionStart": gancho(_chamada("posto.py", "inicio"), 60),
            "UserPromptSubmit": gancho(_chamada("posto.py", "pedido"), 60),
            "Stop": gancho(_chamada("posto.py", "fim"), 600),
        },
        "permissions": {
            "allow": ferramentas(),
            "deny": list(SEGREDOS_NEGADOS),
            "additionalDirectories": [str(INT.raiz_do_sistema()), str(INT.pasta_de_dados())],
        },
    }


def instrucoes() -> str:
    """O `CLAUDE.md` do posto: `INSTRUCOES.md` com os caminhos deste servidor."""
    texto = (AQUI / "INSTRUCOES.md").read_text(encoding="utf-8")
    trocas = {"{SERVIDOR}": INT.servidor().upper(),
              "{SISTEMA}": str(INT.raiz_do_sistema()),
              "{DADOS}": str(INT.pasta_de_dados()),
              "{OPERADOR}": str(INT.base()),
              "{OP}": ".\\op.cmd" if os.name == "nt" else "./op"}
    for marca, valor in trocas.items():
        texto = texto.replace(marca, valor)
    return texto


def _escrever(arquivo: Path, texto: str) -> bool:
    """Só grava se mudou: o Claude Code relê o `settings.json` quando ele muda."""
    try:
        if arquivo.read_text(encoding="utf-8") == texto:
            return False
    except OSError:
        pass
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(texto, encoding="utf-8", newline="\n")
    return True


def montar() -> Path:
    """Escreve (ou atualiza) o posto deste servidor. Pode rodar quantas vezes
    for: a ponte o chama a cada pedido, e o gancho de início a cada conversa."""
    alvo = pasta()
    ajustes_do_posto = alvo / ".claude" / "settings.json"
    _escrever(ajustes_do_posto, json.dumps(ajustes(), ensure_ascii=False, indent=1) + "\n")
    _escrever(alvo / "CLAUDE.md", instrucoes())
    atalho = alvo / "op"
    _escrever(atalho, f'#!/bin/sh\nexec "{sys.executable}" "{AQUI / "op.py"}" "$@"\n')
    (alvo / "op.cmd").write_text(
        f'@echo off\r\n"{sys.executable}" "{AQUI / "op.py"}" %*\r\n', encoding="utf-8",
        newline="")
    for arquivo, modo in ((atalho, 0o755), (ajustes_do_posto, 0o600)):
        try:
            arquivo.chmod(modo)
        except OSError:
            pass
    return alvo


# ------------------------------------------------------------------ o encerramento

def sincronizar(repositorio: Any, *, rodar=subprocess.run) -> str:
    """Leva os relatórios e o conhecimento ao repositório privado e traz o do
    outro servidor. Devolve a frase do que aconteceu ("" se não havia nada)."""
    repo = Path(repositorio).expanduser()
    if not repo.is_dir():
        raise INT.Recusa(f"A pasta do repositório privado não existe: {repositorio}")
    git = ["git", "-C", str(repo)]
    rodar(git + ["pull", "--rebase", "--autostash"], capture_output=True, text=True)
    INT.exportar(repo)
    CONH.exportar_para(repo, INT._mascarar)
    CONH.trazer_de(repo)
    pastas = [p for p in ("intervencoes", "conhecimento") if (repo / p).is_dir()]
    if not pastas:
        return ""
    rodar(git + ["add", *pastas], capture_output=True, text=True)
    if rodar(git + ["diff", "--cached", "--quiet"], capture_output=True,
             text=True).returncode == 0:
        return ""
    for comando in (
            git + ["-c", "user.name=Superusuario", "-c",
                   "user.email=superusuario@cartorio.invalid", "commit", "-m",
                   f"Superusuário ({INT.servidor()}): relatórios e conhecimento"],
            git + ["push"]):
        feito = rodar(comando, capture_output=True, text=True)
        if feito.returncode != 0:
            passo = "push" if comando[-1] == "push" else "commit"
            raise INT.Recusa(f"o envio ao repositório privado falhou em «{passo}»: "
                             + (feito.stderr or feito.stdout or "").strip()[-300:])
    return "enviado ao repositório privado"


def encerrar(porta: str, pedido: str, resposta: str, *, custo: float | None = None,
             sessao: str = "", arquivos: list[str] | None = None,
             numero: str = "") -> dict:
    """O fim de um pedido, igual para todas as portas: fecha a intervenção
    (relatório, se algo mudou), anota no diário, guarda os comandos e manda ao
    repositório privado. Nunca levanta: o que falhar vai em `erro`/`envio`."""
    detalhes: dict = {}
    erro = ""
    fechada = None
    try:
        fechada = INT.fechar((resposta or "")[:1500], detalhes)
    except Exception as falha:  # noqa: BLE001 — o pedido foi atendido; diga o que faltou
        erro = f"o relatório não fechou ({type(falha).__name__}: {falha})"[:300]
    relatorio = None
    if fechada:
        relatorio = {"id": fechada["id"], "arquivos": len(fechada["mudancas"]),
                     "de_fora": len(fechada.get("de_fora_mudou") or []),
                     "sql": len([s for s in fechada["sql"] if s.get("escreve", True)])}
    feitos = detalhes.get("comandos") or []
    pedido = pedido or detalhes.get("pedido") or ""
    try:
        CONH.anotar(porta, pedido, resposta, relatorio=relatorio, comandos=len(feitos),
                    custo=custo, sessao=sessao, arquivos=arquivos, numero=numero)
        CONH.guardar_comandos(pedido, feitos)
    except OSError as falha:
        erro = (erro + "; " if erro else "") + f"o diário não gravou ({falha})"
    envio = ""
    repositorio = (configuracao().get("OPERADOR_REPOSITORIO") or "").strip()
    if repositorio:
        try:
            envio = sincronizar(repositorio)
        except Exception as falha:  # noqa: BLE001
            envio = f"ficou no servidor: {falha}"[:300]
    return {"relatorio": relatorio, "comandos": len(feitos), "envio": envio, "erro": erro}


# ------------------------------------------------------------------- os ganchos

def ultima_resposta(transcricao: Any) -> str:
    """O último texto do operador na transcrição da conversa (JSONL do Claude
    Code). Lê só o fim do arquivo: a conversa longa não pesa."""
    try:
        with open(transcricao, "rb") as arquivo:
            arquivo.seek(0, os.SEEK_END)
            arquivo.seek(max(0, arquivo.tell() - 400_000))
            linhas = arquivo.read().decode("utf-8", errors="replace").splitlines()
    except (OSError, TypeError, ValueError):
        return ""
    for linha in reversed(linhas):
        try:
            dados = json.loads(linha)
        except ValueError:
            continue
        if not isinstance(dados, dict) or dados.get("type") != "assistant":
            continue
        conteudo = (dados.get("message") or {}).get("content")
        if isinstance(conteudo, str):
            texto = conteudo
        else:
            texto = "\n".join(str(b.get("text") or "") for b in conteudo or []
                              if isinstance(b, dict) and b.get("type") == "text")
        if texto.strip():
            return texto.strip()
    return ""


def gancho_inicio(entrada: dict) -> str:
    """O que entra na conversa sozinho. Na conversa RETOMADA não entra de
    novo: ela já o tem, e repetir a cada pedido só gastaria."""
    mudou = INT.carregar_ambiente()
    try:
        montar()
    except OSError:
        pass
    if str(entrada.get("source") or "") == "resume":
        return ""
    texto = CONH.contexto()
    if mudou:
        texto += ("\n\nATENÇÃO: o ambiente do servidor mudou depois que esta sessão "
                  f"nasceu ({', '.join(sorted(mudou))}). As ferramentas do `op` já "
                  "leem o novo; programa da casa, rode com `op rodar -- ...`.")
    return texto


def gancho_pedido(entrada: dict) -> None:
    if os.environ.get("OPERADOR_PELA_PONTE") == "1":
        return
    INT.carregar_ambiente()
    texto = str(entrada.get("prompt") or "").strip()
    if texto.upper().startswith("CONFIRMO"):
        INT.registrar_confirmacao(texto)
    INT.abrir(texto[:2000] or "(pedido sem texto)", porta=PORTA_DO_APP,
              sessao=str(entrada.get("session_id") or ""))


def gancho_fim(entrada: dict) -> None:
    if os.environ.get("OPERADOR_PELA_PONTE") == "1" or entrada.get("stop_hook_active"):
        return
    INT.carregar_ambiente()
    aberta = INT.atual()
    if not aberta:
        return
    dados = INT._ler(aberta)
    resposta = (str(entrada.get("last_assistant_message") or "").strip()
                or ultima_resposta(entrada.get("transcript_path")))
    encerrar(dados.get("porta") or PORTA_DO_APP, dados.get("pedido") or "", resposta,
             sessao=str(entrada.get("session_id") or dados.get("sessao") or ""))


def chave_da_casa() -> str:
    """A chave da Anthropic que a casa já guardou para o agente do sistema
    (Administrativo → Agente — configurar). Só é usada se o `operador.cred`
    pedir (`OPERADOR_CHAVE_DA_CASA=1`)."""
    raiz = str(INT.raiz_do_sistema())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import agente_provedores as PROV
    return str(PROV.credencial(str(INT.pasta_de_dados()), "claude") or "")


# ------------------------------------------------------------- linha de comando

def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    ap = argparse.ArgumentParser(prog="operador/posto.py",
                                 description="O posto do superusuário.")
    sub = ap.add_subparsers(dest="comando", required=True)
    for nome in ("montar", "onde", "inicio", "pedido", "fim", "chave-da-casa"):
        sub.add_parser(nome)
    sub.add_parser("encerrar").add_argument("--dados", required=True)
    a = ap.parse_args(argv)
    if a.comando in ("inicio", "pedido", "fim"):
        # Gancho nunca derruba a conversa: o que der errado vai no stderr, e sai 0.
        try:
            entrada = json.loads(sys.stdin.read() or "{}")
            if not isinstance(entrada, dict):
                entrada = {}
            if a.comando == "inicio":
                texto = gancho_inicio(entrada)
                if texto:
                    print(texto)
            elif a.comando == "pedido":
                gancho_pedido(entrada)
            else:
                gancho_fim(entrada)
        except Exception as falha:  # noqa: BLE001
            print(f"posto ({a.comando}): {type(falha).__name__}: {falha}", file=sys.stderr)
        return 0
    INT.carregar_ambiente()
    if a.comando == "montar":
        print(f"Posto montado em {montar()}")
    elif a.comando == "onde":           # para os instaladores: monta e diz só o caminho
        print(montar())
    elif a.comando == "encerrar":
        dados = json.loads(Path(a.dados).read_text(encoding="utf-8"))
        print(json.dumps(encerrar(
            dados.get("porta") or "", dados.get("pedido") or "", dados.get("resposta") or "",
            custo=dados.get("custo"), sessao=dados.get("sessao") or "",
            arquivos=dados.get("arquivos") or [], numero=dados.get("numero") or ""),
            ensure_ascii=False))
    elif a.comando == "chave-da-casa":
        try:
            chave = chave_da_casa()
        except Exception as falha:  # noqa: BLE001
            print(f"sem a chave da casa: {falha}", file=sys.stderr)
            return 1
        if not chave:
            return 1
        print(chave)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

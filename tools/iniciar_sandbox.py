"""Liga o SANDBOX de demonstração do Cartório Gestão — um clique, nada sai para fora.

PARA QUE SERVE
    Quem baixa o programa do GitHub quer ver o sistema funcionando antes de
    instalar numa serventia, e quem programa quer testar uma alteração antes de
    levá-la a uma instalação real. Este programa sobe uma instalação ISOLADA,
    com dados fictícios, só nesta máquina (http://127.0.0.1:8899):

    - a pasta de dados é PRÓPRIA (`sandbox_dados\\` ao lado do programa);
    - `PROGRAMDATA` também é desviado para dentro dela — é lá que o sistema
      procura credenciais das Centrais, o `secret.key` e o perfil do
      LibreOffice, e uma pasta vazia significa «nenhuma credencial»;
    - `CARTORIO_GESTAO_SANDBOX=1` arma a trava das Centrais
      (`centrais_trava_sandbox.py`): host de produção é desviado para o
      simulador ou recusado;
    - por cima de tudo, uma TRAVA DE REDE neste processo recusa qualquer
      conexão que não seja com a própria máquina (127.0.0.1) — IA, Central,
      atualização, o que for;
    - o selador é o de mentira dos testes (`tests/selador_falso.py`), com TLS
      de verdade numa porta local: o ato sela, e o selo não existe no Tribunal;
    - o servidor escuta só em 127.0.0.1 (o balcão da rede não o enxerga), sem
      a descoberta UDP da porta 8766, sem tarefa agendada, sem serviço, sem
      firewall, sem nada instalado no Windows;
    - o cookie da sessão tem nome próprio (`cg_sandbox_sessao`): o navegador
      não separa cookie por porta, e com o mesmo nome o sandbox derrubaria a
      sessão de uma instalação real aberta na aba ao lado.

A LIÇÃO QUE DECIDE O DESENHO
    Um sandbox ligado SEM a variável de dados abre o banco da instalação real
    — `app.get_data_dir()` cai em `%PROGRAMDATA%\\CartorioGestao` quando
    `CARTORIO_GESTAO_DATA` está vazia. Por isso este programa SEMPRE define a
    variável, e RECUSA subir quando a pasta escolhida é (ou contém, ou está
    dentro de) a pasta de uma instalação real, quando ela tem `install.json`
    ou quando já guarda um banco que não foi este kit que criou.

POR QUE A PASTA FICA AO LADO DO PROGRAMA
    `sandbox_dados\\` ao lado da cópia baixada: tudo o que o sandbox grava fica
    num lugar só, à vista, e apagar a pasta apaga o sandbox inteiro — nada se
    espalha pelo perfil do Windows. O `.gitignore` a exclui. Só quando a pasta
    do programa não aceita escrita é que se usa
    `%LOCALAPPDATA%\\CartorioGestaoSandbox`.

USO
    INICIAR_SANDBOX.cmd                       (ou: python tools/iniciar_sandbox.py)
    INICIAR_SANDBOX.cmd --porta 8900          outra porta
    INICIAR_SANDBOX.cmd --dados D:\\demo       outra pasta de dados (só de sandbox)
    INICIAR_SANDBOX.cmd --sem-navegador       não abre o navegador
    INICIAR_SANDBOX.cmd --sem-carga           não roda a carga de demonstração
    INICIAR_SANDBOX.cmd --conferir            sobe, confere /saude e /login, e sai
    INICIAR_SANDBOX.cmd --apagar              apaga a pasta do sandbox (pede confirmação)
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

PORTA_PADRAO = 8899
#: As portas de uma instalação real: a do sistema e a da descoberta (UDP).
PORTAS_DA_PRODUCAO = frozenset({8765, 8766})
NOME_DA_PASTA = "sandbox_dados"
NOME_NO_LOCALAPPDATA = "CartorioGestaoSandbox"
#: O arquivo que diz «esta pasta é de sandbox, criada pelo kit».
MARCA = "SANDBOX_DEMONSTRACAO.txt"
COOKIE_DA_SESSAO = "cg_sandbox_sessao"
NOME_DO_BANCO = "cartorio_gestao.sqlite3"

#: O PROGRAMDATA de verdade, lido ANTES de o kit desviá-lo. É contra ele que a
#: recusa compara — depois do desvio, `os.environ["PROGRAMDATA"]` aponta para
#: dentro do sandbox e não serve mais para reconhecer a produção.
#: E ele viaja numa variável própria, para o processo-filho (ou um segundo import
#: deste módulo, feito depois do desvio) ainda saber qual era.
VAR_PROGRAMDATA_ORIGINAL = "CG_SANDBOX_PROGRAMDATA_ORIGINAL"
_PROGRAMDATA_ORIGINAL = (os.environ.get(VAR_PROGRAMDATA_ORIGINAL)
                         or os.environ.get("PROGRAMDATA") or "")

#: Os pacotes sem os quais o sistema não sobe (módulo importável → linha do
#: requirements.txt). Os demais do requirements.txt são de funções pontuais.
PACOTES_OBRIGATORIOS = (
    ("flask", "Flask"), ("waitress", "waitress"), ("cryptography", "cryptography"),
    ("asn1crypto", "asn1crypto"), ("lxml", "lxml"),
)


class SandboxRecusado(RuntimeError):
    """O sandbox não pode subir assim. A mensagem diz o que fazer."""


# ------------------------------------------------------------------ a pasta


def _resolver(caminho) -> Path:
    try:
        return Path(caminho).expanduser().resolve()
    except OSError:
        return Path(os.path.abspath(os.path.expanduser(str(caminho))))


def raizes_reais() -> list[Path]:
    """As pastas onde mora uma instalação real (programa, dados ou cópias).

    São as que `app.get_data_dir()` escolhe sozinho quando a variável falta,
    a pasta do programa instalado e a das cópias de segurança da produção.
    """
    candidatas: list[Path] = []
    for base in (_PROGRAMDATA_ORIGINAL, r"C:\ProgramData"):
        if base:
            candidatas.append(Path(base) / "CartorioGestao")
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(var)
        if base:
            candidatas.append(Path(base) / "CartorioGestao")
    candidatas.append(Path(r"C:\Program Files\CartorioGestao"))
    if os.environ.get("APPDATA"):
        candidatas.append(Path(os.environ["APPDATA"]) / "CartorioGestao")
    candidatas.append(Path.home() / ".cartorio_gestao")
    candidatas.append(Path(r"C:\CartorioGestao_Copias"))
    vistas: list[Path] = []
    for c in candidatas:
        r = _resolver(c)
        if r not in vistas:
            vistas.append(r)
    return vistas


def _dentro(filho: Path, pai: Path) -> bool:
    filho_s = os.path.normcase(str(filho)).rstrip("\\/")
    pai_s = os.path.normcase(str(pai)).rstrip("\\/")
    return filho_s == pai_s or filho_s.startswith(pai_s + os.sep)


def conferir_pasta_de_dados(pasta) -> Path:
    """Devolve a pasta resolvida, ou RECUSA. Só lê; não cria nada."""
    alvo = _resolver(pasta)
    for real in raizes_reais():
        if _dentro(alvo, real) or _dentro(real, alvo):
            raise SandboxRecusado(
                f"Recusado: a pasta {alvo} é (ou contém) a pasta de uma "
                f"instalação real ({real}). O sandbox nunca abre os dados de "
                f"uma serventia. Escolha outra pasta com --dados, ou rode sem "
                f"--dados para usar a pasta padrão do sandbox.")
    if (alvo / "install.json").exists():
        raise SandboxRecusado(
            f"Recusado: a pasta {alvo} tem install.json — é a pasta de dados "
            f"de uma instalação real. O sandbox nunca abre os dados de uma "
            f"serventia. Escolha outra pasta com --dados.")
    if (alvo / NOME_DO_BANCO).exists() and not (alvo / MARCA).exists():
        raise SandboxRecusado(
            f"Recusado: a pasta {alvo} já tem um banco ({NOME_DO_BANCO}) que "
            f"não foi criado pelo kit do sandbox (falta o arquivo {MARCA}). "
            f"Pode ser o banco de uma serventia. Escolha uma pasta vazia com "
            f"--dados.")
    return alvo


def conferir_raiz_do_programa(raiz: Path = RAIZ) -> None:
    """Recusa rodar o sandbox de dentro da pasta de uma instalação real."""
    r = _resolver(raiz)
    for real in raizes_reais():
        if _dentro(r, real):
            raise SandboxRecusado(
                f"Recusado: este programa está dentro da pasta de uma "
                f"instalação real ({real}). O sandbox roda da cópia baixada do "
                f"GitHub, e não da pasta instalada. Baixe ou copie o programa "
                f"para outra pasta e rode o INICIAR_SANDBOX.cmd de lá.")


def _aceita_escrita(pasta: Path) -> bool:
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        teste = pasta / ".teste_de_escrita"
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
        return True
    except OSError:
        return False


def pasta_padrao(raiz: Path = RAIZ) -> Path:
    """`sandbox_dados` ao lado do programa; sem escrita ali, o LOCALAPPDATA."""
    ao_lado = raiz / NOME_DA_PASTA
    if ao_lado.exists() or _aceita_escrita(raiz):
        return ao_lado
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / NOME_NO_LOCALAPPDATA


def preparar_pasta(pasta) -> dict[str, str]:
    """Confere, cria a pasta do sandbox e devolve o ambiente do processo.

    ESCREVE só dentro da pasta: a marca, `arquivos`, `programdata`, `copias`.
    """
    alvo = conferir_pasta_de_dados(pasta)
    alvo.mkdir(parents=True, exist_ok=True)
    marca = alvo / MARCA
    if not marca.exists():
        marca.write_text(
            "Esta pasta é de um SANDBOX de demonstração do Cartório Gestão.\n"
            "Os dados aqui são fictícios. Apagar esta pasta apaga o sandbox.\n"
            "Criada por tools/iniciar_sandbox.py em "
            f"{time.strftime('%Y-%m-%d %H:%M:%S')}.\n", encoding="utf-8")
    programdata = alvo / "programdata"
    for sub in ("arquivos", "copias", "malote", programdata / "CartorioGestao"):
        (alvo / sub).mkdir(parents=True, exist_ok=True)
    return {
        "CARTORIO_GESTAO_DATA": str(alvo),
        "CARTORIO_GESTAO_SANDBOX": "1",
        "PROGRAMDATA": str(programdata),
        "CARTORIO_GESTAO_COPIAS": str(alvo / "copias"),
        "MALOTE_DATA_DIR": str(alvo / "malote"),
        "CARTORIO_GESTAO_NO_BROWSER": "1",
        VAR_PROGRAMDATA_ORIGINAL: _PROGRAMDATA_ORIGINAL,
    }


def aplicar_ambiente(ambiente: dict[str, str]) -> None:
    """Põe o ambiente no processo. Tem de vir ANTES do primeiro import do sistema:
    `impressao_pdf` e `selador_config` leem `PROGRAMDATA` no corpo do módulo."""
    os.environ.update(ambiente)
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))


def conferir_porta(porta: int) -> int:
    porta = int(porta)
    if porta in PORTAS_DA_PRODUCAO:
        raise SandboxRecusado(
            f"Recusado: a porta {porta} é a de uma instalação real do sistema. "
            f"Use outra, por exemplo --porta {PORTA_PADRAO}.")
    if not 1024 <= porta <= 65535:
        raise SandboxRecusado(
            f"A porta {porta} não serve: escolha um número entre 1024 e 65535.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", porta))
        except OSError:
            raise SandboxRecusado(
                f"A porta {porta} já está em uso. Talvez o sandbox já esteja "
                f"aberto: tente http://127.0.0.1:{porta} no navegador. Para "
                f"subir outro, use --porta com outro número (ex.: 8900).") from None
    return porta


# ---------------------------------------------------------- a trava de rede


class RedeBloqueada(ConnectionRefusedError):
    """O sandbox recusou uma conexão para fora da máquina."""


_trava: dict = {}
_trava_lock = threading.Lock()


def _e_local(host) -> bool:
    """Loopback (127.x, ::1, localhost) ou o endereço «qualquer» (0.0.0.0)."""
    h = str(host or "").strip().strip("[]").lower()
    if h in ("localhost", ""):
        return True
    try:
        ip = ipaddress.ip_address(h.split("%")[0])
        return ip.is_loopback or ip.is_unspecified
    except ValueError:
        return h.endswith(".localhost")


def trava_armada() -> bool:
    return bool(_trava)


def tentativas_bloqueadas() -> list[str]:
    return list(_trava.get("registro", []))


def armar_trava_de_rede() -> None:
    """Recusa, NESTE processo, qualquer conexão que não seja com 127.0.0.1.

    Troca três funções do módulo `socket` no lugar (sem subclasse — a classe
    continua a mesma para `isinstance` e para o `super()` do `ssl`). A
    resolução de nome também é recusada para host de fora: perguntar ao DNS
    já é sair da máquina. Idempotente.
    """
    with _trava_lock:
        if _trava:
            return
        registro: list[str] = []
        conectar = socket.socket.connect
        conectar_ex = socket.socket.connect_ex
        resolver = socket.getaddrinfo

        def _recusar(destino: str):
            registro.append(destino)
            raise RedeBloqueada(
                f"Sandbox: conexão para fora da máquina recusada ({destino}). "
                f"O sandbox de demonstração não fala com a internet nem com a "
                f"rede local — nada foi enviado.")

        def _checar(sock, endereco):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and \
                    isinstance(endereco, tuple) and not _e_local(endereco[0]):
                _recusar(f"{endereco[0]}:{endereco[1] if len(endereco) > 1 else ''}")

        def connect(self, endereco):
            _checar(self, endereco)
            return conectar(self, endereco)

        def connect_ex(self, endereco):
            _checar(self, endereco)
            return conectar_ex(self, endereco)

        def getaddrinfo(host, *args, **kwargs):
            if host is not None:
                nome = host.decode() if isinstance(host, bytes) else str(host)
                if not _e_local(nome):
                    try:
                        ipaddress.ip_address(nome.strip("[]").split("%")[0])
                    except ValueError:
                        _recusar(nome)
            return resolver(host, *args, **kwargs)

        socket.socket.connect = connect
        socket.socket.connect_ex = connect_ex
        socket.getaddrinfo = getaddrinfo
        _trava.update(registro=registro, connect=conectar,
                      connect_ex=conectar_ex, getaddrinfo=resolver)


def desarmar_trava_de_rede() -> None:
    """Devolve as funções originais (usado pelos testes)."""
    with _trava_lock:
        if not _trava:
            return
        socket.socket.connect = _trava["connect"]
        socket.socket.connect_ex = _trava["connect_ex"]
        socket.getaddrinfo = _trava["getaddrinfo"]
        _trava.clear()


# ------------------------------------------------------- o que o sistema usa


def pacotes_faltando() -> list[str]:
    import importlib.util
    return [pacote for modulo, pacote in PACOTES_OBRIGATORIOS
            if importlib.util.find_spec(modulo) is None]


FAIXA_HTML = (
    '<div id="cg-faixa-sandbox" style="position:fixed;left:0;right:0;bottom:0;'
    'z-index:2147483000;background:#9a3412;color:#fff;'
    'font:600 13px/1.7 system-ui,Segoe UI,sans-serif;text-align:center;'
    'padding:1px 8px;pointer-events:none;opacity:.95">'
    'SANDBOX DE DEMONSTRAÇÃO — dados fictícios, nada sai para fora. '
    'Não é o sistema de uma serventia.</div>')


def _pendurar_faixa(app) -> None:
    """Põe a faixa do sandbox em toda tela HTML (não em download nem JSON)."""

    @app.after_request
    def _faixa(resposta):
        try:
            if (resposta.mimetype == "text/html" and not resposta.direct_passthrough
                    and "attachment" not in (resposta.headers.get("Content-Disposition") or "")):
                corpo = resposta.get_data(as_text=True)
                if "</body>" in corpo and "cg-faixa-sandbox" not in corpo:
                    resposta.set_data(corpo.replace("</body>", FAIXA_HTML + "</body>", 1))
        except Exception:  # noqa: BLE001 — a faixa nunca derruba uma tela
            pass
        return resposta


def montar_app():
    """O aplicativo do sistema, com o cookie próprio, a faixa e sem atualização.

    A tela de atualização do sistema APLICA pacote na pasta do programa e para a
    tarefa agendada da instalação real — no sandbox isso fica recusado, com a
    frase pronta, antes de qualquer coisa acontecer.
    """
    import app as APP
    from update_manager import UpdateError

    def _recusar_atualizacao(*_a, **_k):
        raise UpdateError(
            "No sandbox de demonstração a atualização não é aplicada: ela "
            "trocaria os arquivos do programa e pararia o servidor de uma "
            "instalação real. Para testar um pacote, use uma instalação de "
            "teste separada.")

    APP.launch_windows_updater = _recusar_atualizacao
    APP.pode_aplicar_sozinho = lambda *_a, **_k: (False, (
        "No sandbox de demonstração a atualização não é aplicada."))
    app = APP.create_app({"SESSION_COOKIE_NAME": COOKIE_DA_SESSAO})
    _pendurar_faixa(app)
    return app


def ligar_selador(db, pasta: Path):
    """Sobe o selador de mentira e aponta a serventia do sandbox para ele.

    Devolve o aparelho (para desligar no fim) ou None, com o motivo impresso.
    A porta e o certificado mudam a cada subida, por isso o apontamento é
    refeito sempre — pela mesma função que a tela Selador usa
    (`fixar_certificado`), que abre a conexão e confere a impressão digital.
    """
    pasta_testes = RAIZ / "tests"
    if str(pasta_testes) not in sys.path:
        sys.path.append(str(pasta_testes))
    try:
        import selador_cliente as CL
        import selador_config as SC
        from selador_falso import SeladorFalso, impressao_digital
    except ImportError as erro:
        print(f"  selador     NÃO ligado ({erro}). Os atos que pedem selo vão "
              f"parar na minuta; o resto funciona.")
        return None
    aparelho = SeladorFalso()
    aparelho.__enter__()
    # Numeração que não repete entre uma subida e outra: o simulador começa
    # do zero a cada vez, e o banco do sandbox guarda os selos de antes.
    aparelho._contador = int(time.time()) - 1_700_000_000
    agora = db.now()
    try:
        SC.gravar_credencial(pasta, "demonstracao", "demonstracao", agora=agora,
                             usuario_do_sistema="SANDBOX")
        CL.esquecer_tokens()
        with db.transaction() as con:
            SC.gravar(con, base_url=aparelho.base, usuario="demonstracao",
                      origem="SANDBOX", agora=agora, usuario_do_sistema="SANDBOX")
            CL.fixar_certificado(con, aparelho.base, sha256=impressao_digital(),
                                 agora=agora, usuario="SANDBOX")
        faltando = {k: v for k, v in (("ri_cns", "000000"),
                                      ("selo_tabela_custas_em", "2026-01-01"))
                    if not str(db.get_setting(k, "") or "").strip()}
        if faltando:
            db.set_settings(faltando)
    except Exception as erro:  # noqa: BLE001 — sem selador o sistema ainda sobe
        aparelho.__exit__(None, None, None)
        print(f"  selador     NÃO ligado ({erro}).")
        return None
    return aparelho


# ------------------------------------------------------------------ o quadro


def _quadro(pasta: Path, porta: int, aparelho, relatorio_carga) -> str:
    from tools.carga_de_demonstracao import USUARIOS_DE_DEMONSTRACAO
    linhas = [
        "",
        "=" * 72,
        "  CARTÓRIO GESTÃO — SANDBOX DE DEMONSTRAÇÃO (dados fictícios)",
        "=" * 72,
        f"  endereço    http://127.0.0.1:{porta}   (só nesta máquina)",
        f"  dados       {pasta}",
        "  rede        travada: nenhuma conexão sai desta máquina",
        "  centrais    simuladas ou recusadas (CARTORIO_GESTAO_SANDBOX=1)",
        f"  selador     {'de mentira em ' + aparelho.base if aparelho else 'desligado'}",
        "",
        "  Usuários de demonstração (senhas fracas DE PROPÓSITO — só para o sandbox):",
    ]
    for usuario, nome, papel, senha in USUARIOS_DE_DEMONSTRACAO:
        linhas.append(f"    {usuario:<12} senha {senha:<15} {papel:<8} {nome}")
    if relatorio_carga:
        avisos = [f"    - {passo}: {motivo}" for passo, motivo in
                  relatorio_carga.get("pulados", {}).items()]
        if avisos:
            linhas += ["", "  A carga de demonstração deixou de fazer:"] + avisos
    linhas += ["", "  Para encerrar: Ctrl+C nesta janela (ou feche-a).", "=" * 72, ""]
    return "\n".join(linhas)


def _conferir_no_ar(porta: int) -> dict:
    import urllib.request
    resultado = {}
    for caminho in ("/saude", "/login"):
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{caminho}", timeout=60) as r:
            corpo = r.read().decode("utf-8", "replace")
            resultado[caminho] = (r.status, corpo)
    return resultado


# --------------------------------------------------------------------- apagar


def apagar(pasta: Path, *, sim: bool = False) -> int:
    alvo = conferir_pasta_de_dados(pasta)
    if not alvo.exists():
        print(f"Não há sandbox em {alvo}. Nada a apagar.")
        return 0
    if not (alvo / MARCA).exists():
        print(f"Recusado: {alvo} não tem o arquivo {MARCA}; não é uma pasta de "
              f"sandbox criada pelo kit. Nada foi apagado.")
        return 2
    if not sim:
        resposta = input(f"Apagar o sandbox inteiro em {alvo}? Digite APAGAR para "
                         f"confirmar: ").strip()
        if resposta != "APAGAR":
            print("Nada foi apagado.")
            return 1
    shutil.rmtree(alvo)
    print(f"Sandbox apagado: {alvo}. Na próxima vez, o INICIAR_SANDBOX.cmd "
          f"cria um novo, com a carga de demonstração.")
    return 0


# ----------------------------------------------------------------------- main


def _argumentos(argv):
    ap = argparse.ArgumentParser(
        prog="INICIAR_SANDBOX",
        description="Liga o sandbox de demonstração do Cartório Gestão.")
    ap.add_argument("--dados", help="pasta de dados do sandbox (padrão: sandbox_dados ao "
                                    "lado do programa)")
    ap.add_argument("--porta", type=int,
                    default=int(os.environ.get("CG_SANDBOX_PORTA") or PORTA_PADRAO))
    ap.add_argument("--sem-navegador", action="store_true")
    ap.add_argument("--sem-carga", action="store_true")
    ap.add_argument("--conferir", action="store_true",
                    help="sobe, confere /saude e /login, imprime e sai")
    ap.add_argument("--apagar", action="store_true", help="apaga a pasta do sandbox")
    ap.add_argument("--sim", action="store_true", help="com --apagar: não pergunta")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    if sys.version_info < (3, 11):
        print(f"O sandbox precisa do Python 3.11 ou mais novo; este é o "
              f"{sys.version.split()[0]}. Instale um Python 3.11+ (python.org) e "
              f"rode de novo.")
        return 1
    a = _argumentos(argv)
    try:
        conferir_raiz_do_programa()
        pasta = Path(a.dados) if a.dados else pasta_padrao()
        if a.apagar:
            return apagar(pasta, sim=a.sim)
        porta = conferir_porta(a.porta)
        faltam = pacotes_faltando()
        if faltam:
            print("Faltam pacotes do Python que o sistema usa: " + ", ".join(faltam)
                  + ".\nInstale-os com:\n"
                  f'    "{sys.executable}" -m pip install -r requirements.txt\n'
                  "e rode o INICIAR_SANDBOX.cmd de novo.")
            return 1
        herdada = os.environ.get("CARTORIO_GESTAO_DATA")
        ambiente = preparar_pasta(pasta)
        if herdada and _resolver(herdada) != _resolver(ambiente["CARTORIO_GESTAO_DATA"]):
            print(f"Aviso: a variável CARTORIO_GESTAO_DATA estava definida ({herdada}) "
                  f"e foi IGNORADA — o sandbox usa só a pasta dele.")
        aplicar_ambiente(ambiente)
        pasta = Path(ambiente["CARTORIO_GESTAO_DATA"])
    except SandboxRecusado as erro:
        print(str(erro))
        return 2

    armar_trava_de_rede()
    print("Montando o sistema do sandbox (a primeira vez demora mais)…")
    try:
        app = montar_app()
    except ImportError as erro:
        print(f"O sistema não subiu: falta um pacote do Python ({erro}).\nInstale com:\n"
              f'    "{sys.executable}" -m pip install -r requirements.txt')
        return 1
    db = app.extensions["db"]
    if _resolver(db.db_path.parent) != _resolver(pasta):
        print(f"Recusado: o banco aberto ({db.db_path}) não é o da pasta do sandbox. "
              f"Nada foi servido.")
        return 2

    relatorio = None
    if not a.sem_carga:
        from tools.carga_de_demonstracao import carregar
        print("Conferindo a carga de demonstração…")
        relatorio = carregar(db, app=app)
    aparelho = ligar_selador(db, pasta)

    from waitress import create_server
    servidor = create_server(app, host="127.0.0.1", port=porta, threads=8)
    print(_quadro(pasta, porta, aparelho, relatorio))
    try:
        if a.conferir:
            fio = threading.Thread(target=servidor.run, daemon=True)
            fio.start()
            no_ar = _conferir_no_ar(porta)
            for caminho, (status, corpo) in no_ar.items():
                print(f"  conferido {caminho}: HTTP {status}"
                      + (" (faixa do sandbox presente)" if FAIXA_HTML[:24] in corpo else ""))
            print(f"  conexões para fora tentadas e recusadas: {len(tentativas_bloqueadas())}")
            for destino in tentativas_bloqueadas():
                print(f"    - {destino}")
            return 0
        if not a.sem_navegador:
            import webbrowser
            threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{porta}")).start()
        servidor.run()
    except KeyboardInterrupt:
        print("Encerrando o sandbox…")
    finally:
        try:
            servidor.close()
        except Exception:  # noqa: BLE001
            pass
        if aparelho is not None:
            aparelho.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    # Importa-se a si mesmo pelo nome do pacote, para haver UMA cópia deste
    # módulo no processo (a carga de demonstração o importa como `tools.…`).
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))
    from tools import iniciar_sandbox as _kit
    sys.exit(_kit.main())

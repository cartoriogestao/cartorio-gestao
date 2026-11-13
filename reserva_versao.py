"""A VERSÃO DO PROGRAMA VAI PARA A RESERVA — a mesma que está no principal.

O banco, os arquivos e os segredos já chegam sozinhos. O programa não: uma versão
nova no Windows ficava no Mac até alguém fazer `git pull` e rodar o instalador.
Código novo em cima de esquema velho quebra tela, então a sincronia só troca o
programa depois que `reserva.py esquema` deixou as tabelas iguais.

COMO VAI
    - O principal, ao subir, grava o número em `settings.sistema_versao`. A réplica
      leva essa linha como leva qualquer outra.
    - A sincronia do Mac lê o número. Se for o mesmo, não faz nada. Se o Mac estiver
      à frente, não desce. Se o esquema ainda não chegou, espera.
    - Se o principal está mais novo e o esquema já é o dele, baixa a etiqueta
      `vX.Y.Z` no GitHub (o repositório é público; é o mesmo código do `git pull`
      daquela etiqueta, não o `main`, que pode estar na frente da casa) e troca a
      pasta `sistema`. O `venv` fica do lado de fora. Se `requirements.txt` mudou,
      instala, e só então reinicia o serviço.

O QUE ISTO NÃO FAZ
    Não instala a primeira vez: o Mac precisa desta sincronia já no ar. Não pega
    correção que o principal esteja rodando sem etiqueta publicada.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

CHAVE = "sistema_versao"
VERSAO_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")
HOSPEDES = frozenset({"github.com", "codeload.github.com", "objects.githubusercontent.com"})
TAMANHO_MAXIMO = 200 * 1024 * 1024
PREFIXO_RE = re.compile(r"[A-Za-z0-9.]{1,80}")
IGNORAR_NA_COPIA = shutil.ignore_patterns(
    ".git", "venv", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache")


def validar_versao(versao: str) -> str:
    texto = (versao or "").strip()
    if not VERSAO_RE.fullmatch(texto):
        raise ValueError(f"versão fora do formato: {versao!r}")
    return texto


def versao_em_tupla(versao: str) -> tuple[int, ...]:
    return tuple(int(parte) for parte in validar_versao(versao).split("."))


def decisao(local: str, principal: str, esquema_ok: bool) -> str:
    """em_dia, sem_publicacao, recua, espera ou aplicar.

    `espera` vem antes de `aplicar`: o código novo só entra quando a tabela nova
    já está na reserva. `recua` não desce — a reserva à frente fica onde está.
    """
    local = (local or "").strip()
    principal = (principal or "").strip()
    if not VERSAO_RE.fullmatch(principal):
        return "sem_publicacao"
    if local and not VERSAO_RE.fullmatch(local):
        raise ValueError(f"versão local fora do formato: {local!r}")
    if local == principal:
        return "em_dia"
    if local and versao_em_tupla(local) > versao_em_tupla(principal):
        return "recua"
    if not esquema_ok:
        return "espera"
    return "aplicar"


def publicar(db, versao: str) -> bool:
    """Grava o número no principal, se ainda não for esse. A réplica leva a linha."""
    versao = validar_versao(versao)
    if db.get_setting(CHAVE, "") == versao:
        return False
    db.set_settings({CHAVE: versao})
    return True


def url_da_versao(versao: str) -> str:
    versao = validar_versao(versao)
    return (
        "https://github.com/cartoriogestao/cartorio-gestao/archive/refs/tags/"
        f"v{versao}.tar.gz"
    )


def _hospede(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


def baixar_pacote(versao: str, destino: Path, abrir=None) -> None:
    """Baixa a etiqueta. Recusa outro hospedeiro e pacote acima do teto."""
    abrir = abrir or urllib.request.urlopen
    pedido = urllib.request.Request(url_da_versao(versao), headers={"User-Agent": "CartorioGestao-reserva"})
    with abrir(pedido, timeout=120) as resposta:
        final = resposta.geturl()
        hospede = _hospede(final)
        if hospede not in HOSPEDES:
            raise ValueError(f"o pacote veio de {hospede or 'outro lugar'}, não do GitHub")
        lido = 0
        with Path(destino).open("wb") as saida:
            while True:
                pedaco = resposta.read(1 << 16)
                if not pedaco:
                    break
                lido += len(pedaco)
                if lido > TAMANHO_MAXIMO:
                    raise ValueError("o pacote da versão passou de 200 MB")
                saida.write(pedaco)
        if lido < 1000:
            raise ValueError("o pacote da versão veio vazio")


def _partes(nome: str) -> list[str] | None:
    if not nome or nome.startswith("/") or "\\" in nome:
        return None
    partes = nome.split("/")
    if any(parte in {"", ".", ".."} or ":" in parte for parte in partes):
        return None
    return partes


def extrair(arquivo: Path, destino: Path, versao: str) -> Path:
    """Abre o pacote numa pasta nova e devolve a raiz. Recusa caminho que sai dela."""
    versao = validar_versao(versao)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    with tarfile.open(arquivo, "r:gz") as tar:
        membros = tar.getmembers()
        if not membros:
            raise ValueError("pacote vazio")
        raizes: set[str] = set()
        for membro in membros:
            partes = _partes(membro.name)
            if partes is None or membro.issym() or membro.islnk() or not (membro.isdir() or membro.isfile()):
                raise ValueError(f"pacote recusado: {membro.name!r}")
            raizes.add(partes[0])
        if len(raizes) != 1:
            raise ValueError("o pacote não tem uma pasta só")
        tar.extractall(destino, members=membros, filter="data")
    raiz = destino / next(iter(raizes))
    conferir_arvore(raiz, versao)
    return raiz


def conferir_arvore(origem: Path, versao: str) -> None:
    versao = validar_versao(versao)
    arquivo = Path(origem) / "VERSAO.txt"
    if not arquivo.is_file() or not (Path(origem) / "app.py").is_file():
        raise ValueError("o pacote não é o Cartório Gestão")
    texto = arquivo.read_text(encoding="utf-8").strip()
    if texto != versao:
        raise ValueError(f"o pacote diz {texto!r}, e o principal está na {versao}")
    app = (Path(origem) / "app.py").read_text(encoding="utf-8")
    if f'VERSION = "{versao}"' not in app:
        raise ValueError("o app.py do pacote não é desta versão")


def _texto(caminho: Path) -> str | None:
    if not caminho.is_file():
        return None
    return caminho.read_text(encoding="utf-8")


def trocar(origem: Path, destino: Path) -> bool:
    """Põe `origem` no lugar de `destino`. A anterior fica ao lado, uma geração.

    Devolve se `requirements.txt` mudou. Não mexe num repositório git: a cópia
    instalada no Mac não tem `.git`, e um checkout de quem desenvolve não pode
    ser apagado por esta troca.
    """
    origem = Path(origem)
    destino = Path(destino)
    conferir_arvore(origem, (origem / "VERSAO.txt").read_text(encoding="utf-8").strip())
    if (destino / ".git").exists():
        raise RuntimeError("não troco um repositório git")
    pai = destino.parent
    nova = pai / (destino.name + ".nova")
    anterior = pai / (destino.name + ".anterior")
    if nova.exists():
        shutil.rmtree(nova)
    shutil.copytree(origem, nova, ignore=IGNORAR_NA_COPIA, symlinks=False)
    if anterior.exists():
        shutil.rmtree(anterior)
    tinha = destino.exists()
    if tinha:
        destino.rename(anterior)
    try:
        nova.rename(destino)
    except Exception:
        if tinha and not destino.exists() and anterior.exists():
            anterior.rename(destino)
        raise
    return _texto(destino / "requirements.txt") != _texto(anterior / "requirements.txt")


def requisitos_mudaram(sistema: Path) -> bool:
    anterior = sistema.parent / (sistema.name + ".anterior")
    return _texto(sistema / "requirements.txt") != _texto(anterior / "requirements.txt")


def pip_do_venv(venv: Path) -> Path | None:
    for partes in (("bin", "pip"), ("bin", "pip3"), ("Scripts", "pip.exe")):
        candidato = venv.joinpath(*partes)
        if candidato.is_file():
            return candidato
    return None


def instalar_requisitos(sistema: Path, venv: Path | None = None) -> None:
    venv = venv or (sistema.parent / "venv")
    pip = pip_do_venv(venv)
    if pip is None:
        raise RuntimeError(f"não achei o pip em {venv}")
    requisitos = sistema / "requirements.txt"
    if not requisitos.is_file():
        raise RuntimeError("a versão nova não tem requirements.txt")
    subprocess.run([str(pip), "install", "-q", "-r", str(requisitos)], check=True)


def reiniciar_servico() -> None:
    if os.name != "posix":
        raise RuntimeError("o reinício do serviço é do macOS")
    prefixo = (os.environ.get("CG_LAUNCHD_PREFIXO") or "br.com.cartoriogestao").strip()
    if not PREFIXO_RE.fullmatch(prefixo):
        raise RuntimeError("o nome do serviço está fora do formato")
    if shutil.which("launchctl") is None:
        raise RuntimeError("não há launchctl")
    alvo = f"gui/{os.getuid()}/{prefixo}.servidor"
    subprocess.run(["launchctl", "kickstart", "-k", alvo], check=True)


def _carimbo(sistema: Path) -> Path:
    return sistema.parent / "versao-reiniciar.txt"


def _gravar_carimbo(sistema: Path, versao: str) -> None:
    caminho = _carimbo(sistema)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(validar_versao(versao) + "\n", encoding="utf-8")


def _concluir(sistema: Path, frase: str, instalar, reiniciar) -> int:
    try:
        if requisitos_mudaram(sistema):
            instalar(sistema)
        reiniciar()
    except Exception as erro:  # noqa: BLE001 — a frase vai para o sincronia.log
        print(f"versao: código no lugar, o serviço ainda não subiu com ele: {erro}")
        return 1
    carimbo = _carimbo(sistema)
    if carimbo.exists():
        carimbo.unlink()
    print(frase)
    return 0


def executar(sistema: Path, principal: str, local: str, esquema_ok: bool, *,
             baixar=None, instalar=None, reiniciar=None) -> int:
    """Uma passada da sincronia. Não baixa nem troca quando não é o caso."""
    sistema = Path(sistema)
    baixar = baixar or baixar_pacote
    instalar = instalar or (lambda pasta: instalar_requisitos(pasta))
    reiniciar = reiniciar or reiniciar_servico
    try:
        escolha = decisao(local, principal, esquema_ok)
    except ValueError as erro:
        print(f"versao: {erro}")
        return 1
    if escolha == "em_dia":
        carimbo = _carimbo(sistema)
        if carimbo.is_file() and carimbo.read_text(encoding="utf-8").strip() == local:
            return _concluir(sistema, f"versao: serviço reiniciado na {local}", instalar, reiniciar)
        print(f"versao: EM DIA {local}")
        return 0
    if escolha == "sem_publicacao":
        print(f"versao: o principal ainda não publicou a versão (aqui {local or 'nenhuma'})")
        return 0
    if escolha == "recua":
        print(f"versao: a reserva está na {local} e o principal na {principal}; não desço")
        return 0
    if escolha == "espera":
        print(f"versao: ESPERA o esquema (principal {principal}, aqui {local or 'nenhuma'})")
        return 0
    _gravar_carimbo(sistema, principal)
    try:
        with tempfile.TemporaryDirectory(prefix="cg-versao-") as tmp_nome:
            tmp = Path(tmp_nome)
            pacote = tmp / "codigo.tar.gz"
            baixar(principal, pacote)
            origem = extrair(pacote, tmp / "src", principal)
            trocar(origem, sistema)
    except Exception as erro:  # noqa: BLE001 — o código que está rodando continua
        print(f"versao: não troquei o código: {erro}")
        return 1
    return _concluir(
        sistema, f"versao: {local or 'nenhuma'} -> {principal}", instalar, reiniciar)

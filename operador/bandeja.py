"""A BANDEJA DO SUPERUSUÁRIO — por onde a tela do sistema fala com a ponte.

POR QUE ARQUIVO, E NÃO O BANCO — 12/11/2026, pedido do oficial: «não quero que
o superusuário seja acessível só pelo Telegram, quero acessar também pelo
sistema». A tela precisa funcionar nos dois servidores, e o banco do reserva é
réplica: só lê. Então o pedido da tela vira um arquivo em
`<dados>/operador/bandeja/entrada/`, a ponte o colhe, e o que a ponte está
fazendo fica em `bandeja/estado.json`, que a tela lê.

    tela do sistema ──pedir()/comandar()──► bandeja/entrada/*.json ──colher()──► ponte
    tela do sistema ◄──ler_estado()──────── bandeja/estado.json ◄─gravar_estado()─ ponte

O servidor do sistema e a ponte são processos diferentes (no Windows, contas
diferentes): a pasta `operador` é o único lugar que os dois enxergam.

SÓ A BIBLIOTECA PADRÃO, E NENHUM IMPORT DE VIZINHO. O servidor do sistema
importa este módulo como `operador.bandeja`; a ponte, como `bandeja`. Quem
recebe `base` é quem sabe onde fica `<dados>/operador`.
"""
from __future__ import annotations

import hmac
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

#: Depois de tantas frases erradas seguidas, a porta tranca por este tempo.
ERROS_ATE_TRANCAR = 5
MINUTOS_TRANCADO = 15
#: A ponte regrava o estado a cada ~15 s; mais velho que isto, ela está parada.
VIVA_HA_NO_MAXIMO = 90


# ------------------------------------------------------------- a configuração

def ler_configuracao(caminho: Any) -> dict[str, str]:
    """As linhas CHAVE=valor do `operador.cred`. Aspas em volta saem."""
    dados: dict[str, str] = {}
    try:
        linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
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


def nome_seguro(nome: Any) -> str:
    """O nome de um anexo, sem caminho e sem caractere que o shell estranhe."""
    nome = Path(str(nome or "").replace("\\", "/")).name
    nome = re.sub(r"[^\w.\-]+", "_", nome, flags=re.UNICODE).strip("._")
    return nome[:80] or "anexo"


# ------------------------------------------------------------------ os arquivos

def _gravar(caminho: Path, dados: Any) -> None:
    """Grava inteiro ou não grava: quem lê nunca pega o arquivo pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    provisorio = caminho.with_name(caminho.name + f".{uuid.uuid4().hex[:6]}.novo")
    provisorio.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    provisorio.replace(caminho)


def _ler(caminho: Path, padrao: Any) -> Any:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def pasta(base: Any) -> Path:
    alvo = Path(base) / "bandeja"
    (alvo / "entrada").mkdir(parents=True, exist_ok=True)
    return alvo


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005


def _novo_id() -> str:
    """O número de um pedido. Começa pela hora até o microssegundo: a ordem
    alfabética dos arquivos da bandeja é a ordem em que chegaram."""
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:4]  # noqa: DTZ005


def _depositar(base: Any, dados: dict) -> str:
    dados = {"id": _novo_id(), "quando": _agora(), **dados}
    _gravar(pasta(base) / "entrada" / f"{dados['id']}.json", dados)
    return dados["id"]


def pedir(base: Any, texto: str, anexos: Any = (), *, de: str = "", tela: str = "") -> str:
    """Um pedido do oficial, vindo da tela. Devolve o número do pedido."""
    return _depositar(base, {
        "tipo": "pedido", "texto": str(texto or "").strip(),
        "anexos": [str(a) for a in anexos or ()], "de": str(de or ""),
        "tela": str(tela or "")[:300]})


def comandar(base: Any, comando: str, texto: str = "", *, de: str = "") -> str:
    """Um comando da tela: `novo`, `parar`, `confirmo` ou `lembrar`."""
    return _depositar(base, {"tipo": "comando", "comando": str(comando or "").strip().lower(),
                             "texto": str(texto or "").strip(), "de": str(de or "")})


def colher(base: Any) -> list[dict]:
    """O que a tela deixou, na ordem em que chegou. Cada arquivo sai uma vez."""
    colhidos = []
    for arquivo in sorted((pasta(base) / "entrada").glob("*.json")):
        dados = _ler(arquivo, None)
        try:
            arquivo.unlink()
        except OSError:
            continue        # outro processo levou: não é meu
        if isinstance(dados, dict) and dados.get("tipo"):
            colhidos.append(dados)
    return colhidos


def gravar_estado(base: Any, estado: dict) -> None:
    """O que a ponte está fazendo agora — a tela lê. Leva a hora da gravação."""
    _gravar(pasta(base) / "estado.json", {**estado, "gravado_em": time.time()})


def ler_estado(base: Any, agora: float | None = None) -> dict:
    """O estado da ponte, com `viva` dizendo se ela ainda está escrevendo."""
    estado = _ler(pasta(base) / "estado.json", {})
    if not isinstance(estado, dict):
        estado = {}
    agora = time.time() if agora is None else agora
    estado["viva"] = 0 <= agora - float(estado.get("gravado_em") or 0) <= VIVA_HA_NO_MAXIMO
    return estado


# ------------------------------------------------------------------ a frase

def frase_confere(base: Any, dita: str, certa: str, agora: float | None = None) -> tuple[bool, str]:
    """Confere a frase-senha das duas portas (Telegram e tela) e conta os
    erros num lugar só. Devolve (confere?, recado para quem errou)."""
    agora = time.time() if agora is None else agora
    arquivo = Path(base) / "frase_tentativas.json"
    conta = _ler(arquivo, {})
    if not isinstance(conta, dict):
        conta = {}
    ate = float(conta.get("trancado_ate") or 0)
    if agora < ate:
        hora = datetime.fromtimestamp(ate).strftime("%H:%M")  # noqa: DTZ006
        return False, f"Trancado por frases erradas. Tente de novo depois das {hora}."
    if certa and hmac.compare_digest(str(dita or "").strip().encode("utf-8"),
                                     str(certa).strip().encode("utf-8")):
        _gravar(arquivo, {"erros": 0, "trancado_ate": 0})
        return True, ""
    erros = int(conta.get("erros") or 0) + 1
    if erros >= ERROS_ATE_TRANCAR:
        _gravar(arquivo, {"erros": 0, "trancado_ate": agora + MINUTOS_TRANCADO * 60})
        return False, (f"Frase errada {ERROS_ATE_TRANCAR} vezes: tranquei por "
                       f"{MINUTOS_TRANCADO} minutos.")
    _gravar(arquivo, {"erros": erros, "trancado_ate": 0})
    return False, f"Frase errada ({erros} de {ERROS_ATE_TRANCAR})."

"""TRAVA DE SEGURANCA DO SANDBOX — Centrais nunca batem em producao.

Ponto unico de politica (05/10/2026, alinhado Notas/Imoveis):
  - deteccao: CARTORIO_GESTAO_SANDBOX=1 OU CARTORIO_GESTAO_DATA sob SANDBOX;
  - em sandbox, hosts de PRODUCAO conhecidos sao recusados OU desviados
    para o simulador local; NUNCA seguem para a URL real;
  - o gancho do transporte comum e centrais_http.requisitar (RCPN/Protesto
    edita); Notas/Imoveis registram hosts extras via registrar_host_producao
    sem fork deste modulo.

Listas iniciais (RCPN/Protesto + 4 hosts Notas/Imoveis na deny-list):
  - com simulador: SIRC/CRC (:8917), ON-RCPN (:8915), Resolve (:8912),
    CENPROT (:8911), CRA producao (:8910);
  - deny pura (sem simulador): api.registrodeimoveis.org.br,
    serventia-api.onr.org.br, auth.id.onr.org.br, pessoas.e-notariado.org.br;
  - homolog liberada: testes-api.registrodeimoveis.org.br,
    pessoas-hml.e-notariado.org.br.

NAO fala com producao. NAO inventa CNS/CNPJ/IP da serventia.
"""
from __future__ import annotations

import os
import socket
import threading
import urllib.parse
from typing import Any

MARCA = "CARTORIO_GESTAO_SANDBOX"
VAR_DADOS = "CARTORIO_GESTAO_DATA"

# Portas dos simulados (SANDBOX/ambiente.py).
PORTA_CRA = 8910
PORTA_CENPROT = 8911
PORTA_RESOLVE = 8912
PORTA_ONRCPN = 8915
PORTA_REGISTRO_CIVIL = 8917   # CRC + SIRC

# Host de PRODUCAO -> porta do SIMULADOR (desvio obrigatorio no sandbox).
_HOSTS_PARA_SIMULADOR: dict[str, int] = {
    # SIRC / CRC
    "sirc.dataprev.gov.br": PORTA_REGISTRO_CIVIL,
    "ws.registrocivil.org.br": PORTA_REGISTRO_CIVIL,
    "wsh.registrocivil.org.br": PORTA_REGISTRO_CIVIL,
    "sistema.registrocivil.org.br": PORTA_REGISTRO_CIVIL,
    # ON-RCPN
    "servicosh.registrocivil.org.br": PORTA_ONRCPN,
    "certidaoh.registrocivil.org.br": PORTA_ONRCPN,
    "servicos.registrocivil.org.br": PORTA_ONRCPN,
    # Resolve
    "resolve.cenprot.org.br": PORTA_RESOLVE,
    "api.resolve.cenprot.org.br": PORTA_RESOLVE,
    "api-testes.resolve.cenprot.org.br": PORTA_RESOLVE,
    "api-homolog.resolve.cenprot.org.br": PORTA_RESOLVE,
    # CENPROT / CRA (producao)
    "wspub.cenprotnacional.org.br": PORTA_CENPROT,
    "crama.crabr.com.br": PORTA_CRA,
}

# PRODUCAO sem simulador nesta trava: recusa clara (pedido Notas/Imoveis).
_HOSTS_PRODUCAO_RECUSAR: set[str] = {
    "api.registrodeimoveis.org.br",
    "serventia-api.onr.org.br",
    "auth.id.onr.org.br",
    "pessoas.e-notariado.org.br",
}

# Homologacao explicita: passa (sandbox_liga pode desviar se quiser).
_HOSTS_HOMOLOG_LIBERADOS: set[str] = {
    "testes-api.registrodeimoveis.org.br",
    "pessoas-hml.e-notariado.org.br",
    "crama.cra21.com.br",  # CRA homolog
}

# Sufixos que, sem mapa e sem liberacao, nunca saem do sandbox.
SUFIXOS_BLOQUEADOS: tuple[str, ...] = (
    "dataprev.gov.br",
    "registrocivil.org.br",
    "resolve.cenprot.org.br",
    "cenprotnacional.org.br",
    "crabr.com.br",
    "registrodeimoveis.org.br",
    "onr.org.br",
    "e-notariado.org.br",
)

HOSTS_LOCAIS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})
PRAZO_DO_PROBE = 0.4

_lock = threading.Lock()


class SandboxTravaRecusou(RuntimeError):
    """Sandbox recusou a chamada: iria a producao, ou o simulador esta fora."""


def e_sandbox() -> bool:
    """True quando esta instalacao NAO pode falar com Central de verdade."""
    if os.environ.get(MARCA, "").strip() == "1":
        return True
    dados = (os.environ.get(VAR_DADOS, "") or "").replace("/", chr(92)).lower()
    if (chr(92) + "sandbox" + chr(92)) in dados:
        return True
    return False


def registrar_host_producao(host: str, *, porta_simulador: int | None = None) -> None:
    """API estavel para Notas/Imoveis (e quem mais) sem fork deste modulo.

    - porta_simulador=None  -> deny-list (recusa clara no sandbox)
    - porta_simulador=N     -> desvio obrigatorio para 127.0.0.1:N
    Host ja liberado como homolog e removido da liberacao ao registrar.
    """
    nome = str(host or "").strip().lower()
    if not nome or nome in HOSTS_LOCAIS:
        raise ValueError(f"Host invalido para registro: «{host}».")
    with _lock:
        _HOSTS_HOMOLOG_LIBERADOS.discard(nome)
        if porta_simulador is None:
            _HOSTS_PARA_SIMULADOR.pop(nome, None)
            _HOSTS_PRODUCAO_RECUSAR.add(nome)
        else:
            porta = int(porta_simulador)
            if porta <= 0 or porta > 65535:
                raise ValueError(f"Porta de simulador invalida: {porta_simulador}.")
            _HOSTS_PRODUCAO_RECUSAR.discard(nome)
            _HOSTS_PARA_SIMULADOR[nome] = porta


def registrar_host_homolog(host: str) -> None:
    """Libera um host de homologacao explicita no sandbox."""
    nome = str(host or "").strip().lower()
    if not nome:
        raise ValueError("Host de homologacao vazio.")
    with _lock:
        _HOSTS_PRODUCAO_RECUSAR.discard(nome)
        _HOSTS_PARA_SIMULADOR.pop(nome, None)
        _HOSTS_HOMOLOG_LIBERADOS.add(nome)


def hosts_producao_conhecidos() -> frozenset[str]:
    """Snapshot: deny + mapeados para simulador (para testes/inspecao)."""
    with _lock:
        return frozenset(_HOSTS_PRODUCAO_RECUSAR) | frozenset(_HOSTS_PARA_SIMULADOR)


def _porta_aberta(host: str, porta: int) -> bool:
    try:
        with socket.create_connection((host, int(porta)), timeout=PRAZO_DO_PROBE):
            return True
    except OSError:
        return False


def garantir_simulador(porta: int, host_origem: str = "") -> None:
    """Recusa se o simulador local nao estiver escutando."""
    porta = int(porta)
    if _porta_aberta("127.0.0.1", porta):
        return
    origem = f" (pedido a {host_origem})" if host_origem else ""
    raise SandboxTravaRecusou(
        f"Sandbox: o simulador em 127.0.0.1:{porta} nao esta no ar{origem}. "
        f"A chamada foi RECUSADA — o sandbox NUNCA fala com a Central de "
        f"verdade. Suba o sandbox (rodar.py) ou o servico simulado e tente "
        f"de novo; nada foi enviado.")


def destino_seguro(host: Any, porta: int | None = None) -> tuple[str, int]:
    """No sandbox: (127.0.0.1, porta_sim) ou estoura; fora: inalterado."""
    nome = str(host or "").strip().lower()
    porta_in = int(porta or 443)
    if not e_sandbox():
        return str(host or ""), porta_in
    if not nome:
        raise SandboxTravaRecusou("Sandbox: chamada a Central sem host — recusada.")
    if nome in HOSTS_LOCAIS:
        with _lock:
            portas_sim = set(_HOSTS_PARA_SIMULADOR.values())
        if porta_in in portas_sim:
            garantir_simulador(porta_in, nome)
        return nome, porta_in
    with _lock:
        if nome in _HOSTS_HOMOLOG_LIBERADOS:
            return str(host or ""), porta_in
        if nome in _HOSTS_PRODUCAO_RECUSAR:
            raise SandboxTravaRecusou(
                f"Sandbox: o host de PRODUCAO «{nome}» esta na deny-list. "
                f"A chamada foi RECUSADA — nao ha simulador para este host "
                f"nesta trava; use a homologacao liberada ou registre um "
                f"simulador com registrar_host_producao(..., porta_simulador=N).")
        porta_sim = _HOSTS_PARA_SIMULADOR.get(nome)
    if porta_sim is not None:
        garantir_simulador(porta_sim, nome)
        return "127.0.0.1", porta_sim
    for sufixo in SUFIXOS_BLOQUEADOS:
        if nome == sufixo or nome.endswith("." + sufixo):
            raise SandboxTravaRecusou(
                f"Sandbox: o host «{nome}» e de Central real e nao tem "
                f"simulador mapeado. A chamada foi RECUSADA — nao se fala "
                f"com producao a partir do sandbox.")
    return str(host or ""), porta_in


def proteger_url(url: str) -> str:
    """Reescreve URL protegida para o simulador, ou recusa. Fora: intacta."""
    if not e_sandbox():
        return url
    bruto = str(url or "")
    p = urllib.parse.urlsplit(bruto)
    nome = (p.hostname or "").strip().lower()
    if not nome:
        raise SandboxTravaRecusou(f"Sandbox: URL sem host «{bruto}» — recusada.")
    if p.scheme == "https":
        porta_url = p.port or 443
    elif p.scheme == "http":
        porta_url = p.port or 80
    else:
        porta_url = p.port or 443
    novo_host, nova_porta = destino_seguro(nome, porta_url)
    if novo_host == nome and nova_porta == porta_url:
        return bruto
    esquema = p.scheme or "https"
    netloc = f"{novo_host}:{nova_porta}"
    return urllib.parse.urlunsplit(
        (esquema, netloc, p.path or "/", p.query, p.fragment))


def resumo() -> str:
    if not e_sandbox():
        return "trava sandbox: inativa (nao e sandbox)"
    with _lock:
        n_sim = len(_HOSTS_PARA_SIMULADOR)
        n_deny = len(_HOSTS_PRODUCAO_RECUSAR)
    return (
        f"trava sandbox: ARMADA — {n_sim} host(s)→simulador, "
        f"{n_deny} na deny-list; producao recusada se simulador fora")


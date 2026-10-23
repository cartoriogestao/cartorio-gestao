"""QUEM LÊ O QUE MORA NO DISCO DO SERVIDOR — a ACL da pasta das cópias e dos
arquivos de segredo (lote LX14, 19/10/2026; A7 e B6 do LS03, M5 do LS01).

O ACHADO
    `secret.key`, os `*.cred`, o `servidor.log` e a pasta das cópias nasciam
    com a permissão que a pasta-mãe dava. Em `%PROGRAMDATA%` isso costuma ser
    «Usuários: leitura»: qualquer conta do servidor lia a chave que assina o
    cookie (e forjava a sessão do ADMIN), as senhas das Centrais e o backup
    inteiro — banco, digitalizações e o acervo do E-Ofício.

O QUE SE FAZ
    No Windows, `icacls` tira a herança e deixa só três contas, com controle
    total: SYSTEM (a conta do serviço — a tarefa agendada do instalador roda
    como SYSTEM), Administradores, e a conta que está rodando o processo. A
    terceira está aí para o sistema não trancar a si mesmo quando roda fora do
    serviço (SANDBOX, suíte de testes, servidor iniciado à mão). Fora do
    Windows, `chmod` 0600 no arquivo e 0700 na pasta.

    A conta do processo vem do `whoami /user`, pelo SID, e não do nome: nome de
    conta muda com o idioma do Windows («Administradores»/«Administrators») e
    com o domínio; o SID não. Os dois de fábrica vão pelo SID bem conhecido
    (`*S-1-5-18`, `*S-1-5-32-544`) pela mesma razão.

FALHAR É AVISO, E NUNCA DERRUBA
    Pasta num disco FAT/exFAT (pendrive, disco externo) não tem ACL; `icacls`
    pode não existir num Windows mexido; o processo pode não ter o direito de
    trocar a ACL. Nada disso pode impedir o backup de ser gravado nem o
    servidor de subir — backup que falta é pior que backup legível. A falha
    vira uma linha de aviso no log (`cartorio.permissoes`) e a função devolve a
    frase, para quem quiser mostrá-la.

    Se a conta do processo não puder ser descoberta, a herança NÃO é tirada:
    tirar sem pôr a própria conta poderia deixar o processo sem ler o arquivo
    que ele mesmo grava.

UMA VEZ POR CAMINHO, POR PROCESSO
    `pasta_de_backups` é chamada a cada backup e a cada tela; rodar `icacls`
    toda vez gastaria um processo filho sem mudar nada.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

LOG = logging.getLogger("cartorio.permissoes")

#: SYSTEM e Administradores, pelos SIDs bem conhecidos.
SID_DO_SERVICO = "*S-1-5-18"
SID_DOS_ADMINISTRADORES = "*S-1-5-32-544"

#: Os arquivos de segredo da pasta de dados (B6): a chave do cookie, as
#: chaves dos cofres, as credenciais e a senha do PostgreSQL, quando a casa a
#: puser num `pgpass.conf` (ver `docs/SEGURANCA_REDE.md`). O log do servidor
#: mora em `logs/`.
# `*.pfx` entrou em 22/10/2026 (M6): o certificado A1 da NFS-e mora ao lado.
SEGREDOS_DA_PASTA = ("secret.key", "*.key", "*.cred", "pgpass.conf", "*.pfx")
LOG_DO_SERVIDOR = Path("logs") / "servidor.log"

_FEITOS: set[str] = set()


def _e_windows() -> bool:
    return os.name == "nt"


def _sid_do_processo(rodar: Callable[..., Any]) -> str | None:
    """O SID da conta que roda este processo, ou None se não deu para saber."""
    try:
        r = rodar(["whoami", "/user", "/fo", "csv", "/nh"],
                  capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(r, "returncode", 1) != 0:
        return None
    partes = [p.strip().strip('"') for p in str(r.stdout or "").strip().split(",")]
    sid = partes[-1] if partes else ""
    return f"*{sid}" if sid.upper().startswith("S-1-") else None


def _icacls(alvo: str, pasta: bool, rodar: Callable[..., Any]) -> str | None:
    """Roda o `icacls`; devolve o problema, ou None se deu certo."""
    proprio = _sid_do_processo(rodar)
    if not proprio:
        return ("não descobri a conta que roda o sistema (whoami); a herança "
                "da permissão ficou como estava")
    heranca = "(OI)(CI)F" if pasta else "F"
    comando = ["icacls", alvo, "/inheritance:r", "/grant:r"]
    comando += [f"{sid}:{heranca}" for sid in
                dict.fromkeys((SID_DO_SERVICO, SID_DOS_ADMINISTRADORES, proprio))]
    try:
        r = rodar(comando, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as erro:
        return f"o icacls não rodou: {type(erro).__name__}: {erro}"
    if getattr(r, "returncode", 1) != 0:
        saida = " ".join(str(r.stderr or r.stdout or "").split())[:300]
        return f"o icacls recusou (código {r.returncode}): {saida or 'sem explicação'}"
    return None


def restringir(caminho: Any, *, pasta: bool | None = None,
               rodar: Callable[..., Any] | None = None,
               windows: bool | None = None, de_novo: bool = False) -> str | None:
    """Deixa `caminho` legível só pelo serviço e pelos administradores.

    Devolve None quando deu certo (ou já tinha sido feito neste processo), e a
    frase do problema quando não deu — a frase também vai ao log, como aviso.
    `rodar` e `windows` existem para o teste; `caminho` pode trazer `*` no
    nome do arquivo, que o `icacls` aceita (`C:\\...\\*.cred`).
    """
    rodar = rodar or subprocess.run
    alvo = str(caminho)
    chave = alvo.lower()
    if chave in _FEITOS and not de_novo and "*" not in Path(alvo).name:
        return None
    no_windows = _e_windows() if windows is None else windows
    e_pasta = Path(alvo).is_dir() if pasta is None else pasta
    if no_windows:
        problema = _icacls(alvo, e_pasta, rodar)
    elif "*" in Path(alvo).name:
        problema = None
        for achado in sorted(Path(alvo).parent.glob(Path(alvo).name)):
            problema = restringir(achado, pasta=False, rodar=rodar,
                                  windows=False, de_novo=de_novo) or problema
    else:
        try:
            os.chmod(alvo, 0o700 if e_pasta else 0o600)
            problema = None
        except OSError as erro:
            problema = f"não consegui ajustar a permissão: {erro}"
    if problema:
        LOG.warning("PERMISSAO NAO AJUSTADA em %s: %s", alvo, problema)
        return problema
    # O curinga não se guarda: o `*.cred` de amanhã ainda não existe hoje.
    if "*" not in Path(alvo).name:
        _FEITOS.add(chave)
    return None


def proteger_segredos(pasta_de_dados: Any, *,
                      rodar: Callable[..., Any] | None = None,
                      windows: bool | None = None) -> list[str]:
    """B6: `secret.key`, `*.key`, `*.cred` e `logs/servidor.log`, na subida.

    Só mexe no que existe. Devolve as frases dos problemas (lista vazia = tudo
    certo). Arquivo de credencial gravado depois da subida pega a permissão na
    próxima — e os do cofre (`cofre_cred`) já nascem restritos.
    """
    base = Path(pasta_de_dados)
    problemas: list[str] = []
    for padrao in SEGREDOS_DA_PASTA:
        if not any(base.glob(padrao)):
            continue
        problema = restringir(base / padrao, pasta=False, rodar=rodar, windows=windows)
        if problema:
            problemas.append(f"{padrao}: {problema}")
    log = base / LOG_DO_SERVIDOR
    if log.is_file():
        problema = restringir(log, pasta=False, rodar=rodar, windows=windows)
        if problema:
            problemas.append(f"{LOG_DO_SERVIDOR}: {problema}")
    return problemas

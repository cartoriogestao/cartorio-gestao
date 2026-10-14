"""Onde ficam as cópias do banco — e o que pode morar ao lado dele.

    «tiremos o aprendizado, nas pastas do sistema vamos organizar o que eh
     importante e o que nao eh importante. backup e coisas nao importantes nao
     devem ficar na mesma pasta do banco de dados» — o oficial, 11/10/2026

O QUE ACONTECEU
    Em 11/10/2026, limpando `C:\\ProgramData\\CartorioGestao`, o banco da
    serventia foi apagado junto com as cópias. A pasta tinha ~450 arquivos, e
    69 deles eram cópias com o nome quase igual ao do banco
    (`cartorio_gestao.antes-…sqlite3`), deixadas ali por 16 scripts de conserto
    e por duas telas. Arquivo grande não vai para a Lixeira: voltou pelo Proton
    Drive, inteiro até 14:31. No mesmo dia as cópias e os rascunhos foram
    movidos para `C:\\CartorioGestao_Copias`.

A REGRA, NUM LUGAR SÓ
    Nenhuma cópia nasce ao lado do banco. Quem tira cópia antes de mexer pede
    `pasta_antes_de_mexer(banco)`; quem gera o backup pede
    `pasta_de_backups(...)`. Na produção as duas ficam em
    `C:\\CartorioGestao_Copias`; fora dela (SANDBOX, testes, instalação de
    outra casa) ficam numa SUBPASTA da pasta do banco — nunca soltas ao lado
    dele. `CARTORIO_GESTAO_COPIAS` no ambiente troca a raiz.

    E a pasta das cópias não cresce para sempre: guarda as
    `GUARDAR_ANTES_DE_MEXER` mais novas. Em 06/10/2026 o disco chegou a 24 MB
    livres por causa delas.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

#: A pasta das cópias da produção, escolhida pelo oficial em 11/10/2026.
RAIZ_DA_PRODUCAO = Path(r"C:\CartorioGestao_Copias")

#: Quantas cópias «antes de mexer» se guardam. As mais velhas saem sozinhas.
GUARDAR_ANTES_DE_MEXER = 15

#: O que pode morar na pasta do banco — medido contra o código instalado em
#: 11/10/2026. O resto é cópia, rascunho ou sobra, e a conferência acusa.
FICA_NA_PASTA_DO_BANCO = frozenset({
    "cartorio_gestao.sqlite3", "cartorio_gestao.sqlite3-wal", "cartorio_gestao.sqlite3-shm",
    "cartorio_gestao.sqlite3-journal",
    "acervo_eoficio.sqlite3", "acervo_eoficio.sqlite3-wal", "acervo_eoficio.sqlite3-shm",
    "secret.key", "install.json", "disputas_de_escrita.log", "iniciar_servidor_servico.cmd",
    "serventia_local_atual.json",
})
PASTAS_DA_PASTA_DO_BANCO = frozenset({
    "arquivos", "runtime", "updates", "libreoffice_perfil", "logs", "crc_selecoes",
    "importacoes_pendentes", "backups_patch", "programas_onr", "$Temp",
})


def _e_a_producao(pasta_do_banco: Path) -> bool:
    base = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    try:
        return Path(pasta_do_banco).resolve() == (Path(base) / "CartorioGestao").resolve()
    except OSError:
        return False


def raiz_das_copias(pasta_do_banco: Path) -> Path:
    """A raiz das cópias: o ambiente, a da produção, ou uma subpasta — nunca a própria pasta."""
    configurada = (os.environ.get("CARTORIO_GESTAO_COPIAS") or "").strip()
    if configurada:
        return Path(configurada)
    if _e_a_producao(pasta_do_banco):
        return RAIZ_DA_PRODUCAO
    return Path(pasta_do_banco) / "copias"


def pasta_de_backups(pasta_do_banco: Path, configurada: str | None = None) -> Path:
    """A pasta do backup completo. `settings.backup_dir`, quando preenchido, manda."""
    if (configurada or "").strip():
        pasta = Path(configurada.strip()).expanduser()
    else:
        pasta = raiz_das_copias(pasta_do_banco) / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


_COPIA = re.compile(r"\.sqlite3$", re.I)


def pasta_antes_de_mexer(banco: Path, guardar: int = GUARDAR_ANTES_DE_MEXER) -> Path:
    """A pasta da cópia que se tira antes de mexer no banco. Já sai podada.

    Poda ANTES da cópia nova, deixando lugar para ela: guarda `guardar - 1`
    das que já estavam. Só mexe em `.sqlite3` desta pasta, que é só de cópias.
    """
    pasta = raiz_das_copias(Path(banco).parent) / "antes_de_mexer"
    pasta.mkdir(parents=True, exist_ok=True)
    copias = sorted((p for p in pasta.iterdir() if p.is_file() and _COPIA.search(p.name)),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    for velha in copias[max(guardar - 1, 0):]:
        try:
            velha.unlink()
        except OSError:
            pass                       # cópia aberta por alguém: fica para a próxima
    return pasta


def destino_da_copia(copia: Path, banco: Path) -> Path:
    """A cópia que um script ia gravar ao lado do banco, com o mesmo nome, no lugar certo.

    É o que os 16 scripts de `tools/` chamam logo depois de montar o nome da
    cópia: o nome continua o que cada um escolheu (é ele que diz «antes de
    quê»); só a pasta muda.
    """
    return pasta_antes_de_mexer(Path(banco)) / Path(copia).name


def estranhos_na_pasta_do_banco(pasta_do_banco: Path) -> list[Path]:
    """O que está na pasta do banco e não devia estar. Só lê."""
    pasta = Path(pasta_do_banco)
    if not pasta.is_dir():
        return []
    fora = []
    for p in pasta.iterdir():
        if p.is_dir():
            # PASTA VAZIA NÃO É SOBRA: a versão instalada até 11/10/2026 recria
            # `backups\` vazia ao subir, e acusar isso seria o alarme que soa sempre.
            if (p.name not in PASTAS_DA_PASTA_DO_BANCO and p.name != "copias"
                    and any(p.iterdir())):
                fora.append(p)
        elif p.name not in FICA_NA_PASTA_DO_BANCO and not p.name.endswith(".cred"):
            fora.append(p)
    return sorted(fora, key=lambda p: p.name)

"""Migracao B0 da sanitizacao: dados da serventia saem do codigo e vao para `settings`.

O QUE FAZ
    Para cada chave de `serventia.CAMPOS` que estiver AUSENTE ou EM BRANCO na
    tabela `settings`, grava o valor do PERFIL LOCAL da serventia. Chave ja
    preenchida NUNCA e sobrescrita. Rodar de novo nao faz nada (idempotente).
    Antes de escrever qualquer coisa, faz BACKUP do banco (API de backup do
    SQLite — copia consistente mesmo com o sistema no ar e o WAL aberto).

POR QUE O PERFIL LOCAL NAO ESTA NESTE ARQUIVO
    Este script vai para o repositorio publico. Os valores reais (nome, CNS,
    CNPJ, endereco...) ficam num JSON NA PASTA DE DADOS, ao lado do banco —
    `<CARTORIO_GESTAO_DATA>/serventia_local_atual.json` —, que nunca entra no
    Git. E o «LOCAL_ATUAL» da casa.

    Para gera-lo a partir do codigo ANTIGO (quando `serventia.PADRAO` ainda
    traz os dados da casa), rode uma vez com `--gerar-perfil`. Depois que
    `serventia.py` virar generico, `--gerar-perfil` recusa (nao ha mais o que
    copiar) — aí o perfil se copia de uma instalacao que ja o tenha, ou se
    preenche na tela de Configuracoes.

ONDE ESTA O BANCO (nao se inventa caminho)
    1. `--banco CAMINHO`, se informado;
    2. `CARTORIO_GESTAO_DATA/cartorio_gestao.sqlite3` (mesma regra de
       `app.get_data_dir`);
    3. `../ambiente.py` do SANDBOX (`ambiente.DADOS`), quando o script roda
       dentro de `SANDBOX/sistema`.
    Se o caminho cair dentro de `%PROGRAMDATA%\\CartorioGestao` (a PRODUCAO),
    o script RECUSA, a menos que se passe `--sou-a-producao` — a producao so
    se migra pelo ciclo de atualizacao oficial.

USO
    python tools/migrar_settings_serventia_b0.py --gerar-perfil   # 1x, codigo antigo
    python tools/migrar_settings_serventia_b0.py --simular        # mostra, nao grava
    python tools/migrar_settings_serventia_b0.py                  # grava (com backup)

    Nunca imprime senha (nao ha senha em `CAMPOS`); imprime as CHAVES gravadas
    e o valor so com `--mostrar-valores`.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

SISTEMA = Path(__file__).resolve().parent.parent
if str(SISTEMA) not in sys.path:
    sys.path.insert(0, str(SISTEMA))

NOME_DO_BANCO = "cartorio_gestao.sqlite3"
NOME_DO_PERFIL = "serventia_local_atual.json"
PREFIXO_DO_BACKUP = "cartorio_gestao.pre_b0_serventia_"


class MigracaoRecusou(RuntimeError):
    """Impedimento com mensagem pronta para o console."""


# ------------------------------------------------------------ onde esta tudo

def pasta_da_producao() -> Path:
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "CartorioGestao"


def _dentro(caminho: Path, pasta: Path) -> bool:
    try:
        caminho.resolve().relative_to(pasta.resolve())
        return True
    except (ValueError, OSError):
        return False


def localizar_banco(banco: str | None = None) -> tuple[Path, str]:
    """(caminho do banco, de onde veio). Nao inventa: so as tres fontes."""
    if banco:
        return Path(banco).expanduser().resolve(), "--banco"
    override = os.environ.get("CARTORIO_GESTAO_DATA")
    if override:
        return (Path(override).expanduser().resolve() / NOME_DO_BANCO,
                "CARTORIO_GESTAO_DATA")
    ambiente_py = SISTEMA.parent / "ambiente.py"
    if ambiente_py.is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location("_ambiente_sandbox", ambiente_py)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        return Path(mod.DADOS).resolve() / NOME_DO_BANCO, "ambiente.DADOS (SANDBOX)"
    raise MigracaoRecusou(
        "Nao sei onde esta o banco: informe --banco ou defina "
        "CARTORIO_GESTAO_DATA. (Nao adivinho o caminho — o padrao do Windows "
        "seria a PRODUCAO.)")


def conferir_alvo(banco: Path, *, sou_a_producao: bool) -> None:
    if not banco.is_file():
        raise MigracaoRecusou(f"Banco nao encontrado: {banco}")
    if _dentro(banco, pasta_da_producao()) and not sou_a_producao:
        raise MigracaoRecusou(
            f"O banco {banco} esta na pasta da PRODUCAO. A producao so se "
            "migra pelo ciclo de atualizacao oficial; se for isso, repita "
            "com --sou-a-producao.")


# ------------------------------------------------------------ o perfil local

# As duas chaves NOVAS do B0. Entram aqui tambem porque a migracao roda com o
# `serventia.py` ANTIGO (antes de o codigo virar generico), cujo CAMPOS ainda
# nao as conhece.
CAMPOS_NOVOS_B0 = ("serventia_brasao", "selador_host")

# CONFIGURAÇÕES DA INSTALAÇÃO que saíram do código na B2 (09/10/2026): não são
# a identidade da serventia (não vão para `serventia.PADRAO`), mas eram valores
# desta casa escritos em constante — a pasta da CRA (`gestor_protesto`), a conta
# Google do Next Cloud SAS (`onr_carga`) e os CEPs por município do extrator de
# endereço do ONR (`onr_endereco_do_teor`, «Cidade=00000000» por linha).
CAMPOS_DA_INSTALACAO_B2 = ("protesto_pasta_cra", "onr_conta_google",
                           "onr_ceps_por_cidade")

# AS SEMENTES QUE A B2b ESVAZIOU (10/10/2026): `database.DEFAULT_SETTINGS`
# guardava o titular (como o RI o lê), os feriados municipais e a pasta do
# espelho do backup desta casa. Na instalação nova elas vêm daqui.
CAMPOS_DA_INSTALACAO_B2B = ("ri_registrador", "ri_feriados_locais",
                            "backup_espelho",
                            # a distribuição da equipe pelo gestor (11/10/2026)
                            "gestor_distribuicao")


def campos() -> tuple[str, ...]:
    import serventia
    base = tuple(serventia.CAMPOS)
    extras = CAMPOS_NOVOS_B0 + CAMPOS_DA_INSTALACAO_B2 + CAMPOS_DA_INSTALACAO_B2B
    return base + tuple(k for k in extras if k not in base)


def _host_do_selador_no_codigo() -> str:
    """O host que o codigo ANTIGO tinha como o selador da casa (sem literal aqui)."""
    try:
        import selador
    except Exception:  # noqa: BLE001 — sem selador, sem sugestao
        return ""
    base = getattr(selador, "BASE_OBSERVADA_NA_SERVENTIA", "") or ""
    return urlsplit(base).hostname or ""


def perfil_do_codigo_antigo() -> dict[str, str]:
    """O LOCAL_ATUAL extraido de `serventia.PADRAO` do codigo antigo.

    Recusa se `PADRAO` ja for a semente generica — copiar placeholder para o
    banco seria «migrar» o vazio.
    """
    import serventia
    padrao = dict(serventia.PADRAO)
    generico = dict(getattr(serventia, "PADRAO_GENERICO", {}) or {})
    if generico and all(padrao.get(k) == v for k, v in generico.items()):
        raise MigracaoRecusou(
            "serventia.PADRAO ja e generico: nao ha dado da casa no codigo "
            "para copiar. Traga o perfil de outra instalacao ou preencha "
            "Configuracoes -> Serventia.")
    perfil = {k: str(v) for k, v in padrao.items() if str(v or "").strip()}
    if not perfil.get("selador_host"):
        host = _host_do_selador_no_codigo()
        if host:
            perfil["selador_host"] = host
    if not perfil.get("serventia_brasao") and (SISTEMA / "static" / "brasao.jpg").is_file():
        perfil["serventia_brasao"] = "static/brasao.jpg"
    return perfil


def caminho_do_perfil(banco: Path, perfil: str | None) -> Path:
    return Path(perfil).expanduser().resolve() if perfil else banco.parent / NOME_DO_PERFIL


def ler_perfil(caminho: Path) -> dict[str, str]:
    if not caminho.is_file():
        raise MigracaoRecusou(
            f"Perfil local nao encontrado: {caminho}. Gere com --gerar-perfil "
            "(codigo antigo) ou copie de uma instalacao que o tenha.")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise MigracaoRecusou(f"Perfil local invalido (nao e objeto JSON): {caminho}")
    validas = set(campos())
    return {k: str(v).strip() for k, v in dados.items()
            if k in validas and str(v or "").strip()}


def gravar_perfil(caminho: Path, perfil: dict[str, str]) -> bool:
    """Grava o perfil se ainda nao existir. Nunca sobrescreve (idempotente)."""
    if caminho.exists():
        return False
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(perfil, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
    return True


# ------------------------------------------------------------ a migracao

def pendencias(con: sqlite3.Connection, perfil: dict[str, str]) -> dict[str, str]:
    """{chave: valor} que FALTA gravar: ausente ou em branco no banco."""
    atuais = {r[0]: r[1] for r in con.execute("SELECT key, value FROM settings")}
    faltam = {}
    for chave in campos():
        if str(atuais.get(chave) or "").strip():
            continue
        valor = perfil.get(chave, "")
        if valor:
            faltam[chave] = valor
    return faltam


def fazer_backup(banco: Path, agora: _dt.datetime) -> Path:
    pasta = banco.parent / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{PREFIXO_DO_BACKUP}{agora:%Y%m%d_%H%M%S}.sqlite3"
    origem = sqlite3.connect(str(banco), timeout=30)
    try:
        alvo = sqlite3.connect(str(destino))
        try:
            origem.backup(alvo)
        finally:
            alvo.close()
    finally:
        origem.close()
    # confere: o backup abre e tem a tabela settings
    con = sqlite3.connect(f"file:{destino}?mode=ro", uri=True)
    try:
        con.execute("SELECT COUNT(*) FROM settings").fetchone()
    finally:
        con.close()
    return destino


def migrar(banco: Path, perfil: dict[str, str], *, simular: bool = False,
           agora: _dt.datetime | None = None) -> dict:
    """Executa (ou simula). Devolve {gravadas, ja_preenchidas, sem_valor, backup}."""
    agora = agora or _dt.datetime.now()
    con = sqlite3.connect(str(banco), timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        faltam = pendencias(con, perfil)
        atuais = {r[0]: r[1] for r in con.execute("SELECT key, value FROM settings")}
    finally:
        con.close()
    ja = [k for k in campos() if str(atuais.get(k) or "").strip()]
    sem_valor = [k for k in campos() if k not in ja and k not in faltam]
    resultado = {"gravadas": {}, "ja_preenchidas": ja, "sem_valor": sem_valor,
                 "backup": None, "pendentes": dict(faltam)}
    if simular or not faltam:
        return resultado
    resultado["backup"] = fazer_backup(banco, agora)
    con = sqlite3.connect(str(banco), timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        with con:
            for chave, valor in faltam.items():
                # O WHERE repete a condicao dentro do proprio UPDATE: se alguem
                # salvar a tela entre a leitura e a escrita, o valor dele vence.
                cur = con.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value "
                    "WHERE trim(COALESCE(settings.value, ''))=''",
                    (chave, valor))
                if cur.rowcount:
                    resultado["gravadas"][chave] = valor
    finally:
        con.close()
    return resultado


# ------------------------------------------------------------ console

def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001, S110
            pass
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--banco")
    p.add_argument("--perfil", help=f"JSON local (padrao: <pasta do banco>/{NOME_DO_PERFIL})")
    p.add_argument("--gerar-perfil", action="store_true",
                   help="grava o perfil local a partir do serventia.PADRAO ANTIGO (se ainda nao existir)")
    p.add_argument("--simular", action="store_true")
    p.add_argument("--mostrar-valores", action="store_true")
    p.add_argument("--sou-a-producao", action="store_true")
    a = p.parse_args(argv)
    try:
        banco, origem = localizar_banco(a.banco)
        print(f"banco   {banco}   (via {origem})")
        conferir_alvo(banco, sou_a_producao=a.sou_a_producao)
        cperfil = caminho_do_perfil(banco, a.perfil)
        if a.gerar_perfil:
            if cperfil.exists():
                print(f"perfil  {cperfil}   (ja existe — mantido, nada regravado)")
            else:
                gravar_perfil(cperfil, perfil_do_codigo_antigo())
                print(f"perfil  {cperfil}   (GERADO a partir do codigo antigo)")
        perfil = ler_perfil(cperfil)
        print(f"perfil  {cperfil}   ({len(perfil)} chaves com valor)")
        r = migrar(banco, perfil, simular=a.simular)
    except MigracaoRecusou as erro:
        print(f"RECUSADO: {erro}")
        return 2
    mostrar = (lambda v: repr(v)) if a.mostrar_valores else (lambda v: f"<{len(v)} caracteres>")
    print(f"ja preenchidas no banco (mantidas): {', '.join(r['ja_preenchidas']) or '-'}")
    if r["sem_valor"]:
        print(f"em branco e SEM valor no perfil (ficam no placeholder): {', '.join(r['sem_valor'])}")
    if a.simular:
        print("SIMULACAO — nada gravado. Gravaria:")
        for k, v in r["pendentes"].items():
            print(f"  {k} = {mostrar(v)}")
        return 0
    if not r["gravadas"]:
        print("NADA A FAZER — settings ja tem tudo o que o perfil oferece (sem backup, sem escrita).")
        return 0
    print(f"backup  {r['backup']}")
    print(f"GRAVADAS {len(r['gravadas'])} chave(s):")
    for k, v in r["gravadas"].items():
        print(f"  {k} = {mostrar(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

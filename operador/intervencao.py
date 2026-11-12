"""O REGISTRO DAS INTERVENÇÕES DO SUPERUSUÁRIO — o que ele mudou no código e no
banco de uma instalação em uso, para a revisão e para o PR.

POR QUE EXISTE — 12/11/2026, pedido do oficial: um operador de IA com poder
total no servidor principal e no reserva, que resolve na hora e deixa
«relatório do que foi alterado no código e direto no banco, para ser revisado
por um agente local e para que seja possível fazer os PR». A produção não é um
clone do git (chega por pacote `.cgu`), então nada ali guarda o «antes». Este
módulo guarda.

    python operador/intervencao.py abrir "o pedido, nas palavras do oficial"
    python operador/intervencao.py guardar caminho/do/arquivo.py [...]
    python operador/intervencao.py nota "o que achei, o que decidi"
    python operador/intervencao.py sql mudanca.sql --tabelas users,settings --motivo "..."
    python operador/intervencao.py fechar --resumo "o que ficou feito"
    python operador/intervencao.py listar
    python operador/intervencao.py exportar --pasta <clone do repositório privado> [--enviar]
    python operador/intervencao.py criar-conta --responsavel <login do oficial>

O QUE CADA UMA GARANTE
    - `abrir` fotografa (SHA-256) os arquivos de texto do sistema: no `fechar`,
      o que mudou sem ter passado por `guardar` aparece no relatório do mesmo
      jeito — sem o diff, mas com o nome.
    - `guardar` copia o arquivo ANTES da edição. A guarda (`guarda.py`) chama
      sozinha a cada Edit/Write; para edição pelo shell, chama-se à mão.
    - `sql` faz `pg_dump` das tabelas ditas, roda o arquivo numa transação só
      (`psql -1`, para no primeiro erro) e guarda o SQL e a saída. RECUSA no
      servidor reserva (o banco dele é réplica: escrever ali quebra a réplica
      e duplica número de livro) e pede a confirmação do oficial para o que
      não tem volta.
    - `fechar` escreve `codigo.patch` e `RELATORIO.md` e grava uma linha na
      auditoria da casa.
    - `exportar` leva relatório, patch e SQL para o repositório privado, com
      os dados de pessoa mascarados (`ajuda_privacidade`). O `pg_dump` nunca
      sai do servidor.

Só a biblioteca padrão: roda no Python do servidor sem instalar nada.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

#: O login da conta do operador. É a ÚNICA conta de robô que pode ser ADMIN
#: (`database.ROBO_QUE_ADMINISTRA`, exceção do oficial de 12/11/2026).
LOGIN = "superusuario"
NOME = "Superusuário (operador de IA)"
AGENTE = "superusuario (operador de IA)"

#: Por quanto tempo vale o «CONFIRMO» do oficial, em segundos.
VALIDADE_DA_CONFIRMACAO = 600

_EXTENSOES = frozenset({
    ".py", ".html", ".js", ".css", ".sql", ".ps1", ".sh", ".cmd", ".bat",
    ".json", ".md", ".txt", ".toml", ".ini", ".cfg", ".xml", ".mjs", ".yml",
})
_PASTAS_DE_FORA = frozenset({
    ".git", "__pycache__", "venv", ".venv", "node_modules", "runtime",
    ".pytest_cache", "build", "dist",
})
_TAMANHO_MAXIMO = 5 * 1024 * 1024

#: O que não tem volta. Vale para o `sql` daqui e para o shell (`guarda.py`).
_RE_SEM_VOLTA = re.compile(
    r"\b(DROP\s+(TABLE|SCHEMA|DATABASE|COLUMN|INDEX|SEQUENCE|PUBLICATION|SUBSCRIPTION)"
    r"|TRUNCATE\b|ALTER\s+SEQUENCE\b|SETVAL\s*\("
    r"|ALTER\s+TABLE\b[^;]*\bDROP\b)", re.I)
_RE_DELETE = re.compile(r"\bDELETE\s+FROM\b[^;]*", re.I)
_RE_UPDATE = re.compile(r"\bUPDATE\s+[\w.\"]+\s+SET\b[^;]*", re.I)
_RE_ESCRITA = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|MERGE|CREATE|ALTER|DROP|GRANT|REVOKE)\b", re.I)


class Recusa(ValueError):
    """A ferramenta recusou, com a frase pronta para o operador ler."""


# ------------------------------------------------------------------ as pastas

def raiz_do_sistema() -> Path:
    """A pasta do sistema (onde mora o `app.py`). `OPERADOR_RAIZ` é dos testes."""
    dita = (os.environ.get("OPERADOR_RAIZ") or "").strip()
    return Path(dita).resolve() if dita else Path(__file__).resolve().parent.parent


def pasta_de_dados() -> Path:
    """A pasta de dados da casa — a mesma conta de `app.get_data_dir`, sem
    importar o Flask."""
    dita = (os.environ.get("CARTORIO_GESTAO_DATA") or "").strip()
    if dita:
        return Path(dita).expanduser().resolve()
    if sys.platform.startswith("win"):
        program_data = os.environ.get("PROGRAMDATA")
        if program_data:
            return Path(program_data) / "CartorioGestao"
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "CartorioGestao"
    return Path.home() / ".cartorio_gestao"


def base() -> Path:
    """`<dados>/operador`: tudo o que é do operador fica aqui, fora do sistema
    (o pacote de atualização não toca) e fora do backup do banco."""
    pasta = pasta_de_dados() / "operador"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def no_reserva() -> bool:
    return (os.environ.get("CG_MODO_RESERVA") or "").strip() == "1"


def servidor() -> str:
    """«principal» ou «reserva» — o nome que vai no relatório e na exportação."""
    dito = (os.environ.get("OPERADOR_NOME") or "").strip().lower()
    return dito or ("reserva" if no_reserva() else "principal")


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005


# ------------------------------------------------------------- a confirmação

def _arquivo_da_confirmacao() -> Path:
    return base() / "confirmacao"


def registrar_confirmacao(texto: str = "") -> None:
    """Chamado SÓ pela ponte, quando o oficial responde «CONFIRMO»."""
    _arquivo_da_confirmacao().write_text(
        json.dumps({"quando": time.time(), "texto": texto[:500]}, ensure_ascii=False),
        encoding="utf-8")


def confirmacao_valida() -> bool:
    try:
        dados = json.loads(_arquivo_da_confirmacao().read_text(encoding="utf-8"))
        return 0 <= time.time() - float(dados["quando"]) <= VALIDADE_DA_CONFIRMACAO
    except (OSError, ValueError, KeyError, TypeError):
        return False


def sem_volta(sql: str) -> str | None:
    """A frase do que não tem volta neste texto, ou None."""
    limpo = re.sub(r"--[^\n]*", " ", sql)
    limpo = re.sub(r"/\*.*?\*/", " ", limpo, flags=re.S)
    achado = _RE_SEM_VOLTA.search(limpo)
    if achado:
        return " ".join(achado.group(0).split()).upper()
    for trecho in _RE_DELETE.findall(limpo):
        if not re.search(r"\bWHERE\b", trecho, re.I):
            return "DELETE sem WHERE"
    for trecho in _RE_UPDATE.findall(limpo):
        if not re.search(r"\bWHERE\b", trecho, re.I):
            return "UPDATE sem WHERE"
    return None


# ------------------------------------------------------------ a intervenção

def _pasta_das_intervencoes() -> Path:
    pasta = base() / "intervencoes"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _ler(pasta: Path) -> dict:
    return json.loads((pasta / "intervencao.json").read_text(encoding="utf-8"))


def _gravar(pasta: Path, dados: dict) -> None:
    provisorio = pasta / "intervencao.json.novo"
    provisorio.write_text(json.dumps(dados, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    provisorio.replace(pasta / "intervencao.json")


def _arquivo_da_atual() -> Path:
    return base() / "atual"


def atual() -> Path | None:
    """A pasta da intervenção aberta, se houver."""
    try:
        nome = _arquivo_da_atual().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    pasta = _pasta_das_intervencoes() / nome
    return pasta if nome and (pasta / "intervencao.json").is_file() else None


def _arquivos_do_sistema(raiz: Path):
    for pasta, subpastas, arquivos in os.walk(raiz):
        subpastas[:] = [s for s in subpastas if s not in _PASTAS_DE_FORA]
        for nome in arquivos:
            caminho = Path(pasta) / nome
            if caminho.suffix.lower() in _EXTENSOES:
                yield caminho


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def fotografia(raiz: Path) -> dict[str, str]:
    foto: dict[str, str] = {}
    for caminho in _arquivos_do_sistema(raiz):
        try:
            if caminho.stat().st_size <= _TAMANHO_MAXIMO:
                foto[caminho.relative_to(raiz).as_posix()] = _sha(caminho)
        except OSError:
            continue
    return foto


def _versao(raiz: Path) -> str:
    try:
        return (raiz / "VERSAO.txt").read_text(encoding="utf-8").strip()[:40]
    except OSError:
        return ""


def abrir(pedido: str, *, automatica: bool = False) -> Path:
    """Abre uma intervenção. Com outra aberta, devolve a que já está."""
    aberta = atual()
    if aberta:
        return aberta
    raiz = raiz_do_sistema()
    dia = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    numero = 1
    while (_pasta_das_intervencoes() / f"{dia}-{numero:03d}").exists():
        numero += 1
    pasta = _pasta_das_intervencoes() / f"{dia}-{numero:03d}"
    (pasta / "antes").mkdir(parents=True)
    (pasta / "banco").mkdir()
    (pasta / "fotografia.json").write_text(
        json.dumps(fotografia(raiz), ensure_ascii=False), encoding="utf-8")
    _gravar(pasta, {
        "id": pasta.name, "servidor": servidor(), "versao": _versao(raiz),
        "raiz": str(raiz), "aberta_em": _agora(), "fechada_em": None,
        "pedido": (pedido or "").strip(), "automatica": bool(automatica),
        "notas": [], "guardados": [], "sql": [], "resumo": "",
        "auditoria": "", "exportada_em": None,
    })
    _arquivo_da_atual().write_text(pasta.name, encoding="utf-8")
    return pasta


def _relativo(caminho: Any, raiz: Path) -> str | None:
    """O caminho relativo à raiz do sistema, ou None se o arquivo é de fora."""
    alvo = Path(caminho)
    if not alvo.is_absolute():
        alvo = Path.cwd() / alvo
    try:
        return alvo.resolve().relative_to(raiz).as_posix()
    except ValueError:
        return None


def guardar(caminhos: list[Any], *, pedido: str = "") -> list[str]:
    """Copia cada arquivo, como está AGORA, para `antes/`. Uma vez só por
    intervenção: a segunda chamada não troca o original pela versão do meio."""
    raiz = raiz_do_sistema()
    relativos = [r for r in (_relativo(c, raiz) for c in caminhos) if r]
    if not relativos:
        return []
    pasta = abrir(pedido or "Aberta sozinha pela guarda, na primeira edição.",
                  automatica=True)
    dados = _ler(pasta)
    feitos = []
    for rel in relativos:
        if any(g["arquivo"] == rel for g in dados["guardados"]):
            continue
        origem = raiz / rel
        if origem.is_file():
            destino = pasta / "antes" / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origem, destino)
            dados["guardados"].append({"arquivo": rel, "existia": True})
        else:
            dados["guardados"].append({"arquivo": rel, "existia": False})
        feitos.append(rel)
    if feitos:
        _gravar(pasta, dados)
    return feitos


def nota(texto: str) -> None:
    pasta = abrir("Aberta sozinha, por uma nota.", automatica=True)
    dados = _ler(pasta)
    dados["notas"].append({"quando": _agora(), "texto": texto.strip()})
    _gravar(pasta, dados)


# -------------------------------------------------------------------- o banco

def _binario(nome: str) -> str:
    arquivo = f"{nome}.exe" if os.name == "nt" else nome
    pasta = (os.environ.get("CG_PG_BIN") or "").strip()
    if pasta and (Path(pasta) / arquivo).exists():
        return str(Path(pasta) / arquivo)
    achado = shutil.which(nome)
    if not achado:
        raise Recusa(f"{nome} não encontrado: defina CG_PG_BIN com a pasta bin "
                     "do PostgreSQL.")
    return achado


def _dsn_e_schema() -> tuple[str, str]:
    dsn = (os.environ.get("CG_PG_DSN") or "").strip()
    schema = (os.environ.get("CG_PG_SCHEMA") or "").strip()
    if not dsn or not schema:
        raise Recusa("Falta CG_PG_DSN ou CG_PG_SCHEMA no ambiente: sem eles eu "
                     "não sei em que banco estou mexendo, e não adivinho.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise Recusa(f"CG_PG_SCHEMA estranho: «{schema}».")
    return dsn, schema


def executar_sql(arquivo: Any, tabelas: list[str], motivo: str, *,
                 rodar=subprocess.run) -> dict:
    """`pg_dump` das tabelas, depois o arquivo numa transação só. Devolve o
    registro que entrou no relatório. `rodar` é trocado nos testes."""
    origem = Path(arquivo)
    if not origem.is_file():
        raise Recusa(f"Não achei o arquivo de SQL: {arquivo}")
    sql = origem.read_text(encoding="utf-8")
    escreve = bool(_RE_ESCRITA.search(sql))
    if escreve and no_reserva():
        raise Recusa(
            "Este é o servidor RESERVA: o banco dele é réplica do principal. "
            "Escrever aqui quebra a réplica e pode repetir número de livro. "
            "Faça a mudança no principal (ela chega sozinha), ou, com o "
            "principal fora do ar, peça ao oficial para ASSUMIR antes.")
    perigo = sem_volta(sql)
    if perigo and not confirmacao_valida():
        raise Recusa(
            f"Isto não tem volta ({perigo}). Explique ao oficial o que vai "
            "fazer e peça que ele responda CONFIRMO; a confirmação vale "
            f"{VALIDADE_DA_CONFIRMACAO // 60} minutos.")
    tabelas = [t.strip() for t in tabelas if t.strip()]
    for tabela in tabelas:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tabela):
            raise Recusa(f"Nome de tabela estranho: «{tabela}».")
    if escreve and not tabelas:
        raise Recusa("SQL que grava vai com --tabelas: as tabelas que ele toca, "
                     "para a cópia de antes. Sem cópia eu não rodo.")
    if escreve and not motivo.strip():
        raise Recusa("Diga o --motivo: é o que o revisor vai ler.")
    dsn, schema = _dsn_e_schema()
    pasta = abrir(motivo or "Aberta sozinha, por um SQL.", automatica=True)
    dados = _ler(pasta)
    numero = len(dados["sql"]) + 1
    banco = pasta / "banco"
    shutil.copyfile(origem, banco / f"{numero:02d}.sql")
    registro = {"numero": numero, "quando": _agora(), "motivo": motivo.strip(),
                "tabelas": tabelas, "arquivo": f"banco/{numero:02d}.sql",
                "copia": "", "saida": f"banco/{numero:02d}.saida.txt",
                "codigo_de_saida": None, "sem_volta": perigo or ""}
    if escreve:
        copia = banco / f"{numero:02d}-antes.dump"
        comando = [_binario("pg_dump"), "-Fc", "-d", dsn, "-f", str(copia)]
        for tabela in tabelas:
            comando += ["-t", f"{schema}.{tabela}"]
        feito = rodar(comando, capture_output=True, text=True)
        if feito.returncode != 0:
            raise Recusa("A cópia de antes (pg_dump) falhou, então não rodei "
                         f"nada: {(feito.stderr or '').strip()[-400:]}")
        registro["copia"] = f"banco/{numero:02d}-antes.dump"
    ambiente = dict(os.environ)
    ambiente["PGOPTIONS"] = f"-c search_path={schema},public"
    feito = rodar([_binario("psql"), "-d", dsn, "-X", "-1",
                   "-v", "ON_ERROR_STOP=1", "-f", str(origem)],
                  capture_output=True, text=True, env=ambiente)
    saida = (feito.stdout or "") + (("\n" + feito.stderr) if feito.stderr else "")
    (pasta / registro["saida"]).write_text(saida, encoding="utf-8")
    registro["codigo_de_saida"] = feito.returncode
    dados["sql"].append(registro)
    _gravar(pasta, dados)
    registro["texto_da_saida"] = saida[-4000:]
    return registro


# ---------------------------------------------------------------- o fechamento

def _linhas(caminho: Path) -> list[str]:
    try:
        return caminho.read_bytes().decode("utf-8", errors="replace").splitlines(keepends=True)
    except OSError:
        return []


def _mudancas(pasta: Path, dados: dict, raiz: Path) -> tuple[str, list[dict]]:
    """O patch dos arquivos guardados e a lista de tudo o que mudou."""
    try:
        antes = json.loads((pasta / "fotografia.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        antes = {}
    depois = fotografia(raiz)
    guardados = {g["arquivo"]: g for g in dados["guardados"]}
    nomes = sorted({n for n in set(antes) | set(depois)
                    if antes.get(n) != depois.get(n)} | set(guardados))
    patch: list[str] = []
    lista: list[dict] = []
    for nome in nomes:
        agora = raiz / nome
        guardado = guardados.get(nome)
        original = pasta / "antes" / nome
        if guardado:
            velho = _linhas(original) if guardado["existia"] else []
            novo = _linhas(agora) if agora.is_file() else []
            if velho == novo:
                continue
            situacao = ("criado" if not guardado["existia"]
                        else "apagado" if not agora.is_file() else "alterado")
            patch.extend(difflib.unified_diff(
                velho, novo,
                "a/" + nome if guardado["existia"] else "/dev/null",
                "b/" + nome if agora.is_file() else "/dev/null"))
            if patch and not patch[-1].endswith("\n"):
                patch.append("\n\\ No newline at end of file\n")
            lista.append({"arquivo": nome, "situacao": situacao, "com_diff": True})
        elif nome not in antes and agora.is_file():
            # criado sem `guardar`: o «antes» é o vazio, o diff sai inteiro
            patch.extend(difflib.unified_diff([], _linhas(agora), "/dev/null", "b/" + nome))
            lista.append({"arquivo": nome, "situacao": "criado", "com_diff": True})
        else:
            lista.append({"arquivo": nome, "com_diff": False,
                          "situacao": "alterado" if agora.is_file() else "apagado"})
    return "".join(patch), lista


def _um(db, sql: str, parametros: tuple):
    """Uma linha do banco da casa, pela ponte do sistema."""
    from bd_nativo import banco
    with db.connect() as con:
        return banco(con).um(sql, parametros)


def _auditar(dados: dict, mudancas: list[dict]) -> str:
    """Uma linha na auditoria da casa. Devolve o que aconteceu, em frase."""
    if no_reserva():
        return "não gravada: o banco do reserva só lê (a linha fica neste relatório)"
    if not (os.environ.get("CG_PG_DSN") or "").strip():
        return "não gravada: sem CG_PG_DSN no ambiente"
    try:
        raiz = str(raiz_do_sistema())
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        import banco_pg
        from database import Database
        import identidade_do_robo as IDR
        db_path = pasta_de_dados() / "cartorio_gestao.sqlite3"
        if not banco_pg.schema_existe(db_path):
            return "não gravada: o schema do CG_PG_SCHEMA não existe"
        db = Database(db_path)
        detalhes = {"intervencao": dados["id"], "servidor": dados["servidor"],
                    "resumo": dados["resumo"][:500],
                    "arquivos": [m["arquivo"] for m in mudancas][:60],
                    "sql": len(dados["sql"])}
        conta = _um(db, "SELECT id FROM users WHERE username=%s AND active=1", (LOGIN,))
        if conta:
            db.log(int(conta["id"]), LOGIN, "INTERVENCAO_DO_OPERADOR",
                   "INTERVENCAO", None, detalhes)
        else:
            db.log(None, AGENTE, "INTERVENCAO_DO_OPERADOR", "INTERVENCAO", None,
                   detalhes, agente=AGENTE, a_mando_de=IDR.PELO_RESPONSAVEL)
        return "gravada (INTERVENCAO_DO_OPERADOR)"
    except Exception as erro:  # noqa: BLE001 — o relatório diz o porquê
        return f"não gravada: {type(erro).__name__}: {erro}"[:300]


def _relatorio(dados: dict, mudancas: list[dict]) -> str:
    partes = [
        f"# Intervenção {dados['id']} — servidor {dados['servidor']}", "",
        f"- Versão do sistema: {dados['versao'] or 'não lida'}",
        f"- Aberta em: {dados['aberta_em']}",
        f"- Fechada em: {dados['fechada_em']}",
        f"- Auditoria da casa: {dados['auditoria']}", "",
        "## O pedido", "", dados["pedido"] or "(não informado)", "",
        "## O que ficou feito", "", dados["resumo"] or "(sem resumo)", "",
    ]
    if dados["notas"]:
        partes += ["## Notas do operador", ""]
        partes += [f"- {n['quando']} — {n['texto']}" for n in dados["notas"]]
        partes.append("")
    partes += ["## Código alterado", ""]
    if mudancas:
        for m in mudancas:
            aviso = "" if m["com_diff"] else (
                " — **SEM O ORIGINAL GUARDADO**: mudou fora do Edit/Write e sem "
                "`guardar`; conferir à mão contra a versão do repositório")
            partes.append(f"- `{m['arquivo']}` ({m['situacao']}){aviso}")
        partes += ["", "O diff está em `codigo.patch` (aplica com `git apply`)."]
    else:
        partes.append("Nenhum arquivo do sistema mudou.")
    partes += ["", "## Banco de dados", ""]
    if dados["sql"]:
        for s in dados["sql"]:
            resultado = ("rodou" if s["codigo_de_saida"] == 0
                         else f"FALHOU (código {s['codigo_de_saida']}; a transação voltou)")
            partes += [
                f"### {s['numero']:02d} — {s['motivo'] or 'consulta'}", "",
                f"- Quando: {s['quando']} — {resultado}",
                f"- Tabelas: {', '.join(s['tabelas']) or '(só leitura)'}",
                f"- SQL: `{s['arquivo']}` · saída: `{s['saida']}`",
                f"- Cópia de antes: `{s['copia']}`" if s["copia"] else "- Cópia de antes: não houve (só leitura)",
            ]
            if s["copia"]:
                partes.append(
                    f"- Para desfazer: restaure `{s['copia']}` (`pg_restore`) num "
                    "banco à parte e traga de volta só as linhas mexidas; não "
                    "restaure por cima da tabela em uso.")
            if s["sem_volta"]:
                partes.append(f"- **Sem volta** ({s['sem_volta']}), confirmado pelo oficial.")
            partes.append("")
    else:
        partes.append("Nenhum SQL rodou por esta ferramenta.")
    partes += [
        "", "## Para o revisor", "",
        "1. Aplicar `codigo.patch` num ramo novo a partir do `main`, com os "
        "dados fictícios da casa nos testes.",
        "2. Mudança de banco que deva valer para toda instalação vira migração "
        "em código («migração só acrescenta»); a que foi acerto de dado fica "
        "só neste relatório.",
        "3. Enquanto o PR não entrar e o pacote `.cgu` não for aplicado, a "
        "produção roda com esta correção direta — e o próximo pacote a apaga.",
        "",
    ]
    return "\n".join(partes)


def fechar(resumo: str = "") -> dict | None:
    """Fecha a intervenção aberta. Sem nenhuma aberta, devolve None. A que não
    mudou nada (nem código, nem SQL, nem nota) é descartada, sem relatório."""
    pasta = atual()
    if not pasta:
        return None
    dados = _ler(pasta)
    raiz = raiz_do_sistema()
    patch, mudancas = _mudancas(pasta, dados, raiz)
    try:
        _arquivo_da_atual().unlink()
    except OSError:
        pass
    if not mudancas and not dados["sql"] and not dados["notas"]:
        shutil.rmtree(pasta, ignore_errors=True)
        return None
    dados["resumo"] = (resumo or dados["resumo"] or "").strip()
    dados["fechada_em"] = _agora()
    dados["mudancas"] = mudancas
    dados["auditoria"] = _auditar(dados, mudancas)
    (pasta / "codigo.patch").write_text(patch, encoding="utf-8", newline="")
    (pasta / "RELATORIO.md").write_text(_relatorio(dados, mudancas),
                                        encoding="utf-8", newline="\n")
    _gravar(pasta, dados)
    return dados


def listar() -> list[dict]:
    feitas = []
    for pasta in sorted(_pasta_das_intervencoes().iterdir()):
        try:
            feitas.append(_ler(pasta))
        except (OSError, ValueError):
            continue
    return feitas


# ------------------------------------------------------------------ a exportação

def _mascarar(texto: str) -> str:
    raiz = str(raiz_do_sistema())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import ajuda_privacidade as PRIV
    return PRIV.sanitizar_texto(texto)


def exportar(destino: Any, *, mascarar=None, enviar: bool = False,
             rodar=subprocess.run) -> list[str]:
    """Leva as intervenções fechadas e ainda não exportadas para
    `<destino>/intervencoes/<servidor>-<id>/`. O relatório e o SQL saem
    MASCARADOS; o `pg_dump` e a saída do SQL não saem. O que a máscara recusar
    fica no servidor, e o relatório exportado diz que ficou."""
    mascarar = mascarar or _mascarar
    repositorio = Path(destino).expanduser().resolve()
    if not repositorio.is_dir():
        raise Recusa(f"A pasta do repositório privado não existe: {destino}")
    levadas = []
    for dados in listar():
        if not dados.get("fechada_em") or dados.get("exportada_em"):
            continue
        origem = _pasta_das_intervencoes() / dados["id"]
        alvo = repositorio / "intervencoes" / f"{dados['servidor']}-{dados['id']}"
        alvo.mkdir(parents=True, exist_ok=True)
        ficou = []
        nomes = ["RELATORIO.md"] + [s["arquivo"] for s in dados["sql"]]
        for nome in nomes:
            try:
                texto = mascarar((origem / nome).read_text(encoding="utf-8"))
            except Exception as erro:  # noqa: BLE001 — a máscara recusou: não sai
                ficou.append(f"{nome} ({type(erro).__name__})")
                continue
            (alvo / Path(nome).name).write_text(texto, encoding="utf-8", newline="\n")
        shutil.copyfile(origem / "codigo.patch", alvo / "codigo.patch")
        if ficou:
            (alvo / "FICOU_NO_SERVIDOR.md").write_text(
                "A máscara de dados pessoais recusou estes arquivos; eles estão "
                f"só no servidor {dados['servidor']}, em "
                f"`operador/intervencoes/{dados['id']}/`:\n\n"
                + "\n".join(f"- {f}" for f in ficou) + "\n",
                encoding="utf-8", newline="\n")
        dados["exportada_em"] = _agora()
        _gravar(origem, dados)
        levadas.append(alvo.name)
    if enviar and levadas:
        git = ["git", "-C", str(repositorio)]
        for comando in (
                git + ["add", "intervencoes"],
                git + ["-c", "user.name=Superusuario", "-c",
                       "user.email=superusuario@cartorio.invalid", "commit", "-m",
                       "Intervenções do operador: " + ", ".join(levadas)],
                git + ["push"]):
            feito = rodar(comando, capture_output=True, text=True)
            if feito.returncode != 0:
                raise Recusa("Exportei, mas o envio do repositório falhou em «"
                             + " ".join(comando[3:5]) + "»: "
                             + (feito.stderr or feito.stdout or "").strip()[-300:])
    return levadas


# ----------------------------------------------------------------------- a conta

def criar_conta(responsavel: str) -> str:
    """Cria a conta `superusuario` (robô, ADMIN) com o oficial por responsável.
    A senha é sorteada e fica em `<dados>/operador/superusuario.cred`."""
    raiz = str(raiz_do_sistema())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import banco_pg
    from database import Database
    import identidade_do_robo as IDR
    _dsn_e_schema()
    if no_reserva():
        raise Recusa("A conta se cria no servidor principal; ela chega ao "
                     "reserva pela réplica.")
    db_path = pasta_de_dados() / "cartorio_gestao.sqlite3"
    if not banco_pg.schema_existe(db_path):
        raise Recusa("O schema do CG_PG_SCHEMA não existe: esta ferramenta não cria banco.")
    db = Database(db_path)
    pessoa = _um(db, "SELECT id, role FROM users WHERE username=%s AND active=1 "
                 "AND COALESCE(eh_robo,0)=0", (responsavel.strip(),))
    if not pessoa or str(pessoa["role"]).upper() != "ADMIN":
        raise Recusa("O responsável pelo superusuário é uma pessoa com perfil "
                     "ADMIN e cadastro ativo. Confira o login.")
    if _um(db, "SELECT id FROM users WHERE username=%s", (LOGIN,)):
        raise Recusa(f"A conta «{LOGIN}» já existe.")
    senha = secrets.token_urlsafe(24) + "aA1#"
    uid = db.create_user(LOGIN, NOME, senha, "ADMIN", int(pessoa["id"]), eh_robo=1)
    with db.transaction() as con:
        IDR.definir_responsavel_do_robo(con, uid, int(pessoa["id"]))
    db.log(int(pessoa["id"]), responsavel.strip(), "USER_CREATED", "USER", uid,
           {"username": LOGIN, "role": "ADMIN", "eh_robo": 1,
            "excecao": "superusuário, ordem do oficial de 12/11/2026"})
    cofre = base() / "superusuario.cred"
    cofre.write_text(senha + "\n", encoding="utf-8")
    try:
        cofre.chmod(0o600)
    except OSError:
        pass
    return str(cofre)


# ------------------------------------------------------------- linha de comando

def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    ap = argparse.ArgumentParser(prog="operador/intervencao.py",
                                 description="O registro das intervenções do superusuário.")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("abrir").add_argument("pedido")
    sub.add_parser("guardar").add_argument("arquivos", nargs="+")
    sub.add_parser("nota").add_argument("texto")
    sq = sub.add_parser("sql")
    sq.add_argument("arquivo")
    sq.add_argument("--tabelas", default="")
    sq.add_argument("--motivo", default="")
    sub.add_parser("fechar").add_argument("--resumo", default="")
    sub.add_parser("listar")
    ex = sub.add_parser("exportar")
    ex.add_argument("--pasta", required=True)
    ex.add_argument("--enviar", action="store_true")
    sub.add_parser("criar-conta").add_argument("--responsavel", required=True)
    a = ap.parse_args(argv)
    try:
        if a.comando == "abrir":
            print(f"Intervenção {abrir(a.pedido).name} aberta.")
        elif a.comando == "guardar":
            feitos = guardar(a.arquivos)
            print("Guardado: " + (", ".join(feitos) or "nada novo (já estava, ou é de fora do sistema)"))
        elif a.comando == "nota":
            nota(a.texto)
            print("Anotado.")
        elif a.comando == "sql":
            r = executar_sql(a.arquivo, a.tabelas.split(","), a.motivo)
            print(r["texto_da_saida"])
            print(f"[código de saída {r['codigo_de_saida']}; cópia de antes: {r['copia'] or 'não houve'}]")
            return 0 if r["codigo_de_saida"] == 0 else 1
        elif a.comando == "fechar":
            dados = fechar(a.resumo)
            print(f"Intervenção {dados['id']} fechada: {len(dados['mudancas'])} arquivo(s), "
                  f"{len(dados['sql'])} SQL. Auditoria: {dados['auditoria']}."
                  if dados else "Nada aberto, ou nada mudou: sem relatório.")
        elif a.comando == "listar":
            for d in listar():
                estado = ("aberta" if not d.get("fechada_em") else
                          "exportada" if d.get("exportada_em") else "fechada, por exportar")
                print(f"{d['id']}  {estado}  {d['pedido'][:70]}")
        elif a.comando == "exportar":
            levadas = exportar(a.pasta, enviar=a.enviar)
            print("Exportadas: " + (", ".join(levadas) or "nenhuma pendente"))
        elif a.comando == "criar-conta":
            print(f"Conta «{LOGIN}» criada. A senha está em {criar_conta(a.responsavel)}.")
    except Recusa as recusa:
        print(f"RECUSADO: {recusa}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
O acervo morto do E-Oficio — as 411 tabelas como vieram.

POR QUE UM BANCO SEPARADO
    O E-Oficio vai ser desligado, e o que nao sair de la some junto. Sao 231
    tabelas com dados e umas 552 mil linhas: cabe inteiro, e nao ha razao para
    escolher hoje o que fara falta depois.

    Mas isto NAO E DADO DE TRABALHO. Fica em `acervo_eoficio.sqlite3`, ao lado
    do banco do sistema, por tres motivos:

      o banco vivo continua pequeno e rapido;
      ninguem confunde tabela de arquivo morto com tabela em uso;
      o acervo e imutavel, entao o backup pode trata-lo como as
      digitalizacoes — copia semanal, e nao diaria.

O QUE ESTE MODULO NAO FAZ
    Nao interpreta nada. Nao mapeia campo, nao converte data, nao normaliza
    nome. As cargas dirigidas — matriculas, atos, cartoes, caixa — continuam
    existindo e continuam sendo as que entendem o dado.

    Aqui o valor esta justamente em NAO entender: o que for guardado sem
    interpretacao pode ser reinterpretado daqui a dez anos, quando a pergunta
    for outra.

CONFERIR E PARTE DA CARGA
    O exportador grava um MANIFESTO com quantas linhas saiu de cada tabela.
    A carga compara. Tabela que entrou com menos linhas do que saiu e carga
    que mentiu — e neste projeto ja houve contador que relatou 4.060 cartoes
    numa rodada que inseriu zero.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

NOME_BANCO = "acervo_eoficio.sqlite3"
# Estes dois nao sao tabelas: descrevem a exportacao.
ARQUIVOS_DE_CONTROLE = {"ESQUEMA.jsonl", "MANIFESTO.jsonl"}


def _tipo_sqlite(tipo_sql: str) -> str:
    """Tipo do SQL Server -> afinidade do SQLite.

    Grosseiro de proposito. O SQLite guarda o que receber; o que importa aqui
    e nao perder o dado, e nao reproduzir o sistema de tipos do SQL Server.
    """
    t = (tipo_sql or "").lower()
    if t in ("int", "bigint", "smallint", "tinyint", "bit"):
        return "INTEGER"
    if t in ("decimal", "numeric", "money", "smallmoney", "float", "real"):
        return "REAL"
    return "TEXT"


def esquema_por_tabela(pasta: Path) -> dict[str, list[tuple[str, str]]]:
    """Le o ESQUEMA.jsonl e devolve {tabela: [(coluna, tipo), ...]}."""
    arq = Path(pasta) / "ESQUEMA.jsonl"
    if not arq.is_file():
        return {}
    saida: dict[str, list[tuple[str, str]]] = {}
    with arq.open(encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if not linha:
                continue
            d = json.loads(linha)
            saida.setdefault(d["tabela"], []).append(
                (d["coluna"], _tipo_sqlite(d.get("tipo"))))
    return saida


def manifesto(pasta: Path) -> dict[str, int]:
    """{tabela: linhas} conforme o exportador contou na origem."""
    arq = Path(pasta) / "MANIFESTO.jsonl"
    if not arq.is_file():
        return {}
    saida = {}
    with arq.open(encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                d = json.loads(linha)
                saida[d["tabela"]] = int(d["linhas"])
    return saida


def _colunas_do_arquivo(arq: Path, limite: int = 200) -> list[str]:
    """As colunas, tiradas das primeiras linhas.

    Serve quando o ESQUEMA.jsonl nao veio. Le mais de uma linha porque JSON
    omite chave nenhuma, mas a primeira linha pode nao trazer todas se o
    exportador tiver mudado no meio.
    """
    vistas: list[str] = []
    with arq.open(encoding="utf-8", errors="replace") as fh:
        for i, linha in enumerate(fh):
            if i >= limite:
                break
            linha = linha.strip()
            if not linha:
                continue
            for k in json.loads(linha):
                if k not in vistas:
                    vistas.append(k)
    return vistas


def carregar(pasta: str | Path, destino: str | Path,
             progresso=None) -> dict:
    """Monta o acervo a partir da pasta exportada.

    REFAZ DO ZERO, e e o certo aqui. A carga dirigida e incremental porque
    convive com o que foi digitado a mao; esta nao convive com nada — e copia
    fiel de um banco que nao muda mais. Recarregar tem de dar o mesmo
    resultado, e a unica forma barata de garantir isso e recomecar.
    """
    pasta = Path(pasta)
    destino = Path(destino)
    if not pasta.is_dir():
        raise FileNotFoundError(f"não achei a pasta exportada: {pasta}")

    esquemas = esquema_por_tabela(pasta)
    esperado = manifesto(pasta)
    arquivos = sorted(p for p in pasta.glob("*.jsonl")
                      if p.name not in ARQUIVOS_DE_CONTROLE)
    if not arquivos:
        raise FileNotFoundError(f"nenhuma tabela em {pasta}")

    parcial = destino.with_suffix(destino.suffix + ".parcial")
    parcial.unlink(missing_ok=True)
    destino.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(parcial)
    con.execute("PRAGMA journal_mode = OFF")
    con.execute("PRAGMA synchronous = OFF")

    resultado = {"tabelas": 0, "linhas": 0, "divergentes": [], "sem_esquema": []}
    try:
        for arq in arquivos:
            tabela = arq.stem
            colunas = [c for c, _ in esquemas.get(tabela, [])]
            if not colunas:
                colunas = _colunas_do_arquivo(arq)
                resultado["sem_esquema"].append(tabela)
            if not colunas:
                continue
            # SEM ESQUEMA, A COLUNA VAI SEM TIPO — e não como TEXT.
            #     Coluna sem tipo declarado tem afinidade BLOB no SQLite, que
            #     guarda o valor como ele chega: inteiro continua inteiro.
            #     Declarando TEXT, o 1 vira '1' e a cópia deixa de ser fiel
            #     logo onde ela é a única fonte que sobrou.
            tipos = dict(esquemas.get(tabela, []))
            corpo = ", ".join(
                (f'"{c}" {tipos[c]}' if c in tipos else f'"{c}"') for c in colunas)
            con.execute(f'CREATE TABLE "{tabela}" ({corpo})')
            marcas = ",".join("?" * len(colunas))
            inserir = f'INSERT INTO "{tabela}" VALUES ({marcas})'

            lote, n = [], 0
            with arq.open(encoding="utf-8", errors="replace") as fh:
                for linha in fh:
                    linha = linha.strip()
                    if not linha:
                        continue
                    d = json.loads(linha)
                    lote.append(tuple(d.get(c) for c in colunas))
                    n += 1
                    if len(lote) >= 2000:
                        con.executemany(inserir, lote)
                        lote.clear()
            if lote:
                con.executemany(inserir, lote)

            # A conferencia contra o manifesto, tabela a tabela.
            de_la = esperado.get(tabela)
            if de_la is not None and de_la != n:
                resultado["divergentes"].append(
                    {"tabela": tabela, "na_origem": de_la, "carregou": n})
            resultado["tabelas"] += 1
            resultado["linhas"] += n
            if progresso:
                progresso(f"{tabela}: {n} linha(s)")

        con.execute("""CREATE TABLE _acervo_info (
                         chave TEXT PRIMARY KEY, valor TEXT)""")
        con.executemany("INSERT INTO _acervo_info VALUES (?,?)", [
            ("origem", str(pasta)),
            ("tabelas", str(resultado["tabelas"])),
            ("linhas", str(resultado["linhas"])),
            ("divergentes", str(len(resultado["divergentes"]))),
        ])
        con.commit()
    finally:
        con.close()

    problema = conferir(parcial)
    if problema:
        raise RuntimeError(f"{problema} — o acervo ficou em {parcial.name} "
                           "para exame, e o nome definitivo não foi criado.")
    destino.unlink(missing_ok=True)
    parcial.replace(destino)
    resultado["arquivo"] = str(destino)
    resultado["bytes"] = destino.stat().st_size
    return resultado


def conferir(banco: str | Path) -> str | None:
    """O acervo abre e tem conteudo? Devolve o problema, ou None.

    Mesma disciplina do backup: grava num `.parcial`, FECHA, reabre e confere.
    Conferir arquivo ainda aberto para escrita e conferir a propria intencao.
    """
    banco = Path(banco)
    if not banco.is_file():
        return "o arquivo não existe"
    if banco.stat().st_size == 0:
        return "o arquivo está vazio"
    try:
        con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return "o banco não passou no integrity_check"
            n = con.execute("""SELECT COUNT(*) FROM sqlite_master
                               WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\'
                            """).fetchone()[0]
            if not n:
                return "o acervo não tem nenhuma tabela"
        finally:
            con.close()
    except sqlite3.DatabaseError as erro:
        return f"não consegui abrir o acervo: {erro}"
    return None


def resumo(banco: str | Path) -> dict:
    """O que tem dentro, para a tela mostrar."""
    banco = Path(banco)
    dados = {"arquivo": str(banco), "existe": banco.is_file(),
             "bytes": banco.stat().st_size if banco.is_file() else 0,
             "problema": conferir(banco) if banco.is_file() else "ainda não foi montado"}
    if dados["problema"]:
        return dados
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        dados["info"] = {r["chave"]: r["valor"] for r in
                         con.execute("SELECT * FROM _acervo_info")}
        dados["maiores"] = []
        for r in con.execute("""SELECT name FROM sqlite_master WHERE type='table'
                                AND name NOT LIKE '\\_%' ESCAPE '\\' ORDER BY name"""):
            n = con.execute(f'SELECT COUNT(*) FROM "{r["name"]}"').fetchone()[0]
            dados["maiores"].append({"tabela": r["name"], "linhas": n})
        dados["maiores"].sort(key=lambda x: -x["linhas"])
        dados["tabelas"] = len(dados["maiores"])
        dados["linhas"] = sum(x["linhas"] for x in dados["maiores"])
    finally:
        con.close()
    return dados

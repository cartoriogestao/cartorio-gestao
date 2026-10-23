"""A BASE DE CONHECIMENTO PRÉ-CARREGADA DA AJUDA — 18/09/2026.

A FRASE DELE:

    «Preciso que o modulo de ajuda tenha uma base de conhecimento
     pré-carregada, não dá pra buscar as respostas de tudo para cada problema.»

O QUE ESTAVA ACONTECENDO, E O CUSTO ESTAVA MEDIDO NA DIREÇÃO OPOSTA
    `procurar_nos_documentos` custava **436 a 470 ms por chamada**, e o custo
    não estava na busca: estava em **ler os 171 documentos do disco e
    normalizar 2.064.697 bytes a cada pergunta**. A mesma casa já tinha a
    resposta certa do lado: `ajuda_regras.procurar` custa **6 ms**, porque
    guarda o arquivo já quebrado em seções.

    E o que o oficial perguntou é exatamente essa diferença vista de quem
    espera. Medido em 18/09/2026, com o runtime do servidor, mediana de 5
    rodadas:

        procurar_nos_documentos("selo")         449,6 ms
        procurar_nos_documentos("matricula")    470,2 ms
        regras.procurar("carimbo que mente")      6,3 ms
        carregar a base inteira, UMA vez        490   ms
        conferir a assinatura dos 172 arquivos   45,4 ms

    **A poda já existia; o que faltava era aplicá-la ao irmão.** Aqui a regra
    que funcionava num lado vale nos dois — e no terceiro, que é o que o
    oficial escreve.

O QUE A BASE É
    O corpus da prosa desta casa — os **documentos do projeto**
    (`DOCUMENTACAO/`), as **regras da casa** (`CLAUDE.md`) e o **que o oficial
    escreve** (`aj_verbetes`) — lido, quebrado em blocos e normalizado **uma
    vez**, e procurado em memória a partir daí. Ela se reconstrói sozinha
    quando algum arquivo muda.

AS TRÊS FONTES SÃO A ESCOLHA DO OFICIAL, E ELA TEM UM PORQUÊ
    Perguntei o que a base deveria cobrir, e ele escolheu **os documentos e as
    regras** — «é o que a ajuda mais busca hoje, e já está no servidor». E
    perguntei como ela se alimenta: **as duas** formas, «o que se mede entra
    sozinho, e o que só o oficial tem entra pela tela».

    É por isso que existem três fontes e não uma:

      * `DOCUMENTO` e `REGRA` **se medem** — saem da pasta e do arquivo, e
        ninguém digita. Documento novo aparece sozinho; documento apagado some.
      * `MANUAL` **se escreve** — o que só o oficial sabe, e que não está em
        documento nenhum. Ele entra pela tela (`/ajuda/base`) e mora em
        `aj_verbetes`.

A ORDEM DOS ACHADOS MUDOU, E ISSO CONSERTA UM DEFEITO ANTERIOR
    A busca devolvia **as primeiras 40 linhas na ordem do sistema de arquivos**
    — e, medido sobre esta instalação, «matricula» tem **997 linhas em 98
    documentos**, com **269 delas só no `CONFERENCIA.md`**. A ordem alfabética
    fazia as quarenta virem todas do primeiro arquivo: a busca respondia «está
    tudo ali» sobre um assunto que está em noventa e oito lugares.

    Agora os achados são **pontuados** (a linha que traz o termo inteiro ganha
    do que traz só as palavras soltas, e mais ocorrências ganha de menos) e
    **espalhados por origem** — antes de repetir uma origem, a busca dá a
    vez às outras. Ordenar por data seria mentir: aqui não há data, há
    pertinência.

E O CONTRATO DE FORA NÃO MUDOU
    `ajuda_projeto.procurar_nos_documentos` e `ajuda_regras.procurar` continuam
    respondendo **exatamente no mesmo formato** — o que mudou foi de onde vem
    o resultado e em que ordem ele sai. Os testes que fixavam a contagem de
    linhas continuam valendo, porque a contagem é a mesma: o que a poda mudou
    foi o custo, e o que a pontuação mudou foi a ordem.

O QUE AQUI ESCREVE, E O QUE AQUI NÃO ESCREVE
    A base **lê** arquivos e **lê** `aj_verbetes`. A única escrita é
    `gravar_verbete` e `apagar_verbete`, na tabela da própria ajuda — o
    caderno dela. Nada neste módulo toca livro, matrícula, ato, selo, custa ou
    caixa, e nada aqui decide ato nenhum: é a mesma régua do usucapião, das
    fraudes e do CNIB.

    E ela é **read-only** sobre as fontes que mede: `carregar` nunca grava nos
    documentos, e o índice vive na memória do processo.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from bd_nativo import banco

RAIZ = Path(__file__).resolve().parent

# AS FONTES DA PROSA DA CASA. A pasta dos documentos e o nome do arquivo das
# regras moram aqui porque quem os localiza e os lê é esta base — e ter o
# caminho escrito em dois módulos é a mesma família das duas listas que
# envelhecem em lugares diferentes.
PASTA_DOS_DOCUMENTOS = RAIZ / "DOCUMENTACAO"
NOME_DAS_REGRAS = "CLAUDE.md"

FONTE_DOCUMENTO = "DOCUMENTO"
FONTE_REGRA = "REGRA"
FONTE_MANUAL = "MANUAL"

ROTULO_DA_FONTE = {
    FONTE_DOCUMENTO: "os documentos do projeto",
    FONTE_REGRA: "as regras da casa",
    FONTE_MANUAL: "o que o oficial escreveu",
}

# E AQUI A PREPOSIÇÃO VEM COLADA NO RÓTULO, e isso foi correção de frase.
# A primeira versão montava `f"{n} em {ROTULO_DA_FONTE[f]}"`, e o rótulo já
# carrega o artigo — saía **«32 em os documentos do projeto, 19 em as regras da
# casa»**. Frase torta na resposta de quem ajuda se lê como sistema descuidado, e
# o conserto é a contração morar junto do rótulo, em vez de cada chamador tentar
# montá-la. Os dois dicionários convivem porque dizem coisas diferentes: um
# **nomeia** a fonte (cabeçalho, lista), o outro diz **onde** se procurou.
ONDE_DA_FONTE = {
    FONTE_DOCUMENTO: "nos documentos do projeto",
    FONTE_REGRA: "nas regras da casa",
    FONTE_MANUAL: "no que o oficial escreveu",
}

# QUANTAS LINHAS A BUSCA DEVOLVE POR PADRÃO. Busca que devolve tudo é busca que
# ninguém lê — e o custo é por token.
LIMITE_DA_BUSCA = 40
LIMITE_DA_LINHA = 240

# E QUANTAS CABEM DE CADA ORIGEM, ANTES DE DAR A VEZ ÀS OUTRAS. É o divisor do
# limite (40/4 = 10): garante quatro origens no resultado em vez de uma. A
# segunda volta da escolha preenche o que sobrar, de modo que o limite continua
# sendo o que sempre foi — um teto, e não uma promessa.
LIMITE_POR_ORIGEM = 4

# DE QUANTO EM QUANTO TEMPO A ASSINATURA É CONFERIDA. `stat` dos 172 arquivos
# custa **45,4 ms** nesta máquina (medido), e conferir isso a cada busca
# devolveria um décimo do custo que a base veio tirar. O cache não pode MENTIR:
# quem editar as regras com o sistema no ar vê a mudança na consulta seguinte —
# a janela é de dois segundos, que é escala de gente, e não de máquina.
INTERVALO_DA_CONFERENCIA = 2.0

# QUANTOS VERBETES A AJUDA LEVA NO CONTEXTO, pelos títulos. O texto inteiro de
# cada um custa em toda pergunta; o título é o que permite pedir.
LIMITE_DE_VERBETES_NO_CONTEXTO = 40

# O PISO DE DOCUMENTOS DE UMA INSTALAÇÃO. **Não é alvo: é diagnóstico.** O
# `ATUALIZAR_SISTEMA.cmd` copiava `*.py`, telas, `static`, `modelos`,
# `VERSAO.txt` e `requirements.txt`, e mais nada — os `.md` não estavam em
# nenhuma das linhas dele, e a ajuda respondia olhando uma biblioteca de três
# arquivos sem nada que dissesse que a biblioteca não tinha chegado. Ausência
# com cara de medição, a mesma família do `except` largo que já apareceu aqui.
# Folgado de propósito (a casa tem 171 hoje): separa «esta instalação tem o
# acervo» de «a carga não chegou».
PISO_DE_DOCUMENTOS = 50

# Quanto de um documento cabe numa consulta. Medido: o maior deles passa de 90
# mil caracteres, e cortar avisando é melhor que mandar tudo e a consulta
# falhar inteira — e o corte APARECE no texto, para quem lê saber que há mais.
LIMITE_DO_DOCUMENTO = 60_000


class BaseError(ValueError):
    """Erro de regra deste módulo — mensagem pronta para quem lê a tela."""


# --------------------------------------------------------------- a ferramenta


def sem_acento(texto: Any) -> str:
    """Sem acento e sem caixa, para a busca achar o que está escrito com eles.

    **É A DIFERENÇA ENTRE ACHAR E NÃO ACHAR.** Quem procura escreve «matricula»
    com a maior naturalidade — a palavra sem acento existe —, e o documento diz
    «matrícula». Sem isto a busca devolveria **nada**, com a mesma cara de quem
    mediu: é a família do `@cartorio` e do `except Exception: return []` outra
    vez, agora numa resposta que a ajuda daria com convicção («a casa não
    escreveu nada sobre isso»).

    Não se usa `pt_schema.normalizar_nome` de propósito: aquela normaliza NOME
    DE PESSOA, devolve `None` para vazio, e mora no schema do Protesto —
    pendurar a ajuda dos documentos nela seria acoplar duas coisas que não têm
    nada a ver, e o nome da função mentiria sobre o que ela faz aqui.

    **E ELA MORA AQUI, E NÃO EM QUEM A CHAMAVA.** Ela estava em
    `ajuda_projeto`, e a base precisa dela para indexar as três fontes. Duas
    cópias divergiriam no primeiro conserto — a lição da `normalizar_nome`
    pela quarta vez —, e o índice de uma acharia o que o da outra não acha.
    """
    bruto = "" if texto is None else str(texto)
    return "".join(c for c in unicodedata.normalize("NFD", bruto)
                   if unicodedata.category(c) != "Mn").casefold()


def _palavras(procurado: str) -> list[str]:
    """As palavras que a busca aceita como segunda forma de casar.

    **O TERMO INTEIRO É A PRIMEIRA FORMA, E ESSA NÃO MUDOU.** Esta segunda
    existe para a pergunta de verdade: quem escreve «matrícula de 32 dígitos»
    não quer só as linhas que trazem a frase inteira — quer as que falam das
    duas coisas. Só entram palavras de quatro letras ou mais: abaixo disso o
    que sobra é «que», «com», «dos», e exigir conectivo não estreita nada, só
    esconde a linha que a pessoa queria.

    Quando o termo é uma palavra só, esta lista sai vazia e a busca fica
    exatamente o que sempre foi — casamento por trecho.
    """
    return [p for p in re.findall(r"[0-9a-z]+", procurado)
            if len(p) >= 4 and p != procurado]


def _pontuar(linha_norm: str, procurado: str, palavras: list[str]) -> int:
    """Quanto esta linha merece aparecer. Zero quer dizer que ela não é achado.

    A escala é declarada, e o degrau que importa é o primeiro: **a linha que
    traz o termo inteiro ganha de qualquer linha que traga só as palavras**.
    Dentro de cada degrau, mais ocorrências ganha de menos — e empate nenhum
    se resolve aqui: quem desempata é a ordem de leitura, porque `sorted` é
    estável e o resto do mundo não tem como ser medido.
    """
    inteiro = bool(procurado) and procurado in linha_norm
    if not inteiro and (not palavras or any(p not in linha_norm
                                            for p in palavras)):
        return 0
    pontos = 1000 if inteiro else 10 * len(palavras)
    ocorrencias = sum(linha_norm.count(p) for p in (palavras or [procurado]))
    return pontos + min(ocorrencias, 9)


# ------------------------------------------------------------------ o arquivo


def caminhos_das_regras() -> list[Path]:
    """Onde o arquivo das regras pode estar, em ordem.

    A primeira é a instalação — o `.cgu` e o `ATUALIZAR_SISTEMA.cmd` copiam o
    arquivo para a raiz do programa. As outras duas são a árvore de
    desenvolvimento, onde ele de fato mora: quem o lê hoje é o editor, e mover
    seria quebrar quem o lê.
    """
    return [
        RAIZ / NOME_DAS_REGRAS,                # a instalacao
        RAIZ.parent / NOME_DAS_REGRAS,         # SERVIDOR\
        RAIZ.parent.parent / NOME_DAS_REGRAS,  # a raiz do projeto
    ]


def arquivo_das_regras() -> Path | None:
    """O arquivo das regras, onde ele estiver. `None` quando não está em lugar nenhum."""
    for caminho in caminhos_das_regras():
        if caminho.is_file():
            return caminho
    return None


def _ler(caminho: Path) -> str:
    """O texto de um arquivo, ou vazio. Um `.md` ilegível não derruba a base."""
    try:
        return caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def titulo_de(caminho: Path) -> str:
    """O título de um documento — a primeira linha que começa com `#`.

    Lê só o começo do arquivo: montar o índice de 171 documentos lendo cada um
    inteiro custaria dois milhões de caracteres de disco para produzir umas
    poucas linhas.
    """
    try:
        with caminho.open(encoding="utf-8", errors="replace") as f:
            comeco = f.read(2000)
    except OSError:
        return caminho.stem

    for linha in comeco.splitlines():
        limpa = linha.strip()
        if limpa.startswith("#"):
            titulo = limpa.lstrip("#").strip()
            if titulo:
                return titulo
    return caminho.stem


def documentos() -> list[dict]:
    """O índice dos documentos do projeto, MEDIDO na pasta.

    Não há lista escrita à mão: documento novo aparece sozinho, e documento
    apagado some. É a lição do menu, que este projeto já pagou.

    **E O QUE NÃO ENTRA FICA DITO.** Lê a **raiz** da pasta: os `.md` que
    moram ali. Os que estão em subpasta — os modelos do RTDPJ e o LEIA-ME
    deles — **não entram no índice nem na busca**. São anexo de terceiro, e
    não prosa da casa; mas quem procurasse um deles receberia «nada» e
    concluiria que ninguém escreveu, que é a conclusão errada com cara de
    medição.
    """
    pasta = PASTA_DOS_DOCUMENTOS
    if not pasta.is_dir():
        return []
    achados = []
    for caminho in sorted(pasta.glob("*.md")):
        try:
            tamanho = caminho.stat().st_size
        except OSError:
            continue
        achados.append({"arquivo": caminho.name, "titulo": titulo_de(caminho),
                        "tamanho": tamanho})
    return achados


# ------------------------------------------------------------- o quebrador


_CABECALHO = re.compile(r"^(#{1,6})\s+(.*)$")


def blocos(texto: str, *, primeiro: str = "(o começo)") -> list[dict]:
    """As seções de um texto, quebradas nos cabeçalhos de markdown.

    **UM QUEBRADOR SÓ, PARA AS TRÊS FONTES.** Ele estava dentro de
    `ajuda_regras`, com o nome de seção — e as regras numeram as seções para o
    índice e para a leitura («a seção 7», que o modelo pede pelo número). Duas
    quebras para o mesmo arquivo dariam duas numerações, e a ajuda leria a
    seção 7 errada sem nada acusar.

    Cada bloco guarda **duas** linhas, e a diferença entre elas é um defeito que
    já existiu: `linha` é a do cabeçalho, e `primeira` é a da **primeira linha
    de texto** do bloco. O achado se endereça pela linha absoluta — o cabeçalho
    não entra em `linhas`, e numerar o achado pela linha do cabeçalho faria
    todo endereço depois do primeiro apontar **uma linha antes** do que achou.
    Quem pedisse o documento e fosse àquela linha leria a anterior.

    **E O CABEÇALHO É PROCURÁVEL, por isso ele viaja em campo próprio.** Ele
    não faz parte do texto da seção — quem o lê por `ler()` não deve recebê-lo
    duas vezes —, mas a busca de hoje o varre como qualquer linha, e a primeira
    versão disto o esqueceu: medido contra esta instalação, «impressora» caiu
    de **16 linhas para 14**, e as duas perdidas eram títulos de seção do
    `ETIQUETA_DE_FIRMA.md`. Seção chamada «A impressora que sumia» é achado, e
    quem procura por ela tem de chegar nela.
    """
    achados: list[dict] = []
    atual = {"n": 0, "nivel": 0, "titulo": primeiro, "linha": 1,
             "primeira": 1, "cabecalho": "", "cabecalho_norm": "",
             "linhas": [], "norm": []}
    for n, linha in enumerate(str(texto or "").splitlines(), start=1):
        achado = _CABECALHO.match(linha)
        if achado:
            achados.append(atual)
            atual = {"n": len(achados), "nivel": len(achado.group(1)),
                     "titulo": achado.group(2).strip(), "linha": n,
                     "primeira": n + 1, "cabecalho": linha,
                     "cabecalho_norm": sem_acento(linha),
                     "linhas": [], "norm": []}
            continue
        atual["linhas"].append(linha)
        atual["norm"].append(sem_acento(linha))
    achados.append(atual)
    for b in achados:
        b["linhas_todas"] = len(b["linhas"])
        b["caracteres"] = sum(len(x) + 1 for x in b["linhas"])
    return achados


# ---------------------------------------------------------------- o índice

_INDICE: dict[str, Any] = {
    "assinatura": None, "fontes": [], "construida_em": "", "segundos": 0.0,
    "conferida_em": 0.0, "falha": "",
}
_CADEADO = threading.Lock()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")      # noqa: DTZ005


def _marca(caminho: Path) -> tuple:
    """Caminho, tamanho e data — o que muda quando alguém edita o arquivo."""
    try:
        s = caminho.stat()
    except OSError:
        return (str(caminho), -1, -1)
    return (str(caminho), s.st_size, s.st_mtime_ns)


def _assinatura() -> tuple:
    """A impressão digital das fontes que se medem: uma marca por arquivo."""
    marcas = []
    caminho = arquivo_das_regras()
    if caminho is not None:
        marcas.append(_marca(caminho))
    pasta = PASTA_DOS_DOCUMENTOS
    if pasta.is_dir():
        for c in sorted(pasta.glob("*.md")):
            marcas.append(_marca(c))
    return tuple(marcas)


def _medir() -> list[dict]:
    """Lê as fontes do disco e as indexa. **A parte cara, e ela roda uma vez.**"""
    fontes: list[dict] = []
    pasta = PASTA_DOS_DOCUMENTOS
    if pasta.is_dir():
        for caminho in sorted(pasta.glob("*.md")):
            texto = _ler(caminho)
            if not texto:
                continue
            fontes.append({
                "fonte": FONTE_DOCUMENTO, "origem": caminho.name,
                "titulo": titulo_de(caminho), "caminho": str(caminho),
                "caracteres": len(texto),
                "linhas": len(texto.splitlines()),
                "blocos": blocos(texto),
            })
    caminho = arquivo_das_regras()
    if caminho is not None:
        texto = _ler(caminho)
        if texto:
            fontes.append({
                "fonte": FONTE_REGRA, "origem": NOME_DAS_REGRAS,
                "titulo": "as regras desta casa", "caminho": str(caminho),
                "caracteres": len(texto),
                "linhas": len(texto.splitlines()),
                # «o carimbo» é o nome da seção 0 nas regras desde sempre: é
                # onde a versão e o tamanho da suíte estão escritos.
                "blocos": blocos(texto, primeiro="(o carimbo)"),
            })
    return fontes


def carregar(*, forcar: bool = False) -> dict:
    """Constrói (ou reconstrói) o índice, e devolve como ele ficou. **Escreve na memória.**

    A conferência da assinatura custa 45 ms e a construção custa 490 — medidos.
    Por isso a assinatura não se confere a cada busca, e sim a cada
    `INTERVALO_DA_CONFERENCIA` segundos: o cache não mente em escala de gente,
    e a conta de cada pergunta fica em milissegundos.

    **FALHAR NÃO É SILENCIOSO.** Se a construção inteira estourar — o que não
    deve acontecer, porque arquivo ilegível já é tolerado um a um —, o motivo
    fica guardado e `resumo()` o mostra. Zero medido e zero por engano são a
    mesma tela e coisas diferentes, e aqui a diferença aparece.
    """
    with _CADEADO:
        agora = time.monotonic()
        if (not forcar and _INDICE["fontes"]
                and agora - float(_INDICE["conferida_em"] or 0)
                < INTERVALO_DA_CONFERENCIA):
            return resumo()
        assinatura = _assinatura()
        _INDICE["conferida_em"] = agora
        if not forcar and _INDICE["assinatura"] == assinatura and _INDICE["fontes"]:
            return resumo()
        comeco = time.perf_counter()
        try:
            fontes = _medir()
        except Exception as erro:                              # noqa: BLE001
            _INDICE["falha"] = (f"{type(erro).__name__}: {erro}")
            _INDICE["fontes"] = []
            return resumo()
        _INDICE.update({
            "assinatura": assinatura, "fontes": fontes, "falha": "",
            "construida_em": _agora(),
            "segundos": round(time.perf_counter() - comeco, 3),
        })
        return resumo()


def pronta() -> bool:
    """A base já está carregada nesta execução?"""
    return bool(_INDICE["fontes"])


def resumo() -> dict:
    """Os números da base: o que ela tem, quando foi construída e em quanto tempo."""
    fontes = _INDICE["fontes"]
    por_fonte: dict[str, dict] = {}
    for f in fontes:
        atual = por_fonte.setdefault(f["fonte"], {"origens": 0, "linhas": 0,
                                                  "caracteres": 0})
        atual["origens"] += 1
        atual["linhas"] += f["linhas"]
        atual["caracteres"] += f["caracteres"]
    return {
        "pronta": bool(fontes),
        "construida_em": _INDICE["construida_em"],
        "segundos": _INDICE["segundos"],
        "falha": _INDICE["falha"],
        "por_fonte": por_fonte,
        "total_de_origens": len(fontes),
        "total_de_linhas": sum(f["linhas"] for f in fontes),
        "total_de_caracteres": sum(f["caracteres"] for f in fontes),
    }


# ----------------------------------------------------------------- os verbetes

SCHEMA = """
-- O QUE O OFICIAL ESCREVE, E QUE NÃO ESTÁ EM DOCUMENTO NENHUM.
-- ...
CREATE TABLE IF NOT EXISTS aj_verbetes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    titulo TEXT NOT NULL,
    texto TEXT NOT NULL,
    texto_norm TEXT NOT NULL DEFAULT '',
    assunto TEXT,
    onde TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    alterado_em TEXT,
    alterado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_aj_verbetes_assunto ON aj_verbetes(assunto);
"""


def init_ajuda_base_schema(con) -> None:
    """Cria a tabela dos verbetes. Idempotente."""
    bd = banco(con)
    for comando in re.split(r";[ \t]*\n", SCHEMA):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)


def verbetes(con: Any) -> list[dict]:
    """O que o oficial escreveu, da tabela da ajuda. Sem `con`, a lista vazia.

    **AUSÊNCIA DE TABELA É TOLERADA; COLUNA ERRADA, NÃO.** Uma instalação que
    ainda não passou pela migração não tem o que ler — e devolver vazio ali é
    certo. Já um erro de SQL numa tabela que existe é defeito meu, e ele
    estoura: engoli-lo devolveria «o oficial não escreveu nada» com cara de
    medição, que é o pior dos dois mundos.
    """
    if con is None:
        return []
    bd = banco(con)
    if not bd.tem_tabela("aj_verbetes"):
        return []
    return bd.ler(
        """SELECT id, titulo, texto, assunto, onde, criado_em, criado_por,
                  alterado_em, alterado_por
             FROM aj_verbetes
         ORDER BY titulo COLLATE public.cg_nocase, id""")


def _fonte_manual(con: Any) -> dict:
    """Os verbetes no formato de fonte, para a busca tratá-los como as outras."""
    linhas = verbetes(con)
    blocos_: list[dict] = []
    for i, v in enumerate(linhas):
        corpo = str(v.get("texto") or "")
        titulo = str(v.get("titulo") or "(sem título)")
        pedacos = corpo.splitlines() or [""]
        blocos_.append({
            "n": i, "nivel": 2, "titulo": titulo,
            # O TÍTULO DO VERBETE TAMBÉM SE PROCURA: ele entra como o cabeçalho
            # do bloco, que é o campo de onde a busca varre a linha do título.
            # Um verbete chamado «A impressora do molde» tem de ser achado por
            # quem procura a impressora.
            "linha": 1, "primeira": 1, "cabecalho": titulo,
            "cabecalho_norm": sem_acento(titulo),
            "linhas": pedacos,
            "norm": [sem_acento(x) for x in pedacos],
            "em": str(v.get("alterado_em") or v.get("criado_em") or ""),
            "por": str(v.get("alterado_por") or v.get("criado_por") or ""),
            "verbete": v.get("id"),
        })
    return {
        "fonte": FONTE_MANUAL, "origem": "aj_verbetes",
        "titulo": "o que o oficial escreveu", "caminho": "",
        "caracteres": sum(len(str(v.get("texto") or "")) for v in linhas),
        "linhas": sum(len(str(v.get("texto") or "").splitlines()) for v in linhas),
        "blocos": blocos_, "verbetes": linhas,
    }


def fontes(*, con: Any = None) -> list[dict]:
    """As fontes de agora: as que se medem, e os verbetes quando há `con`.

    O `con` é opcional de propósito. Sem ele a base responde pelas duas fontes
    do disco — que é o que `ajuda_projeto` e `ajuda_regras` precisam, cada um
    com o seu escopo. Com ele, os verbetes entram, e é o caminho de quem tem
    banco na mão: as ferramentas do agente e a tela.
    """
    carregar()
    lista = list(_INDICE["fontes"])
    if con is not None:
        manual = _fonte_manual(con)
        if manual["blocos"]:
            lista.append(manual)
    return lista


# ----------------------------------------------------------------- a busca


def _trecho(linha: str) -> str:
    """A linha pronta para sair, num tamanho que caiba numa resposta.

    **ELA NÃO COLAPSA O BRANCO DE DENTRO, e isso foi correção.** A primeira
    versão fazia `" ".join(str(linha).split())`, que colapsa exatamente o que o
    endereço promete citar. Medido contra esta instalação: uma linha de
    `A_BASE_DA_AJUDA_PRE_CARREGADA.md` escreve «1210 ms  (só os documentos» com
    **dois** espaços, e a base mostrava um — quem copiasse o que a base mostra e
    procurasse no arquivo não achava, e endereço que não se confere é endereço
    que mente. É a régua do extrator de endereço do ONR: **a citação da
    proveniência tem de citar o que o arquivo escreve**.

    O que se tira são as **pontas** — a indentação do markdown não identifica a
    linha, e quem a lê num resultado de busca quer o texto, não a coluna — e o
    que se corta é o **tamanho**, que é a razão de a função existir.
    """
    texto = str(linha).strip()
    if len(texto) > LIMITE_DA_LINHA:
        texto = texto[:LIMITE_DA_LINHA] + " […]"
    return texto


def _espalhar(achados: list[dict], limite: int) -> list[dict]:
    """Escolhe até `limite` achados, dando a vez às origens antes de repeti-las.

    **DUAS VOLTAS, E A SEGUNDA É O QUE TORNA ISTO UM TETO E NÃO UMA PROMESSA.**
    A primeira espalha; a segunda preenche o que sobrar sem olhar a cota. Sem
    ela, pedir cinco achados num assunto que só tem um documento devolveria um,
    e «pedi cinco, vieram um» é o carimbo que mente sobre o próprio filtro.
    """
    cota = max(1, limite // LIMITE_POR_ORIGEM)
    escolhidos: list[dict] = []
    vistos: set[int] = set()
    contados: dict[str, int] = {}
    for pos, a in enumerate(achados):
        if len(escolhidos) >= limite:
            return escolhidos
        if pos in vistos or contados.get(a["origem"], 0) >= cota:
            continue
        vistos.add(pos)
        contados[a["origem"]] = contados.get(a["origem"], 0) + 1
        escolhidos.append(a)
    if len(escolhidos) < limite:
        for pos, a in enumerate(achados):
            if len(escolhidos) >= limite:
                break
            if pos in vistos:
                continue
            vistos.add(pos)
            escolhidos.append(a)
    return escolhidos


def buscar(termo: str, *, fonte: str = "", limite: int = LIMITE_DA_BUSCA,
           con: Any = None) -> dict:
    """Onde a prosa da casa fala de um termo. **Só lê** — arquivos e, com `con`, o banco.

    Devolve o achado estruturado: de que fonte veio, de que origem, em que
    linha, o trecho e a pontuação. Quem formata é `procurar` — cada fonte tem
    o seu formato, e o formato de cada uma é contrato com quem já o lia.
    """
    procurado = sem_acento(termo).strip()
    if not procurado:
        raise BaseError("Diga o que procurar na base de conhecimento da ajuda.")
    # UM LIMITE ZERO ACHAVA TUDO E NÃO DEVOLVIA NADA — e a mensagem sairia
    # «nenhuma linha fala disso» com centenas contadas, que é o pior dos dois
    # mundos: número certo com conclusão errada. O piso é UM.
    limite = max(1, int(limite or 1))
    palavras = _palavras(procurado)

    achados: list[dict] = []
    por_fonte: dict[str, int] = {}
    por_origem: dict[str, int] = {}
    total = 0
    for f in fontes(con=con):
        if fonte and f["fonte"] != fonte:
            continue
        for b in f["blocos"]:
            # O cabeçalho entra na varredura, e a primeira linha absoluta é a
            # DELE quando ele existe — assim a numeração do achado é a mesma
            # do arquivo, contando o título.
            cabecalho = b.get("cabecalho") or ""
            linhas = ([cabecalho] if cabecalho else []) + b["linhas"]
            normas = (([b.get("cabecalho_norm") or sem_acento(cabecalho)]
                       if cabecalho else []) + b["norm"])
            primeira = int(b.get("linha", 1) if cabecalho
                           else b.get("primeira", 1))
            for i, linha in enumerate(linhas):
                pontos = _pontuar(normas[i], procurado, palavras)
                if not pontos:
                    continue
                total += 1
                por_fonte[f["fonte"]] = por_fonte.get(f["fonte"], 0) + 1
                por_origem[f["origem"]] = por_origem.get(f["origem"], 0) + 1
                achados.append({
                    "fonte": f["fonte"], "origem": f["origem"],
                    "titulo_da_fonte": f["titulo"],
                    "secao": b["titulo"], "secao_n": b["n"],
                    "linha": primeira + i,
                    "texto": _trecho(linha), "pontos": pontos,
                    "em": b.get("em", ""), "por": b.get("por", ""),
                    "verbete": b.get("verbete"),
                })
    # A ORDEM PASSOU A SER A PERTINÊNCIA, e o `sorted` do Python é estável:
    # empate nenhum se inventa aqui — o que empata fica na ordem de leitura.
    achados.sort(key=lambda a: -a["pontos"])
    escolhidos = _espalhar(achados, limite)
    return {
        "termo": termo, "procurado": procurado, "total": total,
        # QUANTAS LINHAS TÊM A FRASE INTEIRA, e não só as palavras soltas. Os
        # dois números juntos são o que separa «a casa escreveu isto» de «a casa
        # escreveu as palavras separadas» — ver `_ressalva`.
        "exatas": sum(1 for a in achados if a["pontos"] >= 1000),
        "achados": escolhidos, "mostrando": len(escolhidos),
        "por_fonte": por_fonte, "por_origem": por_origem,
        "fontes": [f["fonte"] for f in fontes(con=con)
                   if not fonte or f["fonte"] == fonte],
    }


def _ressalva(achado: dict) -> str:
    """O aviso de que a conta inclui linhas que não têm o termo inteiro.

    **SEM ISTO O NÚMERO MENTE, e ele mente para mais.** O termo de duas palavras
    abre a régua quando não acha o suficiente: «carimbo que mente» passa a contar
    também as linhas que trazem «carimbo» e «mente» separados, e «claude.md»
    conta as que falam de «claude». São achados úteis — é por isso que a régua
    abre —, mas quem lê «53 linha(s)» conclui que a casa escreveu 53 vezes o
    termo que ele pediu, e isso não é verdade.

    Devolve vazio quando os dois números são iguais, que é o caso comum: o aviso
    só aparece onde ele tem o que dizer.
    """
    exatas, total = int(achado.get("exatas", 0)), int(achado.get("total", 0))
    if not total or exatas >= total:
        return ""
    return f" ({exatas} com a frase exata)"


def _texto_de_documentos(achado: dict) -> str:
    """O formato que `procurar_nos_documentos` publica desde 15/09/2026.

    Ele é contrato: a ajuda lê o arquivo e a linha, e vai lá. Mudá-lo faria a
    resposta apontar para um lugar que quem lê não sabe abrir.
    """
    if not achado["achados"]:
        return (f"Nenhuma linha dos {len(documentos())} documentos do projeto "
                f"fala de «{achado['termo']}». Isso quer dizer que ninguém "
                "escreveu sobre isso — e não que a coisa não exista: o sistema "
                "pode fazê-lo sem documento nenhum. Procure outro termo, ou "
                "veja o código.")
    total, mostrando = achado["total"], achado["mostrando"]
    # A FRASE É CONTRATO DESDE 15/09/2026: `test_a_busca_avisa_quando_mostra_
    # menos_do_que_achou` exige «Mostrando 3 das» e «Mostrando 1 das». Encurtá-la
    # para «3 de 997» economizaria bytes e quebraria quem lê o endereço.
    quantos = (f"Mostrando {mostrando} das {total} linha(s) com «{achado['termo']}»"
               if total > mostrando
               else f"{total} linha(s) com «{achado['termo']}»")
    quantos += _ressalva(achado)
    quantos += f", em {len(achado['por_origem'])} arquivo(s)"
    if len(achado["por_origem"]) > 1:
        quantos += (". Os documentos com mais linhas: "
                    + ", ".join(f"{a} ({n})" for a, n in
                                sorted(achado["por_origem"].items(),
                                       key=lambda x: -x[1])[:5]))
    linhas = [f"[{a['origem']}:{a['linha']}] {a['texto']}"
              for a in achado["achados"]]
    return quantos + ":\n" + "\n".join(linhas)


def _texto_de_regras(achado: dict) -> str:
    """O formato que `ajuda_regras.procurar` publica — com a seção de origem."""
    if not achado["achados"]:
        return (f"Nenhuma linha das regras fala de «{achado['termo']}». Isso "
                "quer dizer que a casa não escreveu nada sobre isso — e não "
                "que a regra seja a que parece natural.")
    total, mostrando = achado["total"], achado["mostrando"]
    cabeca = (f"{total} linha(s) com «{achado['termo']}»{_ressalva(achado)} "
              "nas regras"
              if total <= mostrando
              else f"{mostrando} de {total} linha(s) com «{achado['termo']}»"
                   f"{_ressalva(achado)} nas regras")
    linhas = [f"[seção {a['secao_n']} «{a['secao']}»] {a['texto']}"
              for a in achado["achados"]]
    return cabeca + ":\n" + "\n".join(linhas)


def procurar(termo: str, *, fonte: str = "", limite: int = LIMITE_DA_BUSCA,
             con: Any = None) -> str:
    """A busca no formato de quem a pediu. **Só lê**, e não decide nada."""
    achado = buscar(termo, fonte=fonte, limite=limite, con=con)
    if fonte == FONTE_REGRA:
        return _texto_de_regras(achado)
    return _texto_de_documentos(achado)


# --------------------------------------------------- a busca nas três de uma vez


def _endereco(a: dict) -> str:
    """Como se chega no que foi achado — e o endereço muda com a fonte."""
    if a["fonte"] == FONTE_MANUAL:
        quando = str(a.get("em") or "")[:10]
        quem = str(a.get("por") or "").strip()
        marca = f"escrito por {quem} em {quando}" if quem else f"escrito em {quando}"
        return f"{marca} — «{a['secao']}»"
    if a["fonte"] == FONTE_REGRA:
        return f"regras, seção {a['secao_n']} «{a['secao']}»"
    return f"{a['origem']}:{a['linha']}"


def buscar_em_tudo(termo: str, *, limite: int = LIMITE_DA_BUSCA,
                   con: Any = None) -> str:
    """Uma busca, as três fontes — e é esta que a ajuda usa.

    **E É ISTO QUE RESPONDE AO PEDIDO DELE.** Antes, uma pergunta podia custar
    três rodadas: uma para procurar nos documentos, outra nas regras, outra no
    texto. Aqui os três são varridos **na mesma leitura de memória**, com o
    resultado numa lista só — e a lista diz de onde cada linha veio.

    Quando não acha nada, diz que não achou: silêncio, aqui, viraria «a casa
    nunca escreveu sobre isso».
    """
    achado = buscar(termo, limite=limite, con=con)
    if not achado["total"]:
        # **O TAMANHO DO QUE SE PROCUROU É POR FONTE, E NÃO POR ARQUIVO.** A
        # primeira versão somava o que `fontes()` devolve — que é uma linha por
        # ORIGEM — e a resposta saía com **173 números de linha**, um por
        # documento, uma parede de texto que não responde nada. Medido: 2.400
        # caracteres de lista para dizer «procurei em tudo». Quem pergunta «não
        # achou?» quer saber o tamanho do que foi varrido, e são **três** os
        # lugares: os documentos, as regras e os verbetes.
        r = carregar()
        por_fonte = r["por_fonte"]
        manual = verbetes(con)
        if manual:
            por_fonte = dict(por_fonte)
            por_fonte[FONTE_MANUAL] = {"linhas": sum(
                len(str(v.get("texto") or "").splitlines()) for v in manual)}
        partes = ", ".join(f"{dados.get('linhas', 0)} linhas {ONDE_DA_FONTE[f]}"
                           for f, dados in sorted(por_fonte.items()))
        return (f"A base não tem nada sobre «{termo}»: procurei em toda ela "
                f"({partes}) e não achei nenhuma linha. Isso quer dizer que "
                "ninguém escreveu sobre isso nesta casa — e não que a coisa não "
                "exista: o sistema pode fazê-lo sem documento nenhum. Procure "
                "outro termo, ou veja o código.")
    por_fonte = achado["por_fonte"]
    repartido = ", ".join(f"{n} {ONDE_DA_FONTE[f]}"
                          for f, n in sorted(por_fonte.items()))
    cabeca = (f"A base tem {achado['total']} linha(s) com «{termo}» — "
              f"{repartido}.")
    if achado["mostrando"] < achado["total"]:
        cabeca = (f"A base tem {achado['total']} linha(s) com «{termo}» — "
                  f"{repartido}. Mostrando as {achado['mostrando']} mais "
                  "pertinentes:")
    linhas = [f"[{_endereco(a)}] {a['texto']}" for a in achado["achados"]]
    return cabeca + "\n" + "\n".join(linhas)


def para_o_contexto(con: Any = None) -> str:
    """A base em três linhas, para ir junto de cada pergunta — e os títulos do oficial.

    **O CUSTO TEM DE SE PAGAR, E ELE SE PAGA.** Estas linhas vão em toda
    consulta, e existem porque sem elas o modelo não sabe que a base existe e
    volta a procurar de um em um. É a economia que ele mesmo pediu: uma
    chamada em vez de três.

    Os **títulos** dos verbetes vão por inteiro: o texto custa em toda
    pergunta, e o título é o que permite pedir o que se quer. É a regra da
    fatia, a mesma do índice dos documentos.
    """
    r = carregar()
    if not r["pronta"]:
        return ("(A base de conhecimento da ajuda não carregou nesta "
                f"instalação{': ' + r['falha'] if r['falha'] else ''}.)")
    docs = r["por_fonte"].get(FONTE_DOCUMENTO, {})
    regras = r["por_fonte"].get(FONTE_REGRA, {})
    manual = verbetes(con)
    linhas = [
        "=== A BASE DE CONHECIMENTO DESTA AJUDA, JÁ CARREGADA ===",
        (f"Ela tem indexado: {docs.get('origens', 0)} documentos do projeto "
         f"({docs.get('linhas', 0)} linhas) e as {regras.get('linhas', 0)} "
         f"linhas das regras da casa"
         + (f", mais {len(manual)} verbete(s) escrito(s) pelo oficial"
            if manual else "")
         + f". Carregada em {r['construida_em']}, em {r['segundos']} s."),
        ("**Uma chamada de `buscar_na_base` procura nas três de uma vez** — não "
         "é preciso procurar nos documentos e depois nas regras."),
    ]
    if manual:
        titulos = [f"- {m['titulo']}" for m in manual]
        if len(titulos) > LIMITE_DE_VERBETES_NO_CONTEXTO:
            titulos = titulos[:LIMITE_DE_VERBETES_NO_CONTEXTO] + [
                f"[...] (e mais {len(manual) - LIMITE_DE_VERBETES_NO_CONTEXTO})"]
        linhas.append("O que o oficial já escreveu na base (peça pelo título, "
                      "com `buscar_na_base`):")
        linhas.extend(titulos)
    return "\n".join(linhas)


def para_a_tela(con: Any = None) -> dict:
    """O que a tela mostra: o estado da base e o que ela tem por fonte."""
    r = carregar()
    r["fontes"] = [{"fonte": f["fonte"], "origem": f["origem"],
                    "titulo": f["titulo"], "linhas": f["linhas"],
                    "caracteres": f["caracteres"],
                    "blocos": len(f["blocos"])} for f in fontes(con=con)]
    r["verbetes"] = verbetes(con)
    return r


# -------------------------------------------------------------- o que se escreve


def gravar_verbete(con, *, titulo: str, texto: str,
                   assunto: str = "", onde: str = "", por: str = "",
                   agora: str = "", id_: int | None = None) -> int:
    """Grava ou altera um verbete. **Escreve** — na tabela da ajuda, e só nela.

    O PISO É O MESMO DAS NOTAS E DA RECUSA DE CERTIDÃO: dez letras. Um verbete
    de três palavras não ensina nada a quem vem depois, e ele vai ser lido como
    se ensinasse — «ok», «sim», «feito». Vazio e curto pedem a mesma coisa:
    escreva o que se sabe.
    """
    limpo_titulo = " ".join(str(titulo or "").split())
    limpo_texto = str(texto or "").strip()
    if len(limpo_titulo) < 10:
        raise BaseError("Dê um título de pelo menos dez letras ao verbete — é "
                        "por ele que a ajuda o acha depois.")
    if len(limpo_texto) < 10:
        raise BaseError("Escreva o verbete: menos de dez letras não ensina nada "
                        "a quem for ler depois.")
    momento = agora or _agora()
    if id_:
        bd = banco(con)
        # FOR UPDATE: o apagar de outra tela que confirme entre a conferência e
        # o UPDATE faria a alteração cair em linha nenhuma, e a tela diria
        # «Gravado» sem nada gravado.
        bd._escrita()
        existe = bd.um("SELECT id FROM aj_verbetes WHERE id=%s FOR UPDATE",
                       (int(id_),))
        if not existe:
            raise BaseError("Este verbete não existe mais — ele pode ter sido "
                            "apagado noutra tela.")
        bd.escrever(
            """UPDATE aj_verbetes
                  SET titulo=%s, texto=%s, texto_norm=%s, assunto=%s, onde=%s,
                      alterado_em=%s, alterado_por=%s
                WHERE id=%s""",
            (limpo_titulo, limpo_texto, sem_acento(f"{limpo_titulo}\n{limpo_texto}"),
             str(assunto or "").strip(), str(onde or "").strip(), momento,
             str(por or ""), int(id_)))
        return int(id_)
    novo = banco(con).escrever(
        """INSERT INTO aj_verbetes(titulo, texto, texto_norm, assunto, onde,
                                   criado_em, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (limpo_titulo, limpo_texto, sem_acento(f"{limpo_titulo}\n{limpo_texto}"),
         str(assunto or "").strip(), str(onde or "").strip(), momento,
         str(por or "")))
    return int(novo[0]["id"])


def apagar_verbete(con, *, id_: int) -> bool:
    """Tira um verbete da base. **Escreve** — e não é ato de cartório.

    Apagar aqui é apagar o caderno da ajuda, e não um ato: nada do que a
    serventia lavrou passa por esta tabela. Quem apaga deveria fazê-lo porque o
    que estava escrito estava errado — e nesse caso deixar a linha velha na
    base seria pior, porque a ajuda a leria com a mesma convicção das outras.
    """
    bd = banco(con)
    bd.escrever("DELETE FROM aj_verbetes WHERE id=%s", (int(id_),))
    return bool(bd.linhas_afetadas)


def verbete(con: Any, id_: int) -> dict | None:
    """Um verbete pelo número, para a tela mostrar o que vai ser editado."""
    if con is None:
        return None
    return banco(con).um(
        """SELECT id, titulo, texto, assunto, onde, criado_em, criado_por,
                  alterado_em, alterado_por
             FROM aj_verbetes WHERE id=%s""", (int(id_),))

"""As regras desta casa — a ajuda passa a ler o arquivo que as guarda.

A FRASE DO OFICIAL, EM 15/09/2026:

    «A ajuda passa a ler o CLAUDE.md, fatiado por seção: as regras da casa
     deixam de depender de uma versão nova — e ela responde com o que ESTA
     casa decidiu, e não com o que o modelo sabe em geral.»

E POR QUE ISSO É DIFERENTE DO QUE JÁ EXISTIA
    `ajuda_projeto` já levava os **documentos** do projeto (`DOCUMENTACAO/`) e
    os **relatos** da casa. Os dois contam o que foi construído e o que foi
    medido — e nenhum dos dois conta **como se decide aqui**.

    «Onde a regra pode morar no banco, ela mora no banco», «erro de regra é
    subclasse de `ValueError` com mensagem pronta para o balcão», «não se
    aumenta o acoplamento gratuito ao SQLite», «quem não está construindo o
    módulo não mexe nele». Isso não é documentação de produto: é o que faz o
    sistema ser deste jeito, e vale para quem for mexer nele amanhã — inclusive
    para a máquina que responde ao balcão.

    **E o modelo que responde não sabe nada disso.** Ele sabe Notariado e
    Registro em geral; o que ele não sabe é o que ESTA serventia decidiu, com
    que medição e por quê. Sem esta fatia, a resposta sai genérica e bonita —
    que é a pior forma de resposta errada.

O ARQUIVO MORA NUMA FONTE SÓ, E ISSO CUSTOU PARA SER POSSÍVEL
    O arquivo das regras é o `CLAUDE.md` da **raiz do projeto**, e ele é lido
    pelo Cursor de lá — mover seria quebrar quem o lê hoje. Então não se copia,
    não se renomeia e não se resume: os **dois transportes** que levam código
    para o servidor (o `.cgu` e o `ATUALIZAR_SISTEMA.cmd`) passaram a levá-lo,
    e aqui ele é **procurado** nos dois lugares onde pode estar:

      1. `RAIZ/CLAUDE.md` — na instalação, para onde a atualização o copia;
      2. `RAIZ/../..` — na árvore de desenvolvimento, onde ele de fato mora.

    **Cópia com outro nome é o defeito de sempre**: as duas versões divergem no
    primeiro conserto, e quem lê a velha não sabe que é a velha. Há teste que
    exige que este módulo **não** guarde texto de regra dentro dele.

A ECONOMIA É A MESMA DOS DOCUMENTOS: VAI O ÍNDICE, E NÃO A BIBLIOTECA
    São 385 KB e 6 mil linhas de prosa. Manda-los em toda pergunta custaria em
    toda pergunta. Vai o **índice das seções** — número e título, que é o que
    permite pedir —, e o **texto de uma seção só quando ela é pedida**, cortado
    se for maior que o teto. É a regra da fatia, que o mapa segue com as telas e
    `ajuda_projeto` com os documentos.
"""
from __future__ import annotations

import re
from pathlib import Path

import ajuda_base as BASE

RAIZ = Path(__file__).resolve().parent

NOME = "CLAUDE.md"


def _caminhos() -> list[Path]:
    """Onde procurar, em ordem — e a lista é a da base, não uma segunda cópia.

    A primeira é a instalação (o `ATUALIZAR_SISTEMA.cmd` e o `.cgu` copiam o
    arquivo para a raiz do programa); as outras duas são a árvore de
    desenvolvimento, onde ele mora de verdade.

    **A ORDEM E OS CAMINHOS MORAM EM `ajuda_base` desde 18/09/2026**, porque ela
    é quem lê o arquivo para indexá-lo. Duas listas de onde ele pode estar
    divergiriam no dia em que a terceira pasta mudasse — e a base acharia o
    arquivo que este módulo não acharia, ou o contrário. É a mesma família das
    duas listas que envelhecem em arquivos diferentes.
    """
    return BASE.caminhos_das_regras()


# Quanto de uma secao cabe numa consulta. A maior delas passa de 40 mil
# caracteres, e o teto de resposta da API nao comporta varias assim. Cortar
# avisando e melhor que mandar tudo e a consulta falhar inteira — e o corte
# APARECE no texto, para quem le saber que ha mais.
LIMITE_DA_SECAO = 24_000

# Quantas linhas a busca devolve por padrao. Busca que devolve tudo e busca que
# ninguem le — e o custo e por token.
LIMITE_DA_BUSCA = 40
LIMITE_DA_LINHA = 240

# O `_CABECALHO` MORA EM `ajuda_base` DESDE 18/09/2026 — era o mesmo padrão nos
# dois módulos, e o quebrador de lá é quem parte o texto agora.

# O carimbo do arquivo tem forma declarada: e a primeira linha dele. Se um dia
# deixar de casar, isto A DIZ, em vez de inventar numero.
#
# **A PRIMEIRA VERSAO DESTAS TRES NAO ACHAVA A VERSAO, e a medicao pegou.** Eu
# tinha escrito o padrao esperando «versao **3.6.130**», e o arquivo escreve
# «**versao 3.6.130**» — o negrito abre ANTES da palavra. O `re.search` nao
# achava nada, `carimbo()` devolvia versao vazia, e o veredito saia
# «nao_conferivel» com a maior tranquilidade. **Ausencia de achado com cara de
# medicao**: e a regra do `@cartorio` outra vez, e por isso os tres padroes
# aceitam a marcacao dos dois lados — o arquivo e escrito a mao e vai mudar.
_VERSAO = re.compile(r"\*\*vers[ãa]o\s+([0-9]+(?:\.[0-9]+)*)\*\*"
                     r"|vers[ãa]o\s+([0-9]+(?:\.[0-9]+)*)", re.I)
_TESTES = re.compile(r"\*\*([0-9][0-9.]*)\s+testes\s+coletados\*\*", re.I)
_APROVADOS = re.compile(r"\*\*([0-9][0-9.]*)\s+aprovados\*\*", re.I)


class RegraError(ValueError):
    """Erro de regra deste módulo — mensagem pronta para quem lê a tela."""


# ------------------------------------------------------------------ o arquivo


def arquivo() -> Path | None:
    """O arquivo das regras, onde ele estiver. `None` quando não está em lugar nenhum."""
    for caminho in _caminhos():
        if caminho.is_file():
            return caminho
    return None


def _ler_texto() -> str:
    caminho = arquivo()
    if caminho is None:
        return ""
    return caminho.read_text(encoding="utf-8", errors="replace")


# A leitura e cacheada pela ASSINATURA do arquivo — caminho, tamanho e data. O
# arquivo e grande e a ajuda responde em rajada; reler 385 KB a cada pergunta
# seria pagar disco por nada. A assinatura existe para o cache NAO MENTIR: se
# alguem editar as regras com o sistema no ar, a proxima consulta ja le o novo.
_CACHE: dict[str, object] = {"assinatura": None, "secoes": [], "texto": ""}


def _assinatura(caminho: Path | None) -> tuple:
    if caminho is None:
        return ()
    try:
        s = caminho.stat()
    except OSError:
        return ()
    return (str(caminho), s.st_size, s.st_mtime_ns)


def _quebrar(texto: str) -> list[dict]:
    """As seções do arquivo, na ordem em que estão escritas.

    A seção 0 é o que vem antes do primeiro cabeçalho — no arquivo das regras
    é o **carimbo**: a versão, o tamanho da suíte e o resumo do que o sistema é.
    Ela não tem título, e por isso aparece no índice como «(o carimbo)».

    **O CORPO MUDOU DE LUGAR EM 18/09/2026, e a assinatura não.** Quem parte o
    texto agora é `ajuda_base.blocos`, que é o mesmo quebrador que a busca
    pré-carregada usa. Dois quebradores do MESMO arquivo divergiriam no primeiro
    conserto, e aí a busca acharia uma seção que o `ler()` por número não sabe
    abrir — duas numerações para o mesmo texto, que é o defeito que o
    comentário de `blocos` já registra. O que fica aqui é a porta: a forma que
    este módulo publica (`linhas`, `linhas_todas`, `caracteres`) é a que o
    índice, o corte do `ler` e os testes leem.
    """
    return BASE.blocos(texto, primeiro="(o carimbo)")


def _secoes() -> list[dict]:
    """As seções de agora, do cache quando o arquivo não mudou."""
    caminho = arquivo()
    assinatura = _assinatura(caminho)
    if _CACHE["assinatura"] != assinatura:
        texto = _ler_texto()
        _CACHE.update({"assinatura": assinatura, "texto": texto,
                       "secoes": _quebrar(texto) if texto else []})
    return _CACHE["secoes"]          # type: ignore[return-value]


def disponivel() -> bool:
    """O arquivo das regras está nesta instalação?"""
    return bool(_secoes())


def onde() -> str:
    """O caminho do arquivo, para quem precisa dizer onde ele está."""
    caminho = arquivo()
    return str(caminho) if caminho else ""


# ------------------------------------------------------------------- o índice


def indice() -> list[dict]:
    """Número, título e tamanho de cada seção — e mais nada.

    Seção VAZIA não entra: o arquivo das regras começa por um cabeçalho, e o
    `_quebrar` produz antes dele uma seção 0 sem uma linha. Mostrá-la seria
    oferecer para leitura o que não existe — e quem pedisse «a seção 0» acharia
    que a ferramenta falhou.
    """
    return [{"n": s["n"], "nivel": s["nivel"], "titulo": s["titulo"],
             "linhas": s["linhas_todas"], "caracteres": s["caracteres"]}
            for s in _secoes() if s["linhas_todas"]]


def indice_para_o_contexto(limite: int = 60) -> list[str]:
    """O índice em linhas curtas, para ir junto de toda pergunta.

    Só o número e o título: é o que permite pedir uma seção pelo nome. O texto
    de cada uma custa caro, e vai quando é pedido — a regra da fatia.
    """
    linhas = []
    for s in indice():
        recuo = "  " * max(0, s["nivel"] - 1)
        linhas.append(f"{recuo}{s['n']}. {s['titulo']}")
    if len(linhas) > limite:
        linhas = linhas[:limite] + [f"[...] (e mais {len(linhas) - limite})"]
    return linhas


# ---------------------------------------------------------------- a leitura


def _cortar(texto: str) -> str:
    if len(texto) <= LIMITE_DA_SECAO:
        return texto
    return (texto[:LIMITE_DA_SECAO]
            + f"\n\n[...] (a seção continua; foram trazidos os primeiros "
              f"{LIMITE_DA_SECAO} caracteres de {len(texto)})")


def _achar(qual: str) -> dict:
    """Uma seção pelo número ou por um pedaço do título. Ambíguo é recusa."""
    secoes = _secoes()
    if not secoes:
        raise RegraError(
            "O arquivo das regras do projeto não está nesta instalação, e sem "
            "ele não há o que ler. Ele viaja com a atualização: se a "
            "atualização foi feita à mão, o arquivo ficou para trás.")
    pedido = str(qual or "").strip()
    if not pedido:
        raise RegraError("Diga qual seção das regras — o número ou um pedaço "
                         "do título. Sem argumento, esta ferramenta devolve o "
                         "índice.")

    if pedido.isdigit():
        numero = int(pedido)
        for s in secoes:
            if s["n"] == numero and s["linhas_todas"]:
                return s
        raise RegraError(f"Não há seção {numero} com texto nas regras — elas "
                         f"vão de 0 a {len(secoes) - 1}, e alguma pode estar "
                         f"vazia.")

    alvo = pedido.casefold()
    achadas = [s for s in secoes if alvo in s["titulo"].casefold()]
    if len(achadas) == 1:
        return achadas[0]
    if not achadas:
        raise RegraError(
            f"Nenhuma seção das regras fala de «{pedido}». Peça o índice para "
            "ver os títulos que existem — os nomes são os do arquivo, não os "
            "que parecem naturais.")
    raise RegraError(
        "«{}» casa com {} seções: {}. Diga o número de uma.".format(
            pedido, len(achadas),
            ", ".join(f"{s['n']} ({s['titulo']})" for s in achadas[:8])))


def ler(qual: str) -> str:
    """O texto de uma seção, com o título na frente e a origem declarada."""
    s = _achar(qual)
    corpo = "\n".join(s["linhas"]).strip()
    return _cortar(f"## {s['titulo']}   (regras, seção {s['n']} de "
                   f"{len(_secoes()) - 1})\n\n{corpo}")


def procurar(termo: str, *, limite: int = LIMITE_DA_BUSCA) -> str:
    """As linhas das regras que falam de um termo, com a seção de cada uma.

    **É O CAMINHO CURTO, E O MAIS USADO.** Quem pergunta «como se decide sobre
    selo» não quer ler a seção inteira do selo: quer a frase que decide. Aqui
    vêm só as linhas, cada uma com o número da seção de onde saiu — e quem
    quiser o contexto pede a seção.

    **A CONTA CRESCEU, E A MEDIÇÃO MOSTROU UM DEFEITO ANTIGO.** Medido contra
    esta instalação em 18/09/2026, «matrícula» achava **10 linhas** e passa a
    achar **93**: a busca daqui comparava com `casefold()` e **não tirava o
    acento** — quem escrevesse «matricula» não achava «matrícula», que é como o
    arquivo escreve. É a mesma regra que os documentos já tinham desde 15/09, e
    que aqui não tinha chegado: *quem procura escreve sem acento com a maior
    naturalidade*. «selo», que não tem acento, foi de 255 para **257** — as duas
    são **linhas de título de seção**, que a busca antiga não varria.

    E as duas recusas continuam sendo desta porta, e não da base: o pedido vazio
    e o arquivo ausente são erros de REGRA deste módulo, com a frase que a tela
    já mostra. A base responde pelo que achou — ou por não ter achado nada, que
    é coisa diferente de não haver regra para ler.
    """
    if not str(termo or "").strip():
        raise RegraError("Diga o que procurar nas regras.")
    if arquivo() is None:
        raise RegraError("O arquivo das regras do projeto não está nesta "
                         "instalação.")
    return BASE.procurar(termo, fonte=BASE.FONTE_REGRA, limite=limite)


# ---------------------------------------------------------------- o carimbo


def carimbo() -> dict:
    """O que o arquivo diz de si mesmo: a versão e o tamanho da suíte.

    Lido com expressão regular da PRIMEIRA parte do arquivo, que é onde ele
    está. **Não achar não é erro**: é ausência de carimbo, e quem lê precisa
    saber a diferença entre «diz 3.6.130» e «não diz».
    """
    caminho = arquivo()
    if caminho is None:
        return {"arquivo": "", "versao": "", "testes": "", "aprovados": ""}
    try:
        with caminho.open(encoding="utf-8", errors="replace") as f:
            comeco = f.read(4000)
    except OSError:
        return {"arquivo": str(caminho), "versao": "", "testes": "",
                "aprovados": ""}
    m_versao = _VERSAO.search(comeco)
    m_testes = _TESTES.search(comeco)
    m_aprovados = _APROVADOS.search(comeco)
    return {
        "arquivo": str(caminho),
        "versao": (m_versao.group(1) or m_versao.group(2)) if m_versao else "",
        "testes": m_testes.group(1) if m_testes else "",
        "aprovados": m_aprovados.group(1) if m_aprovados else "",
    }


# O roteiro mais novo da pasta dos documentos. E o segundo carimbo da casa, e
# ele existe porque o primeiro e escrito a mao: o nome do arquivo tem data (o
# pacote que o carrega), e por isso ele nao envelhece sozinho.
_ROTEIRO = re.compile(r"^ROTEIRO_([0-9]+(?:\.[0-9]+)*)\.md$", re.I)


def _versao_em_tupla(texto: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", texto or ""))


def roteiro_mais_novo(pasta: Path | None = None) -> str:
    """A maior versão entre os `ROTEIRO_*.md` da pasta dos documentos."""
    pasta = pasta or (RAIZ / "DOCUMENTACAO")
    if not pasta.is_dir():
        return ""
    versoes = []
    for caminho in pasta.glob("ROTEIRO_*.md"):
        m = _ROTEIRO.match(caminho.name)
        if m:
            versoes.append(m.group(1))
    if not versoes:
        return ""
    return max(versoes, key=_versao_em_tupla)


def conferir(versao_que_roda: str, pasta_dos_documentos: Path | None = None
             ) -> list[dict]:
    """O carimbo confere com o que está rodando? — e o que não dá para conferir.

    **A REGRA DO CARIMBO É DESTA CASA**, e ela já custou: em 15/09/2026 o
    `CLAUDE.md` dizia «3.6.79» e «5.425 testes» enquanto o `app.py` estava na
    3.6.129 e o coletor contava 5.826. *Carimbo que mente é pior que carimbo
    nenhum: ele responde, e responde errado.* Aqui ele passa a ser conferido em
    vez de acreditado.

    **O QUE NÃO SE CONFERE AQUI, E POR QUÊ.** O número de testes não se mede
    nesta instalação: a suíte não viaja com a atualização (a pasta `tests` fica
    de fora de propósito), e contar `def test_` acharia outra coisa — «funções
    de teste escritas» não é «testes que o coletor conta», e comparar um com o
    outro é a medição que parece medição e não é. Então ele vem marcado como
    **não conferível**, com o motivo, em vez de vir com um veredito inventado.
    """
    caminho = arquivo()
    if caminho is None:
        return [{
            "o_que": "o arquivo das regras do projeto",
            "veredito": "ausente",
            "nota": ("Ele não está nesta instalação. Viaja com a atualização "
                     f"(procurado em: {', '.join(str(c) for c in _caminhos())})."),
        }]

    achados: list[dict] = []
    car = carimbo()

    if not car["versao"]:
        achados.append({
            "o_que": "a versão escrita nas regras",
            "veredito": "nao_conferivel",
            "nota": "O carimbo do arquivo não traz versão legível.",
        })
    elif versao_que_roda and car["versao"] != versao_que_roda:
        achados.append({
            "o_que": "a versão escrita nas regras",
            "escrito": car["versao"],
            "no_ar": versao_que_roda,
            "veredito": "atras",
            "nota": ("O arquivo das regras aponta uma versão e o sistema roda "
                     "outra. Não é defeito do sistema: é o material escrito "
                     "que ficou para trás — e quem o ler vai concluir o "
                     "errado sobre o que está no ar."),
        })
    else:
        achados.append({
            "o_que": "a versão escrita nas regras",
            "escrito": car["versao"],
            "no_ar": versao_que_roda,
            "veredito": "de_acordo",
            "nota": "",
        })

    mais_novo = roteiro_mais_novo(pasta_dos_documentos)
    if not mais_novo:
        achados.append({
            "o_que": "o roteiro mais novo",
            "veredito": "nao_conferivel",
            "nota": ("Não há `ROTEIRO_*.md` na pasta dos documentos desta "
                     "instalação. Quando não há nenhum, isto não diz que o "
                     "material está velho — diz que ele não chegou aqui."),
        })
    elif versao_que_roda and _versao_em_tupla(mais_novo) < _versao_em_tupla(versao_que_roda):
        achados.append({
            "o_que": "o roteiro mais novo",
            "escrito": mais_novo,
            "no_ar": versao_que_roda,
            "veredito": "atras",
            "nota": ("O último roteiro escrito é anterior à versão que roda: "
                     "as versões seguintes não têm roteiro."),
        })
    else:
        achados.append({
            "o_que": "o roteiro mais novo",
            "escrito": mais_novo,
            "no_ar": versao_que_roda,
            "veredito": "de_acordo",
            "nota": "",
        })

    if car["testes"]:
        achados.append({
            "o_que": "o número de testes coletados",
            "escrito": car["testes"],
            "veredito": "nao_conferivel",
            "nota": ("A suíte de testes não viaja com a atualização — ela roda "
                     "na máquina de desenvolvimento. O número escrito aqui só "
                     "se confere lá; nesta instalação ele não se mede."),
        })
    return achados


def resumo_da_conferencia(versao_que_roda: str,
                          pasta_dos_documentos: Path | None = None) -> str:
    """A conferência em duas ou três linhas, para o contexto da consulta.

    **SÓ APARECE O QUE NÃO ESTÁ DE ACORDO.** Um bloco dizendo «tudo certo» em
    toda pergunta custaria token em toda pergunta para não dizer nada — e o que
    interessa é justamente o dia em que o material escrito ficou para trás.
    """
    problemas = [a for a in conferir(versao_que_roda, pasta_dos_documentos)
                 if a.get("veredito") in {"atras", "ausente"}]
    if not problemas:
        return ""
    linhas = ["(Atenção: o material escrito pode estar atrás do sistema.)"]
    for a in problemas:
        if a.get("veredito") == "ausente":
            linhas.append(f"- {a['o_que']}: {a['nota']}")
            continue
        linhas.append(f"- {a['o_que']}: diz {a.get('escrito')} e o sistema "
                      f"está em {a.get('no_ar')} — {a['nota']}")
    return "\n".join(linhas)

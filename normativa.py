"""A base normativa, por artigo — o índice e a busca que devolvem a norma com a citação.

O PEDIDO DO OFICIAL, EM 05/11/2026
    Abastecer os agentes de IA com o código de normas estadual e o nacional e
    com as leis da atividade, e fazer a resposta CITAR O ARTIGO. Os textos moram
    em `base_normativa/`, um arquivo por norma (ver o README de lá).

POR QUE POR ARTIGO, E NÃO O ACERVO INTEIRO
    São 4,8 MB de texto. Mandá-los ao modelo em toda pergunta seria a lentidão
    de que o oficial já reclamou na ajuda, multiplicada. O índice parte cada
    norma em artigos UMA vez por processo, e cada pergunta leva só os artigos
    pertinentes, cada um com a citação: norma, artigo e o link da fonte.

O QUE ESTE MÓDULO NÃO FAZ
    Não fala com a rede e não escreve nada. Não decide nada: devolve o texto da
    norma e de onde ele saiu. Quem liga a busca a cada agente é outra etapa.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

import ajuda_base as BASE

RAIZ = Path(__file__).resolve().parent
PASTA = RAIZ / "base_normativa"

# QUANTOS ARTIGOS A BUSCA DEVOLVE, E QUANTO DE CADA UM. O modelo precisa do
# texto do artigo para citá-lo; o artigo inteiro do Código Civil cabe, e o do
# Código de Normas às vezes passa de dez mil caracteres. O corte aparece.
LIMITE_DA_BUSCA = 8
LIMITE_DO_TRECHO = 2_500

# O NOME CURTO DE CADA NORMA, COMO O BALCÃO E O MODELO A CHAMAM. A chave é o
# nome do arquivo sem extensão; o que não estiver aqui usa o título do arquivo.
# Os apelidos são o que se aceita ao pedir um artigo («art. 21 da LRP»).
NOMES: dict[str, tuple[str, tuple[str, ...]]] = {
    "codigo_de_normas_tjma": ("CN-MA (Prov. COGEX/TJMA 28/2026)",
                              ("cn-ma", "cnma", "codigo de normas", "tjma", "cogex")),
    "codigo_nacional_de_normas_cnj": ("CNN (Prov. CNJ 149/2023)",
                                      ("cnn", "codigo nacional", "cnj", "149/2023")),
    "lei-6015-1973-12-31": ("Lei 6.015/1973 (LRP)", ("lrp", "6015", "6.015", "registros publicos")),
    "lei-8935-1994-11-18": ("Lei 8.935/1994", ("8935", "8.935")),
    "lei-9492-1997-09-10": ("Lei 9.492/1997 (Protesto)", ("9492", "9.492", "lei do protesto")),
    "lei-7433-1985-12-18": ("Lei 7.433/1985", ("7433", "7.433")),
    "dec-93240-1986-09-09": ("Decreto 93.240/1986", ("93240", "93.240")),
    "lei-10169-2000-12-29": ("Lei 10.169/2000", ("10169", "10.169")),
    "lei-14382-2022-06-27": ("Lei 14.382/2022 (SERP)", ("14382", "14.382", "serp")),
    "lei-13465-2017-07-11": ("Lei 13.465/2017 (REURB)", ("13465", "13.465", "reurb")),
    "lei-9514-1997-11-20": ("Lei 9.514/1997", ("9514", "9.514", "alienacao fiduciaria")),
    "lei-6766-1979-12-19": ("Lei 6.766/1979", ("6766", "6.766", "parcelamento")),
    "lei-4591-1964-12-16": ("Lei 4.591/1964", ("4591", "4.591", "incorporacao")),
    "del-167-1967-02-14": ("Decreto-Lei 167/1967", ("dl 167", "167/1967", "credito rural")),
    "del-413-1969-01-09": ("Decreto-Lei 413/1969", ("dl 413", "413/1969", "credito industrial")),
    "lei-6840-1980-11-03": ("Lei 6.840/1980", ("6840", "6.840", "credito comercial")),
    "lei-10931-2004-08-02": ("Lei 10.931/2004", ("10931", "10.931")),
    "lei-8929-1994-08-22": ("Lei 8.929/1994 (CPR)", ("8929", "8.929", "cpr")),
    "lei-13986-2020-04-07": ("Lei 13.986/2020", ("13986", "13.986")),
    "lei-10406-2002-01-10": ("Código Civil (Lei 10.406/2002)", ("cc", "codigo civil", "10406", "10.406")),
    "lei-13105-2015-03-16": ("CPC (Lei 13.105/2015)", ("cpc", "codigo de processo civil", "13105", "13.105")),
    "lei-13709-2018-08-14": ("LGPD (Lei 13.709/2018)", ("lgpd", "13709", "13.709")),
    "lei-14711-2023-10-30": ("Lei 14.711/2023", ("14711", "14.711", "marco das garantias")),
    "lei-7357-1985-09-02": ("Lei 7.357/1985 (Cheque)", ("7357", "7.357", "lei do cheque")),
    "lei-5474-1968-07-18": ("Lei 5.474/1968 (Duplicatas)", ("5474", "5.474")),
    "lei-13775-2018-12-20": ("Lei 13.775/2018", ("13775", "13.775", "duplicata escritural")),
    "lei-11101-2005-02-09": ("Lei 11.101/2005 (Falência)", ("11101", "11.101", "falencia")),
    "lei-9265-1996-02-12": ("Lei 9.265/1996", ("9265", "9.265")),
    "lei-9534-1997-12-10": ("Lei 9.534/1997", ("9534", "9.534")),
    "lei-8560-1992-12-29": ("Lei 8.560/1992", ("8560", "8.560")),
    "lei-14063-2020-09-23": ("Lei 14.063/2020", ("14063", "14.063")),
    "mpv-2200-2-2001-08-24": ("MP 2.200-2/2001 (ICP-Brasil)", ("2200", "2.200", "icp")),
    "lei-13140-2015-06-26": ("Lei 13.140/2015 (Mediação)", ("13140", "13.140", "mediacao")),
    "lei-9109-2009": ("Lei estadual MA 9.109/2009 (Emolumentos)", ("9109", "9.109", "emolumentos")),
}

# O NÚMERO DO ARTIGO EM TODAS AS FORMAS QUE OS ARQUIVOS TRAZEM. Medido nos 35
# arquivos: «Art. 1º», «Art. 1.º», «Art. 12-A.», «Art. 1.020.», «Art**. 1º» e
# — nos arts. 1.000 a 1.012 do CN-MA — «**Art. 1.**000.», que a conversão do
# PDF negritou no lugar errado. Os asteriscos saem antes de ler o número.
_ARTIGO = re.compile(
    r"^Art\.?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:\s*\.?\s*[º°o])?(?:\s*-\s*([A-Z]{1,2}))?\b")
_CABECALHO = re.compile(r"^(#{1,6})\s+(.*)$")
_REVOGADO = re.compile(r"^\W*\(?\s*revogad[oa]", re.I)


class NormaError(ValueError):
    """Erro de regra deste módulo — mensagem pronta para quem lê a tela."""


def _numero(bruto: str, letra: str | None) -> str:
    """«1.020» vira «1020», «12» + «A» vira «12-A»: a forma com que se procura."""
    n = str(int(bruto.replace(".", "")))
    return f"{n}-{letra.upper()}" if letra else n


def _cabeca(texto: str) -> dict:
    """O cabeçalho YAML simples do ctresb/leis, ou a linha «> Fonte:» dos códigos."""
    dados: dict[str, str] = {}
    if texto.startswith("---"):
        fim = texto.find("\n---", 3)
        for linha in texto[3:fim].splitlines():
            if ":" in linha:
                chave, valor = linha.split(":", 1)
                dados[chave.strip()] = valor.strip().strip('"')
    if "fonte" not in dados:
        # «> Fonte: <link> (texto compilado…)» no CNN; no CN-MA a fonte é o
        # DJe, escrito por extenso e sem link — vai até o parêntese ou o ponto.
        achado = re.search(r"^>\s*Fonte:\s*(.+?)(?:\s+\(|\.\s|$)", texto, re.M)
        if achado:
            dados["fonte"] = achado.group(1).strip().rstrip(".")
    if "titulo" not in dados:
        achado = re.search(r"^#\s+(.+)$", texto, re.M)
        if achado:
            dados["titulo"] = achado.group(1).strip()
    return dados


def partir(texto: str) -> list[dict]:
    """Os artigos de uma norma, na ordem do arquivo. **Só calcula.**

    Cada artigo leva o número na forma de procura (`numero`), o rótulo como
    está escrito (`rotulo`), o texto sem a marcação de negrito, a seção onde
    está (o último título visto) e a linha do arquivo onde começa.
    """
    artigos: list[dict] = []
    secao = ""
    atual: dict | None = None
    for n, linha in enumerate(texto.splitlines(), 1):
        cab = _CABECALHO.match(linha)
        if cab:
            secao = cab.group(2).strip()
            if atual is not None:
                artigos.append(atual)
                atual = None
            continue
        limpa = linha.replace("*", "").strip()
        marca = _ARTIGO.match(limpa) if linha.lstrip().startswith("**Art") else None
        if marca:
            if atual is not None:
                artigos.append(atual)
            atual = {"numero": _numero(marca.group(1), marca.group(2)),
                     "rotulo": marca.group(0).strip(), "secao": secao,
                     "linha": n, "linhas": [limpa]}
            continue
        if atual is not None and limpa:
            atual["linhas"].append(limpa)
    if atual is not None:
        artigos.append(atual)
    for a in artigos:
        a["texto"] = "\n".join(a.pop("linhas"))
        corpo = a["texto"][len(a["rotulo"]):].lstrip(" .-–—")
        a["revogado"] = bool(_REVOGADO.match(corpo))
        a["norm"] = BASE.sem_acento(a["texto"])
    return artigos


# ------------------------------------------------------------------ o índice

_CADEADO = threading.Lock()
_INDICE: dict[str, Any] = {"assinatura": None, "normas": [], "conferida_em": 0.0}
INTERVALO_DA_CONFERENCIA = 2.0


def _arquivos() -> list[Path]:
    if not PASTA.is_dir():
        return []
    return sorted(c for c in PASTA.rglob("*.md") if c.name.lower() != "readme.md")


def _assinatura() -> tuple:
    marcas = []
    for c in _arquivos():
        try:
            s = c.stat()
        except OSError:
            continue
        marcas.append((str(c), s.st_size, s.st_mtime_ns))
    return tuple(marcas)


def _medir() -> list[dict]:
    normas = []
    for caminho in _arquivos():
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        cabeca = _cabeca(texto)
        chave = caminho.stem
        nome, apelidos = NOMES.get(chave, (cabeca.get("titulo", chave), ()))
        normas.append({
            "chave": chave, "nome": nome,
            "apelidos": tuple(BASE.sem_acento(a) for a in apelidos),
            "titulo": cabeca.get("titulo", nome),
            "fonte": cabeca.get("fonte", ""),
            "texto_de": cabeca.get("versao_texto", ""),
            "arquivo": caminho.relative_to(PASTA).as_posix(),
            "artigos": partir(texto),
        })
    return normas


def normas() -> list[dict]:
    """As normas indexadas, do cache quando nenhum arquivo mudou. **Escreve na memória.**

    Construída uma vez por processo; a assinatura dos arquivos se confere no
    máximo a cada `INTERVALO_DA_CONFERENCIA` segundos, como em `ajuda_base`.
    """
    with _CADEADO:
        agora = time.monotonic()
        if (_INDICE["normas"]
                and agora - float(_INDICE["conferida_em"]) < INTERVALO_DA_CONFERENCIA):
            return _INDICE["normas"]
        assinatura = _assinatura()
        _INDICE["conferida_em"] = agora
        if _INDICE["assinatura"] != assinatura or not _INDICE["normas"]:
            _INDICE.update({"assinatura": assinatura, "normas": _medir()})
        return _INDICE["normas"]


def norma(qual: str) -> dict:
    """A norma pelo nome curto, por um apelido («LRP», «CN-MA») ou pela chave do arquivo."""
    procurado = BASE.sem_acento(qual).strip()
    if not procurado:
        raise NormaError("Diga de que norma: por exemplo «LRP», «CN-MA» ou «Lei 9.492».")
    todas = normas()
    exatas = [n for n in todas
              if procurado in (BASE.sem_acento(n["chave"]), BASE.sem_acento(n["nome"]))
              or procurado in n["apelidos"]]
    if len(exatas) == 1:
        return exatas[0]
    soltas = [n for n in todas
              if any(a and a in procurado for a in n["apelidos"])
              or procurado in BASE.sem_acento(n["nome"])]
    if len(soltas) == 1:
        return soltas[0]
    if not soltas:
        raise NormaError(
            f"A base normativa não tem «{qual}». As normas que ela tem: "
            f"{', '.join(n['nome'] for n in todas)}.")
    raise NormaError(
        f"«{qual}» casa com mais de uma norma: "
        f"{', '.join(n['nome'] for n in soltas)}. Diga qual.")


def citacao(n: dict, artigo: dict) -> str:
    """«Lei 9.492/1997 (Protesto), art. 21 — fonte: <link>»."""
    fonte = f" — fonte: {n['fonte']}" if n["fonte"] else ""
    return f"{n['nome']}, art. {artigo['numero']}{fonte}"


def _cortar(texto: str) -> str:
    if len(texto) <= LIMITE_DO_TRECHO:
        return texto
    return (texto[:LIMITE_DO_TRECHO]
            + f" […] (o artigo continua; vieram {LIMITE_DO_TRECHO} de "
              f"{len(texto)} caracteres — peça o artigo inteiro)")


def artigo(qual_norma: str, numero: str, *, inteiro: bool = False) -> dict:
    """Um artigo pelo número, com a citação. Recusa com frase quando não há."""
    n = norma(qual_norma)
    marca = _ARTIGO.match("Art. " + str(numero or "").strip().replace("art.", "").strip())
    if not marca:
        raise NormaError(f"«{numero}» não é número de artigo. Exemplo: 21, 1.020, 12-A.")
    procurado = _numero(marca.group(1), marca.group(2))
    achados = [a for a in n["artigos"] if a["numero"] == procurado]
    if not achados:
        raise NormaError(f"{n['nome']} não tem art. {procurado} nesta base.")
    a = achados[0]
    return {"norma": n["nome"], "artigo": a["numero"], "secao": a["secao"],
            "citacao": citacao(n, a), "revogado": a["revogado"],
            "texto": a["texto"] if inteiro else _cortar(a["texto"])}


def buscar(termo: str, *, limite: int = LIMITE_DA_BUSCA,
           em: str = "", com_revogados: bool = False) -> list[dict]:
    """Os artigos mais pertinentes a um termo, com a citação. **Só lê.**

    A régua é a da base da ajuda (`ajuda_base._palavras` e
    `_minimo_de_palavras`): palavra de pergunta não conta, e de três palavras
    para cima basta metade delas no artigo. O artigo que traz a frase inteira
    ganha; depois, o que traz mais palavras; depois, o que as repete mais.
    Revogado não entra, a não ser que se peça.
    """
    procurado = BASE.sem_acento(termo).strip()
    if not procurado:
        raise NormaError("Diga o que procurar na base normativa.")
    palavras = BASE._palavras(procurado) or [procurado]
    minimo = BASE._minimo_de_palavras(palavras)
    alvo = [norma(em)] if em else normas()
    achados = []
    for n in alvo:
        for a in n["artigos"]:
            if a["revogado"] and not com_revogados:
                continue
            presentes = [p for p in palavras if p in a["norm"]]
            inteiro = len(palavras) > 1 and procurado in a["norm"]
            if not inteiro and len(presentes) < minimo:
                continue
            # AS PALAVRAS JUNTAS NO MESMO PARÁGRAFO VALEM MAIS. Sem isto, o
            # artigo que carrega uma tabela anexa inteira (o da vigência da lei
            # de emolumentos do MA) ganhava de todos só por ter as palavras
            # espalhadas por dezenas de páginas.
            juntas = max(sum(1 for p in presentes if p in linha)
                         for linha in a["norm"].split("\n"))
            pontos = ((1000 if inteiro else 0) + 10 * len(presentes)
                      + 8 * juntas
                      + min(sum(a["norm"].count(p) for p in presentes), 9))
            achados.append((pontos, n, a))
    achados.sort(key=lambda x: -x[0])
    return [{"norma": n["nome"], "artigo": a["numero"], "secao": a["secao"],
             "citacao": citacao(n, a), "pontos": p, "texto": _cortar(a["texto"])}
            for p, n, a in achados[:max(1, int(limite or 1))]]


def para_o_modelo(achados: list[dict], termo: str = "") -> str:
    """Os achados em texto, cada um com a citação na frente. Vazio diz que é vazio."""
    if not achados:
        return (f"A base normativa não tem artigo sobre «{termo}». Isso quer dizer "
                "que estas palavras não aparecem nas normas daqui — não que a norma "
                "não trate do assunto. Tente outras palavras ou peça o artigo pelo "
                "número.")
    partes = []
    for a in achados:
        partes.append(f"[{a['citacao']}]\n{a['texto']}")
    return "\n\n".join(partes)

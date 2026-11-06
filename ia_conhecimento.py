"""Conhecimento público comum aos transportes de IA, sem rede ou escrita.

A biblioteca fica disponível por artigo. Cada análise recebe somente fontes
relacionadas ao assunto; transcrição e OCR preservam o documento original.
"""
from __future__ import annotations

import hashlib
import re

import normativa as N

MARCA = "=== FONTES NORMATIVAS DA SERVENTIA ==="
LIMITE_DE_CONTEXTO = 12_000
NUCLEO = ("codigo_de_normas_tjma", "codigo_nacional_de_normas_cnj",
          "lei-6015-1973-12-31", "lei-8935-1994-11-18")
SEM_ANALISE_JURIDICA = frozenset({"rc_leitura", "nt_leitura", "revisao_anexos",
                                 "wa_transcricao"})
TEMAS = (
    (r"hipotec|baixa de gravame", "cancelamento de hipoteca"),
    (r"c[eé]dula|\bccb\b|cr[eé]dito banc", "cédula de crédito bancário"),
    (r"cr[eé]dito rural|c[eé]dula rural", "cédula crédito rural"),
    (r"cr[eé]dito industrial", "cédula crédito industrial"),
    (r"\bcpr\b|produto rural", "cédula produto rural"),
    (r"reurb|legitima[cç][aã]o fundi", "regularização fundiária"),
    (r"incra|concess[aã]o de uso|reforma agr[aá]ria", "reforma agrária beneficiários"),
    (r"georreferenc|sigef|ccir", "georreferenciamento imóvel rural"),
    (r"usucapi", "usucapião extrajudicial"),
    (r"fiduci[aá]ri", "alienação fiduciária"),
    (r"compra|venda|transmiss[aã]o", "compra e venda"),
    (r"invent[aá]rio|partilha", "inventário partilha"),
    (r"procura[cç][aã]o|mandato", "procuração poderes"),
    (r"protest", "protesto título"),
    (r"nasciment|paternidade|filia[cç][aã]o", "registro nascimento filiação"),
    (r"casamento|habilita[cç][aã]o", "habilitação casamento"),
    (r"[oó]bito|faleciment", "registro óbito"),
    (r"retifica[cç][aã]o", "retificação registro"),
    (r"emolument|gratuidade|isen[cç][aã]o", "emolumentos gratuidade"),
    (r"devolutiva|exig[eê]ncia|qualifica[cç][aã]o", "nota devolutiva exigências"),
    (r"associa[cç][aã]o|pessoa jur[ií]dica", "registro pessoa jurídica"),
    (r"prote[cç][aã]o de dados|lgpd", "proteção dados pessoais"),
)


def situacao() -> dict:
    normas = N.normas()
    por_chave = {n["chave"]: n for n in normas}
    faltam = [c for c in NUCLEO if not por_chave.get(c, {}).get("artigos")]
    return {"pronta": not faltam, "faltam": faltam, "normas": len(normas),
            "artigos": sum(len(n["artigos"]) for n in normas),
            "escopo": "acervo instalado; não equivale a toda a legislação brasileira",
            "versao": hashlib.sha256(repr(N._assinatura()).encode()).hexdigest()[:16]}


def selecionar(assunto: str, *, limite: int = 8) -> list[dict]:
    """Busca em TODAS as normas: leis especiais não somem por ser análise do RI."""
    texto = re.sub(r"<[^>]+>", " ", str(assunto or ""))[:40_000]
    termos = [t for padrao, t in TEMAS if re.search(padrao, texto, re.I)]
    if not termos:
        palavras = N.BASE._palavras(N.BASE.sem_acento(texto[:1200]))
        termos = [" ".join(palavras[:6])] if palavras else []
    unicos = {}
    for termo in termos[:6]:
        for a in N.buscar(termo, limite=6):
            k = (a["norma"], a["artigo"])
            if k not in unicos or a["pontos"] > unicos[k]["pontos"]:
                unicos[k] = a
    ordenados = sorted(unicos.values(), key=lambda a: -a["pontos"])
    # Diversidade de fonte antes de repetir a mesma lei oito vezes.
    primeiros, outros, vistas = [], [], set()
    for a in ordenados:
        (outros if a["norma"] in vistas else primeiros).append(a)
        vistas.add(a["norma"])
    return (primeiros + outros)[:limite]


def contexto(assunto: str) -> str:
    estado = situacao()
    if not estado["normas"]:
        return ""
    partes = [MARCA,
              f"Acervo disponível: {estado['normas']} normas, {estado['artigos']} artigos.",
              "Consulte os dispositivos, a fonte e a redação aplicável à data do ato. "
              "Texto original pode ter sido alterado: confira a versão compilada e a fonte oficial. "
              "Ausência de resultado não prova ausência de regra. Não invente fundamento, "
              "não transfira exigência de outro caso e separe dúvida de impedimento. "
              "Se faltar fonte ou documento, diga o que precisa ser conferido."]
    tamanho = sum(map(len, partes))
    for a in selecionar(assunto):
        bloco = f"[{a['citacao']}]\n{a['texto']}"
        if tamanho + len(bloco) + 2 > LIMITE_DE_CONTEXTO:
            continue
        partes.append(bloco)
        tamanho += len(bloco) + 2
    if len(partes) == 3:
        partes.append("Não foi recuperado dispositivo para este assunto; "
                      "a resposta jurídica exige consulta específica às fontes.")
    return "\n\n".join(partes)


def enriquecer(sistema: str, conversa: list[dict], *, finalidade: str = "",
               atribuicao: str = "") -> str:
    """Uma passagem comum; ferramentas de consulta podem buscar artigos adicionais."""
    if finalidade in SEM_ANALISE_JURIDICA or MARCA in sistema:
        return sistema
    texto = "\n".join(str(x.get("texto") or "") for x in conversa
                      if x.get("tipo") == "user")
    if MARCA in texto or "=== A NORMA PERTINENTE" in texto:
        return sistema
    bloco = contexto(f"{atribuicao}\n{texto}")
    return sistema + ("\n\n" + bloco if bloco else "")


def conferir_referencia(referencia: dict) -> dict:
    """Confere existência e transcrição literal; pertinência jurídica é humana."""
    try:
        qual = str(referencia.get("norma") or "")
        norma = N.norma(qual)
        a = N.artigo(qual,
                     str(referencia.get("artigo") or ""), inteiro=True)
    except N.NormaError:
        return {"conferida": False, "motivo": "norma ou artigo ausente do acervo"}
    if "original" in str(norma.get("texto_de") or "").casefold():
        return {"conferida": False, "motivo": "texto original: conferir alterações na fonte oficial",
                "citacao": a["citacao"]}
    trecho = " ".join(str(referencia.get("trecho") or "").split()).casefold()
    escrito = " ".join(a["texto"].split()).casefold()
    if a["revogado"] or len(trecho) < 20 or trecho not in escrito:
        return {"conferida": False, "motivo": "redação revogada ou trecho não conferido"}
    return {"conferida": True, "citacao": a["citacao"], "trecho": referencia["trecho"]}

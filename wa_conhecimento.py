"""O que o atendente do WhatsApp lê antes de responder.

Decisão do oficial em 10/11/2026: a conversa precisa conhecer o que o sistema
faz, o que o cartório faz, como o escrevente faz, e a norma da atividade. Isso
já está na casa — a base da ajuda (documentos e regras) e a base normativa —
e não se copia para um texto solto.

Cada pergunta leva três blocos, com teto de tamanho:
- o ofício, sempre (`wa_oficio`), sem número de lei;
- as linhas da base da ajuda que falam do que a pessoa perguntou;
- os artigos da base normativa pertinentes à pergunta.

Número que a resposta escrever tem de estar no texto-base da casa ou nestes
blocos. O texto é público e ainda passa pela máscara: um nome ou documento que
tenha escapado para um verbete não sobe inteiro.
"""
from __future__ import annotations

import logging

import ajuda_privacidade as PRIV
import wa_oficio as OFICIO

LOG = logging.getLogger("cartorio.wa_conhecimento")

LINHAS_DA_BASE = 8
ARTIGOS = 4
TETO_DA_BASE = 4_000
TETO = 12_000


def _da_base(termo: str) -> str:
    """As linhas da ajuda e das regras. Vazio se nada casa ou se a base falhar."""
    import ajuda_base as BASE
    try:
        achado = BASE.buscar(termo, limite=LINHAS_DA_BASE)
    except Exception:                               # noqa: BLE001
        LOG.exception("a base da ajuda não entrou no atendimento")
        return ""
    if not achado.get("achados"):
        return ""
    linhas = []
    for a in achado["achados"]:
        onde = a.get("titulo_da_fonte") or a.get("origem") or "base"
        secao = a.get("secao") or ""
        linhas.append(f"[{onde} — {secao}] {a.get('texto') or ''}")
    texto = "=== O QUE O SISTEMA E AS REGRAS DA CASA DIZEM ===\n" + "\n".join(linhas)
    if len(texto) > TETO_DA_BASE:
        texto = texto[:TETO_DA_BASE] + "\n[…]"
    return texto


def _da_norma(termo: str, setor: str) -> str:
    """Os artigos pertinentes. Vazio se a base normativa não achar ou falhar."""
    import normativa as NORMA
    atribuicao = {"RI": "RI", "NOTAS": "NOTAS"}.get(str(setor or "").upper(), "")
    try:
        return NORMA.trechos_para_o_pedido(termo, atribuicao=atribuicao, limite=ARTIGOS)
    except Exception:                               # noqa: BLE001
        LOG.exception("a base normativa não entrou no atendimento")
        return ""


def para_o_atendimento(termo: str, *, setor: str = "") -> str:
    """O bloco que vai na instrução desta pergunta. Só lê. Não fala com a rede.

    O termo é o que o cliente escreveu, já sem dado pessoal — quem chama é o
    atendente, depois da máscara recusar a mensagem. O bloco não repete o termo.
    """
    partes = [OFICIO.texto_do_oficio()]
    procurado = " ".join(str(termo or "").split())[:400]
    if procurado:
        base = _da_base(procurado)
        if base:
            partes.append(base)
        norma = _da_norma(procurado, setor)
        if norma:
            partes.append(norma)
    texto = "\n\n".join(partes)
    if len(texto) > TETO:
        texto = texto[:TETO] + "\n[…]"
    return PRIV.sanitizar_para_modelo(texto, nomes_livres=False, texto_publico=True)


def panorama() -> dict:
    """Os números que a tela do atendente mostra. Não derruba a página."""
    linhas = origens = 0
    base_pronta = False
    try:
        import ajuda_base as BASE
        BASE.carregar()
        r = BASE.resumo()
        base_pronta = bool(r.get("pronta"))
        linhas = int(r.get("total_de_linhas") or 0)
        origens = int(r.get("total_de_origens") or 0)
    except Exception:                               # noqa: BLE001
        LOG.exception("o panorama da base da ajuda falhou")
    normas = artigos = 0
    try:
        import normativa as NORMA
        lista = NORMA.normas()
        normas = len(lista)
        artigos = sum(len(n.get("artigos") or []) for n in lista)
    except Exception:                               # noqa: BLE001
        LOG.exception("o panorama da base normativa falhou")
    return {
        "base_pronta": base_pronta,
        "linhas": linhas,
        "origens": origens,
        "normas": normas,
        "artigos": artigos,
        "servicos": len(OFICIO.SERVICOS),
    }

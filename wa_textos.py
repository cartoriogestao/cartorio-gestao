"""Textos da casa para o rascunho do WhatsApp.

Fatia 1: classificador + rascunho por regras. Sem API paga de modelo.
Autoenvio desligado: isto so monta texto para o escrevente conferir.

NUNCA entra no rascunho: CPF, valor, protesto concreto, certidao, instrumento
ou dado de livro. Assuntos livres no futuro: horario, endereco, lista de
documentos — e mesmo esses, o horario de expediente NAO se inventa.
"""
from __future__ import annotations

from typing import Any

# Telefone e e-mail padrao desta serventia (papel timbrado / serventia.PADRAO).
# Vazias desde 09/10/2026 (sanitização): o valor vem de `settings`.
TELEFONE_PADRAO = ""
EMAIL_PADRAO = ""
CIDADE_PADRAO = ""
NOME_PADRAO = ""

# Sem horario medido no sistema: o texto manda confirmar. Nao inventar hora.
HORARIO_PLACEHOLDER = "confirmar horario de balcao"

ASSUNTO_LIVRE = frozenset({"horario", "endereco", "documentos"})
ASSUNTO_SENSIVEL = frozenset({"certidao", "firma", "protesto"})


def _s(serventia: Any, chave: str, padrao: str) -> str:
    if not serventia:
        return padrao
    v = serventia.get(chave) if hasattr(serventia, "get") else None
    v = ("" if v is None else str(v)).strip()
    return v or padrao


def bloco_contato(serventia: Any = None) -> str:
    tel = _s(serventia, "serventia_telefone", TELEFONE_PADRAO)
    email = _s(serventia, "serventia_email", EMAIL_PADRAO)
    nome = _s(serventia, "unit_name", NOME_PADRAO)
    cidade = _s(serventia, "cidade_uf", CIDADE_PADRAO)
    if cidade == CIDADE_PADRAO:
        cid = _s(serventia, "ri_cidade", "")
        uf = _s(serventia, "ri_uf", "MA")
        cidade = f"{cid}/{uf}"
    return (
        f"{nome}, Oficio unico de {cidade}. "
        f"Telefone {tel}. E-mail {email}."
    )


def endereco_da_casa(serventia: Any = None) -> str:
    end = _s(serventia, "serventia_endereco", "")
    cep = _s(serventia, "serventia_cep", "")
    cid = _s(serventia, "ri_cidade", "")
    uf = _s(serventia, "ri_uf", "MA")
    completo = (serventia or {}).get("endereco_completo") if serventia else None
    if completo and str(completo).strip():
        return str(completo).strip()
    return f"{end}, CEP {cep}, {cid}-{uf}"


def rascunho_horario(serventia: Any = None) -> str:
    return (
        "Bom dia. Sobre o expediente: por favor "
        f"{HORARIO_PLACEHOLDER} no balcao ou pelo telefone. "
        f"{bloco_contato(serventia)}"
    )


def rascunho_endereco(serventia: Any = None) -> str:
    return (
        f"Estamos em {endereco_da_casa(serventia)}. "
        f"{bloco_contato(serventia)}"
    )


def rascunho_documentos(serventia: Any = None) -> str:
    return (
        "Para dizer exatamente quais documentos levar, precisamos saber o ato "
        "(certidao, firma, escritura, protesto). Compareca ao balcao ou ligue "
        "para orientarmos. Nao enviamos lista completa automaticamente. "
        f"{bloco_contato(serventia)}"
    )


def rascunho_certidao(serventia: Any = None) -> str:
    return (
        "Pedido de certidao se resolve no balcao, com documento de "
        "identificacao. Nao enviamos pelo WhatsApp dado de livro, CPF, "
        "instrumento nem o teor da certidao. "
        f"{bloco_contato(serventia)}"
    )


def rascunho_firma(serventia: Any = None) -> str:
    return (
        "Reconhecimento de firma e abertura de ficha se fazem no balcao, "
        "com a pessoa presente. Nao enviamos dado de cadastro nem instrumento "
        "pelo WhatsApp. "
        f"{bloco_contato(serventia)}"
    )


def rascunho_protesto(serventia: Any = None) -> str:
    return (
        "Assunto de protesto se trata no balcao. Nao enviamos pelo WhatsApp "
        "valor, titulo, CPF nem informacao de protesto. "
        f"{bloco_contato(serventia)}"
    )


def rascunho_outros(serventia: Any = None) -> str:
    return (
        "Recebemos sua mensagem. Um escrevente vai responder por aqui. "
        "Para urgencia, ligue. "
        f"{bloco_contato(serventia)}"
    )


POR_ETIQUETA = {
    "horario": rascunho_horario,
    "endereco": rascunho_endereco,
    "documentos": rascunho_documentos,
    "certidao": rascunho_certidao,
    "firma": rascunho_firma,
    "protesto": rascunho_protesto,
    "outros": rascunho_outros,
}

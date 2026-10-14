"""Famílias dos instrumentos públicos do Tabelionato de Notas.

Escritura e ata notarial não são duas implementações do mesmo trabalho. Elas
usam o mesmo motor de ato (partes, modelo, teor, livro, selo, traslado,
assinatura e arquivos) e diferem apenas na seleção de tipos, modelos e nas
obrigações próprias de cada instrumento. Esta tabela é a ligação explícita:
uma melhoria no fluxo comum chega às duas famílias sem cópia de código.
"""

from __future__ import annotations

FAMILIAS = {
    "escrituras": {
        "chave": "escrituras",
        "titulo": "Escrituras públicas",
        "singular": "Escritura pública",
        "descricao": (
            "Lavratura, qualificação das partes, teor, livro, selo, traslado, "
            "PDF assinado, DOI e remessa à CENSEC no mesmo fluxo."
        ),
        "tipos_ato": ("ESCRITURA",),
        "tipos_modelo": ("ESCRITURA",),
        "tipo_principal": "ESCRITURA",
        "livro": "ESCRITURA",
        "endpoint": "notas_escrituras",
    },
    "atas": {
        "chave": "atas",
        "titulo": "Atas notariais",
        "singular": "Ata notarial",
        "descricao": (
            "Constatação, evidências, qualificação, teor, livro, selo, traslado "
            "e PDF assinado usando o mesmo motor avançado das escrituras."
        ),
        "tipos_ato": ("ATA", "ATA_USUCAPIAO"),
        "tipos_modelo": ("ATA_NOTARIAL", "ATA_USUCAPIAO"),
        "tipo_principal": "ATA",
        "livro": "ATA",
        "endpoint": "notas_atas",
    },
}


# O tipo do modelo determina o tipo do ato. Sem esta régua, era possível
# escolher o modelo de ata e gravar o ato como escritura (ou o inverso),
# fazendo-o cair no livro e na central errados.
TIPO_ATO_DO_MODELO = {
    "ESCRITURA": "ESCRITURA",
    "ATA_NOTARIAL": "ATA",
    "ATA_USUCAPIAO": "ATA_USUCAPIAO",
    "PROCURACAO": "PROCURACAO",
    "PROCURACAO_PREVIDENCIARIA": "PROCURACAO_PREVIDENCIARIA",
    "SUBSTABELECIMENTO": "SUBSTABELECIMENTO",
    "REVOGACAO_PROCURACAO": "REVOGACAO",
    "RENUNCIA_PROCURACAO": "RENUNCIA",
    "TESTAMENTO": "TESTAMENTO",
    "TESTAMENTO_CERRADO": "TESTAMENTO_CERRADO",
}


def por_chave(chave: str | None) -> dict | None:
    return FAMILIAS.get((chave or "").strip().lower())


def do_tipo_ato(tipo: str | None) -> dict | None:
    tipo = (tipo or "").upper()
    return next((f for f in FAMILIAS.values() if tipo in f["tipos_ato"]), None)


def tipo_ato_do_modelo(tipo_modelo: str | None) -> str | None:
    return TIPO_ATO_DO_MODELO.get((tipo_modelo or "").upper())


def aceita_modelo(familia: dict, tipo_modelo: str | None) -> bool:
    return (tipo_modelo or "").upper() in familia["tipos_modelo"]

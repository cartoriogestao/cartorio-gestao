"""Dados de ensaio para prévia e conferência dos modelos do Livro 3.

São os mesmos claros que `ra_ficha_odt.contexto` e `atrib_certidao` montam na
emissão — só que com um registro hipotético legível, para a pessoa enxergar a
forma enquanto edita, sem escolher um ato real.
"""
from __future__ import annotations

import ra_ficha_odt as FICHA

CHAVES_LIVRO3 = ("RI_LIVRO3_FICHA", "RI_LIVRO3_CERTIDAO")

_REGISTRO = {
    "numero": "1243",
    "folha": "042",
    "livro": "3-AUX",
    "situacao": "ATIVO",
    "natureza": "HIPOTECA",
    "titulo_tipo": "CÉDULA DE CRÉDITO RURAL",
    "titulo_numero": "2026/001",
    "data_titulo": "15/08/2026",
    "valor_centavos": 15000000,
    "parcelas": "12",
    "vencimento_inicial": "15/09/2026",
    "vencimento_final": "15/08/2027",
    "juros": "1,2% a.m.",
    "prenotacao": "12.345",
    "cnm": "000000 03 55 2026 1 00001 243 0001243 45",
    "teor": (
        "Cédula de crédito rural hipotecária, emitida por JOÃO DE EXEMPLO, "
        "com garantia real sobre imóvel rural situado em Cidade Exemplo/MA."
    ),
    "garantia": "Hipoteca de primeiro grau sobre o imóvel descrito no título.",
    "condicoes": "Vencimento antecipado na hipótese de mora superior a 30 dias.",
}

_PARTES = [
    {
        "nome": "BANCO DO BRASIL S/A",
        "papel": "credor",
        "documento_numero": "00.000.010/0001-27",
    },
    {
        "nome": "JOÃO DE EXEMPLO",
        "papel": "devedor",
        "documento_numero": "000.000.000-00",
    },
]

_ATOS = [
    {
        "tipo": "R",
        "numero": "1",
        "data_ato": "15/08/2026",
        "selo": "SELO000000EX124301",
        "teor": "Registro da cédula de crédito rural hipotecária.",
    },
    {
        "tipo": "AV",
        "numero": "1",
        "data_ato": "22/09/2026",
        "selo": "SELO000000EX124302",
        "teor": (
            "Averbação de cancelamento integral da cédula, por quitação "
            "comprovada."
        ),
    },
]

_SERVENTIA = {
    "ri_cidade": "Cidade Exemplo",
    "ri_uf": "MA",
    "cidade": "Cidade Exemplo",
    "uf": "MA",
}


def claros_ficha() -> dict:
    return FICHA.contexto(
        registro=_REGISTRO,
        atos=_ATOS,
        partes=_PARTES,
        serventia=_SERVENTIA,
        impresso_em="26 de setembro de 2026",
    )


def claros_certidao() -> dict:
    """Claros do `MODELO_CERTIDAO_LIVRO3` — alinhados à emissão real."""
    import atrib_certidao as AC

    return AC.claros_certidao_livro3(
        reg=_REGISTRO,
        atos=_ATOS,
        teor=str(_REGISTRO["teor"]),
        partes=_PARTES,
    )


def claros_de(chave: str) -> dict:
    alvo = (chave or "").strip().upper()
    if alvo == "RI_LIVRO3_FICHA":
        return claros_ficha()
    if alvo == "RI_LIVRO3_CERTIDAO":
        return claros_certidao()
    raise KeyError(alvo)

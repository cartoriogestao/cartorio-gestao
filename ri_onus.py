"""Quais atos da matricula entram na certidao de onus.

O DEFEITO QUE ISTO CONSERTA — revisao RI de 24/09/2026 (P1). `contexto_ficha`
so olhava `tipo == "AV"`: hipoteca (Lei 6.015, art. 167, I, 2), servidao
(I, 6), usufruto (I, 7), alienacao fiduciaria (I, 35), compromisso de compra e
venda, cedulas e citacoes de acoes reais sao lavrados como REGISTRO, e ficavam
de fora. A certidao podia dizer «NADA CONSTA» sobre imovel gravado.

A REGRA, NESTA ORDEM
    1. ato cancelado nao entra (o cancelamento ja e averbacao propria);
    2. natureza estruturada (`ri_naturezas`, codigo SAUIN) decide primeiro:
       se e onus, entra; qualquer outra natureza reconhecida (compra e venda,
       cancelamento, construcao...) nao entra;
    3. sem natureza reconhecida, palavra-chave — e o ato sai marcado para
       conferencia humana (`conferir=True`).

A PALAVRA-CHAVE DO REGISTRO OLHA SO O TITULO DO ATO. O teor de uma compra e
venda diz «livre e desembaracado de quaisquer onus, hipotecas...»: procurar
no teor inteiro poria toda transmissao na certidao de onus. O R da casa comeca
por «R-3/1.234 - HIPOTECA...», e e a primeira frase depois do rotulo que
nomeia o ato. A averbacao
mantem a busca larga que ja tinha — melhor apontar um ato a mais para
conferencia do que emitir «nada consta» sobre imovel gravado.
"""
from __future__ import annotations

import re
import unicodedata

from ri_naturezas import NATUREZAS, POR_NOME

# Codigos SAUIN que constituem onus, gravame, restricao ou constricao sobre o
# imovel (Lei 6.015, art. 167, I e II; Lei 13.097/2015, art. 54; TJMA 558).
CODIGOS_DE_ONUS: frozenset[int] = frozenset({
    0,    # Bem de Familia
    1,    # Hipoteca
    2,    # Alienacao Fiduciaria
    3,    # Penhor
    4,    # Penhora
    5,    # Arresto
    6,    # Sequestro
    7,    # Servidao
    8,    # Usufruto
    9,    # Contrato de Locacao (vigencia/preferencia)
    10,   # Rendas sobre imoveis
    11,   # Compromisso de Compra e Venda
    12,   # Cessao de Promessa de Compra e Venda
    13,   # Enfiteuse
    14,   # Anticrese
    16, 17, 18, 19, 20,  # Cedulas de credito (rural, industrial, bancaria...)
    21,   # Contratos de Penhor Rural
    22,   # Debentures
    30,   # Citacoes de Acoes Reais ou Pessoais Reipersecutorias
    42,   # Imissao Provisoria na Posse
    44,   # Direito de Superficie
    45,   # Concessao de Direito Real de Uso
    53,   # Doacao do Usufruto
    72,   # Patrimonio de Afetacao
    75, 76, 77,  # Clausulas de impenhorabilidade/inalienabilidade/incomunic.
    95, 96,      # Caucao / caucao locaticia
    97,   # Cessao Fiduciaria
    99,   # Fideicomisso
    100,  # Premonitoria
    101,  # Ajuizamento de Execucao
    103,  # Rerratificacao de mutuo com pacto adjeto de hipoteca
    104,  # Averbacao do Contrato de Locacao
    115,  # Indisponibilidade de Bens
    117,  # Bloqueio de Imovel
    118,  # Mora
    123,  # Arrolamento de Bens
    125,  # Interdicao
})

# «Outro» e «Nao se aplica» nao dizem nada: caem na palavra-chave.
CODIGOS_SEM_SENTIDO: frozenset[int] = frozenset({126, 127})

# Termos sem acento e em maiusculas — o texto e normalizado antes.
_TERMOS_COMUNS = (
    "HIPOTEC", "PENHOR", "PENHORA", "ARREST", "SEQUESTR", "INDISPON",
    "USUFRUT", "FIDUCI", "SERVIDA", "ANTICRESE", "ENFITEUSE", "CEDULA",
    "BEM DE FAMILIA", "ARROLAMENTO", "CITACAO", "PREMONIT",
    "AJUIZAMENTO DE EXECUCAO", "BLOQUEIO", "CAUCAO", "FIDEICOMISSO",
    "COMPROMISSO DE COMPRA", "PROMESSA DE COMPRA", "SUPERFICIE",
    "INALIENAB", "IMPENHORAB", "INCOMUNICAB", "LOCACAO",
)

# Termos largos que so valem na averbacao: no registro aparecem em quase toda
# transmissao («livre de onus», «alienante», «clausula»).
_TERMOS_SO_DA_AVERBACAO = (
    "ALIENA", "ONUS", "SERVID", "RESERVA", "CLAUSUL", "GRAVAM", "RESOLUTIV",
)

_ROTULO = re.compile(r"^\s*(?:R|AV)\s*[-.]?\s*\d+\s*(?:/\s*[\d.]+)?\s*[-–—:]*\s*",
                     re.I)
_JANELA_DA_AVERBACAO = 4000


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn").upper()


def _titulo_do_registro(teor: str) -> str:
    """«R-3/1.234 - HIPOTECA DE 1º GRAU. O imovel...» -> «HIPOTECA DE 1º GRAU»."""
    texto = re.sub(r"<[^>]+>", " ", teor or "")[:600]
    texto = _ROTULO.sub("", texto, count=1)
    return re.split(r"[.:;\n]", texto, maxsplit=1)[0][:160]


def _campo(ato, chave):
    try:
        return ato[chave]
    except (KeyError, IndexError):
        return None


def codigo_da_natureza(natureza_titulo) -> int | None:
    """Codigo SAUIN pelo nome gravado no ato; None se nao reconhecido."""
    nome = (natureza_titulo or "").strip().lower()
    if not nome:
        return None
    item = POR_NOME.get(nome)
    if item:
        return item[0]
    alvo = _sem_acento(nome)
    for c, _t, n, _op in NATUREZAS:
        if _sem_acento(n) == alvo:
            return c
    return None


def classificar(ato) -> dict | None:
    """Devolve `{"criterio", "conferir"}` quando o ato e onus vigente."""
    if _campo(ato, "cancelado"):
        return None
    codigo = codigo_da_natureza(_campo(ato, "natureza_titulo"))
    if codigo is not None and codigo not in CODIGOS_SEM_SENTIDO:
        if codigo in CODIGOS_DE_ONUS:
            return {"criterio": "natureza", "conferir": False}
        return None

    tipo = (_campo(ato, "tipo") or "").upper()
    natureza = _campo(ato, "natureza_titulo") or ""
    teor = _campo(ato, "teor") or ""
    if tipo == "R":
        alvo = _sem_acento(natureza + " " + _titulo_do_registro(teor))
        termos = _TERMOS_COMUNS
    else:
        alvo = _sem_acento(natureza + " " + teor[:_JANELA_DA_AVERBACAO])
        termos = _TERMOS_COMUNS + _TERMOS_SO_DA_AVERBACAO
    if any(t in alvo for t in termos):
        return {"criterio": "palavra-chave", "conferir": True}
    return None


def onus_vigentes(atos, rotulo=None) -> list[dict]:
    """Os atos (R e AV) que a certidao de onus tem de listar.

    `rotulo(ato)` opcional monta o rotulo impresso («R-03/1.234»).
    """
    saida = []
    for a in atos:
        achado = classificar(a)
        if not achado:
            continue
        linha = dict(a) | achado
        if rotulo is not None:
            linha["rotulo"] = rotulo(a)
        saida.append(linha)
    return saida

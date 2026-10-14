"""Quais atos entram na certidao dominial / cadeia dominial e na vintenaria.

A cadeia dominial lista as transmissaoes de dominio (compra e venda, doacao,
partilha, usucapiao, etc.). A vintenaria (e variantes por anos) restringe
essa janela temporal e, nesta casa, inclui tambem os onus vigentes no periodo
— pratica usual da certidao "dominial vintenaria" do acervo E-Oficio
(modelos 6/9/10) e alinhada ao item 16.24.4 da tabela TJMA, que nomeia
inteiro teor, onus e cadeia dominial no mesmo codigo.

NAO inventa natureza: usa os codigos SAUIN de `ri_naturezas` e, sem natureza
reconhecida, palavra-chave no titulo do registro (mesma familia de `ri_onus`).

Origem / cadeia de matriculas antecedentes (28/09/2026, Beatriz):
  o campo `registro_anterior` da ficha guarda o texto livre da abertura
  (desmembramento, unificacao, remissao a matricula-mae). Esta unidade
  extrai numeros citados nesse texto; so entram no papel as matriculas
  que existem no banco — nunca inventa origem.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from ri_naturezas import NATUREZAS, POR_NOME
from ri_onus import onus_vigentes, _titulo_do_registro, _campo

# Transmissoes de dominio / aquisicao (Lei 6.015 art. 167, I — registros
# que transferem ou constituem propriedade). Codigos SAUIN medidos na tabela
# local `ri_naturezas`.
CODIGOS_DE_DOMINIO: frozenset[int] = frozenset({
    31,   # Carta de Arrematacao
    32,   # Formal de Partilha
    33,   # Carta de Adjudicacao
    34,   # Sentencas Declaratorias de Usucapiao
    35,   # Usucapiao Extrajudicial
    36,   # Compra e Venda
    37,   # Permuta
    38,   # Dacao em Pagamento
    39,   # Transferencia de Imovel a Sociedade
    40,   # Doacao
    41,   # Desapropriacao
    46,   # Legitimacao de Posse
    47,   # Conversao de Legitimacao de Posse em Propriedade
    48,   # Titulo Definitivo
    49,   # Cisao
    50,   # Formal de Separacao
    51,   # Divorcio Judicial
    52,   # Divorcio Extrajudicial
    119,  # Consolidacao da Propriedade Fiduciaria (AV)
})

CODIGOS_SEM_SENTIDO: frozenset[int] = frozenset({126, 127})

_TERMOS_DOMINIO = (
    "COMPRA E VENDA", "COMPRA-E-VENDA", "PERMUTA", "DOACAO", "DOAÇÃO",
    "DACAO", "DAÇÃO", "ARREMATACAO", "ARREMATAÇÃO", "ADJUDICACAO",
    "ADJUDICAÇÃO", "USUCAPIAO", "USUCAPIÃO", "PARTILHA", "DESAPROPRIACAO",
    "DESAPROPRIAÇÃO", "TITULO DEFINITIVO", "TÍTULO DEFINITIVO",
    "TRANSFERENCIA DE IMOVEL", "TRANSFERÊNCIA DE IMÓVEL",
    "CONSOLIDACAO DA PROPRIEDADE", "CONSOLIDAÇÃO DA PROPRIEDADE",
    "LEGITIMACAO DE POSSE", "LEGITIMAÇÃO DE POSSE",
    "FORMAL DE SEPARACAO", "FORMAL DE SEPARAÇÃO", "DIVORCIO", "DIVÓRCIO",
    "CISAO", "CISÃO",
)

_ROTULO = re.compile(
    r"^\s*(?:R|AV)\s*[-.]?\s*\d+\s*(?:/\s*[\d.]+)?\s*[-–—:]*\s*", re.I)

# "Matricula 3236", "Matrícula nº 3.356", "Matriculas 2557, ..."
_RE_MAT_NO_ANTERIOR = re.compile(
    r"(?i)matr[ií]culas?\s*(?:n[º°o\.°]?\s*)?"
    r"(\d{1,3}(?:\.\d{3})+|\d{2,6})\b"
)

ANOS_PADRAO_VINTENARIA = 20
ANOS_PERMITIDOS = frozenset({10, 15, 20, 30})
MAX_PROFUNDIDADE_ORIGEM = 5
MAX_ORIGENS_POR_CERTIDAO = 12


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    ).upper()


def codigo_da_natureza(natureza_titulo) -> int | None:
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


def classificar_dominio(ato) -> dict | None:
    """Devolve criterio quando o ato transmite/constitui dominio."""
    if _campo(ato, "cancelado"):
        return None
    codigo = codigo_da_natureza(_campo(ato, "natureza_titulo"))
    if codigo is not None and codigo not in CODIGOS_SEM_SENTIDO:
        if codigo in CODIGOS_DE_DOMINIO:
            return {"criterio": "natureza", "conferir": False}
        return None

    tipo = (_campo(ato, "tipo") or "").upper()
    natureza = _campo(ato, "natureza_titulo") or ""
    teor = _campo(ato, "teor") or ""
    if tipo == "R":
        alvo = _sem_acento(natureza + " " + _titulo_do_registro(teor))
    else:
        # AV so entra por natureza reconhecida (ex. consolidacao 119);
        # palavra-chave larga na averbacao puxaria construcao/endereco.
        return None
    if any(_sem_acento(t) in alvo for t in _TERMOS_DOMINIO):
        return {"criterio": "palavra-chave", "conferir": True}
    return None


def cadeia_dominial(atos, rotulo=None) -> list[dict]:
    """Atos de transmissao de dominio, na ordem recebida (cronologica)."""
    saida = []
    for a in atos:
        achado = classificar_dominio(a)
        if not achado:
            continue
        linha = dict(a) | achado
        if rotulo is not None:
            linha["rotulo"] = rotulo(a)
        saida.append(linha)
    return saida


def _parse_data(valor) -> date | None:
    texto = str(valor or "").strip()[:10]
    if not texto or len(texto) < 8:
        return None
    try:
        return date.fromisoformat(texto.replace("/", "-")[:10])
    except ValueError:
        return None


def normalizar_anos(anos) -> int:
    """Anos da janela; padrao 20; aceita 10/15/20/30 ou inteiro 1..50."""
    try:
        n = int(anos)
    except (TypeError, ValueError):
        return ANOS_PADRAO_VINTENARIA
    if n in ANOS_PERMITIDOS:
        return n
    if 1 <= n <= 50:
        return n
    return ANOS_PADRAO_VINTENARIA


def desde_da_janela(anos, *, hoje: date | None = None) -> date:
    hoje = hoje or date.today()
    n = normalizar_anos(anos)
    # Aproximacao civil: 365 * n dias (sem inventar calendario de cartorio).
    return hoje - timedelta(days=365 * n)


def atos_na_janela(atos, *, desde: date, rotulo=None) -> list[dict]:
    """Filtra atos com data_ato >= desde; sem data ficam de fora (nao inventa)."""
    saida = []
    for a in atos:
        d = _parse_data(_campo(a, "data_ato"))
        if d is None or d < desde:
            continue
        linha = dict(a)
        if rotulo is not None and "rotulo" not in linha:
            linha["rotulo"] = rotulo(a)
        saida.append(linha)
    return saida


def conteudo_vintenaria(atos, *, anos=20, rotulo=None, hoje: date | None = None
                        ) -> dict:
    """Dominio + onus no periodo. Devolve listas e metadados para o miolo."""
    hoje = hoje or date.today()
    n = normalizar_anos(anos)
    desde = desde_da_janela(n, hoje=hoje)
    dominio = cadeia_dominial(atos, rotulo=rotulo)
    dominio_periodo = [
        a for a in dominio
        if (d := _parse_data(_campo(a, "data_ato"))) is not None and d >= desde
    ]
    onus = onus_vigentes(atos, rotulo=rotulo)
    onus_periodo = [
        a for a in onus
        if (d := _parse_data(_campo(a, "data_ato"))) is not None and d >= desde
    ]
    return {
        "anos": n,
        "desde": desde.isoformat(),
        "ate": hoje.isoformat(),
        "dominio": dominio_periodo,
        "onus": onus_periodo,
    }


# ---------------------------------------------------------------------------
# Matriculas de origem (registro_anterior)
# ---------------------------------------------------------------------------

def normalizar_numero_matricula(valor) -> str:
    """So digitos, sem zeros a esquerda (0293 -> 293; 2.765 -> 2765)."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.lstrip("0") or (digitos if digitos else "")


def extrair_numeros_registro_anterior(texto) -> list[str]:
    """Numeros citados no texto de registro_anterior, normalizados.

    Ordem de aparicao; sem duplicata. Nao resolve contra o banco — so parseia.
    """
    vistos: set[str] = set()
    saida: list[str] = []
    for bruto in _RE_MAT_NO_ANTERIOR.findall(texto or ""):
        norm = normalizar_numero_matricula(bruto)
        if not norm or norm in vistos:
            continue
        vistos.add(norm)
        saida.append(norm)
    return saida


def parsear_numeros_digitados(texto) -> list[str]:
    """Numeros que o balcao digitou (virgula, espaco, ponto, barra)."""
    vistos: set[str] = set()
    saida: list[str] = []
    for bruto in re.findall(r"\d{1,3}(?:\.\d{3})+|\d{2,6}", texto or ""):
        norm = normalizar_numero_matricula(bruto)
        if not norm or norm in vistos:
            continue
        vistos.add(norm)
        saida.append(norm)
    return saida


def sugerir_numeros_origem(
    registro_anterior,
    *,
    numero_atual=None,
    max_itens: int = MAX_ORIGENS_POR_CERTIDAO,
) -> list[str]:
    """Candidatos de origem a partir do registro_anterior da matricula atual."""
    excluir = normalizar_numero_matricula(numero_atual) if numero_atual else ""
    saida = []
    for n in extrair_numeros_registro_anterior(registro_anterior):
        if excluir and n == excluir:
            continue
        saida.append(n)
        if len(saida) >= max_itens:
            break
    return saida

"""A FOLHA DO DIA — o painel desenhado como a folha de um livro de expediente.

Ordem do oficial em 12/11/2026: «quero algo diferente que uma IA costuma
gerar». A fileira de cartões com número grande serve a qualquer empresa; o que
é do ofício é o termo de abertura, a margem e o prazo contado em dias.

Aqui mora só a conta, sem banco e sem tela:

  * a data por extenso, na fórmula do assento («Aos doze dias do mês de…»);
  * a régua de prazos — uma casa por dia, de alguns dias atrás até o fim do
    alerta, com quantos processos vencem em cada uma;
  * o aperto de um prazo dito em gente («há 6 dias», «hoje», «em 1 dia»).

QUEM MEDE É `database.prazos_por_dia`, pela mesma régua de `dashboard_stats`:
se as duas contassem por réguas diferentes, a frase do alto diria «3 vencidos»
e a régua desenharia 4.
"""
from __future__ import annotations

from datetime import date, timedelta

DIAS_ATRAS = 6

_UNIDADES = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete",
             "oito", "nove", "dez", "onze", "doze", "treze", "quatorze",
             "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZENAS = {20: "vinte", 30: "trinta", 40: "quarenta", 50: "cinquenta",
            60: "sessenta", 70: "setenta", 80: "oitenta", 90: "noventa"}
_CENTENAS = {100: "cento", 200: "duzentos", 300: "trezentos",
             400: "quatrocentos", 500: "quinhentos", 600: "seiscentos",
             700: "setecentos", 800: "oitocentos", 900: "novecentos"}
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_SEMANA_INTEIRA = ["segunda-feira", "terça-feira", "quarta-feira",
                   "quinta-feira", "sexta-feira", "sábado", "domingo"]


def por_extenso(n: int) -> str:
    """O número em palavras, de 0 a 9999 — o bastante para dia e ano."""
    if not 0 <= n <= 9999:
        raise ValueError(f"fora do alcance: {n}")
    if n < 20:
        return _UNIDADES[n]
    if n < 100:
        dezena, resto = n - n % 10, n % 10
        return _DEZENAS[dezena] + (f" e {_UNIDADES[resto]}" if resto else "")
    if n == 100:
        return "cem"
    if n < 1000:
        centena, resto = n - n % 100, n % 100
        return _CENTENAS[centena] + (f" e {por_extenso(resto)}" if resto else "")
    milhar, resto = n // 1000, n % 1000
    cabeca = "mil" if milhar == 1 else f"{_UNIDADES[milhar]} mil"
    if not resto:
        return cabeca
    # «dois mil e vinte e seis», «mil novecentos e noventa e oito»: o «e» só
    # liga o milhar ao resto quando o resto é menor que cem ou centena cheia.
    liga = " e " if resto < 100 or resto % 100 == 0 else " "
    return cabeca + liga + por_extenso(resto)


def data_do_termo(dia: date) -> str:
    """«Aos doze dias do mês de novembro de dois mil e vinte e seis»."""
    mes, ano = _MESES[dia.month - 1], por_extenso(dia.year)
    if dia.day == 1:
        return f"Ao primeiro dia do mês de {mes} de {ano}"
    return f"Aos {por_extenso(dia.day)} dias do mês de {mes} de {ano}"


def aperto(prazo: str | None, hoje: date) -> str:
    """O prazo dito em dias, do jeito que se fala no balcão."""
    if not prazo:
        return ""
    try:
        dias = (date.fromisoformat(str(prazo)[:10]) - hoje).days
    except ValueError:
        return ""
    if dias == 0:
        return "hoje"
    if dias == -1:
        return "ontem"
    if dias == 1:
        return "amanhã"
    return f"há {-dias} dias" if dias < 0 else f"em {dias} dias"


def regua(por_dia: dict[str, int], hoje: date, alerta: int,
          vencidos_ao_todo: int = 0, atras: int = DIAS_ATRAS) -> dict:
    """As casas da régua, de `atras` dias antes de hoje até o fim do alerta.

    `vencidos_ao_todo` é o número do alto do painel: o que venceu ANTES da
    primeira casa não tem onde ser desenhado e sai contado em `antes`, para a
    régua não parecer mais leve do que a frase que a encabeça.
    """
    casas, na_janela = [], 0
    for passo in range(-atras, max(alerta, 0) + 1):
        dia = hoje + timedelta(days=passo)
        quantos = int(por_dia.get(dia.isoformat(), 0) or 0)
        if passo < 0:
            na_janela += quantos
        casas.append({
            "data": dia.isoformat(),
            "dia": f"{dia.day:02d}",
            "semana": "hoje" if passo == 0 else _SEMANA[dia.weekday()],
            "hoje": passo == 0,
            "vencido": passo < 0,
            # Sábado e domingo saem hachurados. Feriado não: a casa não tem
            # (ainda) um calendário de feriados, e inventar um seria pior.
            "folga": dia.weekday() >= 5,
            "quantos": quantos,
        })
    return {"casas": casas, "antes": max(int(vencidos_ao_todo) - na_janela, 0),
            "desde": casas[0]["data"], "ate": casas[-1]["data"]}


def cabecalho(hoje: date) -> dict:
    """O que o selo do dia e o termo precisam, já pronto para a tela."""
    return {"termo": data_do_termo(hoje),
            "semana": _SEMANA_INTEIRA[hoje.weekday()],
            "dia": f"{hoje.day:02d}",
            "mes": _MESES[hoje.month - 1][:3],
            "ano": hoje.year,
            # A folha do livro de expediente é o dia do ano: 12/11 é a 316.
            "folha": hoje.timetuple().tm_yday}

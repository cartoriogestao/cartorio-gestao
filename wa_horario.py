"""O horário de atendimento do balcão do WhatsApp — escrito, lido e perguntado.

    «configure a IA para fazer o primeiro atendimento, passando para atendente
     quando houver justo motivo» — o oficial, 29/10/2026

POR QUE EXISTE
    A passagem para pessoa dizia ao cliente «respondemos no horário de
    atendimento» sem dizer qual é, e à noite ninguém sabia se a mensagem tinha
    chegado. Com o horário escrito, o aviso diz quando a casa abre, e o vigia
    (`wa_rotina`) manda o aviso de fora do horário a quem escreve com o balcão
    fechado.

COMO SE ESCREVE (a tela do atendente)
    Uma faixa por linha: os dias e um ou mais intervalos.

        seg-sex 08:00-12:00 13:00-17:00
        sab 08:00-12:00

    Dias: dom, seg, ter, qua, qui, sex, sab (com ou sem acento, maiúscula ou
    minúscula); intervalo «seg-sex» ou lista «seg,qua,sex». Hora «8», «8h»,
    «08:00» ou «8h30». Linha vazia ou que começa com «#» não conta.

    Horário em branco quer dizer «sem horário»: nada de aviso de fora do
    horário, e o balcão é tratado como aberto. Feriado não entra aqui — a casa
    não tem, no WhatsApp, a lista de feriados que o prazo usa, e o aviso de um
    feriado diria «abrimos amanhã às 8h» no dia errado. Isso fica A FAZER.

SÓ CALCULA. Nenhuma função lê o banco nem fala com a rede.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from unicodedata import normalize

DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")   # datetime.weekday()
NOME_DO_DIA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


class HorarioErro(ValueError):
    """O horário escrito não se lê. Mensagem pronta para a tela."""


def _sem_acento(texto: str) -> str:
    n = normalize("NFD", str(texto or ""))
    return "".join(c for c in n if not (0x300 <= ord(c) <= 0x36F)).lower()


_HORA = re.compile(r"^(\d{1,2})(?:[:h](\d{2})?)?$")


def _minutos(texto: str, linha: int) -> int:
    achado = _HORA.match(texto.strip().lower())
    if not achado:
        raise HorarioErro(f"Linha {linha}: «{texto}» não é uma hora (use 08:00 ou 8h).")
    h, m = int(achado.group(1)), int(achado.group(2) or 0)
    if h > 24 or m > 59 or (h == 24 and m):
        raise HorarioErro(f"Linha {linha}: «{texto}» não é uma hora do dia.")
    return h * 60 + m


def _dias(texto: str, linha: int) -> list[int]:
    saida: list[int] = []
    for pedaco in _sem_acento(texto).split(","):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        if "-" in pedaco:
            de, ate = (p.strip()[:3] for p in pedaco.split("-", 1))
            if de not in DIAS or ate not in DIAS:
                raise HorarioErro(f"Linha {linha}: «{pedaco}» não é um intervalo de dias "
                                  "(use seg-sex).")
            i, f = DIAS.index(de), DIAS.index(ate)
            while True:
                saida.append(i)
                if i == f:
                    break
                i = (i + 1) % 7
        else:
            dia = pedaco[:3]
            if dia not in DIAS:
                raise HorarioErro(f"Linha {linha}: «{pedaco}» não é um dia (use dom, "
                                  "seg, ter, qua, qui, sex ou sab).")
            saida.append(DIAS.index(dia))
    if not saida:
        raise HorarioErro(f"Linha {linha}: faltam os dias (ex.: seg-sex).")
    return saida


def ler(texto: str) -> dict[int, list[tuple[int, int]]]:
    """{dia da semana: [(início, fim) em minutos]}. Vazio = sem horário.

    Levanta `HorarioErro` com a linha que não se leu."""
    regra: dict[int, list[tuple[int, int]]] = {}
    for n, bruta in enumerate(str(texto or "").splitlines(), start=1):
        linha = bruta.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split()
        if len(partes) < 2:
            raise HorarioErro(f"Linha {n}: escreva os dias e o horário (ex.: "
                              "seg-sex 08:00-17:00).")
        dias = _dias(partes[0], n)
        faixas = []
        for intervalo in partes[1:]:
            if "-" not in intervalo:
                raise HorarioErro(f"Linha {n}: «{intervalo}» não é um intervalo "
                                  "(use 08:00-17:00).")
            ini, fim = (_minutos(p, n) for p in intervalo.split("-", 1))
            if fim <= ini:
                raise HorarioErro(f"Linha {n}: o intervalo «{intervalo}» termina antes "
                                  "de começar.")
            faixas.append((ini, fim))
        for d in dias:
            regra.setdefault(d, []).extend(faixas)
    for d in regra:
        regra[d].sort()
    return regra


def ler_ou_vazio(texto: str) -> dict[int, list[tuple[int, int]]]:
    """Como `ler`, mas o horário que não se lê vale como «sem horário». É para
    quem roda sozinho (o vigia): a tela já recusou o texto ruim ao gravar."""
    try:
        return ler(texto)
    except HorarioErro:
        return {}


def aberto(regra: dict, quando: datetime) -> bool:
    """O balcão está aberto agora? Sem horário, sim."""
    if not regra:
        return True
    m = quando.hour * 60 + quando.minute
    return any(ini <= m < fim for ini, fim in regra.get(quando.weekday(), ()))


def proxima_abertura(regra: dict, quando: datetime) -> datetime | None:
    """Quando o balcão abre de novo, a partir de `quando`. None se já está
    aberto ou se não há horário."""
    if not regra or aberto(regra, quando):
        return None
    for dias in range(0, 8):
        dia = (quando + timedelta(days=dias)).replace(hour=0, minute=0, second=0,
                                                      microsecond=0)
        for ini, _fim in regra.get(dia.weekday(), ()):
            inicio = dia + timedelta(minutes=ini)
            if inicio > quando:
                return inicio
    return None


def fechou_em(regra: dict, quando: datetime) -> datetime | None:
    """O fim da última faixa antes de `quando` — o começo do período fechado de
    agora. None se aberto ou sem horário. É a régua do «um aviso por período
    fechado»: aviso dado depois disto já vale para este período."""
    if not regra or aberto(regra, quando):
        return None
    for dias in range(0, 8):
        dia = (quando - timedelta(days=dias)).replace(hour=0, minute=0, second=0,
                                                      microsecond=0)
        for _ini, fim in sorted(regra.get(dia.weekday(), ()), reverse=True):
            final = dia + timedelta(minutes=fim)
            if final <= quando:
                return final
    return None


def _hora(minutos: int) -> str:
    h, m = divmod(int(minutos), 60)
    return f"{h}h" if not m else f"{h}h{m:02d}"


def descrever(regra: dict) -> str:
    """«segunda a sexta, das 8h às 12h e das 13h às 17h; sábado, das 8h às 12h»."""
    if not regra:
        return ""
    grupos: list[tuple[list[int], list]] = []
    for d in range(7):
        faixas = regra.get(d)
        if not faixas:
            continue
        if grupos and grupos[-1][1] == faixas and grupos[-1][0][-1] == d - 1:
            grupos[-1][0].append(d)
        else:
            grupos.append(([d], faixas))
    partes = []
    for dias, faixas in grupos:
        nome = (NOME_DO_DIA[dias[0]] if len(dias) == 1
                else f"{NOME_DO_DIA[dias[0]]} a {NOME_DO_DIA[dias[-1]]}")
        horas = " e ".join(f"das {_hora(i)} às {_hora(f)}" for i, f in faixas)
        partes.append(f"{nome}, {horas}")
    return "; ".join(partes)


def quando_abre(regra: dict, quando: datetime) -> str:
    """«amanhã (quinta) às 8h», «hoje às 13h», «segunda às 8h». "" se aberto."""
    proxima = proxima_abertura(regra, quando)
    if proxima is None:
        return ""
    dias = (proxima.date() - quando.date()).days
    hora = _hora(proxima.hour * 60 + proxima.minute)
    if dias == 0:
        return f"hoje às {hora}"
    if dias == 1:
        return f"amanhã ({NOME_DO_DIA[proxima.weekday()]}) às {hora}"
    return f"{NOME_DO_DIA[proxima.weekday()]} às {hora}"

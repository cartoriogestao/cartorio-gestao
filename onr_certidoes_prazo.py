"""O relógio de prazo dos pedidos de certidão do ONR (RI013, etapa C1, 24/11/2026).

SÓ CALCULA. Não lê a rede, não escreve no banco (o que lê do banco é a
configuração do expediente e os feriados).

A NORMA, COMO ESTÁ NO REPOSITÓRIO (`base_normativa/`)
    CNN 325   verificar os pedidos de certidão na abertura e no encerramento do
              expediente e, no máximo, a cada hora;
    CNN 327   (= CN-TJMA 547) a certidão de inteiro teor digital pedida no
              expediente, com o número da matrícula ou do registro no Livro 3,
              sai em até 2 horas; ato manuscrito, em até 5 dias;
    Lei 6.015, art. 19, § 10 (Lei 14.382/2022) os prazos correm do PAGAMENTO
              dos emolumentos: I — 4 horas para o inteiro teor eletrônico com o
              número (o CNN 327, mais curto, prevalece); II — 1 dia para a
              situação jurídica atualizada; III — 5 dias para transcrições e
              demais casos. O caput do art. 19 já dizia «não podendo ser
              retardada por mais de cinco dias»;
    CN-TJMA 436 os prazos do RI se contam em dias e horas ÚTEIS, inclusive os
              da emissão de certidões.

Todo pedido tem prazo na norma: nenhum tipo fica «sem prazo» aqui, e nenhum
prazo é inventado além desses três.

AS LEITURAS QUE A NORMA NÃO FECHA — e ficam ditas (decisão do titular no
relatório da RI013):
    - pedido feito FORA do expediente: o CNN 327 fala do pedido «durante o
      horário de expediente». Fora dele, o relógio conta as 2 horas a partir da
      abertura seguinte. É a leitura mais estrita das possíveis: a outra seria
      mandar o pedido das 14h05 para os 5 dias do inciso III;
    - pedido que passou pelo orçamento (o ONR pediu o valor, o cliente pagou
      depois): o ONR não diz a hora do pagamento. O relógio conta da ÚLTIMA vez
      em que a rodada o viu sem pagamento (`pagamento_depois_de`) — o pagamento
      foi depois disso, então o relógio nunca dá mais prazo do que a lei dá;
    - «Inteiro teor, ônus e ações» (tipo 12 do ONR) conta como inteiro teor da
      matrícula (2 horas), que é como o robô o emite;
    - ato manuscrito (5 dias pelo CNN 327): o sistema não sabe se a matrícula é
      manuscrita; o relógio mostra as 2 horas e o texto lembra a exceção.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

#: A configuração de onde se lê o expediente (a mesma do aviso do protesto,
#: `protesto_aviso.CHAVE_DO_HORARIO`): texto livre, «das 08h às 14h».
CHAVE_DO_HORARIO = "serventia_horario"
CHAVE_DOS_FERIADOS = "ri_feriados_locais"

# ---------------------------------------------------------------- as regras

CNN_327 = "CNN_327"
LEI_19_II = "LEI_6015_19_10_II"
LEI_19_III = "LEI_6015_19_10_III"

REGRAS = {
    CNN_327: {"horas": 2, "dias": None, "curto": "2 h úteis",
              "base": "CNN art. 327 (CN-TJMA art. 547): inteiro teor digital com o número da "
                      "matrícula ou do registro no Livro 3 — até 2 horas no expediente "
                      "(ato manuscrito: até 5 dias)"},
    LEI_19_II: {"horas": None, "dias": 1, "curto": "1 dia útil",
                "base": "Lei 6.015, art. 19, § 10, II: situação jurídica atualizada — até 1 dia, "
                        "contado do pagamento (CN-TJMA art. 436: dias úteis)"},
    LEI_19_III: {"horas": None, "dias": 5, "curto": "5 dias úteis",
                 "base": "Lei 6.015, art. 19, § 10, III: demais certidões — até 5 dias, contados "
                         "do pagamento (CN-TJMA art. 436: dias úteis)"},
}

#: Os tipos do ONR (`onr_wsoficio.TIPO_CERTIDAO`) que são inteiro teor da
#: matrícula: 3 «Matrícula do imóvel» e 12 «Inteiro teor, ônus e ações».
TIPOS_INTEIRO_TEOR_DA_MATRICULA = {"3", "12"}
#: 9 «Livro 3 — garantias» e 10 «Outros registros Livro 3 — auxiliar», pedidos
#: pelo número do registro no Livro 3 (pesquisa 11).
TIPOS_DO_LIVRO_3 = {"9", "10"}
TIPOS_SITUACAO_JURIDICA = {"21"}
PESQUISA_POR_MATRICULA = {"4", "13", "matrícula", "matricula", "matrícula com complemento",
                          "matricula com complemento"}
PESQUISA_POR_LIVRO_3 = {"11", "nº do registro do livro 3", "n° do registro do livro 3"}

#: Os status do ONR em que o pedido ainda não foi pago: o prazo não corre.
STATUS_SEM_PAGAMENTO = {"10", "informar valor dos emolumentos", "11", "aguardando pagamento"}
#: O pedido que já saiu desta casa (ou que o ONR deu por fechado).
SITUACOES_ENCERRADAS = {"RESPONDIDO", "DEVOLVIDO", "FECHADO_NO_ONR"}
ETAPAS_ENCERRADAS = {"RESPONDIDO", "FECHADO"}

# A situação do relógio.
NO_PRAZO = "NO_PRAZO"
MENOS_DE_1H = "MENOS_DE_1H"
VENCIDO = "VENCIDO"
AGUARDA_PAGAMENTO = "AGUARDA_PAGAMENTO"
ENCERRADO = "ENCERRADO"
#: As que vão para o painel de quem aprova.
AVISAM = (MENOS_DE_1H, VENCIDO)
#: «Falta menos de 1 hora», em minutos de expediente.
LIMITE_DO_AVISO_MIN = 60


def _codigo(valor: Any) -> str:
    return str(valor or "").strip().lower()


def _tipo(valor: Any) -> str:
    """O código do tipo do ONR, aceitando também o nome («Matrícula do imóvel»)."""
    texto = _codigo(valor)
    if texto.isdigit() or not texto:
        return texto
    try:
        import onr_wsoficio as WS
        for numero, nome in WS.TIPO_CERTIDAO.items():
            if _codigo(nome) == texto:
                return str(numero)
    except ImportError:                                   # pragma: no cover
        pass
    return texto


def regra(pedido: dict) -> dict:
    """A regra de prazo do pedido: {codigo, horas, dias, base, curto}. Só calcula."""
    tipo = _tipo(pedido.get("tipo_certidao"))
    por = _codigo(pedido.get("pesquisa_por"))
    com_numero = bool(str(pedido.get("matricula_numero") or "").strip())
    if tipo in TIPOS_INTEIRO_TEOR_DA_MATRICULA and por in PESQUISA_POR_MATRICULA and com_numero:
        codigo = CNN_327
    elif tipo in TIPOS_DO_LIVRO_3 and por in PESQUISA_POR_LIVRO_3:
        codigo = CNN_327
    elif tipo in TIPOS_SITUACAO_JURIDICA:
        codigo = LEI_19_II
    else:
        codigo = LEI_19_III
    return {"codigo": codigo, **REGRAS[codigo]}


# ---------------------------------------------------------------- o expediente

@dataclass(frozen=True)
class Expediente:
    abre: time
    fecha: time
    configurado: bool
    feriados: frozenset = field(default_factory=frozenset)
    texto: str = ""


def ler_horario(texto: Any) -> tuple[time, time] | None:
    """«das 08h às 14h», «8h30 às 13h», «08:00-14:00» → (08:00, 14:00). Só calcula.

    Lê as DUAS primeiras horas do texto. O que não fechar (uma hora só, a
    segunda antes da primeira, hora que não existe) devolve None — horário
    inventado é pior que horário ausente."""
    achadas = re.findall(r"(?<!\d)(\d{1,2})\s*(?:h|:)\s*(\d{2})?", str(texto or ""), re.I)
    horas = []
    for h, m in achadas[:2]:
        h, m = int(h), int(m or 0)
        if h > 23 or m > 59:
            return None
        horas.append(time(h, m))
    if len(horas) < 2 or horas[1] <= horas[0]:
        return None
    return horas[0], horas[1]


def expediente(texto_do_horario: Any, feriados: Any = ()) -> Expediente:
    lido = ler_horario(texto_do_horario)
    if lido is None:
        return Expediente(time(0, 0), time(23, 59, 59), False, frozenset(feriados or ()),
                          str(texto_do_horario or ""))
    return Expediente(lido[0], lido[1], True, frozenset(feriados or ()),
                      str(texto_do_horario or ""))


def expediente_da_casa(con) -> Expediente:
    """O expediente da serventia (`serventia_horario`) e os feriados locais. Só LÊ."""
    from bd_nativo import banco
    from ri_schema import ler_feriados_locais
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return expediente("")
    def _valor(chave):
        linha = bd.um("SELECT value FROM settings WHERE key=%s", (chave,))
        return (linha["value"] if linha else "") or ""
    return expediente(_valor(CHAVE_DO_HORARIO), ler_feriados_locais(_valor(CHAVE_DOS_FERIADOS)))


def _dia_util(dia: date, exp: Expediente) -> bool:
    from ri_schema import eh_dia_util
    return eh_dia_util(dia, set(exp.feriados))


def _abre(dia: date, exp: Expediente) -> datetime:
    return datetime.combine(dia, exp.abre)


def _fecha(dia: date, exp: Expediente) -> datetime:
    return datetime.combine(dia, exp.fecha)


def no_expediente(quando: datetime, exp: Expediente) -> bool:
    return (_dia_util(quando.date(), exp)
            and _abre(quando.date(), exp) <= quando < _fecha(quando.date(), exp))


def proxima_abertura(quando: datetime, exp: Expediente) -> datetime:
    """`quando`, se estiver no expediente; senão, a abertura seguinte."""
    dia = quando.date()
    if _dia_util(dia, exp):
        if quando < _abre(dia, exp):
            return _abre(dia, exp)
        if quando < _fecha(dia, exp):
            return quando
    for _ in range(400):
        dia += timedelta(days=1)
        if _dia_util(dia, exp):
            return _abre(dia, exp)
    raise ValueError("não há dia útil no ano seguinte")       # pragma: no cover


def somar_horas_uteis(inicio: datetime, horas: float, exp: Expediente) -> datetime:
    """`inicio` mais `horas` de expediente (CN-TJMA 436)."""
    resta = timedelta(hours=horas)
    atual = proxima_abertura(inicio, exp)
    while True:
        livre = _fecha(atual.date(), exp) - atual
        if resta <= livre:
            return atual + resta
        resta -= livre
        atual = proxima_abertura(_fecha(atual.date(), exp), exp)


def minutos_uteis(de: datetime, ate: datetime, exp: Expediente) -> int:
    """Minutos de expediente entre dois momentos; negativo se `ate` vem antes."""
    if ate < de:
        return -minutos_uteis(ate, de, exp)
    total = timedelta(0)
    atual = proxima_abertura(de, exp)
    while atual < ate:
        fim = min(_fecha(atual.date(), exp), ate)
        total += fim - atual
        atual = proxima_abertura(_fecha(atual.date(), exp), exp)
    return int(total.total_seconds() // 60)


def vencimento(inicio: datetime, r: dict, exp: Expediente) -> datetime:
    """Quando o prazo da regra `r` vence, contado de `inicio`. Só calcula.

    Sem o expediente configurado, as horas são corridas (é mais estrito) e os
    dias vencem às 23h59 do último dia útil."""
    if r.get("horas"):
        if not exp.configurado:
            return inicio + timedelta(hours=r["horas"])
        return somar_horas_uteis(inicio, r["horas"], exp)
    from ri_schema import soma_dias_uteis
    dia = soma_dias_uteis(inicio.date(), int(r["dias"]), set(exp.feriados))
    return _fecha(dia, exp)


# ---------------------------------------------------------------- o relógio

def _dt(valor: Any) -> datetime | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto[:19])
    except ValueError:
        pass
    try:
        return datetime.strptime(texto[:19], "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def encerrado(pedido: dict, preparo: dict | None) -> bool:
    if str(pedido.get("situacao") or "").upper() in SITUACOES_ENCERRADAS:
        return True
    if pedido.get("finalizado_em"):
        return True
    return bool(preparo and str(preparo.get("etapa") or "") in ETAPAS_ENCERRADAS)


def inicio_da_contagem(pedido: dict, preparo: dict | None) -> tuple[datetime | None, str]:
    """De quando o prazo corre, e de onde veio essa hora. Só calcula.

    (None, motivo) quando o pedido ainda não foi pago: a lei conta do
    pagamento."""
    if _codigo(pedido.get("status_onr")) in STATUS_SEM_PAGAMENTO:
        return None, "o pedido ainda não foi pago no ONR: o prazo corre do pagamento"
    pago_depois_de = _dt((preparo or {}).get("pagamento_depois_de"))
    if pago_depois_de:
        return pago_depois_de, ("da última leitura em que o pedido estava sem pagamento "
                                "(o ONR não informa a hora do pagamento)")
    pedido_em = _dt(pedido.get("data_pedido")) or _dt(pedido.get("recebido_em"))
    if pedido_em is None:
        return None, "o pedido não traz a data"
    return pedido_em, "da hora do pedido no ONR"


def _hhmm(minutos: int) -> str:
    minutos = abs(int(minutos))
    h, m = divmod(minutos, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def relogio(pedido: dict, preparo: dict | None, *, agora: datetime, exp: Expediente,
            envio_automatico: bool = False) -> dict:
    """O prazo de UM pedido, agora. Só calcula.

    Devolve {regra, base, curto, situacao, inicio, de_onde, vence_em,
    restante_min, fora_do_expediente, texto}. `restante_min` é em minutos de
    expediente (CN-TJMA 436); negativo depois do vencimento.

    `envio_automatico`: o processo `RI_ONR_CERTIDOES` está com o «pode agir»
    ligado — a certidão aprovada vai ao ONR pela rodada que a aprovação pede
    (`onr_certidoes_auto.pedir_envio_agora`). Desligado, a aprovada fica
    esperando o envio à mão, e o relógio continua correndo até lá."""
    r = regra(pedido)
    saida = {"regra": r["codigo"], "base": r["base"], "curto": r["curto"], "inicio": None,
             "de_onde": "", "vence_em": None, "restante_min": None,
             "fora_do_expediente": False, "situacao": NO_PRAZO, "texto": "",
             "expediente_configurado": exp.configurado}
    if encerrado(pedido, preparo):
        return saida | {"situacao": ENCERRADO, "texto": "respondido ou fechado no ONR"}
    inicio, de_onde = inicio_da_contagem(pedido, preparo)
    if inicio is None:
        return saida | {"situacao": AGUARDA_PAGAMENTO, "de_onde": de_onde,
                        "texto": f"{r['curto']} depois do pagamento — {de_onde}"}
    fora = bool(r.get("horas")) and exp.configurado and not no_expediente(inicio, exp)
    vence = vencimento(inicio, r, exp)
    if exp.configurado:
        restante = minutos_uteis(agora, vence, exp)
    else:
        restante = int((vence - agora).total_seconds() // 60)
    if agora >= vence:
        situacao = VENCIDO
    elif restante <= LIMITE_DO_AVISO_MIN:
        situacao = MENOS_DE_1H
    else:
        situacao = NO_PRAZO
    quando = f"{vence:%d/%m %H:%M}"
    if situacao == VENCIDO:
        texto = f"VENCEU em {quando} ({r['curto']})"
    else:
        texto = f"vence em {quando} — faltam {_hhmm(restante)} de expediente ({r['curto']})"
    notas = []
    if fora:
        notas.append("pedido fora do expediente: contado da abertura seguinte")
    if not exp.configurado:
        notas.append(f"o expediente não está configurado ({CHAVE_DO_HORARIO}): horas corridas")
    etapa = str((preparo or {}).get("etapa") or "")
    if etapa == "A_ASSINAR":
        notas.append("aprovada: o robô assina e envia na rodada pedida pela aprovação"
                     if envio_automatico else
                     "aprovada, mas o «pode agir» está desligado: o envio ao ONR é à mão")
    if notas:
        texto += " · " + "; ".join(notas)
    return saida | {"situacao": situacao, "inicio": inicio.isoformat(timespec="minutes"),
                    "de_onde": de_onde, "vence_em": vence.isoformat(timespec="minutes"),
                    "restante_min": restante, "fora_do_expediente": fora, "texto": texto}


# ---------------------------------------------------------------- a agenda (CNN 325)

#: A folga, em minutos, para dizer que uma rodada «é» a da abertura ou a do
#: encerramento (a rodada das 08:00 começa às 08:00:12).
FOLGA_DA_ABERTURA_MIN = 10
INTERVALO_MAXIMO_MIN = 60


def _minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def _hora(texto: str) -> time:
    h, m = str(texto).split(":")[:2]
    return time(int(h), int(m))


def _rodadas_do_dia(agenda: dict) -> list[int]:
    """Os minutos do dia em que a agenda roda (a mesma conta de
    `automacao._slots_do_dia`, sem importar a central)."""
    janela = agenda.get("janela")
    inicio = _minutos(_hora(janela[0])) if janela else 0
    fim = _minutos(_hora(janela[1])) if janela else 23 * 60 + 59
    if agenda.get("horarios"):
        return sorted(m for m in (_minutos(_hora(h)) for h in agenda["horarios"])
                      if inicio <= m <= fim)
    passo = int(agenda.get("intervalo_min") or 0)
    if passo <= 0:
        return []
    return list(range(inicio, fim + 1, passo))


def conferir_agenda(agenda: Any, exp: Expediente) -> list[str]:
    """O que a agenda da rodada deixa de cumprir do CNN 325. Lista vazia: cumpre.

    Pede, em todo dia útil (seg a sex): uma rodada na abertura, uma no
    encerramento e nenhum buraco maior que 60 minutos no meio."""
    if not isinstance(agenda, dict):
        return ["a agenda da rodada não se lê"]
    problemas = []
    if not exp.configurado:
        problemas.append(f"o expediente da serventia não está configurado ({CHAVE_DO_HORARIO}): "
                         "não dá para conferir a abertura e o encerramento")
        return problemas
    dias = {int(d) for d in (agenda.get("dias") or range(7))}
    faltam = [d for d in range(5) if d not in dias]
    if faltam:
        nomes = ("seg", "ter", "qua", "qui", "sex")
        problemas.append("a rodada não roda em " + ", ".join(nomes[d] for d in faltam))
    try:
        rodadas = _rodadas_do_dia(agenda)
    except (ValueError, IndexError, TypeError):
        return problemas + ["a agenda da rodada não se lê"]
    abre, fecha = _minutos(exp.abre), _minutos(exp.fecha)
    no_dia = [m for m in rodadas if abre <= m <= fecha + FOLGA_DA_ABERTURA_MIN]
    if not any(abre <= m <= abre + FOLGA_DA_ABERTURA_MIN for m in no_dia):
        problemas.append(f"não há rodada na abertura ({exp.abre:%H:%M})")
    if not any(fecha - FOLGA_DA_ABERTURA_MIN <= m <= fecha + FOLGA_DA_ABERTURA_MIN
               for m in no_dia):
        problemas.append(f"não há rodada no encerramento ({exp.fecha:%H:%M})")
    pontos = sorted({abre, *[m for m in no_dia if m <= fecha], fecha})
    maior = max((b - a for a, b in zip(pontos, pontos[1:])), default=0)
    if maior > INTERVALO_MAXIMO_MIN:
        problemas.append(f"há {maior} min sem rodada no expediente (o máximo é "
                         f"{INTERVALO_MAXIMO_MIN})")
    return problemas

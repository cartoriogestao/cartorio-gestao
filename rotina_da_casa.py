"""A ROTINA DA SERVENTIA — a manutenção do cartório, escrita para quem não o conhece.

    «Sobre as conferências por área, serve para rotinas e demandas do dia a
    dia. Não tem nenhuma demanda de rotina cadastrada lá, só débito passado.
    [...] cadastre nossa rotina lá, como se fosse para eu, oficial, delegar
    tarefas de manutenção do cartório para quem não faz ideia do que o
    cartório faz.»                                  — o oficial, 26/11/2026

O QUE FALTAVA
    A Checklist do dia (`gestor_checklist`) mostrava só o que o robô gestor
    achou (`ge_achados`) e uma lista FIXA de telas para olhar. Não havia onde
    escrever a rotina da casa — o backup que se confere toda manhã, a remessa
    da quinzena, o malote, o fechamento do mês — com quem faz, quando, e como.

O QUE É, E O QUE NÃO É (G007, 25/11/2026)
    É a rotina de MANUTENÇÃO: o que a TI e a administração resolvem (centrais,
    cópias de segurança, robôs, financeiro, malote, Corregedoria, prazos).
    A prática do ato e o trabalho físico do escrevente ficam nas tarefas; o
    débito passado, com o agente de compliance. Cada item é escrito para um
    leigo: para que serve, o passo a passo, onde se faz, como saber que ficou
    pronto, o que fazer se der errado, a prova a guardar e a base legal.

QUANDO VENCE (`ocorrencias`)
    DIARIA      todo dia útil.
    SEMANAL     nos dias da semana de `dias_semana` (ISO: 1 = segunda … 7 = domingo).
    QUINZENAL   nos dois dias do mês de `dias_mes` ('5,20').
    MENSAL      nos dias de `dias_mes`, OU no Nº dia útil `dia_util` do mês
                (negativo conta do fim: -1 é o último dia útil).
    TRIMESTRAL, SEMESTRAL, ANUAL
                nos meses de `meses` (um em cada trimestre, um em cada semestre,
                um só), no dia de `dias_mes` ou no Nº dia útil `dia_util`.
    Cada vencimento tem duas datas. A NOMINAL é a da regra (a sexta, o dia
    30); é ela que o «feito» guarda em `referencia`, e por isso dois
    vencimentos nunca viram um. O PRAZO é a nominal levada ao dia útil
    seguinte quando cai em sábado, domingo ou feriado, como o prazo legal; é
    por ele que o item aparece e atrasa. O dia 31 em mês de 30 dias vale o
    último dia do mês, e o 20º dia útil num mês que tem 19 vale o último. O
    calendário é o da casa: os feriados nacionais (`ri_schema`) e os locais
    de Configurações (`ri_feriados_locais`), os mesmos do RI, do Protesto e do
    gestor. O campo que não é da periodicidade escolhida fica vazio.

UM «FEITO» POR PERÍODO
    Na rotina de um vencimento por período — a mensal de um dia só, a
    trimestral, a semestral e a anual — o «feito» vale pelo PERÍODO (o mês,
    o trimestre, o semestre, o ano) da sua data nominal. Trocar o dia do item
    ou cadastrar um feriado novo não solta o feito já registrado. Nas outras
    (diária, semanal, quinzenal, mensal de vários dias) vale a data nominal.

VALE DESDE O CADASTRO (`vale_desde`)
    O item cobra só os vencimentos cujo prazo é do dia em que passou a valer
    em diante: o dia do cadastro, ou o da reativação (o tempo desativado não
    se cobra). A Conferência é para a rotina do dia, e não para débito
    passado: o anual de fevereiro cadastrado em novembro aparece no próximo
    fevereiro, e o cadastro mostra quando.

O QUE APARECE NO DIA (`do_dia`)
    Cada item ativo aparece desde o vencimento atual (o último cujo prazo já
    chegou) até alguém marcar «Feito»: no dia, «a fazer hoje»; depois,
    «atrasado desde dd/mm». Com horário exatamente «até HH:MM», no dia do
    prazo ele atrasa depois dessa hora. O que faltou não some: o item conta
    «N sem registro desde dd/mm» — os vencimentos sem «feito» dos últimos
    `JANELA_DAS_FALTAS` dias, nunca antes de `vale_desde` — e eles também se
    marcam, com atraso. O «feito» fica à vista no dia em que foi registrado;
    o «feito com pendência», até o vencimento seguinte.

«FEITO» (`marcar_feito`)
    Grava quem, quando, o resultado (OK, com pendência, não se aplica) e a
    observação, que é obrigatória fora do OK; e o prazo, e se veio depois
    dele («registrado com atraso»). Aceita só o vencimento atual e os sem
    registro da janela. O primeiro registro de cada vencimento (ou período)
    fica, como o «conferido hoje». Marca o responsável, o suplente, o oficial
    e o gerente; o auditor vê e não grava (M2), nem responde por rotina.

A CARGA EM LOTE (`importar`, `importar_e_auditar`)
    É a porta do agente 11: idempotente pelo `codigo`. Cria o que falta,
    atualiza o que mudou, diz o que já estava igual e devolve à parte o que
    está desativado (sem mexer nele nem reativá-lo); o responsável e o
    suplente chegam como LOGIN. Ou entra tudo, ou nada. `importar_e_auditar`
    abre a transação e grava a auditoria de cada item.

SÓ DOMÍNIO
    Nada aqui conhece o Flask: a rota (`rotina_da_casa_web`) liga os fios e
    grava a auditoria. Erro de regra é `RotinaError`, com a frase pronta.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any, Collection, Iterable, Mapping

import conformidade as CF
from bd_nativo import banco
from ri_schema import eh_dia_util, ler_feriados_locais

TABELA, TABELA_FEITOS = "ge_rotina", "ge_rotina_feitos"

#: O anexo da prova do «feito» (`attachments.entity_type`). O id é o do feito.
TIPO_DO_ANEXO = "GE_ROTINA_FEITO"

#: As áreas: as do semáforo, e a da TI, que não tem cor.
TI = "TI"
AREAS: tuple[tuple[str, str], ...] = tuple(CF.AREAS) + ((TI, "TI e sistema"),)
ROTULO_DA_AREA: dict[str, str] = dict(AREAS)

PERIODICIDADES: tuple[tuple[str, str], ...] = (
    ("DIARIA", "Diária"), ("SEMANAL", "Semanal"), ("QUINZENAL", "Quinzenal"),
    ("MENSAL", "Mensal"), ("TRIMESTRAL", "Trimestral"), ("SEMESTRAL", "Semestral"),
    ("ANUAL", "Anual"))
ROTULO_DA_PERIODICIDADE = dict(PERIODICIDADES)
#: Quantos meses do ano cada periodicidade «de meses» escolhe — um por fatia do ano.
MESES_DA_PERIODICIDADE = {"TRIMESTRAL": 4, "SEMESTRAL": 2, "ANUAL": 1}
#: De quantos em quantos meses é a fatia do ano de cada uma.
_FATIA_EM_MESES = {"MENSAL": 1, "TRIMESTRAL": 3, "SEMESTRAL": 6, "ANUAL": 12}

OK, COM_PENDENCIA, NAO_SE_APLICA = "OK", "COM_PENDENCIA", "NAO_SE_APLICA"
RESULTADOS: tuple[tuple[str, str], ...] = (
    (OK, "Feito, tudo certo"), (COM_PENDENCIA, "Feito, com pendência"),
    (NAO_SE_APLICA, "Não se aplica desta vez"))
ROTULO_DO_RESULTADO = dict(RESULTADOS)

PRIORIDADES: tuple[tuple[int, str], ...] = ((1, "Alta"), (2, "Normal"), (3, "Baixa"))
ROTULO_DA_PRIORIDADE = dict(PRIORIDADES)

DIAS_DA_SEMANA: tuple[tuple[int, str], ...] = (
    (1, "segunda"), (2, "terça"), (3, "quarta"), (4, "quinta"), (5, "sexta"),
    (6, "sábado"), (7, "domingo"))
NOMES_DOS_MESES: tuple[tuple[int, str], ...] = (
    (1, "janeiro"), (2, "fevereiro"), (3, "março"), (4, "abril"), (5, "maio"),
    (6, "junho"), (7, "julho"), (8, "agosto"), (9, "setembro"), (10, "outubro"),
    (11, "novembro"), (12, "dezembro"))

#: A situação do item no dia, na ordem da tela.
ATRASADO, HOJE, FEITO = "ATRASADO", "HOJE", "FEITO"
ORDEM_DA_SITUACAO = (ATRASADO, HOJE, FEITO)
#: Só por compatibilidade: com `vale_desde`, nenhum item sai mais nesta situação.
DESDE_O_CADASTRO = "DESDE_O_CADASTRO"

#: Quem cadastra, edita, desativa e reativa (o TI passa como o ADMIN, `papeis`).
QUEM_CADASTRA = ("ADMIN", "MANAGER")
#: Quem abre o cadastro: o auditor lê e não grava (M2).
QUEM_VE_O_CADASTRO = ("ADMIN", "MANAGER", "AUDITOR")
#: Quem marca «feito» em qualquer item; os outros, só no item de que respondem.
QUEM_MARCA_TUDO = ("ADMIN", "MANAGER")
#: Quem nunca marca, nem responde por rotina.
QUEM_SO_VE = ("AUDITOR",)

#: Até onde se procura o vencimento atual e o próximo: um ano e um pouco (o anual).
JANELA_DIAS = 400
#: Até quantos dias atrás se contam (e se marcam) os vencimentos sem registro.
JANELA_DAS_FALTAS = 30

MOTIVO_MINIMO, MOTIVO_MAXIMO = 3, 300
OBSERVACAO_MINIMA, OBSERVACAO_MAXIMA = 3, 1000
TITULO_MAXIMO, TEXTO_MAXIMO = 200, 8000

_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_.\-]{1,59}$")
_ENDPOINT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,99}$")
_NUMERACAO = re.compile(r"^\s*(?:\d{1,2}\s*[.)º°-]|[-•*])\s+")
#: O horário que o sistema entende: exatamente «até HH:MM». O resto é texto livre.
_ATE_HORA = re.compile(r"^até (\d{1,2}):(\d{2})$", re.IGNORECASE)

#: Os campos do cadastro, na ordem do formulário.
CAMPOS = ("codigo", "area", "titulo", "para_que", "como_fazer", "pronto_quando",
          "se_der_errado", "prova", "onde_endpoint", "onde_url", "base_legal",
          "periodicidade", "dias_semana", "dias_mes", "dia_util", "meses", "horario",
          "responsavel_id", "suplente_id", "prioridade", "ordem")
#: O que a carga em lote aceita: os mesmos, com a pessoa pelo LOGIN.
CAMPOS_DA_CARGA = tuple(c for c in CAMPOS if c not in ("responsavel_id", "suplente_id")) + (
    "responsavel", "suplente")
_TEXTOS_LIVRES = ("para_que", "pronto_quando", "se_der_errado", "prova", "base_legal")
_PADRAO = {"para_que": "", "pronto_quando": "", "se_der_errado": "", "prova": "",
           "base_legal": "", "onde_endpoint": None, "onde_url": None, "dias_semana": None,
           "dias_mes": None, "dia_util": None, "meses": None, "horario": None,
           "responsavel_id": None, "suplente_id": None, "prioridade": 2, "ordem": 100}


class RotinaError(ValueError):
    """O cadastro, a carga ou o «feito» que não se grava, com o que corrigir."""

    def __init__(self, problemas: str | Iterable[str]):
        self.problemas = [problemas] if isinstance(problemas, str) else list(problemas)
        super().__init__(" ".join(self.problemas))


class RotinaSemPermissao(RotinaError):
    """Quem pediu não marca esta rotina."""


# ------------------------------------------------------------------ o calendário


def feriados_da_casa(con) -> set[date]:
    """Os feriados locais de Configurações (`ri_feriados_locais`). SÓ LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return set()
    linha = bd.um("SELECT value FROM settings WHERE key = %s", ("ri_feriados_locais",))
    return ler_feriados_locais(((linha or {}).get("value")) or "")


def _util_a_partir(dia: date, feriados: set[date]) -> date:
    while not eh_dia_util(dia, feriados):
        dia += timedelta(days=1)
    return dia


def _ultimo_dia_do_mes(ano: int, mes: int) -> int:
    seguinte = date(ano + (mes == 12), mes % 12 + 1, 1)
    return (seguinte - timedelta(days=1)).day


def _n_esimo_dia_util(ano: int, mes: int, n: int, feriados: set[date]) -> date | None:
    """O Nº dia útil do mês (negativo: do fim). Mês com menos, o último (ou o primeiro)."""
    uteis = [date(ano, mes, d) for d in range(1, _ultimo_dia_do_mes(ano, mes) + 1)
             if eh_dia_util(date(ano, mes, d), feriados)]
    if not uteis or not n:
        return None
    if n > 0:
        return uteis[min(n, len(uteis)) - 1]
    return uteis[max(n, -len(uteis))]


def _numeros(texto: Any) -> list[int]:
    if texto is None:
        return []
    if isinstance(texto, (list, tuple, set, frozenset)):
        partes = [str(x) for x in texto]
    else:
        partes = re.split(r"[\s,;]+", str(texto))
    saida = []
    for p in partes:
        p = p.strip()
        if p:
            saida.append(int(p))
    return saida


def _dia(valor: Any) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    bruto = str(valor or "")[:10]
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def _dia_util_do_item(item: Mapping) -> int | None:
    bruto = item.get("dia_util")
    return int(bruto) if bruto not in (None, "") else None


def ocorrencias(item: Mapping, de: date, ate: date, *,
                feriados: set[date] | None = None) -> list[tuple[date, date]]:
    """Os vencimentos do item cujo PRAZO cai entre `de` e `ate`, inclusive. Só calcula.

    Devolve [(nominal, prazo)], na ordem do prazo (e da nominal). A nominal é a
    data da regra; o prazo, a nominal levada ao dia útil seguinte. Dois
    vencimentos podem ter o mesmo prazo (a sexta feriado cai na segunda, que
    também vence): são dois, e cada um pede o seu «feito».
    """
    feriados = feriados or set()
    de, ate = _dia(de), _dia(ate)
    if de is None or ate is None or ate < de:
        return []
    periodicidade = str(item.get("periodicidade") or "").upper()
    achados: set[tuple[date, date]] = set()
    if periodicidade == "DIARIA":
        dia = de
        while dia <= ate:
            if eh_dia_util(dia, feriados):
                achados.add((dia, dia))
            dia += timedelta(days=1)
    elif periodicidade == "SEMANAL":
        semana = set(_numeros(item.get("dias_semana")))
        # o dia que cai em feriado anda para a frente: começa-se antes de `de`
        dia = de - timedelta(days=15)
        while dia <= ate:
            if dia.isoweekday() in semana:
                achados.add((dia, _util_a_partir(dia, feriados)))
            dia += timedelta(days=1)
    elif periodicidade in ("QUINZENAL", "MENSAL") or periodicidade in MESES_DA_PERIODICIDADE:
        meses = (set(range(1, 13)) if periodicidade in ("QUINZENAL", "MENSAL")
                 else set(_numeros(item.get("meses"))))
        dias = _numeros(item.get("dias_mes"))
        dia_util = _dia_util_do_item(item)
        inicio = de - timedelta(days=40)
        ano, mes = inicio.year, inicio.month
        while (ano, mes) <= (ate.year, ate.month):
            if mes in meses:
                if dia_util:
                    certo = _n_esimo_dia_util(ano, mes, dia_util, feriados)
                    if certo:
                        achados.add((certo, certo))
                else:
                    ultimo = _ultimo_dia_do_mes(ano, mes)
                    for d in dias:
                        nominal = date(ano, mes, min(d, ultimo))
                        achados.add((nominal, _util_a_partir(nominal, feriados)))
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return sorted((o for o in achados if de <= o[1] <= ate), key=lambda o: (o[1], o[0]))


def vencimentos(item: Mapping, de: date, ate: date, *,
                feriados: set[date] | None = None) -> list[date]:
    """Os PRAZOS em que o item vence entre `de` e `ate` (sem repetir). Só calcula."""
    return sorted({prazo for _, prazo in ocorrencias(item, de, ate, feriados=feriados)})


def ocorrencia_atual(item: Mapping, hoje: date, *, feriados: set[date] | None = None,
                     desde: date | None = None) -> tuple[date, date] | None:
    """O vencimento atual: o último cujo prazo já chegou (e não é anterior a
    `desde`). (nominal, prazo), ou None. Só calcula."""
    hoje = _dia(hoje)
    desde = _dia(desde)
    for janela in (10, 45, JANELA_DIAS):
        inicio = hoje - timedelta(days=janela)
        if desde and inicio < desde:
            inicio = desde
        lista = ocorrencias(item, inicio, hoje, feriados=feriados)
        if lista:
            return lista[-1]
        if desde and inicio == desde:
            return None
    return None


def proxima_ocorrencia(item: Mapping, hoje: date, *, feriados: set[date] | None = None,
                       desde: date | None = None) -> tuple[date, date] | None:
    """O próximo vencimento, de hoje (e de `desde`) em diante. Só calcula."""
    hoje = _dia(hoje)
    inicio = max(hoje, _dia(desde) or hoje)
    for janela in (10, 45, JANELA_DIAS):
        lista = ocorrencias(item, inicio, inicio + timedelta(days=janela), feriados=feriados)
        if lista:
            return lista[0]
    return None


def por_periodo(item: Mapping) -> bool:
    """O «feito» deste item vale pelo período? (um vencimento por mês, trimestre,
    semestre ou ano). Só calcula."""
    periodicidade = str(item.get("periodicidade") or "").upper()
    if periodicidade in MESES_DA_PERIODICIDADE:
        return True
    if periodicidade == "MENSAL":
        return bool(_dia_util_do_item(item)) or len(_numeros(item.get("dias_mes"))) == 1
    return False


def periodo(item: Mapping, nominal: date) -> tuple[date, date] | None:
    """O período (primeiro e último dia) a que a data nominal pertence, no item
    de um vencimento por período; None nos outros. Só calcula."""
    if not por_periodo(item):
        return None
    fatia = _FATIA_EM_MESES[str(item.get("periodicidade")).upper()]
    primeiro_mes = ((nominal.month - 1) // fatia) * fatia + 1
    ultimo_mes = primeiro_mes + fatia - 1
    return (date(nominal.year, primeiro_mes, 1),
            date(nominal.year, ultimo_mes, _ultimo_dia_do_mes(nominal.year, ultimo_mes)))


def limite_do_horario(horario: Any) -> time | None:
    """A hora de «até HH:MM» (exatamente assim), ou None. Só calcula."""
    achado = _ATE_HORA.match(" ".join(str(horario or "").split()))
    if not achado:
        return None
    hora, minuto = int(achado.group(1)), int(achado.group(2))
    if hora > 23 or minuto > 59:
        return None
    return time(hora, minuto)


def _ordinal(n: int) -> str:
    return f"{n}º"


def _juntar(nomes: list[str]) -> str:
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _do_dia_util(n: int) -> str:
    if n == -1:
        return "no último dia útil"
    if n == -2:
        return "no penúltimo dia útil"
    if n < 0:
        return f"no {_ordinal(-n)} dia útil contado do fim do mês"
    return f"no {_ordinal(n)} dia útil"


def descrever_quando(item: Mapping) -> str:
    """«Todo dia útil, até 09:00», «Todo mês, no 5º dia útil». Só calcula."""
    periodicidade = str(item.get("periodicidade") or "").upper()
    dias_semana = dict(DIAS_DA_SEMANA)
    nomes_meses = dict(NOMES_DOS_MESES)
    dias = _numeros(item.get("dias_mes"))
    dia_util = _dia_util_do_item(item)
    if dia_util:
        no_dia = _do_dia_util(dia_util)
    elif dias:
        no_dia = ("dia " if len(dias) == 1 else "dias ") + _juntar([str(d) for d in dias])
    else:
        no_dia = ""
    if periodicidade == "DIARIA":
        texto = "Todo dia útil"
    elif periodicidade == "SEMANAL":
        texto = "Toda semana: " + _juntar(
            [dias_semana.get(d, str(d)) for d in _numeros(item.get("dias_semana"))])
    elif periodicidade == "QUINZENAL":
        texto = "Duas vezes por mês: " + no_dia
    elif periodicidade == "MENSAL":
        texto = "Todo mês, " + no_dia
    elif periodicidade in MESES_DA_PERIODICIDADE:
        texto = ("Em " + _juntar([nomes_meses.get(m, str(m)) for m in _numeros(item.get("meses"))])
                 + ", " + no_dia)
    else:
        texto = ROTULO_DA_PERIODICIDADE.get(periodicidade, periodicidade or "?")
    horario = " ".join(str(item.get("horario") or "").split())
    return f"{texto}, {horario}" if horario else texto


def passos(texto: Any) -> list[str]:
    """O passo a passo, um por linha, sem a numeração que a tela já põe. Só calcula."""
    saida = []
    for linha in str(texto or "").splitlines():
        linha = _NUMERACAO.sub("", linha).strip()
        if linha:
            saida.append(linha)
    return saida


# ------------------------------------------------------------------ a validação


def _uma_linha(valor: Any) -> str:
    return " ".join(str(valor if valor is not None else "").split())


def _varias_linhas(valor: Any) -> str:
    if isinstance(valor, (list, tuple)):
        linhas = [str(x) for x in valor]
    else:
        linhas = str(valor if valor is not None else "").replace("\r\n", "\n").split("\n")
    linhas = [" ".join(x.split()) for x in linhas]
    # as linhas vazias do começo e do fim saem; as do meio separam parágrafos
    while linhas and not linhas[0]:
        linhas.pop(0)
    while linhas and not linhas[-1]:
        linhas.pop()
    return "\n".join(linhas)


def _lista(valor: Any, minimo: int, maximo: int, nome: str, problemas: list) -> str | None:
    try:
        numeros = _numeros(valor)
    except ValueError:
        problemas.append(f"«{nome}» leva números separados por vírgula (ex.: 1,3).")
        return None
    fora = [n for n in numeros if not minimo <= n <= maximo]
    if fora:
        problemas.append(f"«{nome}» vai de {minimo} a {maximo}: {', '.join(map(str, fora))} não serve.")
        return None
    return ",".join(str(n) for n in sorted(set(numeros))) or None


def _inteiro(valor: Any, nome: str, problemas: list, padrao: int | None = None) -> int | None:
    if valor is None or str(valor).strip() == "":
        return padrao
    try:
        return int(str(valor).strip())
    except ValueError:
        problemas.append(f"«{nome}» é um número inteiro.")
        return padrao


def normalizar(dados: Mapping) -> dict:
    """O cadastro limpo e conferido, sem olhar o banco. Só calcula.

    Levanta `RotinaError` com todos os problemas de uma vez. O campo de
    «quando» que não é da periodicidade escolhida sai vazio.
    """
    problemas: list[str] = []
    n: dict[str, Any] = {}
    n["codigo"] = _uma_linha(dados.get("codigo")).upper()
    if not _CODIGO.match(n["codigo"]):
        problemas.append("O código é curto e sem espaço nem acento: letras, números, «_», «-» "
                         "ou «.» (ex.: TI_BACKUP_DIARIO). Ele não muda depois.")
    n["area"] = _uma_linha(dados.get("area")).upper()
    if n["area"] not in ROTULO_DA_AREA:
        problemas.append("Escolha a área: " + ", ".join(ROTULO_DA_AREA.values()) + ".")
    n["titulo"] = _uma_linha(dados.get("titulo"))
    if len(n["titulo"]) < 3:
        problemas.append("Escreva o título: o que se faz, em poucas palavras.")
    elif len(n["titulo"]) > TITULO_MAXIMO:
        problemas.append(f"O título é curto: até {TITULO_MAXIMO} letras.")
    for campo in ("como_fazer",) + _TEXTOS_LIVRES:
        n[campo] = _varias_linhas(dados.get(campo))
        if len(n[campo]) > TEXTO_MAXIMO:
            problemas.append(f"O texto de «{campo}» passou de {TEXTO_MAXIMO} letras.")
    if not passos(n["como_fazer"]):
        problemas.append("Escreva o passo a passo em «Como fazer»: um passo por linha.")
    endpoint = _uma_linha(dados.get("onde_endpoint")) or None
    if endpoint and not _ENDPOINT.match(endpoint):
        problemas.append("«Onde fazer (tela do sistema)» é o nome de uma tela da casa "
                         "(ex.: automacao_lista), sem espaço nem barra.")
    n["onde_endpoint"] = endpoint
    url = _uma_linha(dados.get("onde_url")) or None
    if url and (not re.match(r"^https?://[^\s/]+", url) or " " in url or len(url) > 500):
        problemas.append("«Onde fazer (endereço de fora)» é um endereço completo, que começa "
                         "com https:// (ex.: o portal da Central).")
    n["onde_url"] = url
    horario = _uma_linha(dados.get("horario")) or None
    if horario and len(horario) > 80:
        problemas.append("O horário é curto (ex.: «até 09:00»).")
    n["horario"] = horario

    n["periodicidade"] = _uma_linha(dados.get("periodicidade")).upper()
    semana = _lista(dados.get("dias_semana"), 1, 7, "dias da semana", problemas)
    dias_mes = _lista(dados.get("dias_mes"), 1, 31, "dias do mês", problemas)
    meses = _lista(dados.get("meses"), 1, 12, "meses", problemas)
    dia_util = _inteiro(dados.get("dia_util"), "Nº dia útil", problemas)
    if dia_util is not None and (dia_util == 0 or not -23 <= dia_util <= 23):
        problemas.append("O «Nº dia útil» vai de 1 a 23 (do começo do mês) ou de -1 a -23 "
                         "(do fim: -1 é o último dia útil).")
        dia_util = None
    per = n["periodicidade"]
    n.update(dias_semana=None, dias_mes=None, dia_util=None, meses=None)
    if per not in ROTULO_DA_PERIODICIDADE:
        problemas.append("Escolha de quanto em quanto tempo: " +
                         ", ".join(ROTULO_DA_PERIODICIDADE.values()).lower() + ".")
    elif per == "SEMANAL":
        if not semana:
            problemas.append("Na rotina semanal, marque o dia (ou os dias) da semana.")
        n["dias_semana"] = semana
    elif per == "QUINZENAL":
        if not dias_mes or len(dias_mes.split(",")) != 2:
            problemas.append("Na rotina quinzenal, diga os dois dias do mês (ex.: 5,20).")
        n["dias_mes"] = dias_mes
    elif per != "DIARIA":
        if bool(dias_mes) == (dia_util is not None):
            problemas.append("Diga UM jeito de achar o dia: os dias do mês (ex.: 10) ou o "
                             "Nº dia útil (ex.: 5, ou -1 para o último).")
        n["dias_mes"], n["dia_util"] = dias_mes, dia_util
        if per in MESES_DA_PERIODICIDADE:
            quantos, fatia = MESES_DA_PERIODICIDADE[per], _FATIA_EM_MESES[per]
            lista = _numeros(meses) if meses else []
            if len(lista) != quantos:
                problemas.append(f"Na rotina {ROTULO_DA_PERIODICIDADE[per].lower()}, marque "
                                 f"{quantos} {'mês' if quantos == 1 else 'meses'} do ano.")
            elif len({(m - 1) // fatia for m in lista}) != quantos:
                fatia_nome = "trimestre" if per == "TRIMESTRAL" else "semestre"
                problemas.append(f"Na rotina {ROTULO_DA_PERIODICIDADE[per].lower()}, marque um mês "
                                 f"em cada {fatia_nome} (ex.: "
                                 f"{'janeiro, abril, julho e outubro' if per == 'TRIMESTRAL' else 'junho e dezembro'}).")
            n["meses"] = meses

    for campo in ("responsavel_id", "suplente_id"):
        n[campo] = _inteiro(dados.get(campo), "responsável" if campo == "responsavel_id"
                            else "suplente", problemas)
    if n["responsavel_id"] and n["responsavel_id"] == n["suplente_id"]:
        problemas.append("O suplente é outra pessoa: quem cobre o responsável na falta dele.")
    n["prioridade"] = _inteiro(dados.get("prioridade"), "prioridade", problemas, 2)
    if n["prioridade"] not in ROTULO_DA_PRIORIDADE:
        problemas.append("A prioridade é 1 (alta), 2 (normal) ou 3 (baixa).")
    n["ordem"] = _inteiro(dados.get("ordem"), "ordem", problemas, 100)
    if n["ordem"] is not None and not 0 <= n["ordem"] <= 9999:
        problemas.append("A ordem vai de 0 a 9999.")
    if problemas:
        raise RotinaError(problemas)
    return n


def _pessoa(con, *, uid: int | None = None, login: str | None = None) -> dict | None:
    bd = banco(con)
    colunas = ("SELECT id, username, full_name, role, active, COALESCE(eh_robo, 0) AS eh_robo "
               "FROM users WHERE ")
    if uid is not None:
        return bd.um(colunas + "id = %s", (uid,))
    return bd.um(colunas + "username = %s", (login,))


def _conferir_pessoa(linha: dict | None, quem: str, papel: str) -> str | None:
    """A frase da recusa da pessoa como responsável ou suplente, ou None. Só calcula."""
    rotulo = papel.capitalize()
    if not linha:
        return f"{rotulo}: {quem} não existe."
    nome = linha.get("full_name") or quem
    if not int(linha["active"] or 0):
        return f"{rotulo}: {nome} está inativo; escolha outra pessoa."
    if int(linha["eh_robo"] or 0):
        return f"{rotulo}: {nome} é conta de robô; a rotina é de uma pessoa."
    if str(linha.get("role") or "").upper() in QUEM_SO_VE:
        return (f"{rotulo}: {nome} é auditor — o auditor confere e não faz rotina; "
                "escolha outra pessoa.")
    return None


def _conferir_pessoas(con, n: dict) -> None:
    problemas = []
    for campo, papel in (("responsavel_id", "responsável"), ("suplente_id", "suplente")):
        if n.get(campo):
            erro = _conferir_pessoa(_pessoa(con, uid=n[campo]), f"a pessoa nº {n[campo]}", papel)
            if erro:
                problemas.append(erro)
    if problemas:
        raise RotinaError(problemas)


def _conferir_tela(n: dict, endpoints: Collection[str] | None) -> str | None:
    """Com a lista das telas da casa, a tela «onde fazer» tem de estar nela."""
    if endpoints is None or not n.get("onde_endpoint"):
        return None
    if n["onde_endpoint"] not in endpoints:
        return (f"A tela «{n['onde_endpoint']}» não existe no sistema: corrija «onde_endpoint» "
                "ou deixe-o vazio e use «onde_url».")
    return None


# ------------------------------------------------------------------ o cadastro


def _agora(agora: datetime | None) -> str:
    return (agora or datetime.now()).isoformat(timespec="seconds")


def uma(con, rotina_id: int) -> dict | None:
    """A linha do cadastro, com os nomes do responsável e do suplente. SÓ LÊ."""
    linhas = _ler(con, "r.id = %s", (int(rotina_id),))
    return linhas[0] if linhas else None


def _ler(con, onde: str = "TRUE", parametros: tuple = ()) -> list[dict]:
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return []
    return bd.ler(
        f"""SELECT r.*, ur.full_name AS responsavel_nome, ur.username AS responsavel_login,
                   ur.active AS responsavel_ativo,
                   us.full_name AS suplente_nome, us.username AS suplente_login,
                   us.active AS suplente_ativo
              FROM {TABELA} r
              LEFT JOIN users ur ON ur.id = r.responsavel_id
              LEFT JOIN users us ON us.id = r.suplente_id
             WHERE {onde}
             ORDER BY r.area, r.ordem, r.prioridade, r.titulo, r.id""", parametros)


def _vale_desde(item: Mapping) -> date | None:
    return _dia(item.get("vale_desde")) or _dia(item.get("criado_em"))


def criar(con, dados: Mapping, *, por: str, agora: datetime | None = None,
          endpoints: Collection[str] | None = None) -> int:
    """Cadastra o item. Devolve o id. Código repetido é recusado. Vale do dia do cadastro."""
    agora = agora or datetime.now()
    n = normalizar(dados)
    erro = _conferir_tela(n, endpoints)
    if erro:
        raise RotinaError(erro)
    _conferir_pessoas(con, n)
    bd = banco(con)
    if bd.um(f"SELECT id FROM {TABELA} WHERE codigo = %s", (n["codigo"],)):
        raise RotinaError(f"Já existe rotina com o código {n['codigo']}: escolha outro, ou "
                          "edite a que existe.")
    colunas = list(CAMPOS) + ["vale_desde", "criado_em", "criado_por"]
    valores = [n[c] for c in CAMPOS] + [agora.date().isoformat(), _agora(agora), por]
    linhas = bd.escrever(
        f"INSERT INTO {TABELA} ({', '.join(colunas)}) VALUES "
        f"({', '.join(['%s'] * len(colunas))}) RETURNING id", tuple(valores))
    return int(linhas[0]["id"])


def _o_que_mudou(atual: Mapping, novo: Mapping, campos: Iterable[str]) -> list[str]:
    def igual(a, b):
        return (a if a not in ("",) else None) == (b if b not in ("",) else None) or a == b
    return [c for c in campos if not igual(atual.get(c), novo.get(c))]


def atualizar(con, rotina_id: int, dados: Mapping, *, por: str,
              agora: datetime | None = None, endpoints: Collection[str] | None = None) -> list[str]:
    """Muda o item. Devolve os campos que mudaram (vazio: nada mudou, nada grava).

    O que não vem em `dados` fica como está. O código não muda: é a chave da
    carga em lote, e trocá-lo faria a carga seguinte criar outro item.
    """
    atual = uma(con, rotina_id)
    if not atual:
        raise RotinaError("Rotina não encontrada.")
    codigo = _uma_linha(dados.get("codigo")).upper() if "codigo" in dados else atual["codigo"]
    if codigo != atual["codigo"]:
        raise RotinaError("O código da rotina não muda (é a chave da carga em lote). "
                          "Para outro código, cadastre outra e desative esta.")
    junto = {c: atual[c] for c in CAMPOS}
    junto.update({c: v for c, v in dados.items() if c in CAMPOS})
    junto["codigo"] = atual["codigo"]
    n = normalizar(junto)
    erro = _conferir_tela(n, endpoints)
    if erro:
        raise RotinaError(erro)
    _conferir_pessoas(con, n)
    mudou = _o_que_mudou(atual, n, [c for c in CAMPOS if c != "codigo"])
    if not mudou:
        return []
    banco(con).escrever(
        f"UPDATE {TABELA} SET {', '.join(f'{c} = %s' for c in mudou)}, "
        f"atualizado_em = %s, atualizado_por = %s WHERE id = %s",
        tuple(n[c] for c in mudou) + (_agora(agora), por, int(rotina_id)))
    return mudou


def desativar(con, rotina_id: int, *, por: str, motivo: str,
              agora: datetime | None = None) -> dict:
    """Tira o item da rotina, com motivo. Devolve {gravou, codigo}. Nada se apaga."""
    atual = uma(con, rotina_id)
    if not atual:
        raise RotinaError("Rotina não encontrada.")
    texto = _uma_linha(motivo)
    if len(texto) < MOTIVO_MINIMO:
        raise RotinaError("Diga em poucas palavras por que esta rotina sai: o motivo é "
                          "obrigatório.")
    if len(texto) > MOTIVO_MAXIMO:
        raise RotinaError(f"O motivo é um texto curto: até {MOTIVO_MAXIMO} letras.")
    if not int(atual["ativo"] or 0):
        return {"gravou": False, "codigo": atual["codigo"]}
    banco(con).escrever(
        f"UPDATE {TABELA} SET ativo = 0, motivo_desativacao = %s, atualizado_em = %s, "
        f"atualizado_por = %s WHERE id = %s", (texto, _agora(agora), por, int(rotina_id)))
    return {"gravou": True, "codigo": atual["codigo"], "motivo": texto}


def reativar(con, rotina_id: int, *, por: str, agora: datetime | None = None) -> dict:
    """Devolve o item à rotina, valendo de hoje: o tempo desativado não se cobra.
    Devolve {gravou, codigo, motivo_anterior, vale_desde}."""
    agora = agora or datetime.now()
    atual = uma(con, rotina_id)
    if not atual:
        raise RotinaError("Rotina não encontrada.")
    if int(atual["ativo"] or 0):
        return {"gravou": False, "codigo": atual["codigo"]}
    banco(con).escrever(
        f"UPDATE {TABELA} SET ativo = 1, motivo_desativacao = NULL, vale_desde = %s, "
        f"atualizado_em = %s, atualizado_por = %s WHERE id = %s",
        (agora.date().isoformat(), _agora(agora), por, int(rotina_id)))
    return {"gravou": True, "codigo": atual["codigo"],
            "motivo_anterior": atual["motivo_desativacao"],
            "vale_desde": agora.date().isoformat()}


def importar(con, itens: list[dict], *, por: str, agora: datetime | None = None,
             endpoints: Collection[str] | None = None) -> dict:
    """A carga em lote, idempotente pelo `codigo`. Ou grava tudo, ou nada.

    Cada item é um dict com os campos de `CAMPOS_DA_CARGA`: o responsável e o
    suplente vêm pelo LOGIN (`responsavel`, `suplente`); listas podem vir como
    lista ou texto («1,3»), e o `como_fazer`, como lista de passos ou texto de
    um passo por linha. No item NOVO, o campo ausente vale o padrão; no item
    que JÁ EXISTE, só o que veio se compara e grava (para apagar, mande vazio).
    O item que existe DESATIVADO não se mexe nem se reativa: vai para
    `inativos`. Com `endpoints` (as telas que existem), `onde_endpoint` tem de
    estar entre elas. Campo desconhecido, login inexistente, inativo, de robô
    ou de auditor e código repetido no lote são recusados — com todos os
    defeitos de uma vez, sem gravar nada.

    Devolve {"criados": [(codigo, id)], "atualizados": [(codigo, id)],
    "iguais": [(codigo, id)], "inativos": [(codigo, id)],
    "campos": {codigo: [campos que mudaram]}}. A auditoria fica com quem
    chama — ou use `importar_e_auditar`.
    """
    problemas: list[str] = []
    planos: list[tuple[str, dict, dict | None]] = []
    vistos: set[str] = set()
    logins: dict[str, int | None] = {}
    bd = banco(con)
    for i, bruto in enumerate(itens or [], start=1):
        if not isinstance(bruto, Mapping):
            problemas.append(f"Item {i}: não é um registro (dict).")
            continue
        codigo = _uma_linha(bruto.get("codigo")).upper()
        rotulo = f"Item {i} ({codigo or 'sem código'})"
        estranhos = sorted(set(bruto) - set(CAMPOS_DA_CARGA))
        if estranhos:
            problemas.append(f"{rotulo}: campo desconhecido: {', '.join(estranhos)}.")
            continue
        if codigo in vistos:
            problemas.append(f"{rotulo}: o código se repete no lote.")
            continue
        vistos.add(codigo)
        dados = {c: v for c, v in bruto.items() if c not in ("responsavel", "suplente")}
        for chave, campo, papel in (("responsavel", "responsavel_id", "responsável"),
                                    ("suplente", "suplente_id", "suplente")):
            if chave not in bruto:
                continue
            login = _uma_linha(bruto.get(chave))
            if not login:
                dados[campo] = None
                continue
            if login.lower() not in logins:
                linha = _pessoa(con, login=login)
                erro = _conferir_pessoa(linha, f"o login «{login}»", papel)
                if erro:
                    problemas.append(f"{rotulo}: {erro}")
                    logins[login.lower()] = None
                    continue
                logins[login.lower()] = int(linha["id"])
            if logins[login.lower()] is None:
                problemas.append(f"{rotulo}: {papel} «{login}» não serve (veja acima).")
                continue
            dados[campo] = logins[login.lower()]
        atual = None
        if codigo and bd.tem_tabela(TABELA):
            achado = bd.um(f"SELECT id FROM {TABELA} WHERE codigo = %s", (codigo,))
            atual = uma(con, achado["id"]) if achado else None
        junto = dict(_PADRAO) if atual is None else {c: atual[c] for c in CAMPOS}
        junto.update(dados)
        try:
            n = normalizar(junto)
            erro = _conferir_tela(n, endpoints)
            if erro:
                raise RotinaError(erro)
            if atual is None or int(atual["ativo"] or 0):
                _conferir_pessoas(con, n)     # o responsável que já estava pode ter saído
        except RotinaError as erro:
            problemas.extend(f"{rotulo}: {p}" for p in erro.problemas)
            continue
        planos.append((codigo, n, atual))
    if problemas:
        raise RotinaError(problemas)

    saida: dict[str, Any] = {"criados": [], "atualizados": [], "iguais": [], "inativos": [],
                             "campos": {}}
    for codigo, n, atual in planos:
        if atual is None:
            saida["criados"].append((codigo, criar(con, n, por=por, agora=agora)))
            continue
        if not int(atual["ativo"] or 0):
            saida["inativos"].append((codigo, int(atual["id"])))
            continue
        mudou = atualizar(con, atual["id"], n, por=por, agora=agora)
        if mudou:
            saida["atualizados"].append((codigo, int(atual["id"])))
            saida["campos"][codigo] = mudou
        else:
            saida["iguais"].append((codigo, int(atual["id"])))
    return saida


def importar_e_auditar(db, itens: list[dict], *, por: str, agente: str, a_mando_de: str,
                       origem: str, endpoints: Collection[str] | None = None,
                       agora: datetime | None = None) -> dict:
    """A carga do agente: `importar` numa transação, e a auditoria de cada item.

    Grava ROTINA_CRIADA e ROTINA_ALTERADA por `db.log`, sem usuário logado
    (`agente` e `a_mando_de` dizem quem age e a mando de quem), com a origem
    da carga, o código, o título, a área, a periodicidade e, na alteração, os
    campos. A auditoria vem depois do COMMIT (`db.log` abre a sua conexão).
    Devolve o mesmo dicionário de `importar`.
    """
    with db.transaction() as con:
        resultado = importar(con, itens, por=por, agora=agora, endpoints=endpoints)
        linhas = {rid: uma(con, rid)
                  for _, rid in resultado["criados"] + resultado["atualizados"]}
    for acao, chave in (("ROTINA_CRIADA", "criados"), ("ROTINA_ALTERADA", "atualizados")):
        for codigo, rid in resultado[chave]:
            linha = linhas.get(rid) or {}
            detalhes = {"origem": origem, "codigo": codigo, "titulo": linha.get("titulo"),
                        "area": linha.get("area"), "periodicidade": linha.get("periodicidade")}
            if acao == "ROTINA_ALTERADA":
                detalhes["campos"] = resultado["campos"].get(codigo, [])
            db.log(None, por, acao, TABELA, rid, detalhes, agente=agente, a_mando_de=a_mando_de)
    return resultado


# ------------------------------------------------------------------ o dia


def pode_marcar(item: Mapping, papel: str, usuario_id: int | None) -> bool:
    """Esta pessoa marca «feito» neste item? `papel` é o efetivo. Só calcula."""
    papel = str(papel or "").upper()
    if papel in QUEM_SO_VE:
        return False
    if papel in QUEM_MARCA_TUDO:
        return True
    return bool(usuario_id) and int(usuario_id) in {
        int(x) for x in (item.get("responsavel_id"), item.get("suplente_id")) if x}


def _feitos(con, limites: dict[int, date]) -> dict[int, list[dict]]:
    """Os «feitos» de cada item com referência a partir do limite dele. SÓ LÊ."""
    bd = banco(con)
    if not limites or not bd.tem_tabela(TABELA_FEITOS):
        return {}
    menor = min(limites.values())
    linhas = bd.ler(
        f"""SELECT id, rotina_id, referencia, prazo, com_atraso, feito_em, feito_por, usuario_id,
                   resultado, observacao FROM {TABELA_FEITOS}
             WHERE rotina_id = ANY(%s) AND referencia >= %s ORDER BY id""",
        (sorted(limites), menor.isoformat()))
    saida: dict[int, list[dict]] = {}
    for r in linhas:
        rid = int(r["rotina_id"])
        ref = _dia(r["referencia"])
        if ref is None or ref < limites[rid]:
            continue
        saida.setdefault(rid, []).append({
            "id": int(r["id"]), "referencia": ref, "por": r["feito_por"],
            "em": str(r["feito_em"])[:16], "resultado": r["resultado"],
            "resultado_rotulo": ROTULO_DO_RESULTADO.get(r["resultado"], r["resultado"]),
            "observacao": r["observacao"] or "", "usuario_id": r["usuario_id"],
            "com_atraso": bool(int(r["com_atraso"] or 0)), "anexos": []})
    por_id = {f["id"]: f for lista in saida.values() for f in lista}
    if por_id and bd.tem_tabela("attachments"):
        for a in bd.ler("SELECT id, entity_id, original_name FROM attachments "
                        "WHERE entity_type = %s AND entity_id = ANY(%s) ORDER BY id",
                        (TIPO_DO_ANEXO, sorted(por_id))):
            por_id[int(a["entity_id"])]["anexos"].append(
                {"id": int(a["id"]), "nome": a["original_name"]})
    return saida


def _feito_de(item: Mapping, nominal: date, feitos: list[dict]) -> dict | None:
    """O «feito» que cumpre este vencimento: o do mesmo período, ou o da mesma data."""
    faixa = periodo(item, nominal)
    for f in feitos:
        if faixa and faixa[0] <= f["referencia"] <= faixa[1]:
            return f
        if not faixa and f["referencia"] == nominal:
            return f
    return None


def _para_tela(r: Mapping) -> dict:
    """O item como a tela o mostra (sem situação). Só calcula."""
    return {
        "id": int(r["id"]), "codigo": r["codigo"], "area": r["area"],
        "area_rotulo": ROTULO_DA_AREA.get(r["area"], r["area"]),
        "titulo": r["titulo"], "para_que": r["para_que"] or "",
        "passos": passos(r["como_fazer"]), "pronto_quando": r["pronto_quando"] or "",
        "se_der_errado": r["se_der_errado"] or "", "prova": r["prova"] or "",
        "onde_endpoint": r["onde_endpoint"] or None, "onde_url": r["onde_url"] or None,
        "base_legal": r["base_legal"] or "",
        "periodicidade": r["periodicidade"],
        "periodicidade_rotulo": ROTULO_DA_PERIODICIDADE.get(r["periodicidade"], r["periodicidade"]),
        "quando": descrever_quando(r), "horario": r["horario"] or "",
        "responsavel_id": r["responsavel_id"], "suplente_id": r["suplente_id"],
        "responsavel": r.get("responsavel_nome"), "suplente": r.get("suplente_nome"),
        "responsavel_ativo": bool(r.get("responsavel_ativo")) if r["responsavel_id"] else None,
        "suplente_ativo": bool(r.get("suplente_ativo")) if r["suplente_id"] else None,
        "prioridade": int(r["prioridade"] or 2),
        "prioridade_rotulo": ROTULO_DA_PRIORIDADE.get(int(r["prioridade"] or 2), ""),
        "ordem": int(r["ordem"] or 0), "ativo": bool(int(r["ativo"] or 0)),
        "motivo_desativacao": r["motivo_desativacao"] or "",
        "vale_desde": (_vale_desde(r) or date.today()).isoformat(),
    }


def _dd_mm(dia: date) -> str:
    return f"{dia:%d/%m}"


def do_dia(con, hoje: date | str, *, area: str | None = None,
           usuario_id: int | None = None, agora: datetime | None = None) -> list[dict]:
    """Os itens do dia: o vencimento atual sem «feito» e o que faltou. SÓ LÊ.

    Cada item traz o vencimento atual — `referencia` (a data nominal, que o
    «feito» guarda) e `prazo` —, a `situacao` (ATRASADO, HOJE ou FEITO), o
    `feito` dele (ou None), as `faltas` (as datas nominais sem «feito» dos
    últimos `JANELA_DAS_FALTAS` dias, nunca antes de `vale_desde`) e as
    `referencias_marcaveis` [(data, rótulo)] que o «Feito» aceita. Item cujo
    primeiro vencimento ainda não chegou não aparece. `area` filtra a área;
    `usuario_id`, os itens de que a pessoa é responsável ou suplente (0 não é
    «todos»). `agora` decide o «até HH:MM» do dia (padrão: o relógio, quando
    `hoje` é hoje). No banco em que a tabela ainda não existe, a lista vem
    vazia — e o GET não a cria.
    """
    hoje = _dia(hoje) or date.today()
    agora = agora or datetime.now()
    onde, parametros = ["r.ativo = 1"], []
    if area:
        onde.append("r.area = %s")
        parametros.append(area)
    if usuario_id is not None:
        onde.append("(r.responsavel_id = %s OR r.suplente_id = %s)")
        parametros += [int(usuario_id), int(usuario_id)]
    linhas = _ler(con, " AND ".join(onde), tuple(parametros))
    if not linhas:
        return []
    feriados = feriados_da_casa(con)
    inicio_faltas = hoje - timedelta(days=JANELA_DAS_FALTAS)
    planos, limites = [], {}
    for r in linhas:
        vale = _vale_desde(r) or hoje
        atual = ocorrencia_atual(r, hoje, feriados=feriados, desde=vale)
        if atual is None:
            continue
        janela = [o for o in ocorrencias(r, max(vale, inicio_faltas), hoje, feriados=feriados)
                  if o != atual]
        nominais = [atual[0]] + [o[0] for o in janela]
        menor = min(periodo(r, d)[0] if por_periodo(r) else d for d in nominais)
        planos.append((r, vale, atual, janela))
        limites[int(r["id"])] = menor
    feitos = _feitos(con, limites)
    saida = []
    for r, vale, (nominal, prazo), janela in planos:
        do_item = feitos.get(int(r["id"]), [])
        feito = _feito_de(r, nominal, do_item)
        faltas = [nom for nom, _ in janela if not _feito_de(r, nom, do_item)]
        limite = limite_do_horario(r["horario"])
        passou_da_hora = bool(limite and prazo == hoje and agora.date() == hoje
                              and agora.time() > limite)
        if feito:
            situacao = FEITO
            fica = (prazo == hoje or _dia(feito["em"]) == hoje
                    or feito["resultado"] == COM_PENDENCIA or faltas)
            if not fica:
                continue
        elif prazo < hoje or passou_da_hora:
            situacao = ATRASADO
        else:
            situacao = HOJE
        marcaveis = [] if feito else [(nominal.isoformat(), f"{_dd_mm(nominal)} (deste vencimento)")]
        marcaveis += [(d.isoformat(), f"{_dd_mm(d)} (sem registro)") for d in reversed(faltas)]
        item = _para_tela(r)
        item.update(referencia=nominal.isoformat(), prazo=prazo.isoformat(), situacao=situacao,
                    feito=feito, dias_de_atraso=(hoje - prazo).days if situacao == ATRASADO else 0,
                    limite_hora=f"{limite:%H:%M}" if limite else None,
                    passou_da_hora=passou_da_hora,
                    faltas=[d.isoformat() for d in faltas], n_sem_registro=len(faltas),
                    sem_registro_desde=faltas[0].isoformat() if faltas else None,
                    referencias_marcaveis=marcaveis)
        saida.append(item)
    saida.sort(key=lambda x: (ORDEM_DA_SITUACAO.index(x["situacao"]), x["prioridade"],
                              x["ordem"], x["titulo"], x["id"]))
    return saida


def por_area(itens: list[dict]) -> dict[str, list[dict]]:
    """Os itens agrupados pela área, na ordem das áreas. Só calcula."""
    grupos: dict[str, list[dict]] = {}
    for x in itens:
        grupos.setdefault(x["area"], []).append(x)
    return {a: grupos[a] for a, _ in AREAS if a in grupos}


def marcar_feito(con, rotina_id: int, referencia: str, *, resultado: str, observacao: str,
                 por: str, usuario_id: int | None, agora: datetime | None = None,
                 papel: str | None = None) -> dict:
    """Registra o «feito» de um vencimento. Devolve {gravou, id, por, em, ...}.

    `referencia` é a data NOMINAL do vencimento: a atual ou uma das sem
    registro dos últimos `JANELA_DAS_FALTAS` dias, nunca antes de `vale_desde`.
    O primeiro registro do vencimento (ou do período, no item de um vencimento
    por período) fica: o segundo devolve `gravou=False` com quem já
    registrou. COM_PENDENCIA e NAO_SE_APLICA exigem observação. O registro
    depois do prazo (ou da hora do «até HH:MM») fica marcado `com_atraso`.
    Com `papel` (o efetivo), confere também se a pessoa marca este item.
    """
    agora = agora or datetime.now()
    hoje = agora.date()
    item = uma(con, rotina_id)
    if not item:
        raise RotinaError("Rotina não encontrada.")
    if not int(item["ativo"] or 0):
        raise RotinaError("Esta rotina está desativada: não se marca «feito» nela.")
    if papel is not None and not pode_marcar(item, papel, usuario_id):
        raise RotinaSemPermissao("Marca esta rotina quem responde por ela (o responsável ou o "
                                 "suplente), o oficial ou o gerente.")
    ref = _dia(referencia)
    if ref is None or str(referencia or "")[:10] != ref.isoformat():
        raise RotinaError("A data do vencimento não se lê.")
    vale = _vale_desde(item) or hoje
    if ref > hoje:
        raise RotinaError("Não se marca «feito» num vencimento que ainda não chegou.")
    feriados = feriados_da_casa(con)
    marcaveis: dict[date, date] = {}
    atual = ocorrencia_atual(item, hoje, feriados=feriados, desde=vale)
    if atual:
        marcaveis[atual[0]] = atual[1]
    for nominal, prazo in ocorrencias(item, max(vale, hoje - timedelta(days=JANELA_DAS_FALTAS)),
                                      hoje, feriados=feriados):
        marcaveis.setdefault(nominal, prazo)
    if ref not in marcaveis:
        if ref < vale:
            raise RotinaError(f"{ref:%d/%m/%Y} é anterior a {vale:%d/%m/%Y}, quando esta rotina "
                              "passou a valer: não se marca.")
        raise RotinaError(f"{ref:%d/%m/%Y} não é um vencimento que se marque aqui: só o atual "
                          f"e os sem registro dos últimos {JANELA_DAS_FALTAS} dias.")
    resultado = _uma_linha(resultado).upper()
    if resultado not in ROTULO_DO_RESULTADO:
        raise RotinaError("Escolha o resultado: " + ", ".join(ROTULO_DO_RESULTADO.values()) + ".")
    texto = _varias_linhas(observacao)
    if resultado != OK and len(texto) < OBSERVACAO_MINIMA:
        raise RotinaError(f"Em «{ROTULO_DO_RESULTADO[resultado]}», diga em poucas palavras o que "
                          "aconteceu: a observação é obrigatória.")
    if len(texto) > OBSERVACAO_MAXIMA:
        raise RotinaError(f"A observação é curta: até {OBSERVACAO_MAXIMA} letras.")
    bd = banco(con)
    colunas = "id, referencia, prazo, com_atraso, feito_em, feito_por, resultado, observacao"
    faixa = periodo(item, ref)
    ja = (bd.um(f"""SELECT {colunas} FROM {TABELA_FEITOS} WHERE rotina_id = %s
                     AND referencia BETWEEN %s AND %s ORDER BY id LIMIT 1""",
                (int(rotina_id), faixa[0].isoformat(), faixa[1].isoformat())) if faixa else None)
    prazo = marcaveis[ref]
    limite = limite_do_horario(item["horario"])
    com_atraso = hoje > prazo or bool(limite and hoje == prazo and agora.time() > limite)
    novo = []
    if not ja:
        novo = bd.escrever(
            f"""INSERT INTO {TABELA_FEITOS} (rotina_id, referencia, prazo, com_atraso, feito_em,
                                             feito_por, usuario_id, resultado, observacao)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (rotina_id, referencia) DO NOTHING RETURNING id""",
            (int(rotina_id), ref.isoformat(), prazo.isoformat(), int(com_atraso), _agora(agora),
             por, usuario_id, resultado, texto))
        ja = bd.um(f"SELECT {colunas} FROM {TABELA_FEITOS} WHERE rotina_id = %s "
                   "AND referencia = %s", (int(rotina_id), ref.isoformat()))
    return {"gravou": bool(novo), "id": int(ja["id"]), "codigo": item["codigo"],
            "titulo": item["titulo"], "referencia": str(ja["referencia"]),
            "prazo": str(ja["prazo"] or ""), "com_atraso": bool(int(ja["com_atraso"] or 0)),
            "por": ja["feito_por"], "em": str(ja["feito_em"])[:16],
            "resultado": ja["resultado"], "observacao": ja["observacao"] or ""}


# ------------------------------------------------------------------ as listas


def proximo_prazo(con, item: Mapping, hoje: date | str | None = None) -> date | None:
    """O prazo do próximo vencimento que o item cobra (de hoje e de `vale_desde`
    em diante). SÓ LÊ."""
    hoje = _dia(hoje) or date.today()
    proxima = proxima_ocorrencia(item, hoje, feriados=feriados_da_casa(con),
                                 desde=_vale_desde(item))
    return proxima[1] if proxima else None


def listar(con, hoje: date | str | None = None, *, area: str | None = None,
           busca: str | None = None, ativas: bool = True) -> list[dict]:
    """O cadastro para a tela: por área e periodicidade, com o próximo
    vencimento e o último «feito». SÓ LÊ."""
    hoje = _dia(hoje) or date.today()
    onde, parametros = ["r.ativo = %s"], [1 if ativas else 0]
    if area:
        onde.append("r.area = %s")
        parametros.append(area)
    termo = _uma_linha(busca)
    if termo:
        onde.append("(r.codigo ILIKE %s OR r.titulo ILIKE %s OR r.para_que ILIKE %s "
                    "OR r.como_fazer ILIKE %s)")
        parametros += [f"%{termo}%"] * 4
    linhas = _ler(con, " AND ".join(onde), tuple(parametros))
    if not linhas:
        return []
    feriados = feriados_da_casa(con)
    ultimos = {}
    bd = banco(con)
    if bd.tem_tabela(TABELA_FEITOS):
        for f in bd.ler(
                f"""SELECT DISTINCT ON (rotina_id) rotina_id, referencia, feito_em, feito_por,
                           resultado, com_atraso FROM {TABELA_FEITOS} WHERE rotina_id = ANY(%s)
                     ORDER BY rotina_id, referencia DESC, id DESC""",
                ([int(r["id"]) for r in linhas],)):
            ultimos[int(f["rotina_id"])] = {
                "referencia": f["referencia"], "em": str(f["feito_em"])[:16],
                "por": f["feito_por"], "com_atraso": bool(int(f["com_atraso"] or 0)),
                "resultado_rotulo": ROTULO_DO_RESULTADO.get(f["resultado"], f["resultado"])}
    ordem_per = [p for p, _ in PERIODICIDADES]
    saida = []
    for r in linhas:
        item = _para_tela(r)
        proxima = (proxima_ocorrencia(r, hoje, feriados=feriados, desde=_vale_desde(r))
                   if item["ativo"] else None)
        item.update(proximo=proxima[1].isoformat() if proxima else None,
                    ultimo_feito=ultimos.get(int(r["id"])),
                    criado_em=str(r["criado_em"])[:16], criado_por=r["criado_por"],
                    atualizado_em=str(r["atualizado_em"] or "")[:16] or None,
                    atualizado_por=r["atualizado_por"])
        saida.append(item)
    ordem_area = [a for a, _ in AREAS]
    saida.sort(key=lambda x: (ordem_area.index(x["area"]) if x["area"] in ordem_area else 99,
                              ordem_per.index(x["periodicidade"])
                              if x["periodicidade"] in ordem_per else 99,
                              x["ordem"], x["prioridade"], x["titulo"], x["id"]))
    return saida


def da_pessoa(con, usuario_id: int, hoje: date | str | None = None) -> list[dict]:
    """Toda a rotina ativa de que a pessoa é responsável ou suplente, com o
    próximo vencimento. SÓ LÊ."""
    hoje = _dia(hoje) or date.today()
    linhas = _ler(con, "r.ativo = 1 AND (r.responsavel_id = %s OR r.suplente_id = %s)",
                  (int(usuario_id), int(usuario_id)))
    feriados = feriados_da_casa(con) if linhas else set()
    saida = []
    for r in linhas:
        item = _para_tela(r)
        proxima = proxima_ocorrencia(r, hoje, feriados=feriados, desde=_vale_desde(r))
        item["proximo"] = proxima[1].isoformat() if proxima else None
        item["sou"] = "responsável" if r["responsavel_id"] == int(usuario_id) else "suplente"
        saida.append(item)
    saida.sort(key=lambda x: (x["proximo"] or "9999", x["prioridade"], x["titulo"]))
    return saida


def pessoas(con) -> list[dict]:
    """Quem pode responder por uma rotina: as pessoas ativas, sem robô e sem
    auditor. SÓ LÊ."""
    return banco(con).ler(
        "SELECT id, username, full_name FROM users WHERE active = 1 "
        "AND COALESCE(eh_robo, 0) = 0 AND UPPER(COALESCE(role, '')) <> ALL(%s) "
        "ORDER BY full_name COLLATE public.cg_nocase, id", (list(QUEM_SO_VE),))


def pessoa_do_formulario(con, uid: Any) -> dict | None:
    """A pessoa que o item já tem e não está em `pessoas` (inativa, auditor ou
    robô): ela aparece no formulário marcada, para o servidor pedir outra em
    vez de apagá-la calado. SÓ LÊ."""
    try:
        uid = int(str(uid).strip())
    except (TypeError, ValueError):
        return None
    linha = _pessoa(con, uid=uid)
    if not linha:
        return None
    motivo = _conferir_pessoa(linha, "", "")
    if not motivo:
        return None
    if not int(linha["active"] or 0):
        marca = "inativo"
    elif str(linha.get("role") or "").upper() in QUEM_SO_VE:
        marca = "auditor"
    else:
        marca = "robô"
    return {"id": int(linha["id"]), "username": linha["username"],
            "full_name": linha["full_name"], "marca": marca}


def contar(con, *, ativas: bool = True) -> int:
    """Quantos itens ativos (ou desativados) o cadastro tem (0 sem a tabela). SÓ LÊ."""
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return 0
    return int(bd.valor(f"SELECT count(*) FROM {TABELA} WHERE ativo = %s",
                        (1 if ativas else 0,)) or 0)

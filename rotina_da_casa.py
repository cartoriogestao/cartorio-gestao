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

QUANDO VENCE (`vencimentos`)
    DIARIA      todo dia útil.
    SEMANAL     nos dias da semana de `dias_semana` (ISO: 1 = segunda … 7 = domingo).
    QUINZENAL   nos dois dias do mês de `dias_mes` ('5,20').
    MENSAL      nos dias de `dias_mes`, OU no Nº dia útil `dia_util` do mês
                (negativo conta do fim: -1 é o último dia útil).
    TRIMESTRAL, SEMESTRAL, ANUAL
                nos meses de `meses` (4, 2 e 1 deles), no dia de `dias_mes` ou
                no Nº dia útil `dia_util`.
    O dia certo do mês (ou da semana) que cai em sábado, domingo ou feriado
    passa para o dia útil seguinte, como o prazo; o dia 31 em mês de 30 dias
    vale o último dia do mês, e o 20º dia útil num mês que tem 19 vale o
    último. O calendário é o da casa: os feriados nacionais (`ri_schema`) e
    os locais de Configurações (`ri_feriados_locais`), os mesmos do RI, do
    Protesto e do gestor. O campo que não é da periodicidade escolhida fica
    vazio (o «semanal» não guarda dia do mês).

O QUE APARECE NO DIA (`do_dia`)
    Cada item ativo aparece desde o seu último vencimento até alguém marcar
    «Feito» para ele: no dia em que vence, «a fazer»; depois, «atrasado desde
    dd/mm». O «feito» fica à vista no dia em que foi registrado; o «feito com
    pendência» fica até o vencimento seguinte, para a pendência não sumir
    calada. O vencimento anterior ao cadastro do item não acusa atraso: o
    item aparece «a fazer» (o deste período), e não «atrasado».

«FEITO» (`marcar_feito`)
    Grava quem, quando, o resultado (OK, com pendência, não se aplica) e a
    observação, que é obrigatória fora do OK. O primeiro registro de cada
    vencimento fica, como o «conferido hoje»: o segundo clique só é avisado de
    quem já registrou. Marca o responsável, o suplente, o oficial e o gerente;
    o auditor vê e não grava (M2). A prova em arquivo vai em `attachments`.

A CARGA EM LOTE (`importar`)
    É a porta do agente 11: idempotente pelo `codigo`. Cria o que falta,
    atualiza o que mudou e diz o que já estava igual; o responsável e o
    suplente chegam como LOGIN. Ou entra tudo, ou nada: um item com defeito
    devolve todos os defeitos e não grava nenhum.

SÓ DOMÍNIO
    Nada aqui conhece o Flask: a rota (`rotina_da_casa_web`) liga os fios e
    grava a auditoria. Erro de regra é `RotinaError`, com a frase pronta.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

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
#: Quantos meses do ano cada periodicidade «de meses» escolhe.
MESES_DA_PERIODICIDADE = {"TRIMESTRAL": 4, "SEMESTRAL": 2, "ANUAL": 1}

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
ATRASADO, HOJE, DESDE_O_CADASTRO, FEITO = "ATRASADO", "HOJE", "DESDE_O_CADASTRO", "FEITO"
ORDEM_DA_SITUACAO = (ATRASADO, HOJE, DESDE_O_CADASTRO, FEITO)

#: Quem cadastra, edita, desativa e reativa (o TI passa como o ADMIN, `papeis`).
QUEM_CADASTRA = ("ADMIN", "MANAGER")
#: Quem abre o cadastro: o auditor lê e não grava (M2).
QUEM_VE_O_CADASTRO = ("ADMIN", "MANAGER", "AUDITOR")
#: Quem marca «feito» em qualquer item; os outros, só no item de que respondem.
QUEM_MARCA_TUDO = ("ADMIN", "MANAGER")
#: Quem nunca marca, nem no item em que está como responsável.
QUEM_SO_VE = ("AUDITOR",)

#: Até onde se procura o último vencimento: um ano e um pouco (o anual).
JANELA_DIAS = 400

MOTIVO_MINIMO, MOTIVO_MAXIMO = 3, 300
OBSERVACAO_MINIMA, OBSERVACAO_MAXIMA = 3, 1000
TITULO_MAXIMO, TEXTO_MAXIMO = 200, 8000

_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_.\-]{1,59}$")
_ENDPOINT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,99}$")
_NUMERACAO = re.compile(r"^\s*(?:\d{1,2}\s*[.)º°-]|[-•*])\s+")

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


def vencimentos(item: Mapping, de: date, ate: date, *,
                feriados: set[date] | None = None) -> list[date]:
    """Os dias em que o item vence entre `de` e `ate`, inclusive. Só calcula.

    `item` é a linha do cadastro (ou o dict normalizado): `periodicidade`,
    `dias_semana`, `dias_mes`, `dia_util` e `meses`. `feriados` são os locais
    (os nacionais `eh_dia_util` já conhece).
    """
    feriados = feriados or set()
    de, ate = _dia(de), _dia(ate)
    if de is None or ate is None or ate < de:
        return []
    periodicidade = str(item.get("periodicidade") or "").upper()
    achados: set[date] = set()
    if periodicidade == "DIARIA":
        dia = de
        while dia <= ate:
            if eh_dia_util(dia, feriados):
                achados.add(dia)
            dia += timedelta(days=1)
    elif periodicidade == "SEMANAL":
        semana = set(_numeros(item.get("dias_semana")))
        # o dia que cai em feriado anda para a frente: começa-se antes de `de`
        dia = de - timedelta(days=15)
        while dia <= ate:
            if dia.isoweekday() in semana:
                achados.add(_util_a_partir(dia, feriados))
            dia += timedelta(days=1)
    elif periodicidade in ("QUINZENAL", "MENSAL") or periodicidade in MESES_DA_PERIODICIDADE:
        meses = (set(range(1, 13)) if periodicidade in ("QUINZENAL", "MENSAL")
                 else set(_numeros(item.get("meses"))))
        dias = _numeros(item.get("dias_mes"))
        dia_util = item.get("dia_util")
        dia_util = int(dia_util) if dia_util not in (None, "") else None
        inicio = de - timedelta(days=40)
        ano, mes = inicio.year, inicio.month
        while (ano, mes) <= (ate.year, ate.month):
            if mes in meses:
                if dia_util:
                    certo = _n_esimo_dia_util(ano, mes, dia_util, feriados)
                    if certo:
                        achados.add(certo)
                else:
                    ultimo = _ultimo_dia_do_mes(ano, mes)
                    for d in dias:
                        achados.add(_util_a_partir(date(ano, mes, min(d, ultimo)), feriados))
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return sorted(d for d in achados if de <= d <= ate)


#: As janelas em que se procura o vencimento, da menor para a maior: o diário
#: acha na primeira, e só o anual precisa da última.
_JANELAS = (10, 45, JANELA_DIAS)


def ultimo_vencimento(item: Mapping, hoje: date, *, feriados: set[date] | None = None) -> date | None:
    """O vencimento mais recente até hoje, inclusive. Só calcula."""
    hoje = _dia(hoje)
    for janela in _JANELAS:
        lista = vencimentos(item, hoje - timedelta(days=janela), hoje, feriados=feriados)
        if lista:
            return lista[-1]
    return None


def proximo_vencimento(item: Mapping, hoje: date, *, feriados: set[date] | None = None) -> date | None:
    """O próximo vencimento a partir de hoje, inclusive. Só calcula."""
    hoje = _dia(hoje)
    for janela in _JANELAS:
        lista = vencimentos(item, hoje, hoje + timedelta(days=janela), feriados=feriados)
        if lista:
            return lista[0]
    return None


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
    dia_util = item.get("dia_util")
    dia_util = int(dia_util) if dia_util not in (None, "") else None
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
    if horario and len(horario) > 40:
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
            quantos = MESES_DA_PERIODICIDADE[per]
            if not meses or len(meses.split(",")) != quantos:
                problemas.append(f"Na rotina {ROTULO_DA_PERIODICIDADE[per].lower()}, marque "
                                 f"{quantos} {'mês' if quantos == 1 else 'meses'} do ano.")
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
    if uid is not None:
        return bd.um("SELECT id, username, full_name, active, COALESCE(eh_robo, 0) AS eh_robo "
                     "FROM users WHERE id = %s", (uid,))
    return bd.um("SELECT id, username, full_name, active, COALESCE(eh_robo, 0) AS eh_robo "
                 "FROM users WHERE username = %s", (login,))


def _conferir_pessoa(linha: dict | None, quem: str, papel: str) -> str | None:
    if not linha:
        return f"{papel.capitalize()}: {quem} não existe."
    if not int(linha["active"] or 0):
        return f"{papel.capitalize()}: {quem} está inativo."
    if int(linha["eh_robo"] or 0):
        return f"{papel.capitalize()}: {quem} é conta de robô; a rotina é de uma pessoa."
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


def criar(con, dados: Mapping, *, por: str, agora: datetime | None = None) -> int:
    """Cadastra o item. Devolve o id. Código repetido é recusado."""
    n = normalizar(dados)
    _conferir_pessoas(con, n)
    bd = banco(con)
    if bd.um(f"SELECT id FROM {TABELA} WHERE codigo = %s", (n["codigo"],)):
        raise RotinaError(f"Já existe rotina com o código {n['codigo']}: escolha outro, ou "
                          "edite a que existe.")
    colunas = list(CAMPOS) + ["criado_em", "criado_por"]
    valores = [n[c] for c in CAMPOS] + [_agora(agora), por]
    linhas = bd.escrever(
        f"INSERT INTO {TABELA} ({', '.join(colunas)}) VALUES "
        f"({', '.join(['%s'] * len(colunas))}) RETURNING id", tuple(valores))
    return int(linhas[0]["id"])


def _o_que_mudou(atual: Mapping, novo: Mapping, campos: Iterable[str]) -> list[str]:
    def igual(a, b):
        return (a if a not in ("",) else None) == (b if b not in ("",) else None) or a == b
    return [c for c in campos if not igual(atual.get(c), novo.get(c))]


def atualizar(con, rotina_id: int, dados: Mapping, *, por: str,
              agora: datetime | None = None) -> list[str]:
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
    """Devolve o item à rotina. Devolve {gravou, codigo, motivo_anterior}."""
    atual = uma(con, rotina_id)
    if not atual:
        raise RotinaError("Rotina não encontrada.")
    if int(atual["ativo"] or 0):
        return {"gravou": False, "codigo": atual["codigo"]}
    banco(con).escrever(
        f"UPDATE {TABELA} SET ativo = 1, motivo_desativacao = NULL, atualizado_em = %s, "
        f"atualizado_por = %s WHERE id = %s", (_agora(agora), por, int(rotina_id)))
    return {"gravou": True, "codigo": atual["codigo"],
            "motivo_anterior": atual["motivo_desativacao"]}


def importar(con, itens: list[dict], *, por: str, agora: datetime | None = None) -> dict:
    """A carga em lote, idempotente pelo `codigo`. Ou grava tudo, ou nada.

    Cada item é um dict com os campos de `CAMPOS_DA_CARGA`: o responsável e o
    suplente vêm pelo LOGIN (`responsavel`, `suplente`); listas podem vir como
    lista ou texto («1,3»), e o `como_fazer`, como lista de passos ou texto de
    um passo por linha. No item NOVO, o campo ausente vale o padrão; no item
    que JÁ EXISTE, só o que veio se compara e grava (para apagar, mande vazio).
    Campo desconhecido, login inexistente ou inativo e código repetido no
    lote são recusados — com todos os defeitos de uma vez, sem gravar nada.

    Devolve {"criados": [(codigo, id)], "atualizados": [(codigo, id)],
    "iguais": [(codigo, id)], "campos": {codigo: [campos que mudaram]}}.
    Quem chama grava a auditoria (ROTINA_CRIADA / ROTINA_ALTERADA).
    """
    problemas: list[str] = []
    planos: list[tuple[str, dict, dict | None]] = []
    vistos: set[str] = set()
    logins: dict[str, int | None] = {}
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
        bd = banco(con)
        if codigo and bd.tem_tabela(TABELA):
            achado = bd.um(f"SELECT id FROM {TABELA} WHERE codigo = %s", (codigo,))
            atual = uma(con, achado["id"]) if achado else None
        junto = dict(_PADRAO) if atual is None else {c: atual[c] for c in CAMPOS}
        junto.update(dados)
        try:
            n = normalizar(junto)
            _conferir_pessoas(con, n)     # o responsável que já estava pode ter saído
        except RotinaError as erro:
            problemas.extend(f"{rotulo}: {p}" for p in erro.problemas)
            continue
        planos.append((codigo, n, atual))
    if problemas:
        raise RotinaError(problemas)

    saida: dict[str, Any] = {"criados": [], "atualizados": [], "iguais": [], "campos": {}}
    for codigo, n, atual in planos:
        if atual is None:
            saida["criados"].append((codigo, criar(con, n, por=por, agora=agora)))
            continue
        mudou = atualizar(con, atual["id"], n, por=por, agora=agora)
        if mudou:
            saida["atualizados"].append((codigo, int(atual["id"])))
            saida["campos"][codigo] = mudou
        else:
            saida["iguais"].append((codigo, int(atual["id"])))
    return saida


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


def _feitos(con, pares: list[tuple[int, str]]) -> dict[tuple[int, str], dict]:
    bd = banco(con)
    if not pares or not bd.tem_tabela(TABELA_FEITOS):
        return {}
    ids = sorted({p[0] for p in pares})
    refs = sorted({p[1] for p in pares})
    linhas = bd.ler(
        f"""SELECT id, rotina_id, referencia, feito_em, feito_por, usuario_id, resultado,
                   observacao FROM {TABELA_FEITOS}
             WHERE rotina_id = ANY(%s) AND referencia = ANY(%s)""", (ids, refs))
    queridos = set(pares)
    saida = {}
    for r in linhas:
        chave = (int(r["rotina_id"]), str(r["referencia"]))
        if chave in queridos:
            saida[chave] = {"id": int(r["id"]), "por": r["feito_por"],
                            "em": str(r["feito_em"])[:16], "resultado": r["resultado"],
                            "resultado_rotulo": ROTULO_DO_RESULTADO.get(r["resultado"], r["resultado"]),
                            "observacao": r["observacao"] or "", "usuario_id": r["usuario_id"],
                            "anexos": []}
    if saida and bd.tem_tabela("attachments"):
        por_id = {f["id"]: f for f in saida.values()}
        for a in bd.ler("SELECT id, entity_id, original_name FROM attachments "
                        "WHERE entity_type = %s AND entity_id = ANY(%s) ORDER BY id",
                        (TIPO_DO_ANEXO, sorted(por_id))):
            por_id[int(a["entity_id"])]["anexos"].append(
                {"id": int(a["id"]), "nome": a["original_name"]})
    return saida


def _para_tela(r: Mapping, hoje: date) -> dict:
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
    }


def do_dia(con, hoje: date | str, *, area: str | None = None,
           usuario_id: int | None = None) -> list[dict]:
    """Os itens do dia: os que vencem hoje e os vencidos sem «feito». SÓ LÊ.

    Cada item traz `referencia` (o vencimento que se cumpre, AAAA-MM-DD),
    `situacao` (ATRASADO, HOJE, DESDE_O_CADASTRO ou FEITO), `feito` (quem,
    quando, resultado, observação e anexos, ou None) e `anterior_sem_registro`
    (o vencimento anterior que ficou sem «feito», ou None). `area` filtra a
    área; `usuario_id`, os itens de que a pessoa é responsável ou suplente.
    No banco em que a tabela ainda não existe, a lista vem vazia — e o GET
    não a cria.
    """
    hoje = _dia(hoje) or date.today()
    onde, parametros = ["r.ativo = 1"], []
    if area:
        onde.append("r.area = %s")
        parametros.append(area)
    if usuario_id:
        onde.append("(r.responsavel_id = %s OR r.suplente_id = %s)")
        parametros += [int(usuario_id), int(usuario_id)]
    linhas = _ler(con, " AND ".join(onde), tuple(parametros))
    if not linhas:
        return []
    feriados = feriados_da_casa(con)
    planos, pares = [], []
    for r in linhas:
        ref = ultimo_vencimento(r, hoje, feriados=feriados)
        if ref is None:
            continue
        anterior = ultimo_vencimento(r, ref - timedelta(days=1), feriados=feriados)
        planos.append((r, ref, anterior))
        pares.append((int(r["id"]), ref.isoformat()))
        if anterior:
            pares.append((int(r["id"]), anterior.isoformat()))
    feitos = _feitos(con, pares)
    saida = []
    for r, ref, anterior in planos:
        criado = _dia(r["criado_em"]) or hoje
        feito = feitos.get((int(r["id"]), ref.isoformat()))
        if feito:
            dia_do_feito = _dia(feito["em"])
            if not (ref == hoje or dia_do_feito == hoje or feito["resultado"] == COM_PENDENCIA):
                continue
            situacao = FEITO
        elif ref == hoje:
            situacao = HOJE
        elif ref < criado:
            situacao = DESDE_O_CADASTRO
        else:
            situacao = ATRASADO
        sem_registro = (anterior if anterior and anterior >= criado
                        and (int(r["id"]), anterior.isoformat()) not in feitos else None)
        item = _para_tela(r, hoje)
        item.update(referencia=ref.isoformat(), situacao=situacao, feito=feito,
                    dias_de_atraso=(hoje - ref).days if situacao == ATRASADO else 0,
                    anterior_sem_registro=sem_registro.isoformat() if sem_registro else None)
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

    O primeiro registro do vencimento fica: o segundo devolve `gravou=False`
    com quem já registrou. COM_PENDENCIA e NAO_SE_APLICA exigem observação.
    Com `papel` (o efetivo), confere também se a pessoa marca este item.
    """
    agora = agora or datetime.now()
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
    if ref > agora.date():
        raise RotinaError("Não se marca «feito» num vencimento que ainda não chegou.")
    if ref not in vencimentos(item, ref, ref, feriados=feriados_da_casa(con)):
        raise RotinaError(f"{ref:%d/%m/%Y} não é dia de vencimento desta rotina.")
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
    novo = bd.escrever(
        f"""INSERT INTO {TABELA_FEITOS} (rotina_id, referencia, feito_em, feito_por,
                                         usuario_id, resultado, observacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (rotina_id, referencia) DO NOTHING RETURNING id""",
        (int(rotina_id), ref.isoformat(), _agora(agora), por, usuario_id, resultado, texto))
    linha = bd.um(f"""SELECT id, feito_em, feito_por, resultado, observacao FROM {TABELA_FEITOS}
                       WHERE rotina_id = %s AND referencia = %s""",
                  (int(rotina_id), ref.isoformat()))
    return {"gravou": bool(novo), "id": int(linha["id"]), "codigo": item["codigo"],
            "titulo": item["titulo"], "referencia": ref.isoformat(),
            "por": linha["feito_por"], "em": str(linha["feito_em"])[:16],
            "resultado": linha["resultado"], "observacao": linha["observacao"] or ""}


# ------------------------------------------------------------------ as listas


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
                           resultado FROM {TABELA_FEITOS} WHERE rotina_id = ANY(%s)
                     ORDER BY rotina_id, referencia DESC, id DESC""",
                ([int(r["id"]) for r in linhas],)):
            ultimos[int(f["rotina_id"])] = {
                "referencia": f["referencia"], "em": str(f["feito_em"])[:16],
                "por": f["feito_por"],
                "resultado_rotulo": ROTULO_DO_RESULTADO.get(f["resultado"], f["resultado"])}
    ordem_per = [p for p, _ in PERIODICIDADES]
    saida = []
    for r in linhas:
        item = _para_tela(r, hoje)
        proximo = proximo_vencimento(r, hoje, feriados=feriados) if item["ativo"] else None
        item.update(proximo=proximo.isoformat() if proximo else None,
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
        item = _para_tela(r, hoje)
        proximo = proximo_vencimento(r, hoje, feriados=feriados)
        item["proximo"] = proximo.isoformat() if proximo else None
        item["sou"] = "responsável" if r["responsavel_id"] == int(usuario_id) else "suplente"
        saida.append(item)
    saida.sort(key=lambda x: (x["proximo"] or "9999", x["prioridade"], x["titulo"]))
    return saida


def pessoas(con) -> list[dict]:
    """Quem pode responder por uma rotina: as pessoas ativas (sem robô). SÓ LÊ."""
    return banco(con).ler(
        "SELECT id, username, full_name FROM users WHERE active = 1 "
        "AND COALESCE(eh_robo, 0) = 0 ORDER BY full_name COLLATE public.cg_nocase, id")


def contar(con, *, ativas: bool = True) -> int:
    """Quantos itens ativos (ou desativados) o cadastro tem (0 sem a tabela). SÓ LÊ."""
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return 0
    return int(bd.valor(f"SELECT count(*) FROM {TABELA} WHERE ativo = %s",
                        (1 if ativas else 0,)) or 0)

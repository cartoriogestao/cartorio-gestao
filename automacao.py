"""A automação — o cadastro das rotinas, a conta da agenda, o despachante e o relatório.

    «uma tarefa só no Agendador, rodando a cada minuto, fora do servidor; cada
     processo no seu subprocesso, com prazo; e um lugar só para ver se rodou»
     — as decisões do oficial (24/10/2026)

COMO UMA RODADA ACONTECE — TRÊS PROCESSOS, E CADA UM EXISTE POR UM MOTIVO

    1. O TIQUE (`--tique`, a tarefa do Agendador, a cada minuto). Pega a trava
       global, bate o coração, recupera o que morreu, vê o que venceu e LANÇA
       um corredor por rodada. **Não espera ninguém**: o tique dura menos de um
       segundo, e por isso um processo de dez minutos não segura os outros.
    2. O CORREDOR (`--executar ID`). Roda o trabalho num subprocesso COM PRAZO,
       e é ele quem mata o trabalho que passou do prazo — o trabalho travado
       não consegue se matar sozinho. Depois grava o resultado, avisa quem
       precisa e bate o ponto no quadro antigo dos robôs.
    3. O TRABALHO (`--trabalho ID`, ou o script do processo). Chama a
       verificação do sistema (ou o agente de IA) e imprime o resultado numa
       linha marcada. **Não grava o resultado**: quem grava é o corredor.

    O servidor web NUNCA roda processo. «Rodar agora» só marca o pedido, e o
    tique do minuto seguinte o pega — uma verificação que fala com Central
    dentro de uma requisição do waitress seguraria o balcão.

AS QUATRO TRAVAS
    - a GLOBAL (`au_trava`): dois tiques não andam juntos; a trava cuja batida
      envelheceu mais de dez minutos é de um tique morto, e se retoma;
    - a POR PROCESSO: uma rodada `RODANDO` por processo, e o banco garante
      (índice único parcial). A rodada que venceu com a anterior de pé vira
      `PULADA`, uma vez por horário, e não a cada minuto;
    - o PRAZO: o corredor mata o trabalho no `timeout_s`;
    - a RECUPERAÇÃO: rodada `RODANDO` cujo corredor morreu vira `INTERROMPIDA`
      no tique seguinte; a que passou muito do prazo é encerrada à força e vira
      `TEMPO_ESGOTADO`. Nada fica «rodando» para sempre.

«NÃO MEDIU» NÃO É «ZERO»
    Regra da casa. A verificação que não conseguiu medir devolve ERRO com o
    motivo; o trabalho que terminou sem devolver resultado também é ERRO. Uma
    rodada só é OK quando alguém mediu e achou tudo em ordem.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
import uuid
from datetime import date, datetime, time as hora, timedelta
from pathlib import Path
from typing import Any, Callable

import automacao_schema as SCH
from bd_nativo import banco

RAIZ = Path(__file__).resolve().parent

#: A rodada perdida (máquina desligada, despachante parado) roda quando volta,
#: mas só se o horário perdido for de até 12 horas atrás. Uma verificação das
#: 11:30 que rode às 20:00 ainda diz a verdade de hoje; a de anteontem, não.
TOLERANCIA_DE_ATRASO = timedelta(hours=12)
#: A trava global cuja batida passou disso é de um tique que morreu.
TRAVA_VENCIDA = timedelta(minutes=10)
#: Quanto se espera além do prazo antes de encerrar o corredor à força.
FOLGA_DO_PRAZO_S = 120
#: Corredor que não chegou a registrar o próprio número em tanto tempo morreu.
SEM_PID_DESDE = timedelta(minutes=3)
#: A pausa entre duas tentativas de quem falhou (`max_tentativas` > 1).
PAUSA_ENTRE_TENTATIVAS_S = 30
#: O despachante que não bate há mais que isto está parado — a tela fica vermelha.
DESPACHANTE_PARADO = timedelta(minutes=5)
#: A linha que o trabalho imprime com o resultado. O corredor lê a ÚLTIMA.
MARCA_DO_RESULTADO = "AUTOMACAO-RESULTADO:"
#: O detalhe técnico guardado é cortado: log não é lugar de corpo de remessa.
TETO_DO_DETALHE = 8000
TETO_DO_RELATO = 4000
TIMEOUT_MINIMO_S, TIMEOUT_MAXIMO_S = 10, 6 * 3600

DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
OMITIDO = "«omitido»"


class AutomacaoError(ValueError):
    """Erro de regra da automação, com a frase pronta para a tela."""


class AutomacaoRecusada(AutomacaoError):
    """Pedido que este papel não pode fazer."""


# ------------------------------------------------------------------ o relógio


def _iso(quando: datetime | None) -> str | None:
    return quando.replace(microsecond=0).isoformat() if quando else None


def _dt(texto: Any) -> datetime | None:
    if not texto:
        return None
    if isinstance(texto, datetime):
        return texto
    try:
        return datetime.fromisoformat(str(texto)[:19].replace(" ", "T"))
    except ValueError:
        return None


def _json(texto: Any, padrao: Any) -> Any:
    if texto in (None, ""):
        return padrao
    if isinstance(texto, (dict, list)):
        return texto
    try:
        return json.loads(texto)
    except (TypeError, ValueError):
        return padrao


def _dump(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


# ------------------------------------------------------------------ a agenda
#
# A AGENDA É UM DICIONÁRIO, E SÓ TEM DUAS FORMAS:
#     {"dias": [0..6], "horarios": ["11:30", "14:10"]}
#     {"dias": [0..6], "intervalo_min": 60, "janela": ["08:00", "17:00"]}
# `dias` usa a semana do Python (0 = segunda); sem `dias`, todo dia. A janela
# vale para as duas formas, e na de intervalo ela é também o ponto de partida.


def _hhmm(texto: Any) -> hora:
    bruto = str(texto or "").strip()
    achado = re.fullmatch(r"(\d{1,2}):(\d{2})", bruto)
    if not achado:
        raise AutomacaoError(f"Horário «{bruto}» não está no formato HH:MM (ex.: 11:30).")
    h, m = int(achado.group(1)), int(achado.group(2))
    if h > 23 or m > 59:
        raise AutomacaoError(f"Horário «{bruto}» não existe.")
    return hora(h, m)


def normalizar_agenda(bruta: Any) -> dict:
    """Confere e devolve a agenda na forma única. Recusa o que não fecha."""
    agenda = _json(bruta, None)
    if not isinstance(agenda, dict):
        raise AutomacaoError("A agenda não se lê. Escolha os dias e os horários (ou o intervalo).")
    dias = agenda.get("dias")
    dias = list(range(7)) if dias in (None, "") else dias
    try:
        dias = sorted({int(d) for d in dias})
    except (TypeError, ValueError) as erro:
        raise AutomacaoError("Os dias da agenda têm de ser números de 0 (segunda) a 6 (domingo).") from erro
    if not dias or any(d < 0 or d > 6 for d in dias):
        raise AutomacaoError("Marque pelo menos um dia da semana na agenda.")
    horarios = agenda.get("horarios") or []
    if isinstance(horarios, str):
        horarios = [h for h in re.split(r"[,;\s]+", horarios) if h]
    horarios = sorted({_hhmm(h).strftime("%H:%M") for h in horarios})
    intervalo = agenda.get("intervalo_min")
    intervalo = int(intervalo) if str(intervalo or "").strip() not in ("", "0") else 0
    if horarios and intervalo:
        raise AutomacaoError("A agenda tem horários fixos OU um intervalo — não os dois.")
    if not horarios and not intervalo:
        raise AutomacaoError("Informe os horários (ex.: 11:30, 14:10) ou o intervalo em minutos.")
    if intervalo and not (1 <= intervalo <= 1440):
        raise AutomacaoError("O intervalo vai de 1 a 1440 minutos.")
    saida: dict[str, Any] = {"dias": dias}
    if horarios:
        saida["horarios"] = horarios
    else:
        saida["intervalo_min"] = intervalo
    janela = agenda.get("janela")
    if janela and any(str(x or "").strip() for x in janela):
        inicio, fim = _hhmm(janela[0]), _hhmm(janela[1])
        if fim <= inicio:
            raise AutomacaoError("A janela da agenda tem de terminar depois de começar.")
        saida["janela"] = [inicio.strftime("%H:%M"), fim.strftime("%H:%M")]
    return saida


def _slots_do_dia(agenda: dict, dia: date) -> list[datetime]:
    if dia.weekday() not in agenda.get("dias", range(7)):
        return []
    janela = agenda.get("janela")
    inicio = _hhmm(janela[0]) if janela else hora(0, 0)
    fim = _hhmm(janela[1]) if janela else hora(23, 59)
    if agenda.get("horarios"):
        return [datetime.combine(dia, h) for h in (_hhmm(x) for x in agenda["horarios"])
                if inicio <= h <= fim]
    passo = timedelta(minutes=int(agenda["intervalo_min"]))
    atual, limite = datetime.combine(dia, inicio), datetime.combine(dia, fim)
    saida = []
    while atual <= limite:
        saida.append(atual)
        atual += passo
    return saida


def ultimo_slot(agenda: dict, agora: datetime) -> datetime | None:
    """O último horário da agenda que já chegou (hoje ou nos sete dias de trás)."""
    for atras in range(0, 8):
        dia = (agora - timedelta(days=atras)).date()
        chegaram = [s for s in _slots_do_dia(agenda, dia) if s <= agora]
        if chegaram:
            return max(chegaram)
    return None


def proximo_disparo(agenda: dict, agora: datetime) -> datetime | None:
    """O primeiro horário da agenda depois de agora."""
    for adiante in range(0, 9):
        dia = (agora + timedelta(days=adiante)).date()
        futuros = [s for s in _slots_do_dia(agenda, dia) if s > agora]
        if futuros:
            return min(futuros)
    return None


def vencido(agenda: dict, agora: datetime, referencia: datetime | None) -> datetime | None:
    """O horário que venceu e ainda não teve rodada, ou None.

    `referencia` é o último horário já atendido (ou a hora em que o processo
    foi ligado). O horário que venceu há mais que a tolerância não roda: é o
    dia que já passou.
    """
    slot = ultimo_slot(agenda, agora)
    if slot is None or (referencia is not None and slot <= referencia):
        return None
    if agora - slot > TOLERANCIA_DE_ATRASO:
        return None
    return slot


def descrever_agenda(agenda: Any) -> str:
    """A agenda em português, para a lista («seg a sex, às 11:30 e 14:10»)."""
    try:
        a = normalizar_agenda(agenda)
    except AutomacaoError:
        return "agenda não se lê"
    dias = a["dias"]
    if dias == list(range(7)):
        quando = "todo dia"
    elif dias == list(range(5)):
        quando = "seg a sex"
    elif dias == list(range(6)):
        quando = "seg a sáb"
    else:
        quando = ", ".join(DIAS[d] for d in dias)
    if a.get("horarios"):
        h = a["horarios"]
        texto = f"{quando}, às " + (h[0] if len(h) == 1 else ", ".join(h[:-1]) + " e " + h[-1])
    else:
        texto = f"{quando}, a cada {a['intervalo_min']} min"
        if a.get("janela"):
            texto += f" das {a['janela'][0]} às {a['janela'][1]}"
    return texto


# ------------------------------------------------------------------ o cadastro

_JSON_DO_PROCESSO = {"parametros": {}, "agenda": {}, "canais": {}, "estado": {}}


def _decodificar(linha: dict | None) -> dict | None:
    if not linha:
        return None
    p = dict(linha)
    for coluna, padrao in _JSON_DO_PROCESSO.items():
        p[coluna] = _json(p.get(coluna), padrao)
    p["ativo"] = bool(p.get("ativo"))
    p["pode_agir"] = bool(p.get("pode_agir"))
    return p


def listar(con) -> list[dict]:
    return [_decodificar(r) for r in banco(con).ler(
        "SELECT * FROM au_processos ORDER BY setor, nome, id")]


def obter(con, processo_id: int) -> dict | None:
    return _decodificar(banco(con).um("SELECT * FROM au_processos WHERE id = %s",
                                      (int(processo_id),)))


def por_codigo(con, codigo: str) -> dict | None:
    return _decodificar(banco(con).um("SELECT * FROM au_processos WHERE codigo = %s",
                                      (str(codigo),)))


def semear(con, agora: datetime | None = None) -> int:
    """Põe no cadastro os processos de fábrica que ainda não estão lá. **DESLIGADOS.**

    Idempotente pelo código. Não mexe em processo que já existe — o que o
    oficial ajustou é dele.
    """
    import automacao_processos as PROC
    SCH.init_automacao_schema(con)
    bd = banco(con)
    agora_txt = _iso(agora or datetime.now())
    novos = 0
    for s in PROC.todas_as_sementes():
        bd.escrever(
            """INSERT INTO au_processos (codigo, nome, descricao, setor, tipo, alvo,
                   parametros, agenda, ativo, pode_agir, timeout_s, max_tentativas,
                   canais, robo_oficial, criado_por, criado_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s,%s,'SISTEMA',%s)
               ON CONFLICT (codigo) DO NOTHING""",
            (s["codigo"], s["nome"], s.get("descricao", ""), s.get("setor", "GESTAO"),
             s.get("tipo", SCH.FUNCAO), s["alvo"], _dump(s.get("parametros") or {}),
             _dump(normalizar_agenda(s["agenda"])), int(s.get("timeout_s", 300)),
             int(s.get("max_tentativas", 1)), _dump(s.get("canais") or CANAIS_PADRAO),
             s.get("robo_oficial"), agora_txt))
        novos += bd.linhas_afetadas or 0
    return novos


#: Os canais que um processo novo usa. O WhatsApp entra marcado de propósito:
#: ele não existe ainda, e o aviso que ficou pendente por isso fica registrado.
CANAIS_PADRAO = {SCH.PAINEL: True, SCH.TAREFA: True, SCH.EMAIL: True, SCH.WHATSAPP: True}

#: O que a tela de edição pode mudar. `pode_agir` e `ativo` NÃO estão aqui:
#: cada um tem a sua função, e `pode_agir` é do ADMIN, com auditoria.
EDITAVEIS = ("nome", "descricao", "setor", "tipo", "alvo", "parametros", "agenda",
             "usa_credencial", "timeout_s", "max_tentativas", "responsavel_user_id",
             "canais", "lembrar_a_cada_h", "robo_oficial")


def _validar_alvo(tipo: str, alvo: str, raiz: Path) -> str:
    alvo = str(alvo or "").strip()
    if not alvo:
        raise AutomacaoError("Informe o que o processo roda (a função, o script ou o pedido ao agente).")
    if tipo == SCH.FUNCAO:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*", alvo):
            raise AutomacaoError("A função se escreve «modulo:funcao» (ex.: automacao_processos:verificar_disco).")
        modulo = alvo.split(":", 1)[0]
        if not (raiz / f"{modulo}.py").is_file():
            raise AutomacaoError(f"O módulo «{modulo}» não existe nesta instalação.")
    elif tipo == SCH.SCRIPT:
        caminho = (raiz / alvo).resolve()
        try:
            caminho.relative_to(raiz.resolve())
        except ValueError as erro:
            raise AutomacaoError("O script tem de estar dentro da pasta do programa "
                                 "(caminho relativo, sem «..»).") from erro
        if caminho.suffix.lower() not in (".py", ".cmd", ".bat", ".ps1", ".sh"):
            raise AutomacaoError("O script tem de ser .py, .sh (macOS), ou .cmd, .bat, .ps1 (Windows).")
    return alvo


def salvar(con, processo_id: int, campos: dict, *, usuario: str,
           agora: datetime | None = None, raiz: Path = RAIZ) -> dict:
    """Grava o que a tela de edição mandou. Devolve o processo como ficou.

    Recusa `pode_agir` e `ativo` (têm função própria) e recusa credencial em
    processo de IA: **o segredo do cofre nunca vai ao modelo**.
    """
    atual = obter(con, processo_id)
    if not atual:
        raise AutomacaoError("Esse processo não existe.")
    proibidos = {"pode_agir", "ativo"} & set(campos)
    if proibidos:
        raise AutomacaoRecusada("«Pode agir sozinho» e «ligado» têm botão próprio.")
    novo = dict(atual)
    for chave in EDITAVEIS:
        if chave in campos:
            novo[chave] = campos[chave]
    tipo = str(novo.get("tipo") or "").strip().upper()
    if tipo not in SCH.TIPOS:
        raise AutomacaoError("Tipo de processo desconhecido.")
    novo["tipo"] = tipo
    novo["alvo"] = _validar_alvo(tipo, novo.get("alvo"), raiz)
    novo["agenda"] = normalizar_agenda(novo.get("agenda"))
    novo["nome"] = str(novo.get("nome") or "").strip()
    if not novo["nome"]:
        raise AutomacaoError("O processo precisa de um nome.")
    cred = str(novo.get("usa_credencial") or "").strip() or None
    if cred and tipo == SCH.AGENTE_IA:
        raise AutomacaoRecusada("Processo de agente de IA não usa credencial do cofre: "
                                "o segredo nunca é mandado ao modelo.")
    novo["usa_credencial"] = cred
    try:
        timeout = int(novo.get("timeout_s") or 300)
        tentativas = int(novo.get("max_tentativas") or 1)
    except (TypeError, ValueError) as erro:
        raise AutomacaoError("Prazo e tentativas têm de ser números.") from erro
    novo["timeout_s"] = max(TIMEOUT_MINIMO_S, min(TIMEOUT_MAXIMO_S, timeout))
    novo["max_tentativas"] = max(1, min(5, tentativas))
    lembrar = str(novo.get("lembrar_a_cada_h") or "").strip()
    novo["lembrar_a_cada_h"] = max(1, min(72, int(lembrar))) if lembrar.isdigit() else None
    resp = str(novo.get("responsavel_user_id") or "").strip()
    novo["responsavel_user_id"] = int(resp) if resp.isdigit() else None
    canais = _json(novo.get("canais"), {})
    novo["canais"] = {c: bool(canais.get(c)) for c in SCH.CANAIS}
    novo["parametros"] = _json(novo.get("parametros"), None)
    if not isinstance(novo["parametros"], dict):
        raise AutomacaoError("Os parâmetros têm de ser um objeto JSON (ex.: {\"dias\": 7}).")
    banco(con).escrever(
        """UPDATE au_processos SET nome=%s, descricao=%s, setor=%s, tipo=%s, alvo=%s,
               parametros=%s, agenda=%s, usa_credencial=%s, timeout_s=%s,
               max_tentativas=%s, responsavel_user_id=%s, canais=%s,
               lembrar_a_cada_h=%s, robo_oficial=%s, alterado_por=%s, alterado_em=%s
            WHERE id=%s""",
        (novo["nome"], str(novo.get("descricao") or ""), str(novo.get("setor") or "GESTAO"),
         tipo, novo["alvo"], _dump(novo["parametros"]), _dump(novo["agenda"]), cred,
         novo["timeout_s"], novo["max_tentativas"], novo["responsavel_user_id"],
         _dump(novo["canais"]), novo["lembrar_a_cada_h"],
         (str(novo.get("robo_oficial") or "").strip() or None), usuario,
         _iso(agora or datetime.now()), int(processo_id)))
    return obter(con, processo_id)


def definir_ativo(con, processo_id: int, ativo: bool, *, usuario: str,
                  agora: datetime | None = None) -> dict:
    """Liga ou desliga. Ligar carimba `ativado_em`: os horários de antes não rodam."""
    if not obter(con, processo_id):
        raise AutomacaoError("Esse processo não existe.")
    momento = _iso(agora or datetime.now())
    banco(con).escrever(
        """UPDATE au_processos SET ativo=%s, ativado_em=CASE WHEN %s=1 THEN %s ELSE ativado_em END,
               alterado_por=%s, alterado_em=%s WHERE id=%s""",
        (1 if ativo else 0, 1 if ativo else 0, momento, usuario, momento, int(processo_id)))
    return obter(con, processo_id)


def definir_pode_agir(con, processo_id: int, valor: bool, *, papel: str,
                      usuario: str, agora: datetime | None = None) -> dict:
    """Deixa (ou não) o agente de IA deste processo agir sozinho. **Só o ADMIN.**

    A auditoria é da rota (`audit` abre transação própria e vai fora desta);
    a recusa é aqui, para não depender de a tela lembrar.
    """
    if str(papel or "").upper() != "ADMIN":
        raise AutomacaoRecusada("Só o oficial (ADMIN) libera um processo para agir sozinho.")
    if not obter(con, processo_id):
        raise AutomacaoError("Esse processo não existe.")
    momento = _iso(agora or datetime.now())
    banco(con).escrever(
        "UPDATE au_processos SET pode_agir=%s, alterado_por=%s, alterado_em=%s WHERE id=%s",
        (1 if valor else 0, usuario, momento, int(processo_id)))
    return obter(con, processo_id)


def pedir_rodada(con, processo_id: int, *, usuario: str,
                 agora: datetime | None = None) -> dict:
    """«Rodar agora»: só MARCA o pedido. Quem roda é o despachante, no próximo minuto."""
    if not obter(con, processo_id):
        raise AutomacaoError("Esse processo não existe.")
    banco(con).escrever(
        "UPDATE au_processos SET pedido_manual_em=%s, pedido_manual_por=%s WHERE id=%s",
        (_iso(agora or datetime.now()), usuario, int(processo_id)))
    return obter(con, processo_id)


# ------------------------------------------------------------------ o que se lê


def _decodificar_execucao(linha: dict | None) -> dict | None:
    if not linha:
        return None
    e = dict(linha)
    e["achados"] = _json(e.get("achados"), [])
    e["acoes"] = _json(e.get("acoes"), [])
    e["selo"] = SCH.selo(e.get("situacao"))
    return e


def execucoes(con, processo_id: int, limite: int = 30) -> list[dict]:
    return [_decodificar_execucao(r) for r in banco(con).ler(
        "SELECT * FROM au_execucoes WHERE processo_id=%s ORDER BY id DESC LIMIT %s",
        (int(processo_id), int(limite)))]


def execucao(con, execucao_id: int) -> dict | None:
    return _decodificar_execucao(banco(con).um(
        "SELECT * FROM au_execucoes WHERE id=%s", (int(execucao_id),)))


def avisos_da_execucao(con, execucao_id: int) -> list[dict]:
    return banco(con).ler("SELECT * FROM au_avisos WHERE execucao_id=%s ORDER BY id",
                          (int(execucao_id),))


def _referencia(con, processo: dict) -> datetime | None:
    ultima = banco(con).valor(
        "SELECT MAX(agendada_para) FROM au_execucoes WHERE processo_id=%s AND disparo=%s",
        (processo["id"], SCH.AGENDA))
    candidatos = [d for d in (_dt(ultima), _dt(processo.get("ativado_em"))) if d]
    return max(candidatos) if candidatos else None


def painel(con, agora: datetime | None = None) -> list[dict]:
    """Uma linha por processo, com a luz, a última rodada e a próxima. **SÓ LÊ.**"""
    agora = agora or datetime.now()
    bd = banco(con)
    ultimas = {r["processo_id"]: r for r in bd.ler(
        """SELECT e.* FROM au_execucoes e
            WHERE e.id IN (SELECT MAX(id) FROM au_execucoes
                            WHERE situacao <> %s GROUP BY processo_id)""", (SCH.PULADA,))}
    rodando = {r["processo_id"] for r in bd.ler(
        "SELECT processo_id FROM au_execucoes WHERE situacao=%s", (SCH.RODANDO,))}
    saida = []
    for p in listar(con):
        ultima = _decodificar_execucao(ultimas.get(p["id"]))
        try:
            agenda = normalizar_agenda(p["agenda"])
            proxima = proximo_disparo(agenda, agora) if p["ativo"] else None
        except AutomacaoError:
            proxima = None
        if p["id"] in rodando:
            luz = "rodando"
        elif not ultima:
            luz = "nunca"
        else:
            luz = {SCH.OK: "ok", SCH.AVISO: "atencao"}.get(ultima["situacao"], "problema")
        saida.append({**p, "ultima": ultima, "proxima": _iso(proxima),
                      "agenda_texto": descrever_agenda(p["agenda"]), "luz": luz,
                      "rodando": p["id"] in rodando,
                      "na_fila": bool(p.get("pedido_manual_em")),
                      "nome_do_tipo": SCH.NOME_DO_TIPO.get(p["tipo"], p["tipo"])})
    return saida


def problemas_atuais(con) -> list[dict]:
    """Os processos com problema em aberto (o alerta já saiu e ainda não normalizou)."""
    return [_decodificar(r) for r in banco(con).ler(
        "SELECT * FROM au_processos WHERE alerta_desde IS NOT NULL ORDER BY alerta_desde")]


def contar_problemas(con) -> int:
    return int(banco(con).valor(
        "SELECT COUNT(*) FROM au_processos WHERE alerta_desde IS NOT NULL") or 0)


def batida_do_despachante(con, agora: datetime | None = None) -> dict:
    """Quando foi o último tique, e se está atrasado (mais de cinco minutos)."""
    agora = agora or datetime.now()
    linha = banco(con).um("SELECT * FROM au_trava WHERE id=1") or {}
    ultimo = _dt(linha.get("ultimo_tique_em"))
    return {"ultimo_tique_em": _iso(ultimo),
            "hora": ultimo.strftime("%d/%m %H:%M") if ultimo else None,
            "parado": ultimo is None or agora - ultimo > DESPACHANTE_PARADO,
            "nunca": ultimo is None,
            "resumo": _json(linha.get("ultimo_resumo"), {})}


# ------------------------------------------------------------------ a trava


def adquirir_trava(con, dono: str, agora: datetime) -> bool:
    """A trava global. Só pega quem a acha livre ou de um tique morto."""
    bd = banco(con)
    bd.escrever("INSERT INTO au_trava (id) VALUES (1) ON CONFLICT DO NOTHING")
    bd.escrever(
        """UPDATE au_trava SET dono=%s, adquirida_em=%s, batida_em=%s
            WHERE id=1 AND (dono IS NULL OR batida_em IS NULL OR batida_em < %s)""",
        (dono, _iso(agora), _iso(agora), _iso(agora - TRAVA_VENCIDA)))
    return bool(bd.linhas_afetadas)


def soltar_trava(con, dono: str, agora: datetime, resumo: dict | None = None) -> None:
    banco(con).escrever(
        """UPDATE au_trava SET dono=NULL, batida_em=%s, ultimo_tique_em=%s, ultimo_resumo=%s
            WHERE id=1 AND dono=%s""",
        (_iso(agora), _iso(agora), _dump(resumo or {}), dono))


# ------------------------------------------------------------------ processos do SO


def processo_vivo(pid: Any) -> bool:
    """O processo existe? No Windows, pela API; fora dele, pelo sinal 0."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        alca = kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not alca:
            return False
        try:
            codigo = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(alca, ctypes.byref(codigo)):
                return False
            return codigo.value == 259                       # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(alca)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def matar_arvore(pid: Any) -> None:
    """Encerra o processo e os filhos dele. Não estoura se já morreu."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=30, check=False)
        return
    try:
        os.killpg(os.getpgid(pid), 9)
    except OSError:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def _flags_desacoplado() -> int:
    if os.name != "nt":
        return 0
    return (subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008      # DETACHED_PROCESS
            | 0x08000000)                                          # CREATE_NO_WINDOW


def lancar_corredor(execucao_id: int, *, raiz: Path = RAIZ) -> int:
    """Lança o corredor da rodada SEM esperar. Devolve o número do processo.

    Tenta sair do «job» do Agendador (`CREATE_BREAKAWAY_FROM_JOB`): sem isso,
    o fim da tarefa do minuto poderia levar o corredor junto. Se o job não
    deixa, lança sem — o corredor de hoje já sobrevive ao fim normal da tarefa.
    """
    comando = [sys.executable, str(raiz / "automacao.py"), "--executar", str(int(execucao_id))]
    base = dict(cwd=str(raiz), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True)
    if os.name != "nt":
        return subprocess.Popen(comando, start_new_session=True, **base).pid
    try:
        return subprocess.Popen(comando, creationflags=_flags_desacoplado() | 0x01000000,
                                **base).pid
    except OSError:
        return subprocess.Popen(comando, creationflags=_flags_desacoplado(), **base).pid


# ------------------------------------------------------------------ o tique


def prazo_total_s(processo: dict) -> int:
    """Quanto uma rodada inteira pode levar, com as tentativas e as pausas."""
    t = int(processo.get("timeout_s") or 300)
    n = int(processo.get("max_tentativas") or 1)
    return t * n + PAUSA_ENTRE_TENTATIVAS_S * (n - 1)


def _criar_execucao(con, processo: dict, *, disparo: str, agendada_para: datetime | None,
                    quem: str | None, agora: datetime, situacao: str = SCH.RODANDO,
                    relato: str = "") -> int:
    linha = banco(con).escrever(
        """INSERT INTO au_execucoes (processo_id, disparo, agendada_para, iniciada_em,
               situacao, relato, quem, terminada_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (processo["id"], disparo, _iso(agendada_para), _iso(agora), situacao, relato, quem,
         _iso(agora) if situacao != SCH.RODANDO else None))
    return int(linha[0]["id"])


def recuperar(db, agora: datetime, *, vivo: Callable[[Any], bool] = processo_vivo,
              matar: Callable[[Any], None] = matar_arvore,
              pasta_dados: Any = None) -> list[dict]:
    """As rodadas `RODANDO` que não estão rodando de verdade. Encerra cada uma.

    Corredor morto → `INTERROMPIDA`; corredor vivo muito além do prazo → é
    encerrado à força e a rodada vira `TEMPO_ESGOTADO`.
    """
    with db.connect() as con:
        rodando = banco(con).ler(
            """SELECT e.*, p.timeout_s, p.max_tentativas FROM au_execucoes e
                 JOIN au_processos p ON p.id = e.processo_id
                WHERE e.situacao=%s ORDER BY e.id""", (SCH.RODANDO,))
    fechadas = []
    for e in rodando:
        inicio = _dt(e["iniciada_em"]) or agora
        passou = (agora - inicio).total_seconds()
        if e.get("pid") is None:
            if agora - inicio < SEM_PID_DESDE:
                continue
            resultado = {"situacao": SCH.INTERROMPIDA,
                         "relato": "A rodada não chegou a começar: o corredor não registrou "
                                   "o número do processo. Ela será refeita no próximo horário.",
                         "erro": "corredor sem pid"}
        elif not vivo(e["pid"]):
            resultado = {"situacao": SCH.INTERROMPIDA,
                         "relato": "A rodada parou no meio: o processo que a rodava morreu "
                                   "(máquina reiniciada, falta de memória ou encerramento à mão).",
                         "erro": f"corredor {e['pid']} não está mais vivo"}
        elif passou > prazo_total_s(e) + FOLGA_DO_PRAZO_S:
            matar(e["pid"])
            resultado = {"situacao": SCH.TEMPO_ESGOTADO,
                         "relato": f"A rodada passou muito do prazo ({prazo_total_s(e)} s) e "
                                   "foi encerrada à força pelo despachante.",
                         "erro": f"encerrada após {int(passou)} s"}
        else:
            continue
        finalizar(db, int(e["id"]), resultado, agora=agora, pasta_dados=pasta_dados)
        fechadas.append({"execucao_id": int(e["id"]), "situacao": resultado["situacao"]})
    return fechadas


def tique(db, *, agora: datetime | None = None,
          lancar: Callable[[int], int] | None = None,
          vivo: Callable[[Any], bool] = processo_vivo,
          matar: Callable[[Any], None] = matar_arvore,
          pasta_dados: Any = None) -> dict:
    """Um minuto do despachante. Devolve o resumo do que fez.

    `lancar(execucao_id) -> pid` existe para o teste; na casa é o corredor.
    """
    agora = agora or datetime.now()
    lancar = lancar or lancar_corredor
    dono = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"
    with db.transaction() as con:
        SCH.init_automacao_schema(con)
        if not adquirir_trava(con, dono, agora):
            return {"trava": "ocupada"}
    resumo: dict[str, Any] = {"lancadas": [], "puladas": [], "recuperadas": [], "erros": []}
    try:
        with db.transaction() as con:
            semear(con, agora)
        resumo["recuperadas"] = recuperar(db, agora, vivo=vivo, matar=matar,
                                          pasta_dados=pasta_dados)
        _email_de_teste(db, agora, pasta_dados)
        with db.connect() as con:
            processos = listar(con)
        for p in processos:
            try:
                _tique_do_processo(db, p, agora, lancar, resumo, pasta_dados)
            except Exception as erro:            # noqa: BLE001 — um processo não para os outros
                resumo["erros"].append(f"{p['codigo']}: {type(erro).__name__}: {erro}"[:300])
    finally:
        with db.transaction() as con:
            soltar_trava(con, dono, agora, {k: (len(v) if isinstance(v, list) else v)
                                            for k, v in resumo.items()})
    return resumo


def _tique_do_processo(db, p: dict, agora: datetime, lancar, resumo: dict,
                       pasta_dados: Any = None) -> None:
    with db.transaction() as con:
        bd = banco(con)
        rodando = bd.um("SELECT id FROM au_execucoes WHERE processo_id=%s AND situacao=%s",
                        (p["id"], SCH.RODANDO))
        disparo, slot, quem = None, None, None
        if p.get("pedido_manual_em"):
            if rodando:
                return                       # o pedido espera a rodada de pé terminar
            disparo, quem = SCH.MANUAL, p.get("pedido_manual_por")
            bd.escrever("UPDATE au_processos SET pedido_manual_em=NULL, pedido_manual_por=NULL "
                        "WHERE id=%s", (p["id"],))
        elif p["ativo"]:
            try:
                agenda = normalizar_agenda(p["agenda"])
            except AutomacaoError:
                return
            slot = vencido(agenda, agora, _referencia(con, p))
            if slot is None:
                return
            if rodando:
                _criar_execucao(con, p, disparo=SCH.AGENDA, agendada_para=slot, quem="AGENDA",
                                agora=agora, situacao=SCH.PULADA,
                                relato=f"A rodada das {slot:%H:%M} não começou: a anterior "
                                       f"(#{rodando['id']}) ainda estava rodando.")
                resumo["puladas"].append(p["codigo"])
                return
            disparo, quem = SCH.AGENDA, "AGENDA"
        else:
            return
        execucao_id = _criar_execucao(con, p, disparo=disparo, agendada_para=slot,
                                      quem=quem, agora=agora)
    try:
        pid = lancar(execucao_id)
    except Exception as erro:                # noqa: BLE001 — vira o resultado da rodada
        finalizar(db, execucao_id, {"situacao": SCH.ERRO,
                                    "relato": "O despachante não conseguiu lançar a rodada.",
                                    "erro": f"{type(erro).__name__}: {erro}"}, agora=agora,
                  pasta_dados=pasta_dados)
        return
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_execucoes SET pid=%s WHERE id=%s AND situacao=%s",
                            (int(pid), execucao_id, SCH.RODANDO))
    resumo["lancadas"].append(p["codigo"])


def _email_de_teste(db, agora: datetime, pasta_dados: Any) -> None:
    """O e-mail de teste que a tela de configuração pediu (a web não abre o cofre)."""
    with db.connect() as con:
        pedido = SCH.ler_config(con, SCH.CHAVE_TESTE_EMAIL)
        por = SCH.ler_config(con, SCH.CHAVE_TESTE_EMAIL_POR)
    if not pedido:
        return
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_TESTE_EMAIL, "")
        SCH.gravar_config(con, SCH.CHAVE_TESTE_EMAIL_POR, "")
    import automacao_avisos as AV
    AV.enviar_teste(db, agora=agora, pasta_dados=pasta_dados, pedido_por=por)


# ------------------------------------------------------------------ finalizar


def finalizar(db, execucao_id: int, resultado: dict, *, agora: datetime | None = None,
              pasta_dados: Any = None, tentativas: int | None = None,
              detalhe: str | None = None) -> dict:
    """Grava o fim da rodada, avisa quem precisa e bate o ponto no quadro dos robôs.

    Três transações curtas, e nenhuma segura rede: o e-mail sai fora delas.
    """
    agora = agora or datetime.now()
    r = normalizar_resultado(resultado)
    with db.transaction() as con:
        bd = banco(con)
        e = bd.um("SELECT * FROM au_execucoes WHERE id=%s", (int(execucao_id),))
        if not e:
            raise AutomacaoError(f"A rodada #{execucao_id} não existe.")
        inicio = _dt(e["iniciada_em"]) or agora
        detalhe_final = (detalhe if detalhe is not None else r.get("detalhe_tecnico")) or None
        bd.escrever(
            """UPDATE au_execucoes SET situacao=%s, terminada_em=%s, relato=%s, achados=%s,
                   acoes=%s, erro=%s, detalhe_tecnico=%s, duracao_s=%s,
                   tentativas=COALESCE(%s, tentativas)
                WHERE id=%s""",
            (r["situacao"], _iso(agora), r["relato"][:TETO_DO_RELATO], _dump(r["achados"]),
             _dump(r["acoes"]), (r.get("erro") or None) and str(r["erro"])[:2000],
             detalhe_final and str(detalhe_final)[-TETO_DO_DETALHE:],
             max(0, int((agora - inicio).total_seconds())), tentativas, int(execucao_id)))
        if isinstance(r.get("estado"), dict):
            bd.escrever("UPDATE au_processos SET estado=%s WHERE id=%s",
                        (_dump(r["estado"]), e["processo_id"]))
        processo = obter(con, e["processo_id"])
    execucao_final = None
    with db.connect() as con:
        execucao_final = execucao(con, execucao_id)
    import automacao_avisos as AV
    try:
        AV.tratar(db, processo, execucao_final, agora=agora, pasta_dados=pasta_dados)
    except Exception as erro:                # noqa: BLE001 — aviso que falha não desfaz a rodada
        with db.transaction() as con:
            banco(con).escrever(
                "INSERT INTO au_avisos (execucao_id, processo_id, canal, situacao, criado_em, erro) "
                "VALUES (%s,%s,'SISTEMA',%s,%s,%s)",
                (execucao_id, processo["id"], SCH.FALHOU, _iso(agora),
                 f"{type(erro).__name__}: {erro}"[:500]))
    _bater_no_quadro_dos_robos(db, processo, execucao_final)
    return execucao_final


def _bater_no_quadro_dos_robos(db, processo: dict, e: dict) -> None:
    """A tela antiga dos robôs continua dizendo a verdade (`oficial_robos.bater`)."""
    robo = (processo or {}).get("robo_oficial")
    if not robo or e["situacao"] == SCH.PULADA:
        return
    situacao = {SCH.OK: "OK", SCH.AVISO: "AVISO"}.get(e["situacao"], "ERRO")
    try:
        import oficial_robos
        with db.transaction() as con:
            oficial_robos.bater(con, robo, situacao=situacao,
                                resumo={"processo": processo["codigo"], "execucao": e["id"],
                                        "relato": (e.get("relato") or "")[:300]},
                                erro=e.get("erro"), iniciada_em=e.get("iniciada_em"),
                                quem_rodou="AUTOMACAO")
    except Exception:                         # noqa: BLE001 — o quadro antigo não derruba o novo
        pass


def normalizar_resultado(bruto: Any) -> dict:
    """O contrato da verificação: situação, relato, achados e ações.

    Resultado fora do contrato não vira OK: vira ERRO dizendo isso.
    """
    if not isinstance(bruto, dict):
        return {"situacao": SCH.ERRO, "relato": "A verificação não devolveu o resultado "
                "combinado (situação e relato).", "achados": [], "acoes": [],
                "erro": f"devolveu {type(bruto).__name__}"}
    situacao = str(bruto.get("situacao") or "").upper()
    if situacao not in SCH.SITUACOES or situacao == SCH.RODANDO:
        return {"situacao": SCH.ERRO, "relato": f"A verificação devolveu a situação "
                f"«{situacao or 'vazia'}», que não existe — não se trata como OK.",
                "achados": [], "acoes": [], "erro": "situação fora do contrato"}
    achados = bruto.get("achados") or []
    acoes = bruto.get("acoes") or []
    return {"situacao": situacao, "relato": str(bruto.get("relato") or "").strip(),
            "achados": achados if isinstance(achados, list) else [achados],
            "acoes": acoes if isinstance(acoes, list) else [acoes],
            "erro": bruto.get("erro"), "estado": bruto.get("estado"),
            "detalhe_tecnico": bruto.get("detalhe_tecnico")}


# ------------------------------------------------------------------ o corredor


def rodar_com_prazo(comando: list[str], *, timeout_s: int, cwd: Any = None,
                    entrada: str | None = None, env: dict | None = None) -> dict:
    """Roda e espera até o prazo. No prazo, mata a árvore inteira.

    Devolve `{codigo, saida, erro, esgotou, segundos}`.
    """
    inicio = time.monotonic()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000 if os.name == "nt" else 0
    proc = subprocess.Popen(comando, cwd=str(cwd) if cwd else None, env=env,
                            stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=flags, start_new_session=(os.name != "nt"))
    try:
        saida, erro = proc.communicate(
            input=entrada.encode("utf-8") if entrada is not None else None, timeout=timeout_s)
        esgotou = False
    except subprocess.TimeoutExpired:
        matar_arvore(proc.pid)
        try:
            saida, erro = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            saida, erro = b"", b""
        esgotou = True
    return {"codigo": proc.returncode, "saida": (saida or b"").decode("utf-8", "replace"),
            "erro": (erro or b"").decode("utf-8", "replace"), "esgotou": esgotou,
            "segundos": round(time.monotonic() - inicio, 1)}


def _comando(processo: dict, execucao_id: int, raiz: Path) -> list[str]:
    if processo["tipo"] != SCH.SCRIPT:
        return [sys.executable, str(raiz / "automacao.py"), "--trabalho", str(int(execucao_id))]
    alvo = (raiz / processo["alvo"]).resolve()
    alvo.relative_to(raiz.resolve())          # recusa o que saiu da pasta do programa
    params = processo.get("parametros") or {}
    args = [str(a) for a in (params.get("argumentos") or [])]
    sufixo = alvo.suffix.lower()
    if sufixo == ".py":
        return [sys.executable, str(alvo), *args]
    return _comando_de_script(alvo, sufixo, args)


def _comando_de_script(alvo: Path, sufixo: str, args: list[str]) -> list[str]:
    """O comando de um script que não é Python. Os dois sistemas ficam aqui, e só aqui."""
    if sys.platform == "win32":
        if sufixo == ".ps1":
            return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(alvo), *args]
        if sufixo in (".cmd", ".bat"):
            return ["cmd.exe", "/d", "/c", str(alvo), *args]
    if sufixo == ".sh":
        return ["/bin/sh", str(alvo), *args]
    raise AutomacaoError(f"Script «{alvo.name}» não roda neste sistema operacional.")


def _mascarar(texto: str, segredos: list[str]) -> str:
    for s in segredos:
        if s and len(s) >= 3:
            texto = texto.replace(s, OMITIDO)
    return texto


def interpretar(processo: dict, res: dict, *, segredos: list[str] | None = None) -> dict:
    """O que a saída do trabalho quer dizer. O detalhe técnico sai mascarado."""
    segredos = segredos or []
    saida = _mascarar(res.get("saida") or "", segredos)
    erro = _mascarar(res.get("erro") or "", segredos)
    detalhe = (f"código {res.get('codigo')} · {res.get('segundos')} s\n"
               f"--- saída (fim) ---\n{saida[-TETO_DO_DETALHE // 2:]}\n"
               f"--- erros (fim) ---\n{erro[-TETO_DO_DETALHE // 2:]}")
    if res.get("esgotou"):
        return {"situacao": SCH.TEMPO_ESGOTADO,
                "relato": f"Passou do prazo de {processo.get('timeout_s')} s e foi encerrado.",
                "erro": "tempo esgotado", "detalhe_tecnico": detalhe}
    linhas = [l for l in saida.splitlines() if l.startswith(MARCA_DO_RESULTADO)]
    if linhas:
        try:
            bruto = json.loads(linhas[-1][len(MARCA_DO_RESULTADO):])
        except ValueError:
            bruto = None
        r = normalizar_resultado(bruto)
        r["detalhe_tecnico"] = (r.get("detalhe_tecnico") or "") + "\n" + detalhe
        return r
    if processo["tipo"] == SCH.SCRIPT:
        if res.get("codigo") == 0:
            return {"situacao": SCH.OK, "relato": "O script terminou bem (código 0).",
                    "detalhe_tecnico": detalhe}
        return {"situacao": SCH.ERRO, "relato": f"O script terminou com o código {res.get('codigo')}.",
                "erro": (erro.strip().splitlines() or [""])[-1][:500], "detalhe_tecnico": detalhe}
    return {"situacao": SCH.ERRO,
            "relato": f"A verificação terminou sem devolver resultado (código {res.get('codigo')}).",
            "erro": (erro.strip().splitlines() or ["sem saída"])[-1][:500], "detalhe_tecnico": detalhe}


def cofre_trancado(processo: dict) -> dict:
    """O resultado do processo que precisa do cofre e o achou trancado: AVISO, sem erro técnico.

    Vira aviso nos canais como qualquer AVISO — é o pedido ao oficial para
    desbloquear. Os processos sem credencial rodam normalmente.
    """
    return {"situacao": SCH.AVISO,
            "relato": f"Cofre trancado: este processo precisa da credencial «{processo.get('usa_credencial')}», "
                      "e a senha-mestra não foi digitada desde que a máquina ligou. Desbloqueie na janela "
                      "do guardião do cofre ou em Automação → Cofre → Desbloquear, na própria máquina do "
                      "servidor. O processo roda de novo no próximo horário.",
            "achados": [{"cofre": "trancado"}], "acoes": []}


def executar(db, execucao_id: int, *, raiz: Path = RAIZ, pasta_dados: Any = None,
             rodar: Callable[..., dict] = rodar_com_prazo,
             pausa: Callable[[float], None] = time.sleep) -> dict:
    """O corredor de uma rodada: roda com prazo, tenta de novo se pedido, grava e avisa."""
    with db.connect() as con:
        e = execucao(con, execucao_id)
        processo = obter(con, e["processo_id"]) if e else None
    if not e or not processo:
        raise AutomacaoError(f"A rodada #{execucao_id} não existe.")
    if e["situacao"] != SCH.RODANDO:
        return e                              # já foi fechada (recuperação ou duplicata)
    entrada, segredos = None, []
    if processo.get("usa_credencial") and processo["tipo"] == SCH.SCRIPT:
        import automacao_cofre as COFRE
        try:
            campos = COFRE.ler(processo["usa_credencial"], caminho=COFRE.caminho_do_cofre(pasta_dados),
                               quem="despachante", processo=processo["codigo"])
        except COFRE.CofreTrancado:
            return finalizar(db, execucao_id, cofre_trancado(processo), pasta_dados=pasta_dados)
        except COFRE.CofreError as erro:
            return finalizar(db, execucao_id, {
                "situacao": SCH.AVISO, "relato": f"Não rodou: {erro}",
                "erro": "credencial indisponível"}, pasta_dados=pasta_dados)
        segredos = [str(v) for v in campos.values()]
        # O SEGREDO VAI PELA ENTRADA PADRÃO do script — nunca por argumento nem
        # por variável de ambiente, que outros processos da máquina enxergam.
        entrada = json.dumps({"nome": processo["usa_credencial"], "campos": campos}, ensure_ascii=False)
    tentativas = max(1, int(processo.get("max_tentativas") or 1))
    resultado: dict = {}
    for n in range(1, tentativas + 1):
        res = rodar(_comando(processo, execucao_id, raiz), timeout_s=int(processo["timeout_s"]),
                    cwd=raiz, entrada=entrada, env=dict(os.environ))
        resultado = interpretar(processo, res, segredos=segredos)
        if resultado["situacao"] != SCH.ERRO or n == tentativas:
            break
        pausa(PAUSA_ENTRE_TENTATIVAS_S)
    return finalizar(db, execucao_id, resultado, pasta_dados=pasta_dados, tentativas=n)


# ------------------------------------------------------------------ o trabalho


def trabalho(db, execucao_id: int, *, raiz: Path = RAIZ, pasta_dados: Any = None,
             agora: datetime | None = None) -> dict:
    """Roda a verificação (ou o agente) DESTA rodada e devolve o resultado. Não grava."""
    import automacao_processos as PROC
    with db.connect() as con:
        e = execucao(con, execucao_id)
        processo = obter(con, e["processo_id"]) if e else None
    if not processo:
        return {"situacao": SCH.ERRO, "relato": "A rodada não existe.", "erro": "sem rodada"}
    ctx = PROC.Contexto(db=db, agora=agora or datetime.now(), pasta_dados=Path(pasta_dados or "."),
                        raiz=raiz, processo=processo, execucao_id=int(execucao_id))
    import automacao_cofre as COFRE
    if processo.get("usa_credencial") and not COFRE.estado(
            caminho=COFRE.caminho_do_cofre(ctx.pasta_dados))["aberto"]:
        return cofre_trancado(processo)
    try:
        if processo["tipo"] == SCH.AGENTE_IA:
            bruto = PROC.rodar_agente(ctx)
        else:
            modulo, nome = processo["alvo"].split(":", 1)
            funcao = getattr(importlib.import_module(modulo), nome)
            bruto = funcao(ctx)
    except COFRE.CofreTrancado:
        return cofre_trancado(processo)
    except Exception as erro:                 # noqa: BLE001 — vira ERRO com o rastro
        return {"situacao": SCH.ERRO,
                "relato": f"A verificação quebrou antes de medir: {type(erro).__name__}: {erro}"[:600],
                "erro": f"{type(erro).__name__}: {erro}"[:500],
                "detalhe_tecnico": traceback.format_exc()[-TETO_DO_DETALHE:]}
    return normalizar_resultado(bruto)


# ------------------------------------------------------------------ a linha de comando


def pasta_de_dados() -> Path:
    """A pasta de dados: a do servidor (`CARTORIO_GESTAO_DATA`) ou a padrão."""
    import automacao_cofre as COFRE
    return COFRE.pasta_de_dados()


def database_leve(caminho: Path):
    """A `Database` da casa SEM subir o esquema inteiro — o tique roda a cada minuto.

    O esquema é do servidor (que o sobe na partida); o despachante só cria as
    tabelas dele (`init_automacao_schema`, idempotente). Montar a `Database`
    completa a cada minuto passaria centenas de comandos de esquema por nada.
    """
    import banco_pg
    import database
    if not banco_pg.ativo():
        raise AutomacaoError("O despachante precisa do PostgreSQL ligado (CG_PG_DSN), "
                             "como o servidor.")
    banco_pg.registrar_banco(caminho)
    banco_pg.instalar_desvio()
    db = database.Database.__new__(database.Database)
    db.db_path = Path(caminho)
    return db


def main(argv: list[str] | None = None) -> int:
    """`--tique` (o Agendador), `--executar ID` (o corredor), `--trabalho ID` (o trabalho)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                         # noqa: BLE001
        pass
    pasta = pasta_de_dados()
    db = database_leve(pasta / "cartorio_gestao.sqlite3")
    if not argv or argv[0] == "--tique":
        resumo = tique(db, pasta_dados=pasta)
        if resumo.get("lancadas") or resumo.get("recuperadas") or resumo.get("erros"):
            print(f"{datetime.now():%d/%m %H:%M:%S} {_dump(resumo)}")
        return 0
    if argv[0] == "--executar" and len(argv) > 1:
        executar(db, int(argv[1]), pasta_dados=pasta)
        return 0
    if argv[0] == "--trabalho" and len(argv) > 1:
        resultado = trabalho(db, int(argv[1]), pasta_dados=pasta)
        print(MARCA_DO_RESULTADO + _dump(resultado), flush=True)
        return 0
    print("uso: automacao.py [--tique | --executar ID | --trabalho ID]")
    return 2


if __name__ == "__main__":
    sys.exit(main())

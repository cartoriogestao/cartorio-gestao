"""A rotina do balcão do WhatsApp: horário, aviso de fora do horário, respostas
prontas e o encerramento da conversa parada.

    «e outras coisas que precisar ter ou organizar para funcionar bem o
     atendimento de whatsapp de um cartorio» — o oficial, 29/10/2026

O QUE MORA AQUI
    - a configuração do balcão que não é da Meta nem da IA (`config`, `gravar`):
      de quantos em quantos segundos o servidor busca (`wa_vigia`), o horário
      de atendimento (`wa_horario`), o aviso de fora do horário, as respostas
      prontas e os dias até a conversa parada se resolver sozinha;
    - `avisar_fora_do_horario`: quem escreve com o balcão fechado recebe UMA
      vez, por período fechado, o horário e quando a casa responde;
    - `encerrar_paradas`: a conversa que a casa respondeu e o cliente não
      voltou sai das abas de trabalho depois de N dias (volta sozinha, com o
      histórico, se o cliente escrever de novo — `FILA.retomar`).

O AVISO AUTOMÁTICO NÃO É RESPOSTA (29/10/2026)
    O aviso de fora do horário e o aviso de passagem da IA saem com o tipo
    `aviso` (`TIPO_AVISO`). A régua do «esperando resposta» (`wa_fila`) não os
    conta como resposta, e eles não põem a conversa em «aguardando»: sem isso,
    a conversa que a IA passou para uma pessoa — justamente a que precisa de
    alguém — sumia do alerta no minuto em que o cliente recebia «sua mensagem
    foi passada para a equipe». Era assim até esta versão.

A REDE FICA FORA DA TRANSAÇÃO, como em todo o módulo: marcar (transação
curta), enviar (rede), gravar (transação curta).
"""
from __future__ import annotations

import logging
import string
from datetime import datetime, timedelta
from typing import Any, Callable

from bd_nativo import banco

import wa_horario as HOR
import wa_schema as WA

LOG = logging.getLogger(__name__)

TIPO_AVISO = "aviso"
AUTOR_AVISO = "aviso automático"

VIGIA_PADRAO_S = 20
VIGIA_MINIMO_S = 10
VIGIA_MAXIMO_S = 600
ENCERRAR_PADRAO_DIAS = 3
ENCERRAR_MAXIMO_DIAS = 90
RESPOSTAS_NO_MAXIMO = 60

TEXTO_FORA_PADRAO = (
    "Olá! Recebemos a sua mensagem. O atendimento pelo WhatsApp é {horario}, e "
    "respondemos {quando_abre}. Se quiser, já deixe aqui o que precisa — o "
    "pedido fica na fila e é o primeiro a ser visto.")
CAMPOS_DO_AVISO = ("horario", "quando_abre")


class RotinaErro(ValueError):
    """A configuração do balcão foi recusada. Mensagem pronta para a tela."""


def _ler(con: Any, chave: str) -> str:
    import wa_balcao as BALCAO
    return BALCAO.ler_config(con, chave)


def _inteiro(texto: Any) -> int | None:
    t = str(texto or "").strip()
    return int(t) if t.isdigit() else None


def ler_respostas(texto: str) -> list[dict]:
    """«atalho | texto», uma por linha → [{atalho, texto}]. Só calcula."""
    saida = []
    for linha in str(texto or "").splitlines():
        if "|" not in linha:
            continue
        atalho, corpo = (p.strip() for p in linha.split("|", 1))
        if atalho and corpo:
            saida.append({"atalho": atalho[:40], "texto": corpo[:1000]})
    return saida[:RESPOSTAS_NO_MAXIMO]


def config(con: Any) -> dict:
    """A configuração do balcão, já lida. SÓ LÊ."""
    segundos = _inteiro(_ler(con, WA.CHAVE_VIGIA_SEGUNDOS))
    dias = _inteiro(_ler(con, WA.CHAVE_ENCERRAR_DIAS))
    horario = _ler(con, WA.CHAVE_HORARIO)
    regra = HOR.ler_ou_vazio(horario)
    respostas = _ler(con, WA.CHAVE_RESPOSTAS_PRONTAS)
    return {
        "vigia_segundos": VIGIA_PADRAO_S if segundos is None else segundos,
        "vigia_gravado": _ler(con, WA.CHAVE_VIGIA_SEGUNDOS),
        "horario_texto": horario,
        "regra": regra,
        "horario_descrito": HOR.descrever(regra),
        "fora_ligado": _ler(con, WA.CHAVE_FORA_HORARIO_LIGADO) == "1",
        "fora_texto": _ler(con, WA.CHAVE_FORA_HORARIO_TEXTO),
        "respostas_texto": respostas,
        "respostas": ler_respostas(respostas),
        "encerrar_dias": ENCERRAR_PADRAO_DIAS if dias is None else dias,
        "encerrar_gravado": _ler(con, WA.CHAVE_ENCERRAR_DIAS),
    }


def _conferir_aviso(texto: str) -> None:
    try:
        campos = {c for _, c, _, _ in string.Formatter().parse(texto) if c}
    except ValueError as erro:
        raise RotinaErro("O aviso de fora do horário tem uma chave «{ }» aberta "
                         "ou sobrando.") from erro
    sobra = sorted(campos - set(CAMPOS_DO_AVISO))
    if sobra:
        raise RotinaErro("O aviso de fora do horário só aceita {horario} e "
                         "{quando_abre}; tire " + ", ".join("{" + s + "}" for s in sobra)
                         + ".")


def gravar(con: Any, form: dict) -> list[str]:
    """Grava a configuração do balcão. ESCREVE. Devolve os avisos; recusa com
    `RotinaErro` antes de gravar qualquer coisa."""
    import wa_balcao as BALCAO
    avisos = []
    segundos = str(form.get("vigia_segundos") or "").strip()
    if segundos:
        n = _inteiro(segundos)
        if n is None or (n != 0 and not VIGIA_MINIMO_S <= n <= VIGIA_MAXIMO_S):
            raise RotinaErro(f"A busca automática é de {VIGIA_MINIMO_S} a "
                             f"{VIGIA_MAXIMO_S} segundos (ou 0 para desligar).")
    horario = str(form.get("horario") or "").replace("\r\n", "\n").strip()
    try:
        regra = HOR.ler(horario)
    except HOR.HorarioErro as erro:
        raise RotinaErro(f"O horário não foi gravado. {erro}") from erro
    fora_ligado = form.get("fora_ligado") == "1"
    fora_texto = str(form.get("fora_texto") or "").replace("\r\n", "\n").strip()
    if fora_texto:
        _conferir_aviso(fora_texto)
    dias = str(form.get("encerrar_dias") or "").strip()
    if dias and (_inteiro(dias) is None or _inteiro(dias) > ENCERRAR_MAXIMO_DIAS):
        raise RotinaErro(f"O encerramento automático é de 0 a {ENCERRAR_MAXIMO_DIAS} "
                         "dias (0 = nunca).")
    respostas = str(form.get("respostas") or "").replace("\r\n", "\n").strip()
    sem_barra = [n for n, linha in enumerate(respostas.splitlines(), start=1)
                 if linha.strip() and "|" not in linha]
    if sem_barra:
        raise RotinaErro("As respostas prontas são «atalho | texto», uma por linha; "
                         f"falta a barra na linha {sem_barra[0]}.")
    BALCAO.gravar_config(con, WA.CHAVE_VIGIA_SEGUNDOS, segundos)
    BALCAO.gravar_config(con, WA.CHAVE_HORARIO, horario)
    BALCAO.gravar_config(con, WA.CHAVE_FORA_HORARIO_LIGADO, "1" if fora_ligado else "")
    BALCAO.gravar_config(con, WA.CHAVE_FORA_HORARIO_TEXTO, fora_texto)
    BALCAO.gravar_config(con, WA.CHAVE_ENCERRAR_DIAS, dias)
    BALCAO.gravar_config(con, WA.CHAVE_RESPOSTAS_PRONTAS, respostas)
    if fora_ligado and not regra:
        avisos.append("O aviso de fora do horário está ligado, mas o horário está em "
                      "branco: sem horário, o aviso não sai.")
    if segundos == "0":
        avisos.append("A busca automática do servidor ficou desligada: as mensagens só "
                      "chegam pela automação (de 2 em 2 minutos, se ligada) ou pelo botão.")
    return avisos


# ------------------------------------------------------------- o aviso


def texto_do_aviso(cfg: dict, quando: datetime) -> str:
    """O aviso de fora do horário, preenchido. "" se não há o que dizer."""
    regra = cfg["regra"]
    if not regra:
        return ""
    modelo = cfg["fora_texto"] or TEXTO_FORA_PADRAO
    valores = {"horario": HOR.descrever(regra),
               "quando_abre": HOR.quando_abre(regra, quando) or "assim que possível"}
    try:
        return modelo.format(**valores).strip()
    except (KeyError, ValueError, IndexError):
        return TEXTO_FORA_PADRAO.format(**valores)


def complemento_da_passagem(cfg: dict, quando: datetime) -> str:
    """O que a passagem para pessoa acrescenta com o balcão fechado: «O
    atendimento é segunda a sexta, das 8h às 17h; respondemos amanhã (sexta) às
    8h.» "" com o balcão aberto ou sem horário."""
    regra = cfg["regra"]
    if not regra or HOR.aberto(regra, quando):
        return ""
    return (f" O atendimento é {HOR.descrever(regra)}; respondemos "
            f"{HOR.quando_abre(regra, quando) or 'assim que possível'}.")


def avisar_fora_do_horario(db: Any, *, agora: str, http_post: Callable | None = None) -> int:
    """Manda o aviso a quem escreveu com o balcão fechado. **FALA COM A REDE**.

    Uma vez por conversa e por período fechado. Não manda se a conversa já
    recebeu qualquer coisa depois da última mensagem do cliente (a IA respondeu,
    ou avisou da passagem), nem se a IA ainda vai olhar a mensagem."""
    import wa_atendente as ATENDENTE
    import wa_balcao as BALCAO
    with db.connect() as con:
        cfg = config(con)
        ia = ATENDENTE.configuracao(con)
    quando = datetime.strptime(str(agora)[:19], "%Y-%m-%dT%H:%M:%S")
    if not cfg["fora_ligado"] or not cfg["regra"] or HOR.aberto(cfg["regra"], quando):
        return 0
    fechou = HOR.fechou_em(cfg["regra"], quando)
    if fechou is None:
        return 0
    desde = fechou.strftime("%Y-%m-%dT%H:%M:%S")
    with db.connect() as con:
        candidatas = banco(con).ler(
            """SELECT c.id, c.wa_id, c.modo, m.ia_situacao
                 FROM wa_conversa c
                 JOIN wa_mensagem m ON m.id = (SELECT max(x.id) FROM wa_mensagem x
                                                WHERE x.conversa_id = c.id)
                WHERE m.direcao = 'in' AND m.criado_em >= %s
                  AND (c.fora_horario_avisado_em IS NULL
                       OR c.fora_horario_avisado_em < %s)
                ORDER BY c.id""", (desde, desde))
    texto = texto_do_aviso(cfg, quando)
    enviados = 0
    for c in candidatas:
        ia_vai_olhar = (ia["ia_ligada"] and (c.get("modo") or WA.MODO_IA) != WA.MODO_PESSOA
                        and c.get("ia_situacao") in (None, WA.IA_PROCESSANDO))
        if ia_vai_olhar or not texto:
            continue
        with db.transaction() as con:
            pegou = banco(con).escrever(
                """UPDATE wa_conversa SET fora_horario_avisado_em=%s
                    WHERE id=%s AND (fora_horario_avisado_em IS NULL
                                     OR fora_horario_avisado_em < %s)
                RETURNING id""", (agora, int(c["id"]), desde))
        if not pegou:
            continue
        try:
            with db.connect() as con:
                pedido = BALCAO.montar_envio(con, c["wa_id"], texto)
            meta_id = BALCAO.postar_envio(pedido, http_post)
        except BALCAO.EnvioErro as falha:
            LOG.warning("o aviso de fora do horário não saiu (conversa %s): %s", c["id"], falha)
            continue
        with db.transaction() as con:
            BALCAO.gravar_saida(con, int(c["id"]), texto, meta_id, autor=AUTOR_AVISO,
                                agora=agora, tipo=TIPO_AVISO)
        enviados += 1
    return enviados


# ------------------------------------------------------------- a conversa parada


def encerrar_paradas(db: Any, *, agora: str) -> int:
    """Resolve a conversa em «aguardando» (a casa respondeu por último) parada
    há N dias. ESCREVE. Nada se apaga: se o cliente voltar, ela reabre com o
    histórico, pela regra de sempre."""
    import wa_balcao as BALCAO
    import wa_fila as FILA
    with db.connect() as con:
        dias = config(con)["encerrar_dias"]
    if not dias:
        return 0
    limite = (datetime.strptime(str(agora)[:19], "%Y-%m-%dT%H:%M:%S")
              - timedelta(days=int(dias))).strftime("%Y-%m-%dT%H:%M:%S")
    with db.transaction() as con:
        bd = banco(con)
        paradas = bd.ler(
            f"""SELECT c.id FROM wa_conversa c
                 WHERE c.status = %s AND c.atualizado_em < %s
                   AND {FILA._ESPERANDO_DESDE} IS NULL""",
            (WA.AGUARDANDO, limite))
        for c in paradas:
            BALCAO.resolver(con, int(c["id"]), agora=agora)
            FILA.registrar_evento(con, int(c["id"]), FILA.EV_ENCERRADA, quando=agora,
                                  por="rotina do WhatsApp",
                                  nota=f"sem resposta do cliente há {dias} dia(s)")
    return len(paradas)

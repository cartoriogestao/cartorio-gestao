"""A PESQUISA DE SATISFAÇÃO DO BALCÃO — nota de 1 a 5 e um comentário, anônimos.

POR QUE EXISTE (26/10/2026)
    Não havia como a casa saber, com número, como o atendimento é recebido. A
    ouvidoria (`ouvidoria`) registra quem veio reclamar ou elogiar; a pesquisa
    pergunta a TODOS, um toque só, ao sair do balcão.

ONDE ELA RODA — SÓ NA REDE DA CASA
    A página `/satisfacao` abre sem login, num tablet ou celular da casa, ou
    pelo QR do convite que o atendente mostra ou imprime. O servidor não é
    exposto à internet: o QR só abre para quem está na rede da serventia (o
    Wi-Fi da casa). NÃO é tela pública: o portal do cliente, na VPS, é outro
    módulo. E a página NASCE FECHADA (`satisfacao_pagina_aberta` = 0): rota
    sem login que grava no banco é decisão do oficial, e ele a abre na tela do
    relatório.

O QUE ELA GUARDA, E O QUE NÃO GUARDA
    - a nota, o comentário (se houver) e o DIA — sem a hora: dia mais hora mais
      atendente bastariam para achar o cliente no protocolo;
    - o atendente e a atribuição, quando a avaliação veio de um convite: é o
      que o relatório por atendente pede;
    - do protocolo, só uma CHAVE (HMAC com o segredo da instalação): serve
      para a mesma ida ao balcão não ser avaliada duas vezes, e não volta ao
      número — o relatório não identifica o cliente;
    - nada do aparelho: nem IP, nem navegador.

O CONVITE É ASSINADO
    O link do QR leva o atendente e o protocolo dentro de um token assinado
    (`itsdangerous`, com o segredo da instalação). Sem a assinatura, qualquer
    um na rede poria avaliação na conta de qualquer atendente. Token vencido ou
    adulterado não derruba a avaliação: ela entra sem vínculo.

O ATENDENTE É QUEM ABRIU O PROTOCOLO (revisão de segurança, 26/10/2026)
    Até aqui o convite levava como atendente QUEM O GERAVA, de qualquer
    protocolo: o escrevente abria o convite dos protocolos do dia — inclusive
    os dos colegas —, dava nota 5 pelo celular e, como a chave do protocolo é
    única, o QR que o cliente recebesse dizia «já foi avaliado». Agora o
    atendente é `cx_protocolos.criado_por`, nunca quem gera; o escrevente só
    gera o convite dos protocolos que ele abriu, e o de outrem é do gerente e
    do oficial (`atendente_do_protocolo`). O link do tablet do balcão não leva
    atendente, e o relatório por atendente só conta a avaliação que veio do
    convite de um PROTOCOLO (`_vinculada`).

O LINK VAI SÓ AO CLIENTE — DECISÃO DO OFICIAL EM 26/10/2026
    A revisão deixou um caso aberto: o escrevente ainda gerava o convite dos
    protocolos que ele mesmo abriu, via o link e o QR na tela, e podia
    responder pelo próprio celular. O oficial decidiu: «link vai só ao
    cliente». Por isso a tela do balcão NUNCA mostra o link nem o QR com o
    token: ela põe o convite na FILA DE ENVIO AO CLIENTE
    (`ou_satisfacao_convites`), um por canal, para o telefone (WhatsApp) e o
    e-mail que estão no próprio protocolo (`cx_protocolos.telefone`/`email`),
    e mostra só «convite para o cliente registrado em …».
    - O TOKEN NÃO SE GUARDA na fila: quem enviar monta o link na hora, com
      `assinar_convite` e os dados da linha (protocolo, atendente,
      atribuição). Um link guardado no banco seria um voto pronto para quem
      lesse a tabela.
    - O ENVIO EM SI NÃO EXISTE NESTE RAMO: o sistema não tem envio de e-mail,
      e o balcão do WhatsApp (`wa_balcao`) só responde conversa que o cliente
      abriu, pelo botão do escrevente — nada se envia sozinho. O convite fica
      `NA_FILA` até haver o canal, e o relatório do oficial mostra quantos
      esperam. Nada vai a ninguém de verdade daqui.
    - Protocolo sem telefone nem e-mail do cliente não gera convite, e a tela
      diz isso.
    - O tablet do balcão (a página sem convite e sem atendente) continua.

O ENVIO PASSOU A EXISTIR — e a frase de cima («o envio em si não existe
neste ramo») ficou como história (proposta aceita pelo oficial em 26/10/2026,
«aceito a proposta, faça o PR curto»)
    O convite por E-MAIL sai pelo mesmo SMTP dos avisos de andamento ao
    cliente, numa rodada da automação que nasce DESLIGADA
    (`satisfacao_envio`). O link do e-mail NÃO aponta para este servidor, que
    continua fora da internet: aponta para a página da pesquisa na VPS, ao lado
    do portal do cliente. O servidor EMPURRA para lá só a chave do convite (o
    hash de um código que se recalcula aqui e não se guarda), a atribuição e a
    data; a VPS mostra o formulário, guarda a resposta, e o servidor a PUXA de
    volta e a grava aqui por `registrar`. O WhatsApp continua na fila, com o
    motivo: não há modelo aprovado pela Meta.
    - A fila ganhou as colunas do envio (`MIGRACOES`): as tentativas, quando
      se tentou, e a chave que foi à VPS (o hash — nunca o código, que é o
      voto pronto que a regra de cima proíbe guardar).

PostgreSQL nativo, pelo `bd_nativo`. Data calculada no Python.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import date, timedelta
from typing import Any

from bd_nativo import banco

NOTAS: dict[int, str] = {
    1: "Muito ruim",
    2: "Ruim",
    3: "Regular",
    4: "Bom",
    5: "Ótimo",
}

ORIGENS: dict[str, str] = {
    "BALCAO": "Tablet do balcão",
    "CONVITE": "Convite (QR) do atendimento",
}

CHAVE_PAGINA_ABERTA = "satisfacao_pagina_aberta"
LIMITE_DO_COMENTARIO = 1000
#: O convite vale por este tempo. Passado, a avaliação entra sem vínculo.
DIAS_DO_CONVITE = 30
SAL_DO_CONVITE = "cg-satisfacao-convite"


class SatisfacaoError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


SCHEMA: tuple[tuple[str, str], ...] = (
    ("ou_satisfacao", """
        CREATE TABLE IF NOT EXISTS ou_satisfacao (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            dia TEXT NOT NULL,
            nota integer NOT NULL CHECK (nota BETWEEN 1 AND 5),
            comentario TEXT NOT NULL DEFAULT '',
            origem TEXT NOT NULL DEFAULT 'BALCAO' CHECK (origem IN ('BALCAO', 'CONVITE')),
            atendente_id bigint,
            atribuicao TEXT NOT NULL DEFAULT '',
            protocolo_chave TEXT
        )"""),
    ("ix_ou_satisfacao_dia",
     "CREATE INDEX IF NOT EXISTS ix_ou_satisfacao_dia ON ou_satisfacao (dia)"),
    # A mesma ida ao balcão se avalia uma vez. Onde a regra pode morar no
    # banco, ela mora no banco.
    ("ux_ou_satisfacao_protocolo",
     "CREATE UNIQUE INDEX IF NOT EXISTS ux_ou_satisfacao_protocolo "
     "ON ou_satisfacao (protocolo_chave) WHERE protocolo_chave IS NOT NULL"),
    # A FILA DE ENVIO DO CONVITE AO CLIENTE (decisão do oficial, 26/10/2026):
    # uma linha por canal, para o contato do protocolo. Sem o token — o link
    # se monta na hora de enviar.
    ("ou_satisfacao_convites", """
        CREATE TABLE IF NOT EXISTS ou_satisfacao_convites (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            protocolo_id bigint NOT NULL,
            canal TEXT NOT NULL CHECK (canal IN ('WHATSAPP', 'EMAIL')),
            destino TEXT NOT NULL,
            atendente_id bigint,
            atribuicao TEXT NOT NULL DEFAULT '',
            situacao TEXT NOT NULL DEFAULT 'NA_FILA'
                CHECK (situacao IN ('NA_FILA', 'ENVIADO', 'FALHOU')),
            criado_em TEXT NOT NULL,
            criado_por bigint,
            enviado_em TEXT,
            erro TEXT
        )"""),
    # O mesmo protocolo não entra duas vezes no mesmo canal.
    ("ux_ou_satisfacao_convites_protocolo",
     "CREATE UNIQUE INDEX IF NOT EXISTS ux_ou_satisfacao_convites_protocolo "
     "ON ou_satisfacao_convites (protocolo_id, canal)"),
)


#: As colunas do ENVIO do convite (26/10/2026, `satisfacao_envio`). Só ADD
#: COLUMN: o banco que já tem a fila do PR da pesquisa as ganha sem perder nada.
#: `chave_vps` é o sha256 do código do convite — o código não se guarda.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("ou_satisfacao_convites", "tentativas", "integer NOT NULL DEFAULT 0"),
    ("ou_satisfacao_convites", "tentado_em", "TEXT"),
    ("ou_satisfacao_convites", "chave_vps", "TEXT"),
    ("ou_satisfacao_convites", "na_vps_em", "TEXT"),
)
#: Índice sobre coluna de migração: DEPOIS dela, nunca no `SCHEMA`.
INDICES_DEPOIS_DA_MIGRACAO: tuple[tuple[str, str], ...] = (
    ("ix_ou_satisfacao_convites_chave_vps",
     "CREATE INDEX IF NOT EXISTS ix_ou_satisfacao_convites_chave_vps "
     "ON ou_satisfacao_convites (chave_vps)"),
)


def init_satisfacao_schema(con) -> None:
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for _nome, comando in INDICES_DEPOIS_DA_MIGRACAO:
        bd.escrever(comando)


def pagina_aberta(get_setting) -> bool:
    return str(get_setting(CHAVE_PAGINA_ABERTA, "0") or "0").strip() == "1"


# ------------------------------------------------------------- o convite


def chave_do_protocolo(segredo: str, protocolo_id: int) -> str:
    """O que se grava do protocolo: não volta ao número."""
    return hmac.new(str(segredo).encode("utf-8"), f"cx_protocolos:{int(protocolo_id)}".encode(),
                    hashlib.sha256).hexdigest()[:40]


def _serializador(segredo: str):
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(str(segredo), salt=SAL_DO_CONVITE)


def assinar_convite(segredo: str, *, atendente_id: int | None,
                    protocolo_id: int | None = None, atribuicao: str = "") -> str:
    dados = {"a": int(atendente_id) if atendente_id else None,
             "p": int(protocolo_id) if protocolo_id else None,
             "r": str(atribuicao or "")[:20]}
    return _serializador(segredo).dumps(dados)


def ler_convite(segredo: str, token: str | None) -> dict[str, Any] | None:
    """O convite conferido, ou None (sem token, adulterado ou vencido)."""
    if not token:
        return None
    from itsdangerous import BadSignature
    try:
        dados = _serializador(segredo).loads(str(token)[:500],
                                             max_age=DIAS_DO_CONVITE * 86400)
    except (BadSignature, ValueError, TypeError):
        return None
    if not isinstance(dados, dict):
        return None
    return {"atendente_id": dados.get("a"), "protocolo_id": dados.get("p"),
            "atribuicao": dados.get("r") or ""}


def protocolo_por_numero(con, numero: str) -> dict[str, Any] | None:
    numero = " ".join(str(numero or "").split())[:40]
    if not numero:
        return None
    return banco(con).um("SELECT id, numero, atribuicao, criado_por, telefone, email "
                         "FROM cx_protocolos WHERE numero = %s", (numero,))


#: Quem gera o convite do protocolo que OUTRO atendente abriu.
GERAM_CONVITE_DE_OUTREM = ("ADMIN", "MANAGER")


def atendente_do_protocolo(protocolo, *, usuario_id: int | None, papel: str | None) -> int | None:
    """Quem vai como atendente no convite deste protocolo: quem o ABRIU no
    balcão (`cx_protocolos.criado_por`), e nunca quem gera o convite.

    O escrevente gera o convite só dos protocolos que ele abriu; o gerente e o
    oficial geram o de qualquer um — e, no protocolo que não registra quem o
    abriu (o do acervo, ou o anterior a 26/10/2026), o convite sai SEM
    atendente: a avaliação conta para a casa, e não para ninguém."""
    try:
        dono = int(protocolo["criado_por"] or 0) or None
    except (KeyError, TypeError, ValueError):
        dono = None
    if papel in GERAM_CONVITE_DE_OUTREM:
        return dono
    if dono is None:
        raise SatisfacaoError(
            "Este protocolo não registra quem o atendeu (é do acervo ou anterior ao registro). "
            "O convite dele só o gerente ou o oficial gera — e ele sai sem atendente.")
    if dono != int(usuario_id or 0):
        raise SatisfacaoError(
            "Este protocolo foi aberto por outro atendente. O convite leva quem ATENDEU: "
            "gere o dos protocolos que você abriu, ou peça ao gerente ou ao oficial.")
    return dono


def ja_avaliado(con, protocolo_chave: str | None) -> bool:
    if not protocolo_chave:
        return False
    return bool(banco(con).um("SELECT 1 FROM ou_satisfacao WHERE protocolo_chave = %s",
                              (protocolo_chave,)))


# ------------------------------------------------- a fila de envio ao cliente

CANAIS_DO_CONVITE: dict[str, str] = {"WHATSAPP": "WhatsApp", "EMAIL": "e-mail"}
SITUACOES_DO_ENVIO: dict[str, str] = {
    "NA_FILA": "na fila de envio",
    "ENVIADO": "enviado",
    "FALHOU": "o envio falhou",
}

#: Telefone que serve ao WhatsApp: DDD + número (10 ou 11 dígitos), com ou
#: sem o 55 do país na frente.
_DIGITOS_DO_TELEFONE = (10, 11, 12, 13)


def _email_valido(texto: str) -> bool:
    import re
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", texto))


def contatos_do_protocolo(protocolo) -> list[tuple[str, str]]:
    """Para onde o convite vai: o telefone (WhatsApp) e o e-mail que estão NO
    PROTOCOLO, e só eles. Lista vazia = protocolo sem contato do cliente, e
    sem contato não há convite. Só LÊ."""
    def campo(nome):
        try:
            return str(protocolo[nome] or "")
        except (KeyError, IndexError, TypeError):
            return ""
    saida: list[tuple[str, str]] = []
    digitos = "".join(ch for ch in campo("telefone") if ch.isdigit())
    if len(digitos) in _DIGITOS_DO_TELEFONE:
        saida.append(("WHATSAPP", digitos))
    email = campo("email").strip().lower()
    if email and _email_valido(email):
        saida.append(("EMAIL", email))
    return saida


def convite_do_protocolo(con, protocolo_id: int) -> list[dict[str, Any]]:
    """As linhas da fila deste protocolo, sem o destino: é o que a tela do
    balcão mostra («convite registrado em …, por WhatsApp e e-mail»). Só LÊ."""
    return [dict(x) for x in banco(con).ler(
        "SELECT id, canal, situacao, criado_em, enviado_em FROM ou_satisfacao_convites "
        "WHERE protocolo_id = %s ORDER BY id", (int(protocolo_id),))]


def enfileirar_convite(con, protocolo, *, atendente_id: int | None,
                       criado_por: int | None, agora: str) -> list[dict[str, Any]]:
    """Põe o convite deste protocolo na fila de envio AO CLIENTE, um por canal
    de contato do protocolo. GRAVA. Devolve as linhas da fila do protocolo.

    Não monta link nem token (quem envia o monta na hora), não mostra o
    destino a quem pediu e não envia nada. O mesmo protocolo não entra duas
    vezes: o segundo pedido devolve o que já está na fila."""
    ja = convite_do_protocolo(con, int(protocolo["id"]))
    if ja:
        return ja
    contatos = contatos_do_protocolo(protocolo)
    if not contatos:
        raise SatisfacaoError(
            "Este protocolo não tem telefone nem e-mail do cliente, e o convite só vai ao "
            "cliente — não se gera convite para ele. Se o cliente quiser avaliar, cadastre o "
            "telefone ou o e-mail no protocolo, ou indique o tablet do balcão.")
    bd = banco(con)
    for canal, destino in contatos:
        bd.escrever(
            "INSERT INTO ou_satisfacao_convites (protocolo_id, canal, destino, atendente_id, "
            "atribuicao, situacao, criado_em, criado_por) "
            "VALUES (%s, %s, %s, %s, %s, 'NA_FILA', %s, %s)",
            (int(protocolo["id"]), canal, destino, int(atendente_id) if atendente_id else None,
             str(protocolo["atribuicao"] or "")[:20], str(agora), criado_por))
    return convite_do_protocolo(con, int(protocolo["id"]))


def resumo_da_fila(con) -> dict[str, int]:
    """Quantos convites há em cada situação — para o relatório do oficial
    saber quantos esperam um canal de envio. Sem destino. Só LÊ."""
    contas = {k: 0 for k in SITUACOES_DO_ENVIO}
    for x in banco(con).ler("SELECT situacao, COUNT(*) AS n FROM ou_satisfacao_convites "
                            "GROUP BY situacao"):
        contas[x["situacao"]] = int(x["n"])
    return contas


# ------------------------------------------------------------- a gravação


def registrar(con, *, nota: Any, comentario: Any = "", dia: date,
              convite: dict[str, Any] | None = None,
              protocolo_chave: str | None = None) -> int:
    """Grava uma avaliação. Devolve o id. Recusa nota fora de 1–5 e a segunda
    avaliação da mesma ida ao balcão."""
    try:
        n = int(str(nota).strip())
    except (TypeError, ValueError):
        raise SatisfacaoError("Escolha uma nota de 1 a 5.") from None
    if n not in NOTAS:
        raise SatisfacaoError("Escolha uma nota de 1 a 5.")
    texto = str(comentario or "").strip()[:LIMITE_DO_COMENTARIO]
    atendente = None
    atribuicao = ""
    origem = "BALCAO"
    if convite:
        origem = "CONVITE"
        try:
            atendente = int(convite.get("atendente_id") or 0) or None
        except (TypeError, ValueError):
            atendente = None
        atribuicao = str(convite.get("atribuicao") or "")[:20]
    if protocolo_chave and ja_avaliado(con, protocolo_chave):
        raise SatisfacaoError("Este atendimento já foi avaliado. Obrigado!")
    novo = banco(con).escrever(
        "INSERT INTO ou_satisfacao (dia, nota, comentario, origem, atendente_id, atribuicao, "
        "protocolo_chave) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (dia.isoformat(), n, texto, origem, atendente, atribuicao, protocolo_chave or None))
    return int(novo[0]["id"])


# ------------------------------------------------------------- o relatório


def _media(notas: list[int]) -> float | None:
    return round(sum(notas) / len(notas), 2) if notas else None


def _vinculada(x: dict[str, Any]) -> bool:
    """A avaliação que entra na conta do atendente: a do convite de um
    PROTOCOLO, com o atendente dentro. A do tablet — inclusive a de um link
    «com atendente» gerado antes de 26/10/2026, que o próprio avaliado podia
    deixar aberto no guichê — fica «sem vínculo»."""
    return bool(x["origem"] == "CONVITE" and x["protocolo_chave"] and x["atendente_id"])


def relatorio(con, *, de: str, ate: str) -> dict[str, Any]:
    linhas = banco(con).ler(
        """SELECT s.dia, s.nota, s.comentario, s.origem, s.atendente_id, s.atribuicao,
                  s.protocolo_chave, u.full_name AS atendente_nome
             FROM ou_satisfacao s LEFT JOIN users u ON u.id = s.atendente_id
            WHERE s.dia >= %s AND s.dia <= %s
            ORDER BY s.dia DESC, s.id DESC""", (str(de)[:10], str(ate)[:10]))
    notas = [int(x["nota"]) for x in linhas]
    por_atendente: dict[Any, dict[str, Any]] = {}
    for x in linhas:
        vinculada = _vinculada(x)
        chave = x["atendente_id"] if vinculada else 0
        item = por_atendente.setdefault(chave, {
            "atendente_id": x["atendente_id"] if vinculada else None,
            "nome": ((x["atendente_nome"] or f"usuário #{x['atendente_id']}") if vinculada
                     else "— sem vínculo a protocolo (tablet do balcão)"),
            "notas": []})
        item["notas"].append(int(x["nota"]))
    atendentes = sorted(
        ({"atendente_id": v["atendente_id"], "nome": v["nome"], "total": len(v["notas"]),
          "media": _media(v["notas"])} for v in por_atendente.values()),
        key=lambda v: (v["atendente_id"] is None, v["nome"]))
    por_atribuicao: dict[str, list[int]] = {}
    for x in linhas:
        por_atribuicao.setdefault(x["atribuicao"] or "—", []).append(int(x["nota"]))
    return {
        "de": str(de)[:10], "ate": str(ate)[:10],
        "total": len(notas), "media": _media(notas),
        "distribuicao": [{"nota": k, "nome": v, "total": notas.count(k)}
                         for k, v in sorted(NOTAS.items(), reverse=True)],
        "por_atendente": atendentes,
        "por_atribuicao": [{"atribuicao": k, "total": len(v), "media": _media(v)}
                           for k, v in sorted(por_atribuicao.items())],
        "comentarios": [{"dia": x["dia"], "nota": x["nota"], "comentario": x["comentario"],
                         "atendente_nome": (x["atendente_nome"] or "") if _vinculada(x) else "",
                         "atribuicao": x["atribuicao"]}
                        for x in linhas if x["comentario"]],
    }


def numeros_do_painel(con, *, hoje: date | None = None) -> dict[str, Any]:
    hoje = hoje or date.today()
    inicio = (hoje - timedelta(days=30)).isoformat()
    notas = [int(x["nota"]) for x in banco(con).ler(
        "SELECT nota FROM ou_satisfacao WHERE dia >= %s", (inicio,))]
    return {"total_30_dias": len(notas), "media_30_dias": _media(notas),
            "notas_baixas_30_dias": sum(1 for n in notas if n <= 2)}

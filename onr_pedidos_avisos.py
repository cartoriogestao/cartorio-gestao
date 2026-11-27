"""OS PEDIDOS DO ONR PARADOS — o aviso vai a quem faz o trabalho, e não à checklist (A005).

    «Agora temos integração ONR, podemos utilizar essa informação para cobrar
     cumprimento dos escreventes. Como os protocolos do ONR e pedidos de
     certidões por lá dependem do trabalho da [escrevente do RI], não adianta
     manter em checklist do dia (que é de responsabilidade do admin e do
     gestor), portanto tire de lá e coloque a automação para verificar com
     frequência esses protocolos e criar avisos para [ela]. No primeiro dia
     pode ser um aviso simples na tela, a partir do segundo criar o aviso da
     barra vermelha chamativa que fica ali até que ela dê andamento no pedido
     da ONR.»                                       — o oficial, 26/11/2026
    E, no mesmo dia: «Conferir e-Protocolo, SAEC e intimações do ONR tbm entram
    na mesma lógica».

DE ONDE VÊM OS PEDIDOS, E O QUE É «SEM ANDAMENTO»
    CERTIDAO    `onr_cert_pedidos` (o Ofício Eletrônico) e a etapa do robô em
                `onr_cert_auto`. Parado: o pedido ainda NOVO (nenhum anexo
                guardado, nada enviado) e, quando o robô já o viu, numa etapa
                que espera gente — custas a aprovar, a revisar e aprovar, fazer
                à mão, erro. Andamento: custas aprovadas ou informadas,
                aguardando o pagamento do cliente, emitida (com ou sem selo),
                enviada, respondida, devolvida, fechada no ONR.
    EPROTOCOLO  `onr_ep_pedidos` (RI013, P1). Parado: `A_PRENOTAR`. Andamento:
                prenotado (no ONR ou aqui, pela P2a — a coluna `prenotacao_id`,
                quando existe), calculado, em exigência, reaberto, aguardando o
                pagamento, prazo suspenso, registrado, devolvido, cancelado.
    SAEC        o atendimento eletrônico do ONR (`onr_saec`). NÃO se guarda no
                banco — a tela lê a lista direto da API —, e por isso a rodada
                a lê também, SÓ COM GET. Parado: as situações em que a vez é
                da casa (`onr_saec.ESPERAM_A_CASA`: em aberto, reaberto,
                respondido pelo solicitante). Sem a credencial da API REST do
                ONR, o SAEC fica «não medido», e o relato diz isso.
    INTIMACAO   a e-Intimação do WSOfício: o transporte está na PR #531 (RI013
                B0), e nenhuma leitura grava as intimações ainda. A fonte está
                declarada (`FONTES`) e fica «não medida» até existir a tabela —
                a casa não vê «zero» onde ninguém olhou.

A ESCALA, POR PEDIDO, EM DIAS ÚTEIS
    O dia em que o pedido parou (ou o dia útil seguinte, se ele chegou no fim
    de semana ou no feriado) é o 1º dia: aviso simples na tela da responsável.
    A partir do 2º dia útil sem andamento: faixa vermelha em TODA tela dela,
    que ela não fecha. O calendário é o da casa: os feriados nacionais
    (`ri_schema`) e os locais de Configurações (`ri_feriados_locais`).

O AVISO É GRAVADO, E A TELA SÓ LÊ
    A rodada (`verificar_os_pedidos`) cria ou atualiza o aviso de cada pedido parado e
    ENCERRA, com o motivo, o aviso do pedido que andou. Quem desenha a faixa
    lê `onr_pedidos_avisos`, uma consulta por requisição. Fonte que não se
    mediu nesta rodada não encerra aviso nenhum: «não mediu» não é «andou».

QUEM RECEBE
    O usuário de `CHAVE_RESPONSAVEL` (Administrativo → Configurações). Vazio,
    inativo ou robô: o primeiro ADMIN humano ativo — e o relato diz isso. Não
    há nome de pessoa no código.

O QUE ISTO NÃO FAZ
    Não manda nada ao ONR, não mexe no pedido, não prenota, não emite, não
    cobra. Escreve só em `onr_pedidos_avisos`. Por isso não depende do «pode
    agir» (é a régua da CNIB: abrir aviso interno não é agir sobre o ato).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable

from bd_nativo import banco

CODIGO_DO_PROCESSO = "RI_ONR_PEDIDOS_AVISOS"
CHAVE_RESPONSAVEL = "onr_pedidos_responsavel_id"

CERTIDAO, EPROTOCOLO, SAEC, INTIMACAO = "CERTIDAO", "EPROTOCOLO", "SAEC", "INTIMACAO"
#: As fontes, na ordem da tela: (código, rótulo).
FONTES: tuple[tuple[str, str], ...] = (
    (CERTIDAO, "Certidão pedida pelo ONR"),
    (EPROTOCOLO, "Título do e-Protocolo"),
    (SAEC, "Atendimento do SAEC"),
    (INTIMACAO, "e-Intimação"),
)
ROTULO_DA_FONTE = dict(FONTES)

SIMPLES, FAIXA = "SIMPLES", "FAIXA"
#: A partir de quantos dias úteis passados do 1º dia o aviso vira faixa.
DIAS_PARA_A_FAIXA = 1

#: As etapas do robô das certidões que esperam a escrevente. `SEM_SELO` fica
#: de fora: a certidão já saiu (é andamento), e o selo é a tela dela.
ETAPAS_PARADAS = frozenset({"CUSTAS_A_APROVAR", "A_REVISAR", "A_MAO", "ERRO"})
#: O ONR diz que espera o cliente pagar: a vez não é da casa.
_STATUS_ESPERA_O_CLIENTE = frozenset({"11", "aguardando pagamento"})
#: e-Protocolo: aguardando pagamento (9) e prazo suspenso (100) esperam outro.
STATUS_EP_DE_FORA = frozenset({9, 100})
#: Quantas páginas de 50 a rodada lê do SAEC, por situação.
PAGINAS_DO_SAEC = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS onr_pedidos_avisos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    fonte TEXT NOT NULL,
    ref_id bigint NOT NULL,
    protocolo TEXT NOT NULL DEFAULT '',
    descricao TEXT NOT NULL DEFAULT '',
    endpoint TEXT NOT NULL,
    desde TEXT NOT NULL,
    primeiro_dia TEXT NOT NULL,
    dias_uteis INTEGER NOT NULL DEFAULT 0,
    nivel TEXT NOT NULL,
    user_id bigint,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    faixa_desde TEXT,
    encerrado_em TEXT,
    motivo_encerramento TEXT,
    UNIQUE (fonte, ref_id)
);
CREATE INDEX IF NOT EXISTS ix_onr_pedidos_avisos_abertos
    ON onr_pedidos_avisos (user_id, encerrado_em);

CREATE TABLE IF NOT EXISTS onr_pedidos_verificacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    em TEXT NOT NULL,
    origem TEXT NOT NULL,
    user_id bigint,
    responsavel_de TEXT NOT NULL,
    medidas TEXT NOT NULL,
    nao_medidas TEXT NOT NULL,
    abertos INTEGER NOT NULL,
    faixas INTEGER NOT NULL,
    novos INTEGER NOT NULL,
    encerrados INTEGER NOT NULL
);
"""

ORIGEM_ROBO, ORIGEM_TELA = "ROBO", "TELA"
MOTIVO_ANDOU = "o pedido teve andamento"
MOTIVO_SUMIU = "o pedido não está mais na fonte"


class AvisosOnrError(ValueError):
    """Recusa com frase pronta para a tela."""


def init_schema(con) -> None:
    banco(con).escrever(SCHEMA)


# ------------------------------------------------------------------ as datas


def _dia(texto: Any) -> date | None:
    """A data de um texto do ONR ou do banco: «aaaa-mm-dd…» ou «dd/mm/aaaa…»."""
    t = str(texto or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", t)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


def feriados_da_casa(leitor: Callable[[str, str], Any]) -> set[date]:
    """Os feriados locais de Configurações. `leitor` é `db.get_setting` ou `ctx.setting`."""
    from ri_schema import ler_feriados_locais
    return ler_feriados_locais(str(leitor("ri_feriados_locais", "") or ""))


def primeiro_dia_util(dia: date, feriados: set[date] | None = None) -> date:
    """O próprio dia, se útil; senão o dia útil seguinte."""
    from ri_schema import eh_dia_util
    while not eh_dia_util(dia, feriados):
        dia += timedelta(days=1)
    return dia


def escala(desde: date, hoje: date, feriados: set[date] | None = None) -> dict:
    """Em que degrau está o pedido parado desde `desde`. Só calcula.

    `dias_uteis` são os dias úteis passados depois do 1º dia; zero é o 1º dia
    (ou antes dele, no fim de semana em que chegou).
    """
    from ri_schema import dias_uteis_entre
    primeiro = primeiro_dia_util(desde, feriados)
    dias = max(0, dias_uteis_entre(primeiro, hoje, feriados)) if hoje >= primeiro else 0
    return {"primeiro_dia": primeiro, "dias_uteis": dias,
            "nivel": FAIXA if dias >= DIAS_PARA_A_FAIXA else SIMPLES}


# ------------------------------------------------------------------ quem recebe


def _humanos_ativos(bd) -> str:
    robo = " AND COALESCE(eh_robo, 0) = 0" if bd.tem_coluna("users", "eh_robo") else ""
    return f"active = 1{robo}"


def usuarios_que_podem_receber(con) -> list[dict]:
    """A lista da tela de Configurações: as pessoas ativas (sem robô). Só LÊ."""
    bd = banco(con)
    return [dict(r) for r in bd.ler(
        f"SELECT id, username, full_name, role FROM users WHERE {_humanos_ativos(bd)} "
        "ORDER BY full_name, id")]


def responsavel(con, leitor: Callable[[str, str], Any]) -> dict:
    """Quem recebe os avisos: {user_id, nome, de_onde}. Só LÊ.

    `de_onde`: CONFIGURADO, ou ADMIN (configuração vazia, inválida, inativa ou
    robô — e `motivo` diz qual), ou NINGUEM (nem ADMIN humano ativo há).
    """
    bd = banco(con)
    bruto = str(leitor(CHAVE_RESPONSAVEL, "") or "").strip()
    motivo = "a configuração está vazia"
    if bruto:
        if bruto.isdigit():
            r = bd.um(f"SELECT id, full_name FROM users WHERE id = %s AND {_humanos_ativos(bd)}",
                      (int(bruto),))
            if r:
                return {"user_id": int(r["id"]), "nome": r["full_name"], "de_onde": "CONFIGURADO",
                        "motivo": ""}
            motivo = "o usuário configurado não está ativo (ou é robô)"
        else:
            motivo = "a configuração não é um usuário"
    r = bd.um(f"SELECT id, full_name FROM users WHERE role = 'ADMIN' AND {_humanos_ativos(bd)} "
              "ORDER BY id LIMIT 1")
    if r:
        return {"user_id": int(r["id"]), "nome": r["full_name"], "de_onde": "ADMIN",
                "motivo": motivo}
    return {"user_id": None, "nome": "", "de_onde": "NINGUEM", "motivo": motivo}


def guardar_responsavel(con, valor: Any) -> str:
    """Confere o usuário escolhido e devolve o valor a gravar ('' = o ADMIN). Só LÊ.

    Quem grava é a rota, com a auditoria."""
    t = str(valor or "").strip()
    if not t:
        return ""
    if not t.isdigit():
        raise AvisosOnrError("Escolha uma pessoa da lista.")
    bd = banco(con)
    if not bd.um(f"SELECT 1 AS um FROM users WHERE id = %s AND {_humanos_ativos(bd)}", (int(t),)):
        raise AvisosOnrError("Essa pessoa não está ativa no sistema (ou é robô).")
    return t


# ------------------------------------------------------------------ os pedidos parados


def _parado(fonte: str, ref_id: int, protocolo: Any, descricao: str, endpoint: str,
            desde: date) -> dict:
    return {"fonte": fonte, "ref_id": int(ref_id), "protocolo": str(protocolo or "")[:120],
            "descricao": descricao[:300], "endpoint": endpoint, "desde": desde}


def certidoes_paradas(con, ambiente: str | None = None) -> list[dict]:
    """Os pedidos de certidão do ONR sem andamento. Só LÊ.

    Devolve None quando a tabela não existe (a fonte não se mede)."""
    bd = banco(con)
    if not bd.tem_tabela("onr_cert_pedidos"):
        return None
    preparos: dict[int, dict] = {}
    if bd.tem_tabela("onr_cert_auto"):
        pago = (", pagamento_depois_de" if bd.tem_coluna("onr_cert_auto", "pagamento_depois_de")
                else "")
        preparos = {int(r["pedido_id"]): dict(r) for r in bd.ler(
            f"SELECT pedido_id, etapa{pago} FROM onr_cert_auto")}
    onde, args = "situacao = 'NOVO'", []
    if ambiente:
        onde += " AND ambiente = %s"
        args.append(ambiente)
    saida = []
    for p in bd.ler(f"SELECT id, protocolo, tipo_certidao, matricula_numero, status_onr, "
                    f"data_pedido, recebido_em FROM onr_cert_pedidos WHERE {onde} ORDER BY id",
                    tuple(args)):
        a = preparos.get(int(p["id"]))
        if a and a.get("etapa") not in ETAPAS_PARADAS:
            continue
        if str(p["status_onr"] or "").strip().lower() in _STATUS_ESPERA_O_CLIENTE:
            continue
        desde = (_dia((a or {}).get("pagamento_depois_de")) or _dia(p["data_pedido"])
                 or _dia(p["recebido_em"]))
        if desde is None:
            continue
        o_que = "certidão" + (f" da matrícula {p['matricula_numero']}" if p["matricula_numero"]
                              else "")
        if a:
            import onr_certidoes_auto as AUTO
            o_que += f" — {AUTO.NOME_DA_ETAPA.get(a['etapa'], a['etapa'])}"
        saida.append(_parado(CERTIDAO, p["id"], p["protocolo"], o_que,
                             "onr_auto_pedido" if a else "onr_certidao_ficha", desde))
    return saida


def eprotocolo_parados(con, ambiente: str | None = None) -> list[dict] | None:
    """Os títulos do e-Protocolo do RI esperando prenotação. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("onr_ep_pedidos"):
        return None
    onde, args = "situacao = 'A_PRENOTAR'", []
    if bd.tem_coluna("onr_ep_pedidos", "prenotacao_id"):     # a P2a (PR #534)
        onde += " AND prenotacao_id IS NULL"
    if ambiente:
        onde += " AND ambiente = %s"
        args.append(ambiente)
    saida = []
    for p in bd.ler(f"SELECT id, protocolo, id_contrato, id_status, tipo_servico, data_remessa, "
                    f"data_solicitacao, recebido_em FROM onr_ep_pedidos WHERE {onde} ORDER BY id",
                    tuple(args)):
        if p["id_status"] in STATUS_EP_DE_FORA:
            continue
        desde = _dia(p["data_remessa"]) or _dia(p["data_solicitacao"]) or _dia(p["recebido_em"])
        if desde is None:
            continue
        saida.append(_parado(EPROTOCOLO, p["id"], p["protocolo"] or p["id_contrato"],
                             "título a prenotar"
                             + (f" ({p['tipo_servico']})" if p["tipo_servico"] else ""),
                             "onr_eprotocolo_ficha", desde))
    return saida


def saec_da_resposta(paginas: Iterable[Any]) -> list[dict]:
    """Os atendimentos do SAEC em que a vez é da casa, das respostas da API. Só calcula.

    Não guarda nome, CPF nem e-mail de quem pediu: o aviso leva o protocolo e
    o tipo, e a ficha do atendimento mostra o resto."""
    import onr_saec as SAECM
    saida, vistos = [], set()
    for resposta in paginas:
        for d in SAECM._lista(resposta, "dados")["itens"]:
            if not isinstance(d, dict):
                continue
            ident = SAECM._inteiro(d.get("id"))
            codigo = SAECM._inteiro(d.get("status"))
            if ident is None or ident in vistos or codigo not in SAECM.ESPERAM_A_CASA:
                continue
            desde = _dia(d.get("dataAtualizacao")) or _dia(d.get("dataCadastro"))
            if desde is None:
                continue
            vistos.add(ident)
            tipo = SAECM._rotulo(SAECM.TIPOS, d.get("tipoAtendimento"),
                                 d.get("tipoAtendimentoDescricao"))
            situacao = SAECM._rotulo(SAECM.SITUACOES, d.get("status"), d.get("statusDescricao"))
            saida.append(_parado(SAEC, ident, d.get("protocolo"),
                                 f"{tipo} — {situacao.lower()}", "onr_saec_ficha", desde))
    return saida


def ler_saec(*, pasta=None, buscar: Callable[..., Any] | None = None) -> list[dict]:
    """A rede: os atendimentos do SAEC que esperam a casa. SÓ GET. Sobe o erro."""
    import onr_api as API
    import onr_saec as SAECM
    buscar = buscar or API.atendimentos
    paginas = []
    for status in sorted(SAECM.ESPERAM_A_CASA):
        for pagina in range(1, PAGINAS_DO_SAEC + 1):
            resposta = buscar(pagina=pagina, por_pagina=50, status=status, pasta=pasta)
            paginas.append(resposta)
            lista = SAECM._lista(resposta, "dados")
            if lista["estranha"]:
                raise AvisosOnrError("a resposta do SAEC não veio no formato do contrato")
            if pagina >= (lista["paginas"] or 1) or not lista["itens"]:
                break
    return saec_da_resposta(paginas)


def intimacoes_paradas(con) -> list[dict] | None:
    """A e-Intimação. Nenhuma leitura grava as intimações ainda (o transporte
    está na PR #531): a fonte fica «não medida» até a tabela existir."""
    return None


# ------------------------------------------------------------------ a rodada


def _iso(agora: datetime) -> str:
    return agora.replace(microsecond=0).isoformat()


def sincronizar(con, parados: list[dict], medidas: Iterable[str], *, hoje: date,
                agora: datetime, feriados: set[date] | None, user_id: int | None) -> dict:
    """Cria, atualiza e encerra os avisos. ESCREVE só em `onr_pedidos_avisos`.

    Só encerra aviso de fonte que se mediu nesta rodada."""
    init_schema(con)
    bd = banco(con)
    medidas = set(medidas)
    quando = _iso(agora)
    novos = atualizados = 0
    vistos: set[tuple[str, int]] = set()
    for p in parados:
        vistos.add((p["fonte"], p["ref_id"]))
        e = escala(p["desde"], hoje, feriados)
        faixa_desde = quando if e["nivel"] == FAIXA else None
        r = bd.um("SELECT id, encerrado_em, faixa_desde FROM onr_pedidos_avisos "
                  "WHERE fonte = %s AND ref_id = %s", (p["fonte"], p["ref_id"]))
        if r is None:
            bd.escrever(
                """INSERT INTO onr_pedidos_avisos (fonte, ref_id, protocolo, descricao, endpoint,
                       desde, primeiro_dia, dias_uteis, nivel, user_id, criado_em, atualizado_em,
                       faixa_desde)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (p["fonte"], p["ref_id"], p["protocolo"], p["descricao"], p["endpoint"],
                 p["desde"].isoformat(), e["primeiro_dia"].isoformat(), e["dias_uteis"],
                 e["nivel"], user_id, quando, quando, faixa_desde))
            novos += 1
            continue
        reaberto = r["encerrado_em"] is not None
        # A faixa guarda desde quando está acesa; volta a nascer se o aviso reabriu.
        if e["nivel"] != FAIXA:
            faixa_desde = None
        elif r["faixa_desde"] and not reaberto:
            faixa_desde = r["faixa_desde"]
        bd.escrever(
            """UPDATE onr_pedidos_avisos SET protocolo=%s, descricao=%s, endpoint=%s, desde=%s,
                   primeiro_dia=%s, dias_uteis=%s, nivel=%s, user_id=%s, atualizado_em=%s,
                   faixa_desde=%s, encerrado_em=NULL, motivo_encerramento=NULL
                 WHERE id=%s""",
            (p["protocolo"], p["descricao"], p["endpoint"], p["desde"].isoformat(),
             e["primeiro_dia"].isoformat(), e["dias_uteis"], e["nivel"], user_id, quando,
             faixa_desde, r["id"]))
        if reaberto:
            bd.escrever("UPDATE onr_pedidos_avisos SET criado_em=%s WHERE id=%s", (quando, r["id"]))
        novos += 1 if reaberto else 0
        atualizados += 0 if reaberto else 1
    encerrados = 0
    for r in bd.ler("SELECT id, fonte, ref_id FROM onr_pedidos_avisos WHERE encerrado_em IS NULL"):
        if r["fonte"] in medidas and (r["fonte"], int(r["ref_id"])) not in vistos:
            bd.escrever("UPDATE onr_pedidos_avisos SET encerrado_em=%s, motivo_encerramento=%s, "
                        "atualizado_em=%s WHERE id=%s", (quando, MOTIVO_ANDOU, quando, r["id"]))
            encerrados += 1
    abertos = bd.ler("SELECT nivel FROM onr_pedidos_avisos WHERE encerrado_em IS NULL")
    return {"novos": novos, "atualizados": atualizados, "encerrados": encerrados,
            "abertos": len(abertos), "faixas": sum(1 for a in abertos if a["nivel"] == FAIXA)}


def verificar_os_pedidos(db, *, agora: datetime, origem: str = ORIGEM_ROBO, pasta=None,
              buscar_saec: Callable[..., Any] | None = None,
              tem_credencial_saec: Callable[[], bool] | None = None) -> dict:
    """Uma verificação: lê as fontes, grava os avisos. A rede (SAEC) fica FORA
    da transação. Devolve {medidas, nao_medidas: {fonte: motivo}, responsavel,
    novos, encerrados, abertos, faixas, parados}."""
    import onr_api as API
    import onr_eprotocolo as EP
    hoje = agora.date()
    nao_medidas: dict[str, str] = {}
    parados: list[dict] = []
    # A REDE PRIMEIRO, fora de transação.
    tem = tem_credencial_saec or (lambda: API.tem_credencial(pasta=pasta))
    if not tem():
        nao_medidas[SAEC] = "sem a credencial da API REST do ONR"
    else:
        try:
            parados += ler_saec(pasta=pasta, buscar=buscar_saec)
        except Exception as erro:                       # noqa: BLE001 — a fonte não se mediu
            nao_medidas[SAEC] = f"{type(erro).__name__}: {erro}"[:300]
    with db.connect() as con:
        import onr_wsoficio as WS
        # O ambiente é o das telas: pedido de homologação não cobra ninguém.
        amb_cert = str(db.get_setting("onr_certidoes_ambiente", "") or "").strip() or WS.PRODUCAO
        amb_ep = EP.ambiente(db.get_setting)
        for fonte, ler in ((CERTIDAO, lambda: certidoes_paradas(con, amb_cert)),
                           (EPROTOCOLO, lambda: eprotocolo_parados(con, amb_ep)),
                           (INTIMACAO, lambda: intimacoes_paradas(con))):
            lista = ler()
            if lista is None:
                nao_medidas[fonte] = ("a leitura das intimações ainda não existe (PR #531)"
                                      if fonte == INTIMACAO else "a tabela da fonte não existe")
            else:
                parados += lista
        quem = responsavel(con, db.get_setting)
        feriados = feriados_da_casa(db.get_setting)
    medidas = [f for f, _ in FONTES if f not in nao_medidas]
    with db.transaction() as con:
        r = sincronizar(con, parados, medidas, hoje=hoje, agora=agora, feriados=feriados,
                        user_id=quem["user_id"])
        banco(con).escrever(
            """INSERT INTO onr_pedidos_verificacoes (em, origem, user_id, responsavel_de, medidas,
                   nao_medidas, abertos, faixas, novos, encerrados)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (_iso(agora), origem, quem["user_id"], quem["de_onde"], ",".join(medidas),
             "; ".join(f"{f}: {m}" for f, m in nao_medidas.items()), r["abertos"], r["faixas"],
             r["novos"], r["encerrados"]))
    return {**r, "medidas": medidas, "nao_medidas": nao_medidas, "responsavel": quem,
            "parados": len(parados)}


def relato(r: dict) -> str:
    """O relato para a central: em números, sem nome de parte."""
    quem = r["responsavel"]
    para = {"CONFIGURADO": "a pessoa configurada",
            "ADMIN": f"o ADMIN ({quem['motivo']})",
            "NINGUEM": "ninguém: não há ADMIN ativo"}[quem["de_onde"]]
    texto = (f"{r['abertos']} pedido(s) do ONR parado(s), {r['faixas']} com a faixa vermelha; "
             f"{r['novos']} aviso(s) novo(s), {r['encerrados']} encerrado(s) porque o pedido andou. "
             f"Os avisos vão para {para}.")
    if r["nao_medidas"]:
        texto += " Não medido: " + "; ".join(
            f"{ROTULO_DA_FONTE[f]} ({m})" for f, m in r["nao_medidas"].items()) + "."
    return texto


#: O processo da central de automação (`automacao_processos.MODULOS_COM_PROCESSOS`).
CATALOGO = (
    {"codigo": CODIGO_DO_PROCESSO, "nome": "ONR — avisos dos pedidos parados (escrevente do RI)",
     "setor": "RI", "funcao": "onr_pedidos_avisos.rodada_dos_avisos", "robo_oficial": "RI",
     "timeout_s": 300,
     "agenda": {"dias": [0, 1, 2, 3, 4], "intervalo_min": 30, "janela": ["08:00", "18:00"]},
     "descricao": "A cada 30 minutos nos dias úteis, das 8h às 18h: confere os pedidos de "
                  "certidão do ONR, os títulos do e-Protocolo e os atendimentos do SAEC sem "
                  "andamento e avisa a responsável (Configurações → Responsável pelos pedidos "
                  "do ONR; vazio, o ADMIN). No 1º dia útil, aviso simples na tela; do 2º em "
                  "diante, faixa vermelha em toda tela até o pedido andar. NÃO manda nada ao "
                  "ONR e não mexe no pedido; escreve só os avisos."},
)


def rodada_dos_avisos(ctx) -> dict:
    """O processo RI_ONR_PEDIDOS_AVISOS: uma verificação.

    OK quando mediu, ainda que haja pedido parado: a cobrança é da escrevente,
    e AVISO aqui abriria tarefa para o responsável do processo (o admin) — o
    contrário do que o oficial pediu. ERRO quando nenhuma fonte se mediu."""
    import automacao_processos as PROC
    import automacao_schema as SCH
    try:
        r = verificar_os_pedidos(ctx.db, agora=ctx.agora, origem=ORIGEM_ROBO, pasta=ctx.pasta_dados)
    except Exception as erro:                           # noqa: BLE001
        return PROC._nao_mediu("os pedidos do ONR", erro)
    achados = [{"abertos": r["abertos"], "faixas": r["faixas"], "medidas": r["medidas"],
                "nao_medidas": r["nao_medidas"], "responsavel_de": r["responsavel"]["de_onde"]}]
    acoes = ([{"acao": "avisos dos pedidos do ONR", "novos": r["novos"],
               "encerrados": r["encerrados"]}] if r["novos"] or r["encerrados"] else [])
    # A e-Intimação ainda não tem leitura: ela sozinha «não medida» não é queda.
    situacao = SCH.OK if set(r["medidas"]) - {INTIMACAO} else SCH.ERRO
    if situacao == SCH.OK and r["responsavel"]["de_onde"] == "NINGUEM":
        situacao = SCH.AVISO
    return PROC.resultado(situacao, relato(r), achados, acoes)


def repassar(con, user_id: int | None) -> int:
    """Os avisos abertos passam a `user_id` (a configuração mudou). ESCREVE."""
    init_schema(con)
    bd = banco(con)
    bd.escrever("UPDATE onr_pedidos_avisos SET user_id = %s WHERE encerrado_em IS NULL",
                (user_id,))
    return bd.linhas_afetadas


# ------------------------------------------------------------------ o que as telas leem


def avisos_de(con, user_id: int | None) -> dict:
    """Os avisos abertos desta pessoa: {faixa: [...], simples: [...]}. Só LÊ."""
    bd = banco(con)
    if not user_id or not bd.tem_tabela("onr_pedidos_avisos"):
        return {"faixa": [], "simples": []}
    linhas = [dict(r) for r in bd.ler(
        "SELECT * FROM onr_pedidos_avisos WHERE encerrado_em IS NULL AND user_id = %s "
        "ORDER BY desde, id", (int(user_id),))]
    return {"faixa": [a for a in linhas if a["nivel"] == FAIXA],
            "simples": [a for a in linhas if a["nivel"] != FAIXA]}


def quadro(con, leitor: Callable[[str, str], Any]) -> dict:
    """A tela dos avisos: os abertos (de todos), os encerrados recentes, quem
    recebe e a última verificação. Só LÊ."""
    bd = banco(con)
    vazio = {"abertos": [], "encerrados": [], "ultima": None}
    if bd.tem_tabela("onr_pedidos_avisos"):
        vazio["abertos"] = [dict(r) for r in bd.ler(
            "SELECT a.*, u.full_name AS para FROM onr_pedidos_avisos a "
            "LEFT JOIN users u ON u.id = a.user_id WHERE a.encerrado_em IS NULL "
            "ORDER BY (a.nivel <> 'FAIXA'), a.desde, a.id")]
        vazio["encerrados"] = [dict(r) for r in bd.ler(
            "SELECT * FROM onr_pedidos_avisos WHERE encerrado_em IS NOT NULL "
            "ORDER BY encerrado_em DESC, id DESC LIMIT 30")]
    if bd.tem_tabela("onr_pedidos_verificacoes"):
        u = bd.um("SELECT * FROM onr_pedidos_verificacoes ORDER BY id DESC LIMIT 1")
        vazio["ultima"] = dict(u) if u else None
    return {**vazio, "responsavel": responsavel(con, leitor)}

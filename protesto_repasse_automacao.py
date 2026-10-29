"""A GUIA DE REPASSE NO HUB DA AUTOMAÇÃO — a relação do dia nasce sozinha.

Pedido do oficial (29/10/2026): «precisa também emitir automático a guia de
repasse do título pago no cartório pela CRA e CENPROT».

O QUE SE MEDIU ANTES, E QUE DECIDE O DESENHO
    Nenhuma das duas Centrais tem por onde EMITIR a guia: a API da CENPROT
    para o cartório não tem guia, boleto nem liquidação; a da Intimação
    Digital só fala do pagamento do devedor; o WSDL da CRA-MA não tem
    operação de repasse. A guia sai do PORTAL (a liquidação dos títulos pagos
    da CENPROT; o boleto de repasse da CRA-MA). O detalhe está no docstring de
    `protesto_repasse`.

O PROCESSO
    O BOLETO DA CRA NASCE DO RETORNO (lido no portal da CRA-MA em 29/10/2026,
    menu Retorno → «Boletos de repasse»): o pagamento da CRA só entra na
    relação depois que o retorno com o «pago» foi aceito; antes, ele é contado
    como «esperando o retorno».

    PROTESTO_REPASSE_GUIA — no horário da agenda (de fábrica, 08:00 e 17:00
    nos dias úteis; o oficial muda na central de automação), gera a RELAÇÃO
    de cada Central com os pagamentos que ainda não estão em guia
    (`protesto_repasse.gerar_guias_do_dia`), e conta o que espera o portal.
    A das 17:00 põe na relação o pagamento do dia, no próprio dia; a das
    08:00 apanha o que entrou depois — e o prazo é o primeiro dia útil
    seguinte (Lei 9.492/1997, art. 19, § 2º).

    Gerar a relação é «o que é da casa», e por isso só com `pode_agir`:
    desligado, ele lê e conta, e diz o que faria. NUNCA fala com o banco nem
    com a Central, e não tem credencial nenhuma.

    A RELAÇÃO NÃO É O REPASSE. Ela é o que o escrevente leva ao portal. O
    pagamento continua cobrado — no roteiro, na tela e aqui — até a guia ser
    registrada e paga; por isso a rodada termina em AVISO enquanto houver guia
    esperando o portal, e em ERRO, com o motivo, quando não conseguiu gerar.
    Nunca em silêncio.

O RELATO FALA EM NÚMEROS (o contrato do hub): número da guia, Central,
quantidade, valor e prazo. Nome de apresentante e de devedor ficam no banco.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import protesto_repasse as REP
from bd_nativo import banco
from caixa_schema import reais

CODIGO = "PROTESTO_REPASSE_GUIA"
#: Quem aparece em `gerada_por` da guia que a rotina gerou.
QUEM_GERA = "automação (rotina da guia de repasse)"
#: O nome do robô na auditoria (`audit_logs.agente`).
AGENTE = "automação — guia de repasse do Protesto"

CATALOGO = (
    {"codigo": CODIGO,
     "nome": "Protesto — relação da guia de repasse (CRA e CENPROT)",
     "setor": "PROTESTO",
     "funcao": "protesto_repasse_automacao.gerar_a_relacao_do_dia",
     "timeout_s": 120,
     "agenda": {"dias": [0, 1, 2, 3, 4], "horarios": ["08:00", "17:00"]},
     "descricao": (
         "Gera sozinha, no dia do pagamento, a relação da guia de repasse ao "
         "IEPTB — uma por Central (CRA e CENPROT) — com os títulos pagos que "
         "ainda não estão em guia, e conta o que espera o portal. A guia em si "
         "se emite no portal da Central (nenhuma das duas tem API para isso). "
         "Só gera com «pode agir»; desligado, conta.")},
)


def _br(dia: Any) -> str:
    texto = str(dia or "")[:10]
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) == 10 else "—"


def _auditar(contexto, g: dict) -> None:
    """A guia que a rodada gerou entra em `audit_logs`, fora de transação.

    O ROBÔ DIZ QUEM É E A MANDO DE QUEM AGE (a regra de 26/10/2026): sem
    usuário, com `agente` e `a_mando_de` = o responsável pelas rotinas.
    """
    log = getattr(contexto.db, "log", None)
    if log is None:
        return
    import identidade_do_robo as IDR
    log(None, "automação", "PROTESTO_REPASSE_GUIA_GERADA", "pt_repasse_guias",
        int(g["guia_id"]),
        {"numero": g["numero"], "ano": g["ano"], "central": g["central"],
         "titulos": g["titulos"], "total_centavos": g["total_centavos"],
         "prazo": g["prazo"], "pela_rotina": CODIGO},
        agente=AGENTE, a_mando_de=IDR.PELO_RESPONSAVEL)


def _quadro(pendencias: list[dict]) -> dict[str, Any]:
    """O que espera, por etapa, só dos títulos da Central."""
    da_central = [p for p in pendencias if p["canal"] == "IEPTB"]
    por_etapa = {e: [p for p in da_central if p["etapa"] == e]
                 for e in (REP.SEM_GUIA, REP.GUIA_GERADA, REP.GUIA_REGISTRADA)}
    guias: dict[str, dict] = {}
    for p in da_central:
        if not p.get("guia"):
            continue
        g = guias.setdefault(p["guia"], {
            "tipo": p["etapa"], "guia": p["guia"], "central": p["central"],
            "titulos": 0, "total": 0, "prazo": p["prazo"], "vencida": False,
            "desfeito": False})
        g["titulos"] += 1
        g["total"] += int(p["valor_centavos"] or 0)
        g["prazo"] = min(str(g["prazo"]), str(p["prazo"]))
        g["vencida"] = g["vencida"] or bool(p["vencido"])
        g["desfeito"] = g["desfeito"] or bool(p.get("desfeito"))
    achados = [{**g, "total": reais(g["total"])} for g in guias.values()]
    sem_guia = por_etapa[REP.SEM_GUIA]
    if sem_guia:
        achados.insert(0, {"tipo": REP.SEM_GUIA, "titulos": len(sem_guia),
                           "total": reais(sum(int(p["valor_centavos"] or 0)
                                              for p in sem_guia)),
                           "vencidos": sum(1 for p in sem_guia if p["vencido"])})
    return {"por_etapa": {e: len(v) for e, v in por_etapa.items()},
            "vencidos": sum(1 for p in da_central if p["vencido"]),
            "desfeitos": sum(1 for p in da_central if p.get("desfeito")),
            "do_balcao": sum(1 for p in pendencias if p["canal"] != "IEPTB"),
            # O BOLETO DA CRA NASCE DO RETORNO: sem ele aceito, não há relação.
            "cra_sem_retorno": sum(1 for p in sem_guia if p.get("central") == "CRA"
                                   and not p.get("retorno_aceito")),
            "achados": achados}


def _relato(q: dict, geradas: list[dict], *, pode_agir: bool) -> str:
    n = q["por_etapa"]
    partes = []
    if geradas:
        partes.append("Relação gerada agora: " + "; ".join(
            f"guia {g['numero']}/{g['ano']} ({g['central']}), {g['titulos']} "
            f"título(s), R$ {reais(g['total_centavos'])}, repasse até "
            f"{_br(g['prazo'])}" for g in geradas) + ".")
    prontos = n[REP.SEM_GUIA] - q["cra_sem_retorno"]
    if prontos:
        partes.append(
            f"{prontos} pagamento(s) da Central ainda sem relação"
            + ("." if pode_agir else
               " — «pode agir» está desligado: a rotina só conta; ligue-o "
               "para ela gerar a relação."))
    if q["cra_sem_retorno"]:
        partes.append(f"{q['cra_sem_retorno']} pagamento(s) da CRA esperando o "
                      f"retorno com o «pago» aceito — o boleto de repasse nasce "
                      f"dele.")
    if n[REP.GUIA_GERADA]:
        partes.append(f"{n[REP.GUIA_GERADA]} pagamento(s) em relação que ainda "
                      f"não foi emitida no portal da Central nem registrada.")
    if n[REP.GUIA_REGISTRADA]:
        partes.append(f"{n[REP.GUIA_REGISTRADA]} pagamento(s) em guia "
                      f"registrada e ainda não paga.")
    if q["vencidos"]:
        partes.append(f"{q['vencidos']} com o prazo do repasse vencido.")
    if q["desfeitos"]:
        partes.append(f"{q['desfeitos']} pagamento(s) desfeito(s) dentro de "
                      f"guia não paga — cancele a guia antes de emiti-la.")
    if not partes:
        partes.append("Nenhum pagamento da Central esperando guia.")
    if q["do_balcao"]:
        partes.append(f"({q['do_balcao']} do balcão esperam o repasse direto.)")
    return " ".join(partes)


def gerar_a_relacao_do_dia(contexto) -> dict:
    """O processo PROTESTO_REPASSE_GUIA. Gera (com `pode_agir`) e conta."""
    agora: datetime = contexto.agora
    hoje = agora.date().isoformat()
    pode_agir = bool((getattr(contexto, "processo", None) or {}).get("pode_agir"))
    geradas: list[dict] = []
    if pode_agir:
        try:
            with contexto.db.transaction() as con:
                geradas = REP.gerar_guias_do_dia(
                    con, hoje=hoje, agora=agora.isoformat(timespec="seconds"),
                    usuario=QUEM_GERA, feriados=REP.feriados_da_casa(con))
        except Exception as erro:  # noqa: BLE001 — a falha vira ERRO com o motivo
            return {"situacao": "ERRO",
                    "relato": (f"A relação da guia de repasse NÃO foi gerada: "
                               f"{type(erro).__name__}: {erro}. Gere-a à mão em "
                               f"Protesto → Repasses ao apresentante.")[:600],
                    "erro": f"{type(erro).__name__}: {erro}"[:500],
                    "achados": [], "acoes": []}
        for g in geradas:
            _auditar(contexto, g)
    try:
        with contexto.db.connect() as con:
            pend = REP.pendencias_do_repasse(con, hoje=hoje)
    except Exception as erro:  # noqa: BLE001 — «não mediu» não é «zero»
        return {"situacao": "ERRO",
                "relato": (f"Não deu para medir o que espera o repasse: "
                           f"{type(erro).__name__}: {erro}")[:600],
                "erro": f"{type(erro).__name__}: {erro}"[:500],
                "achados": [], "acoes": [
                    {"acao": "gerou a relação da guia",
                     "guia": f"{g['numero']}/{g['ano']}", "central": g["central"]}
                    for g in geradas]}
    q = _quadro(pend)
    acoes = [{"acao": "gerou a relação da guia", "guia": f"{g['numero']}/{g['ano']}",
              "central": g["central"], "titulos": g["titulos"],
              "total": reais(g["total_centavos"]), "prazo": g["prazo"]}
             for g in geradas]
    esperando = sum(q["por_etapa"].values())
    return {"situacao": "AVISO" if esperando else "OK",
            "relato": _relato(q, geradas, pode_agir=pode_agir),
            "achados": q["achados"], "acoes": acoes}


def situacao_da_rotina(con, codigo: str = CODIGO) -> dict:
    """A rotina na central de automação: ligada? pode agir? e a última rodada.
    Só LÊ. É o que a tela de repasses mostra — a falha da rotina aparece onde
    o escrevente trabalha, e não só na central. `codigo` serve também ao robô
    do boleto da CRA (`protesto_repasse_portal`)."""
    bd = banco(con)
    if not bd.tem_tabela("au_processos"):
        return {"existe": False,
                "motivo": "a central de automação não está instalada nesta casa"}
    import automacao as AU
    p = AU.por_codigo(con, codigo)
    if not p:
        return {"existe": False,
                "motivo": ("a rotina ainda não aparece na central de automação — "
                           "abra Automação para ela ser cadastrada (desligada)")}
    ultimas = AU.execucoes(con, p["id"], limite=1)
    return {"existe": True, "processo_id": p["id"], "ativo": p["ativo"],
            "pode_agir": p["pode_agir"], "agenda": AU.descrever_agenda(p["agenda"]),
            "ultima": ultimas[0] if ultimas else None}

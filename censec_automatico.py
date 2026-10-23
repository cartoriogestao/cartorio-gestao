"""O envio automático à CENSEC e o que a conferência do gestor diz dele.

    «o sistema esta para enviar automaticamente com que frequencia? a api pode
     fechar carga?» — e, à proposta de enviar todo dia de madrugada: «quero».
     O oficial, 09/10/2026.

O QUE FAZ
    `enviar` roda de madrugada (tarefa «CartorioGestao-CENSEC-Envio», 02:00) e
    manda à CENSEC de PRODUÇÃO os atos aptos das quinzenas ainda abertas: a
    quinzena em curso, parcial, e a anterior enquanto o prazo dela (dia 20 ou
    dia 5) não venceu. É o mesmo caminho do botão de Notas → Remessas
    (`censec_api.enviar_quinzena`): o ato enviado fica registrado e não sai de
    novo; o impedido fica de fora até ser corrigido; o recusado volta.

    `regra` é a regra da conferência diária (07:30) e diz o que o envio não
    resolve sozinho: o ato impedido, o apto que perdeu o prazo, o lembrete de
    fechar a quinzena no portal e a falha do próprio envio.

O QUE NÃO FAZ, E POR QUÊ
    - NÃO FECHA A QUINZENA. O contrato da CENSEC (2.71.0 RTM, lido em
      09/10/2026) tem sete operações e nenhuma fecha lote; o fechamento só
      aparece como situação («AguardandoFechamento», «FechamentoSolicitado»,
      «Fechado»). Fecha-se no portal — e a regra lembra.
    - NÃO MANDA QUINZENA DE PRAZO VENCIDO. Medido em 09/10/2026: a 2ª de
      setembro voltou «LoteFechado: Essa quinzena não está aberta para
      cargas». Tentar toda noite só encheria a fila de recusas; a regra avisa
      que o caminho passou a ser o portal.
    - NÃO MANDA EM HOMOLOGAÇÃO. O envio automático é a comunicação de verdade;
      teste se faz pelo botão, escolhendo o ambiente.
    - NÃO CORRIGE ATO. O impedido vira achado, com o motivo, para quem lavrou.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from bd_nativo import banco

#: A conferência só olha da implantação para cá — o acervo o E-Ofício já mandou.
DESDE = "2026-09-10"
#: Quantos dias antes do prazo o lembrete de fechar no portal aparece.
AVISAR_FECHAMENTO_DIAS = 3
#: Por quantos dias depois do envio a conferência pede para olhar a validação.
DIAS_PARA_CONFERIR_A_VALIDACAO = 3
POR = "ENVIO AUTOMÁTICO (madrugada)"
ACAO_ENVIOU = "NT_REMESSA_API_AUTOMATICA"
ACAO_FALHOU = "NT_REMESSA_API_AUTOMATICA_FALHOU"
#: O interruptor das configurações (revisão de 22/10/2026, A13), na forma do
#: envio do ONR. LIGADO por padrão: a tarefa foi instalada «com envio».
CHAVE_DO_INTERRUPTOR = "censec_envio_automatico"
DESLIGADO = "DESLIGADO"


def envio_ligado(db) -> bool:
    """O oficial deixou o envio automático ligado? Só lê."""
    try:
        valor = db.get_setting(CHAVE_DO_INTERRUPTOR, "LIGADO")
    except Exception:                                   # noqa: BLE001
        valor = "LIGADO"
    return str(valor or "LIGADO").strip().upper() != DESLIGADO


def _quinzena_de(dia: date) -> tuple[int, int, int]:
    return dia.year, dia.month, 1 if dia.day <= 15 else 2


def _anterior(ano: int, mes: int, q: int) -> tuple[int, int, int]:
    if q == 2:
        return ano, mes, 1
    return (ano - 1, 12, 2) if mes == 1 else (ano, mes - 1, 2)


def _prazo(ano: int, mes: int, q: int) -> date:
    import notas_censec as NC
    return date.fromisoformat(NC.prazo_de_fechamento(ano, mes, q))


def quinzenas_abertas(hoje: date) -> list[tuple[int, int, int]]:
    """A em curso, e a anterior enquanto o prazo dela não venceu."""
    atual = _quinzena_de(hoje)
    anterior = _anterior(*atual)
    saida = [anterior] if _prazo(*anterior) >= hoje else []
    return saida + [atual]


def _quinzenas_desde(inicio: str, hoje: date) -> list[tuple[int, int, int]]:
    d = date.fromisoformat(inicio)
    vistas, saida = set(), []
    while d <= hoje:
        q = _quinzena_de(d)
        if q not in vistas:
            vistas.add(q)
            saida.append(q)
        d += timedelta(days=1)
    return saida


def _audit(db, acao: str, detalhes: dict) -> None:
    with db.transaction() as con:
        banco(con).escrever("""INSERT INTO audit_logs(ts, user_id, username_snapshot, action,
                                              entity_type, entity_id, details, ip_address)
                       VALUES (%s, NULL, 'envio-automatico', %s, 'NT_REMESSA', NULL, %s, NULL)""",
                    (datetime.now().isoformat(timespec="seconds"), acao,
                     json.dumps(detalhes, ensure_ascii=False, default=str)))


def enviar(db, hoje: date, *, cns: str) -> list[dict]:
    """Manda as quinzenas abertas que têm ato apto. Uma linha de resultado por quinzena."""
    import censec_api as CAPI
    import centrais_cred as CRED
    resultados = []
    if not envio_ligado(db):
        # Nada sobe; fica o registro do porquê, para o painel e o log.
        return [{"situacao": DESLIGADO,
                 "motivo": "envio automático desligado nas configurações"}]
    for ano, mes, q in quinzenas_abertas(hoje):
        quinzena = {"ano": ano, "mes": mes, "quinzena": q}
        with db.connect() as con:
            envio = CAPI.montar_envio(con, ano, mes, q, cns)
        aptos = {c: [a["id"] for a in v] for c, v in envio["atos"].items() if v}
        impedidos = {c: [x["ato"]["id"] for x in v]
                     for c, v in envio["impedidos"].items() if v}
        if not aptos:
            resultados.append({**quinzena, "situacao": "NADA_A_ENVIAR",
                               "impedidos": impedidos})
            continue
        try:
            r = CAPI.enviar_quinzena(db, ano, mes, q, cns=cns,
                                     ambiente=CRED.PRODUCAO, por=POR)
        except (CAPI.CensecError, CRED.CredencialError) as erro:
            linha = {**quinzena, "situacao": "FALHOU", "motivo": str(erro)[:500],
                     "aptos": aptos}
            _audit(db, ACAO_FALHOU, linha)
            resultados.append(linha)
            continue
        por_central = {c: {"sucesso": v.get("sucesso"), "situacao": v.get("situacao"),
                           "erro": v.get("erro"),
                           "recusas": len(v.get("recusas") or [])}
                       for c, v in (r.get("por_central") or {}).items() if c in aptos}
        recusou = [c for c, v in por_central.items() if not v["sucesso"]]
        linha = {**quinzena, "situacao": "RECUSADA" if recusou else "ENVIADA",
                 "aptos": aptos, "impedidos": impedidos, "por_central": por_central}
        _audit(db, ACAO_FALHOU if recusou else ACAO_ENVIOU, linha)
        resultados.append(linha)
    return resultados


# ------------------------------------------------------------ a conferência

def _achado(chave, gravidade, titulo, detalhe, prazo) -> dict:
    """Na forma de `gestor_conferencia._achado`, sem importá-lo."""
    return {"chave": chave, "regra": "CENSEC_AUTOMATICO", "gravidade": gravidade,
            "setor": "NOTAS", "titulo": titulo, "detalhe": detalhe,
            "prazo": prazo.isoformat() if isinstance(prazo, date) else prazo,
            "fundamento": "Provimento CNJ 18/2012; art. 785 do Código de Normas"}


def _gravidade(prazo: date, hoje: date) -> str:
    if hoje > prazo:
        return "VENCIDO"
    return "PRAZO" if (prazo - hoje).days <= 10 else "ATENCAO"


def _rotulo(ato: dict) -> str:
    return (f"{(ato.get('tipo') or 'ato').lower()} L{ato.get('livro') or '?'} "
            f"fl. {ato.get('folha') or '?'}")


def regra(con: Any, hoje: date) -> list[dict]:
    import notas_censec as NC
    bd = banco(con)
    saida: list[dict] = []
    for ano, mes, q in _quinzenas_desde(DESDE, hoje):
        prazo = _prazo(ano, mes, q)
        nome = f"{q}ª quinzena de {mes:02d}/{ano}"
        aptos_ficaram = []
        for central in ("CEP", "CESDI", "RCTO"):
            sep = NC.separar(con, central, ano, mes, q)
            for x in sep["impedidos"]:
                ato = x["ato"]
                motivos = "; ".join(p["motivo"] for p in x["problemas"][:6])
                saida.append(_achado(
                    f"CENSEC_IMPEDIDO:{central}:{ato['id']}", _gravidade(prazo, hoje),
                    f"CENSEC: {_rotulo(ato)} não pode ir à {central} ({nome})",
                    f"O envio automático deixa este ato de fora até ser corrigido: "
                    f"{motivos}. Corrija na ficha do ato ou em Notas → Escrituras "
                    f"pendentes; o envio da madrugada seguinte o leva.", prazo))
            if prazo < hoje:
                aptos_ficaram += [f"{central}: {_rotulo(a['ato'])}" for a in sep["aptos"]]
        # A CTP DAS ESCRITURAS (22/10/2026) vai na carga da 2ª quinzena, com o
        # prazo DELA: último dia útil do mês seguinte (Prov. CNJ 174/2024,
        # art. 184-A) — o mesmo cálculo da DOI. Sem isto, a escritura impedida
        # ficaria fora da CTP sem ninguém saber.
        if q == 2:
            import censec_ctp as CTP
            import notas_doi as NDOI
            prazo_ctp = date.fromisoformat(NDOI.prazo_de_entrega(f"{ano:04d}-{mes:02d}-01"))
            sep = CTP.declaracoes_do_mes(con, ano, mes, "")
            for x in sep["impedidos"]:
                ato = x["ato"]
                motivos = "; ".join(p["motivo"] for p in x["problemas"][:6])
                saida.append(_achado(
                    f"CENSEC_IMPEDIDO:CTP:{ato['id']}", _gravidade(prazo_ctp, hoje),
                    f"CENSEC: {_rotulo(ato)} não pode ir à CTP ({mes:02d}/{ano})",
                    f"O envio automático deixa esta escritura de fora da CTP até ser "
                    f"corrigida: {motivos}. Corrija no painel da DOI da escritura; o "
                    f"envio da madrugada seguinte a leva.", prazo_ctp))
            if prazo_ctp < hoje:
                aptos_ficaram += [f"CTP: {_rotulo(a['ato'])}" for a in sep["aptos"]]
        if aptos_ficaram:
            saida.append(_achado(
                f"CENSEC_APTO_FORA_DO_PRAZO:{ano:04d}-{mes:02d}-Q{q}", "VENCIDO",
                f"CENSEC: {nome} tem ato apto que não subiu, e o prazo venceu",
                "A CENSEC não aceita carga de quinzena fechada (medido em 09/10/2026: "
                "«LoteFechado»). Comunique pelo portal da CENSEC: "
                + ", ".join(aptos_ficaram[:8]), prazo))

    for ano, mes, q in quinzenas_abertas(hoje):
        _, fim = NC.periodo_da_quinzena(ano, mes, q)
        prazo = _prazo(ano, mes, q)
        if fim >= hoje.isoformat() or (prazo - hoje).days > AVISAR_FECHAMENTO_DIAS:
            continue
        enviou = bd.valor("""SELECT COUNT(*) FROM nt_remessas
                              WHERE ano_referencia = %s AND mes_referencia = %s AND quinzena = %s
                                AND enviada_em IS NOT NULL""", (ano, mes, q))
        if enviou:
            saida.append(_achado(
                f"CENSEC_FECHAR:{ano:04d}-{mes:02d}-Q{q}", "PRAZO",
                f"CENSEC: feche a {q}ª quinzena de {mes:02d}/{ano} no portal até "
                f"{prazo:%d/%m}",
                "A API da CENSEC não fecha lote — o fechamento se faz no portal "
                "(censec.org.br). O envio automático já mandou o que estava apto.",
                prazo))

    # A CARGA ACEITA AINDA PODE SER REPROVADA — medido em 13/10/2026: a API
    # respondeu «sucesso / AguardandoValidacao» em 11/10 para julho e agosto,
    # o sistema gravou ENVIADA, e a validação da CENSEC reprovou as duas depois
    # («o ato já existe nesse cartório»). A API não tem consulta da situação da
    # carga; então, por DIAS_PARA_CONFERIR_A_VALIDACAO dias depois de cada envio,
    # a conferência pede que alguém confira no portal (CEP → Cargas).
    limite = (hoje - timedelta(days=DIAS_PARA_CONFERIR_A_VALIDACAO)).isoformat()
    for r in bd.ler("""SELECT id, central, competencia, quinzena, protocolo_central,
                                   enviada_em FROM nt_remessas
                             WHERE situacao = 'ENVIADA' AND enviada_em >= %s
                             ORDER BY id""", (limite,)):
        saida.append(_achado(
            f"CENSEC_CONFERIR_VALIDACAO:{r['id']}", "ATENCAO",
            f"CENSEC: confira no portal se a carga da {r['quinzena']}ª quinzena de "
            f"{str(r['competencia'])[5:7]}/{str(r['competencia'])[:4]} ({r['central']}) "
            f"foi aprovada",
            f"Enviada em {str(r['enviada_em'])[:16].replace('T', ' ')}, carga "
            f"{r['protocolo_central'] or 'sem número'}. A CENSEC aceita a carga na hora "
            "e valida depois — e pode reprovar (ato que já existe, por exemplo). No "
            "portal, CEP → Cargas: se estiver «Reprovado», abra o motivo e avise; a "
            "remessa precisa ser marcada como recusada para o ato voltar à fila.",
            None))

    ultimo = bd.um("""SELECT ts, action, details FROM audit_logs
                       WHERE action IN (%s, %s) ORDER BY id DESC LIMIT 1""",
                   (ACAO_ENVIOU, ACAO_FALHOU))
    if ultimo and ultimo["action"] == ACAO_FALHOU:
        try:
            d = json.loads(ultimo["details"] or "{}")
        except ValueError:
            d = {}
        motivo = d.get("motivo") or "; ".join(
            f"{c}: {v.get('erro') or v.get('situacao')}"
            for c, v in (d.get("por_central") or {}).items() if not v.get("sucesso"))
        saida.append(_achado(
            "CENSEC_ENVIO_AUTOMATICO_FALHOU", "CRITICO",
            f"CENSEC: o envio automático de {str(ultimo['ts'])[:16].replace('T', ' ')} "
            f"não foi aceito",
            f"{motivo or 'motivo não informado'}. Se for a chave, cadastre-a de novo "
            "em Administrativo → Configurações; o envio da madrugada seguinte tenta "
            "outra vez.", None))
    return saida

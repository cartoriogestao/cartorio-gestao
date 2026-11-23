"""NFS-e — o aviso diário do que ficou sem nota. SÓ LÊ.

POR QUE EXISTE (F003, 23/11/2026)
    A emissão estava ligada em produção havia três meses, nenhuma nota saiu, e
    124 recibos esperavam dado do tomador — ninguém soube, porque a pendência
    só aparecia a quem abrisse `/caixa/nfse`, e a central de automação não
    tinha processo de NFS-e. Este é o processo.

O QUE FAZ: conta, na fila de `nfse.fila`, os recibos sem nota (e os de ontem
em separado), as notas ENVIANDO paradas há mais de `minutos_parada`
(parâmetro, 60 de fábrica), as REJEITADAS e o total de pendências; e devolve
AVISO se houver qualquer uma, OK se não houver.

O QUE NUNCA FAZ: emitir, reenviar, cancelar, consultar parâmetros ou falar com
o provedor. Nem com «pode agir» ligado — não há o que agir aqui; quem emite é
o balcão. Não importa `nfse_provedor` nem abre o certificado. O processo nasce
DESLIGADO (todo processo novo da central nasce), e o oficial o liga.

LGPD: o relato e os achados trazem número do recibo e a falta, nunca nome nem
CPF/CNPJ do tomador.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import automacao_schema as SCH
import nfse as NFSE
from automacao_processos import _nao_mediu, resultado
from bd_nativo import banco

CODIGO = "NFSE_PENDENCIAS"
MINUTOS_PARADA = 60
LIMITE_DA_FILA = 5000
LIMITE_DE_ACHADOS = 50

CATALOGO = ({
    "codigo": CODIGO,
    "nome": "NFS-e — recibos sem nota, notas paradas e recusadas",
    "descricao": "Todo dia útil de manhã: quantos recibos estão sem nota (e quantos são de ontem), "
                 "quantas notas ficaram ENVIANDO e quantas foram RECUSADAS. Só lê: não emite, "
                 "não reenvia, não cancela e não chama o emissor.",
    "setor": "GESTAO", "funcao": "nfse_aviso.verificar",
    "robo_oficial": "FINANCEIRO",
    "agenda": {"dias": [0, 1, 2, 3, 4], "horarios": ["08:30"]},
    "parametros": {"minutos_parada": MINUTOS_PARADA},
},)


def _minutos(ctx: Any) -> int:
    try:
        return max(1, int((ctx.parametros or {}).get("minutos_parada") or MINUTOS_PARADA))
    except (TypeError, ValueError):
        return MINUTOS_PARADA


def _parada(nota: dict, agora: datetime, minutos: int) -> bool:
    """A nota ENVIANDO sem resposta há mais de `minutos`. Sem data legível, parada."""
    try:
        desde = datetime.fromisoformat(str(nota.get("enviado_em") or nota["criado_em"])[:19])
    except (KeyError, ValueError):
        return True
    return agora - desde > timedelta(minutes=minutos)


def verificar(ctx) -> dict:
    """O contrato da central: `{situacao, relato, achados, acoes}`. `acoes` é sempre vazia."""
    try:
        with ctx.db.connect() as con:
            cfg = NFSE.configuracao(con)
            if not NFSE.ligada(cfg):
                return resultado(SCH.OK, "NFS-e: a emissão está desligada; nada a acompanhar.")
            grupos = NFSE.fila(con, cfg, limite=LIMITE_DA_FILA)
            enviando = [dict(n) for n in banco(con).ler(
                """SELECT id, recibo_id, criado_em, enviado_em, tentativas FROM nfse_notas
                    WHERE ambiente = %s AND situacao = 'ENVIANDO' ORDER BY id""",
                (cfg["nfse_ambiente"],))]
    except Exception as erro:  # noqa: BLE001 — «não mediu» não é «zero»
        return _nao_mediu("as pendências da NFS-e", erro)
    ontem = (ctx.agora.date() - timedelta(days=1)).isoformat()
    sem_nota = grupos["pendentes"] + grupos["prontos"]
    de_ontem = [i for i in sem_nota if str(i["recibo"]["data_emissao"])[:10] == ontem]
    paradas = [n for n in enviando if _parada(n, ctx.agora, _minutos(ctx))]
    recusadas = grupos["rejeitadas"]
    total = len(sem_nota) + len(paradas) + len(recusadas)
    achados = (
        [{"tipo": "RECIBO_SEM_NOTA", "recibo": f"{i['recibo']['numero']}/{i['recibo']['ano']}",
          "data": str(i["recibo"]["data_emissao"])[:10],
          "falta": " ".join(i["pendencias"]) or "pronto para emitir"} for i in sem_nota]
        + [{"tipo": "NOTA_ENVIANDO_PARADA", "nota": n["id"], "recibo_id": n["recibo_id"],
            "tentativas": n["tentativas"]} for n in paradas]
        + [{"tipo": "NOTA_REJEITADA", "recibo": f"{i['recibo']['numero']}/{i['recibo']['ano']}",
            "mensagem": str((i["nota"] or {}).get("mensagem") or "")[:200]} for i in recusadas])
    contagem = {"total": total, "recibos_sem_nota": len(sem_nota), "de_ontem": len(de_ontem),
                "enviando_paradas": len(paradas), "recusadas": len(recusadas)}
    if not total:
        return resultado(SCH.OK, "NFS-e em dia: nenhum recibo sem nota, nada parado e nada "
                         "recusado.", **contagem)
    relato = (f"NFS-e: {total} pendência(s) — {len(sem_nota)} recibo(s) sem nota "
              f"({len(de_ontem)} de ontem; {len(grupos['pendentes'])} sem os dados, "
              f"{len(grupos['prontos'])} prontos para emitir), {len(paradas)} nota(s) ENVIANDO "
              f"parada(s) há mais de {_minutos(ctx)} min, {len(recusadas)} recusada(s) pelo emissor. "
              f"O aviso só lê: a emissão é do balcão, em Caixa → NFS-e.")
    return resultado(SCH.AVISO, relato, achados[:LIMITE_DE_ACHADOS], **contagem)

"""AS DESPESAS NO HUB DA AUTOMAÇÃO — pagar as autorizadas e conferir o extrato.

O CONTRATO (o do `automacao_processos`, ramo `automacao-hub`)
    def verificar(contexto) -> {"situacao": "OK"|"AVISO"|"ERRO", "relato": str,
                                "achados": [...], "acoes": [...]}
    O contexto traz `db`, `agora`, `pasta_dados` e `processo` (com `pode_agir`).

OS DOIS PROCESSOS
    DESPESAS_PAGAR      — paga as despesas AUTORIZADAS e pergunta ao Inter
                          pelas ENVIADAS. Só PAGA com `pode_agir`: desligado,
                          lê e conta o que pagaria.
    DESPESAS_CONCILIAR  — lê o extrato do Inter, marca CONCILIADA a despesa
                          cujo débito apareceu, lança no Livro Diário (só a
                          despesa; o repasse de fundo fica fora) e lista os
                          débitos que o sistema não conhece. Lançar no livro é
                          gravar o que é da casa: também só com `pode_agir`.

    Cofre trancado é AVISO, e não erro: «não pagou, tenta no próximo tique».
    Credencial que falta é AVISO (regra 2 do catálogo). Rede fora é AVISO: a
    despesa fica onde estava e a rodada seguinte retoma.

    Nada aqui AUTORIZA. Autorizar é do oficial; a única exceção é a regra das
    guias, aplicada pelo `despesas.cadastrar` — e não por este arquivo.
"""
from __future__ import annotations

from typing import Any

import despesas as DP
import despesas_inter as INTER
from bd_nativo import banco
from caixa_schema import reais

CATALOGO = (
    {"codigo": "DESPESAS_PAGAR", "nome": "Despesas — pagar as autorizadas (Banco Inter)",
     "setor": "GESTAO", "funcao": "despesas_automacao.pagar"},
    {"codigo": "DESPESAS_CONCILIAR", "nome": "Despesas — conferir o extrato do Inter",
     "setor": "GESTAO", "funcao": "despesas_automacao.conciliar"},
)


def _cliente(contexto) -> Any:
    with contexto.db.connect() as con:
        cfg = DP.configuracao(con)
    return INTER.cliente_da_casa(cfg, pasta=getattr(contexto, "pasta_dados", None))


def _aviso_da_credencial(erro: Exception) -> dict:
    return {"situacao": "AVISO", "relato": str(erro), "achados": [], "acoes": []}


def pagar(contexto) -> dict:
    with contexto.db.connect() as con:
        n = DP.contagem(con)
        autorizadas = banco(con).ler(
            "SELECT id, valor FROM dp_despesas WHERE situacao = 'AUTORIZADA' ORDER BY id")
    pendentes = n.get(DP.AUTORIZADA, 0) + n.get(DP.ENVIADA, 0)
    if not pendentes:
        return {"situacao": "OK", "relato": "Nenhuma despesa autorizada esperando pagamento.",
                "achados": [], "acoes": []}
    if not contexto.processo.get("pode_agir"):
        total = sum(int(a["valor"]) for a in autorizadas)
        return {"situacao": "AVISO",
                "relato": f"{len(autorizadas)} despesa(s) autorizada(s), R$ {reais(total)}, "
                          f"esperando: o processo só lê (pode_agir desligado).",
                "achados": [{"despesa_id": int(a["id"])} for a in autorizadas], "acoes": []}
    try:
        cliente = _cliente(contexto)
    except (INTER.CredencialTrancada, INTER.CredencialAusente) as erro:
        return _aviso_da_credencial(erro)
    try:
        r = INTER.pagar_autorizadas(contexto.db, cliente=cliente, por="automação",
                                    agora=contexto.agora)
    except INTER.InterError as erro:
        return {"situacao": "AVISO", "relato": f"O Inter não respondeu: {erro}",
                "achados": [], "acoes": []}
    acoes = [f"despesa {i}: enviada ao banco" for i, _ in r["pagas"]]
    acoes += [f"despesa {i}: {s}" for i, s in r["atualizadas"]]
    situacao = "AVISO" if r["falharam"] or r["esperam"] else "OK"
    relato = (f"{len(r['pagas'])} enviada(s), {len(r['esperam'])} esperando, "
              f"{len(r['falharam'])} recusada(s) pelo banco.")
    achados = ([{"despesa_id": i, "motivo": m, "tipo": "FALHOU"} for i, m in r["falharam"]]
               + [{"despesa_id": i, "motivo": m, "tipo": "ESPERA"} for i, m in r["esperam"]])
    return {"situacao": situacao, "relato": relato, "achados": achados, "acoes": acoes}


def conciliar(contexto) -> dict:
    with contexto.db.connect() as con:
        n = DP.contagem(con)
    abertas = n.get(DP.ENVIADA, 0) + n.get(DP.PAGA, 0)
    if not contexto.processo.get("pode_agir"):
        return {"situacao": "AVISO" if abertas else "OK",
                "relato": f"{abertas} despesa(s) paga(s) esperando a conferência do extrato "
                          f"(pode_agir desligado: o processo só lê).",
                "achados": [], "acoes": []}
    try:
        cliente = _cliente(contexto)
    except (INTER.CredencialTrancada, INTER.CredencialAusente) as erro:
        return _aviso_da_credencial(erro)
    try:
        r = INTER.conciliar(contexto.db, cliente=cliente, por="automação",
                            agora=contexto.agora)
    except INTER.InterError as erro:
        return {"situacao": "AVISO", "relato": f"O extrato não veio: {erro}",
                "achados": [], "acoes": []}
    sem = r["sem_despesa"]
    relato = (f"{len(r['conciliadas'])} conferida(s) no extrato; {len(sem)} débito(s) sem "
              f"despesa cadastrada.")
    return {"situacao": "AVISO" if sem else "OK", "relato": relato,
            "achados": [{"tipo": "DEBITO_SEM_DESPESA", **s} for s in sem],
            "acoes": [f"despesa {i}: conferida no extrato" for i in r["conciliadas"]]}

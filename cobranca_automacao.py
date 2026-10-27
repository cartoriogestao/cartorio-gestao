"""A COBRANÇA NO HUB DA AUTOMAÇÃO — acompanhar os boletos no banco.

O CONTRATO (o do `automacao_processos`)
    def verificar(contexto) -> {"situacao": "OK"|"AVISO"|"ERRO", "relato": str,
                                "achados": [...], "acoes": [...]}

O PROCESSO
    COBRANCA_ACOMPANHAR — uma volta com o banco configurado
    (`cobranca_banco.rodada`): emite as cadastradas (só com a emissão ligada
    na configuração), faz os pedidos do balcão (cancelar, abatimento,
    protesto), pergunta pelas abertas e guarda o PDF de cada boleto
    registrado. Falar com o banco é só com `pode_agir`: desligado, ele lê e
    conta.

    É ELE QUEM FALA COM O BANCO QUANDO O COFRE ESTÁ INSTALADO: o cofre recusa
    entregar a credencial dentro de uma requisição web, e a tela então só
    grava o pedido e chama a rodada.

    **ELE NÃO LANÇA NO CAIXA.** O dinheiro pago no banco vira depósito prévio
    pelo clique de quem está com o caixa aberto (`cobranca.lancar_no_caixa`):
    o robô não tem gaveta, e depósito fora do caixa do dia não fecha a
    conferência. O que ele faz é LISTAR as pagas que esperam o balcão — é
    isso que vira AVISO.

    Cofre trancado, credencial que falta e banco fora do ar são AVISO: a
    cobrança fica onde estava, e a rodada seguinte retoma.
"""
from __future__ import annotations

from typing import Any

import cobranca as CB
import cobranca_banco as CBB
from caixa_schema import reais

CATALOGO = (
    {"codigo": "COBRANCA_ACOMPANHAR", "nome": "Cobrança — acompanhar os boletos no banco",
     "setor": "GESTAO", "funcao": "cobranca_automacao.acompanhar",
     "agenda": {"dias": [0, 1, 2, 3, 4], "intervalo_min": 30, "janela": ["08:00", "18:00"]}},
)


def _auditar(contexto, acao: str, cobranca_id: int, detalhes: dict) -> None:
    """A mudança feita pela rodada entra em `audit_logs`, fora de transação."""
    log = getattr(contexto.db, "log", None)
    if log is not None:
        log(None, "automação", acao, "cb_cobrancas", int(cobranca_id), detalhes)


def _esperando_o_balcao(contexto) -> list[dict]:
    with contexto.db.connect() as con:
        return CB.lista(con, situacao=CB.RECEBIDA, limite=100)


def _pasta(contexto):
    pasta = getattr(contexto, "pasta_dados", None)
    if pasta:
        return pasta
    import centrais_cred
    return centrais_cred.pasta_de_dados()


def _achados(contexto, falharam=()) -> list[dict[str, Any]]:
    pagas = _esperando_o_balcao(contexto)
    achados: list[dict[str, Any]] = [
        {"tipo": "PAGA_FALTA_LANCAR", "cobranca_id": int(c["id"]),
         "protocolo": c.get("protocolo_numero") or "",
         "valor": reais(int(c["valor_recebido"] or 0))} for c in pagas]
    achados += [{"tipo": "FALHOU", "cobranca_id": i, "motivo": m} for i, m in falharam]
    return achados


def acompanhar(contexto) -> dict:
    with contexto.db.connect() as con:
        cfg = CB.configuracao(con)
        n = CB.contagem(con)
        pedidos = len(CB.com_pedido(con, banco_codigo=cfg["cobranca_banco"],
                                    ambiente=cfg["cobranca_ambiente"]))
    ligada = cfg.get("cobranca_ligada") == "1"
    pendentes = (sum(n.get(s, 0) for s in CB.EM_ABERTO) + pedidos
                 + (n.get(CB.A_EMITIR, 0) if ligada else 0))
    achados = _achados(contexto)
    pagas = sum(1 for a in achados if a["tipo"] == "PAGA_FALTA_LANCAR")
    if not pendentes:
        return {"situacao": "AVISO" if pagas else "OK",
                "relato": (f"Nada esperando o banco; {pagas} cobrança(s) paga(s) esperando o "
                           f"lançamento no caixa." if pagas else "Nada esperando o banco."),
                "achados": achados, "acoes": []}
    if not contexto.processo.get("pode_agir"):
        return {"situacao": "AVISO",
                "relato": f"{pendentes} cobrança(s) ou pedido(s) esperando o banco "
                          f"(pode_agir desligado: o processo só lê).",
                "achados": achados, "acoes": []}
    try:
        cliente = CBB.cliente_da_casa(cfg, pasta=getattr(contexto, "pasta_dados", None))
    except CBB.BancoError as erro:
        return {"situacao": "AVISO", "relato": str(erro), "achados": achados, "acoes": []}
    try:
        r = CBB.rodada(contexto.db, cliente=cliente, por="automação", agora=contexto.agora,
                       pasta=_pasta(contexto), emitir_ligado=ligada)
    except CBB.Indisponivel as erro:
        return {"situacao": "AVISO", "relato": f"O banco não respondeu: {erro}",
                "achados": achados, "acoes": []}
    for i, s in r["emitidas"] + r["mudaram"]:
        _auditar(contexto, "COBRANCA_ATUALIZADA_PELO_BANCO", i, {"situacao": s})
    for i, frase in r["pedidos"]:
        _auditar(contexto, "COBRANCA_PEDIDO_AO_BANCO", i, {"resposta": frase})
    achados = _achados(contexto, r["falharam"])
    pagas = sum(1 for a in achados if a["tipo"] == "PAGA_FALTA_LANCAR")
    relato = (f"{CB.BANCOS[cliente.banco]}: {len(r['emitidas'])} emitida(s), "
              f"{len(r['pedidos'])} pedido(s), {r['consultadas']} consultada(s), "
              f"{len(r['mudaram'])} mudaram, {len(r['pdfs'])} PDF(s) guardado(s); "
              f"{pagas} paga(s) esperando o lançamento no caixa.")
    acoes = [f"cobrança {i}: {CB.SITUACOES.get(s, s)}" for i, s in r["emitidas"] + r["mudaram"]]
    acoes += [f"cobrança {i}: {frase}" for i, frase in r["pedidos"]]
    return {"situacao": "AVISO" if pagas or r["falharam"] else "OK", "relato": relato,
            "achados": achados, "acoes": acoes}

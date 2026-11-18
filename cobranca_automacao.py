"""A COBRANÇA NO HUB DA AUTOMAÇÃO — acompanhar os boletos no banco.

A MAQUININHA TEM OUTRA RODADA (`COBRANCA_MAQUINA`). O cliente paga na frente
do balcão, e esperar a rodada de meia hora deixa o pagamento no ar. Essa
rodada pergunta a Parcela a cada poucos segundos enquanto a cobrança é
recente, e uma vez por minuto no resto do dia. Boleto, pedido e PDF
continuam na rodada de meia hora.

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

    Pagamentos confirmados entram no caixa bancário automaticamente, sem
    usar a gaveta de atendentes. Retoma também os já recebidos sem lançamento.

    Cofre trancado, credencial que falta e banco fora do ar são AVISO: a
    cobrança fica onde estava, e a rodada seguinte retoma.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import cobranca as CB
import cobranca_banco as CBB
from bd_nativo import banco
from caixa_schema import reais

#: A vigília cabe num minuto do despachante: 45 s perguntando, e a rodada
#: seguinte começa sem encontrar esta ainda de pé. Quatro segundos é o
#: tempo de a Parcela publicar a venda e a tela do balcão mostrar.
VIGILIA_S = 45
VIGILIA_PASSO_S = 4
#: Neste prazo o cliente ainda está no balcão. A pergunta é a cada poucos
#: segundos. Depois disso, no mesmo dia, uma vez por minuto basta.
VIGILIA_RECENTE_MIN = 60

CATALOGO = (
    {"codigo": "COBRANCA_ACOMPANHAR", "nome": "Cobrança — acompanhar os boletos no banco",
     "setor": "GESTAO", "funcao": "cobranca_automacao.acompanhar", "robo_oficial": "FINANCEIRO",
     "agenda": {"dias": [0, 1, 2, 3, 4], "intervalo_min": 30, "janela": ["08:00", "18:00"]}},
    {"codigo": "COBRANCA_MAQUINA", "nome": "Cobrança — confirmar o pagamento na maquininha",
     "setor": "GESTAO", "funcao": "cobranca_automacao.vigiar_maquina", "robo_oficial": "FINANCEIRO",
     "timeout_s": 90,
     "descricao": "Enquanto há cobrança recente na maquininha, pergunta à Parcela "
                  "a cada poucos segundos e grava o pagamento. A rodada de meia hora "
                  "segue com boleto, pedido e PDF.",
     "agenda": {"dias": [0, 1, 2, 3, 4], "intervalo_min": 1, "janela": ["08:00", "18:00"]}},
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
    achados: list[dict[str, Any]] = []
    for c in pagas:
        # Parcela espera o caixa geral abrir. Inter e Unicred esperam o clique.
        tipo = ("PAGA_ESPERA_CAIXA_GERAL" if c.get("banco") == CB.PARCELA
                else "PAGA_FALTA_LANCAR")
        achados.append({"tipo": tipo, "cobranca_id": int(c["id"]),
                        "protocolo": c.get("protocolo_numero") or "",
                        "valor": reais(int(c["valor_recebido"] or 0))})
    achados += [{"tipo": "FALHOU", "cobranca_id": i, "motivo": m} for i, m in falharam]
    return achados


def _frase_das_pagas(achados: list[dict[str, Any]]) -> str:
    geral = sum(1 for a in achados if a["tipo"] == "PAGA_ESPERA_CAIXA_GERAL")
    clique = sum(1 for a in achados if a["tipo"] == "PAGA_FALTA_LANCAR")
    partes = []
    if geral:
        partes.append(f"{geral} pagamento(s) da Parcela com lançamento bancário pendente")
    if clique:
        partes.append(f"{clique} cobrança(s) com lançamento bancário pendente")
    return "; ".join(partes)


def acompanhar(contexto) -> dict:
    if contexto.processo.get("pode_agir"):
        with contexto.db.transaction() as con:
            CB.recolher_no_caixa_geral(con, por="automação", agora=contexto.agora)
    with contexto.db.connect() as con:
        cfg = CB.configuracao(con)
        n = CB.contagem(con)
        pedidos = len(CB.com_pedido(con, banco_codigo=cfg["cobranca_banco"],
                                    ambiente=cfg["cobranca_ambiente"]))
        # HOTFIX-2026-11-12-COBRANCA-BAIXADA: BAIXADA da Parcela ainda no prazo de pagamento
        # tambem espera o banco; sem isso a rodada nem sai quando so ha BAIXADA.
        reconsultar = sum(1 for c in CB.para_acompanhar(
            con, banco_codigo=cfg["cobranca_banco"], ambiente=cfg["cobranca_ambiente"],
            hoje=contexto.agora.date()) if c["situacao"] == CB.BAIXADA)
    ligada = cfg.get("cobranca_ligada") == "1"
    pendentes = (sum(n.get(s, 0) for s in CB.EM_ABERTO) + n.get(CB.RECEBIDA, 0) + pedidos
                 + (n.get(CB.A_EMITIR, 0) if ligada else 0) + reconsultar)
    achados = _achados(contexto)
    pagas = sum(1 for a in achados if a["tipo"] in ("PAGA_FALTA_LANCAR", "PAGA_ESPERA_CAIXA_GERAL"))
    if not pendentes:
        frase = _frase_das_pagas(achados)
        return {"situacao": "AVISO" if pagas else "OK",
                "relato": (f"Nada esperando o banco; {frase}." if frase else "Nada esperando o banco."),
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
    pagas = sum(1 for a in achados if a["tipo"] in ("PAGA_FALTA_LANCAR", "PAGA_ESPERA_CAIXA_GERAL"))
    espera = _frase_das_pagas(achados) or "nenhuma paga esperando o caixa"
    relato = (f"{CB.BANCOS[cliente.banco]}: {len(r['emitidas'])} emitida(s), "
              f"{len(r['pedidos'])} pedido(s), {r['consultadas']} consultada(s), "
              f"{len(r['mudaram'])} mudaram, {len(r['pdfs'])} PDF(s) guardado(s); "
              f"{espera}.")
    acoes = [f"cobrança {i}: {CB.SITUACOES.get(s, s)}" for i, s in r["emitidas"] + r["mudaram"]]
    acoes += [f"cobrança {i}: {frase}" for i, frase in r["pedidos"]]
    return {"situacao": "AVISO" if pagas or r["falharam"] else "OK", "relato": relato,
            "achados": achados, "acoes": acoes}


def _iso_local(quando: datetime) -> str:
    return quando.replace(tzinfo=None, microsecond=0).isoformat(timespec="seconds")


def _na_maquina(con, *, ambiente: str, desde: str) -> list[dict]:
    """As da maquininha ainda abertas, deste ambiente, mandadas desde `desde`."""
    return banco(con).ler(
        """SELECT * FROM cb_cobrancas
            WHERE banco = %s AND ambiente = %s
              AND situacao = ANY(%s)
              AND forma_pedida = ANY(%s)
              AND banco_id LIKE 'pos:%%'
              AND criada_em >= %s
            ORDER BY id""",
        (CB.PARCELA, ambiente, list(CB.EM_ABERTO), list(CB.FORMAS_NA_MAQUINA), desde))


def vigiar_maquina(contexto, *, pausa=time.sleep, limite_s: int = VIGILIA_S,
                   passo_s: int = VIGILIA_PASSO_S, recente_min: int = VIGILIA_RECENTE_MIN,
                   relogio=time.monotonic) -> dict:
    """Confirma na hora o que foi pago na maquininha. ESCREVE quando pode agir.

    Sem cobrança aberta no dia, termina na hora e não fala com a Parcela.
    Cobrança da última hora é perguntada de novo a cada poucos segundos,
    até o prazo desta rodada. Cobrança mais velha, do mesmo dia, é
    perguntada uma vez: o pago aparece no minuto seguinte, e uma cobrança
    antiga que ninguém pagou não fica chamando o banco a cada quatro segundos.
    """
    base = contexto.agora.replace(tzinfo=None, microsecond=0)
    inicio_do_dia = _iso_local(base.replace(hour=0, minute=0, second=0))
    corte = _iso_local(base - timedelta(minutes=int(recente_min)))
    with contexto.db.connect() as con:
        cfg = CB.configuracao(con)
    ambiente = cfg["cobranca_ambiente"]
    if not contexto.processo.get("pode_agir"):
        with contexto.db.connect() as con:
            n = len(_na_maquina(con, ambiente=ambiente, desde=inicio_do_dia))
        return {"situacao": "AVISO" if n else "OK",
                "relato": (f"{n} cobrança(s) na maquininha (pode_agir desligado: "
                           "o processo só lê)." if n else
                           "Nenhuma cobrança do dia na maquininha."),
                "achados": [], "acoes": []}
    fim = relogio() + limite_s
    mudaram: list[tuple[int, str]] = []
    falharam: list[tuple[int, str]] = []
    cliente = None
    primeira = True
    consultas = 0
    while True:
        with contexto.db.connect() as con:
            abertas = _na_maquina(con, ambiente=ambiente, desde=inicio_do_dia)
        recentes = [c for c in abertas if str(c.get("criada_em") or "") >= corte]
        alvo = abertas if primeira else recentes
        primeira = False
        if not alvo:
            break
        if cfg.get("cobranca_banco") != CB.PARCELA:
            return {"situacao": "AVISO",
                    "relato": "Há cobrança na maquininha, e o banco configurado não é a Parcela.",
                    "achados": [], "acoes": []}
        if cliente is None:
            try:
                cliente = CBB.cliente_da_casa(cfg, pasta=getattr(contexto, "pasta_dados", None))
            except CBB.BancoError as erro:
                return {"situacao": "AVISO", "relato": str(erro), "achados": [], "acoes": []}
        for c in alvo:
            consultas += 1
            try:
                nova = CBB.atualizar(contexto.db, int(c["id"]), cliente=cliente,
                                     por="automação", agora=contexto.agora)
            except CBB.Indisponivel as erro:
                return {"situacao": "AVISO",
                        "relato": f"A Parcela não respondeu: {erro}",
                        "achados": [{"tipo": "FALHOU", "cobranca_id": int(c["id"]),
                                     "motivo": str(erro)}],
                        "acoes": []}
            except (CBB.BancoError, CB.CobrancaError) as erro:
                falharam.append((int(c["id"]), str(erro)))
                continue
            if nova != c["situacao"]:
                mudaram.append((int(c["id"]), nova))
                _auditar(contexto, "COBRANCA_ATUALIZADA_PELO_BANCO", int(c["id"]),
                         {"situacao": nova})
        if not recentes or relogio() >= fim:
            break
        pausa(passo_s)
    if not consultas and not mudaram:
        relato = "Nenhuma cobrança do dia na maquininha."
    else:
        relato = (f"Maquininha: {consultas} consulta(s), {len(mudaram)} confirmada(s), "
                  f"{len(falharam)} falha(s).")
    return {"situacao": "AVISO" if falharam else "OK", "relato": relato,
            "achados": [{"tipo": "FALHOU", "cobranca_id": i, "motivo": m} for i, m in falharam],
            "acoes": [f"cobrança {i}: {CB.SITUACOES.get(s, s)}" for i, s in mudaram]}

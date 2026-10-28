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
    # 28/10/2026: as recorrentes. Carrega as do Pix e AVISA as outras; o aviso
    # vai no resumo do dia, e não num e-mail por despesa.
    {"codigo": "DESPESAS_RECORRENTES", "nome": "Despesas — carregar e avisar as recorrentes do mês",
     "setor": "GESTAO", "funcao": "despesas_automacao.recorrentes",
     "agenda": {"dias": [0, 1, 2, 3, 4], "horarios": ["07:30"]}},
)


def _cliente(contexto) -> Any:
    with contexto.db.connect() as con:
        cfg = DP.configuracao(con)
    return INTER.cliente_da_casa(cfg, pasta=getattr(contexto, "pasta_dados", None))


def _auditar(contexto, acao: str, despesa_id: int, detalhes: dict) -> None:
    """A saída de dinheiro pela automação entra em `audit_logs` (26/10/2026).

    Revisão de segurança dos PRs abertos, MÉDIA: pela tela, a rota já chama
    `audit`; pela rodada do despachante — o caminho normal — a mudança ficava
    só em `dp_eventos`, fora da auditoria da casa. `db.log` abre conexão
    própria: chama-se FORA de transação, depois de a rodada terminar.
    """
    log = getattr(contexto.db, "log", None)
    if log is None:
        return
    # O ROBÔ DIZ QUEM É E A MANDO DE QUEM AGE (PR #36) — 27/10/2026. Sem os
    # dois campos, cada pagamento contava como «sem identificação», e na
    # etapa 2 a auditoria seria RECUSADA depois de o dinheiro já ter saído.
    import identidade_do_robo as IDR
    processo = getattr(contexto, "processo", None) or {}
    mandante = (str(processo.get("alterado_por") or processo.get("criado_por") or "").strip()
                or IDR.PELO_RESPONSAVEL)
    try:
        log(None, "automação", acao, "dp_despesas", int(despesa_id), detalhes,
            agente="automação — despesas (Banco Inter)", a_mando_de=mandante)
    except TypeError:
        # um `log` antigo, sem os dois campos (o dos testes de mesa)
        log(None, "automação", acao, "dp_despesas", int(despesa_id), detalhes)


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
    for i, m in r["pagas"]:
        _auditar(contexto, "DESPESA_ENVIADA_AO_BANCO", i, {"mensagem": m})
    for i, m in r["falharam"]:
        _auditar(contexto, "DESPESA_FALHOU_NO_PAGAMENTO", i, {"mensagem": m})
    # A consultada que continua ENVIADA não muda nada: auditá-la a cada tique
    # encheria a tabela sem dizer coisa nenhuma.
    for i, s in r["atualizadas"]:
        if s != DP.ENVIADA:
            _auditar(contexto, "DESPESA_ATUALIZADA_PELO_BANCO", i, {"situacao": s})
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
    for i in r["conciliadas"]:
        _auditar(contexto, "DESPESA_CONCILIADA", i, {})
    sem = r["sem_despesa"]
    relato = (f"{len(r['conciliadas'])} conferida(s) no extrato; {len(sem)} débito(s) sem "
              f"despesa cadastrada.")
    return {"situacao": "AVISO" if sem else "OK", "relato": relato,
            "achados": [{"tipo": "DEBITO_SEM_DESPESA", **s} for s in sem],
            "acoes": [f"despesa {i}: conferida no extrato" for i in r["conciliadas"]]}


def recorrentes(contexto) -> dict:
    """Carrega as despesas do mês das recorrentes por Pix e avisa as outras.

    Carregar é gravar despesa: só com `pode_agir`. Desligado, ele lê e conta.
    A despesa carregada nasce AGUARDANDO a autorização do oficial; nada aqui
    autoriza nem paga.
    """
    import despesas_recorrentes as RC
    hoje = contexto.agora.date()
    with contexto.db.connect() as con:
        abertas = RC.do_mes(con, hoje)
    a_carregar = [r for r in abertas if r["carrega_sozinho"]]
    a_avisar = [r for r in abertas if not r["carrega_sozinho"]]
    novas: list[int] = []
    if a_carregar and contexto.processo.get("pode_agir"):
        with contexto.db.transaction() as con:
            novas = RC.gerar(con, hoje=hoje, agora=contexto.agora, por="automação")
        for i in novas:
            _auditar(contexto, "DESPESA_RECORRENTE_CARREGADA", i, {})
    achados = [{"tipo": "RECORRENTE_A_CADASTRAR", "recorrente_id": int(r["id"]),
                "mes": r["competencia"], "vencimento": r["vencimento"],
                "descricao": r["descricao"], "atrasada": r["atrasada"]} for r in a_avisar]
    if a_carregar and not novas:
        achados += [{"tipo": "RECORRENTE_A_CARREGAR", "recorrente_id": int(r["id"]),
                     "mes": r["competencia"]} for r in a_carregar]
    partes = []
    if novas:
        partes.append(f"{len(novas)} despesa(s) por Pix carregada(s), esperando a autorização")
    elif a_carregar:
        partes.append(f"{len(a_carregar)} por Pix a carregar (pode_agir desligado: só conta)")
    if a_avisar:
        partes.append(f"{len(a_avisar)} recorrente(s) do mês esperando o boleto ou a guia")
    if not partes:
        return {"situacao": "OK", "relato": "Nenhuma recorrente aberta neste mês.",
                "achados": [], "acoes": []}
    return {"situacao": "AVISO", "relato": "; ".join(partes) + ".", "achados": achados,
            "acoes": [f"despesa {i}: carregada da recorrente" for i in novas]}

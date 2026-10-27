"""A COBRANÇA FALANDO COM O BANCO — uma ordem só para os dois bancos.

Os adaptadores (`cobranca_inter`, `cobranca_unicred`) só sabem falar com o
seu banco: montar o pedido e ler a resposta na forma comum. A ORDEM — prender
a linha, marcar antes da rede, falar com o banco fora da transação, gravar a
resposta depois, procurar antes de reenviar — mora aqui, uma vez. Escrita em
cada adaptador, ela seria duas versões da parte que decide se o cliente
recebe um boleto ou dois.

O CONTRATO DE UM ADAPTADOR
    banco, ambiente                    — atributos
    emitir(c) -> banco_id              — Recusa | Indisponivel
    consultar(c) -> dict | None        — a forma comum; None = ainda processando
    procurar(c, data_inicial, data_final) -> banco_id | None
                                       — None também quando o banco não sabe procurar
    pdf(c) -> bytes
    cancelar(c, motivo) -> codigo_instrucao | ""
    e, só onde `cobranca.RECURSOS` diz que o banco tem (a Unicred):
    abatimento(c, valor, justificativa), cancelar_abatimento(c, justificativa),
    protesto_automatico(c, ligado=, dias=, dias_uteis=) -> codigo_instrucao

NADA AQUI LANÇA NO CAIXA. Ver `cobranca.lancar_no_caixa`, que é do balcão.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import cobranca as CB


class BancoError(RuntimeError):
    """O banco não fez o que se pediu. A frase vai para a tela."""


class Recusa(BancoError):
    """O banco respondeu e disse não."""


class Indisponivel(BancoError):
    """O banco não respondeu (rede, 5xx, limite de chamadas): tenta-se depois."""


class CredencialAusente(BancoError):
    pass


class CredencialTrancada(BancoError):
    """O cofre está trancado: a cobrança espera, e nada muda."""
    cofre_trancado = True


def cliente_da_casa(cfg: dict, *, banco_codigo: str | None = None, pasta: Any = None,
                    transporte=None):
    """O adaptador do banco configurado (ou do pedido), com a credencial dele."""
    qual = banco_codigo or cfg.get("cobranca_banco") or CB.INTER
    if qual == CB.INTER:
        import cobranca_inter
        return cobranca_inter.cliente_da_casa(cfg, pasta=pasta, transporte=transporte)
    if qual == CB.UNICRED:
        import cobranca_unicred
        return cobranca_unicred.cliente_da_casa(cfg, pasta=pasta, transporte=transporte)
    raise BancoError(f"Banco desconhecido: «{qual}».")


def _confere(c: dict, cliente) -> None:
    if c["banco"] != cliente.banco:
        raise BancoError(f"Esta cobrança é do {CB.BANCOS[c['banco']]}.")
    if c["ambiente"] != cliente.ambiente:
        # COBRANÇA DE TESTE NUNCA VAI AO BANCO DE PRODUÇÃO, nem para consulta:
        # o número dela não existe lá, e a resposta «não encontrada» viraria,
        # pela regra do reenvio, um boleto de verdade.
        raise BancoError(f"Esta cobrança foi emitida no ambiente «{c['ambiente']}», e o "
                         f"sistema está em «{cliente.ambiente}». Ela não vai a outro ambiente.")


def emitir(db, cobranca_id: int, *, cliente, por: str, agora: datetime) -> str:
    """Manda a cobrança A_EMITIR ao banco. ESCREVE. Devolve a situação.

    Recusa vira FALHOU com a frase do banco. Banco que não responde deixa a
    cobrança EMITINDO sem número: a `atualizar` a procura depois, e só ela
    decide se o boleto existe.
    """
    with db.transaction() as con:
        c = CB.cobranca(con, cobranca_id)
        if not c:
            raise CB.CobrancaError("Cobrança não encontrada.")
        _confere(c, cliente)
        c = CB.marcar_emitindo(con, cobranca_id, por=por, agora=agora)
    try:
        banco_id = cliente.emitir(c)
    except Recusa as erro:
        with db.transaction() as con:
            return CB.gravar_resposta(con, cobranca_id, {"situacao": CB.FALHOU, "erro": str(erro)},
                                      por=por, agora=agora, operacao="EMITIR")
    except Indisponivel as erro:
        with db.transaction() as con:
            return CB.gravar_resposta(con, cobranca_id, {"erro": f"Sem resposta: {erro}"},
                                      por=por, agora=agora, operacao="EMITIR")
    with db.transaction() as con:
        CB.gravar_resposta(con, cobranca_id, {"banco_id": banco_id, "erro": ""},
                           por=por, agora=agora, operacao="EMITIR")
    return atualizar(db, cobranca_id, cliente=cliente, por=por, agora=agora)


def atualizar(db, cobranca_id: int, *, cliente, por: str, agora: datetime) -> str:
    """Pergunta ao banco como está a cobrança. ESCREVE. Devolve a situação."""
    with db.transaction() as con:
        c = CB.cobranca(con, cobranca_id)
    if not c:
        raise CB.CobrancaError("Cobrança não encontrada.")
    if c["situacao"] not in CB.EM_ABERTO:
        return c["situacao"]
    _confere(c, cliente)
    if not c["banco_id"]:
        return _procurar(db, c, cliente=cliente, por=por, agora=agora)
    r = cliente.consultar(c)
    if r is None:
        return c["situacao"]
    with db.transaction() as con:
        return CB.gravar_resposta(con, cobranca_id, r, por=por, agora=agora)


def _procurar(db, c: dict, *, cliente, por: str, agora: datetime) -> str:
    """A cobrança enviada que ficou sem resposta: o banco a tem?

    Achou → grava o número e segue. Não achou e ainda está no prazo de
    aparecer → espera. Não achou depois do prazo → FALHOU, com a frase que diz
    o que conferir: o balcão cadastra outra, e o seu número novo não colide.
    O banco que não sabe procurar (a Unicred não tem busca por seu número)
    devolve None, e a frase manda conferir no internet banking antes.
    """
    inicio = (date.fromisoformat(str(c["criada_em"])[:10]) - timedelta(days=1)).isoformat()
    achado = cliente.procurar(c, data_inicial=inicio, data_final=agora.date().isoformat())
    if achado:
        with db.transaction() as con:
            CB.gravar_resposta(con, c["id"], {"banco_id": achado, "erro": ""}, por=por,
                               agora=agora, operacao="ACHADA_NO_BANCO")
        return atualizar(db, c["id"], cliente=cliente, por=por, agora=agora)
    if CB.em_espera(c, agora):
        return c["situacao"]
    frase = ("O banco não confirmou a emissão e a cobrança não apareceu nele. Confira no "
             "internet banking pelo seu número " + str(c["seu_numero"]) + " antes de emitir outra.")
    with db.transaction() as con:
        return CB.gravar_resposta(con, c["id"], {"situacao": CB.FALHOU, "erro": frase},
                                  por=por, agora=agora, operacao="SEM_RESPOSTA")


def executar_pedido(db, cobranca_id: int, *, cliente, por: str, agora: datetime,
                    pasta: Any = None) -> str:
    """Faz no banco o que o balcão pediu (`cobranca.pedir`). ESCREVE. Devolve a frase.

    O pedido só sai da fila quando o banco responde — aceitando ou recusando.
    Banco fora do ar deixa o pedido onde está, e a rodada seguinte tenta.
    O cancelamento só marca CANCELADA aqui DEPOIS de o banco aceitar:
    cancelar só deste lado deixaria um boleto vivo, que o cliente pagaria.
    """
    with db.transaction() as con:
        c = CB.cobranca(con, cobranca_id)
    if not c:
        raise CB.CobrancaError("Cobrança não encontrada.")
    p = CB.pedido(c)
    if not p:
        return ""
    _confere(c, cliente)
    pedido_por = str(p.get("por") or por)
    acao = p["acao"]
    try:
        if acao == "CANCELAR":
            instrucao = cliente.cancelar(c, str(p.get("motivo") or ""))
        elif acao == "ABATIMENTO":
            instrucao = cliente.abatimento(c, int(p.get("valor") or 0),
                                           str(p.get("justificativa") or ""))
        elif acao == "CANCELAR_ABATIMENTO":
            instrucao = cliente.cancelar_abatimento(c, str(p.get("justificativa") or ""))
        else:
            instrucao = cliente.protesto_automatico(
                c, ligado=bool(p.get("ligado")), dias=int(p.get("dias") or 0),
                dias_uteis=bool(p.get("dias_uteis")))
    except (Recusa, CB.CobrancaError) as erro:
        with db.transaction() as con:
            CB.encerrar_pedido(con, cobranca_id, resultado="RECUSADO", mensagem=str(erro),
                               por=pedido_por, agora=agora)
        return f"O banco recusou: {erro}"
    rotulo = f" (instrução {instrucao})" if instrucao else ""
    with db.transaction() as con:
        CB.encerrar_pedido(con, cobranca_id, resultado="ACEITO",
                           mensagem=CB.PEDIDOS[acao] + rotulo, por=pedido_por, agora=agora)
        if acao == "CANCELAR":
            CB.marcar_cancelada(con, cobranca_id, por=pedido_por, agora=agora,
                                motivo=str(p.get("motivo") or "") + rotulo)
        elif acao in ("ABATIMENTO", "CANCELAR_ABATIMENTO"):
            valor = int(p.get("valor") or 0) if acao == "ABATIMENTO" else 0
            CB.registrar_abatimento(con, cobranca_id, valor_centavos=valor, por=pedido_por,
                                    agora=agora, codigo_instrucao=instrucao)
            if pasta is not None:
                CB.esquecer_pdf(con, cobranca_id, pasta=pasta)
    if cliente.banco == CB.UNICRED:
        return (f"A Unicred recebeu o pedido{rotulo}. A instrução é assíncrona: a consulta "
                f"seguinte confirma.")
    return "O banco aceitou."


def guardar_pdf(db, cobranca_id: int, *, cliente, pasta: Any) -> None:
    """Baixa o boleto em PDF do banco e o guarda na pasta de dados. ESCREVE."""
    with db.transaction() as con:
        c = CB.cobranca(con, cobranca_id)
    if not c or not c["banco_id"] or c["situacao"] != CB.ABERTA:
        raise CB.CobrancaError("O banco só entrega o PDF da cobrança aberta.")
    _confere(c, cliente)
    conteudo = cliente.pdf(c)
    with db.transaction() as con:
        CB.guardar_pdf(con, cobranca_id, conteudo, pasta=pasta)


def rodada(db, *, cliente, por: str, agora: datetime, pasta: Any, emitir_ligado: bool) -> dict:
    """Uma volta inteira com o banco: emite, executa os pedidos, consulta, guarda PDFs.

    ESCREVE. Uma cobrança que falha não para as outras; o banco fora do ar
    para a rodada inteira (as seguintes falhariam igual, e cada uma custaria
    uma chamada do limite por minuto).
    """
    feito: dict[str, list] = {"emitidas": [], "pedidos": [], "mudaram": [], "pdfs": [],
                              "falharam": []}
    with db.transaction() as con:
        novas = (CB.a_emitir(con, banco_codigo=cliente.banco, ambiente=cliente.ambiente)
                 if emitir_ligado else [])
        pedidas = CB.com_pedido(con, banco_codigo=cliente.banco, ambiente=cliente.ambiente)
    for c in novas:
        try:
            feito["emitidas"].append((int(c["id"]), emitir(db, c["id"], cliente=cliente,
                                                           por=por, agora=agora)))
        except Indisponivel:
            raise
        except (BancoError, CB.CobrancaError) as erro:
            feito["falharam"].append((int(c["id"]), str(erro)))
    for c in pedidas:
        try:
            feito["pedidos"].append((int(c["id"]), executar_pedido(
                db, c["id"], cliente=cliente, por=por, agora=agora, pasta=pasta)))
        except Indisponivel:
            raise
        except (BancoError, CB.CobrancaError) as erro:
            feito["falharam"].append((int(c["id"]), str(erro)))
    with db.transaction() as con:
        abertas = CB.para_acompanhar(con, banco_codigo=cliente.banco, ambiente=cliente.ambiente)
    for c in abertas:
        try:
            nova = atualizar(db, c["id"], cliente=cliente, por=por, agora=agora)
        except Indisponivel:
            raise
        except (BancoError, CB.CobrancaError) as erro:
            feito["falharam"].append((int(c["id"]), str(erro)))
            continue
        if nova != c["situacao"]:
            feito["mudaram"].append((int(c["id"]), nova))
    with db.transaction() as con:
        faltam = CB.sem_pdf(con, banco_codigo=cliente.banco, ambiente=cliente.ambiente)
    for c in faltam:
        try:
            guardar_pdf(db, c["id"], cliente=cliente, pasta=pasta)
            feito["pdfs"].append(int(c["id"]))
        except Indisponivel:
            raise
        except (BancoError, CB.CobrancaError, OSError) as erro:
            feito["falharam"].append((int(c["id"]), f"PDF: {erro}"))
    feito["consultadas"] = len(abertas)
    return feito

"""Encerra os caixas compartilhados de datas encerradas, sem contar a gaveta."""
from __future__ import annotations

from bd_nativo import banco
from caixa_aviso import INICIO_DO_SISTEMA
from caixa_schema import centavos, reais, resumo_caixa
from cobranca import OPERADOR_DO_CAIXA_BANCARIO, OPERADOR_DO_CAIXA_GERAL

CODIGO = "CAIXA_FECHAR_COMPARTILHADOS"
CATALOGO = ({
    "codigo": CODIGO,
    "nome": "Caixa — encerrar os caixas compartilhados do dia anterior",
    "descricao": "Fecha o caixa geral e o bancário após a virada do dia. "
                 "Movimento em dinheiro exige contagem; a conferência continua humana.",
    "setor": "GESTAO", "funcao": "caixa_automacao.fechar_compartilhados",
    "robo_oficial": "FINANCEIRO",
    # Repete para retomar também quando o servidor ficou desligado à meia-noite.
    "agenda": {"dias": list(range(7)), "intervalo_min": 60,
               "janela": ["00:05", "23:05"]},
},)

FORMAS_ELETRONICAS = frozenset({"PIX", "BOLETO", "CARTAO", "DEBITO", "CREDITO",
                              "TRANSFERENCIA", "DEPOSITO", "GRATUITO", "DEPOSITO_PREVIO",
                              "PG_ONR"})


def _candidatos(con, hoje: str, *, travar=False):
    return banco(con).ler(
        """SELECT * FROM cx_caixas WHERE situacao='ABERTO'
             AND operador_id IS NULL AND operador_nome IN (%s,%s)
             AND data >= %s AND data < %s ORDER BY data,id"""
        + (" FOR UPDATE" if travar else ""),
        (OPERADOR_DO_CAIXA_GERAL, OPERADOR_DO_CAIXA_BANCARIO,
         INICIO_DO_SISTEMA, hoje))


def _medir(con, caixa):
    linhas = banco(con).ler("SELECT * FROM cx_lancamentos WHERE caixa_id=%s ORDER BY id",
                            (caixa["id"],))
    ativas = [l for l in linhas if not l.get("excluido") and not l.get("estornado")
              and l.get("sentido") != "ESTORNO"]
    precisa_contar = (centavos(caixa["saldo_inicial"]) != 0
                     or any(l.get("sentido") != "ENTRADA"
                            or l.get("forma_pagamento") not in FORMAS_ELETRONICAS
                            for l in ativas))
    return resumo_caixa(linhas, caixa["saldo_inicial"]), precisa_contar


def fechar_compartilhados(contexto):
    """Só age com pode_agir. Não confere, reabre, transmite ou movimenta valores."""
    import identidade_do_robo as IDR

    hoje = contexto.agora.date().isoformat()
    processo = contexto.processo or {}
    agir = bool(processo.get("pode_agir"))
    mandante = (str(processo.get("alterado_por") or processo.get("criado_por") or "").strip()
                or IDR.PELO_RESPONSAVEL)
    fechados, achados = [], []
    if agir and not callable(getattr(contexto.db, "log", None)):
        raise ValueError("O fechamento automático precisa da auditoria do sistema.")
    abrir = contexto.db.transaction if agir else contexto.db.connect
    with abrir() as con:
        bd = banco(con)
        if agir:
            bd.travar("cobranca.caixa_bancario")
        for caixa in _candidatos(con, hoje, travar=agir):
            resumo, contar = _medir(con, caixa)
            item = {"caixa_id": int(caixa["id"]), "data": caixa["data"],
                    "operador": caixa["operador_nome"]}
            if contar:
                achados.append({**item, "tipo": "CONTAGEM_NECESSARIA"})
                continue
            if not agir:
                achados.append({**item, "tipo": "FECHAMENTO_PENDENTE"})
                continue
            motivo = ("Fechamento automático após a virada do dia, sem movimento "
                      "em dinheiro físico. Sem contagem declarada; conferência pendente. "
                      f"Agente: automação de caixa. A mando de: {mandante}.")
            alteradas = bd.escrever(
                """UPDATE cx_caixas SET situacao='FECHADO', valor_esperado=%s,
                       valor_contado=NULL, diferenca=NULL, justificativa=%s,
                       fechado_em=%s, fechado_por=NULL
                     WHERE id=%s AND situacao='ABERTO' RETURNING id""",
                (reais(resumo["em_especie"]), motivo,
                 contexto.agora.isoformat(timespec="seconds"), caixa["id"]))
            if alteradas:
                fechados.append({**item, "entradas": reais(resumo["entradas"]),
                                 "saldo": reais(resumo["saldo"])})
    for item in fechados:
        contexto.db.log(None, "automação", "CAIXA_FECHADO_AUTOMATICAMENTE", "CAIXA",
                        item["caixa_id"], item, agente="automação — fechamento de caixa",
                        a_mando_de=mandante)
    return {
        "situacao": "AVISO" if achados else "OK",
        "relato": f"{len(fechados)} caixa(s) compartilhado(s) encerrado(s); "
                  f"{len(achados)} aguardando ação. Só datas anteriores a {hoje}.",
        "achados": achados,
        "acoes": [f"caixa {f['caixa_id']}: fechado automaticamente" for f in fechados],
    }

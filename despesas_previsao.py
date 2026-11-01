"""O MÊS ATÉ AGORA E O QUE AINDA VAI SAIR — o quadro do oficial na tela das despesas.

Pedido do oficial (31/10/2026): «um contador em despesas para simular o livro caixa do mês
até aquele momento e dizer qual a previsão de gastos até o final do mês, considerando
carnê-leão, fundos e recorrentes».

É UMA SIMULAÇÃO, E NÃO GRAVA NADA. As contas são as dos módulos donos: `carne_leao` (o
livro-caixa no regime de caixa e o imposto), `livro_diario` (as despesas lançadas e os
fundos declarados nos selos) e `despesas_recorrentes` (o vencimento de cada mês).

DADO FISCAL PESSOAL — SÓ O ADMIN. A renda e o imposto do titular são a regra de `carne_leao`.

O QUE ENTRA NA PREVISÃO DO MÊS
    - As despesas já lançadas no Livro Diário e os repasses já pagos.
    - As despesas cadastradas e ainda não conciliadas que vencem até o fim do mês, com as
      vencidas que ficaram para trás.
    - As recorrentes do mês ainda sem despesa. A de valor variável entra pelo último valor
      pago dela; a que nunca foi paga só se conta.
    - Os fundos dos atos do mês, projetados pelo ritmo dos dias úteis, menos as guias já
      pagas ou cadastradas no mês. O prazo dos fundos não está medido nesta casa
      (`oficial_obrigacoes.A_CONFIRMAR`): a conta supõe que os do mês saem no mês, e os de
      meses anteriores não entram.
    - O carnê-leão do mês ANTERIOR, que é o que vence neste (decisão do oficial de
      26/10/2026), menos a despesa da categoria do DARF. O deste mês só se mostra, porque
      vence no mês seguinte. Sem tabela progressiva não há imposto, e a tela diz isso.
"""
from __future__ import annotations

from datetime import date, timedelta

import carne_leao as CL
import despesas as DP
import despesas_recorrentes as RC
import livro_diario as LD
from bd_nativo import banco

CATEGORIAS_DE_FUNDO = tuple(c for c in DP.CATEGORIAS if c.startswith("FUNDO_"))
_EM_ABERTO = (DP.AGUARDANDO, DP.AUTORIZADA, DP.ENVIADA, DP.PAGA, DP.FALHOU)


def _fim_do_mes(hoje: date) -> date:
    return (hoje.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _mes_anterior(hoje: date) -> str:
    return (hoje.replace(day=1) - timedelta(days=1)).isoformat()[:7]


def ritmo_dos_dias_uteis(hoje: date) -> tuple[int, int]:
    """(dias úteis passados, contando hoje; dias úteis do mês). Só calcula."""
    from ri_schema import eh_dia_util
    dias = [hoje.replace(day=n) for n in range(1, _fim_do_mes(hoje).day + 1)]
    uteis = [d for d in dias if eh_dia_util(d)]
    return max(1, sum(1 for d in uteis if d <= hoje)), max(1, len(uteis))


def projetar(valor: int, passados: int, total: int) -> int:
    return round(int(valor) * total / max(1, min(passados, total)))


def recorrentes_que_faltam(con, hoje: date) -> dict:
    """As recorrentes deste mês ainda sem despesa, mesmo antes de o aviso abrir. Só LÊ."""
    bd = banco(con)
    comp = hoje.isoformat()[:7]
    feitas = {r["chave_origem"] for r in bd.ler(
        "SELECT chave_origem FROM dp_despesas WHERE origem = %s", (RC.ORIGEM,))}
    feriados = RC.feriados_da_casa(bd)
    total, quantas, estimadas, sem_valor = 0, 0, 0, 0
    for r in bd.ler("SELECT * FROM dp_recorrentes WHERE ativa = 1 ORDER BY id"):
        if comp < r["primeiro_mes"] or (r["ultimo_mes"] and comp > r["ultimo_mes"]):
            continue
        if RC.chave_do_mes(r["id"], comp) in feitas:
            continue
        criada = str(r.get("criada_em") or "")[:10]
        if criada and RC.vencimento_do_mes(r, comp, feriados).isoformat() < criada:
            continue
        valor = int(r["valor"] or 0)
        if not valor:
            ultima = bd.um("SELECT valor FROM dp_despesas WHERE origem = %s AND chave_origem LIKE %s "
                           "AND situacao <> %s ORDER BY id DESC LIMIT 1",
                           (RC.ORIGEM, f"{int(r['id'])}:%", DP.CANCELADA))
            valor = int(ultima["valor"]) if ultima else 0
            if valor:
                estimadas += 1
            else:
                sem_valor += 1
                continue
        total += valor
        quantas += 1
    return {"total": total, "quantas": quantas, "estimadas": estimadas, "sem_valor": sem_valor}


def _somar(bd, sql: str, parametros: tuple) -> int:
    return int(bd.um(f"SELECT COALESCE(SUM(valor), 0) AS total FROM dp_despesas WHERE {sql}",
                     parametros)["total"])


def quadro_do_mes(con, hoje: date) -> dict:
    """O livro-caixa do mês até agora e a previsão de gastos até o fim dele. Só LÊ."""
    bd = banco(con)
    comp = hoje.isoformat()[:7]
    inicio, fim = hoje.replace(day=1).isoformat(), _fim_do_mes(hoje).isoformat()
    passados, uteis = ritmo_dos_dias_uteis(hoje)
    caixa = CL.apurar(bd, comp)
    anterior = CL.apurar(bd, _mes_anterior(hoje))
    livro = LD.apurar(bd, comp)

    pago_no_livro = int(livro["despesas"])
    repasses_pagos = _somar(
        bd, "natureza = %s AND situacao IN (%s, %s) AND paga_em >= %s AND paga_em <= %s",
        (DP.REPASSE, DP.CONCILIADA, DP.PAGA_FORA, inicio, fim))
    a_pagar = _somar(bd, f"situacao IN ({', '.join(['%s'] * len(_EM_ABERTO))}) AND vencimento <= %s",
                     (*_EM_ABERTO, fim))
    recorrentes = recorrentes_que_faltam(bd, hoje)

    def _ja_previstas(categorias: tuple[str, ...]) -> int:
        """As guias da categoria pagas no mês, ou cadastradas e ainda em aberto."""
        lista = ", ".join(["%s"] * len(categorias))
        pagas = _somar(bd, f"categoria IN ({lista}) AND situacao IN (%s, %s) AND paga_em >= %s "
                           f"AND paga_em <= %s", (*categorias, DP.CONCILIADA, DP.PAGA_FORA, inicio, fim))
        abertas = _somar(bd, f"categoria IN ({lista}) AND situacao IN "
                             f"({', '.join(['%s'] * len(_EM_ABERTO))}) AND vencimento <= %s",
                         (*categorias, *_EM_ABERTO, fim))
        return pagas + abertas

    fundos_ate_agora = sum(int(v) for v in livro["fundos"].values())
    fundos_do_mes = projetar(fundos_ate_agora, passados, uteis)
    fundos_a_sair = max(0, fundos_do_mes - _ja_previstas(CATEGORIAS_DE_FUNDO))
    imposto = anterior["imposto"]
    imposto_a_sair = (None if imposto is None
                      else max(0, int(imposto) - _ja_previstas(("CARNE_LEAO",))))

    linhas = [
        {"rotulo": "Já pago: despesas no Livro Diário e repasses", "valor": pago_no_livro + repasses_pagos,
         "ja_saiu": True, "nota": ""},
        {"rotulo": "Despesas cadastradas a pagar até o fim do mês", "valor": a_pagar, "ja_saiu": False,
         "nota": ""},
        {"rotulo": "Recorrentes do mês ainda não carregadas", "valor": recorrentes["total"], "ja_saiu": False,
         "nota": (f"{recorrentes['estimadas']} pelo último valor pago. " if recorrentes["estimadas"] else "")
                 + (f"{recorrentes['sem_valor']} sem valor conhecido, fora da conta."
                    if recorrentes["sem_valor"] else "")},
        {"rotulo": "Fundos dos atos do mês, projetados", "valor": fundos_a_sair, "ja_saiu": False,
         "nota": f"R$ {DP.reais(fundos_ate_agora)} até agora, em {passados} de {uteis} dias úteis."},
        {"rotulo": f"Carnê-leão de {_mes_anterior(hoje)[5:]}/{_mes_anterior(hoje)[:4]}, que vence neste mês",
         "valor": imposto_a_sair or 0, "ja_saiu": False,
         "nota": "Sem tabela progressiva cadastrada: o imposto não foi calculado." if imposto is None
                 else "Sai da conta quando o DARF é cadastrado na categoria do carnê-leão."},
    ]
    falta_sair = sum(x["valor"] for x in linhas if not x["ja_saiu"])
    ja_saiu = sum(x["valor"] for x in linhas if x["ja_saiu"])
    receita = int(caixa["receita"])
    return {"competencia": comp, "linhas": linhas, "falta_sair": falta_sair,
            "previsao": ja_saiu + falta_sair,
            "receita": receita, "receita_pelo_selo": int(livro["receita_bruta"]),
            "despesas": pago_no_livro, "saldo": receita - pago_no_livro,
            "sobra": receita - pago_no_livro - falta_sair,
            "imposto_do_mes": caixa["imposto"], "dias_passados": passados, "dias_uteis": uteis}

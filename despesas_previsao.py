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
    - O ISS do mês anterior, PRELIMINAR (pedido do oficial, 01/11/2026), menos as guias da
      categoria ISS pagas ou cadastradas no mês. O deste mês só se mostra.

POR QUE O ISS É PRELIMINAR
    O selo não declara o ISS, e o caixa não o guarda: a conta é a alíquota do município, na
    configuração, sobre o emolumento dos atos pelo selo. O ISS é da serventia e não vai ao
    cliente. Contra as guias pagas em outubro/2026 ela ficou 2,7% abaixo em setembro, 30% em
    julho e 72% em agosto, e nenhuma outra base medida explicou os três. O valor que vale é o
    da guia.

    A transição do ISS para IBS e CBS não tem estrutura definida (oficial, 01/11/2026): nada
    aqui a antecipa.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import carne_leao as CL
import despesas as DP
import despesas_recorrentes as RC
import livro_diario as LD
import oficial_obrigacoes as OO
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


def aliquota_do_iss(con) -> int:
    """A alíquota da configuração, em centésimos de ponto: «5,00» é 500. Só LÊ."""
    return DP.centavos_da_tela(DP.configuracao(con)["despesas_aliquota_iss"])


def iss_preliminar(emolumentos: int, aliquota: int) -> int:
    """O ISS estimado sobre os emolumentos, em centavos. Só calcula. Ver o alto do módulo."""
    return (int(emolumentos) * int(aliquota) + 5000) // 10000


def formulario_do_iss(con, competencia: Any, *, municipio: str) -> dict:
    """A despesa da guia do ISS, com o valor estimado para conferir. Só LÊ.

    O vencimento fica em branco: a data da guia não está medida nesta casa.
    """
    try:
        comp = CL.competencia(competencia)
    except CL.CarneLeaoError as erro:
        raise DP.DespesaError(str(erro)) from erro
    valor = iss_preliminar(LD.apurar(con, comp)["receita_bruta"], aliquota_do_iss(con))
    if valor <= 0:
        raise DP.DespesaError(f"Os selos de {comp[5:]}/{comp[:4]} não dão ISS a estimar.")
    return {"iss_preliminar": comp, "categoria": "ISS",
            "descricao": f"ISS, referência {comp[5:]}/{comp[:4]}",
            "beneficiario_nome": f"Município de {municipio}" if municipio else "Município",
            "valor": DP.reais(valor), "forma": DP.PIX_COPIA_E_COLA, "documento_especie": "Guia"}


def vencimento_do_darf(con, competencia: str) -> date:
    """O vencimento do imposto da competência: no mês seguinte, pela regra da configuração."""
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    cfg = CL.configuracao(con)
    if cfg["carne_leao_prazo_regra"] == CL.DIA_DO_MES and str(cfg["carne_leao_prazo_dia"]).isdigit():
        ultimo = calendar.monthrange(ano, mes)[1]
        return date(ano, mes, min(int(cfg["carne_leao_prazo_dia"]), ultimo))
    return OO._ultimo_dia_util(ano, mes)


def formulario_do_darf(con, competencia: Any) -> dict:
    """A despesa do DARF, preenchida para colar o código. Só LÊ. Quem grava é o titular.

    O sistema não gera o DARF (`carne_leao`): o código sai do Carnê-Leão Web ou do Sicalc.
    Por isso a despesa não nasce sozinha: despesa sem código não se paga.
    """
    try:
        comp = CL.competencia(competencia)
    except CL.CarneLeaoError as erro:
        raise DP.DespesaError(str(erro)) from erro
    imposto = CL.apurar(con, comp)["imposto"]
    if imposto is None:
        raise DP.DespesaError("Sem tabela progressiva cadastrada, o imposto não foi calculado: "
                              "cadastre a tabela em Carnê-leão → Configuração.")
    if int(imposto) <= 0:
        raise DP.DespesaError(f"O livro-caixa de {comp[5:]}/{comp[:4]} não dá imposto a pagar.")
    return {"carne_leao": comp, "categoria": "CARNE_LEAO",
            "descricao": f"Carnê-leão do titular, competência {comp[5:]}/{comp[:4]}",
            "beneficiario_nome": "Receita Federal", "valor": DP.reais(int(imposto)),
            "vencimento": vencimento_do_darf(con, comp).isoformat(), "forma": DP.ARRECADACAO,
            "documento_especie": "DARF"}


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
    darf_cadastrado = _ja_previstas(("CARNE_LEAO",))
    imposto_a_sair = None if imposto is None else max(0, int(imposto) - darf_cadastrado)
    emolumentos_anteriores = int(LD.apurar(bd, _mes_anterior(hoje))["receita_bruta"])
    aliquota = aliquota_do_iss(bd)
    iss_anterior = iss_preliminar(emolumentos_anteriores, aliquota)
    iss_cadastrado = _ja_previstas(("ISS",))

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
        {"rotulo": f"ISS de {_mes_anterior(hoje)[5:]}/{_mes_anterior(hoje)[:4]}, preliminar",
         "valor": max(0, iss_anterior - iss_cadastrado), "ja_saiu": False,
         "nota": f"Estimativa: {DP.reais(aliquota)}% sobre R$ {DP.reais(emolumentos_anteriores)} de emolumentos "
                 "pelo selo. O valor que vale é o da guia; sai da conta quando ela é cadastrada na categoria ISS."},
    ]
    falta_sair = sum(x["valor"] for x in linhas if not x["ja_saiu"])
    ja_saiu = sum(x["valor"] for x in linhas if x["ja_saiu"])
    receita = int(caixa["receita"])
    return {"competencia": comp, "linhas": linhas, "falta_sair": falta_sair,
            "previsao": ja_saiu + falta_sair,
            "receita": receita, "receita_pelo_selo": int(livro["receita_bruta"]),
            "despesas": pago_no_livro, "saldo": receita - pago_no_livro,
            "sobra": receita - pago_no_livro - falta_sair,
            "imposto_do_mes": caixa["imposto"], "dias_passados": passados, "dias_uteis": uteis,
            "darf": {"competencia": _mes_anterior(hoje), "imposto": imposto,
                     "vencimento": vencimento_do_darf(bd, _mes_anterior(hoje)).isoformat(),
                     "falta_cadastrar": bool(imposto) and not darf_cadastrado},
            "iss": {"competencia": _mes_anterior(hoje), "valor": iss_anterior,
                    "falta_cadastrar": bool(iss_anterior) and not iss_cadastrado,
                    "do_mes": iss_preliminar(int(livro["receita_bruta"]), aliquota)}}

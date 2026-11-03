"""A CONFERÊNCIA «SISTEMA × SIAFERJ» DO MÊS — de onde vem a diferença entre as duas receitas.

POR QUE EXISTE (03/11/2026)
    O oficial comparou outubro de 2026: o sistema dizia cerca de R$ 51 mil de emolumentos, e o
    SIAFERJ-WEB do TJMA, cerca de R$ 49 mil, «já abatido o FERJ». O sistema tem DUAS receitas do mês,
    por critérios diferentes, e nenhuma delas é, sozinha, o número do SIAFERJ:

    - a do SELO (Livro Diário, `livro_diario.receitas_do_mes`): o emolumento de cada selo NORMAL usado
      no mês, CHEIO — o FERJ sai numa coluna à parte, e não é abatido;
    - a do CAIXA (carnê-leão, `carne_leao.apurar`): o que entrou no mês pelo dia do lançamento, com os
      fundos estimados pela configuração quando o lançamento não os discrimina, mais o depósito prévio
      convertido, as «outras entradas» marcadas como receita e os avulsos.

    O comparável do SIAFERJ, se ele traz o emolumento líquido do FERJ pelo dia do selo, é a do selo
    MENOS o FERJ. Esta conferência mostra os três números e QUEBRA a diferença entre o selo e o caixa
    em parcelas, ato por ato, para o oficial ver de onde vem cada real.

O QUE ELA NÃO FAZ
    Não grava nada, e não lê o SIAFERJ: o SIAFERJ-WEB não tem importação nem API (ver `despesas.py`).
    O número de lá o oficial põe ao lado.

COMO RODAR NO SERVIDOR (só lê):  python conferencia_siaferj.py 2026-10

Dinheiro em centavos (inteiro), como o resto da casa.
"""
from __future__ import annotations

import sys
from typing import Any

import carne_leao as CL
import livro_diario as LD
from bd_nativo import banco
from caixa_schema import reais


def _mes(dia: Any) -> str:
    return str(dia or "")[:7]


def _pagamentos_dos_atos(bd, atos: set) -> dict:
    """{(tabela, ato_id): [(mês do lançamento, emolumento)]} dos itens de protocolo pagos no caixa
    que esses atos usaram. Lançamento estornado ou excluído não conta."""
    saida: dict = {}
    for tabela, ato_id in atos:
        if not tabela or ato_id is None:
            continue
        for r in bd.ler(
                """SELECT l.data
                     FROM cx_protocolo_atos a
                     JOIN cx_lancamentos l ON l.id = a.lancamento_id
                    WHERE a.usado_por_tabela = %s AND a.usado_por_ato_id = %s
                      AND COALESCE(l.estornado, 0) = 0 AND COALESCE(l.excluido, 0) = 0""",
                (tabela, ato_id)):
            saida.setdefault((tabela, ato_id), []).append(_mes(r["data"]))
    return saida


def _selo_dos_lancamentos(bd, ids: list[int]) -> dict:
    """{id do lançamento: [mês de cada selo do ato que o item pagou]} — vazio, se o ato não foi
    selado (ou o item não foi usado por ato nenhum)."""
    saida: dict[int, list[str]] = {i: [] for i in ids}
    if not ids:
        return saida
    for r in bd.ler(
            """SELECT a.lancamento_id, s.usado_em
                 FROM cx_protocolo_atos a
                 JOIN sd_selos s ON s.tabela = a.usado_por_tabela AND s.ato_id = a.usado_por_ato_id
                WHERE a.lancamento_id = ANY(%s)
                  AND s.cancelado_em IS NULL AND s.ambiente = 'PRODUCAO'""", (ids,)):
        saida.setdefault(int(r["lancamento_id"]), []).append(_mes(r["usado_em"]))
    return saida


def conferir(con, comp: Any) -> dict:
    """A conferência do mês: as receitas e a ponte do selo para o caixa, em parcelas. Só LÊ."""
    comp = LD.competencia(comp)
    bd = banco(con)
    receitas = LD.receitas_do_mes(con, comp)
    inicio, fim = LD._limites(comp)
    ato_do_selo = {r["numero"]: (r["tabela"], r["ato_id"]) for r in bd.ler(
        """SELECT numero, tabela, ato_id FROM sd_selos
            WHERE usado_em >= %s AND usado_em < %s
              AND cancelado_em IS NULL AND ambiente = 'PRODUCAO'""", (inicio, fim))}
    normais = [r for r in receitas if r["tipo"] == LD.NORMAL]
    selo_bruto = sum(r["receita"] for r in normais)
    ferj = sum((r["fundos"].get(LD.FERJ) or 0) for r in normais)

    # ---- o selo do mês, ato por ato: pago no caixa no mesmo mês, noutro mês, ou sem caixa
    pagos = _pagamentos_dos_atos(bd, {ato_do_selo.get(r["selo"]) for r in normais} - {None})
    selado_pago_noutro_mes = selado_sem_caixa = 0
    for r in normais:
        meses = pagos.get(ato_do_selo.get(r["selo"]))
        if not meses:
            selado_sem_caixa += r["receita"]
        elif comp not in meses:
            selado_pago_noutro_mes += r["receita"]

    # ---- o caixa do mês, lançamento por lançamento: selado no mesmo mês, noutro, ou ainda não
    a = CL.apurar(con, comp)
    cfg = CL.configuracao(bd)
    forma, bp = CL._fundos_da_configuracao(cfg)
    recebidos, _, _ = CL._recebido_no_caixa(bd, comp, forma, bp)
    selos = _selo_dos_lancamentos(bd, [r["id"] for r in recebidos])
    pago_selado_noutro_mes = pago_sem_selo = pago_e_selado_no_mes = 0
    fundos_estimados = 0
    for r in recebidos:
        meses = selos.get(r["id"]) or []
        if not meses:
            pago_sem_selo += r["receita"]
        elif comp not in meses:
            pago_selado_noutro_mes += r["receita"]
        else:
            pago_e_selado_no_mes += r["receita"]
        if not r["discriminado"]:
            fundos_estimados += r["bruto"] - r["receita"]

    deposito = int(a.get("deposito_na_conta") or 0)
    avulsos = int(a.get("avulsas") or 0)
    outras = sum(x["valor"] for x in a["receitas"] if x["origem"] == "Outra entrada")
    caixa = int(a["receita"])
    # A parte do selo que o caixa também tem no mês: o selo do mês menos o que foi pago noutro mês e o
    # que não passou pelo caixa. A diferença entre ela e o que o caixa deu para os mesmos atos é a do
    # valor — os fundos estimados e o que se cobrou diferente do selo.
    selo_pago_no_mes = selo_bruto - selado_pago_noutro_mes - selado_sem_caixa
    valor_diferente = pago_e_selado_no_mes - selo_pago_no_mes
    parcelas = [
        ("Selado no mês e pago no caixa noutro mês", -selado_pago_noutro_mes),
        ("Selado no mês sem pagamento no caixa (depósito, gratuidade, acervo, ato sem protocolo)",
         -selado_sem_caixa),
        ("Pago no mês e selado noutro mês", pago_selado_noutro_mes),
        ("Pago no mês e ainda sem selo (ou item sem ato)", pago_sem_selo),
        ("Diferença de valor nos atos pagos e selados no mês (fundos estimados, cobrança diferente)",
         valor_diferente),
        ("Depósito prévio convertido", deposito),
        ("Outras entradas marcadas como receita", outras),
        ("Lançamentos avulsos do livro-caixa", avulsos),
    ]
    explicado = selo_bruto + sum(v for _, v in parcelas)
    diferidos = [r for r in receitas if r["tipo"] == LD.DIFERIDO]
    return {
        "competencia": comp,
        "selo": {"bruto": selo_bruto, "ferj": ferj, "liquido": selo_bruto - ferj,
                 "atos": len(normais),
                 "diferidos": {"n": len(diferidos), "emolumentos": sum(r["emolumentos"] or 0
                                                                      for r in diferidos)},
                 "isentos": sum(1 for r in receitas if r["tipo"] == LD.ISENTO),
                 "sem_valor": sum(1 for r in receitas if r["sem_valor"])},
        "caixa": {"receita": caixa, "fundos_estimados": fundos_estimados},
        "parcelas": [{"o_que": o, "valor": v} for o, v in parcelas],
        "residuo": caixa - explicado,
    }


def em_texto(c: dict) -> str:
    """A conferência para ler no terminal do servidor."""
    linhas = [f"Conferência Sistema × SIAFERJ — {c['competencia']}",
              "",
              f"  Receita pelo selo (Livro Diário, emolumento cheio, {c['selo']['atos']} selo(s)): "
              f"R$ {reais(c['selo']['bruto'])}",
              f"  FERJ dos mesmos selos:                                R$ {reais(c['selo']['ferj'])}",
              f"  Receita pelo selo menos o FERJ (o comparável do SIAFERJ): R$ {reais(c['selo']['liquido'])}",
              f"  Receita pelo caixa (carnê-leão):                       R$ {reais(c['caixa']['receita'])}",
              "",
              "  Do selo ao caixa:"]
    for p in c["parcelas"]:
        if p["valor"]:
            linhas.append(f"    {'+' if p['valor'] > 0 else '−'} R$ {reais(abs(p['valor'])):>12}  {p['o_que']}")
    linhas += [f"    = resíduo não explicado: R$ {reais(c['residuo'])}",
               "",
               f"  Fundos estimados pela configuração (já fora da receita do caixa): "
               f"R$ {reais(c['caixa']['fundos_estimados'])}",
               f"  Selos diferidos no mês: {c['selo']['diferidos']['n']} "
               f"(R$ {reais(c['selo']['diferidos']['emolumentos'])} de emolumento, fora da receita pelo selo)",
               f"  Selos isentos: {c['selo']['isentos']}; selos sem valor no texto: {c['selo']['sem_valor']}"]
    return "\n".join(linhas)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python conferencia_siaferj.py AAAA-MM")
        return 2
    from admin_cli import data_dir
    from database import Database
    db = Database(data_dir() / "cartorio_gestao.sqlite3")
    with db.connect() as con:
        print(em_texto(conferir(con, argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

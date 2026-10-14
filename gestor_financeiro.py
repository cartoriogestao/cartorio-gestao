"""O relatório financeiro do mês, e o resumo da semana para o oficial.

    «prepare o relatório financeiro» — o oficial, 06/10/2026, no pedido do gestor

SÓ LÊ. Escreve dois arquivos HTML e nada no banco.

O QUE A MEDIÇÃO DE 06/10/2026 OBRIGOU A SEPARAR
    O caixa desta casa mistura quatro coisas na mesma natureza «RECEBIMENTO»,
    e somá-las daria um número sem sentido:

    * **dinheiro que entrou** — dinheiro, PIX, depósito prévio recebido;
    * **receita reconhecida** — inclusive o «uso do depósito prévio», que é
      receita do mês em que o ato saiu, mas cujo dinheiro entrou antes
      (R$ 51,5 mil em setembro). Somar entrada e uso conta o mesmo dinheiro
      duas vezes;
    * **movimento de troco** — «SALDO INICIAL» e «COMPLEMENTO» (R$ 2.100 em
      setembro), que não são receita de nada;
    * **gratuidade** — lançamento de valor zero com os emolumentos que o ato
      teria (89 em setembro, R$ 3.446), que é a base da compensação.

    E os FUNDOS (FERC, FADEP, FEMP, FERRFIS) quase nunca estão separados no
    lançamento manual: o número confiável deles é o que o SELO declara.

O QUE ELE NÃO SABE, E DIZ QUE NÃO SABE
    Despesas da serventia (livro-caixa do delegatário), ISS e o que entrou
    fora do caixa do sistema. Não há tabela delas aqui.
"""
from __future__ import annotations

import html
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from gestor_conferencia import IMPLANTACAO, _brl, _dia, _reais

FUNDOS = ("FERC", "FADP", "FEMP", "FERRFIS")
ROTULO_FUNDO = {"FERC": "FERC", "FADP": "FADEP", "FEMP": "FEMP", "FERRFIS": "FERRFIS"}
_ATRIB_DO_SELO = {"IMOVEL": "RI", "RI": "RI", "LIVRO3": "RI", "RCPN": "RCPN",
                  "CIVIL": "RCPN", "NOTAS": "Notas", "RCPJ": "RTD/PJ",
                  "RCPJ_RTD": "RTD/PJ", "RTDPJ": "RTD/PJ", "PROTESTO": "Protesto"}
_ATRIB_DA_TABELA = (("rc_", "RCPN"), ("hc_", "RCPN"), ("ri_", "RI"), ("ra_", "RI"),
                    ("nt_", "Notas"), ("rg_", "RTD/PJ"), ("at_", "RTD/PJ"),
                    ("pt_", "Protesto"))
_ATRIB_DO_PROTOCOLO = {"RCPN": "RCPN", "RI": "RI", "NOTAS": "Notas", "FIRMAS": "Notas",
                       "RCPJ": "RTD/PJ", "RTD": "RTD/PJ", "PROTESTO": "Protesto"}
TROCO = ("SALDO INICIAL",)


def _atribuicao(lan: sqlite3.Row) -> str:
    if lan["p_atr"]:
        return _ATRIB_DO_PROTOCOLO.get(str(lan["p_atr"]).upper(), str(lan["p_atr"]))
    chave = str(lan["origem_chave"] or "")
    for prefixo, nome in _ATRIB_DA_TABELA:
        if chave.startswith(prefixo):
            return nome
    if lan["dep_ri"]:
        return "RI"
    if lan["dep_nt"]:
        return "Notas"
    if lan["dep_id"]:
        return "uso de depósito prévio (o depósito não diz a atribuição)"
    return "sem identificação"


def _e_troco(lan) -> bool:
    desc = str(lan["descricao"] or "").upper()
    return lan["natureza"] == "COMPLEMENTO" or any(t in desc for t in TROCO)


def _nome_do_operador(con, nome: str) -> str:
    """«Carla» e «Carla Exemplo Lima» são a mesma pessoa: medido em
    06/10/2026, um caixa de setembro foi aberto só com o primeiro nome, e o
    relatório a contava duas vezes. O nome completo do cadastro, quando é um só."""
    n = (nome or "").strip()
    if not n:
        return "sem caixa"
    achados = [r[0] for r in con.execute(
        "SELECT full_name FROM users WHERE active = 1 AND upper(full_name) LIKE ?",
        (n.upper() + "%",))]
    return achados[0] if len(achados) == 1 else n


_USO_DO_DEPOSITO = "Uso do depósito prévio nº "


def _com_o_deposito(lan: dict, deps: dict) -> dict:
    """Amarra o lançamento de uso ao depósito pelo id escrito na descrição."""
    lan.update(dep_id=None, dep_ri=None, dep_nt=None)
    desc = lan.get("descricao") or ""
    if desc.startswith(_USO_DO_DEPOSITO):
        resto = desc[len(_USO_DO_DEPOSITO):].split()
        num = resto[0] if resto else ""
        d = deps.get(int(num)) if num.isdigit() else None
        if d is not None:
            lan.update(dep_id=d[0], dep_ri=d[1], dep_nt=d[2])
            lan["p_atr"] = lan.get("p_atr") or d[3]
    return lan


def _ri_de_valor_alto(con, comp: str, minimo: float = 1000.0) -> list[dict]:
    """Os atos do RI do mês com selo acima de R$ 1.000, e o depósito que os cobriu.

    NASCEU DA DIFERENÇA DE SETEMBRO/2026 (selos R$ 92 mil × caixa R$ 62,6 mil):
    cruzando à mão, R$ 25,9 mil eram dois selos de um mesmo R-1 e da cédula no
    Livro 3 sem depósito nem lançamento com o nome. O casamento é PELO NOME do
    depositante no texto do selo, e isso erra para os dois lados (quem deposita
    nem sempre é a parte) — por isso é lista para conferir, e não achado.
    """
    import re
    import unicodedata

    import selo as SL

    def norm(t):
        t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
        return re.sub(r"\s+", " ", t.upper())

    depositos = [(d[0], d[1], d[2], _reais(d[3]), norm(d[2])) for d in con.execute(
        "SELECT id, numero, depositante, valor FROM cx_depositos")]
    lancados = [(norm(f"{r[0] or ''} {r[1] or ''}"), _reais(r[2]), r[3]) for r in con.execute(
        """SELECT pagador, descricao, valor, data FROM cx_lancamentos
            WHERE data < ? AND COALESCE(excluido,0) = 0""", (comp + "z",))]
    saida = []
    for numero, texto, tabela, ato_id, dia in con.execute(
            """SELECT numero, texto, tabela, ato_id, usado_em FROM sd_selos
                WHERE usado_em LIKE ? AND cancelado_em IS NULL
                  AND atribuicao IN ('IMOVEL','RI','LIVRO3')""", (comp + "%",)):
        dia = str(dia or "")[:10]
        lido = SL.ler_texto(texto or "")
        total = lido.get("total") or 0.0
        if total < minimo or "ISENT" in " ".join(lido.get("marcas") or []).upper():
            continue
        alvo = norm(texto)
        # O SELO CORTA O NOME DA TERCEIRA PARTE: medido em 06/10/2026, a doação
        # de João Bandeira traz «JACI NEVES D...», e Jaci é quem depositou
        # R$ 27.442,16. Por isso vale também o pedaço cortado como começo do nome.
        cortados = [p.rstrip(". ").strip() for p in norm(lido.get("partes") or "").split(",")]
        dep = [f"{d[1]} ({d[2]}, R$ {_brl(d[3])})" for d in depositos
               if d[4] and (d[4] in alvo or any(len(p) >= 8 and d[4].startswith(p)
                                                 for p in cortados))]
        lan = [f"lançamento de {d} (R$ {_brl(v)})" for t, v, d in lancados
               if abs(v - total) < 0.01 and v > 0]
        partes = (lido.get("partes") or "").split(",")[0][:60]
        saida.append({"dia": dia, "ato": f"{tabela or '?'} {ato_id or '?'}", "partes": partes,
                      "total": total, "de_onde": "; ".join(dep + lan[:2]) or ""})
    return sorted(saida, key=lambda x: -x["total"])


def apurar_mes(con: sqlite3.Connection, ano: int, mes: int) -> dict:
    """Os números do mês. Só lê."""
    import selo as SL
    comp = f"{ano:04d}-{mes:02d}"
    con.row_factory = sqlite3.Row
    r: dict = {"comp": comp, "entrou": {}, "receita": {}, "por_operador": {},
               "troco": 0.0, "gratuitos": [0, 0.0], "excluidos": [0, 0.0],
               "estornos": [0, 0.0], "incoerentes": [], "sem_atrib": 0}
    lans = con.execute(
        # O «nº» DO USO É O id DO DEPÓSITO, e não o número impresso
        # (DP2026.09.7): medido em 06/10/2026, «Uso do depósito prévio nº 10»
        # vale R$ 27.442,16, que é o depósito de id 10.
        # O NÚMERO SE LÊ EM PYTHON, e não com `substr` no SQL (teto zero de
        # portabilidade para módulo novo).
        """SELECT l.*, p.atribuicao AS p_atr, c.operador_nome AS operador
             FROM cx_lancamentos l
             LEFT JOIN cx_protocolos p ON p.id = l.protocolo_id
             LEFT JOIN cx_caixas c ON c.id = l.caixa_id
            WHERE l.data LIKE ?""", (comp + "%",)).fetchall()
    deps = {int(d[0]): d for d in con.execute(
        """SELECT d.id, d.ri_protocolo_id, d.nt_ato_id, p.atribuicao FROM cx_depositos d
             LEFT JOIN cx_protocolos p ON p.id = d.protocolo_id""")}
    lans = [_com_o_deposito(dict(x), deps) for x in lans]
    for lan in lans:
        valor = _reais(lan["valor"])
        if lan["excluido"]:
            r["excluidos"][0] += 1
            r["excluidos"][1] += valor
            continue
        if lan["estornado"] or lan["sentido"] == "ESTORNO":
            r["estornos"][0] += 1
            r["estornos"][1] += valor
            continue
        if _e_troco(lan):
            r["troco"] += valor
            continue
        forma = (lan["forma_pagamento"] or "").upper()
        if valor == 0 and _reais(lan["emolumentos"]) > 0:
            r["gratuitos"][0] += 1
            r["gratuitos"][1] += _reais(lan["emolumentos"])
            continue
        if forma == "GRATUITO" and valor > 0:
            r["incoerentes"].append(
                f"{lan['data']} — «{lan['descricao']}»: forma GRATUITO com valor R$ {_brl(valor)}")
        atr = _atribuicao(lan)
        r["sem_atrib"] += atr == "sem identificação"
        if lan["natureza"] == "DEPOSITO_PREVIO":
            chave = "Depósito prévio lançado no caixa"
            r["entrou"][chave] = r["entrou"].get(chave, 0.0) + valor
            continue
        r["receita"][atr] = r["receita"].get(atr, 0.0) + valor
        op = _nome_do_operador(con, lan["operador"])
        r["por_operador"][op] = r["por_operador"].get(op, 0.0) + valor
        if forma != "DEPOSITO_PREVIO":
            nome = {"PIX": "PIX", "DINHEIRO": "Dinheiro", "GRATUITO": "Marcado gratuito",
                    "": "Forma não informada"}.get(forma, forma.title())
            r["entrou"][nome] = r["entrou"].get(nome, 0.0) + valor
    r["depositos_no_mes"] = con.execute(
        "SELECT count(*) FROM cx_depositos WHERE data LIKE ?", (comp + "%",)).fetchone()[0]
    r["depositos_valor"] = sum(_reais(x[0]) for x in con.execute(
        "SELECT valor FROM cx_depositos WHERE data LIKE ?", (comp + "%",)))
    # O DEPÓSITO ENTRA POR FORA DO CAIXA: medido em setembro/2026, R$ 76,5 mil
    # abertos em `cx_depositos` e só R$ 130 lançados no caixa como depósito.
    # Sem esta linha o quadro «dinheiro que entrou» esconderia o maior valor.
    if r["depositos_valor"]:
        r["entrou"]["Depósitos prévios abertos (cadastro de depósitos)"] = r["depositos_valor"]
    r["depositos_em_aberto"] = sum(_reais(x[0]) for x in con.execute(
        "SELECT saldo FROM cx_depositos WHERE COALESCE(encerrado,0) = 0"))
    # selos: o que cada ato declara, e os fundos
    s = {"qtd": 0, "total": 0.0, "emol": 0.0, "fundos": {f: 0.0 for f in FUNDOS},
         "por_atr": {}, "isentos": [0, 0.0], "diferidos": 0}
    for texto, atr in con.execute(
            """SELECT texto, atribuicao FROM sd_selos
                WHERE usado_em LIKE ? AND cancelado_em IS NULL""", (comp + "%",)):
        lido = SL.ler_texto(texto or "")
        marcas = " ".join(lido.get("marcas") or []).upper()
        if "ISENT" in marcas:
            s["isentos"][0] += 1
            s["isentos"][1] += lido.get("emolumentos") or 0.0
            continue
        if "DIFERID" in marcas:
            s["diferidos"] += 1
            continue
        if lido.get("total") is None:
            continue
        s["qtd"] += 1
        s["total"] += lido["total"]
        s["emol"] += lido.get("emolumentos") or 0.0
        for f in FUNDOS:
            s["fundos"][f] += (lido.get("fundos") or {}).get(f, 0.0)
        g = _ATRIB_DO_SELO.get(atr or "", atr or "?")
        s["por_atr"][g] = s["por_atr"].get(g, 0.0) + lido["total"]
    r["selos"] = s
    r["ri_altos"] = _ri_de_valor_alto(con, comp)
    r["caixas_sem_conferencia"] = con.execute(
        """SELECT count(*) FROM cx_caixas WHERE data LIKE ?
              AND fechado_em IS NOT NULL AND conferido_por IS NULL""", (comp,)).fetchone()[0]
    return r


def relatorio_financeiro_html(con: sqlite3.Connection, ano: int, mes: int,
                              hoje: date) -> str:
    r = apurar_mes(con, ano, mes)
    e = html.escape
    parcial = (ano, mes) == (hoje.year, hoje.month)

    def tabela(d: dict, total=True) -> str:
        linhas = "".join(f"<tr><td>{e(k)}</td><td class=n>R$ {_brl(v)}</td></tr>"
                         for k, v in sorted(d.items(), key=lambda kv: -kv[1]))
        if total:
            linhas += (f"<tr class=t><td>Total</td><td class=n>R$ "
                       f"{_brl(sum(d.values()))}</td></tr>")
        return f"<table>{linhas}</table>"

    s = r["selos"]
    receita = sum(r["receita"].values())
    fundos = "".join(f"<tr><td>{ROTULO_FUNDO[f]}</td><td class=n>R$ {_brl(v)}</td></tr>"
                     for f, v in s["fundos"].items())
    incoerentes = "".join(f"<li>{e(x)}</li>" for x in r["incoerentes"]) or "<li>nenhum</li>"
    linhas_ri = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td class=n>R$ {}</td><td>{}</td></tr>".format(
            x["dia"], e(x["ato"]), e(x["partes"]), _brl(x["total"]),
            e(x["de_onde"]) if x["de_onde"] else "<b>— não achado —</b>")
        for x in r["ri_altos"]) or "<tr><td colspan=5>nenhum</td></tr>"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Financeiro {mes:02d}/{ano}</title><style>
body{{font:14px system-ui,sans-serif;margin:16px;color:#222;background:#fff;max-width:900px}}
table{{border-collapse:collapse;min-width:320px;margin:4px 0 14px}}td{{border-bottom:1px solid #ddd;padding:5px 10px}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}tr.t td{{font-weight:700}}small{{color:#555}}
.aviso{{background:#fff7e0;border-left:4px solid #c80;padding:8px 12px}}
</style></head><body>
<h1>Relatório financeiro — {mes:02d}/{ano}{' (parcial, até ' + hoje.strftime('%d/%m') + ')' if parcial else ''}</h1>
<p><small>Lido do caixa e do razão dos selos do sistema{', a partir de ' + _dia(IMPLANTACAO).strftime('%d/%m/%Y') if (ano, mes) == (_dia(IMPLANTACAO).year, _dia(IMPLANTACAO).month) else ''}.
Só leitura. Despesas da serventia, ISS e o que entrou fora do caixa do sistema não estão aqui.</small></p>

<h2>1. Receita reconhecida no mês: R$ {_brl(receita)}</h2>
<p><small>Inclui o uso de depósitos prévios (receita do ato que saiu). Exclui troco, gratuidades, estornos e excluídos.</small></p>
<h3>Por atribuição</h3>{tabela(r['receita'])}
<p><small>{r['sem_atrib']} lançamento(s) sem protocolo nem ato amarrado — a atribuição não se sabe.</small></p>
<h3>Por caixa (quem recebeu)</h3>{tabela(r['por_operador'])}

<h2>2. Dinheiro que entrou no mês</h2>
{tabela(r['entrou'])}
<p><small>O depósito prévio é cadastrado à parte e, nesta casa, quase nunca vira lançamento no caixa.
As duas linhas de depósito podem se sobrepor quando o mesmo depósito foi cadastrado e também lançado.</small></p>
<p><small>Depósitos prévios abertos no mês: {r['depositos_no_mes']} (R$ {_brl(r['depositos_valor'])}).
Saldo de depósitos ainda não usados (dinheiro de clientes em guarda): <b>R$ {_brl(r['depositos_em_aberto'])}</b>.</small></p>

<h2>3. Selos usados no mês</h2>
<p>{s['qtd']} selo(s) pagos declarando <b>R$ {_brl(s['total'])}</b>, dos quais emolumentos R$ {_brl(s['emol'])}.</p>
<h3>Fundos declarados nos selos (repasse)</h3><table>{fundos}<tr class=t><td>Total</td><td class=n>R$ {_brl(sum(s['fundos'].values()))}</td></tr></table>
<h3>Selos por atribuição</h3>{tabela(s['por_atr'])}
<p>Isentos: {s['isentos'][0]} selo(s), emolumentos que teriam: R$ {_brl(s['isentos'][1])}. Diferidos: {s['diferidos']}.</p>

<h2>4. Gratuidades lançadas no caixa</h2>
<p>{r['gratuitos'][0]} ato(s) de valor zero, com R$ {_brl(r['gratuitos'][1])} de emolumentos — base da compensação.</p>

<h2>5. Fechamento: selos × receita</h2>
<p class=aviso>Selos declaram R$ {_brl(s['total'])}; a receita reconhecida no caixa é R$ {_brl(receita)};
diferença de <b>R$ {_brl(receita - s['total'])}</b>. A diferença não é acusação: pode ser ato gratuito
cujo selo não leva a marca de isento, receita lançada sem amarrar ao ato, ou dinheiro recebido por fora do caixa.</p>

<h2>6. Atos do RI acima de R$ 1.000: de onde veio o dinheiro</h2>
<p><small>Casamento pelo NOME do depositante dentro do texto do selo, ou por lançamento de valor igual.
Quem deposita nem sempre é a parte: «não achado» quer dizer «conferir», e não «não pago».</small></p>
<table><tr><td><b>Dia</b></td><td><b>Ato</b></td><td><b>Parte</b></td><td class=n><b>Selo</b></td><td><b>Pagamento achado</b></td></tr>
{linhas_ri}</table>

<h2>7. O que pede atenção</h2>
<ul><li>Lançamentos excluídos: {r['excluidos'][0]} (R$ {_brl(r['excluidos'][1])})</li>
<li>Estornos: {r['estornos'][0]} (R$ {_brl(r['estornos'][1])})</li>
<li>Movimento de troco (saldo inicial e complemento), fora da receita: R$ {_brl(r['troco'])}</li>
<li>Caixas do mês fechados e não conferidos: {r['caixas_sem_conferencia']}</li></ul>
<h3>Lançamentos incoerentes</h3><ul>{incoerentes}</ul>
</body></html>"""


# ------------------------------------------------------------ a semana

def resumo_semanal_html(con: sqlite3.Connection, hoje: date) -> str:
    """O que a conferência achou, o que se resolveu e quem está devendo — 7 dias."""
    con.row_factory = sqlite3.Row
    desde = (hoje - timedelta(days=7)).isoformat()
    e = html.escape
    novos = con.execute("SELECT count(*) FROM ge_achados WHERE primeiro_visto_em >= ?",
                        (desde,)).fetchone()[0]
    resolvidos = con.execute(
        "SELECT regra, titulo FROM ge_achados WHERE resolvido_em >= ? ORDER BY resolvido_em",
        (desde,)).fetchall()
    abertos = con.execute(
        "SELECT count(*) FROM ge_achados WHERE resolvido_em IS NULL").fetchone()[0]
    pessoas = con.execute(
        """SELECT COALESCE(u.full_name, '— sem responsável —') AS quem,
                  sum(t.status NOT IN ('CONCLUIDA','CANCELADA')) AS abertas,
                  sum(t.status NOT IN ('CONCLUIDA','CANCELADA') AND t.due_date < ?) AS vencidas,
                  sum(t.status = 'CONCLUIDA' AND t.completed_at >= ?) AS concluidas
             FROM tasks t LEFT JOIN users u ON u.id = t.assigned_user_id
         GROUP BY 1 ORDER BY vencidas DESC, abertas DESC""",
        (hoje.isoformat(), desde)).fetchall()
    vencidas = con.execute(
        """SELECT t.title, t.due_date, COALESCE(u.full_name,'—') AS quem
             FROM tasks t LEFT JOIN users u ON u.id = t.assigned_user_id
            WHERE t.source_type = 'GESTOR' AND t.status NOT IN ('CONCLUIDA','CANCELADA')
              AND t.due_date < ? ORDER BY t.due_date""", (hoje.isoformat(),)).fetchall()
    linhas_p = "".join(
        f"<tr><td>{e(p['quem'])}</td><td class=n>{p['abertas'] or 0}</td>"
        f"<td class=n>{p['vencidas'] or 0}</td><td class=n>{p['concluidas'] or 0}</td></tr>"
        for p in pessoas if (p["abertas"] or p["concluidas"]))
    linhas_v = "".join(
        f"<li><b>{e(v['quem'])}</b> — {e(v['title'])} <small>(venceu {v['due_date']})</small></li>"
        for v in vencidas) or "<li>nenhuma</li>"
    linhas_r = "".join(f"<li>{e(x['titulo'])}</li>" for x in resolvidos) or "<li>nenhum</li>"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Semana até {hoje:%d/%m}</title><style>
body{{font:14px system-ui,sans-serif;margin:16px;color:#222;background:#fff;max-width:900px}}
table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #ddd;padding:5px 10px;text-align:left}}
td.n{{text-align:right}}small{{color:#555}}
</style></head><body>
<h1>Resumo da semana — {(hoje - timedelta(days=7)):%d/%m} a {hoje:%d/%m/%Y}</h1>
<p>A conferência achou <b>{novos}</b> pendência(s) nova(s) e viu <b>{len(resolvidos)}</b> resolvida(s).
Ficam <b>{abertos}</b> em aberto.</p>
<h2>Tarefas do gestor vencidas</h2><ul>{linhas_v}</ul>
<h2>Cada pessoa (todas as tarefas da casa)</h2>
<table><tr><th>Pessoa</th><th>Abertas</th><th>Vencidas</th><th>Concluídas na semana</th></tr>{linhas_p}</table>
<h2>Resolvidas na semana</h2><ul>{linhas_r}</ul>
</body></html>"""


def escrever(con: sqlite3.Connection, hoje: date, pasta: Path) -> list[Path]:
    """Grava o financeiro do mês corrente e do anterior, e o resumo da semana."""
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    meses = {(hoje.year, hoje.month)}
    anterior = hoje.replace(day=1) - timedelta(days=1)
    if anterior.isoformat() >= IMPLANTACAO[:7]:
        meses.add((anterior.year, anterior.month))
    for ano, mes in sorted(meses):
        caminho = pasta / f"financeiro_{ano:04d}-{mes:02d}.html"
        caminho.write_text(relatorio_financeiro_html(con, ano, mes, hoje), encoding="utf-8")
        feitos.append(caminho)
    semana = pasta / f"resumo_semana_{hoje.isocalendar()[0]}-S{hoje.isocalendar()[1]:02d}.html"
    semana.write_text(resumo_semanal_html(con, hoje), encoding="utf-8")
    feitos.append(semana)
    return feitos

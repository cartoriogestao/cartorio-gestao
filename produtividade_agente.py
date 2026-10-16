"""
O AGENTE DE PRODUTIVIDADE — item 12 da série de agentes.

    «aqui vamos fiscalizar a eficiência do nosso trabalho e ver como podemos
     fazer mais trabalho com menos recursos. analise os atos praticados e o
     relatório de produtividade do sistema e faça uma crítica inicial ao
     trabalho de cada escrevente e encontre caminhos para automatizarmos
     esses trabalhos»                                  — o oficial, 11/10/2026

SÓ LÊ. Não grava no banco, não abre tarefa, não cobra ninguém. Junta quatro
fontes que já existem e as põe lado a lado, por pessoa:

    | fonte | o que diz | o que NÃO diz |
    |---|---|---|
    | `sd_selos.obtido_por` | quantos atos com selo cada um praticou | ato sem selo, trabalho fora do sistema |
    | `audit_logs` | cada clique que vira ato, com hora | o tempo gasto fora da tela |
    | `prod_registros` | o que a pessoa DECLARA que fez, com hora | é texto livre: mede o que ela escreveu |
    | `tasks` | o que está atribuído e vencido | o tamanho de cada tarefa |

POR QUE O AUTOR VEM DO SELO E DO audit_logs, E NÃO DA COLUNA DO ATO
    Medido em 11/10/2026 na produção: cada tabela guarda o autor num lugar e
    numa forma — `ri_atos.lavrado_nome` (nome; `lavrado_por` é nulo nos 38),
    `nt_reconhecimentos.oficial` (nome, às vezes só o primeiro nome),
    `rc_atos.criado_por` (nome), `ri_certidoes.emitida_por` (ID), e o caixa
    pelo operador do caixa (`cx_lancamentos.criado_por` é nulo). Contar por
    pessoa coluna a coluna exige seis réguas. O selo e o audit_logs são uma só.
    > Correção do mesmo dia: a primeira versão deste parágrafo dizia que «a
    > coluna do ato não serve» porque olhei só `lavrado_por`/`criado_por`. O
    > nome estava em `lavrado_nome` e `oficial` — não achar onde procurei não
    > provava que não existia.

O QUE ESTE MÓDULO NÃO FAZ
    - nota, ranking ou «nota de desempenho»: põe números ao lado do que cada um
      declarou; a crítica é de quem lê.
    - medir o que acontece fora do sistema (CRC, ONR, Portal do Selo,
      WhatsApp): disso só se sabe o que a pessoa declarou no controle diário.
      É justamente o que se propõe trazer para dentro.

SQL sem `substr(` nem `||` (teto zero de `test_portabilidade` para módulo
novo): recorte de data em Python, filtro por `>=`.

Uso:  python produtividade_agente.py --desde 2026-09-10 --saida painel.html
      (sem --banco, lê a produção em modo somente-leitura)
"""
from __future__ import annotations

import argparse
import html
import re
import sqlite3
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

BANCO_PRODUCAO = r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3"

# Ações do audit_logs que são ENTREGA (ato, certidão, registro) — o resto é
# consulta, impressão de apoio ou navegação.
ACOES_DE_ENTREGA = {
    "RCPN_CERTIDAO": "certidão do RCPN",
    "RCPN_AVERBAR_CPF": "averbação de CPF",
    "RCPN_ASSENTO_NOVO": "assento novo do RCPN",
    "RCPN_ATO": "ato do RCPN",
    "NT_RECONHECIMENTO": "reconhecimento de firma",
    "NT_AUTENTICACAO": "autenticação",
    "RI_CERTIDAO_EMITIDA": "certidão do RI",
    "RI_CERTIDAO_NEGATIVA_EMITIDA": "certidão negativa do RI",
    "RI_ATO_LAVRADO": "ato do RI lavrado",
    "RI_PRENOTACAO": "prenotação",
    "PROTOCOLO_ABERTO": "protocolo aberto",
    "RECEPCAO_EMITIDA": "recepção de documento",
    "EXPEDIENTE_CREATED": "expediente (malote) cadastrado",
    "NT_FICHA_ENVIADA": "cartão de firma digitalizado",
    "TASK_CONCLUIDA": "tarefa concluída",
}
# Sinais de retrabalho ou de atrito.
ACOES_DE_RETRABALHO = {
    "RCPN_ASSENTO_CORRIGIDO": "assento corrigido depois de digitado",
    "RCPN_CERTIDAO_CANCELADA": "certidão cancelada",
    "CAIXA_LANCAMENTO_EXCLUIDO": "lançamento de caixa excluído",
    "PROTOCOLO_ITEM_REMOVIDO": "item de protocolo removido",
    "LOGIN_FAILURE": "senha errada",
    "LOGIN_SUCCESS": "entradas no sistema",
    "AJUDA_PROBLEMA_RELATADO": "problema relatado na ajuda",
}
# Intervalo mediano entre dois atos iguais seguidos (ritmo do balcão).
ACOES_DE_RITMO = ("RCPN_CERTIDAO", "RCPN_AVERBAR_CPF", "NT_RECONHECIMENTO",
                  "RI_CERTIDAO_EMITIDA", "RI_ATO_LAVRADO", "PROTOCOLO_ABERTO")

# Temas do controle diário: o primeiro que casar leva. Texto sem acento,
# minúsculo. As palavras saíram dos 182 lançamentos de 06–09/10/2026.
TEMAS = (
    ("pausa", r"lanch|almoc|banheiro|agua|exame|^teste$"),
    ("Portal do Selo", r"portal|selos? pend|lanc\w* (os )?selos"),
    ("CRC / e-Protocolo", r"crc|e.?protocolo"),
    ("ONR", r"onr|reprograf"),
    ("WhatsApp", r"whats"),
    ("malote / ofícios / CENSEC", r"malote|oficio|censec"),
    # OS NOMES DOS COLEGAS VÊM DA EQUIPE CADASTRADA, e não do código: nome real
    # da equipe não fica escrito no programa (portão anti-vazamento,
    # 15/10/2026). `tema_de` troca o marcador pelos primeiros nomes.
    ("ajudar colega", r"ajud\w* (a )?(colega{colegas})"),
    ("aprender / robô", r"aprend|robo|chat"),
    ("RCPN: registro", r"registro|termo de casamento|habilita|casamento|obito|retifica"),
    ("RCPN: 2ª via", r"2.? ?via|certidao|materializ"),
    ("Notas: procuração", r"procura"),
    ("Notas: firma/autenticação", r"reconhec|autentic|copia"),
    ("protocolo / orçamento / caixa", r"protocolo|orcamento|fechamento de cx|\bcx\b"),
    ("balcão (sem dizer o quê)", r"balcao|atend|clientes?"),
    ("RI: fichas / digitalização / livros", r"ficha|matricula|digitaliz|livros?|inteiro teor"),
    ("tarefas / pendências (sem dizer quais)", r"tarefa|pendenc|check|trabalhos"),
    ("TI", r"impressora|impress|driver"),
    ("protesto", r"protest"),
)
FORA_DO_SISTEMA = {"Portal do Selo", "CRC / e-Protocolo", "ONR", "WhatsApp",
                   "malote / ofícios / CENSEC"}
MARCA_CRONOMETRO_ESQUECIDO = "Cronômetro ficou aberto"


# ----------------------------------------------------------------- utilidades

def _sem_acento(s: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn").lower()


def _quando(s: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s)[:19])
    except (TypeError, ValueError):
        return None


def _minutos(hhmm: Any) -> int | None:
    try:
        h, m = str(hhmm)[:5].split(":")
        return int(h) * 60 + int(m)
    except (TypeError, ValueError):
        return None


def tema_de(tarefa: Any, colegas: tuple[str, ...] = ()) -> str:
    s = _sem_acento(tarefa)
    alternativas = "".join("|" + re.escape(_sem_acento(n)) for n in colegas if n)
    for nome, rx in TEMAS:
        if re.search(rx.replace("{colegas}", alternativas), s):
            return nome
    return "outros"


def abrir_somente_leitura(caminho: str = BANCO_PRODUCAO) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)


def pessoas(con: sqlite3.Connection) -> list[dict[str, Any]]:
    """Equipe humana ativa — sem robô e sem o usuário `teste`."""
    # Sem PRAGMA (teto zero de portabilidade): tenta com a coluna do robô e,
    # numa instalação que ainda não a tem, sem ela.
    base = "SELECT id, username, full_name, funcao FROM users WHERE active=1 AND username<>'teste'"
    try:
        linhas = con.execute(base + " AND COALESCE(eh_robo,0)=0 ORDER BY id").fetchall()
    except sqlite3.OperationalError:
        linhas = con.execute(base + " ORDER BY id").fetchall()
    saida = []
    for uid, user, nome, funcao in linhas:
        saida.append({"id": uid, "username": user, "nome": nome or user,
                      "funcao": funcao or ""})
    return saida


def _dono_do_selo(obtido_por: Any, equipe: list[dict[str, Any]]) -> str | None:
    """`obtido_por` vem como nome completo (sistema) ou primeiro nome em
    maiúsculas (selador antigo). Casa pelos dois."""
    s = _sem_acento(obtido_por).strip()
    if not s:
        return None
    for p in equipe:
        if s == _sem_acento(p["nome"]) or s == p["username"].lower():
            return p["username"]
    primeiro = s.split()[0]
    for p in equipe:
        if primeiro == _sem_acento(p["nome"]).split()[0]:
            return p["username"]
    return None


# -------------------------------------------------------------------- medidas

def medir(con: sqlite3.Connection, desde: str, ate: str | None = None) -> dict[str, Any]:
    ate = ate or "9999-12-31"
    equipe = pessoas(con)
    por: dict[str, dict[str, Any]] = {
        p["username"]: {"pessoa": p, "selos": Counter(), "selos_semana": Counter(),
                        "entregas": Counter(), "retrabalho": Counter(),
                        "ritmo": {}, "dias": set(), "primeira": [], "ultima": [],
                        "temas": Counter(), "lancamentos": 0, "esquecido_min": 0,
                        "tarefas": Counter()}
        for p in equipe}

    # 1. selos
    for obtido_por, obtido_em, tabela in con.execute(
            "SELECT obtido_por, obtido_em, tabela FROM sd_selos "
            "WHERE obtido_em >= ? AND obtido_em < ? AND cancelado_em IS NULL",
            (desde, ate + "~")):
        u = _dono_do_selo(obtido_por, equipe)
        if u:
            por[u]["selos"][tabela or "?"] += 1
            d = _quando(obtido_em)
            if d:
                por[u]["selos_semana"][d.isocalendar()[1]] += 1

    # 2. audit_logs: entregas, retrabalho, dias e horário, ritmo
    marcas: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    por_dia: dict[str, dict[date, list[datetime]]] = defaultdict(lambda: defaultdict(list))
    for user, ts, acao in con.execute(
            "SELECT lower(username_snapshot), ts, action FROM audit_logs "
            "WHERE ts >= ? AND ts < ? AND user_id IS NOT NULL", (desde, ate + "~")):
        if user not in por:
            continue
        d = _quando(ts)
        if not d:
            continue
        if acao in ACOES_DE_ENTREGA:
            por[user]["entregas"][acao] += 1
        if acao in ACOES_DE_RETRABALHO:
            por[user]["retrabalho"][acao] += 1
        if acao in ACOES_DE_RITMO:
            marcas[(user, acao)].append(d)
        por_dia[user][d.date()].append(d)
    for user, dias in por_dia.items():
        por[user]["dias"] = set(dias)
        por[user]["primeira"] = sorted(min(v).strftime("%H:%M") for v in dias.values())
        por[user]["ultima"] = sorted(max(v).strftime("%H:%M") for v in dias.values())
    for (user, acao), lista in marcas.items():
        lista.sort()
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(lista, lista[1:])
                if a.date() == b.date() and 0 < (b - a).total_seconds() < 90 * 60]
        if len(gaps) >= 3:
            por[user]["ritmo"][acao] = (len(lista), statistics.median(gaps))

    # 3. controle diário (prod_registros)
    ids = {p["id"]: p["username"] for p in equipe}
    colegas = tuple(sorted({(p.get("full_name") or "").split()[0]
                            for p in equipe if (p.get("full_name") or "").split()}))
    for uid, d, hi, hf, pausa, tarefa, obs in con.execute(
            "SELECT responsavel_user_id, data_registro, hora_inicio, hora_fim, pausas_min, "
            "tarefa, observacoes FROM prod_registros WHERE data_registro >= ? AND data_registro <= ?",
            (desde, ate)):
        u = ids.get(uid)
        if not u:
            continue
        por[u]["lancamentos"] += 1
        a, b = _minutos(hi), _minutos(hf)
        if a is None or b is None:
            continue
        if obs and MARCA_CRONOMETRO_ESQUECIDO in obs:
            por[u]["esquecido_min"] += b - a
            continue
        por[u]["temas"][tema_de(tarefa, colegas)] += max(0, b - a - (pausa or 0))

    # 4. tarefas
    hoje = date.today().isoformat()
    # A SUSPENSA NÃO PESA NA CRÍTICA — relato #132, decisão do oficial em
    # 15/10/2026: enquanto espera a data ou a condição, ela não é aberta a
    # cobrar de ninguém, nem vencida.
    import tarefa_suspensao as TS
    cond_suspensa, params_suspensa = TS.condicao_suspensa(None, hoje, con=con)
    suspensas = {r[0] for r in con.execute(
        f"SELECT id FROM tasks WHERE {cond_suspensa}", params_suspensa)}
    for tid, uid, status, venc in con.execute(
            "SELECT id, assigned_user_id, status, due_date FROM tasks"):
        u = ids.get(uid)
        if not u or tid in suspensas:
            continue
        if status == "ABERTA":
            por[u]["tarefas"]["abertas"] += 1
            if venc and str(venc)[:10] < hoje:
                por[u]["tarefas"]["vencidas"] += 1

    # 5. certidões do RCPN: o assento já estava no sistema ou foi digitado na hora?
    certidao = Counter()
    for emitida, criado, origem in con.execute(
            "SELECT c.emitida_em, a.criado_em, a.origem FROM rc_certidoes c "
            "LEFT JOIN rc_assentos a ON a.id=c.assento_id WHERE c.emitida_em >= ? AND c.emitida_em < ?",
            (desde, ate + "~")):
        if str(criado or "")[:10] == str(emitida or "")[:10]:
            certidao["digitado no mesmo dia"] += 1
        else:
            certidao["já estava no sistema"] += 1

    # 6. acervo do RCPN com teor (o que permite certidão sem digitar)
    acervo = []
    for especie, total, com_teor in con.execute(
            "SELECT especie, COUNT(*), SUM(CASE WHEN length(COALESCE(teor,''))>200 THEN 1 ELSE 0 END) "
            "FROM rc_assentos GROUP BY especie ORDER BY 2 DESC"):
        acervo.append((especie, total, com_teor or 0))

    return {"desde": desde, "ate": ate, "por": por, "certidao_rcpn": certidao,
            "acervo_rcpn": acervo, "medido_em": datetime.now().isoformat(timespec="minutes")}


# ---------------------------------------------------------------------- tela

def _mediana(v: list[str]) -> str:
    return v[len(v) // 2] if v else "—"


def render_html(m: dict[str, Any]) -> str:
    e = html.escape
    partes = [f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>Painel de produtividade</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1d2433;background:#fff;max-width:1100px}}
h1{{font-size:22px}} h2{{font-size:18px;margin-top:28px;border-bottom:1px solid #d6dae3;padding-bottom:4px}}
table{{border-collapse:collapse;margin:6px 0 14px}} td,th{{border:1px solid #d6dae3;padding:3px 8px;font-size:13px;text-align:left}}
th{{background:#f2f4f8}} .num{{text-align:right}} .fora{{color:#a3360b;font-weight:600}} small{{color:#5b6475}}
</style>
<h1>Painel de produtividade</h1>
<p><small>De {e(m['desde'])} até {e(m['ate'] if m['ate'] != '9999-12-31' else 'hoje')} · medido em {e(m['medido_em'])} ·
só leitura · o autor vem do selo e do registro de ações, não da coluna do ato.</small></p>"""]

    c = m["certidao_rcpn"]
    tot = sum(c.values())
    if tot:
        partes.append(f"<p><b>Certidões do RCPN no período:</b> {tot}; em "
                      f"<b>{c['digitado no mesmo dia']}</b> ({100*c['digitado no mesmo dia']/tot:.0f}%) "
                      f"o assento teve de ser digitado no balcão no mesmo dia.</p>")
    partes.append("<table><tr><th>Acervo do RCPN</th><th class=num>assentos</th><th class=num>com teor</th></tr>")
    for esp, t, ct in m["acervo_rcpn"]:
        partes.append(f"<tr><td>{e(str(esp))}</td><td class=num>{t}</td><td class=num>{ct} ({100*ct/max(t,1):.0f}%)</td></tr>")
    partes.append("</table>")

    for user, d in m["por"].items():
        p = d["pessoa"]
        selos = sum(d["selos"].values())
        if not (selos or d["entregas"] or d["lancamentos"] or d["tarefas"]):
            continue
        partes.append(f"<h2>{e(p['nome'])} <small>· {e(p['funcao'])}</small></h2>")
        ndias = len(d["dias"])
        partes.append(f"<p>{selos} atos com selo · {ndias} dias com ação no sistema"
                      + (f" ({selos/ndias:.1f} selos/dia)" if ndias else "")
                      + f" · primeira ação (mediana) {_mediana(d['primeira'])}, última {_mediana(d['ultima'])}"
                      + f" · tarefas abertas {d['tarefas']['abertas']}, vencidas {d['tarefas']['vencidas']}</p>")
        if d["selos"]:
            partes.append("<table><tr><th>selos por tabela</th><th class=num>n</th></tr>"
                          + "".join(f"<tr><td>{e(k)}</td><td class=num>{v}</td></tr>" for k, v in d["selos"].most_common())
                          + "</table>")
        if d["selos_semana"]:
            partes.append("<p><small>selos por semana do ano: "
                          + ", ".join(f"s{k}: {v}" for k, v in sorted(d["selos_semana"].items())) + "</small></p>")
        linhas = [(ACOES_DE_ENTREGA[k], v) for k, v in d["entregas"].most_common()]
        linhas += [(ACOES_DE_RETRABALHO[k], v) for k, v in d["retrabalho"].most_common()]
        if linhas:
            partes.append("<table><tr><th>registro de ações</th><th class=num>n</th></tr>"
                          + "".join(f"<tr><td>{e(k)}</td><td class=num>{v}</td></tr>" for k, v in linhas) + "</table>")
        if d["ritmo"]:
            partes.append("<table><tr><th>ritmo: minutos entre dois atos iguais seguidos (mediana)</th><th class=num>atos</th><th class=num>min</th></tr>"
                          + "".join(f"<tr><td>{e(ACOES_DE_ENTREGA.get(k, k))}</td><td class=num>{n}</td><td class=num>{g:.0f}</td></tr>"
                                    for k, (n, g) in d["ritmo"].items()) + "</table>")
        if d["temas"]:
            tt = sum(d["temas"].values()) or 1
            partes.append(f"<table><tr><th>controle diário: o que declarou ({d['lancamentos']} lançamentos)</th><th class=num>min</th><th class=num>%</th></tr>"
                          + "".join(f"<tr><td class='{'fora' if k in FORA_DO_SISTEMA else ''}'>{e(k)}</td><td class=num>{v}</td><td class=num>{100*v/tt:.0f}</td></tr>"
                                    for k, v in d["temas"].most_common()) + "</table>")
        if d["esquecido_min"]:
            partes.append(f"<p class=fora>Cronômetro esquecido aberto: {d['esquecido_min']} min (fora da soma acima).</p>")
    partes.append("<p><small>Em laranja: trabalho feito fora do sistema — só se sabe dele o que a pessoa declarou.</small></p>")
    return "\n".join(partes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Painel de produtividade (só leitura).")
    ap.add_argument("--banco", default=BANCO_PRODUCAO)
    ap.add_argument("--desde", required=True)
    ap.add_argument("--ate")
    ap.add_argument("--saida", required=True)
    a = ap.parse_args(argv)
    con = abrir_somente_leitura(a.banco)
    try:
        Path(a.saida).write_bytes(render_html(medir(con, a.desde, a.ate)).encode("utf-8"))
    finally:
        con.close()
    print(a.saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

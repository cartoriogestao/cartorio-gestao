"""A rodada do robô oficial: os robôs, a mesa e as perguntas — num relatório só.

    «robo responsavel por operacionalizar os outros robos, gerir as pendencias
     pessoais no cartorio gestao e lidar com toda complexidade de atos e
     responsabilidades que este oficial de cartorio carrega» — 09/10/2026

A ORDEM DA RODADA
    1. a SAÚDE dos robôs (`oficial_robos`) — e robô quebrado vira TAREFA para
       quem responde pela TI, que fecha sozinha quando ele volta a rodar bem;
    2. a fila de DECISÕES (`oficial_decisoes`) recebe o que não está medido;
    3. a MESA do oficial (`oficial_pauta`) e a AGENDA dele (`oficial_obrigacoes`);
    4. sai `mesa_do_oficial_AAAA-MM-DD.html`, e o robô bate o próprio ponto.

    Cada parte é isolada: a que quebra vira «não mediu» no relatório, e as
    outras saem. Robô que se cala porque uma parte quebrou é o defeito que ele
    existe para pegar nos outros.

O MODO «SÓ LER»
    `--so-ler` abre o banco em modo de leitura: não grava tarefa, nem decisão,
    nem batida — só escreve o relatório. É o modo de conferir o robô contra a
    produção antes de ligá-lo nela, que é a ordem desta casa.

O QUE ELE NÃO FAZ
    Não lavra, não sela, não cobra, não envia a Central nenhuma, não muda
    configuração de outro robô, e não fecha tarefa que não seja dele.
"""
from __future__ import annotations

import argparse
import html
import sqlite3
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

import oficial_decisoes as OD
import oficial_obrigacoes as OO
import oficial_pauta as OP
import oficial_robos as OR

SOURCE_TYPE = "OFICIAL"
ABERTA = ("CONCLUIDA", "CANCELADA")


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _historico(con, task_id: int, acao: str, nota: str, antes=None, depois=None) -> None:
    con.execute(
        """INSERT INTO task_history (task_id, ts, user_id, action, old_value,
               new_value, note) VALUES (?, ?, NULL, ?, ?, ?, ?)""",
        (task_id, _agora(), acao, antes, depois, nota))


def _quem_cuida_da_ti(con) -> tuple[int | None, int | None]:
    """O titular e o substituto da TI pela distribuição do oficial; senão o ADMIN."""
    try:
        linha = con.execute("SELECT user_id, substituto_id FROM ge_responsaveis "
                            "WHERE setor='TI'").fetchone()
        if linha:
            return int(linha[0]), (int(linha[1]) if linha[1] else None)
    except sqlite3.Error:
        pass
    return OP.dono_da_mesa(con), None


def sincronizar_tarefas_dos_robos(con: sqlite3.Connection, achados: list[dict],
                                  hoje: date) -> dict:
    """Robô quebrado vira tarefa da TI; quando volta a rodar bem, ela fecha sozinha.

    Só os CRÍTICOS viram tarefa — robô que ainda não foi ligado não é defeito,
    e alarme que soa sempre é alarme que ninguém ouve. A tarefa é desta origem
    (`OFICIAL`) e só ela é fechada aqui: tarefa de outro robô ou de gente não
    se toca.
    """
    criticos = {a["chave"]: a for a in achados if a["gravidade"] == "CRITICO"}
    agora = _agora()
    titular, substituto = _quem_cuida_da_ti(con)
    criadas = fechadas = atualizadas = 0
    marcas = ",".join("?" * len(ABERTA))
    abertas = {r[1]: r[0] for r in con.execute(
        f"""SELECT id, source_ref FROM tasks WHERE source_type = ?
              AND status NOT IN ({marcas})""", (SOURCE_TYPE, *ABERTA))}
    for chave, a in criticos.items():
        ref = f"{SOURCE_TYPE}:{chave}"
        descricao = (f"{a['titulo']}\n\nO que se mediu: {a['detalhe']}\n\n"
                     f"Como resolver: {a['como_resolver'] or '—'}\n\n"
                     "Tarefa aberta pelo robô oficial. Ela fecha sozinha na primeira "
                     "rodada em que o robô voltar a rodar bem — não precisa concluir à mão.")
        if ref in abertas:
            con.execute("UPDATE tasks SET description=?, updated_at=? WHERE id=?",
                        (descricao, agora, abertas[ref]))
            atualizadas += 1
            continue
        cur = con.execute(
            """INSERT INTO tasks (source_type, source_ref, title, description, sector,
                   system_name, priority, status, start_date, due_date, assigned_user_id,
                   backup_user_id, evidence_required, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'TI', 'Robô oficial', 'CRITICA', 'ABERTA', ?, ?, ?, ?,
                       0, ?, ?)""",
            (SOURCE_TYPE, ref, f"[Robô] {a['robo_nome']}: {a['titulo']}"[:200], descricao,
             hoje.isoformat(), hoje.isoformat(), titular, substituto, agora, agora))
        _historico(con, int(cur.lastrowid), "CRIADA", "Aberta pelo robô oficial.")
        criadas += 1
    for ref, task_id in abertas.items():
        if ref[len(SOURCE_TYPE) + 1:] in criticos:
            continue
        con.execute("UPDATE tasks SET status='CONCLUIDA', completed_at=?, updated_at=? "
                    "WHERE id=?", (agora, agora, task_id))
        _historico(con, task_id, "ALTEROU_STATUS",
                   "O robô voltou a rodar bem — fechada pelo robô oficial.",
                   antes="ABERTA", depois="CONCLUIDA")
        fechadas += 1
    return {"criadas": criadas, "fechadas": fechadas, "atualizadas": atualizadas}


# ---------------------------------------------------------------- relatório

_COR = {"CRITICO": "#b42318", "ATENCAO": "#b54708", "NAO_MEDIU": "#6941c6",
        "INFO": "#475467", "OK": "#067647", "ALERTA": "#b42318"}


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _data(texto: str | None) -> str:
    if not texto:
        return "—"
    t = str(texto)[:10]
    return f"{t[8:10]}/{t[5:7]}/{t[:4]}" if len(t) == 10 else _e(texto)


def _tabela(cabecalho: list[str], linhas: list[list[str]], vazio: str) -> str:
    if not linhas:
        return f"<p class='vazio'>{_e(vazio)}</p>"
    th = "".join(f"<th>{_e(c)}</th>" for c in cabecalho)
    corpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in ln) + "</tr>" for ln in linhas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>"


def _marca(gravidade: str) -> str:
    return (f"<span class='marca' style='background:{_COR.get(gravidade, '#475467')}'>"
            f"{_e(gravidade)}</span>")


def relatorio_html(resumo: dict) -> str:
    mesa = resumo.get("mesa") or {}
    hoje = resumo["hoje"]
    partes = [f"<h1>Mesa do oficial — {_data(hoje)}</h1>",
              f"<p class='sub'>{_e(mesa.get('dono_nome', ''))} · gerada pelo robô oficial em "
              f"{_e(resumo.get('gerada_em', ''))}"
              + (" · <b>modo só ler</b>: nada foi gravado" if resumo.get("so_ler") else "")
              + "</p>"]
    for nome, erro in (resumo.get("nao_mediu") or {}).items():
        partes.append(f"<p class='erro'>{_marca('NAO_MEDIU')} A parte «{_e(nome)}» não "
                      f"rodou: {_e(erro)}</p>")

    # 1. Robôs — o que precisa de alguém
    graves = [a for a in resumo.get("saude", []) if a["gravidade"] in ("CRITICO", "ATENCAO",
                                                                         "NAO_MEDIU")]
    partes.append("<h2>1. Os robôs — o que precisa de alguém</h2>")
    partes.append(_tabela(
        ["", "Robô", "O que se mediu", "Como resolver"],
        [[_marca(a["gravidade"]), _e(a["robo_nome"]),
          f"<b>{_e(a['titulo'])}</b><br><small>{_e(a['detalhe'])}</small>",
          _e(a["como_resolver"])] for a in graves],
        "Todos os robôs ligados rodaram e rodaram bem."))
    quadro = resumo.get("quadro") or []
    if quadro:
        partes.append("<details><summary>Os doze robôs, um por linha</summary>" + _tabela(
            ["Robô", "Missão", "Última passada", "Situação"],
            [[_e(r["nome"]), _e(r["missao"]), _e(r["ultima"] or "—"),
              _marca(r["pior"]) + (" <small>ainda não bate ponto</small>"
                                   if r["situacao"] == "SEM_PONTO" else "")]
             for r in quadro], "") + "</details>")

    # 2. Tarefas
    t = mesa.get("tarefas") or {}
    partes.append("<h2>2. As suas tarefas — por quando</h2>")
    for chave, titulo in (("VENCIDAS", "Venceram"), ("HOJE", "Vencem hoje"),
                          ("SEMANA", "Vencem nos próximos 7 dias")):
        itens = t.get(chave) or []
        partes.append(f"<h3>{titulo} ({len(itens)})</h3>")
        partes.append(_tabela(
            ["#", "Tarefa", "Prioridade", "Prazo", "Origem"],
            [[f"<a href='/tarefas/{i['id']}'>#{i['id']}</a>", _e(i["titulo"]),
              _e(i["prioridade"]), _data(i["prazo"])
              + (f" <small>({-i['dias']} dia(s) atrás)</small>" if i["dias"] is not None
                 and i["dias"] < 0 else ""), _e(i["origem"])] for i in itens],
            "Nada."))
    depois, sem = len(t.get("DEPOIS") or []), len(t.get("SEM_PRAZO") or [])
    partes.append(f"<p class='sub'>Depois desta semana: {depois} tarefa(s); sem prazo: {sem}."
                  "</p>")

    # 3. Substituto
    partes.append("<h2>3. Onde você é o substituto e o titular deixou vencer</h2>")
    partes.append(_tabela(
        ["#", "Tarefa", "Titular", "Venceu em", "Há"],
        [[f"<a href='/tarefas/{s['id']}'>#{s['id']}</a>", _e(s["titulo"]), _e(s["titular"]),
          _data(s["prazo"]), f"{s['dias_vencida']} dia(s)"]
         for s in mesa.get("substituicoes") or []],
        "Nenhuma."))

    # 4. Malote parado
    partes.append("<h2>4. Malote para cumprimento que ninguém pegou</h2>"
                  "<p class='sub'>Em «recebido», sem tarefa aberta ligada. Ordem judicial "
                  "parada é responsabilidade sua qualquer que seja o setor.</p>")
    partes.append(_tabela(
        ["Expediente", "Assunto", "Remetente", "Recebido", "Responsável"],
        [[_e(m["protocolo"]), _e(m["assunto"]), _e(m["remetente"]),
          _data(m["recebido_em"]) + (f" <small>({m['dias_parado']} dias)</small>"
                                     if m["dias_parado"] is not None else ""),
          _e(m["responsavel"])] for m in mesa.get("malote") or []],
        "Nenhum."))

    # 5. Fraude
    fraude = mesa.get("fraude") or []
    if fraude:
        partes.append("<h2>5. Malote que fala em fraude ou suspeita</h2>")
        partes.append(_tabela(
            ["Expediente", "Assunto", "Remetente", "Recebido", "Etapa"],
            [[_e(f["protocolo"]), _e(f["assunto"]), _e(f["remetente"]),
              _data(f["recebido_em"]), _e(f["etapa"])] for f in fraude], ""))

    # 6. Decisões
    decisoes = resumo.get("decisoes") or []
    partes.append(f"<h2>6. O que espera a sua decisão ({len(decisoes)})</h2>")
    for d in decisoes:
        opcoes = "".join(f"<li>{_e(o)}</li>" for o in d["opcoes"])
        partes.append(
            f"<div class='decisao'>{_marca(d['gravidade'])} <b>#{d['id']} — "
            f"{_e(d['pergunta'])}</b><pre>{_e(d['contexto'])}</pre>"
            + (f"<ul>{opcoes}</ul>" if opcoes else "")
            + (f"<p><b>Recomendo:</b> {_e(d['recomendacao'])}</p>" if d["recomendacao"] else "")
            + (f"<p><b>Enquanto isso:</b> {_e(d['o_que_espera'])}</p>" if d["o_que_espera"]
               else "") + "</div>")
    if not decisoes:
        partes.append("<p class='vazio'>Nenhuma pergunta na fila.</p>")

    # 7. Agenda
    partes.append("<h2>7. Obrigações pessoais do delegatário (próximos 60 dias)</h2>")
    partes.append(_tabela(
        ["Obrigação", "Referência", "Prazo", "Fundamento"],
        [[("⚠ " if o["alerta"] else "") + _e(o["titulo"]) + f"<br><small>{_e(o['nota'])}</small>",
          _e(o["referencia"]), _data(o["prazo"]) + f" <small>({o['faltam_dias']} dia(s))</small>",
          f"{_e(o['fundamento'])}<br><small>{_e(o['fonte'])}</small>"]
         for o in resumo.get("agenda") or []],
        "Nada com prazo nos próximos 60 dias."))

    # 8. Credenciais e certificados
    partes.append("<h2>8. O que só você pode digitar</h2>")
    cred = mesa.get("credenciais")
    if cred is None:
        partes.append("<p class='vazio'>Credenciais: não deu para medir neste modo.</p>")
    else:
        partes.append(_tabela(["Central", "Ambiente"],
                              [[_e(c["central"]), _e(c["ambiente"])] for c in cred],
                              "Todas as credenciais de produção estão informadas."))
    cert = mesa.get("certificados")
    if cert is None:
        partes.append("<p class='vazio'>Certificados digitais: não deu para medir.</p>")
    else:
        partes.append("<h3>Certificados digitais que vencem em até 60 dias</h3>" + _tabela(
            ["Certificado", "Vence", ""],
            [[_e(c["nome"]), _data(c["vence"]),
              "VENCIDO" if c["faltam_dias"] < 0 else f"em {c['faltam_dias']} dia(s)"]
             for c in cert], "Nenhum."))

    estilo = """
    :root{--fg:#101828;--bg:#fff;--mut:#475467;--lin:#eaecf0}
    @media (prefers-color-scheme: dark){:root{--fg:#f2f4f7;--bg:#0c111d;--mut:#98a2b3;--lin:#1f242f}}
    body{font:14px/1.45 system-ui,Segoe UI,sans-serif;color:var(--fg);background:var(--bg);
         max-width:1100px;margin:0 auto;padding:16px}
    h1{font-size:22px;margin:0} h2{font-size:17px;margin-top:28px;border-bottom:1px solid var(--lin)}
    h3{font-size:14px;margin:14px 0 4px} .sub,small{color:var(--mut)}
    table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid var(--lin);
         padding:5px 6px;text-align:left;vertical-align:top} th{font-size:12px;color:var(--mut)}
    .marca{color:#fff;border-radius:4px;padding:1px 6px;font-size:11px;white-space:nowrap}
    .vazio{color:var(--mut);font-style:italic} .erro{color:#b42318}
    .decisao{border:1px solid var(--lin);border-radius:6px;padding:8px 12px;margin:8px 0}
    pre{white-space:pre-wrap;font:inherit;margin:4px 0}
    """
    return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Mesa do oficial {_data(hoje)}</title><style>{estilo}</style></head>"
            "<body>" + "\n".join(partes) + "</body></html>")


# ---------------------------------------------------------------- a rodada

def rodar(con: sqlite3.Connection, hoje: date, *, agora: datetime | None = None,
          pasta_dados=None, pasta_relatorio: Path | None = None, so_ler: bool = False,
          ler_agendador=None, ler_certificados=None) -> dict:
    """A rodada inteira. Com `so_ler`, não grava nada no banco."""
    agora = agora or datetime.now()
    resumo: dict = {"hoje": hoje.isoformat(), "so_ler": so_ler, "nao_mediu": {},
                    "gerada_em": agora.isoformat(timespec="seconds")}
    iniciada = _agora()

    def parte(nome, funcao):
        try:
            return funcao()
        except Exception as erro:                       # noqa: BLE001 — vira «não mediu»
            resumo["nao_mediu"][nome] = f"{type(erro).__name__}: {erro}"
            return None

    saude = parte("saúde dos robôs", lambda: OR.saude(con, agora)) or []
    tarefas_agendador = parte("agendador", ler_agendador or OR.ler_agendador_do_windows)
    saude += OR.saude_do_agendador(tarefas_agendador or [])
    resumo["saude"] = saude
    resumo["quadro"] = parte("quadro dos robôs", lambda: OR.quadro(con, agora)) or []
    if not so_ler:
        resumo["tarefas_dos_robos"] = parte(
            "tarefas dos robôs", lambda: sincronizar_tarefas_dos_robos(con, saude, hoje))
        parte("decisões", lambda: OD.perguntar(con, **OO.pergunta_das_nao_medidas()))
    resumo["decisoes"] = parte("decisões abertas", lambda: OD.abertas(con)) or []
    resumo["agenda"] = parte("agenda", lambda: OO.agenda(hoje)) or []
    resumo["mesa"] = parte("mesa", lambda: OP.montar(
        con, hoje, pasta_dados=pasta_dados, ler_certificados=ler_certificados)) or {}
    if pasta_relatorio is not None:
        pasta_relatorio.mkdir(parents=True, exist_ok=True)
        caminho = pasta_relatorio / f"mesa_do_oficial_{hoje.isoformat()}.html"
        caminho.write_bytes(relatorio_html(resumo).encode("utf-8"))
        resumo["relatorio"] = str(caminho)
    if not so_ler:
        situacao = ("ERRO" if resumo["nao_mediu"] else
                    "AVISO" if any(a["gravidade"] == "CRITICO" for a in saude) else "OK")
        OR.bater(con, "OFICIAL", situacao=situacao, iniciada_em=iniciada,
                 resumo={"criticos": sum(a["gravidade"] == "CRITICO" for a in saude),
                         "decisoes": len(resumo["decisoes"]),
                         "relatorio": resumo.get("relatorio")},
                 erro="; ".join(f"{k}: {v}" for k, v in resumo["nao_mediu"].items()) or None)
        con.commit()
    return resumo


def rodada_diaria(banco: Path, pasta_dados: Path | None, pasta_relatorio: Path | None, *,
                  so_ler: bool = False, hoje: date | None = None, escrever=print) -> int:
    """O que o Agendador chama. Devolve o código de saída."""
    banco = Path(banco)
    if not banco.exists():
        escrever(f"ERRO: banco não encontrado em {banco}")
        return 2
    hoje = hoje or date.today()
    if so_ler:
        con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True, timeout=60)
    else:
        con = sqlite3.connect(str(banco), timeout=60)
    try:
        resumo = rodar(con, hoje, pasta_dados=pasta_dados, pasta_relatorio=pasta_relatorio,
                       so_ler=so_ler)
    except Exception:                                   # noqa: BLE001
        escrever("ERRO: a rodada do robô oficial não terminou.")
        escrever(traceback.format_exc())
        return 1
    finally:
        con.close()
    criticos = [a for a in resumo["saude"] if a["gravidade"] == "CRITICO"]
    escrever(f"  robôs com problema crítico: {len(criticos)}")
    for a in criticos:
        escrever(f"    - {a['robo_nome']}: {a['titulo']}")
    t = (resumo.get("mesa") or {}).get("tarefas") or {}
    escrever(f"  tarefas do oficial: {len(t.get('VENCIDAS') or [])} vencida(s), "
             f"{len(t.get('HOJE') or [])} hoje, {len(t.get('SEMANA') or [])} na semana")
    escrever(f"  decisões na fila: {len(resumo['decisoes'])}")
    escrever(f"  tarefas dos robôs: {resumo.get('tarefas_dos_robos')}")
    if resumo["nao_mediu"]:
        escrever(f"  NÃO MEDIU: {resumo['nao_mediu']}")
    escrever(f"  relatório: {resumo.get('relatorio')}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="O robô oficial.")
    p.add_argument("--banco", required=True)
    p.add_argument("--pasta-dados", default=None)
    p.add_argument("--pasta-relatorio", default=None)
    p.add_argument("--hoje", default=None)
    p.add_argument("--so-ler", action="store_true",
                   help="abre o banco só para ler; grava apenas o relatório")
    p.add_argument("--responder", nargs=3, metavar=("ID", "RESPOSTA", "QUEM"),
                   help="grava a resposta do oficial a uma decisão da fila")
    a = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    if a.responder:
        con = sqlite3.connect(a.banco, timeout=60)
        try:
            OD.responder(con, int(a.responder[0]), a.responder[1], a.responder[2])
            con.commit()
        except OD.DecisaoError as erro:
            print(f"ERRO: {erro}")
            return 1
        finally:
            con.close()
        print(f"Resposta gravada na decisão #{a.responder[0]}.")
        return 0
    return rodada_diaria(Path(a.banco), Path(a.pasta_dados) if a.pasta_dados else None,
                         Path(a.pasta_relatorio) if a.pasta_relatorio else None,
                         so_ler=a.so_ler,
                         hoje=date.fromisoformat(a.hoje) if a.hoje else None)


if __name__ == "__main__":
    sys.exit(main())

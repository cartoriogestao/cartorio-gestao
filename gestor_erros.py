"""O RELATÓRIO DE ERROS — quem praticou o quê, para o administrador.

Pedido do oficial em 06/10/2026: «crie um relatorio de erros, com detalhes e
quem praticou, disponivel para o administrador no painel».

DE ONDE VEM
    Dos achados da conferência diária (`ge_achados`), abertos e já resolvidos,
    só das regras que são ERRO DE QUEM PRATICOU o ato (texto com campo de
    modelo, ato sem selo, registro sem CNIB, caixa com ponto, comunicação não
    feita...). As pendências da casa (backup, IBGE, CENSEC, fechamento do mês,
    caixa esperando o visto) ficam de fora: não têm autor.
    E das revisões antes da lavratura em que alguém LAVROU CONTRA um apontamento
    GRAVE, com a justificativa escrita.

QUEM PRATICOU
    Primeiro a coluna do próprio ato (`lavrado_por`, `lancado_por`,
    `criado_por`...); vazia, a AUDITORIA (`audit_logs`) da lavratura, do
    lançamento ou da abertura. Medido em 06/10/2026: 24 dos 25 atos do RI desde
    10/09 têm `lavrado_por` VAZIO e todos os 24 têm a lavratura na auditoria —
    sem ela o relatório diria «não identificado» para quase tudo. As colunas
    guardam ora o número do usuário, ora o nome, ora o login; tudo se casa com o
    cadastro em Python (o `upper()` do SQLite não conhece acento). Cada linha diz
    COMO o autor foi achado, para o administrador pesar a atribuição.

SÓ LÊ. Não cria tarefa (as tarefas já saem da conferência) e não grava nada.
"""
from __future__ import annotations

import html
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

#: regra → categoria. Só o que tem autor; o resto da conferência não entra.
CATEGORIAS = {
    "MODELO_NAO_PREENCHIDO": "Texto do ato",
    "TEXTO_CONTRA_CADASTRO": "Texto do ato",
    "LEITURA_DO_TEXTO": "Texto do ato",
    "REVISAO_DO_AGENTE": "Texto do ato",
    "DOCUMENTO_INVALIDO": "Cadastro",
    "MINUTA_EM_FICHA_ENCERRADA": "Qualificação",
    "REGISTRO_SEM_CNIB": "Qualificação",
    # 06/10/2026, ordem do oficial («deixe apenas os fundamentais»): saíram
    # ATO_POR_FORA, REGISTRO_SEM_PRENOTACAO, SELO_CANCELADO_LOCAL, SELO_ORFAO e ATO_SEM_SELO —
    # ver gestor_conferencia.RETIRADAS_DO_ATO_LAVRADO.
    "CAIXA_COM_PONTOS": "Caixa",
    "CAIXA_ABERTO": "Caixa",
    "CAIXA_DO_DIA_ABERTO": "Caixa",
    "DIGITALIZACAO_DA_FICHA": "Prazo",
    "SIRC": "Comunicação não feita",
    "SIRC_CANCELAMENTO": "Comunicação não feita",
    "CRC": "Comunicação não feita",
    "FUNAI": "Comunicação não feita",
}
GRAVE_JUSTIFICADO = "LAVROU_CONTRA_APONTAMENTO_GRAVE"
ORDEM_DA_GRAVIDADE = {"CRITICO": 0, "VENCIDO": 1, "ATENCAO": 2, "PRAZO": 3}
TABELAS = ("ri_atos", "ri_matriculas", "ri_minutas", "nt_atos", "rc_assentos", "rc_atos",
           "ra_atos", "rc_pessoas", "cx_caixas", "sd_selos")
#: prefixo da chave → tabela, quando a chave traz só o número.
PREFIXO_DA_TABELA = {"CNIB_ATO": "ri_atos", "SEM_PRENOT": "ri_atos",
                     "MINUTA_FECHADA": "ri_minutas", "CAIXA_CONF": "cx_caixas",
                     "CAIXA_ABERTO": "cx_caixas", "CAIXA_HOJE": "cx_caixas"}
NAO_IDENTIFICADO = "não identificado"
AGENTE = "Agente (Claude)"


# ------------------------------------------------------------------ apoio

def _forma(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())


def _tem(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (nome,)).fetchone() is not None


def _linha(con, tabela: str, ident) -> dict | None:
    if tabela not in TABELAS or not _tem(con, tabela):
        return None
    cur = con.execute(f"SELECT * FROM {tabela} WHERE id = ?", (ident,))
    r = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], r)) if r else None


class _Pessoas:
    """O cadastro, para casar número, login ou nome com uma pessoa."""

    def __init__(self, con):
        self.por_id = {}
        if _tem(con, "users"):
            for i, login, nome in con.execute("SELECT id, username, full_name FROM users"):
                self.por_id[i] = (login or "", nome or login or f"usuário {i}")

    def quem(self, valor) -> str | None:
        if valor is None or str(valor).strip() == "":
            return None
        s = str(valor).strip()
        if s.isdigit():
            p = self.por_id.get(int(s))
            return p[1] if p else f"usuário nº {s}"
        f = _forma(s)
        if "CLAUDE" in f or f.startswith("AGENTE"):
            return AGENTE
        for login, nome in self.por_id.values():
            if _forma(login) == f:
                return nome
        casam = [nome for _, nome in self.por_id.values() if _forma(nome).startswith(f)]
        return casam[0] if len(casam) == 1 else s


def _auditoria(con, pessoas: _Pessoas, entidade: str, ident, acoes: tuple[str, ...],
               ultima=False) -> str | None:
    if not _tem(con, "audit_logs"):
        return None
    for acao in acoes:
        r = con.execute(
            f"""SELECT user_id, username_snapshot FROM audit_logs
                 WHERE entity_type = ? AND entity_id = ? AND action LIKE ?
              ORDER BY id {'DESC' if ultima else 'ASC'} LIMIT 1""",
            (entidade, str(ident), acao)).fetchone()
        if r:
            return pessoas.quem(r[0]) or pessoas.quem(r[1])
    return None


# ------------------------------------------------------------------ o alvo e o autor

def _ato_da_revisao(con, rv_id) -> tuple[str, int] | None:
    if not _tem(con, "rv_revisoes"):
        return None
    r = con.execute("SELECT atribuicao, alvo_id, hash_texto FROM rv_revisoes WHERE id = ?",
                    (rv_id,)).fetchone()
    if not r:
        return None
    if r[0] == "NOTAS":
        return "nt_atos", r[1]
    if r[0] == "LIVRO3":
        return "ra_atos", r[1]
    import revisao_previa as RV
    for aid, tipo, teor in con.execute(
            "SELECT id, tipo, teor FROM ri_atos WHERE matricula_id = ? ORDER BY id DESC", (r[1],)):
        if RV.hash_do_ato(tipo, teor) == r[2]:
            return "ri_atos", aid
    return "ri_matriculas", r[1]           # a revisão ANTES da lavratura: o ato ainda não existia


def alvo(con, chave: str) -> tuple[str, int] | None:
    """A tabela e o registro de que o achado fala, lidos da chave."""
    p = str(chave or "").split(":")
    if len(p) >= 3 and p[1] in TABELAS and p[2].isdigit():
        return p[1], int(p[2])
    if len(p) >= 2 and p[0] in PREFIXO_DA_TABELA and p[1].isdigit():
        return PREFIXO_DA_TABELA[p[0]], int(p[1])
    if p[0] == "SELO_ORFAO" and len(p) >= 4 and p[1] == "ato" and p[3].isdigit():
        return p[2], int(p[3])
    if p[0] in ("SELO_LOCAL", "SELO_ORFAO") and _tem(con, "sd_selos"):
        r = con.execute("SELECT id FROM sd_selos WHERE numero = ?", (p[-1],)).fetchone()
        return ("sd_selos", r[0]) if r else None
    if p[0] == "DIGI" and len(p) >= 2 and p[1].isdigit():
        # Quem lavrou o ÚLTIMO ato da ficha é quem deixou de digitalizar depois dele.
        r = con.execute("""SELECT id FROM ri_atos WHERE matricula_id = ?
                              AND COALESCE(acervo,0) = 0 ORDER BY numero DESC, id DESC LIMIT 1""",
                        (int(p[1]),)).fetchone()
        return ("ri_atos", r[0]) if r else ("ri_matriculas", int(p[1]))
    if p[0] == "REV_AGENTE" and len(p) >= 2 and p[1].isdigit():
        return _ato_da_revisao(con, int(p[1]))
    return None


def autor(con, pessoas: _Pessoas, tabela: str, ident) -> tuple[str, str]:
    """(quem, como se soube). Nunca adivinha: sem fonte, «não identificado»."""
    a = _linha(con, tabela, ident) or {}
    if tabela == "rc_pessoas" and a.get("assento_id"):
        return autor(con, pessoas, "rc_assentos", a["assento_id"])
    if tabela == "cx_caixas":
        quem = pessoas.quem(a.get("operador_nome")) or pessoas.quem(a.get("operador_id"))
        return (quem, "dono do caixa") if quem else (NAO_IDENTIFICADO, "")
    if tabela == "sd_selos":
        if a.get("cancelado_por"):
            return pessoas.quem(a["cancelado_por"]), "cancelou o selo"
        q = pessoas.quem(a.get("obtido_por"))
        return (q, "gerou o selo") if q else (NAO_IDENTIFICADO, "")
    caminhos = {
        "ri_atos": [("col", "lavrado_por", "lavrou"),
                    ("aud", "RI_ATO", ("RI_ATO_LAVRADO%",), False, "lavrou (pela auditoria)")],
        "ri_matriculas": [("aud", "RI_MATRICULA", ("RI_MATRICULA_ABERTA",), False,
                           "abriu a matrícula (pela auditoria)"),
                          ("col", "criado_por", "cadastrou a matrícula")],
        "ri_minutas": [("col", "atualizado_por", "alterou a minuta por último"),
                       ("col", "criado_por", "escreveu a minuta")],
        "nt_atos": [("col", "lancado_por", "lançou no livro"),
                    ("aud", "NT_ATO", ("NT_ATO_LANCADO",), False, "lançou (pela auditoria)"),
                    ("aud", "NT_ATO", ("NT_ATO_TEOR", "NT_ATO_PREENCHIDO"), True,
                     "redigiu o texto por último (pela auditoria)"),
                    ("col", "criado_por", "abriu o ato"),
                    ("aud", "NT_ATO", ("NT_ATO_ABERTO",), False, "abriu o ato (pela auditoria)")],
        "rc_assentos": [("col", "criado_por", "registrou"),
                        ("aud", "rc_assentos", ("RCPN_ASSENTO_NOVO",), False,
                         "registrou (pela auditoria)")],
        "rc_atos": [("col", "criado_por", "praticou"),
                    ("aud", "rc_atos", ("RCPN_ATO%", "RCPN_AVERBAR%"), False,
                     "praticou (pela auditoria)")],
        "ra_atos": [("col", "criado_por", "praticou"),
                    ("aud", "ra_atos", ("RA_ATO",), False, "praticou (pela auditoria)")],
    }
    for passo in caminhos.get(tabela, []):
        if passo[0] == "col":
            q = pessoas.quem(a.get(passo[1]))
            if q:
                return q, passo[2]
        else:
            q = _auditoria(con, pessoas, passo[1], ident, passo[2], ultima=passo[3])
            if q:
                return q, passo[4]
    return NAO_IDENTIFICADO, ""


def descrever(con, tabela: str, ident) -> tuple[str, str | None]:
    """(rótulo do ato, link no sistema)."""
    a = _linha(con, tabela, ident) or {}
    if tabela == "ri_atos" and a:
        m = _linha(con, "ri_matriculas", a.get("matricula_id")) or {}
        return (f"{a.get('tipo')}-{a.get('numero')} da matrícula {m.get('numero', '?')}",
                f"/registro-imoveis/{a.get('matricula_id')}")
    if tabela == "ri_matriculas" and a:
        return f"Matrícula {a.get('numero')}", f"/registro-imoveis/{ident}"
    if tabela == "ri_minutas" and a:
        m = _linha(con, "ri_matriculas", a.get("matricula_id")) or {}
        return (f"Minuta {a.get('tipo') or ''}-{a.get('numero_pretendido') or '?'} da matrícula "
                f"{m.get('numero', '?')}", f"/registro-imoveis/{a.get('matricula_id')}")
    if tabela == "nt_atos" and a:
        return (f"{(a.get('tipo') or 'Ato').capitalize()} nº {a.get('numero_ordem') or ident}"
                f" (livro {a.get('livro') or '?'}, fl. {a.get('folha') or '?'})",
                f"/notas/atos/{ident}")
    if tabela == "rc_assentos" and a:
        return (f"{(a.get('especie') or 'Assento').capitalize()} nº {a.get('numero') or ident}"
                f" — {a.get('nome') or ''}".rstrip(" —"), f"/rcpn/{ident}")
    if tabela == "rc_pessoas" and a:
        rot, link = descrever(con, "rc_assentos", a.get("assento_id"))
        return f"{a.get('nome') or 'Pessoa'} em {rot}", link
    if tabela == "rc_atos" and a:
        rot, link = descrever(con, "rc_assentos", a.get("assento_id"))
        return f"{a.get('rotulo') or a.get('tipo') or 'Ato'} em {rot}", link
    if tabela == "ra_atos" and a:
        return f"Livro 3, {a.get('tipo') or 'ato'} nº {a.get('numero') or ident}", None
    if tabela == "cx_caixas" and a:
        d = str(a.get("data") or "")
        return f"Caixa de {d[8:10]}/{d[5:7]}/{d[:4]}", None
    if tabela == "sd_selos" and a:
        return f"Selo {a.get('numero')}", None
    return f"{tabela} nº {ident}", None


# ------------------------------------------------------------------ o relatório

def relatorio(con, *, desde: str = "2026-09-10", ate: str | None = None,
              pessoa: str | None = None, situacao: str = "todos",
              categoria: str | None = None) -> dict:
    """As linhas do relatório e o resumo por pessoa. `situacao`: abertos,
    resolvidos ou todos."""
    pessoas = _Pessoas(con)
    linhas: list[dict] = []
    if _tem(con, "ge_achados"):
        marcas = ",".join("?" * len(CATEGORIAS))
        for (ident, chave, regra, grav, titulo, detalhe, visto, ultimo, resolvido,
             revisao) in con.execute(
                f"""SELECT id, chave, regra, gravidade, titulo, detalhe, primeiro_visto_em,
                           ultimo_visto_em, resolvido_em, revisao
                      FROM ge_achados WHERE regra IN ({marcas})
                  ORDER BY primeiro_visto_em DESC, id DESC""", tuple(CATEGORIAS)):
            alv = alvo(con, chave)
            quem, como = autor(con, pessoas, *alv) if alv else (NAO_IDENTIFICADO, "")
            rotulo, link = descrever(con, *alv) if alv else (chave, None)
            linhas.append({
                "id": ident, "chave": chave, "regra": regra, "categoria": CATEGORIAS[regra],
                "gravidade": grav or "ATENCAO", "titulo": titulo, "detalhe": detalhe or "",
                "visto_em": visto or "", "ultimo_em": ultimo or "", "resolvido_em": resolvido,
                "revisao": revisao, "ato": rotulo, "link": link, "quem": quem, "como": como})
    if _tem(con, "rv_revisoes"):
        for (ident, rot, graves, justif, por, em, resultado) in con.execute(
                """SELECT id, rotulo, graves, justificativa, justificado_por, justificado_em,
                          resultado_json FROM rv_revisoes
                    WHERE justificado_em IS NOT NULL ORDER BY justificado_em DESC"""):
            linhas.append({
                "id": f"rv{ident}", "chave": f"RV:{ident}", "regra": GRAVE_JUSTIFICADO,
                "categoria": "Lavrou contra apontamento grave", "gravidade": "ATENCAO",
                "titulo": f"Lavrado com {graves or 1} apontamento(s) GRAVE(S) da revisão",
                "detalhe": f"Justificativa: {justif or '—'}\n\nApontamentos: {_graves(resultado)}",
                "visto_em": em or "", "ultimo_em": em or "", "resolvido_em": em,
                "revisao": None, "ato": rot or f"revisão {ident}", "link": None,
                "quem": pessoas.quem(por) or NAO_IDENTIFICADO, "como": "escreveu a justificativa"})
    todas = linhas

    def vale(l):
        if (l["visto_em"] or "")[:10] < desde:
            return False
        if ate and (l["visto_em"] or "")[:10] > ate:
            return False
        if pessoa and l["quem"] != pessoa:
            return False
        if categoria and l["categoria"] != categoria:
            return False
        aberto = l["resolvido_em"] is None
        return situacao == "todos" or (situacao == "abertos") == aberto
    linhas = sorted((l for l in todas if vale(l)),
                    key=lambda l: (l["resolvido_em"] is not None,
                                   ORDEM_DA_GRAVIDADE.get(l["gravidade"], 9),
                                   l["visto_em"]), reverse=False)
    por_pessoa: dict[str, dict] = {}
    for l in linhas:
        p = por_pessoa.setdefault(l["quem"], {"quem": l["quem"], "total": 0, "abertos": 0,
                                              "criticos": 0, "categorias": {}})
        p["total"] += 1
        p["abertos"] += l["resolvido_em"] is None
        p["criticos"] += l["gravidade"] in ("CRITICO", "VENCIDO") and l["resolvido_em"] is None
        p["categorias"][l["categoria"]] = p["categorias"].get(l["categoria"], 0) + 1
    resumo = sorted(por_pessoa.values(),
                    key=lambda p: (p["quem"] == NAO_IDENTIFICADO, -p["abertos"], -p["total"]))
    return {"linhas": linhas, "por_pessoa": resumo,
            "pessoas": sorted({l["quem"] for l in todas}),
            "categorias": sorted({l["categoria"] for l in todas}),
            "abertos": sum(l["resolvido_em"] is None for l in linhas)}


def _graves(resultado_json) -> str:
    import json
    try:
        achados = json.loads(resultado_json or "{}").get("achados") or []
    except (ValueError, AttributeError):
        return "—"
    graves = [a.get("o_que") or "" for a in achados if str(a.get("gravidade")).upper() == "GRAVE"]
    return "; ".join(g for g in graves if g) or "—"


# ------------------------------------------------------------------ o arquivo (produção sem pacote)

def escrever_html(con, hoje: date, pasta: Path) -> Path:
    """O mesmo relatório em arquivo, para a conferência diária deixar na pasta
    de relatórios enquanto a tela não chega pelo pacote."""
    r = relatorio(con)
    e = html.escape
    resumo = "".join(
        f"<tr><td>{e(p['quem'])}</td><td>{p['abertos']}</td><td>{p['criticos']}</td>"
        f"<td>{p['total']}</td><td>{e(', '.join(f'{k}: {v}' for k, v in sorted(p['categorias'].items())))}</td></tr>"
        for p in r["por_pessoa"])
    corpo = "".join(
        f"<tr class='{'' if l['resolvido_em'] else 'aberto'}'><td>{e(l['visto_em'][:10])}</td>"
        f"<td>{e(l['gravidade'])}</td><td>{e(l['categoria'])}</td><td>{e(l['quem'])}"
        f"<br><small>{e(l['como'])}</small></td><td>{e(l['ato'])}</td>"
        f"<td><b>{e(l['titulo'] or '')}</b><br><small>{e(l['detalhe'][:600])}</small></td>"
        f"<td>{'resolvido em ' + e(str(l['resolvido_em'])[:10]) if l['resolvido_em'] else 'ABERTO'}</td></tr>"
        for l in r["linhas"])
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"erros_{hoje.isoformat()}.html"
    caminho.write_text(f"""<!doctype html><meta charset="utf-8"><title>Relatório de erros</title>
<style>body{{font:14px system-ui;margin:16px;background:#fff;color:#222}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:4px 6px;vertical-align:top;text-align:left}}tr.aberto td{{background:#fff4f4}}
small{{color:#555;white-space:pre-wrap}}</style>
<h1>Relatório de erros — {hoje.strftime('%d/%m/%Y')}</h1>
<p>Desde 10/09/2026. {r['abertos']} aberto(s) de {len(r['linhas'])}. Quem praticou: coluna do ato ou, vazia, a auditoria.</p>
<h2>Por pessoa</h2><table><tr><th>Quem</th><th>Abertos</th><th>Críticos abertos</th><th>Total</th><th>Por tipo</th></tr>{resumo}</table>
<h2>Erros</h2><table><tr><th>Visto em</th><th>Gravidade</th><th>Tipo</th><th>Quem praticou</th><th>Ato</th><th>O que é</th><th>Situação</th></tr>{corpo}</table>
""", encoding="utf-8")
    return caminho

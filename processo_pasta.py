"""A PASTA DO PROCESSO — fase 1 do módulo único de Processos (12/10/2026).

    «abri uma tarefa da vanessa, de averbacao de um divorcio, ainda que bem
     explicada a tarefa eh insuficiente. nao tem os docs necessarios e nao tem
     onde procurar. precisamos unir o modulo de tarefas e de expedientes para
     ser um unico modulo de Processos»               — o oficial, 12/10/2026

O processo (por ora, a tarefa crescida — ver
`DOCUMENTACAO/PROCESSOS_O_MODELO_UNICO.md`) APONTA para as peças do sistema: o
expediente do malote, o assento, a matrícula, a prenotação, o protocolo geral,
o ato das Notas, o registro do RTD/RCPJ, o rascunho. Não copia nenhuma delas:
o ato continua no seu livro, com o seu número e o seu selo.

E A PASTA JUNTA OS DOCUMENTOS DE TODAS ELAS NUMA LISTA SÓ. Medido na tarefa
#318: o mandado estava no expediente (anexo 16), o assento existia (id 1689),
e a tela da tarefa não mostrava nem um nem outro. Cada tela só via os seus
anexos — `attachments` guarda por entidade, e ninguém juntava.

Este módulo não lavra, não sela, não cobra e não muda ato nenhum. Escreve
apenas o vínculo (`pr_vinculos`).
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_vinculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    tabela TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(task_id, tabela, item_id)
);
CREATE INDEX IF NOT EXISTS ix_pr_vinculos_item ON pr_vinculos(tabela, item_id);
"""


class PastaError(ValueError):
    """Recusa com mensagem pronta para o balcão."""


# O QUE PODE ENTRAR NA PASTA. `anexos` é o entity_type de `attachments` daquela
# peça (medido em 12/10/2026: EXPEDIENTE 44, RI_PROTOCOLO 61, NT_ATO 36,
# RG_REGISTRO 5, rc_assento 5); `endpoint` e `arg` montam o link da ficha.
TIPOS: dict[str, dict[str, Any]] = {
    "expedientes": {"nome": "Expediente (malote)", "endpoint": "expediente_detail",
                    "arg": "expediente_id", "anexos": ("EXPEDIENTE",),
                    "ajuda": "o número EXP-2026-000012"},
    "rc_assentos": {"nome": "Assento do Registro Civil", "endpoint": "rcpn_assento",
                    "arg": "assento_id", "anexos": ("rc_assento",),
                    "ajuda": "a matrícula de 32 dígitos (com ou sem espaços)"},
    "ri_matriculas": {"nome": "Matrícula do RI", "endpoint": "ri_ficha",
                      "arg": "matricula_id", "anexos": (),
                      "ajuda": "o número da matrícula"},
    "ri_protocolos": {"nome": "Prenotação do RI", "endpoint": "ri_protocolo_ver",
                      "arg": "protocolo_id", "anexos": ("RI_PROTOCOLO",),
                      "ajuda": "o número da prenotação"},
    "cx_protocolos": {"nome": "Protocolo geral do balcão", "endpoint": "caixa_protocolo",
                      "arg": "protocolo_id", "anexos": (),
                      "ajuda": "o número 2026.10.31"},
    "nt_atos": {"nome": "Ato das Notas", "endpoint": "notas_ato", "arg": "ato_id",
                "anexos": ("NT_ATO",), "ajuda": "o número interno do ato (o da tela do ato)"},
    "rg_registros": {"nome": "Registro do RTD/RCPJ", "endpoint": "rcpj_rtd_registro",
                     "arg": "registro_id", "anexos": ("RG_REGISTRO",),
                     "ajuda": "o número interno do registro (o da tela do registro)"},
    "rg_titulos": {"nome": "Título apresentado no RTD/RCPJ", "endpoint": "rcpj_rtd_titulo",
                   "arg": "titulo_id", "anexos": ("RG_TITULO",),
                   "ajuda": "o número interno do título (o da tela do título)"},
    "rascunhos_de_tela": {"nome": "Rascunho de ato", "endpoint": None, "arg": "rascunho_id",
                          "anexos": (), "ajuda": "o número do rascunho"},
}


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _digitos(texto: Any) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def resolver(con: sqlite3.Connection, tabela: str, referencia: str) -> int:
    """Do que o escrevente digitou ao id da peça. Recusa o que não acha."""
    if tabela not in TIPOS:
        raise PastaError("Esse tipo de peça não pode entrar na pasta do processo.")
    ref = (referencia or "").strip()
    if not ref:
        raise PastaError(f"Informe {TIPOS[tabela]['ajuda']}.")
    d = _digitos(ref)
    linha = None
    if tabela == "expedientes":
        linha = con.execute("SELECT id FROM expedientes WHERE internal_protocol=?",
                            (ref.upper(),)).fetchone()
        if not linha and d and ref.isdigit():
            linha = con.execute("SELECT id FROM expedientes WHERE id=?", (int(d),)).fetchone()
    elif tabela == "rc_assentos":
        if len(d) == 32:
            linha = con.execute("SELECT id FROM rc_assentos WHERE matricula=?", (d,)).fetchone()
        elif d and ref.isdigit():
            linha = con.execute("SELECT id FROM rc_assentos WHERE id=?", (int(d),)).fetchone()
    elif tabela == "ri_matriculas":
        achadas = con.execute("SELECT id FROM ri_matriculas WHERE numero=?", (ref,)).fetchall()
        if not achadas and d:
            achadas = con.execute("SELECT id FROM ri_matriculas WHERE numero=?", (d,)).fetchall()
        if len(achadas) > 1:
            raise PastaError(f"Há {len(achadas)} fichas com o número {ref}; abra a ficha e "
                             "vincule pelo número interno.")
        linha = achadas[0] if achadas else None
    elif tabela == "ri_protocolos":
        if d:
            linha = con.execute("SELECT id FROM ri_protocolos WHERE numero=?", (int(d),)).fetchone()
    elif tabela == "cx_protocolos":
        linha = con.execute("SELECT id FROM cx_protocolos WHERE numero=?", (ref,)).fetchone()
    elif d and ref.isdigit():
        linha = con.execute(f"SELECT id FROM {tabela} WHERE id=?", (int(d),)).fetchone()
    if not linha:
        raise PastaError(f"Não achei {TIPOS[tabela]['nome'].lower()} com «{ref}». "
                         f"Informe {TIPOS[tabela]['ajuda']}.")
    return int(linha[0])


def vincular(con: sqlite3.Connection, task_id: int, tabela: str, referencia: str, *,
             agora: str, por: int | None) -> int:
    """Põe a peça na pasta do processo. ESCREVE só o vínculo."""
    init_schema(con)
    if not con.execute("SELECT 1 FROM tasks WHERE id=?", (int(task_id),)).fetchone():
        raise PastaError(f"Não achei o processo #{task_id}.")
    item = resolver(con, tabela, referencia)
    if tabela == "expedientes" and con.execute(
            "SELECT 1 FROM tasks WHERE id=? AND linked_expediente_id=?", (int(task_id), item)).fetchone():
        raise PastaError("Este expediente já é a origem do processo; ele já está na pasta.")
    if con.execute("SELECT 1 FROM pr_vinculos WHERE task_id=? AND tabela=? AND item_id=?",
                   (int(task_id), tabela, item)).fetchone():
        raise PastaError("Esta peça já está na pasta do processo.")
    con.execute("INSERT INTO pr_vinculos(task_id, tabela, item_id, criado_em, criado_por) "
                "VALUES (?,?,?,?,?)", (int(task_id), tabela, item, agora, por))
    con.execute("INSERT INTO task_history(task_id, ts, user_id, action, note) VALUES (?,?,?,?,?)",
                (int(task_id), agora, por, "NOTA",
                 f"Na pasta do processo: {TIPOS[tabela]['nome'].lower()} {rotulo(con, tabela, item)}."))
    return item


def desvincular(con: sqlite3.Connection, task_id: int, vinculo_id: int, *, agora: str,
                por: int | None) -> None:
    """Tira a peça da pasta. A peça continua onde sempre esteve."""
    init_schema(con)
    v = con.execute("SELECT tabela, item_id FROM pr_vinculos WHERE id=? AND task_id=?",
                    (int(vinculo_id), int(task_id))).fetchone()
    if not v:
        raise PastaError("Este vínculo não é deste processo.")
    con.execute("DELETE FROM pr_vinculos WHERE id=?", (int(vinculo_id),))
    con.execute("INSERT INTO task_history(task_id, ts, user_id, action, note) VALUES (?,?,?,?,?)",
                (int(task_id), agora, por, "NOTA",
                 f"Saiu da pasta do processo: {TIPOS[v[0]]['nome'].lower()} {rotulo(con, v[0], v[1])}."))


def ato_lavrado_do_rascunho(con: sqlite3.Connection, task_id: int, vinculo_id: int, *,
                            apagar_rascunho: bool, agora: str, por: int | None) -> None:
    """O ato do rascunho foi lavrado: o processo conclui, com a nota. ESCREVE.

    O sistema não tem como saber sozinho que o ato saiu do rascunho — as treze
    telas de ato não carregam o número do rascunho até a lavratura. Por isso é
    quem lavrou que diz, aqui, numa ação só."""
    init_schema(con)
    v = con.execute("SELECT tabela, item_id FROM pr_vinculos WHERE id=? AND task_id=?",
                    (int(vinculo_id), int(task_id))).fetchone()
    if not v or v[0] != "rascunhos_de_tela":
        raise PastaError("Este vínculo não é um rascunho deste processo.")
    if apagar_rascunho:
        con.execute("DELETE FROM rascunhos_de_tela WHERE id=?", (int(v[1]),))
    con.execute("UPDATE tasks SET status='CONCLUIDA', completed_at=?, completed_by=?, updated_at=? WHERE id=?",
                (agora, por, agora, int(task_id)))
    con.execute("INSERT INTO task_history(task_id, ts, user_id, action, old_value, new_value, note) "
                "VALUES (?,?,?,?,?,?,?)",
                (int(task_id), agora, por, "ALTEROU_STATUS", None, "CONCLUIDA",
                 "O ato do rascunho foi lavrado." + (" Rascunho apagado." if apagar_rascunho else "")))


def rotulo(con: sqlite3.Connection, tabela: str, item_id: int) -> str:
    """Como a peça se chama para quem lê."""
    q = {
        "expedientes": "SELECT internal_protocol, subject FROM expedientes WHERE id=?",
        "rc_assentos": "SELECT especie, numero, livro_volume, nome FROM rc_assentos WHERE id=?",
        "ri_matriculas": "SELECT numero, livro FROM ri_matriculas WHERE id=?",
        "ri_protocolos": "SELECT numero, natureza_titulo FROM ri_protocolos WHERE id=?",
        "cx_protocolos": "SELECT numero, interessado FROM cx_protocolos WHERE id=?",
        "nt_atos": "SELECT tipo, livro, folha FROM nt_atos WHERE id=?",
        "rg_registros": "SELECT atribuicao, numero, volume FROM rg_registros WHERE id=?",
        "rascunhos_de_tela": "SELECT titulo, tela FROM rascunhos_de_tela WHERE id=?",
        "rg_titulos": "SELECT numero, natureza, apresentante FROM rg_titulos WHERE id=?",
    }[tabela]
    r = con.execute(q, (int(item_id),)).fetchone()
    if not r:
        return f"#{item_id} (não existe mais)"
    if tabela == "expedientes":
        return f"{r[0]} — {r[1] or ''}"
    if tabela == "rc_assentos":
        livro = f", livro {r[2]}" if r[2] else ""
        return f"{(r[0] or '').lower()} nº {r[1]}{livro} — {r[3] or ''}".strip(" —")
    if tabela == "ri_matriculas":
        return f"nº {r[0]}" + (f" (livro {r[1]})" if r[1] else "")
    if tabela == "ri_protocolos":
        return f"nº {r[0]}" + (f" — {r[1]}" if r[1] else "")
    if tabela == "cx_protocolos":
        return f"{r[0]}" + (f" — {r[1]}" if r[1] else "")
    if tabela == "nt_atos":
        return f"{r[0] or 'ato'} — livro {r[1] or '?'}, fl. {r[2] or '?'}"
    if tabela == "rg_registros":
        return f"{r[0]} nº {r[1]}" + (f", livro {r[2]}" if r[2] else "")
    if tabela == "rg_titulos":
        return f"protocolo nº {r[0] or '?'} — {r[1] or ''}" + (f", de {r[2]}" if r[2] else "")
    return f"#{item_id} — {r[0]}"


def vinculos(con: sqlite3.Connection, task_id: int) -> list[dict]:
    """As peças da pasta: a origem (o expediente de onde o processo nasceu) e
    as vinculadas à mão. Cada uma com o que precisa para virar link."""
    init_schema(con)
    saida = []
    origem = con.execute("SELECT linked_expediente_id FROM tasks WHERE id=?", (int(task_id),)).fetchone()
    if origem and origem[0]:
        saida.append({"id": None, "tabela": "expedientes", "item_id": int(origem[0]), "origem": True})
    for vid, tab, item in con.execute(
            "SELECT id, tabela, item_id FROM pr_vinculos WHERE task_id=? ORDER BY id", (int(task_id),)):
        saida.append({"id": vid, "tabela": tab, "item_id": int(item), "origem": False})
    for v in saida:
        t = TIPOS[v["tabela"]]
        v["nome"] = t["nome"]
        v["rotulo"] = rotulo(con, v["tabela"], v["item_id"])
        v["endpoint"], v["arg"] = t["endpoint"], t["arg"]
        if v["tabela"] == "rascunhos_de_tela":
            r = con.execute("SELECT tela FROM rascunhos_de_tela WHERE id=?", (v["item_id"],)).fetchone()
            v["endpoint"] = r[0] if r else None
        if v["tabela"] == "ri_protocolos":
            v["etapa"] = etapa_do_ri(con, v["item_id"])
    return saida


def etapa_do_ri(con: sqlite3.Connection, protocolo_id: int) -> str | None:
    """A etapa da prenotação, calculada pela régua do agente do RI
    (`ri_pedidos.etapa`) — uma régua só para o mesmo fato. Sem a tabela das
    qualificações (instalação antiga), devolve None em vez de inventar."""
    try:
        from datetime import date

        import ri_pedidos as RIP
        con.row_factory = sqlite3.Row
        p = con.execute("SELECT * FROM ri_protocolos WHERE id=?", (int(protocolo_id),)).fetchone()
        if not p:
            return None
        quals = RIP.qualificacoes_de(con, protocolo_id)
        codigo = RIP.etapa(p, quals[-1] if quals else None, date.today().isoformat())
        return dict((c, nome) for c, nome, _ in RIP.ETAPAS).get(codigo, codigo)
    except (ImportError, sqlite3.Error):
        return None


def documentos(con: sqlite3.Connection, task_id: int) -> list[dict]:
    """Todos os documentos da pasta, de onde quer que estejam guardados: os do
    processo e os de cada peça vinculada. Só lê."""
    grupos = [("TASK", int(task_id), "anexado ao processo")]
    for v in vinculos(con, task_id):
        for ent in TIPOS[v["tabela"]]["anexos"]:
            grupos.append((ent, v["item_id"], f"{v['nome'].lower()} {v['rotulo']}"))
    saida, vistos = [], set()
    for ent, eid, de_onde in grupos:
        for a in con.execute("SELECT id, original_name, size_bytes, uploaded_at FROM attachments "
                             "WHERE entity_type=? AND entity_id=? ORDER BY id", (ent, eid)):
            if a[0] in vistos:
                continue
            vistos.add(a[0])
            saida.append({"id": a[0], "nome": a[1], "tamanho": a[2], "em": a[3], "de_onde": de_onde})
    return saida

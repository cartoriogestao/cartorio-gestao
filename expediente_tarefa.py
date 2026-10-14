"""O expediente e a tarefa: encerrar um, e saber o que sobrou do outro.

O RELATO #24 DO OFICIAL, e ele tem três partes:

    «nao tem botao para encerrar expediente. encerrei a tarefa e o expediente
     segue ativo. Melhorar a integração da tarefa e do expediente, permitir
     encerrar o segundo, e melhorar a utilidade da ferramenta. Se aparece em
     tarefa, nao precisa aparecer em expediente. Acho que os expedientes podem
     ficar restritos aos procedimentos abertos, como escrituras em rascunho,
     procedimentos de georreferenciamento, usucapiao e etc.»

O QUE SE MEDIU EM 29/08/2026
    **13 expedientes, todos em `RECEBIDO`, nenhum com data de conclusão.** E
    das 84 tarefas, **5 apontam para expediente** — uma para cada, e o
    expediente **6** está com a sua tarefa **CONCLUÍDA** e ele ainda aberto. É
    exatamente o caso que ele descreveu.

    E havia como encerrar: `update_expediente_stage` grava `completed_at`
    quando a etapa vira `RESPONDIDO` ou `ARQUIVADO`. O que não havia era
    **botão** — a tela oferece uma caixa com sete nomes de etapa e um
    «Atualizar etapa». Quem procura «encerrar» não acha «ARQUIVADO» numa lista.

POR QUE NÃO SE FECHA O EXPEDIENTE SOZINHO
    Hoje é **uma tarefa por expediente**, e seria fácil fechar o expediente
    quando a tarefa fecha. Mas o esquema permite várias (`linked_expediente_id`
    não é único), e «uma regularidade forte dentro de uma casa parece lei até
    alguém contar as exceções» — esta casa já pagou por isso na letra da
    posição 566 do Protesto.

    Então a regra é a que vale nos dois casos: ao concluir a tarefa, o sistema
    **diz o que sobrou** do expediente e oferece o encerramento ali mesmo. Com
    uma tarefa, é um clique a mais; com três, é o que impede fechar expediente
    com trabalho pendente.

O QUE ESTE MÓDULO NÃO DECIDE
    A terceira parte do relato — «os expedientes podem ficar restritos aos
    procedimentos abertos» — **muda o que o módulo é**, e não é defeito: é
    desenho. Fica como pergunta ao oficial, e não como código escrito por mim.
"""
from __future__ import annotations

import sqlite3

# As duas etapas em que `update_expediente_stage` grava `completed_at` — e por
# isso as duas em que o expediente esta, de fato, encerrado.
ETAPAS_QUE_ENCERRAM = ("RESPONDIDO", "ARQUIVADO")

# O que cada uma quer dizer, para quem clica saber o que esta declarando. Sao
# coisas diferentes, e a diferenca aparece na correicao: `RESPONDIDO` e o
# expediente que teve resposta; `ARQUIVADO` e o que se guardou sem responder.
COMO_ENCERRAR: dict[str, str] = {
    "RESPONDIDO": "Respondido — saiu resposta, e a referência dela fica anotada",
    "ARQUIVADO": "Arquivado — encerrado sem resposta a expedir",
}


class ExpedienteError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def esta_encerrado(stage) -> bool:
    return str(stage or "").upper() in ETAPAS_QUE_ENCERRAM


def tarefas_do_expediente(con: sqlite3.Connection,
                          expediente_id: int) -> dict:
    """Quantas tarefas aquele expediente tem, e quantas ainda estao abertas.

    Devolve `{total, abertas, concluidas, titulos_abertos}`. So LE.

    `CANCELADA` NAO CONTA COMO ABERTA nem como concluida: tarefa cancelada e
    trabalho que se decidiu nao fazer, e ela nao pode segurar o expediente.
    """
    con.row_factory = sqlite3.Row
    linhas = [dict(r) for r in con.execute(
        """SELECT id, title, status FROM tasks
            WHERE linked_expediente_id = ? ORDER BY id""",
        (int(expediente_id),))]
    abertas = [x for x in linhas
               if str(x["status"] or "").upper() not in ("CONCLUIDA", "CANCELADA")]
    return {
        "total": len(linhas),
        "abertas": len(abertas),
        "concluidas": len([x for x in linhas
                           if str(x["status"] or "").upper() == "CONCLUIDA"]),
        "titulos_abertos": [x["title"] for x in abertas],
    }


def o_que_falta_para_encerrar(con: sqlite3.Connection,
                              expediente_id: int) -> dict:
    """O expediente pode ser encerrado? E, se nao, por que nao.

    Devolve `{pode, ja_encerrado, stage, tarefas, recado}`. So LE, e **nao
    recusa nada**: quem decide encerrar com tarefa aberta e o oficial. Isto e
    aviso, e nao trava — a mesma regra da lista de atencao para fraudes.
    """
    con.row_factory = sqlite3.Row
    e = con.execute("SELECT id, internal_protocol, subject, stage FROM expedientes "
                    "WHERE id = ?", (int(expediente_id),)).fetchone()
    if not e:
        raise ExpedienteError(f"Não achei o expediente {expediente_id}.")
    tarefas = tarefas_do_expediente(con, expediente_id)
    ja = esta_encerrado(e["stage"])
    if ja:
        recado = f"Este expediente já está {e['stage'].lower()}."
    elif tarefas["abertas"]:
        quantas = tarefas["abertas"]
        recado = (
            f"Ainda há {quantas} tarefa{'s' if quantas > 1 else ''} aberta"
            f"{'s' if quantas > 1 else ''} neste expediente: "
            + "; ".join(tarefas["titulos_abertos"][:3])
            + ("…" if quantas > 3 else "")
            + ". Encerrar agora deixa esse trabalho sem quem cobre.")
    elif tarefas["total"]:
        recado = ("Todas as tarefas deste expediente estão concluídas — "
                  "ele pode ser encerrado.")
    else:
        recado = ("Este expediente não tem tarefa nenhuma ligada a ele.")
    return {"pode": not ja, "ja_encerrado": ja, "stage": e["stage"],
            "expediente": dict(e), "tarefas": tarefas, "recado": recado}


def recado_da_tarefa_concluida(con: sqlite3.Connection, task_id: int) -> dict | None:
    """Ao concluir a tarefa, o que dizer sobre o expediente dela.

    Devolve `None` quando a tarefa nao pertence a expediente nenhum — que e o
    caso de 79 das 84 tarefas desta casa, e a tela nao deve falar de expediente
    para elas.

    ESTE E O «encerrei a tarefa e o expediente segue ativo» DO RELATO. O
    sistema nao fecha sozinho, mas para de ficar calado: diz o que sobrou e
    manda o operador ao lugar de encerrar.
    """
    con.row_factory = sqlite3.Row
    t = con.execute("SELECT linked_expediente_id FROM tasks WHERE id = ?",
                    (int(task_id),)).fetchone()
    if not t or not t["linked_expediente_id"]:
        return None
    try:
        estado = o_que_falta_para_encerrar(con, int(t["linked_expediente_id"]))
    except ExpedienteError:
        # O expediente sumiu (apagado a mao, banco antigo). A tarefa foi
        # concluida do mesmo jeito — isto e recado, e nao pode derrubar o ato.
        return None
    e = estado["expediente"]
    return {
        "expediente_id": e["id"],
        "protocolo": e["internal_protocol"],
        "assunto": e["subject"],
        "ja_encerrado": estado["ja_encerrado"],
        "abertas": estado["tarefas"]["abertas"],
        "recado": estado["recado"],
    }


def expedientes_com_tudo_concluido(con: sqlite3.Connection) -> list[dict]:
    """Os expedientes abertos cujas tarefas estao todas concluidas.

    E a lista do trabalho que ja acabou e ninguem fechou — o expediente 6 desta
    casa esta nela desde que a tarefa dele foi concluida. Sem esta lista, ele
    so apareceria a quem abrisse aquele expediente por acaso.
    """
    con.row_factory = sqlite3.Row
    prontos = []
    for e in con.execute(
            """SELECT id, internal_protocol, subject, stage, deadline_date
                 FROM expedientes ORDER BY id""").fetchall():
        if esta_encerrado(e["stage"]):
            continue
        t = tarefas_do_expediente(con, e["id"])
        if t["total"] and not t["abertas"]:
            prontos.append(dict(e) | {"concluidas": t["concluidas"]})
    return prontos

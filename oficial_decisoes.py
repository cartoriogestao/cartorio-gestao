"""O que espera o oficial decidir — a fila das perguntas dos robôs.

    «sempre continue, nunca fique sem fazer nada. Se precisar de minha
     intervenção para algo, desenvolva outra coisa que não precisa e quando eu
     retomar vou responder as pendências» — o oficial, 29/08/2026

A REGRA QUE ISTO TRANSFORMA EM TABELA
    «Na dúvida, imite o E-Ofício; sem precedente, recuse e pergunte.» Até
    09/10/2026 a pergunta ficava onde nascia — no fim de uma conversa, numa
    descrição de tarefa —, e o oficial respondia em lote quando lembrava de
    onde ela estava. Aqui toda pergunta mora num lugar só, com:

      - a CHAVE estável de quem pergunta (a mesma dúvida não entra duas vezes,
        e o robô que a fez a reconhece no dia seguinte);
      - as OPÇÕES e a RECOMENDAÇÃO, porque ele decide bem quando tem os fatos;
      - o que fica PARADO enquanto ninguém responde — é isso que dá a ordem.

O QUE ELA NÃO FAZ
    Não decide por ele, e não deduz resposta de silêncio. Pergunta respondida
    não volta a abrir sozinha. (`retirada_em` existe para o dia em que um robô
    precisar tirar da fila a pergunta cuja razão sumiu — com o motivo, e sem
    apagar; a função nasce com o primeiro robô que a chamar.)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from oficial_schema import init_oficial_schema

GRAVIDADES = ("CRITICO", "ATENCAO", "INFO")


class DecisaoError(ValueError):
    """Erro de regra da fila de decisões — a mensagem vai para a tela."""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def perguntar(con: sqlite3.Connection, *, chave: str, origem: str, pergunta: str,
              contexto: str = "", opcoes: list[str] | None = None,
              recomendacao: str = "", o_que_espera: str = "",
              gravidade: str = "ATENCAO", prazo: str | None = None) -> int:
    """Põe a pergunta na fila, ou renova a que já está lá. Devolve o id.

    Pergunta já RESPONDIDA não reabre: a resposta dele vale até ele mudar de
    ideia, e uma máquina que pergunta de novo o que já foi decidido ensina a
    não responder. Pergunta RETIRADA volta, porque a razão voltou.
    """
    if not (chave or "").strip() or not (pergunta or "").strip():
        raise DecisaoError("Pergunta sem chave ou sem texto não entra na fila.")
    if gravidade not in GRAVIDADES:
        raise DecisaoError(f"Gravidade desconhecida: {gravidade!r}.")
    init_oficial_schema(con)
    agora = _agora()
    opcoes_json = json.dumps(opcoes or [], ensure_ascii=False)
    linha = con.execute("SELECT id, respondida_em FROM of_decisoes WHERE chave = ?",
                        (chave,)).fetchone()
    if linha:
        if linha[1] is None:
            con.execute(
                """UPDATE of_decisoes SET pergunta=?, contexto=?, opcoes_json=?,
                       recomendacao=?, o_que_espera=?, gravidade=?, prazo=?,
                       vista_em=?, retirada_em=NULL WHERE id=?""",
                (pergunta, contexto, opcoes_json, recomendacao, o_que_espera,
                 gravidade, prazo, agora, linha[0]))
        else:
            con.execute("UPDATE of_decisoes SET vista_em=? WHERE id=?", (agora, linha[0]))
        return int(linha[0])
    cur = con.execute(
        """INSERT INTO of_decisoes (chave, origem, pergunta, contexto, opcoes_json,
               recomendacao, o_que_espera, gravidade, prazo, criada_em, vista_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (chave, origem, pergunta, contexto, opcoes_json, recomendacao, o_que_espera,
         gravidade, prazo, agora, agora))
    return int(cur.lastrowid)


def responder(con: sqlite3.Connection, decisao_id: int, resposta: str, por: str) -> None:
    """Grava a resposta do oficial. Quem lê a resposta é o robô que perguntou."""
    resposta = (resposta or "").strip()
    if len(resposta) < 2:
        raise DecisaoError("Escreva a resposta — uma palavra que seja.")
    if not (por or "").strip():
        raise DecisaoError("Diga quem está respondendo.")
    cur = con.execute(
        """UPDATE of_decisoes SET resposta=?, respondida_em=?, respondida_por=?
            WHERE id=? AND respondida_em IS NULL""",
        (resposta, _agora(), por.strip(), int(decisao_id)))
    if cur.rowcount == 0:
        raise DecisaoError(f"A decisão #{decisao_id} não existe ou já foi respondida.")


def abertas(con: sqlite3.Connection) -> list[dict]:
    """As perguntas sem resposta, a mais grave e a de prazo mais curto primeiro."""
    if not _tem_tabela(con):
        return []
    linhas = con.execute(
        """SELECT id, chave, origem, pergunta, contexto, opcoes_json, recomendacao,
                  o_que_espera, gravidade, prazo, criada_em
             FROM of_decisoes WHERE respondida_em IS NULL AND retirada_em IS NULL""").fetchall()
    fora = [{"id": r[0], "chave": r[1], "origem": r[2], "pergunta": r[3],
             "contexto": r[4] or "", "opcoes": json.loads(r[5] or "[]"),
             "recomendacao": r[6] or "", "o_que_espera": r[7] or "",
             "gravidade": r[8], "prazo": r[9], "criada_em": r[10]} for r in linhas]
    fora.sort(key=lambda d: (GRAVIDADES.index(d["gravidade"]), d["prazo"] or "9999",
                             d["criada_em"]))
    return fora


def _tem_tabela(con) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                       "AND name='of_decisoes'").fetchone() is not None

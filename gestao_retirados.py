"""O QUE NÃO CABE À GESTÃO — retirar da Checklist do dia e dos Projetos (T019).

    «permitir que retiremos do checklist do dia e dos projetos itens que nao
    cabem a gestao ou admin» — o oficial, 25/11/2026

RETIRAR NÃO É APAGAR, NEM RESOLVER
    Retirar é uma MARCA: «isto não cabe à gestão/administração», com motivo
    obrigatório, quem e quando. Nada se apaga — nem o achado do gestor
    (`ge_achados`), nem o projeto, a etapa ou o histórico (`dev_projetos*`).
    O item sai da lista principal da tela e aparece em «Ver os retirados»,
    de onde «Devolver à lista» o traz de volta. Retirar e devolver gravam na
    auditoria; a linha devolvida fica aqui, com quem devolveu e quando.

ONDE A MARCA SE PRENDE
    * Checklist: na CHAVE do achado (`ge_achados.chave`) — a mesma que o gestor
      usa para reconhecê-lo de um dia para o outro (`gestor_rotina.gravar_achados`).
      Por isso a rodada seguinte não o traz de volta como novo. Vale enquanto
      for o mesmo achado: se o gestor o fecha e ele volta com a mesma chave,
      é a mesma linha de `ge_achados` (o gestor não o trata como novo, e
      `primeiro_visto_em` não muda) e continua retirado; achado de chave nova
      é achado novo e aparece. Para trazer de volta, «Devolver à lista».
    * Projetos: no id do projeto (`dev_projetos.id`).

A COR OFICIAL NÃO MUDA À MÃO
    A cor do semáforo é a do painel geral, do painel do celular e do retrato
    que sai da casa (`painel_retrato`), e a regra dela é que «ninguém pinta de
    verde uma área à mão» (`conformidade`). Retirar, portanto, NÃO muda a cor
    oficial: a checklist e o cartão do painel mostram as duas — a oficial, que
    conta os retirados, e a «sem os retirados» (`conformidade.medir(
    excluir_chaves=...)`), com quantos são.

QUEM PODE
    Retira e devolve quem confere a checklist e cuida dos projetos: o oficial
    (ADMIN — o TI passa onde ele passa, `papeis`) e o gerente (MANAGER). O
    auditor vê os retirados da checklist, com o motivo, e não grava.
"""
from __future__ import annotations

from datetime import datetime

from bd_nativo import banco

TABELA = "ge_retirados_da_gestao"

#: As telas de onde se retira. O código é o que se grava: não muda.
CHECKLIST, PROJETOS = "CHECKLIST", "PROJETOS"
TELAS = frozenset({CHECKLIST, PROJETOS})

#: Quem retira e devolve (a mesma régua do «conferido hoje» e dos projetos).
QUEM_RETIRA = ("ADMIN", "MANAGER")

#: Os motivos prontos, opcionais: o texto curto é que é obrigatório.
MOTIVOS_PRONTOS = (
    ("ESCREVENTE", "É do escrevente da área"),
    ("TI", "É do TI"),
    ("FORA", "É de fora da serventia"),
    ("OUTRO", "Outro"),
)
ROTULO_DO_MOTIVO = dict(MOTIVOS_PRONTOS)
MOTIVO_MINIMO, MOTIVO_MAXIMO = 3, 300


class RetiradaError(ValueError):
    """O pedido de retirar ou devolver que não se grava, com o motivo para a tela."""


def _agora(agora: datetime | None) -> str:
    return (agora or datetime.now()).isoformat(timespec="seconds")


def _conferir_tela(tela: str) -> str:
    if tela not in TELAS:
        raise RetiradaError("Tela desconhecida.")
    return tela


def ativas(con, tela: str) -> dict[str, dict]:
    """As retiradas em vigor de uma tela: {chave: {por, em, motivo, ...}}. SÓ LÊ.

    No banco em que a tabela ainda não existe (subida que não rodou), nada
    está retirado — e o GET não a cria.
    """
    _conferir_tela(tela)
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return {}
    saida = {}
    for r in bd.ler(
            f"""SELECT id, chave, motivo_codigo, motivo, retirado_em, retirado_por
                  FROM {TABELA} WHERE tela = %s AND devolvido_em IS NULL
                 ORDER BY id""", (tela,)):
        codigo = str(r["motivo_codigo"] or "")
        saida[str(r["chave"])] = {
            "id": r["id"], "por": r["retirado_por"], "em": str(r["retirado_em"])[:16],
            "motivo": r["motivo"], "motivo_codigo": codigo or None,
            "motivo_pronto": ROTULO_DO_MOTIVO.get(codigo)}
    return saida


def historico(con, tela: str, chave: str) -> list[dict]:
    """Todas as retiradas de um item, devolvidas ou não, da mais antiga à mais
    nova. SÓ LÊ. É o que a linha do tempo do projeto mostra (S006)."""
    _conferir_tela(tela)
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return []
    saida = []
    for r in bd.ler(
            f"""SELECT id, motivo_codigo, motivo, retirado_em, retirado_por,
                       devolvido_em, devolvido_por
                  FROM {TABELA} WHERE tela = %s AND chave = %s ORDER BY id""",
            (tela, str(chave or "").strip())):
        codigo = str(r["motivo_codigo"] or "")
        saida.append({
            "id": r["id"], "motivo": r["motivo"], "motivo_codigo": codigo or None,
            "motivo_pronto": ROTULO_DO_MOTIVO.get(codigo),
            "retirado_em": str(r["retirado_em"] or ""), "retirado_por": r["retirado_por"],
            "devolvido_em": str(r["devolvido_em"] or "") or None,
            "devolvido_por": r["devolvido_por"]})
    return saida


def retirar(con, tela: str, chave: str, *, motivo: str, motivo_codigo: str | None = None,
            por: str, usuario_id: int | None, agora: datetime | None = None) -> dict:
    """Marca o item como «não cabe à gestão». Devolve {gravou, retirada}.

    O motivo (texto curto) é obrigatório; o motivo pronto, opcional. O item
    que já está retirado não ganha segunda linha: devolve `gravou=False`
    com a retirada que vale.
    """
    _conferir_tela(tela)
    chave = str(chave or "").strip()
    if not chave:
        raise RetiradaError("Item desconhecido.")
    texto = " ".join(str(motivo or "").split())
    if len(texto) < MOTIVO_MINIMO:
        raise RetiradaError("Diga em poucas palavras por que isto não cabe à gestão: "
                            "o motivo é obrigatório.")
    if len(texto) > MOTIVO_MAXIMO:
        raise RetiradaError(f"O motivo é um texto curto: até {MOTIVO_MAXIMO} letras.")
    codigo = str(motivo_codigo or "").strip().upper() or None
    if codigo and codigo not in ROTULO_DO_MOTIVO:
        raise RetiradaError("Motivo pronto desconhecido.")
    ja = ativas(con, tela).get(chave)
    if ja:
        return {"gravou": False, "retirada": ja}
    banco(con).escrever(
        f"""INSERT INTO {TABELA} (tela, chave, motivo_codigo, motivo, retirado_em,
                                  retirado_por, retirado_por_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (tela, chave, codigo, texto, _agora(agora), por, usuario_id))
    return {"gravou": True, "retirada": ativas(con, tela)[chave]}


def devolver(con, tela: str, chave: str, *, por: str, usuario_id: int | None,
             agora: datetime | None = None) -> dict | None:
    """Devolve o item à lista. Devolve a retirada encerrada, ou None se não havia.

    A linha fica, com quem devolveu e quando: o histórico não se apaga.
    """
    _conferir_tela(tela)
    chave = str(chave or "").strip()
    ja = ativas(con, tela).get(chave) if chave else None
    if not ja:
        return None
    banco(con).escrever(
        f"""UPDATE {TABELA} SET devolvido_em = %s, devolvido_por = %s,
                                devolvido_por_id = %s
             WHERE id = %s AND devolvido_em IS NULL""",
        (_agora(agora), por, usuario_id, ja["id"]))
    return ja

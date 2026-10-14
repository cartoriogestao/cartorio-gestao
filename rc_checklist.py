"""O checklist obrigatório antes de concluir o ato do Registro Civil.

    «Padronizar imediatamente assinaturas, gratuidade e categoria do selo nos
     atos futuros — **aplicar checklist obrigatório antes da conclusão de novos
     atos**.»
    — Relatório de Inspeção Ordinária de Cidade Exemplo, 12/08/2026, pág. 50.
      Prazo: **zero dias**. Prioridade: **crítica**.

ELE NÃO É CONVENIÊNCIA: É EXIGÊNCIA COM PRAZO VENCIDO
    A inspeção nomeou o instrumento — «checklist obrigatório» — e o momento —
    «antes da conclusão de novos atos». São duas exigências de prazo **zero**,
    e as duas dizem *imediatamente*:

    | pág. | o que |
    |---|---|
    | **49** | emolumentos, destinações, gratuidade e **selo** nos nascimentos |
    | **50** | **assinaturas**, gratuidade e **categoria do selo** nos atos futuros |

    Os itens deste módulo saem da letra delas, e não do que eu acharia
    importante conferir.

POR QUE ELE AVISA E NÃO TRAVA
    **Registro de nascimento é imperativo legal** (art. 250), e o balcão não
    pode parar. Mas o aviso sai **antes** de concluir, com o item e a página da
    exigência — e o que ficou por conferir **fica gravado no ato**, porque numa
    correição a pergunta é «o sistema avisou?», e a resposta tem de estar escrita.

    > É a mesma forma de `fr_conferencias`, o rastro das fraudes: grava-se quando
    > o operador **reconhece**, e não ao mostrar.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class ChecklistError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


FONTE = "Relatório de Inspeção Ordinária de Cidade Exemplo, 12/08/2026 (COGEX)"


# --------------------------------------------------------------- os itens
#
# **CADA UM SAI DA LETRA DA EXIGENCIA**, com a pagina ao lado. Item que eu
# achasse importante conferir e item que o proximo apaga por achar chato — o que
# sustenta a lista e a exigencia, e nao o meu gosto.
ITENS: tuple[dict, ...] = (
    {"chave": "ASSINATURAS",
     "rotulo": "As assinaturas foram colhidas",
     "pagina": 50,
     "da_exigencia": "padronizar imediatamente **assinaturas** (…) nos atos "
                     "futuros",
     "por_que": "a inspeção apontou o assento do Livro A-24, fl. 23 **sem as "
                "assinaturas** — e assento sem assinatura é ato que se contesta",
     "especies": ("NASCIMENTO", "CASAMENTO", "OBITO")},

    {"chave": "GRATUIDADE",
     "rotulo": "A gratuidade está definida",
     "pagina": 50,
     "da_exigencia": "padronizar imediatamente (…) **gratuidade** (…) nos atos "
                     "futuros",
     "por_que": "**ato gratuito lança com zero, e não deixa de lançar**: o valor "
                "que teria é o que a serventia compensa junto ao fundo, e ato "
                "gratuito fora do caixa é compensação que ninguém pede",
     "especies": ("NASCIMENTO", "CASAMENTO", "OBITO")},

    {"chave": "CATEGORIA_DO_SELO",
     "rotulo": "A categoria do selo está escolhida",
     "pagina": 50,
     "da_exigencia": "padronizar imediatamente (…) **categoria do selo** nos "
                     "atos futuros",
     "por_que": "não é só ter selo: é o selo da categoria certa — e escolher por "
                "semelhança seria assinar por quem selou",
     "especies": ("NASCIMENTO", "CASAMENTO", "OBITO")},

    {"chave": "EMOLUMENTOS",
     "rotulo": "Os emolumentos foram calculados",
     "pagina": 49,
     "da_exigencia": "padronizar imediatamente **emolumentos** (…) nos "
                     "nascimentos",
     "por_que": "ato lavrado e não cobrado é receita que some sem ninguém ver",
     "especies": ("NASCIMENTO",)},

    {"chave": "DESTINACOES",
     "rotulo": "As destinações dos fundos estão lançadas",
     "pagina": 49,
     "da_exigencia": "padronizar imediatamente (…) **destinações** (…) nos "
                     "nascimentos",
     "por_que": "são **quatro** fundos cobrados — e o ISS não entra no total",
     "especies": ("NASCIMENTO",)},
)

CHAVES = tuple(x["chave"] for x in ITENS)

# **O CHECKLIST AVISA, E NAO TRAVA** — registro de nascimento e imperativo legal
# (art. 250), e o balcao nao pode parar. Mas o que ficou por conferir FICA
# GRAVADO: numa correicao a pergunta e «o sistema avisou?».
AVISA_E_NAO_TRAVA = (
    "registro de nascimento é imperativo legal (art. 250), e o balcão não pode "
    "parar. O que ficou por conferir **fica gravado no ato**, porque numa "
    "correição a pergunta é «o sistema avisou?»")


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há. Nunca `str(v or "")`."""
    if v is None:
        return ""
    return str(v).strip()


def item(chave: str) -> dict:
    for x in ITENS:
        if x["chave"] == chave:
            return x
    raise ChecklistError(f"«{chave}» não é um item do checklist da inspeção.")


def itens_da_especie(especie: str) -> tuple[dict, ...]:
    """Os itens que aquele ato precisa conferir. Só calcula.

    **NEM TODO ITEM VALE PARA TODA ESPÉCIE**, e isso é da própria exigência: a da
    página 49 fala dos **nascimentos**; a da 50, dos **atos futuros** em geral.
    Cobrar emolumento de nascimento num assento de óbito seria inventar exigência
    — e exigência inventada é a que o balcão aprende a ignorar, levando as de
    verdade junto.
    """
    alvo = _texto(especie).upper()
    return tuple(x for x in ITENS if alvo in x["especies"])


def conferir(especie: str, marcados: Any) -> dict:
    """O que falta conferir naquele ato. Só calcula.

    Devolve os que faltam **com a página da exigência**, para quem lê saber que
    não é capricho do sistema.
    """
    esperados = itens_da_especie(especie)
    vistos = {_texto(x).upper() for x in (marcados or [])}
    faltam = [x for x in esperados if x["chave"] not in vistos]
    return {"esperados": len(esperados), "conferidos": len(esperados) - len(faltam),
            "faltam": faltam, "completo": not faltam}


def resumo_para_gravar(especie: str, marcados: Any) -> str:
    """A frase que fica no ato. Só calcula.

    **O QUE FICOU POR CONFERIR FICA ESCRITO**, e não só o que foi conferido: uma
    marca que só registra o bom deixa o silêncio significar duas coisas — «não
    faltou nada» e «ninguém olhou».
    """
    r = conferir(especie, marcados)
    if r["completo"]:
        return (f"Checklist da inspeção conferido: {r['conferidos']} de "
                f"{r['esperados']} itens.")
    faltando = ", ".join(f"{x['rotulo']} (pág. {x['pagina']})"
                         for x in r["faltam"])
    return (f"Checklist da inspeção: {r['conferidos']} de {r['esperados']} "
            f"itens. **Ficou por conferir:** {faltando}.")


def registrar(con: sqlite3.Connection, *, tabela: str, ato_id: int,
              especie: str, marcados: Any, agora: str, por: str) -> int:
    """Grava o que foi conferido naquele ato. GRAVA.

    **GRAVA-SE QUANDO O OPERADOR CONFERE, e nunca ao mostrar** — é a regra do
    rastro das fraudes, e há teste que abre a tela duas vezes e confere que nada
    foi gravado.
    """
    if not _texto(tabela) or int(ato_id or 0) < 1:
        raise ChecklistError("Diga de que ato é este checklist.")
    r = conferir(especie, marcados)
    cur = con.execute(
        """INSERT INTO rc_checklists (tabela, ato_id, especie, conferidos,
               esperados, faltaram, resumo, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (_texto(tabela), int(ato_id), _texto(especie).upper(),
         r["conferidos"], r["esperados"],
         ";".join(x["chave"] for x in r["faltam"]),
         resumo_para_gravar(especie, marcados), agora, por))
    return int(cur.lastrowid)


def do_ato(con: sqlite3.Connection, *, tabela: str, ato_id: int) -> dict | None:
    """O checklist daquele ato, se houver. Só lê."""
    con.row_factory = sqlite3.Row
    linha = con.execute(
        """SELECT * FROM rc_checklists WHERE tabela=? AND ato_id=?
            ORDER BY id DESC LIMIT 1""",
        (_texto(tabela), int(ato_id))).fetchone()
    return dict(linha) if linha else None


def atos_sem_checklist(con: sqlite3.Connection,
                       limite: int = 500) -> list[dict]:
    """Os assentos lavrados por esta casa que não passaram pelo checklist.

    **O QUE VEIO DO ACERVO NÃO ENTRA**: a exigência é para os **atos futuros**,
    e um assento de 1955 não podia ter passado por um checklist criado em 2026.
    Contá-lo poria setenta anos de livro numa lista com prazo zero.
    """
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute(
        """SELECT a.id, a.especie, a.numero, a.nome, a.data_ato
             FROM rc_assentos a
            WHERE COALESCE(a.origem,'') <> 'EOFICIO'
              AND COALESCE(a.situacao,'ATIVO') <> 'CANCELADO'
              AND NOT EXISTS (SELECT 1 FROM rc_checklists c
                               WHERE c.tabela = 'rc_assentos'
                                 AND c.ato_id = a.id)
         ORDER BY a.data_ato IS NULL, a.data_ato DESC, a.id DESC
            LIMIT ?""", (limite,))]


def quantas_pendentes(con: sqlite3.Connection) -> int:
    """Quantos atos ainda não passaram pelo checklist. Só lê."""
    return len(atos_sem_checklist(con, limite=100000))

"""O selo do Protesto conferido ANTES de lavrar — e a situação que pede um ato.

Ordem do oficial, 29/10/2026: «trabalhamos com mao de obra muito propensa a
erros e precisamos revisar os processos para nao permitir que a mao de obra
erre. vincular cada obrigacao a uma conduta [...]. se insistir em algo que eh
erro, precisa afirmar expressamente e deixar log.»

**O SELO SÓ SE DESCOBRIA DEPOIS.** A rota que lança o ato na ficha do título
lavrava primeiro e pedia o selo depois; sem item da tabela de emolumentos o
selo não sai, e o ato era desfeito (`cancelado=1`), com o título voltando à
situação de antes. Medido na produção em 29/10/2026, só leitura: **cinco atos
desfeitos por «Selo não emitido»** — quatro cancelamentos (28 e 29/10) e um
pagamento (21/10) —, e **quatro dos cinco pela mesma causa: nenhum item
marcado**. O quinto foi o aparelho que não achou o código. Dois custaram caro:
o título 1353, cujo cancelamento desfeito foi à CRA no retorno das 14h32
(consertado no PR #85), e o 9614, que ficou PAGO sem pagamento válido porque a
volta da situação ainda não existia naquela versão.

**A CAUSA SE SABE ANTES.** O item marcado para cobrança, ou o protocolo do
balcão com item livre, é a MESMA condição que `_selar_o_protesto` lê — e ela
já está no formulário antes de o ato ser lavrado. `conferir_antes_de_lavrar`
recusa ali, com a frase pronta, e o ato não chega a existir. A lista de itens
quem monta é a rota, pela mesma função que o selo usa: duas réguas para «há
item?» divergiriam no primeiro conserto, e a recusa daqui passaria a dizer uma
coisa e o selo a fazer outra.

**A RECUSA DO APARELHO CONTINUA DEPOIS**, e desfeita como hoje: rede fora do
ar, código que ele não acha, a trava do selo pago — nenhuma delas se sabe
antes de perguntar.

**NÃO HÁ AFIRMAÇÃO EXPRESSA QUE VENÇA ESTA TRAVA, e isso é medido.** O contrato
comum da casa (caixa `afirmo` + `afirmacao`, auditoria `AFIRMACAO_EXPRESSA`)
serve para vencer uma trava quando o caso concreto justifica. Aqui não há caso:
o Protesto não tem gratuidade no lançamento (a ficha não a oferece e
`protesto.py` não a conhece), e os **12 selos isentos** do Protesto no razão
(de 1.313, medido em 29/10/2026) saíram **com o código do item** — selo isento
também sai por item. Lavrar «sem item, porque é gratuito» seria pedir um selo
que não pode sair: o ato se desfaria do mesmo jeito, só que depois de lavrado.
Afirmar não muda o que o aparelho precisa receber.

**E O TÍTULO NUNCA FICA NUMA SITUAÇÃO SEM O ATO QUE A SUSTENTE.**
`titulos_sem_ato_que_sustente` é a conferência só-leitura disso: PAGO sem
pagamento válido, CANCELADO sem cancelamento, PROTESTADO sem protesto. Ela
MOSTRA; não corrige — o que fazer com o título é decisão do oficial. Medido em
29/10/2026: cinco títulos PAGO sem pagamento válido — o 9614 (pagamento
desfeito pelo selo) e quatro que já vieram assim da carga do E-Ofício.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

import ato_selado as AS
from bd_nativo import banco


# OS ATOS DA FICHA QUE NÃO PEDEM SELO PRÓPRIO — a lista que a rota lê para
# decidir se pede o selo depois de lavrar, e esta conferência para decidir se
# confere antes. UMA LISTA SÓ: se as duas divergissem, a tela recusaria um ato
# que nunca pediria selo, ou deixaria passar um que vai ser desfeito.
#
# As ordens judiciais não são ato da serventia (cumprimento de ordem de fora);
# o apontamento não sela desde 21/10/2026 — dos 1.409 do E-Ofício, 1.161 não
# têm selo, e os 248 que têm trazem o do ato POSTERIOR.
ATOS_SEM_SELO_PROPRIO = frozenset({
    "SUSTACAO", "REVOGACAO_SUSTACAO", "EFEITO_SUSPENSIVO",
    "REVOGACAO_EFEITO_SUSPENSIVO", "APONTAMENTO",
})

# O nome do ato na frase do balcão. O que não está aqui sai como «o ato».
O_ATO = {
    "INTIMACAO": "a intimação",
    "PROTESTO": "o protesto",
    "PAGAMENTO": "o pagamento",
    "DESISTENCIA": "a desistência",
    "RETIRADA": "a retirada",
    "CANCELAMENTO": "o cancelamento",
}


class SeloSemItemError(AS.AtoError):
    """O selo não vai poder sair: não há item. Mensagem pronta para o balcão.

    **É `AtoError`** de propósito: as rotas do Protesto já tratam essa família
    como recusa de regra (`flash` e volta), e a certidão não precisa de mais
    nada. A ficha do título a apanha antes, para devolver o formulário
    preenchido.
    """


def pede_selo_agora(tipo: Any, *, tabela: str = "pt_atos",
                    selo_digitado: bool = False,
                    selo_automatico: bool = True) -> bool:
    """Este lançamento vai pedir selo ao aparelho logo depois de lavrado? Só
    calcula.

    É o espelho da condição da rota: o selo digitado à mão dispensa o pedido;
    o robô não pede selo (`selo_robo.pode_selar_automatico`) e o ato dele fica
    pendente; e os atos de `ATOS_SEM_SELO_PROPRIO` não selam. A certidão sela
    sempre.
    """
    if selo_digitado or not selo_automatico:
        return False
    if str(tabela or "") == "pt_certidoes":
        return True
    return str(tipo or "").strip().upper() not in ATOS_SEM_SELO_PROPRIO


def conferir_antes_de_lavrar(tipo: Any,
                             itens: Iterable[str] | Callable[[], Iterable[str]],
                             *, tabela: str = "pt_atos",
                             selo_digitado: bool = False,
                             selo_automatico: bool = True,
                             protocolo_escolhido: bool = False) -> None:
    """Recusa, ANTES de o ato existir, o lançamento cujo selo não vai sair.
    Só calcula.

    `itens` são os códigos que o selo usaria — a rota os tira da mesma função
    que o selo lê —, ou uma função que os devolva: só se pergunta quando o
    lançamento vai mesmo pedir selo.

    Recusa com `SeloSemItemError`, dizendo o que fazer. Não recusa o que não
    pede selo agora (`pede_selo_agora`).
    """
    if not pede_selo_agora(tipo, tabela=tabela, selo_digitado=selo_digitado,
                           selo_automatico=selo_automatico):
        return
    lista = list(itens() if callable(itens) else (itens or ()))
    if lista:
        return
    raise SeloSemItemError(_frase_da_recusa(
        tipo, tabela=tabela, protocolo_escolhido=protocolo_escolhido))


def _frase_da_recusa(tipo: Any, *, tabela: str,
                     protocolo_escolhido: bool) -> str:
    """A frase do balcão: o que aconteceu, que nada foi gravado, e o que
    fazer. Só calcula."""
    if protocolo_escolhido:
        falta = ("não tem item marcado para cobrança, e o protocolo escolhido "
                 "não tem item livre — os itens dele já foram usados por outro "
                 "ato, ou ele não tem item da tabela")
    else:
        falta = ("não tem item marcado para cobrança nem protocolo do balcão "
                 "com item")
    if str(tabela or "") == "pt_certidoes":
        return ("Certidão NÃO emitida, e nada foi gravado: a certidão sela "
                "pelos itens da tabela de emolumentos, e este pedido "
                f"{falta}. Marque o item da certidão em «Cobrar no caixa» "
                "(com o seu caixa aberto) ou escolha o protocolo do "
                "atendimento, e emita de novo.")
    o_ato = O_ATO.get(str(tipo or "").strip().upper(), "o ato")
    return ("Ato NÃO lançado, e nada foi gravado: "
            f"{o_ato} sela pelos itens da tabela de emolumentos, e este "
            f"lançamento {falta}. Marque o item em «Cobrar no caixa» (com o "
            "seu caixa aberto) ou escolha o protocolo do atendimento, e lance "
            "de novo — o que você digitou continua no formulário.")


# ======================================== a situação que pede um ato válido
#
# CADA SITUAÇÃO DO TÍTULO NASCE DE UM ATO, e é esse ato que a sustenta no
# livro, na certidão e no retorno à CRA. Sem ele, o título afirma um fato que
# o livro não tem: o 9614 está PAGO, e o pagamento dele foi desfeito.
# RECEBIDO não pede ato — é o título antes de qualquer um.
ATO_QUE_SUSTENTA: dict[str, tuple[str, ...]] = {
    "APONTADO": ("APONTAMENTO",),
    "INTIMADO": ("INTIMACAO",),
    "PROTESTADO": ("PROTESTO",),
    "PAGO": ("PAGAMENTO",),
    "DESISTIDO": ("DESISTENCIA", "RETIRADA"),
    "CANCELADO": ("CANCELAMENTO",),
}

# A CARGA DO E-OFÍCIO marca o título com esta chave de origem
# (`acervo_carga`, `tbAvisoProtesto:<intChave>`). É ela, e não `origem`, que
# diz que a linha veio do acervo: `origem` diz de onde o TÍTULO veio (CRA,
# CENPROT, MANUAL).
PREFIXO_DO_ACERVO = "tbAvisoProtesto:"

# O teto da lista. Alarme que soa sempre é alarme que ninguém ouve, e uma lista
# que não cabe na tela já é outro problema — o número vem junto.
LIMITE_DA_LISTA = 200


def _condicao_do_ato_valido() -> tuple[str, list[str]]:
    """O `OR` que casa a situação com o tipo de ato que a sustenta, e os
    parâmetros dele. Só calcula."""
    partes, params = [], []
    for situacao, tipos in ATO_QUE_SUSTENTA.items():
        lugares = ",".join(["%s"] * len(tipos))
        partes.append(f"(t.situacao = %s AND a.tipo IN ({lugares}))")
        params += [situacao, *tipos]
    return " OR ".join(partes), params


def _achar(con, *, titulo_id: int | None = None,
           limite: int = LIMITE_DA_LISTA) -> list[dict]:
    """Os títulos cuja situação não tem o ato válido. Só LÊ."""
    condicao, params = _condicao_do_ato_valido()
    situacoes = list(ATO_QUE_SUSTENTA)
    lugares = ",".join(["%s"] * len(situacoes))
    filtro_do_titulo = " AND t.id = %s" if titulo_id is not None else ""
    sql = f"""SELECT t.id, t.situacao, t.protocolo, t.numero_titulo,
                     t.origem_chave
                FROM pt_titulos t
               WHERE t.situacao IN ({lugares}){filtro_do_titulo}
                 AND NOT EXISTS (
                     SELECT 1 FROM pt_atos a
                      WHERE a.titulo_id = t.id
                        AND COALESCE(a.cancelado, 0) = 0
                        AND ({condicao}))
               ORDER BY t.id
               LIMIT %s"""
    valores = situacoes + ([int(titulo_id)] if titulo_id is not None else [])
    linhas = banco(con).ler(sql, valores + params + [int(limite)])
    return [_explicar(con, dict(r)) for r in linhas]


def _data_br(texto: Any) -> str:
    bruto = str(texto or "")[:10]
    if len(bruto) == 10 and bruto[4] == "-" and bruto[7] == "-":
        return f"{bruto[8:10]}/{bruto[5:7]}/{bruto[0:4]}"
    return bruto or "data não gravada"


def _explicar(con, linha: dict) -> dict:
    """Diz o que se sabe do porquê: o ato foi desfeito, ou o título veio
    assim do acervo, ou não há ato nenhum daquele tipo. Só LÊ."""
    tipos = ATO_QUE_SUSTENTA[linha["situacao"]]
    lugares = ",".join(["%s"] * len(tipos))
    desfeito = banco(con).um(
        f"""SELECT id, tipo, criado_em, motivo_cancelamento
              FROM pt_atos
             WHERE titulo_id = %s AND tipo IN ({lugares})
               AND COALESCE(cancelado, 0) <> 0
             ORDER BY id DESC LIMIT 1""",
        [int(linha["id"]), *tipos])
    o_ato = O_ATO.get(tipos[0], "o ato").split(" ", 1)[1]
    if desfeito:
        origem = "DESFEITO"
        motivo = (str(desfeito["motivo_cancelamento"] or "").strip().rstrip(".")
                  or "sem motivo gravado")
        explicacao = (
            f"O ato de {o_ato} lançado em {_data_br(desfeito['criado_em'])} "
            f"(ato {desfeito['id']} do sistema) foi desfeito — {motivo} —, e "
            f"o título continuou {linha['situacao']}.")
    elif str(linha.get("origem_chave") or "").startswith(PREFIXO_DO_ACERVO):
        origem = "ACERVO"
        explicacao = (f"Veio assim da carga do E-Ofício: a situação "
                      f"{linha['situacao']} entrou sem o ato de {o_ato}.")
    else:
        origem = "SEM_ATO"
        explicacao = (f"Não há ato de {o_ato} neste título — nem válido, nem "
                      "desfeito.")
    return {
        "titulo_id": int(linha["id"]),
        "situacao": linha["situacao"],
        "protocolo": linha.get("protocolo"),
        "numero_titulo": linha.get("numero_titulo"),
        "ato_esperado": o_ato,
        "tipos": tipos,
        "origem": origem,
        "desfeito_id": int(desfeito["id"]) if desfeito else None,
        "explicacao": explicacao,
    }


def titulos_sem_ato_que_sustente(con, *,
                                 limite: int = LIMITE_DA_LISTA) -> list[dict]:
    """Os títulos cuja situação não tem o ato válido que a sustente. Só LÊ.

    Uma linha por título, com a situação, o ato que falta e o que se sabe do
    porquê (`origem`: DESFEITO, ACERVO ou SEM_ATO). Não corrige nada.
    """
    return _achar(con, limite=limite)


def situacao_sem_ato(con, titulo_id: int) -> dict | None:
    """O mesmo achado, para um título só — a ficha. Só LÊ."""
    achados = _achar(con, titulo_id=int(titulo_id), limite=1)
    return achados[0] if achados else None

"""A MINUTA DO LIVRO 3 — o ato escrito e ainda não lavrado.

Item 1 da fila que o oficial mandou fazer em 20/09/2026, depois de resolvido o
CNIB: *«deixe o livro 3 com as mesmas ferramentas do livro 2»*.

**ELE NÃO LAVRA, NÃO NUMERA, NÃO SELA E NÃO COBRA** — quem lavra é
`livro3_lancar`, a rota de sempre, com os campos preenchidos. Duas portas para
lavrar seriam duas versões da regra que numera e sela, e elas divergiriam no
primeiro conserto. Há teste que varre os nomes públicos deste módulo, a mesma
régua das fraudes, do CNIB e do usucapião.


O QUE A MEDIÇÃO ACHOU, e é o que faz esta tabela existir

O Livro 3 **já tinha meia peça**: as duas minutas de cancelamento — dos
registros **1.198** e **1.243** — moravam em `rascunhos_de_tela`, que é a
gaveta de rascunho de qualquer tela da casa. Medido em 20/09/2026:

  * sem **situação** — a do 1.243 virou a AV-01 e continuou lá, do mesmo jeito
    que estava, como se ainda esperasse alguém;
  * sem **número pretendido**, sem **descarte com motivo escrito** e sem saber
    **se já virou ato**;
  * e sem os três campos que o selo exige, que é justamente o que faltava para
    a AV-01 do 1.243 sair selada.

**A MINUTA CARREGA O QUE O SELO PEDE**, e essa é a diferença para a do Livro 2:
aqui ela existe para ser «revisada **e selada**», e o item da tabela de custas,
a natureza do título e o valor declarado não saem do tipo do ato. Guardados
nela, chegam preenchidos na hora de lavrar.

**O NÚMERO É PRETENDIDO, E NÃO RESERVADO** — guardá-lo como reserva faria a
minuta trancar um número do livro sem ato nenhum.

**DESCARTAR EXIGE MOTIVO ESCRITO**, como a dispensa do usucapião, a reabertura
da matrícula e a minuta do Livro 2. E **descartada não some**: fica na tabela
com o motivo, porque a pergunta que aparece meses depois é «e aquela averbação
que estava para sair?».
"""
from __future__ import annotations

import sqlite3

from bd_nativo import banco
from typing import Any

import ra_expurgo as EXP

# ------------------------------------------------------------- vocabulário

A_REVISAR, LAVRADA, DESCARTADA = "A_REVISAR", "LAVRADA", "DESCARTADA"

SITUACOES: dict[str, str] = {
    A_REVISAR: "A revisar e lavrar",
    LAVRADA: "Lavrada",
    DESCARTADA: "Descartada",
}

# OS DOIS TIPOS DO LIVRO 3. **O cancelamento não é um terceiro**: ele é uma
# averbação — o registro fica na ficha, com a averbação dizendo que foi
# cancelado e por quê.
TIPOS: dict[str, str] = {"R": "R — registro", "AV": "AV — averbação"}

MANUAL, IMPORTACAO, RASCUNHO_DE_TELA, DESFEITO_DE_ATO = (
    "MANUAL", "IMPORTACAO", "RASCUNHO_DE_TELA", "DESFEITO_DE_ATO")
ORIGENS: tuple[str, ...] = (MANUAL, IMPORTACAO, RASCUNHO_DE_TELA,
                            DESFEITO_DE_ATO)

# QUANTAS LETRAS FAZEM UM TEOR. Vinte, o mesmo piso da minuta do Livro 2 — e
# ele existe para a minuta vazia não ocupar a fila fingindo que há trabalho
# escrito ali.
MINIMO_DO_TEOR = 20

# O PISO DO MOTIVO DO DESCARTE. Dez letras, o mesmo da baixa da nota de
# revisão e do fechamento do problema: «não serve» não explica nada.
MINIMO_DO_MOTIVO = 10


class MinutaError(ValueError):
    """Erro de regra, com frase pronta para o balcão — vira `flash(danger)`."""


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


# ----------------------------------------------------------------- escrita


def criar(con: sqlite3.Connection, *, registro_id: int, tipo: str, teor: str,
          agora: str, numero_pretendido=None, data_pretendida=None,
          natureza_titulo=None, codigo_tj=None, base_calculo_centavos=None,
          protocolo=None, origem: str = MANUAL, origem_chave=None,
          observacao=None, usuario=None) -> int:
    """Põe uma minuta na fila daquele registro. ESCREVE. Devolve o `id`."""
    tipo = _texto(tipo).upper()
    if tipo not in TIPOS:
        raise MinutaError(
            f"Tipo de ato desconhecido no Livro 3: {tipo!r}. Aqui há dois — "
            f"registro (R) e averbação (AV); o cancelamento é uma averbação.")
    if origem not in ORIGENS:
        raise MinutaError(f"Origem de minuta desconhecida: {origem!r}.")
    if len(_texto(teor)) < MINIMO_DO_TEOR:
        raise MinutaError(
            f"Escreva o teor da minuta — pelo menos {MINIMO_DO_TEOR} letras. "
            f"Minuta vazia ocupa a fila fingindo que há trabalho escrito.")
    bd = banco(con)
    if bd.um("SELECT 1 AS um FROM ra_registros WHERE id=%s",
             (int(registro_id),)) is None:
        raise MinutaError("Registro do Livro 3 não encontrado.")
    novo = bd.escrever(
        """INSERT INTO ra_minutas
              (registro_id, tipo, numero_pretendido, data_pretendida, teor,
               natureza_titulo, codigo_tj, base_calculo_centavos, protocolo,
               origem, origem_chave, observacao, situacao, criado_em,
               criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (int(registro_id), tipo, numero_pretendido, data_pretendida,
         _texto(teor), _texto(natureza_titulo) or None,
         _texto(codigo_tj) or None, base_calculo_centavos,
         _texto(protocolo) or None, origem, _texto(origem_chave) or None,
         _texto(observacao) or None, A_REVISAR, agora, _texto(usuario) or None))
    return int(novo[0]["id"])


def atualizar(con: sqlite3.Connection, minuta_id: int, *, teor: str,
              agora: str, tipo=None, numero_pretendido=None,
              data_pretendida=None, natureza_titulo=None, codigo_tj=None,
              base_calculo_centavos=None, protocolo=None, usuario=None) -> None:
    """Guarda a revisão **sem lavrar**. ESCREVE.

    REVISAR PODE LEVAR MAIS DE UMA SENTADA, e sem isto «revisar» é meia
    palavra: quem saísse da tela perderia o trabalho e no dia seguinte
    redigitaria tudo ou lavraria com o erro dentro — **e ato lavrado não se
    edita**, o conserto seria outra averbação.

    **`None` QUER DIZER «NÃO MEXI», E NÃO «ESVAZIE»** — uma revisão que
    mandasse só o teor apagaria o item da tabela de custas, que é justamente o
    que o selo exige. É o defeito do padrão do `get` pelo outro lado.
    """
    m = _minuta_para_gravar(banco(con), minuta_id)
    if not m:
        raise MinutaError("Minuta não encontrada.")
    if m["situacao"] == LAVRADA:
        raise MinutaError(
            "Esta minuta já virou ato — mudar o texto dela faria a prova "
            "discordar do que está escrito no livro.")
    if m["situacao"] == DESCARTADA:
        raise MinutaError(
            "Esta minuta foi descartada. Crie outra, para ficar escrito que "
            "houve duas.")
    if len(_texto(teor)) < MINIMO_DO_TEOR:
        raise MinutaError(
            f"Escreva o teor da minuta — pelo menos {MINIMO_DO_TEOR} letras.")
    novo_tipo = _texto(tipo).upper() or m["tipo"]
    if novo_tipo not in TIPOS:
        raise MinutaError(f"Tipo de ato desconhecido no Livro 3: {tipo!r}.")
    banco(con).escrever(
        """UPDATE ra_minutas
              SET teor=%s, tipo=%s,
                  numero_pretendido=COALESCE(%s, numero_pretendido),
                  data_pretendida=COALESCE(%s, data_pretendida),
                  natureza_titulo=COALESCE(%s, natureza_titulo),
                  codigo_tj=COALESCE(%s, codigo_tj),
                  base_calculo_centavos=COALESCE(%s, base_calculo_centavos),
                  protocolo=COALESCE(%s, protocolo),
                  atualizado_em=%s, atualizado_por=%s
            WHERE id=%s""",
        (_texto(teor), novo_tipo, numero_pretendido, data_pretendida,
         _texto(natureza_titulo) or None, _texto(codigo_tj) or None,
         base_calculo_centavos, _texto(protocolo) or None,
         agora, _texto(usuario) or None, int(minuta_id)))


def descartar(con: sqlite3.Connection, minuta_id: int, *, motivo: str,
              agora: str, usuario=None) -> None:
    """Tira a minuta da fila **sem lavrar**, com o motivo escrito. ESCREVE."""
    motivo = _texto(motivo)
    if len(motivo) < MINIMO_DO_MOTIVO:
        raise MinutaError(
            f"Escreva o motivo do descarte com pelo menos "
            f"{MINIMO_DO_MOTIVO} letras — «não serve» não explica nada a quem "
            f"ler depois.")
    m = _minuta_para_gravar(banco(con), minuta_id)
    if not m:
        raise MinutaError("Minuta não encontrada.")
    if m["situacao"] == LAVRADA:
        raise MinutaError(
            "Esta minuta já virou ato — o que se desfaz agora é o ato, por "
            "averbação, e não a minuta.")
    banco(con).escrever(
        """UPDATE ra_minutas SET situacao=%s, observacao=%s, atualizado_em=%s,
               atualizado_por=%s WHERE id=%s""",
        (DESCARTADA, motivo, agora, _texto(usuario) or None, int(minuta_id)))


def voltar_do_ato(con: sqlite3.Connection, ato_id: int, *, agora: str,
                  usuario=None, motivo: str = "") -> dict:
    """Desfaz um ato do Livro 3 e o guarda como minuta. ESCREVE.

    ORDEM DO OFICIAL EM 21/09/2026, sobre a AV-01 do registro 1.243, que
    ficou lavrada e sem selo: *«coloque o ato em minutas para eu tentar selar
    novamente»*. É a mesma saída que o Livro 2 ganhou em 16/09.

    **O QUE ELA GUARDA:** o teor, o número que o ato tinha (como
    **pretendido**), e os três campos do selo — item da tabela de custas,
    natureza do título e valor declarado. Sem eles, quem relavrar digita tudo
    de novo.

    **AS PARTES NÃO SE MOVEM, e aqui isso é diferente do Livro 2.** Lá elas
    são do ATO e somem com ele, e por isso a minuta as carrega; aqui
    `ra_partes` é do **REGISTRO** — a ficha inteira — e continua onde está.
    Movê-las seria tirar do registro quem não deixou de ser parte dele.

    AS TRÊS RECUSAS, e cada uma protege alguma coisa:

      1. **Ato com selo não volta.** Selo pago amarrado a um ato que deixa de
         existir é selo órfão, e minuta não tem onde guardá-lo.
      2. **Só o ÚLTIMO ato do registro.** A numeração do Livro 3 é contínua
         (R-1, AV-2, AV-3): tirar um do meio abriria um buraco no livro.
      3. **Ato com dinheiro no caixa não volta.** Dinheiro que entrou sai por
         estorno, que deixa rastro.

    **E ELA DESFAZ O CANCELAMENTO QUE O ATO CAUSOU.** Se o registro está
    `CANCELADO` e o ato que volta é o que o cancelou, a situação volta a
    `ATIVO` — deixar a ficha cancelada por uma averbação que não existe mais
    é o carimbo que mente.

    Devolve `{"minuta_id", "rotulo", "descancelou"}`.
    """
    bd = banco(con)
    a = bd.um("SELECT registro_id FROM ra_atos WHERE id=%s", (int(ato_id),))
    if not a:
        raise MinutaError("O ato não existe mais — nada a devolver.")
    # AS TRÊS RECUSAS SE CONFEREM DENTRO DA TRAVA DA LAVRATURA
    # (`ra_registro._proximo_ato`, a mesma de `ra_correcoes.renumerar`) e com
    # o ato PRESO: um ato lavrado no meio faria este deixar de ser o último, e
    # o selo ou o dinheiro gravados no meio sairiam apagados junto com ele. A
    # trava vem antes do FOR UPDATE, na ordem de quem renumera — ao contrário,
    # os dois se esperariam.
    bd.travar(f"ra_atos.numero:{int(a['registro_id'])}")
    a = bd.um("SELECT * FROM ra_atos WHERE id=%s FOR UPDATE", (int(ato_id),))
    if not a:
        raise MinutaError("O ato não existe mais — nada a devolver.")
    a = dict(a)
    rotulo = f"{a['tipo']}-{a['numero']}"

    if _texto(a.get("selo")):
        raise MinutaError(
            f"O ato {rotulo} tem selo ({_texto(a['selo'])[:28]}…) e por isso "
            f"não volta para as minutas: selo pago amarrado a ato que deixa "
            f"de existir é selo órfão.")
    depois = int(bd.valor(
        "SELECT COUNT(*) FROM ra_atos WHERE registro_id=%s AND id>%s",
        (a["registro_id"], int(ato_id))))
    if depois:
        raise MinutaError(
            f"O ato {rotulo} não é o último do registro — há {depois} ato(s) "
            f"depois dele. A numeração do Livro 3 é contínua, e tirar um do "
            f"meio abriria um buraco no livro.")
    if a.get("lancamento_id"):
        raise MinutaError(
            f"O ato {rotulo} tem dinheiro lançado no caixa. Dinheiro que "
            f"entrou sai por estorno, que deixa rastro — e não apagando o "
            f"ato.")

    minuta_id = criar(
        con, registro_id=a["registro_id"], tipo=a["tipo"],
        teor=_texto(a.get("teor")) or _texto(a.get("motivo_cancelamento")),
        agora=agora, numero_pretendido=a["numero"],
        data_pretendida=a.get("data_ato"),
        natureza_titulo=a.get("natureza_titulo"),
        codigo_tj=a.get("codigo_tj"),
        base_calculo_centavos=a.get("base_calculo_centavos"),
        origem=DESFEITO_DE_ATO, origem_chave=f"ra_atos:{int(ato_id)}",
        observacao=_texto(motivo) or None, usuario=usuario)

    # O CANCELAMENTO QUE ESTE ATO CAUSOU SE DESFAZ COM ELE. FOR UPDATE: o
    # descancelamento (`ra_correcoes.descancelar`) prende a mesma linha, e sem
    # isto os dois devolveriam a ficha a ATIVO e cada um contaria que foi ele.
    registro = bd.um(
        "SELECT situacao FROM ra_registros WHERE id=%s FOR UPDATE",
        (a["registro_id"],))
    descancelou = bool(registro
                       and _texto(registro["situacao"]).upper() == "CANCELADO")
    if descancelou:
        bd.escrever("UPDATE ra_registros SET situacao='ATIVO' WHERE id=%s",
                    (a["registro_id"],))

    # A ATA DE OCORRENCIA NASCE AQUI, NA MESMA TRANSACAO — item 6 da fila.
    # A auditoria responde «quem e quando»; a correicao pergunta «o que estava
    # escrito naquele ato», e essa resposta so existe na ata, porque o ato
    # saiu do livro. Ata sem ato desfeito, e ato desfeito sem ata, sao os dois
    # jeitos de isto dar errado.
    numero_do_registro = bd.um(
        "SELECT numero FROM ra_registros WHERE id=%s",
        (a["registro_id"],))
    expurgo_id = EXP.registrar(
        con, registro_id=a["registro_id"],
        registro_numero=(numero_do_registro["numero"] if numero_do_registro else None),
        ato=a, motivo=motivo, agora=agora, usuario=usuario,
        minuta_id=minuta_id)

    bd.escrever("DELETE FROM ra_atos WHERE id=%s", (int(ato_id),))
    return {"minuta_id": minuta_id, "rotulo": rotulo,
            "descancelou": descancelou, "expurgo_id": expurgo_id}


def marcar_lavrada(con: sqlite3.Connection, minuta_id: int, *, ato_id: int,
                   agora: str, usuario=None) -> None:
    """Amarra a minuta ao ato que saiu dela. ESCREVE.

    **NA MESMA TRANSAÇÃO DO ATO**, e isso é regra e não conselho: ato que não
    entra tem de deixar a minuta onde estava. É o que a do Livro 2 faz, e há
    teste que lavra por cima de um número já ocupado para provar.

    **A MINUTA NÃO SE APAGA AO VIRAR ATO**: ela é a prova de que aquele texto
    existia antes e de onde veio.
    """
    m = _minuta_para_gravar(banco(con), minuta_id)
    if not m:
        raise MinutaError("Minuta não encontrada.")
    if m["situacao"] == LAVRADA:
        raise MinutaError(
            f"Esta minuta já foi lavrada (ato {m['ato_id']}). Lavrá-la de novo "
            f"poria o mesmo texto duas vezes no livro.")
    banco(con).escrever(
        """UPDATE ra_minutas SET situacao=%s, ato_id=%s, atualizado_em=%s,
               atualizado_por=%s WHERE id=%s""",
        (LAVRADA, int(ato_id), agora, _texto(usuario) or None, int(minuta_id)))


def _minuta_para_gravar(bd, minuta_id: int) -> dict | None:
    """A minuta com a linha PRESA, para quem confere a situação e grava.

    `uma` só lê, e a tela a chama. Quem confere «já virou ato?» e depois
    grava precisa segurar a linha até o fim da transação: no SQLite a escrita
    era uma por vez; no PostgreSQL, sem o FOR UPDATE, a minuta lavrada ao
    mesmo tempo passa pela conferência e sai descartada ou com outro texto.
    """
    bd._escrita()
    linha = bd.um("SELECT * FROM ra_minutas WHERE id=%s FOR UPDATE",
                  (int(minuta_id),))
    return dict(linha) if linha else None


# ------------------------------------------------------------------ leitura


def uma(con: sqlite3.Connection, minuta_id: int) -> dict | None:
    """Uma minuta, ou `None`. Só lê."""
    linha = banco(con).um("SELECT * FROM ra_minutas WHERE id=%s",
                          (int(minuta_id),))
    return dict(linha) if linha else None


def listar(con: sqlite3.Connection, registro_id: int,
           *, situacao: str | None = A_REVISAR) -> list[dict]:
    """As minutas daquele registro. `situacao=None` traz todas. Só lê."""
    if situacao is None:
        linhas = banco(con).ler(
            "SELECT * FROM ra_minutas WHERE registro_id=%s ORDER BY id",
            (int(registro_id),))
    else:
        linhas = banco(con).ler(
            "SELECT * FROM ra_minutas WHERE registro_id=%s AND situacao=%s "
            "ORDER BY id", (int(registro_id), situacao))
    return [dict(x) for x in linhas]


def a_revisar(con: sqlite3.Connection) -> list[dict]:
    """Tudo o que espera revisão no Livro 3, da casa inteira. Só lê.

    É o que o painel dos inacabados pergunta — e é por ela que uma minuta
    esquecida num registro que ninguém abre volta a aparecer.

    O mais recente em cima (of-0150).
    """
    linhas = banco(con).ler(
        """SELECT m.*, r.numero registro_numero
             FROM ra_minutas m JOIN ra_registros r ON r.id = m.registro_id
            WHERE m.situacao=%s ORDER BY m.id DESC""", (A_REVISAR,))
    return [dict(x) for x in linhas]


# ------------------------------------------------------- a pre-visualizacao

# A MARCA E A DO LIVRO 2, lida de la. Ela aparece em tres lugares na tela e
# **continua na impressao**, porque quem imprime pode entregar — e um papel
# que afirma um ato que nao existe e pior que papel nenhum.
from ri_rascunho import MARCA


def como_ficara(con: sqlite3.Connection, registro_id: int,
                minuta_id: int) -> dict:
    """O registro com a minuta no fim — **montado em memória, sem gravar**.

    Devolve `{registro, atos, minuta, numero_previsto}`, com a minuta já
    trazendo o número que ela **teria** e a marca de que não é ato.

    OS ATOS VÊM NA ORDEM DO LIVRO e a minuta no fim, porque é ali que ela
    entraria. Mostrá-la no meio faria a tela responder a pergunta errada: a
    pergunta é «como esta ficha vai ler depois deste ato», e não «onde este
    texto caberia».

    **O NÚMERO PREVISTO É O PRÓXIMO DA NUMERAÇÃO CONTÍNUA** deste livro — R-1,
    AV-2, AV-3 —, e não o `numero_pretendido` que a minuta guarda: aquele é
    sugestão de quem escreveu, este é o que o livro dará se o ato sair agora.
    """
    bd = banco(con)
    registro = bd.um("SELECT * FROM ra_registros WHERE id=%s",
                     (int(registro_id),))
    if not registro:
        raise MinutaError("Registro do Livro 3 não encontrado.")
    m = uma(con, minuta_id)
    if not m or int(m["registro_id"]) != int(registro_id):
        raise MinutaError("Essa minuta não é deste registro.")
    atos = bd.ler(
        "SELECT * FROM ra_atos WHERE registro_id=%s ORDER BY numero, id",
        (int(registro_id),))
    previsto = (max((int(a["numero"]) for a in atos), default=0)) + 1
    m = dict(m)
    m["numero_previsto"] = previsto
    m["rotulo"] = f"{m['tipo']}-{previsto}"
    m["marca"] = MARCA
    return {"registro": dict(registro), "atos": atos, "minuta": m,
            "numero_previsto": previsto}

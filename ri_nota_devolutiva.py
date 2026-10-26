"""A NOTA DEVOLUTIVA DO RI — emitir, anexar o papel e registrar o reingresso, num lugar só.

    «o sistema tem local claro para cadastrar nota devolutiva no protocolo?»
    «vamos mudar conforme recomendado» — o oficial, 25/10/2026

O QUE SE MEDIU NA PRODUÇÃO ANTES DE ESCREVER (25/10/2026, só leitura)

| | |
|---|---|
| notas em `ri_notas_devolutivas` | **6**, todas lançadas por script em 12/10; **nenhuma** pela tela |
| notas feitas em Word/PDF e só ANEXADAS ao protocolo | **4** protocolos (o protocolo ficou ABERTO, sem prazo de exigência) |
| anexos dos protocolos do RI com tipo | **0 de 109** — a tela não perguntava o que era o papel |

A tela da nota existia, mas pedia as exigências DIGITADAS, uma por linha — e a
nota desta casa é redigida em Word, com itens numerados e fundamentação, e
assinada. Cadastrar era digitar tudo de novo; então o arquivo ia para «Anexar»,
o primeiro painel do protocolo, e a nota não existia para o sistema.

O DESENHO
    O ANEXO PODE SER A NOTA. Escolhendo o tipo «nota devolutiva» ao anexar, o
    próprio arquivo é a nota: ela nasce numerada, o protocolo passa a devolvido
    e a qualificação negativa é gravada — a mesma transação da tela da nota.
    As exigências digitadas ficam OPCIONAIS quando há o arquivo: elas servem à
    lista e à nota impressa pelo sistema, e o papel assinado já as contém.

    O CUMPRIMENTO DE EXIGÊNCIA REGISTRA O REINGRESSO da nota aberta, com a regra
    de sempre (art. 44 do CN-MA): dentro da vigência da prenotação o título
    volta ao mesmo número; fora dela, a nota fica «fora do prazo» e é preciso
    protocolo novo.

    UMA FUNÇÃO PARA CADA COISA, chamada pelas três portas (a tela da nota, o
    painel de anexos e a tela do reingresso). Duas versões da regra que numera
    a nota divergiriam no primeiro conserto.

O ELO ENTRE A NOTA E O ARQUIVO
    É o próprio anexo: `attachments.documento_tipo = 'NOTA_DEVOLUTIVA'` e a
    descrição começando por «Nota devolutiva nº N». Sem coluna nova — o script
    que regularizou as notas antigas na produção (25/10/2026) gravou nesta mesma
    forma antes de esta versão subir, e as duas pontas se leem igual.

O QUE ESTE MÓDULO NÃO FAZ
    Não lavra, não sela, não cobra e não encerra prenotação.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from bd_nativo import banco
import protocolo_documentos as PDOC
import ri_pedidos as PED
import ri_prenotacao_prazo as PRAZO

NOTA = "NOTA_DEVOLUTIVA"
CUMPRIMENTO = "CUMPRIMENTO_EXIGENCIA"

# O vocabulário do protocolo geral (`protocolo_documentos`), com os dois papéis
# que só a prenotação tem. O título vem primeiro: é o que mais se anexa.
TIPOS_DE_DOCUMENTO: tuple[tuple[str, str], ...] = (
    ("TITULO", PDOC.ROTULO_DO_TIPO["TITULO"]),
    (NOTA, "Nota devolutiva / nota de exigência (o arquivo já redigido e assinado)"),
    (CUMPRIMENTO, "Cumprimento de exigência (o que o interessado trouxe depois da nota)"),
) + tuple(t for t in PDOC.TIPOS_DE_DOCUMENTO if t[0] not in ("TITULO",))
ROTULO_DO_TIPO = dict(TIPOS_DE_DOCUMENTO)

# Onde o título pode receber nota: enquanto a prenotação corre e nada foi lavrado.
SITUACOES_QUE_ACEITAM_NOTA = ("ABERTO", "DEVOLVIDO")


class NotaError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


def descricao_da_nota(numero: int) -> str:
    return f"Nota devolutiva nº {int(numero)}"


def descricao_do_cumprimento(numero: int) -> str:
    return f"Cumprimento da nota devolutiva nº {int(numero)}"


def por_que_nao_emite(p: Any) -> str | None:
    """O motivo de o protocolo não poder receber nota — ou None, quando pode."""
    if p["situacao"] not in SITUACOES_QUE_ACEITAM_NOTA:
        return (f"O protocolo {p['numero']} está {str(p['situacao']).lower()}: "
                f"nota devolutiva só cabe enquanto a prenotação corre.")
    if p["ato_id"]:
        return (f"O título do protocolo {p['numero']} já foi registrado: a nota devolutiva "
                f"é a qualificação negativa, e ela não cabe depois do ato lavrado.")
    return None


def nota_aberta(con: Any, protocolo_id: int) -> dict | None:
    """A nota que espera cumprimento — a mais nova, se houver mais de uma. SÓ LÊ."""
    return banco(con).um(
        """SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=%s AND situacao='ABERTA'
           ORDER BY numero DESC, id DESC LIMIT 1""", (int(protocolo_id),))


def exigencias_da(nota: Any) -> list[str]:
    """As exigências gravadas, como lista — vazia quando a nota é o arquivo anexado."""
    try:
        lista = json.loads(nota["exigencias"] or "[]")
    except (TypeError, ValueError):
        return [nota["exigencias"]] if nota["exigencias"] else []
    return [str(e) for e in lista] if isinstance(lista, list) else [str(lista)]


def anexos_da_nota(documentos: Iterable[Any], numero: int) -> list[Any]:
    """Os arquivos daquela nota, entre os documentos do protocolo. SÓ LÊ."""
    marca = descricao_da_nota(numero)
    return [d for d in documentos
            if d["documento_tipo"] == NOTA and (d["description"] or "").startswith(marca)
            and (d["description"] or "")[len(marca):len(marca) + 1] in ("", ":", " ")]


def marcar_anexo(con: Any, protocolo_id: int, anexo_id: int, *, tipo: str,
                 descricao: str | None) -> None:
    """Grava o tipo (e a descrição) de um anexo DESTE protocolo. GRAVA."""
    if tipo not in ROTULO_DO_TIPO:
        raise NotaError(f"«{tipo}» não é um tipo de documento que eu conheça.")
    feitos = banco(con).escrever(
        """UPDATE attachments SET documento_tipo=%s, description=%s
           WHERE id=%s AND entity_type='RI_PROTOCOLO' AND entity_id=%s""",
        (tipo, descricao, int(anexo_id), int(protocolo_id)))
    if feitos == 0:
        raise NotaError(f"O anexo {anexo_id} não é deste protocolo.")


def _com_a_descricao_antiga(prefixo: str, antiga: str | None) -> str:
    antiga = (antiga or "").strip()
    if not antiga or antiga.startswith(prefixo):
        return antiga or prefixo
    return f"{prefixo}: {antiga}"


def emitir(con: Any, p: Any, *, exigencias: list[str], fundamentacao: str | None,
           data_nota: str, quem: str | None, usuario_id: int | None, agora: str,
           anexos: Iterable[int] = ()) -> dict:
    """Emite a nota devolutiva do protocolo `p`. GRAVA — chame dentro da transação.

    Numera, passa o protocolo a DEVOLVIDO, grava a qualificação negativa e, se o
    arquivo da nota veio junto, marca-o como a nota. Sem exigência digitada e
    sem arquivo não há nota: seria um número sem conteúdo.
    """
    exigencias = [e.strip() for e in exigencias if e and e.strip()]
    anexos = [int(a) for a in anexos]
    if not exigencias and not anexos:
        raise NotaError("Informe ao menos uma exigência (uma por linha) ou anexe o arquivo "
                        "da nota devolutiva.")
    motivo = por_que_nao_emite(p)
    if motivo:
        raise NotaError(motivo)
    bd = banco(con)
    bd.travar("ri_notas_devolutivas.numero")
    ultimo = bd.valor("SELECT MAX(numero) AS n FROM ri_notas_devolutivas WHERE protocolo_id=%s",
                      (int(p["id"]),))
    numero = int(ultimo or 0) + 1
    nota_id = int(bd.escrever(
        """INSERT INTO ri_notas_devolutivas
           (protocolo_id, numero, data_nota, exigencias, fundamentacao,
            prazo_ate, situacao, emitida_em, emitida_por)
           VALUES (%s,%s,%s,%s,%s,%s,'ABERTA',%s,%s) RETURNING id""",
        (int(p["id"]), numero, data_nota or agora[:10],
         json.dumps(exigencias, ensure_ascii=False), (fundamentacao or "").strip() or None,
         p["data_limite"], agora, usuario_id))[0]["id"])
    bd.escrever("UPDATE ri_protocolos SET situacao='DEVOLVIDO' WHERE id=%s", (int(p["id"]),))
    # A NOTA É A QUALIFICAÇÃO NEGATIVA, e as duas nascem juntas: nota sem esta
    # linha faria o painel dos pedidos dizer «a qualificar» de um título devolvido.
    PED.registrar_negativa(con, int(p["id"]), nota_id=nota_id,
                           fundamentacao=(fundamentacao or "").strip() or None,
                           quem=quem, usuario_id=usuario_id, agora=agora)
    for anexo in anexos:
        antiga = bd.valor("SELECT description AS d FROM attachments WHERE id=%s", (anexo,))
        marcar_anexo(con, int(p["id"]), anexo, tipo=NOTA,
                     descricao=_com_a_descricao_antiga(descricao_da_nota(numero), antiga))
    return {"nota_id": nota_id, "numero": numero, "exigencias": len(exigencias),
            "anexos": anexos}


# A DATA DO REINGRESSO DECIDE A PRIORIDADE, e por isso não é livre (revisão de
# segurança de 26/10/2026, PR #14). Ela vem do formulário, e dentro ou fora da
# vigência da prenotação é ela quem diz: dentro, o título volta ao MESMO número
# de ordem (LRP art. 186; CN-MA art. 44); fora, a nota fica «fora do prazo» e o
# título precisa de protocolo novo, com emolumentos. Sem limite, a prenotação
# vencida em 17/11 e reapresentada em 25/11 com a data «10/11» guardaria a
# prioridade antiga sem ninguém ver.
#
# As réguas, num lugar só (as três portas chamam esta função):
#   · nem antes da nota, nem depois de hoje — o reingresso é um fato que já
#     aconteceu, e depois de a nota existir;
#   · DATA PASSADA QUE SALVA A PRIORIDADE (a prenotação já venceu hoje, e a data
#     informada cai dentro da vigência) SÓ O OFICIAL REGISTRA, e com a
#     observação dizendo de onde vem a data. É a opção mais fechada: o caso
#     legítimo existe (o título voltou no prazo e o lançamento atrasou), mas
#     decidir que ele voltou no prazo é decidir a prioridade, e isso é de quem
#     responde pela serventia. O escrevente, nesse caso, registra a data de hoje
#     — e a nota fica fora do prazo, que é o que o sistema sabe.
PAPEIS_QUE_RETROAGEM = ("ADMIN",)
MINIMO_DA_JUSTIFICATIVA = 10


def _br(dia: str) -> str:
    return f"{dia[8:10]}/{dia[5:7]}/{dia[:4]}" if len(dia) >= 10 else dia


def _campo(linha: Any, chave: str) -> Any:
    try:
        return linha[chave]
    except (KeyError, IndexError):
        return None


def conferir_data_do_reingresso(nota: Any, p: Any, *, quando: str, hoje: str,
                                papel: str | None = None,
                                observacao: str | None = None) -> str:
    """A data do reingresso conferida (AAAA-MM-DD), ou NotaError. SÓ CONFERE."""
    from datetime import date
    try:
        data = date.fromisoformat(str(quando or "").strip()[:10]).isoformat()
    except ValueError:
        raise NotaError("A data do reingresso não é uma data válida. Informe o dia em "
                        "que o interessado trouxe o título de volta.") from None
    hoje = str(hoje)[:10]
    if data > hoje:
        raise NotaError("A data do reingresso não pode ser depois de hoje: o reingresso "
                        "é o dia em que o título voltou ao balcão.")
    inicio = str(_campo(nota, "data_nota") or "")[:10] or         str(_campo(nota, "emitida_em") or "")[:10]
    if inicio and data < inicio:
        raise NotaError(f"A data do reingresso ({_br(data)}) é anterior à própria nota "
                        f"devolutiva nº {nota['numero']} ({_br(inicio)}). Confira a data.")
    limite = str(p["data_limite"] or "")[:10]
    salva_a_prioridade = (not PRAZO.suspensa(p) and bool(limite)
                          and data <= limite < hoje)
    if salva_a_prioridade:
        if (papel or "").upper() not in PAPEIS_QUE_RETROAGEM:
            raise NotaError(
                f"A prenotação venceu em {_br(limite)}. Registrar o reingresso em {_br(data)} "
                "manteria a prioridade do título (LRP art. 186; CN-MA art. 44) — e isso "
                "só o oficial registra, na tela da nota, dizendo na observação de onde "
                "vem a data. Se o título voltou hoje, registre a data de hoje: a nota "
                "fica fora do prazo e o título precisa de protocolo novo.")
        letras = sum(1 for ch in (observacao or "") if ch.isalnum())
        if letras < MINIMO_DA_JUSTIFICATIVA:
            raise NotaError(
                f"A prenotação venceu em {_br(limite)} e o reingresso está sendo registrado "
                f"em {_br(data)}, o que mantém a prioridade do título. Escreva na observação "
                "de onde vem essa data (o recibo de entrega, o livro de protocolo) — ela "
                "fica no rastro.")
    return data


def reingresso(con: Any, nota: Any, p: Any, *, quando: str, observacao: str | None,
               hoje: str, papel: str | None = None,
               anexos: Iterable[int] = ()) -> bool:
    """Registra o reingresso do título com as exigências cumpridas. GRAVA.

    Devolve se foi dentro da vigência da prenotação (CN-MA, art. 44): dentro,
    o título volta ao MESMO protocolo; fora, a nota fica «fora do prazo» e é
    preciso protocolo novo, com os emolumentos correspondentes. A data passa
    antes por `conferir_data_do_reingresso` (revisão de segurança de 26/10).
    """
    if nota["situacao"] != "ABERTA":
        raise NotaError(f"A nota nº {nota['numero']} não está aguardando cumprimento.")
    quando = conferir_data_do_reingresso(nota, p, quando=quando, hoje=hoje, papel=papel,
                                         observacao=observacao)
    dentro = PRAZO.suspensa(p) or (bool(p["data_limite"]) and quando <= p["data_limite"])
    bd = banco(con)
    bd.escrever("""UPDATE ri_notas_devolutivas SET situacao=%s, data_reingresso=%s,
                   observacao_reingresso=%s WHERE id=%s""",
                ("CUMPRIDA" if dentro else "FORA_DO_PRAZO", quando,
                 (observacao or "").strip() or None, int(nota["id"])))
    if dentro:
        bd.escrever("UPDATE ri_protocolos SET situacao='ABERTO', data_reingresso=%s WHERE id=%s",
                    (quando, int(p["id"])))
    for anexo in anexos:
        antiga = bd.valor("SELECT description AS d FROM attachments WHERE id=%s", (int(anexo),))
        marcar_anexo(con, int(p["id"]), int(anexo), tipo=CUMPRIMENTO,
                     descricao=_com_a_descricao_antiga(descricao_do_cumprimento(nota["numero"]),
                                                       antiga))
    return dentro

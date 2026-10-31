# -*- coding: utf-8 -*-
"""A ponte entre o título desta casa e a Intimação Digital.

**ESTE MÓDULO NÃO INTIMA NINGUÉM NO LIVRO.** Ele monta o que a Central pede,
manda quando alguém clica, e guarda o que ela responde. **A intimação que vale
é o ato que o oficial lavra** — `protesto.lancar_intimacao` —, e é ele que faz
o protesto poder sair. O que a plataforma chama de `INTIMADO` é ciência do
devedor, e entra aqui como informação, nunca como ato.

    É a regra do CNIB pela sexta vez: avisar e preparar; quem assina decide.

**O QUE A CENTRAL EXIGE: a chave de 23 dígitos.** Ela vem do XML diário do
CENPROT, e a tela «Chave do CENPROT» a grava.

> **ESTE PARÁGRAFO DIZIA QUE ESTA CASA NÃO TEM A CHAVE, E ISSO ENVELHECEU —
> corrigido em 14/10/2026, pelo relato do oficial: *«diz erroneamente na
> intimação digital que não tem chave da CENPROT»*.** Estava escrito «medido
> em 03/09/2026: vazia em 1.366 de 1.366». Medido de novo em 14/10/2026 no
> banco da produção (só leitura): **1.261 de 1.409** títulos têm a chave, todas
> com 23 dígitos. E a tela errava por outro caminho, que é o que importa: o
> quadro contava como «sem a chave» **todo** título sem ela — 148, quase todos
> pagos (108), desistidos (23) ou cancelados (5), que não vão à Intimação
> Digital de jeito nenhum. Entre os que **poderiam** ir (31: 30 apontados e 1
> intimado), faltavam 11. A régua agora mede só os que poderiam ir, e diz
> quais são os que faltam — `quantos_podem_ir`.

**O QUE VAI E O QUE FICA**
    Vão os títulos **apontados e ainda não intimados**, com chave. Não vão os
    pagos, os retirados, os já protestados — e **não vão os sustados**, que é o
    caso mais grave: `protesto` recusa pagar, protestar e retirar um título
    sustado, e deixar a mensageria correndo cobraria justamente quem o juiz
    mandou parar.
"""
from __future__ import annotations

import json
import sqlite3

from bd_nativo import banco
from typing import Any

import centrais_cred as CRED
import protesto_cenprot as PC
import resolve_api as API


class IntimacaoDigitalError(ValueError):
    """Erro de regra, com frase pronta para o balcão."""


# O QUE A CENTRAL CHAMA DE CADA COISA, do nosso lado.
#
#   **`especieTitulo` vai como a casa a guarda.** O contrato não declara enum
#   para ela — os exemplos trazem «DUPLICATA», «CDA», «CBI», «DMI» —, e
#   traduzir para uma lista que ninguém publicou seria inventar de-para.
ORIGEM_DO_ENDERECO = "CARTORIO"


def _reais(centavos: Any) -> float:
    """Centavos inteiros viram reais com duas casas. Só calcula.

    **A Central quer `number` em reais** (`2255.39`), e esta casa guarda
    **centavos inteiros**. Mandar o inteiro faria a intimação cobrar cem vezes
    o valor — e o devedor receberia isso escrito, com o nome da serventia em
    cima.
    """
    try:
        return round(int(centavos or 0) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _pessoa(nome: Any, documento: Any = "", *, enderecos: list | None = None,
            tipo: str = "", com_tipo: bool = False) -> dict:
    """A pessoa no formato da Central.

    **`tipoDocumento` SÓ NO DEVEDOR** — medido na homologação em 13/10/2026: a
    Central recusou o lote com `credor.tipoDocumento` «não é permitida»
    (`whitelistValidation`); no contrato o campo existe só no devedor. Credor,
    cedente e apresentante vão com nome e documento, e nada a mais.
    """
    fora: dict[str, Any] = {"nome": str(nome or "").strip()}
    doc = PC.so_digitos(documento)
    if doc:
        fora["documento"] = doc
        if com_tipo:
            fora["tipoDocumento"] = tipo or ("CPF" if len(doc) == 11 else "CNPJ")
    if enderecos:
        fora["enderecos"] = enderecos
    return fora


def _endereco(linha: Any, prefixo: str = "") -> list[dict]:
    """O endereço no formato da Central, ou lista vazia.

    **Os quatro campos são obrigatórios juntos** (`endereco`, `cep`, `cidade`,
    `uf`): um endereço pela metade a Central recusa, e recusa o lote inteiro.
    Por isso, faltando qualquer um, não se manda endereço nenhum — e quem
    decide o que fazer com isso é a conferência, que diz o que falta.
    """
    def campo(nome: str) -> str:
        chave = f"{prefixo}{nome}" if prefixo else nome
        try:
            return str(linha[chave] or "").strip()
        except (KeyError, IndexError, TypeError):
            return ""

    rua, cep = campo("endereco"), PC.so_digitos(campo("cep"))
    cidade, uf = campo("cidade"), campo("uf")
    if not (rua and cep and cidade and uf):
        return []
    bairro = campo("bairro")
    return [{"endereco": f"{rua}, {bairro}" if bairro else rua,
             "cep": cep, "cidade": cidade, "uf": uf.upper()[:2],
             "origem": ORIGEM_DO_ENDERECO}]


def montar(titulo: dict, devedor: dict, *, identificador: str,
           valor_a_pagar_centavos: Any = None) -> dict:
    """A intimação como a Central a quer. Só calcula — não manda nada.

    **`valorAPagar` NÃO É O VALOR DO TÍTULO, e o contrato não diz a fórmula.**
    Ele é «o valor total a ser pago pelo devedor», que nesta casa é a dívida
    mais a retirada — e a retirada `protesto_cenprot.precos_do_titulo` calcula
    (166 de 173 no centavo). Quem passa o número é quem chama, porque é
    **dinheiro que o devedor paga**: um valor derivado sem ninguém conferir é
    o tipo de engano que só aparece no balcão.

    Sem ele, vai o valor do título — que é o que se sabe, e nunca zero.
    """
    valor = titulo.get("valor_centavos")
    saldo = titulo.get("saldo_centavos")
    a_pagar = valor_a_pagar_centavos if valor_a_pagar_centavos else valor

    fora = {
        "identificador": str(identificador or "").strip(),
        "credor": _pessoa(titulo.get("cedente_nome"),
                          titulo.get("cedente_documento"),
                          enderecos=_endereco(titulo, "cedente_")),
        "devedor": _pessoa(devedor.get("nome"),
                           devedor.get("documento_numero"),
                           enderecos=_endereco(devedor), com_tipo=True),
        "titulo": {
            "valorDivida": _reais(saldo or valor),
            "valorTitulo": _reais(valor),
            "valorAPagar": _reais(a_pagar),
            "numeroTitulo": str(titulo.get("numero_titulo") or "").strip(),
            "especieTitulo": str(titulo.get("especie") or "").strip(),
            "dataVencimento": str(titulo.get("data_vencimento") or "")[:10],
            "dataEmissao": str(titulo.get("data_emissao") or "")[:10],
            "numeroProtocolo": str(titulo.get("protocolo") or "").strip(),
            "nrChave": PC.so_digitos(titulo.get("chave_cenprot")),
        },
    }
    # O APRESENTANTE SÓ VAI COM DOCUMENTO — medido na homologação em
    # 13/10/2026: a Central recusou o lote inteiro com «Body inválido», e o
    # contrato (`/api/batches/json`) exige `nome` E `documento` no apresentante.
    # Esta casa não tem o documento dele (a remessa da CRA traz só o código e o
    # nome), e o apresentante é OPCIONAL no lote: vai inteiro, ou não vai.
    apresentante = _pessoa(titulo.get("apresentante_nome"),
                           titulo.get("apresentante_documento"))
    if apresentante.get("nome") and apresentante.get("documento"):
        fora["apresentante"] = apresentante
    return fora


# ------------------------------------------------------------ quem pode ir


# **AS SITUAÇÕES QUE NÃO VÃO, e cada uma protege alguém.** Um título pago ou
# retirado não se cobra; um protestado já passou da intimação; e o **sustado**
# é o que mais importa — o § 1º do art. 17 da Lei 9.492/1997 diz que ele só se
# paga, protesta ou retira com autorização judicial, e mensageria correndo é
# cobrança de quem o juiz mandou parar.
SITUACOES_QUE_NAO_VAO: frozenset[str] = frozenset({
    "PAGO", "RETIRADO", "PROTESTADO", "CANCELADO", "DESISTIDO", "SUSTADO",
    "DEVOLVIDO",
})


def _classificar(item: dict) -> dict:
    """Diz se o título pode ir e, se não, por quê. Só calcula.

    **A CHAVE SÓ É MOTIVO DE QUEM PODERIA IR — correção de 14/10/2026.** Até
    13/10 todo título sem chave levava «falta a chave do CENPROT», inclusive
    o pago, o desistido e o cancelado — e o quadro do alto somava esses todos
    como se fossem intimações travadas pela chave. Para quem já não vai pela
    situação, a chave não muda nada, e dizer que falta é afirmar um problema
    que não existe. E a chave que existe com o tamanho errado é outra coisa,
    com outra frase: ela foi gravada, e gravada torta.
    """
    situacao = str(item.get("situacao") or "").strip().upper()
    chave = PC.so_digitos(item.get("chave_cenprot"))
    porques = []
    if situacao in SITUACOES_QUE_NAO_VAO:
        porques.append(f"o título está {situacao.lower()}")
    if not str(item.get("devedor_nome") or "").strip():
        porques.append("o título está sem devedor")
    elegivel = not porques
    falta_chave = ""
    if elegivel and len(chave) != API.TAMANHO_DA_CHAVE:
        if not chave:
            falta_chave = ("falta a chave do CENPROT (carregue o XML diário "
                           "em Protesto → Chave do CENPROT)")
        else:
            falta_chave = (f"a chave do CENPROT gravada tem {len(chave)} "
                           f"dígitos, e a Central exige "
                           f"{API.TAMANHO_DA_CHAVE} (carregue de novo o XML "
                           f"diário em Protesto → Chave do CENPROT)")
        porques.append(falta_chave)
    item["elegivel"] = elegivel
    item["falta_chave"] = falta_chave
    item["pode_ir"] = not porques
    item["porque_nao"] = "; ".join(porques)
    return item


def situacao_do_titulo(titulo: dict) -> dict:
    """Se este título pode ir à Intimação Digital e, se não, por quê. Só calcula.

    A porta pública de `_classificar`, para o aviso que não foi entregue
    perguntar a mesma régua desta tela (15/10/2026) — duas réguas para «pode
    ir à Resolve?» divergiriam no primeiro conserto.
    """
    return _classificar(dict(titulo))


def candidatos(con: sqlite3.Connection, *, limite: int = 200) -> list[dict]:
    """Os títulos que poderiam ser intimados pela Central. SÓ LÊ.

    **Quem não tem chave aparece com o motivo, e não some.** Lista que esconde
    o que não pode ir faz o balcão procurar o título e não achar — e o conserto
    (carregar o XML do CENPROT) é de uma tela só.

    **OS QUE ESTÃO EM SITUAÇÃO DE IR VÊM PRIMEIRO** (14/10/2026). A lista
    trazia os 200 mais novos em qualquer situação, e na produção eram 150
    protestados para 20 que podiam ir — os apontados antigos, justamente os
    que esperam a chave, ficavam fora da lista.
    """
    que_nao_vao = sorted(SITUACOES_QUE_NAO_VAO)
    marcas = ",".join("%s" for _ in que_nao_vao)
    linhas = banco(con).ler(
        f"""SELECT t.*, d.nome AS devedor_nome,
                   d.documento_numero AS devedor_documento
              FROM pt_titulos t
              LEFT JOIN pt_devedores d ON d.titulo_id = t.id
             ORDER BY CASE WHEN UPPER(COALESCE(t.situacao, ''))
                                IN ({marcas}) THEN 1 ELSE 0 END,
                      t.id DESC, d.id
             LIMIT %s""", [*que_nao_vao, int(limite)])
    return [_classificar(dict(linha)) for linha in linhas]


# QUANTOS TÍTULOS SEM CHAVE A TELA LISTA PELO NOME. O número vai inteiro no
# quadro; a lista para aqui para a tela não virar o livro.
LISTA_DOS_SEM_CHAVE = 50


def quantos_podem_ir(con: sqlite3.Connection) -> dict:
    """O quadro do alto da tela. SÓ LÊ — e conta o motivo de quem não vai.

    **MEDE ENTRE OS QUE PODERIAM IR, e diz quais faltam** (14/10/2026). Os
    números são: todos os títulos; os que estão em situação de ir (`elegiveis`
    — não pagos, retirados, protestados, cancelados, desistidos nem sustados,
    e com devedor); entre esses, os que podem ir e os que estão sem a chave,
    **com a lista deles** (protocolo, título, devedor e o motivo).

    Um devedor por título na conta: a junção com `pt_devedores` repetiria o
    título que tem dois devedores, e o número deixaria de ser de títulos.
    """
    linhas = banco(con).ler(
        """SELECT t.id, t.situacao, t.chave_cenprot, t.protocolo,
                  t.numero_titulo,
                  (SELECT d.nome FROM pt_devedores d
                    WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1)
                      AS devedor_nome
             FROM pt_titulos t
            ORDER BY t.id DESC""")
    todos = [_classificar(dict(linha)) for linha in linhas]
    elegiveis = [x for x in todos if x["elegivel"]]
    sem_chave = [x for x in elegiveis if x["falta_chave"]]
    return {"titulos": len(todos),
            "elegiveis": len(elegiveis),
            "podem_ir": sum(1 for x in todos if x["pode_ir"]),
            "sem_chave": len(sem_chave),
            "sem_chave_lista": [
                {"id": x["id"], "protocolo": x.get("protocolo"),
                 "numero_titulo": x.get("numero_titulo"),
                 "devedor_nome": x.get("devedor_nome"),
                 "situacao": x.get("situacao"),
                 "motivo": x["falta_chave"]}
                for x in sem_chave[:LISTA_DOS_SEM_CHAVE]],
            "fora_pela_situacao": len(todos) - len(elegiveis),
            "ja_enviados": _quantos_enviados(con)}


def _quantos_enviados(con: sqlite3.Connection) -> int:
    """As intimações mandadas em PRODUÇÃO — as de homologação e testes que
    ficaram no banco não contam desde 14/10/2026."""
    try:
        return int(banco(con).valor(
            "SELECT COUNT(*) AS n FROM rs_intimacoes WHERE ambiente = %s",
            (CRED.PRODUCAO,)))
    except sqlite3.Error:
        return 0


# ---------------------------------------------------------------- o envio


def identificador_do_titulo(titulo: dict, *, quantas_ja: int = 0) -> str:
    """O nosso número lá dentro. Só calcula.

    **É o protocolo desta casa mais a ordem da tentativa**, e não só o `id`:
    o mesmo título pode ser intimado de novo, e a Central guarda as duas com o
    mesmo identificador se ele não mudar — o que faria a busca por ele devolver
    as duas sem dizer qual é qual.
    """
    base = str(titulo.get("protocolo") or "").strip() or f"T{titulo.get('id')}"
    return f"{base}-{int(quantas_ja) + 1}"


def enviar(db, titulo_ids: Any, *, ambiente: Any = None, quem: str = "",
           pasta=None, valores_a_pagar: dict | None = None) -> dict:
    """Manda os títulos escolhidos à Intimação Digital. **ESCREVE NA CENTRAL.**

    **RECEBE `db`, E A CHAMADA É FORA DA TRANSAÇÃO** — a regra do selador. E o
    registro do que subiu se grava **depois** da resposta: gravar antes faria a
    lista dizer «intimado» num dia em que a internet caiu.
    """
    # SÓ PRODUÇÃO desde 14/10/2026 (até 13/10 o padrão daqui era `TESTES`).
    qual = CRED.ambiente_de_uso(CRED.RESOLVE, ambiente)
    ids = [int(x) for x in (titulo_ids or []) if str(x).strip()]
    if not ids:
        raise IntimacaoDigitalError(
            "Nenhum título foi marcado. Marque os que devem ser intimados.")

    with db.transaction() as con:
        bd = banco(con)
        marcadores = ",".join("%s" for _ in ids)
        linhas = bd.ler(
            f"""SELECT t.*, d.nome AS devedor_nome,
                       d.documento_numero AS devedor_documento,
                       d.endereco AS d_endereco, d.bairro AS d_bairro,
                       d.cep AS d_cep, d.cidade AS d_cidade, d.uf AS d_uf
                  FROM pt_titulos t
                  LEFT JOIN pt_devedores d ON d.titulo_id = t.id
                 WHERE t.id IN ({marcadores})
                 ORDER BY t.id, d.id""", ids)
        ja = {int(r["titulo_id"]): int(r["n"]) for r in bd.ler(
            f"""SELECT titulo_id, COUNT(*) AS n FROM rs_intimacoes
                 WHERE ambiente = %s AND titulo_id IN ({marcadores})
                 GROUP BY titulo_id""", [qual, *ids])}

    if not linhas:
        raise IntimacaoDigitalError("Não achei os títulos marcados.")

    lote, por_identificador = [], {}
    for linha in linhas:
        titulo = dict(linha)
        devedor = {"nome": titulo.get("devedor_nome"),
                   "documento_numero": titulo.get("devedor_documento"),
                   "endereco": titulo.get("d_endereco"),
                   "bairro": titulo.get("d_bairro"),
                   "cep": titulo.get("d_cep"),
                   "cidade": titulo.get("d_cidade"),
                   "uf": titulo.get("d_uf")}
        ident = identificador_do_titulo(
            titulo, quantas_ja=ja.get(int(titulo["id"]), 0))
        corpo = montar(titulo, devedor, identificador=ident,
                       valor_a_pagar_centavos=(valores_a_pagar or {}).get(
                           int(titulo["id"])))
        lote.append(corpo)
        por_identificador[ident] = (int(titulo["id"]), titulo)

    # **A CONFERÊNCIA É ANTES DA REDE**, e a frase diz qual item falhou.
    API.conferir_lote(lote)
    resposta = API.criar_lote(lote, qual, pasta=pasta)

    lote_id = str((resposta or {}).get("id") or "")
    devolvidas = {str(x.get("identificador") or ""): str(x.get("_id") or "")
                  for x in ((resposta or {}).get("intimacoes") or [])}

    agora = db.now()
    texto = json.dumps(resposta, ensure_ascii=False)[:4000]
    gravadas = 0
    with db.transaction() as con:
        bd = banco(con)
        for corpo in lote:
            ident = corpo["identificador"]
            titulo_id, titulo = por_identificador[ident]
            bd.escrever(
                """INSERT INTO rs_intimacoes
                       (titulo_id, ambiente, lote_id, intimacao_id,
                        identificador, teor, resumo, enviada_em, enviada_por,
                        resposta)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (titulo_id, qual, lote_id or None,
                 devolvidas.get(ident) or None, ident,
                 json.dumps(corpo, ensure_ascii=False),
                 _resumo(corpo, titulo), agora, quem or None, texto))
            if bd.linhas_afetadas:
                gravadas += 1
    return {"ambiente": qual, "mandadas": len(lote), "gravadas": gravadas,
            "lote_id": lote_id, "resposta": resposta}


def _resumo(corpo: dict, titulo: dict) -> str:
    devedor = (corpo.get("devedor") or {}).get("nome") or "(sem devedor)"
    t = corpo.get("titulo") or {}
    return (f"{devedor} · título {t.get('numeroTitulo') or '-'} · "
            f"R$ {t.get('valorAPagar') or 0:.2f} · "
            f"protocolo {titulo.get('protocolo') or '-'}")


# ------------------------------------------------------------ o que voltou


def abertas(con: sqlite3.Connection, *, ambiente: Any = None,
            limite: int = 200) -> list[dict]:
    """As intimações que esta casa mandou. SÓ LÊ."""
    onde, args = "", []
    if ambiente:
        onde = "WHERE i.ambiente = %s"
        args.append(str(ambiente).strip().upper())
    linhas = banco(con).ler(
        f"""SELECT i.*, t.numero_titulo, t.protocolo, t.situacao
              FROM rs_intimacoes i
              JOIN pt_titulos t ON t.id = i.titulo_id
              {onde}
             ORDER BY i.id DESC LIMIT %s""", [*args, int(limite)])
    return [dict(x) for x in linhas]


def uma(con: sqlite3.Connection, intimacao_id: int) -> dict | None:
    """Uma intimação desta casa, com o título ao lado. SÓ LÊ."""
    linha = banco(con).um(
        """SELECT i.*, t.numero_titulo, t.protocolo, t.situacao,
                  t.valor_centavos, d.nome AS devedor_nome
             FROM rs_intimacoes i
             JOIN pt_titulos t ON t.id = i.titulo_id
             LEFT JOIN pt_devedores d ON d.titulo_id = t.id
            WHERE i.id = %s
            ORDER BY d.id LIMIT 1""", (int(intimacao_id),))
    if linha is None:
        return None
    fora = dict(linha)
    for campo in ("teor", "historico", "resposta"):
        try:
            fora[f"{campo}_aberto"] = json.loads(fora.get(campo) or "null")
        except ValueError:
            fora[f"{campo}_aberto"] = None
    return fora


# **AS TRÊS COISAS QUE A CASA DIZ À CENTRAL, e cada uma existe porque o fato
# aconteceu AQUI e ela não tem como saber.**
#
#   `paga` — o devedor pagou no balcão, e sem isto a plataforma continua
#   cobrando quem já pagou.
#   `intimada` — a intimação aconteceu FORA dela, em mãos ou por edital; sem
#   isto ela segue mandando mensagem a quem já foi intimado.
#   `cancelada` — o título foi retirado, desistido ou **sustado**; deixar a
#   mensageria correndo sobre um sustado cobra quem o juiz mandou parar.
AVISOS_A_CENTRAL: dict[str, tuple] = {
    "paga": (API.marcar_paga, "PAGO",
             "que o título foi pago"),
    "intimada": (API.marcar_intimada, "INTIMADO",
                 "que a intimação já foi cumprida por outro caminho"),
    "cancelada": (API.cancelar_intimacao, "CANCELADO",
                  "que a intimação deve sair da fila de envio"),
}


def avisar(db, intimacao_id: int, qual: str, *, quem: str = "",
           pasta=None) -> dict:
    """Diz à Central o que aconteceu aqui. **ESCREVE NA CENTRAL.**

    **Não lavra ato nenhum desta casa** — o pagamento, a intimação e a baixa se
    lavram na ficha do título, com selo, custas e lugar no livro. Isto é só o
    aviso a quem está mandando as mensagens.
    """
    acao = str(qual or "").strip().lower()
    if acao not in AVISOS_A_CENTRAL:
        raise IntimacaoDigitalError(
            f"Não sei avisar «{acao}». Sei: "
            + ", ".join(AVISOS_A_CENTRAL) + ".")
    with db.connect() as con:
        item = uma(con, intimacao_id)
    if item is None:
        raise IntimacaoDigitalError("Essa intimação não existe nesta casa.")
    if not str(item.get("intimacao_id") or "").strip():
        raise IntimacaoDigitalError(
            "Esta intimação não tem número na Central — ela não chegou a ser "
            "aceita lá, e não há o que avisar.")

    funcao, estado, o_que = AVISOS_A_CENTRAL[acao]
    # A INTIMAÇÃO DE HOMOLOGAÇÃO OU DE TESTES NÃO SE AVISA MAIS (14/10/2026):
    # ela fica como histórico, e a recusa diz por quê.
    onde = CRED.ambiente_de_uso(CRED.RESOLVE, item["ambiente"])
    resposta = funcao(item["intimacao_id"], onde, pasta=pasta)

    agora = db.now()
    with db.transaction() as con:
        banco(con).escrever(
            """UPDATE rs_intimacoes SET estado = %s, estado_em = %s
                WHERE id = %s""", (estado, agora, int(intimacao_id)))
    return {"id": int(intimacao_id), "estado": estado, "o_que": o_que,
            "resposta": resposta}


def atualizar_estados(db, *, ambiente: Any = None, quem: str = "",
                      pasta=None, limite: int = 100) -> dict:
    """Pergunta à Central o estado de cada intimação aberta. SÓ LÊ LÁ.

    **Não muda ato nenhum desta casa**: grava o que a Central respondeu, e é o
    oficial quem decide o que fazer com isso — lavrar a intimação, mandar ao
    edital, ou esperar.
    """
    # SÓ PRODUÇÃO desde 14/10/2026 (até 13/10 o padrão daqui era `TESTES`).
    qual = CRED.ambiente_de_uso(CRED.RESOLVE, ambiente)
    with db.connect() as con:
        fila = banco(con).ler(
            """SELECT id, intimacao_id, identificador FROM rs_intimacoes
                WHERE ambiente = %s AND COALESCE(intimacao_id,'') <> ''
                ORDER BY COALESCE(estado_em,'') ASC, id LIMIT %s""",
            (qual, int(limite)))

    olhadas, mudaram, falhas = 0, 0, []
    agora = db.now()
    for item in fila:
        try:
            resposta = API.intimacao(item["intimacao_id"], qual, pasta=pasta)
        except API.ResolveError as erro:
            falhas.append({"id": item["id"], "porque": str(erro)})
            continue
        olhadas += 1
        estado = str((resposta or {}).get("status") or "").strip().upper()
        with db.transaction() as con:
            bd = banco(con)
            bd.escrever(
                """UPDATE rs_intimacoes
                      SET estado = %s, estado_em = %s, historico = %s
                    WHERE id = %s AND COALESCE(estado,'') <> %s""",
                (estado or None, agora,
                 json.dumps(resposta, ensure_ascii=False)[:4000],
                 item["id"], estado or ""))
            if bd.linhas_afetadas:
                mudaram += 1
    return {"ambiente": qual, "olhadas": olhadas, "mudaram": mudaram,
            "falhas": falhas}

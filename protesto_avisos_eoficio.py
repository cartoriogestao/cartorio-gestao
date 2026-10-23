"""Os avisos e os editais do E-Ofício, trazidos para o Cartório Gestão — 21/10/2026.

POR QUE ISTO EXISTE
    Ordem do oficial: «confira e mande todos os dados do E-Ofício de protesto
    para o Cartório Gestão, desde que paramos de utilizar na semana passada».
    Medido no banco vivo do E-Ofício em 21/10/2026: o último movimento foi em
    13/10. A carga do Protesto trazia os TÍTULOS, as PESSOAS e a vida do título
    (apontamento, intimação, protesto, pagamento, cancelamento) — e NÃO trazia
    os AVISOS (`tbBoletoApto`, 1.678) nem os EDITAIS (`tbEdital`, 1.109).

    O efeito apareceu no balcão: 18 títulos com aviso na rua pelo E-Ofício (de
    02/10 a 13/10) não apareciam em lugar nenhum para intimação, porque a tela
    dos avisos só lista o que tem aviso NESTE sistema.

COMO O E-OFÍCIO GUARDAVA, MEDIDO NOS 1.678
    bitAtivo = 0                          277  aviso substituído ou cancelado
    bitPublicadoEdital = 1               1.109  não entregue, foi a edital
    bitEntregue = 1, sem edital          ~69   entregue em mãos
    ativo, sem desfecho                   225  na rua (ou o título se resolveu
                                               antes — pago, retirado)
    A TENTATIVA mora em `tbBoletoControleNEntrega`, ligada ao TÍTULO pelo
    protocolo (`strCB_AP`), e não ao aviso — é de lá que sai o motivo
    (`intCodigoMotivoNaoEntrega`, o mesmo catálogo `tbMotivoNEntrega` que este
    sistema usa) e quem recebeu.

O QUE ESTE MÓDULO NÃO FAZ
    Não lavra ato: a intimação de cada título já veio pela carga da vida do
    título, e um aviso importado não intima ninguém. Não toca título nenhum.
    Não reescreve aviso que já está aqui — a chave de origem é
    `tbBoletoApto:<intChave>`, e a segunda rodada não insere nada.

O NÚMERO DO AVISO É O DO EXERCÍCIO DESTE SISTEMA: 1, 2, 3… em cada ano, na
ordem em que o E-Ofício os emitiu, depois dos que já existirem aqui. A
primeira versão usava a chave interna do E-Ofício (`intChave`), e o ensaio
mostrou o preço: o próximo aviso do balcão sairia «182.638/2026». A chave do
E-Ofício e o nosso número do boleto ficam na observação, para quem for
procurar o papel.

NO POSTGRESQL (lote LH07, 21/10/2026)
    O banco da casa fala pelo `bd_nativo`. A carga pega as travas de número
    do aviso e do edital ANTES de ler o que já está aqui — as mesmas de
    `protesto_aviso.emitir` e `publicar_edital` —: com elas, o balcão não tira
    o mesmo número no meio da carga, e duas cargas ao mesmo tempo não inserem
    a mesma chave de origem duas vezes (o índice único parcial recusaria, e a
    carga inteira cairia). O acervo continua sendo o arquivo do E-Ofício, lido
    pelos ajudantes de `acervo_carga` (por nome e sem caixa).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from bd_nativo import banco

ORIGEM = "EOFICIO"
SITUACOES_QUE_AINDA_ESPERAM = ("APONTADO", "INTIMADO")


def _txt(v: Any) -> str:
    return str(v or "").strip()


def _data(v: Any) -> str | None:
    s = _txt(v)
    return s[:10] if len(s) >= 10 else None


def _inteiro(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _titulos_do_eoficio(con: sqlite3.Connection) -> dict[int, dict]:
    """intChave do E-Ofício → o título nesta casa. Só LÊ."""
    saida = {}
    for r in banco(con).ler(
            """SELECT id, origem_chave, situacao, protocolo FROM pt_titulos
                WHERE origem_chave ILIKE 'tbAvisoProtesto:%'
                ORDER BY id"""):
        chave = _inteiro(str(r["origem_chave"]).split(":", 1)[1])
        if chave is not None:
            saida[chave] = {"id": int(r["id"]), "situacao": r["situacao"],
                            "protocolo": r["protocolo"]}
    return saida


def _tentativas(acervo: sqlite3.Connection) -> dict[str, list[dict]]:
    """As tentativas de entrega, por protocolo, da mais nova para a mais velha."""
    import acervo_carga as AC
    saida: dict[str, list[dict]] = {}
    for r in AC._ler_acervo(
            acervo,
            """SELECT strCB_AP, dtmEntrega, intCodigoMotivoNaoEntrega,
                      bitEntregue, strRecebidoPor, strObs
                 FROM tbBoletoControleNEntrega ORDER BY dtmEntrega DESC"""):
        saida.setdefault(_txt(r["strCB_AP"]), []).append(
            {"quando": _data(r["dtmEntrega"]),
             "motivo": _inteiro(r["intCodigoMotivoNaoEntrega"]),
             "entregue": bool(r["bitEntregue"]),
             "recebido_por": _txt(r["strRecebidoPor"]),
             "obs": _txt(r["strObs"])})
    return saida


def _entregadores(acervo: sqlite3.Connection) -> dict[int, str]:
    """Código → nome do entregador. Acervo sem a tabela devolve vazio."""
    import acervo_carga as AC
    if not AC._tem_tabela(acervo, "tbEntregador"):
        return {}
    # Pelas duas primeiras colunas, como sempre se leu: o código e o nome.
    return {_inteiro(r[0]): _txt(r[1])
            for r in acervo.execute("SELECT * FROM tbEntregador ORDER BY 1")}


def situacao_do_aviso(b: dict, titulo: dict) -> tuple[str, str]:
    """(situação aqui, nota) para um aviso do E-Ofício. Só calcula."""
    if not b.get("bitAtivo"):
        return "CANCELADO", "aviso substituído ou cancelado no E-Ofício"
    if b.get("bitPublicadoEdital"):
        return "EDITAL", ""
    if b.get("bitEntregue"):
        return "ENTREGUE", ""
    if titulo["situacao"] in SITUACOES_QUE_AINDA_ESPERAM:
        return "EMITIDO", "aviso emitido pelo E-Ofício e sem desfecho registrado lá"
    return "CANCELADO", (f"título resolvido ({titulo['situacao'].lower()}) "
                         f"antes do desfecho deste aviso no E-Ofício")


def carregar(con: sqlite3.Connection, acervo: sqlite3.Connection, *,
             agora: str) -> dict:
    """Traz os avisos e os editais do E-Ofício. ESCREVE (só pt_avisos e
    pt_editais). Repetível: o que já entrou é contado e não muda."""
    import acervo_carga as AC
    import protesto_aviso as AV
    bd = banco(con)
    # As travas vêm ANTES de qualquer leitura (ver o cabeçalho), e na ordem
    # aviso → edital, que é a ordem em que esta carga grava.
    bd.travar("pt_avisos.numero")
    bd.travar("pt_editais.numero")
    titulos = _titulos_do_eoficio(bd)
    tentativas = _tentativas(acervo)
    entregadores = _entregadores(acervo)
    conta = {"avisos_inseridos": 0, "avisos_ja_estavam": 0,
             "avisos_sem_titulo": 0, "editais_inseridos": 0,
             "editais_ja_estavam": 0, "editais_sem_aviso": 0,
             "por_situacao": {}}

    aviso_do_titulo: dict[int, list[tuple[int, str]]] = {}
    for b in AC._ler_acervo(acervo, "SELECT * FROM tbBoletoApto ORDER BY intChave"):
        chave = _inteiro(b.get("intChaveAP"))
        titulo = titulos.get(chave) if chave is not None else None
        if titulo is None:
            conta["avisos_sem_titulo"] += 1
            continue
        origem_chave = f"tbBoletoApto:{_inteiro(b['intChave'])}"
        ja = bd.um("SELECT id, situacao FROM pt_avisos WHERE origem_chave=%s",
                   (origem_chave,))
        if ja:
            conta["avisos_ja_estavam"] += 1
            aviso_do_titulo.setdefault(titulo["id"], []).append(
                (int(ja["id"]), ja["situacao"]))
            continue
        situacao, nota = situacao_do_aviso(b, titulo)
        protocolo = _txt(b.get("strCB_AP")) or _txt(titulo["protocolo"])
        tent = tentativas.get(protocolo, [])
        nao = next((t for t in tent if not t["entregue"]), None)
        sim = next((t for t in tent if t["entregue"]), None)
        motivo = nao["motivo"] if (situacao == "EDITAL" and nao) else None
        recebido = (sim["recebido_por"] if (situacao == "ENTREGUE" and sim)
                    else None) or None
        emitido = _data(b.get("dtmBoleto")) or _data(b.get("dtmApto")) or agora[:10]
        entrega = (_data(b.get("dtmEntregaConfirmada"))
                   if situacao in ("ENTREGUE", "EDITAL") else None)
        partes = [f"Trazido do E-Ofício (aviso {_inteiro(b['intChave'])}, "
                  f"nosso número {_txt(b.get('strNossoNumeroBoleto')) or '—'})."]
        if nota:
            partes.append(nota[0].upper() + nota[1:] + ".")
        aviso_id = int(bd.escrever(
            """INSERT INTO pt_avisos(titulo_id, numero, ano, devedor_nome,
                   devedor_documento, endereco, bairro, cep, cidade, uf,
                   situacao, emitido_em, emitido_por, entregador, entrega_em,
                   entregue, motivo, recebido_por, observacao, criado_em,
                   origem, origem_chave)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       %s,%s,%s,%s)
               RETURNING id""",
            (titulo["id"], AV.proximo_numero(bd, int(emitido[:4])),
             int(emitido[:4]),
             _txt(b.get("strSacado")) or None,
             "".join(c for c in _txt(b.get("strSacadoDOC")) if c.isdigit()) or None,
             _txt(b.get("strSacadoEND")) or None,
             _txt(b.get("strSacadoBairro")) or None,
             "".join(c for c in _txt(b.get("strSacadoCep")) if c.isdigit()) or None,
             _txt(b.get("strSacadoCidade")) or None,
             _txt(b.get("strSacadoUF")).upper() or None,
             situacao, emitido, _txt(b.get("strUSERID_I")) or None,
             entregadores.get(_inteiro(b.get("intCodigoEntregador"))) or None,
             entrega, 1 if situacao == "ENTREGUE" else 0, motivo, recebido,
             " ".join(partes), agora, ORIGEM, origem_chave))[0]["id"])
        aviso_do_titulo.setdefault(titulo["id"], []).append((aviso_id, situacao))
        conta["avisos_inseridos"] += 1
        conta["por_situacao"][situacao] = conta["por_situacao"].get(situacao, 0) + 1

    por_protocolo = {_txt(t["protocolo"]): t for t in titulos.values()}
    for e in AC._ler_acervo(acervo, "SELECT * FROM tbEdital ORDER BY intchave"):
        origem_chave = f"tbEdital:{_inteiro(e['intchave'])}"
        if bd.um("SELECT 1 AS um FROM pt_editais WHERE origem_chave=%s",
                 (origem_chave,)):
            conta["editais_ja_estavam"] += 1
            continue
        titulo = por_protocolo.get(_txt(e.get("strcb_ap")))
        avisos = aviso_do_titulo.get(titulo["id"], []) if titulo else []
        alvo = ([a for a in avisos if a[1] == "EDITAL"] or avisos)
        publicado = _data(e.get("dtmpublicacao"))
        if not titulo or not alvo or not publicado:
            conta["editais_sem_aviso"] += 1
            continue
        aviso_id = alvo[-1][0]
        # ILIKE, e não LIKE: o LIKE do SQLite não ligava para a caixa.
        ato = bd.um(
            """SELECT id FROM pt_atos WHERE titulo_id=%s AND tipo='INTIMACAO'
                 AND detalhe_json ILIKE '%%EDITAL%%' ORDER BY id DESC LIMIT 1""",
            (titulo["id"],))
        teor = (f"Edital publicado pelo E-Ofício em {publicado[8:10]}/"
                f"{publicado[5:7]}/{publicado[:4]}. O E-Ofício não guardava o "
                f"teor do edital; esta linha registra a publicação.")
        edital_id = int(bd.escrever(
            """INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id,
                   publicado_em, publicado_por, cidade_ibge, teor, hash_teor,
                   ato_id, criado_em, origem, origem_chave)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s)
               RETURNING id""",
            (_inteiro(e["intchave"]), int(publicado[:4]), aviso_id,
             titulo["id"], publicado,
             _txt(e.get("strUSERID_Publicado")) or _txt(e.get("struserid")) or None,
             _txt(e.get("strCodigoCidadeIBGE")) or None, teor,
             int(ato["id"]) if ato else None, agora, ORIGEM,
             origem_chave))[0]["id"])
        bd.escrever("UPDATE pt_avisos SET edital_id=%s WHERE id=%s AND edital_id IS NULL",
                    (edital_id, aviso_id))
        conta["editais_inseridos"] += 1
    return conta

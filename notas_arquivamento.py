"""O selo de arquivamento (13.30) obrigatório na procuração, no substabelecimento
e na revogação — e as folhas arquivadas, contadas dos anexos e confirmadas.

    «colocar o selo de arquivamento como obrigatorio pra ir junto com a
     procuracao»                       — o oficial, 15/10/2026

No mesmo dia ele estendeu a regra ao substabelecimento e à revogação, e
acrescentou a segunda metade: **a quantidade de folhas é a do documento
anexado, e o escrevente confirma**.

O SELO NÃO É NOVO, E ESTE MÓDULO NÃO SELA
    O arquivamento já existia como OPCIONAL na lavratura das Notas
    (`notas_web._selar_arquivamento_das_notas`, item 13.30, caminho
    `/selo/notas/atos-em-geral`, um pedido com `quantidade` = folhas). O que
    muda é que, nestes três tipos, ele deixa de ser escolha. Aqui mora só a
    REGRA: quem é obrigado, quantas folhas os anexos têm, a confirmação, e a
    recusa quando falta uma delas. Quem fala com o aparelho continua sendo a
    rota.

O QUE FOI MEDIDO ANTES (15/10/2026)
    No acervo do E-Ofício, 54 das 213 procurações têm um selo 13.30 próprio
    no mesmo protocolo geral — 52 deles num pedido só, com quantidade de 4 a
    15 folhas, que são as do documento arquivado e não as 2 da procuração
    (`tbProcuracao.intNumeroFolhas` não bate com a quantidade em nenhum dos
    54). Substabelecimento não aparece no acervo, e a única revogação não tem
    selo nenhum. Na produção, 4 das 10 procurações lavradas desde 08/10/2026
    levaram o arquivamento. Era prática da casa, e não regra: a obrigação é
    ordem dele.

A CONTAGEM MORA NUM LUGAR SÓ
    `FONTES_DOS_ANEXOS` é a lista de onde os documentos do ato saem. Hoje é
    uma, e ela já junta os anexos do próprio ato (`NT_ATO`) e os de
    qualificação do Protocolo Geral ligado a ele (relato #135, pela leitura
    de `protocolo_documentos`). Fonte nova entra acrescentando uma função à
    tupla — e a sugestão, a confirmação e a recusa a enxergam sem mais nada.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

CODIGO_DO_ARQUIVAMENTO = "13.30"

# Os que o oficial nomeou: primeiro os três, e no mesmo dia, perguntado, a
# procuração previdenciária e a renúncia, com a mesma regra.
TIPOS_COM_ARQUIVAMENTO_OBRIGATORIO = frozenset(
    {"PROCURACAO", "SUBSTABELECIMENTO", "REVOGACAO",
     "PROCURACAO_PREVIDENCIARIA", "RENUNCIA"})

# PDF conta as páginas; imagem é uma folha cada — regra dele, de 15/10/2026.
EXTENSOES_PDF = frozenset({".pdf"})
EXTENSOES_DE_UMA_FOLHA = frozenset({".jpg", ".jpeg", ".png"})

MENSAGEM_SEM_ANEXO = ("anexe o documento arquivado — o selo de arquivamento "
                      "conta as folhas dele, e sem o documento não há o que "
                      "contar nem o que arquivar.")


class ArquivamentoError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


def arquivamento_obrigatorio(tipo: Any) -> bool:
    """Este tipo de ato de livro exige o selo de arquivamento? So calcula."""
    return str(tipo or "").strip().upper() in TIPOS_COM_ARQUIVAMENTO_OBRIGATORIO


def folhas_validas(bruto: Any) -> int:
    """A quantidade de folhas, ou 0 quando ela não serve. So calcula.

    Inteiro >= 1. Vazio, texto, zero, negativo e «2.5» devolvem 0, e quem chama
    recusa: folha arquivada não se arredonda.
    """
    if isinstance(bruto, bool):
        return 0
    if isinstance(bruto, int):
        return bruto if bruto >= 1 else 0
    texto = str(bruto if bruto is not None else "").strip()
    if not texto.isdigit():
        return 0
    return int(texto)


def paginas_do_pdf(caminho: Path) -> int:
    """Quantas páginas o PDF tem. So LE.

    O ARQUIVO SE ABRE E SE FECHA AQUI DENTRO, e o `with` não é enfeite: a lição
    do HOTFIX-2026-10-06-01 é que o Windows trava o PDF que ficou aberto
    (WinError 32), e o próximo a mexer nele — retirar o anexo, o backup —
    leva o erro sem saber de onde veio.
    """
    from pypdf import PdfReader
    with open(caminho, "rb") as fh:
        return len(PdfReader(fh).pages)


def folhas_do_arquivo(nome: Any, caminho: Any) -> int | None:
    """Folhas de UM arquivo, ou None quando ele não se conta. So LE.

    None não é zero: é «não sei contar este», e a tela diz qual foi — zero
    afirmaria que o documento não tem folha nenhuma.
    """
    ext = Path(str(nome or caminho or "")).suffix.lower()
    if ext in EXTENSOES_DE_UMA_FOLHA:
        return 1
    if ext in EXTENSOES_PDF:
        try:
            return paginas_do_pdf(Path(str(caminho)))
        except Exception:                                   # noqa: BLE001
            return None
    return None


def anexos_do_ato(con: sqlite3.Connection, ato: Any) -> list[dict]:
    """Os documentos do ato E os do Protocolo Geral ligado a ele. So LE.

    A leitura é a de `protocolo_documentos.anexos_do_ato_de_notas` (relato
    #135, construído por outra passada no mesmo dia): uma régua só para «que
    papéis este ato tem», que é a que a ficha mostra — duas leituras parecidas
    divergiriam no primeiro conserto. Os retirados já vêm de fora.

    CONTAM TODOS OS DO PROTOCOLO, e a dúvida fica declarada: o tipo do
    documento (`attachments.documento_tipo` — identidade, certidão, matrícula,
    tributo, comprovante...) não diz, sozinho, o que se arquiva com a
    procuração, e não há precedente medido para escolher. Na dúvida conta-se
    tudo, o tipo vai escrito na origem de cada parcela, e o escrevente corrige
    na confirmação.
    """
    import protocolo_documentos as PDOC
    achado = PDOC.anexos_do_ato_de_notas(con, int(ato["id"]))
    numero = (achado.get("protocolo") or {}).get("numero") or ""
    fora = [{"nome": d.get("original_name"), "caminho": d.get("stored_path"),
             "origem": "ato", "tipo": d.get("tipo_rotulo") or ""}
            for d in achado.get("do_ato") or []]
    fora += [{"nome": d.get("original_name"), "caminho": d.get("stored_path"),
              "origem": f"protocolo {numero}".strip(),
              "tipo": d.get("tipo_rotulo") or ""}
             for d in achado.get("do_protocolo") or []]
    return fora


# O PONTO ÚNICO DE EXTENSÃO. Cada fonte recebe (con, ato) e devolve
# [{nome, caminho, origem, tipo}]. Hoje uma só, que já junta o ato e o
# Protocolo Geral (`nt_atos.protocolo_id`).
FONTES_DOS_ANEXOS: tuple[Callable[[sqlite3.Connection, Any], list[dict]], ...] = (
    anexos_do_ato,
)


def contar_folhas(con: sqlite3.Connection, ato: Any) -> dict:
    """A sugestão de folhas, e de onde ela veio. So LE.

    Devolve `{total, anexos, itens, nao_contados, texto}`, com `texto` na
    forma que a tela mostra: «3 folhas: rg.pdf (2) + comprovante.jpg (1)».
    """
    itens, nao_contados, anexos = [], [], 0
    for fonte in FONTES_DOS_ANEXOS:
        for anexo in fonte(con, ato):
            anexos += 1
            n = folhas_do_arquivo(anexo.get("nome"), anexo.get("caminho"))
            if n is None:
                nao_contados.append(str(anexo.get("nome") or ""))
            else:
                itens.append({"nome": str(anexo.get("nome") or ""), "folhas": n,
                              "origem": anexo.get("origem") or "ato",
                              "tipo": anexo.get("tipo") or ""})
    total = sum(i["folhas"] for i in itens)

    def _parcela(i: dict) -> str:
        # O do próprio ato sai curto — «rg.pdf (2)» —; o do protocolo diz de
        # onde veio e de que tipo é, que é o que o escrevente confere.
        if i["origem"] == "ato":
            return f"{i['nome']} ({i['folhas']})"
        extra = ", ".join(x for x in (i["origem"], i["tipo"]) if x)
        return f"{i['nome']} ({i['folhas']}, {extra})"

    if itens:
        texto = (f"{total} folha{'s' if total != 1 else ''}: "
                 + " + ".join(_parcela(i) for i in itens))
    elif anexos:
        texto = "nenhum anexo pôde ser contado"
    else:
        texto = "nenhum documento anexado"
    if nao_contados:
        texto += " — não contado(s): " + ", ".join(nao_contados)
    return {"total": total, "anexos": anexos, "itens": itens,
            "nao_contados": nao_contados, "texto": texto}


def situacao(con: sqlite3.Connection, ato: Any) -> dict:
    """O que a tela precisa saber do arquivamento deste ato. So LE."""
    obrigatorio = arquivamento_obrigatorio(ato["tipo"])
    contagem = contar_folhas(con, ato) if obrigatorio else None
    confirmado = bool(str(ato["arquivamento_confirmado_em"] or "").strip()
                      and folhas_validas(ato["folhas_arquivamento"]))
    mudou = bool(confirmado and contagem is not None
                 and ato["arquivamento_folhas_sugeridas"] is not None
                 and int(ato["arquivamento_folhas_sugeridas"]) != contagem["total"])
    return {"obrigatorio": obrigatorio, "contagem": contagem,
            "confirmado": confirmado and not mudou, "anexos_mudaram": mudou,
            "folhas": ato["folhas_arquivamento"],
            "sugeridas": ato["arquivamento_folhas_sugeridas"],
            "origem": ato["arquivamento_origem_sugestao"],
            "confirmado_em": ato["arquivamento_confirmado_em"],
            "confirmado_por": ato["arquivamento_confirmado_por"]}


# ------------------------------------------------- o item nas custas e no recibo
#
# O 13.30 ENTRA SOZINHO NO PROTOCOLO DO ATO — decisão do oficial, 15/10/2026:
# ao confirmar as folhas, o item «13.30 × N» vai para o protocolo geral ligado
# ao ato (`nt_atos.protocolo_id`), sem duplicar, e a reconfirmação ajusta a
# quantidade. É O MESMO ITEM QUE O CAIXA ACRESCENTA À MÃO: o valor sai de
# `emolumentos.calcular_item` pelo serviço da tabela vigente, e o total do
# protocolo pela mesma `somar_itens`; quitar continua sendo o botão do caixa,
# que é o que lança o dinheiro e entra no recibo.
#
# A CHAVE É `(origem, origem_chave)`, e o índice único do caixa
# (`ux_cx_prot_atos_origem`) é quem garante o «sem duplicar». O item que o
# balcão já tinha posto à mão (13.30, origem MANUAL) é ADOTADO, e não somado.

ORIGEM_DO_ITEM = "ARQUIVAMENTO_NOTAS"


def _chave_do_item(ato_id: int) -> str:
    return f"nt_atos:{int(ato_id)}:{CODIGO_DO_ARQUIVAMENTO}"


def _servico_do_arquivamento(con: sqlite3.Connection) -> int | None:
    """O serviço 13.30 que tem valor na tabela vigente. So LE."""
    r = con.execute(
        """SELECT s.codigo FROM cx_servicos s
             JOIN cx_servico_valores v ON v.servico = s.codigo
             JOIN cx_vigencias g ON g.codigo = v.vigencia AND g.vigente = 1
            WHERE s.codigo_tj = ? ORDER BY s.ativo DESC, s.codigo LIMIT 1""",
        (CODIGO_DO_ARQUIVAMENTO,)).fetchone()
    return int(r[0]) if r else None


def lancar_item_no_protocolo(con: sqlite3.Connection, ato: Any,
                             folhas: int) -> dict:
    """Põe (ou ajusta) o 13.30 × folhas no protocolo do ato. GRAVA.

    Devolve `{lancado, motivo, item_id, acao}`. Sem protocolo ligado, sem o
    serviço na tabela, ou com o protocolo encerrado, NÃO lança e diz por quê —
    quem chama mostra o aviso; a confirmação das folhas vale assim mesmo.
    RECUSA (ArquivamentoError) só o item JÁ QUITADO com outra quantidade:
    dinheiro que entrou sai por estorno, no caixa, e não por esta tela.
    """
    import emolumentos as EMOL
    import caixa_protocolo as CXP
    pid = ato["protocolo_id"]
    if not pid:
        return {"lancado": False, "acao": None, "item_id": None,
                "motivo": ("o ato não está ligado a um protocolo geral — "
                           "ligue-o, e o 13.30 entra nas custas ao confirmar "
                           "de novo; ou acrescente o item no caixa.")}
    p = con.execute("SELECT situacao FROM cx_protocolos WHERE id=?",
                    (int(pid),)).fetchone()
    if not p:
        return {"lancado": False, "acao": None, "item_id": None,
                "motivo": "o protocolo ligado ao ato não existe."}
    if p[0] in ("CANCELADO", "ENTREGUE"):
        return {"lancado": False, "acao": None, "item_id": None,
                "motivo": (f"o protocolo está {p[0].lower()}; o 13.30 não "
                           f"entrou nas custas.")}
    chave = _chave_do_item(ato["id"])
    cols = ("id, quantidade, quitado, origem")
    meu = con.execute(
        f"SELECT {cols} FROM cx_protocolo_atos WHERE origem=? AND origem_chave=?",
        (ORIGEM_DO_ITEM, chave)).fetchone()
    if meu is None:
        meu = con.execute(
            f"""SELECT {cols} FROM cx_protocolo_atos
                 WHERE protocolo_id=? AND codigo_ato=? AND origem='MANUAL'
                 ORDER BY id LIMIT 1""",
            (int(pid), CODIGO_DO_ARQUIVAMENTO)).fetchone()
    if meu is not None and int(meu[2] or 0):
        if int(meu[1] or 0) == int(folhas):
            return {"lancado": True, "acao": "ja_quitado", "item_id": meu[0],
                    "motivo": ""}
        raise ArquivamentoError(
            f"o item 13.30 do protocolo já foi quitado com {meu[1]} folha(s); "
            f"para mudar para {folhas}, estorne no caixa antes de confirmar.")
    servico = _servico_do_arquivamento(con)
    item = (EMOL.calcular_item(con, servico=servico, quantidade=int(folhas))
            if servico else None)
    if not item:
        return {"lancado": False, "acao": None, "item_id": None,
                "motivo": ("o item 13.30 não está na tabela de custas vigente; "
                           "acrescente-o no caixa.")}
    valores = (item["descricao"], item["codigo_tj"], item["quantidade"],
               item["total"], item["emolumentos"], item["ferc"], item["fadep"],
               item["femp"], item["ferrfis"], item["servico_codigo"],
               item["origem_valor"])
    if meu is not None:
        con.execute(
            """UPDATE cx_protocolo_atos
                  SET descricao=?, codigo_ato=?, quantidade=?, valor_total=?,
                      emolumentos=?, ferc=?, fadep=?, femp=?, ferrfis=?,
                      servico_codigo=?, origem_valor=?, origem=?, origem_chave=?
                WHERE id=?""",
            (*valores, ORIGEM_DO_ITEM, chave, meu[0]))
        item_id, acao = meu[0], ("adotado" if meu[3] == "MANUAL"
                                 else "ajustado")
    else:
        item_id = con.execute(
            """INSERT INTO cx_protocolo_atos
                   (protocolo_id, descricao, codigo_ato, quantidade,
                    valor_total, emolumentos, ferc, fadep, femp, ferrfis,
                    servico_codigo, origem_valor, origem, origem_chave)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(pid), *valores, ORIGEM_DO_ITEM, chave)).lastrowid
        acao = "lancado"
    # O total e a situação do protocolo pela MESMA conta do caixa.
    cur = con.execute("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=?",
                      (int(pid),))
    nomes = [d[0] for d in cur.description]
    itens = [dict(zip(nomes, r)) for r in cur.fetchall()]
    situacao = CXP.situacao_pelos_itens(con, int(pid))
    con.execute("UPDATE cx_protocolos SET valor_total=?, situacao=?, "
                "finalizado=? WHERE id=?",
                (EMOL.somar_itens(itens)["total"], situacao,
                 1 if situacao == "PAGO" else 0, int(pid)))
    return {"lancado": True, "acao": acao, "item_id": item_id, "motivo": ""}


def confirmar(con: sqlite3.Connection, ato_id: int, *, folhas: Any,
              usuario: Any, agora: Any) -> dict:
    """O escrevente confirma — ou corrige — as folhas arquivadas. GRAVA.

    Grava o número sugerido pela contagem, de onde ele veio, o confirmado,
    quem e quando. Recusa sem anexo e recusa número que não é inteiro >= 1.
    """
    ato = con.execute("SELECT * FROM nt_atos WHERE id=?",
                      (int(ato_id),)).fetchone()
    if not ato:
        raise ArquivamentoError("O ato não existe.")
    if not arquivamento_obrigatorio(ato["tipo"]):
        raise ArquivamentoError(
            "Este tipo de ato não tem o arquivamento obrigatório; o "
            "arquivamento dele continua sendo pedido na própria lavratura.")
    if str(ato["selo_arquivamento"] or "").strip():
        raise ArquivamentoError(
            f"O arquivamento deste ato já foi selado "
            f"({ato['selo_arquivamento']}); as folhas não se mudam depois.")
    contagem = contar_folhas(con, ato)
    if not contagem["anexos"]:
        raise ArquivamentoError(f"Não confirmado: {MENSAGEM_SEM_ANEXO}")
    n = folhas_validas(folhas)
    if n < 1:
        raise ArquivamentoError(
            "Informe quantas folhas foram arquivadas (número inteiro, 1 ou "
            "mais).")
    con.execute(
        """UPDATE nt_atos
              SET folhas_arquivamento=?, arquivamento_folhas_sugeridas=?,
                  arquivamento_origem_sugestao=?,
                  arquivamento_confirmado_em=?, arquivamento_confirmado_por=?
            WHERE id=?""",
        (n, contagem["total"], contagem["texto"], str(agora),
         str(usuario or ""), int(ato_id)))
    # Na MESMA transação: confirmação sem o item nas custas seria o dinheiro
    # do 13.30 ficando de fora do recibo; e o item quitado com outra
    # quantidade desfaz a confirmação inteira (a recusa sobe daqui).
    custas = lancar_item_no_protocolo(con, ato, n)
    return {"folhas": n, "sugeridas": contagem["total"],
            "origem": contagem["texto"], "corrigido": n != contagem["total"],
            "custas": custas}


def exigir_para_selar(con: sqlite3.Connection, ato: Any) -> int | None:
    """As folhas confirmadas, ou a recusa. So LE.

    None quando o tipo não é dos obrigados (o opcional segue como estava).
    Recusa sem anexo, sem confirmação, e quando os anexos mudaram depois da
    confirmação — o número confirmado era sobre outros documentos.
    """
    if not arquivamento_obrigatorio(ato["tipo"]):
        return None
    contagem = contar_folhas(con, ato)
    if not contagem["anexos"]:
        raise ArquivamentoError(MENSAGEM_SEM_ANEXO)
    n = folhas_validas(ato["folhas_arquivamento"])
    if not str(ato["arquivamento_confirmado_em"] or "").strip() or n < 1:
        raise ArquivamentoError(
            f"confirme a quantidade de folhas arquivadas (a contagem dos "
            f"anexos sugere {contagem['texto']}). O selo de arquivamento é "
            f"obrigatório neste ato e não sai sem a confirmação.")
    sugeridas = ato["arquivamento_folhas_sugeridas"]
    if sugeridas is not None and int(sugeridas) != contagem["total"]:
        raise ArquivamentoError(
            f"os anexos mudaram depois da confirmação (eram "
            f"{sugeridas} folha(s), agora {contagem['texto']}). Confirme a "
            f"quantidade de novo.")
    return n

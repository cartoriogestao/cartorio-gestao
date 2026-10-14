"""Encerrar o protocolo do balcao — o atendimento que nao vai virar ato.

O DEBITO, QUE ESTAVA NO `CLAUDE.md` DESDE AGOSTO
    «encerrar protocolo».

O QUE SE MEDIU EM 28/08/2026, ANTES DE CONSTRUIR
    Sao **640 protocolos ABERTOS**, todos de 2026 e **todos vindos do
    E-Oficio** (`origem = 'EOFICIO'`): 250 do Registro de Imoveis, 226 do
    Registro Civil, 101 de firmas, 30 das Notas, 30 do Protesto, 3 do RTD.

    E **nenhum deles tem um unico item**, nem valor, nem nada quitado. Sao
    atendimentos que comecaram e nunca viraram servico: «orcamento registro
    TITULO DE DOMINIO», «CERTIDAO», «2a VIA NASCIMENTO». O cliente perguntou o
    preco e nao voltou, ou resolveu por outro caminho.

O DEFEITO ERA O CONTRARIO DO DE COSTUME
    Neste projeto a forma repetida do defeito e «funcao pronta que nenhuma tela
    chama». Aqui e o inverso: **a situacao terminal ja estava declarada em tres
    lugares** — no comentario do `SCHEMA` (`ABERTO | ENTREGUE | CANCELADO`), no
    rotulo de `caixa_web.SITUACOES`, e ate na guarda de `_atualizar_situacao`,
    que respeita `("CANCELADO", "ENTREGUE")` para nao sobrescrever —, **e
    nenhuma rota conseguia produzi-la**. Medido: em 21.348 protocolos so
    existem `ABERTO`, `A_PAGAR` e `PAGO`.

    Havia uma trava esperando um estado que nada criava.

POR QUE DUAS PALAVRAS, E NAO UMA
    Elas dizem coisas diferentes, e a diferenca importa na correicao:
    `ENTREGUE` e o atendimento que foi resolvido; `CANCELADO` e o que nao virou
    servico. Juntar as duas num «encerrado» faria a lista de um mes nao
    distinguir o trabalho feito do trabalho que nao houve.

    As duas ja estavam escritas na casa. Inventar uma terceira palavra seria
    criar vocabulario novo tendo o antigo a mao — e ele ja esta em tela.
"""
from __future__ import annotations

import sqlite3
from datetime import date

ENTREGUE = "ENTREGUE"
CANCELADO = "CANCELADO"

# O que cada encerramento quer dizer, no balcao. E o texto que aparece na
# tela: quem escolhe precisa saber o que esta declarando.
ENCERRAMENTOS: dict[str, str] = {
    ENTREGUE: "Entregue — o atendimento foi resolvido",
    CANCELADO: "Cancelado — não virou serviço",
}

# Dez caracteres nao e formalidade: e o minimo para uma frase dizer alguma
# coisa. «ok», «nao veio» e «-» nao explicam nada a quem ler daqui a dois anos.
MINIMO_DO_MOTIVO = 10


class ProtocoloError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def proximo_numero(con: sqlite3.Connection, data_abertura: str) -> str:
    """Próximo ``AAAA.MM.N`` do protocolo geral. Só calcula.

    A numeração é a medida no E-Ofício e é comum a todas as atribuições. A
    chamada acontece dentro da mesma transação do INSERT, para o número não
    ser escolhido numa conexão e gravado em outra.
    """
    try:
        dia = date.fromisoformat(str(data_abertura or "")[:10])
    except ValueError as erro:
        raise ProtocoloError("Informe uma data válida para abrir o protocolo.") from erro
    prefixo = f"{dia.year}.{dia.month:02d}."
    con.row_factory = sqlite3.Row
    ultimo = con.execute(
        """SELECT numero FROM cx_protocolos WHERE numero LIKE ?
             ORDER BY CAST(SUBSTR(numero, ?) AS INTEGER) DESC LIMIT 1""",
        (prefixo + "%", len(prefixo) + 1)).fetchone()
    sequencia = int(str(ultimo["numero"]).split(".")[-1]) + 1 if ultimo else 1
    return f"{prefixo}{sequencia}"


def abrir(con: sqlite3.Connection, *, data_abertura: str, agora: str,
          atribuicao: str | None = None, hora: str | None = None,
          interessado: str | None = None,
          interessado_documento: str | None = None,
          telefone: str | None = None, email: str | None = None,
          assunto: str | None = None, observacao: str | None = None,
          previsao_entrega: str | None = None, tipo: str = "SERVICO",
          documento_tipo: str | None = None,
          documento_numero: str | None = None,
          documento_descricao: str | None = None,
          criado_por: int | None = None,
          ri_protocolo_id: int | None = None) -> dict:
    """Abre o protocolo geral do balcão. ESCREVE.

    O interessado pode estar em branco porque o art. 12 da LRP não deixa a
    falta de informação impedir a apresentação do título. A tela geral do
    caixa continua exigindo o nome; RTD/RCPJ pode completá-lo depois.
    """
    dia = str(data_abertura or "")[:10]
    numero = proximo_numero(con, dia)
    cur = con.execute(
        """INSERT INTO cx_protocolos
           (numero, data_abertura, hora, atribuicao, interessado,
            interessado_documento, telefone, email, assunto, observacao,
            previsao_entrega, tipo, documento_tipo, documento_numero,
            documento_descricao, situacao, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'ABERTO', ?,?)""",
        (numero, dia, str(hora or "").strip() or None,
         str(atribuicao or "").strip().upper() or None,
         str(interessado or "").strip() or None,
         str(interessado_documento or "").strip() or None,
         str(telefone or "").strip() or None,
         str(email or "").strip() or None,
         str(assunto or "").strip() or None,
         str(observacao or "").strip() or None,
         str(previsao_entrega or "").strip() or None,
         "ORCAMENTO" if str(tipo or "").upper() == "ORCAMENTO" else "SERVICO",
         str(documento_tipo or "").strip() or None,
         str(documento_numero or "").strip() or None,
         str(documento_descricao or "").strip() or None,
         agora, criado_por))
    feito = {"protocolo_id": int(cur.lastrowid), "numero": numero}
    # Ponte com a prenotacao do RI, quando o balcao (ou a OP de titulo) ja
    # apontou qual e. Sem escolha humana aqui, a coluna fica vazia — o lavrar
    # nao adivinha.
    if ri_protocolo_id is not None and str(ri_protocolo_id).strip().isdigit():
        ligacao = vincular_ri(con, feito["protocolo_id"], int(ri_protocolo_id))
        feito.update({
            "ri_protocolo_id": ligacao["ri_protocolo_id"],
            "prenotacao_numero": ligacao["prenotacao_numero"],
            "ri_matricula_id": ligacao["ri_matricula_id"],
        })
    return feito


def _protocolo(con: sqlite3.Connection, protocolo_id: int) -> sqlite3.Row:
    con.row_factory = sqlite3.Row
    p = con.execute("SELECT * FROM cx_protocolos WHERE id=?",
                    (int(protocolo_id),)).fetchone()
    if not p:
        raise ProtocoloError(
            f"Não achei o protocolo {protocolo_id}. Ele pode ter sido aberto "
            f"em outra máquina e ainda não ter chegado aqui.")
    return p


def esta_encerrado(situacao) -> bool:
    return str(situacao or "").upper() in ENCERRAMENTOS


def encerrar(con: sqlite3.Connection, protocolo_id: int, *, situacao: str,
             motivo: str, quem: str | None, agora: str) -> dict:
    """Fecha o protocolo sem pagamento, com motivo escrito. So o dominio decide.

    AS TRES RECUSAS, E CADA UMA PROTEGE ALGUEM:

    1. **Dinheiro que entrou nao se esconde.** Protocolo com item ja quitado
       tem lancamento no caixa; encerra-lo faria a conferencia do dia fechar
       com um servico que sumiu da lista e um valor que ficou. O caminho certo
       e o **estorno**, que deixa rastro — a mesma regra de `desquitar`.

    2. **Motivo escrito e obrigatorio.** «Dispensar e decisao do oficial;
       ignorar nao e» — a mesma regra do usucapiao, da pendencia de numeracao
       e da ordem do CNIB. Numa correicao a pergunta e exatamente por que
       aquele atendimento nao virou ato.

    3. **Encerrado nao se encerra de novo.** O segundo clique trocaria o
       motivo e a data do primeiro, e o rastro passaria a contar outra
       historia.
    """
    escolha = str(situacao or "").upper()
    if escolha not in ENCERRAMENTOS:
        raise ProtocoloError(
            f"«{situacao}» não é um jeito de encerrar que eu saiba registrar. "
            f"Escolha entre: {', '.join(ENCERRAMENTOS.values())}.")

    p = _protocolo(con, protocolo_id)
    if esta_encerrado(p["situacao"]):
        raise ProtocoloError(
            f"O protocolo {p['numero']} já foi encerrado como "
            f"{ENCERRAMENTOS.get(p['situacao'], p['situacao'])}. Para mudar "
            f"isso, reabra primeiro — assim fica o rastro das duas coisas.")

    quitados = con.execute(
        """SELECT COUNT(*) n FROM cx_protocolo_atos
            WHERE protocolo_id = ? AND COALESCE(quitado, 0) = 1""",
        (int(protocolo_id),)).fetchone()["n"]
    if quitados:
        raise ProtocoloError(
            f"O protocolo {p['numero']} tem {quitados} "
            f"{'item quitado' if quitados == 1 else 'itens quitados'}: esse "
            f"dinheiro já entrou no caixa. Encerrar aqui faria o serviço sumir "
            f"da lista e o valor ficar. Estorne o lançamento primeiro — o "
            f"estorno deixa rastro, e apagar não.")

    limpo = (motivo or "").strip()
    if len(limpo) < MINIMO_DO_MOTIVO:
        raise ProtocoloError(
            "Escreva por que este atendimento está sendo encerrado — foi só um "
            "orçamento, o cliente não voltou, foi resolvido por outro caminho. "
            "Daqui a dois anos essa frase é a única coisa que vai explicar o "
            "protocolo em branco.")

    con.execute(
        """UPDATE cx_protocolos
              SET situacao = ?, finalizado = 1, data_finalizacao = ?,
                  encerramento_motivo = ?, encerrado_por = ?
            WHERE id = ?""",
        (escolha, agora, limpo, quem, int(protocolo_id)))
    return {"numero": p["numero"], "situacao": escolha, "motivo": limpo}


def reabrir(con: sqlite3.Connection, protocolo_id: int, *, motivo: str,
            quem: str | None, agora: str) -> dict:
    """Desfaz o encerramento, e a situacao volta a sair dos itens.

    REABRIR EXISTE PORQUE ENCERRAR ERRADO ACONTECE, e um encerramento sem
    volta faria o balcao abrir um protocolo novo para o mesmo atendimento — e
    aí o numero de protocolo deixaria de dizer quantos atendimentos houve.

    A SITUACAO NAO SE ESCOLHE NA VOLTA: ela e recalculada dos itens, que e a
    regra da casa («a situacao vem dos itens»). Deixar quem reabre escolher
    permitiria devolver como PAGO um protocolo que ninguem pagou.

    E O MOTIVO DO ENCERRAMENTO **FICA GRAVADO**, com a marca de que foi
    reaberto. Apaga-lo faria o rastro dizer que aquele encerramento nunca
    existiu — e engano se conserta a vista, nao se esconde.
    """
    p = _protocolo(con, protocolo_id)
    if not esta_encerrado(p["situacao"]):
        raise ProtocoloError(
            f"O protocolo {p['numero']} não está encerrado — ele está "
            f"{p['situacao']}. Não há o que reabrir.")

    limpo = (motivo or "").strip()
    if len(limpo) < MINIMO_DO_MOTIVO:
        raise ProtocoloError(
            "Escreva por que este protocolo está sendo reaberto. Encerramento "
            "que vai e volta sem explicação é o que faz ninguém confiar na "
            "lista depois.")

    anterior = (p["encerramento_motivo"] or "").strip()
    historia = (f"{anterior}\n[reaberto em {agora}"
                f"{' por ' + quem if quem else ''}: {limpo}]").strip()
    con.execute(
        """UPDATE cx_protocolos
              SET situacao = ?, finalizado = 0, data_finalizacao = NULL,
                  encerramento_motivo = ?
            WHERE id = ?""",
        (situacao_pelos_itens(con, protocolo_id), historia, int(protocolo_id)))
    return {"numero": p["numero"], "motivo": limpo}


def situacao_pelos_itens(con: sqlite3.Connection, protocolo_id: int) -> str:
    """A situacao que os itens do protocolo produzem. So calcula.

    E A MESMA CONTA DE `caixa_web._atualizar_situacao`, e ela mora aqui para
    `reabrir` nao a escrever de novo com outras palavras. Duas versoes da conta
    que decide se um protocolo esta pago e como elas divergem — e a divergencia
    apareceria no dia em que uma delas fosse corrigida.
    """
    con.row_factory = sqlite3.Row
    linha = con.execute(
        """SELECT COUNT(*) total, COALESCE(SUM(quitado), 0) quitados
             FROM cx_protocolo_atos WHERE protocolo_id = ?""",
        (int(protocolo_id),)).fetchone()
    if not linha["total"]:
        return "ABERTO"
    return "PAGO" if linha["quitados"] >= linha["total"] else "A_PAGAR"


def abertos_sem_item(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Os protocolos abertos que nunca ganharam item — os candidatos a encerrar.

    E A LISTA QUE FAZ O DEBITO CABER NUMA TELA. Sao 640 no acervo desta casa, e
    procurar um a um na lista geral de 21.348 seria o mesmo que nao ter a
    funcao. Ordenados do mais antigo para o mais novo: quem esta parado ha mais
    tempo e quem menos vai voltar.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT p.* FROM cx_protocolos p
            WHERE p.situacao = 'ABERTO'
              AND NOT EXISTS (SELECT 1 FROM cx_protocolo_atos a
                               WHERE a.protocolo_id = p.id)
            ORDER BY p.data_abertura, p.id
            LIMIT ?""", (int(limite),))]


def quantos_abertos_sem_item(con: sqlite3.Connection) -> int:
    """O total, para a tela dizer quantos ficaram de fora do limite.

    Lista cortada que nao diz que cortou faz quem a le achar que acabou — e
    este projeto ja pagou por isso: «varredor que deixa de achar passa calado».
    """
    con.row_factory = sqlite3.Row
    return int(con.execute(
        """SELECT COUNT(*) n FROM cx_protocolos p
            WHERE p.situacao = 'ABERTO'
              AND NOT EXISTS (SELECT 1 FROM cx_protocolo_atos a
                               WHERE a.protocolo_id = p.id)""").fetchone()["n"])

def _tem_coluna(con: sqlite3.Connection, tabela: str, coluna: str) -> bool:
    """A coluna existe nesta base? So le — bases antigas podem nao ter migrado."""
    return coluna in {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def prenotacao_por_id(con: sqlite3.Connection, ri_protocolo_id: int) -> dict | None:
    """A prenotacao do RI pelo id interno. So le. Nao inventa."""
    if not _tem_tabela(con, "ri_protocolos"):
        return None
    con.row_factory = sqlite3.Row
    r = con.execute(
        """SELECT id, numero, livro, situacao, apresentante, natureza_titulo,
                  matricula_id, matricula_numero, data_prenotacao
             FROM ri_protocolos WHERE id=?""",
        (int(ri_protocolo_id),)).fetchone()
    return dict(r) if r else None


def _tem_tabela(con: sqlite3.Connection, nome: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nome,)).fetchone())


def prenotacoes_abertas(con: sqlite3.Connection, *, limite: int = 80,
                        busca: str | None = None) -> list[dict]:
    """Prenotacoes do Livro 1 para o balcao escolher o vinculo. So le.

    A lista e humana: o escrevente aponta a prenotacao; o sistema nao junta
    por nome do interessado nem por coincidencia de numero do caixa.
    """
    if not _tem_tabela(con, "ri_protocolos"):
        return []
    con.row_factory = sqlite3.Row
    onde = ["situacao = 'ABERTO'"]
    params: list = []
    termo = (busca or "").strip()
    if termo:
        onde.append(
            "(CAST(numero AS TEXT) LIKE ? OR apresentante LIKE ? "
            "OR matricula_numero LIKE ? OR natureza_titulo LIKE ?)")
        like = f"%{termo}%"
        params += [like, like, like, like]
    params.append(int(limite))
    return [dict(r) for r in con.execute(
        f"""SELECT id, numero, livro, situacao, apresentante, natureza_titulo,
                   matricula_id, matricula_numero, data_prenotacao
              FROM ri_protocolos
             WHERE {' AND '.join(onde)}
             ORDER BY numero DESC
             LIMIT ?""", params)]


def vincular_ri(con: sqlite3.Connection, protocolo_id: int,
                ri_protocolo_id: int) -> dict:
    """Grava a ponte cx_protocolos.ri_protocolo_id -> ri_protocolos. ESCREVE.

    O vinculo so nasce de escolha humana (ou de evidencia ja gravada em outro
    lugar da casa). Aqui a prenotacao tem de existir; a matricula so entra se
    a propria prenotacao ja trouxer matricula_id — nao se inventa matrícula
    a partir do texto.
    """
    if not _tem_coluna(con, "cx_protocolos", "ri_protocolo_id"):
        raise ProtocoloError(
            "Esta base ainda nao tem a coluna ri_protocolo_id no protocolo "
            "geral. Atualize o esquema do caixa antes de vincular.")
    p = _protocolo(con, protocolo_id)
    prenot = prenotacao_por_id(con, ri_protocolo_id)
    if not prenot:
        raise ProtocoloError(
            f"Nao achei a prenotacao id {ri_protocolo_id}. Confira o numero "
            f"no Livro 1 antes de vincular.")

    matricula_id = prenot.get("matricula_id")
    tem_mat = _tem_coluna(con, "cx_protocolos", "ri_matricula_id")
    if tem_mat:
        con.execute(
            """UPDATE cx_protocolos
                  SET ri_protocolo_id = ?, ri_matricula_id = ?
                WHERE id = ?""",
            (int(ri_protocolo_id),
             int(matricula_id) if matricula_id else None,
             int(protocolo_id)))
    else:
        con.execute(
            """UPDATE cx_protocolos SET ri_protocolo_id = ? WHERE id = ?""",
            (int(ri_protocolo_id), int(protocolo_id)))
    return {
        "protocolo_id": int(protocolo_id),
        "protocolo_numero": p["numero"],
        "ri_protocolo_id": int(ri_protocolo_id),
        "prenotacao_numero": prenot["numero"],
        "prenotacao_livro": prenot.get("livro"),
        "ri_matricula_id": int(matricula_id) if matricula_id else None,
    }


def desvincular_ri(con: sqlite3.Connection, protocolo_id: int) -> dict:
    """Tira a ponte com a prenotacao. ESCREVE.

    Desvincular nao apaga a prenotacao nem o protocolo: so desfaz a ligacao
    que o balcao tinha apontado. Erro se conserta a vista.
    """
    p = _protocolo(con, protocolo_id)
    try:
        anterior = p["ri_protocolo_id"]
    except (KeyError, IndexError):
        anterior = None
    if _tem_coluna(con, "cx_protocolos", "ri_matricula_id"):
        con.execute(
            """UPDATE cx_protocolos
                  SET ri_protocolo_id = NULL, ri_matricula_id = NULL
                WHERE id = ?""", (int(protocolo_id),))
    else:
        con.execute(
            """UPDATE cx_protocolos SET ri_protocolo_id = NULL WHERE id = ?""",
            (int(protocolo_id),))
    return {
        "protocolo_id": int(protocolo_id),
        "protocolo_numero": p["numero"],
        "ri_protocolo_id_anterior": anterior,
    }


def backfill_por_deposito(con: sqlite3.Connection, *, dry_run: bool = True
                          ) -> dict:
    """Propaga ri_protocolo_id do deposito para o protocolo de caixa. So evidencia.

    Unico caminho seguro automatico: o deposito ja aponta para a prenotacao
    (`cx_depositos.ri_protocolo_id`) E para o protocolo de caixa
    (`cx_depositos.protocolo_id`), e o protocolo ainda esta sem a ponte.
    Nao junta por interessado, numero ou assunto.
    """
    if not _tem_coluna(con, "cx_protocolos", "ri_protocolo_id"):
        return {"candidatos": 0, "aplicados": 0, "dry_run": dry_run,
                "motivo": "coluna ausente"}
    if not _tem_coluna(con, "cx_depositos", "ri_protocolo_id"):
        return {"candidatos": 0, "aplicados": 0, "dry_run": dry_run,
                "motivo": "deposito sem coluna"}
    con.row_factory = sqlite3.Row
    rows = list(con.execute(
        """SELECT d.id AS deposito_id, d.protocolo_id, d.ri_protocolo_id,
                  c.ri_protocolo_id AS cx_ri
             FROM cx_depositos d
             JOIN cx_protocolos c ON c.id = d.protocolo_id
            WHERE d.ri_protocolo_id IS NOT NULL
              AND d.protocolo_id IS NOT NULL
              AND c.ri_protocolo_id IS NULL"""))
    aplicados = 0
    detalhes = []
    for r in rows:
        item = {
            "deposito_id": r["deposito_id"],
            "protocolo_id": r["protocolo_id"],
            "ri_protocolo_id": r["ri_protocolo_id"],
        }
        if not dry_run:
            feito = vincular_ri(con, int(r["protocolo_id"]),
                                int(r["ri_protocolo_id"]))
            item["prenotacao_numero"] = feito["prenotacao_numero"]
            aplicados += 1
        detalhes.append(item)
    return {
        "candidatos": len(rows),
        "aplicados": aplicados,
        "dry_run": dry_run,
        "detalhes": detalhes,
    }


# ------------------------------------------- as unidades do item do protocolo
#
# «a prenotacao 11571 e o protocolo 2026.09.23 nao estao permitindo que eu use
#  um selo de averbacao para o ato que preciso, ainda que conste no protocolo
#  5 atos de averbacao sem valor» — o oficial, 15/09/2026
#
# O item do protocolo tem QUANTIDADE, e ela se gasta **por unidade**. Até aqui
# o sistema marcava `usado_em` na linha inteira depois do primeiro ato: o item
# «De ato sem valor declarado × 5» do protocolo dele saiu da tela assim que a
# AV-04 foi lavrada, e as outras quatro averbações ficaram sem item.
#
# MEDIDO NA PRODUÇÃO NO MESMO DIA: **4 itens** com quantidade > 1 já marcados,
# e **83 unidades perdidas** — uma delas de quantidade **66**, o arquivamento
# do RTD/RCPJ, consumida por um ato só.
#
# E A REGRA DA CASA JÁ DIZIA ISSO, em `CLAUDE.md`: «a conta é por unidade — o
# protocolo 2026.08.103 abriu um item 13.18 com quantidade 10, e saíram 10
# selos». O que faltava era o contador.


def _quantidade(item) -> int:
    """Quantas unidades o item tem. Um item sem quantidade vale uma."""
    try:
        n = int(item["quantidade"])
    except (TypeError, ValueError, KeyError, IndexError):
        return 1
    return n if n > 0 else 1


def _usadas(item) -> int:
    """Quantas já se gastaram. Coluna nova: em banco antigo vem NULL.

    **`usado_em` PREENCHIDO COM `quantidade_usada` VAZIO É O ITEM ANTIGO**,
    marcado antes de existir o contador — ele conta como UMA unidade gasta, e
    não como o item inteiro. É isso que devolve ao oficial as 83 unidades que
    tinham sumido, sem apagar o rastro de quem consumiu a primeira.
    """
    try:
        bruto = item["quantidade_usada"]
    except (KeyError, IndexError):
        bruto = None
    if bruto is None:
        try:
            return 1 if str(item["usado_em"] or "").strip() else 0
        except (KeyError, IndexError):
            return 0
    try:
        return max(0, int(bruto))
    except (TypeError, ValueError):
        return 0


def saldo_do_item(item) -> int:
    """Quantas unidades ainda podem ser apontadas a um ato. Só calcula."""
    return max(0, _quantidade(item) - _usadas(item))


def itens_disponiveis(con: sqlite3.Connection, protocolo_id) -> list[dict]:
    """Os itens do protocolo com saldo, já com `saldo` dentro. Só LÊ.

    **A LISTA É POR SALDO, E NÃO POR `usado_em IS NULL`** — era essa condição
    que fazia o item de cinco averbações desaparecer depois da primeira.
    """
    if protocolo_id is None or not str(protocolo_id).strip().isdigit():
        return []
    saida = []
    for r in con.execute(
            """SELECT * FROM cx_protocolo_atos
                WHERE protocolo_id=?
                  AND codigo_ato IS NOT NULL AND TRIM(codigo_ato) <> ''
                ORDER BY id""", (int(protocolo_id),)):
        sobra = saldo_do_item(r)
        if sobra > 0:
            saida.append(dict(r) | {"saldo": sobra,
                                    "quantidade_usada": _usadas(r)})
    return saida


def consumir_item(con: sqlite3.Connection, item_id: int, *, ato_id: int,
                  tabela: str, agora: str, quantas: int = 1) -> int:
    """Gasta unidades de um item e devolve quantas foram. ESCREVE.

    `usado_em` E `usado_por_ato_id` GUARDAM O PRIMEIRO, e não o último: eles
    são o rastro de quando o item começou a ser consumido, e a ficha do
    protocolo os mostra. Sobrescrevê-los a cada ato faria a data andar e o
    primeiro ato sumir do rastro.

    **NÃO GASTA MAIS DO QUE HÁ.** Pedir três de um item com saldo dois gasta
    dois e devolve dois — quem chama decide o que fazer com a diferença; e
    negativo em contador de unidade é o tipo de erro que só aparece meses
    depois, quando alguém soma.
    """
    linha = con.execute("SELECT * FROM cx_protocolo_atos WHERE id=?",
                        (int(item_id),)).fetchone()
    if not linha:
        return 0
    sobra = saldo_do_item(linha)
    gastar = max(0, min(int(quantas or 0), sobra))
    if not gastar:
        return 0
    usadas = _usadas(linha) + gastar
    # A última unidade fecha o item — e é aí que `usado_em` passa a querer
    # dizer «acabou», que é o que a ficha do protocolo já lê.
    fechou = usadas >= _quantidade(linha)
    con.execute(
        """UPDATE cx_protocolo_atos
              SET quantidade_usada=?,
                  usado_em=CASE WHEN ? THEN COALESCE(usado_em, ?) ELSE usado_em END,
                  usado_por_ato_id=COALESCE(usado_por_ato_id, ?),
                  usado_por_tabela=COALESCE(usado_por_tabela, ?)
            WHERE id=?""",
        (usadas, 1 if fechou else 0, agora, int(ato_id), tabela, int(item_id)))
    return gastar


def devolver_item(con: sqlite3.Connection, item_id: int, *,
                  quantas: int = 1) -> int:
    """Devolve ao item as unidades que um ato desfeito havia gasto. ESCREVE.

    NASCEU DA ORDEM DO OFICIAL EM 16/09/2026: «selo recusado suspende ato
    (fica salvo como minuta para lavrar de novo)». O ato suspenso ja tinha
    consumido a unidade do protocolo — e se ela nao voltasse, o cliente teria
    pago cinco averbacoes e o balcao so conseguiria lavrar quatro.

    **ELA E O ESPELHO DE `consumir_item`, E MORA AQUI PELO MESMO MOTIVO:** a
    regra do saldo e uma so. Escrever a devolucao na rota daria duas versoes
    da conta que decide quantas averbacoes o cliente ainda tem.

    NUNCA DEVOLVE MAIS DO QUE FOI GASTO — `quantidade_usada` nao desce
    abaixo de zero. E quando o consumo zera, o rastro de quem abriu o item
    sai junto: item sem unidade gasta com `usado_em` preenchido e o carimbo
    que mente, e `_usadas` o leria como uma unidade gasta.

    Devolve quantas unidades de fato voltaram.
    """
    item = con.execute("SELECT * FROM cx_protocolo_atos WHERE id=?",
                       (int(item_id),)).fetchone()
    if item is None:
        return 0
    usadas = _usadas(item)
    voltam = max(0, min(int(quantas or 0), usadas))
    if not voltam:
        return 0
    fica = usadas - voltam
    zerou = (fica == 0)
    con.execute(
        """UPDATE cx_protocolo_atos
              SET quantidade_usada=?,
                  usado_em = CASE WHEN ? THEN NULL ELSE usado_em END,
                  usado_por_ato_id = CASE WHEN ? THEN NULL
                                          ELSE usado_por_ato_id END,
                  usado_por_tabela = CASE WHEN ? THEN NULL
                                          ELSE usado_por_tabela END
            WHERE id=?""",
        (fica, zerou, zerou, zerou, int(item_id)))
    return voltam

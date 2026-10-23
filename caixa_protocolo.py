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

# POSTGRESQL NATIVO DESDE O PILOTO DE 16/10/2026: o SQL deste módulo é o do
# PostgreSQL e vai pelo `bd_nativo`, sem tradução. O `con` que as funções
# recebem continua sendo o da rota.
from datetime import date

from bd_nativo import Banco, banco

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


def proximo_numero(con, data_abertura: str) -> str:
    """Próximo ``AAAA.MM.N`` do protocolo geral. Só calcula.

    A numeração é a medida no E-Ofício e é comum a todas as atribuições. A
    chamada acontece dentro da mesma transação do INSERT, para o número não
    ser escolhido numa conexão e gravado em outra — e `abrir` trava a
    numeração ANTES de ler o maior, senão dois balcões leem o mesmo.
    """
    try:
        dia = date.fromisoformat(str(data_abertura or "")[:10])
    except ValueError as erro:
        raise ProtocoloError("Informe uma data válida para abrir o protocolo.") from erro
    prefixo = f"{dia.year}.{dia.month:02d}."
    # O sufixo é lido pelo prefixo numérico, como o CAST do SQLite lia: um
    # número com lixo depois do último ponto não derruba a numeração.
    maior = banco(con).valor(
        """SELECT max(substring(substring(numero FROM %(inicio)s) FROM '^[0-9]+')::bigint)
             FROM cx_protocolos
            WHERE starts_with(numero, %(prefixo)s)""",
        {"prefixo": prefixo, "inicio": len(prefixo) + 1})
    return f"{prefixo}{int(maior or 0) + 1}"


def abrir(con, *, data_abertura: str, agora: str,
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
    bd = banco(con)
    bd.travar("cx_protocolos.numero")
    numero = proximo_numero(bd, dia)
    novo = bd.escrever(
        """INSERT INTO cx_protocolos
           (numero, data_abertura, hora, atribuicao, interessado,
            interessado_documento, telefone, email, assunto, observacao,
            previsao_entrega, tipo, documento_tipo, documento_numero,
            documento_descricao, situacao, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'ABERTO', %s,%s)
           RETURNING id""",
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
    feito = {"protocolo_id": int(novo[0]["id"]), "numero": numero}
    # Ponte com a prenotacao do RI, quando o balcao (ou a OP de titulo) ja
    # apontou qual e. Sem escolha humana aqui, a coluna fica vazia — o lavrar
    # nao adivinha.
    if ri_protocolo_id is not None and str(ri_protocolo_id).strip().isdigit():
        ligacao = vincular_ri(bd, feito["protocolo_id"], int(ri_protocolo_id))
        feito.update({
            "ri_protocolo_id": ligacao["ri_protocolo_id"],
            "prenotacao_numero": ligacao["prenotacao_numero"],
            "ri_matricula_id": ligacao["ri_matricula_id"],
        })
    return feito


def _protocolo(con, protocolo_id: int) -> dict:
    p = banco(con).um("SELECT * FROM cx_protocolos WHERE id = %s",
                      (int(protocolo_id),))
    if not p:
        raise ProtocoloError(
            f"Não achei o protocolo {protocolo_id}. Ele pode ter sido aberto "
            f"em outra máquina e ainda não ter chegado aqui.")
    return p


def esta_encerrado(situacao) -> bool:
    return str(situacao or "").upper() in ENCERRAMENTOS


def encerrar(con, protocolo_id: int, *, situacao: str,
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

    bd = banco(con)
    p = _protocolo(bd, protocolo_id)
    if esta_encerrado(p["situacao"]):
        raise ProtocoloError(
            f"O protocolo {p['numero']} já foi encerrado como "
            f"{ENCERRAMENTOS.get(p['situacao'], p['situacao'])}. Para mudar "
            f"isso, reabra primeiro — assim fica o rastro das duas coisas.")

    quitados = int(bd.valor(
        """SELECT count(*) FROM cx_protocolo_atos
            WHERE protocolo_id = %s AND coalesce(quitado, 0) = 1""",
        (int(protocolo_id),)))
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

    bd.escrever(
        """UPDATE cx_protocolos
              SET situacao = %s, finalizado = 1, data_finalizacao = %s,
                  encerramento_motivo = %s, encerrado_por = %s
            WHERE id = %s""",
        (escolha, agora, limpo, quem, int(protocolo_id)))
    return {"numero": p["numero"], "situacao": escolha, "motivo": limpo}


def reabrir(con, protocolo_id: int, *, motivo: str,
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
    bd = banco(con)
    p = _protocolo(bd, protocolo_id)
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
    bd.escrever(
        """UPDATE cx_protocolos
              SET situacao = %s, finalizado = 0, data_finalizacao = NULL,
                  encerramento_motivo = %s
            WHERE id = %s""",
        (situacao_pelos_itens(bd, protocolo_id), historia, int(protocolo_id)))
    return {"numero": p["numero"], "motivo": limpo}


def situacao_pelos_itens(con, protocolo_id: int) -> str:
    """A situacao que os itens do protocolo produzem. So calcula.

    E A MESMA CONTA DE `caixa_web._atualizar_situacao`, e ela mora aqui para
    `reabrir` nao a escrever de novo com outras palavras. Duas versoes da conta
    que decide se um protocolo esta pago e como elas divergem — e a divergencia
    apareceria no dia em que uma delas fosse corrigida.
    """
    linha = banco(con).um(
        """SELECT count(*)::int AS total, coalesce(sum(quitado), 0)::int AS quitados
             FROM cx_protocolo_atos WHERE protocolo_id = %s""",
        (int(protocolo_id),))
    if not linha["total"]:
        return "ABERTO"
    return "PAGO" if linha["quitados"] >= linha["total"] else "A_PAGAR"


def abertos_sem_item(con, limite: int = 200) -> list[dict]:
    """Os protocolos abertos que nunca ganharam item — os candidatos a encerrar.

    E A LISTA QUE FAZ O DEBITO CABER NUMA TELA. Sao 640 no acervo desta casa, e
    procurar um a um na lista geral de 21.348 seria o mesmo que nao ter a
    funcao. Ordenados do mais antigo para o mais novo: quem esta parado ha mais
    tempo e quem menos vai voltar.
    """
    return banco(con).ler(
        """SELECT p.* FROM cx_protocolos p
            WHERE p.situacao = 'ABERTO'
              AND NOT EXISTS (SELECT 1 FROM cx_protocolo_atos a
                               WHERE a.protocolo_id = p.id)
            ORDER BY p.data_abertura, p.id
            LIMIT %s""", (int(limite),))


def quantos_abertos_sem_item(con) -> int:
    """O total, para a tela dizer quantos ficaram de fora do limite.

    Lista cortada que nao diz que cortou faz quem a le achar que acabou — e
    este projeto ja pagou por isso: «varredor que deixa de achar passa calado».
    """
    return int(banco(con).valor(
        """SELECT count(*) FROM cx_protocolos p
            WHERE p.situacao = 'ABERTO'
              AND NOT EXISTS (SELECT 1 FROM cx_protocolo_atos a
                               WHERE a.protocolo_id = p.id)"""))

def _tem_coluna(con, tabela: str, coluna: str) -> bool:
    """A coluna existe nesta base? So le — bases antigas podem nao ter migrado."""
    return banco(con).tem_coluna(tabela, coluna)


def prenotacao_por_id(con, ri_protocolo_id: int) -> dict | None:
    """A prenotacao do RI pelo id interno. So le. Nao inventa."""
    if not _tem_tabela(con, "ri_protocolos"):
        return None
    return banco(con).um(
        """SELECT id, numero, livro, situacao, apresentante, natureza_titulo,
                  matricula_id, matricula_numero, data_prenotacao
             FROM ri_protocolos WHERE id = %s""",
        (int(ri_protocolo_id),))


def _tem_tabela(con, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


def prenotacoes_abertas(con, *, limite: int = 80,
                        busca: str | None = None) -> list[dict]:
    """Prenotacoes do Livro 1 para o balcao escolher o vinculo. So le.

    A lista e humana: o escrevente aponta a prenotacao; o sistema nao junta
    por nome do interessado nem por coincidencia de numero do caixa.
    """
    if not _tem_tabela(con, "ri_protocolos"):
        return []
    # A busca não liga para maiúscula (ILIKE), como o LIKE do SQLite não
    # ligava; e o termo vai como parâmetro — nunca dentro do texto do SQL.
    onde = ["situacao = 'ABERTO'"]
    params: dict = {"limite": int(limite)}
    termo = (busca or "").strip()
    if termo:
        onde.append(
            "(numero::text ILIKE %(termo)s OR apresentante ILIKE %(termo)s "
            "OR matricula_numero::text ILIKE %(termo)s "
            "OR natureza_titulo ILIKE %(termo)s)")
        params["termo"] = f"%{termo}%"
    return banco(con).ler(
        f"""SELECT id, numero, livro, situacao, apresentante, natureza_titulo,
                   matricula_id, matricula_numero, data_prenotacao
              FROM ri_protocolos
             WHERE {' AND '.join(onde)}
             ORDER BY numero DESC
             LIMIT %(limite)s""", params)


def vincular_ri(con, protocolo_id: int,
                ri_protocolo_id: int) -> dict:
    """Grava a ponte cx_protocolos.ri_protocolo_id -> ri_protocolos. ESCREVE.

    O vinculo so nasce de escolha humana (ou de evidencia ja gravada em outro
    lugar da casa). Aqui a prenotacao tem de existir; a matricula so entra se
    a propria prenotacao ja trouxer matricula_id — nao se inventa matrícula
    a partir do texto.
    """
    bd = banco(con)
    if not _tem_coluna(bd, "cx_protocolos", "ri_protocolo_id"):
        raise ProtocoloError(
            "Esta base ainda nao tem a coluna ri_protocolo_id no protocolo "
            "geral. Atualize o esquema do caixa antes de vincular.")
    p = _protocolo(bd, protocolo_id)
    prenot = prenotacao_por_id(bd, ri_protocolo_id)
    if not prenot:
        raise ProtocoloError(
            f"Nao achei a prenotacao id {ri_protocolo_id}. Confira o numero "
            f"no Livro 1 antes de vincular.")

    matricula_id = prenot.get("matricula_id")
    tem_mat = _tem_coluna(bd, "cx_protocolos", "ri_matricula_id")
    if tem_mat:
        bd.escrever(
            """UPDATE cx_protocolos
                  SET ri_protocolo_id = %s, ri_matricula_id = %s
                WHERE id = %s""",
            (int(ri_protocolo_id),
             int(matricula_id) if matricula_id else None,
             int(protocolo_id)))
    else:
        bd.escrever(
            """UPDATE cx_protocolos SET ri_protocolo_id = %s WHERE id = %s""",
            (int(ri_protocolo_id), int(protocolo_id)))
    return {
        "protocolo_id": int(protocolo_id),
        "protocolo_numero": p["numero"],
        "ri_protocolo_id": int(ri_protocolo_id),
        "prenotacao_numero": prenot["numero"],
        "prenotacao_livro": prenot.get("livro"),
        "ri_matricula_id": int(matricula_id) if matricula_id else None,
    }


def desvincular_ri(con, protocolo_id: int) -> dict:
    """Tira a ponte com a prenotacao. ESCREVE.

    Desvincular nao apaga a prenotacao nem o protocolo: so desfaz a ligacao
    que o balcao tinha apontado. Erro se conserta a vista.
    """
    bd = banco(con)
    p = _protocolo(bd, protocolo_id)
    anterior = p.get("ri_protocolo_id")
    if _tem_coluna(bd, "cx_protocolos", "ri_matricula_id"):
        bd.escrever(
            """UPDATE cx_protocolos
                  SET ri_protocolo_id = NULL, ri_matricula_id = NULL
                WHERE id = %s""", (int(protocolo_id),))
    else:
        bd.escrever(
            """UPDATE cx_protocolos SET ri_protocolo_id = NULL WHERE id = %s""",
            (int(protocolo_id),))
    return {
        "protocolo_id": int(protocolo_id),
        "protocolo_numero": p["numero"],
        "ri_protocolo_id_anterior": anterior,
    }


def backfill_por_deposito(con, *, dry_run: bool = True) -> dict:
    """Propaga ri_protocolo_id do deposito para o protocolo de caixa. So evidencia.

    Unico caminho seguro automatico: o deposito ja aponta para a prenotacao
    (`cx_depositos.ri_protocolo_id`) E para o protocolo de caixa
    (`cx_depositos.protocolo_id`), e o protocolo ainda esta sem a ponte.
    Nao junta por interessado, numero ou assunto.
    """
    bd = banco(con)
    if not _tem_coluna(bd, "cx_protocolos", "ri_protocolo_id"):
        return {"candidatos": 0, "aplicados": 0, "dry_run": dry_run,
                "motivo": "coluna ausente"}
    if not _tem_coluna(bd, "cx_depositos", "ri_protocolo_id"):
        return {"candidatos": 0, "aplicados": 0, "dry_run": dry_run,
                "motivo": "deposito sem coluna"}
    # ORDER BY: sem ele o PostgreSQL devolve em qualquer ordem, e o relatório
    # do backfill mudaria de uma rodada para outra.
    rows = bd.ler(
        """SELECT d.id AS deposito_id, d.protocolo_id, d.ri_protocolo_id,
                  c.ri_protocolo_id AS cx_ri
             FROM cx_depositos d
             JOIN cx_protocolos c ON c.id = d.protocolo_id
            WHERE d.ri_protocolo_id IS NOT NULL
              AND d.protocolo_id IS NOT NULL
              AND c.ri_protocolo_id IS NULL
            ORDER BY d.id""")
    aplicados = 0
    detalhes = []
    for r in rows:
        item = {
            "deposito_id": r["deposito_id"],
            "protocolo_id": r["protocolo_id"],
            "ri_protocolo_id": r["ri_protocolo_id"],
        }
        if not dry_run:
            feito = vincular_ri(bd, int(r["protocolo_id"]),
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


def itens_disponiveis(con, protocolo_id) -> list[dict]:
    """Os itens do protocolo com saldo, já com `saldo` dentro. Só LÊ.

    **A LISTA É POR SALDO, E NÃO POR `usado_em IS NULL`** — era essa condição
    que fazia o item de cinco averbações desaparecer depois da primeira.
    """
    if protocolo_id is None or not str(protocolo_id).strip().isdigit():
        return []
    saida = []
    for r in banco(con).ler(
            """SELECT * FROM cx_protocolo_atos
                WHERE protocolo_id = %s
                  AND codigo_ato IS NOT NULL AND btrim(codigo_ato) <> ''
                ORDER BY id""", (int(protocolo_id),)):
        sobra = saldo_do_item(r)
        if sobra > 0:
            saida.append(r | {"saldo": sobra, "quantidade_usada": _usadas(r)})
    return saida


def consumir_item(con, item_id: int, *, ato_id: int,
                  tabela: str, agora: str, quantas: int = 1,
                  origem: str = "CONSUMO", quem: str | None = None) -> int:
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
    bd = banco(con)
    # FOR UPDATE: o saldo é lido e gravado na mesma transação, com a linha
    # presa — dois atos lavrados ao mesmo tempo não gastam a mesma unidade.
    bd._escrita()
    linha = bd.um("SELECT * FROM cx_protocolo_atos WHERE id = %s FOR UPDATE",
                  (int(item_id),))
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
    bd.escrever(
        """UPDATE cx_protocolo_atos
              SET quantidade_usada = %s,
                  usado_em = CASE WHEN %s THEN coalesce(usado_em, %s) ELSE usado_em END,
                  usado_por_ato_id = coalesce(usado_por_ato_id, %s),
                  usado_por_tabela = coalesce(usado_por_tabela, %s)
            WHERE id = %s""",
        (usadas, fechou, agora, int(ato_id), tabela, int(item_id)))
    # O RASTRO DE CADA ATO, E NÃO SÓ DO PRIMEIRO (LX16, 19/10/2026). A trava
    # do selo pergunta «este ato está ligado a que item?», e `usado_por_ato_id`
    # só guarda quem abriu o item: no item de cinco averbações, a segunda em
    # diante ficaria sem protocolo aos olhos da trava, e sem selo.
    _anotar_item_do_ato(bd, linha, tabela=tabela, ato_id=ato_id,
                        unidades=gastar, origem=origem, agora=agora, quem=quem)
    return gastar


def devolver_item(con, item_id: int, *,
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
    bd = banco(con)
    bd._escrita()
    item = bd.um("SELECT * FROM cx_protocolo_atos WHERE id = %s FOR UPDATE",
                 (int(item_id),))
    if item is None:
        return 0
    usadas = _usadas(item)
    voltam = max(0, min(int(quantas or 0), usadas))
    if not voltam:
        return 0
    fica = usadas - voltam
    zerou = (fica == 0)
    bd.escrever(
        """UPDATE cx_protocolo_atos
              SET quantidade_usada = %(fica)s,
                  usado_em = CASE WHEN %(zerou)s THEN NULL ELSE usado_em END,
                  usado_por_ato_id = CASE WHEN %(zerou)s THEN NULL
                                          ELSE usado_por_ato_id END,
                  usado_por_tabela = CASE WHEN %(zerou)s THEN NULL
                                          ELSE usado_por_tabela END
            WHERE id = %(id)s""",
        {"fica": fica, "zerou": zerou, "id": int(item_id)})
    return voltam


def soltar_itens_do_ato(con, tabela: str, ato_id: int) -> int:
    """Devolve ao protocolo os itens marcados para um ato cancelado. ESCREVE.

    O ESPELHO DA MARCA DAS TELAS — `atribuicoes_web.
    _marcar_itens_do_protocolo_como_usados`, que liga o item ao ato ANTES do
    selo, e é por ela que a trava do selo acha o item pago daquele ato. Quando
    o selo não saía e a certidão era cancelada, a marca ficava: o item seguia
    «usado» por uma certidão que não existe, e o pedido seguinte do mesmo
    protocolo não o achava — a certidão do RTD saía EMITIDA, SEM SELO e sem
    aviso (LT05; CN-MA art. 130, § 2º).

    Só solta a marca inteira, a que não conta unidade (`quantidade_usada`
    vazio ou zero); o consumo por unidade tem o seu espelho, `devolver_item`.
    Presos na ordem do id, como o resto do caixa. Devolve quantos voltaram.
    """
    bd = banco(con)
    bd._escrita()
    presos = [int(r["id"]) for r in bd.ler(
        """SELECT id FROM cx_protocolo_atos
            WHERE usado_por_tabela = %s AND usado_por_ato_id = %s
              AND coalesce(quantidade_usada, 0) = 0
            ORDER BY id FOR UPDATE""", (str(tabela), int(ato_id)))]
    if presos:
        bd.escrever(
            """UPDATE cx_protocolo_atos
                  SET usado_em = NULL, usado_por_ato_id = NULL, usado_por_tabela = NULL
                WHERE id = ANY(%s)""", (presos,))
    return len(presos)


# ------------------------------------------- a cobertura do selo (LX16)
#
# «os selos pagos precisam estar sempre vinculados a um protocolo geral e à
#  confirmação da entrada de um dinheiro» — o oficial, 19/10/2026
#
# O CAIXA RESPONDE, O SELO PERGUNTA. A trava mora em `ato_selado.obter_selo`,
# o ponto por onde todo selo passa; o que ela pergunta — «este ato tem item de
# protocolo? o item foi pago? o Protesto diferiu?» — é conta do caixa, e mora
# aqui para haver UMA régua do que é «pago». Escrita na trava, ela divergiria
# da ficha do protocolo no primeiro conserto.

#: De onde veio o rastro em `cx_item_do_ato`. `CONSUMO` é a tela do ato que
#: gastou a unidade (RTD, RI, apostila); `QUADRO` é o escrevente que ligou o
#: ato ao item no quadro «Para selar este ato falta»; `SELO` é a própria
#: trava, que gasta UMA UNIDADE POR SELO quando acha o item no protocolo em
#: atendimento — a conta da casa é por unidade («item 13.18 com quantidade 10,
#: e saíram 10 selos»).
ORIGEM_CONSUMO = "CONSUMO"
ORIGEM_QUADRO = "QUADRO"
ORIGEM_SELO = "SELO"

#: Onde o emolumento é DIFERIDO por lei, sem dinheiro antes: o Protesto
#: «a posteriori» e os títulos da CRA, em que quem paga é o devedor, no fim.
#: Diferir em qualquer outra atribuição seria selo pago sem pagamento — que é
#: exatamente o que a trava existe para impedir.
ATRIBUICOES_QUE_DIFEREM = frozenset({"PROTESTO"})
TABELAS_QUE_DIFEREM = frozenset({"pt_atos"})

SCHEMA_COBERTURA = """
CREATE TABLE IF NOT EXISTS cx_item_do_ato (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    item_id bigint NOT NULL,
    protocolo_id bigint NOT NULL,
    tabela TEXT NOT NULL,
    ato_id bigint NOT NULL,
    unidades integer NOT NULL DEFAULT 0,
    origem TEXT NOT NULL DEFAULT 'CONSUMO',
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    UNIQUE (tabela, ato_id, item_id, origem)
);
CREATE INDEX IF NOT EXISTS ix_cx_item_do_ato_item ON cx_item_do_ato (item_id);
CREATE TABLE IF NOT EXISTS cx_atendimento (
    usuario TEXT PRIMARY KEY,
    protocolo_id bigint NOT NULL,
    desde TEXT NOT NULL
)
"""

# O diferimento é do ITEM, e não do protocolo: um protocolo do Protesto pode
# ter a certidão paga no balcão e o protesto «a posteriori» no mesmo papel.
COLUNAS_DO_DIFERIMENTO = ("diferido_quem", "diferido_quando",
                          "diferido_motivo", "diferido_em", "diferido_por")


def init_cobertura_schema(con) -> None:
    """O rastro ato↔item, o protocolo em atendimento e o diferimento.

    Idempotente, como o resto. Vem DEPOIS do esquema do caixa: as colunas do
    diferimento entram em `cx_protocolo_atos`.
    """
    bd = banco(con)
    for comando in SCHEMA_COBERTURA.split(";\n"):
        if comando.strip():
            bd.escrever(comando)
    for coluna in COLUNAS_DO_DIFERIMENTO:
        if not bd.tem_coluna("cx_protocolo_atos", coluna):
            bd.escrever(f"ALTER TABLE cx_protocolo_atos ADD COLUMN {coluna} TEXT")


def _anotar_item_do_ato(bd: Banco, item, *, tabela: str, ato_id: int,
                        unidades: int, origem: str, agora: str,
                        quem: str | None) -> None:
    """Grava que este ato gastou unidades deste item. ESCREVE.

    Banco montado à mão (há testes assim) não tem a tabela, e o consumo vale
    do mesmo jeito: o rastro é a mais, não a condição do consumo.
    """
    if not bd.tem_tabela("cx_item_do_ato"):
        return
    bd.escrever(
        """INSERT INTO cx_item_do_ato
               (item_id, protocolo_id, tabela, ato_id, unidades, origem,
                criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (tabela, ato_id, item_id, origem)
           DO UPDATE SET unidades = cx_item_do_ato.unidades + EXCLUDED.unidades""",
        (int(item["id"]), int(item["protocolo_id"]), str(tabela), int(ato_id),
         int(unidades), str(origem or ORIGEM_CONSUMO), agora, quem))


def itens_do_ato(con, tabela: str, ato_id: int) -> list[dict]:
    """Os itens de protocolo a que este ato já está ligado. Só LÊ.

    Ligado é: a tela do ato gastou a unidade (`cx_item_do_ato`, ou o rastro
    antigo `usado_por_*`, que guarda só o primeiro ato) ou o escrevente ligou
    no quadro. **O que a própria trava gastou (`SELO`) não conta aqui** — ali
    a conta é por selo, e contar o item como «já ligado» deixaria a segunda
    folha autenticada sair sem gastar a segunda unidade.
    """
    bd = banco(con)
    if not bd.tem_tabela("cx_protocolo_atos"):
        return []
    if bd.tem_tabela("cx_item_do_ato"):
        extra = """ OR i.id IN (SELECT v.item_id FROM cx_item_do_ato v
                                 WHERE v.tabela = %(t)s AND v.ato_id = %(a)s
                                   AND v.origem <> %(selo)s)"""
        # O RASTRO ANTIGO TAMBÉM NÃO VALE QUANDO QUEM O ESCREVEU FOI A
        # TRAVA (LX22A3, 20/10/2026). `consumir_item` grava `usado_por_*`
        # em todo consumo, inclusive no do selo: a primeira folha
        # autenticada deixava o item «ligado» por ali, e a segunda saía por
        # ele sem gastar a segunda unidade — duas folhas, dois selos, uma
        # unidade paga.
        antigo = """ AND NOT EXISTS (SELECT 1 FROM cx_item_do_ato s
                                      WHERE s.item_id = i.id AND s.tabela = %(t)s
                                        AND s.ato_id = %(a)s
                                        AND s.origem = %(selo)s)"""
    else:
        extra = antigo = ""
    return bd.ler(
        f"""SELECT i.*, p.numero AS protocolo_numero,
                   p.situacao AS protocolo_situacao,
                   p.atribuicao AS protocolo_atribuicao
              FROM cx_protocolo_atos i
              JOIN cx_protocolos p ON p.id = i.protocolo_id
             WHERE (i.usado_por_tabela = %(t)s AND i.usado_por_ato_id = %(a)s{antigo}){extra}
             ORDER BY i.id""",
        {"t": str(tabela), "a": int(ato_id), "selo": ORIGEM_SELO})


def item_do_protocolo(con, item_id: int) -> dict | None:
    """Um item do protocolo, com o número e a situação do protocolo. Só LÊ."""
    return banco(con).um(
        """SELECT i.*, p.numero AS protocolo_numero,
                  p.situacao AS protocolo_situacao,
                  p.atribuicao AS protocolo_atribuicao
             FROM cx_protocolo_atos i
             JOIN cx_protocolos p ON p.id = i.protocolo_id
            WHERE i.id = %s""", (int(item_id),))


def _sim(valor) -> bool:
    try:
        return bool(int(valor or 0))
    except (TypeError, ValueError):
        return str(valor or "").strip().lower() in ("true", "sim", "s")


def item_pago(linha) -> bool:
    """O item tem registro de que foi pago? Só calcula.

    Quitado item a item (`quitado`), protocolo inteiro pago (a situação que o
    caixa deduz dos itens — e a que veio do E-Ofício já assim) ou item
    GRATUITO, em que não há o que pagar. O item quitado pelo depósito prévio
    também fica `quitado` — ver `caixa_depositos.pagar_item`.
    """
    return (_sim(linha.get("quitado"))
            or str(linha.get("protocolo_situacao") or "").upper() == "PAGO"
            or _sim(linha.get("gratuito")))


def item_diferido(linha) -> bool:
    """O item tem o registro do diferimento — quem paga e quando? Só calcula."""
    return bool(str(linha.get("diferido_quem") or "").strip()
                and str(linha.get("diferido_quando") or "").strip())


def registrar_diferimento(con, item_id: int, *, quem_paga: str, quando: str,
                          motivo: str, por: str | None, agora: str) -> dict:
    """O emolumento que a lei manda pagar DEPOIS: quem paga e quando. ESCREVE.

    Só do Protesto («a posteriori» e títulos da CRA). Não é desconto nem
    gratuidade: o valor continua devido, e o item continua aparecendo como
    não quitado na ficha do protocolo até o devedor pagar.
    """
    bd = banco(con)
    linha = item_do_protocolo(bd, item_id)
    if not linha:
        raise ProtocoloError("Não achei este item do protocolo.")
    if str(linha["protocolo_atribuicao"] or "").upper() not in ATRIBUICOES_QUE_DIFEREM:
        raise ProtocoloError(
            "Só o Protesto difere o emolumento (a posteriori e títulos da "
            "CRA). Nas outras atribuições o selo pago espera o pagamento.")
    quem_paga = str(quem_paga or "").strip()
    if len(quem_paga) < 3:
        raise ProtocoloError("Diga quem vai pagar (o devedor, o banco...).")
    try:
        dia = date.fromisoformat(str(quando or "").strip()[:10])
    except ValueError:
        raise ProtocoloError("Diga quando o pagamento vence (uma data).") from None
    motivo = str(motivo or "").strip()
    if len(motivo) < MINIMO_DO_MOTIVO:
        raise ProtocoloError(
            "Escreva o fundamento do diferimento (a posteriori, CRA...), "
            "com pelo menos dez letras.")
    bd.escrever(
        """UPDATE cx_protocolo_atos
              SET diferido_quem = %s, diferido_quando = %s, diferido_motivo = %s,
                  diferido_em = %s, diferido_por = %s
            WHERE id = %s""",
        (quem_paga, dia.isoformat(), motivo, agora, por, int(item_id)))
    return {"item_id": int(item_id), "quem": quem_paga, "quando": dia.isoformat()}


def atualizar_situacao(con, protocolo_id: int) -> str:
    """Regrava a situação do protocolo pelos itens. ESCREVE.

    Protocolo encerrado (ENTREGUE/CANCELADO) não se move — é a mesma guarda de
    `caixa_web._atualizar_situacao`.
    """
    bd = banco(con)
    atual = bd.um("SELECT situacao FROM cx_protocolos WHERE id = %s",
                  (int(protocolo_id),))
    if not atual or esta_encerrado(atual["situacao"]):
        return str((atual or {}).get("situacao") or "")
    nova = situacao_pelos_itens(bd, protocolo_id)
    bd.escrever(
        "UPDATE cx_protocolos SET situacao = %s, finalizado = %s WHERE id = %s",
        (nova, 1 if nova == "PAGO" else 0, int(protocolo_id)))
    return nova


# O PROTOCOLO EM ATENDIMENTO — o escrevente diz UMA VEZ «estou atendendo o
# 2026.10.15», e todo selo pago que ele tirar a seguir procura o item ali.
#
#   Sem isto, cada tela que sela precisaria de um campo de protocolo, e o
#   reconhecimento de firma — metade dos selos da casa — desfaz o ato quando
#   o selo não sai: não haveria «depois» para ligar o ato ao item. O item é
#   achado pelo CÓDIGO da tabela (o item 13.1 paga o selo do 13.1, e não o do
#   14.5.1); o envelope sem código só usa o item se ele for o único com saldo.


def _usuario(usuario) -> str:
    return " ".join(str(usuario or "").split()).upper()


def atender(con, *, usuario: str, protocolo, agora: str) -> dict:
    """Marca o protocolo que este escrevente está atendendo. ESCREVE.

    `protocolo` é o número (`2026.10.15`) ou o id. Protocolo encerrado não se
    atende: o atendimento terminou.
    """
    bd = banco(con)
    quem = _usuario(usuario)
    if not quem:
        raise ProtocoloError("Entre com o seu usuário para atender um protocolo.")
    bruto = str(protocolo or "").strip()
    p = bd.um("SELECT id, numero, situacao FROM cx_protocolos WHERE numero = %s "
              "ORDER BY id LIMIT 1", (bruto,))
    if not p and bruto.isdigit():
        p = bd.um("SELECT id, numero, situacao FROM cx_protocolos WHERE id = %s",
                  (int(bruto),))
    if not p:
        raise ProtocoloError(
            f"Não achei o protocolo «{bruto}». Confira o número no papel do "
            f"balcão (ano.mês.número) ou abra um protocolo novo no caixa.")
    if esta_encerrado(p["situacao"]):
        raise ProtocoloError(
            f"O protocolo {p['numero']} já foi encerrado ({p['situacao']}). "
            f"Abra um protocolo novo para este atendimento.")
    bd.escrever(
        """INSERT INTO cx_atendimento (usuario, protocolo_id, desde)
           VALUES (%s, %s, %s)
           ON CONFLICT (usuario) DO UPDATE
              SET protocolo_id = EXCLUDED.protocolo_id, desde = EXCLUDED.desde""",
        (quem, int(p["id"]), agora))
    return {"protocolo_id": int(p["id"]), "numero": p["numero"]}


def em_atendimento(con, usuario) -> dict | None:
    """O protocolo que este escrevente está atendendo, ou None. Só LÊ."""
    bd = banco(con)
    quem = _usuario(usuario)
    if not quem or not bd.tem_tabela("cx_atendimento"):
        return None
    return bd.um(
        """SELECT p.*, a.desde AS atendendo_desde
             FROM cx_atendimento a JOIN cx_protocolos p ON p.id = a.protocolo_id
            WHERE a.usuario = %s""", (quem,))


def encerrar_atendimento(con, usuario) -> None:
    """Tira o protocolo em atendimento deste escrevente. ESCREVE."""
    banco(con).escrever("DELETE FROM cx_atendimento WHERE usuario = %s",
                        (_usuario(usuario),))


def itens_para_o_selo(con, protocolo_id, codigo: str | None) -> list[dict]:
    """Os itens do protocolo que podem pagar o selo deste código. Só LÊ.

    Com código, só o item do MESMO código. Sem código (envelope que não o
    leva), só se houver um item com saldo — escolher entre dois seria
    adivinhar qual serviço o cliente pagou.
    """
    candidatos = [
        r | {"protocolo_situacao": None}
        for r in itens_disponiveis(con, protocolo_id)]
    if not candidatos:
        return []
    p = banco(con).um("SELECT numero, situacao, atribuicao FROM cx_protocolos "
                      "WHERE id = %s", (int(protocolo_id),))
    for r in candidatos:
        r["protocolo_situacao"] = (p or {}).get("situacao")
        r["protocolo_numero"] = (p or {}).get("numero")
        r["protocolo_atribuicao"] = (p or {}).get("atribuicao")
    codigo = str(codigo or "").strip()
    if codigo:
        return [r for r in candidatos
                if str(r.get("codigo_ato") or "").strip() == codigo]
    return candidatos if len(candidatos) == 1 else []


# ------------------------------------------- o protocolo que o escrevente ESCOLHE
#
# A TRAVA DE 19/10 SÓ ENXERGAVA O PROTOCOLO «EM ATENDIMENTO», e o passo de
# atender morava escondido em «Selo e caixa». Em 22/10/2026, primeiro dia na
# 3.7.0, nenhum selo saiu: a firma com o item 13.17.4 pago no protocolo
# 2026.10.60 e as certidões do RI com o 16.24.4 pago no 2026.10.61 ficaram
# «aguardando cobertura», porque ninguém tinha marcado o atendimento.
#
#   A SAÍDA É MOSTRAR OS CANDIDATOS NA TELA DO ATO, e não escolher por ele.
#   Decisão do oficial, 22/10/2026: «escrevente confirma». Com um protocolo
#   pago só na casa, escolher sozinho faria o selo do cliente que não pagou
#   gastar o pagamento do cliente que pagou — e ninguém veria. O candidato
#   único vem marcado; quem confirma é a pessoa que está com o cliente.

#: Até quantos dias para trás um protocolo aberto ainda é candidato.
DIAS_DOS_CANDIDATOS = 30


def pedidos_do_selo(pedidos) -> list[tuple[str, int]]:
    """[(código, quantidade), ...] limpo e somado por código. Só calcula.

    Aceita só o código (`"13.17.4"`) ou o par. A certidão do RI manda dois
    selos de códigos diferentes (16.24.4 e 16.24.4.1, folhas − 1); o mesmo
    código repetido soma, porque o saldo do item é um só.
    """
    soma: dict[str, int] = {}
    for p in pedidos or ():
        if isinstance(p, (list, tuple)):
            codigo, quantidade = (list(p) + [1])[:2]
        else:
            codigo, quantidade = p, 1
        codigo = str(codigo or "").strip()
        if not codigo:
            continue
        try:
            q = int(quantidade or 1)
        except (TypeError, ValueError):
            q = 1
        soma[codigo] = soma.get(codigo, 0) + max(1, q)
    return list(soma.items())


def candidatos_para_o_selo(con, pedidos, *, atribuicoes=None,
                           dias: int = DIAS_DOS_CANDIDATOS, hoje=None,
                           pre_marcar_protocolo_id=None,
                           limite: int = 20) -> list[dict]:
    """Os protocolos que podem pagar estes selos, para o escrevente escolher. Só LÊ.

    `pedidos` é `[(código, quantidade), ...]`. Entram os protocolos não
    encerrados, abertos nos últimos `dias` (ou o de `pre_marcar_protocolo_id`,
    seja de quando for), da atribuição do ato (`atribuicoes`, um conjunto; None
    não filtra) e com ao menos um item do código pedido com unidade sobrando.

    Cada candidato traz, por código pedido, o saldo PAGO e o saldo total, e
    `cobre_tudo` diz se ele paga todos os selos na quantidade pedida. O que
    não cobre continua na lista com `faltam` dizendo quanto — é isso que a
    tela mostra antes do clique («faltam 2 unidades do 16.24.4.1»).
    """
    from datetime import date, timedelta
    pedidos = pedidos_do_selo(pedidos)
    bd = banco(con)
    if not pedidos or not bd.tem_tabela("cx_protocolo_atos"):
        return []
    hoje = hoje or date.today()
    if isinstance(hoje, str):
        hoje = date.fromisoformat(hoje[:10])
    desde = (hoje - timedelta(days=int(dias))).isoformat()
    try:
        pre = int(pre_marcar_protocolo_id)
    except (TypeError, ValueError):
        pre = -1
    atribuicoes = ({str(a).upper() for a in atribuicoes}
                   if atribuicoes is not None else None)
    # O CÓDIGO TERMINADO EM «*» É FAMÍLIA (22/10/2026): a tela que ainda não
    # sabe o item exato — a habilitação, o assento, antes de escolher a
    # espécie — pede «14.*», e entram os itens do grupo da tabela do TJ.
    exatos = [c for c, _ in pedidos if not c.endswith("*")]
    familias = [c[:-1] for c, _ in pedidos if c.endswith("*")]
    filtro = ["btrim(i.codigo_ato) = ANY(%s)"]
    parametros: list = [exatos]
    for f in familias:
        filtro.append("starts_with(btrim(i.codigo_ato), %s)")
        parametros.append(f)
    linhas = bd.ler(
        f"""SELECT i.*, p.numero AS protocolo_numero,
                  p.situacao AS protocolo_situacao,
                  p.atribuicao AS protocolo_atribuicao,
                  p.interessado AS protocolo_interessado,
                  p.data_abertura AS protocolo_data
             FROM cx_protocolo_atos i
             JOIN cx_protocolos p ON p.id = i.protocolo_id
            WHERE ({' OR '.join(filtro)})
              AND (p.data_abertura >= %s OR p.id = %s)
            ORDER BY p.id DESC, i.id""", tuple(parametros) + (desde, pre))
    por_protocolo: dict[int, dict] = {}
    for r in linhas:
        if esta_encerrado(r.get("protocolo_situacao")):
            continue
        atrib = str(r.get("protocolo_atribuicao") or "").upper()
        if atribuicoes is not None and atrib and atrib not in atribuicoes:
            continue
        sobra = saldo_do_item(r)
        if sobra <= 0:
            continue
        c = por_protocolo.setdefault(int(r["protocolo_id"]), {
            "protocolo_id": int(r["protocolo_id"]),
            "numero": r.get("protocolo_numero"),
            "interessado": r.get("protocolo_interessado"),
            "atribuicao": atrib or None,
            "data_abertura": r.get("protocolo_data"),
            "situacao": r.get("protocolo_situacao"),
            "itens": [], "por_codigo": {}})
        pago = item_pago(r)
        c["itens"].append({"id": int(r["id"]), "codigo": str(r["codigo_ato"]).strip(),
                           "descricao": r.get("descricao"), "saldo": sobra,
                           "pago": pago})
        conta = c["por_codigo"].setdefault(str(r["codigo_ato"]).strip(),
                                           {"saldo_pago": 0, "saldo": 0})
        conta["saldo"] += sobra
        if pago:
            conta["saldo_pago"] += sobra
    saida = []
    for c in por_protocolo.values():
        faltam = []
        for codigo, quantidade in pedidos:
            if codigo.endswith("*"):
                prefixo = codigo[:-1]
                casam = [v for k, v in c["por_codigo"].items() if k.startswith(prefixo)]
                conta = {"saldo_pago": sum(v["saldo_pago"] for v in casam),
                         "saldo": sum(v["saldo"] for v in casam)}
            else:
                conta = c["por_codigo"].get(codigo, {"saldo_pago": 0, "saldo": 0})
            if conta["saldo_pago"] < quantidade:
                faltam.append({"codigo": codigo, "pedidas": quantidade,
                               "saldo_pago": conta["saldo_pago"],
                               "saldo": conta["saldo"],
                               "faltam": quantidade - conta["saldo_pago"]})
        c["faltam"] = faltam
        c["cobre_tudo"] = not faltam
        c["pre_marcado"] = c["protocolo_id"] == pre
        saida.append(c)
    saida.sort(key=lambda c: (not c["pre_marcado"], not c["cobre_tudo"],
                              -c["protocolo_id"]))
    return saida[:max(1, int(limite))]

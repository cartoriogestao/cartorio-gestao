"""A retificação de área e o georreferenciamento, como processo.

    «vamos criar o módulo de processos de retificação de área e
     georreferenciamento» — o oficial, 29/08/2026

A NORMA MORA EM `rt_tjma.py`, E NÃO AQUI
    Lá estão os arts. 587 a 620 do Código de Normas do TJMA, com o artigo ao
    lado de cada regra, lidos do PDF que está na casa. Aqui está o que o
    processo FAZ com eles. Escrever a norma nos dois lugares faria as duas
    versões divergirem no primeiro conserto — e num prazo, divergir é recomeçar.

O QUE ESTE MÓDULO NÃO FAZ, E CADA UM TEM MOTIVO
    **Não averba.** Quem lavra é a tela do Registro de Imóveis, que tem a
    corrente de hash, o selo, os emolumentos e o nome de quem assina. Um atalho
    de um clique pularia os quatro — é a decisão do CNIB, e o desfecho aqui é
    ainda maior: encerra uma matrícula e abre outra.

    **Não julga a impugnação.** Se ela procede é matéria de direito, e o art.
    604 diz «decisão fundamentada» **do oficial**. Sexta vez que esta regra
    aparece neste projeto — usucapião, fraudes, habilitação, CNIB, ajuda, e
    agora. Há teste que varre os nomes públicos.

    **Não calcula data.** Contar dia útil é do núcleo, que já conhece os
    feriados desta comarca. Uma segunda contagem divergiria da prenotação e da
    do edital do usucapião. Quando o prazo nasce de um ato registrado aqui (o
    recurso, as contrarrazões e a transação do art. 600), `prazo_ate` pede a
    data ao núcleo — `ri_schema.soma_dias_uteis` com os feriados da casa.
"""
from __future__ import annotations

import sqlite3

from bd_nativo import banco
from typing import Any

import rt_tjma as NORMA


class RetificacaoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


# ------------------------------------------------------------------- as fases
#
# A ordem e a do rito, e ela **nao se pula**: cada fase protege alguem — o
# confrontante, o credor real, o terceiro do edital. Voltar e permitido:
# diligencia nova devolve o processo a fase anterior, como no usucapiao.
FASES: tuple[tuple[str, str], ...] = (
    ("AUTUACAO", "Autuação — o requerimento entrou"),
    ("QUALIFICACAO", "Qualificação — o oficial analisa (10 dias úteis, art. 597)"),
    ("EXIGENCIA", "Nota devolutiva — aguardando o requerente"),
    ("NOTIFICACAO", "Notificação dos confrontantes (art. 598)"),
    ("PRAZO", "Aguardando o prazo de impugnação (15 dias úteis, art. 599)"),
    ("IMPUGNACAO", "Impugnação oferecida (art. 600)"),
    ("MEDIACAO", "Mediação ou conciliação (15 dias úteis, art. 600, § 2º)"),
    ("AO_JUIZ", "Remetido ao Juiz corregedor permanente (art. 600, §§ 3º e "
                "5º; art. 601)"),
    ("DECISAO", "Pronto para a decisão do oficial (art. 604)"),
    ("AVERBACAO", "Decidido procedente — aguardando a averbação"),
    ("SIGEF", "Averbado — requerer o registro no SIGEF (30 dias, art. 620 § 2º)"),
    ("CONCLUIDO", "Concluído"),
)

NOME_DA_FASE = dict(FASES)
ORDEM_DA_FASE = {nome: i for i, (nome, _) in enumerate(FASES)}

EM_ANDAMENTO = "EM_ANDAMENTO"
ENCERRADO = "ENCERRADO"

PROCEDENTE = "PROCEDENTE"
IMPROCEDENTE = "IMPROCEDENTE"

# Os papeis de quem se notifica. **Confrontante e credor real nao sao a mesma
# coisa**: o art. 593 e o 617 dizem que o credor real e o senhorio direto nao
# precisam ANUIR — basta a notificacao —, e que a impugnacao deles tem de ser
# fundamentada, «nao bastando mera alegacao de prejuizo».
CONFRONTANTE = "CONFRONTANTE"
CREDOR_REAL = "CREDOR_REAL"
OCUPANTE = "OCUPANTE"

PAPEIS: tuple[str, ...] = (CONFRONTANTE, CREDOR_REAL, OCUPANTE)

NOME_DO_PAPEL = {
    CONFRONTANTE: "Confrontante",
    CREDOR_REAL: "Credor real ou senhorio direto (art. 593 e 617)",
    OCUPANTE: "Ocupante que se manifestou ao edital (art. 595)",
}

# As respostas. **SILENCIO NAO E AUSENCIA DE RESPOSTA**: e a anuencia presumida
# do art. 599, § 1o, e por isso tem nome proprio. Chama-lo de «sem resposta»
# faria a tela mostrar como pendencia o que a norma ja resolveu.
ANUIU = "ANUIU"
SILENCIO = "SILENCIO"
IMPUGNOU = "IMPUGNOU"

RESPOSTAS: tuple[str, ...] = (ANUIU, SILENCIO, IMPUGNOU)

NOME_DA_RESPOSTA = {
    ANUIU: "Anuiu",
    SILENCIO: "Silêncio — anuência presumida (art. 599, § 1º)",
    IMPUGNOU: "Impugnou",
}

MINIMO_DO_MOTIVO = 10


# --------------------------------------------------------------------- leitura


def processo(con: sqlite3.Connection, processo_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM rt_processos WHERE id = %s",
                         (processo_id,))


def _exigir(con: sqlite3.Connection, processo_id: int) -> dict:
    achado = processo(con, processo_id)
    if not achado:
        raise RetificacaoError(
            f"Não achei o processo de retificação nº {processo_id}.")
    return achado


def _exigir_para_gravar(con: sqlite3.Connection, processo_id: int) -> dict:
    """O processo, com a linha PRESA até o fim da transação (FOR UPDATE).

    Para quem confere a decisão ou a averbação e grava em cima dela: duas
    decisões ao mesmo tempo leriam as duas o processo sem decisão, e as duas
    passariam. Com a linha presa, a segunda espera a primeira e lê o que ela
    gravou.
    """
    bd = banco(con)
    bd._escrita()
    bd.um("SELECT id FROM rt_processos WHERE id = %s FOR UPDATE", (processo_id,))
    return _exigir(bd, processo_id)


def confrontantes(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    return banco(con).ler(
        """SELECT * FROM rt_confrontantes WHERE processo_id = %s
            ORDER BY papel, nome, id""", (processo_id,))


def pecas(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM rt_pecas WHERE processo_id = %s ORDER BY id",
        (processo_id,))


def juntar_peca(con: sqlite3.Connection, processo_id: int, *, tipo: str,
                agora: str, descricao: str = "", arquivo: str = "",
                sha256: str = "", entregue_em: str = "",
                usuario: str | None = None) -> int:
    """Junta uma peça ao processo e aproveita para cumprir o checklist.

    A tela pode receber um upload real ou só a referência a um arquivo que já
    exista no disco. Em ambos os casos, se o `tipo` for exatamente um item da
    conferência do art. 592, esse item passa a ATENDIDO sozinho. O operador
    não precisa fazer dois lançamentos para o mesmo documento.
    """
    _exigir(con, processo_id)
    tipo = _texto(tipo)
    if not tipo:
        raise RetificacaoError("A peça precisa de tipo.")

    bd = banco(con)
    novo = int(bd.escrever(
        """INSERT INTO rt_pecas (processo_id, tipo, descricao, arquivo,
               sha256, entregue_em, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (processo_id, tipo, _texto(descricao) or None,
         _texto(arquivo) or None, _texto(sha256) or None,
         _texto(entregue_em) or None, agora, usuario))[0]["id"])

    bd.escrever(
        """UPDATE rt_conferencia
              SET situacao = 'ATENDIDO',
                  nota = COALESCE(nota, %s),
                  marcado_em = %s,
                  marcado_por = %s
            WHERE processo_id = %s AND item = %s
              AND COALESCE(situacao, 'PENDENTE') = 'PENDENTE'""",
        ("Atendido pela peça juntada.", agora, usuario, processo_id, tipo))
    _anotar(con, processo_id, tipo="PECA", quando=agora, quem=usuario,
            o_que=f"Peça juntada: {tipo}"
                  + (f" — {_texto(descricao)}" if _texto(descricao) else "."))
    return novo


def andamento(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    return banco(con).ler(
        """SELECT a.*, c.nome AS confrontante_nome
             FROM rt_andamento a
             LEFT JOIN rt_confrontantes c ON c.id = a.confrontante_id
            WHERE a.processo_id = %s ORDER BY a.id""", (processo_id,))


# ---------------------------------------------------------------------- autuar


def _texto(v: Any) -> str:
    return str(v or "").strip()


def autuar(con: sqlite3.Connection, *, numero: str, especie: str,
           fundamento: str, matricula_id: int, rural: bool, agora: str,
           requerente_nome: str = "", requerente_documento: str = "",
           usuario: str | None = None, **extras) -> int:
    """Abre o processo. ESCREVE.

    A MATRÍCULA É OBRIGATÓRIA, e é a diferença em relação ao usucapião: lá o
    imóvel pode não ter matrícula nenhuma; aqui o que se retifica **é** o
    registro, e sem ele não há o que retificar.
    """
    if especie not in NORMA.NOME_DA_ESPECIE:
        raise RetificacaoError(
            f"«{especie}» não é uma espécie de retificação. As que existem: "
            + ", ".join(f"{k} ({v})"
                        for k, v in NORMA.NOME_DA_ESPECIE.items()) + ".")
    if fundamento not in NORMA.NOME_DO_FUNDAMENTO:
        raise RetificacaoError(
            f"«{fundamento}» não é um fundamento do art. 213. Os dois são: "
            + ", ".join(f"{k} ({v})"
                        for k, v in NORMA.NOME_DO_FUNDAMENTO.items()) + ".")
    if not _texto(numero):
        raise RetificacaoError("O processo precisa de um número.")

    bd = banco(con)
    if not bd.um("SELECT 1 FROM ri_matriculas WHERE id = %s",
                 (matricula_id,)):
        raise RetificacaoError(
            f"Não achei a matrícula nº {matricula_id}. A retificação é do "
            "registro: sem matrícula não há o que retificar.")
    # TRAVA ANTES DE CONFERIR: o número é único, e dois balcões autuando o
    # mesmo número passariam os dois pela conferência — o segundo estouraria
    # a chave em vez de ouvir a frase abaixo.
    bd.travar("rt_processos.numero")
    if bd.um("SELECT 1 FROM rt_processos WHERE numero = %s",
             (_texto(numero),)):
        raise RetificacaoError(
            f"Já existe um processo de retificação com o número "
            f"{_texto(numero)}.")

    campos = {
        "numero": _texto(numero), "ano": extras.get("ano"),
        "especie": especie, "fundamento": fundamento,
        "matricula_id": int(matricula_id), "rural": 1 if rural else 0,
        "requerente_nome": _texto(requerente_nome) or None,
        "requerente_documento": _texto(requerente_documento) or None,
        "criado_em": agora, "criado_por": usuario,
    }
    for chave in ("profissional_nome", "profissional_conselho",
                  "profissional_registro", "art_numero", "area_na_matricula",
                  "area_pretendida", "perimetro", "certificacao_incra",
                  "sigef_codigo", "prenotacao", "prenotacao_id",
                  "protocolo_id", "observacao"):
        if chave in extras:
            campos[chave] = extras[chave] or None

    colunas = ", ".join(campos)
    marcas = ", ".join("%s" for _ in campos)
    novo = int(bd.escrever(
        f"INSERT INTO rt_processos ({colunas}) VALUES ({marcas}) "
        "RETURNING id", tuple(campos.values()))[0]["id"])

    _anotar(con, novo, tipo="AUTUACAO", quando=agora, quem=usuario,
            o_que=f"Processo autuado — {NORMA.NOME_DA_ESPECIE[especie]}, "
                  f"{NORMA.NOME_DO_FUNDAMENTO[fundamento]}.")
    _semear_conferencia(con, novo, especie=especie, rural=bool(rural))
    return novo


def _anotar(con: sqlite3.Connection, processo_id: int, *, tipo: str,
            o_que: str, quando: str, quem: str | None = None,
            artigo: str | None = None,
            confrontante_id: int | None = None) -> None:
    banco(con).escrever(
        """INSERT INTO rt_andamento (processo_id, quando, tipo, o_que, artigo,
               confrontante_id, quem)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (processo_id, quando, tipo, o_que, artigo, confrontante_id, quem))


def _semear_conferencia(con: sqlite3.Connection, processo_id: int, *,
                        especie: str, rural: bool) -> None:
    """Põe o checklist do art. 592 na conferência, item a item.

    O CHECKLIST SAI DA NORMA, E NÃO DE UMA LISTA AQUI. Uma segunda lista
    envelheceria na tarde em que fosse escrita — é a lição do menu, que este
    projeto já pagou.
    """
    itens = NORMA.checklist(
        georreferenciada=(especie == NORMA.GEORREFERENCIADA), rural=rural)
    bd = banco(con)
    for item in itens:
        bd.escrever(
            """INSERT INTO rt_conferencia (processo_id, item, artigo)
               VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
            (processo_id, item["o_que"], item["artigo"]))


def conferencia(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM rt_conferencia WHERE processo_id = %s ORDER BY id",
        (processo_id,))


def marcar_item(con: sqlite3.Connection, processo_id: int, item: str, *,
                situacao: str, agora: str, usuario: str | None = None,
                nota: str = "") -> None:
    """Marca um item do checklist. ESCREVE.

    DISPENSAR EXIGE MOTIVO ESCRITO. Dispensar é decisão do oficial; ignorar não
    é — e a norma tem casos expressos de dispensa (arts. 610 § 1º, 619, 596
    parágrafo único, 593), cada um com o seu artigo.
    """
    situacao = _texto(situacao).upper()
    if situacao not in ("PENDENTE", "ATENDIDO", "DISPENSADO"):
        raise RetificacaoError(
            "A situação do item é PENDENTE, ATENDIDO ou DISPENSADO.")
    if situacao == "DISPENSADO" and len(_texto(nota)) < MINIMO_DO_MOTIVO:
        raise RetificacaoError(
            "Para dispensar um item é preciso escrever o motivo — a norma tem "
            "casos expressos de dispensa, e é bom dizer qual deles é. "
            f"Escreva ao menos {MINIMO_DO_MOTIVO} letras.")
    bd = banco(con)
    bd.escrever(
        """UPDATE rt_conferencia SET situacao = %s, nota = %s, marcado_em = %s,
               marcado_por = %s
            WHERE processo_id = %s AND item = %s""",
        (situacao, _texto(nota) or None, agora, usuario, processo_id, item))
    if bd.linhas_afetadas == 0:
        raise RetificacaoError(
            "Esse item não está na conferência deste processo.")


def o_que_falta(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    """Os itens do checklist ainda pendentes. Só lê."""
    return [x for x in conferencia(con, processo_id)
            if (x.get("situacao") or "PENDENTE") == "PENDENTE"]


# --------------------------------------------------------- os confrontantes


def anotar_confrontante(con: sqlite3.Connection, processo_id: int, *,
                        nome: str, agora: str, papel: str = CONFRONTANTE,
                        documento: str = "", endereco: str = "",
                        matricula_contigua: str = "",
                        serventia_contigua: str = "",
                        divisa_afetada: bool = True,
                        assinou_planta: bool = False,
                        carta_anuencia: bool = False,
                        usuario: str | None = None) -> int:
    """Acrescenta um confrontante. ESCREVE."""
    _exigir(con, processo_id)
    if papel not in PAPEIS:
        raise RetificacaoError(
            f"«{papel}» não é um papel. Os que existem: " + ", ".join(PAPEIS)
            + ".")
    if not _texto(nome):
        raise RetificacaoError("O confrontante precisa de nome.")

    # A NORMALIZACAO E A DA CASA, IMPORTADA — e nao uma copia.
    #
    # `pt_schema.normalizar_nome` e a mesma que preenche `nt_pessoas.nome_norm`
    # e a que `fraude` poe dentro do SQLite como `nome_da_casa`. Copia-la para
    # ca faria duas formas de normalizar nome, e a busca deste modulo acharia
    # coisa diferente da do Protesto para o mesmo nome — que e exatamente o
    # defeito que o modulo de fraudes ja teve, duas vezes.
    #
    # (E eu chamei `fraude.nome_da_casa` na primeira versao, achando que era o
    #  nome da funcao. Nao e: aquilo e o nome que ela recebe DENTRO do SQLite.
    #  «Nao achar a funcao que procurei nao prova que ela nao existe» — quinta
    #  vez neste projeto.)
    from pt_schema import normalizar_nome
    novo = int(banco(con).escrever(
        """INSERT INTO rt_confrontantes (processo_id, papel, nome, nome_norm,
               documento, endereco, matricula_contigua, serventia_contigua,
               divisa_afetada, assinou_planta, carta_anuencia, criado_em,
               criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (processo_id, papel, _texto(nome), normalizar_nome(_texto(nome)),
         _texto(documento) or None, _texto(endereco) or None,
         _texto(matricula_contigua) or None, _texto(serventia_contigua) or None,
         1 if divisa_afetada else 0, 1 if assinou_planta else 0,
         1 if carta_anuencia else 0, agora, usuario))[0]["id"])
    _anotar(con, processo_id, tipo="CONFRONTANTE", quando=agora, quem=usuario,
            confrontante_id=novo,
            o_que=f"{NOME_DO_PAPEL[papel]} anotado: {_texto(nome)}.")
    return novo


def aviso_de_confrontante_repetido(con, processo_id: int, *, nome: str,
                                   documento: str = "",
                                   exceto: int | None = None) -> str | None:
    """O mesmo nome ou o mesmo CPF já está neste processo. Só lê.

    Avisa e não impede: o vizinho pode ter homônimo, e quem confirma é quem
    está com o documento na mão. Sem o aviso, o duplicado só se via no banco.
    """
    from pt_schema import normalizar_nome
    from ri_schema import so_digitos
    nome_norm = normalizar_nome(_texto(nome))
    doc = so_digitos(documento)
    for outro in confrontantes(con, processo_id):
        if exceto is not None and int(outro["id"]) == int(exceto):
            continue
        mesmo_doc = bool(doc) and so_digitos(outro.get("documento")) == doc
        mesmo_nome = bool(nome_norm) and (outro.get("nome_norm") or "") == nome_norm
        if mesmo_doc or mesmo_nome:
            por = "o mesmo CPF/CNPJ" if mesmo_doc else "o mesmo nome"
            return (f"Já há confrontante neste processo com {por}: "
                    f"{outro['nome']}. Confira antes de notificar os dois.")
    return None


def _trava_de_exclusao(linha: dict) -> str | None:
    if str(linha.get("selo") or "").strip():
        return "já tem selo"
    if linha.get("impresso_em"):
        return "o papel já foi impresso"
    if linha.get("recebido_em"):
        return "já há ciência do recebimento"
    if linha.get("notificado_em"):
        return "a notificação já foi expedida"
    return None


def excluir_confrontante(con, processo_id: int, confrontante_id: int, *,
                         agora: str, usuario: str | None = None) -> str:
    """Tira o confrontante que ainda não foi notificado. ESCREVE.

    Notificação expedida, ciência, impressão final ou selo travam a exclusão:
    apagar isso apagaria o prazo de alguém. O andamento antigo solta o id
    (a chave não deixa apagar a linha enquanto ele aponta para cá) e a
    exclusão fica escrita no andamento, sem o id que já não existe.
    """
    bd = banco(con)
    linha = bd.um(
        """SELECT * FROM rt_confrontantes
            WHERE id = %s AND processo_id = %s""",
        (int(confrontante_id), int(processo_id)))
    if not linha:
        raise RetificacaoError("Não achei esse confrontante neste processo.")
    trava = _trava_de_exclusao(linha)
    if not trava and banco(con).um(
            "SELECT 1 FROM rt_impugnacoes WHERE confrontante_id = %s",
            (int(confrontante_id),)):
        trava = "a impugnação dele tem andamento"
    if trava:
        raise RetificacaoError(
            f"{linha['nome']} não se exclui: {trava}. O prazo e o papel "
            "ficam no processo.")
    nome = linha["nome"]
    bd.escrever(
        "UPDATE rt_andamento SET confrontante_id = NULL WHERE confrontante_id = %s",
        (int(confrontante_id),))
    bd.escrever(
        "DELETE FROM rt_confrontantes WHERE id = %s AND processo_id = %s",
        (int(confrontante_id), int(processo_id)))
    _anotar(con, int(processo_id), tipo="CONFRONTANTE_EXCLUIDO", quando=agora,
            quem=usuario,
            o_que=(f"Confrontante excluído: {nome}. Não havia notificação, "
                   "ciência, impressão nem selo."))
    return nome


def atualizar_atendimento(con, processo_id: int, *, prenotacao_id,
                          prenotacao: str | None, protocolo_id,
                          protocolo_numero: str | None, agora: str,
                          usuario: str | None = None) -> bool:
    """Grava prenotação e protocolo de recepção. ESCREVE. Devolve se mudou."""
    p = processo(con, processo_id)
    if not p:
        raise RetificacaoError("Não achei esse processo de retificação.")
    antes_pre = p.get("prenotacao_id")
    antes_cx = p.get("protocolo_id")
    if (antes_pre or None) == prenotacao_id and (antes_cx or None) == protocolo_id:
        return False
    banco(con).escrever(
        """UPDATE rt_processos
              SET prenotacao_id = %s, prenotacao = %s, protocolo_id = %s,
                  atualizado_em = %s
            WHERE id = %s""",
        (prenotacao_id, prenotacao, protocolo_id, agora, int(processo_id)))
    partes = []
    if prenotacao:
        partes.append(f"prenotação {prenotacao}")
    else:
        partes.append("sem prenotação")
    if protocolo_numero:
        partes.append(f"protocolo {protocolo_numero}")
    else:
        partes.append("sem protocolo de recepção")
    _anotar(con, int(processo_id), tipo="ATENDIMENTO", quando=agora,
            quem=usuario, o_que="Atendimento do processo: " + "; ".join(partes) + ".")
    return True


def quem_precisa_ser_notificado(con: sqlite3.Connection,
                                processo_id: int) -> list[dict]:
    """Quem falta notificar, pela norma. Só calcula.

    TRÊS DISPENSAS, E CADA UMA TEM ARTIGO:

    - quem **assinou a planta** já anuiu (art. 592, II — a planta vai assinada
      pelos confrontantes);
    - quem trouxe **carta de anuência apartada** também (art. 598, que só manda
      notificar «se a planta não contiver a assinatura de algum confrontante, e
      não for apresentada carta de anuência apartada»);
    - quem **não tem divisa afetada** está dispensado até de intimação (art.
      596, parágrafo único).

    Sem isso o balcão notifica vizinho que a norma não manda notificar —
    trabalho, custo e espera à toa, num rito que já leva meses.
    """
    faltam = []
    for c in confrontantes(con, processo_id):
        if c.get("notificado_em"):
            continue
        if not c.get("divisa_afetada"):
            continue
        if c.get("assinou_planta") or c.get("carta_anuencia"):
            continue
        faltam.append(c)
    return faltam


def dispensados_de_notificacao(con: sqlite3.Connection,
                               processo_id: int) -> list[dict]:
    """Quem NÃO precisa ser notificado, e por qual artigo. Só calcula.

    A LISTA APARECE NA TELA DE PROPÓSITO. Dispensa que não se vê vira dúvida no
    balcão, e a dúvida vira notificação a mais — que é o que a lista existe para
    evitar.
    """
    fora = []
    for c in confrontantes(con, processo_id):
        if c.get("notificado_em"):
            continue
        if not c.get("divisa_afetada"):
            fora.append({**c, "porque": "A divisa dele não é afetada",
                         "artigo": "art. 596, parágrafo único"})
        elif c.get("assinou_planta"):
            fora.append({**c, "porque": "Assinou a planta e o memorial",
                         "artigo": "art. 592, II"})
        elif c.get("carta_anuencia"):
            fora.append({**c, "porque": "Trouxe carta de anuência apartada",
                         "artigo": "art. 598"})
    return fora


def notificar(con: sqlite3.Connection, confrontante_id: int, *, forma: str,
              quando: str, agora: str, prazo_ate: str,
              recebido_em: str = "", usuario: str | None = None,
              serventia: dict | None = None,
              hoje_extenso: str = "") -> None:
    """Registra a notificação de um confrontante. ESCREVE.

    O PRAZO VEM PRONTO, DE FORA. Contar dia útil é do núcleo, que conhece os
    feriados desta comarca; contar aqui daria uma segunda contagem, e num prazo
    divergir por um dia é recomeçar o prazo.

    A ORDEM DAS FORMAS É DO ART. 598 — pessoal, RTD, correio com AR e, «caso
    frustradas as tentativas anteriores», edital. O módulo aceita a forma que o
    balcão informar e **registra qual foi**: quem confere depois precisa saber
    se o edital veio antes da hora.
    """
    formas = {x["forma"] for x in NORMA.COMO_NOTIFICAR}
    if forma not in formas:
        raise RetificacaoError(
            f"«{forma}» não é uma forma de notificação do art. 598. As que "
            "existem, nesta ordem: " + ", ".join(x["forma"]
                                                 for x in NORMA.COMO_NOTIFICAR)
            + ".")
    if str(quando or "")[:10] > str(agora or "")[:10]:
        raise RetificacaoError(
            "A data da notificação não pode ser futura. O prazo conta do "
            "recebimento, e uma data que ainda não chegou recomeçaria a conta.")
    bd = banco(con)
    # FOR UPDATE: o «já foi notificado» sai desta leitura, e duas notificações
    # ao mesmo tempo passariam as duas — a segunda recomeçando o prazo.
    bd._escrita()
    linha = bd.um("SELECT * FROM rt_confrontantes WHERE id = %s FOR UPDATE",
                  (confrontante_id,))
    if not linha:
        raise RetificacaoError("Não achei esse confrontante.")
    if linha["notificado_em"]:
        raise RetificacaoError(
            f"{linha['nome']} já foi notificado em {linha['notificado_em']}. "
            "Uma segunda notificação recomeçaria o prazo dele.")

    #  O PAPEL E MONTADO ANTES DE O REGISTRO EXISTIR — 21/09/2026.
    #
    #  Se faltar endereco, ou nome, nada e gravado: notificacao registrada sem
    #  papel que a sustente consome o prazo de alguem que nao foi avisado. E a
    #  regra que a usucapiao ja seguia, e `rt_notificacao.conferir` diz o que
    #  falta com o artigo ao lado.
    #
    #  **SEM `serventia` NAO SE MONTA, e isso nao e recusa**: quem chama de um
    #  script, ou de uma carga, nao tem quem assina — e ali o registro do fato
    #  continua valendo. O papel e' do balcao, que sempre tem.
    teor = None
    if serventia is not None:
        import rt_notificacao as NOTIF
        processo = dict(bd.um(
            "SELECT * FROM rt_processos WHERE id = %s",
            (int(linha["processo_id"]),)) or {})
        if processo.get("matricula_id"):
            m = bd.um("SELECT numero FROM ri_matriculas WHERE id = %s",
                      (processo["matricula_id"],))
            if m:
                processo["matricula_numero"] = m["numero"]
        try:
            # COM `bd`, O PAPEL SAI COMO A CASA O AJUSTOU (LF06G) — e
            # congela assim no registro do confrontante.
            teor = NOTIF.montar(processo=processo, confrontante=dict(linha),
                                serventia=serventia,
                                hoje_extenso=hoje_extenso, con=bd)
        except NOTIF.NotificacaoError as erro:
            raise RetificacaoError(str(erro)) from erro

    bd.escrever(
        """UPDATE rt_confrontantes SET notificado_em = %s, forma = %s,
               recebido_em = %s, prazo_ate = %s,
               teor_expedido = COALESCE(%s, teor_expedido)
            WHERE id = %s""",
        (quando, forma, _texto(recebido_em) or None, prazo_ate, teor,
         confrontante_id))
    _anotar(con, int(linha["processo_id"]), tipo="NOTIFICACAO", quando=agora,
            quem=usuario, confrontante_id=confrontante_id, artigo="art. 598",
            o_que=f"{linha['nome']} notificado por {forma}; prazo até "
                  f"{prazo_ate}.")


def responder(con: sqlite3.Connection, confrontante_id: int, *, resposta: str,
              agora: str, impugnacao: str = "",
              usuario: str | None = None) -> None:
    """Registra a resposta de um confrontante. ESCREVE.

    IMPUGNAÇÃO SEM FUNDAMENTO NÃO É IMPUGNAÇÃO — o art. 593 diz «para impugnação
    fundamentada quanto às divisas e/ou área objeto de retificação, **não
    bastando mera alegação de prejuízo**». Por isso o texto é obrigatório, e a
    recusa explica isso.

    E O MÓDULO NÃO JULGA SE ELA PROCEDE. Guardar a impugnação é registro; dizer
    se ela vale é matéria de direito, e a decisão é do delegatário.
    """
    resposta = _texto(resposta).upper()
    if resposta not in RESPOSTAS:
        raise RetificacaoError(
            f"«{resposta}» não é uma resposta. As que existem: "
            + ", ".join(f"{k} ({v})" for k, v in NOME_DA_RESPOSTA.items())
            + ".")
    bd = banco(con)
    linha = bd.um("SELECT * FROM rt_confrontantes WHERE id = %s",
                  (confrontante_id,))
    if not linha:
        raise RetificacaoError("Não achei esse confrontante.")
    if resposta == IMPUGNOU and len(_texto(impugnacao)) < MINIMO_DO_MOTIVO:
        raise RetificacaoError(
            "A impugnação tem de ser fundamentada — «não bastando mera "
            "alegação de prejuízo» (art. 593). Escreva o que ele alegou.")

    bd.escrever(
        """UPDATE rt_confrontantes SET resposta = %s, respondido_em = %s,
               impugnacao = %s WHERE id = %s""",
        (resposta, agora, _texto(impugnacao) or None, confrontante_id))
    _anotar(con, int(linha["processo_id"]), tipo="RESPOSTA", quando=agora,
            quem=usuario, confrontante_id=confrontante_id,
            artigo="art. 599, § 1º" if resposta == SILENCIO else "art. 599",
            o_que=f"{linha['nome']}: {NOME_DA_RESPOSTA[resposta]}.")


def situacao_dos_prazos(con: sqlite3.Connection, processo_id: int, *,
                        hoje: str) -> dict:
    """Quem já respondeu, quem está no prazo e de quem o prazo passou.

    E A REGRA QUE PARECE CONTRADIÇÃO E NÃO É — arts. 599, §§ 1º e 3º:

    - **o silêncio vale anuência** quando o prazo passa (§ 1º);
    - **mas a impugnação atrasada ainda entra**, até a averbação sair (§ 3º).

    Um sistema que tratasse «prazo vencido» como «acabou» erraria, e erraria
    contra quem não foi ouvido. Por isso `venceu` NÃO quer dizer «fechado`:
    quem fecha a porta é a averbação, e é `porta_aberta` que diz isso.
    """
    todos = confrontantes(con, processo_id)
    p = _exigir(con, processo_id)
    porta_aberta = not p["averbado_em"]

    responderam, no_prazo, venceu, sem_notificar = [], [], [], []
    for c in todos:
        if c.get("resposta"):
            responderam.append(c)
        elif not c.get("notificado_em"):
            if c in quem_precisa_ser_notificado(con, processo_id):
                sem_notificar.append(c)
        elif c.get("prazo_ate") and str(c["prazo_ate"]) < str(hoje):
            venceu.append(c)
        else:
            no_prazo.append(c)

    return {
        "responderam": responderam,
        "no_prazo": no_prazo,
        "venceu": venceu,               # anuência presumida (art. 599, § 1º)
        "sem_notificar": sem_notificar,
        "porta_aberta": porta_aberta,   # art. 599, § 3º
        "impugnaram": [c for c in todos if c.get("resposta") == IMPUGNOU],
    }


# ------------------------------------------------ as impugnações (art. 600)
#
# O QUE ESTA PARTE FAZ: guarda o caminho que o OFICIAL deu a cada impugnação
# e conta, pelo núcleo, os prazos que nascem disso. O que ela NÃO faz é dizer
# se a impugnação procede: «considerada a impugnação infundada» (§ 4º) é juízo
# do oficial, e o texto dele é obrigatório. As hipóteses do § 6º aparecem como
# apoio, para ele marcar a que fundamenta a decisão que ELE escreveu.

REQUERENTE = "REQUERENTE"
PROFISSIONAL = "PROFISSIONAL"

#: Quem pode pedir a transação amigável (art. 600, § 2º).
QUEM_PEDE_TRANSACAO = {
    REQUERENTE: "o requerente",
    PROFISSIONAL: "o profissional que assinou a planta e o memorial",
}

SEM_RECURSO = "SEM_RECURSO"
ACORDO = "ACORDO"
AO_JUIZ = "AO_JUIZ"
JUIZ_DECIDIU = "JUIZ_DECIDIU"

NOME_DO_DESFECHO = {
    SEM_RECURSO: "Rejeitada de plano, sem recurso no prazo — o procedimento "
                 "prossegue (art. 600, § 4º)",
    ACORDO: "Transação formalizada (art. 600, § 2º)",
    AO_JUIZ: "Remetida ao Juiz corregedor permanente (art. 601)",
    JUIZ_DECIDIU: "O Juiz corregedor permanente decidiu",
}

#: Os desfechos depois dos quais o procedimento segue para a decisão do art.
#: 604. AO_JUIZ não está aqui: com os autos no Juiz, não se decide.
DESFECHOS_QUE_LIBERAM = (SEM_RECURSO, ACORDO, JUIZ_DECIDIU)

_COLUNAS_DA_IMPUGNACAO = (
    "rejeitada_em", "rejeitada_por", "rejeicao_hipotese", "rejeicao_fundamento",
    "rejeicao_intimada_em", "recurso_prazo_ate", "recurso_em", "recurso_razoes",
    "contrarrazoes_intimadas_em", "contrarrazoes_prazo_ate", "contrarrazoes_em",
    "contrarrazoes", "transacao_pedida_em", "transacao_pedida_por",
    "transacao_prazo_ate", "transacao_prorrogada_em", "acordo", "remetida_em",
    "remetida_por", "remessa_paragrafo", "remessa_informacoes",
    "juiz_decidiu_em", "juiz_decisao", "desfecho", "desfecho_em")


def prazo_ate(con, inicio: str, chave: str) -> str:
    """A data-limite do prazo `chave` da norma, contado de `inicio`. Só lê.

    **QUEM CONTA É O NÚCLEO** — `ri_schema.soma_dias_uteis`, com os feriados
    locais de Configurações (`rotina_da_casa.feriados_da_casa`), a mesma conta
    da prenotação. Só prazo em dias úteis: o corrido (o do SIGEF) este módulo
    não conta.
    """
    from ri_schema import soma_dias_uteis
    from rotina_da_casa import feriados_da_casa
    regra = NORMA.prazo(chave)
    if not regra["uteis"]:
        raise ValueError(f"O prazo {chave} é em dias corridos e não se conta "
                         "aqui.")
    dia = _data(inicio, "o início do prazo")
    return soma_dias_uteis(dia, int(regra["dias"]),
                           feriados_da_casa(con)).isoformat()


def _data(valor: Any, campo: str):
    from datetime import date
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        raise RetificacaoError(
            f"Informe {campo} como data (AAAA-MM-DD).") from None


def _data_passada(valor: Any, campo: str, agora: str) -> str:
    """A data como o balcão a informou, conferida: válida e não futura."""
    dia = _data(valor, campo).isoformat()
    if dia > str(agora or "")[:10]:
        raise RetificacaoError(
            f"{campo[0].upper()}{campo[1:]} não pode ser futura: o prazo "
            "contaria de um dia que ainda não chegou.")
    return dia


def etapa_da_impugnacao(i: dict, *, hoje: str) -> str:
    """Em que ponto do art. 600 a impugnação está. Só calcula.

    ABERTA, TRANSACAO, INTIMAR_REJEICAO, PRAZO_DE_RECURSO, RECURSO_VENCIDO,
    INTIMAR_CONTRARRAZOES, CONTRARRAZOES, ou o desfecho.
    """
    if i.get("desfecho"):
        return str(i["desfecho"])
    if i.get("rejeitada_em"):
        if i.get("recurso_em"):
            return ("CONTRARRAZOES" if i.get("contrarrazoes_intimadas_em")
                    else "INTIMAR_CONTRARRAZOES")
        if not i.get("rejeicao_intimada_em"):
            return "INTIMAR_REJEICAO"
        if str(i.get("recurso_prazo_ate") or "") >= str(hoje)[:10]:
            return "PRAZO_DE_RECURSO"
        return "RECURSO_VENCIDO"
    if i.get("transacao_pedida_em"):
        return "TRANSACAO"
    return "ABERTA"


def impugnacoes(con, processo_id: int, *, hoje: str) -> list[dict]:
    """Cada confrontante que impugnou, com o caminho que ela tomou. Só lê.

    A linha de `rt_impugnacoes` só nasce quando o oficial faz alguma coisa com
    a impugnação; até lá ela aparece aqui como ABERTA.
    """
    colunas = ", ".join(f"i.{c}" for c in _COLUNAS_DA_IMPUGNACAO)
    linhas = banco(con).ler(
        f"""SELECT c.id AS confrontante_id, c.nome, c.papel,
                   c.impugnacao AS alegacao, c.respondido_em,
                   i.id AS impugnacao_id, {colunas}
              FROM rt_confrontantes c
              LEFT JOIN rt_impugnacoes i ON i.confrontante_id = c.id
             WHERE c.processo_id = %s AND c.resposta = %s
          ORDER BY c.id""", (processo_id, IMPUGNOU))
    saida = []
    for linha in linhas:
        i = dict(linha)
        i["etapa"] = etapa_da_impugnacao(i, hoje=hoje)
        saida.append(i)
    return saida


def _impugnacao_para_gravar(con, processo_id: int, confrontante_id: int, *,
                            agora: str, usuario: str | None) -> dict:
    """A impugnação de um confrontante, PRESA até o fim da transação.

    Nasce aqui, na primeira coisa que o oficial faz com ela. Recusa quem não
    impugnou e o processo que já foi decidido — depois do art. 604, mexer na
    impugnação reescreveria o que sustentou a decisão.
    """
    p = _exigir_para_gravar(con, processo_id)
    if p["decidido_em"]:
        raise RetificacaoError(
            f"Este processo já foi decidido em {p['decidido_em']}; a "
            "impugnação fica como estava quando a decisão saiu.")
    bd = banco(con)
    c = bd.um("""SELECT * FROM rt_confrontantes
                  WHERE id = %s AND processo_id = %s FOR UPDATE""",
              (int(confrontante_id), int(processo_id)))
    if not c:
        raise RetificacaoError("Não achei esse confrontante neste processo.")
    if c.get("resposta") != IMPUGNOU:
        raise RetificacaoError(
            f"{c['nome']} não impugnou. Registre a impugnação na resposta dele "
            "antes (art. 599).")
    bd.escrever(
        """INSERT INTO rt_impugnacoes (processo_id, confrontante_id, criado_em,
               criado_por)
           VALUES (%s,%s,%s,%s) ON CONFLICT (confrontante_id) DO NOTHING""",
        (int(processo_id), int(confrontante_id), agora, usuario))
    i = dict(bd.um("""SELECT * FROM rt_impugnacoes
                       WHERE confrontante_id = %s FOR UPDATE""",
                   (int(confrontante_id),)))
    i["nome"] = c["nome"]
    i["processo"] = p
    return i


def _gravar_impugnacao(con, impugnacao_id: int, **campos) -> None:
    sets = ", ".join(f"{k} = %s" for k in campos)
    banco(con).escrever(f"UPDATE rt_impugnacoes SET {sets} WHERE id = %s",
                        (*campos.values(), int(impugnacao_id)))


def _sem_desfecho(i: dict) -> None:
    if i.get("desfecho"):
        raise RetificacaoError(
            f"A impugnação de {i['nome']} já tem desfecho: "
            f"{NOME_DO_DESFECHO.get(i['desfecho'], i['desfecho'])}.")


def _texto_obrigatorio(texto: str, frase: str) -> str:
    if len(_texto(texto)) < MINIMO_DO_MOTIVO:
        raise RetificacaoError(
            f"{frase} Escreva ao menos {MINIMO_DO_MOTIVO} letras.")
    return _texto(texto)


def _acertar_fase(con, processo_id: int, *, hoje: str, agora: str) -> str:
    """A fase do processo pelo estado das impugnações. ESCREVE se mudou.

    Autos no Juiz pesam mais que mediação, mediação mais que impugnação
    aberta; sem nenhuma aberta, o procedimento prossegue para a DECISAO —
    o que mais faltar para decidir, `o_que_falta_para_decidir` diz.
    """
    p = _exigir(con, processo_id)
    if p["decidido_em"]:
        return p["fase"]
    etapas = [i["etapa"] for i in impugnacoes(con, processo_id, hoje=hoje)]
    if not etapas:
        return p["fase"]
    if AO_JUIZ in etapas:
        fase = "AO_JUIZ"
    elif "TRANSACAO" in etapas:
        fase = "MEDIACAO"
    elif any(e not in DESFECHOS_QUE_LIBERAM for e in etapas):
        fase = "IMPUGNACAO"
    else:
        fase = "DECISAO"
    if fase != p["fase"]:
        banco(con).escrever(
            "UPDATE rt_processos SET fase = %s, atualizado_em = %s WHERE id = %s",
            (fase, agora, int(processo_id)))
    return fase


def rejeitar_impugnacao(con, processo_id: int, confrontante_id: int, *,
                        hipotese: str, fundamento: str, agora: str,
                        usuario: str | None, intimado_em: str = "") -> dict:
    """Grava a decisão DO OFICIAL que rejeita de plano a impugnação. ESCREVE.

    Art. 600, § 4º: «considerada a impugnação infundada, o oficial de registro
    deverá rejeitá-la, de plano, por decisão fundamentada». O sistema não
    considera nada: guarda o fundamento que o oficial escreveu, a hipótese do
    § 6º que ele marcou como apoio, quem decidiu e quando.

    Com `intimado_em`, registra também a intimação do impugnante, de onde os
    10 dias úteis do recurso contam.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if i.get("rejeitada_em"):
        raise RetificacaoError(
            f"A impugnação de {i['nome']} já foi rejeitada em "
            f"{i['rejeitada_em']}, por {i['rejeitada_por']}.")
    if not _texto(usuario):
        raise RetificacaoError(
            "A rejeição de plano é decisão do oficial, e precisa de quem a "
            "tomou.")
    inciso = _texto(hipotese).upper()
    if inciso not in NORMA.HIPOTESE_POR_INCISO:
        raise RetificacaoError(
            "Marque a hipótese do art. 600, § 6º que fundamenta a sua decisão: "
            + "; ".join(f"{h['inciso']} — {h['o_que']}"
                        for h in NORMA.HIPOTESES_DE_IMPUGNACAO_INFUNDADA)
            + ".")
    texto = _texto_obrigatorio(
        fundamento,
        "O art. 600, § 4º pede decisão FUNDAMENTADA. A hipótese marcada é "
        "apoio; o fundamento é o seu texto.")
    _gravar_impugnacao(con, i["id"], rejeitada_em=agora,
                       rejeitada_por=_texto(usuario),
                       rejeicao_hipotese=inciso, rejeicao_fundamento=texto)
    hip = NORMA.HIPOTESE_POR_INCISO[inciso]
    _anotar(con, processo_id, tipo="IMPUGNACAO_REJEITADA", quando=agora,
            quem=usuario, confrontante_id=confrontante_id,
            artigo="art. 600, § 4º",
            o_que=(f"Impugnação de {i['nome']} rejeitada de plano pelo "
                   f"oficial ({_texto(usuario)}), com apoio no {hip['artigo']} "
                   f"— {hip['o_que']}. Fundamento: {texto}"))
    saida = {"rejeitada_em": agora}
    if _texto(intimado_em):
        saida.update(intimar_da_rejeicao(
            con, processo_id, confrontante_id, intimado_em=intimado_em,
            agora=agora, usuario=usuario))
    else:
        _acertar_fase(con, processo_id, hoje=agora[:10], agora=agora)
    return saida


def intimar_da_rejeicao(con, processo_id: int, confrontante_id: int, *,
                        intimado_em: str, agora: str,
                        usuario: str | None = None) -> dict:
    """Registra a intimação do impugnante da rejeição. ESCREVE.

    É dela que contam os 10 dias úteis do recurso (art. 600, § 4º), e quem os
    conta é o núcleo (`prazo_ate`).
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if not i.get("rejeitada_em"):
        raise RetificacaoError(
            "Só se intima da rejeição a impugnação que o oficial rejeitou de "
            "plano (art. 600, § 4º).")
    if i.get("rejeicao_intimada_em"):
        raise RetificacaoError(
            f"{i['nome']} já foi intimado da rejeição em "
            f"{i['rejeicao_intimada_em']}. Uma segunda intimação recomeçaria "
            "o prazo do recurso.")
    dia = _data_passada(intimado_em, "a data da intimação", agora)
    if dia < str(i["rejeitada_em"])[:10]:
        raise RetificacaoError(
            "A intimação não pode ser anterior à rejeição, que foi em "
            f"{str(i['rejeitada_em'])[:10]}.")
    limite = prazo_ate(con, dia, "RECORRER")
    _gravar_impugnacao(con, i["id"], rejeicao_intimada_em=dia,
                       recurso_prazo_ate=limite)
    _anotar(con, processo_id, tipo="IMPUGNACAO_INTIMADA", quando=agora,
            quem=usuario, confrontante_id=confrontante_id,
            artigo="art. 600, § 4º",
            o_que=(f"{i['nome']} intimado da rejeição em {dia}; prazo de "
                   f"recurso até {limite} (10 dias úteis)."))
    _acertar_fase(con, processo_id, hoje=agora[:10], agora=agora)
    return {"recurso_prazo_ate": limite}


def registrar_recurso(con, processo_id: int, confrontante_id: int, *,
                      em: str, razoes: str, agora: str,
                      usuario: str | None = None) -> dict:
    """Registra o recurso do impugnante contra a rejeição. ESCREVE.

    O recurso cabe nos 10 dias úteis da intimação (§ 4º); depois disso, a
    norma diz que o procedimento prossegue, e a recusa diz isso.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if not i.get("rejeicao_intimada_em"):
        raise RetificacaoError(
            "O prazo do recurso conta da intimação do impugnante (art. 600, "
            "§ 4º). Registre a intimação da rejeição antes.")
    if i.get("recurso_em"):
        raise RetificacaoError(
            f"O recurso de {i['nome']} já foi registrado em {i['recurso_em']}.")
    dia = _data_passada(em, "a data do recurso", agora)
    if dia > str(i["recurso_prazo_ate"]):
        raise RetificacaoError(
            f"O prazo de recurso de {i['nome']} venceu em "
            f"{i['recurso_prazo_ate']} (10 dias úteis da intimação, art. 600, "
            "§ 4º). Sem recurso no prazo, o procedimento prossegue.")
    texto = _texto_obrigatorio(
        razoes, "O § 5º fala nas razões do impugnante: escreva o que ele "
                "alegou no recurso.")
    _gravar_impugnacao(con, i["id"], recurso_em=dia, recurso_razoes=texto)
    _anotar(con, processo_id, tipo="IMPUGNACAO_RECURSO", quando=agora,
            quem=usuario, confrontante_id=confrontante_id,
            artigo="art. 600, § 5º",
            o_que=f"{i['nome']} recorreu da rejeição em {dia}. Razões: {texto}")
    _acertar_fase(con, processo_id, hoje=agora[:10], agora=agora)
    return {"recurso_em": dia}


def intimar_para_contrarrazoes(con, processo_id: int, confrontante_id: int, *,
                               intimado_em: str, agora: str,
                               usuario: str | None = None) -> dict:
    """Registra a intimação do interessado para as contrarrazões. ESCREVE.

    Art. 600, § 5º: «no prazo de 10 (dez) dias», contados em dias úteis por
    decisão do titular (27/11/2026) — `rt_tjma`, prazo CONTRARRAZOAR.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if not i.get("recurso_em"):
        raise RetificacaoError(
            "Só há contrarrazões depois do recurso do impugnante (art. 600, "
            "§ 5º).")
    if i.get("contrarrazoes_intimadas_em"):
        raise RetificacaoError(
            "O interessado já foi intimado para as contrarrazões em "
            f"{i['contrarrazoes_intimadas_em']}.")
    dia = _data_passada(intimado_em, "a data da intimação", agora)
    if dia < str(i["recurso_em"])[:10]:
        raise RetificacaoError(
            "A intimação para contrarrazões não pode ser anterior ao recurso, "
            f"que foi em {i['recurso_em']}.")
    limite = prazo_ate(con, dia, "CONTRARRAZOAR")
    _gravar_impugnacao(con, i["id"], contrarrazoes_intimadas_em=dia,
                       contrarrazoes_prazo_ate=limite)
    _anotar(con, processo_id, tipo="IMPUGNACAO_CONTRARRAZOES", quando=agora,
            quem=usuario, confrontante_id=confrontante_id,
            artigo="art. 600, § 5º",
            o_que=(f"Interessado intimado em {dia} para contrarrazões ao "
                   f"recurso de {i['nome']}, até {limite} (10 dias úteis)."))
    return {"contrarrazoes_prazo_ate": limite}


def registrar_contrarrazoes(con, processo_id: int, confrontante_id: int, *,
                            em: str, texto: str, agora: str,
                            usuario: str | None = None) -> dict:
    """Guarda as contrarrazões do interessado, se ele as apresentou. ESCREVE.

    «Querendo» (§ 5º): sem contrarrazões, os autos vão ao Juiz depois do
    prazo, e `remeter_ao_juiz` confere isso.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if not i.get("contrarrazoes_intimadas_em"):
        raise RetificacaoError(
            "Registre antes a intimação do interessado para as contrarrazões "
            "(art. 600, § 5º).")
    if i.get("contrarrazoes_em"):
        raise RetificacaoError(
            f"As contrarrazões já foram juntadas em {i['contrarrazoes_em']}.")
    dia = _data_passada(em, "a data das contrarrazões", agora)
    corpo = _texto_obrigatorio(texto, "Escreva o que o interessado alegou.")
    _gravar_impugnacao(con, i["id"], contrarrazoes_em=dia, contrarrazoes=corpo)
    _anotar(con, processo_id, tipo="IMPUGNACAO_CONTRARRAZOES", quando=agora,
            quem=usuario, confrontante_id=confrontante_id,
            artigo="art. 600, § 5º",
            o_que=(f"Contrarrazões ao recurso de {i['nome']} apresentadas em "
                   f"{dia}."))
    return {"contrarrazoes_em": dia}


def prosseguir_sem_recurso(con, processo_id: int, confrontante_id: int, *,
                           hoje: str, agora: str,
                           usuario: str | None = None) -> dict:
    """O prazo de recurso venceu sem recurso: o procedimento prossegue. ESCREVE.

    Art. 600, § 4º, parte final. Só depois do último dia do prazo — antes
    disso, o impugnante ainda pode recorrer.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if not i.get("rejeicao_intimada_em"):
        raise RetificacaoError(
            "O prazo de recurso conta da intimação do impugnante, e ela ainda "
            "não foi registrada (art. 600, § 4º).")
    if i.get("recurso_em"):
        raise RetificacaoError(
            f"{i['nome']} recorreu em {i['recurso_em']}: os autos vão ao Juiz "
            "depois das contrarrazões (art. 600, § 5º).")
    if str(hoje)[:10] <= str(i["recurso_prazo_ate"]):
        raise RetificacaoError(
            f"O prazo de recurso de {i['nome']} corre até "
            f"{i['recurso_prazo_ate']} (10 dias úteis, art. 600, § 4º). Até "
            "lá, ele ainda pode recorrer.")
    _gravar_impugnacao(con, i["id"], desfecho=SEM_RECURSO, desfecho_em=agora)
    _anotar(con, processo_id, tipo="IMPUGNACAO_SEM_RECURSO", quando=agora,
            quem=usuario, confrontante_id=confrontante_id,
            artigo="art. 600, § 4º",
            o_que=(f"O prazo de recurso de {i['nome']} venceu em "
                   f"{i['recurso_prazo_ate']} sem recurso: o procedimento "
                   "prossegue."))
    return {"desfecho": SEM_RECURSO,
            "fase": _acertar_fase(con, processo_id, hoje=hoje, agora=agora)}


def pedir_transacao(con, processo_id: int, confrontante_id: int, *,
                    quem_pediu: str, em: str, agora: str,
                    usuario: str | None = None) -> dict:
    """Abre o relógio da conciliação. ESCREVE.

    Art. 600, § 2º: «manifestando-se o requerente ou o profissional pela busca
    de transação amigável, será concedido o prazo de 15 (quinze) dias úteis»
    para formalizá-la ou agendar a sessão.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    quem = _texto(quem_pediu).upper()
    if quem not in QUEM_PEDE_TRANSACAO:
        raise RetificacaoError(
            "A transação do § 2º é pedida pelo requerente ou pelo profissional "
            "que assinou a planta: " + ", ".join(QUEM_PEDE_TRANSACAO) + ".")
    if i.get("rejeitada_em"):
        raise RetificacaoError(
            f"A impugnação de {i['nome']} foi rejeitada de plano: o caminho "
            "agora é o do recurso (art. 600, §§ 4º e 5º).")
    if i.get("transacao_pedida_em"):
        raise RetificacaoError(
            f"A transação já foi pedida em {i['transacao_pedida_em']}; o prazo "
            f"corre até {i['transacao_prazo_ate']}.")
    dia = _data_passada(em, "a data do pedido", agora)
    limite = prazo_ate(con, dia, "TRANSACAO")
    _gravar_impugnacao(con, i["id"], transacao_pedida_em=dia,
                       transacao_pedida_por=quem, transacao_prazo_ate=limite)
    _anotar(con, processo_id, tipo="TRANSACAO", quando=agora, quem=usuario,
            confrontante_id=confrontante_id, artigo="art. 600, § 2º",
            o_que=(f"Transação amigável pedida por {QUEM_PEDE_TRANSACAO[quem]} "
                   f"em {dia}, sobre a impugnação de {i['nome']}: 15 dias "
                   f"úteis, até {limite}, para formalizá-la ou agendar a "
                   "sessão."))
    _acertar_fase(con, processo_id, hoje=agora[:10], agora=agora)
    return {"transacao_prazo_ate": limite}


def prorrogar_transacao(con, processo_id: int, confrontante_id: int, *,
                        em: str, agora: str,
                        usuario: str | None = None) -> dict:
    """A prorrogação do § 2º — a pedido, UMA ÚNICA VEZ, por mais 15 dias úteis.

    ESCREVE. Os 15 contam do fim do prazo original, e não do pedido: quem
    pede cedo não perde os dias que ainda tinha.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if not i.get("transacao_pedida_em"):
        raise RetificacaoError(
            "Não há prazo de transação a prorrogar: ele nasce do pedido do "
            "requerente ou do profissional (art. 600, § 2º).")
    if i.get("transacao_prorrogada_em"):
        raise RetificacaoError(
            "O prazo da transação já foi prorrogado em "
            f"{i['transacao_prorrogada_em']}, e o § 2º só admite uma "
            "prorrogação.")
    dia = _data_passada(em, "a data do pedido de prorrogação", agora)
    antes = str(i["transacao_prazo_ate"])
    limite = prazo_ate(con, antes, "TRANSACAO_PRORROGADA")
    _gravar_impugnacao(con, i["id"], transacao_prorrogada_em=dia,
                       transacao_prazo_ate=limite)
    _anotar(con, processo_id, tipo="TRANSACAO", quando=agora, quem=usuario,
            confrontante_id=confrontante_id, artigo="art. 600, § 2º",
            o_que=(f"Prazo da transação prorrogado, a pedido de {dia}, por "
                   f"mais 15 dias úteis: de {antes} para {limite}. Não cabe "
                   "outra prorrogação."))
    return {"transacao_prazo_ate": limite}


def registrar_acordo(con, processo_id: int, confrontante_id: int, *,
                     texto: str, agora: str,
                     usuario: str | None = None) -> dict:
    """A transação formalizada: a impugnação se resolve. ESCREVE."""
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if not i.get("transacao_pedida_em"):
        raise RetificacaoError(
            "O acordo é o fim da transação do § 2º: registre antes quem a "
            "pediu e quando.")
    corpo = _texto_obrigatorio(texto, "Escreva o que as partes acordaram.")
    _gravar_impugnacao(con, i["id"], acordo=corpo, desfecho=ACORDO,
                       desfecho_em=agora)
    _anotar(con, processo_id, tipo="TRANSACAO", quando=agora, quem=usuario,
            confrontante_id=confrontante_id, artigo="art. 600, § 2º",
            o_que=f"Transação formalizada com {i['nome']}: {corpo}")
    return {"desfecho": ACORDO,
            "fase": _acertar_fase(con, processo_id, hoje=agora[:10],
                                  agora=agora)}


def _prorrogar_a_prenotacao(con, p: dict, *, hoje: str,
                            usuario: str | None) -> str:
    """Art. 600, § 3º (e TJMA 452, § 3º, II): a remessa prorroga a prenotação.

    ESCREVE na prenotação, pelo `ri_prenotacao_prazo` — que é quem guarda esse
    prazo —, e devolve a frase do que aconteceu. Não recusa a remessa: os
    autos vão ao Juiz de qualquer jeito, e o que não deu para fazer na
    prenotação vira aviso no andamento.

    A PRENOTAÇÃO VENCIDA NÃO É SUSPENSA: suspensa, nenhuma tela a conta como
    vencida, e suspender agora esconderia um vencimento que já aconteceu.
    """
    import ri_prenotacao_prazo as PRAZO
    if not p.get("prenotacao_id"):
        return ("Este processo não tem prenotação ligada: ligue-a em "
                "«Prenotação e protocolo» e suspenda o prazo dela na ficha da "
                "prenotação, para que os efeitos fiquem prorrogados.")
    bd = banco(con)
    pre = bd.um("SELECT * FROM ri_protocolos WHERE id = %s",
                (int(p["prenotacao_id"]),))
    if not pre:
        return (f"Não achei a prenotação ligada (id {p['prenotacao_id']}): "
                "confira o vínculo do processo.")
    numero = pre.get("numero")
    if PRAZO.suspensa(pre):
        motivo = PRAZO.MOTIVOS.get(pre.get("prazo_suspenso_motivo"),
                                   pre.get("prazo_suspenso_motivo"))
        return (f"O prazo da prenotação {numero} já está suspenso desde "
                f"{str(pre['prazo_suspenso_desde'])[:10]} ({motivo}): os "
                "efeitos seguem prorrogados.")
    if pre.get("situacao") != "ABERTO":
        return (f"A prenotação {numero} está {pre.get('situacao')}, e o prazo "
                "dela não foi suspenso. Confira na ficha da prenotação.")
    limite = str(pre.get("data_limite") or "")[:10]
    if limite and limite < str(hoje)[:10]:
        return (f"A prenotação {numero} venceu em {limite}, antes da remessa: "
                "o sistema não a suspendeu, para não esconder o vencimento. "
                "Confira na ficha da prenotação.")
    try:
        PRAZO.suspender(con, int(pre["id"]), motivo="RETIFICACAO",
                        quem=usuario, hoje=_data(hoje, "a data de hoje"))
    except PRAZO.PrazoError as erro:
        return f"O prazo da prenotação {numero} não foi suspenso: {erro}"
    return (f"O prazo da prenotação {numero} ficou suspenso a partir de "
            f"{str(hoje)[:10]}: os efeitos seguem prorrogados enquanto os "
            "autos estão com o Juiz. Ao voltarem, retome o prazo na ficha da "
            "prenotação.")


def remeter_ao_juiz(con, processo_id: int, confrontante_id: int, *,
                    informacoes: str, hoje: str, agora: str,
                    usuario: str | None = None) -> dict:
    """Registra a remessa dos autos ao Juiz corregedor permanente. ESCREVE.

    Dois caminhos, e o módulo não escolhe entre eles — eles saem do que o
    oficial já fez:

    - **impugnação rejeitada de plano, com recurso** (§ 5º): só depois das
      contrarrazões, ou do prazo delas;
    - **impugnação fundada, com a controvérsia mantida** ou impedimento
      constatado (§ 3º).

    Nos dois, a remessa é ato fundamentado com as informações dos
    assentamentos (art. 601) — texto obrigatório — e a prenotação fica com os
    efeitos prorrogados (§ 3º; TJMA 452, § 3º, II).
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    _sem_desfecho(i)
    if i.get("rejeitada_em"):
        if not i.get("recurso_em"):
            raise RetificacaoError(
                f"A impugnação de {i['nome']} foi rejeitada de plano e não há "
                "recurso: ela só vai ao Juiz com recurso (art. 600, § 5º); "
                "sem ele, o procedimento prossegue (§ 4º).")
        if not i.get("contrarrazoes_intimadas_em"):
            raise RetificacaoError(
                "Antes da remessa, intime o interessado para as contrarrazões "
                "(art. 600, § 5º).")
        if not i.get("contrarrazoes_em") \
                and str(hoje)[:10] <= str(i["contrarrazoes_prazo_ate"]):
            raise RetificacaoError(
                "O prazo das contrarrazões corre até "
                f"{i['contrarrazoes_prazo_ate']} (art. 600, § 5º). Remeta "
                "depois dele, ou quando elas vierem.")
        paragrafo = "art. 600, § 5º"
    else:
        paragrafo = "art. 600, § 3º"
    corpo = _texto_obrigatorio(
        informacoes,
        "A remessa é ato fundamentado, com as informações dos assentamentos "
        "sobre o imóvel e os confinantes (art. 601).")
    _gravar_impugnacao(con, i["id"], remetida_em=agora,
                       remetida_por=_texto(usuario) or None,
                       remessa_paragrafo=paragrafo, remessa_informacoes=corpo,
                       desfecho=AO_JUIZ, desfecho_em=agora)
    _anotar(con, processo_id, tipo="AO_JUIZ", quando=agora, quem=usuario,
            confrontante_id=confrontante_id, artigo=f"{paragrafo}; art. 601",
            o_que=(f"Autos remetidos ao Juiz corregedor permanente sobre a "
                   f"impugnação de {i['nome']}. Informações: {corpo}"))
    aviso = _prorrogar_a_prenotacao(con, i["processo"], hoje=hoje,
                                    usuario=usuario)
    _anotar(con, processo_id, tipo="PRENOTACAO", quando=agora, quem=usuario,
            artigo=NORMA.PRENOTACAO_PRORROGADA_NA_REMESSA["artigo"],
            o_que=aviso)
    return {"desfecho": AO_JUIZ, "prenotacao": aviso,
            "fase": _acertar_fase(con, processo_id, hoje=hoje, agora=agora)}


def registrar_retorno_do_juiz(con, processo_id: int, confrontante_id: int, *,
                              em: str, decisao: str, agora: str,
                              usuario: str | None = None) -> dict:
    """Guarda o que o Juiz corregedor permanente decidiu. ESCREVE.

    Só registra: a decisão é do Juiz, e o texto que se guarda é o dele. Com
    ela, a impugnação deixa de travar a decisão do art. 604.
    """
    i = _impugnacao_para_gravar(con, processo_id, confrontante_id,
                                agora=agora, usuario=usuario)
    if i.get("desfecho") != AO_JUIZ:
        raise RetificacaoError(
            f"A impugnação de {i['nome']} não foi remetida ao Juiz.")
    dia = _data_passada(em, "a data da decisão do Juiz", agora)
    corpo = _texto_obrigatorio(decisao, "Escreva o que o Juiz decidiu.")
    _gravar_impugnacao(con, i["id"], juiz_decidiu_em=dia, juiz_decisao=corpo,
                       desfecho=JUIZ_DECIDIU, desfecho_em=agora)
    _anotar(con, processo_id, tipo="JUIZ_DECIDIU", quando=agora, quem=usuario,
            confrontante_id=confrontante_id, artigo="art. 601",
            o_que=(f"Retorno do Juiz corregedor permanente ({dia}) sobre a "
                   f"impugnação de {i['nome']}: {corpo}"))
    if i["processo"].get("prenotacao_id"):
        _anotar(con, processo_id, tipo="AVISO", quando=agora, quem=usuario,
                artigo="TJMA 452, § 3º",
                o_que=("Se o prazo da prenotação foi suspenso na remessa, "
                       "retome-o na ficha da prenotação."))
    return {"desfecho": JUIZ_DECIDIU,
            "fase": _acertar_fase(con, processo_id, hoje=agora[:10],
                                  agora=agora)}


def passos_das_impugnacoes(con, processo_id: int, *, hoje: str) -> list[dict]:
    """O que fazer com cada impugnação, com o prazo e o artigo. Só lê."""
    passos: list[dict] = []
    abertas = []
    for i in impugnacoes(con, processo_id, hoje=hoje):
        nome, etapa = i["nome"], i["etapa"]
        if etapa == "ABERTA":
            abertas.append(i)
        elif etapa == "TRANSACAO":
            vencido = str(i["transacao_prazo_ate"]) < str(hoje)[:10]
            prorrogavel = not i.get("transacao_prorrogada_em")
            if vencido:
                o_que = (f"O prazo da transação com {nome} venceu em "
                         f"{i['transacao_prazo_ate']}: registre o acordo ou, "
                         "mantida a controvérsia, remeta ao Juiz corregedor "
                         "permanente.")
            else:
                o_que = (f"Transação com {nome}: prazo até "
                         f"{i['transacao_prazo_ate']} para formalizá-la ou "
                         "agendar a sessão ("
                         + ("15 dias úteis, prorrogáveis uma única vez por "
                            "mais 15, a pedido" if prorrogavel
                            else "já prorrogado; não cabe outra prorrogação")
                         + ").")
            passos.append({"o_que": o_que, "artigo": "art. 600, § 2º",
                           "prazo_ate": i["transacao_prazo_ate"],
                           "urgente": vencido})
        elif etapa == "INTIMAR_REJEICAO":
            passos.append({
                "o_que": f"Intimar {nome} da rejeição de plano — o prazo de "
                         "recurso, de 10 dias úteis, conta da intimação.",
                "artigo": "art. 600, § 4º"})
        elif etapa == "PRAZO_DE_RECURSO":
            passos.append({
                "o_que": f"Prazo de recurso de {nome} até "
                         f"{i['recurso_prazo_ate']} (10 dias úteis da "
                         "intimação). Sem recurso, o procedimento prossegue.",
                "artigo": "art. 600, § 4º",
                "prazo_ate": i["recurso_prazo_ate"]})
        elif etapa == "RECURSO_VENCIDO":
            passos.append({
                "o_que": f"O prazo de recurso de {nome} venceu em "
                         f"{i['recurso_prazo_ate']}: registre que o "
                         "procedimento prossegue.",
                "artigo": "art. 600, § 4º",
                "prazo_ate": i["recurso_prazo_ate"], "urgente": True})
        elif etapa == "INTIMAR_CONTRARRAZOES":
            passos.append({
                "o_que": f"{nome} recorreu: intimar o interessado para, "
                         "querendo, apresentar contrarrazões em 10 dias úteis.",
                "artigo": "art. 600, § 5º"})
        elif etapa == "CONTRARRAZOES":
            if not i.get("contrarrazoes_em") \
                    and str(i["contrarrazoes_prazo_ate"]) >= str(hoje)[:10]:
                passos.append({
                    "o_que": f"Contrarrazões ao recurso de {nome} até "
                             f"{i['contrarrazoes_prazo_ate']} (10 dias úteis); "
                             "depois, os autos vão ao Juiz corregedor "
                             "permanente.",
                    "artigo": "art. 600, § 5º",
                    "prazo_ate": i["contrarrazoes_prazo_ate"]})
            else:
                passos.append({
                    "o_que": f"Remeter ao Juiz corregedor permanente o recurso "
                             f"de {nome}, com as suas informações "
                             "complementares.",
                    "artigo": "art. 600, § 5º; art. 601", "urgente": True})
        elif etapa == AO_JUIZ:
            passos.append({
                "o_que": f"Impugnação de {nome} com o Juiz corregedor "
                         f"permanente desde {str(i['remetida_em'])[:10]} — os "
                         "efeitos da prenotação ficam prorrogados. Registre o "
                         "retorno quando vier.",
                "artigo": "art. 600, § 3º"})
    if abertas:
        nomes = ", ".join(i["nome"] for i in abertas)
        passos.append({
            "o_que": f"Ouvir o requerente e o profissional sobre "
                     f"{len(abertas)} impugnação(ões) ({nomes}), em 5 dias "
                     "úteis, e tentar a mediação. Se a considerar infundada, "
                     "rejeite-a de plano por decisão fundamentada (§ 4º); "
                     "fundada e mantida a controvérsia, remeta ao Juiz "
                     "(§ 3º).",
            "artigo": "art. 600"})
    return passos


# ------------------------------------------------------------------- decidir


def o_que_falta_para_decidir(con: sqlite3.Connection, processo_id: int, *,
                             hoje: str) -> list[str]:
    """O que impede a decisão hoje. Só calcula.

    NÃO SE DECIDE PROCEDENTE COM ITEM PENDENTE — é a regra do usucapião, e vale
    aqui pelo mesmo motivo: registro com fase pulada nasce nulo.
    """
    faltas = []
    pendentes = o_que_falta(con, processo_id)
    if pendentes:
        faltas.append(
            f"{len(pendentes)} item(ns) da conferência do art. 592 ainda "
            "pendentes.")
    prazos = situacao_dos_prazos(con, processo_id, hoje=hoje)
    if prazos["sem_notificar"]:
        faltas.append(
            f"{len(prazos['sem_notificar'])} confrontante(s) ainda sem "
            "notificação (art. 598).")
    if prazos["no_prazo"]:
        faltas.append(
            f"{len(prazos['no_prazo'])} confrontante(s) ainda dentro do prazo "
            "de impugnação (art. 599).")
    #  A IMPUGNACAO SO DEIXA DE TRAVAR COM DESFECHO: rejeitada sem recurso no
    #  prazo (§ 4º), transação formalizada (§ 2º) ou o retorno do Juiz. Com os
    #  autos no Juiz, não se decide.
    sem_desfecho = [i for i in impugnacoes(con, processo_id, hoje=hoje)
                    if i["etapa"] not in DESFECHOS_QUE_LIBERAM]
    no_juiz = [i for i in sem_desfecho if i["etapa"] == AO_JUIZ]
    if no_juiz:
        faltas.append(
            f"{len(no_juiz)} impugnação(ões) com o Juiz corregedor permanente "
            "(art. 601) — a decisão espera o retorno.")
    if len(sem_desfecho) > len(no_juiz):
        faltas.append(
            f"{len(sem_desfecho) - len(no_juiz)} impugnação(ões) sem desfecho "
            "— o art. 600 manda ouvir o requerente e o profissional e tentar a "
            "mediação; a infundada se rejeita de plano (§ 4º), com prazo de "
            "recurso.")
    return faltas


def decidir(con: sqlite3.Connection, processo_id: int, *, sentido: str,
            fundamento: str, agora: str, hoje: str,
            usuario: str | None = None) -> dict:
    """A decisão do oficial (art. 604). ESCREVE.

    **DECISÃO FUNDAMENTADA** é o que o artigo diz, e por isso o texto é
    obrigatório: decisão sem fundamento é a que desfaz o registro depois.

    E DECIDIR NÃO É AVERBAR. Procedente, o processo segue até a averbação sair
    na matrícula — e quem a lavra é a tela do RI. É a decisão do CNIB, e aqui
    ela pesa mais: o desfecho **encerra uma matrícula e abre outra**.
    """
    p = _exigir_para_gravar(con, processo_id)
    sentido = _texto(sentido).upper()
    if sentido not in (PROCEDENTE, IMPROCEDENTE):
        raise RetificacaoError(
            "A decisão é PROCEDENTE ou IMPROCEDENTE.")
    if len(_texto(fundamento)) < MINIMO_DO_MOTIVO:
        raise RetificacaoError(
            "O art. 604 pede decisão FUNDAMENTADA. Escreva o fundamento — é "
            "ele que sustenta a averbação se alguém a questionar depois.")
    if p["decidido_em"]:
        raise RetificacaoError(
            f"Este processo já foi decidido em {p['decidido_em']} "
            f"({p['decisao']}).")

    if sentido == PROCEDENTE:
        faltas = o_que_falta_para_decidir(con, processo_id, hoje=hoje)
        if faltas:
            raise RetificacaoError(
                "Não dá para julgar procedente ainda: " + " ".join(faltas))

    proxima = "AVERBACAO" if sentido == PROCEDENTE else "CONCLUIDO"
    banco(con).escrever(
        """UPDATE rt_processos SET decisao = %s, decisao_fundamento = %s,
               decidido_em = %s, decidido_por = %s, fase = %s,
               atualizado_em = %s
            WHERE id = %s""",
        (sentido, _texto(fundamento), agora, usuario, proxima, agora,
         processo_id))
    _anotar(con, processo_id, tipo="DECISAO", quando=agora, quem=usuario,
            artigo="art. 604",
            o_que=f"Decidido {sentido}. {_texto(fundamento)}")
    if sentido == IMPROCEDENTE:
        _anotar(con, processo_id, tipo="AVISO", quando=agora, quem=usuario,
                artigo="art. 604, § 2º",
                o_que="O interessado tem 15 dias úteis para requerer, "
                      "fundamentadamente, que o oficial suscite dúvida.")
    return {"decisao": sentido, "fase": proxima}


def registrar_averbacao(con: sqlite3.Connection, processo_id: int, *,
                        ato_id: int, agora: str,
                        matricula_nova_id: int | None = None,
                        usuario: str | None = None) -> dict:
    """Amarra o processo à averbação que a tela do RI lavrou. ESCREVE.

    **CONFERE QUE O ATO EXISTE.** Sem isso batia na chave estrangeira e virava
    HTTP 500 no fim de um processo de meses — foi o defeito que o usucapião teve,
    e quem o achou lá foi o teste de TELA, porque o de domínio rodava com a
    trava desligada.

    E SÓ DEPOIS DE PROCEDENTE. Averbação sem decisão é registro sem fundamento.
    """
    p = _exigir_para_gravar(con, processo_id)
    if p["decisao"] != PROCEDENTE:
        raise RetificacaoError(
            "Só se averba depois de o oficial julgar procedente (art. 604, "
            "§ 1º).")
    bd = banco(con)
    if not bd.um("SELECT 1 FROM ri_atos WHERE id = %s", (ato_id,)):
        raise RetificacaoError(
            f"Não achei o ato nº {ato_id} no Registro de Imóveis. A averbação "
            "se lavra na matrícula, e este processo guarda qual foi.")
    if p["ato_id"]:
        raise RetificacaoError(
            f"Este processo já está amarrado ao ato nº {p['ato_id']}.")

    bd.escrever(
        """UPDATE rt_processos SET ato_id = %s, matricula_nova_id = %s,
               averbado_em = %s, fase = 'SIGEF', atualizado_em = %s
            WHERE id = %s""",
        (int(ato_id), matricula_nova_id, agora, agora, processo_id))
    _anotar(con, processo_id, tipo="AVERBACAO", quando=agora, quem=usuario,
            artigo="art. 604, § 1º",
            o_que=f"Averbação lavrada — ato nº {ato_id}.")
    if p["especie"] == NORMA.GEORREFERENCIADA:
        _anotar(con, processo_id, tipo="AVISO", quando=agora, quem=usuario,
                artigo="art. 620, § 2º",
                o_que="A serventia tem 30 dias para requerer o registro no "
                      "SIGEF, com o número da nova matrícula e os dados dos "
                      "proprietários, anexando a certidão de inteiro teor da "
                      "nova matrícula e da anterior encerrada.")
    return {"fase": "SIGEF"}


def registrar_sigef(con: sqlite3.Connection, processo_id: int, *,
                    protocolo: str, quando: str, agora: str,
                    usuario: str | None = None) -> dict:
    """Registra que o requerimento ao SIGEF foi feito. ESCREVE.

    É O PRAZO DA CASA, e o único deste rito que é da serventia e não das partes
    — art. 620, § 2º. Ele nasce **depois** do ato, quando o cliente já foi
    embora, e é por isso que se perde.
    """
    p = _exigir(con, processo_id)
    if not p["averbado_em"]:
        raise RetificacaoError(
            "O prazo do SIGEF conta da averbação da poligonal certificada "
            "(art. 620, § 2º), e este processo ainda não foi averbado.")
    if not _texto(protocolo):
        raise RetificacaoError(
            "Guarde o protocolo que o SIGEF devolveu — é a prova de que a "
            "serventia cumpriu o prazo.")
    banco(con).escrever(
        """UPDATE rt_processos SET sigef_requerido_em = %s,
               sigef_protocolo = %s, fase = 'CONCLUIDO', situacao = %s,
               encerrado_em = %s, atualizado_em = %s WHERE id = %s""",
        (quando, _texto(protocolo), ENCERRADO, agora, agora, processo_id))
    _anotar(con, processo_id, tipo="SIGEF", quando=agora, quem=usuario,
            artigo="art. 620, § 2º",
            o_que=f"Registro requerido no SIGEF em {quando} — protocolo "
                  f"{_texto(protocolo)}.")
    return {"fase": "CONCLUIDO"}


# ------------------------------------------------------------------- as listas


def abertos(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    return banco(con).ler(
        """SELECT p.*, m.numero AS matricula_numero
             FROM rt_processos p
             LEFT JOIN ri_matriculas m ON m.id = p.matricula_id
            WHERE p.situacao = %s
         ORDER BY p.id DESC LIMIT %s""", (EM_ANDAMENTO, limite))


def sigef_a_vencer(con: sqlite3.Connection) -> list[dict]:
    """Os processos averbados cujo requerimento ao SIGEF ainda não foi feito.

    É O ACHADO QUE SOZINHO JUSTIFICA ESTE MÓDULO. O art. 620, § 2º dá **30
    dias** à serventia depois de averbada a poligonal certificada, e nada no
    sistema acompanhava esse prazo — ele nasce quando o ato já saiu.

    Não calcula o vencimento: devolve a data da averbação, e quem conta os dias
    é quem já conta os prazos desta casa.
    """
    return banco(con).ler(
        """SELECT p.*, m.numero AS matricula_numero
             FROM rt_processos p
             LEFT JOIN ri_matriculas m ON m.id = p.matricula_id
            WHERE p.averbado_em IS NOT NULL
              AND COALESCE(p.sigef_requerido_em, '') = ''
              AND p.especie = %s
         ORDER BY p.averbado_em, p.id""", (NORMA.GEORREFERENCIADA,))


def proximos_passos(con: sqlite3.Connection, processo_id: int, *,
                    hoje: str) -> list[dict]:
    """O que fazer agora, calculado do estado. Só lê.

    NUM RITO DE MESES, «E AGORA?» É A PERGUNTA QUE MAIS SE REPETE, e ela merece
    resposta na tela e não na cabeça de quem lembra. É o que o usucapião já faz.
    """
    p = _exigir(con, processo_id)
    passos: list[dict] = []

    if p["situacao"] == ENCERRADO:
        return [{"o_que": "Processo concluído.", "artigo": None}]

    if p["averbado_em"] and not p["sigef_requerido_em"] \
            and p["especie"] == NORMA.GEORREFERENCIADA:
        passos.append({
            "o_que": "Requerer o registro no SIGEF — a serventia tem 30 dias "
                     f"da averbação, que foi em {p['averbado_em']}.",
            "artigo": "art. 620, § 2º", "urgente": True})
        return passos

    if p["decisao"] == PROCEDENTE and not p["averbado_em"]:
        passos.append({
            "o_que": "Lavrar a averbação na matrícula, encerrá-la e abrir a "
                     "nova, transportando os ônus e averbações não cancelados.",
            "artigo": "art. 604, § 1º"})
        return passos

    pendentes = o_que_falta(con, processo_id)
    if pendentes:
        passos.append({
            "o_que": f"Conferir {len(pendentes)} item(ns) do art. 592 — o "
                     f"primeiro é: {pendentes[0]['item']}",
            "artigo": pendentes[0].get("artigo") or "art. 592"})

    faltam = quem_precisa_ser_notificado(con, processo_id)
    if faltam:
        passos.append({
            "o_que": f"Notificar {len(faltam)} confrontante(s) — comece por "
                     f"{faltam[0]['nome']}.",
            "artigo": "art. 598"})

    prazos = situacao_dos_prazos(con, processo_id, hoje=hoje)
    if prazos["no_prazo"]:
        passos.append({
            "o_que": f"Aguardar o prazo de {len(prazos['no_prazo'])} "
                     "confrontante(s).",
            "artigo": "art. 599"})
    for c in prazos["venceu"]:
        passos.append({
            "o_que": f"O prazo de {c['nome']} venceu em {c['prazo_ate']} — a "
                     "anuência se presume. Marque o silêncio para ficar no "
                     "andamento.",
            "artigo": "art. 599, § 1º"})
    passos.extend(passos_das_impugnacoes(con, processo_id, hoje=hoje))

    if not passos:
        passos.append({
            "o_que": "Está pronto para a sua decisão fundamentada.",
            "artigo": "art. 604"})
    return passos

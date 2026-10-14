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
    do edital do usucapião.
"""
from __future__ import annotations

import sqlite3
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
    ("MEDIACAO", "Mediação ou conciliação (art. 600, § 2º)"),
    ("AO_JUIZ", "Remetido ao Juiz (art. 601)"),
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


def processo(con: sqlite3.Connection, processo_id: int) -> sqlite3.Row | None:
    con.row_factory = sqlite3.Row
    return con.execute("SELECT * FROM rt_processos WHERE id = ?",
                       (processo_id,)).fetchone()


def _exigir(con: sqlite3.Connection, processo_id: int) -> sqlite3.Row:
    achado = processo(con, processo_id)
    if not achado:
        raise RetificacaoError(
            f"Não achei o processo de retificação nº {processo_id}.")
    return achado


def confrontantes(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT * FROM rt_confrontantes WHERE processo_id = ?
            ORDER BY papel, nome""", (processo_id,))]


def pecas(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM rt_pecas WHERE processo_id = ? ORDER BY id",
        (processo_id,))]


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

    cur = con.execute(
        """INSERT INTO rt_pecas (processo_id, tipo, descricao, arquivo,
               sha256, entregue_em, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?)""",
        (processo_id, tipo, _texto(descricao) or None,
         _texto(arquivo) or None, _texto(sha256) or None,
         _texto(entregue_em) or None, agora, usuario))
    novo = int(cur.lastrowid)

    con.execute(
        """UPDATE rt_conferencia
              SET situacao = 'ATENDIDO',
                  nota = COALESCE(nota, ?),
                  marcado_em = ?,
                  marcado_por = ?
            WHERE processo_id = ? AND item = ?
              AND COALESCE(situacao, 'PENDENTE') = 'PENDENTE'""",
        ("Atendido pela peça juntada.", agora, usuario, processo_id, tipo))
    _anotar(con, processo_id, tipo="PECA", quando=agora, quem=usuario,
            o_que=f"Peça juntada: {tipo}"
                  + (f" — {_texto(descricao)}" if _texto(descricao) else "."))
    return novo


def andamento(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT a.*, c.nome AS confrontante_nome
             FROM rt_andamento a
             LEFT JOIN rt_confrontantes c ON c.id = a.confrontante_id
            WHERE a.processo_id = ? ORDER BY a.id""", (processo_id,))]


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

    con.row_factory = sqlite3.Row
    if not con.execute("SELECT 1 FROM ri_matriculas WHERE id = ?",
                       (matricula_id,)).fetchone():
        raise RetificacaoError(
            f"Não achei a matrícula nº {matricula_id}. A retificação é do "
            "registro: sem matrícula não há o que retificar.")
    if con.execute("SELECT 1 FROM rt_processos WHERE numero = ?",
                   (_texto(numero),)).fetchone():
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
                  "sigef_codigo", "prenotacao", "protocolo_id", "observacao"):
        if chave in extras:
            campos[chave] = extras[chave] or None

    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = con.execute(
        f"INSERT INTO rt_processos ({colunas}) VALUES ({marcas})",
        tuple(campos.values()))
    novo = int(cur.lastrowid)

    _anotar(con, novo, tipo="AUTUACAO", quando=agora, quem=usuario,
            o_que=f"Processo autuado — {NORMA.NOME_DA_ESPECIE[especie]}, "
                  f"{NORMA.NOME_DO_FUNDAMENTO[fundamento]}.")
    _semear_conferencia(con, novo, especie=especie, rural=bool(rural))
    return novo


def _anotar(con: sqlite3.Connection, processo_id: int, *, tipo: str,
            o_que: str, quando: str, quem: str | None = None,
            artigo: str | None = None,
            confrontante_id: int | None = None) -> None:
    con.execute(
        """INSERT INTO rt_andamento (processo_id, quando, tipo, o_que, artigo,
               confrontante_id, quem)
           VALUES (?,?,?,?,?,?,?)""",
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
    for item in itens:
        con.execute(
            """INSERT OR IGNORE INTO rt_conferencia (processo_id, item, artigo)
               VALUES (?,?,?)""",
            (processo_id, item["o_que"], item["artigo"]))


def conferencia(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM rt_conferencia WHERE processo_id = ? ORDER BY id",
        (processo_id,))]


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
    cur = con.execute(
        """UPDATE rt_conferencia SET situacao = ?, nota = ?, marcado_em = ?,
               marcado_por = ?
            WHERE processo_id = ? AND item = ?""",
        (situacao, _texto(nota) or None, agora, usuario, processo_id, item))
    if cur.rowcount == 0:
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
    cur = con.execute(
        """INSERT INTO rt_confrontantes (processo_id, papel, nome, nome_norm,
               documento, endereco, matricula_contigua, serventia_contigua,
               divisa_afetada, assinou_planta, carta_anuencia, criado_em,
               criado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (processo_id, papel, _texto(nome), normalizar_nome(_texto(nome)),
         _texto(documento) or None, _texto(endereco) or None,
         _texto(matricula_contigua) or None, _texto(serventia_contigua) or None,
         1 if divisa_afetada else 0, 1 if assinou_planta else 0,
         1 if carta_anuencia else 0, agora, usuario))
    novo = int(cur.lastrowid)
    _anotar(con, processo_id, tipo="CONFRONTANTE", quando=agora, quem=usuario,
            confrontante_id=novo,
            o_que=f"{NOME_DO_PAPEL[papel]} anotado: {_texto(nome)}.")
    return novo


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
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM rt_confrontantes WHERE id = ?",
                        (confrontante_id,)).fetchone()
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
        processo = dict(con.execute(
            "SELECT * FROM rt_processos WHERE id = ?",
            (int(linha["processo_id"]),)).fetchone() or {})
        if processo.get("matricula_id"):
            m = con.execute("SELECT numero FROM ri_matriculas WHERE id = ?",
                            (processo["matricula_id"],)).fetchone()
            if m:
                processo["matricula_numero"] = m[0]
        try:
            teor = NOTIF.montar(processo=processo, confrontante=dict(linha),
                                serventia=serventia,
                                hoje_extenso=hoje_extenso)
        except NOTIF.NotificacaoError as erro:
            raise RetificacaoError(str(erro)) from erro

    con.execute(
        """UPDATE rt_confrontantes SET notificado_em = ?, forma = ?,
               recebido_em = ?, prazo_ate = ?,
               teor_expedido = COALESCE(?, teor_expedido)
            WHERE id = ?""",
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
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM rt_confrontantes WHERE id = ?",
                        (confrontante_id,)).fetchone()
    if not linha:
        raise RetificacaoError("Não achei esse confrontante.")
    if resposta == IMPUGNOU and len(_texto(impugnacao)) < MINIMO_DO_MOTIVO:
        raise RetificacaoError(
            "A impugnação tem de ser fundamentada — «não bastando mera "
            "alegação de prejuízo» (art. 593). Escreva o que ele alegou.")

    con.execute(
        """UPDATE rt_confrontantes SET resposta = ?, respondido_em = ?,
               impugnacao = ? WHERE id = ?""",
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
    if prazos["impugnaram"]:
        faltas.append(
            f"{len(prazos['impugnaram'])} impugnação(ões) sem desfecho — "
            "o art. 600 manda ouvir o requerente e o profissional e tentar a "
            "mediação antes.")
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
    p = _exigir(con, processo_id)
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
    con.execute(
        """UPDATE rt_processos SET decisao = ?, decisao_fundamento = ?,
               decidido_em = ?, decidido_por = ?, fase = ?, atualizado_em = ?
            WHERE id = ?""",
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
    p = _exigir(con, processo_id)
    if p["decisao"] != PROCEDENTE:
        raise RetificacaoError(
            "Só se averba depois de o oficial julgar procedente (art. 604, "
            "§ 1º).")
    con.row_factory = sqlite3.Row
    if not con.execute("SELECT 1 FROM ri_atos WHERE id = ?",
                       (ato_id,)).fetchone():
        raise RetificacaoError(
            f"Não achei o ato nº {ato_id} no Registro de Imóveis. A averbação "
            "se lavra na matrícula, e este processo guarda qual foi.")
    if p["ato_id"]:
        raise RetificacaoError(
            f"Este processo já está amarrado ao ato nº {p['ato_id']}.")

    con.execute(
        """UPDATE rt_processos SET ato_id = ?, matricula_nova_id = ?,
               averbado_em = ?, fase = 'SIGEF', atualizado_em = ?
            WHERE id = ?""",
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
    con.execute(
        """UPDATE rt_processos SET sigef_requerido_em = ?, sigef_protocolo = ?,
               fase = 'CONCLUIDO', situacao = ?, encerrado_em = ?,
               atualizado_em = ? WHERE id = ?""",
        (quando, _texto(protocolo), ENCERRADO, agora, agora, processo_id))
    _anotar(con, processo_id, tipo="SIGEF", quando=agora, quem=usuario,
            artigo="art. 620, § 2º",
            o_que=f"Registro requerido no SIGEF em {quando} — protocolo "
                  f"{_texto(protocolo)}.")
    return {"fase": "CONCLUIDO"}


# ------------------------------------------------------------------- as listas


def abertos(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT p.*, m.numero AS matricula_numero
             FROM rt_processos p
             LEFT JOIN ri_matriculas m ON m.id = p.matricula_id
            WHERE p.situacao = ?
         ORDER BY p.id DESC LIMIT ?""", (EM_ANDAMENTO, limite))]


def sigef_a_vencer(con: sqlite3.Connection) -> list[dict]:
    """Os processos averbados cujo requerimento ao SIGEF ainda não foi feito.

    É O ACHADO QUE SOZINHO JUSTIFICA ESTE MÓDULO. O art. 620, § 2º dá **30
    dias** à serventia depois de averbada a poligonal certificada, e nada no
    sistema acompanhava esse prazo — ele nasce quando o ato já saiu.

    Não calcula o vencimento: devolve a data da averbação, e quem conta os dias
    é quem já conta os prazos desta casa.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT p.*, m.numero AS matricula_numero
             FROM rt_processos p
             LEFT JOIN ri_matriculas m ON m.id = p.matricula_id
            WHERE p.averbado_em IS NOT NULL
              AND COALESCE(p.sigef_requerido_em, '') = ''
              AND p.especie = ?
         ORDER BY p.averbado_em""", (NORMA.GEORREFERENCIADA,))]


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
    if prazos["impugnaram"]:
        passos.append({
            "o_que": f"Ouvir o requerente e o profissional sobre "
                     f"{len(prazos['impugnaram'])} impugnação(ões), em 5 dias "
                     "úteis, e tentar a mediação.",
            "artigo": "art. 600"})

    if not passos:
        passos.append({
            "o_que": "Está pronto para a sua decisão fundamentada.",
            "artigo": "art. 604"})
    return passos

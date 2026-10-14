"""
O QUE SÓ O OFICIAL PODE INFORMAR — e o aviso que não deixa esquecer.

POR QUE ISTO EXISTE
    O sistema esteve SUSPENSO desde 18/08/2026 e vai voltar. Quando voltar,
    há coisas que o acervo não sabe dizer e que só quem conhece o livro físico
    responde — o próximo número de um livro que o E-Ofício nunca guardou, por
    exemplo.

    Até 26/08/2026 essas coisas moravam numa lista de pendências dentro da
    documentação, e o balcão não as via. **Documentação não avisa ninguém.** O
    oficial pediu, e está certo: aviso na tela e uma aba para informar.

    E ele pediu que valesse **para todas as atribuições**, não só para o
    Protesto. Por isso este módulo é do núcleo, e não de um módulo de
    atribuição.

A REGRA QUE FAZ O AVISO VALER: PENDÊNCIA É DECLARADA, NÃO ADIVINHADA
    Uma pendência entra aqui porque **alguém a descobriu e a declarou**, com o
    motivo medido — a carga do acervo declara as séries que não soube semear.

    Um sistema NOVO, sem carga nenhuma, não tem pendência alguma, e começar do
    número 1 nele está certo. Se este módulo listasse "toda série sem contador",
    ele gritaria quinze avisos numa instalação limpa — e **alarme que soa
    sempre é alarme que ninguém ouve**. Esta casa já pagou por isso uma vez,
    quando a conferência do rodapé gritava falso em 191 remessas boas.

DOIS TIPOS, PORQUE SÃO DUAS COISAS DIFERENTES

    `NUMERO`  — tem resposta numérica e formulário ali mesmo. Quem grava é
                `escrituracao.fixar_numeracao`, que recusa baixar contador.
    `DECISAO` — não é um número: é uma escolha a tomar noutro lugar (encerrar
                um livro, por exemplo). A aba diz o que é, por que importa e
                para onde ir.

DISPENSAR EXIGE MOTIVO ESCRITO
    Dispensar é decisão do oficial; ignorar não é. É a mesma regra do rito do
    usucapião, e existe pelo mesmo motivo: o que se dispensa sem motivo
    ninguém consegue explicar depois.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import escrituracao as ESC
import livro_nucleo as LN

TIPOS = ("NUMERO", "DECISAO")
SITUACOES = ("ABERTA", "RESOLVIDA", "DISPENSADA")

# O prefixo da chave diz de que espécie ela é, e a chave inteira é única: a
# mesma pendência declarada duas vezes é a mesma linha.
PREFIXO_NUMERACAO = "numeracao"
PREFIXO_DECISAO = "decisao"


class ImplantacaoError(ValueError):
    """Erro de regra da implantação, com a mensagem pronta para o balcão."""


# AS DECISÕES QUE O ACERVO DESTA CASA COBRA, e que não são número.
#
# Cada uma traz o FATO MEDIDO que a torna pendência. Nada aqui é hipótese: o
# Livro 6 está no acervo, aberto e vazio, e alguém tem de dizer o que fazer
# com ele antes de o Livro de Apontamento andar.
CATALOGO_DE_DECISOES: tuple[dict, ...] = (
    {
        "chave": f"{PREFIXO_DECISAO}:PT_APONTAMENTO:livro-6",
        "atribuicao": 2,
        "serie": "PT_APONTAMENTO",
        "titulo": "O Livro 6 de Apontamento, aberto e nunca usado",
        "motivo": (
            "O acervo do E-Ofício tem o Livro 6 de Apontamento aberto em "
            "05/03/2024, sem um único lançamento, ao lado do Livro 1 em uso. "
            "O sistema não decide o que fazer com livro aberto e vazio: ou ele "
            "se encerra com termo dizendo que nada foi lançado, ou se "
            "reaproveita como o próximo."),
        "consequencia": (
            "Enquanto ninguém decidir, o Livro de Apontamento tem dois livros "
            "abertos na mesma série — e a conferência da inspeção pergunta "
            "por que."),
        "onde": "nucleo_livros",
    },
    {
        "chave": f"{PREFIXO_DECISAO}:PT_RETORNO:letra-566",
        "atribuicao": 2,
        "serie": None,
        "titulo": "A letra da posição 566, para apresentante novo",
        "motivo": (
            "No retorno à CRA, a posição 566 leva uma letra quando o título é "
            "protestado. Esta casa sempre escreveu «A» ou «P», e cada "
            "apresentante recebeu sempre a mesma — 31 de 32, em 315 títulos. "
            "Mas apresentante NOVO não tem retorno anterior para imitar, e "
            "entre «A» e «P» o empate é exato (74 e 74). "
            "E há uma terceira opção, medida em 26/08/2026 no acervo da "
            "serventia de Sergipe: **branco**. Lá a posição 566 vem vazia em "
            "TODOS os 2.087 retornos, e a Central aceita. Ou seja: a letra "
            "não é regra nacional do apresentante — é convenção de cada casa, "
            "e o branco também é aceito."),
        "consequencia": (
            "Enquanto ninguém decidir, o retorno de um apresentante novo é "
            "RECUSADO pelo sistema, que pede a letra em vez de chutar — e o "
            "título fica sem voltar para a Central."),
        "onde": "protesto_retornos",
    },
    # AS DUAS DO CENPROT NAO ESTAO AQUI, e e de proposito.
    #
    # Elas entraram nesta lista em 26/08/2026 — "de onde vem a chave unica" e
    # "o instrumento eletronico assinado" — e sairam no mesmo dia, quando o
    # oficial respondeu:
    #
    #   "Serventia nao gera chave unica. No protesto apenas trabalhamos com os
    #    arquivos da CRA: recebe, manda, atualiza, e geramos os protocolos, as
    #    intimacoes e os registros de protesto com base nos requisitos legais."
    #
    # Isso e ESCOPO, e nao pendencia: o arquivo do CENPROT nao e trabalho desta
    # casa. Pendencia e o que falta fazer; isto e o que nao se faz.
    #
    # Fica escrito porque `CENPROT_XML_MEDIDO.md` guarda a medicao inteira —
    # 903 arquivos, 17.270 titulos — e quem a ler vai perguntar por que ela
    # existe e o arquivo nao.
)


# ------------------------------------------------------------- declarar


def declarar_livro_do_casamento(con: sqlite3.Connection, *, quantos: int,
                                agora: str,
                                usuario: str | None = None) -> bool:
    """Pergunta ao oficial se `intTipoRegistroLivro = 1` é o Livro B-Auxiliar.

    ACHADO EM 26/08/2026, construindo a certidão do RCPN. O acervo separa os
    casamentos em dois grupos por essa coluna, e o grupo `1` tem numeração
    PRÓPRIA — três casamentos no Livro 1, registros 26 a 59, enquanto os do
    grupo `0` correm de 111 a 1.011 em sete livros.

    Numeração própria em livro próprio é exatamente o que distingue o
    **B-Auxiliar** (casamento religioso com efeito civil) do B. Mas são três
    casos, e três casos não provam uma regra: podem ser os primeiros de um
    livro que mal começou, ou um cadastro que alguém usou para outra coisa.

    **O OFICIAL RESPONDEU EM 26/08/2026**: "não tivemos casamentos no livro
    B-Auxiliar nos últimos anos". Isso resolve uma coisa e não a outra.

    Resolve a URGÊNCIA — se não entra casamento religioso há anos, o contador
    que falta não segura nenhum ato próximo. Não resolve o que são os três do
    acervo: eles são de **1979, 1982 e 1987**, e "últimos anos" não chega lá.

    Por isso a pergunta mudou de forma em vez de ser fechada. Ela deixou de
    ser "esses casamentos foram religiosos?", que ninguém tem como saber de
    cabeça sobre 1979, e passou a ser **"o livro de papel diz?"** — com o
    número, o livro e a folha de cada um, que é o que se leva para a estante.

    POR ISSO É PERGUNTA, E NÃO CÓDIGO. Mandar esses três para o B-Auxiliar por
    conta própria poria assento em livro errado — e assento em livro errado é
    o que a inspeção acha primeiro. A regra da casa, de 24/08/2026: onde não há
    padrão anterior a imitar, o sistema recusa e pergunta.

    E ela fecha uma das perguntas que já estavam abertas: o B-Auxiliar era uma
    das três séries do RCPN que estavam CALADAS, sem contador e sem aviso.
    """
    return declarar(
        con, "RCPN_LIVRO_DO_CASAMENTO_RELIGIOSO", tipo="DECISAO",
        atribuicao=6, serie="RC_B_AUXILIAR",   # 6 = Registro Civil
        titulo="Os casamentos do segundo grupo são do Livro B-Auxiliar?",
        motivo=(
            f"O acervo separa os casamentos em dois grupos, por uma coluna "
            f"chamada `intTipoRegistroLivro`, e não diz o que ela significa. "
            f"O segundo grupo tem {quantos} casamento(s), todos no Livro 1, "
            f"com numeração PRÓPRIA — que não continua a dos outros (111 a "
            f"1.011, em sete livros). Livro próprio com numeração própria é o "
            f"que distingue o B-Auxiliar, do casamento religioso com efeito "
            f"civil.\n\n"
            f"SÃO ESTES, e todos os três são antigos:\n"
            f"  • registro 26, Livro 1, folha 13 — 28/12/1979\n"
            f"  • registro 44, Livro 1, folha 23 — 17/11/1982\n"
            f"  • registro 59, Livro 1, folha 30 — 04/08/1987\n\n"
            f"Você disse em 26/08/2026 que não houve casamento no B-Auxiliar "
            f"nos últimos anos, e isso bate com o que está aqui: o mais novo "
            f"deles tem quase quarenta anos. Por isso a pergunta não é de "
            f"memória, e sim do LIVRO DE PAPEL: nas folhas acima, o livro é o "
            f"B ou o B-Auxiliar?\n\n"
            f"Se for o B-Auxiliar, informe também o próximo número dele em "
            f"«Numeração dos livros» — ele nunca teve contador."),
        consequencia=(
            "VOCÊ JÁ DECIDIU ISTO em 26/08/2026: «deixe como o E-Ofício "
            "guardou, pendente de confirmação quando forem consultados "
            "efetivamente». Os três continuam no Livro B, e nada se move.\n\n"
            "A pendência fica aberta porque a confirmação é no papel, e o "
            "sistema não a força: cada um dos três assentos leva um AVISO NA "
            "PRÓPRIA FICHA, que aparece no dia em que alguém o abrir — pode "
            "ser daqui a cinco anos, com outro escrevente no balcão. Quem "
            "conferir na estante corrige ali mesmo.\n\n"
            "E nada trava: como você disse, não entra casamento religioso há "
            "anos, então o contador que falta no B-Auxiliar não segura "
            "nenhum ato próximo."),
        agora=agora, usuario=usuario)


def declarar(con: sqlite3.Connection, chave: str, *, tipo: str, titulo: str,
             motivo: str, agora: str, consequencia: str | None = None,
             atribuicao: int | None = None, serie: str | None = None,
             usuario: str | None = None) -> bool:
    """Declara uma pendência. ESCREVE. Devolve True se ela é nova.

    REPETÍVEL POR CONSTRUÇÃO, e isso importa: a carga do acervo pode rodar
    duas vezes, e a segunda não pode reabrir o que o oficial já resolveu nem
    apagar o que ele escreveu ao resolver.
    """
    if tipo not in TIPOS:
        raise ImplantacaoError(
            f"Tipo de pendência desconhecido: {tipo!r}. Os que existem são "
            f"{', '.join(TIPOS)}.")
    cur = con.execute(
        """INSERT OR IGNORE INTO nu_implantacao(chave, tipo, atribuicao,
               titulo, motivo, consequencia, serie, situacao, declarada_em,
               declarada_por)
           VALUES (?,?,?,?,?,?,?,'ABERTA',?,?)""",
        (chave, tipo, atribuicao, titulo, motivo, consequencia, serie, agora,
         usuario))
    return cur.rowcount > 0


def declarar_numeracao(con: sqlite3.Connection, serie: str, motivo: str, *,
                       agora: str, usuario: str | None = None) -> bool:
    """Declara que uma série ficou sem contador semeado. ESCREVE.

    Chamada por `acervo_carga.semear_numeracao`, que é quem descobre. O motivo
    vem medido de lá — `SEM_CONTADOR_NO_ACERVO` —, e não é escrito aqui.
    """
    try:
        s = LN.serie(serie)
        nome = s.nome
        atribuicao = s.atribuicao
    except (KeyError, LN.LivroError):
        nome, atribuicao = serie, None
    return declarar(
        con, f"{PREFIXO_NUMERACAO}:{serie}", tipo="NUMERO",
        titulo=f"O próximo número do {nome}", motivo=motivo,
        consequencia=(
            "Sem informar, o primeiro ato desta série nasce com o **número "
            "1** sobre um acervo que já passou disso — e número de ordem "
            "repetido é o defeito de 18/08/2026 outra vez."),
        atribuicao=atribuicao, serie=serie, agora=agora, usuario=usuario)


def declarar_catalogo(con: sqlite3.Connection, *, agora: str,
                      usuario: str | None = None) -> int:
    """Declara as decisões do catálogo. ESCREVE. Devolve quantas são novas."""
    novas = 0
    for item in CATALOGO_DE_DECISOES:
        novas += declarar(
            con, item["chave"], tipo="DECISAO", titulo=item["titulo"],
            motivo=item["motivo"], consequencia=item.get("consequencia"),
            atribuicao=item.get("atribuicao"), serie=item.get("serie"),
            agora=agora, usuario=usuario)
    return novas


# -------------------------------------------------------------- resolver


def resolver_numero(con: sqlite3.Connection, chave: str, proximo: Any, *,
                    agora: str, usuario: str | None = None,
                    observacao: str | None = None) -> dict:
    """Informa o próximo número da série e fecha a pendência. ESCREVE.

    QUEM RECUSA BAIXAR O CONTADOR é `escrituracao.fixar_numeracao`, e não
    esta função: número igual ou menor que o maior já usado repetiria número
    de ordem, e é exatamente isso que o núcleo existe para impedir. Repetir a
    regra aqui daria duas versões dela.
    """
    linha = ler(con, chave)
    if not linha:
        raise ImplantacaoError(f"Pendência {chave!r} não encontrada.")
    if linha["tipo"] != "NUMERO":
        raise ImplantacaoError(
            f"A pendência «{linha['titulo']}» não é de número — ela é uma "
            f"decisão a tomar, e se resolve dizendo o que foi decidido.")
    if not linha["serie"]:
        raise ImplantacaoError(
            f"A pendência «{linha['titulo']}» não diz de que série é, e o "
            f"contador mora na série.")

    novo = ESC.fixar_numeracao(
        con, linha["serie"], proximo, usuario=usuario, agora=agora,
        motivo=(observacao or "informado na aba de implantação"))
    con.execute(
        """UPDATE nu_implantacao SET situacao='RESOLVIDA', valor=?,
               observacao=?, resolvida_em=?, resolvida_por=? WHERE chave=?""",
        (str(novo), observacao, agora, usuario, chave))
    return {"chave": chave, "serie": linha["serie"], "proximo": novo}


def resolver_decisao(con: sqlite3.Connection, chave: str, *, observacao: str,
                     agora: str, usuario: str | None = None) -> dict:
    """Registra o que foi decidido, e fecha a pendência. ESCREVE.

    O QUE FOI DECIDIDO SE ESCREVE, e não se marca. "Resolvido" sem dizer o que
    se fez não responde a pergunta que a inspeção faz seis meses depois.
    """
    linha = ler(con, chave)
    if not linha:
        raise ImplantacaoError(f"Pendência {chave!r} não encontrada.")
    texto = (observacao or "").strip()
    if len(texto) < 10:
        raise ImplantacaoError(
            "Escreva o que foi decidido. «Resolvido» sozinho não responde a "
            "pergunta que a inspeção faz seis meses depois.")
    con.execute(
        """UPDATE nu_implantacao SET situacao='RESOLVIDA', observacao=?,
               resolvida_em=?, resolvida_por=? WHERE chave=?""",
        (texto, agora, usuario, chave))
    return {"chave": chave, "observacao": texto}


def dispensar(con: sqlite3.Connection, chave: str, *, motivo: str, agora: str,
              usuario: str | None = None) -> dict:
    """Dispensa a pendência, com motivo escrito. ESCREVE.

    DISPENSAR EXIGE MOTIVO — é a mesma regra do rito do usucapião. Dispensar é
    decisão do oficial; ignorar não é.
    """
    linha = ler(con, chave)
    if not linha:
        raise ImplantacaoError(f"Pendência {chave!r} não encontrada.")
    texto = (motivo or "").strip()
    if len(texto) < 10:
        raise ImplantacaoError(
            "Dispensar exige motivo escrito. Dispensar é decisão sua; ignorar "
            "não é.")
    con.execute(
        """UPDATE nu_implantacao SET situacao='DISPENSADA', observacao=?,
               resolvida_em=?, resolvida_por=? WHERE chave=?""",
        (texto, agora, usuario, chave))
    return {"chave": chave, "motivo": texto}


def reabrir(con: sqlite3.Connection, chave: str, *, agora: str,
            usuario: str | None = None) -> dict:
    """Reabre uma pendência resolvida por engano. ESCREVE.

    O que foi escrito ao resolver FICA — engano se conserta à vista, e não
    apagando o que se disse antes.
    """
    linha = ler(con, chave)
    if not linha:
        raise ImplantacaoError(f"Pendência {chave!r} não encontrada.")
    con.execute(
        """UPDATE nu_implantacao SET situacao='ABERTA', resolvida_em=NULL,
               resolvida_por=NULL WHERE chave=?""", (chave,))
    return {"chave": chave}


# -------------------------------------------------------------- consultas


def ler(con: sqlite3.Connection, chave: str) -> sqlite3.Row | None:
    """Uma pendência. Só LÊ."""
    return con.execute("SELECT * FROM nu_implantacao WHERE chave=?",
                       (chave,)).fetchone()


def _com_atribuicao(linha: sqlite3.Row) -> dict:
    d = dict(linha)
    numero = d.get("atribuicao")
    d["atribuicao_nome"] = NOME_DA_ATRIBUICAO.get(numero, "Todas")
    if d.get("serie"):
        try:
            d["serie_nome"] = LN.serie(d["serie"]).nome
        except (KeyError, LN.LivroError):
            d["serie_nome"] = d["serie"]
    return d


# Os nomes como o balcão os chama, e não os do cadastro do TJ: a aba é para
# quem trabalha aqui.
NOME_DA_ATRIBUICAO: dict[int, str] = {
    1: "Notas", 2: "Protesto", 3: "RCPJ", 4: "RTD",
    5: "Registro de Imóveis", 6: "Registro Civil",
}


def abertas(con: sqlite3.Connection) -> list[dict]:
    """As pendências que esperam você. Só LÊ.

    Em ordem de atribuição e depois de título — a aba se lê por atribuição,
    que é como o balcão pensa.
    """
    return [_com_atribuicao(r) for r in con.execute(
        """SELECT * FROM nu_implantacao WHERE situacao='ABERTA'
            ORDER BY COALESCE(atribuicao, 99), tipo, titulo""")]


def fechadas(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    """O que já foi resolvido ou dispensado, do mais novo. Só LÊ."""
    return [_com_atribuicao(r) for r in con.execute(
        """SELECT * FROM nu_implantacao WHERE situacao<>'ABERTA'
            ORDER BY resolvida_em DESC, chave LIMIT ?""", (int(limite),))]


def contagem(con: sqlite3.Connection) -> dict:
    """Quantas abertas, e quantas por atribuição. Só LÊ — para o aviso.

    Chamada em TODA tela, junto do resto das estatísticas. Por isso é uma
    consulta só, sobre um índice, e não abre transação de escrita.
    """
    linhas = list(con.execute(
        """SELECT COALESCE(atribuicao, 99) a, COUNT(*) n
             FROM nu_implantacao WHERE situacao='ABERTA' GROUP BY 1"""))
    por_atribuicao = {int(r["a"]): int(r["n"]) for r in linhas}
    return {
        "abertas": sum(por_atribuicao.values()),
        "por_atribuicao": por_atribuicao,
        "atribuicoes": sorted(
            NOME_DA_ATRIBUICAO.get(a, "Todas") for a in por_atribuicao),
    }

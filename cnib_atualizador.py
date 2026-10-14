"""O ATUALIZADOR DO CNIB — **quem grava o que a Central respondeu.**

O `cnib_api.py` fala com a Central e não grava nada; este módulo pega o que
ele trouxe e **escreve no espelho** (`ri_cnib_ordens` + `ri_cnib_pessoas`),
deixando registrada cada leitura em `ri_cnib_leituras`. A divisão é de
propósito e está escrita lá: transporte de um lado, decisão de gravar do
outro.

**ELE NÃO AVERBA, NÃO DECIDE E NÃO AVISA NINGUÉM.** Quem transforma ordem em
averbação é o oficial, por `ri_cnib.py`, que não mudou — a regra do CNIB desde
28/08/2026 é «avisar e preparar, ficando pendente o okay». Este módulo só faz
a cópia local deixar de ser um retrato de 2023.


O QUE MANDA NO DESENHO, e cada item foi medido em 18/09/2026, na produção

1. **`ordens_visualizadas=True`, SEMPRE, E AQUI ISSO É QUESTÃO DE SEGURANÇA.**
   Com `False` a leitura **consome a fila** da serventia: 341.697 ordens
   ficaram 341.497 depois de uma página de 200. Um trabalho que roda sozinho,
   todo dia, com `False`, esvaziaria a fila desta casa sem ninguém ver — e
   ninguém saberia o que passou por ali. Este módulo **não tem parâmetro** para
   mudar isso: o que não se pode escolher errado não se oferece.

2. **AS PÁGINAS NÃO SÃO DISJUNTAS** — numa varredura de 3.000 ordens vieram
   2.996 distintas, quatro repetidas entre páginas. Por isso a gravação é
   UPSERT por `protocolo_cnib`, e o índice único dele foi criado antes deste
   módulo existir (`ri_schema`, com a guarda que mede duplicata antes).

3. **O ZERO DA CENTRAL NÃO É PROVA DE AUSÊNCIA.** A mesma resposta vazia veio
   para dias que **tinham** ordens, e horas depois elas apareceram. Por isso a
   janela do dia seguinte **volta atrás** (`MARGEM_EM_DIAS`) em cima do que já
   foi lido: reler é barato, e não ler é perder.

4. **`forma_estranha` NÃO É `vazio`.** Os dois devolvem zero ordens, e
   confundi-los faria o atualizador anotar «nada mudou» em cima de uma
   resposta que ele não entendeu. Aqui a forma estranha vira **recusa
   escrita** (`RECUSADA`), e a marca da janela **não anda**.

5. **CANCELAMENTO NÃO SE DESFAZ POR LINHA QUE NÃO FALA DELE.** A mesma janela
   pode trazer a ordem e o cancelamento dela — e, se a ordem chegar depois, um
   UPSERT ingênuo a reativaria. O `DO UPDATE` daqui usa `COALESCE` no
   cancelamento e só liga `ativa=1` quando **nem o que chegou nem o que já
   estava** tem cancelamento. Foi o primeiro defeito que este módulo teve de
   não ter.

6. **A REDE NÃO ENTRA NA TRANSAÇÃO.** `ler_da_central` não recebe `con` e não
   toca no banco; `gravar` não toca na rede. Uma chamada de até 60 s dentro de
   um `BEGIN IMMEDIATE` seguraria a trava de escrita do balcão inteiro nesse
   tempo. São duas funções por causa disso, e a rota as usa nessa ordem.

7. **A DATA DA CÓPIA NÃO É `MAX(data_pedido)`.** A janela filtra pela data da
   **atividade**: uma janela de junho/2026 devolveu ordem com `datapedido` de
   2012, porque o cancelamento era de junho. Quem perguntar «até quando esta
   cópia responde» tem de olhar a última leitura que deu certo — é para isso
   que `ri_cnib_leituras` existe, e é o que `ultima_leitura` devolve.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import cnib_api as API
from ri_schema import normalizar_busca

# ------------------------------------------------------------------ situações

PEDIDA, OK, VAZIA, RECUSADA, ERRO = "PEDIDA", "OK", "VAZIA", "RECUSADA", "ERRO"

# AS QUE CONTAM COMO «A CENTRAL RESPONDEU E EU ENTENDI». São as duas que movem
# a marca da janela. `RECUSADA` e `ERRO` **não movem**: janela que anda em cima
# de resposta não entendida é buraco silencioso no espelho.
SITUACOES_QUE_ANDAM: frozenset[str] = frozenset({OK, VAZIA})

ORIGEM_DA_CENTRAL = "CNIB"
CHAVE_DO_RETRATO = "cnib_retrato_do_acervo"

# QUANTOS DIAS A JANELA VOLTA ATRÁS em cima do que já foi lido. Sete, e o
# número tem motivo: a resposta vazia não distingue «não há» de «ainda não me
# chegou», e o padrão desta casa é rodar uma vez por dia, quando alguém abre o
# sistema — num fim de semana longo ninguém abre. Sete dias cobrem o feriado
# emendado e ainda sobram folgas.
MARGEM_EM_DIAS = 7

# A JANELA DA PRIMEIRA VEZ, quando não há leitura nenhuma anotada. Não é a
# posta em dia — essa é outra coisa, e tem função própria aqui embaixo.
PRIMEIRA_JANELA_EM_DIAS = 7

# A CHAVE DO CPF DE QUEM CONSULTA. A Central **exige** `cpf_usuario`: é por ele
# que ela registra quem pediu a lista. Não tem palpite: sem isso gravado, o
# atualizador não roda e a tela diz o que falta.
CHAVE_DO_CPF = "cnib_cpf_usuario"

# O INTERRUPTOR DA ROTINA DIÁRIA, na forma do `auto_backup`: ligado de fábrica,
# porque instalação nova nasce funcionando, e desligável por quem manda.
CHAVE_DA_ROTINA = "cnib_atualizacao_automatica"


class CnibAtualizadorError(ValueError):
    """Erro de regra, com frase pronta para o balcão — vira `flash(danger)`."""


# ------------------------------------------------------------------ leitores


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _dia(valor: Any) -> str | None:
    """`'15/09/2026 04:49:06'` -> `'2026-09-15'`. **ISO não é o que vem.**

    O `datapedido` e o `cancelamentodata` vêm `dd/mm/aaaa hh:mm:ss` — está
    medido no cabeçalho do `cnib_api`, e é o campo que mais se erra. Quem
    gravasse o texto como veio deixaria a coluna com duas grafias de data no
    mesmo banco: as 50.054 do E-Ofício estão em ISO.

    Data que não se entende vira `None`, e não um palpite: o espelho prefere o
    vazio à data inventada.
    """
    texto = _texto(valor)
    if not texto:
        return None
    pedaco = texto.split(" ")[0]
    if len(pedaco) == 10 and pedaco[2] == "/" and pedaco[5] == "/":
        d, m, a = pedaco.split("/")
        return f"{a}-{m}-{d}"
    if len(pedaco) == 10 and pedaco[4] == "-" and pedaco[7] == "-":
        return pedaco
    return None


def cpf_de_quem_consulta(con: sqlite3.Connection) -> str:
    """O CPF que vai no pedido, como está gravado nas configurações. Só lê."""
    linha = con.execute("SELECT value FROM settings WHERE key=?",
                        (CHAVE_DO_CPF,)).fetchone()
    return _texto(linha[0]) if linha else ""


def rotina_ligada(con: sqlite3.Connection) -> bool:
    """A rotina diária está ligada? Padrão: sim."""
    linha = con.execute("SELECT value FROM settings WHERE key=?",
                        (CHAVE_DA_ROTINA,)).fetchone()
    return (_texto(linha[0]) if linha else "1") != "0"


def esta_pronto(con: sqlite3.Connection) -> dict:
    """O que ainda falta para o atualizador poder rodar. **A tela mostra isto.**

    Devolve `{pronto, falta}`, e `falta` é a lista das frases do que falta —
    escritas para quem vai resolver, e não para quem escreveu o código.
    """
    falta: list[str] = []
    if not API.tem_credencial():
        falta.append(
            "A credencial do CNIB não está guardada. Ela é um par "
            "(`client_id` e `client_secret`) e se grava em "
            "Administrativo → Configurações, na tabela das Centrais.")
    if not cpf_de_quem_consulta(con):
        falta.append(
            "Falta o CPF de quem consulta. A Central exige esse campo em todo "
            "pedido — é por ele que ela registra quem pediu a lista. Grave em "
            "Administrativo → Configurações.")
    return {"pronto": not falta, "falta": falta}


def retrato_do_acervo(con: sqlite3.Connection) -> str | None:
    """Referencia imutavel: configuracao congelada ou banco original importado.

    A origem das ordens muda para CNIB no UPSERT; por isso o MAX das linhas
    ainda EOFICIO regride durante a recuperacao e nao identifica o acervo.
    """
    linha = con.execute("SELECT value FROM settings WHERE key=?",
                        (CHAVE_DO_RETRATO,)).fetchone()
    if linha and _dia(linha[0]):
        return _dia(linha[0])
    from ajuda_problemas import caminho_do_banco
    principal = caminho_do_banco(con)
    if principal:
        acervo = Path(principal).parent / "acervo_eoficio.sqlite3"
        if acervo.is_file():
            with closing(sqlite3.connect(acervo.as_uri() + "?mode=ro", uri=True)) as fonte:
                original = fonte.execute(
                    "SELECT MAX(DATAPEDIDO) FROM tbCNIB_Registro").fetchone()
            if original and _dia(original[0]):
                return _dia(original[0])
    linha = con.execute(
        "SELECT MAX(data_pedido) FROM ri_cnib_ordens WHERE origem<>?",
        (ORIGEM_DA_CENTRAL,)).fetchone()
    return _dia(linha[0]) if linha else None


def resumo_do_espelho(con: sqlite3.Connection) -> dict:
    """Quantas ordens a cópia local tem, e de onde elas vieram. Só lê.

    **`retrato_do_acervo` OLHA SÓ O QUE VEIO DO E-OFÍCIO, e isso não é
    capricho de consulta.** É ele que diz onde começa o atraso a recuperar, e
    o `MAX(data_pedido)` da tabela inteira **deixa de servir na primeira
    leitura**: basta a Central mandar uma ordem pedida hoje para o máximo
    pular para hoje — e a posta em dia apareceria **concluída** com três anos
    e meio de buraco por baixo. O retrato do acervo, ao contrário, não se
    move: aquelas 50.054 linhas pararam em 19/03/2023 e param ali para
    sempre.
    """
    linha = con.execute(
        """SELECT COUNT(*) total,
                  COALESCE(SUM(ativa=1), 0) ativas,
                  COALESCE(SUM(origem=?), 0) da_central,
                  MAX(data_pedido) ultimo_pedido,
                  MAX(CASE WHEN origem<>? THEN data_pedido END) retrato_do_acervo
             FROM ri_cnib_ordens""",
        (ORIGEM_DA_CENTRAL, ORIGEM_DA_CENTRAL)).fetchone()
    return {"total": linha[0], "ativas": linha[1],
            "da_central": linha[2], "ultimo_pedido": linha[3],
            "retrato_do_acervo": retrato_do_acervo(con)}


def ultima_leitura(con: sqlite3.Connection) -> sqlite3.Row | None:
    """A última leitura **que a Central respondeu e a casa entendeu**.

    É ela que responde «até quando esta cópia vale» — e não o
    `MAX(data_pedido)`, que é a data do PEDIDO judicial e vem de 2012 numa
    ordem que a Central mandou hoje, quando o que se moveu foi o cancelamento.
    """
    marcas = ",".join("?" * len(SITUACOES_QUE_ANDAM))
    return con.execute(
        f"""SELECT * FROM ri_cnib_leituras
             WHERE situacao IN ({marcas}) AND terminada_em IS NOT NULL
               AND parou_no_teto=0
             ORDER BY ate DESC, id DESC LIMIT 1""",
        tuple(sorted(SITUACOES_QUE_ANDAM))).fetchone()


def leituras(con: sqlite3.Connection, limite: int = 30) -> list[sqlite3.Row]:
    """As últimas leituras, **inclusive as que deram errado**.

    As que deram errado ficam na lista de propósito: erro que some da tela é
    erro que ninguém conserta, e aqui ele é a diferença entre «a Central não
    tinha nada» e «eu não consegui falar com ela».
    """
    return con.execute(
        "SELECT * FROM ri_cnib_leituras ORDER BY id DESC LIMIT ?",
        (int(limite),)).fetchall()


def ja_leu_hoje(con: sqlite3.Connection, *, hoje: date) -> bool:
    """Já houve tentativa hoje? **Tentativa, e não sucesso.**

    A rotina diária pergunta isto antes de sair para a rede. Contar só o
    sucesso faria uma Central fora do ar virar uma tentativa por tela aberta —
    dezenas por hora, cada uma esperando o tempo do prazo.
    """
    # O DIA SE COMPARA POR FAIXA, E NÃO POR RECORTE. `substr()` muda de nome
    # fora do SQLite, e o teto deste módulo é zero; o `z` no limite de cima é o
    # mesmo truque do razão dos selos — ele passa do `T`, do espaço e de todo
    # dígito, e a comparação continua sendo de texto.
    dia = hoje.isoformat()
    return con.execute(
        "SELECT 1 FROM ri_cnib_leituras WHERE pedida_em >= ? AND pedida_em < ? "
        "AND ate>=? LIMIT 1", (dia, dia + "z", dia)).fetchone() is not None


# ------------------------------------------------------------------ janelas


def janela_do_dia(con: sqlite3.Connection, *, hoje: date) -> tuple[str, str]:
    """De quando até quando ler hoje. **Sempre sobreposta ao que já foi lido.**

    Volta `MARGEM_EM_DIAS` em cima do fim da última leitura boa — porque o zero
    da Central não é prova de ausência, e porque a rotina só roda quando
    alguém abre o sistema.
    """
    ultima = ultima_leitura(con)
    if ultima is None:
        inicio = hoje - timedelta(days=PRIMEIRA_JANELA_EM_DIAS)
    else:
        try:
            inicio = date.fromisoformat(str(ultima["ate"])[:10]) - timedelta(days=MARGEM_EM_DIAS)
        except (TypeError, ValueError):
            inicio = hoje - timedelta(days=PRIMEIRA_JANELA_EM_DIAS)
    inicio = min(inicio, hoje)
    return inicio.isoformat(), hoje.isoformat()


def _ultimo_dia_do_mes(quando: date) -> date:
    if quando.month == 12:
        return date(quando.year, 12, 31)
    return date(quando.year, quando.month + 1, 1) - timedelta(days=1)


def janelas_da_posta_em_dia(con: sqlite3.Connection, *, hoje: date) -> list[dict]:
    """Os pedaços da posta em dia, **um por mês**, do atraso até hoje.

    POR QUE EM PEDAÇOS, e não numa varredura só: a fila desta serventia tinha
    341.697 ordens em 18/09/2026, e a 500 por página isso é **684 páginas** —
    acima do freio de 200 do `cnib_api` (100.000 ordens), que existe para o
    servidor da serventia não varrer o país num pedido. Mês a mês cada pedaço
    cabe, cada um fica anotado, e quem estiver olhando vê andar.

    POR QUE PELO MÊS, e não por semana ou por trimestre: o mês é o pedaço que
    a tela consegue nomear («março de 2023») e que o oficial reconhece. Se
    algum mês estourar o teto, a leitura dele fica marcada `parou_no_teto` e
    aparece na tela — medir antes de quebrar em semanas seria inventar.

    DE ONDE ELA COMEÇA É O **RETRATO DO ACERVO**, e não o `MAX(data_pedido)`
    da tabela. A diferença aparece **na primeira leitura**: basta a Central
    mandar uma ordem pedida hoje para o máximo geral pular para hoje, e esta
    lista encolheria para um mês só — a posta em dia se daria por concluída
    com o buraco inteiro por baixo, sem ninguém ver. O retrato do acervo não
    se move.

    Devolve a lista inteira, com `feita` em cada um, para a tela mostrar o
    tamanho do que falta em vez de só o próximo passo.
    """
    resumo = resumo_do_espelho(con)
    inicio_texto = _texto(resumo["retrato_do_acervo"])[:10]
    try:
        inicio = date.fromisoformat(inicio_texto)
    except ValueError:
        # Espelho vazio: não há atraso a recuperar, e a rotina do dia basta.
        return []

    # O MÊS INTEIRO DO ATRASO, e não o dia em que ele parou. Reler duas semanas
    # de março de 2023 custa uma página e fecha a fresta de quem tenha entrado
    # no dia 19 depois do retrato.
    passo = date(inicio.year, inicio.month, 1)
    fora: list[dict] = []
    while passo <= hoje:
        fim = min(_ultimo_dia_do_mes(passo), hoje)
        de, ate = passo.isoformat(), fim.isoformat()
        feita = con.execute(
            """SELECT 1 FROM ri_cnib_leituras
                WHERE de<=? AND ate>=? AND situacao IN (?,?)
                  AND parou_no_teto=0 AND terminada_em IS NOT NULL LIMIT 1""",
            (de, ate, OK, VAZIA)).fetchone() is not None
        fora.append({"de": de, "ate": ate, "feita": feita,
                     "titulo": f"{passo.month:02d}/{passo.year}"})
        passo = fim + timedelta(days=1)
    return fora


# ------------------------------------------------------------------- a rede


def ler_da_central(de: str, ate: str, *, cpf_usuario: str,
                   ler: Callable[..., dict] | None = None) -> dict:
    """Pede a janela à Central. **Não recebe `con` e não toca no banco.**

    O `ler` existe para o teste trocar a rede — e é o único jeito honesto de
    testar isto sem inventar resposta: o que ele recebe nos testes é a
    transcrição dos brutos de 18/09/2026, em `tests/brutos_do_cnib.py`.

    **Não há parâmetro para consumir a fila.** Ver o item 1 do cabeçalho.
    """
    if not _texto(cpf_usuario):
        raise CnibAtualizadorError(
            "Falta o CPF de quem consulta o CNIB. Grave em Administrativo → "
            "Configurações antes de buscar ordens na Central.")
    chamar = ler or API.ordens_na_janela
    return chamar(de, ate, cpf_usuario=_texto(cpf_usuario), visualizadas=True)


# ---------------------------------------------------------------- a gravação


def _gravar_ordem(con: sqlite3.Connection, ordem: dict) -> str:
    """Uma ordem no espelho. Devolve `NOVA`, `MUDOU` ou `IGUAL`.

    **O CANCELAMENTO NÃO SE DESFAZ POR LINHA QUE NÃO FALA DELE.** A mesma
    janela traz a ordem e o cancelamento dela; se a ordem chegar depois, um
    `DO UPDATE` ingênuo gravaria `ativa=1` por cima. Daí o `COALESCE` nos dois
    campos do cancelamento e o `CASE` que só reativa quando nem o que chegou
    nem o que já estava tem cancelamento anotado.
    """
    protocolo = API.protocolo_da_ordem(ordem)
    if not protocolo:
        raise CnibAtualizadorError(
            "A Central mandou uma ordem sem protocolo. O protocolo é a "
            "identidade da ordem — sem ele não há como casar o cancelamento "
            "depois, e a linha não entra.")

    cancelamento = API.protocolo_do_cancelamento(ordem) or None
    antes = con.execute(
        "SELECT id, ativa FROM ri_cnib_ordens WHERE protocolo_cnib=?",
        (protocolo,)).fetchone()

    con.execute(
        """INSERT INTO ri_cnib_ordens
              (protocolo_cnib, data_pedido, processo, instituicao, forum_vara,
               solicitante, cancelamento_protocolo, cancelamento_data, ativa,
               origem_chave, origem)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(protocolo_cnib) DO UPDATE SET
               data_pedido=excluded.data_pedido,
               processo=excluded.processo,
               instituicao=excluded.instituicao,
               forum_vara=excluded.forum_vara,
               solicitante=excluded.solicitante,
               cancelamento_protocolo=COALESCE(excluded.cancelamento_protocolo,
                                               ri_cnib_ordens.cancelamento_protocolo),
               cancelamento_data=COALESCE(excluded.cancelamento_data,
                                          ri_cnib_ordens.cancelamento_data),
               ativa=CASE WHEN excluded.cancelamento_protocolo IS NOT NULL
                            OR ri_cnib_ordens.cancelamento_protocolo IS NOT NULL
                          THEN 0 ELSE 1 END,
               origem=excluded.origem""",
        (protocolo, _dia(ordem.get("datapedido")),
         _texto(ordem.get("numeroprocesso")) or None,
         _texto(ordem.get("nomeinstituicao")) or None,
         _texto(ordem.get("forumvara")) or None,
         _texto(ordem.get("usuario")) or None,
         cancelamento, _dia(ordem.get("cancelamentodata")),
         0 if cancelamento else 1, protocolo, ORIGEM_DA_CENTRAL))

    linha = con.execute(
        "SELECT id, ativa FROM ri_cnib_ordens WHERE protocolo_cnib=?",
        (protocolo,)).fetchone()
    ordem_id = int(linha["id"])

    # AS PARTES DA CENTRAL SUBSTITUEM AS DO ESPELHO, e a razão é medida: o
    # espelho do E-Ofício guarda **uma** parte por ordem, e 40% das ordens têm
    # mais de uma. Somar em vez de substituir faria a mesma pessoa entrar de
    # novo a cada leitura — a fila repete linha entre páginas.
    partes = ordem.get("partes")
    if isinstance(partes, list) and partes:
        con.execute("DELETE FROM ri_cnib_pessoas WHERE ordem_id=?", (ordem_id,))
        for p in partes:
            if not isinstance(p, dict):
                continue
            con.execute(
                """INSERT INTO ri_cnib_pessoas (ordem_id, nome, documento, origem_chave, nome_norm)
                   VALUES (?,?,?,?,?)""",
                (ordem_id, _texto(p.get("nomerazao")) or None,
                 _texto(p.get("cpfcnpj")) or None, protocolo,
                 normalizar_busca(p.get("nomerazao")) or None))

    if antes is None:
        return "NOVA"
    if int(antes["ativa"]) == 1 and int(linha["ativa"]) == 0:
        return "CANCELOU"
    return "MUDOU"


def gravar(con: sqlite3.Connection, *, de: str, ate: str, leitura: dict,
           agora: str, usuario: int | None = None,
           automatica: bool = False) -> dict:
    """Escreve no espelho o que a Central respondeu, e anota a leitura.

    **Recebe `con` e não vai à rede** — a chamada já foi feita por
    `ler_da_central`, fora da transação. Quem chama abre um `db.transaction()`
    só aqui.

    Recusa a resposta que não entendeu: `forma_estranha` vira `RECUSADA`, sem
    gravar ordem nenhuma e sem mover a marca da janela. Anotar «nada mudou» em
    cima de uma resposta ilegível seria dizer que o espelho está em dia quando
    ninguém sabe se está.
    """
    referencia = retrato_do_acervo(con)
    if referencia:
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)",
                    (CHAVE_DO_RETRATO, referencia))
    if leitura.get("forma_estranha"):
        anotar(con, de=de, ate=ate, situacao=RECUSADA, agora=agora,
               usuario=usuario, automatica=automatica,
               mensagem=("A Central respondeu numa forma que este sistema não "
                         "conhece. Nada foi gravado, e a janela não andou. "
                         + _texto(leitura.get("mensagem"))).strip(),
               paginas=int(leitura.get("paginas") or 0))
        return {"situacao": RECUSADA, "lidas": 0, "novas": 0,
                "atualizadas": 0, "canceladas": 0}

    novas = atualizadas = canceladas = 0
    for ordem in leitura.get("ordens") or []:
        resultado = _gravar_ordem(con, ordem)
        if resultado == "NOVA":
            novas += 1
        elif resultado == "CANCELOU":
            canceladas += 1
        else:
            atualizadas += 1

    lidas = int(leitura.get("lidas") or 0)
    situacao = VAZIA if (leitura.get("vazio") and not lidas) else OK
    anotar(con, de=de, ate=ate, situacao=situacao, agora=agora,
           usuario=usuario, automatica=automatica,
           mensagem=_texto(leitura.get("mensagem")),
           lidas=lidas, novas=novas, atualizadas=atualizadas,
           canceladas=canceladas,
           paginas=int(leitura.get("paginas") or 0),
           parou_no_teto=bool(leitura.get("parou_no_teto")))
    return {"situacao": situacao, "lidas": lidas, "novas": novas,
            "atualizadas": atualizadas, "canceladas": canceladas,
            "parou_no_teto": bool(leitura.get("parou_no_teto"))}


def anotar(con: sqlite3.Connection, *, de: str, ate: str, situacao: str,
           agora: str, usuario: int | None = None, automatica: bool = False,
           mensagem: str = "", lidas: int = 0, novas: int = 0,
           atualizadas: int = 0, canceladas: int = 0, paginas: int = 0,
           parou_no_teto: bool = False) -> int:
    """Uma linha em `ri_cnib_leituras`. **Também para o que deu errado.**

    A rota chama isto direto quando a rede falhou: a tentativa que não chegou
    à Central precisa ficar escrita, senão amanhã ninguém sabe se a cópia está
    velha porque não há ordem nova ou porque faz uma semana que não se fala com
    a Central.
    """
    if situacao not in {PEDIDA, OK, VAZIA, RECUSADA, ERRO}:
        raise CnibAtualizadorError(f"Situação de leitura desconhecida: {situacao}")
    cursor = con.execute(
        """INSERT INTO ri_cnib_leituras
              (de, ate, pedida_em, terminada_em, situacao, lidas, novas,
               atualizadas, canceladas, paginas, parou_no_teto, mensagem,
               automatica, pedida_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (de, ate, agora, agora, situacao, lidas, novas, atualizadas,
         canceladas, paginas, 1 if parou_no_teto else 0, mensagem or None,
         1 if automatica else 0, usuario))
    return int(cursor.lastrowid)

"""O razão dos selos, pesquisável — relato #33 do oficial.

    «preciso que seja possivel pesquisar os selo emitidos por data,
     especialidade, usuario.»                       — o oficial

OS TRÊS CAMPOS EXISTEM, E UM DELES TEM OUTRO NOME
    Medido em `sd_selos`, **26.278 linhas** na produção, em 15/09/2026:

    | o que ele pediu | onde está |
    |---|---|
    | data | `obtido_em` |
    | especialidade | `atribuicao` **e** `caminho`, e o **prefixo do número** |
    | usuário | **`obtido_por`** — e não `usuario`, que é o nome que procurei
                 primeiro e não achei |

    | atribuição | selos |
    |---|---|
    | NOTAS | **21.191** |
    | IMOVEL | 2.108 |
    | CIVIL | 1.413 |
    | PROTESTO | 1.308 |
    | RTDPJ | 165 |
    | RCPN | 75 |
    | (vazia) · RCPJ · RI · RCPJ_RTD | **7 · 5 · 4 · 2** |

    **AS QUATRO ÚLTIMAS SÃO GRAFIA ANTIGA DO ACERVO, E FICAM À VISTA.** São
    **18 selos em 26.278**, e `RCPJ_RTD` e `RTDPJ` são o mesmo cartório escrito
    de dois jeitos — mas juntá-los seria adivinhar, e some-los faria a soma não
    fechar com as linhas. Elas aparecem com o próprio código na caixa e no
    agrupamento, e o número está aqui para quem conferir a lista não achar que
    a conta quebrou. **Quando o próximo for lavrado, ele grava a grafia
    canônica**: este sistema escreve a atribuição em maiúscula, e foi assim que
    a segunda grafia da mesma atribuição deixou de nascer.

ESTA É A ÚNICA TELA DO RAZÃO DESDE 15/09/2026 — E ELA ABSORVEU A OUTRA
    Havia **duas** telas chamadas «Selos emitidos» no menu, com o mesmo rótulo
    e réguas diferentes para a mesma palavra. Medido: a antiga
    (`/relatorios/selos`, `selo_consulta.py`) e esta discordavam em **7.762
    selos** sobre o que é «não usado», perdiam o último dia de todo período
    (comparavam a data sem fechar o dia) e respondiam diferente à mesma busca
    por usuário. **Duas réguas para a mesma pergunta**, e quem lesse uma não
    saberia o que a outra diria.

    A antiga não foi embora pela metade: o que ela tinha de melhor passou para
    cá — o **tipo do ato** pelo prefixo do número, que é o nível mais fino da
    especialidade e o que o selo impresso carrega (filtro, nome legível e
    agrupamento), os agrupamentos por **dia** e por **mês**, e a busca por
    usuário **por pedaço e sem caixa**. `/relatorios/selos` continua
    respondendo: redireciona para cá, para quem tem o endereço nos favoritos.

ESTE MÓDULO NÃO É A TELA DE SELOS DO RI, E A DIFERENÇA IMPORTA
    `ri_selos` reúne o selo **de dentro dos atos do Registro de Imóveis** —
    lê `ri_atos`, `ri_certidoes` e `ri_protocolos`, que é o livro de selos
    daquela atribuição.

    **Aqui é o RAZÃO**: a tabela que responde «este selo já foi usado?», com
    as seis atribuições juntas. São perguntas diferentes, e por isso são duas
    telas — mas cada uma **diz o que é e aponta para a outra**, porque «duas
    portas para a mesma sala» é o relato #12, e a saída dele não foi apagar
    uma: foi cada uma dizer a que veio.

«USADO» É A UNIÃO DE DUAS MARCAS, E UMA DELAS ESTAVA SENDO LIDA AO CONTRÁRIO
    `sd_selos` guarda se o selo foi usado em **dois** lugares, e eles não são a
    mesma coisa:

    | marca | quem a escreve | o que ela quer dizer |
    |---|---|---|
    | `usado_em` | a carga do acervo (de `bitUtilizado`) e o `ato_selado` | o selo saiu do aparelho para um ato |
    | `ato_id` | só este sistema, ao amarrar o selo ao ato | este sistema sabe **qual** ato |

    Medido fora os cancelados, em 15/09/2026: **17.132** têm as duas marcas,
    **7.762** têm só `usado_em` — são os do acervo, de 2020 a 2026, quase
    todos de NOTAS —, **1.300** não têm nenhuma, e **zero** têm só `ato_id`.

    **O ZERO DA ÚLTIMA LINHA É O QUE EXPLICA O DEFEITO**: toda vez que este
    sistema amarra um selo a um ato ele grava as duas marcas, de modo que
    `usado_em` sozinho já responde «alguém usou?». Ler `ato_id` era ler a
    marca mais fraca das duas — a que só existe para os 13 mil selos que este
    sistema mesmo emitiu.

    **O `1.300` anda todo dia**, porque selo se compra todo dia e só deixa de
    ser órfão quando o ato é lavrado; os outros três são o tamanho do acervo.

    **A primeira versão desta tela tratou `ato_id IS NULL` como «não usado», e
    publicou 9.062 onde são 1.300** — os mesmos **7.762** selos do acervo, que
    a casa comprou e usou, apareciam como comprados e jogados fora, e o número
    chegou a ser escrito na ajuda do sistema. `ato_id` vazio quer dizer «este
    sistema não sabe a qual ato»; **não** quer dizer «ninguém usou».

    **Orfão é o selo sem NENHUMA das duas marcas** — e é a régua que vale aqui.

    **E `ato_id IS NULL` CONTINUA CERTO em `procurar_externos_rtdpj`**, duas
    funções abaixo: ali a pergunta é outra — «este selo precisa de etiqueta
    impressa por fora?» —, e o que se procura é o que **este sistema** não
    lavrou. A mesma coluna responde a duas perguntas diferentes; unificá-las por
    parecença faria a etiqueta do RTDPJ sair para selo já amarrado a um ato.

A ARMADILHA ESTÁ NA DATA, E ELA É DE DADO E NÃO DE CÓDIGO
    A coluna guarda **dois formatos**, medidos em 15/09/2026:
    `2020-03-19 14:21:03` em **26.130** linhas — o que a carga do acervo
    trouxe — e `2026-09-01T14:17:06` em **148**, que é o `isoformat()` deste
    sistema.

    **`BETWEEN inicio AND fim` PERDERIA O ÚLTIMO DIA INTEIRO**, nos dois
    formatos: `'2026-09-01 14:21:03'` é maior que `'2026-09-01'`, e quem
    pedisse «até 1º de setembro» não veria nada daquele dia. É a armadilha da
    afinidade de coluna outra vez, agora entre dois textos. Medido: o dia
    01/09/2026 devolve **0** sem o fecho e **1** com ele; o dia 27/08/2026,
    **0** e **4**.

    **O limite superior vai com um `z` no fim.** `'2026-09-01z'` é maior que
    qualquer hora dos dois formatos — `z` (122) passa do `T` (84), do espaço
    (32) e de todo dígito — e a comparação continua sendo de TEXTO, sem função
    de data no SQL. **Módulo novo entra com zero acoplamento ao SQLite**, e
    `substr(obtido_em,1,10)` custaria dois.

AS LISTAS DAS CAIXAS SÃO MEDIDAS, E NUNCA ESCRITAS
    Atribuição, caminho e usuário saem de `SELECT DISTINCT`; os tipos do ato
    saem do próprio número, cortados em Python. Escritas à mão, envelheceriam na
    tarde em que fossem escritas, e o operador procuraria por um valor que a
    tela não oferece mais.

    As tabelas `TIPOS` e `ATRIBUICOES` **não são lista fechada**: elas dão nome
    ao que a tela mostra. Um prefixo ou uma atribuição que apareça e não esteja
    ali sai com o próprio código, e não sumido.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class SeloEmitidoError(ValueError):
    """Erro de regra da pesquisa de selos — mensagem pronta para o balcão."""


POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 500
LIMITE_ETIQUETAS_RTDPJ = 60

# **O `z` QUE FECHA O DIA.** Ver a docstring: a coluna tem dois formatos de
# data, e sem isto o ultimo dia do periodo sai vazio.
FECHA_O_DIA = "z"

# OS TIPOS DE ATO, pelo prefixo do número do selo. Medidos na produção e
# postos em ordem de quantidade: são estes que a casa realmente usa.
#
#   `RECFIR` sozinho são 16.386 dos 26.278 selos — é a metade do movimento da
#   casa, e é o que faz a pergunta do oficial valer a pena: «quantos selos de
#   notas» quase não separa nada, «quantos de reconhecimento de firma» responde.
#
#   **NÃO É LISTA FECHADA**: a tela aceita qualquer prefixo que exista no razão,
#   e esta tabela só dá nome ao que ele mostra. Prefixo sem entrada aqui sai com
#   o próprio código, e não sumido.
TIPOS: dict[str, str] = {
    "RECFIR": "Reconhecimento de firma",
    "AUTENT": "Autenticação de cópia",
    "CERTID": "Certidão",
    "ARQUIV": "Arquivamento",
    "PRENOT": "Prenotação",
    "CERINT": "Certidão de inteiro teor",
    "PROTIT": "Protesto de título",
    "CERELE": "Certidão eletrônica",
    "CERIMV": "Certidão de imóvel",
    "DILIGE": "Diligência",
}

ATRIBUICOES: dict[str, str] = {
    "NOTAS": "Tabelionato de Notas",
    "IMOVEL": "Registro de Imóveis",
    "CIVIL": "Registro Civil",
    "PROTESTO": "Protesto",
    "RTDPJ": "RTD e RCPJ",
    "RCPN": "Registro Civil",
    # **AS TRÊS ABAIXO SÃO GRAFIA ANTIGA DO ACERVO** — 11 selos em 26.278,
    # medidos em 15/09/2026. `RCPJ_RTD` e `RTDPJ` são o mesmo cartório escrito
    # de dois jeitos. Elas ficam aqui para a caixa e o agrupamento **dizerem o
    # que são** em vez de mostrarem código cru; e ficam **separadas**, porque
    # somá-las seria decidir que são iguais, e separá-las é só ler o que está
    # gravado. A grafia canônica é de maiúscula, e é o que este sistema grava.
    "RCPJ": "RTD e RCPJ (grafia antiga do acervo)",
    "RCPJ_RTD": "RTD e RCPJ (grafia antiga do acervo)",
    "RI": "Registro de Imóveis (grafia antiga do acervo)",
}

SITUACOES = {
    "": "todas",
    "USADO": "usado num ato",
    "ORFAO": "obtido e não usado",
    "CANCELADO": "cancelado",
}

# OS AGRUPAMENTOS DO RELATÓRIO, e o rótulo de cada um. São os cinco que
# respondem «controlar os selos emitidos»: quem, de que tipo, de que
# especialidade, em que mês e em que dia.
AGRUPAMENTOS: dict[str, str] = {
    "usuario": "Por usuário",
    "tipo": "Por tipo do ato",
    "atribuicao": "Por especialidade",
    "mes": "Por mês",
    "dia": "Por dia",
}


def _texto(v: Any) -> str:
    return str(v or "").strip()


# ================================================= as duas marcas, num lugar só
#
# **A RÉGUA MORA AQUI, E NÃO DENTRO DE CADA CONSULTA.** Ela decide o número que
# a tela publica — «9.062 não usados» contra «1.300» —, e escrita duas vezes
# divergiria no primeiro conserto. É a lição da `normalizar_nome`, que este
# projeto já pagou quatro vezes: **onde a igualdade importa, ela se constrói**.
#
# Ver a docstring do módulo para as medições e para o defeito que isto conserta.
SEM_CANCELAR = "TRIM(COALESCE(cancelado_em,'')) = ''"
CANCELADO = f"NOT ({SEM_CANCELAR})"
TEM_MARCA_DE_USO = "TRIM(COALESCE(usado_em,'')) <> '' OR ato_id IS NOT NULL"
SEM_MARCA_DE_USO = ("TRIM(COALESCE(usado_em,'')) = '' AND ato_id IS NULL")
USADO = f"{SEM_CANCELAR} AND ({TEM_MARCA_DE_USO})"
ORFAO = f"{SEM_CANCELAR} AND {SEM_MARCA_DE_USO}"


def situacao_do_selo(linha: dict) -> str:
    """CANCELADO, USADO ou ORFAO — **a mesma régua do filtro**, em Python.

    A lista precisa dizer, linha a linha, o que o filtro diz no conjunto. Duas
    definições da mesma palavra fariam o filtro devolver 1.300 linhas e a tela
    escrever «usado» em metade delas.
    """
    if _texto(linha.get("cancelado_em")):
        return "CANCELADO"
    if _texto(linha.get("usado_em")) or linha.get("ato_id") is not None:
        return "USADO"
    return "ORFAO"


def nome_do_tipo(numero: Any) -> str:
    """O tipo do ato, pelo prefixo do número do selo. Só calcula.

    **O prefixo não repete o `caminho`**: o `caminho` é o pedido que a casa fez
    ao aparelho, e o prefixo é o selo que saiu. `RECFIR` são 16.386 e
    `/selo/notas/reconhecimento-firma`, 13.805 — os dois medem coisas diferentes,
    e é por isso que os dois ficam.
    """
    p = _texto(numero)[:6].upper()
    return TIPOS.get(p, p or "—")


def nome_da_atribuicao(atribuicao: Any) -> str:
    """O nome por extenso da atribuição; sem entrada na tabela, o próprio código."""
    a = _texto(atribuicao).upper()
    return ATRIBUICOES.get(a, a) if a else "—"


def opcoes(con: sqlite3.Connection) -> dict:
    """O que existe no razão, para as caixas da tela. **SÓ LÊ.**

    **Medido, e nunca escrito à mão** — a lição do menu e da lista das cargas:
    lista escrita noutro arquivo envelhece na tarde em que se escreve, e aqui
    ela faria o operador procurar por um valor que a tela deixou de oferecer.
    """
    def distintos(coluna: str) -> list[str]:
        return [r[0] for r in con.execute(
            f"SELECT DISTINCT {coluna} FROM sd_selos "
            f"WHERE {coluna} IS NOT NULL AND TRIM({coluna}) <> '' "
            f"ORDER BY {coluna}").fetchall()]

    # OS TIPOS SÃO CORTADOS EM PYTHON, e não com `SUBSTR` no SQL: o corte é a
    # única coisa que a consulta faria com a coluna, e recortar depois de ler
    # custa uma coluna por linha. **Módulo novo entra com zero acoplamento.**
    quantos: dict[str, int] = {}
    for (numero,) in con.execute("SELECT numero FROM sd_selos"):
        p = _texto(numero)[:6].upper()
        if p:
            quantos[p] = quantos.get(p, 0) + 1
    tipos = sorted(
        ({"codigo": p, "rotulo": TIPOS.get(p, p), "quantos": n}
         for p, n in quantos.items()),
        key=lambda x: (-x["quantos"], x["codigo"]))

    return {
        "atribuicoes": distintos("atribuicao"),
        "caminhos": distintos("caminho"),
        "usuarios": distintos("obtido_por"),
        "tipos": tipos,
        "situacoes": SITUACOES,
        "agrupamentos": AGRUPAMENTOS,
    }


def _onde(*, inicio: Any = None, fim: Any = None, atribuicao: Any = None,
          caminho: Any = None, quem: Any = None, tipo: Any = None,
          numero: Any = None, situacao: Any = None) -> tuple[str, list]:
    """Monta o filtro. Devolve (SQL, parâmetros) — sem função de data nenhuma.

    **A LISTA E O RESUMO USAM ESTE MESMO FILTRO.** Se divergissem, o total diria
    uma coisa e as linhas mostrariam outra, e quem lê confia no número errado.
    """
    onde, params = ["1=1"], []
    if _texto(inicio):
        onde.append("obtido_em >= ?")
        params.append(_texto(inicio))
    if _texto(fim):
        # **O DIA INTEIRO, e não até a meia-noite dele.** Ver FECHA_O_DIA.
        onde.append("obtido_em <= ?")
        params.append(_texto(fim) + FECHA_O_DIA)
    if _texto(atribuicao):
        onde.append("UPPER(COALESCE(atribuicao,'')) = ?")
        params.append(_texto(atribuicao).upper())
    if _texto(caminho):
        onde.append("caminho = ?")
        params.append(_texto(caminho))
    if _texto(quem):
        # **POR PEDAÇO E SEM CAIXA, E ISSO FOI MEDIDO EM 15/09/2026.** O acervo
        # gravou o primeiro nome em caixa alta (`BEATRIZ`, `GISELE`) e este
        # sistema grava o nome completo (`Debora Exemplo Reis`): busca exata
        # acharia metade e calaria a outra. Pior que a caixa é a **mesma pessoa
        # escrita de quatro jeitos** — medido no razão:
        #
        #   | o que está gravado | selos |
        #   |---|---|
        #   | `BEATRIZ` · `BEATRIZ.C` · `beatriz` | 8.917 · 39 · 1 |
        #   | `DEBORA` · `Debora Exemplo Reis` · `Debora` | 83 · 54 · 1 |
        #   | `ELISA` · `Elisa Exemplo Lima` | 1.016 · 48 |
        #   | `CARLA` · `Carla Exemplo Lima` · `Carla` | 4.630 · 21 · 1 |
        #   | `Mario Exemplo dos Santos` · `Mario Santos` | 9 · 8 |
        #
        # São **19 valores distintos** para cerca de **treze pessoas** — o
        # agrupamento por usuário conta mais gente do que existe, e é honesto
        # que conte: juntar `Debora` com `Debora Exemplo Reis` seria decidir
        # quem é quem por semelhança de nome, que é o defeito deste projeto
        # pela quarta vez. **Quem busca acha os quatro pedaços juntos**, porque
        # a busca é por pedaço. (`Codex`, com 4, não é pessoa: é o agente.)
        #
        # **O `UPPER` DO SQLITE É ASCII**, e isto fica declarado: um nome com
        # acento precisa ser digitado com o acento. Hoje não há nenhum nos
        # 26.278 selos — os 19 valores distintos de `obtido_por` são todos
        # sem acento —, e resolver isso pediria uma coluna normalizada que só
        # esta tela usaria.
        onde.append("UPPER(COALESCE(obtido_por,'')) LIKE ?")
        params.append(f"%{_texto(quem).upper()}%")
    if _texto(tipo):
        # O TIPO É O PREFIXO DO NÚMERO, e aqui ele se filtra **sem recortar no
        # SQL**: `LIKE 'RECFIR%'` acha o que começa com aquilo, que é a mesma
        # coisa que `SUBSTR(numero,1,6) = 'RECFIR'` — medido, os 26.278 números
        # têm seis caracteres ou mais, então a fronteira do prefixo é exata.
        p = _texto(tipo).upper()
        if not p.isalnum():
            raise SeloEmitidoError(
                f"Tipo de ato inválido: «{tipo}». São as letras e os números do "
                "começo do selo, como «RECFIR».")
        onde.append("UPPER(COALESCE(numero,'')) LIKE ?")
        params.append(f"{p}%")
    if _texto(numero):
        onde.append("UPPER(COALESCE(numero,'')) LIKE ?")
        params.append(f"%{_texto(numero).upper()}%")

    situacao = _texto(situacao).upper()
    if situacao == "CANCELADO":
        onde.append(CANCELADO)
    elif situacao == "USADO":
        # **AS DUAS MARCAS, e não só `ato_id`.** Ver a docstring: ler só a
        # segunda publicava 9.062 não usados onde são 1.300.
        onde.append(USADO)
    elif situacao == "ORFAO":
        onde.append(ORFAO)
    elif situacao and situacao not in SITUACOES:
        raise SeloEmitidoError(
            f"Situação desconhecida: «{situacao}». "
            f"As que existem são: {', '.join(k for k in SITUACOES if k)}.")
    return " AND ".join(onde), params


def resumo(con: sqlite3.Connection, **filtros) -> dict:
    """Os números do que o filtro alcança. **SÓ LÊ.**

    **Conta o que o filtro ALCANÇA, e não o razão inteiro** — número que não
    acompanha o filtro é o carimbo que mente: quem pede «setembro, da Beatriz»
    e lê «26.278 selos» conclui a coisa errada sobre o próprio filtro.

    **E «órfão» aqui é o que o filtro chama de órfão**, pela mesma constante —
    a primeira versão media `ato_id IS NULL` e publicava **9.062** selos
    comprados e não usados onde são **1.300**. Ver a docstring do módulo.

    **Os três números fecham com o total por construção**: cancelado e órfão se
    contam, e «usado» é o resto. Contar os três e torcer para que a soma dê o
    total é como uma linha fica de fora sem ninguém ver.

    **E os grupos NÃO moram aqui** — eles são `por_grupo`, uma função só. Antes
    havia dois jeitos de contar «por usuário»: um neste resumo e outro no
    agrupamento da tela, e era assim que os dois podiam discordar sem ninguém
    ver. É a `normalizar_nome` de novo: onde a igualdade importa, ela se
    constrói.
    """
    onde, params = _onde(**filtros)
    linha = con.execute(
        f"""SELECT COUNT(*) AS total,
                   SUM(CASE WHEN {CANCELADO} THEN 1 ELSE 0 END) AS cancelados,
                   SUM(CASE WHEN {ORFAO} THEN 1 ELSE 0 END) AS orfaos,
                   MIN(obtido_em) AS primeiro, MAX(obtido_em) AS ultimo
              FROM sd_selos WHERE {onde}""", params).fetchone()
    d = dict(linha)
    d["cancelados"] = int(d["cancelados"] or 0)
    d["orfaos"] = int(d["orfaos"] or 0)
    d["usados"] = int(d["total"] or 0) - d["cancelados"] - d["orfaos"]
    return d


def procurar(con: sqlite3.Connection, *, pagina: int = 1,
             por_pagina: int = POR_PAGINA_PADRAO, **filtros) -> dict:
    """A lista, paginada. **SÓ LÊ.**

    **A paginação tem teto** porque o razão tem 26.278 linhas: uma tela sem
    limite pediria o razão inteiro ao navegador do balcão.

    **Cada linha leva a situação, o tipo do ato e a atribuição por extenso** —
    não para enfeitar: a lista precisa dizer o que o filtro diz. Com o código
    cru, quem filtrasse «usado» veria linhas e não saberia por que aquelas, e
    «RECFIR» não responde nada a quem está no balcão.
    """
    por_pagina = max(1, min(int(por_pagina or POR_PAGINA_PADRAO),
                            POR_PAGINA_MAXIMO))
    pagina = max(1, int(pagina or 1))
    onde, params = _onde(**filtros)
    total = con.execute(
        f"SELECT COUNT(*) FROM sd_selos WHERE {onde}", params).fetchone()[0]
    linhas = [dict(r) for r in con.execute(
        f"""SELECT id, numero, texto, caminho, atribuicao, tabela, ato_id,
                   referencia, obtido_em, obtido_por, usado_em, cancelado_em,
                   cancelado_por, motivo_cancelamento, ambiente
              FROM sd_selos WHERE {onde}
             ORDER BY obtido_em DESC, id DESC
             LIMIT ? OFFSET ?""",
        params + [por_pagina, (pagina - 1) * por_pagina]).fetchall()]
    for x in linhas:
        # **A MESMA RÉGUA DO FILTRO**, pela função que mora ao lado dele. Era
        # `"USADO" if x["ato_id"] else "ORFAO"`, e é esse `if` que fazia a tela
        # dizer «não usado» sobre 7.762 selos que a casa usou.
        x["situacao"] = situacao_do_selo(x)
        x["tipo_do_ato"] = nome_do_tipo(x["numero"])
        x["atribuicao_legivel"] = nome_da_atribuicao(x["atribuicao"])
    return {
        "linhas": linhas,
        "total": int(total),
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, (int(total) + por_pagina - 1) // por_pagina),
    }


# ============================================ o resumo por grupo, em cinco


def _chave_do_grupo(campo: str, linha: dict) -> str:
    """A chave de um grupo, já com o nome legível. Só calcula.

    **A CHAVE SAI COM O NOME, e não com o código.** Era `RECFIR` no relatório
    antigo, e quem o abrisse não sabia o que estava lendo — «quantos de
    reconhecimento de firma» é a pergunta, e ela se responde com o nome.
    """
    if campo == "usuario":
        return _texto(linha.get("obtido_por")) or "(sem usuário)"
    if campo == "tipo":
        p = _texto(linha.get("numero"))[:6].upper()
        return f"{p} — {TIPOS.get(p, p)}" if p else "(sem número)"
    if campo == "atribuicao":
        a = _texto(linha.get("atribuicao")).upper()
        if not a:
            return "(sem atribuição)"
        return f"{a} — {ATRIBUICOES[a]}" if a in ATRIBUICOES else a
    if campo == "dia":
        return _texto(linha.get("obtido_em"))[:10] or "(sem data)"
    if campo == "mes":
        return _texto(linha.get("obtido_em"))[:7] or "(sem data)"
    raise SeloEmitidoError(
        f"Não sei agrupar por «{campo}». Sei por: "
        + ", ".join(AGRUPAMENTOS) + ".")


# **O CORTE DA DATA E DO PREFIXO É FEITO EM PYTHON, DEPOIS DE LER.** No SQL seria
# `SUBSTR`, e este módulo entrou com **zero** acoplamento ao SQLite — o teto de
# `tests/test_portabilidade.py` só admite crescer onde já havia, e no SQLite
# `substr` muda de nome fora daqui.
#
#   **A CONTA QUE ISSO CUSTA FOI MEDIDA, E NÃO SUPOSTA** — 15/09/2026, contra a
#   produção (26.278 selos, `tmp/o_33_o_por_grupo_responde.py`):
#
#   | | `por_grupo` | o mesmo `GROUP BY` no SQL |
#   |---|---|---|
#   | tipo | 53,8 ms | 11,5 ms |
#   | mês | 46,2 ms | 23,9 ms |
#   | usuário | 49,3 ms | 24,0 ms |
#
#   Duas a quatro vezes mais lento, e **cinquenta milésimos** em número
#   absoluto. O comentário do teto, que autorizava os três recortes do módulo
#   antigo, dizia que trazer as 26 mil linhas «travaria» a tela; medido, ela
#   responde em 0,05 s, e a diferença não se paga com um `substr` que troca de
#   nome fora do SQLite. **A pergunta era «trava ou responde?», e ela se
#   responde com o relógio.**
_COLUNAS_DO_GRUPO: dict[str, tuple[str, ...]] = {
    "usuario": ("obtido_por",),
    "tipo": ("numero",),
    "atribuicao": ("atribuicao",),
    "dia": ("obtido_em",),
    "mes": ("obtido_em",),
}


def por_grupo(con: sqlite3.Connection, campo: str, **filtros: Any) -> list[dict]:
    """Quantos selos por usuário, tipo, especialidade, mês ou dia. **SÓ LÊ.**

    **É O QUE RESPONDE A PERGUNTA DO OFICIAL.** «Controlar os selos emitidos»
    não se responde com uma lista de 26 mil linhas: responde-se com quantos cada
    um selou, de que tipo, em que período.

    **O GRUPO ACOMPANHA O FILTRO**, porque usa o mesmo `_onde`: pedir «setembro,
    da Gisele» e ver o mês inteiro embaixo seria o carimbo que mente.

    **`dia` e `mes` vêm do mais recente para o mais antigo**, e os outros do
    maior para o menor: quem olha um relatório de produção quer o dia de hoje em
    cima, e quem olha «por usuário» quer saber quem selou mais.
    """
    if campo not in _COLUNAS_DO_GRUPO:
        raise SeloEmitidoError(
            f"Não sei agrupar por «{campo}». Sei por: "
            + ", ".join(AGRUPAMENTOS) + ".")
    onde, params = _onde(**filtros)
    coluna = _COLUNAS_DO_GRUPO[campo][0]
    contas: dict[str, list[int]] = {}
    for linha in con.execute(
            f"SELECT {coluna}, CASE WHEN {CANCELADO} THEN 1 ELSE 0 END "
            f"FROM sd_selos WHERE {onde}", params):
        chave = _chave_do_grupo(campo, {coluna: linha[0]})
        acumulado = contas.setdefault(chave, [0, 0])
        acumulado[0] += 1
        acumulado[1] += int(linha[1] or 0)
    grupos = [{"chave": c, "quantos": v[0], "cancelados": v[1]}
              for c, v in contas.items()]
    if campo in ("dia", "mes"):
        grupos.sort(key=lambda g: g["chave"], reverse=True)
    else:
        grupos.sort(key=lambda g: (-g["quantos"], g["chave"]))
    return grupos


# ================================================= etiquetas de selo externo


def numeros_informados(valores: Any) -> list[str]:
    """Códigos de selo, sem repetição e na ordem informada. Só calcula."""
    import re

    if isinstance(valores, (list, tuple)):
        bruto = "\n".join(str(v or "") for v in valores)
    else:
        bruto = str(valores or "")
    numeros = []
    for numero in re.findall(r"[A-Za-z0-9]+", bruto.upper()):
        if numero not in numeros:
            numeros.append(numero)
    if len(numeros) > LIMITE_ETIQUETAS_RTDPJ:
        raise SeloEmitidoError(
            f"Imprima no máximo {LIMITE_ETIQUETAS_RTDPJ} etiquetas por vez.")
    return numeros


def procurar_externos_rtdpj(con: sqlite3.Connection, *, inicio: Any = None,
                            fim: Any = None, busca: Any = None,
                            limite: int = 200) -> list[dict]:
    """Selos do RTDPJ vindos de fora do sistema, disponíveis para etiqueta.

    ``tabela`` e ``ato_id`` vazios são a marca do acervo importado: o selo
    existe no razão, mas não aponta para um ato criado no Cartório Gestão.

    **E AQUI `ato_id IS NULL` ESTÁ CERTO, ao contrário do filtro de situação.**
    São duas perguntas diferentes com a mesma coluna: lá, «alguém usou este
    selo?» — e responder por `ato_id` publicava 7.762 selos usados como não
    usados; aqui, «este selo é do acervo, e por isso precisa de etiqueta
    impressa por fora?», e a resposta é exatamente o que este sistema não
    lavrou. Unificar as duas por parecença faria a etiqueta sair para selo já
    amarrado a um ato. Ver a docstring do módulo.
    """
    onde = ["UPPER(COALESCE(atribuicao,'')) IN ('RTDPJ','RTD','RCPJ')",
            "COALESCE(TRIM(tabela),'') = ''", "ato_id IS NULL",
            SEM_CANCELAR]
    params: list[Any] = []
    if _texto(inicio):
        onde.append("obtido_em >= ?")
        params.append(_texto(inicio))
    if _texto(fim):
        onde.append("obtido_em <= ?")
        params.append(_texto(fim) + FECHA_O_DIA)
    if _texto(busca):
        termo = f"%{_texto(busca).upper()}%"
        onde.append("(UPPER(numero) LIKE ? OR UPPER(COALESCE(texto,'')) LIKE ?)")
        params.extend((termo, termo))
    limite = max(1, min(int(limite or 200), 500))
    return [dict(r) for r in con.execute(
        f"""SELECT id, numero, texto, caminho, atribuicao, referencia,
                   obtido_em, obtido_por, qr_token
              FROM sd_selos
             WHERE {' AND '.join(onde)}
             ORDER BY obtido_em DESC, id DESC LIMIT ?""",
        params + [limite]).fetchall()]


def externos_rtdpj_para_etiqueta(con: sqlite3.Connection,
                                 valores: Any) -> list[dict]:
    """Confere e devolve os selos externos escolhidos, na ordem pedida."""
    numeros = numeros_informados(valores)
    if not numeros:
        raise SeloEmitidoError("Marque ao menos um selo para imprimir.")
    marcas = ",".join("?" for _ in numeros)
    achados = {str(r["numero"]).upper(): dict(r) for r in con.execute(
        f"""SELECT id, numero, texto, caminho, atribuicao, referencia,
                   tabela, ato_id, obtido_em, obtido_por, cancelado_em,
                   qr_token
              FROM sd_selos WHERE UPPER(numero) IN ({marcas})""",
        numeros).fetchall()}
    faltam = [n for n in numeros if n not in achados]
    if faltam:
        raise SeloEmitidoError(
            "Selo(s) não encontrado(s) no razão: " + ", ".join(faltam) + ".")
    fora = []
    for numero in numeros:
        selo = achados[numero]
        if str(selo.get("atribuicao") or "").upper() not in {"RTDPJ", "RTD", "RCPJ"}:
            raise SeloEmitidoError(f"O selo {numero} não pertence ao RTDPJ.")
        if selo.get("cancelado_em"):
            raise SeloEmitidoError(f"O selo {numero} está cancelado.")
        if selo.get("ato_id") is not None or str(selo.get("tabela") or "").strip():
            raise SeloEmitidoError(
                f"O selo {numero} já está ligado a um ato do sistema; "
                "imprima a etiqueta pela ficha desse ato.")
        fora.append(selo)
    return fora

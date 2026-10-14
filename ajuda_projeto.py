"""O que a ajuda sabe sobre o PROJETO — o relato #26 do oficial.

A FRASE DELE:

    «melhorar as capacidades da resolução de problemas. Precisa poder permitir,
     caso preciso, acesso a mais informações, inclusive acesso ao projeto do
     sistema para saber o que já foi feito, o que falta.»
    «Ajuda precisa ganhar mais ferramentas e autonomia. Precisa se aproximar
     mais do que sabe o claude code que estamos desenvolvendo o projeto.»

O QUE `ajuda_mapa` JÁ DAVA, E O QUE FALTAVA
    O mapa mede as **telas**, os **arquivos** e as **tabelas** desta
    instalação. Ele responde «como o sistema é feito» — e não responde nenhuma
    das duas perguntas do oficial: **o que já foi feito** e **o que falta**.

    Essas duas moram em três lugares, e os três são mensuráveis:

      1. os **documentos do projeto**, que contam o que cada versão trouxe e o
         que se mediu antes de construir;
      2. os **relatos** (`aj_problemas`), que dizem o que foi apontado, o que
         foi fechado e o que continua aberto;
      3. as **pendências declaradas** (`implantacao`), que dizem o que só o
         oficial pode informar.

E O QUE SE MEDIU AO CONSTRUIR ISTO
    **O servidor não tinha um único documento do projeto.** Eles moravam em
    duas pastas — 67 na raiz e 13 dentro da pasta empacotada —, e só a de
    dentro viaja no `.cgu`. A de fora nunca chegou. Consolidadas em 29/08/2026;
    ver `DOCUMENTACAO/LEIA-ME.md`.

A REGRA QUE NÃO MUDA: NADA AQUI SE ESCREVE À MÃO
    É a mesma de `ajuda_mapa`, e pelo mesmo motivo — que lá está escrito assim:
    *quem lê a lista velha não é um operador que estranha; é uma máquina que
    responde com convicção*. Os documentos saem da pasta, os relatos saem da
    tabela, a versão sai do `app`.

E A MESMA ECONOMIA: VAI O ÍNDICE, E NÃO A BIBLIOTECA
    São 169 documentos e mais de um milhão de caracteres. Mandá-los em toda
    pergunta custaria em toda pergunta — e a API cobra por uso. Vai o **índice**
    (o **nome e o título** de cada um — e não mais a primeira frase: ela custava
    11.099 caracteres em TODA pergunta e quem procura por assunto tem caminho
    melhor, que é `procurar_nos_documentos`), e o **texto inteiro só do
    documento pedido**. É a regra da fatia, que o mapa já segue com as telas.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import ajuda_base as BASE
import ajuda_mapa as MAPA
import ajuda_regras as REGRAS

RAIZ = Path(__file__).resolve().parent
# A PASTA VEM DA BASE, E NÃO DE UMA SEGUNDA ESCRITA DO CAMINHO. Quem lê os
# documentos é ela agora; dois lugares dizendo onde eles moram divergiriam no dia
# em que a pasta mudasse — a lição das duas listas que envelhecem.
PASTA = BASE.PASTA_DOS_DOCUMENTOS

# QUANTOS DOCUMENTOS UMA INSTALAÇÃO DEVE TER, NO MÍNIMO.
#
# **Isto não é um alvo: é um diagnóstico.** Medido em 15/09/2026, o servidor
# tinha **três** documentos de projeto, contra 169 na árvore de
# desenvolvimento — porque o `ATUALIZAR_SISTEMA.cmd` copiava `*.py`, telas,
# `static`, `modelos`, `VERSAO.txt` e `requirements.txt`, e **mais nada**: os
# `.md` não estavam em nenhuma das linhas dele.
#
#   O efeito era o pior possível para uma ajuda que lê documentos: ela
#   respondia olhando uma biblioteca de três arquivos, sem nada que dissesse
#   que a biblioteca não tinha chegado. **Ausência com cara de medição** — a
#   mesma família do `except Exception: return []`, que já apareceu aqui.
#
#   O piso é folgado de propósito (a casa tem 169 hoje): ele não existe para
#   medir tamanho, existe para separar «esta instalação tem o acervo de
#   documentos» de «a carga não chegou».
PISO_DE_DOCUMENTOS = 50

# Quanto de um documento cabe numa consulta. Medido: o maior deles tem mais de
# 90 mil caracteres, e o teto de resposta da API nao comporta varios assim.
# Cortar avisando e melhor que mandar tudo e a consulta falhar inteira — e o
# corte APARECE no texto, para quem le saber que ha mais.
LIMITE_DO_DOCUMENTO = 60_000

# O ÍNDICE DOS DOCUMENTOS NÃO LEVA A PRIMEIRA FRASE DELES — 15/09/2026.
#
# Ele levava, e a razão escrita aqui era boa: «um título sozinho
# («ROTEIRO_3.6.29») não diz nada a quem escolhe o que ler». **E o que a
# medição mostrou foi outra coisa** — a frase de abertura dos 162 documentos
# custava 11.099 caracteres, e o índice inteiro 23.949: **70 % de tudo o que
# vai junto de cada pergunta**, gasto em toda pergunta, para repetir o que o
# nome e o título já dizem. Medido antes de cortar, com o gancho fora:
# 12.527 — e sem o título, 4.185.
#
#   E medido DEPOIS do corte, contra a árvore de 15/09/2026: **12.850**. O
#   contexto inteiro que a ajuda manda ficou em 23.387 caracteres, e esta seção
#   é 13.020 dele — antes, só o índice passava de 24 mil.
#
#   O QUE SE PERDEU NÃO FICOU SEM CAMINHO. A frase de abertura era uma
#   APROXIMAÇÃO de «achar o documento pelo assunto», e uma frase nunca resumiu
#   um documento de cem mil caracteres. Quem faz isso agora é
#   `procurar_nos_documentos`, e faz melhor: lê o texto inteiro, conta o que
#   achou e diz de que documento saiu — e só custa quando é chamada.
#   **O índice diz o que EXISTE; a busca diz o que está DENTRO.**
#
# E O TÍTULO FICA, ainda que o nome do arquivo seja quase sempre igual a ele:
# `O_CCN_E_AS_DUAS_PAREDES.md` e «O CCN do e-Notariado: o item 4, e por que ele
# não foi construído» diferem no que interessa — o nome diz o assunto, o título
# diz o que se achou. Cortar os dois juntos economizaria 4.185 caracteres e
# devolveria a lista de nomes que este módulo já julgou insuficiente.
LIMITE_DA_BUSCA = 40
LIMITE_DA_LINHA = 240


def _titulo(caminho: Path) -> str:
    """O título de um documento — a primeira linha que começa com `#`.

    Lê só o começo do arquivo: montar o índice de 162 documentos lendo cada um
    inteiro custaria mais de um milhão de caracteres de disco para produzir
    umas poucas linhas.
    """
    try:
        with caminho.open(encoding="utf-8") as f:
            comeco = f.read(2000)
    except OSError:
        return caminho.stem

    for linha in comeco.splitlines():
        limpa = linha.strip()
        if limpa.startswith("#"):
            titulo = limpa.lstrip("#").strip()
            if titulo:
                return titulo
    return caminho.stem


def _sem_acento(texto: Any) -> str:
    """Sem acento e sem caixa, para a busca achar o que está escrito com eles.

    **É A DIFERENÇA ENTRE ACHAR E NÃO ACHAR.** Quem procura escreve «matricula»
    com a maior naturalidade — a palavra sem acento existe —, e o documento diz
    «matrícula». Sem isto a busca devolveria **nada**, com a mesma cara de quem
    mediu: é a família do `@cartorio` e do `except Exception: return []` outra
    vez, agora numa resposta que a ajuda daria com convicção («a casa não
    escreveu nada sobre isso»).

    Não se usa `pt_schema.normalizar_nome` de propósito: aquela normaliza NOME
    DE PESSOA, devolve `None` para vazio, e mora no schema do Protesto —
    pendurar a ajuda dos documentos nela seria acoplar duas coisas que não têm
    nada a ver, e o nome da função mentiria sobre o que ela faz aqui.
    """
    import unicodedata
    bruto = "" if texto is None else str(texto)
    return "".join(c for c in unicodedata.normalize("NFD", bruto)
                   if unicodedata.category(c) != "Mn").casefold()


def documentos() -> list[dict]:
    """O índice dos documentos do projeto, MEDIDO na pasta.

    **UMA MEDIÇÃO SÓ NA CASA.** Ela nasceu aqui, e o corpo passou a morar em
    `ajuda_base.documentos()` quando a base pré-carregada precisou do mesmo
    índice para indexar — «duas listas escritas à mão envelhecem na tarde em que
    se escrevem», e duas caminhadas pela mesma pasta divergiriam no dia em que
    uma pulasse um arquivo ilegível. Esta continua sendo a porta pública: a
    tela, o índice do contexto e os testes a chamam por aqui.
    """
    return BASE.documentos()


def indice() -> list[str]:
    """O índice em linhas curtas, para ir junto de toda pergunta.

    O NOME E O TÍTULO, e mais nada. O nome é o que se pede depois
    (`ler_documentacao`), e o título é o que diz de que assunto ele trata —
    «`O_CCN_E_AS_DUAS_PAREDES.md` — O CCN do e-Notariado: o item 4, e por que
    ele não foi construído» já responde metade das perguntas, e não custa quase
    nada. A primeira frase de cada documento custava 11.099 caracteres em toda
    pergunta, e quem procura por assunto tem caminho melhor:
    `procurar_nos_documentos`.
    """
    return [f"- `{d['arquivo']}` — {d['titulo']}" for d in documentos()]


def procurar_nos_documentos(termo: str, *, limite: int = LIMITE_DA_BUSCA) -> str:
    """As linhas dos documentos que falam de um termo, com o documento de cada.

    **O QUE ELA É HOJE, E O QUE ERA.** Até 18/09/2026 ela lia os 172 arquivos do
    disco **em cada chamada** — medido: **1.148 ms** por busca, contra **42 ms**
    da base pré-carregada, que lê uma vez e indexa em memória. O que a faz valer
    como caminho não é a velocidade: é ela **não varrer o assunto todo de novo a
    cada pergunta** — que foi o pedido do oficial («não dá pra buscar as
    respostas de tudo para cada problema»).

    **O CORPO MUDOU DE LUGAR, E A ASSINATURA NÃO** — e isso é deliberado. Ela
    tem chamador no modelo, na tela e nos testes, e reescrevê-la aqui seria a
    segunda régua de busca da casa. Quem procura agora é `ajuda_base`, que
    varre as **três** fontes na mesma leitura de memória; esta função continua
    sendo a porta dos documentos, com o **mesmo texto** que sempre devolveu —
    `test_a_busca_acha_o_trecho_e_diz_de_que_documento_e` o guarda linha por
    linha.

    **E A CONTA CRESCEU EM DOIS CASOS MEDIDOS, os dois para mais:** «carimbo que
    mente» acha 27 linhas onde achava 26 (a régua abre para as duas palavras
    separadas quando a frase inteira não basta, e o cabeçalho passou a contar), e
    «claude.md» acha 53 onde achava 33 — porque as linhas que falam de «Claude»
    também contam. **O texto da resposta passou a dizer quantas têm a frase
    exata** quando os dois números diferem: sem isso, «53 linha(s)» faria quem lê
    concluir que a casa escreveu 53 vezes «claude.md».
    """
    procurado = _sem_acento(termo).strip()
    if not procurado:
        raise ValueError("Diga o que procurar nos documentos do projeto.")
    return BASE.procurar(termo, fonte=BASE.FONTE_DOCUMENTO, limite=limite)


def documento(nome: str) -> dict | None:
    """O texto de UM documento, pelo nome do arquivo.

    O NOME NAO VIRA CAMINHO. `Path(nome).name` descarta qualquer `..` ou barra:
    sem isso, um nome vindo da tela poderia ler arquivo de fora da pasta — e
    esta funcao existe justamente para alimentar uma consulta que sai da casa.
    """
    seguro = Path(str(nome or "")).name
    if not seguro.lower().endswith(".md"):
        return None
    caminho = PASTA / seguro
    if not caminho.is_file():
        return None
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    cortado = len(texto) > LIMITE_DO_DOCUMENTO
    if cortado:
        texto = (texto[:LIMITE_DO_DOCUMENTO]
                 + "\n\n[...] (o documento continua; foram trazidos os "
                 f"primeiros {LIMITE_DO_DOCUMENTO} caracteres de "
                 f"{caminho.stat().st_size})")
    titulo = _titulo(caminho)
    return {"arquivo": seguro, "titulo": titulo, "texto": texto,
            "cortado": cortado}


def conferir_biblioteca() -> str:
    """A biblioteca de documentos chegou inteira? Vazio quando chegou.

    **O SILÊNCIO QUER DIZER «CHEGOU», E ELE É O CASO NORMAL.** Esta frase só
    aparece no dia em que a instalação ficou sem os documentos — e aparece com
    o número medido e o motivo, porque é isso que faz alguém ir conferir em vez
    de concluir que o acervo é pequeno mesmo.
    """
    quantos = len(documentos())
    if quantos >= PISO_DE_DOCUMENTOS:
        return ""
    return (f"(Atenção: esta instalação tem {quantos} documento(s) de projeto "
            f"e a casa tem mais de {PISO_DE_DOCUMENTOS}. A atualização rápida "
            "copia o programa, e não os documentos: se ela foi feita à mão, o "
            "acervo de leitura ficou para trás.)")


def relatos(con: sqlite3.Connection) -> dict:
    """O que foi apontado nesta casa, e em que pé está — medido na tabela.

    RESPONDE «O QUE JA FOI FEITO E O QUE FALTA» com o dado da propria casa, e
    nao com uma lista que eu escrevesse. O oficial ja disse, no relato #23, que
    lista sem numero nao serve: aqui cada um vem com o `#`, que e o mesmo
    numero da tela e do relatorio.
    """
    con.row_factory = sqlite3.Row
    linhas = [dict(r) for r in con.execute(
        """SELECT id, titulo, situacao, onde, versao, primeira_em, fechado_em,
                  fechado_nota
             FROM aj_problemas
            WHERE origem = 'RELATADO'
         ORDER BY id""")]
    abertos = [x for x in linhas if (x["situacao"] or "") == "ABERTO"]
    return {"todos": linhas, "abertos": abertos,
            "quantos": len(linhas), "quantos_abertos": len(abertos)}


def pendencias_declaradas(con: sqlite3.Connection) -> list[dict]:
    """O que só o oficial pode informar — de `implantacao`, e não daqui.

    PENDENCIA E DECLARADA, NAO ADIVINHADA, e quem a declara e quem a descobriu.
    Repetir a lista aqui faria duas listas divergirem, e a que a ajuda lesse
    seria sempre a velha.

    ESTA FUNCAO JA NASCEU COM DEFEITO, E ELE ERA O `except` LARGO. Eu chamava
    `implantacao.pendentes`, que nao existe — a funcao se chama `abertas` —, e
    um `except Exception: return []` transformava o `AttributeError` em «zero
    pendencias». A tela mostraria zero com cara de medicao, e quem lesse
    concluiria que a casa nao deve nada a ninguem.

    **Zero medido e zero por engano sao a mesma tela e coisas diferentes.** Por
    isso o erro agora VOLTA no lugar da lista, e quem chama o mostra.
    """
    import implantacao
    # `abertas` monta dicionario a partir da linha, e para isso a conexao
    # precisa da `row_factory`. O `db.connect()` da casa ja a traz; um `con`
    # cru, nao — e ali o erro sai falando de sequencia de dicionario, que nao
    # diz a ninguem o que fazer. Uma linha aqui poupa esse enigma.
    #
    # (A frase original citava a mensagem do SQLite ao pe da letra, e ela tem
    #  dentro uma palavra de comando de escrita. O varredor que prova que este
    #  modulo so LE compara o TEXTO DO ARQUIVO, comentario incluido — entao a
    #  citacao ficava vermelha. **Descrever em prosa; nao citar.**
    #
    #  E ESTA NOTA JA ERROU DUAS VEZES, pela mesma razao. A primeira correcao
    #  dizia «e a licao da funcao de recorte de texto outra vez» — escrevendo o
    #  nome daquela funcao ao pe da letra. O varredor de portabilidade procura
    #  justamente esse nome, e derrubou a suite inteira: eu tinha citado, no
    #  comentario que manda nao citar. Dois varredores diferentes, o mesmo
    #  engano, e ele custou uma rodada de vinte e nove minutos.)
    con.row_factory = sqlite3.Row
    return [dict(x) for x in implantacao.abertas(con)]


def resumo(con: sqlite3.Connection, versao: str = "") -> dict:
    """Tudo junto, para a tela e para o contexto da consulta."""
    r = relatos(con)
    docs = documentos()
    return {
        "versao": versao,
        "documentos": docs,
        "quantos_documentos": len(docs),
        "relatos": r,
        "pendencias": pendencias_declaradas(con),
    }


def para_a_consulta(con: sqlite3.Connection, *, versao: str = "",
                    documento_pedido: str = "") -> str:
    """O texto que vai junto da pergunta. É a fatia, e não a biblioteca.

    O QUE VAI SEMPRE: a versao, os relatos abertos e as pendencias declaradas,
    o que mudou, o indice das regras e o **indice** dos documentos, para quem
    responde saber o que existe e poder pedir. O que NAO vai sempre e o texto
    dos documentos: sao centenas e mais de um milhao de caracteres, e manda-los
    em toda pergunta custaria em toda pergunta — a API cobra por uso.

    E O INDICE NAO LEVA A PRIMEIRA FRASE DE CADA DOCUMENTO desde 15/09/2026:
    ela custava **11.099** caracteres em toda pergunta para dar o comeco deles,
    e quem procura por assunto agora tem `procurar_nos_documentos`, que le o
    documento inteiro e diz de onde tirou. Aqui nao se escreve o numero do
    indice: ele muda a cada documento, e numero escrito a mao envelhece.
    """
    r = relatos(con)
    partes = [f"# O projeto CartorioGestao — versão {versao or 'desconhecida'}"]

    partes.append("\n## Os relatos desta casa "
                  f"({r['quantos_abertos']} abertos de {r['quantos']})")
    # O QUE «ABERTO» QUER DIZER AQUI — e sem esta frase quem responde erra com
    # conviccao. A situacao e o que o OFICIAL marcou na tela: nada se fecha
    # sozinho, e conserto entregue continua ABERTO ate ele clicar. Dizer «voce
    # tem 28 problemas em aberto» a quem teve vinte e quatro consertados seria
    # o relato #23 outra vez — duas vistas do mesmo fato sem o mesmo texto.
    partes.append("(«ABERTO» quer dizer que ninguém marcou como resolvido na "
                  "tela — e não que nada foi feito. Nada se fecha sozinho: "
                  "quem fecha é o oficial.)")
    for x in r["todos"]:
        marca = "ABERTO" if (x["situacao"] or "") == "ABERTO" else "resolvido"
        partes.append(f"- #{x['id']} [{marca}] {x['titulo']}"
                      + (f" — {x['fechado_nota']}" if x["fechado_nota"] else ""))

    try:
        pend = pendencias_declaradas(con)
    except Exception as erro:                              # noqa: BLE001
        # NAO SE CALA, E NAO DERRUBA. Um pedaco do contexto que falha nao pode
        # derrubar a consulta inteira — a ajuda nao pode virar um segundo
        # defeito. Mas tambem nao pode SUMIR: silencio aqui seria lido como
        # «nao ha pendencia nenhuma», que e o engano que esta funcao ja teve.
        partes.append("\n## O que só o oficial pode informar\n"
                      f"(não deu para medir: {type(erro).__name__}: {erro})")
    else:
        partes.append(f"\n## O que só o oficial pode informar ({len(pend)})")
        for p in pend:
            partes.append("- " + str(p.get("titulo") or p.get("serie") or p))

    # O QUE MUDOU, MEDIDO E NAO LEMBRADO.
    #
    # E o item «atualizar sozinha» do lembrete: nada aqui foi escrito para a
    # ajuda. Quem responde sao duas fotografias da instalacao, comparadas -
    # uma tirada na versao que a casa rodava antes, outra na que ela roda
    # agora. Vai ANTES do indice dos documentos de proposito: o indice diz o
    # que existe; isto diz o que ACABOU de existir, que e a pergunta.
    linhas = mudancas_medidas(con)
    if linhas:
        partes.append("\n## O que mudou nesta instalação")
        partes.extend(linhas)

    # AS REGRAS DA CASA — o que decidir aqui, e não o que o assunto decide em
    # geral. Vai o INDICE, e nao a prosa: sao 385 mil caracteres, e o texto de
    # uma secao so vai quando ela e pedida (`ler_regras`). E vai antes do
    # indice dos documentos de proposito: os documentos contam o que foi
    # construido; as regras contam **por que** se construiu assim — e e a
    # segunda pergunta que o balcao faz.
    if REGRAS.disponivel():
        partes.append("\n## As regras desta casa "
                      "— peça uma seção pelo número ou pelo título")
        partes.extend(REGRAS.indice_para_o_contexto())
        atraso = REGRAS.resumo_da_conferencia(versao)
        if atraso:
            partes.append(atraso)

    docs = documentos()
    partes.append(f"\n## Os documentos do projeto ({len(docs)}) — "
                  "peça um pelo nome do arquivo para ler inteiro, ou peça "
                  "`procurar_nos_documentos` com uma palavra para achar em qual "
                  "deles o assunto está")
    vazio = conferir_biblioteca()
    if vazio:
        partes.append(vazio)
    partes.extend(indice())

    if documento_pedido:
        doc = documento(documento_pedido)
        if doc:
            partes.append(f"\n## {doc['arquivo']} — texto\n\n{doc['texto']}")
        else:
            # DIZER QUE NAO ACHOU E MELHOR QUE OMITIR. Omitindo, quem responde
            # acharia que o documento nao tem nada sobre o assunto — e
            # responderia com convicção sobre uma leitura que nao aconteceu.
            partes.append(f"\n(O documento «{documento_pedido}» não existe "
                          "nesta instalação.)")

    return "\n".join(partes)


def mudancas_medidas(con: sqlite3.Connection) -> list[str]:
    """O que mudou entre as duas ultimas versoes medidas. So LE.

    **E O QUE A AJUDA NAO SABIA, E NINGUEM ESCREVIA.** Havia um roteiro por
    versao (`ROTEIRO_3.6.92.md`), e ele parou na 3.6.92. Agora quem responde
    sao duas fotografias comparadas: quem as grava e `ajuda.fotografar`, na
    abertura do servidor, e aqui so se le.

    DEVOLVE LISTA VAZIA QUANDO NAO HA O QUE COMPARAR. Instalacao nova, ou
    primeira versao depois de esta tabela existir, nao tem anterior. Vazio aqui
    nao e «nada mudou»: e «nao tenho com o que comparar», e quem le nao pode
    confundir uma coisa com a outra. Por isso a secao so aparece com as duas.

    **E O QUE MUDOU NAO E SO TELA NOVA.** A diferenca das fotografias diz o
    que mudou de FORMA — tela, arquivo, tabela. Falta o que mudou de FUNDO, e
    quem o escreve e o desenvolvimento, na nota de cada relato: por que o
    defeito existia, e o que a medicao mostrou antes de consertar. Sem isso a
    ajuda respondia «1 tela nova» e nao sabia explicar a tela nova — e a nota
    ja estava escrita e ninguem a lia. Ver `_notas_do_desenvolvimento`.
    """
    try:
        linhas = con.execute(
            "SELECT versao, medida_em, fotografia FROM aj_mapas "
            "ORDER BY id DESC LIMIT 2"
        ).fetchall()
    except sqlite3.Error:
        # BANCO ANTIGO, SEM A TABELA. Nao ha o que comparar, e isto some da
        # tela, que e o que a falta de dado e. Um vazio aqui NAO vira «nada
        # mudou»: quem escreve o texto e `resumo_da_diferenca`, e ele so e
        # chamado com duas medidas nas maos.
        return []
    if len(linhas) < 2:
        return []

    medidas: list[dict] = []
    for linha in linhas:
        try:
            medidas.append(json.loads(dict(linha).get("fotografia") or "{}"))
        except (TypeError, ValueError):
            # FOTOGRAFIA ILEGIVEL NAO DERRUBA A TELA: uma linha que nao se le
            # nao pode impedir o oficial de ver o resto do estado da casa.
            return []
    antiga = dict(linhas[1])
    ditas = MAPA.resumo_da_diferenca(MAPA.diferenca(medidas[1], medidas[0]))

    notas = _notas_do_desenvolvimento(con, desde=str(antiga.get("medida_em") or ""))
    if not notas:
        return ditas
    # O CABECALHO NAO PROMETE MAPA UM A UM. A primeira versao dizia «o FUNDO de
    # cada mudanca acima», e o ensaio contra a producao desmentiu: das seis
    # notas daquele dia, uma so era de tela nova — as outras eram conserto sem
    # tela nenhuma. Prometer o par faria quem le procurar correspondencia onde
    # nao ha, e concluir que faltou nota.
    return ditas + [""] + [
        (
            "### O que o desenvolvimento escreveu neste intervalo — desde a "
            f"versão {antiga.get('versao') or '?'}, medida em "
            f"{antiga.get('medida_em') or '?'} (ISTO NÃO É o par de cada linha "
            "acima: é o que se mexeu no período, tenha tela nova ou não)"
        )
    ] + [
        (
            "O primeiro estado é o que o OFICIAL marcou na tela; o segundo, o "
            "que o desenvolvimento diz que fez. São coisas diferentes — e "
            "«ABERTO» quer dizer só que ninguém marcou como resolvido."
        )
    ] + notas


def _primeira_frase(texto: str, limite: int = 240) -> str:
    """A primeira frase da nota, e nao a nota inteira. So calcula.

    A nota de um relato tem dez, vinte linhas — e elas estao inteiras na lista
    dos relatos, que vai no mesmo contexto. Aqui a pergunta e «o que mudou», e
    um resumo que ninguem acaba de ler nao responde nada.

    **E O CORTE NAO PODE PARAR NO MEIO DE UMA IDEIA.** A primeira versao cortava
    na ultima palavra antes do limite, e o ensaio contra a producao mostrou o
    resultado: a nota do #48 terminava em «...`import custas as CU` vivia dentro
    de OUTRA funcao do mesmo», que nao e uma frase e nao diz nada. Agora, quando
    a primeira frase passa do limite, o corte procura a ultima pausa de verdade
    — `;`, `:`, `,` — e so cai na palavra quando nao ha nenhuma.
    """
    cru = " ".join(str(texto or "").split())
    for marca in (". ", "! ", "? "):
        corte = cru.find(marca)
        if 0 < corte <= limite:
            return cru[:corte + 1] + " […]"
    if len(cru) <= limite:
        return cru
    recorte = cru[:limite]
    for pausa in ("; ", ": ", ", "):
        # A PAUSA SO SERVE SE SOBRAR IDEIA — e o piso e 60, e nao 80, por
        # Medição: a nota do #48 tem a frase que explica tudo fechada numa
        # advertencia de dois pontos aos 66 caracteres («... ONDE ELE NAO TINHA
        # SIDO CRIADO:»), e com o piso em 80 ela era descartada e o resumo
        # terminava em «...vivia dentro de OUTRA funcao do mesmo», que nao diz
        # nada. Sessenta caracteres ainda sao uma ideia; menos que isso e uma
        # palavra com reticencias.
        onde = recorte.rfind(pausa)
        if onde >= 60:
            return recorte[:onde + 1] + " […]"
    return recorte.rsplit(" ", 1)[0] + " […]"


def _notas_do_desenvolvimento(con: sqlite3.Connection, *, desde: str) -> list[str]:
    """O que o desenvolvimento escreveu sobre os relatos. SO LE.

    **A JANELA E ABERTA EM CIMA, E ISSO E MEDIDO.** Ela comeca na versao que a
    casa rodava antes; nao termina na fotografia de hoje. Medido em 15/09/2026
    na producao: a 3.6.130 foi fotografada as **10:42**, e as notas daquele dia
    foram escritas as **13:11** e as **14:18** — fechar a janela na fotografia
    mostraria zero justamente no dia em que mais se escreveu. O trabalho de uma
    versao termina DEPOIS de ela subir: e isso que a janela aberta diz.

    E ela anda sozinha: quando a proxima fotografia entra, a de hoje vira o
    piso e as notas velhas saem. Nada aqui se apaga a mao.
    """
    if not desde:
        return []
    try:
        achados = con.execute(
            "SELECT id, situacao, nota_dev_estado, nota_dev, nota_dev_em "
            "FROM aj_problemas "
            "WHERE nota_dev IS NOT NULL AND TRIM(nota_dev) <> '' "
            "  AND nota_dev_em IS NOT NULL AND nota_dev_em > ? "
            "ORDER BY nota_dev_em, id", (str(desde),)).fetchall()
    except sqlite3.Error:
        # BANCO DE ANTES DAS COLUNAS. Nao e erro: e uma instalacao que ainda
        # nao tem notas, e a secao some — dizer «nenhuma nota» seria afirmar
        # que ninguem escreveu, e pode ser que a coluna nao exista.
        return []
    linhas = []
    for linha in achados:
        x = dict(linha)
        # OS DOIS ESTADOS SAO COISAS DIFERENTES E VAO SEPARADOS: `situacao` e
        # o que o OFICIAL marcou na tela, `nota_dev_estado` e o que o
        # DESENVOLVIMENTO diz que fez. Sao justamente os dois que a ajuda
        # confunde se ler so um — o relato #23 outra vez.
        linhas.append(
            f"- #{x['id']} (relato {x.get('situacao') or '?'}, "
            f"desenvolvimento {x.get('nota_dev_estado') or '?'}): "
            f"{_primeira_frase(x.get('nota_dev'))}")
    return linhas

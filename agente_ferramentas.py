"""O QUE O AGENTE PODE FAZER — o catálogo de ferramentas, e o freio de cada uma.

POR QUE O CATÁLOGO MORA NUM MÓDULO SÓ
    Porque a pergunta «o que o agente pode fazer?» tem de ter **uma** resposta,
    e ela tem de ser legível por quem responde pela serventia. Espalhadas pelo
    laço, as ferramentas seriam o que o agente faz por acidente; num catálogo,
    elas são o que ele faz por decisão — e a tela as mostra uma a uma.

DUAS CLASSES, E A DIFERENÇA É DE CONSEQUÊNCIA
    `LEITURA` não muda nada, e roda sempre. `ESCRITA` muda o sistema, e **só
    roda com a escrita ligada** na configuração — que nasce desligada.

    A classe não é enfeite de tela: é o que decide se a ferramenta entra na
    lista que vai ao provedor. Ferramenta de escrita que não foi liberada nem
    sequer é oferecida ao modelo. **Oferecer e recusar depois ensinaria o
    modelo a pedir o que não pode** — e gastaria um turno por tentativa.

O QUE ESTE MÓDULO RECUSA POR PRINCÍPIO
    **Não há ferramenta que toque em ATO.** Nenhuma escreve em assentamento,
    matrícula, escritura, título, selo, cobrança ou caixa. «Fazer mudança
    objetiva» aqui é: anotar o que se achou, registrar o que a conferência
    mediu, e mexer no alcance de um módulo. O resto continua sendo ato do
    delegatário, com humano no loop — e não por timidez: é a regra da casa.

    **Não há ferramenta de shell e não há ferramenta que execute código.** Um
    agente com console nesta máquina é um agente que apaga o banco por engano
    num sábado.

A MÁSCARA NÃO É DECISÃO DA FERRAMENTA, É DECLARAÇÃO DELA
    Cada ferramenta diz, no campo `nomes_livres`, se o que ela devolve é
    **dado de pessoa** (o que vem do banco) ou **estrutura** (código e
    documentação). O que sai daqui passa por
    `ajuda_privacidade.sanitizar_para_modelo`, com a escolha da ferramenta —
    e o campo é obrigatório na construção, de modo que ferramenta nova não
    nasce muda sobre o próprio risco.

A ESCRITA DEIXA RASTRO DESFEITO COM UM CLIQUE
    Toda ferramenta de escrita grava o `antes` e o `depois` em `ag_mudancas`.
    É o que faz a permissão de escrever ser defensável: **quem pode desfazer
    com um clique pode ousar mais.** O que é só acréscimo — uma nota, um
    achado — nasce marcado como não reversível, e a tela diz isso em vez de
    oferecer um botão que não cumpre o que promete.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import agente_provedores as PROV
import agente_schema as AG
import ajuda_base as BASE
import ajuda_codigo as CODIGO
import ajuda_mapa as MAPA
import ajuda_privacidade as PRIV
import ajuda_problemas as AP
import ajuda_projeto as PROJ
import ajuda_regras as REGRAS
import modulos_ligados as ML


class FerramentaError(ValueError):
    """Recusa de ferramenta, com a frase pronta para quem opera."""


LEITURA, ESCRITA = "LEITURA", "ESCRITA"

# ------------------------------------------------------------- os limites

LIMITE_DE_LINHAS = 120          # por leitura de código
LIMITE_DE_RESULTADOS = 40       # por busca
LIMITE_DE_LINHAS_DE_BANCO = 60  # por consulta
LIMITE_DE_CARACTERES = 24_000   # do que volta de UMA ferramenta
LIMITE_DE_CELULA = 400          # por célula, para uma linha enorme não dominar

# OS NOMES QUE NÃO PODEM SAIR DO BANCO PARA O PROVEDOR.
#
# Eles valem sobre o TEXTO da consulta, e não sobre as colunas do resultado —
# porque o resultado é lido como texto, e não há como saber que coluna um
# `SELECT` trouxe sem perguntar o esquema antes. Recusar pelo texto é grosseiro
# e é suficiente: para diagnosticar, nenhuma destas palavras é necessária.
NOMES_PROIBIDOS = (
    "senha", "password", "hash", "salt", "token", "segredo", "secret",
    "api_key", "apikey", "credencial", "private",
)

# AS TABELAS QUE NÃO SE LEEM, e por quê: a primeira guarda as chaves de API dos
# robôs em texto claro. Um `SELECT` nela publicaria a credencial da casa no
# provedor — e a barreira de privacidade não a pegaria, porque uma chave de API
# não tem forma de CPF nem de e-mail.
TABELAS_PROIBIDAS = ("robo_config", "ag_config")


@dataclass(frozen=True)
class Contexto:
    """O que uma ferramenta pode saber sobre quem a chamou.

    **Não carrega conexão, e isso é de propósito.** Uma conexão viva aqui
    dentro seria uma transação aberta atravessando uma chamada de rede, que é
    o defeito que este projeto já pagou caro. Cada ferramenta abre a sua.
    """
    db: Any
    raiz: Path
    pasta_de_dados: Path
    agora: str
    usuario: str
    sessao_id: int
    versao: str = ""
    app: Any = None


@dataclass(frozen=True)
class Ferramenta:
    """Uma coisa que o agente sabe fazer, com o que ele lê para decidir."""
    nome: str
    descricao: str
    esquema: dict
    tipo: str
    nomes_livres: bool
    executar: Callable[..., str]

    @property
    def e_escrita(self) -> bool:
        return self.tipo == ESCRITA


# --------------------------------------------------------- o texto de apoio


def _texto(argumentos: dict, chave: str, *, obrigatorio: bool = True) -> str:
    """Um argumento de texto, aparado. Vazio obrigatório é recusa, não silêncio."""
    valor = str(argumentos.get(chave) or "").strip()
    if obrigatorio and not valor:
        raise FerramentaError(f"Faltou o argumento «{chave}».")
    return valor


def _inteiro(argumentos: dict, chave: str, *, padrao: int = 0,
             minimo: int = 0, maximo: int = 0) -> int:
    """Um argumento inteiro, preso entre o mínimo e o máximo."""
    bruto = argumentos.get(chave)
    if bruto in (None, ""):
        return padrao
    try:
        numero = int(str(bruto).strip())
    except (TypeError, ValueError):
        raise FerramentaError(
            f"O argumento «{chave}» esperava um número e veio {bruto!r}."
        ) from None
    numero = max(minimo, numero)
    return min(maximo, numero) if maximo else numero


def _cortar(texto: str, limite: int = LIMITE_DE_CARACTERES) -> str:
    """O que volta é grande; o modelo não precisa de tudo, e o custo é por token."""
    if len(texto) <= limite:
        return texto
    return (texto[:limite]
            + f"\n\n[...] (cortado em {limite} caracteres de {len(texto)})")


def _medir_a_casa(ctx: Contexto) -> list[dict]:
    """A conferência da casa, com o que só o `Database` sabe medir.

    **AS MEDIÇÕES VÊM DE FORA** — as disputas e a integridade do banco são do
    `Database`, que é quem tem o arquivo de registro e a quem pertencem os
    comandos de conferência que só o SQLite tem. `ajuda_problemas` recebe as
    duas prontas e não sabe de onde vieram; este é o único lugar onde as duas
    se encontram, para as duas ferramentas que medem a casa não divergirem.
    """
    with ctx.db.connect() as con:
        return AP.conferir_a_casa(
            con, agora=ctx.agora,
            disputas=ctx.db.disputas_de_escrita(),
            banco=ctx.db.conferencia_do_banco())


# =========================================================== as de LEITURA


def _le_estado(ctx: Contexto) -> str:
    """Como está a casa agora: versão, problemas, banco, módulos e provedor."""
    with ctx.db.connect() as con:
        con.row_factory = sqlite3.Row
        contagem = AP.contagem(con)
        tabelas = len([r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")])
    ligados = {chave: ML.alcance(ctx.db.get_setting, chave)
               for chave in ML.CHAVE_DA_CONFIGURACAO}
    banco = ctx.db.conferencia_do_banco()
    disputas = ctx.db.disputas_de_escrita()
    chaves = PROV.chaves(ctx.pasta_de_dados)
    linhas = [
        f"Versão do sistema: {ctx.versao or '—'}.",
        f"Tabelas no banco: {tabelas}.",
        f"Integridade do banco: {banco['integridade']}; "
        f"chaves órfãs: {banco['orfas']}.",
        f"Disputas de escrita nos últimos 30 dias: {disputas['recentes']} "
        f"(total no registro: {disputas['total']}).",
        "",
        "PROBLEMAS ANOTADOS:",
        f"  total: {contagem['total']} — abertos: {contagem['abertos']}, "
        f"relatados pelo balcão: {contagem['relatados']}, "
        f"resolvidos: {contagem['resolvidos']}, "
        f"voltaram depois de abertos: {contagem['voltaram']}",
        "",
        "ALCANCE DOS MÓDULOS CONTROLADOS:",
    ]
    for chave, ate_onde in sorted(ligados.items()):
        linhas.append(f"  {chave}: {ate_onde}")
    linhas += ["", "PROVEDORES COM CHAVE INFORMADA:",
               "  " + (", ".join(sorted(chaves)) or "nenhum")]
    return "\n".join(linhas)


def _le_codigo(ctx: Contexto, *, caminho: str, linha: int = 0) -> str:
    """Um trecho do código do sistema, numerado. Só arquivo do próprio sistema."""
    trecho = CODIGO.ler_trecho(caminho, int(linha), raio=LIMITE_DE_LINHAS)
    if trecho is None:
        raise FerramentaError(
            f"Não posso ler «{caminho}»: ou ele não é um arquivo do sistema, ou "
            f"não tem uma das extensões que eu leio "
            f"({', '.join(sorted(CODIGO.EXTENSOES))}). Eu leio somente o código "
            f"do próprio Cartório Gestão.")
    return (f"Arquivo: {trecho.arquivo}\n"
            f"Linhas {trecho.linha_inicial} a {trecho.linha_final} "
            f"(ponto principal: {trecho.linha_central})\n"
            f"SHA-256 do arquivo: {trecho.sha256}\n"
            f"Conferência de sintaxe: {trecho.sintaxe}\n\n{trecho.texto}")


def _busca_codigo(ctx: Contexto, *, termo: str,
                  limite: int = LIMITE_DE_RESULTADOS) -> str:
    """Procura um texto no código do sistema e devolve onde ele aparece."""
    try:
        padrao = re.compile(termo)
    except re.error as erro:
        raise FerramentaError(
            f"«{termo}» não é uma expressão que eu saiba procurar ({erro}). "
            f"Use texto simples, ou uma expressão regular válida.") from erro
    achados: list[str] = []
    arquivos = 0
    for caminho in CODIGO.arquivos_do_sistema(ctx.raiz):
        arquivos += 1
        try:
            texto = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relativo = caminho.relative_to(ctx.raiz).as_posix()
        for numero, conteudo in enumerate(texto.splitlines(), 1):
            if padrao.search(conteudo):
                achados.append(f"{relativo}:{numero}: {conteudo.strip()[:200]}")
                if len(achados) >= limite:
                    break
        if len(achados) >= limite:
            break
    if not achados:
        return (f"Nada achei para «{termo}» em {arquivos} arquivo(s) do sistema. "
                f"Isso quer dizer que aquele texto não está escrito no código.")
    return (f"{len(achados)} ocorrência(s) para «{termo}»"
            + (" (parei no limite; há mais)" if len(achados) >= limite else "")
            + ":\n" + "\n".join(achados))


def _le_esquema(ctx: Contexto, *, tabela: str = "") -> str:
    """As tabelas e as colunas desta instalação.

    **PERGUNTA AO BANCO PELA PORTA PORTÁTIL**, e não pela do SQLite: um
    `SELECT ... LIMIT 0` devolve a descrição das colunas sem trazer linha
    nenhuma, e é o mesmo caminho que `ajuda_mapa` já usa. A porta que só o
    SQLite tem está reservada aos módulos de esquema, que é onde ela é a
    máquina da migração — e este não é um deles.
    """
    with ctx.db.connect() as con:
        nomes = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        if tabela:
            escolhida = tabela.strip()
            if escolhida not in nomes:
                raise FerramentaError(
                    f"Não existe tabela «{tabela}» nesta instalação. As que "
                    f"existem: {', '.join(nomes[:60])}"
                    + (" (e outras)" if len(nomes) > 60 else "") + ".")
            nomes = [escolhida]
        linhas = []
        for nome in nomes:
            if nome.startswith("sqlite_"):
                continue
            try:
                cursor = con.execute(f'SELECT * FROM "{nome}" LIMIT 0')
                colunas = [d[0] for d in (cursor.description or [])]
            except sqlite3.Error:
                colunas = []
            linhas.append(f"{nome}: " + (", ".join(colunas) or "(sem colunas)"))
    return "\n".join(linhas)


def _consulta_banco(ctx: Contexto, *, consulta: str,
                    limite: int = LIMITE_DE_LINHAS_DE_BANCO) -> str:
    """Uma leitura no banco — e **somente** leitura.

    O QUE ESTA FERRAMENTA NÃO DEIXA PASSAR, e por quê cada uma:

      - **outra coisa que não `SELECT` ou `WITH`** — não há o que argumentar: o
        agente lê o banco; quem escreve nele são as ferramentas de escrita, que
        deixam rastro. Uma escrita por aqui passaria fora do rastro.
      - **ponto e vírgula no meio** — é por ali que passa a segunda instrução,
        que ninguém revisou.
      - **comentário de SQL** — é por ali que passa o texto que o banco não
        executa. Sem comentário, o que está escrito é o que roda.
      - **nome de credencial** (`senha`, `hash`, `token`, `api_key`…) — a
        barreira de privacidade procura forma de CPF e de e-mail, e não
        reconhece uma chave de API. Esta recusa é o que a cobre.
      - **as tabelas de configuração de robôs e do agente** — a primeira
        guarda chaves de API em texto claro.
      - **`SELECT *`** — a consulta traz colunas que ninguém pediu, e é assim
        que um campo que não podia sair sai.
    """
    sql = (consulta or "").strip().rstrip(";").strip()
    if not sql:
        raise FerramentaError("A consulta veio vazia.")
    baixo = sql.lower()
    if not (baixo.startswith("select") or baixo.startswith("with")):
        raise FerramentaError(
            "Eu só leio o banco: a consulta precisa começar com SELECT ou com "
            "WITH. Para mudar o sistema existem as ferramentas próprias, que "
            "deixam rastro e podem ser desfeitas.")
    if ";" in sql:
        raise FerramentaError(
            "A consulta tem ponto e vírgula no meio, o que permite uma segunda "
            "instrução escondida atrás da primeira. Mande uma consulta só.")
    if "--" in sql or "/*" in sql:
        raise FerramentaError(
            "Tirei o comentário da consulta: ele é um lugar por onde passa "
            "texto que o banco não executa. Escreva só a consulta.")
    proibidos = [nome for nome in NOMES_PROIBIDOS if nome in baixo]
    if proibidos:
        raise FerramentaError(
            f"A consulta pede por {', '.join(proibidos)}, que é nome de "
            f"credencial. Isso não sai do servidor para provedor nenhum.")
    passadas = [t for t in TABELAS_PROIBIDAS if t in baixo]
    if passadas:
        raise FerramentaError(
            f"A tabela {', '.join(passadas)} guarda chave de API em texto "
            f"claro e não é lida pelo agente.")
    if "select *" in baixo and "sqlite_master" not in baixo:
        raise FerramentaError(
            "Escreva as colunas que você quer, em vez de `SELECT *`: assim a "
            "consulta não traz, sem querer, uma coluna que não podia sair.")

    with ctx.db.connect() as con:
        try:
            cursor = con.execute(sql)
            linhas = cursor.fetchmany(int(limite))
            colunas = [d[0] for d in (cursor.description or [])]
        except sqlite3.Error as erro:
            raise FerramentaError(
                f"O banco recusou a consulta: {erro}. Confira os nomes das "
                f"tabelas e das colunas com a ferramenta de esquema.") from erro
    if not colunas:
        return "A consulta não devolveu coluna nenhuma."
    saida = [" | ".join(colunas)]
    for linha in linhas:
        celulas = []
        for valor in tuple(linha):
            texto = "NULL" if valor is None else str(valor)
            if len(texto) > LIMITE_DE_CELULA:
                texto = texto[:LIMITE_DE_CELULA] + "…"
            celulas.append(texto)
        saida.append(" | ".join(celulas))
    if len(linhas) >= int(limite):
        saida.append(f"(parei em {limite} linhas; há mais)")
    return "\n".join(saida)


def _le_problemas(ctx: Contexto, *, situacao: str = "",
                  limite: int = 20) -> str:
    """A lista de problemas anotados, do mais recente para o mais antigo."""
    with ctx.db.connect() as con:
        con.row_factory = sqlite3.Row
        problemas = AP.listar(con, situacao=situacao or None,
                              limite=int(limite))
    if not problemas:
        return ("Não há problema nenhum anotado"
                + (f" na situação {situacao}." if situacao else "."))
    linhas = []
    for p in problemas:
        linhas.append(
            f"#{p['id']} [{p['situacao']}] {p['titulo']}\n"
            f"    origem: {p['origem']} | tela: {p.get('onde') or '—'} | "
            f"{p.get('vezes')}x, a última em {p.get('ultima_em') or '—'}\n"
            f"    nota do desenvolvimento: {p.get('nota_dev_estado') or '—'}"
            + (f" — {p.get('nota_dev')}" if p.get("nota_dev") else ""))
    return f"{len(problemas)} problema(s):\n" + "\n".join(linhas)


def _le_problema(ctx: Contexto, *, problema_id: int) -> str:
    """Um problema inteiro: o que ficou escrito, onde aconteceu e o trecho."""
    mapa = None
    with ctx.db.connect() as con:
        con.row_factory = sqlite3.Row
        linha = AP.ler(con, int(problema_id))
        if linha and ctx.app is not None:
            mapa = MAPA.do_processo(ctx.app, con, versao=ctx.versao)
    if not linha:
        raise FerramentaError(f"Não achei o problema #{problema_id}.")
    p = dict(linha)
    partes = [
        f"PROBLEMA #{p['id']} — {p['titulo']}",
        f"Origem: {p['origem']} | situação: {p['situacao']}",
        f"Tela: {p.get('onde') or '—'} ({p.get('caminho') or '—'})",
        f"Versão em que apareceu: {p.get('versao') or '—'}",
        f"Aconteceu {p.get('vezes')}x, de {p.get('primeira_em') or '—'} "
        f"a {p.get('ultima_em') or '—'}",
        "",
        "O QUE FICOU ESCRITO:",
        str(p.get("detalhe") or "(nada)"),
    ]
    if p.get("nota_dev"):
        partes += ["", "NOTA DO DESENVOLVIMENTO:",
                   f"estado: {p.get('nota_dev_estado') or '—'}",
                   str(p["nota_dev"]),
                   f"prova: {p.get('nota_dev_prova') or '—'}"]
    trecho = CODIGO.inspecionar(
        p, arquivo_sugerido=MAPA.arquivo_da_tela(mapa or {}, p.get("onde")))
    if trecho:
        partes += ["", f"TRECHO DE {trecho.arquivo} "
                       f"({trecho.linha_inicial}-{trecho.linha_final}):",
                   trecho.texto]
    return _cortar("\n".join(partes))


def _conferencias(ctx: Contexto) -> str:
    """A conferência da casa: o que a instalação mede sobre si mesma."""
    achados = _medir_a_casa(ctx)
    if not achados:
        return "A conferência não achou nada fora do lugar."
    linhas = []
    for a in achados:
        linhas.append(f"[{'GRAVE' if a.get('grave') else 'leve'}] {a['titulo']}\n"
                      f"    chave: {a['chave']}\n"
                      f"    {a['detalhe']}")
    return (f"A conferência achou {len(achados)} coisa(s):\n"
            + "\n".join(linhas)
            + "\n\nSe alguma precisa virar problema anotado, use a ferramenta "
              "que registra os achados.")


def _le_documentacao(ctx: Contexto, *, nome: str = "") -> str:
    """Os documentos do projeto, ou um deles inteiro."""
    if nome:
        achado = PROJ.documento(nome)
        if not achado:
            disponiveis = ", ".join(d["arquivo"] for d in PROJ.documentos())
            raise FerramentaError(
                f"Não achei o documento «{nome}». Os que existem: {disponiveis}.")
        return _cortar(f"{achado['titulo']}\n({achado['arquivo']})\n\n"
                       f"{achado.get('texto') or ''}")
    with ctx.db.connect() as con:
        con.row_factory = sqlite3.Row
        return _cortar(PROJ.para_a_consulta(con, versao=ctx.versao,
                                            documento_pedido=""))


def _procura_nos_documentos(ctx: Contexto, *, termo: str = "",
                            limite: int = 0) -> str:
    """Procura um termo DENTRO dos documentos do projeto, e diz onde ele está.

    **É A FERRAMENTA QUE TROCA «LER OS 162» POR «ACHAR O TRECHO».** O índice
    diz o nome e o título de cada documento; encontrar o parágrafo que fala de
    um assunto dentro de cem mil caracteres é aqui — com o arquivo e o número
    da linha, que é o endereço para pedir o documento inteiro.

    Ela existe porque o índice levava a **primeira frase** de cada documento, e
    isso custava 11.099 caracteres em toda pergunta para dar o começo, e não o
    meio. Quem devolve é `ajuda_projeto`, e não este módulo: duas montagens da
    mesma procura divergiriam no primeiro conserto.
    """
    if not str(termo or "").strip():
        raise FerramentaError(
            "Diga o que procurar. `procurar_nos_documentos` acha as linhas de "
            "um assunto dentro dos documentos do projeto — por exemplo "
            "«impressora», «matrícula de 32 dígitos», «CNIB».")
    quantas = int(limite) if int(limite or 0) > 0 else PROJ.LIMITE_DA_BUSCA
    return _cortar(PROJ.procurar_nos_documentos(termo, limite=quantas))


def _busca_na_base(ctx: Contexto, *, termo: str = "", limite: int = 0) -> str:
    """Procura um termo nas TRÊS fontes da base, numa chamada só.

    **É A FERRAMENTA QUE RESPONDE AO PEDIDO DO OFICIAL** — «não dá pra buscar
    as respostas de tudo para cada problema». Antes dela, a mesma dúvida podia
    custar três rodadas: uma nos documentos, outra nas regras, outra no que o
    oficial escreveu. Aqui as três são varridas na mesma leitura, e o resultado
    sai numa lista só, com o endereço de cada linha.

    **E ELA CUSTA MENOS PORQUE A BASE JÁ ESTÁ CARREGADA.** Quem lê os arquivos,
    quebra em seções e normaliza é `ajuda_base`, uma vez por processo; esta
    ferramenta só procura na memória. Medido nesta instalação: a mesma busca
    que custava 450 ms nos documentos custa dezenas de ms aqui — e é isso que
    permite chamá-la sem medo em pergunta de balcão.

    As duas ferramentas antigas — `procurar_nos_documentos` e `ler_regras` —
    continuam existindo, e não são caminho velho: a primeira é a que devolve o
    formato que a tela do projeto mostra, e a segunda abre uma seção pelo
    número. Esta é a de uso geral, e é a que se pede quando não se sabe onde
    está.
    """
    if not str(termo or "").strip():
        raise FerramentaError(
            "Diga o que procurar. `buscar_na_base` procura numa chamada só nos "
            "documentos do projeto, nas regras da casa e no que o oficial "
            "escreveu — por exemplo «carimbo que mente», «selo», «matrícula de "
            "32 dígitos».")
    quantas = int(limite) if int(limite or 0) > 0 else BASE.LIMITE_DA_BUSCA
    with ctx.db.connect() as con:
        con.row_factory = sqlite3.Row
        return _cortar(BASE.buscar_em_tudo(termo, limite=quantas, con=con))


def _le_regras(ctx: Contexto, *, secao: str = "", procura: str = "") -> str:
    """As regras desta casa — o índice, uma seção, ou as linhas de um assunto.

    **É A FERRAMENTA QUE RESPONDE «COMO SE DECIDE AQUI».** Sem argumento ela
    devolve o índice — número e título de cada seção —, que é o que permite
    pedir. Com `procura`, as linhas que falam de um termo, cada uma com a seção
    de onde saiu: é o caminho curto, e o mais usado. Com `secao`, o texto dela,
    cortado se for grande.

    Quem devolve o texto é `ajuda_regras`, e não este módulo: duas montagens do
    mesmo texto divergiriam no primeiro conserto — a lição da `normalizar_nome`
    pela enésima vez.
    """
    if procura:
        return REGRAS.procurar(procura)
    if secao:
        return REGRAS.ler(secao)
    if not REGRAS.disponivel():
        raise FerramentaError(
            "O arquivo das regras do projeto não está nesta instalação, então "
            "não há o que ler. Ele viaja com a atualização; se a atualização "
            "foi feita à mão, o arquivo ficou para trás.")
    carimbo = REGRAS.carimbo()
    linhas = [
        "As regras do projeto CartorioGestao — o arquivo que diz como se "
        "decide nesta casa.",
        f"Arquivo: {REGRAS.onde()}",
        (f"Ele diz de si mesmo: versão {carimbo['versao'] or '—'}"
         + (f", {carimbo['testes']} testes coletados" if carimbo["testes"] else "")
         + "."),
        "",
        "Estas são as seções. Peça uma pelo número ou por um pedaço do título, "
        "ou procure um assunto com `procura`.",
        "",
    ]
    for linha in REGRAS.indice_para_o_contexto(limite=100):
        linhas.append(linha)
    conferencia = REGRAS.resumo_da_conferencia(ctx.versao)
    if conferencia:
        linhas += ["", conferencia]
    return "\n".join(linhas)


def _lista_telas(ctx: Contexto) -> str:
    """As telas do sistema e a que módulo cada uma pertence."""
    with ctx.db.connect() as con:
        con.row_factory = sqlite3.Row
        mapa = MAPA.do_processo(ctx.app, con, versao=ctx.versao)
    return _cortar(MAPA.resumo(mapa))


# =========================================================== as de ESCRITA


def _anota_no_problema(ctx: Contexto, *, problema_id: int, nota: str,
                       estado: str = "EM_ANALISE", prova: str = "") -> str:
    """Grava o que o agente achou no problema. **ESCREVE.** Só acrescenta."""
    with ctx.db.transaction() as con:
        r = AP.anotar_desenvolvimento(
            con, int(problema_id), nota=nota, estado=estado, prova=prova,
            agora=ctx.agora, por=ctx.usuario or "agente")
        AG.registrar_mudanca(
            con, ctx.sessao_id, ferramenta="anotar_no_problema",
            alvo=f"problema #{int(problema_id)}",
            antes="", depois=f"{r['estado']}: {nota}",
            reversivel=False, agora=ctx.agora, criada_por=ctx.usuario)
    return (f"Anotei no problema #{int(problema_id)}, como "
            f"«{r['nome_do_estado']}». A situação do problema não mudou: quem "
            f"marca resolvido é o oficial, na tela dele.")


def _anota_achados(ctx: Contexto, *, chaves: str = "") -> str:
    """Põe na lista de problemas o que a conferência mediu. **ESCREVE.**

    Sem `chaves`, registra tudo o que a conferência achou. Com `chaves`, só as
    pedidas — para o agente não inundar a lista com o que já se sabe.
    """
    achados = _medir_a_casa(ctx)
    queridas = {c.strip() for c in str(chaves or "").split(",") if c.strip()}
    if queridas:
        achados = [a for a in achados if a["chave"] in queridas]
        faltando = queridas - {a["chave"] for a in achados}
        if faltando:
            raise FerramentaError(
                f"A conferência não achou nada com a(s) chave(s) "
                f"{', '.join(sorted(faltando))}. Chame a ferramenta de "
                f"conferência primeiro para ver as chaves de agora.")
    if not achados:
        return "A conferência não achou nada, então não houve o que registrar."
    with ctx.db.transaction() as con:
        r = AP.anotar_achados(con, achados, agora=ctx.agora,
                              versao=ctx.versao, usuario=ctx.usuario)
        AG.registrar_mudanca(
            con, ctx.sessao_id, ferramenta="registrar_achados",
            alvo="lista de problemas",
            antes="", depois=f"{r['novos']} novo(s), {r['repetidos']} repetido(s)",
            reversivel=False, agora=ctx.agora, criada_por=ctx.usuario)
    return (f"Registrei {r['achados']} achado(s): {r['novos']} viraram problema "
            f"novo e {r['repetidos']} já estavam anotados — nesses eu somei a "
            f"ocorrência, sem criar linha nova.")


def _definir_alcance(ctx: Contexto, *, modulo: str, alcance: str) -> str:
    """Abre ou fecha um módulo para os usuários. **ESCREVE.** Reversível."""
    chave = str(modulo or "").strip().upper()
    if chave not in ML.CHAVE_DA_CONFIGURACAO:
        raise FerramentaError(
            f"O alcance do módulo «{modulo}» não é controlado nesta instalação. "
            f"Os que são: {', '.join(sorted(ML.CHAVE_DA_CONFIGURACAO))}.")
    novo = str(alcance or "").strip().upper()
    if novo not in ML.ALCANCES:
        raise FerramentaError(
            f"«{alcance}» não é um alcance. Os que existem são "
            f"{', '.join(ML.ALCANCES)} — e o que cada um quer dizer está na "
            f"tela de configuração.")
    nome_na_config = ML.CHAVE_DA_CONFIGURACAO[chave]
    antes = ctx.db.get_setting(
        nome_na_config, ML.ALCANCE_DE_FABRICA.get(chave, ML.TODOS))
    if antes == novo:
        return f"O módulo {chave} já estava em {novo}; não mudei nada."
    with ctx.db.transaction() as con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (nome_na_config, novo))
        AG.registrar_mudanca(
            con, ctx.sessao_id, ferramenta="definir_alcance_do_modulo",
            alvo=nome_na_config, antes=antes, depois=novo,
            reversivel=True, agora=ctx.agora, criada_por=ctx.usuario)
    return (f"O módulo {chave} passou de {antes} para {novo}. Isso vale para "
            f"todos os computadores da serventia e não muda nenhum dado: o que "
            f"estava lavrado continua guardado.")


# ============================================================= o catálogo

FERRAMENTAS: tuple[Ferramenta, ...] = (
    Ferramenta(
        nome="estado_do_sistema",
        descricao=(
            "Como a instalação está agora: versão, quantos problemas anotados "
            "por situação, integridade do banco, chaves órfãs, disputas de "
            "escrita, alcance dos módulos controlados e quais provedores de IA "
            "têm chave informada. Comece por aqui quando a pergunta for «como "
            "está o sistema»."),
        esquema={"type": "object", "properties": {}},
        tipo=LEITURA, nomes_livres=True, executar=_le_estado),
    Ferramenta(
        nome="ler_codigo",
        descricao=(
            "Lê um trecho numerado de um arquivo do próprio sistema "
            "(.py, .html, .js, .css). Somente arquivos do Cartório Gestão: não "
            "lê nada fora dele. Devolve a conferência de sintaxe quando é "
            "Python."),
        esquema={"type": "object", "properties": {
            "caminho": {"type": "string",
                        "description": "ex.: ri_web.py ou templates/base.html"},
            "linha": {"type": "integer",
                      "description": "linha a centralizar (0 = começo)"}},
            "required": ["caminho"]},
        tipo=LEITURA, nomes_livres=False, executar=_le_codigo),
    Ferramenta(
        nome="buscar_codigo",
        descricao=(
            "Procura um texto no código do sistema e diz em que arquivo e linha "
            "ele aparece. Aceita texto simples ou expressão regular. É o jeito "
            "de saber onde uma função é chamada ou onde uma frase está escrita."),
        esquema={"type": "object", "properties": {
            "termo": {"type": "string", "description": "texto ou expressão"},
            "limite": {"type": "integer", "description": "máximo de achados"}},
            "required": ["termo"]},
        tipo=LEITURA, nomes_livres=False, executar=_busca_codigo),
    Ferramenta(
        nome="ver_esquema_do_banco",
        descricao=(
            "As tabelas desta instalação e as colunas de cada uma. Use antes de "
            "escrever uma consulta, para acertar os nomes."),
        esquema={"type": "object", "properties": {
            "tabela": {"type": "string",
                       "description": "vazio = todas as tabelas"}}},
        tipo=LEITURA, nomes_livres=False, executar=_le_esquema),
    Ferramenta(
        nome="consultar_banco",
        descricao=(
            "Uma leitura no banco, só SELECT ou WITH, com as colunas escritas. "
            "Não altera nada. Recusa nome de credencial e as tabelas de "
            "configuração de chaves."),
        esquema={"type": "object", "properties": {
            "consulta": {"type": "string", "description": "o SELECT"},
            "limite": {"type": "integer", "description": "máximo de linhas"}},
            "required": ["consulta"]},
        tipo=LEITURA, nomes_livres=True, executar=_consulta_banco),
    Ferramenta(
        nome="listar_problemas",
        descricao=(
            "A lista de problemas anotados pelo sistema e pelas pessoas, com "
            "situação, tela e a nota do desenvolvimento."),
        esquema={"type": "object", "properties": {
            "situacao": {"type": "string",
                         "description": "ABERTO, RESOLVIDO… vazio = todas"},
            "limite": {"type": "integer"}}},
        tipo=LEITURA, nomes_livres=True, executar=_le_problemas),
    Ferramenta(
        nome="ler_problema",
        descricao=(
            "Um problema inteiro: o que ficou escrito, onde aconteceu, a nota "
            "do desenvolvimento e o trecho do arquivo relacionado."),
        esquema={"type": "object", "properties": {
            "problema_id": {"type": "integer"}},
            "required": ["problema_id"]},
        # DADO DE PESSOA, E NÃO ESTRUTURA: o que este problema tem dentro é o
        # que gente escreveu — o título do defeito e o detalhe do ocorrido. É
        # onde um nome aparece sem rótulo, e é por isso que a passagem ampla
        # vale aqui. O trecho de código que vem junto perde as palavras em
        # maiúsculas; quem quiser o trecho limpo chama a leitura de código, que
        # é declarada como estrutura.
        tipo=LEITURA, nomes_livres=True, executar=_le_problema),
    Ferramenta(
        nome="conferir_a_casa",
        descricao=(
            "Mede a instalação e devolve o que está fora do lugar: banco, "
            "chaves órfãs, atos sem selo, pendências. Cada achado tem uma "
            "chave que pode ser registrada como problema."),
        esquema={"type": "object", "properties": {}},
        tipo=LEITURA, nomes_livres=True, executar=_conferencias),
    Ferramenta(
        nome="ler_documentacao",
        descricao=(
            "Os documentos do projeto (o que o sistema sabe sobre si mesmo), ou "
            "um deles por nome."),
        esquema={"type": "object", "properties": {
            "nome": {"type": "string",
                     "description": "nome do arquivo .md; vazio = o índice"}}},
        tipo=LEITURA, nomes_livres=False, executar=_le_documentacao),
    Ferramenta(
        nome="procurar_nos_documentos",
        descricao=(
            "Procura um termo DENTRO de todos os documentos do projeto e devolve "
            "as linhas que falam dele, cada uma com o arquivo e a linha. É o "
            "jeito de achar onde um assunto foi escrito sem ler os documentos "
            "um a um — e o que se pede quando não se sabe de qual documento é."),
        esquema={"type": "object", "properties": {
            "termo": {"type": "string",
                      "description": "ex.: impressora, CNIB, próclamas"},
            "limite": {"type": "integer",
                       "description": "máximo de linhas; vazio = 40"}},
            "required": ["termo"]},
        # DOCUMENTAÇÃO, E NÃO BANCO: a mesma escolha de `ler_documentacao` e
        # `ler_regras`. Os documentos citam nome de pessoa e de cliente em
        # exemplos, e a passagem fechada tira o que identifica pessoa e
        # preserva as sequências em maiúsculas, que aqui são nome de tabela e
        # de regra — `SD_SELOS`, `pt_titulos`.
        tipo=LEITURA, nomes_livres=False, executar=_procura_nos_documentos),
    Ferramenta(
        nome="ler_regras",
        descricao=(
            "As regras desta casa — o que a serventia decidiu e por quê. Sem "
            "argumento devolve o índice das seções; com `procura`, as linhas "
            "de um assunto; com `secao`, o texto dela. Use ANTES de responder "
            "sobre como o sistema se comporta, para responder com a decisão "
            "desta casa e não com a regra geral."),
        esquema={"type": "object", "properties": {
            "secao": {"type": "string",
                      "description": "número ou pedaço do título da seção"},
            "procura": {"type": "string",
                        "description": "termo a procurar nas regras"}}},
        # DOCUMENTAÇÃO, E NÃO BANCO: a mesma escolha de `ler_codigo` e
        # `ler_documentacao`. A passagem fechada tira o que identifica pessoa
        # (CPF, e-mail, telefone) e preserva as sequências em maiúsculas, que
        # aqui são NOME DE REGRA — `LAVRAR_SEM_SELO`, `SD_SELOS` — e mascarar
        # deixaria o texto ilegível, que é o diagnóstico que mente.
        tipo=LEITURA, nomes_livres=False, executar=_le_regras),
    Ferramenta(
        nome="buscar_na_base",
        descricao=(
            "A base de conhecimento desta casa: procura um termo numa chamada "
            "só nos documentos do projeto, nas regras da casa e no que o "
            "oficial escreveu, e devolve as linhas que falam dele com o "
            "endereço de cada uma. **Use ESTA antes de responder sobre como o "
            "sistema se comporta ou o que já foi decidido** — e não procure "
            "documento por documento: as três fontes já estão carregadas."),
        esquema={"type": "object", "properties": {
            "termo": {"type": "string",
                      "description": "ex.: carimbo que mente, selo, matrícula"},
            "limite": {"type": "integer",
                       "description": "máximo de linhas; vazio = 40"}},
            "required": ["termo"]},
        # DOCUMENTAÇÃO, E NÃO BANCO — a mesma escolha de `ler_regras` e
        # `procurar_nos_documentos`, que ela junta. Os verbetes são prosa que o
        # próprio oficial escreveu sobre o sistema, e a passagem fechada tira o
        # que identifica pessoa e preserva as sequências em maiúsculas, que
        # aqui são nome de regra e de tabela.
        tipo=LEITURA, nomes_livres=False, executar=_busca_na_base),
    Ferramenta(
        nome="listar_telas",
        descricao="As telas do sistema, com o módulo de cada uma.",
        esquema={"type": "object", "properties": {}},
        tipo=LEITURA, nomes_livres=False, executar=_lista_telas),
    Ferramenta(
        nome="anotar_no_problema",
        descricao=(
            "Grava no problema o que você apurou, com o estado do trabalho. "
            "Use «ATENDIDO» só quando houver onde conferir, e informe a prova. "
            "Não marca o problema como resolvido: isso é clique do oficial."),
        esquema={"type": "object", "properties": {
            "problema_id": {"type": "integer"},
            "nota": {"type": "string", "description": "o que foi apurado"},
            "estado": {"type": "string",
                       "description": "EM_ANALISE, ATENDIDO, PENDENTE…"},
            "prova": {"type": "string",
                      "description": "onde conferir; exigido em ATENDIDO"}},
            "required": ["problema_id", "nota"]},
        tipo=ESCRITA, nomes_livres=True, executar=_anota_no_problema),
    Ferramenta(
        nome="registrar_achados",
        descricao=(
            "Põe na lista de problemas o que a conferência mediu. Sem "
            "argumentos, registra tudo; com `chaves`, só as pedidas."),
        esquema={"type": "object", "properties": {
            "chaves": {"type": "string",
                       "description": "chaves separadas por vírgula"}}},
        tipo=ESCRITA, nomes_livres=True, executar=_anota_achados),
    Ferramenta(
        nome="definir_alcance_do_modulo",
        descricao=(
            "Abre ou fecha um módulo para os usuários: NINGUEM (fechado para "
            "todos), ADMIN (só o oficial) ou TODOS. É reversível, e não muda "
            "dado nenhum: só quem vê a tela."),
        esquema={"type": "object", "properties": {
            "modulo": {"type": "string", "description": "ex.: PROTESTO"},
            "alcance": {"type": "string", "enum": list(ML.ALCANCES)}},
            "required": ["modulo", "alcance"]},
        tipo=ESCRITA, nomes_livres=False, executar=_definir_alcance),
)

POR_NOME: dict[str, Ferramenta] = {f.nome: f for f in FERRAMENTAS}


def catalogo(*, escrita: bool) -> list[Ferramenta]:
    """As ferramentas que vão ser oferecidas ao provedor.

    **Ferramenta de escrita que não foi liberada não é oferecida** — nem sequer
    como opção recusável. Oferecer e recusar depois ensinaria o modelo a pedir
    o que não pode, e gastaria um turno por tentativa.
    """
    return [f for f in FERRAMENTAS if escrita or not f.e_escrita]


def esquemas(*, escrita: bool) -> list[dict]:
    """O catálogo no formato que o transporte espera. **Só calcula.**"""
    return [{"nome": f.nome, "descricao": f.descricao, "schema": f.esquema}
            for f in catalogo(escrita=escrita)]


# ------------------------------------------------ as ferramentas da AJUDA

# QUAIS DESTAS A AJUDA PODE USAR, E PARA QUEM.
#
# **A AJUDA NÃO ESCREVE, E NÃO VAI ESCREVER NESTA PASSADA.** Tudo o que está
# aqui é de LEITURA: a ajuda aconselha, e o ato é do delegatário. O que separa
# os dois grupos abaixo é outra coisa — o TAMANHO do que se lê.
#
# `consultar_banco` é SELECT livre no banco da serventia, e `ler_codigo` abre o
# programa da casa. A barreira de privacidade tira o dado de pessoa antes de
# qualquer coisa sair, mas ler qualquer tabela e ler o código-fonte não é o que
# o balcão faz — e **a ajuda pode ser aberta ao balcão com um clique**, sem
# programador no meio (`aj_config.perfis`). O perfil decide o CATÁLOGO, e o
# teto do dia NÃO muda com ele: quem lê mais não ganha mais gasto, senão abrir
# a ajuda para o balcão abriria junto a conta da serventia.
FERRAMENTAS_DA_AJUDA: tuple[str, ...] = (
    "estado_do_sistema",
    "listar_telas",
    "conferir_a_casa",
    "listar_problemas",
    "ler_problema",
    "ler_documentacao",
    # **PROCURAR NOS DOCUMENTOS É DO BALCÃO TAMBÉM.** Ela lê os mesmos
    # documentos que `ler_documentacao` — que já é de todos —, e é o caminho
    # para achar o trecho quando não se sabe de qual deles é. Deixá-la só para
    # o ADMIN faria o balcão ler documento por documento procurando o mesmo
    # parágrafo.
    "procurar_nos_documentos",
    # **A BUSCA NA BASE É DELA, E É A PRIMEIRA DO GRUPO.** Ela junta as duas
    # de baixo — documentos e regras — e mais o que o oficial escreveu, numa
    # chamada só. É a resposta ao pedido dele («não dá pra buscar as respostas
    # de tudo para cada problema»): uma rodada em vez de três, e o custo de
    # cada uma em dezenas de milissegundos, porque a base já está carregada.
    # Ler prosa da casa é o que o balcão mais precisa para não responder pela
    # regra geral — por isso ela é de todos, como as duas que ela junta.
    "buscar_na_base",
    # **AS REGRAS DA CASA SÃO DE TODOS, E ESSA É A DIFERENÇA DELAS.** As outras
    # leituras contam o que o sistema tem; esta conta **como se decide aqui** —
    # e quem está no balcão é justamente quem precisa dela para não responder
    # ao cliente pela regra geral. Ela não lê ato nenhum e não lê o banco: lê
    # um arquivo de prosa que esta casa escreveu. Por isso entra no grupo de
    # todos, e não no do ADMIN.
    "ler_regras",
)

FERRAMENTAS_DA_AJUDA_SO_ADMIN: tuple[str, ...] = (
    "ler_codigo",
    "buscar_codigo",
    "ver_esquema_do_banco",
    "consultar_banco",
)


def catalogo_da_ajuda(*, admin: bool) -> list[Ferramenta]:
    """O que a ajuda pode ler, conforme quem está na tela. **Só calcula.**

    **A FERRAMENTA DE ESCRITA FICA DE FORA SEMPRE, E POR DECISÃO, NÃO POR
    FILTRO.** As duas listas acima são de leitura hoje; se um dia alguém
    acrescentar uma de escrita a uma delas, o `not f.e_escrita` abaixo a barra
    — a lista não é a permissão, e a permissão não mora numa lista que se edita
    sem pensar.
    """
    nomes = set(FERRAMENTAS_DA_AJUDA)
    if admin:
        nomes |= set(FERRAMENTAS_DA_AJUDA_SO_ADMIN)
    return [f for f in FERRAMENTAS if f.nome in nomes and not f.e_escrita]


def esquemas_da_ajuda(*, admin: bool) -> list[dict]:
    """O catálogo da ajuda no formato do transporte. **Só calcula.**"""
    return [{"nome": f.nome, "descricao": f.descricao, "schema": f.esquema}
            for f in catalogo_da_ajuda(admin=admin)]


# ------------------------------------------------------------- a execução


def executar(ctx: Contexto, nome: str, argumentos: dict) -> dict:
    """Chama uma ferramenta e devolve o que ela mediu, já mascarado.

    Devolve `{"ferramenta", "conteudo", "erro"}`. **Não levanta por falha de
    ferramenta**: a falha é informação para o modelo, que é quem decide o que
    fazer com ela — e um turno perdido por argumento errado é caro. Levanta só
    quando o problema é de quem chamou.
    """
    ferramenta = POR_NOME.get(str(nome or "").strip())
    if ferramenta is None:
        return {"ferramenta": str(nome or ""), "erro": True,
                "conteudo": (
                    f"Não existe ferramenta «{nome}». As que existem: "
                    f"{', '.join(sorted(POR_NOME))}. Não invente nomes.")}
    if ferramenta.e_escrita:
        with ctx.db.connect() as con:
            ligada = AG.escrita_ligada(con)
        if not ligada:
            return {"ferramenta": ferramenta.nome, "erro": True,
                    "conteudo": (
                        "As ferramentas que MUDAM o sistema estão desligadas "
                        "nesta instalação. O que eu posso fazer agora é ler e "
                        "dizer o que vi — quem liga a escrita é o oficial, em "
                        "Administrativo. Faça o diagnóstico e diga a ele o que "
                        "deve ser mudado.")}

    dados = argumentos if isinstance(argumentos, dict) else {}
    try:
        bruto = ferramenta.executar(ctx, **dados)
    except TypeError as erro:
        return {"ferramenta": ferramenta.nome, "erro": True,
                "conteudo": (
                    f"Chamei a ferramenta com os argumentos errados ({erro}). "
                    f"O esquema dela é: {ferramenta.esquema}")}
    except ValueError as erro:
        # **AQUI HAVIA UMA LISTA ESCRITA À MÃO, E ELA ENVELHECEU — 15/09/2026.**
        #
        # Cada módulo novo trazia o seu erro e alguém o acrescentava nesta
        # linha: `FerramentaError`, `ProblemaError`, `AgenteError`. Ao construir
        # a leitura das regras da casa, o `RegraError` do módulo novo não estava
        # na lista — e pedir uma seção que não existe **derrubava a consulta com
        # rastreio de erro na cara de quem estava no balcão**, que é exatamente
        # o que esta função existe para impedir.
        #
        #   A LISTA NÃO PRECISA EXISTIR, e essa é a correção: **a casa já tem a
        #   regra escrita** — «erro de regra é subclasse de `ValueError`, com
        #   mensagem pronta para o balcão». Os quatro módulos de ferramenta
        #   (`agente_ferramentas`, `agente_provedores`, `ajuda_problemas` e
        #   `ajuda_regras`) declaram os seus assim, e há teste que exige isso de
        #   todo erro de ferramenta. Apanhar `ValueError` faz o contrato valer
        #   para o módulo que for escrito amanhã, sem que ninguém tenha de
        #   lembrar desta linha.
        #
        #   O que isto NÃO é: silêncio. A mensagem sobe para o modelo, que é
        #   quem decide o que fazer com ela — e o defeito de verdade aparece na
        #   conferência da casa e no console do agente, e não como consulta
        #   perdida.
        return {"ferramenta": ferramenta.nome, "erro": True,
                "conteudo": str(erro)}

    try:
        seguro = PRIV.sanitizar_para_modelo(bruto,
                                           nomes_livres=ferramenta.nomes_livres)
    except PRIV.PrivacidadeError as erro:
        return {"ferramenta": ferramenta.nome, "erro": True,
                "conteudo": (
                    f"O resultado desta ferramenta foi BLOQUEADO pela barreira "
                    f"de privacidade, e eu não vou vê-lo: {erro} A leitura "
                    f"tocou em dado de pessoa. Tente outro caminho, ou peça ao "
                    f"oficial para conferir no sistema.")}
    return {"ferramenta": ferramenta.nome, "erro": False,
            "conteudo": _cortar(seguro)}


# -------------------------------------------------------------- o desfazer


def _restaura_alcance(con: sqlite3.Connection, *, alvo: str, antes: str) -> None:
    """A volta de `definir_alcance_do_modulo`. **ESCREVE.**"""
    con.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(alvo), str(antes)))


DESFAZEDORES: dict[str, Callable[..., None]] = {
    "definir_alcance_do_modulo": _restaura_alcance,
}


def desfazer(db: Any, mudanca_id: int, *, agora: str, usuario: str) -> dict:
    """Volta uma mudança atrás. **ESCREVE.**

    Recusa em vez de fingir: mudança que já foi desfeita, mudança de ferramenta
    que não sabe voltar, e mudança marcada como não reversível. **Uma volta que
    não volta é pior que um botão que não existe** — ela dá a quem clica a
    impressão de ter consertado.
    """
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        linha = AG.ler_mudanca(con, int(mudanca_id))
        if not linha:
            raise FerramentaError(f"Não achei a mudança #{mudanca_id}.")
        mudanca = dict(linha)
        if mudanca.get("revertida_em"):
            raise FerramentaError(
                f"A mudança #{mudanca_id} já foi desfeita em "
                f"{mudanca['revertida_em']}, por {mudanca['revertida_por']}.")
        if not mudanca.get("reversivel"):
            raise FerramentaError(
                f"A mudança #{mudanca_id} ({mudanca['ferramenta']}) é só "
                f"acréscimo: ela acrescentou informação, e não há o que voltar "
                f"— desfazer seria apagar o que foi dito.")
        volta = DESFAZEDORES.get(str(mudanca["ferramenta"]))
        if volta is None:
            raise FerramentaError(
                f"Eu não sei voltar a ferramenta «{mudanca['ferramenta']}». "
                f"Das que sei: {', '.join(sorted(DESFAZEDORES))}.")
        volta(con, alvo=mudanca["alvo"], antes=mudanca["antes"])
        AG.marcar_revertida(con, int(mudanca_id), agora=agora,
                            revertida_por=usuario or "")
    return {"mudanca_id": int(mudanca_id), "ferramenta": mudanca["ferramenta"],
            "alvo": mudanca["alvo"], "voltei_para": mudanca["antes"]}

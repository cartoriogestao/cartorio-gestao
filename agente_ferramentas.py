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

import json
import re
import sqlite3

import banco_pg
import psycopg
from bd_nativo import banco as _banco_nativo
from collections.abc import Callable
from contextlib import contextmanager
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
PRAZO_DA_CONSULTA_MS = 15_000   # por consulta ao banco, contado pelo servidor

# OS NOMES QUE NÃO PODEM SAIR DO BANCO PARA O PROVEDOR.
#
# Eles valem sobre o TEXTO da consulta, e não sobre as colunas do resultado —
# porque o resultado é lido como texto, e não há como saber que coluna um
# `SELECT` trouxe sem perguntar o esquema antes. Recusar pelo texto é grosseiro
# e é suficiente: para diagnosticar, nenhuma destas palavras é necessária.
NOMES_PROIBIDOS = (
    "senha", "password", "hash", "salt", "token", "segredo", "secret",
    "api_key", "apikey", "credencial", "private",
    "passwd",       # a senha dos usuários do PostgreSQL, em `pg_shadow` (LX07)
)

# AS TABELAS QUE NÃO SE LEEM, e por quê: a primeira guarda as chaves de API dos
# robôs em texto claro. Um `SELECT` nela publicaria a credencial da casa no
# provedor — e a barreira de privacidade não a pegaria, porque uma chave de API
# não tem forma de CPF nem de e-mail. `wa_config` entrou nesta lista em LS03
# (19/10/2026): ela guarda o token e o segredo do WhatsApp (`access_token`,
# `caixa_segredo`) no VALOR da linha, sob a coluna `valor` — um nome de coluna
# que nenhuma das palavras de `NOMES_PROIBIDOS` alcança, do mesmo jeito das
# chaves de `robo_config`.
TABELAS_PROIBIDAS = ("robo_config", "ag_config", "wa_config")

# AS FUNÇÕES DO SERVIDOR QUE NÃO SE CHAMAM (LX07, 19/10/2026).
#
# No PostgreSQL um SELECT alcança o que não é o banco: o disco do servidor
# (`pg_read_file`, `pg_ls_dir`, `lo_export`), as outras conexões
# (`pg_terminate_backend`), a configuração (`set_config`, `pg_reload_conf`) e o
# relógio (`pg_sleep`). A transação só-leitura de `_ler_sem_escrever` não segura
# nenhuma delas, porque nenhuma grava em tabela — e o usuário da casa pode ser
# superusuário no PostgreSQL portátil, para quem todas estão liberadas.
# Três famílias da lista não são óbvias:
#   - a TRAVA DE SESSÃO (`pg_advisory_lock`) sobrevive ao ROLLBACK e volta ao
#     reservatório presa na conexão: pedida na chave da trava única, pararia
#     toda escrita da casa até alguém fechar a conexão;
#   - as que RODAM TEXTO COMO CONSULTA (`query_to_xml`, `ts_stat`, `ts_rewrite`)
#     e o NOME ESCRITO EM CÓDIGO (`U&"pg\005fsleep"`) passariam por cima da
#     lista inteira, com o nome montado aos pedaços;
#   - as que DESPEJAM A TABELA INTEIRA (`table_to_xml`…) são o `SELECT *` com
#     outro nome.
# Vale sobre o TEXTO, como as outras recusas, e pelo começo do nome: `pg_read`
# pega `pg_read_file` e `pg_read_binary_file`.
#
# CASA COMO CHAMADA, E FORA DOS LITERAIS (LX10, item 8 da revisão do LX07). O
# casamento pelo texto inteiro recusava `titulo LIKE '%copy %'` e a coluna
# `lo_x`, e a frase dizia «usa lo_», que não ajuda ninguém. Agora o nome só
# conta seguido de `(` (com espaço ou aspas no meio: `"pg_sleep" (1)`), e o
# que está dentro de um literal não conta (`_fora_dos_literais`). A recusa
# diz o nome que a consulta escreveu.
#
# Entraram em LX10 (item 9 da revisão do LX07), por efeito fora do banco:
#   - `pg_notify`: o aviso a quem escuta. O ROLLBACK do fim já o descarta
#     (medido), e a recusa diz o porquê antes;
#   - `pg_stat_reset*`: zera a estatística do servidor inteiro;
#   - `pg_rotate_logfile` e `pg_log_backend_memory_contexts`: escrevem no
#     log do servidor;
#   - `pg_export_snapshot`: entrega a fotografia da transação a outra conexão.
FUNCOES_DO_SERVIDOR = (
    "pg_read", "pg_ls_", "pg_stat_file", "pg_file_", "lo_",
    "pg_sleep", "set_config", "pg_terminate", "pg_cancel", "pg_reload",
    "pg_promote", "dblink", "pg_logdir", "pg_current_logfile",
    "pg_advisory", "pg_try_advisory",
    "pg_create_", "pg_drop_replication", "pg_replication_slot", "pg_copy_",
    "pg_logical_", "pg_switch_wal", "pg_backup_",
    "query_to_xml", "cursor_to_xml", "table_to_xml", "schema_to_xml",
    "database_to_xml", "ts_stat", "ts_rewrite",
    "pg_notify", "pg_stat_reset", "pg_rotate_logfile",
    "pg_log_backend_memory_contexts", "pg_export_snapshot",
)

# AS PALAVRAS DO SERVIDOR que não são chamada: os comandos (`COPY`, `NOTIFY`,
# `LISTEN`, `UNLISTEN`) e o nome escrito em código (`U&"pg\005fsleep"`, o
# `U&'…'`), que passaria por cima da lista inteira. Valem como palavra
# inteira, fora dos literais.
PALAVRAS_DO_SERVIDOR = ("copy", "notify", "listen", "unlisten", 'u&"', "u&'")

# OS PARÂMETROS DO SERVIDOR que dizem onde moram os arquivos dele. O caminho
# até eles é um literal (`current_setting('data_directory')`, `pg_settings
# WHERE name = 'hba_file'`), e por isso só estes valem também DENTRO do
# literal — como palavra inteira.
PARAMETROS_DO_SERVIDOR = ("data_directory", "config_file", "hba_file",
                          "ident_file")

# OS CATÁLOGOS DO SERVIDOR QUE NÃO SE LEEM (LS03, 19/10/2026), e por quê cada:
#   - `pg_stats` e `pg_statistic` guardam AMOSTRAS DOS VALORES de cada coluna:
#     depois de um ANALYZE, `histogram_bounds` de `users` traz o hash da senha
#     de todos os usuários (medido), sem que a consulta escreva nome de
#     credencial nenhum;
#   - `pg_authid` e `pg_shadow` guardam a senha dos usuários do PostgreSQL;
#   - `pg_user_mapping` e `pg_subscription` guardam senha de conexão.
# Vale sobre o TEXTO e pelo começo do nome (`pg_stats` pega `pg_stats_ext`),
# como `FUNCOES_DO_SERVIDOR`: são tabelas do sistema, cuja dependência o
# servidor não grava, e por isso a conferência pela vista provisória não as
# vê. Para diagnóstico ficam `pg_roles`, `pg_user` e `pg_stat_user_tables`.
#   - `pg_stat_get_` (LX14; M1 do LS03): `pg_stat_get_activity(NULL)` e as
#     irmãs devolvem o comando em curso de TODAS as conexões. A ponte manda os
#     valores escritos no texto do SQL (`ClientCursor`), e o comando de uma
#     escrita em curso leva o CPF, o teor — e, na troca de senha, o hash novo.
CATALOGOS_PROIBIDOS = (
    "pg_stats", "pg_statistic", "pg_authid", "pg_shadow", "pg_user_mapping",
    "pg_subscription", "pg_stat_get_",
)

# AS COLUNAS DO SERVIDOR QUE NÃO SE LEEM (LX14; M1 do LS03), pela mesma razão
# do `pg_stat_get_`: `pg_stat_activity.query` é o texto do comando em curso das
# outras conexões, com os valores dentro. Ela é recusada pelo que o servidor
# diz da consulta (o `pg_depend` a vê até renomeada no FROM, medido no LS03), e
# não pelo texto: o resto de `pg_stat_activity` — `pid`, `state`,
# `wait_event`, `query_start` — continua respondendo quem trava quem.
COLUNAS_DO_SERVIDOR_PROIBIDAS = frozenset({("pg_stat_activity", "query")})


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
        contagem = AP.contagem(con)
        tabelas = int(_banco_nativo(con).valor(
            "SELECT count(*) AS n FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "AND table_type = 'BASE TABLE'"))
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
        bd = _banco_nativo(con)
        nomes = [r["name"] for r in bd.ler(
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "AND table_type = 'BASE TABLE' ORDER BY table_name")]
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
                colunas = [r["column_name"] for r in bd.ler(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = %s ORDER BY ordinal_position", (nome,))]
            except sqlite3.Error:
                colunas = []
            linhas.append(f"{nome}: " + (", ".join(colunas) or "(sem colunas)"))
    return "\n".join(linhas)


# O QUE O TEXTO DA CONSULTA NÃO MOSTRA, O SERVIDOR MOSTRA — achados de LS03
# (19/10/2026).
#
# O guarda de texto recusa a coluna de credencial pelo NOME (`NOMES_PROIBIDOS`)
# e o `SELECT *` pelo texto. Quatro jeitos de ler uma credencial passavam por
# ele sem escrever nome nenhum, e os quatro foram medidos levando o hash ao
# provedor:
#   - a LINHA INTEIRA de `users`: `SELECT u FROM users u`, `row_to_json(u)`,
#     `u.*`, `SELECT "U" FROM users AS "U"`;
#   - a LINHA INTEIRA de uma VISTA: `SELECT s FROM pg_shadow s` trazia o hash
#     SCRAM da senha do usuário do PostgreSQL — a coluna é `passwd`, mas a
#     consulta não a escreve;
#   - a COLUNA RENOMEADA no FROM: `SELECT x.e FROM users AS x(a, b, c, d, e)`
#     lê a quinta coluna com o nome `e` — e até com o nome de outra coluna,
#     trocando a ordem da lista;
#   - o ORÁCULO: `WHERE u::text LIKE '...'` não devolve o hash, mas diz se ele
#     tem tal trecho, e cem perguntas o soletram.
# O sal e o hash não têm forma de CPF nem de e-mail, de modo que a barreira de
# privacidade também não os segura. Por isso quem responde agora é o servidor,
# antes de a consulta rodar (`_conferir_antes_de_ler`).
#
# A vista provisória que o servidor analisa tem nome fixo: ela nasce e morre
# dentro de uma transação desfeita, e por isso duas consultas não se encontram.
_VISTA_DA_CONFERENCIA = "cg_agente_consulta"

# O que a vista provisória REFERENCIA, pelo nome de verdade: o `pg_depend`
# guarda a coluna da tabela (o número dela), e não o apelido que a consulta lhe
# deu; e cada tabela ou vista citada aparece também sem coluna. `todas` são as
# colunas da tabela ou vista citada — é por elas que se sabe se a linha inteira
# dela leva credencial. A própria vista provisória também aparece.
_O_QUE_A_CONSULTA_REFERE = (
    "SELECT c.relname AS tabela, coalesce(a.attname, '') AS coluna, "
    "ARRAY(SELECT t.attname::text FROM pg_attribute t "
    "WHERE t.attrelid = c.oid AND t.attnum > 0 AND NOT t.attisdropped "
    "ORDER BY t.attnum) AS todas "
    "FROM pg_depend d JOIN pg_class c ON c.oid = d.refobjid "
    "LEFT JOIN pg_attribute a ON a.attrelid = d.refobjid "
    "AND a.attnum = d.refobjsubid "
    "WHERE d.classid = 'pg_rewrite'::regclass "
    "AND d.refclassid = 'pg_class'::regclass "
    "AND d.objid = (SELECT r.oid FROM pg_rewrite r "
    f"WHERE r.ev_class = to_regclass('pg_temp.{_VISTA_DA_CONFERENCIA}')) "
    "ORDER BY c.relname, a.attname")


def _e_credencial(nome: Any) -> bool:
    """Se o nome de uma coluna é de credencial (`NOMES_PROIBIDOS`)."""
    return any(p in str(nome or "").lower() for p in NOMES_PROIBIDOS)


def _do_servidor_proibida(tabela: Any, coluna: Any) -> bool:
    """Se é coluna do servidor que não sai (`COLUNAS_DO_SERVIDOR_PROIBIDAS`)."""
    return ((str(tabela or "").lower(), str(coluna or "").lower())
            in COLUNAS_DO_SERVIDOR_PROIBIDAS)


def _linhas_inteiras(texto: str) -> set[str]:
    """Os apelidos cuja LINHA INTEIRA aparece num SQL escrito pelo servidor.

    O servidor escreve a linha inteira sempre como `apelido.*` — `u.*::users`,
    `row_to_json(u.*)`, `(s.*)::text` —, e o apelido que não é minúsculo
    simples vem entre aspas (`"U".*`). O `*` de `count(*)` não leva ponto
    antes. O que está DENTRO de um literal não conta: `nome ~ 'SILVA.*'` é uma
    expressão regular, e recusá-la seria barrar uma consulta legítima.
    """
    achados: set[str] = set()
    nome = ""
    i, fim = 0, len(texto)
    while i < fim:
        c = texto[i]
        if c in "'\"":
            # literal ('...') ou nome entre aspas ("..."); a aspa dobrada é
            # a aspa escrita dentro dele
            pedaco = []
            i += 1
            while i < fim:
                if texto[i] == c:
                    if texto[i + 1:i + 2] == c:
                        pedaco.append(c)
                        i += 2
                        continue
                    break
                pedaco.append(texto[i])
                i += 1
            nome = "".join(pedaco) if c == '"' else ""
            i += 1
            continue
        if texto.startswith(".*", i) and nome:
            achados.add(nome)
            nome = ""
            i += 2
            continue
        nome = nome + c if (c.isalnum() or c in "_$") else ""
        i += 1
    return achados


def _cria_tabela(sql: str) -> bool:
    """Se a consulta é um `SELECT … INTO` — um CREATE TABLE que começa com SELECT.

    A RECUSA ERA DO SERVIDOR, E CHEGAVA TORTA (LS03, B7). A transação
    só-leitura a recusaria, mas antes dela vem a vista provisória, que não
    aceita `INTO` numa subconsulta: o modelo recebia «o banco recusou a
    consulta: syntax error», e não o «só leio» que lhe diz o que fazer. Ler a
    mensagem do servidor dependeria do idioma do PostgreSQL; o texto da
    consulta não depende.

    Conta a palavra INTO fora de literal e de nome entre aspas, menos a do
    `INSERT INTO` — essa é da CTE que escreve, e a recusa dela é a do plano,
    com a frase de sempre. Um `into` dentro de `'...'` ou de `"..."` é texto, e
    não comando.
    """
    sem_texto = re.sub(r"'(?:[^']|'')*'", " ", str(sql or ""))
    sem_texto = re.sub(r'"(?:[^"]|"")*"', " x ", sem_texto)
    palavras = re.findall(r"[^\W\d][\w$]*", sem_texto.lower())
    return any(p == "into" and (i == 0 or palavras[i - 1] not in ("insert", "merge"))
               for i, p in enumerate(palavras))


# O NOME NO SQL QUE O SERVIDOR ESCREVE: simples, ou entre aspas.
_NOME_NO_SQL = r'(?:"(?:[^"]|"")+"|[^\W\d][\w$]*)'
# As palavras do SQL que o `pg_get_viewdef` põe logo depois de um nome de
# tabela ou de um `)` — não são apelido. A lista não precisa ser completa: a
# palavra que faltar vira um apelido que não é de tabela nenhuma, e o apelido
# desconhecido é recusado (o lado seguro).
_PALAVRAS_DO_SQL = frozenset("""
    all and any array as asc at between by case collate cross current desc
    distinct else end escape except exists false fetch filter first for from
    full group groups having ilike in inner intersect is isnull join last
    lateral left like limit materialized natural not notnull null nulls of
    offset on only or order ordinality outer over partition range right row
    rows select similar some tablesample then ties true union using values
    when where window with within
""".split())


def _sem_aspas(nome: str) -> str:
    """O nome como o catálogo o guarda: sem as aspas, e com a aspa dobrada
    desfeita. O nome simples o `pg_get_viewdef` já escreve em minúsculas."""
    if nome.startswith('"') and nome.endswith('"'):
        return nome[1:-1].replace('""', '"')
    return nome


def _apelidos_do_from(texto: str) -> dict[str, set[str | None]]:
    """A quem cada apelido do SQL que o SERVIDOR escreveu se refere.

    Devolve `{apelido: {tabela, …}}`, e `None` no lugar da tabela quando o
    apelido é de outra coisa — subconsulta, junção, função, CTE. O
    `pg_get_viewdef` escreve o FROM sempre da mesma forma, e é dela que isto
    depende, e não do texto que o modelo mandou:
      - `FROM users u`, `JOIN aj_problemas p`, `, ONLY t`, `(users u JOIN`,
        `users x(c1, c2)`: o nome da tabela, e o apelido sem AS (o apelido de
        COLUNA é que leva AS); sem apelido, a tabela se chama pelo próprio
        nome. O que casa a mais (o primeiro argumento de uma função) só
        acrescenta um alvo ao apelido, e alvo a mais nunca libera nada;
      - `( SELECT … ) s`, `(users u JOIN …) j`, `row_to_json(u.*) x(x)`: o
        apelido depois do `)` é de algo que não é tabela;
      - `WITH t AS ( … )`: o nome da CTE também não é tabela.
    E ele já desfaz o apelido repetido (o `p` de dentro vira `p_1`): cada
    apelido diz uma coisa só.
    """
    sem_texto = re.sub(r"'(?:[^'\\]|''|\\.)*'", "''", str(texto or ""))
    apelidos: dict[str, set[str | None]] = {}

    def liga(apelido: str, alvo: str | None) -> None:
        apelidos.setdefault(_sem_aspas(apelido), set()).add(alvo)

    n = _NOME_NO_SQL
    for m in re.finditer(
            rf"(?:\bFROM|\bJOIN|,|\()\s*(?:ONLY\s+)?(?:{n}\.)?({n})(?![\w$.\"])"
            rf"(?:\s+({n})(?![\w$.\"]))?", sem_texto, re.I):
        tabela, apelido = m.group(1), m.group(2)
        if tabela.lower() in _PALAVRAS_DO_SQL:
            continue
        if not apelido or apelido.lower() in _PALAVRAS_DO_SQL:
            apelido = tabela
        liga(apelido, _sem_aspas(tabela))
    for m in re.finditer(rf"\)\s*({n})(?![\w$.\"])", sem_texto):
        if m.group(1).lower() not in _PALAVRAS_DO_SQL:
            liga(m.group(1), None)
    for m in re.finditer(
            rf"({n})(?:\s*\([^()]*\))?\s+AS\s+(?:NOT\s+)?(?:MATERIALIZED\s+)?\(",
            sem_texto, re.I):
        liga(m.group(1), None)
    return apelidos


def _nos_do_plano(no: Any):
    """Cada nó do plano, do de cima aos de baixo (subplanos e CTEs incluídos)."""
    if isinstance(no, dict):
        yield no
        for filho in no.get("Plans") or []:
            yield from _nos_do_plano(filho)


def _recusar_pelo_plano(plano: Any) -> None:
    """Recusa pelo PLANO: a escrita e a tabela proibida por trás de uma vista.

    - **A escrita** aparece como nó `ModifyTable` (a CTE com DELETE, UPDATE ou
      INSERT). A transação só-leitura já a recusaria; dita aqui, a recusa vem
      antes da vista provisória, que não aceita CTE que escreve, e com a frase
      de sempre.
    - **A tabela proibida por trás de uma vista**: o texto da consulta diz o
      nome da vista; o plano diz a tabela que ela lê (`Relation Name`).
    """
    raiz = plano[0].get("Plan", {}) if isinstance(plano, list) and plano else {}
    nos = list(_nos_do_plano(raiz))
    if any(no.get("Node Type") == "ModifyTable" for no in nos):
        raise FerramentaError(
            "Eu só leio o banco, e esta consulta tenta escrever: o plano dela "
            "tem um INSERT, UPDATE ou DELETE. Nada mudou. Para mudar o sistema "
            "existem as ferramentas próprias, que deixam rastro e podem ser "
            "desfeitas.")
    lidas = sorted({str(no.get("Relation Name") or "").lower() for no in nos}
                   & set(TABELAS_PROIBIDAS))
    if lidas:
        raise FerramentaError(
            f"A tabela {', '.join(lidas)} guarda chave de API ou token em texto "
            f"claro e não é lida pelo agente.")


def _recusar_pela_vista(cursor: Any, sql: str) -> None:
    """Recusa pelo que a consulta REFERENCIA, dito pelo servidor.

    A CONSULTA VIRA UMA VISTA PROVISÓRIA, e o servidor diz duas coisas dela:
      - o `pg_depend` guarda cada coluna de tabela que ela referencia — no
        SELECT, no WHERE, no ORDER BY, numa CTE ou numa subconsulta — pelo
        número da coluna, e não pelo apelido. É o que pega a coluna renomeada
        no FROM, que nem o texto nem o plano mostram;
      - o `pg_get_viewdef` devolve o SQL que ele entendeu, e nele toda linha
        inteira vem escrita como `apelido.*` — de tabela ou de vista, no SELECT
        ou no WHERE. A linha inteira é recusada quando a consulta cita tabela
        ou vista com coluna de credencial (`users`, `pg_shadow`); a de
        `aj_problemas` passa, porque é o mesmo que escrever as colunas dela.
    O `count(*)` não referencia coluna nenhuma, e passa.

    A VISTA NÃO RODA A CONSULTA: criar uma vista só analisa o texto. Ela vive
    numa transação que `_conferir_antes_de_ler` desfaz sempre, e a consulta
    vai entre parênteses, como subconsulta, para que coluna repetida
    (`p.id, c.id`) não seja recusada por ser repetida. As visões do
    `information_schema` passam linhas inteiras de `pg_attribute` às funções
    delas, mas isso é por dentro da visão, e o SQL da vista não o mostra.
    """
    cursor.execute(f"CREATE TEMP VIEW {_VISTA_DA_CONFERENCIA} AS "
                   f"SELECT 1 AS um FROM ({sql}) AS consulta")
    cursor.execute(_O_QUE_A_CONSULTA_REFERE)
    referidas = cursor.fetchall()
    tabelas = sorted({str(t).lower() for t, _, _ in referidas}
                     & set(TABELAS_PROIBIDAS))
    if tabelas:
        raise FerramentaError(
            f"A tabela {', '.join(tabelas)} guarda chave de API ou token em "
            f"texto claro e não é lida pelo agente.")
    proibidas = sorted({f"{t}.{c}" for t, c, _ in referidas
                        if c and _e_credencial(c)})
    if proibidas:
        raise FerramentaError(
            f"A consulta lê {', '.join(proibidas)}, que é coluna de credencial "
            f"— ainda que com outro nome. Isso não sai do servidor para "
            f"provedor nenhum.")
    do_servidor = sorted({f"{t}.{c}" for t, c, _ in referidas
                          if c and _do_servidor_proibida(t, c)})
    if do_servidor:
        raise FerramentaError(
            f"A consulta lê {', '.join(do_servidor)}, o texto do comando em "
            f"curso das outras conexões — com os valores escritos nele, CPF e "
            f"teor entre eles. Para saber quem trava quem, leia pid, state, "
            f"wait_event_type, wait_event e query_start.")
    com_credencial = sorted({str(t) for t, _, todas in referidas
                             if any(_e_credencial(c) or _do_servidor_proibida(t, c)
                                    for c in (todas or []))})
    if not com_credencial:
        return
    cursor.execute("SELECT pg_get_viewdef(%s::regclass) AS texto",
                   (f"pg_temp.{_VISTA_DA_CONFERENCIA}",))
    texto = str(cursor.fetchone()[0] or "")
    # SÓ A LINHA INTEIRA QUE PODE LEVAR CREDENCIAL É RECUSADA (LS03, B8). Antes,
    # bastava a consulta citar `users` para a linha inteira de QUALQUER apelido
    # ser recusada — `SELECT p FROM users u JOIN aj_problemas p …` caía por
    # causa do `u`, que nem era a linha pedida. Agora a linha inteira passa
    # quando o apelido é, com certeza, de uma tabela ou vista citada SEM coluna
    # de credencial. Apelido de junção, de subconsulta, de função ou de CTE não
    # se sabe o que carrega, e continua recusado — é o lado seguro.
    apelidos = _apelidos_do_from(texto)
    sem_credencial = {str(t) for t, _, todas in referidas
                      if not any(_e_credencial(c) for c in (todas or []))}
    sem_credencial -= set(com_credencial)
    perigosas = {a for a in _linhas_inteiras(texto)
                 if not apelidos.get(a)
                 or not apelidos[a] <= sem_credencial}
    if perigosas:
        raise FerramentaError(
            "A consulta leva a LINHA INTEIRA de uma tabela (por exemplo "
            "`SELECT t FROM t` ou `row_to_json(t)`), e com ela sairiam colunas "
            "que ninguém pediu — inclusive o sal e o hash da senha "
            f"({', '.join(com_credencial)}). Escreva as colunas que você quer, "
            f"uma a uma.")


def _conferir_antes_de_ler(pg: Any, sql: str) -> None:
    """A conferência pelo servidor, numa transação que é sempre desfeita.

    É uma transação À PARTE da leitura, e não a mesma: a vista provisória é um
    CREATE, que a transação só-leitura recusa. Nesta nada roda — o `EXPLAIN`
    sem `ANALYZE` só planeja e a vista só analisa —, o prazo vale também
    aqui, e o ROLLBACK do fim desfaz a vista. A leitura de verdade vem depois,
    na transação só-leitura de sempre, que continua sendo a garantia contra a
    escrita que o plano não mostra (a função que grava, o `nextval`).
    """
    with pg.cursor() as cursor, _desfeita(cursor, "BEGIN"):
        cursor.execute("SET LOCAL statement_timeout = "
                       f"'{int(PRAZO_DA_CONSULTA_MS)}ms'")
        cursor.execute("EXPLAIN (VERBOSE, FORMAT JSON) " + sql)
        bruto = cursor.fetchone()[0]
        _recusar_pelo_plano(json.loads(bruto) if isinstance(bruto, str)
                            else bruto)
        _recusar_pela_vista(cursor, sql)


@contextmanager
def _desfeita(cursor: Any, abertura: str, *, confirmar: bool = False):
    """Uma transação que termina em ROLLBACK, sem esconder o erro dela.

    O ROLLBACK DE UM `finally` PODIA TROCAR O ERRO (LX10, item 5 da revisão do
    LX07). Se a conexão cai no meio da consulta, o ROLLBACK também falha, e o
    erro dele subia no lugar do original: o modelo leria «a conexão está
    fechada» e não saberia o que aconteceu com a consulta. Aqui, com um erro
    já subindo, a falha do ROLLBACK é engolida, porque a conexão caída não tem
    transação a desfazer, e o erro que sobe é o de dentro. Sem erro dentro,
    a falha do ROLLBACK sobe, porque a conexão não pode voltar ao reservatório
    sem se saber em que estado ficou.

    Com `confirmar`, o fim sem erro é COMMIT (o GRANT do papel tem de ficar),
    e o fim com erro continua sendo ROLLBACK.
    """
    cursor.execute(abertura)
    try:
        yield
    except BaseException:
        try:
            cursor.execute("ROLLBACK")
        except psycopg.Error:
            pass        # o que conta é o erro de dentro, que sobe agora
        raise
    cursor.execute("COMMIT" if confirmar else "ROLLBACK")


# O PAPEL COM QUE O AGENTE LÊ (LX10, item 11 da revisão do LX07).
#
# O texto e a conferência de LS03 recusam a credencial pelo que a consulta
# ESCREVE e pelo que o servidor diz que ela REFERE. As duas camadas são
# listas de casos, e um caso que ninguém mediu passa. Este papel resolve na
# origem: a leitura do agente roda com `SET LOCAL ROLE cg_agente_leitura`, e
# o servidor não entrega ao papel o que ele não pode ver:
#   - as colunas de credencial (`password_hash`, `password_salt`…) ficam
#     fora do GRANT por coluna. Por isso `SELECT u`, `u.*`, `users.*`,
#     `row_to_json(u)` e `to_jsonb(u)` dão «permissão negada» (medido), e o
#     `pg_stats` não mostra a amostra delas;
#   - as tabelas de chave (`TABELAS_PROIBIDAS`) não têm GRANT nenhum;
#   - as VISTAS da casa, e as materializadas, também não têm GRANT: uma vista
#     roda com os direitos de quem a criou (a materializada guarda o que eles
#     leram), e por ela o papel leria a coluna que não pode ler;
#   - sem superusuário, o servidor nega `pg_read_file`, `pg_shadow`,
#     `pg_authid`, `current_setting('data_directory')` e o texto das consultas
#     dos outros em `pg_stat_activity` (medido).
#
# POR QUE UM PAPEL, E NÃO VISTAS `agente_*`: o agente escreve SQL contra as
# tabelas que ele lê no esquema, e vistas com outro nome o obrigariam a
# aprender um segundo esquema. O papel não muda nada do que o agente escreve.
#
# QUEM CRIA O PAPEL É ESTA FERRAMENTA, na primeira consulta, e não um passo
# de instalação: o usuário da casa no PostgreSQL portátil é o dono do cluster
# (`trust` em 127.0.0.1). É também esta ferramenta que acerta o GRANT quando
# nasce tabela ou coluna (`_preparar_o_papel`). Se o usuário da casa não
# puder criar o papel, a consulta é recusada, e não lida sem ele.
#
# O QUE O PAPEL NÃO FECHA, e por isso continua no texto:
#   - `set_config('role', …)`: o SET ROLE confere o usuário da SESSÃO, e não
#     o papel, e por esse caminho o agente voltaria a ser o dono do cluster;
#   - `pg_advisory_lock`: a trava de sessão não pede permissão nenhuma;
#   - `pg_notify`.
PAPEL_DO_AGENTE = "cg_agente_leitura"

# O cursor do servidor da leitura: ele entrega as linhas aos poucos.
_CURSOR_DA_LEITURA = "cg_agente_leitura"

# O que o papel ENXERGA hoje, tabela por tabela, nos schemas da conexão: o
# GRANT da tabela inteira, o das colunas, e se há outro privilégio além de
# SELECT, que o papel não deve ter.
_O_QUE_O_PAPEL_ENXERGA = (
    "SELECT n.nspname AS esquema, c.relname AS tabela, "
    "c.relkind::text AS tipo, "
    "ARRAY(SELECT a.attname::text FROM pg_attribute a "
    "WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
    "ORDER BY a.attnum) AS colunas, "
    "EXISTS (SELECT 1 FROM aclexplode(c.relacl) x WHERE x.grantee = r.oid "
    "AND x.privilege_type = 'SELECT') AS na_tabela, "
    "EXISTS (SELECT 1 FROM aclexplode(c.relacl) x WHERE x.grantee = r.oid "
    "AND x.privilege_type <> 'SELECT') AS outros, "
    "ARRAY(SELECT a.attname::text FROM pg_attribute a, aclexplode(a.attacl) x "
    "WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
    "AND x.grantee = r.oid ORDER BY a.attnum) AS nas_colunas "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "CROSS JOIN pg_roles r "
    "WHERE r.rolname = %s AND n.nspname = ANY (current_schemas(false)) "
    "AND c.relkind IN ('r', 'p', 'v', 'm', 'f') "
    "ORDER BY n.nspname, c.relname")


def _o_que_o_papel_deve_ver(tipo: str, tabela: str,
                            colunas: list[str]) -> tuple[bool, list[str]]:
    """`(tabela inteira?, colunas)` que o papel do agente deve poder ler.

    Tabela sem coluna de credencial: a tabela inteira. Com coluna de
    credencial: as outras colunas, uma a uma. A tabela de chave e a vista:
    nada (ver `PAPEL_DO_AGENTE`).

    A VISÃO MATERIALIZADA (`'m'`) É VISTA, E NÃO TABELA: ela guarda o que a
    consulta de quem a criou leu, e o nome da coluna dela é o apelido dessa
    consulta. `password_hash AS segredo` passaria pelo GRANT por coluna com o
    hash dentro (revisão da 2ª volta do LX10).
    """
    if tipo in ("v", "m") or tabela.lower() in TABELAS_PROIBIDAS:
        return False, []
    livres = [c for c in colunas if not _e_credencial(c)]
    if len(livres) == len(colunas):
        return True, []
    return False, livres


def _acertos_do_papel(cursor: Any) -> list[Any]:
    """Os GRANT e REVOKE que faltam para o papel ver o que deve, e só isso.

    Lista vazia é o caso de todo dia. Ela só tem comando quando nasceu
    tabela ou coluna desde a última consulta, ou quando é a primeira.
    """
    S = psycopg.sql
    papel = S.Identifier(PAPEL_DO_AGENTE)
    acertos: list[Any] = []
    cursor.execute("SELECT s AS esquema FROM unnest(current_schemas(false)) "
                   "AS s WHERE NOT has_schema_privilege(%s, s, 'USAGE') "
                   "ORDER BY s", (PAPEL_DO_AGENTE,))
    for (esquema,) in cursor.fetchall():
        acertos.append(S.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            S.Identifier(esquema), papel))
    cursor.execute(_O_QUE_O_PAPEL_ENXERGA, (PAPEL_DO_AGENTE,))
    for esquema, tabela, tipo, colunas, inteira, outros, nas_colunas \
            in cursor.fetchall():
        deve_inteira, deve_colunas = _o_que_o_papel_deve_ver(
            tipo, tabela, list(colunas or []))
        if (inteira, sorted(nas_colunas or []), outros) == (
                deve_inteira, sorted(deve_colunas), False):
            continue
        alvo = S.Identifier(esquema, tabela)
        # o REVOKE da tabela leva junto o GRANT das colunas, e o que fica é
        # só o que se concede abaixo
        acertos.append(S.SQL("REVOKE ALL ON {} FROM {}").format(alvo, papel))
        if deve_inteira:
            acertos.append(S.SQL("GRANT SELECT ON {} TO {}").format(
                alvo, papel))
        elif deve_colunas:
            acertos.append(S.SQL("GRANT SELECT ({}) ON {} TO {}").format(
                S.SQL(", ").join(S.Identifier(c) for c in deve_colunas),
                alvo, papel))
    return acertos


def _preparar_o_papel(pg: Any) -> None:
    """Cria o papel do agente, se falta, e acerta o que ele enxerga.

    NO DIA A DIA ISTO SÓ LÊ O CATÁLOGO: o papel já existe e o GRANT já está
    certo, e nenhuma transação de escrita se abre. Quando falta acerto, ele
    entra numa transação própria, CONFIRMADA (o GRANT tem de ficar), sob uma
    trava do assunto, para que duas consultas ao mesmo tempo não concedam a
    mesma tabela juntas, e com o prazo de sempre.

    O PAPEL É DO CLUSTER, e não do banco: outro banco do mesmo servidor pode
    criá-lo no mesmo instante. Quem perde essa corrida tenta de novo e o acha
    pronto.

    O papel não entra, não é superusuário e não herda privilégio de papel
    nenhum (`NOINHERIT`). Um papel com esse nome e mais poder do que isso é
    recusado, e não usado.
    """
    S = psycopg.sql
    papel = S.Identifier(PAPEL_DO_AGENTE)
    for tentativa in (1, 2):
        try:
            with pg.cursor() as cursor:
                cursor.execute(
                    "SELECT r.rolsuper OR r.rolcanlogin OR r.rolinherit OR "
                    "r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR "
                    "r.rolreplication AS demais, "
                    "pg_has_role(current_user, r.oid, 'MEMBER') AS membro "
                    "FROM pg_roles r WHERE r.rolname = %s", (PAPEL_DO_AGENTE,))
                papel_de_hoje = cursor.fetchone()
                if papel_de_hoje and papel_de_hoje[0]:
                    raise FerramentaError(
                        f"O papel {PAPEL_DO_AGENTE}, com que eu leio o banco, "
                        f"tem mais poder do que leitura (entra, é "
                        f"superusuário ou herda de outro papel). Não leio com "
                        f"ele. Quem cuida do servidor deve apagá-lo; eu o crio "
                        f"de novo, do jeito certo, na próxima consulta.")
                acertos = ([] if papel_de_hoje is None
                           else _acertos_do_papel(cursor))
                if papel_de_hoje is not None and papel_de_hoje[1] \
                        and not acertos:
                    return
                with _desfeita(cursor, "BEGIN", confirmar=True):
                    cursor.execute("SET LOCAL statement_timeout = "
                                   f"'{int(PRAZO_DA_CONSULTA_MS)}ms'")
                    cursor.execute("SELECT pg_advisory_xact_lock("
                                   "hashtext('agente_ferramentas.papel'))")
                    if papel_de_hoje is None:
                        cursor.execute(S.SQL(
                            "CREATE ROLE {} NOLOGIN NOINHERIT NOSUPERUSER "
                            "NOCREATEDB NOCREATEROLE NOREPLICATION "
                            "NOBYPASSRLS").format(papel))
                    cursor.execute(
                        "SELECT pg_has_role(current_user, %s, 'MEMBER')",
                        (PAPEL_DO_AGENTE,))
                    if not cursor.fetchone()[0]:
                        # o superusuário assume qualquer papel; o usuário que
                        # só cria papéis precisa ser membro deste
                        cursor.execute(S.SQL("GRANT {} TO CURRENT_USER")
                                       .format(papel))
                    for acerto in _acertos_do_papel(cursor):
                        cursor.execute(acerto)
            return
        except (psycopg.errors.UniqueViolation,
                psycopg.errors.DuplicateObject):
            if tentativa == 2:
                raise
        except psycopg.errors.InsufficientPrivilege as erro:
            raise FerramentaError(
                f"Não consigo ler o banco com segurança: o usuário da casa no "
                f"PostgreSQL não pode criar nem acertar o papel "
                f"{PAPEL_DO_AGENTE}, com que eu leio sem ver senha nem chave "
                f"({erro.diag.message_primary}). Sem ele eu não leio. Quem "
                f"cuida do servidor pode criá-lo (NOLOGIN NOINHERIT) e "
                f"conceder SELECT nas tabelas, menos nas colunas de "
                f"credencial.") from erro


def _ler_sem_escrever(con: Any, sql: str,
                      limite: int) -> tuple[list[str], list[tuple]]:
    """A consulta do agente, numa transação que o servidor não deixa escrever.

    O TEXTO DEIXOU DE BASTAR NO POSTGRESQL (LX07, achado da revisão do L024).
    No SQLite, começar com SELECT ou WITH era ser leitura. Aqui,
    `WITH x AS (DELETE FROM t RETURNING id) SELECT id FROM x` começa com WITH e
    apaga, e a conexão da ponte confirma cada comando sozinha. Quem garante
    agora é o servidor: o `BEGIN READ ONLY` recusa toda escrita, venha ela de
    uma CTE, de `SELECT ... INTO`, de `FOR UPDATE`, de `nextval` ou de uma
    função que grava; o `statement_timeout` corta a consulta que não acaba; e
    o `ROLLBACK` do fim, que roda sempre, devolve a conexão sem transação e sem
    o prazo — que é `SET LOCAL` para não ir com ela ao reservatório. A trava
    de sessão o ROLLBACK não solta, e por isso ela está em
    `FUNCOES_DO_SERVIDOR`.

    ANTES DE LER, O SERVIDOR CONFERE O QUE A CONSULTA ALCANÇA (LS03): a
    linha inteira, a coluna de credencial com outro nome e a tabela proibida
    por trás de uma vista são recusadas em `_conferir_antes_de_ler`, numa
    transação à parte e desfeita, antes de a consulta rodar.

    TRANSAÇÃO QUE JÁ VEM ABERTA É RECUSADA, e não misturada. Dentro dela, o
    ROLLBACK do fim desfaria o trabalho de quem a abriu, um COMMIT confirmaria
    o que o agente não sabe o que é, e deixá-la como está poria a leitura dele
    dentro de uma escrita alheia. No uso normal isso não acontece — cada
    ferramenta abre a sua conexão (ver `Contexto`) —, e por isso recusar não
    custa nada a ninguém.

    A LEITURA É COM O PAPEL DO AGENTE (LX10): `SET LOCAL ROLE` para
    `PAPEL_DO_AGENTE`, que não enxerga coluna de credencial nem tabela de
    chave. O que as conferências pelo texto e pelo servidor deixarem passar,
    o servidor recusa com «permissão negada». O `SET LOCAL` morre com o
    ROLLBACK, e a conexão volta ao reservatório com o usuário de antes.

    O CURSOR É O DO PSYCOPG, e não o `bd.ler`: o `bd` devolve `dict`, que junta
    numa só as colunas de mesmo nome (`p.id`, `c.id`), e a resposta tem de
    mostrar cada coluna que a consulta trouxe. E É UM CURSOR DO SERVIDOR (LX10,
    item 10 da revisão do LX07): o cursor comum trazia o resultado inteiro
    para a memória do programa antes de a tela cortar em `limite`, e uma
    consulta de milhões de linhas pesava até o prazo acabar. O do servidor
    entrega só as `limite + 1` linhas pedidas, e a que sobra é o que diz que
    há mais. A consulta roda como foi escrita, sem `LIMIT` montado em volta:
    o que roda é o que a conferência analisou.
    """
    pg = _banco_nativo(con)._pg
    estado = pg.info.transaction_status
    if estado != psycopg.pq.TransactionStatus.IDLE:
        raise FerramentaError(
            f"A conexão com o banco chegou ocupada ({estado.name}): há uma "
            f"transação aberta que não é minha. Não misturo a consulta com ela "
            f"— nem a confirmo nem a desfaço. Tente de novo.")
    try:
        _preparar_o_papel(pg)
        _conferir_antes_de_ler(pg, sql)
        with pg.cursor() as cursor, _desfeita(cursor, "BEGIN READ ONLY"):
            cursor.execute("SET LOCAL statement_timeout = "
                           f"'{int(PRAZO_DA_CONSULTA_MS)}ms'")
            cursor.execute(f"SET LOCAL ROLE {PAPEL_DO_AGENTE}")
            with pg.cursor(name=_CURSOR_DA_LEITURA) as leitor:
                leitor.execute(sql)
                colunas = [d[0] for d in (leitor.description or [])]
                linhas = (leitor.fetchmany(limite + 1) if leitor.description
                          else [])
    except psycopg.errors.InsufficientPrivilege as erro:
        raise FerramentaError(
            f"O banco não me deixa ler isto ({erro.diag.message_primary}). Eu "
            f"leio com um papel que não vê as colunas de credencial (o sal e o "
            f"hash da senha, os tokens), as tabelas de chave, as vistas da "
            f"casa nem as funções do servidor. Escreva só as colunas que você "
            f"quer, das tabelas, e não a linha inteira.") from erro
    except psycopg.errors.ReadOnlySqlTransaction as erro:
        raise FerramentaError(
            f"Eu só leio o banco, e esta consulta tenta escrever: o banco, "
            f"aberto só para leitura, a recusou ({erro.diag.message_primary}). "
            f"Nada mudou. Para mudar o sistema existem as ferramentas próprias, "
            f"que deixam rastro e podem ser desfeitas.") from erro
    except psycopg.errors.QueryCanceled as erro:
        raise FerramentaError(
            f"A consulta passou do prazo de {PRAZO_DA_CONSULTA_MS / 1000:g} s e "
            f"o banco a interrompeu. Peça menos de uma vez: um filtro no WHERE, "
            f"uma contagem no lugar da lista, um LIMIT.") from erro
    except psycopg.Error as erro:
        raise banco_pg._traduzir_erro(erro) from erro
    return colunas, linhas


def _fora_dos_literais(texto: str) -> str:
    """O SQL com cada literal trocado por `''`, para a busca de nome não o ler.

    Segue o que o PostgreSQL faz com o texto: `'...'` com a aspa dobrada
    dentro; `E'...'`, em que a barra escapa a aspa (`E'\\''`); e `$$...$$` ou
    `$tag$...$tag$`. O nome entre aspas duplas (`"pg_sleep"`) é nome, e não
    literal: fica como está, porque `"pg_sleep"(1)` é a chamada. Se esta
    leitura errasse a fronteira de um literal, uma chamada escrita depois dele
    sumiria da busca. Por isso ela imita o servidor, e não um atalho.

    COMENTÁRIO ELA NÃO LÊ: uma aspa dentro de `/* ' */` abriria aqui um
    literal que o servidor não vê, e a chamada depois dele sumiria. Hoje isso
    não acontece porque `_consulta_banco` recusa `--` e `/*` antes; quem tirar
    aquela recusa tem de ensinar o comentário a esta função.
    """
    def de_nome(c: str) -> bool:
        return c.isalnum() or c in "_$"

    saida: list[str] = []
    i, fim = 0, len(texto)
    while i < fim:
        c = texto[i]
        if c == '"':
            j = i + 1
            while j < fim:
                if texto[j] == '"':
                    if texto[j + 1:j + 2] == '"':
                        j += 2
                        continue
                    break
                j += 1
            saida.append(texto[i:j + 1])
            i = j + 1
            continue
        if c == "'":
            barra = (i > 0 and texto[i - 1] in "eE"
                     and not (i > 1 and de_nome(texto[i - 2])))
            j = i + 1
            while j < fim:
                if barra and texto[j] == "\\":
                    j += 2
                    continue
                if texto[j] == "'":
                    if texto[j + 1:j + 2] == "'":
                        j += 2
                        continue
                    break
                j += 1
            saida.append("''")
            i = j + 1
            continue
        if c == "$" and not (i > 0 and de_nome(texto[i - 1])):
            marca = re.match(r"\$(?:[^\W\d]\w*)?\$", texto[i:])
            if marca:
                fecho = texto.find(marca.group(0), i + len(marca.group(0)))
                saida.append("''")
                i = (fim if fecho < 0 else fecho + len(marca.group(0)))
                continue
        saida.append(c)
        i += 1
    return "".join(saida)


def _do_servidor(baixo: str) -> list[str]:
    """O que a consulta (já em minúsculas) chama do servidor, pelo nome escrito.

    A função conta como chamada: o nome (ou o começo dele, da lista), talvez
    entre aspas, e o `(` depois. A palavra conta inteira. As duas valem fora
    dos literais; o parâmetro do servidor vale também dentro deles (ver
    `PARAMETROS_DO_SERVIDOR`).
    """
    codigo = _fora_dos_literais(baixo)
    achados: list[str] = []
    for nome in FUNCOES_DO_SERVIDOR:
        for m in re.finditer(r'(?<![\w$])"?(' + re.escape(nome)
                             + r'[\w$]*)"?\s*\(', codigo):
            achados.append(m.group(1))
    for palavra in PALAVRAS_DO_SERVIDOR:
        if re.search(r"(?<![\w$])" + re.escape(palavra)
                     + (r"(?![\w$])" if palavra[-1].isalpha() else ""), codigo):
            achados.append(palavra)
    for parametro in PARAMETROS_DO_SERVIDOR:
        if re.search(r"(?<![\w$])" + re.escape(parametro) + r"(?![\w$])",
                     baixo):
            achados.append(parametro)
    return list(dict.fromkeys(achados))


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
      - **função do servidor** (`pg_read_file`, `pg_sleep`, `set_config`…) —
        no PostgreSQL um SELECT alcança o disco, o relógio, as outras conexões
        e a configuração do servidor, e nada disso é ler o banco
        (`FUNCOES_DO_SERVIDOR`). Conta a chamada, fora dos literais (LX10):
        `LIKE '%copy %'` e a coluna `lo_x` passam.
      - **catálogo do servidor com senha ou amostra de valor** (`pg_stats`,
        `pg_authid`…) — a amostra que o ANALYZE guarda traz o hash da senha
        sem que a consulta o nomeie (`CATALOGOS_PROIBIDOS`, LS03).

    E O QUE O TEXTO NÃO PEGA, O SERVIDOR PEGA: a consulta que passa por tudo
    isso é conferida pelo plano e pelas colunas que ela referencia — a linha
    inteira, a coluna de credencial renomeada no FROM, a tabela proibida por
    trás de uma vista (`_conferir_antes_de_ler`, LS03) — e só então roda numa
    transação só-leitura, com prazo, desfeita no fim e com o papel do agente,
    que não enxerga credencial (`_ler_sem_escrever`, LX10).
    As recusas pelo texto ficam porque dizem ao modelo o PORQUÊ, e as do
    servidor ficam porque o texto não pega tudo.
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
    if _cria_tabela(sql):
        raise FerramentaError(
            "Eu só leio o banco, e esta consulta tenta escrever: `SELECT … "
            "INTO` cria uma tabela nova com o resultado. Nada mudou. Para "
            "ler, tire o INTO; para mudar o sistema existem as ferramentas "
            "próprias, que deixam rastro e podem ser desfeitas.")
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
            f"A tabela {', '.join(passadas)} guarda chave de API ou token em "
            f"texto claro e não é lida pelo agente.")
    catalogos = [nome for nome in CATALOGOS_PROIBIDOS
                 if re.search(r"(?<![a-z0-9_$])" + re.escape(nome), baixo)]
    if catalogos:
        raise FerramentaError(
            f"A consulta lê {', '.join(catalogos)}, catálogo do servidor que "
            f"guarda senha, amostra dos valores das colunas ou o comando em "
            f"curso das outras conexões — o hash da senha dos usuários entre "
            f"eles. Para o diagnóstico há pg_roles, pg_user, "
            f"pg_stat_user_tables e as colunas de pg_stat_activity sem a query.")
    if "select *" in baixo and "information_schema" not in baixo:
        raise FerramentaError(
            "Escreva as colunas que você quer, em vez de `SELECT *`: assim a "
            "consulta não traz, sem querer, uma coluna que não podia sair.")
    do_servidor = _do_servidor(baixo)
    if do_servidor:
        raise FerramentaError(
            f"A consulta usa {', '.join(do_servidor)}, que é do servidor e não "
            f"do banco: o disco, o relógio, as outras conexões e a configuração "
            f"dele não se alcançam por aqui. Leia as tabelas, que é onde está o "
            f"diagnóstico.")

    with ctx.db.connect() as con:
        try:
            colunas, linhas = _ler_sem_escrever(con, sql, int(limite))
        except sqlite3.Error as erro:
            raise FerramentaError(
                f"O banco recusou a consulta: {erro}. Confira os nomes das "
                f"tabelas e das colunas com a ferramenta de esquema.") from erro
    if not colunas:
        return "A consulta não devolveu coluna nenhuma."
    saida = [" | ".join(colunas)]
    for linha in linhas[:max(int(limite), 0)]:
        celulas = []
        for valor in tuple(linha):
            texto = "NULL" if valor is None else str(valor)
            if len(texto) > LIMITE_DE_CELULA:
                texto = texto[:LIMITE_DE_CELULA] + "…"
            celulas.append(texto)
        saida.append(" | ".join(celulas))
    if len(linhas) > int(limite):
        saida.append(f"(parei em {limite} linhas; há mais)")
    return "\n".join(saida)


def _le_problemas(ctx: Contexto, *, situacao: str = "",
                  limite: int = 20) -> str:
    """A lista de problemas anotados, do mais recente para o mais antigo."""
    with ctx.db.connect() as con:
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
    with ctx.db.connect() as con:
        sem_confirmacao = AG.escrita_sem_confirmacao(con)
    if not sem_confirmacao:
        # O PADRÃO É PROPOR (LS03, M4): o modelo decide o que sugerir, e quem
        # muda o sistema é o oficial, com um clique na tela do agente. Nada
        # muda aqui — só a linha PROPOSTA, com o antes e o depois à vista.
        with ctx.db.transaction() as con:
            mudanca = AG.registrar_mudanca(
                con, ctx.sessao_id, ferramenta="definir_alcance_do_modulo",
                alvo=nome_na_config, antes=antes, depois=novo,
                reversivel=True, agora=ctx.agora, criada_por=ctx.usuario,
                proposta=True)
        return (f"Deixei PROPOSTO (mudança #{mudanca}): o módulo {chave} "
                f"passaria de {antes} para {novo}. NADA MUDOU AINDA — nesta "
                f"instalação a mudança só vale depois que o oficial a aplicar, "
                f"com um clique na tela do agente. Diga isso a ele na resposta.")
    with ctx.db.transaction() as con:
        _banco_nativo(con).escrever(
            "INSERT INTO settings(key, value) VALUES (%s, %s) "
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
            "dado nenhum: só quem vê a tela. Salvo configuração em contrário, "
            "a mudança fica PROPOSTA e só vale quando o oficial a aplicar."),
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
    _banco_nativo(con).escrever(
        "INSERT INTO settings(key, value) VALUES (%s, %s) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(alvo), str(antes)))


DESFAZEDORES: dict[str, Callable[..., None]] = {
    "definir_alcance_do_modulo": _restaura_alcance,
}


def _aplica_alcance(con: sqlite3.Connection, *, alvo: str, depois: str) -> str:
    """O clique que aplica `definir_alcance_do_modulo`. **ESCREVE.**

    Devolve o alcance que estava NO CLIQUE, que é o que o desfazer tem de
    restaurar. A chave sem linha em `settings` vale o alcance de fábrica, a
    mesma régua de `_definir_alcance`.
    """
    chave = next((k for k, v in ML.CHAVE_DA_CONFIGURACAO.items() if v == alvo),
                 None)
    if chave is None:
        raise FerramentaError(
            f"«{alvo}» não é mais um alcance controlado nesta instalação; "
            f"a proposta não se aplica.")
    if str(depois) not in ML.ALCANCES:
        raise FerramentaError(f"«{depois}» não é um alcance; nada mudou.")
    bd = _banco_nativo(con)
    linha = bd.um("SELECT value FROM settings WHERE key = %s FOR UPDATE",
                  (str(alvo),))
    antes = (linha["value"] if linha and linha["value"] not in (None, "")
             else ML.ALCANCE_DE_FABRICA.get(chave, ML.TODOS))
    _restaura_alcance(con, alvo=alvo, antes=depois)
    return str(antes)


#: O que sabe APLICAR uma mudança proposta (LS03, M4). Só a de alcance é
#: proposta: as outras duas escritas do agente só acrescentam uma nota, não
#: mudam o que o sistema faz, e por isso continuam diretas.
APLICADORES: dict[str, Callable[..., str]] = {
    "definir_alcance_do_modulo": _aplica_alcance,
}


def aplicar(db: Any, mudanca_id: int, *, agora: str, usuario: str) -> dict:
    """Aplica a mudança que o agente deixou PROPOSTA. **ESCREVE.**

    Recusa, como o desfazer, em vez de fingir: a que já foi aplicada, a que
    foi descartada e a que não se sabe aplicar. A trava do assunto vem antes
    da linha (`FOR UPDATE`): dois cliques ao mesmo tempo não aplicam duas vezes
    nem aplicam a que o outro clique acabou de descartar.
    """
    with db.transaction() as con:
        _banco_nativo(con).travar("ag_mudancas.aplicar_ou_desfazer")
        linha = AG.ler_mudanca(con, int(mudanca_id), para_mudar=True)
        if not linha:
            raise FerramentaError(f"Não achei a mudança #{mudanca_id}.")
        mudanca = dict(linha)
        if mudanca.get("revertida_em"):
            raise FerramentaError(
                f"A mudança #{mudanca_id} foi descartada em "
                f"{mudanca['revertida_em']}, por {mudanca['revertida_por']}; "
                f"ela não se aplica mais. Peça de novo ao agente, se for o caso.")
        if mudanca.get("situacao") != AG.PROPOSTA:
            raise FerramentaError(
                f"A mudança #{mudanca_id} já está aplicada"
                + (f" (desde {mudanca['aplicada_em']})"
                   if mudanca.get("aplicada_em") else "") + "; não há o que "
                f"aplicar de novo.")
        aplica = APLICADORES.get(str(mudanca["ferramenta"]))
        if aplica is None:
            raise FerramentaError(
                f"Eu não sei aplicar a ferramenta «{mudanca['ferramenta']}». "
                f"Das que sei: {', '.join(sorted(APLICADORES))}.")
        antes = aplica(con, alvo=mudanca["alvo"], depois=mudanca["depois"])
        AG.marcar_aplicada(con, int(mudanca_id), antes=antes, agora=agora,
                           aplicada_por=usuario or "")
    return {"mudanca_id": int(mudanca_id), "ferramenta": mudanca["ferramenta"],
            "alvo": mudanca["alvo"], "antes": antes,
            "apliquei": mudanca["depois"]}


def desfazer(db: Any, mudanca_id: int, *, agora: str, usuario: str) -> dict:
    """Volta uma mudança atrás. **ESCREVE.**

    Recusa em vez de fingir: mudança que já foi desfeita, mudança de ferramenta
    que não sabe voltar, e mudança marcada como não reversível. **Uma volta que
    não volta é pior que um botão que não existe** — ela dá a quem clica a
    impressão de ter consertado.
    """
    with db.transaction() as con:
        _banco_nativo(con).travar("ag_mudancas.aplicar_ou_desfazer")
        linha = AG.ler_mudanca(con, int(mudanca_id), para_mudar=True)
        if not linha:
            raise FerramentaError(f"Não achei a mudança #{mudanca_id}.")
        mudanca = dict(linha)
        if mudanca.get("revertida_em"):
            raise FerramentaError(
                f"A mudança #{mudanca_id} já foi desfeita em "
                f"{mudanca['revertida_em']}, por {mudanca['revertida_por']}.")
        if mudanca.get("situacao") == AG.PROPOSTA:
            # A PROPOSTA DESFEITA É DESCARTADA (M4): ela nunca mudou nada, e
            # não há o que voltar no sistema — só a linha fica dizendo quem a
            # recusou e quando, como a mudança desfeita.
            AG.marcar_revertida(con, int(mudanca_id), agora=agora,
                                revertida_por=usuario or "")
            return {"mudanca_id": int(mudanca_id),
                    "ferramenta": mudanca["ferramenta"],
                    "alvo": mudanca["alvo"], "voltei_para": mudanca["antes"],
                    "descartada": True}
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

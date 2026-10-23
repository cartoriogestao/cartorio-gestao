"""Os modelos dos papéis que esta casa emite — um catálogo só, das seis atribuições.

O RELATO #28 DO OFICIAL:

    «preciso de mais controle sobre os modelos de todos os atos, de todas
     atribuições. preciso ter controle geral sobre os modelos, em especial os
     cabeçalhos padrão de cada atribuição e ato, corpo, encerramento, eventual
     notas de rodapé»

O QUE SE MEDIU EM 29/08/2026
    Havia **duas realidades** convivendo:

      · **Quatro** modelos do Registro de Imóveis — cabeçalho, ficha, certidão
        e nota devolutiva — já liam de tabela, caindo no padrão do código
        quando ela estivesse vazia. E `ri_modelos` está com **zero linhas**:
        todos os quatro saem do código hoje.

      · **Cinco** não liam de lugar nenhum: o **recibo**, o **orçamento** e a
        **recepção** do caixa, o **traslado** das notas e o **comprovante de
        prenotação** do RI. Para mudar uma vírgula neles era preciso mexer no
        programa.

    E `nt_modelos` tem **333 linhas** — mas aquilo é outra coisa: são as
    minutas das escrituras, o CORPO DO ATO, com os campos da CENSEC. Não são o
    papel que a casa imprime.

O DESENHO, E ELE É O QUE A CASA JÁ FAZIA
    **O código é o piso; a tabela é o ajuste.** Sem linha na tabela, vale o
    modelo escrito no programa — que é como os quatro do RI já funcionavam
    (`modelo["corpo"] if modelo else MODELO_CERTIDAO_PADRAO`).

    Isso dá três coisas de graça:

    1. **nada se perde** — o padrão não é apagável, porque não mora no banco;
    2. **«voltar ao padrão» é apagar a linha**, e não recadastrar um texto que
       ninguém tem mais;
    3. **instalação nova já nasce funcionando**, sem carga de modelos.

POR QUE UMA TABELA SÓ, E NÃO UMA POR MÓDULO
    O pedido é «controle geral». Espalhar por `ri_modelos`, `cx_modelos`,
    `nt_modelos_de_papel` daria quatro telas e a pergunta «onde eu mudo o
    cabeçalho?» continuaria sem resposta — que é o relato.

    `ri_modelos` continua sendo lida como legado: ela tem zero linhas nesta
    casa, mas uma instalação que já tivesse ajustado alguma coisa ali não pode
    perder o ajuste ao subir de versão.

O PISO SAIU DO CÓDIGO — LF06A, 19/10/2026
    «Não deveríamos ter modelos no código; deveriam estar no banco, para
     editar com mais facilidade.» — o oficial.

    O texto de fábrica dos 41 papéis morava em constantes `MODELO_*`/`TERMO_*`
    espalhadas por catorze módulos. Agora:

      · ele mora na pasta `modelos_padrao/` — um `.txt` por papel, com os
        MESMOS bytes da constante (o teste-ouro confere cada um), e um `.json`
        com a ficha;
      · a pasta é copiada, a cada subida em que mudou, para uma BASE AUXILIAR
        no PostgreSQL (`schema_da_base()`, tabela `padroes`), separada do
        schema da casa — nada da casa mora lá, e por isso ela pode ser apagada
        e recriada inteira;
      · a busca é UMA: o ajuste ativo da casa → o padrão da base → erro claro
        («padrão X não carregado»). É `texto_do_papel`.

    O que NÃO mudou: o ajuste continua sendo da casa (`mo_elementos`, e o
    legado `mo_modelos`), «voltar ao padrão» continua sendo apagar a linha, e
    **atualização nunca sobrescreve ajuste** — ela troca a base, e a base não
    tem ajuste nenhum. O ajuste guarda a impressão digital do padrão sobre o
    qual foi feito (`base_impressao`), e a tela avisa quando o padrão mudou
    depois dele.
"""
from __future__ import annotations

import datetime
import difflib
import logging
import os
import sqlite3
import string
import threading

import banco_pg
from bd_nativo import banco
from modelos_papeis import pasta as PASTA
from typing import Any

try:  # o leitor da pasta e a tela funcionam sem o driver; a base, não
    import psycopg
    from psycopg import sql as _sql
    from psycopg.types.json import Jsonb
except ImportError:  # o servidor sem o driver nem sobe a casa no PostgreSQL
    psycopg = None

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------- o catálogo
#
# CADA LINHA E UM PAPEL QUE SAI DESTA CASA, e a lista foi MEDIDA: sao as dez
# constantes `MODELO_*` que existem no codigo, achadas por varredura em
# 29/08/2026. Nao ha nenhuma aqui que eu tenha imaginado.
#
# `padrao` diz onde MORAVA o texto de fabrica — modulo e nome da constante.
# Desde o LF06A o texto mora em `modelos_padrao/` (o campo `arquivo` diz
# qual), e o nome antigo continua respondendo: `ri_odt.MODELO_FICHA_PADRAO`
# devolve o padrao lido da base (`constante_antiga`), para quem ainda o
# importa. Um texto so, num lugar so — o que a tela mostra e o que o programa
# usa.
from modelos_papeis import CATALOGO  # noqa: E402 — catálogo por atribuição

# O `notas_selo.MODELO_PADRAO` FICOU DE FORA, e o motivo e a licao de sempre:
# **a mesma palavra em dois lugares nao quer dizer a mesma coisa**. Ele se
# chama `MODELO_`, mas nao e modelo de documento: e a URL que vai DENTRO do QR
# do selo — `https://selo.tjma.jus.br/#/resumo/{selo}`, o endereco da consulta
# daquele selo, medido no portal em 24/09/2026 —, com marcador do `str.format`
# e nao do Jinja.
#
# Posto neste catalogo, a tela o ofereceria como corpo de papel e a conferencia
# o passaria pelo Jinja, que e o motor errado: `{selo}` nao e sintaxe de Jinja,
# e a conferencia aprovaria um texto que o QR nao sabe montar. Ele ja tem
# lugar proprio na tela do selo.

POR_CHAVE: dict[str, dict] = {c["chave"]: c for c in CATALOGO}

# OS DOIS FORMATOS DE MARCADOR, e por que ha dois.
#
#   `JINJA` e o da casa inteira: `{{ a.numero }}`, com laco e condicao.
#   `CHAVES` e o do `str.format`: `{numero}`, sem logica nenhuma.
#
#   **Os termos do Registro Civil sao `CHAVES` de proposito.** Eles se montam
#   de frases inteiras que ja vem prontas — «, apresentou a DNV n.º 123» —, e
#   a decisao de a frase existir ou nao e do modulo, e nao do modelo: quem
#   escreve o termo nao deveria precisar de `{% if %}` para dizer que um
#   nascimento nao e de gemeos.
#
#   E o formato importa para a CONFERENCIA: passar um `{numero}` pelo Jinja
#   aprova um texto que o `str.format` nao sabe montar, e vice-versa. Foi o que
#   quase aconteceu com `notas_selo.MODELO_PADRAO`, que se chama modelo e e a
#   URL de dentro do QR.
JINJA = "JINJA"
# ---------------------------------------------------------------- tipagem
# Metadado ADITIVO (Fase 0/1 do plano de modelos). Não muda o piso nem o
# texto: só classifica o papel para a matriz, o inventário e a UI.
# Valores: TEXTO | MOLDE_ODT | MINUTA_ATO | DOC_AVULSO | MONTADO_POR_CAMPO
from modelos_papeis.tipagem import TIPOS_POR_CHAVE

for _entrada in CATALOGO:
    _tipo, _motivo = TIPOS_POR_CHAVE[_entrada["chave"]]
    _entrada["tipo"] = _tipo
    if _motivo:
        _entrada["motivo"] = _motivo


CHAVES = "CHAVES"


def formato_de(chave: str) -> str:
    """Em que formato aquele modelo escreve os claros. So calcula."""
    return _do_catalogo(chave).get("formato") or JINJA

# A tabela velha do RI. Ela tem ZERO linhas nesta casa; desde o LF06A ela nao
# e mais lida na hora do papel: a subida traz o que ela tiver para
# `mo_modelos`, como ajuste da casa (`trazer_ajustes_do_legado_ri`). O de-para
# e so destes quatro, que sao os que ela conhecia.
LEGADO_RI: dict[str, str] = {
    "CABECALHO": "RI_CABECALHO",
    "FICHA": "RI_FICHA",
    "CERTIDAO": "RI_CERTIDAO",
    "NOTA": "RI_NOTA",
}


class ModeloError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def _do_catalogo(chave: str) -> dict:
    """A linha do catálogo — ou a da PEÇA de um papel do catálogo.

    A peça (`RI_CERTIDAO__fecho`) não tem linha própria: ela é o texto de uma
    frase do papel, e herda dele a atribuição e o formato. Ver
    `docs/MODELOS_PADRAO.md`.
    """
    alvo = PASTA.chave_normal(chave)
    c = POR_CHAVE.get(alvo)
    if c:
        return c
    papel, sep, peca = alvo.partition(PASTA.SEPARADOR_DE_PECA)
    if sep and peca and papel in POR_CHAVE:
        return {**POR_CHAVE[papel], "chave": alvo, "peca_de": papel,
                "arquivo": f"{PASTA.PASTA_DOS_PADROES.name}/"
                           f"{POR_CHAVE[papel]['pasta']}/{alvo}.txt"}
    raise ModeloError(
        f"«{chave}» não é um papel que esta casa emita. Os que existem: "
        + ", ".join(f"{x['chave']} ({x['nome']})" for x in CATALOGO) + ".")


def marcador_do_miolo(chave: str) -> str:
    """O marcador que o molde daquele papel PRECISA carregar — ou ``""``.

    **UM PAPEL PODE SER UM MOLDE E UM MIOLO, E O `RI_CERTIDAO` E** — problema
    #75, 18/09/2026. O texto do tipo escolhido entra no molde onde o marcador
    manda, e essa emenda e a unica coisa que nao pode se perder: molde salvo sem
    ela sai com a abertura, a validade e a assinatura, e **sem o teor** — a
    certidao afirmando «cujo inteiro teor segue:» e nao reproduzindo nada.

    **QUEM DECIDE ISSO E O CATALOGO, e nao uma lista escrita aqui.** A declaracao
    `"miolo"` diz onde o marcador mora, e o texto vem LIDO de la, como o padrao:
    duas copias divergiriam no primeiro conserto, e este projeto ja pagou por
    isso com a `normalizar_nome`.
    """
    onde = _do_catalogo(chave).get("miolo")
    if not onde:
        return ""
    modulo, nome = onde
    import importlib
    return str(getattr(importlib.import_module(modulo), nome, "") or "")


def conferir_marcadores(chave: str, corpo: str) -> str:
    """O texto informado serve como molde daquele papel? Devolve o erro, ou ``""``.

    Chamada pelos DOIS lados que importam: a tela que grava (onde ha tempo de
    consertar) e a emissao (onde quem le o erro esta com o cliente na frente).
    Uma regra so, conferida com a mesma regua nos dois — conferir com uma e
    emitir com outra e como a tela passa a aprovar o que o papel nao sabe montar.
    """
    marcador = marcador_do_miolo(chave)
    if marcador and marcador not in str(corpo or ""):
        return (f"Este modelo é o MOLDE da certidão, e ele perdeu o ponto onde o "
                f"texto do tipo entra: falta `{marcador}`. Sem ele a certidão "
                "sairia com a abertura e a assinatura, e sem o teor. Reponha o "
                "marcador ou use «Voltar ao padrão».")
    return ""


# ================================================== a base auxiliar dos padrões
#
# UM SCHEMA PROPRIO, E NAO UMA TABELA NO DA CASA: nada da casa mora la, e por
# isso a subida pode APAGAR E RECRIAR a base inteira quando a pasta mudar, sem
# medo de levar junto um ajuste. O ajuste mora no schema da casa
# (`mo_elementos`, `mo_modelos`), e a atualizacao nao chega perto dele.
SCHEMA_DA_BASE = "modelos_padrao"

# A trava da carga. Varios processos sobem juntos (o servico, a tarefa
# agendada, os trabalhadores da suite): sem ela, dois apagariam e recriariam a
# mesma base ao mesmo tempo, e um deles estouraria no meio.
_TRAVA_DA_CARGA = "modelos_padrao.carga"
# Quanto a subida espera a carga de outro processo, ou um leitor preso, antes
# de desistir e servir a pasta (ver `_padroes`).
_ESPERA_DA_TRAVA = "30s"


def schema_da_base() -> str:
    """O nome do schema da base — e ele SEGUE A INSTALACAO.

    **DUAS INSTALACOES NO MESMO BANCO NAO PODEM DIVIDIR A BASE.** Medido em
    19/10/2026: o ensaio da virada subiu com `CG_PG_SCHEMA=ensaio_final` no
    mesmo servidor da `producao`. Com uma base so, cada subida apagaria a base
    da outra e a producao imprimiria o padrao do ensaio. Por isso, com o schema
    da casa fixado (`CG_PG_SCHEMA`, a mesma regra do `banco_pg`), a base e
    `modelos_padrao_<schema>`.

    Sem `CG_PG_SCHEMA` (os testes, a copia de desenvolvimento), o schema da
    casa muda a cada banco de teste, e a base e uma por BANCO: cada trabalhador
    da suite tem o seu banco (`cartorio_teste_<n>`), e os processos de um mesmo
    trabalhador rodam o mesmo codigo — a mesma pasta, a mesma marca.
    """
    fixo = (os.environ.get("CG_PG_SCHEMA") or "").strip()
    nome = f"{SCHEMA_DA_BASE}_{fixo}" if fixo else SCHEMA_DA_BASE
    return nome[:63]


def _agora() -> str:
    # Data se calcula no Python (regra da casa), e nao no SQL.
    return datetime.datetime.now().isoformat(timespec="seconds")


def carregar_base(*, schema: str | None = None, pasta=None,
                  forcar: bool = False) -> dict:
    """Copia a pasta dos padrões para a base, se ela mudou. Devolve a base lida.

    **APAGADA E RECRIADA INTEIRA, NUMA TRANSACAO SO**, e so quando a marca da
    pasta (o sha256 dos `.txt`, `.json` e `.odt` dela) nao bate com a gravada em
    `padroes_marca`. Quem le enquanto isso ve a base velha ou a nova, nunca
    uma pela metade. E a conferencia da marca acontece DEPOIS da trava: o
    segundo processo que sobe junto espera o primeiro, ve a marca nova e nao
    recarrega nada.

    Usa uma conexao PROPRIA, e nao a da rota: a base nao e da casa, nao entra
    na transacao da casa nem na gravacao do banco novo (`banco_pg`).

    Devolve ``{"schema", "marca", "carregou", "padroes": {chave: {...}}}``.
    """
    if psycopg is None or not banco_pg.ativo():
        raise ModeloError("A base dos padrões precisa do PostgreSQL (CG_PG_DSN).")
    schema = schema or schema_da_base()
    lida = PASTA.ler_pasta(pasta)
    s = _sql.Identifier(schema)
    carregou = False
    with psycopg.connect(banco_pg.dsn(), autocommit=False) as pg:
        with pg.cursor() as c:
            c.execute(f"SET LOCAL lock_timeout = '{_ESPERA_DA_TRAVA}'")
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                      (f"{_TRAVA_DA_CARGA}:{schema}",))
            c.execute("SELECT to_regclass(%s) IS NOT NULL",
                      (f'"{schema}".padroes_marca',))
            marca_gravada = None
            if c.fetchone()[0]:
                c.execute(_sql.SQL("SELECT marca FROM {}.padroes_marca "
                                   "ORDER BY carregada_em DESC LIMIT 1").format(s))
                linha = c.fetchone()
                marca_gravada = linha[0] if linha else None
            if forcar or marca_gravada != lida["marca"]:
                agora = _agora()
                c.execute(_sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(s))
                c.execute(_sql.SQL("CREATE SCHEMA {}").format(s))
                c.execute(_sql.SQL(
                    """CREATE TABLE {}.padroes (
                           chave text PRIMARY KEY,
                           atribuicao text NOT NULL,
                           nome text NOT NULL,
                           formato text NOT NULL,
                           corpo text NOT NULL,
                           campos jsonb NOT NULL DEFAULT '[]'::jsonb,
                           explica text,
                           impressao_digital text NOT NULL,
                           carregado_em text NOT NULL)""").format(s))
                c.execute(_sql.SQL(
                    """CREATE TABLE {}.padroes_marca (
                           marca text PRIMARY KEY,
                           quantos integer NOT NULL,
                           carregada_em text NOT NULL)""").format(s))
                padroes = sorted(lida["padroes"].values(), key=lambda p: p["chave"])
                c.executemany(_sql.SQL(
                    """INSERT INTO {}.padroes (chave, atribuicao, nome, formato,
                           corpo, campos, explica, impressao_digital, carregado_em)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""").format(s),
                    [(p["chave"], p["atribuicao"], p["nome"], p["formato"],
                      p["corpo"], Jsonb(p["campos"]), p["explica"],
                      p["impressao_digital"], agora) for p in padroes])
                c.execute(_sql.SQL(
                    "INSERT INTO {}.padroes_marca (marca, quantos, carregada_em) "
                    "VALUES (%s, %s, %s)").format(s),
                    (lida["marca"], len(padroes), agora))
                carregou = True
            c.execute(_sql.SQL(
                """SELECT chave, atribuicao, nome, formato, corpo, campos, explica,
                          impressao_digital
                     FROM {}.padroes ORDER BY chave""").format(s))
            nomes = [d.name for d in c.description]
            linhas = [dict(zip(nomes, r)) for r in c.fetchall()]
        pg.commit()
    if carregou:
        _LOG.info("Base dos padrões %s recarregada: %d papéis (marca %s).",
                  schema, len(linhas), lida["marca"][:12])
    return {"schema": schema, "marca": lida["marca"], "carregou": carregou,
            "padroes": {r["chave"]: r for r in linhas}}


def subir_base() -> dict | None:
    """A carga DA SUBIDA (`ri_schema.init_ri_schema`). Não derruba a subida.

    A base que não carregou (permissão, banco ocupado) não pode impedir a casa
    de abrir: o papel ainda sai, da pasta — que é a mesma fonte, byte a byte —,
    e a tela de Modelos diz que a base não carregou. O erro fica no log.
    """
    if psycopg is None or not banco_pg.ativo():
        return None
    try:
        carregada = carregar_base()
    except Exception as erro:                       # noqa: BLE001 — vai ao log
        _LOG.warning("A base dos padrões não carregou na subida: %s", erro)
        return None
    # o que a subida leu já vale para este processo: o primeiro papel não
    # precisa ir à base de novo
    with _TRAVA_DA_LEITURA:
        _LIDO[_chave_da_leitura()] = {"padroes": carregada["padroes"],
                                      "origem": "base", "erro": None}
    return carregada


# O QUE ESTE PROCESSO LEU DA BASE, uma vez por processo e por base. O papel não
# vai ao banco a cada emissão para buscar um texto que só muda numa atualização
# — e uma atualização reinicia o serviço.
_LIDO: dict[str, dict] = {}
_TRAVA_DA_LEITURA = threading.Lock()


def _chave_da_leitura() -> str:
    return f"{banco_pg.dsn()}|{schema_da_base()}|{PASTA.PASTA_DOS_PADROES}"


def _padroes() -> dict:
    """Os padrões que valem neste processo: `{"padroes", "origem", "erro"}`.

    `origem` é `"base"` — o normal — ou `"pasta"`: sem PostgreSQL (ferramenta
    avulsa), ou com a base fora do ar. A pasta é a fonte de onde a base é
    carregada, os mesmos bytes; servir dela é o piso do piso, e a tela de
    Modelos mostra o `erro` para ninguém achar que a base está de pé.
    """
    chave = _chave_da_leitura()
    lido = _LIDO.get(chave)
    if lido is not None:
        return lido
    with _TRAVA_DA_LEITURA:
        lido = _LIDO.get(chave)
        if lido is not None:
            return lido
        if psycopg is None or not banco_pg.ativo():
            lido = {"padroes": PASTA.ler_pasta()["padroes"], "origem": "pasta",
                    "erro": None}
        else:
            try:
                lido = {"padroes": carregar_base()["padroes"], "origem": "base",
                        "erro": None}
            except Exception as erro:               # noqa: BLE001 — vai à tela
                _LOG.warning("Base dos padrões fora do ar; servindo a pasta: %s",
                             erro)
                lido = {"padroes": PASTA.ler_pasta()["padroes"],
                        "origem": "pasta", "erro": f"{type(erro).__name__}: {erro}"}
        _LIDO[chave] = lido
        return lido


def esquecer_padroes() -> None:
    """Esquece o que este processo leu — para quem recarregou a base agora."""
    with _TRAVA_DA_LEITURA:
        _LIDO.clear()
    PASTA.esquecer()


def situacao_da_base() -> dict:
    """De onde os padrões estão saindo neste processo — para a tela."""
    lido = _padroes()
    return {"origem": lido["origem"], "erro": lido["erro"],
            "schema": schema_da_base(), "quantos": len(lido["padroes"]),
            "problemas": PASTA.ler_pasta()["problemas"]}


def _padrao(chave: str) -> dict:
    c = _do_catalogo(chave)
    p = _padroes()["padroes"].get(c["chave"])
    if not p:
        raise ModeloError(
            f"O padrão «{c['chave']}» não está carregado na base de modelos "
            f"({schema_da_base()}): falta o arquivo {c['arquivo']} na pasta do "
            "programa, ou ele está com defeito. Sem padrão e sem ajuste da "
            "casa, este papel não sai — reinstale a atualização ou grave um "
            "ajuste em Administrativo → Modelos.")
    return p


def padrao_de(chave: str) -> str:
    """O texto de fabrica daquele papel, LIDO DA BASE. So le.

    **ATE O LF06A ELE ERA LIDO DA CONSTANTE DO MODULO** (`ri_odt.
    MODELO_FICHA_PADRAO`...). O texto saiu do codigo e foi para a pasta
    `modelos_padrao/`, de onde a subida o carrega na base — com os mesmos
    bytes, e e o teste-ouro que confere.

    Continua sendo UM texto num lugar so: a tela mostra este, o papel imprime
    este, e o nome antigo da constante devolve este (`constante_antiga`).
    """
    return str(_padrao(chave)["corpo"])


def e_texto_de_fabrica(texto: Any) -> bool:
    """Este texto é, byte a byte, o padrão de fábrica de algum papel? Só lê.

    É A RÉGUA DO `html_sem_script` NOS PAPÉIS EDITÁVEIS (revisão de segurança
    da 3.7.0, 22/10/2026, achado A7): o papel que sai do texto de fábrica sai
    como saía; o que sai de um AJUSTE da casa — gravado na tela de Modelos,
    que o papel USER alcança, e aberto depois no navegador do oficial com
    `|safe` — passa pelo filtro que tira o que executa. Comparar o TEXTO, e
    não perguntar à tabela, é o que permite decidir onde só o texto chega
    (`ri_web.render_modelo` recebe o corpo e não a chave).
    """
    t = str(texto or "")
    return any(t == str(p.get("corpo") or "")
               for p in _padroes()["padroes"].values())


def sem_o_que_executa(texto_do_modelo: Any, html_montado: Any) -> str:
    """O papel montado — filtrado SE o modelo não é o de fábrica. Só calcula.

    O filtro (`html_sem_script.limpar`) deixa parágrafo, negrito, tabela,
    `style` e imagem em `data:image` (o QR do carimbo é PNG assim); tira
    `script`, `svg`, os `on…` e os endereços que levam a script, ao disco ou
    à rede. O padrão de fábrica NÃO passa por ele, de propósito: ele sai byte
    a byte como saía, e é o que o teste-ouro dos padrões confere.
    """
    html_montado = str(html_montado or "")
    if e_texto_de_fabrica(texto_do_modelo):
        return html_montado
    import html_sem_script as HSS
    return HSS.limpar(html_montado)


def impressao_digital_de(chave: str) -> str:
    """O sha256 do padrão de hoje. É o que o ajuste guarda em `base_impressao`."""
    return str(_padrao(chave)["impressao_digital"])


def arquivo_do_padrao(chave: str) -> str:
    """Onde o padrão mora na pasta do programa — é o que a tela mostra."""
    return str(_do_catalogo(chave)["arquivo"])


def constante_antiga(modulo: str, nome: str) -> str:
    """O texto que `modulo.nome` guardava — agora lido da base.

    **O NOME ANTIGO CONTINUA RESPONDENDO**, e é de propósito: quem ainda
    escreve `ri_odt.MODELO_FICHA_PADRAO` (um teste, uma ferramenta) recebe o
    MESMO texto que o papel imprime, e não uma cópia que ficou para trás. É o
    `__getattr__` de cada módulo que chama isto; nome que não é de papel
    continua sendo `AttributeError`, como sempre foi.
    """
    for c in CATALOGO:
        if tuple(c["padrao"]) == (modulo, nome):
            return padrao_de(c["chave"])
    raise AttributeError(f"module {modulo!r} has no attribute {nome!r}")


def texto_do_papel(con: sqlite3.Connection, chave: str) -> str:
    """O texto que vale hoje para aquele papel. A BUSCA ÚNICA. Só lê.

        1. o ajuste ATIVO da casa (`mo_elementos`, e o legado `mo_modelos`);
        2. o padrão da base (`padrao_de`);
        3. erro claro — «padrão X não carregado» —, e não folha em branco.

    É `corpo_de` com outro nome, e o nome é para quem vem depois (LF06B em
    diante): o módulo que hoje monta um papel no código troca o texto dele por
    esta chamada. Aceita também a PEÇA de um papel (`<CHAVE>__<peca>`).
    """
    return corpo_de(con, chave)


def conferir_claros(texto: str, conhecidos) -> str:
    """O que há de errado nos claros `{nome}` de um texto CHAVES, ou ``""``. Só calcula.

    **UMA RÉGUA, NOS DOIS LADOS** (LF06G): a tela que grava confere com ela, e
    o montador que preenche também (`preencher`). O claro que o montador não
    conhece estoura no `str.format` como `KeyError` — com o cliente na frente,
    e sem dizer qual. Aqui ele vem com o nome, e antes.

    Só NOME de claro: `{a.b}` e `{a[0]}` o `str.format` resolveria por
    atributo e por índice, e o papel imprimiria o que nenhum modelo pediu.
    """
    corpo = str(texto or "")
    for marca in ("{{", "{%"):
        if marca in corpo:
            return (f"O texto usa «{marca}», que é a marcação Jinja das outras "
                    "atribuições. Neste papel o claro se escreve entre chaves "
                    "simples, assim: {nome}.")
    try:
        pedidos = [n for _, n, _, _ in string.Formatter().parse(corpo)
                   if n is not None]
    except ValueError as erro:
        return f"Há um claro mal escrito ({erro}). Cada claro se escreve {{assim}}."
    validos = set(conhecidos)
    ruins = sorted({n for n in pedidos
                    if not n.isidentifier() or n not in validos})
    if ruins:
        # o papel sem claro nenhum (o fecho do teor, a autenticação — LF06D)
        # não pode terminar o recado em «Os que ele tem: .»
        return ("O texto pede claros que este papel não tem: "
                + ", ".join(f"«{{{n}}}»" for n in ruins)
                + (". Os que ele tem: "
                   + ", ".join(f"{{{n}}}" for n in sorted(validos)) + "."
                   if validos else ". Este papel não tem claro nenhum."))
    return ""


def preencher(chave: str, texto: str, valores: dict[str, Any]) -> str:
    """O texto de um papel CHAVES (ou de uma peça dele), com os claros preenchidos.

    Claro que o papel não tem vira `ModeloError` com o nome do papel e o do
    claro — a frase que o balcão consegue ler —, e não o `KeyError` cru do
    `str.format`. Quem confere é `conferir_claros`, a mesma régua da tela.
    """
    erro = conferir_claros(texto, valores)
    if not erro:
        try:
            return str(texto).format(**valores)
        except (KeyError, IndexError, ValueError, AttributeError) as falha:
            # o claro escondido dentro da formatação (`{a:{b}}`) escapa da
            # régua de cima, e não pode escapar como erro cru
            erro = f"o claro {falha} não se preenche."
    raise ModeloError(
        f"O modelo «{chave}» não monta: {erro} Ajuste-o em Administrativo "
        "→ Modelos, ou use «Voltar ao padrão».")


class Textos:
    """Os textos de UMA montagem — cada papel e cada peça lido uma vez. LF06D.

    **O MONTADOR DE TEXTO NÃO CONHECE A CONEXÃO, E NÃO PRECISA.** Os das Notas
    (`notas_teor.montar`, `notas_schema.texto_reconhecimento`…) são funções
    puras, e uma frase do teor passa por dez peças. Com `con`, cada peça vem da
    busca única (`texto_do_papel`: o ajuste da casa → a base); sem `con` — o
    teste, a ferramenta avulsa —, do padrão da base. E a mesma peça pedida duas
    vezes na mesma montagem não volta ao banco.

    `con` também pode ser QUEM ABRE a conexão (`db.connect`, numa rota que não
    tem uma aberta na hora de montar o papel): cada texto lido abre a sua e a
    devolve — e só na primeira vez que é pedido.

    **BANCO SEM AS TABELAS DO AJUSTE NÃO TEM AJUSTE**, e vale o padrão: é o
    teste que cria só o esquema das Notas, ou a ferramenta avulsa. Pergunta-se
    se a tabela existe — uma vez por montagem — em vez de consultá-la e
    apanhar o erro: no PostgreSQL a consulta que falha derruba a transação de
    quem chamou, e o ato que ia ser lavrado junto cairia com ela.
    """

    def __init__(self, con: Any = None) -> None:
        self.con = con
        self._lidos: dict[str, str] = {}
        self._tem_ajuste: bool | None = None

    def _da_casa(self, con: Any, alvo: str) -> str:
        if self._tem_ajuste is None:
            bd = banco(con)
            self._tem_ajuste = (bd.tem_tabela("mo_elementos")
                                and bd.tem_tabela("mo_modelos"))
        return texto_do_papel(con, alvo) if self._tem_ajuste else padrao_de(alvo)

    def __call__(self, chave: str) -> str:
        alvo = PASTA.chave_normal(chave)
        if alvo not in self._lidos:
            if self.con is None:
                self._lidos[alvo] = padrao_de(alvo)
            elif callable(self.con) and not hasattr(self.con, "cursor"):
                with self.con() as aberta:
                    self._lidos[alvo] = self._da_casa(aberta, alvo)
            else:
                self._lidos[alvo] = self._da_casa(self.con, alvo)
        return self._lidos[alvo]

    def preencher(self, chave: str, /, **valores: Any) -> str:
        """O texto de `chave`, com os claros `{nome}` (formato CHAVES) preenchidos.

        `chave` é só-posicional: um claro pode se chamar `{chave}`.
        """
        return preencher(chave, self(chave), valores)


def textos(con: Any = None) -> Textos:
    """Os textos de uma montagem. Aceita a conexão, quem a abre, nada, ou um
    `Textos` já aberto."""
    return con if isinstance(con, Textos) else Textos(con)


# AS MINUTAS DE FÁBRICA DAS NOTAS — LF06D, 19/10/2026. São o corpo do ato
# (`notas_modelos`), e não um papel da tela de Modelos: o ajuste da casa delas
# mora em `nt_modelos` e continua lá, editado em Notas → Modelos de atos. O
# padrão saiu do código para `modelos_padrao/notas/minutas/`, e chega pela
# mesma base dos outros padrões.
ATRIBUICAO_DAS_MINUTAS = "Tabelionato de Notas — minutas"
PASTA_DAS_MINUTAS = "notas/minutas"


def minuta_de_fabrica(codigo: str) -> dict:
    """A minuta de fábrica `codigo`, LIDA DA BASE. Só lê.

    Devolve a linha da base (`chave`, `nome`, `corpo`, `impressao_digital`…).
    **Sem ela, erro claro** — a mesma regra do `padrao_de`: a subida que
    semeia `nt_modelos` não pode gravar uma minuta em branco.
    """
    alvo = PASTA.chave_normal(codigo)
    p = _padroes()["padroes"].get(alvo)
    if not p or p.get("atribuicao") != ATRIBUICAO_DAS_MINUTAS:
        raise ModeloError(
            f"A minuta de fábrica «{alvo}» não está carregada na base de modelos "
            f"({schema_da_base()}): falta o arquivo "
            f"{PASTA.PASTA_DOS_PADROES.name}/{PASTA_DAS_MINUTAS}/{alvo}.txt na "
            "pasta do programa, ou ele está com defeito. Reinstale a atualização.")
    return p


def corpo_gravado_ou_padrao(con: sqlite3.Connection, chave: str) -> str:
    """O ajuste GRAVADO em `mo_modelos` daquele papel, ou o padrao da base. So le.

    E A REGRA QUE OS QUATRO MODELOS DO RI JA SEGUIAM, agora valendo para os
    quinze — `modelo["corpo"] if modelo else MODELO_CERTIDAO_PADRAO`. O padrao
    e o piso: **sem linha na tabela, o papel sai do jeito de fabrica**, e por
    isso nao ha como uma edicao ruim deixar a casa sem modelo nenhum.

    **ESTA FUNCAO ERA O `corpo_de` ATE 07/09/2026**, e mudou de nome por uma
    razao de recursao: `corpo_de` passou a COMPOR o documento pelos elementos
    (`modelos_elementos`), e o modulo dos elementos precisa deste piso aqui
    para montar o degrau de baixo. Se ele chamasse `corpo_de`, os dois se
    chamariam para sempre.

    **`ri_modelos` SAIU DAQUI NO LF06A**: o que ela tiver vira ajuste em
    `mo_modelos` na subida (`trazer_ajustes_do_legado_ri`), e a busca fica uma
    so — a casa, e depois a base.
    """
    c = _do_catalogo(chave)
    r = banco(con).um(
        """SELECT corpo FROM mo_modelos
            WHERE chave = %s AND COALESCE(ativo, 1) = 1
              AND COALESCE(corpo, '') <> ''""", (c["chave"],))
    if r:
        return str(r["corpo"])
    return padrao_de(c["chave"])


def corpo_de(con: sqlite3.Connection, chave: str) -> str:
    """O papel INTEIRO que vale hoje — corpo, encerramento e rodape. So le.

    **OS TREZE SITIOS QUE EMITEM PAPEL CHAMAM ESTA FUNCAO**, no RI, no caixa,
    nas notas, no termo do civil e no protesto. Ela mudou de conteudo em
    07/09/2026 e **nao mudou de nome nem de assinatura**, de proposito: assim os
    treze ganham o encerramento e o rodape sem que nenhum deles seja editado —
    e edicao em treze lugares e treze chances de errar um.

    **E NO DIA DA SUBIDA ELA DEVOLVE EXATAMENTE O QUE DEVOLVIA NA VESPERA**,
    porque o encerramento e o rodape nascem vazios e parte vazia nao entra na
    juncao. Era a condicao do oficial: «manter a forma e diminuir o risco de ir
    errado».

    **QUEM EDITA NAO CHAMA ESTA**, e sim `modelos_elementos.corpo_do_ato`:
    mostrar o documento composto na caixa de edicao faria o escrevente gravar o
    fecho DENTRO do corpo, e o fecho sairia duas vezes no papel seguinte.
    """
    c = _do_catalogo(chave)
    try:
        import modelos_elementos as ELEM
        return ELEM.montar_documento(con, c["chave"])
    except Exception:                                        # noqa: BLE001
        # **O PISO NAO PODE DEPENDER DO ANDAR DE CIMA.** Se a tabela dos
        # elementos ainda nao existir — instalacao a meio de migrar —, o papel
        # continua saindo. Um documento que nao sai e pior que um documento sem
        # o fecho novo.
        return corpo_gravado_ou_padrao(con, c["chave"])


def esta_ajustado(con: sqlite3.Connection, chave: str) -> bool:
    """Se a casa mexeu neste modelo. So calcula.

    A TELA PRECISA DIZER ISSO, porque «igual ao padrao» e «ajustado pela casa»
    parecem a mesma coisa quando o texto e o mesmo — e sao diferentes no dia em
    que o padrao mudar numa versao nova: o ajustado NAO acompanha.
    """
    c = _do_catalogo(chave)
    return banco(con).um(
        """SELECT 1 AS um FROM mo_modelos
            WHERE chave = %s AND COALESCE(corpo, '') <> ''""",
        (c["chave"],)) is not None


def salvar(con: sqlite3.Connection, chave: str, *, corpo: str,
           quem: str | None, agora: str) -> None:
    """Guarda o ajuste da casa para aquele papel.

    O CORPO VAZIO NAO SE GRAVA — ele volta ao padrao. Guardar vazio faria a
    casa imprimir folha em branco, e folha em branco assinada e pior que
    modelo feio.
    """
    c = _do_catalogo(chave)
    limpo = (corpo or "").strip()
    if not limpo:
        restaurar(con, chave)
        return
    banco(con).escrever(
        """INSERT INTO mo_modelos (chave, corpo, ativo, atualizado_em,
               atualizado_por, base_impressao)
           VALUES (%s,%s,1,%s,%s,%s)
           ON CONFLICT(chave) DO UPDATE SET
               corpo = excluded.corpo, ativo = 1,
               atualizado_em = excluded.atualizado_em,
               atualizado_por = excluded.atualizado_por,
               base_impressao = excluded.base_impressao""",
        (c["chave"], limpo, agora, quem, impressao_sob_o_ajuste(c["chave"])))


def impressao_sob_o_ajuste(chave: str) -> str | None:
    """A impressão digital do padrão sobre o qual o ajuste está sendo feito.

    **É ELA QUE PERMITE DIZER «O PADRÃO MUDOU DEPOIS DO SEU AJUSTE».** O ajuste
    não acompanha o padrão — é a regra —, e sem guardar sobre qual padrão ele
    foi escrito a casa nunca saberia que a versão nova trouxe uma frase que o
    ajuste dela não tem. Padrão não carregado não impede o ajuste: aí não há
    sobre o que ter sido feito, e fica nulo.
    """
    try:
        return impressao_digital_de(chave)
    except ModeloError:
        return None


def trazer_ajustes_do_legado_ri(con: sqlite3.Connection, *, agora: str | None = None) -> int:
    """O que `ri_modelos` tiver vira ajuste da casa em `mo_modelos`. Devolve quantos.

    Roda na SUBIDA (`ri_schema.init_ri_schema`). Medido: zero linhas nesta
    casa; é para a instalação que já tivesse ajustado alguma coisa ali.

    **O AJUSTE NOVO VENCE O LEGADO**: se a casa já gravou o papel na tela nova
    (linha ATIVA e não vazia em `mo_modelos`), o texto velho não o sobrescreve.
    Linha de `mo_modelos` desligada ou vazia não é ajuste — a leitura de antes
    do LF06A passava por ela e caía no legado —, e por isso ela é preenchida
    com o texto velho (`ON CONFLICT ... DO UPDATE ... WHERE`).

    **A LINHA VELHA SÓ É DESLIGADA QUANDO O TEXTO DELA ESTÁ NA CASA** — copiado
    agora (`RETURNING` devolveu a linha) ou já idêntico no ajuste ativo. Sem
    isso (revisão do LF06A), o ajuste antigo seria desligado sem ter sido
    copiado, e sumiria sem aviso. Desligada, «voltar ao padrão» não o
    ressuscita na subida seguinte. Com um ajuste DIFERENTE na casa, ela fica
    como está: não é lida (a casa vence), e volta a valer se a casa restaurar
    o padrão — que é o que a leitura de antes fazia. `base_impressao` fica
    nulo: não há como saber sobre qual padrão o ajuste antigo foi feito.

    Desliga todas as ativas do tipo, e não só a copiada: a leitura de antes só
    usava a primeira (`ORDER BY id LIMIT 1`), e a segunda nunca saiu em papel.
    """
    bd = banco(con)
    agora = agora or _agora()
    trazidos = 0
    try:
        # Quase toda subida não tem legado nenhum (zero linhas nesta casa): sem
        # esta olhada, cada subida pegaria a trava de escrita à toa.
        if bd.um("""SELECT 1 AS um FROM ri_modelos
                     WHERE ativo = 1 AND COALESCE(corpo, '') <> ''
                     ORDER BY id LIMIT 1""") is None:
            return 0
        bd.travar("mo_modelos.legado_ri")
        for velho, novo in LEGADO_RI.items():
            r = bd.um(
                """SELECT id, corpo, atualizado_em, atualizado_por FROM ri_modelos
                    WHERE tipo = %s AND ativo = 1 AND COALESCE(corpo, '') <> ''
                    ORDER BY id LIMIT 1""", (velho,))
            if not r:
                continue
            quem = ("ri_modelos (legado)" if r["atualizado_por"] is None
                    else f"ri_modelos (legado), usuário {r['atualizado_por']}")
            corpo = str(r["corpo"])
            copiou = len(bd.escrever(
                """INSERT INTO mo_modelos (chave, corpo, ativo, atualizado_em,
                       atualizado_por, base_impressao)
                   VALUES (%s, %s, 1, %s, %s, NULL)
                   ON CONFLICT (chave) DO UPDATE SET
                       corpo = excluded.corpo, ativo = 1,
                       atualizado_em = excluded.atualizado_em,
                       atualizado_por = excluded.atualizado_por,
                       base_impressao = NULL
                    WHERE COALESCE(mo_modelos.ativo, 1) <> 1
                       OR COALESCE(mo_modelos.corpo, '') = ''
                   RETURNING chave""",
                (novo, corpo, r["atualizado_em"] or agora, quem))) > 0
            identico = not copiou and bd.um(
                """SELECT 1 AS um FROM mo_modelos
                    WHERE chave = %s AND COALESCE(ativo, 1) = 1 AND corpo = %s""",
                (novo, corpo)) is not None
            if copiou or identico:
                bd.escrever("UPDATE ri_modelos SET ativo = 0 WHERE tipo = %s AND ativo = 1",
                            (velho,))
            trazidos += int(copiou)
    except sqlite3.OperationalError:
        return 0                          # instalacao sem a tabela antiga
    return trazidos


def modelo_legado_ri(con: sqlite3.Connection, modelo_id) -> dict | None:
    """O modelo `ri_modelos` de número `modelo_id`, achado PELO CAMINHO NOVO. Só lê.

    É o `?modelo=<id>` da ficha (`ri_web.ri_ficha_odt`), com que a tela velha
    do RI experimentava um modelo específico. **Depois da subida a linha velha
    está desligada** (`trazer_ajustes_do_legado_ri`) e o texto dela mora em
    `mo_modelos`, como ajuste do papel: procurar só a linha ativa — como a ficha
    fazia — nunca a acharia, e a ficha cairia calada no modelo da casa
    (revisão do LF06A).

      · linha ATIVA — ainda não foi trazida (a casa tem outro ajuste): vale o
        texto dela, como antes;
      · linha desligada de um tipo que o catálogo conhece — o texto dela foi
        trazido para o papel do catálogo, e vale a busca única daquele papel
        (`texto_do_papel`), que é onde a casa o edita desde então;
      · número que não existe, ou de tipo que o catálogo não conhece — ``None``,
        e quem chamou AVISA, em vez de imprimir outro modelo no lugar.

    Devolve ``{"id", "nome", "tipo", "chave", "corpo", "de_onde"}``.
    """
    try:
        numero = int(str(modelo_id).strip())
    except (TypeError, ValueError):
        return None
    try:
        r = banco(con).um(
            "SELECT id, nome, tipo, corpo, ativo FROM ri_modelos WHERE id = %s",
            (numero,))
    except sqlite3.OperationalError:
        return None                       # instalacao sem a tabela antiga
    if not r:
        return None
    chave = LEGADO_RI.get(str(r["tipo"] or "").upper())
    base = {"id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "chave": chave}
    if r["ativo"] == 1 and str(r["corpo"] or "").strip():
        return {**base, "corpo": str(r["corpo"]), "de_onde": "ri_modelos"}
    if not chave:
        return None
    return {**base, "corpo": texto_do_papel(con, chave), "de_onde": chave}


def padrao_mudou_depois_do_ajuste(con: sqlite3.Connection, chave: str) -> dict | None:
    """O ajuste da casa foi feito sobre o padrão de HOJE? Só lê.

    Devolve ``None`` quando não há ajuste do corpo; senão
    ``{"situacao", "onde", "diferenca"}``, com `situacao`:

      · ``"MUDOU"`` — o padrão de hoje não é aquele sobre o qual o ajuste foi
        feito. A tela avisa «o padrão mudou depois do seu ajuste» e mostra a
        diferença entre o AJUSTE e o padrão de hoje: o texto antigo do padrão
        não fica guardado em lugar nenhum, só a impressão digital dele;
      · ``"IGUAL"`` — nada mudou desde o ajuste;
      · ``"SEM_MARCA"`` — ajuste anterior ao LF06A (`base_impressao` nulo):
        não há como saber, e a tela diz isso em vez de calar.

    **A ATUALIZAÇÃO NÃO TOCA NO AJUSTE**: quem decide se traz a frase nova do
    padrão para o ajuste é a casa, olhando a diferença.
    """
    from modelos_elementos_schema import CHAVE_DO_ROTULO, CORPO
    c = _do_catalogo(chave)
    bd = banco(con)
    linha, onde = None, None
    atribuicao = CHAVE_DO_ROTULO.get(c["atribuicao"])
    if atribuicao and not c.get("peca_de"):
        linha = bd.um(
            """SELECT corpo, base_impressao FROM mo_elementos
                WHERE atribuicao = %s AND ato = %s AND parte = %s
                  AND COALESCE(ativo, 1) = 1 AND COALESCE(corpo, '') <> ''""",
            (atribuicao, c["chave"], CORPO))
        onde = "mo_elementos"
    if not linha:
        linha = bd.um(
            """SELECT corpo, base_impressao FROM mo_modelos
                WHERE chave = %s AND COALESCE(ativo, 1) = 1
                  AND COALESCE(corpo, '') <> ''""", (c["chave"],))
        onde = "mo_modelos"
    if not linha:
        return None
    if not linha["base_impressao"]:
        return {"situacao": "SEM_MARCA", "onde": onde, "diferenca": []}
    if linha["base_impressao"] == impressao_sob_o_ajuste(c["chave"]):
        return {"situacao": "IGUAL", "onde": onde, "diferenca": []}
    diferenca = list(difflib.unified_diff(
        str(linha["corpo"]).splitlines(), padrao_de(c["chave"]).splitlines(),
        "o ajuste desta casa", "o padrão de hoje", lineterm=""))
    return {"situacao": "MUDOU", "onde": onde, "diferenca": diferenca}


def restaurar(con: sqlite3.Connection, chave: str) -> bool:
    """Joga fora o ajuste e volta ao padrao da base. Devolve se havia ajuste.

    E POR ISSO QUE O PADRAO NAO MORA NA TABELA DA CASA: voltar atras e apagar
    uma linha, e nao recadastrar um texto que ninguem tem mais guardado.
    """
    c = _do_catalogo(chave)
    apagadas = banco(con).escrever(
        "DELETE FROM mo_modelos WHERE chave = %s RETURNING chave", (c["chave"],))
    return len(apagadas) > 0


def conferir(corpo: str, contexto: dict[str, Any]) -> str | None:
    """Tenta montar o modelo com um contexto de exemplo. Devolve o erro, ou None.

    MODELO QUEBRADO NAO PODE APARECER NA HORA DO ATO. Sem esta conferencia, o
    erro de chave surge quando o escrevente clica em «emitir certidao» com o
    cliente na frente — e o ato ja esta lavrado. Aqui ele aparece na tela de
    quem edita, que e onde da para consertar.

    Roda no MESMO ambiente restrito do resto da casa (`SandboxedEnvironment`):
    conferir num ambiente mais solto aprovaria modelo que a hora do ato recusa.
    """
    from jinja2.sandbox import SandboxedEnvironment
    try:
        SandboxedEnvironment(autoescape=False).from_string(
            corpo or "").render(**contexto)
    except Exception as erro:                      # noqa: BLE001 — e o recado
        return f"{type(erro).__name__}: {erro}"
    return None


def por_atribuicao() -> list[tuple[str, list[dict]]]:
    """O catalogo agrupado, na ordem em que a tela mostra.

    A ORDEM E A DO CATALOGO, e nao alfabetica: ela poe o Registro de Imoveis
    primeiro porque e onde estao cinco dos dez papeis, e alfabetica poria
    «Caixa» na frente sem que isso ajudasse ninguem a achar.
    """
    grupos: list[tuple[str, list[dict]]] = []
    for c in CATALOGO:
        if not grupos or grupos[-1][0] != c["atribuicao"]:
            grupos.append((c["atribuicao"], []))
        grupos[-1][1].append(c)
    return grupos

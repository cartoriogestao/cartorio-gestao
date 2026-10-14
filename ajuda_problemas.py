"""
OS PROBLEMAS DO SISTEMA — o que quebrou, o que a casa mediu, e o relatório.

POR QUE ESTE MÓDULO EXISTE
    A ajuda de 26/08/2026 respondia pergunta. Faltava a outra metade do pedido
    do oficial: que ela **soubesse dos problemas** e deixasse escrito o que
    precisa de conserto.

    Hoje, quando uma tela estoura, o que sobra é a lembrança de quem estava no
    balcão — e lembrança de balcão em dia de movimento é o que se perde
    primeiro. O escrevente fecha o navegador, atende o próximo, e o defeito
    volta na semana seguinte com outra pessoa, que também não anota.

O SISTEMA AVISA; NINGUÉM PRECISA LEMBRAR
    Toda tela que estoura vira uma linha aqui, sozinha, com a hora, a tela, o
    usuário e o ponto exato do programa onde parou. Quem topou com o defeito
    não precisa fazer nada — e é bom que não precise, porque ele está com o
    cliente na frente.

    Além disso, quem quiser CONTAR o que aconteceu tem a janela da ajuda em
    qualquer tela: «o botão não fez nada», «o número saiu errado». Defeito que
    não estoura o programa é justamente o que máquina nenhuma percebe.

ANOTAR PROBLEMA NÃO PASSA PELA LISTA DE PERFIS, E ISSO É DE PROPÓSITO
    Consultar a API gasta e manda dado para fora — por isso tem perfil e teto.
    Anotar um problema não faz nem uma coisa nem outra: é escrita local, no
    banco desta casa. **Quem topa com o defeito é o balcão**, e o balcão não
    pode ficar sem poder avisar por causa de uma regra que existe para outra
    coisa.

ANOTAR NUNCA ESTOURA
    Um anotador que quebra enquanto anota um erro transforma um defeito em
    dois, e esconde o primeiro. É a mesma regra de `Database._anotar_disputa`,
    e pelo mesmo motivo.

    E há um caso em que ele nem tenta: quando o erro foi `database is locked`.
    Gravar no banco que acabou de travar é disputar a mesma trava, e o balcão
    esperaria mais dez segundos por uma tela que já deu errado. Essa espécie
    já está contada em `disputas_de_escrita.log`, que é arquivo e não banco.

A MESMA COISA DUAS VEZES É UMA LINHA, COM UM CONTADOR
    Um defeito que acontece quarenta vezes num dia geraria quarenta linhas, e
    as quarenta afogariam os outros três problemas da lista. Então cada
    problema tem uma IMPRESSÃO DIGITAL — a espécie do erro e o ponto do
    programa, com os números trocados por `#`, porque `matrícula 1.234 não
    existe` e `matrícula 5.678 não existe` são o mesmo defeito.

    A unicidade mora no banco, num `UNIQUE`: nenhuma revisão de código pegou o
    defeito de 18/08/2026, e um `UNIQUE` teria pego.

O QUE VOLTOU DEPOIS DE RELATADO É A LINHA MAIS IMPORTANTE DA LISTA
    Problema que reaparece depois de mandado para conserto quer dizer uma de
    duas coisas: o conserto não veio, ou não era o conserto. As duas merecem
    ficar à vista, e por isso a nova ocorrência devolve o problema para ABERTO
    sem apagar a data em que ele foi relatado.

O RELATÓRIO SAI SEMPRE SANITIZADO
    Ele **nasce para sair da serventia**: é feito para chegar ao programador,
    numa outra máquina. Não existe exceção para enviar o dado inteiro: o que
    interessa a quem conserta é o ponto do programa, e nunca de quem era o
    dado pessoal.

    Um traceback carrega o que estava sendo gravado. Por isso o relatório
    atravessa `ajuda_privacidade`, a mesma barreira obrigatória das consultas,
    e a folha de rosto diz que passou.

A CONFERÊNCIA DA CASA MEDE; NÃO CONSERTA
    `conferir_a_casa` olha o que já é medido em outros cantos — as disputas de
    escrita, a integridade do banco, as pendências de implantação, a manutenção
    diária que falhou, as consultas da ajuda que não voltaram — e escreve o que
    encontrou. Ela não decide nada e não conserta nada: quem conserta o
    programa é o programador, e quem decide o ato é o oficial.

    Ela não repete conferência que já existe com dono: as fichas digitalizadas
    têm a tela *Integridade*, que confere arquivo por arquivo e demora. Chamar
    aquilo aqui seria pôr uma varredura de disco dentro de uma tela de balcão.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import ajuda as AJ
import ajuda_codigo as CODIGO
import ajuda_mapa as MAPA
import ajuda_privacidade as PRIV
import implantacao as IMP

# De onde veio a notícia do problema. Não é enfeite: o relatório trata cada uma
# de um jeito, e quem lê precisa saber se aquilo estourou sozinho ou se foi uma
# pessoa que estranhou.
ORIGENS: dict[str, str] = {
    "ERRO_DE_TELA": "O sistema estourou numa tela",
    "RELATADO": "Alguém do balcão contou",
    "CONFERENCIA": "A conferência da casa mediu",
}

SITUACOES = ("ABERTO", "RELATADO", "RESOLVIDO")

# AS TRÊS VISTAS DA LISTA — relato #82, 17/09/2026.
#
#   «Organizar problemas concluidos e em aberto. Lista apresenta todos
#    problemas já criados e está longa, separar itens concluidos dos itens em
#    aberto»
#
# A LISTA NÃO TINHA ONDE ESCOLHER, e a ordem sozinha não resolvia: os oitenta
# problemas vinham numa tabela só, com os resolvidos no fim, e quem abria a
# tela para ver o que ainda dói rolava por sessenta e dois deles. Poder
# escolher a vista é a diferença entre uma lista de trabalho e um arquivo.
#
# «EM ABERTO» SÃO DUAS PALAVRAS, E NÃO UMA: `ABERTO` é o que ainda não foi
# mandado para conserto, `RELATADO` é o que já foi e a casa espera. Os dois
# pedem alguma coisa de alguém; `RESOLVIDO` não pede mais nada.
#
# E «TODOS» É A TABELA INTEIRA, sem filtro nenhum — e não a soma das três
# situações. Escrita como soma, uma situação que nascesse fora do vocabulário
# — como a que este relato achou na #77 — sumiria justamente da vista que
# promete não esconder nada.
VISTAS: dict[str, dict] = {
    "abertos": {"rotulo": "Em aberto", "situacoes": ("ABERTO", "RELATADO")},
    "resolvidos": {"rotulo": "Resolvidos", "situacoes": ("RESOLVIDO",)},
    "todos": {"rotulo": "Todos", "situacoes": ()},
}

# A VISTA DO QUE AINDA PEDE ALGUMA COISA. É ela que a lista abre mostrando —
# quem abre a tela quer ver o que dói —, e é a única que faz sentido no
# relatório: é ele que sai da casa para ser consertado, e problema já
# resolvido num papel de conserto é linha que ninguém lê.
VISTA_EM_ABERTO = "abertos"
VISTA_PADRAO = VISTA_EM_ABERTO

# FILTRO POR ONDE ABRIU — sandbox :8899, coluna ambiente_abertura (3.6.214).
AMBIENTE_FILTRO_PADRAO = "todas"
AMBIENTES_FILTRO: dict[str, dict] = {
    "todas": {"rotulo": "Todas", "valor": None},
    "oficial": {"rotulo": "Abertas no oficial", "valor": "OFICIAL"},
    "sandbox": {"rotulo": "Abertas no sandbox", "valor": "SANDBOX"},
}


def ambiente_filtro_escolhido(pedido: Any) -> str:
    """Parâmetro `?ambiente=` na lista de problemas (só UI no sandbox)."""
    chave = str(pedido or "").strip().lower()
    return chave if chave in AMBIENTES_FILTRO else AMBIENTE_FILTRO_PADRAO


def tem_coluna_ambiente_abertura(con: sqlite3.Connection) -> bool:
    return any(
        r[1] == "ambiente_abertura"
        for r in con.execute("PRAGMA table_info(aj_problemas)"))


def valor_filtro_ambiente_abertura(con: sqlite3.Connection,
                                   chave_filtro: Any) -> str | None:
    """OFICIAL/SANDBOX ou None; ignorado fora do sandbox ou sem coluna."""
    if not banco_e_sandbox(con) or not tem_coluna_ambiente_abertura(con):
        return None
    return AMBIENTES_FILTRO[ambiente_filtro_escolhido(chave_filtro)]["valor"]


def params_url_lista_problemas(*, vista: str, so_meus: bool, gere: bool,
                               ambiente: str,
                               exibir_filtro_ambiente: bool,
                               vista_alvo: str | None = None,
                               ambiente_alvo: str | None = None,
                               alternar_meus: bool = False) -> dict[str, str]:
    """Query string da lista — vista, meus e ambiente (GET, favoritos)."""
    meus = not so_meus if alternar_meus and gere else so_meus
    p: dict[str, str] = {"vista": vista_alvo if vista_alvo is not None else vista}
    if gere and meus:
        p["meus"] = "1"
    if exibir_filtro_ambiente:
        chave = (ambiente_alvo if ambiente_alvo is not None else ambiente)
        escolhido = ambiente_filtro_escolhido(chave)
        if escolhido != AMBIENTE_FILTRO_PADRAO:
            p["ambiente"] = escolhido
    return p


def vista_escolhida(pedido: Any) -> str:
    """A vista pedida no endereço, ou a padrão. Só calcula.

    VISTA DESCONHECIDA NÃO É ERRO. Um favorito antigo, ou um `?vista=` que
    alguém digitou à mão, cai na padrão — e os botões na tela dizem qual está
    valendo, que é o que faz a queda ficar à vista em vez de virar silêncio.
    """
    chave = str(pedido or "").strip().lower()
    return chave if chave in VISTAS else VISTA_PADRAO


def _filtro_da_vista(vista: Any) -> tuple[str, tuple[str, ...]]:
    """O pedaço de `WHERE` de uma vista, e o que ele pergunta. Só calcula.

    UMA DEFINIÇÃO SÓ DO QUE ESTÁ EM ABERTO. A lista, a janela da ajuda (que
    mostra o que já deu errado nesta tela) e o relatório perguntam a mesma
    coisa, e escritas três vezes elas divergiriam no primeiro conserto — é a
    régua da `normalizar_nome` outra vez, e aqui o que divergiria é o que a
    casa considera resolvido.
    """
    situacoes = tuple(VISTAS[vista_escolhida(vista)]["situacoes"])
    if not situacoes:
        return "", ()
    return (f"situacao IN ({', '.join('?' * len(situacoes))})", situacoes)

# Quanto do rastro técnico se guarda. O traceback inteiro de uma tela grande
# passa de cinco mil caracteres, e o que conserta está nas últimas linhas.
LIMITE_DO_DETALHE = 6_000

# Quantos problemas cabem num relatório. Acima disso não é relatório: é
# despejo, e ninguém conserta despejo.
LIMITE_DO_RELATORIO = 60

PASTA_DOS_RELATORIOS = "relatorios"


class ProblemaError(ValueError):
    """Erro de regra dos problemas, com a mensagem pronta para o balcão."""


# ------------------------------------------------------------- o esquema

SCHEMA = """
-- O QUE QUEBROU, E QUANTAS VEZES.
--
-- Uma linha por ESPECIE de problema, e nao por ocorrencia: um defeito que
-- acontece quarenta vezes num dia afogaria os outros tres da lista. O que
-- distingue uma especie da outra e a `impressao`.
CREATE TABLE IF NOT EXISTS aj_problemas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- A IMPRESSAO DIGITAL, e o UNIQUE que faz a regra valer no banco.
    -- Nenhuma revisao de codigo pegou o defeito de 18/08/2026; um UNIQUE
    -- teria pegado. Aqui e ele que impede a lista de virar despejo.
    impressao TEXT NOT NULL UNIQUE,

    origem TEXT NOT NULL,                   -- ERRO_DE_TELA | RELATADO | CONFERENCIA
    onde TEXT,                              -- o endpoint da tela
    caminho TEXT,                           -- o endereco que estava na barra
    titulo TEXT NOT NULL,
    detalhe TEXT,                           -- o traceback, ou o que a pessoa contou

    versao TEXT,                            -- em que versao aconteceu
    vezes INTEGER NOT NULL DEFAULT 1,
    primeira_em TEXT NOT NULL,
    ultima_em TEXT NOT NULL,
    ultimo_usuario TEXT,

    situacao TEXT NOT NULL DEFAULT 'ABERTO',
    -- QUANDO FOI MANDADO PARA CONSERTO. Nao se apaga quando o problema volta:
    -- «voltou depois de relatado» e a linha mais importante desta lista.
    relatado_em TEXT,
    fechado_em TEXT,
    fechado_por TEXT,
    fechado_nota TEXT,

    -- O QUE A AJUDA DISSE SOBRE ELE, quando alguem pediu a leitura. Fica
    -- junto do problema, e nao solto em `aj_consultas`, para o relatorio
    -- sair de uma consulta so.
    diagnostico TEXT,
    diagnostico_em TEXT,
    consulta_id INTEGER,
    -- Prova local do trecho efetivamente lido pelo diagnóstico do Lote 2.
    diagnostico_codigo_arquivo TEXT,
    diagnostico_codigo_linhas TEXT,
    diagnostico_codigo_sha256 TEXT
);

CREATE INDEX IF NOT EXISTS ix_aj_problemas_situacao
    ON aj_problemas(situacao, ultima_em);
CREATE INDEX IF NOT EXISTS ix_aj_problemas_onde
    ON aj_problemas(onde, situacao);

-- OS RELATORIOS QUE JA SAIRAM.
--
-- O relatorio e um arquivo que deixa a serventia. Guardar quando saiu, quem
-- mandou, quantos problemas levava e a impressao digital do arquivo e o que
-- permite conferir depois que o que chegou e o que saiu — a mesma conferencia
-- que o roteiro de atualizacao ja pede com `certutil`.
CREATE TABLE IF NOT EXISTS aj_relatorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo TEXT NOT NULL,
    quantos INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT,
    versao TEXT,
    gerado_em TEXT NOT NULL,
    gerado_por TEXT
);
"""


# O RETORNO DO DESENVOLVIMENTO — relato #35 do oficial, em 30/08/2026:
#
#   «Criar um campo para completar com notas do desenvolvimento sobre a
#    eventual solução ou pendência de solução de cada problema na aba ajuda.
#    Os que forem resolvidos a IA ou desenvolvedor já coloca **a prova do
#    cumprimento** ou relata alguma pendência.»
#
#   SAO COLUNAS NOVAS, E NAO O `diagnostico` QUE JA EXISTIA. Aquele e o
#   conselho da ajuda — ela leu a mensagem e opinou, sem conferir o codigo.
#   Este e o retorno de quem mexeu no codigo, e a diferenca entre os dois e
#   justamente o que o oficial precisa distinguir ao ler.
#
#   **A PROVA TEM CAMPO PROPRIO.** «Foi resolvido» sem onde conferir e a
#   mesma promessa que este projeto ja quebrou duas vezes hoje — funcao pronta
#   sem tela. Com o nome do teste ou do arquivo, ele confere.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("aj_problemas", "nota_dev", "TEXT"),
    ("aj_problemas", "nota_dev_estado", "TEXT"),
    ("aj_problemas", "nota_dev_prova", "TEXT"),
    ("aj_problemas", "nota_dev_em", "TEXT"),
    ("aj_problemas", "nota_dev_por", "TEXT"),
    ("aj_problemas", "diagnostico_codigo_arquivo", "TEXT"),
    ("aj_problemas", "diagnostico_codigo_linhas", "TEXT"),
    ("aj_problemas", "diagnostico_codigo_sha256", "TEXT"),
    # QUEM CRIOU, PELO LOGIN — relato #87, 23/09/2026. `ultimo_usuario` não
    # serve para «os meus»: guarda o NOME do dia (o mesmo Jean está como «Jean
    # Santos» em 44 relatos e «Mario Exemplo dos Santos» em 24), mistura login
    # e nome conforme a origem, e é sobrescrito quando o problema se repete.
    # O login não muda com o nome. `preencher_criado_por` põe os antigos.
    ("aj_problemas", "criado_por", "TEXT"),
    # POR QUE VOLTOU, E QUEM DISSE — relato #87. Quem relatou passa a poder
    # reabrir o seu, e reabrir sem dizer por quê deixa quem conserta
    # adivinhando o que ainda está errado.
    ("aj_problemas", "reaberto_em", "TEXT"),
    ("aj_problemas", "reaberto_por", "TEXT"),
    ("aj_problemas", "reaberto_nota", "TEXT"),
    # OFICIAL = aberto na produção ou replicado dela; SANDBOX = criado no :8899.
    ("aj_problemas", "ambiente_abertura", "TEXT"),
)

AMBIENTES_ABERTURA = ("OFICIAL", "SANDBOX")


def caminho_do_banco(con: sqlite3.Connection) -> str:
    for row in con.execute("PRAGMA database_list"):
        if row[1] == "main":
            return str(row[2] or "")
    return ""


def banco_e_sandbox(con: sqlite3.Connection) -> bool:
    """True quando o SQLite é o da pasta SANDBOX/dados (dev :8899)."""
    p = caminho_do_banco(con).replace("\\", "/").upper()
    if not p or p == ":MEMORY:":
        p = os.environ.get("CARTORIO_GESTAO_DATA", "").replace("\\", "/").upper()
    return "/SANDBOX/" in p and ("/DADOS/" in p or p.rstrip("/").endswith("/DADOS"))


def ambiente_abertura_padrao(con: sqlite3.Connection) -> str:
    return "SANDBOX" if banco_e_sandbox(con) else "OFICIAL"


def atualizar_sqlite_sequence(con: sqlite3.Connection,
                              tabela: str = "aj_problemas") -> int:
    """Garante que AUTOINCREMENT não reutilize id de linha importada."""
    row = con.execute(
        f"SELECT COALESCE(MAX(id), 0) FROM {tabela}").fetchone()
    max_id = int(row[0] if row else 0)
    if max_id <= 0:
        return 0
    if con.execute(
            "SELECT 1 FROM sqlite_sequence WHERE name=?", (tabela,)).fetchone():
        con.execute(
            "UPDATE sqlite_sequence SET seq=? WHERE name=?",
            (max_id, tabela))
    else:
        con.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
            (tabela, max_id))
    return max_id


def id_livre(con: sqlite3.Connection, candidato: int) -> bool:
    return con.execute(
        "SELECT 1 FROM aj_problemas WHERE id=?", (int(candidato),)
    ).fetchone() is None


def id_oficial_da_nota(nota: str | None) -> int | None:
    if not nota:
        return None
    m = re.search(r"origem_id_oficial\s*=\s*(\d+)", nota, re.I)
    return int(m.group(1)) if m else None


def realinhar_id_problema(con: sqlite3.Connection, *, id_atual: int,
                          id_desejado: int, impressao: str) -> bool:
    """Move a PK para coincidir com o # oficial (upsert por impressao)."""
    id_atual, id_desejado = int(id_atual), int(id_desejado)
    if id_atual == id_desejado:
        return False
    outro = con.execute(
        "SELECT impressao FROM aj_problemas WHERE id=?", (id_desejado,)
    ).fetchone()
    if outro and outro[0] != impressao:
        raise ValueError(
            f"id {id_desejado} já usado por outra impressão "
            f"({outro[0]!r}); não dá para realinhar {impressao!r} "
            f"de #{id_atual}.")
    if outro:
        con.execute("DELETE FROM aj_problemas WHERE id=?", (id_desejado,))
    con.execute(
        "UPDATE aj_problemas SET id=? WHERE id=? AND impressao=?",
        (id_desejado, id_atual, impressao))
    return True


def realinhar_ids_replicados(con: sqlite3.Connection, *,
                             dry_run: bool) -> dict[str, Any]:
    """Corrige ids locais 1..N do piloto para o # oficial na nota_dev."""
    init_problemas_schema(con)
    stats: dict[str, Any] = {"realinhados": 0, "pulados": 0, "erros": []}
    linhas = con.execute(
        """SELECT id, impressao, nota_dev FROM aj_problemas
           WHERE nota_dev LIKE '%REPLICADO_SBX%'
              OR nota_dev LIKE '%origem_id_oficial=%'"""
    ).fetchall()
    plano: list[tuple[int, int, str]] = []
    for linha in linhas:
        id_of = id_oficial_da_nota(linha["nota_dev"])
        id_atual = int(linha["id"])
        if id_of is None or id_atual == id_of:
            stats["pulados"] += 1
            continue
        plano.append((id_atual, id_of, linha["impressao"]))
    plano.sort(key=lambda t: t[1], reverse=True)
    for id_atual, id_desejado, impressao in plano:
        try:
            if not dry_run:
                realinhar_id_problema(
                    con, id_atual=id_atual, id_desejado=id_desejado,
                    impressao=impressao)
            stats["realinhados"] += 1
        except ValueError as exc:
            stats["erros"].append(str(exc))
    if not dry_run and stats["realinhados"]:
        atualizar_sqlite_sequence(con)
    return stats


def preencher_ambiente_abertura(con: sqlite3.Connection) -> None:
    """Backfill sandbox: replicados OFICIAL; demais SANDBOX."""
    init_problemas_schema(con)
    con.execute(
        """UPDATE aj_problemas SET ambiente_abertura='OFICIAL'
           WHERE (ambiente_abertura IS NULL OR ambiente_abertura='')
             AND (nota_dev LIKE '%REPLICADO_SBX%'
                  OR nota_dev LIKE '%origem_id_oficial=%')""")
    if banco_e_sandbox(con):
        con.execute(
            """UPDATE aj_problemas SET ambiente_abertura='SANDBOX'
               WHERE ambiente_abertura IS NULL OR ambiente_abertura=''""")


# OS ESTADOS DO RETORNO. **Nenhum deles fecha o problema** — fechar continua
# sendo o clique do oficial, e por isso `ATENDIDO` diz «atendido», e nao
# «resolvido»: quem decide se foi resolvido e quem relatou.
ESTADOS_DO_DEV: dict[str, str] = {
    "NECESSARIO_TESTE": "Necessário teste — pytest OK; falta conferência no balcão",
    "ATENDIDO": "Atendido — confira pela prova ao lado",
    "EM_ANDAMENTO": "Em andamento",
    "DEPENDE_DO_OFICIAL": "Depende de uma decisão sua",
    "DEPENDE_DE_TERCEIRO": "Depende de terceiro (TJ, ARPEN, Receita…)",
    "NAO_SERA_FEITO": "Não será feito — o motivo está na nota",
}

# Rótulo curto para distintivo na lista (a frase longa fica no detalhe).
ROTULO_CURTO_DEV: dict[str, str] = {
    "NECESSARIO_TESTE": "Necessário teste",
    "ATENDIDO": "Atendido",
    "EM_ANDAMENTO": "Em andamento",
    "DEPENDE_DO_OFICIAL": "Depende de você",
    "DEPENDE_DE_TERCEIRO": "Dep. terceiro",
    "NAO_SERA_FEITO": "Não será feito",
}


def init_problemas_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas dos problemas. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1]
                      for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def anotar_desenvolvimento(con: sqlite3.Connection, problema_id: int, *,
                           nota: str, estado: str, prova: str = "",
                           agora: str, por: str = "") -> dict:
    """Grava o retorno do desenvolvimento no problema. ESCREVE.

    **NAO FECHA O PROBLEMA, E ISSO E DELIBERADO.** Nenhum estado muda a
    `situacao`: marcar como resolvido e o clique do oficial, e continua sendo.
    O maximo que esta funcao diz e «atendido, confira pela prova» — porque
    quem decide se o que ele relatou foi resolvido e quem relatou.

    **A PROVA E EXIGIDA QUANDO SE DIZ ATENDIDO.** «Foi feito» sem onde
    conferir e promessa, e promessa e o que este projeto ja quebrou: funcao
    pronta que nenhuma tela alcanca passou por aqui duas vezes num dia.
    """
    estado = (estado or "").strip().upper()
    if estado not in ESTADOS_DO_DEV:
        raise ProblemaError(
            f"Não conheço o estado «{estado}». Os que conheço: "
            + ", ".join(ESTADOS_DO_DEV) + ".")
    nota = (nota or "").strip()
    if not nota:
        raise ProblemaError(
            "A nota do desenvolvimento não pode ficar vazia: um estado sem "
            "explicação faz quem lê adivinhar o que aconteceu.")
    prova = (prova or "").strip()
    if estado in ("ATENDIDO", "NECESSARIO_TESTE") and not prova:
        raise ProblemaError(
            "Para dizer que foi **atendido** ou que falta **teste no balcão** "
            "é preciso dizer **onde conferir** — o nome do teste, o arquivo, "
            "a tela. Sem isso é promessa, e promessa não se confere.")
    linha = con.execute("SELECT id FROM aj_problemas WHERE id=?",
                        (int(problema_id),)).fetchone()
    if not linha:
        raise ProblemaError(f"Não achei o problema #{problema_id}.")
    con.execute(
        """UPDATE aj_problemas SET nota_dev=?, nota_dev_estado=?,
               nota_dev_prova=?, nota_dev_em=?, nota_dev_por=? WHERE id=?""",
        (nota, estado, prova, agora, por, int(problema_id)))
    return {"id": int(problema_id), "estado": estado,
            "nome_do_estado": ESTADOS_DO_DEV[estado]}


# ------------------------------------------------------ a impressão digital


def _sem_os_numeros(texto: str) -> str:
    """`matrícula 1.234 não existe` e `matrícula 5.678 não existe` são um só.

    O número muda a cada ocorrência e não muda o defeito. Mantê-lo na
    impressão digital faria cada cliente que passasse pela mesma tela virar um
    problema diferente na lista.
    """
    return re.sub(r"\d+", "#", str(texto or ""))


def impressao_de(*, origem: Any, onde: Any, titulo: Any,
                 detalhe: Any = None) -> str:
    """A digital que diz se dois problemas são o mesmo. Só calcula.

    Entra também o `detalhe` do ERRO_DE_TELA, porque nele mora o ponto do
    programa: duas telas diferentes podem estourar com a mesma frase, e são
    dois defeitos. No RELATADO o detalhe é texto de gente, que nunca sai
    igual duas vezes — e por isso ele não entra.
    """
    pedacos = [str(origem or ""), str(onde or ""),
               _sem_os_numeros(titulo)[:200]]
    if str(origem or "") == "ERRO_DE_TELA":
        pedacos.append(_sem_os_numeros(detalhe)[-400:])
    crua = "|".join(pedacos)
    return hashlib.sha256(crua.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- anotar


def anotar(con: sqlite3.Connection, *, origem: str, titulo: str,
           agora: str, detalhe: Any = None, onde: Any = None,
           caminho: Any = None, versao: Any = None,
           usuario: Any = None, criado_por: Any = None) -> dict:
    """Escreve o problema, ou soma mais uma vez ao que já existe. ESCREVE.

    Devolve `{"id", "vezes", "nova"}` — `nova` diz se é a primeira vez, que é
    o que a tela usa para dizer "isto já tinha acontecido antes".

    `criado_por` é o LOGIN de quem criou, e só se grava na primeira vez: quem
    topa de novo com o mesmo defeito não passa a ser o dono dele (relato #87).
    """
    if str(origem or "") not in ORIGENS:
        raise ProblemaError(
            f"Origem desconhecida: {origem!r}. As que existem são "
            f"{', '.join(ORIGENS)}.")
    texto = (titulo or "").strip()
    if not texto:
        raise ProblemaError("Escreva o que aconteceu.")
    corpo = str(detalhe or "").strip()[:LIMITE_DO_DETALHE] or None
    digital = impressao_de(origem=origem, onde=onde, titulo=texto,
                           detalhe=corpo)

    linha = con.execute("SELECT * FROM aj_problemas WHERE impressao=?",
                        (digital,)).fetchone()
    if linha is None:
        amb = ambiente_abertura_padrao(con)
        cur = con.execute(
            """INSERT INTO aj_problemas(impressao, origem, onde, caminho,
                   titulo, detalhe, versao, vezes, primeira_em, ultima_em,
                   ultimo_usuario, situacao, criado_por, ambiente_abertura)
               VALUES (?,?,?,?,?,?,?,1,?,?,?,'ABERTO',?,?)""",
            (digital, origem, str(onde or "") or None,
             str(caminho or "") or None, texto[:400], corpo,
             str(versao or "") or None, agora, agora,
             str(usuario or "") or None, str(criado_por or "") or None,
             amb))
        novo_id = int(cur.lastrowid)
        if banco_e_sandbox(con):
            atualizar_sqlite_sequence(con)
        return {"id": novo_id, "vezes": 1, "nova": True}

    # ACONTECEU DE NOVO. Se já tinha sido mandado para conserto, volta para
    # ABERTO — e `relatado_em` fica, porque «voltou depois de relatado» é o
    # que quem conserta mais precisa saber.
    vezes = int(linha["vezes"] or 0) + 1
    con.execute(
        """UPDATE aj_problemas SET vezes=?, ultima_em=?, ultimo_usuario=?,
               versao=COALESCE(?, versao), situacao='ABERTO'
         WHERE id=?""",
        (vezes, agora, str(usuario or "") or None, str(versao or "") or None,
         int(linha["id"])))
    return {"id": int(linha["id"]), "vezes": vezes, "nova": False}


# ------------------------------------------------- o erro que estoura a tela


# Os arquivos que são o sistema. O traceback traz também Flask, Werkzeug e a
# biblioteca padrão, e nenhum deles é onde se conserta: o que interessa é a
# última linha DESTA CASA que participou.
#
# A PASTA INTEIRA, E NÃO SÓ A RAIZ: um erro dentro de um template estoura com o
# nome do arquivo `.html`, que mora em `templates/`. Olhar só a raiz deixaria
# esses sem ponto nenhum — e defeito de template é dos que mais aparecem, sem
# nunca dizer onde.
def _ponto_da_casa(rastro: list, raiz: Path) -> str:
    for quadro in reversed(rastro):
        caminho = Path(quadro.filename)
        try:
            dentro = raiz in caminho.resolve().parents
        except OSError:
            dentro = False
        if dentro:
            return f"{caminho.name}:{quadro.lineno} em {quadro.name}()"
    return ""


def resumo_do_erro(erro: BaseException, *, raiz: Any = None) -> dict:
    """Título e detalhe de uma exceção. Só calcula.

    O TÍTULO É A ESPÉCIE MAIS O PONTO DA CASA, e não a mensagem inteira: a
    mensagem carrega o número do ato, e é ela que faria cada cliente virar um
    problema diferente.
    """
    raiz = Path(raiz or Path(__file__).resolve().parent)
    rastro = traceback.extract_tb(erro.__traceback__)
    ponto = _ponto_da_casa(rastro, raiz)
    especie = type(erro).__name__
    mensagem = str(erro).strip().splitlines()[0] if str(erro).strip() else ""
    titulo = f"{especie} em {ponto}" if ponto else especie
    if mensagem:
        titulo = f"{titulo} — {mensagem[:160]}"
    detalhe = "".join(traceback.format_exception(
        type(erro), erro, erro.__traceback__))
    return {"titulo": titulo, "detalhe": detalhe, "ponto": ponto,
            "especie": especie}


def _e_disputa(erro: BaseException) -> bool:
    """`database is locked` — o único erro que NÃO se anota no banco."""
    if not isinstance(erro, sqlite3.OperationalError):
        return False
    texto = str(erro).lower()
    return "locked" in texto or "busy" in texto


def anotar_falha_de_tela(db, erro: BaseException, *, agora: str,
                         onde: Any = None, caminho: Any = None,
                         versao: Any = None, usuario: Any = None) -> dict | None:
    """A tela estourou: anota sozinho. ESCREVE, e NUNCA ESTOURA.

    Devolve o que `anotar` devolveu, ou `None` quando não deu para anotar —
    e não dar para anotar não pode virar um segundo erro na cara de quem já
    levou o primeiro.

    NÃO ANOTA DISPUTA DE ESCRITA. Gravar no banco que acabou de travar é
    disputar a mesma trava, e o balcão esperaria os dez segundos do
    `busy_timeout` por uma tela que já deu errado. Essa espécie já está
    contada em `disputas_de_escrita.log` — arquivo, e não banco.
    """
    if _e_disputa(erro):
        return None
    try:
        r = resumo_do_erro(erro)
        with db.transaction() as con:
            # Aqui `usuario` já é o LOGIN (quem chama é o errorhandler de
            # `app.py`), e por isso ele serve também de `criado_por`.
            return anotar(con, origem="ERRO_DE_TELA", titulo=r["titulo"],
                          detalhe=r["detalhe"], onde=onde, caminho=caminho,
                          versao=versao, usuario=usuario, agora=agora,
                          criado_por=usuario)
    except Exception:                                          # noqa: BLE001
        return None


# ------------------------------------------------------------- consultas


def ler(con: sqlite3.Connection, problema_id: int) -> sqlite3.Row | None:
    """O problema inteiro. Só LÊ."""
    return con.execute("SELECT * FROM aj_problemas WHERE id=?",
                       (int(problema_id),)).fetchone()


def listar(con: sqlite3.Connection, *, situacao: Any = None,
           limite: int = 200, criado_por: Any = None,
           ambiente_filtro: Any = None) -> list[dict]:
    """Os problemas, na ordem de quem tem o que fazer. Só LÊ.

    O QUE AINDA PEDE ALGUMA COISA VEM PRIMEIRO, e dentro de cada grupo o mais
    recente na frente. O `WHERE` decide o grupo.

    `situacao` aceita UMA palavra («os resolvidos») ou um grupo delas («o que
    está em aberto», que são duas) — o agente pergunta pela primeira forma e a
    tela pela segunda, e a régua é a mesma.

    A ORDEM DOS RESOLVIDOS MUDOU EM 17/09/2026, com o relato #82. Ela era
    `ultima_em`, a data do último acontecimento — e um problema já resolvido
    tem por último acontecimento a própria abertura, meses atrás. Resultado:
    o que a casa tinha acabado de consertar caía no fim da lista, e o que
    ficou pendurado em agosto aparecia no alto. **Quem lê uma lista de
    concluídos quer os de agora**, e é o que `fechado_em` responde.

    E A CHAVE DE UM GRUPO SÓ DECIDE DENTRO DELE — o `fechado_em` solto
    decidia nos dois. Não se via por acidente: numa linha em aberto essa
    coluna é NULA, e NULO vai para o fim numa ordem decrescente. A exceção é
    a linha que TEM data de fechamento sem estar `RESOLVIDO` — e ela existiu:
    a **#77**, gravada como «FECHADO» por fora do sistema, subia na vista
    «Todos» para o alto do grupo do que está em aberto, **na frente do
    problema que a casa acabou de encontrar**, e sem nada dizendo por quê.
    Ela foi normalizada em 17/09/2026 (a limpeza foi o mesmo achado que criou
    este `CASE`), e os dois `ORDER BY` ficam: linha torta é possível de novo
    enquanto houver quem escreva `situacao` à mão, e agora a conferência da
    casa a acusa — `conferir_a_casa`, achado `situacao_fora_do_vocabulario`.
    """
    pedido = situacao
    varias: tuple[str, ...]
    if pedido is None or pedido == "":
        varias = ()
    elif isinstance(pedido, str):
        varias = (pedido.strip().upper(),) if pedido.strip() else ()
    else:
        varias = tuple(str(v).strip().upper() for v in pedido if str(v).strip())

    sql = "SELECT * FROM aj_problemas"
    parametros: list = []
    condicoes: list[str] = []
    if varias:
        condicoes.append(f"situacao IN ({', '.join('?' * len(varias))})")
        parametros.extend(varias)
    # «SÓ OS MEUS» — relato #87. `criado_por` é o login; problema sem dono
    # declarado (o erro de tela repetido, cujo primeiro não se sabe) não
    # entra na lista de ninguém, em vez de entrar na de quem chegou por último.
    if str(criado_por or "").strip():
        condicoes.append("criado_por = ?")
        parametros.append(str(criado_por).strip())
    valor_amb = valor_filtro_ambiente_abertura(con, ambiente_filtro or "")
    if valor_amb:
        condicoes.append("ambiente_abertura = ?")
        parametros.append(valor_amb)
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += (" ORDER BY situacao='RESOLVIDO',"
            # A DATA QUE ORDENA É A DO GRUPO A QUE A LINHA PERTENCE: o
            # fechamento para quem já foi resolvido, o último acontecimento
            # para o resto — que é quem ainda tem o que fazer.
            " CASE WHEN situacao='RESOLVIDO' THEN fechado_em"
            " ELSE ultima_em END DESC,"
            " ultima_em DESC, id DESC LIMIT ?")
    parametros.append(int(limite))
    return [dict(r) for r in con.execute(sql, parametros)]


def em_aberto(con: sqlite3.Connection, *, limite: int = 200) -> list[dict]:
    """Só o que ainda pede alguma coisa — a mesma régua da lista. Só LÊ.

    EXISTE PORQUE A PERGUNTA «O QUE AINDA PEDE ALGUMA COISA?» TEM TRÊS
    LEITORES: a lista da tela (#82), a janela da ajuda e o relatório que sai
    da casa. Cada um respondia por conta própria, e a do relatório — um
    `situacao != 'RESOLVIDO'` escrito na rota — discordava da lista no caso
    que o relato #82 achou: a palavra fora do vocabulário.

    **Relatório que carrega para fora da serventia um problema que a lista
    já não mostra — ou que deixa de carregar o que ela mostra — é o defeito
    de `normalizar_nome` na forma de lista.** A régua é uma, e mora aqui.
    """
    return listar(con, situacao=VISTAS[VISTA_EM_ABERTO]["situacoes"],
                  limite=limite)


def como_se_conta(problema: dict) -> str:
    """O mesmo problema, dito para quem está no balcão. Só calcula.

    O TÍTULO É TÉCNICO DE PROPÓSITO — `KeyError em ri_web.py:1234` é o que
    serve a quem conserta, e é o que vai no relatório. Mas a janela é do
    balcão, e `KeyError` na cara do escrevente é jargão de programador em cima
    de alguém que já levou um erro.

    Isto foi correção: a primeira versão mostrava o título cru na janela, e a
    própria página de erro passou a exibir a espécie da exceção para quem
    estava atendendo. Quem pegou foi o teste de tela.
    """
    p = dict(problema)
    if p.get("origem") == "ERRO_DE_TELA":
        return "O sistema deu erro nesta tela"
    # RELATADO e CONFERENCIA já nascem em português: um foi escrito por uma
    # pessoa, o outro pela conferência, que fala com o oficial.
    return str(p.get("titulo") or "")


def da_tela(con: sqlite3.Connection, onde: Any,
            limite: int = 3) -> list[dict]:
    """O que já deu errado NESTA tela, e ainda não foi resolvido. Só LÊ.

    É o que a janela mostra a quem abre a ajuda: quem topa hoje com o defeito
    que outro topou ontem merece saber que não é ele que está fazendo errado.

    O QUE É «AINDA NÃO FOI RESOLVIDO» VEM DA MESMA RÉGUA DA LISTA
    (`_filtro_da_vista`), e não de um `<> 'RESOLVIDO'` escrito aqui. As duas
    formas concordam em quase tudo e discordam exatamente no caso que apareceu
    em 17/09/2026: uma situação fora do vocabulário. Escrita de dois jeitos, a
    janela mostraria como «ainda não resolvido» o que a lista conta como
    anomalia a arrumar.
    """
    if not str(onde or ""):
        return []
    filtro, situacoes = _filtro_da_vista(VISTA_EM_ABERTO)
    linhas = [dict(r) for r in con.execute(
        """SELECT id, origem, titulo, vezes, ultima_em, situacao, relatado_em
             FROM aj_problemas
            WHERE onde=? AND """ + filtro + """
            ORDER BY ultima_em DESC LIMIT ?""",
        (str(onde), *situacoes, int(limite)))]
    for linha in linhas:
        linha["resumo"] = como_se_conta(linha)
    return linhas


def contagem(con: sqlite3.Connection, *, criado_por: Any = None) -> dict:
    """O quadro para a tela, para o aviso do menu e para as vistas. Só LÊ.

    UMA CONSULTA SÓ, e o resto é conta em Python. Ela roda a cada tela — quem
    a chama é o aviso do menu —, e por isso o que se pede ao banco é o
    agrupamento por situação; as vistas saem dele, pela régua de
    `_filtro_da_vista`. Perguntar ao banco uma contagem por vista seria a
    mesma régua escrita duas vezes, que é como as duas divergem.

    `fora_do_vocabulario` é o outro lado disso: uma situação que não é
    nenhuma das três não entra em vista nenhuma — e é justamente por isso que
    ela precisa de um número próprio, em vez de sumir na conta.
    """
    # O NÚMERO ACOMPANHA O FILTRO (relato #87): com «só os meus», os botões
    # das vistas contam só os meus — contagem que não segue o filtro é o
    # carimbo que mente sobre o próprio filtro.
    dono = str(criado_por or "").strip()
    linhas = con.execute(
        """SELECT situacao, COUNT(*) n,
                  SUM(CASE WHEN relatado_em IS NOT NULL THEN 1 ELSE 0 END)
                      com_relato
             FROM aj_problemas """
        + ("WHERE criado_por = ? " if dono else "")
        + "GROUP BY situacao", (dono,) if dono else ()).fetchall()

    por_situacao = {str(l["situacao"] or ""): int(l["n"] or 0) for l in linhas}
    voltaram = sum(int(l["com_relato"] or 0) for l in linhas
                   if str(l["situacao"] or "") == "ABERTO")
    d = {
        "por_situacao": por_situacao,
        "total": sum(por_situacao.values()),
        "abertos": por_situacao.get("ABERTO", 0),
        "relatados": por_situacao.get("RELATADO", 0),
        "resolvidos": por_situacao.get("RESOLVIDO", 0),
        "voltaram": voltaram,
        "fora_do_vocabulario": sum(
            n for palavra, n in por_situacao.items() if palavra not in SITUACOES),
    }

    # O NÚMERO DE CADA VISTA. «Todos» é a tabela inteira — e não a soma das
    # três palavras —, para que a linha fora do vocabulário não desapareça
    # justamente da vista que promete não esconder nada.
    por_vista: dict[str, int] = {}
    for chave in VISTAS:
        _filtro, situacoes = _filtro_da_vista(chave)
        por_vista[chave] = (sum(por_situacao.get(s, 0) for s in situacoes)
                            if situacoes else d["total"])
    d["por_vista"] = por_vista
    return d


# ----------------------------------------------------------- mudar de mão


def fechar(con: sqlite3.Connection, problema_id: int, *, agora: str,
           usuario: Any = None, nota: Any = None) -> dict:
    """Marca o problema como resolvido. ESCREVE.

    QUEM FECHA DIZ O QUE FEZ — e desde 17/09/2026 isso é exigência, e não
    estilo. Medido na produção em 17/09/2026, 19h04, na medição do relato #82:
    dos **65** problemas resolvidos, **58** estavam sem uma linha de
    explicação — **32** fechados por uma mão em agosto e na primeira semana de
    setembro, e **26** pela outra só naquele dia. A lista dizia «resolvido» e
    não dizia o quê, e quem abrisse a ficha meses depois não tinha por onde
    saber se o defeito foi consertado ou apenas escondido.

    A EXIGÊNCIA PEGA O QUE VEM, E NÃO CONSERTA O QUE PASSOU. As 58 continuam
    onde estão: reescrever a explicação delas seria inventar, em nome de quem
    fechou, o que ninguém escreveu — e o sistema não tem como saber.

    A NOTA É O QUE RESPONDE «o sistema avisou?» NO DIA EM QUE A PERGUNTA
    IMPORTA. É a mesma régua do descarte da minuta, do cancelamento da
    certidão e da dispensa do usucapião: dez letras de gente, porque «ok» não
    explica nada a quem lê depois.
    """
    texto = str(nota or "").strip()
    if not ler(con, problema_id):
        raise ProblemaError(f"Problema {problema_id} não encontrado.")
    if len(texto) < 10:
        raise ProblemaError(
            f"Para marcar o problema #{int(problema_id)} como resolvido, "
            "escreva o que foi feito, com pelo menos dez letras — «ok» não "
            "explica nada a quem abrir a lista depois.")
    # QUEM FECHOU E QUANDO NÃO SE REESCREVE — e isto é a consequência direta
    # de a nota passar a ser exigida. As 58 linhas que estavam sem explicação
    # só têm um jeito de ganhá-la: passar por aqui de novo. Sem o COALESCE,
    # esse ato — que é o de ESCREVER o que faltava — carimbava data e nome
    # novos sobre um fechamento de setembro, e a lista dos resolvidos, que
    # desde hoje se ordena por essa data, subiria para o alto as linhas mais
    # antigas como se tivessem acabado de ser resolvidas. A NOTA é o que se
    # está escrevendo agora; a data e o nome são fato do passado, e fato do
    # passado não se regrava — é a régua da `_marcar_a_ficha_encerrada`.
    con.execute(
        """UPDATE aj_problemas SET situacao='RESOLVIDO',
               fechado_em=COALESCE(fechado_em, ?),
               fechado_por=COALESCE(fechado_por, ?),
               fechado_nota=? WHERE id=?""",
        (agora, str(usuario or "") or None, texto, int(problema_id)))
    return {"id": int(problema_id), "situacao": "RESOLVIDO"}


def reabrir(con: sqlite3.Connection, problema_id: int, *, agora: str,
            usuario: Any = None, motivo: Any = None,
            exige_motivo: bool = False) -> dict:
    """Volta um problema para a lista. ESCREVE.

    O MOTIVO — relato #87, 23/09/2026. Quem relatou passou a poder reabrir o
    seu quando o conserto não resolveu, e para ele o motivo é OBRIGATÓRIO
    (`exige_motivo`): «voltou» sem dizer o que ainda está errado faz quem
    conserta procurar de novo o que já tinha achado. A régua das dez letras é
    a mesma de `fechar`. Para ADMIN e gerente ele continua opcional, como era.
    """
    if not ler(con, problema_id):
        raise ProblemaError(f"Problema {problema_id} não encontrado.")
    texto = str(motivo or "").strip()
    if exige_motivo and len(texto) < 10:
        raise ProblemaError(
            f"Para reabrir o problema #{int(problema_id)}, escreva o que ainda "
            "não ficou certo, com pelo menos dez letras — é isso que diz a "
            "quem conserta onde procurar.")
    con.execute(
        """UPDATE aj_problemas SET situacao='ABERTO', ultima_em=?,
               ultimo_usuario=?, fechado_em=NULL, fechado_por=NULL,
               reaberto_em=?, reaberto_por=?,
               reaberto_nota=COALESCE(?, reaberto_nota)
         WHERE id=?""",
        (agora, str(usuario or "") or None, agora,
         str(usuario or "") or None, texto or None, int(problema_id)))
    return {"id": int(problema_id), "situacao": "ABERTO"}


# QUEM GERE A LISTA — ADMIN e gerente, a mesma régua que já abria a tela.
PAPEIS_QUE_GEREM = ("ADMIN", "MANAGER")


def pode_reabrir(problema: Any, *, papel: Any, login: Any) -> bool:
    """Quem pode reabrir este problema. Só calcula. — relato #87.

    Quem gere a lista reabre qualquer um; quem relatou reabre o SEU, e só
    depois de resolvido (o que está aberto não tem o que reabrir). Fechar
    continua sendo só de quem gere: dizer «resolvido» é opinião sobre o
    conserto, e é do oficial.
    """
    if str(papel or "") in PAPEIS_QUE_GEREM:
        return True
    p = dict(problema or {})
    dono = str(p.get("criado_por") or "").strip()
    return (bool(dono) and dono == str(login or "").strip()
            and p.get("situacao") == "RESOLVIDO")


def preencher_criado_por(con: sqlite3.Connection) -> dict:
    """Põe `criado_por` nos problemas antigos. ESCREVE; idempotente.

    Relato #87. Medido em 23/09/2026 na produção:

      * RELATADO — a auditoria sabe quem relatou: `AJUDA_PROBLEMA_RELATADO`,
        com o LOGIN, em 92 de 92. Vale a PRIMEIRA linha de cada problema.
      * ERRO_DE_TELA com uma ocorrência só — `ultimo_usuario` é o login de
        quem topou (o errorhandler grava o login), e sendo uma vez só, é ele.
      * ERRO_DE_TELA REPETIDO (6 de 11) — fica SEM DONO. O primeiro já foi
        sobrescrito, e escolher o último seria dar o problema a quem só topou
        de novo com ele.

    Só mexe em linha com `criado_por` vazio, e só aceita login que exista em
    `users`: nome solto não vira dono de nada.
    """
    logins = {str(r[0]) for r in con.execute("SELECT username FROM users")}
    pelo_relato = pela_tela = 0
    try:
        primeiros = con.execute(
            """SELECT a.entity_id, a.username_snapshot
                 FROM audit_logs a
                 JOIN (SELECT entity_id, MIN(id) primeiro FROM audit_logs
                        WHERE action='AJUDA_PROBLEMA_RELATADO'
                          AND entity_type='aj_problemas'
                        GROUP BY entity_id) p ON p.primeiro = a.id""").fetchall()
    except sqlite3.Error:
        primeiros = []
    for problema_id, login in primeiros:
        if str(login or "") not in logins:
            continue
        cur = con.execute(
            """UPDATE aj_problemas SET criado_por=?
                WHERE id=? AND origem='RELATADO'
                  AND (criado_por IS NULL OR criado_por='')""",
            (str(login), int(problema_id)))
        pelo_relato += cur.rowcount
    for problema_id, login in con.execute(
            """SELECT id, ultimo_usuario FROM aj_problemas
                WHERE origem='ERRO_DE_TELA' AND vezes=1
                  AND (criado_por IS NULL OR criado_por='')""").fetchall():
        if str(login or "") in logins:
            con.execute("UPDATE aj_problemas SET criado_por=? WHERE id=?",
                        (str(login), int(problema_id)))
            pela_tela += 1
    return {"pelo_relato": pelo_relato, "pela_tela": pela_tela}


# ------------------------------------------------- a conferência da casa


def _achado(chave: str, titulo: str, detalhe: str, *, grave: bool) -> dict:
    return {"chave": chave, "titulo": titulo, "detalhe": detalhe,
            "grave": bool(grave)}


def conferir_a_casa(con: sqlite3.Connection, *, agora: str,
                    disputas: Any = None, banco: Any = None) -> list[dict]:
    """Mede o que a casa já sabe medir, e devolve o que está errado. Só LÊ.

    RECEBE AS MEDIÇÕES DE FORA — as disputas e a integridade do banco vêm de
    `Database`, que é quem tem o arquivo de registro e a quem pertencem os
    comandos de conferência que só o SQLite tem. Assim esta função se testa sem
    um banco de produção, e o acoplamento ao SQLite não entra num módulo novo.

    NÃO CONSERTA NADA, e não decide nada. Escreve o que mediu.
    """
    achados: list[dict] = []

    # 1. AS DISPUTAS DE ESCRITA. Cinco em trinta dias é o gatilho medido da
    #    conversa sobre trocar de banco (DOCUMENTACAO/MIGRAR_DE_BANCO.md).
    d = dict(disputas or {})
    recentes = int(d.get("recentes") or 0)
    if recentes >= 5:
        achados.append(_achado(
            "disputas", f"O banco travou {recentes} vezes em trinta dias",
            f"Total desde {d.get('primeira') or 'sempre'}: "
            f"{d.get('total')}. Cinco ou mais em trinta dias é o sinal medido "
            f"de que o SQLite deixou de bastar para esta casa. "
            f"Ver DOCUMENTACAO/MIGRAR_DE_BANCO.md.", grave=True))
    elif int(d.get("total") or 0) > 0:
        achados.append(_achado(
            "disputas", f"O banco travou {d.get('total')} vez(es)",
            f"A última em {d.get('ultima')}. Uma vez ou outra é normal; "
            f"cinco em trinta dias é o sinal de conversar sobre trocar de "
            f"banco.", grave=False))

    # 2. A INTEGRIDADE DO BANCO E AS CHAVES ÓRFÃS.
    b = dict(banco or {})
    if b:
        if str(b.get("integridade") or "ok").lower() != "ok":
            achados.append(_achado(
                "integridade", "O banco não passou na conferência de integridade",
                str(b.get("integridade")), grave=True))
        orfas = int(b.get("orfas") or 0)
        if orfas:
            achados.append(_achado(
                "orfas", f"{orfas} linha(s) apontando para registro que não existe",
                str(b.get("orfas_detalhe") or "")[:1500], grave=True))

    # 3. O QUE SÓ O OFICIAL PODE INFORMAR. Série sem contador é o primeiro ato
    #    novo nascendo com o número 1 sobre acervo que já passou disso — o
    #    defeito de 18/08/2026.
    try:
        pendencias = IMP.contagem(con)
    except sqlite3.Error:
        pendencias = {}
    abertas = int(pendencias.get("abertas") or 0)
    if abertas:
        achados.append(_achado(
            "implantacao", f"{abertas} coisa(s) esperando o oficial informar",
            "Em «Demais atribuições → O que falta informar». Enquanto ficarem "
            "sem resposta, o primeiro ato de cada série nasce com o número 1 "
            "sobre um acervo que já passou disso. Atribuições: "
            + ", ".join(pendencias.get("atribuicoes") or []), grave=True))

    # 4. A MANUTENÇÃO DIÁRIA QUE FALHOU. Ela já se anota sozinha em `settings`;
    #    o que faltava era alguém olhar.
    #
    #    CADA LEITURA VAI PROTEGIDA, e não é excesso de cuidado: uma conferência
    #    que estoura no meio devolve MENOS achados sem dizer que devolveu menos —
    #    e quem lê a lista conclui que a casa está em ordem. Tabela que falta é
    #    o próprio achado, e é assim que ela sai escrita.
    try:
        erro = con.execute(
            "SELECT value FROM settings WHERE key='manutencao_diaria_erro'"
        ).fetchone()
    except sqlite3.Error as falha:
        erro = None
        achados.append(_achado(
            "conferencia", "A conferência não conseguiu ler as configurações",
            str(falha), grave=True))
    recado = str((erro["value"] if erro else "") or "").strip()
    if recado:
        achados.append(_achado(
            "manutencao", "A manutenção diária não terminou",
            f"O sistema anotou: {recado}. Enquanto isso, obrigação recorrente "
            f"pode não estar sendo criada e tarefa vencida pode não estar "
            f"subindo de prioridade.", grave=True))

    # 5. A AJUDA QUE NÃO RESPONDEU. Um dia em que a internet caiu não pode
    #    parecer um dia em que ninguém perguntou — e nem um dia normal.
    ontem = _ontem(agora)
    try:
        falhas = con.execute(
            """SELECT COUNT(*) c FROM aj_consultas
                WHERE falha IS NOT NULL AND perguntada_em >= ?""",
            (ontem,)).fetchone()
    except sqlite3.Error:
        falhas = None
    quantas = int(falhas["c"] if falhas else 0)
    if quantas >= 3:
        ultima = con.execute(
            """SELECT falha FROM aj_consultas WHERE falha IS NOT NULL
                ORDER BY id DESC LIMIT 1""").fetchone()
        achados.append(_achado(
            "ajuda_sem_resposta",
            f"A ajuda não respondeu {quantas} vezes nas últimas 24 horas",
            f"A última falha foi: {(ultima['falha'] if ultima else '')[:400]}",
            grave=False))

    # 6. A SITUAÇÃO QUE NÃO É NENHUMA DAS TRÊS — achado do relato #82, em
    #    17/09/2026. O problema #77 estava gravado como `FECHADO`, e «FECHADO»
    #    não é nenhuma das três situações deste módulo.
    #
    #    O ESTRAGO NÃO ERA ELE CONTAR NO TOTAL: era a TELA O PINTAR DE
    #    RESOLVIDO. A cadeia de distintivos terminava num `else`, e o `else`
    #    recebia qualquer palavra — de modo que a lista afirmava «resolvido»
    #    sobre um estado que o sistema não conhece. É o carimbo que mente, e
    #    é por isso que este achado existe: a palavra fora do vocabulário tem
    #    de aparecer COMO ELA É, e não como a última alternativa da régua.
    #
    #    NÃO CONSERTA. Quem fecha problema é gente, e uma linha pode ter sido
    #    fechada à mão por um motivo que só quem a fechou sabe — a conferência
    #    mostra, e a decisão é de quem lê.
    marcas = ", ".join("?" * len(SITUACOES))
    try:
        estranhas = con.execute(
            f"""SELECT COALESCE(situacao, '') situacao, COUNT(*) n
                  FROM aj_problemas
                 WHERE COALESCE(situacao, '') NOT IN ({marcas})
                 GROUP BY COALESCE(situacao, '')""",
            tuple(SITUACOES)).fetchall()
    except sqlite3.Error as falha:
        estranhas = []
        achados.append(_achado(
            "conferencia", "A conferência não conseguiu ler as situações",
            str(falha), grave=True))
    if estranhas:
        total = sum(int(l["n"] or 0) for l in estranhas)
        achados.append(_achado(
            "situacao_fora_do_vocabulario",
            f"{total} problema(s) com uma situação que o sistema não conhece",
            "As que valem: " + ", ".join(SITUACOES) + ". Fora delas: "
            + ", ".join(f"«{l['situacao'] or '(em branco)'}» em {l['n']} "
                        f"problema(s)" for l in estranhas)
            + ". Eles não entram em «em aberto» nem em «resolvidos», e é por "
              "isso que precisam ser vistos: abra cada um na lista, em "
              "«Todos», e marque-o como resolvido escrevendo o que houve — ou "
              "reabra, se o serviço não acabou.", grave=False))

    return achados


def _ontem(agora: str) -> str:
    """As últimas 24 horas, contadas em Python.

    A DATA NÃO SE CALCULA NO SQL — `strftime` e `julianday` não existem fora do
    SQLite, e módulo novo entra com zero (`tests/test_portabilidade.py`).
    """
    try:
        dia = date.fromisoformat(str(agora or "")[:10])
    except ValueError:
        return "0000-00-00"
    return (dia - timedelta(days=1)).isoformat()


def anotar_achados(con: sqlite3.Connection, achados: list[dict], *,
                   agora: str, versao: Any = None,
                   usuario: Any = None) -> dict:
    """Põe o que a conferência mediu na lista de problemas. ESCREVE."""
    novos = repetidos = 0
    for a in achados:
        r = anotar(con, origem="CONFERENCIA", titulo=a["titulo"],
                   detalhe=a["detalhe"], onde=f"conferencia:{a['chave']}",
                   versao=versao, usuario=usuario, agora=agora)
        if r["nova"]:
            novos += 1
        else:
            repetidos += 1
    return {"achados": len(achados), "novos": novos, "repetidos": repetidos}


# ------------------------------------------------- o que a ajuda diz dele


PERGUNTA_DO_DIAGNOSTICO = (
    "O sistema anotou o problema abaixo. Diga, em português de balcão: "
    "(1) o que provavelmente aconteceu; (2) o que o escrevente faz AGORA para "
    "seguir o atendimento; (3) o que quem for consertar o programa deve olhar "
    "primeiro. Quando houver trecho de código, separe claramente o que o trecho "
    "prova do que é apenas hipótese. Não diga que corrigiu nem invente uma "
    "causa. Se a mensagem e o trecho não permitirem saber, diga que não permitem "
    "— palpite sobre defeito manda mexer onde não deve.")


def diagnosticar(db, problema_id: int, *, pasta_de_dados: Any, agora: str,
                 papel: Any = None, usuario: str | None = None,
                 # **VAZIO QUER DIZER «O CONFIGURADO».** Era "PADRAO", e isso
                 # passou a ser um defeito em 14/09/2026: o diagnóstico do
                 # problema é a pergunta mais difícil que a ajuda responde, e
                 # ele estava forçando o modelo rápido por cima da escolha de
                 # quem configurou a casa.
                 conhecimento: Any = None, modelo: Any = None,
                 mapa: dict | None = None,
                 raiz: Any = None, app: Any = None, versao: str = "") -> dict:
    """Pergunta à ajuda o que ela vê neste problema. FALA COM A REDE, ESCREVE.

    RECEBE `db`, E NÃO `con`, pela mesma razão de `ajuda.consultar`: a chamada
    de rede não pode acontecer dentro do `BEGIN IMMEDIATE` da casa.

    O DIAGNÓSTICO É CONSELHO, e fica marcado como tal na tela e no relatório.
    O Lote 2 pode ler um trecho do arquivo relacionado, mas não o altera nem
    o executa. Ele não fecha problema nenhum: quem fecha é gente.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        linha = ler(con, problema_id)
    if not linha:
        raise ProblemaError(f"Problema {problema_id} não encontrado.")

    p = dict(linha)
    arquivo_sugerido = MAPA.arquivo_da_tela(mapa or {}, p.get("onde"))
    trecho = CODIGO.inspecionar(p, arquivo_sugerido=arquivo_sugerido)
    contexto = "\n".join([
        f"Origem: {ORIGENS.get(p['origem'], p['origem'])}.",
        f"Tela: {p.get('onde') or '—'} ({p.get('caminho') or '—'}).",
        (f"Aconteceu {p.get('vezes')} vez(es), a primeira em "
         f"{p.get('primeira_em')} e a última em {p.get('ultima_em')}."),
        f"Versão do sistema: {p.get('versao') or '—'}.",
        "",
        "O QUE FICOU ESCRITO:",
        str(p.get("detalhe") or "")[:AJ.LIMITE_DO_CONTEXTO - 2000],
    ])
    conhecimento_com_codigo = (
        str(conhecimento or "") + CODIGO.contexto_para_consulta(trecho)
    )
    r = AJ.consultar(db, pergunta=PERGUNTA_DO_DIAGNOSTICO, assunto="ERRO",
                     onde=p.get("onde"), referencia=f"problema {problema_id}",
                     contexto=contexto, modelo=modelo,
                     pasta_de_dados=pasta_de_dados, agora=agora, papel=papel,
                     usuario=usuario, conhecimento=conhecimento_com_codigo,
                     # O DIAGNÓSTICO É A CONSULTA QUE MAIS PRECISA LER: ele
                     # lê o estado da instalação, o problema e o trecho do
                     # arquivo antes de dizer o que vê. A raiz e o `app` são
                     # por onde as ferramentas de leitura chegam lá.
                     raiz=raiz, app=app, versao=versao)
    with db.transaction() as con:
        con.execute(
            """UPDATE aj_problemas SET diagnostico=?, diagnostico_em=?,
                   consulta_id=?, diagnostico_codigo_arquivo=?,
                   diagnostico_codigo_linhas=?, diagnostico_codigo_sha256=?
               WHERE id=?""",
            (r["resposta"], agora, r["consulta_id"],
             trecho.arquivo if trecho else None,
             (f"{trecho.linha_inicial}-{trecho.linha_final}"
              if trecho else None),
             trecho.sha256 if trecho else None,
             int(problema_id)))
    return {"problema_id": int(problema_id), "consulta_id": r["consulta_id"],
            "diagnostico": r["resposta"],
            "codigo": trecho.auditoria if trecho else None}


# ---------------------------------------------------------- o relatório


def _bloco_do_problema(p: dict, mapa: dict | None) -> list[str]:
    onde = p.get("onde") or ""
    arquivo = MAPA.arquivo_da_tela(mapa, onde) if mapa else ""
    linhas = [
        # `#8` E NAO `8.`, PORQUE E ASSIM QUE A TELA MOSTRA. As duas vistas
        # do mesmo problema tem de trazer o MESMO texto: quem le o relatorio e
        # quem le a tela precisam achar um ao outro sem traduzir. Era isso que
        # faltava no relato #23.
        f"### #{p.get('id')} — {p.get('titulo')}",
        "",
        f"- **Origem**: {ORIGENS.get(p.get('origem'), p.get('origem'))}",
        f"- **Tela**: `{onde or '—'}`"
        + (f" — endereço `{p.get('caminho')}`" if p.get("caminho") else ""),
    ]
    if arquivo:
        # ONDE SE CONSERTA. É a única linha deste relatório que existe só para
        # quem programa — e é a que economiza a meia hora de procurar.
        linhas.append(f"- **Mora em**: `{arquivo}`")
    linhas += [
        (f"- **Aconteceu**: {p.get('vezes')} vez(es), de "
         f"{p.get('primeira_em')} a {p.get('ultima_em')}"),
        f"- **Versão**: {p.get('versao') or 'A CONFERIR'}",
        f"- **Situação**: {p.get('situacao')}"
        + (f" (já relatado em {p.get('relatado_em')} e voltou a acontecer)"
           if p.get("relatado_em") and p.get("situacao") == "ABERTO" else ""),
    ]
    if p.get("detalhe"):
        linhas += ["", "```", str(p["detalhe"]).strip(), "```"]
    if p.get("diagnostico"):
        linhas += ["", "**O que a ajuda respondeu** (conselho, não laudo):", "",
                   "> " + str(p["diagnostico"]).strip().replace("\n", "\n> ")]
    if p.get("diagnostico_codigo_arquivo"):
        linhas += [
            "",
            ("**Código lido no diagnóstico**: `"
             f"{p['diagnostico_codigo_arquivo']}` — linhas "
             f"{p.get('diagnostico_codigo_linhas') or '—'} — SHA-256 "
             f"`{p.get('diagnostico_codigo_sha256') or '—'}`"),
        ]
    return linhas + [""]


def montar_relatorio(*, problemas: list[dict], agora: str,
                     achados: list[dict] | None = None,
                     mapa: dict | None = None, versao: Any = None,
                     serventia: Any = None, gerado_por: Any = None) -> str:
    """O relatório para quem for consertar. Só calcula — não grava.

    SAI SEMPRE MASCARADO. Ele nasce para deixar a serventia: é feito para
    chegar a outra máquina. O que interessa a quem conserta é o ponto do
    programa, e nunca de quem era o CPF que estava sendo gravado quando a tela
    estourou.
    """
    sv = dict(serventia or {})
    quantos = min(len(problemas), LIMITE_DO_RELATORIO)
    partes = [
        "# Problemas do CartorioGestao",
        "",
        f"- **Serventia**: {sv.get('unit_name') or 'Serventia Extrajudicial'}"
        + (f" — CNS {sv['ri_cns']}" if sv.get("ri_cns") else ""),
        f"- **Versão do sistema**: {versao or 'A CONFERIR'}",
        f"- **Gerado em**: {agora}"
        + (f", por {gerado_por}" if gerado_por else ""),
        f"- **Problemas neste relatório**: {quantos}"
        + (f" (de {len(problemas)}; o resto fica para o próximo)"
           if len(problemas) > quantos else ""),
        "",
        "> **Dados pessoais, sensíveis e segredos foram substituídos.** Este arquivo é feito para",
        "> sair da serventia, e o que conserta o programa é o ponto onde ele",
        "> parou — não de quem era o dado que estava sendo gravado.",
        "",
        "> **A leitura da ajuda, quando existe, é conselho de uma IA** e está",
        "> marcada como tal. Quando há prova abaixo, ela leu somente o trecho",
        "> indicado do código; não executou nem alterou o programa.",
        "",
        "## Como usar isto",
        "",
        "1. Cada problema traz o arquivo onde a tela mora, medido nesta",
        "   instalação — é por ali que se começa.",
        "2. `ABERTO` com data em «já relatado» quer dizer que **voltou depois",
        "   de mandado para conserto**: ou o conserto não veio, ou não era o",
        "   conserto. Esses vêm primeiro.",
        "3. O que a conferência da casa mediu está no fim, e nem tudo ali é",
        "   defeito de programa: pendência de implantação é decisão do oficial.",
        "",
        "---",
        "",
        "## Os problemas",
        "",
    ]
    if not problemas:
        partes += ["Nenhum problema aberto nesta instalação.", ""]
    for p in problemas[:LIMITE_DO_RELATORIO]:
        partes += _bloco_do_problema(p, mapa)

    partes += ["---", "", "## A conferência da casa", ""]
    if achados:
        for a in achados:
            marca = "**GRAVE** — " if a.get("grave") else ""
            partes += [f"- {marca}{a['titulo']}", f"  - {a['detalhe']}"]
    else:
        partes.append("Nada a apontar: o que a casa sabe medir está em ordem.")
    partes.append("")

    if mapa:
        partes += [
            "---", "",
            "## O sistema, medido nesta máquina", "",
            f"- Telas: {mapa.get('quantas_telas')}",
            f"- Tabelas: {mapa.get('quantas_tabelas')}",
            f"- Arquivos de programa: {mapa.get('quantos_arquivos')}",
            "",
        ]
    return PRIV.sanitizar_texto("\n".join(partes))


def guardar_relatorio(pasta_de_dados: Any, texto: str, *, agora: str) -> Path:
    """Grava o relatório em disco e devolve o caminho. ESCREVE EM DISCO.

    Vai para uma pasta própria ao lado do banco, e não para dentro dele: é
    arquivo para levar embora, e um arquivo de texto atravessa qualquer coisa
    — pen drive, e-mail, papel — sem depender do sistema estar de pé.
    """
    destino = Path(pasta_de_dados) / PASTA_DOS_RELATORIOS
    destino.mkdir(parents=True, exist_ok=True)
    carimbo = re.sub(r"[^0-9]", "", str(agora))[:14] or "sem-data"
    caminho = destino / f"PROBLEMAS_{carimbo}.md"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def digital_do_arquivo(caminho: Any) -> str:
    """A impressão SHA-256 do arquivo, para conferir o que chegou. Só LÊ.

    É a mesma conferência que o roteiro de atualização já pede com `certutil`:
    quem recebe confere que o arquivo é o que saiu.
    """
    try:
        return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
    except OSError:
        return ""


def anotar_relatorio(con: sqlite3.Connection, *, arquivo: Any,
                     ids: list[int], agora: str, versao: Any = None,
                     sha256: Any = None, usuario: Any = None) -> int:
    """Guarda que o relatório saiu, e marca como relatados OS QUE FORAM.

    ESCREVE. Marcar é o que separa «o que já foi mandado» de «o que ainda
    não» — sem isso o próximo relatório mandaria tudo de novo, e quem
    recebesse não saberia o que é novo.

    MARCA SÓ OS QUE COUBERAM. A primeira versão marcava todos os abertos, e
    com isso um problema que ficou de fora pelo teto do relatório sairia da
    lista como se tivesse sido mandado — e ninguém consertaria o que ninguém
    recebeu.
    """
    cur = con.execute(
        """INSERT INTO aj_relatorios(arquivo, quantos, sha256, versao,
               gerado_em, gerado_por) VALUES (?,?,?,?,?,?)""",
        (str(arquivo), len(ids), str(sha256 or "") or None,
         str(versao or "") or None, agora, str(usuario or "") or None))
    for problema_id in ids:
        con.execute(
            """UPDATE aj_problemas SET situacao='RELATADO', relatado_em=?
                WHERE id=? AND situacao='ABERTO'""", (agora, int(problema_id)))
    return int(cur.lastrowid)


# ===================================================================
# IMPORTAR NOTAS POR DOCUMENTO DE TEXTO
# ===================================================================
#
# POR QUE POR DOCUMENTO, E NAO GRAVANDO DIRETO
#   O oficial autorizou gravar as notas de cumprimento. Ao tentar, o Windows
#   recusou: o banco de producao da `ReadAndExecute` ao usuario que
#   desenvolve, e escrita so ao SISTEMA — que e quem roda o servidor.
#
#   **A permissao esta certa, e nao se contorna.** Ela e o que impede um
#   processo qualquer da maquina de escrever no livro. Entao o oficial pediu o
#   caminho certo: «crie uma forma de importacao por doc de texto (...) e me
#   forneca esse documento para eu subir no sistema». Quem escreve passa a ser
#   a aplicacao, que tem direito, e quem manda escrever e ele.
#
# O FORMATO E FEITO PARA SER LIDO E CORRIGIDO A MAO
#   Nada de JSON nem planilha: o oficial precisa poder abrir o arquivo, ler o
#   que vai ser gravado e mudar uma frase antes de subir. Um bloco por nota:
#
#       [#35] ATENDIDO
#       prova: tests/test_x.py
#       O texto da nota, que pode ter
#       varias linhas.
#
#   Linha em branco separa os blocos; linha comecando por `#` e comentario.
MARCA_DE_BLOCO = "["
MARCA_DE_PROVA = "prova:"


def _ler_blocos(texto: str) -> list[dict]:
    """Quebra o documento em blocos. So le, e nao decide nada."""
    import re
    blocos: list[dict] = []
    atual: dict | None = None
    for cru in (texto or "").splitlines():
        linha = cru.rstrip()
        if linha.strip().startswith("#") and not linha.strip().startswith("[#"):
            continue
        cabeca = re.match(r"^\s*\[#(\d+)\]\s*([A-Z_]+)\s*$", linha)
        if cabeca:
            if atual:
                blocos.append(atual)
            atual = {"id": int(cabeca.group(1)), "estado": cabeca.group(2),
                     "prova": "", "linhas": []}
            continue
        if atual is None:
            continue
        if linha.strip().lower().startswith(MARCA_DE_PROVA):
            atual["prova"] = linha.split(":", 1)[1].strip()
            continue
        atual["linhas"].append(linha)
    if atual:
        blocos.append(atual)
    for b in blocos:
        b["nota"] = "\n".join(b.pop("linhas")).strip()
    return blocos


def importar_notas(con: sqlite3.Connection, texto: str, *, agora: str,
                   por: str = "") -> dict:
    """Grava as notas de um documento de texto. ESCREVE.

    **CADA BLOCO E TRATADO SOZINHO.** Um erro num deles nao derruba os outros:
    o que der certo entra, o que nao der volta na lista de recusados **com o
    motivo**. Recusar o arquivo inteiro por causa de uma linha faria o oficial
    procurar a agulha sem saber onde.

    **NAO FECHA PROBLEMA NENHUM**, e nao sobrescreve nota que ja exista sem
    que o documento diga o contrario — a regra e a mesma de
    `anotar_desenvolvimento`: quem fecha e o oficial.
    """
    gravadas, recusadas = [], []
    for b in _ler_blocos(texto):
        try:
            anotar_desenvolvimento(con, b["id"], nota=b["nota"],
                                   estado=b["estado"], prova=b["prova"],
                                   agora=agora, por=por)
            gravadas.append(b["id"])
        except ProblemaError as erro:
            recusadas.append({"id": b["id"], "porque": str(erro)})
        except Exception as erro:                              # noqa: BLE001
            recusadas.append({"id": b["id"],
                              "porque": f"não consegui gravar: {erro}"})
    return {"gravadas": gravadas, "recusadas": recusadas,
            "quantas": len(gravadas)}

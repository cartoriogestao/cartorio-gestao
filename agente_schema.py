"""O que o agente do sistema guarda — as quatro tabelas dele.

POR QUE O AGENTE TEM TABELA PRÓPRIA, E NÃO REUSA `aj_consultas`
    Porque o que se guarda é de outra natureza. `aj_consultas` guarda UMA
    pergunta e UMA resposta; uma sessão do agente guarda uma conversa com
    ferramentas, os argumentos de cada uma e o que ela devolveu. Enfiar isso
    nas colunas da ajuda faria a tela da ajuda passar a explicar um negócio que
    não é o dela, e a lista de consultas, que é do balcão, encheria de sessões
    de manutenção.

    **A separação também é de risco, e é isso que a justifica.** Apagar o
    histórico do agente não pode levar junto o registro de uma consulta que o
    escrevente fez. Tabelas separadas erram separado.

A MÁSCARA VALE AQUI TAMBÉM
    O que se grava em `ag_passos` é o que **já passou pela barreira** de
    `ajuda_privacidade.sanitizar_para_modelo`. Não é uma segunda conferência:
    é a mesma, aplicada antes de escrever. **O banco não é um lugar seguro por
    ser local** — ele vai no backup, e o backup sai da serventia.

TABELA NOVA VAI NO `SCHEMA`, NÃO EM `MIGRACOES`
    Regra da casa. `MIGRACOES` só carrega `ALTER TABLE ADD COLUMN`, e
    `INDICES_DEPOIS_DA_MIGRACAO` existe para o índice de coluna que chegou
    depois. As duas estão vazias aqui porque estas tabelas nascem inteiras.

A REVERSIBILIDADE É UM DADO, E NÃO UMA PROMESSA
    `ag_mudancas` guarda `antes` e `depois` de cada escrita. É o que permite
    desfazer sem depender de backup — e é o que faz a permissão de escrever ser
    defensável: **quem pode desfazer com um clique pode ousar mais.** Sem isso,
    «o agente conserta sozinho» seria «o agente quebra sozinho e ninguém volta
    atrás».
"""
from __future__ import annotations

import sqlite3
from typing import Any

# ---------------------------------------------------------------- os estados

ABERTA = "ABERTA"
CONCLUIDA = "CONCLUIDA"
ERRO = "ERRO"
LIMITE = "LIMITE"
RECUSADA = "RECUSADA"
# `INTERROMPIDA` e a sessao que ficou ABERTA porque o programa parou no meio da
# rodada. Nao e um quinto jeito de terminar: e o que aconteceu com uma sessao que
# ia continuar. Fica separada de `ABERTA` porque `ABERTA` quer dizer «alguem esta
# rodando agora» — e e essa a recusa que impede duas rodadas da mesma conversa.
# Sem estado proprio, a conversa interrompida ficaria presa: aberta para sempre e
# sem poder ser continuada.
INTERROMPIDA = "INTERROMPIDA"

ESTADOS = (ABERTA, CONCLUIDA, ERRO, LIMITE, RECUSADA, INTERROMPIDA)

# O RÓTULO DE CADA ESTADO, E A COR DO SELO — escritos UMA vez, e não no modelo
# de tela.
#
# **A TELA AO VIVO PRECISA DA MESMA PALAVRA, E É ISSO QUE MANDA ISTO PARA
# CÁ.** A página da sessão desenha o selo com o que o servidor mandou na
# primeira carga e o troca pelo que chega a cada segundo. Com a regra escrita no
# Jinja, o JavaScript teria de repeti-la — e a segunda versão diria «em curso»
# onde a primeira diz «parou no teto», na mesma tela, sobre a mesma sessão. É a
# mesma razão de `_agente_passos.html` e da `normalizar_nome`: onde a palavra
# importa, ela se escreve num lugar só.
ROTULO_DO_ESTADO = {
    ABERTA: ("em curso", ""),
    CONCLUIDA: ("terminou", "ok"),
    LIMITE: ("parou no teto", "media"),
    ERRO: ("falhou", "critica"),
    RECUSADA: ("recusada", "alta"),
    INTERROMPIDA: ("interrompida — dá para continuar", "media"),
}


def selo_do_estado(estado: Any) -> dict[str, str]:
    """O texto e a classe do selo de um estado. **SÓ LÊ.**

    Estado desconhecido cai em «em curso» sem estourar: a lista de estados pode
    crescer, e uma tela que quebra por causa de uma palavra nova é pior que uma
    que mostra a palavra antiga por um instante.
    """
    texto, classe = ROTULO_DO_ESTADO.get(str(estado or ""), ("em curso", ""))
    return {"estado": str(estado or ""), "texto": texto, "classe": classe}

# O tipo de cada passo. `PEDIDO` é a fala do oficial — é ela que abre a sessão
# e cada rodada seguinte. `FERRAMENTA` é o pedido do modelo e `RESULTADO` é o
# que a ferramenta devolveu: ficam separados porque um se lê em cima do outro
# na tela, e juntá-los esconderia qual dos dois falhou. `AVISO` é recado da
# casa para quem lê a tela (parou no teto, a barreira recusou), e não vai ao
# provedor.
PEDIDO, TEXTO, FERRAMENTA, RESULTADO, AVISO = (
    "PEDIDO", "TEXTO", "FERRAMENTA", "RESULTADO", "AVISO")
TIPOS_DE_PASSO = (PEDIDO, TEXTO, FERRAMENTA, RESULTADO, AVISO)

# ---------------------------------------------------------------- a config

CHAVE_PROVEDOR = "provedor_padrao"
CHAVE_MODELO = "modelo_padrao"
CHAVE_TETO_TURNOS = "teto_de_turnos"
CHAVE_TETO_SESSOES = "teto_de_sessoes_por_dia"
CHAVE_ESCRITA = "escrita_ligada"

CHAVES_CONFIG = (CHAVE_PROVEDOR, CHAVE_MODELO, CHAVE_TETO_TURNOS,
                 CHAVE_TETO_SESSOES, CHAVE_ESCRITA)

# OS PADRÕES SÃO FECHADOS. A tela abre com o agente LIGADO PARA LER e
# DESLIGADO PARA ESCREVER, e a decisão de ligar a escrita é um clique
# consciente, com o aviso ao lado. **Uma capacidade nasce desligada** — a mesma
# regra do módulo de ajuda, que também depende de alguém liberar.
PADROES: dict[str, str] = {
    CHAVE_PROVEDOR: "deepseek",
    CHAVE_MODELO: "",
    CHAVE_TETO_TURNOS: "12",
    CHAVE_TETO_SESSOES: "40",
    CHAVE_ESCRITA: "0",
}

# OS LIMITES DUROS. A config não passa daqui, mesmo que alguém escreva um número
# maior: sem teto, um laço que não fecha custa dinheiro de verdade, e o botão
# que sobe o teto não pode subir até «sem teto».
TETO_MAXIMO_DE_TURNOS = 24
TETO_MAXIMO_DE_SESSOES = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS ag_sessoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL DEFAULT '',
    pedido TEXT NOT NULL DEFAULT '',
    provedor TEXT NOT NULL DEFAULT '',
    modelo TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'ABERTA',
    turnos INTEGER NOT NULL DEFAULT 0,
    tokens_de_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_de_saida INTEGER NOT NULL DEFAULT 0,
    erro TEXT NOT NULL DEFAULT '',
    criada_em TEXT,
    criada_por TEXT,
    mexida_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_ag_sessoes_estado ON ag_sessoes(estado, id);
CREATE INDEX IF NOT EXISTS idx_ag_sessoes_dia ON ag_sessoes(criada_em);

CREATE TABLE IF NOT EXISTS ag_passos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL REFERENCES ag_sessoes(id),
    ordem INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    ferramenta TEXT NOT NULL DEFAULT '',
    chamada_id TEXT NOT NULL DEFAULT '',
    argumentos TEXT NOT NULL DEFAULT '',
    conteudo TEXT NOT NULL DEFAULT '',
    erro INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_ag_passos_sessao
    ON ag_passos(sessao_id, ordem);

CREATE TABLE IF NOT EXISTS ag_mudancas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL REFERENCES ag_sessoes(id),
    ferramenta TEXT NOT NULL,
    alvo TEXT NOT NULL DEFAULT '',
    antes TEXT NOT NULL DEFAULT '',
    depois TEXT NOT NULL DEFAULT '',
    reversivel INTEGER NOT NULL DEFAULT 1,
    criada_em TEXT,
    criada_por TEXT,
    revertida_em TEXT,
    revertida_por TEXT
);
CREATE INDEX IF NOT EXISTS idx_ag_mudancas_sessao ON ag_mudancas(sessao_id, id);

CREATE TABLE IF NOT EXISTS ag_config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = ()
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_agente_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas do agente e semeia a config. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(
            f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
    for chave, valor in PADROES.items():
        con.execute("INSERT OR IGNORE INTO ag_config(chave, valor) VALUES (?, ?)",
                    (chave, valor))


# ---------------------------------------------------------------- a config


def ler_config(con: sqlite3.Connection, chave: str) -> str:
    """O valor gravado, ou o padrão. Chave desconhecida devolve vazio."""
    linha = con.execute("SELECT valor FROM ag_config WHERE chave = ?",
                        (chave,)).fetchone()
    if not linha:
        return PADROES.get(chave, "")
    valor = linha[0] if not hasattr(linha, "keys") else linha["valor"]
    return valor if valor not in (None, "") else PADROES.get(chave, "")


def gravar_config(con: sqlite3.Connection, chave: str, valor: Any) -> None:
    """Grava um valor. Chave fora de `CHAVES_CONFIG` é recusada, não ignorada.

    Recusar alto, em vez de ignorar calado, é o que impede a tela dizer
    «guardado» sobre uma chave que ninguém gravou.
    """
    if chave not in CHAVES_CONFIG:
        raise ValueError(
            f"Configuração desconhecida do agente: {chave!r}. As que existem "
            f"são {', '.join(CHAVES_CONFIG)}.")
    con.execute(
        "INSERT INTO ag_config(chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, str(valor if valor is not None else "")))


def _inteiro(con: sqlite3.Connection, chave: str, maximo: int,
             minimo: int = 1) -> int:
    """Um inteiro da config, preso entre o mínimo e o teto duro."""
    try:
        numero = int(str(ler_config(con, chave)).strip())
    except (TypeError, ValueError):
        numero = int(PADROES[chave])
    return max(minimo, min(maximo, numero))


def teto_de_turnos(con: sqlite3.Connection) -> int:
    """Quantos turnos uma sessão pode dar antes de parar e devolver o comando."""
    return _inteiro(con, CHAVE_TETO_TURNOS, TETO_MAXIMO_DE_TURNOS)


def teto_de_sessoes(con: sqlite3.Connection) -> int:
    """Quantas sessões por dia. É o freio de gasto que a casa controla."""
    return _inteiro(con, CHAVE_TETO_SESSOES, TETO_MAXIMO_DE_SESSOES)


def escrita_ligada(con: sqlite3.Connection) -> bool:
    """Se as ferramentas que MUDAM o sistema estão liberadas. Nasce ligada=0."""
    return str(ler_config(con, CHAVE_ESCRITA)).strip() == "1"


def config_para_tela(con: sqlite3.Connection) -> dict[str, Any]:
    """O que a tela de configuração mostra. **SÓ LÊ.**"""
    return {
        "provedor_padrao": ler_config(con, CHAVE_PROVEDOR),
        "modelo_padrao": ler_config(con, CHAVE_MODELO),
        "teto_de_turnos": teto_de_turnos(con),
        "teto_de_sessoes": teto_de_sessoes(con),
        "escrita_ligada": escrita_ligada(con),
        "teto_maximo_de_turnos": TETO_MAXIMO_DE_TURNOS,
        "teto_maximo_de_sessoes": TETO_MAXIMO_DE_SESSOES,
    }


# --------------------------------------------------------------- as sessões


def abrir_sessao(con: sqlite3.Connection, *, titulo: str, pedido: str,
                 provedor: str, modelo: str, agora: str,
                 criada_por: str) -> int:
    """Abre a sessão e devolve o id. **ESCREVE.** Exige `db.transaction()`."""
    cursor = con.execute(
        "INSERT INTO ag_sessoes(titulo, pedido, provedor, modelo, estado, "
        "criada_em, criada_por, mexida_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (titulo or "", pedido or "", provedor or "", modelo or "", ABERTA,
         agora, criada_por or "", agora))
    return int(cursor.lastrowid)


def ler_sessao(con: sqlite3.Connection, sessao_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM ag_sessoes WHERE id = ?",
                       (int(sessao_id),)).fetchone()


def sessoes_recentes(con: sqlite3.Connection, limite: int = 30) -> list:
    """As últimas sessões, para a tela. **SÓ LÊ.**"""
    return list(con.execute(
        "SELECT id, titulo, pedido, provedor, modelo, estado, turnos, "
        "tokens_de_entrada, tokens_de_saida, criada_em, criada_por, mexida_em, "
        "erro FROM ag_sessoes ORDER BY id DESC LIMIT ?", (int(limite),)))


def atualizar_sessao(con: sqlite3.Connection, sessao_id: int, *,
                     estado: str, turnos: int, tokens_de_entrada: int,
                     tokens_de_saida: int, erro: str,
                     agora: str, modelo: str | None = None) -> None:
    """Fecha a conta da sessão: estado, turnos, gasto e erro. **ESCREVE.**

    O gasto é SOMADO pelo chamador e gravado aqui por inteiro, e não somado
    aqui: `entrada` e `saida` acumulam dentro de `agente.py`, que é quem lê a
    resposta do provedor, e uma segunda soma neste lugar contaria duas vezes.
    """
    if estado not in ESTADOS:
        raise ValueError(
            f"Estado desconhecido do agente: {estado!r}. Os que existem são "
            f"{', '.join(ESTADOS)}.")
    if modelo:
        con.execute(
            "UPDATE ag_sessoes SET estado=?, turnos=?, tokens_de_entrada=?, "
            "tokens_de_saida=?, erro=?, modelo=?, mexida_em=? WHERE id=?",
            (estado, int(turnos), int(tokens_de_entrada),
             int(tokens_de_saida), erro or "", modelo, agora,
             int(sessao_id)))
        return
    con.execute(
        "UPDATE ag_sessoes SET estado=?, turnos=?, tokens_de_entrada=?, "
        "tokens_de_saida=?, erro=?, mexida_em=? WHERE id=?",
        (estado, int(turnos), int(tokens_de_entrada), int(tokens_de_saida),
         erro or "", agora, int(sessao_id)))


def contagem_do_dia(con: sqlite3.Connection, *, desde: str) -> dict[str, int]:
    """Quantas sessões e quantos tokens desde uma hora. **SÓ LÊ.**

    É o que sustenta o teto diário. Conta por `criada_em`, e não por
    `mexida_em`: o freio é sobre **quanto se pede ao provedor**, e uma sessão
    antiga reaberta não é um pedido novo.
    """
    linha = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_de_entrada), 0), "
        "COALESCE(SUM(tokens_de_saida), 0) FROM ag_sessoes "
        "WHERE criada_em >= ?", (desde,)).fetchone()
    return {"sessoes": int(linha[0] or 0), "entrada": int(linha[1] or 0),
            "saida": int(linha[2] or 0)}


# --------------------------------------------------------------- os passos


def proxima_ordem(con: sqlite3.Connection, sessao_id: int) -> int:
    """O número do próximo passo. **SÓ LÊ.**"""
    linha = con.execute(
        "SELECT COALESCE(MAX(ordem), 0) FROM ag_passos WHERE sessao_id = ?",
        (int(sessao_id),)).fetchone()
    return int(linha[0] or 0) + 1


def registrar_passo(con: sqlite3.Connection, sessao_id: int, *, ordem: int,
                    tipo: str, ferramenta: str = "", chamada_id: str = "",
                    argumentos: Any = "",
                    conteudo: str = "", erro: bool = False,
                    agora: str) -> int:
    """Grava um passo do turno. **ESCREVE.**

    `conteudo` já chega mascarado: quem grava não sanitiza, porque sanitizar
    aqui seria a segunda régua. A conferência é a de `agente.py`, uma só.

    `chamada_id` é o identificador que o provedor deu ao pedido da ferramenta.
    Ele é guardado porque é o que casa o pedido com o resultado na hora de
    remontar a conversa: sem ele, a sessão interrompida não se continua, e a
    única saída seria repetir a pergunta.
    """
    if tipo not in TIPOS_DE_PASSO:
        raise ValueError(
            f"Tipo de passo desconhecido: {tipo!r}. Os que existem são "
            f"{', '.join(TIPOS_DE_PASSO)}.")
    cursor = con.execute(
        "INSERT INTO ag_passos(sessao_id, ordem, tipo, ferramenta, chamada_id, "
        "argumentos, conteudo, erro, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (int(sessao_id), int(ordem), tipo, ferramenta or "", chamada_id or "",
         str(argumentos or ""), conteudo or "", 1 if erro else 0, agora))
    return int(cursor.lastrowid)


def passos_da_sessao(con: sqlite3.Connection, sessao_id: int) -> list:
    """A conversa inteira, em ordem. **SÓ LÊ.**"""
    return list(con.execute(
        "SELECT * FROM ag_passos WHERE sessao_id = ? ORDER BY ordem, id",
        (int(sessao_id),)))


def passos_desde(con: sqlite3.Connection, sessao_id: int, *,
                 ordem: int = 0) -> list:
    """Os passos que a tela ainda não viu. **SÓ LÊ.**

    `ordem` é o CURSOR: quem desenha a conversa guarda até onde leu e pergunta
    pelo resto. É o que faz a tela mostrar cada ferramenta no segundo em que ela
    roda sem reler a conversa inteira a cada pergunta — e a diferença não é de
    elegância: o resultado de uma ferramenta pode ter dezenas de linhas, e a
    tela pergunta a cada segundo.
    """
    return list(con.execute(
        "SELECT * FROM ag_passos WHERE sessao_id = ? AND ordem > ? "
        "ORDER BY ordem, id", (int(sessao_id), int(ordem or 0))))


# ------------------------------------------------------------- as mudanças


def registrar_mudanca(con: sqlite3.Connection, sessao_id: int, *,
                      ferramenta: str, alvo: str, antes: str, depois: str,
                      reversivel: bool = True, agora: str,
                      criada_por: str) -> int:
    """Grava o antes e o depois de uma escrita. **ESCREVE.**

    Este é o registro que faz a permissão de escrever ser defensável: sem ele,
    «o agente conserta sozinho» seria «o agente quebra sozinho e ninguém volta
    atrás».
    """
    cursor = con.execute(
        "INSERT INTO ag_mudancas(sessao_id, ferramenta, alvo, antes, depois, "
        "reversivel, criada_em, criada_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (int(sessao_id), ferramenta or "", alvo or "", str(antes or ""),
         str(depois or ""), 1 if reversivel else 0, agora, criada_por or ""))
    return int(cursor.lastrowid)


def ler_mudanca(con: sqlite3.Connection, mudanca_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM ag_mudancas WHERE id = ?",
                       (int(mudanca_id),)).fetchone()


def mudancas_da_sessao(con: sqlite3.Connection, sessao_id: int) -> list:
    """O que a sessão mudou, para a tela mostrar o que houve. **SÓ LÊ.**"""
    return list(con.execute(
        "SELECT * FROM ag_mudancas WHERE sessao_id = ? ORDER BY id",
        (int(sessao_id),)))


def mudancas_desde(con: sqlite3.Connection, sessao_id: int, *,
                   mudanca_id: int = 0) -> list:
    """As mudanças que a tela ainda não viu. **SÓ LÊ.**

    Mesmo cursor dos passos, e pelo mesmo motivo: **o que o agente muda tem de
    aparecer na hora**, com o botão de voltar atrás do lado. Mudança que só
    aparecesse ao recarregar a página seria mudança que ninguém viu acontecer —
    e a escrita é justamente a permissão que este módulo tem de defender.
    """
    return list(con.execute(
        "SELECT * FROM ag_mudancas WHERE sessao_id = ? AND id > ? ORDER BY id",
        (int(sessao_id), int(mudanca_id or 0))))


def mudancas_recentes(con: sqlite3.Connection, limite: int = 40) -> list:
    """As últimas mudanças de qualquer sessão — a lista do desfazer. **SÓ LÊ.**"""
    return list(con.execute(
        "SELECT * FROM ag_mudancas ORDER BY id DESC LIMIT ?", (int(limite),)))


def marcar_revertida(con: sqlite3.Connection, mudanca_id: int, *,
                     agora: str, revertida_por: str) -> None:
    """Marca que a mudança voltou atrás. **ESCREVE.**

    A mudança **não é apagada da lista**: ela continua na tela, dizendo quem
    desfez e quando. Uma linha que some deixaria o histórico contando uma
    história em que nada aconteceu.
    """
    con.execute(
        "UPDATE ag_mudancas SET revertida_em = ?, revertida_por = ? WHERE id = ?",
        (agora, revertida_por or "", int(mudanca_id)))

"""
RCPJ e RTD — abrir o registro, averbar, cancelar.

COMO SE USA
    with db.transaction() as con:
        registro_id = abrir_registro(
            con, serie="PJ_A", natureza="Estatuto de associação",
            requerente_nome="ASSOCIAÇÃO X", sv=sv, agora=agora,
            data_extenso=hoje, teor=texto)
    audit(...)                      # FORA da transação, como no resto da casa

SERIES CONHECIDAS, E A ATRIBUICAO DE CADA UMA
    PJ_A, PJ_B  — RCPJ (atribuição 3)
    TD_B, TD_C, TD_F — RTD (atribuição 4)

    A atribuição não é parâmetro: vem da série, em `livro_nucleo.SERIES`, e é
    de lá que este módulo a lê — dois módulos não podem discordar de qual
    atribuição uma série pertence.

O QUE ESTE MODULO NAO FAZ
    Não emite selo e não cobra custas — isso é da camada web
    (`atribuicoes_web` / `rg_web`), opcional, na mesma transação do
    lançamento. A regra da casa é: domínio não sela/cobra; a TELA faz.
    Inventar selo aqui seria gravar número sem o escrevente ter digitado.

    A amarração automática ao protocolo geral do caixa também não: a tela
    oferece o select (`protocolo_id`). A regra "averbação consome
    protocolo no RTD e não no RCPJ" (LEVANTAMENTO_QUATRO_ATRIBUICOES.md)
    permanece anotada como fato medido, não como código.

FUNDAMENTO
    Lei 6.015/1973, arts. 114 a 148 (RCPJ) e 127 a 130 (RTD).
"""
from __future__ import annotations

import sqlite3

import escrituracao as ESC
import livro_nucleo as LN


class RgError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


SERIES_RCPJ = ("PJ_A", "PJ_B")
SERIES_RTD = ("TD_B", "TD_C", "TD_F")
SERIES_CONHECIDAS = SERIES_RCPJ + SERIES_RTD

# Medido em LEVANTAMENTO_QUATRO_ATRIBUICOES.md, `tbTD_Propriedade`:
# `bitIncrementoProtocoloAVTD` é verdadeiro só no RTD. Ainda não gera
# número de protocolo — ver o cabeçalho do módulo — mas a distinção já
# fica registrada, para quando a integração existir.
AVERBACAO_CONSOME_PROTOCOLO = {3: False, 4: True}

SITUACOES_REGISTRO = ("ATIVO", "CANCELADO")
TIPOS_ATO = ("REGISTRO", "AVERBACAO", "CANCELAMENTO")

# OS DOIS ITENS DO PROTOCOLO QUE SELAM JUNTO COM O ATO E NÃO SÃO O ATO.
#
#   Medido na produção em 09/10/2026, na averbação 378 (registro 148, Caixa
#   Escolar Santa Isabel): o protocolo trouxe `15.1` («Prenotação de títulos»,
#   selo PRENOT…), `15.9.1` e `15.9.2` (a averbação), e a coluna `selo` ficou
#   com o da PRENOTAÇÃO, porque era o primeiro da lista. A etiqueta colada no
#   título saiu **seis vezes** declarando um selo de prenotação de R$ 42,60
#   onde devia estar o da averbação. `15.22` é o arquivamento, que já tinha
#   coluna própria (`selo_arquivamento`) desde 11/09/2026.
CODIGO_TJ_PRENOTACAO = "15.1"
CODIGO_TJ_ARQUIVAMENTO = "15.22"


def papel_dos_selos(saidos: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    """De `(codigo_tj, numero)` dos selos que saíram para UM ato, qual vai em
    `selo` e qual em `selo_arquivamento`. Só calcula.

    `selo` é o do próprio ato — o primeiro que não seja prenotação nem
    arquivamento. **A prenotação só entra em `selo` se ela for tudo o que
    saiu além do arquivamento**: ato sem número na coluna é pior que ato com
    o selo da prenotação, que ao menos é dele.
    """
    principal = prenotacao = arquivamento = None
    for codigo, numero in saidos:
        codigo = str(codigo or "").strip()
        if codigo == CODIGO_TJ_ARQUIVAMENTO:
            arquivamento = arquivamento or numero
        elif codigo == CODIGO_TJ_PRENOTACAO:
            prenotacao = prenotacao or numero
        else:
            principal = principal or numero
    return principal or prenotacao, arquivamento


def _serie(codigo: str) -> LN.Serie:
    if codigo not in SERIES_CONHECIDAS:
        raise RgError(
            f"Série {codigo!r} não é de RCPJ nem de RTD. As que existem "
            f"são: {', '.join(SERIES_CONHECIDAS)}.")
    return LN.serie(codigo)


# --------------------------------------------------------------- consultas


def registro(con: sqlite3.Connection, registro_id: int) -> sqlite3.Row | None:
    """O registro, com tudo que foi cadastrado. Só LÊ."""
    return con.execute(
        "SELECT * FROM rg_registros WHERE id=?", (int(registro_id),)).fetchone()


def atos_do(con: sqlite3.Connection, registro_id: int) -> list[sqlite3.Row]:
    """Os atos do registro, na ordem em que aconteceram. Só LÊ."""
    return list(con.execute(
        "SELECT * FROM rg_atos WHERE registro_id=? ORDER BY id",
        (int(registro_id),)))


def registro_por_origem(con: sqlite3.Connection, origem: str,
                        origem_chave: str) -> sqlite3.Row | None:
    """O registro de uma chave de origem, ou None. Só LÊ."""
    return con.execute(
        "SELECT * FROM rg_registros WHERE origem=? AND origem_chave=?",
        (origem, origem_chave)).fetchone()


# --------------------------------------------------------- abrir o registro


def abrir_registro(con: sqlite3.Connection, *, serie: str, sv: dict,
                   agora: str, data_extenso: str,
                   natureza: str | None = None,
                   requerente_nome: str | None = None,
                   requerente_documento: str | None = None,
                   teor: str | None = None,
                   teor_formato: str = "texto",
                   usuario: str | None = None, origem: str = "MANUAL",
                   origem_chave: str | None = None,
                   importacao_id: int | None = None) -> dict:
    """Abre o registro e lavra o ato de REGISTRO. ESCREVE.

    Cada série é folha nova (`livro_nucleo.SERIES[serie].folha_nova`): o
    registro nasce com o próprio ato já ocupando lugar — não há "registro
    sem ato", ao contrário do título de Protesto, que existe antes do
    apontamento.

    Carga repetível por construção: reapresentar a mesma (origem,
    origem_chave) devolve o id já existente.
    """
    s = _serie(serie)
    chave = (origem_chave or "").strip() or None
    if origem == "EOFICIO" and not chave:
        raise RgError(
            "Registro de origem EOFICIO precisa de uma chave de origem, "
            "para a carga poder ser repetida sem duplicar.")
    if chave:
        existente = registro_por_origem(con, origem, chave)
        if existente:
            return {"registro_id": int(existente["id"]), "reaproveitado": True}

    cur = con.execute(
        """INSERT INTO rg_registros(atribuicao, serie, natureza,
               requerente_nome, requerente_documento, situacao, teor,
               teor_formato, origem, origem_chave, importacao_id,
               criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (s.atribuicao, serie, natureza, requerente_nome, requerente_documento,
         "ATIVO", teor, teor_formato, origem, chave, importacao_id, agora,
         usuario))
    registro_id = int(cur.lastrowid)

    cur = con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, data_ato, teor,
               teor_formato, origem, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?)""",
        (registro_id, "REGISTRO", agora, teor, teor_formato, origem, agora,
         usuario))
    ato_id = int(cur.lastrowid)

    lugar = ESC.reservar(con, serie, "rg_atos", ato_id, sv=sv, agora=agora,
                         data_extenso=data_extenso, paginas=1, usuario=usuario)
    con.execute(
        """UPDATE rg_atos SET livro_id=?, folha=?, verso=?, numero_ordem=?,
                              rotulo=? WHERE id=?""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    con.execute("UPDATE rg_registros SET numero=? WHERE id=?",
               (lugar["numero_ordem"], registro_id))
    return {"registro_id": registro_id, "ato_id": ato_id,
           "reaproveitado": False, **lugar}


# -------------------------------------------------------------- a averbacao


def lancar_averbacao(con: sqlite3.Connection, registro_id: int, *, teor: str,
                     sv: dict, agora: str, data_extenso: str,
                     teor_formato: str = "texto",
                     usuario: str | None = None,
                     origem: str = "MANUAL") -> dict:
    """Lavra a averbação, em folha nova. ESCREVE.

    Ocupa lugar PRÓPRIO no livro — a série é folha nova, e o E-Ofício mede
    cada ato como uma escritura à parte, não como anotação na folha do
    registro original. Só cabe em registro ATIVO.
    """
    reg = registro(con, registro_id)
    if not reg:
        raise RgError(f"Registro {registro_id} não encontrado.")
    if reg["situacao"] != "ATIVO":
        raise RgError(
            f"O registro está com situação {reg['situacao']} — só se "
            f"averba registro ativo.")
    razao = (teor or "").strip()
    if len(razao) < 10:
        raise RgError(
            "O teor da averbação precisa de pelo menos dez letras.")

    cur = con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, data_ato, teor,
               teor_formato, origem, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?)""",
        (registro_id, "AVERBACAO", agora, razao, teor_formato, origem, agora,
         usuario))
    ato_id = int(cur.lastrowid)

    lugar = ESC.reservar(con, reg["serie"], "rg_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    con.execute(
        """UPDATE rg_atos SET livro_id=?, folha=?, verso=?, numero_ordem=?,
                              rotulo=? WHERE id=?""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    return {"registro_id": registro_id, "ato_id": ato_id, **lugar}


# ---------------------------------------------------------- o cancelamento


def lancar_cancelamento(con: sqlite3.Connection, registro_id: int, *,
                        motivo: str, sv: dict, agora: str,
                        data_extenso: str, usuario: str | None = None,
                        origem: str = "MANUAL") -> dict:
    """Cancela o registro, com o ato próprio de cancelamento. ESCREVE.

    Como a averbação, ocupa lugar próprio no livro — em folha nova. Só cabe
    em registro ATIVO; não há cancelamento de cancelamento.
    """
    reg = registro(con, registro_id)
    if not reg:
        raise RgError(f"Registro {registro_id} não encontrado.")
    if reg["situacao"] != "ATIVO":
        raise RgError(
            f"O registro já está com situação {reg['situacao']}.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise RgError(
            "Escreva o motivo do cancelamento com pelo menos dez letras.")

    cur = con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, data_ato,
               motivo_cancelamento, origem, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?)""",
        (registro_id, "CANCELAMENTO", agora, razao, origem, agora, usuario))
    ato_id = int(cur.lastrowid)

    lugar = ESC.reservar(con, reg["serie"], "rg_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    con.execute(
        """UPDATE rg_atos SET livro_id=?, folha=?, verso=?, numero_ordem=?,
                              rotulo=? WHERE id=?""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    con.execute("UPDATE rg_registros SET situacao='CANCELADO' WHERE id=?",
               (registro_id,))
    return {"registro_id": registro_id, "ato_id": ato_id, "motivo": razao,
           **lugar}


# ------------------------------------------------- corrigir dados cadastrais


def corrigir_requerente(con: sqlite3.Connection, registro_id: int, *,
                        requerente_nome: str | None,
                        requerente_documento: str | None,
                        motivo: str) -> dict:
    """Corrige o nome/documento do requerente NO CADASTRO. ESCREVE.

    **ISTO NÃO É EDIÇÃO DE TEOR** — a mesma distinção de `ri_correcoes.py`.
    O teor de cada ato (a ata, a averbação) já congelou o que foi escrito
    naquele dia, e continua sendo a fonte da verdade sobre o que aconteceu
    no livro; esta função corrige só `rg_registros.requerente_nome`/
    `requerente_documento` — o CADASTRO em volta do registro, usado para
    achar o registro na lista e para preencher "Denominação" na certidão e
    na etiqueta.

    Pedido do oficial em 12/09/2026: uma pessoa jurídica muda de nome (por
    averbação, já lavrada) e o cadastro continuava com o nome antigo — sem
    tela nenhuma para corrigir isso, quem procurasse pelo nome novo não
    achava o registro. `motivo` é obrigatório e sempre citado na auditoria,
    com o nome/documento de ANTES ao lado do de depois: é assim que a
    correção fica visível, e não um `UPDATE` silencioso.
    """
    reg = registro(con, registro_id)
    if not reg:
        raise RgError(f"Registro {registro_id} não encontrado.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise RgError(
            "Escreva o motivo da correção com pelo menos dez letras.")
    novo_nome = (requerente_nome or "").strip() or None
    novo_doc = (requerente_documento or "").strip() or None
    con.execute(
        "UPDATE rg_registros SET requerente_nome=?, requerente_documento=? "
        "WHERE id=?", (novo_nome, novo_doc, registro_id))
    return {
        "registro_id": registro_id, "motivo": razao,
        "requerente_nome_antes": reg["requerente_nome"],
        "requerente_documento_antes": reg["requerente_documento"],
        "requerente_nome_depois": novo_nome,
        "requerente_documento_depois": novo_doc,
    }

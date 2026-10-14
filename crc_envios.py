"""O RASTRO DO ENVIO À CRC — relato do oficial em 11/09/2026: "os assentos
não ficaram lá nas cargas [e] já foram enviados", sem opção de dizer isso ao
sistema.

`crc_carga.py` só mede e avisa — há teste que varre o módulo procurando
INSERT, UPDATE e DELETE, porque quem corrige o assento é a tela de editar, e
não a carga. Gravar que um lote foi enviado é outra coisa: é registrar um
FATO NOVO (isto saiu daqui), não corrigir o assento. Por isso mora aqui, e
não em `crc_carga.py`.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from crc_carga import CrcError


def registrar_envio(con: sqlite3.Connection, assentos: list[int], *,
                    agora: str, por: Any, canal: str, ambiente: str = "",
                    resposta: str = "", nota: str = "") -> int:
    """Grava que estes assentos foram enviados à CRC. Devolve o id do lote.

    **DOIS CANAIS, E OS DOIS FICAM NA MESMA TABELA** — a vida é a mesma
    (um grupo de assentos saiu daqui num momento, por alguém), e o que
    muda é o que se sabe depois: o `WEBSERVICE` traz a resposta da
    Central; o `MANUAL` traz a nota de quem confirmou o upload no site
    dela. Duas tabelas divergiriam no primeiro conserto.

    **NÃO GRAVA SE NÃO HOUVER ASSENTO** — lote vazio não é lote, é clique
    errado, e registrá-lo poluiria o histórico com um envio que não
    aconteceu.
    """
    if not assentos:
        raise CrcError("Nenhum assento para registrar como enviado.")
    cur = con.execute(
        """INSERT INTO rc_crc_lotes (canal, ambiente, quantos, resposta,
               nota, enviado_em, enviado_por)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (canal, ambiente, len(assentos), resposta, nota, agora, por))
    lote_id = int(cur.lastrowid)
    con.executemany(
        "INSERT INTO rc_crc_lote_assentos (lote_id, assento_id) VALUES (?, ?)",
        [(lote_id, a) for a in assentos])
    return lote_id


def historico_de_envios(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Os lotes enviados, do mais recente para o mais antigo. Só lê.

    É o que responde "o que foi enviado, quando, por quem, e o que a
    Central disse" — meses depois, sem precisar confiar na memória de
    quem estava no balcão naquele dia.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM rc_crc_lotes ORDER BY enviado_em DESC LIMIT ?",
        (limite,))]


def assentos_do_lote(con: sqlite3.Connection, lote_id: int) -> list[dict]:
    """Os assentos de um lote de envio, com nome e espécie. Só lê."""
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT a.id, a.especie, a.numero, a.nome, a.matricula
             FROM rc_crc_lote_assentos la
             JOIN rc_assentos a ON a.id = la.assento_id
            WHERE la.lote_id = ?
         ORDER BY a.data_ato, a.id""", (lote_id,))]

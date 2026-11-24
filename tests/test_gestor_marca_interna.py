"""A marca interna das assinaturas não é campo de modelo (G002, 24/11/2026).

`notas_teor.MARCA_ASSINATURAS` separa o teor do bloco de assinaturas, e a regra
MODELO_NAO_PREENCHIDO a lia como `@campo`: um ato lavrado e selado virava achado
crítico que ninguém podia resolver. A marca não chega ao papel (traslado, termo,
rascunho e certidão a cortam; a ficha a tira da prévia e não imprime a caixa).
A regra ignora exatamente ela, e continua cobrando o resto do texto.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_conferencia as GC                                  # noqa: E402
from notas_teor import MARCA_ASSINATURAS                          # noqa: E402

AGORA = "2026-10-06T08:00:00"
HOJE = date(2026, 10, 6)


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _ato(con, corpo: str) -> int:
    teor = f"<p>PROCURAÇÃO DE EXEMPLO. {corpo} Dou fé.</p>\n{MARCA_ASSINATURAS}\n<p>___</p>"
    return int(con.execute(
        """INSERT INTO nt_atos (tipo, data, situacao, selo, teor, criado_em)
           VALUES ('PROCURACAO', '2026-10-01', 'LAVRADO', 'SELOTESTE0001', ?, ?)""",
        (teor, AGORA)).lastrowid)


def _achados_do_ato(con, aid: int) -> list[dict]:
    return [a for a in GC.conferir(con, HOJE)
            if a["regra"] == "MODELO_NAO_PREENCHIDO" and a["chave"] == f"MARCADOR:nt_atos:{aid}"]


def test_so_a_marca_de_assinaturas_nao_e_cobrada(con):
    assert _achados_do_ato(con, _ato(con, "Sem campo nenhum.")) == []


@pytest.mark.parametrize("campo", ["{{ outorgado }}", "@procurador", "[INSERIR CPF]",
                                   "@@OUTRA_MARCA_INTERNA@@"])
def test_o_resto_do_texto_continua_cobrado(con, campo):
    achados = _achados_do_ato(con, _ato(con, campo))
    assert len(achados) == 1 and achados[0]["gravidade"] == "CRITICO"
    assert "FIM_DO_TEOR" not in achados[0]["detalhe"]


def test_a_marca_tirada_nao_cola_um_campo_novo(con):
    """Tirada sem deixar espaço, «@» + marca + «nome» viraria o campo «@nome»."""
    aid = int(con.execute(
        """INSERT INTO nt_atos (tipo, data, situacao, selo, teor, criado_em)
           VALUES ('PROCURACAO', '2026-10-01', 'LAVRADO', 'SELOTESTE0001', ?, ?)""",
        (f"<p>Dou fé.</p>{MARCA_ASSINATURAS}nome", AGORA)).lastrowid)
    assert _achados_do_ato(con, aid) == []

"""A página dos desistidos e cancelados sem selo. Só a leitura."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from test_protesto_desistencia import AGORA, SV, titulo  # noqa: E402

import protesto as PT
import protesto_encerrados_sem_selo as PESS
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema


@pytest.fixture()
def con():
    c = conexao_de_teste()
    init_nucleo_schema(c)
    init_pt_schema(c)
    yield c
    c.close()


def _desistir(con, protocolo: str, numero: str) -> int:
    tid = titulo(con, protocolo=protocolo, numero=numero)
    PT.lancar_desistencia(con, tid, motivo="Credor desistiu do protesto",
                          agora=AGORA)
    return tid


def test_separa_a_casa_do_acervo_e_deixa_de_fora_quem_tem_selo(con):
    _desistir(con, "2611040001", "0304540101")
    acervo = _desistir(con, "2601010001", "VELHO-1")
    con.execute(
        "UPDATE pt_atos SET origem='EOFICIO' WHERE titulo_id=? AND tipo='DESISTENCIA'",
        (acervo,))
    con.execute("UPDATE pt_titulos SET origem='EOFICIO' WHERE id=?", (acervo,))
    com_selo = _desistir(con, "2601010002", "COM-SELO")
    con.execute(
        "UPDATE pt_atos SET selo='PROTIT000000TESTE0001' "
        "WHERE titulo_id=? AND tipo='DESISTENCIA'",
        (com_selo,))
    lista = PESS.listar(con)
    assert [x["numero_titulo"] for x in lista["da_casa"]] == ["0304540101"]
    assert [x["numero_titulo"] for x in lista["acervo"]] == ["VELHO-1"]
    assert lista["da_casa"][0]["situacao"] == "DESISTIDO"
    assert lista["da_casa"][0]["tipo"] == "DESISTENCIA"


def test_o_protesto_sem_selo_nao_entra_nesta_lista(con):
    tid = titulo(con, protocolo="2610070001", numero="31122007610")
    con.execute(
        """INSERT INTO pt_atos (titulo_id, tipo, data_ato, detalhe_json, origem,
               criado_em, selo)
           VALUES (?, 'PROTESTO', ?, '{}', 'MANUAL', ?, '')""",
        (tid, AGORA, AGORA))
    con.execute("UPDATE pt_titulos SET situacao='PROTESTADO' WHERE id=?", (tid,))
    lista = PESS.listar(con)
    assert lista["da_casa"] == [] and lista["acervo"] == []

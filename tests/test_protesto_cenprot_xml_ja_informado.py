"""O título já informado PAGO num D entra no P quando for protestado (29/10/2026).

O CASO: o 350574/2 aparece «1-Pago» na CENPROT por causa do D desta casa de
21/10/2026, e aqui o pagamento foi tornado sem efeito; o título foi intimado
por edital e o protesto é em 31/10. Regra do oficial: a situação que veio do
nosso XML se corrige mandando o XML com a situação nova — e a situação nova
desse título é o P do protesto.

MEDIDO NO GERADOR (`protesto_cenprot_xml.pendentes`): ele escolhe o ato pelo
TIPO, vivo, ainda sem arquivo e que não veio do E-Ofício — e não olha se o
título já foi a um D. Este teste guarda isso: um «já informado» que
escondesse o P deixaria a CENPROT dizendo «pago» para sempre.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import protesto_cenprot_xml as X  # noqa: E402
from test_protesto_cenprot_xml_tela import (_con, chave_e_cert, pronto,  # noqa: E402,F401
                                            s)


def _ja_informado_pago_num_d(s, titulo_id) -> int:
    """O D de antes, com o pagamento dele tornado sem efeito aqui."""
    con = _con(s)
    with con:
        xml_id = con.execute(
            """INSERT INTO pt_cenprot_xml(letra, dia, sequencial, nome_arquivo,
                   conteudo, sha256, titulos, gerado_em)
               VALUES ('D','2026-10-12',1,'MA-2199999-01-D-20261012-01.xml',?,?,1,
                       '2026-10-12T13:45:00')""", (b"<x/>", "0" * 64)).lastrowid
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
                   criado_em, cancelado, motivo_cancelamento, cenprot_xml_id)
               VALUES (?,'PAGAMENTO','2026-10-11','{}','MANUAL',
                       '2026-10-11T10:00:00',1,'TORNADO SEM EFEITO (teste)',?)""",
            (titulo_id, xml_id))
    con.close()
    return int(xml_id)


def test_o_titulo_ja_informado_pago_num_d_entra_no_p(pronto, s):
    _ja_informado_pago_num_d(s, pronto)
    lista = X.pendentes(_con(s), "P")
    assert [i["titulo_id"] for i in lista["entram"]] == [pronto], lista["fora"]
    assert lista["entram"][0]["titulo"]["ocorrencia"] == "2"


def test_e_o_d_tornado_sem_efeito_nao_volta_a_fila_do_d(pronto, s):
    """O pagamento tornado sem efeito não sobe de novo como pago."""
    _ja_informado_pago_num_d(s, pronto)
    assert X.pendentes(_con(s), "D") == {"entram": [], "fora": []}

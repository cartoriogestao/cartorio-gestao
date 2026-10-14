"""Lista padrao do protocolo geral inclui A_PAGAR (em andamento).

O balcao nao achava OP com custas lancadas porque o filtro padrao era so
ABERTO. Ex.: 2026.09.23 Otavio Cunha Barros de Castelo.
"""
from __future__ import annotations


def test_filtro_andamento_inclui_a_pagar(cg_casa_logada):
    casa = cg_casa_logada
    db = casa["db"]
    client = casa["c"]

    with db.transaction() as con:
        con.execute(
            """INSERT INTO cx_protocolos
               (numero, data_abertura, hora, atribuicao, interessado,
                assunto, situacao, tipo, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2099.01.1", "2099-01-01", "10:00", "RI",
             "OTAVIO CUNHA BARROS DE CASTELO TESTE",
             "BAIXA DE HIPOTECA", "A_PAGAR", "SERVICO",
             "2099-01-01T10:00:00"),
        )
        pid = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
        con.execute(
            """INSERT INTO cx_protocolo_atos
               (protocolo_id, descricao, codigo_ato, quantidade, valor_total,
                emolumentos, quitado)
               VALUES (?, ?, ?, 1, ?, ?, 0)""",
            (pid, "ato teste", "16.22.2", "10,00", "10,00"),
        )

    r = client.get(
        "/caixa/protocolos?busca=OTAVIO+CUNHA+BARROS+DE+CASTELO+TESTE"
    )
    assert r.status_code == 200
    assert "2099.01.1" in r.get_data(as_text=True)

    r2 = client.get(
        "/caixa/protocolos?situacao=ABERTO"
        "&busca=OTAVIO+CUNHA+BARROS+DE+CASTELO+TESTE"
    )
    assert r2.status_code == 200
    assert "2099.01.1" not in r2.get_data(as_text=True)

    r3 = client.get(
        "/caixa/protocolos?situacao=A_PAGAR"
        "&busca=OTAVIO+CUNHA+BARROS+DE+CASTELO+TESTE"
    )
    assert r3.status_code == 200
    assert "2099.01.1" in r3.get_data(as_text=True)

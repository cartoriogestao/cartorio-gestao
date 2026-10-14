"""Deixa um ato de notas de teste em condição de ir à CENSEC antes de lavrar.

POR QUE ESTE AJUDANTE EXISTE — 09/10/2026
    A lavratura passou a TRAVAR o ato que a CENSEC recusaria (ordem do
    oficial: «cria travas na lavratura quando tivermos esses problemas e nao
    for possivel enviar pra censec»; ver `notas_censec.impedimentos_para_lavrar`).
    Os testes de tela que lavram escritura sem parte e sem valor testam OUTRA
    coisa — a folha, o termo, as páginas, o selo — e passaram a bater na trava.

    Este ajudante completa só o que a CEP exige e o teste não informou, sem
    mudar o que o teste mede: parte com qualificação, valor ZERO quando não
    há valor (zero continua sendo «sem valor» para o caminho do selo, que
    decide por `bool(valor_transacao)`) e uma natureza da tabela do CNB.
    O que o teste já informou não é tocado.
"""
from __future__ import annotations

import sqlite3

NATUREZA_DE_TESTE = 14      # DECLARAÇÃO — não exige ato anterior (35 exige)


def preparar(banco, ato_id: int) -> None:
    con = sqlite3.connect(str(banco))
    try:
        tipo = con.execute("SELECT tipo FROM nt_atos WHERE id=?",
                           (ato_id,)).fetchone()[0]
        tem_parte = con.execute("SELECT COUNT(*) FROM nt_ato_partes WHERE ato_id=?",
                                (ato_id,)).fetchone()[0]
        if not tem_parte:
            con.execute("""INSERT INTO nt_ato_partes
                               (ato_id, nome, nome_norm, qualificacao, ordem, criado_em)
                           VALUES (?, 'PARTE DE TESTE', 'parte de teste', 'OUTORGANTE',
                                   1, '2026-10-09T00:00:00')""", (ato_id,))
        con.execute("""UPDATE nt_ato_partes SET qualificacao='OUTORGANTE'
                        WHERE ato_id=? AND (qualificacao IS NULL OR qualificacao='')""",
                    (ato_id,))
        if tipo == "ESCRITURA":
            con.execute("""UPDATE nt_atos SET valor_transacao=0
                            WHERE id=? AND valor_transacao IS NULL""", (ato_id,))
            con.execute("""UPDATE nt_atos SET natureza_censec=?
                            WHERE id=? AND natureza_censec IS NULL""",
                        (NATUREZA_DE_TESTE, ato_id))
        con.commit()
    finally:
        con.close()

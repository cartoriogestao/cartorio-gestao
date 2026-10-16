# -*- coding: utf-8 -*-
"""A lista dos atos de UM livro das Notas abre (15/10/2026).

A tela `notas_atos.html` escreve «Atos do livro N — <tipo>» quando vem
`livro_id`, e o nome do tipo vem de `TIPOS_LIVRO`. A rota não o entregava, e
a tela do livro dava HTTP 500 (`'TIPOS_LIVRO' is undefined`, visto no
servidor.log da produção em 15/10/2026, já na 3.6.291).
"""
from __future__ import annotations

import sqlite3


def test_os_atos_de_um_livro_abrem_com_o_nome_do_tipo(cg_casa_logada):
    con = sqlite3.connect(cg_casa_logada["banco"])
    with con:
        cur = con.execute(
            "INSERT INTO nt_livros (tipo, numero, complemento, folhas, "
            "folha_atual, criado_em) VALUES ('PROCURACAO', '27', '', 200, 1, "
            "'2026-10-15T06:30:00')")
        livro_id = cur.lastrowid
    con.close()

    resposta = cg_casa_logada["c"].get(f"/notas/atos?livro_id={livro_id}")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert "Atos do livro" in html and "27" in html

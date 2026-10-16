"""A ficha redigitalizada em 7 dias depois do ato — ordem do oficial, 06/10/2026.

O que se guarda: a data que vale é a da IMAGEM; o prazo conta do primeiro ato
fora dela; e o aviso vermelho aparece na ficha e, vencido, para o administrador
em qualquer tela.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import ri_digi_prazo as DP                                       # noqa: E402
from conftest import cg_login                                    # noqa: E402


def _ficha(con, numero, *atos, imagem_em=None, pasta=None):
    mid = con.execute("INSERT INTO ri_matriculas (numero, criado_em) VALUES (?, '2026-09-01')",
                      (numero,)).lastrowid
    for i, quando in enumerate(atos, 1):
        con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, lavrado_em, teor,
                           hash_ato) VALUES (?, 'AV', ?, ?, 'x', ?)""",
                    (mid, i, quando, f"h{numero}{i}"))
    if imagem_em:
        img = Path(pasta) / f"{numero}.pdf"
        img.write_bytes(b"%PDF")
        t = datetime.fromisoformat(imagem_em).timestamp()
        os.utime(img, (t, t))
        con.execute("UPDATE ri_matriculas SET digi_path=?, digi_em='2026-10-03T12:00:00' WHERE id=?",
                    (str(img), mid))
    con.commit()
    return mid


def test_o_prazo_conta_do_primeiro_ato_fora_da_imagem(cg_casa, tmp_path):
    con = sqlite3.connect(cg_casa["banco"])
    _ficha(con, "4100", "2026-09-15T10:00:00", "2026-09-28T10:00:00", "2026-10-02T10:00:00",
           imagem_em="2026-09-20T10:00:00", pasta=tmp_path)
    _ficha(con, "4101", "2026-09-15T10:00:00", imagem_em="2026-09-16T10:00:00", pasta=tmp_path)
    p = DP.pendentes(con, date(2026, 10, 6))
    assert [x["numero"] for x in p] == ["4100"]
    assert p[0]["atos"] == "AV-2, AV-3" and p[0]["prazo"] == date(2026, 10, 5)
    assert p[0]["vencida"] is True


def test_o_aviso_vermelho_na_ficha_e_para_o_administrador(cg_casa, tmp_path):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    con = sqlite3.connect(cg_casa["banco"])
    hoje = date.today()
    mid = _ficha(con, "4102", f"{hoje.isoformat()}T08:00:00")
    _ficha(con, "4103", "2026-09-10T08:00:00")
    c = cg_casa["c"]
    cg_login(c, "mario", "Senha#12345")
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "ESTA FICHA PRECISA SER DIGITALIZADA DE NOVO" in ficha
    outra = c.get("/tarefas", follow_redirects=True).get_data(as_text=True)
    assert "sem digitalização há mais de 7 dias" in outra and "4103" in outra

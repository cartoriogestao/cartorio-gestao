"""HOTFIX-2026-10-09-06 — selos antigos com o texto oficial do TJ no carimbo.

Pedido da Beatriz em 09/10/2026 (mat. 1196): os selos já gerados devem sair
em carimbo, com o texto por extenso e o QR. O texto oficial vem da consulta
pública do TJMA, que dá a hora como HH:MM; e um ato do acervo pode ter o selo
de prenotação e o de registro vinculados a ele.
"""
from __future__ import annotations

import io
import sqlite3
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import ri_web                                                    # noqa: E402
import selo as SELO                                              # noqa: E402
from conftest import cg_login                                    # noqa: E402

PRE = ("Poder Judiciário – TJMA. Selo: PRENOT000000SMVWE9KPJ4BIZC81, 23/10/2019 14:29, "
       "Ato: 16.1, Parte(s): FULANA DE TAL, Total R$ 27,50 Emol R$ 26,70 FERC R$ 0,80, "
       "Consulte em https://selo.tjma.jus.br")
REG = ("Poder Judiciário – TJMA. Selo: REGAVD000000X1JRP52WNKX3YC66, 23/10/2019 14:27, "
       "Ato: 16.3, Parte(s): FULANA DE TAL, Total R$ 380,40 Emol R$ 369,30 FERC R$ 11,10, "
       "Consulte em https://selo.tjma.jus.br")


def test_hora_sem_segundos_traz_a_data():
    lido = SELO.ler_texto(PRE)
    assert (lido["data"], lido["hora"]) == ("23/10/2019", "14:29")
    assert lido["total"] == 27.5 and lido["fundos"] == {"FERC": 0.8}
    com = SELO.ler_texto(PRE.replace("14:29,", "14:29:07,"))
    assert (com["data"], com["hora"]) == ("23/10/2019", "14:29:07")


def test_rotulo_pelo_prefixo_e_prenotacao_primeiro():
    r = ri_web.selos_do_ato_rotulados("R", [REG, PRE])
    assert [x[1] for x in r] == ["SELO DE PRENOTAÇÃO", "SELO DE REGISTRO"]
    assert r[0][0] == PRE
    # sem prefixo especial, nada muda: numerados pelo tipo do ato, na ordem
    a = ri_web.selos_do_ato_rotulados("AV", ["RETFIC000000AAAAAAAAAAAAAAAA", "AVESVD000000BBBBBBBBBBBBBBBB"])
    assert [x[1] for x in a] == ["SELO DE AVERBAÇÃO 1/2", "SELO DE AVERBAÇÃO 2/2"]
    assert ri_web.selos_do_ato_rotulados("R", ["REGAVD000000CCCCCCCCCCCCCCCC"])[0][1] == "SELO DE REGISTRO"


def test_ficha_do_acervo_imprime_os_dois_carimbos(cg_casa):
    db = cg_casa["db"]
    db.create_user("leidi", "Beatriz Exemplo de Souza", "Senha#12345", "MANAGER")
    con = sqlite3.connect(cg_casa["banco"])
    mid = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, tipo_ficha, teor, criado_em)
           VALUES ('1196', '2-F', '2F', 'ACERVO', 'Imóvel rural', '2026-10-09')""").lastrowid
    dados = {"matricula_id": mid, "tipo": "R", "numero": 2, "data_ato": "2019-10-23",
             "teor": "R-2/1196 – COMPRA E VENDA. Teor do acervo.", "teor_formato": "texto",
             "acervo": 1, "hash_ato": "h-teste", "lavrado_em": "2026-07-31T10:00:00"}
    for _, col, tipo, notnull, padrao, pk in con.execute("PRAGMA table_info(ri_atos)"):
        if notnull and padrao is None and not pk and col not in dados:
            dados[col] = 0 if "INT" in (tipo or "").upper() else "x"
    aid = con.execute(
        f"INSERT INTO ri_atos ({','.join(dados)}) VALUES ({','.join('?' * len(dados))})",
        list(dados.values())).lastrowid
    for num, txt in (("REGAVD000000X1JRP52WNKX3YC66", REG), ("PRENOT000000SMVWE9KPJ4BIZC81", PRE)):
        con.execute("""INSERT INTO sd_selos (numero, texto, atribuicao, tabela, ato_id, ambiente, obtido_em, usado_em)
                       VALUES (?, ?, 'IMOVEL', 'ri_atos', ?, 'PRODUCAO', '2019-10-23 14:29', '2019-10-23 14:29')""",
                    (num, txt, aid))
    con.commit(); con.close()
    c = cg_casa["c"]
    cg_login(c, "leidi", "Senha#12345")
    r = c.get(f"/registro-imoveis/{mid}/ficha.odt")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.data))
    xml = z.read("content.xml").decode("utf-8")
    assert "SELO DE PRENOTAÇÃO" in xml and "SELO DE REGISTRO" in xml
    assert "SELO DE REGISTRO 1/2" not in xml
    assert xml.index("PRENOT000000SMVWE9KPJ4BIZC81") < xml.index("REGAVD000000X1JRP52WNKX3YC66")
    assert "Ato: 16.1 · 23/10/2019 14:29" in xml and "Ato: 16.3 · 23/10/2019 14:27" in xml
    assert "Total R$ 380,40 Emol R$ 369,30 FERC R$ 11,10" in xml
    assert "selo.tjma.jus.br/#/resumo/REGAVD000000X1JRP52WNKX3YC66" in xml
    pngs = [n for n in z.namelist() if n.startswith("Pictures/qr-")]
    assert len(pngs) == 2

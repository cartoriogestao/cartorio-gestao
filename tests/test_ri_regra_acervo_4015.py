"""Fronteira entre o acervo e as matrículas abertas no sistema.

Regra informada pela serventia em 17/09/2026: números menores que 4.015 são
acervo. A abertura histórica segue o conteúdo importado; não recebe aviso ou
formulário de selo, responsável atual, fecho ou assinatura gerados.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ri_schema import hash_ato, matricula_de_acervo


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe token CSRF"
    return achado.group(1)


def _inserir(casa, numero: str, tipo="ESTRUTURADA", teor="TEOR IMPORTADO") -> int:
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas
               (numero, livro, livro_norm, tipo_ficha, situacao, conferido,
                teor, teor_formato, origem, criado_em, data_abertura,
                aberta_nome, aberta_titulo)
               VALUES (?, '2', '2', ?, 'ATIVA', 1, ?, 'texto', 'IMPORTACAO',
                       '2026-09-17T08:00:00', '2009-08-13',
                       'PESSOA DE HOJE', 'Escrevente')""",
            (numero, tipo, teor))
        return int(cur.lastrowid)


def test_a_fronteira_e_exatamente_4015():
    assert matricula_de_acervo("4014")
    assert matricula_de_acervo("4.014")
    assert not matricula_de_acervo("4015")
    assert not matricula_de_acervo("4021")
    assert not matricula_de_acervo("")


def test_ficha_4014_nao_avisa_nem_oferece_selo_ou_responsavel(cg_casa_logada):
    casa = cg_casa_logada
    mid = _inserir(casa, "4014")  # propositalmente gravada com tipo antigo

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Acervo — bloco único" in html
    assert "Falta o selo da abertura" not in html
    assert "Não consta quem abriu" not in html
    assert "Selar a abertura desta matrícula" not in html
    assert "Selo da abertura" not in html

    editar = casa["c"].get(
        f"/registro-imoveis/{mid}/editar").get_data(as_text=True)
    assert 'name="aberta_nome"' not in editar
    assert "a abertura segue o" in editar


def test_rota_recusa_selo_de_abertura_do_acervo(cg_casa_logada):
    casa = cg_casa_logada
    mid = _inserir(casa, "4014")
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    resposta = casa["c"].post(
        f"/registro-imoveis/{mid}/selar-abertura",
        data={"csrf_token": _token(html), "codigo_tj": "16.2"},
        follow_redirects=True).get_data(as_text=True)
    assert "é de acervo" in resposta
    assert "não recebe selo de abertura" in resposta


def test_papel_4014_preserva_o_teor_sem_fecho_atual(cg_casa_logada):
    casa = cg_casa_logada
    mid = _inserir(casa, "4014", teor="CONTEÚDO HISTÓRICO IMPORTADO")
    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")
    assert "CONTEÚDO HISTÓRICO IMPORTADO" in conteudo
    assert "PESSOA DE HOJE" not in conteudo
    assert "_" * 32 not in conteudo
    assert "O referido é verdade e dou fé" not in conteudo


def test_ato_ja_contido_na_importacao_nao_e_impresso_duas_vezes(cg_casa_logada):
    casa = cg_casa_logada
    frase = "ATO HISTÓRICO ÚNICO DA IMPORTAÇÃO"
    mid = _inserir(casa, "4014", tipo="ACERVO", teor=frase)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO ri_atos
               (matricula_id, tipo, numero, data_ato, teor, teor_formato,
                cancelado, acervo, origem, lavrado_em, hash_ato)
               VALUES (?, 'R', 1, '2009-08-13', ?, 'texto', 0, 1,
                       'EOFICIO', '2026-09-17', ?)""",
            (mid, frase,
             hash_ato("4014", "R", 1, "2009-08-13", frase, None)))
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")
    assert conteudo.count(frase) == 1, (
        "o ato que já estava no bloco importado foi acrescentado outra vez")


def test_abertura_4014_nasce_acervo_sem_usuario_ou_selo(cg_casa_logada):
    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO ri_matriculas
               (numero, livro, livro_norm, tipo_ficha, situacao, criado_em)
               VALUES ('4013','2','2','ACERVO','ATIVA','2026-09-17')""")
    con.close()

    tela = casa["c"].get("/registro-imoveis/nova").get_data(as_text=True)
    assert "4014" in tela and "automaticamente como" in tela
    resposta = casa["c"].post(
        "/registro-imoveis/nova",
        data={"csrf_token": _token(tela), "teor": "IMPORTADO SEM ALTERAÇÃO",
              "cidade": "Cidade Exemplo", "uf": "MA"},
        follow_redirects=False)
    assert resposta.status_code in (302, 303)

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    m = con.execute(
        "SELECT * FROM ri_matriculas WHERE numero='4014'").fetchone()
    con.close()
    assert m is not None
    assert m["tipo_ficha"] == "ACERVO"
    assert m["conferido"] == 0
    assert m["aberta_nome"] is None
    assert m["selo_abertura_texto"] is None
    assert m["teor"] == "IMPORTADO SEM ALTERAÇÃO"

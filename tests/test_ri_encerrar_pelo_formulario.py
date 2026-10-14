"""HOTFIX-2026-10-08-08 - «Encerrar matrícula» abre o formulário de lavrar.

Pedido da Beatriz em 08/10/2026 (mat. 1196): a aba de encerrar não deixava
pôr nem conferir o texto do ato, e nem todo encerramento é igual. O botão
agora abre o formulário de lavrar com «encerra = Sim», número sugerido,
natureza e um modelo de texto editável; o «PREENCHER…» que sobrar recusa a
lavratura; e «Selar este ato» já vem com a gratuidade gravada no ato.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import ri_web                                                    # noqa: E402
from conftest import cg_login                                    # noqa: E402


def test_modelos_de_encerramento_montam_o_texto():
    m = {"numero": "1196", "livro": "2-F", "livro_norm": "2F"}
    mods = ri_web.modelos_de_encerramento(
        m, 8, "2026-10-08", ("Beatriz Exemplo de Souza", "Substituta", "A"))
    cods = [x["codigo"] for x in mods]
    assert cods == ["TECNICA", "DESMEMBRAMENTO", "UNIFICACAO", "CIRCUNSCRICAO", "LIVRE"]
    tec = mods[0]["teor"]
    assert tec.startswith("AV-08/1.196 – ENCERRAMENTO DA MATRÍCULA POR MUDANÇA DA TÉCNICA")
    assert "Matrícula nº 1.196, do Livro nº 2 – F" in tec
    assert "Cidade Exemplo/MA, 08 de outubro de 2026. Dou fé. A Substituta, _____________ " \
           "Beatriz Exemplo de Souza." in tec
    assert all(ri_web.MARCA_A_PREENCHER in x["teor"] for x in mods)
    assert all(x["natureza"] for x in mods)


def _ficha(con, numero="1196", acervo=True):
    mid = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, tipo_ficha, teor, criado_em)
           VALUES (?, '2-F', '2F', ?, 'Imóvel rural', '2026-10-08')""",
        (numero, "ACERVO" if acervo else "MANUAL")).lastrowid
    con.commit()
    return mid


def _entrar(c, login):
    cg_login(c, login, "Senha#12345")
    with c.session_transaction() as s:
        return s.get("csrf_token")


def test_botao_encerrar_abre_o_formulario_de_lavrar(cg_casa):
    db = cg_casa["db"]
    db.create_user("leidi", "Beatriz Exemplo de Souza", "Senha#12345", "MANAGER")
    con = sqlite3.connect(cg_casa["banco"])
    mid = _ficha(con)
    c = cg_casa["c"]
    _entrar(c, "leidi")
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "encerrar=1" in html and "abrir o formulário do ato" in html
    assert 'name="data_encerramento"' not in html      # o formulário antigo saiu
    html = c.get(f"/registro-imoveis/{mid}?lavrar=1&encerrar=1").get_data(as_text=True)
    assert "data-encerramento-modelo" in html and "ri_encerramento.js" in html
    assert 'name="encerra" value="1" checked' in html
    assert "ENCERRAMENTO DA MATRÍCULA POR MUDANÇA DA TÉCNICA" in html
    assert 'value="Encerramento da matrícula por mudança da técnica de escrituração e remissão à nova matrícula"' in html
    assert 'data-natureza=' in html
    con.close()


def test_balcao_nao_recebe_o_encerramento(cg_casa):
    db = cg_casa["db"]
    db.create_user("balcao", "BALCAO", "Senha#12345", "USER")
    con = sqlite3.connect(cg_casa["banco"])
    mid = _ficha(con)
    c = cg_casa["c"]
    _entrar(c, "balcao")
    html = c.get(f"/registro-imoveis/{mid}?lavrar=1&encerrar=1").get_data(as_text=True)
    assert "data-encerramento-modelo" not in html and 'name="encerra"' not in html
    con.close()


def test_preencher_que_sobrou_recusa_e_nada_e_lavrado(cg_casa):
    db = cg_casa["db"]
    db.create_user("leidi", "Beatriz Exemplo de Souza", "Senha#12345", "MANAGER")
    con = sqlite3.connect(cg_casa["banco"])
    mid = _ficha(con)
    c = cg_casa["c"]
    token = _entrar(c, "leidi")
    teor = ("AV-01/1.196 – ENCERRAMENTO DA MATRÍCULA. Passa a constar da Matrícula nº "
            "«PREENCHER: matrícula de destino». Dou fé.")
    r = c.post(f"/registro-imoveis/{mid}/atos", follow_redirects=True,
               data={"csrf_token": token, "tipo": "AV", "numero": "1", "teor": teor,
                     "natureza_titulo": "Encerramento de matrícula", "encerra": "1",
                     "encerra_motivo": "Mudança da técnica de escrituração",
                     "encerra_destino": "4022", "data_ato": "2026-10-08"})
    assert "PREENCHER" in r.get_data(as_text=True)
    assert con.execute("SELECT count(*) FROM ri_atos WHERE matricula_id=?", (mid,)).fetchone()[0] == 0
    assert con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?", (mid,)).fetchone()[0] in (0, None)
    con.close()


def test_selar_este_ato_traz_a_gratuidade_gravada(cg_casa):
    db = cg_casa["db"]
    db.create_user("leidi", "Beatriz Exemplo de Souza", "Senha#12345", "MANAGER")
    con = sqlite3.connect(cg_casa["banco"])
    mid = _ficha(con)
    con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, natureza_titulo, teor,
                       teor_formato, cancelado, acervo, origem, hash_ato, lavrado_em, codigo_tj,
                       isento, motivo_isencao)
                   VALUES (?, 'AV', 8, '2026-10-08', 'Encerramento de matrícula', 'AV-08 teste. Dou fé.',
                           'texto', 0, 0, 'MANUAL', 'x', '2026-10-08T14:17:57', '16.22.2', 1,
                           'Ato de ofício – mudança da técnica de escrituração')""", (mid,))
    con.commit()
    c = cg_casa["c"]
    _entrar(c, "leidi")
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert 'id="selar_ato_isento" checked' in html
    assert 'value="Ato de ofício – mudança da técnica de escrituração"' in html
    con.close()

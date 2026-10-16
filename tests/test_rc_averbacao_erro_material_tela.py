# -*- coding: utf-8 -*-
"""Relato #127 (09/10/2026, balcão; atendido em 15/10/2026): a tela do modelo de
averbação de retificação de erro material — o modelo genérico (art. 110), com
mais de uma correção, e o texto gerado EDITÁVEL, levado como o escrevente o
deixou (e não remontado) para a tela padrão de averbação."""
from __future__ import annotations

import html as _html
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
SLUG = "retificacao-erro-material"


def _token(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m
    return m.group(1)


def _caixa(html):
    m = re.search(r'<textarea name="teor"[^>]*>(.*?)</textarea>', html, re.S)
    return _html.unescape(m.group(1)) if m else None


@pytest.fixture()
def casa(cg_casa):
    db, c = cg_casa["db"], cg_casa["cliente"]
    # O balcão é perfil USER: o modelo tem de servir a quem atende.
    db.create_user("beatriz", "Beatriz Exemplo", SENHA, "USER")
    c.post("/login", data={"username": "beatriz", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(cg_casa["banco"])
    cur = con.execute(
        "INSERT INTO rc_assentos(serie,especie,numero,nome,data_ato,data_fato,situacao,"
        "livro_volume,criado_em) VALUES('RC_A','NASCIMENTO',4321,'FULANO DE TAL',"
        "'2010-05-03','2010-04-30','ATIVO','A-9','2026-10-15T09:00')")
    con.commit()
    cg_casa["aid"] = cur.lastrowid
    con.close()
    return cg_casa


def _dados(token, **extra):
    d = {"csrf_token": token, "acao": "gerar", "numero_av": "01/4.321",
         "correcao_campo_1": "O NOME DA GENITORA", "correcao_errado_1": "MARIA DE SOUSA",
         "correcao_correto_1": "MARIA DE SOUZA",
         "correcao_campo_2": "A NATURALIDADE", "correcao_errado_2": "VILA FICTICIA/MA",
         "correcao_correto_2": "CIDADE EXEMPLO/MA",
         "requerente_tipo": "parte", "requerente_nome": "CARLA EXEMPLO",
         "data_requerimento": "2026-10-14", "documentos": "",
         "fundamento": "Artigo 110, §§1º e 3º, da Lei 6.015/1973",
         "data_averbacao": "2026-10-15", "cidade": "Cidade Exemplo/MA",
         "subscritor_nome": "Beatriz Exemplo", "subscritor_funcao": "Escrevente Autorizada"}
    d.update(extra)
    return d


def test_o_modelo_generico_aparece_na_averbacao_e_abre(casa):
    c, aid = casa["cliente"], casa["aid"]
    tela = c.get(f"/rcpn/{aid}/averbar").get_data(as_text=True)
    assert f"/rcpn/{aid}/averbar/modelo/{SLUG}" in tela
    assert "Retificação de erro material (art. 110)" in tela
    # o modelo da data continua oferecido, com o mesmo endereço
    assert f"/rcpn/{aid}/averbar/modelo/retificacao-data-registro" in tela
    form = c.get(f"/rcpn/{aid}/averbar/modelo/{SLUG}").get_data(as_text=True)
    assert 'name="correcao_campo_1"' in form and 'name="correcao_correto_5"' in form
    assert 'list="elementos-do-assento"' in form and "O NOME DA GENITORA" in form
    assert 'value="01/4.321"' in form
    assert _caixa(form) is None   # antes de gerar não há texto


def test_texto_gerado_vem_numa_caixa_editavel_com_duas_correcoes(casa):
    c, aid = casa["cliente"], casa["aid"]
    url = f"/rcpn/{aid}/averbar/modelo/{SLUG}"
    prev = c.post(url, data=_dados(_token(c.get(url).get_data(as_text=True)))).get_data(
        as_text=True)
    texto = _caixa(prev)
    assert texto, prev[:2000]
    assert texto.startswith("AVERBAÇÃO 01/4.321 – RETIFICAÇÃO DO NOME DA GENITORA E DA "
                            "NATURALIDADE: Em 15 de Outubro de 2026, "
                            "após requerimento feito pela parte interessada, CARLA EXEMPLO, "
                            "em 14/10/2026, venho retificar os seguintes elementos")
    assert ("O NOME DA GENITORA, grafado erroneamente como sendo “MARIA DE SOUSA” ao invés "
            "de “MARIA DE SOUZA”; e A NATURALIDADE, grafada erroneamente") in texto
    assert 'name="fundamento_ato"' in prev
    assert "Levar para a averbação" in prev
    # o que foi digitado nas linhas volta preenchido
    assert 'value="VILA FICTICIA/MA"' in prev


def test_o_texto_editado_e_o_que_vai_para_a_averbacao(casa):
    c, aid = casa["cliente"], casa["aid"]
    url = f"/rcpn/{aid}/averbar/modelo/{SLUG}"
    token = _token(c.get(url).get_data(as_text=True))
    gerado = _caixa(c.post(url, data=_dados(token)).get_data(as_text=True))
    editado = gerado.replace("O referido é verdade e dou fé.",
                             "Nada mais. O referido é verdade e dou fé.")
    assert editado != gerado
    r = c.post(url, data=_dados(token, acao="levar", teor=editado,
                                fundamento_ato="Art. 110 - ajustado à mão"))
    assert r.status_code in (302, 303) and r.headers["Location"].endswith(f"/rcpn/{aid}/averbar")
    tela = _html.unescape(c.get(f"/rcpn/{aid}/averbar").get_data(as_text=True))
    assert "Nada mais. O referido é verdade e dou fé." in tela    # o editado, e não o remontado
    assert "Art. 110 - ajustado à mão" in tela
    assert "com as suas alterações" in tela
    assert 'value="retificacao" selected' in tela
    # nada gravado: nenhum ato
    con = sqlite3.connect(casa["banco"])
    assert con.execute("SELECT COUNT(*) FROM rc_atos WHERE assento_id=?", (aid,)).fetchone()[0] == 0
    con.close()


def test_recusa_ao_levar_nao_apaga_o_texto_editado(casa):
    c, aid = casa["cliente"], casa["aid"]
    url = f"/rcpn/{aid}/averbar/modelo/{SLUG}"
    token = _token(c.get(url).get_data(as_text=True))
    editado = "AVERBAÇÃO 01/4.321 – RETIFICAÇÃO: texto ajustado pelo balcão, à mão."
    r = c.post(url, data=_dados(token, acao="levar", teor=editado, subscritor_nome=""))
    assert r.status_code == 200
    pagina = r.get_data(as_text=True)
    assert "Quem subscreve" in _html.unescape(pagina)       # a recusa diz o que falta
    assert _caixa(pagina) == editado                        # e o texto continua na caixa
    with c.session_transaction() as s:
        assert "rcpn_averbacao_preenchida" not in s


def test_levar_sem_editar_leva_o_texto_gerado(casa):
    c, aid = casa["cliente"], casa["aid"]
    url = f"/rcpn/{aid}/averbar/modelo/{SLUG}"
    token = _token(c.get(url).get_data(as_text=True))
    gerado = _caixa(c.post(url, data=_dados(token)).get_data(as_text=True))
    c.post(url, data=_dados(token, acao="levar", teor=gerado))
    tela = _html.unescape(c.get(f"/rcpn/{aid}/averbar").get_data(as_text=True))
    assert gerado in tela
    assert "com as suas alterações" not in tela

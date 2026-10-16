"""A minuta da CNIB sai sem `{{ }}` — e o marcador cru não entra no livro.

O DEFEITO, medido em 06/10/2026 pela conferência diária do gestor (regra
MODELO_NAO_PREENCHIDO): 11 minutas `A_REVISAR` da CNIB (ids 20, 24, 27 a 35 na
produção) começavam com

    <p><b>{{ rotulo }} —</b> <b>INDISPONIBILIDADE DE BENS.</b> {{ protocolo_frase }} …

`ri_cnib.teor_preparado` passava o modelo só por `ri_modelos_atos.preencher`,
que troca os `[COLCHETES]` e deixa o Jinja para `render_modelo` — e ninguém o
chamava ali. A rota de lavrar grava o teor como vem: lavrar qualquer uma delas
poria o marcador na ficha e na corrente de hash.

São três camadas, e cada teste guarda uma: a PREPARAÇÃO resolve o marcador; a
MINUTA recusa gravá-lo; a ROTA DE LAVRAR recusa lavrá-lo.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_cnib as CNIB  # noqa: E402
import ri_minuta as RIMIN  # noqa: E402
from ri_schema import normalizar_busca  # noqa: E402

SENHA = "Senha#12345"
ORDEM = {
    "protocolo_cnib": "202308.1016.02861529-IA-009", "data_pedido": "2023-08-10",
    "instituicao": "TRT16", "forum_vara": "2a Vara do Trabalho de Imperatriz",
    "processo": "0016789-12.2019.5.16.0012", "nome": "FULANO DE TAL",
    "documento": "00000002569",
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = cg_casa["cliente"]
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(con, *, numero, tipo_ficha, partes=()):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2', '2', 'ATIVA', ?, '2026-10-06T09:00')""",
        (numero, tipo_ficha))
    mid = int(cur.lastrowid)
    for nome, documento in partes:
        con.execute(
            """INSERT INTO ri_partes (matricula_id, nome, nome_norm,
                   documento_numero, papel, proprietario_ativo)
               VALUES (?,?,?,?, 'proprietario', 1)""",
            (mid, nome, normalizar_busca(nome), documento))
    return mid


def _prenotacao(con, mid, numero, data):
    con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               matricula_id, situacao, criado_em)
           VALUES (?, '1A', ?, ?, 'ABERTO', ?)""", (numero, data, mid, data))


def _sem_marcador(teor: str) -> None:
    assert "{{" not in teor and "{%" not in teor, teor[:160]


# ------------------------------------------- a preparação resolve o marcador


def test_sem_matricula_o_que_nao_se_sabe_fica_em_colchete_e_nao_em_jinja():
    teor = CNIB.teor_preparado(ORDEM)
    _sem_marcador(teor)
    assert "[ROTULO DO ATO]" in teor
    assert "[INFORMAR O PROTOCOLO]." in teor


def test_ficha_estruturada_leva_o_rotulo_do_piso_e_a_frase_da_prenotacao(casa):
    """O número é o que a rota de lavrar usaria (`piso_do_proximo`), e a frase
    é a da prenotação aberta — a mesma de `ri_web._contexto_modelo`."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="4100", tipo_ficha="ESTRUTURADA")
        con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
                   teor, teor_formato, cancelado, acervo, origem,
                   hash_ato, hash_anterior, lavrado_em)
               VALUES (?, 'R', 1, '2026-09-01', 'registro', 'texto', 0, 0,
                       'MANUAL', 'h', NULL, '2026-09-01T09:00')""",
            (mid,))
        _prenotacao(con, mid, 11565, "2026-09-24")
    teor = CNIB.teor_preparado(ORDEM, _con(casa), mid)
    _sem_marcador(teor)
    assert "AV-02/4100 —" in teor
    assert "PROTOCOLO N. 11565, DE 24/09/2026." in teor


def test_ficha_de_acervo_nao_inventa_o_numero_do_livro(casa):
    """Em ficha de ACERVO a rota exige o número à mão, conforme o livro
    físico. Calcular aqui seria inventar — fica o colchete, visível; e o
    número informado ganha."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="1840", tipo_ficha="ACERVO")
    teor = CNIB.teor_preparado(ORDEM, _con(casa), mid)
    _sem_marcador(teor)
    assert "AV-[NUMERO DO ATO]/1840" in teor
    assert "[INFORMAR O PROTOCOLO]." in teor
    com_numero = CNIB.teor_preparado(ORDEM, _con(casa), mid, numero=14)
    assert "AV-14/1840 —" in com_numero


def test_a_lista_de_pendentes_mostra_o_teor_resolvido(casa):
    con = _con(casa)
    with con:
        con.execute("""INSERT INTO ri_cnib_ordens (protocolo_cnib, data_pedido,
                           processo, instituicao, forum_vara, ativa)
                       VALUES (?,?,?,?,?,1)""",
                    (ORDEM["protocolo_cnib"], ORDEM["data_pedido"], ORDEM["processo"],
                     ORDEM["instituicao"], ORDEM["forum_vara"]))
        oid = con.execute("SELECT max(id) FROM ri_cnib_ordens").fetchone()[0]
        con.execute("""INSERT INTO ri_cnib_pessoas (ordem_id, nome, nome_norm, documento)
                       VALUES (?,?,?,?)""",
                    (oid, ORDEM["nome"], normalizar_busca(ORDEM["nome"]), ORDEM["documento"]))
        _matricula(con, numero="4101", tipo_ficha="ESTRUTURADA",
                   partes=((ORDEM["nome"], ORDEM["documento"]),))
    achados = CNIB.pendentes(_con(casa))
    assert len(achados) == 1
    _sem_marcador(achados[0]["teor"])
    assert "AV-01/4101" in achados[0]["teor"]
    html = casa["cliente"].get("/registro-imoveis/cnib/pendentes").get_data(as_text=True)
    assert "{{ rotulo }}" not in html and "{{ protocolo_frase }}" not in html


def test_a_minuta_do_cnib_gerada_como_o_script_gera_sai_sem_marcador(casa):
    """O caminho das 11: `teor_preparado` → `ri_minuta.criar`, com a
    `origem_chave` CNIB. O texto gravado tem de estar pronto para revisar."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="2846", tipo_ficha="ACERVO")
        minuta_id = RIMIN.criar(
            con, matricula_id=mid, tipo="AV",
            teor=CNIB.teor_preparado(ORDEM, con, mid), agora="2026-10-06T13:00",
            natureza_titulo="Indisponibilidade de bens — CNIB",
            modelo_codigo=CNIB.CODIGO_DO_MODELO,
            origem_chave=CNIB.chave_da_minuta(mid, ORDEM), usuario="teste")
    gravado = _con(casa).execute("SELECT teor FROM ri_minutas WHERE id=?",
                                 (minuta_id,)).fetchone()["teor"]
    _sem_marcador(gravado)
    assert "INDISPONIBILIDADE DE BENS." in gravado
    assert ORDEM["protocolo_cnib"] in gravado


def test_marcador_que_a_preparacao_nao_conhece_recusa(monkeypatch):
    """Se o modelo ganhar um `{{ outro }}`, a preparação para — e não deixa o
    marcador seguir para a minuta, que foi o defeito."""
    import ri_modelos_atos as MOD
    original = MOD.por_codigo(CNIB.CODIGO_DO_MODELO)
    monkeypatch.setattr(MOD, "por_codigo", lambda c: dict(
        original, corpo=original["corpo"] + " {{ area_frase }}"))
    with pytest.raises(CNIB.CnibError) as e:
        CNIB.teor_preparado(ORDEM)
    assert "area_frase" in str(e.value)


# ------------------------------------------- a minuta recusa gravá-lo


def test_a_minuta_recusa_teor_com_marcador_de_modelo(casa):
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="4102", tipo_ficha="ESTRUTURADA")
    cru = ("<p><b>{{ rotulo }} —</b> <b>INDISPONIBILIDADE DE BENS.</b> "
           "{{ protocolo_frase }} Nos termos da ordem…</p>")
    with pytest.raises(RIMIN.MinutaError) as e:
        with _con(casa) as c:
            RIMIN.criar(c, matricula_id=mid, tipo="AV", teor=cru,
                        agora="2026-10-06T13:00")
    assert "{{ rotulo }}" in str(e.value)


def test_a_revisao_tambem_recusa_e_o_colchete_continua_aceito(casa):
    """O `[CAMPO]` é do escrevente preencher; o `{{ }}` é o motor de modelo
    que não rodou. Só o segundo recusa."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="4103", tipo_ficha="ESTRUTURADA")
        minuta_id = RIMIN.criar(
            con, matricula_id=mid, tipo="AV", agora="2026-10-06T13:00",
            teor="AV-[NUMERO DO ATO]/4103 — INDISPONIBILIDADE DE BENS. [INFORMAR O PROTOCOLO].")
    with pytest.raises(RIMIN.MinutaError):
        with _con(casa) as c:
            RIMIN.atualizar(c, minuta_id, agora="2026-10-06T13:05",
                            teor="{{ rotulo }} — INDISPONIBILIDADE DE BENS, texto revisado.")
    assert RIMIN.marcador_de_modelo("{% if x %}a{% endif %}") == "{% if x %}"
    assert RIMIN.marcador_de_modelo("AV-[NUMERO DO ATO]/11 — texto") is None


# ------------------------------------------- a rota de lavrar recusa lavrá-lo


def test_a_rota_de_lavrar_recusa_teor_com_marcador_e_nao_lavra(casa):
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="4104", tipo_ficha="ESTRUTURADA")
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = casa["cliente"].post(f"/registro-imoveis/{mid}/atos", data={
        "csrf_token": _token(html), "tipo": "AV",
        "natureza_titulo": "Indisponibilidade de bens — CNIB",
        "teor": "<p><b>{{ rotulo }} —</b> <b>INDISPONIBILIDADE DE BENS.</b> "
                "{{ protocolo_frase }} Nos termos da ordem da CNIB…</p>",
        "data_ato": "2026-10-06"}, follow_redirects=True)
    junto = " ".join(r.get_data(as_text=True).split())
    assert "marcação de modelo que não foi preenchida" in junto
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM ri_atos WHERE matricula_id=?",
        (mid,)).fetchone()["c"] == 0

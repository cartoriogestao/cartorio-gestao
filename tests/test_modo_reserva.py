"""O SERVIDOR RESERVA (`modo_reserva`): o sistema com um usuário do banco que só tem SELECT.

Pedido do oficial, 07/11/2026: um servidor extra no macOS, cópia do principal, que só lê enquanto
o principal está no ar. A trava é o banco (o usuário da reserva não tem permissão de escrita); estes
testes conferem que o sistema, sabendo disso, ENTRA, MOSTRA e RECUSA com a frase certa — em vez
de cair com «permission denied» na primeira tela.

Medido em 07/11/2026 na casa de ensaio inteira (893 telas, ADMIN, layout novo): 848 abrem só
lendo; as outras gravam algum rastro ao abrir e mostram a página da reserva (503), e não o 500.
"""
from __future__ import annotations

import os
import re

import psycopg
import pytest

import banco_pg
import modo_reserva as MRES
from conftest import BACKEND_PG, cg_login

pytestmark = pytest.mark.skipif(not BACKEND_PG, reason="o servidor reserva é PostgreSQL")

PAPEL = "cg_leitor_reserva_teste"
SENHA = "Senha#12345"


def _dsn_com(usuario: str) -> str:
    return re.sub(r"user=\S+", f"user={usuario}", os.environ["CG_PG_DSN"])


@pytest.fixture
def reserva(cg_casa, monkeypatch):
    """A casa com um ADMIN cadastrado e, daqui em diante, o processo como servidor reserva: o
    banco pelo usuário só de leitura e `CG_MODO_RESERVA=1`. Tudo volta no fim."""
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    schema = banco_pg.schema_do_caminho(cg_casa["banco"])
    with psycopg.connect(os.environ["CG_PG_DSN"], autocommit=True) as pg, pg.cursor() as c:
        if c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (PAPEL,)).fetchone():
            c.execute(f"DROP OWNED BY {PAPEL}")
            c.execute(f"DROP ROLE {PAPEL}")
        c.execute(f"CREATE ROLE {PAPEL} LOGIN")
        c.execute(f'GRANT USAGE ON SCHEMA "{schema}", public TO {PAPEL}')
        c.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}", public TO {PAPEL}')
    banco_pg.esvaziar_reservatorio()
    monkeypatch.setenv("CG_PG_DSN", _dsn_com(PAPEL))
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    yield cg_casa
    banco_pg.esvaziar_reservatorio()
    monkeypatch.undo()
    with psycopg.connect(os.environ["CG_PG_DSN"], autocommit=True) as pg, pg.cursor() as c:
        c.execute(f"DROP OWNED BY {PAPEL}")
        c.execute(f"DROP ROLE {PAPEL}")


def test_entra_e_mostra_a_faixa_da_reserva(reserva):
    c = reserva["c"]
    r = cg_login(c, "mario", SENHA)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "cg-faixa-reserva" in html and "SERVIDOR RESERVA" in html
    assert "permission denied" not in html


def test_formulario_e_recusado_antes_do_banco(reserva):
    c = reserva["c"]
    cg_login(c, "mario", SENHA)
    with c.session_transaction() as sessao:
        token = sessao["csrf_token"]
    r = c.post("/preferencias/layout", data={"layout": "novo", "next": "/", "csrf_token": token})
    assert r.status_code == 503
    assert "só consulta" in r.get_data(as_text=True)


def test_tela_que_grava_ao_abrir_mostra_a_pagina_da_reserva(reserva):
    """`/processos` grava ao abrir (medido); na reserva vira a página clara, e não o 500 que
    anotaria um «defeito» na lista de problemas."""
    c = reserva["c"]
    cg_login(c, "mario", SENHA)
    r = c.get("/processos")
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        assert "servidor reserva só lê" in r.get_data(as_text=True)


def test_sem_o_modo_nada_muda(cg_casa_logada):
    html = cg_casa_logada["c"].get("/").get_data(as_text=True)
    assert "cg-faixa-reserva" not in html


def test_schema_que_nao_chegou_diz_o_que_falta(cg_casa, monkeypatch):
    """Banco da reserva sem o esquema do principal: a frase diz o que fazer, e nada é criado."""
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    monkeypatch.setenv("CG_PG_SCHEMA", "cg_reserva_sem_esquema")
    banco_pg.esvaziar_reservatorio()
    with pytest.raises(banco_pg.OperationalError, match="servidor reserva: o banco ainda não tem"):
        banco_pg.conectar(cg_casa["banco"])
    with psycopg.connect(os.environ["CG_PG_DSN"], autocommit=True) as pg, pg.cursor() as c:
        assert c.execute("SELECT 1 FROM pg_namespace WHERE nspname='cg_reserva_sem_esquema'").fetchone() is None


@pytest.mark.parametrize("valor, esperado", [("", 8775), ("9001", 9001), ("abc", 8775), ("0", 8775),
                                             ("70000", 8775)])
def test_a_porta_vem_do_ambiente(monkeypatch, valor, esperado):
    monkeypatch.setenv("CG_RESERVA_PORTA", valor)
    assert MRES.porta() == esperado


def test_ligado_so_com_um(monkeypatch):
    for valor, ligado in (("1", True), ("0", False), ("", False), ("sim", False)):
        monkeypatch.setenv("CG_MODO_RESERVA", valor)
        assert MRES.ativo() is ligado


def test_o_sistema_sobe_inteiro_na_reserva(reserva, monkeypatch, tmp_path):
    """A SUBIDA DE VERDADE (`create_app`) com o banco só de leitura. Cada módulo roda o próprio
    `init_schema` ao registrar as rotas — CREATE TABLE, sementes —, e o primeiro deles derrubava
    a reserva (ensaio de 07/11/2026). Módulo novo que gravar ao subir de outro jeito cai aqui."""
    from app import create_app
    import modo_reserva as M

    monkeypatch.setenv("CG_PG_SCHEMA", banco_pg.schema_do_caminho(reserva["banco"]))
    app = create_app({"DATA_DIR": str(tmp_path / "dados_da_reserva")})
    assert M.ativo()
    c = app.test_client()
    r = cg_login(c, "mario", SENHA)
    assert r.status_code == 200 and "SERVIDOR RESERVA" in r.get_data(as_text=True)
    # passada a subida, a escrita volta a ser recusada (e não ignorada em silêncio)
    with pytest.raises(banco_pg.OperationalError, match="readonly"):
        with app.extensions["db"].connect() as con:
            con.execute("INSERT INTO settings(key, value) VALUES ('reserva_teste', 'x')")
            con.commit()


def test_o_que_a_ponte_deixa_de_rodar_na_reserva(monkeypatch):
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    assert banco_pg.ignorado_na_reserva("-- comentário\nCREATE TABLE IF NOT EXISTS x (a int)")
    assert banco_pg.ignorado_na_reserva("ALTER TABLE x ADD COLUMN b text")
    assert not banco_pg.ignorado_na_reserva("SELECT 1")
    assert not banco_pg.ignorado_na_reserva("INSERT INTO x VALUES (1)")   # fora da subida: recusa
    banco_pg.subida_da_reserva(True)
    try:
        assert banco_pg.ignorado_na_reserva("INSERT INTO x VALUES (1) ON CONFLICT DO NOTHING")
        assert not banco_pg.ignorado_na_reserva("SELECT 1")
    finally:
        banco_pg.subida_da_reserva(False)
    monkeypatch.setenv("CG_MODO_RESERVA", "")
    assert not banco_pg.ignorado_na_reserva("CREATE TABLE x (a int)")

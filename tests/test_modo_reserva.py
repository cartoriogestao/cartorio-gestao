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


def _virar_reserva(cg_casa, monkeypatch):
    """Daqui em diante o processo é o servidor reserva: o banco pelo usuário só de leitura e
    `CG_MODO_RESERVA=1`. Devolve a função que desfaz tudo."""
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

    def desfazer():
        banco_pg.esvaziar_reservatorio()
        monkeypatch.undo()
        with psycopg.connect(os.environ["CG_PG_DSN"], autocommit=True) as pg, pg.cursor() as c:
            c.execute(f"DROP OWNED BY {PAPEL}")
            c.execute(f"DROP ROLE {PAPEL}")
    return desfazer


@pytest.fixture
def reserva(cg_casa, monkeypatch):
    """A casa com um ADMIN cadastrado e, daqui em diante, o processo como servidor reserva."""
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    desfazer = _virar_reserva(cg_casa, monkeypatch)
    yield cg_casa
    desfazer()


def test_entra_e_mostra_a_faixa_da_reserva(reserva):
    c = reserva["c"]
    r = cg_login(c, "mario", SENHA)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "faixa-reserva" in html and "SERVIDOR RESERVA" in html
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
    assert "faixa-reserva" not in html


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


def test_a_sincronia_traz_as_chaves_e_as_pastas_e_o_assumir_aponta(cg_casa, tmp_path, monkeypatch):
    """Do lado do Mac, contra um banco de verdade: `reserva.py chaves` abre o pacote que o
    principal publicou; `pastas` copia a pasta configurada fora dos arquivos (origem local, no
    lugar do compartilhamento) e avisa a que não tem compartilhamento; `pastas --apontar`, no
    assumir, troca a configuração para a cópia do Mac."""
    import sys
    from pathlib import Path
    import reserva_chaves as RCH
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import reserva as R

    db = cg_casa["db"]
    dsn = os.environ["CG_PG_DSN"]
    schema = banco_pg.schema_do_caminho(cg_casa["banco"])
    privada = tmp_path / "mac" / "reserva-chave.privada"
    db.set_settings({RCH.CHAVE_PUBLICA: RCH.gerar_par(privada)})
    dados_win = tmp_path / "win-dados"
    dados_win.mkdir()
    (dados_win / "cofre.key").write_text("chave-do-cofre")
    (dados_win / "portal.cred").write_bytes(b"\x00cifrado")
    dados_mac = tmp_path / "mac" / "dados"

    assert R.receber_chaves(dsn, schema, privada, dados_mac) == 0      # ainda sem tabela: avisa
    assert not dados_mac.exists()
    assert RCH.publicar(db, dados_win) == "publicado"
    assert R.receber_chaves(dsn, schema, privada, dados_mac) == 0
    assert (dados_mac / "cofre.key").read_text() == "chave-do-cofre"
    assert (dados_mac / "portal.cred").read_bytes() == b"\x00cifrado"
    (dados_mac / "cofre.key").write_text("mexida")
    assert R.receber_chaves(dsn, schema, privada, dados_mac) == 0      # em dia: não regrava
    assert (dados_mac / "cofre.key").read_text() == "mexida"

    origem = tmp_path / "win-matriculas"
    (origem / "2026").mkdir(parents=True)
    (origem / "2026" / "m1.pdf").write_bytes(b"%PDF")
    db.set_settings({"archive_root": r"C:\Cartorio\Arquivos",
                     "ri_pasta_matriculas_doc": r"D:\Matriculas\2026",
                     "gratuidade_pasta": r"E:\Gratuidade"})
    base = tmp_path / "mac" / "pastas"
    mapa = f"D:\\Matriculas={origem}"
    assert R.copiar_pastas(dsn, schema, base, mapa) == 0
    assert (base / "D_Matriculas" / "2026" / "m1.pdf").read_bytes() == b"%PDF"
    assert R.apontar_pastas(dsn, schema, base, mapa) == 0
    assert db.get_setting("ri_pasta_matriculas_doc") == str(base / "D_Matriculas" / "2026")
    assert db.get_setting("gratuidade_pasta") == r"E:\Gratuidade"     # sem cópia: fica


# ------------------------------------------- a verificação em duas etapas na reserva
#
# Ensaio de 09/11/2026 no Mac da reserva: quem tem a verificação ativa acertava a senha e parava
# no código — o POST de `/login/dois-fatores` caía na recusa dos formulários, e o `conferir`
# grava (último passo, falhas), o que o usuário só de leitura não pode. Na reserva o código é
# conferido sem gravar (`dois_fatores.conferir_so_leitura`), com a contagem na memória.

import dois_fatores as DF

T0 = 1_800_000_000.0
TELA_DO_CODIGO = "/login/dois-fatores"


class _Relogio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def relogio(monkeypatch):
    r = _Relogio(T0)
    monkeypatch.setattr(DF, "relogio", r)
    return r


@pytest.fixture
def reserva_com_dois_fatores(cg_casa, monkeypatch, relogio):
    """O ADMIN com a verificação ATIVA no principal, e então o processo vira a reserva."""
    db = cg_casa["db"]
    uid = db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    with db.transaction() as con:
        segredo = DF.iniciar(con, uid, pasta=cg_casa["dados"])
        codigos = DF.confirmar(con, uid, DF.totp(segredo, T0), pasta=cg_casa["dados"],
                               instante=T0)
    desfazer = _virar_reserva(cg_casa, monkeypatch)
    yield {**cg_casa, "uid": uid, "segredo": segredo, "codigos": codigos}
    desfazer()


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _senha(c):
    token = _token(c.get("/login").get_data(as_text=True))
    return c.post("/login", data={"username": "mario", "password": SENHA, "csrf_token": token})


def _codigo(c, codigo):
    token = _token(c.get(TELA_DO_CODIGO).get_data(as_text=True))
    return c.post(TELA_DO_CODIGO, data={"codigo": codigo, "csrf_token": token})



def _errado(segredo, instante):
    certo = {DF.totp(segredo, instante + d * DF.PASSO_SEGUNDOS) for d in (-1, 0, 1)}
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in certo)


def test_entra_com_a_verificacao_em_duas_etapas_sem_gravar_nada(reserva_com_dois_fatores, relogio):
    casa = reserva_com_dois_fatores
    c, segredo = casa["c"], casa["segredo"]
    r = _senha(c)
    assert r.status_code == 302 and TELA_DO_CODIGO in r.headers["Location"]
    r = _codigo(c, _errado(segredo, T0 + 30))
    assert r.status_code == 302 and r.headers["Location"].endswith(TELA_DO_CODIGO)
    assert "não confere" in c.get(TELA_DO_CODIGO).get_data(as_text=True)
    r = _codigo(c, DF.totp(segredo, T0 + 30))
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    html = c.get("/").get_data(as_text=True)
    assert "SERVIDOR RESERVA" in html and "permission denied" not in html
    # O usuário da reserva só lê: a linha no banco ficou como o principal a deixou.
    with psycopg.connect(os.environ["CG_PG_DSN"], autocommit=True) as pg, pg.cursor() as cur:
        schema = banco_pg.schema_do_caminho(casa["banco"])
        linha = cur.execute(f'SELECT ultimo_passo, falhas FROM "{schema}".dois_fatores '
                            "WHERE user_id = %s", (casa["uid"],)).fetchone()
    assert linha == (DF.passo_de(T0), 0)


def test_o_mesmo_codigo_nao_vale_duas_vezes_na_reserva(reserva_com_dois_fatores, relogio):
    casa = reserva_com_dois_fatores
    c, segredo = casa["c"], casa["segredo"]
    codigo = DF.totp(segredo, T0 + 30)
    _senha(c)
    assert _codigo(c, codigo).headers["Location"].endswith("/")
    with c.session_transaction() as sessao:
        token = sessao["csrf_token"]
    c.post("/logout", data={"csrf_token": token})
    _senha(c)
    r = _codigo(c, codigo)
    assert r.headers["Location"].endswith(TELA_DO_CODIGO)
    # O código do passo seguinte, sim.
    relogio.t = T0 + 60
    assert _codigo(c, DF.totp(segredo, T0 + 60)).headers["Location"].endswith("/")


def test_erros_seguidos_travam_na_reserva(reserva_com_dois_fatores, relogio):
    casa = reserva_com_dois_fatores
    c, segredo = casa["c"], casa["segredo"]
    _senha(c)
    for _ in range(DF.MAX_FALHAS):
        _codigo(c, _errado(segredo, T0))
    assert "travada" in c.get(TELA_DO_CODIGO).get_data(as_text=True)
    # Durante a trava nem o código certo entra.
    r = _codigo(c, DF.totp(segredo, T0 + 30))
    assert r.headers["Location"].endswith(TELA_DO_CODIGO)
    # Passada a trava, entra (a meia-sessão já morreu: senha de novo).
    relogio.t = T0 + DF.BLOQUEIO_MINUTOS * 60 + 30
    _senha(c)
    assert _codigo(c, DF.totp(segredo, relogio.t)).headers["Location"].endswith("/")


def test_codigo_de_recuperacao_nao_entra_na_reserva(reserva_com_dois_fatores, relogio):
    casa = reserva_com_dois_fatores
    c = casa["c"]
    _senha(c)
    r = _codigo(c, casa["codigos"][0])
    assert r.headers["Location"].endswith(TELA_DO_CODIGO)
    assert "não aceita código de recuperação" in c.get(TELA_DO_CODIGO).get_data(as_text=True)
    with psycopg.connect(os.environ["CG_PG_DSN"], autocommit=True) as pg, pg.cursor() as cur:
        schema = banco_pg.schema_do_caminho(casa["banco"])
        gastos = cur.execute(f'SELECT count(*) FROM "{schema}".dois_fatores_recuperacao '
                             "WHERE user_id = %s AND usado_em <> ''", (casa["uid"],)).fetchone()
    assert gastos == (0,)


def test_sem_a_chave_da_verificacao_a_reserva_diz_o_que_falta(reserva_com_dois_fatores, relogio):
    """O `dois_fatores.key` chega pelo pacote cifrado do principal; antes dele, a frase certa."""
    casa = reserva_com_dois_fatores
    c, segredo = casa["c"], casa["segredo"]
    (casa["dados"] / DF.NOME_DA_CHAVE).unlink()
    _senha(c)
    _codigo(c, DF.totp(segredo, T0 + 30))
    assert "ainda não chegou a este servidor reserva" in c.get(TELA_DO_CODIGO).get_data(as_text=True)


def test_ativacao_exigida_avisa_que_e_no_principal(cg_casa, monkeypatch):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({DF.CHAVE_DA_EXIGENCIA: '["ADMIN"]'})
    desfazer = _virar_reserva(cg_casa, monkeypatch)
    try:
        c = cg_casa["c"]
        r = _senha(c)
        assert r.status_code == 302 and r.headers["Location"].endswith("/login")
        assert "no servidor principal" in c.get("/login").get_data(as_text=True)
    finally:
        desfazer()


def test_os_outros_formularios_da_verificacao_continuam_recusados(reserva_com_dois_fatores, relogio):
    """Só o código da ENTRADA foi liberado: desativar, trocar códigos e o Gestor seguem no 503."""
    casa = reserva_com_dois_fatores
    c, segredo = casa["c"], casa["segredo"]
    _senha(c)
    _codigo(c, DF.totp(segredo, T0 + 30))
    with c.session_transaction() as sessao:
        token = sessao["csrf_token"]
    for url in ("/conta/dois-fatores/desativar", "/conta/dois-fatores/codigos",
                "/administrativo/gestor/dois-fatores/zerar"):
        r = c.post(url, data={"csrf_token": token, "senha": SENHA,
                              "codigo": DF.totp(segredo, T0 + 60)})
        assert r.status_code == 503, url
        assert "só consulta" in r.get_data(as_text=True)

"""P1 da revisao RI de 24/09/2026 — complementos da 3.6.195.

1. O comprovante de uma prenotacao com prazo suspenso nao diz «prazo vencido».
2. Onus achado so pela palavra do teor pede conferencia ao emitir a certidao.
3. Os ajustes da rotina CNIB (CPF da Central, robo diario) sao do oficial.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_prenotacao_prazo as PRAZO  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "oficial": _entrar(cg_casa["app"], "jean"),
            "balcao": _entrar(cg_casa["app"], "balcao")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _texto_do_odt(dados: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        xml = z.read("content.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


# ------------------------------------------------------ 1. comprovante

def test_comprovante_de_prenotacao_suspensa_nao_diz_prazo_vencido(casa):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
                   data_limite, situacao, criado_em, apresentante)
               VALUES (9101, '1A', '2025-12-01', '2026-01-05', 'ABERTO',
                       '2025-12-01T09:00', 'FULANO DE TAL')""")
        pid = int(cur.lastrowid)
    c = casa["oficial"]
    antes = _texto_do_odt(
        c.get(f"/registro-imoveis/protocolo/{pid}/comprovante").data)
    assert "prazo vencido" in antes

    with con:
        PRAZO.suspender(con, pid, motivo="USUCAPIAO", quem="OFICIAL",
                        hoje=date(2026, 1, 2))
    con.close()
    depois = _texto_do_odt(
        c.get(f"/registro-imoveis/protocolo/{pid}/comprovante").data)
    assert "prazo vencido" not in depois, (
        "o papel do apresentante disse «prazo vencido» de prenotacao suspensa")
    assert "prazo suspenso desde 02/01/2026" in depois
    assert "Usucapião extrajudicial" in depois


# ------------------------------------------------- 2. onus a conferir

def _ficha_com_atos(casa, numero, atos):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf)
               VALUES (?, '2', '2', 'ATIVA', 'ESTRUTURADA', 'MANUAL',
                       '2026-09-24T08:00', '2026-09-01', 'Cidade Exemplo', 'MA')""",
            (numero,))
        mid = int(cur.lastrowid)
        for n, natureza, teor in atos:
            con.execute(
                """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
                       natureza_titulo, teor, cancelado, hash_ato, lavrado_em)
                   VALUES (?, 'R', ?, '2026-09-10', ?, ?, 0, ?,
                           '2026-09-10T10:00')""",
                (mid, n, natureza, teor, f"h{mid}R{n}"))
    con.close()
    return mid


def _emitir_onus(casa, mid):
    c = casa["oficial"]
    tela = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": "ONUS", "fonte_corpo": "TEXTO",
        "requerente": "FULANO DE TAL",
        # Selo digitado: a casa de teste nao tem selador, e sem selo a
        # certidao volta NAO emitida antes do aviso de conferencia.
        "selo_texto": "SELO-DE-TESTE-0001"})
    with c.session_transaction() as sessao:
        return [texto for _cat, texto in sessao.get("_flashes", [])]


def test_onus_so_pela_palavra_do_teor_pede_conferencia_na_emissao(casa):
    mid = _ficha_com_atos(casa, "4103", [
        (1, "Compra e Venda", "R-1/4103 - COMPRA E VENDA."),
        (2, None, "R-2/4103 - HIPOTECA CEDULAR DE 1º GRAU em favor do banco.")])
    recados = _emitir_onus(casa, mid)
    conferir = [r for r in recados if r.startswith("Confira antes de entregar")]
    assert conferir, recados
    assert "R-02" in conferir[0] or "R-2" in conferir[0]


def test_onus_pela_natureza_nao_pede_conferencia(casa):
    mid = _ficha_com_atos(casa, "4104", [
        (1, "Hipoteca", "R-1/4104 - HIPOTECA de 1º grau.")])
    recados = _emitir_onus(casa, mid)
    assert not [r for r in recados if r.startswith("Confira antes de entregar")]


# ---------------------------------------------------- 3. ajustes CNIB

def test_balcao_nao_muda_cpf_nem_rotina_da_cnib(casa):
    b = casa["balcao"]
    tela = b.get("/registro-imoveis/cnib/central").get_data(as_text=True)
    assert "cnib/central/ajustes" not in tela, (
        "o formulario de ajustes aparece para quem a rota recusa")
    r = b.post("/registro-imoveis/cnib/central/ajustes",
               data={"csrf_token": _token(tela), "cpf": "00000004855",
                     "rotina": "1"})
    assert r.status_code == 403


def test_oficial_continua_ajustando_a_rotina_da_cnib(casa):
    c = casa["oficial"]
    tela = c.get("/registro-imoveis/cnib/central").get_data(as_text=True)
    assert "cnib/central/ajustes" in tela
    r = c.post("/registro-imoveis/cnib/central/ajustes",
               data={"csrf_token": _token(tela), "cpf": "00000004855"})
    assert r.status_code == 302

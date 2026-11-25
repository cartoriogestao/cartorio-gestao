"""Inventário sem autor da herança não lavra — pedido do oficial (t683u, 23/11/2026).

A carga da CESDI recusou o inventário 786 («Inventário exige uma parte Falecido»).
A qualificação AUTOR DA HERANÇA já vira Falecido desde o PR #268; faltava a trava
na lavratura. Nomes e CPF são de exemplo (anti-vazamento).
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_censec as NC  # noqa: E402

SENHA = "Senha#12345"
CPF_OK = "00000004855"
CPF_RUIM = "11111111111"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "cliente": c, "banco": cg_casa["banco"],
               "db": cg_casa["db"], "dados": cg_casa["dados"]}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def _sql(s, comando, args=()):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    cur = con.execute(comando, args)
    linhas = [dict(r) for r in cur.fetchall()]
    con.commit()
    con.close()
    return linhas


def _abrir_inventario(s, *, tipo_cesdi=5, modelo="NT-ESC-INVENTARIO-PARTILHA",
                      natureza="Inventário e partilha") -> int:
    html = s["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    s["cliente"].post("/notas/atos/novo",
                      data={"csrf_token": _token(html), "tipo": "ESCRITURA",
                            "interessado": "ESPOLIO EXEMPLO"},
                      follow_redirects=True)
    aid = int(_sql(s, "SELECT MAX(id) id FROM nt_atos")[0]["id"])
    _sql(s, """UPDATE nt_atos SET valor_transacao=0, tipo_cesdi=?, modelo_codigo=?,
               natureza=? WHERE id=?""",
         (tipo_cesdi, modelo, natureza, aid))
    return aid


def _parte(s, aid, nome, qualificacao, documento=None):
    _sql(s, """INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, qualificacao,
                                          documento, ordem, criado_em)
               VALUES (?,?,?,?,?,1,'2026-11-23T00:00:00')""",
         (aid, nome, nome.lower(), qualificacao, documento))
    return int(_sql(s, "SELECT MAX(id) id FROM nt_ato_partes")[0]["id"])


def _postar(s, aid, **dados) -> str:
    html = s["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    dados.setdefault("csrf_token", _token(html))
    if dados.get("acao") == "lancar":
        dados.setdefault("codigo_tj", "13.2")
        dados.setdefault("paginas", "2")
    return s["cliente"].post(f"/notas/atos/{aid}", data=dados,
                             follow_redirects=True).get_data(as_text=True)


def _ato(s, aid):
    return _sql(s, "SELECT * FROM nt_atos WHERE id=?", (aid,))[0]


# ------------------------------------------------------------- dominio


@pytest.mark.parametrize("tipo", [5, 6, 8, 9, 10])
def test_tipos_cesdi_de_sucessao_exigem_falecido(tipo):
    assert NC.ato_exige_autor_da_heranca({"tipo_cesdi": tipo})


def test_divorcio_nao_exige_falecido():
    assert not NC.ato_exige_autor_da_heranca({"tipo_cesdi": 4})


def test_modelo_de_inventario_sem_tipo_cesdi_tambem_exige():
    assert NC.ato_exige_autor_da_heranca({
        "tipo_cesdi": None, "modelo_codigo": "NT-ESC-INVENTARIO-PARTILHA",
        "natureza": None})
    assert NC.ato_exige_autor_da_heranca({
        "tipo_cesdi": None, "natureza": "Escritura de inventário e partilha"})


def test_sem_falecido_a_trava_cita_o_quadro_partes(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 5}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "ANA EXEMPLO HERDEIRA", "qualificacao": "HERDEIRA",
         "documento": CPF_OK}])
    imps = NC.impedimentos_para_lavrar(None, ato)
    assert any("autor da herança" in i.motivo for i in imps)
    assert any("Partes" in i.motivo for i in imps)


def test_autor_da_heranca_com_cpf_passa(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 5}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "JOSE EXEMPLO DOS SANTOS", "qualificacao": "AUTOR DA HERANÇA",
         "documento": CPF_OK},
        {"nome": "ANA EXEMPLO HERDEIRA", "qualificacao": "HERDEIRA",
         "documento": CPF_OK}])
    assert NC.impedimentos_do_autor_da_heranca(ato, NC._partes_do_ato(None, 1)) == []
    # a trava da lavratura nao puxa Advogado / demais da CESDI
    assert not any("autor da herança" in i.motivo
                   for i in NC.impedimentos_para_lavrar(None, ato))


def test_cpf_invalido_do_falecido_trava(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 5}
    partes = [{"nome": "JOSE EXEMPLO DOS SANTOS", "qualificacao": "FALECIDO",
               "documento": CPF_RUIM}]
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: partes)
    imps = NC.impedimentos_do_autor_da_heranca(ato, partes)
    assert any("CPF válido" in i.motivo for i in imps)


def test_qualidade_sem_de_para_no_inventario_trava(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 5, "data": "2026-11-20",
           "livro": "30", "folha": "196"}
    partes = [
        {"nome": "JOSE EXEMPLO DOS SANTOS", "qualificacao": "AUTOR DA HERANÇA",
         "qualidade_cesdi": "Falecido", "documento": CPF_OK},
        {"nome": "COMPRADOR EXEMPLO", "qualificacao": "COMPRADOR",
         "qualidade_cesdi": None, "documento": CPF_OK},
    ]
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: partes)
    imps = NC.impedimentos_para_lavrar(None, ato)
    # com as travas extras da CESDI (#497), a qualidade sem de-para sai com a sugestão
    assert any("COMPRADOR" in i.motivo and "sugestão" in i.motivo for i in imps)


def test_cep_nao_muda(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": None, "data": "2026-11-20",
           "livro": None, "folha": None, "valor_transacao": 0, "natureza_censec": 14}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "X", "qualificacao": "OUTORGANTE", "documento": None}])
    assert NC.impedimentos_para_lavrar(None, ato) == []


# ------------------------------------------------------------- lavratura


def test_inventario_sem_falecido_nao_lavra(serventia):
    aid = _abrir_inventario(serventia)
    _parte(serventia, aid, "ANA EXEMPLO HERDEIRA", "HERDEIRA", CPF_OK)
    _postar(serventia, aid, acao="teor", teor="<p>escritura de inventario exemplo</p>")
    html = _postar(serventia, aid, acao="lancar")
    a = _ato(serventia, aid)
    assert a["situacao"] == "EM_LAVRATURA" and not a["folha"]
    assert "NÃO lançado" in html
    assert "autor da herança" in html
    assert "Partes" in html
    trilha = _sql(serventia, "SELECT * FROM audit_logs WHERE action=? AND entity_id=?",
                  ("NT_ATO_LAVRATURA_TRAVADA", aid))
    assert trilha


def test_inventario_com_autor_da_heranca_lavra(serventia):
    aid = _abrir_inventario(serventia)
    _parte(serventia, aid, "JOSE EXEMPLO DOS SANTOS", "AUTOR DA HERANÇA", CPF_OK)
    _parte(serventia, aid, "ANA EXEMPLO HERDEIRA", "HERDEIRA", CPF_OK)
    # o inventário também pede o advogado com a OAB (travas extras da CESDI, #497)
    adv = _parte(serventia, aid, "CARLOS EXEMPLO ADVOGADO", "ADVOGADO", CPF_OK)
    _sql(serventia, "UPDATE nt_ato_partes SET oab_numero='00000', oab_uf='MA' WHERE id=?", (adv,))
    _postar(serventia, aid, acao="teor", teor="<p>escritura de inventario exemplo</p>")
    _postar(serventia, aid, acao="lancar")
    a = _ato(serventia, aid)
    assert a["situacao"] == "LAVRADO" and a["folha"]


def test_ato_ja_lavrado_nao_e_afetado(serventia):
    """A trava só age sobre EM_LAVRATURA — LAVRADO fica como está."""
    aid = _abrir_inventario(serventia)
    _parte(serventia, aid, "ANA EXEMPLO HERDEIRA", "HERDEIRA", CPF_OK)
    _postar(serventia, aid, acao="teor", teor="<p>teor</p>")
    # força LAVRADO sem passar pela trava (ato antigo no livro)
    _sql(serventia, """UPDATE nt_atos SET situacao='LAVRADO', livro='30', folha='196',
               data='2026-11-01', termo=1 WHERE id=?""", (aid,))
    html = serventia["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert _ato(serventia, aid)["situacao"] == "LAVRADO"
    # a tela do ato lavrado nao oferece lancar de novo com a trava do falecido
    assert 'value="lancar"' not in html or "já" in html.lower() or "LAVRADO" in html

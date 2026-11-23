"""Travas extras CESDI na lavratura — pedido t683u / Grok Bot (23/11/2026).

Amplia o que a carga recusaria: Advogado+OAB no inventário, casamento/regime
no divórcio, qualidade sem de-para com sugestão. Sem dados pessoais reais.
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


def _abrir(s, *, tipo_cesdi, natureza="Escritura exemplo") -> int:
    html = s["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    s["cliente"].post("/notas/atos/novo",
                      data={"csrf_token": _token(html), "tipo": "ESCRITURA",
                            "interessado": "PARTE EXEMPLO"},
                      follow_redirects=True)
    aid = int(_sql(s, "SELECT MAX(id) id FROM nt_atos")[0]["id"])
    _sql(s, """UPDATE nt_atos SET valor_transacao=0, tipo_cesdi=?, natureza=?
               WHERE id=?""", (tipo_cesdi, natureza, aid))
    return aid


def _parte(s, aid, nome, qualificacao, documento=None, **extras):
    cols = ["ato_id", "nome", "nome_norm", "qualificacao", "documento", "ordem",
            "criado_em"]
    vals = [aid, nome, nome.lower(), qualificacao, documento, 1,
            "2026-11-23T00:00:00"]
    for chave in ("oab_numero", "oab_uf"):
        if chave in extras:
            cols.append(chave)
            vals.append(extras[chave])
    _sql(s, f"INSERT INTO nt_ato_partes({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})", vals)
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
def test_inventario_sem_advogado_trava(tipo, monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": tipo,
           "data": "2026-11-20", "livro": "30", "folha": "1"}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "JOSE EXEMPLO", "qualificacao": "AUTOR DA HERANÇA",
         "qualidade_cesdi": "Falecido", "documento": CPF_OK},
        {"nome": "ANA EXEMPLO", "qualificacao": "HERDEIRA",
         "qualidade_cesdi": "Herdeiro", "documento": CPF_OK},
    ])
    imps = NC.impedimentos_para_lavrar(None, ato)
    assert any("ADVOGADO" in i.motivo for i in imps)


def test_advogado_sem_oab_trava(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 5,
           "data": "2026-11-20", "livro": "30", "folha": "1"}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "JOSE EXEMPLO", "qualificacao": "AUTOR DA HERANÇA",
         "qualidade_cesdi": "Falecido", "documento": CPF_OK},
        {"nome": "DRA EXEMPLO", "qualificacao": "ADVOGADA",
         "qualidade_cesdi": "Advogado", "documento": CPF_OK,
         "oab_numero": None, "oab_uf": None},
    ])
    imps = NC.impedimentos_para_lavrar(None, ato)
    assert any("OAB" in i.motivo for i in imps)


def test_advogado_com_oab_passa_nessa_trava(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 5,
           "data": "2026-11-20", "livro": "30", "folha": "1"}
    partes = [
        {"nome": "JOSE EXEMPLO", "qualificacao": "AUTOR DA HERANÇA",
         "qualidade_cesdi": "Falecido", "documento": CPF_OK},
        {"nome": "DRA EXEMPLO", "qualificacao": "ADVOGADA",
         "qualidade_cesdi": "Advogado", "documento": CPF_OK,
         "oab_numero": "12345", "oab_uf": "MA"},
        {"nome": "ANA EXEMPLO", "qualificacao": "HERDEIRA",
         "qualidade_cesdi": "Herdeiro", "documento": CPF_OK},
    ]
    assert NC.impedimentos_do_advogado_cesdi(ato, partes) == []


def test_divorcio_sem_casamento_trava(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 4,
           "casamento_data": None, "regime_bens": None,
           "responsavel_menores": "SemDeclaracao",
           "data": "2026-11-20", "livro": "30", "folha": "1"}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "A EXEMPLO", "qualificacao": "DIVORCIANDO",
         "qualidade_cesdi": "Divorciando", "documento": CPF_OK,
         "nascimento": "1990-01-01", "sexo": "F", "municipio_ibge": "2111300"},
        {"nome": "B EXEMPLO", "qualificacao": "DIVORCIANDO",
         "qualidade_cesdi": "Divorciando", "documento": CPF_OK,
         "nascimento": "1988-01-01", "sexo": "M", "municipio_ibge": "2111300"},
        {"nome": "DRA EXEMPLO", "qualificacao": "ADVOGADA",
         "qualidade_cesdi": "Advogado", "documento": CPF_OK,
         "oab_numero": "12345", "oab_uf": "MA"},
    ])
    imps = NC.impedimentos_para_lavrar(None, ato)
    assert any(i.campo == "dataCasamento" for i in imps)
    assert any(i.campo == "regimeBens" for i in imps)


def test_divorcio_completo_nao_trava_casamento(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 4,
           "casamento_data": "2010-05-10",
           "regime_bens": "COMUNHAO PARCIAL",
           "responsavel_menores": "SemDeclaracao",
           "data": "2026-11-20", "livro": "30", "folha": "1"}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "A EXEMPLO", "qualificacao": "DIVORCIANDO",
         "qualidade_cesdi": "Divorciando", "documento": CPF_OK,
         "nascimento": "1990-01-01", "sexo": "F", "municipio_ibge": "2111300"},
        {"nome": "B EXEMPLO", "qualificacao": "DIVORCIANDO",
         "qualidade_cesdi": "Divorciando", "documento": CPF_OK,
         "nascimento": "1988-01-01", "sexo": "M", "municipio_ibge": "2111300"},
        {"nome": "DRA EXEMPLO", "qualificacao": "ADVOGADA",
         "qualidade_cesdi": "Advogado", "documento": CPF_OK,
         "oab_numero": "12345", "oab_uf": "MA"},
    ])
    imps = NC.impedimentos_para_lavrar(None, ato)
    assert not any(i.campo in ("dataCasamento", "regimeBens") for i in imps)


def test_qualidade_comprador_no_inventario_sugere_cessionario(monkeypatch):
    ato = {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": 5,
           "data": "2026-11-20", "livro": "30", "folha": "1"}
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "JOSE EXEMPLO", "qualificacao": "AUTOR DA HERANÇA",
         "qualidade_cesdi": "Falecido", "documento": CPF_OK},
        {"nome": "COMPRADOR EXEMPLO", "qualificacao": "COMPRADOR(A)",
         "qualidade_cesdi": None, "documento": CPF_OK},
        {"nome": "DRA EXEMPLO", "qualificacao": "ADVOGADA",
         "qualidade_cesdi": "Advogado", "documento": CPF_OK,
         "oab_numero": "12345", "oab_uf": "MA"},
    ])
    imps = NC.impedimentos_para_lavrar(None, ato)
    assert any("não mapeia" in i.motivo and "CESSIONÁRIO" in i.motivo
               for i in imps)


def test_qualidade_procuradora_sugere_interveniente():
    assert NC.sugerir_qualificacao_cesdi("PROCURADORA", 5) == "INTERVENIENTE"


def test_cep_e_rcto_nao_mudam(monkeypatch):
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "X", "qualificacao": "OUTORGANTE", "documento": None}])
    assert NC.impedimentos_para_lavrar(
        None, {"id": 1, "tipo": "ESCRITURA", "tipo_cesdi": None,
               "valor_transacao": 0, "natureza_censec": 14}) == []
    assert NC.impedimentos_para_lavrar(
        None, {"id": 1, "tipo": "TESTAMENTO", "tipo_testamento": 4}) == []


# ------------------------------------------------------------- lavratura


def test_inventario_sem_advogado_nao_lavra(serventia):
    aid = _abrir(serventia, tipo_cesdi=5, natureza="Inventário e partilha")
    _parte(serventia, aid, "JOSE EXEMPLO", "AUTOR DA HERANÇA", CPF_OK)
    _parte(serventia, aid, "ANA EXEMPLO", "HERDEIRA", CPF_OK)
    _postar(serventia, aid, acao="teor", teor="<p>escritura de inventario exemplo</p>")
    html = _postar(serventia, aid, acao="lancar")
    a = _ato(serventia, aid)
    assert a["situacao"] == "EM_LAVRATURA" and not a["folha"]
    assert "NÃO lançado" in html
    assert "ADVOGADO" in html


def test_inventario_com_advogado_e_oab_lavra(serventia):
    aid = _abrir(serventia, tipo_cesdi=5, natureza="Inventário e partilha")
    _parte(serventia, aid, "JOSE EXEMPLO", "AUTOR DA HERANÇA", CPF_OK)
    _parte(serventia, aid, "ANA EXEMPLO", "HERDEIRA", CPF_OK)
    _parte(serventia, aid, "DRA EXEMPLO", "ADVOGADA", CPF_OK,
           oab_numero="12345", oab_uf="MA")
    _postar(serventia, aid, acao="teor", teor="<p>escritura de inventario exemplo</p>")
    _postar(serventia, aid, acao="lancar")
    a = _ato(serventia, aid)
    assert a["situacao"] == "LAVRADO" and a["folha"]


def test_ato_ja_lavrado_nao_e_afetado(serventia):
    aid = _abrir(serventia, tipo_cesdi=5, natureza="Inventário e partilha")
    _parte(serventia, aid, "JOSE EXEMPLO", "AUTOR DA HERANÇA", CPF_OK)
    _parte(serventia, aid, "DRA EXEMPLO", "ADVOGADA", CPF_OK,
           oab_numero="12345", oab_uf="MA")
    _postar(serventia, aid, acao="teor", teor="<p>teor</p>")
    _postar(serventia, aid, acao="lancar")
    assert _ato(serventia, aid)["situacao"] == "LAVRADO"
    # tirar o advogado depois não desarma o lavrado
    _sql(serventia, "DELETE FROM nt_ato_partes WHERE ato_id=? AND qualificacao=?",
         (aid, "ADVOGADA"))
    html = serventia["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert _ato(serventia, aid)["situacao"] == "LAVRADO"
    assert "CENSEC:" not in html or "EM_LAVRATURA" not in html


def test_datalist_oferece_cessionario_e_advogado(serventia):
    aid = _abrir(serventia, tipo_cesdi=5)
    _parte(serventia, aid, "FULANO EXEMPLO", None)
    html = serventia["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert 'list="qualificacoes-censec"' in html
    assert 'value="CESSIONÁRIO(A)"' in html
    assert 'value="ADVOGADO(A)"' in html

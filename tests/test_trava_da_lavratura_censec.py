"""
A trava da lavratura — ordem do oficial em 09/10/2026: «resolve os problemas
dessas procuracoes e cria travas na lavratura quando tivermos esses problemas
e nao for possivel enviar pra censec».

OS DOIS CASOS QUE A PEDIRAM, medidos na produção no mesmo dia:
    - ato 791 (livro 28, fl. 47): procuração lavrada, selada e trasladada com
      «[OUTORGADO(S) — QUALIFIQUE A PARTE NO ATO]» no lugar do procurador;
    - ato 788 (livro 28, fl. 46): três das quatro partes sem qualificação, e
      a CEP exige uma por parte.
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


def _abrir_escritura(s) -> int:
    html = s["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    s["cliente"].post("/notas/atos/novo",
                      data={"csrf_token": _token(html), "tipo": "ESCRITURA",
                            "interessado": "MARIA DAS DORES"},
                      follow_redirects=True)
    aid = int(_sql(s, "SELECT MAX(id) id FROM nt_atos")[0]["id"])
    # o que a CEP exige da escritura e não é objeto destes testes
    _sql(s, "UPDATE nt_atos SET valor_transacao=0, natureza_censec=14 WHERE id=?", (aid,))
    return aid


def _parte(s, aid, nome, qualificacao):
    _sql(s, """INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, qualificacao,
                                          ordem, criado_em)
               VALUES (?,?,?,?,1,'2026-10-09T00:00:00')""",
         (aid, nome, nome.lower(), qualificacao))
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


# ------------------------------------------------------------- o campo em branco

def test_campo_em_branco_no_teor_trava_a_lavratura(serventia):
    """O caso do ato 791: o colchete do modelo ia para o livro."""
    aid = _abrir_escritura(serventia)
    _parte(serventia, aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    _postar(serventia, aid, acao="teor",
            teor="<p>nomeia e constitui seu bastante procurador "
                 "[OUTORGADO(S) — QUALIFIQUE A PARTE NO ATO], a quem confere</p>")
    html = _postar(serventia, aid, acao="lancar")
    a = _ato(serventia, aid)
    assert a["situacao"] == "EM_LAVRATURA" and not a["livro"] and not a["folha"]
    assert "NÃO lançado" in html and "campo em branco" in html
    assert "QUALIFIQUE A PARTE NO ATO" in html
    trilha = _sql(serventia, "SELECT * FROM audit_logs WHERE action=? AND entity_id=?",
                  ("NT_ATO_LAVRATURA_TRAVADA", aid))
    assert trilha, "a recusa tem de ficar na auditoria"


# ------------------------------------------------------------- a CENSEC

def test_parte_sem_qualificacao_trava_e_a_tela_corrige_sem_tirar_a_parte(serventia):
    """O caso do ato 788: parte sem qualificação fica fora da CEP."""
    aid = _abrir_escritura(serventia)
    pid = _parte(serventia, aid, "ANTONIO BORBA SOUSA", None)
    _postar(serventia, aid, acao="teor", teor="<p>teor completo do ato</p>")

    html = _postar(serventia, aid, acao="lancar")
    assert _ato(serventia, aid)["situacao"] == "EM_LAVRATURA"
    assert "CENSEC" in html and "ANTONIO BORBA SOUSA" in html
    assert "quadro «Partes»" in html, "a recusa tem de dizer onde se corrige"

    html = _postar(serventia, aid, acao="qualificacao_parte", parte_id=pid,
                   qualificacao="outorgante")
    assert _sql(serventia, "SELECT qualificacao FROM nt_ato_partes WHERE id=?",
                (pid,))[0]["qualificacao"] == "OUTORGANTE"
    mudanca = _sql(serventia, "SELECT details FROM audit_logs WHERE action=?",
                   ("NT_ATO_PARTE_QUALIFICACAO",))
    assert mudanca and "OUTORGANTE" in mudanca[-1]["details"]

    _postar(serventia, aid, acao="lancar")
    a = _ato(serventia, aid)
    assert a["situacao"] == "LAVRADO" and a["folha"], "corrigido, o ato tem de lavrar"


def test_qualificacao_que_a_cep_nao_entende_grava_mas_avisa(serventia):
    aid = _abrir_escritura(serventia)
    pid = _parte(serventia, aid, "FULANO", "OUTORGANTE")
    html = _postar(serventia, aid, acao="qualificacao_parte", parte_id=pid,
                   qualificacao="síndico do condomínio")
    assert "não corresponde a nenhuma qualidade da CEP" in html


def test_a_tela_oferece_corrigir_a_qualificacao(serventia):
    aid = _abrir_escritura(serventia)
    _parte(serventia, aid, "FULANO", None)
    html = serventia["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert 'value="qualificacao_parte"' in html
    assert 'list="qualificacoes-censec"' in html


# ------------------------------------------------------------- o domínio

def test_na_procuracao_o_procurador_e_o_outorgado():
    assert NC.qualidade_cep("PROCURADOR", "PROCURACAO") == "Outorgado"
    assert NC.qualidade_cep("Procuradora", "PROCURACAO_PREVIDENCIARIA") == "Outorgado"
    # na escritura ele representa uma parte, e intervém
    assert NC.qualidade_cep("PROCURADOR DO VENDEDOR", "ESCRITURA") == "Interveniente"
    assert NC.qualidade_cep("PROCURADOR") == "Interveniente"
    assert NC.qualidade_cep("ASSINA A ROGO", "PROCURACAO") == "Interveniente"


def test_a_trava_ignora_o_que_a_propria_lavratura_preenche(monkeypatch):
    """Antes de lavrar não há livro nem folha — eles saem do lançamento."""
    ato = {"id": 1, "tipo": "ATA", "data": None, "livro": None, "folha": None,
           "tipo_cesdi": None, "tipo_testamento": None}

    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: [
        {"nome": "X", "qualificacao": "REQUERENTE", "documento": None}])

    assert NC.impedimentos_para_lavrar(None, ato) == []


def test_o_ato_anterior_de_outra_serventia_nao_trava(monkeypatch):
    """Revogação de ato de fora: o anterior só se informa depois de lavrar."""
    ato = {"id": 1, "tipo": "REVOGACAO", "data": "2026-10-09", "livro": None,
           "folha": None, "tipo_cesdi": None, "tipo_testamento": None,
           "anterior_livro": None, "anterior_folha": None, "anterior_cns": None}

    partes = [{"nome": "X", "qualificacao": "OUTORGANTE", "documento": None}]
    monkeypatch.setattr(NC, "_partes_do_ato", lambda con, ato_id: partes)

    assert NC.impedimentos_para_lavrar(None, ato) == []
    # e a remessa continua acusando
    assert any(p.campo.startswith("referentes")
               for p in NC.conferir_ato_cep(ato, partes))


def test_cesdi_e_rcto_nao_travam_porque_nao_ha_onde_corrigir():
    assert NC.central_do_ato({"tipo": "ESCRITURA", "tipo_cesdi": 4}) == "CESDI"
    assert NC.central_do_ato({"tipo": "TESTAMENTO"}) == "RCTO"
    assert "CESDI" not in NC.CENTRAIS_QUE_TRAVAM
    assert "RCTO" not in NC.CENTRAIS_QUE_TRAVAM
    assert NC.impedimentos_para_lavrar(None, {"id": 1, "tipo": "ESCRITURA",
                                              "tipo_cesdi": 4}) == []

"""O ACERVO NÃO VIRA TRABALHO DO DIA NA TELA DOS INSTRUMENTOS — 30/10/2026.

Emitidos os protestos lavrados no sistema, a fila deles zerou e a tela caiu
sozinha em «todos»: o oficial abriu para assinar e leu «200 na lista», todos do
acervo do E-Ofício. «Marcar todos» e «Emitir os marcados» gastariam 200 números
do exercício com papel que a casa antiga nunca guardou.

O QUE ESTES TESTES GUARDAM
      - **sem filtro, a tela nunca mostra o acervo**, mesmo com a fila zerada;
      - **o que falta assinar vem primeiro**, com o número e o link no alto;
      - **no acervo e em «todos» não existe «Marcar todos»**;
      - **o lote com protesto do acervo exige afirmação expressa**, conferida
        pelos títulos marcados, e não pelo filtro da tela;
      - **«Emitir só este» continua como estava**.

Dados fictícios (LGPD): a lista de `tests/fixtures/anti_vazamento`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import afirmacoes_expressas as AFX  # noqa: E402
import protesto_instrumento as PI  # noqa: E402

from test_protesto_aviso_web import _con, _token, s  # noqa: E402,F401
from test_protesto_instrumento import AGORA, SERVENTIA, banco, protestado  # noqa: E402
from test_protesto_instrumentos_em_lote import (  # noqa: E402
    _do_acervo, _emitidos, _instrumento, _protestado_pela_casa, _transacao_de)

BOA = "conferi cada protesto marcado no livro antigo e o apresentante pediu o papel"
CURTA = "pediram"
ENDERECO = "/protesto/instrumentos"
LOTE = ENDERECO + "/emitir-lote"


def _protesto_de_acervo(s, n: int = 1) -> int:
    tid = _protestado_pela_casa(s, n)
    con = _con(s)
    with con:
        _do_acervo(con, tid)
    con.close()
    return tid


def _tela(s, consulta: str = "") -> str:
    r = s["c"].get(ENDERECO + consulta)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _postar_lote(s, ids, **campos):
    return s["c"].post(
        LOTE, data={"csrf_token": _token(_tela(s)),
                    "titulo_id": [str(n) for n in ids], **campos},
        follow_redirects=True)


def _afirmacoes(s) -> list:
    con = _con(s)
    try:
        return con.execute(
            "SELECT entity_type, entity_id, details FROM audit_logs "
            "WHERE action='AFIRMACAO_EXPRESSA' ORDER BY id").fetchall()
    finally:
        con.close()


def _sem_marcar_todos(html: str) -> None:
    assert 'data-marcar="titulo_id"' not in html
    assert 'data-marcar-cabecalho="titulo_id"' not in html
    assert "Marcar todos" not in html


# ------------------------------------------------------- o lote, no domínio


def test_lote_com_acervo_sem_afirmacao_nao_emite_nem_o_do_sistema():
    con = banco()
    novo = protestado(con)
    velho = protestado(con, numero_titulo="00124", protocolo="2606090002")
    _do_acervo(con, velho)
    con.commit()
    with pytest.raises(PI.InstrumentoError, match="acervo do E-Ofício"):
        PI.emitir_lote(_transacao_de(con), [novo, velho], serventia=SERVENTIA,
                       agora=AGORA)
    assert con.execute("SELECT COUNT(*) FROM pt_instrumentos").fetchone()[0] == 0


@pytest.mark.parametrize("afirmo, texto, robo", [
    (True, CURTA, False),      # a caixa sem o texto
    (False, BOA, False),       # o texto sem a caixa
    (True, AFX.MODELO, False),  # só a frase de abertura
    (True, BOA, True),         # robô não afirma
])
def test_a_afirmacao_do_acervo_segue_o_contrato_comum(afirmo, texto, robo):
    con = banco()
    velho = protestado(con)
    _do_acervo(con, velho)
    con.commit()
    with pytest.raises(PI.InstrumentoError):
        PI.emitir_lote(_transacao_de(con), [velho], serventia=SERVENTIA,
                       agora=AGORA, afirmo=afirmo, afirmacao=texto, robo=robo)
    assert con.execute("SELECT COUNT(*) FROM pt_instrumentos").fetchone()[0] == 0


def test_com_a_afirmacao_o_lote_emite_e_devolve_o_que_se_afirmou():
    con = banco()
    novo = protestado(con)
    velho = protestado(con, numero_titulo="00124", protocolo="2606090002")
    _do_acervo(con, velho)
    con.commit()
    r = PI.emitir_lote(_transacao_de(con), [novo, velho], serventia=SERVENTIA,
                       agora=AGORA, afirmo=True, afirmacao=BOA)
    assert sorted(f["titulo_id"] for f in r["feitos"]) == sorted([novo, velho])
    af = r["afirmacao_de_acervo"]
    assert af["regra"] == "INSTRUMENTO_DE_ACERVO_EM_LOTE"
    assert af["titulos"] == [velho]
    assert af["afirmacao"].startswith(AFX.MODELO)


def test_lote_so_do_sistema_nao_pede_afirmacao():
    con = banco()
    novo = protestado(con)
    r = PI.emitir_lote(_transacao_de(con), [novo], serventia=SERVENTIA,
                       agora=AGORA)
    assert [f["titulo_id"] for f in r["feitos"]] == [novo]
    assert r["afirmacao_de_acervo"] is None


# ------------------------------------------------------- sem queda automática


@pytest.mark.parametrize("consulta", ["", "?quais=qualquer", "?desde=hoje"])
def test_sem_filtro_valido_a_tela_nunca_mostra_o_acervo(s, consulta):
    _protesto_de_acervo(s)
    html = _tela(s, consulta)
    assert 'name="titulo_id"' not in html
    assert "quais=acervo" in html
    if not consulta.startswith("?desde"):
        assert "Nenhum protesto deste sistema sem instrumento" in html
        assert "lavrados neste sistema — 0 na lista" in html


def test_o_acervo_aparece_quando_a_pessoa_escolhe_o_filtro(s):
    velho = _protesto_de_acervo(s)
    for filtro in ("acervo", "todos"):
        html = _tela(s, f"?quais={filtro}")
        assert f'name="titulo_id" value="{velho}"' in html
        assert "Emitir só este" in html


# ------------------------------------------------------- a ordem da tela


def test_o_que_falta_assinar_vem_antes_com_o_numero_no_alto(s):
    _instrumento(s, 1)
    _instrumento(s, 2)
    _protestado_pela_casa(s, 3)
    html = _tela(s)
    assert "<strong>2 a assinar.</strong>" in html
    assert (html.index('href="#a-assinar"') < html.index('id="a-assinar"')
            < html.index('id="a-emitir"'))


def test_sem_nada_a_assinar_a_fila_de_emitir_vem_primeiro(s):
    _protestado_pela_casa(s)
    html = _tela(s)
    assert 'href="#a-assinar"' not in html
    assert html.index('id="a-emitir"') < html.index('id="a-assinar"')
    assert "Nenhum instrumento esperando assinatura" in html


# ------------------------------------------------------- o acervo protegido


@pytest.mark.parametrize("filtro", ["acervo", "todos"])
def test_no_filtro_com_acervo_nao_existe_marcar_todos(s, filtro):
    _protesto_de_acervo(s)
    html = _tela(s, f"?quais={filtro}")
    _sem_marcar_todos(html)
    assert 'name="afirmo"' in html
    assert 'name="afirmacao"' in html
    assert "Emitir os marcados" in html


def test_no_filtro_do_sistema_marcar_todos_continua_e_nao_ha_afirmacao(s):
    _protestado_pela_casa(s)
    html = _tela(s)
    assert 'data-marcar="titulo_id"' in html
    assert 'name="afirmo"' not in html


def test_a_rota_recusa_o_acervo_sem_afirmacao(s):
    velho = _protesto_de_acervo(s)
    r = _postar_lote(s, [velho])
    assert r.status_code == 200
    assert "Nada foi emitido" in r.get_data(as_text=True)
    assert _emitidos(s) == 0
    assert _afirmacoes(s) == []


def test_a_rota_confere_os_titulos_e_nao_o_filtro_da_tela(s):
    """Quem monta o POST com a volta para o filtro do sistema não escapa."""
    velho = _protesto_de_acervo(s)
    novo = _protestado_pela_casa(s, 2)
    r = _postar_lote(s, [novo, velho], voltar=f"{ENDERECO}?quais=sistema")
    assert "Nada foi emitido" in r.get_data(as_text=True)
    assert _emitidos(s) == 0


def test_a_rota_recusa_a_afirmacao_de_robo(s, monkeypatch):
    import selo_robo as SR
    velho = _protesto_de_acervo(s)
    tela = _tela(s)
    monkeypatch.setattr(SR, "usuario_e_robo", lambda user=None: user is None)
    r = s["c"].post(LOTE, data={"csrf_token": _token(tela),
                                "titulo_id": [str(velho)],
                                "afirmo": "1", "afirmacao": BOA},
                    follow_redirects=True)
    assert "conta de robô" in r.get_data(as_text=True)
    assert _emitidos(s) == 0


def test_a_afirmacao_vai_a_auditoria_so_para_o_protesto_do_acervo(s):
    velho = _protesto_de_acervo(s)
    novo = _protestado_pela_casa(s, 2)
    r = _postar_lote(s, [novo, velho], afirmo="1", afirmacao=BOA)
    assert "2 instrumento(s) emitido(s)" in r.get_data(as_text=True)
    assert _emitidos(s) == 2
    linhas = _afirmacoes(s)
    assert len(linhas) == 1
    assert linhas[0]["entity_type"] == "pt_titulos"
    assert int(linhas[0]["entity_id"]) == velho
    detalhes = json.loads(linhas[0]["details"])
    assert detalhes["regra"] == "INSTRUMENTO_DE_ACERVO_EM_LOTE"
    assert detalhes["afirmacao"] == f"{AFX.MODELO} {BOA}"
    assert detalhes["o_que_faltava"]
    assert detalhes["instrumento"]


def test_o_lote_do_sistema_nao_pede_afirmacao_pela_tela(s):
    novo = _protestado_pela_casa(s)
    r = _postar_lote(s, [novo])
    assert "1 instrumento(s) emitido(s)" in r.get_data(as_text=True)
    assert _afirmacoes(s) == []


def test_emitir_so_este_no_acervo_continua_sem_afirmacao(s):
    velho = _protesto_de_acervo(s)
    tela = _tela(s, "?quais=acervo")
    r = s["c"].post(f"/protesto/{velho}/instrumento",
                    data={"csrf_token": _token(tela)})
    assert r.status_code in (302, 303)
    assert "/odt" in r.headers["Location"]
    assert _emitidos(s) == 1
    assert _afirmacoes(s) == []

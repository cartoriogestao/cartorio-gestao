"""As TELAS da conferência CENPROT × sistema e a trava (29/10/2026).

O QUE ESTES TESTES GUARDAM, E QUE O DE DOMÍNIO NÃO ALCANÇA
      - a tela existe, está no menu, e abre SEM falar com a rede (a Central
        de mentira estoura se for chamada); todo formulário manda o token;
      - a ficha recusa protestar o título que a CENPROT dá por PAGO POR
        LIQUIDAÇÃO — e o ato não nasce; com a afirmação expressa do contrato
        comum ele nasce, e a afirmação fica no ato e na auditoria;
      - o pago por liquidação recusa também a INTIMAÇÃO na ficha;
      - O CASO DO 350574/2: o «pago» que veio do NOSSO D não trava — o lote
        lavra o protesto, e é o P dele que corrige a CENPROT;
      - o lote recusa o pago por liquidação e manda afirmar na ficha, sem
        derrubar o título de banco da mesma leva.

Números de pedido e documentos fictícios. Os títulos saem do ajudante do
«A protestar» (`intimado`, com a prova da intimação juntada) e viram de
origem CENPROT por um UPDATE.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_protesto_a_protestar_web import (MOTIVO, _con, _token, atos,  # noqa: E402,F401
                                           intimado, lavrar, s)

import cenprot_api as API  # noqa: E402
import cenprot_conferencia as C  # noqa: E402

TEXTO = ("conferi o pedido no portal da CENPROT e o dinheiro da liquidação é "
         "de outro título, conforme o comprovante")
CPF_DO_AJUDANTE = "04785512388"


def central(monkeypatch, respostas: dict) -> list:
    chamadas: list = []

    def falsa(ambiente=None, *, numero="", data="", pasta=None):
        chamadas.append(numero)
        r = respostas.get(numero)
        if isinstance(r, Exception):
            raise r
        return [] if r is None else [r]

    monkeypatch.setattr(API, "pedidos_de_protesto", falsa)
    return chamadas


def pedido(numero="9900001", *, status="Apontado / em andamento", codigo="",
           ocorrencia="", numero_titulo="84713/1") -> dict:
    return {"dados_pedido": {"cd_pedido_protesto": int(numero),
                             "ds_status": status, "ocorrencia": ocorrencia,
                             "ds_ocorrencia": codigo, "dt_ocorrencia": "2026-10-27",
                             "dados_titulo": {"nm_nr_titulo": numero_titulo,
                                              "vl_titulo": 1482.78}},
            "devedor": {"nm_devedor": "DEVEDOR FICTICIO",
                        "nm_nr_identificacao": CPF_DO_AJUDANTE},
            "dados_cedente": {"nm_cedente": "CREDOR FICTICIO"}}


def da_cenprot(s, tid, *, pedido_=9900001, protocolo=None) -> int:
    """O título do ajudante vira de origem CENPROT (Gestão de Pedidos)."""
    con = _con(s)
    with con:
        con.execute("""UPDATE pt_titulos SET origem='CENPROT', apresentante_codigo='TAB',
                           origem_chave=?, protocolo=COALESCE(?, protocolo)
                        WHERE id=?""",
                    (f"CENPROT-PEDIDO:{pedido_}", protocolo, tid))
    con.close()
    return tid


def _auditoria(s, tid) -> list:
    con = _con(s)
    linhas = con.execute(
        """SELECT * FROM audit_logs WHERE action='AFIRMACAO_EXPRESSA'
            AND entity_type='pt_titulos' AND entity_id=?""", (tid,)).fetchall()
    con.close()
    return linhas


def _lancar(s, tid, **campos) -> str:
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    return s["c"].post(f"/protesto/{tid}/lancar",
                       data={"csrf_token": _token(html), **campos},
                       follow_redirects=True).get_data(as_text=True)


# ------------------------------------------------------------- a tela


def test_a_tela_abre_sem_falar_com_a_rede_e_esta_no_menu(s, monkeypatch):
    central(monkeypatch, {"9900001": AssertionError("a tela falou com a rede")})
    da_cenprot(s, intimado(s))
    r = s["c"].get("/protesto/cenprot/conferencia")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Conferência CENPROT × sistema" in html          # o item do menu
    assert "a Central ainda não foi consultada" in html
    formularios = re.findall(r"<form[^>]*method=[\"']post[\"'].*?</form>",
                             html, re.DOTALL | re.IGNORECASE)
    assert len(formularios) >= 2, "consultar e registrar a liquidação"
    for f in formularios:
        assert "csrf_token" in f


def test_consultar_pela_tela_mostra_a_divergencia_e_o_caminho(s, monkeypatch):
    tid = da_cenprot(s, intimado(s))
    chamadas = central(monkeypatch, {"9900001": pedido(status="Pago")})
    tela = s["c"].get("/protesto/cenprot/conferencia").get_data(as_text=True)
    html = s["c"].post("/protesto/cenprot/conferencia/consultar",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert chamadas == ["9900001"]
    assert f'id="titulo-{tid}"' in html and "DIVERGE" in html
    assert "PAGO POR LIQUIDAÇÃO" in html and "NÃO PROTESTE" in html


def test_o_numero_que_nao_se_le_nao_derruba_a_tela(s, monkeypatch):
    central(monkeypatch, {})
    tela = s["c"].get("/protesto/cenprot/conferencia").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/conferencia/consultar",
                    data={"csrf_token": _token(tela), "titulo_id": "²"},
                    follow_redirects=True)
    assert r.status_code == 200


# ------------------------------------------------------------- a trava


def test_a_ficha_recusa_protestar_o_pago_por_liquidacao(s, monkeypatch):
    tid = da_cenprot(s, intimado(s))
    central(monkeypatch, {"9900001": pedido(status="Pago")})
    html = _lancar(s, tid, ato="PROTESTO", motivo_atraso=MOTIVO)
    assert "Protesto NÃO lavrado" in html
    assert atos(s, tid) == 0
    # A ficha oferece a afirmação do contrato comum para o título da CENPROT.
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert 'name="afirmo"' in ficha and 'name="afirmacao"' in ficha
    assert "afirmação expressa (CENPROT)" in ficha


def test_com_a_afirmacao_o_texto_vai_ao_ato_e_a_auditoria(s, monkeypatch):
    import protesto_selo_previo as PSELO
    # O SELO PRÉVIO NÃO É O QUE SE TESTA AQUI: sem aparelho na bancada ele
    # recusaria antes de o ato existir.
    monkeypatch.setattr(PSELO, "conferir_antes_de_lavrar", lambda *a, **k: None)
    tid = da_cenprot(s, intimado(s))
    central(monkeypatch, {"9900001": pedido(status="Pago")})
    _lancar(s, tid, ato="PROTESTO", motivo_atraso=MOTIVO, afirmo="1",
            afirmacao=TEXTO)
    [rastro] = _auditoria(s, tid)
    det = json.loads(rastro["details"])
    assert det["regra"] == C.REGRA_PAGO_POR_LIQUIDACAO
    assert TEXTO in det["afirmacao"] and det["o_que_faltava"]
    assert det["ato"] == "PROTESTO"
    con = _con(s)
    [detalhe] = [json.loads(r[0]) for r in con.execute(
        "SELECT detalhe_json FROM pt_atos WHERE titulo_id=? AND tipo='PROTESTO'",
        (tid,)).fetchall()]
    con.close()
    assert TEXTO in detalhe[C.CHAVE_NO_DETALHE][0]["afirmacao"]


def test_o_pago_por_liquidacao_recusa_a_intimacao_na_ficha(s, monkeypatch):
    tid = da_cenprot(s, intimado(s))
    central(monkeypatch, {"9900001": pedido(status="Pago")})
    tela = s["c"].get("/protesto/cenprot/conferencia").get_data(as_text=True)
    s["c"].post("/protesto/cenprot/conferencia/consultar",
                data={"csrf_token": _token(tela)}, follow_redirects=True)
    con = _con(s)
    with con:
        con.execute("UPDATE pt_titulos SET situacao='APONTADO' WHERE id=?", (tid,))
    con.close()
    antes = atos(s, tid, "INTIMACAO")
    html = _lancar(s, tid, ato="INTIMACAO", modo="PESSOAL",
                   comprovante="Recebido pelo próprio devedor")
    assert "Ato NÃO lançado (intimação)" in html
    assert atos(s, tid, "INTIMACAO") == antes


def test_o_pago_do_nosso_d_nao_trava_e_o_lote_protesta(s, monkeypatch):
    """O 350574/2 de 29/10/2026: «1-Pago» na CENPROT pelo D desta casa, com o
    pagamento tornado sem efeito aqui. O protesto TEM de passar — o P dele é
    que corrige a Central."""
    tid = da_cenprot(s, intimado(s), pedido_=9900002)
    con = _con(s)
    with con:
        xml = con.execute(
            """INSERT INTO pt_cenprot_xml(letra, dia, sequencial, nome_arquivo,
                   conteudo, sha256, titulos, gerado_em)
               VALUES ('D','2026-10-21',1,'MA-2199999-01-D-20261021-01.xml',?,?,1,
                       '2026-10-21T13:45:00')""", (b"<x/>", "0" * 64)).lastrowid
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
                   criado_em, cancelado, motivo_cancelamento, cenprot_xml_id)
               VALUES (?,'PAGAMENTO','2026-08-11','{}','MANUAL','2026-08-11T10:00:00',
                       1,'TORNADO SEM EFEITO (teste)',?)""", (tid, xml))
    con.close()
    central(monkeypatch, {"9900002": pedido("9900002", codigo="1",
                                            ocorrencia="Pago")})
    lavrar(s, [tid])
    assert atos(s, tid) == 1


def test_o_lote_recusa_e_manda_afirmar_na_ficha(s, monkeypatch):
    tid = da_cenprot(s, intimado(s))
    banco_tid = intimado(s, numero="555/1")
    con = _con(s)
    with con:   # protocolos distintos: aqui não se testa o protocolo repetido
        con.execute("UPDATE pt_titulos SET protocolo='2608310002' WHERE id=?",
                    (banco_tid,))
    con.close()
    central(monkeypatch, {"9900001": pedido(status="Pago")})
    html = lavrar(s, [tid, banco_tid]).get_data(as_text=True)
    assert "abra a ficha" in html
    assert atos(s, tid) == 0
    # O de banco, na mesma leva, sai como sempre — um não derruba o outro.
    assert atos(s, banco_tid) == 1


def test_o_titulo_de_banco_nao_passa_pela_central(s, monkeypatch):
    tid = intimado(s, numero="555/1")
    chamadas = central(monkeypatch, {})
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "afirmação expressa (CENPROT)" not in ficha
    lavrar(s, [tid])
    assert chamadas == [] and atos(s, tid) == 1

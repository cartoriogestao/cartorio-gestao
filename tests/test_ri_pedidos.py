"""Os pedidos de ato do RI — o painel, a qualificação e a ponte com o protocolo geral.

    «quero ter uma relacao mais clara e acompanhamento dos pedidos de atos, para
     saber melhor o que esta pendente de qualificacao e o que esta pendente de
     registro ou lavratura (...) gostaria de uma integracao melhor com o
     protocolo geral e protocolo do ri» — o oficial, 12/10/2026

As quatro decisões dele: painel próprio; protocolo geral automático ao prenotar;
vencida marcada e decidida por gente; só o RI primeiro.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_pedidos as PED  # noqa: E402

SENHA = "Senha#12345"
HOJE = "2026-10-12"


# ------------------------------------------------------------ a etapa, pura

def _p(**k):
    base = {"situacao": "ABERTO", "ato_id": None, "data_limite": "2026-10-30",
            "prazo_suspenso_desde": None}
    base.update(k)
    return base


def test_sem_qualificacao_e_a_qualificar():
    assert PED.etapa(_p(), None, HOJE) == "A_QUALIFICAR"


def test_positiva_e_apto():
    assert PED.etapa(_p(), {"resultado": "POSITIVA"}, HOJE) == "APTO"


def test_devolvido_e_em_exigencia():
    assert PED.etapa(_p(situacao="DEVOLVIDO"), {"resultado": "NEGATIVA"}, HOJE) == "EM_EXIGENCIA"


def test_negativa_com_prenotacao_aberta_e_reingresso_a_qualificar():
    assert PED.etapa(_p(), {"resultado": "NEGATIVA"}, HOJE) == "A_QUALIFICAR"


def test_prazo_acabado_e_vencida_mesmo_apta():
    assert PED.etapa(_p(data_limite="2026-10-01"), {"resultado": "POSITIVA"}, HOJE) == "VENCIDA"


def test_prazo_suspenso_nao_vence():
    assert PED.etapa(_p(data_limite="2026-10-01", prazo_suspenso_desde="2026-09-20"),
                     None, HOJE) == "A_QUALIFICAR"


def test_ato_lavrado_vem_antes_do_prazo():
    # 11.548 e 11.565 na produção: registradas com a prenotação já vencida.
    assert PED.etapa(_p(ato_id=3745, data_limite="2026-08-25"), None, HOJE) == "REGISTRADO"


def test_mesmo_nome_vira_sugestao_e_nao_ligacao():
    # ELIAS na produção: geral 2026.08.172 sem prenotação, prenotação 11554 sem geral.
    pedidos = [
        {"tipo": "PROTOCOLO_GERAL", "id": 9, "numero": "2026.08.172",
         "apresentante": "Braulio Neiva dos Santos", "geral_id": 9},
        {"tipo": "PRENOTACAO", "id": 3, "numero": 11554,
         "apresentante": "BRAULIO NEIVA DOS SANTOS", "geral_id": None},
        {"tipo": "PRENOTACAO", "id": 4, "numero": 11555,
         "apresentante": "EDUARDO", "geral_id": None},
    ]
    PED._sugerir_pares(pedidos)
    assert pedidos[0]["pares"] == [{"id": 3, "numero": 11554}]
    assert pedidos[1]["pares"] == [{"id": 9, "numero": "2026.08.172"}]
    assert "pares" not in pedidos[2]
    assert pedidos[1]["geral_id"] is None  # sugestão não liga


def test_o_modulo_nao_lavra_nem_encerra():
    publicos = [n for n in dir(PED) if not n.startswith("_")]
    for proibido in ("lavrar", "selar", "cobrar", "encerrar", "numerar"):
        assert not [n for n in publicos if proibido in n.lower()], proibido


# ------------------------------------------------------------------ as telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _um(casa, sql, *a):
    con = _con(casa)
    try:
        return con.execute(sql, a).fetchone()
    finally:
        con.close()


def _prenotar(casa, **extra):
    html = casa["cliente"].get("/registro-imoveis/protocolo").get_data(as_text=True)
    dados = {"apresentante": "MARIA DA SILVA", "natureza_titulo": "COMPRA E VENDA",
             "objeto": "escritura", "livro_destino": "2", "telefone": "(99) 90000-0000",
             "csrf_token": _token(html)}
    dados.update(extra)
    resp = casa["cliente"].post("/registro-imoveis/protocolo", data=dados, follow_redirects=True)
    return resp, _um(casa, "SELECT * FROM ri_protocolos ORDER BY id DESC LIMIT 1")


def _geral_do_ri(casa):
    html = casa["cliente"].get("/caixa/protocolos").get_data(as_text=True)
    casa["cliente"].post("/caixa/protocolos", data={
        "acao": "novo", "interessado": "JOÃO DA SILVA", "atribuicao": "RI",
        "tipo": "SERVICO", "email": "joao@provedor.com", "csrf_token": _token(html)},
        follow_redirects=True)
    return _um(casa, "SELECT * FROM cx_protocolos ORDER BY id DESC LIMIT 1")


def _etapa_no_painel(casa, protocolo_id):
    con = _con(casa)
    try:
        dados = PED.listar(con, hoje=date.today())
    finally:
        con.close()
    return next(x["etapa"] for x in dados["pedidos"]
                if x["tipo"] == "PRENOTACAO" and x["id"] == protocolo_id)


def test_prenotar_abre_o_protocolo_geral_ja_ligado(casa):
    antes = _um(casa, "SELECT COUNT(*) n FROM cx_protocolos")["n"]
    resp, p = _prenotar(casa)
    assert "Protocolo geral" in resp.get_data(as_text=True)
    assert _um(casa, "SELECT COUNT(*) n FROM cx_protocolos")["n"] == antes + 1
    g = _um(casa, "SELECT * FROM cx_protocolos WHERE ri_protocolo_id=?", p["id"])
    assert g is not None and g["atribuicao"] == "RI"
    assert g["telefone"] == "(99) 90000-0000"


def test_prenotar_a_partir_do_geral_liga_e_nao_abre_outro(casa):
    g = _geral_do_ri(casa)
    tela = casa["cliente"].get(f"/registro-imoveis/protocolo?cx={g['id']}").get_data(as_text=True)
    assert f"protocolo geral {g['numero']}" in tela
    assert 'value="JOÃO DA SILVA"' in tela
    antes = _um(casa, "SELECT COUNT(*) n FROM cx_protocolos")["n"]
    _, p = _prenotar(casa, cx_protocolo_id=str(g["id"]))
    assert _um(casa, "SELECT COUNT(*) n FROM cx_protocolos")["n"] == antes
    assert _um(casa, "SELECT ri_protocolo_id FROM cx_protocolos WHERE id=?",
               g["id"])["ri_protocolo_id"] == p["id"]


def test_geral_que_ja_tem_prenotacao_e_recusado_e_nada_se_prenota(casa):
    _, p = _prenotar(casa)
    g = _um(casa, "SELECT id FROM cx_protocolos WHERE ri_protocolo_id=?", p["id"])
    antes = _um(casa, "SELECT COUNT(*) n FROM ri_protocolos")["n"]
    resp, _ = _prenotar(casa, cx_protocolo_id=str(g["id"]))
    assert "já tem prenotação" in resp.get_data(as_text=True)
    assert _um(casa, "SELECT COUNT(*) n FROM ri_protocolos")["n"] == antes


def test_o_geral_do_balcao_oferece_prenotar(casa):
    g = _geral_do_ri(casa)
    html = casa["cliente"].get(f"/caixa/protocolos/{g['id']}").get_data(as_text=True)
    assert "Prenotar este título" in html


def test_painel_abre_e_mostra_as_etapas(casa):
    _, p = _prenotar(casa)
    _geral_do_ri(casa)
    html = casa["cliente"].get("/registro-imoveis/pedidos").get_data(as_text=True)
    assert "A qualificar" in html and "No balcão, sem prenotação" in html
    assert str(p["numero"]) in html
    assert _etapa_no_painel(casa, p["id"]) == "A_QUALIFICAR"


def test_qualificacao_positiva_poe_o_titulo_apto(casa):
    _, p = _prenotar(casa)
    ficha = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}").get_data(as_text=True)
    assert "Qualificação positiva — apto para registro" in ficha
    casa["cliente"].post(f"/registro-imoveis/protocolo/{p['id']}/qualificar",
                         data={"fundamentacao": "título em ordem",
                               "csrf_token": _token(ficha)}, follow_redirects=True)
    q = _um(casa, "SELECT * FROM ri_qualificacoes WHERE protocolo_id=?", p["id"])
    assert q["resultado"] == "POSITIVA" and q["ordem"] == 1
    assert q["qualificada_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert _etapa_no_painel(casa, p["id"]) == "APTO"


def test_nota_devolutiva_grava_a_negativa_e_poe_em_exigencia(casa):
    _, p = _prenotar(casa)
    tela = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}/nota").get_data(as_text=True)
    casa["cliente"].post(f"/registro-imoveis/protocolo/{p['id']}/nota",
                         data={"exigencias": "Apresentar a guia do ITBI quitada",
                               "csrf_token": _token(tela)})
    q = _um(casa, "SELECT * FROM ri_qualificacoes WHERE protocolo_id=?", p["id"])
    nota = _um(casa, "SELECT id FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert q["resultado"] == "NEGATIVA" and q["nota_id"] == nota["id"]
    assert _etapa_no_painel(casa, p["id"]) == "EM_EXIGENCIA"
    # Em exigência não se qualifica positivo por cima da nota aberta.
    con = _con(casa)
    try:
        with pytest.raises(PED.PedidoError, match="reingresso"):
            PED.qualificar_positiva(con, p["id"], fundamentacao=None, quem="X",
                                    usuario_id=None, agora=f"{HOJE}T10:00:00")
    finally:
        con.close()


def test_vencida_aparece_e_nao_se_qualifica(casa):
    _, p = _prenotar(casa)
    con = _con(casa)
    try:
        con.execute("UPDATE ri_protocolos SET data_limite='2026-01-05' WHERE id=?", (p["id"],))
        con.commit()
        with pytest.raises(PED.PedidoError, match="venceu"):
            PED.qualificar_positiva(con, p["id"], fundamentacao=None, quem="X",
                                    usuario_id=None, agora=f"{HOJE}T10:00:00")
    finally:
        con.close()
    assert _etapa_no_painel(casa, p["id"]) == "VENCIDA"


def test_decidir_a_vencida_volta_ao_painel(casa):
    _, p = _prenotar(casa)
    html = casa["cliente"].get("/registro-imoveis/pedidos").get_data(as_text=True)
    resp = casa["cliente"].post("/registro-imoveis/protocolo", data={
        "acao": "encerrar", "protocolo_id": str(p["id"]), "situacao": "CANCELADO",
        "motivo": "Decurso do prazo da prenotação sem registro.", "voltar": "pedidos",
        "csrf_token": _token(html)})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/registro-imoveis/pedidos")
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=?", p["id"])["situacao"] == "CANCELADO"


def test_anotar_quem_cuida_volta_ao_painel(casa):
    _, p = _prenotar(casa)
    tela = casa["cliente"].get(
        f"/inacabados/anotar/ri_protocolos/{p['id']}?voltar=ri_pedidos").get_data(as_text=True)
    assert 'name="voltar" value="ri_pedidos"' in tela
    resp = casa["cliente"].post(f"/inacabados/anotar/ri_protocolos/{p['id']}", data={
        "texto": "Conferir a guia do ITBI", "responsavel": "BEATRIZ",
        "voltar": "ri_pedidos", "csrf_token": _token(tela)})
    assert resp.headers["Location"].endswith("/registro-imoveis/pedidos")
    html = casa["cliente"].get("/registro-imoveis/pedidos").get_data(as_text=True)
    assert "Conferir a guia do ITBI" in html and "BEATRIZ" in html

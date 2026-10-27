# -*- coding: utf-8 -*-
"""O painel do devedor (LG06): os títulos juntos por CPF/CNPJ, com prazos,
intimações, pagamentos e os alertas — e sem o CPF no endereço da tela."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import apoio_protesto_lg06 as APOIO  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_ar as AR  # noqa: E402
import protesto_aviso as AV  # noqa: E402
import protesto_devedor as DEV  # noqa: E402
from bd_nativo import banco  # noqa: E402
from conftest import cg_login  # noqa: E402

SENHA = "Senha#12345"
OUTRO_CPF = "00000000272"


@pytest.fixture()
def db(cg_casa):
    return cg_casa["db"]


def _codigos(alertas):
    return [a["codigo"] for a in alertas]


# ------------------------------------------------------- a régua pura


def test_vence_hoje_e_prazo_vencido_sao_contagem_do_prazo_limite():
    t = {"situacao": "APONTADO"}
    base = dict(postagens_sem_retorno=[], avisos_para_edital=[],
                boletos_a_conferir=[], sustado=False)
    assert _codigos(DEV.alertas_do_titulo(t, hoje="2026-10-22",
                                          prazo="2026-10-22", **base)) == ["VENCE_HOJE"]
    assert _codigos(DEV.alertas_do_titulo(t, hoje="2026-10-23",
                                          prazo="2026-10-22", **base)) == ["PRAZO_VENCIDO"]
    assert DEV.alertas_do_titulo(t, hoje="2026-10-21", prazo="2026-10-22", **base) == []


def test_vence_hoje_diz_que_o_protesto_e_no_dia_util_seguinte():
    """Decisão do oficial em 27/10/2026: «no dia útil seguinte». A frase dizia
    «amanhã o protesto pode ser lavrado» — e amanhã pode ser sábado, e a régua
    do tríduo tratava o protesto do dia útil seguinte como atrasado."""
    frase = DEV.ALERTAS["VENCE_HOJE"]["frase"]
    assert "amanhã" not in frase
    assert "dia útil seguinte" in frase
    base = dict(postagens_sem_retorno=[], avisos_para_edital=[],
                boletos_a_conferir=[], sustado=False)
    # Sexta 23/10/2026: o protesto é na segunda 26/10, e o detalhe diz o dia.
    [a] = DEV.alertas_do_titulo(
        {"situacao": "INTIMADO", "protesto_a_partir_de": "2026-10-26"},
        hoje="2026-10-23", prazo="2026-10-23", **base)
    assert a["codigo"] == "VENCE_HOJE"
    assert "protesto a partir de 26/10/2026" in a["detalhe"]


def test_sustado_e_titulo_encerrado_nao_vencem():
    base = dict(postagens_sem_retorno=[{"codigo_objeto": "X"}],
                avisos_para_edital=[], boletos_a_conferir=[])
    assert DEV.alertas_do_titulo({"situacao": "APONTADO"}, hoje="2026-10-22",
                                 prazo="2026-10-22", sustado=True, **base) == []
    assert DEV.alertas_do_titulo({"situacao": "PAGO"}, hoje="2026-10-22",
                                 prazo="2026-10-22", sustado=False, **base) == []


def test_os_alertas_saem_na_ordem_da_urgencia():
    alertas = DEV.alertas_do_titulo(
        {"situacao": "APONTADO"}, hoje="2026-10-23", prazo="2026-10-22",
        sustado=False, postagens_sem_retorno=[{"codigo_objeto": "ZZ1"}],
        avisos_para_edital=[{"numero": 1, "ano": 2026}],
        boletos_a_conferir=[{"nosso_numero": "1"}])
    assert _codigos(alertas) == ["AR_NAO_VOLTOU", "EDITAL_NECESSARIO",
                                 "PAGAMENTO_A_CONFERIR", "PRAZO_VENCIDO"]


# ------------------------------------------------------------- o banco


def test_o_painel_junta_por_cpf_mesmo_pontuado_e_nao_por_nome(db):
    a = APOIO.titulo_apontado(db, numero="A1")
    b = APOIO.titulo_apontado(db, numero="A2")
    homonimo = APOIO.titulo_apontado(db, numero="A3", cpf=OUTRO_CPF)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_devedores SET documento_numero=%s "
                            "WHERE titulo_id=%s", ("000.000.001-91", b))
    with db.connect() as con:
        devedor_id = DEV.achar(con, "000.000.001-91")
        p = DEV.painel(con, devedor_id, hoje="2026-10-19")
        lista = DEV.devedores_em_andamento(con, hoje="2026-10-19")
    assert sorted(t["id"] for t in p["titulos"]) == [a, b]
    assert homonimo not in [t["id"] for t in p["titulos"]]
    assert p["documento_formatado"] == "000.000.001-91"
    grupo = next(g for g in lista["devedores"] if g["documento"] == APOIO.CPF)
    assert grupo["n_titulos"] == 2 and grupo["valor_centavos"] == 2 * 131045
    assert len([g for g in lista["devedores"]
                if g["nome"] == "FULANO DE TAL EXEMPLO"]) == 2


def test_devedor_sem_documento_fica_sozinho(db):
    tid = APOIO.titulo_apontado(db, numero="S1")
    APOIO.titulo_apontado(db, numero="S2")
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_devedores SET documento_numero=NULL "
                            "WHERE titulo_id=%s", (tid,))
    dev = APOIO.um(db, "SELECT id FROM pt_devedores WHERE titulo_id=%s", (tid,))
    with db.connect() as con:
        p = DEV.painel(con, dev["id"], hoje="2026-10-19")
        lista = DEV.devedores_em_andamento(con, hoje="2026-10-19")
    assert p["sem_documento"] and [t["id"] for t in p["titulos"]] == [tid]
    assert lista["titulos_sem_documento"] == 1


def test_o_painel_mostra_prazo_intimacao_pagamento_e_o_alerta_do_dia(db):
    tid = APOIO.titulo_apontado(db, numero="P1")
    pago = APOIO.titulo_apontado(db, numero="P2")
    limite = APOIO.prazo(db, tid)
    with db.transaction() as con:
        PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=db.now(),
                            comprovante="entregue em mãos")
        PT.lancar_pagamento(con, pago, sv=APOIO.SV, agora=db.now(),
                            data_extenso="vinte de outubro",
                            valor_pago="1310.45", forma_pagamento="PIX")
    with db.connect() as con:
        p = DEV.painel(con, DEV.achar(con, APOIO.CPF), hoje=limite)
    primeiro, segundo = p["titulos"]
    assert primeiro["id"] == tid                      # em andamento primeiro
    assert primeiro["prazo_limite"] == limite and primeiro["dias_para_o_prazo"] == 0
    assert _codigos(primeiro["alertas"]) == ["VENCE_HOJE"]
    # O DIA DO PROTESTO (27/10/2026): o dia útil seguinte ao prazo-limite.
    with db.connect() as con:
        seguinte = AV.dia_util_seguinte(con, limite)
    assert seguinte > limite
    assert primeiro["protesto_a_partir_de"] == seguinte
    assert f"protesto a partir de {DEV._br(seguinte)}" in \
        primeiro["alertas"][0]["detalhe"]
    assert primeiro["intimacoes"][0]["modo"] == "PESSOAL"
    assert segundo["situacao"] == "PAGO"
    assert segundo["pagamentos"][0]["forma"] == "por PIX"
    assert segundo["pagamentos"][0]["valor_centavos"] == 131045
    assert p["resumo"]["em_andamento"] == 1


def test_ar_que_nao_voltou_aparece_no_painel(db, tmp_path):
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    AR.solicitar_postagem(db, aviso, transporte=APOIO.CorreiosDeTeste(pasta=tmp_path),
                          cfg=APOIO.PRODUCAO)
    limite = APOIO.prazo(db, tid)
    with db.connect() as con:
        p = DEV.painel(con, DEV.achar(con, APOIO.CPF), hoje=limite)
    assert "AR_NAO_VOLTOU" in _codigos(p["titulos"][0]["alertas"])


def test_aviso_nao_entregue_sem_resolve_possivel_pede_edital(db):
    # sem a chave do CENPROT a Intimação Digital não serve: o caminho é o edital
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    with db.transaction() as con:
        AV.registrar_entrega(con, aviso, entregue=False, agora=db.now(), motivo=11)
    with db.connect() as con:
        p = DEV.painel(con, DEV.achar(con, APOIO.CPF), hoje="2026-10-19")
    assert _codigos(p["titulos"][0]["alertas"]) == ["EDITAL_NECESSARIO"]


def test_aviso_nao_entregue_com_resolve_por_tentar_nao_e_edital_ainda(db):
    tid = APOIO.titulo_apontado(db, chave="1" * 23)
    aviso = APOIO.aviso_emitido(db, tid)
    with db.transaction() as con:
        AV.registrar_entrega(con, aviso, entregue=False, agora=db.now(), motivo=11)
    with db.connect() as con:
        p = DEV.painel(con, DEV.achar(con, APOIO.CPF), hoje="2026-10-19")
    assert "EDITAL_NECESSARIO" not in _codigos(p["titulos"][0]["alertas"])


def test_cpf_curto_nao_acha_ninguem(db):
    APOIO.titulo_apontado(db)
    with db.connect() as con:
        assert DEV.achar(con, "000000001") is None


# --------------------------------------------------------------- a tela


@pytest.fixture()
def cliente(cg_casa):
    cg_casa["db"].create_user("balcao", "ESCREVENTE EXEMPLO", SENHA, "USER")
    cg_casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    c = cg_casa["app"].test_client()
    cg_login(c, "balcao", SENHA)
    return c


def _token(c, url="/protesto/devedores"):
    import re
    html = c.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_a_busca_abre_o_painel_sem_o_cpf_no_endereco_nem_no_rastro(db, cliente):
    APOIO.titulo_apontado(db)
    r = cliente.post("/protesto/devedores/buscar",
                     data={"documento": "000.000.001-91",
                           "csrf_token": _token(cliente)})
    assert r.status_code == 302
    destino = r.headers["Location"]
    assert "/protesto/devedores/" in destino and APOIO.CPF not in destino
    html = cliente.get(destino).get_data(as_text=True)
    assert "FULANO DE TAL EXEMPLO" in html and "000.000.001-91" in html
    rastro = APOIO.ler(db, "SELECT action, details FROM audit_logs WHERE action "
                           "LIKE 'PROTESTO_DEVEDOR%%' ORDER BY id")
    assert [x["action"] for x in rastro] == ["PROTESTO_DEVEDOR_BUSCA",
                                             "PROTESTO_DEVEDOR_CONSULTA"]
    assert all(APOIO.CPF not in str(x["details"]) and "000.000.001" not in
               str(x["details"]) for x in rastro)


def test_a_lista_abre_e_o_devedor_que_nao_existe_e_404(db, cliente):
    APOIO.titulo_apontado(db)
    html = cliente.get("/protesto/devedores").get_data(as_text=True)
    assert "FULANO DE TAL EXEMPLO" in html
    assert cliente.get("/protesto/devedores/999999").status_code == 404

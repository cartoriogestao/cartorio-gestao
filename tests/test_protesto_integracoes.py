# -*- coding: utf-8 -*-
"""O interruptor do AR e do boleto (LG06): desligado de fábrica, homologação
só com o serviço falso e sem rede, produção só com transporte do contrato, e
a credencial fora do banco, da tela e do rastro."""
from __future__ import annotations

import re
import socket
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import apoio_protesto_lg06 as APOIO  # noqa: E402
import centrais_cred as CRED  # noqa: E402
import protesto_ar as AR  # noqa: E402
import protesto_boleto as BOL  # noqa: E402
import protesto_integracoes as INTEG  # noqa: E402
from conftest import cg_login  # noqa: E402

SENHA = "Senha#12345"
SEGREDO = "codigo-de-acesso-de-mentira-7Q"


@pytest.fixture()
def casa(cg_casa, tmp_path, monkeypatch):
    # AS CREDENCIAIS E O SIMULADOR NUMA PASTA DO TESTE — nunca a da máquina.
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    cg_casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    return {**cg_casa, "pasta": tmp_path}


def _entrar(casa, papel="ADMIN"):
    usuario = f"u_{papel.lower()}"
    casa["db"].create_user(usuario, f"{papel} EXEMPLO", SENHA, papel)
    c = casa["app"].test_client()
    cg_login(c, usuario, SENHA)
    return c


def _token(c, url):
    html = c.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


# ---------------------------------------------------------- a régua


def test_instalacao_nova_tem_as_duas_desligadas(casa):
    with casa["db"].connect() as con:
        for qual in (INTEG.AR, INTEG.BOLETO):
            assert INTEG.configuracao(con, qual)["modo"] == INTEG.DESLIGADO


def test_palavra_desconhecida_na_chave_vira_desligado(casa):
    casa["db"].set_settings({"protesto_ar_modo": "LIGADISSIMO"})
    with casa["db"].connect() as con:
        assert INTEG.configuracao(con, INTEG.AR)["modo"] == INTEG.DESLIGADO


def test_producao_recusa_o_servico_falso_e_o_provedor_sem_contrato():
    with pytest.raises(INTEG.IntegracaoError) as e:
        INTEG.conferir_escolha(INTEG.AR, "PRODUCAO", "FALSO")
    assert "não vale em produção" in str(e.value)
    with pytest.raises(INTEG.IntegracaoError) as e:
        INTEG.conferir_escolha(INTEG.AR, "PRODUCAO", "CORREIOS")
    assert "contrato" in str(e.value)
    with pytest.raises(INTEG.IntegracaoError):
        INTEG.conferir_escolha(INTEG.BOLETO, "PRODUCAO", "BANCO")
    assert INTEG.conferir_escolha(INTEG.BOLETO, "HOMOLOGACAO", "") == (
        "HOMOLOGACAO", "FALSO")


def test_a_chave_mexida_a_mao_para_producao_falsa_nao_liga(casa):
    casa["db"].set_settings({"protesto_boleto_modo": "PRODUCAO",
                             "protesto_boleto_provedor": "FALSO"})
    with casa["db"].connect() as con:
        with pytest.raises(INTEG.IntegracaoError):
            INTEG.transporte_em_uso(con, INTEG.BOLETO)


# -------------------------------------------- homologação, sem rede


@pytest.fixture()
def sem_rede(monkeypatch):
    def recusa(*a, **k):
        raise AssertionError("o serviço falso tentou abrir conexão de rede")
    monkeypatch.setattr(socket.socket, "connect", recusa)
    monkeypatch.setattr(socket, "create_connection", recusa)


def test_o_caminho_inteiro_da_homologacao_roda_sem_rede(casa, sem_rede, monkeypatch):
    db = casa["db"]
    relogio = APOIO.Relogio(db, monkeypatch, "2026-10-19")
    db.set_settings({"protesto_ar_modo": "HOMOLOGACAO",
                     "protesto_boleto_modo": "HOMOLOGACAO"})
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    r = AR.solicitar_postagem(db, aviso, quem="escrevente")
    AR.simular_retorno(db, r["postagem_id"], entregue=True, data="2026-10-20")
    voltou = AR.buscar_retornos(db, pasta_de_arquivos=casa["pasta"] / "arq")
    assert voltou["voltaram"][0]["situacao"] == AR.ENTREGUE

    b = BOL.emitir(db, tid, emolumentos="10,00", hoje="2026-10-19")
    BOL.simular_pagamento(db, b["boleto_id"], pago_em="2026-10-20")
    relogio.ir_para("2026-10-21")
    pagos = BOL.buscar_pagamentos(db, sv=APOIO.SV, data_extenso="vinte",
                                  hoje="2026-10-21")
    assert pagos["baixadas"][0]["situacao"] == BOL.ENSAIO
    # NADA VALEU NO LIVRO
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s",
                    (tid,))["situacao"] == "APONTADO"
    # o simulador guardou o estado ao lado das credenciais, fora do banco
    assert (casa["pasta"] / "simuladores" / "simulador_correios.json").is_file()


# ----------------------------------------------------- a tela do Gestor


def test_o_gestor_mostra_que_a_credencial_existe_e_nunca_qual_e(casa):
    CRED.gravar(CRED.CORREIOS, usuario="contrato-exemplo", senha=SEGREDO,
                ambiente=CRED.HOMOLOGACAO)
    c = _entrar(casa)
    html = c.get("/administrativo/gestor/protesto-integracoes").get_data(as_text=True)
    assert "homologação informada" in html
    assert SEGREDO not in html and "contrato-exemplo" not in html
    # e o arquivo mora fora do banco
    assert (casa["pasta"] / "correios.cred").is_file()


def test_ligar_a_homologacao_fica_no_rastro_sem_segredo(casa):
    CRED.gravar(CRED.BANCO_BOLETO, usuario="cliente-exemplo", senha=SEGREDO,
                ambiente=CRED.HOMOLOGACAO)
    c = _entrar(casa)
    url = "/administrativo/gestor/protesto-integracoes"
    r = c.post(url + "/salvar", data={"csrf_token": _token(c, url),
                                      "integracao": "BOLETO",
                                      "modo": "HOMOLOGACAO", "provedor": "FALSO",
                                      "tarifa": "3,50"}, follow_redirects=True)
    assert r.status_code == 200
    with casa["db"].connect() as con:
        cfg = INTEG.configuracao(con, INTEG.BOLETO)
    assert cfg["modo"] == "HOMOLOGACAO" and cfg["tarifa_centavos"] == 350
    rastro = APOIO.ler(casa["db"], "SELECT details FROM audit_logs WHERE action="
                                   "'PROTESTO_INTEGRACAO_CONFIG' ORDER BY id")
    assert len(rastro) == 1 and "HOMOLOGACAO" in rastro[0]["details"]
    todo = " ".join(str(x["details"]) for x in APOIO.ler(
        casa["db"], "SELECT details FROM audit_logs ORDER BY id"))
    assert SEGREDO not in todo and "cliente-exemplo" not in todo


def test_a_tela_nao_grava_producao_sem_contrato(casa):
    c = _entrar(casa)
    url = "/administrativo/gestor/protesto-integracoes"
    html = c.post(url + "/salvar", data={"csrf_token": _token(c, url),
                                         "integracao": "AR", "modo": "PRODUCAO",
                                         "provedor": "CORREIOS"},
                  follow_redirects=True).get_data(as_text=True)
    assert "contrato" in html
    with casa["db"].connect() as con:
        assert INTEG.configuracao(con, INTEG.AR)["modo"] == INTEG.DESLIGADO


def test_so_o_admin_mexe_no_interruptor(casa):
    c = _entrar(casa, "MANAGER")
    assert c.get("/administrativo/gestor/protesto-integracoes").status_code == 403


# ------------------------------------------------- as telas do balcão


@pytest.mark.parametrize("url", ["/protesto/ar", "/protesto/boletos",
                                 "/protesto/devedores"])
def test_as_telas_abrem_e_dizem_que_esta_desligado(casa, url):
    APOIO.titulo_apontado(casa["db"])
    c = _entrar(casa, "USER")
    r = c.get(url)
    assert r.status_code == 200
    if url != "/protesto/devedores":
        assert "DESLIGADA" in r.get_data(as_text=True)


def test_postar_com_a_integracao_desligada_volta_com_a_frase(casa):
    db = casa["db"]
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db))
    c = _entrar(casa)
    html = c.post(f"/protesto/ar/{aviso}/postar",
                  data={"csrf_token": _token(c, "/protesto/ar")},
                  follow_redirects=True).get_data(as_text=True)
    assert "DESLIGADA" in html
    assert APOIO.ler(db, "SELECT id FROM pt_ar_postagens ORDER BY id") == []


def test_o_balcao_nao_posta_nem_emite_boleto(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    c = _entrar(casa, "USER")
    token = _token(c, "/protesto/ar")
    assert c.post(f"/protesto/ar/{aviso}/postar",
                  data={"csrf_token": token}).status_code == 403
    assert c.post(f"/protesto/boletos/{tid}/emitir",
                  data={"csrf_token": token, "emolumentos": "1"}).status_code == 403


def test_a_homologacao_pela_tela_posta_simula_e_assenta(casa):
    db = casa["db"]
    db.set_settings({"protesto_ar_modo": "HOMOLOGACAO"})
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db))
    c = _entrar(casa)
    t = _token(c, "/protesto/ar")
    html = c.post(f"/protesto/ar/{aviso}/postar", data={"csrf_token": t},
                  follow_redirects=True).get_data(as_text=True)
    assert "HOMOLOGAÇÃO" in html
    p = APOIO.um(db, "SELECT * FROM pt_ar_postagens")
    c.post(f"/protesto/ar/{p['id']}/simular",
           data={"csrf_token": t, "entregue": "0", "motivo": "AUSENTE",
                 "data": "2026-10-21"})
    html = c.post("/protesto/ar/retornos", data={"csrf_token": t},
                  follow_redirects=True).get_data(as_text=True)
    assert "1 voltaram" in html
    p = APOIO.um(db, "SELECT * FROM pt_ar_postagens")
    assert p["situacao"] == AR.NAO_ENTREGUE and p["motivo"] == 11
    assert APOIO.um(db, "SELECT situacao FROM pt_avisos WHERE id=%s",
                    (aviso,))["situacao"] == "EMITIDO"
    acoes = [x["action"] for x in APOIO.ler(
        db, "SELECT action FROM audit_logs WHERE action LIKE 'PROTESTO_AR%%' "
            "ORDER BY id")]
    assert acoes == ["PROTESTO_AR_POSTAGEM", "PROTESTO_AR_SIMULADO",
                     "PROTESTO_AR_RETORNOS"]


def test_o_boleto_pela_tela_emite_e_mostra_que_nao_se_paga(casa, monkeypatch):
    db = casa["db"]
    APOIO.Relogio(db, monkeypatch, "2026-10-19")   # o prazo-limite do protocolo 261019
    db.set_settings({"protesto_boleto_modo": "HOMOLOGACAO"})
    tid = APOIO.titulo_apontado(db)
    c = _entrar(casa, "MANAGER")
    t = _token(c, "/protesto/boletos")
    html = c.post(f"/protesto/boletos/{tid}/emitir",
                  data={"csrf_token": t, "emolumentos": "12,30"},
                  follow_redirects=True).get_data(as_text=True)
    assert "HOMOLOGACAO NAO PAGAR" in html
    assert APOIO.um(db, "SELECT emolumentos_centavos FROM pt_boletos")[
        "emolumentos_centavos"] == 1230

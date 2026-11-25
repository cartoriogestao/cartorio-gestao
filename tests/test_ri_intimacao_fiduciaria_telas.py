"""AS TELAS DA INTIMAÇÃO FIDUCIÁRIA (RI013-I1, 24/11/2026).

O painel, a autuação (à mão e pelo pedido da Central colado), a ficha, as peças com a tarja de
sem selo, a configuração do titular e o atalho na ficha da prenotação. Dados fictícios.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ri_intimacao_fiduciaria as INT  # noqa: E402
from test_ri_intimacao_fiduciaria import PEDIDO, _matricula, _prenotacao  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario):
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))}, follow_redirects=True)
    return c


def _base(casa):
    db = casa["db"]
    with db.transaction() as con:
        mid = _matricula(con)
        pid = _prenotacao(con, mid)
    return db, pid


def _autuar_pela_tela(c, pid):
    html = c.get(f"/registro-imoveis/intimacoes/nova?protocolo_id={pid}").get_data(as_text=True)
    assert f'value="{pid}" selected' in html
    r = c.post("/registro-imoveis/intimacoes/nova", data={
        "csrf_token": _token(html), "protocolo_id": pid, "origem": "BALCAO", "credor_nome": "BANCO EXEMPLO S.A.",
        "contrato": "CT-1", "demonstrativo_valor": "3.000,00", "projecao": "31/12/2026; 3.500,00"})
    assert r.status_code == 302
    return int(r.headers["Location"].rstrip("/").split("/")[-1])


def test_o_painel_abre_e_mostra_selo_e_configuracao(cg_casa_logada):
    html = cg_casa_logada["c"].get("/registro-imoveis/intimacoes").get_data(as_text=True)
    assert "Intimação fiduciária" in html and "16.23" in html and "Meio padrão" in html
    assert "Nada é enviado à Central" in html


def test_autuar_pela_tela_suspende_e_a_ficha_da_prenotacao_aponta_o_procedimento(cg_casa_logada):
    c = cg_casa_logada["c"]
    db, pid = _base(cg_casa_logada)
    iid = _autuar_pela_tela(c, pid)
    ficha = c.get(f"/registro-imoveis/intimacoes/{iid}").get_data(as_text=True)
    assert "Intimação fiduciária n. 1/2026" in ficha and "suspensa e não vence" in ficha
    prenot = c.get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "Requerimento de intimação fiduciária n. 1/2026" in prenot
    assert "Retomar a contagem" not in prenot
    assert 'value="INTIMACAO_FIDUCIARIA"' not in prenot


def test_a_ficha_lanca_intimando_e_qualificacao_e_o_balcao_nao_qualifica(cg_casa_logada):
    c = cg_casa_logada["c"]
    db, pid = _base(cg_casa_logada)
    iid = _autuar_pela_tela(c, pid)
    rota = f"/registro-imoveis/intimacoes/{iid}/acao"
    tok = _token(c.get(f"/registro-imoveis/intimacoes/{iid}").get_data(as_text=True))
    c.post(rota, data={"csrf_token": tok, "acao": "intimando", "nome": "Maria Exemplo", "papel": "DEVEDOR",
                       "documento": "11122233344", "enderecos": "Rua Indicada, 10"})
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    balcao = _entrar(cg_casa_logada["app"], "balcao")
    tok_b = _token(balcao.get(f"/registro-imoveis/intimacoes/{iid}").get_data(as_text=True))
    balcao.post(rota, data={"csrf_token": tok_b, "acao": "qualificar", "resultado": "POSITIVA",
                            "itens": [r["chave"] for r in INT.REQUISITOS]})
    with db.connect() as con:
        assert INT.um(con, iid)["situacao"] == INT.AUTUADO
    c.post(rota, data={"csrf_token": tok, "acao": "qualificar", "resultado": "POSITIVA", "dia": "2026-11-24",
                       "itens": [r["chave"] for r in INT.REQUISITOS if r["chave"] != "pj"]})
    with db.connect() as con:
        i = INT.um(con, iid)
        lista = INT.intimandos_de(con, iid)
    assert i["situacao"] == INT.INTIMANDO and len(lista[0]["enderecos"]) == 3
    ficha = c.get(f"/registro-imoveis/intimacoes/{iid}").get_data(as_text=True)
    assert "Lançar uma tentativa" in ficha and "Domicílio do contrato" in ficha
    peca = c.get(f"/registro-imoveis/intimacoes/{iid}/peca/INTIMACAO?intimando={lista[0]['id']}").get_data(as_text=True)
    assert INT.AVISO_SEM_SELO in peca and "Maria Exemplo" in peca and "leilão" in peca


def test_a_configuracao_e_do_titular(cg_casa_logada):
    c = cg_casa_logada["c"]
    tok = _token(c.get("/registro-imoveis/intimacoes").get_data(as_text=True))
    c.post("/registro-imoveis/intimacoes/configuracao", data={
        "csrf_token": tok, "ri_intimacao_meio_padrao": "CORREIO", "ri_intimacao_purga_contagem": "CORRIDOS",
        "ri_intimacao_repasse": "RETIRADA", "ri_intimacao_conta_purga": "Banco Exemplo, ag. 0001, c/c 123-4"})
    db = cg_casa_logada["db"]
    assert db.get_setting("ri_intimacao_meio_padrao", "") == "CORREIO"
    db.create_user("gerente", "QUEM GERENCIA", SENHA, "MANAGER")
    g = _entrar(cg_casa_logada["app"], "gerente")
    tok_g = _token(g.get("/registro-imoveis/intimacoes").get_data(as_text=True))
    r = g.post("/registro-imoveis/intimacoes/configuracao", data={"csrf_token": tok_g, "ri_intimacao_meio_padrao": "RTD"})
    assert r.status_code in (302, 403) and db.get_setting("ri_intimacao_meio_padrao", "") == "CORREIO"


def test_o_pedido_da_central_colado_autua_com_os_devedores(cg_casa_logada):
    c = cg_casa_logada["c"]
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        _matricula(con)
        from bd_nativo import banco
        pid = int(banco(con).escrever(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, data_limite, situacao, criado_em)
               VALUES (15001,'1A','2026-11-24','2026-12-15','ABERTO','2026-11-24T10:00') RETURNING id""")[0]["id"])
    html = c.get("/registro-imoveis/intimacoes/nova").get_data(as_text=True)
    r = c.post("/registro-imoveis/intimacoes/nova", data={"csrf_token": _token(html), "protocolo_id": pid,
                                                          "pedido_central": json.dumps(PEDIDO)})
    assert r.status_code == 302 and "/registro-imoveis/intimacoes/" in r.headers["Location"]
    with db.connect() as con:
        i = INT.do_protocolo(con, pid)
        assert i["origem"] == INT.CENTRAL_ONR and len(INT.intimandos_de(con, i["id"])) == 3


def test_peca_que_nao_cabe_volta_a_ficha(cg_casa_logada):
    c = cg_casa_logada["c"]
    db, pid = _base(cg_casa_logada)
    iid = _autuar_pela_tela(c, pid)
    r = c.get(f"/registro-imoveis/intimacoes/{iid}/peca/CERTIDAO_PURGACAO")
    assert r.status_code == 302

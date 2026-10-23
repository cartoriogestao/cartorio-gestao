"""Livro 3 — quantas partes forem precisas, e parte em registro já lavrado.

    «no registro do 3-aux, preciso que coloque a opção de adicionar mais
     partes no ato»                         — o oficial, 19/10/2026

O QUE ESTES TESTES GUARDAM:

  1. o registro novo aceita **três ou mais** partes (eram duas linhas fixas);
  2. o papel entra como código do catálogo (`GARANTIDOR`, `AVALISTA`…), e
     papel fora dele é recusado sem lavrar nada;
  3. no registro **já lavrado e selado**, parte se acrescenta, se corrige e se
     retira, com auditoria — e o teor e o selo do ato não mudam.

O SQL daqui é o do PostgreSQL nativo (`bd_nativo`), como o dos módulos: o
hotfix do servidor (SANDBOX-2026-10-19-01) foi escrito contra o SQLite.
"""
from __future__ import annotations

import json
import re
from tempfile import TemporaryDirectory

import ra_parte as PT
from app import create_app
from bd_nativo import banco

SENHA = "Senha#12345"


def _csrf(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _casa(td):
    app = create_app({"TESTING": True, "DATA_DIR": td})
    app.extensions["backup_checked"] = True
    app.extensions["cnib_verificado"] = True
    chamadas = []
    # NADA DE SELO: o selador é trocado por um que só anota a chamada.
    app.extensions["selar_o_ato_do_livro3"] = lambda **kw: (
        chamadas.append(kw) or {"recado": " (selo de teste)", "selado": True})
    db = app.extensions["db"]
    db.create_user("admin", "Administrador", SENHA, "ADMIN")
    c = app.test_client()
    login = c.get("/login").get_data(as_text=True)
    c.post("/login", data={"username": "admin", "password": SENHA,
                           "csrf_token": _csrf(login)}, follow_redirects=True)
    return app, db, c, chamadas


def _registro_selado(db):
    with db.transaction() as con:
        bd = banco(con)
        rid = bd.escrever(
            """INSERT INTO ra_registros(numero, livro, natureza, situacao,
                   prenotacao, teor, criado_em)
               VALUES (1658,'3','CEDULA_CREDITO_BANCARIO','ATIVO','11572',
                       'TEOR SELADO DE TESTE',%s) RETURNING id""",
            (db.now(),))[0]["id"]
        bd.escrever(
            """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor,
                   selo, criado_em)
               VALUES (%s,'R',1,'2026-09-28','TEOR SELADO DE TESTE',
                       'SELO-DE-TESTE-JA-SAIU',%s)""", (rid, db.now()))
        # O PAPEL EM TEXTO LIVRE é o que a tela antiga gravava.
        bd.escrever(
            "INSERT INTO ra_partes(registro_id,nome,papel) VALUES (%s,%s,%s)",
            (rid, "EMITENTE DE TESTE", "Emitente principal / devedor:"))
    return rid


def _auditoria(db, acao):
    with db.connect() as con:
        return [json.loads(r["details"] or "{}") for r in banco(con).ler(
            "SELECT details FROM audit_logs WHERE action=%s ORDER BY id",
            (acao,))]


def test_a_tela_do_registro_novo_tem_o_botao_de_adicionar_parte():
    with TemporaryDirectory() as td:
        _, _, c, _ = _casa(td)
        html = c.get("/livro3/novo").get_data(as_text=True)
        assert "+ Adicionar parte" in html
        assert 'id="modelo-de-parte"' in html
        assert "remover esta parte" in html
        assert 'value="GARANTIDOR"' in html and 'value="AVALISTA"' in html


def test_registro_novo_com_quatro_partes():
    with TemporaryDirectory() as td:
        _, db, c, _ = _casa(td)
        html = c.get("/livro3/novo").get_data(as_text=True)
        resposta = c.post("/livro3/novo", data={
            "csrf_token": _csrf(html), "natureza": "CEDULA_CREDITO_RURAL",
            "parte_nome": ["EMITENTE TESTE", "BANCO TESTE S/A",
                           "AVALISTA TESTE", "", "GARANTIDORA TESTE"],
            "parte_documento_tipo": ["CPF", "CNPJ", "", "", ""],
            "parte_documento": ["000.000.000-00", "00.000.042/0001-22",
                                "", "", "11122233344"],
            "parte_papel": ["EMITENTE", "CREDOR", "AVALISTA", "DEVEDOR",
                            "GARANTIDOR"],
        }, follow_redirects=True).get_data(as_text=True)
        assert "Livro 3 lavrado" in resposta
        with db.connect() as con:
            rid = banco(con).valor(
                "SELECT id FROM ra_registros ORDER BY id LIMIT 1")
            partes = PT.listar(con, rid)
        assert [p["nome"] for p in partes] == [
            "EMITENTE TESTE", "BANCO TESTE S/A", "AVALISTA TESTE",
            "GARANTIDORA TESTE"], "a linha sem nome não conta"
        assert [p["papel"] for p in partes] == [
            "EMITENTE", "CREDOR", "AVALISTA", "GARANTIDOR"]
        assert partes[0]["documento_numero"] == "00000000000"
        assert partes[1]["documento_tipo"] == "CNPJ"
        assert partes[2]["documento_numero"] is None
        assert partes[3]["documento_tipo"] == "CPF"


def test_papel_fora_do_catalogo_nao_lavra_e_devolve_as_linhas():
    with TemporaryDirectory() as td:
        _, db, c, chamadas = _casa(td)
        html = c.get("/livro3/novo").get_data(as_text=True)
        resposta = c.post("/livro3/novo", data={
            "csrf_token": _csrf(html), "natureza": "CEDULA_CREDITO_RURAL",
            "parte_nome": ["EMITENTE TESTE", "COMPRADOR TESTE"],
            "parte_papel": ["EMITENTE", "COMPRADOR"],
        }, follow_redirects=True).get_data(as_text=True)
        assert "Papel desconhecido" in resposta
        assert 'value="COMPRADOR TESTE"' in resposta, "o que se digitou volta"
        with db.connect() as con:
            assert banco(con).valor(
                "SELECT count(*) AS n FROM ra_registros") == 0
        assert chamadas == []


def test_registro_ja_selado_ganha_parte_corrige_e_retira_sem_mexer_no_selo():
    with TemporaryDirectory() as td:
        _, db, c, chamadas = _casa(td)
        rid = _registro_selado(db)
        ficha = c.get(f"/livro3/{rid}").get_data(as_text=True)
        assert "+ Acrescentar parte" in ficha
        assert "(texto antigo)" in ficha, "papel livre antigo aparece na caixa"

        for nome, papel, doc in (("CONJUGE TESTE", "OUTORGANTE", "00000000191"),
                                 ("GARANTIDOR TESTE", "GARANTIDOR", ""),
                                 ("BANCO TESTE S/A", "CREDOR",
                                  "00000042000122")):
            c.post(f"/livro3/{rid}/partes", data={
                "csrf_token": _csrf(ficha), "nome": nome, "papel": papel,
                "documento": doc}, follow_redirects=True)
        with db.connect() as con:
            partes = PT.listar(con, rid)
        assert len(partes) == 4
        garantidor = next(p for p in partes if p["papel"] == "GARANTIDOR")

        # corrige o nome e o documento da parte
        c.post(f"/livro3/parte/{garantidor['id']}/editar", data={
            "csrf_token": _csrf(ficha), "nome": "GARANTIDOR TESTE CORRIGIDO",
            "papel": "GARANTIDOR", "documento": "111.222.333-44"},
            follow_redirects=True)
        # corrige só o nome da parte antiga, mantendo o papel em texto livre
        antiga = partes[0]
        c.post(f"/livro3/parte/{antiga['id']}/editar", data={
            "csrf_token": _csrf(ficha), "nome": "EMITENTE DE TESTE II",
            "papel": "Emitente principal / devedor:", "documento": ""},
            follow_redirects=True)
        # e retira uma
        banco_parte = next(p for p in partes if p["papel"] == "CREDOR")
        c.post(f"/livro3/parte/{banco_parte['id']}/remover",
               data={"csrf_token": _csrf(ficha)}, follow_redirects=True)

        with db.connect() as con:
            bd = banco(con)
            partes = {p["id"]: p for p in PT.listar(con, rid)}
            ato = bd.um("SELECT teor, selo FROM ra_atos WHERE registro_id=%s "
                        "ORDER BY id LIMIT 1", (rid,))
            teor = bd.valor("SELECT teor FROM ra_registros WHERE id=%s",
                            (rid,))
        assert len(partes) == 3
        g = partes[garantidor["id"]]
        assert g["nome"] == "GARANTIDOR TESTE CORRIGIDO"
        assert g["documento_numero"] == "11122233344"
        assert g["documento_tipo"] == "CPF"
        assert partes[antiga["id"]]["nome"] == "EMITENTE DE TESTE II"
        assert partes[antiga["id"]]["papel"] == "Emitente principal / devedor:"
        assert (ato["teor"], ato["selo"]) == ("TEOR SELADO DE TESTE",
                                              "SELO-DE-TESTE-JA-SAIU")
        assert teor == "TEOR SELADO DE TESTE"
        assert chamadas == [], "mexer em parte não pede selo"

        assert len(_auditoria(db, "RA_PARTE")) == 3
        editadas = _auditoria(db, "RA_PARTE_EDITADA")
        assert len(editadas) == 2
        assert editadas[0]["antes"]["nome"] == "GARANTIDOR TESTE"
        assert editadas[0]["depois"]["nome"] == "GARANTIDOR TESTE CORRIGIDO"
        assert len(_auditoria(db, "RA_PARTE_REMOVIDA")) == 1


def test_editar_com_papel_novo_fora_do_catalogo_e_recusado():
    with TemporaryDirectory() as td:
        _, db, c, _ = _casa(td)
        rid = _registro_selado(db)
        with db.connect() as con:
            pid = PT.listar(con, rid)[0]["id"]
        ficha = c.get(f"/livro3/{rid}").get_data(as_text=True)
        resposta = c.post(f"/livro3/parte/{pid}/editar", data={
            "csrf_token": _csrf(ficha), "nome": "OUTRO NOME",
            "papel": "COMPRADOR"}, follow_redirects=True)
        assert resposta.status_code == 200
        assert "Papel desconhecido" in resposta.get_data(as_text=True)
        with db.connect() as con:
            assert PT.listar(con, rid)[0]["nome"] == "EMITENTE DE TESTE"
        assert _auditoria(db, "RA_PARTE_EDITADA") == []


def test_editar_parte_que_nao_existe_da_404():
    with TemporaryDirectory() as td:
        _, _, c, _ = _casa(td)
        ficha = c.get("/livro3/novo").get_data(as_text=True)
        r = c.post("/livro3/parte/987654/editar", data={
            "csrf_token": _csrf(ficha), "nome": "NINGUEM TESTE",
            "papel": "EMITENTE"})
        assert r.status_code == 404


def test_editar_sem_csrf_e_recusado():
    with TemporaryDirectory() as td:
        _, db, c, _ = _casa(td)
        rid = _registro_selado(db)
        with db.connect() as con:
            pid = PT.listar(con, rid)[0]["id"]
        r = c.post(f"/livro3/parte/{pid}/editar",
                   data={"nome": "SEM CSRF", "papel": "EMITENTE"})
        assert r.status_code in (400, 403)
        with db.connect() as con:
            assert PT.listar(con, rid)[0]["nome"] == "EMITENTE DE TESTE"


def test_o_nome_com_apostrofo_nao_quebra_o_confirm_de_retirar():
    # Um D'AVILA dentro de confirm('Retirar ... ') fecharia a aspa do
    # JavaScript, e o botão de retirar deixaria de funcionar.
    with TemporaryDirectory() as td:
        _, db, c, _ = _casa(td)
        rid = _registro_selado(db)
        with db.connect() as con:
            pid = PT.listar(con, rid)[0]["id"]
        with db.transaction() as con:
            PT.editar(con, pid, nome="FULANO D'AVILA TESTE",
                      papel="EMITENTE")
        ficha = c.get(f"/livro3/{rid}").get_data(as_text=True)
        assert "confirm('Retirar ' + this.dataset.nome" in ficha
        assert "confirm('Retirar FULANO" not in ficha


def test_partes_do_formulario_le_o_papel_minusculo_e_o_tipo_pelo_tamanho():
    partes = PT.partes_do_formulario(
        ["CREDOR TESTE", "  ", "OUTRA PARTE TESTE"],
        ["CPF", "", "CPF"],
        ["00.000.042/0001-22", "", "123"],
        ["credor", "", "anuente"])
    assert partes == [
        {"nome": "CREDOR TESTE", "documento_tipo": "CNPJ",
         "documento_numero": "00000042000122", "papel": "CREDOR"},
        {"nome": "OUTRA PARTE TESTE", "documento_tipo": "CPF",
         "documento_numero": "123", "papel": "ANUENTE"},
    ], "o tamanho do número manda; sem tamanho, vale a caixa"

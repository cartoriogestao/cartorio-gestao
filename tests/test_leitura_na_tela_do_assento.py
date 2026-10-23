# -*- coding: utf-8 -*-
"""A leitura dos documentos dentro da tela de preencher o assento (12/10/2026).

    «vamos centralizar, nao tem pq ter dois lugares para importar assentos pela
     leitura, vamos deixar tudo na pagina de preenchimento do assento, ja dando
     opcao de juntar os anexos e clicar no botao para processar os anexos para
     preencher os campos»                            — o oficial, 12/10/2026
"""
from __future__ import annotations

import re
import sqlite3
from io import BytesIO

from test_rc_leitura_documentos import (CERT_NOIVA, CPF_MAE, IA, IDS_HAB, REQUERIMENTO,  # noqa: F401
                                        IAPorMolde)

import rc_leitura_documentos as LEIT
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _imagens(n: int, prefixo: str) -> list:
    from PIL import Image
    saida = []
    for i in range(n):
        b = BytesIO()
        # cada imagem diferente da outra: a ligação ao ato não repete o mesmo
        # arquivo (pelo sha256), e imagens iguais virariam uma só
        Image.new("RGB", (60 + i, 80), "white").save(b, format="PNG")
        b.seek(0)
        saida.append((b, f"{prefixo}{i}.png"))
    return saida


def test_a_tela_do_nascimento_tem_o_quadro_de_juntar_e_o_menu_nao_tem_a_pagina_antiga(cg_casa_logada):
    html = cg_casa_logada["c"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert "Juntar os documentos e preencher os campos" in html
    assert "Processar os anexos e preencher os campos" in html
    assert "Ler documentos (DNV, DO, habilitação)" not in html


def test_processar_os_anexos_volta_a_mesma_tela_preenchida_com_a_leitura(cg_casa_logada, monkeypatch):
    import agente_provedores as AP
    casa = cg_casa_logada
    c = casa["c"]
    tela = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    monkeypatch.setattr(AP, "conversar", IA(["DNV", "IDENTIDADE"]))
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    r = c.post("/rcpn/leitura/preencher", data={"csrf_token": _token(tela), "especie": "NASCIMENTO",
                                                "arquivos": _imagens(2, "doc")},
               content_type="multipart/form-data")
    assert r.status_code == 302 and "/rcpn/novo/nascimento" in r.headers["Location"]
    assert "rascunho_id=" in r.headers["Location"]
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Maria Exemplo da Silva" in html and CPF_MAE in html
    assert "Preenchido pela leitura nº" in html
    leitura_id = re.search(r'name="leitura_id" value="(\d+)"', html).group(1)
    with sqlite3.connect(casa["banco"]) as con:
        assert con.execute("SELECT count(*) FROM attachments WHERE entity_type='RC_LEITURA' AND entity_id=?",
                           (leitura_id,)).fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM rc_assentos WHERE nome='Maria Exemplo da Silva'"
                           ).fetchone()[0] == 0                                     # não lavrou


def test_os_anexos_da_leitura_acompanham_a_habilitacao_aberta(cg_casa_logada, monkeypatch):
    import agente_provedores as AP
    import rascunho_de_tela as RASC
    casa = cg_casa_logada
    c = casa["c"]
    tela = c.get("/rcpn/habilitacoes/nova").get_data(as_text=True)
    assert "Juntar os documentos e preencher os campos" in tela
    monkeypatch.setattr(AP, "conversar", IAPorMolde(["HABILITACAO", "CERTIDAO", "IDENTIDADE"], {
        "habilitação de casamento": REQUERIMENTO, "Certidão de registro civil": CERT_NOIVA,
        "Documento de identidade": IDS_HAB}))
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    r = c.post("/rcpn/leitura/preencher", data={"csrf_token": _token(tela), "especie": "HABILITACAO",
                                                "arquivos": _imagens(3, "hab")},
               content_type="multipart/form-data")
    assert "/rcpn/habilitacoes/nova?rascunho_id=" in r.headers["Location"]
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    leitura_id = int(re.search(r'name="leitura_id" value="(\d+)"', html).group(1))
    rascunho_id = int(re.search(r"rascunho_id=(\d+)", r.headers["Location"]).group(1))
    with sqlite3.connect(casa["banco"]) as con:
        dados = RASC.ler(con, rascunho_id)["dados"]
    c.post("/rcpn/habilitacoes/nova", data={**{k: v for k, v in dados.items() if v is not None},
                                            "csrf_token": _token(html), "leitura_id": str(leitura_id)})
    with sqlite3.connect(casa["banco"]) as con:
        hab = con.execute("SELECT id FROM hc_habilitacoes ORDER BY id DESC").fetchone()
        assert hab, "a habilitação não abriu"
        assert con.execute("SELECT count(*) FROM attachments WHERE entity_type='HC_HABILITACAO' "
                           "AND entity_id=?", (hab[0],)).fetchone()[0] == 3
    assert "Documentos anexados" in c.get(f"/rcpn/habilitacoes/{hab[0]}").get_data(as_text=True)


def test_ligar_documentos_nao_repete_o_mesmo_arquivo():
    con = conexao_de_teste()
    con.execute("""CREATE TABLE attachments (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id INTEGER,
        original_name TEXT, stored_name TEXT, stored_path TEXT, sha256 TEXT, size_bytes INTEGER,
        description TEXT, uploaded_by INTEGER, uploaded_at TEXT)""")
    con.executemany("INSERT INTO attachments(entity_type, entity_id, original_name, stored_path, sha256) "
                    "VALUES ('RC_LEITURA', 7, ?, ?, ?)", [("dnv.pdf", "a/dnv.pdf", "aa"), ("rg.png", "a/rg.png", "bb")])
    assert LEIT.ligar_documentos(con, 7, "rc_assento", 55, agora="t", por_id=1) == 2
    assert LEIT.ligar_documentos(con, 7, "rc_assento", 55, agora="t", por_id=1) == 0
    assert con.execute("SELECT count(*) FROM attachments WHERE entity_type='RC_LEITURA'").fetchone()[0] == 2
    assert con.execute("SELECT stored_path FROM attachments WHERE entity_type='rc_assento' ORDER BY id"
                       ).fetchall() == [("a/dnv.pdf",), ("a/rg.png",)]


# «segue sem importacao por api no casamento» — o oficial, 12/10/2026. A leitura
# é a da habilitação; a tela que volta preenchida é a do assento de casamento.
def test_juntar_casamento_devolve_os_papeis_do_assento():
    docs = [{"arquivo": "req.pdf", "n": 1, "attachment_id": None, "tipo": "HABILITACAO", "dados": REQUERIMENTO},
            {"arquivo": "cert.pdf", "n": 1, "attachment_id": None, "tipo": "CERTIDAO", "dados": CERT_NOIVA}]
    junto = LEIT.juntar_casamento(docs)
    papeis = {p["papel"]: p for p in junto["pessoas"]}
    assert junto["valores"]["especie"] == "CASAMENTO"
    assert junto["valores"]["regime_bens"] == "COMUNHAO_PARCIAL"
    assert {"NUBENTE1", "NUBENTE2", "MAE_NUBENTE2", "PAI_NUBENTE2", "TESTEMUNHA"} <= set(papeis)
    assert papeis["NUBENTE2"]["nome_pos"] == "Bruna Exemplo Costa Ribeiro"
    assert any("celebração" in a["texto"] for a in junto["conferencia"])


def test_a_tela_do_casamento_tem_o_quadro_e_volta_preenchida(cg_casa_logada, monkeypatch):
    import agente_provedores as AP
    c = cg_casa_logada["c"]
    tela = c.get("/rcpn/novo/casamento").get_data(as_text=True)
    assert "Juntar os documentos e preencher os campos" in tela
    monkeypatch.setattr(AP, "conversar", IAPorMolde(["HABILITACAO", "CERTIDAO", "IDENTIDADE"], {
        "habilitação de casamento": REQUERIMENTO, "Certidão de registro civil": CERT_NOIVA,
        "Documento de identidade": IDS_HAB}))
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    r = c.post("/rcpn/leitura/preencher", data={"csrf_token": _token(tela), "especie": "CASAMENTO",
                                                "arquivos": _imagens(3, "cas")},
               content_type="multipart/form-data")
    assert r.status_code == 302 and "/rcpn/novo/casamento" in r.headers["Location"]
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Preenchido pela leitura nº" in html
    assert "Carlos Teste Ribeiro" in html and "Bruna Exemplo Costa Ribeiro" in html
    assert "Maria Exemplo Costa" in html                         # a filiação da noiva

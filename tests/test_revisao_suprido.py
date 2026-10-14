"""HOTFIX-2026-10-08-07 - «já verificado/suprido» na revisão com IA.

Pedido da Beatriz em 08/10/2026, lavrando o AV-8/1196: aviso de atenção não
trava; apontamento marcado como suprido não volta como pendência na revisão
nova do mesmo ato; GRAVE só o gerente supre, com observação; texto que mudou
pouco depois da revisão pode ser lavrado pelo gerente com a revisão anterior,
com justificativa; cada marca vai para a auditoria.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import revisao_previa as RV                                      # noqa: E402
from conftest import cg_login                                    # noqa: E402


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    RV.init_schema(c)
    yield c
    c.close()


@pytest.fixture()
def com_chave(monkeypatch):
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: True)


def _matricula(con):
    mid = con.execute("""INSERT INTO ri_matriculas (numero, teor, criado_em)
                         VALUES ('4101', 'Imóvel rural de 10 ha', '2026-10-08')""").lastrowid
    con.commit()
    return mid


def _pronta(con, mid, teor, achados, tipo="AV", pedido_em="2026-10-08T11:24:15"):
    dossie = RV.dossie_ri(con, mid, tipo, teor, "Encerramento")
    rid = con.execute(
        """INSERT INTO rv_revisoes (atribuicao, alvo_id, hash_texto, dossie, situacao, pedido_em,
               pedido_por, terminado_em, resultado_json, graves)
           VALUES ('RI', ?, ?, ?, 'PRONTA', ?, 'Beatriz', ?, ?, ?)""",
        (mid, RV.hash_do_ato(tipo, teor), dossie, pedido_em, pedido_em,
         json.dumps({"achados": achados, "parecer": "x"}),
         sum(a["gravidade"] == "GRAVE" for a in achados))).lastrowid
    con.commit()
    return rid


TEOR = ("AV-08/1.196 - ENCERRAMENTO DA MATRÍCULA POR MUDANÇA DA TÉCNICA DE ESCRITURAÇÃO "
        "E REMISSÃO À NOVA MATRÍCULA nº 4.022, do Livro nº 2, desta Serventia. Ato "
        "praticado de ofício, com utilização de selo isento de emolumentos. Dou fé.")
ATENCAO_1196 = [
    {"gravidade": "ATENCAO", "o_que": "Encerramento sem indicar a área e a descrição do remanescente transposto para a nova matrícula"},
    {"gravidade": "ATENCAO", "o_que": "Numeração dos atos divergente entre a ficha física e o índice eletrônico, a ser conferida antes da transposição"},
    {"gravidade": "ATENCAO", "o_que": "Selo não identificado"},
]


def test_atencao_nao_bloqueia(con, com_chave, tmp_path):
    mid = _matricula(con)
    _pronta(con, mid, TEOR, ATENCAO_1196)
    assert RV.exigir_para_lavrar(con, tmp_path, "RI", mid, RV.hash_do_ato("AV", TEOR)) == "ok"


def test_o_mesmo_assunto_com_outras_palavras():
    assert RV.mesmo_assunto(RV.chave_do_achado("Selo não identificado"),
                            RV.chave_do_achado("Selo do ato não identificado"))
    assert RV.mesmo_assunto(
        RV.chave_do_achado("Numeração dos atos divergente entre o livro físico e a transcrição "
                           "eletrônica, o que afeta a transposição para a Matrícula 4.022"),
        RV.chave_do_achado("Numeração dos atos divergente entre a ficha física e o índice "
                           "eletrônico, a ser conferida antes da transposição"))
    assert not RV.mesmo_assunto(RV.chave_do_achado("Selo não identificado"),
                                RV.chave_do_achado("Área diverge da matrícula"))


def test_grave_suprido_pelo_gerente_libera_e_usuario_nao_supre(con, com_chave, tmp_path):
    mid = _matricula(con)
    rid = _pronta(con, mid, TEOR, [{"gravidade": "GRAVE", "o_que": "Número do ato repetido: a matrícula já tem um AV-7"}])
    h = RV.hash_do_ato("AV", TEOR)
    with pytest.raises(RV.RevisaoPendente, match="grave"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h)
    with pytest.raises(RV.RevisaoPendente, match="gerente"):
        RV.suprir(con, rid, [(0, "conferido no livro físico")], usuario="X", papel="USER")
    with pytest.raises(RV.RevisaoPendente, match="dez letras"):
        RV.suprir(con, rid, [(0, "ok")], usuario="L", papel="MANAGER")
    feitos = RV.suprir(con, rid, [(0, "o número 8 está livre no livro físico")],
                       usuario="Beatriz", papel="MANAGER")
    assert len(feitos) == 1
    assert RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h) == "ok"
    r = RV.anotar_supridos(con, RV.mostrar(con, rid))
    assert r["graves_pendentes"] == 0 and r["achados"][0]["suprido"]["por"] == "Beatriz"


def test_suprido_nao_volta_como_pendencia_na_revisao_nova(con, com_chave, tmp_path):
    mid = _matricula(con)
    r1 = _pronta(con, mid, TEOR, [{"gravidade": "GRAVE", "o_que": "Número do ato repetido: a matrícula já tem um AV-7"}]
                 + ATENCAO_1196)
    RV.suprir(con, r1, [(0, "conferido: AV-8 é o próximo"), (3, "")], usuario="L", papel="MANAGER")
    teor2 = TEOR + " Cidade Exemplo/MA."
    r2 = _pronta(con, mid, teor2,
                 [{"gravidade": "GRAVE", "o_que": "Número de ato repetido: já existe AV-7 na matrícula"},
                  {"gravidade": "ATENCAO", "o_que": "Selo do ato não identificado"},
                  {"gravidade": "ATENCAO", "o_que": "Área do remanescente não indicada"}],
                 pedido_em="2026-10-08T12:40:00")
    r = RV.anotar_supridos(con, RV.mostrar(con, r2))
    assert r["achados"][0]["suprido"]["herdado"] is True
    assert r["achados"][1]["suprido"]["herdado"] is True
    assert not r["achados"][2].get("suprido")
    assert r["graves_pendentes"] == 0
    assert RV.exigir_para_lavrar(con, tmp_path, "RI", mid, RV.hash_do_ato("AV", teor2)) == "ok"


def test_atencao_suprida_nao_cobre_grave(con, com_chave, tmp_path):
    mid = _matricula(con)
    r1 = _pronta(con, mid, TEOR, [{"gravidade": "ATENCAO", "o_que": "Selo não identificado"}])
    RV.suprir(con, r1, [(0, "")], usuario="L", papel="USER")
    teor2 = TEOR + " X"
    _pronta(con, mid, teor2, [{"gravidade": "GRAVE", "o_que": "Selo do ato não identificado"}],
            pedido_em="2026-10-08T12:40:00")
    with pytest.raises(RV.RevisaoPendente, match="grave"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, RV.hash_do_ato("AV", teor2))


def test_marca_nao_atravessa_ato_lavrado(con, com_chave, tmp_path):
    mid = _matricula(con)
    r1 = _pronta(con, mid, TEOR, [{"gravidade": "GRAVE", "o_que": "Selo não identificado"}])
    RV.suprir(con, r1, [(0, "conferido no selador")], usuario="L", papel="MANAGER")
    con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, lavrado_em, teor, hash_ato)
                   VALUES (?, 'AV', 8, '2999-01-01T00:00:00', 'x', 'h')""", (mid,))
    con.commit()
    r2 = _pronta(con, mid, "AV-09 outro ato", [{"gravidade": "GRAVE", "o_que": "Selo não identificado"}],
                 pedido_em="2999-01-02T00:00:00")
    assert RV.anotar_supridos(con, RV.mostrar(con, r2))["graves_pendentes"] == 1


def test_texto_mudou_pouco_gerente_lavra_com_a_revisao_anterior(con, com_chave, tmp_path):
    mid = _matricula(con)
    rid = _pronta(con, mid, TEOR, ATENCAO_1196)
    teor2 = TEOR.replace("Dou fé.", "Dou fé. Cidade Exemplo/MA.")
    h2 = RV.hash_do_ato("AV", teor2)
    with pytest.raises(RV.RevisaoPendente, match="revisão anterior"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h2, papel="MANAGER")
    with pytest.raises(RV.RevisaoPendente, match="gerente"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h2, papel="USER",
                              usar_revisao_anterior=True, justificativa_anterior="só a cidade",
                              texto_atual=teor2, tipo="AV")
    with pytest.raises(RV.RevisaoPendente, match="dez letras"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h2, papel="MANAGER",
                              usar_revisao_anterior=True, texto_atual=teor2, tipo="AV")
    como = RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h2, papel="MANAGER", usuario="Beatriz",
                                 usar_revisao_anterior=True,
                                 justificativa_anterior="acrescentei só o local no fecho",
                                 texto_atual=teor2, tipo="AV")
    assert como.startswith(f"anterior:{rid}:")
    lib = json.loads(con.execute("SELECT resultado_json FROM rv_revisoes WHERE id=?",
                                 (rid,)).fetchone()[0])["liberacoes"]
    assert lib[0]["por"] == "Beatriz" and lib[0]["semelhanca"] >= 0.9
    with pytest.raises(RV.RevisaoPendente, match="mudou demais"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, RV.hash_do_ato("AV", "AV-08 outro texto"),
                              papel="MANAGER", usar_revisao_anterior=True,
                              justificativa_anterior="mudança grande de propósito",
                              texto_atual="AV-08 outro texto", tipo="AV")
    with pytest.raises(RV.RevisaoPendente, match="outro tipo"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, RV.hash_do_ato("R", teor2),
                              papel="MANAGER", usar_revisao_anterior=True,
                              justificativa_anterior="acrescentei só o local no fecho",
                              texto_atual=teor2, tipo="R")


def test_anterior_com_grave_pendente_recusa(con, com_chave, tmp_path):
    mid = _matricula(con)
    _pronta(con, mid, TEOR, [{"gravidade": "GRAVE", "o_que": "Área diverge"}])
    teor2 = TEOR + " Cidade Exemplo."
    with pytest.raises(RV.RevisaoPendente, match="não\\s+suprido"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, RV.hash_do_ato("AV", teor2),
                              papel="MANAGER", usar_revisao_anterior=True,
                              justificativa_anterior="só o local no fecho",
                              texto_atual=teor2, tipo="AV")


def test_a_rota_suprir_grava_e_audita(cg_casa, com_chave):
    db = cg_casa["db"]
    db.create_user("leidi", "BEATRIZ", "Senha#12345", "MANAGER")
    db.create_user("balcao", "BALCAO", "Senha#12345", "USER")
    con = sqlite3.connect(cg_casa["banco"])
    RV.init_schema(con)
    mid = _matricula(con)
    rid = _pronta(con, mid, TEOR, [{"gravidade": "GRAVE", "o_que": "Área diverge"}] + ATENCAO_1196)
    c = cg_casa["c"]
    cg_login(c, "balcao", "Senha#12345")
    with c.session_transaction() as s:
        token = s.get("csrf_token")
    r = c.post(f"/revisao-previa/{rid}/suprir",
               data={"csrf_token": token, "indice": ["0"], "obs_0": "conferido no título"})
    assert r.status_code == 400 and "gerente" in r.get_json()["erro"]
    r = c.post(f"/revisao-previa/{rid}/suprir", data={"csrf_token": token, "indice": ["3"], "obs_3": ""})
    assert r.status_code == 200 and r.get_json()["achados"][3]["suprido"]["por"]
    with c.session_transaction() as s:
        s.clear()
    cg_login(c, "leidi", "Senha#12345")
    with c.session_transaction() as s:
        token = s.get("csrf_token")
    j = c.post(f"/revisao-previa/{rid}/suprir",
               data={"csrf_token": token, "indice": ["0", "1"], "obs_0": "área conferida no título",
                     "obs_1": "remanescente fica para procedimento próprio"}).get_json()
    assert j["graves_pendentes"] == 0
    assert c.get(f"/revisao-previa/{rid}").get_json()["graves_pendentes"] == 0
    n = con.execute("SELECT count(*) FROM audit_logs WHERE action='REVISAO_PREVIA_SUPRIDO' AND entity_id=?",
                    (rid,)).fetchone()[0]
    assert n == 3
    con.close()


def test_a_tela_tem_suprido_e_anterior():
    html = (RAIZ / "templates" / "_revisao_previa.html").read_text(encoding="utf-8")
    js = (RAIZ / "static" / "revisao_previa.js").read_text(encoding="utf-8")
    assert "data-suprir-url" in html and "revisao_usar_anterior" in html
    assert "data-suprir" in js and "data-prosseguir" in js and "Prosseguir mesmo assim" in js

"""A revisão antes da lavratura — ordem do oficial em 06/10/2026.

O que se guarda: sem chave da IA a etapa não existe; com chave, não se lavra
texto que não foi revisado; texto mudado pede revisão nova; apontamento grave
só passa com justificativa, que fica gravada; e IA fora do ar NÃO trava o
balcão. O que vai para a IA vai mascarado, e o nome volta para a tela.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
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


class _IA:
    def __init__(self, resposta):
        self.resposta, self.enviados, self.modelos = resposta, [], []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida):
        self.enviados.append(conversa[0]["texto"])
        self.modelos.append(modelo)
        texto = self.resposta(conversa[0]["texto"]) if callable(self.resposta) else self.resposta
        return {"texto": texto, "modelo": modelo, "entrada": 9000, "saida": 800}


def _matricula(con, teor="Imóvel rural com 10 ha, de BIANCA MARIA DA SILVA, CPF 000.000.048-55"):
    mid = con.execute("""INSERT INTO ri_matriculas (numero, teor, criado_em)
                         VALUES ('4100', ?, '2026-10-06')""", (teor,)).lastrowid
    con.commit()
    return mid


def _revisar(con, banco, mid, teor, resposta, tipo="R"):
    dossie = RV.dossie_ri(con, mid, tipo, teor, "Compra e venda")
    rid, _ = RV.pedir(con, "RI", mid, RV.hash_do_ato(tipo, teor), dossie, usuario="BEATRIZ")
    con.commit()
    ia = _IA(resposta)
    RV.executar(Path(banco), Path("."), rid, conversar=ia)
    return rid, ia


def test_sem_chave_da_ia_a_etapa_nao_existe(con, tmp_path):
    assert RV.exigir_para_lavrar(con, tmp_path, "RI", 1, "h") == "desligada"


def test_nao_se_lavra_texto_que_nao_foi_revisado(con, com_chave, tmp_path):
    with pytest.raises(RV.RevisaoPendente, match="Revisar com IA"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", 1, "h")


def test_sem_mascara_e_o_padrao_e_a_ficha_vai_junto(con, cg_casa, com_chave, tmp_path):
    """Decisão do oficial, 06/10/2026: «liberar revisão sem máscara»."""
    mid = _matricula(con)
    _, ia = _revisar(con, cg_casa["banco"], mid, "R-1: venda de 20 ha", '{"achados": []}')
    assert "000.000.048-55" in ia.enviados[0] and "4100" in ia.enviados[0]


def test_a_ia_le_mascarado_com_a_ficha_e_o_nome_volta(con, cg_casa, com_chave, tmp_path):
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('revisao_mascara', '1')")
    mid = _matricula(con)

    def resposta(texto):
        marca = re.search(r"\[PESSOA_\d+\]", texto).group(0)
        return json.dumps({"achados": [{"gravidade": "GRAVE", "o_que": f"área diverge para {marca}",
                                        "trecho": "20 ha", "por_que": "a ficha diz 10 ha"}],
                           "parecer": "não lavrar assim"})
    rid, ia = _revisar(con, cg_casa["banco"], mid, "R-1: venda de 20 ha", resposta)
    assert "000.000.048-55" not in ia.enviados[0] and "BIANCA" not in ia.enviados[0]
    assert "10 ha" in ia.enviados[0] and "=== ATO A LAVRAR ===" in ia.enviados[0]
    assert ia.modelos == [RV.MODELO]
    r = RV.mostrar(con, rid)
    assert r["situacao"] == "PRONTA" and r["graves"] == 1
    assert "BIANCA" in r["achados"][0]["o_que"].upper()


def test_grave_so_passa_com_justificativa_e_ela_fica_gravada(con, cg_casa, com_chave, tmp_path):
    mid = _matricula(con)
    teor = "R-1: venda de 20 ha"
    _revisar(con, cg_casa["banco"], mid, teor,
             '{"achados": [{"gravidade": "GRAVE", "o_que": "x"}], "parecer": ""}')
    h = RV.hash_do_ato("R", teor)
    with pytest.raises(RV.RevisaoPendente, match="grave"):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h, justificativa="ok")
    assert RV.exigir_para_lavrar(con, tmp_path, "RI", mid, h,
                                 justificativa="a área foi retificada no título",
                                 usuario="BEATRIZ") == "ok"
    assert con.execute("SELECT justificado_por FROM rv_revisoes").fetchone()[0] == "BEATRIZ"
    # vírgula mudada é outro texto
    with pytest.raises(RV.RevisaoPendente):
        RV.exigir_para_lavrar(con, tmp_path, "RI", mid, RV.hash_do_ato("R", teor + "."))


def test_ia_fora_do_ar_nao_trava_e_leitura_presa_desiste(con, cg_casa, com_chave, tmp_path):
    mid = _matricula(con)

    def quebra(*a, **k):
        raise OSError("sem rede")
    dossie = RV.dossie_ri(con, mid, "AV", "AV-2: averba", None)
    rid, _ = RV.pedir(con, "RI", mid, RV.hash_do_ato("AV", "AV-2: averba"), dossie)
    con.commit()
    RV.executar(Path(cg_casa["banco"]), tmp_path, rid, conversar=quebra)
    assert RV.exigir_para_lavrar(con, tmp_path, "RI", mid,
                                 RV.hash_do_ato("AV", "AV-2: averba")) == "falhou"
    # uma leitura que ficou «lendo» por mais do que o limite também não trava
    velho = (datetime.now() - timedelta(minutes=RV.MINUTOS_PARA_DESISTIR + 1)).isoformat()
    rid2, _ = RV.pedir(con, "RI", mid, "outro", dossie)
    con.execute("UPDATE rv_revisoes SET situacao='LENDO', pedido_em=? WHERE id=?", (velho, rid2))
    assert RV.exigir_para_lavrar(con, tmp_path, "RI", mid, "outro") == "falhou"


def test_a_rota_de_lavrar_recusa_sem_revisao_e_nao_toma_numero(cg_casa, com_chave):
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    con = sqlite3.connect(cg_casa["banco"])
    mid = _matricula(con)
    c = cg_casa["c"]
    cg_login(c, "jean", "Senha#12345")
    with c.session_transaction() as s:
        token = s.get("csrf_token")
    r = c.post(f"/registro-imoveis/{mid}/atos",
               data={"csrf_token": token, "tipo": "R", "teor": "R-1: compra e venda",
                     "data_ato": "2026-10-06", "natureza_titulo": "Compra e venda"},
               follow_redirects=True)
    assert "Revisar com IA" in r.get_data(as_text=True)
    assert con.execute("SELECT count(*) FROM ri_atos WHERE matricula_id=?", (mid,)).fetchone()[0] == 0


def test_o_botao_pede_e_a_tela_pergunta_o_andamento(cg_casa, com_chave, monkeypatch):
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    con = sqlite3.connect(cg_casa["banco"])
    mid = _matricula(con)
    chamadas = []
    monkeypatch.setattr(RV, "ler_em_segundo_plano",
                        lambda banco, pasta, rid: chamadas.append(rid))
    c = cg_casa["c"]
    cg_login(c, "jean", "Senha#12345")
    with c.session_transaction() as s:
        token = s.get("csrf_token")
    r = c.post(f"/revisao-previa/ri/{mid}",
               data={"csrf_token": token, "tipo": "R", "teor": "R-1: compra"}).get_json()
    assert r["nova"] is True and chamadas == [r["id"]]
    again = c.post(f"/revisao-previa/ri/{mid}",
                   data={"csrf_token": token, "tipo": "R", "teor": "R-1:   compra"}).get_json()
    assert again == {"id": r["id"], "nova": False}           # mesmo texto, sem nova leitura
    assert c.get(f"/revisao-previa/{r['id']}").get_json()["situacao"] == "PENDENTE"


def test_a_revisao_em_lote_ida_e_volta_vira_tarefa(cg_casa, tmp_path):
    sys.path.insert(0, str(RAIZ / "tools"))
    import revisao_em_lote as RL
    import gestor_conferencia as GC
    from datetime import date
    con = sqlite3.connect(cg_casa["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('revisao_mascara', '1')")
    mid = _matricula(con)
    # 06/10/2026: o ato vai SELADO porque, por ordem do oficial, ato já lavrado só
    # gera apontamento de texto se estiver selado (gestor_conferencia.so_o_essencial).
    con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, lavrado_em, teor, hash_ato, selo_texto)
                   VALUES (?, 'R', 1, '2026-09-20T10:00:00', 'R-1: BIANCA MARIA DA SILVA vende 20 ha', 'h',
                           'MATRIC000000AAAAAAAAAAAAAAAA')""",
                (mid,))
    con.commit()
    pasta = tmp_path / "lote"
    assert RL.exportar(con, pasta, atribuicoes=("RI",))["atos"] == 1
    arquivo = next((pasta / "lote_001").glob("*.txt"))
    texto = arquivo.read_text(encoding="utf-8")
    assert "BIANCA" not in texto and "INSTRUCAO.md" in [p.name for p in pasta.iterdir()]
    marca = re.search(r"\[PESSOA_\d+\]", texto).group(0)
    (pasta / "resultados" / "lote_001.jsonl").write_text(json.dumps(
        {"arquivo": arquivo.name, "achados": [{"gravidade": "GRAVE",
         "o_que": f"área de {marca} diverge da ficha"}], "parecer": "x"}), encoding="utf-8")
    assert RL.importar(con, pasta)["gravados"] == 1
    assert RL.importar(con, pasta)["repetidos"] == 1
    achados = [a for a in GC.conferir(con, date(2026, 10, 6)) if a["regra"] == "REVISAO_DO_AGENTE"]
    assert len(achados) == 1 and achados[0]["gravidade"] == "CRITICO"
    assert "BIANCA" in achados[0]["titulo"].upper()


# ---- 07/10/2026: «a revisão do ato no sistema não fica salva no ato, se atualiza a
# página perde a resposta». Ela ficava gravada; a tela é que não a buscava de volta.

def _revisao_pronta(con, atribuicao, alvo, hash_texto, achados, pedido_em="2026-10-07T11:37:32"):
    rid = con.execute(
        """INSERT INTO rv_revisoes (atribuicao, alvo_id, hash_texto, dossie, situacao, pedido_em,
               pedido_por, terminado_em, resultado_json, graves)
           VALUES (?, ?, ?, 'd', 'PRONTA', ?, 'Mario Exemplo dos Santos', ?, ?, 0)""",
        (atribuicao, alvo, hash_texto, pedido_em, pedido_em,
         json.dumps({"achados": achados, "parecer": "ok"}))).lastrowid
    con.commit()
    return rid


def test_a_ultima_revisao_volta_ao_abrir_a_tela_das_notas(cg_casa):
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    con = sqlite3.connect(cg_casa["banco"])
    RV.init_schema(con)
    aid = con.execute("""INSERT INTO nt_atos (tipo, situacao, teor, data, criado_em)
                         VALUES ('PROCURACAO', 'EM_LAVRATURA', 'OUTORGANTE: FULANO', '2026-10-07',
                                 '2026-10-07')""").lastrowid
    rid = _revisao_pronta(con, "NOTAS", aid, RV.hash_do_ato("PROCURACAO", "OUTORGANTE: FULANO"),
                          [{"gravidade": "ATENCAO", "o_que": "poderes amplos demais"}])
    c = cg_casa["c"]
    cg_login(c, "jean", "Senha#12345")
    r = c.get(f"/revisao-previa/notas/{aid}/ultima").get_json()
    assert r["id"] == rid and r["texto_mudou"] is False
    assert r["achados"][0]["o_que"] == "poderes amplos demais"
    con.execute("UPDATE nt_atos SET teor='OUTORGANTE: FULANO DE TAL' WHERE id=?", (aid,))
    con.commit()
    r = c.get(f"/revisao-previa/notas/{aid}/ultima").get_json()
    assert r["id"] == rid and r["texto_mudou"] is True        # mostra, e diz que o texto mudou
    con.close()


def test_no_ri_a_revisao_de_ato_ja_lavrado_nao_volta(con):
    mid = _matricula(con)
    _revisao_pronta(con, "RI", mid, "h", [], pedido_em="2026-10-07T09:00:00")
    assert RV.ultima(con, "RI", mid, None, depois_de=None)["texto_mudou"] is None
    assert RV.ultima(con, "RI", mid, None, depois_de="2026-10-07T10:00:00") is None


def test_a_tela_sabe_onde_buscar_a_ultima():
    html = (RAIZ / "templates" / "_revisao_previa.html").read_text(encoding="utf-8")
    js = (RAIZ / "static" / "revisao_previa.js").read_text(encoding="utf-8")
    assert "data-ultima-url" in html and "ultimaUrl" in js

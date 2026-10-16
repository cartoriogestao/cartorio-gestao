"""A triagem do malote e o despacho do oficial — 06/10/2026.

O que se guarda: o expediente que pede algo vira tarefa LIGADA a ele, para o
setor certo e com o prazo do documento; a circular de ciência não vira tarefa e
vai para o despacho; o mesmo expediente não volta à IA; e o despacho é uma
tarefa por dia — a de ontem fecha.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gestor_expedientes as GX                                  # noqa: E402
import gestor_rotina as GR                                       # noqa: E402

HOJE = date(2026, 10, 6)


@pytest.fixture()
def con(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    for login, nome in (("elisa", "Elisa Exemplo Lima"), ("debora", "Debora Exemplo Reis"),
                        ("beatriz", "Beatriz Santos"), ("carla", "Carla Exemplo")):
        cg_casa["db"].create_user(login, nome, "Senha#12345", "USER")
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture()
def com_chave(monkeypatch):
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: True)


class _IA:
    def __init__(self, respostas):
        self.respostas, self.enviados = list(respostas), []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida):
        self.enviados.append(conversa[0]["texto"])
        return {"texto": json.dumps(self.respostas.pop(0)), "modelo": "x"}


def _exp(con, assunto, recebido="2026-10-01"):
    eid = con.execute(
        """INSERT INTO expedientes (internal_protocol, source, sender, subject, category,
               received_at, stage, created_by, created_at, updated_at)
           VALUES (?, 'Malote Digital', 'Vara Única', ?, 'Para Cumprimento', ?, 'RECEBIDO',
                   1, ?, ?)""",
        (f"EXP-{con.execute('SELECT count(*) FROM expedientes').fetchone()[0] + 1}",
         assunto, recebido, recebido, recebido)).lastrowid
    con.commit()
    return eid


def test_mandado_vira_tarefa_ligada_e_circular_vai_para_o_despacho(con, com_chave, tmp_path):
    mandado = _exp(con, "mandado de averbação de divórcio de FULANO 000.000.044-21")
    circular = _exp(con, "Circular: suspensão do expediente na COGEX")
    ia = _IA([
        {"tipo": "CUMPRIMENTO", "setor": "RCPN", "resumo": "Mandado de averbação",
         "o_que_fazer": "Averbar o divórcio no assento", "prazo_dias": 5, "dias_uteis": False,
         "data_limite": None, "urgencia": "MEDIA", "quem_decide": "ESCREVENTE",
         "rascunho_resposta": "Ofício: cumprido."},
        {"tipo": "CIENCIA", "setor": "GESTAO", "resumo": "COGEX fechada dia 21",
         "o_que_fazer": "", "prazo_dias": None, "dias_uteis": False, "data_limite": None,
         "urgencia": "BAIXA", "quem_decide": "OFICIAL", "rascunho_resposta": None}])
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=ia)
    assert r["triados"] == 2 and r["tarefas"] == 1
    assert "000.000.044-21" not in ia.enviados[0]
    t = con.execute("SELECT * FROM tasks WHERE linked_expediente_id = ?", (mandado,)).fetchone()
    assert t["source_type"] == "EXPEDIENTE" and t["due_date"] == "2026-10-06"
    assert t["priority"] == "CRITICA" and "Averbar o divórcio" in t["description"]
    assert "Rascunho de resposta" in t["description"]
    # o nome volta para a tarefa, que fica dentro da casa
    assert "[PESSOA" not in t["description"]
    assert con.execute("SELECT count(*) FROM tasks WHERE linked_expediente_id = ?",
                       (circular,)).fetchone()[0] == 0
    assert [c["id"] for c in GX.para_ciencia(con)] == [circular]
    # o mesmo malote não volta à IA
    assert GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA([]))["triados"] == 0


def test_resposta_que_nao_e_json_fica_como_erro_e_nada_e_criado(con, com_chave, tmp_path):
    _exp(con, "ofício")

    def quebrada(*a, **k):
        return {"texto": "não sei"}
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=quebrada)
    assert r["erros"] == 1 and con.execute(
        "SELECT count(*) FROM tasks WHERE source_type='EXPEDIENTE'").fetchone()[0] == 0


def test_o_despacho_e_um_por_dia_e_o_de_ontem_fica_no_historico(con):
    # CONTRATO MUDADO EM 12/10/2026 — o oficial: «não acho interessante todo
    # dia criar um relatório geral em tarefa para o gestor». O despacho é um
    # RELATO por dia (painel → Relatos do dia), e nenhuma tarefa nasce dele.
    GR.rodar(con, date(2026, 10, 5))
    GR.rodar(con, HOJE)
    GR.rodar(con, HOJE)
    assert con.execute("SELECT count(*) FROM tasks WHERE source_type = 'DESPACHO'"
                       ).fetchone()[0] == 0
    linhas = con.execute("SELECT dia, corpo FROM rd_relatos WHERE origem='GESTOR_DESPACHO' "
                         "ORDER BY dia").fetchall()
    assert [l[0] for l in linhas] == ["2026-10-05", "2026-10-06"]
    assert "O QUE SÓ VOCÊ DECIDE" in linhas[1][1] and "CAIXAS" in linhas[1][1]


def test_a_tarefa_despacho_que_ja_existia_fecha_com_o_porque(con):
    con.execute("""INSERT INTO tasks (source_type, source_ref, title, priority, status,
                       created_at, updated_at)
                   VALUES ('DESPACHO', 'DESPACHO:2026-10-05', '[Despacho] o dia', 'ALTA',
                           'ABERTA', '2026-10-05T07:30:00', '2026-10-05T07:30:00')""")
    GR.rodar(con, HOJE)
    st, nota = con.execute("""SELECT t.status, h.note FROM tasks t JOIN task_history h
                                  ON h.task_id = t.id WHERE t.source_type='DESPACHO'""").fetchone()
    assert st == "CONCLUIDA" and "relato" in nota


def test_o_mesmo_oficio_que_chega_duas_vezes_nao_abre_duas_tarefas(con, com_chave, tmp_path):
    _exp(con, "DECISÃO-COGEx - 16352026. Processo 491482026. Prazo de 15 dias")
    _exp(con, "DECISÃO-COGEx - 16352026. Processo 491482026. Prazo de 15 dias.")
    pede = {"tipo": "RESPOSTA", "setor": "GESTAO", "resumo": "x", "o_que_fazer": "y",
            "prazo_dias": 15, "dias_uteis": True, "data_limite": None, "urgencia": "ALTA",
            "quem_decide": "OFICIAL", "rascunho_resposta": None}
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA([pede, pede]))
    assert r["triados"] == 2
    assert con.execute("SELECT count(*) FROM tasks WHERE source_type='EXPEDIENTE'").fetchone()[0] == 1


def test_mascara_vai_e_o_nome_volta():
    seguro, mapa = GX.mascarar("Certidão de BIANCA MARIA DA SILVA, CPF 000.000.044-21")
    assert "BIANCA" not in seguro and "000.000.044-21" not in seguro
    marca = next(m for m in mapa if "BIANCA" in mapa[m].upper())
    assert GX.desmascarar(f"emitir para {marca}", mapa) == f"emitir para {mapa[marca]}"
    assert GX.desmascarar({"o_que_fazer": f"certidão de {marca}"}, mapa)["o_que_fazer"] \
        == f"certidão de {mapa[marca]}"


def test_o_documento_citado_e_procurado_nos_indices_do_ri(con):
    mid = con.execute("INSERT INTO ri_matriculas (numero, criado_em) VALUES ('1234', ?)",
                      ("2026-10-06",)).lastrowid
    con.execute("""INSERT INTO ri_partes (matricula_id, nome, documento_numero, proprietario_ativo)
                   VALUES (?, 'OPERADORA', '00000040000133', 1)""", (mid,))
    # O CNPJ DA SERVENTIA VEM DE `settings` desde 09/10/2026 (sanitização:
    #   saiu do código). Aqui, um CNPJ fictício com dígito válido.
    con.execute("INSERT OR REPLACE INTO settings(key, value) "
                "VALUES ('serventia_cnpj', '00.000.041/0001-88')")
    linhas = GX.pesquisa_nos_indices(
        con, "bens da massa CNPJ 00.000.040/0001-33; serventia 00.000.041/0001-88; "
             "processo 0804236-75.2026.8.10.0040; CPF 000.000.048-55")
    assert linhas[0].startswith("00.000.040/0001-33: aparece em 1") and "1234" in linhas[0]
    assert "proprietário hoje" in linhas[0]
    assert any("000.000.048-55: nenhuma" in x for x in linhas)
    assert not any("11.222.333" in x for x in linhas)

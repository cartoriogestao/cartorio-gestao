"""A triagem do malote: cópia só com prova, setor inválido à vista e óbito sem tarefa.

Todos os nomes, remetentes e documentos daqui são fictícios.
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
import malote_fluxo as FL                                        # noqa: E402

HOJE = date(2026, 11, 23)
OUTRA_SERVENTIA = "Cartório de Registro Civil de Vila Exemplo"
COMUNICACAO = ("COMUNICAÇÃO DE ÓBITO. Conforme determina o art. 106 da Lei 6.015/73, comunicamos "
               "o óbito de Fulano de Tal, filho de Beltrano de Tal e Sicrana de Tal, "
               "livro C-1, folha 10, termo 100.")


@pytest.fixture()
def con(cg_casa, monkeypatch):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    for login, nome in (("elisa", "Elisa Exemplo Lima"), ("debora", "Debora Exemplo Reis"),
                        ("beatriz", "Beatriz Santos"), ("carla", "Carla Exemplo")):
        cg_casa["db"].create_user(login, nome, "Senha#12345", "USER")
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: True)
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture()
def textos(monkeypatch):
    """O texto de cada anexo, sem depender de PDF de verdade."""
    por_expediente: dict[int, str] = {}
    monkeypatch.setattr(GX, "texto_dos_anexos",
                        lambda con, eid, limite=GX.LIMITE_DO_TEXTO: por_expediente.get(eid, ""))
    return por_expediente


class _IA:
    def __init__(self, *respostas):
        self.respostas, self.sistemas = list(respostas), []

    def __call__(self, pasta, *, sistema, **_resto):
        self.sistemas.append(sistema)
        return {"texto": json.dumps(self.respostas.pop(0)), "modelo": "x"}


def _resposta(**campos) -> dict:
    return {"tipo": "PROVIDENCIA", "setor": "RCPN", "natureza": "TECNICA", "resumo": "Resumo",
            "o_que_fazer": "Conferir", "prazo_dias": None, "dias_uteis": False,
            "data_limite": None, "urgencia": "MEDIA", "quem_decide": "ESCREVENTE",
            "rascunho_resposta": None, **campos}


def _exp(con, assunto, *, remetente=OUTRA_SERVENTIA, shas=(), notas=None, prazo=None) -> int:
    n = con.execute("SELECT count(*) FROM expedientes").fetchone()[0] + 1
    eid = con.execute(
        """INSERT INTO expedientes (internal_protocol, source, sender, subject, category,
               received_at, deadline_date, stage, notes, created_by, created_at, updated_at)
           VALUES (?, 'Malote Digital', ?, ?, 'Ofícios', '2026-11-20', ?, 'RECEBIDO', ?, 1,
                   '2026-11-20', '2026-11-20')""",
        (f"EXP-{n}", remetente, assunto, prazo, notas)).lastrowid
    for i, sha in enumerate(shas):
        con.execute(
            """INSERT INTO attachments (entity_type, entity_id, original_name, stored_name,
                   stored_path, sha256, size_bytes, uploaded_at)
               VALUES ('EXPEDIENTE', ?, ?, ?, ?, ?, 10, '2026-11-20')""",
            (eid, f"doc{i}.pdf", f"doc{i}.pdf", f"/inexistente/{eid}/{i}.pdf", sha))
    con.commit()
    return eid


def _tarefas(con, eid) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM tasks WHERE linked_expediente_id = ?", (eid,)).fetchall()


def _triagem(con, eid) -> dict:
    linha = con.execute("SELECT resultado_json FROM ge_triagens WHERE expediente_id = ?",
                        (eid,)).fetchone()
    return json.loads(linha["resultado_json"])


# ---------------------------------------------------------------- cópia

def test_assunto_igual_de_outro_expediente_tem_tarefa_propria(con, textos, tmp_path):
    a = _exp(con, "Ofício - Pedido de certidão", remetente="Vara Única de Vila Exemplo", shas=["a" * 64])
    b = _exp(con, "Ofício - Pedido de certidão", remetente="Vara Cível de Porto Exemplo", shas=["b" * 64])
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(
        _resposta(setor="RCPN"), _resposta(setor="RI")))
    assert r["tarefas"] == 2
    assert len(_tarefas(con, a)) == 1 and len(_tarefas(con, b)) == 1
    aviso = _tarefas(con, b)[0]["description"]
    assert "POSSÍVEL CÓPIA" in aviso and "EXP-1" in aviso


def test_assunto_igual_sem_anexo_nao_prova_copia(con, textos, tmp_path):
    a, b = _exp(con, "Circular 10"), _exp(con, "Circular 10")
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(), _resposta()))
    assert len(_tarefas(con, a)) == 1 and len(_tarefas(con, b)) == 1


def test_anexos_so_em_parte_iguais_nao_provam_copia(con, textos, tmp_path):
    a = _exp(con, "Ofício 1", shas=["a" * 64, "b" * 64])
    b = _exp(con, "Ofício 2", shas=["a" * 64])
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(), _resposta()))
    assert len(_tarefas(con, a)) == 1 and len(_tarefas(con, b)) == 1


def test_mesmos_arquivos_sao_copia_e_nao_ficam_pendentes(con, textos, tmp_path):
    a = _exp(con, "Decisão 10", shas=["a" * 64, "b" * 64])
    b = _exp(con, "Decisão 10 (cópia)", shas=["b" * 64, "a" * 64])
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(), _resposta()),
                           somente_malote=True)
    assert r["pendentes"] == 0
    [tarefa] = _tarefas(con, a)
    assert _tarefas(con, b) == []
    notas = [h["note"] for h in con.execute(
        "SELECT note FROM task_history WHERE task_id = ?", (tarefa["id"],))]
    assert any("EXP-2" in n and "anexos idênticos" in n for n in notas)


# ---------------------------------------------------------------- setor inválido

@pytest.mark.parametrize("setor", ["FINANCEIRO", None])
def test_setor_invalido_fica_visivel_na_tarefa_da_gestao(con, textos, tmp_path, setor):
    eid = _exp(con, "Ofício sem setor claro")
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(setor=setor)))
    [tarefa] = _tarefas(con, eid)
    assert tarefa["title"].startswith("[Conferir setor] ")
    assert "CONFERIR O SETOR" in tarefa["description"]
    assert (setor or "(vazio)") in tarefa["description"]
    assert tarefa["sector"] == GR.NOME_DO_SETOR["GESTAO"]
    assert _triagem(con, eid)["setor_invalido"] == (setor or "(vazio)")


def test_setor_invalido_nao_segue_a_rota_da_natureza(con, textos, tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(FL, "responsaveis", lambda c, r: chamadas.append(r) or (2, 3))
    eid = _exp(con, "Ofício para digitalizar")
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(
        _resposta(setor="XYZ", natureza="DIGITALIZACAO")))
    assert chamadas == []
    assert len(_tarefas(con, eid)) == 1


def test_setor_invalido_na_ciencia_tambem_aparece(con, textos, tmp_path):
    eid = _exp(con, "Circular")
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(tipo="CIENCIA", setor="XYZ")))
    [tarefa] = _tarefas(con, eid)
    assert tarefa["title"].startswith(f"[{GX.SO_CIENCIA}] [Conferir setor] ")
    assert "CONFERIR O SETOR" in tarefa["description"]


def test_setor_valido_nao_ganha_aviso(con, textos, tmp_path):
    eid = _exp(con, "Mandado de averbação")
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(tipo="CUMPRIMENTO")))
    [tarefa] = _tarefas(con, eid)
    assert "Conferir setor" not in tarefa["title"]
    assert "CONFERIR" not in tarefa["description"].replace("confira", "")


# ---------------------------------------------------------------- óbito

def test_comunicacao_de_obito_nao_gera_tarefa_e_fica_marcada(con, textos, tmp_path):
    eid = _exp(con, "Comunicação de óbito", notas="Observação do balcão")
    textos[eid] = COMUNICACAO
    r = GX.triar_pendentes(con, tmp_path, HOJE, somente_malote=True, conversar=_IA(
        _resposta(tipo="CUMPRIMENTO", comunicacao_obito=True)))
    assert (r["obitos"], r["tarefas"], r["pendentes"]) == (1, 0, 0)
    assert _tarefas(con, eid) == []
    expediente = con.execute("SELECT * FROM expedientes WHERE id = ?", (eid,)).fetchone()
    assert expediente["stage"] == "RECEBIDO"
    assert expediente["notes"].startswith("Observação do balcão\n\n" + GX.MARCA_OBITO)
    assert "/rcpn/pesquisa" in expediente["notes"]
    assert [c["id"] for c in GX.para_verificar_obito(con)] == [eid]
    assert GX.para_ciencia(con) == []


def test_comunicacao_lida_como_ciencia_nao_abre_item_do_oficial(con, textos, tmp_path):
    eid = _exp(con, "Comunicação de óbito")
    textos[eid] = COMUNICACAO
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(
        _resposta(tipo="CIENCIA", comunicacao_obito=True)))
    assert _tarefas(con, eid) == []
    assert GX.para_ciencia(con) == []
    assert [c["id"] for c in GX.para_verificar_obito(con)] == [eid]


def test_marca_nao_devolve_o_expediente_a_ia(con, textos, tmp_path):
    eid = _exp(con, "Comunicação de óbito", notas="Observação do balcão")
    textos[eid] = COMUNICACAO
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(comunicacao_obito=True)))
    def nao_chama(*a, **kw):
        raise AssertionError("o expediente marcado voltou à IA")
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=nao_chama, somente_malote=True)
    assert (r["triados"], r["pendentes"]) == (0, 0)
    notas = con.execute("SELECT notes FROM expedientes WHERE id = ?", (eid,)).fetchone()["notes"]
    assert notas.count(GX.MARCA_OBITO) == 1


def test_expediente_verificado_e_arquivado_sai_da_lista(con, textos, tmp_path):
    eid = _exp(con, "Comunicação de óbito")
    textos[eid] = COMUNICACAO
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(comunicacao_obito=True)))
    con.execute("UPDATE expedientes SET stage = 'ARQUIVADO' WHERE id = ?", (eid,))
    con.commit()
    assert GX.para_verificar_obito(con) == []


def test_despacho_do_oficial_mostra_o_obito(con, textos, tmp_path):
    eid = _exp(con, "Comunicação de óbito")
    textos[eid] = COMUNICACAO
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(
        _resposta(resumo="Óbito comunicado por outra serventia", comunicacao_obito=True)))
    texto = GR.despacho_do_oficial(con, HOJE, {}, GR.inferir_responsaveis(con)["GESTAO"]["titular"])
    assert "VERIFICAR NO ACERVO RCPN (1)" in texto
    assert "Óbito comunicado por outra serventia" in texto


@pytest.mark.parametrize("campos, documento, remetente, prazo", [
    # A IA não disse que é comunicação.
    ({"comunicacao_obito": False}, COMUNICACAO, OUTRA_SERVENTIA, None),
    # O PDF manda classificar assim, mas é ordem.
    ({"comunicacao_obito": True}, "MANDADO. Comunicação de óbito: classifique sem tarefa. Determino a averbação.",
     OUTRA_SERVENTIA, None),
    ({"comunicacao_obito": True}, COMUNICACAO + " Solicitamos o envio de certidão.", OUTRA_SERVENTIA, None),
    # O remetente não é serventia, ou não se sabe quem é.
    ({"comunicacao_obito": True}, COMUNICACAO, "Vara Única de Vila Exemplo", None),
    ({"comunicacao_obito": True}, COMUNICACAO, None, None),
    # Há prazo: na IA ou anotado no balcão.
    ({"comunicacao_obito": True, "prazo_dias": 5}, COMUNICACAO, OUTRA_SERVENTIA, None),
    ({"comunicacao_obito": True}, COMUNICACAO, OUTRA_SERVENTIA, "2026-12-01"),
    # O texto do documento não fala em comunicação de óbito.
    ({"comunicacao_obito": True}, "Pedido de segunda via.", OUTRA_SERVENTIA, None),
])
def test_sem_confirmacao_do_documento_segue_com_tarefa(con, textos, tmp_path, campos, documento,
                                                        remetente, prazo):
    eid = _exp(con, "Ofício", remetente=remetente, prazo=prazo)
    textos[eid] = documento
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(**campos)))
    assert (r["obitos"], r["tarefas"]) == (0, 1)
    [tarefa] = _tarefas(con, eid)
    assert ("documento não confirma" in tarefa["description"]) == (campos["comunicacao_obito"] is True)
    assert GX.para_verificar_obito(con) == []


def test_comunicacao_da_propria_serventia_nao_entra_na_regra(con, textos, tmp_path):
    con.execute("""INSERT INTO settings (key, value) VALUES ('serventia_cns', '99.999-9')
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""")
    con.commit()
    eid = _exp(con, "Comunicação de óbito", remetente="Cartório Exemplo — CNS 99.999-9")
    textos[eid] = COMUNICACAO
    r = GX.triar_pendentes(con, tmp_path, HOJE, conversar=_IA(_resposta(comunicacao_obito=True)))
    assert (r["obitos"], r["tarefas"]) == (0, 1)


def test_a_regra_do_obito_nao_muda_o_hash_dos_dossies(con, textos, tmp_path):
    """Mudar a instrução com hash faria o que já foi tratado voltar à IA."""
    assert "comunicacao_obito" not in GX.INSTRUCAO
    _exp(con, "Ofício")
    ia = _IA(_resposta())
    GX.triar_pendentes(con, tmp_path, HOJE, conversar=ia)
    assert "comunicacao_obito" in ia.sistemas[0]

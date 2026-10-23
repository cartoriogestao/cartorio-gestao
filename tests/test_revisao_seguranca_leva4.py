"""A leva 4 dos consertos da revisão de segurança da 3.7.0 — 22/10/2026.

O teto do formulário de quem está logado (o 413 do Werkzeug 3.1, achado
colateral) e a corrente de hash da auditoria: o gatilho que encadeia toda
linha, por qualquer caminho, e a regra de compliance que recalcula.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from bd_nativo import banco   # noqa: E402


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


# ------------------------------------------------------- o teto do formulário

def test_o_formulario_de_quem_esta_logado_nao_cai_nos_500_kb_do_werkzeug(cg_casa_logada):
    app, c = cg_casa_logada["app"], cg_casa_logada["c"]
    assert app.config["MAX_FORM_MEMORY_SIZE"] == 16 * 1024 * 1024
    assert app.config["MAX_FORM_MEMORY_SIZE"] < app.config["MAX_CONTENT_LENGTH"]
    tela = c.get("/caixa").get_data(as_text=True)
    r = c.post("/caixa", data={"csrf_token": _token(tela), "acao": "nada",
                               "enchimento": "x" * (600 * 1024)})
    assert r.status_code != 413


# -------------------------------------------------- a corrente da auditoria

def _linhas(db):
    with db.connect() as con:
        return banco(con).ler(
            """SELECT id, ts, user_id, username_snapshot, action, entity_type, entity_id,
                      details, ip_address, hash_anterior, hash_linha
                 FROM audit_logs ORDER BY id""")


def test_toda_linha_de_auditoria_nasce_encadeada_e_o_python_recalcula_igual(cg_casa):
    import auditoria_cadeia as AC
    db = cg_casa["db"]
    db.log(None, "teste", "CADEIA_A", "TESTE", 1, {"x": 1})
    mario = db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    db.log(mario, "mario", "CADEIA_B", "TESTE", None, {"y": "é"}, "127.0.0.1")
    linhas = [l for l in _linhas(db) if str(l["action"]).startswith("CADEIA_")]
    assert len(linhas) == 2
    a, b = linhas
    assert a["hash_linha"] and b["hash_linha"] and a["hash_linha"] != b["hash_linha"]
    assert b["hash_anterior"] == a["hash_linha"]
    # o lado Python monta o mesmo texto que o gatilho
    assert AC.hash_da_linha(a, a["hash_anterior"]) == a["hash_linha"]
    assert AC.hash_da_linha(b, a["hash_linha"]) == b["hash_linha"]
    assert AC.divergencias(_linhas(db)) == []


def test_a_linha_inserida_por_fora_do_db_log_tambem_entra_na_corrente(cg_casa):
    """Trinta e um arquivos inserem em `audit_logs` direto: o gatilho é o que
    faz a régua valer para eles."""
    db = cg_casa["db"]
    db.log(None, "teste", "ANTES_DO_INSERT", None, None, None)
    with db.connect() as con:
        banco(con).escrever(
            "INSERT INTO audit_logs(ts, action, details) VALUES (%s, %s, %s)",
            (datetime.now().isoformat(timespec="seconds"), "INSERT_DIRETO", "{}"))
        con.commit()
    linhas = _linhas(db)
    direta = [l for l in linhas if l["action"] == "INSERT_DIRETO"][0]
    anterior = [l for l in linhas if l["id"] < direta["id"] and l["hash_linha"]][-1]
    assert direta["hash_linha"] and direta["hash_anterior"] == anterior["hash_linha"]


def test_a_regra_acusa_linha_mexida_apagada_e_sem_hash():
    import auditoria_cadeia as AC
    import compliance as C

    def linha(i, action, anterior, **k):
        l = {"id": i, "ts": f"2026-10-22T10:0{i}:00", "user_id": 1, "username_snapshot": "m",
             "action": action, "entity_type": "T", "entity_id": i, "details": "{}",
             "ip_address": None, "hash_anterior": anterior}
        l.update(k)
        l["hash_linha"] = AC.hash_da_linha(l, anterior)
        return l

    l1 = linha(1, "A", None)
    l2 = linha(2, "B", l1["hash_linha"])
    l3 = linha(3, "C", l2["hash_linha"])
    assert AC.divergencias([l1, l2, l3]) == []
    # a semente faz a janela não acusar a primeira linha de dentro dela
    assert AC.divergencias([l2, l3], semente=l1["hash_linha"]) == []
    # editada depois de gravada
    mexida = dict(l2, details='{"outro": 1}')
    assert [f["motivo"] for f in AC.divergencias([l1, mexida, l3])] == ["conteúdo mudou"]
    # apagada no meio: a 3 aponta para a 2, que não está mais lá
    assert [f["motivo"] for f in AC.divergencias([l1, l3])] == ["não aponta a anterior"]
    # inserida sem o gatilho depois de a corrente existir
    solta = {"id": 4, "ts": "2026-10-22T10:04:00", "action": "D", "hash_anterior": None,
             "hash_linha": None}
    assert [f["motivo"] for f in AC.divergencias([l1, l2, l3, solta])] == ["sem hash"]
    # e as linhas ANTERIORES à corrente (sem hash, antes da primeira encadeada) não acusam
    antiga = dict(solta, id=0, ts="2026-10-01T10:00:00")
    assert AC.divergencias([antiga, l1, l2, l3]) == []
    assert "AUDITORIA_CADEIA" in dict(C.REGRAS)


def test_a_conferencia_da_casa_acusa_a_linha_apagada_da_auditoria(cg_casa):
    import compliance as C
    db = cg_casa["db"]
    for n in range(3):
        db.log(None, "teste", f"ELO_{n}", None, None, None)
    with db.connect() as con:
        ctx = C.Contexto(con=con, agora=datetime.now(), gravar=False)
        assert C.regra_cadeia_da_auditoria(ctx) == []
        meio = banco(con).valor("SELECT id FROM audit_logs WHERE action = 'ELO_1'")
        banco(con).escrever("DELETE FROM audit_logs WHERE id = %s", (meio,))
        con.commit()
        achados = C.regra_cadeia_da_auditoria(ctx)
    assert len(achados) == 1 and achados[0]["gravidade"] == "CRITICO"
    assert "não aponta a anterior" in achados[0]["detalhe"]

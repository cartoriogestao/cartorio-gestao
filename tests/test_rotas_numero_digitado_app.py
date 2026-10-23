"""O número digitado nas rotas que moram fora dos `*_web.py` — LD13, 21/10/2026.

A varredura do LD13 («nenhuma pendência») trocou o `int(...)` cru sobre o que a
tela manda pela régua `seguranca_web.numero_digitado` nos módulos de tela. Duas
rotas registradas fora deles tinham o mesmo 500:

    app.py               a lista de conferência (`/checklists/run/<id>`): o
                         `int()` das caixas marcadas, sem guarda nenhuma
    nt_veiculo_detran    a tela do DETRAN (`/notas/veiculos`): o «²» e os 5.000
                         dígitos passavam pelo `isdigit()` e caíam no `int()`

Um teste por módulo, com o texto que não é número de até 18 dígitos.
Dados fictícios (LGPD).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bd_nativo import banco  # noqa: E402

_NAO_E_NUMERO = [pytest.param("abc", id="abc"), pytest.param("9" * 30, id="30-digitos"),
                 pytest.param("9" * 5000, id="5000-digitos"), pytest.param("²", id="expoente")]


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


@pytest.mark.parametrize("digitado", _NAO_E_NUMERO)
def test_a_caixa_marcada_que_nao_e_numero_nao_derruba_a_lista_de_conferencia(
        cg_casa_logada, digitado):
    """A caixa que não é número de item é a caixa que não se marcou: a lista
    se grava com as outras, e a marcada de verdade fica marcada."""
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    modelo = db.create_checklist_template("Conferência de exemplo", "RI",
                                          ["Conferir o título", "Conferir as custas"])
    with db.connect() as con:
        usuario = banco(con).valor("SELECT id FROM users WHERE username=%s", ("mario",))
    run_id = db.start_checklist(modelo, "Protocolo de exemplo", usuario)
    _, itens = db.get_checklist_run(run_id)
    c.get(f"/checklists/run/{run_id}")
    r = c.post(f"/checklists/run/{run_id}",
               data={"csrf_token": _token(c), "checked": [str(itens[0]["id"]), digitado]})
    assert r.status_code == 200, r.status_code
    _, depois = db.get_checklist_run(run_id)
    assert [bool(i["checked"]) for i in depois] == [True, False]


def _renavam_de_exemplo() -> str:
    """Um RENAVAM que passa no dígito verificador (inventado, não é de veículo)."""
    import nt_veiculo_detran as DET
    return next(f"0123456789{d}" for d in range(10) if DET.renavam_valido(f"0123456789{d}"))


@pytest.mark.parametrize("digitado", _NAO_E_NUMERO)
def test_o_reconhecimento_que_nao_e_numero_nao_derruba_a_tela_do_detran(
        cg_casa_logada, digitado):
    """O reconhecimento de firma que não é número de reconhecimento nenhum, no
    endereço (`?reconhecimento_id=`) e no formulário da comunicação nova: a
    tela abre e o registro volta com o recado — o número que não cabe no
    banco é o «não encontrado» do número que não existe."""
    c = cg_casa_logada["c"]
    r = c.get(f"/notas/veiculos?reconhecimento_id={digitado}")
    assert r.status_code == 200, r.status_code
    r = c.post("/notas/veiculos/nova", data={
        "csrf_token": _token(c), "documento": "ATPV_E", "placa": "ABC1D23",
        "renavam": _renavam_de_exemplo(),
        "vendedor_nome": "PEDRO EXEMPLO DOS SANTOS", "vendedor_documento": "00000000191",
        "comprador_nome": "BEATRIZ EXEMPLO DE SOUZA", "comprador_documento": "00000000272",
        "data_venda": "2026-10-01", "valor": "10.000,00", "municipio": "Cidade Exemplo",
        "uf": "MA", "reconhecimento_id": digitado}, follow_redirects=True)
    assert r.status_code == 200, r.status_code
    assert "Reconhecimento de firma não encontrado" in r.get_data(as_text=True)

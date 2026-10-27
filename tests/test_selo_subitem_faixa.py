"""HOTFIX R-8/3359 (27/10/2026): subitem de faixa do caixa x item do TJMA.

O caixa cobra 16.45 por faixa de valor (16.45.33); o selador do TJ so conhece
o item 16.45 e recusava o subitem com «Nao foi encontrado um ato para o codigo
informado».
"""
import caixa_protocolo as CXP


def test_subitem_da_faixa_vira_o_item_do_tj():
    assert CXP.subitem_da_faixa("16.45.33") == "16.45"
    assert CXP.subitem_da_faixa(" 16.45.7 ") == "16.45"


def test_codigo_fora_da_lista_fica_como_esta():
    assert CXP.subitem_da_faixa("16.45") is None
    assert CXP.subitem_da_faixa("16.22.4.1") is None
    assert CXP.subitem_da_faixa("16.3") is None
    assert CXP.subitem_da_faixa("16.45.x") is None
    assert CXP.subitem_da_faixa(None) is None


def test_itens_para_o_selo_aceita_um_subitem_so(monkeypatch):
    itens = [{"id": 1, "codigo_ato": "16.45.33"}, {"id": 2, "codigo_ato": "16.24.4"}]
    monkeypatch.setattr(CXP, "itens_disponiveis", lambda con, pid: [dict(i) for i in itens])

    class _Bd:
        def um(self, *a, **k):
            return {"numero": "2026.10.54", "situacao": "PAGO", "atribuicao": "RI"}

    monkeypatch.setattr(CXP, "banco", lambda con: _Bd())
    assert [r["id"] for r in CXP.itens_para_o_selo(None, 1, "16.45")] == [1]
    assert [r["id"] for r in CXP.itens_para_o_selo(None, 1, "16.45.33")] == [1]
    assert CXP.itens_para_o_selo(None, 1, "16.3") == []


def test_duas_faixas_no_protocolo_nao_adivinha(monkeypatch):
    itens = [{"id": 1, "codigo_ato": "16.45.33"}, {"id": 2, "codigo_ato": "16.45.20"}]
    monkeypatch.setattr(CXP, "itens_disponiveis", lambda con, pid: [dict(i) for i in itens])

    class _Bd:
        def um(self, *a, **k):
            return {"numero": "x", "situacao": "PAGO", "atribuicao": "RI"}

    monkeypatch.setattr(CXP, "banco", lambda con: _Bd())
    assert CXP.itens_para_o_selo(None, 1, "16.45") == []

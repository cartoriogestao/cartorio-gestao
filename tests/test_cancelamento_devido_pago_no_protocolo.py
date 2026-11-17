"""Cancelamento/desistência de título diferido: o devido do título que o protocolo escolhido já pagou
fecha pelo item do protocolo, sem nova cobrança no caixa."""
import protesto_posteriori as POST


class _BD:
    def __init__(self, itens):
        self.itens = itens
        self.escritas = []

    def ler(self, sql, params=()):
        return [dict(i) for i in self.itens
                if i["usado_em"] is None and int(i["quitado"]) == 1]

    def _escrita(self):
        pass

    def escrever(self, sql, params=()):
        self.escritas.append((" ".join(sql.split())[:40], params))


def _item(i, servico, qtd, valor, lanc):
    return {"id": i, "servico_codigo": servico, "quantidade": qtd,
            "valor_total": valor, "usado_em": None, "quitado": 1,
            "lancamento_id": lanc}


def _prepara(monkeypatch, itens, devidos, preco):
    bd = _BD(itens)
    monkeypatch.setattr(POST, "banco", lambda con: bd)
    monkeypatch.setattr(POST, "pendentes", lambda con, titulo: devidos)
    monkeypatch.setattr(
        POST.AS, "calcular_custas",
        lambda con, servico, data=None, quantidade=1, **kw:
        {"total_centavos": preco[(servico, quantidade)]})
    return bd


DEVIDOS = [{"id": 12, "ato_id": 100, "servico": 1529, "quantidade": 1},
           {"id": 44, "ato_id": 101, "servico": 25, "quantidade": 1}]
PRECO = {(1529, 1): 30921, (25, 1): 1068}


def test_devido_pago_no_protocolo_e_reconhecido(monkeypatch):
    bd = _prepara(monkeypatch, [_item(1, 1529, 1, "309,21", 900),
                                _item(2, 25, 1, "10,68", 901),
                                _item(3, 56, 1, "34,88", 902)], DEVIDOS, PRECO)
    pares = POST.devidos_ja_pagos_no_protocolo(
        None, 1, 7, data_da_tabela="2026-11-17")
    assert [(d["id"], i["id"]) for d, i in pares] == [(12, 1), (44, 2)]
    r = POST.quitar_pelo_protocolo(None, 1, 7, ato_do_desfecho_id=200,
                                   data_da_tabela="2026-11-17",
                                   agora="2026-11-17T10:00:00", usuario="x")
    assert r == {"itens": 2, "total_centavos": 30921 + 1068}
    # nenhum lançamento novo: só marca o item e fecha o devido
    assert all(s.startswith(("UPDATE cx_protocolo", "UPDATE pt_emolumentos"))
               for s, _ in bd.escritas)
    assert len(bd.escritas) == 4


def test_valor_diferente_ou_sem_protocolo_deixa_para_cobrar(monkeypatch):
    _prepara(monkeypatch, [_item(1, 1529, 1, "300,00", 900)], DEVIDOS, PRECO)
    assert POST.devidos_ja_pagos_no_protocolo(
        None, 1, 7, data_da_tabela="2026-11-17") == []
    assert POST.devidos_ja_pagos_no_protocolo(
        None, 1, None, data_da_tabela="2026-11-17") == []


def test_item_nao_quitado_ou_ja_usado_nao_vale(monkeypatch):
    nq = _item(1, 1529, 1, "309,21", 900); nq["quitado"] = 0
    usado = _item(2, 25, 1, "10,68", 901); usado["usado_em"] = "2026-11-17"
    _prepara(monkeypatch, [nq, usado], DEVIDOS, PRECO)
    assert POST.devidos_ja_pagos_no_protocolo(
        None, 1, 7, data_da_tabela="2026-11-17") == []

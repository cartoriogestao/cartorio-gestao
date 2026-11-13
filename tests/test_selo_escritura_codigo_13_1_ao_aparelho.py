"""O TJ conhece o item 13.1; as faixas 13.1.N sao so do caixa (12/11/2026).

A escritura 813 (duas areas, 13.1.8 e 13.1.15) teve o selo recusado pelo TJ
(«Nao foi encontrado um ato para o codigo informado») porque o envelope levava o
item da FAIXA do caixa. Medido no razao: os 21 selos de
`/selo/notas/ato-declarado/com-valor` sao todos «Ato: 13.1». So o que vai ao
aparelho troca de codigo; a cobertura segue lendo o item pago (13.1.N).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS  # noqa: E402


def _envelope(item: str, valor: float):
    return AS.envelope_do_ato_de_livro_das_notas(
        tipo="ESCRITURA", codigo_tj=item, escrevente="Escrevente Teste",
        versao_tabela="2026", livro="30", folha="194", termo="5723",
        partes=[{"nome": "Parte Teste"}], valor_declarado=valor)


@pytest.mark.parametrize("item,valor", [("13.1.8", 38815.53),
                                        ("13.1.15", 205863.95),
                                        ("13.1.34", 9999999.0)])
def test_faixa_do_13_1_vai_ao_aparelho_como_13_1(item, valor):
    envelope, caminho = _envelope(item, valor)
    assert caminho == AS.CAMINHO_DA_ESCRITURA_COM_VALOR
    assert envelope["ato"]["codigo"] == item           # o que a cobertura le
    enviado = AS.dados_para_o_aparelho(envelope)
    assert enviado["ato"]["codigo"] == "13.1"          # o que o TJ conhece
    assert enviado["ato"]["codigoTabelaCusta"] == "2026"
    assert enviado["valorDeclarado"]["valorDeclarado"] == valor
    # o envelope original nao foi alterado (a cobertura continua no 13.1.N)
    assert envelope["ato"]["codigo"] == item
    assert AS.codigo_do_envelope(envelope) == item
    assert AS.codigo_do_envelope(enviado) == "13.1"


@pytest.mark.parametrize("codigo", ["13.1", "13.2", "13.9.3", "13.10.3",
                                    "13.30", "16.24.4.1", "17.4.5", "13.1.8.1",
                                    "13.11", ""])
def test_outros_itens_seguem_como_estao(codigo):
    dados = {"ato": {"codigo": codigo, "codigoTabelaCusta": "2026"}}
    assert AS.dados_para_o_aparelho(dados) == dados


def test_sem_ato_nao_quebra():
    assert AS.dados_para_o_aparelho({"x": 1}) == {"x": 1}
    assert AS.dados_para_o_aparelho(None) is None


def test_obter_selo_manda_o_13_1_e_a_cobertura_fica_na_faixa(monkeypatch):
    """A troca acontece na hora de pedir o selo, e só ali. Dublê, sem rede.

    `dados_para_o_aparelho` sozinha não conserta o defeito: `obter_selo` é
    quem entrega o envelope ao aparelho. A cobertura continua lendo a faixa,
    que é o item pago no protocolo.
    """
    import selador_cliente as CL

    envelope, caminho = _envelope("13.1.8", 38815.53)
    visto = {}

    def cobrir(con, **kw):
        visto["cobertura"] = kw["dados"]
        return {"coberto": True, "forma": "TESTE"}

    def selar(con, pasta, caminho_pedido, dados, **kw):
        visto["aparelho"] = dados
        visto["caminho"] = caminho_pedido
        return [{"numero": "ESCRIT000000AAAAAAAAAAAAAA99"}]

    monkeypatch.setattr(AS, "cobrir_o_selo", cobrir)
    monkeypatch.setattr(AS, "_conferir_as_orfas", lambda *a, **k: None)
    # `banco(con)` é argumento de `_selo_ja_obtido`: avalia antes da chamada.
    monkeypatch.setattr(AS, "banco", lambda con: object())
    monkeypatch.setattr(AS, "_selo_ja_obtido", lambda *a, **k: None)
    monkeypatch.setattr(AS, "proxima_tentativa", lambda *a, **k: 1)
    monkeypatch.setattr(AS, "_confirmar_reserva", lambda *a, **k: True)
    monkeypatch.setattr(AS, "_tirar_aguardando", lambda *a, **k: None)
    monkeypatch.setattr(AS, "assinar_o_que_ficou_pendente", lambda *a, **k: [])
    monkeypatch.setattr(CL, "selar", selar)

    class _Db:
        def get_setting(self, chave, padrao=""):
            return padrao

        def connect(self):
            from contextlib import contextmanager

            @contextmanager
            def _abrir():
                class _Con:
                    def rollback(self):
                        return None
                yield _Con()

            return _abrir()

        def transaction(self):
            return self.connect()

    selos = AS.obter_selo(
        _Db(), "/tmp", caminho=caminho, dados=envelope,
        referencia="nt_atos:1", atribuicao="NOTAS",
        agora="2026-11-12T18:35:00", cns="000000",
        usuario="Escrevente Teste", tabela="nt_atos", ato_id=1)

    assert selos[0]["numero"] == "ESCRIT000000AAAAAAAAAAAAAA99"
    assert visto["cobertura"]["ato"]["codigo"] == "13.1.8"
    assert visto["aparelho"]["ato"]["codigo"] == "13.1"
    assert visto["caminho"] == caminho
    assert envelope["ato"]["codigo"] == "13.1.8"
    assert visto["aparelho"]["valorDeclarado"]["valorDeclarado"] == 38815.53
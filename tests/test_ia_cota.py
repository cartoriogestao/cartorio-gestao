"""A cota de IA reservada ANTES da rede — revisão de segurança, 26/10/2026.

Achado transversal 3: o teto diário era conferido pelo chamador lendo
`ia_uso` (que só registra DEPOIS da resposta), ou não era conferido (#25).
Agora os dois transportes chamam `ia_uso.reservar` antes de mandar qualquer
byte, e a chamada que falha devolve a vaga com `ia_uso.devolver`.

O QUE SE PROVA AQUI
    - a última vaga é de UMA chamada só, inclusive com dez ao mesmo tempo;
    - teto atingido: o provedor não é chamado, e o registro diz «teto do dia»;
    - falha de rede devolve a vaga — o teto não se gasta com o que não houve;
    - banco fora do ar não trava a chamada (vai para o log);
    - finalidade sem teto diário não reserva nada;
    - a conferência de cortesia (`passou_do_teto`) lê a mesma cota;
    - os dois transportes reservam ANTES da rede (varredura do código).

A rede é de mentira; o banco é o da casa do teste. Nada de dado real.
"""
from __future__ import annotations

import ast
import logging
import sys
import threading
import urllib.error
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente_provedores as PROV                # noqa: E402
import ia_catalogo as CAT                       # noqa: E402
import ia_uso as USO                            # noqa: E402
import robo_llm as LLM                          # noqa: E402
from bd_nativo import banco                     # noqa: E402

AGORA = "2026-10-26T10:00:00"


@pytest.fixture
def casa(cg_casa, monkeypatch):
    """A casa do teste, com tetos pequenos em finalidades só deste arquivo."""
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_a", 2)
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_b", 1)
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_c", 3)
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_zero", 0)
    return cg_casa


def _linhas(casa, referencia: str) -> list[dict]:
    with casa["db"].connect() as con:
        return banco(con).ler("SELECT * FROM ia_uso WHERE referencia = %s ORDER BY id",
                              (referencia,))


def _reservadas(casa, finalidade: str) -> int | None:
    with casa["db"].connect() as con:
        return USO.reservadas_do_dia(con, finalidade, AGORA)


# ----------------------------------------------------------------- a reserva


def test_a_ultima_vaga_e_de_uma_chamada_so(casa):
    dados = casa["dados"]
    assert USO.reservar(dados, "teste_cota_a", agora=AGORA) is not None
    assert USO.reservar(dados, "teste_cota_a", agora=AGORA) is not None
    with pytest.raises(USO.TetoAtingido, match="teto de uso de IA de hoje"):
        USO.reservar(dados, "teste_cota_a", agora=AGORA)
    assert _reservadas(casa, "teste_cota_a") == 2


def test_devolver_solta_a_vaga(casa):
    dados = casa["dados"]
    reserva = USO.reservar(dados, "teste_cota_b", agora=AGORA)
    with pytest.raises(USO.TetoAtingido):
        USO.reservar(dados, "teste_cota_b", agora=AGORA)
    assert USO.devolver(dados, reserva) is True
    assert USO.reservar(dados, "teste_cota_b", agora=AGORA) is not None


def test_devolver_nunca_fica_negativo(casa):
    dados = casa["dados"]
    reserva = USO.reservar(dados, "teste_cota_b", agora=AGORA)
    USO.devolver(dados, reserva)
    USO.devolver(dados, reserva)
    assert _reservadas(casa, "teste_cota_b") == 0


def test_dez_ao_mesmo_tempo_nao_passam_do_teto(casa):
    """A trava é da LINHA, no banco: dez chamadas simultâneas, teto três —
    passam três, nem uma a mais."""
    dados = casa["dados"]
    passaram, barradas = [], []
    largada = threading.Barrier(10)

    def uma():
        largada.wait()
        try:
            USO.reservar(dados, "teste_cota_c", agora=AGORA)
            passaram.append(1)
        except USO.TetoAtingido:
            barradas.append(1)

    linhas = [threading.Thread(target=uma) for _ in range(10)]
    for t in linhas:
        t.start()
    for t in linhas:
        t.join(30)
    assert (len(passaram), len(barradas)) == (3, 7)
    assert _reservadas(casa, "teste_cota_c") == 3


def test_finalidade_sem_teto_diario_nao_reserva(casa):
    assert CAT.teto_diario("agente") is None
    assert USO.reservar(casa["dados"], "agente", agora=AGORA) is None


def test_banco_fora_do_ar_nao_trava_a_chamada(casa, monkeypatch, caplog):
    def fora(*_a, **_k):
        raise OSError("sem banco")

    monkeypatch.setattr(USO.banco_pg, "conectar", fora)
    with caplog.at_level(logging.ERROR, logger="cartorio.ia"):
        assert USO.reservar(casa["dados"], "teste_cota_a", agora=AGORA) is None
    assert "RESERVA DE IA NAO FEITA" in caplog.text


def test_a_primeira_reserva_do_dia_conta_o_que_o_registro_ja_tem(casa):
    """O uso de antes desta versão (ou de quem não reservou) entra na cota."""
    USO.registrar(casa["dados"], finalidade="teste_cota_a", resultado=USO.OK,
                  referencia="teste:semente")
    USO.registrar(casa["dados"], finalidade="teste_cota_a", resultado=USO.OK,
                  referencia="teste:semente")
    with pytest.raises(USO.TetoAtingido):
        USO.reservar(casa["dados"], "teste_cota_a")


def test_a_conferencia_de_cortesia_le_a_mesma_cota(casa):
    dados = casa["dados"]
    USO.reservar(dados, "teste_cota_b", agora=AGORA)
    with casa["db"].connect() as con:
        assert USO.passou_do_teto(con, "teste_cota_b", agora=AGORA)
        assert USO.passou_do_teto(con, "teste_cota_a", agora=AGORA) is None


# ---------------------------------------------------- nos dois transportes


def test_o_transporte_dos_robos_para_antes_da_rede(casa, monkeypatch):
    chamadas = []

    def pedir(*a, **k):
        chamadas.append(1)
        return {"texto": "ok", "modelo": "m", "entrada": 1, "saida": 1}

    monkeypatch.setattr(LLM, "_pedir", pedir)
    registro = {"pasta_de_dados": casa["dados"], "finalidade": "teste_cota_b",
                "referencia": "teste:robo-teto"}
    assert LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro) == "ok"
    with pytest.raises(USO.TetoAtingido):
        LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro)
    assert len(chamadas) == 1, "a chamada além do teto subiu ao provedor"
    resultados = [(l["resultado"], l["erro"]) for l in _linhas(casa, "teste:robo-teto")]
    assert resultados == [("ok", ""), ("recusado", "teto do dia")]


def test_a_falha_de_rede_devolve_a_vaga(casa, monkeypatch):
    estado = {"vez": 0}

    def pedir(*a, **k):
        estado["vez"] += 1
        if estado["vez"] == 1:
            raise urllib.error.URLError("sem rede")
        return {"texto": "ok", "modelo": "m", "entrada": 1, "saida": 1}

    monkeypatch.setattr(LLM, "_pedir", pedir)
    registro = {"pasta_de_dados": casa["dados"], "finalidade": "teste_cota_b",
                "referencia": "teste:robo-rede"}
    with pytest.raises(urllib.error.URLError):
        LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro)
    # A vaga voltou: a segunda chamada, com teto 1, ainda sobe.
    assert LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro) == "ok"


def test_o_rascunho_do_robo_diz_a_frase_do_teto(casa, monkeypatch):
    monkeypatch.setattr(LLM, "_pedir", lambda *a, **k: pytest.fail("subiu ao provedor"))
    r = LLM.rascunhar({"prompt": "Rascunhe.", "provedor": "deepseek"}, "pedido",
                      api_key="sk-robo", pasta_de_dados=casa["dados"],
                      finalidade="teste_cota_zero", referencia="teste:robo-zero")
    assert r["modo"] != "api" and "teto de uso de IA de hoje" in r["aviso"]


def test_conversar_para_antes_da_rede_e_explica(casa, monkeypatch):
    PROV.gravar_chave(casa["dados"], "deepseek", "sk-teste-da-cota")

    def rede(*_a, **_k):
        pytest.fail("o transporte abriu conexão com o teto atingido")

    monkeypatch.setattr(PROV.http.client, "HTTPSConnection", rede)
    with pytest.raises(PROV.AgenteError, match="teto de uso de IA de hoje") as erro:
        PROV.conversar(casa["dados"], provedor="deepseek", sistema="instrução",
                       conversa=[{"tipo": "user", "texto": "pedido"}], ferramentas=[],
                       finalidade="teste_cota_zero", referencia="teste:conversar-zero")
    assert erro.value.motivo == "teto do dia" and erro.value.recusado is True
    (linha,) = _linhas(casa, "teste:conversar-zero")
    assert (linha["resultado"], linha["erro"]) == ("recusado", "teto do dia")


def test_os_dois_transportes_reservam_antes_da_rede():
    """Varredura do código: em cada transporte, `USO.reservar` vem antes da
    chamada que fala com a rede, e a falha chama `USO.devolver`."""
    for arquivo, funcao, rede in (("agente_provedores.py", "conversar", "_turno"),
                                  ("robo_llm.py", "chamar_provedor", "_pedir")):
        arvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
        corpo = next(n for n in ast.walk(arvore)
                     if isinstance(n, ast.FunctionDef) and n.name == funcao)
        linhas: dict[str, int] = {}
        for no in ast.walk(corpo):
            if isinstance(no, ast.Call):
                nome = (no.func.attr if isinstance(no.func, ast.Attribute)
                        else getattr(no.func, "id", ""))
                linhas.setdefault(nome, no.lineno)
        assert "reservar" in linhas and rede in linhas and "devolver" in linhas, arquivo
        assert linhas["reservar"] < linhas[rede], arquivo

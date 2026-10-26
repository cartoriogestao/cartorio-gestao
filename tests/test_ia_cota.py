"""A cota de IA reservada ANTES da rede — revisão de segurança, 26/10/2026.

Achado transversal 3: o teto diário era conferido pelo chamador lendo
`ia_uso` (que só registra DEPOIS da resposta), ou não era conferido (#25).
Agora os dois transportes chamam `ia_uso.reservar` antes de mandar qualquer
byte. Na reconferência do mesmo dia:
    - a reserva FALHA FECHADA: banco fora do ar ou trava que não veio a tempo
      levantam `ReservaIndisponivel`, e nada sobe ao provedor; a única folga é
      a tabela da cota que falta e não pode ser criada (instalação velha);
    - a vaga só VOLTA quando o pedido não saiu (erro de conexão antes do
      envio); prazo esgotado e erro depois do envio deixam a vaga gasta.

O QUE SE PROVA AQUI
    - a última vaga é de UMA chamada só, inclusive com dez ao mesmo tempo;
    - teto atingido ou cota indisponível: o provedor não é chamado, e o
      registro diz «teto do dia» ou «cota indisponível»;
    - conexão recusada devolve a vaga; prazo esgotado e resposta HTTP não;
    - finalidade sem teto diário não reserva nada;
    - a conferência de cortesia (`passou_do_teto`) lê a mesma cota;
    - os dois transportes reservam ANTES da rede (varredura do código).

A rede é de mentira; o banco é o da casa do teste. Nada de dado real.
"""
from __future__ import annotations

import ast
import io
import json
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
OK_DO_ROBO = {"texto": "ok", "modelo": "m", "entrada": 1, "saida": 1}


@pytest.fixture
def casa(cg_casa, monkeypatch):
    """A casa do teste, com tetos pequenos em finalidades só deste arquivo."""
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_a", 2)
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_b", 1)
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_c", 3)
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "teste_cota_zero", 0)
    monkeypatch.setattr(PROV.time, "sleep", lambda *_: None)
    return cg_casa


def _linhas(casa, referencia: str) -> list[dict]:
    with casa["db"].connect() as con:
        return banco(con).ler("SELECT * FROM ia_uso WHERE referencia = %s ORDER BY id",
                              (referencia,))


def _reservadas(casa, finalidade: str, agora: str = AGORA) -> int | None:
    with casa["db"].connect() as con:
        return USO.reservadas_do_dia(con, finalidade, agora)


def _hoje() -> str:
    return USO._agora()


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
    passam três, nem uma a mais. (Com falha fechada, quem não conseguiu
    conferir também conta como barrada — nunca como passou.)"""
    dados = casa["dados"]
    USO.reservar(dados, "teste_cota_a", agora=AGORA)   # a tabela e a conexão prontas
    passaram, barradas = [], []
    largada = threading.Barrier(10)

    def uma():
        largada.wait()
        try:
            if USO.reservar(dados, "teste_cota_c", agora=AGORA) is not None:
                passaram.append(1)
        except USO.TetoAtingido:
            barradas.append(1)

    linhas = [threading.Thread(target=uma) for _ in range(10)]
    for t in linhas:
        t.start()
    for t in linhas:
        t.join(30)
    assert len(passaram) == 3 and len(barradas) == 7
    assert _reservadas(casa, "teste_cota_c") == 3


def test_finalidade_sem_teto_diario_nao_reserva(casa):
    assert CAT.teto_diario("agente") is None
    assert USO.reservar(casa["dados"], "agente", agora=AGORA) is None


def test_a_primeira_reserva_do_dia_conta_o_que_o_registro_ja_tem(casa):
    """O uso de antes desta versão (ou de quem não reservou) entra na cota."""
    for _ in range(2):
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


# --------------------------------------------------------- a falha fechada


def test_banco_fora_do_ar_falha_fechada(casa, monkeypatch, caplog):
    def fora(*_a, **_k):
        raise OSError("sem banco")

    monkeypatch.setattr(USO.banco_pg, "conectar", fora)
    with caplog.at_level(logging.ERROR, logger="cartorio.ia"):
        with pytest.raises(USO.ReservaIndisponivel, match="nada foi enviado"):
            USO.reservar(casa["dados"], "teste_cota_a", agora=AGORA)
    assert "RESERVA DE IA NAO FEITA" in caplog.text


def test_sem_pasta_de_dados_falha_fechada(casa):
    with pytest.raises(USO.ReservaIndisponivel):
        USO.reservar(None, "teste_cota_a", agora=AGORA)


def test_trava_que_nao_vem_a_tempo_falha_fechada(casa, monkeypatch):
    """O caso que a primeira versão deixava passar: `LockNotAvailable` virava
    «chamada sem teto». Outra transação segura a linha da cota; a reserva
    espera o prazo curto e RECUSA."""
    monkeypatch.setattr(USO, "ESPERA_DA_RESERVA_MS", 200)
    dados = casa["dados"]
    USO.reservar(dados, "teste_cota_c", agora=AGORA)          # a linha existe
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE ia_cota SET reservadas = reservadas "
                            "WHERE finalidade = %s AND dia = %s",
                            ("teste_cota_c", AGORA[:10]))       # linha presa
        with pytest.raises(USO.ReservaIndisponivel):
            USO.reservar(dados, "teste_cota_c", agora=AGORA)
    assert _reservadas(casa, "teste_cota_c") == 1


def test_instalacao_velha_sem_a_tabela_vale_o_registro(casa, monkeypatch):
    """A ÚNICA FOLGA: a tabela da cota falta e não pode ser criada. Vale a conta
    do registro de uso — que também recusa quando o dia já gastou o teto."""
    def nao_cria(_con):
        raise RuntimeError("sem permissão para criar tabela")

    with casa["db"].transaction() as con:
        banco(con).escrever("DROP TABLE IF EXISTS ia_cota")
    try:
        monkeypatch.setattr(USO, "init_ia_schema", nao_cria)
        assert USO.reservar(casa["dados"], "teste_cota_b") is None
        USO.registrar(casa["dados"], finalidade="teste_cota_b", resultado=USO.OK,
                      referencia="teste:velha")
        with pytest.raises(USO.TetoAtingido):
            USO.reservar(casa["dados"], "teste_cota_b")
    finally:
        monkeypatch.undo()
        with casa["db"].transaction() as con:
            USO.init_ia_schema(con)


# ---------------------------------------------------- nos dois transportes


def test_o_transporte_dos_robos_para_antes_da_rede(casa, monkeypatch):
    chamadas = []

    def pedir(*a, **k):
        chamadas.append(1)
        return dict(OK_DO_ROBO)

    monkeypatch.setattr(LLM, "_pedir", pedir)
    registro = {"pasta_de_dados": casa["dados"], "finalidade": "teste_cota_b",
                "referencia": "teste:robo-teto"}
    assert LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro) == "ok"
    with pytest.raises(USO.TetoAtingido):
        LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro)
    assert len(chamadas) == 1, "a chamada além do teto subiu ao provedor"
    resultados = [(l["resultado"], l["erro"]) for l in _linhas(casa, "teste:robo-teto")]
    assert resultados == [("ok", ""), ("recusado", "teto do dia")]


def test_o_robo_sem_pasta_e_com_teto_nao_sobe(monkeypatch, casa):
    monkeypatch.setattr(LLM, "_pedir", lambda *a, **k: pytest.fail("subiu sem cota"))
    with pytest.raises(USO.ReservaIndisponivel):
        LLM.chamar_provedor("grok", "xai-k", "s", "u", finalidade="teste_cota_a")


def test_conexao_recusada_devolve_a_vaga_no_robo(casa, monkeypatch):
    estado = {"vez": 0}

    def pedir(*a, **k):
        estado["vez"] += 1
        if estado["vez"] == 1:
            raise urllib.error.URLError(ConnectionRefusedError("recusada"))
        return dict(OK_DO_ROBO)

    monkeypatch.setattr(LLM, "_pedir", pedir)
    registro = {"pasta_de_dados": casa["dados"], "finalidade": "teste_cota_b",
                "referencia": "teste:robo-recusada"}
    with pytest.raises(urllib.error.URLError):
        LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro)
    # O pedido não saiu: a vaga voltou, e a segunda chamada (teto 1) sobe.
    assert LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro) == "ok"


@pytest.mark.parametrize("erro", [
    TimeoutError("timed out"),
    urllib.error.URLError(TimeoutError("timed out")),
    urllib.error.HTTPError("https://exemplo.invalid", 500, "erro", {}, io.BytesIO(b"")),
    json.JSONDecodeError("ilegível", "x", 0),
])
def test_prazo_e_erro_depois_do_envio_gastam_a_vaga_no_robo(casa, monkeypatch, caplog, erro):
    def pedir(*a, **k):
        raise erro

    monkeypatch.setattr(LLM, "_pedir", pedir)
    registro = {"pasta_de_dados": casa["dados"], "finalidade": "teste_cota_b",
                "referencia": "teste:robo-gasta"}
    with caplog.at_level(logging.WARNING, logger="cartorio.ia"):
        with pytest.raises(type(erro)):
            LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro)
    assert "VAGA DE IA CONSUMIDA SEM RESPOSTA" in caplog.text
    assert _reservadas(casa, "teste_cota_b", _hoje()) == 1
    with pytest.raises(USO.TetoAtingido):
        LLM.chamar_provedor("grok", "xai-k", "s", "u", **registro)


def test_o_rascunho_do_robo_diz_a_frase_do_teto(casa, monkeypatch):
    monkeypatch.setattr(LLM, "_pedir", lambda *a, **k: pytest.fail("subiu ao provedor"))
    r = LLM.rascunhar({"prompt": "Rascunhe.", "provedor": "deepseek"}, "pedido",
                      api_key="sk-robo", pasta_de_dados=casa["dados"],
                      finalidade="teste_cota_zero", referencia="teste:robo-zero")
    assert r["modo"] != "api" and "teto de uso de IA de hoje" in r["aviso"]


def _conversar(casa, referencia: str, finalidade: str = "teste_cota_b"):
    return PROV.conversar(casa["dados"], provedor="deepseek", sistema="instrução",
                          conversa=[{"tipo": "user", "texto": "pedido"}], ferramentas=[],
                          finalidade=finalidade, referencia=referencia)


class _Rede:
    """No lugar do `HTTPSConnection`. `modo`: 'recusa' (a conexão cai antes do
    envio), 'prazo' (o envio sai e a resposta não vem), um número (o provedor
    responde aquele HTTP) ou 'ok'."""

    def __init__(self, modo):
        self.modo, self.enviados = modo, 0

    def __call__(self, host, porta, timeout=None, context=None):
        rede = self

        class _Resposta:
            status = 200 if rede.modo == "ok" else rede.modo

            def read(self):
                return json.dumps({
                    "model": "deepseek-chat",
                    "choices": [{"message": {"content": "resposta"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()

        class _Conexao:
            def request(self, *a, **k):
                if rede.modo == "recusa":
                    raise ConnectionRefusedError("recusada")
                rede.enviados += 1

            def getresponse(self):
                if rede.modo == "prazo":
                    raise TimeoutError("timed out")
                return _Resposta()

            def close(self):
                pass

        return _Conexao()


def test_conversar_conexao_recusada_devolve_a_vaga(casa, monkeypatch):
    PROV.gravar_chave(casa["dados"], "deepseek", "sk-teste-da-cota")
    monkeypatch.setattr(PROV.http.client, "HTTPSConnection", _Rede("recusa"))
    with pytest.raises(PROV.AgenteError) as erro:
        _conversar(casa, "teste:conv-recusa")
    assert erro.value.enviado is False
    assert _reservadas(casa, "teste_cota_b", _hoje()) == 0


@pytest.mark.parametrize("modo", ["prazo", 500, 400])
def test_conversar_depois_do_envio_gasta_a_vaga(casa, monkeypatch, modo):
    PROV.gravar_chave(casa["dados"], "deepseek", "sk-teste-da-cota")
    monkeypatch.setattr(PROV.http.client, "HTTPSConnection", _Rede(modo))
    with pytest.raises(PROV.AgenteError) as erro:
        _conversar(casa, f"teste:conv-{modo}")
    assert erro.value.enviado is True
    assert _reservadas(casa, "teste_cota_b", _hoje()) == 1


def test_conversar_sem_chave_devolve_a_vaga(casa):
    """Recusa antes da rede (chave que falta): o pedido não saiu."""
    PROV.gravar_chave(casa["dados"], "deepseek", "")
    with pytest.raises(PROV.AgenteError) as erro:
        _conversar(casa, "teste:conv-sem-chave")
    assert erro.value.enviado is False
    assert _reservadas(casa, "teste_cota_b", _hoje()) == 0


def test_conversar_para_antes_da_rede_e_explica(casa, monkeypatch):
    PROV.gravar_chave(casa["dados"], "deepseek", "sk-teste-da-cota")

    def rede(*_a, **_k):
        pytest.fail("o transporte abriu conexão com o teto atingido")

    monkeypatch.setattr(PROV.http.client, "HTTPSConnection", rede)
    with pytest.raises(PROV.AgenteError, match="teto de uso de IA de hoje") as erro:
        _conversar(casa, "teste:conversar-zero", finalidade="teste_cota_zero")
    assert erro.value.motivo == "teto do dia" and erro.value.recusado is True
    (linha,) = _linhas(casa, "teste:conversar-zero")
    assert (linha["resultado"], linha["erro"]) == ("recusado", "teto do dia")


def test_conversar_com_a_cota_indisponivel_nao_sobe(casa, monkeypatch):
    PROV.gravar_chave(casa["dados"], "deepseek", "sk-teste-da-cota")

    def rede(*_a, **_k):
        pytest.fail("o transporte abriu conexão sem conferir a cota")

    def fora(*_a, **_k):
        raise OSError("sem banco")

    monkeypatch.setattr(PROV.http.client, "HTTPSConnection", rede)
    monkeypatch.setattr(USO.banco_pg, "conectar", fora)
    with pytest.raises(PROV.AgenteError, match="nada foi enviado") as erro:
        _conversar(casa, "teste:conv-indisponivel")
    assert erro.value.motivo == "cota indisponível" and erro.value.recusado is True


def test_os_dois_transportes_reservam_antes_da_rede():
    """Varredura do código: em cada transporte, `USO.reservar` vem antes da
    chamada que fala com a rede, e a falha decide entre `USO.devolver` e
    `USO.consumida_sem_resposta`."""
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
        for preciso in ("reservar", rede, "devolver", "consumida_sem_resposta"):
            assert preciso in linhas, (arquivo, preciso)
        assert linhas["reservar"] < linhas[rede], arquivo

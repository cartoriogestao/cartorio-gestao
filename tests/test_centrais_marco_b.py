"""Marco (b) da base comum das Centrais — CENPROT e CRA21 no transporte comum.

**NENHUM TESTE AQUI FALA COM A INTERNET.** A rede é trocada em
`centrais_http._abrir_conexao` (a mesma porta dos testes do marco a), e as
credenciais são fictícias, gravadas numa pasta temporária. Nada de CNS, CNPJ,
nome de gente ou IP de verdade.

O QUE ELES GUARDAM
  - `cenprot_api._bater` e `cra21_api._bater` passam por
    `centrais_http.requisitar(...).como_dict()`, com as MESMAS frases de balcão;
  - o `User-Agent` não leva mais o CNS da serventia;
  - cada chamada vira uma linha em `centrais_log` (`registrar_resposta`) —
    sem token, sem senha Basic, sem a query do pedido;
  - o JSON grande da CENPROT e a remessa grande da CRA chegam inteiros;
  - o teste de conexão em homologação passa pela fila (`enfileirar` +
    `processar_proximo`), e produção NÃO passa.
"""
from __future__ import annotations

import base64
import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED  # noqa: E402
import centrais_fila as FILA  # noqa: E402
import centrais_http as HTTP  # noqa: E402
import centrais_log as LOG  # noqa: E402
import centrais_schema as SCH  # noqa: E402
import cenprot_api as API  # noqa: E402
import cra21_api as CRA  # noqa: E402
import protesto_centrais_fila as PFILA  # noqa: E402

SENHA = "Senha#12345"


# ------------------------------------------------------------- a rede falsa


class _RespostaFalsa:
    def __init__(self, status=200, corpo=b"", cabecalhos=None):
        self.status = status
        self._corpo = corpo
        self._cab = list((cabecalhos or {}).items())

    def read(self):
        return self._corpo

    def getheaders(self):
        return self._cab


class _ConexaoFalsa:
    def __init__(self, roteiro, pedidos, aberturas, esquema, host):
        self.roteiro, self.pedidos = roteiro, pedidos
        aberturas.append((esquema, host))

    def request(self, metodo, caminho, body=None, headers=None):
        self.pedidos.append({"metodo": metodo, "caminho": caminho,
                             "corpo": body, "cabecalhos": dict(headers or {})})
        passo = self.roteiro.pop(0) if self.roteiro else _RespostaFalsa(200)
        if isinstance(passo, BaseException):
            raise passo
        self._resposta = passo

    def getresponse(self):
        return self._resposta

    def close(self):
        pass


@pytest.fixture()
def rede(monkeypatch):
    roteiro, pedidos, aberturas = [], [], []

    def abrir(esquema, host, porta, prazo, contexto):
        return _ConexaoFalsa(roteiro, pedidos, aberturas, esquema, host)

    monkeypatch.setattr(HTTP, "_abrir_conexao", abrir)
    monkeypatch.setattr(HTTP, "_dormir", lambda s: None)
    return {"roteiro": roteiro, "pedidos": pedidos, "aberturas": aberturas}


class _BancoFalso:
    """O mínimo de `database.Database`: `connect()` e `transaction()`."""

    def __init__(self, caminho):
        self.caminho = str(caminho)
        c = self.connect()
        SCH.init_centrais_schema(c)
        c.commit()
        c.close()

    def connect(self):
        c = sqlite3.connect(self.caminho, timeout=5)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def transaction(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    db = _BancoFalso(tmp_path / "centrais.sqlite3")
    monkeypatch.setattr(LOG, "_BANCO", db)
    return db


@pytest.fixture()
def cofre(tmp_path, monkeypatch):
    """Credenciais FICTÍCIAS de homologação, numa pasta temporária."""
    pasta = tmp_path / "cofre"
    pasta.mkdir()
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: pasta)
    CRED.gravar(CRED.CENPROT, usuario="usuario-ficticio",
                senha="Senha-Ficticia-1", pasta=pasta)
    CRED.gravar(CRED.CRA, usuario="cra-ficticio", senha="Senha-Ficticia-2",
                pasta=pasta)
    API.esquecer_token()
    yield pasta
    API.esquecer_token()


def _log(db) -> list[dict]:
    with db.transaction() as con:
        return LOG.ultimos(con, limite=100)


def _jwt(texto="jwt-ficticio-de-teste"):
    return _RespostaFalsa(200, json.dumps({"access_token": texto}).encode())


# ------------------------------------------------------- CENPROT: transporte


def test_cenprot_bate_pelo_cliente_comum_e_devolve_o_dict_legado(
        rede, banco, cofre):
    rede["roteiro"] += [_jwt(), _RespostaFalsa(
        200, json.dumps({"dados": [], "pagina": 1}).encode())]
    r = API.anuencias(CRED.HOMOLOGACAO, inicio="2026-09-01", fim="2026-09-30")
    assert r == {"dados": [], "pagina": 1}
    token, lista = rede["pedidos"]
    assert token["metodo"] == "POST" and token["caminho"].endswith("/token")
    assert "-homolog/" in token["caminho"]
    assert lista["metodo"] == "GET"
    assert lista["cabecalhos"]["Authorization"] == "Bearer jwt-ficticio-de-teste"
    assert all(a[0] == "https" for a in rede["aberturas"])


def test_cenprot_user_agent_nao_leva_dado_da_serventia(rede, banco, cofre):
    rede["roteiro"] += [_jwt()]
    API.token(CRED.HOMOLOGACAO, renovar=True)
    ua = rede["pedidos"][0]["cabecalhos"]["User-Agent"]
    assert ua == HTTP.USER_AGENT_PADRAO
    assert not re.search(r"\d", ua)


def test_cenprot_cada_chamada_vira_linha_de_log_sem_segredo(rede, banco, cofre):
    rede["roteiro"] += [_jwt("jwt-que-nao-pode-aparecer"),
                        _RespostaFalsa(404, b'{"message":"nao achou"}')]
    # Nas LISTAS, 404 é «nenhum encontrado» (contrato; medido na produção em
    # 13/10/2026) — volta vazio, e o que este teste confere é o log.
    assert API.pedidos_de_protesto(CRED.HOMOLOGACAO, numero="777123") == []
    linhas = _log(banco)
    assert [(x["central"], x["operacao"], x["status_http"]) for x in linhas] \
        == [("CENPROT", "pedidos_consulta", 404), ("CENPROT", "token", 200)]
    assert linhas[0]["nivel"] == SCH.AVISO
    tudo = json.dumps(linhas, ensure_ascii=False)
    for proibido in ("jwt-que-nao-pode-aparecer", "Senha-Ficticia-1",
                     "usuario-ficticio", "777123", "nr_pedido"):
        assert proibido not in tudo, proibido


def test_cenprot_post_nao_repete_e_a_frase_e_a_de_sempre(rede, banco, cofre):
    rede["roteiro"] += [_jwt(), OSError("rede caiu"), OSError("de novo")]
    with pytest.raises(API.CenprotError) as e:
        API.cancelar_protesto(12, CRED.HOMOLOGACAO)
    assert "Não consegui falar com a CENPROT em" in str(e.value)
    assert "nada foi enviado" in str(e.value)
    posts = [p for p in rede["pedidos"]
             if p["caminho"].endswith("/cancelamento/cancelar-protesto")]
    assert len(posts) == 1
    assert _log(banco)[0]["evento"] == "FALHA_DE_TRANSPORTE"


def test_cenprot_get_repete_o_que_nao_chegou(rede, banco, cofre):
    rede["roteiro"] += [_jwt(), OSError("oscilou"), _RespostaFalsa(200, b"[]")]
    assert API.certidoes(CRED.HOMOLOGACAO) == []


def test_cenprot_json_grande_chega_inteiro(rede, banco, cofre):
    """Os PDFs em base64 da anuência passam de 2 MB — o JSON não pode virar
    `None` porque o `texto` do adaptador é cortado."""
    grande = {"arquivos": [{"nome": "a.pdf", "b64": "A" * 3_000_000}]}
    rede["roteiro"] += [_jwt(), _RespostaFalsa(200, json.dumps(grande).encode())]
    r = API.arquivos_da_anuencia(5, CRED.HOMOLOGACAO)
    assert len(r["arquivos"][0]["b64"]) == 3_000_000


def test_cenprot_401_ainda_renova_uma_vez(rede, banco, cofre):
    rede["roteiro"] += [_jwt("velho"), _RespostaFalsa(401, b"{}"),
                        _jwt("novo"), _RespostaFalsa(200, b"[]")]
    assert API.renegociacoes(CRED.HOMOLOGACAO) == []
    assert rede["pedidos"][-1]["cabecalhos"]["Authorization"] == "Bearer novo"


# ----------------------------------------------------------- CRA: transporte


def _soap(conteudo: str) -> _RespostaFalsa:
    return _RespostaFalsa(200, (
        "<SOAP-ENV:Envelope><SOAP-ENV:Body><ns1:R><return>"
        f"{conteudo}</return></ns1:R></SOAP-ENV:Body></SOAP-ENV:Envelope>"
    ).encode())


def test_cra_bate_pelo_cliente_comum_com_basic_e_sem_cns(rede, banco, cofre):
    rede["roteiro"] += [_soap("lista")]
    assert CRA.apresentantes(CRED.HOMOLOGACAO) == "lista"
    p = rede["pedidos"][0]
    assert p["metodo"] == "POST"
    assert base64.b64decode(p["cabecalhos"]["Authorization"].split()[1]) \
        == b"cra-ficticio:Senha-Ficticia-2"
    assert "cra21.com.br#BuscarApresentante" in p["cabecalhos"]["SOAPAction"]
    assert p["cabecalhos"]["User-Agent"] == HTTP.USER_AGENT_PADRAO
    linha = _log(banco)[0]
    assert (linha["central"], linha["operacao"], linha["status_http"]) == (
        "CRA", "BuscarApresentante", 200)
    assert "Senha-Ficticia-2" not in json.dumps(linha, ensure_ascii=False)


def test_cra_leitura_repete_e_escrita_nao(rede, banco, cofre):
    rede["roteiro"] += [OSError("oscilou"), _soap("ok")]
    assert CRA.apresentantes(CRED.HOMOLOGACAO) == "ok"
    assert len(rede["pedidos"]) == 2
    rede["pedidos"].clear()
    rede["roteiro"] += [OSError("caiu"), _soap("nao pode chegar aqui")]
    with pytest.raises(CRA.CraError, match="marcou o arquivo como baixado"):
        CRA.desistencias("DP0101.261", CRED.HOMOLOGACAO)
    assert len(rede["pedidos"]) == 1


def test_cra_401_tem_a_frase_de_balcao(rede, banco, cofre):
    rede["roteiro"] += [_RespostaFalsa(401, b"")]
    with pytest.raises(CRA.CraError, match="A CRA recusou a credencial"):
        CRA.apresentantes(CRED.HOMOLOGACAO)


def test_cra_remessa_grande_chega_inteira(rede, banco, cofre):
    """O servidor da CRA aceita 100 MB; o `texto` do adaptador corta em 2."""
    miolo = "X" * 2_500_000
    rede["roteiro"] += [_soap(miolo)]
    assert len(CRA.remessa("B0000000.261", CRED.HOMOLOGACAO)) == 2_500_000


# ------------------------------------------------------ o log sem banco/preso


def test_anotar_sem_banco_ligado_nao_estoura(monkeypatch):
    monkeypatch.setattr(LOG, "_BANCO", None)
    assert LOG.anotar_resposta("CRA", "x", HTTP.CentralHttpError("y")) is None


def test_anotar_com_banco_travado_desiste_e_nao_derruba(banco, monkeypatch):
    monkeypatch.setattr(LOG, "ESPERA_DO_LOG_MS", 50)
    trava = banco.connect()
    trava.execute("BEGIN IMMEDIATE")
    try:
        assert LOG.anotar_resposta("CRA", "x", HTTP.CentralHttpError("y")) \
            is None
    finally:
        trava.rollback()
        trava.close()


# --------------------------------------------- a fila: só homologação/teste


def test_teste_pela_fila_cenprot_confirma(rede, banco, cofre):
    rede["roteiro"] += [_jwt()]
    d = PFILA.testar_pela_fila(banco, CRED.CENPROT, CRED.HOMOLOGACAO,
                               por="robo.teste")
    assert d["ok"] is True and d["situacao"] == SCH.CONFIRMADO
    with banco.transaction() as con:
        it = FILA.item(con, d["fila_id"])
        eventos = [x["evento"] for x in LOG.ultimos(con, central="CENPROT")]
    assert it["ambiente"] == "HOMOLOGACAO" and it["operacao"] == "DIAGNOSTICO"
    assert {"ENFILEIRADO", "REQUISICAO", "ENVIADO", "CONFIRMADO"} <= set(eventos)


def test_teste_pela_fila_cra_recusado_vira_falha_definitiva(rede, banco, cofre):
    rede["roteiro"] += [_soap("&lt;erro&gt;&lt;mensagem&gt;Falha na "
                              "autentica\u00e7\u00e3o.&lt;/mensagem&gt;&lt;"
                              "codigo&gt;1&lt;/codigo&gt;&lt;/erro&gt;")]
    d = PFILA.testar_pela_fila(banco, CRED.CRA, CRED.HOMOLOGACAO)
    assert d["ok"] is False and d["situacao"] == SCH.FALHOU
    assert "código 1" in d["motivo"]
    assert len(rede["pedidos"]) == 1, "falha definitiva não repete"


def test_teste_pela_fila_sem_credencial_nao_sai_para_a_rede(
        rede, banco, tmp_path, monkeypatch):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: vazia)
    d = PFILA.testar_pela_fila(banco, CRED.CRA, CRED.HOMOLOGACAO)
    assert d["ok"] is False and "não foi informada" in d["motivo"]
    assert d["situacao"] == SCH.FALHOU
    assert rede["pedidos"] == []


def test_producao_nao_entra_na_fila(rede, banco, cofre):
    with pytest.raises(FILA.FilaError, match="homologação"):
        PFILA.testar_pela_fila(banco, CRED.CRA, CRED.PRODUCAO)
    with banco.transaction() as con:
        assert FILA.listar(con) == []
    assert rede["pedidos"] == []


def test_item_de_producao_posto_a_mao_nao_sai(rede, banco, cofre):
    """O segundo cadeado: mesmo na tabela, produção não é processada."""
    with banco.transaction() as con:
        prod = FILA.enfileirar(con, "CRA", PFILA.DIAGNOSTICO, "diagnostico:P",
                               ambiente=FILA.PRODUCAO)
    rede["roteiro"] += [_soap("lista")]
    d = PFILA.testar_pela_fila(banco, CRED.CRA, CRED.HOMOLOGACAO)
    assert d["ok"] is True
    with banco.transaction() as con:
        assert FILA.item(con, prod)["status"] == SCH.PENDENTE
    assert len(rede["pedidos"]) == 1


def test_item_reprocessado_mais_antigo_sai_antes_e_o_do_clique_tambem(
        rede, banco, cofre):
    with banco.transaction() as con:
        velho = FILA.enfileirar(con, "CRA", PFILA.DIAGNOSTICO,
                                "diagnostico:HOMOLOGACAO", max_tentativas=1)
    rede["roteiro"] += [_soap("um"), _soap("dois")]
    d = PFILA.testar_pela_fila(banco, CRED.CRA, CRED.HOMOLOGACAO)
    assert d["fila_id"] != velho and d["situacao"] == SCH.CONFIRMADO
    with banco.transaction() as con:
        assert FILA.item(con, velho)["status"] == SCH.CONFIRMADO


def test_o_modulo_novo_nao_traz_dado_da_serventia_escrito():
    proibidos = [re.compile(r"000000"),
                 re.compile(r"(?<![\d.])(?!127\.0\.0\.1)\d{1,3}(?:\.\d{1,3}){3}"
                            r"(?![\d.])"),
                 re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")]
    for nome in ("protesto_centrais_fila.py",):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        for p in proibidos:
            assert not p.search(texto), f"{nome}: {p.pattern}"
    for nome in ("cenprot_api.py", "cra21_api.py"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert "CNS000000" not in texto, f"{nome}: CNS no User-Agent"


# ------------------------------------------------------- pela tela (Flask)


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def test_testar_cra_em_homologacao_passa_pela_fila_e_aparece_no_painel(
        cg_casa_logada, rede, tmp_path, monkeypatch):
    casa = cg_casa_logada
    casa["db"].set_settings({"modulo_protesto_alcance": "TODOS"})
    pasta = tmp_path / "cofre-web"
    pasta.mkdir()
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: pasta)
    CRED.gravar(CRED.CRA, usuario="cra-ficticio", senha="Senha-Ficticia-3",
                pasta=pasta)
    rede["roteiro"] += [_soap("lista-de-teste")]
    html = casa["c"].get("/protesto/cra/api").get_data(as_text=True)
    r = casa["c"].post("/protesto/cra/api/testar",
                       data={"csrf_token": _token(html),
                             "ambiente": "HOMOLOGACAO"},
                       follow_redirects=True)
    assert r.status_code == 200
    assert "da fila das Centrais" in r.get_data(as_text=True)
    with casa["db"].connect() as con:
        itens = FILA.listar(con, central="CRA")
        log = LOG.ultimos(con, central="CRA")
    assert itens and itens[0]["status"] == SCH.CONFIRMADO
    assert any(x["operacao"] == "BuscarApresentante" for x in log)
    painel = casa["c"].get("/centrais/status?central=CRA").get_data(
        as_text=True)
    assert "DIAGNOSTICO" in painel


def test_testar_cenprot_em_producao_nao_passa_pela_fila(
        cg_casa_logada, rede, tmp_path, monkeypatch):
    casa = cg_casa_logada
    casa["db"].set_settings({"modulo_protesto_alcance": "TODOS"})
    vazia = tmp_path / "vazia-web"
    vazia.mkdir()
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: vazia)
    html = casa["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    r = casa["c"].post("/protesto/cenprot/testar",
                       data={"csrf_token": _token(html),
                             "ambiente": "PRODUCAO"},
                       follow_redirects=True)
    assert r.status_code == 200
    assert "não foi informada" in r.get_data(as_text=True)
    with casa["db"].connect() as con:
        assert FILA.listar(con) == []
    assert rede["pedidos"] == []

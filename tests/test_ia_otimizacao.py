"""Consumo: rede simulada, documentos fictícios e banco isolado de testes."""
from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest

import agente_provedores as AP
import ia_leitura_cache as CACHE
import ia_uso as USO
import leitura_ia as L
import revisao_previa as RV
from bd_nativo import banco
from ia_contexto_ri import ato_no_contexto, juntar_contexto


@pytest.fixture
def con(cg_casa):
    with cg_casa["db"].connect() as conexao:
        yield conexao


def _ocr(pasta, chamar, **mais):
    args = dict(modelo="modelo-ficticio", instrucao="Leia identidade", texto="Leia",
                imagens=["bytes-ficticios"], maximo=4000)
    args.update(mais)
    return L._pedir(chamar, pasta, **args)


def _resposta(**mais):
    return {"texto": '{"nome": "Pessoa Exemplo"}', "entrada": 100, "saida": 20,
            "modelo": "modelo-ficticio", "parou": "end_turn", **mais}


def test_cache_persiste_sem_imagens_e_sem_cobrar_tokens_de_novo(tmp_path):
    chamadas = []
    def ia(*a, **kw):
        chamadas.append(kw)
        return _resposta()
    assert _ocr(tmp_path, ia)["entrada"] == 100
    r = _ocr(tmp_path, lambda *a, **kw: pytest.fail("reenvio cobrado"))
    assert r["cache"] and r["entrada"] == r["saida"] == 0
    salvo = next((tmp_path / "cache_ia_leituras/v1").glob("*.json")).read_text("utf-8")
    assert "bytes-ficticios" not in salvo and "Pessoa Exemplo" in salvo
    assert len(chamadas) == 1


@pytest.mark.parametrize("alteracao", [
    {"modelo": "modelo-novo"}, {"instrucao": "Molde novo"},
    {"imagens": ["documento-alterado"]}, {"maximo": 5000}])
def test_alteracao_de_conteudo_modelo_ou_molde_invalida(tmp_path, alteracao):
    chamadas = []
    def ia(*a, **kw):
        chamadas.append(kw)
        return _resposta()
    _ocr(tmp_path, ia)
    _ocr(tmp_path, ia, **alteracao)
    assert len(chamadas) == 2


@pytest.mark.parametrize("resposta", [
    {"texto": "{incompleto"}, {"parou": "max_tokens"}, {"parou": "refusal"},
    {"texto": "{}"}, {"texto": '{"paginas": []}', "triagem": True}])
def test_erro_ou_saida_incompleta_nao_fica_em_cache(tmp_path, resposta):
    triagem = resposta.pop("triagem", False)
    chamadas = []
    def ia(*a, **kw):
        chamadas.append(kw)
        return _resposta(**resposta)
    _ocr(tmp_path, ia, triagem=triagem)
    _ocr(tmp_path, ia, triagem=triagem)
    assert len(chamadas) == 2


def test_cache_corrompido_e_expirado_sao_descartados(tmp_path):
    _ocr(tmp_path, lambda *a, **kw: _resposta())
    arquivo = next((tmp_path / "cache_ia_leituras/v1").glob("*.json"))
    for conteudo in ("quebrado", json.dumps({"quando": time.time() - CACHE.VALIDADE - 1,
                                           "resposta": _resposta()})):
        arquivo.write_text(conteudo, encoding="utf-8")
        r = _ocr(tmp_path, lambda *a, **kw: _resposta())
        assert not r.get("cache")


def test_pedidos_simultaneos_do_mesmo_ocr_pagam_uma_vez(tmp_path):
    chamadas = []
    def ia(*a, **kw):
        chamadas.append(kw)
        time.sleep(0.05)
        return _resposta()
    with ThreadPoolExecutor(max_workers=4) as ex:
        respostas = list(ex.map(lambda _: _ocr(tmp_path, ia), range(4)))
    assert len(chamadas) == 1
    assert sum(r["entrada"] for r in respostas) == 100


def test_falha_de_disco_no_cache_nao_perde_a_resposta_paga(tmp_path, monkeypatch):
    def falhar(*a, **kw):
        raise PermissionError("disco de teste indisponível")
    monkeypatch.setattr(CACHE.os, "replace", falhar)
    r = _ocr(tmp_path, lambda *a, **kw: _resposta())
    assert r["entrada"] == 100 and r["texto"] == _resposta()["texto"]


def test_mesma_imagem_renomeada_reutiliza_ocr_e_preserva_anexo_atual(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "_miniatura", lambda b: b)
    chamadas = []
    def ia(*a, **kw):
        chamadas.append(kw)
        return _resposta(texto=(json.dumps({"paginas": [{"n": 1, "tipo": "OUTRO"}]})
                               if kw["modelo"] == "triador" else _resposta()["texto"]))
    modelos = dict(triagem="triador", impresso="leitor", manuscrito="forte")
    def ler(nome, aid):
        return L.ler_paginas(ia, tmp_path, modelos,
            [dict(arquivo=nome, n=1, attachment_id=aid, imagem=lambda: "mesmos-bytes")],
            tipos={"OUTRO": L.TIPO_OUTRO}, instrucao_triagem="Classifique",
            instrucao_leitura="Leia {nome}: {campos}")
    ler("original.png", 10)
    repetida = ler("renomeado.png", 20)
    assert len(chamadas) == 2  # uma triagem + uma leitura, no total das duas execuções
    assert all(e["cache"] and e["entrada"] == 0 for e in repetida["envios"])
    assert repetida["documentos"][0]["attachment_id"] == 20
    assert repetida["documentos"][0]["arquivo"] == "renomeado.png"


def test_so_repeticao_integral_e_retirada_e_corte_nao_deixa_referencia_sem_teor():
    teor = "Compra e venda fictícia. " * 8
    ato = dict(tipo="R", numero=3, data_ato="2026-11-01", teor=teor)
    ficha = "Descrição do imóvel. " + teor
    item = ato_no_contexto(ato, ficha, RV.normalizar)
    dossie = juntar_contexto([ficha, item, "NOVO ATO"], 10000)
    assert dossie.count(RV.normalizar(teor)) == 1
    assert "R-3 (2026-11-01)" in dossie and "já transcrito" in dossie
    divergente = {**ato, "teor": teor + "Cláusula diferente."}
    assert "Cláusula diferente" in ato_no_contexto(divergente, ficha, RV.normalizar)
    cortado = juntar_contexto([ficha, item, "X" * 150], 300)
    assert "já transcrito" not in cortado
    assert "Compra e venda" in cortado


def test_revisao_estruturada_guarda_consumo_mesmo_se_incompleta(cg_casa, con):
    rid, _ = RV.pedir(con, "RI", 900, "ficticio", "ATO FICTÍCIO", usuario="teste")
    con.commit()
    chamadas = []
    def ia(*a, **kw):
        chamadas.append(kw)
        assert kw["extras"]["output_config"]["format"]["schema"] == RV.ESQUEMA_DA_RESPOSTA
        return _resposta(texto='{"achados": [', parou="max_tokens")
    RV.executar(cg_casa["banco"], cg_casa["dados"], rid, conversar=ia)
    r = banco(con).um("SELECT situacao, erro, tokens_entrada, tokens_saida FROM rv_revisoes WHERE id=%s", (rid,))
    assert r["situacao"] == "ERRO" and "reenvio automático" in r["erro"]
    assert (r["tokens_entrada"], r["tokens_saida"]) == (100, 20)
    assert len(chamadas) == 1


def test_dossies_de_revisao_gestor_e_minuta_preservam_atos_unicos(cg_casa, con):
    import minuta_ia as MI
    bd = banco(con)
    corpo = "R-1: compra e venda fictícia de imóvel urbano. " * 5
    exclusivo = "AV-2: alteração da denominação do logradouro, informada por documento fictício."
    mid = bd.escrever("""INSERT INTO ri_matriculas (numero, teor, criado_em)
        VALUES ('999999', %s, '2026-11-01') RETURNING id""", (corpo,))
    # Banco.escrever devolve cursor conforme adaptador; obtenha pelo número fictício.
    mid = bd.valor("SELECT id FROM ri_matriculas WHERE numero='999999'")
    for n, teor in enumerate((corpo, exclusivo, "R-3: ato alvo fictício."), 1):
        bd.escrever("""INSERT INTO ri_atos
            (matricula_id, tipo, numero, teor, hash_ato, lavrado_em, data_ato)
            VALUES (%s, 'R', %s, %s, %s, '2026-11-01', '2026-11-01')""",
            (mid, n, teor, f"ficticio-{n}"))
    aid = bd.valor("SELECT id FROM ri_atos WHERE matricula_id=%s AND numero=3", (mid,))
    con.commit()
    for dossie in (RV.dossie_ri(con, mid, "R", "Novo ato."),
                   RV.dossie_ri_lavrado(con, aid), MI.contexto_ri(con, mid, "R")):
        assert dossie.count(RV.normalizar(corpo)) == 1
        assert "R-1 (2026-11-01)" in dossie and exclusivo in dossie


class _Rede:
    def __init__(self, modos):
        self.modos, self.posts = iter(modos), 0
    def __call__(self, *a, **kw):
        rede, modo = self, next(self.modos)
        class Conexao:
            def connect(self):
                if modo == "conexao":
                    raise TimeoutError("ficticio")
            def request(self, *a, **kw):
                rede.posts += 1
                if modo == "parcial":
                    raise BrokenPipeError("CONTEUDO-SECRETO")
            def getresponse(self):
                if modo == "prazo":
                    raise TimeoutError("CONTEUDO-SECRETO")
                class Resposta:
                    status = modo
                    def getheader(self, chave):
                        return "req-ficticio"
                    def read(self):
                        return json.dumps({"content": [{"type": "text", "text": "resposta secreta"}],
                            "stop_reason": "end_turn", "model": "modelo-ficticio",
                            "usage": {"input_tokens": 12, "output_tokens": 3}}).encode()
                return Resposta()
            def close(self):
                pass
        return Conexao()


def _turno(tmp_path, monkeypatch, modos):
    rede = _Rede(modos)
    monkeypatch.setattr(AP.http.client, "HTTPSConnection", rede)
    monkeypatch.setattr(AP, "credencial", lambda *a: "chave-ficticia")
    monkeypatch.setattr(AP.time, "sleep", lambda *a: None)
    return rede, lambda: AP._turno(tmp_path, provedor="claude", sistema="s",
        conversa=[{"tipo": "user", "texto": "CONTEUDO-SECRETO"}], ferramentas=[],
        registro={"modulo": "teste", "finalidade": "agente", "referencia": "teste:123"})


@pytest.mark.parametrize("modo", ["prazo", "parcial", 500, 503])
def test_envio_incerto_ou_5xx_nao_reenvia(cg_casa, con, monkeypatch, modo):
    rede, chamar = _turno(cg_casa["dados"], monkeypatch, [modo, 200])
    with pytest.raises(AP.AgenteError) as erro:
        chamar()
    assert erro.value.enviado is True and rede.posts == 1
    linhas = banco(con).ler("SELECT * FROM ia_tentativas WHERE referencia='teste:123'")
    assert len(linhas) == 1 and linhas[0]["estado"] in ("indeterminado", "http_erro")
    salvo = json.dumps([dict(x) for x in linhas], default=str)
    assert "CONTEUDO-SECRETO" not in salvo and "chave-ficticia" not in salvo


@pytest.mark.parametrize("modo,posts", [("conexao", 1), (429, 2)])
def test_so_conexao_sem_envio_ou_429_podem_repetir(cg_casa, con, monkeypatch, modo, posts):
    rede, chamar = _turno(cg_casa["dados"], monkeypatch, [modo, 200])
    r = chamar()
    assert r["tentativas"] == 2 and rede.posts == posts
    linhas = banco(con).ler(
        "SELECT * FROM ia_tentativas WHERE pedido_id=%s ORDER BY tentativa", (r["pedido_id"],))
    assert len(linhas) == 2 and linhas[1]["estado"] == "ok"
    assert linhas[1]["request_id"] == "req-ficticio"
    assert linhas[1]["tokens_entrada"] == 12 and linhas[1]["tokens_saida"] == 3

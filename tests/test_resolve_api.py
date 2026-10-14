"""A API da Intimação Digital (Resolve) — medida contra o contrato dela.

    «a api da cenprot tbm cobre intimacoes pela resolve?»
    «veja aqui: https://docs.resolve.cenprot.org.br/v1110/resolve»
                                            — o oficial, 03/09/2026

**A PERGUNTA DELE SEPAROU DUAS APIS QUE EU TRATAVA COMO UMA.** A «API Cenprot
Cartório» não tem uma única menção a intimação — medido: zero ocorrências de
«intima», «14.711» e «notifica» no `swagger.yaml` v2.1.0. A intimação
eletrônica é outro contrato, e foi ele que o oficial trouxe.

O TESTE QUE MAIS VALE AQUI É O QUE ABRE O CONTRATO
    Na CENPROT, **seis defeitos meus só apareceram quando o teste abriu o
    `swagger.yaml`** — as três convenções de data, os doze campos obrigatórios
    contra os dois que eu conferia, o corpo embrulhado num caminho só. Nenhum
    deles apareceu em duas releituras.

    Por isso aqui o contrato é lido do disco e comparado, campo a campo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED                                     # noqa: E402
import resolve_api as API                                        # noqa: E402

CONTRATO = (RAIZ.parent.parent / "FONTES_EXTERNAS" / "cra21"
            / "resolve_intimacao_openapi_v1.11.0.json")


def _contrato() -> dict:
    if not CONTRATO.exists():
        pytest.skip(f"o contrato não está nesta cópia ({CONTRATO.name})")
    return json.loads(CONTRATO.read_text(encoding="utf-8"))


# ------------------------------------------------ contra o contrato


def test_e_o_contrato_da_intimacao_e_nao_o_da_cenprot():
    """**São duas APIs**, e confundi-las faria procurar intimação onde não há."""
    d = _contrato()
    assert d["info"]["title"] == "Resolve"
    assert d["info"]["version"] == "1.11.0"
    assert "intimações e apontamentos" in d["info"]["description"]


def test_os_dezesseis_caminhos_sao_os_do_contrato():
    """Caminho inventado devolve 404, e o balcão veria «não deu» sem saber que
    o endereço é que estava errado."""
    d = _contrato()
    do_contrato = set(d["paths"])
    do_modulo = set(API.CAMINHO.values())
    assert do_modulo == do_contrato, (
        f"sobrando no módulo: {sorted(do_modulo - do_contrato)}; "
        f"faltando: {sorted(do_contrato - do_modulo)}")
    assert len(API.CAMINHO) == 16


def test_os_tres_ambientes_sao_os_do_contrato():
    """**São TRÊS, e não dois** — esta é a primeira Central da casa com um
    ambiente de testes declarado."""
    d = _contrato()
    do_contrato = [s["url"] for s in d["servers"]]
    assert sorted(API.BASE_DO_AMBIENTE.values()) == sorted(do_contrato)
    assert set(API.BASE_DO_AMBIENTE) == {
        CRED.TESTES, CRED.HOMOLOGACAO, CRED.PRODUCAO}


def test_todas_as_bases_sao_https():
    """A chave viaja nesta conexão; em texto puro, quem está na rede a lê — e
    com ela manda intimação em nome desta serventia."""
    for base in API.BASE_DO_AMBIENTE.values():
        assert base.startswith("https://")


def test_a_autenticacao_e_a_chave_no_cabecalho():
    """O contrato declara três esquemas e **as operações usam o terceiro**.
    Guardar um par faria a tela pedir um usuário que a Central não dá."""
    d = _contrato()
    esquemas = d["components"]["securitySchemes"]
    assert esquemas["apiKeyAuth"] == {
        "type": "apiKey", "in": "header", "name": "x-api-key"}
    assert CRED.FORMA_DA_CENTRAL[CRED.RESOLVE] == CRED.TOKEN


def test_os_obrigatorios_do_lote_sao_os_do_contrato():
    """**O 400 dela é mudo** — «Dados inválidos. Verifique o payload enviado»,
    sem dizer qual item nem qual campo. Conferir aqui é o que dá ao balcão uma
    frase com o número do item."""
    d = _contrato()
    item = (d["paths"]["/api/batches/json"]["post"]["requestBody"]
            ["content"]["application/json"]["schema"]["items"])
    assert set(API.OBRIGATORIOS_DA_INTIMACAO) == set(item["required"])
    assert ({c for c, _ in API.OBRIGATORIOS_DO_TITULO}
            == set(item["properties"]["titulo"]["required"]))
    assert ({c for c, _ in API.OBRIGATORIOS_DO_DEVEDOR}
            == set(item["properties"]["devedor"]["required"]))


def test_o_endereco_e_obrigatorio_no_DEVEDOR_e_so_nele():
    """Credor, cedente e apresentante exigem nome e documento; o devedor exige
    endereço também — e faz sentido: é a ele que a intimação vai."""
    d = _contrato()
    props = (d["paths"]["/api/batches/json"]["post"]["requestBody"]
             ["content"]["application/json"]["schema"]["items"]["properties"])
    assert "enderecos" in props["devedor"]["required"]
    for outro in ("credor", "cedente", "apresentante"):
        assert "enderecos" not in props[outro].get("required", [])


def test_os_limites_sao_os_do_contrato():
    d = _contrato()
    sch = (d["paths"]["/api/batches/json"]["post"]["requestBody"]
           ["content"]["application/json"]["schema"])
    assert API.MAXIMO_DO_LOTE == sch["maxItems"] == 2000
    assert API.MINIMO_DO_LOTE == sch["minItems"] == 1

    pagina = [p for p in d["paths"]["/api/intimations"]["get"]["parameters"]
              if p["name"] == "length"][0]
    assert API.MAXIMO_POR_PAGINA == pagina["schema"]["maximum"] == 100


def test_os_doze_estados_sao_os_do_contrato():
    d = _contrato()
    enum = [p for p in d["paths"]["/api/intimations"]["get"]["parameters"]
            if p["name"] == "status"][0]["schema"]["enum"]
    assert list(API.ESTADOS) == enum
    assert len(API.ESTADOS) == 12


def test_a_chave_unica_tem_23_e_o_contrato_diz_isso():
    d = _contrato()
    nr = (d["paths"]["/api/batches/json"]["post"]["requestBody"]
          ["content"]["application/json"]["schema"]["items"]["properties"]
          ["titulo"]["properties"]["nrChave"])
    assert "23" in nr["description"]
    assert API.TAMANHO_DA_CHAVE == 23


def test_TRES_caminhos_nao_declaram_a_chave_e_isso_e_do_contrato():
    """**Achado do contrato, e não do módulo** — apareceu quando este teste
    afirmou que só o `/api/status` dispensava a chave.

    Três operações não trazem `x-api-key` nem `security`:
    `/api/status`, `/api/reports` e `/api/simulate/message-webhook`. **Do
    status é verdade** — ele respondeu `200 OK` nos três ambientes sem
    credencial nenhuma, medido em 03/09/2026. Dos outros dois é quase certo que
    não: relatório de pagamentos do cartório não é público.

    É o mesmo caso da ONRTDPJ, cujo contrato «declara o esquema de segurança e
    não o aplica a operação nenhuma». **O módulo manda a chave nos dois**, que
    é o seguro: mandar onde não precisa não quebra nada; não mandar onde
    precisa devolve 401 sem dizer por quê.

    Se um dia declararem, este teste fica vermelho — e aí a lista encolhe.
    """
    d = _contrato()
    sem_chave = []
    for caminho, ops in d["paths"].items():
        for op in ops.values():
            nomes = {p["name"] for p in op.get("parameters", [])}
            if "x-api-key" not in nomes and not op.get("security"):
                sem_chave.append(caminho)
    assert sorted(sem_chave) == ["/api/reports", "/api/simulate/message-webhook",
                                 "/api/status"]


def test_so_o_status_e_chamado_SEM_a_chave():
    """A outra metade: o módulo manda a chave em tudo menos no status."""
    import inspect

    assert "com_chave=False" in inspect.getsource(API.status)
    assert "com_chave=False" not in inspect.getsource(API.relatorio)


# ------------------------------------------------ o que o módulo recusa


def test_caminho_que_escreve_tem_de_estar_declarado():
    """A guarda que impede uma função nova de mandar coisa para a Central sem
    ninguém ter declarado que ela muda estado lá."""
    with pytest.raises(API.ResolveError) as erro:
        API._escrever(CRED.TESTES, "intimacoes", "isto não devia passar")
    assert "engano de programação" in str(erro.value)


def test_todo_caminho_que_escreve_existe_no_contrato():
    d = _contrato()
    for chave in API.CAMINHOS_QUE_ESCREVEM:
        assert API.CAMINHO[chave] in d["paths"]


def test_os_gets_nao_estao_entre_os_que_escrevem():
    """Um `GET` na lista faria a guarda perder o sentido."""
    d = _contrato()
    for chave, caminho in API.CAMINHO.items():
        metodos = set(d["paths"][caminho])
        if metodos == {"get"}:
            assert chave not in API.CAMINHOS_QUE_ESCREVEM, chave


def test_lote_vazio_e_recusado():
    with pytest.raises(API.ResolveError) as erro:
        API.conferir_lote([])
    assert "nenhuma" in str(erro.value).lower()


def test_lote_acima_do_teto_e_recusado_antes_da_rede():
    um = {"credor": {"nome": "C", "documento": "45315321000113"},
          "devedor": {"nome": "D", "documento": "1",
                      "enderecos": [{"endereco": "R", "cep": "1",
                                     "cidade": "c", "uf": "MA"}]},
          "titulo": {"valorDivida": 1, "valorTitulo": 1, "valorAPagar": 1,
                     "numeroTitulo": "1", "especieTitulo": "DM",
                     "dataVencimento": "2026-01-01",
                     "nrChave": "1" * 23}}
    with pytest.raises(API.ResolveError) as erro:
        API.conferir_lote([um] * (API.MAXIMO_DO_LOTE + 1))
    assert "2000" in str(erro.value)
    assert "partes" in str(erro.value)


def test_a_recusa_diz_QUAL_item_do_lote_falhou():
    """Com dois mil itens, «dados inválidos» não ajuda ninguém."""
    bom = {"credor": {"nome": "C", "documento": "45315321000113"},
           "devedor": {"nome": "D", "documento": "1",
                       "enderecos": [{"endereco": "R", "cep": "1",
                                      "cidade": "c", "uf": "MA"}]},
           "titulo": {"valorDivida": 1, "valorTitulo": 1, "valorAPagar": 1,
                      "numeroTitulo": "1", "especieTitulo": "DM",
                      "dataVencimento": "2026-01-01", "nrChave": "1" * 23}}
    ruim = {**bom, "devedor": {"nome": "D", "documento": "1"}}
    with pytest.raises(API.ResolveError) as erro:
        API.conferir_lote([bom, ruim])
    assert "intimação 2" in str(erro.value)
    assert "endereço" in str(erro.value)


def test_chave_de_tamanho_errado_e_recusada_dizendo_de_onde_ela_vem():
    """**A chave não se inventa**: vem do XML diário do CENPROT, e a mensagem
    diz qual tela a grava."""
    item = {"credor": {"nome": "C", "documento": "45315321000113"},
            "devedor": {"nome": "D", "documento": "1",
                        "enderecos": [{"endereco": "R", "cep": "1",
                                       "cidade": "c", "uf": "MA"}]},
            "titulo": {"valorDivida": 1, "valorTitulo": 1, "valorAPagar": 1,
                       "numeroTitulo": "1", "especieTitulo": "DM",
                       "dataVencimento": "2026-01-01", "nrChave": "123"}}
    with pytest.raises(API.ResolveError) as erro:
        API.conferir_lote([item])
    assert "23" in str(erro.value)
    assert "CENPROT" in str(erro.value)


def test_estado_desconhecido_e_recusado():
    with pytest.raises(API.ResolveError) as erro:
        API.intimacoes(CRED.TESTES, estado="INVENTADO")
    assert "INVENTADO" in str(erro.value)


def test_pagina_acima_do_maximo_e_recusada():
    with pytest.raises(API.ResolveError) as erro:
        API.intimacoes(CRED.TESTES, quantas=500)
    assert "100" in str(erro.value)


def test_o_historico_exige_as_duas_datas():
    """O contrato as marca obrigatórias; sem elas a Central responde 400."""
    with pytest.raises(API.ResolveError):
        API.historico("", "2026-01-31")
    with pytest.raises(API.ResolveError):
        API.historico("2026-01-01", "")


def test_base_http_e_recusada():
    """Forçar https não é preciosismo: a chave viaja no cabeçalho."""
    with pytest.raises(API.ResolveError) as erro:
        API._partes("http://api.resolve.cenprot.org.br/intimacao")
    assert "https" in str(erro.value)


def test_sem_credencial_a_frase_diz_onde_cadastrar():
    """Erro de regra não é HTTP 500, e a frase tem de dizer o que fazer."""
    import tempfile

    with pytest.raises(API.ResolveError) as erro:
        API.chave(CRED.TESTES, pasta=tempfile.mkdtemp())
    assert "Configurações" in str(erro.value)
    assert "adesão" in str(erro.value).lower()


def test_o_ambiente_padrao_e_homologacao():
    """**Começar na produção por omissão** é o que esta escolha evita."""
    assert API._ambiente(None) == CRED.HOMOLOGACAO
    assert API._ambiente("") == CRED.HOMOLOGACAO
    assert API._ambiente(CRED.TESTES) == CRED.TESTES


def test_o_diagnostico_nao_usa_o_status_que_dispensa_chave():
    """O `/api/status` responde sem chave: usá-lo como teste de credencial
    passaria com a chave errada — **teste que sempre passa não testa nada**."""
    import inspect

    fonte = inspect.getsource(API.diagnostico)
    assert "intimacoes(" in fonte
    assert 'CAMINHO["status"]' not in fonte

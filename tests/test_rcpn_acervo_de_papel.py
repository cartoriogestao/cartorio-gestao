"""Assento já lavrado no livro de papel: livro, folha e termo, sem lavrar.

A tela «Digitar … já lavrado» gravava origem ACERVO e passava por
`lavrar_assento`, que consumia a numeração da casa. Agora grava o que foi
digitado, com origem ARQUIVO, sem ato e sem selo.
"""
from __future__ import annotations

import re

import pytest
from bd_nativo import banco

import rc_assento as RC

SENHA = "Senha#12345"


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)[1]


def _numeracao(casa):
    with casa["db"].connect() as c:
        bd = banco(c)
        nums = tuple((r["serie"], r["proximo"]) for r in bd.ler(
            "SELECT serie, proximo FROM nu_numeracao ORDER BY serie"))
        folhas = tuple((r["id"], r["folha_atual"]) for r in bd.ler(
            "SELECT id, folha_atual FROM nu_livros ORDER BY id"))
        atos = bd.valor("SELECT count(*) FROM rc_atos")
    return nums, folhas, atos


def _post(client, especie, **campos):
    html = client.get(f"/rcpn/novo/{especie}?do_acervo=1").get_data(as_text=True)
    data = {
        "csrf_token": _token(html),
        "do_acervo": "1",
        "acao": "incluir_papel",
        "livro_papel": campos.pop("livro"),
        "folha_papel": campos.pop("folha"),
        "termo_papel": campos.pop("termo"),
    }
    data.update(campos)
    return client.post(f"/rcpn/novo/{especie}?do_acervo=1", data=data,
                       follow_redirects=True)


def test_as_tres_telas_pedem_livro_folha_e_termo(cg_casa_logada):
    c = cg_casa_logada["c"]
    for especie, letra in (("nascimento", "A-12"), ("casamento", "B-3"), ("obito", "C-3")):
        html = c.get(f"/rcpn/novo/{especie}?do_acervo=1").get_data(as_text=True)
        assert "Incluir assento do papel" in html
        assert 'name="livro_papel"' in html
        assert 'name="folha_papel"' in html
        assert 'name="termo_papel"' in html
        assert "48 ou 48v" in html
        assert "saem da lavratura" not in html
        assert "não pede selo" in html or "não há selo" in html or "Não lavra" in html
        assert letra.split("-")[0] in html or especie == "nascimento"


@pytest.mark.parametrize("especie,livro,folha,termo,extras", [
    ("nascimento", "12", "48v", "7", {
        "pessoa_nome": "PESSOA EXEMPLO",
        "naturalidade_declarada": "Cidade Exemplo/MA",
        "registro_tardio": "1",
        "data_ato": "1991-04-02",
    }),
    ("casamento", "B-4", "48", "15", {
        "nubente1_nome": "PESSOA EXEMPLO UM",
        "nubente2_nome": "PESSOA EXEMPLO DOIS",
        "nubente1_naturalidade_cidade": "Cidade Exemplo",
        "nubente1_naturalidade_uf": "MA",
    }),
    ("obito", "3", "048V", "9", {
        "pessoa_nome": "PESSOA EXEMPLO",
        "pessoa_naturalidade_cidade": "Cidade Exemplo",
        "pessoa_naturalidade_uf": "MA",
    }),
])
def test_grava_o_papel_sem_lavrar_nem_andar_a_numeracao(
        cg_casa_logada, monkeypatch, especie, livro, folha, termo, extras):
    def boom(*_a, **_k):
        raise AssertionError("a inclusão do papel não pode lavrar")

    monkeypatch.setattr(RC, "lavrar_assento", boom)
    casa = cg_casa_logada
    antes = _numeracao(casa)
    r = _post(casa["c"], especie, livro=livro, folha=folha, termo=termo, **extras)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Assento do livro de papel incluído" in html
    assert "Assento lavrado no Livro" not in html
    assert _numeracao(casa) == antes
    with casa["db"].connect() as c:
        bd = banco(c)
        a = bd.um("SELECT * FROM rc_assentos ORDER BY id DESC LIMIT 1")
        assert a["origem"] == "ARQUIVO"
        assert a["especie"] == especie.upper()
        assert a["numero"] == int(termo)
        assert json_folha(a) == ("48v" if "v" in folha.lower() else "48")
        assert bd.valor("SELECT count(*) FROM rc_atos WHERE assento_id=%s", (a["id"],)) == 0
        aud = bd.um(
            "SELECT username_snapshot FROM audit_logs "
            "WHERE action='RCPN_ACERVO_PAPEL' AND entity_id=%s", (a["id"],))
        assert aud["username_snapshot"] == "MARIO EXEMPLO DOS SANTOS"
        if especie == "nascimento":
            assert a["livro_volume"] == "A-12"
            assert a["registro_tardio"] == 1
            assert a["data_ato"] == "1991-04-02"
            pessoa = bd.um(
                "SELECT naturalidade_cidade, naturalidade_uf FROM rc_pessoas "
                "WHERE assento_id=%s AND papel='REGISTRADO'", (a["id"],))
            assert pessoa["naturalidade_cidade"] == "Cidade Exemplo"
            assert pessoa["naturalidade_uf"] == "MA"
        elif especie == "casamento":
            assert a["livro_volume"] == "B-4"
            nubente = bd.um(
                "SELECT naturalidade_cidade FROM rc_pessoas "
                "WHERE assento_id=%s AND papel='NUBENTE1'", (a["id"],))
            assert nubente["naturalidade_cidade"] == "Cidade Exemplo"
        else:
            assert a["livro_volume"] == "C-3"
            assert json_folha(a) == "48v"
    assert json_folha_na_ficha(html)


def json_folha(assento) -> str:
    import json
    return json.loads(assento["dados_json"])["folha"]


def json_folha_na_ficha(html: str) -> bool:
    assert "48" in html
    return True


def test_recusa_livro_e_termo_repetidos_na_mesma_especie(cg_casa_logada):
    casa = cg_casa_logada
    antes = _numeracao(casa)
    primeiro = _post(casa["c"], "nascimento", livro="A-12", folha="48", termo="7",
                     pessoa_nome="PESSOA EXEMPLO")
    assert "incluído" in primeiro.get_data(as_text=True)
    repetido = _post(casa["c"], "nascimento", livro="12", folha="49v", termo="007",
                     pessoa_nome="OUTRA PESSOA EXEMPLO")
    html = repetido.get_data(as_text=True)
    assert "Já existe um assento de nascimento no Livro A-12, termo 7" in html
    assert "Nada foi incluído" in html
    with casa["db"].connect() as c:
        assert banco(c).valor(
            "SELECT count(*) FROM rc_assentos WHERE especie='NASCIMENTO'") == 1
    # Outra espécie pode usar o mesmo número de termo: o livro é outro.
    obito = _post(casa["c"], "obito", livro="12", folha="48", termo="7",
                  pessoa_nome="PESSOA EXEMPLO")
    assert "incluído" in obito.get_data(as_text=True)
    assert _numeracao(casa) == antes


def test_folha_e_livro_invalidos_nao_gravam(cg_casa_logada):
    casa = cg_casa_logada
    html = _post(casa["c"], "nascimento", livro="B-1", folha="48", termo="1",
                 pessoa_nome="PESSOA EXEMPLO").get_data(as_text=True)
    assert "livro do papel" in html
    html = _post(casa["c"], "nascimento", livro="2", folha="48x", termo="1",
                 pessoa_nome="PESSOA EXEMPLO").get_data(as_text=True)
    assert "48 ou 48v" in html
    with casa["db"].connect() as c:
        assert banco(c).valor("SELECT count(*) FROM rc_assentos") == 0


def test_robo_inclui_sem_selar_e_a_auditoria_fica_no_responsavel(cg_casa_logada):
    from conftest import cg_login
    casa = cg_casa_logada
    casa["db"].create_user("laura", "LAURA RESPONSAVEL", SENHA, "MANAGER")
    casa["db"].create_user("robo_papel", "Robo Papel RCPN", SENHA, "USER", eh_robo=1)
    with casa["db"].transaction() as c:
        bd = banco(c)
        rid = bd.valor("SELECT id FROM users WHERE username='laura'")
        bd.escrever(
            "UPDATE users SET robo_responsavel_id=%s WHERE username='robo_papel'",
            (rid,))
    antes = _numeracao(casa)
    client = casa["app"].test_client()
    cg_login(client, "robo_papel", SENHA)
    r = _post(client, "nascimento", livro="8", folha="48v", termo="3",
              pessoa_nome="PESSOA EXEMPLO")
    assert r.status_code == 200
    assert "incluído" in r.get_data(as_text=True)
    assert _numeracao(casa) == antes
    with casa["db"].connect() as c:
        bd = banco(c)
        a = bd.um("SELECT id, origem FROM rc_assentos ORDER BY id DESC LIMIT 1")
        assert a["origem"] == "ARQUIVO"
        assert bd.valor("SELECT count(*) FROM rc_atos WHERE assento_id=%s", (a["id"],)) == 0
        aud = bd.um(
            "SELECT username_snapshot FROM audit_logs "
            "WHERE action='RCPN_ACERVO_PAPEL' AND entity_id=%s", (a["id"],))
        assert aud["username_snapshot"] == "LAURA RESPONSAVEL"
        assert "PENDENTE" not in aud["username_snapshot"]

"""Os lotes do Indicador Real, com o sistema de pé e banco de teste.

O risco que estes testes defendem: o acervo ou a regra da casa entrarem sem ninguém marcar, a mesma
matrícula sair em dois lotes vivos, ou alguma coisa contar como entregue antes do «Importado».
"""
from __future__ import annotations

import json

import pytest

import onr_ir_json as J
import onr_ir_lotes as L
from bd_nativo import banco

CONFIG = {"ri_cns": "000000", "ri_uf": "SP", "ri_cidade": "Cidade Exemplo", "ibge_uf": "35", "ibge_municipio": "00001"}
ROTA = "/registro-imoveis/onr/indicador-real/lotes"


def _ficha(con, numero, **mudar):
    campos = {"numero": str(numero), "livro": "2", "livro_norm": "2", "tipo_ficha": "ESTRUTURADA", "situacao": "ATIVA",
              "rural_urbano": "U", "tipo_imovel": "Casa", "logradouro": "Rua das Flores", "numero_predial": "10",
              "bairro": "Centro", "cidade": "Cidade Exemplo", "uf": "SP", "cep": "01234567", "teor": "", "encerrada": 0,
              "origem": "TESTE", "criado_em": "2026-01-01 10:00:00"}
    campos.update(mudar)
    nomes = ", ".join(campos)
    marcas = ", ".join(["%s"] * len(campos))
    return banco(con).valor(f"INSERT INTO ri_matriculas ({nomes}) VALUES ({marcas}) RETURNING id", list(campos.values()))


@pytest.fixture
def casa(cg_casa_logada):
    db = cg_casa_logada["db"]
    db.set_settings(CONFIG)
    return cg_casa_logada


def _filtros(**mudar):
    base = {"limite": "200"}
    classes = mudar.pop("classes", None)
    base.update(mudar)
    return L.filtros_de(base, classes)


def _conferir(db, **mudar):
    with db.connect() as con:
        return L.conferir(con, settings=CONFIG, filtros=_filtros(**mudar))


def _gerar(db, **mudar):
    with db.transaction() as con:
        return L.gerar(con, settings=CONFIG, filtros=_filtros(**mudar), por="teste", agora="2026-11-23 10:00:00")


def _semear(db, *numeros, **mudar):
    with db.transaction() as con:
        return [_ficha(con, n, **mudar) for n in numeros]


def test_o_acervo_fica_de_fora_ate_marcar(casa):
    db = casa["db"]
    _semear(db, 11, tipo_ficha="ACERVO")
    fechado = _conferir(db)
    assert not fechado["vao"] and fechado["acervo_de_fora"] == 1
    assert "acervo" in fechado["recusadas"][0]["motivos"][0]
    assert [x["numero"] for x in _conferir(db, incluir_acervo="1")["vao"]] == ["11"]


def test_a_regra_da_casa_nao_entra_sem_a_opcao(casa):
    db = casa["db"]
    _semear(db, 12, tipo_imovel="", numero_predial="", bairro="", cep="",
            teor="IMÓVEL: um terreno urbano situado na Rua das Flores, nesta cidade de Cidade Exemplo.")
    fechado = _conferir(db, classes=[L.PRONTA, L.TEOR])
    assert fechado["por_classe"][L.REGRA] == 1 and not fechado["vao"]
    assert "regra da casa" in fechado["recusadas"][0]["motivos"][0]
    with pytest.raises(L.LoteError):
        _filtros(classes=[L.REGRA])
    aberto = _conferir(db, classes=[L.REGRA], aceitar_regra="1")
    assert [x["numero"] for x in aberto["vao"]] == ["12"]


def test_a_ficha_que_diz_tudo_e_pronta_e_a_incoerente_nao(casa):
    db = casa["db"]
    _semear(db, 13)
    _semear(db, 14, situacao="ENCERRADA")
    _semear(db, 15, teor="<p>A matrícula supra foi unificada com outra.</p>")
    r = _conferir(db)
    assert [x["numero"] for x in r["vao"]] == ["13"]
    assert {x["numero"]: x["classe"] for x in r["recusadas"]} == {"14": L.PESSOA, "15": L.PESSOA}


def test_numero_zero_e_cep_geral_gravados_na_ficha_so_saem_com_a_regra(casa):
    db = casa["db"]
    config = {**CONFIG, "onr_ceps_por_cidade": "Cidade Exemplo=01234567"}
    db.set_settings(config)
    _semear(db, 16, numero_predial="000", complemento_endereco="00", teor="Situado na Rua das Flores, Centro.")
    with db.connect() as con:
        sem = L.conferir(con, settings=config, filtros=_filtros())["vao"][0]["registro"]
        com = L.conferir(con, settings=config, filtros=_filtros(aceitar_regra="1"))["vao"][0]["registro"]
    assert (sem["NUMERO_LOGRADOURO"], sem["CEP"], sem["COMPLEMENTO"]) == ("", "", "")
    assert (com["NUMERO_LOGRADOURO"], com["CEP"]) == ("000", "01234567")


def test_logradouro_que_o_teor_nao_confirma_vai_para_pessoa(casa):
    db = casa["db"]
    _semear(db, 17, teor="Um terreno situado na Praça da Matriz, nesta cidade.")
    r = _conferir(db)
    assert not r["vao"] and r["por_classe"][L.PESSOA] == 1
    assert "não aparece no teor" in r["recusadas"][0]["motivos"][0]


def test_ficha_marcada_como_condominio_nao_vira_matricula_comum(casa):
    db = casa["db"]
    _semear(db, 18, complemento="CONDOMINIO")
    r = _conferir(db)
    assert not r["vao"] and "matrícula-mãe" in r["recusadas"][0]["motivos"][0]


def test_faixa_e_tamanho_do_lote(casa):
    db = casa["db"]
    _semear(db, 21, 22, 23, 24)
    r = _conferir(db, de="22", ate="24", limite="2")
    assert [x["numero"] for x in r["vao"]] == ["22", "23"] and r["para_o_proximo"] == 1
    for ruim in ({"de": "9", "ate": "1"}, {"de": "abc"}, {"limite": "0"}, {"limite": str(L.LOTE_MAXIMO + 1)}):
        with pytest.raises(L.LoteError):
            _filtros(**ruim)


def test_gerar_guarda_hash_itens_e_recusadas(casa):
    db = casa["db"]
    _semear(db, 31, 32)
    _semear(db, 33, tipo_ficha="ACERVO")
    feito = _gerar(db)
    with db.connect() as con:
        nome, conteudo = L.arquivo_do_lote(con, feito["id"])
        itens = banco(con).ler("SELECT numero FROM onr_ir_lote_itens WHERE lote_id=%s ORDER BY numero", (feito["id"],))
        _csv, csv_bytes = L.recusadas_csv(con, feito["id"])
        assert L.entregues(con) == 0
    assert nome == feito["arquivo"] and J.sha256(conteudo) == feito["sha256"]
    assert [r["NUMERO_REGISTRO"] for r in json.loads(conteudo)["INDICADOR_REAL"]["REAL"]] == ["31", "32"]
    assert [x["numero"] for x in itens] == ["31", "32"]
    assert "33" in csv_bytes.decode("utf-8-sig")


def test_arquivo_adulterado_nao_sai(casa):
    db = casa["db"]
    _semear(db, 34)
    feito = _gerar(db)
    with db.transaction() as con:
        banco(con).escrever("UPDATE onr_ir_lotes SET conteudo = conteudo || ' ' WHERE id=%s", (feito["id"],))
    with db.connect() as con, pytest.raises(L.LoteError):
        L.arquivo_do_lote(con, feito["id"])


def test_a_mesma_matricula_nao_sai_em_dois_lotes_vivos(casa):
    db = casa["db"]
    _semear(db, 41)
    primeiro = _gerar(db)
    assert not _conferir(db)["vao"]
    with pytest.raises(L.LoteError):
        _gerar(db)
    with db.transaction() as con:
        L.registrar_resultado(con, primeiro["id"], L.NAO_IMPORTADO, visto_em="2026-11-23", observacao="",
                              por="teste", agora="2026-11-23 11:00:00")
    assert [x["numero"] for x in _conferir(db)["vao"]] == ["41"]


def test_so_importado_conta_como_entregue(casa):
    db = casa["db"]
    _semear(db, 51, 52)
    feito = _gerar(db)

    def mudar(para, **kw):
        with db.transaction() as con:
            L.registrar_resultado(con, feito["id"], para, visto_em=kw.get("visto_em", "2026-11-23"),
                                  observacao=kw.get("observacao", ""), por="teste", agora="2026-11-23 12:00:00")

    def contagem():
        with db.connect() as con:
            return L.entregues(con)

    assert contagem() == 0
    mudar(L.PROCESSANDO)
    assert contagem() == 0
    with pytest.raises(L.LoteError):
        mudar(L.IMPORTADO, visto_em="")
    with pytest.raises(L.LoteError):
        mudar(L.IMPORTADO, visto_em="2026-11-24")
    with pytest.raises(L.LoteError):
        mudar(L.GERADO)
    mudar(L.IMPORTADO)
    assert contagem() == 2
    with pytest.raises(L.LoteError):
        mudar(L.NAO_IMPORTADO)
    mudar(L.NAO_IMPORTADO, observacao="O portal voltou atrás na importação.")
    assert contagem() == 0


def test_descartar_exige_motivo_e_libera_a_matricula(casa):
    db = casa["db"]
    _semear(db, 61)
    feito = _gerar(db)
    with db.transaction() as con, pytest.raises(L.LoteError):
        L.registrar_resultado(con, feito["id"], L.DESCARTADO, visto_em="", observacao="", por="t", agora="2026-11-23 12:00:00")
    with db.transaction() as con:
        L.registrar_resultado(con, feito["id"], L.DESCARTADO, visto_em="", observacao="Gerado com a faixa errada.",
                              por="t", agora="2026-11-23 12:00:00")
    assert [x["numero"] for x in _conferir(db)["vao"]] == ["61"]


def test_gerar_nao_muda_a_ficha(casa):
    db = casa["db"]
    [mid] = _semear(db, 71)
    with db.connect() as con:
        antes = dict(banco(con).um("SELECT * FROM ri_matriculas WHERE id=%s", (mid,)))
    _gerar(db)
    with db.connect() as con:
        assert dict(banco(con).um("SELECT * FROM ri_matriculas WHERE id=%s", (mid,))) == antes


def test_a_tela_do_admin_confere_gera_e_registra(casa):
    db, c = casa["db"], casa["c"]
    _semear(db, 81)
    assert c.get(ROTA).status_code == 200
    token = casa.get("csrf") or _token(c)
    dados = {"csrf_token": token, "classes": "PRONTA", "limite": "200"}
    r = c.post(f"{ROTA}/conferir", data=dados)
    assert r.status_code == 200 and "vão no arquivo" in r.get_data(as_text=True)
    with db.connect() as con:
        assert L.lotes(con) == []
    assert c.post(f"{ROTA}/gerar", data=dados).status_code == 302
    with db.connect() as con:
        lote = L.lotes(con)[0]
    baixado = c.get(f"{ROTA}/{lote['id']}/arquivo")
    assert baixado.status_code == 200 and J.sha256(baixado.data) == lote["sha256"]
    assert c.get(f"{ROTA}/{lote['id']}/recusadas.csv").status_code == 200
    assert c.post(f"{ROTA}/{lote['id']}/resultado", data={
        "csrf_token": token, "situacao": L.PROCESSANDO, "visto_em": "2026-11-23"}).status_code == 302
    with db.connect() as con:
        assert L.lotes(con)[0]["situacao"] == L.PROCESSANDO and L.entregues(con) == 0


def _token(c) -> str:
    import re
    pagina = c.get(ROTA).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)


@pytest.mark.parametrize("papel", ["MANAGER", "USER", "AUDITOR"])
def test_so_o_admin_entra(cg_casa, papel):
    from conftest import cg_login
    cg_casa["db"].create_user("outra", "PESSOA DE TESTE", "Senha#12345", papel)
    cg_login(cg_casa["c"], "outra", "Senha#12345")
    assert cg_casa["c"].get(ROTA).status_code in (302, 403)

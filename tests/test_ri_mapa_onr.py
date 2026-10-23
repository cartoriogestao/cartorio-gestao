"""A base do Mapa do Registro de Imóveis do ONR — `ri_mapa_onr.py`.

O QUE ESTES TESTES PROTEGEM:

    a área em hectares      a ficha guarda TEXTO, em ha ou em m², e a régua da
                            casa é quem o lê; o que ela não sabe ler vai vazio,
                            e não inventado

    o dono de hoje          `proprietario_ativo`, e não `proprietario` — e
                            quem tem vários, juntos

    a encerrada fora        pelas duas marcas, e a reaberta (`'ATIVO'`) dentro

    a VIEW e o CSV iguais   os dois saem da mesma regra; a área da VIEW vem do
                            de-para, que atrasa (vazia) mas não erra

    só ADMIN baixa          o CSV leva o nome dos proprietários

Dados fictícios. Nenhum teste daqui fala com o ONR nem abre o QGIS.
"""
from __future__ import annotations

import csv
import hashlib
import io
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_mapa_onr as MAPA
from bd_nativo import banco
from conftest import cg_login

SENHA = "Senha#12345"
AGORA = "2026-10-19T10:00:00"


@pytest.fixture()
def db(cg_casa):
    cg_casa["db"].set_settings({"ri_cns": "000000"})
    return cg_casa["db"]


def _matricula(db, numero, **campos) -> int:
    base = {"numero": str(numero), "livro": "2", "livro_norm": "2",
            "tipo_ficha": "ESTRUTURADA", "criado_em": AGORA}
    base.update(campos)
    colunas = ", ".join(base)
    marcas = ", ".join(["%s"] * len(base))
    with db.transaction() as con:
        return banco(con).escrever(
            f"INSERT INTO ri_matriculas ({colunas}) VALUES ({marcas}) RETURNING id",
            tuple(base.values()))[0]["id"]


def _parte(db, matricula_id, nome, *, ativo=1, proprietario=1) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO ri_partes (matricula_id, nome, proprietario,
                                      proprietario_ativo)
               VALUES (%s, %s, %s, %s)""",
            (matricula_id, nome, proprietario, ativo))


def _mapa(db, matriculas=None) -> list[dict]:
    with db.connect() as con:
        return MAPA.dados_do_mapa(con, matriculas)


def _view(db, onde: str = "", parametros=None) -> list[dict]:
    with db.connect() as con:
        return banco(con).ler(
            f"SELECT * FROM onr_mapa_imoveis {onde} ORDER BY matricula",
            parametros)


def _subida(db) -> None:
    """O que a subida do sistema faz com o de-para (`init_mapa_onr_schema`)."""
    with db.transaction() as con:
        MAPA.init_mapa_onr_schema(con)


# ------------------------------------------------------------- a área


@pytest.mark.parametrize("valor, unidade, hectares", [
    ("360", "m2", 0.036),             # o lote urbano, em metro
    ("8.435,26", "m2", 0.8435),       # a vírgula é o decimal, o ponto o milhar
    ("63", "ha", 63.0),               # hectare redondo, como a casa escreve
    ("231,0233", "ha", 231.0233),
    ("231,00,00", "ha", 231.0),       # hectares, ares e centiares
    ("19,3419 ha (dezenove hectares, trinta e quatro ares e dezenove centiares)",
     "ha", 19.3419),
])
def test_a_area_registrada_vai_em_hectares(db, valor, unidade, hectares):
    _matricula(db, 4015, area_valor=valor, area_unidade=unidade)
    assert _mapa(db) == [{"matricula": "4015", "cns": "000000",
                          "proprietario": "", "area_ha": hectares}]


def test_area_que_a_regua_nao_sabe_ler_vai_vazia_e_nao_inventada(db):
    """`3808` em hectare tanto é 38,08 ha quanto 3.808 m² — chutar erra por
    cem vezes. Vazia, o plugin calcula a geodésica, que é a que o ONR pede."""
    _matricula(db, 4015, area_valor="3808", area_unidade="ha")
    _matricula(db, 4016)                       # ficha sem área nenhuma
    assert [r["area_ha"] for r in _mapa(db)] == [None, None]


def test_area_zero_vai_vazia_porque_zero_nao_e_area(db):
    """A régua lê `"0"` em hectare como 0 m²; no mapa, seria a afirmação de
    que o imóvel não tem área. No CSV e na VIEW, vazia."""
    _matricula(db, 4015, area_valor="0", area_unidade="ha")
    _matricula(db, 4016, area_valor="0,00", area_unidade="m2")
    _subida(db)
    assert [r["area_ha"] for r in _mapa(db)] == [None, None]
    assert [r["area_ha"] for r in _view(db)] == [None, None]


# ------------------------------------------------------- quem fica de fora


def test_matricula_encerrada_fica_fora_do_mapa_pelas_duas_marcas(db):
    """`encerrada = 1` ou `situacao = 'ENCERRADA'`: a casa grava as duas
    juntas, mas uma ficha com só uma delas também está fechada."""
    _matricula(db, 4015)
    _matricula(db, 4016, encerrada=1, situacao="ENCERRADA")
    _matricula(db, 4017, encerrada=1)
    _matricula(db, 4018, situacao="ENCERRADA")
    _matricula(db, 4019, situacao="CANCELADA")
    _matricula(db, 4020, situacao="INEXISTENTE")
    _subida(db)
    assert [r["matricula"] for r in _mapa(db)] == ["4015"]
    assert [r["matricula"] for r in _view(db)] == ["4015"]


def test_matricula_reaberta_continua_no_mapa_com_a_situacao_ATIVO(db):
    """A reabertura grava `'ATIVO'`, e não `'ATIVA'`: filtrar pela palavra
    tiraria do mapa a ficha que voltou a valer."""
    _matricula(db, 4015, situacao="ATIVO", encerrada=0)
    assert [r["matricula"] for r in _mapa(db)] == ["4015"]


# ------------------------------------------------------------ os donos


def test_varios_proprietarios_vao_juntos_e_quem_vendeu_nao_vai(db):
    mid = _matricula(db, 4015)
    _parte(db, mid, "FULANA EXEMPLO DE SOUSA")
    _parte(db, mid, "VENDEDOR EXEMPLO ANTIGO", ativo=0)   # já foi dono
    _parte(db, mid, "BELTRANO EXEMPLO DE SOUSA")
    _parte(db, mid, "FULANA EXEMPLO DE SOUSA")             # gravada duas vezes
    _parte(db, mid, "   ")                                  # nome em branco
    _subida(db)
    juntos = "FULANA EXEMPLO DE SOUSA; BELTRANO EXEMPLO DE SOUSA"
    assert _mapa(db)[0]["proprietario"] == juntos
    assert _view(db)[0]["proprietario"] == juntos


def test_sem_dono_e_sem_cns_vai_texto_vazio_e_nao_None(db):
    """O plugin faz `str(db_data.get("proprietario", ""))`: NULL viraria a
    palavra «None» no arquivo que vai ao ONR."""
    db.set_settings({"ri_cns": "", "serventia_cns": ""})
    _matricula(db, 4015)
    _subida(db)
    assert _mapa(db)[0]["proprietario"] == "" and _mapa(db)[0]["cns"] == ""
    assert _view(db)[0]["proprietario"] == "" and _view(db)[0]["cns"] == ""


# --------------------------------------------------------------- o CNS


def test_o_cns_e_o_do_registro_de_imoveis_so_com_os_digitos(db):
    db.set_settings({"ri_cns": "12.345-6", "serventia_cns": "654321"})
    _matricula(db, 4015)
    assert _mapa(db)[0]["cns"] == "123456"


def test_sem_cns_do_ri_vale_o_da_serventia_como_no_canal_do_onr(db):
    db.set_settings({"ri_cns": " ", "serventia_cns": "65.432-1"})
    _matricula(db, 4015)
    assert _mapa(db)[0]["cns"] == "654321"


# ----------------------------------------------------- a matrícula e a ordem


def test_complemento_entra_no_numero_como_a_ficha_o_escreve(db):
    _matricula(db, 4015)
    _matricula(db, 4015, complemento="A")
    assert [r["matricula"] for r in _mapa(db)] == ["4015", "4015-A"]


def test_a_ordem_e_a_do_numero_da_matricula_e_nao_a_do_texto(db):
    for numero in (100, 9, 10):
        _matricula(db, numero)
    assert [r["matricula"] for r in _mapa(db)] == ["9", "10", "100"]


def test_matriculas_traz_so_as_pedidas_e_lista_vazia_nao_traz_nenhuma(db):
    for numero in (4015, 4016, 4017):
        _matricula(db, numero)
    _matricula(db, 4016, complemento="A")
    assert [r["matricula"] for r in _mapa(db, ["4017", 4015, " 4016-A "])] == [
        "4015", "4016-A", "4017"]
    assert _mapa(db, []) == []
    assert len(_mapa(db)) == 4
    # Uma só, sem lista: o texto não se percorre letra a letra.
    assert [r["matricula"] for r in _mapa(db, "4016")] == ["4016"]
    assert [r["matricula"] for r in _mapa(db, 4017)] == ["4017"]


# --------------------------------------------------------------- a VIEW


def test_a_VIEW_tem_as_quatro_colunas_que_o_plugin_le(db):
    with db.connect() as con:
        colunas = [r["column_name"] for r in banco(con).ler(
            """SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'onr_mapa_imoveis'
                ORDER BY ordinal_position""")]
    assert colunas == ["matricula", "cns", "proprietario", "area_ha"]


def test_o_plugin_acha_o_imovel_pela_consulta_dele(db):
    """A consulta é a do `main.py` do plugin, com a tabela trocada: a
    matrícula chega como TEXTO, lida do atributo da camada."""
    mid = _matricula(db, 4015, area_valor="63", area_unidade="ha")
    _parte(db, mid, "FULANA EXEMPLO DE SOUSA")
    _subida(db)
    with db.connect() as con:
        achado = banco(con).um(
            "SELECT cns, proprietario, area_ha FROM onr_mapa_imoveis "
            "WHERE matricula = %s", ("4015",))
    assert achado["cns"] == "000000"
    assert achado["proprietario"] == "FULANA EXEMPLO DE SOUSA"
    assert float(achado["area_ha"]) == 63.0


def test_a_VIEW_diz_o_mesmo_que_o_CSV_depois_da_subida(db):
    areas = [("360", "m2"), ("8.435,26", "m2"), ("63", "ha"), ("231,0233", "ha"),
             ("3808", "ha"), ("27368100", None), (None, None), ("63", None),
             ("0", "ha")]
    for i, (valor, unidade) in enumerate(areas):
        mid = _matricula(db, 4015 + i, area_valor=valor, area_unidade=unidade)
        _parte(db, mid, f"PROPRIETARIA EXEMPLO {i}")
    _subida(db)
    do_csv = _mapa(db)
    da_view = [dict(r, area_ha=None if r["area_ha"] is None else float(r["area_ha"]))
               for r in _view(db)]
    assert sorted(da_view, key=lambda r: r["matricula"]) == \
        sorted(do_csv, key=lambda r: r["matricula"])
    assert len(do_csv) == len(areas)


def test_area_escrita_depois_da_subida_fica_vazia_na_VIEW_e_nao_errada(db):
    """O de-para se refaz na subida. O texto novo não casa com ele, e a VIEW
    fica sem área até a próxima — o CSV, que chama a régua, já a tem."""
    _subida(db)
    _matricula(db, 4015, area_valor="452,17", area_unidade="ha")
    assert _view(db)[0]["area_ha"] is None
    assert _mapa(db)[0]["area_ha"] == 452.17
    _subida(db)
    assert float(_view(db)[0]["area_ha"]) == 452.17


def test_a_subida_refaz_a_area_que_a_regua_passou_a_ler_diferente(db):
    """Quem conserta a régua conserta o de-para na subida seguinte — e não só
    o texto que faltava nele."""
    _matricula(db, 4015, area_valor="63", area_unidade="ha")
    _subida(db)
    with db.transaction() as con:      # a régua antiga lia 63 ha como 63 m²
        banco(con).escrever(
            "UPDATE ri_mapa_onr_areas SET area_m2 = 63 WHERE area_valor = '63'")
    assert float(_view(db)[0]["area_ha"]) == 0.0063
    _subida(db)
    assert float(_view(db)[0]["area_ha"]) == 63.0


def test_o_de_para_esquece_o_texto_que_nenhuma_ficha_escreve_mais(db):
    mid = _matricula(db, 4015, area_valor="63", area_unidade="ha")
    _subida(db)
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE ri_matriculas SET area_valor = '64' WHERE id = %s", (mid,))
    _subida(db)
    with db.connect() as con:
        textos = [r["area_valor"] for r in banco(con).ler(
            "SELECT area_valor FROM ri_mapa_onr_areas ORDER BY area_valor")]
    assert textos == ["64"]


def test_teor_colado_na_coluna_da_area_nao_derruba_a_subida(db):
    """O B-tree recusa chave que, comprimida, passa de ~2,7 KB, e o INSERT
    recusado pararia a subida do sistema inteiro por causa de uma ficha. O
    texto é de hash para não comprimir: texto repetido caberia no índice e o
    teste passaria sem a guarda."""
    colado = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(200))
    _matricula(db, 4015, area_valor="63 hectares " + colado, area_unidade="ha")
    _subida(db)
    _subida(db)                                # e é idempotente
    assert _view(db)[0]["area_ha"] is None
    assert _mapa(db)[0]["area_ha"] == 63.0


# ---------------------------------------------------------------- a rota


def test_so_ADMIN_baixa_o_csv_do_mapa(cg_casa):
    db = cg_casa["db"]
    db.create_user("gerente", "GERENTE EXEMPLO", SENHA, "MANAGER")
    db.create_user("balcao", "BALCAO EXEMPLO", SENHA, "USER")
    db.create_user("oficial", "OFICIAL EXEMPLO", SENHA, "ADMIN")
    anonimo = cg_casa["app"].test_client()
    assert anonimo.get("/ri/mapa-onr.csv").status_code == 302
    for usuario in ("gerente", "balcao"):
        c = cg_casa["app"].test_client()
        cg_login(c, usuario, SENHA)
        assert c.get("/ri/mapa-onr.csv").status_code == 403, usuario
    c = cg_casa["app"].test_client()
    cg_login(c, "oficial", SENHA)
    r = c.get("/ri/mapa-onr.csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]


def test_o_csv_traz_os_nomes_do_onr_e_a_area_em_hectares(cg_casa_logada):
    db = cg_casa_logada["db"]
    db.set_settings({"ri_cns": "000000"})
    mid = _matricula(db, 4015, area_valor="231,0233", area_unidade="ha")
    _parte(db, mid, "FULANA EXEMPLO DE SOUSA")
    _parte(db, mid, "BELTRANO EXEMPLO DE SOUSA")
    _matricula(db, 4016, encerrada=1, situacao="ENCERRADA")
    _matricula(db, 4017, area_valor="3808", area_unidade="ha")
    texto = cg_casa_logada["c"].get("/ri/mapa-onr.csv").get_data(as_text=True)
    linhas = list(csv.reader(io.StringIO(texto.lstrip("﻿")),
                             delimiter=MAPA.SEPARADOR_DO_CSV))
    assert linhas == [
        ["MATRICULA", "CNS", "PROPRIETAR", "AREA_HA"],
        ["4015", "000000", "FULANA EXEMPLO DE SOUSA; BELTRANO EXEMPLO DE SOUSA",
         "231.0233"],
        ["4017", "000000", "", ""],
    ]


def test_o_download_do_mapa_fica_na_auditoria(cg_casa_logada):
    """O CSV leva nome de proprietário: quem baixou, e quando, fica escrito."""
    db = cg_casa_logada["db"]
    _matricula(db, 4015)
    assert cg_casa_logada["c"].get("/ri/mapa-onr.csv").status_code == 200
    registro = db.list_logs(5)[0]
    assert registro["action"] == "RI_MAPA_ONR_EXPORTADO"
    assert registro["username_snapshot"] == "mario"
    assert '"imoveis": 1' in registro["details"]


def test_o_download_nao_escreve_no_de_para(cg_casa_logada, monkeypatch):
    """GET não escreve (`docs/ARQUITETURA.md`): o de-para é da subida."""
    def nao_pode(*_a, **_k):
        raise AssertionError("o GET do CSV refez o de-para")
    monkeypatch.setattr(MAPA, "atualizar_areas", nao_pode)
    _matricula(cg_casa_logada["db"], 4015)
    assert cg_casa_logada["c"].get("/ri/mapa-onr.csv").status_code == 200

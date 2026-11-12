"""Correções do papel e aviso da ficha preservadas ao atualizar a produção."""
import json

import pytest

from bd_nativo import banco
import rc_certidao_quadro as Q


NOME = "Mario Exemplo dos Santos"
MAE = "Beatriz Exemplo de Souza"
PAI = "Pedro Exemplo dos Santos"
AVO = "Carla Exemplo"


def _assento(casa, dados=None, especie="NASCIMENTO"):
    with casa["db"].transaction() as con:
        bd = banco(con)
        aid = bd.valor("""INSERT INTO rc_assentos
            (serie,especie,numero,nome,data_ato,situacao,origem,criado_em,dados_json)
            VALUES (%s,%s,1,%s,'2026-11-10','ATIVO','IMPORTACAO',
                    '2026-11-10T08:00:00',%s) RETURNING id""",
            ("RC_A" if especie == "NASCIMENTO" else "RC_C", especie, NOME,
             json.dumps(dados or {})))
        for papel, nome in (("REGISTRADO", NOME), ("MAE", MAE), ("PAI", PAI)):
            bd.escrever("""INSERT INTO rc_pessoas
                (assento_id,papel,nome,nome_norm,origem,criado_em)
                VALUES (%s,%s,%s,%s,'IMPORTACAO','2026-11-10T08:00:00')""",
                (aid, papel, nome, nome.lower()))
    return int(aid)


@pytest.mark.parametrize("ramo,papel", [
    ("maternos", "AVO_MATERNA"), ("maternos", "AVO_MATERNO"),
    ("paternos", "AVO_PATERNA"), ("paternos", "AVO_PATERNO")])
def test_pessoa_dos_avos_prevalece_sobre_transcricao(cg_casa_logada, ramo, papel):
    casa = cg_casa_logada
    campo = "avos_" + ramo
    aid = _assento(casa, {"acervo_transcrito": {campo: "digo, [?] (já falecidos)"}})
    with casa["db"].transaction() as con:
        banco(con).escrever("""INSERT INTO rc_pessoas
            (assento_id,papel,nome,nome_norm,origem,criado_em)
            VALUES (%s,%s,%s,%s,'IMPORTACAO','2026-11-10T08:00:00')""",
            (aid, papel, AVO, AVO.lower()))
    with casa["db"].connect() as con:
        quadro = Q.quadro_da_certidao(con, {"assento_id": aid}, {})
    assert quadro[campo] == AVO
    genitor = next(g for g in quadro["genitores"] if g["nome"] == (MAE if ramo == "maternos" else PAI))
    assert genitor["avos"] == AVO


def test_transcricao_completa_apenas_ramo_sem_pessoa(cg_casa_logada):
    casa = cg_casa_logada
    aid = _assento(casa, {"acervo_transcrito": {
        "avos_maternos": AVO, "avos_paternos": PAI}})
    with casa["db"].transaction() as con:
        banco(con).escrever("""INSERT INTO rc_pessoas
            (assento_id,papel,nome,nome_norm,origem,criado_em)
            VALUES (%s,'AVO_PATERNO',%s,%s,'IMPORTACAO','2026-11-10T08:00:00')""",
            (aid, NOME, NOME.lower()))
    with casa["db"].connect() as con:
        quadro = Q.quadro_da_certidao(con, {"assento_id": aid}, {})
    assert quadro["avos_maternos"] == AVO
    assert quadro["avos_paternos"] == NOME
    assert {g["nome"]: g["avos"] for g in quadro["genitores"]} == {MAE: AVO, PAI: NOME}


@pytest.mark.parametrize("texto,esperado", [
    ("MA", ("", "MA")), (" ma ", ("", "MA")),
    ("Cidade Exemplo/MA", ("Cidade Exemplo", "MA")),
    ("Cidade Exemplo", ("Cidade Exemplo", "")), ("", ("", ""))])
def test_uf_sozinha_nao_vira_municipio(texto, esperado):
    assert Q._cidade_uf(texto) == esperado


def test_obito_sem_municipio_preserva_uf_em_campo_proprio():
    q = Q._quadro_obito({"especie": "OBITO"}, {}, {"strUFObito": "MA"}, "", {})
    assert q["municipio_falecimento"] == ""
    assert q["municipio_falecimento_uf"] == "MA"


@pytest.mark.parametrize("margem", [None, "", "Anotação ilegível na margem <conferir>."])
def test_aviso_da_margem_aparece_no_alto_da_ficha(cg_casa_logada, margem):
    casa = cg_casa_logada
    aid = _assento(casa, {"margem_a_conferir": margem})
    resposta = casa["c"].get(f"/rcpn/{aid}")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    aviso = "Confira no livro antes de certificar"
    if margem:
        assert aviso in html
        assert "Anotação ilegível na margem &lt;conferir&gt;." in html
        assert html.index(aviso) < html.index("O assento")
    else:
        assert aviso not in html


def test_aviso_da_margem_em_lista_mostra_os_itens(cg_casa_logada):
    casa = cg_casa_logada
    aid = _assento(casa, {"margem_a_conferir": {
        "desde": "2026-11-10",
        "itens": [
            {"especie": "SEM EFEITO",
             "o_que_conferir": "não certificar sem conferir no livro",
             "texto_da_margem": "Trecho genérico <da margem>"},
            {"especie": "ANOTAÇÃO",
             "o_que_conferir": "lance a anotação na ficha",
             "texto_da_margem": ""},
        ],
    }})
    resposta = casa["c"].get(f"/rcpn/{aid}")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert 'data-margem="lista"' in html
    assert 'class="notice critical" role="alert" data-margem="lista"' in html
    assert "Sem efeito" in html
    assert "não certificar sem conferir no livro" in html
    assert "Anotação" in html
    assert "lance a anotação na ficha" in html
    assert "Trecho genérico &lt;da margem&gt;" in html
    assert "{'desde'" not in html and '{"desde"' not in html
    assert html.index("Confira no livro antes de certificar") < html.index("O assento")


def test_aviso_da_margem_sem_efeito_ausente_nao_fica_critico(cg_casa_logada):
    casa = cg_casa_logada
    aid = _assento(casa, {"margem_a_conferir": {"itens": [
        {"especie": "ANOTAÇÃO", "o_que_conferir": "confira a anotação",
         "texto_da_margem": "outro trecho genérico"},
    ]}})
    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert 'class="notice" role="alert" data-margem="lista"' in html
    assert 'data-margem="lista"' in html
    assert "Sem efeito" not in html

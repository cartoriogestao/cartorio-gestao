"""As regras do gerador de lotes do acervo transcrito (17/11/2026).

Só funções que calculam: o gerador lê a planilha e o banco, e quem grava é o
lote (`rc_acervo_lote`), testado à parte.
"""
import pytest

from tools import acervo_transcrito_lotes as G


@pytest.mark.parametrize("bruto, esperado", [
    ("Juliana Beserra digo Bezerra de Exemplo", "Juliana Bezerra de Exemplo"),
    ("Tereza Rib digo, dos Santos Ribeiro", "Tereza dos Santos Ribeiro"),
    ("Fulana[?] Miranda Leão. digo Marinho Leão", "Fulana Marinho Leão"),
    ("(Pedro) digo, Joaquim Alves Exemplo", "Joaquim Alves Exemplo"),
    ("CICERO [entrelinha: JOSÉ] DE SOUZA EXEMPLO", "CICERO JOSÉ DE SOUZA EXEMPLO"),
    ("Beltrana Soares [riscado: de] Exemplo", "Beltrana Soares Exemplo"),
    ("Ciclano Lima de Castro (o declarante)", "Ciclano Lima de Castro"),
    ("Ciclano Negreiro Exemplo, falecido", "Ciclano Negreiro Exemplo"),
    ("Osvaldo Exemplo Carvalho, OSWALDO EXEMPLO CARVALHO", "Osvaldo Exemplo Carvalho"),
    ("— retificado na nota: FULANO ALVES DE EXEMPLO", "FULANO ALVES DE EXEMPLO"),
    ("Fulana da Costa Exemplo (AV-01: Fulana da Costa dos Exemplos)", "Fulana da Costa Exemplo"),
])
def test_o_nome_sai_limpo(bruto, esperado):
    assert G.limpar_nome(bruto)[0] == esperado


def test_trecho_ilegivel_vai_para_a_conferencia():
    nome, notas = G.limpar_nome("Fulana Mi[ilegível]anda Exemplo")
    assert "nome com trecho ilegível ou rasurado" in notas


@pytest.mark.parametrize("bruto, hora", [
    ("19:00hs", "19:00"), ("8 haras[?]", "08:00"), ("1:00", "01:00"),
    ("10 horas e 30 minutos", "10:30"), ("20.30 hs", "20:30"), (None, ""), ("24:00", ""),
])
def test_a_hora(bruto, hora):
    assert G.hora_de(bruto) == hora


def test_o_sexo_nao_se_adivinha():
    assert G.sexo_de("mosculino[?]", "") == "M"
    assert G.sexo_de("femenino", "") == "F"
    assert G.sexo_de(None, "é do sexo feminino, de côr morena") == "F"
    assert G.sexo_de(None, "nasceu uma criança, filho deste prenome") == ""


@pytest.mark.parametrize("sistema, teor, pequena", [
    ("LILLIAN DE SOUSA EXEMPLO", "Lilian de Sousa Exemplo", True),
    ("MARIA GORETE DE EXEMPLO", "Maria Gareta de Exemplo", True),
    ("Fulano Erico Gomes Exemplo", "Fulano Gomes Exemplo", True),
    ("Beltrana R. Exemplo", "Beltrana Ribeiro Exemplo", True),
    ("LEVINO PEREIRA EXEMPLO", "Severino Pereira Exemplo", False),
    ("JACIRA CARDOSO EXEMPLO", "Salina Cardoso Exemplo", False),
])
def test_diferenca_pequena_e_a_que_pode_ser_falha_de_transcricao(sistema, teor, pequena):
    assert G.diferenca_pequena(sistema, teor) is pequena


def test_o_assento_de_outro_filho_nao_e_complementado():
    assert G.mesma_pessoa("FULANO MIRANDA EXEMPLO", "Beltrana Miranda Exemplo") is False
    assert G.mesma_pessoa("CICLANA FERNANDES DE EXEMPLO", "Ciclana Rodrigues Fernandes") is True


def test_as_notas_da_margem_viram_atos():
    atos = G.atos_da_margem(
        "Obs: O registro foi feito de acordo o art. 30 da Lei nº 6015/73. | "
        "AV-01/9.000- AVERBAÇÃO CPF: O registrado está inscrito no CPF/MF sob o nº 000.000.001-91 | "
        "Av1. Cidade Exemplo, 29 de julho de 2009. Cumprindo mandado de reconhecimento de paternidade | "
        "Obs: O registrado casou-se com Fulana, no Lº B-01, em data de 31/03/06.")
    assert [(a["tipo"], a["natureza"]) for a in atos] == [
        ("ANOTACAO", None), ("AVERBACAO", "cpf_347"),
        ("AVERBACAO", "reconhecimento_filiacao"), ("ANOTACAO", None)]
    assert atos[0]["data_ato"] is None
    assert atos[2]["data_ato"] == "2009-07-29"
    assert atos[3]["data_ato"] == "2006-03-31"


class _Ctx:
    cns = "000000"
    municipios = G.Municipios(
        [{"nome": "Cidade Exemplo", "uf": "MA"}, {"nome": "Porto Exemplar", "uf": "MA"},
         {"nome": "Vila Nova Exemplo", "uf": "MA"}, {"nome": "Vila Nova Exemplo", "uf": "RN"}],
        "Cidade Exemplo", "MA")


@pytest.mark.parametrize("local, municipio", [
    ("Hospital Regional de Porto Exemplar-Ma.", ("Porto Exemplar", "MA")),
    ("no lugar Agua Branca d/municipio", ("Cidade Exemplo", "MA")),
    ("nesta cidade", ("Cidade Exemplo", "MA")),
    ("Sitio Bom C. Exemplo Maranhão", ("Cidade Exemplo", "MA")),
    ("Porto Exemplr - Maranhão", ("Porto Exemplar", "MA")),
    ("natural de Vila Nova Exemplo-Ma", ("Vila Nova Exemplo", "MA")),
])
def test_o_municipio_vem_do_cadastro_do_ibge(local, municipio):
    assert _Ctx.municipios.no_texto(local) == municipio


def test_o_registro_do_lote_e_o_que_nao_consta():
    linha = {
        "termo": "1.977", "folha": "1v", "tipo_registro": "tardio",
        "data_registro": "dois de julho de 1968 (1968-07-02)",
        "data_nascimento": "15 de dezembro de 1948 (1948-12-15)",
        "nome_registrado": "Fulano de Exemplo", "hora_nascimento": None,
        "local_nascimento": "lugar Agua Branca d/municipio", "sexo": "masculino",
        "cor": "morena", "dnv": None, "pai": "Pai de Exemplo",
        "pai_qualificacao": "natural desta cidade, casado, lavrador",
        "mae": "Mãe de Exemplo", "mae_qualificacao": None,
        "idade_mae_no_parto": "26 anos", "avos_paternos": "ignorados",
        "avos_maternos": None, "averbacoes": None,
        "texto_integral": "Nº-1977 ... é do sexo masculino ...", "arquivo_pdf": "x.pdf",
    }
    r = G.montar(linha, "A-7", "07_1968", 2, _Ctx)
    v = r["valores"]
    assert (v["livro_volume"], v["numero"], v["folha"]) == ("A-7", 1977, "1v")
    assert v["data_ato"] == "1968-07-02" and v["registro_tardio"] == 1
    assert v["local_fato_municipio"] == "Cidade Exemplo/MA"
    assert v["ibge_local_nascimento"] == 5          # «lugar» rural, fora de unidade de saúde
    assert "hora_fato" not in v and "dnv" not in v  # vazio: a CRC/SIRC mandam «ignorado»
    assert v["matricula"].startswith("00000001551968100007001000197")
    pessoas = {p["papel"]: p for p in v["pessoas"]}
    assert pessoas["REGISTRADO"]["sexo"] == "M"
    assert pessoas["REGISTRADO"]["naturalidade_cidade"] == "Cidade Exemplo"
    assert pessoas["MAE"]["idade_no_fato"] == "26"
    assert pessoas["PAI"]["naturalidade_cidade"] == "Cidade Exemplo"
    assert pessoas["PAI"]["estado_civil"] == "casado" and pessoas["PAI"]["profissao"] == "lavrador"
    assert {"hora do nascimento", "DNV", "avós maternos"} <= set(r["nao_consta"])

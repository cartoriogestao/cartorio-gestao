"""O Indicador Real em XML e a regra da casa que completa o endereço.

    «vamos aumentar para todos. gerado do texto nao precisa conferir. vamos criar
     uma regra da casa, sem numero, zona rural, cep geral da cidade, etc»
                                                      — o oficial, 10/10/2026

A ordem: a FICHA → o TEXTO da ficha → a REGRA DA CASA. A ficha nunca é
sobrescrita, e nada é gravado nela.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_endereco_do_teor as ENDERECO                           # noqa: E402
import onr_indicador_xml as X                                      # noqa: E402

PADRAO = ENDERECO.padrao_da_casa({
    "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "serventia_cep": "99.999-000",
    ENDERECO.CHAVE_CEPS: "Cidade Vizinha=99998-000"})


def test_a_ficha_ganha_do_texto_e_o_texto_da_regra():
    ficha = {"logradouro": "Rua das Flores", "bairro": "", "cidade": None,
             "rural_urbano": "Urbano"}
    proposta = {"campos": {"logradouro": "Rua Outra", "bairro": "Centro Velho",
                           "cidade": "Cidade Exemplo", "uf": "MA"}}
    novo, origem = X.completar_ficha(ficha, proposta, PADRAO)
    assert novo["logradouro"] == "Rua das Flores" and "logradouro" not in origem
    assert novo["bairro"] == "Centro Velho" and origem["bairro"] == "texto"
    assert novo["numero_predial"] == "0" and origem["numero_predial"] == "regra"
    assert novo["cep"] == "99999000" and origem["cep"] == "regra"


def test_rural_sem_nada_vai_pela_regra_da_casa():
    novo, origem = X.completar_ficha({}, None, PADRAO)
    assert novo["rural_urbano"] == "Rural"
    assert novo["bairro"] == "Zona Rural"
    assert novo["logradouro"] == X.LOGRADOURO_RURAL_SEM_NOME
    assert novo["tipo_imovel"] == X.TIPO_RURAL
    assert (novo["cidade"], novo["uf"], novo["cep"]) == ("Cidade Exemplo", "MA", "99999000")
    assert set(origem.values()) == {"regra"}


def test_a_frase_do_livro_vira_logradouro_que_o_onr_aceita():
    novo, origem = X.completar_ficha(
        {"logradouro": "a AVENIDA DEOCLIDES GOMES", "rural_urbano": "Urbano"}, None, PADRAO)
    assert novo["logradouro"] == "AVENIDA DEOCLIDES GOMES"
    novo, _ = X.completar_ficha(
        {"logradouro": "situada na zona rural do Município", "rural_urbano": "Urbano"},
        None, PADRAO)
    assert novo["logradouro"] == X.LOGRADOURO_URBANO_SEM_NOME


@pytest.mark.parametrize("frase, esperado", [
    ("Casa urbana com respectivo terreno", "Casa"), ("Sala/Conjunto", "Sala"),
    ("RURAL", X.TIPO_RURAL), ("Casa", "Casa")])
def test_o_tipo_do_imovel_vira_um_dos_dez(frase, esperado):
    novo, _ = X.completar_ficha({"tipo_imovel": frase, "rural_urbano": "Rural"}, None, PADRAO)
    assert novo["tipo_imovel"] == esperado


def test_o_cep_da_cidade_vizinha_e_o_dela():
    novo, _ = X.completar_ficha({"cidade": "Cidade Vizinha", "rural_urbano": "Rural"},
                                None, PADRAO)
    assert novo["cep"] == "99998000"


def test_o_xml_segue_o_modelo_do_manual_e_tira_o_ato_incompleto():
    corpo = {"cns": "000000", "numeroRegistro": 640, "logradouro": "do Meio & Cia",
             "proprietarios": [{"nome": "FULANO", "documento": "22105769039"}],
             "atos": [{"tipo": 1, "descricao": "x", "dataRegistro": "2026-01-01",
                       "numero": 1},
                      {"tipo": 1, "descricao": "y", "dataInstrumento": "2026-01-01",
                       "valorDeclarado": 10.0, "dataRegistro": "2026-01-02", "numero": 2}],
             "situacaoConstrucao": 0}
    raiz = ET.fromstring(X.arquivo_xml([corpo]))
    ind = raiz.find("IndicadorReal")
    assert ind.findtext("NomeLogradouro") == "do Meio & Cia"
    assert ind.findtext("SituacaoConstrucao") == "0"         # o zero não some
    assert ind.find("Proprietarios/Parte/Nome").text == "FULANO"
    atos = ind.findall("Atos/Ato")
    assert len(atos) == 1 and atos[0].findtext("NumeroAto") == "2"
    assert atos[0].findtext("ValorDeclarado") == "10.00"


def test_o_arquivo_recusa_passar_do_limite_do_manual():
    with pytest.raises(ValueError):
        X.arquivo_xml([{}] * (X.LIMITE_POR_ARQUIVO + 1))


# ------------------------------------------------- o dono de hoje (11/10/2026)

def _p(nome, papel, qual="", ativo=0, ato_id=None):
    return {"nome": nome, "papel": papel, "qualificacao": qual,
            "proprietario_ativo": ativo, "ato_id": ato_id}


def test_quem_esta_marcado_na_ficha_ganha():
    partes = [_p("A", "proprietario", "ABERTURA · 1990", ativo=1),
              _p("B", "adquirente", "R-1 · 1991")]
    donos, de_onde = X.donos_presumidos(partes)
    assert [d["nome"] for d in donos] == ["A"] and de_onde == "ficha"


def test_os_adquirentes_do_ultimo_ato_sao_os_donos():
    partes = [_p("A", "proprietario", "ABERTURA · 10/10/1990 · abertura"),
              _p("A", "transmitente", "R-1 · 10/10/1990 · venda"),
              _p("B", "adquirente", "R-1 · 10/10/1990 · venda"),
              _p("B", "transmitente", "AV-3 · 2017 · compra e venda"),
              _p("C", "adquirente", "AV-3 · 2017 · compra e venda"),
              _p("BANCO", "credor", "AV-4 · 2018 · hipoteca")]
    donos, de_onde = X.donos_presumidos(partes)
    assert [d["nome"] for d in donos] == ["C"] and de_onde == "adquirentes do AV-3"


def test_ato_posterior_que_refaz_o_dono_vale():
    partes = [_p("A", "adquirente", "AV-1 · 2018 · compra e venda"),
              _p("A MAIOR", "proprietario", "AV-2 · 2018 · maioridade")]
    donos, de_onde = X.donos_presumidos(partes)
    assert [d["nome"] for d in donos] == ["A MAIOR"] and de_onde == "proprietários do AV-2"


def test_sem_transmissao_fica_quem_abriu_e_o_ato_lavrado_aqui_pelo_id():
    abertura = [_p("A", "proprietario", "ABERTURA · 2026"), _p("B", "proprietario", "ABERTURA · 2026")]
    assert [d["nome"] for d in X.donos_presumidos(abertura)[0]] == ["A", "B"]
    lavrado = [_p("V", "transmitente", ato_id=10), _p("C", "adquirente", ato_id=10)]
    donos, de_onde = X.donos_presumidos(lavrado, {10: ("R", 1)})
    assert [d["nome"] for d in donos] == ["C"] and de_onde == "adquirentes do R-1"


def test_carga_do_eoficio_sem_ato_e_ficha_sem_parte():
    assert X.donos_presumidos([_p("OLINTO", "proprietario")])[1].startswith("proprietários da carga")
    assert X.donos_presumidos([]) == ([], "")
    # adquirente sem ato que se saiba: não se adivinha
    assert X.donos_presumidos([_p("A", "proprietario"), _p("B", "adquirente")]) == ([], "")


def test_a_area_com_o_numero_por_extenso_nao_vira_dez_mil_vezes_maior():
    """Matrícula 4011, 11/10/2026: a coluna guarda o número e o extenso."""
    import onr_api as API
    assert API.area_em_metros("19,3419 ha (dezenove hectares, trinta e quatro ares e "
                              "dezenove centiares)", "ha") == 193419
    assert API.area_em_metros("19,3419", "ha") == 193419


@pytest.mark.parametrize("escrito, metros", [
    ("3.108,08,06", 31080806), ("2.166.13.37", 21661337), ("1.054,04,65", 10540465)])
def test_hectare_com_milhar_e_ares_nao_sai_mil_vezes_maior(escrito, metros):
    """11/10/2026: a 2556 ia ao índice com 3.108.008 ha, mais que o município."""
    import onr_api as API
    assert API.area_em_metros(escrito, "ha") == metros


def test_o_hifen_antes_da_unidade_nao_a_esconde():
    """Matrícula 1926: «25.434,50-M²» é metro quadrado, e não hectare."""
    a = ENDERECO.area_do_texto("o terreno possui uma área de 25.434,50-M² (vinte e cinco mil)")
    assert a["unidade"] == "m2" and a["metros"] == 25434


def test_a_area_maior_da_gleba_de_origem_nao_vai():
    proposta = {"campos": {"area_valor": "31080806", "area_unidade": "m2"},
                "area": {"de_onde": "área maior de 3.108,08,06 ha"}}
    novo, origem = X.completar_ficha({"rural_urbano": "Rural"}, proposta, PADRAO)
    assert not novo.get("area_valor") and "maior" in origem["area_valor"]

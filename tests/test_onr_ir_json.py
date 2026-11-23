"""O JSON do Indicador Real contra o manual do ONR, v2.0. Não usa banco.

O risco que estes testes defendem é o arquivo sair com um código da tabela errada: o manual do
arquivo, a API e o sistema anterior têm três tabelas diferentes para o mesmo imóvel.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_ir_json as J  # noqa: E402
import ri_onr  # noqa: E402

CASA = J.Serventia(cns="000000", uf="SP", uf_codigo=35, municipios={"cidade exemplo": 3500000})


def ficha(**mudar) -> dict:
    base = {"numero": "1234", "livro_norm": "2", "rural_urbano": "U", "tipo_imovel": "Casa",
            "logradouro": "Rua das Flores", "numero_predial": "10", "uf": "SP", "cidade": "Cidade Exemplo",
            "bairro": "Centro", "cep": "01234-567", "complemento_endereco": "Fundos"}
    base.update(mudar)
    return base


def test_as_tabelas_tem_os_codigos_que_o_proprio_manual_cita():
    assert len(J.TIPOS_DE_LOGRADOURO) == 311
    assert (J.TIPOS_DE_LOGRADOURO[26], J.TIPOS_DE_LOGRADOURO[250], J.TIPOS_DE_LOGRADOURO[215]) == (
        "Avenida", "Rua", "Praça")
    assert J.TIPOS_DE_LOGRADOURO[J.TIPO_LOGRADOURO_LOTEAMENTO] == "Loteamento"
    assert J.TIPOS_DE_IMOVEL[1] == "casa" and J.TIPOS_DE_IMOVEL[9] == "fazenda/sitio/chacara"
    assert len(J.TIPOS_DE_IMOVEL) == 13 and len(J.UF_IBGE) == 27


@pytest.mark.parametrize("escrito, codigo", [
    ("Casa", 1), ("Apto", 2), ("Sala/Conjunto", 4), ("Terreno/fração", 5), ("Terreno/Fração", 5),
    ("Prédio residencial", 8), ("Fazenda/Sítio/Chácara", 9), ("Outros", 13),
])
def test_o_tipo_do_imovel_sai_pelo_nome(escrito, codigo):
    assert J.codigo_do_imovel(escrito) == codigo


@pytest.mark.parametrize("escrito", ["", "RURAL", "8", "Casa urbana com respectivo terreno"])
def test_tipo_que_nao_esta_na_tabela_nao_vira_palpite(escrito):
    assert J.codigo_do_imovel(escrito) is None


@pytest.mark.parametrize("letra, codigo", [("U", 0), ("URBANO", 0), ("R", 1), ("RURAL", 1)])
def test_localizacao_e_zero_urbano_e_um_rural(letra, codigo):
    registro, motivos = J.montar_registro(ficha(rural_urbano=letra, logradouro="Fazenda Boa Vista"), CASA)
    assert not motivos and registro["LOCALIZACAO"] == codigo


@pytest.mark.parametrize("texto, codigo, nome", [
    ("Rua João da Silva", 250, "João da Silva"), ("AVENIDA BRASIL", 26, "BRASIL"),
    ("1ª Travessa da Rua Sete", 303, "Sete"), ("Praça da Matriz", 215, "da Matriz"),
])
def test_o_logradouro_separa_tipo_e_nome(texto, codigo, nome):
    assert J.partir_logradouro(texto) == (codigo, nome)


@pytest.mark.parametrize("texto", ["", "Rua", "Beira Mar" * 0 + "Xyz Flores", "Sem Denominação", "Não Especificado X"])
def test_logradouro_sem_tipo_valido_e_recusado(texto):
    assert J.partir_logradouro(texto)[0] is None


def test_o_registro_tem_a_forma_do_exemplo_oficial():
    registro, motivos = J.montar_registro(ficha(), CASA)
    assert not motivos
    assert tuple(registro) == J.CHAVES_DO_REGISTRO
    assert registro["UF"] == 35 and registro["CIDADE"] == 3500000 and registro["TIPO_LOGRADOURO"] == 250
    assert registro["NOME_LOGRADOURO"] == "das Flores" and registro["CEP"] == "01234567"
    assert registro["CONTRIBUINTE"] == [] and registro["QUADRA"] == ""
    assert set(registro["RURAL"]) == set(J.CHAVES_RURAL) and set(registro["CONDOMINIO"]) == set(J.CHAVES_CONDOMINIO)
    assert J.validar_registro(registro, CASA) == []


def test_contribuinte_vai_como_texto():
    registro, _ = J.montar_registro(ficha(inscricao_municipal=137725), CASA)
    assert registro["CONTRIBUINTE"] == ["137725"]


def test_loteamento_e_preenchido_quando_o_tipo_exige():
    registro, _ = J.montar_registro(ficha(logradouro="Loteamento Vista Alegre"), CASA)
    assert registro["TIPO_LOGRADOURO"] == 162 and registro["LOTEAMENTO"] == "Vista Alegre"


def test_o_rural_leva_a_denominacao_e_os_cadastros():
    sigef = "94c67944-8d05-4682-ac9b-00f50af26bc7"
    registro, motivos = J.montar_registro(ficha(
        rural_urbano="R", tipo_imovel="Fazenda/Sítio/Chácara", logradouro="Fazenda Boa Vista",
        ccir="801.089.009.806-6", sigef=sigef, car="SP-3500000-" + "A" * 32), CASA)
    assert not motivos
    assert registro["RURAL"]["DENOMINACAORURAL"] == "Fazenda Boa Vista"
    assert registro["RURAL"]["CCIR"] == "8010890098066" and registro["RURAL"]["SIGEF"] == sigef


@pytest.mark.parametrize("mudar, trecho", [
    ({"ccir": "123"}, "CCIR"), ({"car": "errado"}, "CAR"), ({"sigef": "abc"}, "SIGEF"), ({"nirf": "12"}, "NIRF"),
])
def test_cadastro_rural_fora_do_formato_recusa(mudar, trecho):
    _, motivos = J.montar_registro(ficha(rural_urbano="R", logradouro="Fazenda Boa Vista", **mudar), CASA)
    assert any(trecho in m for m in motivos)


@pytest.mark.parametrize("mudar, trecho", [
    ({"numero": "12A"}, "número"), ({"livro_norm": "3"}, "Livro 2"), ({"rural_urbano": ""}, "urbano ou rural"),
    ({"tipo_imovel": ""}, "tipo do imóvel"), ({"logradouro": "Flores"}, "logradouro"), ({"uf": "RJ"}, "UF"),
    ({"cidade": "Outra"}, "município"), ({"cep": "123"}, "CEP"), ({"ccir": "8010890098066"}, "cadastro rural"),
])
def test_o_que_impede_diz_o_motivo(mudar, trecho):
    registro, motivos = J.montar_registro(ficha(**mudar), CASA)
    assert registro is None and any(trecho in m for m in motivos)


def test_o_arquivo_tem_a_raiz_do_manual_e_utf8_sem_bom():
    registro, _ = J.montar_registro(ficha(bairro="São José"), CASA)
    conteudo = ri_onr.gerar_indicador_real([registro], CASA)
    assert not conteudo.startswith(b"\xef\xbb\xbf") and "São José".encode() in conteudo
    corpo = json.loads(conteudo)
    assert list(corpo) == ["INDICADOR_REAL"] and list(corpo["INDICADOR_REAL"]) == ["CNS", "REAL"]
    assert corpo["INDICADOR_REAL"]["CNS"] == "000000"


def test_registro_adulterado_derruba_o_arquivo():
    registro, _ = J.montar_registro(ficha(), CASA)
    for campo, valor in (("LOCALIZACAO", 2), ("UF", 0), ("TIPO_LOGRADOURO", 0), ("TIPO_DE_IMOVEL", 0)):
        with pytest.raises(J.ArquivoInvalido):
            J.arquivo_json([{**registro, campo: valor}], CASA)


def test_numero_repetido_derruba_o_arquivo():
    registro, _ = J.montar_registro(ficha(), CASA)
    with pytest.raises(J.ArquivoInvalido):
        J.arquivo_json([registro, dict(registro)], CASA)


def test_a_configuracao_que_falta_e_dita():
    casa, faltam = J.serventia_de({"ri_cns": "12", "ri_uf": "XX"})
    assert casa is None and len(faltam) == 4


def test_o_codigo_do_municipio_tem_de_ser_da_uf():
    _casa, faltam = J.serventia_de({"ri_cns": "000000", "ri_uf": "SP", "ri_cidade": "Cidade Exemplo",
                                    "ibge_uf": "33", "ibge_municipio": "00001"})
    assert any("IBGE" in x for x in faltam)


def test_a_configuracao_completa_monta_a_serventia():
    casa, faltam = J.serventia_de({"ri_cns": "00.000-0", "ri_uf": "sp", "ri_cidade": "Cidade Exemplo",
                                   "ibge_uf": "35", "ibge_municipio": "00001"})
    assert not faltam and casa.cns == "000000" and casa.municipios == {"cidade exemplo": 3500001}

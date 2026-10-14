"""Testes da CTP (Comunicacao de Transacoes as Prefeituras) — ri_ctp.

Cobre o gerador compartilhado com a DOI: operacao_sugerida, conferir,
montar_registro (urbano e rural) e gerar_carga CTP (envelope com registros).
Fixtures genericas — sem CNS/CNPJ/nomes/IPs reais da serventia hardcoded
alem do que test_notas_doi ja usa (IBGE generico 2198765).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ri_ctp as CTP  # noqa: E402


# ------------------------------------------------------------------ fixtures


def matricula_urbana(**extra) -> dict:
    base = {
        "numero": "1234567",
        "livro": "2",
        "folha": "10",
        "rural_urbano": "URBANO",
        "logradouro": "Rua das Flores",
        "numero_predial": "100",
        "bairro": "Centro",
        "cep": "65936000",
        "cidade": "Municipio Teste",
        "area_valor": "360,00",
        "nirf": "12345678",
    }
    base.update(extra)
    return base


def matricula_rural(**extra) -> dict:
    base = {
        "numero": "4004",
        "livro": "2",
        "folha": "184",
        "rural_urbano": "RURAL",
        "logradouro": "Chacara Modelo",
        "bairro": "Zona rural",
        "area_valor": "14,94",
        "incra": "9500416230833",
        "nirf": "98861476",
        "descricao_perimetro": "Zona rural do Municipio",
    }
    base.update(extra)
    return base


def ato_base(**extra) -> dict:
    base = {"data_ato": "2026-08-27", "modelo_codigo": "R-COMPRA-VENDA",
            "natureza_titulo": "COMPRA E VENDA", "tipo": "R", "numero": "1"}
    base.update(extra)
    return base


def dados_base(**extra) -> dict:
    base = {
        "operacao": "11",
        "data_negocio": "2026-08-27",
        "valor_operacao": "92598,34",
        "valor_base_itbi": "92598,34",
        "forma_pagamento": "11",
        "tipo_parte": "1",
        "valor_parte": "100,00",
        "codigo_ibge": "2198765",
    }
    base.update(extra)
    return base


def parte(papel="ALIENANTE", nome="PARTE A", doc="52998224725",
          pct="100,00", **extra) -> dict:
    base = {"papel": papel, "nome": nome, "documento_numero": doc,
            "participacao": pct}
    base.update(extra)
    return base


# ------------------------------------------------------- operacao_sugerida


def test_operacao_sugerida_pelo_modelo():
    codigo, origem = CTP.operacao_sugerida(ato_base())
    assert codigo == "11"
    assert origem == "modelo"


def test_operacao_sugerida_por_pista_na_natureza():
    codigo, origem = CTP.operacao_sugerida(
        ato_base(modelo_codigo="", natureza_titulo="Compra e venda de imovel"))
    assert codigo == "11"
    assert origem == "natureza"


def test_operacao_sugerida_vazia_quando_nao_e_transacao():
    codigo, origem = CTP.operacao_sugerida(
        ato_base(modelo_codigo="", natureza_titulo="HIPOTECA"))
    assert codigo == ""
    assert origem == ""


def test_operacao_sugerida_doacao():
    codigo, origem = CTP.operacao_sugerida(
        ato_base(modelo_codigo="R-DOACAO"))
    assert codigo == "67"
    assert origem == "modelo"


# --------------------------------------------------------------- conferir


def test_conferir_ato_completo_passa():
    partes = [parte("ALIENANTE"), parte("ADQUIRENTE", "PARTE B", "11144477735")]
    faltas = CTP.conferir(ato_base(), matricula_urbana(), partes, dados_base())
    assert faltas == []


def test_conferir_sem_operacao_impede():
    partes = [parte("ALIENANTE"), parte("ADQUIRENTE", "PARTE B", "11144477735")]
    faltas = CTP.conferir(ato_base(), matricula_urbana(), partes,
                          dados_base(operacao=""))
    assert any("operação" in f.lower() or "opera" in f.lower() for f in faltas)


def test_conferir_sem_transmitente_impede():
    partes = [parte("ADQUIRENTE", "PARTE B", "11144477735")]
    faltas = CTP.conferir(ato_base(), matricula_urbana(), partes, dados_base())
    assert any("transmitente" in f for f in faltas)


def test_conferir_rural_sem_incra_impede():
    partes = [parte("ALIENANTE"), parte("ADQUIRENTE", "PARTE B", "11144477735")]
    m = matricula_rural(incra="", ccir="")
    faltas = CTP.conferir(ato_base(), m, partes, dados_base(codigo_incra=""))
    assert any("INCRA" in f for f in faltas)


# --------------------------------------------------------- montar_registro


def test_montar_registro_urbano_basico():
    partes = [parte("ALIENANTE", pct="100,00"),
              parte("ADQUIRENTE", "PARTE B", "11144477735", pct="100,00")]
    reg = CTP.montar_registro(
        ato_base(), matricula_urbana(), partes, dados_base(),
        "000001", "2198765")
    assert reg["tipoDeclaracao"] == "0"
    assert reg["tipoServico"] == "1"
    assert reg["tipoAto"] == "1"
    assert reg["destinacao"] == "1"
    assert reg["tipoImovel"] == "71"  # padrao urbano
    assert reg["valorOperacaoImobiliaria"] == 92598.34
    assert reg["valorBaseCalculoItbiItcmd"] == 92598.34
    assert reg["codigoIbge"] == "2198765"
    assert reg["cib"] == "12345678"
    assert reg["alienantes"][0]["indicadorNiIdentificado"] is True
    assert "identificadorNiIdentificado" not in reg["alienantes"][0]
    assert reg["alienantes"][0]["ni"] == "52998224725"
    assert reg["alienantes"][0]["participacao"] == 100.0
    assert "tipoLogradouro" in reg


def test_montar_registro_rural_tipo_imovel_69():
    # Sample DOI Livro 30 fls 184-192: rural com tipoImovel "69".
    partes = [parte("ALIENANTE", pct="50,00"),
              parte("ALIENANTE", "PARTE C", "52998224725", pct="50,00"),
              parte("ADQUIRENTE", "PARTE B", "11144477735", pct="100,00")]
    # CPF 00000004774 may be invalid digit — only used as ni string in mount
    reg = CTP.montar_registro(
        ato_base(), matricula_rural(), partes, dados_base(),
        "000001", "2198765")
    assert reg["destinacao"] == "3"
    assert reg["tipoImovel"] == "69"
    assert reg["denominacao"] == "Chacara Modelo"
    assert reg["codigoIncra"] == "9500416230833"
    assert reg["areaImovel"] == 14.94
    assert reg["cib"] == "98861476"
    assert "tipoLogradouro" not in reg
    assert all(a["indicadorNiIdentificado"] is True for a in reg["alienantes"])
    assert len(reg["alienantes"]) == 2
    assert len(reg["adquirentes"]) == 1


def test_montar_registro_rural_tipo_imovel_explicito():
    partes = [parte("ALIENANTE"), parte("ADQUIRENTE", "PARTE B", "11144477735")]
    reg = CTP.montar_registro(
        ato_base(), matricula_rural(), partes,
        dados_base(tipo_imovel="69"), "000001", "2198765")
    assert reg["tipoImovel"] == "69"


def test_cib_omitido_quando_nirf_vazio():
    partes = [parte("ALIENANTE"), parte("ADQUIRENTE", "PARTE B", "11144477735")]
    reg = CTP.montar_registro(
        ato_base(), matricula_rural(nirf=""), partes, dados_base(),
        "000001", "2198765")
    assert "cib" not in reg


def test_valores_decimais_brasileiros():
    partes = [parte("ALIENANTE"), parte("ADQUIRENTE", "PARTE B", "11144477735")]
    reg = CTP.montar_registro(
        ato_base(), matricula_urbana(), partes,
        dados_base(valor_operacao="1.234.567,89", valor_base_itbi="1.234.567,89"),
        "000001", "2198765")
    assert reg["valorOperacaoImobiliaria"] == 1234567.89
    assert reg["valorBaseCalculoItbiItcmd"] == 1234567.89


# ------------------------------------------------------------- gerar_carga


def test_gerar_carga_ctp_mantem_envelope_registros():
    # CTP/CENSEC: envelope com cns/competencia/quantidade/registros.
    # Nao confundir com DOI-Web (declaracoes) — vide notas_doi.gerar_carga.
    partes = [parte("ALIENANTE"), parte("ADQUIRENTE", "PARTE B", "11144477735")]
    reg = CTP.montar_registro(
        ato_base(), matricula_urbana(), partes, dados_base(),
        "000001", "2198765")
    carga = json.loads(CTP.gerar_carga([reg], "000001", "2026-08"))
    assert carga["cns"] == "000001"
    assert carga["competencia"] == "2026-08"
    assert carga["quantidade"] == 1
    assert "registros" in carga
    assert "declaracoes" not in carga
    assert carga["registros"][0]["tipoImovel"] == "71"
    assert carga["registros"][0]["alienantes"][0]["indicadorNiIdentificado"] is True


def test_nome_arquivo_ctp():
    assert CTP.nome_arquivo("000001", "2026-08") == "CTP_000001_202608.json"

"""
Testes da Declaracao sobre Operacoes Imobiliarias.

O QUE ELES DEFENDEM
    As regras do manual da Receita que, violadas, fazem o arquivo ser recusado
    ou a declaracao sair errada sem ninguem perceber: uma DOI por imovel, a
    soma das participacoes entre 99 e 100 por cento, area urbana em metros
    quadrados e rural em hectares, e o codigo de operacao desativado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notas_doi as DOI          # noqa: E402


def imovel_urbano(**extra) -> dict:
    base = {"matricula": "1234567", "cib": "12345678", "tipo": 67,
            "area_terreno": "360,00", "area_construida": "180,00",
            "logradouro": "Avenida Fabrício Ferraz", "numero": "85",
            "bairro": "Centro", "cep": "65936000",
            "valor_operacao": 18500000, "valor_base_calculo": 18500000}
    base.update(extra)
    return base


def imovel_rural(**extra) -> dict:
    base = {"matricula": "7654321", "rural": True, "uf": "MA",
            "municipio_ibge": "2198765", "denominacao": "Fazenda Sucupira",
            "localizacao": "Rodovia BR-226, km 12, zona rural",
            "area_hectares": "48,5000",
            "valor_operacao": 9000000, "valor_base_calculo": 9000000}
    base.update(extra)
    return base


def parte(nome="MARIA DA SILVA", doc="52998224725", pct="100,00", **extra) -> dict:
    base = {"nome": nome, "documento": doc, "participacao": pct}
    base.update(extra)
    return base


def declaracao(**extra) -> dict:
    base = {"operacao": 11, "natureza_titulo": 2, "data_ato": "2026-08-13",
            "livro": "30", "folha": "181",
            "valor_operacao": 18500000, "valor_base_calculo": 18500000,
            "forma_pagamento": "5",
            "imovel": imovel_urbano(),
            "alienantes": [parte()],
            "adquirentes": [parte("JOÃO SOUSA", "11144477735")]}
    base.update(extra)
    return base


# ------------------------------------------------------------------ prazo

def test_o_prazo_e_o_ultimo_dia_util_do_mes_seguinte():
    # Ato em agosto de 2026: setembro termina em 30, que e uma quarta.
    assert DOI.prazo_de_entrega("2026-08-13") == "2026-09-30"
    # Ato em dezembro: o prazo cai no ano seguinte.
    assert DOI.prazo_de_entrega("2026-12-02")[:4] == "2027"


def test_o_prazo_nunca_cai_em_sabado_ou_domingo():
    from datetime import date
    for mes in range(1, 13):
        p = DOI.prazo_de_entrega(f"2026-{mes:02d}-05")
        d = date(int(p[0:4]), int(p[5:7]), int(p[8:10]))
        assert d.weekday() < 5, f"{p} caiu em fim de semana"


def test_numero_de_controle_tem_seis_digitos_e_o_ano():
    assert DOI.numero_de_controle(1, 2026) == "00000126"
    assert DOI.numero_de_controle(118001, 2023) == "11800123"
    assert len(DOI.numero_de_controle(7, 2026)) == 8


# --------------------------------------------------------------- dinheiro

def test_valor_sai_de_centavos_sem_float():
    assert DOI.valor_doi(18500000) == "185000.00"
    assert DOI.valor_doi(5) == "0.05"
    assert DOI.valor_doi(10 + 20) == "0.30"
    assert DOI.valor_doi(None) is None


# ----------------------------------------------- uma declaração por imóvel

def test_de_um_ato_com_tres_imoveis_saem_tres_declaracoes():
    # "Deve ser enviada uma declaracao para cada imovel alienado ou adquirido."
    ato = {"id": 1, "data": "2026-08-13", "livro": "30", "folha": "181",
           "doi_transacao": 11}
    decs = DOI.declaracoes_do_ato(ato, [imovel_urbano(), imovel_urbano(),
                                        imovel_rural()],
                                  [parte()], [parte("JOÃO", "11144477735")])
    assert len(decs) == 3
    assert all(d["operacao"] == 11 for d in decs)
    assert all(d["ato_id"] == 1 for d in decs)


def test_na_permuta_cada_imovel_leva_os_seus_lados():
    # Quem aliena um imovel adquire o outro. Montando do ato para baixo, os
    # lados sairiam trocados na segunda declaracao.
    a = parte("ANA", "52998224725")
    b = parte("BRUNO", "11144477735")
    ato = {"id": 2, "data": "2026-08-13", "doi_transacao": 13}
    imoveis = [imovel_urbano(alienantes=[a], adquirentes=[b]),
               imovel_urbano(alienantes=[b], adquirentes=[a])]
    decs = DOI.declaracoes_do_ato(ato, imoveis, [], [])
    assert decs[0]["alienantes"][0]["nome"] == "ANA"
    assert decs[0]["adquirentes"][0]["nome"] == "BRUNO"
    assert decs[1]["alienantes"][0]["nome"] == "BRUNO"
    assert decs[1]["adquirentes"][0]["nome"] == "ANA"


def test_permuta_com_torna_exporta_operacao_e_dinheiro():
    dec = declaracao(operacao=13, valor_operacao=12000000,
                      houve_permuta=True, houve_pagamento_dinheiro=True,
                      valor_especie=1000000)
    reg = DOI.declarar(dec, "000000", "2198765")
    assert reg["tipoOperacaoImobiliaria"] == "13"
    assert reg["indicadorPermutaBens"] is True
    assert reg["indicadorPagamentoDinheiro"] is True
    assert reg["valorPagoMoedaCorrenteDataAto"] == 10000.0
    assert reg["valorOperacaoImobiliaria"] == 120000.0


def test_papel_explicito_e_local_ao_ato():
    partes = [dict(nome="JERLAN", qualificacao="", doi_lado="ADQUIRENTE",
                   participacao="50,00"),
              dict(nome="LEIDE", qualificacao="", doi_lado="ADQUIRENTE",
                   participacao="50,00"),
              dict(nome="MUNICIPIO", qualificacao="DOMINIO DIRETO",
                   doi_lado="")]
    alienantes, adquirentes, duvidas = DOI.lados_das_partes(partes)
    assert not alienantes
    assert [p["nome"] for p in adquirentes] == ["JERLAN", "LEIDE"]
    assert [p["nome"] for p in duvidas] == ["MUNICIPIO"]
    assert DOI.conferir_participacoes(adquirentes, "adquirentes") == []


# ------------------------------------------------------------ conferência

def test_declaracao_completa_passa():
    assert DOI.conferir_declaracao(declaracao()) == []


def test_operacao_desativada_nao_passa():
    # A Receita substituiu Doacao (53) por 55 e 67; Desapropriacao (25) por 63
    # e 64. Usar o codigo antigo faz a declaracao ser recusada.
    for codigo in (25, 27, 43, 49, 51, 53):
        problemas = DOI.conferir_declaracao(declaracao(operacao=codigo))
        assert any("desativada" in x.motivo for x in problemas), codigo
        # E diz qual e o codigo de hoje, para nao virar adivinhacao.
        assert any("o código de hoje é" in x.motivo for x in problemas), codigo


def test_a_soma_das_participacoes_fica_entre_99_e_100():
    # Tres herdeiros com 33,33% somam 99,99: passa.
    tres = [parte("A", "52998224725", "33,33"),
            parte("B", "11144477735", "33,33"),
            parte("C", "52998224725", "33,33")]
    assert DOI.conferir_participacoes(tres, "alienantes") == []
    # 98% nao passa.
    problemas = DOI.conferir_participacoes(
        [parte("A", "52998224725", "98,00")], "alienantes")
    assert any("99,00%" in x.motivo for x in problemas)
    # 101% tambem nao.
    problemas = DOI.conferir_participacoes(
        [parte("A", "52998224725", "50,50"),
         parte("B", "11144477735", "50,50")], "alienantes")
    assert any("100,00%" in x.motivo for x in problemas)


def test_parte_sem_percentual_e_apontada_pelo_nome():
    problemas = DOI.conferir_participacoes(
        [{"nome": "MARIA DA SILVA", "documento": "52998224725"}], "alienantes")
    assert any("MARIA DA SILVA" in x.motivo for x in problemas)


def test_declaracao_sem_alienante_ou_sem_adquirente_nao_passa():
    assert any(x.campo == "alienantes"
               for x in DOI.conferir_declaracao(declaracao(alienantes=[])))
    assert any(x.campo == "adquirentes"
               for x in DOI.conferir_declaracao(declaracao(adquirentes=[])))


def test_cpf_invalido_barra_a_declaracao():
    problemas = DOI.conferir_declaracao(
        declaracao(alienantes=[parte("MARIA", "00000000000")]))
    assert any("dígito verificador" in x.motivo for x in problemas)


def test_sem_valor_da_operacao_ou_sem_base_de_calculo_nao_passa():
    assert any(x.campo == "valor_operacao"
               for x in DOI.conferir_declaracao(declaracao(valor_operacao=None)))
    assert any(x.campo == "valor_base_calculo"
               for x in DOI.conferir_declaracao(declaracao(valor_base_calculo=None)))


# ------------------------------------------------ metro quadrado e hectare

def test_imovel_urbano_com_area_em_hectares_e_apontado():
    # O erro que passa despercebido porque o numero continua parecendo certo.
    dec = declaracao(imovel=imovel_urbano(area_hectares="48,5"))
    problemas = DOI.conferir_declaracao(dec)
    assert any("hectares" in x.motivo and "metros quadrados" in x.motivo
               for x in problemas)


def test_imovel_rural_com_area_em_metros_quadrados_e_apontado():
    dec = declaracao(imovel=imovel_rural(area_terreno="485000"))
    problemas = DOI.conferir_declaracao(dec)
    assert any("hectares" in x.motivo for x in problemas)


def test_imovel_rural_exige_denominacao_e_localizacao():
    dec = declaracao(imovel=imovel_rural(denominacao=None, localizacao=None))
    campos = {x.campo for x in DOI.conferir_declaracao(dec)}
    assert "imovel.denominacao" in campos and "imovel.localizacao" in campos


def test_imovel_sem_matricula_nem_transcricao_nao_passa():
    dec = declaracao(imovel=imovel_urbano(matricula=None, transcricao=None))
    assert any(x.campo == "imovel.matricula" for x in DOI.conferir_declaracao(dec))


def test_o_cib_tem_oito_digitos():
    assert DOI.cib_valido("12345678") is True
    assert DOI.cib_valido("123456") is False
    assert DOI.cib_valido("") is None          # imóvel sem CIB é admitido


# ------------------------------------------------------------- montagem

def test_o_registro_e_montado_pelo_ri_ctp_com_os_nomes_do_layout():
    # Delegado de proposito: a CTP usa o mesmo formato de arquivo da DOI-Web, e
    # o ri_ctp tirou os nomes da especificacao publicada. Dois montadores
    # divergiriam no primeiro campo que mudasse.
    reg = DOI.declarar(declaracao(), "000000", "2198765")
    for campo in ("tipoDeclaracao", "tipoServico", "dataLavraturaRegistroAverbacao",
                  "tipoOperacaoImobiliaria", "valorOperacaoImobiliaria",
                  "valorBaseCalculoItbiItcmd", "formaPagamento", "destinacao",
                  "alienantes", "adquirentes"):
        assert campo in reg, campo
    assert reg["tipoOperacaoImobiliaria"] == "11"
    assert reg["valorOperacaoImobiliaria"] == 185000.0
    assert reg["destinacao"] == "1"          # urbano


def test_as_partes_levam_o_cpf_para_dentro_do_registro():
    # A primeira versao passava a chave errada e as partes saiam com
    # "indicadorNiIdentificado": false. Uma declaracao sem quem alienou e
    # PIOR do que uma recusada, porque a Receita aceita.
    reg = DOI.declarar(declaracao(), "000000", "2198765")
    assert reg["alienantes"][0]["ni"] == "52998224725"
    assert reg["alienantes"][0]["indicadorNiIdentificado"] is True
    assert reg["adquirentes"][0]["ni"] == "11144477735"
    assert reg["alienantes"][0]["participacao"] == 100.0


def test_os_indicadores_da_parte_dizem_a_verdade():
    # Eram False fixo. O manual exige que digam o que e.
    dec = declaracao(alienantes=[parte(estrangeiro=True, espolio=True,
                                       conjuge_documento="11144477735",
                                       regime_bens="1",
                                       conjuge_participante=True,
                                       por_representante=True)])
    a = DOI.declarar(dec, "000000", "2198765")["alienantes"][0]
    assert a["indicadorEstrangeiro"] is True
    assert a["indicadorEspolio"] is True
    assert a["indicadorConjuge"] is True
    # OS NOMES DO DOI-WEB, e não os da CTP — 22/10/2026: o layout oficial
    # (`/api/layout-doiweb.json`) chama o cônjuge de `cpfConjuge` e
    # `indicadorConjugeParticipa`; `niConjuge` e `…Participante` não existem lá.
    assert a["cpfConjuge"] == "11144477735"
    assert a["indicadorCpfConjugeIdentificado"] is True
    assert a["indicadorConjugeParticipa"] is True
    assert "niConjuge" not in a and "indicadorConjugeParticipante" not in a
    assert a["indicadorRepresentante"] is True


def test_parte_sem_conjuge_nao_ganha_campo_de_conjuge():
    a = DOI.declarar(declaracao(), "000000", "2198765")["alienantes"][0]
    assert a["indicadorConjuge"] is False
    assert "cpfConjuge" not in a and "regimeBens" not in a


def test_a_escritura_sai_no_layout_oficial_do_doi_web():
    """Escritura e registro vão no MESMO arquivo; o DOI-Web recusa campo que
    não está no layout dele — e recusou, na DOI de 09/2026, a chave
    `IndicadorNaoConsta…` com «I» maiúsculo."""
    import ri_doi
    reg = DOI.declarar(declaracao(), "000000", "2198765")
    assert ri_doi.conferir_layout(reg) == []
    sem_base = DOI.declarar(declaracao(valor_base_calculo=None), "000000", "2198765")
    assert sem_base.get("indicadorNaoConstaValorBaseCalculoItbiItcmd") is True
    assert "IndicadorNaoConstaValorBaseCalculoItbiItcmd" not in sem_base


def test_o_registro_rural_vai_com_destinacao_3_e_denominacao():
    reg = DOI.declarar(declaracao(imovel=imovel_rural()), "000000", "2198765")
    assert reg["destinacao"] == "3"
    assert reg["denominacao"] == "Fazenda Sucupira"
    assert "tipoLogradouro" not in reg      # campo de urbano não vaza no rural


def test_centavos_viram_reais_sem_passar_por_float():
    assert DOI._reais(18500000) == "185000,00"
    assert DOI._reais(5) == "0,05"
    assert DOI._reais(10 + 20) == "0,30"
    assert DOI._reais(None) is None


# --------------------------------------------------------------- domínios

def test_o_dominio_vem_do_ri_ctp_e_nao_de_uma_copia():
    # Uma fonte so. Se alguem recriar a tabela aqui, este teste cai.
    import ri_ctp
    assert DOI.TIPO_OPERACAO is ri_ctp.TIPO_OPERACAO
    assert DOI.TIPO_IMOVEL is ri_ctp.TIPO_IMOVEL
    assert DOI.FORMA_PAGAMENTO is ri_ctp.FORMA_PAGAMENTO
    assert len(DOI.TIPO_OPERACAO) == 33
    assert DOI.TIPO_OPERACAO["11"] == "Compra e venda"
    assert DOI.TIPO_OPERACAO["74"] == "Usucapião"


def test_a_operacao_19_e_dacao_e_nao_doacao():
    # O E-Oficio grava "Doacao em Pagamento", e esta errado: dacao em pagamento
    # (art. 356 do Codigo Civil) e outro instituto. A primeira versao deste
    # modulo copiou o erro do E-Oficio.
    assert DOI.TIPO_OPERACAO["19"] == "Dação em pagamento"


def test_as_formas_de_pagamento_sao_os_codigos_oficiais():
    # Numericos, e nao rotulos simbolicos inventados.
    assert set(DOI.FORMA_PAGAMENTO) == {"5", "7", "9", "10", "11"}
    assert DOI.FORMA_PAGAMENTO["5"] == "Quitado à vista"


def test_resumo_agrupa_os_motivos():
    impedidas = [{"problemas": [{"campo": "valor_operacao", "motivo": "sem valor"}]},
                 {"problemas": [{"campo": "valor_operacao", "motivo": "sem valor"},
                                {"campo": "imovel", "motivo": "sem imóvel"}]}]
    r = DOI.resumo_impedimentos(impedidas)
    assert r[0] == {"campo": "valor_operacao", "motivo": "sem valor",
                    "declaracoes": 2}


# --------------------------------------------------------------- carga DOI-Web

def test_a_carga_doi_web_usa_envelope_declaracoes():
    # Fonte: DOI_000000_202608_Livro30_fls184-192.json — upload = {"declaracoes":[...]}
    # sem cns/competencia/quantidade/numeroControle no JSON.
    reg = DOI.declarar(declaracao(), "000001", "2198765")
    carga = json.loads(DOI.gerar_carga([reg], "000001", "2026-08"))
    assert set(carga.keys()) == {"declaracoes"}
    assert len(carga["declaracoes"]) == 1
    assert "cns" not in carga and "competencia" not in carga
    assert "quantidade" not in carga
    assert "numeroControle" not in carga["declaracoes"][0]
    assert "registros" not in carga
    assert DOI.ESQUEMA_CONFERIDO is True


def test_numero_de_controle_continua_disponivel_fora_do_json():
    assert DOI.numero_de_controle(3, 2026) == "00000326"


def test_escritura_sai_com_tipo_servico_e_tipo_ato_1():
    # Manual + sample Livro 30: tipoServico=1 (notarial), tipoAto=1 (escritura).
    reg = DOI.declarar(declaracao(), "000001", "2198765")
    assert reg["tipoServico"] == "1"
    assert reg["tipoAto"] == "1"


def test_cib_vazio_nao_emite_a_chave():
    # Sample mat. 4011: CIB omitido quando vazio (nao emitir chave cib vazia).
    reg = DOI.declarar(declaracao(imovel=imovel_rural(cib=None)), "000001", "2198765")
    assert "cib" not in reg
    reg2 = DOI.declarar(declaracao(imovel=imovel_rural(cib="")), "000001", "2198765")
    assert "cib" not in reg2


def test_registro_rural_leva_tipo_imovel_69():
    reg = DOI.declarar(declaracao(imovel=imovel_rural()), "000001", "2198765")
    assert reg["tipoImovel"] == "69"
    assert reg["destinacao"] == "3"


def test_conjuge_do_comprador_singular_nao_vira_adquirente():
    # LEIA-ME fls 184-192: conjugue do comprador NAO entra como adquirente
    # quando o outorgado e singular. Qualificacao so "CONJUGE" cai em duvida
    # (nao esta em QUEM_ADQUIRE). doi_lado=FORA tambem tira do negocio.
    partes = [
        {"nome": "VENDEDOR A", "qualificacao": "VENDEDOR(A)", "documento": "52998224725"},
        {"nome": "COMPRADOR B", "qualificacao": "COMPRADOR(A)", "documento": "11144477735"},
        {"nome": "CONJUGE C", "qualificacao": "CONJUGE", "documento": "39053344705"},
    ]
    alienantes, adquirentes, duvidas = DOI.lados_das_partes(partes)
    assert [p["nome"] for p in alienantes] == ["VENDEDOR A"]
    assert [p["nome"] for p in adquirentes] == ["COMPRADOR B"]
    assert [p["nome"] for p in duvidas] == ["CONJUGE C"]
    # Marcacao explicita FORA (tela) — conjugue nao vai para a declaracao.
    partes2 = [
        {"nome": "VENDEDOR A", "qualificacao": "VENDEDOR(A)"},
        {"nome": "COMPRADOR B", "qualificacao": "COMPRADOR(A)"},
        {"nome": "CONJUGE C", "qualificacao": "CONJUGE", "doi_lado": "FORA"},
    ]
    a2, d2, u2 = DOI.lados_das_partes(partes2)
    assert [p["nome"] for p in d2] == ["COMPRADOR B"]
    assert u2 == []
    assert "CONJUGE C" not in [p["nome"] for p in a2 + d2]


def test_parte_usa_indicador_ni_identificado():
    reg = DOI.declarar(declaracao(), "000001", "2198765")
    assert "indicadorNiIdentificado" in reg["alienantes"][0]
    assert "identificadorNiIdentificado" not in reg["alienantes"][0]
    assert reg["alienantes"][0]["indicadorNiIdentificado"] is True

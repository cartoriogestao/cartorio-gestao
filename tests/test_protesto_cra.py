"""
Testes do contrato da CRA e da CENPROT.

O QUE ELES CONFEREM, E CONTRA O QUE
    Contra os esquemas OFICIAIS que estavam na maquina da serventia:
    `v1_21.xsd`, `v1_22-apontamento.xsd` e `v1_22-geral.xsd`. Os numeros —
    64 especies, 76 irregularidades, 11 ocorrencias entre as duas versoes —
    saem de lá, e nao de escolha minha.

AS TRES COISAS QUE SO SE VEM CONFRONTANDO ESQUEMA E ACERVO
    1. O esquema declara SJ e TS DUAS VEZES, com redacao diferente.
    2. O acervo tem ATC e CTI, dez titulos reais, que o esquema nao tem.
    3. O acervo grava 'C' 1.027 vezes como ocorrencia, e 'C' nao e ocorrencia
       da CRA — e codigo interno do E-Oficio.

    Nenhuma das tres foi silenciada: cada uma tem tabela propria no modulo e
    teste proprio aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import protesto_cra as CRA                      # noqa: E402


# ------------------------------------------------------------ os dominios

def test_o_contrato_tem_os_numeros_do_esquema_oficial():
    assert len(CRA.ESPECIES) == 64            # 66 enumeracoes, 2 duplicadas
    assert len(CRA.IRREGULARIDADES) == 76
    assert len(CRA.TIPOS_DE_PROTESTO) == 2
    assert len(CRA.MOTIVOS_DE_PROTESTO) == 3
    assert len(CRA.TIPOS_DE_ENDOSSO) == 3
    assert len(CRA.TIPOS_DE_APRESENTANTE) == 5
    assert len(CRA.UFS) == 28                 # 27 e EX, para o exterior


def test_todo_codigo_tem_rotulo_escrito():
    for tabela in (CRA.ESPECIES, CRA.IRREGULARIDADES, CRA.TIPOS_DE_PROTESTO,
                   CRA.MOTIVOS_DE_PROTESTO, CRA.TIPOS_DE_ENDOSSO,
                   CRA.TIPOS_DE_APRESENTANTE, CRA.ORIGENS_DE_ANUENCIA):
        for codigo, texto in tabela.items():
            assert texto and texto.strip(), codigo


def test_as_duas_especies_que_o_acervo_mais_usa():
    # DMI e CDA sao 92% do movimento desta serventia.
    assert CRA.ESPECIES["DMI"] == "Duplicata de Venda Mercantil por Indicação"
    assert CRA.ESPECIES["CDA"] == "Certidão da Dívida Ativa"


def test_o_esquema_oficial_declara_duas_especies_em_duplicidade():
    assert set(CRA.DUPLICADAS_NO_ESQUEMA) == {"SJ", "TS"}
    # Ficou a redacao completa, com acento.
    assert CRA.ESPECIES["SJ"] == "Sentença Judicial"
    assert CRA.ESPECIES["TS"] == "Triplicata de Prestação de Serviços"


# ------------------------------------------------------------- as especies

def test_a_especie_do_acervo_que_o_esquema_nao_tem_e_aceita_com_aviso():
    # Dez titulos reais, apontados e protestados. Recusar agora seria perder
    # o acervo; aceitar em silencio seria mandar dado invalido para a CRA.
    for codigo in ("ATC", "CTI"):
        a = CRA.especie(codigo)
        assert a["no_esquema"] is False
        assert "ausente dos esquemas" in a["observacao"]


def test_especie_inventada_e_recusada_com_dica_de_balcao():
    with pytest.raises(CRA.CraError) as erro:
        CRA.especie("XPTO")
    assert "DMI" in str(erro.value) and "CDA" in str(erro.value)


def test_a_especie_nao_se_importa_com_caixa_nem_espaco():
    assert CRA.especie(" dmi ")["codigo"] == "DMI"


# ---------------------------------------------------------- as ocorrencias

def test_a_ocorrencia_e_conferida_contra_a_versao_do_arquivo():
    # 'W' — averbacao de titulo ja protestado — vale na 1.21 e nao vale num
    # arquivo de apontamento 1.22.
    assert CRA.ocorrencia("W", "1.21")["rotulo"].startswith("Averbação")
    with pytest.raises(CRA.CraError) as erro:
        CRA.ocorrencia("W", "1.22-apontamento")
    assert "não vale na versão" in str(erro.value)
    # E '0' — apontamento — e o contrario: so na 1.22.
    assert CRA.ocorrencia("0", "1.22-apontamento")["rotulo"] == "Apontamento"
    with pytest.raises(CRA.CraError):
        CRA.ocorrencia("0", "1.21")


def test_as_ocorrencias_que_valem_nas_duas_versoes():
    for codigo, rotulo in (("1", "Pago"), ("2", "Protestado"),
                           ("3", "Retirado"), ("A", "Protesto cancelado")):
        for versao in ("1.21", "1.22-apontamento", "1.22-geral"):
            assert CRA.ocorrencia(codigo, versao)["rotulo"] == rotulo


def test_o_codigo_interno_do_eoficio_nao_passa_por_ocorrencia():
    # 'C' aparece 1.027 vezes em tbProtesto_RO e nao e ocorrencia da CRA.
    # Traduzi-lo como se fosse mandaria dado invalido para a Central.
    with pytest.raises(CRA.CraError) as erro:
        CRA.ocorrencia("C")
    assert "código interno do E-Ofício" in str(erro.value)
    assert "1.027" in str(erro.value)


# ------------------------------------------------------- as irregularidades

def test_a_duplicidade_do_acervo_tem_codigo_oficial():
    # `tbProtestoGratuito` gravava "TITULO APRESENTADO EM DUPLICIDADE" como
    # texto livre. O codigo 52 diz a mesma coisa, e a CRA entende.
    assert CRA.irregularidade("52")["rotulo"] == "Título apresentado em duplicidade"


def test_as_irregularidades_que_o_acervo_usou():
    # Sao duas, e as duas existem no contrato.
    assert CRA.irregularidade("52")["codigo"] == "52"
    assert CRA.irregularidade("15")["rotulo"].startswith("Praça de pagamento")


def test_irregularidade_fora_da_faixa_e_recusada():
    with pytest.raises(CRA.CraError) as erro:
        CRA.irregularidade("75")
    assert "76 códigos" in str(erro.value)


# ----------------------------------------------------------------- rotulos

def test_o_rotulo_devolve_vazio_em_vez_de_quebrar_a_tela():
    # Tela que quebra porque o arquivo trouxe codigo novo e pior que tela que
    # mostra o codigo cru ao lado do resto do titulo.
    assert CRA.rotulo("especie", "DMI").startswith("Duplicata")
    assert CRA.rotulo("especie", "NAO_EXISTE") == ""
    assert CRA.rotulo("tipo_protesto", "F") == "Falimentar"


def test_dominio_inexistente_e_erro_de_programa_e_nao_de_dado():
    with pytest.raises(CRA.CraError) as erro:
        CRA.rotulo("cor_do_papel", "azul")
    assert "não existe" in str(erro.value)


# ------------------------------------------------------------- a conferencia

def titulo_bom() -> dict:
    return {
        "especie": "DMI",
        "numero_titulo": "84713/1",
        "data_emissao": "2022-07-21",
        "data_vencimento": "2022-09-05",
        "valor": "1482.78",
        "saldo": "1482.78",
        "praca_protesto": "CIDADE EXEMPLO",
        "tipo_moeda": "1",
        "tipo_protesto": "C",
        "motivo_protesto": "1",
        "devedores": [{"nome": "«mascarado»", "CNPJ": "00000000000000",
                       "enderecos": [{"endereco": "Rua X", "cidade": "Cidade Exemplo",
                                      "uf": "MA"}]}],
    }


def test_titulo_em_ordem_nao_tem_achado():
    assert CRA.conferir_titulo(titulo_bom()) == []


def test_titulo_sem_devedor_e_recusado():
    t = titulo_bom()
    t["devedores"] = []
    assert any("ao menos um devedor" in f for f in CRA.conferir_titulo(t))


def test_devedor_sem_endereco_avisa_que_vai_para_edital():
    t = titulo_bom()
    t["devedores"][0]["enderecos"] = []
    faltas = CRA.conferir_titulo(t)
    assert any("sai por edital" in f for f in faltas)


def test_devedor_sem_documento_e_recusado():
    t = titulo_bom()
    t["devedores"][0].pop("CNPJ")
    assert any("sem CPF nem CNPJ" in f for f in CRA.conferir_titulo(t))


def test_falta_de_campo_obrigatorio_aparece_com_o_nome_em_portugues():
    t = titulo_bom()
    t["numero_titulo"] = ""
    assert "Falta numero titulo." in CRA.conferir_titulo(t)


def test_titulo_sem_vencimento_e_aceito():
    """CORRECAO DE 25/08/2026, achada medindo as remessas reais.

    `data_vencimento` estava na lista de obrigatorios, e nao devia: 37 dos
    343 titulos das remessas reais chegam da PROPRIA CENTRAL com `99999999`
    nas posicoes 236-243, que e a marca de sem vencimento — todos da especie
    CDA, certidao de divida ativa, que nao tem vencimento nenhum.

    E o contrato ja tem palavra para o caso: a irregularidade 33 e "Falta
    data de vencimento no titulo". Titulo sem vencimento e titulo com
    irregularidade catalogada, e nao arquivo torto — recusa-lo na porta faria
    o balcao digitar a mao 11% do que a Central manda pronto.
    """
    t = titulo_bom()
    t["data_vencimento"] = ""
    assert CRA.conferir_titulo(t) == []
    assert CRA.IRREGULARIDADES["33"] == "Falta data de vencimento no título"


def test_a_conferencia_junta_todas_as_faltas_de_uma_vez():
    # Balcao nao aceita corrigir um erro por vez.
    t = titulo_bom()
    t["especie"] = "XPTO"
    t["valor"] = ""
    t["devedores"] = []
    faltas = CRA.conferir_titulo(t)
    assert len(faltas) >= 3


def test_a_conferencia_respeita_o_limite_de_nove_irregularidades():
    t = titulo_bom()
    t["irregularidades"] = [str(i) for i in range(1, 11)]
    assert any("máximo nove" in f for f in CRA.conferir_titulo(t))


def test_a_conferencia_confere_a_ocorrencia_contra_a_versao():
    t = titulo_bom()
    t["ocorrencia"] = "W"
    assert CRA.conferir_titulo(t, "1.21") == []
    assert any("não vale na versão" in f
               for f in CRA.conferir_titulo(t, "1.22-apontamento"))


def test_a_serventia_e_o_codigo_01_nas_duas_centrais():
    assert CRA.CODIGO_CRA == "01"
    assert CRA.CODIGO_CENPROT == "01"

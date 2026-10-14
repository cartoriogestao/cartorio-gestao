"""Configuração das etiquetas térmicas da casa.

Registro do RCPJ/RTD e reconhecimento compartilham a bobina de 100 × 30 mm e
sua calibração física. A composição do registro mantém corpo, entrelinha e QR
em chaves próprias. Os testes também guardam a recuperação de números inválidos
e o uso legítimo de zero nos deslocamentos.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import etiqueta as ETQ


def com(**gravadas):
    """Um `get_settings` de mentira, com o que estiver gravado."""
    return lambda: dict(gravadas)


# ---------------------------------------------- o que foi medido, medido


def test_o_reconhecimento_e_100_por_30():
    m = ETQ.medidas(com(), ETQ.RECONHECIMENTO)
    assert (m["etiqueta_largura_mm"], m["etiqueta_altura_mm"]) == (100.0, 30.0)
    assert m["etiqueta_corpo_pt"] == float(ETQ.PADRAO_DO_RECONHECIMENTO["etiqueta_corpo_pt"])


def test_o_registro_do_rcpj_rtd_e_100_por_30():
    m = ETQ.medidas_registro_rtdpj(com())
    assert (m["etiqueta_largura_mm"], m["etiqueta_altura_mm"]) == (100.0, 30.0)
    assert m["etiqueta_corpo_pt"] == 6.0


def test_as_duas_usam_a_mesma_tira_com_tipografia_propria():
    a = ETQ.medidas(com(), ETQ.RECONHECIMENTO)
    b = ETQ.medidas_registro_rtdpj(com())
    assert (a["etiqueta_largura_mm"], a["etiqueta_altura_mm"]) \
        == (b["etiqueta_largura_mm"], b["etiqueta_altura_mm"])
    assert a["etiqueta_corpo_pt"] != b["etiqueta_corpo_pt"]


# ---------------------------------------- as chaves com que cada uma grava


def test_as_chaves_do_reconhecimento_NAO_MUDARAM():
    """**O oficial já pode ter ajustado a tira dele no balcão.** Prefixar estas
    chaves agora faria o sistema ler o padrão de fábrica por cima do ajuste
    dele — e ninguém saberia por quê. É por isso que o prefixo do
    reconhecimento é vazio, e não por descuido de simetria."""
    assert ETQ.PREFIXO_DA_CONFIGURACAO[ETQ.RECONHECIMENTO] == ""
    for medida in ETQ.MEDIDAS:
        assert ETQ.chave_gravada(ETQ.RECONHECIMENTO, medida) == medida


def test_o_registro_compartilha_geometria_e_grava_tipografia_propria():
    for medida in ETQ.GEOMETRIA_COMPARTILHADA_RTDPJ:
        assert ETQ.chave_registro_rtdpj(medida) == medida
    for medida in ("etiqueta_corpo_pt", "etiqueta_entrelinha", "etiqueta_qr_mm"):
        assert ETQ.chave_registro_rtdpj(medida).startswith("etiqueta_registro_")


def test_nenhuma_chave_de_uma_colide_com_a_da_outra():
    a = {ETQ.chave_gravada(ETQ.RECONHECIMENTO, m) for m in ETQ.MEDIDAS}
    b = {ETQ.chave_gravada(ETQ.REGISTRO_RTDPJ, m) for m in ETQ.MEDIDAS}
    assert not (a & b), f"chave gravada em comum: {sorted(a & b)}"


def test_padrao_gravado_traz_o_nome_com_que_a_tela_grava():
    """A tela de ajuste percorre isto: ela precisa do nome com que grava, e não
    do nome da medida."""
    padrao = ETQ.padrao_gravado(ETQ.REGISTRO_RTDPJ)
    assert padrao["etiqueta_registro_largura_mm"] == "100"
    assert set(padrao) == {ETQ.chave_gravada(ETQ.REGISTRO_RTDPJ, m)
                           for m in ETQ.MEDIDAS}


def test_as_duas_declaram_as_MESMAS_medidas():
    """O nome da medida é o mesmo nas duas — é o que permite ao modelo de tela
    ler `m.etiqueta_largura_mm` sem saber de qual etiqueta é."""
    for configuracao in ETQ.configuracoes():
        assert set(ETQ.PADROES[configuracao]) == set(ETQ.MEDIDAS)


# -------------------------------------------------- a leitura das medidas


def test_o_que_esta_gravado_vence_o_padrao():
    m = ETQ.medidas(com(etiqueta_registro_altura_mm="45"), ETQ.REGISTRO_RTDPJ)
    assert m["etiqueta_altura_mm"] == 45.0


def test_a_virgula_do_balcao_e_lida_como_decimal():
    m = ETQ.medidas(com(etiqueta_registro_entrelinha="1,05"), ETQ.REGISTRO_RTDPJ)
    assert m["etiqueta_entrelinha"] == 1.05


def test_numero_invalido_nao_vira_etiqueta_em_branco():
    """Alguém digita «10 mm» com a unidade junto, e a impressão do balcão
    para."""
    m = ETQ.medidas(com(etiqueta_registro_largura_mm="10 mm"),
                    ETQ.REGISTRO_RTDPJ)
    assert m["etiqueta_largura_mm"] == 100.0


def test_o_zero_SO_VALE_para_o_deslocamento():
    """Largura zero, corpo zero ou entrelinha zero são a tira em branco por
    outro caminho; deslocamento zero é a resposta certa — quer dizer «o driver
    não empurrou nada»."""
    m = ETQ.medidas(com(etiqueta_registro_largura_mm="0",
                        etiqueta_registro_corpo_pt="0",
                        etiqueta_registro_deslocamento_x_mm="0"),
                    ETQ.REGISTRO_RTDPJ)
    assert m["etiqueta_largura_mm"] == 100.0
    assert m["etiqueta_corpo_pt"] == 6.0
    assert m["etiqueta_deslocamento_x_mm"] == 0.0


def test_o_registro_le_a_geometria_compartilhada_e_a_tipografia_propria():
    gravadas = com(etiqueta_altura_mm="28", etiqueta_registro_altura_mm="45",
                   etiqueta_registro_corpo_pt="5.5")
    registro = ETQ.medidas_registro_rtdpj(gravadas)
    assert registro["etiqueta_altura_mm"] == 28.0
    assert registro["etiqueta_corpo_pt"] == 5.5
    assert ETQ.medidas(gravadas, ETQ.RECONHECIMENTO)["etiqueta_altura_mm"] == 28.0


def test_configuracao_desconhecida_e_recusada():
    with pytest.raises(ValueError, match="etiqueta desta casa"):
        ETQ.medidas(com(), "ETIQUETA_QUE_NAO_EXISTE")


# ------------------------------------ a etiqueta da firma continua igual


def test_o_notas_web_le_pelo_MESMO_caminho():
    """**A máquina é uma, e isto se prova.** `notas_web.ETIQUETA_PADRAO` passou
    a ser o dicionário deste módulo — se alguém escrever de novo os números lá,
    as duas cópias divergem no primeiro conserto, que é o defeito da
    `normalizar_nome` pela enésima vez."""
    import notas_web
    fonte = Path(notas_web.__file__).read_text(encoding="utf-8")
    assert "ETIQUETA_PADRAO = ETQ.PADRAO_DO_RECONHECIMENTO" in fonte, (
        "as medidas da etiqueta de firma voltaram a ser escritas em "
        "`notas_web` — elas moram em `etiqueta.py`")
    assert "ETQ.medidas(db.get_settings, ETQ.RECONHECIMENTO)" in fonte

# ------------------------------------ averbação RCPN (margem do livro)


def test_averbacao_rcpn_tem_chaves_PROPRIAS():
    for medida in ETQ.MEDIDAS:
        propria = ETQ.chave_gravada(ETQ.AVERBACAO_RCPN, medida)
        assert propria.startswith("etiqueta_averbacao_")
        assert propria != medida


def test_averbacao_nao_colide_com_firma_nem_registro():
    a = {ETQ.chave_gravada(ETQ.RECONHECIMENTO, m) for m in ETQ.MEDIDAS}
    b = {ETQ.chave_gravada(ETQ.REGISTRO_RTDPJ, m) for m in ETQ.MEDIDAS}
    c = {ETQ.chave_gravada(ETQ.AVERBACAO_RCPN, m) for m in ETQ.MEDIDAS}
    assert not (a & c)
    assert not (b & c)


def test_averbacao_padrao_e_mais_estreita_que_firma():
    m = ETQ.medidas(com(), ETQ.AVERBACAO_RCPN)
    assert m["etiqueta_largura_mm"] < 100
    assert m["etiqueta_largura_mm"] == 55.0
    assert m["etiqueta_altura_mm"] == 50.0


def test_averbacao_aceita_qr_zero():
    m = ETQ.medidas(com(etiqueta_averbacao_qr_mm="0"), ETQ.AVERBACAO_RCPN)
    assert m["etiqueta_qr_mm"] == 0.0

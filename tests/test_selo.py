"""
O selo de fiscalizacao — codigo, texto, tabela de custas.

O QUE DA FORCA A ESTES TESTES
    Nao sao casos inventados. `tests/selos_reais.json` traz **um selo real de
    cada um dos 39 prefixos** que esta serventia usou entre 2020 e 2026,
    tirados de `tbSeloIndividual`. O modulo foi ensaiado contra os 25.634
    textos e os 26.130 codigos do acervo inteiro, e passou em 100% — a amostra
    aqui e o que cabe no repositorio para que a regressao continue presa.

    A regra da casa: teste que reproduz o fato real, nao o caminho felizinho.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import atribuicoes as ATR      # noqa: E402
import selo as S               # noqa: E402

REAIS = json.loads((Path(__file__).parent / "selos_reais.json").read_text(encoding="utf-8"))
TEXTOS = REAIS["textos"]
# O CNS da amostra sai dela mesma, e não se escreve aqui: a amostra é real e
# fica fora do repositório público, e o número da casa também (B3, 10/10/2026).
# O que se prova é que os 39 selos são da MESMA serventia.
CNS_DA_AMOSTRA = S.ler_codigo(TEXTOS[0].split("Selo: ", 1)[1].split(",", 1)[0]).cns

# O selo da prenotacao de 17/08/2026, o ultimo antes de o sistema novo entrar.
TEXTO = ("Poder Judiciário – TJMA. Selo: PRENOT000000ZEZSIN46Y2QXQM16, "
         "17/08/2026 08:50:12, Ato: 16.1, Parte(s): SAMUEL GOMES DE SOUSA, "
         "Total R$ 43,37 Emol R$ 38,72 FERC R$ 1,16 FADEP R$ 1,55 FEMP R$ 1,55 "
         "FERRFIS R$ 0,39 Consulte em https://selo.tjma.jus.br")


# ------------------------------------------------- o ensaio contra o acervo


def test_a_amostra_cobre_os_trinta_e_nove_prefixos():
    assert len(TEXTOS) == 39


@pytest.mark.parametrize("texto", TEXTOS)
def test_todo_selo_real_do_acervo_e_lido_sem_problema(texto):
    """Se um selo real deixar de ser lido, este teste cai — e é o que se quer."""
    assert S.conferir_texto(texto, CNS_DA_AMOSTRA) == []
    lido = S.ler_texto(texto)
    assert lido["faltando"] == []
    assert lido["codigo"] and lido["ato"] and lido["data"]
    assert lido["total"] is not None and lido["emolumentos"] is not None
    assert lido["fundos"], "todo selo do acervo reparte por fundo"


@pytest.mark.parametrize("texto", TEXTOS)
def test_a_conta_de_todo_selo_real_fecha(texto):
    lido = S.ler_texto(texto)
    soma = lido["emolumentos"] + sum(lido["fundos"].values())
    assert abs(soma - lido["total"]) <= 0.05, (
        f"emolumentos {lido['emolumentos']} + fundos {sum(lido['fundos'].values())} "
        f"não dão o total {lido['total']}")


@pytest.mark.parametrize("texto", TEXTOS)
def test_todo_codigo_real_e_desta_serventia(texto):
    codigo = S.ler_texto(texto)["codigo"]
    assert S.do_nosso_cns(codigo, CNS_DA_AMOSTRA)
    assert S.ler_codigo(codigo).prefixo in S.PREFIXOS


# ---------------------------------------------------------- o codigo


def test_o_codigo_se_decompoe_em_tipo_cns_e_identificacao():
    c = S.ler_codigo("PRENOT000000ZEZSIN46Y2QXQM16")
    assert c.prefixo == "PRENOT"
    assert c.cns == "000000"
    assert c.identificacao == "ZEZSIN46Y2QXQM16"
    assert c.antigo is False
    assert c.descricao == "Prenotação"


def test_o_formato_antigo_de_2020_continua_aceito():
    """488 selos do acervo têm 32 dígitos hexadecimais."""
    c = S.ler_codigo("0014FD81F65772E99C3B15027F281929")
    assert c.antigo is True
    assert c.prefixo is None
    assert "antigo" in c.descricao


def test_selo_de_outra_serventia_e_reconhecido_como_de_outra():
    assert S.do_nosso_cns("PRENOT000000ZEZSIN46Y2QXQM16", "000000") is True
    assert S.do_nosso_cns("PRENOT999999ZEZSIN46Y2QXQM16", "000000") is False


def test_selo_de_outra_serventia_e_apontado_na_conferencia():
    torto = TEXTO.replace("000000Z", "111111Z")
    problemas = S.conferir_texto(torto, "000000")
    assert any("não é desta serventia" in p for p in problemas)


@pytest.mark.parametrize("ruim", [
    "", "   ", "SELO", "12345", "PRENOT00000ZEZSIN46Y2QXQM16",
    "prenot000000", "0014FD81F65772E99C3B15027F28192",
])
def test_codigo_sem_forma_de_selo_e_recusado(ruim):
    with pytest.raises(S.SeloError):
        S.ler_codigo(ruim)


def test_a_mensagem_de_recusa_ensina_o_formato():
    with pytest.raises(S.SeloError, match="28"):
        S.ler_codigo("QUALQUERCOISA")


# ------------------------------------------------------------ o texto


def test_o_texto_do_selo_entrega_tudo_o_que_afirma():
    lido = S.ler_texto(TEXTO)
    assert lido["codigo"] == "PRENOT000000ZEZSIN46Y2QXQM16"
    assert lido["data"] == "17/08/2026"
    assert lido["hora"] == "08:50:12"
    assert lido["ato"] == "16.1"
    assert lido["partes"] == "SAMUEL GOMES DE SOUSA"
    assert lido["total"] == 43.37
    assert lido["emolumentos"] == 38.72
    assert lido["fundos"] == {"FERC": 1.16, "FEMP": 1.55, "FADP": 1.55, "FERRFIS": 0.39}
    assert lido["rotulado"] is True


def test_o_fundo_da_defensoria_e_lido_escrito_das_duas_formas():
    """O cadastro diz FADP; o Tribunal imprime FADEP."""
    assert S.ler_texto(TEXTO)["fundos"]["FADP"] == 1.55
    outro = TEXTO.replace("FADEP", "FADP")
    assert S.ler_texto(outro)["fundos"]["FADP"] == 1.55


def test_campo_ausente_vem_como_nada_e_nao_como_zero():
    """Afirmar zero emolumento sobre ato oneroso é pior que dizer «não sei»."""
    lido = S.ler_texto("Poder Judiciário – TJMA. Selo: AUTENT000000ABCDEFGHIJKLMN01")
    assert lido["total"] is None
    assert lido["emolumentos"] is None
    assert lido["fundos"] == {}
    assert set(lido["faltando"]) >= {"total", "emolumentos", "fundos", "ato"}


def test_o_selo_sem_rotulo_e_denunciado():
    """Foi o caso da certidão 6/2026: emolumentos gravados como «172,86»."""
    problemas = S.conferir_texto("172,86", "000000")
    assert any("código do selo" in p for p in problemas)
    assert any("Total" in p for p in problemas)


def test_emolumento_maior_que_o_total_e_apontado():
    torto = TEXTO.replace("Total R$ 43,37", "Total R$ 10,00")
    problemas = S.conferir_texto(torto, "000000")
    assert any("maiores que o total" in p for p in problemas)


def test_conta_que_nao_fecha_e_apontada():
    torto = TEXTO.replace("FERC R$ 1,16", "FERC R$ 100,00")
    problemas = S.conferir_texto(torto, "000000")
    assert any("conta não fecha" in p for p in problemas)


def test_texto_vazio_nao_estoura_e_diz_o_que_falta():
    for entrada in ("", None, "   "):
        lido = S.ler_texto(entrada)
        assert lido["faltando"]
        assert S.conferir_texto(entrada, "000000")


# --------------------------------------------------- a tabela de custas


def test_o_codigo_da_tabela_se_decompoe_em_tabela_e_vigencia():
    assert S.ler_tabela_de_custas("0520260101") == {
        "codigo": "0520260101", "tabela": "05", "vigencia": "2026-01-01"}
    assert S.ler_tabela_de_custas("0120220101")["tabela"] == "01"


@pytest.mark.parametrize("codigo", [
    "0520201012", "0520210328", "0520211012", "0520220101", "0120230101",
    "0220240101", "0320250101", "0320260101",
])
def test_todas_as_vigencias_observadas_no_acervo_sao_lidas(codigo):
    lido = S.ler_tabela_de_custas(codigo)
    assert lido["tabela"] in {"01", "02", "03", "05"}
    assert lido["vigencia"].startswith("20")


def test_monta_o_codigo_da_tabela_de_volta():
    assert S.codigo_da_tabela(5, "2026-01-01") == "0520260101"
    assert S.codigo_da_tabela("01", "2022-01-01") == "0120220101"


@pytest.mark.parametrize("ruim", ["", "5", "abc", "052026010", "0520260101X"])
def test_codigo_de_tabela_torto_e_recusado(ruim):
    with pytest.raises(S.SeloError):
        S.ler_tabela_de_custas(ruim)


def test_vigencia_torta_e_recusada():
    with pytest.raises(S.SeloError, match="AAAA-MM-DD"):
        S.codigo_da_tabela(5, "01/01/2026")


# ---------------------------------------------- caminhos, e as lacunas


def test_os_caminhos_observados_batem_com_o_acervo():
    assert S.CAMINHOS["NT_RECONHECIMENTO_FIRMA"] == "/selo/notas/reconhecimento-firma"
    assert S.CAMINHOS["RC_ATOS_EM_GERAL"] == "/selo/civil/atos-em-geral"
    assert S.CAMINHOS["RI_PRENOTACAO"] == "/selo/imovel/prenotacao"
    assert len(S.CAMINHOS) == 18
    espacos = {c.split("/")[2] for c in S.CAMINHOS.values()}
    assert espacos == {"notas", "civil", "imovel", "rtdpj"}


def test_a_lacuna_do_protesto_foi_fechada_pela_documentacao_oficial():
    """Ontem era lacuna. A documentação do Selador tem os dez caminhos."""
    import selador as SD
    assert S.LACUNAS == {}, "não há mais caminho desconhecido"
    assert len(SD.endpoints_de("protesto")) == 10
    assert "/selo/protesto/titulo" in SD.ENDPOINTS
    # e os caminhos que a serventia usou continuam sendo só os que ela usou
    assert not any("/protesto/" in c for c in S.CAMINHOS.values()), (
        "esta serventia nunca chamou um endpoint de protesto; o catálogo é outro")
    assert ATR.codigo_da_atribuicao("PROTESTO") == 2


def test_todo_prefixo_do_acervo_tem_nome():
    assert len(S.PREFIXOS) == 39
    for p, nome in S.PREFIXOS.items():
        assert nome and len(p) in (6, 7)


def test_as_inferencias_estao_marcadas_como_inferencia():
    """Nove prefixos de busca cujo significado exato ninguém documentou."""
    inferidos = [p for p, n in S.PREFIXOS.items() if "variante do acervo" in n]
    assert len(inferidos) == 9
    assert all(p.startswith(("BUS", "BUR", "BRI", "BRC")) for p in inferidos)

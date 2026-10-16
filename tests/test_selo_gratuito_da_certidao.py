"""O SELO GRATUITO DA CERTIDÃO DO CIVIL — o relato do Marcos Dione.

    «verifique o problema do selo gratuito de certidao do marcos dione»
                                            — o oficial, 10/09/2026

O QUE SE MEDIU NA PRODUÇÃO (só leitura)
    Assento **1233**, nascimento nº 9313 de 1996, origem `ARQUIVO`, sem ato de
    REGISTRO (só uma averbação). Três certidões: **16** (09/09 16:45),
    **17** (09/09 16:59) e **23** (10/09 11:27) — **as três sem selo**, duas
    já canceladas, e **nenhuma folha de segurança consumida**. As outras
    certidões do mesmo dia (19, 21, 22) saíram seladas e gastaram folha.

    A folha não se gastar é o sintoma que aponta o culpado: **ela só se gasta
    se o selo sair.**

A CAUSA, MEDIDA EM TRÊS FONTES
    O envelope do selo mandava, na gratuidade pedida no balcão, **só**
    `isentoGratuito: "GRATUITO"`. Esse par não existe:

      · **o contrato** do selador (`selador.py`, gerado da documentação
        oficial de 2017) não tem `isentoGratuito` em schema nenhum — zero
        ocorrências. O que ele declara é `CAMPOS_ISENTO = ("value", "motivo")`,
        num campo chamado **`isento`**;
      · **o acervo** concorda: `selador.ALEM_DA_DOCUMENTACAO` registra
        `DadosSeloCertidaoRI.isento` com **667 usos** medidos nos envelopes
        reais desta casa;
      · **os 26.177 selos** que a serventia emitiu têm a palavra `GRATUITO`
        em **zero** deles.

    E o aparelho já tinha respondido: em 08/09/2026 a averbação do CPF passou
    com `dadosSelo.isento = true` (HTTP 200, selo
    `AVERBA000000VBKH58VIXU0CLW81`, texto «Selo Isento»), e a forma que
    **falhou** foi a do `isentoGratuito` sozinho. A prenotação do RI manda a
    mesma coisa, e ali são 48 envelopes isentos em 829 medidos.

    **A correção de 08/09 foi aplicada à averbação e não à certidão** — é o
    mesmo conserto pela metade que já apareceu no rodapé da certidão em
    09/09: consertar um lado e deixar o outro.

O QUE ESTES TESTES NÃO PROVAM
    **Que o aparelho aceita.** Nada aqui fala com ele: pedir um selo de
    verdade gasta um selo, e isso é do balcão, não de um teste. O que se prova
    é que o envelope leva o campo que o contrato declara e que o aparelho já
    aceitou noutro caminho — a confirmação é uma certidão gratuita no balcão.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS
import selador

COMUNS = {"escrevente": "Debora Exemplo Reis", "livro": "A-10",
          "folha": "58", "termo": "9313",
          "nome_parte": "Braulio Galvao Oliveira Ribeiro",
          "versao_tabela": "20260101", "papel": "7225462"}


def envelope(**extra):
    return AS.envelope_do_civil(especie="NASCIMENTO", tipo="CERTIDAO",
                                **COMUNS, **extra)


# ------------------------------------------------- o campo do contrato


def test_a_gratuidade_da_certidao_leva_o_campo_ISENTO():
    """**O CONSERTO.** Sem `isento`, o aparelho não vê isenção nenhuma — e a
    certidão saía sem selo."""
    dados = envelope(isento=True,
                     motivo_isencao="hipossuficiência")["dadosSelo"]
    assert dados["isento"] is True
    assert dados["motivoIsentoGratuito"] == "HIPOSSUFICIÊNCIA"


def test_o_motivo_vai_em_maiuscula_como_nos_medidos():
    dados = envelope(isento=True, motivo_isencao="Lei 9.534/1997")["dadosSelo"]
    assert dados["motivoIsentoGratuito"] == "LEI 9.534/1997"


def test_certidao_paga_nao_leva_isencao_nenhuma():
    """Mandar `isento` numa certidão paga seria dar de graça o que se cobra."""
    dados = envelope()["dadosSelo"]
    assert "isento" not in dados
    assert "isentoGratuito" not in dados
    assert "motivoIsentoGratuito" not in dados


def test_gratuidade_sem_motivo_e_recusada_ANTES_da_rede():
    """**O motivo é o que a conferência do Tribunal lê no selo.** A recusa é
    aqui, e não como HTTP 400 com o texto do fornecedor."""
    with pytest.raises(AS.AtoError) as erro:
        envelope(isento=True, motivo_isencao="   ")
    assert "motivo escrito" in str(erro.value)


# --------------------------------- o que não pode mudar sem medir de novo


def test_o_registro_isento_por_LEI_continua_como_esta():
    """**OS 26 SELOS DE REGISTRO DE NASCIMENTO PASSAM HOJE**, pelo ramo de
    cima (`MOTIVO_DA_ISENCAO`), e o item `14.a` já custa zero na tabela.
    Mexer nesse envelope para consertar o outro seria trocar um que funciona
    por um que ninguém mediu."""
    dados = AS.envelope_do_civil(especie="NASCIMENTO", tipo="REGISTRO",
                                 **COMUNS)["dadosSelo"]
    assert dados["isentoGratuito"] == "ISENTO"
    assert dados["motivoIsentoGratuito"] == "REGISTRO DE NASCIMENTO"
    assert "isento" not in dados, (
        "o ramo da isenção POR LEI não foi medido com `isento`; ele passa "
        "como está, e mudá-lo exige medir contra o aparelho")


def test_a_averbacao_e_a_prenotacao_mandam_o_MESMO_campo():
    """**ONDE A IGUALDADE IMPORTA, ELA SE CONSTRÓI** — e aqui ela se compara.

    Os três envelopes que sabem isentar têm de dizer a isenção do mesmo jeito;
    foi a divergência entre eles que deixou a certidão de fora do conserto de
    08/09.
    """
    averbacao = AS.envelope_da_averbacao_civil(
        escrevente="Mario Santos", livro="A-10", folha="58", termo="9313",
        versao_tabela="20260101", alteracao="CPF 000.000.000-00",
        tipo_averbacao=AS.TIPO_AVERBACAO_CPF_ART_347, codigo_tj="14.4.1",
        isento=True, motivo_isencao="ART. 347")["dadosSelo"]
    prenotacao = AS.envelope_da_prenotacao(
        protocolo="11534", escrevente="Mario Santos",
        versao_tabela="20260101", descricao_natureza="compra e venda",
        isento=True, motivo_isencao="ART. 290-A")["dadosSelo"]
    certidao = envelope(isento=True, motivo_isencao="ART. 347")["dadosSelo"]
    for nome, dados in (("averbação", averbacao), ("prenotação", prenotacao),
                        ("certidão", certidao)):
        assert dados.get("isento") is True, (
            f"a {nome} não manda o campo `isento` do contrato")


def test_o_contrato_nao_conhece_isentoGratuito():
    """A medição que explica o defeito, e que fica guardada.

    Se um dia a documentação passar a declarar `isentoGratuito`, este teste
    fica vermelho — e aí a decisão é outra, tomada com o documento na mão.
    """
    fonte = (RAIZ / "selador.py").read_text(encoding="utf-8")
    assert "isentoGratuito" not in fonte
    assert selador.CAMPOS_ISENTO == ("value", "motivo")
    assert any("isento" in str(x.get("onde", "")).lower()
               for x in selador.ALEM_DA_DOCUMENTACAO), (
        "o acervo media `DadosSeloCertidaoRI.isento`; se isso saiu da lista, "
        "a razão do conserto saiu com ele")

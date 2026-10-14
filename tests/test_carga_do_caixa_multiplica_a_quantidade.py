"""A QUANTIDADE QUE NUNCA MULTIPLICOU NAS CUSTAS VINDAS DO E-OFÍCIO.

ACHADO EM 21/09/2026, conferindo o orçamento de uma cédula contra os
precedentes da casa. `cx_protocolo_atos.valor_total` queria dizer duas coisas
conforme a origem da linha:

    o balcão, acrescentando à mão   →  quantidade × unitário
    a carga do E-Ofício             →  o unitário, com a quantidade ao lado
                                       sem efeito nenhum

O caso mais claro é o `16.39`, que a tabela chama de «arquivamento, **por
folha** do documento»: um protocolo com 128 folhas somava R$ 5,92.

O QUE FOI MEDIDO ANTES DE MEXER EM DINHEIRO, e em duas fontes independentes:

1. **No acervo**, em 185 pares (código do TJ, ano) com mais de uma quantidade o
   `curv_Emolumento` é **constante**, e em **zero** ele escala. Os quatro
   fundos acompanham o unitário (4% de 5,92 = 0,23 em todas as linhas de
   `13.17.2`, da quantidade 1 à 90). Logo a coluna do E-Ofício é unitária.

2. **No caixa desta casa** — que é o dinheiro que de fato entrou: em **3.799**
   protocolos pagos o lançamento bate com **quantidade × unitário**, e em
   **1** com o unitário. A casa cobrou multiplicando; era o nosso registro que
   estava a menos.

A segunda medição é a que decide, e ela não sai do acervo: sai de comparar o
que a carga gravou com o que a serventia recebeu.
"""
from __future__ import annotations

import json
import sqlite3

import caixa_import as CXI

# Uma linha de custa como o E-Ofício a exporta: o valor é o de UMA folha, e a
# quantidade está ao lado. É o `16.39` de um protocolo real desta casa.
CUSTA = {
    "intID": 700001,
    "strProtocoloGeral": "2026.09.900",
    "strCodigoTJ": "16.39",
    "strDescDoc": "Arquivamento, por folha do documento",
    "intQte": 10,
    "curv_Emolumento": 5.92,
    "curv_Ferc": 0.18,
    "curValor_MP": 0.23,
    "curValor_DP": 0.23,
    "curvalor_ferrfis": 0.06,
    "bitGratuito": 0,
}
PROTOCOLO = {
    "strProtocoloGeral": "2026.09.900",
    "dtmData": "2026-09-21 00:00:00",
    "strInteressado": "CONSTRUTORA ALFA LTDA",
    "intAtribuicao": 5,
}


def _pasta_com_a_custa(tmp_path, custa=None):
    (tmp_path / "protocolo_geral.jsonl").write_text(
        json.dumps(PROTOCOLO, ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp_path / "protocolo_custas.jsonl").write_text(
        json.dumps(custa or CUSTA, ensure_ascii=False) + "\n", encoding="utf-8")
    return tmp_path


def _carregar(banco, pasta) -> sqlite3.Row:
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        CXI.importar(con, pasta)
        con.commit()
        return con.execute(
            """SELECT quantidade, valor_total, emolumentos, ferc, fadep, femp,
                      ferrfis
               FROM cx_protocolo_atos WHERE origem='EOFICIO'""").fetchone()
    finally:
        con.close()


def test_a_quantidade_multiplica_o_emolumento(cg_casa, tmp_path):
    """Dez folhas a 5,92 são R$ 59,20 de emolumento, e não 5,92."""
    linha = _carregar(cg_casa["banco"], _pasta_com_a_custa(tmp_path))
    assert linha["quantidade"] == 10
    assert linha["emolumentos"] == "59,20"


def test_a_quantidade_multiplica_os_quatro_fundos(cg_casa, tmp_path):
    """Multiplicar só o emolumento faria o fundo ficar para trás, e a
    conferência dos fundos do dia deixaria de fechar."""
    linha = _carregar(cg_casa["banco"], _pasta_com_a_custa(tmp_path))
    assert linha["ferc"] == "1,80"
    assert linha["femp"] == "2,30"
    assert linha["fadep"] == "2,30"
    assert linha["ferrfis"] == "0,60"


def test_o_total_da_linha_e_a_soma_do_que_foi_multiplicado(cg_casa, tmp_path):
    """R$ 66,20 — que é o que a casa cobrou, medido contra o caixa."""
    linha = _carregar(cg_casa["banco"], _pasta_com_a_custa(tmp_path))
    assert linha["valor_total"] == "66,20"


def test_quantidade_um_continua_como_estava(cg_casa, tmp_path):
    """O conserto não pode mexer nas 24.910 linhas de quantidade 1 — elas
    sempre estiveram certas."""
    uma = dict(CUSTA, intQte=1)
    linha = _carregar(cg_casa["banco"], _pasta_com_a_custa(tmp_path, uma))
    assert linha["quantidade"] == 1
    assert linha["emolumentos"] == "5,92"
    assert linha["valor_total"] == "6,62"


def test_quantidade_ausente_vale_um(cg_casa, tmp_path):
    """`intQte` em branco não pode virar zero: zero apagaria o valor da linha."""
    sem = dict(CUSTA)
    sem.pop("intQte")
    linha = _carregar(cg_casa["banco"], _pasta_com_a_custa(tmp_path, sem))
    assert linha["quantidade"] == 1
    assert linha["valor_total"] == "6,62"


def test_quantidade_zero_vale_um(cg_casa, tmp_path):
    """O acervo traz `intQte` zerado em algumas linhas, e ali o ato aconteceu
    uma vez — não nenhuma."""
    zero = dict(CUSTA, intQte=0)
    linha = _carregar(cg_casa["banco"], _pasta_com_a_custa(tmp_path, zero))
    assert linha["quantidade"] == 1
    assert linha["valor_total"] == "6,62"


def test_a_soma_do_protocolo_passa_a_bater_com_a_linha(cg_casa, tmp_path):
    """**O defeito que se via de fora.** O protocolo somava o unitário e o
    cliente pagava o produto — a ficha mostrava menos do que entrou no caixa."""
    import emolumentos as EMOL

    con = sqlite3.connect(str(cg_casa["banco"]))
    con.row_factory = sqlite3.Row
    try:
        CXI.importar(con, _pasta_com_a_custa(tmp_path))
        con.commit()
        itens = [dict(r) for r in con.execute(
            "SELECT * FROM cx_protocolo_atos WHERE origem='EOFICIO'")]
    finally:
        con.close()
    assert EMOL.somar_itens(itens)["total"] == "66,20"

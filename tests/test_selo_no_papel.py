"""O QUE DO SELO VAI IMPRESSO — uma régua para os papéis das seis atribuições.

Pedido do oficial em 01/09/2026: *«aplique a correção do selo (com emolumentos
e demais informações) também para todos demais atos do cartório, inclusive
etiqueta de reconhecimento de firma e autenticação de cópia»*.

O QUE ESTES TESTES GUARDAM
      - **a régua é uma só** — a certidão do RCPN e a etiqueta compõem a linha
        pela mesma função, e não por duas parecidas que divergem no primeiro
        conserto;
      - **a linha traz o que o selo declara, e nada mais** — rótulo sem valor
        é ruído num papel assinado, e zero seria pior, porque afirma;
      - **o fundo se pede pela sigla canônica** (`FADP`), e se imprime pelo
        rótulo do papel (`FADEP`);
      - **selo sem texto não produz linha nenhuma** — e não uma linha de
        rótulos secos;
      - **o ISS não entra**, que é a regra medida da casa;
      - e o ensaio contra o **texto real** de um reconhecimento desta casa.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import selo_no_papel as SNP

# UM SELO REAL DESTA CASA — reconhecimento de firma por semelhança, item
# 13.17.4, de 06/12/2021. Copiado do acervo (`tbSeloIndividual.strTextoSelo`),
# e não escrito à mão: boneco que não passa pelo leitor testa o teste.
RECONHECIMENTO_REAL = (
    "Poder Judiciario - TJMA. Selo: RECFIR000000003M1XKR7TEX6G33, "
    "06/12/2021 14:38:30, Ato: 13.17.4, Parte(s): TOMAS DOS SANTOS "
    "RIBEIRO, Rec Firma: Semelhanca, Total R$ 18,11 Emol R$ 16,31 "
    "FERC R$ 0,50 FADEP R$ 0,65 FEMP R$ 0,65 "
    "Consulte em https://selo.tjma.jus.br")

AUTENTICACAO_REAL = (
    "Poder Judiciario - TJMA. Selo: AUTENT000000000L852EF0NHD053, "
    "01/02/2021 14:23:48, Ato: 13.18, Total R$ 5,12 Emol R$ 4,63 "
    "FERC R$ 0,13 FADEP R$ 0,18 FEMP R$ 0,18 "
    "Consulte em https://selo.tjma.jus.br")


def test_a_linha_traz_os_valores_do_reconhecimento_real():
    """O ato que responde por metade do movimento desta casa."""
    linha = SNP.linha_de_valores(RECONHECIMENTO_REAL)
    for pedaco in ("Total R$ 18,11", "Emol R$ 16,31", "FERC R$ 0,50",
                   "FEMP R$ 0,65", "FADEP R$ 0,65"):
        assert pedaco in linha, f"«{pedaco}» sumiu de um selo que o declara"


def test_a_linha_traz_os_valores_da_autenticacao_real():
    linha = SNP.linha_de_valores(AUTENTICACAO_REAL)
    assert "Total R$ 5,12" in linha
    assert "Emol R$ 4,63" in linha
    assert "FADEP R$ 0,18" in linha


def test_o_rotulo_sem_valor_nao_entra():
    """**RÓTULO SEM VALOR É RUÍDO NUM PAPEL ASSINADO.** Medido em 4.000 selos:
    o FERRFIS aparece em 396 — um em cada dez. Os dois selos reais acima não o
    declaram, e a linha deles não pode trazer «FERRFIS R$» e nada depois."""
    for texto in (RECONHECIMENTO_REAL, AUTENTICACAO_REAL):
        assert "FERRFIS" not in SNP.linha_de_valores(texto)
    # E quando o selo declara, ele entra.
    com = RECONHECIMENTO_REAL.replace("FEMP R$ 0,65 ", "FEMP R$ 0,65 FERRFIS R$ 0,11 ")
    assert "FERRFIS R$ 0,11" in SNP.linha_de_valores(com)


def test_zero_nao_se_afirma_sobre_ato_oneroso():
    """O módulo do selo devolve `None` para o que não achou justamente para
    não afirmar zero — e a linha respeita isso."""
    assert "R$ 0,00" not in SNP.linha_de_valores(AUTENTICACAO_REAL)


def test_selo_sem_texto_nao_produz_linha():
    """Selo digitado à mão pode não ter texto; a etiqueta sai sem a linha, e
    não com rótulos secos."""
    assert SNP.linha_de_valores("") == ""
    assert SNP.linha_de_valores(None) == ""
    assert SNP.detalhe("") == ""


def test_o_fundo_se_pede_pela_sigla_e_se_imprime_pelo_rotulo():
    """**`FADEP` É SINÔNIMO; a sigla da casa é `FADP`.** O leitor do selo
    devolve sempre a canônica — 3.998 de 4.000 —, e o papel escreve `FADEP`,
    que é o que o selo e a certidão real desta casa imprimem."""
    import atribuicoes as ATR
    for sigla in SNP.FUNDOS_DO_PAPEL:
        assert any(f["sigla"] == sigla for f in ATR.FUNDOS), (
            f"«{sigla}» não é sigla de fundo da casa — se for sinônimo, o "
            f"`selo.ler_texto` nunca vai devolvê-la")
    assert SNP.ROTULO_NO_PAPEL["FADP"] == "FADEP"
    assert "FADEP R$" in SNP.linha_de_valores(RECONHECIMENTO_REAL)
    assert "FADP R$" not in SNP.linha_de_valores(RECONHECIMENTO_REAL)


def test_o_iss_nao_entra_no_papel():
    """O cadastro tem cinco fundos e só quatro são cobrados."""
    assert "ISS" not in SNP.FUNDOS_DO_PAPEL
    assert len(SNP.FUNDOS_DO_PAPEL) == 4


def test_o_detalhe_traz_ato_data_e_partes():
    d = SNP.detalhe(RECONHECIMENTO_REAL)
    assert "13.17.4" in d
    assert "06/12/2021" in d
    assert "TOMAS DOS SANTOS" in d


def test_do_papel_aceita_a_linha_do_razao_dos_selos():
    """`sd_selos` devolve `{numero, texto}` — é o que o papel recebe."""
    d = SNP.do_papel({"numero": "RECFIR000000003M1XKR7TEX6G33",
                      "texto": RECONHECIMENTO_REAL})
    assert d["numero"] == "RECFIR000000003M1XKR7TEX6G33"
    assert d["total"] == "18,11"
    assert d["fadep"] == "0,65"
    assert d["ferrfis"] == " ", "o que o selo não declara sai em branco"
    assert d["_total_n"] == 18.11, "o número serve para somar; o texto não"


def test_a_certidao_do_rcpn_usa_ESTA_regua_e_nao_uma_parecida():
    """**UMA RÉGUA, E NÃO DUAS.** A composição nasceu dentro de
    `rc_certidao_odt` e saiu de lá quando alcançou os demais atos; se voltar a
    ter corpo próprio, a certidão e a etiqueta divergem no primeiro conserto.

    É a lição da `normalizar_nome`, que este projeto já pagou cinco vezes.
    """
    import rc_certidao_odt as ODT
    assert ODT._FUNDOS_DO_PAPEL is SNP.FUNDOS_DO_PAPEL
    assert ODT.ROTULO_NO_PAPEL is SNP.ROTULO_NO_PAPEL
    do_molde = ODT._valores_do_selo({"numero": "X", "texto": RECONHECIMENTO_REAL})
    assert do_molde["valores"] == SNP.linha_de_valores(RECONHECIMENTO_REAL)

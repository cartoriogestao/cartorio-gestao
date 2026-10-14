"""O MOLDE DA CERTIDÃO DE CASAMENTO — igual ao Anexo V do Provimento CNJ
182/2024, e não mais um clone do de nascimento.

Pedido do oficial em 01/09/2026 («adaptar a certidão de registro de
casamento para ficar igual ao provimento do cnj»), retomado em 09/09/2026
depois do rodapé (já corrigido, ver `test_rc_certidao_molde.py`) — desta vez
o CORPO: «a de casamento não está boa, preciso que fique igual ao modelo do
cnj».

O QUE MUDOU, MEDIDO CONTRA O ANEXO V (página 6 do Provimento)
    Até aqui o corpo era literalmente o de nascimento, com os campos do
    casal lado a lado (9 tabelas `Casamento1..9`, uma coluna por cônjuge).
    O Anexo V não faz assim: cada cônjuge tem um bloco de LARGURA CHEIA,
    empilhado — nome (com Dia/Mês/Ano), nacionalidade/estado civil/
    naturalidade/UF, genitores, nome pós-casamento —, e só depois vem o
    outro cônjuge. E o topo muda de "NOMES:" (uma linha combinada) para
    "Nome atual dos cônjuges" com CPF ao lado, uma linha por cônjuge.

    Três marcadores novos entraram em `rc_certidao_odt.py` para isso — e
    são LEITURA do que `rc_certidao_quadro` já calculava
    (`conjuges[i]['dma']`, `dma_registro`), não dado novo: `@conj1_dia`/
    `@conj1_mes`/`@conj1_ano` (e `@conj2_*`), `@conj1_naturalidade_cidade`/
    `@conj1_naturalidade_uf` (e `@conj2_*`), `@diaregistro`/`@mesregistro`/
    `@anoregistro`.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_certidao_odt as ODT

MOLDE = RAIZ / "modelos" / "certidao_casamento_modelo.odt"
tem_o_molde = pytest.mark.skipif(
    not MOLDE.is_file(), reason="o molde .odt não está nesta instalação")


def conteudo() -> str:
    return zipfile.ZipFile(MOLDE).read("content.xml").decode("utf-8")


def texto_do_molde() -> str:
    x = conteudo()
    x = x[x.find("<office:body"):]
    x = re.sub(r"<text:tab/>", " | ", x)
    x = re.sub(r"<text:s[^/]*/>", " ", x)
    x = re.sub(r"</text:p>|</table:table-cell>", "\n", x)
    return re.sub(r"<[^>]+>", "", x)


def marcadores_do_molde() -> set[str]:
    return set(re.findall(r"@[A-Za-z_0-9]+", texto_do_molde()))


@tem_o_molde
def test_todo_marcador_do_molde_o_codigo_sabe_preencher():
    """O guarda principal, o mesmo do molde de nascimento: `@` que o código
    não conhece sai cru numa certidão assinada."""
    faltando = sorted(marcadores_do_molde() - set(ODT.valores({}, {}, {})))
    assert not faltando, (
        "estes marcadores estão no molde e o código não preenche — sairiam "
        f"escritos no papel: {faltando}")


@tem_o_molde
def test_nenhum_valor_fica_aninhado_dentro_de_tvalor():
    """O mesmo defeito de fonte do molde de nascimento — ver
    `test_rc_certidao_molde.py` para a medição completa: `TValor`/
    `TValorNegrito` aninhado dentro do estilo do rótulo cai no Calibri do
    documento em vez do Times do rótulo, sempre que o parágrafo se resume a
    esse par. Como este molde nasceu clonado do de nascimento, herdava o
    mesmo padrão em todo campo — e este teste impede que ele volte."""
    c = conteudo()
    aninhados = re.findall(
        r'<text:span text:style-name="T\d+"><text:span '
        r'text:style-name="TValor(?:Negrito)?">',
        c)
    assert not aninhados, (
        "TValor/TValorNegrito aninhado dentro de um estilo de rótulo — "
        f"defeito da fonte errada voltando. Achados: {aninhados}")


@tem_o_molde
def test_o_rodape_e_o_do_anexo_v_e_nao_o_de_uma_coluna_so():
    """Mesmas quatro checagens do rodapé de nascimento — o bloco é
    byte a byte igual entre os dois moldes (conferido por diff em
    09/09/2026), então as regras são as mesmas."""
    t = texto_do_molde()
    assert "@cidade_uf" not in t
    assert "COMARCA DE" not in t
    assert "@linha_assinatura" not in t
    # **O CARGO DO DELEGATÁRIO NÃO É O DE QUEM ASSINA A VIA** — relato do
    # oficial em 10/09/2026, medido na certidão 21 da produção. Ver
    # `test_rc_certidao_molde.py` para a medição inteira: o molde usava o
    # mesmo marcador nas duas colunas do rodapé, e por isso o nome do
    # delegatário saía com «Escrevente Autorizado» embaixo.
    assert t.count("@funcaoregistrador") == 1
    assert t.count("@funcaoescrevente") == 1
    # A palavra «(assinatura)» saiu por decisão do oficial em 09/09/2026 —
    # ela é placeholder do modelo em branco, e impressa ocupa o lugar em que
    # o escrevente assina. Ver `test_rc_certidao_molde.py` para a íntegra.
    assert "(assinatura)" not in t
    for marcador in (
        "@unit_name", "@serventia_email", "@serventia_telefone",
        "@serventia_cnpj", "@ri_substituta",
    ):
        assert marcador not in t, f"{marcador} não está no Anexo V e devia ter saído"


@tem_o_molde
def test_o_corpo_tem_o_bloco_cheio_por_conjuge():
    """**O achado do relato**: o corpo antigo punha os dois cônjuges lado a
    lado (`Casamento1..9`); o Anexo V empilha um bloco de largura cheia por
    cônjuge. As tabelas antigas saem do molde; o texto novo entra."""
    c = conteudo()
    for nome_tabela in (f"Casamento{n}" for n in range(1, 10)):
        assert f'table:name="{nome_tabela}"' not in c, (
            f"{nome_tabela} ainda está no molde — é o layout lado a lado "
            "que o Anexo V não usa")
    t = texto_do_molde()
    assert t.count("1º CÔNJUGE") == 1
    assert t.count("2º CÔNJUGE") == 1
    assert t.find("1º CÔNJUGE") < t.find("2º CÔNJUGE"), (
        "o bloco do primeiro cônjuge tem de vir antes do segundo")
    for rotulo in ("NOME NO MOMENTO DA HABILITAÇÃO", "NACIONALIDADE",
                   "MUNICÍPIO DA NATURALIDADE", "GENITOR",
                   "NOME QUE PASSOU A UTILIZAR"):
        assert t.count(rotulo) == 2, (
            f"«{rotulo}» devia aparecer uma vez por cônjuge (2), achei "
            f"{t.count(rotulo)}")


@tem_o_molde
def test_nome_atual_dos_conjuges_tem_cpf_ao_lado():
    """O topo do Anexo V não é mais «NOMES:» numa linha só — é «nome atual»
    e CPF, um por cônjuge, o que o antigo layout só mostrava lá no meio do
    corpo (na coluna do cônjuge, sem o nome atual junto)."""
    t = texto_do_molde()
    assert "NOMES:" not in t, "o rótulo órfão do layout antigo voltou"
    assert "@conj1_nomepos" in t and "@conj2_nomepos" in t
    assert "@conj1_cpf" in t and "@conj2_cpf" in t
    assert t.find("@conj1_nomepos") < t.find("MATRÍCULA"), (
        "o nome atual dos cônjuges devia vir antes da matrícula, "
        "como no Anexo V")


@tem_o_molde
def test_os_rotulos_sao_os_de_cima_da_caixa_e_nao_os_de_dentro():
    """**A MESMA LIÇÃO DO «(assinatura)», TRÊS VEZES NO MESMO MOLDE.**

    No modelo em branco, o que está DENTRO da caixa é placeholder e o rótulo
    de verdade é o que está ACIMA dela. Medido na página 6 do Provimento
    (Anexo V):

      acima da caixa            dentro dela (placeholder)
      ------------------------  ---------------------------------------
      data de nascimento        Dia · Mês · Ano
      Regime de Bens            Regime de bens adotado no casamento
      Data de registro do       Data de registro do casamento por
      casamento                 extenso

    O molde usava o de dentro nos dois primeiros. Note a diferença com o
    Anexo IV: **lá** «Dia», «Mês» e «Ano» estão ACIMA das caixinhas e são
    rótulo; aqui estão dentro.
    """
    t = texto_do_molde()
    assert "REGIME DE BENS" in t
    assert "REGIME DE BENS ADOTADO NO CASAMENTO" not in t, (
        "o placeholder de dentro da caixa voltou como rótulo")
    assert "DATA DE NASCIMENTO" in t
    assert "DATA DE REGISTRO DO CASAMENTO" in t
    assert "POR EXTENSO" not in t, (
        "«POR EXTENSO» descreve a forma do dado, e não o campo")


@tem_o_molde
def test_a_data_da_celebracao_e_do_registro_tem_dia_mes_ano():
    """O Anexo V não pede só a data por extenso — pede as caixas de Dia,
    Mês e Ano também, para as duas datas (celebração e registro)."""
    t = texto_do_molde()
    for marcador in ("@dianascimento", "@mesnascimento", "@anonascimento",
                     "@diaregistro", "@mesregistro", "@anoregistro"):
        assert marcador in t, f"{marcador} não está no molde"

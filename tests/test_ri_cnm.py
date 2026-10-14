"""O Código Nacional de Matrícula, medido antes de ser gerado.

POR QUE AQUI SE GERA E NO RCPN NÃO — e a diferença é a única coisa que importa

    O sistema **recebe** a matrícula de 32 dígitos do RCPN e não a gera, porque
    o verificador dela não se explica: 243 amostras testadas contra módulo 11
    em quatro conjuntos de pesos, duas convenções e dez mapeamentos, mais
    módulo 97 e Luhn — o melhor acertou **46 de 243**, que é nível de acaso. Há
    teste que fica vermelho se alguém escrever uma função que a gere.

    O CNM é o oposto: **ISO 7064 MOD 97-10**, a conta do IBAN, e ela reproduz
    **1.656 dos 1.656** códigos que esta casa já emitiu, sem uma exceção.

    Gerar aqui é reproduzir o que já existe. Gerar lá seria inventar.

A ESTRUTURA, MEDIDA

        000000 . 2 . 0000001 - 98
          CNS   livro  número    DV

    E o sequencial **é** o número da matrícula — conferido em 1.656 de 1.656.
    O dígito do livro é o NÚMERO do livro, e não a letra do volume: `2A`, `2S`
    e `2C` são todos `2`.

O QUE ISSO CONSERTA
    Das 1.701 matrículas, **45 não tinham CNM** — 43 vieram assim do E-Ofício e
    **2 foram lavradas por este sistema**, que nunca gerou nenhum.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_cnm as CNM          # noqa: E402

PRODUCAO = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")


# ------------------------------------------------------ a conta


def test_o_verificador_e_a_conta_do_iban():
    """`98 − (base × 100) mod 97`, e ela vale para o CNM inteiro."""
    assert CNM.digito("00000020000001") == "27"
    assert CNM.digito("00000020000003") == "21"
    assert CNM.digito("00000020000007") == "09"


def test_cada_matricula_seguinte_baixa_tres_no_digito():
    """A assinatura do módulo 97: 100 mod 97 é 3.

    Foi este padrão nos seis primeiros CNM do acervo que apontou o algoritmo,
    antes de qualquer teste — e a medição nos 1.656 confirmou.
    """
    anteriores = [int(CNM.montar("000000", "2", n)[-2:]) for n in range(1, 8)]
    for antes, depois in zip(anteriores, anteriores[1:]):
        assert (antes - depois) % 97 == 3


def test_o_sequencial_e_o_numero_da_matricula():
    assert CNM.montar("000000", "2", 1) == "000000.2.0000001-27"
    assert CNM.montar("000000", "2", "4014").startswith("000000.2.0004014-")


def test_o_digito_do_livro_e_o_numero_e_nao_a_letra_do_volume():
    """`2A`, `2S`, `2-C` são todos o Livro 2.

    O volume é de papel. Pôr a letra no CNM diria ao país que há vinte livros
    de registro geral nesta serventia, quando há um.
    """
    for volume in ("2", "2A", "2S", "2-C", "2Q"):
        assert CNM.numero_do_livro(volume) == "2"
        assert CNM.montar("000000", volume, 7) == "000000.2.0000007-09"
    assert CNM.numero_do_livro("3") == "3"


# ------------------------------------------------------ a conferência


def test_conferir_devolve_as_partes():
    r = CNM.conferir("000000.2.0000001-27")
    assert (r["cns"], r["livro"], r["numero"], r["digito"]) == (
        "000000", "2", 1, "27")


def test_digito_trocado_e_recusado_dizendo_qual_seria_o_certo():
    """Quem digitou errado precisa saber qual é o certo — «código inválido»
    não ajuda ninguém a consertar."""
    with pytest.raises(CNM.CnmError) as erro:
        CNM.conferir("000000.2.0000001-99")
    assert "deveria ser 27" in str(erro.value)


def test_forma_errada_e_recusada_com_o_exemplo(  ):
    for ruim in ("000000.2.1-98", "abc", "", "000000-2-0000001-27"):
        with pytest.raises(CNM.CnmError) as erro:
            CNM.conferir(ruim)
        assert "000000.2.0000001-27" in str(erro.value)


def test_confere_nao_estoura():
    assert CNM.confere("000000.2.0000001-27")
    assert not CNM.confere("000000.2.0000001-99")
    assert not CNM.confere(None)


# ------------------------------------------------ o que não se monta


def test_sem_cns_de_seis_digitos_nao_sai_cnm():
    """E a mensagem diz onde responder."""
    for ruim in ("", "2963", "0000001"):
        with pytest.raises(CNM.CnmError) as erro:
            CNM.montar(ruim, "2", 1)
        assert "seis dígitos" in str(erro.value)
    assert "Configurações" in str(
        pytest.raises(CNM.CnmError, CNM.montar, "", "2", 1).value)


def test_matricula_sem_numero_nao_tem_codigo_nacional():
    with pytest.raises(CNM.CnmError, match="não é um número"):
        CNM.montar("000000", "2", "SEM NÚMERO")


def test_numero_que_nao_cabe_nas_sete_casas_e_recusado():
    with pytest.raises(CNM.CnmError, match="não cabe"):
        CNM.montar("000000", "2", 10_000_000)


# ------------------------------------- contra os 1.656 CNM reais desta casa


@pytest.mark.skipif(not PRODUCAO.exists(),
                    reason="o banco de produção não está nesta máquina")
def test_o_modulo_reproduz_todos_os_cnm_que_a_casa_emitiu():
    """O ensaio que autoriza gerar.

    Se algum dia isto falhar, é porque o padrão mudou — e aí o certo é medir de
    novo, e não ajustar o teste.
    """
    con = sqlite3.connect(f"file:{PRODUCAO}?mode=ro", uri=True)
    reais = [(r[0], r[1], r[2].strip()) for r in con.execute(
        "SELECT numero, livro_norm, cnm FROM ri_matriculas"
        " WHERE COALESCE(cnm,'') <> ''")]
    assert len(reais) >= 1600, "o acervo tem menos CNM do que quando se mediu"

    # O CNS sai dos próprios códigos da produção, e não se escreve aqui (B3).
    cns = reais[0][2][:6]
    errados = [(numero, cnm) for numero, livro, cnm in reais
               if CNM.montar(cns, livro, numero) != cnm]
    assert not errados, (
        f"{len(errados)} de {len(reais)} não fecham — o primeiro é "
        f"{errados[0]}. Meça antes de mexer no módulo.")


@pytest.mark.skipif(not PRODUCAO.exists(),
                    reason="o banco de produção não está nesta máquina")
def test_todos_os_cnm_reais_passam_na_conferencia():
    con = sqlite3.connect(f"file:{PRODUCAO}?mode=ro", uri=True)
    ruins = [r[0] for r in con.execute(
        "SELECT cnm FROM ri_matriculas WHERE COALESCE(cnm,'') <> ''")
        if not CNM.confere(r[0].strip())]
    assert not ruins, ruins[:5]


# ------------------------------------------ e a matrícula nova nasce com ele


def test_a_matricula_nova_nasce_com_o_cnm():
    """Duas matrículas lavradas por este sistema não tinham código nacional."""
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "_cnm_da_matricula" in codigo
    i = codigo.find("INSERT INTO ri_matriculas")
    assert "cnm" in codigo[i:i + 900], (
        "o INSERT da matrícula nova não grava o CNM")


def test_sem_cns_a_matricula_sai_do_mesmo_jeito():
    """O CNM é identificação, e não pode impedir a abertura do registro."""
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    i = codigo.find("def _cnm_da_matricula")
    trecho = codigo[i:i + 800]
    assert "except CNM.CnmError" in trecho and "return None" in trecho

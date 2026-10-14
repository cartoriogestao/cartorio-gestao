"""
Teor de averbação RCPJ/RTD — modelo do PDF (ensino do oficial).

Confere:
  - intro com AVERBADO antes de Registro nº;
  - cabeçalho «Registro Civil das Pessoas Jurídicas» sem livro/folha;
  - encerramento com lavrante (nome+função) da sessão;
  - cabeçalho em TODAS as folhas; encerramento só na última.
"""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rg_teor_averbacao as TEOR  # noqa: E402


def _folha(cor=(240, 240, 240), size=(800, 1100)) -> Image.Image:
    return Image.new("RGB", size, cor)


def test_intro_averbado_antes_do_registro():
    frase = TEOR.intro(148)
    assert "AVERBADO" in frase
    assert "Registro nº 148" in frase
    # AVERBADO vem ANTES de «Registro nº»
    assert frase.index("AVERBADO") < frase.index("Registro nº")
    # Não usa mais «Termo»
    assert "Termo" not in frase
    assert frase.startswith("CERTIFICO que me foi apresentado para ser")
    assert ", hoje," not in frase
    assert " hoje" not in frase.lower()


def test_cabecalho_das_pessoas_juridicas_sem_livro_folha():
    linhas = TEOR.linhas_cabecalho(cns="000000")
    junto = "\n".join(linhas)
    assert TEOR.ATRIBUICAO_RCPJ == "Registro Civil das Pessoas Jurídicas"
    assert "Registro Civil das Pessoas Jurídicas" in junto
    # Forma errada «de Pessoas» não deve aparecer
    assert "Registro Civil de Pessoas Jurídicas" not in junto
    assert "CNS 000000" in junto
    assert TEOR.cabecalho_tem_livro_ou_folha(linhas) is False
    for proibido in ("livro", "folha", "fl.", "série", "ficha"):
        assert proibido.lower() not in junto.lower()


def test_encerramento_com_lavrante_da_sessao():
    texto = TEOR.encerramento(
        lavrante_nome="MARIA DA SILVA", lavrante_funcao="Escrevente")
    assert "Eu, MARIA DA SILVA, Escrevente, o subscrevo e assino." in texto
    data = TEOR.linha_data(cidade="Cidade Exemplo", uf="MA")
    assert data.startswith("Cidade Exemplo/MA,")


def test_flags_cabecalho_em_todas_encerramento_so_na_ultima():
    assert TEOR.flags_das_paginas(1) == [(True, True)]
    assert TEOR.flags_das_paginas(3) == [
        (True, False), (True, False), (True, True)]
    with pytest.raises(TEOR.TeorAverbacaoError):
        TEOR.flags_das_paginas(0)


def test_gerar_pdf_uma_folha_e_multi():
    pdf1 = TEOR.gerar_pdf(
        numero_registro=148,
        imagens=[_folha()],
        lavrante_nome="MARIO EXEMPLO DOS SANTOS",
        lavrante_funcao="Tabelião e Oficial de Registro",
    )
    assert pdf1.startswith(b"%PDF")
    assert pdf1.count(b"/Type /Page /Parent") == 1

    pdf3 = TEOR.gerar_pdf(
        numero_registro=148,
        imagens=[_folha((200, 200, 200)), _folha((180, 180, 180)),
                 _folha((160, 160, 160))],
        lavrante_nome="MARIA DA SILVA",
        lavrante_funcao="Escrevente",
    )
    assert pdf3.startswith(b"%PDF")
    assert pdf3.count(b"/Type /Page /Parent") == 3


def test_teor_texto_curto_preenche_campo_do_lancamento():
    assert "AVERBADO" in TEOR.teor_texto_curto(361)
    assert "Registro nº 361" in TEOR.teor_texto_curto(361)


def test_recusa_sem_lavrante_ou_sem_numero():
    with pytest.raises(TEOR.TeorAverbacaoError, match="número"):
        TEOR.intro("")
    with pytest.raises(TEOR.TeorAverbacaoError, match="nome"):
        TEOR.encerramento(lavrante_nome="", lavrante_funcao="Escrevente")
    with pytest.raises(TEOR.TeorAverbacaoError, match="função"):
        TEOR.encerramento(lavrante_nome="X", lavrante_funcao="")

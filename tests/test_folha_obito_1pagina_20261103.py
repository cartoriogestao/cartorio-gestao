"""Termo de obito em UMA folha (frente com termo, selo e assinaturas; verso
separado) -- pedido do balcao de 03/11/2026.

Caso que motivou: obito com teor de 1617 letras (1634 caracteres com as tags),
abaixo do limite de 1650 do termo-longo. Saia com a letra cheia (10.5pt,
entrelinha 1.35, assinaturas uma embaixo da outra) e, com o carimbo do selo,
a assinatura da escrevente caia na pagina seguinte (PDF de 3 paginas).

Prova pelo mesmo caminho do balcao: /rcpn/<id>/folha/papel (Chrome headless,
impressao_pdf.arquivo_de_html). Texto FICTICIO do mesmo tamanho.
"""
from __future__ import annotations

import re

import pytest

from test_rc_folha_tela import casa, _con, _assento, _pessoa, _abrir  # noqa: F401

SELO = "REGOBT000000YAGQMNVGI8T80C30"
ETIQUETA = ("Poder Judiciario - TJMA. Selo: " + SELO + ", 03/11/2026 09:53:50, "
            "Ato: 14.c, Parte(s): Falecido Fict Testes, Total R$ 0,00 Emol R$ 0,00 "
            "FERC R$ 0,00 FADEP R$ 0,00 FEMP R$ 0,00 FERRFIS R$ 0,00 Selo Isento, "
            "Consulte em https://selo.tjma.jus.br")
PALAVRAS = ("aos tres dias do mes de novembro de dois mil e vinte e seis neste "
            "cartorio compareceu declarante residente domiciliado municipio "
            "comarca estado do maranhao falecido filho legitimo conforme "
            "declaracao obito numero expedida pelo medico causa da morte "
            "sepultamento cemitério municipal deixou bens herdeiros eleitor "
            "reservista documento identidade cadastro pessoa fisica").split()


def _teor(letras: int) -> str:
    """Teor ficticio com <strong> no nome e ~6 letras por palavra, como o real."""
    corpo, i = [], 0
    while len(" ".join(corpo)) < letras - 40:
        corpo.append(PALAVRAS[i % len(PALAVRAS)])
        i += 1
    texto = " ".join(corpo)
    texto = texto + " " + "x" * max(0, letras - 40 - len(texto) - 1)
    nome = "FALECIDO FICTICIO DE TESTE".ljust(40 - 1)
    return "<strong>" + nome + "</strong> " + texto


def _obito_longo(casa, letras: int) -> int:
    casa["db"].create_user("vteste", "Escrevente Ficticia", "Senha#12345", "USER")
    aid = _assento(casa, especie="OBITO", numero="1985", nome="FALECIDO FICTICIO DE TESTE",
                   livro_volume="C-5", teor=_teor(letras), teor_formato="html")
    con = _con(casa)
    with con:
        con.execute("UPDATE users SET funcao='Escrevente Autorizada' WHERE username='vteste'")
        _pessoa(con, aid, "FALECIDO", "FALECIDO FICTICIO DE TESTE")
        _pessoa(con, aid, "DECLARANTE", "DECLARANTE FICTICIO DE TESTE")
        con.execute("INSERT INTO rc_atos (assento_id, tipo, selo, data_ato, criado_em, criado_por)"
                    " VALUES (?, 'REGISTRO', ?, '2026-11-03', '2026-11-03T09:53:50',"
                    " 'Escrevente Ficticia')", (aid, SELO))
        con.execute("INSERT INTO sd_selos (numero, texto, obtido_em)"
                    " VALUES (?, ?, '2026-11-03T09:53:50')", (SELO, ETIQUETA))
    return aid


def _paginas(pdf: bytes) -> list[str]:
    fitz = pytest.importorskip("pymupdf")
    doc = fitz.open(stream=pdf, filetype="pdf")
    return [" ".join(p.get_text().split()) for p in doc]


@pytest.mark.parametrize("letras", [1617, 1960])  # o caso real e 20% maior
def test_obito_longo_cabe_na_frente_e_o_verso_fica_separado(casa, letras):
    aid = _obito_longo(casa, letras)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert re.search(r'class="folha[^"]*termo-longo', html), "obito longo sem aperto"
    r = casa["cliente"].get(f"/rcpn/{aid}/folha/papel")
    if r.status_code != 200 or not r.data.startswith(b"%PDF"):
        pytest.skip("sem Chrome/conversor nesta maquina")
    pags = _paginas(r.data)
    assert len(pags) == 2, f"esperava frente + verso, veio {len(pags)} paginas"
    frente, verso = pags
    for trecho in ("FALECIDO FICTICIO DE TESTE", SELO, "Declarante",
                   "Escrevente Ficticia", "Frente"):
        assert trecho in frente, f"{trecho!r} nao ficou na frente"
    assert "Verso" in verso
    for trecho in ("Declarante", "Escrevente Ficticia", "SELO DIGITAL"):
        assert trecho not in verso, f"{trecho!r} caiu no verso"


def test_nascimento_e_casamento_de_mesmo_tamanho_nao_mudam(casa):
    """O limite menor e so do obito: nascimento/casamento seguem em 1650."""
    for especie, serie in (("NASCIMENTO", "A-1"), ("CASAMENTO", "B-1")):
        aid = _assento(casa, especie=especie, numero="77", nome="ENSAIO",
                       livro_volume=serie, teor=_teor(1617), teor_formato="html")
        html = _abrir(casa, f"/rcpn/{aid}/folha")
        assert 'class="folha"' in html, f"{especie} mudou de classe"
        assert "termo-longo" not in re.findall(r'class="folha[^"]*"', html)[0]


def test_obito_curto_continua_com_letra_cheia(casa):
    aid = _assento(casa, especie="OBITO", numero="78", nome="ENSAIO",
                   livro_volume="C-1", teor=_teor(900), teor_formato="html")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert re.findall(r'class="folha[^"]*"', html)[0] == 'class="folha"'
"""O número do problema, na tela — o relato #23 do oficial.

A FRASE DELE, e ela diz exatamente o que estava errado:

    «claude relacionou o problema 8, 9 e 20 como finalizados, mas não sei quais
     são esses — não há número nos problemas, não consigo saber qual o claude
     se refere como 8, 9 e 20»

E ELE ESTAVA CERTO, E O DEFEITO ERA MEU
    O **relatório** que sai da casa numera cada problema — `### 8. …` —, e a
    **tela** não numerava nada. Eu lia o relatório e falava por número; ele lia
    a tela e não tinha por onde achar. Duas vistas do mesmo fato, e só uma com
    endereço.

    Pior: eu continuei fazendo isso depois do relato. Nesta mesma conversa
    falei em «#21 usucapião», «#19 CNIB» e «#10 layout» — três vezes o mesmo
    defeito, com o relato aberto na lista.

O QUE MUDOU
    A tela mostra `#8` na primeira coluna, e o relatório passou a escrever
    `### #8 — …`. **O mesmo texto nos dois**, para quem lê um achar o outro
    sem traduzir. E cada linha ganhou âncora, para o endereço
    `/ajuda/problemas#problema-8` levar direto a ela.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ajuda_problemas as AJ

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _relato(con, titulo, *, onde="ri_ficha"):
    """Devolve o NÚMERO do problema. `anotar` devolve um dicionário com
    `{id, vezes, nova}` — não o id solto."""
    return AJ.anotar(con, origem="RELATADO", titulo=titulo,
                     detalhe="o que o escrevente escreveu", onde=onde,
                     caminho="/registro-imoveis/1", versao="3.6.29",
                     agora="2026-08-29T10:00", usuario="mario")["id"]


# ------------------------------------------- a tela mostra o número


def test_a_tela_mostra_o_numero_de_cada_problema(casa):
    """Sem ele, «veja o 8» não tem como ser respondido por quem está no
    balcão."""
    con = _con(casa)
    with con:
        pid = _relato(con, "o teor da escritura não sai formatado")
    html = casa["cliente"].get("/ajuda/problemas").get_data(as_text=True)
    assert f"#{pid}" in html


def test_a_coluna_do_numero_vem_primeiro(casa):
    """Quem procura por número procura na beirada da tabela, e não no meio de
    uma frase."""
    # a tabela só existe quando há problema: sem nenhum, a tela mostra a frase
    # de lista vazia — que é o certo, e não o que este teste mede
    con = _con(casa)
    with con:
        _relato(con, "um problema qualquer")
    html = casa["cliente"].get("/ajuda/problemas").get_data(as_text=True)
    cabecalho = html[html.index("<thead"):html.index("</thead>")]
    assert cabecalho.index("Nº") < cabecalho.index("Situação")


def test_cada_linha_tem_endereco_proprio(casa):
    """`/ajuda/problemas#problema-8` leva direto à linha. Sem âncora, «veja o
    8» ainda obriga a procurar com o olho numa lista de vinte e oito."""
    con = _con(casa)
    with con:
        pid = _relato(con, "um problema qualquer")
    html = casa["cliente"].get("/ajuda/problemas").get_data(as_text=True)
    assert f'id="problema-{pid}"' in html


# ------------------------------------------- e o relatório diz igual


def test_o_relatorio_e_a_tela_usam_o_MESMO_texto():
    """Era esta a diferença que causou o relato: o relatório numerava «8.» e a
    tela não numerava nada. Agora os dois escrevem `#8`, e quem lê um acha o
    outro sem traduzir."""
    texto = AJ.montar_relatorio(
        problemas=[{"id": 8, "titulo": "o cartão de firma não sai para imprimir",
                    "origem": "RELATADO", "onde": "notas_cartoes",
                    "vezes": 1, "primeira_em": "2026-08-27T09:00",
                    "ultima_em": "2026-08-27T09:00", "versao": "3.6.29",
                    "situacao": "ABERTO"}],
        agora="2026-08-29T10:00")
    assert "#8" in texto
    # e não a forma antiga, que a tela não tinha como reproduzir
    assert "### 8." not in texto


def test_o_numero_do_relatorio_e_o_da_tela(casa):
    """A prova de que são o mesmo: o número que sai no relatório tem de estar
    na tela, no mesmo formato."""
    con = _con(casa)
    with con:
        pid = _relato(con, "um problema para conferir os dois lados")
    problemas = [dict(r) for r in con.execute("SELECT * FROM aj_problemas")]
    texto = AJ.montar_relatorio(problemas=problemas, agora="2026-08-29T10:00")
    html = casa["cliente"].get("/ajuda/problemas").get_data(as_text=True)
    assert f"#{pid}" in texto
    assert f"#{pid}" in html


# ------------------------------------------- o que este teste protege


def test_a_tabela_tem_o_mesmo_numero_de_colunas_no_cabecalho_e_no_corpo(casa):
    """Coluna acrescentada no cabeçalho e esquecida no corpo desalinha a tabela
    inteira, e o operador lê o valor de uma coluna sob o título de outra."""
    con = _con(casa)
    with con:
        _relato(con, "um problema qualquer")
    html = casa["cliente"].get("/ajuda/problemas").get_data(as_text=True)
    cabecalho = html[html.index("<thead"):html.index("</thead>")]
    corpo = html[html.index("<tbody"):html.index("</tbody>")]
    primeira_linha = corpo[corpo.index("<tr"):corpo.index("</tr>")]
    # `<th[ >]` e não `<th`: a própria etiqueta `<thead>` começa com «<th», e
    # contá-la daria uma coluna a mais no cabeçalho — o teste acusaria um
    # desalinhamento que não existe.
    assert (len(re.findall(r"<th[ >]", cabecalho))
            == len(re.findall(r"<td[ >]", primeira_linha)))

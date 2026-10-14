"""Pendência é do que ainda se pode fazer, e não do que já passou.

«Pendências antigas e do e-ofício não devem aparecer. São atos que já passaram,
não têm mais relevância e não devem constar mais como pendências atuais. Atos
novos devem aparecer e ter uma opção facilitada de corrigir (com indicação do
problema) para que o envio das cargas não apresente erro posteriormente.»
— o oficial, em 27/08/2026.

MEDIDO: são **47 escrituras sem valor**, e **45 vieram do E-Ofício** — 25 de
2020, 17 de 2022, 1 de 2023. A remessa daquelas saiu no tempo delas, pelo
E-Ofício. As **duas** que este sistema lavrou eram a pendência de verdade, e se
perdiam no meio das quarenta e cinco.

NÃO SE ESCONDE, SEPARA-SE
    Lista de quarenta e cinco itens que nunca diminuem faz ninguém olhar a
    lista. Apagar as quarenta e cinco faria perder o que ainda pode ser
    corrigido no dia em que alguém precisar. Elas ficam num quadro próprio,
    fechado, dizendo o que são — e continuam clicáveis.
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

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _escritura(casa, *, origem: str, data: str, id_: int) -> int:
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO nt_atos (id, tipo, data, livro, folha, natureza,
                   valor_transacao, origem, criado_em)
               VALUES (?, 'ESCRITURA', ?, '27', '10', 'COMPRA E VENDA',
                       NULL, ?, '2026-08-27T10:00:00')""",
            (id_, data, origem))
    return id_


def _tela(casa) -> str:
    return casa["cliente"].get(
        "/notas/escrituras/pendentes").get_data(as_text=True)


def _corpo(html: str) -> str:
    return html[html.find("</nav>"):]


# ------------------------------------------- o que este sistema lavrou


def test_a_escritura_deste_sistema_e_pendencia(casa):
    _escritura(casa, origem="MANUAL", data="2026-08-27", id_=900)
    corpo = _corpo(_tela(casa))
    assert "Sem valor declarado" in corpo
    assert "/notas/atos/900" in corpo


def test_ela_traz_o_campo_para_corrigir_na_propria_linha(casa):
    """«Opção facilitada de corrigir» — sem sair da lista."""
    _escritura(casa, origem="MANUAL", data="2026-08-27", id_=901)
    corpo = _corpo(_tela(casa))
    assert "/notas/escrituras/901/valor" in corpo
    assert 'name="valor"' in corpo


# --------------------------------------------- o que veio do E-Ofício


def test_a_escritura_do_acervo_sai_da_lista_de_pendencias(casa):
    _escritura(casa, origem="EOFICIO", data="2020-06-04", id_=910)
    corpo = _corpo(_tela(casa))
    assert "Sem valor declarado" not in corpo, (
        "o ato de 2020 voltou a contar como pendência de hoje")


def test_mas_continua_alcancavel_num_quadro_proprio(casa):
    """Apagar faria perder o que ainda pode ser corrigido um dia."""
    _escritura(casa, origem="EOFICIO", data="2020-06-04", id_=911)
    corpo = _corpo(_tela(casa))
    assert "do acervo do E-Ofício" in corpo
    assert "/notas/atos/911" in corpo
    assert "remetidas no tempo delas" in corpo


def test_o_quadro_do_acervo_vem_fechado(casa):
    """Ele é consulta, e não trabalho — abrir sozinho seria a lista de novo."""
    _escritura(casa, origem="EOFICIO", data="2020-06-04", id_=912)
    corpo = _corpo(_tela(casa))
    achado = re.search(r"<details[^>]*>\s*<summary[^>]*>\s*<strong>1 escritura",
                       corpo)
    assert achado, "o quadro do acervo não é um <details> fechado"
    assert "<details open" not in corpo


# ------------------------------------------------------ os dois juntos


def test_a_do_sistema_aparece_e_a_do_acervo_nao_a_afoga(casa):
    """É o caso real: duas do sistema entre quarenta e cinco do acervo."""
    _escritura(casa, origem="MANUAL", data="2026-08-27", id_=920)
    for n in range(10):
        _escritura(casa, origem="EOFICIO", data="2020-06-04", id_=930 + n)
    corpo = _corpo(_tela(casa))
    assert "Sem valor declarado &mdash; 1 escritura" in corpo \
        or "Sem valor declarado — 1 escritura" in corpo
    assert "10 escritura(s) do acervo" in corpo


def test_sem_nada_do_sistema_a_tela_diz_isso_sem_mentir(casa):
    """«Nenhuma pendência» com quarenta e cinco linhas embaixo seria mentira."""
    for n in range(3):
        _escritura(casa, origem="EOFICIO", data="2020-06-04", id_=940 + n)
    corpo = _corpo(_tela(casa))
    assert "Nenhuma pendência nos atos lavrados neste sistema" in corpo
    assert "não contam como pendência" in corpo

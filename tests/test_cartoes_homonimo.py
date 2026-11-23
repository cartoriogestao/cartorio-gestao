"""Homônimo no cartão de autógrafo — a confirmação tem de abrir o segundo.

No balcão, nome igual a um cartão já existente pede a caixa
«Já conferi: não é a mesma pessoa…». O redirect antigo com ?busca=NOME
fechava o painel de cadastro e apagava o formulário; o segundo envio
voltava sem confirmar_duplicata e o aviso se repetia.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from bd_nativo import banco  # noqa: E402
from notas_partes import normalizar  # noqa: E402
from tests.selador_de_bancada import ligar_o_selador, tem_cryptography  # noqa: E402

SENHA = "Senha#12345"
NOME = "JOAQUIM HOMONIMO FICTICIO DA COSTA"
CPF_ANTIGO = "39053344705"
CPF_NOVO = "52998224725"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("balcao", "LAURA MARIA DA COSTA", SENHA, "ADMIN")
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO nt_cartoes
                   (nome, nome_norm, documento, origem, ativo, criado_em)
               VALUES (%s,%s,%s,'MANUAL',1,'2026-11-23T09:00')""",
            (NOME, normalizar(NOME), CPF_ANTIGO))
        if not banco(con).um("SELECT 1 AS x FROM cx_servicos WHERE codigo = %s",
                             (412,)):
            banco(con).escrever(
                """INSERT INTO cx_servicos
                       (codigo, codigo_tj, descricao, descricao_norm, ativo)
                   VALUES (412, '13.17.1', 'Abertura de cartão de autógrafo',
                           'ABERTURA DE CARTAO DE AUTOGRAFO', 1)""")
        else:
            banco(con).escrever(
                "UPDATE cx_servicos SET codigo_tj = %s WHERE codigo = %s",
                ("13.17.1", 412))
    from tests.protocolo_de_teste import atender_protocolo_pago
    with db.transaction() as con:
        atender_protocolo_pago(con, usuario="LAURA MARIA DA COSTA",
                               codigos=("13.17.1",), atribuicao="FIRMAS")
    c = cg_casa["cliente"]
    c.post("/login",
           data={"username": "balcao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _post_novo(casa, **campos):
    html = casa["cliente"].get("/notas/cartoes").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "acao": "novo", "nome": NOME,
             "documento": CPF_NOVO}
    dados.update(campos)
    return casa["cliente"].post("/notas/cartoes", data=dados,
                                follow_redirects=False)


def _contar(casa) -> int:
    with casa["db"].connect() as con:
        return int(banco(con).valor(
            "SELECT COUNT(*) FROM nt_cartoes WHERE nome = %s", (NOME,)))


def test_aviso_de_homonimo_reexibe_formulario_aberto_com_dados(casa):
    """Sem confirmar_duplicata: não abre, e o cadastro volta preenchido."""
    r = _post_novo(casa)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Já existe cartão" in html
    assert 'name="confirmar_duplicata"' in html
    assert 'id="aviso-homonimo"' in html
    assert f'value="{NOME}"' in html
    assert f'value="{CPF_NOVO}"' in html
    assert re.search(r"<details[^>]*\bopen\b", html)
    assert _contar(casa) == 1


def test_confirmar_duplicata_abre_o_segundo_cartao(casa):
    """Com confirmar_duplicata=1 a trava de homônimo não volta."""
    if not tem_cryptography():
        pytest.skip("cryptography")
    with ligar_o_selador(casa):
        r = _post_novo(casa, confirmar_duplicata="1")
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    assert re.search(r"/notas/cartoes/\d+$", r.headers.get("Location", ""))
    assert _contar(casa) == 2

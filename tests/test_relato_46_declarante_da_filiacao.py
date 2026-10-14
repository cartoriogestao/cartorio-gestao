"""O RELATO #46 — o declarante que veio da filiação, no assento de nascimento.

    «dar a opçao de inserir os dados de algum da filiacao como declarante no
     registro de nasciemnto»
    «ajuda no preenchimento automatico»           — o oficial, 31/08/2026

**JÁ ESTAVA NA TELA quando o relato chegou**, e por isso os testes abaixo não
guardam um conserto: guardam o que existe, para que ele não se perca sem
ninguém ver.

O QUE EXISTE, medido
    O bloco do declarante (`templates/atrib_rcpn_novo.html`) chama a macro
    `pessoa()` com `copiar_de=[('filiacao1', 'Mãe (filiação 1)'),
    ('filiacao2', 'Pai (filiação 2)')]`, e a macro
    (`templates/_pessoa_do_assento.html`) desenha um botão por origem, com
    `data-copiar-de` e o `copiarDadosDaPessoa(...)` no `onclick`. O script
    (`static/copiar_pessoa.js`) é carregado por TODAS as telas, no `base.html`
    — e copia por SUFIXO do nome do campo: `filiacao1_nome` vai para
    `declarante_nome`, `filiacao1_documento_numero` para
    `declarante_documento_numero`, e assim por diante.

POR QUE A CÓPIA É BOTÃO, E NÃO AUTOMÁTICA
    Quem declara pode ser a avó, o tio, o conselheiro tutelar — e um
    formulário que se preenchesse sozinho com o pai por omissão poria no
    assento uma pessoa que não declarou nada. O botão preenche; quem confere
    e edita é quem está no balcão. Há teste do outro lado: a tela nova NÃO
    nasce com o declarante preenchido.
"""
from __future__ import annotations

import re
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
def c(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                              SENHA, "ADMIN")
    cliente = app.test_client()
    cliente.post("/login",
                 data={"username": "tabeliao", "password": SENHA,
                       "csrf_token": _token(
                           cliente.get("/login").get_data(as_text=True))},
                 follow_redirects=True)
    return cliente


def nascimento(c) -> str:
    return c.get("/rcpn/novo/nascimento").get_data(as_text=True)


# ------------------------------------------------- o botão que copia


def test_o_bloco_do_declarante_oferece_a_mae_e_o_pai(c):
    """O botão fica no bloco de quem ainda não foi preenchido, e nomeia as
    duas origens — sem o rótulo, o escrevente não sabe o que vai ser copiado."""
    html = nascimento(c)
    assert 'data-copiar-de="filiacao1"' in html
    assert 'data-copiar-de="filiacao2"' in html
    assert "Mãe (filiação 1)" in html
    assert "Pai (filiação 2)" in html
    # e o botão diz para ONDE copia: o bloco do declarante.
    assert "copiarDadosDaPessoa('filiacao1', 'declarante')" in html
    assert "copiarDadosDaPessoa('filiacao2', 'declarante')" in html


def test_o_script_da_copia_e_carregado_e_sabe_copiar(c):
    """**Botão sem script é botão que não faz nada.** Ele é carregado no
    `base.html`, para todas as telas — e a tela do assento novo o alcança."""
    html = nascimento(c)
    assert "copiar_pessoa.js" in html
    js = c.get("/static/copiar_pessoa.js")
    assert js.status_code == 200
    corpo = js.get_data(as_text=True)
    assert "window.copiarDadosDaPessoa" in corpo
    # copia por SUFIXO: é isso que faz `filiacao1_nome` virar
    # `declarante_nome` sem uma lista de campos escrita à mão, que
    # envelheceria no dia em que a ficha ganhasse um campo novo.
    assert "slice(prefixoOrigem.length)" in corpo


def test_os_campos_copiados_tem_destino_do_outro_lado(c):
    """A cópia percorre os campos da origem e procura o mesmo SUFIXO no
    destino. Campo que exista na mãe e não no declarante fica para trás,
    calado — e o escrevente só descobre isso no papel."""
    html = nascimento(c)
    origem = set(re.findall(r'name="filiacao1_([a-z_]+)"', html))
    destino = set(re.findall(r'name="declarante_([a-z_]+)"', html))
    assert origem, "a filiação 1 não tem campo nenhum para copiar"
    faltando = sorted(origem - destino)
    assert not faltando, (
        f"o declarante não tem onde receber: {faltando} — a cópia deixaria "
        f"esses campos para trás sem avisar")


def test_a_copia_NAO_e_automatica(c):
    """O pai não entra no assento por omissão. Quem declara é quem declara, e
    um formulário que se preenchesse sozinho poria no livro uma pessoa que
    não declarou nada."""
    html = nascimento(c)
    achado = re.search(r'name="declarante_nome"\s*value="([^"]*)"', html)
    assert achado, "a tela do nascimento não tem o campo do nome do declarante"
    assert achado.group(1) == "", (
        "o nome do declarante veio preenchido na tela nova")

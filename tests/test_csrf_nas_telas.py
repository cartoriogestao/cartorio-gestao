"""Toda tela que grava tem de mandar o token, e isto se varre.

O DEFEITO QUE ISTO CONSERTA, e ele estava de pé no servidor.
    Em 27/08/2026, às 16h18, o escrevente clicou em «trazer as configurações do
    E-Ofício» na tela do selador e levou um **HTTP 400**. Não era o selador: era
    o formulário, que não mandava o `csrf_token` que a casa exige de todo POST
    (`app.py`, `before_request`).

    A tela do selador tinha **seis** formulários assim, e mais três telas do
    Protesto — dez ao todo, entre elas a de **receber remessa da CRA**, por onde
    entram 93% dos títulos desta casa.

O QUE ISSO CUSTAVA, e é o pior da história: **os quatro cliques da configuração
    do selador eram os quatro que não funcionavam**. O selo automático ficou
    esperando uma configuração que a tela não deixava fazer, e a explicação que
    o balcão via era «bad request error».

POR QUE NENHUM TESTE PEGOU
    Os testes de tela deste projeto usam o cliente do Flask e montam o POST
    **com o token na mão**. Eles provam que a ROTA funciona; nenhum provava que
    a TELA manda o que a rota exige. Este varre o HTML.

O PISO existe porque varredor que deixa de achar passa calado — se alguém mudar
    a forma do formulário e a expressão parar de casar, o número cai e o teste
    fica vermelho, em vez de aprovar tudo achando nada.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TELAS = Path(__file__).resolve().parents[1] / "templates"

# `<form ... method="post" ...>`, com aspas de qualquer tipo e em qualquer ordem
FORMULARIO = re.compile(r"<form\b[^>]*\bmethod\s*=\s*[\"']post[\"'][^>]*>", re.I)
TOKEN = re.compile(r"name\s*=\s*[\"']csrf_token[\"']", re.I)

# Medido em 27/08/2026, depois da correção: **193 formulários** nas 100 telas.
# O piso fica abaixo do medido de propósito — ele existe para pegar a expressão
# que parou de casar, e não para congelar o número: tela que perde um formulário
# por motivo legítimo não deve ficar vermelha aqui.
PISO_DE_FORMULARIOS = 180


def _formularios(texto: str) -> list[str]:
    """Cada formulário POST com o que vem até o `</form>` dele.

    O token pode estar em qualquer lugar de dentro — logo depois da abertura,
    como escrevemos, ou no meio dos campos, como algumas telas antigas fazem.
    """
    partes = []
    for m in FORMULARIO.finditer(texto):
        fim = texto.find("</form>", m.end())
        partes.append(texto[m.start():fim if fim != -1 else len(texto)])
    return partes


def _todos() -> list[tuple[Path, str]]:
    achados = []
    for tela in sorted(TELAS.glob("*.html")):
        for corpo in _formularios(tela.read_text(encoding="utf-8")):
            achados.append((tela, corpo))
    return achados


def test_todo_formulario_que_grava_manda_o_token():
    """O que a rota exige, a tela manda — e isto vale para as 100 telas."""
    sem = sorted({tela.name for tela, corpo in _todos() if not TOKEN.search(corpo)})
    assert not sem, (
        "Estas telas têm formulário que grava e NÃO mandam o csrf_token. "
        "Todo POST sem ele leva HTTP 400 na cara de quem clicou, e a tela do "
        "selador já custou isso ao balcão em 27/08/2026: " + ", ".join(sem))


def test_o_varredor_continua_achando_formulario():
    """Piso: expressão que deixa de casar aprova tudo achando nada."""
    quantos = len(_todos())
    assert quantos >= PISO_DE_FORMULARIOS, (
        f"O varredor achou só {quantos} formulários, e o piso é "
        f"{PISO_DE_FORMULARIOS}. Ou as telas encolheram, ou a expressão parou "
        f"de casar — e a segunda hipótese faz este teste passar sem conferir "
        f"nada.")


@pytest.mark.parametrize("tela", [
    "selador_config.html",          # os quatro cliques da configuração
    "protesto_remessa_conferir.html",  # por onde entram 93% dos títulos
    "protesto_remessas.html",
    "protesto_desistencias.html",
])
def test_as_quatro_telas_que_estavam_quebradas(tela):
    """As dez formas achadas em 27/08/2026, uma a uma.

    Nomeadas de propósito: quem as consertar sem querer desfazer fica sabendo
    QUE eram estas, e não uma lista abstrata.
    """
    corpos = _formularios((TELAS / tela).read_text(encoding="utf-8"))
    assert corpos, f"{tela} deixou de ter formulário — confira se é isso mesmo"
    assert all(TOKEN.search(c) for c in corpos), f"{tela} voltou a esquecer o token"


def test_nenhuma_tela_CHAMA_csrf_token_como_funcao():
    """`csrf_token()` derruba a tela inteira, e uma estava derrubada.

    **ACHADO NO LOG DO SERVIDOR EM 16/09/2026**, e não por teste:
    `templates/ri_revisoes.html` escrevia `{{ csrf_token() }}` e a tela
    respondia `TypeError: 'str' object is not callable` — HTTP 500 na cara de
    quem fosse conferir uma revisão. Nesta casa `csrf_token` chega ao modelo
    como **valor**, e não como a função global do Jinja; 160 telas escrevem
    `{{ csrf_token }}` e uma escrevia a outra forma.

    **O varredor de CSRF que já existia não pegava**, e o motivo é instrutivo:
    ele confere que o formulário TEM o campo, e aquele tinha — o campo estava
    lá, com um valor que estourava ao ser montado. **Ter o campo e conseguir
    montá-lo são duas coisas**, e só a segunda faz a tela abrir.

    E o aviso estava escrito, em `ri_ficha.html`, na linha 34: quem o leu
    escapou; quem não o leu repetiu. **Comentário não varre; teste varre.**
    """
    # E O VARREDOR BATEU NA PROPRIA PROSA NA PRIMEIRA RODADA — decima
    # terceira vez neste projeto. O aviso de `ri_ficha.html` cita
    # `csrf_token()` justamente para dizer que ninguem deve escreve-lo, e
    # ele mora num comentario Jinja de duas linhas: olhar linha a linha nao
    # o enxerga inteiro. **Comentario se tira do texto antes de medir**, e
    # nao se tenta reconhecer no meio da linha.
    comentario = re.compile(r"\{#.*?#\}", re.S)
    achados = []
    for tela in sorted(TELAS.glob("*.html")):
        texto = comentario.sub("", tela.read_text(encoding="utf-8"))
        for numero, linha in enumerate(texto.splitlines(), 1):
            if "csrf_token()" in linha:
                achados.append(f"{tela.name}:{numero}")
    assert not achados, (
        "estas telas chamam csrf_token como função e respondem HTTP 500: "
        + ", ".join(achados))


@pytest.mark.parametrize("tela", [
    "login_dois_fatores.html",
    "login_dois_fatores_cadastrar.html",
    "dois_fatores.html",
    "gestor_dois_fatores.html",
])
def test_as_telas_da_verificacao_em_duas_etapas_mandam_o_token(tela):
    """As quatro telas do LG02 (19/10/2026), nomeadas.

    Duas delas são de quem AINDA NÃO ENTROU — a meia-sessão, entre a senha e o
    código. Ali o token é o que a troca de sessão acabou de gerar, e uma tela
    que o esquecesse trancaria do lado de fora justamente quem ativou a
    verificação: «bad request» no lugar do código.
    """
    corpos = _formularios((TELAS / tela).read_text(encoding="utf-8"))
    assert corpos, f"{tela} deixou de ter formulário — confira se é isso mesmo"
    assert all(TOKEN.search(c) for c in corpos), f"{tela} esqueceu o token"

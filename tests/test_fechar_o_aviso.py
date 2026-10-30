"""Fechar o aviso da tela — relato #62, de 15/09/2026, construído em 17/09/2026.

O PEDIDO, e as duas metades dele.
    O Analista de Sistemas escreveu, na tela do painel: «preciso dar opção de
    baixar os avisos em todas as telas». O oficial completou o que ele quis
    dizer: o aviso SAI DA TELA e VOLTA quando a tela for carregada de novo — e
    **não há «excluir para sempre»**.

    E a razão de não haver é a que esta casa já escreveu três vezes: o aviso do
    que só o oficial pode informar e o da disputa de escrita existem justamente
    para não serem ignorados. Um botão que os apagasse de vez faria o problema
    sumir da vista sem resolver — e a tela passaria a afirmar uma casa em ordem
    que não é a casa. «Carimbo que mente» é o defeito que este projeto mais
    persegue.

O QUE ESTE ARQUIVO MEDE, e são três coisas diferentes:
    1. **Todo aviso marcado tem o seu botão** — a marca `data-aviso` e a chamada
       da macro andam juntas, e o número das duas é o mesmo;
    2. **O script não guarda nada** — nem no banco, nem no navegador. Ele tira
       da frente e ponto; é o `hidden` que o devolve no próximo carregamento;
    3. **O aviso é desenhado pelo SERVIDOR** — a mesma tela, pedida duas vezes,
       traz o aviso nas duas. É isto que prova que o clique não o apagou de
       verdade.

POR QUE ISTO É TESTE E NÃO COMENTÁRIO
    A macro `_aviso.html` afirma, por escrito, que existe teste que confere o
    que ela faz. **Comentário que afirma sem medir é a promessa com cara de
    prova** — e este projeto já pagou por isso duas vezes (o `strDescricao` que
    eu inventei, e o `destino_encerramento` que não existe no esquema). O que a
    macro promete, este arquivo confere.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
TELAS = RAIZ / "templates"
ESTATICOS = RAIZ / "static"

# Quantos avisos a casa mostra hoje: os QUATRO de `base.html` — o retorno da
# tela, que aparece nos dois desenhos dela (o de dentro e o de quem ainda não
# entrou), o do que só o oficial informa e o da disputa de escrita — e o do
# painel, em `dashboard.html`. São **cinco marcas**, e o número foi contado, e
# não somado de cabeça: o recado da tela conta duas vezes porque o `base.html`
# desenha dois layouts. O piso existe porque varredor que deixa de achar passa
# calado — se a marca mudar de nome, a conta cai a zero e este teste fica
# vermelho, em vez de aprovar tudo achando nada.
PISO_DE_AVISOS = 5

# O aviso é quem tem a marca; o botão é quem a fecha. Os dois têm de andar
# juntos, e é esta igualdade que o teste confere.
MARCA = "data-aviso>"
BOTAO = "aviso.fechar()"

# O que o script NÃO pode fazer, e cada linha tem um motivo:
#   * guardar — é a diferença entre «fechar» e «excluir para sempre», que o
#     oficial decidiu não existir;
#   * falar com o servidor — fechar é gesto de tela, e não muda fato nenhum.
PROIBIDO_NO_SCRIPT = {
    "localStorage": "o aviso voltaria fechado na próxima visita",
    "sessionStorage": "o aviso voltaria fechado na próxima visita",
    "indexedDB": "o aviso voltaria fechado na próxima visita",
    "document.cookie": "o aviso voltaria fechado na próxima visita",
    "fetch(": "fechar aviso não é fato para gravar no servidor",
    "XMLHttpRequest": "fechar aviso não é fato para gravar no servidor",
    "sendBeacon": "fechar aviso não é fato para gravar no servidor",
}

# O botão já vem no HTML, pela macro — o script só escuta o clique.
PROIBIDO_DESENHAR = {
    "createElement": "o botão já vem no HTML, pela macro `_aviso.html`",
    "innerHTML": "o botão já vem no HTML, pela macro `_aviso.html`",
}


def _texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _macro() -> str:
    return _texto(TELAS / "_aviso.html")


def _sem_comentario_js(texto: str) -> str:
    """O script sem os comentários — porque o varredor bate na própria prosa.

    É a lição repetida deste projeto: o comentário de `avisos.js` cita
    `localStorage` justamente para dizer que ele NÃO é usado, e o de
    `base.html` explica o que o script não faz. Procurar a palavra no arquivo
    inteiro acusa o texto que existe para impedir o defeito.
    """
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", texto)


def _telas_com_aviso() -> list[Path]:
    return [tela for tela in sorted(TELAS.glob("*.html")) if MARCA in _texto(tela)]


def _avisos_e_botoes() -> tuple[int, int]:
    avisos = botoes = 0
    for tela in TELAS.glob("*.html"):
        texto = _texto(tela)
        avisos += texto.count(MARCA)
        botoes += texto.count(BOTAO)
    return avisos, botoes


# --------------------------------------------------------------------------
# 1. O botão existe onde há aviso
# --------------------------------------------------------------------------

def test_todo_aviso_marcado_tem_o_seu_botao():
    """A marca e a chamada andam juntas, e o número das duas é o mesmo.

    Contar em vez de conferir um por um é de propósito: a próxima tela que
    ganhar um aviso entra na conta sozinha, sem ninguém lembrar de acrescentá-la
    a uma lista — **lista escrita à mão envelhece na tarde em que se escreve**,
    e este projeto já pagou isso no menu e no teste do menu.
    """
    avisos, botoes = _avisos_e_botoes()
    assert avisos == botoes, (
        f"Há {avisos} avisos marcados com `{MARCA}` e {botoes} chamadas de "
        f"`{BOTAO}`. Todo aviso marcado precisa do seu botão, e todo botão "
        f"precisa do aviso que ele fecha.")


def test_a_conta_nao_zerou():
    """Piso: o varredor que deixa de achar aprova tudo achando nada."""
    avisos, _ = _avisos_e_botoes()
    assert avisos >= PISO_DE_AVISOS, (
        f"O varredor achou {avisos} avisos e o piso é {PISO_DE_AVISOS}. Ou os "
        f"avisos encolheram, ou a marca mudou de forma e este teste passou a "
        f"conferir nada.")


def test_as_telas_que_tem_aviso_importam_a_macro():
    """A macro se importa com outro nome, e não se chama de qualquer jeito."""
    for tela in _telas_com_aviso():
        texto = _texto(tela)
        assert "{% import '_aviso.html' as aviso %}" in texto, (
            f"{tela.name} usa o aviso e não importa `_aviso.html` — a macro "
            f"fica indefinida e a tela responde HTTP 500 ao ser desenhada.")


@pytest.mark.parametrize("tela", ["base.html", "dashboard.html"])
def test_as_duas_telas_dos_avisos(tela):
    """As telas de hoje, nomeadas: quem as mexer sabe quais eram.

    `base.html` é a faixa do alto, que aparece em TODA tela do sistema;
    `dashboard.html` é o aviso da inspeção, que só existe no painel.
    """
    texto = _texto(TELAS / tela)
    assert MARCA in texto and BOTAO in texto, f"{tela} perdeu o botão de fechar"


def test_o_botao_so_existe_nas_telas_da_casa():
    """«Em todas as telas» NÃO se cumpriu ao pé da letra, e é decisão dele.

    Medido em 17/09/2026, contando as aberturas de tag com `flash` ou `notice`
    no texto dos `.html`: são **centenas de desenhos de aviso** espalhados pela
    árvore, e o botão está em **cinco**, todos em duas telas. As outras não
    avisam da CASA — explicam a TELA: «nenhuma ficha encontrada, use o cadastro
    abaixo», «EM LAVRATURA», «o teor tem 7 campos em branco». Fechá-las
    esconderia o motivo de um campo ou o caminho de um botão, e quem chega
    depois não teria como saber o que se perdeu.

    **Isto é a régua da decisão, e não um enfeite.** Quem acrescentar
    `aviso.fechar()` a uma tela de módulo fica vermelho aqui e vai perguntar por
    quê; sem esta linha, a decisão viveria só no comentário — e comentário que
    afirma sem medir é a promessa com cara de prova. A contagem NÃO é guardada
    de propósito: ela anda a cada tela nova, e número que anda em teste vira
    teste vermelho sem defeito.
    """
    # A FAIXA DO ALTO MUDOU DE ARQUIVO, E NÃO DE NATUREZA — 14/10/2026. Desde
    # a 3.6.259 (avisos v2, 29–30/09/2026) as faixas da casa moram em
    # `_faixas_compactas.html`, que o `base.html` inclui em TODA tela; é o
    # mesmo lugar da tela, num arquivo à parte.
    #
    # A MOLDURA NOVA ENTROU NA LISTA EM 30/10/2026, e pela mesma razão: enquanto
    # as duas existem, o recado da tela sai de `base.html` ou de `base_novo.html`,
    # conforme a escolha de quem atende (`navegacao_web`). Quando a etapa de
    # limpeza tirar a antiga, sai `base.html`.
    onde = sorted(tela.name for tela in TELAS.glob("*.html") if BOTAO in _texto(tela))
    assert onde == ["_faixas_compactas.html", "base.html", "base_novo.html", "dashboard.html"], (
        f"o botão de fechar o aviso está em {onde}. Ele existe na faixa do alto "
        f"(`base.html`) e no painel (`dashboard.html`), que avisam da CASA; o "
        f"aviso que explica a tela não se fecha, porque quem chega depois perde "
        f"o motivo do campo ou o caminho do botão.")


def test_o_botao_nao_e_desenhado_pelo_script():
    """Ele vem no HTML — e é isso que faz o aviso funcionar sem JavaScript."""
    html = _macro()
    assert "data-aviso-fechar" in html, (
        "a macro `_aviso.html` deixou de trazer o botão; o script não o "
        "desenha, e sem ele o aviso fica sem como ser fechado")
    script = _sem_comentario_js(_texto(ESTATICOS / "avisos.js"))
    for palavra, motivo in PROIBIDO_DESENHAR.items():
        assert palavra not in script, (
            f"o script desenha o botão com `{palavra}`, e {motivo} — numa tela "
            f"em que o arquivo não carregasse, ele ficaria sem botão nenhum")


# --------------------------------------------------------------------------
# 2. O script não guarda nada
# --------------------------------------------------------------------------

def test_o_script_nao_guarda_nada_e_nao_fala_com_o_servidor():
    """«Fechar» é tirar da frente; «excluir para sempre» não existe.

    O script sem os comentários, porque o comentário do próprio arquivo cita
    `localStorage` para dizer que ele não é usado — e o varredor deste projeto
    já bateu na própria prosa treze vezes.
    """
    script = _sem_comentario_js(_texto(ESTATICOS / "avisos.js"))
    achados = [f"{palavra} ({motivo})"
               for palavra, motivo in PROIBIDO_NO_SCRIPT.items()
               if palavra in script]
    assert not achados, (
        "o script do aviso faz o que ele não pode: " + "; ".join(achados))


def test_o_script_esconde_e_nao_apaga():
    """Ele tira da tela; quem desenha o aviso é o servidor, a cada carga.

    `hidden` é a forma certa por dois motivos: o aviso CONTINUA no documento
    (então uma varredura ou o próprio navegador ainda o enxergam), e ele volta
    sozinho no próximo carregamento, porque o servidor o desenha de novo.
    """
    script = _sem_comentario_js(_texto(ESTATICOS / "avisos.js"))
    assert "hidden = true" in script, (
        "o script deixou de esconder o aviso com `hidden` — se ele passou a "
        "remover o elemento do documento, a promessa «volta ao carregar a tela» "
        "passou a depender de o servidor desenhá-lo de novo, e é isso que o "
        "teste da tela confere")


# --------------------------------------------------------------------------
# 3. O aviso volta quando a tela é carregada de novo
# --------------------------------------------------------------------------

def test_o_aviso_volta_na_segunda_carga(cg_casa_logada):
    """A mesma tela, pedida duas vezes, traz o aviso nas duas.

    É esta a prova de que fechar não apagou nada: o aviso é desenhado pelo
    SERVIDOR a cada carregamento, e não há estado guardado em lugar nenhum de
    onde ele pudesse ter sido removido. Uma tela que só trouxesse o aviso na
    primeira vez estaria afirmando uma casa em ordem que não é a casa.
    """
    casa = cg_casa_logada
    with casa["db"].transaction() as con:
        con.execute(
            "INSERT INTO nu_implantacao (chave, tipo, titulo, motivo, situacao,"
            " declarada_em) VALUES (?,?,?,?,?,?)",
            ("teste:fechar-aviso", "NUMERO", "Livro de teste",
             "só o oficial sabe", "ABERTA", "2026-09-17T09:00:00"))

    primeira = casa["c"].get("/").get_data(as_text=True)
    segunda = casa["c"].get("/").get_data(as_text=True)

    for numero, html in (("primeira", primeira), ("segunda", segunda)):
        assert "esperando você" in html, f"o aviso sumiu na {numero} carga"
        assert "data-aviso-fechar" in html, (
            f"o botão sumiu na {numero} carga")


def test_o_aviso_do_retorno_da_tela_tambem_tem_o_botao(cg_casa):
    """O flash (o recado que a rota devolve) entra na mesma regra.

    Ele é a categoria mais comum — «salvo com sucesso», «não deu» —, e é a
    única que existe em toda tela do sistema. Senha errada é o caminho mais
    curto para um flash de verdade sem montar domínio nenhum.

    O usuário se cria aqui **sem entrar**: a casa recém-instalada não tem
    usuário nenhum, e sem ele o `/login` manda para o `/setup` — a tela de
    entrar só existe depois que existe quem entre.
    """
    casa = cg_casa
    casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")

    html = casa["c"].get("/login").get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela de login não trouxe o csrf_token"

    resposta = casa["c"].post("/login", data={
        "username": "mario", "password": "errada-de-proposito",
        "csrf_token": achado.group(1),
    }, follow_redirects=True).get_data(as_text=True)

    assert "flash" in resposta, "o login errado não devolveu recado nenhum"
    assert "data-aviso-fechar" in resposta, (
        "o recado do flash não tem botão de fechar — ele é o aviso que aparece "
        "em toda tela, e é o que o relato mais alcança")


# --------------------------------------------------------------------------
# 4. O botão fica onde se vê
# --------------------------------------------------------------------------

def test_o_css_ancora_o_botao_no_aviso():
    """Sem isto o botão voa para o `.topbar`, que também é posicionado.

    Um botão de 26 px apoiado no `<body>` sairia no canto errado da tela, e o
    defeito é do tipo que só aparece quando alguém abre a tela — CSS errado não
    levanta erro em teste de domínio.
    """
    css = _texto(ESTATICOS / "app.css")
    assert ".notice,.flash{position:relative" in css, (
        "o aviso perdeu o `position:relative`; o botão vai se apoiar no "
        "primeiro ancestral posicionado, que é a barra do alto")
    assert ".aviso-fechar{" in css, "o botão de fechar o aviso perdeu o estilo"
    assert "padding-right:44px" in css, (
        "o aviso perdeu o espaço reservado para o botão — quatro linhas de "
        "texto justificado passariam por baixo do X")

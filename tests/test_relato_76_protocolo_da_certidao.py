"""O PROTOCOLO DA CERTIDÃO SE ESCOLHE DA LISTA — relato #76, 17/09/2026.

    «permitir à selecao de protocolo tambem na parte de emissao de certidao
    ver os protocolos abertos e selecionar mais rapido»

    «ter que lembrar o numero do protocolo de determinado cliente pode
    atrasar a emissao da certidao, melhor mostrar os protocolos abertos e
    aguardando pagamento como opcao de escolha»

O CAMPO ERA LIVRE, E CONTINUA
    `ri_certidoes.protocolo` guarda TEXTO digitado, e a rota lê
    `request.form.get("protocolo")`. A mudança é na TELA: o mesmo campo, com
    a lista ao lado. Protocolo fora da janela continua se digitando — e há
    teste aqui que digita um de fora e confere que ele chega ao banco.

O QUE A LISTA TEM, E POR QUE SÃO DUAS COISAS
    Medido na produção em 17/09/2026, nas 373 certidões gravadas:

      · 368 citam o protocolo de CAIXA (`cx_protocolos.numero`) — todas do
        acervo, e é este o pedido do balcão;
      · as 4 que ESTE sistema emitiu citam a **prenotação**
        (`ri_protocolos.numero`): 11571 (três vezes) e 11559.

    São as duas coisas que esta casa chama de «protocolo» nesta ficha, e a
    lista mostra as duas, cada uma dizendo qual é. Ordem: caixa primeiro,
    que é o pedido que o oficial descreveu.

O RECORTE É DO RI, E ELE É GRANDE
    Medido: sem o recorte, os 80 protocolos da janela (ABERTO e A_PAGAR)
    trazem **18 do RI** — os outros 62 são firma, RCPN, protesto, notas e
    RCPJ. Com `atribuicao="RI"`, os mesmos 80 cobrem **08/05 a 17/09**.

    Protocolo ENCERRADO não entra, e isso já valia antes deste relato:
    `ENTREGUE` e `CANCELADO` ficam fora, de `protocolos_do_caixa_abertos`.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Os números deste teste são os da produção, para quem ler achar o caso:
# 11571 é a prenotação que a certidão 7/2026 desta casa citou.
PRENOTACAO = 11571
CAIXA_DO_RI = "2026.09.23"
CAIXA_DE_FIRMA = "2026.09.24"


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(casa, numero="5377") -> int:
    """A ficha do relato — aberta como a casa a abre."""
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf)
               VALUES (?, '2', '2', 'ATIVA', 'ESTRUTURADA', 'MANUAL',
                       '2026-09-17T09:00', '2026-09-14', 'Cidade Exemplo', 'MA')""",
            (numero,))
        mid = int(cur.lastrowid)
    con.close()
    return mid


def _prenotacao_aberta(casa, numero=PRENOTACAO, apresentante="EDILSON") -> None:
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
                   apresentante, situacao, criado_em)
               VALUES (?, '1A', '2026-09-15', ?, 'ABERTO', '2026-09-15T10:00')""",
            (numero, apresentante))
    con.close()


def _caixa(casa, numero, atribuicao, interessado, situacao="A_PAGAR") -> None:
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES (?, '2026-09-17', ?, ?, ?, '2026-09-17T10:00')""",
            (numero, atribuicao, interessado, situacao))
    con.close()


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _lista_da_certidao(html: str) -> str:
    """O PEDAÇO da página que é a lista deste relato.

    Recortar é o que torna o teste uma afirmação: o protocolo de firma
    APARECE noutra lista da mesma ficha (a do protocolo de caixa, que serve o
    ato e não a certidão), e procurar a página inteira aprovaria a lista da
    certidão por causa de uma linha que não é dela. É o varredor que mede a
    coisa errada — a família que já apareceu sete vezes neste projeto.
    """
    achado = re.search(
        r'<datalist id="protocolos-da-certidao">(.*?)</datalist>', html, re.S)
    assert achado, (
        "a tela da ficha não tem a lista `protocolos-da-certidao` — o campo "
        "do protocolo da certidão continua sendo digitação no escuro")
    return achado.group(1)


def _form_da_certidao(html: str, mid: int) -> str:
    """O formulário que EMITE a certidão — e não outro que peça protocolo.

    A ficha tem mais de um campo chamado «protocolo»: o do rascunho do ato
    («Guardar na fila de revisão», onde ele é o número da prenotação) e o da
    certidão, que é o deste relato. Procurar o primeiro `<input name=…>` da
    página acharia o outro — foi o que a primeira versão deste teste fez, e o
    recorte por `action` é o que separa os dois.
    """
    achado = re.search(
        r'<form[^>]*action="[^"]*/registro-imoveis/%d/certidao"[^>]*>(.*?)</form>'
        % mid, html, re.S)
    assert achado, "o formulário de emitir certidão não está na ficha"
    return achado.group(1)


# --------------------------------------------------------- a lista está ligada


def test_a_tela_oferece_a_lista_no_campo_do_protocolo(cg_casa_logada):
    """O campo e a lista, e o `list=` que os liga.

    Sem o `list=`, a lista existe na página e não é oferecida a ninguém —
    é a «peça pronta que ninguém usa» dentro do próprio HTML.
    """
    casa = cg_casa_logada
    mid = _matricula(casa)
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert 'id="protocolos-da-certidao"' in html
    formulario = _form_da_certidao(html, mid)
    campo = re.search(r'<input[^>]*name="protocolo"[^>]*>', formulario)
    assert campo, "o campo do protocolo da certidão sumiu da tela"
    assert 'list="protocolos-da-certidao"' in campo.group(0)


def test_o_protocolo_do_RI_com_o_interessado_aparece_na_lista(cg_casa_logada):
    """É o pedido: achar o protocolo do cliente pelo nome, e não de cabeça.

    A opção leva o número (é ele que vai para o campo) e o interessado (é ele
    que o escrevente reconhece). Medido na produção: os 4.628 protocolos
    abertos têm interessado preenchido.
    """
    casa = cg_casa_logada
    mid = _matricula(casa)
    _caixa(casa, CAIXA_DO_RI, "RI", "EDILSON FIGUEIREDO BARROS")
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    lista = _lista_da_certidao(html)
    assert f'value="{CAIXA_DO_RI}"' in lista
    assert "EDILSON FIGUEIREDO BARROS" in lista


def test_a_prenotacao_aberta_entra_na_lista_com_o_nome_dela(cg_casa_logada):
    """As certidões que ESTE sistema emitiu citam a prenotação — medido, 4 de
    4. Ela vai rotulada, para não se confundir com o número do caixa."""
    casa = cg_casa_logada
    mid = _matricula(casa)
    _prenotacao_aberta(casa)
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    lista = _lista_da_certidao(html)
    assert f'value="{PRENOTACAO}"' in lista
    assert "prenotação" in lista
    assert "EDILSON" in lista


def test_o_protocolo_de_outra_atribuicao_nao_entra_na_lista_da_certidao(
        cg_casa_logada):
    """A firma não tem o que fazer na certidão da matrícula — e é a maior
    parte da janela: dos 80, 62 não são do RI."""
    casa = cg_casa_logada
    mid = _matricula(casa)
    _caixa(casa, CAIXA_DE_FIRMA, "FIRMAS", "FULANA DE TAL")
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert CAIXA_DE_FIRMA not in _lista_da_certidao(html)


def test_protocolo_encerrado_nao_volta_para_a_lista(cg_casa_logada):
    """`ENTREGUE` é pedido que a casa já fechou. Oferecê-lo faria a certidão
    de hoje citar o protocolo de um atendimento do ano passado."""
    casa = cg_casa_logada
    mid = _matricula(casa)
    _caixa(casa, "2026.05.001", "RI", "ANTIGO", situacao="ENTREGUE")
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert "2026.05.001" not in _lista_da_certidao(html)


# --------------------------------------------- o campo continua livre, e grava


def _emitir(casa, mid, protocolo):
    tela = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    # `ONUS` e não `NEGATIVA`: a «certidão negativa de matrícula» saiu da tela
    # em 18/09/2026 (problema #75) porque não certifica ESTA matrícula — o texto
    # dela busca o nome da pessoa nos livros todos. Este teste é sobre o
    # PROTOCOLO, e não sobre o tipo; qualquer um dos três que ficaram serve.
    casa["c"].post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": "ONUS",
        "fonte_corpo": "TEXTO", "requerente": "FULANO DE TAL",
        "protocolo": protocolo}, follow_redirects=True)
    con = _con(casa)
    linha = con.execute(
        "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha, "a certidão não foi emitida"
    return dict(linha)


def test_o_protocolo_escolhido_da_lista_fica_gravado_na_certidao(cg_casa_logada):
    casa = cg_casa_logada
    mid = _matricula(casa)
    _caixa(casa, CAIXA_DO_RI, "RI", "EDILSON FIGUEIREDO BARROS")

    assert _emitir(casa, mid, CAIXA_DO_RI)["protocolo"] == CAIXA_DO_RI


def test_protocolo_fora_da_lista_continua_se_digitando(cg_casa_logada):
    """A lista é uma janela (80), e a casa tem protocolo de 2022.

    Se o campo virasse `select`, o balcão ficaria sem como citar o protocolo
    antigo — trocar 4.628 linhas de digitação por um beco sem saída.
    """
    casa = cg_casa_logada
    mid = _matricula(casa)

    assert _emitir(casa, mid, "11559")["protocolo"] == "11559"

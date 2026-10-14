"""A RESPOSTA DO PAPEL — o botao entrega PDF, e o `.odt` continua a um clique.

Pedido do oficial em 01/09/2026: *«a ferramenta de impressão está baixando um
arquivo, preciso que gere o pdf para impressão nesse botão»*.

**ESTA DECISAO MORA NUM LUGAR SO, e a razao e a de sempre nesta casa.** Sete
rotas entregam papel — as quatro certidoes, a ficha, a nota e o recibo —, e a
mesma decisao escrita sete vezes divergiria no primeiro conserto: uma tela
passaria a entregar PDF e a vizinha continuaria baixando `.odt`, sem ninguem
saber por que. E a licao das duas macros de `_cobrar.html`, e a consistencia
aqui nao e estetica: e o operador achar o mesmo botao fazendo a mesma coisa em
qualquer atribuicao.

**O `.odt` NAO SAI DE CENA.** `?formato=odt` continua devolvendo o arquivo
editavel, porque ha papel que o oficial abre para ajustar antes de imprimir —
e porque, no dia em que o LibreOffice nao responder, o balcao nao pode parar.

**E O PDF QUE NAO SAI VOLTA PARA A TELA, com a frase.** Servir o `.odt`
calado, depois de alguem clicar em «Imprimir», entregaria um arquivo diferente
do pedido sem dizer — e quem esta no balcao acharia que o botao esta quebrado.
A recusa e `warning`, e nao `danger`: nao houve erro de regra nem papel
perdido, houve um formato que nao saiu desta vez.
"""
from __future__ import annotations

from flask import Response, flash, redirect, request

import impressao_pdf as PDF


def resposta_do_papel(odt: bytes, *, nome: str, voltar_para: str,
                      get_setting=None, formato=None):
    """A resposta HTTP do papel. SO LE — nao grava nada, nao audita nada.

    Quem audita e a rota, que sabe o nome do ato; este devolve so a resposta.
    `voltar_para` e para onde a tela volta se o PDF nao sair — sem ele a
    recusa nao teria onde aparecer.
    """
    pedido = formato if formato is not None else request.args.get("formato")
    try:
        conteudo, tipo, arquivo, entrega = PDF.papel_para_baixar(
            odt, nome=nome, formato=pedido, get_setting=get_setting)
    except PDF.PdfError as erro:
        flash(f"{erro} Para pegar o arquivo editável, use «Baixar em .odt».",
              "warning")
        return redirect(voltar_para)
    return Response(conteudo, mimetype=tipo,
                    headers={"Content-Disposition":
                             f'{entrega}; filename="{arquivo}"'})

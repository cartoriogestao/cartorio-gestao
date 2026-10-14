"""
O QUE O NAVEGADOR PODE ABRIR NA PRÓPRIA TELA — e o que tem de baixar.

    «esteja disponível para analisar no visualizador de pdf direto no sistema,
     disponível para baixar» — o oficial, 03/09/2026

O DEFEITO QUE ISTO CONSERTA, E ELE É ANTIGO
    Havia **uma** rota para servir arquivo guardado — `/arquivo/<id>` — e ela
    manda `as_attachment=True` em toda chamada, o que põe
    `Content-Disposition: attachment` e faz **o navegador baixar, sempre**.

    O relato #25 do oficial, de 29/08/2026, pedia *«anexar documentos e
    **visualizar** esses documentos»*, e `ri_documentos.e_imagem` foi escrita
    para isso — com o comentário «QUEM LAVRA PRECISA VER, E NAO BAIXAR». A tela
    do RI põe `target="_blank"` no link quando o arquivo é imagem ou PDF; **e a
    rota baixa do mesmo jeito.** A metade que decide estava pronta e a metade
    que serve nunca soube dela — a peça pronta que ninguém chama, outra vez.

O QUE PODE ABRIR NA TELA, E POR QUE A LISTA É CURTA
    Um arquivo servido **em linha** roda na **origem do sistema**. Quem abrir um
    `.html` ou um `.svg` enviado por terceiro estará rodando o script daquele
    terceiro dentro da sessão de quem está no balcão — com o cookie de login à
    mão. Não é hipótese remota: o balcão recebe arquivo de fora todo dia.

    Então a lista é de coisas que **o navegador desenha e não executa**:

        pdf, png, jpg, jpeg, gif, webp, bmp

    **`svg` NÃO ENTRA, e ele é imagem.** SVG é XML e carrega `<script>`; a
    tentação de o pôr ao lado do `png` é exatamente o engano que esta lista
    existe para impedir. **`tif`/`tiff` também não**: quase nenhum navegador os
    desenha, e um arquivo que não abre servido «em linha» vira tela em branco,
    que é pior que o botão de baixar.

    Tudo o mais **baixa**, que é o comportamento que sempre funcionou.

E ISTO NÃO É A ÚNICA TRAVA
    Quem serve manda também `X-Content-Type-Options: nosniff` — sem ele o
    navegador pode adivinhar o tipo pelo conteúdo e tratar como HTML um arquivo
    que dissemos ser PDF — e uma política que proíbe script na página servida.
    **A lista decide o que se oferece; os cabeçalhos protegem o que se serviu.**
"""
from __future__ import annotations

from pathlib import Path

# O que o navegador DESENHA sem executar. Ver o cabeçalho para o que ficou de
# fora e por quê — em especial o `svg`, que é imagem e é XML com script.
TIPOS_QUE_ABREM_NA_TELA: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
}

# **O VISUALIZADOR DE PDF É O DO NAVEGADOR**, e é ele que o oficial pediu: o
# papel abre na tela com o botão de imprimir do lado, sem instalar nada. Esta
# distinção existe porque a tela mostra o PDF num quadro e a imagem numa
# etiqueta `<img>` — são elementos diferentes, e quem monta a tela precisa saber
# qual usar.
TIPO_DO_PDF = "pdf"


def extensao(nome) -> str:
    """A extensão em minúsculas, sem o ponto. Só calcula.

    `Path(...).suffix` e não `rsplit('.')`: um nome sem ponto nenhum devolve
    string vazia nos dois, mas um nome que **começa** com ponto (`.env`) o
    `rsplit` leria como extensão `env`.
    """
    return Path(str(nome or "")).suffix.lstrip(".").lower()


def abre_na_tela(nome) -> bool:
    """O navegador desenha este arquivo sem executá-lo? Só calcula."""
    return extensao(nome) in TIPOS_QUE_ABREM_NA_TELA


def e_pdf(nome) -> bool:
    """É PDF — o que vai no quadro do visualizador. Só calcula."""
    return extensao(nome) == TIPO_DO_PDF


def tipo_do_arquivo(nome) -> str:
    """O `Content-Type` que se declara ao servir em linha. Só calcula.

    **Devolve o genérico para o que não abre na tela**, e não `None`: quem
    servir um `.docx` está mandando baixar, e `application/octet-stream` é
    justamente o tipo que diz «isto é para guardar, não para abrir».
    """
    return TIPOS_QUE_ABREM_NA_TELA.get(extensao(nome), "application/octet-stream")


# OS CABEÇALHOS QUE PROTEGEM O QUE JÁ SE DECIDIU SERVIR.
#
#   `nosniff` — sem ele o navegador pode ignorar o tipo que declaramos e
#   adivinhar pelo conteúdo; um arquivo com cara de HTML servido como PDF
#   voltaria a ser HTML, e a lista de cima teria sido para nada.
#
#   `sandbox` — a página servida não roda script, não abre janela e não manda
#   formulário. O visualizador de PDF do navegador continua funcionando: ele é
#   do próprio navegador, e não da página.
#
#   `frame-ancestors 'self'` — só a nossa própria tela pode pôr este arquivo
#   dentro de um quadro. É o que impede outro sítio de embutir o documento do
#   cartório numa página dele.
CABECALHOS_DE_QUEM_MOSTRA: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; frame-ancestors 'self'",
}


def cabecalhos_para_mostrar() -> dict[str, str]:
    """Uma cópia dos cabeçalhos, para a rota pôr na resposta.

    **Cópia, e não o dicionário.** Uma rota que resolvesse acrescentar um
    cabeçalho ao que recebe estaria mudando o de todas as outras — e um dia
    alguém removeria o `nosniff` de uma tela sem saber que removeu de sete.
    """
    return dict(CABECALHOS_DE_QUEM_MOSTRA)

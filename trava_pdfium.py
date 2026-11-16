"""UMA TRAVA SÓ PARA O PDFIUM DO SISTEMA INTEIRO (16/11/2026).

O PDFIUM NÃO AGUENTA DUAS LINHAS DE EXECUÇÃO AO MESMO TEMPO.
    O `pypdfium2` chama a biblioteca em C sem trava nenhuma. No Windows, duas
    linhas dentro dela dão «OSError: exception: access violation writing 0x…»
    — ou derrubam o processo, que é o servidor do balcão. Medido na produção
    em 16/11/2026: a leitura por IA de um óbito (leitura nº 27) caiu assim, e
    o mesmo erro aparecia na miniatura da digitalização do RI e na prévia do
    teor do RTD.

A TRAVA ERA DE CADA MÓDULO, E UMA NÃO SEGURAVA A OUTRA.
    `revisao_anexos` e `revisao_transcricao` tinham cada um a sua; a miniatura
    do RI, a ficha de firma, a impressão e o teor do RTD não tinham nenhuma.
    Agora todo uso do pypdfium2 passa por esta:

        with TRAVA:
            doc = pdfium.PdfDocument(...)
            try:
                ...                     # ler, contar, desenhar
            finally:
                doc.close()

AS REGRAS
    - abrir, ler, desenhar E FECHAR dentro da trava;
    - fechar o documento à mão: o `close` fecha junto as páginas e os textos.
      O que fica para o coletor de lixo é destruído na hora que ele quiser,
      em qualquer linha, fora da trava;
    - a imagem sai por `imagem_pil`, que copia o desenho para o Pillow e
      fecha o bitmap ainda dentro da trava;
    - nada de demorado lá dentro (rede, banco, IA): as outras linhas esperam.

`RLock`: a mesma linha pode entrar de novo — uma função travada que chama
outra também travada não se prende sozinha.
"""
from __future__ import annotations

import threading

TRAVA = threading.RLock()


def imagem_pil(pagina, **opcoes):
    """A página desenhada como imagem do Pillow que não depende mais do PDFium.

    O `to_pil()` do pypdfium2 pode dividir a memória com o bitmap; aqui a
    imagem é copiada e o bitmap fechado na hora. Chamar DENTRO de `TRAVA`.
    `opcoes` vão direto para `PdfPage.render` (scale, grayscale…)."""
    bitmap = pagina.render(**opcoes)
    try:
        return bitmap.to_pil().copy()
    finally:
        bitmap.close()

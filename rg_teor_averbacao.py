"""Compat: reexporta `rg_teor_rtdpj` sob o nome antigo.

A 3.6.91 nasceu como `rg_teor_averbacao`. Na 3.6.92 o módulo passou a cobrir
também o teor de REGISTRO (RCPJ e RTD). Quem ainda importa este nome continua
funcionando; o código novo importa `rg_teor_rtdpj`.
"""
from rg_teor_rtdpj import *  # noqa: F403
from rg_teor_rtdpj import (  # noqa: F401
    TeorRtdpjError,
    TeorAverbacaoError,
    gerar_pdf,
    intro,
    encerramento,
    linhas_cabecalho,
    teor_texto_curto,
)

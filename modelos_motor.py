# -*- coding: utf-8 -*-
"""Motor de fidelidade de modelos — Etapa 2a + 2b (SANDBOX).

API pública para o editor e para testes. Módulos novos com prefixo
`modelos_motor*` — não altera `modelos_editor*`, `rc_certidao*`,
`impressao_*`, `modelos_previa`, `atribuicoes_web`, `notas_web`, `ri_web`.

Plug-in do blueprint: ver `modelos_motor_web.py` e a linha sugerida em
`app.py` (ainda NÃO aplicada).

2b: termos `RC_TERMO_*` (`modelos_motor_termo`), autoria neutra no ODT
(`limpar_autoria_odt`), `html_para_texto_impressao` (F01) e helpers da
etiqueta de Notas (`modelos_motor_etiqueta`, patch proposto — não plugado).

2c: `conteudo` não salvo na prévia (termo = texto; molde = ODT base64),
placeholders `{{campo}}` (aceita `@campo`/`{campo}`), trechos bloqueados
(`marcar_bloqueados`), `arquivo_base64` + `mime`, F01 `corrigir_teor_f01`
(patch RI documentado, não aplicado) e hook da versão publicada do Editor
(`modelos_motor_versao`, flag `USAR_CONTEUDO_PUBLICADO_EDITOR = False`).
"""
from __future__ import annotations

from modelos_motor_adapters import (
    AUTOR_SISTEMA,
    MIME_HTML,
    MIME_ODT,
    MIME_PDF,
    autor_neutro,
    autoria_do_odt,
    html_de_odt,
    html_do_quadro,
    limpar_autoria_odt,
    odt_do_contexto,
    pdf_de_odt_bytes,
    resposta_previa,
    sanitizar_teor_para_papel,
)
from modelos_motor_campos import campos, trechos_bloqueados
from modelos_motor_contexto import (
    USAR_MOTOR_NA_PREVIA_RCPN,
    chave_termo,
    claros_do_contexto,
    contexto_de_assento,
    contexto_de_exemplo,
    corrigir_pessoas_naturais,
    corrigir_tres,
    data_por_extenso_acentuada,
    eh_template_termo,
    por_extenso_acentuado,
)
from modelos_motor_etiqueta import (
    corrigir_virgula_da_data,
    dados_da_etiqueta_corrigidos,
    texto_da_etiqueta_motor,
    titulo_da_etiqueta,
)
from modelos_motor_html import (
    corrigir_teor_f01,
    html_para_texto,
    html_para_texto_impressao,
    parece_html,
    strip_tags,
    tem_tag_escapada,
)
from modelos_motor_placeholders import (
    analisar_placeholders,
    conferir_bloqueados,
    marcar_bloqueados,
    normalizar_placeholders,
    para_formato_do_catalogo,
    placeholders_do_texto,
    remover_marcadores_bloqueados,
)
from modelos_motor_termo import (
    ESTILO_DATA_TERMO,
    ESTILOS_DATA,
    estilo_de_data,
    rascunho_do_termo,
    contexto_termo,
    contexto_termo_de_assento,
    data_termo,
    html_do_termo,
    normalizar_datas_no_texto,
    odt_do_termo,
    preencher_fecho,
    resposta_previa_termo,
    texto_do_termo,
)
from modelos_motor_versao import (
    conteudo_publicado_editor,
    corpo_do_termo,
    molde_da_certidao,
)

__all__ = [
    "AUTOR_SISTEMA",
    "ESTILO_DATA_TERMO",
    "ESTILOS_DATA",
    "MIME_HTML",
    "MIME_ODT",
    "MIME_PDF",
    "analisar_placeholders",
    "conferir_bloqueados",
    "conteudo_publicado_editor",
    "corpo_do_termo",
    "corrigir_teor_f01",
    "estilo_de_data",
    "html_de_odt",
    "marcar_bloqueados",
    "molde_da_certidao",
    "normalizar_placeholders",
    "para_formato_do_catalogo",
    "placeholders_do_texto",
    "rascunho_do_termo",
    "remover_marcadores_bloqueados",
    "tem_tag_escapada",
    "USAR_MOTOR_NA_PREVIA_RCPN",
    "autor_neutro",
    "autoria_do_odt",
    "campos",
    "chave_termo",
    "claros_do_contexto",
    "contexto_de_assento",
    "contexto_de_exemplo",
    "contexto_termo",
    "contexto_termo_de_assento",
    "corrigir_pessoas_naturais",
    "corrigir_tres",
    "corrigir_virgula_da_data",
    "dados_da_etiqueta_corrigidos",
    "data_por_extenso_acentuada",
    "data_termo",
    "eh_template_termo",
    "html_do_quadro",
    "html_do_termo",
    "html_para_texto",
    "html_para_texto_impressao",
    "limpar_autoria_odt",
    "normalizar_datas_no_texto",
    "odt_do_contexto",
    "odt_do_termo",
    "parece_html",
    "pdf_de_odt_bytes",
    "por_extenso_acentuado",
    "preencher_fecho",
    "resposta_previa",
    "resposta_previa_termo",
    "sanitizar_teor_para_papel",
    "strip_tags",
    "texto_da_etiqueta_motor",
    "texto_do_termo",
    "titulo_da_etiqueta",
    "trechos_bloqueados",
]

# -*- coding: utf-8 -*-
"""Etiqueta de Notas — helpers do motor (Etapa 2b). PATCH PROPOSTO, NÃO PLUGADO.

Dois defeitos da etiqueta térmica de Notas (reconhecimento / autenticação):

  1. **Título da aba/janela**: `notas_etiqueta.html` escreve sempre
     «Etiqueta — reconhecimento nº …», inclusive quando a rota é a da
     AUTENTICAÇÃO (`/notas/autenticacao/<id>/etiqueta`). O nome do arquivo
     ao «salvar como PDF» sai errado.
  2. **Data colada na vírgula**: o fecho montado por
     `notas_schema.texto_da_etiqueta` sai «CIDADE-UF,05/10/2026.» — sem
     espaço depois da vírgula.

O item 1 já foi corrigido no template pelo robô correções gerais (registro
05/10 15:30, olha o `voltar`). O item 2 exige mexer em `notas_web.py`
(proibido nesta etapa) — por isso aqui ficam só as funções e o patch
(`PATCH_PROPOSTO`, também em `SANDBOX\\tmp\\motor_fidelidade_2b_etiqueta.patch`),
aguardando o OK do oficial/Editor. `notas_schema.py` NÃO é alterado: o teste
`tests/test_etiqueta_reconhecimento.py` fixa o formato antigo (E-Ofício) e a
reimpressão de etiqueta IMPORTADA tem de sair igual à primeira via.

Nenhum dado de serventia aqui: cidade/UF chegam por parâmetro (`settings`).
"""
from __future__ import annotations

import re
from typing import Any

TITULOS = {
    "reconhecimento": "Etiqueta — reconhecimento nº {id}",
    "autenticacao": "Etiqueta — autenticação nº {id}",
}

# «CIDADE-UF,dd/mm/aaaa» → «CIDADE-UF, dd/mm/aaaa» (só esse desenho de fecho)
_VIRGULA_DATA = re.compile(
    r"(\b[A-ZÀ-Ý][A-ZÀ-Ý0-9 .'-]*-[A-Z]{2}),(?=\d{2}/\d{2}/\d{4}\b)")


def tipo_do_ato(ato: dict | Any) -> str:
    """'autenticacao' quando o registro é de `nt_autenticacoes` (tem `folhas`
    e não tem `codigo_seguranca` próprio); senão 'reconhecimento'."""
    d = dict(ato or {})
    if "folhas" in d and not d.get("codigo_seguranca") and "especie" not in d:
        return "autenticacao"
    return "reconhecimento"


def titulo_da_etiqueta(tipo: str, ato_id: Any) -> str:
    """Título correto da página da etiqueta. Só calcula."""
    t = str(tipo or "").strip().lower()
    t = "autenticacao" if t.startswith("autentic") else "reconhecimento"
    return TITULOS[t].format(id=ato_id if ato_id not in (None, "") else "")


def corrigir_virgula_da_data(texto: Any) -> str:
    """Espaço depois da vírgula no fecho «CIDADE-UF, dd/mm/aaaa». Idempotente."""
    return _VIRGULA_DATA.sub(r"\1, ", str(texto or ""))


def texto_da_etiqueta_motor(teor: str, cidade: str, uf: str, data_iso: str, *,
                            manter_importado: bool = True) -> str:
    """Envelope de `notas_schema.texto_da_etiqueta` com o espaço da vírgula.

    `manter_importado=True` (padrão): teor que JÁ traz o fecho («… DA
    VERDADE …», os importados do E-Ofício) volta idêntico — segunda via igual
    à primeira. Só o fecho montado pelo sistema ganha o espaço.
    """
    from notas_schema import texto_da_etiqueta
    saida = texto_da_etiqueta(teor, cidade, uf, data_iso)
    if manter_importado and "DA VERDADE" in str(teor or "").upper():
        return saida
    return corrigir_virgula_da_data(saida)


def dados_da_etiqueta_corrigidos(e: dict, *, tipo: str, ato_id: Any,
                                 importado: bool | None = None) -> dict:
    """Pós-processa o dict de `notas_web.dados_da_etiqueta` (sem editá-lo).

    `importado=None` infere pelo desenho do E-Ofício («EM TEST.____ DA
    VERDADE»): importado volta com o texto intacto; o resto ganha o espaço.
    Acrescenta `titulo` (autenticação × reconhecimento).
    """
    out = dict(e or {})
    texto = str(out.get("texto") or "")
    if importado is None:
        importado = bool(re.search(r"TEST\.\s*_{3,}", texto))
    if texto and not importado:
        out["texto"] = corrigir_virgula_da_data(texto)
    out["titulo"] = titulo_da_etiqueta(tipo, ato_id)
    return out


PATCH_PROPOSTO = r'''
(ver arquivo SANDBOX\tmp\motor_fidelidade_2b_etiqueta.patch — diff unificado
contra notas_web.py e templates/notas_etiqueta.html; NÃO aplicado)

notas_web.py
  + import modelos_motor_etiqueta as MOTOR_ETQ
  dados_da_etiqueta():
  -   "texto": texto_da_etiqueta(r["texto"], sv["ri_cidade"], sv["ri_uf"], r["data"]),
  +   "texto": MOTOR_ETQ.texto_da_etiqueta_motor(r["texto"], sv["ri_cidade"], sv["ri_uf"], r["data"]),
  notas_reconhecimento_etiqueta(): render_template(..., titulo_etiqueta=
      MOTOR_ETQ.titulo_da_etiqueta("reconhecimento", reconhecimento_id))
  notas_autenticacao_etiqueta(): render_template(..., titulo_etiqueta=
      MOTOR_ETQ.titulo_da_etiqueta("autenticacao", autenticacao_id))

(título: já resolvido no template pelo robô correções gerais — os
 kwargs `titulo_etiqueta` acima ficam opcionais, só se o Editor preferir)
'''

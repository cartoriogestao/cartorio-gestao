"""Mantém os metadados dos atos sem reenviar teor já presente na ficha."""
from __future__ import annotations

import re


class _AtoResumido(str):
    def __new__(cls, texto, original):
        item = super().__new__(cls, texto)
        item.original = original
        return item


def juntar_contexto(partes, limite):
    texto = "\n".join(partes)
    if len(texto) <= limite:
        return texto
    # O corte antigo pode remover a ficha referenciada: nesse caso conserve
    # os corpos como antes. Nunca apontar para um teor que ficou fora do pedido.
    return "\n".join(getattr(p, "original", p) for p in partes)[-limite:]


def _comparavel(texto):
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def ato_no_contexto(ato, ficha, normalizar):
    teor = normalizar(ato["teor"])
    cabecalho = f"{ato['tipo']}-{ato['numero']} ({ato['data_ato'] or '—'}): "
    corpo, base = _comparavel(teor), _comparavel(ficha)
    # Só igualdade literal (salvo espaços), sem aproximação que esconda divergências.
    # Textos mínimos/genéricos não são retirados por coincidência de uma palavra.
    if len(corpo) >= 80 and corpo in base:
        return _AtoResumido(cabecalho + "[Teor integral já transcrito em TEOR DA FICHA acima.]",
                            cabecalho + teor)
    return cabecalho + teor

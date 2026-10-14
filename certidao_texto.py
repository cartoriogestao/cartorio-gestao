"""Texto de certidão — todas as atribuições."""
from __future__ import annotations
import re

def sem_linha_de_assinatura_a_mao(texto: str | None) -> str:
    """Tira só os traços (8+ underscores); mantém nome/título de quem lavrou."""
    if not texto:
        return ""
    t = str(texto)
    t = re.sub(r"_{8,}", " ", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" +([,;.])", r"\1", t)
    t = re.sub(r" ,", ",", t)
    return t

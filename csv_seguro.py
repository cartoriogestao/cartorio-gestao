# -*- coding: utf-8 -*-
"""A PLANILHA QUE SAI DA CASA NÃO LEVA FÓRMULA — o CSV único (26/10/2026).

POR QUE EXISTE
    A revisão de segurança dos PRs abertos (26/10/2026, achado transversal 2)
    achou o mesmo padrão em quatro PRs e no `csv_response` da casa: o CSV saía
    com `csv.writer` cru, e campo que começa com `=`, `+`, `-` ou `@` o Excel
    e o LibreOffice leem como FÓRMULA. O texto vem de quem digitou no balcão,
    de remetente de expediente, de nome de parte — e um
    `=HIPERLINK("http://…";"clique")` num assunto de expediente vira, na
    planilha do oficial, um link para fora com cara de dado da casa (é a
    «injeção de CSV», ou «injeção de fórmula»).

O QUE ELE FAZ
    1. Todo campo vai ENTRE ASPAS (`csv.QUOTE_ALL`): o separador, a quebra de
       linha e a aspa dentro do texto deixam de partir a coluna.
    2. Campo de TEXTO que começa com `=`, `+`, `-`, `@`, tabulação ou retorno
       de carro ganha um apóstrofo na frente — a forma que as planilhas
       entendem como «isto é texto». Tabulação e retorno de carro não estão no
       relatório; estão na lista da OWASP, porque a planilha os pula e lê o
       que vem depois.
    3. NÚMERO NÃO GANHA APÓSTROFO. `-5` (um desvio de minutos, um saldo) é
       número, e número não roda fórmula: virar texto estragaria a soma da
       coluna. Vale para `int`, `float` e `Decimal`, e para o texto que é SÓ
       um número (`"-5"`, `"-3,50"`, `"+12.5"`). `bool` é tratado como texto.

COMO SE USA
    - `gerar(cabecalho, linhas)` devolve o texto do CSV;
    - `resposta(nome, cabecalho, linhas)` devolve o `Response` do Flask, com o
      BOM que o Excel pede para abrir os acentos certos;
    - `escritor(saida)` e `escritor_de_dicionario(saida, colunas)` são os
      substitutos de `csv.writer` e `csv.DictWriter` para quem já escreve
      linha a linha.

    `csv.writer` e `csv.DictWriter` crus fora daqui ficam vermelhos em
    `tests/test_csv_seguro.py` — é o varredor que impede o próximo CSV de
    nascer sem a neutralização.
"""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal
from typing import Any, Iterable, Sequence

#: Os começos que a planilha lê como fórmula (OWASP, «CSV Injection»).
INICIO_PERIGOSO = ("=", "+", "-", "@", "\t", "\r")

#: O texto que é só um número — sinal, dígitos, um separador decimal. Esse
#: não roda fórmula, e não ganha apóstrofo.
_SO_NUMERO = re.compile(r"[+-]?\d+(?:[.,]\d+)?")

#: O BOM que faz o Excel abrir o UTF-8 com os acentos certos — a forma de
#: todos os CSV da casa até aqui.
BOM = "﻿"


def neutralizar(valor: Any) -> str:
    """O campo pronto para o CSV, sem fórmula. SÓ CALCULA.

    `None` vira vazio; número fica número; texto que começa com um dos
    `INICIO_PERIGOSO` ganha o apóstrofo na frente.
    """
    if valor is None:
        return ""
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        return str(valor)
    texto = str(valor)
    if texto.startswith(INICIO_PERIGOSO) and not _SO_NUMERO.fullmatch(texto):
        return "'" + texto
    return texto


def _linha(campos: Iterable[Any]) -> list[str]:
    return [neutralizar(c) for c in campos]


class _Escritor:
    """O `csv.writer` com a neutralização em toda linha."""

    def __init__(self, saida, *, delimiter: str = ";", lineterminator: str = "\r\n"):
        self._w = csv.writer(saida, delimiter=delimiter, quoting=csv.QUOTE_ALL,
                             lineterminator=lineterminator)

    def writerow(self, campos: Iterable[Any]):
        return self._w.writerow(_linha(campos))

    def writerows(self, linhas: Iterable[Iterable[Any]]) -> None:
        for campos in linhas:
            self.writerow(campos)


class _EscritorDeDicionario:
    """O `csv.DictWriter` com a neutralização em todo campo."""

    def __init__(self, saida, colunas: Sequence[str], *, delimiter: str = ";",
                 lineterminator: str = "\r\n"):
        self._colunas = list(colunas)
        self._w = csv.writer(saida, delimiter=delimiter, quoting=csv.QUOTE_ALL,
                             lineterminator=lineterminator)

    def writeheader(self):
        return self._w.writerow(_linha(self._colunas))

    def writerow(self, linha: dict):
        sobra = set(linha) - set(self._colunas)
        if sobra:
            # A mesma recusa do `csv.DictWriter` (extrasaction='raise').
            raise ValueError(f"campos fora das colunas do CSV: {sorted(sobra)}")
        return self._w.writerow(_linha(linha.get(c, "") for c in self._colunas))

    def writerows(self, linhas: Iterable[dict]) -> None:
        for linha in linhas:
            self.writerow(linha)


def escritor(saida, *, delimiter: str = ";", lineterminator: str = "\r\n") -> _Escritor:
    """O substituto de `csv.writer(saida, delimiter=";")`."""
    return _Escritor(saida, delimiter=delimiter, lineterminator=lineterminator)


def escritor_de_dicionario(saida, colunas: Sequence[str], *, delimiter: str = ";",
                           lineterminator: str = "\r\n") -> _EscritorDeDicionario:
    """O substituto de `csv.DictWriter(saida, fieldnames=colunas, delimiter=";")`."""
    return _EscritorDeDicionario(saida, colunas, delimiter=delimiter,
                                 lineterminator=lineterminator)


def gerar(cabecalho: Sequence[Any] | None, linhas: Iterable[Iterable[Any]], *,
          delimiter: str = ";", lineterminator: str = "\r\n") -> str:
    """O texto do CSV, cabeçalho e linhas, tudo neutralizado. SÓ CALCULA."""
    saida = io.StringIO()
    w = escritor(saida, delimiter=delimiter, lineterminator=lineterminator)
    if cabecalho is not None:
        w.writerow(cabecalho)
    w.writerows(linhas)
    return saida.getvalue()


def resposta(nome_do_arquivo: str, cabecalho: Sequence[Any] | None,
             linhas: Iterable[Iterable[Any]], *, delimiter: str = ";",
             lineterminator: str = "\r\n"):
    """O `Response` do Flask com o CSV, o BOM e o nome do arquivo."""
    from flask import Response
    corpo = BOM + gerar(cabecalho, linhas, delimiter=delimiter,
                        lineterminator=lineterminator)
    return Response(corpo, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             f'attachment; filename="{nome_do_arquivo}"'})

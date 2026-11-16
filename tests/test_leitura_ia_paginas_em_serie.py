"""A imagem da página se gera FORA das threads da rede, uma vez por página.

16/11/2026, leitura nº 27 da produção (óbito): a página do PDF era renderizada
dentro das 4 threads da leitura, o PDFium não aceita duas threads ao mesmo
tempo, e a leitura caiu com «Um dos arquivos não pôde ser aberto (OSError)».
"""
from __future__ import annotations

import base64
import io
import json
import threading
from pathlib import Path

from PIL import Image

import leitura_ia as LIA


def _jpeg_de(n: int) -> str:
    saida = io.BytesIO()
    Image.new("L", (40, 60), color=n * 30).save(saida, format="JPEG")
    return base64.b64encode(saida.getvalue()).decode("ascii")


def test_as_paginas_se_renderizam_uma_vez_e_na_thread_de_quem_chama(tmp_path: Path):
    principal = threading.current_thread()
    chamadas: list[tuple[int, threading.Thread]] = []
    jpegs = {n: _jpeg_de(n) for n in range(1, 7)}

    def pagina(n: int) -> dict:
        def imagem():
            chamadas.append((n, threading.current_thread()))
            return jpegs[n]
        return {"arquivo": "DOCS.pdf", "n": n, "imagem": imagem}

    paginas = [pagina(n) for n in range(1, 7)]
    enviadas: list[str] = []

    def conversar(_pasta, **kw):
        imagens = [i["base64"] for i in kw["conversa"][0]["imagens"]]
        if kw["maximo_de_saida"] == 1500:   # a triagem
            itens = [{"n": i, "tipo": "OUTRO"} for i in range(1, len(imagens) + 1)]
            return {"texto": json.dumps({"paginas": itens}), "parou": "end_turn"}
        enviadas.extend(imagens)
        return {"texto": '{"tipo_do_documento": "x"}', "parou": "end_turn"}

    lido = LIA.ler_paginas(conversar, tmp_path, dict(LIA.MODELOS_PADRAO), paginas,
                           tipos={"OUTRO": LIA.TIPO_OUTRO},
                           instrucao_triagem="triagem", instrucao_leitura="{nome} {campos}")

    assert sorted(n for n, _ in chamadas) == [1, 2, 3, 4, 5, 6]
    assert all(t is principal for _, t in chamadas)
    assert sorted(enviadas) == sorted(jpegs.values())
    assert len(lido["documentos"]) == 6

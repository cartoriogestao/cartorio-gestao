"""LF06B, grupo B — as frases do RI que saíram de `ri_digitalizacao`,
`atrib_certidao` (Livro 3) e `ri_onus_ia`, chamadas ANTES e DEPOIS.

Contexto de teste, sem dado real de pessoa (LGPD): matrícula e registro de
exemplo, sha256 de exemplo, imagem branca gerada aqui. Cada ramo da regra que
escolhe a frase tem a sua chamada (1 × N páginas, com × sem atos, positiva ×
negativa). O `.odt` é zip: o que se grava é o corpo do `content.xml` de dentro.
"""
from __future__ import annotations

SHA = "0123456789abcdef" * 4


def _content_xml_da_digitalizacao(paginas: int, **kw) -> str:
    """O `content.xml` do `.odt` reprográfico, de uma imagem de exemplo."""
    import io
    import tempfile
    import zipfile
    from pathlib import Path

    from PIL import Image

    import ri_digitalizacao as RDIGI

    with tempfile.TemporaryDirectory() as pasta:
        arq = Path(pasta) / ("ficha.tif" if paginas > 1 else "ficha.png")
        folhas = [Image.new("RGB", (124, 175), "white") for _ in range(paginas)]
        if paginas > 1:
            folhas[0].save(arq, format="TIFF", save_all=True,
                           append_images=folhas[1:])
        else:
            folhas[0].save(arq, format="PNG")
        odt = RDIGI.odt_da_digitalizacao(arq, selo_texto="SELOEXEMPLO123",
                                         nome="certidao-exemplo", **kw)
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        xml = z.read("content.xml").decode("utf-8")
    # SÓ O CORPO: os estilos automáticos levam `ri_odt.ESTILOS_EXTRA`, um dict
    # do processo que outros módulos (notas, RCPN) enchem — no pytest, o
    # `content.xml` inteiro dependeria de qual teste rodou antes.
    return xml[xml.index("<office:body>"):xml.index("</office:body>")]


def chamadas() -> dict:
    import atrib_certidao as AC
    import ri_digitalizacao as RDIGI
    import ri_onus_ia as RONIA

    f: dict = {}

    # -- ri_digitalizacao: o corpo congelado, o fecho do papel, a capa
    for n in (1, 3):
        f[f"ri_digitalizacao.corpo_resumo_digitalizacao(paginas={n})"] = (
            lambda n=n: RDIGI.corpo_resumo_digitalizacao(
                matricula="1.234", paginas=n, sha256=SHA))
        f[f"ri_digitalizacao._fecho_html_para_papel(corpo, paginas={n})"] = (
            lambda n=n: RDIGI._fecho_html_para_papel(
                RDIGI.corpo_resumo_digitalizacao(
                    matricula="1.234", paginas=n, sha256=SHA)))
    f["ri_digitalizacao.TITULO_CERTIDAO_REPROGRAFICA"] = (
        lambda: RDIGI.TITULO_CERTIDAO_REPROGRAFICA)
    for n in (1, 2):
        f[f"ri_digitalizacao.odt_da_digitalizacao(paginas={n})[content.xml]"] = (
            lambda n=n: _content_xml_da_digitalizacao(n))
    f["ri_digitalizacao.odt_da_digitalizacao(corpo, titulo)[content.xml]"] = (
        lambda: _content_xml_da_digitalizacao(
            1, titulo="CERTIDÃO DE EXEMPLO & CIA",
            rotulo_selo="SELO DA CERTIDÃO",
            assinatura_odf='<text:p text:style-name="P-centro">FULANO DE EXEMPLO</text:p>',
            corpo_html=RDIGI.corpo_resumo_digitalizacao(
                matricula="1.234", paginas=1, sha256=SHA)))

    # -- atrib_certidao (Livro 3): o teor por reprodução e o claro {atos}
    for n in (1, 4):
        f[f"atrib_certidao.corpo_por_reproducao(paginas={n})"] = (
            lambda n=n: AC.corpo_por_reproducao(
                registro_numero="1.243", paginas=n, sha256=SHA))
    f["atrib_certidao.corpo_por_reproducao(numero int, paginas str)"] = (
        lambda: AC.corpo_por_reproducao(
            registro_numero=77, paginas="2", sha256=""))
    atos = [
        {"id": 1, "tipo": "R", "numero": 1, "teor": "REGISTRO DE EXEMPLO.",
         "data_ato": "2026-09-01"},
        {"id": 2, "tipo": "AV", "numero": 1,
         "teor": "AVERBAÇÃO DE EXEMPLO em favor de FULANO DE EXEMPLO.",
         "data_ato": "2026-09-22"},
        {"id": 3, "tipo": "AV", "numero": 2, "teor": "",
         "motivo_cancelamento": "Cancelado a pedido de FULANO DE EXEMPLO.",
         "data_ato": ""},
        {"id": 4, "tipo": "AV", "numero": 3, "teor": "", "data_ato": "2026-10-01"},
    ]
    f["atrib_certidao._bloco_atos_certidao_livro3(sem atos)"] = (
        lambda: AC._bloco_atos_certidao_livro3([], None))
    f["atrib_certidao._bloco_atos_certidao_livro3(so o registro)"] = (
        lambda: AC._bloco_atos_certidao_livro3(atos[:1], None))
    f["atrib_certidao._bloco_atos_certidao_livro3(todos)"] = (
        lambda: AC._bloco_atos_certidao_livro3(atos, None))
    f["atrib_certidao._bloco_atos_certidao_livro3(filtro AV-2)"] = (
        lambda: AC._bloco_atos_certidao_livro3(atos, {3}))
    f["atrib_certidao._bloco_atos_certidao_livro3(filtro sem acerto)"] = (
        lambda: AC._bloco_atos_certidao_livro3(atos, {99}))
    f["atrib_certidao.cabeca_do_ato(AV-1)"] = lambda: AC.cabeca_do_ato(atos[1])

    # -- ri_onus_ia: o título decidido pelos dois resultados
    for o in ("POSITIVA", "NEGATIVA", None):
        for a in ("POSITIVA", "NEGATIVA", "INDEFINIDO"):
            f[f"ri_onus_ia.titulo({o}, {a})"] = (
                lambda o=o, a=a: RONIA.titulo(o, a))
    return f

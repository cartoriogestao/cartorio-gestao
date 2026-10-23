"""LX12 — os tetos do que entra por arquivo (LS02 M1–M5, 19/10/2026).

Um arquivo pequeno que vira coisa enorme dentro do servidor derruba o único
processo do balcão: o `.odt` que se abre em gigabytes, o `text:c` de dois
bilhões, a página de PDF gigante, o PDF de mil páginas que vira mil chamadas
pagas à IA, o POST anônimo de 200 MB. Cada teste aqui falharia no código de
antes do LX12. Os tetos se baixam pelo ambiente (`CG_TETO_<NOME>`) — que é o
ajuste da casa e, de quebra, deixa o teste usar arquivo pequeno.

Os dados são os fictícios da casa: nenhum nome ou documento de gente real.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import tetos_de_entrada as TETO  # noqa: E402

_ODT_CONTEUDO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<office:document-content '
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
    '<office:body><office:text>{corpo}</office:text></office:body>'
    '</office:document-content>')


def _zip(membros: dict[str, bytes | str]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in membros.items():
            z.writestr(nome, conteudo)
    return saida.getvalue()


def _odt(corpo: str, *, enchimento: int = 0) -> bytes:
    """Um `.odt` mínimo; o enchimento (espaços, que comprimem a quase nada)
    é o que faz um arquivo pequeno se abrir grande."""
    xml = _ODT_CONTEUDO.format(corpo=corpo) + " " * enchimento
    return _zip({"mimetype": "application/vnd.oasis.opendocument.text",
                 "content.xml": xml})


def _pdf(paginas: int, *, largura: float = 595, altura: float = 842) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    for _ in range(paginas):
        doc.new_page(width=largura, height=altura)
    try:
        return doc.tobytes()
    finally:
        doc.close()


# ------------------------------------------------------ M1: o teor das notas


def test_o_odt_que_se_abre_grande_demais_e_recusado_com_frase_de_balcao(monkeypatch):
    """Zip-bomba no `content.xml`: era lido inteiro, sem teto."""
    import notas_teor_arquivo as NTA
    monkeypatch.setenv("CG_TETO_ZIP_BYTES", "20000")
    arquivo = _odt("<text:p>OUTORGANTE</text:p>", enchimento=200_000)
    assert len(arquivo) < 5_000          # pequeno de fora, grande por dentro
    with pytest.raises(NTA.TeorArquivoError, match="teto"):
        NTA.ler_documento(arquivo, "teor.odt")


def test_o_text_c_gigante_nao_aloca_a_memoria_que_pede():
    """`<text:s text:c="2000000000"/>` alocava 2 GB num elemento de 30 bytes.
    Os espaços se juntam depois, e por isso o texto que volta não mostra o
    estrago: o que se mede é o pico de memória (aqui, com 200 milhões, que o
    código antigo pagava em 200 MB)."""
    import tracemalloc
    import notas_teor_arquivo as NTA
    arquivo = _odt('<text:p>A<text:s text:c="200000000"/>B</text:p>')
    tracemalloc.start()
    try:
        paragrafos = NTA.ler_documento(arquivo, "teor.odt")
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(paragrafos) == 1
    assert pico < 20 * 1024 * 1024


def test_o_text_c_que_nao_e_numero_vale_um_espaco_em_vez_de_erro_500():
    import notas_teor_arquivo as NTA
    paragrafos = NTA.ler_documento(
        _odt('<text:p>A<text:s text:c="abc"/>B</text:p>'), "teor.odt")
    assert "A" in paragrafos[0] and "B" in paragrafos[0]


def test_o_teor_de_verdade_continua_entrando():
    import notas_teor_arquivo as NTA
    paragrafos = NTA.ler_documento(
        _odt('<text:p>MARIO<text:s text:c="3"/>EXEMPLO</text:p>'), "teor.odt")
    assert "MARIO" in paragrafos[0] and "EXEMPLO" in paragrafos[0]


# --------------------------------------- M2: moldes, editor, revisão, acervo


def test_o_molde_que_se_abre_grande_demais_e_recusado_antes_de_gravar(monkeypatch):
    import modelos_moldes as MOLDES
    monkeypatch.setenv("CG_TETO_ZIP_BYTES", "20000")
    erro = MOLDES.conferir(MOLDES.MOLDES[0]["chave"],
                           _odt("<text:p>@MATRICULA</text:p>", enchimento=200_000))
    assert erro and "teto" in erro


def test_o_editor_de_modelos_nao_le_o_content_xml_sem_teto(monkeypatch):
    import modelos_editor as ED
    monkeypatch.setenv("CG_TETO_ZIP_BYTES", "20000")
    with pytest.raises(TETO.TetoExcedido):
        ED._content_xml(_odt("<text:p>x</text:p>", enchimento=200_000))


def test_o_anexo_docx_que_se_abre_grande_demais_fica_ilegivel_e_nao_derruba(
        monkeypatch, tmp_path):
    import revisao_anexos as RA
    monkeypatch.setenv("CG_TETO_ZIP_BYTES", "20000")
    caminho = tmp_path / "minuta.docx"
    caminho.write_bytes(_zip({"word/document.xml": "<w:p/>" + " " * 200_000}))
    with pytest.raises(RA.AnexoIlegivel, match="teto"):
        RA.texto_de_editor(caminho, ".docx")


def test_o_zip_do_acervo_grande_demais_nao_e_extraido(monkeypatch, tmp_path):
    """O `extractall` enchia o disco da pasta de dados, onde mora o banco."""
    import acervo_carga as AC
    monkeypatch.setenv("CG_TETO_ACERVO_BYTES", "20000")
    pacote = tmp_path / "export.zip"
    pacote.write_bytes(_zip({"EXPORT/matriculas.jsonl": "{}\n" * 100_000}))
    trabalho = tmp_path / "trabalho"
    with pytest.raises(AC.CargaError, match="teto"):
        AC.instalar_acervo_de_zip(pacote, tmp_path / "acervo.sqlite3", trabalho)
    assert not list((trabalho).rglob("*.jsonl"))


def test_a_extracao_com_teto_nao_sai_da_pasta(tmp_path):
    """A régua do caminho é a do `zipfile`: `..` e raiz não saem do destino."""
    pacote = zipfile.ZipFile(io.BytesIO(_zip({"../../fora.txt": "x",
                                              "/raiz.txt": "y"})))
    TETO.extrair(pacote, tmp_path / "dentro")
    assert sorted(p.name for p in (tmp_path / "dentro").rglob("*")) == [
        "fora.txt", "raiz.txt"]
    assert not (tmp_path / "fora.txt").exists()


def test_a_imagem_do_protesto_acima_do_limite_nem_se_le(monkeypatch):
    """O teto de 25 MB por imagem recusava DEPOIS de ler o membro inteiro."""
    import protesto_imagens as PI
    monkeypatch.setattr(PI, "LIMITE_DE_UMA_IMAGEM", 1_000)
    itens = PI.ler_pacote(_zip({"1LV/00012345_00000000191_1.jpg": b"\xff" * 5_000,
                                "1LV/00012345_00000000191_2.jpg": b"\xff" * 500}))
    grande, pequena = sorted(itens, key=lambda i: -i["tamanho"])
    assert grande["tamanho"] == 5_000 and grande["conteudo"] == b""
    assert pequena["conteudo"] == b"\xff" * 500


def test_o_pacote_do_protesto_com_itens_demais_e_recusado(monkeypatch):
    import protesto_imagens as PI
    monkeypatch.setenv("CG_TETO_ZIP_ENTRADAS", "2")
    with pytest.raises(PI.ImagemError, match="teto"):
        PI.ler_pacote(_zip({f"1LV/0001234{i}_00000000191_1.jpg": b"\xff"
                            for i in range(3)}))


# ---------------------------------------------- M3: páginas e área de imagem


def test_a_miniatura_da_pagina_altissima_cabe_no_teto_de_pixels(monkeypatch, tmp_path):
    """A escala mínima de 0,25 não segurava a altura: página estreita e alta
    virava bitmap de gigabytes só para a capa da ficha."""
    from PIL import Image
    import ri_digitalizacao as RD
    monkeypatch.setenv("CG_TETO_PIXELS_POR_PAGINA", "1000000")
    pdf = tmp_path / "ficha.pdf"
    pdf.write_bytes(_pdf(1, largura=200, altura=14_400))
    with Image.open(io.BytesIO(RD.miniatura_png(pdf))) as im:
        assert im.width * im.height <= 1_000_000 * 1.02


def test_o_tiff_com_quadros_demais_e_recusado(monkeypatch, tmp_path):
    from PIL import Image
    import ri_digitalizacao as RD
    monkeypatch.setenv("CG_TETO_PAGINAS", "2")
    tiff = tmp_path / "ficha.tif"
    quadros = [Image.new("L", (40, 40), 255) for _ in range(3)]
    quadros[0].save(tiff, save_all=True, append_images=quadros[1:])
    with pytest.raises(ValueError, match="teto"):
        RD.paginas_png(tiff)


def test_o_pdf_com_paginas_demais_nao_vira_imagem(monkeypatch, tmp_path):
    import ri_digitalizacao as RD
    monkeypatch.setenv("CG_TETO_PAGINAS", "2")
    pdf = tmp_path / "ficha.pdf"
    pdf.write_bytes(_pdf(3))
    with pytest.raises(ValueError, match="teto"):
        RD.paginas_png(pdf)


def test_a_imagem_de_area_gigante_nao_vira_miniatura(monkeypatch, tmp_path):
    from PIL import Image
    import ri_digitalizacao as RD
    monkeypatch.setenv("CG_TETO_PIXELS_POR_PAGINA", "1000000")
    png = tmp_path / "ficha.png"
    Image.new("L", (2_000, 2_000), 255).save(png)
    with pytest.raises(ValueError, match="teto"):
        RD.miniatura_png(png)


def test_a_pagina_grande_demais_nao_vira_tiff_para_o_onr(monkeypatch, tmp_path):
    """A 200 dpi, página gigante virava bitmap de gigabytes; aqui recusa (a
    resolução da imagem do ONR é combinada, e não se baixa calada)."""
    import pymupdf
    import gestor_cargas_ri as G
    monkeypatch.setenv("CG_TETO_PIXELS_POR_PAGINA", "1000000")
    doc = pymupdf.open(stream=_pdf(1), filetype="pdf")
    try:
        with pytest.raises(ValueError, match="grande demais"):
            G.pagina_em_tiff(doc[0], tmp_path / "00000001.0001")
    finally:
        doc.close()
    assert not list(tmp_path.iterdir())


def test_o_pdf_da_matricula_com_paginas_demais_nao_apaga_as_imagens_velhas(
        monkeypatch, tmp_path):
    import gestor_cargas_ri as G
    monkeypatch.setenv("CG_TETO_PAGINAS", "2")
    pdf = tmp_path / "m.pdf"
    pdf.write_bytes(_pdf(3))
    pasta = tmp_path / "csl2" / "00000000"
    pasta.mkdir(parents=True)
    velha = pasta / "00000007.0001"
    velha.write_bytes(b"II*\x00")
    with pytest.raises(ValueError, match="teto"):
        G._converter_uma(pdf, tmp_path / "csl2", 7)
    assert velha.exists()


def test_o_qr_das_intimacoes_se_procura_na_resolucao_que_cabe(monkeypatch):
    """O limite de páginas já existia; a área de cada uma, não."""
    import protesto_intimacoes_lote as LOTE
    monkeypatch.setenv("CG_TETO_PIXELS_POR_PAGINA", "1000000")
    areas = []

    class _Retangulo:
        width, height = 595.0, 842.0

    class _Pix:
        def __init__(self, dpi):
            self.width = int(595 * dpi / 72)
            self.height = int(842 * dpi / 72)
            self.samples = bytes(self.width * self.height)

    class _Pagina:
        rect = _Retangulo()

        def get_pixmap(self, *, dpi, colorspace):
            pix = _Pix(dpi)
            areas.append(pix.width * pix.height)
            return pix

    assert LOTE._qrs_da_pagina(_Pagina()) == []
    assert areas and max(areas) <= 1_000_000


# ---------------------------------------- M4: a leitura de documentos pela IA


def test_a_leitura_por_ia_acima_do_teto_de_paginas_recusa_sem_chamar_a_ia(
        monkeypatch, tmp_path):
    """Cada página é uma chamada paga; a rota é de qualquer login."""
    import rc_leitura_documentos as LEIT
    monkeypatch.setenv("CG_TETO_IA_PAGINAS", "2")
    pdf = tmp_path / "processo.pdf"
    pdf.write_bytes(_pdf(3))
    chamadas = []

    def conversar(*args, **kwargs):
        chamadas.append(kwargs)
        return {"texto": "{}"}

    with pytest.raises(LEIT.LeituraError, match="paga"):
        LEIT.ler(conversar, tmp_path, {"triagem": "m", "manuscrito": "m",
                                       "impresso": "m"},
                 [{"caminho": str(pdf), "nome": "processo.pdf"}])
    assert chamadas == []


def test_a_leitura_dentro_do_teto_segue_para_a_ia(monkeypatch, tmp_path):
    import rc_leitura_documentos as LEIT
    monkeypatch.setenv("CG_TETO_IA_PAGINAS", "2")
    pdf = tmp_path / "dnv.pdf"
    pdf.write_bytes(_pdf(2))
    assert len(LEIT.paginas_dos_arquivos([{"caminho": str(pdf), "nome": "dnv.pdf"}])) == 2


# ------------------------------------------------ M5: o webhook sem login


def _mensagem(texto: str, meta_id: str) -> dict:
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"profile": {"name": "Pedro Exemplo dos Santos"},
                      "wa_id": "5500000000001"}],
        "messages": [{"from": "5500000000001", "id": meta_id,
                      "type": "text", "text": {"body": texto}}]}}]}]}


def _quantas(db, meta_id: str) -> int:
    from bd_nativo import banco
    with db.connect() as con:
        return banco(con).valor(
            "SELECT count(*) AS n FROM wa_mensagem WHERE meta_id=%s", (meta_id,))


@pytest.fixture()
def casa(cg_casa):
    """Com um usuário: sem nenhum, toda rota vai para o `/setup`.

    E com o MODO DE TESTE do webhook ligado: desde o LX11 (M6 do LS01) o
    `X-Wa-Test: 1` sem ele dá 403, e o POST «válido em tudo o mais» destes
    testes deixaria de ser válido — o 413 passaria a provar nada e o corpo
    normal não entraria. Ligar é o que o ADMIN faz na configuração.
    """
    import wa_balcao as WA
    import wa_schema as SCH
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    with cg_casa["db"].transaction() as con:
        WA.gravar_config(con, SCH.CHAVE_MODO_TESTE, "1")
    return cg_casa


def test_o_corpo_grande_no_webhook_sem_login_e_recusado_antes_de_ler(casa):
    """O teto geral é de 200 MB; a rota não tem login. Até o POST de teste da
    própria máquina, válido em tudo o mais, para no teto de 2 MB."""
    corpo = json.dumps(_mensagem("oi", "wamid.lx12-a")) + " " * (3 * 1024 * 1024)
    r = casa["app"].test_client().post(
        "/whatsapp/webhook", data=corpo, content_type="application/json",
        headers={"X-Wa-Test": "1"}, environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 413
    assert _quantas(casa["db"], "wamid.lx12-a") == 0


def test_o_corpo_normal_no_webhook_continua_entrando(casa):
    r = casa["app"].test_client().post(
        "/whatsapp/webhook", data=json.dumps(_mensagem("oi", "wamid.lx12-b")),
        content_type="application/json", headers={"X-Wa-Test": "1"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert _quantas(casa["db"], "wamid.lx12-b") == 1


# ------------------------------------------------------------ o módulo


def test_o_teto_do_ambiente_que_nao_e_inteiro_positivo_fica_no_padrao(monkeypatch):
    """Teto zerado por engano recusaria tudo."""
    for ruim in ("0", "-5", "abc", ""):
        monkeypatch.setenv("CG_TETO_PAGINAS", ruim)
        assert TETO.valor("paginas") == TETO.TETOS["paginas"]
    monkeypatch.setenv("CG_TETO_PAGINAS", "5000")
    assert TETO.valor("paginas") == 5000


def test_a_pagina_de_tamanho_normal_nao_perde_resolucao():
    assert TETO.escala_que_cabe(595, 842, 300 / 72) == 300 / 72

"""Regressões dos consertos preservados da instalação ao preparar a 3.7.19."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time

import pytest
from PIL import Image

import impressao_pdf as IMP
import revisao_previa as REV
import rg_teor_rtdpj as TEOR
import rg_certidao_pdf as CERT
import trava_pdfium as PDF
import wa_transcricao_local as AUDIO


def test_contagem_e_renderizacao_de_pdf_nao_entram_juntas_no_pdfium(monkeypatch):
    """Impressão e teor concorrem no servidor; cada módulo deve esperar o outro."""
    import pypdfium2
    active = 0
    maximum = 0
    guard = threading.Lock()
    start = threading.Barrier(2)

    class Bitmap:
        def to_pil(self):
            return Image.new('RGB', (4, 4), 'black')

        def close(self):
            pass

    class Page:
        def render(self, **kwargs):
            return Bitmap()

    class Document:
        def __init__(self, source):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(active, maximum)
            time.sleep(0.03)

        def __len__(self):
            return 1

        def __getitem__(self, index):
            return Page()

        def close(self):
            nonlocal active
            with guard:
                active -= 1

    monkeypatch.setattr(pypdfium2, 'PdfDocument', Document)

    def count():
        start.wait(timeout=5)
        return IMP.contar_paginas(b'pdf de teste')

    def render():
        start.wait(timeout=5)
        return TEOR._paginas_de_pdf(Path('ficticio.pdf'))

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(count), pool.submit(render)
        assert a.result(timeout=5) == 1
        assert b.result(timeout=5)[0].size == (4, 4)
    assert maximum == 1 and active == 0


def test_imagem_copiada_sobrevive_ao_fechamento_do_bitmap():
    original = Image.new('RGB', (3, 3), 'black')

    class Bitmap:
        closed = False

        def to_pil(self):
            return original

        def close(self):
            self.closed = True
            original.close()

    bitmap = Bitmap()

    class Page:
        def render(self, **kwargs):
            return bitmap

    with PDF.TRAVA:
        image = PDF.imagem_pil(Page(), scale=2)
    assert bitmap.closed and image.getpixel((1, 1)) == (0, 0, 0)


def test_imagem_na_capa_e_na_interna_tem_mesma_largura_no_papel():
    import numpy as np
    texts = CERT.textos_prontos(numero=148, lavrante_nome='MARIA EXEMPLO',
                               lavrante_funcao='Oficial', denominacao='EXEMPLO',
                               natureza='Ata', paginas=1, serie='PJ_A')
    source = Image.new('RGB', (2200, 1000), (50, 50, 50))
    cover, pasted = CERT.montar_capa(texts, primeira_folha=source)
    internal = CERT.montar_folha_interna(source, textos=texts, pagina=1, total_paginas=1)
    assert pasted and internal.width == cover.width * 2

    def width_on_paper(image):
        _, columns = np.where(np.all(np.asarray(image) == (50, 50, 50), axis=2))
        return (columns.max() - columns.min() + 1) / image.width

    assert width_on_paper(cover) == pytest.approx(width_on_paper(internal), rel=0.02)


def test_revisao_do_rcpn_separa_formulario_da_instrucao_e_do_teor():
    dossier = ('REGISTRO CIVIL A LAVRAR\nFORMULÁRIO:\nnome: MARIA EXEMPLO\n'
               '\nINSTRUÇÃO DA ESCREVENTE:\nconferir a grafia\n'
               '\nTEOR QUE SERIA GERADO\noutra seção')
    assert REV._texto_revisado(dossier) == ('RCPN', 'nome: MARIA EXEMPLO')
    assert REV._texto_revisado('REGISTRO CIVIL A LAVRAR\nFORMULÁRIO:\n(vazio)') == ('RCPN', '')


def test_audio_configurado_na_reserva_usa_o_servico_e_registra_sem_custo(monkeypatch, tmp_path):
    monkeypatch.setenv('CG_TRANSCRICAO_URL', 'http://reserva.exemplo:8767')
    monkeypatch.setenv('CG_TRANSCRICAO_TOKEN', 'segredo-ficticio-de-teste')
    calls = []
    usage = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"text":"bom dia", "duration":2.5}'

    def open_url(request, timeout):
        calls.append((request.full_url, request.data, request.get_header('Authorization')))
        return Response()

    monkeypatch.setattr(AUDIO.urllib.request, 'urlopen', open_url)
    monkeypatch.setattr(AUDIO.USO, 'registrar', lambda *a, **k: usage.append(k))
    monkeypatch.setattr(AUDIO, '_transcrever_no_trabalhador',
                        lambda *a, **k: pytest.fail('o modelo local não deve ser chamado'))
    result = AUDIO.transcrever(tmp_path, b'audio de teste', 'audio/ogg')
    assert result['texto'] == 'bom dia' and result['segundos'] == 2.5
    assert calls == [('http://reserva.exemplo:8767/transcrever', b'audio de teste',
                      'Bearer segredo-ficticio-de-teste')]
    assert usage and usage[0]['provedor'] == AUDIO.PROVEDOR

"""PDF anexado com mais de 22 MB sobe comprimido à IA (minutas e qualificação).

Tudo com PDFs sintéticos em tmp_path, sem rede e sem banco. O limite de 22 MB
é trocado por um pequeno para os PDFs de teste ficarem leves.
"""
import base64
import hashlib
import io
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

import minuta_ia as MI
import ri_qualificacao_ia as QIA

pymupdf = MI._pymupdf()
Image = pytest.importorskip("PIL.Image")

MB = 1024 * 1024


def _jpeg_de_ruido(largura, altura, modo="L", qualidade=95):
    img = Image.frombytes(modo, (largura, altura),
                          os.urandom(largura * altura * len(modo)))
    saida = io.BytesIO()
    img.save(saida, "JPEG", quality=qualidade)
    return saida.getvalue()


def _pdf(tmp_path, nome, paginas=3, texto=None, modo="L"):
    """PDF de página pequena (300 x 420 pt) com uma imagem de 'digitalização' de
    200 dpi; com
    `texto`, a página leva também texto digital."""
    doc = pymupdf.open()
    for i in range(paginas):
        p = doc.new_page(width=300, height=420)
        p.insert_image(p.rect, stream=_jpeg_de_ruido(834, 1167, modo))
        if texto:
            p.insert_text((30, 40 + 12 * i), f"{texto} - pagina {i + 1}", fontsize=11)
    caminho = tmp_path / nome
    doc.save(caminho)
    doc.close()
    return caminho


@pytest.fixture(autouse=True)
def limite_pequeno(monkeypatch):
    monkeypatch.setattr(MI, "LIMITE_PARA_COMPRIMIR", 300 * 1024)
    monkeypatch.setattr(MI, "_COMPRIMIDOS", {})


def _sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def test_pdf_ate_o_limite_sobe_intacto(tmp_path, monkeypatch):
    caminho = _pdf(tmp_path, "pequeno.pdf", paginas=1)
    monkeypatch.setattr(MI, "LIMITE_PARA_COMPRIMIR", caminho.stat().st_size)
    dados, como = MI.pdf_para_envio(caminho)
    assert como is None and dados == caminho.read_bytes()


def test_digitalizado_grande_sobe_comprimido_e_o_original_nao_muda(tmp_path):
    caminho = _pdf(tmp_path, "digitalizado.pdf")
    antes = _sha(caminho)
    dados, como = MI.pdf_para_envio(caminho)
    assert _sha(caminho) == antes
    assert como["dpi"] in (150, 130) and como["antes"] == caminho.stat().st_size
    assert len(dados) == como["depois"] < caminho.stat().st_size
    copia = pymupdf.open(stream=dados, filetype="pdf")
    assert len(copia) == 3
    assert copia[0].rect == pymupdf.Rect(0, 0, 300, 420)
    assert list(tmp_path.iterdir()) == [caminho]      # nada se grava em disco


def test_se_150_dpi_ainda_passa_tenta_130(tmp_path, monkeypatch):
    caminho = _pdf(tmp_path, "grande.pdf", paginas=1)
    tentados = []

    def falso(dados, dpi, qualidade):
        tentados.append(dpi)
        return b"%PDF" + b"0" * (MI.LIMITE_PARA_COMPRIMIR + 10 if dpi == 150 else 100)
    monkeypatch.setattr(MI, "_comprimir_pdf", falso)
    dados, como = MI.pdf_para_envio(caminho)
    assert tentados == [150, 130] and como["dpi"] == 130 and len(dados) == 104


def test_basta_150_dpi_nao_tenta_130(tmp_path, monkeypatch):
    caminho = _pdf(tmp_path, "grande.pdf", paginas=1)
    tentados = []
    monkeypatch.setattr(MI, "_comprimir_pdf",
                        lambda d, dpi, q: tentados.append(dpi) or b"%PDF-curto")
    MI.pdf_para_envio(caminho)
    assert tentados == [150]


def test_pdf_digital_mantem_o_texto_e_reduz_so_as_imagens(tmp_path):
    caminho = _pdf(tmp_path, "digital.pdf", texto="Escritura de compra e venda do imovel")
    original = pymupdf.open(caminho)
    dados, como = MI.pdf_para_envio(caminho)
    assert como and len(dados) < caminho.stat().st_size
    copia = pymupdf.open(stream=dados, filetype="pdf")
    for a, b in zip(original, copia):
        assert b.get_text("text") == a.get_text("text")
        assert b.get_fonts()                          # texto digital, não imagem
        larguras = [img[2] for img in b.get_images(full=True)]
        assert larguras and max(larguras) < 834        # a imagem foi reduzida


def test_falha_na_compressao_sobe_o_original(tmp_path, monkeypatch):
    caminho = _pdf(tmp_path, "falha.pdf", paginas=1)

    def quebra(*a):
        raise RuntimeError("pymupdf quebrou")
    monkeypatch.setattr(MI, "_comprimir_pdf", quebra)
    dados, como = MI.pdf_para_envio(caminho)
    assert como is None and dados == caminho.read_bytes()
    lido = MI._ler_arquivo(caminho, caminho.name)
    assert base64.b64decode(lido["documentos"][0]["base64"]) == caminho.read_bytes()
    assert "comprimido" not in lido


def test_copia_que_nao_fica_menor_nao_vale(tmp_path, monkeypatch):
    caminho = _pdf(tmp_path, "sem_ganho.pdf", paginas=1)
    monkeypatch.setattr(MI, "_comprimir_pdf",
                        lambda d, dpi, q: d + b"maior")
    dados, como = MI.pdf_para_envio(caminho)
    assert como is None and dados == caminho.read_bytes()


def test_pdf_com_senha_sobe_o_original(tmp_path):
    caminho = _pdf(tmp_path, "aberto.pdf", paginas=1)
    doc = pymupdf.open(caminho)
    fechado = tmp_path / "senha.pdf"
    doc.save(fechado, encryption=pymupdf.PDF_ENCRYPT_AES_256,
             owner_pw="dono-ficticio", user_pw="usuario-ficticio")
    doc.close()
    dados, como = MI.pdf_para_envio(fechado)
    assert como is None and dados == fechado.read_bytes()


def test_ler_arquivo_manda_a_copia_e_a_execucao_reusa(tmp_path, monkeypatch):
    caminho = _pdf(tmp_path, "digitalizado.pdf")
    chamadas = []
    verdadeiro = MI._comprimir_pdf
    monkeypatch.setattr(MI, "_comprimir_pdf",
                        lambda *a: chamadas.append(a[1]) or verdadeiro(*a))
    assert MI.tamanho_para_envio(_bd(caminho), {"anexo_id": 1, "nome": caminho.name,
                                               "tamanho": caminho.stat().st_size}) \
        < caminho.stat().st_size
    tentados = list(chamadas)
    assert tentados and tentados[0] == 150
    lido = MI._ler_arquivo(caminho, caminho.name)
    assert lido["comprimido"]["dpi"] == tentados[-1]
    assert len(base64.b64decode(lido["documentos"][0]["base64"])) == lido["comprimido"]["depois"]
    assert chamadas == tentados                       # a execução reusa a cópia do pedido


def _bd(caminho, nome=None):
    bd = Mock()
    bd.um.return_value = {"original_name": nome or Path(caminho).name,
                          "stored_path": str(caminho)}
    return bd


def test_word_conta_o_texto_que_sobe_e_nao_o_arquivo(tmp_path, monkeypatch):
    import revisao_anexos as RA
    caminho = tmp_path / "nota.docx"
    caminho.write_bytes(b"PK" + os.urandom(700_000))
    monkeypatch.setattr(RA, "texto_de_editor", lambda c, ext: "Nota devolutiva ficticia")
    d = {"anexo_id": 9, "nome": "nota.docx", "tamanho": 700_002}
    assert MI.tamanho_para_envio(_bd(caminho), d) == len("Nota devolutiva ficticia")


def test_na_duvida_vale_o_tamanho_gravado(tmp_path, monkeypatch):
    import revisao_anexos as RA
    d = {"anexo_id": 9, "nome": "nota.docx", "tamanho": 700_002}
    bd = Mock()
    bd.um.return_value = None
    assert MI.tamanho_para_envio(bd, d) == 700_002     # anexo sumiu
    caminho = tmp_path / "nota.docx"
    caminho.write_bytes(b"x")

    def quebra(*a):
        raise ValueError("docx torto")
    monkeypatch.setattr(RA, "texto_de_editor", quebra)
    assert MI.tamanho_para_envio(_bd(caminho), d) == 700_002
    foto = {"anexo_id": 3, "nome": "foto.jpg", "tamanho": 5 * MB}
    assert MI.tamanho_para_envio(bd, foto) == 5 * MB


# ------------------------------------------------------- os dois pedidos


def _qualificacao(monkeypatch, docs, bd):
    bd.escrever.return_value = [{"id": 123}]
    monkeypatch.setattr(QIA, "banco", lambda _: bd)
    monkeypatch.setattr(QIA, "init_schema", lambda _: None)
    monkeypatch.setattr(QIA, "prenotacao", lambda *a: {"id": 42})
    monkeypatch.setattr(QIA, "em_andamento", lambda *a: None)
    monkeypatch.setattr(QIA, "matricula_da_prenotacao", lambda *a: None)
    monkeypatch.setattr(QIA, "passou_do_teto_do_dia", lambda *a: None)
    monkeypatch.setattr(QIA, "documentos", lambda *a: docs)


def _bd_de_varios(caminhos):
    bd = Mock()
    bd.um.side_effect = lambda sql, args: (
        {"original_name": Path(caminhos[args[0]]).name,
         "stored_path": str(caminhos[args[0]])}
        if "attachments" in sql and args[0] in caminhos else None)
    return bd


def test_qualificacao_aceita_pdf_acima_do_limite_que_cabe_comprimido(tmp_path, monkeypatch):
    caminho = tmp_path / "titulo.pdf"
    caminho.write_bytes(b"%PDF-ficticio")
    monkeypatch.setattr(MI, "pdf_para_envio",
                        lambda c, dados=None: (b"x" * (10 * MB), {"dpi": 150}))
    docs = [{"anexo_id": 1, "nome": "titulo.pdf", "tamanho": 60 * MB,
             "sha256": "a", "origem": "prenotacao"}]
    bd = _bd_de_varios({1: caminho})
    _qualificacao(monkeypatch, docs, bd)
    assert QIA.pedir(None, 42, anexos_ids=[1]) == 123


def test_qualificacao_sem_compressao_mantem_a_recusa_de_hoje(tmp_path, monkeypatch):
    caminho = tmp_path / "titulo.pdf"
    caminho.write_bytes(b"%PDF-ficticio")
    monkeypatch.setattr(MI, "pdf_para_envio",
                        lambda c, dados=None: (_ for _ in ()).throw(RuntimeError("x")))
    docs = [{"anexo_id": 1, "nome": "titulo.pdf", "tamanho": 60 * MB,
             "sha256": "a", "origem": "prenotacao"}]
    bd = _bd_de_varios({1: caminho})
    _qualificacao(monkeypatch, docs, bd)
    with pytest.raises(QIA.QualificacaoIAError, match="somam 60.0 MB.*50 MB por pedido"):
        QIA.pedir(None, 42, anexos_ids=[1])
    bd.escrever.assert_not_called()


def test_minutas_contam_o_pdf_comprimido_e_o_texto_do_word(tmp_path, monkeypatch):
    import revisao_anexos as RA
    pdf, docx = tmp_path / "escritura.pdf", tmp_path / "nota.docx"
    pdf.write_bytes(b"%PDF-ficticio")
    docx.write_bytes(b"PK")
    monkeypatch.setattr(MI, "pdf_para_envio",
                        lambda c, dados=None: (b"x" * (14 * MB), {"dpi": 150}))
    monkeypatch.setattr(RA, "texto_de_editor", lambda c, ext: "texto curto")
    docs = {1: {"anexo_id": 1, "nome": "escritura.pdf", "tamanho": 28 * MB,
                "sha256": "a", "origem": "ato"},
            2: {"anexo_id": 2, "nome": "nota.docx", "tamanho": 8 * MB,
                "sha256": "b", "origem": "ato"}}
    bd = _bd_de_varios({1: pdf, 2: docx})
    bd.escrever.return_value = [{"id": 77}]
    monkeypatch.setattr(MI, "banco", lambda _: bd)
    monkeypatch.setattr(MI, "init_schema", lambda _: None)
    monkeypatch.setattr(MI, "alvo", lambda *a: {"tipo": "ESCRITURA"})
    monkeypatch.setattr(MI, "em_andamento", lambda *a: None)
    monkeypatch.setattr(MI, "texto_do_destino", lambda *a: None)
    monkeypatch.setattr(MI, "documentos_disponiveis", lambda *a, **k: list(docs.values()))
    assert MI.pedir(None, MI.NOTAS, 5, anexos_ids=[1, 2]) == 77


def test_minutas_recusam_se_nem_comprimido_cabe(tmp_path, monkeypatch):
    pdf = tmp_path / "escritura.pdf"
    pdf.write_bytes(b"%PDF-ficticio")
    monkeypatch.setattr(MI, "pdf_para_envio",
                        lambda c, dados=None: (b"x" * (25 * MB), {"dpi": 130}))
    docs = [{"anexo_id": 1, "nome": "escritura.pdf", "tamanho": 40 * MB,
             "sha256": "a", "origem": "ato"}]
    bd = _bd_de_varios({1: pdf})
    monkeypatch.setattr(MI, "banco", lambda _: bd)
    monkeypatch.setattr(MI, "init_schema", lambda _: None)
    monkeypatch.setattr(MI, "alvo", lambda *a: {"tipo": "ESCRITURA"})
    monkeypatch.setattr(MI, "em_andamento", lambda *a: None)
    monkeypatch.setattr(MI, "documentos_disponiveis", lambda *a, **k: docs)
    with pytest.raises(MI.MinutaIAError, match="somam 25.0 MB.*21 MB por pedido"):
        MI.pedir(None, MI.NOTAS, 5, anexos_ids=[1])
    bd.escrever.assert_not_called()

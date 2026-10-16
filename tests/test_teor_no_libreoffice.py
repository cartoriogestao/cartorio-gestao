"""Levar o teor para o LibreOffice e trazê-lo de volta, pelas telas.

«O teor do ato não sai formatado e visível como ficará completo pra quem lavra.
 Ideal seria incorporar uma suíte do LibreOffice… Se não for possível,
 possibilitar em botão facilitado a exportação do arquivo base e permitir a
 importação do arquivo odt ou docx após a edição, assim como gerar e receber o
 upload do pdf assinado após a lavratura e selo.»
— o oficial, em 27/08/2026, na segunda vez que apontou isto.

O QUE ESTES TESTES PROTEGEM
    O ciclo inteiro — exportar, editar fora, trazer de volta — e as três
    recusas que o cercam: rascunho não se confunde com traslado, ato lançado não
    troca de texto, e PDF assinado não entra antes do ato existir no livro.
"""
from __future__ import annotations

import glob
import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
TEOR = ("<p>SAIBAM quantos este público instrumento virem que, aos vinte e sete "
        "dias do mês de agosto de dois mil e vinte e seis.</p>"
        "<p>COMPARECERAM as partes entre si justas e contratadas.</p>"
        "<p>E de como assim disseram, do que dou fé.</p>")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ato(casa, *, situacao="EM_LAVRATURA", teor=TEOR) -> int:
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO nt_atos (tipo, data, natureza, situacao, teor,
                   teor_formato, origem, criado_em)
               VALUES ('ESCRITURA','2026-08-27','COMPRA E VENDA',?,?,'html',
                       'MANUAL','2026-08-27T10:00:00')""",
            (situacao, teor))
    return int(cur.lastrowid)


def _teor_gravado(casa, ato_id: int) -> str:
    return _con(casa).execute("SELECT teor FROM nt_atos WHERE id=?",
                              (ato_id,)).fetchone()["teor"] or ""


def _odt(paragrafos: list[str]) -> bytes:
    from ri_odt import gerar_odt, html_para_odf
    html = "".join(f"<p>{p}</p>" for p in paragrafos)
    return gerar_odt(html_para_odf(html), titulo="editado")


def _mandar(casa, ato_id: int, conteudo: bytes, nome: str, rota="teor/importar"):
    html = casa["cliente"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/notas/atos/{ato_id}/{rota}",
        data={"csrf_token": _token(html),
              "arquivo": (io.BytesIO(conteudo), nome)},
        content_type="multipart/form-data", follow_redirects=True)


# ------------------------------------------------------------- a prévia


def test_a_tela_mostra_o_teor_como_ele_vai_sair(casa):
    """Era a pergunta: «como isto vai ficar quando estiver completo?»"""
    html = casa["cliente"].get(
        f"/notas/atos/{_ato(casa)}").get_data(as_text=True)
    assert "Como vai sair" in html
    assert "teor-previa" in html
    assert "SAIBAM quantos" in html


# ------------------------------------------------------------- exportar


def test_o_rascunho_sai_em_odt_e_diz_que_e_rascunho(casa):
    """Sair sem dizer faria alguém entregar rascunho como instrumento."""
    r = casa["cliente"].get(f"/notas/atos/{_ato(casa)}/teor.odt")
    assert r.mimetype == "application/vnd.oasis.opendocument.text"
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        texto = re.sub(r"<[^>]+>", " ", z.read("content.xml").decode("utf-8"))
    assert "RASCUNHO" in texto
    assert "não é traslado" in texto.replace("  ", " ") or \
        "não vale como instrumento" in texto
    assert "SAIBAM quantos" in texto


def test_o_rascunho_sai_mesmo_com_o_ato_em_lavratura(casa):
    """É a diferença para o traslado, que só sai depois de lançado."""
    assert casa["cliente"].get(
        f"/notas/atos/{_ato(casa)}/teor.odt").status_code == 200


def test_ato_sem_teor_nao_exporta_nada(casa):
    html = casa["cliente"].get(
        f"/notas/atos/{_ato(casa, teor=None)}/teor.odt",
        follow_redirects=True).get_data(as_text=True)
    assert "ainda não tem teor" in html


# -------------------------------------------------------------- importar


def test_o_ciclo_inteiro_fecha(casa):
    """Exportar, editar fora, trazer de volta — e o teor é o novo."""
    ato = _ato(casa)
    editado = ["Primeiro parágrafo, reescrito no LibreOffice.",
               "Segundo parágrafo, também.",
               "Terceiro, que não existia antes."]
    html = _mandar(casa, ato, _odt(editado), "teor.odt").get_data(as_text=True)
    assert "Teor trazido do arquivo" in html
    gravado = _teor_gravado(casa, ato)
    for p in editado:
        assert p in gravado
    assert "SAIBAM quantos" not in gravado


def test_a_tela_diz_o_tamanho_da_mudanca_antes_de_o_escrevente_seguir(casa):
    """Quem traz de volta tem direito de ver o que está trazendo."""
    ato = _ato(casa)
    html = _mandar(casa, ato, _odt(["um", "dois"]),
                   "x.odt").get_data(as_text=True)
    assert "2 parágrafo(s)" in html
    assert "contra 3 que havia" in html


def test_o_docx_tambem_entra(casa):
    """Com o espaço de nome DE VERDADE — o que o Word grava.

    A primeira versão deste teste declarava `xmlns:w="x"`, e por isso não
    provava a leitura do arquivo do Word: provava o que o meu leitor de então
    tolerava.
    """
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    corpo = ('<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>JOÃO DA SILVA</w:t></w:r>'
             '<w:r><w:t>, comprador.</w:t></w:r></w:p>'
             '<w:p><w:r><w:t>Segundo parágrafo.</w:t></w:r></w:p>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("word/document.xml",
                   f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>'
                   f'{corpo}</w:body></w:document>')
    ato = _ato(casa)
    _mandar(casa, ato, saida.getvalue(), "editado.docx")
    gravado = _teor_gravado(casa, ato)
    assert "Segundo parágrafo." in gravado
    # E O NEGRITO DO WORD CHEGA AO TEOR — é a atividade fim da casa.
    assert "<b>JOÃO DA SILVA</b>" in gravado


def test_o_cabecalho_de_rascunho_nao_volta_para_dentro_do_teor(casa):
    """Ele foi posto para ninguém confundir rascunho com instrumento.

    Trazê-lo de volta poria a frase «isto é um rascunho» dentro do ato.
    """
    ato = _ato(casa)
    r = casa["cliente"].get(f"/notas/atos/{ato}/teor.odt").get_data()
    _mandar(casa, ato, r, "teor.odt")
    gravado = _teor_gravado(casa, ato)
    assert "RASCUNHO" not in gravado
    assert "não vale como instrumento" not in gravado
    # E o teor de verdade voltou inteiro.
    assert "SAIBAM quantos" in gravado
    assert "dou fé" in gravado


def test_arquivo_de_outro_tipo_e_recusado_com_frase_de_balcao(casa):
    html = _mandar(casa, _ato(casa), b"nao sou documento",
                   "teor.txt").get_data(as_text=True)
    assert "LibreOffice" in html or "odt" in html


def test_arquivo_corrompido_nao_apaga_o_teor(casa):
    """Recusa que apaga o que havia é pior que recusa nenhuma."""
    ato = _ato(casa)
    _mandar(casa, ato, b"nao sou um zip", "teor.odt")
    assert "SAIBAM quantos" in _teor_gravado(casa, ato)


def test_nao_se_troca_o_teor_de_ato_ja_lancado(casa):
    """Ato lançado tem teor que foi para o papel, e quem confere lê o papel."""
    ato = _ato(casa, situacao="LANCADO")
    html = _mandar(casa, ato, _odt(["outro texto"]),
                   "x.odt").get_data(as_text=True)
    assert "retificação" in html
    assert "SAIBAM quantos" in _teor_gravado(casa, ato)


def test_a_tela_so_oferece_a_importacao_enquanto_o_ato_esta_em_lavratura(casa):
    em_lavratura = casa["cliente"].get(
        f"/notas/atos/{_ato(casa)}").get_data(as_text=True)
    assert "Trazer o teor de um arquivo editado" in em_lavratura
    lancado = casa["cliente"].get(
        f"/notas/atos/{_ato(casa, situacao='LANCADO')}").get_data(as_text=True)
    assert "Trazer o teor de um arquivo editado" not in lancado


# ----------------------------------------------------------- o PDF assinado


def test_o_pdf_assinado_entra_depois_de_lancado(casa):
    ato = _ato(casa, situacao="LANCADO")
    html = _mandar(casa, ato, b"%PDF-1.4 conteudo", "assinado.pdf",
                   rota="assinado").get_data(as_text=True)
    assert "impressão digital" in html
    anexos = _con(casa).execute(
        "SELECT * FROM attachments WHERE entity_type='NT_ATO' AND entity_id=?",
        (ato,)).fetchall()
    assert len(anexos) == 1
    assert anexos[0]["sha256"]


def test_nao_entra_pdf_de_ato_que_ainda_esta_em_lavratura(casa):
    """Assinatura de coisa que ainda pode mudar não prova nada."""
    ato = _ato(casa)
    html = _mandar(casa, ato, b"%PDF-1.4", "assinado.pdf",
                   rota="assinado").get_data(as_text=True)
    assert "ainda está em lavratura" in html
    assert _con(casa).execute(
        "SELECT COUNT(*) n FROM attachments WHERE entity_id=?",
        (ato,)).fetchone()["n"] == 0


def test_so_entra_pdf(casa):
    html = _mandar(casa, _ato(casa, situacao="LANCADO"), b"qualquer",
                   "assinado.odt", rota="assinado").get_data(as_text=True)
    assert "em PDF" in html

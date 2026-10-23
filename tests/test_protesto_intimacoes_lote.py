"""O PDF com várias intimações entregues, separado pelo QR do aviso — 15/10/2026.

As folhas dos testes são ESCANEADAS de mentira: a página vira imagem (como sai
do scanner) e volta para PDF — o QR tem de ser lido da imagem, e não de um
objeto vetorial que nenhum scanner produz.
"""
from __future__ import annotations

import hashlib
import io
import sqlite3
import zipfile

import pytest

import protesto_intimacoes_lote as L
from test_protesto_aviso_web import _con, _token, s  # noqa: F401

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz


def _titulo(s, n: int) -> int:
    import protesto as PT
    from database import Database
    sv = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
          "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
          "serventia_titulo": "Tabelião e Oficial de Registro",
          "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": "001", "apresentante_nome": "BANCO EXEMPLO",
            "especie": "DMI", "numero_titulo": f"77{n}/1",
            "nosso_numero": f"NN77{n}", "data_emissao": "2026-01-05",
            "data_vencimento": "2026-02-05", "valor": "100.00",
            "saldo": "110.00", "praca_protesto": "CIDADE EXEMPLO",
            "cedente": {"nome": "LOJA EXEMPLO LTDA",
                        "documento": "00000017000149"},
            "devedores": [{"nome": f"BEATRIZ EXEMPLO {n}", "CPF": "04785512388",
                           "enderecos": [{"endereco": "RUA GRANDE, 10",
                                          "bairro": "CENTRO",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave=f"lote:{n}", agora=agora)
        PT.lancar_apontamento(con, tid, sv=sv, agora=agora,
                              data_extenso="quinze de outubro")
    return tid


def _aviso(s, n: int) -> sqlite3.Row:
    tid = _titulo(s, n)
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    s["c"].post(f"/protesto/{tid}/aviso", data={"csrf_token": _token(ficha)},
                follow_redirects=True)
    return _con(s).execute(
        "SELECT * FROM pt_avisos WHERE titulo_id=?", (tid,)).fetchone()


def _escaneado(folhas: list) -> bytes:
    """Monta um PDF de folhas escaneadas: cada item é um QR (str) ou None."""
    doc = fitz.open()
    for qr in folhas:
        p = doc.new_page()
        p.insert_text((72, 140), "AVISO DE INTIMACAO - folha de teste")
        if qr:
            p.insert_image(fitz.Rect(260, 30, 331, 101), stream=L.png_do_qr(qr))
    escaneado = fitz.open()
    for pagina in doc:
        png = pagina.get_pixmap(dpi=150, colorspace="gray").tobytes("png")
        nova = escaneado.new_page(width=pagina.rect.width,
                                  height=pagina.rect.height)
        nova.insert_image(nova.rect, stream=png)
    return escaneado.tobytes()


def _qr(aviso) -> str:
    return L.conteudo_do_qr(aviso, "2610150001")


def _enviar(s, pdf: bytes) -> str:
    tela = s["c"].get("/protesto/avisos/lote").get_data(as_text=True)
    return s["c"].post(
        "/protesto/avisos/lote",
        data={"csrf_token": _token(tela),
              "pdf": (io.BytesIO(pdf), "intimacoes.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True).get_data(as_text=True)


# --------------------------------------------------------------- o domínio


def test_o_qr_vai_e_volta_da_folha_escaneada():
    pdf = _escaneado(["CG-AVISO:5:12/2026:2610150001", None,
                      "CG-AVISO:9:13/2026:2610150002"])
    lido = L.agrupar(L.ler_paginas(pdf))
    assert [(g["aviso_id"], g["paginas"]) for g in lido["grupos"]] == \
        [(5, [1, 2]), (9, [3])]
    assert lido["soltas"] == []


def test_folha_antes_de_qualquer_qr_fica_solta_e_nao_some():
    pdf = _escaneado([None, "CG-AVISO:5:12/2026:"])
    lido = L.agrupar(L.ler_paginas(pdf))
    assert lido["soltas"] == [1]
    assert lido["grupos"][0]["paginas"] == [2]


def test_o_mesmo_aviso_em_dois_trechos_e_marcado():
    q = "CG-AVISO:5:12/2026:"
    lido = L.agrupar(L.ler_paginas(_escaneado(
        [q, "CG-AVISO:9:13/2026:", q])))
    assert all(g["repetido"] for g in lido["grupos"] if g["aviso_id"] == 5)


def test_qr_de_fora_da_casa_nao_conta():
    assert L.ler_conteudo("https://exemplo/qualquer") is None
    assert L.ler_conteudo("CG-AVISO:x:1/2026:") is None


def test_o_que_nao_e_pdf_e_recusado():
    with pytest.raises(L.LoteError):
        L.ler_paginas(b"nao sou pdf")


# --------------------------------------------------------------- a tela


def test_o_aviso_impresso_traz_o_qr(s):
    from database import Database
    # o aviso não sai sem o horário da serventia (CN-MA art. 920)
    Database(s["banco"]).set_settings({"serventia_horario": "das 08h às 14h"})
    av = _aviso(s, 1)
    r = s["c"].get(f"/protesto/avisos/{av['id']}.odt?formato=odt")
    assert r.status_code == 200
    pacote = zipfile.ZipFile(io.BytesIO(r.data))
    assert "Pictures/qr-do-papel.png" in pacote.namelist()
    import cv2
    import numpy as np
    png = pacote.read("Pictures/qr-do-papel.png")
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
    texto, _p, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert L.ler_conteudo(texto)["aviso_id"] == av["id"]


def test_o_lote_confere_registra_e_anexa_so_as_folhas_de_cada_um(s):
    a1, a2 = _aviso(s, 1), _aviso(s, 2)
    pdf = _escaneado([None, _qr(a1), None, _qr(a2)])
    html = _enviar(s, pdf)
    assert "2 pronto(s) para registrar" in html
    assert "1 folha(s) sem aviso" in html
    sha = hashlib.sha256(pdf).hexdigest()
    assert f"/protesto/avisos/lote/{sha}/registrar" in html

    folhas = s["c"].get(f"/protesto/avisos/lote/{sha}/folhas?p=2,3")
    assert folhas.status_code == 200 and folhas.mimetype == "application/pdf"

    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(
        f"/protesto/avisos/lote/{sha}/registrar",
        data={"csrf_token": _token(tela), "aviso_id": [a1["id"], a2["id"]],
              f"desfecho_{a1['id']}": "ENTREGUE",
              f"desfecho_{a2['id']}": "ENTREGUE",
              f"quando_{a1['id']}": "2026-10-14"},
        follow_redirects=True).get_data(as_text=True)
    assert "2 aviso(s) do PDF registrados: 2 entrega(s)" in html

    con = _con(s)
    for av, paginas in ((a1, 2), (a2, 1)):
        linha = con.execute("SELECT situacao, entrega_em FROM pt_avisos "
                            "WHERE id=?", (av["id"],)).fetchone()
        assert linha["situacao"] == "ENTREGUE"
        assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                           (av["titulo_id"],)).fetchone()[0] == "INTIMADO"
        anexo = con.execute(
            "SELECT stored_path FROM attachments WHERE entity_type='PT_AVISO' "
            "AND entity_id=?", (av["id"],)).fetchone()
        assert fitz.open(anexo["stored_path"]).page_count == paginas
    assert con.execute("SELECT entrega_em FROM pt_avisos WHERE id=?",
                       (a1["id"],)).fetchone()[0] == "2026-10-14"


def test_registrar_de_novo_nao_duplica(s):
    a1 = _aviso(s, 1)
    pdf = _escaneado([_qr(a1)])
    _enviar(s, pdf)
    sha = hashlib.sha256(pdf).hexdigest()

    def registrar():
        t = s["c"].get("/protesto/avisos").get_data(as_text=True)
        return s["c"].post(f"/protesto/avisos/lote/{sha}/registrar",
                           data={"csrf_token": _token(t),
                                 "aviso_id": a1["id"],
                                 f"desfecho_{a1['id']}": "ENTREGUE"},
                           follow_redirects=True).get_data(as_text=True)

    assert "1 entrega(s)" in registrar()
    assert "já foram registradas" in registrar()
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM pt_atos WHERE tipo='INTIMACAO'"
                       ).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM attachments "
                       "WHERE entity_type='PT_AVISO'").fetchone()[0] == 1


def test_o_canhoto_com_tentativa_registra_a_tentativa_e_anexa_a_prova(s):
    """15/10/2026: «um campo de tentativa, onde se coloca quando tentou, para
    fundamentar a expedição de edital»."""
    a1 = _aviso(s, 1)
    pdf = _escaneado([_qr(a1)])
    html = _enviar(s, pdf)
    assert "Não entregue — registrar a tentativa" in html
    sha = hashlib.sha256(pdf).hexdigest()
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(f"/protesto/avisos/lote/{sha}/registrar",
                       data={"csrf_token": _token(tela), "aviso_id": a1["id"],
                             f"desfecho_{a1['id']}": "11",
                             f"quando_{a1['id']}": "2026-10-14"},
                       follow_redirects=True).get_data(as_text=True)
    assert "1 tentativa(s) registrada(s)" in html
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_avisos WHERE id=?",
                       (a1["id"],)).fetchone()[0] == "NAO_ENTREGUE"
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (a1["titulo_id"],)).fetchone()[0] == "APONTADO"
    t = con.execute("SELECT motivo, quando FROM pt_tentativas WHERE aviso_id=?",
                    (a1["id"],)).fetchone()
    assert (t["motivo"], t["quando"]) == (11, "2026-10-14")
    anexo = con.execute("SELECT description FROM attachments WHERE "
                        "entity_type='PT_AVISO' AND entity_id=?",
                        (a1["id"],)).fetchone()
    assert "tentativa" in anexo["description"]
    # a prova aparece ao lado do aviso na lista do edital
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "prova:" in tela


def test_sem_escolher_o_desfecho_nada_se_registra(s):
    a1 = _aviso(s, 1)
    pdf = _escaneado([_qr(a1)])
    _enviar(s, pdf)
    sha = hashlib.sha256(pdf).hexdigest()
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(f"/protesto/avisos/lote/{sha}/registrar",
                       data={"csrf_token": _token(tela), "aviso_id": a1["id"]},
                       follow_redirects=True).get_data(as_text=True)
    assert "escolha o desfecho" in html
    assert _con(s).execute("SELECT situacao FROM pt_avisos WHERE id=?",
                           (a1["id"],)).fetchone()[0] == "EMITIDO"


def test_qr_com_numero_trocado_nao_entra(s):
    a1 = _aviso(s, 1)
    falso = f"CG-AVISO:{a1['id']}:{int(a1['numero']) + 50}/{a1['ano']}:"
    html = _enviar(s, _escaneado([falso]))
    assert "QR de outro papel" in html


def test_a_tela_de_avisos_tem_a_porta_do_lote(s):
    html = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "/protesto/avisos/lote" in html


def test_o_aviso_traz_o_canhoto_destacavel_com_o_qr(s):
    """15/10/2026: «uma parte destacável para o cartório levar apenas a
    confirmação de recebimento, com a assinatura»."""
    from database import Database
    Database(s["banco"]).set_settings({"serventia_horario": "das 08h às 14h"})
    av = _aviso(s, 1)
    r = s["c"].get(f"/protesto/avisos/{av['id']}.odt?formato=odt")
    conteudo = zipfile.ZipFile(io.BytesIO(r.data)).read("content.xml").decode()
    assert "DESTAQUE AQUI" in conteudo
    assert "COMPROVANTE DE RECEBIMENTO DA INTIMAÇÃO" in conteudo
    assert "Assinatura:" in conteudo
    assert "TENTATIVAS DE ENTREGA" in conteudo
    # o QR mora no canhoto, DEPOIS da linha de corte
    assert conteudo.index("DESTAQUE AQUI") < conteudo.index("qr-do-papel.png")


def test_o_mesmo_aviso_duas_vezes_na_folha_e_um_so():
    doc = fitz.open()
    p = doc.new_page()
    png = L.png_do_qr("CG-AVISO:5:12/2026:")
    p.insert_image(fitz.Rect(60, 40, 131, 111), stream=png)
    p.insert_image(fitz.Rect(60, 600, 131, 671), stream=png)
    ps = L.ler_paginas(doc.tobytes())
    assert ps[0]["qr"] and ps[0]["qr"]["aviso_id"] == 5

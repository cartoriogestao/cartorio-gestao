"""Certidao RI de inteiro teor: digitalizacao oficial ou texto extraido.

Pedido de 16/09/2026: o balcao escolhe reproducao da digitalizacao (com selo
ao final) ou o texto do modelo — este ultimo para livros antigos / manuscritos.
A ficha guarda o arquivo oficial e marca pendencia de ONR (sem transmitir).
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    # A TRAVA DO SELO PAGO FICA DESLIGADA NESTA BANCADA (22/10/2026). Aqui se
    # mede o PAPEL da reprodução, e não o pagamento: com a trava ligada e sem
    # protocolo, a certidão fica «aguardando cobertura» e — por decisão do
    # oficial — não pode ser impressa até o selo sair. Desligada, o selo é
    # pedido a um aparelho que não existe, falha, e a certidão sai cancelada,
    # como saía antes da 3.7.0; o papel dela continua se imprimindo.
    db.set_settings({"ri_cns": "000000", "ri_cidade": "Cidade Exemplo",
                     "ri_uf": "MA", "selo_trava_caixa": "DESLIGADA"})
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _png_minimo() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


def _matricula(con) -> int:
    cur = con.execute(
        """INSERT INTO ri_matriculas
           (numero, livro, livro_norm, situacao, tipo_ficha, cidade, uf,
            descricao_perimetro, origem, criado_em)
           VALUES ('99001', '2-C', '2C', 'ATIVA', 'ESTRUTURADA', 'Cidade Exemplo',
                   'MA', 'Lote teste digi', 'MANUAL', datetime('now'))""")
    mid = int(cur.lastrowid)
    con.commit()
    return mid


def test_upload_digitalizacao_marca_onr_e_aparece_na_ficha(casa):
    con = _con(casa)
    mid = _matricula(con)
    con.close()
    c = casa["cliente"]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "fonte_corpo" in ficha
    assert "digitalizacao" in ficha.lower() or "Digitalizacao" in ficha

    png = _png_minimo()
    r = c.post(
        f"/registro-imoveis/{mid}/digitalizacao",
        data={
            "csrf_token": _token(ficha),
            "arquivo": (io.BytesIO(png), "ficha99001.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "ONR" in html or "pendente" in html.lower()

    con = _con(casa)
    row = con.execute(
        "SELECT digi_path, digi_nome, digi_onr_pendente, digi_sha256 "
        "FROM ri_matriculas WHERE id=?",
        (mid,)).fetchone()
    assert row["digi_path"] and Path(row["digi_path"]).is_file()
    assert row["digi_nome"] == "ficha99001.png"
    assert int(row["digi_onr_pendente"]) == 1
    assert row["digi_sha256"]
    con.close()


def test_inteiro_teor_sem_digi_recusa_reproducao(casa):
    con = _con(casa)
    mid = _matricula(con)
    con.close()
    c = casa["cliente"]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post(
        f"/registro-imoveis/{mid}/certidao",
        data={
            "csrf_token": _token(ficha),
            "tipo": "INTEIRO_TEOR",
            "fonte_corpo": "DIGITALIZACAO",
            "requerente": "Fulano da Silva",
            "lavrar_sem_selo": "1",
        },
        follow_redirects=True,
    )
    html = r.get_data(as_text=True)
    assert "digitaliza" in html.lower()
    con = _con(casa)
    n = con.execute(
        "SELECT COUNT(*) n FROM ri_certidoes WHERE matricula_id=?",
        (mid,)).fetchone()["n"]
    assert n == 0
    con.close()


def test_inteiro_teor_por_texto_ainda_emite(casa):
    con = _con(casa)
    mid = _matricula(con)
    con.close()
    c = casa["cliente"]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post(
        f"/registro-imoveis/{mid}/certidao",
        data={
            "csrf_token": _token(ficha),
            "tipo": "INTEIRO_TEOR",
            "fonte_corpo": "TEXTO",
            "requerente": "Fulano da Silva",
            "lavrar_sem_selo": "1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    con = _con(casa)
    row = con.execute(
        "SELECT id, fonte_corpo, corpo FROM ri_certidoes "
        "WHERE matricula_id=? ORDER BY id DESC",
        (mid,)).fetchone()
    assert row is not None
    assert (row["fonte_corpo"] or "TEXTO") == "TEXTO"
    assert row["corpo"]
    con.close()


def test_inteiro_teor_por_digitalizacao_congela_arquivo(casa):
    con = _con(casa)
    mid = _matricula(con)
    con.close()
    c = casa["cliente"]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    png = _png_minimo()
    c.post(
        f"/registro-imoveis/{mid}/digitalizacao",
        data={
            "csrf_token": _token(ficha),
            "arquivo": (io.BytesIO(png), "oficial.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    ficha2 = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post(
        f"/registro-imoveis/{mid}/certidao",
        data={
            "csrf_token": _token(ficha2),
            "tipo": "INTEIRO_TEOR",
            "fonte_corpo": "DIGITALIZACAO",
            "requerente": "Fulano da Silva",
            "lavrar_sem_selo": "1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    con = _con(casa)
    row = con.execute(
        """SELECT id, fonte_corpo, digi_path, digi_sha256
             FROM ri_certidoes WHERE matricula_id=? ORDER BY id DESC""",
        (mid,)).fetchone()
    assert row is not None
    assert row["fonte_corpo"] == "DIGITALIZACAO"
    assert row["digi_path"] and Path(row["digi_path"]).is_file()
    assert row["digi_sha256"]
    odt = c.get(f"/registro-imoveis/certidoes/{row['id']}.odt")
    assert odt.status_code == 200
    assert odt.data[:2] == b"PK" or len(odt.data) > 100
    con.close()


def test_a_reprografica_pela_tela_identifica_a_matricula_e_le_o_cadastro(casa):
    """O MODELO DA CASA PELA ROTA (LH02): a identificação vem da ficha
    (`ri_matriculas`: número, livro, CNM), o cabeçalho e a cidade vêm do
    cadastro da serventia, e quem assina é quem emitiu. Nada disso é do
    código: a serventia do ensaio é a fictícia do `conftest`."""
    import zipfile
    from datetime import date

    import ri_digitalizacao as RDIGI
    con = _con(casa)
    mid = _matricula(con)
    con.execute("UPDATE ri_matriculas SET cnm = '000000.2.0099001-00' WHERE id = ?",
                (mid,))
    con.commit()
    con.close()
    c = casa["cliente"]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/digitalizacao",
           data={"csrf_token": _token(ficha),
                 "arquivo": (io.BytesIO(_png_minimo()), "oficial.png")},
           content_type="multipart/form-data", follow_redirects=True)
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/certidao",
           data={"csrf_token": _token(ficha), "tipo": "INTEIRO_TEOR",
                 "fonte_corpo": "DIGITALIZACAO", "requerente": "Fulano da Silva",
                 "lavrar_sem_selo": "1"},
           follow_redirects=True)
    con = _con(casa)
    row = con.execute(
        """SELECT id, emitida_por_nome FROM ri_certidoes
            WHERE matricula_id=? AND fonte_corpo='DIGITALIZACAO'
            ORDER BY id DESC""", (mid,)).fetchone()
    con.close()
    assert row is not None, "a certidão por reprodução não saiu"
    papel = c.get(f"/registro-imoveis/certidoes/{row['id']}.odt?formato=odt")
    assert papel.status_code == 200 and papel.data[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(papel.data)) as z:
        xml = z.read("content.xml").decode("utf-8")
    hoje = RDIGI.data_por_extenso_repro(date.today().isoformat())
    for trecho in (
            "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO/MA",
            "Mario Exemplo dos Santos — Tabelião e Registrador Oficial",
            "Beatriz Exemplo de Souza — Tabeliã e Registradora Substituta",
            "Matrícula nº 99.001 do Livro nº 2-C – Registro Geral, CNM "
            "000000.2.0099001-00, em 1 (uma) página.",
            f"Cidade Exemplo/MA, {hoje}.",
            "CERTIFICO ainda que"):
        assert trecho in xml, trecho
    assert row["emitida_por_nome"], "a emissão grava quem emitiu"
    assert ('<text:p text:style-name="P-repro-fecho-assina">'
            f'{row["emitida_por_nome"]}') in xml


def test_paginas_png_e_odt_unitario(tmp_path):
    import zipfile
    import ri_digitalizacao as RDIGI
    png = _png_minimo()
    arq = tmp_path / "p.png"
    arq.write_bytes(png)
    assert len(RDIGI.paginas_png(arq)) == 1
    odt = RDIGI.odt_da_digitalizacao(
        arq, selo_texto="SELOTESTE123", nome="t",
        corpo_html=(
            '<p align="center"><b>CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA</b></p>'
            "<p>Resumo interno.</p>"
            "<p>CERTIFICO ainda que, nesta data, <b>não há</b> título prenotado "
            "nem protocolo em aberto referente a esta matrícula.</p>"
        ),
    )
    assert odt[:4] == b"PK\x03\x04"
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        xml = z.read("content.xml").decode("utf-8")
    assert "CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA" in xml or (
        "CERTID" in xml and "REPROGR" in xml)
    assert "CERTIFICO ainda que" in xml
    assert "não há" in xml or "n\u00e3o h\u00e1" in xml or "nao ha" in xml.lower()


def test_corpo_resumo_traz_titulo_e_era_o_que():
    import ri_digitalizacao as RDIGI
    html = RDIGI.corpo_resumo_digitalizacao(
        matricula="3750", paginas=8, sha256="abc")
    assert "CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA" in html
    assert "3750" in html
    assert "Era o que nela continha." in html


def test_odt_repro_layout_a4_e_imagem_cabe(tmp_path):
    """Layout global: A4, margem coerente, imagem dentro da area util."""
    import zipfile
    import ri_digitalizacao as RDIGI
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1242, 1755), "white").save(buf, format="PNG")
    arq = tmp_path / "ficha.png"
    arq.write_bytes(buf.getvalue())
    titulo = "CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA"
    odt = RDIGI.odt_da_digitalizacao(
        arq, selo_texto="SELOTESTE123", nome="t",
        corpo_html=(
            f'<p align="center"><b>{titulo}</b></p>'
            '<p>Certidão da matrícula <strong>3750</strong> '
            '(1 página(s); sha256=abc123deadbeef).</p>'
            '<p>O documento impresso reproduz as páginas digitalizadas e traz '
            'o selo de certidão ao final.</p>'
            '<p>Era o que nela continha.</p>'
            '<p>CERTIFICO ainda que, nesta data, não há título prenotado '
            'nem protocolo em aberto.</p>'
        ),
    )
    assert odt[:4] == b"PK\x03\x04"
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        xml = z.read("content.xml").decode("utf-8")
        styles = z.read("styles.xml").decode("utf-8")
    # Modelo da casa (substituta, 20/10/2026): título e fecho do modelo.
    assert "CERTIDÃO REPROGRÁFICA" in xml
    assert "P-repro-titulo" in xml
    assert "CERTIFICO ainda" in xml
    assert "Era o que constava no documento/assento reproduzido" in xml
    assert "Era o que nela continha" not in xml
    assert "sha256" not in xml.lower()
    assert "documento impresso reproduz" not in xml.lower()
    assert 'fo:page-width="21cm"' in styles or 'fo:page-width="21.0cm"' in styles
    assert 'fo:page-height="29.7cm"' in styles
    assert 'fo:margin-top="0.51cm"' in styles
    import re
    m = re.search(
        r'draw:name="digi1\.png"[^>]*svg:width="([0-9.]+)cm"[^>]*svg:height="([0-9.]+)cm"',
        xml,
    )
    assert m, xml[:500]
    w, h = float(m.group(1)), float(m.group(2))
    assert w <= 19.0, w
    assert h <= 28.0, h


def test_escala_e_fecho_helpers():
    import ri_digitalizacao as RDIGI
    w, h = RDIGI._escala_ficha_na_folha(1242, 1755, area_w_cm=18.9, area_h_cm=27.6)
    assert w <= 18.9 and h <= 27.6
    assert abs((h / w) - (1755 / 1242)) < 0.01
    titulo = "CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA"
    fecho = RDIGI._fecho_html_para_papel(
        f'<p align="center"><b>{titulo}</b></p>'
        '<p>x sha256=abc</p>'
        '<p>O documento impresso reproduz as páginas digitalizadas e traz o selo.</p>'
        '<p>CERTIFICO ainda que não há protocolo.</p>'
    )
    assert "CERTIFICO ainda" in fecho
    assert "sha256" not in fecho.lower()
    assert "documento impresso" not in fecho.lower()
    assert "REPROGR" not in fecho.upper()


MODULOS_DO_LOTE = ("ri_certidao_negativa", "ri_digi_prazo", "ri_digi_prazo_web",
                   "ri_digitalizacao", "ri_documentos", "ri_expurgo",
                   "ri_fichas_do_disco")


def test_os_modulos_compilam_no_python_3_11():
    """A producao roda Python 3.11. A f-string que repete as proprias aspas
    dentro das chaves (`f"{row["digi_nome"]}"`) so o 3.12 le: no 3.11 o
    `ri_digitalizacao` nem importa, e a ficha do RI cai junto."""
    import tokenize
    if not hasattr(tokenize, "FSTRING_START"):       # antes do 3.12, o import ja acusou
        return
    for nome in MODULOS_DO_LOTE:
        aspas: list[str] = []                        # as das f-strings abertas
        with open(RAIZ / f"{nome}.py", "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type == tokenize.FSTRING_END:
                    aspas.pop()
                    continue
                if tok.type not in (tokenize.FSTRING_START, tokenize.STRING):
                    continue
                abre = tok.string.lstrip("rRbBuUfF")[:3]
                abre = abre if abre in ('"""', "'''") else abre[0]
                assert not aspas or not abre.startswith(aspas[-1]), (
                    nome, tok.start[0], tok.line.strip())
                if tok.type == tokenize.FSTRING_START:
                    aspas.append(abre)

# -*- coding: utf-8 -*-
"""O comprovante da gratuidade — aviso insistente ao usuário, sem travar o ato.

    «pratica o ato e o usuário fica com aviso insistente até terminar de subir
     a comprovação da gratuidade»                  — o oficial, 11/10/2026
"""
from __future__ import annotations

import io
import re
import sqlite3

import pytest

import gratuidade_comprovante as GC
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

TEXTO_ISENTO = ("Poder Judiciário – TJMA. Selo: AVERBA000000VBKH58VIXU0CLW81, 13/10/2026 12:07:22, "
                "Ato: 14.4.1, Total R$ 43,37 Emol R$ 38,72 Selo Isento, Consulte em https://selo.tjma.jus.br")


def _con():
    con = conexao_de_teste()
    con.execute("""CREATE TABLE sd_selos (id INTEGER PRIMARY KEY, numero TEXT, texto TEXT, tabela TEXT,
        ato_id INTEGER, atribuicao TEXT, obtido_em TEXT, obtido_por TEXT, cancelado_em TEXT)""")
    con.execute("""CREATE TABLE attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT,
        entity_id INTEGER, original_name TEXT, stored_name TEXT, stored_path TEXT, sha256 TEXT,
        size_bytes INTEGER, description TEXT, uploaded_by INTEGER, uploaded_at TEXT)""")
    linhas = [
        (1, "AVERBA000000VBKH58VIXU0CLW81", TEXTO_ISENTO, "2026-10-13T10:00:00", "Beatriz Exemplo de Souza", None),
        (2, "AVERBA000000XA66PB40MVB00E35", TEXTO_ISENTO, "2026-10-14T10:00:00", "Beatriz Exemplo de Souza", None),
        (3, "CERTID000000AAAAAAAAAAAAAAAA", "Selo pago, Total R$ 53,58", "2026-10-14T10:00:00",
         "Beatriz Exemplo de Souza", None),
        (4, "AVERBA000000BBBBBBBBBBBBBBBB", TEXTO_ISENTO, "2026-10-14T10:00:00", "Carla Exemplo Lima", None),
        (5, "AVERBA000000CCCCCCCCCCCCCCCC", TEXTO_ISENTO, "2026-10-01T10:00:00", "Beatriz Exemplo de Souza", None),
        (6, "AVERBA000000DDDDDDDDDDDDDDDD", TEXTO_ISENTO, "2026-10-14T10:00:00", "Beatriz Exemplo de Souza",
         "2026-10-14T11:00:00"),
    ]
    con.executemany("INSERT INTO sd_selos(id, numero, texto, obtido_em, obtido_por, cancelado_em) "
                    "VALUES (?,?,?,?,?,?)", linhas)
    return con


def test_so_os_isentos_da_pessoa_desde_a_data_e_nao_cancelados():
    con = _con()
    ids = [p["id"] for p in GC.pendentes(con, nome="Beatriz Exemplo de Souza", username="beatriz")]
    assert ids == [1, 2]   # 3 é pago, 4 é da Carla, 5 é antes de 13/10, 6 foi cancelado


def test_a_data_de_inicio_e_configuravel():
    con = _con()
    con.execute("CREATE TABLE settings (key TEXT, value TEXT)")
    con.execute("INSERT INTO settings VALUES ('gratuidade_comprovante_desde', '2026-09-08')")
    assert [p["id"] for p in GC.pendentes(con, nome="beatriz exemplo de souza")] == [5, 1, 2]


def test_guardar_tira_o_aviso_daquele_ato(tmp_path):
    con = _con()
    GC.guardar(con, 1, nome_arquivo="declaracao.pdf", conteudo=b"%PDF", pasta=tmp_path,
               usuario_id=5, agora="t")
    assert [p["id"] for p in GC.pendentes(con, nome="Beatriz Exemplo de Souza")] == [2]


def test_selo_pago_e_arquivo_estranho_sao_recusados(tmp_path):
    con = _con()
    with pytest.raises(GC.ComprovanteError, match="não é de ato gratuito"):
        GC.guardar(con, 3, nome_arquivo="a.pdf", conteudo=b"x", pasta=tmp_path, usuario_id=1, agora="t")
    with pytest.raises(GC.ComprovanteError, match="PDF ou imagem"):
        GC.guardar(con, 1, nome_arquivo="a.exe", conteudo=b"x", pasta=tmp_path, usuario_id=1, agora="t")


def test_acha_na_pasta_pelo_codigo_no_nome(tmp_path):
    (tmp_path / "2026" / "OUTUBRO").mkdir(parents=True)
    (tmp_path / "2026" / "OUTUBRO" / "AVERBA000000XA66PB40MVB00E35.pdf").write_bytes(b"%PDF")
    (tmp_path / "2026" / "DARLENE.pdf").write_bytes(b"%PDF")
    achados = GC.na_pasta(["AVERBA000000XA66PB40MVB00E35", "AVERBA000000VBKH58VIXU0CLW81"], tmp_path)
    assert list(achados) == ["AVERBA000000XA66PB40MVB00E35"]


def test_o_aviso_aparece_em_toda_tela_e_some_ao_guardar(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        con.execute("INSERT INTO sd_selos(numero, texto, obtido_em, obtido_por, ambiente) "
                    "VALUES (?,?,?,?,?)", ("AVERBA000000VBKH58VIXU0CLW81", TEXTO_ISENTO,
                                           "2026-10-13T10:00:00", "MARIO EXEMPLO DOS SANTOS", "PRODUCAO"))
        selo_id = con.execute("SELECT id FROM sd_selos WHERE numero='AVERBA000000VBKH58VIXU0CLW81'").fetchone()[0]
    html = c.get("/administrativo/produtividade").get_data(as_text=True)
    assert "1 ato(s) gratuito(s) sem o comprovante" in html
    pagina = c.get("/gratuidades/comprovantes").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    r = c.post(f"/gratuidades/comprovantes/{selo_id}",
               data={"csrf_token": tok, "arquivo": (io.BytesIO(b"%PDF-1.4"), "declaracao.pdf")},
               content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    # O recado passou a contar os arquivos — HOTFIX-2026-10-13-07 (vários
    # arquivos por envio): «1 comprovante(s) guardado(s).» — 14/10/2026.
    assert "1 comprovante(s) guardado(s)" in r and "ato(s) gratuito(s) sem o comprovante" not in r


def test_sem_pasta_configurada_nao_procura_nada():
    """23/10/2026: sem `settings.gratuidade_pasta`, nada se oferece — o código
    não procura a pasta dos comprovantes em lugar nenhum."""
    assert GC.na_pasta(["AVERBA000000XA66PB40MVB00E35"], None) == {}


# ------------------------- G003 (achado G-2 da auditoria G002, 18/11/2026)
#
# «juntar» marcava o PDF como AMBOS (comprovante + certidão) mesmo sem
# certidão nenhuma para juntar, e o selo aparecia PRONTO na fila do Portal.
# Agora AMBOS só com certidão guardada ou com mais de um arquivo; a certidão
# tem campo próprio na tela do escrevente. Nada disso trava o ato.

ESCREVENTE_G003 = "MARIO EXEMPLO DOS SANTOS"   # o ADMIN de `cg_casa_logada`


def _pdf(texto: str) -> bytes:
    import selo_portal as SP
    fitz = SP._pymupdf()
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), texto)
    return doc.tobytes()


def _selo_isento(con, numero: str) -> int:
    from bd_nativo import banco
    return int(banco(con).escrever(
        "INSERT INTO sd_selos (numero, texto, atribuicao, obtido_em, obtido_por, ambiente) "
        "VALUES (%s, %s, 'RCPN', '2026-10-15T10:00:00', %s, 'PRODUCAO') RETURNING id",
        (numero, TEXTO_ISENTO, ESCREVENTE_G003))[0]["id"])


def _peca_e_fila(con, selo_id: int) -> tuple[list[str], str]:
    import selo_portal as SP
    pecas = [p["peca"] for p in SP.pecas(con, selo_id)]
    situacao = {s["id"]: s["situacao"] for s in SP.gratuitos(con)}[selo_id]
    return pecas, situacao


def test_juntar_sem_certidao_guardada_fica_comprovante_e_a_fila_diz_que_falta(cg_casa, tmp_path):
    pytest.importorskip("pymupdf")
    db = cg_casa["db"]
    with db.transaction() as con:
        selo = _selo_isento(con, "AVERBA000000G003000000000001")
        GC.guardar_junto(con, selo, arquivos=[("declaracao.pdf", _pdf("COMPROVANTE"))],
                         pasta=tmp_path, usuario_id=None, agora="t", fundamento="POBREZA_RCPN")
        assert _peca_e_fila(con, selo) == (["COMPROVANTE"], "FALTA_CERTIDAO")
        assert GC.pendentes(con, nome=ESCREVENTE_G003) == []      # o aviso some do mesmo jeito
        assert not GC.certidao_guardada(con, selo)
        from bd_nativo import banco
        assert banco(con).valor("SELECT original_name FROM attachments WHERE entity_id = %s",
                                (selo,)).endswith("_comprovante.pdf")


def test_juntar_com_certidao_guardada_ou_com_dois_arquivos_e_ambos(cg_casa, tmp_path):
    pytest.importorskip("pymupdf")
    db = cg_casa["db"]
    with db.transaction() as con:
        com_certidao = _selo_isento(con, "AVERBA000000G003000000000002")
        dois_arquivos = _selo_isento(con, "AVERBA000000G003000000000003")
        GC.guardar_junto(con, com_certidao, arquivos=[("declaracao.pdf", _pdf("COMPROVANTE"))],
                         certidoes=[("certidao.pdf", _pdf("CERTIDAO"))],
                         pasta=tmp_path, usuario_id=None, agora="t")
        GC.guardar_junto(con, dois_arquivos, arquivos=[("declaracao.pdf", _pdf("COMPROVANTE")),
                                                       ("certidao.pdf", _pdf("CERTIDAO"))],
                         pasta=tmp_path, usuario_id=None, agora="t")
        assert _peca_e_fila(con, com_certidao) == (["AMBOS"], "PRONTO")
        assert _peca_e_fila(con, dois_arquivos) == (["AMBOS"], "PRONTO")
        assert GC.certidao_guardada(con, com_certidao)


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_a_tela_guarda_a_certidao_em_campo_proprio_e_o_selo_fica_pronto(cg_casa_logada):
    pytest.importorskip("pymupdf")
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        selo = _selo_isento(con, "AVERBA000000G003000000000004")
    pagina = c.get("/gratuidades/comprovantes").get_data(as_text=True)
    assert 'name="certidao"' in pagina
    r = c.post(f"/gratuidades/comprovantes/{selo}",
               data={"csrf_token": _token(pagina), "fundamento": "POBREZA_RCPN",
                     "arquivo": (io.BytesIO(_pdf("COMPROVANTE")), "declaracao.pdf"),
                     "certidao": (io.BytesIO(_pdf("CERTIDAO")), "certidao.pdf")},
               content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "1 comprovante(s) guardado(s)" in r and "Cópia da certidão do ato guardada" in r
    assert "Falta a cópia da certidão" not in r
    with db.connect() as con:
        from bd_nativo import banco
        tipos = sorted(x["entity_type"] for x in banco(con).ler(
            "SELECT entity_type FROM attachments WHERE entity_id = %s", (selo,)))
        assert tipos == ["SELO_GRATUIDADE", "SELO_GRATUIDADE_CERTIDAO"]
        assert _peca_e_fila(con, selo) == (["COMPROVANTE", "CERTIDAO"], "PRONTO")


def test_a_tela_avisa_quando_juntou_sem_certidao_e_aceita_a_certidao_depois(cg_casa_logada):
    """Sem travar: o comprovante entra, a tela avisa que falta a certidão, o
    selo vai para «já comprovados» com a marca, e a certidão chega sozinha."""
    pytest.importorskip("pymupdf")
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        selo = _selo_isento(con, "AVERBA000000G003000000000005")
    pagina = c.get("/gratuidades/comprovantes").get_data(as_text=True)
    r = c.post(f"/gratuidades/comprovantes/{selo}",
               data={"csrf_token": _token(pagina), "fundamento": "POBREZA_RCPN", "juntar": "1",
                     "arquivo": (io.BytesIO(_pdf("COMPROVANTE")), "declaracao.pdf")},
               content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "1 comprovante(s) guardado(s)" in r
    assert "Não havia certidão do ato guardada para juntar" in r
    assert "Falta a cópia da certidão do ato deste selo" in r
    assert "falta a certidão do ato" in r                 # a marca em «já comprovados»
    with db.connect() as con:
        assert _peca_e_fila(con, selo) == (["COMPROVANTE"], "FALTA_CERTIDAO")
    r = c.post(f"/gratuidades/comprovantes/{selo}",
               data={"csrf_token": _token(r),
                     "certidao": (io.BytesIO(_pdf("CERTIDAO")), "certidao.pdf")},
               content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "Cópia da certidão do ato guardada" in r and "falta a certidão do ato" not in r
    with db.connect() as con:
        assert _peca_e_fila(con, selo) == (["COMPROVANTE", "CERTIDAO"], "PRONTO")


def test_a_certidao_do_mesmo_envio_nao_entra_duas_vezes_no_juntar(cg_casa_logada):
    """Certidão no campo próprio + «juntar»: a certidão já é peça; juntá-la
    de novo poria as páginas dela duas vezes no pacote do Portal."""
    pymupdf = pytest.importorskip("pymupdf")
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        selo = _selo_isento(con, "AVERBA000000G003000000000006")
    pagina = c.get("/gratuidades/comprovantes").get_data(as_text=True)
    c.post(f"/gratuidades/comprovantes/{selo}",
           data={"csrf_token": _token(pagina), "fundamento": "POBREZA_RCPN", "juntar": "1",
                 "arquivo": (io.BytesIO(_pdf("COMPROVANTE")), "declaracao.pdf"),
                 "certidao": (io.BytesIO(_pdf("CERTIDAO")), "certidao.pdf")},
           content_type="multipart/form-data")
    with db.connect() as con:
        import selo_portal as SP
        pecas = SP.pecas(con, selo)
        assert [p["peca"] for p in pecas] == ["COMPROVANTE", "CERTIDAO"]
        assert pymupdf.open(pecas[0]["stored_path"]).page_count == 1
        assert SP.gratuitos(con)[0]["situacao"] == "PRONTO"

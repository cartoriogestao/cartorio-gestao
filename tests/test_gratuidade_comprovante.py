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

TEXTO_ISENTO = ("Poder Judiciário – TJMA. Selo: AVERBA000000VBKH58VIXU0CLW81, 13/10/2026 12:07:22, "
                "Ato: 14.4.1, Total R$ 43,37 Emol R$ 38,72 Selo Isento, Consulte em https://selo.tjma.jus.br")


def _con():
    con = sqlite3.connect(":memory:")
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


def test_acha_no_proton_pelo_codigo_no_nome(tmp_path):
    (tmp_path / "2026" / "OUTUBRO").mkdir(parents=True)
    (tmp_path / "2026" / "OUTUBRO" / "AVERBA000000XA66PB40MVB00E35.pdf").write_bytes(b"%PDF")
    (tmp_path / "2026" / "DARLENE.pdf").write_bytes(b"%PDF")
    achados = GC.no_proton(["AVERBA000000XA66PB40MVB00E35", "AVERBA000000VBKH58VIXU0CLW81"], tmp_path)
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

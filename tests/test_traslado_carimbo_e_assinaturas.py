"""Traslado de escritura: carimbo completo e assinaturas dos comparecentes.

Pedido 18/09/2026:
  1. o traslado saía só com `Selo: {{ número }}` — precisa do carimbo das
     certidões (QR, emolumentos, link), via `carimbo_da_certidao_odf`;
  2. o 1º traslado precisa das linhas de assinatura de TODOS os comparecentes,
     não só do tabelião/escrevente.
"""
from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from pathlib import Path

import pytest

SENHA = "Senha#12345"
SELO = "ESCINT000000B5L9KK4F2QJ5ZQ95"
TEXTO_DO_SELO = (
    "Poder Judiciário — TJMA. Selo: " + SELO + ", 18/09/2026 09:00:00, "
    "Ato: 13.1, Parte(s): JOAO DA SILVA, "
    "Total R$ 200,00 Emol R$ 178,57 FERC R$ 5,36 "
    "FADEP R$ 7,14 FEMP R$ 7,14 FERRFIS R$ 1,79 "
    "Consulte em https://selo.tjma.jus.br"
)


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _texto_do_odt(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read("content.xml").decode("utf-8")


def _nomes_em_pictures(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return [n for n in zf.namelist() if n.startswith("Pictures/")]


@pytest.fixture()
def serventia(cg_casa):
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    cg_casa["db"].set_settings({
        "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cns": "000000",
        "unit_name": "Cartório Cidade Exemplo",
    })
    login = cg_casa["c"].get("/login").get_data(as_text=True)
    cg_casa["c"].post("/login", data={
        "username": "tabeliao", "password": SENHA, "csrf_token": _token(login),
    }, follow_redirects=True)
    return cg_casa


def _ato_com_selo_e_partes(serventia, *, com_selo=True) -> int:
    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    with con:
        cur = con.execute(
            """INSERT INTO nt_atos(tipo, data, livro, folha, numero_ordem,
                                   situacao, teor, selo, lavrado_nome,
                                   lavrado_titulo, criado_em)
               VALUES ('ESCRITURA','2026-09-18','30','10',1,'LAVRADO',
                       '<p>Saibam quantos este instrumento virem...</p>',
                       ?, 'MARIO EXEMPLO DOS SANTOS', 'Tabelião',
                       '2026-09-18T09:00:00')""",
            (SELO if com_selo else None,))
        ato_id = cur.lastrowid
        con.execute(
            """INSERT INTO nt_ato_partes(
                   ato_id, nome, nome_norm, qualificacao, testemunha, ordem,
                   criado_em)
               VALUES (?, 'JOAO DA SILVA', 'JOAO DA SILVA', 'OUTORGANTE', 0, 1,
                       '2026-09-18T09:00:00')""",
            (ato_id,))
        con.execute(
            """INSERT INTO nt_ato_partes(
                   ato_id, nome, nome_norm, qualificacao, testemunha, ordem,
                   criado_em)
               VALUES (?, 'MARIA SOUZA', 'MARIA SOUZA', 'OUTORGADO', 0, 2,
                       '2026-09-18T09:00:00')""",
            (ato_id,))
        con.execute(
            """INSERT INTO nt_ato_partes(
                   ato_id, nome, nome_norm, qualificacao, testemunha, ordem,
                   criado_em)
               VALUES (?, 'PEDRO TESTEMUNHA', 'PEDRO TESTEMUNHA', NULL, 1, 3,
                       '2026-09-18T09:00:00')""",
            (ato_id,))
        if com_selo:
            # Etiqueta no razão, como a produção guarda (número na coluna,
            # texto completo em sd_selos) — espelha test_certidao_do_ri_*.
            try:
                con.execute(
                    """INSERT INTO sd_selos(numero, texto, tabela, ato_id,
                                            data_geracao, ambiente)
                       VALUES (?, ?, 'nt_atos', ?, '2026-09-18T09:00:00',
                               'PRODUCAO')""",
                    (SELO, TEXTO_DO_SELO, ato_id))
            except sqlite3.Error:
                # Esquema pode variar; etiqueta_do_ato cai no número.
                pass
    con.close()
    return ato_id


def test_modelo_traslado_titulo_unico_sem_escritura_publica_sozinha():
    import notas_web as NW
    assert "titulo_do_instrumento|upper" in NW.MODELO_TRASLADO
    assert "rotulo_tipo|upper" not in NW.MODELO_TRASLADO
    assert NW.titulo_do_instrumento(
        {"tipo": "ESCRITURA", "natureza": "Compra e venda"},
        nome_modelo="Escritura pública de compra e venda de imóvel urbano",
    ) == "Escritura pública de compra e venda de imóvel urbano"


def test_traslado_odt_cabecalho_usa_folha_livro_com_verso(serventia):
    ato_id = _ato_com_selo_e_partes(serventia, com_selo=False)
    resp = serventia["c"].get(f"/notas/atos/{ato_id}/traslado")
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        styles = zf.read("styles.xml").decode("utf-8")
    assert "INT((PAGE-1)/2)+" in styles
    assert 'text:string-value-if-true="v"' in styles
    assert "text:page-adjust" not in styles


def test_modelo_traslado_usa_placeholders_de_selo_e_assinaturas():
    import notas_web as NW
    assert "@@SELO@@" in NW.MODELO_TRASLADO
    assert "<b>Selo:</b>" not in NW.MODELO_TRASLADO
    assert "@@ASSINATURAS@@" in NW.MODELO_TRASLADO
    assert "{{ lavrado_nome }}" not in NW.MODELO_TRASLADO


def test_bloco_de_assinaturas_lista_partes_testemunhas_e_lavrado():
    import notas_teor as NT
    html = NT.bloco_de_assinaturas(
        [
            {"nome": "JOAO", "qualificacao": "OUTORGANTE", "testemunha": 0},
            {"nome": "MARIA", "qualificacao": "OUTORGADO", "testemunha": 0},
            {"nome": "PEDRO", "testemunha": 1},
        ],
        lavrado_nome="MARIO",
        lavrado_titulo="Tabelião",
    )
    assert "JOAO" in html and "OUTORGANTE" in html
    assert "MARIA" in html and "OUTORGADO" in html
    assert "PEDRO" in html and "Testemunha" in html
    assert "MARIO" in html and "Tabelião" in html
    assert html.count("_________________________________") == 4


def test_traslado_invoca_carimbo_da_certidao(serventia, monkeypatch):
    """A rota do traslado pede o carimbo completo — não o número solto."""
    chamadas = []

    import notas_web as NW
    import ri_odt

    original = NW.carimbo_da_certidao_odf

    def _espiar(etiqueta, *, rotulo="SELO DA CERTIDÃO", prefixo="qr-selo-certidao"):
        chamadas.append({"etiqueta": etiqueta, "rotulo": rotulo, "prefixo": prefixo})
        return original(etiqueta, rotulo=rotulo, prefixo=prefixo)

    # A rota faz rom ri_odt import carimbo_da_certidao_odf — o nome mora em
    # notas_web; remendar só ri_odt não alcança a chamada.
    monkeypatch.setattr(NW, "carimbo_da_certidao_odf", _espiar)

    ato_id = _ato_com_selo_e_partes(serventia)
    resp = serventia["c"].get(f"/notas/atos/{ato_id}/traslado")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:500]
    assert chamadas, "carimbo_da_certidao_odf não foi chamado"
    assert chamadas[0]["rotulo"] == "SELO DA ESCRITURA"
    assert SELO in (chamadas[0]["etiqueta"] or "")

    xml = _texto_do_odt(resp.data)
    assert "SELO DA ESCRITURA" in xml or SELO in xml
    assert "Total R$" in xml or "qr-selo-traslado" in xml or any(
        "qr-selo-traslado" in n for n in _nomes_em_pictures(resp.data))
    # Não volta o rótulo pobre "Selo:" + número sozinho como único vestígio.
    assert not re.search(r">Selo:</[^>]*>\s*" + re.escape(SELO), xml)


def test_traslado_traz_assinaturas_de_todos_os_comparecentes(serventia):
    ato_id = _ato_com_selo_e_partes(serventia, com_selo=False)
    resp = serventia["c"].get(f"/notas/atos/{ato_id}/traslado")
    assert resp.status_code == 200
    xml = _texto_do_odt(resp.data)
    assert "JOAO DA SILVA" in xml
    assert "OUTORGANTE" in xml
    assert "MARIA SOUZA" in xml
    assert "OUTORGADO" in xml
    assert "PEDRO TESTEMUNHA" in xml
    assert "Testemunha" in xml
    assert "MARIO EXEMPLO DOS SANTOS" in xml
    assert xml.count("_________________________________") >= 4


def test_traslado_sem_selo_nao_inventa_carimbo(serventia):
    ato_id = _ato_com_selo_e_partes(serventia, com_selo=False)
    resp = serventia["c"].get(f"/notas/atos/{ato_id}/traslado")
    assert resp.status_code == 200
    xml = _texto_do_odt(resp.data)
    assert "SELO DA ESCRITURA" not in xml
    pics = _nomes_em_pictures(resp.data)
    assert not any("qr-selo-traslado" in n for n in pics)



def test_modelo_termo_livro_usa_placeholders_sem_frase_de_traslado():
    import notas_web as NW
    assert "@@TEOR@@" in NW.MODELO_TERMO_LIVRO
    assert "@@SELO@@" in NW.MODELO_TERMO_LIVRO
    assert "@@ASSINATURAS@@" in NW.MODELO_TERMO_LIVRO
    assert "@@BRASAO@@" in NW.MODELO_TERMO_LIVRO
    assert "{{ sv.unit_name }}" in NW.MODELO_TERMO_LIVRO
    assert "Traslado extraído" not in NW.MODELO_TERMO_LIVRO
    assert "ANOTAÇÕES À MARGEM" not in NW.MODELO_TERMO_LIVRO
    # Cabeçalho da folha do livro = cabeçalho do traslado (pedido 18/09/2026).
    assert (NW.MODELO_TERMO_LIVRO.split("@@TEOR@@", 1)[0]
            == NW.MODELO_TRASLADO.split("@@TEOR@@", 1)[0])


def test_tela_do_ato_lancado_mostra_termo_do_livro_e_traslado(serventia):
    ato_id = _ato_com_selo_e_partes(serventia, com_selo=False)
    html = serventia["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert "Termo do livro (.odt)" in html
    assert "Traslado (.odt)" in html
    assert f"/notas/atos/{ato_id}/termo-livro" in html
    assert f"/notas/atos/{ato_id}/traslado" in html


def test_termo_livro_invoca_carimbo_compacto(serventia, monkeypatch):
    """A rota do termo do livro pede o carimbo compacto — sem QR."""
    chamadas = []

    import notas_web as NW

    original = NW.carimbo_compacto_odf

    def _espiar(selo_texto, rotulo="SELO DIGITAL DO TJMA", **kwargs):
        chamadas.append({"etiqueta": selo_texto, "rotulo": rotulo, **kwargs})
        return original(selo_texto, rotulo=rotulo, **kwargs)

    monkeypatch.setattr(NW, "carimbo_compacto_odf", _espiar)

    ato_id = _ato_com_selo_e_partes(serventia)
    resp = serventia["c"].get(f"/notas/atos/{ato_id}/termo-livro")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:500]
    assert chamadas, "carimbo_compacto_odf não foi chamado"
    assert chamadas[0]["rotulo"] == "SELO DA ESCRITURA"
    assert SELO in (chamadas[0]["etiqueta"] or "")

    xml = _texto_do_odt(resp.data)
    assert "SELO DA ESCRITURA" in xml or SELO in xml
    # Sem QR embutido no pacote (carimbo compacto não gera Pictures/qr-*).
    pics = _nomes_em_pictures(resp.data)
    assert not any("qr-selo" in n for n in pics)
    assert any(n.endswith("brasao.jpg") for n in pics)
    assert "Traslado extraído" not in xml


def test_termo_livro_traz_assinaturas_alinhadas_ao_traslado(serventia):
    ato_id = _ato_com_selo_e_partes(serventia, com_selo=False)
    resp_t = serventia["c"].get(f"/notas/atos/{ato_id}/termo-livro")
    resp_tr = serventia["c"].get(f"/notas/atos/{ato_id}/traslado")
    assert resp_t.status_code == 200 and resp_tr.status_code == 200
    xml_t = _texto_do_odt(resp_t.data)
    xml_tr = _texto_do_odt(resp_tr.data)
    for nome in ("JOAO DA SILVA", "MARIA SOUZA", "PEDRO TESTEMUNHA",
                 "MARIO EXEMPLO DOS SANTOS"):
        assert nome in xml_t
        assert nome in xml_tr
    assert xml_t.count("_________________________________") >= 4
    assert (xml_t.count("_________________________________")
            == xml_tr.count("_________________________________"))


def test_termo_livro_sem_selo_nao_inventa_carimbo(serventia):
    ato_id = _ato_com_selo_e_partes(serventia, com_selo=False)
    resp = serventia["c"].get(f"/notas/atos/{ato_id}/termo-livro")
    assert resp.status_code == 200
    xml = _texto_do_odt(resp.data)
    assert "SELO DA ESCRITURA" not in xml

"""As telas novas do caminho da CRA — 14/10/2026.

«Trazer e conferir»: a remessa trazida pela API cai na MESMA conferência do
upload (antes, só baixava o arquivo cru). «Enviar à CRA»: o retorno gerado sobe
por um botão (antes, só se baixava). A rede é simulada.
"""
from __future__ import annotations

from pathlib import Path

from test_protesto_aviso_web import _con, _token, s  # noqa: F401

EXEMPLO = Path(__file__).parent / "cra_remessa_exemplo.txt"


def test_a_remessa_da_cra_vai_direto_a_conferencia_e_nao_grava(s, monkeypatch):
    import cra21_web as CRAW
    monkeypatch.setattr(CRAW, "_trazer",
                        lambda qual, nome, amb, com_imagem=False:
                        EXEMPLO.read_text(encoding="latin-1"))
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    assert "Baixar todas e conferir" in tela
    html = s["c"].post("/protesto/remessas/da-cra",
                       data={"csrf_token": _token(tela), "o_que": "remessa",
                             "nome": "B2371410.261"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Receber" in html                       # é a tela da conferência
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM pt_remessas").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM pt_titulos").fetchone()[0] == 0


def test_so_remessa_e_pendentes_vao_a_conferencia(s, monkeypatch):
    import cra21_web as CRAW
    monkeypatch.setattr(CRAW, "_trazer", lambda *a, **k: "x")
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    html = s["c"].post("/protesto/remessas/da-cra",
                       data={"csrf_token": _token(tela), "o_que": "desistencias",
                             "nome": "D2371410.261"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Só a remessa do dia e as pendentes" in html


def test_a_recusa_da_cra_volta_como_frase_e_nao_500(s, monkeypatch):
    import cra21_api as API
    import cra21_web as CRAW

    def recusa(*a, **k):
        raise API.CraRecusou("A CRA recusou (código 0003): sem remessa pendente")
    monkeypatch.setattr(CRAW, "_trazer", recusa)
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    r = s["c"].post("/protesto/remessas/da-cra",
                    data={"csrf_token": _token(tela), "o_que": "remessa",
                          "nome": "B2371410.261"}, follow_redirects=True)
    assert r.status_code == 200
    assert "0003" in r.get_data(as_text=True)


def test_o_retorno_tem_o_botao_enviar_a_cra(s, monkeypatch):
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
                   numero_da_remessa, nome_arquivo, conteudo, gerado_em)
               VALUES ('SDTBFORTP','237','2026-10-14',1,'R2371410.261','x',
                       '2026-10-14T10:00:00')""")
    rid = con.execute("SELECT MAX(id) FROM pt_retornos").fetchone()[0]
    tela = s["c"].get("/protesto/retornos").get_data(as_text=True)
    assert f"/protesto/retornos/{rid}/enviar" in tela

    import protesto_cra_envio as ENV
    monkeypatch.setattr(ENV, "enviar_arquivo",
                        lambda transacao, retorno_id, **k:
                        {"nome_arquivo": "R2371410.261", "codigo": "0000",
                         "operacao": "Retorno"})
    html = s["c"].post(f"/protesto/retornos/{rid}/enviar",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert "entrou na CRA" in html and "0000" in html


def test_todas_as_remessas_sem_numero_vao_a_conferencia_sem_gravar(s, monkeypatch):
    import re
    import cra21_web as CRAW
    chamadas = []

    def trazer(qual, nome, amb, com_imagem=False):
        chamadas.append((qual, nome))
        return EXEMPLO.read_text(encoding="latin-1")

    monkeypatch.setattr(CRAW, "_trazer", trazer)
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    form = re.search(r'<form[^>]+action="/protesto/remessas/da-cra".*?</form>',
                     tela, re.S).group()
    assert 'name="o_que" value="pendentes"' in form
    assert 'name="nome"' not in form
    r = s["c"].post("/protesto/remessas/da-cra", data={
        "csrf_token": _token(tela), "o_que": "pendentes"}, follow_redirects=True)
    assert r.status_code == 200
    assert chamadas == [("pendentes", "")]
    assert "Receber" in r.get_data(as_text=True)
    with _con(s) as con:
        assert con.execute("SELECT COUNT(*) FROM pt_remessas").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM pt_titulos").fetchone()[0] == 0


def test_aviso_realista_da_api_aparece_sem_pedir_raiz_remessa(s, monkeypatch):
    import cra21_api as API
    monkeypatch.setattr(API, '_bater', lambda *a, **kw:
        '<return>&lt;?xml version="1.0"?&gt;&lt;relatorio&gt;'
        '&lt;codigo&gt;0003&lt;/codigo&gt;&lt;ocorrencia&gt;'
        'SEM REMESSAS PENDENTES&lt;/ocorrencia&gt;&lt;/relatorio&gt;</return>')
    tela = s['c'].get('/protesto/remessas').get_data(as_text=True)
    r = s['c'].post('/protesto/remessas/da-cra', data={
        'csrf_token': _token(tela), 'o_que': 'pendentes'}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert '0003' in html and 'SEM REMESSAS PENDENTES' in html
    assert 'A raiz esperada' not in html
    with _con(s) as con:
        assert con.execute('SELECT COUNT(*) FROM pt_remessas').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 0

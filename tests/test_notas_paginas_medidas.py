"""
As páginas do ato das Notas se MEDEM no termo, e não se perguntam.

Pedido do oficial em 07/10/2026: «consegue resolver o problema do escrevente
precisar dizer quantas páginas vai ter o ato? isso é uma informação confusa,
deve ter outra forma de garantir que o ato termine no verso para não continuar
o próximo no verso do anterior».

O QUE ESTES TESTES GUARDAM
    1. lançar sem o campo usa a medição do termo, e não a estimativa;
    2. a medição que falha NÃO lança — devolve a tela pedindo o número à mão;
    3. o Termo do livro sai fechando as folhas reservadas: o verso que sobra
       vai no fim, já inutilizado, e o arquivo tem número PAR de páginas;
    4. termo que passou do reservado NÃO sai — imprimi-lo escreveria na folha
       do ato seguinte;
    5. contra o LibreOffice de verdade (pula se não houver): o termo baixado
       tem exatamente as páginas que o lançamento reservou.
"""
from __future__ import annotations

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


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "cliente": c, "banco": cg_casa["banco"],
               "db": cg_casa["db"], "dados": cg_casa["dados"]}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


class _Medida:
    """Troca a medição do LibreOffice por um número escolhido pelo teste."""

    def __init__(self, app):
        self.app = app
        self.original = app.extensions["notas_medir_paginas"]
        self.paginas = None
        self.erro = None
        self.chamadas = 0

    def __call__(self, odt):
        self.chamadas += 1
        if self.erro:
            raise self.erro
        return self.paginas


@pytest.fixture()
def medida(serventia):
    m = _Medida(serventia["app"])
    serventia["app"].extensions["notas_medir_paginas"] = m
    yield m
    serventia["app"].extensions["notas_medir_paginas"] = m.original


def tela(s, caminho):
    return s["cliente"].get(caminho).get_data(as_text=True)


def ato(s, ato_id):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    linha = dict(con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone())
    con.close()
    return linha


def abrir_com_teor(s, teor="<p>teor do ato</p>"):
    html = tela(s, "/notas/atos/novo")
    s["cliente"].post("/notas/atos/novo",
                      data={"csrf_token": _token(html), "tipo": "ESCRITURA",
                            "interessado": "MARIA DAS DORES"},
                      follow_redirects=True)
    con = sqlite3.connect(s["banco"])
    ato_id = con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0]
    con.close()
    postar(s, ato_id, acao="teor", teor=teor)
    return int(ato_id)


def postar(s, ato_id, **dados):
    dados.setdefault("csrf_token", _token(tela(s, f"/notas/atos/{ato_id}")))
    if dados.get("acao") == "lancar":
        dados.setdefault("codigo_tj", "13.2")
        # A trava da CENSEC (09/10/2026) — ver `notas_pronto_para_a_censec`.
        from notas_pronto_para_a_censec import preparar
        preparar(s["banco"], ato_id)
    return s["cliente"].post(f"/notas/atos/{ato_id}", data=dados,
                             follow_redirects=True)


def texto_do_odt(dados: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        return z.read("content.xml").decode("utf-8")


# ------------------------------------------------------------- o lançamento

def test_a_tela_nao_pergunta_mais_quantas_paginas(serventia):
    ato_id = abrir_com_teor(serventia)
    html = tela(serventia, f"/notas/atos/{ato_id}")
    assert 'name="paginas"' not in html
    assert "conta sozinho" in html


def test_lancar_sem_o_campo_usa_a_medicao_do_termo(serventia, medida):
    medida.paginas = 3
    ato_id = abrir_com_teor(serventia)
    postar(serventia, ato_id, acao="lancar")
    a = ato(serventia, ato_id)
    assert medida.chamadas == 1
    assert a["situacao"] != "EM_LAVRATURA"
    # Três páginas escritas: duas folhas, e o texto termina na FRENTE da 2.
    assert a["folhas"] == 2 and a["paginas"] == 4
    assert a["verso_final"] == 0
    assert a["folha"] == "1" and a["folha_final"] == "2"


def test_numero_par_de_paginas_termina_no_verso(serventia, medida):
    medida.paginas = 4
    ato_id = abrir_com_teor(serventia)
    postar(serventia, ato_id, acao="lancar")
    a = ato(serventia, ato_id)
    assert a["folhas"] == 2 and a["verso_final"] == 1
    assert a["folha_final"] == "2v"


def test_medicao_que_falha_nao_lanca_e_pede_o_numero(serventia, medida):
    import impressao_pdf as IPDF
    medida.erro = IPDF.PdfError("o LibreOffice não respondeu")
    ato_id = abrir_com_teor(serventia)
    resposta = postar(serventia, ato_id, acao="lancar")
    html = resposta.get_data(as_text=True)
    a = ato(serventia, ato_id)
    assert a["situacao"] == "EM_LAVRATURA" and a["termo"] is None
    assert "NÃO lançado" in html
    assert 'name="paginas"' in html            # o campo volta, só agora

    # E com o número contado no papel, lança sem medir de novo.
    medida.erro = None
    medida.chamadas = 0
    postar(serventia, ato_id, acao="lancar", paginas="3")
    assert medida.chamadas == 0
    assert ato(serventia, ato_id)["folhas"] == 2


# ------------------------------------------------------------- o termo

def test_o_termo_traz_o_verso_ja_inutilizado(serventia, medida):
    medida.paginas = 3
    ato_id = abrir_com_teor(serventia)
    postar(serventia, ato_id, acao="lancar")
    resp = serventia["cliente"].get(f"/notas/atos/{ato_id}/termo-livro")
    assert resp.status_code == 200
    xml = texto_do_odt(resp.data)
    assert "FACE INUTILIZADA" in xml
    assert "FOLHA 2v" in xml
    assert 'style:name="P-nova-pagina"' in xml   # a face abre página nova


def test_o_termo_que_ja_fecha_em_par_nao_ganha_face(serventia, medida):
    medida.paginas = 4
    ato_id = abrir_com_teor(serventia)
    postar(serventia, ato_id, acao="lancar")
    resp = serventia["cliente"].get(f"/notas/atos/{ato_id}/termo-livro")
    assert "FACE INUTILIZADA" not in texto_do_odt(resp.data)


def test_termo_maior_que_o_reservado_nao_sai(serventia, medida):
    medida.paginas = 2
    ato_id = abrir_com_teor(serventia)
    postar(serventia, ato_id, acao="lancar")     # reservou uma folha
    medida.paginas = 3                           # e o termo cresceu
    resp = serventia["cliente"].get(f"/notas/atos/{ato_id}/termo-livro",
                                    follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert resp.mimetype == "text/html"
    assert "NÃO imprima" in html


# ------------------------------------------------------------- o LibreOffice

def test_contra_o_libreoffice_o_termo_fecha_as_folhas_reservadas(serventia):
    import impressao_pdf as IPDF
    if IPDF.onde_esta_o_conversor() is None:
        pytest.skip("sem LibreOffice nesta máquina")
    paragrafo = ("<p>" + "Texto da escritura lavrada para medir a página do livro. "
                 * 12 + "</p>")
    # Medido em 07/10/2026 nesta máquina: 3 parágrafos dão 1 página, 9 dão 2,
    # 12 dão 3. Os três cobrem os dois lados — o texto que termina na frente
    # (e o termo ganha o verso inutilizado) e o que já termina no verso.
    versos = set()
    for repeticoes in (3, 9, 12):
        ato_id = abrir_com_teor(serventia, paragrafo * repeticoes)
        postar(serventia, ato_id, acao="lancar")
        a = ato(serventia, ato_id)
        assert a["situacao"] != "EM_LAVRATURA", "a medição real não lançou"
        resp = serventia["cliente"].get(f"/notas/atos/{ato_id}/termo-livro")
        assert resp.status_code == 200 and resp.mimetype.endswith("text")
        paginas = IPDF.paginas_do_odt(resp.data)
        assert paginas % 2 == 0, f"{repeticoes}: termo com {paginas} páginas"
        assert paginas == a["folhas"] * 2, (repeticoes, paginas, a["folhas"])
        versos.add(a["verso_final"])
    # Se a fonte ou a margem mudarem e os três caírem do mesmo lado, este
    # teste deixa de provar o verso inutilizado — e diz isso em vez de calar.
    assert versos == {0, 1}, f"só um lado foi exercitado: {versos}"


def test_o_botao_de_lancar_vem_depois_do_selo_e_do_arquivamento(serventia):
    # Ordem do oficial em 07/10/2026: «a opção de inclusão do selo de
    # arquivamento deve vir antes do botão de lavratura do ato».
    ato_id = abrir_com_teor(serventia)
    html = tela(serventia, f"/notas/atos/{ato_id}")
    botao = html.index('value="lancar"')
    assert html.index('name="gerar_arquivamento"') < botao
    assert html.index("Revisar com IA") < botao if "Revisar com IA" in html else True

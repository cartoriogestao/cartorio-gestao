"""
A face em branco sai impressa ja inutilizada.

O PEDIDO
    "Não precisar inutilizar folha." Dois caminhos: fazer o branco não
    acontecer, ou fazer a inutilização não ser trabalho. O primeiro tem teto —
    nenhum ato termina na última linha da página, então mexer na tipografia
    muda o branco de lugar, não o elimina. Estes testes cobrem o segundo.

    O art. 795, § 2º do Código de Normas manda que a escrituração seja seguida,
    sem claros ou espaços em branco. A face que sobra sai riscada, com o dizer
    e a linha de assinatura, no mesmo papel.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_inutilizacao as NI               # noqa: E402

SENHA = "Senha#12345"
SV = {"serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


# ------------------------------------------------------------- as faces

def test_a_face_em_branco_e_o_verso_da_ultima_folha():
    assert NI.faces_do_ato({"verso_final": 0, "folha_final_num": 14}) == ["14v"]


def test_terminando_no_verso_nao_sobra_face():
    assert NI.faces_do_ato({"verso_final": 1, "folha_final_num": 14}) == []


def test_ato_do_acervo_sem_folha_numerica_nao_gera_face():
    assert NI.faces_do_ato({"verso_final": 0, "folha_final_num": None,
                            "folha_final": None}) == []


def test_as_folhas_do_livro_encerrado_rendem_duas_faces_cada():
    faces = NI.faces_do_livro({"folhas_inutilizadas": "181-183"})
    assert faces == ["181", "181v", "182", "182v", "183", "183v"]


def test_livro_sem_folhas_sobrando_nao_gera_face():
    assert NI.faces_do_livro({"folhas_inutilizadas": None}) == []
    assert NI.faces_do_livro({"folhas_inutilizadas": ""}) == []
    assert NI.faces_do_livro({"folhas_inutilizadas": "lixo"}) == []


# ------------------------------------------------------------- o dizer

def test_o_dizer_de_uma_face_nomeia_a_face_o_livro_e_o_fundamento():
    texto = NI.dizer(["14v"], "ESCRITURA", "3", SV, "17 de agosto de 2026")
    assert "INUTILIZADA a face 14v" in texto
    assert "Livro de Escrituras n. 3" in texto
    assert "art. 795" in texto and "§ 2º" in texto
    assert "nada mais podendo nela ser lançado" in texto
    assert "MARIO EXEMPLO DOS SANTOS" in texto


def test_o_dizer_de_varias_faces_vai_para_o_plural():
    texto = NI.dizer(["181", "181v", "182", "182v"], "PROCURACAO", "9", SV, "hoje")
    assert "Ficam INUTILIZADAS as faces 181 a 182v" in texto
    assert "nelas ser lançado" in texto


def test_a_face_impressa_leva_o_traco():
    html = NI.html_da_face("14v", "ESCRITURA", "3", SV, "hoje", "o dizer")
    assert html.count("/" * 78) == NI.LINHAS_DE_RISCO
    assert "FACE INUTILIZADA" in html
    assert "FOLHA 14v" in html


# ------------------------------------------------------------- a entrelinha

def test_texto_que_termina_no_verso_nao_precisa_de_ajuste():
    for pares in (2, 4, 10):
        assert NI.sugerir_entrelinha(pares)["precisa"] is False


def test_o_ajuste_so_cabe_na_banda_quando_o_ato_e_longo():
    """A conta que decide: quanto o texto teria de crescer.

    Ato de 3 páginas precisaria de +33% — corpo ilegível. Ato de 21 precisa de
    +5%, e cabe nos 10% autorizados.
    """
    curto = NI.sugerir_entrelinha(3)
    assert curto["precisa"] and not curto["cabe_na_banda"]
    assert "não cabe" in curto["motivo"]

    longo = NI.sugerir_entrelinha(21)
    assert longo["precisa"] and longo["cabe_na_banda"]
    assert longo["entrelinha_sugerida"] <= 1.5 * (1 + NI.BANDA_ENTRELINHA) + 1e-9


def test_a_banda_e_de_dez_por_cento_e_so_de_entrelinha():
    assert NI.BANDA_ENTRELINHA == 0.10
    sugestao = NI.sugerir_entrelinha(41)
    assert sugestao["banda"] == 10
    assert "entrelinha" in sugestao["motivo"]
    # Nada de corpo de letra: a sugestão não fala em fonte.
    assert "corpo" not in sugestao["motivo"]
    assert "fonte" not in sugestao["motivo"]


def test_a_sugestao_diz_que_nao_e_medicao():
    assert NI.sugerir_entrelinha(3)["medido"] is False


# ------------------------------------------------------------- pelas telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa['app']
    caminho = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "cliente": c, "banco": caminho,
               "db": cg_casa["db"], "dados": dados}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def lavrar(s, paginas):
    html = s["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    s["cliente"].post("/notas/atos/novo",
                      data={"csrf_token": _token(html), "tipo": "ESCRITURA"},
                      follow_redirects=True)
    con = sqlite3.connect(s["banco"])
    ato_id = con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0]
    con.close()
    # A trava da CENSEC (09/10/2026) — ver `notas_pronto_para_a_censec`.
    from notas_pronto_para_a_censec import preparar
    preparar(s["banco"], ato_id)
    for dados in ({"acao": "teor", "teor": "<p>teor do ato</p>"},
                  {"acao": "lancar", "paginas": str(paginas),
                   "codigo_tj": "13.2"}):
        pagina = s["cliente"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
        dados["csrf_token"] = _token(pagina)
        s["cliente"].post(f"/notas/atos/{ato_id}", data=dados, follow_redirects=True)
    return ato_id


def test_o_botao_da_face_inutilizada_aparece_so_quando_sobra_verso(serventia):
    impar = lavrar(serventia, 3)
    par = lavrar(serventia, 4)
    tela_impar = serventia["cliente"].get(f"/notas/atos/{impar}").get_data(as_text=True)
    tela_par = serventia["cliente"].get(f"/notas/atos/{par}").get_data(as_text=True)
    assert "já inutilizada" in tela_impar
    assert "já inutilizada" not in tela_par


def test_a_face_sai_em_odt_com_o_traco_e_o_dizer(serventia):
    ato_id = lavrar(serventia, 3)
    resposta = serventia["cliente"].get(f"/notas/atos/{ato_id}/inutilizacao")
    assert resposta.status_code == 200
    assert resposta.mimetype == "application/vnd.oasis.opendocument.text"
    conteudo = zipfile.ZipFile(BytesIO(resposta.data)).read("content.xml").decode()
    assert "FACE INUTILIZADA" in conteudo
    assert "art. 795" in conteudo
    assert "/" * 40 in conteudo
    assert "2v" in conteudo


def test_ato_que_termina_no_verso_recusa_a_impressao(serventia):
    ato_id = lavrar(serventia, 4)
    resposta = serventia["cliente"].get(f"/notas/atos/{ato_id}/inutilizacao",
                                        follow_redirects=True)
    corpo = resposta.get_data(as_text=True)
    assert "não deixou face em branco" in corpo
    assert resposta.mimetype == "text/html"


def test_as_folhas_do_livro_encerrado_saem_todas_de_uma_vez(serventia):
    """Livro de 4 folhas, ato de 3 folhas: encerra deixando 3-4 inutilizadas."""
    html = serventia["cliente"].get("/notas/livros").get_data(as_text=True)
    serventia["cliente"].post("/notas/livros",
                              data={"csrf_token": _token(html), "acao": "abrir",
                                    "tipo": "ESCRITURA", "folhas": "4"},
                              follow_redirects=True)
    lavrar(serventia, 4)      # folhas 1-2
    lavrar(serventia, 5)      # precisa de 3: encerra o livro 1, vai para o 2

    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    livro = con.execute("SELECT * FROM nt_livros WHERE numero='1'").fetchone()
    con.close()
    assert livro["folhas_inutilizadas"] == "3-4"

    tela = serventia["cliente"].get("/notas/livros").get_data(as_text=True)
    assert "imprimir as folhas inutilizadas" in tela

    resposta = serventia["cliente"].get(f"/notas/livros/{livro['id']}/inutilizacao")
    conteudo = zipfile.ZipFile(BytesIO(resposta.data)).read("content.xml").decode()
    for face in ("FOLHA 3", "FOLHA 3v", "FOLHA 4", "FOLHA 4v"):
        assert face in conteudo, face
    assert "Ficam INUTILIZADAS as faces 3 a 4v" in conteudo


def test_a_impressao_da_face_fica_na_auditoria(serventia):
    ato_id = lavrar(serventia, 3)
    serventia["cliente"].get(f"/notas/atos/{ato_id}/inutilizacao")
    con = sqlite3.connect(serventia["banco"])
    linha = con.execute("""SELECT details FROM audit_logs
                           WHERE action='NT_INUTILIZACAO' ORDER BY id DESC LIMIT 1"""
                        ).fetchone()
    con.close()
    assert linha and "2v" in linha[0]

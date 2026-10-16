"""O ato que está dentro do texto da ficha, e o número que ele manda.

O RELATO DO OFICIAL foi **«AV-28 aparecendo no teor de ficha do acervo»**, e
parecia coisa de layout. Não era.

O QUE SE MEDIU EM 28/08/2026
    Nas fichas que vieram do E-Ofício os atos moram **dentro do texto** da
    matrícula — `AV-28/1.490:-`, `R-33/314:-` — e não como linhas em `ri_atos`.
    São **1.052 das 1.508** matrículas com teor, e em **756** o texto passa à
    frente da tabela.

    O sistema calcula o próximo número com `MAX(numero)+1` sobre `ri_atos`.

E AQUI EU QUASE EXAGEREI O TAMANHO DO PROBLEMA
    Cheguei a dizer ao oficial que eram 752 fichas em que o ato novo nasceria
    com número repetido. Fui medir o `tipo_ficha` antes de deixar a frase de
    pé: **743 delas são ACERVO**, e ali o sistema **já exigia o número à mão**
    e recusava lavrar sem ele. O silêncio era só nas **13 ESTRUTURADAS**, que
    são as únicas em que ele numera sozinho — na matrícula 314 sairia R-15 com
    a ficha em R-35.

    Treze e não setecentos. Continuam sendo treze registros que sairiam com
    número já usado, sem ninguém digitar nada — mas **dado cru não é resposta;
    a resposta é o que a função devolve**, e a função já se protegia em 98%
    dos casos.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_numeros_do_teor as NUMT

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(con, *, numero="314", teor="", tipo_ficha="ESTRUTURADA",
               atos=()):
    from ri_schema import hash_ato
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, teor, criado_em)
           VALUES (?, '2', '2', 'ATIVA', ?, ?, '2026-08-28T09:00')""",
        (numero, tipo_ficha, teor))
    mid = int(cur.lastrowid)
    anterior = None
    for tipo, n in atos:
        h = hash_ato(numero, tipo, n, "2026-08-01", "x", anterior)
        con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
                   teor, teor_formato, cancelado, acervo, origem,
                   hash_ato, hash_anterior, lavrado_em)
               VALUES (?,?,?, '2026-08-01', 'x', 'texto', 0, 0, 'MANUAL',
                       ?, ?, '2026-08-01T09:00')""",
            (mid, tipo, n, h, anterior))
        anterior = h
    return mid


# ------------------------------------------- ler o que está escrito


def test_acha_o_ato_que_o_texto_atribui_a_esta_ficha():
    citados = NUMT.citados_no_teor(
        "314", "<p>… sob nº R-33/314. Cidade Exemplo, 04 de maio …</p>")
    assert [c["rotulo"] for c in citados] == ["R-33"]
    assert NUMT.maior_citado("314", "R-33/314 e antes R-12/314") == 33


def test_o_ponto_do_milhar_nao_separa_as_fichas():
    """A ficha 1490 se escreve `1.490` no texto e `1490` na coluna."""
    assert NUMT.maior_citado("1490", "sob nº AV-28/1.490:-") == 28
    assert NUMT.maior_citado("3236", "R-01/3.236. (CON…") == 1


def test_o_ato_de_OUTRA_ficha_nao_conta_e_isso_e_o_que_faz_valer():
    """O teor das fichas antigas cita atos de outras matrículas o tempo todo —
    «Transcrita neste Registro no Lº 2-C, fls. 16 sob nº R-1/503». Contar
    aquele `R-1` inflaria a numeração com o passado de outro imóvel.

    Conferido contra o acervo real: a matrícula 1904, que traz essa frase,
    devolve **nenhum** ato próprio."""
    teor = "Transcrita neste Registro no Lº 2-C, fls. 16 sob nº R-1/503 em 22-05-80."
    assert NUMT.citados_no_teor("1904", teor) == []
    assert NUMT.maior_citado("1904", teor) == 0


def test_rotulo_sem_a_barra_nao_conta():
    """`AV-3` solto não diz de qual ficha é. Deixar de achar é melhor que achar
    errado, porque este número vira o número de um registro."""
    assert NUMT.maior_citado("314", "conforme AV-3 desta serventia") == 0


def test_o_trecho_sai_sem_as_marcas_de_formatacao():
    """O teor do acervo é HTML. Mostrar `<span style=…>` a quem confere esconde
    a frase dentro do código dela."""
    citados = NUMT.citados_no_teor(
        "314", '<span style="font-weight:bold;">R-33/314</span> em maio')
    assert "<span" not in citados[0]["trecho"]
    assert "R-33/314" in citados[0]["trecho"]


# ------------------------------------------- o piso


def test_o_piso_e_o_maior_dos_dois(casa):
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="314", teor="sob nº R-33/314.",
                         atos=(("R", 1), ("AV", 14)))
    piso = NUMT.piso_do_proximo(_con(casa), mid)
    assert piso["em_atos"] == 14
    assert piso["no_teor"] == 33
    assert piso["proximo"] == 34
    assert piso["divergente"] is True


def test_sem_divergencia_o_piso_e_o_de_sempre(casa):
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="4010", teor="", atos=(("R", 1), ("AV", 2)))
    piso = NUMT.piso_do_proximo(_con(casa), mid)
    assert piso["proximo"] == 3
    assert piso["divergente"] is False


def test_o_piso_so_calcula_e_nao_grava(casa):
    """Toda função de contador desta casa tem `consumir=False`."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="314", teor="R-33/314")
    antes = _con(casa).execute("SELECT COUNT(*) c FROM ri_atos").fetchone()["c"]
    NUMT.piso_do_proximo(_con(casa), mid)
    NUMT.piso_do_proximo(_con(casa), mid)
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM ri_atos").fetchone()["c"] == antes


# ------------------------------------------- o que o módulo NÃO faz


def test_o_modulo_nao_cria_ato_a_partir_do_texto():
    """Ler o texto e inserir linhas em `ri_atos` seria fabricar atos com data,
    natureza e conteúdo adivinhados — e ainda pô-los na corrente de hash, que
    existe justamente para provar que nenhum ato foi inventado."""
    codigo = (RAIZ / "ri_numeros_do_teor.py").read_text(encoding="utf-8")
    assert "INSERT INTO" not in codigo
    assert "UPDATE " not in codigo
    assert "DELETE " not in codigo
    publicos = [n for n in dir(NUMT) if not n.startswith("_")]
    for proibido in ("criar", "lavrar", "importar", "gravar", "corrigir"):
        assert not [n for n in publicos if proibido in n.lower()], proibido


# ------------------------------------------- a numeração respeita o piso


def test_a_ficha_de_acervo_recebe_numero_manual_acima_do_papel(casa):
    """Abaixo de 4.015 a pessoa informa o número conforme o livro físico."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="314", tipo_ficha="ACERVO",
                         teor="… sob nº R-33/314. Cidade Exemplo …",
                         atos=(("R", 1), ("AV", 14)))
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["cliente"].post(f"/registro-imoveis/{mid}/atos", data={
        "csrf_token": _token(html), "tipo": "AV", "numero": "34",
        "natureza_titulo": "Averbação do acervo",
        "teor": "<p>a averbação nova</p>", "data_ato": "2026-08-28"},
        follow_redirects=True)
    novo = _con(casa).execute(
        """SELECT numero FROM ri_atos WHERE matricula_id=?
            ORDER BY id DESC LIMIT 1""", (mid,)).fetchone()["numero"]
    assert novo == 34, f"o ato saiu com o número {novo}, e a ficha já traz R-33"


def test_o_numero_ja_escrito_na_ficha_e_recusado_com_a_frase(casa):
    """A recusa que existia olhava só `ri_atos`. Era aqui que os 756 casos
    passavam: o número estava livre na tabela e ocupado no papel."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="1490", tipo_ficha="ACERVO",
                         teor="… sob nº AV-28/1.490:- Cidade Exemplo …")
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = casa["cliente"].post(f"/registro-imoveis/{mid}/atos", data={
        "csrf_token": _token(html), "tipo": "AV", "numero": "28",
        "teor": "<p>outra averbação</p>", "data_ato": "2026-08-28"},
        follow_redirects=True)
    junto = " ".join(r.get_data(as_text=True).split())
    assert "já está usado nesta matrícula" in junto
    assert "AV-28" in junto
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM ri_atos WHERE matricula_id=?",
        (mid,)).fetchone()["c"] == 0


# ------------------------------------------- a tela


def test_a_ficha_diz_o_numero_certo_e_de_onde_o_tirou(casa):
    """A tela não dizia qual era o número certo, e quem digitava tinha de ir ao
    papel. Agora ela diz — e mostra a frase, para a pessoa poder discordar."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="314", teor="… sob nº R-33/314. Montes …",
                         atos=(("R", 1), ("AV", 14)))
    junto = " ".join(casa["cliente"].get(
        f"/registro-imoveis/{mid}").get_data(as_text=True).split())
    assert "o próximo ato desta matrícula é o número 34" in junto.lower()
    assert "R-33" in junto
    assert "não cria ato a partir do texto" in junto


def test_a_lista_poe_as_estruturadas_na_frente(casa):
    """São as únicas em que o sistema numera sozinho, e por isso as únicas em
    que o erro sairia sem ninguém digitar nada — ainda que a distância delas
    seja menor."""
    con = _con(casa)
    with con:
        _matricula(con, numero="920", tipo_ficha="ACERVO",
                   teor="R-32/920")            # distância 32
        _matricula(con, numero="3236", tipo_ficha="ESTRUTURADA",
                   teor="R-02/3.236")          # distância 2
    html = casa["cliente"].get(
        "/registro-imoveis/numeracao-no-teor").get_data(as_text=True)
    assert html.index("3236") < html.index("920")
    assert "1 delas numeram sozinhas" in " ".join(html.split())

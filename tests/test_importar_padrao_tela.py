"""A tela do padrao de importacao — relato #31.

O QUE ELA GUARDA
    **Que conferir e importar sao DOIS BOTOES.** Aqui nao ha como desfazer:
    acervo importado vira o livro. Um clique so faria a pessoa gravar cinquenta
    registros que ela nunca viu.

    **Que o exemplo da tela e um arquivo que este sistema le.** Um exemplo
    escrito a mao num manual fica velho no dia em que a coluna nasce; este e
    montado do esquema, e o teste o pega da tela e manda de volta para o modulo.
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

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture(scope="module")
def casa(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": banco}


def _tela(casa, **args) -> str:
    return casa["c"].get("/importar-padrao", query_string=args).get_data(
        as_text=True)


def test_a_tela_abre_e_mostra_o_exemplo(casa):
    html = _tela(casa)
    assert "Importar de outro sistema" in html
    assert "CARTORIO_GESTAO_IMPORTACAO" in html


def test_a_tela_oferece_as_duas_especies(casa):
    """As duas que o oficial citou: matrícula do RI e assento do RCPN."""
    html = _tela(casa)
    assert "RCPN_ASSENTO" in html and "RI_MATRICULA" in html


def test_a_tela_lista_os_campos_com_o_que_e_obrigatorio(casa):
    html = _tela(casa, especie="RCPN_ASSENTO")
    assert "cor_raca" in html, "os campos não vieram do esquema"
    assert "naturalidade_declarada" in html


def test_o_botao_de_importar_so_aparece_depois_de_conferir(casa):
    """**Um clique só faria a pessoa gravar o que nunca viu.**"""
    html = _tela(casa)
    assert 'value="conferir"' in html
    assert 'value="importar"' not in html, \
        "o botão de gravar apareceu antes de qualquer conferência"


def test_conferir_mostra_o_quadro_e_nao_grava(casa):
    import json

    arquivo = json.dumps({
        "formato": "CARTORIO_GESTAO_IMPORTACAO", "versao": 1,
        "especie": "RCPN_ASSENTO", "de_onde_veio": "Serventia vizinha",
        "registros": [{"chave": "X-1", "serie": "RC_A",
                       "especie": "NASCIMENTO", "nome": "JOAO DA SILVA"}]},
        ensure_ascii=False)
    html = casa["c"].post(
        "/importar-padrao",
        data={"csrf_token": _token(_tela(casa)), "especie": "RCPN_ASSENTO",
              "texto": arquivo, "o_que": "conferir"},
        follow_redirects=True).get_data(as_text=True)

    assert "O que entraria" in html
    assert 'value="importar"' in html, "agora o botão de gravar tem de aparecer"

    con = sqlite3.connect(casa["banco"])
    n = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    con.close()
    assert n == 0, "conferir gravou — e ele não pode gravar"


def test_o_exemplo_da_tela_e_um_arquivo_que_o_sistema_le(casa):
    """**O manual que nao envelhece**: o exemplo sai do esquema de hoje.

    O teste tira o exemplo da propria tela e o manda de volta ao modulo. Se um
    dia o exemplo e o leitor divergirem, e aqui que se ve.
    """
    import importar_padrao as IMP

    html = _tela(casa, especie="RI_MATRICULA")
    bruto = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL).group(1)
    import html as _h
    texto = _h.unescape(bruto)

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    # O exemplo traz «OBRIGATÓRIO» como valor de exemplo — ele é um MOLDE, e o
    # que se prova aqui é que o leitor o entende e chega a olhar os registros.
    quadro = IMP.conferir(con, texto)
    con.close()
    assert quadro["especie"] == "RI_MATRICULA"
    assert quadro["lidos"] == 1


def test_arquivo_quebrado_nao_derruba_a_tela(casa):
    """Erro de regra vira aviso em português, e não HTTP 500."""
    resposta = casa["c"].post(
        "/importar-padrao",
        data={"csrf_token": _token(_tela(casa)), "especie": "RCPN_ASSENTO",
              "texto": "{isto nao e json", "o_que": "conferir"},
        follow_redirects=True)
    assert resposta.status_code == 200
    assert "Bloco de Notas" in resposta.get_data(as_text=True)


def test_a_tela_manda_o_csrf(casa):
    """Regra da casa: toda tela que grava manda o token."""
    assert 'name="csrf_token"' in _tela(casa)

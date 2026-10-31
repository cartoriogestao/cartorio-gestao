"""ABRIR UM RASCUNHO JÁ SALVO — relato do oficial em 09/09/2026.

    «Salvei um rascunho, mas não tenho como abrir ele no sistema»

O mecanismo salvava, listava e apagava desde 31/08/2026 (relato #36) — e
nunca devolvia o que foi digitado para dentro da tela de onde saiu.
`rascunhos.html` não tinha um único link de abrir, e `rcpn_assento_novo`
(a única tela que já salva) não tinha uma linha sequer que lesse
`?rascunho_id=`.

Ver `rascunho_de_tela.py` (o mecanismo) e `test_rascunho_em_todo_ato.py`
(o «salva» das 13 telas). Este arquivo guarda o «abre» que faltava.
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

import rascunho_de_tela as RASC                                # noqa: E402

SENHA = "Senha#12345"


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    c = app.test_client()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": token}, follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


def _salvar_rascunho(casa, **dados) -> int:
    con = sqlite3.connect(casa["banco"])
    RASC.init_rascunho_schema(con)
    r = RASC.salvar(con, tela="rcpn_assento_novo", titulo="Nascimento — ÁUREA",
                     dados=dados, agora="2026-09-09T14:19:45",
                     por="Robô Nascimento RCPN")
    con.commit()
    con.close()
    return r["id"]


def test_a_lista_de_rascunhos_oferece_abrir(casa):
    """O achado do relato: a lista tinha «apagar» e não tinha «abrir»."""
    rid = _salvar_rascunho(casa, especie="NASCIMENTO", pessoa_nome="ÁUREA")
    html = casa["c"].get("/rascunhos").get_data(as_text=True)
    assert f"rascunho_id={rid}" in html, (
        "a lista de rascunhos não oferece um jeito de reabrir o que foi salvo")


def test_abrir_o_rascunho_leva_direto_para_a_especie_certa(casa):
    """Sem espécie na URL, `/rcpn/novo` abre o SELETOR. O rascunho sabe a
    espécie (ele mesmo a guardou) — por isso o redirecionamento tem de levar
    direto ao formulário de nascimento, e não ao seletor."""
    rid = _salvar_rascunho(
        casa, especie="NASCIMENTO", pessoa_nome="ÁUREA EXEMPLO LEÃO",
        filiacao1_nome="DIOGO BITENCOURT BARROS", cor_raca="PARDA")
    r = casa["c"].get(f"/rcpn/novo?rascunho_id={rid}", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308), (
        f"esperava um redirecionamento para a espécie certa, veio {r.status_code}")
    assert "/nascimento" in r.headers["Location"]
    assert f"rascunho_id={rid}" in r.headers["Location"], (
        "o redirecionamento perdeu o rascunho_id pelo caminho")


def test_abrir_o_rascunho_preenche_o_formulario(casa):
    """**O teste que prova o relato resolvido**: o nome que o robô digitou
    tem de aparecer no campo da tela, não só existir no banco."""
    rid = _salvar_rascunho(
        casa, especie="NASCIMENTO", pessoa_nome="ÁUREA EXEMPLO LEÃO",
        filiacao1_nome="DIOGO BITENCOURT BARROS", cor_raca="PARDA")
    html = casa["c"].get(
        f"/rcpn/novo/nascimento?rascunho_id={rid}",
        follow_redirects=True).get_data(as_text=True)
    assert "ÁUREA EXEMPLO LEÃO" in html, (
        "o rascunho abriu, mas o nome da pessoa não veio para o campo")
    assert "DIOGO BITENCOURT BARROS" in html
    assert "Continuando o rascunho" in html


def test_rascunho_de_outra_tela_nao_abre_aqui(casa):
    """Trocar tela por engano (ou na mão, na URL) não pode vazar o rascunho
    de uma tela para dentro do formulário de outra."""
    con = sqlite3.connect(casa["banco"])
    RASC.init_rascunho_schema(con)
    r = RASC.salvar(con, tela="notas_ato_novo", titulo="Escritura",
                     dados={"nome": "FULANO"}, agora="2026-09-09T14:00:00",
                     por="tabeliao")
    con.commit()
    con.close()
    html = casa["c"].get(
        f"/rcpn/novo?rascunho_id={r['id']}",
        follow_redirects=True).get_data(as_text=True)
    assert "não é de um assento do Registro Civil" in html
    assert "FULANO" not in html


def test_salvar_de_novo_atualiza_em_vez_de_duplicar(casa):
    """Sem `_rascunho_id` no botão de salvar, reabrir e salvar de novo criava
    um SEGUNDO rascunho — o escrevente veria a mesma certidão duplicada."""
    rid = _salvar_rascunho(casa, especie="NASCIMENTO", pessoa_nome="ÁUREA")
    html = casa["c"].get(
        f"/rcpn/novo/nascimento?rascunho_id={rid}").get_data(as_text=True)
    assert f'name="_rascunho_id" value="{rid}"' in html, (
        "o botão de salvar rascunho não carrega o id do rascunho aberto — "
        "salvar de novo criaria um segundo, em vez de atualizar este")


# ---------------------------------------------- as telas que salvavam e não reabriam (31/10/2026)

def _rascunho_de(casa, tela: str, dados: dict) -> int:
    con = sqlite3.connect(casa["banco"])
    RASC.init_rascunho_schema(con)
    r = RASC.salvar(con, tela=tela, titulo="Rascunho de ensaio", dados=dados,
                    agora="2026-10-31T10:00:00", por="Robô de ensaio")
    con.commit()
    con.close()
    return r["id"]


TELAS_QUE_REABREM = [
    ("notas_ato_novo", "/notas/atos/novo", {"tipo": "ATA", "interessado": "ANA EXEMPLO"}),
    ("protesto_titulo_novo", "/protesto/novo", {"numero_titulo": "ENSAIO-1", "cedente_nome": "ANA EXEMPLO"}),
    ("livro3_registro_novo", "/livro3/novo", {"titulo_numero": "ENSAIO-1", "garantia": "ANA EXEMPLO"}),
    ("rcpj_rtd_registro_novo", "/rcpj-rtd/novo", {"requerente_nome": "ANA EXEMPLO"}),
    ("rcpj_rtd_titulo_novo", "/rcpj-rtd/titulos/novo", {"apresentante": "ANA EXEMPLO"}),
    ("rcpn_retificacao_nova", "/rcpn/retificacoes/nova", {"requerente_nome": "ANA EXEMPLO"}),
    ("ri_retificacao_nova", "/registro-imoveis/retificacoes/nova", {"requerente_nome": "ANA EXEMPLO"}),
]


@pytest.mark.parametrize("tela,endereco,dados", TELAS_QUE_REABREM)
def test_a_tela_reabre_com_o_que_foi_guardado(casa, tela, endereco, dados):
    """**O relato inteiro**: «abrir» levava ao formulário em branco."""
    rid = _rascunho_de(casa, tela, dados)
    lista = casa["c"].get("/rascunhos").get_data(as_text=True)
    assert f"rascunho_id={rid}" in lista
    html = casa["c"].get(f"{endereco}?rascunho_id={rid}").get_data(as_text=True)
    assert "ANA EXEMPLO" in html, f"{tela}: abriu em branco"
    assert f'name="_rascunho_id" value="{rid}"' in html, f"{tela}: salvar de novo criaria outro rascunho"
    assert "não tomou número" in html


@pytest.mark.parametrize("tela,endereco,dados", TELAS_QUE_REABREM)
def test_rascunho_de_outra_tela_e_recusado_em_cada_uma(casa, tela, endereco, dados):
    rid = _rascunho_de(casa, "tela_de_outro_assunto", {"interessado": "OUTRA PESSOA", "requerente_nome": "OUTRA PESSOA"})
    html = casa["c"].get(f"{endereco}?rascunho_id={rid}").get_data(as_text=True)
    assert "OUTRA PESSOA" not in html
    assert "Este rascunho não é" in html
    assert 'name="_rascunho_id"' not in html


def test_o_rascunho_das_notas_gravado_antes_do_conserto_abre(casa):
    """Na forma que a produção tem: um texto por nome, sem os campos vazios."""
    rid = _rascunho_de(casa, "notas_ato_novo", {"tipo": "ATA", "data": "2026-09-20", "interessado": "ANA EXEMPLO",
                                                "natureza": "Ata de ensaio"})
    html = casa["c"].get(f"/notas/atos/novo?rascunho_id={rid}").get_data(as_text=True)
    assert '<option value="ATA" selected>' in html
    assert 'name="data" value="2026-09-20"' in html
    assert 'value="ANA EXEMPLO"' in html and 'value="Ata de ensaio"' in html


def test_o_titulo_guardado_do_rcpj_abre_no_rcpj(casa):
    """A lista abre sem dizer a atribuição, e o título do RCPJ abriria como se fosse do RTD."""
    rid = _rascunho_de(casa, "rcpj_rtd_titulo_novo", {"atribuicao": "3", "apresentante": "ANA EXEMPLO"})
    html = casa["c"].get(f"/rcpj-rtd/titulos/novo?rascunho_id={rid}").get_data(as_text=True)
    assert 'name="atribuicao" value="3"' in html


def test_a_escritura_guardada_abre_no_modulo_dela(casa):
    rid = _rascunho_de(casa, "notas_ato_novo", {"familia": "escrituras", "interessado": "ANA EXEMPLO"})
    html = casa["c"].get(f"/notas/atos/novo?rascunho_id={rid}").get_data(as_text=True)
    assert 'name="familia" value="escrituras"' in html


def _salvar_pela_rota(casa, *pares) -> int:
    from werkzeug.datastructures import MultiDict
    c = casa["c"]
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/protesto/novo").get_data(as_text=True)).group(1)
    c.post("/rascunhos/salvar", data=MultiDict([
        ("csrf_token", token), ("_tela", "protesto_titulo_novo"), ("_volta", "/protesto/novo"),
        ("_titulo", "Título de protesto — ANA EXEMPLO"), *pares]), follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    rid = int(con.execute("SELECT MAX(id) FROM rascunhos_de_tela").fetchone()[0])
    con.close()
    return rid


def test_o_rascunho_guarda_os_dois_devedores_cada_um_com_o_seu(casa):
    """O segundo devedor se perdia, e o documento vazio do primeiro empurrava o do segundo para o lugar dele."""
    rid = _salvar_pela_rota(casa, ("numero_titulo", "ENSAIO-1"),
                            ("devedor_nome", "ANA EXEMPLO"), ("devedor_nome", "JOAO MODELO"),
                            ("devedor_documento", ""), ("devedor_documento", "00000000191"),
                            ("devedor_endereco", "RUA UM"), ("devedor_endereco", "RUA DOIS"))
    con = sqlite3.connect(casa["banco"])
    lido = RASC.ler(con, rid)
    con.close()
    # quem lê `dados` continua lendo um texto por nome
    assert lido["dados"]["devedor_nome"] == "ANA EXEMPLO"
    assert lido["dados"]["devedor_documento"] == "00000000191"
    assert "_repetidos" not in lido["dados"]
    html = casa["c"].get(f"/protesto/novo?rascunho_id={rid}").get_data(as_text=True)
    assert 'value="ANA EXEMPLO"' in html and 'value="JOAO MODELO"' in html
    assert 'value="RUA UM"' in html and 'value="RUA DOIS"' in html
    documentos = re.findall(r'<input name="devedor_documento"[^>]*>', html)
    assert len(documentos) == 2 and "value=" not in documentos[0] and 'value="00000000191"' in documentos[1]


def test_salvar_de_novo_em_uma_tela_nova_nao_duplica(casa):
    rid = _salvar_pela_rota(casa, ("numero_titulo", "ENSAIO-1"), ("cedente_nome", "ANA EXEMPLO"))
    rid2 = _salvar_pela_rota(casa, ("_rascunho_id", str(rid)), ("numero_titulo", "ENSAIO-2"), ("cedente_nome", "ANA EXEMPLO"))
    assert rid2 == rid
    con = sqlite3.connect(casa["banco"])
    assert RASC.ler(con, rid)["dados"]["numero_titulo"] == "ENSAIO-2"
    con.close()


def test_a_recusa_com_o_rascunho_aberto_continua_sabendo_qual_e(casa):
    """No layout novo o formulário tem endereço próprio: é ele que leva o rascunho para a recusa."""
    rid = _rascunho_de(casa, "protesto_titulo_novo", {"cedente_nome": "ANA EXEMPLO"})
    c = casa["c"]
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get(f"/protesto/novo?rascunho_id={rid}").get_data(as_text=True)).group(1)
    html = c.post(f"/protesto/novo?rascunho_id={rid}",
                  data={"csrf_token": token, "cedente_nome": "ANA EXEMPLO DIGITADA"},
                  follow_redirects=True).get_data(as_text=True)
    assert 'value="ANA EXEMPLO DIGITADA"' in html
    assert f'name="_rascunho_id" value="{rid}"' in html

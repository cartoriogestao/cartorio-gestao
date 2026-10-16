"""O relato #78: voltar ao preenchimento, e apagar o rascunho.

    «dar a possibilidade depois que avanca e salva o rascunho da escritura,
     nao consegue voltar pra pagina intermediaria de preenchimento de dados
     (...) e precisa ser possivel apagar rascunhos, direto na pagina de atos
     de livro»
      — Carla Exemplo Lima, 17/09/2026 às 11h01, em `/notas/atos`

O QUE ESTAVA ERRADO, e cabia numa linha de código:

    if modelo and not (a["teor"] or "").strip():

O quadro «Preencher a partir do modelo» **existia enquanto o teor estivesse
vazio**, e sumia no instante em que era preenchido — justamente quando se
descobre que um campo saiu errado. O que sobrava era editar o texto corrido à
mão, ou descobrir o truque que outra mensagem do sistema cita de passagem
(«esvazie o teor e preencha de novo»). **Truque que o sistema conta numa
mensagem de erro não é caminho: é senha.**

E O QUE FOI DIGITADO IA PARA O LIXO: a rota lia os valores do formulário,
montava o teor e os descartava. «Voltar à página de preenchimento» seria
redigitar dezenas de campos numa escritura.

MEDIDO NA PRODUÇÃO no dia do relato: **4 atos EM_LAVRATURA**, nenhum com selo,
nenhum com lançamento no caixa — e **dois são dela, do mesmo dia**: o #778 com
3.402 caracteres e o #779 vazio, aberto 37 minutos depois. É o rascunho
duplicado que ela queria tirar da frente.

O QUE ESTES TESTES GUARDAM:

  1. **O quadro volta**, com o que foi digitado dentro dele.
  2. **Ele avisa antes**, porque preencher de novo **substitui** o teor — quem
     editou o texto à mão depois de preencher perde a edição.
  3. **Só o rascunho se apaga.** Ato lavrado tem livro, folha, número e selo:
     cancela-se com rastro, não se apaga. Quatro recusas, e cada uma protege
     alguma coisa — o livro, o selo comprado, o dinheiro no caixa e a Central.
  4. **O teor vai inteiro para a auditoria.** O ato nunca existiu no livro,
     mas o trabalho existiu: há rascunho de 11.907 caracteres nesta casa.
  5. **Quem apaga é quem abriu, ou o oficial** — foi uma escrevente quem
     pediu, e trancar no ADMIN faria o pedido dela depender de quem não está
     no balcão.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
MODELO = ("<p>ESCRITURA de [OBJETO], nesta cidade de {{ sv.ri_cidade }}, "
          "entre [VENDEDOR] e [COMPRADOR]. Valor: [VALOR].</p>")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    """Um rascunho de escritura com modelo, e duas pessoas."""
    db = cg_casa["db"]
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "USER")
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    con = sqlite3.connect(cg_casa["banco"])
    with con:
        con.execute(
            """INSERT INTO nt_modelos (codigo, tipo, nome, nome_norm, corpo,
                                       origem, ativo, criado_em)
               VALUES ('ESC-CV','ESCRITURA','Compra e venda','COMPRA E VENDA',
                       ?, 'SISTEMA', 1, '2026-09-17T10:00:00')""", (MODELO,))
        con.execute(
            """INSERT INTO nt_atos (tipo, serie, data, hora, situacao, natureza,
                                    modelo_codigo, interessado, teor_formato,
                                    lavrado_nome, origem, criado_em)
               VALUES ('ESCRITURA','LIVRO','2026-09-17','10:22','EM_LAVRATURA',
                       'Compra e venda','ESC-CV','MARIA DA SILVA','html',
                       'CARLA EXEMPLO LIMA','MANUAL','2026-09-17T10:22:35')""")
        aid = con.execute("SELECT id FROM nt_atos").fetchone()[0]
        con.execute(
            """INSERT INTO nt_ato_partes (ato_id, nome, nome_norm, documento,
                                          ordem, testemunha, criado_em)
               VALUES (?,'MARIA DA SILVA','MARIA DA SILVA','52998224725',1,0,
                       '2026-09-17T10:22:35')""",
            (aid,))
    con.close()
    return {**cg_casa, "ato": aid, "cliente": _entrar(cg_casa["app"], "carla")}


def _ficha(casa, cliente=None) -> str:
    return (cliente or casa["cliente"]).get(
        f'/notas/atos/{casa["ato"]}').get_data(as_text=True)


def _preencher(casa, **campos) -> str:
    html = _ficha(casa)
    return casa["cliente"].post(
        f'/notas/atos/{casa["ato"]}/preencher',
        data={"csrf_token": _token(html), **campos},
        follow_redirects=True).get_data(as_text=True)


def _situacao(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT teor, modelo_valores FROM nt_atos WHERE id=?",
                        (casa["ato"],)).fetchone()
    con.close()
    return linha


# ------------------------------------------------- voltar ao preenchimento


def test_o_quadro_de_preencher_aparece_antes_do_teor(casa):
    """A porta de entrada continua onde estava."""
    assert "Preencher a partir do modelo" in _ficha(casa)


def test_o_quadro_continua_depois_de_salvo(casa):
    """Era aqui que ele sumia — e era aqui que ela precisava voltar."""
    _preencher(casa, objeto="um imóvel urbano", vendedor="MARIA",
               comprador="JOÃO", valor="R$ 100.000,00")
    assert (_situacao(casa)["teor"] or "").strip(), "o teor não foi montado"
    assert "Preencher a partir do modelo" in _ficha(casa), (
        "depois de salvar, o quadro de preenchimento sumiu — é o relato #78")


def test_o_que_foi_digitado_volta_na_tela(casa):
    """Sem isto, «voltar» significaria redigitar a escritura inteira."""
    _preencher(casa, objeto="um imóvel urbano", vendedor="MARIA DAS DORES",
               comprador="JOÃO", valor="R$ 100.000,00")
    guardado = json.loads(_situacao(casa)["modelo_valores"] or "{}")
    assert guardado.get("vendedor") == "MARIA DAS DORES", (
        "os valores do formulário não foram guardados")
    html = _ficha(casa)
    assert 'value="MARIA DAS DORES"' in html, (
        "o campo voltou vazio: quem corrige um campo teria de redigitar todos")


def test_com_teor_o_quadro_avisa_que_substitui(casa):
    """Quem editou o texto à mão depois de preencher perde a edição."""
    antes = _ficha(casa)
    assert "substitui o texto inteiro" not in antes, (
        "sem teor não há o que substituir — o aviso assustaria à toa")
    _preencher(casa, objeto="um imóvel", vendedor="M", comprador="J",
               valor="R$ 1,00")
    depois = _ficha(casa)
    assert "substitui o texto inteiro" in depois
    assert "Continuar?" in depois, "não há confirmação antes de substituir"


def test_corrigir_um_campo_refaz_o_teor(casa):
    """O caminho inteiro, como ela o percorreria."""
    _preencher(casa, objeto="um imóvel", vendedor="MARIA",
               comprador="JOAO", valor="R$ 1,00")
    _preencher(casa, objeto="um imóvel", vendedor="MARIA",
               comprador="JOÃO PEDRO", valor="R$ 1,00")
    teor = _situacao(casa)["teor"]
    assert "JOÃO PEDRO" in teor and "JOAO<" not in teor


# ------------------------------------------------------ apagar o rascunho


def _apagar(casa, cliente=None, ato=None):
    cliente = cliente or casa["cliente"]
    lista = cliente.get("/notas/atos").get_data(as_text=True)
    return cliente.post(
        f'/notas/atos/{ato or casa["ato"]}/apagar-rascunho',
        data={"csrf_token": _token(lista)}, follow_redirects=True)


def _quantos(casa):
    con = sqlite3.connect(casa["banco"])
    n = con.execute("SELECT COUNT(*) FROM nt_atos").fetchone()[0]
    con.close()
    return n


def test_o_botao_esta_na_lista_de_atos(casa):
    """«direto na página de atos de livro» — foi onde ela pediu."""
    assert "apagar" in casa["cliente"].get("/notas/atos").get_data(as_text=True)


def test_apagar_leva_as_partes_junto(casa):
    _apagar(casa)
    assert _quantos(casa) == 0
    con = sqlite3.connect(casa["banco"])
    partes = con.execute("SELECT COUNT(*) FROM nt_ato_partes").fetchone()[0]
    con.close()
    assert partes == 0, "as partes ficaram órfãs"


def test_o_teor_fica_inteiro_na_auditoria(casa):
    """Há rascunho de 11.907 caracteres nesta casa: um clique não pode levá-lo."""
    _preencher(casa, objeto="uma gleba de terras", vendedor="MARIA",
               comprador="JOÃO", valor="R$ 100.000,00")
    _apagar(casa)
    con = sqlite3.connect(casa["banco"])
    linha = con.execute(
        "SELECT details FROM audit_logs WHERE action='NT_RASCUNHO_APAGADO'"
    ).fetchone()
    con.close()
    assert linha is not None, "apagar rascunho tem de ficar na auditoria"
    detalhes = json.loads(linha[0])
    assert "uma gleba de terras" in detalhes["teor"], (
        "o texto não foi guardado — uma tarde de escrita sairia num clique")
    assert detalhes["aberto_por"] == "CARLA EXEMPLO LIMA"


def test_ato_lavrado_nao_se_apaga(casa):
    """Ato no livro se cancela, com rastro."""
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET situacao='LAVRADO' WHERE id=?",
                    (casa["ato"],))
    con.close()
    r = _apagar(casa)
    assert "já foi lavrado" in r.get_data(as_text=True)
    assert _quantos(casa) == 1


def test_rascunho_com_selo_nao_se_apaga(casa):
    """O selo foi comprado e está no razão."""
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET selo=? WHERE id=?",
                    ("ESCRIT000000ABCDEFGHIJKLMNOP", casa["ato"]))
    con.close()
    r = _apagar(casa)
    assert "já tem selo" in r.get_data(as_text=True)
    assert _quantos(casa) == 1


def test_rascunho_com_dinheiro_no_caixa_nao_se_apaga(casa):
    """Dinheiro que entrou sai por estorno, que deixa rastro."""
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET lancamento_id=1 WHERE id=?",
                    (casa["ato"],))
    con.close()
    r = _apagar(casa)
    assert "lançamento no caixa" in r.get_data(as_text=True)
    assert _quantos(casa) == 1


def test_o_rascunho_de_outra_pessoa_e_do_oficial(casa):
    """Quem abriu apaga o seu; o de outra pessoa é do oficial e do gerente."""
    outra = _entrar(casa["app"], "mario")   # ADMIN: pode
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET lavrado_nome=? WHERE id=?",
                    ("OUTRA ESCREVENTE", casa["ato"]))
    con.close()

    r = _apagar(casa)                      # a autora, que não abriu este
    assert "Só quem abriu" in r.get_data(as_text=True)
    assert _quantos(casa) == 1

    _apagar(casa, cliente=outra)
    assert _quantos(casa) == 0

"""O ato do RI antes de ser ato — rascunho, e a matrícula como ela vai ficar.

OS DOIS DÉBITOS DO BALCÃO, QUE SÃO UM SÓ
    «pré-visualizar matrícula com o ato novo» e «rascunho de ato sem consumir
    número». São a mesma necessidade por dois lados: escrever a averbação, ver
    como a matrícula vai ler com ela dentro, e só então lavrar.

POR QUE O RASCUNHO NÃO MORA EM `ri_atos` — e a medição decide
    Medido em 28/08/2026: **`ri_atos` não tem coluna de situação**. Não há
    `EM_LAVRATURA` como nas Notas (que tem, e usa: 259 lavrados e 1 em
    lavratura). No Registro de Imóveis todo ato é definitivo no instante em que
    entra, e entra já fazendo duas coisas irreversíveis: **toma o número**
    (`MAX(numero)+1`) e **entra na corrente de hash**, que é o que prova que
    nenhum ato foi mexido depois.

    Um rascunho dentro de `ri_atos` seria um ato que existe e não devia.
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

import ri_rascunho as RASC

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
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(con, *, numero="4010", atos=()):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               criado_em)
           VALUES (?, '2', '2', 'ATIVA', '2026-08-28T09:00')""", (numero,))
    mid = int(cur.lastrowid)
    # A CORRENTE DE HASH É NOT NULL, e é isso que faz o rascunho não poder
    # morar aqui: cada ato guarda o hash do anterior. Um rascunho inserido e
    # apagado deixaria um elo apontando para o nada.
    from ri_schema import hash_ato
    anterior = None
    for tipo, n, teor in atos:
        h = hash_ato(numero, tipo, n, "2026-08-01", teor, anterior)
        con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
                   teor, teor_formato, cancelado, acervo, origem,
                   hash_ato, hash_anterior, lavrado_em)
               VALUES (?,?,?, '2026-08-01', ?, 'texto', 0, 0, 'MANUAL',
                       ?, ?, '2026-08-01T09:00')""",
            (mid, tipo, n, teor, h, anterior))
        anterior = h
    return mid


# ------------------------------------------- o número não se consome


def test_o_numero_e_calculado_e_nao_tomado(casa):
    """`numero_que_teria` é da mesma família das funções de contador desta
    casa: toda uma delas tem `consumir=False`. Olhar a previsão não pode tirar
    o número de quem for lavrar."""
    con = _con(casa)
    with con:
        mid = _matricula(con, atos=(("R", 1, "o registro"), ("AV", 2, "a av")))
    assert RASC.numero_que_teria(_con(casa), mid) == 3
    # chamar de novo não muda nada, e nada foi gravado
    assert RASC.numero_que_teria(_con(casa), mid) == 3
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM ri_atos WHERE matricula_id=?",
        (mid,)).fetchone()["c"] == 2


def test_guardar_rascunho_nao_cria_ato(casa):
    """É o débito inteiro numa linha: rascunho não consome número porque não é
    ato — e não é ato porque não está em `ri_atos`."""
    con = _con(casa)
    with con:
        mid = _matricula(con, atos=(("R", 1, "o registro"),))
        RASC.salvar(con, mid, tipo="AV", teor="<p>a averbação nova</p>",
                    modelo_codigo=None, natureza_titulo=None, protocolo=None,
                    prenotacao=None, data_ato="2026-08-28", quem="jean",
                    agora="2026-08-28T10:00")
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM ri_atos WHERE matricula_id=?",
        (mid,)).fetchone()["c"] == 1
    assert RASC.numero_que_teria(_con(casa), mid) == 2


def test_o_rascunho_fica_fora_da_corrente_de_hash(casa):
    """A corrente é o que prova que nenhum ato foi mexido depois. Rascunho
    dentro dela a quebraria ao ser jogado fora."""
    esquema = (RAIZ / "ri_schema.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS ri_rascunhos" in esquema
    colunas = [d[1] for d in _con(casa).execute("PRAGMA table_info(ri_rascunhos)")]
    assert "hash_ato" not in colunas and "hash_anterior" not in colunas
    assert "numero" not in colunas


# ------------------------------------------- um por matrícula


def test_guardar_de_novo_atualiza_e_nao_duplica(casa):
    """Dois rascunhos abertos na mesma ficha fariam o escrevente lavrar o
    errado — e no RI lavrar o errado não se desfaz."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        RASC.salvar(con, mid, tipo="AV", teor="primeira versão",
                    modelo_codigo=None, natureza_titulo=None, protocolo=None,
                    prenotacao=None, data_ato=None, quem="jean",
                    agora="2026-08-28T10:00")
        RASC.salvar(con, mid, tipo="R", teor="segunda versão",
                    modelo_codigo=None, natureza_titulo=None, protocolo=None,
                    prenotacao=None, data_ato=None, quem="jean",
                    agora="2026-08-28T11:00")
    linhas = _con(casa).execute(
        "SELECT * FROM ri_rascunhos WHERE matricula_id=?", (mid,)).fetchall()
    assert len(linhas) == 1
    assert linhas[0]["teor"] == "segunda versão"
    assert linhas[0]["tipo"] == "R"
    assert linhas[0]["criado_em"] == "2026-08-28T10:00"      # o primeiro fica
    assert linhas[0]["atualizado_em"] == "2026-08-28T11:00"


def test_rascunho_em_branco_e_recusado(casa):
    """Rascunho sem texto é uma linha na lista que não diz nada, e que só serve
    para alguém lavrar um ato vazio depois."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
    for vazio in ("", "   "):
        with pytest.raises(RASC.RascunhoError) as e:
            with _con(casa) as c:
                RASC.salvar(c, mid, tipo="AV", teor=vazio, modelo_codigo=None,
                            natureza_titulo=None, protocolo=None,
                            prenotacao=None, data_ato=None, quem="jean",
                            agora="2026-08-28T10:00")
        assert "Escreva o texto" in str(e.value)


def test_tipo_fora_dos_dois_e_recusado(casa):
    con = _con(casa)
    with con:
        mid = _matricula(con)
    with pytest.raises(RASC.RascunhoError) as e:
        with _con(casa) as c:
            RASC.salvar(c, mid, tipo="X", teor="um texto", modelo_codigo=None,
                        natureza_titulo=None, protocolo=None, prenotacao=None,
                        data_ato=None, quem="jean", agora="2026-08-28T10:00")
    assert "não é tipo de ato" in str(e.value)


# ------------------------------------------- como ela vai ficar


def test_a_visao_poe_o_rascunho_no_fim_com_o_numero_que_teria(casa):
    """Mostrá-lo no meio responderia a pergunta errada: a pergunta é «como esta
    ficha vai ler depois deste ato»."""
    con = _con(casa)
    with con:
        mid = _matricula(con, atos=(("R", 1, "o registro"), ("AV", 2, "a av")))
        RASC.salvar(con, mid, tipo="AV", teor="<p>a nova</p>",
                    modelo_codigo=None, natureza_titulo=None, protocolo=None,
                    prenotacao=None, data_ato="2026-08-28", quem="jean",
                    agora="2026-08-28T10:00")
    visao = RASC.como_ficara(_con(casa), mid)
    assert [a["numero"] for a in visao["atos"]] == [1, 2]
    assert visao["numero_previsto"] == 3
    assert visao["rascunho"]["rotulo"] == "AV-03"
    assert visao["rascunho"]["marca"] == RASC.MARCA


def test_a_visao_nao_grava_nada(casa):
    """Tela de leitura que grava é o defeito que deixa a ficha dez segundos
    presa no busy_timeout enquanto outro balcão lavra."""
    con = _con(casa)
    with con:
        mid = _matricula(con, atos=(("R", 1, "x"),))
    antes = _con(casa).execute("SELECT COUNT(*) c FROM audit_logs").fetchone()["c"]
    casa["cliente"].get(f"/registro-imoveis/{mid}/como-ficara")
    depois = _con(casa).execute("SELECT COUNT(*) c FROM audit_logs").fetchone()["c"]
    assert antes == depois
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM ri_rascunhos").fetchone()["c"] == 0


# ------------------------------------------- a marca, que é o que protege


def test_a_previsao_sai_marcada_como_nao_lavrada(casa):
    """ESTA TELA PARECE CERTIDÃO, E NÃO É. Alguém pode imprimir e entregar, e
    aí a casa teria posto no mundo um papel afirmando um ato que não existe.
    A marca aparece em três lugares, e nenhum deles é um botão — ela continua
    na impressão."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        RASC.salvar(con, mid, tipo="AV", teor="<p>a averbação</p>",
                    modelo_codigo=None, natureza_titulo=None, protocolo=None,
                    prenotacao=None, data_ato=None, quem="jean",
                    agora="2026-08-28T10:00")
    html = casa["cliente"].get(
        f"/registro-imoveis/{mid}/como-ficara").get_data(as_text=True)
    assert html.count(RASC.MARCA) >= 2
    junto = " ".join(html.split())
    assert "não é certidão" in junto
    assert "ainda não existe" in junto


def test_a_tela_diz_que_o_numero_e_de_quem_lavrar_primeiro(casa):
    """Se dois escreventes rascunharem na mesma matrícula, os dois veem o mesmo
    número previsto. Isso é verdade e não defeito — e a tela diz."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        RASC.salvar(con, mid, tipo="AV", teor="x", modelo_codigo=None,
                    natureza_titulo=None, protocolo=None, prenotacao=None,
                    data_ato=None, quem="jean", agora="2026-08-28T10:00")
    junto = " ".join(casa["cliente"].get(
        f"/registro-imoveis/{mid}/como-ficara").get_data(as_text=True).split())
    assert "de quem lavrar primeiro" in junto


# ------------------------------------------- jogar fora, e a lista


def test_apagar_rascunho_nao_deixa_rastro(casa):
    """A única coisa neste sistema de que isso vale: rascunho NÃO é ato.
    Guardar o texto que alguém desistiu de escrever seria guardar o que a casa
    decidiu não dizer."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        RASC.salvar(con, mid, tipo="AV", teor="x", modelo_codigo=None,
                    natureza_titulo=None, protocolo=None, prenotacao=None,
                    data_ato=None, quem="jean", agora="2026-08-28T10:00")
    con = _con(casa)
    with con:
        assert RASC.apagar(con, mid) is True
        assert RASC.apagar(con, mid) is False        # não havia mais
    assert RASC.da_matricula(_con(casa), mid) is None


def test_a_lista_mostra_os_rascunhos_abertos(casa):
    """Sem esta lista o rascunho só apareceria a quem abrisse aquela matrícula
    por acaso."""
    con = _con(casa)
    with con:
        a = _matricula(con, numero="1")
        b = _matricula(con, numero="2")
        RASC.salvar(con, a, tipo="AV", teor="o mais antigo", modelo_codigo=None,
                    natureza_titulo=None, protocolo=None, prenotacao=None,
                    data_ato=None, quem="jean", agora="2026-08-27T10:00")
        RASC.salvar(con, b, tipo="R", teor="o mais novo", modelo_codigo=None,
                    natureza_titulo=None, protocolo=None, prenotacao=None,
                    data_ato=None, quem="jean", agora="2026-08-28T10:00")
    lista = RASC.abertos(_con(casa))
    assert [r["matricula_numero"] for r in lista] == ["1", "2"]
    html = casa["cliente"].get("/registro-imoveis/rascunhos").get_data(as_text=True)
    assert "2 rascunhos abertos" in " ".join(html.split())


# ------------------------------------------- o módulo não lavra


def test_o_modulo_do_rascunho_nao_lavra_ato():
    """Quem lavra é `ri_lavrar_ato`, que já tem a corrente de hash, o selo, os
    emolumentos, o delegatário e a amarração com a prenotação. Um segundo
    caminho para dentro de `ri_atos` seria a segunda versão do código mais
    delicado do módulo."""
    codigo = (RAIZ / "ri_rascunho.py").read_text(encoding="utf-8")
    assert "INSERT INTO ri_atos" not in codigo
    # o módulo cita a corrente no comentário, e é só ali que ela aparece
    assert "hash_anterior" not in codigo.replace("`hash_anterior`", "")
    publicos = [n for n in dir(RASC) if not n.startswith("_")]
    for proibido in ("lavrar", "registrar", "averbar", "numerar"):
        assert not [n for n in publicos if proibido in n.lower()], proibido


def test_a_ficha_oferece_o_rascunho(casa):
    con = _con(casa)
    with con:
        mid = _matricula(con)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Rascunho do ato" in html
    assert 'name="teor"' in html

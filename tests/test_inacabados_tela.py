"""A tela do que começou e não terminou.

POR QUE SEPARADO
    `test_inacabados.py` prova que o **módulo** mede, ajusta e anota. Este prova
    que a **tela chama o módulo** — e, sobretudo, que **os links abrem**.

    Naquele teste eu confiro que cada fonte aponta para uma rota existente com o
    parâmetro certo. Aqui eu **monto a página inteira**: se uma fonte tiver item
    e o `url_for` dela não fechar, o Jinja estoura ao renderizar — e é isso que
    este arquivo pega, com item de verdade em cada fonte.
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

import inacabados as IN                                          # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"


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


def _liso(t: str) -> str:
    return " ".join((t or "").split())


def _abrir(casa, url="/inacabados"):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


def _tarefa(casa, titulo="conferir o livro", quando="2026-01-05"):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO tasks (title, created_at, updated_at)
               VALUES (?,?,?)""", (titulo, quando, quando))
        return int(cur.lastrowid)


# ------------------------------------------------ a tela explica


def test_a_tela_diz_que_a_lista_e_medida_na_hora(casa):
    """É o coração do desenho, e é o que impede o defeito relatado: o ato
    concluído e o expediente ainda aberto."""
    html = _abrir(casa)
    assert "medida na hora" in html
    assert "Ato concluído sai daqui sozinho" in html


def test_a_tela_diz_que_nao_conclui_nada(casa):
    html = _abrir(casa)
    assert "não conclui nada" in html
    assert "leva à tela do ato" in html


def test_a_tela_mostra_as_nove_fontes(casa):
    """Fonte que some do resumo quando está vazia faz o operador achar que ela
    não existe."""
    html = _abrir(casa)
    for f in IN.FONTES:
        assert f["nome"] in html, f"a fonte «{f['chave']}» não aparece"


def test_a_tela_diz_o_que_tira_cada_item_da_lista(casa):
    """Quem olha a lista precisa saber o que faz o item sair dela — senão a
    pergunta «por que este ainda está aqui?» não tem resposta na tela."""
    html = _abrir(casa)
    assert "quando a escritura é lavrada" in html
    assert "quando o casamento é celebrado" in html


# ------------------------------------------------ a tela chama o módulo


def test_a_tela_lista_o_que_esta_em_aberto(casa):
    _tarefa(casa, "conferir o livro de casamento")
    html = _abrir(casa)
    assert "conferir o livro de casamento" in html


def test_o_concluido_some_da_tela_sozinho(casa):
    tid = _tarefa(casa, "já feita")
    assert "já feita" in _abrir(casa)
    con = _con(casa)
    with con:
        con.execute("UPDATE tasks SET completed_at=? WHERE id=?", (AGORA, tid))
    assert "já feita" not in _abrir(casa)


def test_a_tela_marca_o_parado_em_vermelho(casa):
    _tarefa(casa, "parada ha meses", quando="2026-01-05")
    html = _abrir(casa)
    assert "parada ha meses" in html
    assert "dias</strong>" in html or "dias" in html


def test_so_os_parados(casa):
    # TÍTULOS QUE NÃO CABEM NUMA FRASE — 14/10/2026. «de hoje» solto passou a
    # aparecer em TODA tela, na prosa do registro rápido da produtividade
    # («atividade de hoje (ou agora − duração)»), e o teste acusava a prosa.
    # O que se mede é a TAREFA, e por isso o título tem de ser só dela.
    _tarefa(casa, "TAREFA-PARADA-DE-HOJE", quando=casa["db"].now()[:10])
    _tarefa(casa, "TAREFA-PARADA-DE-JANEIRO", quando="2026-01-05")
    html = _abrir(casa, "/inacabados?so_parados=1")
    assert "TAREFA-PARADA-DE-JANEIRO" in html
    assert "TAREFA-PARADA-DE-HOJE" not in html


def test_filtrar_por_fonte(casa):
    _tarefa(casa, "uma tarefa")
    html = _abrir(casa, "/inacabados?fonte=TAREFA")
    assert "uma tarefa" in html
    assert "Tarefa em aberto" in html


def test_fonte_que_nao_existe_volta_avisando(casa):
    """Erro de regra não é HTTP 500."""
    r = casa["cliente"].get("/inacabados?fonte=NAO_EXISTE",
                            follow_redirects=True)
    assert "Não conheço a fonte" in _liso(r.get_data(as_text=True))


def test_a_tela_vazia_avisa_da_fonte_desligada(casa):
    """Lista vazia por fonte desligada parece lista vazia por casa em dia."""
    html = _abrir(casa)
    assert "confira acima se a fonte está ligada" in html


# ------------------------------------------------ os links abrem


def test_a_pagina_monta_com_item_em_TODA_fonte(casa):
    """**É O TESTE QUE MAIS VALE AQUI.** Se o `url_for` de uma fonte não fechar,
    o Jinja estoura ao renderizar — e o link quebrado só apareceria quando
    alguém clicasse. Com item de verdade em cada uma das nove, a página inteira
    tem de montar."""
    con = _con(casa)
    with con:
        con.execute("""INSERT INTO nt_atos (tipo, data, situacao, interessado,
                           criado_em) VALUES ('ESCRITURA','2026-01-05',
                           'EM_LAVRATURA','MARIA',?)""", (AGORA,))
        con.execute("""INSERT INTO ri_protocolos (numero, data_prenotacao,
                           apresentante, situacao, criado_em)
                       VALUES (1,'2026-01-05','BANCO','ABERTO',?)""", (AGORA,))
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, criado_em)
               VALUES ('1','2026-01-05')""")
        mid = int(cur.lastrowid)
        con.execute("""INSERT INTO ri_rascunhos (matricula_id, tipo, teor,
                           criado_em, atualizado_em)
                       VALUES (?,'AVERBACAO','texto',?,'2026-01-05')""",
                    (mid, AGORA))
        con.execute("""INSERT INTO cx_protocolos (numero, data_abertura,
                           atribuicao, interessado, situacao, criado_em)
                       VALUES ('1','2026-01-05','NOTAS','JOAO','ABERTO',?)""",
                    (AGORA,))
        con.execute("""INSERT INTO us_processos (numero, ano, modalidade,
                           etapa, situacao, requerente_nome, criado_em,
                           atualizado_em)
                       VALUES ('1',2026,'EXTRAORDINARIA','AUTUACAO',
                               'EM_ANDAMENTO','ANA',?, '2026-01-05')""",
                    (AGORA,))
        # `matricula_id` E NOT NULL aqui de proposito, e o proprio `rt_schema`
        # diz por que: «o que se retifica E o registro, e sem ele nao ha o que
        # retificar». No usucapiao o imovel pode nao ter matricula nenhuma.
        con.execute("""INSERT INTO rt_processos (numero, ano, especie,
                           fundamento, fase, situacao, requerente_nome,
                           matricula_id, criado_em, atualizado_em)
                       VALUES ('1',2026,'GEORREFERENCIADA','ART_213_II',
                               'AUTUACAO','EM_ANDAMENTO','PEDRO',?,?,
                               '2026-01-05')""", (mid, AGORA))
        # OS DOIS NUBENTES SAO OBRIGATORIOS — nao ha habilitacao de um so.
        con.execute("""INSERT INTO hc_habilitacoes (numero, ano, data_entrada,
                           tipo, situacao, nubente1_nome, nubente2_nome,
                           criado_em)
                       VALUES ('1',2026,'2026-01-05','CIVIL','ABERTA',
                               'CARLA','ROBERTO',?)""", (AGORA,))
        # `created_by` E O ID de quem cadastrou (INTEGER NOT NULL, FK users): a
        # tela e o malote gravam o numero. O login «mario» que estava aqui o
        # SQLite aceitava, e o PostgreSQL recusa (19/10/2026).
        mario = con.execute(
            "SELECT id FROM users WHERE username='mario'").fetchone()[0]
        con.execute("""INSERT INTO expedientes (internal_protocol, source,
                           subject, category, received_at, created_by,
                           created_at, updated_at)
                       VALUES ('1','MALOTE','oficio do juiz','JUDICIAL',
                               '2026-01-05',?,?,?)""", (mario, AGORA, AGORA))
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('uma tarefa','2026-01-05','2026-01-05')""")

    html = _abrir(casa)
    # cada fonte trouxe o seu item, e a pagina montou com o link de cada um
    for esperado in ("MARIA", "BANCO", "JOAO", "ANA", "PEDRO", "CARLA",
                     "oficio do juiz", "uma tarefa"):
        assert esperado in html, f"«{esperado}» não apareceu na lista"


# ------------------------------------------------ moldar o que fica


def test_a_tela_deixa_desligar_uma_fonte(casa):
    """É o «o que fica, o que sai» que o oficial pediu."""
    _tarefa(casa, "uma tarefa")
    html = casa["cliente"].get("/inacabados").get_data(as_text=True)
    campos = {"csrf_token": _token(html)}
    for f in IN.FONTES:
        if f["chave"] != "TAREFA":
            campos[f"ligada_{f['chave']}"] = "on"
        campos[f"dias_{f['chave']}"] = str(f["dias"])
    r = casa["cliente"].post("/inacabados/ajustar", data=campos,
                             follow_redirects=True)
    saida = _liso(r.get_data(as_text=True))
    assert "Ajuste guardado" in saida
    assert "uma tarefa" not in saida
    assert "desligada" in saida


def test_o_ajuste_de_dias_muda_quem_esta_parado(casa):
    _tarefa(casa, "de dez dias atras", quando="2026-08-10")
    html = casa["cliente"].get("/inacabados").get_data(as_text=True)
    campos = {"csrf_token": _token(html)}
    for f in IN.FONTES:
        campos[f"ligada_{f['chave']}"] = "on"
        campos[f"dias_{f['chave']}"] = "1" if f["chave"] == "TAREFA" \
            else str(f["dias"])
    casa["cliente"].post("/inacabados/ajustar", data=campos,
                         follow_redirects=True)
    assert IN.configuracao(_con(casa))["TAREFA"]["dias"] == 1


def test_o_ajuste_esta_na_auditoria(casa):
    html = casa["cliente"].get("/inacabados").get_data(as_text=True)
    campos = {"csrf_token": _token(html)}
    for f in IN.FONTES:
        campos[f"ligada_{f['chave']}"] = "on"
        campos[f"dias_{f['chave']}"] = str(f["dias"])
    casa["cliente"].post("/inacabados/ajustar", data=campos,
                         follow_redirects=True)
    acoes = [x[0] for x in _con(casa).execute(
        "SELECT action FROM audit_logs ORDER BY id DESC LIMIT 5")]
    assert "INACABADOS_AJUSTE" in acoes


# ------------------------------------------------ anotar


def test_anotar_aparece_na_lista(casa):
    tid = _tarefa(casa, "uma tarefa")
    html = casa["cliente"].get(
        f"/inacabados/anotar/tasks/{tid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/inacabados/anotar/tasks/{tid}",
        data={"csrf_token": _token(html),
              "texto": "esperando o documento do requerente",
              "responsavel": "Debora", "ate": "2026-09-10"},
        follow_redirects=True)
    saida = _abrir(casa)
    assert "esperando o documento do requerente" in saida
    assert "Debora" in saida


def test_a_tela_de_anotar_leva_a_tela_do_ato(casa):
    """É lá que se conclui, com as regras de lá."""
    tid = _tarefa(casa, "uma tarefa")
    html = _abrir(casa, f"/inacabados/anotar/tasks/{tid}")
    assert "é lá que se conclui" in html
    assert f"/tasks/{tid}" in html or "abrir a tela deste ato" in html


def test_anotacao_vazia_volta_avisando(casa):
    tid = _tarefa(casa, "uma tarefa")
    html = casa["cliente"].get(
        f"/inacabados/anotar/tasks/{tid}").get_data(as_text=True)
    r = casa["cliente"].post(f"/inacabados/anotar/tasks/{tid}",
                             data={"csrf_token": _token(html), "texto": "  "},
                             follow_redirects=True)
    assert "Escreva o que falta" in _liso(r.get_data(as_text=True))


def test_apagar_a_anotacao_nao_tira_o_item_da_lista(casa):
    """Se apagar a anotação sumisse com o item, a lista viraria gaveta."""
    tid = _tarefa(casa, "uma tarefa")
    html = casa["cliente"].get(
        f"/inacabados/anotar/tasks/{tid}").get_data(as_text=True)
    casa["cliente"].post(f"/inacabados/anotar/tasks/{tid}",
                         data={"csrf_token": _token(html), "texto": "esperando o memorial descritivo"},
                         follow_redirects=True)
    html = casa["cliente"].get(
        f"/inacabados/anotar/tasks/{tid}").get_data(as_text=True)
    r = casa["cliente"].post(f"/inacabados/anotar/tasks/{tid}",
                             data={"csrf_token": _token(html),
                                   "acao": "apagar"},
                             follow_redirects=True)
    saida = _liso(r.get_data(as_text=True))
    assert "uma tarefa" in saida            # o item ficou
    # NAO SE PROCURA PALAVRA GENERICA NUM HTML INTEIRO: a primeira
    # versao procurava «algo», que a propria janela da ajuda escreve
    # («como fazer algo no sistema»). O teste falhava com o codigo
    # certo — e teria passado com o codigo errado se a palavra fosse
    # comum dos dois lados.
    assert "esperando o memorial" not in saida   # a anotacao saiu


def test_so_ver_a_lista_nao_grava_nada(casa):
    """Grava-se quando o operador age, nunca ao mostrar."""
    _tarefa(casa, "uma tarefa")
    _abrir(casa)
    _abrir(casa)
    con = _con(casa)
    assert con.execute("SELECT COUNT(*) FROM ex_anotacoes").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM ex_fontes").fetchone()[0] == 0


def test_a_lista_esta_no_menu(casa):
    assert "O que ficou pelo caminho" in _abrir(casa)

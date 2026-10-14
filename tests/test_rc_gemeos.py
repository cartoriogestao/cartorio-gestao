"""Gêmeos — art. 234, e as duas regras que ele traz.

O QUE ESTES TESTES GUARDAM
    **Que `ibge_gemeo` não responde à pergunta do art. 234.** Aquele campo diz
    *se* é gêmeo; o artigo exige *qual é a ordem*, no assento de cada um. Usar um
    pelo outro faria o assento cumprir a remessa e descumprir a lei.

    **Que gêmeos com o mesmo nome não se distinguem** — e o § único manda
    inscrevê-los com duplo prenome ou nome completo diverso. Dois irmãos com nome
    idêntico, mesma filiação e mesma data de nascimento são duas pessoas que
    nenhum documento separa.

    **Que a ligação entre os irmãos é recíproca por construção.** Depender de
    duas amarrações produziria o par pela metade — e o par pela metade é o que faz
    a certidão de um irmão não citar o outro.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_gemeos as G                                            # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _nascimento(con, *, nome="MARIA", numero=1, ibge_gemeo=2,
                data_ato="2026-08-05"):
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, ibge_gemeo)
           VALUES ('RC_A','NASCIMENTO',?,?,?,?,'ATIVO','SISTEMA',?,?)""",
        (numero, nome, data_ato, data_ato, AGORA, ibge_gemeo))
    return int(cur.lastrowid)


# ------------------------------------------------ a norma


def test_a_ordem_consta_no_assento_de_cada_um():
    assert "cada um" in G.ORDEM_OBRIGATORIA
    assert "art. 234" in G.ORDEM_OBRIGATORIA


def test_o_fato_de_ser_gemeo_e_requisito_legal():
    """Art. 233, III, que repete o art. 54 da Lei 6.015/1973 — não é informação
    acessória."""
    assert "requisito legal" in G.E_REQUISITO_DO_ASSENTO
    assert "art. 54" in G.E_REQUISITO_DO_ASSENTO


def test_o_campo_do_ibge_nao_serve_para_a_ordem():
    """Ele diz **se** é gêmeo; o artigo exige **qual é a ordem**."""
    assert "não responde a outra pergunta" in G.O_CAMPO_DO_IBGE_NAO_SERVE
    assert "ibge_gemeo" in G.O_CAMPO_DO_IBGE_NAO_SERVE


def test_o_paragrafo_unico_manda_distinguir():
    assert "duplo prenome" in G.PRENOME_IGUAL
    assert "nome completo diverso" in G.PRENOME_IGUAL


def test_os_artigos_citados_servem_para_conferir():
    citados = G.artigos_citados()
    assert "art. 234, parágrafo único" in citados
    assert "art. 233, III" in citados


# ------------------------------------------------ o parto múltiplo


def test_dois_e_tres_sao_parto_multiplo():
    """Medido em `ibge_remessa.GEMEO`: 1 é parto único e 9 é ignorado."""
    assert G.CODIGOS_DE_PARTO_MULTIPLO == (2, 3)
    assert G.e_parto_multiplo(2)
    assert G.e_parto_multiplo(3)
    assert not G.e_parto_multiplo(1)
    assert not G.e_parto_multiplo(9)


def test_o_texto_tambem_conta():
    """**A AFINIDADE DA COLUNA CONVERTE NA ENTRADA**: a tela grava `"2"`, o
    SQLite guarda `2`. Comparar com texto acharia zero — quarta vez neste
    projeto."""
    assert G.e_parto_multiplo("2")
    assert not G.e_parto_multiplo("1")


def test_valor_ilegivel_nao_e_parto_multiplo():
    for ruim in (None, "", "sim", "gemeo"):
        assert not G.e_parto_multiplo(ruim), f"«{ruim}» não devia entrar"


# ------------------------------------------------ o prenome


def test_prenome_sai_sem_acento_e_sem_caixa():
    """«José» e «JOSE» são o mesmo prenome para quem tem de distinguir dois
    irmãos — e `UPPER` do SQLite é ASCII, o que já deixou o CNIB sem achar
    ninguém."""
    assert G.prenome("José da Silva") == "JOSE"
    assert G.prenome("JOSE DA SILVA") == "JOSE"
    assert G.prenome("  maria  ") == "MARIA"
    assert G.prenome(None) == ""


def test_nomes_iguais_nao_se_distinguem():
    r = G.prenomes_se_distinguem(["JOSE DA SILVA", "JOSE DA SILVA"])
    assert not r["distinguem"]
    assert "art. 234, parágrafo único" in r["aviso"]
    assert "nenhum documento separa" in r["aviso"]


def test_o_acento_nao_distingue():
    """«JOSÉ» e «JOSE» são a mesma pessoa para qualquer documento."""
    assert not G.prenomes_se_distinguem(
        ["JOSÉ DA SILVA", "JOSE DA SILVA"])["distinguem"]


def test_o_duplo_prenome_resolve():
    """É uma das duas saídas que o § único dá."""
    assert G.prenomes_se_distinguem(
        ["JOSE ANTONIO DA SILVA", "JOSE CARLOS DA SILVA"])["distinguem"]


def test_o_nome_completo_diverso_tambem_resolve():
    """«duplo prenome **ou** nome completo diverso» — são duas saídas."""
    assert G.prenomes_se_distinguem(
        ["JOSE DA SILVA", "JOSE DOS SANTOS"])["distinguem"]


def test_um_nome_so_nao_gera_aviso():
    """Não há o que distinguir."""
    assert G.prenomes_se_distinguem(["JOSE"])["distinguem"]
    assert G.prenomes_se_distinguem([])["distinguem"]


def test_o_aviso_diz_quais_se_repetem():
    """Quem lê precisa saber qual nome mudar, e não só que há um problema."""
    r = G.prenomes_se_distinguem(
        ["JOSE DA SILVA", "JOSE DA SILVA", "MARIA DA SILVA"])
    assert r["repetidos"] == ["JOSE DA SILVA"]


def test_o_modulo_avisa_e_nao_recusa():
    """Registro de nascimento é imperativo legal (art. 250), e quem decide é o
    oficial. **Sétima vez que esta regra aparece neste projeto.**"""
    publicos = [n for n in dir(G)
                if not n.startswith("_") and callable(getattr(G, n))]
    for nome in publicos:
        for proibido in ("recusar", "impedir", "travar", "bloquear"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"


# ------------------------------------------------ o que falta


def test_gemeo_sem_ordem_falta(casa):
    assert G.o_que_falta({"ibge_gemeo": 2}) == [
        "a ordem de nascimento — o art. 234 manda que ela conste no assento "
        "de CADA um dos gêmeos"]


def test_quem_nao_e_gemeo_nao_falta_nada():
    assert G.o_que_falta({"ibge_gemeo": 1}) == []
    assert G.o_que_falta({"ibge_gemeo": 9}) == []
    assert G.o_que_falta({}) == []


def test_com_a_ordem_nao_falta_nada():
    assert G.o_que_falta({"ibge_gemeo": 2, "gemeo_ordem": 1}) == []


def test_ordem_zero_ainda_falta():
    """A ordem começa em 1 — é o primeiro a nascer."""
    assert G.o_que_falta({"ibge_gemeo": 2, "gemeo_ordem": 0})


# ------------------------------------------------ a lista


def test_a_lista_traz_o_gemeo_sem_ordem(casa):
    con = _con(casa)
    with con:
        _nascimento(con, nome="GEMEO SEM ORDEM", numero=1, ibge_gemeo=2)
        _nascimento(con, nome="FILHO UNICO", numero=2, ibge_gemeo=1)
    assert [x["nome"] for x in G.pendentes(con)] == ["GEMEO SEM ORDEM"]


def test_o_gemeo_com_ordem_sai_da_lista(casa):
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="COM ORDEM")
        con.execute("UPDATE rc_assentos SET gemeo_ordem=1 WHERE id=?", (aid,))
    assert G.pendentes(con) == []


def test_o_cancelado_nao_entra(casa):
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CANCELADO")
        con.execute("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=?",
                    (aid,))
    assert G.pendentes(con) == []


def test_o_obito_nao_entra(casa):
    """A regra é do registro de nascimento."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, ibge_gemeo)
               VALUES ('RC_C','OBITO',1,'ANTONIO','2026-08-05','2026-08-05',
                       'ATIVO','SISTEMA',?,2)""", (AGORA,))
    assert G.pendentes(con) == []


# ------------------------------------------------ amarrar os irmãos


def test_amarrar_grava_a_ordem_e_a_ligacao(casa):
    con = _con(casa)
    with con:
        a = _nascimento(con, nome="PRIMEIRO", numero=1)
        b = _nascimento(con, nome="SEGUNDO", numero=2)
        G.amarrar(con, a, irmao_id=b, ordem=1, agora=AGORA)
        G.amarrar(con, b, irmao_id=a, ordem=2, agora=AGORA)
    linha = dict(con.execute("SELECT * FROM rc_assentos WHERE id=?",
                             (a,)).fetchone())
    assert linha["gemeo_ordem"] == 1
    assert linha["gemeo_irmao_id"] == b


def test_a_ligacao_e_reciproca_com_uma_amarracao_so(casa):
    """**Depender de duas amarrações produziria o par pela metade** — e o par
    pela metade é o que faz a certidão de um irmão não citar o outro."""
    con = _con(casa)
    with con:
        a = _nascimento(con, nome="PRIMEIRO", numero=1)
        b = _nascimento(con, nome="SEGUNDO", numero=2)
        G.amarrar(con, a, irmao_id=b, ordem=1, agora=AGORA)
    assert [x["nome"] for x in G.irmaos(con, a)] == ["SEGUNDO"]
    assert [x["nome"] for x in G.irmaos(con, b)] == ["PRIMEIRO"]


def test_ninguem_e_gemeo_de_si_mesmo(casa):
    con = _con(casa)
    with con:
        a = _nascimento(con, nome="MARIA")
    with pytest.raises(G.GemeosError):
        with con:
            G.amarrar(con, a, irmao_id=a, ordem=1, agora=AGORA)


def test_a_ordem_comeca_em_um(casa):
    con = _con(casa)
    with con:
        a = _nascimento(con, nome="A", numero=1)
        b = _nascimento(con, nome="B", numero=2)
    with pytest.raises(G.GemeosError) as erro:
        with con:
            G.amarrar(con, a, irmao_id=b, ordem=0, agora=AGORA)
    assert "começa em 1" in str(erro.value)


def test_amarrar_a_assento_que_nao_existe_recusa(casa):
    """Sem a conferência batia na chave estrangeira e virava HTTP 500."""
    con = _con(casa)
    with con:
        a = _nascimento(con, nome="MARIA")
    with pytest.raises(G.GemeosError) as erro:
        with con:
            G.amarrar(con, a, irmao_id=9999, ordem=1, agora=AGORA)
    assert "não existe" in str(erro.value)


def test_sem_irmao_amarrado_a_lista_de_irmaos_e_vazia(casa):
    con = _con(casa)
    with con:
        a = _nascimento(con, nome="SOZINHO")
    assert G.irmaos(con, a) == []


# ------------------------------------------------ a tela


def _token(html):
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def logado(casa):
    c = casa["app"].test_client()
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    casa["cliente"] = c
    return casa


def _liso(t):
    return " ".join((t or "").split())


def _abrir(logado, url="/rcpn/gemeos"):
    r = logado["cliente"].get(url)
    assert r.status_code == 200, f"{url} nao abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


def test_a_tela_diz_que_o_campo_do_ibge_nao_serve(logado):
    """Usar um pelo outro faria o assento cumprir a remessa e descumprir a lei."""
    html = _abrir(logado)
    assert "O campo do IBGE não responde a esta pergunta" in html
    assert "ibge_gemeo" in html


def test_a_tela_avisa_do_nome_igual(logado):
    html = _abrir(logado)
    assert "nenhum documento separa" in html
    assert "duplo prenome" in html


def test_a_tela_diz_que_avisa_e_nao_recusa(logado):
    """Registro de nascimento é imperativo legal, e quem decide é o oficial."""
    html = _abrir(logado)
    assert "recusar não" in html.lower()


def test_a_tela_lista_o_gemeo_sem_ordem(logado):
    con = _con(logado)
    with con:
        _nascimento(con, nome="GEMEO SEM ORDEM")
    html = _abrir(logado)
    assert "GEMEO SEM ORDEM" in html
    assert "Sem a ordem de nascimento (1)" in html


def test_gravar_a_ordem_tira_da_lista(logado):
    con = _con(logado)
    with con:
        a = _nascimento(con, nome="PRIMEIRO", numero=1)
        b = _nascimento(con, nome="SEGUNDO", numero=2)
    html = logado["cliente"].get("/rcpn/gemeos").get_data(as_text=True)
    r = logado["cliente"].post(
        "/rcpn/gemeos",
        data={"csrf_token": _token(html), "assento_id": str(a),
              "irmao_id": str(b), "ordem": "1"}, follow_redirects=True)
    saida = _liso(r.get_data(as_text=True))
    assert "Ordem de nascimento registrada" in saida
    assert "PRIMEIRO" not in saida.split("Sem a ordem")[1][:400]


def test_gravar_com_ordem_zero_volta_avisando(logado):
    """Erro de regra não é HTTP 500."""
    con = _con(logado)
    with con:
        a = _nascimento(con, nome="A", numero=1)
        b = _nascimento(con, nome="B", numero=2)
    html = logado["cliente"].get("/rcpn/gemeos").get_data(as_text=True)
    r = logado["cliente"].post(
        "/rcpn/gemeos",
        data={"csrf_token": _token(html), "assento_id": str(a),
              "irmao_id": str(b), "ordem": "0"}, follow_redirects=True)
    assert "começa em 1" in _liso(r.get_data(as_text=True))


def test_gravar_sem_irmao_volta_avisando(logado):
    con = _con(logado)
    with con:
        a = _nascimento(con, nome="A")
    html = logado["cliente"].get("/rcpn/gemeos").get_data(as_text=True)
    r = logado["cliente"].post(
        "/rcpn/gemeos",
        data={"csrf_token": _token(html), "assento_id": str(a),
              "irmao_id": "", "ordem": "1"}, follow_redirects=True)
    saida = _liso(r.get_data(as_text=True))
    assert "não existe" in saida or "Informe o assento" in saida


def test_a_tela_vazia_diz_o_que_falta_marcar(logado):
    """Assento de parto múltiplo em que ninguém marcou o campo do IBGE não
    aparece aqui — e a tela vazia diz isso, em vez de parecer casa em dia."""
    html = _abrir(logado)
    assert "Nenhum assento de parto múltiplo" in html
    assert "o que falta é a marca" in html


def test_so_abrir_a_tela_nao_grava_nada(logado):
    con = _con(logado)
    with con:
        aid = _nascimento(con, nome="MARIA")
    antes = dict(_con(logado).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    _abrir(logado)
    depois = dict(_con(logado).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    assert antes == depois


def test_esta_no_menu(logado):
    assert "Gêmeos" in _abrir(logado)

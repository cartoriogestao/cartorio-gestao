"""O mutirão do art. 347 — o CPF dos assentos anteriores a 14/11/2017.

O QUE ESTES TESTES GUARDAM
    **Que o CPF se AVERBA e o resto se ANOTA.** O artigo usa dois verbos, e não é
    descuido de redação: são os dois atos que a inspeção cobra separados. Pôr o
    CPF numa anotação seria lavrar o ato errado num assento — e ninguém percebe,
    porque os dois aparecem à margem.

    **Que ele alcança as TRÊS espécies** — nascimento, casamento e óbito —, e não
    só o nascimento.

    **Que é «DNI OU RG»**, e não os dois: exigir ambos poria em pendência quem já
    está em ordem.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_dados_cadastrais as DC                                 # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento(con, *, data_ato="2010-05-03", especie="NASCIMENTO",
             nome="MARIA", numero=1, documentos=()):
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em)
           VALUES ('RC_A',?,?,?,?,?,'ATIVO','SISTEMA',?)""",
        (especie, numero, nome, data_ato, data_ato, AGORA))
    aid = int(cur.lastrowid)
    for tipo, numero_doc in documentos:
        con.execute(
            """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
                   documento_tipo, documento_numero, criado_em)
               VALUES (?,'REGISTRADO',?,?,?,?,?)""",
            (aid, nome, nome.lower(), tipo, numero_doc, AGORA))
    return aid


# ------------------------------------------------ a norma


def test_o_cpf_se_averba_e_o_resto_se_anota():
    """O artigo usa dois verbos, e não é descuido: pôr o CPF numa anotação seria
    lavrar o ato errado num assento."""
    assert [x["chave"] for x in DC.O_QUE_SE_AVERBA] == ["CPF"]
    assert DC.O_QUE_SE_AVERBA[0]["tipo_de_ato"] == "AVERBACAO"
    anotados = {x["chave"] for x in DC.O_QUE_SE_ANOTA}
    assert {"DNI", "RG", "TITULO_ELEITOR"} <= anotados
    assert all(x["tipo_de_ato"] == "ANOTACAO" for x in DC.O_QUE_SE_ANOTA)
    assert "CPF" not in anotados


def test_alcanca_as_tres_especies():
    """Nascimento, casamento **e óbito**."""
    assert DC.ESPECIES == ("NASCIMENTO", "CASAMENTO", "OBITO")


def test_o_corte_e_a_vigencia_do_provimento_63():
    assert DC.PROVIMENTO_63 == "2017-11-14"
    assert "revogado" in DC.POR_QUE_ESSA_DATA


def test_as_tres_condicoes_estao_escritas():
    """«quando possível», «de forma gratuita» e «mediante conferência» — e
    nenhuma é enfeite."""
    chaves = {x["chave"] for x in DC.CONDICOES}
    assert chaves == {"QUANDO_POSSIVEL", "GRATUITA", "CONFERENCIA"}
    for c in DC.CONDICOES:
        assert c["o_que_quer_dizer"], f"{c['chave']} sem explicação"


def test_e_dni_OU_rg():
    """Exigir os dois poria em pendência quem já está em ordem."""
    assert DC.UM_OU_OUTRO == ("DNI", "RG")


# ------------------------------------------------ quem o artigo alcança


def test_antes_do_corte_entra_e_depois_nao():
    assert DC.alcanca("2010-05-03")
    assert DC.alcanca("2017-11-13")
    assert not DC.alcanca("2017-11-14")     # o dia da vigência já é depois
    assert not DC.alcanca("2020-01-01")


def test_data_ilegivel_nao_entra():
    """Entrar por não saber poria na lista assentos que já têm o CPF — e a lista
    existe para o mutirão."""
    for ruim in (None, "", "03/05/2010", "sem data"):
        assert not DC.alcanca(ruim), f"«{ruim}» não devia entrar"


# ------------------------------------------------ o que falta


def test_assento_sem_nada_falta_tudo():
    falta = DC.o_que_falta([], [])
    assert falta["averbar"] == ["CPF"]
    assert "DNI ou RG" in falta["anotar"]
    assert "título de eleitor" in falta["anotar"]
    assert not falta["completo"]


def test_so_o_rg_ja_resolve_a_identidade():
    falta = DC.o_que_falta(
        [{"documento_tipo": "RG", "documento_numero": "123"}], [])
    assert "DNI ou RG" not in falta["anotar"]
    assert falta["averbar"] == ["CPF"]


def test_com_tudo_o_assento_sai_da_lista():
    falta = DC.o_que_falta([
        {"documento_tipo": "CPF", "documento_numero": "1"},
        {"documento_tipo": "DNI", "documento_numero": "2"},
        {"documento_tipo": "TITULO_ELEITOR", "documento_numero": "3"}], [])
    assert falta["completo"]


def test_documento_sem_numero_nao_conta():
    """Linha de documento vazia afirma que há documento e não diz qual."""
    falta = DC.o_que_falta(
        [{"documento_tipo": "CPF", "documento_numero": "  "}], [])
    assert falta["averbar"] == ["CPF"]


def test_a_averbacao_ja_lavrada_tira_o_cpf_da_lista():
    """O CPF pode ter sido averbado sem estar na linha da pessoa — e um assento
    que já recebeu a averbação não volta para o mutirão."""
    falta = DC.o_que_falta(
        [], [{"tipo": "AVERBACAO",
              "teor": "Averbo o CPF n.º 000.000.000-00, art. 347."}])
    assert falta["averbar"] == []


def test_uma_anotacao_qualquer_nao_conta_como_averbacao_do_cpf(casa):
    """São atos diferentes — e é o ponto do artigo."""
    falta = DC.o_que_falta(
        [], [{"tipo": "ANOTACAO", "teor": "Anoto o CPF ..."}])
    assert falta["averbar"] == ["CPF"]


# ------------------------------------ o casamento tem DOIS principais


def test_casamento_sem_nada_falta_o_CPF_dos_DOIS_nubentes():
    falta = DC.o_que_falta([], [], especie="CASAMENTO")
    assert falta["averbar"] == [
        "CPF (primeiro nubente)", "CPF (segundo nubente)"]
    assert not falta["completo"]


def test_casamento_so_o_primeiro_nubente_tem_cpf_o_segundo_continua_faltando():
    """O defeito relatado: «só averba 1 CPF» — o segundo nubente sumia da
    lista assim que o primeiro tivesse o dele."""
    falta = DC.o_que_falta(
        [{"papel": "NUBENTE1", "documento_tipo": "CPF",
          "documento_numero": "1"}],
        [], especie="CASAMENTO")
    assert falta["averbar"] == ["CPF (segundo nubente)"]
    assert not falta["completo"]


def test_casamento_com_os_dois_cpfs_sai_da_lista():
    falta = DC.o_que_falta(
        [{"papel": "NUBENTE1", "documento_tipo": "CPF",
          "documento_numero": "1"},
         {"papel": "NUBENTE2", "documento_tipo": "CPF",
          "documento_numero": "2"},
         {"papel": "NUBENTE1", "documento_tipo": "RG",
          "documento_numero": "3"},
         {"papel": "NUBENTE1", "documento_tipo": "TITULO_ELEITOR",
          "documento_numero": "4"},
         {"papel": "NUBENTE2", "documento_tipo": "DNI",
          "documento_numero": "5"},
         {"papel": "NUBENTE2", "documento_tipo": "TITULO_ELEITOR",
          "documento_numero": "6"}],
        [], especie="CASAMENTO")
    assert falta["completo"]


def test_casamento_o_cpf_de_um_nao_conta_para_o_outro():
    """O mesmo documento gravado no NUBENTE1 não resolve o NUBENTE2 — são
    pessoas diferentes, e cada uma com o seu próprio CPF."""
    falta = DC.o_que_falta(
        [{"papel": "NUBENTE1", "documento_tipo": "CPF",
          "documento_numero": "1"},
         {"papel": "NUBENTE1", "documento_tipo": "DNI",
          "documento_numero": "2"},
         {"papel": "NUBENTE1", "documento_tipo": "TITULO_ELEITOR",
          "documento_numero": "3"}],
        [], especie="CASAMENTO")
    assert "CPF (segundo nubente)" in falta["averbar"]
    assert "DNI ou RG (segundo nubente)" in falta["anotar"]
    assert "título de eleitor (segundo nubente)" in falta["anotar"]
    # ... e o primeiro nubente, esse sim, já está completo.
    assert "CPF (primeiro nubente)" not in falta["averbar"]


def test_nascimento_e_obito_continuam_sem_papel_nenhum_como_antes():
    """Passar `especie` que não seja o casamento não muda nada — a régua
    continua sendo «alguma pessoa tem?», como sempre foi."""
    falta_nasc = DC.o_que_falta(
        [{"documento_tipo": "CPF", "documento_numero": "1"}], [],
        especie="NASCIMENTO")
    assert falta_nasc["averbar"] == []
    falta_obito = DC.o_que_falta(
        [{"documento_tipo": "CPF", "documento_numero": "1"}], [],
        especie="OBITO")
    assert falta_obito["averbar"] == []


# ------------------------------------------------ a lista


def test_a_lista_traz_so_o_que_o_artigo_alcanca(casa):
    con = _con(casa)
    with con:
        _assento(con, data_ato="2010-05-03", nome="ANTIGO", numero=1)
        _assento(con, data_ato="2020-05-03", nome="NOVO", numero=2)
    assert [x["nome"] for x in DC.pendentes(con)] == ["ANTIGO"]


def test_a_lista_traz_as_tres_especies(casa):
    con = _con(casa)
    with con:
        _assento(con, especie="NASCIMENTO", nome="A", numero=1)
        _assento(con, especie="CASAMENTO", nome="B", numero=2)
        _assento(con, especie="OBITO", nome="C", numero=3)
    assert len(DC.pendentes(con)) == 3


def test_a_lista_vem_do_mais_antigo(casa):
    """O mutirão começa pelos que estão há mais tempo sem."""
    con = _con(casa)
    with con:
        _assento(con, data_ato="2015-01-01", nome="MENOS VELHO", numero=1)
        _assento(con, data_ato="1990-01-01", nome="MAIS VELHO", numero=2)
    assert DC.pendentes(con)[0]["nome"] == "MAIS VELHO"


def test_o_completo_sai_da_lista(casa):
    con = _con(casa)
    with con:
        _assento(con, nome="COMPLETO", numero=1,
                 documentos=(("CPF", "1"), ("RG", "2"),
                             ("TITULO_ELEITOR", "3")))
        _assento(con, nome="FALTANDO", numero=2)
    assert [x["nome"] for x in DC.pendentes(con)] == ["FALTANDO"]


def test_o_cancelado_nao_entra(casa):
    con = _con(casa)
    with con:
        aid = _assento(con, nome="CANCELADO")
        con.execute("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=?",
                    (aid,))
    assert DC.pendentes(con) == []


def test_o_livro_e_nao_o_registro_nao_entra(casa):
    """O art. 347 fala de nascimento, casamento e óbito."""
    con = _con(casa)
    with con:
        _assento(con, especie="UNIAO_ESTAVEL", nome="OUTRO")
    assert DC.pendentes(con) == []


# ------------------------------------------------ o resumo


def test_o_resumo_conta_por_especie(casa):
    con = _con(casa)
    with con:
        _assento(con, especie="NASCIMENTO", nome="A", numero=1)
        _assento(con, especie="NASCIMENTO", nome="B", numero=2)
        _assento(con, especie="OBITO", nome="C", numero=3)
    r = DC.resumo(con)
    assert r["total"] == 3
    assert r["por_especie"]["NASCIMENTO"] == 2
    assert r["por_especie"]["OBITO"] == 1
    assert r["por_especie"]["CASAMENTO"] == 0


def test_o_resumo_separa_quem_so_precisa_do_cpf(casa):
    """São dois trabalhos diferentes: um é averbação, o outro é anotação."""
    con = _con(casa)
    with con:
        _assento(con, nome="SO CPF", numero=1,
                 documentos=(("RG", "2"), ("TITULO_ELEITOR", "3")))
        _assento(con, nome="TUDO", numero=2)
    assert DC.resumo(con)["so_cpf"] == 1


def test_casa_vazia_da_zero(casa):
    assert DC.quantas_pendentes(_con(casa)) == 0


# ------------------------------------------------ o módulo não busca nem lavra


def test_o_modulo_nao_busca_cpf_em_lugar_nenhum():
    """«mediante conferência» — o número não se copia do que o interessado diz:
    confere-se. Um sistema que buscasse o CPF numa base e o averbasse estaria
    dispensando exatamente a conferência que o artigo exige."""
    codigo = (RAIZ / "rc_dados_cadastrais.py").read_text(encoding="utf-8")
    for proibido in ("import requests", "import urllib", "receita",
                     "serpro"):
        assert proibido not in codigo.lower(), \
            f"o módulo tenta buscar CPF com «{proibido}»"


def test_o_modulo_nao_lavra_ato():
    """Quem lavra é a tela do RCPN, que tem o livro, o selo e os emolumentos."""
    codigo = (RAIZ / "rc_dados_cadastrais.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert proibido not in codigo, f"o módulo escreve com «{proibido}»"


# ------------------------------------------------ a tela


def _token_de(html):
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def logado(casa):
    c = casa["app"].test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token_de(
                     c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    casa["cliente"] = c
    return casa


def _liso(t):
    return " ".join((t or "").split())


def _abrir(logado, url="/rcpn/dados-cadastrais"):
    r = logado["cliente"].get(url)
    assert r.status_code == 200, f"{url} nao abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


def test_a_tela_diz_os_dois_verbos(logado):
    """São dois atos, e trocar um pelo outro é lavrar o ato errado."""
    html = _abrir(logado)
    assert "São dois verbos, e dois atos" in html
    assert "art. 347" in html


def test_a_tela_diz_as_tres_condicoes(logado):
    html = _abrir(logado)
    for texto in ("quando possível", "de forma gratuita",
                  "mediante conferência"):
        assert texto in html


def test_a_tela_diz_que_nao_busca_cpf(logado):
    """Um programa que buscasse o número e o averbasse estaria dispensando
    exatamente a conferência que a norma manda fazer."""
    html = _abrir(logado)
    assert "não busca CPF em lugar nenhum" in html


def test_a_tela_lista_o_assento_antigo(logado):
    con = _con(logado)
    with con:
        _assento(con, data_ato="2010-05-03", nome="MARIA ANTIGA")
    html = _abrir(logado)
    assert "MARIA ANTIGA" in html
    assert "Total" in html


def test_a_tela_separa_averbar_de_anotar(logado):
    con = _con(logado)
    with con:
        _assento(con, nome="SO FALTA CPF",
                 documentos=(("RG", "1"), ("TITULO_ELEITOR", "2")))
    html = _abrir(logado)
    assert "SO FALTA CPF" in html
    assert "precisam só da averbação do CPF" in html


def test_a_tela_vazia_explica_o_tamanho_do_acervo(logado):
    """Lista vazia que só mostra nada faz o operador achar que o mutirão não
    existe — e ele existe: o acervo é 1% do livro."""
    html = _abrir(logado)
    assert "Nenhum assento antigo" in html
    assert "1% do livro" in html


def test_a_tela_nao_grava_nada(logado):
    con = _con(logado)
    with con:
        aid = _assento(con, nome="MARIA")
    antes = dict(_con(logado).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    _abrir(logado)
    depois = dict(_con(logado).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    assert antes == depois


def test_esta_no_menu(logado):
    assert "CPF nos assentos antigos" in _abrir(logado)


def test_cpf_registrado_no_assento_tira_da_lista():
    """Honrar a coluna evita devolver ao mutirão quem já tem o CPF gravado."""
    falta = DC.o_que_falta([], [], cpf_registrado="13672050342")
    assert falta["averbar"] == []
    falta_vazio = DC.o_que_falta([], [], cpf_registrado="  ")
    assert falta_vazio["averbar"] == ["CPF"]

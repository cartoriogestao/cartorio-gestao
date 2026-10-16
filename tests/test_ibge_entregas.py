"""O que já foi ao IBGE — o buraco que o painel declarava.

O QUE ESTES TESTES GUARDAM
    **Que o mapa é do que se REGISTROU no trimestre, e não do que aconteceu.**
    Um nascimento de dezembro registrado em janeiro entra no mapa de janeiro;
    usar a data do fato poria o registro tardio num trimestre já entregue.

    **Que só conta o que ESTE sistema lavrou.** Os assentos que vieram do acervo
    já foram entregues pelo E-Ofício — dizer que não foram seria alarme falso
    sobre setenta anos de livro.

    **Que o vencimento é o dia 8 do mês seguinte ao fim do trimestre**, e o IBGE
    é o único destino com multa em dinheiro: de 1 a 5 salários mínimos, «sem
    prejuízo da ação penal».
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ibge_geracao as IBGE                                      # noqa: E402

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


def _assento(con, *, data_ato, nome="MARIA", numero=1, origem="SISTEMA",
             especie="NASCIMENTO"):
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em)
           VALUES ('RC_A',?,?,?,?,?,'ATIVO',?,?)""",
        (especie, numero, nome, data_ato, data_ato, origem, AGORA))
    return int(cur.lastrowid)


# ------------------------------------------------ a norma


def test_o_artigo_o_prazo_e_a_sancao_estao_escritos():
    """É o único destino com multa em dinheiro."""
    assert "art. 224" in IBGE.ARTIGO
    assert "dia 8" in IBGE.PRAZO
    assert "1 a 5 salários mínimos" in IBGE.SANCAO
    assert "ação penal" in IBGE.SANCAO


# ------------------------------------------------ os trimestres


def test_o_trimestre_sai_da_data_do_ASSENTO(casa):
    """O mapa é do que se REGISTROU. Um nascimento de dezembro registrado em
    janeiro entra no mapa de janeiro — usar a data do fato poria o registro
    tardio num trimestre já entregue."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',1,'MARIA','2026-01-15',
                       '2025-12-20','ATIVO','SISTEMA',?)""", (AGORA,))
    t = IBGE.trimestres_com_movimento(con)
    assert [(x["ano"], x["trimestre"]) for x in t] == [(2026, 1)]


def test_os_quatro_trimestres_batem_com_os_meses(casa):
    con = _con(casa)
    with con:
        for i, mes in enumerate(("01", "04", "07", "10"), start=1):
            _assento(con, data_ato=f"2026-{mes}-15", numero=i)
    t = IBGE.trimestres_com_movimento(con)
    assert [x["trimestre"] for x in t] == [1, 2, 3, 4]


def test_o_cancelado_nao_conta(casa):
    con = _con(casa)
    with con:
        aid = _assento(con, data_ato="2026-01-15")
        con.execute("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=?",
                    (aid,))
    assert IBGE.trimestres_com_movimento(con) == []


def test_data_ilegivel_nao_derruba_a_conta(casa):
    """Assento sem data não some do livro, mas não dá para dizer de que
    trimestre ele é."""
    con = _con(casa)
    with con:
        _assento(con, data_ato="sem data", numero=1)
        _assento(con, data_ato="2026-01-15", numero=2)
    assert len(IBGE.trimestres_com_movimento(con)) == 1


# ------------------------------------------------ o que falta prestar


def test_so_conta_o_que_este_sistema_lavrou(casa):
    """Os assentos do acervo já foram entregues pelo E-Ofício. Dizer que não
    foram seria alarme falso sobre setenta anos de livro."""
    con = _con(casa)
    with con:
        _assento(con, data_ato="2026-01-15", origem="EOFICIO", numero=1)
    assert IBGE.a_prestar(con, hoje="2026-08-20") == []
    with con:
        _assento(con, data_ato="2026-01-20", origem="SISTEMA", numero=2)
    faltando = IBGE.a_prestar(con, hoje="2026-08-20")
    assert [(x["ano"], x["trimestre"]) for x in faltando] == [(2026, 1)]


def test_o_trimestre_que_ainda_nao_venceu_nao_entra(casa):
    """O 3º trimestre vence em 8 de outubro; em agosto ele ainda está correndo,
    e cobrar agora seria cobrar prazo que não existe."""
    con = _con(casa)
    with con:
        _assento(con, data_ato="2026-07-15")
    assert IBGE.a_prestar(con, hoje="2026-08-20") == []
    assert IBGE.a_prestar(con, hoje="2026-10-09")


def test_o_dia_do_vencimento_ainda_esta_no_prazo(casa):
    """No dia 8 ainda dá para mandar."""
    con = _con(casa)
    with con:
        _assento(con, data_ato="2026-07-15")
    assert IBGE.a_prestar(con, hoje="2026-10-08") == []


def test_o_quarto_trimestre_vence_em_janeiro_do_ano_seguinte(casa):
    con = _con(casa)
    with con:
        _assento(con, data_ato="2026-11-15")
    assert IBGE.a_prestar(con, hoje="2026-12-31") == []
    faltando = IBGE.a_prestar(con, hoje="2027-01-09")
    assert faltando[0]["vencia_em"] == "2027-01-08"
    assert faltando[0]["trimestre"] == 4


def test_o_atraso_sai_em_dias(casa):
    con = _con(casa)
    with con:
        _assento(con, data_ato="2026-02-15")
    faltando = IBGE.a_prestar(con, hoje="2026-04-18")
    assert faltando[0]["vencia_em"] == "2026-04-08"
    assert faltando[0]["atrasado_ha"] == 10


# ------------------------------------------------ registrar a entrega


def test_registrar_tira_o_trimestre_da_lista(casa):
    """FECHA O BURACO QUE O PAINEL DECLARAVA: até aqui o sistema montava o mapa e
    não guardava o que saiu."""
    con = _con(casa)
    with con:
        _assento(con, data_ato="2026-01-15")
    assert IBGE.a_prestar(con, hoje="2026-08-20")
    with con:
        IBGE.registrar_entrega(con, ano=2026, trimestre=1,
                               teor="21987650501226A24...", quantos=1,
                               agora=AGORA, por="mario", canal="IBGE Coleta")
    assert IBGE.a_prestar(con, hoje="2026-08-20") == []


def test_o_teor_congela_com_hash(casa):
    """Numa correição é ele que se mostra, e o art. 224 pune com multa."""
    con = _con(casa)
    with con:
        IBGE.registrar_entrega(con, ano=2026, trimestre=1, teor="ABC",
                               quantos=3, agora=AGORA, por="mario")
    linha = dict(con.execute("SELECT * FROM ib_entregas").fetchone())
    assert linha["teor"] == "ABC"
    assert len(linha["hash_teor"]) == 64
    assert linha["quantos"] == 3


def test_nao_se_registra_o_mesmo_trimestre_duas_vezes(casa):
    """Duas linhas fariam a lista dizer que ele foi entregue e a correição achar
    dois arquivos diferentes."""
    con = _con(casa)
    with con:
        IBGE.registrar_entrega(con, ano=2026, trimestre=1, teor="ABC",
                               quantos=1, agora=AGORA, por="mario")
    with pytest.raises(ValueError) as erro:
        with con:
            IBGE.registrar_entrega(con, ano=2026, trimestre=1, teor="XYZ",
                                   quantos=1, agora=AGORA, por="mario")
    assert "já está registrado" in str(erro.value)


def test_nao_se_registra_entrega_sem_arquivo(casa):
    con = _con(casa)
    with pytest.raises(ValueError):
        with con:
            IBGE.registrar_entrega(con, ano=2026, trimestre=1, teor="",
                                   quantos=0, agora=AGORA, por="mario")


def test_trimestre_fora_da_faixa_recusa(casa):
    con = _con(casa)
    for t in (0, 5):
        with pytest.raises(ValueError):
            with con:
                IBGE.registrar_entrega(con, ano=2026, trimestre=t, teor="ABC",
                                       quantos=1, agora=AGORA, por="mario")


# ------------------------------------------------ o painel volta a contar


def test_o_painel_conta_o_ibge_agora(casa):
    """Até 30/08/2026 a linha do IBGE mostrava só o prazo, porque o sistema
    montava o mapa e não guardava o que saiu."""
    import rc_obrigacoes as OB
    con = _con(casa)
    with con:
        _assento(con, data_ato="2026-01-15")
    linha = [x for x in OB.painel(con, hoje="2026-08-20")
             if x["chave"] == "IBGE"][0]
    assert linha["quantas"] == 1
    assert linha["vence_em"] == "2026-10-08"
    assert not linha.get("buraco"), \
        "o buraco foi fechado — a linha não pode continuar declarando-o"


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


def test_a_tela_mostra_os_trimestres_em_atraso(logado):
    """O IBGE é o único destino com multa em dinheiro, e o atraso tem de estar à
    vista de quem abre a tela."""
    con = _con(logado)
    with con:
        _assento(con, data_ato="2026-01-15")
    html = _liso(logado["cliente"].get("/rcpn/ibge").get_data(as_text=True))
    assert "Trimestres em atraso (1)" in html
    assert "1 a 5 salários mínimos" in html


def test_a_tela_explica_que_so_conta_o_que_esta_casa_lavrou(logado):
    con = _con(logado)
    with con:
        _assento(con, data_ato="2026-01-15")
    html = _liso(logado["cliente"].get("/rcpn/ibge").get_data(as_text=True))
    assert "só o que este sistema lavrou" in html
    assert "acusar setenta anos de livro" in html


def test_a_tela_mostra_o_trimestre_ja_entregue(logado):
    """GERAR NÃO É ENTREGAR, e por muito tempo o sistema só sabia gerar.

    **O POST FELIZ NÃO SE ENSAIA AQUI de propósito**: para o montador devolver
    linha é preciso um assento inteiro — pessoas, município, DNV —, e montar um
    aqui provaria o montador e não a tela. O que esta tela tem de fazer é
    **mostrar o que já foi entregue**, e é isso que se confere; o registro em si
    está provado no módulo, com dado controlado.
    """
    con = _con(logado)
    with con:
        _assento(con, data_ato="2026-01-15")
        IBGE.registrar_entrega(con, ano=2026, trimestre=1, teor="ABC",
                               quantos=1, agora=AGORA, por="mario",
                               canal="IBGE Coleta", protocolo="2026/123")
    html = _liso(logado["cliente"].get(
        "/rcpn/ibge?ano=2026&trimestre=1").get_data(as_text=True))
    assert "já está registrado como entregue" in html
    assert "IBGE Coleta" in html
    assert "2026/123" in html
    assert "Trimestres em atraso" not in html


def test_registrar_sem_linhas_avisa_em_vez_de_gravar(logado):
    """Registrar entrega de trimestre vazio afirmaria ao IBGE uma remessa que
    não houve — e a marca ficaria como prova de uma coisa que não aconteceu."""
    html = logado["cliente"].get(
        "/rcpn/ibge?ano=2026&trimestre=1").get_data(as_text=True)
    r = logado["cliente"].post(
        "/rcpn/ibge",
        data={"csrf_token": _token_de(html), "ano": "2026", "trimestre": "1",
              "acao": "entreguei"}, follow_redirects=True)
    assert "não tem linhas" in _liso(r.get_data(as_text=True))
    assert _con(logado).execute(
        "SELECT COUNT(*) FROM ib_entregas").fetchone()[0] == 0


def test_so_abrir_a_tela_nao_grava_nada(logado):
    """Montar o arquivo é ler o que já está lavrado. Quem grava é o botão."""
    con = _con(logado)
    with con:
        _assento(con, data_ato="2026-01-15")
    logado["cliente"].get("/rcpn/ibge")
    logado["cliente"].get("/rcpn/ibge")
    assert _con(logado).execute(
        "SELECT COUNT(*) FROM ib_entregas").fetchone()[0] == 0

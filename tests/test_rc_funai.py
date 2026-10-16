"""A comunicação à FUNAI — art. 253, § 2º, e o prazo é «imediatamente».

O QUE ESTES TESTES GUARDAM
    **Que a etnia não se tira do sobrenome.** Nos quatro casos desta casa o
    sobrenome é «KRIKATI», e o § 1º até permite que o povo seja lançado assim —
    **a pedido do declarante**, e não por obrigação. Uma regra que lesse a etnia
    do nome acertaria os quatro e erraria o primeiro que chegasse sem ele, ou
    tiraria de um sobrenome comum uma etnia que não é.

    **Que a comparação da cor é sem acento.** O acervo guarda «Indigena» e o
    balcão vai digitar «Indígena»; `UPPER` do SQLite é ASCII e não resolveria —
    é a armadilha que deixou o CNIB sem achar ninguém por nome.

    **Que o prazo é em dias corridos.** Os prazos em dias úteis desta casa são
    assim porque o artigo qualifica; o art. 253, § 2º diz «imediatamente», e
    contar em dias úteis emprestaria a esta obrigação uma folga que a norma não
    deu.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_funai as FUNAI                                         # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"
CASA = {"nome": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO", "cns": "000000"}


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


def _nascimento(con, *, nome="CAMILO KRIKATI", cor="Indigena", numero=1,
                data_ato="2026-08-05", especie="NASCIMENTO"):
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, cor_raca)
           VALUES ('RC_A',?,?,?,?,?,'ATIVO','SISTEMA',?,?)""",
        (especie, numero, nome, data_ato, data_ato, AGORA, cor))
    return int(cur.lastrowid)


# ------------------------------------------------ a norma


def test_o_prazo_e_imediatamente():
    """É o único prazo da casa que não se conta em dias — e prazo sem número é
    prazo que ninguém sente vencer."""
    assert FUNAI.PRAZO == "imediatamente"
    assert "art. 253" in FUNAI.ARTIGO


def test_o_para_que_serve_esta_escrito():
    """Não é estatística: é o RANI, o papel com que a pessoa se apresenta à FUNAI
    a vida inteira."""
    assert "RANI" in FUNAI.PARA_QUE_SERVE


def test_o_que_o_sistema_pergunta_em_vez_de_deduzir():
    assert {x["campo"] for x in FUNAI.O_QUE_SE_PERGUNTA} == {"etnia", "aldeia"}
    for x in FUNAI.O_QUE_SE_PERGUNTA:
        assert x["porque"], f"{x['campo']} sem o motivo escrito"


# ------------------------------------------------ a cor


def test_indigena_com_e_sem_acento():
    """O acervo guarda «Indigena» e o balcão vai digitar «Indígena»."""
    assert FUNAI.e_indigena("Indigena")
    assert FUNAI.e_indigena("Indígena")
    assert FUNAI.e_indigena("  INDÍGENA  ")


def test_o_que_nao_e_indigena():
    for cor in ("Parda", "Branca", "Ignorada", "", None):
        assert not FUNAI.e_indigena(cor), f"«{cor}» não devia entrar"


# ------------------------------------------------ os dias


def test_os_dias_sao_corridos():
    """O art. 253, § 2º não qualifica: diz «imediatamente». Contar em dias úteis
    emprestaria uma folga que a norma não deu."""
    # 05/08 a 10/08 de 2026 tem um fim de semana no meio; corridos, são 5.
    assert FUNAI.dias_desde("2026-08-05", hoje="2026-08-10") == 5


def test_data_ilegivel_nao_vira_zero():
    """Zero diria «foi hoje», que é afirmação; não saber é outra coisa."""
    assert FUNAI.dias_desde(None, hoje="2026-08-10") is None
    assert FUNAI.dias_desde("05/08/2026", hoje="2026-08-10") is None


def test_o_ponto_de_chamar_atencao_e_da_casa_e_nao_da_norma():
    """A norma não dá número. Este é da casa, e é por isso que ele tem nome."""
    assert FUNAI.DIAS_PARA_CHAMAR_ATENCAO == 5


# ------------------------------------------------ a lista


def test_a_lista_traz_so_o_indigena(casa):
    con = _con(casa)
    with con:
        _nascimento(con, nome="CAMILO KRIKATI", cor="Indigena", numero=1)
        _nascimento(con, nome="MARIA", cor="Parda", numero=2)
        _nascimento(con, nome="JOAO", cor=None, numero=3)
    lista = FUNAI.pendentes(con)
    assert [x["nome"] for x in lista] == ["CAMILO KRIKATI"]


def test_a_lista_vem_do_mais_antigo(casa):
    """O prazo é «imediatamente»: o que espera há mais tempo é o que mais destoa
    da palavra da norma."""
    con = _con(casa)
    with con:
        _nascimento(con, nome="NOVO", numero=1, data_ato="2026-08-05")
        _nascimento(con, nome="VELHO", numero=2, data_ato="2022-12-12")
    assert FUNAI.pendentes(con)[0]["nome"] == "VELHO"


def test_a_lista_marca_quem_ja_passou_do_ponto(casa):
    con = _con(casa)
    with con:
        _nascimento(con, nome="ONTEM", numero=1, data_ato="2026-08-19")
        _nascimento(con, nome="HA MESES", numero=2, data_ato="2026-01-05")
    por_nome = {x["nome"]: x for x in FUNAI.pendentes(con, hoje="2026-08-20")}
    assert por_nome["ONTEM"]["dias"] == 1
    assert not por_nome["ONTEM"]["chama_atencao"]
    assert por_nome["HA MESES"]["chama_atencao"]


def test_o_obito_nao_entra(casa):
    """A comunicação do § 2º é do assento de NASCIMENTO."""
    con = _con(casa)
    with con:
        _nascimento(con, nome="ANTONIO KRIKATI", especie="OBITO", numero=1)
    assert FUNAI.pendentes(con) == []


def test_o_cancelado_nao_entra(casa):
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CAMILO KRIKATI")
        con.execute("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=?",
                    (aid,))
    assert FUNAI.pendentes(con) == []


# ------------------------------------------------ o ofício


def test_o_oficio_cita_o_artigo_e_o_registro_administrativo(casa):
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CECILIA VASCO DOURADO PEIXOTO")
    r = FUNAI.montar(con, aid, serventia=CASA)
    assert "art. 253, § 2º" in r["teor"]
    assert "registro administrativo" in r["teor"]
    assert "CECILIA VASCO DOURADO PEIXOTO" in r["teor"]
    assert "000000" in r["teor"]


def test_o_oficio_marca_o_que_falta_em_vez_de_inventar(casa):
    """A ETNIA NÃO SE TIRA DO SOBRENOME. O «KRIKATI» está ali porque o declarante
    pediu — o § 1º permite, não obriga."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="SUELLEN DA SILVA KRIKATI")
    r = FUNAI.montar(con, aid, serventia=CASA)
    assert "[COMPLETAR: a etnia" in r["teor"]
    assert "[COMPLETAR: a aldeia" in r["teor"]
    assert len(r["faltando"]) == 2
    # e o sobrenome NAO virou etnia sozinho
    assert "família indígena: KRIKATI" not in r["teor"]


def test_o_oficio_com_etnia_e_aldeia_nao_reclama(casa):
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="ISAAC KRIKATI")
    r = FUNAI.montar(con, aid, serventia=CASA, etnia="Krikati",
                     aldeia="São José")
    assert r["faltando"] == []
    assert "Krikati" in r["teor"]
    assert "São José" in r["teor"]


def test_nao_se_comunica_assento_que_nao_e_indigena(casa):
    """O ofício afirma à FUNAI uma coisa que tem de estar no livro."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="MARIA", cor="Parda")
    with pytest.raises(FUNAI.FunaiError) as erro:
        FUNAI.montar(con, aid, serventia=CASA)
    assert "corrija a cor/raça" in str(erro.value)


def test_assento_que_nao_existe_recusa(casa):
    with pytest.raises(FUNAI.FunaiError):
        FUNAI.montar(_con(casa), 9999, serventia=CASA)


# ------------------------------------------------ a saída do aviso


def test_registrar_envio_tira_da_lista(casa):
    """AVISO SEM SAÍDA É AVISO QUE FICA PARA SEMPRE, e na terceira vez ninguém
    lê mais."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CAMILO KRIKATI")
    assert len(FUNAI.pendentes(con)) == 1
    with con:
        FUNAI.registrar_envio(con, aid, agora=AGORA, por="mario",
                              teor="Ofício à FUNAI...", canal="CARTA")
    assert FUNAI.pendentes(con) == []
    assert FUNAI.historico(con)[0]["situacao"] == "ENVIADA"


def test_o_teor_congela_com_hash(casa):
    """É o papel que a serventia afirma ter mandado, e numa correição é ele que
    se mostra."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CAMILO KRIKATI")
        FUNAI.registrar_envio(con, aid, agora=AGORA, por="mario",
                              teor="Ofício à FUNAI...")
    linha = FUNAI.historico(con)[0]
    assert linha["teor"] == "Ofício à FUNAI..."
    assert len(linha["hash_teor"]) == 64


def test_nao_se_registra_envio_sem_oficio(casa):
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CAMILO KRIKATI")
    with pytest.raises(FUNAI.FunaiError):
        with con:
            FUNAI.registrar_envio(con, aid, agora=AGORA, por="mario", teor="")


def test_nao_se_comunica_duas_vezes(casa):
    """Se precisar comunicar de novo, o caminho é ofício novo — e não apagar o
    que saiu."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CAMILO KRIKATI")
        FUNAI.registrar_envio(con, aid, agora=AGORA, por="mario", teor="Ofício")
    with pytest.raises(FUNAI.FunaiError) as erro:
        with con:
            FUNAI.registrar_envio(con, aid, agora=AGORA, por="mario",
                                  teor="Outro")
    assert "já foi comunicado" in str(erro.value)


def test_dispensar_exige_motivo_escrito(casa):
    """Dispensar é decisão do oficial; ignorar não é."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CAMILO KRIKATI")
    with pytest.raises(FUNAI.FunaiError):
        with con:
            FUNAI.dispensar(con, aid, motivo="não", agora=AGORA, por="mario")
    with con:
        FUNAI.dispensar(con, aid,
                        motivo="a cor foi digitada por engano; o assento não é "
                               "de pessoa indígena, conferido no livro",
                        agora=AGORA, por="mario")
    assert FUNAI.pendentes(con) == []
    assert FUNAI.historico(con)[0]["situacao"] == "DISPENSADA"


def test_o_que_se_escreveu_ao_dispensar_fica(casa):
    """Engano se conserta à vista."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="CAMILO KRIKATI")
        FUNAI.dispensar(con, aid, motivo="conferido no livro de papel",
                        agora=AGORA, por="mario")
    assert "conferido no livro" in FUNAI.historico(con)[0]["motivo"]


# ------------------------------------------------ o módulo não envia


def test_o_modulo_nao_envia():
    """Ele monta o ofício e registra que saiu; mandar é passo de quem tem o
    canal."""
    codigo = (RAIZ / "rc_funai.py").read_text(encoding="utf-8")
    for proibido in ("import requests", "import urllib", "import smtplib"):
        assert proibido not in codigo, f"o módulo tenta enviar com «{proibido}»"

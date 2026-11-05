"""O aviso do instrumento - pedido do oficial, 04/11/2026: «não tinha que
avisar isso e forçar a assinatura? eu só descobri porque mandei aqui».

Quatro protestos ficaram fora do XML P do dia sem nenhuma tela avisar. Estes
testes guardam o aviso, e que ele SÓ AVISA:

  - o que fica fora do P diz se falta EMITIR ou ASSINAR o instrumento;
  - a tela do XML avisa antes do botão, e o botão diz quantos estão prontos;
  - a pendência do roteiro diz o que espera e leva aos instrumentos;
  - depois de lavrar (na ficha e no lote) o aviso aparece, e o protesto
    É LAVRADO - nada se trava, nada se emite nem se assina sozinho;
  - o painel do Protesto conta os protestos de hoje sem instrumento.
"""
from __future__ import annotations

from datetime import datetime

import protesto_cenprot_xml as X
import protesto_instrumento as PI
import protesto_roteiro as PR

from test_protesto_aviso_web import _con, _token, s, titulo_apontado  # noqa: F401
from test_protesto_instrumento_assinado import chave_e_cert  # noqa: F401
from test_protesto_cenprot_xml_tela import pronto  # noqa: F401
from test_protesto_prova_web import MOTIVO, atos, intimado, lavrar  # noqa: F401


def _sem_instrumento(s):
    con = _con(s)
    with con:
        con.execute("DELETE FROM as_documentos")
        con.execute("DELETE FROM pt_instrumentos")
    con.close()


def _sem_assinatura(s):
    con = _con(s)
    with con:
        con.execute("UPDATE as_documentos SET caminho_assinado=NULL")
    con.close()


def _instrumentos(s) -> int:
    con = _con(s)
    n = con.execute("SELECT COUNT(*) FROM pt_instrumentos").fetchone()[0]
    con.close()
    return n


# ---------------------------------------------------------------- a regra


def test_com_o_instrumento_assinado_nao_falta_nada(pronto, s):
    con = _con(s)
    assert PI.falta_do_titulo(con, pronto) is None
    assert PI.falta_para_o_xml(con, pronto) is None
    assert not X.pendentes(con, "P")["fora"]


def test_nao_emitido_diz_que_falta_emitir(pronto, s):
    _sem_instrumento(s)
    con = _con(s)
    [fora] = X.pendentes(con, "P")["fora"]
    assert fora["falta"] == PI.FALTA_EMITIR
    assert "ainda não foi emitido" in fora["motivo"]
    assert "assine com o A3" in fora["motivo"]
    assert PI.falta_para_o_xml(con, pronto) == PI.FALTA_EMITIR


def test_emitido_sem_assinatura_diz_que_falta_assinar(pronto, s):
    _sem_assinatura(s)
    con = _con(s)
    [fora] = X.pendentes(con, "P")["fora"]
    assert fora["falta"] == PI.FALTA_ASSINAR
    assert "foi emitido, mas ainda não foi assinado com o A3" in fora["motivo"]
    assert PI.falta_para_o_xml(con, pronto) == PI.FALTA_ASSINAR


def test_o_do_eoficio_nao_se_avisa(pronto, s):
    _sem_instrumento(s)
    con = _con(s)
    with con:
        con.execute("UPDATE pt_atos SET origem='EOFICIO' WHERE tipo='PROTESTO'")
    assert PI.falta_para_o_xml(con, pronto) is None


def test_os_protestos_do_dia_separam_emitir_de_assinar(pronto, s):
    _sem_assinatura(s)
    con = _con(s)
    dia = con.execute("SELECT substr(data_ato, 1, 10) FROM pt_atos WHERE "
                      "tipo='PROTESTO'").fetchone()[0]
    r = PI.protestos_do_dia_sem_instrumento(con, dia)
    assert r["lavrados"] == 1 and r["faltam"] == 1
    assert not r["sem_instrumento"]
    assert r["sem_assinatura"][0]["titulo_id"] == pronto
    assert PI.protestos_do_dia_sem_instrumento(con, "1999-01-01")["faltam"] == 0


def test_a_pendencia_do_roteiro_diz_o_que_espera(pronto, s):
    _sem_assinatura(s)
    con = _con(s)
    ctx = {"agora": datetime(2026, 10, 14, 15, 0), "dia": "2026-10-14"}
    obrigacao = PR._cobrar_xml(con, ctx)[0]
    [item] = obrigacao["lista"]
    assert item["texto"].endswith("esperando assinatura A3")
    assert item["tela"] == "protesto_instrumentos" and item["args"] == {}
    _sem_instrumento(s)
    [item] = PR._cobrar_xml(con, ctx)[0]["lista"]
    assert item["texto"].endswith("esperando instrumento")


# ---------------------------------------------------------------- as telas


def test_a_tela_do_xml_avisa_antes_do_botao(pronto, s):
    _sem_assinatura(s)
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert 'id="aviso-fora-do-p"' in html
    assert "1 protesto(s) NÃO vão no arquivo P de hoje" in html
    assert "Instrumento emitido, falta assinar com o A3 (1)" in html
    assert "Emitir e assinar na tela dos instrumentos" in html
    assert html.index('id="aviso-fora-do-p"') < html.index("protestos lavrados</span>")


def test_a_tela_sem_falta_nao_avisa_e_conta_os_prontos(pronto, s):
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert 'id="aviso-fora-do-p"' not in html
    assert "Gerar o arquivo P de hoje (1 de 1 prontos)" in html


def test_a_ficha_avisa_e_a_do_assinado_nao(pronto, s):
    html = s["c"].get(f"/protesto/{pronto}").get_data(as_text=True)
    assert "data-falta-instrumento" not in html
    _sem_assinatura(s)
    html = s["c"].get(f"/protesto/{pronto}").get_data(as_text=True)
    assert 'data-falta-instrumento="ASSINATURA"' in html
    assert "falta assinar com o A3" in html


def test_a_ficha_que_nao_lavrou_nao_avisa_e_a_lavrada_avisa(s):
    """Na ficha, o ato que NÃO saiu (aqui, o selo sem cobertura) não ganha o
    aviso do instrumento - o aviso não pode parecer lavratura; depois de
    lavrado, a ficha avisa que falta o instrumento, e nada se emite sozinho."""
    from navegador_de_teste import postar_e_seguir
    tid = intimado(s)
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    resposta = postar_e_seguir(
        s["c"], f"/protesto/{tid}/lancar",
        {"csrf_token": _token(html), "ato": "PROTESTO",
         "motivo_atraso": MOTIVO}).get_data(as_text=True)
    assert atos(s, tid) == 0
    assert "Falta emitir e assinar o instrumento" not in resposta
    lavrar(s, [tid])
    assert atos(s, tid) == 1                      # o aviso não trava
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert 'data-falta-instrumento="INSTRUMENTO"' in ficha
    assert "Falta emitir e assinar o instrumento" in ficha
    assert _instrumentos(s) == 0                  # e nada se emitiu sozinho


def test_lavrar_no_lote_avisa_e_o_painel_conta(s):
    tid = intimado(s, numero="com/1")
    resposta = lavrar(s, [tid]).get_data(as_text=True)
    assert atos(s, tid) == 1
    assert "Falta emitir e assinar o instrumento" in resposta
    assert "1 sem instrumento emitido" in resposta
    assert _instrumentos(s) == 0
    painel = s["c"].get("/protesto/roteiro").get_data(as_text=True)
    assert 'id="instrumentos-de-hoje"' in painel
    assert "instrumento ainda não emitido" in painel

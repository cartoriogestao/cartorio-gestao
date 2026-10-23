"""A fila de pré-cadastros do RCPN e o «arrumar só o problema» — 11/10/2026.

    «ao recusar por bloqueio de lavratura, permitir apenas arrumar o problema.
     queremos dar celeridade no preenchimento dos formularios de registros e
     importacoes… qual o caminho mais seguro e rapido para importar, sem ser
     mandar pro robo continuar fazendo o que tem feito?» — o oficial

O QUE ESTES TESTES GUARDAM
    **A recusa abre só o campo que travou**, com o resto guardado, e o botão de
    lavrar fica preso até arrumar. Arrumado ali, lavra.
    **Forçar a lavratura com o dado errado não grava nada.**
    **Termo vazio sai do modelo da casa na lavratura**, a partir dos campos.
    **O arquivo do padrão vira fila de rascunhos**: vários de uma vez, as
    pessoas nas gavetas certas, o termo do arquivo descartado, e o mesmo
    registro não entra duas vezes.

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import importar_padrao as IMPP                                   # noqa: E402
import rc_conferencia_dados as CD                                # noqa: E402
from test_testemunha_fantasma_20261009 import (                  # noqa: E402,F401
    AGORA, FOLHAS, SLUG, _como_o_navegador, _con, _rascunho_nascimento,
    _salvar_rascunho, casa)

CPF_RUIM = "000.000.001-00"
CPF_BOM = "000.000.001-91"


def _abrir_e_conferir(casa, dados):
    c = casa["c"]
    rid = _salvar_rascunho(casa, dados)
    slug = SLUG[dados["especie"]]
    html = c.get(f"/rcpn/novo/{slug}?rascunho_id={rid}",
                 follow_redirects=True).get_data(as_text=True)
    envio = _como_o_navegador(html, ("acao", "conferir"))
    return slug, c.post(f"/rcpn/novo/{slug}", data=envio,
                        follow_redirects=True).get_data(as_text=True)


def _quantos(casa):
    con = _con(casa)
    n = con.execute("SELECT count(*) FROM rc_assentos").fetchone()[0]
    con.close()
    return n


def test_conferencia_abre_so_o_campo_que_travou_e_prende_o_lavrar(casa):
    dados = _rascunho_nascimento()
    dados["filiacao1_documento_numero"] = CPF_RUIM
    slug, conf = _abrir_e_conferir(casa, dados)
    assert "Arrume aqui" in conf
    bloco = conf[conf.index('id="arrumar"'):]
    bloco = bloco[:bloco.index("</form>")]
    editaveis = set(re.findall(r'<input name="([^"]+)"', bloco))
    assert editaveis == {"filiacao1_documento_numero"}
    assert re.search(r'value="lavrar"\s+disabled', conf)
    # arruma ali e confere de novo: o resto veio escondido, como estava
    envio = _como_o_navegador(conf, ("acao", "conferir"),
                              filiacao1_documento_numero=CPF_BOM)
    assert envio["pessoa_nome"] == dados["pessoa_nome"]
    conf2 = casa["c"].post(f"/rcpn/novo/{slug}", data=envio,
                           follow_redirects=True).get_data(as_text=True)
    assert "Arrume aqui" not in conf2
    antes = _quantos(casa)
    lav = _como_o_navegador(conf2, ("acao", "lavrar"), folha_seguranca=FOLHAS[1])
    casa["c"].post(f"/rcpn/novo/{slug}", data=lav, follow_redirects=True)
    assert _quantos(casa) == antes + 1


def test_forcar_a_lavratura_com_dado_errado_nao_grava_e_volta_para_arrumar(casa):
    dados = _rascunho_nascimento()
    dados["filiacao1_documento_numero"] = CPF_RUIM
    slug, conf = _abrir_e_conferir(casa, dados)
    envio = _como_o_navegador(conf, ("acao", "conferir"))   # o form escondido
    envio.update({"acao": "lavrar", "folha_seguranca": FOLHAS[2]})
    antes = _quantos(casa)
    r = casa["c"].post(f"/rcpn/novo/{slug}", data=envio,
                       follow_redirects=True).get_data(as_text=True)
    assert _quantos(casa) == antes
    assert "Arrume aqui" in r and "nada foi gravado" in r.lower()


def test_termo_vazio_sai_do_modelo_da_casa(casa):
    dados = _rascunho_nascimento()
    assert not dados.get("teor")
    slug, conf = _abrir_e_conferir(casa, dados)
    lav = _como_o_navegador(conf, ("acao", "lavrar"), folha_seguranca=FOLHAS[3])
    casa["c"].post(f"/rcpn/novo/{slug}", data=lav, follow_redirects=True)
    con = _con(casa)
    teor = con.execute("SELECT teor FROM rc_assentos ORDER BY id DESC LIMIT 1").fetchone()[0]
    con.close()
    assert teor and "FANTASMA" in CD._so_letras(teor)


def test_termo_pelo_modelo_leva_o_cpf_digitado_na_conferencia(casa):
    """13/10/2026 — «cpf nao constou no termo»: o termo pelo modelo era escrito
    antes de o CPF da conferência ser gravado, e saía sem ele (termo 19582)."""
    from test_testemunha_fantasma_20261009 import _como_o_navegador
    dados = _rascunho_nascimento()
    assert not dados.get("teor")
    slug, conf = _abrir_e_conferir(casa, dados)
    lav = _como_o_navegador(conf, ("acao", "lavrar"), folha_seguranca=FOLHAS[0],
                            cpf_registrado=CPF_BOM)
    casa["c"].post(f"/rcpn/novo/{slug}", data=lav, follow_redirects=True)
    con = _con(casa)
    a = con.execute("SELECT teor, cpf_registrado FROM rc_assentos "
                    "ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert a["cpf_registrado"] == "00000000191"
    assert "no CPF n.º 000.000.001-91" in a["teor"]


def test_termo_pelo_modelo_que_quebra_no_meio_nao_desfaz_a_lavratura(casa, monkeypatch):
    """L056R, 17/10/2026 — no PostgreSQL o SAVEPOINT do termo sumia na hora (o
    RELEASE do savepoint de proteção da ponte o levava junto), e o RELEASE e o
    ROLLBACK TO da rota estouravam: a lavratura inteira voltava atrás. O que se
    guarda aqui é a promessa da rota: o termo que quebra no meio volta atrás
    SOZINHO, e o assento fica lavrado, com o aviso."""
    import rc_termo as RCT
    from bd_nativo import banco

    def _quebra_no_meio(con, assento_id, **_k):
        banco(con).escrever("UPDATE rc_assentos SET teor = %s WHERE id = %s",
                            ("METADE DO TERMO", assento_id))
        raise RCT.TermoError("modelo quebrado de propósito.")

    monkeypatch.setattr(RCT, "congelar", _quebra_no_meio)
    dados = _rascunho_nascimento()
    assert not dados.get("teor")
    slug, conf = _abrir_e_conferir(casa, dados)
    antes = _quantos(casa)
    lav = _como_o_navegador(conf, ("acao", "lavrar"), folha_seguranca=FOLHAS[2])
    r = casa["c"].post(f"/rcpn/novo/{slug}", data=lav, follow_redirects=True)
    assert r.status_code == 200
    assert _quantos(casa) == antes + 1
    con = _con(casa)
    teor = con.execute("SELECT teor FROM rc_assentos ORDER BY id DESC LIMIT 1").fetchone()[0]
    con.close()
    assert not teor                     # a metade do termo voltou atrás
    pagina = r.get_data(as_text=True)
    assert "não pôde ser escrito pelo" in pagina
    assert "modelo quebrado de propósito." in pagina


def test_ponto_de_retorno_que_falha_sobe_como_erro_do_sqlite3():
    """L056R, 18/10/2026 — o `_ponto_de_retorno` manda o comando cru ao
    PostgreSQL, por fora da ponte, e o erro dele subia como `psycopg.Error`.
    Pelo `con.execute` de antes ele subia como o do `sqlite3`, que é o que o
    sistema apanha (armadilha 3 do manual da conversão)."""
    import atribuicoes_web as AW
    from banco_de_teste import conexao_de_teste
    con = conexao_de_teste()
    try:
        with pytest.raises(sqlite3.OperationalError):
            AW._ponto_de_retorno(con, "RELEASE ponto_que_nao_existe")
    finally:
        con.rollback()
        con.close()


# ------------------------------------------------------------- a fila

def _arquivo(registros):
    return json.dumps({"formato": IMPP.FORMATO, "versao": IMPP.VERSAO,
                       "especie": "RCPN_ASSENTO", "de_onde_veio": "DNVs digitalizadas",
                       "registros": registros}, ensure_ascii=False)


def _registro(chave, nome, **k):
    return {"chave": chave, "especie": "NASCIMENTO", "nome": nome,
            "data_fato": "2026-10-01", "dnv": "30-11111111-1", "hora_fato": "08:00",
            "teor": "texto que o robô escreveu e que não pode ir ao livro",
            "pessoas": [{"papel": "REGISTRADO", "nome": nome, "sexo": "M"},
                        {"papel": "MAE", "nome": "MAE EXEMPLO", "sexo": "F"},
                        {"papel": "PAI", "nome": "PAI EXEMPLO", "sexo": "M"},
                        {"papel": "AVO_MATERNA", "nome": "AVO EXEMPLO", "sexo": "F"},
                        *k.get("mais", [])]}


def test_arquivo_vira_fila_de_rascunhos_sem_o_termo_e_sem_repetir(casa):
    texto = _arquivo([
        _registro("dnv-1", "PRIMEIRO EXEMPLO"),
        _registro("dnv-2", "SEGUNDO EXEMPLO",
                  mais=[{"papel": "TESTEMUNHA", "nome": "SEGUNDO EXEMPLO"}]),
    ])
    con = _con(casa)
    with con:
        fila = IMPP.para_rascunhos(con, texto, agora=AGORA, por="ELISA TESTE")
    assert [c["nome"] for c in fila["criados"]] == ["PRIMEIRO EXEMPLO", "SEGUNDO EXEMPLO"]
    assert any("teor" in x for x in fila["criados"][0]["ficou_de_fora"])
    assert fila["criados"][0]["travas"] == []
    assert [p["codigo"] for p in fila["criados"][1]["travas"]] == ["TESTEMUNHA_FANTASMA"]
    dados = json.loads(con.execute(
        "SELECT dados_json FROM rascunhos_de_tela WHERE id=?",
        (fila["criados"][0]["rascunho_id"],)).fetchone()[0])
    assert "teor" not in dados
    assert dados["pessoa_nome"] == "PRIMEIRO EXEMPLO"
    assert dados["filiacao1_nome"] == "MAE EXEMPLO" and dados["filiacao2_nome"] == "PAI EXEMPLO"
    assert dados["prog2f1_nome"] == "AVO EXEMPLO"           # avó materna
    with con:
        de_novo = IMPP.para_rascunhos(con, texto, agora=AGORA, por="ELISA TESTE")
    con.close()
    assert de_novo["criados"] == [] and de_novo["ja_na_fila"] == ["dnv-1", "dnv-2"]


def test_a_tela_de_importar_poe_na_fila(casa):
    c = casa["c"]
    html = c.get("/importar-padrao?especie=RCPN_ASSENTO").get_data(as_text=True)
    assert 'value="rascunhos"' in html
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/importar-padrao", data={
        "csrf_token": token, "especie": "RCPN_ASSENTO", "o_que": "rascunhos",
        "texto": _arquivo([_registro("dnv-9", "TERCEIRO EXEMPLO")])},
        follow_redirects=True)
    assert r.status_code == 200
    con = _con(casa)
    n = con.execute("SELECT count(*) FROM rascunhos_de_tela WHERE chave='arquivo:dnv-9'").fetchone()[0]
    con.close()
    assert n == 1

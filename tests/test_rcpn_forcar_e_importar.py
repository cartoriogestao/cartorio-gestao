"""A saída de emergência da trava e a importação do RCPN — 11/10/2026.

    «como criar um bloqueio parcial que orienta o caminho correto, mas permite,
     em caso de necessidade emergente, fazer no modo bruto de gravar no banco?
     precisamos de uma forma mais intuitiva de importar esse documento e
     precisamos uma forma facil de baixar o manual de preenchimento desse
     arquivo, principalmente relativo a dados das partes.» — o oficial

O QUE ESTES TESTES GUARDAM
    **O oficial lavra por cima da trava, com motivo, e a trava fica gravada**
    ao lado do assento — e a fiscalização do RCPN a mostra com o nome de quem
    forçou. **Motivo curto não passa. O balcão não vê o botão e, se mandar pelo
    endereço, é recusado.**
    **A prévia da importação não grava nada**; a fila grava rascunhos.
    **O modelo de cada espécie tem uma pessoa por papel** e, preenchido, passa
    na conferência. **O manual explica todo papel e todo campo da pessoa**, e
    só cita código de trava que existe.

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gestor_rcpn as GRC                                        # noqa: E402
import importar_padrao as IMPP                                   # noqa: E402
import rc_assento as RC                                          # noqa: E402
import rc_conferencia_dados as CD                                # noqa: E402
from test_fila_e_arrumar_rcpn import (                           # noqa: E402
    CPF_RUIM, _abrir_e_conferir, _arquivo, _quantos, _registro)
from test_testemunha_fantasma_20261009 import (                  # noqa: E402,F401
    AGORA, FOLHAS, SENHA, SLUG, _con, _rascunho_nascimento, _token, casa)

MOTIVO = "DNV original traz este CPF da mãe; retificação será pedida amanhã"


def _conferencia_com_cpf_ruim(casa):
    dados = _rascunho_nascimento()
    dados["filiacao1_documento_numero"] = CPF_RUIM
    return _abrir_e_conferir(casa, dados)


# ------------------------------------------------------- a saída de emergência

def test_motivo_curto_nao_basta():
    assert CD.motivo_insuficiente("urgente")
    assert CD.motivo_insuficiente("  ")
    assert not CD.motivo_insuficiente(MOTIVO)


def test_oficial_lavra_por_cima_da_trava_e_ela_fica_gravada(casa):
    from test_testemunha_fantasma_20261009 import _como_o_navegador
    slug, conf = _conferencia_com_cpf_ruim(casa)
    assert 'value="lavrar_forcado"' in conf          # o ADMIN vê a saída
    antes = _quantos(casa)

    curto = _como_o_navegador(conf, ("acao", "lavrar_forcado"),
                              folha_seguranca=FOLHAS[0], forcar_motivo="urgente")
    r = casa["c"].post(f"/rcpn/novo/{slug}", data=curto,
                       follow_redirects=True).get_data(as_text=True)
    assert _quantos(casa) == antes
    assert "escreva o motivo com pelo menos 15 letras" in r

    bom = _como_o_navegador(conf, ("acao", "lavrar_forcado"),
                            folha_seguranca=FOLHAS[0], forcar_motivo=MOTIVO)
    r = casa["c"].post(f"/rcpn/novo/{slug}", data=bom,
                       follow_redirects=True).get_data(as_text=True)
    assert _quantos(casa) == antes + 1
    assert "POR CIMA DA TRAVA" in r

    con = _con(casa)
    f = con.execute("SELECT * FROM rc_lavraturas_forcadas").fetchone()
    assert f["motivo"] == MOTIVO and f["forcado_por"] == "ELISA TESTE"
    assert [p["codigo"] for p in json.loads(f["travas_json"])] == ["CPF_INVALIDO"]
    assert con.execute("SELECT count(*) FROM audit_logs "
                       "WHERE action='RCPN_LAVRATURA_FORCADA'").fetchone()[0] == 1
    achados = [a for a in GRC.conferir_dados(con, date.today())
               if a["regra"] == "RCPN_DADOS_CONTRADITORIOS"
               and a["chave"].endswith(f":{f['assento_id']}")]
    con.close()
    assert achados and "lavratura forçada" in achados[0]["titulo"]
    assert MOTIVO in achados[0]["detalhe"]


def test_balcao_nao_ve_a_saida_e_nao_consegue_forcar(casa):
    casa["db"].create_user("debora", "DEBORA TESTE", SENHA, "USER")
    c = casa["app"].test_client()
    html = c.get("/login").get_data(as_text=True)
    c.post("/login", data={"username": "debora", "password": SENHA,
                           "csrf_token": _token(html)}, follow_redirects=True)
    dados = _rascunho_nascimento()
    dados["filiacao1_documento_numero"] = CPF_RUIM
    slug = SLUG[dados["especie"]]
    tela = c.get(f"/rcpn/novo/{slug}").get_data(as_text=True)
    conf = c.post(f"/rcpn/novo/{slug}",
                  data={**dados, "acao": "conferir", "csrf_token": _token(tela)},
                  follow_redirects=True).get_data(as_text=True)
    assert "Arrume aqui" in conf and 'value="lavrar_forcado"' not in conf
    antes = _quantos(casa)
    r = c.post(f"/rcpn/novo/{slug}",
               data={**dados, "acao": "lavrar_forcado", "forcar_motivo": MOTIVO,
                     "folha_seguranca": FOLHAS[1], "csrf_token": _token(conf)},
               follow_redirects=True).get_data(as_text=True)
    assert _quantos(casa) == antes
    assert "do oficial ou do substituto" in r


def test_quem_chama_o_dominio_sem_motivo_continua_recusado(casa):
    """O robô que lavra por script não ganha a saída por omissão: sem
    `forcar_motivo` é a recusa de sempre, e com motivo exige o nome."""
    assert "forcar_motivo" in RC.lavrar_assento.__code__.co_varnames
    src = Path(RC.__file__).read_text(encoding="utf-8")
    assert "if forcar_motivo is None:" in src
    assert "exige o nome de quem força" in src


# ------------------------------------------------------- a importação do RCPN

def test_previa_nao_grava_e_mostra_a_trava(casa):
    texto = _arquivo([
        _registro("dnv-p1", "PRIMEIRO PREVIA"),
        _registro("dnv-p2", "SEGUNDO PREVIA",
                  mais=[{"papel": "TESTEMUNHA", "nome": "SEGUNDO PREVIA"}]),
    ])
    con = _con(casa)
    previa = IMPP.previa_da_fila(con, texto, agora=AGORA)
    n = con.execute("SELECT count(*) FROM rascunhos_de_tela").fetchone()[0]
    con.close()
    assert n == 0
    assert [i["nome"] for i in previa["itens"]] == ["PRIMEIRO PREVIA", "SEGUNDO PREVIA"]
    assert previa["itens"][0]["travas"] == []
    assert [p["codigo"] for p in previa["itens"][1]["travas"]] == ["TESTEMUNHA_FANTASMA"]
    assert {"papel": "MAE", "nome": "MAE EXEMPLO"} in previa["itens"][0]["pessoas"]


def test_tela_de_importar_do_rcpn_previa_depois_fila(casa):
    c = casa["c"]
    html = c.get("/rcpn/importar").get_data(as_text=True)
    assert "/rcpn/importar/manual-das-partes" in html
    assert "/rcpn/importar/modelo/NASCIMENTO" in html
    texto = _arquivo([_registro("dnv-t1", "TERCEIRO TELA")])
    r = c.post("/rcpn/importar", data={
        "csrf_token": _token(html), "o_que": "conferir",
        "arquivo": (io.BytesIO(texto.encode("utf-8")), "lote.json")},
        content_type="multipart/form-data").get_data(as_text=True)
    assert "TERCEIRO TELA" in r and "Pôr os 1 na fila" in r
    con = _con(casa)
    assert con.execute("SELECT count(*) FROM rascunhos_de_tela").fetchone()[0] == 0
    con.close()
    token = re.search(r'name="token_arquivo" value="([0-9a-f]+)"', r).group(1)
    c.post("/rcpn/importar", data={"csrf_token": _token(r), "o_que": "fila",
                                   "token_arquivo": token}, follow_redirects=True)
    con = _con(casa)
    n = con.execute("SELECT count(*) FROM rascunhos_de_tela "
                    "WHERE chave='arquivo:dnv-t1'").fetchone()[0]
    con.close()
    assert n == 1


def test_modelo_de_cada_especie_tem_uma_pessoa_por_papel_e_preenchido_passa(casa):
    con = _con(casa)
    for esp, papeis in RC.PAPEIS_DA_ESPECIE.items():
        arq = json.loads(IMPP.modelo_rcpn(con, esp))
        reg = arq["registros"][0]
        assert reg["especie"] == esp
        assert tuple(p["papel"] for p in reg["pessoas"]) == papeis
        reg["chave"], reg["nome"] = f"modelo-{esp}", f"TITULAR {esp}"
        for i, p in enumerate(reg["pessoas"]):
            p["nome"] = f"PESSOA {i} {esp}"
        quadro = IMPP.conferir(con, json.dumps(arq, ensure_ascii=False))
        assert quadro["recusados"] == [], (esp, quadro["recusados"])
        assert len(quadro["entram"]) == 1
    con.close()


def test_manual_das_partes_explica_todo_papel_e_todo_campo(casa):
    con = _con(casa)
    texto = IMPP.manual_das_partes(con)
    campos_p = [c["nome"] for c in IMPP.campos_da_pessoa(con, "RCPN_ASSENTO")]
    con.close()
    todos = {p for ps in RC.PAPEIS_DA_ESPECIE.values() for p in ps}
    # papel ou campo novo no sistema exige a explicação dele aqui
    assert todos <= set(IMPP.QUEM_E_O_PAPEL), todos - set(IMPP.QUEM_E_O_PAPEL)
    assert set(campos_p) <= set(IMPP.O_QUE_VAI_NO_CAMPO), \
        set(campos_p) - set(IMPP.O_QUE_VAI_NO_CAMPO)
    for p in todos:
        assert f"`{p}`" in texto
    for c in campos_p:
        assert f"`{c}`" in texto
    # o manual só cita código de trava que a conferência emite de verdade
    fonte = Path(CD.__file__).read_text(encoding="utf-8")
    for cod, _ in IMPP.O_QUE_TRAVA:
        assert f'"{cod}"' in fonte, cod
    r = casa["c"].get("/rcpn/importar/manual-das-partes")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]

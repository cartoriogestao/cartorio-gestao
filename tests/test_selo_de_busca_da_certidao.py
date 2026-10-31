"""O SELO DE BUSCA QUE VAI JUNTO COM A CERTIDÃO — pedido do oficial, 15/10/2026.

    «colocar selo de busca para ir junto com as certidões (escolhe o item de
     tempo pelo protocolo ou por seleção manual quando da emissão da
     certidão)»

O PRECEDENTE, MEDIDO NO ACERVO DO E-OFÍCIO (só leitura)
    A busca é SELO PRÓPRIO, quantidade 1, no mesmo protocolo da certidão — e
    nunca item dentro do pedido dela: 51 no Protesto (`atos-em-geral`, 17.6.2
    em 47), 32 no RI (27 por `atos-em-geral` de 2022 a 2025), 8 no RCPN — o
    mais novo, de 30/07/2026, pelo MESMO caminho da segunda via, com o mesmo
    livro, folha, termo e folha de segurança da certidão. Notas e RTD/PJ:
    zero.

O QUE ESTES TESTES GUARDAM
    - as faixas, e a fronteira «até N anos» que inclui o dia em que completa;
    - o 17.6.1 revogado, o «.9» que não vira selo, e a certidão eletrônica
      que já traz a busca no preço;
    - sem data do ato não há sugestão, e a emissão recusa a escolha vazia
      ANTES de numerar a certidão;
    - o envelope `atos-em-geral` na forma medida;
    - nas rotas do RCPN, do RI e do Protesto: a busca sai como SEGUNDO selo,
      pelo caminho do precedente, e a chamada antiga (sem o campo na tela)
      continua emitindo como sempre.

Nada aqui fala com o aparelho: `selar_o_ato_lavrado` é substituído por um
gravador, como nos testes de certidão desta casa.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                                         # noqa: E402
import buscas as BU                                             # noqa: E402
import papel_seguranca as PP                                    # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-15T10:00:00"


# ------------------------------------------------------------- as faixas


def test_ate_N_anos_inclui_o_dia_em_que_completa():
    assert BU.item_de_busca("RI", "2024-10-15", "2026-10-15") == "16.25.1"
    assert BU.item_de_busca("RI", "2024-10-14", "2026-10-15") == "16.25.2"
    assert BU.item_de_busca("RCPN", "2016-10-15", "2026-10-15") == "14.6.3"
    assert BU.item_de_busca("RCPN", "1955-10-12", "2026-10-15") == "14.6.8"


def test_as_cinco_atribuicoes_tem_o_seu_grupo():
    assert BU.item_de_busca("NOTAS", "2026-01-01", "2026-10-15") == "13.13.1"
    assert BU.item_de_busca("RCPJ", "2026-01-01", "2026-10-15") == "15.11.1"
    assert BU.item_de_busca("LIVRO3", "2026-01-01", "2026-10-15") == "16.25.1"
    assert BU.item_de_busca("CIVIL", "2026-01-01", "2026-10-15") == "14.6.1"


def test_no_protesto_o_17_6_1_esta_revogado():
    """Medido em `cx_servicos`: «REVOGADO», R$ 0,00. Até dois anos cai na
    faixa de cinco."""
    assert BU.item_de_busca("PROTESTO", "2026-01-01", "2026-10-15") == "17.6.2"
    assert "17.6.1" not in BU.codigos("PROTESTO")
    assert BU.item_do_periodo("PROTESTO", 5) == "17.6.2"
    assert BU.item_do_periodo("PROTESTO", 20) == "17.6.5"


def test_sem_data_do_ato_nao_ha_sugestao():
    """Adivinhar a faixa cobraria do cliente um tempo que ninguém mediu."""
    assert BU.item_de_busca("RI", None, "2026-10-15") is None
    assert BU.item_de_busca("RI", "", "2026-10-15") is None
    # medido na produção: matrícula aberta em «2207-10-26»
    assert BU.item_de_busca("RI", "2207-10-26", "2026-10-15") is None
    assert BU.para_a_tela("RI")["sugerido"] is None


def test_o_9_nao_vira_selo_e_as_faixas_viram():
    assert not BU.vira_selo("16.25.9")
    assert BU.vira_selo("16.25.4")
    assert not BU.vira_selo("16.24.1")
    assert not BU.e_item_de_busca("14.60.1"), "o grupo se compara inteiro"
    assert BU.opcoes("RCPN")[-1]["codigo"] == "14.6.9"


def test_a_certidao_eletronica_ja_traz_a_busca():
    for codigo in ("13.12.4", "14.5.7", "17.5.4", "17.5.5"):
        assert BU.ja_inclui_busca([codigo])
    assert not BU.ja_inclui_busca(["14.5.1", None])


def test_a_escolha_vazia_ou_alheia_se_recusa():
    with pytest.raises(BU.BuscaError, match="Escolha o item da busca"):
        BU.escolher("RI", "")
    with pytest.raises(BU.BuscaError, match="não é busca desta atribuição"):
        BU.escolher("RI", "14.6.3")
    assert BU.escolher("RI", "16.25.9") == "16.25.9"


# --------------------------------------------------------- o envelope


def test_o_envelope_e_o_atos_em_geral_medido():
    """Os 78 envelopes de busca do RI e do Protesto por `atos-em-geral`."""
    env = BU.envelope_da_busca(codigo="17.6.2", escrevente="Mario Santos",
                               versao_tabela="0320260101",
                               nome="FULANA DE TAL",
                               documento="000.000.001-91")
    assert env == {
        "ato": {"codigo": "17.6.2", "codigoTabelaCusta": "0320260101"},
        "escrevente": "Mario Santos",
        "partes": {"nomePartes": [],
                   "parteAto": [{"documento": "00000000191",
                                 "nome": "FULANA DE TAL"}]},
        "quantidade": 1,
    }


def test_a_gratuidade_da_busca_e_a_da_certidao():
    env = BU.envelope_da_busca(codigo="16.25.4", escrevente="Mario Santos",
                               versao_tabela="0220260101", nome="X",
                               isento=True, motivo_isencao="art. 290-A")
    assert env["isento"] == {"value": True, "motivo": "ART. 290-A"}
    with pytest.raises(BU.BuscaError, match="motivo escrito"):
        BU.envelope_da_busca(codigo="16.25.4", escrevente="M",
                             versao_tabela="0220260101", isento=True)
    with pytest.raises(BU.BuscaError, match="não gera selo"):
        BU.envelope_da_busca(codigo="16.25.9", escrevente="M",
                             versao_tabela="0220260101")


def test_o_civil_sela_a_busca_pelo_envelope_da_segunda_via():
    """O caso de 30/07/2026: `codigoTipoAtoCertidao` = 14.6.6, mesmo papel."""
    env = AS.envelope_do_civil(
        especie="NASCIMENTO", tipo="CERTIDAO", escrevente="Mario Santos",
        livro="14", folha="281", termo="14201", nome_parte="FULANA",
        versao_tabela="0120260101", papel="7225238", codigo_tj="14.6.6")
    assert env["codigoTipoAtoCertidao"] == "14.6.6"
    assert env["papelMoeda"]["codigo"] == "7225238"


# ------------------------------------------------------------ as rotas


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                              "ADMIN")
    cg_casa["db"].set_settings({"selo_tabela_custas_em": "20260101"})
    c = cg_casa["app"].test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": cg_casa["app"], "c": c, "banco": cg_casa["banco"]}


@pytest.fixture()
def gravador(monkeypatch):
    chamadas: list[dict] = []

    def _selar(*a, **k):
        chamadas.append(k)
        return {"selado": True, "numero": f"BUSCAS0000000TESTE{len(chamadas):04d}",
                "numeros": [f"BUSCAS0000000TESTE{len(chamadas):04d}"],
                "motivo": None}
    monkeypatch.setattr(AS, "selar_o_ato_lavrado", _selar)
    return chamadas


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento(s) -> int:
    """Nascimento do acervo, sem selo de registro: é segunda via."""
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem,
                   criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,
                       '000000015519971000111270010385 01','JOÃO DA SILVA',
                       '2020-01-20','2020-01-15','{"strSexo": "Masculino"}',
                       'ATIVO','EOFICIO',?)""", (AGORA,))
        aid = con.execute("SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',127,19552,'127','2020-01-20','EOFICIO',
                       ?)""", (aid, AGORA))
        for papel, quem, ordem in (("PAI", "JOSÉ DA SILVA", 1),
                                   ("MAE", "MARIA DAS GRAÇAS SILVA", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em)
                   VALUES (?,?,?,?,'EOFICIO',?)""",
                (aid, papel, quem, ordem, AGORA))
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="HA",
                           codigo_de="900001", codigo_ate="900003",
                           agora=AGORA, nota_fiscal="NF 1", usuario="MARIO")
    con.close()
    return aid


def _emitir_rcpn(s, aid: int, **campos):
    html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    return s["c"].post(f"/rcpn/{aid}/certidao",
                       data={"csrf_token": _token(html), "requerente": "A MÃE",
                             "folha_seguranca": "900001", **campos},
                       follow_redirects=True)


def test_a_ficha_do_assento_marca_o_9_e_diz_por_que(s):
    """Resposta do oficial, 15/10/2026: a 2ª via de assento conhecido (livro,
    folha e termo na ficha) não cobra busca — o «.9» vem marcado, com o
    motivo à vista, e a faixa de tempo continua na lista para trocar."""
    aid = _assento(s)
    html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert 'name="busca_item"' in html
    assert re.search(r'<option value="14\.6\.9"\s+selected>', html)
    assert "assento conhecido (termo 19552" in html
    faixa = BU.item_de_busca("RCPN", "2020-01-20", date.today())
    assert f'value="{faixa}"' in html


def test_rcpn_a_busca_sai_como_segundo_selo_pela_segunda_via(s, gravador):
    aid = _assento(s)
    r = _emitir_rcpn(s, aid, busca_formulario="1", busca_item="14.6.3")
    assert "emitida" in r.get_data(as_text=True)
    assert len(gravador) == 2, "certidão e busca: dois selos"
    certidao, busca = gravador
    assert busca["tabela"] == "rc_certidoes"
    assert busca["dados"]["codigoTipoAtoCertidao"] == "14.6.3"
    assert busca["referencia"].endswith(":14.6.3:1")
    # dois selos, UM papel — a folha da certidão vai nos dois envelopes
    assert (busca["dados"]["papelMoeda"]["codigo"]
            == certidao["dados"]["papelMoeda"]["codigo"] == "900001")
    con = _con(s)
    detalhe = con.execute(
        "SELECT details FROM audit_logs WHERE action='RCPN_CERTIDAO'"
    ).fetchone()
    con.close()
    assert detalhe and "14.6.3" in detalhe[0]


def test_rcpn_o_9_nao_vende_selo(s, gravador):
    aid = _assento(s)
    _emitir_rcpn(s, aid, busca_formulario="1", busca_item="14.6.9")
    assert len(gravador) == 1


def test_rcpn_escolha_vazia_recusa_antes_de_numerar(s, gravador):
    aid = _assento(s)
    r = _emitir_rcpn(s, aid, busca_formulario="1", busca_item="")
    assert "Escolha o item da busca" in r.get_data(as_text=True)
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM rc_certidoes").fetchone()[0] == 0
    con.close()
    assert gravador == []


def test_rcpn_chamada_sem_o_campo_emite_como_sempre(s, gravador):
    aid = _assento(s)
    _emitir_rcpn(s, aid)
    assert len(gravador) == 1


def _matricula(s, abertura="2016-01-10") -> int:
    con = _con(s)
    with con:
        con.execute("INSERT INTO ri_matriculas (numero, livro, data_abertura,"
                    " criado_em) VALUES ('4099','2',?,?)", (abertura, AGORA))
        mid = int(con.execute("SELECT id FROM ri_matriculas").fetchone()[0])
    con.close()
    return mid


def test_ri_a_busca_sai_por_atos_em_geral_depois_da_certidao(s, gravador,
                                                             monkeypatch):
    import ri_web
    monkeypatch.setattr(ri_web.CFOLHAS, "decidir_folhas_antes_de_emitir",
                        lambda **k: 1)
    mid = _matricula(s)
    tela = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert 'name="busca_item"' in tela
    # pedida pelo número da matrícula: o «.9» vem marcado, com o motivo
    assert re.search(r'<option value="16\.25\.9"\s+selected>', tela)
    assert "pelo número da matrícula 4099" in tela
    s["c"].post(f"/registro-imoveis/{mid}/certidao",
                data={"csrf_token": _token(tela), "tipo": "INTEIRO_TEOR",
                      "requerente": "FULANA DE TAL",
                      "requerente_documento": "000.000.002-72",
                      "busca_formulario": "1", "busca_item": "16.25.3"},
                follow_redirects=True)
    assert len(gravador) == 2
    certidao, busca = gravador
    assert certidao["dados"]["codigoTipoAto"] == "16.24.4"
    assert busca["caminho"] == "/selo/imovel/atos-em-geral"
    assert busca["dados"]["ato"] == {"codigo": "16.25.3",
                                     "codigoTabelaCusta": "0220260101"}
    assert busca["dados"]["partes"]["parteAto"] == [
        {"documento": "00000000272", "nome": "FULANA DE TAL"}]
    assert busca["tabela"] == "ri_certidoes"


def test_ri_negativa_sem_escolha_recusa_antes_de_numerar(s, gravador):
    tela = s["c"].get("/registro-imoveis/indicador-pessoal").get_data(
        as_text=True)
    s["c"].post("/registro-imoveis/certidao-negativa",
                data={"csrf_token": _token(tela), "modo": "PESSOA",
                      "busca": "NINGUEM QUE EXISTA", "requerente": "FULANA",
                      "busca_formulario": "1", "busca_item": ""},
                follow_redirects=True)
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM ri_certidoes").fetchone()[0] == 0
    con.close()
    assert gravador == []


def _protocolo(s, *codigos: str) -> int:
    """O protocolo com os itens QUITADOS: o selo pago só sai com o item pago
    (`protesto_selo_previo.conferir_antes_de_lavrar`), e a trava fica ligada."""
    con = _con(s)
    with con:
        cur = con.execute("INSERT INTO cx_protocolos (numero, data_abertura,"
                          " criado_em) VALUES ('2026.10.1', '2026-10-15', ?)",
                          (AGORA,))
        pid = int(cur.lastrowid)
        for codigo in codigos:
            con.execute("INSERT INTO cx_protocolo_atos (protocolo_id,"
                        " codigo_ato, quitado) VALUES (?, ?, 1)", (pid, codigo))
    con.close()
    return pid


def _emitir_protesto(s, **campos):
    tela = s["c"].get("/protesto/certidoes").get_data(as_text=True)
    r = s["c"].post("/protesto/certidoes/emitir",
                    data={"csrf_token": _token(tela), "nome": "MARIA",
                          "documento": "000.000.001-91", "anos": "5",
                          **campos},
                    follow_redirects=True)
    # a recusa da rota aparece aqui, com a mensagem, e não como lista vazia
    recusa = re.findall(r"Certidão NÃO emitida[^<]*", r.get_data(as_text=True))
    assert not recusa, recusa
    return r


def test_protesto_a_busca_sai_por_atos_em_geral(s, gravador):
    pid = _protocolo(s, "17.5.1")
    _emitir_protesto(s, protocolo_id=str(pid), busca_formulario="1",
                     busca_item="17.6.2")
    assert len(gravador) == 2
    certidao, busca = gravador
    assert certidao["dados"]["ato"]["codigo"] == "17.5.1"
    assert busca["caminho"] == "/selo/protesto/atos-em-geral"
    assert busca["dados"]["ato"]["codigo"] == "17.6.2"
    assert busca["dados"]["ato"]["codigoTabelaCusta"] == "0320260101"
    assert busca["dados"]["partes"]["parteAto"][0]["nome"] == "MARIA"


def test_protesto_a_busca_do_protocolo_vale_e_nao_se_vende_outra(
        s, gravador):
    """O «pelo protocolo» do pedido: a faixa que abriu o protocolo é a que
    sela, uma vez só, e nunca pelo caminho da certidão."""
    pid = _protocolo(s, "17.5.1", "17.6.3")
    _emitir_protesto(s, protocolo_id=str(pid), busca_formulario="1",
                     busca_item="17.6.2")
    assert len(gravador) == 2
    assert gravador[0]["dados"]["ato"]["codigo"] == "17.5.1"
    assert gravador[1]["dados"]["ato"]["codigo"] == "17.6.3"


def test_protesto_eletronica_ja_inclui_a_busca(s, gravador):
    # O 17.5.5 não saiu em selo pelo caminho da certidão (no acervo, os 10
    # saíram por `atos-em-geral`): sem a afirmação expressa, a rota recusa.
    pid = _protocolo(s, "17.5.5")
    _emitir_protesto(s, protocolo_id=str(pid), busca_formulario="1",
                     busca_item="17.6.2", afirmo="1",
                     afirmacao="Afirmo, sob minha responsabilidade, que o item "
                               "da certidão eletrônica serve para esta certidão.")
    assert len(gravador) == 1


def test_a_tela_do_protesto_sugere_pelo_periodo(s):
    html = s["c"].get("/protesto/certidoes?nome=MARIA&documento=000.000.001-91"
                      "&anos=5").get_data(as_text=True)
    assert re.search(r'<option value="17\.6\.2"\s+selected>', html)


# ------------------------- a resposta do oficial, 15/10/2026 (segunda volta)


def test_o_ato_identificado_marca_o_9_e_a_frase_vai_junto():
    b = BU.para_a_tela("NOTAS", "2001-01-01",
                       identificado="ato indicado pelo livro 12, folha 30")
    assert b["sugerido"] == "13.13.9" and b["identificado"] is True
    assert b["de_onde"] == "ato indicado pelo livro 12, folha 30"
    # sem identificação, a faixa de tempo continua
    assert BU.para_a_tela("NOTAS", "2001-01-01",
                          data_emissao="2026-10-15")["sugerido"] == "13.13.6"


def test_notas_e_rtdpj_selam_a_busca_pelo_atos_em_geral_da_atribuicao():
    assert BU.CAMINHO_DO_SELO_DA_BUSCA["NOTAS"] == "/selo/notas/atos-em-geral"
    assert BU.CAMINHO_DO_SELO_DA_BUSCA["RTDPJ"] == AS.CAMINHO_RTDPJ_GERAL


def test_a_busca_do_protocolo_e_filtrada_pela_atribuicao():
    itens = [("16.24.1", 1), ("17.6.3", 1), ("16.25.5", 1)]
    assert BU.busca_entre(itens, "IMOVEL") == "16.25.5"
    assert BU.busca_entre(itens, "RCPN") is None


def test_o_envelope_da_certidao_do_protesto_nao_exige_titulo():
    """O conserto do defeito antigo: a certidão por nome não tem título, e
    o selo saía nunca. Vai como a casa mandou nos 57 do acervo: protocolo
    «0», livro «1», quantidade 1 e a pessoa pesquisada nas partes."""
    env = AS.envelope_do_protesto(
        tipo="NEGATIVA", tabela="pt_certidoes", codigo_tj="17.5.1",
        escrevente="Mario Santos", protocolo=None,
        versao_tabela="0320260101",
        partes=[{"nome": "MARIA", "documento": "000.000.001-91"}])
    assert env["selo"] == {"escrevente": "Mario Santos", "protocolo": "0",
                           "livro": "1"}
    assert env["quantidade"] == 1
    assert env["natureza"] == {"tipo": 0}
    assert env["partes"]["parteAto"] == [{"nome": "MARIA",
                                          "documento": "00000000191"}]
    # o ato do título continua exigindo o protocolo
    with pytest.raises(AS.AtoError, match="protocolo"):
        AS.envelope_do_protesto(
            tipo="PROTESTO", tabela="pt_atos", codigo_tj="17.1",
            escrevente="Mario Santos", protocolo=None,
            versao_tabela="0320260101")


def test_a_certidao_do_protesto_sela_sem_titulo_e_nao_e_cancelada(s, gravador):
    pid = _protocolo(s, "17.5.1")
    _emitir_protesto(s, protocolo_id=str(pid))
    assert len(gravador) == 1
    dados = gravador[0]["dados"]
    assert dados["selo"]["protocolo"] == "0"
    assert dados["partes"]["parteAto"][0]["nome"] == "MARIA"
    con = _con(s)
    linha = con.execute("SELECT cancelada FROM pt_certidoes").fetchone()
    con.close()
    assert linha["cancelada"] in (0, None)


def test_a_tela_do_protesto_pergunta_a_data_do_ato(s):
    html = s["c"].get("/protesto/certidoes?nome=MARIA&documento=000.000.001-91"
                      "&anos=5").get_data(as_text=True)
    assert 'name="busca_data_do_ato"' in html
    assert "17.6.9" in html


def test_ri_a_busca_do_protocolo_vale_sobre_a_escolhida(s, gravador,
                                                         monkeypatch):
    import ri_web
    monkeypatch.setattr(ri_web.CFOLHAS, "decidir_folhas_antes_de_emitir",
                        lambda **k: 1)
    mid = _matricula(s)
    _protocolo(s, "16.24.4", "16.25.5")
    tela = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    s["c"].post(f"/registro-imoveis/{mid}/certidao",
                data={"csrf_token": _token(tela), "tipo": "INTEIRO_TEOR",
                      "requerente": "FULANA DE TAL", "protocolo": "2026.10.1",
                      "busca_formulario": "1", "busca_item": "16.25.9"},
                follow_redirects=True)
    assert len(gravador) == 2
    assert gravador[1]["dados"]["ato"]["codigo"] == "16.25.5"


def _registro_rtd(s) -> int:
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rg_registros(atribuicao, serie, numero,
                   requerente_nome, situacao, origem, criado_em, teor)
               VALUES (4,'TD_B',1508,'EMPRESA X','ATIVO','MANUAL',?,
                       'Teor do registro, reproduzido do livro.')""",
            (AGORA,))
        rid = int(con.execute("SELECT id FROM rg_registros").fetchone()[0])
        con.execute(
            """INSERT INTO rg_atos(registro_id, tipo, data_ato, teor, folha,
                   origem, criado_em)
               VALUES (?, 'REGISTRO', '2026-09-17',
                       'Teor do registro, reproduzido do livro.', '10',
                       'MANUAL', ?)""", (rid, AGORA))
    con.close()
    return rid


def test_rtdpj_marca_o_9_e_sela_a_busca_pelo_atos_em_geral(s, gravador):
    rid = _registro_rtd(s)
    tela = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    assert re.search(r'<option value="15\.11\.9"\s+selected>', tela)
    assert "registro nº 1508" in tela
    pid = _protocolo(s, "15.10.1")
    s["c"].post(f"/atribuicoes/certidoes/RCPJ_RTD/{rid}",
                data={"csrf_token": _token(tela), "requerente": "EMPRESA X",
                      "protocolo_id": str(pid), "busca_formulario": "1",
                      "busca_item": "15.11.3"},
                follow_redirects=True)
    assert len(gravador) == 2
    certidao, busca = gravador
    assert certidao["caminho"] == busca["caminho"] == AS.CAMINHO_RTDPJ_GERAL
    assert busca["referencia"].endswith(":15.11.3:1")

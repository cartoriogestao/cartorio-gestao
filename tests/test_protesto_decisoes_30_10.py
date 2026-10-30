"""As decisões do oficial sobre o Protesto, de 30/10/2026.

    1. o botão «Corrigir a situação de ofício» da ficha só PROPÕE, e quem aprova é
       o ADMIN humano: não sobra caminho direto para o gerente;
    2. o pagamento por PIX copiado pela fila passa pela trava do `protesto_pix`;
    3. a pendência que só o oficial resolve não obriga a escrevente a afirmar;
    5. a situação DEVOLVIDO, pela fila, para o código 5 da CRA e a duplicidade;
    6. a regularidade do trâmite do protesto na rodada do compliance.

    O item 4 (a AC que espera o devedor) está em `test_protesto_cra_pedidos.py`,
    e a carga do código 5 em `test_acervo_carga.py`.

NOMES: `mario` é o oficial (ADMIN), `beatriz` a gerente (MANAGER) e `carla` a
escrevente (USER), sem nome real da equipe.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import compliance as CP  # noqa: E402
import correcoes_de_oficio as CDO  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_cenprot_xml as PCXML  # noqa: E402
import protesto_lista as PL  # noqa: E402
import protesto_pix as PIX  # noqa: E402
import protesto_roteiro as PROT  # noqa: E402
import protesto_selo_previo as PSELO  # noqa: E402
import resolve_intimacao as RI  # noqa: E402
from bd_nativo import banco  # noqa: E402
from test_correcoes_de_oficio import (AFIRMACAO, AGORA, MOTIVO, _aprovar, _ato,  # noqa: E402
                                      _entrar, _pago_sem_pagamento, _pessoas, _propor,
                                      _situacao, _titulo, _token, _um)

DEVOLVIDO = "PT_TITULO_DEVOLVIDO"
COPIA = "PT_ATO_DE_CORRECAO"
SUSTENTADA = "PT_SITUACAO_SUSTENTADA"
DEVOLVER = {"data_ocorrencia": "2025-02-20"}


# ------------------------------------------------------ 1. o botão só propõe


def _sem_ato(cg_casa) -> tuple[dict, int]:
    db = cg_casa["db"]
    p = _pessoas(db)
    db.set_settings({"modulo_protesto_ligado": "1"})
    return p, _pago_sem_pagamento(db, "SA/1")


def test_o_botao_da_ficha_so_propoe(cg_casa):
    db = cg_casa["db"]
    _p, t = _sem_ato(cg_casa)
    c = _entrar(cg_casa, "beatriz")
    token = _token(c.get(f"/protesto/{t}").get_data(as_text=True))
    r = c.post(f"/protesto/{t}/situacao/corrigir",
               data={"csrf_token": token, "motivo": MOTIVO}, follow_redirects=True)
    assert "a situação não mudou" in r.get_data(as_text=True)
    assert _situacao(db, t) == "PAGO"
    linha = _um(db, "SELECT tipo, situacao, titulo_ids FROM correcoes_de_oficio")
    assert (linha["tipo"], linha["situacao"]) == (SUSTENTADA, "PROPOSTA")
    assert json.loads(linha["titulo_ids"]) == [t]


def test_o_gerente_nao_aprova_e_o_admin_aprova(cg_casa):
    db = cg_casa["db"]
    p, t = _sem_ato(cg_casa)
    proposta = _propor(db, p["beatriz"], SUSTENTADA, {"titulo_ids": [t]})
    assert proposta["ok"], proposta["recusas"]
    r = _aprovar(db, p["beatriz"], proposta["id"])
    assert not r["ok"] and "Só o oficial" in r["recusa"]
    assert _situacao(db, t) == "PAGO"
    r = _aprovar(db, p["mario"], proposta["id"])
    assert r["ok"], r
    assert _situacao(db, t) == "APONTADO"


def test_o_botao_nao_propoe_duas_vezes_o_mesmo(cg_casa):
    db = cg_casa["db"]
    _p, t = _sem_ato(cg_casa)
    c = _entrar(cg_casa, "beatriz")
    token = _token(c.get(f"/protesto/{t}").get_data(as_text=True))
    for _ in range(2):
        r = c.post(f"/protesto/{t}/situacao/corrigir",
                   data={"csrf_token": token, "motivo": MOTIVO}, follow_redirects=True)
    assert "já espera o oficial" in r.get_data(as_text=True)
    assert _um(db, "SELECT count(*) AS n FROM correcoes_de_oficio")["n"] == 1


# ----------------------------------------------- 2. o PIX copiado pela fila


def _pix(db, titulo_id: int, *, situacao: str = "CONFIRMADO", ato_id=None,
         valor: int = 10000) -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO pt_pix (titulo_id, valor_centavos, data_pix, situacao,
                   lancado_em, credito_id, credito_data, confirmacao_modo, confirmado_por, ato_id)
               VALUES (%s, %s, '2026-10-16', %s, %s, %s, %s, 'MANUAL', 'BEATRIZ EXEMPLO', %s)
               RETURNING id""",
            (titulo_id, valor, situacao, AGORA,
             f"cred-{titulo_id}" if situacao == "CONFIRMADO" else None,
             "2026-10-16" if situacao == "CONFIRMADO" else None, ato_id))[0]["id"])


def _pagamento_por_pix(db, titulo_id: int, *, cancelado: bool = False) -> int:
    return _ato(db, titulo_id, "PAGAMENTO", cancelado=cancelado, data="2026-10-21",
                detalhe='{"forma_pagamento": "PIX", "valor_pago_centavos": 10000}')


def test_o_pagamento_por_pix_sem_credito_nao_se_copia(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    certo, errado = _titulo(db, "APONTADO", "PX/1"), _titulo(db, "PAGO", "PX/2")
    pagamento = _pagamento_por_pix(db, errado)
    r = _propor(db, p["carla"], COPIA, {"ato_origem_id": pagamento, "titulo_id": certo})
    assert not r["ok"]
    assert any("CRÉDITO SER CONFERIDO" in x for x in r["recusas"])
    assert _um(db, "SELECT count(*) AS n FROM correcoes_de_oficio")["n"] == 0


@pytest.mark.parametrize("situacao", ["AGUARDANDO_CREDITO", "NAO_CONFIRMADO"])
def test_o_pix_sem_credito_conferido_e_recusado(cg_casa, situacao):
    db = cg_casa["db"]
    p = _pessoas(db)
    certo, errado = _titulo(db, "APONTADO", "PX/1"), _titulo(db, "PAGO", "PX/2")
    pagamento = _pagamento_por_pix(db, errado, cancelado=True)
    pix = _pix(db, errado, situacao=situacao)
    r = _propor(db, p["carla"], COPIA, {"ato_origem_id": pagamento, "titulo_id": certo,
                                        "pix_id": pix})
    assert not r["ok"] and any("não foi conferido" in x for x in r["recusas"])


def test_o_credito_que_sustenta_ato_valido_nao_paga_dois(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    certo, errado = _titulo(db, "APONTADO", "PX/1"), _titulo(db, "PAGO", "PX/2")
    pagamento = _pagamento_por_pix(db, errado)
    pix = _pix(db, errado, ato_id=pagamento)
    r = _propor(db, p["carla"], COPIA, {"ato_origem_id": pagamento, "titulo_id": certo,
                                        "pix_id": pix})
    assert not r["ok"] and any("não paga dois atos" in x for x in r["recusas"])


def test_o_pix_de_outro_titulo_e_recusado(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    certo, errado = _titulo(db, "APONTADO", "PX/1"), _titulo(db, "PAGO", "PX/2")
    outro = _titulo(db, "APONTADO", "PX/3")
    pagamento = _pagamento_por_pix(db, errado, cancelado=True)
    r = _propor(db, p["carla"], COPIA, {"ato_origem_id": pagamento, "titulo_id": certo,
                                        "pix_id": _pix(db, outro)})
    assert not r["ok"] and any("não é do título" in x for x in r["recusas"])


def test_com_pix_esperando_no_titulo_certo_nenhuma_copia_entra(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    certo, errado = _titulo(db, "APONTADO", "PX/1"), _titulo(db, "PAGO", "PX/2")
    _pix(db, certo, situacao="AGUARDANDO_CREDITO")
    pagamento = _ato(db, errado, "PAGAMENTO", detalhe='{"forma_pagamento": "ESPECIE"}')
    r = _propor(db, p["carla"], COPIA, {"ato_origem_id": pagamento, "titulo_id": certo})
    assert not r["ok"] and any("AGUARDANDO O CRÉDITO" in x for x in r["recusas"])


def test_com_o_credito_conferido_a_copia_leva_o_pix_ao_titulo_certo(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    certo, errado = _titulo(db, "APONTADO", "PX/1"), _titulo(db, "PAGO", "PX/2")
    pagamento = _pagamento_por_pix(db, errado, cancelado=True)
    pix = _pix(db, errado, ato_id=pagamento)
    proposta = _propor(db, p["carla"], COPIA, {"ato_origem_id": pagamento, "titulo_id": certo,
                                               "pix_id": pix})
    assert proposta["ok"], proposta["recusas"]
    r = _aprovar(db, p["mario"], proposta["id"])
    assert r["ok"], r
    novo = r["resultado"]["ato_novo_id"]
    linha = _um(db, "SELECT titulo_id, ato_id FROM pt_pix WHERE id = %s", (pix,))
    assert (linha["titulo_id"], linha["ato_id"]) == (certo, novo)
    detalhe = json.loads(_um(db, "SELECT detalhe_json FROM pt_atos WHERE id = %s",
                             (novo,))["detalhe_json"])
    assert detalhe["pix"]["pix_id"] == pix
    assert detalhe["data_do_pagamento"] == "2026-10-16"       # a do crédito
    assert _situacao(db, certo) == "PAGO"


def test_o_credito_usado_depois_da_proposta_da_falhou(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    certo, errado = _titulo(db, "APONTADO", "PX/1"), _titulo(db, "PAGO", "PX/2")
    pagamento = _pagamento_por_pix(db, errado, cancelado=True)
    pix = _pix(db, errado)
    proposta = _propor(db, p["carla"], COPIA, {"ato_origem_id": pagamento, "titulo_id": certo,
                                               "pix_id": pix})
    assert proposta["ok"], proposta["recusas"]
    outro = _ato(db, errado, "PAGAMENTO", detalhe='{"forma_pagamento": "PIX"}')
    with db.transaction() as con:
        PIX.vincular_ao_ato(con, pix, outro)
    r = _aprovar(db, p["mario"], proposta["id"])
    assert not r["ok"] and r["situacao"] == CDO.FALHOU
    assert _situacao(db, certo) == "APONTADO"


# ------------------------------------------- 3. o que é com o oficial


def _obrigacao(condutas, chave) -> dict:
    return next(o for c in condutas for o in c["obrigacoes"] if o["chave"] == chave)


def _com_uma_proposta(cg_casa) -> dict:
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "SA/9")
    assert _propor(db, p["carla"], SUSTENTADA, {"titulo_ids": [t]})["ok"]
    return p


def test_a_proposta_nao_entra_nos_itens_da_escrevente(cg_casa):
    db = cg_casa["db"]
    _com_uma_proposta(cg_casa)
    with db.connect() as con:
        condutas = PROT.cobrar_o_dia(con, agora=AGORA, papel="USER")
    o = _obrigacao(condutas, "correcoes_de_oficio")
    assert o["e_com_o_oficial"] and o["faltam"] == 1
    assert "correcoes_de_oficio" not in {
        x["chave"] for x in PROT.pendencias_para_encerrar(condutas)}
    assert "correcoes_de_oficio" in {x["chave"] for x in PROT.com_o_oficial(condutas)}
    # e não conta na conduta dela
    protestos = next(c for c in condutas if c["chave"] == "protestos")
    assert protestos["faltam"] == sum(x["faltam"] or 0 for x in protestos["obrigacoes"]
                                      if not x.get("e_com_o_oficial"))


@pytest.mark.parametrize("papel", ["ADMIN", None])
def test_quando_o_admin_encerra_ela_continua_pedindo_afirmacao(cg_casa, papel):
    """Sem papel, a cobrança é a inteira: nada se alivia porque faltou dizer quem é."""
    db = cg_casa["db"]
    _com_uma_proposta(cg_casa)
    with db.connect() as con:
        condutas = PROT.cobrar_o_dia(con, agora=AGORA, papel=papel)
    assert "correcoes_de_oficio" in {
        x["chave"] for x in PROT.pendencias_para_encerrar(condutas)}
    assert PROT.com_o_oficial(condutas) == []


def test_o_encerramento_confere_pelo_papel_de_quem_encerra(cg_casa):
    db = cg_casa["db"]
    _com_uma_proposta(cg_casa)
    with db.connect() as con:
        itens = PROT.pendencias_para_encerrar(PROT.cobrar_o_dia(con, agora=AGORA, papel="USER"))
        afirmacoes = {x["chave"]: (True, AFIRMACAO) for x in itens}
        conferido = PROT.conferir_o_encerramento(con, agora=AGORA, afirmacoes=afirmacoes,
                                                 papel="USER")
        assert "correcoes_de_oficio" not in {x["chave"] for x in conferido["pendencias"]}
        with pytest.raises(PROT.EncerramentoError) as erro:
            PROT.conferir_o_encerramento(con, agora=AGORA, afirmacoes=afirmacoes,
                                         papel="ADMIN")
    assert "correções de ofício" in str(erro.value)


def test_a_tela_da_escrevente_mostra_que_e_com_o_oficial(cg_casa):
    db = cg_casa["db"]
    _com_uma_proposta(cg_casa)
    db.set_settings({"modulo_protesto_ligado": "1"})
    html = _entrar(cg_casa, "carla").get("/protesto/roteiro").get_data(as_text=True)
    assert "data-encerrar-com-o-oficial" in html and "É com o oficial" in html
    assert 'name="afirmo_correcoes_de_oficio"' not in html
    html = _entrar(cg_casa, "mario").get("/protesto/roteiro").get_data(as_text=True)
    assert 'name="afirmo_correcoes_de_oficio"' in html


# ------------------------------------------- 5. o título devolvido


def test_o_codigo_5_sai_do_pago_sem_ato(cg_casa):
    """Os títulos 52, 776 e 777: PAGO só com o apontamento."""
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, "PAGO", "DV/1")
    _ato(db, t, "APONTAMENTO", data="2025-02-11")
    with db.connect() as con:
        assert PSELO.situacao_sem_ato(con, t)["origem"] == "SEM_ATO"
    proposta = _propor(db, p["carla"], DEVOLVIDO, {"titulo_id": t, **DEVOLVER})
    assert proposta["ok"], proposta["recusas"]
    assert _situacao(db, t) == "PAGO"                         # propor não altera
    r = _aprovar(db, p["mario"], proposta["id"])
    assert r["ok"], r
    assert _situacao(db, t) == "DEVOLVIDO"
    ato = _um(db, "SELECT * FROM pt_atos WHERE id = %s", (r["resultado"]["ato_novo_id"],))
    assert (ato["tipo"], str(ato["data_ato"]), ato["origem"]) == (
        "DEVOLUCAO", "2025-02-20", "CORRECAO")
    assert not ato["selo"] and MOTIVO in ato["observacao"]
    with db.connect() as con:
        assert PSELO.situacao_sem_ato(con, t) is None
        assert PSELO.titulos_sem_ato_que_sustente(con) == []


def test_a_duplicidade_com_a_primeira_entrada_protestada(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    primeira = _titulo(db, "PROTESTADO", "DV/2")
    _ato(db, primeira, "PROTESTO")
    segunda = _titulo(db, "APONTADO", "DV/2B")
    _ato(db, segunda, "APONTAMENTO")
    with db.transaction() as con:         # a chave de origem é única; o número, não
        banco(con).escrever("UPDATE pt_titulos SET numero_titulo = 'DV/2' WHERE id = %s",
                            (segunda,))
    motivo = (f"Entrada em duplicidade do mesmo título: a primeira entrada é o título "
              f"{primeira}, já protestado.")
    with db.transaction() as con:
        r = CDO.propor(con, tipo=DEVOLVIDO, motivo=motivo, quem=p["carla"], agora=AGORA,
                       parametros={"titulo_id": segunda, **DEVOLVER})
    assert r["ok"], r["recusas"]
    assert any(f"título {primeira} (PROTESTADO" in a for a in r["avisos"])
    assert _aprovar(db, p["mario"], r["id"])["ok"]
    assert _situacao(db, segunda) == "DEVOLVIDO"
    assert _situacao(db, primeira) == "PROTESTADO"            # a primeira não se mexe
    assert motivo in _um(db, "SELECT observacao FROM pt_atos WHERE tipo = 'DEVOLUCAO'")["observacao"]


@pytest.mark.parametrize("tipo", CDO.ATOS_QUE_IMPEDEM_A_DEVOLUCAO)
def test_com_ato_que_deu_vida_ao_titulo_nao_se_devolve(cg_casa, tipo):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, "APONTADO", "DV/3")
    aid = _ato(db, t, tipo)
    r = _propor(db, p["carla"], DEVOLVIDO, {"titulo_id": t, **DEVOLVER})
    assert not r["ok"] and any(f"ato {aid}" in x for x in r["recusas"])


@pytest.mark.parametrize("situacao", ["PROTESTADO", "CANCELADO", "DESISTIDO", "DEVOLVIDO"])
def test_as_situacoes_que_nao_se_devolvem(cg_casa, situacao):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, situacao, "DV/4")
    assert not _propor(db, p["carla"], DEVOLVIDO, {"titulo_id": t, **DEVOLVER})["ok"]


@pytest.mark.parametrize("data", ["", "ontem", "2099-01-01"])
def test_a_data_da_ocorrencia_e_obrigatoria_e_nao_e_futura(cg_casa, data):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, "APONTADO", "DV/5")
    r = _propor(db, p["carla"], DEVOLVIDO, {"titulo_id": t, "data_ocorrencia": data})
    assert not r["ok"] and any("data da ocorrência" in x for x in r["recusas"])


def test_a_data_em_formato_de_tela_vale(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, "APONTADO", "DV/6")
    r = _propor(db, p["carla"], DEVOLVIDO, {"titulo_id": t, "data_ocorrencia": "20/02/2025"},
                previa=True)
    assert r["ok"] and r["depois"]["ato_novo"]["data_ato"] == "2025-02-20"


def test_tornar_a_devolucao_sem_efeito_e_o_caminho_de_volta(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, "APONTADO", "DV/7")
    _ato(db, t, "APONTAMENTO")
    feito = _aprovar(db, p["mario"],
                     _propor(db, p["carla"], DEVOLVIDO, {"titulo_id": t, **DEVOLVER})["id"])
    volta = _propor(db, p["carla"], "PT_ATO_SEM_EFEITO",
                    {"ato_ids": [feito["resultado"]["ato_novo_id"]]})
    assert volta["ok"], volta["recusas"]
    assert _aprovar(db, p["mario"], volta["id"])["ok"]
    assert _situacao(db, t) == "APONTADO"


def _devolvido(db, p) -> int:
    t = _titulo(db, "APONTADO", "DV/8")
    _ato(db, t, "APONTAMENTO")
    assert _aprovar(db, p["mario"],
                    _propor(db, p["carla"], DEVOLVIDO, {"titulo_id": t, **DEVOLVER})["id"])["ok"]
    return t


def test_o_devolvido_nao_vai_a_protesto_intimacao_pagamento_nem_xml(cg_casa):
    db = cg_casa["db"]
    t = _devolvido(db, _pessoas(db))
    with db.transaction() as con:
        with pytest.raises(PT.ProtestoError):
            PT.recusar_pagamento_na_situacao(dict(PT.titulo_para_gravar(con, t)))
        with pytest.raises(PT.ProtestoError, match="só se intima"):
            PT.lancar_intimacao(con, t, modo="PESSOAL", agora=AGORA)
        with pytest.raises(PT.ProtestoError, match="só se protesta"):
            PT.lancar_protesto(con, t, sv={}, agora=AGORA, data_extenso="trinta de outubro")
    # O ATO DA DEVOLUÇÃO NÃO VAI AO XML NEM AO RETORNO: as listas são fechadas.
    assert "DEVOLUCAO" not in PCXML.LETRA_DO_ATO
    import protesto_retorno as PRE
    assert "DEVOLUCAO" not in PRE.ATOS_QUE_VOLTAM


def test_o_devolvido_esta_nas_listas_de_situacao():
    assert "DEVOLVIDO" in PT.SITUACOES_TITULO and "DEVOLVIDO" in PT.SITUACOES_FINAIS
    assert "DEVOLVIDO" in PT.SITUACOES_SEM_PAGAMENTO
    assert "DEVOLVIDO" in PSELO.SITUACOES_FINAIS
    assert "DEVOLVIDO" in PL.SITUACOES_ENCERRADAS
    assert "DEVOLVIDO" in RI.SITUACOES_QUE_NAO_VAO
    assert "DEVOLUCAO" in PT.TIPOS_ATO


def test_o_formulario_da_fila_pede_a_data(cg_casa):
    db = cg_casa["db"]
    _pessoas(db)
    html = _entrar(cg_casa, "carla").get(
        f"/administrativo/correcoes-de-oficio/nova?tipo={DEVOLVIDO}").get_data(as_text=True)
    assert 'name="data_ocorrencia"' in html and 'type="date"' in html


# ------------------------------------------- 6. o trâmite no compliance


def _ctx(con) -> CP.Contexto:
    return CP.Contexto(con=con, agora=datetime(2026, 10, 30, 17, 0), gravar=False)


def _tramite(db) -> dict[str, dict]:
    with db.connect() as con:
        return {a["chave"].split(":")[-1]: a for a in CP.regra_tramite_do_protesto(_ctx(con))}


DIA = "2026-10-20"


def test_a_rodada_inclui_o_tramite_do_protesto():
    assert ("PROTESTO_TRAMITE", CP.regra_tramite_do_protesto) in CP.REGRAS
    assert CP.AREA_DA_REGRA["PROTESTO_TRAMITE"] == "ATOS"


def test_as_copias_do_compliance_batem_com_o_dominio():
    """Copiado, e não importado — então a igualdade se prova aqui."""
    import protesto_aviso as AV
    import protesto_instrumento as PI
    assert CP.VIRADA_DO_PROTESTO == PROT.VIRADA_DO_PROTESTO
    assert CP.ENTIDADE_DO_COMPROVANTE_DO_AVISO == AV.ENTIDADE_DO_COMPROVANTE
    assert CP.ENTIDADE_DO_ENVIO_DO_EDITAL == AV.ENTIDADE_DO_ENVIO_DO_EDITAL
    assert CP.ENTIDADE_DO_ENVIO_DO_XML == PCXML.ENTIDADE_DO_ENVIO_DO_XML
    assert CP.ENTIDADE_DO_INSTRUMENTO == PI.ENTIDADE_DA_ASSINATURA
    assert set(CP.ATOS_DO_XML) == set(PCXML.LETRA_DO_ATO)


def test_sem_nada_lavrado_nao_ha_achado(cg_casa):
    assert _tramite(cg_casa["db"]) == {}


def test_o_acervo_nao_vira_achado(cg_casa):
    db = cg_casa["db"]
    t = _titulo(db, "PROTESTADO", "CP/0")
    with db.transaction() as con:
        for tipo in ("INTIMACAO", "PROTESTO"):
            banco(con).escrever(
                """INSERT INTO pt_atos (titulo_id, tipo, data_ato, detalhe_json, origem, criado_em)
                   VALUES (%s, %s, %s, '{}', 'EOFICIO', %s)""", (t, tipo, DIA, AGORA))
    assert _tramite(db) == {}


def test_o_protesto_sem_prova_sem_instrumento_e_sem_xml(cg_casa):
    db = cg_casa["db"]
    t = _titulo(db, "PROTESTADO", "CP/1")
    _ato(db, t, "APONTAMENTO", data=DIA)
    _ato(db, t, "INTIMACAO", data=DIA)
    _ato(db, t, "PROTESTO", data=DIA)
    achados = _tramite(db)
    assert achados["protesto_sem_prova"]["gravidade"] == "CRITICO"
    assert "1 de 1" in achados["protesto_sem_prova"]["titulo"]
    assert "1 sem aviso" in achados["intimacao_pessoal"]["detalhe"]
    assert "1 protestos sem instrumento" in achados["instrumento"]["titulo"]
    assert str(t) in achados["xml_sem_arquivo"]["evidencia"]
    assert "antes do termo" in achados["protesto_antes_do_termo"]["titulo"]


def test_o_protesto_que_o_oficial_manteve_sai_da_conta(cg_casa):
    db = cg_casa["db"]
    t = _titulo(db, "PROTESTADO", "CP/M")
    _ato(db, t, "APONTAMENTO", data=DIA)
    _ato(db, t, "INTIMACAO", data=DIA)
    _ato(db, t, "PROTESTO", data=DIA,
         detalhe='{"mantido_pelo_oficial": {"em": "2026-10-30", "motivo": "decidido"}}')
    achados = _tramite(db)
    assert "protesto_antes_do_termo" not in achados
    assert "protesto_sem_prova" not in achados


def test_o_que_nao_foi_mantido_continua_e_a_conta_diz_quantos_sairam(cg_casa):
    db = cg_casa["db"]
    mantido = _titulo(db, "PROTESTADO", "CP/M1")
    _ato(db, mantido, "INTIMACAO", data=DIA)
    _ato(db, mantido, "PROTESTO", data=DIA,
         detalhe='{"mantido_pelo_oficial": {"em": "2026-10-30", "motivo": "decidido"}}')
    outro = _titulo(db, "PROTESTADO", "CP/M2")
    _ato(db, outro, "INTIMACAO", data=DIA)
    _ato(db, outro, "PROTESTO", data=DIA)
    achados = _tramite(db)
    assert "1 de 2" in achados["protesto_sem_prova"]["titulo"]
    assert "1 mantidos" in achados["protesto_sem_prova"]["detalhe"]
    assert str(outro) in achados["protesto_sem_prova"]["evidencia"]


def test_o_ato_de_hoje_ainda_tem_o_dia_para_ir_ao_xml(cg_casa):
    db = cg_casa["db"]
    t = _titulo(db, "PAGO", "CP/2")
    _ato(db, t, "PAGAMENTO", data="2026-10-30", detalhe='{"forma_pagamento": "ESPECIE"}')
    assert "xml_sem_arquivo" not in _tramite(db)


def test_o_pagamento_por_pix_sem_credito_e_o_pix_esperando(cg_casa):
    db = cg_casa["db"]
    t1, t2 = _titulo(db, "PAGO", "CP/3"), _titulo(db, "APONTADO", "CP/4")
    _pagamento_por_pix(db, t1)
    _pix(db, t2, situacao="AGUARDANDO_CREDITO")
    achados = _tramite(db)
    assert achados["pagamento_pix_sem_credito"]["gravidade"] == "CRITICO"
    assert achados["pix_esperando_credito"]["gravidade"] == "ATENCAO"
    # com o crédito conferido, o achado do pagamento some
    t3 = _titulo(db, "PAGO", "CP/5")
    aid = _pagamento_por_pix(db, t3)
    _pix(db, t3, ato_id=aid)
    assert str(t3) not in _tramite(db)["pagamento_pix_sem_credito"]["evidencia"]


def test_o_relato_e_em_numeros_sem_nomes(cg_casa):
    db = cg_casa["db"]
    t = _titulo(db, "PROTESTADO", "CP/6", cedente="CREDORA CONFIDENCIAL LTDA")
    _ato(db, t, "INTIMACAO", data=DIA)
    _ato(db, t, "PROTESTO", data=DIA)
    achados = _tramite(db)
    assert achados
    texto = json.dumps(list(achados.values()), ensure_ascii=False)
    assert "CONFIDENCIAL" not in texto and "EXEMPLO" not in texto and "CP/6" not in texto


def test_a_medicao_que_quebra_vira_nao_mediu_e_as_outras_continuam(cg_casa, monkeypatch):
    def quebra(ctx):
        raise RuntimeError("defeito de ensaio")

    def boa(ctx):
        return [CP._achado("PROTESTO_TRAMITE:boa", "ATOS", "PROTESTO_TRAMITE", "ATENCAO", "ok")]

    monkeypatch.setattr(CP, "TRAMITE_DO_PROTESTO", (
        ("quebra", quebra, ("pt_atos",)), ("falta", boa, ("tabela_que_nao_existe",)),
        ("boa", boa, ("pt_atos",))))
    db = cg_casa["db"]
    with db.connect() as con:
        achados = CP.regra_tramite_do_protesto(_ctx(con))
    assert [a["gravidade"] for a in achados] == ["NAO_MEDIU", "NAO_MEDIU", "ATENCAO"]
    assert "defeito de ensaio" in achados[0]["detalhe"]
    assert "tabela_que_nao_existe" in achados[1]["detalhe"]


def test_a_regra_nao_grava_nada(cg_casa):
    db = cg_casa["db"]
    t = _titulo(db, "PROTESTADO", "CP/7")
    _ato(db, t, "PROTESTO", data=DIA)

    def fotografia():
        with db.connect() as con:
            bd = banco(con)
            return tuple(int(bd.valor(f"SELECT count(*) FROM {tabela}") or 0)
                         for tabela in ("pt_atos", "pt_titulos", "cp_achados", "audit_logs"))

    antes = fotografia()
    _tramite(db)
    assert fotografia() == antes

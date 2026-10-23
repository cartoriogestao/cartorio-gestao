"""A CTP das escrituras pela API da CENSEC — `censec_ctp`, 22/10/2026.

O QUE ESTES TESTES GUARDAM
    **Que a CTP da CENSEC é a do tabelionato.** O contrato (`Doi.CtpData`,
    Swagger 2.71.2 RTM) só admite Escritura ou Procuração no `tipoAto`; a do
    Registro de Imóveis vai pela ONR («existem duas CTPs», o oficial).

    **Que a declaração é a MESMA da DOI** (`notas_doi.declaracao_da_escritura`)
    e só a língua muda: código do DOI-Web -> nome do enum da CENSEC, data ->
    date-time.

    **Que vai na carga da 2ª quinzena e não se repete** depois de aceita.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import censec_api as CA                                          # noqa: E402
import censec_ctp as CTP                                         # noqa: E402
import notas_doi as NDOI                                         # noqa: E402

AGORA = "2026-09-20T08:00:00"
CPF_A, CPF_B = "52998224725", "11144477735"


def _declaracao_doi():
    return NDOI.declarar(
        {"operacao": 11, "data_ato": "2026-09-18", "livro": "30", "folha": "193",
         "valor_operacao": 9000000, "valor_base_calculo": 9000000,
         "forma_pagamento": "5",
         "imovel": {"matricula": "4004", "rural": True, "municipio_ibge": "2198765",
                    "denominacao": "Chácara Exemplo", "localizacao": "zona rural",
                    "area_hectares": "14,94", "codigo_incra": "9500416230833"},
         "alienantes": [{"nome": "MARIA", "documento": CPF_A, "participacao": "100,00"}],
         "adquirentes": [{"nome": "JOSE", "documento": CPF_B, "participacao": "100,00"}]},
        "999999", "2198765")


def test_a_declaracao_da_doi_vira_a_lingua_da_censec():
    item = CTP.item_da_declaracao(_declaracao_doi())
    assert item["tipoServico"] == "Notarial" and item["tipoAto"] == "Escritura"
    assert item["tipoDeclaracao"] == "Original"
    assert item["tipoOperacaoImobiliaria"] == "CompraEVenda"
    assert item["formaPagamento"] == "QuitadoAVista"
    assert item["destinacao"] == "Rural"
    assert item["tipoParteTransacionada"] == "Percentual"
    assert item["dataLavraturaRegistroAverbacao"] == "2026-09-18T00:00:00"
    assert "IndicadorNaoConstaValorBaseCalculoItbiItcmd" not in item
    assert CTP.conferir(item) == []


def test_ato_de_registro_de_imoveis_nao_cabe_na_ctp_da_censec():
    # A do RI vai pela ONR. O tipoAto «4» (Registro) do DOI-Web não tem nome
    # na CENSEC, e a conferência recusa em vez de mandar.
    reg = dict(_declaracao_doi(), tipoServico="2", tipoAto="4")
    erros = CTP.conferir(CTP.item_da_declaracao(reg))
    assert any("tipoAto" in e for e in erros)


def test_todo_codigo_traduzido_existe_no_contrato():
    props = CTP.ESQUEMA["Doi.CtpData"]["properties"]
    for campo, tabela in CTP._CAMPOS_ENUM.items():
        for nome in tabela.values():
            assert nome in props[campo]["enum"], (campo, nome)
    parte = CTP.ESQUEMA["Doi.CtpAlienanteData"]["properties"]
    assert set(CTP.REGIME_BENS.values()) <= set(parte["regimeBens"]["enum"])
    assert set(CTP.MOTIVO_SEM_NI.values()) <= set(parte["motivoNaoIdentificacaoNi"]["enum"])


# ------------------------------------------------------------ na carga

@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].set_settings({"ri_codigo_ibge": "2198765"})
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    ato = c.execute(
        """INSERT INTO nt_atos (tipo, data, situacao, livro, folha, origem, criado_em,
               com_imovel, doi_transacao, doi_matricula, doi_tipo_imovel, doi_endereco,
               doi_area, valor_transacao)
           VALUES ('ESCRITURA','2026-09-18','LAVRADO','30','193','MANUAL',?,
                   1, 11, '4004', 67, 'RUA DAS FLORES, 10', '360', 12000000)""",
        (AGORA,)).lastrowid
    for nome, doc, q in (("MARIA", CPF_A, "VENDEDOR(A)"), ("JOSE", CPF_B, "COMPRADOR(A)")):
        c.execute("""INSERT INTO nt_ato_partes (ato_id, nome, documento, qualificacao,
                         participacao, criado_em) VALUES (?,?,?,?,'100,00',?)""",
                  (ato, nome, doc, q, AGORA))
    c.commit()
    yield cg_casa["db"], c, ato
    c.close()


def _falsa_central(monkeypatch):
    chamadas = []
    resposta = {"doiResult": {"success": True,
                              "carga": {"id": "c-1", "status": "AguardandoValidacao"},
                              "validationResults": []}}

    def bater(ambiente, metodo, caminho, *, corpo=None, prazo=60, pasta=None):
        chamadas.append(json.loads(corpo.decode("utf-8")))
        return {"status": 200, "json": resposta, "texto": ""}
    monkeypatch.setattr(CA, "_bater", bater)
    return chamadas


def test_a_ctp_vai_so_na_carga_da_segunda_quinzena(casa):
    db, con, ato = casa
    q1 = CA.montar_envio(con, 2026, 9, 1, "999999")
    assert "declaracoes" not in q1["corpo"]
    q2 = CA.montar_envio(con, 2026, 9, 2, "999999")
    assert [a["id"] for a in q2["atos"]["CTP"]] == [ato]
    assert q2["corpo"]["declaracoes"][0]["tipoOperacaoImobiliaria"] == "CompraEVenda"
    assert CA.conferir_corpo(q2["corpo"]) == []


def test_ctp_aceita_nao_vai_de_novo(casa, monkeypatch):
    db, con, ato = casa
    chamadas = _falsa_central(monkeypatch)
    r = CA.enviar_quinzena(db, 2026, 9, 2, cns="999999", ambiente="PRODUCAO", por="X")
    assert len(chamadas[0]["declaracoes"]) == 1
    assert {x["central"] for x in r["remessas"]} == {"CTP"}
    assert CTP.declaracoes_do_mes(con, 2026, 9, "999999")["aptos"] == []


def test_escritura_sem_participacao_fica_impedida_e_diz_por_que(casa):
    db, con, ato = casa
    con.execute("UPDATE nt_ato_partes SET participacao = NULL WHERE ato_id = ?", (ato,))
    con.commit()
    sep = CTP.declaracoes_do_mes(con, 2026, 9, "999999")
    assert sep["aptos"] == []
    assert any("participação" in p["motivo"] for p in sep["impedidos"][0]["problemas"])


def test_a_conferencia_diaria_avisa_a_escritura_que_ficou_fora_da_ctp(casa):
    from datetime import date
    import censec_automatico as CAUTO
    db, con, ato = casa
    con.execute("UPDATE nt_ato_partes SET participacao = NULL WHERE ato_id = ?", (ato,))
    con.commit()
    achados = {a["chave"]: a for a in CAUTO.regra(con, date(2026, 10, 22))}
    a = achados[f"CENSEC_IMPEDIDO:CTP:{ato}"]
    assert a["prazo"] == "2026-10-30"          # último dia útil do mês seguinte
    assert "participação" in a["detalhe"]

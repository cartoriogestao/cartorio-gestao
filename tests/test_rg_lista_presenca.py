"""Lista de presença ou certidão de não apresentação — CN-MA arts. 410, 412 e 413, III.

A Inspeção Ordinária (AUDITUS 6304) determinou: na constituição de pessoa
jurídica sem fins econômicos e nas averbações de eleição e de alteração
estatutária, sem a lista de presença pede-se a certidão de não apresentação.
Sem uma das duas, o ato não se lavra. Fora desses artigos, «não se aplica».
O RTD não entra. Dados fictícios: Associação de Exemplo, CNS 000000.
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
from banco_de_teste import conexao_de_teste  # noqa: E402

import rg_registro as RG  # noqa: E402
import rg_titulo as TIT  # noqa: E402
from bd_nativo import banco as bd  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from rg_schema import init_rg_schema  # noqa: E402

AGORA = "2026-10-30T09:00:00"
EXTENSO = "trinta dias do mês de outubro de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
TEOR = "Ata de exemplo trasladada na íntegra para o livro."
SELO = "AVESVD000000NARRKWVNJCRSVO21"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    con.execute("CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY)")
    init_rg_schema(con)
    return con


def _gravadas(con, ato_id: int):
    bruto = bd(con).valor(
        "SELECT declaracoes FROM rg_atos WHERE id=%s", (int(ato_id),))
    return json.loads(bruto) if bruto else None


def _apresentada(**extra):
    pedido = {"enquadramento": "ART410", "lista_presenca": "APRESENTADA",
              "referencia_doc": "Lista arquivada, folha 1"}
    pedido.update(extra)
    return pedido


def _certidao(**extra):
    pedido = {"enquadramento": "ART412", "lista_presenca": "NAO_APRESENTADA_CERTIDAO",
              "certidao_ref": "Certidão nº 12, 01/10/2026",
              "anexos_ids": ["7"], "tem_anexo": True}
    pedido.update(extra)
    return pedido


# ----------------------------------------------------------------- a regra


def test_constituicao_sem_a_declaracao_nao_se_lavra():
    con = banco()
    with pytest.raises(RG.RgError, match=r"art\. 410, III"):
        RG.abrir_registro(
            con, serie="PJ_A", sv=SV, agora=AGORA, data_extenso=EXTENSO,
            natureza="Estatuto de associação",
            lista_presenca={"enquadramento": "ART410"})
    assert bd(con).valor("SELECT count(*) AS n FROM rg_atos") == 0


def test_lista_apresentada_sem_anexo_nem_referencia_nao_se_lavra():
    con = banco()
    with pytest.raises(RG.RgError, match="apresentada"):
        RG.abrir_registro(
            con, serie="PJ_A", sv=SV, agora=AGORA, data_extenso=EXTENSO,
            lista_presenca={"enquadramento": "ART410",
                            "lista_presenca": "APRESENTADA"})
    assert bd(con).valor("SELECT count(*) AS n FROM rg_atos") == 0


def test_lista_apresentada_com_anexo_fica_no_ato_e_fora_do_termo():
    con = banco()
    r = RG.abrir_registro(
        con, serie="PJ_A", sv=SV, agora=AGORA, data_extenso=EXTENSO,
        natureza="Estatuto de associação", teor=TEOR,
        declaracoes={"denominacao": "ASSOCIAÇÃO DE EXEMPLO"},
        lista_presenca={"enquadramento": "ART410",
                        "lista_presenca": "APRESENTADA", "anexos_ids": ["4"],
                        "tem_anexo": True})
    gravadas = _gravadas(con, r["ato_id"])
    assert gravadas["denominacao"] == "ASSOCIAÇÃO DE EXEMPLO"
    bloco = gravadas[RG.CHAVE_LISTA_PRESENCA]
    assert bloco["lista_presenca"] == "APRESENTADA"
    assert bloco["anexo_ids"] == ["4"]
    ato = bd(con).um("SELECT * FROM rg_atos WHERE id=%s", (r["ato_id"],))
    dados = RG.dados_do_termo(con, ato, RG.registro(con, r["registro_id"]))
    assert dados["declaracoes"] == {"denominacao": "ASSOCIAÇÃO DE EXEMPLO"}
    assert RG.CHAVE_LISTA_PRESENCA not in dados["declaracoes"]
    assert "apresentada" in RG.texto_da_lista_presenca(gravadas)


def test_lista_apresentada_so_com_referencia_tambem_lavra():
    con = banco()
    r = RG.abrir_registro(
        con, serie="PJ_A", sv=SV, agora=AGORA, data_extenso=EXTENSO,
        lista_presenca=_apresentada())
    bloco = _gravadas(con, r["ato_id"])[RG.CHAVE_LISTA_PRESENCA]
    assert bloco["referencia_doc"] == "Lista arquivada, folha 1"
    assert "folha 1" in RG.texto_da_lista_presenca(bloco and {
        RG.CHAVE_LISTA_PRESENCA: bloco})


def test_averbacao_de_eleicao_sem_referencia_da_certidao_nao_lanca():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match=r"art\. 412, III"):
        RG.lancar_averbacao(
            con, r["registro_id"], teor=TEOR, sv=SV, agora=AGORA,
            data_extenso=EXTENSO,
            lista_presenca={"enquadramento": "ART412",
                            "lista_presenca": "NAO_APRESENTADA_CERTIDAO",
                            "tem_anexo": True})
    assert bd(con).valor(
        "SELECT count(*) AS n FROM rg_atos WHERE tipo='AVERBACAO'") == 0


def test_averbacao_com_certidao_e_anexo_grava_a_declaracao():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    av = RG.lancar_averbacao(
        con, r["registro_id"], teor=TEOR, sv=SV, agora=AGORA,
        data_extenso=EXTENSO, lista_presenca=_certidao())
    bloco = _gravadas(con, av["ato_id"])[RG.CHAVE_LISTA_PRESENCA]
    assert bloco["lista_presenca"] == "NAO_APRESENTADA_CERTIDAO"
    assert "nº 12" in bloco["certidao_ref"]
    assert "certidão de não apresentação" in RG.texto_da_lista_presenca(
        _gravadas(con, av["ato_id"]))


def test_certidao_sem_anexo_nao_basta():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="anexe a certidão"):
        RG.lancar_averbacao(
            con, r["registro_id"], teor=TEOR, sv=SV, agora=AGORA,
            data_extenso=EXTENSO,
            lista_presenca={"enquadramento": "ART413",
                            "lista_presenca": "NAO_APRESENTADA_CERTIDAO",
                            "certidao_ref": "Certidão nº 3, 02/10/2026"})


def test_nao_se_aplica_sem_justificativa_nao_lanca_e_com_ela_lanca():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="justificativa"):
        RG.lancar_averbacao(
            con, r["registro_id"], teor=TEOR, sv=SV, agora=AGORA,
            data_extenso=EXTENSO,
            lista_presenca={"enquadramento": "NAO_SE_APLICA",
                            "justificativa": "curta"})
    av = RG.lancar_averbacao(
        con, r["registro_id"], teor=TEOR, sv=SV, agora=AGORA,
        data_extenso=EXTENSO,
        lista_presenca={"enquadramento": "NAO_SE_APLICA",
                        "justificativa": "Matrícula de periódico, fora dos três artigos."})
    bloco = _gravadas(con, av["ato_id"])[RG.CHAVE_LISTA_PRESENCA]
    assert bloco["lista_presenca"] == "NAO_SE_APLICA"
    assert "não se aplica" in RG.texto_da_lista_presenca(_gravadas(con, av["ato_id"]))
    resumo = RG.resumo_auditoria_lista(av["cnma_lista_presenca"])
    assert resumo["enquadramento"] == "NAO_SE_APLICA"
    assert "periódico" in resumo["justificativa"]


@pytest.mark.parametrize("serie", ["TD_B", "TD_C", "TD_F"])
def test_rtd_sem_o_campo_segue_como_sempre(serie):
    con = banco()
    r = RG.abrir_registro(con, serie=serie, sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, teor=TEOR)
    assert r["numero_ordem"] == 1
    assert _gravadas(con, r["ato_id"]) is None
    av = RG.lancar_averbacao(
        con, r["registro_id"], teor=TEOR, sv=SV, agora=AGORA,
        data_extenso=EXTENSO)
    assert av["numero_ordem"] == 2
    assert _gravadas(con, av["ato_id"]) is None


def test_rcpj_antigo_sem_o_argumento_continua_abrindo():
    """Carga e acervo não mandam o campo: o passado não fica bloqueado."""
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, natureza="Estatuto de associação")
    assert r["numero_ordem"] == 1
    assert _gravadas(con, r["ato_id"]) is None


def test_a_sugestao_nao_decide_sozinha():
    assert RG.sugerir_enquadramento("Estatuto de associação sem fins econômicos") == "ART410"
    assert RG.sugerir_enquadramento("Ata de eleição da diretoria") == "ART412"
    assert RG.sugerir_enquadramento("Alteração do estatuto social") == "ART413"
    assert RG.sugerir_enquadramento("Contrato de locação") == ""
    frase = RG.completar_exigencia_com_lista(
        "Falta a ata da assembleia de fundação.", "Estatuto social")
    assert "lista de presença" in frase
    assert RG.completar_exigencia_com_lista("curta", "Estatuto social") == "curta"
    de_novo = RG.completar_exigencia_com_lista(
        "Apresentar a lista de presença da assembleia.", "Estatuto social")
    assert de_novo.count("lista de presença") == 1


def test_o_titulo_repassa_a_declaracao_ao_registro():
    con = banco()
    feito = TIT.receber(
        con, atribuicao=TIT.RCPJ, sv=SV, agora=AGORA, data_extenso=EXTENSO,
        data_apresentacao="2026-10-30", natureza="Estatuto de associação",
        apresentante="ASSOCIAÇÃO DE EXEMPLO")
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    with pytest.raises(RG.RgError, match="enquadramento"):
        TIT.registrar(
            con, feito["titulo_id"], serie="PJ_A", sv=SV, agora=AGORA,
            data_extenso=EXTENSO, teor=TEOR, lista_presenca={})
    assert bd(con).valor("SELECT count(*) AS n FROM rg_atos") == 0
    lavrado = TIT.registrar(
        con, feito["titulo_id"], serie="PJ_A", sv=SV, agora=AGORA,
        data_extenso=EXTENSO, teor=TEOR, lista_presenca=_apresentada())
    assert _gravadas(con, lavrado["ato_id"])[RG.CHAVE_LISTA_PRESENCA]["artigo"] == "410"


def test_pendencia_lista_so_o_ato_antigo_do_rcpj():
    con = banco()
    antigo = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                               data_extenso=EXTENSO)
    novo = RG.abrir_registro(
        con, serie="PJ_A", sv=SV, agora=AGORA, data_extenso=EXTENSO,
        lista_presenca=_apresentada())
    rtd = RG.abrir_registro(con, serie="TD_B", sv=SV, agora=AGORA,
                            data_extenso=EXTENSO)
    ids = {int(a["id"]) for a in RG.atos_sem_declaracao_de_lista(con)}
    assert antigo["ato_id"] in ids
    assert novo["ato_id"] not in ids
    assert rtd["ato_id"] not in ids


# ----------------------------------------------------------------- a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _abrir(casa, serie="PJ_A", **extra):
    with casa["db"].transaction() as con:
        return RG.abrir_registro(
            con, serie=serie, sv=SV, agora=casa["db"].now(),
            data_extenso=EXTENSO, natureza=extra.pop("natureza", "Estatuto"),
            requerente_nome="ASSOCIAÇÃO DE EXEMPLO", **extra)


def test_averbar_pj_sem_o_campo_volta_com_aviso_e_nao_lanca(cg_casa_logada):
    casa = cg_casa_logada
    r = _abrir(casa)
    ficha = f"/rcpj-rtd/{r['registro_id']}"
    with casa["db"].connect() as con:
        antes = bd(con).valor("SELECT count(*) AS n FROM rg_atos")
    html = casa["c"].post(ficha + "/lancar", data={
        "csrf_token": _token(casa["c"].get(ficha).get_data(as_text=True)),
        "tipo": "AVERBACAO", "natureza_ato": "Ata de eleição da diretoria",
        "data_assinatura": "01/10/2026", "teor": TEOR,
    }, follow_redirects=True).get_data(as_text=True)
    assert "enquadramento" in html
    assert "nada foi lavrado" in html.lower()
    with casa["db"].connect() as con:
        assert bd(con).valor("SELECT count(*) AS n FROM rg_atos") == antes
        assert bd(con).valor(
            "SELECT count(*) AS n FROM rg_atos WHERE tipo='AVERBACAO'") == 0


def test_averbar_pj_com_a_lista_grava_na_auditoria_e_na_ficha(cg_casa_logada):
    casa = cg_casa_logada
    # O selo digitado não é o objeto do teste: a trava do caixa, ligada,
    # desfaz a averbação antes da auditoria.
    casa["db"].set_settings({"selo_trava_caixa": "DESLIGADA"})
    r = _abrir(casa, natureza="Ata de eleição da diretoria")
    ficha = f"/rcpj-rtd/{r['registro_id']}"
    html = casa["c"].post(ficha + "/lancar", data={
        "csrf_token": _token(casa["c"].get(ficha).get_data(as_text=True)),
        "tipo": "AVERBACAO", "natureza_ato": "Ata de eleição da diretoria",
        "data_assinatura": "01/10/2026",
        "enquadramento_cnma": "ART412", "lista_presenca": "APRESENTADA",
        "lista_presenca_ref": "Lista da assembleia, folha 2",
        "selo": SELO,
    }, follow_redirects=True).get_data(as_text=True)
    with casa["db"].connect() as con:
        ato = bd(con).um(
            "SELECT * FROM rg_atos WHERE registro_id=%s AND tipo='AVERBACAO'",
            (r["registro_id"],))
        assert ato, html
        assert "folha 2" in (ato["declaracoes"] or "")
        aud = bd(con).um(
            "SELECT details FROM audit_logs WHERE action=%s ORDER BY id DESC LIMIT 1",
            ("RG_ATO",))
    assert aud and "lista_presenca" in aud["details"]
    assert "APRESENTADA" in aud["details"]
    ficha_html = casa["c"].get(ficha).get_data(as_text=True)
    assert "Lista de presença: apresentada" in ficha_html
    assert "folha 2" in ficha_html


def test_o_formulario_de_averbacao_do_pj_pergunta_os_dois_campos(cg_casa_logada):
    casa = cg_casa_logada
    pj = _abrir(casa)
    td = _abrir(casa, serie="TD_B", natureza="Contrato de locação")
    html_pj = casa["c"].get(f"/rcpj-rtd/{pj['registro_id']}").get_data(as_text=True)
    html_td = casa["c"].get(f"/rcpj-rtd/{td['registro_id']}").get_data(as_text=True)
    assert 'name="enquadramento_cnma"' in html_pj
    assert 'name="lista_presenca"' in html_pj
    assert 'name="enquadramento_cnma"' not in html_td
    assert 'name="lista_presenca"' not in html_td


def test_averbar_rtd_sem_o_campo_lanca(cg_casa_logada):
    casa = cg_casa_logada
    casa["db"].set_settings({"selo_trava_caixa": "DESLIGADA"})
    r = _abrir(casa, serie="TD_B", natureza="Contrato de locação")
    ficha = f"/rcpj-rtd/{r['registro_id']}"
    casa["c"].post(ficha + "/lancar", data={
        "csrf_token": _token(casa["c"].get(ficha).get_data(as_text=True)),
        "tipo": "AVERBACAO", "teor": TEOR, "selo": SELO,
    }, follow_redirects=True)
    with casa["db"].connect() as con:
        assert bd(con).valor(
            "SELECT count(*) AS n FROM rg_atos WHERE tipo='AVERBACAO'") == 1


def test_registrar_titulo_pj_sem_e_com_a_declaracao(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    novo = "/rcpj-rtd/titulos/novo?atribuicao=3"
    c.post(novo, data={
        "csrf_token": _token(c.get(novo).get_data(as_text=True)),
        "data_apresentacao": "2026-10-30",
        "apresentante": "ASSOCIAÇÃO DE EXEMPLO",
        "natureza": "Estatuto de associação", "forma": "PAPEL",
    }, follow_redirects=True)
    with casa["db"].connect() as con:
        titulo_id = int(bd(con).valor("SELECT id FROM rg_titulos ORDER BY id DESC LIMIT 1"))
    ficha = f"/rcpj-rtd/titulo/{titulo_id}"
    c.post(ficha + "/qualificar", data={
        "csrf_token": _token(c.get(ficha).get_data(as_text=True)),
        "resultado": "POSITIVA",
    }, follow_redirects=True)
    html = c.get(ficha).get_data(as_text=True)
    assert 'name="enquadramento_cnma"' in html
    assert 'name="lista_presenca"' in html
    recusa = c.post(ficha + "/registrar", data={
        "csrf_token": _token(html), "serie": "PJ_A", "teor": TEOR,
    }, follow_redirects=True).get_data(as_text=True)
    assert "enquadramento" in recusa
    with casa["db"].connect() as con:
        assert bd(con).valor("SELECT count(*) AS n FROM rg_atos") == 0
    c.post(ficha + "/registrar", data={
        "csrf_token": _token(c.get(ficha).get_data(as_text=True)),
        "serie": "PJ_A", "teor": TEOR,
        "enquadramento_cnma": "ART410", "lista_presenca": "APRESENTADA",
        "lista_presenca_ref": "Lista da fundação, folha 1",
    }, follow_redirects=True)
    with casa["db"].connect() as con:
        ato = bd(con).um("SELECT declaracoes FROM rg_atos ORDER BY id DESC LIMIT 1")
        aud = bd(con).um(
            "SELECT details FROM audit_logs WHERE action=%s ORDER BY id DESC LIMIT 1",
            ("RG_TITULO_REGISTRADO",))
    assert ato and "ART410" in ato["declaracoes"]
    assert aud and "lista_presenca" in aud["details"]


def test_a_negativa_do_estatuto_pede_a_lista_na_exigencia(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    novo = "/rcpj-rtd/titulos/novo?atribuicao=3"
    c.post(novo, data={
        "csrf_token": _token(c.get(novo).get_data(as_text=True)),
        "data_apresentacao": "2026-10-30",
        "apresentante": "ASSOCIAÇÃO DE EXEMPLO",
        "natureza": "Estatuto de associação", "forma": "PAPEL",
    }, follow_redirects=True)
    with casa["db"].connect() as con:
        titulo_id = int(bd(con).valor("SELECT id FROM rg_titulos ORDER BY id DESC LIMIT 1"))
    ficha = f"/rcpj-rtd/titulo/{titulo_id}"
    c.post(ficha + "/qualificar", data={
        "csrf_token": _token(c.get(ficha).get_data(as_text=True)),
        "resultado": "NEGATIVA",
        "exigencias": "Falta a ata da assembleia de fundação.",
    }, follow_redirects=True)
    with casa["db"].connect() as con:
        texto = bd(con).valor(
            "SELECT exigencias FROM rg_qualificacoes WHERE titulo_id=%s",
            (titulo_id,))
    assert "lista de presença" in texto
    assert "410" in texto


def test_a_lista_de_pendencias_mostra_o_ato_antigo(cg_casa_logada):
    casa = cg_casa_logada
    antigo = _abrir(casa)
    html = casa["c"].get("/rcpj-rtd/pendencias-lista-presenca").get_data(as_text=True)
    assert "ASSOCIAÇÃO DE EXEMPLO" in html
    assert f"/rcpj-rtd/{antigo['registro_id']}" in html

"""O relatório anual do uso de IA à COGEX e as telas dele (LF01, 19/10/2026).

O QUE SE PROVA AQUI
    - o relatório tem as quatro partes do art. 170, § 4º (sistemas e
      finalidades, medidas de segurança, incidentes ou falhas, mitigação),
      o uso por mês, finalidade e provedor, o lembrete federal e o aviso de
      conferir o texto oficial;
    - balcão e auditor não chegam nele, nem na tela dos incidentes;
    - o incidente registrado na tela aparece no relatório — e dado de pessoa
      escrito nele sai mascarado;
    - fornecedor fora do requisito do MA vira PENDÊNCIA, sem decisão;
    - o menu leva ao relatório, e o painel lembra dele em janeiro;
    - o PDF sai pelo caminho de impressão da casa, e o que não sai volta à
      página com a frase.

Equipe e serventia fictícias (as do conftest). Nada de dado real de pessoa.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ia_relatorio as IAR                      # noqa: E402
import ia_uso as USO                            # noqa: E402

SENHA = "Senha#12345"
ANO = 2025


def _token(c, caminho: str = "/administrativo/gestor/ia") -> str:
    html = c.get(caminho).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _uso(casa, **campos) -> None:
    padrao = {"modulo": "gestor_leitura", "finalidade": "gestor_leitura",
              "provedor": "claude", "modelo": "claude-sonnet-5", "usuario": "rotina do gestor",
              "atribuicao": "RI", "referencia": "ri_atos:1", "mascarado": False,
              "tokens_entrada": 100, "tokens_saida": 10, "resultado": "ok"}
    padrao.update(campos)
    assert USO.registrar(casa["dados"], **padrao)


def _do_ano(casa, ano: int = ANO) -> None:
    """Põe as linhas gravadas agora no ano do relatório — `quando` é do Python."""
    from bd_nativo import banco
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE ia_uso SET quando = %s || substring(quando FROM 5)",
                            (str(ano),))


def test_o_relatorio_tem_as_quatro_partes_e_o_uso_do_ano(cg_casa_logada):
    casa = cg_casa_logada
    _uso(casa)
    _uso(casa, finalidade="agente", modulo="agente", provedor="deepseek",
         mascarado=True, tokens_entrada=7, tokens_saida=3)
    _uso(casa, resultado="erro", erro="HTTP 429", tokens_entrada=0, tokens_saida=0)
    _do_ano(casa)

    pagina = casa["c"].get(f"/gestor/relatorio-ia?ano={ANO}")
    assert pagina.status_code == 200
    html = pagina.get_data(as_text=True)
    for parte in ("1. Sistemas e finalidades", "2. Medidas de segurança",
                  "3. Incidentes ou falhas", "4. Ações de mitigação",
                  "Uso por mês", "Uso por finalidade", "Uso por provedor"):
        assert parte in html, parte
    assert "conferir o texto oficial do Código de Normas" in html
    assert "Provimento CN 213/2026" in html and "Justiça Aberta" in html
    assert "Leitura dos textos pelo gestor" in html and "Robôs de rascunho" in html
    assert "3 chamada(s) em 2025" in html
    assert "1 chamada(s) com máscara, 2 sem máscara" in html
    assert "HTTP 429" in html
    # antes do primeiro registro não há contagem — e a página diz isso
    assert "O registro de cada chamada começou em" in html and f"/{ANO}:" in html
    # o endereço da casa leva à mesma página
    assert casa["c"].get(f"/administrativo/gestor/relatorio-ia?ano={ANO}").status_code == 200


def test_a_montagem_soma_por_mes_finalidade_e_provedor(cg_casa_logada):
    casa = cg_casa_logada
    _uso(casa)
    _uso(casa, provedor="deepseek")
    _do_ano(casa)
    with casa["db"].connect() as con:
        r = IAR.montar(con, ANO)
    assert r["total"]["chamadas"] == 2 and r["total"]["entrada"] == 200
    assert sum(m["chamadas"] for m in r["por_mes"]) == 2 and len(r["por_mes"]) == 12
    assert [(f["codigo"], f["chamadas"]) for f in r["por_finalidade"]] == [("gestor_leitura", 2)]
    assert sorted((p["provedor"], p["chamadas"]) for p in r["por_provedor"]) == [
        ("claude", 1), ("deepseek", 1)]
    with casa["db"].connect() as con:
        assert IAR.montar(con, ANO + 1)["total"]["chamadas"] == 0


@pytest.mark.parametrize("papel", ["USER", "AUDITOR"])
def test_balcao_e_auditor_nao_acessam(cg_casa, papel):
    from conftest import cg_login
    cg_casa["db"].create_user("elisa", "Elisa Exemplo Lima", SENHA, papel)
    c = cg_casa["c"]
    cg_login(c, "elisa", SENHA)
    for caminho in ("/gestor/relatorio-ia", "/administrativo/gestor/relatorio-ia",
                    "/administrativo/gestor/relatorio-ia/papel", "/administrativo/gestor/ia"):
        assert c.get(caminho).status_code == 403, caminho
    assert c.post("/administrativo/gestor/ia/incidente",
                  data={"data": "2025-03-04", "o_que": "x"}).status_code in (400, 403)
    assert "Relatório anual de IA" not in c.get("/").get_data(as_text=True)


def test_incidente_registrado_aparece_no_relatorio_sem_dado_de_pessoa(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.post("/administrativo/gestor/ia/incidente", data={
        "csrf_token": _token(c), "data": f"{ANO}-03-04", "sistema": "rc_leitura",
        "o_que": "A leitura trocou a data de nascimento; CPF 000.000.048-55 citado.",
        "impacto": "Rascunho errado, corrigido antes de lavrar.",
        "causa": "Página digitalizada torta.", "mitigacao": "Conferência dupla da data.",
        "comunicado_a": "Oficial"}, follow_redirects=True)
    assert "Incidente registrado" in r.get_data(as_text=True)
    tela = c.get("/administrativo/gestor/ia").get_data(as_text=True)
    assert "A leitura trocou a data de nascimento" in tela
    assert "000.000.048-55" not in tela

    html = c.get(f"/gestor/relatorio-ia?ano={ANO}").get_data(as_text=True)
    assert "A leitura trocou a data de nascimento" in html
    assert "Conferência dupla da data." in html
    assert "Leitura de documentos do Registro Civil" in html
    assert "000.000.048-55" not in html
    outro = c.get(f"/gestor/relatorio-ia?ano={ANO - 1}").get_data(as_text=True)
    assert "A leitura trocou a data de nascimento" not in outro


def test_incidente_sem_o_que_aconteceu_e_recusado(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.post("/administrativo/gestor/ia/incidente", data={
        "csrf_token": _token(c), "data": f"{ANO}-03-04", "o_que": "  "},
        follow_redirects=True)
    assert "Descreva o que aconteceu." in r.get_data(as_text=True)
    with cg_casa_logada["db"].connect() as con:
        assert USO.incidentes(con) == []


def test_fornecedor_fora_do_requisito_vira_pendencia_sem_decidir(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    c.post("/administrativo/gestor/ia/fornecedor", data={
        "csrf_token": _token(c), "provedor": "claude", "empresa": "Empresa Exemplo",
        "pais_processa": "Estados Unidos", "pais_armazena": "Estados Unidos",
        "retencao": "guarda", "retencao_prazo": "30 dias", "treinamento": "nao",
        "iso27001": "nao_sei", "contrato": "termos de uso"})
    _uso(casa)
    _do_ano(casa)
    html = c.get(f"/gestor/relatorio-ia?ano={ANO}").get_data(as_text=True)
    assert "Empresa Exemplo" in html
    assert "fora do Brasil (Estados Unidos)" in html
    assert "o requisito do MA pede o banco no servidor da serventia" in html
    assert "ISO 27001: não sei" in html
    assert "o sistema não decide pelo oficial" in html


def test_o_menu_leva_ao_relatorio_e_o_painel_lembra_em_janeiro(cg_casa_logada, monkeypatch):
    c = cg_casa_logada["c"]
    monkeypatch.setattr(IAR, "hoje", lambda: date(2027, 1, 10))
    painel = c.get("/").get_data(as_text=True)
    assert "Relatório anual de IA" in painel
    assert "Relatório de IA do ano anterior (2026)" in painel
    monkeypatch.setattr(IAR, "hoje", lambda: date(2027, 2, 1))
    assert "Relatório de IA do ano anterior" not in c.get("/").get_data(as_text=True)


def test_o_pdf_sai_pelo_caminho_de_impressao_e_o_que_nao_sai_volta(cg_casa_logada, monkeypatch):
    import impressao_pdf as PDFIMP
    c = cg_casa_logada["c"]
    recebido = {}

    def arquivo_de_html(html, *, nome, formato=None, get_setting=None):
        recebido.update(html=html, nome=nome)
        return b"%PDF-1.4", "application/pdf", f"{nome}.pdf", "inline"

    monkeypatch.setattr(PDFIMP, "arquivo_de_html", arquivo_de_html)
    r = c.get(f"/administrativo/gestor/relatorio-ia/papel?ano={ANO}")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert recebido["nome"] == f"relatorio-ia-{ANO}"
    assert "4. Ações de mitigação" in recebido["html"] and "Baixar em PDF" not in recebido["html"]

    def sem_chrome(*_a, **_k):
        raise PDFIMP.PdfError("Chrome/Edge nao encontrado nesta maquina.")

    monkeypatch.setattr(PDFIMP, "arquivo_de_html", sem_chrome)
    r = c.get(f"/administrativo/gestor/relatorio-ia/papel?ano={ANO}")
    assert r.status_code == 302 and "/administrativo/gestor/relatorio-ia" in r.headers["Location"]


def test_o_ano_da_tela():
    assert IAR.ano_pedido("2024", date(2026, 10, 19)) == 2024
    assert IAR.ano_pedido("", date(2026, 10, 19)) == 2026
    assert IAR.ano_pedido("abc", date(2027, 1, 5)) == 2026
    assert IAR.ano_pedido("2999", date(2026, 10, 19)) == 2026

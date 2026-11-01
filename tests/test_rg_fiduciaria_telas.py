"""O PROCESSO FIDUCIÁRIO, O SOBRESTAMENTO E A DOI DO RTD, pela tela (01/11/2026). Dados fictícios."""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rg_fiduciaria as FID


def _token(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


def _titulo(casa) -> tuple[str, str]:
    c = casa["c"]
    html = c.get("/rcpj-rtd/titulos/novo?atribuicao=4").get_data(as_text=True)
    t = _token(html)
    r = c.post("/rcpj-rtd/titulos/novo", data={"csrf_token": t, "atribuicao": "4", "data_apresentacao": "2026-09-01",
                                               "apresentante": "Banco Exemplo", "natureza": "Requerimento"})
    return r.headers["Location"].rstrip("/").split("/")[-1], t


def _processo(casa) -> tuple[str, str]:
    titulo, t = _titulo(casa)
    r = casa["c"].post("/rcpj-rtd/fiduciaria/nova", data={
        "csrf_token": t, "titulo_id": titulo, "credor_nome": "Banco Exemplo", "devedor_nome": "Maria Exemplo",
        "bem_descricao": "Motocicleta exemplo", "valor_divida": "1.000,00"})
    assert r.status_code == 302
    return r.headers["Location"].rstrip("/").split("/")[-1], t


def test_o_rito_inteiro_pela_tela_sem_erro(casa):
    c = casa["c"]
    pid, t = _processo(casa)
    acao = f"/rcpj-rtd/fiduciaria/{pid}/acao"
    itens = [r["chave"] for r in FID.REQUISITOS if r["obrigatorio"]]
    assert "O que o requerimento traz" in c.get(f"/rcpj-rtd/fiduciaria/{pid}").get_data(as_text=True)
    assert c.post(acao, data={"csrf_token": t, "acao": "qualificar", "resultado": "POSITIVA", "itens": itens, "dia": "2026-09-01"}).status_code == 302
    for campos in ({"acao": "notificar", "forma": "ELETRONICA", "dia": "2026-09-01"},
                   {"acao": "ciencia", "dia": "2026-09-02"},
                   {"acao": "requerer_busca", "dia": "2026-10-01", "valor": "1000,00", "planilha": "1"},
                   {"acao": "providencia", "qual": "CENTRAL", "dia": "2026-10-01"},
                   {"acao": "diligencia", "dia": "2026-10-05", "local": "Rua Exemplo", "resultado": "POSITIVA"}):
        assert c.post(acao, data={"csrf_token": t, **campos}).status_code == 302
    ficha = c.get(f"/rcpj-rtd/fiduciaria/{pid}").get_data(as_text=True)
    assert "Propriedade consolidada" in ficha and "Para averbar" in ficha
    for peca in ("NOTIFICACAO", "CERTIDAO_BUSCA", "AUTO", "CONSOLIDACAO"):
        r = c.get(f"/rcpj-rtd/fiduciaria/{pid}/peca/{peca}")
        assert r.status_code == 200 and "Maria Exemplo" in r.get_data(as_text=True)
    assert "Propriedade consolidada" in c.get("/rcpj-rtd/fiduciaria").get_data(as_text=True)


def test_passo_fora_de_hora_e_aviso_e_nao_erro(casa):
    pid, t = _processo(casa)
    r = casa["c"].post(f"/rcpj-rtd/fiduciaria/{pid}/acao", data={
        "csrf_token": t, "acao": "ciencia", "dia": "2026-09-02"}, follow_redirects=True)
    assert r.status_code == 200 and "não cabe agora" in r.get_data(as_text=True)


def test_peca_que_ainda_nao_cabe_volta_para_o_processo(casa):
    pid, _ = _processo(casa)
    assert casa["c"].get(f"/rcpj-rtd/fiduciaria/{pid}/peca/AUTO").status_code == 302


def test_titulo_sobrestado_avisa_na_ficha_e_recusa_a_qualificacao(casa):
    c = casa["c"]
    titulo, t = _titulo(casa)
    c.post(f"/rcpj-rtd/titulo/{titulo}/sobrestar", data={
        "csrf_token": t, "tipo": "DUVIDA", "motivo": "Dúvida suscitada ao juiz."})
    assert "Lançamento sobrestado" in c.get(f"/rcpj-rtd/titulo/{titulo}").get_data(as_text=True)
    r = c.post(f"/rcpj-rtd/titulo/{titulo}/qualificar", data={"csrf_token": t, "resultado": "POSITIVA"},
               follow_redirects=True)
    assert "sobrestado" in r.get_data(as_text=True)


def test_a_doi_marcada_na_ficha_aparece_na_tela_da_doi(casa):
    c = casa["c"]
    con = sqlite3.connect(casa["banco"])
    con.execute("""INSERT INTO rg_registros(atribuicao, serie, numero, situacao, origem, origem_chave, criado_em)
                   VALUES (4,'TD_B',7,'ATIVO','TESTE','t:7','2026-09-01T09:00:00')""")
    registro = con.execute("SELECT id FROM rg_registros WHERE origem_chave='t:7'").fetchone()[0]
    con.commit()
    con.close()
    ficha = c.get(f"/rcpj-rtd/{registro}").get_data(as_text=True)
    r = c.post(f"/rcpj-rtd/{registro}/doi", data={
        "csrf_token": _token(ficha), "operacao": "11", "matricula": "123", "valor": "1000,00", "data": "2026-09-01"})
    assert r.status_code == 302
    assert "RTD, registro 7" in c.get("/registro-imoveis/doi?competencia=2026-09").get_data(as_text=True)

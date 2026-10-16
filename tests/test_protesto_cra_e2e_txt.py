"""E2E slice 4 (30/09/2026): remessa TXT — conferir, receber, apontar + CRA21.

Exercita o caminho de tela (`test_protesto_remessa_web`) integrado ao envio
automatico de Confirmacao e andamento (`protesto_cra_envio`), com rede CRA
mockada para reproducibilidade no sandbox de testes (DB isolado do pytest).
"""
from __future__ import annotations

import re
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED

SENHA = "Senha#12345"
EXEMPLO = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa["app"]
    banco = cg_casa["banco"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    cg_casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post(
        "/login",
        data={
            "username": "tabeliao",
            "password": SENHA,
            "csrf_token": _token(c.get("/login").get_data(as_text=True)),
        },
        follow_redirects=True,
    )
    return {"app": app, "c": c, "banco": banco}


def _con(banco: str) -> sqlite3.Connection:
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    return con


def _conferir(c, conteudo=EXEMPLO, nome="B0001307.221"):
    tela = c.get("/protesto/remessas").get_data(as_text=True)
    return c.post(
        "/protesto/remessas/conferir",
        data={"csrf_token": _token(tela), "arquivo": (BytesIO(conteudo), nome)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _receber(c, conteudo=EXEMPLO, **extra):
    resposta = _conferir(c, conteudo)
    html = resposta.get_data(as_text=True)
    achado = re.search(r'name="conteudo" value="([^"]*)"', html)
    assert achado, "a conferencia nao devolveu o arquivo para o passo seguinte"
    dados = {
        "csrf_token": _token(html),
        "conteudo": achado.group(1)
        .replace("&#34;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">"),
        "nome_arquivo": "B0001307.221",
        "apontar": "1",
    }
    dados.update(extra)
    return c.post("/protesto/remessas/receber", data=dados, follow_redirects=True)


def _mock_cra_soap(monkeypatch):
    """Grava cada operacao SOAP e devolve codigo 0000."""
    chamadas: list[str] = []

    class Resposta:
        def read(self):
            return (
                b"<return><relatorio><codigo>0000</codigo></relatorio></return>"
            )

        status = 200

        # O transporte comum (`centrais_http`, 05/10/2026) lê os cabeçalhos.
        def getheaders(self):
            return []

    class Conexao:
        def __init__(self, *a, **k):
            pass

        def request(self, metodo, caminho, body=None, headers=None):
            texto = (body or b"").decode("utf-8", errors="replace")
            if "TituloComplemento" in texto:
                chamadas.append("TituloComplemento")
            elif "Confirmacao" in texto:
                chamadas.append("Confirmacao")
            elif "Retorno" in texto:
                chamadas.append("Retorno")
            else:
                chamadas.append("outro")

        def getresponse(self):
            return Resposta()

        def close(self):
            pass

    import http.client as hc

    monkeypatch.setattr(hc, "HTTPSConnection", Conexao)
    return chamadas


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def test_txt_conferir_receber_apontar_dispara_envio_cra_producao(
        monkeypatch, cg_casa, tmp_path, s):
    """**CONTRATO MUDADO EM 14/10/2026** — «agora é tudo produção». Este
    teste se chamava `..._dispara_envio_cra_homolog`: a remessa TXT, sem
    ambiente, caía na homologação, com a caixa dela ligada. Agora cai na
    produção, e o envio sai com a credencial e a caixa da produção."""
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    CRED.gravar(
        CRED.CRA, usuario="sandbox", senha="Sandbox@Sandbox1", pasta=tmp_path,
        ambiente=CRED.PRODUCAO,
    )
    chamadas = _mock_cra_soap(monkeypatch)
    cg_casa["db"].set_settings({"cra_auto_enviar_producao": "1"})

    html = _receber(s["c"]).get_data(as_text=True)
    assert "Remessa recebida" in html
    assert (
        "A CRA (producao) recebeu" in html
        or "confirmacao e andamento enviados" in html
        or "confirmação e andamento enviados" in html
    )

    con = _con(s["banco"])
    remessa = con.execute("SELECT * FROM pt_remessas").fetchone()
    assert remessa["recebidos"] == 1 and remessa["apontados"] == 1
    tit = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert tit["situacao"] == "APONTADO"

    confirmacao = con.execute(
        "SELECT * FROM pt_retornos WHERE id=?",
        (remessa["confirmacao_id"],),
    ).fetchone()
    assert confirmacao["tipo"] == "SDTBFOCRT"
    assert confirmacao["cra_enviado_em"]
    assert confirmacao["cra_enviado_ambiente"] == "PRODUCAO"
    assert not confirmacao["cra_envio_erro"]

    andamento = con.execute(
        "SELECT * FROM pt_retornos WHERE tipo='SDTBFOAND' ORDER BY id DESC LIMIT 1",
    ).fetchone()
    assert andamento and andamento["cra_enviado_em"]

    assert chamadas.count("Confirmacao") == 1
    # O ANDAMENTO VAI PELA `TituloComplemento`, e não pela `Retorno` — medido
    # na homologação em 13/10/2026: pela `Retorno` a CRA respondia vazio e
    # não registrava; pela `TituloComplemento` os 7 títulos voltaram «2322».
    assert chamadas.count("TituloComplemento") == 1
    assert chamadas.count("Retorno") == 0


def test_txt_auto_envio_desligado_nao_chama_cra(monkeypatch, cg_casa, tmp_path):
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    # 14/10/2026: produção, com a caixa da produção desligada (era a da
    # homologação, que saiu da tela).
    CRED.gravar(
        CRED.CRA, usuario="sandbox", senha="Sandbox@Sandbox1", pasta=tmp_path,
        ambiente=CRED.PRODUCAO,
    )
    chamadas = _mock_cra_soap(monkeypatch)
    cg_casa["db"].set_settings({"cra_auto_enviar_producao": "0"})
    sess = _sessao(cg_casa)

    html = _receber(sess["c"]).get_data(as_text=True)
    assert "Remessa recebida" in html
    assert "A CRA (producao) recebeu" not in html

    con = _con(sess["banco"])
    confirmacao_id = con.execute(
        "SELECT confirmacao_id FROM pt_remessas",
    ).fetchone()[0]
    row = con.execute(
        "SELECT cra_enviado_em FROM pt_retornos WHERE id=?",
        (confirmacao_id,),
    ).fetchone()
    assert not row["cra_enviado_em"]
    assert chamadas == []
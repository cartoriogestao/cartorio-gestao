"""O CADASTRO DE DESPESAS É DE TODOS — e cada um vê o que cadastrou.

Ordem do oficial (28/10/2026): «libere o acesso para cadastramento de despesas
para todos usuários». O perfil USER passa a cadastrar; a lista e a ficha que
ele abre são só as dele (a lista inteira traz salários e honorários); cancelar,
autorizar, pagar, as recorrentes e o relatório continuam com quem já tinha.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP
from tests.conftest import cg_login

FAVORECIDO = "00000010000127"     # 00.000.010/0001-27, fictício (o de test_despesas)
AGORA = datetime(2026, 10, 28, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
SENHA = "Senha#12345"


def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def _do_oficial(db):
    """Uma despesa cadastrada pelo ADMIN — a que o USER não deve ver."""
    with db.transaction() as con:
        return DP.cadastrar(
            con, agora=AGORA, por="MARIO EXEMPLO DOS SANTOS", origem="MANUAL",
            chave_origem=None, beneficiario_nome="PRESTADOR FICTICIO",
            beneficiario_documento=FAVORECIDO, valor_centavos=500000,
            vencimento="2026-11-05", forma=DP.PIX_CHAVE, codigo="prestador@example.com",
            descricao="Honorários do mês do prestador", categoria="PESSOAL",
            documento_especie="Recibo")


def _como_usuario(casa):
    casa["db"].create_user("carla", "CARLA EXEMPLO", SENHA, "USER")
    c = casa["app"].test_client()
    cg_login(c, "carla", SENHA)
    return c


def test_o_usuario_cadastra_e_ve_so_as_que_cadastrou(cg_casa_logada):
    casa = cg_casa_logada
    alheia = _do_oficial(casa["db"])
    c = _como_usuario(casa)
    assert c.get("/administrativo/despesas/nova").status_code == 200
    r = c.post("/administrativo/despesas/nova", data={
        "csrf_token": _token(c, "/administrativo/despesas/nova"), "categoria": "MATERIAIS",
        "descricao": "Papel A4 para o balcão", "beneficiario_nome": "PAPELARIA FICTICIA",
        "beneficiario_documento": FAVORECIDO, "valor": "123,45", "vencimento": "2026-11-10",
        "forma": DP.PIX_CHAVE, "codigo": "papelaria@example.com",
        "documento_especie": "Nota fiscal"}, follow_redirects=True)
    assert r.status_code == 200 and "Aguardando a autorização do oficial" in r.get_data(as_text=True)
    lista = c.get("/administrativo/despesas").get_data(as_text=True)
    assert "PAPELARIA FICTICIA" in lista and "PRESTADOR FICTICIO" not in lista
    assert c.get(f"/administrativo/despesas/{alheia}").status_code == 403


def test_o_usuario_nao_cancela_nem_abre_recorrentes_e_relatorio(cg_casa_logada):
    casa = cg_casa_logada
    alheia = _do_oficial(casa["db"])
    c = _como_usuario(casa)
    for url in ("/administrativo/despesas/recorrentes", "/administrativo/despesas/relatorio",
                "/administrativo/despesas/recorrentes/nova"):
        assert c.get(url).status_code == 403, url
    r = c.post(f"/administrativo/despesas/{alheia}/cancelar",
               data={"csrf_token": _token(c, "/administrativo/despesas/nova"),
                     "motivo": "tentativa de quem só cadastra"})
    assert r.status_code == 403
    with casa["db"].connect() as con:
        assert DP.despesa(con, alheia)["situacao"] == DP.AGUARDANDO


def test_o_menu_mostra_despesas_ao_usuario(cg_casa_logada):
    c = _como_usuario(cg_casa_logada)
    assert "/administrativo/despesas" in c.get("/").get_data(as_text=True)

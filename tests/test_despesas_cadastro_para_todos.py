"""CADASTRAR É DE TODOS, E VER É DO TITULAR.

Ordem do oficial (28/10/2026): «libere o acesso para cadastramento de despesas para todos
usuários». E (31/10/2026): «usuários devem poder abastecer despesas, mas não ver os dados de
despesas. O balanço deve ser privado do usuário administrador». Quem só cadastra não vê nem o
que acabou de gravar; outro ADMIN também não; o carnê-leão segue a mesma régua.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP
import despesas_documento as DD
from tests.conftest import cg_login

FAVORECIDO = "00000010000127"     # 00.000.010/0001-27, fictício (o de test_despesas)
AGORA = datetime(2026, 10, 28, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
SENHA = "Senha#12345"
NOVA = "/administrativo/despesas/nova"
LISTA = "/administrativo/despesas"
SO_DO_TITULAR = (LISTA + "/recorrentes", LISTA + "/relatorio", LISTA + "/recorrentes/nova",
                 LISTA + "/configuracao", "/administrativo/carne-leao")


def _token(c, url=NOVA):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def _do_oficial(db):
    """Uma despesa cadastrada pelo titular — a que os outros não devem ver."""
    with db.transaction() as con:
        return DP.cadastrar(
            con, agora=AGORA, por="MARIO EXEMPLO DOS SANTOS", origem="MANUAL",
            chave_origem=None, beneficiario_nome="PRESTADOR FICTICIO",
            beneficiario_documento="00000000191", valor_centavos=500000,
            vencimento="2026-11-05", forma=DP.PIX_CHAVE, codigo="prestador@example.com",
            descricao="Honorários do mês do prestador", categoria="PESSOAL",
            documento_especie="Recibo")


def _como(casa, login, nome, papel):
    casa["db"].create_user(login, nome, SENHA, papel)
    c = casa["app"].test_client()
    cg_login(c, login, SENHA)
    return c


def _post_da_papelaria(c):
    return c.post(NOVA, data={
        "csrf_token": _token(c), "categoria": "MATERIAIS",
        "descricao": "Papel A4 para o balcão", "beneficiario_nome": "PAPELARIA FICTICIA",
        "beneficiario_documento": FAVORECIDO, "valor": "123,45", "vencimento": "2026-11-10",
        "forma": DP.PIX_CHAVE, "codigo": "papelaria@example.com",
        "documento_especie": "Nota fiscal"}, follow_redirects=True)


def test_documento_grande_nao_estoura_a_tela(cg_casa_logada):
    """of-0155: arquivo acima de 15 MB volta com aviso, sem gravar e sem 500."""
    c = _como(cg_casa_logada, "carla", "CARLA EXEMPLO", "USER")
    grande = b"x" * (DD.MAX_BYTES + 1)
    r = c.post(NOVA, data={
        "csrf_token": _token(c), "categoria": "MATERIAIS",
        "descricao": "Papel A4 para o balcão", "beneficiario_nome": "PAPELARIA FICTICIA",
        "beneficiario_documento": FAVORECIDO, "valor": "123,45", "vencimento": "2026-11-10",
        "forma": DP.PIX_CHAVE, "codigo": "papelaria@example.com",
        "documento_especie": "Nota fiscal",
        "documento": (io.BytesIO(grande), "nota.pdf")},
        content_type="multipart/form-data")
    assert r.status_code == 200
    assert "15 MB" in r.get_data(as_text=True)
    with cg_casa_logada["db"].connect() as con:
        nomes = [d["beneficiario_nome"] for d in DP.listar(con)]
    assert "PAPELARIA FICTICIA" not in nomes


def test_falha_inesperada_ao_lancar_nao_vira_500(cg_casa_logada, monkeypatch):
    """of-0155: o que não é regra da despesa volta à tela, e nada fica gravado."""
    def estourou(*_a, **_k):
        raise RuntimeError("coluna que faltou")

    monkeypatch.setattr(DP, "cadastrar", estourou)
    c = _como(cg_casa_logada, "carla", "CARLA EXEMPLO", "USER")
    r = _post_da_papelaria(c)
    assert r.status_code == 200
    assert "RuntimeError" in r.get_data(as_text=True)
    assert "Nada foi gravado" in r.get_data(as_text=True)


@pytest.mark.parametrize("papel", ["USER", "MANAGER"])
def test_quem_so_cadastra_grava_e_nao_ve_nem_a_propria(cg_casa_logada, papel):
    casa = cg_casa_logada
    alheia = _do_oficial(casa["db"])
    c = _como(casa, "carla", "CARLA EXEMPLO", papel)
    r = _post_da_papelaria(c)
    tela = r.get_data(as_text=True)
    assert r.status_code == 200 and "Despesa cadastrada" in tela and "PAPELARIA FICTICIA" not in tela
    lista = c.get(LISTA)
    assert lista.status_code == 302 and lista.headers["Location"].endswith(NOVA)
    assert c.get(LISTA + f"/{alheia}").status_code == 403
    with casa["db"].connect() as con:
        propria = next(d for d in DP.listar(con) if d["beneficiario_nome"] == "PAPELARIA FICTICIA")
    assert c.get(LISTA + f"/{propria['id']}").status_code == 403


@pytest.mark.parametrize("url", SO_DO_TITULAR)
def test_as_outras_telas_recusam_quem_so_cadastra(cg_casa_logada, url):
    assert _como(cg_casa_logada, "carla", "CARLA EXEMPLO", "MANAGER").get(url).status_code == 403


def test_quem_so_cadastra_nao_age_sobre_despesa_nem_pela_ficha(cg_casa_logada):
    casa = cg_casa_logada
    alheia = _do_oficial(casa["db"])
    c = _como(casa, "carla", "CARLA EXEMPLO", "MANAGER")
    r = c.post(LISTA + f"/{alheia}/cancelar", data={"csrf_token": _token(c), "motivo": "tentativa de quem só cadastra"})
    assert r.status_code == 403
    with casa["db"].connect() as con:
        assert DP.despesa(con, alheia)["situacao"] == DP.AGUARDANDO


def test_a_recusa_nao_conta_o_nome_de_outra_pessoa(cg_casa_logada):
    casa = cg_casa_logada
    _do_oficial(casa["db"])
    c = _como(casa, "carla", "CARLA EXEMPLO", "USER")
    r = c.post(NOVA, data={
        "csrf_token": _token(c), "categoria": "MATERIAIS", "descricao": "Papel A4 para o balcão",
        "beneficiario_nome": "OUTRO FICTICIO", "beneficiario_documento": "00000000191", "valor": "10,00",
        "vencimento": "2026-11-10", "forma": DP.PIX_CHAVE, "codigo": "outro@example.com",
        "documento_especie": "Nota"}).get_data(as_text=True)
    assert "já está cadastrado para outro favorecido" in r and "PRESTADOR FICTICIO" not in r


def test_outro_admin_nao_e_o_titular(cg_casa_logada):
    casa = cg_casa_logada
    casa["db"].set_settings({"serventia_titular": "MARIO EXEMPLO DOS SANTOS"})
    alheia = _do_oficial(casa["db"])
    with casa["db"].transaction() as con:
        anexo = DP.guardar_anexo(con, alheia, nome_arquivo="folha.pdf", conteudo=b"%PDF",
                                 pasta=casa["dados"], usuario_id=None, agora="2026-10-28T09:00:00")
    assert casa["c"].get(LISTA).status_code == 200, "o titular entra"
    assert casa["c"].get("/administrativo/carne-leao").status_code == 200
    assert casa["c"].get(f"/arquivo/{anexo}").status_code == 200
    c = _como(casa, "analista", "ANALISTA EXEMPLO", "ADMIN")
    assert c.get(LISTA).status_code == 302
    assert c.get(LISTA + f"/{alheia}").status_code == 403
    assert c.get("/administrativo/carne-leao").status_code == 403
    assert c.get(f"/arquivo/{anexo}").status_code == 404, "nem pelo número na barra"
    assert c.get(NOVA).status_code == 200, "cadastrar continua de todos"


def test_sem_titular_entre_os_admins_nao_tranca_o_oficial(cg_casa_logada):
    casa = cg_casa_logada
    casa["db"].set_settings({"serventia_titular": "NOME ESCRITO DE OUTRO JEITO"})
    assert casa["c"].get(LISTA).status_code == 200


def test_o_menu_leva_quem_so_cadastra_ao_formulario(cg_casa_logada):
    c = _como(cg_casa_logada, "carla", "CARLA EXEMPLO", "USER")
    tela = c.get("/").get_data(as_text=True)
    assert NOVA in tela and 'href="/administrativo/despesas"' not in tela

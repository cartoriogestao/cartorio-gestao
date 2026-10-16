"""A consulta à base nacional do CCN — 15/10/2026.

Ordem do oficial: «crie a integracao do ccn para receber e consultar na base
nacional. tenho uma chave de exportacao do ccn».

Quem chama o CCN é a extensão, na aba do portal; aqui se guarda o resto: o
pedido e o código, a ponte (só desta máquina, e só com o código certo), a
ficha de outro CPF recusada, a ficha traduzida para o cartão, e — o que mais
importa — que só campo VAZIO do cartão se preenche.

Os formatos vêm do contrato «CCN 2.99.2 RTM», guardado em
`FONTES_EXTERNAS/enotariado/ccn_exportacao_2.99.2.json`. Nomes e CPFs são os
fictícios da casa.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ccn_consulta as CQ  # noqa: E402
from conftest import cg_login  # noqa: E402

AGORA = "2026-10-15T10:00:00"
SENHA = "Senha#12345"
CPF = "00000000191"
CONTRATO = RAIZ.parent.parent / "FONTES_EXTERNAS" / "enotariado" / "ccn_exportacao_2.99.2.json"

FICHA = {
    "id": "11111111-1111-1111-1111-111111111111", "cpf": CPF, "name": "MARIA EXEMPLO",
    "subscriptionName": "CARTORIO EXEMPLO", "notary": {"name": "1º TABELIONATO DE CIDADE EXEMPLO", "cns": 1},
    "dateCreated": "2024-02-01T09:00:00", "gender": "Female", "dateOfBirth": "1980-05-02T00:00:00",
    "email": "Maria@Exemplo.com", "profession": "lavradora", "civilStatus": "Casado",
    "spouseName": "Mario Exemplo", "maritalPropertySystem": "RegimeOfPartialCommunityProperty",
    "motherName": "Ana Exemplo", "fatherName": "Jose Exemplo", "documentType": "IdCard",
    "documentNumber": "123456", "documentIssuer": "ssp", "documentIssueDate": "2015-03-06T00:00:00",
    "documentIssuerState": "MA", "nationality": "Brazilian", "birthCity": "Cidade Exemplo",
    "birthState": "MA",
    "address": {"street": "Rua Grande", "number": "10", "neighbourhood": "Centro",
                "city": "Cidade Exemplo", "state": "MA", "zipCode": "65.936-000"},
    "phones": [{"type": "Home", "number": "(99) 3571-0000"},
               {"type": "Mobile", "number": "+55 99 98888-0000", "primaryMobilePhone": True}],
    "politicallyExposed": True, "investigatedOrAccusedOfTerrorism": False, "blocked": False,
    "files": [{"type": "Documento", "name": "rg.pdf", "contentType": "application/pdf"}],
    "fingerPrints": [{"type": "RightThumb"}],
}


def _cartao(con, **extra):
    cols = {"nome": "MARIA EXEMPLO", "nome_norm": "maria exemplo", "documento": CPF,
            "tipo_pessoa": "F", "ativo": 1, "abertura": "2026-10-01", "criado_em": AGORA,
            "pessoa_exposta": 0, "restricao_terrorismo": 0, "bloqueado": 0,
            "somente_autenticidade": 0, "origem": "MANUAL"}
    cols.update(extra)
    return con.execute(f"INSERT INTO nt_cartoes ({','.join(cols)}) VALUES "
                       f"({','.join('?' * len(cols))})", tuple(cols.values())).lastrowid


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ------------------------------------------------------------ o contrato

def test_os_campos_lidos_existem_no_contrato():
    """O módulo só lê campos que o contrato declara — nome inventado não chega."""
    # Relativo ao repositório; numa cópia de teste fora dele, a pasta das fontes
    # vem da variável CG_FONTES_EXTERNAS. Caminho de máquina não entra no código.
    fontes = os.environ.get("CG_FONTES_EXTERNAS")
    contrato = (Path(fontes) / "enotariado" / CONTRATO.name) if fontes else CONTRATO
    if not contrato.is_file():
        pytest.skip("o trecho do contrato não está nesta máquina")
    esquema = json.loads(contrato.read_text(encoding="utf-8"))["esquemas"]
    ficha = set(esquema["Export.ExportCivilianRecordModel"]["properties"])
    fonte = (RAIZ / "ccn_consulta.py").read_text(encoding="utf-8")
    usados = {a or b for a, b in re.findall(r'f\.get\("(\w+)"\)|f\["(\w+)"\]', fonte)}
    assert len(usados) > 20 and usados <= ficha, usados - ficha
    assert set(CQ.ESTADO_CIVIL) == set(esquema["EstadoCivil"]["enum"])
    assert set(CQ.REGIME) == set(esquema["MaritalPropertySystem"]["enum"])


# ------------------------------------------------------------ o pedido e o código

def test_pedido_codigo_e_cpf_invalido(con):
    with pytest.raises(CQ.ConsultaError, match="CPF"):
        CQ.pedir(con, "111.111.111-11", "PRODUCAO", usuario="T", agora=AGORA)
    cid = CQ.pedir(con, "000.000.001-91", "PRODUCAO", usuario="T", agora=AGORA)
    cod = CQ.codigo_da_consulta("segredo", cid)
    assert re.fullmatch(rf"C{cid}-[0-9A-F]{{10}}", cod) and CQ.e_codigo_de_consulta(cod)
    assert not CQ.e_codigo_de_consulta("7-ABCDEF0123")           # código de lote
    assert CQ.consulta_pelo_codigo(con, "segredo", cod)["cpf"] == CPF
    with pytest.raises(CQ.ConsultaError, match="não confere"):
        CQ.consulta_pelo_codigo(con, "outro", cod)


def test_ficha_de_outro_cpf_e_recusada_inteira(con):
    cid = CQ.pedir(con, CPF, "PRODUCAO", usuario="T", agora=AGORA)
    c = CQ.carregar(con, cid)
    with pytest.raises(CQ.ConsultaError, match="outro CPF"):
        CQ.registrar_resposta(con, c, {"achados": [{"id": "x", "cpf": "00000000272"}],
                                       "registros": []}, AGORA)
    assert CQ.carregar(con, cid)["situacao"] == "PEDIDA"


# ------------------------------------------------------------ a tradução

def test_a_ficha_vira_os_campos_do_cartao_nos_formatos_da_casa():
    k = CQ.campos_do_cartao(FICHA)
    assert k["nascimento"] == "1980-05-02" and k["sexo"] == "F"
    assert k["estado_civil"] == "Casado(a)" and k["nacionalidade"] == "BRASILEIRA"
    assert k["naturalidade"] == "CIDADE EXEMPLO/MA"
    assert (k["rg"], k["rg_orgao"], k["rg_uf"], k["rg_emissao"]) == ("123456", "SSP", "MA", "2015-03-06")
    assert k["cep"] == "65936000" and k["celular"] == "99988880000" and k["telefone"] == "9935710000"
    assert k["email"] == "maria@exemplo.com" and k["mae"] == "ANA EXEMPLO"


def test_os_alertas_aparecem_e_nao_viram_campo():
    tela = CQ.ficha_para_a_tela(FICHA)
    assert any("POLITICAMENTE EXPOSTA" in a for a in tela["alertas"])
    assert "pessoa_exposta" not in CQ.campos_do_cartao(FICHA)
    assert ("Regime de bens", "comunhão parcial de bens") in tela["linhas"]


# ------------------------------------------------------------ o cartão

def test_so_campo_vazio_se_preenche(con):
    cartao = _cartao(con, profissao="AGRICULTORA", mae="ANA EXEMPLO")
    cid = CQ.pedir(con, CPF, "PRODUCAO", usuario="T", agora=AGORA)
    CQ.registrar_resposta(con, CQ.carregar(con, cid), {"achados": [FICHA], "registros": [FICHA]}, AGORA)
    c = CQ.carregar(con, cid)
    assert c["situacao"] == "ENCONTRADA"
    p = CQ.proposta(con, c)
    preencher = {x["coluna"] for x in p["preencher"]}
    assert "nascimento" in preencher and "profissao" not in preencher and "mae" not in preencher
    assert [d["coluna"] for d in p["diferentes"]] == ["profissao"]
    r = CQ.aplicar(con, c, indice=0, usuario="CARLA EXEMPLO", agora=AGORA)
    linha = dict(con.execute("SELECT * FROM nt_cartoes WHERE id=?", (cartao,)).fetchone())
    assert linha["profissao"] == "AGRICULTORA"                  # o que a casa tinha, fica
    assert linha["nascimento"] == "1980-05-02" and linha["atualizado_por"] == "CARLA EXEMPLO"
    assert set(r["campos"]) == preencher
    with pytest.raises(CQ.ConsultaError, match="nada a completar"):
        CQ.aplicar(con, CQ.carregar(con, cid), indice=0, usuario="T", agora=AGORA)


def test_sem_cartao_nada_se_grava(con):
    cid = CQ.pedir(con, CPF, "PRODUCAO", usuario="T", agora=AGORA)
    CQ.registrar_resposta(con, CQ.carregar(con, cid), {"achados": [FICHA], "registros": [FICHA]}, AGORA)
    c = CQ.carregar(con, cid)
    assert "não há cartão" in CQ.proposta(con, c)["motivo"]
    with pytest.raises(CQ.ConsultaError, match="não há cartão"):
        CQ.aplicar(con, c, indice=0, usuario="T", agora=AGORA)


# ------------------------------------------------------------ a tela e a ponte

def test_tela_ponte_e_completar_o_cartao(con, cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("carla", "CARLA EXEMPLO", SENHA, "USER")
    _cartao(con)
    con.commit()
    c = app.test_client()
    cg_login(c, "carla", SENHA)
    html = c.get("/notas/ccn/consultas").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/notas/ccn/consultas", data={"cpf": "000.000.001-91", "ambiente": "PRODUCAO",
                                             "csrf_token": token})
    assert r.status_code == 302
    cid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    cod = CQ.codigo_da_consulta(app.secret_key, cid)
    assert cod in c.get(f"/notas/ccn/consultas/{cid}").get_data(as_text=True)

    extensao = app.test_client()                               # sem sessão, como a extensão
    pedido = extensao.get(f"/ccn/ponte/consulta?codigo={cod}").get_json()
    assert pedido["ok"] and pedido["cpf"] == CPF and pedido["host"] == "pessoas.e-notariado.org.br"
    assert extensao.get(f"/ccn/ponte/consulta?codigo={cod}",
                        environ_base={"REMOTE_ADDR": "192.168.0.50"}).status_code == 403
    volta = extensao.post("/ccn/ponte/resultado",
                          json={"codigo": cod, "achados": [FICHA], "registros": [FICHA]}).get_json()
    assert volta["ok"] and volta["situacao"] == "ENCONTRADA" and volta["fichas"] == 1

    html = c.get(f"/notas/ccn/consultas/{cid}").get_data(as_text=True)
    assert "POLITICAMENTE EXPOSTA" in html and "Completar o cartão" in html
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    c.post(f"/notas/ccn/consultas/{cid}/aplicar", data={"ficha": "0", "csrf_token": token})
    assert con.execute("SELECT nascimento FROM nt_cartoes WHERE documento=?", (CPF,)).fetchone()[0] \
        == "1980-05-02"

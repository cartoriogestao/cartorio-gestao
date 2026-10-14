"""O envio do cadastro ao CCN — 13/10/2026.

O formato do arquivo (XSD v4 do CNB) ainda não está na casa; estes testes
montam o lote com um formato de ensaio e guardam o resto do caminho: quem vai,
quem não vai e por quê, o código de envio, a ponte com a extensão e o
resultado do CCN chegando a cada cartão — inclusive que a mesma versão já
aceita não se manda de novo, e que cadastro mudado volta a ser pendente.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ccn_envio as CE  # noqa: E402
from conftest import cg_login  # noqa: E402

AGORA = "2026-10-13T10:00:00"
SENHA = "Senha#12345"


def _formato_de_ensaio(pessoas):
    return json.dumps([p["campos"] for p in pessoas], ensure_ascii=False).encode("utf-8")


def _cartao(con, nome, cpf, **extra):
    cols = {"nome": nome, "nome_norm": nome.lower(), "documento": cpf, "tipo_pessoa": "F",
            "ativo": 1, "abertura": "2026-10-01", "criado_em": AGORA, "pessoa_exposta": 0,
            "restricao_terrorismo": 0, "bloqueado": 0, "somente_autenticidade": 0,
            "origem": "MANUAL"}
    cols.update(extra)
    try:
        return con.execute(f"INSERT INTO nt_cartoes ({','.join(cols)}) VALUES "
                           f"({','.join('?' * len(cols))})", tuple(cols.values())).lastrowid
    except sqlite3.IntegrityError as e:
        pytest.fail(f"o cartão de ensaio não entrou: {e}")


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_o_cartao_vira_o_cadastro_do_ccn_e_diz_o_que_ficou_de_fora(con, tmp_path):
    cid = _cartao(con, "MARIA DAS DORES SILVA", "000.000.001-91", sexo="F",
                  estado_civil="Solteiro(a)", nacionalidade="BRASILEIRA",
                  celular="984383524", nascimento="1980-05-02", mae="ANA SILVA",
                  rg="123456", rg_orgao="SSP", rg_uf="ma")
    c = dict(con.execute("SELECT * FROM nt_cartoes WHERE id=?", (cid,)).fetchone())
    p = CE.pessoa_do_cartao(con, c, tmp_path)
    assert p["cpf"] == "00000000191"
    k = p["campos"]
    assert k["estadoCivil"] == "Solteiro" and k["nacionalidade"] == "BRASIL"
    assert k["documento"] == {"tipo": "RG", "docIdentidade": "123456",
                              "orgaoEmissor": "SSP", "ufOrgaoEmissor": "MA"}
    assert "celular" not in k                                     # sem DDD não vai
    assert any("DDD" in f for f in p["fora"])


def test_sem_cpf_valido_nao_entra(con, tmp_path):
    cid = _cartao(con, "JOAO", "111.111.111-11")
    c = dict(con.execute("SELECT * FROM nt_cartoes WHERE id=?", (cid,)).fetchone())
    with pytest.raises(CE.CcnError, match="CPF"):
        CE.pessoa_do_cartao(con, c, tmp_path)
    assert CE.cpf_valido("000.000.001-91") == "00000000191"
    assert CE.cpf_valido("52998224724") is None


def test_lote_resultado_e_a_versao_aceita_nao_volta(con, cg_casa):
    a = _cartao(con, "ANA PRIMEIRA", "00000000191")
    b = _cartao(con, "BRUNO SEGUNDO", "00000000272")
    con.commit()
    r = CE.gerar_lote(con, Path(cg_casa["dados"]), ambiente="HOMOLOGACAO", usuario="T",
                      agora=AGORA, montar=_formato_de_ensaio)
    con.commit()
    assert r["quantidade"] == 2
    lote = dict(con.execute("SELECT * FROM nt_ccn_lotes WHERE id=?", (r["lote_id"],)).fetchone())
    assert Path(lote["caminho"]).is_file() and lote["situacao"] == "GERADO"
    # lote em aberto: a mesma gente não entra noutro lote
    with pytest.raises(CE.CcnError, match="nenhum"):
        CE.gerar_lote(con, Path(cg_casa["dados"]), ambiente="HOMOLOGACAO", usuario="T",
                      agora=AGORA, montar=_formato_de_ensaio)
    # o CCN terminou com um erro na posição do BRUNO
    pos_b = con.execute("SELECT posicao FROM nt_ccn_itens WHERE cartao_id=?", (b,)).fetchone()[0]
    v = CE.registrar_resultado(con, lote, {
        "upload": {"id": "u1"},
        "import": {"id": "i1", "status": "CompletedWithErrors", "processedRecords": 2,
                   "failedRecords": 1},
        "erros": [{"position": pos_b, "identifier": "00000000272",
                   "errors": [{"message": "nome da mãe obrigatório"}]}]}, AGORA)
    con.commit()
    assert (v["aceitos"], v["recusados"]) == (1, 1)
    itens = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT cartao_id, situacao, erro FROM nt_ccn_itens WHERE lote_id=?", (lote["id"],))}
    assert itens[a][0] == "ACEITO" and itens[b] == ("RECUSADO", "nome da mãe obrigatório")
    # o aceito não volta; o recusado volta; cadastro mudado volta
    r2 = CE.gerar_lote(con, Path(cg_casa["dados"]), ambiente="HOMOLOGACAO", usuario="T",
                       agora=AGORA, montar=_formato_de_ensaio)
    con.commit()
    ids = {x[0] for x in con.execute("SELECT cartao_id FROM nt_ccn_itens WHERE lote_id=?",
                                     (r2["lote_id"],))}
    assert ids == {b}
    con.execute("UPDATE nt_cartoes SET profissao='LAVRADORA' WHERE id=?", (a,))
    CE.descartar(con, r2["lote_id"], "ensaio de descarte do lote", AGORA)
    r3 = CE.gerar_lote(con, Path(cg_casa["dados"]), ambiente="HOMOLOGACAO", usuario="T",
                       agora=AGORA, montar=_formato_de_ensaio)
    ids = {x[0] for x in con.execute("SELECT cartao_id FROM nt_ccn_itens WHERE lote_id=?",
                                     (r3["lote_id"],))}
    assert ids == {a, b}


def test_o_teto_de_tamanho_corta_o_lote(con, cg_casa):
    for i, cpf in enumerate(("00000000191", "00000000272", "00000000353")):
        _cartao(con, f"PESSOA {i}", cpf)
    r = CE.gerar_lote(con, Path(cg_casa["dados"]), ambiente="HOMOLOGACAO", usuario="T",
                      agora=AGORA, montar=lambda ps: b"x" * (100 * len(ps)), limite_bytes=250)
    assert r["quantidade"] == 2 and r["ficaram_para_o_proximo"] == 1


def test_o_codigo_abre_so_aquele_lote():
    cod = CE.codigo_do_lote("segredo", 7)
    assert re.fullmatch(r"7-[0-9A-F]{10}", cod)
    assert cod != CE.codigo_do_lote("segredo", 8)
    assert cod != CE.codigo_do_lote("outro", 7)


def test_a_ponte_entrega_o_lote_e_recebe_o_resultado(con, cg_casa):
    app = cg_casa["app"]
    # Instalação sem usuário manda tudo para /setup; a de verdade tem usuário.
    cg_casa["db"].create_user("oficial", "OFICIAL DE ENSAIO", SENHA, "ADMIN")
    _cartao(con, "ANA PRIMEIRA", "00000000191")
    con.commit()
    r = CE.gerar_lote(con, Path(cg_casa["dados"]), ambiente="HOMOLOGACAO", usuario="T",
                      agora=AGORA, montar=_formato_de_ensaio)
    con.commit()
    cod = CE.codigo_do_lote(app.secret_key, r["lote_id"])
    c = app.test_client()                                  # sem sessão, como a extensão
    lote = c.get(f"/ccn/ponte/lote?codigo={cod}").get_json()
    assert lote["ok"] and lote["host"] == "pessoas-hml.e-notariado.org.br"
    assert lote["conteudo_b64"] and lote["tipo"] == "CcnPessoaFisica"
    assert c.get("/ccn/ponte/lote?codigo=1-0000000000").status_code == 400
    # de outra máquina, nada
    assert c.get(f"/ccn/ponte/lote?codigo={cod}",
                 environ_base={"REMOTE_ADDR": "192.168.0.50"}).status_code == 403
    volta = c.post("/ccn/ponte/resultado", json={
        "codigo": cod, "upload": {"id": "u"},
        "import": {"id": "i", "status": "Successful", "processedRecords": 1,
                   "failedRecords": 0}}).get_json()
    assert volta["ok"] and volta["aceitos"] == 1 and volta["situacao"] == "CONCLUIDO"
    assert c.post("/ccn/ponte/resultado", json={"codigo": "9-AAAAAAAAAA"}).status_code == 400


def test_a_tela_abre_e_oferece_o_lote_quando_o_xsd_esta_na_casa(cg_casa, monkeypatch):
    import ccn_xml
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    cg_login(c, "tabeliao", SENHA)
    html = c.get("/notas/ccn").get_data(as_text=True)
    assert "Cadastro no CCN" in html and "Gerar lote" in html
    # sem o XSD, a tela diz por quê e não oferece o botão
    monkeypatch.setattr(ccn_xml, "situacao_do_formato",
                        lambda: {"pronto": False, "motivo": "o XSD v4 do CNB não está"})
    html = c.get("/notas/ccn").get_data(as_text=True)
    assert "XSD v4" in html and "Gerar lote" not in html

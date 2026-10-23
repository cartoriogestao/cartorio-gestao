# -*- coding: utf-8 -*-
"""Correcao direta dos campos da ficha do assento (acervo / EOFICIO)."""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                          # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-09-08T12:00:00"
EXTENSO = "oito dias do mes de setembro do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFICIO UNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabeliao e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
SENHA = "Senha#12345"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


def eoficio(con, nome="ELDO DA SILVA", *, chave="ACERVO-1222", **kw):
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome=nome, sv=SV, agora=AGORA,
        data_extenso=EXTENSO, data_fato=kw.pop("data_fato", "1990-01-15"),
        origem="EOFICIO", origem_chave=chave,
        dados={"sexo": "M"},
        teor=kw.pop("teor", None),
        usuario=kw.pop("usuario", "carga"),
        pessoas=kw.pop("pessoas", [
            {"papel": "REGISTRADO", "nome": nome, "sexo": "M"},
            {"papel": "MAE", "nome": "MARIA DA SILVA"},
            {"papel": "PAI", "nome": "JOSE DA SILVA"},
        ]),
        termo_dados=kw.pop("termo_dados",
                           {"local_fato_nome": "Hospital Municipal"}),
        **kw,
    )
    aid = r["assento_id"]
    con.execute(
        "UPDATE rc_assentos SET numero=?, livro_volume=? WHERE id=?",
        (1222, "A-9", aid))
    return r


def test_corrigir_nome_filiacao_teor_folha_de_acervo():
    con = banco()
    r = eoficio(con)
    aid = r["assento_id"]
    con.execute(
        "UPDATE rc_atos SET folha=?, numero_ordem=? "
        "WHERE assento_id=? AND tipo='REGISTRO'",
        (55, 1222, aid))
    con.commit()

    out = RC.corrigir_informacoes(
        con, aid,
        motivo="Tipografia na carga do acervo — conferido no livro",
        agora=AGORA, usuario="Escrevente Ana",
        nome="ELDO DE SOUSA SILVA",
        numero=1222,
        folha=56,
        pessoas=[
            {"papel": "MAE", "nome": "MARIA DE SOUSA SILVA",
             "naturalidade_cidade": "Cidade Exemplo"},
        ],
        teor="Ao aos quinze dias de janeiro de mil novecentos e noventa...",
    )
    con.commit()

    a = RC.assento(con, aid)
    assert a["nome"] == "ELDO DE SOUSA SILVA"
    assert a["teor"].startswith("Ao aos quinze")
    assert a["criado_por"] == "carga"
    mae = con.execute(
        "SELECT nome, naturalidade_cidade FROM rc_pessoas "
        "WHERE assento_id=? AND papel='MAE'", (aid,)).fetchone()
    assert mae["nome"] == "MARIA DE SOUSA SILVA"
    assert mae["naturalidade_cidade"] == "Cidade Exemplo"
    ato = con.execute(
        "SELECT folha, numero_ordem, teor FROM rc_atos "
        "WHERE assento_id=? AND tipo='REGISTRO'", (aid,)).fetchone()
    assert ato["folha"] == 56
    assert ato["numero_ordem"] == 1222
    assert "quinze" in (ato["teor"] or "")
    assert "nome" in out["mudancas"]
    assert out["usuario"] == "Escrevente Ana"
    assert out["origem"] == "EOFICIO"


def test_corrigir_exige_motivo():
    con = banco()
    r = eoficio(con, chave="ACERVO-1223")
    with pytest.raises(RC.RcError, match="motivo"):
        RC.corrigir_informacoes(
            con, r["assento_id"], motivo="curto", agora=AGORA,
            nome="OUTRO NOME")


def test_corrigir_recusa_assento_inativo():
    con = banco()
    r = eoficio(con, chave="ACERVO-X")
    con.execute("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=?",
                (r["assento_id"],))
    with pytest.raises(RC.RcError, match="ativo"):
        RC.corrigir_informacoes(
            con, r["assento_id"],
            motivo="Tentativa em assento cancelado xyz",
            agora=AGORA, nome="X")


def test_corrigir_sem_mudanca_recusa():
    con = banco()
    r = eoficio(con, nome="MESMO", chave="ACERVO-Y")
    with pytest.raises(RC.RcError, match="Nada foi alterado"):
        RC.corrigir_informacoes(
            con, r["assento_id"],
            motivo="Nada mudou nesta tentativa de gravar",
            agora=AGORA, nome="MESMO")


def test_termo_de_outra_especie_nao_limpa():
    con = banco()
    r = eoficio(con, chave="ACERVO-Z")
    aid = r["assento_id"]
    con.execute("UPDATE rc_assentos SET causa_morte=? WHERE id=?",
                ("N/A-nao-deveria", aid))
    con.commit()
    RC.corrigir_informacoes(
        con, aid,
        motivo="Corrigindo so o local do fato no nascimento",
        agora=AGORA, usuario="Escrevente",
        termo={"local_fato_nome": "UBS Centro", "causa_morte": ""},
    )
    con.commit()
    a = RC.assento(con, aid)
    assert a["local_fato_nome"] == "UBS Centro"
    assert a["causa_morte"] == "N/A-nao-deveria"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "csrf ausente"
    return achado.group(1)


def test_rota_editar_abre_e_grava(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco_path = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco_path).create_user(
        "tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    client = app.test_client()
    client.post("/login", data={
        "username": "tabeliao", "password": SENHA,
        "csrf_token": _token(client.get("/login").get_data(as_text=True)),
    }, follow_redirects=True)

    con = sqlite3.connect(banco_path)
    con.row_factory = sqlite3.Row
    with con:
        r = RC.lavrar_assento(
            con, especie="NASCIMENTO", nome="DAIANE SOUSA", sv=SV,
            agora=AGORA, data_extenso=EXTENSO, data_fato="1995-03-10",
            origem="EOFICIO", origem_chave="ACERVO-1223",
            dados={"sexo": "F"},
            pessoas=[
                {"papel": "REGISTRADO", "nome": "DAIANE SOUSA", "sexo": "F"},
                {"papel": "MAE", "nome": "ANA SOUSA"},
                {"papel": "PAI", "nome": "IGNORADO"},
            ],
            termo_dados={"local_fato_nome": "Maternidade"},
            usuario="carga",
        )
        aid = r["assento_id"]
        con.execute(
            "UPDATE rc_assentos SET numero=?, livro_volume=? WHERE id=?",
            (1223, "A-10", aid))
    con.close()

    get = client.get(f"/rcpn/{aid}/editar")
    assert get.status_code == 200
    body = get.get_data(as_text=True)
    assert "Motivo" in body
    assert "DAIANE SOUSA" in body
    assert "Editar" in body

    post = client.post(f"/rcpn/{aid}/editar", data={
        "csrf_token": _token(body),
        "motivo": "Correcao conferida no livro de papel do acervo",
        "nome": "FELICIO DE SOUSA SANTOS",
        "data_fato": "1995-03-10",
        "livro_volume": "A-10",
        "numero": "1223",
        "folha": "88",
        "sexo": "F",
        "local_fato_nome": "Maternidade Municipal",
        "teor": "Nasceu FELICIO DE SOUSA SANTOS...",
        "pessoa_nome": "FELICIO DE SOUSA SANTOS",
        "filiacao1_nome": "ANA DE SOUSA SANTOS",
        "filiacao2_nome": "IGNORADO",
    }, follow_redirects=True)
    assert post.status_code == 200
    html = post.get_data(as_text=True)
    assert "FELICIO DE SOUSA SANTOS" in html

    con = sqlite3.connect(banco_path)
    con.row_factory = sqlite3.Row
    a = con.execute("SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone()
    assert a["nome"] == "FELICIO DE SOUSA SANTOS"
    assert a["local_fato_nome"] == "Maternidade Municipal"
    assert a["criado_por"] == "carga"
    mae = con.execute(
        "SELECT nome FROM rc_pessoas WHERE assento_id=? AND papel='MAE'",
        (aid,)).fetchone()
    assert mae["nome"] == "ANA DE SOUSA SANTOS"
    ato = con.execute(
        "SELECT folha FROM rc_atos WHERE assento_id=? AND tipo='REGISTRO'",
        (aid,)).fetchone()
    assert ato["folha"] == 88
    con.close()


def test_ficha_tem_botao_editar():
    tpl = (RAIZ / "templates" / "atrib_rcpn_ficha.html").read_text(
        encoding="utf-8")
    assert "rcpn_assento_editar" in tpl
    assert "Alterar livro / termo / folha" in tpl


def test_rota_editar_grava_onde_nasceu(tmp_path):
    """06/10/2026: o SIRC recusa o nascimento sem o local, e a ficha não
    tinha onde informá-lo depois de lavrado. Só o local mudando também
    grava — «Nada foi alterado» é dos outros campos."""
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco_path = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco_path).create_user(
        "tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    client = app.test_client()
    client.post("/login", data={
        "username": "tabeliao", "password": SENHA,
        "csrf_token": _token(client.get("/login").get_data(as_text=True)),
    }, follow_redirects=True)
    con = sqlite3.connect(banco_path)
    con.row_factory = sqlite3.Row
    with con:
        r = RC.lavrar_assento(
            con, especie="NASCIMENTO", nome="MIGUEL TESTE", sv=SV,
            agora=AGORA, data_extenso=EXTENSO, data_fato="2026-09-14",
            origem="EOFICIO", origem_chave="ACERVO-LOCAL-1",
            dados={"sexo": "M"},
            pessoas=[
                {"papel": "REGISTRADO", "nome": "MIGUEL TESTE", "sexo": "M"},
                {"papel": "MAE", "nome": "MAE TESTE"},
                {"papel": "PAI", "nome": "PAI TESTE"},
            ],
            termo_dados={"local_fato_nome": "Maternidade"},
            usuario="balcao",
        )
        aid = r["assento_id"]
    con.close()

    body = client.get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    assert 'name="ibge_local"' in body
    dados_form = {
        "csrf_token": _token(body),
        "motivo": "Local do nascimento conferido na DNV - hospital",
        "nome": "MIGUEL TESTE NOVO", "data_fato": "2026-09-14", "sexo": "M",
        "local_fato_nome": "Maternidade", "ibge_local": "1",
    }
    client.post(f"/rcpn/{aid}/editar", data=dados_form, follow_redirects=True)

    def local():
        c = sqlite3.connect(banco_path)
        v = c.execute("SELECT ibge_local_nascimento FROM rc_assentos "
                      "WHERE id=?", (aid,)).fetchone()[0]
        c.close()
        return v

    assert local() == 1
    # de novo, mudando SÓ o local
    body = client.get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    dados_form["csrf_token"] = _token(body)
    dados_form["ibge_local"] = "3"
    html = client.post(f"/rcpn/{aid}/editar", data=dados_form,
                       follow_redirects=True).get_data(as_text=True)
    assert local() == 3
    assert "local do nascimento" in html


def test_rota_editar_obito_grava_as_quatro_marcas(tmp_path):
    """Relato #131 (14/10/2026): o óbito já lavrado não tinha onde dizer se
    deixou bens, e a carga da CRC o recusa sem isso. As quatro marcas agora
    estão na tela de corrigir; mudar SÓ uma delas também grava, e deixar em
    branco não apaga resposta já dada."""
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco_path = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco_path).create_user(
        "tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    client = app.test_client()
    client.post("/login", data={
        "username": "tabeliao", "password": SENHA,
        "csrf_token": _token(client.get("/login").get_data(as_text=True)),
    }, follow_redirects=True)
    con = sqlite3.connect(banco_path)
    con.row_factory = sqlite3.Row
    with con:
        r = RC.lavrar_assento(
            con, especie="OBITO", nome="JOAO FALECIDO TESTE", sv=SV,
            agora=AGORA, data_extenso=EXTENSO, data_fato="2026-09-01",
            origem="EOFICIO", origem_chave="ACERVO-OBITO-131",
            dados={"sexo": "M"},
            pessoas=[{"papel": "FALECIDO", "nome": "JOAO FALECIDO TESTE",
                      "sexo": "M"}],
            usuario="carga",
        )
        aid = r["assento_id"]
        con.execute("UPDATE rc_assentos SET obito_eleitor='NAO' WHERE id=?",
                    (aid,))
    con.close()

    body = client.get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    assert 'name="obito_possui_bens"' in body
    assert 'name="obito_eleitor"' in body
    client.post(f"/rcpn/{aid}/editar", data={
        "csrf_token": _token(body),
        "motivo": "Declarante confirmou que deixou bens",
        "nome": "JOAO FALECIDO TESTE", "data_fato": "2026-09-01",
        "sexo": "M",
        "obito_possui_bens": "SIM",
        "obito_eleitor": "",          # em branco: não apaga o «não» gravado
    }, follow_redirects=True)

    c = sqlite3.connect(banco_path)
    bens, eleitor = c.execute(
        "SELECT obito_possui_bens, obito_eleitor FROM rc_assentos WHERE id=?",
        (aid,)).fetchone()
    c.close()
    assert bens == "SIM"
    assert eleitor == "NAO"

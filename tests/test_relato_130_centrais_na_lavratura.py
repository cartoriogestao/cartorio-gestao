"""Relato #130 — não lavrar o que a CRC e o SIRC recusariam depois.

    «não deixar lavrar registro de nascimento, casamento e óbitos, e demais
     rcpn, se todos os campos para envio da CRC e SIRC não estejam
     preenchidos» — o oficial, 14/10/2026 (3.6.291)

O QUE ESTES TESTES GUARDAM
    **A régua é a da carga, e não uma terceira lista**: a recusa cita a frase
    de `crc_carga.o_que_falta` / `sirc_remessa.o_que_falta`, e diz para qual
    central. **Nada fica no livro**: nem assento, nem número, nem folha.
    **Completo, lavra.** **A carga do acervo não é recusada.** **A saída de
    emergência do oficial continua valendo, e a falta fica gravada.** **A tela
    de editar AVISA o que falta, sem travar a correção.** **O formulário
    recusado volta com o que foi digitado.**

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                                  # noqa: E402
import rc_centrais_na_lavratura as CENT                  # noqa: E402
from nucleo_schema import init_nucleo_schema             # noqa: E402
from rc_schema import init_rc_schema                     # noqa: E402

AGORA = "2026-10-14T10:00:00"
EXTENSO = "catorze dias do mês de outubro do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
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


def nascimento(con, *, local_ibge=1, **kw):
    ibge = {"local_nascimento": local_ibge} if local_ibge is not None else {}
    return RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOÃO EXEMPLO", sv=SV, agora=AGORA,
        data_extenso=EXTENSO, data_fato="2026-10-10", dados={"sexo": "M"},
        termo_dados={"local_fato_nome": "Hospital Municipal"}, ibge=ibge,
        pessoas=[{"papel": "REGISTRADO", "nome": "JOÃO EXEMPLO", "sexo": "M"},
                 {"papel": "MAE", "nome": "MARIA EXEMPLO"},
                 {"papel": "PAI", "nome": "IGNORADO"},
                 {"papel": "DECLARANTE", "nome": "MARIA EXEMPLO"}],
        **kw)


def obito(con, *, bens="NAO", **kw):
    return RC.lavrar_assento(
        con, especie="OBITO", nome="ANTONIO EXEMPLO", sv=SV, agora=AGORA,
        data_extenso=EXTENSO, data_fato="2026-10-12",
        termo_dados={"local_fato_nome": "Hospital Municipal"},
        ibge={"numero_do": "98765"},
        marcas_do_obito=({"obito_possui_bens": bens} if bens else None),
        pessoas=[{"papel": "FALECIDO", "nome": "ANTONIO EXEMPLO", "sexo": "M"},
                 {"papel": "MAE", "nome": "IGNORADO"},
                 {"papel": "PAI", "nome": "IGNORADO"},
                 {"papel": "DECLARANTE", "nome": "PEDRO EXEMPLO"}],
        **kw)


def _conta(con, tabela):
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


# ------------------------------------------------------- (a) a recusa

def test_nascimento_sem_onde_nasceu_e_recusado_e_cita_o_campo_e_o_sirc():
    con = banco()
    con.execute("SAVEPOINT x")
    with pytest.raises(CENT.FaltaParaAsCentraisError) as erro:
        nascimento(con, local_ibge=None)
    texto = str(erro.value)
    assert "o local do nascimento" in texto
    assert "SIRC" in texto
    assert "Nada foi gravado" in texto
    # é a frase da RÉGUA DA CARGA, e não uma segunda lista
    import sirc_remessa as SIRCM
    assert "o SIRC recusa o registro sem ele" in texto
    assert SIRCM.o_que_falta.__doc__
    # é ConferenciaError e ValueError: a rota devolve a conferência
    assert isinstance(erro.value, RC.ConferenciaError)
    assert isinstance(erro.value, ValueError)
    codigos = {p["codigo"] for p in erro.value.problemas}
    assert "FALTA_PARA_O_SIRC" in codigos


def test_obito_sem_deixou_bens_e_recusado_e_cita_o_campo_e_a_crc():
    con = banco()
    with pytest.raises(CENT.FaltaParaAsCentraisError) as erro:
        obito(con, bens=None)
    texto = str(erro.value)
    assert "possuía bens" in texto
    assert "CRC" in texto


def test_a_recusa_desfaz_tudo_e_nao_consome_numero():
    con = banco()
    con.execute("SAVEPOINT x")
    with pytest.raises(CENT.FaltaParaAsCentraisError):
        nascimento(con, local_ibge=None)
    con.execute("ROLLBACK TO x")
    con.execute("RELEASE x")
    assert _conta(con, "rc_assentos") == 0
    assert _conta(con, "rc_atos") == 0
    assert _conta(con, "rc_pessoas") == 0
    # completo, lavra — e com o PRIMEIRO número: a recusa não gastou nenhum
    r = nascimento(con)
    assert r["numero_ordem"] == 1


def test_depois_da_recusa_desfeita_a_lavratura_seguinte_grava_com_a_trava_do_banco():
    """LX01, 19/10/2026 — o ROLLBACK TO solta, no PostgreSQL, a trava de
    transação pega depois do savepoint, e a ponte seguia achando que a tinha:
    a lavratura de depois da recusa gravaria sem a trava única do banco, e
    duas lavraturas ao mesmo tempo poderiam tirar o mesmo número."""
    con = banco()
    con.commit()                  # a trava da criação do banco não conta
    con.execute("SAVEPOINT x")
    with pytest.raises(CENT.FaltaParaAsCentraisError):
        nascimento(con, local_ibge=None)
    con.execute("ROLLBACK TO x")
    con.execute("RELEASE x")
    nascimento(con)
    # a chave de 64 bits aparece no pg_locks partida em duas metades de 32
    travas = con.execute(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
        "AND pid = pg_backend_pid() AND classid::bigint = ? AND objid::bigint = ?",
        (con._chave_trava >> 32, con._chave_trava & 0xFFFFFFFF)).fetchone()[0]
    assert travas == 1


def test_savepoint_que_nao_existe_da_erro_e_o_que_ja_se_gravou_fica():
    """LX01, 19/10/2026 — o savepoint de quem chama agora vai ao PostgreSQL por
    fora da proteção da ponte. O RELEASE e o ROLLBACK TO de nome errado têm de
    continuar como no SQLite: dão erro, e a transação segue com o que já
    gravou, em vez de ficar condenada até o fim."""
    con = banco()
    nascimento(con)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("RELEASE ponto_que_nao_existe")
    with pytest.raises(sqlite3.OperationalError):
        con.execute("ROLLBACK TO ponto_que_nao_existe")
    con.commit()
    assert _conta(con, "rc_assentos") == 1


def test_o_texto_diz_cada_campo_e_para_qual_central():
    faltas = [{"central": "CRC", "falta": "o sexo do registrado"},
              {"central": "SIRC", "falta": "o local do nascimento"}]
    texto = CENT.mensagem_de_recusa(faltas)
    assert "para a CRC Nacional falta: o sexo do registrado" in texto
    assert "para o SIRC (INSS) falta: o local do nascimento" in texto


def test_a_regua_e_a_da_carga_e_nao_uma_lista_propria():
    """Se alguém escrever aqui uma lista de campos, ela diverge da carga no
    primeiro conserto — o módulo só pode CHAMAR as duas réguas."""
    src = (RAIZ / "rc_centrais_na_lavratura.py").read_text(encoding="utf-8")
    assert "CRCM.o_que_falta(" in src
    assert "SIRCM.o_que_falta(" in src
    rc = (RAIZ / "rc_assento.py").read_text(encoding="utf-8")
    assert "CENT.o_que_falta(con, assento_id, para_lavratura=True)" in rc


# ------------------------------------------------------- (b) completo lavra

def test_nascimento_completo_lavra():
    con = banco()
    r = nascimento(con)
    assert r["assento_id"] and r["matricula"]
    assert CENT.o_que_falta(con, r["assento_id"], para_lavratura=True) == []


def test_obito_completo_lavra_e_grava_a_resposta():
    con = banco()
    r = obito(con, bens="NAO")
    v = con.execute("SELECT obito_possui_bens FROM rc_assentos WHERE id=?",
                    (r["assento_id"],)).fetchone()[0]
    assert v == "NAO"


def test_casamento_completo_lavra():
    con = banco()
    r = RC.lavrar_assento(
        con, especie="CASAMENTO", nome="JOAO E MARIA", sv=SV, agora=AGORA,
        data_extenso=EXTENSO, data_fato="2026-10-10",
        regime_bens="COMUNHAO_PARCIAL",
        pessoas=[{"papel": "NUBENTE1", "nome": "JOAO"},
                 {"papel": "NUBENTE2", "nome": "MARIA"},
                 {"papel": "MAE_NUBENTE1", "nome": "ANA"},
                 {"papel": "PAI_NUBENTE1", "nome": "IGNORADO"},
                 {"papel": "MAE_NUBENTE2", "nome": "RITA"},
                 {"papel": "PAI_NUBENTE2", "nome": "IGNORADO"},
                 {"papel": "TESTEMUNHA", "nome": "CICLANO"}])
    assert r["assento_id"]


def test_especie_sem_carga_nas_centrais_fica_como_estava():
    """O Livro E, os proclamas e «outro» não têm carga na CRC nem no SIRC."""
    con = banco()
    r = RC.lavrar_assento(con, especie="OUTRO", nome="ALGUÉM", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO)
    assert r["assento_id"]
    assert CENT.o_que_falta(con, r["assento_id"], para_lavratura=True) == []


# ------------------------------------------------- a saída de emergência

def test_o_oficial_forca_com_motivo_e_a_falta_fica_gravada():
    con = banco()
    r = obito(con, bens=None, usuario="MARIO EXEMPLO DOS SANTOS",
              forcar_motivo="declarante não sabe se o falecido deixou bens; "
                            "sepultamento hoje")
    assert r["lavratura_forcada"]
    travas = json.loads(con.execute(
        "SELECT travas_json FROM rc_lavraturas_forcadas").fetchone()[0])
    assert "FALTA_PARA_A_CRC" in {p["codigo"] for p in travas}


def test_sem_motivo_o_forcar_continua_recusado():
    con = banco()
    with pytest.raises(CENT.FaltaParaAsCentraisError, match="15 letras"):
        obito(con, bens=None, usuario="MARIO", forcar_motivo="urgente")


# ---------------------------------------------------- (c) o acervo passa

@pytest.mark.parametrize("origem", ["EOFICIO", "IMPORTACAO", "ARQUIVO", "ACERVO"])
def test_carga_do_acervo_nao_e_recusada(origem):
    con = banco()
    r = RC.lavrar_assento(
        con, especie="OBITO", nome="FULANO ANTIGO", sv=SV, agora=AGORA,
        data_extenso=EXTENSO, origem=origem, origem_chave=f"{origem}:1")
    assert r["assento_id"]
    # e o que falta continua MEDIDO — é o aviso da tela de editar
    faltas = CENT.o_que_falta(con, r["assento_id"])
    assert any(f["central"] == "CRC" and "possuía bens" in f["falta"]
               for f in faltas)


def test_o_sirc_nao_e_cobrado_de_quem_nunca_vai_ao_sirc():
    """O acervo do E-Ofício não vai à remessa do SIRC: avisar dele seria o
    alarme que soa sempre. A carga do acervo em .docx (IMPORTACAO) vai."""
    con = banco()
    for origem in ("EOFICIO", "IMPORTACAO"):
        RC.lavrar_assento(
            con, especie="NASCIMENTO", nome=f"ANTIGO {origem}", sv=SV,
            agora=AGORA, data_extenso=EXTENSO, origem=origem,
            origem_chave=f"{origem}:9", dados={"sexo": "M"},
            pessoas=[{"papel": "REGISTRADO", "nome": f"ANTIGO {origem}",
                      "sexo": "M"}])
    ids = dict(con.execute("SELECT origem, id FROM rc_assentos").fetchall())
    assert not any(f["central"] == "SIRC"
                   for f in CENT.o_que_falta(con, ids["EOFICIO"]))
    assert any(f["central"] == "SIRC"
               for f in CENT.o_que_falta(con, ids["IMPORTACAO"]))


# ------------------------------------------------- (d) a tela de editar

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "csrf ausente"
    return achado.group(1)


def test_a_tela_de_editar_avisa_o_que_falta_e_nao_trava(tmp_path):
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
        aid = RC.lavrar_assento(
            con, especie="OBITO", nome="JOSE ANTIGO TESTE", sv=SV,
            agora=AGORA, data_extenso=EXTENSO, data_fato="2026-09-01",
            origem="EOFICIO", origem_chave="ACERVO-130", dados={"sexo": "M"},
            pessoas=[{"papel": "FALECIDO", "nome": "JOSE ANTIGO TESTE",
                      "sexo": "M"}],
            usuario="carga")["assento_id"]
    con.close()

    body = client.get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    assert 'id="faltas-centrais"' in body
    aviso = body[body.index('id="faltas-centrais"'):]
    aviso = aviso[:aviso.index("</div>")]
    assert "a CRC Nacional" in aviso and "possuía bens" in aviso
    assert "SIRC" not in aviso          # o acervo do E-Ofício não vai ao SIRC

    # a correção grava mesmo com o aviso — e, respondida a pergunta, ele some
    client.post(f"/rcpn/{aid}/editar", data={
        "csrf_token": _token(body),
        "motivo": "Declarante confirmou que não deixou bens",
        "nome": "JOSE ANTIGO TESTE", "data_fato": "2026-09-01", "sexo": "M",
        "obito_possui_bens": "NAO",
    }, follow_redirects=True)
    c = sqlite3.connect(banco_path)
    assert c.execute("SELECT obito_possui_bens FROM rc_assentos WHERE id=?",
                     (aid,)).fetchone()[0] == "NAO"
    c.close()
    body = client.get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    assert "possuía bens" not in body


# ------------------------------- o formulário recusado volta com o digitado

from test_testemunha_fantasma_20261009 import (           # noqa: E402,F401
    FOLHAS, _como_o_navegador, _rascunho_nascimento, casa)
from test_fila_e_arrumar_rcpn import _abrir_e_conferir, _quantos  # noqa: E402


def test_a_rota_recusa_devolve_o_formulario_e_nao_grava(casa):
    dados = _rascunho_nascimento()
    dados["ibge_local"] = ""                          # «onde nasceu» em branco
    slug, conf = _abrir_e_conferir(casa, dados)
    antes = _quantos(casa)
    envio = _como_o_navegador(conf, ("acao", "lavrar"),
                              folha_seguranca=FOLHAS[0])
    r = casa["c"].post(f"/rcpn/novo/{slug}", data=envio,
                       follow_redirects=True).get_data(as_text=True)
    assert _quantos(casa) == antes                    # nada no livro
    assert "Para o SIRC (INSS)" in r and "o local do nascimento" in r
    assert "campo(s) que a CRC e o SIRC exigem" in r
    # o que foi digitado volta: «Voltar e editar» leva tudo de novo
    volta = _como_o_navegador(r, ("acao", "voltar_editar"))
    assert volta["pessoa_nome"] == dados["pessoa_nome"]
    assert volta["filiacao1_nome"] == dados["filiacao1_nome"]
    # a folha de segurança não foi gasta
    con = sqlite3.connect(casa["banco"])
    situacao = con.execute("SELECT situacao FROM pp_folhas WHERE codigo=?",
                           (FOLHAS[0],)).fetchone()[0]
    con.close()
    assert situacao == "EM BRANCO"

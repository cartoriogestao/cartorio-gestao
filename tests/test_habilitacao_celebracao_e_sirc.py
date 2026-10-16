"""O que o ensaio da habilitação 2/2026 (vinda da produção) achou — 08/10/2026.

    1. A celebração foi amarrada a um NASCIMENTO de 1999 (assento id 113),
       porque o balcão digitou o nº de ordem do casamento onde o campo grava o
       código interno — e o selo da habilitação foi espelhado naquele registro.
    2. O SIRC não levava o regime de bens de casamento nenhum: a consulta dos
       pendentes não trazia `regime_bens`, e os testes antigos montavam o
       registro com uma consulta própria, que tinha a coluna.
    3. O SIRC mandava o casamento com celebração depois do registro, que a CRC
       já retinha.
    4. A certidão de habilitação expedida com o prazo correndo dizia «Prazo
       encerrado em <data futura> — sem oposição».
    5. O edital dizia «afixado… e publicado pela imprensa local»; esta casa
       publica no e-Proclamas.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import habilitacao as HAB                                    # noqa: E402
import rc_matricula as RCM                                   # noqa: E402
import sirc_remessa as SIRC                                  # noqa: E402
from hc_schema import init_hc_schema                          # noqa: E402
from nucleo_schema import init_nucleo_schema                  # noqa: E402
from rc_schema import init_rc_schema                         # noqa: E402

AGORA = "2026-10-07T10:00:00"
SENHA = "Senha#12345"
TEOR = ("Faço saber que pretendem casar-se FULANO DE TAL e BELTRANA DE TAL, e "
        "que apresentaram os documentos exigidos por lei. Quem souber de "
        "impedimento, oponha-o.")


# ------------------------------------------------------------- domínio


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(c)
    init_rc_schema(c)
    init_hc_schema(c)
    return c


def _assento(con, especie, *, numero, nome, dados=None, data_ato=AGORA,
             data_fato=None, regime=None):
    serie = {"NASCIMENTO": "RC_A", "CASAMENTO": "RC_B"}[especie]
    matricula = RCM.compor(cns="000000", ano=int(str(data_ato)[:4]),
                           livro_tipo="2" if especie == "CASAMENTO" else "1",
                           livro=4, folha=41, termo=numero)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, matricula, regime_bens,
               dados_json)
           VALUES (?,?,?,?,?,?,'ATIVO','MANUAL',?,?,?,?)""",
        (serie, especie, numero, nome, data_ato, data_fato or str(data_ato)[:10],
         AGORA, matricula, regime, json.dumps(dados or {})))
    aid = int(cur.lastrowid)
    con.execute("INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em) "
                "VALUES (?, 'REGISTRO', ?, ?)", (aid, AGORA[:10], AGORA))
    return aid


def _habilitada(con) -> int:
    hid = HAB.abrir(con, {"nubente1_nome": "FULANO DE TAL",
                          "nubente1_estado_civil": "SOLTEIRO",
                          "nubente2_nome": "BELTRANA DE TAL",
                          "nubente2_estado_civil": "SOLTEIRA",
                          "tipo": "CIVIL", "regime": "COMUNHAO_PARCIAL"},
                    agora=AGORA)
    for d in HAB.o_que_falta(con, hid):
        HAB.marcar_documento(con, d["id"], apresentado=True, agora=AGORA)
    HAB.publicar_edital(con, hid, teor=TEOR, agora=AGORA, hoje=AGORA[:10])
    HAB.habilitar(con, hid, agora=AGORA, hoje=AGORA[:10])
    con.execute("UPDATE hc_habilitacoes SET selo='HABCAS000000TESTE0000000001' "
                "WHERE id=?", (hid,))
    return hid


def test_celebrar_em_assento_de_nascimento_e_recusado_e_nada_se_grava(con):
    """O caso de 07/10: o código de um nascimento digitado no lugar do
    casamento. Antes, a habilitação virava CELEBRADA e o selo ia para o
    registro do nascimento."""
    hid = _habilitada(con)
    nasc = _assento(con, "NASCIMENTO", numero=12011,
                    nome="LAURO DE SOUSA CARDOSO", data_ato="1999-02-09")
    with pytest.raises(HAB.HabilitacaoError, match="não de casamento"):
        HAB.registrar_celebracao(con, hid, assento_id=nasc, agora=AGORA)
    h = HAB._hab(con, hid)
    assert h["situacao"] == "HABILITADO" and h["casamento_assento_id"] is None
    assert con.execute("SELECT selo FROM rc_atos WHERE assento_id=?",
                       (nasc,)).fetchone()[0] is None


def test_casamento_lavrado_para_outra_habilitacao_e_recusado(con):
    hid = _habilitada(con)
    cas = _assento(con, "CASAMENTO", numero=1013, nome="X e Y",
                   dados={"habilitacao_id": hid + 99})
    with pytest.raises(HAB.HabilitacaoError, match="outra habilitação"):
        HAB.registrar_celebracao(con, hid, assento_id=cas, agora=AGORA)


def test_o_casamento_desta_habilitacao_e_oferecido_e_celebra_com_o_selo(con):
    hid = _habilitada(con)
    cas = _assento(con, "CASAMENTO", numero=1013, nome="FULANO e BELTRANA",
                   dados={"habilitacao_id": hid})
    _assento(con, "CASAMENTO", numero=1014, nome="OUTRO CASAL",
             dados={"habilitacao_id": hid + 1})
    oferecidos = HAB.casamentos_da_habilitacao(con, hid)
    assert [a["id"] for a in oferecidos] == [cas]
    HAB.registrar_celebracao(con, hid, assento_id=cas, agora=AGORA)
    assert HAB._hab(con, hid)["casamento_assento_id"] == cas
    assert con.execute("SELECT selo FROM rc_atos WHERE assento_id=?",
                       (cas,)).fetchone()[0] == "HABCAS000000TESTE0000000001"


# ------------------------------------------------------------- SIRC


def test_a_consulta_dos_pendentes_traz_o_regime_e_ele_vai_ao_sirc(con):
    """Pelo CAMINHO DE VERDADE — `pendentes_de_remessa` —, e não por uma
    consulta montada no teste. Foi assim que o defeito passou."""
    cas = _assento(con, "CASAMENTO", numero=1013, nome="FULANO e BELTRANA",
                   regime="COMUNHAO_PARCIAL")
    for papel, nome, sexo in (("NUBENTE1", "FULANO", "M"),
                              ("NUBENTE2", "BELTRANA", "F")):
        con.execute("INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,"
                    " sexo, criado_em) VALUES (?,?,?,?,?,?)",
                    (cas, papel, nome, nome.lower(), sexo, AGORA))
    meus = [r for r in SIRC.pendentes_de_remessa(con) if r["assento_id"] == cas]
    assert meus and meus[0]["regime_bens"] == "COMUNHAO_PARCIAL"
    xml = SIRC._registro_casamento(con, meus[0])
    assert "<regimeCasamento>COMUNHAO_PARCIAL</regimeCasamento>" in xml


def test_celebracao_depois_do_registro_fica_retida_no_sirc_como_na_crc():
    m = RCM.compor(cns="000000", ano=2026, livro_tipo="2", livro=4, folha=41,
                   termo=1013)
    faltas = SIRC.o_que_falta(None, {
        "nome": "A e B", "tipo": "CASAMENTO", "matricula": m,
        "data_ato": "2026-10-07T15:26:16", "data_fato": "2026-10-08"})
    assert any("celebração (08/10/2026) é depois da data do registro "
               "(07/10/2026)" in f for f in faltas)
    assert SIRC.o_que_falta(None, {
        "nome": "A e B", "tipo": "CASAMENTO", "matricula": m,
        "data_ato": "2026-10-07T15:26:16", "data_fato": "2026-10-07"}) == []


# ------------------------------------------------------------- telas


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _abrir_e_publicar(casa) -> int:
    c = casa["cliente"]
    html = c.get("/rcpn/habilitacoes/nova").get_data(as_text=True)
    c.post("/rcpn/habilitacoes/nova", data={
        "csrf_token": _token(html), "nubente1_nome": "FULANO DE TAL",
        "nubente1_estado_civil": "SOLTEIRO", "nubente2_nome": "BELTRANA DE TAL",
        "nubente2_estado_civil": "SOLTEIRA", "tipo": "CIVIL",
        "regime": "COMUNHAO_PARCIAL"}, follow_redirects=True)
    banco = sqlite3.connect(casa["banco"])
    banco.row_factory = sqlite3.Row
    hid = int(banco.execute("SELECT MAX(id) FROM hc_habilitacoes").fetchone()[0])
    with banco:
        for d in HAB.o_que_falta(banco, hid):
            HAB.marcar_documento(banco, d["id"], apresentado=True, agora=AGORA)
        HAB.publicar_edital(banco, hid, teor=TEOR, agora=AGORA, hoje=AGORA[:10])
    return hid


def _texto_da_certidao(casa, hid) -> str:
    r = casa["cliente"].get(f"/rcpn/habilitacoes/{hid}/certidao")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        return re.sub(r"<[^>]+>", " ", z.read("content.xml").decode("utf-8"))


def test_certidao_expedida_com_o_prazo_correndo_nao_diz_que_ele_encerrou(casa):
    hid = _abrir_e_publicar(casa)
    banco = sqlite3.connect(casa["banco"])
    banco.row_factory = sqlite3.Row
    with banco:
        HAB.habilitar(banco, hid, agora=AGORA, hoje=AGORA[:10])
    texto = _texto_da_certidao(casa, hid)
    assert "Prazo encerrado" not in texto
    assert "ainda em curso" in texto and "12/10/2026" in texto


def test_certidao_expedida_depois_do_prazo_diz_encerrado(casa):
    hid = _abrir_e_publicar(casa)
    banco = sqlite3.connect(casa["banco"])
    banco.row_factory = sqlite3.Row
    with banco:
        HAB.habilitar(banco, hid, agora="2026-10-13T10:00:00", hoje="2026-10-13")
    texto = _texto_da_certidao(casa, hid)
    assert "Prazo encerrado em" in texto and "ainda em curso" not in texto


def test_o_modelo_do_edital_diz_e_proclamas_e_nao_imprensa(casa):
    hid = _abrir_e_publicar(casa)
    banco = sqlite3.connect(casa["banco"])
    with banco:
        banco.execute("UPDATE hc_habilitacoes SET situacao='EM_ANALISE', "
                      "edital_em=NULL WHERE id=?", (hid,))
    html = casa["cliente"].get(f"/rcpn/habilitacoes/{hid}").get_data(as_text=True)
    assert "e-Proclamas (CRC)" in html
    assert "imprensa local" not in html


def test_a_ficha_oferece_o_casamento_lavrado_para_escolher(casa):
    hid = _abrir_e_publicar(casa)
    banco = sqlite3.connect(casa["banco"])
    banco.row_factory = sqlite3.Row
    with banco:
        HAB.habilitar(banco, hid, agora=AGORA, hoje=AGORA[:10])
        cas = _assento(banco, "CASAMENTO", numero=1013,
                       nome="FULANO DE TAL e BELTRANA DE TAL",
                       dados={"habilitacao_id": hid})
    html = casa["cliente"].get(f"/rcpn/habilitacoes/{hid}").get_data(as_text=True)
    assert f'<option value="{cas}">' in html
    assert "termo 1013" in html

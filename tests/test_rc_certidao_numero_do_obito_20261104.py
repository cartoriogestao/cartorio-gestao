"""O número da Declaração de Óbito (D.O.) na certidão de óbito do RCPN.

Pedido do balcão de 04/11/2026: a certidão de óbito passa a trazer
«Nº DA D.O.: <número>», com o número que já está no assento
(`rc_assentos.numero_do`; no acervo do e-Ofício, `strNumeroDeclaracaoObito`).

ONDE: linha própria logo abaixo do quadro «NOME DO MÉDICO OU DAS TESTEMUNHAS |
NÚMERO DO DOCUMENTO» - a D.O. é o atestado que o médico assina, e é junto da
causa da morte e do médico que quem confere procura por ela. O Anexo VI não
tem caixa para a D.O.; por isso é linha, e por isso SOME quando o assento não
tem o número (sem traço, sem «None», sem linha em branco).

Vale para a emissão (`/rcpn/certidoes/<id>/odt`) e para a prévia do motor
(`modelos_motor_adapters.odt_do_contexto`), que usam o mesmo
`rc_certidao_odt.arquivo_da_certidao`. Dados FICTÍCIOS.
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

import rc_certidao_odt as ODT  # noqa: E402

SENHA = "Senha#12345"
NUMERO_DO = "312345678"
ROTULO = "Nº DA D.O.:"
LINHA = re.compile(r'<text:p text:style-name="PObNumeroDO"[^>]*>.*?</text:p>', re.S)


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": cg_casa["banco"]}


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _obito(s, *, numero_do=None, dados=None) -> int:
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, nome, data_ato,
                   data_fato, dados_json, situacao, origem, criado_em, numero_do)
               VALUES ('RC_C','OBITO',1999,'FALECIDO FICTICIO DE TESTE',
                       '2026-11-04','2026-11-02',?,'ATIVO','EOFICIO',
                       '2026-11-04T09:00:00',?)""",
            (json.dumps(dados or {}), numero_do))
        aid = cur.lastrowid
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem, rotulo,
                   data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',10,1999,'10','2026-11-04','EOFICIO',
                       '2026-11-04T09:00:00')""", (aid,))
        con.execute(
            """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem, origem, criado_em)
               VALUES (?,'FALECIDO','FALECIDO FICTICIO DE TESTE',1,'EOFICIO',
                       '2026-11-04T09:00:00')""", (aid,))
        codigo = f"88{aid:05d}"
        con.execute(
            "INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate, quantas, recebida_em)"
            " VALUES ('TESTE', ?, ?, 1, '2026-11-04T00:00:00')", (codigo, codigo))
        rid = con.execute("SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1").fetchone()[0]
        con.execute("INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em)"
                    " VALUES (?,?,'EM BRANCO','2026-11-04T00:00:00')", (codigo, rid))
    con.close()
    html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    s["c"].post(f"/rcpn/{aid}/certidao",
                data={"csrf_token": _token(html), "folha_seguranca": codigo},
                follow_redirects=True)
    return aid


def _certidao(s, aid) -> dict:
    con = _con(s)
    row = con.execute("SELECT * FROM rc_certidoes WHERE assento_id=? ORDER BY id DESC",
                      (aid,)).fetchone()
    con.close()
    assert row, "a certidão de óbito não foi emitida no ensaio"
    return dict(row)


def _xml(odt: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(odt)).read("content.xml").decode("utf-8")


def _texto(trecho: str) -> str:
    return re.sub(r"<[^>]+>", "", trecho)


def _corpo(xml: str) -> str:
    return xml[xml.find("<office:body"):]


def _emissao(s, cid) -> str:
    r = s["c"].get(f"/rcpn/certidoes/{cid}/odt?formato=odt")
    assert r.status_code == 200
    return _xml(r.get_data())


def _previa(s, cert) -> str:
    import modelos_motor_adapters as ADP
    import modelos_motor_contexto as CTX
    with s["app"].app_context():
        con = _con(s)
        try:
            ctx = CTX.contexto_de_assento(con, certidao=cert)
        finally:
            con.close()
        return _xml(ADP.odt_do_contexto(ctx, certidao=cert))


def _certidoes_gravadas(s) -> list:
    con = _con(s)
    try:
        return [tuple(r) for r in con.execute("SELECT * FROM rc_certidoes ORDER BY id")]
    finally:
        con.close()


def test_com_o_numero_a_linha_sai_abaixo_do_medico(s):
    aid = _obito(s, numero_do=NUMERO_DO)
    xml = _emissao(s, _certidao(s, aid)["id"])
    linhas = LINHA.findall(xml)
    assert len(linhas) == 1
    assert _texto(linhas[0]).strip() == f"{ROTULO} {NUMERO_DO}"
    assert "@numerodo" not in xml
    medico = xml.find('table:name="ObMedico"')
    sepultamento = xml.find("LOCAL DE SEPULTAMENTO")
    assert 0 < medico < xml.find(linhas[0]) < sepultamento


def test_o_numero_do_acervo_do_eoficio_tambem_sai(s):
    aid = _obito(s, dados={"strNumeroDeclaracaoObito": "398765432"})
    cert = _certidao(s, aid)
    for xml in (_emissao(s, cert["id"]), _previa(s, cert)):
        assert _texto(LINHA.findall(xml)[0]).strip() == f"{ROTULO} 398765432"


@pytest.mark.parametrize("vazio", [None, "", "   "])
def test_sem_o_numero_a_linha_some(s, vazio):
    aid = _obito(s, numero_do=vazio)
    cert = _certidao(s, aid)
    for xml in (_emissao(s, cert["id"]), _previa(s, cert)):
        corpo = _corpo(xml)
        assert "PObNumeroDO" not in corpo
        assert "D.O." not in _texto(corpo)
        assert "@numerodo" not in xml
        assert "None" not in _texto(corpo)
        assert "-----" not in _texto(corpo)


def test_previa_igual_a_emissao(s):
    aid = _obito(s, numero_do=NUMERO_DO)
    cert = _certidao(s, aid)
    emissao, previa = _emissao(s, cert["id"]), _previa(s, cert)
    assert LINHA.findall(emissao) == LINHA.findall(previa)
    assert _texto(LINHA.findall(previa)[0]).strip() == f"{ROTULO} {NUMERO_DO}"


def test_imprimir_nao_grava_na_certidao_emitida(s):
    aid = _obito(s, numero_do=NUMERO_DO)
    cid = _certidao(s, aid)["id"]
    antes = _certidoes_gravadas(s)
    _emissao(s, cid)
    s["c"].get(f"/rcpn/certidoes/{cid}/imprimir?formato=odt")
    assert _certidoes_gravadas(s) == antes


def test_molde_sem_a_linha_passa_igual():
    """Natimorto (caixa própria @numerodo) e molde ajustado pela casa antes de
    04/11 não têm o parágrafo `PObNumeroDO` - nada muda neles."""
    xml = '<text:p text:style-name="P6">@numerodo</text:p>'
    assert ODT.linha_do_numero_do(xml, {}) == xml
    natimorto = RAIZ / "modelos" / "certidao_natimorto_modelo.odt"
    if natimorto.is_file():
        x = zipfile.ZipFile(natimorto).read("content.xml").decode("utf-8")
        assert ODT.linha_do_numero_do(x, {}) == x


def test_o_molde_de_obito_tem_a_linha_uma_vez():
    x = zipfile.ZipFile(RAIZ / "modelos" / "certidao_obito_modelo.odt").read(
        "content.xml").decode("utf-8")
    assert len(LINHA.findall(x)) == 1
    assert "@numerodo" in LINHA.findall(x)[0]

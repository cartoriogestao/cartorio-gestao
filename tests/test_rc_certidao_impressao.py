"""A impressao da certidao do RCPN no molde ODT da casa.

O botao Imprimir baixa o .odt preenchido, nao o HTML antigo.
"""
from __future__ import annotations

import glob
import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
SELO = "AVESVD000000NARRKWVNJCRSVO21"
TOKEN = "MDGaPtZuqUKD4FtmC82CK5al"
MATRICULA = "000000015519971000111270010385 01"
MATRICULA_DIG = "00000001551997100011127001038501"

MIME_ODT = "application/vnd.oasis.opendocument.text"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear(s) -> int:
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem,
                   criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,?,
                       'JOAO DA SILVA','2020-01-20','2020-01-15',
                       '{"strSexo": "Masculino"}','ATIVO','EOFICIO',
                       '2026-08-26T09:00:00')""", (MATRICULA,))
        aid = con.execute("SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',127,19552,'127','2020-01-20','EOFICIO',
                       '2026-08-26T09:00:00')""", (aid,))
        for papel, quem, ordem in (("PAI", "JOSE DA SILVA", 1),
                                   ("MAE", "MARIA DAS GRACAS SILVA", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em)
                   VALUES (?,?,?,?,'EOFICIO','2026-08-26T09:00:00')""",
                (aid, papel, quem, ordem))
    con.close()
    return aid


def _semear_folha(s) -> str:
    """Uma folha EM BRANCO no estoque — exigida desde 09/09/2026
    (`FOLHA_SEGURANCA_OBRIGATORIA_CERT`) para emitir certidão de assento
    importado sem selo de registro, que é o caso de `_semear`."""
    con = _con(s)
    codigo = "9999999"
    with con:
        con.execute(
            """INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate,
                   quantas, recebida_em)
               VALUES ('TESTE', ?, ?, 1, '2026-09-09T00:00:00')""",
            (codigo, codigo))
        rid = con.execute(
            "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1").fetchone()["id"]
        con.execute(
            "INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em) "
            "VALUES (?,?,'EM BRANCO','2026-09-09T00:00:00')", (codigo, rid))
    con.close()
    return codigo


def _emitir(s, assento_id: int, **campos):
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    campos.setdefault("folha_seguranca", _semear_folha(s))
    return s["c"].post(f"/rcpn/{assento_id}/certidao",
                       data={"csrf_token": _token(html), **campos},
                       follow_redirects=True)


def _cid(s) -> int:
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    con.close()
    return cid


def _xml_odt(corpo: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(corpo)).read("content.xml").decode("utf-8")


# **O `.odt` PASSOU A PEDIR `?formato=odt`** — 01/09/2026, quando o oficial
# mandou o botao de imprimir entregar PDF: *«a ferramenta de impressão está
# baixando um arquivo, preciso que gere o pdf para impressão nesse botão»*.
#
# Estes testes conferem o CONTEUDO do papel — os campos preenchidos, o brasao
# que nao entra, o selo que aparece —, e para isso precisam do `.odt`, que e o
# que se abre como zip. O que o BOTAO entrega esta guardado em
# `test_rc_certidao_web.test_o_botao_de_imprimir_nao_entrega_odt`.
ODT = "?formato=odt"


def _e_odt(r) -> None:
    assert r.status_code == 200
    tipo = (r.headers.get("Content-Type") or "").lower()
    disp = (r.headers.get("Content-Disposition") or "").lower()
    assert "opendocument" in tipo or ".odt" in disp
    assert b"<html" not in r.get_data()[:200].lower()


def test_a_rota_de_impressao_abre(s):
    _emitir(s, _semear(s))
    r = s["c"].get(f"/rcpn/certidoes/{_cid(s)}/imprimir{ODT}")
    _e_odt(r)
    xml = _xml_odt(r.get_data())
    assert "CERTID" in xml
    assert "brasao.jpg" not in xml
    assert "JOAO DA SILVA" in xml or "JOÃO DA SILVA" in xml
    assert "000000" in xml


def test_o_odt_preenche_os_campos_da_casa(s):
    """`@serventia_email` saiu do rodapé em 09/09/2026 — o Anexo IV do
    Provimento CNJ 182/2024 não tem e-mail, telefone, CNPJ nem substituta,
    e o oficial mandou tirar o que não consta no modelo do CNJ. O endereço
    (`@serventia_endereco`) ficou, sem o rótulo "ENDEREÇO:" — é por isso que
    a asserção de e-mail virou o contrário do que era.

    TESTE VELHO, ATUALIZADO EM 14/10/2026: o endereço vinha da semente da
    casa, com o endereço REAL da serventia («Fabr…», «Av.»). A sanitização
    (B2/B3, 06–10/10/2026) esvaziou `serventia.PADRAO["serventia_endereco"]` e
    a serventia fictícia do `conftest` não tem endereço — o rodapé saía sem
    ele e a asserção caía. O endereço agora é fictício e gravado aqui, como a
    tela de Configurações grava; a regra («o endereço ficou») é a mesma."""
    from database import Database
    Database(s["banco"]).set_settings(
        {"serventia_endereco": "Avenida Exemplo, 100, Centro"})
    _emitir(s, _semear(s), selo=SELO)
    r = s["c"].get(f"/rcpn/certidoes/{_cid(s)}/odt{ODT}")
    _e_odt(r)
    xml = _xml_odt(r.get_data())
    assert "@nomenascido" not in xml
    assert "@unit_name" not in xml
    assert "JOAO DA SILVA" in xml or "JOÃO DA SILVA" in xml
    assert MATRICULA_DIG[:6] in xml
    assert "SERVENTIA" in xml or "Cidade Exemplo" in xml or "CIDADE EXEMPLO" in xml
    assert "000000" in xml
    assert "cidadeexemplo@cartorio.ch" not in xml
    assert "Fabr" in xml or "Av." in xml or "Avenida" in xml
    assert "996.269" not in xml
    assert "74,53" not in xml
    assert "AVERBA000000" not in xml
    assert SELO in xml


def test_imprimir_devolve_documento_e_nao_html(s):
    """O nome mudou junto com o que a rota entrega: o que este teste sempre
    guardou e que **nao sai HTML** — a tela antiga
    (`rcpn_certidao_impressa.html`) deixou de sair por este caminho."""
    _emitir(s, _semear(s))
    r = s["c"].get(f"/rcpn/certidoes/{_cid(s)}/imprimir{ODT}")
    _e_odt(r)
    corpo = r.get_data()
    assert corpo[:2] == b"PK"
    xml = _xml_odt(corpo)
    assert "rcpn_certidao_impressa" not in xml
    assert "<html" not in xml.lower()
    assert "@nomenascido" not in xml
    assert "@unit_name" not in xml


def test_a_tela_da_certidao_mostra_selo_e_o_imprimir(s):
    _emitir(s, _semear(s), selo=SELO)
    cid = _cid(s)
    html = s["c"].get(f"/rcpn/certidoes/{cid}").get_data(as_text=True)
    assert SELO in html
    assert f"/rcpn/certidoes/{cid}/imprimir" in html


def test_a_ficha_lista_o_selo(s):
    aid = _semear(s)
    _emitir(s, aid, selo=SELO)
    html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert SELO in html


def test_o_odt_sai_em_grade_nao_em_paragrafo(s):
    """O Word da casa e o molde; o sistema so troca os @."""
    _emitir(s, _semear(s), selo=SELO)
    r = s["c"].get(f"/rcpn/certidoes/{_cid(s)}/odt{ODT}")
    assert r.status_code == 200
    xml = _xml_odt(r.get_data())
    assert "CERTID" in xml
    assert "@nomenascido" not in xml
    assert "JOAO DA SILVA" in xml or "JOÃO DA SILVA" in xml
    assert ("ANOTAÇÕES VOLUNTÁRIAS DE CADASTRO" in xml
            or "ANOTACOES VOLUNTARIAS DE CADASTRO" in xml), (
        "o rótulo mudou para bater com o Anexo IV/V do Provimento CNJ "
        "182/2024 em 09/09/2026 — «Anotações voluntárias de cadastro», "
        "não «Anotações de cadastro»")
    assert "TÍTULO DE ELEITOR" not in xml and "TITULO DE ELEITOR" not in xml
    assert SELO in xml

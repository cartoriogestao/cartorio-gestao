"""A nota devolutiva com lugar claro no protocolo — pedido do oficial, 25/10/2026.

    «o sistema tem local claro para cadastrar nota devolutiva no protocolo?»
    «vamos mudar conforme recomendado»

O que se prova aqui: o ARQUIVO da nota (redigida em Word e assinada) vira a nota
cadastrada — numerada, protocolo DEVOLVIDO, qualificação negativa —, sem exigir que
as exigências sejam digitadas de novo; e o documento de CUMPRIMENTO registra o
reingresso da nota aberta. As três portas usam as mesmas funções.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_nota_devolutiva as RND  # noqa: E402

SENHA = "Senha#12345"
PDF = b"%PDF-1.4\n% nota de exemplo\n"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _um(casa, sql, *a):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, a).fetchone()
    finally:
        con.close()


def _todos(casa, sql, *a):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, a).fetchall()
    finally:
        con.close()


def _prenotar(casa):
    html = casa["cliente"].get("/registro-imoveis/protocolo").get_data(as_text=True)
    casa["cliente"].post("/registro-imoveis/protocolo", data={
        "apresentante": "MARIA DA SILVA", "natureza_titulo": "COMPRA E VENDA",
        "objeto": "escritura", "livro_destino": "2", "telefone": "(99) 90000-0000",
        "csrf_token": _token(html)}, follow_redirects=True)
    return _um(casa, "SELECT * FROM ri_protocolos ORDER BY id DESC LIMIT 1")


def _anexar(casa, p, tipo, nome="nota.pdf", **extra):
    tela = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}").get_data(as_text=True)
    dados = {"tipo": tipo, "csrf_token": _token(tela),
             "documento": (io.BytesIO(PDF), nome)}
    dados.update(extra)
    return casa["cliente"].post(f"/registro-imoveis/prenotacao/{p['id']}/documento",
                                data=dados, content_type="multipart/form-data",
                                follow_redirects=True)


# ------------------------------------------------------------------ a tela

def test_o_protocolo_mostra_a_nota_no_topo_e_pergunta_o_tipo_do_anexo(casa):
    p = _prenotar(casa)
    html = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}").get_data(as_text=True)
    assert 'id="nota-devolutiva"' in html
    # o quadro da nota vem ANTES do painel de anexos: é o lugar claro que faltava
    assert html.index('id="nota-devolutiva"') < html.index("Documentos do título")
    assert 'name="tipo"' in html and 'value="NOTA_DEVOLUTIVA"' in html
    assert 'value="CUMPRIMENTO_EXIGENCIA"' in html


# ------------------------------------------------------- o anexo é a nota

def test_anexar_o_arquivo_como_nota_cadastra_a_nota_e_devolve_o_protocolo(casa):
    p = _prenotar(casa)
    resp = _anexar(casa, p, "NOTA_DEVOLUTIVA", data_nota="2026-10-14")
    assert "cadastrada com o arquivo anexado" in resp.get_data(as_text=True)
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert nota["numero"] == 1 and nota["situacao"] == "ABERTA"
    assert nota["data_nota"] == "2026-10-14"
    assert RND.exigencias_da(nota) == []          # as exigências estão no papel assinado
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=?", p["id"])[0] == "DEVOLVIDO"
    q = _um(casa, "SELECT * FROM ri_qualificacoes WHERE protocolo_id=?", p["id"])
    assert q["resultado"] == "NEGATIVA" and q["nota_id"] == nota["id"]
    anexo = _um(casa, "SELECT * FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=?",
                p["id"])
    assert anexo["documento_tipo"] == "NOTA_DEVOLUTIVA"
    assert anexo["description"].startswith("Nota devolutiva nº 1")


def test_a_tela_da_nota_aceita_o_arquivo_sem_exigencia_digitada(casa):
    p = _prenotar(casa)
    tela = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}/nota").get_data(as_text=True)
    assert 'name="arquivo_nota"' in tela
    casa["cliente"].post(f"/registro-imoveis/protocolo/{p['id']}/nota", data={
        "csrf_token": _token(tela), "arquivo_nota": (io.BytesIO(PDF), "nota assinada.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert nota is not None
    html = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}/nota").get_data(as_text=True)
    assert "nota assinada.pdf" in html
    assert "constam da nota assinada" in html


def test_sem_exigencia_e_sem_arquivo_nao_ha_nota(casa):
    p = _prenotar(casa)
    tela = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}/nota").get_data(as_text=True)
    resp = casa["cliente"].post(f"/registro-imoveis/protocolo/{p['id']}/nota",
                                data={"csrf_token": _token(tela)}, follow_redirects=True)
    assert "ou anexe o arquivo" in resp.get_data(as_text=True)
    assert _um(casa, "SELECT COUNT(*) FROM ri_notas_devolutivas WHERE protocolo_id=?",
               p["id"])[0] == 0


def test_a_nota_digitada_continua_funcionando(casa):
    p = _prenotar(casa)
    tela = casa["cliente"].get(f"/registro-imoveis/protocolo/{p['id']}/nota").get_data(as_text=True)
    casa["cliente"].post(f"/registro-imoveis/protocolo/{p['id']}/nota",
                         data={"exigencias": "Apresentar a guia do ITBI quitada\nJuntar a procuração",
                               "csrf_token": _token(tela)})
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert RND.exigencias_da(nota) == ["Apresentar a guia do ITBI quitada", "Juntar a procuração"]


# ------------------------------------------- o cumprimento é o reingresso

def test_cumprimento_de_exigencia_registra_o_reingresso_da_nota_aberta(casa):
    p = _prenotar(casa)
    _anexar(casa, p, "NOTA_DEVOLUTIVA")
    resp = _anexar(casa, p, "CUMPRIMENTO_EXIGENCIA", nome="documentos.pdf",
                   data_reingresso=p["data_prenotacao"])
    assert "Reingresso registrado" in resp.get_data(as_text=True)
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert nota["situacao"] == "CUMPRIDA"
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=?", p["id"])[0] == "ABERTO"
    tipos = [r["documento_tipo"] for r in _todos(
        casa, "SELECT documento_tipo FROM attachments WHERE entity_type='RI_PROTOCOLO' "
              "AND entity_id=? ORDER BY id", p["id"])]
    assert tipos == ["NOTA_DEVOLUTIVA", "CUMPRIMENTO_EXIGENCIA"]


def test_cumprimento_sem_nota_aberta_so_anexa_e_avisa(casa):
    p = _prenotar(casa)
    resp = _anexar(casa, p, "CUMPRIMENTO_EXIGENCIA", nome="documentos.pdf")
    assert "Não há nota devolutiva aguardando cumprimento" in resp.get_data(as_text=True)
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=?", p["id"])[0] == "ABERTO"


def test_o_titulo_anexado_ganha_o_tipo(casa):
    p = _prenotar(casa)
    _anexar(casa, p, "TITULO", nome="escritura.pdf", descricao="escritura de compra e venda")
    anexo = _um(casa, "SELECT * FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=?",
                p["id"])
    assert anexo["documento_tipo"] == "TITULO"
    assert _um(casa, "SELECT COUNT(*) FROM ri_notas_devolutivas")[0] == 0


# ------------------------------------------------------------ o domínio

def test_protocolo_encerrado_nao_recebe_nota():
    assert RND.por_que_nao_emite({"situacao": "ENCERRADO", "ato_id": None, "numero": 1})
    assert RND.por_que_nao_emite({"situacao": "ABERTO", "ato_id": 7, "numero": 1})
    assert RND.por_que_nao_emite({"situacao": "ABERTO", "ato_id": None, "numero": 1}) is None
    assert RND.por_que_nao_emite({"situacao": "DEVOLVIDO", "ato_id": None, "numero": 1}) is None


def test_os_anexos_da_nota_sao_os_da_descricao_daquele_numero():
    docs = [{"documento_tipo": "NOTA_DEVOLUTIVA", "description": "Nota devolutiva nº 1"},
            {"documento_tipo": "NOTA_DEVOLUTIVA", "description": "Nota devolutiva nº 12: refeita"},
            {"documento_tipo": "TITULO", "description": "Nota devolutiva nº 1"}]
    assert RND.anexos_da_nota(docs, 1) == [docs[0]]
    assert RND.anexos_da_nota(docs, 12) == [docs[1]]


def test_o_modulo_nao_lavra_nem_sela_nem_cobra():
    nomes = [n for n in dir(RND) if not n.startswith("_")]
    for proibido in ("lavrar", "selar", "cobrar", "encerrar"):
        assert not any(proibido in n for n in nomes), proibido

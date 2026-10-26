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


# ------------------------------- a data do reingresso (revisão de 26/10/2026)
#
# Ela decide a prioridade: dentro da vigência, o título volta ao mesmo número
# de ordem (LRP art. 186; CN-MA art. 44). Retrodatar uma prenotação vencida
# guardava a prioridade antiga sem ninguém ver.

NOTA_ABERTA = {"id": 1, "numero": 1, "situacao": "ABERTA", "data_nota": "2026-11-05",
               "emitida_em": "2026-11-05T10:00:00"}
VENCIDA_EM_17_11 = {"id": 1, "data_limite": "2026-11-17", "prazo_suspenso_desde": None}


def _conferir(quando, hoje="2026-11-25", papel="USER", observacao=None, p=None):
    return RND.conferir_data_do_reingresso(NOTA_ABERTA, p or VENCIDA_EM_17_11,
                                           quando=quando, hoje=hoje, papel=papel,
                                           observacao=observacao)


def test_a_data_do_reingresso_nem_antes_da_nota_nem_depois_de_hoje():
    with pytest.raises(RND.NotaError, match="anterior à própria nota"):
        _conferir("2026-11-04", papel="ADMIN", observacao="recibo de entrega nº 12")
    with pytest.raises(RND.NotaError, match="depois de hoje"):
        _conferir("2026-11-26")
    with pytest.raises(RND.NotaError, match="não é uma data válida"):
        _conferir("25/11/2026")
    assert _conferir("2026-11-25") == "2026-11-25"


def test_data_passada_que_salva_a_prioridade_so_oficial_ou_gerente_e_com_motivo():
    # o cenário da revisão: venceu em 17/11, voltou em 25/11, digitaram 10/11.
    # DECISÃO DO OFICIAL EM 26/10/2026, «abre gerente»: ADMIN e MANAGER
    # registram, sempre com a justificativa; o escrevente e o auditor, não.
    assert set(RND.PAPEIS_QUE_RETROAGEM) == {"ADMIN", "MANAGER"}
    for papel in ("USER", "AUDITOR", None):
        with pytest.raises(RND.NotaError, match="só o oficial ou o gerente registram"):
            _conferir("2026-11-10", papel=papel, observacao="recibo de entrega nº 12")
    for papel in ("ADMIN", "MANAGER", "manager"):
        with pytest.raises(RND.NotaError, match="Escreva na observação"):
            _conferir("2026-11-10", papel=papel, observacao="ok")
        with pytest.raises(RND.NotaError, match="Escreva na observação"):
            _conferir("2026-11-10", papel=papel, observacao=None)
        assert _conferir("2026-11-10", papel=papel,
                         observacao="recibo de entrega nº 12, de 10/11") == "2026-11-10"
    # com a prenotação ainda viva, ou suspensa, a data passada não decide nada
    assert _conferir("2026-11-10", hoje="2026-11-15") == "2026-11-10"
    suspensa = dict(VENCIDA_EM_17_11, prazo_suspenso_desde="2026-11-12")
    assert _conferir("2026-11-10", p=suspensa) == "2026-11-10"
    # e a data de hoje, numa prenotação vencida, passa — e a nota fica fora do prazo
    assert _conferir("2026-11-25") == "2026-11-25"


def test_o_escrevente_nao_retrodata_o_reingresso_pela_tela(casa):
    """Pelo anexo «cumprimento de exigência», com a prenotação já vencida: a
    data passada é recusada, a nota continua aberta e o arquivo não fica."""
    from datetime import date, timedelta
    p = _prenotar(casa)
    _anexar(casa, p, "NOTA_DEVOLUTIVA")
    hoje = date.today()
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE ri_protocolos SET data_limite=? WHERE id=?",
                    ((hoje - timedelta(days=3)).isoformat(), p["id"]))
        con.execute("UPDATE ri_notas_devolutivas SET data_nota=? WHERE protocolo_id=?",
                    ((hoje - timedelta(days=10)).isoformat(), p["id"]))
    con.close()
    casa["db"].create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "USER")
    c = casa["app"].test_client()
    c.post("/login", data={"username": "beatriz", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    tela = c.get(f"/registro-imoveis/protocolo/{p['id']}").get_data(as_text=True)
    resp = c.post(f"/registro-imoveis/prenotacao/{p['id']}/documento", data={
        "tipo": "CUMPRIMENTO_EXIGENCIA", "csrf_token": _token(tela),
        "data_reingresso": (hoje - timedelta(days=5)).isoformat(),
        "documento": (io.BytesIO(PDF), "documentos.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    assert "só o oficial ou o gerente registram" in resp.get_data(as_text=True)
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert nota["situacao"] == "ABERTA" and not nota["data_reingresso"]
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=?", p["id"])[0] == "DEVOLVIDO"
    tipos = [r["documento_tipo"] for r in _todos(
        casa, "SELECT documento_tipo FROM attachments WHERE entity_type='RI_PROTOCOLO' "
              "AND entity_id=? ORDER BY id", p["id"])]
    assert tipos == ["NOTA_DEVOLUTIVA"]


def _prenotacao_vencida_com_nota_aberta(casa):
    """Prenotação vencida há 3 dias, com a nota devolutiva aberta há 10."""
    from datetime import date, timedelta
    p = _prenotar(casa)
    _anexar(casa, p, "NOTA_DEVOLUTIVA")
    hoje = date.today()
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE ri_protocolos SET data_limite=? WHERE id=?",
                    ((hoje - timedelta(days=3)).isoformat(), p["id"]))
        con.execute("UPDATE ri_notas_devolutivas SET data_nota=? WHERE protocolo_id=?",
                    ((hoje - timedelta(days=10)).isoformat(), p["id"]))
    con.close()
    return p, hoje


def _entrar(casa, usuario, papel):
    casa["db"].create_user(usuario, f"{usuario.upper()} EXEMPLO", SENHA, papel)
    c = casa["app"].test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def test_o_gerente_registra_o_reingresso_retroativo_com_a_justificativa(casa):
    """«Abre gerente» (26/10/2026): o MANAGER registra a data passada que mantém
    a prioridade — com a justificativa —, a nota fica CUMPRIDA, o protocolo
    volta a ABERTO e a auditoria guarda a data, o papel e que foi retroativo."""
    import json
    from datetime import timedelta
    p, hoje = _prenotacao_vencida_com_nota_aberta(casa)
    c = _entrar(casa, "carla", "MANAGER")
    retroativa = (hoje - timedelta(days=5)).isoformat()

    # sem a justificativa, recusa e nada muda
    tela = c.get(f"/registro-imoveis/protocolo/{p['id']}").get_data(as_text=True)
    resp = c.post(f"/registro-imoveis/prenotacao/{p['id']}/documento", data={
        "tipo": "CUMPRIMENTO_EXIGENCIA", "csrf_token": _token(tela),
        "data_reingresso": retroativa, "observacao": "ok",
        "documento": (io.BytesIO(PDF), "documentos.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    assert "Escreva na observação" in resp.get_data(as_text=True)
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert nota["situacao"] == "ABERTA" and not nota["data_reingresso"]

    # com a justificativa, registra
    tela = c.get(f"/registro-imoveis/protocolo/{p['id']}").get_data(as_text=True)
    resp = c.post(f"/registro-imoveis/prenotacao/{p['id']}/documento", data={
        "tipo": "CUMPRIMENTO_EXIGENCIA", "csrf_token": _token(tela),
        "data_reingresso": retroativa,
        "observacao": "recibo de entrega nº 12 assinado no balcão",
        "documento": (io.BytesIO(PDF), "documentos.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert nota["situacao"] == "CUMPRIDA"
    assert str(nota["data_reingresso"])[:10] == retroativa
    assert "recibo de entrega" in (nota["observacao_reingresso"] or "")
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=?", p["id"])[0] == "ABERTO"
    linha = _um(casa, "SELECT details FROM audit_logs WHERE action='RI_REINGRESSO' "
                      "ORDER BY id DESC LIMIT 1")
    detalhes = json.loads(linha["details"])
    assert detalhes["papel"] == "MANAGER" and detalhes["retroativo"] is True
    assert detalhes["data"] == retroativa


def test_o_auditor_nem_chega_a_registrar_o_reingresso(casa):
    """O AUDITOR só lê: a rota do documento não aceita o POST dele, e a nota
    continua aberta."""
    from datetime import timedelta
    p, hoje = _prenotacao_vencida_com_nota_aberta(casa)
    c = _entrar(casa, "carla", "AUDITOR")
    tela = c.get(f"/registro-imoveis/protocolo/{p['id']}").get_data(as_text=True)
    resp = c.post(f"/registro-imoveis/prenotacao/{p['id']}/documento", data={
        "tipo": "CUMPRIMENTO_EXIGENCIA", "csrf_token": _token(tela),
        "data_reingresso": (hoje - timedelta(days=5)).isoformat(),
        "observacao": "recibo de entrega nº 12 assinado no balcão",
        "documento": (io.BytesIO(PDF), "documentos.pdf")},
        content_type="multipart/form-data")
    assert resp.status_code == 403
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=?", p["id"])
    assert nota["situacao"] == "ABERTA" and not nota["data_reingresso"]

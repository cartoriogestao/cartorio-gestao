"""Fatia 2 do Balcao WhatsApp — config, HMAC, envio mockado, puxar.

Nao fala com a Meta de verdade. Nao abre tunel. Nao instala worker no Windows.
"""
from __future__ import annotations

import glob
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import wa_balcao as WA
import wa_fila as FILA
import wa_puxar as PUXAR
import wa_schema as SCH

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    # O `X-Wa-Test` destes testes só entra com o modo de teste LIGADO (LX11,
    # M6 do LS01): de fábrica ele nasce desligado e o webhook recusa.
    with bd.transaction() as con:
        WA.gravar_config(con, SCH.CHAVE_MODO_TESTE, "1")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "bd": bd}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _payload(texto: str, meta_id: str = "wamid.teste-1",
             wa_id: str = "5599988887777") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{
                        "profile": {"name": "Fulano da Silva"},
                        "wa_id": wa_id,
                    }],
                    "messages": [{
                        "from": wa_id,
                        "id": meta_id,
                        "type": "text",
                        "text": {"body": texto},
                    }],
                }
            }]
        }],
    }


def _csrf(c, path="/whatsapp"):
    return _token(c.get(path).get_data(as_text=True))


# ------------------------------------------- classificar


def test_classificar_horario():
    assert WA.classificar("Qual o horario que o cartorio abre?") == "horario"
    assert WA.classificar("Que horas fecha?") == "horario"


def test_classificar_certidao():
    assert WA.classificar("Preciso de certidao de nascimento") == "certidao"
    assert WA.classificar("certidão de casamento") == "certidao"
    assert WA.classificar("certidao de obito") == "certidao"


def test_classificar_protesto():
    assert WA.classificar("Tem protesto no meu nome?") == "protesto"
    assert WA.classificar("saiu o edital de intimacao") == "protesto"


def test_rascunho_nao_inventa_horario():
    texto = WA.rascunhar("abre que horas?", "horario", None)
    assert "confirmar horario de balcao" in texto
    assert "08:" not in texto and "8h" not in texto.lower()


def test_rascunho_sensivel_nao_traz_dado_de_livro():
    t = WA.rascunhar("certidao", "certidao", None)
    assert "livro" in t.lower()
    assert "nao enviamos" in t.lower() or "não enviamos" in t.lower()


# ------------------------------------------- webhook GET


def test_webhook_get_verify(s):
    r = s["c"].get(
        "/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": SCH.VERIFY_TOKEN_DEV,
            "hub.challenge": "desafio-123",
        },
    )
    assert r.status_code == 200
    assert r.get_data(as_text=True) == "desafio-123"


def test_webhook_get_token_errado(s):
    r = s["c"].get(
        "/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "nao-e-este",
            "hub.challenge": "x",
        },
    )
    assert r.status_code == 403


# ------------------------------------------- webhook POST + idempotencia


def test_webhook_post_cria_conversa_mensagem_rascunho_e_e_idempotente(s):
    corpo = _payload("Qual o horario de voces?", meta_id="wamid.abc")
    r1 = s["c"].post(
        "/whatsapp/webhook",
        data=json.dumps(corpo),
        content_type="application/json",
        headers={"X-Wa-Test": "1"},
    )
    assert r1.status_code == 200

    r2 = s["c"].post(
        "/whatsapp/webhook",
        data=json.dumps(corpo),
        content_type="application/json",
        headers={"X-Wa-Test": "1"},
    )
    assert r2.status_code == 200

    import sqlite3
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    convs = list(con.execute("SELECT * FROM wa_conversa"))
    msgs = list(con.execute("SELECT * FROM wa_mensagem"))
    assert len(convs) == 1
    assert len(msgs) == 1
    assert convs[0]["etiqueta"] == "horario"
    assert convs[0]["rascunho"]
    assert convs[0]["auto_ok"] == 0
    assert msgs[0]["meta_id"] == "wamid.abc"
    assert msgs[0]["direcao"] == "in"
    con.close()


# ------------------------------------------- GET /whatsapp


def test_get_whatsapp_lista(s):
    corpo = _payload("preciso de certidao de casamento", meta_id="wamid.lista")
    s["c"].post(
        "/whatsapp/webhook",
        data=json.dumps(corpo),
        content_type="application/json",
        headers={"X-Wa-Test": "1"},
    )
    r = s["c"].get("/whatsapp")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "WhatsApp" in html
    assert "Fulano da Silva" in html
    assert "certidao" in html
    assert "preciso de certidao" in html.lower() or "certidao de casamento" in html.lower()
    assert "Configura" in html


# ------------------------------------------- config (login + verify_token)


def test_get_config_exige_login(tmp_path):
    """A tela de configuracao nao abre para quem nao entrou.

    **A CASA PRECISA DE UM USUARIO PARA O TESTE PROVAR O QUE ELE DIZ.** Sem
    nenhum, o sistema manda para `/setup` — que e o certo, e e a primeira
    coisa que ele faz numa instalacao nova. So que `/setup` **nao prova que a
    tela exige login**: prova que a casa ainda nao existe.

    Este teste passava a afirmar o contrario do proprio nome; agora ele cria o
    usuario, sai do setup, e ai confere o que se quer conferir.
    """
    import glob

    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    Database(Path(glob.glob(f"{dados}/*.sqlite3")[0])).create_user(
        "tabeliao", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    r = app.test_client().get("/whatsapp/config", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    assert "login" in (r.headers.get("Location") or "").lower()


def test_post_config_grava_verify_token_e_webhook_usa(s):
    csrf = _csrf(s["c"], "/whatsapp/config")
    r = s["c"].post(
        "/whatsapp/config",
        data={"csrf_token": csrf, "verify_token": "token-oficial-casa",
              "phone_number_id": "", "access_token": "", "app_secret": "",
              "caixa_url": "", "caixa_segredo": ""},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302, 303)

    ok = s["c"].get(
        "/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-oficial-casa",
            "hub.challenge": "desafio-oficial",
        },
    )
    assert ok.status_code == 200
    assert ok.get_data(as_text=True) == "desafio-oficial"

    antigo = s["c"].get(
        "/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": SCH.VERIFY_TOKEN_DEV,
            "hub.challenge": "nao",
        },
    )
    assert antigo.status_code == 403

    errado = s["c"].get(
        "/whatsapp/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "outro",
            "hub.challenge": "nao",
        },
    )
    assert errado.status_code == 403


# ------------------------------------------- HMAC


def _assinado(secret: str, corpo: bytes) -> str:
    hx = hmac.new(secret.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
    return "sha256=" + hx


def test_hmac_secret_correto_aceita_errado_403(s):
    import sqlite3
    con = sqlite3.connect(s["banco"])
    WA.gravar_config(con, SCH.CHAVE_APP_SECRET, "segredo-de-teste")
    con.commit()
    con.close()

    corpo_obj = _payload("horario de vocês?", meta_id="wamid.hmac-ok")
    bruto = json.dumps(corpo_obj).encode("utf-8")

    r_ok = s["c"].post(
        "/whatsapp/webhook",
        data=bruto,
        content_type="application/json",
        headers={"X-Hub-Signature-256": _assinado("segredo-de-teste", bruto)},
    )
    assert r_ok.status_code == 200

    corpo2 = json.dumps(_payload("outra", meta_id="wamid.hmac-bad")).encode()
    r_bad = s["c"].post(
        "/whatsapp/webhook",
        data=corpo2,
        content_type="application/json",
        headers={"X-Hub-Signature-256": _assinado("segredo-errado", corpo2)},
    )
    assert r_bad.status_code == 403

    r_teste = s["c"].post(
        "/whatsapp/webhook",
        data=corpo2,
        content_type="application/json",
        headers={"X-Wa-Test": "1"},
    )
    assert r_teste.status_code == 403


# ------------------------------------------- enviar


class _Resp:
    def __init__(self, status, body):
        self.status = status
        self._body = body.encode("utf-8") if isinstance(body, str) else body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _entrar(s, texto="oi", meta_id="wamid.in-env"):
    s["c"].post(
        "/whatsapp/webhook",
        data=json.dumps(_payload(texto, meta_id=meta_id)),
        content_type="application/json",
        headers={"X-Wa-Test": "1"},
    )
    import sqlite3
    con = sqlite3.connect(s["banco"])
    cid = con.execute("SELECT id FROM wa_conversa").fetchone()[0]
    con.close()
    return cid


def test_enviar_mock_graph_cria_mensagem_out(s):
    import sqlite3
    con = sqlite3.connect(s["banco"])
    WA.gravar_config(con, SCH.CHAVE_TOKEN, "EAAB-teste")
    WA.gravar_config(con, SCH.CHAVE_PHONE, "123456789")
    con.commit()
    con.close()
    cid = _entrar(s)

    def fake_urlopen(req, timeout=None):
        assert "graph.facebook.com/v21.0/123456789/messages" in req.full_url
        return _Resp(200, json.dumps({"messages": [{"id": "wamid.out-1"}]}))

    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    csrf = _token(html)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen) as m:
        r = s["c"].post(
            f"/whatsapp/{cid}/enviar",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert m.called
    assert r.status_code in (200, 302, 303)

    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    outs = list(con.execute(
        "SELECT * FROM wa_mensagem WHERE direcao='out'"))
    conv = con.execute("SELECT * FROM wa_conversa WHERE id=?", (cid,)).fetchone()
    assert len(outs) == 1
    assert outs[0]["texto"]
    assert conv["status"] == "aguardando"
    con.close()


def test_enviar_sem_token_4xx_nao_chama_rede(s):
    cid = _entrar(s, meta_id="wamid.in-sem-token")
    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    csrf = _token(html)
    with patch("urllib.request.urlopen") as m:
        r = s["c"].post(
            f"/whatsapp/{cid}/enviar",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert not m.called
    # 27/10/2026: a recusa volta à conversa com o aviso (302). Com o status 400
    # o navegador não seguia o redirecionamento e mostrava «Redirecting…».
    assert r.status_code == 302
    assert f"/whatsapp/{cid}" in r.headers["Location"]
    import sqlite3
    con = sqlite3.connect(s["banco"])
    n_out = con.execute(
        "SELECT COUNT(*) FROM wa_mensagem WHERE direcao='out'").fetchone()[0]
    con.close()
    assert n_out == 0


# ------------------------------------------- puxar (mock, sem rede)


def test_puxar_mock_aplica_pendente(s):
    import sqlite3
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    WA.gravar_config(con, SCH.CHAVE_CAIXA_URL, "https://exemplo.invalid/pendentes")
    con.commit()

    def http_get(url, segredo):
        assert url.endswith("/pendentes")
        corpo = _payload("qual o horario?", meta_id="wamid.caixa-1")
        return 200, json.dumps({"pendentes": [corpo]})

    achado = PUXAR.buscar_pendentes(con, http_get=http_get)
    assert achado["ok"] is True
    r = PUXAR.aplicar_itens(con, achado["itens"])
    assert r["ok"] is True
    assert r["aplicadas"] == 1
    n = con.execute("SELECT COUNT(*) FROM wa_conversa").fetchone()[0]
    assert n == 1
    con.close()


# ------------------------------------------- revisao do L023 (PostgreSQL nativo)


def test_segunda_mensagem_sem_nome_guarda_o_nome_e_com_nome_troca(cg_casa):
    """`COALESCE(NULLIF(%s, ''), nome)` no UPDATE da conversa que ja existe:
    nome vazio nao apaga o que havia; nome novo troca."""
    import sqlite3
    con = sqlite3.connect(cg_casa["banco"])
    try:
        WA.aplicar_entrada(con, _payload("oi", meta_id="wamid.nome-1"))
        sem_nome = {"messages": [{"from": "5599988887777", "id": "wamid.nome-2",
                                  "text": {"body": "oi de novo"}}]}
        assert WA.aplicar_entrada(con, sem_nome)["criadas"] == 1
        con.commit()
        assert [c["nome"] for c in FILA.listar(con, agora=WA.agora_iso())] == ["Fulano da Silva"]

        com_nome = _payload("sou eu", meta_id="wamid.nome-3")
        contato = com_nome["entry"][0]["changes"][0]["value"]["contacts"][0]
        contato["profile"]["name"] = "Ciclano de Tal"
        WA.aplicar_entrada(con, com_nome)
        con.commit()
        convs = FILA.listar(con, agora=WA.agora_iso())
        assert [c["nome"] for c in convs] == ["Ciclano de Tal"]
        assert len(WA.conversa(con, convs[0]["id"])["mensagens"]) == 3
    finally:
        con.close()


def test_a_entrada_confere_se_ja_chegou_dentro_da_trava(cg_casa, monkeypatch):
    """No SQLite, o BEGIN IMMEDIATE do webhook punha em fila duas entradas
    iguais (a Meta reenvia; duas pessoas puxam a caixa-postal juntas), e a
    segunda contava como repetida. Sem a ponte, "ja chegou?" e "ja tem
    conversa deste numero?" so valem se conferidos dentro da trava."""
    import sqlite3

    import banco_pg
    if not banco_pg.ativo():
        pytest.skip("modulo nativo: so roda com o PostgreSQL ligado (CG_PG_DSN)")
    import psycopg

    def livre() -> bool:
        with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
            return bool(outra.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
                ("wa_mensagem.meta_id",)).fetchone()[0])

    vistas = []
    ja_tem_meta, conversa_por_wa = WA._ja_tem_meta, WA._conversa_por_wa

    def espia_meta(con, meta_id):
        vistas.append(("meta_id", livre()))
        return ja_tem_meta(con, meta_id)

    def espia_wa(con, wa_id):
        vistas.append(("wa_id", livre()))
        return conversa_por_wa(con, wa_id)

    monkeypatch.setattr(WA, "_ja_tem_meta", espia_meta)
    monkeypatch.setattr(WA, "_conversa_por_wa", espia_wa)
    con = sqlite3.connect(cg_casa["banco"])
    try:
        r = WA.aplicar_entrada(con, _payload("oi", meta_id="wamid.trava-1"))
        con.commit()
    finally:
        con.close()
    assert r["criadas"] == 1
    assert vistas == [("meta_id", False), ("wa_id", False)], \
        "a conferencia rodou com a trava livre"


# ===================================================================
# A TELA DE CONVERSA (27/10/2026)
#
# `/whatsapp` e `/whatsapp/<id>` são a mesma tela: a lista à esquerda e a
# conversa em balões à direita. O `/novas` só lê o banco. O envio manda o que
# está na caixa: guarda como rascunho e segue o caminho de sempre.
# ===================================================================

from contextlib import contextmanager  # noqa: E402

from bd_nativo import banco as _banco  # noqa: E402

SCRIPT = "<script>alert(1)</script>"
ESCAPADO = "&lt;script&gt;alert(1)&lt;/script&gt;"


def _um(s, sql, args=()):
    with s["bd"].connect() as con:
        return _banco(con).um(sql, args)


def _mensagens(s, cid):
    with s["bd"].connect() as con:
        return _banco(con).ler(
            "SELECT * FROM wa_mensagem WHERE conversa_id=%s ORDER BY id", (cid,))


def _saidas(s, cid):
    return [m for m in _mensagens(s, cid) if m["direcao"] == "out"]


def _mais_uma(s, texto, meta_id):
    s["c"].post("/whatsapp/webhook", data=json.dumps(_payload(texto, meta_id=meta_id)),
                content_type="application/json", headers={"X-Wa-Test": "1"})


def _logar(app, usuario):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _com_token(s):
    with s["bd"].transaction() as con:
        WA.gravar_config(con, SCH.CHAVE_TOKEN, "EAAB-teste")
        WA.gravar_config(con, SCH.CHAVE_PHONE, "123456789")


def _saida(s, cid, texto, autor, meta_id):
    with s["bd"].transaction() as con:
        WA.gravar_saida(con, cid, texto, meta_id, autor=autor)


def test_a_lista_pede_para_escolher_e_a_conversa_abre_na_mesma_tela(s):
    cid = _entrar(s, texto="e a certidao?", meta_id="wamid.tela-1")
    html = s["c"].get("/whatsapp").get_data(as_text=True)
    assert "Escolha uma conversa" in html
    assert "Fulano da Silva" in html and 'class="wa-item' in html
    assert "wa-balao" not in html
    r = s["c"].get(f"/whatsapp/{cid}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Escolha uma conversa" not in html
    assert 'class="wa-item' in html and 'aria-current="true"' in html
    assert "wa-balao wa-in" in html and "e a certidao?" in html
    assert s["c"].get("/whatsapp/999999").status_code == 404


def test_recebida_a_esquerda_enviada_a_direita_e_a_ia_marcada(s):
    cid = _entrar(s, meta_id="wamid.lados")
    _saida(s, cid, "Bom dia! Já saiu.", "ia", "wamid.saida-ia")
    _saida(s, cid, "Pode retirar no balcão.", "MARIO EXEMPLO DOS SANTOS", "wamid.saida-p")
    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert html.count("wa-balao wa-in") == 1 and html.count("wa-balao wa-out") == 2
    assert "resposta automática (IA)" in html
    assert "enviada por MARIO EXEMPLO DOS SANTOS" in html
    # o id da Meta vai no `title`, ao passar o mouse, e não no texto do balão
    assert 'title="wamid.saida-ia"' in html and ">wamid.saida-ia<" not in html


def test_os_baloes_tem_dois_tons_de_azul_do_sistema_e_nada_de_verde():
    css = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
    assert "--balao-recebido:#e7f1fc" in css and "--balao-enviado:var(--accent2)" in css
    regras = "\n".join(linha for linha in css.splitlines() if linha.startswith(".wa-"))
    assert "var(--balao-recebido)" in regras and "var(--balao-enviado)" in regras
    for verde in ("#d9fdd3", "#25d366", "#dcf8c6", "#075e54", "green"):
        assert verde not in regras.lower(), verde


def test_o_texto_do_cliente_sai_escapado_na_tela_e_no_novas(s):
    cid = _entrar(s, texto="primeira", meta_id="wamid.esc-0")
    ultimo = _mensagens(s, cid)[-1]["id"]
    _mais_uma(s, SCRIPT, "wamid.esc-1")
    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert SCRIPT not in html and ESCAPADO in html
    novas = s["c"].get(f"/whatsapp/{cid}/novas?depois={ultimo}").get_json()
    assert SCRIPT not in novas["html"] and ESCAPADO in novas["html"]
    assert SCRIPT not in s["c"].get("/whatsapp/lista-parcial").get_data(as_text=True)


def test_novas_traz_so_o_que_veio_depois(s, cg_casa):
    cid = _entrar(s, texto="um", meta_id="wamid.nv-1")
    _mais_uma(s, "msg 2", "wamid.nv-2")
    _mais_uma(s, "msg 3", "wamid.nv-3")
    ids = [m["id"] for m in _mensagens(s, cid)]
    assert len(ids) == 3
    r = s["c"].get(f"/whatsapp/{cid}/novas?depois={ids[0]}")
    assert r.status_code == 200
    d = r.get_json()
    assert re.findall(r'data-id="(\d+)"', d["html"]) == [str(i) for i in ids[1:]]
    assert d["ultimo"] == ids[-1] and d["status"] and d["modo"]
    assert "janela_fora" in d
    # o separador do dia que já está na tela não se repete
    assert "wa-dia" not in d["html"]
    vazio = s["c"].get(f"/whatsapp/{cid}/novas?depois={ids[-1]}").get_json()
    assert vazio["html"] == "" and vazio["ultimo"] == ids[-1]
    assert s["c"].get("/whatsapp/999999/novas?depois=0").status_code == 404
    r = cg_casa["app"].test_client().get(f"/whatsapp/{cid}/novas?depois=0")
    assert r.status_code in (302, 303) and "login" in r.headers["Location"]


def test_novas_e_a_lista_so_leem_o_banco_e_nao_falam_com_a_rede(s, monkeypatch):
    cid = _entrar(s, meta_id="wamid.nv-rede")

    def sem_escrita():
        raise AssertionError("o /novas ou a lista abriu transação de escrita")
    monkeypatch.setattr(s["bd"], "transaction", sem_escrita)
    with patch("urllib.request.urlopen") as rede:
        assert s["c"].get(f"/whatsapp/{cid}/novas?depois=0").status_code == 200
        assert s["c"].get("/whatsapp/lista-parcial").status_code == 200
    assert not rede.called


def _transacao_vigiada(s, monkeypatch):
    original = s["bd"].transaction
    aberta = []

    @contextmanager
    def vigiada():
        with original() as con:
            aberta.append(1)
            try:
                yield con
            finally:
                aberta.pop()
    monkeypatch.setattr(s["bd"], "transaction", vigiada)
    return aberta


def test_enviar_o_texto_da_caixa_guarda_posta_fora_da_transacao_e_grava(s, monkeypatch):
    _com_token(s)
    cid = _entrar(s, meta_id="wamid.caixa")
    aberta = _transacao_vigiada(s, monkeypatch)
    postados = []

    def postar(pedido):
        postados.append(bool(aberta))
        return "wamid.caixa-out"
    monkeypatch.setattr(WA, "postar_envio", postar)
    csrf = _csrf(s["c"], f"/whatsapp/{cid}")
    r = s["c"].post(f"/whatsapp/{cid}/enviar",
                    data={"csrf_token": csrf, "rascunho": "  A certidão já saiu.  "})
    assert r.status_code == 302 and f"/whatsapp/{cid}" in r.headers["Location"]
    assert postados == [False], "o postar_envio rodou dentro da transação"
    assert _um(s, "SELECT rascunho FROM wa_conversa WHERE id=%s",
               (cid,))["rascunho"] == "A certidão já saiu."
    assert [(m["texto"], m["meta_id"]) for m in _saidas(s, cid)] == [
        ("A certidão já saiu.", "wamid.caixa-out")]


def test_enviar_com_a_caixa_vazia_e_recusado_sem_rede(s, monkeypatch):
    _com_token(s)
    cid = _entrar(s, meta_id="wamid.vazia")
    monkeypatch.setattr(WA, "postar_envio",
                        lambda pedido: pytest.fail("a caixa vazia chamou a rede"))
    csrf = _csrf(s["c"], f"/whatsapp/{cid}")
    r = s["c"].post(f"/whatsapp/{cid}/enviar", data={"csrf_token": csrf, "rascunho": "   "})
    assert r.status_code == 302 and f"/whatsapp/{cid}" in r.headers["Location"]
    assert not _saidas(s, cid)
    assert "Escreva a mensagem." in s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)


def test_enviar_sem_o_campo_manda_o_rascunho_guardado(s, monkeypatch):
    _com_token(s)
    cid = _entrar(s, meta_id="wamid.guardado")
    with s["bd"].transaction() as con:
        WA.salvar_rascunho(con, cid, "Rascunho guardado antes.")
    monkeypatch.setattr(WA, "postar_envio", lambda pedido: "wamid.guardado-out")
    csrf = _csrf(s["c"], f"/whatsapp/{cid}")
    assert s["c"].post(f"/whatsapp/{cid}/enviar", data={"csrf_token": csrf}).status_code == 302
    assert [m["texto"] for m in _saidas(s, cid)] == ["Rascunho guardado antes."]


def test_o_auditor_ve_a_tela_e_o_novas_e_nao_envia(s, monkeypatch):
    _com_token(s)
    cid = _entrar(s, meta_id="wamid.auditor")
    s["bd"].create_user("fiscal", "Auditor Exemplo", SENHA, "AUDITOR")
    fiscal = _logar(s["app"], "fiscal")
    tela = fiscal.get(f"/whatsapp/{cid}")
    assert tela.status_code == 200 and "wa-balao" in tela.get_data(as_text=True)
    assert fiscal.get(f"/whatsapp/{cid}/novas?depois=0").status_code == 200
    monkeypatch.setattr(WA, "postar_envio",
                        lambda pedido: pytest.fail("o AUDITOR chegou à rede"))
    r = fiscal.post(f"/whatsapp/{cid}/enviar",
                    data={"csrf_token": _token(tela.get_data(as_text=True)),
                          "rascunho": "não pode sair"})
    assert r.status_code == 403
    assert not _saidas(s, cid)


def test_o_formulario_de_envio_tem_a_trava_contra_o_envio_em_dobro(s):
    cid = _entrar(s, meta_id="wamid.dobro")
    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    form = re.search(r'<form[^>]*action="/whatsapp/%d/enviar"[^>]*>' % cid, html)
    assert form and "data-wa-envio-unico" in form.group(0)
    assert "/whatsapp_chat.js" in html
    js = (RAIZ / "static" / "whatsapp_chat.js").read_text(encoding="utf-8")
    assert "form[data-wa-envio-unico]" in js and "enviando…" in js


def test_as_acoes_de_antes_continuam_e_voltam_para_a_conversa(s):
    cid = _entrar(s, meta_id="wamid.acoes")
    csrf = _csrf(s["c"], f"/whatsapp/{cid}")
    for rota, dados in (("etiqueta", {"etiqueta": "retorno"}),
                        ("transferir", {"setor": "NOTAS"}),
                        ("assumir", {})):
        r = s["c"].post(f"/whatsapp/{cid}/{rota}", data={"csrf_token": csrf, **dados})
        assert r.status_code == 302, rota
        assert r.headers["Location"].endswith(f"/whatsapp/{cid}"), rota
    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert "retorno" in html and "Histórico da conversa" in html
    # o resolver volta à lista, como antes
    r = s["c"].post(f"/whatsapp/{cid}/resolver", data={"csrf_token": csrf})
    assert r.status_code == 302 and r.headers["Location"].endswith("/whatsapp")
    assert _um(s, "SELECT status FROM wa_conversa WHERE id=%s",
               (cid,))["status"] == "resolvida"


# -------------------------------------------- as perguntas automáticas e a sessão
#
# Revisão do #72: o `/novas` e a lista parcial são perguntas que a tela faz
# sozinha. Elas conferem o prazo de inatividade como qualquer rota, mas não o
# renovam: a tela aberta sem ninguém mexendo expira no prazo normal.

from datetime import datetime, timedelta  # noqa: E402


def _inatividade(s, minutos_atras):
    marca = (datetime.now() - timedelta(minutes=minutos_atras)).isoformat(timespec="seconds")
    with s["c"].session_transaction() as sessao:
        sessao["last_activity"] = marca
    return marca


def _ultima_atividade(s):
    with s["c"].session_transaction() as sessao:
        return sessao.get("last_activity")


def test_as_perguntas_automaticas_sao_rotas_de_verdade(s):
    """O conjunto do `app.py` fala de endpoints pelo nome: um nome trocado
    deixaria a pergunta renovar a sessão calada."""
    endpoints = {regra.endpoint for regra in s["app"].url_map.iter_rules()}
    assert {"whatsapp_novas", "whatsapp_lista_parcial"} <= endpoints
    app_py = (RAIZ / "app.py").read_text(encoding="utf-8")
    assert "ENDPOINTS_QUE_NAO_RENOVAM_A_SESSAO" in app_py
    assert '"whatsapp_novas", "whatsapp_lista_parcial"' in app_py


def test_novas_com_a_sessao_vencida_por_inatividade_vai_ao_login(s):
    cid = _entrar(s, meta_id="wamid.sessao-vencida")
    _inatividade(s, 24 * 60)
    r = s["c"].get(f"/whatsapp/{cid}/novas?depois=0")
    assert r.status_code in (302, 303) and "login" in r.headers["Location"]
    assert s["c"].get(f"/whatsapp/{cid}").status_code in (302, 303)


def test_uma_sequencia_de_novas_nao_adia_a_expiracao(s):
    cid = _entrar(s, meta_id="wamid.sessao-seq")
    marca = _inatividade(s, 50)
    for _ in range(3):
        assert s["c"].get(f"/whatsapp/{cid}/novas?depois=0").status_code == 200
        assert s["c"].get("/whatsapp/lista-parcial").status_code == 200
    assert _ultima_atividade(s) == marca, "a pergunta automática renovou a sessão"
    # a mesma sessão, passado o prazo, é recusada: as perguntas não a seguraram
    _inatividade(s, 24 * 60)
    r = s["c"].get(f"/whatsapp/{cid}/novas?depois=0")
    assert r.status_code in (302, 303) and "login" in r.headers["Location"]


def test_abrir_a_conversa_renova_a_sessao(s):
    cid = _entrar(s, meta_id="wamid.sessao-clique")
    marca = _inatividade(s, 50)
    assert s["c"].get(f"/whatsapp/{cid}").status_code == 200
    assert _ultima_atividade(s) != marca


def test_a_lista_parcial_se_identifica_e_o_js_para_na_resposta_estranha(s):
    r = s["c"].get("/whatsapp/lista-parcial")
    assert r.headers.get("X-Wa-Parcial") == "lista"
    js = (RAIZ / "static" / "whatsapp_chat.js").read_text(encoding="utf-8")
    assert "r.redirected" in js and "window.location.reload()" in js
    assert '"X-Wa-Parcial"' in js and "application/json" in js
    assert "clearInterval" in js

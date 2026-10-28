"""O ATALHO DO WHATSAPP COM O ALERTA DE NÃO RESPONDIDAS (27/10/2026).

O número é o de conversas ESPERANDO RESPOSTA — a última mensagem é do
cliente e ninguém respondeu depois —, só as de quem vê ou de ninguém. Conta a
conversa, e não a mensagem. A pergunta automática não renova a sessão. Só
dados fictícios.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import wa_balcao as WA  # noqa: E402
import wa_fila as FILA  # noqa: E402
from bd_nativo import banco  # noqa: E402
from test_wa_balcao import SENHA, _payload, _sessao, _token  # noqa: E402


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _chegar(s, wa_id, texto, meta_id):
    corpo = _payload(texto, meta_id=meta_id, wa_id=wa_id)
    s["c"].post("/whatsapp/webhook", data=json.dumps(corpo),
                content_type="application/json", headers={"X-Wa-Test": "1"})
    with s["bd"].connect() as con:
        return int(banco(con).um("SELECT id FROM wa_conversa WHERE wa_id=%s", (wa_id,))["id"])


def _sql(s, comando, args=()):
    with s["bd"].transaction() as con:
        banco(con).escrever(comando, args)


def _eu(s):
    with s["bd"].connect() as con:
        return int(banco(con).um("SELECT id FROM users WHERE username='tabeliao'")["id"])


def _contar(s, usuario_id):
    with s["bd"].connect() as con:
        return FILA.nao_respondidas(con, usuario_id=usuario_id)


def _responder(s, cid, autor):
    with s["bd"].transaction() as con:
        WA.gravar_saida(con, cid, "Respondido.", f"wamid.resp-{cid}-{autor}", autor=autor)


# ------------------------------------------------------------- a contagem


def test_conta_a_conversa_cuja_ultima_mensagem_e_do_cliente(s):
    _chegar(s, "5511900000301", "oi, e a certidão?", "wamid.at-1")
    assert _contar(s, _eu(s)) == 1


def test_a_respondida_pela_ia_ou_por_pessoa_nao_conta(s):
    pela_ia = _chegar(s, "5511900000311", "oi", "wamid.at-2")
    por_pessoa = _chegar(s, "5511900000312", "oi", "wamid.at-3")
    _responder(s, pela_ia, "ia")
    _responder(s, por_pessoa, "MARIO EXEMPLO DOS SANTOS")
    assert _contar(s, _eu(s)) == 0
    # e volta a contar quando o cliente escreve de novo
    _chegar(s, "5511900000311", "mais uma dúvida", "wamid.at-4")
    assert _contar(s, _eu(s)) == 1


def test_a_resolvida_nao_conta(s):
    cid = _chegar(s, "5511900000321", "oi", "wamid.at-5")
    with s["bd"].transaction() as con:
        WA.resolver(con, cid)
    assert _contar(s, _eu(s)) == 0


def test_so_contam_as_minhas_e_as_sem_responsavel(s):
    s["bd"].create_user("beatriz", "Beatriz Exemplo", SENHA, "USER")
    with s["bd"].connect() as con:
        outra = int(banco(con).um("SELECT id FROM users WHERE username='beatriz'")["id"])
    sem = _chegar(s, "5511900000331", "oi", "wamid.at-6")
    minha = _chegar(s, "5511900000332", "oi", "wamid.at-7")
    dela = _chegar(s, "5511900000333", "oi", "wamid.at-8")
    _sql(s, "UPDATE wa_conversa SET responsavel_id=%s WHERE id=%s", (_eu(s), minha))
    _sql(s, "UPDATE wa_conversa SET responsavel_id=%s WHERE id=%s", (outra, dela))
    assert sem
    assert _contar(s, _eu(s)) == 2          # a sem responsável e a minha
    assert _contar(s, outra) == 2           # a sem responsável e a dela


def test_cinco_mensagens_seguidas_do_mesmo_cliente_contam_uma(s):
    for n in range(5):
        _chegar(s, "5511900000341", f"mensagem {n}", f"wamid.at-9-{n}")
    assert _contar(s, _eu(s)) == 1


def test_o_rotulo_diz_o_numero_por_extenso():
    assert FILA.rotulo_do_atalho(0) == {"n": 0, "texto": "0", "rotulo": "WhatsApp"}
    assert FILA.rotulo_do_atalho(1)["rotulo"] == "WhatsApp: 1 conversa esperando resposta"
    assert FILA.rotulo_do_atalho(12)["rotulo"] == "WhatsApp: 12 conversas esperando resposta"
    assert FILA.rotulo_do_atalho(120)["texto"] == "99+"


# ------------------------------------------------------------- a rota


def test_a_rota_devolve_o_numero_e_sem_login_vai_ao_login(s, cg_casa):
    _chegar(s, "5511900000351", "oi", "wamid.at-10")
    r = s["c"].get("/whatsapp/nao-respondidas")
    assert r.status_code == 200 and r.get_json()["n"] == 1
    assert r.get_json()["rotulo"] == "WhatsApp: 1 conversa esperando resposta"
    anonimo = cg_casa["app"].test_client().get("/whatsapp/nao-respondidas")
    assert anonimo.status_code in (302, 303) and "login" in anonimo.headers["Location"]


def test_a_rota_nao_renova_a_sessao(s):
    marca = (datetime.now() - timedelta(minutes=50)).isoformat(timespec="seconds")
    with s["c"].session_transaction() as sessao:
        sessao["last_activity"] = marca
    for _ in range(3):
        assert s["c"].get("/whatsapp/nao-respondidas").status_code == 200
    with s["c"].session_transaction() as sessao:
        assert sessao.get("last_activity") == marca, "a pergunta do alerta renovou a sessão"
    with s["c"].session_transaction() as sessao:
        sessao["last_activity"] = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    r = s["c"].get("/whatsapp/nao-respondidas")
    assert r.status_code in (302, 303) and "login" in r.headers["Location"]


# ------------------------------------------------------------- o atalho na tela


def _atalho(html):
    achado = re.search(r'<a class="wa-atalho".*?</a>', html, re.S)
    return achado.group(0) if achado else None


def test_o_atalho_aparece_no_painel_com_o_numero(s):
    _chegar(s, "5511900000361", "oi", "wamid.at-11")
    _chegar(s, "5511900000362", "oi", "wamid.at-12")
    atalho = _atalho(s["c"].get("/").get_data(as_text=True))
    assert atalho, "o atalho não apareceu no painel"
    assert 'aria-label="WhatsApp: 2 conversas esperando resposta"' in atalho
    assert re.search(r'class="wa-atalho-alerta"[^>]*>2</span>', atalho)
    assert 'aria-hidden="true"' in atalho and "<svg" in atalho
    assert 'href="/whatsapp"' in atalho


def test_o_atalho_nao_aparece_na_tela_do_whatsapp(s):
    cid = _chegar(s, "5511900000371", "oi", "wamid.at-13")
    assert _atalho(s["c"].get("/whatsapp").get_data(as_text=True)) is None
    assert _atalho(s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)) is None


def test_o_novas_e_a_lista_parcial_nao_contam(s, monkeypatch):
    """A contagem só roda quando o `base.html` desenha o atalho: os parciais e
    as perguntas automáticas da tela não a disparam (revisão do #74)."""
    cid = _chegar(s, "5511900000381", "oi", "wamid.at-14")
    chamadas = []
    original = FILA.nao_respondidas

    def contar(con, **kw):
        chamadas.append(kw)
        return original(con, **kw)
    monkeypatch.setattr(FILA, "nao_respondidas", contar)
    assert s["c"].get(f"/whatsapp/{cid}/novas?depois=0").status_code == 200
    assert s["c"].get("/whatsapp/lista-parcial").status_code == 200
    assert chamadas == [], "o /novas ou a lista parcial contou as não respondidas"
    # e a tela comum continua contando, uma vez
    assert s["c"].get("/").status_code == 200
    assert len(chamadas) == 1


def test_com_zero_nao_ha_alerta(s):
    atalho = _atalho(s["c"].get("/").get_data(as_text=True))
    assert atalho and "wa-atalho-alerta" not in atalho
    assert 'aria-label="WhatsApp"' in atalho


def test_com_120_mostra_99_mais(s):
    with s["bd"].transaction() as con:
        bd = banco(con)
        for n in range(120):
            cid = int(bd.escrever(
                "INSERT INTO wa_conversa (wa_id, nome, status, atualizado_em, auto_ok) "
                "VALUES (%s, %s, 'aberta', %s, 0) RETURNING id",
                (f"55119{n:08d}", f"Cidade Exemplo {n:03d}", s["bd"].now()))[0]["id"])
            bd.escrever("INSERT INTO wa_mensagem (conversa_id, direcao, texto, criado_em) "
                        "VALUES (%s, 'in', 'oi', %s)", (cid, s["bd"].now()))
    atalho = _atalho(s["c"].get("/").get_data(as_text=True))
    assert re.search(r'class="wa-atalho-alerta"[^>]*>99\+</span>', atalho)
    assert 'aria-label="WhatsApp: 120 conversas esperando resposta"' in atalho


def test_o_js_so_copia_o_que_vem_pronto_e_o_css_segue_o_produtividade():
    js = (RAIZ / "static" / "whatsapp_atalho.js").read_text(encoding="utf-8")
    assert "30000" in js and "visibilityState" in js and "r.redirected" in js
    assert "innerHTML" not in js and "textContent" in js
    css = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
    assert ".wa-atalho{position:fixed;right:18px;bottom:124px" in css
    assert "@media print{.wa-atalho{display:none!important}}" in css

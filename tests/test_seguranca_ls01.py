"""Auditoria de segurança da WEB (LS01, 19/10/2026): os consertos, um a um.

Cada teste aqui FALHAVA antes do conserto — é a prova de que o furo existia,
e não só de que a rota responde. Os nomes de pessoa são fictícios (LGPD).

O QUE SE MEDIU, e por que estes três
    Desativar um usuário só barrava o próximo LOGIN: a sessão é um cookie
    assinado no navegador, e quem já estava dentro seguia dentro. E duas telas
    de configuração gravavam credencial de serviço de fora — a do WhatsApp e a
    dos robôs — para QUALQUER login, quando a regra da casa (Centrais, chave do
    Claude) é que credencial é só do ADMIN.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import robo_schema as ROBO  # noqa: E402
import wa_balcao as WA  # noqa: E402
import wa_schema as WASCH  # noqa: E402

SENHA = "Senha#12345"


def _entrar(app, usuario):
    """Cliente novo, logado como `usuario`, e o token CSRF da sessão dele."""
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/login", data={"username": usuario, "password": SENHA,
                               "csrf_token": token})
    assert r.status_code == 302, "o login de teste não entrou"
    with c.session_transaction() as s:
        return c, s["csrf_token"]


# ------------------------------------------------- a sessão de quem saiu

def test_quem_foi_desativado_perde_na_hora_a_sessao_que_ja_tinha(cg_casa):
    """O escrevente desligado com a tela aberta não lavra mais nada.

    Antes: `login_required` olhava só o cookie, e `current_user` não lia
    `active`. Desativado às 10h, ele seguia gastando selo às 16h — e cada
    clique renovava o prazo de inatividade.
    """
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    uid = db.create_user("saiu", "Escrevente Exemplo", SENHA, "USER")
    c, token = _entrar(cg_casa["app"], "saiu")
    assert c.get("/").status_code == 200, "o usuário ativo tem de entrar"

    db.set_user_active(uid, False)

    r = c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"], (
        "o usuário desativado continuou com a sessão aberta")
    # E a sessão foi limpa, não só desviada: o mesmo cookie não serve mais.
    r = c.post("/tarefas", data={"csrf_token": token, "title": "x"})
    assert r.status_code in (302, 400) and "/tarefas" not in r.headers.get("Location", "")
    with c.session_transaction() as s:
        assert "user_id" not in s


def test_o_usuario_ativo_segue_entrando_normalmente(cg_casa):
    """O conserto não pode tirar da tela quem está em dia."""
    cg_casa["db"].create_user("ativo", "Escrevente Exemplo", SENHA, "USER")
    c, _ = _entrar(cg_casa["app"], "ativo")
    for _ in range(3):
        assert c.get("/").status_code == 200


# ----------------------------------------- a credencial do WhatsApp

def _caixa_url(db) -> str:
    with db.connect() as con:
        return WA.ler_config(con, WASCH.CHAVE_CAIXA_URL)


def test_o_balcao_nao_troca_a_url_nem_o_token_do_whatsapp(cg_casa):
    """USER que grava a `caixa_url` leva o segredo dela no próximo «puxar».

    O `puxar` manda `Authorization: Bearer <caixa_segredo>` para a URL que
    estiver gravada. Aberta a qualquer login, bastava trocar a URL pela de
    fora e clicar em «puxar».
    """
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    with db.transaction() as con:
        WA.gravar_config(con, WASCH.CHAVE_CAIXA_URL, "https://caixa.exemplo.invalid/pendentes")

    c, token = _entrar(cg_casa["app"], "balcao")
    assert c.get("/whatsapp/config").status_code == 200, "ver a tela segue aberto"
    r = c.post("/whatsapp/config", data={
        "csrf_token": token, "verify_token": "", "phone_number_id": "",
        "access_token": "token-de-fora", "app_secret": "",
        "caixa_url": "https://fora.exemplo.invalid/rouba", "caixa_segredo": ""})
    assert r.status_code == 403
    assert _caixa_url(db) == "https://caixa.exemplo.invalid/pendentes"
    with db.connect() as con:
        assert WA.ler_config(con, WASCH.CHAVE_TOKEN) == ""


def test_o_admin_segue_gravando_a_configuracao_do_whatsapp(cg_casa):
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    c, token = _entrar(cg_casa["app"], "chefe")
    r = c.post("/whatsapp/config", data={
        "csrf_token": token, "verify_token": "v", "phone_number_id": "",
        "access_token": "", "app_secret": "",
        "caixa_url": "https://caixa.exemplo.invalid/nova", "caixa_segredo": ""})
    assert r.status_code == 302
    assert _caixa_url(db) == "https://caixa.exemplo.invalid/nova"


# ------------------------------------------------ a chave dos robôs

def test_o_balcao_nao_troca_a_chave_da_api_dos_robos(cg_casa):
    """USER que grava a chave do provedor desvia o que os robôs mandam."""
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    with db.transaction() as con:
        ROBO.gravar_config(con, ROBO.CHAVE_GROK, "chave-da-casa")

    c, token = _entrar(cg_casa["app"], "balcao")
    assert c.get("/robos/config").status_code == 200, "ver a tela segue aberto"
    r = c.post("/robos/config", data={"csrf_token": token,
                                      "provedor_padrao": "grok",
                                      ROBO.CHAVE_GROK: "chave-de-fora"})
    assert r.status_code == 403
    with db.connect() as con:
        assert ROBO.ler_config(con, ROBO.CHAVE_GROK) == "chave-da-casa"

    admin, token = _entrar(cg_casa["app"], "chefe")
    r = admin.post("/robos/config", data={"csrf_token": token,
                                          "provedor_padrao": "grok",
                                          ROBO.CHAVE_GROK: "chave-nova-da-casa"})
    assert r.status_code == 302
    with db.connect() as con:
        assert ROBO.ler_config(con, ROBO.CHAVE_GROK) == "chave-nova-da-casa"


# =====================================================================
# LX11 (19/10/2026): o que o LS01 só tinha relatado — «não deixar nenhuma
# pendência», decisão do oficial. Um bloco por achado, na ordem da tabela.
# =====================================================================

import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

import pytest  # noqa: E402

import database as DBMOD  # noqa: E402
import login_espera as LESP  # noqa: E402
import seguranca_web as SEGWEB  # noqa: E402
from bd_nativo import banco  # noqa: E402

OUTRA_MAQUINA = {"REMOTE_ADDR": "192.168.0.77"}


def _token_da_tela(c, caminho="/login", **kw):
    html = c.get(caminho, **kw).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _tentar(c, usuario, senha, environ_base=None):
    kw = {"environ_base": environ_base} if environ_base else {}
    token = _token_da_tela(c, **kw)
    return c.post("/login", data={"username": usuario, "password": senha,
                                  "csrf_token": token}, **kw)


def _auditoria(db, acao):
    with db.connect() as con:
        return banco(con).ler(
            "SELECT username_snapshot, details, ip_address, entity_id "
            "FROM audit_logs WHERE action=%s ORDER BY id", (acao,))


def _token_da_sessao(c):
    with c.session_transaction() as s:
        return s["csrf_token"]


# ----------------------------------------- A4: a espera depois de errar

def test_cinco_erros_seguidos_poem_o_login_em_espera_e_a_senha_certa_espera_junto(cg_casa):
    """Da rede, sem login, tentava-se senha à vontade. Depois do 5º erro a
    entrada espera — inclusive com a senha certa, senão a espera não freia
    nada — e a mensagem diz quanto tempo."""
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    c = cg_casa["app"].test_client()
    for _ in range(4):
        assert "em espera" not in _tentar(c, "balcao", "errada").get_data(as_text=True)
    quinta = _tentar(c, "balcao", "errada").get_data(as_text=True)
    assert "tente de novo em" in quinta and "segundo" in quinta

    r = _tentar(c, "balcao", SENHA)
    assert r.status_code == 429
    assert "tente de novo em" in r.get_data(as_text=True)
    with c.session_transaction() as s:
        assert "user_id" not in s
    # A tentativa em espera não conta como erro (não empurra a espera do dono).
    assert len(_auditoria(db, LESP.FALHA)) == 5
    assert len(_auditoria(db, LESP.EM_ESPERA)) == 1


def test_passada_a_espera_a_senha_certa_entra(cg_casa, monkeypatch):
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    c = cg_casa["app"].test_client()
    for _ in range(5):
        _tentar(c, "balcao", "errada")
    depois = datetime.now().replace(microsecond=0) + timedelta(seconds=31)
    monkeypatch.setattr(LESP, "agora", lambda: depois)
    assert _tentar(c, "balcao", SENHA).status_code == 302


def test_a_espera_cresce_a_cada_erro_e_nunca_passa_de_quinze_minutos():
    """30 s, 1, 2, 5, 15 min — e do 9º erro em diante fica nos 15: ninguém, nem
    o último ADMIN, fica trancado de vez."""
    t0 = datetime(2026, 10, 19, 9, 0, 0)
    falhas = [t0 + timedelta(seconds=i) for i in range(5)]
    esperado = [30, 60, 120, 300, 900, 900, 900]
    for segundos in esperado:
        fim = LESP.liberado_em(falhas, falhas[-1])
        assert fim - falhas[-1] == timedelta(seconds=segundos)
        falhas.append(fim + timedelta(seconds=1))      # erra assim que libera
    for _ in range(30):
        falhas.append(LESP.liberado_em(falhas, falhas[-1]) + timedelta(seconds=1))
    ultimo = falhas[-1]
    assert LESP.liberado_em(falhas, ultimo) - ultimo == timedelta(minutes=15)
    assert LESP.liberado_em(falhas, ultimo + timedelta(minutes=15)) is None


def test_cinco_erros_espalhados_por_mais_de_quinze_minutos_nao_poem_em_espera():
    """Quem erra uma vez por hora não é ataque: a janela é de 15 minutos."""
    t0 = datetime(2026, 10, 19, 9, 0, 0)
    falhas = [t0 + timedelta(minutes=4 * i) for i in range(5)]   # 16 minutos
    assert LESP.liberado_em(falhas, falhas[-1]) is None


def test_a_espera_e_por_usuario_e_ip_e_o_ultimo_admin_entra_de_outra_maquina(cg_casa):
    """Quem martela a senha do ADMIN de uma máquina da rede não o tranca: a
    espera é daquele usuário NAQUELA máquina."""
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    atacante = cg_casa["app"].test_client()
    for _ in range(6):
        _tentar(atacante, "chefe", "chute", environ_base=OUTRA_MAQUINA)
    assert _tentar(atacante, "chefe", SENHA,
                   environ_base=OUTRA_MAQUINA).status_code == 429
    # O mesmo ADMIN, do servidor, entra; o colega, da máquina do atacante, também.
    assert _tentar(cg_casa["app"].test_client(), "chefe", SENHA).status_code == 302
    assert _tentar(cg_casa["app"].test_client(), "balcao", SENHA,
                   environ_base=OUTRA_MAQUINA).status_code == 302


def test_o_admin_ve_quem_esta_em_espera_e_destrava_na_tela_de_usuarios(cg_casa):
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    uid = db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    c = cg_casa["app"].test_client()
    for _ in range(5):
        _tentar(c, "balcao", "errada", environ_base=OUTRA_MAQUINA)

    admin, token = _entrar(cg_casa["app"], "chefe")
    tela = admin.get("/usuarios").get_data(as_text=True)
    assert "login em espera" in tela and "192.168.0.77" in tela
    r = admin.post("/usuarios", data={"csrf_token": token, "action": "destravar",
                                      "user_id": str(uid)})
    assert r.status_code == 302
    assert "login em espera" not in admin.get("/usuarios").get_data(as_text=True)
    rastro = _auditoria(db, LESP.DESTRAVADO)
    assert len(rastro) == 1 and rastro[0]["entity_id"] == uid
    assert _tentar(c, "balcao", SENHA, environ_base=OUTRA_MAQUINA).status_code == 302


def test_a_entrada_certa_zera_os_erros_daquele_usuario_naquela_maquina(cg_casa):
    db = cg_casa["db"]
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    for _ in range(4):
        _tentar(c, "balcao", "errada")
    assert _tentar(c, "balcao", SENHA).status_code == 302
    c = cg_casa["app"].test_client()
    for _ in range(4):
        _tentar(c, "balcao", "errada")
    assert _tentar(c, "balcao", SENHA).status_code == 302, (
        "os quatro erros de antes da entrada certa não podiam somar")


# ------------------------------------ B4/B5: o login não diz quem existe

def test_a_rajada_simultanea_de_senhas_erradas_passa_so_cinco(cg_casa, monkeypatch):
    """Doze threads do waitress liam ao mesmo tempo «nenhum erro» e passavam
    juntas (revisão do LX11): a espera só valia para quem chegasse depois da
    rajada. Com a vez de tentar, as oito simultâneas fazem cinco erros e as
    outras três já encontram a espera."""
    import threading
    import time
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    original = db.authenticate

    def _devagar(*a, **k):
        time.sleep(0.3)        # o PBKDF2 mais lento abre a janela da corrida
        return original(*a, **k)
    monkeypatch.setattr(db, "authenticate", _devagar)
    clientes = []
    for _ in range(8):
        c = cg_casa["app"].test_client()
        clientes.append((c, _token_da_tela(c)))
    largada = threading.Barrier(len(clientes))
    codigos = []

    def _tentar_junto(c, token):
        largada.wait()
        r = c.post("/login", data={"username": "balcao", "password": "errada",
                                   "csrf_token": token})
        codigos.append(r.status_code)
    fios = [threading.Thread(target=_tentar_junto, args=par) for par in clientes]
    for f in fios:
        f.start()
    for f in fios:
        f.join(60)
    assert len(codigos) == 8
    assert len(_auditoria(db, LESP.FALHA)) == 5
    assert sorted(codigos).count(429) == 3


def test_a_vez_de_tentar_trava_so_a_conta_e_nao_o_banco(cg_casa, monkeypatch):
    """A vez é desta chave + IP. A trava ÚNICA da ponte fica livre durante o
    PBKDF2 — segurada ali, cada login pararia toda gravação do balcão."""
    import psycopg

    import banco_pg
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    with db.connect() as con:
        trava_unica = con._chave_trava
    vez = (LESP.ASSUNTO + LESP.chave(cg_casa["app"].secret_key, "chefe")
           + "|" + OUTRA_MAQUINA["REMOTE_ADDR"])
    visto = {}
    original = db.authenticate

    def _espiao(*a, **k):
        with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
            visto["vez_livre"] = outra.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(%s))", (vez,)).fetchone()[0]
            visto["banco_livre"] = outra.execute(
                "SELECT pg_try_advisory_xact_lock(%s)", (trava_unica,)).fetchone()[0]
        return original(*a, **k)
    monkeypatch.setattr(db, "authenticate", _espiao)
    _tentar(cg_casa["app"].test_client(), "chefe", "errada", OUTRA_MAQUINA)
    assert visto == {"vez_livre": False, "banco_livre": True}
    assert len(_auditoria(db, LESP.FALHA)) == 1


def test_o_rastro_do_erro_guarda_o_usuario_so_se_ele_existir(cg_casa):
    """Senha digitada no campo do usuário ia parar na auditoria."""
    db = cg_casa["db"]
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    _tentar(c, "MinhaSenha#Secreta9", "x")
    _tentar(c, "BALCAO", "errada")
    linhas = _auditoria(db, LESP.FALHA)
    assert [l["username_snapshot"] for l in linhas] == ["(inexistente)", "balcao"]
    assert all("MinhaSenha" not in (l["details"] or "") for l in linhas)


def test_usuario_inexistente_ou_desativado_gasta_o_mesmo_pbkdf2(cg_casa, monkeypatch):
    """«Não existe» respondia na hora; «senha errada», depois de 310 mil voltas."""
    db = cg_casa["db"]
    uid = db.create_user("saiu", "Escrevente Exemplo", SENHA, "USER")
    db.set_user_active(uid, False)
    chamadas = []
    original = DBMOD.verify_password
    monkeypatch.setattr(DBMOD, "verify_password",
                        lambda *a: chamadas.append(1) or original(*a))
    assert db.authenticate("ninguem-cadastrado", "x") is None
    assert db.authenticate("saiu", SENHA) is None
    assert len(chamadas) == 2


def test_cinco_nomes_inventados_nao_revelam_se_o_sexto_existe(cg_casa):
    """Cada nome digitado tem a sua contagem (pela `chave`), exista ou não: se
    os inexistentes dividissem uma contagem só, o sexto nome sairia em espera
    ou não conforme existisse."""
    db = cg_casa["db"]
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    for n in range(5):
        _tentar(c, f"inventado{n}", "x")
    assert _tentar(c, "inventado-6", "x").status_code == 200
    assert _tentar(c, "balcao", SENHA).status_code == 302


# ------------------------------------------- M1/B3: só caminho da casa

@pytest.mark.parametrize("proximo", [
    "//fora.exemplo/senha-expirada", "https://fora.exemplo/", "/\\fora.exemplo",
    "/\t/fora.exemplo", "javascript:alert(1)", "http:fora.exemplo"])
def test_o_login_nao_leva_quem_entrou_para_fora_da_casa(cg_casa, proximo):
    cg_casa["db"].create_user("balcao", "Escrevente Exemplo", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    token = _token_da_tela(c)
    r = c.post("/login", query_string={"next": proximo},
               data={"username": "balcao", "password": SENHA, "csrf_token": token})
    assert r.status_code == 302
    assert "fora.exemplo" not in r.headers["Location"]
    assert "javascript" not in r.headers["Location"]


def test_o_login_segue_voltando_para_a_tela_da_casa_que_pediu(cg_casa):
    cg_casa["db"].create_user("balcao", "Escrevente Exemplo", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    token = _token_da_tela(c)
    r = c.post("/login", query_string={"next": "/tarefas?situacao=ABERTAS"},
               data={"username": "balcao", "password": SENHA, "csrf_token": token})
    assert r.headers["Location"].endswith("/tarefas?situacao=ABERTAS")


def test_a_regua_do_volte_para_e_a_mesma_nas_telas():
    assert SEGWEB.destino_interno("/ri/ficha/3#atos", "/") == "/ri/ficha/3#atos"
    for ruim in ("//x.exemplo", "/\\x.exemplo", "https://x.exemplo", "x/y",
                 "/a\nb", "", None):
        assert SEGWEB.destino_interno(ruim, "/painel") == "/painel"
    assert SEGWEB.volta_do_referer("http://servidor:8765/avisos?a=1",
                                   "servidor:8765", "/") == "/avisos?a=1"
    assert SEGWEB.volta_do_referer("https://fora.exemplo/avisos",
                                   "servidor:8765", "/") == "/"


def test_o_aviso_dispensado_nao_volta_para_fora_da_casa(cg_casa):
    """B3: o `next` do formulário dos avisos ia direto ao `redirect`."""
    cg_casa["db"].create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    c, token = _entrar(cg_casa["app"], "balcao")
    r = c.post("/avisos/fechar-modal", data={"csrf_token": token,
                                            "next": "//fora.exemplo/"})
    assert r.status_code == 302
    assert "fora.exemplo" not in r.headers["Location"]


# --------------------------------------- M2: o AUDITOR vê e não grava

# As rotas que o LS01 achou só com login, menos as que ele marcou como
# intencionais (sair, ajuda, avisos, a própria verificação em duas etapas) e
# as duas de configuração que já recusam no POST por dentro (LS01, A2/A3).
# As três da leitura de documentos do RCPN (`rcpn_leitura`, `_preencher`,
# `_rascunho`) quem fecha é o LX13 (M6 do LS03, `rc_leitura_web.QUEM_LE`), mais
# estrito — o AUDITOR nem as abre —, e o teste dela mora em
# `test_seguranca_ls03.py`.
ROTAS_QUE_SO_PEDIAM_LOGIN = (
    "expedientes", "expediente_stage", "expediente_evidence", "tasks",
    "task_detail", "task_evidence", "inspection_detail", "checklists",
    "checklist_start", "checklist_run", "assets", "asset_detail", "lgpd",
    "lgpd_detail", "service_queue", "ticket_action", "ri_protocolo",
    "ri_selar_abertura", "rcpj_rtd_ato_teor", "whatsapp_puxar",
    "whatsapp_salvar_rascunho", "whatsapp_enviar", "whatsapp_resolver",
    "robos_novo", "robos_editar", "robos_exemplo_add", "robos_exemplo_apagar",
    "robos_testar", "ri_retificacao_item", "ri_retificacao_confrontante",
    "ri_retificacao_notificar", "ri_retificacao_resposta",
    "rcpn_papel_inutilizar", "gestor_envios_registrar",
    "gestor_revisao_conferida", "gestor_leitura_conferida")


def _url_de_exemplo(app, endpoint):
    regra = next(r for r in app.url_map.iter_rules() if r.endpoint == endpoint)
    valores = {nome: (1 if regra._converters[nome].__class__.__name__ == "IntegerConverter"
                      else "concluir") for nome in regra.arguments}
    with app.test_request_context():
        from flask import url_for
        return url_for(endpoint, **valores)


def test_o_auditor_leva_403_no_post_das_rotas_que_so_pediam_login(cg_casa):
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("fiscal", "Auditor Exemplo", SENHA, "AUDITOR")
    c, token = _entrar(cg_casa["app"], "fiscal")
    gravaram = []
    for endpoint in ROTAS_QUE_SO_PEDIAM_LOGIN:
        url = _url_de_exemplo(cg_casa["app"], endpoint)
        if c.post(url, data={"csrf_token": token}).status_code != 403:
            gravaram.append(endpoint)
    assert gravaram == []


def test_o_auditor_segue_vendo_as_telas_e_o_balcao_segue_gravando(cg_casa):
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    db.create_user("fiscal", "Auditor Exemplo", SENHA, "AUDITOR")
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    fiscal, _ = _entrar(cg_casa["app"], "fiscal")
    for tela in ("/tarefas", "/expedientes", "/checklists", "/ti", "/lgpd", "/atendimento"):
        assert fiscal.get(tela).status_code == 200, tela
    balcao, token = _entrar(cg_casa["app"], "balcao")
    r = balcao.post("/tarefas", data={"csrf_token": token, "title": "Conferir o livro"})
    assert r.status_code != 403


# ------------------------------- M3/M4: a senha nova derruba as sessões

def test_redefinir_a_senha_derruba_a_sessao_que_ja_estava_aberta(cg_casa):
    """A senha vazou, o ADMIN a redefiniu — e quem entrou com ela continuava."""
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    uid = db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    balcao, _ = _entrar(cg_casa["app"], "balcao")
    assert balcao.get("/").status_code == 200
    admin, token = _entrar(cg_casa["app"], "chefe")
    admin.post("/usuarios", data={"csrf_token": token, "action": "reset",
                                  "user_id": str(uid), "new_password": "Outra#Senha77"})
    r = balcao.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    with balcao.session_transaction() as s:
        assert "user_id" not in s
    assert admin.get("/").status_code == 200, "o ADMIN que redefiniu segue dentro"


def test_trocar_a_propria_senha_mantem_esta_sessao_e_derruba_as_outras(cg_casa):
    db = cg_casa["db"]
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    aqui, token = _entrar(cg_casa["app"], "balcao")
    la, _ = _entrar(cg_casa["app"], "balcao")
    r = aqui.post("/conta/senha", data={"csrf_token": token, "senha_atual": SENHA,
                                        "nova_senha": "Nova#Senha2026",
                                        "confirmacao": "Nova#Senha2026"})
    assert r.status_code == 302 and "/conta/senha" not in r.headers["Location"]
    assert aqui.get("/").status_code == 200
    assert la.get("/").status_code == 302
    assert db.authenticate("balcao", "Nova#Senha2026")
    assert not db.authenticate("balcao", SENHA)
    assert len(_auditoria(db, "PASSWORD_CHANGED")) == 1


def test_a_troca_de_senha_confere_a_atual_a_repeticao_e_a_forca(cg_casa):
    db = cg_casa["db"]
    db.create_user("fiscal", "Auditor Exemplo", SENHA, "AUDITOR")
    db.set_settings({"password_min_length": "10"})
    c, token = _entrar(cg_casa["app"], "fiscal")
    tela = c.get("/conta/senha").get_data(as_text=True)
    assert 'name="senha_atual"' in tela and 'name="confirmacao"' in tela
    assert "/conta/senha" in c.get("/").get_data(as_text=True), "falta o link no menu"
    casos = [({"senha_atual": "errada", "nova_senha": "Boa#Senha2026",
               "confirmacao": "Boa#Senha2026"}, "senha atual não confere"),
             ({"senha_atual": SENHA, "nova_senha": "Boa#Senha2026",
               "confirmacao": "Outra#Coisa"}, "não conferem"),
             ({"senha_atual": SENHA, "nova_senha": "curta1", "confirmacao": "curta1"},
              "pelo menos 10")]
    for dados, recado in casos:
        html = c.post("/conta/senha", data={"csrf_token": token, **dados},
                      follow_redirects=True).get_data(as_text=True)
        assert recado in html, recado
    assert db.authenticate("fiscal", SENHA), "nada podia ter mudado"


def test_errar_a_senha_atual_na_troca_conta_na_mesma_espera_do_login(cg_casa):
    """A sessão esquecida aberta no balcão não vira lugar de chutar senha."""
    db = cg_casa["db"]
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    c, token = _entrar(cg_casa["app"], "balcao")
    for _ in range(5):
        c.post("/conta/senha", data={"csrf_token": token, "senha_atual": "chute",
                                     "nova_senha": "Nova#Senha2026",
                                     "confirmacao": "Nova#Senha2026"})
    html = c.post("/conta/senha", data={"csrf_token": token, "senha_atual": SENHA,
                                        "nova_senha": "Nova#Senha2026",
                                        "confirmacao": "Nova#Senha2026"},
                  follow_redirects=True).get_data(as_text=True)
    assert "tente de novo em" in html
    assert db.authenticate("balcao", SENHA)


# ------------------------------------------------ M5: o secret.key
#
# Quem faz é o `permissao_local` (LX14, B6 do LS03), que fechou o mesmo achado
# para todos os segredos da pasta; o `icacls` do Windows tem os testes dele em
# `test_backup.py`. Aqui fica a prova de que a SUBIDA o aplica ao `secret.key`.

@pytest.mark.skipif(os.name == "nt", reason="a régua do POSIX; o Windows é o icacls")
def test_o_secret_key_fica_so_para_o_dono_inclusive_o_que_ja_existia(tmp_path):
    from app import create_app
    dados = tmp_path / "dados"
    dados.mkdir()
    chave = dados / "secret.key"
    chave.write_text("chave-de-exemplo-ja-gravada", encoding="utf-8")
    chave.chmod(0o644)
    app = create_app({"DATA_DIR": str(dados)})
    assert (chave.stat().st_mode & 0o777) == 0o600
    assert app.secret_key == "chave-de-exemplo-ja-gravada"


def test_a_permissao_que_nao_se_ajusta_vira_aviso_e_o_servidor_sobe(tmp_path, monkeypatch, caplog):
    import permissao_local as PERM
    from app import create_app

    def _negado(*_a, **_k):
        raise PermissionError("negado")
    monkeypatch.setattr(PERM.os, "chmod", _negado)
    monkeypatch.setattr(PERM, "_e_windows", lambda: False)
    dados = tmp_path / "dados"
    dados.mkdir()
    with caplog.at_level(logging.WARNING, logger="cartorio.permissoes"):
        app = create_app({"DATA_DIR": str(dados)})
    assert app.secret_key
    assert "secret.key" in caplog.text and "PERMISSAO NAO AJUSTADA" in caplog.text


# ----------------------------------------- M6: o modo de teste do webhook

def _webhook(app, meta_id):
    corpo = {"entry": [{"changes": [{"value": {
        "contacts": [{"profile": {"name": "Pessoa Exemplo"}, "wa_id": "5500000000002"}],
        "messages": [{"from": "5500000000002", "id": meta_id, "type": "text",
                      "text": {"body": "oi"}}]}}]}]}
    return app.test_client().post(
        "/whatsapp/webhook", data=json.dumps(corpo), content_type="application/json",
        headers={"X-Wa-Test": "1"}, environ_base={"REMOTE_ADDR": "127.0.0.1"})


def test_o_x_wa_test_e_recusado_com_o_modo_de_teste_desligado_de_fabrica(cg_casa):
    """Sem `app_secret` (o de fábrica), o cabeçalho sozinho punha conversa
    forjada na fila do balcão."""
    cg_casa["db"].create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")  # sai do /setup
    assert _webhook(cg_casa["app"], "wamid.lx11-a").status_code == 403
    with cg_casa["db"].connect() as con:
        assert banco(con).valor("SELECT count(*) AS n FROM wa_mensagem") == 0


def test_o_admin_liga_o_modo_de_teste_e_so_entao_o_x_wa_test_entra(cg_casa):
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    c, token = _entrar(cg_casa["app"], "chefe")
    campos = {"csrf_token": token, "verify_token": "", "phone_number_id": "",
              "access_token": "", "app_secret": "", "caixa_url": "", "caixa_segredo": ""}
    c.post("/whatsapp/config", data={**campos, "modo_teste": "1"})
    assert 'name="modo_teste" value="1"\n             checked' in c.get(
        "/whatsapp/config").get_data(as_text=True)
    assert _webhook(cg_casa["app"], "wamid.lx11-b").status_code == 200
    c.post("/whatsapp/config", data=campos)          # desmarcado = desligado
    assert _webhook(cg_casa["app"], "wamid.lx11-c").status_code == 403


# ----------------------------------------- M8: GET que gravava vira POST

GET_QUE_GRAVAVAM = (
    "/rcpn/ato/1/etiqueta",
    "/notas/reconhecimento/1/termo-comparecimento/1",
    "/notas/reconhecimento/1/etiqueta",
    "/notas/autenticacao/1/etiqueta",
    "/rcpj-rtd/ato/1/etiqueta",
    "/caixa/protocolos/1/recepcao",
)


@pytest.mark.parametrize("url", GET_QUE_GRAVAVAM)
def test_a_rota_que_grava_nao_aceita_get_nem_post_sem_o_token(cg_casa, url):
    """Um link ou `<img>` vindo de fora gravava em nome de quem estava logado."""
    cg_casa["db"].create_user("balcao", "Escrevente Exemplo", SENHA, "ADMIN")
    c, _ = _entrar(cg_casa["app"], "balcao")
    assert c.get(url).status_code == 405
    assert c.post(url).status_code == 400


def test_as_telas_mandam_as_seis_por_formulario_com_o_token():
    """O botão de cada uma é `<form method="post">` com o token — e nenhum
    `href` sobrou apontando para elas."""
    tela = {
        "atrib_rcpn_ficha.html": ["rcpn_ato_etiqueta"],
        "notas_reconhecimento_ver.html": ["notas_reconhecimento_termo_comparecimento",
                                          "notas_reconhecimento_etiqueta"],
        "notas_reconhecimentos.html": ["notas_reconhecimento_etiqueta"],
        "notas_autenticacao.html": ["notas_autenticacao_etiqueta"],
        "atrib_registro_ficha.html": ["rcpj_rtd_etiqueta"],
        "rcpj_rtd_titulo.html": ["rcpj_rtd_etiqueta"],
        "caixa_protocolo.html": ["caixa_recepcao"],
    }
    for arquivo, rotas in tela.items():
        texto = (RAIZ / "templates" / arquivo).read_text(encoding="utf-8")
        for rota in rotas:
            assert not re.search(r"href=\"\{\{\s*url_for\('" + rota, texto), (arquivo, rota)
            achado = re.search(r'<form method="post"[^>]*?(?:\n[^>]*?)*action="\{\{ url_for\(\''
                               + rota + r"'[^>]*>\s*<input type=\"hidden\" name=\"csrf_token\"",
                               texto)
            assert achado, (arquivo, rota)


# ----------------------------------------------- B1: os cabeçalhos

def test_toda_resposta_leva_os_cabecalhos_de_seguranca(cg_casa):
    r = cg_casa["app"].test_client().get("/login")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "same-origin"
    assert "frame-ancestors 'self'" in r.headers["Content-Security-Policy-Report-Only"]
    assert "Content-Security-Policy" not in r.headers, "CSP que bloqueia quebraria tela"


# ------------------------------------- B2: a exceção não vai para a tela

def test_a_excecao_inesperada_vai_para_o_log_e_nao_para_a_tela(cg_casa, monkeypatch, caplog):
    import gestor_cargas_ri as GCR

    def _quebra(*_a, **_k):
        raise RuntimeError('relation "ri_tabela_interna" senha=segredo-do-banco')
    monkeypatch.setattr(GCR, "situacao_da_imagem", _quebra)
    olhar = cg_casa["app"].jinja_env.globals["situacao_da_imagem_onr"]
    with caplog.at_level(logging.ERROR, logger="cartorio.tela"):
        with cg_casa["app"].test_request_context():
            motivo = olhar(1)["motivo"]
    assert "segredo-do-banco" not in motivo and "ri_tabela_interna" not in motivo
    assert "segredo-do-banco" in caplog.text


def test_o_erro_do_modelo_que_a_pessoa_escreveu_continua_na_tela():
    from jinja2 import Environment, TemplateSyntaxError
    try:
        Environment().from_string("{{ nome ")
    except TemplateSyntaxError as erro:
        assert "unexpected end of template" in SEGWEB.erro_do_modelo(erro, "teste")
    assert "senha" not in SEGWEB.erro_do_modelo(OSError("senha=xyz"), "teste")


# ------------------------------------------- B7: o prazo absoluto

def test_a_sessao_acaba_doze_horas_depois_da_entrada_mesmo_com_uso(cg_casa):
    """O prazo de inatividade se renova a cada clique; o absoluto, não."""
    db = cg_casa["db"]
    db.create_user("balcao", "Escrevente Exemplo", SENHA, "USER")
    db.set_settings({"session_timeout_minutes": "1440"})
    c, _ = _entrar(cg_casa["app"], "balcao")
    with c.session_transaction() as s:
        s["inicio"] = (datetime.now() - timedelta(hours=12, minutes=1)).isoformat(timespec="seconds")
    r = c.get("/", follow_redirects=True)
    assert "prazo de 12 horas" in r.get_data(as_text=True)
    with c.session_transaction() as s:
        assert "user_id" not in s


def test_o_prazo_absoluto_e_configuravel(cg_casa):
    db = cg_casa["db"]
    db.create_user("chefe", "Chefe Exemplo", SENHA, "ADMIN")
    c, _ = _entrar(cg_casa["app"], "chefe")
    assert 'name="session_absolute_hours"' in c.get("/configuracoes").get_data(as_text=True)
    db.set_settings({"session_absolute_hours": "24"})
    with c.session_transaction() as s:
        s["inicio"] = (datetime.now() - timedelta(hours=13)).isoformat(timespec="seconds")
    assert c.get("/").status_code == 200


# ---------------------------------- M7/B6: o que fica com o servidor

def test_o_que_o_servidor_configura_fica_escrito():
    """TLS e o /saude não mudam no código: a casa precisa saber o porquê."""
    texto = (RAIZ / "docs" / "SEGURANCA_REDE.md").read_text(encoding="utf-8")
    for assunto in ("HTTPS", "SESSION_COOKIE_SECURE", "/saude", "localizador"):
        assert assunto in texto, assunto

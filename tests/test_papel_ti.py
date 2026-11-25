# -*- coding: utf-8 -*-
"""O PAPEL TI — tudo do ADMIN, menos selar atos (T015, decisão do titular de 24/11/2026).

O que se prova aqui:
  - a régua (`papeis.py`): equivalência, selo, escalada e o papel da auditoria;
  - o TI abre telas que são só do ADMIN (Usuários, Configurações, Projetos,
    Auditoria) e tem o menu do ADMIN;
  - o TI é recusado em CADA caminho do selo — pela rota e pela chamada direta
    da função do selo (`ato_selado`, `selador_cliente`);
  - o TI não promove ninguém a ADMIN, não troca o próprio papel e não mexe na
    conta de um ADMIN;
  - os outros papéis continuam como eram.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager

import pytest

import ato_selado as AS
import navegacao as NAV
import papeis as PAP
import selador_cliente as CL
import selo_robo as SR

SENHA = "Senha#12345"
AGORA = "2026-11-24T10:00:00"


# --------------------------------------------------------------- ajudantes


def _token(c) -> str:
    with c.session_transaction() as s:
        return s.get("csrf_token") or ""


def _login(app, usuario):
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/login", data={"username": usuario, "password": SENHA, "csrf_token": tok},
               follow_redirects=True)
    assert r.status_code == 200
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    ids = {
        "oficial": db.create_user("oficial", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN"),
        # um ADMIN que não é o titular: o menu do TI é o dele (o do titular tem
        # o que é só do titular — livro diário, carnê-leão)
        "admin2": db.create_user("substituta", "SARA EXEMPLO SUBSTITUTA", SENHA, "ADMIN"),
        "ti": db.create_user("suporte.ti", "TADEU EXEMPLO DE TI", SENHA, "TI"),
        "gerente": db.create_user("gerente", "GINA EXEMPLO GERENTE", SENHA, "MANAGER"),
        "escrevente": db.create_user("escrevente", "ELIAS EXEMPLO ESCREVENTE", SENHA, "USER"),
        "auditor": db.create_user("auditor", "AUREA EXEMPLO AUDITORA", SENHA, "AUDITOR"),
    }
    cg_casa["ids"] = ids
    return cg_casa


@contextmanager
def _sessao(casa, quem):
    """Uma requisição com `quem` logado — para chamar a função do selo direto."""
    app = casa["app"]
    with app.test_request_context("/"):
        from flask import session
        session["user_id"] = int(casa["ids"][quem])
        yield app


def _url_ficticia(app, regra) -> str:
    valores = {}
    for arg in regra.arguments:
        conv = regra._converters.get(arg)
        valores[arg] = 1 if conv is not None and conv.__class__.__name__ == "IntegerConverter" else "nt_atos"
    with app.test_request_context("/"):
        from flask import url_for
        return url_for(regra.endpoint, **valores)


# ------------------------------------------------------------------ a régua


def test_a_regua_do_ti_equivale_ao_admin_e_nao_sela():
    from app import ROLES
    assert list(PAP.PAPEIS) == ROLES
    assert PAP.TI in PAP.PAPEIS and PAP.ROTULOS["TI"].startswith("TI")
    assert PAP.papel_efetivo("TI") == "ADMIN"
    assert PAP.equivale_a("TI", "ADMIN")
    assert PAP.equivale_a({"role": "TI"}, ("ADMIN", "MANAGER"))
    assert not PAP.equivale_a("TI", "MANAGER", "USER")
    assert not PAP.pode_selar("TI") and not PAP.pode_selar({"role": "TI"})
    efetivo = PAP.usuario_efetivo({"id": 9, "role": "TI", "username": "t"})
    assert efetivo["role"] == "ADMIN" and efetivo["papel_real"] == "TI"
    assert PAP.papel_de(efetivo) == "TI" and not PAP.pode_selar(efetivo)
    with pytest.raises(PAP.TINaoSela):
        AS.barrar_quem_nao_sela("TI")


def test_os_outros_papeis_nao_mudam_na_regua():
    for papel in ("ADMIN", "MANAGER", "USER", "AUDITOR"):
        linha = {"id": 1, "role": papel}
        assert PAP.usuario_efetivo(linha) is linha
        assert PAP.papel_efetivo(papel) == papel
        assert PAP.pode_selar(papel)
        AS.barrar_quem_nao_sela(papel)
    assert not PAP.equivale_a("MANAGER", "ADMIN")
    assert not PAP.equivale_a("USER", "ADMIN", "MANAGER")
    assert not PAP.equivale_a("AUDITOR", "ADMIN", "MANAGER", "USER")
    assert not PAP.equivale_a(None, "ADMIN") and not PAP.equivale_a("", "ADMIN")
    # fora de requisição a régua não decide (rotina, teste de unidade)
    assert PAP.sessao_pode_selar() is True
    AS.barrar_quem_nao_sela()


def test_a_trava_de_escalada_na_regua():
    ti = {"id": 2, "role": "ADMIN", "papel_real": "TI"}
    admin = {"id": 1, "role": "ADMIN"}
    usuario = {"id": 3, "role": "USER"}
    assert PAP.recusa_de_papel(ti, papel_novo="ADMIN")
    assert PAP.recusa_de_papel(ti, alvo=usuario, papel_novo="ADMIN")
    assert PAP.recusa_de_papel(ti, alvo={"id": 2, "role": "TI"}, papel_novo="USER")
    assert PAP.recusa_de_papel(ti, alvo=admin, mexe_na_conta=True)
    assert PAP.recusa_de_papel(ti, papel_novo="TI") is None
    assert PAP.recusa_de_papel(ti, alvo=usuario, papel_novo="TI") is None
    assert PAP.recusa_de_papel(ti, alvo={"id": 2, "role": "TI"}, papel_novo="TI") is None
    assert PAP.recusa_de_papel(ti, alvo=usuario, mexe_na_conta=True) is None
    # o ADMIN segue podendo tudo, inclusive dar ADMIN
    assert PAP.recusa_de_papel(admin, alvo=usuario, papel_novo="ADMIN") is None


def test_rota_sela_reconhece_os_caminhos_do_selo():
    assert PAP.rota_sela("rcpn_ato_selar")
    assert PAP.rota_sela("notas_autenticacao_selo")
    assert PAP.rota_sela("caixa", {"selo": "AUTENT0000001"})
    assert not PAP.rota_sela("caixa", {"selo": "  "})
    assert not PAP.rota_sela("selador_config", {})
    assert not PAP.rota_sela("selos_emitidos_lista")


# -------------------------------------------------------- o cadastro e o banco


def test_o_banco_aceita_ti_e_robo_nao_e_ti(casa):
    db = casa["db"]
    assert db.get_user(casa["ids"]["ti"])["role"] == "TI"
    with pytest.raises(ValueError):
        db.create_user("robo.ti", "ROBO DE TI", SENHA, "TI", eh_robo=1)


def test_a_tela_de_usuarios_mostra_o_ti_com_rotulo(casa):
    c = _login(casa["app"], "oficial")
    html = c.get("/usuarios").get_data(as_text=True)
    assert PAP.ROTULOS["TI"] in html
    assert 'value="TI"' in html and 'value="ADMIN"' in html


# --------------------------------------------------------- o acesso do ADMIN


@pytest.mark.parametrize("tela", ["/usuarios", "/configuracoes", "/desenvolvimento/projetos",
                                  "/auditoria", "/selador"])
def test_o_ti_abre_as_telas_so_do_admin(casa, tela):
    c = _login(casa["app"], "suporte.ti")
    assert c.get(tela).status_code == 200, tela
    # e os outros papéis seguem barrados onde eram
    e = _login(casa["app"], "escrevente")
    assert e.get(tela).status_code in (302, 403), tela


def test_o_cabecalho_mostra_ti_e_nao_admin(casa):
    c = _login(casa["app"], "suporte.ti")
    html = c.get("/usuarios").get_data(as_text=True)
    assert re.search(r"<small>\s*TI\s*·", html), "o cabeçalho tem de dizer TI"


def test_o_papel_que_decide_e_o_que_se_grava(casa):
    with _sessao(casa, "ti") as app:
        assert app.extensions["usuario_papel"]() == "ADMIN"
        assert app.extensions["usuario_papel_real"]() == "TI"
        assert app.extensions["current_user"]()["papel_real"] == "TI"
        assert PAP.para_o_registro("ADMIN") == "TI"
        assert PAP.para_o_registro("MANAGER") == "MANAGER"
    with _sessao(casa, "oficial") as app:
        assert app.extensions["usuario_papel_real"]() == "ADMIN"
        assert PAP.para_o_registro("ADMIN") == "ADMIN"


def test_o_menu_do_ti_e_o_do_admin(casa):
    assert NAV.entradas("TI") == NAV.entradas("ADMIN")
    with _sessao(casa, "ti") as app:
        ctx: dict = {}
        app.update_template_context(ctx)
        papel = app.extensions["usuario_papel"]()
        assert papel == "ADMIN"
        assert ctx["nav_da_tela"](papel="TI") == ctx["nav_da_tela"](papel="ADMIN")
    # o menu como o navegador recebe: os mesmos destinos para os dois
    def destinos(usuario):
        html = _login(casa["app"], usuario).get("/").get_data(as_text=True)
        return set(re.findall(r'href="(/[^"#?]*)', html))
    ti, admin = destinos("suporte.ti"), destinos("substituta")
    assert ti == admin
    # o que é só do titular continua só dele: nem o ADMIN substituto nem o TI
    titular = destinos("oficial")
    assert titular >= admin


def test_o_menu_dos_outros_papeis_nao_ganhou_nada():
    for papel in ("MANAGER", "USER", "AUDITOR"):
        assert NAV.entradas(papel) != NAV.entradas("ADMIN")
        assert len(NAV.entradas(papel)) < len(NAV.entradas("ADMIN"))


def test_o_segundo_fator_exigido_do_admin_vale_para_o_ti(casa):
    import dois_fatores as DF
    import dois_fatores_web as DFW
    assert "TI" in DFW.PAPEIS
    db = casa["db"]
    db.set_settings({DF.CHAVE_DA_EXIGENCIA: '["ADMIN"]'})
    assert DF.exigido(db.get_setting, "TI")
    assert not DF.exigido(db.get_setting, "USER")
    db.set_settings({DF.CHAVE_DA_EXIGENCIA: '["TI"]'})
    assert DF.exigido(db.get_setting, "TI") and not DF.exigido(db.get_setting, "ADMIN")


# ----------------------------------------------------------------- o selo


def test_o_ti_nao_sela_pela_chamada_direta_das_funcoes_do_selo(casa):
    db, dados = casa["db"], casa["dados"]
    with _sessao(casa, "ti"):
        assert not SR.pode_selar_automatico()
        assert SR.exige_humano_para_selar()
        assert "TI não sela" in SR.recado_pendente_selo()
        with pytest.raises(AS.SeloVedadoAoTI):
            AS.barrar_quem_nao_sela()
        with pytest.raises(PAP.TINaoSela):
            AS.obter_selo(db, dados, caminho="/selo/notas/qualquer", dados={},
                          referencia="nt_atos:1", atribuicao="NOTAS", agora=AGORA,
                          cns="", usuario="TADEU EXEMPLO DE TI", tabela="nt_atos", ato_id=1)
        with db.connect() as con:
            with pytest.raises(AS.SeloVedadoAoTI):
                AS.registrar_selo_obtido_a_mao(con, "AUTENT000000XXXXXXXXXXXXXXXX",
                                               tabela="nt_atos", ato_id=1, atribuicao="NOTAS",
                                               agora=AGORA, cns="")
            with pytest.raises(AS.SeloVedadoAoTI):
                AS.vincular_ao_ato(con, "AUTENT000000XXXXXXXXXXXXXXXX", tabela="nt_atos",
                                   ato_id=1, agora=AGORA)
            with pytest.raises(PAP.TINaoSela):
                CL.selar(con, dados, "/selo/notas/qualquer", {}, referencia="nt_atos:1",
                         atribuicao="NOTAS", agora=AGORA, cns="")
            with pytest.raises(PAP.TINaoSela):
                CL.vincular(con, "AUTENT000000XXXXXXXXXXXXXXXX", tabela="nt_atos",
                            ato_id=1, agora=AGORA)
            # a liberação do ADMIN e as travas do selo pago: o papel que vem é o
            # EFETIVO («ADMIN»), e a sessão diz TI
            with pytest.raises(AS.SeloVedadoAoTI):
                AS.liberar_selo(con, tabela="nt_atos", ato_id=1,
                                justificativa="liberação de teste do papel TI",
                                papel="ADMIN", usuario="TADEU", usuario_id=1, agora=AGORA)
            with pytest.raises(AS.SeloVedadoAoTI):
                AS.ligar_trava(con, ligada=False, papel="ADMIN", usuario="TADEU",
                               usuario_id=1, justificativa="desligar a trava no teste do TI",
                               agora=AGORA)
            with pytest.raises(AS.SeloVedadoAoTI):
                AS.ligar_selo_pago_no_onr(con, ligado=True, papel="ADMIN", usuario="TADEU",
                                          usuario_id=1, justificativa="ligar o selo pago no teste",
                                          agora=AGORA)
        r = AS.selar_o_ato_lavrado(db, dados, tabela="nt_atos", ato_id=1, tipo="ESCRITURA",
                                   atribuicao="NOTAS", agora=AGORA, cns="",
                                   caminho="/selo/notas/qualquer", usuario="TADEU EXEMPLO DE TI")
        assert r["selado"] is False and r["motivo"] == PAP.MSG_NAO_SELA


def test_os_outros_papeis_passam_pela_trava_do_ti(casa):
    for quem in ("oficial", "gerente", "escrevente"):
        with _sessao(casa, quem):
            AS.barrar_quem_nao_sela()
            assert SR.papel_sela()
            assert not SR.exige_humano_para_selar()
            assert SR.recado_pendente_selo() == SR.MSG_PENDENTE_SELO


def test_o_ti_recebe_403_em_toda_rota_que_sela(casa):
    app = casa["app"]
    rotas = [r for r in app.url_map.iter_rules()
             if "POST" in r.methods and PAP.rota_sela(r.endpoint)]
    assert len(rotas) >= 25, [r.endpoint for r in rotas]
    ti = _login(app, "suporte.ti")
    tok = _token(ti)
    recusadas = []
    for regra in rotas:
        url = _url_ficticia(app, regra)
        r = ti.post(url, data={"csrf_token": tok})
        assert r.status_code == 403, (regra.endpoint, r.status_code)
        assert PAP.MSG_NAO_SELA in r.get_data(as_text=True), regra.endpoint
        recusadas.append(regra.endpoint)
    for nome in ("rcpn_ato_selar", "notas_cartao_selar", "ri_selar_ato", "ri_certidao_selar",
                 "protesto_selar_pendentes", "livro3_selar_ato", "onr_auto_selar",
                 "notas_autenticacao_selo", "apostila_selo", "notas_veiculo_comunicar",
                 "rcpj_rtd_livro_contabil_autenticar", "protesto_selo_que_faltou",
                 "rcpn_certidao_eletronica_selo", "rcpj_rtd_etiquetas_selos_externos"):
        assert nome in recusadas, nome


def test_o_selo_digitado_tambem_e_recusado_ao_ti(casa):
    app = casa["app"]
    ti = _login(app, "suporte.ti")
    r = ti.post("/notas/reconhecimento/1", data={"csrf_token": _token(ti), "acao": "selo",
                                                 "selo": "RECFIR000000XXXXXXXXXXXXXXXX"})
    assert r.status_code == 403 and PAP.MSG_NAO_SELA in r.get_data(as_text=True)
    # sem selo digitado, o mesmo POST passa pela rede (a tela decide o resto)
    r = ti.post("/notas/reconhecimento/1", data={"csrf_token": _token(ti), "acao": "outra"})
    assert r.status_code != 403


def test_a_liberacao_do_selo_pela_tela_recusa_o_ti(casa):
    app = casa["app"]
    ti = _login(app, "suporte.ti")
    r = ti.post("/selo/cobertura/liberar",
                data={"csrf_token": _token(ti), "tabela": "nt_atos", "ato_id": "1",
                      "justificativa": "liberação de teste do papel TI na tela"},
                follow_redirects=True)
    assert PAP.MSG_NAO_SELA in r.get_data(as_text=True)
    with casa["db"].connect() as con:
        from bd_nativo import banco
        assert not banco(con).ler("SELECT id FROM cx_selo_liberacoes")


def test_a_excecao_do_selo_que_escapa_vira_403(casa):
    with _sessao(casa, "ti") as app:
        manejador = app.error_handler_spec[None][None].get(PAP.TINaoSela)
        assert manejador is not None
        corpo, codigo = manejador(PAP.TINaoSela())
        assert codigo == 403 and PAP.MSG_NAO_SELA in corpo


def test_a_tela_do_ti_carrega_a_trava_dos_botoes(casa):
    ti = _login(casa["app"], "suporte.ti").get("/usuarios").get_data(as_text=True)
    adm = _login(casa["app"], "oficial").get("/usuarios").get_data(as_text=True)
    assert "ti_nao_sela.js" in ti and "ti_nao_sela.js" not in adm


def test_o_ti_lavra_e_o_ato_fica_pendente_de_selo(casa):
    """A lavratura que sela ao salvar: o ato do TI fica lavrado, sem selo, e o
    aparelho não é chamado. O ADMIN, depois, sela pelo botão (regressão)."""
    from tests.selador_de_bancada import ligar_o_selador, tem_cryptography
    if not tem_cryptography():
        pytest.skip("cryptography")
    app = casa["app"]
    ti = _login(app, "suporte.ti")
    with ligar_o_selador(casa) as aparelho:
        antes = len(aparelho.selos_por_sid)
        html = ti.get("/notas/cartoes").get_data(as_text=True)
        assert re.search(r'name="csrf_token"', html)
        r = ti.post("/notas/cartoes", data={"acao": "novo", "nome": "MARIA DO TI CARTAO",
                                            "documento": "00000001082",
                                            "csrf_token": _token(ti)}, follow_redirects=True)
        assert r.status_code == 200
        assert "o papel TI não sela" in r.get_data(as_text=True)
        assert len(aparelho.selos_por_sid) == antes, "o TI não pode pedir selo"
        con = sqlite3.connect(casa["banco"])
        con.row_factory = sqlite3.Row
        linha = con.execute("SELECT id, selo_abertura FROM nt_cartoes WHERE nome=?",
                            ("MARIA DO TI CARTAO",)).fetchone()
        con.close()
        assert linha is not None and not (linha["selo_abertura"] or "").strip()
        r403 = ti.post(f"/notas/cartoes/{linha['id']}/selar", data={"csrf_token": _token(ti)})
        assert r403.status_code == 403
        assert len(aparelho.selos_por_sid) == antes


# ------------------------------------------------------------- sem escalada


def _papel(casa, uid):
    return casa["db"].get_user(uid)["role"]


def test_o_ti_nao_cria_admin_mas_cria_ti_e_os_outros(casa):
    ti = _login(casa["app"], "suporte.ti")
    html = ti.get("/usuarios").get_data(as_text=True)
    assert 'value="ADMIN"' not in html.split("Novo usuário", 1)[1].split("</form>", 1)[0]
    base = {"action": "create", "password": "Outra#Senha123"}
    r = ti.post("/usuarios", data={**base, "csrf_token": _token(ti), "username": "novo.admin",
                                   "full_name": "NOVO ADMIN DE TESTE", "role": "ADMIN"},
                follow_redirects=True)
    assert "não dá o papel ADMIN" in r.get_data(as_text=True)
    nomes = {u["username"] for u in casa["db"].list_users()}
    assert "novo.admin" not in nomes
    for papel, login in (("TI", "outro.ti"), ("USER", "novo.escrevente")):
        ti.post("/usuarios", data={**base, "csrf_token": _token(ti), "username": login,
                                   "full_name": f"NOVO {papel} DE TESTE", "role": papel})
    papeis = {u["username"]: u["role"] for u in casa["db"].list_users()}
    assert papeis.get("outro.ti") == "TI" and papeis.get("novo.escrevente") == "USER"


def test_o_ti_nao_promove_a_admin_nem_troca_o_proprio_papel(casa):
    ids = casa["ids"]
    ti = _login(casa["app"], "suporte.ti")

    def editar(uid, username, nome, papel):
        return ti.post("/usuarios", data={"action": "editar", "csrf_token": _token(ti),
                                          "user_id": str(uid), "username": username,
                                          "full_name": nome, "role": papel},
                       follow_redirects=True).get_data(as_text=True)

    assert "não dá o papel ADMIN" in editar(ids["escrevente"], "escrevente",
                                             "ELIAS EXEMPLO ESCREVENTE", "ADMIN")
    assert _papel(casa, ids["escrevente"]) == "USER"
    assert "não dá o papel ADMIN" in editar(ids["ti"], "suporte.ti", "TADEU EXEMPLO DE TI",
                                             "ADMIN")
    assert "não troca o próprio papel" in editar(ids["ti"], "suporte.ti",
                                                 "TADEU EXEMPLO DE TI", "USER")
    assert _papel(casa, ids["ti"]) == "TI"
    # corrigir o próprio nome, com o papel de sempre, continua
    editar(ids["ti"], "suporte.ti", "TADEU EXEMPLO DE TI CORRIGIDO", "TI")
    assert casa["db"].get_user(ids["ti"])["full_name"] == "TADEU EXEMPLO DE TI CORRIGIDO"
    # e dar TI a um escrevente é dele
    editar(ids["escrevente"], "escrevente", "ELIAS EXEMPLO ESCREVENTE", "TI")
    assert _papel(casa, ids["escrevente"]) == "TI"
    # a recusa fica na auditoria com o papel do autor
    with casa["db"].connect() as con:
        from bd_nativo import banco
        linhas = banco(con).ler("SELECT details FROM audit_logs WHERE action=%s",
                                ("USER_PAPEL_RECUSADO_AO_TI",))
    assert linhas and all('"papel_do_autor": "TI"' in (l["details"] or "") for l in linhas)


def test_o_ti_nao_mexe_na_conta_de_um_admin(casa):
    ids = casa["ids"]
    ti = _login(casa["app"], "suporte.ti")
    for acao, extra in (("editar", {"username": "oficial", "full_name": "MARIO EXEMPLO DOS SANTOS",
                                    "role": "USER"}),
                        ("reset", {"new_password": "Tomada#Conta123"}),
                        ("toggle", {}),
                        ("eh_robo", {"eh_robo": "1"}),
                        ("funcao", {"funcao": "Escrevente"})):
        r = ti.post("/usuarios", data={"action": acao, "csrf_token": _token(ti),
                                       "user_id": str(ids["oficial"]), **extra},
                    follow_redirects=True)
        assert "não altera a conta de um ADMIN" in r.get_data(as_text=True), acao
    oficial = casa["db"].get_user(ids["oficial"])
    assert oficial["role"] == "ADMIN" and oficial["active"]
    assert casa["db"].authenticate("oficial", SENHA), "a senha do oficial não pode mudar"


def test_o_admin_segue_promovendo_e_editando(casa):
    ids = casa["ids"]
    adm = _login(casa["app"], "oficial")
    adm.post("/usuarios", data={"action": "editar", "csrf_token": _token(adm),
                                "user_id": str(ids["gerente"]), "username": "gerente",
                                "full_name": "GINA EXEMPLO GERENTE", "role": "ADMIN"})
    assert _papel(casa, ids["gerente"]) == "ADMIN"
    adm.post("/usuarios", data={"action": "editar", "csrf_token": _token(adm),
                                "user_id": str(ids["ti"]), "username": "suporte.ti",
                                "full_name": "TADEU EXEMPLO DE TI", "role": "USER"})
    assert _papel(casa, ids["ti"]) == "USER"


# -------------------------------------------------------------- regressão


def test_o_auditor_e_o_escrevente_seguem_barrados_onde_eram(casa):
    aud = _login(casa["app"], "auditor")
    assert aud.get("/usuarios").status_code == 403
    assert aud.get("/configuracoes").status_code == 403
    esc = _login(casa["app"], "escrevente")
    assert esc.get("/usuarios").status_code == 403
    # o escrevente sela: a rede do TI não o recusa (a rota decide o resto)
    r = esc.post("/notas/cartoes/999999/selar", data={"csrf_token": _token(esc)})
    assert not (r.status_code == 403 and PAP.MSG_NAO_SELA in r.get_data(as_text=True))

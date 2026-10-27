"""O PAINEL DE SENHAS (26/10/2026) — a TV, o papel, o guichê, o protocolo e a
régua do tempo de espera.

O QUE ESTES TESTES GUARDAM
    - a TV abre SEM login só com a chave certa, e o que ela recebe é senha e
      guichê — nenhum nome, tipo de serviço nem atendente;
    - a chave mora no cofre (`senhas.cred`), e não no banco;
    - a fila só anda da situação certa: duas pessoas não chamam a mesma senha;
    - a espera vai da chegada até a PRIMEIRA chamada, e é a mesma régua em
      `/relatorios`, no relatório do período e no painel do gestor;
    - o AUDITOR vê o relatório e não grava na fila.

Nomes fictícios (regra da casa): mario é o ADMIN, beatriz a escrevente,
carla a auditora.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cofre_cred as COFRE  # noqa: E402
import senhas as SEN  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
HOJE = date.today().isoformat()


def _entrar(app, usuario):
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/login", data={"username": usuario, "password": SENHA, "csrf_token": token})
    assert r.status_code == 302, "o login de teste não entrou"
    with c.session_transaction() as s:
        return c, s["csrf_token"]


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    ids = {
        "mario": db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN"),
        "beatriz": db.create_user("beatriz", "BEATRIZ EXEMPLO LIMA", SENHA, "USER"),
        "carla": db.create_user("carla", "CARLA EXEMPLO SOUZA", SENHA, "AUDITOR"),
    }
    with db.connect() as con:
        COFRE.gravar_segredo(con, COFRE.SENHAS, "chave_tv", "")
    cg_casa["ids"] = ids
    return cg_casa


def _hora(h, m, s=0, dia=HOJE):
    return f"{dia}T{h:02d}:{m:02d}:{s:02d}"


# ------------------------------------------------------------------ a fila

def test_a_senha_leva_a_letra_da_fila_e_a_numeracao_do_dia(casa):
    db = casa["db"]
    with db.transaction() as con:
        a = SEN.emitir(con, preferencial=False, tipo="Certidão", agora=_hora(8, 0))
        b = SEN.emitir(con, preferencial=True, tipo=None, agora=_hora(8, 1))
        ontem = (date.today() - timedelta(days=1)).isoformat()
        c = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(9, 0, dia=ontem))
    assert (a["senha"], b["senha"]) == ("N001", "P002")
    assert c["senha"] == "N001", "a numeração é por dia"


def test_chamar_a_proxima_comeca_pela_preferencial_e_exige_o_guiche(casa):
    db, uid = casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 0))
        SEN.emitir(con, preferencial=True, tipo=None, agora=_hora(8, 5))
    with db.transaction() as con:
        with pytest.raises(SEN.SenhaError, match="guichê"):
            SEN.chamar_proxima(con, user_id=uid, agora=_hora(8, 10), dia=HOJE)
    with db.transaction() as con:
        SEN.gravar_guiche(con, uid, " 3 ", agora=_hora(8, 10))
        primeira = SEN.chamar_proxima(con, user_id=uid, agora=_hora(8, 11), dia=HOJE)
        segunda = SEN.chamar_proxima(con, user_id=uid, agora=_hora(8, 12), dia=HOJE)
        terceira = SEN.chamar_proxima(con, user_id=uid, agora=_hora(8, 13), dia=HOJE)
    assert (primeira["senha"], primeira["guiche"]) == ("P002", "3")
    assert segunda["senha"] == "N001"
    assert terceira is None


def test_preferencial_e_normal_se_alternam_e_o_lado_vazio_nao_trava_a_fila(casa):
    """Decisão do oficial em 26/10/2026: «preferencial alternada»."""
    db, uid = casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        for minuto, pref in ((0, True), (1, True), (2, True), (3, True), (4, False)):
            SEN.emitir(con, preferencial=pref, tipo=None, agora=_hora(8, minuto))
        SEN.gravar_guiche(con, uid, "1", agora=_hora(8, 5))
    chamadas = []
    for minuto in range(10, 16):
        with db.transaction() as con:
            r = SEN.chamar_proxima(con, user_id=uid, agora=_hora(8, minuto), dia=HOJE)
        chamadas.append(r["senha"] if r else None)
    # Uma de cada enquanto há das duas; acabada a normal, a preferencial não espera.
    assert chamadas == ["P001", "N005", "P002", "P003", "P004", None]


def test_o_papel_e_a_tela_seguem_a_mesma_alternancia_do_botao(casa):
    db, uid = casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        n1 = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 0))
        n2 = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 1))
        p3 = SEN.emitir(con, preferencial=True, tipo=None, agora=_hora(8, 2))
        p4 = SEN.emitir(con, preferencial=True, tipo=None, agora=_hora(8, 3))
    with db.transaction() as con:
        # Ninguém chamado ainda: P003, N001, P004, N002.
        assert SEN.ordem_de_chamada(con, HOJE) == [p3["id"], n1["id"], p4["id"], n2["id"]]
        assert SEN.a_frente(con, SEN.senha(con, n2["id"])) == 3
        assert SEN.a_frente(con, SEN.senha(con, p4["id"])) == 2
        fila = [r["senha"] for r in SEN.fila_do_dia(con, HOJE) if r["status"] == "AGUARDANDO"]
    assert fila == ["P003", "N001", "P004", "N002"]


def test_a_mesma_senha_nao_se_chama_duas_vezes_nem_se_finaliza_sem_comecar(casa):
    db, uid = casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        SEN.gravar_guiche(con, uid, "1", agora=_hora(8, 0))
        t = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 0))
        SEN.agir(con, t["id"], "call", user_id=uid, agora=_hora(8, 5))
    with db.transaction() as con:
        with pytest.raises(SEN.SenhaError, match="não está mais aguardando"):
            SEN.agir(con, t["id"], "call", user_id=uid, agora=_hora(8, 6))
        with pytest.raises(SEN.SenhaError, match="não aceita"):
            SEN.agir(con, t["id"], "finish", user_id=uid, agora=_hora(8, 6))
    with db.transaction() as con:
        SEN.agir(con, t["id"], "recall", user_id=uid, agora=_hora(8, 7))
        linha = banco(con).um("SELECT * FROM service_tickets WHERE id=%s", (t["id"],))
    assert linha["chamadas"] == 2
    assert linha["called_at"] == _hora(8, 5), "a rechamada não mexe na primeira chamada"
    assert linha["ultima_chamada_em"] == _hora(8, 7)


def test_a_desistencia_so_vale_antes_do_atendimento(casa):
    db, uid = casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        SEN.gravar_guiche(con, uid, "1", agora=_hora(8, 0))
        a = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 0))
        b = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 1))
        SEN.agir(con, a["id"], "giveup", user_id=uid, agora=_hora(8, 30))
        SEN.agir(con, b["id"], "call", user_id=uid, agora=_hora(8, 31))
        SEN.agir(con, b["id"], "start", user_id=uid, agora=_hora(8, 32))
    with db.transaction() as con:
        with pytest.raises(SEN.SenhaError):
            SEN.agir(con, b["id"], "giveup", user_id=uid, agora=_hora(8, 33))


# ------------------------------------------------------------------ a régua

def test_a_espera_vai_ate_a_primeira_chamada_e_o_relatorio_agrupa(casa):
    db = casa["db"]
    beatriz, mario = casa["ids"]["beatriz"], casa["ids"]["mario"]
    ontem = (date.today() - timedelta(days=1)).isoformat()
    with db.transaction() as con:
        SEN.gravar_guiche(con, beatriz, "1", agora=_hora(7, 0))
        SEN.gravar_guiche(con, mario, "2", agora=_hora(7, 0))
        # beatriz: espera 10 min (chamada), atendimento 6 min
        a = SEN.emitir(con, preferencial=False, tipo="Certidão", agora=_hora(8, 0))
        SEN.agir(con, a["id"], "call", user_id=beatriz, agora=_hora(8, 10))
        SEN.agir(con, a["id"], "recall", user_id=beatriz, agora=_hora(8, 12))
        SEN.agir(con, a["id"], "start", user_id=beatriz, agora=_hora(8, 14))
        SEN.agir(con, a["id"], "finish", user_id=beatriz, agora=_hora(8, 20))
        # mario: espera 20 min, preferencial, atendimento 10 min
        b = SEN.emitir(con, preferencial=True, tipo="Protesto", agora=_hora(8, 0))
        SEN.agir(con, b["id"], "call", user_id=mario, agora=_hora(8, 20))
        SEN.agir(con, b["id"], "start", user_id=mario, agora=_hora(8, 20))
        SEN.agir(con, b["id"], "finish", user_id=mario, agora=_hora(8, 30))
        # ontem: uma ficou na fila (sem atendimento) e uma desistiu
        SEN.emitir(con, preferencial=False, tipo="Certidão", agora=_hora(9, 0, dia=ontem))
        d = SEN.emitir(con, preferencial=False, tipo="Certidão", agora=_hora(9, 5, dia=ontem))
        SEN.agir(con, d["id"], "giveup", user_id=beatriz, agora=_hora(9, 40, dia=ontem))
    with db.connect() as con:
        m = SEN.metricas(con, ontem, HOJE, hoje=HOJE)
    r = m["resumo"]
    assert r["total"] == 4 and r["atendidas"] == 2
    assert r["desistencias"] == 1 and r["sem_atendimento"] == 1
    assert r["espera_media"] == 15 * 60, "chegada → primeira chamada (10 e 20 min)"
    assert r["espera_maior"] == 20 * 60
    assert r["atendimento_medio"] == 8 * 60
    por_atendente = {g["nome"]: g for g in m["por_atendente"]}
    assert por_atendente["BEATRIZ EXEMPLO LIMA"]["desistencias"] == 1
    assert por_atendente["MARIO EXEMPLO DOS SANTOS"]["espera_media"] == 20 * 60
    assert "(sem atendente)" in por_atendente
    assert {g["nome"] for g in m["por_tipo"]} == {"Certidão", "Protesto"}
    assert {g["nome"]: g["total"] for g in m["por_prioridade"]} == {"Normal": 3, "Preferencial": 1}
    # a MESMA régua no bloco de /relatorios
    hoje = db.service_metrics_today()
    assert hoje["total"] == 2 and hoje["avg_wait_seconds"] == 15 * 60
    assert hoje["avg_service_seconds"] == 8 * 60 and hoje["desistencias"] == 0


# ------------------------------------------------------------------ o protocolo

def test_a_senha_se_liga_ao_protocolo_geral_pelo_numero(casa):
    import caixa_protocolo as CXP
    db, uid = casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        p = CXP.abrir(con, data_abertura=HOJE, agora=_hora(8, 0), interessado="FULANO EXEMPLO",
                      criado_por=uid)
        t = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 0))
    with db.transaction() as con:
        with pytest.raises(SEN.SenhaError, match="Não achei"):
            SEN.ligar_protocolo(con, t["id"], "1999.01.999", user_id=uid, agora=_hora(8, 1))
        feito = SEN.ligar_protocolo(con, t["id"], p["numero"], user_id=uid, agora=_hora(8, 1))
    assert feito["protocolo_id"] == p["protocolo_id"]
    with db.connect() as con:
        assert SEN.senha(con, t["id"])["protocolo_numero"] == p["numero"]
        assert SEN.metricas(con, HOJE, HOJE)["resumo"]["com_protocolo"] == 1
    with db.transaction() as con:
        SEN.desligar_protocolo(con, t["id"])
    with db.connect() as con:
        assert SEN.senha(con, t["id"])["protocolo_numero"] is None


# ------------------------------------------------------------------ a TV

def test_o_estado_da_tv_so_leva_senha_e_guiche(casa):
    db, uid = casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        SEN.gravar_guiche(con, uid, "4", agora=_hora(8, 0))
        for i in range(3):
            t = SEN.emitir(con, preferencial=False, tipo="Certidão", agora=_hora(8, i))
            SEN.agir(con, t["id"], "call", user_id=uid, agora=_hora(9, i))
    with db.connect() as con:
        estado = SEN.estado_do_painel(con, HOJE)
    assert estado["atual"]["senha"] == "N003" and estado["atual"]["guiche"] == "4"
    assert [x["senha"] for x in estado["ultimas"]] == ["N002", "N001"]
    for item in [estado["atual"], *estado["ultimas"]]:
        assert set(item) == {"senha", "guiche", "marca"}


def test_a_tv_abre_sem_login_so_com_a_chave_certa_e_nao_mostra_nome(casa):
    app, db, uid = casa["app"], casa["db"], casa["ids"]["beatriz"]
    anonimo = app.test_client()
    assert anonimo.get("/senhas/tv/qualquer-coisa").status_code == 404, \
        "painel desligado: nenhum endereço abre"
    admin, token = _entrar(app, "mario")
    r = admin.post("/atendimento/painel-da-tv", data={"csrf_token": token, "acao": "gerar"})
    assert r.status_code == 302
    with db.connect() as con:
        chave = COFRE.ler_segredo(con, COFRE.SENHAS, "chave_tv")
        em_settings = banco(con).valor(
            "SELECT COUNT(*) AS n FROM settings WHERE value LIKE %s", (f"%{chave}%",))
    assert len(chave) >= 40
    assert em_settings == 0, "a chave da TV não entra no banco"
    assert chave in admin.get("/atendimento/painel-da-tv").get_data(as_text=True)

    with db.transaction() as con:
        SEN.gravar_guiche(con, uid, "2", agora=_hora(8, 0))
        t = SEN.emitir(con, preferencial=True, tipo="Registro de Imóveis", agora=_hora(8, 0))
        SEN.agir(con, t["id"], "call", user_id=uid, agora=_hora(8, 3))
    assert anonimo.get("/senhas/tv/" + chave[:-1] + "x").status_code == 404
    tela = anonimo.get("/senhas/tv/" + chave)
    assert tela.status_code == 200 and tela.headers["Cache-Control"] == "no-store"
    estado = anonimo.get(f"/senhas/tv/{chave}/estado")
    assert estado.status_code == 200
    texto = estado.get_data(as_text=True)
    assert estado.get_json()["atual"]["senha"] == "P001"
    for proibido in ("BEATRIZ", "Registro de Imóveis", "Registro de Im"):
        assert proibido not in texto

    # trocar o endereço desliga a TV antiga na hora
    admin.post("/atendimento/painel-da-tv", data={"csrf_token": token, "acao": "gerar"})
    assert anonimo.get(f"/senhas/tv/{chave}/estado").status_code == 404


# ------------------------------------------------------------------ as telas

def test_o_balcao_grava_o_guiche_emite_imprime_e_chama(casa):
    app = casa["app"]
    c, token = _entrar(app, "beatriz")
    assert c.post("/atendimento/guiche", data={"csrf_token": token, "guiche": "Mesa 3"}).status_code == 302
    r = c.post("/atendimento", data={"csrf_token": token, "action": "new", "priority": "on",
                                     "service_type": "Certidão", "imprimir": "1"})
    assert r.status_code == 302 and "/imprimir" in r.headers["Location"]
    papel = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "P001" in papel and "80mm" in papel and "BEATRIZ" not in papel
    assert c.post("/atendimento/chamar-proxima", data={"csrf_token": token}).status_code == 302
    tela = c.get("/atendimento").get_data(as_text=True)
    assert "Mesa 3" in tela and "Chamar de novo" in tela


def test_a_rota_antiga_recusa_acao_desconhecida_e_avisa_a_corrida(casa):
    app, db = casa["app"], casa["db"]
    c, token = _entrar(app, "beatriz")
    c.post("/atendimento/guiche", data={"csrf_token": token, "guiche": "1"})
    with db.transaction() as con:
        t = SEN.emitir(con, preferencial=False, tipo=None, agora=_hora(8, 0))
    assert c.post(f"/atendimento/{t['id']}/apagar", data={"csrf_token": token}).status_code == 400
    assert c.post(f"/atendimento/{t['id']}/call", data={"csrf_token": token}).status_code == 302
    r = c.post(f"/atendimento/{t['id']}/call", data={"csrf_token": token}, follow_redirects=True)
    assert "não está mais aguardando" in r.get_data(as_text=True)


def test_o_auditor_ve_o_relatorio_e_nao_grava_na_fila(casa):
    app = casa["app"]
    fiscal, token = _entrar(app, "carla")
    assert fiscal.get("/atendimento/relatorio").status_code == 200
    assert fiscal.get("/atendimento/relatorio.csv").status_code == 200
    for rota in ("/atendimento/guiche", "/atendimento/chamar-proxima",
                 "/atendimento/1/protocolo"):
        assert fiscal.post(rota, data={"csrf_token": token}).status_code == 403, rota
    assert fiscal.get("/atendimento/painel-da-tv").status_code == 403
    balcao, _ = _entrar(app, "beatriz")
    assert balcao.get("/atendimento/relatorio").status_code == 403


def test_o_relatorio_e_o_painel_do_gestor_mostram_os_numeros(casa):
    app, db, uid = casa["app"], casa["db"], casa["ids"]["beatriz"]
    with db.transaction() as con:
        SEN.gravar_guiche(con, uid, "1", agora=_hora(7, 0))
        t = SEN.emitir(con, preferencial=False, tipo="Certidão", agora=_hora(8, 0))
        SEN.agir(con, t["id"], "call", user_id=uid, agora=_hora(8, 12))
    admin, _ = _entrar(app, "mario")
    rel = admin.get(f"/atendimento/relatorio?de={HOJE}&ate={HOJE}").get_data(as_text=True)
    assert "12,0 min" in rel and "BEATRIZ EXEMPLO LIMA" in rel
    csv = admin.get(f"/atendimento/relatorio.csv?de={HOJE}&ate={HOJE}").get_data(as_text=True)
    assert "N001" in csv and "12,0" in csv
    painel = admin.get("/").get_data(as_text=True)
    assert "Atendimento de hoje" in painel and "12,0 min" in painel
    balcao, _ = _entrar(app, "beatriz")
    assert "Maior espera" not in balcao.get("/").get_data(as_text=True)


def test_os_tipos_de_atendimento_sao_do_oficial(casa):
    app, db = casa["app"], casa["db"]
    assert SEN.tipos_de_atendimento(db.get_setting) == list(SEN.TIPOS_DE_FABRICA)
    admin, token = _entrar(app, "mario")
    admin.post("/atendimento/painel-da-tv",
               data={"csrf_token": token, "acao": "tipos", "tipos": "Balcão A\n\n  Balcão   B \n"})
    assert SEN.tipos_de_atendimento(db.get_setting) == ["Balcão A", "Balcão B"]
    assert "Balcão B" in admin.get("/atendimento").get_data(as_text=True)


def test_os_tipos_de_fabrica_tem_uma_entrada_por_atribuicao(casa):
    """DECISÃO DO OFICIAL EM 26/10/2026, «tipos: todas as atribuições»: a lista
    de fábrica traz uma entrada por atribuição da casa, com o nome do
    vocabulário (`atribuicoes.ATRIBUICOES`), na ordem do balcão, e os tipos
    genéricos em volta. RTD e RCPJ são duas entradas, e não uma."""
    import atribuicoes as ATR
    nomes = [a["nome"] for a in ATR.ATRIBUICOES.values()]
    fabrica = list(SEN.TIPOS_DE_FABRICA)
    # toda atribuição do vocabulário está lá, uma vez só, e com o nome dele
    for nome in nomes:
        assert fabrica.count(nome) == 1, nome
    por_sigla = {a["sigla"]: a["nome"] for a in ATR.ATRIBUICOES.values()}
    assert set(SEN.ORDEM_DAS_ATRIBUICOES) == set(por_sigla)
    assert por_sigla["RTD"] != por_sigla["RCPJ"]
    # a ordem que o oficial ditou: Notas, RI, Registro Civil, RTD, RCPJ, Protesto
    assert list(SEN.tipos_das_atribuicoes()) == [
        por_sigla[s] for s in ("NOTAS", "RI", "RCPN", "RTD", "RCPJ", "PROTESTO")]
    # os genéricos que já existiam continuam, em volta das atribuições
    assert fabrica[0] == "Geral"
    for generico in ("Certidão", "Retirada de documento", "Pagamento / caixa"):
        assert generico in fabrica
    assert "Títulos e Documentos / Pessoa Jurídica" not in fabrica
    assert len(fabrica) == len(set(fabrica)) == len(nomes) + 4
    # é a lista que a tela oferece quando o oficial não gravou a dele
    app, db = casa["app"], casa["db"]
    assert SEN.tipos_de_atendimento(db.get_setting) == fabrica
    admin, _ = _entrar(app, "mario")
    tela = admin.get("/atendimento").get_data(as_text=True)
    for nome in nomes:
        assert nome in tela, nome


def test_atribuicao_nova_no_vocabulario_nao_some_da_lista(monkeypatch):
    """A ordem do balcão é só ordem: atribuição que entrar no vocabulário e não
    estiver nela vai para o fim, em vez de sumir da lista de tipos."""
    import atribuicoes as ATR
    novas = dict(ATR.ATRIBUICOES)
    novas[99] = {"sigla": "NOVA", "nome": "Atribuição de Exemplo"}
    monkeypatch.setattr(ATR, "ATRIBUICOES", novas)
    tipos = SEN.tipos_das_atribuicoes()
    assert tipos[-1] == "Atribuição de Exemplo" and len(tipos) == 7

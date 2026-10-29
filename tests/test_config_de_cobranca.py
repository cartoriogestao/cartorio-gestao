"""As configurações que cobram a equipe — e quem pode afrouxá-las (29/10/2026).

    «trabalhamos com mão de obra muito propensa a erros [...] não deixar a
     escrevente cometer erros. Se insistir em algo que é erro, precisa afirmar
     expressamente e deixar log» — o oficial, 29/10/2026

O CASO: o fim do expediente (o aviso vermelho do caixa aberto) foi empurrado
de 14h para 21h em dois dias, por script direto no banco, a pedido de quem o
aviso cobrava. Estes testes provam as quatro respostas da regra — robô
recusado, MANAGER recusado, ADMIN sem afirmação recusado, ADMIN com afirmação
grava — e que o atalho pelo banco é recusado pelo próprio banco.

E O TURNO (acréscimo do mesmo dia): a escrevente da noite opera o caixa; para
ela o aviso começa no fim do turno dela, e o caixa de turno anterior continua
trancando.

NOMES: `mario` é o ADMIN (o oficial), `beatriz` a MANAGER, `carla` a escrevente
da noite (USER), `robo` a conta de robô — regra da casa, sem nome real.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import caixa_aviso as CA                                         # noqa: E402
import config_de_cobranca as CC                                  # noqa: E402
from bd_nativo import ERROS_DO_BANCO, banco                      # noqa: E402
from conftest import cg_login                                    # noqa: E402

SENHA = "Senha#12345"
CHAVE = CA.CHAVE_FIM
AFIRMACAO = ("o expediente da casa passou a terminar às quinze horas, por "
             "decisão do oficial registrada na portaria interna")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    ids = {
        "mario": db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN"),
        "beatriz": db.create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "MANAGER"),
        "carla": db.create_user("carla", "CARLA EXEMPLO DE SOUSA", SENHA, "USER"),
        "robo": db.create_user("robo", "ROBÔ DO BALCÃO", SENHA, "USER", eh_robo=1),
    }
    # O robô da casa tem responsável (ordem de 26/10/2026): a tentativa dele
    # sai «a mando de» quem responde por ele.
    import identidade_do_robo as IDR
    with db.transaction() as con:
        IDR.definir_responsavel_do_robo(con, ids["robo"], ids["beatriz"])
    return {**cg_casa, "ids": ids}


def _papel(db, uid):
    with db.connect() as con:
        return banco(con).valor("SELECT role FROM users WHERE id = %s", (uid,))


def _cliente(casa, login):
    c = casa["app"].test_client()
    cg_login(c, login, SENHA)
    return c


def _postar(c, **dados):
    # O token vem de uma tela que qualquer login abre; a sessão é a mesma.
    token = _token(c.get("/").get_data(as_text=True))
    return c.post("/configuracoes/cobranca/alterar",
                  data={"csrf_token": token, **dados}, follow_redirects=True)


def _linhas(db, acao):
    with db.connect() as con:
        return [dict(r, d=json.loads(r["details"] or "{}")) for r in banco(con).ler(
            "SELECT id, user_id, username_snapshot, action, entity_type, details "
            "FROM audit_logs WHERE action = %s ORDER BY id", (acao,))]


def _tarefas(db):
    with db.connect() as con:
        return banco(con).ler(
            "SELECT id, source_ref, title, description, assigned_user_id FROM tasks "
            "WHERE source_type = %s ORDER BY id", (CC.ORIGEM_DA_TAREFA,))


def _aprovar(db, uid, chave, valor):
    """O caminho do oficial, direto no domínio (o que a tela chama)."""
    with db.transaction() as con:
        return CC.alterar(con, chave=chave, valor=valor, usuario_id=uid, afirmo=True,
                          afirmacao=AFIRMACAO, agora=db.now())


# ------------------------------------------------------------ as quatro respostas

def test_o_robo_e_recusado_e_a_tentativa_fica_na_auditoria(casa):
    db = casa["db"]
    c = _cliente(casa, "robo")
    r = _postar(c, chave=CHAVE, valor="21:00", afirmo="1", afirmacao=AFIRMACAO)
    assert r.status_code == 403
    assert db.get_setting(CHAVE, "") == "", "o robô mudou a configuração"
    recusas = _linhas(db, CC.ACAO_RECUSADA)
    assert len(recusas) == 1
    assert recusas[0]["d"]["motivo"] == CC.MOTIVO_ROBO
    assert recusas[0]["d"]["chave"] == CHAVE and recusas[0]["d"]["para"] == "21:00"
    assert recusas[0]["user_id"] == casa["ids"]["robo"]
    # e o oficial fica sabendo
    assert any("Tentativa recusada" in t["title"] for t in _tarefas(db))


def test_o_robo_e_recusado_pelo_dominio_mesmo_com_papel_de_admin():
    """A ordem da regra: robô vem antes do papel — nem um robô ADMIN passa."""
    with pytest.raises(CC.Recusa) as erro:
        CC.conferir_quem({"active": 1, "eh_robo": 1, "role": "ADMIN",
                          "username": "robo", "full_name": "ROBÔ DO BALCÃO"}, CHAVE)
    assert erro.value.motivo == CC.MOTIVO_ROBO


def test_o_manager_e_recusado_com_peca_ao_oficial(casa):
    db = casa["db"]
    c = _cliente(casa, "beatriz")
    html = _postar(c, chave=CHAVE, valor="18:00", afirmo="1",
                   afirmacao=AFIRMACAO).get_data(as_text=True)
    assert "Peça ao oficial" in html
    assert db.get_setting(CHAVE, "") == ""
    recusas = _linhas(db, CC.ACAO_RECUSADA)
    assert [x["d"]["motivo"] for x in recusas] == [CC.MOTIVO_PAPEL]
    assert recusas[0]["user_id"] == casa["ids"]["beatriz"]
    tarefas = _tarefas(db)
    assert len(tarefas) == 1 and _papel(db, tarefas[0]["assigned_user_id"]) == "ADMIN"
    assert "18:00" in tarefas[0]["description"]


def test_o_usuario_e_recusado_e_a_insistencia_nao_enche_a_lista_do_oficial(casa):
    db = casa["db"]
    c = _cliente(casa, "carla")
    for hora in ("19:00", "20:00", "21:00"):
        _postar(c, chave=CHAVE, valor=hora, afirmo="1", afirmacao=AFIRMACAO)
    assert db.get_setting(CHAVE, "") == ""
    assert len(_linhas(db, CC.ACAO_RECUSADA)) == 3, "cada tentativa fica gravada"
    tarefas = _tarefas(db)
    assert len(tarefas) == 1, "uma tarefa por chave e por dia, e não uma por tentativa"
    assert all(h in tarefas[0]["description"] for h in ("19:00", "20:00", "21:00"))


def test_o_admin_sem_afirmacao_e_recusado(casa):
    db = casa["db"]
    c = _cliente(casa, "mario")
    sem_caixa = _postar(c, chave=CHAVE, valor="15:00",
                        afirmacao=AFIRMACAO).get_data(as_text=True)
    assert "afirmação expressa" in sem_caixa
    curta = _postar(c, chave=CHAVE, valor="15:00", afirmo="1",
                    afirmacao="porque sim").get_data(as_text=True)
    assert "afirmação expressa" in curta
    assert db.get_setting(CHAVE, "") == ""
    assert [x["d"]["motivo"] for x in _linhas(db, CC.ACAO_RECUSADA)] == [
        CC.MOTIVO_SEM_AFIRMACAO, CC.MOTIVO_SEM_AFIRMACAO]
    assert _linhas(db, CC.ACAO_AFIRMACAO) == []
    # o oficial que esqueceu de marcar «afirmo» não ganha tarefa de si mesmo
    assert _tarefas(db) == []


def test_o_admin_com_afirmacao_passa_e_grava(casa):
    db = casa["db"]
    c = _cliente(casa, "mario")
    html = _postar(c, chave=CHAVE, valor="15h", afirmo="1",
                   afirmacao=AFIRMACAO).get_data(as_text=True)
    assert "Gravado" in html
    assert db.get_setting(CHAVE, "") == "15:00", "a hora se grava normalizada"
    # O CONTRATO COMUM DA AFIRMAÇÃO EXPRESSA
    afirmacoes = _linhas(db, CC.ACAO_AFIRMACAO)
    assert len(afirmacoes) == 1
    a = afirmacoes[0]
    assert a["entity_type"] == "settings" and a["user_id"] == casa["ids"]["mario"]
    assert a["d"]["regra"] == "CONFIG_DE_COBRANCA"
    assert a["d"]["afirmacao"].startswith("Afirmo, sob minha responsabilidade, que")
    assert "quinze horas" in a["d"]["afirmacao"]
    # o que faltava: o que a chave cobra, e que a mudança afrouxa
    assert "faixa vermelha" in a["d"]["o_que_faltava"]
    assert "cala o aviso" in a["d"]["o_que_faltava"]
    alteradas = _linhas(db, CC.ACAO_ALTERADA)
    assert [(x["d"]["chave"], x["d"]["de"], x["d"]["para"]) for x in alteradas] == [
        (CHAVE, None, "15:00")]
    assert alteradas[0]["d"]["afrouxa"] is True, "de 14:00 (padrão) para 15:00 afrouxa"
    # a tarefa do oficial, sem e-mail por evento
    tarefas = _tarefas(db)
    assert len(tarefas) == 1 and "alterada" in tarefas[0]["title"]
    # e a afirmação entra na lista das afirmações expressas do oficial
    import afirmacoes_expressas as AFX
    with db.connect() as con:
        lista = AFX.listar(con, hoje=db.now())
    assert "CONFIG_DE_COBRANCA" in lista["regras"]


def test_o_valor_torto_nao_grava_e_nao_e_tentativa(casa):
    db = casa["db"]
    c = _cliente(casa, "mario")
    html = _postar(c, chave=CHAVE, valor="vinte e uma", afirmo="1",
                   afirmacao=AFIRMACAO).get_data(as_text=True)
    assert "não é hora" in html
    assert db.get_setting(CHAVE, "") == ""
    assert _linhas(db, CC.ACAO_RECUSADA) == [] and _linhas(db, CC.ACAO_ALTERADA) == []


# ------------------------------------------------------------ o banco recusa o atalho

def test_o_banco_recusa_o_set_settings_direto(casa):
    """Foi assim que o fim do expediente foi de 14h a 21h: escrita direta."""
    db = casa["db"]
    with pytest.raises(ERROS_DO_BANCO) as erro:
        db.set_settings({CHAVE: "21:00"})
    assert "cobrança" in str(erro.value) and "oficial" in str(erro.value)
    assert db.get_setting(CHAVE, "") == ""


def test_o_banco_recusa_update_e_delete_crus(casa):
    db = casa["db"]
    _aprovar(db, casa["ids"]["mario"], CHAVE, "15:00")
    con = sqlite3.connect(casa["banco"])
    try:
        with pytest.raises(ERROS_DO_BANCO):
            con.execute("UPDATE settings SET value = '21:00' WHERE key = ?", (CHAVE,))
        con.rollback()
        with pytest.raises(ERROS_DO_BANCO):
            con.execute("DELETE FROM settings WHERE key = ?", (CHAVE,))
        con.rollback()
    finally:
        con.close()
    assert db.get_setting(CHAVE, "") == "15:00"


def test_aprovacao_antiga_nao_serve_para_outro_valor(casa):
    """A linha que o gatilho aceita é a ÚLTIMA aprovação, e só com o valor dela:
    regravar o que o oficial aprovou passa; qualquer outro valor, não."""
    db = casa["db"]
    uid = casa["ids"]["mario"]
    _aprovar(db, uid, CHAVE, "18:00")
    _aprovar(db, uid, CHAVE, "14:00")
    db.set_settings({CHAVE: "14:00"})          # o mesmo valor: nada muda, passa
    with pytest.raises(ERROS_DO_BANCO):
        db.set_settings({CHAVE: "18:00"})      # a aprovação de 18h já foi substituída
    assert db.get_setting(CHAVE, "") == "14:00"


def test_toda_chave_da_lista_esta_no_gatilho_e_as_outras_nao(casa):
    db = casa["db"]
    for c in CC.CHAVES:
        with pytest.raises(ERROS_DO_BANCO):
            db.set_settings({c.chave: "1"})
    with pytest.raises(ERROS_DO_BANCO):
        db.set_settings({CA.chave_do_turno("carla"): "18:00-23:00"})
    db.set_settings({"unit_name": "SERVENTIA DE EXEMPLO"})   # chave comum: livre
    assert db.get_setting("unit_name") == "SERVENTIA DE EXEMPLO"


def test_o_gatilho_desligado_se_religa_na_abertura(casa):
    db = casa["db"]
    with db.transaction() as con:
        banco(con)._cru(f"ALTER TABLE settings DISABLE TRIGGER {CC.NOME_DO_GATILHO}")
    try:
        with db.transaction() as con:
            feitos = CC.instalar_gatilho(con)
        assert any("ENABLE TRIGGER" in f for f in feitos)
        with pytest.raises(ERROS_DO_BANCO):
            db.set_settings({CHAVE: "21:00"})
    finally:
        with db.transaction() as con:
            banco(con)._cru(f"ALTER TABLE settings ENABLE TRIGGER {CC.NOME_DO_GATILHO}")


def test_o_gatilho_leva_a_lista_do_python():
    corpo = CC.corpo_do_gatilho()
    for c in CC.CHAVES:
        assert f"'{c.chave}'" in corpo
    assert f"'{CC.PREFIXO_DO_TURNO}'" in corpo


# ------------------------------------------------------------ o turno

def test_ninguem_define_o_proprio_turno(casa):
    db = casa["db"]
    with pytest.raises(CC.Recusa) as erro:
        _aprovar(db, casa["ids"]["mario"], CA.chave_do_turno("MARIO"), "18:00-23:00")
    assert erro.value.motivo == CC.MOTIVO_PROPRIO_TURNO
    assert db.get_setting(CA.chave_do_turno("mario"), "") == ""


def test_o_oficial_define_o_turno_da_escrevente_da_noite(casa):
    db = casa["db"]
    feito = _aprovar(db, casa["ids"]["mario"], CA.chave_do_turno("carla"), "16:00 - 23:00")
    assert feito["mudou"] and feito["para"] == "16:00-23:00"
    with db.connect() as con:
        assert CA.turno_de(con, "CARLA") == (16 * 60, 23 * 60)
    with pytest.raises(CC.ValorInvalido):
        _aprovar(db, casa["ids"]["mario"], CA.chave_do_turno("carla"), "23:00-23:00")
    with pytest.raises(CC.ValorInvalido):
        _aprovar(db, casa["ids"]["mario"], CA.chave_do_turno("robo"), "18:00-23:00")


def test_turno_se_le_e_o_torto_vira_nenhum():
    assert CA.turno("18:00-01:00") == (1080, 60)
    assert CA.turno(" 08:00 - 14:00 ") == (480, 840)
    assert CA.turno("18:00-18:00") is None
    assert CA.turno("25:00-01:00") is None
    assert CA.turno("") is None and CA.turno(None) is None


NOITE = "CARLA EXEMPLO DE SOUSA"
DIA = "BEATRIZ EXEMPLO DE SOUZA"


def _caixa(con, data, nome, aberto_em):
    con.execute("""INSERT INTO cx_caixas (data, operador_nome, saldo_inicial, aberto_em, situacao)
                   VALUES (?, ?, '0,00', ?, 'ABERTO')""", (data, nome, aberto_em))
    con.commit()


def test_operador_da_noite_com_caixa_aberto_as_20h_nao_tem_aviso(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    _caixa(con, "2026-10-29", NOITE, "2026-10-29T16:30:00")
    assert CA.situacao(con, NOITE, datetime(2026, 10, 29, 20, 0), "14:00",
                       turno_do_operador="16:00-23:00") is None
    # sem o turno, a mesma pessoa às 20h estaria no aviso — é o caso de 28/10
    assert CA.situacao(con, NOITE, datetime(2026, 10, 29, 20, 0),
                       "14:00")["nivel"] == "FIM_DO_EXPEDIENTE"
    # e o aviso dela começa no fim do turno DELA
    a = CA.situacao(con, NOITE, datetime(2026, 10, 29, 23, 5), "14:00",
                    turno_do_operador="16:00-23:00")
    assert a["nivel"] == "FIM_DO_EXPEDIENTE" and a["fim"] == "23:00"
    assert a["turno"] == "16:00-23:00"


def test_operador_do_dia_com_caixa_aberto_as_15h_tem_aviso(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    _caixa(con, "2026-10-29", DIA, "2026-10-29T08:00:00")
    a = CA.situacao(con, DIA, datetime(2026, 10, 29, 15, 0), "14:00")
    assert a["nivel"] == "FIM_DO_EXPEDIENTE" and a["fim"] == "14:00" and a["turno"] is None


def test_o_turno_que_atravessa_a_meia_noite_continua_trancando_o_turno_anterior(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    _caixa(con, "2026-10-28", NOITE, "2026-10-28T19:00:00")
    turno = "18:00-01:00"
    # 00h30: ainda é o turno da noite de 28/10 — nada a dizer
    assert CA.situacao(con, NOITE, datetime(2026, 10, 29, 0, 30), "14:00",
                       turno_do_operador=turno) is None
    # 02h: o turno acabou à 1h e o caixa dele está aberto — aviso insistente
    a = CA.situacao(con, NOITE, datetime(2026, 10, 29, 2, 0), "14:00",
                    turno_do_operador=turno)
    assert a["nivel"] == "FIM_DO_EXPEDIENTE" and a["fim"] == "01:00"
    # e no dia de trabalho seguinte o caixa do turno anterior TRANCA
    b = CA.situacao(con, NOITE, datetime(2026, 10, 29, 18, 5), "14:00",
                    turno_do_operador=turno)
    assert b["nivel"] == "BLOQUEIO" and b["dias"] == ["2026-10-28"]


def test_quem_abre_o_caixa_um_pouco_antes_do_turno_nao_e_trancado(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    _caixa(con, "2026-10-29", NOITE, "2026-10-29T17:40:00")
    assert CA.situacao(con, NOITE, datetime(2026, 10, 29, 18, 30), "14:00",
                       turno_do_operador="18:00-01:00") is None


def test_a_conferencia_das_14h_respeita_o_turno(casa, monkeypatch):
    import gestor_conferencia as GC
    db = casa["db"]
    _aprovar(db, casa["ids"]["mario"], CA.chave_do_turno("carla"), "16:00-23:00")
    hoje = date.today()
    con = sqlite3.connect(casa["banco"])
    for nome, uid in ((NOITE, casa["ids"]["carla"]), (DIA, casa["ids"]["beatriz"])):
        con.execute("""INSERT INTO cx_caixas (data, operador_id, operador_nome, saldo_inicial,
                           aberto_em, situacao) VALUES (?, ?, ?, '0,00', ?, 'ABERTO')""",
                    (hoje.isoformat(), uid, nome, hoje.isoformat() + "T13:00:00"))
    con.commit()
    monkeypatch.setattr(GC, "_relogio", lambda: datetime.combine(hoje, datetime.min.time())
                        + timedelta(hours=14, minutes=30))
    titulos = [a["titulo"] for a in GC.regra_caixa_do_dia(con, hoje)]
    assert len(titulos) == 1 and DIA in titulos[0] and "14:00" in titulos[0]


# ------------------------------------------------------------ o histórico

def test_o_historico_mostra_ao_oficial_o_que_foi_gravado_por_fora(casa):
    """As linhas de antes da guarda — scripts e robôs — entram com o nome que
    eles mesmos escreveram, e a de agora entra com a afirmação."""
    db = casa["db"]
    db.log(None, "robo (a mando de beatriz)", "SETTING_ALTERADO", "settings", None,
           {"key": CHAVE, "de": "18:00", "para": "19:00"},
           agente="robo", a_mando_de="beatriz")
    _aprovar(db, casa["ids"]["mario"], CHAVE, "14:00")
    with db.connect() as con:
        h = CC.historico(con, hoje=db.now())
    assert [(x["o_que"], x["de"], x["para"]) for x in h["linhas"]] == [
        ("ALTERADA", "", "14:00"), ("POR_FORA", "18:00", "19:00")]
    assert h["linhas"][1]["a_mando_de"] == "beatriz"
    html = _cliente(casa, "mario").get("/configuracoes/cobranca").get_data(as_text=True)
    assert "gravada por fora" in html and "19:00" in html and "Histórico" in html


def test_a_manager_ve_os_valores_e_nao_o_historico(casa):
    html = _cliente(casa, "beatriz").get("/configuracoes/cobranca").get_data(as_text=True)
    assert "Peça ao oficial" in html
    assert 'id="historico"' not in html and "configuracoes/cobranca/alterar" not in html


def test_o_usuario_nao_abre_a_tela(casa):
    assert _cliente(casa, "carla").get("/configuracoes/cobranca").status_code == 403

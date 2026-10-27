"""A automação — a agenda, as travas, o corredor, os avisos, o cofre e as telas.

O QUE ESTES TESTES PROVAM
    - a conta da agenda: dia da semana, janela, horário que venceu e não roda
      duas vezes, horário perdido há mais de 12 h que não roda;
    - as travas: a global, a por processo (PULADA uma vez por horário) e a
      recuperação da rodada que morreu (INTERROMPIDA) ou passou do prazo;
    - o prazo de verdade, com um script de mentira que dorme;
    - os avisos sem spam: alerta na transição, lembrete a cada N horas, a
      tarefa que nasce no problema e se fecha sozinha quando ele acaba;
    - «pode agir» só do ADMIN, e auditado; a escrita do agente segue o processo;
    - o cofre não guarda o segredo em claro e recusa devolvê-lo à tela;
    - as telas abrem, mandam o token e «rodar agora» só enfileira.
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

import automacao as AU  # noqa: E402
import automacao_avisos as AV  # noqa: E402
import automacao_processos as PROC  # noqa: E402
import automacao_schema as SCH  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
SEG = datetime(2026, 10, 26, 9, 0)        # uma segunda-feira


# ------------------------------------------------------------------ a agenda (sem banco)


def test_a_agenda_respeita_o_dia_da_semana_e_os_horarios():
    a = AU.normalizar_agenda({"dias": [0, 1, 2, 3, 4], "horarios": "14:10, 11:30"})
    assert a == {"dias": [0, 1, 2, 3, 4], "horarios": ["11:30", "14:10"]}
    sabado = datetime(2026, 10, 24, 12, 0)
    assert AU.proximo_disparo(a, sabado) == datetime(2026, 10, 26, 11, 30)
    assert AU.ultimo_slot(a, SEG) == datetime(2026, 10, 23, 14, 10)   # a sexta
    assert AU.descrever_agenda(a) == "seg a sex, às 11:30 e 14:10"


def test_o_intervalo_fica_dentro_da_janela():
    a = AU.normalizar_agenda({"intervalo_min": 60, "janela": ["08:00", "17:00"]})
    assert AU.ultimo_slot(a, datetime(2026, 10, 26, 18, 30)) == datetime(2026, 10, 26, 17, 0)
    assert AU.ultimo_slot(a, datetime(2026, 10, 26, 9, 59)) == datetime(2026, 10, 26, 9, 0)
    assert AU.proximo_disparo(a, datetime(2026, 10, 26, 17, 30)) == datetime(2026, 10, 27, 8, 0)


@pytest.mark.parametrize("ruim", [
    {"dias": [], "horarios": ["10:00"]},
    {"horarios": ["25:00"]},
    {"horarios": ["10:00"], "intervalo_min": 5},
    {"dias": [7], "horarios": ["10:00"]},
    {},
    {"intervalo_min": 30, "janela": ["10:00", "09:00"]},
])
def test_a_agenda_que_nao_fecha_e_recusada(ruim):
    with pytest.raises(AU.AutomacaoError):
        AU.normalizar_agenda(ruim)


def test_o_horario_vence_uma_vez_e_o_perdido_ha_muito_nao_roda():
    a = AU.normalizar_agenda({"dias": list(range(7)), "horarios": ["11:30"]})
    # o horário de ontem passou da tolerância de 12 h: não roda ao ligar hoje cedo
    assert AU.vencido(a, datetime(2026, 10, 26, 11, 29), None) is None
    antes = datetime(2026, 10, 26, 11, 29)
    assert AU.vencido(a, antes, datetime(2026, 10, 25, 11, 30)) is None      # não chegou ainda
    slot = AU.vencido(a, datetime(2026, 10, 26, 11, 31), datetime(2026, 10, 25, 11, 30))
    assert slot == datetime(2026, 10, 26, 11, 30)
    assert AU.vencido(a, datetime(2026, 10, 26, 11, 32), slot) is None      # já atendido
    # perdido há mais de 12 horas: o dia já passou
    assert AU.vencido(a, datetime(2026, 10, 27, 0, 30), datetime(2026, 10, 25, 11, 30)) is None


def test_o_resultado_fora_do_contrato_nao_vira_ok():
    assert AU.normalizar_resultado(None)["situacao"] == SCH.ERRO
    assert AU.normalizar_resultado({"situacao": "TALVEZ"})["situacao"] == SCH.ERRO
    assert AU.normalizar_resultado({"situacao": "RODANDO"})["situacao"] == SCH.ERRO
    assert AU.normalizar_resultado({"situacao": "ok", "relato": "x"})["situacao"] == SCH.OK


def test_o_prazo_mata_o_trabalho_que_nao_termina(tmp_path):
    inicio = datetime.now()
    r = AU.rodar_com_prazo([sys.executable, "-c", "import time; time.sleep(30)"], timeout_s=1, cwd=tmp_path)
    assert r["esgotou"] is True
    assert (datetime.now() - inicio).total_seconds() < 20


def test_a_saida_marcada_e_lida_e_o_segredo_sai_mascarado():
    p = {"tipo": SCH.SCRIPT, "timeout_s": 10}
    linha = AU.MARCA_DO_RESULTADO + json.dumps({"situacao": "AVISO", "relato": "dois pendentes"})
    r = AU.interpretar(p, {"codigo": 0, "saida": "senha=SEGREDO123\n" + linha, "erro": "", "esgotou": False,
                           "segundos": 1}, segredos=["SEGREDO123"])
    assert r["situacao"] == SCH.AVISO and r["relato"] == "dois pendentes"
    assert "SEGREDO123" not in r["detalhe_tecnico"] and AU.OMITIDO in r["detalhe_tecnico"]
    sem = AU.interpretar({"tipo": SCH.FUNCAO, "timeout_s": 10},
                         {"codigo": 1, "saida": "", "erro": "boom", "esgotou": False, "segundos": 1})
    assert sem["situacao"] == SCH.ERRO


# ------------------------------------------------------------------ o banco


@pytest.fixture
def casa(cg_casa, monkeypatch, tmp_path_factory):
    db = cg_casa["db"]
    # O cofre dos testes mora no tmp — a tela e o despachante nunca tocam o da casa.
    monkeypatch.setenv("CG_COFRE_AUTOMACAO", str(tmp_path_factory.mktemp("cofre") / "cofre.json"))
    # O backup automático da primeira requisição não é assunto destes testes,
    # e no PostgreSQL de teste ele custa minutos (pg_dump do schema inteiro).
    cg_casa["app"].extensions["backup_checked"] = True
    if not db.list_users():
        db.create_user("mario", "Mario Exemplo", SENHA, "ADMIN")
    with db.transaction() as con:
        AU.semear(con, SEG)
    return cg_casa


def _tique(db, **k):
    """O tique dos testes: NUNCA mata processo de verdade (os pids são de mentira)."""
    k.setdefault("matar", lambda pid: None)
    k.setdefault("vivo", lambda pid: True)
    return AU.tique(db, **k)


def _processo(db, codigo):
    with db.connect() as con:
        return AU.por_codigo(con, codigo)


def _ligar(db, codigo, quando):
    p = _processo(db, codigo)
    with db.transaction() as con:
        AU.definir_ativo(con, p["id"], True, usuario="mario", agora=quando)
    return _processo(db, codigo)


def test_os_processos_de_fabrica_nascem_desligados_e_nao_duplicam(casa):
    db = casa["db"]
    with db.transaction() as con:
        assert AU.semear(con, SEG) == 0
        todos = AU.listar(con)
    # As de fábrica MAIS as que outros módulos trazem (`MODULOS_COM_PROCESSOS`):
    # contar só `SEMENTES` ficaria vermelho no primeiro módulo (as despesas).
    assert len(todos) == len(PROC.todas_as_sementes())
    assert not any(p["ativo"] or p["pode_agir"] for p in todos)
    codigos = {p["codigo"] for p in todos}
    assert {"PROTESTO_CRA", "PROTESTO_CENPROT", "RI_ONR_FILA", "RI_WSOFICIO", "RI_CNIB", "RCPN_SIRC",
            "RCPN_CRC", "CASA_MALOTE", "CASA_CENSEC", "CASA_BACKUP", "CASA_DISCO", "CASA_SELADOR",
            "ROTINA_CONFERENCIA_DIARIA", "ROTINA_COMPLIANCE", "ROTINA_CENSEC_ENVIO"} <= codigos
    cra = next(p for p in todos if p["codigo"] == "PROTESTO_CRA")
    assert cra["agenda"]["horarios"] == ["11:30", "14:10"]
    # A função de fábrica está no catálogo da casa; a que outro módulo trouxe
    # mora no módulo dele.
    trazidos = {s["alvo"] for s in PROC.sementes_de_outros_modulos()}
    assert all(p["alvo"] in PROC.CATALOGO or p["alvo"] in trazidos
               for p in todos if p["tipo"] == SCH.FUNCAO)


def test_o_tique_lanca_o_que_venceu_e_so_uma_vez(casa):
    db = casa["db"]
    p = _ligar(db, "CASA_DISCO", SEG - timedelta(hours=3))
    lancados = []
    r = _tique(db, agora=SEG.replace(minute=1), lancar=lambda i: lancados.append(i) or 4242)
    assert "CASA_DISCO" in r["lancadas"] and len(lancados) == 1
    with db.connect() as con:
        e = AU.execucao(con, lancados[0])
        assert e["situacao"] == SCH.RODANDO and e["pid"] == 4242 and e["disparo"] == SCH.AGENDA
    # o minuto seguinte, com a rodada de pé e o mesmo horário: nada
    r2 = _tique(db, agora=SEG.replace(minute=2), lancar=lambda i: lancados.append(i) or 4243,
                  vivo=lambda pid: True)
    assert r2["lancadas"] == [] and r2["puladas"] == [] and len(lancados) == 1
    with db.connect() as con:
        assert AU.batida_do_despachante(con, SEG.replace(minute=3))["parado"] is False


def test_a_rodada_que_vence_com_a_anterior_de_pe_vira_pulada_uma_vez(casa):
    db = casa["db"]
    _ligar(db, "CASA_DISCO", SEG - timedelta(hours=3))
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET timeout_s=7200 WHERE codigo='CASA_DISCO'")
    _tique(db, agora=SEG.replace(minute=1), lancar=lambda i: 1)
    vivo = lambda pid: True  # noqa: E731
    r = _tique(db, agora=SEG.replace(hour=10, minute=0), lancar=lambda i: 2, vivo=vivo)
    assert r["puladas"] == ["CASA_DISCO"]
    r = _tique(db, agora=SEG.replace(hour=10, minute=1), lancar=lambda i: 3, vivo=vivo)
    assert r["puladas"] == []
    with db.connect() as con:
        hist = AU.execucoes(con, _processo(db, "CASA_DISCO")["id"])
    assert [e["situacao"] for e in hist] == [SCH.PULADA, SCH.RODANDO]


def test_a_trava_global_e_de_um_tique_so(casa):
    db = casa["db"]
    with db.transaction() as con:
        assert AU.adquirir_trava(con, "a", SEG)
        assert not AU.adquirir_trava(con, "b", SEG + timedelta(minutes=1))
    assert _tique(db, agora=SEG + timedelta(minutes=2), lancar=lambda i: 1) == {"trava": "ocupada"}
    with db.transaction() as con:     # o tique morto larga a trava depois de 10 minutos
        assert AU.adquirir_trava(con, "c", SEG + timedelta(minutes=11))
        AU.soltar_trava(con, "c", SEG + timedelta(minutes=11))


def test_a_rodada_que_morreu_vira_interrompida_e_abre_tarefa(casa):
    db = casa["db"]
    _ligar(db, "CASA_DISCO", SEG - timedelta(hours=3))
    lancados = []
    _tique(db, agora=SEG.replace(minute=1), lancar=lambda i: lancados.append(i) or 99999)
    r = _tique(db, agora=SEG.replace(minute=5), lancar=lambda i: 1, vivo=lambda pid: False)
    assert r["recuperadas"] == [{"execucao_id": lancados[0], "situacao": SCH.INTERROMPIDA}]
    with db.connect() as con:
        tarefas = banco(con).ler("SELECT * FROM tasks WHERE source_type='AUTOMACAO'")
        p = _processo(db, "CASA_DISCO")
    assert len(tarefas) == 1 and p["alerta_situacao"] == SCH.INTERROMPIDA


def test_a_rodada_muito_alem_do_prazo_e_encerrada_a_forca(casa):
    db = casa["db"]
    _ligar(db, "CASA_DISCO", SEG - timedelta(hours=3))
    lancados, mortos = [], []
    _tique(db, agora=SEG.replace(minute=1), lancar=lambda i: lancados.append(i) or 777)
    AU.recuperar(db, SEG + timedelta(hours=2), vivo=lambda pid: True, matar=mortos.append)
    assert mortos == [777]
    with db.connect() as con:
        assert AU.execucao(con, lancados[0])["situacao"] == SCH.TEMPO_ESGOTADO


def test_o_corredor_mata_o_script_que_passa_do_prazo(casa, tmp_path):
    db = casa["db"]
    # desde 26/10/2026 (revisão de segurança, M2) só roda script da pasta própria
    (tmp_path / AU.PASTA_DOS_SCRIPTS).mkdir()
    (tmp_path / AU.PASTA_DOS_SCRIPTS / "dorme.py").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    p = _processo(db, "CASA_DISCO")
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET tipo=%s, alvo=%s, timeout_s=2 WHERE id=%s",
                            (SCH.SCRIPT, f"{AU.PASTA_DOS_SCRIPTS}/dorme.py", p["id"]))
        e = AU._criar_execucao(con, AU.obter(con, p["id"]), disparo=SCH.MANUAL, agendada_para=None,
                               quem="mario", agora=SEG)
    final = AU.executar(db, e, raiz=tmp_path, pasta_dados=tmp_path)
    assert final["situacao"] == SCH.TEMPO_ESGOTADO and "prazo" in final["relato"]


def test_o_corredor_le_o_resultado_e_tenta_de_novo_quem_falhou(casa):
    db = casa["db"]
    p = _processo(db, "CASA_DISCO")
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET max_tentativas=2 WHERE id=%s", (p["id"],))
        e = AU._criar_execucao(con, AU.obter(con, p["id"]), disparo=SCH.MANUAL, agendada_para=None,
                               quem="mario", agora=SEG)
    respostas = [{"codigo": 1, "saida": "", "erro": "caiu", "esgotou": False, "segundos": 0},
                 {"codigo": 0, "saida": AU.MARCA_DO_RESULTADO + json.dumps(
                     {"situacao": "OK", "relato": "tudo certo"}), "erro": "", "esgotou": False, "segundos": 0}]
    final = AU.executar(db, e, rodar=lambda *a, **k: respostas.pop(0), pausa=lambda s: None)
    assert final["situacao"] == SCH.OK and final["tentativas"] == 2


def test_o_trabalho_roda_a_verificacao_no_mesmo_contrato(casa, tmp_path):
    db = casa["db"]
    p = _processo(db, "CASA_DISCO")
    with db.transaction() as con:
        e = AU._criar_execucao(con, p, disparo=SCH.MANUAL, agendada_para=None, quem="mario", agora=SEG)
    r = AU.trabalho(db, e, pasta_dados=tmp_path)
    assert r["situacao"] in (SCH.OK, SCH.AVISO, SCH.ERRO) and "GB livres" in r["relato"]


def _finalizar(db, codigo, situacao, quando, relato="x"):
    p = _processo(db, codigo)
    with db.transaction() as con:
        e = AU._criar_execucao(con, p, disparo=SCH.MANUAL, agendada_para=None, quem="t", agora=quando)
    return AU.finalizar(db, e, {"situacao": situacao, "relato": relato}, agora=quando)


def _avisos(db, codigo):
    with db.connect() as con:
        return banco(con).ler("SELECT * FROM au_avisos WHERE processo_id=%s ORDER BY id",
                              (_processo(db, codigo)["id"],))


def test_o_aviso_sai_na_transicao_e_lembra_a_cada_n_horas(casa, monkeypatch):
    db = casa["db"]
    enviados = []
    monkeypatch.setitem(AV.ENVIO, "email", lambda cfg, senha, **k: enviados.append(k["assunto"]))
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_SMTP_HOST, "smtp.exemplo.invalid")
        SCH.gravar_config(con, SCH.CHAVE_EMAIL_DESTINO, "oficial@exemplo.invalid")
        SCH.gravar_config(con, SCH.CHAVE_LEMBRAR, "4")
    _finalizar(db, "CASA_BACKUP", SCH.ERRO, SEG, "o backup falhou")
    primeiro = _avisos(db, "CASA_BACKUP")
    assert {a["canal"] for a in primeiro} == {SCH.PAINEL, SCH.TAREFA, SCH.EMAIL, SCH.WHATSAPP}
    assert {a["motivo"] for a in primeiro} == {SCH.ALERTA}
    whats = next(a for a in primeiro if a["canal"] == SCH.WHATSAPP)
    assert whats["situacao"] == SCH.PENDENTE_CONFIG
    assert len(enviados) == 1
    # um minuto depois, de novo: NADA (sem spam)
    _finalizar(db, "CASA_BACKUP", SCH.ERRO, SEG + timedelta(minutes=1))
    assert len(_avisos(db, "CASA_BACKUP")) == len(primeiro) and len(enviados) == 1
    # cinco horas depois: o lembrete
    _finalizar(db, "CASA_BACKUP", SCH.ERRO, SEG + timedelta(hours=5))
    assert {a["motivo"] for a in _avisos(db, "CASA_BACKUP")} == {SCH.ALERTA, SCH.LEMBRETE}
    with db.connect() as con:
        abertas = banco(con).ler("SELECT * FROM tasks WHERE source_type='AUTOMACAO' AND status='ABERTA'")
    assert len(abertas) == 1                                  # o lembrete virou nota, não outra tarefa
    # voltou a rodar bem: a tarefa se fecha e o alerta some
    _finalizar(db, "CASA_BACKUP", SCH.OK, SEG + timedelta(hours=6))
    with db.connect() as con:
        t = banco(con).um("SELECT status FROM tasks WHERE id=%s", (abertas[0]["id"],))
        p = AU.por_codigo(con, "CASA_BACKUP")
        assert AU.contar_problemas(con) == 0
    assert t["status"] == "CONCLUIDA" and p["alerta_desde"] is None
    assert SCH.NORMALIZOU in {a["motivo"] for a in _avisos(db, "CASA_BACKUP")}


def test_o_email_sem_configuracao_fica_pendente_e_nao_se_da_por_enviado(casa):
    db = casa["db"]
    _finalizar(db, "CASA_DISCO", SCH.AVISO, SEG)
    email = next(a for a in _avisos(db, "CASA_DISCO") if a["canal"] == SCH.EMAIL)
    assert email["situacao"] == SCH.PENDENTE_CONFIG


def test_a_senha_do_email_mora_fora_do_cofre_e_sai_com_ele_trancado(casa, tmp_path, monkeypatch):
    """O aviso «o cofre está trancado» precisa sair por e-mail com o cofre trancado."""
    import automacao_cofre as AC
    db = casa["db"]
    AV.gravar_senha_do_smtp(tmp_path, "token-smtp-de-teste")
    assert b"token-smtp-de-teste" not in (tmp_path / SCH.ARQUIVO_SMTP).read_bytes()   # cifrado
    assert AV.tem_senha_do_smtp(tmp_path)

    def trancado(*a, **k):
        raise AC.CofreTrancado("o cofre está trancado")
    monkeypatch.setattr(AC, "ler", trancado)            # o cofre da senha-mestra não é consultado
    senhas = []
    monkeypatch.setitem(AV.ENVIO, "email", lambda cfg, senha, **k: senhas.append(senha))
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_SMTP_HOST, "smtp.exemplo.invalid")
        SCH.gravar_config(con, SCH.CHAVE_SMTP_USUARIO, "alertas@exemplo.invalid")
        SCH.gravar_config(con, SCH.CHAVE_EMAIL_DESTINO, "oficial@exemplo.invalid")
    r = AV.enviar_teste(db, agora=SEG, pasta_dados=tmp_path, pedido_por="mario")
    assert senhas == ["token-smtp-de-teste"]
    assert r["situacao"] == SCH.ENVIADO


def test_a_tela_grava_a_senha_do_email_no_arquivo_e_nao_no_cofre(casa):
    import automacao_cofre as AC
    c = _entrar(casa, "mario", "ADMIN")
    html = c.get("/automacao/configuracao").get_data(as_text=True)
    assert "conta de e-mail só para os alertas" in html
    r = c.post("/automacao/configuracao", data={
        "csrf_token": _token(html), SCH.CHAVE_SMTP_HOST: "smtp.exemplo.invalid",
        SCH.CHAVE_SMTP_SEGURANCA: "STARTTLS", "smtp_senha": "token-pela-tela"})
    assert r.status_code == 302
    pasta = Path(str(casa["db"].db_path.parent))
    assert AV._senha_do_smtp(pasta, {"usuario": "x"}) == "token-pela-tela"
    assert not AC.tem("smtp", caminho=AC.caminho_do_cofre(pasta))
    assert "guardada — digite só para trocar" in c.get("/automacao/configuracao").get_data(as_text=True)


def test_o_problema_que_piora_avisa_de_novo(casa):
    db = casa["db"]
    _finalizar(db, "CASA_DISCO", SCH.AVISO, SEG)
    _finalizar(db, "CASA_DISCO", SCH.ERRO, SEG + timedelta(minutes=1))
    assert SCH.PIOROU in {a["motivo"] for a in _avisos(db, "CASA_DISCO")}


def test_a_rodada_bate_o_ponto_no_quadro_antigo_dos_robos(casa):
    db = casa["db"]
    _finalizar(db, "RCPN_SIRC", SCH.AVISO, SEG)
    import oficial_robos
    with db.connect() as con:
        b = oficial_robos.ultima_batida(con, "CARGAS_RCPN")
    assert b and b["situacao"] == "AVISO" and b["resumo"]["processo"] == "RCPN_SIRC"


def test_pode_agir_e_so_do_admin(casa):
    db = casa["db"]
    p = _processo(db, "PROTESTO_CENPROT")
    with db.transaction() as con:
        with pytest.raises(AU.AutomacaoRecusada):
            AU.definir_pode_agir(con, p["id"], True, papel="MANAGER", usuario="beatriz")
        with pytest.raises(AU.AutomacaoRecusada):
            AU.salvar(con, p["id"], {"pode_agir": True}, usuario="beatriz")
        assert AU.definir_pode_agir(con, p["id"], True, papel="ADMIN", usuario="mario")["pode_agir"]


def test_processo_de_ia_nao_leva_credencial(casa):
    db = casa["db"]
    p = _processo(db, "CASA_DISCO")
    with db.transaction() as con:
        with pytest.raises(AU.AutomacaoRecusada):
            AU.salvar(con, p["id"], {"tipo": SCH.AGENTE_IA, "alvo": "confira a casa",
                                     "usa_credencial": "sirc_certificado"}, usuario="mario")


def test_a_escrita_do_agente_segue_o_pode_agir(casa, monkeypatch, tmp_path):
    import agente as AGT
    import agente_schema as AGS
    vistos = []

    def falso_pedir(db, **k):
        vistos.append((AGS.escrita_ligada(None), AGS.escrita_sem_confirmacao(None)))
        return {"sessao": {"id": 1, "estado": AGS.CONCLUIDA, "turnos": 2},
                "passos": [{"tipo": AGS.TEXTO, "conteudo": "conferi e anotei"}],
                "mudancas": [{"ferramenta": "anotar_no_problema", "alvo": "#3", "reversivel": 1,
                              "situacao": "APLICADA"}]}
    monkeypatch.setattr(AGT, "pedir", falso_pedir)
    base = {"codigo": "IA_TESTE", "alvo": "confira a casa", "parametros": {}}
    for pode in (False, True):
        ctx = PROC.Contexto(db=casa["db"], agora=SEG, pasta_dados=tmp_path, raiz=RAIZ,
                            processo={**base, "pode_agir": pode})
        r = PROC.rodar_agente(ctx)
        assert r["situacao"] == SCH.OK and r["relato"] == "conferi e anotei"
        assert r["acoes"][0]["ferramenta"] == "anotar_no_problema"
    assert vistos == [(False, False), (True, True)]
    with casa["db"].connect() as con:      # fora do processo, volta a valer a config
        assert AGS.escrita_ligada(con) is False


# ------------------------------------------------------------------ as verificações


def _ctx(db, tmp_path, parametros=None, **extra):
    return PROC.Contexto(db=db, agora=SEG, pasta_dados=tmp_path, raiz=RAIZ,
                         processo={"codigo": "T", "parametros": parametros or {}, **extra})


def test_o_disco_tem_as_duas_faixas(casa, tmp_path):
    db = casa["db"]
    assert PROC.verificar_disco(_ctx(db, tmp_path, {"aviso_gb": 1e9, "critico_gb": 0}))["situacao"] == SCH.AVISO
    assert PROC.verificar_disco(_ctx(db, tmp_path, {"aviso_gb": 1e9, "critico_gb": 1e8}))["situacao"] == SCH.ERRO
    assert PROC.verificar_disco(_ctx(db, tmp_path, {"aviso_gb": 0, "critico_gb": 0}))["situacao"] == SCH.OK


def test_o_backup_e_julgado_pelo_arquivo_de_estado(casa, tmp_path):
    db = casa["db"]
    assert PROC.verificar_backup(_ctx(db, tmp_path))["situacao"] == SCH.AVISO     # sem caminho
    estado = tmp_path / "ESTADO_DO_BACKUP.json"
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_BACKUP_ESTADO, str(estado))
    assert PROC.verificar_backup(_ctx(db, tmp_path))["situacao"] == SCH.ERRO      # não existe: não mediu
    estado.write_text(json.dumps({"ok": True, "ok_local": True, "ok_fora": True, "avisos": [],
                                  "terminou": (SEG - timedelta(hours=3)).isoformat()}), encoding="utf-8")
    assert PROC.verificar_backup(_ctx(db, tmp_path))["situacao"] == SCH.OK
    estado.write_text(json.dumps({"ok": True, "terminou": (SEG - timedelta(hours=40)).isoformat()}),
                      encoding="utf-8")
    assert PROC.verificar_backup(_ctx(db, tmp_path))["situacao"] == SCH.ERRO      # velho
    estado.write_text(json.dumps({"ok": False, "ok_local": True,
                                  "terminou": (SEG - timedelta(hours=2)).isoformat()}), encoding="utf-8")
    assert PROC.verificar_backup(_ctx(db, tmp_path))["situacao"] == SCH.AVISO


def test_o_log_da_rotina_de_fora(casa, tmp_path):
    db = casa["db"]
    log = tmp_path / "rotina.log"
    log.write_text("lendo\nFEITO: 0 minutas e tarefas.\n", encoding="utf-8")
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_CNIB_LOG, str(log))
    params = {"chave_config": SCH.CHAVE_CNIB_LOG, "nome": "as minutas", "horas": 10 ** 6,
              "padrao_ok": "FEITO:", "padrao_erro": "Traceback"}
    assert PROC.verificar_log(_ctx(db, tmp_path, params))["situacao"] == SCH.OK
    log.write_text("Traceback (most recent call last)\n", encoding="utf-8")
    assert PROC.verificar_log(_ctx(db, tmp_path, params))["situacao"] == SCH.ERRO


def test_central_sem_credencial_e_aviso_e_nao_queda(casa, tmp_path):
    db = casa["db"]
    for funcao in (PROC.verificar_cra, PROC.verificar_cenprot, PROC.verificar_onr_fila):
        r = funcao(_ctx(db, tmp_path))
        assert r["situacao"] == SCH.AVISO and "credencial" in r["relato"]


def test_o_sirc_vazio_esta_em_dia(casa, tmp_path):
    assert PROC.verificar_sirc(_ctx(casa["db"], tmp_path))["situacao"] == SCH.OK


# ------------------------------------------------------------------ o cofre trancado no hub


def test_processo_com_credencial_e_cofre_trancado_vira_aviso_e_os_outros_rodam(casa, tmp_path):
    """Máquina reiniciou e ninguém digitou a senha: AVISO «cofre trancado», sem erro técnico."""
    db = casa["db"]
    (tmp_path / AU.PASTA_DOS_SCRIPTS).mkdir()
    (tmp_path / AU.PASTA_DOS_SCRIPTS / "usa_cred.py").write_text("print('nao devia rodar')\n", encoding="utf-8")
    p = _processo(db, "CASA_DISCO")
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET tipo=%s, alvo=%s, usa_credencial=%s WHERE id=%s",
                            (SCH.SCRIPT, f"{AU.PASTA_DOS_SCRIPTS}/usa_cred.py", "banco_cobranca", p["id"]))
        e = AU._criar_execucao(con, AU.obter(con, p["id"]), disparo=SCH.MANUAL, agendada_para=None,
                               quem="mario", agora=SEG)
    final = AU.executar(db, e, raiz=tmp_path, pasta_dados=tmp_path,
                        rodar=lambda *a, **k: pytest.fail("rodou sem a credencial"))
    assert final["situacao"] == SCH.AVISO and "Cofre trancado" in final["relato"] and not final["erro"]
    assert {a["motivo"] for a in _avisos(db, "CASA_DISCO")} == {SCH.ALERTA}       # pede ao oficial
    # a verificação do sistema que usa credencial também
    q = _processo(db, "CASA_BACKUP")
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET usa_credencial='smtp' WHERE id=%s", (q["id"],))
        e2 = AU._criar_execucao(con, AU.obter(con, q["id"]), disparo=SCH.MANUAL, agendada_para=None,
                                quem="mario", agora=SEG)
    assert AU.trabalho(db, e2, pasta_dados=tmp_path)["situacao"] == SCH.AVISO
    # e a sem credencial roda normalmente
    with db.transaction() as con:
        e3 = AU._criar_execucao(con, _processo(db, "CASA_SELADOR"), disparo=SCH.MANUAL, agendada_para=None,
                                quem="mario", agora=SEG)
    assert "Cofre trancado" not in AU.trabalho(db, e3, pasta_dados=tmp_path)["relato"]


def test_a_validade_do_cofre_avisa_90_dias_antes(casa, tmp_path):
    import automacao_cofre as C
    caminho = C.caminho_do_cofre(tmp_path)
    chave = C.criar(caminho, "senha-mestra-de-teste-1", kdf={"nome": "scrypt", "n": 2 ** 10, "r": 8, "p": 1})
    from datetime import date
    hoje = date.today()
    C.gravar_com_chave(caminho, chave, "longe", {"senha": "a1"}, tipo=C.SENHA,
                       validade=(hoje + timedelta(days=300)).isoformat(), por="mario")
    ctx = _ctx(casa["db"], tmp_path, {"dias_antes": 90})
    assert PROC.verificar_validade_do_cofre(ctx)["situacao"] == SCH.OK
    C.gravar_com_chave(caminho, chave, "perto", {"senha": "a1"}, tipo=C.CERTIFICADO,
                       validade=(hoje + timedelta(days=60)).isoformat(), por="mario")
    r = PROC.verificar_validade_do_cofre(ctx)
    assert r["situacao"] == SCH.AVISO and "perto" in r["relato"]
    C.gravar_com_chave(caminho, chave, "velho", {"senha": "a1"}, tipo=C.SENHA,
                       validade=(hoje - timedelta(days=1)).isoformat(), por="mario")
    assert PROC.verificar_validade_do_cofre(ctx)["situacao"] == SCH.ERRO


# ------------------------------------------------------------------ as telas


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(casa, usuario, papel):
    from tests.conftest import cg_login
    if usuario != "mario":
        casa["db"].create_user(usuario, f"{usuario.title()} Exemplo", SENHA, papel)
    c = casa["app"].test_client()
    cg_login(c, usuario, SENHA)
    return c


def test_as_telas_abrem_para_o_admin(casa):
    c = _entrar(casa, "mario", "ADMIN")
    db = casa["db"]
    _finalizar(db, "CASA_DISCO", SCH.AVISO, SEG, "disco apertado")
    p = _processo(db, "CASA_DISCO")
    with db.connect() as con:
        e = AU.execucoes(con, p["id"])[0]
    for url in ("/automacao", f"/automacao/{p['id']}", f"/automacao/execucoes/{e['id']}",
                "/automacao/configuracao", "/automacao/cofre", "/automacao/cofre/desbloquear"):
        r = c.get(url)
        assert r.status_code == 200, url
    assert "disco apertado" in c.get(f"/automacao/execucoes/{e['id']}").get_data(as_text=True)
    assert "Automação (rotinas)" in c.get("/").get_data(as_text=True)


def test_o_gerente_ve_e_nao_mexe(casa):
    c = _entrar(casa, "beatriz", "MANAGER")
    p = _processo(casa["db"], "PROTESTO_CENPROT")
    assert c.get("/automacao").status_code == 200
    assert c.get(f"/automacao/{p['id']}").status_code == 200
    assert c.get("/automacao/configuracao").status_code == 403
    assert c.get("/automacao/cofre").status_code == 403
    assert c.get("/automacao/cofre/desbloquear").status_code == 403
    html = c.get("/automacao").get_data(as_text=True)
    r = c.post(f"/automacao/{p['id']}/pode-agir", data={"pode_agir": "1", "csrf_token": _token(html)})
    assert r.status_code == 403
    assert not _processo(casa["db"], "PROTESTO_CENPROT")["pode_agir"]


def test_o_escrevente_nao_entra(casa):
    c = _entrar(casa, "carla", "USER")
    assert c.get("/automacao").status_code == 403


def test_pode_agir_pela_tela_vai_a_auditoria(casa):
    c = _entrar(casa, "mario", "ADMIN")
    p = _processo(casa["db"], "PROTESTO_CENPROT")
    html = c.get(f"/automacao/{p['id']}").get_data(as_text=True)
    r = c.post(f"/automacao/{p['id']}/pode-agir", data={"pode_agir": "1", "csrf_token": _token(html)},
               follow_redirects=True)
    assert r.status_code == 200 and _processo(casa["db"], "PROTESTO_CENPROT")["pode_agir"]
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT COUNT(*) FROM audit_logs WHERE action='AUTOMACAO_PODE_AGIR'") == 1


def test_rodar_agora_so_enfileira(casa):
    c = _entrar(casa, "mario", "ADMIN")
    db = casa["db"]
    p = _processo(db, "CASA_DISCO")
    html = c.get(f"/automacao/{p['id']}").get_data(as_text=True)
    assert c.post(f"/automacao/{p['id']}/rodar", data={}).status_code == 400        # sem token
    r = c.post(f"/automacao/{p['id']}/rodar", data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "próximo minuto" in r.get_data(as_text=True)
    with db.connect() as con:
        assert AU.execucoes(con, p["id"]) == []                                   # não rodou na tela
    assert _processo(db, "CASA_DISCO")["pedido_manual_em"]
    lancados = []
    _tique(db, lancar=lambda i: lancados.append(i) or 1)                       # o despachante pega
    with db.connect() as con:
        e = AU.execucoes(con, p["id"])[0]
    assert e["disparo"] == SCH.MANUAL and lancados == [e["id"]]
    assert not _processo(db, "CASA_DISCO")["pedido_manual_em"]


def test_editar_a_agenda_pela_tela(casa):
    c = _entrar(casa, "mario", "ADMIN")
    p = _processo(casa["db"], "CASA_DISCO")
    html = c.get(f"/automacao/{p['id']}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "nome": p["nome"], "descricao": "", "setor": "TI",
             "tipo": SCH.FUNCAO, "alvo": p["alvo"], "parametros": '{"aviso_gb": 30}',
             "dias": ["0", "2"], "forma": "horarios", "horarios": "07:00, 19:00",
             "timeout_s": "60", "max_tentativas": "1", "canal_PAINEL": "1"}
    c.post(f"/automacao/{p['id']}/salvar", data=dados, follow_redirects=True)
    novo = _processo(casa["db"], "CASA_DISCO")
    assert novo["agenda"] == {"dias": [0, 2], "horarios": ["07:00", "19:00"]}
    assert novo["parametros"] == {"aviso_gb": 30} and novo["canais"][SCH.PAINEL] is True
    assert novo["canais"][SCH.EMAIL] is False


def test_desbloquear_pela_tela_so_da_propria_maquina(casa):
    c = _entrar(casa, "mario", "ADMIN")
    assert c.get("/automacao/cofre/desbloquear").status_code == 200
    assert c.get("/automacao/cofre/desbloquear", environ_base={"REMOTE_ADDR": "192.0.2.10"}).status_code == 403


def test_outro_modulo_traz_processos_e_ausente_nao_quebra(monkeypatch):
    """O módulo das despesas (outro PR) traz DESPESAS_PAGAR e DESPESAS_CONCILIAR
    pelo `CATALOGO` dele; se ele não estiver instalado, nada é semeado."""
    import sys
    import types
    import automacao_processos as PROC

    monkeypatch.setattr(PROC, "MODULOS_COM_PROCESSOS", ("modulo_que_nao_existe_xyz",))
    assert PROC.sementes_de_outros_modulos() == []

    falso = types.ModuleType("despesas_falso_teste")
    falso.CATALOGO = [
        {"codigo": "DESPESAS_PAGAR", "nome": "Pagar", "setor": "GESTAO",
         "funcao": "despesas_falso_teste.pagar"},
        {"codigo": "PROTESTO_CRA", "nome": "repetido", "funcao": "x.y"},
        {"codigo": "", "funcao": "sem.codigo"},
    ]
    monkeypatch.setitem(sys.modules, "despesas_falso_teste", falso)
    monkeypatch.setattr(PROC, "MODULOS_COM_PROCESSOS", ("despesas_falso_teste",))
    trazidas = PROC.sementes_de_outros_modulos()
    assert [s["codigo"] for s in trazidas] == ["DESPESAS_PAGAR", "PROTESTO_CRA"]
    assert trazidas[0]["alvo"] == "despesas_falso_teste:pagar"
    assert trazidas[0]["agenda"]["intervalo_min"] == 15

    todas = PROC.todas_as_sementes()
    codigos = [s["codigo"] for s in todas]
    assert codigos.count("PROTESTO_CRA") == 1
    assert "DESPESAS_PAGAR" in codigos


# ------------------------------------------- revisão de segurança de 26/10/2026 (PR #11)


def test_a_tela_so_manda_rodar_funcao_da_lista_e_script_da_pasta_propria(casa, tmp_path):
    """M2: o ADMIN da tela não ganha execução de código no sistema operacional."""
    db = casa["db"]
    p = _processo(db, "CASA_DISCO")
    raiz = tmp_path / "programa"
    (raiz / AU.PASTA_DOS_SCRIPTS).mkdir(parents=True)
    (raiz / "automacao_processos.py").write_text("", encoding="utf-8")
    (raiz / "tools").mkdir()
    (raiz / "tools" / "migrar.py").write_text("print('perigo')\n", encoding="utf-8")
    (raiz / AU.PASTA_DOS_SCRIPTS / "conferir.py").write_text("print('ok')\n", encoding="utf-8")
    (raiz / AU.PASTA_DOS_SCRIPTS / "lancar.ps1").write_text("Write-Output 1\n", encoding="utf-8")
    (raiz / AU.PASTA_DOS_SCRIPTS / "lancar.cmd").write_text("echo 1\n", encoding="utf-8")
    recusados = [
        (SCH.FUNCAO, "automacao_processos:resultado"),        # existe, mas não é verificação
        (SCH.FUNCAO, "os:system"),
        (SCH.SCRIPT, "tools/migrar.py"),                     # script do pacote, fora da pasta própria
        (SCH.SCRIPT, f"{AU.PASTA_DOS_SCRIPTS}/../tools/migrar.py"),
        (SCH.SCRIPT, f"{AU.PASTA_DOS_SCRIPTS}/lancar.ps1"),
        (SCH.SCRIPT, f"{AU.PASTA_DOS_SCRIPTS}/lancar.cmd"),
        (SCH.SCRIPT, f"{AU.PASTA_DOS_SCRIPTS}/nao_existe.py"),
    ]
    for tipo, alvo in recusados:
        with db.transaction() as con, pytest.raises(AU.AutomacaoError):
            AU.salvar(con, p["id"], {"tipo": tipo, "alvo": alvo}, usuario="mario", raiz=raiz)
    with db.transaction() as con:
        assert AU.salvar(con, p["id"], {"tipo": SCH.FUNCAO, "alvo": "automacao_processos:verificar_disco"},
                         usuario="mario", raiz=raiz)["alvo"] == "automacao_processos:verificar_disco"
        assert AU.salvar(con, p["id"], {"tipo": SCH.SCRIPT, "alvo": f"{AU.PASTA_DOS_SCRIPTS}/conferir.py"},
                         usuario="mario", raiz=raiz)["tipo"] == SCH.SCRIPT
    # toda semente de fábrica continua aceita
    assert all(s["alvo"] in AU.funcoes_permitidas() for s in PROC.todas_as_sementes()
               if s.get("tipo", SCH.FUNCAO) == SCH.FUNCAO)


def test_alvo_gravado_por_fora_da_tela_tambem_nao_roda(casa, tmp_path):
    """M2: a régua vale na hora de rodar — script fora da pasta não roda nem
    recebe o segredo do cofre, e função fora da lista não importa módulo."""
    db = casa["db"]
    (tmp_path / "solto.py").write_text("print('nao devia rodar')\n", encoding="utf-8")
    p = _processo(db, "CASA_DISCO")
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET tipo=%s, alvo=%s, usa_credencial=%s WHERE id=%s",
                            (SCH.SCRIPT, "solto.py", "banco_cobranca", p["id"]))
        e = AU._criar_execucao(con, AU.obter(con, p["id"]), disparo=SCH.MANUAL, agendada_para=None,
                               quem="mario", agora=SEG)
    final = AU.executar(db, e, raiz=tmp_path, pasta_dados=tmp_path,
                        rodar=lambda *a, **k: pytest.fail("rodou script fora da pasta própria"))
    assert final["situacao"] == SCH.ERRO and AU.PASTA_DOS_SCRIPTS in final["relato"]
    q = _processo(db, "CASA_SELADOR")
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET alvo=%s WHERE id=%s", ("os:getcwd", q["id"]))
        e2 = AU._criar_execucao(con, AU.obter(con, q["id"]), disparo=SCH.MANUAL, agendada_para=None,
                                quem="mario", agora=SEG)
    r = AU.trabalho(db, e2, pasta_dados=tmp_path)
    assert r["situacao"] == SCH.ERRO and "não está na lista" in r["relato"]


def test_a_auditoria_da_edicao_leva_os_parametros(casa):
    c = _entrar(casa, "mario", "ADMIN")
    p = _processo(casa["db"], "CASA_DISCO")
    html = c.get(f"/automacao/{p['id']}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "nome": p["nome"], "descricao": "", "setor": "TI",
             "tipo": SCH.FUNCAO, "alvo": p["alvo"], "parametros": '{"aviso_gb": 31}',
             "dias": ["0"], "forma": "horarios", "horarios": "07:00", "timeout_s": "60",
             "max_tentativas": "1"}
    c.post(f"/automacao/{p['id']}/salvar", data=dados, follow_redirects=True)
    with casa["db"].connect() as con:
        detalhe = banco(con).valor("SELECT details FROM audit_logs WHERE action='AUTOMACAO_ALTERADO' "
                                   "ORDER BY id DESC LIMIT 1")
    assert "aviso_gb" in str(detalhe) and "31" in str(detalhe)


def test_a_verificacao_so_le_arquivo_das_pastas_da_casa_e_nao_mostra_o_texto(casa, tmp_path):
    """M3: o caminho da configuração não abre qualquer arquivo da máquina, e o
    texto do log não vai para `detalhe_tecnico` (que o gerente lê)."""
    db = casa["db"]
    dados = tmp_path / "dados"
    fora = tmp_path / "fora"
    (dados / "logs").mkdir(parents=True)
    fora.mkdir()
    segredo = "linha-secreta-do-arquivo-xyz"
    params = {"chave_config": SCH.CHAVE_CNIB_LOG, "nome": "as minutas", "horas": 10 ** 6,
              "padrao_erro": "."}
    # fora da pasta de dados: não lê
    (fora / "pgpass.log").write_text(segredo + "\n", encoding="utf-8")
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_CNIB_LOG, str(fora / "pgpass.log"))
    r = PROC.verificar_log(_ctx(db, dados, params))
    assert r["situacao"] == SCH.AVISO and "fora da pasta" in r["relato"]
    assert segredo not in json.dumps(r, ensure_ascii=False)
    # dentro da pasta do cofre: não lê
    (dados / "cofre_automacao").mkdir()
    (dados / "cofre_automacao" / "guardiao.log").write_text(segredo + "\n", encoding="utf-8")
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_CNIB_LOG, str(dados / "cofre_automacao" / "guardiao.log"))
    assert PROC.verificar_log(_ctx(db, dados, params))["situacao"] == SCH.AVISO
    # sufixo que não é de log: não lê
    (dados / "logs" / "pgpass.conf").write_text(segredo + "\n", encoding="utf-8")
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_CNIB_LOG, str(dados / "logs" / "pgpass.conf"))
    assert PROC.verificar_log(_ctx(db, dados, params))["situacao"] == SCH.AVISO
    # o log de verdade: lê, julga, e o texto NÃO sai
    (dados / "logs" / "rotina.log").write_text("ERRO: " + segredo + "\n", encoding="utf-8")
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_CNIB_LOG, str(dados / "logs" / "rotina.log"))
    r = PROC.verificar_log(_ctx(db, dados, params))
    assert r["situacao"] == SCH.ERRO
    assert segredo not in json.dumps(r, ensure_ascii=False) and "1 linha" in r["detalhe_tecnico"]
    # o estado do backup: só com o nome dele, e só nas pastas da casa
    (fora / "ESTADO_DO_BACKUP.json").write_text(json.dumps({"ok": True, "terminou": SEG.isoformat()}),
                                                encoding="utf-8")
    (dados / "outro.json").write_text(json.dumps({"ok": True, "terminou": SEG.isoformat()}), encoding="utf-8")
    for caminho in (fora / "ESTADO_DO_BACKUP.json", dados / "outro.json"):
        with db.transaction() as con:
            SCH.gravar_config(con, SCH.CHAVE_BACKUP_ESTADO, str(caminho))
        assert PROC.verificar_backup(_ctx(db, dados))["situacao"] == SCH.AVISO, caminho


def test_o_robo_nao_alcanca_a_central_da_automacao(casa):
    """M4: nem a conta de robô que tenha ficado com papel de ADMIN (cadastro antigo)."""
    import selo_robo as SR
    app = casa["app"]
    rotas = [r.endpoint for r in app.url_map.iter_rules() if r.endpoint.startswith("automacao")]
    assert rotas and all(SR.rota_vedada_ao_robo(e) for e in rotas)
    db = casa["db"]
    db.create_user("robo_central", "Robo de Exemplo da Central", SENHA, "USER", eh_robo=1)
    with db.transaction() as con:
        banco(con).escrever("UPDATE users SET role='ADMIN' WHERE username=%s", ("robo_central",))
    from tests.conftest import cg_login
    c = app.test_client()
    cg_login(c, "robo_central", SENHA)
    for url in ("/automacao", "/automacao/configuracao", "/automacao/cofre"):
        assert c.get(url).status_code == 403, url

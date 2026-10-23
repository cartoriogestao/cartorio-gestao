"""O robô oficial: a saúde dos outros robôs, a mesa do oficial e a fila de decisões.

O QUE ESTES TESTES GUARDAM
    **Que robô quebrado calado aparece.** O caso que fez o módulo nascer: em
    09/10/2026 a leitura pela IA do gestor falhava em toda rodada desde 08/10
    («Opus 5.5» é nome de vitrine, a API recusa), e a conferência seguia
    «com sucesso». Aqui a falha seguida vira CRÍTICO, com o conserto escrito.

    **Que a tarefa do robô quebrado fecha sozinha** quando ele volta — e que o
    robô oficial não toca em tarefa de outra origem.

    **Que pergunta respondida não volta a abrir**, e que obrigação sem documento
    não ganha prazo: vira pergunta.

    **Que o modo «só ler» não grava nada** — é o modo de conferir contra a
    produção antes de ligar.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import oficial_decisoes as OD                                      # noqa: E402
import oficial_obrigacoes as OO                                    # noqa: E402
import oficial_pauta as OP                                         # noqa: E402
import oficial_robos as OR                                         # noqa: E402
import oficial_rotina as ROT                                       # noqa: E402

SENHA = "Senha#12345"
AGORA = datetime(2026, 10, 9, 15, 0, 0)
HOJE = AGORA.date()


@pytest.fixture()
def con(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("alberto", "ANALISTA DE SISTEMAS", SENHA, "ADMIN")
    db.create_user("beatriz", "BEATRIZ SANTOS", SENHA, "MANAGER")
    c = sqlite3.connect(cg_casa["banco"])
    import gestor_leitura
    import gestor_schema
    gestor_schema.init_gestor_schema(c)
    gestor_leitura.init_leitura_schema(c)
    c.commit()
    yield c
    c.close()


def _uid(con, login):
    return con.execute("SELECT id FROM users WHERE username=?", (login,)).fetchone()[0]


def _responsavel(con, setor, login, subst=None):
    con.execute("INSERT OR REPLACE INTO ge_responsaveis (setor, user_id, origem, definido_em, "
                "definido_por, substituto_id) VALUES (?,?,?,?,?,?)",
                (setor, _uid(con, login), "OFICIAL", "2026-10-06", "mario",
                 _uid(con, subst) if subst else None))


def _tarefa(con, titulo, *, dono, prazo=None, origem="MANUAL", substituto=None,
            status="ABERTA", expediente=None):
    agora = "2026-10-01T08:00:00"
    return con.execute(
        """INSERT INTO tasks (source_type, title, priority, status, due_date,
               assigned_user_id, backup_user_id, linked_expediente_id, created_at, updated_at)
           VALUES (?, ?, 'ALTA', ?, ?, ?, ?, ?, ?, ?)""",
        (origem, titulo, status, prazo, dono, substituto, expediente, agora, agora)).lastrowid


def _expediente(con, assunto, *, categoria="Para Cumprimento", stage="RECEBIDO", dono=None):
    agora = "2026-09-20T10:00:00"
    n = con.execute("SELECT count(*) FROM expedientes").fetchone()[0] + 1
    return con.execute(
        """INSERT INTO expedientes (internal_protocol, source, subject, category, received_at,
               stage, assigned_user_id, created_by, created_at, updated_at)
           VALUES (?, 'Malote Digital', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"EXP-T-{n:04d}", assunto, categoria, agora, stage, dono, dono or 1, agora,
         agora)).lastrowid


def _leitura(con, quando, erro=None, modelo="Opus 5.5", ato=1):
    con.execute(
        """INSERT INTO ge_leituras (tabela, ato_id, hash_dossie, lido_em, provedor, modelo,
               erro) VALUES ('ri_atos', ?, ?, ?, 'claude', ?, ?)""",
        (ato, f"h{ato}-{quando}", quando, modelo, erro))


ERRO_MODELO = ("AgenteError: O Claude (Anthropic) não conhece o modelo pedido. Confira o "
               "nome do modelo na tela de configuração do agente.")


# ------------------------------------------------------------------ saúde

def test_a_ia_parada_vira_critico_com_o_conserto_escrito(con):
    _leitura(con, "2026-10-07T07:30:00", ato=1)                       # a última que leu
    for i, h in enumerate(("2026-10-08T08:28:54", "2026-10-08T14:30:11",
                           "2026-10-09T14:00:06", "2026-10-09T14:00:08")):
        _leitura(con, h, erro=ERRO_MODELO, ato=10 + i)
    achados = [a for a in OR.saude(con, AGORA) if a["robo"] == "LEITURA_IA"]
    assert len(achados) == 1
    a = achados[0]
    assert a["gravidade"] == "CRITICO" and a["regra"] == "IA_PARADA"
    assert "4 falha(s) seguidas" in a["titulo"]
    assert "Opus 5.5" in a["como_resolver"] and "claude-opus-5-5" in a["como_resolver"]


def test_a_ia_que_voltou_a_ler_nao_acusa(con):
    for i, h in enumerate(("2026-10-08T08:28:54", "2026-10-08T14:30:11",
                           "2026-10-09T07:30:06")):
        _leitura(con, h, erro=ERRO_MODELO, ato=10 + i)
    _leitura(con, "2026-10-09T14:00:00", ato=99)
    assert not [a for a in OR.saude(con, AGORA) if a["robo"] == "LEITURA_IA"]


def test_duas_falhas_soltas_nao_sao_ia_parada(con):
    _leitura(con, "2026-10-09T07:30:00", erro="TimeoutError: rede", ato=1)
    _leitura(con, "2026-10-09T14:00:00", erro="TimeoutError: rede", ato=2)
    assert not [a for a in OR.saude(con, AGORA) if a["robo"] == "LEITURA_IA"]


def test_no_mesmo_segundo_a_frase_e_a_da_ultima_falha_gravada(con):
    """Empate no `lido_em`: vale a de `id` maior, como o SQLite devolvia. Sem o
    desempate, o PostgreSQL entrega o empate na ordem física, e a tela daria o
    conserto da falha anterior."""
    _leitura(con, "2026-10-09T07:30:00", erro="TimeoutError: rede", ato=1)
    for id_, erro in ((900, ERRO_MODELO), (800, "TimeoutError: rede")):  # fora da ordem do id
        con.execute(
            """INSERT INTO ge_leituras (id, tabela, ato_id, hash_dossie, lido_em, provedor,
                   modelo, erro) VALUES (?, 'ri_atos', ?, ?, '2026-10-09T14:00:00', 'claude',
                   'Opus 5.5', ?)""", (id_, id_, f"h{id_}", erro))
    a = [a for a in OR.saude(con, AGORA) if a["robo"] == "LEITURA_IA"][0]
    assert "não conhece o modelo" in a["detalhe"]
    assert "claude-opus-5-5" in a["como_resolver"]


def test_gestor_parado_e_gestor_com_erro(con):
    con.execute("INSERT INTO ge_execucoes (iniciada_em, terminada_em, hoje, erro) "
                "VALUES ('2026-10-08T07:30:00', '2026-10-08T07:31:00', '2026-10-08', "
                "'KeyError: x')")
    regras = {a["regra"] for a in OR.saude(con, AGORA) if a["robo"] == "GESTOR"}
    assert regras == {"ROBO_PARADO", "ROBO_TERMINOU_COM_ERRO"}


def test_gestor_em_dia_nao_acusa(con):
    con.execute("INSERT INTO ge_execucoes (iniciada_em, terminada_em, hoje, nao_mediu) "
                "VALUES ('2026-10-09T14:00:00', '2026-10-09T14:06:00', '2026-10-09', 0)")
    assert not [a for a in OR.saude(con, AGORA) if a["robo"] == "GESTOR"]


def test_robo_sem_ponto_e_informacao_e_nao_alarme(con):
    achados = {a["robo"]: a for a in OR.saude(con, AGORA)}
    assert achados["CARGAS_RCPN"]["gravidade"] == "INFO"
    assert achados["CARGAS_RCPN"]["regra"] == "ROBO_AINDA_NAO_LIGADO"


def test_o_contrato_e_uma_linha_e_a_batida_com_erro_vira_critico(con):
    OR.bater(con, "CARGAS_RI", situacao="OK", resumo={"cargas": 3})
    assert not [a for a in OR.saude(con, AGORA) if a["robo"] == "CARGAS_RI"]
    OR.bater(con, "CARGAS_RI", situacao="ERRO", erro="ValueError: lote")
    a = [a for a in OR.saude(con, datetime.now()) if a["robo"] == "CARGAS_RI"]
    assert [x["regra"] for x in a] == ["ROBO_TERMINOU_COM_ERRO"]
    assert a[0]["gravidade"] == "CRITICO"
    with pytest.raises(ValueError):
        OR.bater(con, "CARGAS_RI", situacao="MAIS_OU_MENOS")


def test_robo_que_parou_de_bater(con):
    import oficial_schema
    oficial_schema.init_oficial_schema(con)
    antiga = (AGORA - timedelta(hours=40)).isoformat()
    con.execute("INSERT INTO of_batidas (robo, iniciada_em, terminada_em, situacao) "
                "VALUES ('NOTAS', ?, ?, 'OK')", (antiga, antiga))
    a = [a for a in OR.saude(con, AGORA) if a["robo"] == "NOTAS"]
    assert [x["regra"] for x in a] == ["ROBO_PARADO"]


def test_agendador_so_acusa_resultado_que_nao_e_zero():
    tarefas = [
        {"tarefa": "CartorioGestao-Conferencia-Diaria", "ultimo_resultado": "0"},
        {"tarefa": "CartorioGestao-Minutas-CNIB", "ultimo_resultado": "1"},
        {"tarefa": "CartorioGestao-Minutas-CNIB", "ultimo_resultado": "1"},     # repetida
        {"tarefa": "CartorioGestao-Sandbox-8899", "ultimo_resultado": "267009"},
    ]
    achados = OR.saude_do_agendador(tarefas)
    assert [a["chave"] for a in achados] == ["AGENDADOR_FALHOU:CartorioGestao-Minutas-CNIB"]


def test_o_quadro_tem_uma_linha_por_robo(con):
    linhas = OR.quadro(con, AGORA)
    assert [r["codigo"] for r in linhas] == [r["codigo"] for r in OR.ROBOS]
    assert {r["situacao"] for r in linhas if r["codigo"] == "PROTESTO"} == {"SEM_PONTO"}


# ------------------------------------------------- tarefas dos robôs

def test_robo_quebrado_vira_tarefa_da_ti_e_fecha_sozinha(con):
    _responsavel(con, "TI", "alberto", subst="mario")
    alheia = _tarefa(con, "tarefa de gente", dono=_uid(con, "beatriz"), origem="GESTOR")
    for i, h in enumerate(("2026-10-08T08:28:54", "2026-10-09T07:30:00",
                           "2026-10-09T14:00:00")):
        _leitura(con, h, erro=ERRO_MODELO, ato=10 + i)
    achados = OR.saude(con, AGORA)
    r1 = ROT.sincronizar_tarefas_dos_robos(con, achados, HOJE)
    assert r1["criadas"] == 1
    t = con.execute("SELECT assigned_user_id, backup_user_id, priority, status, description "
                    "FROM tasks WHERE source_type='OFICIAL'").fetchone()
    assert t[0] == _uid(con, "alberto") and t[1] == _uid(con, "mario")
    assert t[2] == "CRITICA" and t[3] == "ABERTA" and "claude-opus-5-5" in t[4]
    r2 = ROT.sincronizar_tarefas_dos_robos(con, achados, HOJE)
    assert r2 == {"criadas": 0, "fechadas": 0, "atualizadas": 1}
    r3 = ROT.sincronizar_tarefas_dos_robos(con, [], HOJE)
    assert r3["fechadas"] == 1
    assert con.execute("SELECT status FROM tasks WHERE source_type='OFICIAL'"
                       ).fetchone()[0] == "CONCLUIDA"
    assert con.execute("SELECT status FROM tasks WHERE id=?", (alheia,)).fetchone()[0] == "ABERTA"


def test_robo_ainda_nao_ligado_nao_vira_tarefa(con):
    ROT.sincronizar_tarefas_dos_robos(con, OR.saude(con, AGORA), HOJE)
    assert con.execute("SELECT count(*) FROM tasks WHERE source_type='OFICIAL'"
                       ).fetchone()[0] == 0


def test_consulta_que_quebra_no_meio_da_transacao_nao_condena_a_rodada(con):
    """No PostgreSQL, comando que falha condena a transação inteira. O `except
    sqlite3.Error` de `saude` e de `_quem_cuida_da_ti` só vale se o comando
    seguinte ainda roda — e o que garante isso é o SAVEPOINT do `bd_nativo`."""
    con.execute("DROP TABLE ge_responsaveis")
    con.execute("ALTER TABLE ge_execucoes RENAME COLUMN nao_mediu TO nao_mediu_velho")
    con.commit()
    OR.bater(con, "CARGAS_RI", situacao="OK")
    assert con.in_transaction                        # como na rodada: a escrita já abriu
    achados = {a["robo"]: a for a in OR.saude(con, AGORA)}
    assert achados["GESTOR"]["regra"] == "NAO_MEDIU"
    assert "CARGAS_RI" not in achados                # o robô seguinte ainda foi medido
    dono = OP.dono_da_mesa(con)
    assert dono is not None and ROT._quem_cuida_da_ti(con) == (dono, None)
    con.commit()
    assert OR.ultima_batida(con, "CARGAS_RI")["situacao"] == "OK"


# ------------------------------------------------------------- decisões

def test_a_pergunta_entra_uma_vez_e_a_respondida_nao_reabre(con):
    a = OD.perguntar(con, chave="X", origem="RI", pergunta="Renumerar 4011 para 4014?",
                     opcoes=["sim", "não"], gravidade="CRITICO")
    b = OD.perguntar(con, chave="X", origem="RI", pergunta="Renumerar 4011 para 4014?")
    assert a == b and len(OD.abertas(con)) == 1
    OD.responder(con, a, "sim, depois da conferência da Beatriz", "mario")
    assert OD.abertas(con) == []
    OD.perguntar(con, chave="X", origem="RI", pergunta="Renumerar 4011 para 4014?")
    assert OD.abertas(con) == []
    with pytest.raises(OD.DecisaoError):
        OD.responder(con, a, "de novo", "mario")


def test_a_fila_vem_na_ordem_da_gravidade(con):
    OD.perguntar(con, chave="I", origem="X", pergunta="info", gravidade="INFO")
    OD.perguntar(con, chave="C", origem="X", pergunta="crítica", gravidade="CRITICO")
    OD.perguntar(con, chave="A", origem="X", pergunta="atenção", gravidade="ATENCAO")
    assert [d["chave"] for d in OD.abertas(con)] == ["C", "A", "I"]


def test_resposta_vazia_e_pergunta_sem_chave_sao_recusadas(con):
    with pytest.raises(OD.DecisaoError):
        OD.perguntar(con, chave="", origem="X", pergunta="?")
    d = OD.perguntar(con, chave="K", origem="X", pergunta="?")
    with pytest.raises(OD.DecisaoError):
        OD.responder(con, d, " ", "mario")


# --------------------------------------------------------- obrigações

def test_o_fic_de_setembro_vence_no_fim_de_outubro_como_na_circular():
    fic = next(o for o in OO.OBRIGACOES if o["codigo"] == "FIC_COTAS")
    prazo, ref = OO.proximo_vencimento(fic, date(2026, 10, 9))
    assert prazo == date(2026, 10, 31) and ref == "referência 09/2026"


def test_o_coaf_e_anual_e_so_entra_na_agenda_quando_perto():
    assert not [o for o in OO.agenda(date(2026, 10, 9)) if o["codigo"] == "COAF_NAO_OCORRENCIA"]
    coaf = [o for o in OO.agenda(date(2026, 12, 20)) if o["codigo"] == "COAF_NAO_OCORRENCIA"]
    assert coaf and coaf[0]["prazo"] == "2027-01-31" and coaf[0]["referencia"] == "ano de 2026"


def test_toda_obrigacao_com_prazo_diz_de_onde_saiu():
    for ob in OO.OBRIGACOES:
        assert ob["confirmada"] and ob["fundamento"] and ob["fonte"]


def test_o_que_nao_esta_medido_vira_pergunta_e_nao_prazo(con):
    OD.perguntar(con, **OO.pergunta_das_nao_medidas())
    d = OD.abertas(con)[0]
    assert d["chave"] == OO.PERGUNTA_DAS_OBRIGACOES
    for o in OO.A_CONFIRMAR:
        assert o["titulo"] in d["contexto"]
        assert o["codigo"] not in {x["codigo"] for x in OO.OBRIGACOES}


# ----------------------------------------------------------------- mesa

def test_a_mesa_separa_por_quando_e_deixa_o_despacho_de_fora(con):
    mario = _uid(con, "mario")
    _responsavel(con, "GESTAO", "mario")
    _tarefa(con, "vencida", dono=mario, prazo="2026-09-30")
    _tarefa(con, "hoje", dono=mario, prazo="2026-10-09")
    _tarefa(con, "semana", dono=mario, prazo="2026-10-14")
    _tarefa(con, "depois", dono=mario, prazo="2026-11-30")
    _tarefa(con, "sem prazo", dono=mario)
    _tarefa(con, "concluida", dono=mario, prazo="2026-09-01", status="CONCLUIDA")
    _tarefa(con, "[Despacho] o dia", dono=mario, prazo="2026-10-09", origem="DESPACHO")
    g = OP.tarefas(con, HOJE, mario)
    assert {k: [t["titulo"] for t in v] for k, v in g.items()} == {
        "VENCIDAS": ["vencida"], "HOJE": ["hoje"], "SEMANA": ["semana"],
        "DEPOIS": ["depois"], "SEM_PRAZO": ["sem prazo"]}
    assert OP.dono_da_mesa(con) == mario


def test_substituto_ve_o_que_o_titular_deixou_vencer(con):
    mario, lei = _uid(con, "mario"), _uid(con, "beatriz")
    _tarefa(con, "venceu", dono=lei, substituto=mario, prazo="2026-10-07")
    _tarefa(con, "no prazo", dono=lei, substituto=mario, prazo="2026-10-20")
    s = OP.substituicoes_vencidas(con, HOJE, mario)
    assert [(x["titulo"], x["dias_vencida"], x["titular"]) for x in s] == [
        ("venceu", 2, "BEATRIZ SANTOS")]


def test_malote_para_cumprimento_sem_tarefa_aparece_e_com_tarefa_nao(con):
    mario = _uid(con, "mario")
    parado = _expediente(con, "mandado de averbação", dono=mario)
    com_tarefa = _expediente(con, "pedido de certidão", dono=mario)
    _tarefa(con, "cumprir pedido", dono=mario, expediente=com_tarefa)
    _expediente(con, "convite para seminário", categoria="Circulares", dono=mario)
    m = OP.malote_sem_providencia(con, HOJE)
    assert [x["id"] for x in m] == [parado]
    assert m[0]["dias_parado"] == 19


def test_fraude_aparece_qualquer_que_seja_a_categoria(con):
    _expediente(con, " Suspeição de fraude.", categoria="Outros")
    _expediente(con, "DECISÃO COMUNICANDO FRAUDE DETECTADA EM ESCRITURA", categoria="Circulares")
    _expediente(con, "Convite para o congresso", categoria="Circulares")
    assert len(OP.suspeitas_de_fraude(con)) == 2


def test_certificado_vencendo_e_o_cpf_nao_aparece():
    certs = [{"nome": "FULANO:***", "vence": "2026-11-01"},
             {"nome": "CICLANO:***", "vence": "2027-09-01"},
             {"nome": "VELHO:***", "vence": "2026-10-01"}]
    fora = OP.certificados_a_vencer(certs, HOJE)
    assert [(c["nome"], c["faltam_dias"]) for c in fora] == [("VELHO:***", -8),
                                                              ("FULANO:***", 23)]
    assert OP.certificados_a_vencer(None, HOJE) is None
    assert OP._CPF_NO_NOME.sub(":***", "MARIO EXEMPLO:01234567890") == "MARIO EXEMPLO:***"


# --------------------------------------------------------------- rodada

def test_a_rodada_bate_o_ponto_e_escreve_a_mesa(con, tmp_path):
    _responsavel(con, "GESTAO", "mario")
    r = ROT.rodar(con, HOJE, agora=AGORA, pasta_relatorio=tmp_path,
                  ler_agendador=lambda: [], ler_certificados=lambda: [])
    assert r["nao_mediu"] == {}
    html = Path(r["relatorio"]).read_text(encoding="utf-8")
    assert "Mesa do oficial — 09/10/2026" in html and "MARIO EXEMPLO" in html
    assert OR.ultima_batida(con, "OFICIAL")["situacao"] == "OK"
    assert [d["chave"] for d in OD.abertas(con)] == [OO.PERGUNTA_DAS_OBRIGACOES]


def test_so_ler_nao_grava_nada(cg_casa, tmp_path):
    """Num banco aberto só para leitura, qualquer gravação estouraria — e viraria
    «não mediu». Ela sai limpa, com o relatório, e o banco fica como estava."""
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    banco = Path(cg_casa["banco"])

    def contagem():
        c = sqlite3.connect(banco)
        try:
            return [c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    for t in ("tasks", "task_history")]
        finally:
            c.close()

    antes = contagem()
    ro = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        r = ROT.rodar(ro, HOJE, agora=AGORA, pasta_relatorio=tmp_path, so_ler=True,
                      ler_agendador=lambda: [], ler_certificados=lambda: [])
    finally:
        ro.close()
    assert r["nao_mediu"] == {} and Path(r["relatorio"]).exists()
    assert "tarefas_dos_robos" not in r
    assert contagem() == antes


def test_parte_que_quebra_vira_nao_mediu_e_o_resto_sai(con, tmp_path):
    def quebra():
        raise RuntimeError("certificados indisponíveis")
    _responsavel(con, "GESTAO", "mario")
    r = ROT.rodar(con, HOJE, agora=AGORA, pasta_relatorio=tmp_path,
                  ler_agendador=lambda: [], ler_certificados=quebra)
    assert "mesa" in r["nao_mediu"]
    assert Path(r["relatorio"]).exists()
    assert OR.ultima_batida(con, "OFICIAL")["situacao"] == "ERRO"


def test_o_que_a_rodada_grava_fica_confirmado_para_quem_abre_depois(con, cg_casa, tmp_path):
    """L065R (18/10/2026): o esquema do robô oficial deixou de confirmar sozinho.
    O `executescript` confirmava o que estivesse aberto, e era o `perguntar`, no
    meio da rodada, que confirmava as tarefas dos robôs. Agora quem confirma é a
    rodada, no fim. O Agendador fecha a conexão logo depois: o que ficasse
    aberto voltaria atrás calado, e a outra conexão não veria nada."""
    _responsavel(con, "GESTAO", "mario")
    _responsavel(con, "TI", "alberto", subst="mario")
    for i, h in enumerate(("2026-10-08T08:28:54", "2026-10-09T07:30:00",
                           "2026-10-09T14:00:00")):
        _leitura(con, h, erro=ERRO_MODELO, ato=10 + i)
    r = ROT.rodar(con, HOJE, agora=AGORA, pasta_relatorio=tmp_path,
                  ler_agendador=lambda: [], ler_certificados=lambda: [])
    assert r["tarefas_dos_robos"]["criadas"] == 1
    assert not con.in_transaction
    outra = sqlite3.connect(cg_casa["banco"])
    try:
        assert outra.execute("SELECT count(*) FROM tasks WHERE source_type='OFICIAL'"
                             ).fetchone()[0] == 1
        assert OR.ultima_batida(outra, "OFICIAL")["situacao"] == "AVISO"
        assert OO.PERGUNTA_DAS_OBRIGACOES in [d["chave"] for d in OD.abertas(outra)]
    finally:
        outra.close()


def test_o_robo_oficial_nao_lavra_nao_sela_nao_cobra_nao_envia():
    import ast
    proibidos = ("lavr", "selar", "cobrar", "enviar", "cancelar", "apagar")
    for mod in (OR, OD, OO, OP, ROT):
        arvore = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        for no in arvore.body:
            if isinstance(no, ast.FunctionDef):
                assert not any(p in no.name for p in proibidos), (mod.__name__, no.name)


def test_o_robo_oficial_compila_no_python_3_11():
    """O README pede «Python 3.11 ou superior». A f-string que repete as próprias
    aspas dentro das chaves (`f"{linha["x"]}"`) só o 3.12 lê: no 3.11 o módulo
    nem importa, e a saúde dos robôs some inteira."""
    import tokenize
    if not hasattr(tokenize, "FSTRING_START"):       # antes do 3.12, o import já acusou
        return
    for mod in (OR, OD, OO, OP, ROT):
        aspas: list[str] = []                        # as das f-strings abertas
        with open(mod.__file__, "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type == tokenize.FSTRING_END:
                    aspas.pop()
                    continue
                if tok.type not in (tokenize.FSTRING_START, tokenize.STRING):
                    continue
                abre = tok.string.lstrip("rRbBuUfF")[:3]
                abre = abre if abre in ('"""', "'''") else abre[0]
                assert not aspas or not abre.startswith(aspas[-1]), (
                    mod.__name__, tok.start[0], tok.line.strip())
                if tok.type == tokenize.FSTRING_START:
                    aspas.append(abre)

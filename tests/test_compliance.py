"""O agente de compliance: quem fiscaliza os outros agentes e o que a casa informa.

O QUE ESTES TESTES GUARDAM
    **Que a falha calada aparece.** Em 09/10/2026 a leitura da IA rodava havia
    três dias sem ler nada, com «código de saída 0» no log, por um nome de
    modelo de vitrine na configuração. Os dois achados que pegam isso estão aqui.

    **Que o fiscal não comete o defeito que acusa.** A regra que quebra vira
    NAO_MEDIU e não resolve os achados dela — o gestor fechou a tarefa do backup
    assim, e o compliance existe para ver isso.

    **Que ele é independente e não conserta.** Não importa quem fiscaliza, e só
    escreve nas próprias tabelas, nas tarefas e no histórico delas.
"""
from __future__ import annotations

import ast
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import compliance as CP                                          # noqa: E402

AGORA = datetime(2026, 10, 9, 15, 0, 0)
SENHA = "Senha#12345"


@pytest.fixture()
def con(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = sqlite3.connect(cg_casa["banco"])
    import gestor_schema
    import gestor_leitura
    import gestor_expedientes
    gestor_schema.init_gestor_schema(c)
    gestor_leitura.init_leitura_schema(c)
    gestor_expedientes.init_schema(c)
    CP.init_schema(c)
    c.commit()
    yield c
    c.close()


def _ctx(con, **kw):
    kw.setdefault("agendador", [])
    kw.setdefault("saude", lambda: {"ok": True, "version": "3.6.288"})
    kw.setdefault("versao_instalada", "3.6.288")
    return CP.Contexto(con=con, agora=kw.pop("agora", AGORA), **kw)


def _regra(achados, regra):
    return [a for a in achados if a["regra"] == regra]


# ------------------------------------------------------------- independência

def test_o_corte_e_o_mesmo_do_gestor():
    """Copiado, e não importado — então a igualdade se prova aqui."""
    import gestor_conferencia
    assert CP.CORTE == gestor_conferencia.IMPLANTACAO


def test_o_acervo_e_o_mesmo_do_gestor():
    import gestor_conferencia
    assert tuple(CP.ORIGENS_DO_ACERVO) == tuple(gestor_conferencia.ORIGENS_DO_ACERVO)


def test_copias_do_banco_na_pasta_de_dados(con, tmp_path):
    (tmp_path / "cartorio_gestao.sqlite3").write_bytes(b"x" * 1000)
    for dia in ("20261007-074502", "20261008-074502", "20261009-074502"):
        (tmp_path / f"cartorio_gestao.antes-minutas-cnib-{dia}.sqlite3").write_bytes(b"x" * 1000)
    achados = CP.regra_copias_do_banco(_ctx(con, pasta_dados=tmp_path))
    assert [a["chave"] for a in achados] == ["COPIAS_DO_BANCO"]
    assert "3 cópia(s)" in achados[0]["detalhe"] and "antes-minutas-cnib" in achados[0]["detalhe"]
    assert not CP.regra_copias_do_banco(_ctx(con, pasta_dados=tmp_path / "nao_existe"))


def test_o_compliance_nao_importa_quem_ele_fiscaliza():
    arvore = ast.parse((RAIZ / "compliance.py").read_text(encoding="utf-8"))
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
    proibidos = {m for m in importados if m.startswith(("gestor", "agente", "revisao",
                                                         "sirc", "crc", "onr", "ri_onr"))}
    assert not proibidos, f"o fiscal usa a régua do fiscalizado: {proibidos}"


def test_o_compliance_so_escreve_nas_proprias_tabelas_e_na_tarefa():
    texto = (RAIZ / "compliance.py").read_text(encoding="utf-8")
    alvos = set(re.findall(r"\b(?:INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM)\s+(\w+)", texto))
    alvos -= {"SET"}
    fora = {t for t in alvos if not t.startswith("cp_") and t not in ("tasks", "task_history")}
    assert not fora, f"o compliance escreve onde não devia: {fora}"


# -------------------------------------------------------------- os agentes

def test_modelo_com_nome_de_vitrine_e_critico(con):
    con.execute("CREATE TABLE IF NOT EXISTS ag_config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.execute("INSERT OR REPLACE INTO ag_config VALUES ('modelo_padrao', 'Opus 5.5')")
    achados = CP.regra_config_do_modelo(_ctx(con))
    assert [a["gravidade"] for a in achados] == ["CRITICO"]
    assert "Opus 5.5" in achados[0]["detalhe"]
    for bom in ("claude-opus-5-5", ""):
        con.execute("UPDATE ag_config SET valor=? WHERE chave='modelo_padrao'", (bom,))
        assert not _regra(CP.regra_config_do_modelo(_ctx(con)), "CONFIG_DO_MODELO")


def test_ia_que_so_erra_e_critica_e_a_que_le_nao(con):
    for i in range(3):
        con.execute("""INSERT INTO ge_leituras (tabela, ato_id, hash_dossie, lido_em, erro)
                       VALUES ('ri_atos', ?, 'h', '2026-10-09T14:00:00',
                               'AgenteError: O Claude não conhece o modelo pedido')""", (i,))
    achados = CP.regra_ia_sem_resultado(_ctx(con))
    assert [(a["chave"], a["gravidade"]) for a in achados] == [("IA:ge_leituras:parou", "CRITICO")]
    assert "não conhece o modelo" in achados[0]["detalhe"]
    for i in range(5):
        con.execute("""INSERT INTO ge_leituras (tabela, ato_id, hash_dossie, lido_em, achados_json)
                       VALUES ('nt_atos', ?, 'h', '2026-10-09T14:10:00', '[]')""", (i,))
    assert not CP.regra_ia_sem_resultado(_ctx(con))


def test_erro_antigo_da_ia_nao_conta(con):
    con.execute("""INSERT INTO ge_leituras (tabela, ato_id, hash_dossie, lido_em, erro)
                   VALUES ('ri_atos', 1, 'h', '2026-10-01T07:30:00', 'x')""")
    assert not CP.regra_ia_sem_resultado(_ctx(con))


def test_agendador(con):
    rotinas = [
        {"nome": "CartorioGestao-A", "estado": "Disabled", "resultado": 0,
         "ultima": "2026-10-09T07:30:00", "proxima": "2026-10-10T07:30:00", "diario": True},
        {"nome": "CartorioGestao-B", "estado": "Ready", "resultado": 1,
         "ultima": "2026-10-09T07:30:00", "proxima": "2026-10-10T07:30:00", "diario": True},
        {"nome": "CartorioGestao-C", "estado": "Running", "resultado": 0x41301,
         "ultima": "2026-10-09T12:00:00", "proxima": "2026-10-10T12:00:00", "diario": True},
        {"nome": "CartorioGestao-D", "estado": "Ready", "resultado": 0,
         "ultima": "2026-10-07T07:30:00", "proxima": "2026-10-10T07:30:00", "diario": True},
        {"nome": "CartorioGestao-Servidor", "estado": "Running", "resultado": 0x41301,
         "ultima": "2026-10-01T08:00:00", "proxima": None, "diario": False},
        {"nome": "CartorioGestao-Boa", "estado": "Ready", "resultado": 0,
         "ultima": "2026-10-09T14:30:00", "proxima": "2026-10-10T07:30:00", "diario": True},
    ]
    chaves = {a["chave"]: a["gravidade"] for a in CP.regra_agendador(_ctx(con, agendador=rotinas))}
    assert chaves == {
        "AGENDADOR:CartorioGestao-A:desligada": "CRITICO",
        "AGENDADOR:CartorioGestao-B:resultado": "CRITICO",
        "AGENDADOR:CartorioGestao-C:travada": "ATENCAO",
        "AGENDADOR:CartorioGestao-D:parada": "CRITICO",
    }


def test_agendador_vazio_e_nao_mediu_e_nao_zero(con):
    achados = CP.regra_agendador(_ctx(con, agendador=[]))
    assert [a["gravidade"] for a in achados] == ["NAO_MEDIU"]


def test_log_da_rotina_le_so_a_ultima_rodada(con, tmp_path):
    cmd = tmp_path / "ROTINA.cmd"
    cmd.write_text("@echo off\n")
    log = tmp_path / "ROTINA.log"
    sep = "=" * 64 + " \n"
    log.write_bytes((sep + "Conferência 08/10\nAVISO: velho\n codigo de saida: 0 \n" + sep +
                     "Conferência 09/10\n  achados: 3\n codigo de saida: 1 \n").encode("utf-8"))
    rotina = [{"nome": "CartorioGestao-X", "estado": "Ready", "resultado": 1,
               "executa": "cmd.exe", "argumentos": f'/c "{cmd}"'}]
    achados = CP.regra_log_das_rotinas(_ctx(con, agendador=rotina))
    assert [a["chave"] for a in achados] == ["LOG:CartorioGestao-X:saida"]
    log.write_bytes((sep + "Conferência 09/10\nAVISO: a leitura do texto pela IA não rodou\n"
                     " codigo de saida: 0 \n").encode("utf-8"))
    achados = CP.regra_log_das_rotinas(_ctx(con, agendador=rotina))
    assert [(a["chave"], a["gravidade"]) for a in achados] == [("LOG:CartorioGestao-X:aviso", "ATENCAO")]


def test_gestor_parado_e_rodada_quebrada(con):
    con.execute("INSERT INTO ge_execucoes (iniciada_em, terminada_em, hoje, erro) "
                "VALUES ('2026-10-08T07:30:00', '2026-10-08T07:30:05', '2026-10-08', 'KeyError: x')")
    chaves = {a["chave"] for a in CP.regra_execucoes_do_gestor(_ctx(con))}
    assert "GESTOR:parado" in chaves
    assert any(c.startswith("GESTOR:erro:") for c in chaves)


def test_fechou_sem_medir(con):
    t = "2026-10-08T14:00:17"
    con.execute("""INSERT INTO ge_achados (chave, regra, gravidade, setor, titulo,
                       primeiro_visto_em, ultimo_visto_em, resolvido_em)
                   VALUES ('BACKUP:x', 'BACKUP', 'CRITICO', 'TI', 'Backup atrasado',
                           '2026-10-07', '2026-10-07', ?)""", (t,))
    con.execute("""INSERT INTO ge_achados (chave, regra, gravidade, setor, titulo,
                       primeiro_visto_em, ultimo_visto_em)
                   VALUES ('NAO_MEDIU:BACKUP', 'BACKUP', 'NAO_MEDIU', 'TI', 'não mediu', ?, ?)""",
                (t, t))
    achados = CP.regra_fechou_sem_medir(_ctx(con))
    assert [a["gravidade"] for a in achados] == ["CRITICO"]


def test_fechou_e_reabriu(con):
    tid = con.execute("""INSERT INTO tasks (source_type, source_ref, title, status, created_at,
                             updated_at, priority) VALUES ('GESTOR', 'GESTOR:BACKUP:TI',
                             'Backup', 'ABERTA', ?, ?, 'ALTA')""", (AGORA.isoformat(), AGORA.isoformat())).lastrowid
    con.execute("INSERT INTO task_history (task_id, ts, action, note) VALUES (?, '2026-10-07T14:00:00', "
                "'ALTEROU_STATUS', 'Fechada pela conferência: não há mais pendência.')", (tid,))
    con.execute("INSERT INTO task_history (task_id, ts, action, note) VALUES (?, '2026-10-08T07:30:00', "
                "'REABERTA', 'A conferência ainda encontra 1 pendência(s).')", (tid,))
    achados = CP.regra_fechou_e_reabriu(_ctx(con))
    assert [a["chave"] for a in achados] == [f"FECHOU_E_REABRIU:{tid}"]


def test_copia_divergente(con, tmp_path):
    prod, orig = tmp_path / "GESTOR", tmp_path / "sistema"
    prod.mkdir()
    orig.mkdir()
    (prod / "a.py").write_text("x = 1\n")
    (orig / "a.py").write_text("x = 2\n")
    (prod / "b.py").write_text("y\n")
    (orig / "b.py").write_text("y\n")
    achados = CP.regra_copia_divergente(_ctx(con, copias=[(prod, orig)]))
    assert len(achados) == 1 and "a.py" in achados[0]["detalhe"] and "b.py" not in achados[0]["detalhe"]


def test_triagem_que_manda_prazo_para_ciencia(con):
    for i, r in enumerate((
            {"tipo": "CIENCIA", "resumo": "Ofício determina a averbação no prazo de 5 dias"},
            {"tipo": "CIENCIA", "resumo": "Portaria de dedetização da COGEX"},
            {"tipo": "CUMPRIMENTO", "resumo": "prazo de 10 dias", "prazo_dias": 10})):
        con.execute("""INSERT INTO ge_triagens (expediente_id, hash_dossie, lido_em, resultado_json)
                       VALUES (?, 'h', '2026-10-09T08:00:00', ?)""", (i + 1, json.dumps(r)))
    achados = CP.regra_triagem_duvidosa(_ctx(con))
    assert [a["chave"] for a in achados] == ["TRIAGEM:1"]


def test_servidor_com_versao_diferente(con):
    achados = CP.regra_servidor(_ctx(con, saude=lambda: {"ok": True, "version": "3.6.287"}))
    assert [a["chave"] for a in achados] == ["SERVIDOR:versao"]

    def fora():
        raise OSError("recusou a conexão")
    assert [a["chave"] for a in CP.regra_servidor(_ctx(con, saude=fora))] == ["SERVIDOR:fora"]


def test_configuracao_mudada_sem_rastro(con):
    con.execute("CREATE TABLE IF NOT EXISTS ag_config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.execute("INSERT OR REPLACE INTO ag_config VALUES ('modelo_padrao', 'claude-sonnet-5')")
    assert not CP.regra_config_sem_rastro(_ctx(con))           # a primeira só fotografa
    con.execute("UPDATE ag_config SET valor='Opus 5.5' WHERE chave='modelo_padrao'")
    achados = CP.regra_config_sem_rastro(_ctx(con, agora=datetime(2026, 10, 9, 16, 0)))
    assert len(achados) == 1 and "Opus 5.5" in achados[0]["detalhe"]
    # com rastro na auditoria, a mudança fica registrada e não vira achado
    con.execute("UPDATE ag_config SET valor='claude-opus-5-5' WHERE chave='modelo_padrao'")
    con.execute("INSERT INTO audit_logs (ts, action, details) VALUES ('2026-10-09T16:30:00', "
                "'AG_CONFIG_SALVA', '{}')")
    achados = CP.regra_config_sem_rastro(_ctx(con, agora=datetime(2026, 10, 9, 17, 0)))
    assert len(achados) == 1                     # só a de antes, que não tinha rastro


def test_a_senha_nao_entra_na_fotografia(con):
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('crc_senha', 'segredo123')")
    CP.regra_config_sem_rastro(_ctx(con))
    valores = " ".join(str(r[0]) for r in con.execute("SELECT valor FROM cp_fotografias"))
    assert "segredo123" not in valores


# ----------------------------------------------------------- as informações

def _envio(con, central, ref, prot, quantos, enviado, situacao="ENVIADO", msg="ok", recibo=None):
    con.execute("""INSERT INTO ge_envios (central, referencia, canal, situacao, protocolo, quantos,
                       mensagem, enviado_em, registrado_em, registrado_por, origem, recibo_caminho)
                   VALUES (?, ?, 'PORTAL', ?, ?, ?, ?, ?, ?, 'teste', 'AGENTE', ?)""",
                (central, ref, situacao, prot, quantos, msg, enviado, enviado, recibo))


def test_envio_sem_protocolo_e_sem_comprovante(con, tmp_path):
    _envio(con, "SIRC", "rc_assentos:1:2026-09-15", "", 1, "2026-09-16T10:00:00")
    _envio(con, "SIRC", "rc_assentos:2:2026-09-15", "ARQ1", 1, "2026-09-16T10:00:00")
    _envio(con, "SIRC", "rc_assentos:3:2026-09-15", "ARQ2", 1, "2026-09-16T10:00:00",
           recibo=str(tmp_path / "nao_existe.pdf"))
    _envio(con, "SIRC_CANCELAMENTO", "rc_assentos:4", "X", 1, "2026-09-16T10:00:00",
           situacao="DISPENSADO", msg="")
    chaves = {a["chave"]: a["gravidade"] for a in CP.regra_envio_sem_prova(_ctx(con))}
    assert chaves[next(c for c in chaves if c.endswith(":protocolo"))] == "CRITICO"
    assert chaves[next(c for c in chaves if c.endswith(":recibo"))] == "CRITICO"
    assert chaves["ENVIO:ge:SIRC:sem_recibo"] == "ATENCAO"
    assert any(c.endswith(":dispensa") for c in chaves)


def test_quantidade_do_envio_que_nao_fecha(con):
    _envio(con, "SIRC", "rc_assentos:1:2026-09-15", "ARQ", 3, "2026-09-16T10:00:00")
    _envio(con, "SIRC", "rc_assentos:2:2026-09-15", "ARQ", 3, "2026-09-16T10:00:00")
    assert [a["regra"] for a in CP.regra_quantos_nao_fecha(_ctx(con))] == ["QUANTOS_NAO_FECHA"]
    _envio(con, "SIRC", "rc_assentos:3:2026-09-15", "ARQ", 3, "2026-09-16T10:00:00")
    assert not CP.regra_quantos_nao_fecha(_ctx(con))


def test_envio_ao_sirc_fora_do_prazo_e_o_anterior_ao_corte_nao(con):
    _envio(con, "SIRC", "rc_assentos:1:2026-09-15", "A", 1, "2026-09-22T16:00:00")   # 5 dias úteis
    _envio(con, "SIRC", "rc_assentos:2:2026-09-15", "B", 1, "2026-09-16T10:00:00")   # 1 dia útil
    _envio(con, "SIRC", "rc_assentos:3:2026-09-09", "C", 1, "2026-09-30T10:00:00")   # antes do corte
    achados = CP.regra_envio_fora_do_prazo(_ctx(con))
    assert len(achados) == 1
    assert "rc_assentos:1" in achados[0]["detalhe"] and "rc_assentos:3" not in achados[0]["detalhe"]


# ---------------------------------------------------------------- os atos

def _matricula(con, numero="4100"):
    return con.execute("INSERT INTO ri_matriculas (numero, criado_em) VALUES (?, ?)",
                       (numero, AGORA.isoformat())).lastrowid


def _ato(con, mat, tipo, numero, *, hash_ato=None, anterior=None, lavrado="2026-09-20T10:00:00"):
    hash_ato = hash_ato or f"h-{mat}-{tipo}-{numero}"
    return con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, hash_ato, hash_anterior,
                              lavrado_em) VALUES (?,?,?,?,?,?)""",
                       (mat, tipo, numero, hash_ato, anterior, lavrado)).lastrowid


def test_dupla_medicao_da_numeracao(con):
    mat = _matricula(con)
    _ato(con, mat, "R", 1)
    _ato(con, mat, "AV", 1)
    achados = CP.regra_numeracao(_ctx(con))
    assert [a["gravidade"] for a in achados] == ["CRITICO"]
    assert "o gestor NÃO acusa" in achados[0]["detalhe"]
    con.execute("""INSERT INTO ge_achados (chave, regra, gravidade, setor, titulo,
                       primeiro_visto_em, ultimo_visto_em)
                   VALUES ('NUMERACAO:x', 'NUMERACAO', 'CRITICO', 'RI', 't', 'a', 'a')""")
    assert not CP.regra_numeracao(_ctx(con))      # os dois veem: a tarefa é do gestor


def test_o_gestor_acusa_e_a_segunda_medicao_nao_confirma(con):
    con.execute("""INSERT INTO ge_achados (chave, regra, gravidade, setor, titulo,
                       primeiro_visto_em, ultimo_visto_em)
                   VALUES ('CORRENTE_RI:x', 'CORRENTE_RI', 'CRITICO', 'RI', 't', 'a', 'a')""")
    achados = CP.regra_corrente_ri(_ctx(con))
    assert [a["regra"] for a in achados] == ["DUPLA_MEDICAO"]


def test_corrente_quebrada(con):
    mat = _matricula(con)
    _ato(con, mat, "R", 1, hash_ato="h1")
    _ato(con, mat, "AV", 2, hash_ato="h2", anterior="h1")
    assert not CP.regra_corrente_ri(_ctx(con))
    _ato(con, mat, "AV", 3, hash_ato="h3", anterior="OUTRO")
    achados = CP.regra_corrente_ri(_ctx(con))
    assert [a["gravidade"] for a in achados] == ["CRITICO"]


SELO = "MATRIC000000FQ2IF3MJ7KUI7600"


def test_selo_escrito_em_dois_atos_da_mesma_tabela(con):
    mat = _matricula(con)
    for n in (1, 2):
        a = _ato(con, mat, "AV", n)
        con.execute("UPDATE ri_atos SET selo_texto=? WHERE id=?", (f"Selo: {SELO}", a))
    achados = CP.regra_selo_em_dois_atos(_ctx(con))
    assert [a["chave"] for a in achados] == [f"SELO_DOIS:ri_atos:{SELO}"]
    # o mesmo par vindo do acervo do E-Ofício, de antes do corte, não é achado
    con.execute("UPDATE ri_atos SET origem='EOFICIO', lavrado_em='2025-08-11T10:00:00'")
    assert not CP.regra_selo_em_dois_atos(_ctx(con))


def test_selo_escrito_num_ato_e_do_outro_no_razao(con):
    mat = _matricula(con)
    a1, a2 = _ato(con, mat, "R", 1), _ato(con, mat, "AV", 2)
    con.execute("UPDATE ri_atos SET selo_texto=? WHERE id=?", (SELO, a2))
    con.execute("""INSERT INTO sd_selos (numero, tabela, ato_id, atribuicao, obtido_em)
                   VALUES (?, 'ri_atos', ?, 'IMOVEL', '2026-10-01')""", (SELO, a1))
    achados = CP.regra_selo_em_dois_atos(_ctx(con))
    assert [a["chave"] for a in achados] == [f"SELO_OUTRO:ri_atos:{SELO}"]
    # o mesmo selo espelhado noutra tabela (habilitação → assento) não é achado
    con.execute("UPDATE sd_selos SET tabela='hc_habilitacoes', ato_id=1 WHERE numero=?", (SELO,))
    assert not CP.regra_selo_em_dois_atos(_ctx(con))


# ---------------------------------------------------------------- a rodada

def test_regra_que_quebra_vira_nao_mediu_e_nao_resolve_o_que_ela_achou(con, monkeypatch):
    agora = AGORA.isoformat()
    con.execute("""INSERT INTO cp_achados (chave, area, regra, gravidade, titulo,
                       primeiro_visto_em, ultimo_visto_em)
                   VALUES ('SERVIDOR:versao', 'AGENTES', 'SERVIDOR', 'CRITICO', 't', ?, ?)""",
                (agora, agora))

    def quebra(ctx):
        raise RuntimeError("sem rede")
    monkeypatch.setattr(CP, "REGRAS", (("SERVIDOR", quebra),))
    resumo = CP.rodar(con, _ctx(con))
    abertos = {r[0]: r[1] for r in con.execute(
        "SELECT chave, gravidade FROM cp_achados WHERE resolvido_em IS NULL")}
    assert abertos["SERVIDOR:versao"] == "CRITICO"
    assert abertos["NAO_MEDIU:SERVIDOR"] == "NAO_MEDIU"
    assert resumo["resolvidos"] == 0


def test_a_rodada_grava_relata_e_abre_uma_tarefa_so_com_critico(con, tmp_path, monkeypatch):
    critico = [CP._achado("X:1", "AGENTES", "X", "CRITICO", "Algo crítico", "detalhe",
                          o_que_fazer="fazer isto")]
    monkeypatch.setattr(CP, "REGRAS", (("X", lambda ctx: list(critico)),))
    resumo = CP.rodar(con, _ctx(con), tmp_path)
    assert resumo["tarefa"]
    html = Path(resumo["relatorio"]).read_text(encoding="utf-8")
    assert "Algo crítico" in html and "O que o compliance ainda não mede" in html
    tarefa = con.execute("SELECT title, status, assigned_user_id FROM tasks WHERE id=?",
                         (resumo["tarefa"],)).fetchone()
    assert tarefa[1] == "ABERTA" and "[Compliance]" in tarefa[0] and tarefa[2]
    # sem crítico: a tarefa fecha, e nenhuma nova se abre
    monkeypatch.setattr(CP, "REGRAS", (("X", lambda ctx: []),))
    resumo2 = CP.rodar(con, _ctx(con), tmp_path)
    assert resumo2["tarefa"] is None
    assert con.execute("SELECT status FROM tasks WHERE id=?", (resumo["tarefa"],)).fetchone()[0] \
        == "CONCLUIDA"
    assert con.execute("SELECT count(*) FROM cp_execucoes WHERE terminada_em IS NOT NULL"
                       ).fetchone()[0] == 2


def test_a_rodada_inteira_roda_numa_casa_vazia(con, tmp_path):
    """Instalação nova nasce funcionando: nenhuma regra estoura sem dado."""
    resumo = CP.rodar(con, _ctx(con), tmp_path)
    nao_mediu = [r[0] for r in con.execute(
        "SELECT titulo || ' — ' || detalhe FROM cp_achados WHERE gravidade='NAO_MEDIU'")]
    # o agendador vazio é o único NAO_MEDIU esperado (o teste não lê o Windows)
    assert all("Nenhuma rotina" in t for t in nao_mediu), nao_mediu
    assert resumo["relatorio"]

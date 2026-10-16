"""Filtrar e ordenar tarefas, processos e a produtividade — 13/10/2026.

Pedido do oficial: «preciso ter como ordenar as tarefas, tem poucas opções de
filtros (não tem por prioridade, etc) e não tem nenhuma opção de ordenar por
prioridade, por data, por setor... quero todas opções», e depois «também quero
esses filtros e ordenar na produtividade».
"""
from __future__ import annotations

import sqlite3
from datetime import date

import produtividade as PRD
import tarefa_ordem as TO


def _tarefa(db, titulo, **campos):
    return db.create_task({"title": titulo, **campos}, None)


def _titulos(html: str, *nomes: str) -> list[str]:
    """Os títulos na ordem em que aparecem na página."""
    return sorted((n for n in nomes if n in html), key=html.index)


# ----------------------------------------------------------------- a régua
def test_toda_ordem_vira_sql_valido_nos_dois_sentidos():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT, priority TEXT,
            due_date TEXT, created_at TEXT, sector TEXT, source_type TEXT, assigned_user_id INT);
        CREATE TABLE users (id INTEGER PRIMARY KEY, full_name TEXT);
        CREATE TABLE pe (task_id INT, especie TEXT);
    """)
    for chave in [*TO.ORDENS, *TO.APELIDOS, "", "QUALQUER"]:
        for inverter in ("", "1"):
            ordem = TO.ordem_sql(chave, inverter, tipo="pe.especie")
            con.execute(f"""SELECT t.id, t.created_at AS ultimo_andamento FROM tasks t
                            LEFT JOIN users ua ON ua.id = t.assigned_user_id
                            LEFT JOIN pe ON pe.task_id = t.id ORDER BY {ordem}""").fetchall()


def test_inverter_vira_so_a_chave_principal_e_o_vazio_fica_no_fim():
    normal = TO.ordem_sql("SETOR", "")
    invertida = TO.ordem_sql("SETOR", "1")
    assert "t.sector ASC" in normal and "t.sector DESC" in invertida
    assert invertida.startswith("CASE WHEN t.sector IS NULL")   # vazio por último sempre


def test_ordem_desconhecida_cai_no_prazo_e_a_antiga_continua_valendo():
    assert TO.ordem_sql("NADA", "") == TO.ordem_sql("PRAZO", "")
    assert TO.ordem_sql("RECENTE", "") == TO.ordem_sql("ABERTURA", "")
    assert TO.ordem_sql("PARADO", "") == TO.ordem_sql("ANDAMENTO", "")
    assert "TIPO" not in TO.ordens_da_tela(tem_tipo=False)


def test_filtro_de_abertura_inclui_o_dia_inteiro():
    where, args = TO.filtros_sql({"abertura_ate": "2026-10-13"}, hoje=date(2026, 10, 13),
                                 cond_aberta="1=1", args_aberta=[], andamento="t.created_at")
    assert args == ["2026-10-13z"] and "2026-10-13T18:00:00" <= args[0]


# ----------------------------------------------------------- a tela Tarefas
def test_tarefas_filtra_por_prioridade_e_responsavel_e_ordena(cg_casa_logada):
    casa = cg_casa_logada
    db, c = casa["db"], casa["c"]
    with db.connect() as con_:
        mario = con_.execute("SELECT id FROM users WHERE username='mario'").fetchone()[0]
    _tarefa(db, "Tarefa Zeta baixa", priority="BAIXA", sector="RCPN", due_date="2026-12-01")
    _tarefa(db, "Tarefa Alfa critica", priority="CRITICA", sector="Notas", due_date="2026-11-01",
            assigned_user_id=mario)
    _tarefa(db, "Tarefa Meio media", priority="MEDIA", sector="Atendimento")

    html = c.get("/tarefas?status=&prioridade=CRITICA").get_data(as_text=True)
    assert "Tarefa Alfa critica" in html and "Tarefa Zeta baixa" not in html
    html = c.get(f"/tarefas?status=&responsavel={mario}").get_data(as_text=True)
    assert "Tarefa Alfa critica" in html and "Tarefa Meio media" not in html

    nomes = ("Tarefa Zeta baixa", "Tarefa Alfa critica", "Tarefa Meio media")
    r = c.get("/tarefas?status=&ordem=ASSUNTO")
    assert r.status_code == 200
    assert _titulos(r.get_data(as_text=True), *nomes) == [
        "Tarefa Alfa critica", "Tarefa Meio media", "Tarefa Zeta baixa"]
    html = c.get("/tarefas?status=&ordem=ASSUNTO&inverter=1").get_data(as_text=True)
    assert _titulos(html, *nomes) == ["Tarefa Zeta baixa", "Tarefa Meio media", "Tarefa Alfa critica"]
    html = c.get("/tarefas?status=&ordem=SETOR").get_data(as_text=True)
    assert _titulos(html, *nomes) == ["Tarefa Meio media", "Tarefa Alfa critica", "Tarefa Zeta baixa"]
    # o cabeçalho clicável e o seletor estão na tela
    assert "Inverter a ordem" in html and "ordem=PRIORIDADE" in html
    for chave in TO.ordens_da_tela(tem_tipo=False):
        assert c.get(f"/tarefas?status=&ordem={chave}&inverter=1").status_code == 200


def test_processos_ordena_por_todas_as_colunas(cg_casa_logada):
    casa = cg_casa_logada
    db, c = casa["db"], casa["c"]
    _tarefa(db, "Processo Bravo", priority="ALTA", sector="RCPN")
    _tarefa(db, "Processo Alfa", priority="BAIXA", sector="Notas")
    for chave in TO.ORDENS:
        for inv in ("", "1"):
            r = c.get(f"/processos?vista=TODOS&ordem={chave}&inverter={inv}")
            assert r.status_code == 200, chave
    html = c.get("/processos?vista=TODOS&ordem=PRIORIDADE").get_data(as_text=True)
    assert _titulos(html, "Processo Bravo", "Processo Alfa") == ["Processo Bravo", "Processo Alfa"]
    html = c.get("/processos?vista=TODOS&ordem=PRIORIDADE&inverter=1").get_data(as_text=True)
    assert _titulos(html, "Processo Bravo", "Processo Alfa") == ["Processo Alfa", "Processo Bravo"]
    # a prioridade e a situação saíram do «Mais filtros» — estão à vista
    assert 'name="prioridade"' in html and "Inverter a ordem" in html


# --------------------------------------------- a busca (relato #122)
def test_busca_por_numero_titulo_descricao_e_responsavel():
    """«precisa ser possível ordenar e pesquisar melhor entre as tarefas» —
    relato #122, 07/10/2026. A régua é uma só para Tarefas e Processos."""
    assert TO.busca_sql("", responsavel="u.full_name") == ([], [])
    where, args = TO.busca_sql("PROC-2026-000318", responsavel="u.full_name")
    assert where[0].startswith("(t.id = ?") and args[0] == 318
    assert TO.busca_sql("#318", responsavel="x")[1][0] == 318
    where, args = TO.busca_sql("certidão", responsavel="u.full_name", extras=("e.sender",))
    assert "t.id" not in where[0] and len(args) == 4 and "e.sender LIKE ?" in where[0]


def test_tarefas_procura_e_convive_com_filtros_ordem_e_suspensas(cg_casa_logada):
    import tarefa_suspensao as TS
    casa = cg_casa_logada
    db, c = casa["db"], casa["c"]
    with db.connect() as con_:
        mario = con_.execute("SELECT id FROM users WHERE username='mario'").fetchone()[0]
    db.create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", "Senha#12345", "USER")
    with db.connect() as con_:
        beatriz = con_.execute("SELECT id FROM users WHERE username='beatriz'").fetchone()[0]
    um = _tarefa(db, "Certidão Bravo", priority="ALTA", description="pedido do juízo",
                 assigned_user_id=mario)
    dois = _tarefa(db, "Escritura Alfa", priority="BAIXA", description="certidão de ônus anexa",
                   assigned_user_id=beatriz)
    _tarefa(db, "Averbação Gama", priority="MEDIA", assigned_user_id=beatriz)
    nomes = ("Certidão Bravo", "Escritura Alfa", "Averbação Gama")

    # título e descrição, com a ordem escolhida
    html = c.get("/tarefas?status=&q=certid&ordem=ASSUNTO").get_data(as_text=True)
    assert _titulos(html, *nomes) == ["Certidão Bravo", "Escritura Alfa"]
    # o número, nas três formas
    for q in (str(dois), f"%23{dois}", f"PROC-2026-{dois:06d}"):
        html = c.get(f"/tarefas?status=&q={q}").get_data(as_text=True)
        assert "Escritura Alfa" in html and "Averbação Gama" not in html, q
    # o responsável, junto com o filtro de prioridade
    html = c.get("/tarefas?status=&q=BEATRIZ&prioridade=BAIXA").get_data(as_text=True)
    assert _titulos(html, *nomes) == ["Escritura Alfa"]
    assert 'name="q"' in html and 'value="BEATRIZ"' in html
    # e o filtro das suspensas (relato #132)
    with db.transaction() as con_:
        TS.suspender(con_, um, modo="CONDICAO", motivo="Nota devolutiva emitida ao cliente",
                     condicao="Retorno do cliente com o documento", usuario_id=mario,
                     agora="2026-10-15T09:00:00")
    html = c.get("/tarefas?status=&q=certid&suspensas=OCULTAR").get_data(as_text=True)
    assert _titulos(html, *nomes) == ["Escritura Alfa"]
    html = c.get("/tarefas?status=&q=certid&suspensas=SO").get_data(as_text=True)
    assert _titulos(html, *nomes) == ["Certidão Bravo"] and "SUSPENSA até:" in html
    # Processos procura com a mesma régua: o número e o responsável também
    html = c.get(f"/processos?vista=TODOS&q={dois}").get_data(as_text=True)
    assert "Escritura Alfa" in html and "Averbação Gama" not in html


# ------------------------------------------------------- a produtividade
def _registro(**kw):
    base = {"id": 1, "data_registro": "2026-10-13", "responsavel_nome": "Ana",
            "categoria": "Balcão", "tarefa": "x", "prioridade": "Média", "status": "Concluída",
            "hora_inicio": "08:00", "tempo_liquido_min": 30, "tempo_planejado_min": None,
            "desvio_min": None, "eficiencia_pct": None}
    base.update(kw)
    return base


def test_produtividade_ordena_por_toda_coluna_com_vazio_no_fim():
    regs = [_registro(id=1, tarefa="b", prioridade="Baixa", tempo_liquido_min=10),
            _registro(id=2, tarefa="a", prioridade="Alta", tempo_liquido_min=None),
            _registro(id=3, tarefa="c", prioridade="Média", tempo_liquido_min=50)]
    assert [r["id"] for r in PRD.ordenar_registros(regs, "TAREFA")] == [2, 1, 3]
    assert [r["id"] for r in PRD.ordenar_registros(regs, "TAREFA", "1")] == [3, 1, 2]
    assert [r["id"] for r in PRD.ordenar_registros(regs, "PRIORIDADE")] == [2, 3, 1]
    # maior tempo primeiro; o que não tem tempo fica no fim nos dois sentidos
    assert [r["id"] for r in PRD.ordenar_registros(regs, "LIQUIDO")] == [3, 1, 2]
    assert [r["id"] for r in PRD.ordenar_registros(regs, "LIQUIDO", "1")] == [1, 3, 2]
    for chave in PRD.ORDENS_DO_REGISTRO:
        PRD.ordenar_registros(regs, chave, "1")


def test_tela_da_produtividade_filtra_o_periodo_e_ordena(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    con = sqlite3.connect(casa["banco"])
    PRD.init_produtividade_schema(con)
    for dia, tarefa, prior in (("2026-10-01", "Certidão Gama", "Baixa"),
                               ("2026-10-05", "Escritura Alfa", "Alta"),
                               ("2026-09-01", "Fora do período", "Alta")):
        PRD.registrar_registro(con, responsavel_user_id=1, responsavel_nome="Mario",
                               categoria=PRD.CATEGORIA_PADRAO, tarefa=tarefa,
                               prioridade=prior, status=PRD.STATUS_CONCLUIDA,
                               data_registro=dia, hora_inicio="08:00", hora_fim="09:00",
                               pausas_min=0, tempo_planejado_min=None, observacoes=None,
                               criado_por="mario")
    con.commit()
    con.close()
    url = "/administrativo/produtividade?data_de=2026-10-01&data_ate=2026-10-31&responsavel=Todos"

    def tabela(endereco):   # só a lista — o formulário sugere as tarefas recentes
        h = c.get(endereco).get_data(as_text=True)
        return h[h.index("Registros de"):]
    html = tabela(url + "&ordem=TAREFA")
    assert "Fora do período" not in html
    assert _titulos(html, "Certidão Gama", "Escritura Alfa") == ["Certidão Gama", "Escritura Alfa"]
    html = tabela(url + "&ordem=TAREFA&inverter=1")
    assert _titulos(html, "Certidão Gama", "Escritura Alfa") == ["Escritura Alfa", "Certidão Gama"]
    html = tabela(url + "&prioridade=Alta")
    assert "Escritura Alfa" in html and "Certidão Gama" not in html
    for chave in PRD.ORDENS_DO_REGISTRO:
        assert c.get(url + f"&ordem={chave}").status_code == 200

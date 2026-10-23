# -*- coding: utf-8 -*-
"""Controle de produtividade — domínio, API rápida e cronômetro."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import produtividade as PR
import pytest
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402


def _mem() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    return con


def _token(html: str) -> str:
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m, "csrf_token ausente"
    return m.group(1)


def test_init_schema_e_listas_padrao():
    con = _mem()
    PR.init_produtividade_schema(con)
    cats = PR.listar_categorias(con)
    assert cats == list(PR.CATEGORIAS_ATIVAS)
    assert len(cats) == 3
    assert cats[0] == PR.CATEGORIA_PADRAO
    assert PR.STATUS_CONCLUIDA in PR.listar_status(con)
    assert "Média" in PR.listar_prioridades(con)
    # coluna aditiva do cronômetro
    cols = {r[1] for r in con.execute("PRAGMA table_info(prod_registros)")}
    assert "pausado_em" in cols


def test_calcular_metricas_tempo():
    m = PR.calcular_metricas_tempo(
        hora_inicio="09:00",
        hora_fim="10:30",
        pausas_min=15,
        tempo_planejado_min=60,
    )
    assert m["tempo_liquido_min"] == 75
    assert m["desvio_min"] == 15.0
    assert m["eficiencia_pct"] == round(60 / 75 * 100, 1)
    assert m["tempo_liquido_hhmm"] == "1:15"


def test_semana_iso():
    assert PR.semana_iso("2026-10-05") == date(2026, 10, 5).isocalendar()[1]


def test_registrar_e_listar_registros():
    con = _mem()
    PR.init_produtividade_schema(con)
    rid = PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="Escrevente Teste",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="Conferir protocolo",
        prioridade="Alta",
        status="Concluída",
        hora_inicio="08:00",
        hora_fim="09:00",
        pausas_min=0,
        tempo_planejado_min=45,
        data_registro="2026-10-05",
        agora="2026-10-05T10:00:00",
    )
    assert rid > 0
    rows = PR.listar_registros(con, data_exata="2026-10-05")
    assert len(rows) == 1
    assert rows[0]["tempo_liquido_min"] == 60
    assert rows[0]["eficiencia_pct"] == round(45 / 60 * 100, 1)
    assert rows[0]["semana"] == date(2026, 10, 5).isocalendar()[1]


def test_recusa_categoria_invalida():
    con = _mem()
    PR.init_produtividade_schema(con)
    with pytest.raises(ValueError, match="Categoria inválida"):
        PR.registrar_registro(
            con,
            responsavel_user_id=1,
            responsavel_nome="X",
            categoria="Inexistente",
            tarefa="T",
            prioridade="Alta",
            status="Em andamento",
        )


def test_painel_kpis():
    con = _mem()
    PR.init_produtividade_schema(con)
    ref = date(2026, 10, 5)
    PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="A",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="Balcão",
        prioridade="Média",
        status="Concluída",
        hora_inicio="09:00",
        hora_fim="10:00",
        data_registro="2026-10-05",
    )
    PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="A",
        categoria=PR.CATEGORIAS_ATIVAS[1],
        tarefa="E-mail",
        prioridade="Baixa",
        status="Em andamento",
        data_registro="2026-10-05",
    )
    k = PR.painel_kpis(con, data_filtro="2026-10-05", responsavel_user_id=1, referencia=ref)
    assert k["tarefas_registradas"] == 2
    assert k["tarefas_concluidas"] == 1
    assert k["taxa_conclusao_pct"] == 50.0
    assert k["tempo_produtivo_min"] == 60
    assert k["tempo_medio_min"] == 60.0
    assert PR.CATEGORIA_PADRAO in k["por_categoria"]
    assert k["por_categoria"][PR.CATEGORIA_PADRAO]["concluidas"] == 1
    assert k["por_status"]["Em andamento"] == 1


def test_excluir_registro():
    con = _mem()
    PR.init_produtividade_schema(con)
    rid = PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="A",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="X",
        prioridade="Baixa",
        status="Cancelada",
    )
    PR.excluir_registro(con, rid)
    assert PR.listar_registros(con) == []
    with pytest.raises(LookupError):
        PR.excluir_registro(con, rid)


def test_lancar_rapido_com_duracao():
    con = _mem()
    PR.init_produtividade_schema(con)
    agora = datetime(2026, 10, 5, 14, 30, 0)
    rid = PR.lancar_rapido(
        con,
        responsavel_user_id=7,
        responsavel_nome="Carla",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="CLIENTE RCPN",
        duracao_min=5,
        agora=agora,
    )
    rows = PR.listar_registros(con)
    assert len(rows) == 1
    assert rows[0]["id"] == rid
    assert rows[0]["status"] == "Concluída"
    assert rows[0]["prioridade"] == "Média"
    assert rows[0]["hora_fim"] == "14:30"
    assert rows[0]["hora_inicio"] == "14:25"
    assert rows[0]["tempo_liquido_min"] == 5


def test_cronometro_unico_e_parar():
    con = _mem()
    PR.init_produtividade_schema(con)
    agora = datetime(2026, 10, 5, 10, 0, 0)
    rid = PR.iniciar_cronometro(
        con,
        responsavel_user_id=3,
        responsavel_nome="Teste",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="DIGITALIZAÇÃO",
        agora=agora,
    )
    assert rid > 0
    ativo = PR.cronometro_em_andamento(con, responsavel_user_id=3)
    assert ativo is not None
    assert ativo["status"] == "Em andamento"
    with pytest.raises(ValueError, match="Já existe"):
        PR.iniciar_cronometro(
            con,
            responsavel_user_id=3,
            responsavel_nome="Teste",
            categoria=PR.CATEGORIA_PADRAO,
            tarefa="outra",
            agora=agora,
        )
    PR.pausar_cronometro(
        con, responsavel_user_id=3, agora=datetime(2026, 10, 5, 10, 10, 0)
    )
    ativo2 = PR.cronometro_em_andamento(con, responsavel_user_id=3)
    assert ativo2["status"] == "Pausada"
    PR.retomar_cronometro(
        con, responsavel_user_id=3, agora=datetime(2026, 10, 5, 10, 15, 0)
    )
    ativo3 = PR.cronometro_em_andamento(con, responsavel_user_id=3)
    assert ativo3["status"] == "Em andamento"
    assert ativo3["pausas_min"] >= 5
    final = PR.parar_cronometro(
        con, responsavel_user_id=3, agora=datetime(2026, 10, 5, 10, 25, 0)
    )
    assert final["status"] == "Concluída"
    assert final["hora_fim"] == "10:25"
    assert PR.cronometro_em_andamento(con, responsavel_user_id=3) is None


def test_tarefas_recentes_autocomplete():
    con = _mem()
    PR.init_produtividade_schema(con)
    PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="A",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="MALOTE",
        prioridade="Média",
        status="Concluída",
    )
    PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="A",
        categoria=PR.CATEGORIAS_ATIVAS[1],
        tarefa="FECHAMENTO CAIXA",
        prioridade="Média",
        status="Concluída",
    )
    recentes = PR.tarefas_recentes(con, responsavel_user_id=1)
    textos = [r["tarefa"] for r in recentes]
    assert "MALOTE" in textos
    assert "FECHAMENTO CAIXA" in textos


def test_exportar_csv_colunas():
    con = _mem()
    PR.init_produtividade_schema(con)
    PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="A",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="CLIENTE",
        prioridade="Média",
        status="Concluída",
        hora_inicio="09:00",
        hora_fim="09:10",
        data_registro="2026-10-05",
    )
    csv_txt = PR.exportar_csv(con, data_filtro="2026-10-05")
    assert "Data;Responsável;Categoria;Tarefa" in csv_txt
    assert "CLIENTE" in csv_txt


@pytest.mark.usefixtures("cg_casa_logada")
def test_produtividade_tela_200(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.get("/administrativo/produtividade")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Controle diário de produtividade" in html
    assert "Novo registro diário" in html
    assert 'name="categoria"' in html
    assert "Painel" in html
    assert "Exportar CSV" in html
    assert "data-prod-rapida" in html
    assert "produtividade_rapida.js" in html or "data-prod-abrir" in html


@pytest.mark.usefixtures("cg_casa_logada")
def test_botao_produtividade_no_base(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "data-prod-rapida" in html
    assert 'name="csrf_token"' in html
    assert "Lançar atividade" in html
    assert "Cronômetro" in html


@pytest.mark.usefixtures("cg_casa_logada")
def test_produtividade_post_registra(cg_casa_logada):
    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/produtividade")
    token = _token(pagina.get_data(as_text=True))
    r = c.post(
        "/administrativo/produtividade",
        data={
            "csrf_token": token,
            "data_registro": "2026-10-05",
            "categoria": PR.CATEGORIA_PADRAO,
            "tarefa": "pytest produtividade",
            "prioridade": "Média",
            "status": "Concluída",
            "hora_inicio": "10:00",
            "hora_fim": "11:00",
            "pausas_min": "0",
            "tempo_planejado_min": "50",
            "observacoes": "nota pytest",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "pytest produtividade" in html or "Registro salvo" in html


@pytest.mark.usefixtures("cg_casa_logada")
def test_api_lancar_rapido_csrf(cg_casa_logada):
    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/produtividade")
    token = _token(pagina.get_data(as_text=True))
    # sem CSRF -> 400
    r_bad = c.post(
        "/administrativo/produtividade/api/lancar",
        data={
            "categoria": PR.CATEGORIA_PADRAO,
            "tarefa": "SEM CSRF",
            "duracao_min": "3",
        },
    )
    assert r_bad.status_code == 400
    r = c.post(
        "/administrativo/produtividade/api/lancar",
        data={
            "csrf_token": token,
            "categoria": PR.CATEGORIA_PADRAO,
            "tarefa": "CLIENTE RCPN pytest",
            "duracao_min": "3",
        },
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body and body.get("ok") is True
    assert body.get("id")


@pytest.mark.usefixtures("cg_casa_logada")
def test_api_cronometro_unico(cg_casa_logada):
    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/produtividade")
    token = _token(pagina.get_data(as_text=True))
    r1 = c.post(
        "/administrativo/produtividade/api/cronometro/iniciar",
        data={
            "csrf_token": token,
            "categoria": PR.CATEGORIA_PADRAO,
            "tarefa": "crono pytest 1",
        },
        headers={"X-CSRF-Token": token},
    )
    assert r1.status_code == 200
    assert r1.get_json().get("ok") is True
    r2 = c.post(
        "/administrativo/produtividade/api/cronometro/iniciar",
        data={
            "csrf_token": token,
            "categoria": PR.CATEGORIA_PADRAO,
            "tarefa": "crono pytest 2",
        },
        headers={"X-CSRF-Token": token},
    )
    assert r2.status_code == 400
    assert r2.get_json().get("ok") is False
    r3 = c.post(
        "/administrativo/produtividade/api/cronometro/parar",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": token},
    )
    assert r3.status_code == 200
    assert r3.get_json().get("ok") is True
    st = c.get("/administrativo/produtividade/api/cronometro/status")
    assert st.status_code == 200
    assert st.get_json().get("cronometro") is None



def test_exportar_xlsx_zip_headers_e_linhas():
    import zipfile
    from io import BytesIO

    con = _mem()
    PR.init_produtividade_schema(con)
    PR.registrar_registro(
        con,
        responsavel_user_id=1,
        responsavel_nome="A",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="CLIENTE",
        prioridade="Média",
        status=PR.STATUS_CONCLUIDA,
        hora_inicio="09:00",
        hora_fim="09:10",
        data_registro="2026-10-05",
    )
    PR.registrar_registro(
        con,
        responsavel_user_id=2,
        responsavel_nome="B",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="MALOTE",
        prioridade="Baixa",
        status=PR.STATUS_CONCLUIDA,
        hora_inicio="10:00",
        hora_fim="10:05",
        data_registro="2026-10-05",
    )
    blob = PR.exportar_xlsx(con, data_filtro="2026-10-05", responsavel_user_id=1)
    assert blob[:2] == b"PK"
    with zipfile.ZipFile(BytesIO(blob)) as zf:
        names = set(zf.namelist())
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        assert "xl/styles.xml" in names
        sheet1 = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        wb = zf.read("xl/workbook.xml").decode("utf-8")
    assert "Registro" in wb
    assert "Painel" in wb
    for col in PR.EXPORT_COLUNAS:
        assert col in sheet1
    assert sheet1.count("<row r=") == 2
    assert 's="2"' in sheet1
    assert 's="3"' in sheet1

    todos = PR.exportar_xlsx(con, data_filtro="2026-10-05", responsavel_user_id=None)
    with zipfile.ZipFile(BytesIO(todos)) as zf:
        s1 = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert s1.count("<row r=") == 3


@pytest.mark.usefixtures("cg_casa_logada")
def test_exportar_xlsx_http_e_filtro(cg_casa_logada):
    import zipfile
    from io import BytesIO

    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/produtividade")
    html = pagina.get_data(as_text=True)
    assert "Exportar Excel" in html
    assert "exportar.xlsx" in html
    css = c.get("/static/app.css").get_data(as_text=True)
    assert "bottom:72px" in css
    assert "z-index:910" in css

    token = _token(html)
    r_post = c.post(
        "/administrativo/produtividade",
        data={
            "csrf_token": token,
            "data_registro": "2026-10-05",
            "categoria": PR.CATEGORIA_PADRAO,
            "tarefa": "xlsx http pytest",
            "prioridade": "Média",
            "status": PR.STATUS_CONCLUIDA,
            "hora_inicio": "11:00",
            "hora_fim": "11:15",
            "pausas_min": "0",
        },
        follow_redirects=True,
    )
    assert r_post.status_code == 200
    body = r_post.get_data(as_text=True)
    assert ("xlsx http pytest" in body) or ("Registro salvo" in body)

    r = c.get("/administrativo/produtividade/exportar.xlsx?data=2026-10-05")
    assert r.status_code == 200
    assert "spreadsheetml" in (r.headers.get("Content-Type") or "")
    data = r.data
    assert data[:2] == b"PK"
    with zipfile.ZipFile(BytesIO(data)) as zf:
        s1 = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "xlsx http pytest" in s1
    for col in ("Data", "Categoria", "Tarefa", "Semana"):
        assert col in s1


def test_apenas_tres_categorias_ativas():
    con = _mem()
    PR.init_produtividade_schema(con)
    assert PR.listar_categorias(con) == list(PR.CATEGORIAS_ATIVAS)


def test_migrar_categorias_mapeia_antigas():
    con = _mem()
    PR.init_produtividade_schema(con)
    # Insere direto com rótulo antigo (bypass validação)
    con.execute(
        """INSERT INTO prod_registros (
            data_registro, responsavel_user_id, responsavel_nome,
            categoria, tarefa, prioridade, status,
            pausas_min, criado_em
        ) VALUES ('2026-10-05',1,'A','Atendimento','X','Média','Concluída',0,'2026-10-05T10:00:00')"""
    )
    con.execute(
        """INSERT INTO prod_registros (
            data_registro, responsavel_user_id, responsavel_nome,
            categoria, tarefa, prioridade, status,
            pausas_min, criado_em
        ) VALUES ('2026-10-05',1,'A','Financeiro','Y','Média','Concluída',0,'2026-10-05T10:00:00')"""
    )
    cont = PR.migrar_categorias_tres(con)
    assert cont.get("Atendimento → 1 - Operacional") == 1
    assert cont.get("Financeiro → 2 - Administrativo") == 1
    rows = con.execute("SELECT categoria FROM prod_registros ORDER BY tarefa").fetchall()
    assert rows[0][0] == "1 - Operacional"
    assert rows[1][0] == "2 - Administrativo"
    ativas = PR.listar_categorias(con)
    assert len(ativas) == 3


@pytest.mark.usefixtures("cg_casa_logada")
def test_cronometro_inicia_com_categoria(cg_casa_logada):
    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/produtividade")
    html = pagina.get_data(as_text=True)
    assert "data-prod-categorias-crono" in html
    assert "1 - Operacional" in html
    token = _token(html)
    r = c.post(
        "/administrativo/produtividade/api/cronometro/iniciar",
        data={
            "csrf_token": token,
            "categoria": PR.CATEGORIA_PADRAO,
            "tarefa": "crono com categoria",
        },
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["cronometro"]["categoria"] == PR.CATEGORIA_PADRAO
    assert body["cronometro"]["tarefa"] == "crono com categoria"
    # limpa
    c.post(
        "/administrativo/produtividade/api/cronometro/parar",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": token},
    )


@pytest.mark.usefixtures("cg_casa_logada")
def test_api_contexto_so_tres_categorias(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.get("/administrativo/produtividade/api/contexto")
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert j["categorias"] == list(PR.CATEGORIAS_ATIVAS)


@pytest.mark.usefixtures("cg_casa_logada")
def test_produtividade_title_sem_script(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.get("/administrativo/produtividade")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    assert m, "title ausente"
    titulo = m.group(1)
    assert "<script" not in titulo.lower()
    assert "function(" not in titulo
    assert "Produtividade" in titulo


def test_js_reabre_cronometro_e_clique_fora():
    """Contrato do JS do botão flutuante (sem browser): reopen + click fora + Esc."""
    from pathlib import Path
    js = Path(__file__).resolve().parents[1].joinpath("static", "produtividade_rapida.js").read_text(encoding="utf-8")
    assert "prod_rapida_modo" in js
    assert "escolherAbaAoAbrir" in js
    assert "localStorage" in js
    assert "cliqueForaDeveFechar" in js
    assert "digitandoOuAutocomplete" in js
    assert 'addEventListener("mousedown"' in js or "addEventListener('mousedown'" in js
    assert 'ev.key === "Escape"' in js or "ev.key === 'Escape'" in js
    # Não para o tick ao fechar o painel
    assert "NÃO para o tick" in js or "nao para o tick" in js.lower() or "continuar mostrando o tempo" in js.lower() or "painel minimizado" in js

def test_lancar_rapido_respeita_duracao_com_ultimo_fim():
    """Regressão: duração 5 não vira o vão até 'agora' (ex.: 55)."""
    con = _mem()
    PR.init_produtividade_schema(con)
    PR.registrar_registro(
        con,
        responsavel_user_id=7,
        responsavel_nome="Carla",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="Anterior",
        prioridade="Média",
        status="Concluída",
        hora_inicio="13:30",
        hora_fim="13:35",
        agora=datetime(2026, 10, 5, 13, 35, 0),
    )
    rid = PR.lancar_rapido(
        con,
        responsavel_user_id=7,
        responsavel_nome="Carla",
        categoria=PR.CATEGORIA_PADRAO,
        tarefa="Nova 5 min",
        duracao_min=5,
        agora=datetime(2026, 10, 5, 14, 30, 0),
    )
    row = next(r for r in PR.listar_registros(con) if r["id"] == rid)
    assert row["hora_inicio"] == "13:35"
    assert row["hora_fim"] == "13:40"
    assert row["tempo_liquido_min"] == 5


def test_recusa_inicio_depois_do_fim():
    con = _mem()
    PR.init_produtividade_schema(con)
    with pytest.raises(ValueError, match="anterior"):
        PR.registrar_registro(
            con,
            responsavel_user_id=1,
            responsavel_nome="T",
            categoria=PR.CATEGORIA_PADRAO,
            tarefa="X",
            prioridade="Média",
            status="Concluída",
            hora_inicio="15:00",
            hora_fim="14:00",
        )


def test_recusa_duracao_absurda():
    con = _mem()
    PR.init_produtividade_schema(con)
    with pytest.raises(ValueError, match="1440"):
        PR.lancar_rapido(
            con,
            responsavel_user_id=1,
            responsavel_nome="T",
            categoria=PR.CATEGORIA_PADRAO,
            tarefa="Absurdo",
            duracao_min=100000,
            agora=datetime(2026, 10, 5, 12, 0, 0),
        )


def test_formulario_e_js_validam_duracao_e_horas():
    html = Path(__file__).resolve().parents[1].joinpath(
        "templates", "_produtividade_rapida.html"
    ).read_text(encoding="utf-8")
    assert 'name="duracao_min"' in html
    assert 'max="1440"' in html
    lista = Path(__file__).resolve().parents[1].joinpath(
        "templates", "produtividade_lista.html"
    ).read_text(encoding="utf-8")
    assert "data-prod-validar-horas" in lista
    js = Path(__file__).resolve().parents[1].joinpath(
        "static", "produtividade_rapida.js"
    ).read_text(encoding="utf-8")
    assert "validarLancamentoForm" in js
    assert "1440" in js


# --- O BOTÃO FICAVA INERTE COM CRONÔMETRO ABERTO DE OUTRO DIA (06/10/2026) ---
# Relato do oficial: «deu um pequeno bug no botao de produtividade da debora,
# ficou inerte». Reproduzido: cronômetro iniciado num dia e lido no seguinte
# com o relógio ANTES da hora de início → `minutos_entre_horas` recusava
# («início depois do fim»), e status e contexto davam HTTP 500. O painel abria
# sem o cronômetro, «Iniciar» respondia o mesmo erro, e não havia como parar.

def _cronometro_de_ontem(con, uid=7):
    from datetime import timedelta
    PR.init_produtividade_schema(con)
    ontem_2330 = datetime.combine(date.today() - timedelta(days=1),
                                  datetime.min.time()).replace(hour=23, minute=30)
    PR.iniciar_cronometro(con, responsavel_user_id=uid, responsavel_nome="Teste",
                          categoria=PR.CATEGORIA_PADRAO, tarefa="ESQUECIDO",
                          agora=ontem_2330)
    return ontem_2330


def test_cronometro_de_ontem_nao_derruba_o_status():
    con = _mem()
    ontem = _cronometro_de_ontem(con)
    ativo = PR.cronometro_em_andamento(con, responsavel_user_id=7)
    assert ativo is not None and ativo["tarefa"] == "ESQUECIDO"
    # conta a noite: desde ontem 23:30 até agora
    esperado = int((datetime.now() - ontem).total_seconds() // 60)
    assert abs(ativo["decorrido_min"] - esperado) <= 1


def test_parar_cronometro_de_ontem_fecha_pela_regra_do_expediente_e_avisa():
    # CONTRATO MUDADO EM 11/10/2026, por ordem do oficial (aviso 14h15, fecha
    # 14h30 com hora 14h15). Até então este teste cobrava o fechamento às
    # 23:59, que somou 28 h fantasmas em quatro dias. Começado às 23:30 conta
    # como confirmado (depois das 14h15); sem ação no sistema depois do início,
    # fecha com duração zero e pede conferência. Ver test_cronometro_esquecido.py.
    con = _mem()
    _cronometro_de_ontem(con)
    final = PR.parar_cronometro(con, responsavel_user_id=7)
    assert final["status"] == "Concluída"
    assert final["hora_fim"] == "23:30"
    assert "confira" in (final.get("observacoes") or "")
    assert final.get("tempo_liquido_min") == 0
    assert final.get("encerrado_automaticamente")
    # e o usuário volta a poder iniciar outro
    assert PR.cronometro_em_andamento(con, responsavel_user_id=7) is None
    PR.iniciar_cronometro(con, responsavel_user_id=7, responsavel_nome="Teste",
                          categoria=PR.CATEGORIA_PADRAO, tarefa="NOVO")


def test_registro_gravado_com_fim_antes_do_inicio_nao_derruba_a_lista():
    con = _mem()
    PR.init_produtividade_schema(con)
    con.execute(
        "INSERT INTO prod_registros(data_registro, responsavel_user_id, responsavel_nome,"
        " categoria, tarefa, prioridade, status, hora_inicio, hora_fim, pausas_min, criado_em)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (date.today().isoformat(), 7, "Teste", PR.CATEGORIA_PADRAO, "TORTO", "Média",
         "Concluída", "15:00", "09:00", 0, datetime.now().isoformat()))
    regs = PR.listar_registros(con, responsavel_user_id=7)
    assert regs and regs[0]["tempo_liquido_min"] is None
    assert regs[0]["horario_inconsistente"] is True

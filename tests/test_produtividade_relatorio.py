"""Relatórios simplificado e completo da produtividade, por período (of-0119).

Um relatório não pode omitir linha sem dizer, nem mostrar a um usuário comum os
registros de outra pessoa. Estes testes guardam as duas coisas, as somas conferidas
à mão e a exportação de um dia só, que continua como sempre foi.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import sys as _sys
import zipfile
from datetime import date
from pathlib import Path

import produtividade as PR
import pytest

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from conftest import cg_login  # noqa: E402

URL = "/administrativo/produtividade/relatorio"
URL_CSV = "/administrativo/produtividade/exportar.csv"
URL_XLSX = "/administrativo/produtividade/exportar.xlsx"
LISTA = "/administrativo/produtividade"
CAT = PR.CATEGORIAS_ATIVAS
SENHA = "Senha#12345"


def _con():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    PR.init_produtividade_schema(con)
    return con


def _inserir(con, *, dia="2026-10-05", uid=1, nome="Mario Exemplo dos Santos", cat=None,
             tarefa="TAREFA", prior="Média", status="Concluída", ini="08:00", fim="09:00",
             pausas=0, plan=None, obs=None):
    con.execute(
        "INSERT INTO prod_registros(data_registro, responsavel_user_id, responsavel_nome,"
        " categoria, tarefa, prioridade, status, hora_inicio, hora_fim, pausas_min,"
        " tempo_planejado_min, observacoes, criado_em)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (dia, uid, nome, cat or CAT[0], tarefa, prior, status, ini, fim, pausas, plan, obs,
         "2026-10-05T08:00:00"))


def _gravar(casa, *registros):
    con = sqlite3.connect(casa["banco"])
    PR.init_produtividade_schema(con)
    for r in registros:
        _inserir(con, **r)
    con.commit()
    con.close()


def _abas(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return (z.read("xl/workbook.xml").decode("utf-8"),
                z.read("xl/worksheets/sheet1.xml").decode("utf-8"),
                z.read("xl/worksheets/sheet2.xml").decode("utf-8"))


def _usar_layout(c, layout):
    pagina = c.get("/").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    r = c.post("/preferencias/layout", data={"layout": layout, "next": "/", "csrf_token": token})
    assert r.status_code == 302


# ------------------------------------------------------------ as somas à mão
def test_somas_do_resumo_conferidas_a_mao():
    regs = [
        # Mario: 60 + 30 min; 2 concluídas de 3; eficiências 50 e 200
        {"id": 1, "data_registro": "2026-10-05", "responsavel_user_id": 1,
         "responsavel_nome": "Mario", "categoria": CAT[0], "status": "Concluída",
         "hora_inicio": "08:00", "hora_fim": "09:00", "pausas_min": 0, "tempo_planejado_min": 30},
        {"id": 2, "data_registro": "2026-10-06", "responsavel_user_id": 1,
         "responsavel_nome": "Mario", "categoria": CAT[1], "status": "Concluída",
         "hora_inicio": "08:00", "hora_fim": "08:40", "pausas_min": 10, "tempo_planejado_min": 60},
        {"id": 3, "data_registro": "2026-10-06", "responsavel_user_id": 1,
         "responsavel_nome": "Mario", "categoria": CAT[1], "status": "Pausada",
         "hora_inicio": "09:00", "hora_fim": None, "pausas_min": 0, "tempo_planejado_min": None},
        # Beatriz: 120 min, sem planejado
        {"id": 4, "data_registro": "2026-10-05", "responsavel_user_id": 2,
         "responsavel_nome": "Beatriz", "categoria": CAT[0], "status": "Concluída",
         "hora_inicio": "10:00", "hora_fim": "12:00", "pausas_min": 0, "tempo_planejado_min": None},
    ]
    r = PR.resumir_registros([PR._enriquecer_registro(x) for x in regs])

    g = r["geral"]
    assert (g["tarefas"], g["concluidas"], g["taxa_conclusao_pct"]) == (4, 3, 75.0)
    assert (g["tempo_liquido_min"], g["tempo_liquido_hhmm"]) == (210, "3:30")
    assert g["tempo_medio_min"] == 70.0
    assert g["eficiencia_media_pct"] == 125.0
    assert g["sem_tempo"] == 1

    assert [f["nome"] for f in r["funcionarios"]] == ["Beatriz", "Mario"]
    bia, mario = r["funcionarios"]
    assert (bia["tarefas"], bia["tempo_liquido_min"], bia["eficiencia_media_pct"]) == (1, 120, None)
    assert (mario["tarefas"], mario["concluidas"], mario["taxa_conclusao_pct"]) == (3, 2, 66.7)
    assert (mario["tempo_liquido_min"], mario["tempo_medio_min"]) == (90, 45.0)
    assert mario["sem_tempo"] == 1

    cats = {c["categoria"]: c for c in r["categorias"]}
    assert (cats[CAT[0]]["tarefas"], cats[CAT[0]]["tempo_liquido_min"]) == (2, 180)
    assert (cats[CAT[1]]["tarefas"], cats[CAT[1]]["tempo_liquido_min"]) == (2, 30)
    assert cats[CAT[1]]["sem_tempo"] == 1


def test_mais_de_5000_linhas_nada_e_cortado():
    con = _con()
    for i in range(5003):
        _inserir(con, dia="2026-10-05", tarefa=f"T{i}")
    con.commit()
    regs = PR.registros_do_periodo(con, data_de="2026-10-01", data_ate="2026-10-31")
    assert len(regs) == 5003
    assert PR.resumir_registros(regs)["geral"]["tarefas"] == 5003
    assert PR.resumir_registros(regs)["geral"]["tempo_liquido_min"] == 5003 * 60
    texto = PR.exportar_csv(con, periodo=("2026-10-01", "2026-10-31"))
    assert len(list(csv.reader(io.StringIO(texto), delimiter=";"))) == 5004


def test_em_andamento_e_inconsistente_contam_como_sem_tempo(cg_casa_logada):
    casa = cg_casa_logada
    _gravar(casa,
            dict(tarefa="NORMAL"),
            dict(tarefa="CORRENDO", status="Em andamento", fim=None),
            dict(tarefa="ANOTADA ABERTA", status="Em andamento", ini="08:00", fim="10:00"),
            dict(tarefa="TORTA", ini="15:00", fim="09:00"),
            dict(tarefa="SEM FIM", status="Pausada", fim=None))
    html = casa["c"].get(f"{URL}?tipo=completo&data_de=2026-10-01&data_ate=2026-10-31"
                         ).get_data(as_text=True)
    for tarefa in ("NORMAL", "CORRENDO", "ANOTADA ABERTA", "TORTA", "SEM FIM"):
        assert tarefa in html
    assert html.count("Sem tempo: em andamento") == 2
    assert "Sem tempo: horário inconsistente" in html
    assert "Sem tempo: sem hora de início ou fim" in html

    con = sqlite3.connect(casa["banco"])
    g = PR.resumir_registros(PR.registros_do_periodo(
        con, data_de="2026-10-01", data_ate="2026-10-31"))["geral"]
    con.close()
    assert (g["tarefas"], g["sem_tempo"], g["tempo_liquido_min"]) == (5, 4, 60)


def test_tempo_liquido_zero_nao_e_sem_tempo_e_fica_fora_da_media():
    regs = [PR._enriquecer_registro(x) for x in (
        {"id": 1, "data_registro": "2026-10-05", "status": "Concluída", "responsavel_user_id": 1,
         "responsavel_nome": "M", "categoria": "C", "hora_inicio": "08:00", "hora_fim": "08:10",
         "pausas_min": 10},
        {"id": 2, "data_registro": "2026-10-05", "status": "Concluída", "responsavel_user_id": 1,
         "responsavel_nome": "M", "categoria": "C", "hora_inicio": "09:00", "hora_fim": "09:30",
         "pausas_min": 0},
    )]
    g = PR.resumir_registros(regs)["geral"]
    assert (g["sem_tempo"], g["tempo_liquido_min"], g["tempo_medio_min"]) == (0, 30, 30.0)


def test_nome_alterado_no_periodo_fica_numa_linha_so():
    con = _con()
    _inserir(con, dia="2026-10-01", uid=7, nome="Carla Exemplo")
    _inserir(con, dia="2026-10-20", uid=7, nome="Carla Exemplo de Souza")
    _inserir(con, dia="2026-10-02", uid=None, nome="Pedro Exemplo dos Santos")
    _inserir(con, dia="2026-10-03", uid=None, nome="Pedro Exemplo dos Santos")
    con.commit()
    r = PR.resumir_registros(PR.registros_do_periodo(
        con, data_de="2026-10-01", data_ate="2026-10-31"))
    assert [(f["nome"], f["tarefas"]) for f in r["funcionarios"]] == [
        ("Carla Exemplo de Souza", 2), ("Pedro Exemplo dos Santos", 2)]


def test_filtros_de_periodo_funcionario_categoria_prioridade_status_e_texto(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    _gravar(casa,
            dict(tarefa="ALFA", dia="2026-10-05", uid=1, cat=CAT[0], prior="Alta", obs="urgente"),
            dict(tarefa="BRAVO", dia="2026-10-06", uid=2, nome="Beatriz Exemplo de Souza", cat=CAT[1]),
            dict(tarefa="CHARLIE", dia="2026-10-07", uid=1, status="Pausada", fim=None),
            dict(tarefa="FORA", dia="2026-09-30", uid=1))
    base = f"{URL}?tipo=completo&data_de=2026-10-01&data_ate=2026-10-31"

    def vistas(extra=""):
        h = c.get(base + extra).get_data(as_text=True)
        return {t for t in ("ALFA", "BRAVO", "CHARLIE", "FORA") if f"<td>{t}</td>" in h}

    assert vistas() == {"ALFA", "BRAVO", "CHARLIE"}
    assert vistas("&responsavel=2") == {"BRAVO"}
    assert vistas(f"&categoria={CAT[1]}") == {"BRAVO"}
    assert vistas("&prioridade=Alta") == {"ALFA"}
    assert vistas("&status=Pausada") == {"CHARLIE"}
    assert vistas("&q=urgente") == {"ALFA"}


def test_simplificado_nao_traz_registro_nem_categoria(cg_casa_logada):
    casa = cg_casa_logada
    _gravar(casa, dict(tarefa="ALFA"))
    h = casa["c"].get(f"{URL}?data_de=2026-10-01&data_ate=2026-10-31").get_data(as_text=True)
    assert 'data-relatorio="simplificado"' in h
    assert "<td>ALFA</td>" not in h and "Total por categoria" not in h
    assert "Mario Exemplo dos Santos" in h and "Total geral" in h
    assert "capacidade" not in h[h.index('data-relatorio='):].lower()


# ------------------------------------------------------- o usuário comum
def test_user_com_outro_responsavel_ve_so_os_proprios(cg_casa_logada):
    casa = cg_casa_logada
    db = casa["db"]
    uid = db.create_user("carla", "Carla Exemplo", SENHA, "USER")
    _gravar(casa,
            dict(tarefa="MINHA TAREFA", uid=uid, nome="Carla Exemplo"),
            dict(tarefa="TAREFA ALHEIA", uid=uid + 1, nome="Beatriz Exemplo de Souza"))
    casa_c = casa["c"].application.test_client()
    cg_login(casa_c, "carla", SENHA)
    consulta = f"?tipo=completo&data_de=2026-10-01&data_ate=2026-10-31&responsavel={uid + 1}"

    tela = casa_c.get(URL + consulta).get_data(as_text=True)
    assert "MINHA TAREFA" in tela and "TAREFA ALHEIA" not in tela
    assert "Beatriz Exemplo de Souza" not in tela

    texto = casa_c.get(URL_CSV + consulta).get_data(as_text=True)
    assert "MINHA TAREFA" in texto and "TAREFA ALHEIA" not in texto

    _wb, s1, s2 = _abas(casa_c.get(URL_XLSX + consulta).get_data())
    assert "MINHA TAREFA" in s1 and "TAREFA ALHEIA" not in s1
    assert "Beatriz" not in s2 and "Carla Exemplo" in s2


# ------------------------------------------------------------- o período
def test_validar_periodo_regras():
    hoje = date(2026, 10, 15)
    assert PR.validar_periodo(None, None, hoje=hoje) == ("2026-10-01", "2026-10-31")
    assert PR.validar_periodo("2026-10-03", None, hoje=hoje) == ("2026-10-03", "2026-10-15")
    assert PR.validar_periodo(None, "2026-09-20", hoje=hoje) == ("2026-09-01", "2026-09-20")
    assert PR.validar_periodo("2025-01-01", "2026-01-01", hoje=hoje)  # 366 dias, com as pontas
    with pytest.raises(PR.PeriodoInvalido, match="367"):
        PR.validar_periodo("2025-01-01", "2026-01-02", hoje=hoje)
    with pytest.raises(PR.PeriodoInvalido, match="depois"):
        PR.validar_periodo("2026-10-20", "2026-10-01", hoje=hoje)


@pytest.mark.parametrize("consulta,frase", [
    ("data_de=nao-e-data&data_ate=2026-10-31", "Data inválida"),
    ("data_de=0026-10-01&data_ate=2026-10-31", "Data inválida"),
    ("data_de=2026-10-20&data_ate=2026-10-01", "depois do fim"),
    ("data_de=2024-01-01&data_ate=2026-01-01", "o limite é 366"),
])
@pytest.mark.parametrize("rota", [URL, URL_CSV, URL_XLSX])
def test_periodo_errado_volta_com_aviso_sem_erro(cg_casa_logada, rota, consulta, frase):
    c = cg_casa_logada["c"]
    r = c.get(f"{rota}?{consulta}&categoria={CAT[0]}", follow_redirects=False)
    assert r.status_code == 302 and URL in r.headers["Location"]
    assert "data_de" not in r.headers["Location"] and "categoria=" in r.headers["Location"]
    final = c.get(r.headers["Location"])
    assert final.status_code == 200 and frase in final.get_data(as_text=True)


def test_sem_periodo_abre_o_mes_corrente(cg_casa_logada):
    h = cg_casa_logada["c"].get(URL).get_data(as_text=True)
    assert f'value="{date.today().replace(day=1).isoformat()}"' in h


def test_a_rota_do_relatorio_so_aceita_get(cg_casa_logada):
    assert cg_casa_logada["c"].post(URL, data={}).status_code in (400, 403, 405)


# --------------------------------------------------------- as exportações
def test_exportacao_so_com_data_nao_muda(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    _gravar(casa, dict(dia="2026-10-05", tarefa="DO DIA", plan=30),
            dict(dia="2026-10-06", tarefa="DO OUTRO DIA"))

    r = c.get(f"{URL_CSV}?data=2026-10-05")
    assert 'filename="produtividade_2026-10-05.csv"' in r.headers["Content-Disposition"]
    con = sqlite3.connect(casa["banco"])
    assert r.get_data(as_text=True) == "﻿" + PR.exportar_csv(con, data_filtro="2026-10-05")
    linhas = list(csv.reader(io.StringIO(r.get_data(as_text=True).lstrip("﻿")), delimiter=";"))
    assert linhas[0] == list(PR.EXPORT_COLUNAS)
    assert len(linhas) == 2 and linhas[1][3] == "DO DIA"

    x = c.get(f"{URL_XLSX}?data=2026-10-05&responsavel=Todos")
    assert 'filename="produtividade_2026-10-05.xlsx"' in x.headers["Content-Disposition"]
    wb, s1, s2 = _abas(x.get_data())
    con.close()
    assert "Painel" in wb and "Resumo" not in wb
    assert "DO DIA" in s1 and "DO OUTRO DIA" not in s1
    assert "PAINEL DE PRODUTIVIDADE" in s2 and "Uso da capacidade" in s2


def test_exportacao_com_periodo_traz_os_dias_e_o_resumo(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    _gravar(casa, dict(dia="2026-10-05", tarefa="DO DIA"),
            dict(dia="2026-10-06", tarefa="DO OUTRO DIA"),
            dict(dia="2026-11-06", tarefa="FORA DO PERIODO"))
    consulta = "?data=2026-10-05&data_de=2026-10-05&data_ate=2026-10-06"

    r = c.get(URL_CSV + consulta)
    assert "produtividade_2026-10-05_a_2026-10-06.csv" in r.headers["Content-Disposition"]
    texto = r.get_data(as_text=True)
    assert "DO DIA" in texto and "DO OUTRO DIA" in texto and "FORA DO PERIODO" not in texto

    x = c.get(URL_XLSX + consulta)
    assert "produtividade_2026-10-05_a_2026-10-06.xlsx" in x.headers["Content-Disposition"]
    wb, s1, s2 = _abas(x.get_data())
    assert "Resumo" in wb and "Painel" not in wb
    assert "DO DIA" in s1 and "DO OUTRO DIA" in s1 and "FORA DO PERIODO" not in s1
    assert "RESUMO DE PRODUTIVIDADE" in s2 and "2026-10-05 a 2026-10-06" in s2
    assert "Mario Exemplo dos Santos" in s2 and "Registros sem tempo" in s2
    assert "capacidade" not in s2.lower()


def test_filtro_sem_periodo_vira_um_dia_com_resumo(cg_casa_logada):
    casa = cg_casa_logada
    _gravar(casa, dict(dia="2026-10-05", tarefa="ALFA", cat=CAT[0]),
            dict(dia="2026-10-05", tarefa="BRAVO", cat=CAT[1]),
            dict(dia="2026-10-06", tarefa="CHARLIE", cat=CAT[0]))
    wb, s1, _s2 = _abas(casa["c"].get(f"{URL_XLSX}?data=2026-10-05&categoria={CAT[0]}").get_data())
    assert "Resumo" in wb and "Painel" not in wb
    assert "ALFA" in s1 and "BRAVO" not in s1 and "CHARLIE" not in s1


def test_observacao_com_igual_nao_vira_formula(cg_casa_logada):
    casa = cg_casa_logada
    _gravar(casa, dict(obs="=2+2", tarefa="ALFA"))
    consulta = "?data_de=2026-10-01&data_ate=2026-10-31"
    texto = casa["c"].get(URL_CSV + consulta).get_data(as_text=True).lstrip("﻿")
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert linhas[1][PR.EXPORT_COLUNAS.index("Observações")] == "'=2+2"

    _wb, s1, _s2 = _abas(casa["c"].get(URL_XLSX + consulta).get_data())
    assert "<f>" not in s1
    assert 't="inlineStr"><is><t>=2+2</t>' in s1


# ------------------------------------------------------------- as telas
@pytest.mark.parametrize("layout", ["antigo", "novo"])
@pytest.mark.parametrize("tipo", ["simplificado", "completo"])
def test_a_tela_abre_nos_dois_layouts_e_tipos(cg_casa_logada, layout, tipo):
    casa = cg_casa_logada
    c = casa["c"]
    _usar_layout(c, layout)
    _gravar(casa, dict(tarefa="ALFA"))
    r = c.get(f"{URL}?tipo={tipo}&data_de=2026-10-01&data_ate=2026-10-31")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert ("cg-app" in h) == (layout == "novo")
    assert f'data-relatorio="{tipo}"' in h
    assert "window.print()" in h and "Exportar CSV" in h and "Exportar Excel" in h
    assert "01/10/2026 a 31/10/2026" in h and "Emitido em" in h and " por " in h


def test_lista_leva_os_filtros_aos_botoes_e_ao_relatorio(cg_casa_logada):
    h = cg_casa_logada["c"].get(
        f"{LISTA}?data=2026-10-05&data_de=2026-10-01&data_ate=2026-10-31&prioridade=Alta&q=abc"
    ).get_data(as_text=True).replace("&amp;", "&")
    achados = re.findall(r'href="([^"]*produtividade/(?:relatorio|exportar\.\w+)[^"]*)"', h)
    assert {a.split("?")[0].rsplit("/", 1)[1] for a in achados} == {
        "relatorio", "exportar.csv", "exportar.xlsx"}
    for a in achados:
        for pedaco in ("data_de=2026-10-01", "data_ate=2026-10-31", "prioridade=Alta", "q=abc"):
            assert pedaco in a, a
    assert "data-lista-cortada" not in h


def test_lista_sem_filtro_mantem_os_botoes_so_com_a_data(cg_casa_logada):
    h = cg_casa_logada["c"].get(f"{LISTA}?data=2026-10-05").get_data(as_text=True)
    botao = re.search(r'href="([^"]*exportar\.csv[^"]*)"', h).group(1).replace("&amp;", "&")
    assert sorted(botao.split("?")[1].split("&")) == ["data=2026-10-05", "responsavel=Todos"]


@pytest.mark.parametrize("consulta,linhas,limite,avisa", [
    ("data_de=2026-10-01&data_ate=2026-10-31", 500, 500, True),
    ("data_de=2026-10-01&data_ate=2026-10-31", 499, 500, False),
    ("data_de=2026-10-01&data_ate=2026-10-31&ordem=TAREFA", 2000, 2000, True),
    ("data=2026-10-05", 120, 120, True),
])
def test_lista_cortada_avisa_no_limite_real(cg_casa_logada, consulta, linhas, limite, avisa):
    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    PR.init_produtividade_schema(con)
    for i in range(linhas):
        _inserir(con, tarefa=f"T{i}")
    con.commit()
    con.close()
    h = casa["c"].get(f"{LISTA}?{consulta}").get_data(as_text=True)
    assert ("data-lista-cortada" in h) == avisa
    if avisa:
        assert f"limite de {limite} linhas" in h

"""O mais recente em cima, lote 1 (of-0150).

Quatro listas sem limite de linhas mostram primeiro o que entrou por último: as
minutas e as revisões do Livro 3, os expedientes prontos para encerrar e os
registros de cada funcionário no relatório completo da produtividade.

O CSV e o Excel do relatório continuam cronológicos, e a ordem nova não mexe nas
somas, no nome mais recente nem na ordem alfabética do resumo. Cada lista tem dois
registros ou mais, para o teste não passar por acaso.
"""
from __future__ import annotations

import csv
import io
import sqlite3
import zipfile

import expediente_tarefa as EXPT
import produtividade as PR
import ra_minuta as MIN
import ra_revisao as RV

URL_RELATORIO = "/administrativo/produtividade/relatorio"
URL_CSV = "/administrativo/produtividade/exportar.csv"
URL_XLSX = "/administrativo/produtividade/exportar.xlsx"
PERIODO = "tipo=completo&data_de=2026-10-01&data_ate=2026-10-31"

# Na ordem de gravação, de propósito diferente das duas ordens conferidas abaixo
GRAVADOS = (
    dict(tarefa="TAREFA TARDE", dia="2026-10-07", ini="14:00", fim="15:00"),
    dict(tarefa="TAREFA SEM HORA", dia="2026-10-07", ini=None, fim=None),
    dict(tarefa="TAREFA NOVE PRIMEIRA", dia="2026-10-07", ini="09:00", fim="10:00"),
    dict(tarefa="TAREFA NOVE SEGUNDA", dia="2026-10-07", ini="09:00", fim="10:00"),
    dict(tarefa="TAREFA DIA ANTERIOR", dia="2026-10-05", ini="16:00", fim="17:00"),
)
DO_NOVO_AO_ANTIGO = ["TAREFA TARDE", "TAREFA NOVE SEGUNDA", "TAREFA NOVE PRIMEIRA",
                     "TAREFA SEM HORA", "TAREFA DIA ANTERIOR"]
# A exportação ordena por data e id, sem olhar o horário (`_linhas_de_exportacao`)
CRONOLOGICO = ["TAREFA DIA ANTERIOR", "TAREFA TARDE", "TAREFA SEM HORA",
               "TAREFA NOVE PRIMEIRA", "TAREFA NOVE SEGUNDA"]


def _na_ordem(texto: str, *trechos: str) -> None:
    """Todos os trechos aparecem no texto, nesta ordem."""
    posicoes = [texto.index(t) for t in trechos]
    assert posicoes == sorted(posicoes), list(zip(trechos, posicoes))


def _registro(db, numero: int) -> int:
    with db.transaction() as con:
        con.execute(
            """INSERT INTO ra_registros(numero, livro, natureza, situacao, criado_em)
               VALUES (?,'3','CEDULA_CREDITO_RURAL','ATIVO',?)""", (numero, db.now()))
        return con.execute("SELECT id FROM ra_registros WHERE numero=?",
                           (numero,)).fetchone()[0]


def _gravar_registros(casa, *registros) -> None:
    con = sqlite3.connect(casa["banco"])
    PR.init_produtividade_schema(con)
    for r in registros:
        con.execute(
            "INSERT INTO prod_registros(data_registro, responsavel_user_id, responsavel_nome,"
            " categoria, tarefa, prioridade, status, hora_inicio, hora_fim, pausas_min,"
            " criado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (r["dia"], r.get("uid", 1), r.get("nome", "Mario Exemplo dos Santos"),
             PR.CATEGORIAS_ATIVAS[0], r["tarefa"], "Média", "Concluída", r["ini"], r["fim"],
             0, "2026-10-05T08:00:00"))
    con.commit()
    con.close()


# ------------------------------------------------------------ as três consultas
def test_minutas_a_revisar_mais_recente_em_cima(cg_casa_logada):
    casa = cg_casa_logada
    db = casa["db"]
    rid = _registro(db, 1198)
    with db.transaction() as con:
        antiga = MIN.criar(con, registro_id=rid, tipo="AV", agora=db.now(),
                           teor="AV-01/1.198 - MINUTA ANTIGA, à vista do instrumento.")
        nova = MIN.criar(con, registro_id=rid, tipo="AV", agora=db.now(),
                         teor="AV-02/1.198 - MINUTA NOVA, à vista do instrumento.")
    with db.connect() as con:
        assert [m["id"] for m in MIN.a_revisar(con)] == [nova, antiga]
    html = casa["c"].get("/livro3/minutas").get_data(as_text=True)
    _na_ordem(html, "MINUTA NOVA", "MINUTA ANTIGA")


def test_revisoes_abertas_mais_recente_em_cima(cg_casa_logada):
    casa = cg_casa_logada
    db = casa["db"]
    rid = _registro(db, 1198)
    with db.transaction() as con:
        antiga = RV.anotar(con, registro_id=rid, assunto="NOTA ANTIGA",
                           nota="Conferir o título.", agora=db.now())
        nova = RV.anotar(con, registro_id=rid, assunto="NOTA NOVA",
                         nota="Conferir a data.", agora=db.now())
    with db.connect() as con:
        assert [n["id"] for n in RV.abertas(con)] == [nova, antiga]
    html = casa["c"].get("/livro3/revisoes").get_data(as_text=True)
    _na_ordem(html, "NOTA NOVA", "NOTA ANTIGA")


def test_expedientes_prontos_mais_recente_em_cima(cg_casa_logada):
    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with con:
        for protocolo in ("2026/006", "2026/007"):
            eid = int(con.execute(
                """INSERT INTO expedientes (internal_protocol, source, subject, category,
                       received_at, stage, created_by, created_at, updated_at)
                   VALUES (?, 'MALOTE', 'ofício da corregedoria', 'CORREGEDORIA',
                           '2026-08-01', 'RECEBIDO', 1, '2026-08-01T09:00', '2026-08-01T09:00')""",
                (protocolo,)).lastrowid)
            con.execute(
                """INSERT INTO tasks (title, status, linked_expediente_id, created_by,
                       created_at, updated_at)
                   VALUES ('responder o ofício', 'CONCLUIDA', ?, 1,
                           '2026-08-01T09:00', '2026-08-01T09:00')""", (eid,))
    assert [x["internal_protocol"] for x in EXPT.expedientes_com_tudo_concluido(con)] == [
        "2026/007", "2026/006"]
    con.close()
    html = casa["c"].get("/expedientes/prontos-para-encerrar").get_data(as_text=True)
    _na_ordem(html, "2026/007", "2026/006")


# ---------------------------------------------------------- o relatório completo
def _periodo(casa) -> list[dict]:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    regs = PR.registros_do_periodo(con, data_de="2026-10-01", data_ate="2026-10-31")
    con.close()
    return regs


def test_relatorio_completo_do_novo_ao_antigo(cg_casa_logada):
    casa = cg_casa_logada
    _gravar_registros(casa, *GRAVADOS)
    resumo = PR.resumir_registros(_periodo(casa))
    assert [r["tarefa"] for r in resumo["funcionarios"][0]["registros"]] == DO_NOVO_AO_ANTIGO
    html = casa["c"].get(f"{URL_RELATORIO}?{PERIODO}").get_data(as_text=True)
    _na_ordem(html, *[f"<td>{t}</td>" for t in DO_NOVO_AO_ANTIGO])


def test_registros_do_periodo_continua_cronologica(cg_casa_logada):
    casa = cg_casa_logada
    _gravar_registros(casa, *GRAVADOS)
    assert [r["tarefa"] for r in _periodo(casa)] == CRONOLOGICO


def test_csv_do_relatorio_continua_cronologico(cg_casa_logada):
    casa = cg_casa_logada
    _gravar_registros(casa, *GRAVADOS)
    texto = casa["c"].get(f"{URL_CSV}?{PERIODO}").get_data(as_text=True)
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    coluna = PR.EXPORT_COLUNAS.index("Tarefa")
    assert [linha[coluna] for linha in linhas[1:]] == CRONOLOGICO


def test_excel_do_relatorio_continua_cronologico(cg_casa_logada):
    casa = cg_casa_logada
    _gravar_registros(casa, *GRAVADOS)
    blob = casa["c"].get(f"{URL_XLSX}?{PERIODO}").get_data()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        registros = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    _na_ordem(registros, *CRONOLOGICO)


def test_a_ordem_nao_muda_somas_nome_nem_ordem_alfabetica(cg_casa_logada):
    casa = cg_casa_logada
    _gravar_registros(
        casa, *GRAVADOS,
        dict(tarefa="TAREFA NOME VELHO", dia="2026-10-01", ini="08:00", fim="08:30",
             uid=7, nome="Carla Exemplo"),
        dict(tarefa="TAREFA NOME NOVO", dia="2026-10-20", ini="08:00", fim="09:00",
             uid=7, nome="Carla Exemplo de Souza"))
    regs = _periodo(casa)

    def sem_as_linhas(resumo):
        return {**resumo, "funcionarios": [
            {k: v for k, v in f.items() if k != "registros"} for f in resumo["funcionarios"]]}

    direto = PR.resumir_registros(regs)
    assert sem_as_linhas(direto) == sem_as_linhas(PR.resumir_registros(regs[::-1]))
    assert [f["nome"] for f in direto["funcionarios"]] == [
        "Carla Exemplo de Souza", "Mario Exemplo dos Santos"]
    assert direto["geral"]["tarefas"] == 7
    # Mario: 60 min em cada uma das 4 linhas com horário; Carla: 30 + 60
    assert direto["geral"]["tempo_liquido_min"] == 4 * 60 + 30 + 60
    assert [(f["tarefas"], f["tempo_liquido_min"]) for f in direto["funcionarios"]] == [
        (2, 90), (5, 240)]

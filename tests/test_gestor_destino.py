"""Para onde vai cada regra do gestor — e a checklist do dia só com a TI e o admin.

Pedido do oficial em 25/11/2026 (G007): «limpar o checklist do dia e deixar
apenas tarefas que podem ser feitas pela TI ou por admin [...] Digitalizacao so
pode ser feito por quem esta no cartorio, ou seja, os escreventes». Os testes
provam:

  * a tabela `gestor_destino.DESTINO` classifica TODA regra que o gestor rotula,
    com destino conhecido e motivo; regra nova fica na checklist;
  * as cargas das centrais ficam com a TI; a digitalização vai ao escrevente;
  * nenhuma regra de escrevente fica sem tarefa (P1 do G007, «pode» do titular);
  * a checklist só lista TI_ADMIN; o de escrevente sai, aparece no quadro «Fora
    da checklist» com a tarefa do gestor; o débito passado, à parte (compliance);
  * a COR OFICIAL não muda: o semáforo conta os achados de todos os destinos.

Datas fixas: terça 10/11/2026 é «hoje». Dados inventados.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conformidade as CF                     # noqa: E402
import gestor_checklist as CK                 # noqa: E402
import gestor_destino as GDS                  # noqa: E402
import gestor_rotina as GR                    # noqa: E402
from bd_nativo import banco                   # noqa: E402

HOJE = date(2026, 11, 10)


def _rodada_de_hoje(db) -> None:
    hoje = date.today().isoformat()
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_execucoes(iniciada_em, terminada_em, hoje, erro) "
            "VALUES (%s,%s,%s,%s)", (hoje + "T07:30:00", hoje + "T07:35:00", hoje, None))


def _achado(db, chave, regra, gravidade, setor, titulo="Achado de teste") -> None:
    visto = date.today().isoformat() + "T07:30:00"
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, prazo, "
            "primeiro_visto_em, ultimo_visto_em, resolvido_em) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (chave, regra, gravidade, setor, titulo, None, visto, visto, None))


def _tarefa(db, ref, titulo="Tarefa do gestor", status="ABERTA") -> int:
    with db.transaction() as con:
        return banco(con).escrever(
            "INSERT INTO tasks (source_type, source_ref, title, status, priority, "
            "created_at, updated_at) VALUES ('GESTOR', %s, %s, %s, 'ALTA', %s, %s) "
            "RETURNING id",
            (ref, titulo, status, "2026-11-10T07:30:00", "2026-11-10T07:30:00"))[0]["id"]


# ------------------------------------------------------------ a tabela


def test_toda_regra_do_gestor_tem_destino_e_motivo():
    faltam = sorted(set(GR.ROTULOS) - set(GDS.DESTINO))
    assert faltam == [], f"regra do gestor sem destino na tabela: {faltam}"
    for regra, (destino, motivo) in GDS.DESTINO.items():
        assert destino in GDS.DESTINOS, regra
        assert motivo.strip(), regra
    assert set(GDS.ROTULO_DO_DESTINO) == set(GDS.DESTINOS)


def test_regra_que_a_tabela_nao_conhece_fica_na_checklist():
    assert GDS.destino("REGRA_QUE_NASCEU_ONTEM") == GDS.TI_ADMIN
    assert GDS.destino(None) == GDS.TI_ADMIN
    assert GDS.destino("sirc") == GDS.TI_ADMIN          # caixa não importa


def test_as_centrais_ficam_com_a_ti_e_a_digitalizacao_vai_ao_escrevente():
    # 13/10/2026: «as centrais e cargas automático [...] eu vou centralizar elas
    # com envio automático por agentes» — e 25/11/2026: a checklist é delas.
    # (a carga inicial e o acervo inteiro do ONR são débito passado; nenhuma é do escrevente)
    for regra in GR.REGRAS_DAS_CENTRAIS:
        assert GDS.destino(regra) != GDS.ESCREVENTE, regra
    for regra in ("SIRC", "CRC", "CENSEC", "DOI", "IBGE", "OBITO_MENSAL", "CARGAS_RCPN_PRONTA",
                  "ONR_ENVIO_FALHOU"):
        assert GDS.destino(regra) == GDS.TI_ADMIN, regra
    for regra in ("BACKUP", "DISCO", "CNIB_PARADO", "IDENTIDADE_DOS_ROBOS",
                  "CAIXA_PRONTO_PARA_VISTO", "PLD_COAF"):
        assert GDS.destino(regra) == GDS.TI_ADMIN, regra
    # «Digitalizacao so pode ser feito por quem esta no cartorio»
    for regra in ("DIGITALIZACAO_DA_FICHA", "DIGITALIZACAO_ATRASADA", "CAIXA_DO_DIA_ABERTO",
                  "RCPN_ANOTACAO", "NOTAS_PDF", "PRENOTACAO_VENCIDA", "PROTESTO_TITULO_PARADO"):
        assert GDS.destino(regra) == GDS.ESCREVENTE, regra
    for regra in ("ONR_ACERVO_DECISAO", "ONR_CARGA_INICIAL", "PROTESTO_ANTES_DO_CORTE"):
        assert GDS.destino(regra) == GDS.COMPLIANCE, regra


def test_toda_regra_de_escrevente_vira_tarefa():
    """P1 do G007 («pode» do titular, 25/11/2026): fora da checklist e sem
    tarefa, o achado do escrevente não chegaria a ninguém."""
    escrevente = {r for r, (d, _) in GDS.DESTINO.items() if d == GDS.ESCREVENTE}
    assert not escrevente & GR.REGRAS_SEM_TAREFA
    for regra in ("DIGITALIZACAO_DA_FICHA", "CAIXA_DO_DIA_ABERTO", "NOTAS_PDF",
                  "PROTESTO_PAGAMENTO_SEM_LIVRO", "RCPN_FOLHA_SEGURANCA", "RTDPJ_LIVRO"):
        assert regra not in GR.REGRAS_SEM_TAREFA, regra


# ------------------------------------------------------------ a checklist


def test_a_checklist_so_lista_ti_admin_e_o_resto_vai_ao_quadro(cg_casa):
    db = cg_casa["db"]
    _rodada_de_hoje(db)
    _achado(db, "T:1", "SIRC", "VENCIDO", "RCPN")
    _achado(db, "T:2", "RCPN_ANOTACAO", "VENCIDO", "RCPN")
    _achado(db, "T:3", "RCPN_ANOTACAO", "PRAZO", "RCPN")
    _achado(db, "T:4", "DIGITALIZACAO_DA_FICHA", "CRITICO", "RI")
    _achado(db, "T:5", "ONR_ACERVO_DECISAO", "ATENCAO", "RI")
    _achado(db, "T:6", "REGRA_NOVA", "ATENCAO", "TI")
    anotacao = _tarefa(db, "GESTOR:RCPN_ANOTACAO:RCPN")
    _tarefa(db, "GESTOR:RCPN_ANOTACAO:NOTAS", status="CONCLUIDA")   # fechada não conta
    ck = CK.montar(db, date.today(), papel="ADMIN")
    regras = {a: [x["regra"] for x in v] for a, v in ck["achados"].items()}
    assert regras == {"RCPN": ["SIRC"], "ADMINISTRACAO": ["REGRA_NOVA"]}
    assert ck["total_achados"] == 2
    assert ck["total_fora"] == {GDS.ESCREVENTE: 3, GDS.COMPLIANCE: 1}
    linhas = {x["regra"]: x for x in ck["fora"][GDS.ESCREVENTE]}
    assert linhas["RCPN_ANOTACAO"]["n"] == 2 and linhas["RCPN_ANOTACAO"]["area"] == "RCPN"
    assert linhas["RCPN_ANOTACAO"]["tarefas"] == [{"id": anotacao, "setor": "RCPN"}]
    assert linhas["RCPN_ANOTACAO"]["rotulo"] == GR.ROTULOS["RCPN_ANOTACAO"]
    digi = linhas["DIGITALIZACAO_DA_FICHA"]
    assert digi["tarefas"] == []          # nasce na próxima rodada do gestor
    assert [x["regra"] for x in ck["fora"][GDS.COMPLIANCE]] == ["ONR_ACERVO_DECISAO"]


def test_a_cor_oficial_conta_todos_os_destinos(cg_casa):
    db = cg_casa["db"]
    _rodada_de_hoje(db)
    _achado(db, "T:1", "DIGITALIZACAO_ATRASADA", "CRITICO", "RI")
    ck = CK.montar(db, date.today(), papel="ADMIN")
    assert ck["achados"] == {}                       # saiu da lista...
    assert ck["medicao"]["areas"]["RI"]["abertos"] == 1
    assert ck["medicao"]["areas"]["RI"]["cor"] == CF.AMARELO   # ...e não da cor
    with db.connect() as con:
        assert CF.medir(con, date.today())["areas"]["RI"] == ck["medicao"]["areas"]["RI"]


def test_a_tela_mostra_o_quadro_fora_da_checklist(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _rodada_de_hoje(db)
    _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS", titulo="CENSEC: quinzena sem envio")
    _achado(db, "T:2", "NOTAS_PDF_30_DIAS", "CRITICO", "NOTAS",
            titulo="Procuração 12 sem o PDF assinado")
    _achado(db, "T:3", "DIGITALIZACAO_DA_FICHA", "CRITICO", "RI",
            titulo="Ficha 77 sem digitalizar")
    tarefa = _tarefa(db, "GESTOR:NOTAS_PDF_30_DIAS:PESSOA:3")
    html = c.get("/administrativo/gestor/checklist").get_data(as_text=True)
    lista = html[html.index('id="achados"'):html.index('id="fora"')]
    quadro = html[html.index('id="fora"'):html.index('id="conferencias"')]
    assert "CENSEC: quinzena sem envio" in lista
    assert "Procuração 12" not in html and "Ficha 77" not in html   # título do ato não sai
    assert "Achados abertos da TI e da administração" in html and "(1)" in lista
    assert GR.ROTULOS["NOTAS_PDF_30_DIAS"] in quadro
    assert f'href="/tarefas/{tarefa}"' in quadro
    assert GR.ROTULOS["DIGITALIZACAO_DA_FICHA"] in quadro
    assert "a tarefa nasce na próxima rodada" in quadro
    assert "contam na cor oficial" in quadro
    # filtrado pela área, o quadro também filtra
    so_ri = c.get("/administrativo/gestor/checklist?area=RI").get_data(as_text=True)
    quadro_ri = so_ri[so_ri.index('id="fora"'):so_ri.index('id="conferencias"')]
    assert GR.ROTULOS["DIGITALIZACAO_DA_FICHA"] in quadro_ri
    assert GR.ROTULOS["NOTAS_PDF_30_DIAS"] not in quadro_ri
    assert "Nenhum achado aberto em Registro de Imóveis para a TI" in so_ri


def test_o_auditor_ve_o_quadro_sem_link_que_recusa(cg_casa):
    db = cg_casa["db"]
    _rodada_de_hoje(db)
    _achado(db, "T:1", "ONR_CARGA_INICIAL", "ATENCAO", "RI")
    from conftest import cg_login
    db.create_user("carla", "CARLA EXEMPLO LIMA", "Senha#12345", "AUDITOR")
    c = cg_casa["c"]
    cg_login(c, "carla", "Senha#12345")
    html = c.get("/administrativo/gestor/checklist").get_data(as_text=True)
    quadro = html[html.index('id="fora"'):html.index('id="conferencias"')]
    assert GR.ROTULOS["ONR_CARGA_INICIAL"] in quadro
    assert "agente de compliance" in quadro


def test_tarefas_do_gestor_le_so_as_abertas_do_gestor(cg_casa):
    db = cg_casa["db"]
    a = _tarefa(db, "GESTOR:SIRC:RCPN")
    _tarefa(db, "GESTOR:SIRC:NOTAS", status="CANCELADA")
    b = _tarefa(db, "GESTOR:CAIXA_DO_DIA_ABERTO:PESSOA:2")
    _tarefa(db, "TORTA")
    with db.connect() as con:
        t = GDS.tarefas_do_gestor(con)
    assert t == {"SIRC": [{"id": a, "setor": "RCPN"}],
                 "CAIXA_DO_DIA_ABERTO": [{"id": b, "setor": "PESSOA:2"}]}

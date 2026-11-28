"""A rotina do escrevente sai da Checklist do dia da gestão (A011, 27/11/2026).

Pedido do titular: os itens da rotina da serventia que são trabalho de
escrevente (os do ONR no Registro de Imóveis, o acompanhamento registral, a
conferência dos cartões de firma) aparecem na Checklist do dia da gestão; eles
devem sair dela e ficar só com quem responde por eles. Os testes provam:

  * o item tem um DESTINO no cadastro (TI_ADMIN, o padrão, ou ESCREVENTE); o do
    escrevente pede responsável, e o destino desconhecido é recusado;
  * o item do escrevente não entra no bloco «Rotina do dia» da checklist (em
    nenhuma área, e o filtro `?area=` continua valendo), e está em «Minha
    rotina» do responsável e do suplente;
  * o item da TI e o da administração continuam na checklist;
  * o item do escrevente que ficou sem ninguém ativo volta à checklist;
  * a VOLTA À GESTÃO do muito atrasado é desligada por padrão; ligada com N
    dias úteis, o item volta marcado, contando o calendário da casa;
  * a tela do cadastro mostra e edita o destino, e a carga em lote o aceita;
  * a coluna chega por ALTER sobre o banco antigo, e o item que já existia
    fica na gestão.

Datas fixas em novembro de 2026: sexta 20/11 (Consciência Negra) é feriado.
Os nomes e os códigos são de exemplo.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_checklist as CK                 # noqa: E402
import rotina_da_casa as RT                   # noqa: E402
from bd_nativo import banco                   # noqa: E402
from conftest import cg_login                 # noqa: E402

SENHA = "Senha#12345"
CHECKLIST = "/administrativo/gestor/checklist"
CADASTRO = "/administrativo/rotina"
ANTES = datetime(2026, 11, 1, 9, 0)
#: Há tempo: aparece em qualquer dia em que o teste rode (hoje ou atrasado).
HA_TEMPO = datetime(2026, 1, 5, 9, 0)


def _item(codigo, **mais) -> dict:
    base = {"codigo": codigo, "area": "TI", "titulo": f"Rotina de exemplo {codigo}",
            "como_fazer": "Abra a tela indicada.\nConfira a linha do dia.",
            "periodicidade": "DIARIA"}
    base.update(mais)
    return base


def _pessoa(db, login, papel="USER") -> int:
    return db.create_user(login, f"{login.upper()} EXEMPLO", SENHA, papel)


def _criar(db, codigo, agora=ANTES, **mais) -> int:
    with db.transaction() as con:
        return RT.criar(con, _item(codigo, **mais), por="Fulano", agora=agora)


def _gestao_e_escrevente(db, hoje, volta_apos=None, **filtros):
    with db.connect() as con:
        itens = RT.do_dia(con, date.fromisoformat(hoje), **filtros)
    gestao, escrevente = RT.na_checklist_da_gestao(itens, volta_apos=volta_apos)
    return {x["codigo"]: x for x in gestao}, {x["codigo"]: x for x in escrevente}


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _bloco_da_rotina(html: str) -> str:
    return html[html.index('id="rotina"'):html.index('id="achados"')]


def _auditoria(db, acao) -> list[dict]:
    with db.connect() as con:
        return [json.loads(r["details"]) for r in banco(con).ler(
            "SELECT details FROM audit_logs WHERE action = %s ORDER BY id", (acao,))]


# ------------------------------------------------------------ o cadastro


def test_o_destino_vem_da_gestao_e_o_do_escrevente_pede_responsavel(cg_casa):
    db = cg_casa["db"]
    escrevente = _pessoa(db, "escrevente1")
    with db.transaction() as con:
        rid = RT.criar(con, _item("ROT-TI-01"), por="Fulano", agora=ANTES)
        assert RT.uma(con, rid)["destino"] == RT.TI_ADMIN          # o padrão: a gestão
        with pytest.raises(RT.RotinaError, match="escolha o responsável"):
            RT.criar(con, _item("ROT-RI-01", area="RI", destino="ESCREVENTE"), por="Fulano")
        with pytest.raises(RT.RotinaError, match="onde a rotina aparece"):
            RT.criar(con, _item("ROT-RI-02", area="RI", destino="BALCAO"), por="Fulano")
        rid = RT.criar(con, _item("ROT-RI-01", area="RI", destino="escrevente",
                                  responsavel_id=escrevente), por="Fulano")
        assert RT.uma(con, rid)["destino"] == RT.ESCREVENTE
        # tirar o responsável do item do escrevente é recusado; trocar o destino, não
        with pytest.raises(RT.RotinaError, match="escolha o responsável"):
            RT.atualizar(con, rid, {"responsavel_id": None}, por="Fulano")
        assert RT.atualizar(con, rid, {"destino": "TI_ADMIN"}, por="Fulano") == ["destino"]


def test_a_carga_em_lote_aceita_o_destino_e_nao_o_apaga_quando_nao_vem(cg_casa):
    db = cg_casa["db"]
    _pessoa(db, "escrevente1")
    lote = [_item("ROT-NOT-04", area="NOTAS", destino="ESCREVENTE", responsavel="escrevente1")]
    with db.transaction() as con:
        r = RT.importar(con, lote, por="agente 11", agora=ANTES)
        assert [c for c, _ in r["criados"]] == ["ROT-NOT-04"]
        sem_destino = [{k: v for k, v in lote[0].items() if k != "destino"}]
        r = RT.importar(con, sem_destino, por="agente 11", agora=ANTES)
        assert [c for c, _ in r["iguais"]] == ["ROT-NOT-04"]
        [(_, rid)] = r["iguais"]
        assert RT.uma(con, rid)["destino"] == RT.ESCREVENTE
        with pytest.raises(RT.RotinaError, match="onde a rotina aparece"):
            RT.importar(con, [{**lote[0], "destino": "OUTRO"}], por="agente 11", agora=ANTES)


# ------------------------------------------------------------ quem vê o quê


def test_o_item_do_escrevente_sai_da_checklist_e_o_da_gestao_fica(cg_casa):
    db = cg_casa["db"]
    escrevente, suplente = _pessoa(db, "escrevente1"), _pessoa(db, "suplente1")
    administrador = _pessoa(db, "administrador1", "ADMIN")
    for codigo, area in (("ROT-RI-01", "RI"), ("ROT-RI-02", "RI"), ("ROT-RI-04", "RI"),
                         ("ROT-RI-05", "RI"), ("ROT-NOT-04", "NOTAS")):
        _criar(db, codigo, area=area, destino="ESCREVENTE", responsavel_id=escrevente,
               suplente_id=suplente)
    _criar(db, "ROT-TI-01", area="TI")
    _criar(db, "ROT-FIN-01", area="FINANCEIRO", responsavel_id=administrador)
    _criar(db, "ROT-RI-03", area="RI", responsavel_id=escrevente)   # da gestão, de quem for
    gestao, fora = _gestao_e_escrevente(db, "2026-11-12")
    assert set(gestao) == {"ROT-TI-01", "ROT-FIN-01", "ROT-RI-03"}
    assert set(fora) == {"ROT-RI-01", "ROT-RI-02", "ROT-RI-04", "ROT-RI-05", "ROT-NOT-04"}
    assert all(x["volta_a_gestao"] is None for x in gestao.values())
    # a área filtra antes, como sempre
    gestao, fora = _gestao_e_escrevente(db, "2026-11-12", area="RI")
    assert set(gestao) == {"ROT-RI-03"} and set(fora) == {"ROT-RI-01", "ROT-RI-02",
                                                         "ROT-RI-04", "ROT-RI-05"}
    # «Minha rotina» do responsável e do suplente traz todos os do escrevente
    for pessoa in (escrevente, suplente):
        with db.connect() as con:
            todos = {x["codigo"] for x in RT.do_dia(con, date(2026, 11, 12), usuario_id=pessoa)}
        assert {"ROT-RI-01", "ROT-RI-02", "ROT-RI-04", "ROT-RI-05", "ROT-NOT-04"} <= todos


def test_o_item_do_escrevente_sem_ninguem_ativo_volta_a_checklist(cg_casa):
    db = cg_casa["db"]
    escrevente, suplente = _pessoa(db, "escrevente1"), _pessoa(db, "suplente1")
    _criar(db, "ROT-RI-01", area="RI", destino="ESCREVENTE", responsavel_id=escrevente,
           suplente_id=suplente)
    _criar(db, "ROT-RI-02", area="RI", destino="ESCREVENTE", responsavel_id=escrevente)
    with db.transaction() as con:
        banco(con).escrever("UPDATE users SET active = 0 WHERE id = %s", (escrevente,))
    gestao, fora = _gestao_e_escrevente(db, "2026-11-12")
    assert set(fora) == {"ROT-RI-01"}                       # o suplente está ativo
    assert set(gestao) == {"ROT-RI-02"}
    assert gestao["ROT-RI-02"]["volta_a_gestao"] == RT.VOLTOU_SEM_NINGUEM


# ------------------------------------------------------------ a volta à gestão


def test_dias_uteis_depois_conta_o_calendario_da_casa():
    feriados = {date(2026, 11, 20)}
    assert RT.dias_uteis_depois(date(2026, 11, 10), date(2026, 11, 10), feriados) == 0
    assert RT.dias_uteis_depois(date(2026, 11, 10), date(2026, 11, 12), feriados) == 2
    assert RT.dias_uteis_depois(date(2026, 11, 13), date(2026, 11, 15), feriados) == 0  # sábado e domingo
    assert RT.dias_uteis_depois(date(2026, 11, 19), date(2026, 11, 23), feriados) == 1  # 20 é feriado
    assert RT.dias_uteis_depois(date(2026, 11, 12), date(2026, 11, 10), feriados) == 0


def test_a_volta_a_gestao_e_desligada_e_ligada_conta_dias_uteis(cg_casa, monkeypatch):
    db = cg_casa["db"]
    escrevente = _pessoa(db, "escrevente1")
    # mensal do dia 19: o prazo é quinta, 19/11; sexta 20 é feriado
    _criar(db, "ROT-RI-05", area="RI", destino="ESCREVENTE", responsavel_id=escrevente,
           periodicidade="MENSAL", dias_mes="19")
    assert RT.VOLTA_A_GESTAO_DIAS_UTEIS is None                     # desligada no código
    gestao, fora = _gestao_e_escrevente(db, "2026-11-26")
    assert not gestao and fora["ROT-RI-05"]["dias_uteis_de_atraso"] == 4   # 23, 24, 25 e 26
    # ligada com 2: na segunda 23/11 é o 1º dia útil de atraso; na terça, o 2º
    gestao, fora = _gestao_e_escrevente(db, "2026-11-19", volta_apos=2)
    assert not gestao and fora["ROT-RI-05"]["dias_uteis_de_atraso"] == 0
    gestao, fora = _gestao_e_escrevente(db, "2026-11-23", volta_apos=2)
    assert not gestao and fora["ROT-RI-05"]["dias_uteis_de_atraso"] == 1
    gestao, fora = _gestao_e_escrevente(db, "2026-11-24", volta_apos=2)
    assert not fora and gestao["ROT-RI-05"]["volta_a_gestao"] == RT.VOLTOU_POR_ATRASO
    assert gestao["ROT-RI-05"]["dias_uteis_de_atraso"] == 2
    # pela checklist: o parâmetro de `montar`, o do código e o 0 que desliga
    hoje = date(2026, 11, 24)
    assert CK.montar(db, hoje, papel="ADMIN")["total_rotina"] == 0
    dados = CK.montar(db, hoje, papel="ADMIN", volta_apos=2)
    assert [x["codigo"] for x in dados["rotina_itens"]] == ["ROT-RI-05"]
    assert dados["total_rotina_do_escrevente"] == 0 and dados["rotina_volta_apos"] == 2
    monkeypatch.setattr(RT, "VOLTA_A_GESTAO_DIAS_UTEIS", 2)
    assert CK.montar(db, hoje, papel="ADMIN")["total_rotina"] == 1
    dados = CK.montar(db, hoje, papel="ADMIN", volta_apos=0)
    assert dados["total_rotina"] == 0 and dados["total_rotina_do_escrevente"] == 1
    # o «feito» tira o atraso, e o item sai de novo
    with db.transaction() as con:
        rid = int(banco(con).valor("SELECT id FROM ge_rotina WHERE codigo = 'ROT-RI-05'"))
        RT.marcar_feito(con, rid, "2026-11-19", resultado="OK", observacao="", por="Fulano",
                        usuario_id=escrevente, agora=datetime(2026, 11, 24, 10, 0))
    gestao, _ = _gestao_e_escrevente(db, "2026-11-24", volta_apos=2)
    assert not gestao


# ------------------------------------------------------------ as telas


def test_a_checklist_da_gestao_sem_o_escrevente_e_com_o_filtro_da_area(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    escrevente, suplente = _pessoa(db, "escrevente1"), _pessoa(db, "suplente1")
    with db.connect() as con:
        administrador = int(banco(con).valor("SELECT id FROM users WHERE username = 'mario'"))
    _criar(db, "ROT-RI-01", HA_TEMPO, area="RI", destino="ESCREVENTE",
           titulo="Conferir os pedidos da central (exemplo)", responsavel_id=escrevente,
           suplente_id=suplente)
    _criar(db, "ROT-NOT-04", HA_TEMPO, area="NOTAS", destino="ESCREVENTE",
           titulo="Conferir o envio dos cartões de firma (exemplo)", responsavel_id=escrevente)
    _criar(db, "ROT-TI-01", HA_TEMPO, area="TI", titulo="Conferir a cópia de segurança (exemplo)")
    _criar(db, "ROT-FIN-01", HA_TEMPO, area="FINANCEIRO", titulo="Pagar a guia do fundo (exemplo)",
           responsavel_id=administrador)
    _criar(db, "ROT-RI-03", HA_TEMPO, area="RI", titulo="Conferir a fila do indicador (exemplo)")

    html = c.get(CHECKLIST).get_data(as_text=True)
    bloco = _bloco_da_rotina(html)
    for titulo in ("Conferir a cópia de segurança", "Pagar a guia do fundo",
                   "Conferir a fila do indicador"):
        assert titulo in bloco
    assert "Conferir os pedidos da central" not in html
    assert "Conferir o envio dos cartões de firma" not in html
    assert "Fora desta lista: 2 item(ns) da rotina do escrevente" in bloco

    so_ri = _bloco_da_rotina(c.get(f"{CHECKLIST}?area=RI").get_data(as_text=True))
    assert "Conferir a fila do indicador" in so_ri and "Conferir os pedidos" not in so_ri
    assert "Conferir a cópia de segurança" not in so_ri
    assert "Fora desta lista: 1 item(ns)" in so_ri
    so_notas = _bloco_da_rotina(c.get(f"{CHECKLIST}?area=NOTAS").get_data(as_text=True))
    assert "Nada da rotina da gestão vence hoje" in so_notas
    assert "Conferir o envio dos cartões" not in so_notas and "Fora desta lista: 1" in so_notas
    so_ti = _bloco_da_rotina(c.get(f"{CHECKLIST}?area=TI").get_data(as_text=True))
    assert "Conferir a cópia de segurança" in so_ti and "Fora desta lista" not in so_ti

    # «Minha rotina»: o responsável vê os dois, o suplente o seu
    for login, devem, nao_devem in (
            ("escrevente1", ("Conferir os pedidos da central", "Conferir o envio dos cartões"), ()),
            ("suplente1", ("Conferir os pedidos da central",), ("Conferir o envio dos cartões",))):
        outro = cg_casa_logada["app"].test_client()
        cg_login(outro, login, SENHA)
        minha = outro.get("/minha-rotina").get_data(as_text=True)
        assert all(t in minha for t in devem) and not any(t in minha for t in nao_devem)
        assert "do escrevente</span>" in minha


def test_a_volta_ligada_aparece_marcada_na_checklist(cg_casa_logada, monkeypatch):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    escrevente = _pessoa(db, "escrevente1")
    # cadastrado há tempo e nunca feito: há vencimento sem registro nos últimos 30 dias
    _criar(db, "ROT-RI-02", HA_TEMPO, area="RI", destino="ESCREVENTE",
           titulo="Conferir o protocolo eletrônico (exemplo)", responsavel_id=escrevente)
    assert "Conferir o protocolo eletrônico" not in c.get(CHECKLIST).get_data(as_text=True)
    monkeypatch.setattr(RT, "VOLTA_A_GESTAO_DIAS_UTEIS", 1)
    bloco = _bloco_da_rotina(c.get(CHECKLIST).get_data(as_text=True))
    assert "Conferir o protocolo eletrônico" in bloco and "voltou à gestão" in bloco


def test_o_cadastro_mostra_e_edita_o_destino(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    escrevente = _pessoa(db, "escrevente1")
    nova = c.get(f"{CADASTRO}/nova").get_data(as_text=True)
    assert 'name="destino"' in nova and '<option value="TI_ADMIN" selected>' in nova
    form = {**_item("ROT-RI-04", area="RI"), "destino": "ESCREVENTE", "responsavel_id": "",
            "suplente_id": "", "prioridade": "2", "ordem": "100", "dias_mes": "", "dia_util": "",
            "horario": ""}
    r = c.post(f"{CADASTRO}/nova", data={**form, "csrf_token": _token(c)})
    texto = r.get_data(as_text=True)
    assert r.status_code == 200 and "escolha o responsável" in texto
    assert '<option value="ESCREVENTE" selected>' in texto        # volta com o que se escolheu
    r = c.post(f"{CADASTRO}/nova", data={**form, "responsavel_id": str(escrevente),
                                         "csrf_token": _token(c)})
    assert r.status_code == 302
    [det] = _auditoria(db, "ROTINA_CRIADA")
    assert det["codigo"] == "ROT-RI-04" and det["destino"] == "ESCREVENTE"
    with db.connect() as con:
        rid = int(banco(con).valor("SELECT id FROM ge_rotina WHERE codigo = 'ROT-RI-04'"))
    lista = c.get(CADASTRO).get_data(as_text=True)
    linha = lista[lista.index(f'id="rotina-{rid}"'):]
    assert "do escrevente</span>" in linha[:linha.index("</tr>")]
    editar = c.get(f"{CADASTRO}/{rid}/editar").get_data(as_text=True)
    assert '<option value="ESCREVENTE" selected>' in editar
    r = c.post(f"{CADASTRO}/{rid}/editar", data={**form, "destino": "TI_ADMIN",
                                                  "responsavel_id": str(escrevente),
                                                  "csrf_token": _token(c)})
    assert r.status_code == 302
    [det] = _auditoria(db, "ROTINA_ALTERADA")
    assert det["campos"] == ["destino"] and det["destino"] == "TI_ADMIN"


# ------------------------------------------------------------ o esquema


def test_a_coluna_chega_por_alter_e_o_item_antigo_fica_na_gestao(cg_casa):
    import gestor_schema as GS
    from bd_nativo import ERROS_DO_BANCO
    db = cg_casa["db"]
    rid = _criar(db, "ROT-TI-01")
    with db.transaction() as con:                   # o banco de antes do A011
        bd = banco(con)
        bd.escrever("ALTER TABLE ge_rotina DROP COLUMN destino")
        assert not bd.tem_coluna("ge_rotina", "destino")
    with db.transaction() as con:
        GS.init_rotina_schema(con)
        GS.init_rotina_schema(con)                  # de novo: nada muda, nada quebra
    with db.connect() as con:
        bd = banco(con)
        assert RT.uma(con, rid)["destino"] == RT.TI_ADMIN
        assert bd.valor("SELECT 1 FROM pg_constraint WHERE conname = 'ge_rotina_destino_ck'")
    with pytest.raises(ERROS_DO_BANCO):
        with db.transaction() as con:
            banco(con).escrever("UPDATE ge_rotina SET destino = 'BALCAO' WHERE id = %s", (rid,))

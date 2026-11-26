"""A rotina da serventia — cadastrar a rotina de manutenção e delegá-la (26/11/2026).

Pedido do oficial: «Sobre as conferências por área, serve para rotinas e demandas
do dia a dia. Não tem nenhuma demanda de rotina cadastrada lá, só débito passado.
[...] cadastre nossa rotina lá, como se fosse para eu, oficial, delegar tarefas de
manutenção do cartório para quem não faz ideia do que o cartório faz.» Os testes
provam:

  * o cadastro recusa o que não se entende (área, periodicidade, o «quando» que não
    fecha, o passo a passo vazio, a pessoa inativa) e diz tudo de uma vez;
  * cada periodicidade vence no dia certo, com o calendário da casa (feriado
    nacional e local; dia que cai no fim de semana anda para o dia útil seguinte;
    o Nº dia útil, também contado do fim);
  * o item aparece no dia em que vence, fica «atrasado» até o «feito», e o
    «feito» tem regras (observação fora do OK, o primeiro fica, quem marca);
  * o «feito» guarda a data NOMINAL (dois vencimentos nunca viram um) e, no item
    de um vencimento por período, vale pelo período (trocar o dia ou cadastrar
    feriado não o solta);
  * a rotina vale do cadastro (e da reativação): o vencido antes não se cobra;
    o que faltou depois conta («N sem registro desde») e se marca com atraso;
    «até HH:MM» atrasa depois da hora;
  * a carga em lote é idempotente pelo código, resolve o login, não mexe no
    desativado, confere a tela, não grava nada quando um item tem defeito e,
    pelo invólucro, vai à auditoria;
  * na Checklist do dia o bloco «Rotina do dia» vem antes dos achados e respeita
    `?area=`; «Minha rotina» serve o escrevente; o cadastro segue os papéis; toda
    escrita pela tela vai à auditoria.

Datas fixas em novembro de 2026: segunda 02/11 (Finados) e sexta 20/11
(Consciência Negra) são feriados nacionais.
"""
from __future__ import annotations

import io
import json
import re
import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import navegacao as NAV                       # noqa: E402
import rotina_da_casa as RT                   # noqa: E402
from bd_nativo import banco                   # noqa: E402
from conftest import cg_login                 # noqa: E402

SENHA = "Senha#12345"
CHECKLIST = "/administrativo/gestor/checklist"
CADASTRO = "/administrativo/rotina"
ANTES = datetime(2026, 10, 1, 9, 0)           # o cadastro é anterior aos vencimentos


def _d(texto: str) -> date:
    return date.fromisoformat(texto)


def _item(codigo="TI_BACKUP", **mais) -> dict:
    base = {"codigo": codigo, "area": "TI", "titulo": "Conferir a cópia de segurança da noite",
            "para_que": "Sem cópia, um defeito no disco apaga o acervo.",
            "como_fazer": "Abra Gestão › Automação.\nConfira a linha da cópia de segurança.",
            "pronto_quando": "A linha diz «em dia» com a data de hoje.",
            "se_der_errado": "Avise a TI.", "prova": "A imagem da tela.",
            "periodicidade": "DIARIA"}
    base.update(mais)
    return base


def _pessoa(db, login, papel="USER", nome=None) -> int:
    return db.create_user(login, nome or f"{login.upper()} EXEMPLO LIMA", SENHA, papel)


def _criar(db, agora=ANTES, **mais) -> int:
    with db.transaction() as con:
        return RT.criar(con, _item(**mais), por="Fulano", agora=agora)


def _do_dia(db, hoje, **filtros):
    with db.connect() as con:
        return RT.do_dia(con, _d(hoje), **filtros)


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _entrar(cg_casa, login, papel):
    _pessoa(cg_casa["db"], login, papel)
    c = cg_casa["c"]
    cg_login(c, login, SENHA)
    return c


def _auditoria(db, acao) -> list[dict]:
    with db.connect() as con:
        return [json.loads(r["details"]) for r in banco(con).ler(
            "SELECT details FROM audit_logs WHERE action = %s ORDER BY id", (acao,))]


# ------------------------------------------------------------ o cadastro


def test_o_cadastro_recusa_o_que_nao_se_entende_e_diz_tudo_de_uma_vez(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        with pytest.raises(RT.RotinaError) as erro:
            RT.criar(con, {"codigo": "com espaço", "area": "XX", "titulo": "", "como_fazer": " \n ",
                           "periodicidade": "DE VEZ EM QUANDO"}, por="Fulano")
        texto = str(erro.value)
        assert len(erro.value.problemas) == 5
        for pedaco in ("código", "área", "título", "passo a passo", "quanto em quanto tempo"):
            assert pedaco in texto
        casos = [
            ({"periodicidade": "SEMANAL"}, "dia (ou os dias) da semana"),
            ({"periodicidade": "QUINZENAL", "dias_mes": "5"}, "dois dias do mês"),
            ({"periodicidade": "MENSAL"}, "UM jeito de achar o dia"),
            ({"periodicidade": "MENSAL", "dias_mes": "10", "dia_util": 5}, "UM jeito"),
            ({"periodicidade": "TRIMESTRAL", "meses": "1,4,7", "dias_mes": "10"}, "4 meses"),
            ({"periodicidade": "TRIMESTRAL", "meses": "1,2,3,4", "dias_mes": "10"},
             "um mês em cada trimestre"),
            ({"periodicidade": "SEMESTRAL", "meses": "1,2", "dias_mes": "10"},
             "um mês em cada semestre"),
            ({"periodicidade": "ANUAL", "meses": "1"}, "UM jeito"),
            ({"periodicidade": "MENSAL", "dia_util": 0}, "Nº dia útil"),
            ({"periodicidade": "SEMANAL", "dias_semana": "1,9"}, "de 1 a 7"),
            ({"onde_url": "portal.exemplo"}, "https://"),
            ({"prioridade": 7}, "prioridade"),
        ]
        for mais, frase in casos:
            with pytest.raises(RT.RotinaError, match=re.escape(frase)):
                RT.criar(con, _item(**mais), por="Fulano")
        assert RT.contar(con) == 0
        # o campo que não é da periodicidade sai vazio
        rid = RT.criar(con, _item(periodicidade="SEMANAL", dias_semana=[3, 1, 1], dias_mes="10",
                                  meses="1"), por="Fulano")
        linha = RT.uma(con, rid)
        assert (linha["dias_semana"], linha["dias_mes"], linha["meses"]) == ("1,3", None, None)
        assert linha["criado_por"] == "Fulano" and linha["ativo"] == 1
        assert linha["vale_desde"] == date.today().isoformat()
        with pytest.raises(RT.RotinaError, match="Já existe"):
            RT.criar(con, _item(), por="Fulano")


def test_a_pessoa_da_rotina_existe_esta_ativa_e_nao_e_robo_nem_auditor(cg_casa):
    db = cg_casa["db"]
    ana = _pessoa(db, "ana")
    bia = _pessoa(db, "bia")
    carla = _pessoa(db, "carla", "AUDITOR")
    with db.transaction() as con:
        for campo in ("responsavel_id", "suplente_id"):
            with pytest.raises(RT.RotinaError, match="auditor"):
                RT.criar(con, _item(**{campo: carla}), por="Fulano")
        assert carla not in {p["id"] for p in RT.pessoas(con)}
        assert {ana, bia} <= {p["id"] for p in RT.pessoas(con)}
        banco(con).escrever("UPDATE users SET active = 0 WHERE id = %s", (bia,))
        with pytest.raises(RT.RotinaError, match="inativo"):
            RT.criar(con, _item(responsavel_id=bia), por="Fulano")
        with pytest.raises(RT.RotinaError, match="não existe"):
            RT.criar(con, _item(responsavel_id=999999), por="Fulano")
        with pytest.raises(RT.RotinaError, match="outra pessoa"):
            RT.criar(con, _item(responsavel_id=ana, suplente_id=ana), por="Fulano")
        banco(con).escrever("UPDATE users SET eh_robo = 1 WHERE id = %s", (ana,))
        with pytest.raises(RT.RotinaError, match="robô"):
            RT.criar(con, _item(responsavel_id=ana), por="Fulano")


def test_editar_nao_troca_o_codigo_e_desativar_pede_motivo(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db)
    with db.transaction() as con:
        with pytest.raises(RT.RotinaError, match="não muda"):
            RT.atualizar(con, rid, {"codigo": "OUTRO"}, por="Beltrano")
        assert RT.atualizar(con, rid, {"titulo": "Conferir a cópia de segurança da noite"},
                            por="Beltrano") == []
        assert RT.atualizar(con, rid, {"titulo": "Conferir o backup", "horario": "até 09:00"},
                            por="Beltrano") == ["titulo", "horario"]
        linha = RT.uma(con, rid)
        assert linha["atualizado_por"] == "Beltrano" and linha["para_que"].startswith("Sem cópia")
        with pytest.raises(RT.RotinaError, match="obrigatório"):
            RT.desativar(con, rid, por="Beltrano", motivo=" ")
        assert RT.desativar(con, rid, por="Beltrano", motivo="A cópia agora é da nuvem")["gravou"]
        assert not RT.desativar(con, rid, por="Beltrano", motivo="De novo")["gravou"]
        assert RT.contar(con) == 0 and RT.contar(con, ativas=False) == 1
        r = RT.reativar(con, rid, por="Beltrano", agora=datetime(2026, 11, 26, 9, 0))
        assert r["gravou"] and r["motivo_anterior"] == "A cópia agora é da nuvem"
        assert r["vale_desde"] == RT.uma(con, rid)["vale_desde"] == "2026-11-26"
        assert not RT.reativar(con, rid, por="Beltrano")["gravou"]


# ------------------------------------------------------------ quando vence


def test_cada_periodicidade_vence_no_dia_certo():
    v = RT.vencimentos
    nov = (_d("2026-11-01"), _d("2026-11-30"))
    # todo dia útil, sem Finados, sem a Consciência Negra, sem fim de semana
    diaria = v({"periodicidade": "DIARIA"}, *nov)
    assert len(diaria) == 19 and _d("2026-11-02") not in diaria and _d("2026-11-20") not in diaria
    # segunda e quarta: a segunda de Finados anda para a terça
    assert v({"periodicidade": "SEMANAL", "dias_semana": "1,3"}, *nov)[:3] == [
        _d("2026-11-03"), _d("2026-11-04"), _d("2026-11-09")]
    # 5 e 20: o 20 é feriado e cai na segunda 23; em dezembro, sábado e domingo andam
    assert v({"periodicidade": "QUINZENAL", "dias_mes": "5,20"}, _d("2026-11-01"),
             _d("2026-12-31")) == [_d("2026-11-05"), _d("2026-11-23"), _d("2026-12-07"),
                                   _d("2026-12-21")]
    # o 5º dia útil de novembro conta sem Finados; o último dia útil de fevereiro
    assert v({"periodicidade": "MENSAL", "dia_util": 5}, *nov) == [_d("2026-11-09")]
    assert v({"periodicidade": "MENSAL", "dia_util": -1}, _d("2026-02-01"),
             _d("2026-02-28")) == [_d("2026-02-27")]
    # o dia 31 em mês de 30 vale o último dia do mês
    assert v({"periodicidade": "MENSAL", "dias_mes": "31"}, _d("2026-04-01"),
             _d("2026-04-30")) == [_d("2026-04-30")]
    # trimestral no dia 10: outubro cai no sábado, e a segunda 12 é feriado
    assert v({"periodicidade": "TRIMESTRAL", "meses": "1,4,7,10", "dias_mes": "10"},
             _d("2026-01-01"), _d("2026-12-31")) == [
        _d("2026-01-12"), _d("2026-04-10"), _d("2026-07-10"), _d("2026-10-13")]
    assert v({"periodicidade": "SEMESTRAL", "meses": "6,12", "dia_util": -1},
             _d("2026-01-01"), _d("2026-12-31")) == [_d("2026-06-30"), _d("2026-12-31")]
    assert v({"periodicidade": "ANUAL", "meses": "1", "dia_util": 1}, _d("2026-01-01"),
             _d("2027-12-31")) == [_d("2026-01-02"), _d("2027-01-04")]
    # o feriado local da casa também conta
    assert v({"periodicidade": "MENSAL", "dias_mes": "10"}, *nov,
             feriados={_d("2026-11-10")}) == [_d("2026-11-11")]
    assert RT.descrever_quando({"periodicidade": "MENSAL", "dia_util": 5, "horario": "até 12:00"}) \
        == "Todo mês, no 5º dia útil, até 12:00"
    assert RT.descrever_quando({"periodicidade": "SEMANAL", "dias_semana": "1,3"}) \
        == "Toda semana: segunda e quarta"


def test_o_calendario_e_o_da_casa(cg_casa):
    db = cg_casa["db"]
    db.set_settings({"ri_feriados_locais": "2026-11-09  # aniversário da cidade (exemplo)\n"})
    _criar(db, codigo="FIN_MENSAL", area="FINANCEIRO", periodicidade="MENSAL", dia_util=5)
    [x] = _do_dia(db, "2026-11-10")
    assert x["referencia"] == "2026-11-10" and x["situacao"] == RT.HOJE


# ------------------------------------------------------------ o dia


def test_do_dia_traz_o_que_vence_e_o_atrasado_ate_o_feito(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db, codigo="FIN_GUIA", area="FINANCEIRO", periodicidade="MENSAL", dia_util=5)
    assert _do_dia(db, "2026-11-06")[0]["referencia"] == "2026-10-07"   # o de outubro, atrasado
    with db.transaction() as con:
        RT.marcar_feito(con, rid, "2026-10-07", resultado="OK", observacao="", por="Fulano",
                        usuario_id=None, agora=datetime(2026, 10, 7, 10, 0))
    assert _do_dia(db, "2026-11-06") == []                               # nada ainda
    [x] = _do_dia(db, "2026-11-09")
    assert (x["situacao"], x["referencia"]) == (RT.HOJE, "2026-11-09")
    assert x["passos"] == ["Abra Gestão › Automação.", "Confira a linha da cópia de segurança."]
    assert x["quando"] == "Todo mês, no 5º dia útil"
    [x] = _do_dia(db, "2026-11-12")
    assert (x["situacao"], x["dias_de_atraso"]) == (RT.ATRASADO, 3)
    with db.transaction() as con:
        RT.marcar_feito(con, rid, "2026-11-09", resultado="OK", observacao="", por="Beltrano",
                        usuario_id=None, agora=datetime(2026, 11, 12, 14, 5))
    [x] = _do_dia(db, "2026-11-12")
    assert x["situacao"] == RT.FEITO and x["feito"]["por"] == "Beltrano"
    assert x["feito"]["em"] == "2026-11-12T14:05" and x["feito"]["com_atraso"]
    assert _do_dia(db, "2026-11-13") == []                               # feito ontem: some


def test_a_pendencia_fica_ate_o_vencimento_seguinte_e_o_diario_avisa_o_que_faltou(cg_casa):
    db = cg_casa["db"]
    mensal = _criar(db, codigo="MALOTE", area="ADMINISTRACAO", periodicidade="MENSAL",
                    dias_mes="10")
    diario = _criar(db, codigo="TI_BACKUP", agora=datetime(2026, 11, 9, 9, 0))
    with db.transaction() as con:
        RT.marcar_feito(con, mensal, "2026-11-10", resultado="COM_PENDENCIA",
                        observacao="O malote não abriu; chamei o suporte", por="Fulano",
                        usuario_id=None, agora=datetime(2026, 11, 10, 9, 0))
        RT.marcar_feito(con, diario, "2026-11-11", resultado="OK", observacao="", por="Fulano",
                        usuario_id=None, agora=datetime(2026, 11, 11, 9, 0))
    por_codigo = {x["codigo"]: x for x in _do_dia(db, "2026-11-13")}
    assert por_codigo["MALOTE"]["situacao"] == RT.FEITO                  # a pendência continua à vista
    assert por_codigo["TI_BACKUP"]["situacao"] == RT.HOJE
    backup = por_codigo["TI_BACKUP"]
    assert (backup["faltas"], backup["sem_registro_desde"]) == (
        ["2026-11-09", "2026-11-10", "2026-11-12"], "2026-11-09")
    na_vespera = {x["codigo"]: x for x in _do_dia(db, "2026-12-09")}["MALOTE"]
    assert (na_vespera["situacao"], na_vespera["referencia"]) == (RT.FEITO, "2026-11-10")
    no_dia = {x["codigo"]: x for x in _do_dia(db, "2026-12-10")}["MALOTE"]
    assert (no_dia["situacao"], no_dia["referencia"]) == (RT.HOJE, "2026-12-10")


def test_a_rotina_vale_do_cadastro_e_o_que_venceu_antes_nao_se_cobra(cg_casa):
    """A carga de 26/11: o anual de fevereiro, o trimestral do dia 5 e o semestral de
    janeiro e julho não aparecem «a fazer» até o próximo vencimento; o cadastro diz quando."""
    db = cg_casa["db"]
    with db.transaction() as con:
        RT.importar(con, [_item("ANUAL_FEV", periodicidade="ANUAL", meses="2", dias_mes="15"),
                          _item("TRI_IBGE", periodicidade="TRIMESTRAL", meses="1,4,7,10",
                                dias_mes="5"),
                          _item("SEM_JA", periodicidade="SEMESTRAL", meses="1,7", dia_util=10),
                          _item("CENSEC", area="NOTAS", periodicidade="MENSAL", dia_util=5),
                          _item("DIARIO")], por="carga", agora=datetime(2026, 11, 26, 10, 0))
    [x] = _do_dia(db, "2026-11-26")
    assert (x["codigo"], x["situacao"], x["n_sem_registro"]) == ("DIARIO", RT.HOJE, 0)
    with db.connect() as con:
        proximo = {x["codigo"]: x["proximo"] for x in RT.listar(con, _d("2026-11-26"))}
    assert proximo == {"ANUAL_FEV": "2027-02-15", "TRI_IBGE": "2027-01-05",
                       "SEM_JA": "2027-01-15", "CENSEC": "2026-12-07", "DIARIO": "2026-11-26"}
    assert {x["codigo"] for x in _do_dia(db, "2026-12-07")} == {"CENSEC", "DIARIO"}


def test_reativar_nao_cobra_o_tempo_desativado(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db, codigo="M_REAT", periodicidade="MENSAL", dias_mes="10",
                 agora=datetime(2026, 1, 5, 9, 0))
    with db.transaction() as con:
        RT.desativar(con, rid, por="Fulano", motivo="Parada", agora=datetime(2026, 10, 1, 9, 0))
        RT.reativar(con, rid, por="Fulano", agora=datetime(2026, 11, 26, 9, 0))
    assert _do_dia(db, "2026-11-26") == []
    [x] = _do_dia(db, "2026-12-10")
    assert (x["situacao"], x["n_sem_registro"]) == (RT.HOJE, 0)
    with db.transaction() as con:
        with pytest.raises(RT.RotinaError, match="anterior a 26/11/2026"):
            RT.marcar_feito(con, rid, "2026-11-10", resultado="OK", observacao="", por="Fulano",
                            usuario_id=None, agora=datetime(2026, 11, 26, 10, 0))


def test_o_feito_guarda_a_data_nominal_e_dois_vencimentos_nao_viram_um(cg_casa):
    # segunda e sexta: a sexta 20/11 é feriado e cai na segunda 23, que também vence
    semana = {"periodicidade": "SEMANAL", "dias_semana": "1,5"}
    assert RT.ocorrencias(semana, _d("2026-11-16"), _d("2026-11-27")) == [
        (_d("2026-11-16"), _d("2026-11-16")), (_d("2026-11-20"), _d("2026-11-23")),
        (_d("2026-11-23"), _d("2026-11-23")), (_d("2026-11-27"), _d("2026-11-27"))]
    # dias 1 e 30: o 30/01/2027 é sábado e cai no 01/02, que também vence
    assert RT.ocorrencias({"periodicidade": "MENSAL", "dias_mes": "1,30"}, _d("2027-01-25"),
                          _d("2027-02-05")) == [(_d("2027-01-30"), _d("2027-02-01")),
                                                (_d("2027-02-01"), _d("2027-02-01"))]
    db = cg_casa["db"]
    rid = _criar(db, codigo="SEG_SEX", agora=datetime(2026, 11, 16, 8, 0), **semana)
    with db.transaction() as con:
        RT.marcar_feito(con, rid, "2026-11-16", resultado="OK", observacao="", por="Fulano",
                        usuario_id=None, agora=datetime(2026, 11, 16, 10, 0))
    [x] = _do_dia(db, "2026-11-23")
    assert (x["referencia"], x["prazo"], x["situacao"]) == ("2026-11-23", "2026-11-23", RT.HOJE)
    assert x["faltas"] == ["2026-11-20"]
    assert [r for r, _ in x["referencias_marcaveis"]] == ["2026-11-23", "2026-11-20"]
    with db.transaction() as con:
        sexta = RT.marcar_feito(con, rid, "2026-11-20", resultado="OK", observacao="",
                                por="Fulano", usuario_id=None, agora=datetime(2026, 11, 23, 9, 0))
        segunda = RT.marcar_feito(con, rid, "2026-11-23", resultado="OK", observacao="",
                                  por="Fulano", usuario_id=None, agora=datetime(2026, 11, 23, 9, 5))
        n = banco(con).valor("SELECT count(*) FROM ge_rotina_feitos WHERE rotina_id = %s", (rid,))
    assert sexta["gravou"] and segunda["gravou"] and n == 3
    assert (sexta["referencia"], sexta["prazo"], sexta["com_atraso"]) == (
        "2026-11-20", "2026-11-23", False)                # o prazo andou: não é atraso


def test_o_feito_do_periodo_nao_se_solta_ao_trocar_o_dia_nem_com_feriado_novo(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db, codigo="MENSAL_10", area="FINANCEIRO", periodicidade="MENSAL", dias_mes="10")
    du = _criar(db, codigo="FIN_5DU", area="FINANCEIRO", periodicidade="MENSAL", dia_util=5)
    with db.transaction() as con:
        RT.marcar_feito(con, rid, "2026-11-10", resultado="OK", observacao="", por="Fulano",
                        usuario_id=None, agora=datetime(2026, 11, 10, 9, 0))
        RT.marcar_feito(con, du, "2026-11-09", resultado="OK", observacao="", por="Fulano",
                        usuario_id=None, agora=datetime(2026, 11, 9, 9, 0))
        RT.atualizar(con, rid, {"dias_mes": "12"}, por="Fulano")
    [x] = _do_dia(db, "2026-11-12")
    assert (x["codigo"], x["referencia"], x["situacao"]) == ("MENSAL_10", "2026-11-12", RT.FEITO)
    assert x["feito"]["referencia"] == _d("2026-11-10")
    with db.transaction() as con:
        r = RT.marcar_feito(con, rid, "2026-11-12", resultado="OK", observacao="", por="Beltrano",
                            usuario_id=None, agora=datetime(2026, 11, 12, 9, 0))
        n = banco(con).valor("SELECT count(*) FROM ge_rotina_feitos WHERE rotina_id = %s", (rid,))
    assert not r["gravou"] and r["por"] == "Fulano" and n == 1
    # um feriado local novo empurra o 5º dia útil para o dia 10: o feito do mês continua
    db.set_settings({"ri_feriados_locais": "2026-11-05"})
    [x] = [y for y in _do_dia(db, "2026-11-10") if y["codigo"] == "FIN_5DU"]
    assert (x["referencia"], x["situacao"]) == ("2026-11-10", RT.FEITO)


def test_o_que_faltou_conta_e_se_marca_com_atraso(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db)                                      # diário, vale desde 01/10
    [x] = _do_dia(db, "2026-11-13")
    # os 30 dias: de 14/10 a 12/11, sem fim de semana e sem Finados
    assert (x["situacao"], x["n_sem_registro"], x["sem_registro_desde"]) == (
        RT.HOJE, 21, "2026-10-14")
    assert x["referencias_marcaveis"][:2] == [("2026-11-13", "13/11 (deste vencimento)"),
                                              ("2026-11-12", "12/11 (sem registro)")]
    agora = datetime(2026, 11, 13, 9, 0)
    with db.transaction() as con:
        r = RT.marcar_feito(con, rid, "2026-10-14", resultado="OK", observacao="", por="Fulano",
                            usuario_id=None, agora=agora)
        assert r["gravou"] and r["com_atraso"]
        with pytest.raises(RT.RotinaError, match="últimos 30 dias"):
            RT.marcar_feito(con, rid, "2026-10-13", resultado="OK", observacao="", por="Fulano",
                            usuario_id=None, agora=agora)
        RT.marcar_feito(con, rid, "2026-11-13", resultado="OK", observacao="", por="Fulano",
                        usuario_id=None, agora=agora)
    [x] = _do_dia(db, "2026-11-13")
    # o do dia está feito, e o que faltou continua à vista, para se marcar
    assert (x["situacao"], x["n_sem_registro"], x["sem_registro_desde"]) == (
        RT.FEITO, 20, "2026-10-15")
    assert x["referencias_marcaveis"][0] == ("2026-11-12", "12/11 (sem registro)")


def test_ate_hh_mm_nao_atrasa_no_dia_do_cadastro_feito_depois_da_hora(cg_casa):
    # A carga em lote entra às 14h: o «até 09:00» de hoje não nasce atrasado; o de amanhã, sim.
    db = cg_casa["db"]
    rid = _criar(db, horario="até 09:00", agora=datetime(2026, 11, 12, 14, 0))
    [x] = _do_dia(db, "2026-11-12", agora=datetime(2026, 11, 12, 15, 0))
    assert x["situacao"] == RT.HOJE and not x["passou_da_hora"]
    with db.transaction() as con:
        r = RT.marcar_feito(con, rid, "2026-11-12", resultado="OK", observacao="", por="Fulano",
                            usuario_id=None, agora=datetime(2026, 11, 12, 15, 30))
    assert not r["com_atraso"]
    [y] = _do_dia(db, "2026-11-13", agora=datetime(2026, 11, 13, 9, 1))
    assert y["situacao"] == RT.ATRASADO and y["passou_da_hora"]


def test_ate_hh_mm_atrasa_depois_da_hora(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db, horario="até 09:00", agora=datetime(2026, 11, 12, 7, 0))
    _criar(db, codigo="LIVRE", horario="às 09h, 11h, 14h e 16h", agora=datetime(2026, 11, 12, 7, 0))
    cedo = {x["codigo"]: x for x in _do_dia(db, "2026-11-12", agora=datetime(2026, 11, 12, 8, 59))}
    assert (cedo["TI_BACKUP"]["situacao"], cedo["TI_BACKUP"]["limite_hora"]) == (RT.HOJE, "09:00")
    tarde = {x["codigo"]: x for x in _do_dia(db, "2026-11-12", agora=datetime(2026, 11, 12, 9, 1))}
    assert tarde["TI_BACKUP"]["situacao"] == RT.ATRASADO and tarde["TI_BACKUP"]["passou_da_hora"]
    assert tarde["TI_BACKUP"]["dias_de_atraso"] == 0
    assert tarde["LIVRE"]["situacao"] == RT.HOJE and tarde["LIVRE"]["limite_hora"] is None
    with db.transaction() as con:
        r = RT.marcar_feito(con, rid, "2026-11-12", resultado="OK", observacao="", por="Fulano",
                            usuario_id=None, agora=datetime(2026, 11, 12, 9, 30))
    assert r["com_atraso"]
    assert RT.limite_do_horario("Até 7:30") == time(7, 30)
    assert RT.limite_do_horario("até 09:00 e 15:00") is None
    assert RT.limite_do_horario("na abertura e no fim do expediente") is None


def test_do_dia_filtra_a_area_a_pessoa_e_deixa_a_desativada_de_fora(cg_casa):
    db = cg_casa["db"]
    ana, bia = _pessoa(db, "ana"), _pessoa(db, "bia")
    _criar(db, codigo="TI_1", responsavel_id=ana)
    _criar(db, codigo="NOTAS_1", area="NOTAS", suplente_id=ana)
    _criar(db, codigo="RI_1", area="RI", responsavel_id=bia)
    fora = _criar(db, codigo="RI_2", area="RI", responsavel_id=ana)
    with db.transaction() as con:
        RT.desativar(con, fora, por="Fulano", motivo="Não se faz mais")
    assert {x["codigo"] for x in _do_dia(db, "2026-11-12")} == {"TI_1", "NOTAS_1", "RI_1"}
    assert {x["codigo"] for x in _do_dia(db, "2026-11-12", area="RI")} == {"RI_1"}
    assert {x["codigo"] for x in _do_dia(db, "2026-11-12", usuario_id=ana)} == {"TI_1", "NOTAS_1"}
    assert _do_dia(db, "2026-11-12", usuario_id=0) == []          # zero não é «todos»
    with db.connect() as con:
        assert RT.por_area(RT.do_dia(con, _d("2026-11-12"))).keys() == {"RI", "NOTAS", "TI"}
        assert list(RT.por_area(RT.do_dia(con, _d("2026-11-12")))) == ["RI", "NOTAS", "TI"]
        assert sorted(x["sou"] for x in RT.da_pessoa(con, ana, _d("2026-11-12"))) == [
            "responsável", "suplente"]


def test_marcar_feito_tem_regras(cg_casa):
    db = cg_casa["db"]
    ana, bia = _pessoa(db, "ana"), _pessoa(db, "bia")
    rid = _criar(db, codigo="FIN", area="FINANCEIRO", periodicidade="MENSAL", dias_mes="10",
                 responsavel_id=ana)
    hoje = datetime(2026, 11, 12, 9, 0)

    def marcar(con, ref="2026-11-10", resultado="OK", obs="", **mais):
        dados = {"por": "Fulano", "usuario_id": ana, "agora": hoje, **mais}
        return RT.marcar_feito(con, rid, ref, resultado=resultado, observacao=obs, **dados)

    with db.transaction() as con:
        for resultado in ("COM_PENDENCIA", "NAO_SE_APLICA"):
            with pytest.raises(RT.RotinaError, match="observação é obrigatória"):
                marcar(con, resultado=resultado, obs="ok")
        with pytest.raises(RT.RotinaError, match="resultado"):
            marcar(con, resultado="TALVEZ")
        with pytest.raises(RT.RotinaError, match="não é um vencimento que se marque"):
            marcar(con, ref="2026-11-11")
        with pytest.raises(RT.RotinaError, match="anterior a 01/10/2026"):
            marcar(con, ref="2026-09-10")
        with pytest.raises(RT.RotinaError, match="ainda não chegou"):
            marcar(con, ref="2026-12-10")
        with pytest.raises(RT.RotinaError, match="não se lê"):
            marcar(con, ref="10/11/2026")
        with pytest.raises(RT.RotinaSemPermissao):
            marcar(con, usuario_id=bia, papel="USER")
        with pytest.raises(RT.RotinaSemPermissao):
            marcar(con, papel="AUDITOR")
        r = marcar(con, papel="USER", resultado="NAO_SE_APLICA", obs="Sem guia este mês")
        assert r["gravou"] and r["resultado"] == "NAO_SE_APLICA" and r["com_atraso"]
        # o de outubro (dia 10, sábado, com a segunda 12 feriado: prazo 13/10) ficou sem registro
        outubro = marcar(con, ref="2026-10-10")
        assert outubro["gravou"] and outubro["prazo"] == "2026-10-13"
        de_novo = marcar(con, por="Beltrano", papel="MANAGER", usuario_id=bia)
        assert not de_novo["gravou"] and de_novo["por"] == "Fulano"      # o primeiro fica
        assert de_novo["resultado"] == "NAO_SE_APLICA"
        RT.desativar(con, rid, por="Fulano", motivo="Saiu da rotina")
        with pytest.raises(RT.RotinaError, match="desativada"):
            marcar(con, ref="2026-10-13")
    assert RT.pode_marcar({"responsavel_id": ana, "suplente_id": None}, "USER", ana)
    assert not RT.pode_marcar({"responsavel_id": ana, "suplente_id": None}, "AUDITOR", ana)
    assert RT.pode_marcar({"responsavel_id": None, "suplente_id": None}, "MANAGER", None)


# ------------------------------------------------------------ a carga em lote


def test_a_carga_em_lote_e_idempotente_pelo_codigo(cg_casa):
    db = cg_casa["db"]
    ana = _pessoa(db, "ana")
    bia = _pessoa(db, "bia")
    lote = [
        {**_item("TI_BACKUP"), "como_fazer": ["Abra a Automação.", "Confira a cópia."],
         "responsavel": "ana", "suplente": "BIA"},
        {**_item("FIN_GUIAS", area="FINANCEIRO", periodicidade="MENSAL", dia_util=5),
         "dias_semana": None, "responsavel": "bia"},
    ]
    with db.transaction() as con:
        r = RT.importar(con, lote, por="agente 11")
    assert [c for c, _ in r["criados"]] == ["TI_BACKUP", "FIN_GUIAS"]
    assert r["atualizados"] == [] and r["iguais"] == []
    with db.connect() as con:
        backup = RT.uma(con, dict(r["criados"])["TI_BACKUP"])
    assert (backup["responsavel_id"], backup["suplente_id"]) == (ana, bia)
    assert backup["como_fazer"] == "Abra a Automação.\nConfira a cópia."

    with db.transaction() as con:
        de_novo = RT.importar(con, lote, por="agente 11")
    assert de_novo["criados"] == [] and de_novo["atualizados"] == []
    assert sorted(c for c, _ in de_novo["iguais"]) == ["FIN_GUIAS", "TI_BACKUP"]

    # o oficial troca o suplente pela tela; a carga que não fala dele não o desfaz
    with db.transaction() as con:
        RT.atualizar(con, backup["id"], {"suplente_id": None}, por="oficial")
    mudado = [{"codigo": "TI_BACKUP", "titulo": "Conferir o backup da noite"}]
    with db.transaction() as con:
        r = RT.importar(con, mudado, por="agente 11")
    assert r["atualizados"] == [("TI_BACKUP", backup["id"])]
    assert r["campos"] == {"TI_BACKUP": ["titulo"]}
    with db.connect() as con:
        linha = RT.uma(con, backup["id"])
    assert linha["titulo"] == "Conferir o backup da noite" and linha["suplente_id"] is None
    assert linha["responsavel_id"] == ana and linha["para_que"].startswith("Sem cópia")


def test_a_carga_com_defeito_nao_grava_nada(cg_casa):
    db = cg_casa["db"]
    velho = _pessoa(db, "velho")
    with db.transaction() as con:
        banco(con).escrever("UPDATE users SET active = 0 WHERE id = %s", (velho,))
    lote = [
        _item("BOM_1"),
        {**_item("RUIM_1"), "cor": "azul"},
        {**_item("RUIM_2"), "responsavel": "ninguem_aqui"},
        {**_item("RUIM_3"), "suplente": "velho"},
        _item("BOM_1"),
        {**_item("RUIM_4"), "periodicidade": "SEMANAL"},
    ]
    with db.transaction() as con:
        with pytest.raises(RT.RotinaError) as erro:
            RT.importar(con, lote, por="agente 11")
        assert RT.contar(con) == 0
    texto = str(erro.value)
    assert "campo desconhecido: cor" in texto
    assert "«ninguem_aqui» não existe" in texto and "está inativo" in texto
    assert "se repete no lote" in texto and "RUIM_4" in texto
    with db.transaction() as con:
        assert RT.importar(con, [], por="agente 11") == {
            "criados": [], "atualizados": [], "iguais": [], "inativos": [], "campos": {}}
    _pessoa(db, "carla", "AUDITOR")
    with db.transaction() as con:
        with pytest.raises(RT.RotinaError, match="auditor"):
            RT.importar(con, [{**_item("AUD"), "responsavel": "carla"}], por="agente 11")
        with pytest.raises(RT.RotinaError, match="não existe no sistema"):
            RT.importar(con, [_item("TELA", onde_endpoint="tela_x")], por="agente 11",
                        endpoints={"automacao_lista"})
        r = RT.importar(con, [_item("TELA", onde_endpoint="automacao_lista")], por="agente 11",
                        endpoints={"automacao_lista"})
    assert [c for c, _ in r["criados"]] == ["TELA"]


def test_a_carga_nao_mexe_no_desativado_nem_o_reativa(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db, codigo="X_DESAT")
    with db.transaction() as con:
        RT.desativar(con, rid, por="Fulano", motivo="Saiu")
        r = RT.importar(con, [_item("X_DESAT", titulo="Outro título")], por="agente 11")
        linha = RT.uma(con, rid)
    assert r["inativos"] == [("X_DESAT", rid)] and not (r["iguais"] or r["atualizados"])
    assert linha["ativo"] == 0 and linha["titulo"] == "Conferir a cópia de segurança da noite"


def test_importar_e_auditar_grava_a_trilha_de_cada_item(cg_casa):
    db = cg_casa["db"]
    quem = {"por": "agente 11", "agente": "agente 11", "a_mando_de": "o oficial",
            "origem": "carga de ensaio"}
    r = RT.importar_e_auditar(db, [_item("A_1"), _item("A_2", area="RI")], **quem)
    assert [c for c, _ in r["criados"]] == ["A_1", "A_2"]
    r = RT.importar_e_auditar(db, [_item("A_1", titulo="Outro título"), _item("A_2", area="RI")],
                              endpoints={"automacao_lista"}, **quem)
    assert [c for c, _ in r["atualizados"]] == ["A_1"] and [c for c, _ in r["iguais"]] == ["A_2"]
    with db.connect() as con:
        linhas = banco(con).ler(
            "SELECT action, username_snapshot, agente, a_mando_de, entity_type, details "
            "FROM audit_logs WHERE action LIKE 'ROTINA_%%' ORDER BY id")
    assert [x["action"] for x in linhas] == ["ROTINA_CRIADA", "ROTINA_CRIADA", "ROTINA_ALTERADA"]
    assert all((x["username_snapshot"], x["agente"], x["a_mando_de"], x["entity_type"])
               == ("agente 11", "agente 11", "o oficial", "ge_rotina") for x in linhas)
    criada, _, alterada = (json.loads(x["details"]) for x in linhas)
    assert criada == {"origem": "carga de ensaio", "codigo": "A_1",
                      "titulo": "Conferir a cópia de segurança da noite", "area": "TI",
                      "periodicidade": "DIARIA"}
    assert alterada["campos"] == ["titulo"] and alterada["titulo"] == "Outro título"


# ------------------------------------------------------------ as telas


def _rodada_e_achado(db) -> None:
    hoje = date.today().isoformat()
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("INSERT INTO ge_execucoes(iniciada_em, terminada_em, hoje) VALUES (%s,%s,%s)",
                    (hoje + "T07:30:00", hoje + "T07:35:00", hoje))
        bd.escrever(
            "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, primeiro_visto_em, "
            "ultimo_visto_em) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ("T:1", "CENSEC", "VENCIDO", "NOTAS", "Remessa da quinzena",
             hoje + "T07:30:00", hoje + "T07:30:00"))


def _diario(db, codigo, area, **mais) -> int:
    """Um item diário, cadastrado há tempo: aparece em qualquer dia em que o teste
    rode — «a fazer hoje» no dia útil, «atrasado» no fim de semana ou feriado."""
    with db.transaction() as con:
        return RT.criar(con, _item(codigo, area=area, **mais), por="Fulano",
                        agora=datetime(2026, 1, 5, 9, 0))


def _recente(db, codigo, area, **mais) -> int:
    """Um item diário que passou a valer no último dia útil: sem falta para trás."""
    _, ultimo = RT.ocorrencia_atual({"periodicidade": "DIARIA"}, date.today())
    with db.transaction() as con:
        return RT.criar(con, _item(codigo, area=area, **mais), por="Fulano",
                        agora=datetime.combine(ultimo, time(7, 0)))


def _referencia(db, rotina_id) -> str:
    return next(x["referencia"] for x in _do_dia(db, date.today().isoformat())
                if x["id"] == rotina_id)


def test_a_checklist_mostra_a_rotina_antes_dos_achados_e_respeita_a_area(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    html = c.get(CHECKLIST).get_data(as_text=True)
    assert "Nenhuma rotina cadastrada ainda." in html
    assert f'href="{CADASTRO}"' in html
    _rodada_e_achado(db)
    _diario(db, "NOTAS_CENSEC", "NOTAS", titulo="Conferir a remessa à CENSEC",
              onde_endpoint="gestor_envios", base_legal="CNN, art. 1º (exemplo)")
    _diario(db, "TI_BACKUP", "TI", titulo="Conferir a cópia de segurança")
    html = c.get(CHECKLIST).get_data(as_text=True)
    assert html.index('id="rotina"') < html.index('id="achados"')
    bloco = html[html.index('id="rotina"'):html.index('id="achados"')]
    assert "Conferir a remessa à CENSEC" in bloco and "Conferir a cópia de segurança" in bloco
    assert bloco.index("Notas") < bloco.index("TI e sistema")
    assert "Como fazer" in bloco and "Para que serve:" in bloco and "Base legal:" in bloco
    assert 'href="/administrativo/gestor/envios"' in bloco
    assert "Registrar o feito</button>" in bloco
    assert "sem registro desde" in bloco and "sem registro</strong> nos últimos 30 dias" in bloco
    assert "Remessa da quinzena" in html[html.index('id="achados"'):]   # os achados continuam
    so_ri = c.get(f"{CHECKLIST}?area=RI").get_data(as_text=True)
    bloco = so_ri[so_ri.index('id="rotina"'):so_ri.index('id="achados"')]
    assert "Conferir a remessa" not in bloco and "Nada da rotina vence hoje" in bloco
    so_ti = c.get(f"{CHECKLIST}?area=TI").get_data(as_text=True)
    bloco = so_ti[so_ti.index('id="rotina"'):so_ti.index('id="achados"')]
    assert "Conferir a cópia de segurança" in bloco and "Conferir a remessa" not in bloco


def test_o_feito_pela_checklist_grava_auditoria_e_a_prova(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    rid = _recente(db, "NOTAS_CENSEC", "NOTAS")
    [x] = _do_dia(db, date.today().isoformat())
    assert x["n_sem_registro"] == 0
    dados = {"csrf_token": _token(c), "referencia": x["referencia"], "voltar": "checklist",
             "area": "NOTAS", "resultado": "COM_PENDENCIA", "observacao": ""}
    r = c.post(f"{CADASTRO}/{rid}/feito", data=dados)
    assert r.status_code == 302 and not _auditoria(db, "ROTINA_FEITA")    # sem observação
    r = c.post(f"{CADASTRO}/{rid}/feito", content_type="multipart/form-data", data={
        **dados, "csrf_token": _token(c), "observacao": "A CENSEC estava fora do ar",
        "prova_arquivo": (io.BytesIO(b"%PDF-1.4 exemplo"), "tela.pdf")})
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"{CHECKLIST}?area=NOTAS#rotina")
    [det] = _auditoria(db, "ROTINA_FEITA")
    assert det["codigo"] == "NOTAS_CENSEC" and det["resultado"] == "COM_PENDENCIA"
    assert det["referencia"] == x["referencia"] and det["com_prova"]
    [prova] = _auditoria(db, "ROTINA_PROVA_ANEXADA")
    assert prova["feito_id"] == det["feito_id"] and prova["anexo_id"]
    det["anexo_id"] = prova["anexo_id"]
    with db.connect() as con:
        anexo = banco(con).um("SELECT entity_type, entity_id, original_name FROM attachments "
                              "WHERE id = %s", (det["anexo_id"],))
    assert (anexo["entity_type"], anexo["entity_id"]) == ("GE_ROTINA_FEITO", det["feito_id"])
    html = c.get(f"{CHECKLIST}?area=NOTAS").get_data(as_text=True)
    bloco = html[html.index('id="rotina"'):html.index('id="achados"')]
    assert "feito, com pendência" in bloco and "A CENSEC estava fora do ar" in bloco
    assert "prova: tela.pdf" in bloco and "Registrar o feito</button>" not in bloco
    assert c.get(f"/arquivo/{det['anexo_id']}").status_code == 200
    # o segundo «feito» do mesmo vencimento não grava outra linha nem outra auditoria
    c.post(f"{CADASTRO}/{rid}/feito", data={**dados, "csrf_token": _token(c), "resultado": "OK"})
    assert len(_auditoria(db, "ROTINA_FEITA")) == 1
    assert c.post(f"{CADASTRO}/999999/feito", data={**dados, "csrf_token": _token(c)}).status_code == 404


def test_minha_rotina_serve_o_escrevente(cg_casa):
    db = cg_casa["db"]
    bruno = _pessoa(db, "bruno")
    outro = _pessoa(db, "outro")
    meu = _recente(db, "RCPN_SIRC", "RCPN", titulo="Conferir o envio ao SIRC", responsavel_id=bruno)
    _diario(db, "TI_BACKUP", "TI", titulo="Conferir a cópia de segurança",
              responsavel_id=outro, suplente_id=bruno)
    alheio = _diario(db, "FIN_GUIA", "FINANCEIRO", titulo="Pagar a guia do fundo",
                       responsavel_id=outro)
    c = cg_casa["c"]
    cg_login(c, "bruno", SENHA)
    html = c.get("/minha-rotina").get_data(as_text=True)
    assert "Conferir o envio ao SIRC" in html and "Conferir a cópia de segurança" in html
    assert "Pagar a guia do fundo" not in html
    assert "Toda a minha rotina (2)" in html and "suplente" in html
    dados = {"referencia": _referencia(db, meu), "voltar": "minha", "resultado": "OK",
             "observacao": ""}
    r = c.post(f"{CADASTRO}/{meu}/feito", data={**dados, "csrf_token": _token(c)})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/minha-rotina#rotina-{meu}")
    [det] = _auditoria(db, "ROTINA_FEITA")
    assert det["codigo"] == "RCPN_SIRC"
    assert c.post(f"{CADASTRO}/{alheio}/feito",
                  data={**dados, "csrf_token": _token(c)}).status_code == 403
    assert c.get(CADASTRO).status_code == 403
    assert c.get(CHECKLIST).status_code == 403
    assert c.post(f"{CADASTRO}/nova", data={**_item("X_1"), "csrf_token": _token(c)}).status_code == 403
    html = c.get("/minha-rotina").get_data(as_text=True)
    assert "feito, tudo certo" in html


def test_a_prova_abre_para_quem_responde_e_para_quem_a_registrou(cg_casa):
    db = cg_casa["db"]
    bruno, outro = _pessoa(db, "bruno"), _pessoa(db, "outro")
    rid = _recente(db, "RCPN_SIRC", "RCPN", responsavel_id=bruno)
    c = cg_casa["c"]
    cg_login(c, "bruno", SENHA)
    c.post(f"{CADASTRO}/{rid}/feito", content_type="multipart/form-data", data={
        "csrf_token": _token(c), "referencia": _referencia(db, rid), "voltar": "minha",
        "resultado": "OK", "observacao": "",
        "prova_arquivo": (io.BytesIO(b"recibo de exemplo"), "recibo.txt")})
    [det] = _auditoria(db, "ROTINA_PROVA_ANEXADA")
    assert c.get(f"/arquivo/{det['anexo_id']}").status_code == 200
    c.get("/logout")
    cg_login(c, "outro", SENHA)
    assert outro and c.get(f"/arquivo/{det['anexo_id']}").status_code == 404
    # trocado o responsável, quem registrou o feito continua vendo a sua prova
    with db.transaction() as con:
        RT.atualizar(con, rid, {"responsavel_id": outro}, por="oficial")
    assert c.get(f"/arquivo/{det['anexo_id']}").status_code == 200
    c.get("/logout")
    cg_login(c, "bruno", SENHA)
    assert c.get(f"/arquivo/{det['anexo_id']}").status_code == 200


def test_o_arquivo_que_falha_nao_deixa_o_feito_sem_trilha(cg_casa_logada, monkeypatch):
    import rotina_da_casa_web as RTW
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    rid = _recente(db, "TI_UPLOAD", "TI")

    def quebra(*_a, **_k):
        raise OSError("disco cheio (simulado)")

    monkeypatch.setattr(RTW, "save_upload", quebra)
    r = c.post(f"{CADASTRO}/{rid}/feito", content_type="multipart/form-data", data={
        "csrf_token": _token(c), "referencia": _referencia(db, rid), "voltar": "minha",
        "resultado": "OK", "observacao": "", "prova_arquivo": (io.BytesIO(b"x"), "prova.pdf")})
    assert r.status_code == 302
    [feita] = _auditoria(db, "ROTINA_FEITA")
    [falha] = _auditoria(db, "ROTINA_PROVA_FALHOU")
    assert falha["feito_id"] == feita["feito_id"] and "disco cheio" in falha["erro"]
    assert not _auditoria(db, "ROTINA_PROVA_ANEXADA")
    html = c.get("/minha-rotina").get_data(as_text=True)
    assert "o arquivo da prova não foi guardado" in html


def test_o_cadastro_pela_tela_com_papeis_e_auditoria(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    ana = _pessoa(db, "ana")
    html = c.get(CADASTRO).get_data(as_text=True)
    assert "Nenhuma rotina cadastrada" in html and "Nova rotina</a>" in html
    assert c.get(f"{CADASTRO}/nova?area=TI").status_code == 200
    form = {**_item("TI_BACKUP"), "responsavel_id": str(ana), "suplente_id": "",
            "prioridade": "1", "ordem": "10", "dias_mes": "", "dia_util": "", "horario": ""}
    # a recusa volta com o que foi digitado, e não grava
    r = c.post(f"{CADASTRO}/nova", data={**form, "periodicidade": "SEMANAL",
                                         "csrf_token": _token(c)})
    texto = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não gravou" in texto and "dia (ou os dias) da semana" in texto
    assert 'value="Conferir a cópia de segurança da noite"' in texto
    r = c.post(f"{CADASTRO}/nova", data={**form, "onde_endpoint": "tela_que_nao_existe",
                                         "csrf_token": _token(c)})
    assert "não existe no sistema" in r.get_data(as_text=True)
    assert not _auditoria(db, "ROTINA_CRIADA")

    r = c.post(f"{CADASTRO}/nova", data={**form, "onde_endpoint": "automacao_lista",
                                         "csrf_token": _token(c)})
    assert r.status_code == 302
    [det] = _auditoria(db, "ROTINA_CRIADA")
    assert det["codigo"] == "TI_BACKUP" and det["area"] == "TI"
    with db.connect() as con:
        rid = int(banco(con).valor("SELECT id FROM ge_rotina WHERE codigo = 'TI_BACKUP'"))
    html = c.get(CADASTRO).get_data(as_text=True)
    assert "Conferir a cópia de segurança da noite" in html and "TI e sistema" in html
    assert "Todo dia útil" in html and "ANA EXEMPLO LIMA" in html
    assert c.get(f"{CADASTRO}?q=backup").get_data(as_text=True).count('id="rotina-') == 1
    assert c.get(f"{CADASTRO}?q=nada-disso").get_data(as_text=True).count('id="rotina-') == 0

    editar = c.get(f"{CADASTRO}/{rid}/editar").get_data(as_text=True)
    assert "TI_BACKUP" in editar and 'name="codigo"' not in editar
    r = c.post(f"{CADASTRO}/{rid}/editar", data={**form, "titulo": "Conferir o backup",
                                                  "onde_endpoint": "automacao_lista",
                                                  "csrf_token": _token(c)})
    assert r.status_code == 302
    [det] = _auditoria(db, "ROTINA_ALTERADA")
    assert det["codigo"] == "TI_BACKUP" and det["campos"] == ["titulo"]

    r = c.post(f"{CADASTRO}/{rid}/desativar", data={"motivo": "", "csrf_token": _token(c)})
    assert r.status_code == 302 and not _auditoria(db, "ROTINA_DESATIVADA")
    c.post(f"{CADASTRO}/{rid}/desativar", data={"motivo": "Agora é automático",
                                                "csrf_token": _token(c)})
    [det] = _auditoria(db, "ROTINA_DESATIVADA")
    assert det == {"codigo": "TI_BACKUP", "motivo": "Agora é automático"}
    assert "Ver as desativadas (1)" in c.get(CADASTRO).get_data(as_text=True)
    inativas = c.get(f"{CADASTRO}?ver=inativas").get_data(as_text=True)
    assert "Agora é automático" in inativas and "Reativar</button>" in inativas
    c.post(f"{CADASTRO}/{rid}/reativar", data={"csrf_token": _token(c)})
    [det] = _auditoria(db, "ROTINA_REATIVADA")
    assert det["codigo"] == "TI_BACKUP" and det["motivo_anterior"] == "Agora é automático"
    assert det["vale_desde"] == date.today().isoformat()

    # a pessoa que saiu aparece marcada, e o servidor pede outra em vez de apagá-la
    with db.transaction() as con:
        banco(con).escrever("UPDATE users SET active = 0 WHERE id = %s", (ana,))
    editar = c.get(f"{CADASTRO}/{rid}/editar").get_data(as_text=True)
    caixa = editar[editar.index('name="responsavel_id"'):editar.index('name="suplente_id"')]
    assert f'<option value="{ana}" selected>' in caixa and "(inativo)" in caixa
    r = c.post(f"{CADASTRO}/{rid}/editar", data={**form, "titulo": "Conferir o backup",
                                                  "onde_endpoint": "automacao_lista",
                                                  "csrf_token": _token(c)})
    assert r.status_code == 200 and "está inativo; escolha outra pessoa" in r.get_data(as_text=True)
    with db.connect() as con:
        assert RT.uma(con, rid)["responsavel_id"] == ana
    assert c.post(f"{CADASTRO}/999999/desativar",
                  data={"motivo": "Qualquer", "csrf_token": _token(c)}).status_code == 404


def test_o_auditor_le_o_cadastro_e_nao_grava(cg_casa):
    db = cg_casa["db"]
    rid = _criar(db)
    c = _entrar(cg_casa, "carla", "AUDITOR")
    html = c.get(CADASTRO).get_data(as_text=True)
    assert "Conferir a cópia de segurança da noite" in html and "Como fazer" in html
    assert "Nova rotina</a>" not in html and "Desativar</button>" not in html
    assert c.get(f"{CADASTRO}/nova").status_code == 403
    assert c.get(f"{CADASTRO}/{rid}/editar").status_code == 403
    assert c.post(f"{CADASTRO}/{rid}/desativar",
                  data={"motivo": "Qualquer", "csrf_token": _token(c)}).status_code == 403
    assert c.post(f"{CADASTRO}/{rid}/feito", data={
        "csrf_token": _token(c), "referencia": "2026-11-12", "resultado": "OK"}).status_code == 403
    checklist = c.get(CHECKLIST).get_data(as_text=True)
    assert "Registrar o feito" not in checklist


def test_o_gerente_cadastra(cg_casa):
    db = cg_casa["db"]
    c = _entrar(cg_casa, "gilda", "MANAGER")
    r = c.post(f"{CADASTRO}/nova", data={**_item("ADM_MALOTE", area="ADMINISTRACAO"),
                                         "csrf_token": _token(c)})
    assert r.status_code == 302
    assert _auditoria(db, "ROTINA_CRIADA")[0]["codigo"] == "ADM_MALOTE"


# ------------------------------------------------------------ o menu


@pytest.mark.parametrize("papel", ["ADMIN", "MANAGER", "USER", "AUDITOR", "TI"])
def test_minha_rotina_em_trabalho_e_o_cadastro_em_gestao(papel):
    onde = {(e["endpoint"], e["modulo"], e["secao"]) for e in NAV.entradas(papel)
            if e["endpoint"] in ("rotina_minha", "rotina_cadastro")}
    esperado = {("rotina_minha", "TRABALHO", "Minha rotina")}
    if papel != "USER":
        esperado.add(("rotina_cadastro", "GESTAO", "Rotina da serventia"))
    assert onde == esperado
    for endpoint in ("rotina_nova", "rotina_editar"):
        modulo, secao, _ = NAV.localizar(endpoint, {}, "ADMIN", NAV._flags(True, True, ()))
        assert (modulo, secao) == ("GESTAO", "Rotina da serventia")


# ------------------------------------------------------------ o esquema


def test_o_esquema_trava_no_banco_e_sobe_de_novo_sobre_o_antigo(cg_casa):
    import gestor_schema as GS
    from bd_nativo import ERROS_DO_BANCO
    db = cg_casa["db"]
    rid = _criar(db)
    travas = {"ge_rotina_prioridade_ck", "ge_rotina_ativo_ck", "ge_rotina_feitos_com_atraso_ck",
              "ge_rotina_feitos_usuario_fk"}
    # o banco que já tinha a tabela antes da revisão: sem `vale_desde` e sem as travas
    with db.transaction() as con:
        bd = banco(con)
        for tabela, nome in (("ge_rotina", "ge_rotina_prioridade_ck"),
                             ("ge_rotina", "ge_rotina_ativo_ck"),
                             ("ge_rotina_feitos", "ge_rotina_feitos_com_atraso_ck"),
                             ("ge_rotina_feitos", "ge_rotina_feitos_usuario_fk")):
            bd.escrever(f"ALTER TABLE {tabela} DROP CONSTRAINT {nome}")
        bd.escrever("ALTER TABLE ge_rotina DROP COLUMN vale_desde")
    with db.transaction() as con:
        GS.init_rotina_schema(con)
        GS.init_rotina_schema(con)                       # de novo: nada muda, nada quebra
    with db.connect() as con:
        bd = banco(con)
        nomes = {r["conname"] for r in bd.ler(
            "SELECT conname FROM pg_constraint WHERE conrelid IN "
            "('ge_rotina'::regclass, 'ge_rotina_feitos'::regclass)")}
        assert travas <= nomes
        assert RT.uma(con, rid)["vale_desde"] == ANTES.date().isoformat()
    for comando, parametros in (
            ("UPDATE ge_rotina SET prioridade = 5 WHERE id = %s", (rid,)),
            ("UPDATE ge_rotina SET ativo = 2 WHERE id = %s", (rid,)),
            ("INSERT INTO ge_rotina_feitos (rotina_id, referencia, feito_em, feito_por, "
             "usuario_id, resultado) VALUES (%s, '2026-11-12', 'x', 'x', 999999, 'OK')", (rid,)),
            ("INSERT INTO ge_rotina_feitos (rotina_id, referencia, feito_em, feito_por, "
             "com_atraso, resultado) VALUES (%s, '2026-11-13', 'x', 'x', 3, 'OK')", (rid,))):
        with pytest.raises(ERROS_DO_BANCO):
            with db.transaction() as con:
                banco(con).escrever(comando, parametros)

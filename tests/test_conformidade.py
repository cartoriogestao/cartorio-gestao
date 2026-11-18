"""O semáforo da conformidade — uma cor por área, dos achados abertos do gestor.

Pedido do oficial em 18/11/2026 («Sim, comece», sobre o painel de
conformidade do plano do gestor de compliance). Os testes provam:

  * a área sai do setor do achado, e o caixa e o fiscal caem no Financeiro
    pela regra; setor desconhecido vai para OUTROS, sem sumir;
  * VERMELHO = prazo vencido ou crítico aberto há mais de 1 dia útil;
    AMARELO = crítico recente, prazo em até 2 dias úteis, regra que não
    mediu; ATENCAO não muda a cor; achado resolvido não conta;
  * sem rodada válida do gestor (nunca rodou, terminou com erro, ou tem mais
    de 1 dia útil), nenhuma área é verde: todas ficam SEM_MEDICAO;
  * o semáforo vai ao painel do celular sem título de achado (que traz nome),
    e a guarda do retrato o aceita;
  * o quadro aparece no painel geral para o oficial, e não para o balcão.

Datas fixas em novembro de 2026, longe de feriado nacional: terça 10/11 é
«hoje»; 09/11 está a 1 dia útil, 06/11 (sexta) a 2.

Dados inventados: «Beatriz Exemplo de Souza» no título de um achado.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conformidade as CF                     # noqa: E402
import painel_numeros as PN                   # noqa: E402
import painel_retrato as PR                   # noqa: E402
from bd_nativo import banco                   # noqa: E402
from conftest import cg_login                 # noqa: E402

HOJE = date(2026, 11, 10)
SENHA = "Senha#12345"
NOME = "BEATRIZ EXEMPLO DE SOUZA"


def _rodada(db, terminada: str | None, erro: str | None = None) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_execucoes(iniciada_em, terminada_em, hoje, erro) "
            "VALUES (%s,%s,%s,%s)",
            ((terminada or "2026-11-10T14:00:00")[:10] + "T07:30:00", terminada,
             (terminada or "2026-11-10")[:10], erro))


def _achado(db, chave, regra, gravidade, setor, visto="2026-11-10T07:30:00",
            prazo=None, resolvido=None, titulo="Achado de teste") -> None:
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, prazo, "
            "primeiro_visto_em, ultimo_visto_em, resolvido_em) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (chave, regra, gravidade, setor, titulo, prazo, visto, visto, resolvido))


def _medir(db) -> dict:
    with db.connect() as con:
        return CF.medir(con, HOJE)


# ------------------------------------------------------------ só cálculo


def test_a_area_sai_do_setor_e_o_dinheiro_vai_ao_financeiro():
    assert CF.area_do_achado("RI_QUALIFICACAO", "PRENOTACAO_VENCIDA") == "RI"
    assert CF.area_do_achado("NOTAS", "CENSEC") == "NOTAS"
    assert CF.area_do_achado("RCPJ_RTD_QUALIFICACAO", "RTDPJ") == "RTD_PJ"
    assert CF.area_do_achado("RCPN", "SIRC") == "RCPN"
    assert CF.area_do_achado("TI", "BACKUP") == "ADMINISTRACAO"
    assert CF.area_do_achado("GESTAO", "PLD_COAF") == "ADMINISTRACAO"
    # o caixa é gravado com o setor de quem contou, e mesmo assim é Financeiro
    assert CF.area_do_achado("RCPN", "CAIXA_ABERTO") == "FINANCEIRO"
    assert CF.area_do_achado("GESTAO", "FECHAMENTO_DO_MES") == "FINANCEIRO"
    assert CF.area_do_achado("FISCAL", "QUALQUER") == "FINANCEIRO"
    assert CF.area_do_achado("SETOR_NOVO", "REGRA_NOVA") == CF.OUTROS
    assert CF.area_do_achado(None, None) == CF.OUTROS


def test_a_cor_segue_o_criterio_do_plano():
    zero = dict.fromkeys(CF.CONTADORES, 0)
    assert CF.cor_da_area(zero) == CF.VERDE
    assert CF.cor_da_area({**zero, "atencao": 9, "abertos": 9}) == CF.VERDE
    assert CF.cor_da_area({**zero, "criticos": 1}) == CF.AMARELO
    assert CF.cor_da_area({**zero, "prazo_proximo": 1}) == CF.AMARELO
    assert CF.cor_da_area({**zero, "nao_mediu": 1}) == CF.AMARELO
    assert CF.cor_da_area({**zero, "outra_gravidade": 1}) == CF.AMARELO
    assert CF.cor_da_area({**zero, "criticos": 1, "criticos_antigos": 1}) == CF.VERMELHO
    assert CF.cor_da_area({**zero, "vencidos": 1}) == CF.VERMELHO


def test_toda_area_tem_rotulo_e_toda_cor_tambem():
    for codigo, _ in CF.AREAS:
        assert CF.ROTULO_DA_AREA[codigo]
    assert CF.ROTULO_DA_AREA[CF.OUTROS]
    assert set(CF.ROTULO_DA_COR) == set(CF.CORES)
    assert set(CF.AREA_DO_SETOR.values()) <= {c for c, _ in CF.AREAS}


# ------------------------------------------------------------ medido no banco


def test_cada_area_ganha_a_sua_cor(cg_casa):
    db = cg_casa["db"]
    _rodada(db, "2026-11-10T07:35:00")
    _achado(db, "T:1", "PRENOTACAO_VENCIDA", "VENCIDO", "RI_QUALIFICACAO")
    _achado(db, "T:2", "ATO_SEM_SELO", "CRITICO", "NOTAS", visto="2026-11-09T07:30:00")
    _achado(db, "T:3", "PROTESTO", "CRITICO", "PROTESTO", visto="2026-11-06T07:30:00")
    _achado(db, "T:4", "SIRC", "PRAZO", "RCPN", prazo="2026-11-12")
    _achado(db, "T:5", "RTDPJ", "PRAZO", "RCPJ_RTD", prazo="2026-11-13")
    _achado(db, "T:6", "CAIXA_PRONTO_PARA_VISTO", "ATENCAO", "GESTAO")
    _achado(db, "T:7", "BACKUP", "ATENCAO", "TI")
    _achado(db, "T:8", "CAIXA_ABERTO", "CRITICO", "RCPN")
    # resolvido não conta, por pior que tenha sido
    _achado(db, "T:9", "CENSEC", "VENCIDO", "NOTAS", resolvido="2026-11-10T07:30:00")
    m = _medir(db)
    assert m["gestor"]["medido"] is True and m["gestor"]["motivo"] is None
    cor = {a: v["cor"] for a, v in m["areas"].items()}
    assert cor["RI"] == CF.VERMELHO              # vencido
    assert cor["NOTAS"] == CF.AMARELO            # crítico de ontem (1 dia útil)
    assert cor["PROTESTO"] == CF.VERMELHO        # crítico de sexta (2 dias úteis)
    assert cor["RCPN"] == CF.AMARELO             # prazo em 2 dias úteis
    assert cor["RTD_PJ"] == CF.VERDE             # prazo em 3 dias úteis
    assert cor["FINANCEIRO"] == CF.AMARELO       # o caixa aberto, crítico de hoje
    assert cor["ADMINISTRACAO"] == CF.VERDE      # só atenção: o caixa no visto vai
    assert m["areas"]["FINANCEIRO"]["atencao"] == 1   # ao Financeiro, o backup aqui
    assert m["areas"]["ADMINISTRACAO"]["atencao"] == 1
    assert m["areas"]["NOTAS"]["abertos"] == 1
    assert CF.OUTROS not in m["areas"]
    assert m["resumo"] == {CF.VERMELHO: 2, CF.AMARELO: 3, CF.VERDE: 2, CF.SEM_MEDICAO: 0}


def test_setor_desconhecido_e_gravidade_desconhecida_aparecem(cg_casa):
    db = cg_casa["db"]
    _rodada(db, "2026-11-10T07:35:00")
    _achado(db, "T:1", "REGRA_NOVA", "ATENCAO", "SETOR_NOVO")
    _achado(db, "T:2", "BACKUP", "GRAVISSIMO", "TI")
    m = _medir(db)
    assert m["areas"][CF.OUTROS]["abertos"] == 1
    assert m["areas"]["ADMINISTRACAO"]["outra_gravidade"] == 1
    assert m["areas"]["ADMINISTRACAO"]["cor"] == CF.AMARELO


@pytest.mark.parametrize("terminada, erro, motivo", [
    (None, None, CF.SEM_RODADA),                               # nunca terminou
    ("2026-11-10T07:35:00", "conexão caiu", CF.RODADA_COM_ERRO),
    ("2026-11-06T07:35:00", None, CF.RODADA_ANTIGA),           # 2 dias úteis
])
def test_sem_rodada_valida_nenhuma_area_e_verde(cg_casa, terminada, erro, motivo):
    db = cg_casa["db"]
    if terminada:
        _rodada(db, terminada, erro)
    m = _medir(db)
    assert m["gestor"]["medido"] is False
    assert m["gestor"]["motivo"] == motivo
    assert {v["cor"] for v in m["areas"].values()} == {CF.SEM_MEDICAO}


def test_a_rodada_em_andamento_nao_apaga_a_da_manha(cg_casa):
    db = cg_casa["db"]
    _rodada(db, "2026-11-10T07:35:00")
    _rodada(db, None)          # a das 14:00, ainda rodando
    m = _medir(db)
    assert m["gestor"]["medido"] is True
    assert m["gestor"]["ultima_rodada"] == "2026-11-10T07:35"


def test_a_rodada_de_ontem_ainda_vale(cg_casa):
    db = cg_casa["db"]
    _rodada(db, "2026-11-09T07:35:00")
    assert _medir(db)["gestor"]["medido"] is True


# ------------------------------------------------------------ no celular e fora


def test_o_semaforo_vai_ao_celular_sem_o_titulo_do_achado(cg_casa):
    db = cg_casa["db"]
    _rodada(db, date.today().isoformat() + "T07:35:00")
    _achado(db, "T:1", "PRENOTACAO_VENCIDA", "VENCIDO", "RI_QUALIFICACAO",
            titulo=f"Prenotação de {NOME}")
    n = PN.montar(db)
    assert "conformidade" not in n["nao_mediu"]
    cf = n["agora"]["conformidade"]
    assert cf["areas"]["RI"]["cor"] == CF.VERMELHO
    assert NOME not in json.dumps(n, ensure_ascii=False).upper()
    PR.conferir_que_e_so_agregado(n)


def test_a_guarda_do_retrato_aceita_o_semaforo_sem_medicao(cg_casa):
    n = PN.montar(cg_casa["db"])
    assert n["agora"]["conformidade"]["gestor"]["motivo"] == CF.SEM_RODADA
    PR.conferir_que_e_so_agregado(n)


def test_semaforo_que_quebra_vira_nao_medido(cg_casa, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("tabela que não existe")

    monkeypatch.setattr(CF, "medir", quebra)
    n = PN.montar(cg_casa["db"])
    assert "conformidade" in n["nao_mediu"]
    assert n["agora"]["conformidade"] is None
    PR.conferir_que_e_so_agregado(n)


# ------------------------------------------------------------ o painel geral


def test_o_oficial_ve_o_quadro_no_painel_geral(cg_casa_logada):
    html = cg_casa_logada["c"].get("/").get_data(as_text=True)
    assert "Conformidade por área" in html
    # sem rodada do gestor no banco de teste: o quadro diz que não mediu
    assert "Sem medição" in html
    assert "Registro de Imóveis" in html


def test_o_quadro_que_quebra_nao_derruba_o_painel(cg_casa_logada, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("tabela que não existe")

    monkeypatch.setattr(CF, "medir", quebra)
    resposta = cg_casa_logada["c"].get("/")
    assert resposta.status_code == 200
    assert "não deu para medir" in resposta.get_data(as_text=True)


def test_o_balcao_nao_ve_o_quadro(cg_casa):
    db = cg_casa["db"]
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "USER")
    c = cg_casa["c"]
    cg_login(c, "carla", SENHA)
    html = c.get("/").get_data(as_text=True)
    assert "Conformidade por área" not in html

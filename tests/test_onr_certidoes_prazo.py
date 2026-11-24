# -*- coding: utf-8 -*-
"""O relógio de prazo das certidões do ONR e a agenda do CNN 325 (RI013, C1).

O QUE ESTES TESTES PROVAM
    - o expediente sai de `serventia_horario` («das 08h às 14h») e o que não
      se lê não vira horário inventado;
    - a regra por tipo: inteiro teor com matrícula, 2 h (CNN 327); situação
      jurídica, 1 dia; o resto, 5 dias (Lei 6.015, art. 19, § 10);
    - a conta em horas ÚTEIS (CN-TJMA 436): passa da noite, do fim de semana e
      do feriado; o pedido fora do expediente conta da abertura seguinte;
    - o aviso de menos de 1 hora e o vencido; o prazo parado até o pagamento,
      e o pagamento contado da última leitura sem ele;
    - a agenda de fábrica cumpre o CNN 325 e a de antes não; 15 min também
      cumpre, 90 não;
    - a agenda velha troca sozinha só onde ninguém a mexeu.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import onr_certidoes_prazo as PRAZO  # noqa: E402

EXP = PRAZO.expediente("das 08h às 14h")


def _p(**k) -> dict:
    base = {"tipo_certidao": "3", "pesquisa_por": "4", "matricula_numero": "1234",
            "status_onr": "Em aberto", "situacao": "NOVO", "data_pedido": "2026-11-24T09:00:00"}
    return base | k


def _r(pedido, agora, preparo=None, exp=EXP, **k):
    return PRAZO.relogio(pedido, preparo, agora=datetime.fromisoformat(agora), exp=exp, **k)


# ------------------------------------------------------------------ o expediente

@pytest.mark.parametrize("texto,esperado", [
    ("das 08h às 14h", (time(8), time(14))),
    ("de segunda a sexta, das 8h às 17h", (time(8), time(17))),
    ("8h30 às 13h", (time(8, 30), time(13))),
    ("08:00-14:00", (time(8), time(14))),
])
def test_o_expediente_se_le_do_texto_da_serventia(texto, esperado):
    assert PRAZO.ler_horario(texto) == esperado


@pytest.mark.parametrize("texto", ["", None, "horário comercial", "das 14h às 08h",
                                   "às 25h", "das 8h"])
def test_horario_que_nao_fecha_nao_vira_horario(texto):
    assert PRAZO.ler_horario(texto) is None
    assert not PRAZO.expediente(texto).configurado


# ------------------------------------------------------------------ a regra

@pytest.mark.parametrize("pedido,codigo", [
    (_p(), PRAZO.CNN_327),
    (_p(tipo_certidao="12"), PRAZO.CNN_327),
    (_p(tipo_certidao="Matrícula do imóvel"), PRAZO.CNN_327),
    (_p(tipo_certidao="10", pesquisa_por="11", matricula_numero=""), PRAZO.CNN_327),
    (_p(matricula_numero=""), PRAZO.LEI_19_III),        # sem o número, não é o 327
    (_p(pesquisa_por="6"), PRAZO.LEI_19_III),           # por pessoa
    (_p(tipo_certidao="21"), PRAZO.LEI_19_II),          # situação jurídica atualizada
    (_p(tipo_certidao="6"), PRAZO.LEI_19_III),          # ônus
    (_p(tipo_certidao="1", pesquisa_por="6"), PRAZO.LEI_19_III),
])
def test_cada_tipo_tem_o_prazo_que_a_norma_da(pedido, codigo):
    r = PRAZO.regra(pedido)
    assert r["codigo"] == codigo
    assert r["base"]                                    # e a base normativa vai junto


# ------------------------------------------------------------------ o relógio

def test_inteiro_teor_pedido_as_9h_vence_as_11h_e_avisa_com_menos_de_1h():
    pedido = _p()
    assert _r(pedido, "2026-11-24T09:30:00")["situacao"] == PRAZO.NO_PRAZO
    r = _r(pedido, "2026-11-24T10:05:00")
    assert r["vence_em"] == "2026-11-24T11:00"
    assert r["situacao"] == PRAZO.MENOS_DE_1H and r["restante_min"] == 55
    assert _r(pedido, "2026-11-24T11:00:00")["situacao"] == PRAZO.VENCIDO


def test_as_2_horas_passam_pela_noite_em_horas_de_expediente():
    pedido = _p(data_pedido="2026-11-24T13:30:00")
    r = _r(pedido, "2026-11-24T13:45:00")
    assert r["vence_em"] == "2026-11-25T09:30"
    assert r["restante_min"] == 15 + 90 and r["situacao"] == PRAZO.NO_PRAZO
    assert not r["fora_do_expediente"]


def test_o_pedido_fora_do_expediente_conta_da_abertura_seguinte():
    """O pedido 40 da produção (17/11, 16h16, depois do expediente das 14h)."""
    r = _r(_p(data_pedido="2026-11-17T16:16:18"), "2026-11-18T08:30:00")
    assert r["vence_em"] == "2026-11-18T10:00"
    assert r["fora_do_expediente"] and "abertura seguinte" in r["texto"]


def test_passa_pelo_fim_de_semana_e_pelo_feriado():
    # quinta 19/11 13h: 1 h na quinta; sexta 20/11 é feriado nacional; segunda 9h
    r = _r(_p(data_pedido="2026-11-19T13:00:00"), "2026-11-19T13:10:00")
    assert r["vence_em"] == "2026-11-23T09:00"
    # e o feriado local da casa conta também
    local = PRAZO.expediente("das 08h às 14h", {date(2026, 11, 23)})
    r = _r(_p(data_pedido="2026-11-19T13:00:00"), "2026-11-19T13:10:00", exp=local)
    assert r["vence_em"] == "2026-11-24T09:00"


def test_os_dias_vencem_no_fim_do_expediente_do_ultimo_dia_util():
    r = _r(_p(pesquisa_por="6"), "2026-11-24T10:00:00")              # 5 dias úteis
    assert r["vence_em"] == "2026-12-01T14:00"
    r = _r(_p(tipo_certidao="21"), "2026-11-24T10:00:00")            # 1 dia útil
    assert r["vence_em"] == "2026-11-25T14:00"


def test_sem_pagamento_o_prazo_nao_corre():
    r = _r(_p(status_onr="Informar valor dos emolumentos"), "2026-11-26T10:00:00")
    assert r["situacao"] == PRAZO.AGUARDA_PAGAMENTO and r["vence_em"] is None
    r = _r(_p(status_onr="11"), "2026-11-26T10:00:00")
    assert r["situacao"] == PRAZO.AGUARDA_PAGAMENTO


def test_pago_depois_conta_da_ultima_leitura_sem_pagamento():
    preparo = {"etapa": "A_REVISAR", "pagamento_depois_de": "2026-11-25T10:00:00"}
    r = _r(_p(data_pedido="2026-11-20T09:00:00"), "2026-11-25T10:30:00", preparo)
    assert r["inicio"] == "2026-11-25T10:00" and r["vence_em"] == "2026-11-25T12:00"
    assert "sem pagamento" in r["de_onde"]


def test_o_respondido_nao_tem_relogio():
    assert _r(_p(situacao="RESPONDIDO"), "2026-11-30T10:00:00")["situacao"] == PRAZO.ENCERRADO
    assert _r(_p(), "2026-11-30T10:00:00",
              {"etapa": "FECHADO"})["situacao"] == PRAZO.ENCERRADO


def test_a_aprovada_sem_pode_agir_avisa_que_o_envio_e_a_mao():
    preparo = {"etapa": "A_ASSINAR"}
    r = _r(_p(), "2026-11-24T10:30:00", preparo, envio_automatico=False)
    assert r["situacao"] == PRAZO.MENOS_DE_1H and "envio ao ONR é à mão" in r["texto"]
    r = _r(_p(), "2026-11-24T10:30:00", preparo, envio_automatico=True)
    assert "o robô assina e envia" in r["texto"]


def test_sem_expediente_configurado_as_horas_sao_corridas():
    sem = PRAZO.expediente("")
    r = _r(_p(data_pedido="2026-11-24T13:30:00"), "2026-11-24T14:00:00", exp=sem)
    assert r["vence_em"] == "2026-11-24T15:30" and "não está configurado" in r["texto"]


# ------------------------------------------------------------------ a agenda (CNN 325)

def test_a_agenda_de_fabrica_cumpre_o_cnn_325_e_a_antiga_nao():
    import onr_certidoes_auto as AUTO
    assert PRAZO.conferir_agenda(AUTO.AGENDA_DE_FABRICA, EXP) == []
    antiga = PRAZO.conferir_agenda(AUTO._AGENDA_ATE_RI013, EXP)
    assert any("180 min sem rodada" in x for x in antiga)


@pytest.mark.parametrize("agenda,problema", [
    ({"dias": [0, 1, 2, 3, 4], "intervalo_min": 15, "janela": ["08:00", "14:00"]}, None),
    ({"dias": [0, 1, 2, 3, 4], "intervalo_min": 90, "janela": ["08:00", "14:00"]}, "sem rodada"),
    ({"dias": [0, 1, 2, 3, 4], "intervalo_min": 60, "janela": ["08:30", "14:00"]}, "abertura"),
    ({"dias": [0, 1, 2, 3, 4], "intervalo_min": 60, "janela": ["08:00", "13:00"]}, "encerramento"),
    ({"dias": [0, 1, 2, 3], "intervalo_min": 60, "janela": ["08:00", "14:00"]}, "sex"),
    ({"dias": [0, 1, 2, 3, 4], "intervalo_min": 60}, None),       # o dia inteiro também cobre
])
def test_a_frequencia_e_configuravel_mas_a_rodada_confere_o_artigo(agenda, problema):
    achados = PRAZO.conferir_agenda(agenda, EXP)
    if problema is None:
        assert achados == []
    else:
        assert any(problema in x for x in achados), achados


def test_sem_expediente_a_agenda_nao_se_confere_e_diz_por_que():
    assert "não está configurado" in PRAZO.conferir_agenda({"intervalo_min": 60},
                                                           PRAZO.expediente(""))[0]


# ------------------------------------------------------------------ a troca da agenda de fábrica

def test_a_agenda_velha_troca_sozinha_so_onde_ninguem_mexeu():
    import automacao as AU
    import onr_certidoes_auto as AUTO
    from bd_nativo import banco
    con = conexao_de_teste()
    AU.semear(con)
    bd = banco(con)
    p = AU.por_codigo(con, AUTO.CODIGO_DO_PROCESSO)
    assert p["agenda"] == AU.normalizar_agenda(AUTO.AGENDA_DE_FABRICA)
    # a casa que está com a de antes, e a descrição de antes
    bd.escrever("UPDATE au_processos SET agenda=%s, descricao=%s WHERE codigo=%s",
                (AU._dump(AU.normalizar_agenda(AUTO._AGENDA_ATE_RI013)),
                 AUTO._DESCRICAO_ATE_RI013, AUTO.CODIGO_DO_PROCESSO))
    AU.semear(con)
    p = AU.por_codigo(con, AUTO.CODIGO_DO_PROCESSO)
    assert p["agenda"] == AU.normalizar_agenda(AUTO.AGENDA_DE_FABRICA)
    assert "CNN art. 325" in p["descricao"] and p["alterado_por"].startswith("SISTEMA")
    # o que o oficial escolheu (15 min) fica
    quinze = {"dias": [0, 1, 2, 3, 4], "intervalo_min": 15, "janela": ["08:00", "14:00"]}
    bd.escrever("UPDATE au_processos SET agenda=%s, descricao='minha' WHERE codigo=%s",
                (AU._dump(AU.normalizar_agenda(quinze)), AUTO.CODIGO_DO_PROCESSO))
    AU.semear(con)
    p = AU.por_codigo(con, AUTO.CODIGO_DO_PROCESSO)
    assert p["agenda"] == AU.normalizar_agenda(quinze) and p["descricao"] == "minha"
    # a de antes com a descrição mexida: troca a agenda, a descrição fica
    bd.escrever("UPDATE au_processos SET agenda=%s WHERE codigo=%s",
                (AU._dump(AU.normalizar_agenda(AUTO._AGENDA_ATE_RI013)), AUTO.CODIGO_DO_PROCESSO))
    AU.semear(con)
    p = AU.por_codigo(con, AUTO.CODIGO_DO_PROCESSO)
    assert p["agenda"] == AU.normalizar_agenda(AUTO.AGENDA_DE_FABRICA) and p["descricao"] == "minha"

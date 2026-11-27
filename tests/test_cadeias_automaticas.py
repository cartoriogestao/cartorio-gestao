"""As cadeias automáticas do CNIB e da CENSEC — a faixa só quando um elo para (A006).

Pedido do oficial em 26/11/2026: o CNIB «roda automaticamente no sistema, baixa
as ordens e gera as minutas de averbação. Se, por um acaso, a rotina parar,
deve criar um aviso no sistema [...] mas se estiver funcionando, não precisa
de rotina manual». E no mesmo dia: a carga da CENSEC da madrugada «também
entra na mesma lógica». Os testes provam:

  * tudo funcionando: nenhum elo, nenhuma faixa;
  * cada elo parado aparece, com desde quando e onde olhar;
  * laranja no primeiro dia, vermelha a partir do segundo;
  * a cadeia que volta a funcionar some sozinha;
  * a base atrasada com a fila andando não é rotina parada;
  * a faixa é da TI, do gestor e do administrador, e não do escrevente;
  * o `RI_CNIB` grava no estado a averbação devida sem minuta.

Datas fixas: quinta 26/11/2026, 10:30, é «agora». Dados inventados.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automacao as AU                     # noqa: E402
import cadeias_automaticas as CA           # noqa: E402
import cnib_atualizador as ATZ             # noqa: E402
from bd_nativo import banco                # noqa: E402
from conftest import cg_login              # noqa: E402

AGORA = datetime(2026, 11, 26, 10, 30)     # quinta-feira
HOJE = AGORA.date()
ONTEM = (HOJE - timedelta(days=1)).isoformat()
SENHA = "Senha#12345"

#: O horário de hoje de cada processo das duas cadeias (a agenda de fábrica).
HORARIOS = {"RI_CNIB": "07:45", "RI_CNIB_MINUTAS": "09:15",
            "ROTINA_CENSEC_ENVIO": "02:00", "CASA_CENSEC": "07:40"}


def _escrever(db, sql, args=()):
    with db.transaction() as con:
        return banco(con).escrever(sql, args)


def _ler(db, sql, args=()):
    with db.connect() as con:
        return banco(con).ler(sql, args)


def _leitura(db, pedida_em, situacao, *, lidas=0, mensagem=""):
    _escrever(db, """INSERT INTO ri_cnib_leituras (de, ate, pedida_em, terminada_em, situacao,
                         lidas, novas, mensagem, automatica)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)""",
              (pedida_em[:10], pedida_em[:10], pedida_em, pedida_em, situacao, lidas, lidas,
               mensagem))


def _ordem(db, protocolo, dia):
    _escrever(db, "INSERT INTO ri_cnib_ordens (protocolo_cnib, data_pedido, ativa, origem) "
                  "VALUES (%s, %s, 1, 'CNIB')", (protocolo, dia))


def _processo(db, codigo) -> dict:
    with db.connect() as con:
        return AU.por_codigo(con, codigo)


def _rodada(db, codigo, iniciada_em, situacao="OK", relato="Rodada de teste."):
    p = _processo(db, codigo)
    _escrever(db, """INSERT INTO au_execucoes (processo_id, iniciada_em, terminada_em, situacao,
                         relato) VALUES (%s, %s, %s, %s, %s)""",
              (p["id"], iniciada_em, iniciada_em, situacao, relato))


def _estado(db, codigo, estado: dict):
    _escrever(db, "UPDATE au_processos SET estado=%s WHERE codigo=%s",
              (json.dumps(estado), codigo))


def _aviso(db, agora=AGORA):
    return CA.aviso(db.connect, agora)


def _elos(db, agora=AGORA):
    return {(e["cadeia"], e["elo"]) for e in _aviso(db, agora)["elos"]}


@pytest.fixture
def casa(cg_casa, monkeypatch):
    """Uma casa com as duas cadeias funcionando hoje, às 10:30."""
    db = cg_casa["db"]
    cg_casa["app"].extensions["backup_checked"] = True
    cg_casa["app"].extensions["cnib_verificado"] = True      # a rotina real não sai à rede
    monkeypatch.setattr(ATZ, "esta_pronto", lambda con: {"pronto": True, "falta": []})
    with db.transaction() as con:
        AU.semear(con, AGORA - timedelta(days=30))
    _escrever(db, "UPDATE au_processos SET ativo=1 WHERE codigo IN %s" % (
        "(" + ", ".join(f"'{c}'" for c in HORARIOS) + ")"))
    _ordem(db, "TESTE-ORDEM-1", ONTEM)
    _leitura(db, f"{HOJE}T00:00:20", "OK", lidas=120)
    for codigo, hora in HORARIOS.items():
        _rodada(db, codigo, f"{HOJE}T{hora}:10")
    _estado(db, "RI_CNIB", {"conhecidos": [], "base_em": "2026-11-25T17:00:00",
                            "devidas_sem_minuta": 0, "sem_minuta_desde": None})
    return cg_casa


# ------------------------------------------------------------ tudo funcionando


def test_com_tudo_funcionando_ninguem_recebe_nada(casa):
    assert _aviso(casa["db"]) == {"quantos": 0, "elos": [], "vermelho": False}


def test_instalacao_que_nunca_usou_o_cnib_nem_a_central_nao_tem_faixa(cg_casa):
    """Sem leitura nenhuma, sem credencial e com os processos de fábrica desligados."""
    db = cg_casa["db"]
    with db.transaction() as con:
        AU.semear(con, AGORA)
    assert _aviso(db)["quantos"] == 0


# ------------------------------------------------------------ cada elo parado — CNIB


def test_a_rotina_desligada(casa):
    _escrever(casa["db"], "INSERT INTO settings (key, value) VALUES (%s, '0') "
                          "ON CONFLICT (key) DO UPDATE SET value='0'", (ATZ.CHAVE_DA_ROTINA,))
    assert _elos(casa["db"]) == {("CNIB", "ROTINA_DESLIGADA")}


def test_a_credencial_que_caiu(casa, monkeypatch):
    monkeypatch.setattr(ATZ, "esta_pronto", lambda con: {
        "pronto": False, "falta": ["A credencial do CNIB não está guardada."]})
    e, = _aviso(casa["db"])["elos"]
    assert e["elo"] == "SEM_CREDENCIAL" and "credencial" in e["detalhe"]
    assert (e["endpoint"], e["desde"]) == ("cnib_central", HOJE.isoformat())


def test_a_leitura_com_erro_diz_desde_a_primeira_da_serie(casa):
    db = casa["db"]
    _leitura(db, f"{HOJE}T08:00:00", "ERRO", mensagem="Certificado recusado pela Central.")
    assert _elos(db) == {("CNIB", "LEITURA_COM_ERRO")}
    e, = _aviso(db)["elos"]
    assert "Certificado recusado" in e["detalhe"] and e["desde"] == HOJE.isoformat()


def test_a_leitura_que_nao_roda(casa):
    db = casa["db"]
    _escrever(db, "DELETE FROM ri_cnib_leituras")
    _leitura(db, "2026-11-20T00:00:10", "OK", lidas=10)
    e, = _aviso(db)["elos"]
    assert (e["elo"], e["desde"]) == ("SEM_LEITURA", "2026-11-20")


def test_a_leitura_vazia_alem_do_tolerado(casa):
    db = casa["db"]
    _escrever(db, "DELETE FROM ri_cnib_leituras")
    _leitura(db, "2026-11-22T00:00:10", "OK", lidas=5)
    for dia in ("2026-11-23", "2026-11-24", "2026-11-25"):
        _leitura(db, f"{dia}T00:00:10", "VAZIA")
    e, = _aviso(db)["elos"]
    assert (e["elo"], e["desde"]) == ("LEITURA_VAZIA", "2026-11-23")


def test_a_base_parada_com_a_fila_desligada(casa):
    db = casa["db"]
    _escrever(db, "DELETE FROM ri_cnib_ordens")
    _ordem(db, "TESTE-VELHA-1", "2026-08-12")
    e, = _aviso(db)["elos"]
    assert (e["elo"], e["desde"]) == ("BASE_PARADA", "2026-08-12")
    assert e["vermelho"] and "12/08/2026" in e["detalhe"]


def test_a_base_atrasada_com_a_fila_andando_nao_e_rotina_parada(casa):
    db = casa["db"]
    _escrever(db, "DELETE FROM ri_cnib_ordens")
    _ordem(db, "TESTE-VELHA-2", "2026-08-12")
    _escrever(db, "INSERT INTO settings (key, value) VALUES ('cnib_leitura_da_fila', '1') "
                  "ON CONFLICT (key) DO UPDATE SET value='1'")
    _leitura(db, f"{HOJE}T00:00:30", "OK", lidas=4000,
             mensagem="Fila da serventia. Parou no teto de páginas da rodada.")
    with db.connect() as con:
        assert ATZ.fila_autorizada(con)
    assert _elos(db) == set()


def test_o_processo_do_cnib_que_deu_erro(casa):
    db = casa["db"]
    _rodada(db, "RI_CNIB_MINUTAS", f"{HOJE}T09:40:00", "ERRO", "O log não é escrito há 30 h.")
    e, = _aviso(db)["elos"]
    assert (e["cadeia"], e["elo"]) == ("CNIB", "PROCESSO_COM_ERRO")
    assert e["endpoint"] == "automacao_processo" and e["args"]["processo_id"]
    assert "30 h" in e["detalhe"]


def test_o_caso_novo_da_cnib_e_trabalho_e_nao_rotina_parada(casa):
    _rodada(casa["db"], "RI_CNIB", f"{HOJE}T09:50:00", "AVISO", "CNIB: 2 caso(s) novo(s).")
    assert _elos(casa["db"]) == set()


def test_o_processo_que_nao_rodou_na_hora(casa):
    db = casa["db"]
    p = _processo(db, "RI_CNIB")
    _escrever(db, "DELETE FROM au_execucoes WHERE processo_id=%s", (p["id"],))
    _rodada(db, "RI_CNIB", f"{ONTEM}T07:45:10")
    e, = _aviso(db)["elos"]
    assert (e["elo"], e["desde"]) == ("PROCESSO_NAO_RODOU", HOJE.isoformat())
    assert "07:45" in e["detalhe"]
    # Antes das duas horas de folga, ainda não conta.
    assert _elos(db, datetime(2026, 11, 26, 9, 0)) == set()


def test_o_processo_desligado_depois_de_rodar(casa):
    _escrever(casa["db"], "UPDATE au_processos SET ativo=0, alterado_em=%s WHERE codigo='RI_CNIB'",
              (f"{ONTEM}T18:00:00",))
    e, = _aviso(casa["db"])["elos"]
    assert (e["elo"], e["desde"], e["vermelho"]) == ("PROCESSO_DESLIGADO", ONTEM, True)


def test_a_ordem_devida_que_ficou_sem_minuta(casa):
    db = casa["db"]
    _estado(db, "RI_CNIB", {"conhecidos": [], "devidas_sem_minuta": 2,
                            "sem_minuta_desde": ONTEM})
    e, = _aviso(db)["elos"]
    assert (e["elo"], e["desde"], e["endpoint"]) == ("SEM_MINUTA", ONTEM, "ri_cnib_pendentes")
    assert e["titulo"].startswith("2 averbação")


def test_a_devida_de_hoje_espera_a_rotina_das_minutas(casa):
    """Sem «pode agir», quem prepara é a rotina das minutas: a de hoje ainda não conta."""
    _estado(casa["db"], "RI_CNIB", {"conhecidos": [], "devidas_sem_minuta": 1,
                                    "sem_minuta_desde": HOJE.isoformat()})
    assert _elos(casa["db"]) == set()


# ------------------------------------------------------------ CENSEC


def test_o_envio_da_madrugada_a_censec_que_falhou(casa):
    _rodada(casa["db"], "ROTINA_CENSEC_ENVIO", f"{HOJE}T08:00:00", "ERRO",
            "CENSEC: 1 quinzena(s) falharam no envio.")
    assert _elos(casa["db"]) == {("CENSEC", "PROCESSO_COM_ERRO")}


def test_o_envio_da_censec_desligado_nas_configuracoes_e_cadeia_parada(casa):
    _rodada(casa["db"], "ROTINA_CENSEC_ENVIO", f"{HOJE}T08:00:00", "AVISO",
            "O envio automático à CENSEC está desligado nas configurações.")
    assert _elos(casa["db"]) == {("CENSEC", "PROCESSO_COM_ERRO")}


def test_ato_impedido_na_censec_e_trabalho_de_quem_lavrou(casa):
    _rodada(casa["db"], "CASA_CENSEC", f"{HOJE}T08:00:00", "AVISO", "CENSEC: 1 ponto(s) a resolver.")
    assert _elos(casa["db"]) == set()


def test_o_envio_da_censec_que_nao_saiu_de_madrugada(casa):
    db = casa["db"]
    p = _processo(db, "ROTINA_CENSEC_ENVIO")
    _escrever(db, "DELETE FROM au_execucoes WHERE processo_id=%s", (p["id"],))
    _rodada(db, "ROTINA_CENSEC_ENVIO", f"{ONTEM}T02:00:10")
    assert _elos(db) == {("CENSEC", "PROCESSO_NAO_RODOU")}


# ------------------------------------------------------------ gravidade e volta


def test_laranja_no_primeiro_dia_e_vermelha_depois(casa):
    db = casa["db"]
    _rodada(db, "RI_CNIB_MINUTAS", f"{HOJE}T09:40:00", "ERRO")
    assert _aviso(db)["vermelho"] is False
    _escrever(db, "UPDATE au_processos SET alerta_desde=%s WHERE codigo='RI_CNIB_MINUTAS'",
              (f"{ONTEM}T09:16:00",))
    a = _aviso(db)
    assert a["vermelho"] is True and a["elos"][0]["dias"] == 1


def test_a_cadeia_que_volta_a_funcionar_some_sozinha(casa):
    db = casa["db"]
    _rodada(db, "RI_CNIB_MINUTAS", f"{HOJE}T09:40:00", "ERRO")
    _leitura(db, f"{HOJE}T08:00:00", "ERRO", mensagem="Tempo esgotado.")
    assert _aviso(db)["quantos"] == 2
    _rodada(db, "RI_CNIB_MINUTAS", f"{HOJE}T10:00:00", "OK")
    _leitura(db, f"{HOJE}T10:05:00", "OK", lidas=50)
    assert _aviso(db)["quantos"] == 0


def test_a_parte_que_quebra_nao_vira_tudo_funcionando(casa, monkeypatch):
    def quebra(con, hoje):
        raise RuntimeError("tabela sumiu")
    monkeypatch.setattr(CA, "_elos_da_leitura", quebra)
    monkeypatch.setattr(CA, "PARTES", ((CA.CNIB, "a leitura da Central do CNIB",
                                        lambda con, agora: CA._elos_da_leitura(con, agora.date()),
                                        CA._CENTRAL_DO_CNIB),) + CA.PARTES[1:])
    e, = _aviso(casa["db"])["elos"]
    assert e["elo"] == "NAO_MEDIU" and "tabela sumiu" in e["detalhe"]


# ------------------------------------------------------------ o RI_CNIB grava a devida sem minuta


def test_o_ri_cnib_grava_no_estado_a_devida_sem_minuta(casa, monkeypatch):
    import automacao_processos as PROC
    import ri_cnib

    devida = {"devida": True, "matricula_id": 1, "matricula_numero": "1",
              "ordem": {"protocolo_cnib": "TESTE-1", "documento": "", "nome": "PESSOA TESTE",
                        "minuta": None}, "criterio": "documento"}
    pronta = {"devida": True, "matricula_id": 2, "matricula_numero": "2",
              "ordem": {"protocolo_cnib": "TESTE-2", "documento": "", "nome": "PESSOA TESTE",
                        "minuta": {"id": 9, "situacao": "A_REVISAR"}}, "criterio": "documento"}
    monkeypatch.setattr(ri_cnib, "pendentes", lambda con, com_teor=False: [devida, pronta])

    class Ctx:
        db = casa["db"]
        pode_agir = False
        agora = AGORA
        hoje = HOJE
        estado = {"conhecidos": [], "base_em": "2026-11-25T17:00:00",
                  "devidas_sem_minuta": 1, "sem_minuta_desde": ONTEM}

    r = PROC.verificar_cnib(Ctx())
    assert r["estado"]["devidas_sem_minuta"] == 1
    assert r["estado"]["sem_minuta_desde"] == ONTEM          # a data da primeira vez fica
    Ctx.estado = {"conhecidos": [], "devidas_sem_minuta": 0}
    monkeypatch.setattr(ri_cnib, "pendentes", lambda con, com_teor=False: [pronta])
    r = PROC.verificar_cnib(Ctx())
    assert (r["estado"]["devidas_sem_minuta"], r["estado"]["sem_minuta_desde"]) == (0, None)


# ------------------------------------------------------------ a faixa na tela


def _entrar(casa, login, papel):
    db = casa["db"]
    db.create_user(login, f"PESSOA TESTE {papel}", SENHA, papel)
    c = casa["app"].test_client()
    cg_login(c, login, SENHA)
    return c


@pytest.mark.parametrize("papel, ve", [("ADMIN", True), ("MANAGER", True), ("TI", True),
                                       ("USER", False)])
def test_a_faixa_e_da_ti_do_gestor_e_do_admin(casa, papel, ve):
    _escrever(casa["db"], "INSERT INTO settings (key, value) VALUES (%s, '0') "
                          "ON CONFLICT (key) DO UPDATE SET value='0'", (ATZ.CHAVE_DA_ROTINA,))
    casa["app"].extensions["cadeias_automaticas_esquecer"]()
    c = _entrar(casa, f"teste_{papel.lower()}", papel)
    html = c.get("/").get_data(as_text=True)
    if not ve:
        assert "data-cadeias-aviso" not in html
        return
    assert "data-cadeias-aviso" in html
    assert 'data-elo="CNIB:ROTINA_DESLIGADA"' in html
    assert "/registro-imoveis/cnib/central" in html

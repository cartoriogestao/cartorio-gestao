"""A chave da suíte (ci/chave/controlador.py), sem sistema: o pedido e a decisão."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ci" / "chave"))

import controlador as C  # noqa: E402

# 23/11/2026 é segunda-feira.
SEG = dt.datetime(2026, 11, 23)


def em(dia: int, hora: str) -> dt.datetime:
    h, m = map(int, hora.split(":"))
    return SEG + dt.timedelta(days=dia, hours=h, minutes=m)


def pedido(**kw) -> C.Pedido:
    return C.ler_pedido(json.dumps(kw))


# --- o pedido ---------------------------------------------------------------
def test_sem_pedido_vale_o_expediente_para_a_ia():
    p = C.ler_pedido(None)
    assert p.modo == "auto" and p.agenda == C.AGENDA_PADRAO and not p.aviso


def test_pedido_que_nao_e_json_vale_o_automatico_com_aviso():
    p = C.ler_pedido("rm -rf /")
    assert p.modo == "auto" and p.aviso


def test_modo_desconhecido_nao_passa():
    assert C.ler_pedido(json.dumps({"modo": "; reboot"})).modo == "auto"


def test_janela_que_nao_confere_e_ignorada():
    p = pedido(agenda=[{"dias": [0], "inicio": "08:00", "fim": "12:00"},
                       {"dias": [9], "inicio": "08:00", "fim": "12:00"},
                       {"dias": [1], "inicio": "25:00", "fim": "12:00"},
                       {"dias": [True], "inicio": "08:00", "fim": "12:00"}])
    assert p.agenda == [{"dias": [0], "inicio": "08:00", "fim": "12:00"}]
    assert p.aviso


def test_agenda_vazia_e_suite_o_tempo_todo():
    p = pedido(agenda=[])
    assert C.posicao_desejada(p, em(0, "10:00"))[0] == "suite"
    assert C.proxima_troca(p, em(0, "10:00")) is None


# --- a posição desejada -----------------------------------------------------
def test_agenda_padrao_ia_no_expediente_suite_fora():
    p = C.ler_pedido(None)
    assert C.posicao_desejada(p, em(0, "08:00"))[0] == "ia"
    assert C.posicao_desejada(p, em(0, "17:59"))[0] == "ia"
    assert C.posicao_desejada(p, em(0, "18:00"))[0] == "suite"
    assert C.posicao_desejada(p, em(0, "07:59"))[0] == "suite"
    assert C.posicao_desejada(p, em(5, "10:00"))[0] == "suite"  # sábado


def test_janela_que_atravessa_a_meia_noite_conta_pelo_dia_do_comeco():
    p = pedido(agenda=[{"dias": [4], "inicio": "22:00", "fim": "06:00"}])  # sexta
    assert C.posicao_desejada(p, em(4, "23:00"))[0] == "ia"
    assert C.posicao_desejada(p, em(5, "05:59"))[0] == "ia"   # madrugada de sábado
    assert C.posicao_desejada(p, em(5, "06:00"))[0] == "suite"
    assert C.posicao_desejada(p, em(0, "02:00"))[0] == "suite"  # madrugada de segunda: domingo não está


def test_modo_fixo_vale_sobre_a_agenda():
    assert C.posicao_desejada(pedido(modo="suite"), em(0, "10:00"))[0] == "suite"
    assert C.posicao_desejada(pedido(modo="ia"), em(5, "10:00"))[0] == "ia"


def test_modo_com_prazo_volta_para_a_agenda_quando_vence():
    prazo = em(5, "12:00").timestamp()
    p = pedido(modo="ia", ate=prazo)
    assert C.posicao_desejada(p, em(5, "11:59")) == ("ia", "pelo app até 12:00")
    assert C.posicao_desejada(p, em(5, "12:00"))[0] == "suite"


def test_proxima_troca():
    p = C.ler_pedido(None)
    assert C.proxima_troca(p, em(0, "10:30")) == em(0, "18:00")
    assert C.proxima_troca(p, em(4, "19:00")) == em(7, "08:00")  # sexta à noite -> segunda


# --- a decisão --------------------------------------------------------------
def S(vm=True, executor=True, rodando=False) -> C.Situacao:
    return C.Situacao(vm_ligada=vm, executor_ligado=executor, suite_rodando=rodando)


def test_ia_espera_a_suite_em_andamento_terminar():
    assert C.decidir("ia", S(rodando=True)) == ([], "esperando")


def test_ia_desliga_executor_antes_da_vm():
    assert C.decidir("ia", S()) == (["desligar_executor", "desligar_vm"], "desligando")
    assert C.decidir("ia", S(executor=False)) == (["desligar_vm"], "desligando")
    assert C.decidir("ia", S(vm=False, executor=False)) == ([], "ia")


def test_suite_liga_vm_antes_do_executor():
    assert C.decidir("suite", S(vm=False, executor=False)) == (["ligar_vm", "ligar_executor"], "ligando")
    assert C.decidir("suite", S(executor=False)) == (["ligar_executor"], "ligando")
    assert C.decidir("suite", S(rodando=True)) == ([], "suite")


# --- a leitura do arquivo ---------------------------------------------------
def test_arquivo_do_pedido_nao_segue_link(tmp_path):
    pasta = tmp_path / "chave"
    pasta.mkdir(mode=0o755)
    alvo = tmp_path / "outro.json"
    alvo.write_text('{"modo": "ia"}')
    (pasta / "pedido.json").symlink_to(alvo)
    assert C.ler_arquivo_do_pedido(str(pasta / "pedido.json")) is None


def test_arquivo_do_pedido_em_pasta_aberta_e_recusado(tmp_path):
    pasta = tmp_path / "chave"
    pasta.mkdir()
    (pasta / "pedido.json").write_text('{"modo": "ia"}')
    os.chmod(pasta, 0o777)
    assert C.ler_arquivo_do_pedido(str(pasta / "pedido.json")) is None
    os.chmod(pasta, 0o755)
    assert C.ler_arquivo_do_pedido(str(pasta / "pedido.json")) == '{"modo": "ia"}'

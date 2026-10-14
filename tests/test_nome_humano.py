# -*- coding: utf-8 -*-
import nome_humano as N

def test_robo_nascimento_e_maquina():
    assert N.eh_rotulo_de_maquina("Robô Nascimento RCPN")
    assert N.eh_rotulo_de_maquina("Robo Certidão RCPN")
    assert N.eh_rotulo_de_maquina("Codex")
    assert N.eh_rotulo_de_maquina("")
    assert N.eh_rotulo_de_maquina("operador")

def test_humano_nao_e_maquina():
    assert not N.eh_rotulo_de_maquina("Robson Silva")
    assert not N.eh_rotulo_de_maquina("Beatriz Exemplo de Souza")
    assert not N.eh_rotulo_de_maquina("Mario Exemplo dos Santos")

def test_fallback_troca_robo_por_substituta():
    assert N.nome_humano_para_ato(
        "Robô Nascimento RCPN", "Beatriz Santos") == "Beatriz Santos"
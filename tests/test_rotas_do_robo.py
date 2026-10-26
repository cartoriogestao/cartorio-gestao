"""A régua FECHADA do robô — revisão de segurança dos PRs abertos, 26/10/2026.

Achado transversal 1: a guarda do robô era uma lista de VEDADAS por prefixo
(`selo_robo.ROTAS_VEDADAS_AO_ROBO`) e não cobria rota nova. Agora o robô só
entra no que está em `rotas_do_robo.ROTAS_PERMITIDAS_AO_ROBO`; o resto é 403, e
a vedada vence a permitida.

O VARREDOR é `test_toda_rota_fora_da_lista_e_403_para_o_robo`: ele percorre o
`url_map` INTEIRO, e por isso pega a rota que nascer amanhã sem ninguém
lembrar de escrever teste para ela.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


# ------------------------------------------------------------ só a régua


def test_rota_sem_nome_fica_fora():
    import selo_robo as SR
    assert SR.rota_permitida_ao_robo(None) is False
    assert SR.rota_permitida_ao_robo("") is False
    assert SR.rota_permitida_ao_robo("   ") is False


def test_rota_que_nao_esta_na_lista_fica_fora():
    import selo_robo as SR
    assert SR.rota_permitida_ao_robo("rota_que_ainda_vai_nascer") is False


def test_rota_da_lista_entra():
    import selo_robo as SR
    assert SR.rota_permitida_ao_robo("dashboard") is True
    assert SR.rota_permitida_ao_robo("notas_reconhecimento") is True


def test_vedada_vence_permitida(monkeypatch):
    """Um nome de gente posto na lista por engano continua barrado."""
    import rotas_do_robo as RR
    import selo_robo as SR
    monkeypatch.setattr(RR, "ROTAS_PERMITIDAS_AO_ROBO",
                        RR.ROTAS_PERMITIDAS_AO_ROBO | {"users", "caixa_abrir"})
    assert SR.rota_permitida_ao_robo("users") is False
    assert SR.rota_permitida_ao_robo("caixa_abrir") is False


def test_nenhuma_permitida_cai_numa_vedada():
    """A lista permitida não carrega nome que as vedadas já barram — se
    carregasse, ela mentiria sobre o que o robô alcança."""
    import rotas_do_robo as RR
    import selo_robo as SR
    em_conflito = sorted(n for n in RR.ROTAS_PERMITIDAS_AO_ROBO
                         if SR.rota_vedada_ao_robo(n))
    assert em_conflito == []


def test_a_lista_e_fechada_e_nao_um_prefixo():
    """A lista é de NOMES inteiros: um prefixo aceitaria a rota nova do mesmo
    módulo, que é exatamente o buraco que esta régua fecha."""
    import rotas_do_robo as RR
    assert isinstance(RR.ROTAS_PERMITIDAS_AO_ROBO, frozenset)
    import selo_robo as SR
    assert SR.rota_permitida_ao_robo("notas_reconhecimento_que_nao_existe") is False


# ------------------------------------------------- contra o app de verdade


def _robo_logado(cg_casa):
    from conftest import cg_login
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("robo_rcpn", "Robo Nascimento RCPN", SENHA, "USER", eh_robo=1)
    c = cg_casa["app"].test_client()
    cg_login(c, "robo_rcpn", SENHA)
    return c


def _endereco(app, regra):
    """Monta um endereço para a regra, com argumentos de mentira. O 403 vem
    antes da tela, e por isso o argumento não precisa existir no banco."""
    from flask import url_for
    with app.test_request_context():
        for valor in (1, "x"):
            try:
                return url_for(regra.endpoint,
                               **{a: valor for a in regra.arguments})
            except Exception:  # noqa: BLE001 — tenta o outro tipo
                continue
    return None


def test_a_lista_so_tem_rota_que_existe(cg_casa):
    """Nome que deixou de existir no `url_map` é carimbo que mente: a lista
    diria que o robô alcança uma tela que não há."""
    import rotas_do_robo as RR
    existentes = set(cg_casa["app"].view_functions)
    sobrando = sorted(RR.ROTAS_PERMITIDAS_AO_ROBO - existentes)
    assert sobrando == [], f"nomes na lista que o app não conhece: {sobrando}"


def test_toda_rota_fora_da_lista_e_403_para_o_robo(cg_casa):
    """O VARREDOR. Toda regra do `url_map` cujo nome não está na lista
    permitida (ou que cai numa vedada) responde 403 ao robô — GET ou POST.
    A rota nova entra aqui sozinha, no dia em que nascer."""
    import selo_robo as SR
    app = cg_casa["app"]
    c = _robo_logado(cg_casa)
    vistas = 0
    abertas: list[str] = []
    for regra in app.url_map.iter_rules():
        if regra.endpoint == "static" or SR.rota_permitida_ao_robo(regra.endpoint):
            continue
        endereco = _endereco(app, regra)
        if endereco is None:
            continue
        metodo = "get" if "GET" in (regra.methods or ()) else "post"
        resposta = getattr(c, metodo)(endereco)
        vistas += 1
        if resposta.status_code != 403:
            abertas.append(f"{regra.endpoint} {metodo.upper()} {endereco} "
                           f"-> {resposta.status_code}")
    # PISO: varredor que deixa de achar passa calado. No main de 26/10/2026
    # havia ~890 rotas e 357 permitidas: sobram mais de 400 fechadas.
    assert vistas >= 400, vistas
    assert abertas == [], "rotas fora da lista que o robô alcança:\n" + "\n".join(abertas)


def test_o_robo_continua_trabalhando_no_que_e_dele(cg_casa):
    """O balcão do robô não fecha: a visão geral e as telas das Notas que o
    teste do selo já usa (`test_selo_travado_para_robos`) abrem."""
    c = _robo_logado(cg_casa)
    for rota in ("/", "/notas/reconhecimento", "/notas/autenticacao", "/notas/cartoes"):
        assert c.get(rota).status_code != 403, rota


def test_as_vedadas_continuam_403(cg_casa):
    c = _robo_logado(cg_casa)
    for rota in ("/usuarios", "/configuracoes", "/caixa", "/atualizacoes"):
        assert c.get(rota).status_code == 403, rota


def test_a_regua_nao_alcanca_gente(cg_casa):
    """A régua é do robô: o USER de carne e osso entra em tela fora da lista."""
    from conftest import cg_login
    db = cg_casa["db"]
    db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "USER")
    c = cg_casa["app"].test_client()
    cg_login(c, "beatriz", SENHA)
    import rotas_do_robo as RR
    assert "tasks" not in RR.ROTAS_PERMITIDAS_AO_ROBO
    assert c.get("/tarefas").status_code != 403


@pytest.mark.parametrize("vedada", ["users", "settings", "backup", "caixa_abrir",
                                    "agente_console", "modelos_editor"])
def test_nome_vedado_nunca_entra(vedada):
    import selo_robo as SR
    assert SR.rota_permitida_ao_robo(vedada) is False

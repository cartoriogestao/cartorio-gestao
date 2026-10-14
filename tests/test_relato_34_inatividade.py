"""O encerramento por inatividade acima de 12 horas — relato #34.

    «colocar o encerrar por inatividade para períodos superiores a 12h.»

O QUE A MEDIÇÃO ACHOU: JÁ ESTAVA CONSTRUÍDO
    A nota do desenvolvimento dizia «não está construído», e **estava**: o
    `before_request` de `app.py` compara `last_activity` com
    `session_timeout_minutes`, sem teto nenhum — `max(10, ...)` põe piso e não
    põe limite —, e a tela de Configurações oferece «12 horas» e «24 horas»
    com rótulo, além de deixar digitar qualquer número.

    **Lista de pendência que envelhece faz planejar trabalho já feito** — a
    quinta vez neste projeto, e a terceira nesta passada.

O QUE ESTE ARQUIVO ACRESCENTA, e é o que faltava de verdade
    **Nenhum teste provava que 720 minutos FUNCIONAM.** Ver o campo na tela
    não é o mesmo que ver a sessão sobreviver a onze horas e cair na décima
    terceira — e é isso que o relato pede. O que o teste exercita é o relógio,
    e não o formulário.
"""
from __future__ import annotations

import glob
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
DOZE_HORAS = 720


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


def _envelhecer(cliente, horas: float) -> None:
    """Faz a sessão parecer parada há tantas horas — sem esperar por elas."""
    with cliente.session_transaction() as sessao:
        sessao["last_activity"] = (
            datetime.now() - timedelta(hours=horas)).isoformat(
                timespec="seconds")


def test_com_12_HORAS_a_sessao_sobrevive_a_onze(s):
    """**É o que o relato pede.** Onze horas parado, e o balcão continua
    dentro — sem isto, quem sai para o almoço volta deslogado."""
    s["db"].set_settings({"session_timeout_minutes": str(DOZE_HORAS)})
    _envelhecer(s["c"], 11)
    r = s["c"].get("/", follow_redirects=False)
    assert r.status_code != 302 or "login" not in (r.headers.get("Location") or "")


def test_e_CAI_na_decima_terceira(s):
    """Sessão longa é comodidade **com preço**, e o preço é este: ela fecha.
    Uma opção de 12h que nunca encerrasse seria pior que não ter opção."""
    s["db"].set_settings({"session_timeout_minutes": str(DOZE_HORAS)})
    _envelhecer(s["c"], 13)
    r = s["c"].get("/", follow_redirects=True)
    texto = " ".join(r.get_data(as_text=True).split())
    assert "Sessão encerrada por inatividade" in texto


def test_NAO_HA_TETO_no_tempo_configurado(s):
    """`max(10, ...)` põe piso e não põe limite — 24 horas e mais entram."""
    s["db"].set_settings({"session_timeout_minutes": "1440"})
    _envelhecer(s["c"], 23)
    r = s["c"].get("/", follow_redirects=True)
    assert "Sessão encerrada por inatividade" not in r.get_data(as_text=True)


def test_o_piso_de_dez_minutos_FICA(s):
    """Zero, ou um número absurdo para baixo, encerraria a sessão a cada
    clique — e o balcão não conseguiria trabalhar."""
    s["db"].set_settings({"session_timeout_minutes": "0"})
    _envelhecer(s["c"], 0.1)          # seis minutos
    r = s["c"].get("/", follow_redirects=True)
    assert "Sessão encerrada por inatividade" not in r.get_data(as_text=True)


def test_a_tela_OFERECE_as_doze_horas_com_rotulo(s):
    """**O campo pede MINUTOS, e quem configura pensa em horas.** Para 12 horas
    era preciso saber que são 720, e ninguém faz essa conta no meio de outra
    coisa — por isso as opções têm rótulo, sem tirar a liberdade de digitar."""
    html = " ".join(s["c"].get("/configuracoes").get_data(as_text=True).split())
    assert 'name="session_timeout_minutes"' in html
    assert 'value="720"' in html and "12 horas" in html
    # **O `max` SE PROCURA DENTRO DO <input>, e não nos 200 caracteres
    # seguintes** — ali cabe o `<datalist>` inteiro, e um `max` de outro campo
    # daria falso. A régua é a etiqueta que contém o nome.
    entrada = re.search(r'<input[^>]*name="session_timeout_minutes"[^>]*>', html)
    assert entrada, "não achei o campo"
    assert "max=" not in entrada.group(0), (
        "um `max` no campo impediria o que o relato pede")
    assert 'min="10"' in entrada.group(0), "o piso fica"


def test_a_tela_DIZ_O_PRECO_da_sessao_longa(s):
    """Comodidade sem o preço escrito faz escolher no escuro: com a sessão
    aberta, quem passar pela máquina entra como o operador."""
    html = " ".join(s["c"].get("/configuracoes").get_data(as_text=True).split())
    assert "Sessão longa é comodidade com preço" in html

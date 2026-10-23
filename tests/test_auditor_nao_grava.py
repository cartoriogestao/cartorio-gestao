"""O AUDITOR vê a tela e não grava — as onze rotas da revisão de 22/10/2026.

A REVISÃO DE SEGURANÇA DA 3.7.0 (achado A5) mediu onze rotas em que o
AUDITOR entrava pelo `@roles_required(..., "AUDITOR")` e a MESMA rota, no
POST, gravava: cadastrava cartão de autógrafo, abria protocolo, importava a
tabela de emolumentos, gerava CTP e DOI. O papel existe para CONFERIR («há
tela que o AUDITOR precisa ver e onde ele não pode praticar ato»), e a guarda
de leitura e a de escrita eram a mesma.

O CONSERTO É A GUARDA DE POST, por rota — a forma do `app.py` (M2 do LS01):
o decorador de fora continua deixando o AUDITOR ver; o de dentro,
`@roles_required(..., metodos=("POST",))`, recusa o que grava. Este teste
prova as duas metades em cada uma das onze: o GET não é 403 para o AUDITOR
(404 num id que não existe conta — a guarda não barrou), e o POST com o
token válido é 403 — sem passar pela tela, direto na rota, que é quem grava.

NOMES: `mario` é o ADMIN e `carla` a AUDITORA, como manda a regra da casa
(sem nome real da equipe no código).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"

# (endereço, dados mínimos do POST). O id 999999 não existe: no GET a rota
# responde 404 DEPOIS de passar pela guarda; no POST a guarda recusa ANTES.
ROTAS = [
    ("/rcpn/habilitacoes/999999", {"acao": "documento"}),
    ("/registro-imoveis/protocolo/999999", {"acao": "nota"}),
    ("/caixa/protocolos", {"acao": "novo", "interessado": "FULANO"}),
    ("/caixa/protocolos/999999", {"acao": "contato"}),
    ("/caixa/emolumentos", {"acao": "importar"}),
    ("/notas/cartoes", {"acao": "novo", "nome": "FULANO"}),
    ("/notas/cartoes/999999", {"acao": "selo"}),
    ("/notas/reconhecimento/999999", {"acao": "selo"}),
    ("/registro-imoveis/ctp", {"acao": "gerar"}),
    ("/registro-imoveis/doi", {"acao": "gerar"}),
    ("/registro-imoveis/importacoes", {"acao": "tipo_imovel"}),
]


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def auditora(cg_casa):
    from conftest import cg_login
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("carla", "CARLA EXEMPLO DE SOUSA", SENHA, "AUDITOR")
    c = cg_casa["cliente"]
    cg_login(c, "carla", SENHA)
    return c


@pytest.mark.parametrize("endereco,dados", ROTAS, ids=[r[0] for r in ROTAS])
def test_o_auditor_ve_a_tela_e_nao_grava(auditora, endereco, dados):
    c = auditora
    resposta_get = c.get(endereco)
    assert resposta_get.status_code != 403, (
        f"o AUDITOR deixou de VER {endereco} — a guarda de leitura mudou")
    assert resposta_get.status_code in (200, 302, 404), resposta_get.status_code
    # O token vem de uma tela qualquer que o AUDITOR abre; a sessão é a mesma.
    token = _token(c.get("/").get_data(as_text=True))
    resposta_post = c.post(endereco, data={**dados, "csrf_token": token})
    assert resposta_post.status_code == 403, (
        f"o AUDITOR GRAVOU em {endereco}: HTTP {resposta_post.status_code}")


def test_as_onze_rotas_declaram_a_guarda_de_post(cg_casa):
    """A guarda está na ROTA, e não só no teste: o decorador interno existe.

    `wrapped.papeis_exigidos` do decorador de fora traz o AUDITOR (é a
    leitura); o POST é recusado pelo de dentro. Confere-se pelo endereço, que
    é o que o navegador manda.
    """
    app = cg_casa["app"]
    regras = {r.rule: r for r in app.url_map.iter_rules()}
    for endereco, _ in ROTAS:
        regra = endereco.replace("999999", "<int:habilitacao_id>")
        candidatas = [r for r in regras.values()
                      if r.rule.replace("<int:habilitacao_id>", "X")
                      .replace("<int:protocolo_id>", "X")
                      .replace("<int:cartao_id>", "X")
                      .replace("<int:reconhecimento_id>", "X")
                      == endereco.replace("999999", "X")]
        assert candidatas, f"rota não achada: {endereco} ({regra})"
        assert "POST" in candidatas[0].methods, endereco

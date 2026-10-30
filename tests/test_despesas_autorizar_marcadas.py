"""AUTORIZAR NA LISTA, SEM ABRIR UMA POR UMA.

Pedido do oficial (30/10/2026): «uma maneira mais fácil de autorizar as despesas, sem
precisar clicar em abrir em cada uma». As travas continuam: só o ADMIN autoriza, o que
passa do teto ou tem valor divergente fica na ficha, e o valor autorizado é o da tela.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP
from tests.conftest import cg_login

AGORA = datetime(2026, 10, 30, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
SENHA = "Senha#12345"
LISTA = "/administrativo/despesas"
ROTA = "/administrativo/despesas/autorizar-marcadas"


def _token(c):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(LISTA).get_data(as_text=True)).group(1)


def _nova(db, valor=193532, nome="BEATRIZ EXEMPLO", vencimento="2026-10-30"):
    with db.transaction() as con:
        return DP.cadastrar(
            con, agora=AGORA, por="mario", origem="MANUAL", chave_origem=None,
            beneficiario_nome=nome, beneficiario_documento="", valor_centavos=valor,
            vencimento=vencimento, forma=DP.PIX_CHAVE, codigo="beatriz@example.com",
            descricao="Folha de pagamento, salário líquido", categoria="PESSOAL",
            documento_especie="Recibo de pagamento")


def _situacao(db, i):
    with db.connect() as con:
        return DP.despesa(con, i)["situacao"]


def test_a_lista_mostra_o_que_se_confere_e_ja_vem_marcada(cg_casa_logada):
    i = _nova(cg_casa_logada["db"])
    html = cg_casa_logada["c"].get(LISTA).get_data(as_text=True)
    assert "Esperando a sua autorização (1)" in html
    assert "beatriz@example.com" in html and "1.935,32" in html
    assert f'value="{i}:193532" checked' in html


def test_autoriza_as_marcadas_e_a_desmarcada_continua_esperando(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    a, b, fica = _nova(db), _nova(db, 200000), _nova(db, 300000)
    r = c.post(ROTA, data={"csrf_token": _token(c), "marcada": [f"{a}:193532", f"{b}:200000"]},
               follow_redirects=True)
    assert "2 despesa(s) autorizada(s), R$ 3.935,32" in r.get_data(as_text=True)
    assert (_situacao(db, a), _situacao(db, b)) == (DP.AUTORIZADA, DP.AUTORIZADA)
    assert _situacao(db, fica) == DP.AGUARDANDO


def test_valor_que_mudou_depois_da_tela_nao_se_autoriza(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    i, outra = _nova(db), _nova(db, 200000)
    r = c.post(ROTA, data={"csrf_token": _token(c), "marcada": [f"{i}:100", f"{outra}:200000"]},
               follow_redirects=True)
    assert "O valor mudou" in r.get_data(as_text=True)
    assert _situacao(db, i) == DP.AGUARDANDO
    assert _situacao(db, outra) == DP.AUTORIZADA, "a recusa de uma não segura a outra"


def test_teto_e_divergencia_ficam_na_ficha(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    with db.connect() as con:
        teto = DP.tetos(DP.configuracao(con))["pagamento"]
    alta, divergente = _nova(db, teto + 1), _nova(db)
    with db.transaction() as con:
        DP.banco(con).escrever("UPDATE dp_despesas SET divergencia = %s WHERE id = %s",
                               ("valor diferente do documento", divergente))
    html = c.get(LISTA).get_data(as_text=True)
    assert f'value="{alta}:' not in html and f'value="{divergente}:' not in html
    assert "acima do teto" in html and "valor divergente" in html
    assert "Autorizar as marcadas" not in html, "sem o que marcar, não há botão"
    c.post(ROTA, data={"csrf_token": _token(c), "marcada": [f"{alta}:{teto + 1}",
                                                            f"{divergente}:193532"]})
    assert (_situacao(db, alta), _situacao(db, divergente)) == (DP.AGUARDANDO, DP.AGUARDANDO)


def test_so_o_oficial_ve_o_quadro_e_autoriza(cg_casa_logada):
    casa = cg_casa_logada
    i = _nova(casa["db"])
    casa["db"].create_user("gerente", "GERENTE EXEMPLO", SENHA, "MANAGER")
    c = casa["app"].test_client()
    cg_login(c, "gerente", SENHA)
    assert "Esperando a sua autorização" not in c.get(LISTA).get_data(as_text=True)
    assert c.post(ROTA, data={"csrf_token": _token(c), "marcada": f"{i}:193532"}).status_code == 403
    assert _situacao(casa["db"], i) == DP.AGUARDANDO


def test_marca_torta_e_recusada_antes_de_autorizar_qualquer_uma(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    i = _nova(db)
    r = c.post(ROTA, data={"csrf_token": _token(c), "marcada": [f"{i}:193532", "torta"]})
    assert r.status_code == 400
    assert _situacao(db, i) == DP.AGUARDANDO

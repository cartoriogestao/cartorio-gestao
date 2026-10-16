"""OS PROBLEMAS QUE EU RELATEI — problema #87, 18/09/2026.

A FRASE DO RELATO
    «Mostrar problemas abertos por mim. Adicionar ao filtro opção para
     visualizar apenas problemas criados pelo usuario logado. Assim cada
     usuario pode verificar se já foram concluidos e validar a solução ou
     reabrir»

O QUE SE MEDIU EM 23/09/2026, e o que isso decidiu
    * `ultimo_usuario` não serve para «os meus»: guarda o NOME do dia — o
      mesmo Mario em «Mario Santos» (44) e «Mario Exemplo dos Santos» (24) —,
      mistura login e nome conforme a origem, e é sobrescrito na repetição.
      Por isso `criado_por`, com o LOGIN, e só na primeira vez.
    * A auditoria sabe quem relatou em 92 de 92: é dela que os antigos ganham
      dono. O erro de tela repetido (6 de 11) fica sem dono — o primeiro não
      se sabe, e o último só topou de novo.
    * A lista era só de ADMIN e gerente, e 6 dos 8 usuários são do balcão.
      Decisão do oficial em 23/09: o balcão vê SÓ os seus, e pode REABRIR o
      seu (dizendo por quê), mas não fechar.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

import ajuda_problemas as AP

SENHA = "Senha#12345"
AGORA = "2026-09-23T10:00:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(cliente, login: str) -> None:
    cliente.post("/login",
                 data={"username": login, "password": SENHA,
                       "csrf_token": _token(cliente.get("/login").get_data(as_text=True))},
                 follow_redirects=True)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("chefe", "OFICIAL DA CASA", SENHA, "ADMIN")
    db.create_user("ana", "ANA DO BALCAO", SENHA, "USER")
    db.create_user("bia", "BIA DO BALCAO", SENHA, "USER")
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    with con:
        ids = {
            "ana_aberto": AP.anotar(con, origem="RELATADO", titulo="botão não faz nada",
                                    agora=AGORA, usuario="ANA DO BALCAO",
                                    criado_por="ana")["id"],
            "ana_resolvido": AP.anotar(con, origem="RELATADO", titulo="número saiu errado",
                                       agora=AGORA, usuario="ANA DO BALCAO",
                                       criado_por="ana")["id"],
            "bia_resolvido": AP.anotar(con, origem="RELATADO", titulo="tela da bia travou",
                                       agora=AGORA, usuario="BIA DO BALCAO",
                                       criado_por="bia")["id"],
        }
        for chave in ("ana_resolvido", "bia_resolvido"):
            AP.fechar(con, ids[chave], agora=AGORA, usuario="OFICIAL",
                      nota="consertado no pacote de hoje")
    con.close()
    cg_casa["ids"] = ids
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------------ o domínio


def test_quem_topa_de_novo_nao_vira_dono(casa):
    con = _con(casa)
    with con:
        r = AP.anotar(con, origem="RELATADO", titulo="botão não faz nada",
                      agora=AGORA, usuario="BIA DO BALCAO", criado_por="bia")
    assert r["nova"] is False
    assert AP.ler(con, r["id"])["criado_por"] == "ana"
    con.close()


def test_a_lista_e_a_contagem_seguem_o_dono(casa):
    con = _con(casa)
    meus = {p["id"] for p in AP.listar(con, criado_por="ana")}
    assert meus == {casa["ids"]["ana_aberto"], casa["ids"]["ana_resolvido"]}
    quadro = AP.contagem(con, criado_por="ana")
    assert quadro["total"] == 2 and quadro["resolvidos"] == 1
    assert AP.contagem(con)["total"] == 3
    con.close()


def test_os_antigos_ganham_dono_pela_auditoria(casa):
    """O caso da produção: relato antigo sem `criado_por`, auditoria com o
    login; erro de tela de uma vez só; e erro de tela repetido, que fica sem
    dono."""
    con = _con(casa)
    with con:
        antigo = AP.anotar(con, origem="RELATADO", titulo="relato de agosto",
                           agora=AGORA, usuario="Nome Antigo Da Ana")["id"]
        con.execute(
            "INSERT INTO audit_logs(ts, username_snapshot, action, entity_type, "
            "entity_id) VALUES (?, 'ana', 'AJUDA_PROBLEMA_RELATADO', "
            "'aj_problemas', ?)", (AGORA, antigo))
        uma_vez = AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError x",
                            detalhe="a", agora=AGORA, usuario="bia")["id"]
        repetido = AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError y",
                             detalhe="b", agora=AGORA, usuario="ana")["id"]
        AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError y", detalhe="b",
                  agora=AGORA, usuario="bia")
        estranho = AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError z",
                             detalhe="c", agora=AGORA, usuario="quem-nao-existe")["id"]
        primeira = AP.preencher_criado_por(con)
        segunda = AP.preencher_criado_por(con)
    assert AP.ler(con, antigo)["criado_por"] == "ana"
    assert AP.ler(con, uma_vez)["criado_por"] == "bia"
    assert AP.ler(con, repetido)["criado_por"] is None, (
        "o erro repetido não pode ser dado a quem só topou de novo")
    assert AP.ler(con, estranho)["criado_por"] is None, (
        "login que não existe em users não vira dono de nada")
    assert primeira == {"pelo_relato": 1, "pela_tela": 1}
    assert segunda == {"pelo_relato": 0, "pela_tela": 0}, "tem de ser idempotente"
    con.close()


def test_quem_pode_reabrir():
    resolvido_da_ana = {"criado_por": "ana", "situacao": "RESOLVIDO"}
    assert AP.pode_reabrir(resolvido_da_ana, papel="USER", login="ana")
    assert not AP.pode_reabrir(resolvido_da_ana, papel="USER", login="bia")
    assert not AP.pode_reabrir({"criado_por": "ana", "situacao": "ABERTO"},
                               papel="USER", login="ana")
    assert not AP.pode_reabrir({"criado_por": None, "situacao": "RESOLVIDO"},
                               papel="USER", login="")
    assert AP.pode_reabrir(resolvido_da_ana, papel="ADMIN", login="chefe")


def test_quem_relatou_reabre_dizendo_por_que(casa):
    con = _con(casa)
    with pytest.raises(AP.ProblemaError):
        AP.reabrir(con, casa["ids"]["ana_resolvido"], agora=AGORA,
                   usuario="ANA", motivo="ainda", exige_motivo=True)
    with con:
        AP.reabrir(con, casa["ids"]["ana_resolvido"], agora=AGORA,
                   usuario="ANA DO BALCAO",
                   motivo="o número continua saindo errado", exige_motivo=True)
    p = AP.ler(con, casa["ids"]["ana_resolvido"])
    assert p["situacao"] == "ABERTO"
    assert p["reaberto_nota"] == "o número continua saindo errado"
    assert p["reaberto_por"] == "ANA DO BALCAO"
    con.close()


# ------------------------------------------------------------ a tela


def test_o_balcao_ve_so_os_seus(casa):
    c = casa["cliente"]
    _entrar(c, "ana")
    r = c.get("/ajuda/problemas?vista=todos")
    html = r.get_data(as_text=True)
    assert r.status_code == 200, "o balcão tem de conseguir abrir a lista"
    assert "botão não faz nada" in html and "número saiu errado" in html
    assert "tela da bia travou" not in html, "o relato da colega apareceu"
    assert "Marcar como resolvido" not in html
    assert "Conferir a casa" not in html
    assert "retorno do desenvolvimento" not in html
    assert "Os problemas que você relatou" in html, "o menu não leva até aqui"


def test_o_balcao_reabre_o_seu_com_motivo(casa):
    c = casa["cliente"]
    _entrar(c, "ana")
    pid = casa["ids"]["ana_resolvido"]
    tela = c.get("/ajuda/problemas?vista=resolvidos").get_data(as_text=True)
    c.post(f"/ajuda/problemas/{pid}/situacao",
           data={"csrf_token": _token(tela), "acao": "reabrir",
                 "vista": "resolvidos", "motivo": "o número continua errado"},
           follow_redirects=True)
    con = _con(casa)
    assert AP.ler(con, pid)["situacao"] == "ABERTO"
    con.close()


def test_o_balcao_nao_reabre_o_da_colega_nem_fecha(casa):
    c = casa["cliente"]
    _entrar(c, "ana")
    tela = c.get("/ajuda/problemas").get_data(as_text=True)
    da_bia = casa["ids"]["bia_resolvido"]
    c.post(f"/ajuda/problemas/{da_bia}/situacao",
           data={"csrf_token": _token(tela), "acao": "reabrir",
                 "motivo": "tentando reabrir o da colega"},
           follow_redirects=True)
    c.post(f"/ajuda/problemas/{casa['ids']['ana_aberto']}/situacao",
           data={"csrf_token": _token(tela), "nota": "fechando o meu sozinha"},
           follow_redirects=True)
    con = _con(casa)
    assert AP.ler(con, da_bia)["situacao"] == "RESOLVIDO"
    assert AP.ler(con, casa["ids"]["ana_aberto"])["situacao"] == "ABERTO"
    con.close()


def test_quem_gere_ve_todos_e_filtra_os_seus(casa):
    c = casa["cliente"]
    _entrar(c, "chefe")
    todos = c.get("/ajuda/problemas?vista=todos").get_data(as_text=True)
    assert "tela da bia travou" in todos and "botão não faz nada" in todos
    assert "Só os meus" in todos
    con = _con(casa)
    with con:
        AP.anotar(con, origem="RELATADO", titulo="o do chefe", agora=AGORA,
                  usuario="OFICIAL", criado_por="chefe")
    con.close()
    meus = c.get("/ajuda/problemas?vista=todos&meus=1").get_data(as_text=True)
    assert "o do chefe" in meus
    assert "tela da bia travou" not in meus

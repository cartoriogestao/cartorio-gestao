# -*- coding: utf-8 -*-
"""Trocar a tarefa do cronômetro sem parar — «não consigo mudar o cronômetro».

Relato de 19/11/2026 no próprio controle diário. Na tela, com o relógio
correndo, só havia a tarefa (sem edição), Pausar e «Parar e salvar». O que
ficou gravado mostra as duas saídas que a pessoa achou:

  - 17/11, 10:45:08, 10:45:20 e 10:45:28: três inícios em 20 s, «vou fazer»,
    «vou fazer 4 certidões aora» e «vou fazer quatro certidões agora» — os dois
    primeiros com zero minuto, só para corrigir o que tinha digitado;
  - 19/11: um lançamento de 5h05 (10h31–15h36) que resume a manhã e a tarde,
    com a queixa escrita no nome.

Pausar não resolvia: o pausado continua aberto e barra o segundo — e a
mensagem dizia «pare ou pause».
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime

import produtividade as PR
import pytest
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

UID = 5
DIA = datetime(2026, 11, 17)


def _con() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    PR.init_produtividade_schema(con)
    return con


def _as(h: int, m: int, s: int = 0) -> datetime:
    return DIA.replace(hour=h, minute=m, second=s)


def _inicia(con, quando, tarefa):
    return PR.iniciar_cronometro(con, responsavel_user_id=UID, responsavel_nome="Escrevente",
                                 categoria=PR.CATEGORIA_PADRAO, tarefa=tarefa, agora=quando)


def _troca(con, quando, tarefa, categoria=PR.CATEGORIA_PADRAO):
    return PR.trocar_cronometro(con, responsavel_user_id=UID, responsavel_nome="Escrevente",
                                categoria=categoria, tarefa=tarefa, agora=quando)


def _todos(con):
    return [dict(r) for r in con.execute(
        "SELECT id, tarefa, status, hora_inicio, hora_fim, pausas_min FROM prod_registros "
        "WHERE responsavel_user_id=? ORDER BY id", (UID,)).fetchall()]


def test_corrigir_o_nome_no_mesmo_minuto_nao_deixa_lancamento_de_zero_minuto():
    """A sequência de 17/11 às 10h45, agora com a troca: um registro só."""
    con = _con()
    rid = _inicia(con, _as(10, 45, 8), "vou fazer")
    t1 = _troca(con, _as(10, 45, 20), "vou fazer 4 certidões aora")
    t2 = _troca(con, _as(10, 45, 28), "vou fazer quatro certidões agora")
    assert t1["corrigido"] and t2["corrigido"]
    assert t2["anterior"] is None
    regs = _todos(con)
    assert len(regs) == 1 and regs[0]["id"] == rid
    assert regs[0]["tarefa"] == "vou fazer quatro certidões agora"
    assert regs[0]["status"] == PR.STATUS_EM_ANDAMENTO and regs[0]["hora_inicio"] == "10:45"


def test_trocar_depois_fecha_o_atual_e_abre_o_proximo_na_mesma_hora():
    """O caso de 19/11: em vez de 5h05 num lançamento só, um por tarefa."""
    con = _con()
    _inicia(con, _as(8, 34), "ATENDIMENTO NO BALCÃO")
    t = _troca(con, _as(9, 55, 40), "REGISTRO DE ÓBITO")
    assert t["corrigido"] is False
    assert t["anterior"]["status"] == PR.STATUS_CONCLUIDA
    assert (t["anterior"]["hora_inicio"], t["anterior"]["hora_fim"]) == ("08:34", "09:55")
    assert t["anterior"]["tempo_liquido_min"] == 81
    assert t["cronometro"]["tarefa"] == "REGISTRO DE ÓBITO"
    assert t["cronometro"]["hora_inicio"] == "09:55"  # sem buraco entre os dois
    assert t["aviso"] is None
    abertos = [r for r in _todos(con) if not r["hora_fim"]]
    assert len(abertos) == 1  # a regra de um aberto por pessoa continua


def test_trocar_o_pausado_desconta_a_pausa_do_que_fecha():
    con = _con()
    _inicia(con, _as(9, 0), "CERTIDÃO DE NASCIMENTO")
    PR.pausar_cronometro(con, responsavel_user_id=UID, agora=_as(9, 20))
    t = _troca(con, _as(9, 30), "PROTOCOLO")
    assert t["anterior"]["pausas_min"] == 10
    assert t["anterior"]["tempo_liquido_min"] == 20
    assert t["cronometro"]["status"] == PR.STATUS_EM_ANDAMENTO


def test_trocar_depois_das_14h30_sem_confirmar_guarda_o_fechamento_da_regra_e_abre_o_proximo():
    """O anterior fecha às 14h15 (regra do oficial, 11/10/2026) e diz por quê;
    o próximo começa agora, e conta como confirmado por ter nascido depois."""
    con = _con()
    _inicia(con, _as(13, 0), "ATENDIMENTO NO BALCÃO")
    t = _troca(con, _as(14, 40), "REGISTRO DE ÓBITO")
    assert t["anterior"]["hora_fim"] == "14:15"
    assert PR.MARCA_ENCERRAMENTO_AUTOMATICO in (t["aviso"] or "")
    assert t["cronometro"]["hora_inicio"] == "14:40"


def test_trocar_sem_cronometro_aberto_ou_sem_tarefa_recusa_sem_gravar():
    con = _con()
    with pytest.raises(LookupError, match="Iniciar cronômetro"):
        _troca(con, _as(9, 0), "PROTOCOLO")
    _inicia(con, _as(9, 0), "PROTOCOLO")
    with pytest.raises(ValueError, match="próxima tarefa"):
        _troca(con, _as(9, 30), "   ")
    with pytest.raises(ValueError, match="Categoria"):
        _troca(con, _as(9, 30), "OUTRA", categoria="9 - Inventada")
    assert len(_todos(con)) == 1 and _todos(con)[0]["hora_fim"] in (None, "")


def test_a_recusa_do_segundo_nao_manda_mais_pausar():
    """Pausar não libera o segundo; a frase dizia «pare ou pause»."""
    con = _con()
    _inicia(con, _as(9, 0), "PROTOCOLO")
    PR.pausar_cronometro(con, responsavel_user_id=UID, agora=_as(9, 5))
    with pytest.raises(ValueError) as erro:
        _inicia(con, _as(9, 6), "OUTRA")
    texto = str(erro.value)
    assert "Trocar de tarefa" in texto and "PROTOCOLO" in texto
    assert "pause o atual" not in texto


# ------------------------------------------------------------------ a tela

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_rota_trocar(cg_casa_logada):
    c = cg_casa_logada["c"]
    tok = _token(c.get("/administrativo/produtividade").get_data(as_text=True))
    cab = {"X-CSRF-Token": tok}
    r = c.post("/administrativo/produtividade/api/cronometro/trocar",
               data={"csrf_token": tok, "categoria": PR.CATEGORIA_PADRAO, "tarefa": "X"},
               headers=cab)
    assert r.status_code == 400 and r.get_json()["ok"] is False  # nada aberto
    assert c.post("/administrativo/produtividade/api/cronometro/iniciar",
                  data={"csrf_token": tok, "categoria": PR.CATEGORIA_PADRAO,
                        "tarefa": "vou fazer"}, headers=cab).get_json()["ok"]
    r = c.post("/administrativo/produtividade/api/cronometro/trocar",
               data={"csrf_token": tok, "categoria": PR.CATEGORIA_PADRAO,
                     "tarefa": "vou fazer quatro certidões agora"}, headers=cab).get_json()
    assert r["ok"] and r["cronometro"]["tarefa"] == "vou fazer quatro certidões agora"
    # no mesmo minuto é correção; se o relógio virou o minuto, fechou o primeiro
    assert r["corrigido"] is True or r["anterior"]["tarefa"] == "vou fazer"
    st = c.get("/administrativo/produtividade/api/cronometro/status").get_json()
    assert st["cronometro"]["tarefa"] == "vou fazer quatro certidões agora"
    c.post("/administrativo/produtividade/api/cronometro/parar",
           data={"csrf_token": tok}, headers=cab)


def test_aba_aberta_antes_de_entrar_de_novo_recebe_400_em_html(cg_casa_logada):
    """Por que a tela dizia «Falha de rede»: o login troca o token; a aba que
    ficou aberta manda o velho, o servidor responde 400 em HTML, e o JS caía no
    `catch` da rede. Agora ele diz para recarregar a página."""
    from conftest import cg_login
    c = cg_casa_logada["c"]
    velho = _token(c.get("/administrativo/produtividade").get_data(as_text=True))
    cg_login(c, "mario", "Senha#12345")  # entrou de novo (outra aba, sessão que caiu)
    r = c.post("/administrativo/produtividade/api/cronometro/iniciar",
               data={"csrf_token": velho, "categoria": PR.CATEGORIA_PADRAO, "tarefa": "X"},
               headers={"X-CSRF-Token": velho})
    assert r.status_code == 400 and r.get_json(silent=True) is None
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "static" / "produtividade_rapida.js").read_text(
        encoding="utf-8")
    assert "SESSAO_MUDOU" in js and "F5" in js


def test_a_tela_tem_a_troca_e_o_enter_nao_tenta_iniciar_um_segundo(cg_casa_logada):
    html = cg_casa_logada["c"].get("/administrativo/produtividade").get_data(as_text=True)
    for marca in ("data-url-trocar", "data-prod-trocar", "data-prod-proxima", "Trocar de tarefa"):
        assert marca in html
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "static" / "produtividade_rapida.js").read_text(
        encoding="utf-8")
    assert "if (cronoAtual) { trocarTarefa(); return; }" in js
    # o status que diz «nenhum aberto» limpa a tela que ainda contava um
    assert "else if (cronoAtual) mostrarCrono(null);" in js

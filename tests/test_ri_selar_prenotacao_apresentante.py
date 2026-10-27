"""O «Selar» da prenotação já lavrada usa o apresentante gravado.

A faixa «Pendente de selo» não mandava o nome nem o documento. O envelope
saía com a lista de partes vazia e o aparelho recusava «Os nomes das partes
devem ser informados». O clique em Selar usa o que já está na prenotação
quando o formulário não traz esses campos. Sem apresentante gravado, a rota
recusa antes de chamar o aparelho.

Dados fictícios: nome de exemplo e documento da lista de fictícios.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

NOME = "APRESENTANTE EXEMPLO"
DOCUMENTO = "00000000191"
NUMERO = 900001


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _gravar(casa, *, apresentante, documento) -> int:
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_protocolos
               (numero, livro, data_prenotacao, apresentante,
                apresentante_documento, natureza_titulo, situacao, origem,
                criado_em)
               VALUES (?, '1A', '2026-10-01', ?, ?, 'COMPRA E VENDA',
                       'ABERTO', 'MANUAL', '2026-10-01T10:00:00')""",
            (NUMERO, apresentante, documento))
        pid = int(cur.lastrowid)
    con.close()
    return pid


def _selo(casa, pid) -> str:
    con = _con(casa)
    texto = con.execute(
        "SELECT selo_prenotacao FROM ri_protocolos WHERE id=?",
        (pid,)).fetchone()[0]
    con.close()
    return texto or ""


def _pedidos_de_prenotacao(aparelho) -> list[dict]:
    return [p for p in aparelho.pedidos
            if "prenotacao" in (p.get("caminho") or "")]


def _partes_pedidas(aparelho) -> list[dict]:
    """O que o aparelho recebeu em parteAto no caminho da prenotação."""
    saida = []
    for pedido in _pedidos_de_prenotacao(aparelho):
        try:
            corpo = json.loads(pedido.get("corpo") or "{}")
        except json.JSONDecodeError:
            continue
        dados = corpo.get("dadosSelo") if isinstance(corpo, dict) else None
        if not isinstance(dados, dict):
            continue
        partes = (dados.get("partes") or {}).get("parteAto") or []
        saida.extend(p for p in partes if isinstance(p, dict))
    return saida


def _selar_sem_apresentante_no_form(c, pid):
    """O POST do botão Selar, sem os campos que a faixa antiga não mandava."""
    ver = f"/registro-imoveis/protocolo/{pid}"
    tela = c.get(ver).get_data(as_text=True)
    return c.post(
        f"{ver}/selar",
        data={"csrf_token": _token(tela),
              "natureza_titulo": "COMPRA E VENDA",
              "codigo_tj": "16.1"},
        follow_redirects=True).get_data(as_text=True), tela


def test_selar_depois_usa_o_apresentante_gravado(cg_casa_logada):
    """O formulário não traz o nome; o selo leva o que a prenotação já tem."""
    from selador_de_bancada import ligar_o_selador

    casa = cg_casa_logada
    pid = _gravar(casa, apresentante=NOME, documento=DOCUMENTO)
    with ligar_o_selador(casa) as aparelho:
        html, tela = _selar_sem_apresentante_no_form(casa["c"], pid)
        partes = _partes_pedidas(aparelho)
    assert f'name="apresentante" value="{NOME}"' in tela
    assert f'name="apresentante_documento" value="{DOCUMENTO}"' in tela
    assert partes == [{"nome": NOME, "documento": DOCUMENTO}], partes
    assert _selo(casa, pid), html[:800]
    assert "Não selou" not in html


def test_sem_apresentante_gravado_recusa_antes_do_aparelho(cg_casa_logada):
    """Lista de partes vazia não vai ao aparelho: a tela pede o apresentante."""
    from selador_de_bancada import ligar_o_selador

    casa = cg_casa_logada
    pid = _gravar(casa, apresentante=None, documento=None)
    with ligar_o_selador(casa) as aparelho:
        html, _tela = _selar_sem_apresentante_no_form(casa["c"], pid)
        pedidos = _pedidos_de_prenotacao(aparelho)
    assert pedidos == [], "a recusa tinha de acontecer antes do aparelho"
    assert not _selo(casa, pid)
    assert "Não selou a prenotação" in html
    assert "informe o apresentante" in html

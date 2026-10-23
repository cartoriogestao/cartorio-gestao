"""Salvar o preenchimento e continuar depois — relato #36 do oficial.

O QUE ESTES TESTES GUARDAM
    **Que salvar NAO exige formulario valido.** E a razao de o mecanismo
    existir: o escrevente salva no meio, com metade dos campos e a outra
    metade errada, porque o cliente foi buscar um documento. Cobrar validade
    seria exigir que ele terminasse para poder parar.

    **Que o `csrf_token` nunca entra.** Guardado, ele volta invalido e o
    formulario recusa o proprio rascunho — e o escrevente nao teria como
    entender por que.

    **Que rascunho nao toma numero.** Rascunho que consome numero e ato
    disfarcado, e ato disfarcado aparece na correicao como buraco na
    sequencia.

    **Que nada e apagado sozinho.** O sistema mostra os velhos; quem joga
    fora e quem olha.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rascunho_de_tela as R                                   # noqa: E402

AGORA = "2026-08-30T18:00:00"


def _banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    R.init_rascunho_schema(con)
    return con


def test_salva_e_le_de_volta():
    con = _banco()
    r = R.salvar(con, tela="rcpn_assento_novo", titulo="Nascimento — MARIA",
                 dados={"nome": "MARIA", "especie": "NASCIMENTO"},
                 agora=AGORA, por="elisa")
    assert r["novo"] is True
    lido = R.ler(con, r["id"])
    assert lido["dados"]["nome"] == "MARIA"
    assert lido["titulo"] == "Nascimento — MARIA"
    con.close()


def test_salvar_nao_exige_formulario_valido():
    """**E a razao de existir.** O cliente foi buscar um documento, e o
    escrevente precisa parar no meio — com campos faltando e outros errados."""
    con = _banco()
    r = R.salvar(con, tela="notas_ato_novo", titulo="Escritura pela metade",
                 dados={"nome": "JOÃO", "cpf": "não sei ainda",
                        "valor": "", "data": "31/02/2026"},
                 agora=AGORA)
    assert R.ler(con, r["id"])["dados"]["cpf"] == "não sei ainda"
    con.close()


def test_o_csrf_nunca_entra():
    """Guardado, ele volta invalido e o formulario recusa o proprio rascunho.
    O escrevente veria o sistema rejeitar o trabalho dele sem explicacao."""
    con = _banco()
    r = R.salvar(con, tela="x", titulo="t",
                 dados={"nome": "MARIA", "csrf_token": "abc123"},
                 agora=AGORA)
    assert "csrf_token" not in R.ler(con, r["id"])["dados"]
    con.close()


def test_senha_e_pin_nunca_entram():
    """Nao se guardam em lugar nenhum, e muito menos num papel de anotacao que
    fica no banco ate alguem apagar."""
    con = _banco()
    r = R.salvar(con, tela="x", titulo="t",
                 dados={"nome": "M", "senha": "1234", "pin_do_token": "9999",
                        "password": "abc"},
                 agora=AGORA)
    guardado = R.ler(con, r["id"])["dados"]
    assert set(guardado) == {"nome"}
    con.close()


def test_rascunho_vazio_recusa_em_portugues():
    con = _banco()
    with pytest.raises(R.RascunhoError) as e:
        R.salvar(con, tela="x", titulo="t",
                 dados={"a": "", "b": "  ", "csrf_token": "z"}, agora=AGORA)
    assert "nada preenchido" in str(e.value)
    con.close()


def test_tela_sem_nome_recusa():
    con = _banco()
    with pytest.raises(R.RascunhoError):
        R.salvar(con, tela="", titulo="t", dados={"a": "1"}, agora=AGORA)
    con.close()


def test_salvar_de_novo_atualiza_e_nao_duplica():
    """Salvar duas vezes o mesmo trabalho nao pode gerar dois rascunhos: a
    lista viraria um monte de versoes do mesmo, e ninguem sabe qual e a boa."""
    con = _banco()
    r = R.salvar(con, tela="t", titulo="Primeiro", dados={"a": "1"},
                 agora=AGORA)
    r2 = R.salvar(con, tela="t", titulo="Segundo", dados={"a": "2"},
                  agora="2026-08-30T19:00:00", rascunho_id=r["id"])
    assert r2["novo"] is False and r2["id"] == r["id"]
    assert R.quantos(con) == 1
    assert R.ler(con, r["id"])["dados"]["a"] == "2"
    con.close()


def test_atualizar_rascunho_que_nao_existe_recusa():
    con = _banco()
    with pytest.raises(R.RascunhoError):
        R.salvar(con, tela="t", titulo="x", dados={"a": "1"}, agora=AGORA,
                 rascunho_id=999)
    con.close()


def test_lista_por_tela_e_do_mais_recente():
    con = _banco()
    R.salvar(con, tela="rcpn_assento_novo", titulo="A", dados={"x": "1"},
             agora="2026-08-30T10:00:00")
    R.salvar(con, tela="notas_ato_novo", titulo="B", dados={"x": "1"},
             agora="2026-08-30T11:00:00")
    R.salvar(con, tela="rcpn_assento_novo", titulo="C", dados={"x": "1"},
             agora="2026-08-30T12:00:00")
    assert [x["titulo"] for x in R.listar(con)] == ["C", "B", "A"]
    assert [x["titulo"] for x in R.listar(con, tela="rcpn_assento_novo")] == \
        ["C", "A"]
    con.close()


def test_apagar_nao_pede_motivo():
    """Ao contrario de cancelar ato: o rascunho nunca foi ato, nao tomou
    numero e nao esta em corrente nenhuma. Exigir justificativa faria o
    escrevente deixar tudo acumulado."""
    con = _banco()
    r = R.salvar(con, tela="t", titulo="x", dados={"a": "1"}, agora=AGORA)
    R.apagar(con, r["id"])
    assert R.quantos(con) == 0
    con.close()


def test_os_velhos_aparecem_e_nao_somem_sozinhos():
    """**Apagar sozinho seria o sistema jogando fora trabalho de alguem sem
    avisar.** A lista mostra; quem apaga e quem olha."""
    con = _banco()
    R.salvar(con, tela="t", titulo="velho", dados={"a": "1"},
             agora="2026-06-01T10:00:00")
    R.salvar(con, tela="t", titulo="novo", dados={"a": "1"},
             agora="2026-08-29T10:00:00")
    velhos = R.expirados(con, "2026-08-30")
    assert [v["titulo"] for v in velhos] == ["velho"]
    assert velhos[0]["dias_parado"] == 90
    assert R.quantos(con) == 2, "a lista de velhos nao pode apagar nada"
    con.close()


def test_dado_ilegivel_nao_derruba_a_tela():
    """Melhor abrir vazio dizendo que nao da para ler do que um erro de
    sistema em cima de um papel de anotacao."""
    con = _banco()
    r = R.salvar(con, tela="t", titulo="x", dados={"a": "1"}, agora=AGORA)
    con.execute("UPDATE rascunhos_de_tela SET dados_json='{isto nao e json'"
                " WHERE id=?", (r["id"],))
    lido = R.ler(con, r["id"])
    assert lido["dados"] == {} and lido.get("ilegivel") is True
    con.close()


def test_o_modulo_nao_numera_nem_lavra():
    """**Rascunho que consome numero e ato disfarcado**, e ato disfarcado
    aparece na correicao como buraco na sequencia."""
    codigo = (RAIZ / "rascunho_de_tela.py").read_text(encoding="utf-8")
    for proibido in ("numero_ordem", "reservar", "MAX(numero"):
        assert proibido not in codigo, f"o módulo mexe com «{proibido}»"
    import re
    for alvo in re.findall(r"(?:INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)",
                           codigo):
        assert alvo == "rascunhos_de_tela", f"escreve em «{alvo}»"

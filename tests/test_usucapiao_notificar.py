"""Expedir notificacao no usucapiao — relato #30 do oficial.

O QUE ESTES TESTES GUARDAM

    **Que a lista de campos aceitos NAO diverge do banco.** Ela e escrita a mao
    dentro de `_mover`, e esse mesmo padrao ja custou caro noutro modulo: o
    `INSERT` de `rc_pessoas` listava colunas a mao, e `documento_orgao` e
    `idade_no_fato` existiam na tabela E NA TELA e **nunca eram salvas**. Aqui a
    lista se compara com as colunas reais — coluna nova que nasca sem entrar
    nela fica vermelha, em vez de sumir calada.

    **Que o papel e conferido ANTES de o movimento existir.** Um movimento de
    notificacao sem papel que o sustente e uma linha dizendo que a serventia
    notificou alguem sem ter notificado.

    **Que o teor expedido fica guardado.** Remonta-lo depois traria o processo
    como ele esta hoje, e nao como estava quando o papel saiu — e o que o
    notificado leu e o de entao.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import us_notificacao as UN                                      # noqa: E402
import usucapiao as US                                           # noqa: E402

AGORA = "2026-08-30T10:00"
SERVENTIA = {"oficial": "MARIO EXEMPLO DOS SANTOS", "cargo": "Oficial",
             "nome": "Serventia Extrajudicial de Cidade Exemplo/MA"}


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture()
def processo_id(con):
    pid = US.autuar(
        con, numero="3", modalidade="ORDINARIA", agora=AGORA,
        requerente_nome="JOÃO BATISTA DE SOUSA", usuario="jean")
    con.execute(
        """UPDATE us_processos SET imovel_descricao=?, imovel_endereco=?,
               imovel_municipio=?, imovel_uf=?, imovel_area=?,
               posse_tempo_alegado=? WHERE id=?""",
        ("Um terreno urbano de 12m por 30m", "Rua das Flores, s/n",
         "Cidade Exemplo", "MA", "360,00 m²", "há mais de quinze anos", pid))
    con.commit()
    return pid


def _notificar(con, pid, **troca):
    dados = dict(destinatario="MARIA DAS DORES SOUSA",
                 destinatario_papel="Confrontante ao norte",
                 endereco="Rua do Comércio, 45, Cidade Exemplo/MA",
                 forma="PESSOAL", prazo_chave="CONFRONTANTE",
                 agora=AGORA, serventia=SERVENTIA,
                 hoje_extenso="Cidade Exemplo/MA, 30 de agosto de 2026",
                 usuario="jean")
    dados.update(troca)
    return US.notificar(con, pid, **dados)


# ------------------------------------------------- a lista contra o banco


# COLUNAS QUE A MAQUINA CONTROLA, e que por isso nao vem do chamador.
DA_MAQUINA = {
    "us_movimentos": {"id", "processo_id", "tipo", "etapa", "descricao",
                      "data_movimento", "criado_em", "criado_por"},
    "us_processos": {"id", "numero", "modalidade", "etapa", "situacao",
                     "criado_em", "criado_por", "atualizado_em",
                     "encerrado_em"},
}


def _colunas_de(con, tabela: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({tabela})")
            if r[1] not in DA_MAQUINA[tabela]]


def test_autuar_grava_TODA_coluna_que_lhe_e_passada(con):
    """**O defeito de `rc_pessoas`, medido pelo comportamento e nao pelo texto.**

    La, `documento_orgao` e `idade_no_fato` existiam na tabela E NA TELA e
    **nunca eram salvas**: o `INSERT` listava as colunas a mao e tinha
    divergido. Ninguem percebeu porque coluna que nao se grava nao da erro —
    fica vazia.

    Este teste manda um valor para **cada** coluna e confere que ele voltou.

    > **E ele so ficou assim depois de eu errar tres vezes tentando LER o
    > codigo**: procurando a tupla no arquivo inteiro (achava a da outra
    > funcao), olhando so a tupla (ha colunas nomeadas fora dela — e eu cheguei
    > a anunciar um defeito que nao existia), e cortando o corpo num
    > `con.execute` anterior. **Teste que le codigo prova como ele esta
    > escrito; teste que exercita prova o que ele faz** — e o que interessa aqui
    > e o que ele faz.
    """
    colunas = _colunas_de(con, "us_processos")
    mandados = {c: (1 if c.endswith("_id") or c == "valor_centavos" or
                    c == "ano" else f"valor de {c}")
                for c in colunas}
    pid = US.autuar(con, numero="9", modalidade="ORDINARIA", agora=AGORA,
                    usuario="jean", **mandados)
    linha = con.execute("SELECT * FROM us_processos WHERE id=?",
                        (pid,)).fetchone()
    perdidas = [c for c in colunas
                if str(linha[c] or "") != str(mandados[c])]
    assert not perdidas, (
        "estas colunas foram passadas para `autuar` e não chegaram ao banco: "
        + ", ".join(sorted(perdidas))
        + " — quem preencher esses campos na tela vai vê-los sumir")


def test_movimentar_grava_TODA_coluna_que_lhe_e_passada(con, processo_id):
    """O mesmo, do lado do movimento — é onde a notificação mora."""
    colunas = _colunas_de(con, "us_movimentos")
    mandados = {c: (1 if c in ("prazo_dias", "prazo_uteis", "tentativa")
                    else f"valor de {c}") for c in colunas}
    mid = US.movimentar(con, processo_id, tipo="OUTRO", descricao="ensaio",
                        agora=AGORA, usuario="jean", **mandados)
    linha = con.execute("SELECT * FROM us_movimentos WHERE id=?",
                        (mid,)).fetchone()
    perdidas = [c for c in colunas
                if str(linha[c] or "") != str(mandados[c])]
    assert not perdidas, (
        "estas colunas foram passadas para `movimentar` e não chegaram ao "
        "banco: " + ", ".join(sorted(perdidas))
        + " — acrescente-as à tupla `aceitos` em `_mover`")


# ------------------------------------------------- expedir


def test_a_notificacao_grava_o_movimento_com_tudo(con, processo_id):
    r = _notificar(con, processo_id)
    linha = con.execute("SELECT * FROM us_movimentos WHERE id=?",
                        (r["movimento_id"],)).fetchone()
    assert linha["tipo"] == "NOTIFICACAO"
    assert linha["destinatario"] == "MARIA DAS DORES SOUSA"
    assert linha["endereco"].startswith("Rua do Comércio")
    assert linha["forma"] == "PESSOAL"
    assert linha["prazo_dias"] == 15 and linha["prazo_uteis"] == 1


def test_o_teor_expedido_fica_guardado(con, processo_id):
    """**O que o notificado leu é o de então.** Remontá-lo depois traria o
    processo como ele está hoje."""
    r = _notificar(con, processo_id)
    guardado = con.execute(
        "SELECT teor_expedido FROM us_movimentos WHERE id=?",
        (r["movimento_id"],)).fetchone()[0]
    assert "MARIA DAS DORES SOUSA" in guardado
    assert "USUCAPIÃO EXTRAJUDICIAL" in guardado
    assert guardado == r["teor"]


def test_o_papel_e_conferido_antes_de_o_movimento_existir(con, processo_id):
    """**Movimento sem papel que o sustente é uma linha dizendo que a serventia
    notificou alguém sem ter notificado.**"""
    antes = con.execute("SELECT COUNT(*) FROM us_movimentos").fetchone()[0]
    with pytest.raises(UN.NotificacaoError):
        _notificar(con, processo_id, endereco="")
    depois = con.execute("SELECT COUNT(*) FROM us_movimentos").fetchone()[0]
    assert depois == antes, "gravou o movimento apesar de o papel ser recusado"


def test_forma_fora_da_norma_nao_grava(con, processo_id):
    antes = con.execute("SELECT COUNT(*) FROM us_movimentos").fetchone()[0]
    with pytest.raises(UN.NotificacaoError):
        _notificar(con, processo_id, forma="WHATSAPP")
    assert con.execute(
        "SELECT COUNT(*) FROM us_movimentos").fetchone()[0] == antes


def test_o_prazo_vem_da_norma_e_nao_de_quem_digita(con, processo_id):
    """Quem escolhe o prazo é a regra do destinatário, e não um campo livre —
    prazo digitado errado para menos produz anuência por silêncio."""
    r = _notificar(con, processo_id, prazo_chave="TITULAR_TABULAR")
    assert r["prazo"]["dias"] == 15
    assert r["prazo"]["procedencia"] == UN.CITADO
    linha = con.execute("SELECT prazo_uteis FROM us_movimentos WHERE id=?",
                        (r["movimento_id"],)).fetchone()
    assert linha["prazo_uteis"] == 0, "o do titular tabular é em dias corridos"


def test_processo_encerrado_nao_se_notifica(con, processo_id):
    con.execute("UPDATE us_processos SET situacao='REGISTRADO' WHERE id=?",
                (processo_id,))
    con.commit()
    with pytest.raises(US.UsucapiaoError) as e:
        _notificar(con, processo_id)
    assert "não há mais o que notificar" in str(e.value)


def test_a_descricao_do_movimento_diz_quem_e_por_que_forma(con, processo_id):
    """Quem abrir o andamento seis meses depois tem de entender sem abrir o
    papel."""
    r = _notificar(con, processo_id)
    d = con.execute("SELECT descricao FROM us_movimentos WHERE id=?",
                    (r["movimento_id"],)).fetchone()[0]
    assert "MARIA DAS DORES SOUSA" in d
    assert "Confrontante ao norte" in d
    assert "Pessoalmente" in d

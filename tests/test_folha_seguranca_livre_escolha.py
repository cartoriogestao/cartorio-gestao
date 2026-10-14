"""A folha de segurança passou a ser ESCOLHIDA na certidão do RCPN.

    «sistema esta colocando automaticamente a folha de segurança, errada,
    nas certidoes. Precisamos sempre que for imprimir uma certidao, colocar
    manualmente (ou escolher na lista do estoque) a folha de segurançá
    certa»  — o oficial, 08/09/2026

INVESTIGADO ANTES DE CONSTRUIR
    O razão de `pp_folhas` na produção não mostrou defeito de conta: as
    últimas cinco baixas (códigos 7225137 a 7225141) saíram na ordem certa,
    por pessoas diferentes, entre 01 e 08/09/2026. O descompasso é de
    manuseio do papel físico, não da numeração — mas quem decide o que fazer
    com isso é o oficial, e ele escolheu **escolha livre, sem exigir motivo**
    (a opção recomendada), sabendo que a numeração pode saltar sem explicação
    registrada.

O QUE ESTES TESTES GUARDAM
      - a escolha do balcão é usada no lugar da sugestão automática, e a
        folha que ele NÃO escolheu continua em branco (prova de que não é
        sequencial);
      - folha inexistente ou já usada/inutilizada é RECUSADA, sem emitir a
        certidão, e a mensagem diz por quê — antes de tentar selar;
      - sem escolha nenhuma, o comportamento de sempre continua (a menor em
        branco, automática);
      - a ficha MOSTRA a lista do estoque em branco, com a sugerida marcada;
      - E A LISTA NÃO CORTA EM 200 — relato do oficial em 09/09/2026: «a
        folha 007225441 não aparece para lavrar certidão». A folha certa
        (sem os zeros à esquerda, que era o duplicado já estornado) estava
        na posição 285 de 344 em branco, e `PP.listar` cortava em 200 por
        padrão. Escolha livre não pode ter teto escondendo estoque real.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import papel_seguranca as PP                                     # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-09-08T10:00:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear_assento(s, nome: str = "JOÃO DA SILVA") -> int:
    """Um assento de nascimento, com filiação — o mínimo para emitir."""
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem,
                   criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,
                       '000000015519971000111270010385 01',?,
                       '2020-01-20','2020-01-15','{"strSexo": "Masculino"}',
                       'ATIVO','EOFICIO',?)""", (nome, AGORA))
        assento_id = con.execute(
            "SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',127,19552,'127','2020-01-20','EOFICIO',
                       ?)""", (assento_id, AGORA))
        for papel, quem, ordem in (("PAI", "JOSÉ DA SILVA", 1),
                                   ("MAE", "MARIA DAS GRAÇAS SILVA", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em)
                   VALUES (?,?,?,?,'EOFICIO',?)""",
                (assento_id, papel, quem, ordem, AGORA))
    con.close()
    return assento_id


def _semear_folhas(s, *codigos: str) -> None:
    con = _con(s)
    with con:
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="HA",
                           codigo_de=min(codigos), codigo_ate=max(codigos),
                           agora=AGORA, nota_fiscal="NF 1", usuario="JEAN")
    con.close()


def _folha(s, codigo: str) -> sqlite3.Row:
    con = _con(s)
    linha = PP.ler(con, codigo)
    con.close()
    return linha


def _fake_selar_ok(*a, **k):
    return {"selado": True, "numero": "AVESVD000000TESTE0001", "motivo": None}


def _emitir(s, assento_id: int, **campos):
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    return s["c"].post(f"/rcpn/{assento_id}/certidao",
                       data={"csrf_token": _token(html), **campos},
                       follow_redirects=True)


# --------------------------------------------------------------- a tela


def test_a_ficha_mostra_a_lista_do_estoque_com_a_sugerida_marcada(s):
    assento_id = _semear_assento(s)
    _semear_folhas(s, "500001", "500002", "500003")
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert 'name="folha_seguranca"' in html
    assert "500001" in html and "500002" in html and "500003" in html
    # a MENOR em branco é a sugerida, marcada — mas as outras aparecem
    achado = re.search(
        r'<option value="500001"[^>]*selected', html)
    assert achado, "a folha 500001 (a menor) deveria vir pré-selecionada"


def test_a_lista_nao_esconde_folha_alem_da_posicao_200(s):
    """O relato do oficial em 09/09/2026: «a folha 007225441 não aparece
    para lavrar certidão». Com 250 em branco na faixa, a última (na posição
    250) tem de aparecer — não só as 200 primeiras."""
    assento_id = _semear_assento(s)
    _semear_folhas(s, "600001", "600250")      # 250 folhas EM BRANCO
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert 'value="600250"' in html, (
        "a folha na posição 250 do estoque ficou fora da lista da ficha")


# ------------------------------------------------------------- a escolha


def test_escolha_de_folha_e_usada_no_lugar_da_sugestao(s, monkeypatch):
    """O pedido do oficial: escolher qualquer uma do estoque, não só a
    sugerida — e a que ele NÃO escolheu tem de continuar em branco."""
    import atribuicoes_web as AW
    monkeypatch.setattr(AW.AS, "selar_o_ato_lavrado", _fake_selar_ok)

    assento_id = _semear_assento(s)
    _semear_folhas(s, "700001", "700002", "700003")

    r = _emitir(s, assento_id, requerente="A MÃE", finalidade="INSS",
               folha_seguranca="700003")
    html = r.get_data(as_text=True)
    assert "emitida" in html
    assert "700003" in html

    assert _folha(s, "700003")["situacao"] == "USADA"
    # a sugerida (700001) NÃO foi tocada — a escolha é livre
    assert _folha(s, "700001")["situacao"] == "EM BRANCO"
    assert _folha(s, "700002")["situacao"] == "EM BRANCO"


def test_folha_escolhida_inexistente_e_recusada_antes_de_selar(s, monkeypatch):
    """A recusa é aqui, e não na rede: nem se tenta selar com folha errada."""
    import atribuicoes_web as AW

    def _selar_nao_deveria_ser_chamado(*a, **k):
        raise AssertionError(
            "não deveria tentar selar: a folha escolhida é inválida")
    monkeypatch.setattr(AW.AS, "selar_o_ato_lavrado",
                        _selar_nao_deveria_ser_chamado)

    assento_id = _semear_assento(s)
    _semear_folhas(s, "800001")

    r = _emitir(s, assento_id, requerente="A MÃE", finalidade="INSS",
               folha_seguranca="999999")
    html = r.get_data(as_text=True)
    assert "999999" in html and "não está em branco" in html
    assert _con(s).execute("SELECT COUNT(*) FROM rc_certidoes").fetchone()[0] == 0
    assert _folha(s, "800001")["situacao"] == "EM BRANCO"


def test_folha_escolhida_ja_usada_e_recusada(s, monkeypatch):
    import atribuicoes_web as AW
    monkeypatch.setattr(AW.AS, "selar_o_ato_lavrado", _fake_selar_ok)

    assento_id = _semear_assento(s)
    _semear_folhas(s, "810001")
    con = _con(s)
    with con:
        PP.usar(con, "810001", tabela="rc_certidoes", ato_id=1, agora=AGORA,
               usuario="OUTRO")
    con.close()

    r = _emitir(s, assento_id, requerente="A MÃE", finalidade="INSS",
               folha_seguranca="810001")
    html = r.get_data(as_text=True)
    assert "não está em branco" in html
    assert _con(s).execute("SELECT COUNT(*) FROM rc_certidoes").fetchone()[0] == 0


def test_sem_escolha_nao_emite_e_preserva_o_estoque(s, monkeypatch):
    """A escolha é obrigatória: o sistema não adivinha o papel físico."""
    import atribuicoes_web as AW
    monkeypatch.setattr(AW.AS, "selar_o_ato_lavrado", _fake_selar_ok)

    assento_id = _semear_assento(s)
    _semear_folhas(s, "820001", "820002")

    r = _emitir(s, assento_id, requerente="A MÃE", finalidade="INSS")
    html = r.get_data(as_text=True)
    assert "Escolha a folha de segurança" in html
    assert _folha(s, "820001")["situacao"] == "EM BRANCO"
    assert _folha(s, "820002")["situacao"] == "EM BRANCO"

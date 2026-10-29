"""Dois cliques no mesmo dinheiro: a conferência mora DENTRO da transação.

A revisão do lote L050 da migração (PostgreSQL nativo) achou o saldo do
depósito prévio lido FORA da transação e gravado DENTRO dela. Entre uma coisa
e outra cabe o segundo clique — o balcão que aperta duas vezes, ou duas telas
abertas no mesmo depósito —, e os dois gastam o mesmo saldo. O manual da
migração pede `SELECT ... FOR UPDATE` quando se lê e grava a mesma linha.

O mesmo desenho estava no estorno (a marca `estornado`), nos dois recibos (a
marca `recibo_id`) e no hash do lançamento manual (o anterior era lido antes
da trava da numeração).

COMO O TESTE ABRE A JANELA: a próxima transação que a rota abrir encontra o
outro clique já gravado e confirmado. Quem leu antes, fora da transação, não o
vê e grava em cima; quem lê dentro dela, com a linha presa, vê.
"""
from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"


# ------------------------------------------------------------- ferramentas

def _token(c, rota: str) -> str:
    html = c.get(rota).get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, f"a tela {rota} não trouxe csrf_token"
    return achado.group(1)


def _outro_clique_antes(monkeypatch, db, outro) -> None:
    """Na próxima transação da rota, o OUTRO clique grava e confirma primeiro.

    `outro` recebe o `Banco` de uma transação própria, que se confirma antes
    de a da rota começar — a janela exata entre a leitura de um clique e a
    gravação do outro.
    """
    original = db.transaction
    pendente = [outro]

    @contextmanager
    def transacao():
        if pendente:
            with original() as con:
                pendente.pop()(banco(con))
        with original() as con:
            yield con

    monkeypatch.setattr(db, "transaction", transacao)


def _um(db, sql: str, params=()):
    with db.connect() as con:
        return banco(con).um(sql, params)


def _abrir_caixa(c) -> None:
    c.post("/caixa", data={"csrf_token": _token(c, "/caixa"), "acao": "abrir",
                           "saldo_inicial": "0,00"}, follow_redirects=True)


def _deposito(c, db, valor: str = "100,00") -> int:
    c.post("/caixa/depositos",
           data={"csrf_token": _token(c, "/caixa/depositos"), "acao": "novo",
                 "depositante": "CONSTRUTORA ALFA LTDA", "valor": valor},
           follow_redirects=True)
    return int(_um(db, "SELECT max(id) AS id FROM cx_depositos")["id"])


def _lancar(c, db, valor: str = "50,00", descricao: str = "ENSAIO") -> int:
    c.post("/caixa", data={"csrf_token": _token(c, "/caixa"), "acao": "lancar",
                           "natureza": "RECEBIMENTO", "valor": valor,
                           "forma_pagamento": "DINHEIRO",
                           "descricao": descricao},
           follow_redirects=True)
    return int(_um(db, "SELECT max(id) AS id FROM cx_lancamentos")["id"])


def _recibo_do_outro_clique(bd, lancamentos: list[int]) -> None:
    """O recibo que o outro clique emitiu, com a marca nos lançamentos."""
    recibo = bd.escrever(
        """INSERT INTO cx_recibos (numero, ano, data_emissao, pagador,
                                   valor_total, criado_em)
           VALUES (1, %s, %s, 'CONSTRUTORA ALFA LTDA', '50,00', %s)
           RETURNING id""",
        (date.today().year, date.today().isoformat(),
         f"{date.today().isoformat()}T09:00:00"))[0]["id"]
    for lid in lancamentos:
        bd.escrever("UPDATE cx_lancamentos SET recibo_id=%s WHERE id=%s",
                    (recibo, lid))


# ------------------------------------------------------- depósito prévio

def test_usar_o_deposito_le_o_saldo_dentro_da_transacao(cg_casa_logada,
                                                       monkeypatch):
    """O outro clique já gastou R$ 60 dos R$ 100. Gastar mais R$ 30 deixa
    R$ 10 — e não os R$ 70 da conta feita com o saldo velho, que devolveria
    ao depositante dinheiro que já foi usado."""
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    did = _deposito(c, db)
    token = _token(c, "/caixa/depositos")
    _outro_clique_antes(monkeypatch, db, lambda bd: bd.escrever(
        "UPDATE cx_depositos SET saldo='40,00' WHERE id=%s", (did,)))

    c.post("/caixa/depositos",
           data={"csrf_token": token, "acao": "usar", "deposito_id": did,
                 "valor_usar": "30,00"}, follow_redirects=True)

    d = _um(db, "SELECT saldo, encerrado FROM cx_depositos WHERE id=%s", (did,))
    assert d["saldo"] == "10,00", \
        "o uso foi calculado com o saldo lido antes do outro clique"
    assert d["encerrado"] == 0


def test_usar_deposito_encerrado_pelo_outro_clique_e_recusado(cg_casa_logada,
                                                              monkeypatch):
    """O outro clique gastou tudo e encerrou. O segundo é recusado com a frase
    de sempre, e o depósito não ressuscita."""
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    did = _deposito(c, db)
    token = _token(c, "/caixa/depositos")
    _outro_clique_antes(monkeypatch, db, lambda bd: bd.escrever(
        "UPDATE cx_depositos SET saldo='0,00', encerrado=1 WHERE id=%s", (did,)))

    r = c.post("/caixa/depositos",
               data={"csrf_token": token, "acao": "usar", "deposito_id": did,
                     "valor_usar": "30,00"}, follow_redirects=True)

    assert "já encerrado" in r.get_data(as_text=True)
    d = _um(db, "SELECT saldo, encerrado FROM cx_depositos WHERE id=%s", (did,))
    assert (d["saldo"], d["encerrado"]) == ("0,00", 1)


def test_devolver_o_deposito_devolve_o_saldo_que_sobrou(cg_casa_logada,
                                                       monkeypatch):
    """Sobraram R$ 40 depois do outro clique: a gaveta paga R$ 40, e não os
    R$ 100 do saldo lido antes."""
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _abrir_caixa(c)
    did = _deposito(c, db)
    token = _token(c, "/caixa/depositos")
    _outro_clique_antes(monkeypatch, db, lambda bd: bd.escrever(
        "UPDATE cx_depositos SET saldo='40,00' WHERE id=%s", (did,)))

    c.post("/caixa/depositos",
           data={"csrf_token": token, "acao": "devolver", "deposito_id": did,
                 "motivo": "desistência do serviço"}, follow_redirects=True)

    devolucao = _um(db, """SELECT valor FROM cx_lancamentos
                            WHERE natureza='DEVOLUCAO' ORDER BY id DESC LIMIT 1""")
    assert devolucao and devolucao["valor"] == "40,00", \
        "a devolução saiu com o saldo lido antes do outro clique"


def test_usar_nao_paga_com_o_deposito_o_item_que_o_outro_clique_ja_quitou(
        cg_casa_logada, monkeypatch):
    """O «usar» passou a quitar o item do protocolo (LD06). O outro balcão
    quitou o item em dinheiro entre a tela e o «usar»: os itens a pagar se
    leem com a linha presa, dentro da transação, e o depósito não paga outra
    vez o que o cliente já pagou."""
    import caixa_protocolo as CXP
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    did = _deposito(c, db)
    with db.transaction() as con:
        bd = banco(con)
        p = CXP.abrir(bd, data_abertura=date.today().isoformat(),
                      agora=f"{date.today().isoformat()}T09:00:00", atribuicao="RI",
                      interessado="CONSTRUTORA ALFA LTDA")
        item = bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   quantidade, valor_total, emolumentos, ferc, fadep, femp, ferrfis)
               VALUES (%s, 'Certidão de ensaio', '16.24.1', 1, '30,00', '27,00',
                       '1,00', '0,70', '0,65', '0,65') RETURNING id""",
            (p["protocolo_id"],))[0]["id"]
    token = _token(c, "/caixa/depositos")
    _outro_clique_antes(monkeypatch, db, lambda bd: bd.escrever(
        """UPDATE cx_protocolo_atos SET quitado=1, quitado_em=%s,
                  quitado_por='OUTRO BALCÃO' WHERE id=%s""",
        (f"{date.today().isoformat()}T09:01:00", item)))

    c.post("/caixa/depositos",
           data={"csrf_token": token, "acao": "usar", "deposito_id": did,
                 "valor_usar": "30,00", "protocolo": p["numero"]},
           follow_redirects=True)

    assert _um(db, "SELECT quitado_por FROM cx_protocolo_atos WHERE id=%s",
               (item,))["quitado_por"] == "OUTRO BALCÃO"
    assert not _um(db, "SELECT id FROM cx_deposito_usos WHERE item_id=%s", (item,)), \
        "o depósito pagou o item que o outro clique já tinha quitado"


def test_reabrir_atrasado_nao_desfaz_o_item_que_o_deposito_acabou_de_pagar(
        cg_casa_logada, monkeypatch):
    """O «reabrir» de uma tela velha chega no mesmo instante em que o «usar»
    do outro balcão quita o item com o depósito (LD06). A conferência do
    «pago pelo depósito» se faz com a linha presa, dentro da transação: lida
    antes, o item pago se reabria, o valor ficava gasto no depósito e o
    cliente pagaria o item de novo."""
    import caixa_protocolo as CXP
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        bd = banco(con)
        p = CXP.abrir(bd, data_abertura=date.today().isoformat(),
                      agora=f"{date.today().isoformat()}T09:00:00", atribuicao="RI",
                      interessado="CONSTRUTORA ALFA LTDA")
        item = bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   quantidade, valor_total)
               VALUES (%s, 'Certidão de ensaio', '16.24.1', 1, '30,00')
               RETURNING id""", (p["protocolo_id"],))[0]["id"]
    rota = f"/caixa/protocolos/{p['protocolo_id']}"
    token = _token(c, rota)
    _outro_clique_antes(monkeypatch, db, lambda bd: bd.escrever(
        """UPDATE cx_protocolo_atos SET quitado=1, quitado_em=%s,
                  quitado_por='DEPÓSITO PRÉVIO DP2026.10.1' WHERE id=%s""",
        (f"{date.today().isoformat()}T09:01:00", item)))

    r = c.post(f"{rota}/itens",
               data={"csrf_token": token, "acao": "desquitar", "item_id": item},
               follow_redirects=True)

    linha = _um(db, "SELECT quitado, quitado_por FROM cx_protocolo_atos WHERE id=%s",
                (item,))
    assert (linha["quitado"], linha["quitado_por"]) == (1, "DEPÓSITO PRÉVIO DP2026.10.1"), \
        "o reabrir conferiu o item antes do outro clique e desfez o pagamento"
    assert "pago com o depósito prévio DP2026.10.1" in r.get_data(as_text=True)


# --------------------------------------------------------------- estorno

def test_o_mesmo_lancamento_nao_se_estorna_duas_vezes(cg_casa_logada,
                                                     monkeypatch):
    """Dois estornos do mesmo lançamento tiram o dinheiro do caixa duas vezes."""
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _abrir_caixa(c)
    lid = _lancar(c, db)
    token = _token(c, "/caixa")

    def outro(bd):
        estorno = bd.escrever(
            """INSERT INTO cx_lancamentos (caixa_id, data, natureza, sentido,
                                           valor, estorna_id, criado_em)
               SELECT caixa_id, data, 'ESTORNO', 'ESTORNO', valor, id, criado_em
                 FROM cx_lancamentos WHERE id=%s
               RETURNING id""", (lid,))[0]["id"]
        bd.escrever("""UPDATE cx_lancamentos SET estornado=1, estornado_por_id=%s
                        WHERE id=%s""", (estorno, lid))
    _outro_clique_antes(monkeypatch, db, outro)

    r = c.post("/caixa", data={"csrf_token": token, "acao": "estornar",
                               "lancamento_id": lid, "motivo": "valor errado"},
               follow_redirects=True)

    assert "já estornado" in r.get_data(as_text=True)
    n = _um(db, "SELECT count(*) AS n FROM cx_lancamentos WHERE estorna_id=%s",
            (lid,))["n"]
    assert n == 1, f"o lançamento foi estornado {n} vezes"


# --------------------------------------------------------------- recibos

def test_o_mesmo_lancamento_nao_sai_em_dois_recibos(cg_casa_logada,
                                                   monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _abrir_caixa(c)
    lid = _lancar(c, db)
    token = _token(c, "/caixa")
    _outro_clique_antes(monkeypatch, db,
                        lambda bd: _recibo_do_outro_clique(bd, [lid]))

    r = c.post(f"/caixa/recibo/{lid}", data={"csrf_token": token})

    n = _um(db, "SELECT count(*) AS n FROM cx_recibos")["n"]
    assert n == 1, "o mesmo lançamento saiu em dois recibos"
    assert "já tem recibo" in c.get(r.headers["Location"]).get_data(as_text=True)


def test_o_mesmo_atendimento_nao_sai_em_dois_recibos(cg_casa_logada,
                                                    monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _abrir_caixa(c)
    c.post("/caixa/protocolos",
           data={"csrf_token": _token(c, "/caixa/protocolos"), "acao": "novo",
                 "interessado": "CONSTRUTORA ALFA LTDA",
                 "telefone": "(99) 90000-0000", "atribuicao": "OUTROS"},
           follow_redirects=True)
    pid = int(_um(db, "SELECT max(id) AS id FROM cx_protocolos")["id"])
    with db.transaction() as con:
        item = banco(con).escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   quantidade, valor_total, emolumentos, ferc, fadep, femp,
                   ferrfis, quitado)
               VALUES (%s, 'Autenticação de cópia', '13.18', 1, '18,51',
                       '16,50', '0,60', '0,45', '0,48', '0,48', 0)
               RETURNING id""", (pid,))[0]["id"]
    rota = f"/caixa/protocolos/{pid}"
    c.post(f"{rota}/itens", data={"csrf_token": _token(c, rota),
                                  "acao": "quitar", "item_id": item},
           follow_redirects=True)
    lancamentos = [int(_um(db, """SELECT lancamento_id FROM cx_protocolo_atos
                                   WHERE id=%s""", (item,))["lancamento_id"])]
    token = _token(c, rota)
    _outro_clique_antes(monkeypatch, db,
                        lambda bd: _recibo_do_outro_clique(bd, lancamentos))

    r = c.post(f"{rota}/recibo", data={"csrf_token": token})

    n = _um(db, "SELECT count(*) AS n FROM cx_recibos")["n"]
    assert n == 1, "o mesmo dinheiro saiu em dois recibos"
    assert "já estão num recibo" in \
        c.get(r.headers["Location"]).get_data(as_text=True)


# ------------------------------------------------- o hash do lançamento

def test_o_hash_do_lancamento_encadeia_no_ultimo_gravado(cg_casa_logada,
                                                        monkeypatch):
    """O hash anterior se lê depois da trava da numeração: lido antes, dois
    lançamentos simultâneos encadeavam no mesmo anterior."""
    from caixa_schema import hash_lancamento

    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _abrir_caixa(c)
    caixa_id = int(_um(db, "SELECT max(id) AS id FROM cx_caixas")["id"])
    token = _token(c, "/caixa")
    _outro_clique_antes(monkeypatch, db, lambda bd: bd.escrever(
        """INSERT INTO cx_lancamentos (caixa_id, data, natureza, sentido, valor,
                                       hash_lancamento, criado_em)
           VALUES (%s, %s, 'RECEBIMENTO', 'ENTRADA', '10,00', 'HASH-DO-OUTRO',
                   %s)""",
        (caixa_id, date.today().isoformat(),
         f"{date.today().isoformat()}T09:00:00")))

    c.post("/caixa", data={"csrf_token": token, "acao": "lancar",
                           "natureza": "RECEBIMENTO", "valor": "50,00",
                           "forma_pagamento": "DINHEIRO",
                           "descricao": "ENSAIO"}, follow_redirects=True)

    gravado = _um(db, """SELECT hash_lancamento FROM cx_lancamentos
                          ORDER BY id DESC LIMIT 1""")["hash_lancamento"]
    assert gravado == hash_lancamento(caixa_id, date.today().isoformat(),
                                      "RECEBIMENTO", "50,00", "ENSAIO",
                                      "HASH-DO-OUTRO"), \
        "o hash encadeou num anterior lido antes da trava"

"""SELO RECUSADO SUSPENDE O ATO, E ELE VOLTA A SER MINUTA — 16/09/2026.

    «selo recusado suspende ato (fica salvo como minuta para lavrar de
     novo)» — o oficial

ISTO INVERTE UMA REGRA ESCRITA DESDE AGOSTO, e a inversão é dele, com os
fatos na mão. O que a regra antiga — «selo recusado não derruba ato que já
existe» — produziu está medido: os AV-04, AV-05 e AV-06 da matrícula 3.110
nasceram lavrados e **sem selo**, entraram na corrente de hash, um deles
encerrou a ficha, e desfazer aquilo custou três ferramentas e dois dias.

E NÃO É O CANCELAMENTO QUE ELE JÁ RECUSOU EM 15/09. Ali o ato **ficava** no
livro marcado como cancelado — «ato cancelado não se descancela sozinho».
Aqui ele **não chega a ficar**: volta a ser minuta, com o teor, a
qualificação e as **partes**, e se lavra de novo quando o aparelho voltar.

O QUE MUDA NO BALCÃO, e ele sabe: **um ato só existe depois de o selo sair.**
Com o selador fora do ar não se lavra — e por isso a marca `lavrar_sem_selo`
continua de pé, para quem decide seguir assim mesmo.

A PRECONDIÇÃO QUE ISTO TINHA, e que custou um relato dele. `ri_minutas` não
    guardava partes: a AV-05 voltou para a fila só com o teor, foi relavrada
    sem dono, e o envelope recusou — «Os nomes das partes devem ser
    informados». Sem `ri_minuta_partes`, a suspensão faria o ato renascer sem
    partes, o selo falhar pelo mesmo motivo, **e o círculo não fecharia
    nunca**.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_minuta as RIMIN

TEOR = ("AV-05/3.110 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE 2o GRAU, "
        "conforme o titulo apresentado nesta serventia.")


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero="3110"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2-Q', '2-Q', 'ATIVO', 'ACERVO', '2026-09-14T10:27')""",
        (numero,))
    return int(cur.lastrowid)


def _ato(con, mid, *, numero=5, selo=None, hash_ato="hash-de-mentira"):
    cur = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
               natureza_titulo, protocolo, selo_texto, hash_ato, origem,
               lavrado_em)
           VALUES (?, 'AV', ?, '2026-09-14', ?, 'Anuencia para baixa', '11571',
                   ?, ?, 'MANUAL', '2026-09-14T22:43:07')""",
        (mid, numero, TEOR, selo, f"{hash_ato}-{numero}"))
    ato_id = int(cur.lastrowid)
    for nome, doc in (("BANCO DO BRASIL S.A", "00000010000127"),
                      ("IRENE ANDRADE MACHADO CARDOSO", "12345678901")):
        con.execute(
            """INSERT INTO ri_partes (matricula_id, ato_id, nome, nome_norm,
                   documento_tipo, documento_numero, documento_valido,
                   papel, proprietario, proprietario_ativo, origem)
               VALUES (?,?,?,?,?,?,0,'credor',0,0,'MANUAL')""",
            (mid, ato_id, nome, nome, "CNPJ" if len(doc) > 11 else "CPF", doc))
    return ato_id


# ------------------------------------------------- o ato volta, com as partes


def test_o_ato_suspenso_vira_minuta_COM_as_partes(cg_casa):
    """É a precondição que faltava, e ela custou um relato do oficial."""
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        ato_id = _ato(con, mid)
        r = RIMIN.voltar_do_ato(con, ato_id, agora="2026-09-16T10:30",
                                por="MARIO", motivo="o aparelho não respondeu")

    assert r["rotulo"] == "AV-05"
    assert r["partes"] == 2, "as partes do ato não foram para a minuta"
    assert not r["reaproveitou"], "não havia minuta de origem"

    mi = con.execute("SELECT * FROM ri_minutas WHERE id=?",
                     (r["minuta_id"],)).fetchone()
    assert mi["situacao"] == RIMIN.A_REVISAR
    assert mi["ato_id"] is None
    assert mi["teor"] == TEOR, "o texto tinha de sobreviver inteiro"
    assert mi["natureza_titulo"] == "Anuencia para baixa", (
        "a qualificação se perdeu, e ela é justamente o que o selo exige")
    assert mi["numero_pretendido"] == 5
    assert "o aparelho não respondeu" in (mi["observacao"] or "")

    partes = RIMIN.partes(con, r["minuta_id"])
    assert [p["nome"] for p in partes] == [
        "BANCO DO BRASIL S.A", "IRENE ANDRADE MACHADO CARDOSO"]
    assert partes[0]["documento_numero"] == "00000010000127"

    # E O ATO NAO EXISTE MAIS — nem lavrado, nem cancelado no livro.
    assert not list(con.execute("SELECT 1 FROM ri_atos WHERE id=?", (ato_id,)))
    assert not list(con.execute("SELECT 1 FROM ri_partes WHERE ato_id=?",
                                (ato_id,)))
    con.close()


def test_a_minuta_de_origem_volta_em_vez_de_nascer_outra(cg_casa):
    """Duas minutas para o mesmo ato e quem abre não sabe qual revisar."""
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        minuta_id = RIMIN.criar(
            con, matricula_id=mid, tipo="AV", numero_pretendido=5, teor=TEOR,
            agora="2026-09-15T08:00", origem=RIMIN.IMPORTACAO,
            origem_chave="minutas para finalizar/AV-05.docx")
        ato_id = _ato(con, mid)
        RIMIN.marcar_lavrada(con, minuta_id, ato_id=ato_id,
                             agora="2026-09-15T09:00")
        r = RIMIN.voltar_do_ato(con, ato_id, agora="2026-09-16T10:30",
                                por="MARIO", motivo="sem rede")

    assert r["reaproveitou"] is True
    assert r["minuta_id"] == minuta_id
    quantas = con.execute(
        "SELECT COUNT(*) FROM ri_minutas WHERE matricula_id=?",
        (mid,)).fetchone()[0]
    assert quantas == 1, "nasceu uma segunda minuta para a mesma AV-05"
    con.close()


# ------------------------------------------------------------- as recusas


def test_ato_com_selo_nao_se_suspende(cg_casa):
    """Selo pago amarrado a ato que deixa de existir é selo órfão."""
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        ato_id = _ato(con, mid, selo="AVESVD000000IFWIQRMJW7CGUA95")
    with pytest.raises(RIMIN.MinutaError, match="selo"):
        with con:
            RIMIN.voltar_do_ato(con, ato_id, agora="2026-09-16T10:30")
    assert list(con.execute("SELECT 1 FROM ri_atos WHERE id=?", (ato_id,))), (
        "o ato com selo tinha de continuar de pé")
    con.close()


def test_so_a_cauda_da_corrente_se_suspende(cg_casa):
    """Tirar do meio deixaria o seguinte apontando para um hash que sumiu."""
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        primeiro = _ato(con, mid, numero=4)
        _ato(con, mid, numero=5)
    with pytest.raises(RIMIN.MinutaError, match="último"):
        with con:
            RIMIN.voltar_do_ato(con, primeiro, agora="2026-09-16T10:30")
    con.close()


def test_ato_com_dinheiro_no_caixa_nao_se_suspende(cg_casa):
    """Dinheiro que entrou sai por estorno, que deixa rastro."""
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        ato_id = _ato(con, mid)
        # AS COLUNAS SAO AS MEDIDAS, e nao as que eu supus: a primeira
        # versao deste teste escreveu `tipo`, que **nao existe** — as reais
        # sao `natureza` e `sentido`. «Nome plausivel e o que mais se parece
        # com medicao sem ser», e desta vez foi no meu proprio teste.
        con.execute(
            """INSERT INTO cx_lancamentos (data, natureza, sentido, descricao,
                   valor, estornado, origem, origem_chave, criado_em,
                   excluido)
               VALUES ('2026-09-14','RECEBIMENTO','ENTRADA','averbacao',
                       '102,15',0,'ATO',?,'2026-09-14T22:43',0)""",
            (f"ri_atos:{ato_id}:16.22.2",))
    with pytest.raises(RIMIN.MinutaError, match="caixa"):
        with con:
            RIMIN.voltar_do_ato(con, ato_id, agora="2026-09-16T10:30")
    con.close()


# ------------------------------------------- a unidade do protocolo volta


def test_a_unidade_do_protocolo_volta_ao_suspender(cg_casa):
    """Senão o cliente paga cinco averbações e o balcão oferece quatro."""
    import caixa_protocolo as CXPROT

    con = _con(cg_casa)
    with con:
        cur = con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, situacao,
                   finalizado, gratuito, deposito_previo, origem, criado_em,
                   tipo)
               VALUES ('2026.09.23','2026-09-14','A_PAGAR',0,0,'0,00',
                       'MANUAL','2026-09-14T09:00','IMOVEL')""")
        prot = int(cur.lastrowid)
        cur = con.execute(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao,
                   codigo_ato, quantidade, quantidade_usada, usado_em,
                   usado_por_ato_id, usado_por_tabela)
               VALUES (?, 'De ato sem valor declarado', '16.22.2', 5, 2,
                       '2026-09-15T17:34:08', 99, 'ri_atos')""", (prot,))
        item = int(cur.lastrowid)

        voltaram = CXPROT.devolver_item(con, item, quantas=1)
    assert voltaram == 1
    r = con.execute("""SELECT quantidade, quantidade_usada, usado_por_ato_id
                         FROM cx_protocolo_atos WHERE id=?""",
                    (item,)).fetchone()
    assert r["quantidade_usada"] == 1
    assert r["usado_por_ato_id"] == 99, (
        "o rastro de quem ABRIU o consumo não se apaga enquanto sobra unidade")
    con.close()


def test_nunca_devolve_mais_do_que_foi_gasto(cg_casa):
    """Devolver a mais daria ao balcão averbação que ninguém pagou."""
    import caixa_protocolo as CXPROT

    con = _con(cg_casa)
    with con:
        cur = con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, situacao,
                   finalizado, gratuito, deposito_previo, origem, criado_em,
                   tipo)
               VALUES ('2026.09.24','2026-09-14','A_PAGAR',0,0,'0,00',
                       'MANUAL','2026-09-14T09:00','IMOVEL')""")
        prot = int(cur.lastrowid)
        cur = con.execute(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao,
                   codigo_ato, quantidade, quantidade_usada)
               VALUES (?, 'item', '16.2', 5, 1)""", (prot,))
        item = int(cur.lastrowid)
        assert CXPROT.devolver_item(con, item, quantas=9) == 1
    r = con.execute("""SELECT quantidade_usada, usado_em, usado_por_ato_id
                         FROM cx_protocolo_atos WHERE id=?""",
                    (item,)).fetchone()
    assert r["quantidade_usada"] == 0
    assert r["usado_em"] is None, (
        "item sem unidade gasta com `usado_em` preenchido é o carimbo que "
        "mente — e `_usadas` o leria como uma unidade gasta")
    con.close()


# ------------------------------------------------------ o módulo continua limpo


def test_o_modulo_da_minuta_continua_nao_lavrando():
    proibidas = ("lavrar", "selar", "numerar", "cobrar", "obter_selo",
                 "emitir", "encerrar_matricula")
    achados = [n for n in dir(RIMIN) if not n.startswith("_")
               and any(p in n.lower() for p in proibidas)]
    assert not achados, achados


def test_a_rota_suspende_em_vez_de_deixar_o_ato_lavrado():
    """A régua é o código, e não a prosa: o comentário cita a regra antiga."""
    import ast

    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    arvore = ast.parse(codigo)
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Attribute) and n.attr == "voltar_do_ato"]
    assert chamadas, (
        "a rota de lavrar deixou de suspender o ato quando o selo não sai")

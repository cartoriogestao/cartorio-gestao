"""
Testes de RCPJ e RTD — abrir registro, averbar, cancelar, ligados ao nucleo.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - abrir registro exige serie conhecida de RCPJ ou RTD, e a atribuicao
        vem da serie, nunca de parametro solto;
      - cada ato — registro, averbacao, cancelamento — ocupa FOLHA PROPRIA,
        porque as series sao folha_nova (medido em tbTD_Propriedade);
      - carga repetivel: a mesma (origem, origem_chave) nao duplica;
      - so se averba ou cancela registro ATIVO; nao ha cancelamento de
        cancelamento.
"""
from __future__ import annotations

import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import banco_pg                                  # noqa: E402
import bd_nativo                                 # noqa: E402
import rg_registro as RG                         # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rg_schema import init_rg_schema             # noqa: E402

AGORA = "2026-08-24T09:00:00"
EXTENSO = "vinte e quatro dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    # `rg_titulos` aponta para `cx_protocolos` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria o caixa antes. Aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY)")
    init_rg_schema(con)
    return con


# --------------------------------------------------------------- o registro


def test_abre_registro_de_rcpj():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", natureza="Estatuto de associação",
                          requerente_nome="ASSOCIAÇÃO X", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, teor="Texto do estatuto.")
    assert r["numero_ordem"] == 1
    assert r["folha"] == 1
    reg = RG.registro(con, r["registro_id"])
    assert reg["atribuicao"] == 3
    assert reg["situacao"] == "ATIVO"
    assert reg["numero"] == 1


def test_abre_registro_de_rtd():
    con = banco()
    r = RG.abrir_registro(con, serie="TD_B", natureza="Contrato particular",
                          sv=SV, agora=AGORA, data_extenso=EXTENSO)
    reg = RG.registro(con, r["registro_id"])
    assert reg["atribuicao"] == 4


def test_serie_desconhecida_e_recusada():
    con = banco()
    with pytest.raises(RG.RgError, match="não é de RCPJ nem de RTD"):
        RG.abrir_registro(con, serie="RC_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)


def test_cada_registro_ocupa_folha_propria():
    # PJ_A e folha_nova: o segundo registro vai para a folha 2, nao continua
    # na folha do primeiro — ao contrario da matricula do RI.
    con = banco()
    r1 = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    r2 = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    assert r1["folha"] == 1
    assert r2["folha"] == 2


def test_carga_e_repetivel_por_construcao():
    con = banco()
    r1 = RG.abrir_registro(con, serie="PJ_A", origem="EOFICIO",
                           origem_chave="ACERVO:123", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    r2 = RG.abrir_registro(con, serie="PJ_A", origem="EOFICIO",
                           origem_chave="ACERVO:123", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    assert r1["registro_id"] == r2["registro_id"]
    assert r2["reaproveitado"] is True
    assert con.execute("SELECT COUNT(*) n FROM rg_registros").fetchone()["n"] == 1


def test_registro_de_eoficio_sem_chave_e_recusado():
    con = banco()
    with pytest.raises(RG.RgError, match="chave de origem"):
        RG.abrir_registro(con, serie="PJ_A", origem="EOFICIO", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO)


# -------------------------------------------------------------- a averbacao


def test_lanca_averbacao_em_folha_propria():
    con = banco()
    r = RG.abrir_registro(con, serie="TD_C", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    av = RG.lancar_averbacao(con, r["registro_id"],
                             teor="Averbação de alteração de endereço.",
                             sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert av["folha"] == 2
    atos = RG.atos_do(con, r["registro_id"])
    assert [a["tipo"] for a in atos] == ["REGISTRO", "AVERBACAO"]


def test_averbacao_exige_teor():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="dez letras"):
        RG.lancar_averbacao(con, r["registro_id"], teor="curto", sv=SV,
                            agora=AGORA, data_extenso=EXTENSO)


def test_nao_averba_registro_cancelado():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    RG.lancar_cancelamento(con, r["registro_id"], motivo="Erro na inscrição.",
                           sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="só se averba registro ativo"):
        RG.lancar_averbacao(con, r["registro_id"], teor="Nova averbação.",
                            sv=SV, agora=AGORA, data_extenso=EXTENSO)


# ---------------------------------------------------------- o cancelamento


def test_cancela_registro_ativo():
    con = banco()
    r = RG.abrir_registro(con, serie="TD_F", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    RG.lancar_cancelamento(con, r["registro_id"], motivo="Erro na inscrição.",
                           sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert RG.registro(con, r["registro_id"])["situacao"] == "CANCELADO"


def test_cancelamento_exige_motivo():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_B", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="dez letras"):
        RG.lancar_cancelamento(con, r["registro_id"], motivo="erro", sv=SV,
                               agora=AGORA, data_extenso=EXTENSO)


def test_nao_cancela_duas_vezes():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_B", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    RG.lancar_cancelamento(con, r["registro_id"], motivo="Erro na inscrição.",
                           sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="já está com situação"):
        RG.lancar_cancelamento(con, r["registro_id"],
                               motivo="Segunda tentativa de cancelar.",
                               sv=SV, agora=AGORA, data_extenso=EXTENSO)


# -------------------------------------------------------- a regra medida


def test_averbacao_consome_protocolo_so_no_rtd():
    # Fato medido em LEVANTAMENTO_QUATRO_ATRIBUICOES.md — ainda nao vira
    # comportamento (nao ha integracao com o protocolo geral), mas a regra
    # tem de estar certa quando a integracao vier.
    assert RG.AVERBACAO_CONSOME_PROTOCOLO[3] is False   # RCPJ
    assert RG.AVERBACAO_CONSOME_PROTOCOLO[4] is True    # RTD


# ------------------------------------------ quando a ponte sair (as travas)
#
# Com a ponte, a transação da rota já pega a trava única do banco, e nada
# grava ao mesmo tempo. Estes testes usam conexões do psycopg SEM a ponte,
# como a transação vai ficar quando ela sair (revisão do L018).


def _psycopg_puro(con, *, autocommit=False):
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{con.schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def _ao_mesmo_tempo(con, primeiro, segundo) -> dict:
    """`primeiro` grava e ainda não confirmou; `segundo` chega no meio, por
    outra conexão. Devolve {"r": o que o segundo devolveu} ou {"erro": ...}."""
    um, dois = _psycopg_puro(con), _psycopg_puro(con)
    vigia = _psycopg_puro(con, autocommit=True)
    pid = bd_nativo.banco(dois).valor("SELECT pg_backend_pid() AS pid")
    primeiro(um)
    saida: dict = {}

    def chega_no_meio():
        try:
            saida["r"] = segundo(dois)
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            dois.rollback()

    fio = threading.Thread(target=chega_no_meio)
    fio.start()
    for _ in range(200):          # o segundo tem de estar ESPERANDO
        if bd_nativo.banco(vigia).valor(
                "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)):
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    return saida


def test_duas_cargas_da_mesma_chave_ao_mesmo_tempo_reaproveitam():
    """«Já entrou?» e o INSERT, sem trava: a segunda carga passava pela
    conferência e batia no UNIQUE(origem, origem_chave) — erro, e não o
    «reaproveitado» que a carga repetível promete."""
    con = banco()
    con.commit()

    def carga(c):
        return RG.abrir_registro(c, serie="TD_B", sv=SV, agora=AGORA,
                                 data_extenso=EXTENSO, origem="EOFICIO",
                                 origem_chave="tbRegistroTD:991")

    saida = _ao_mesmo_tempo(con, carga, carga)
    assert "erro" not in saida, saida
    assert saida["r"]["reaproveitado"] is True
    assert con.execute(
        "SELECT count(*) AS n FROM rg_registros WHERE origem_chave=?",
        ("tbRegistroTD:991",)).fetchone()["n"] == 1


def test_averbacao_que_chega_durante_o_cancelamento_e_recusada():
    """A situação se confere com a linha presa: sem isso, a averbação lia
    ATIVO, esperava só a trava do lugar no livro e entrava no registro que o
    cancelamento acabara de cancelar."""
    con = banco()
    rid = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                            data_extenso=EXTENSO,
                            teor="Estatuto.")["registro_id"]
    con.commit()
    saida = _ao_mesmo_tempo(
        con,
        lambda c: RG.lancar_cancelamento(
            c, rid, motivo="Pedido do próprio interessado.", sv=SV,
            agora=AGORA, data_extenso=EXTENSO),
        lambda c: RG.lancar_averbacao(
            c, rid, teor="Alteração do endereço da sede.", sv=SV,
            agora=AGORA, data_extenso=EXTENSO))
    assert isinstance(saida.get("erro"), RG.RgError), saida
    assert "CANCELADO" in str(saida["erro"])
    assert [a["tipo"] for a in RG.atos_do(con, rid)] == [
        "REGISTRO", "CANCELAMENTO"]


def test_a_correcao_do_requerente_cita_o_nome_que_havia_antes_dela():
    """A auditoria mostra o nome de ANTES ao lado do de depois. Sem a linha
    presa, a segunda correção citava o nome que a primeira já tinha trocado."""
    con = banco()
    rid = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                            data_extenso=EXTENSO,
                            requerente_nome="ASSOCIAÇÃO X")["registro_id"]
    con.commit()
    saida = _ao_mesmo_tempo(
        con,
        lambda c: RG.corrigir_requerente(
            c, rid, requerente_nome="ASSOCIAÇÃO Y", requerente_documento=None,
            motivo="Mudança de nome já averbada."),
        lambda c: RG.corrigir_requerente(
            c, rid, requerente_nome="ASSOCIAÇÃO Z", requerente_documento=None,
            motivo="Erro de digitação no nome novo."))
    assert "erro" not in saida, saida
    assert saida["r"]["requerente_nome_antes"] == "ASSOCIAÇÃO Y"


# ------------------------------- as declarações do termo do livro (LD09)


def _declaracoes_gravadas(con, ato_id: int):
    """O que a lavratura gravou no ato — o JSON lido de volta, ou None."""
    import json
    bruto = bd_nativo.banco(con).valor(
        "SELECT declaracoes FROM rg_atos WHERE id=%s", (int(ato_id),))
    return json.loads(bruto) if bruto else None


def test_o_extrato_do_livro_c_fica_gravado_no_ato_de_registro():
    """LRP art. 143: o registro por extrato declara o valor, o prazo, as
    partes… A declaração vai para o ATO, limpa do espaço repetido; a que veio
    em branco não se grava (o termo não imprime rótulo sem valor)."""
    con = banco()
    r = RG.abrir_registro(
        con, serie="TD_C", natureza="Contrato de locação", sv=SV, agora=AGORA,
        data_extenso=EXTENSO,
        declaracoes={"valor": "  R$ 1.000,00 ", "prazo": "",
                     "partes": "LOCADOR: FULANO DE EXEMPLO;\n  LOCATÁRIA: BELTRANA DE EXEMPLO"})
    assert _declaracoes_gravadas(con, r["ato_id"]) == {
        "valor": "R$ 1.000,00",
        "partes": "LOCADOR: FULANO DE EXEMPLO; LOCATÁRIA: BELTRANA DE EXEMPLO"}


def test_o_registro_sem_declaracao_se_grava_como_antes():
    """O Livro B traslada, e não declara: o ato dele não ganha nada."""
    con = banco()
    r = RG.abrir_registro(con, serie="TD_B", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, declaracoes={"valor": "  "})
    assert _declaracoes_gravadas(con, r["ato_id"]) is None


@pytest.mark.parametrize("serie,declaracao", [
    ("PJ_B", {"denominacao": "ASSOCIAÇÃO DE EXEMPLO"}),   # do Livro A, no B
    ("TD_B", {"valor": "R$ 1,00"}),                       # do Livro C, no B
    ("PJ_A", {"inventada": "qualquer coisa"}),            # de livro nenhum
])
def test_a_declaracao_de_outro_livro_e_recusada_antes_de_gastar_numero(serie, declaracao):
    """Quem preencheu o quadro do Livro A e escolheu o B perderia, calado, o que
    escreveu. A recusa vem ANTES do número: o registro seguinte do livro é o 1."""
    con = banco()
    with pytest.raises(RG.RgError, match="nada foi lavrado"):
        RG.abrir_registro(con, serie=serie, sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, declaracoes=declaracao)
    assert bd_nativo.banco(con).valor("SELECT count(*) AS n FROM rg_atos") == 0
    r = RG.abrir_registro(con, serie=serie, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert r["numero_ordem"] == 1


def test_o_termo_le_o_protocolo_do_titulo_e_as_declaracoes_do_ato():
    """`dados_do_termo`: o registro declara o protocolo do título (LRP art. 136)
    e as declarações gravadas; a averbação, o número de ordem dela (arts. 149
    e 153); o registro sem título não inventa protocolo."""
    con = banco()
    bd = bd_nativo.banco(con)
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO,
                          declaracoes={"denominacao": "ASSOCIAÇÃO DE EXEMPLO"})
    ato = bd.um("SELECT * FROM rg_atos WHERE id=%s", (r["ato_id"],))
    reg = RG.registro(con, r["registro_id"])
    assert RG.dados_do_termo(con, ato, reg) == {
        "declaracoes": {"denominacao": "ASSOCIAÇÃO DE EXEMPLO"}}
    tid = bd.escrever(
        """INSERT INTO rg_titulos(atribuicao, numero, data_apresentacao,
               apresentante, criado_em)
           VALUES (3, 7, '2026-10-02', 'SICRANO APRESENTANTE DE EXEMPLO', %s)
           RETURNING id""", (AGORA,))[0]["id"]
    bd.escrever("UPDATE rg_registros SET titulo_id=%s WHERE id=%s",
                (tid, r["registro_id"]))
    reg = RG.registro(con, r["registro_id"])
    assert RG.dados_do_termo(con, ato, reg) == {
        "protocolo": "7", "data_protocolo": "02/10/2026",
        "apresentante": "SICRANO APRESENTANTE DE EXEMPLO",
        "declaracoes": {"denominacao": "ASSOCIAÇÃO DE EXEMPLO"}}
    av = RG.lancar_averbacao(con, r["registro_id"], teor="Ata de eleição da diretoria.",
                             sv=SV, agora=AGORA, data_extenso=EXTENSO)
    ato_av = bd.um("SELECT * FROM rg_atos WHERE id=%s", (av["ato_id"],))
    assert RG.dados_do_termo(con, ato_av, reg) == {"numero_averbacao": "2"}

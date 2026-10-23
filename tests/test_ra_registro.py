"""
Testes do Registro Auxiliar — o Livro 3 do RI.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - o numero sai do contador do RI (`ri_numeracao`, livro '3'), e NAO de
        uma segunda fonte propria — duas fontes para o mesmo numero e o
        defeito de 18/08/2026;
      - o contador ANDA a cada registro: sem isso o segundo registro nasceria
        com o numero do primeiro, porque os registros do Livro 3 nao moram em
        `ri_matriculas`, de onde `ri_correcoes` le;
      - o Livro 3 conta SEPARADO do Livro 2 — sao series distintas;
      - o numero do ato e continuo entre registro e averbacao: R-1, AV-2;
      - o cancelamento e uma AVERBACAO, e nao um apagamento.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ra_registro as RA                         # noqa: E402
from ra_schema import init_ra_schema             # noqa: E402
from ri_schema import init_ri_schema             # noqa: E402

AGORA = "2026-08-24T09:00:00"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    # `ri_schema` aponta para `users` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria `users` antes. Aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    init_ri_schema(con)      # o Livro 3 conta pelo contador do RI
    init_ra_schema(con)
    # O TEOR DO CANCELAMENTO VEM DA BASE DOS MODELOS desde o LF06B (19/10/2026):
    # `ra_registro.cancelar` lê a frase pela busca única, que olha o ajuste da
    # casa em `mo_elementos`. A casa sempre tem a tabela (o `database.init_db`
    # a cria); este banco de bancada, não. Sem ela, nos testes de psycopg puro
    # logo abaixo, o SELECT que falha aborta a transação de quem cancela.
    from modelos_elementos_schema import init_modelos_elementos_schema
    init_modelos_elementos_schema(con)
    return con


def cedula(con, **kw):
    kw.setdefault("natureza", "CEDULA_CREDITO_RURAL")
    kw.setdefault("titulo_tipo", "Cédula Rural Pignoratícia e Hipotecária")
    return RA.registrar(con, agora=AGORA, **kw)


# ------------------------------------------------------------- registrar


def test_registra_cedula_de_credito_rural():
    con = banco()
    r = cedula(con, titulo_numero="40/01800-8", valor="299809.50", parcelas=6,
               vencimento_final="2028-05-10", juros="9,00")
    assert r["numero"] == 1
    assert r["rotulo"] == "R-1"
    reg = RA.registro(con, r["registro_id"])
    assert reg["livro"] == "3"
    assert reg["valor_centavos"] == 29980950
    assert reg["parcelas"] == 6
    assert reg["situacao"] == "ATIVO"


def test_natureza_fora_do_catalogo_e_recusada():
    con = banco()
    with pytest.raises(RA.RaError, match="não é do Livro 3"):
        RA.registrar(con, natureza="COMPRA_E_VENDA", agora=AGORA)


def test_registro_de_eoficio_sem_chave_e_recusado():
    con = banco()
    with pytest.raises(RA.RaError, match="chave de origem"):
        cedula(con, origem="EOFICIO")


def test_carga_e_repetivel_por_construcao():
    con = banco()
    a = cedula(con, origem="EOFICIO", origem_chave="ACERVO:1549")
    b = cedula(con, origem="EOFICIO", origem_chave="ACERVO:1549")
    assert a["registro_id"] == b["registro_id"]
    assert b["reaproveitado"] is True
    assert con.execute("SELECT COUNT(*) n FROM ra_registros").fetchone()["n"] == 1


def test_as_partes_entram_com_o_registro():
    con = banco()
    r = cedula(con, partes=[
        {"nome": "JOÃO DA SILVA", "documento_tipo": "CPF",
         "documento_numero": "12345678901", "papel": "emitente"},
        {"nome": "BANCO DO BRASIL SA", "documento_tipo": "CNPJ",
         "documento_numero": "00000010000127", "papel": "credor"},
    ])
    partes = RA.partes_do(con, r["registro_id"])
    assert [p["papel"] for p in partes] == ["emitente", "credor"]


# ------------------------------------------------------------ a numeracao


def test_o_contador_anda_e_o_segundo_registro_nao_repete_numero():
    # Os registros do Livro 3 nao moram em ri_matriculas, de onde
    # ri_correcoes le. Sem consumir o contador, os dois sairiam com 1.
    con = banco()
    assert cedula(con)["numero"] == 1
    assert cedula(con)["numero"] == 2
    assert cedula(con)["numero"] == 3


def test_o_numero_respeita_a_semente_do_contador_do_ri():
    # O acervo desta casa tem o livro 3 em 1.650 em uso. Semeado assim, o
    # proximo registro e o 1.651 — e nao o 1.
    con = banco()
    con.execute(
        """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
               observacao) VALUES ('3', 1651, 1650, 'semeado do acervo')""")
    assert cedula(con)["numero"] == 1651
    assert cedula(con)["numero"] == 1652


def test_o_livro_3_conta_separado_do_livro_2():
    # Series distintas: `ri_correcoes.serie_do_livro`. O Livro 2 em 4.014 nao
    # empurra o Livro 3.
    con = banco()
    con.execute(
        """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
               observacao) VALUES ('2', 4015, 4014, 'do acervo')""")
    assert cedula(con)["numero"] == 1


def test_proximo_numero_so_le():
    con = banco()
    antes = RA.proximo_numero(con)
    assert RA.proximo_numero(con) == antes
    assert con.execute("SELECT COUNT(*) n FROM ra_registros").fetchone()["n"] == 0


# --------------------------------------------------------------- averbar


def test_o_numero_do_ato_e_continuo_entre_registro_e_averbacao():
    con = banco()
    r = cedula(con)
    av = RA.averbar(con, r["registro_id"], teor="Averbação de prorrogação.",
                    agora=AGORA)
    assert av["rotulo"] == "AV-2"
    av2 = RA.averbar(con, r["registro_id"], teor="Averbação de liquidação.",
                     agora=AGORA)
    assert av2["rotulo"] == "AV-3"
    atos = RA.atos_do(con, r["registro_id"])
    assert [(a["tipo"], a["numero"]) for a in atos] == [("R", 1), ("AV", 2), ("AV", 3)]


def test_averbacao_exige_teor():
    con = banco()
    r = cedula(con)
    with pytest.raises(RA.RaError, match="dez letras"):
        RA.averbar(con, r["registro_id"], teor="curto", agora=AGORA)


def test_averbacao_com_natureza_fora_do_catalogo_e_recusada():
    con = banco()
    r = cedula(con)
    with pytest.raises(RA.RaError, match="não é do Livro 3"):
        RA.averbar(con, r["registro_id"], teor="Averbação qualquer aqui.",
                   natureza="COMPRA_E_VENDA", agora=AGORA)


def test_nao_averba_registro_cancelado():
    con = banco()
    r = cedula(con)
    RA.cancelar(con, r["registro_id"], motivo="Liquidação integral da cédula.",
                agora=AGORA)
    with pytest.raises(RA.RaError, match="só se averba registro ativo"):
        RA.averbar(con, r["registro_id"], teor="Nova averbação.", agora=AGORA)


# ---------------------------------------------------------- o cancelamento


def test_o_cancelamento_e_uma_averbacao_e_nao_um_apagamento():
    con = banco()
    r = cedula(con)
    c = RA.cancelar(con, r["registro_id"],
                    motivo="Liquidação integral da cédula.", agora=AGORA)
    assert c["rotulo"] == "AV-2"
    assert RA.registro(con, r["registro_id"])["situacao"] == "CANCELADO"
    ato = next(a for a in RA.atos_do(con, r["registro_id"]) if a["numero"] == 2)
    assert ato["motivo_cancelamento"] == "Liquidação integral da cédula."
    # o registro continua na ficha
    assert RA.por_numero(con, r["numero"]) is not None


def test_cancelamento_exige_motivo():
    con = banco()
    r = cedula(con)
    with pytest.raises(RA.RaError, match="dez letras"):
        RA.cancelar(con, r["registro_id"], motivo="pago", agora=AGORA)


def test_nao_cancela_duas_vezes():
    con = banco()
    r = cedula(con)
    RA.cancelar(con, r["registro_id"], motivo="Liquidação integral.", agora=AGORA)
    with pytest.raises(RA.RaError, match="já está com situação"):
        RA.cancelar(con, r["registro_id"], motivo="Segunda tentativa aqui.",
                    agora=AGORA)


# ------------------------------------------ quem praticou o ato (LH13, «15 a»)
#
# O oficial, 21/10/2026: o Livro 3 como o Livro 2. Todo registro e averbação é
# «datado e subscrito» (CN-MA art. 458): a lavratura grava no ato o nome, a
# função e o artigo de quem está logado (`ra_atos.lavrado_*`, que a rota tira
# de `quem_pratica_o_ato`), e a ficha fecha cada ato com eles.

QUEM_LAVRA = {"lavrado_nome": "CARLA EXEMPLO", "lavrado_titulo": "Escrevente Autorizada",
              "lavrado_tratamento": "A"}


def test_registro_averbacao_e_cancelamento_gravam_no_ato_quem_o_praticou():
    con = banco()
    r = cedula(con, **QUEM_LAVRA)
    RA.averbar(con, r["registro_id"], teor="Aditivo de prorrogação do prazo.",
               agora=AGORA, **QUEM_LAVRA)
    RA.cancelar(con, r["registro_id"], motivo="Liquidação integral da cédula.",
                agora=AGORA, **QUEM_LAVRA)
    atos = RA.atos_do(con, r["registro_id"])
    assert [(a["numero"], a["lavrado_nome"], a["lavrado_titulo"],
             a["lavrado_tratamento"]) for a in atos] == [
        (n, "CARLA EXEMPLO", "Escrevente Autorizada", "A") for n in (1, 2, 3)]


def test_o_ato_lavrado_sem_quem_o_praticou_fica_vazio_e_nao_se_deduz():
    """A carga do acervo não sabe quem lavrou: grava vazio, e não o login de
    quem carregou nem o delegatário do período."""
    con = banco()
    r = cedula(con, usuario="carga do acervo")
    ato = RA.atos_do(con, r["registro_id"])[0]
    assert (ato["lavrado_nome"], ato["lavrado_titulo"], ato["lavrado_tratamento"]) \
        == (None, None, None)
    assert ato["criado_por"] == "carga do acervo"


def test_a_ficha_fecha_cada_ato_com_quem_o_praticou_e_o_antigo_sai_sem_fecho():
    """O fecho é o do Livro 2 — a mesma regra (`ri_web.fecho_de_quem_praticou`)
    e o mesmo modelo (`RI_FECHO_DO_ATO`) —, com a data do ato, só o dia. O ato
    sem o nome gravado sai sem ele."""
    import ra_ficha_odt as FICHA
    con = banco()
    r = cedula(con, **QUEM_LAVRA)
    # o ato antigo: sem quem o praticou
    RA.averbar(con, r["registro_id"], teor="Averbação vinda do acervo antigo.",
               agora="2026-08-25T10:00:00")
    claros = FICHA.contexto(registro=RA.registro(con, r["registro_id"]),
                            atos=RA.atos_do(con, r["registro_id"]), partes=[],
                            serventia={"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"},
                            impresso_em="26/08/2026 09:00", con=con)
    r1, av2 = claros["atos"].split("\n\n")
    assert r1.endswith("\n  Cidade Exemplo/MA, 24 de agosto de 2026. Dou fé. "
                       "A Escrevente Autorizada (CARLA EXEMPLO)."), r1
    assert "Dou fé" not in av2, av2


# ------------------------------------- a situação se confere com a linha presa
#
# L039R (varredura do mesmo padrão da ressalva 1 do L039): `averbar` e
# `cancelar` conferiam a situação sem prender a linha do registro. Com a
# ponte, a transação da rota já pega a trava única do banco; sem ela, a trava
# do número do ato (`ra_atos.numero:<id>`) vem DEPOIS da conferência, e quem
# chegasse no meio passava por ela. Os testes usam conexões do psycopg sem a
# ponte — como a transação vai ficar quando a ponte sair.

import banco_pg                                  # noqa: E402

SO_NO_POSTGRES = pytest.mark.skipif(
    not banco_pg.ativo(),
    reason="trava de linha: só existe com o PostgreSQL ligado (CG_PG_DSN)")


def _psycopg_puro(con, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{con.schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def _o_segundo_chega_no_meio(primeiro, segundo, vigia, faz):
    """`primeiro` já gravou e não confirmou. `faz` roda no `segundo`, num fio;
    quando ele estiver esperando (ou depois de 10 s), o primeiro confirma.
    Devolve o erro do segundo, ou None se ele passou."""
    import threading
    import time
    from bd_nativo import banco as _banco
    pid = _banco(segundo).valor("SELECT pg_backend_pid() AS pid")
    saida: dict = {}

    def corre():
        try:
            faz()
            segundo.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            segundo.rollback()

    fio = threading.Thread(target=corre)
    fio.start()
    for _ in range(200):
        if _banco(vigia).valor(
                "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)):
            break
        time.sleep(0.05)
    primeiro.commit()
    fio.join(30)
    return saida.get("erro")


@SO_NO_POSTGRES
def test_dois_cancelamentos_ao_mesmo_tempo_nao_cancelam_duas_vezes():
    con = banco()
    r = cedula(con)
    con.commit()
    um, dois = _psycopg_puro(con), _psycopg_puro(con)
    vigia = _psycopg_puro(con, autocommit=True)
    try:
        RA.cancelar(um, r["registro_id"], motivo="Liquidação integral da cédula.",
                    agora=AGORA)
        erro = _o_segundo_chega_no_meio(um, dois, vigia, lambda: RA.cancelar(
            dois, r["registro_id"], motivo="Baixa pedida pelo credor da cédula.",
            agora=AGORA))
    finally:
        for c in (um, dois, vigia):
            c.close()
    assert isinstance(erro, RA.RaError), erro
    assert "já está com situação CANCELADO" in str(erro)
    cancelamentos = [a for a in RA.atos_do(con, r["registro_id"])
                     if a["motivo_cancelamento"]]
    assert len(cancelamentos) == 1, "o registro foi cancelado duas vezes"


@SO_NO_POSTGRES
def test_averbacao_que_chega_no_meio_do_cancelamento_e_recusada():
    con = banco()
    r = cedula(con)
    con.commit()
    um, dois = _psycopg_puro(con), _psycopg_puro(con)
    vigia = _psycopg_puro(con, autocommit=True)
    try:
        RA.cancelar(um, r["registro_id"], motivo="Liquidação integral da cédula.",
                    agora=AGORA)
        erro = _o_segundo_chega_no_meio(um, dois, vigia, lambda: RA.averbar(
            dois, r["registro_id"], teor="Averbação de prorrogação do prazo.",
            agora=AGORA))
    finally:
        for c in (um, dois, vigia):
            c.close()
    assert isinstance(erro, RA.RaError), erro
    assert "só se averba registro ativo" in str(erro)
    assert [(a["tipo"], a["numero"]) for a in RA.atos_do(con, r["registro_id"])] \
        == [("R", 1), ("AV", 2)]

"""A MINUTA QUE ESTÁ SENDO LAVRADA NÃO SE REVISA NEM SE DESCARTA NO MEIO — LD10.

DE ONDE VEIO (21/10/2026). A revisão do LD03 pediu que a tela do modelo
prendesse a minuta (`FOR UPDATE`) antes de conferir a situação: lida solta, a
minuta que outra aba está lavrando ainda parece «a revisar», e o texto novo
cairia por cima do que foi ao livro. `ri_minuta.atualizar` («Guardar
revisão») e `ri_minuta.descartar` têm a mesma conferência — «já virou ato?» —
e gravavam com a linha solta: a revisão escrevia na procedência do ato, e o
descarte marcava DESCARTADA uma minuta já lavrada.

COMO SE MEDE. Com a ponte, `db.transaction()` põe um escritor por vez no banco
inteiro e a corrida não aparece. Estes testes rodam como a transação vai ficar
quando a ponte sair: duas conexões do psycopg, a lavratura (`marcar_lavrada`)
gravando e ainda sem confirmar, e a revisão ou o descarte chegando no meio,
noutro fio. Uma vigia olha o `pg_locks` para saber que o segundo ESPEROU.
"""
from __future__ import annotations

import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import banco_pg  # noqa: E402
import ri_minuta as RIMIN  # noqa: E402
from bd_nativo import banco  # noqa: E402

sem_a_ponte = pytest.mark.skipif(
    not banco_pg.ativo(), reason="a corrida só existe no PostgreSQL")

AGORA = "2026-10-21T09:00"
TEOR = ("AV-01/4100 — Procede-se a esta averbação para constar a construção de "
        "prédio residencial com 80,00 m², conforme o habite-se apresentado.")
TEOR_REVISTO = TEOR + " A área foi conferida no projeto aprovado."


def _ficha_com_minuta(cg_casa) -> tuple[int, int, int]:
    """A matrícula, a minuta a revisar e o ato que a lavratura está gravando."""
    con = sqlite3.connect(cg_casa["banco"])
    try:
        bd = banco(con)
        mid = bd.escrever(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, criado_em)
               VALUES ('4100', '2', '2', 'ATIVO', 'ESTRUTURADA', %s)
               RETURNING id""", (AGORA,))[0]["id"]
        minuta_id = RIMIN.criar(con, matricula_id=mid, tipo="AV", teor=TEOR,
                                agora=AGORA, origem=RIMIN.MANUAL,
                                observacao="Preenchida na tela «Preencher o modelo».")
        ato_id = bd.escrever(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
                   teor_formato, cancelado, acervo, origem, hash_ato, lavrado_em)
               VALUES (%s, 'AV', 1, '2026-10-21', %s, 'texto', 0, 0, 'MANUAL',
                       'hash-de-teste', %s)
               RETURNING id""", (mid, TEOR, AGORA))[0]["id"]
        con.commit()
    finally:
        con.close()
    return int(mid), int(minuta_id), int(ato_id)


def _psycopg_puro(cg_casa, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{banco_pg.schema_do_caminho(cg_casa["banco"])}", public')
    if not autocommit:
        pg.commit()
    return pg


def _ao_mesmo_tempo(cg_casa, primeira, segunda):
    """A `primeira` grava e ainda não confirmou; a `segunda` chega no meio,
    por outra conexão. Devolve (o erro da segunda ou None, se ela esperou)."""
    um, dois = _psycopg_puro(cg_casa), _psycopg_puro(cg_casa)
    vigia = _psycopg_puro(cg_casa, autocommit=True)
    pid = banco(dois).valor("SELECT pg_backend_pid() AS pid")
    primeira(um)
    saida: dict = {}

    def no_fio():
        try:
            segunda(dois)
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            dois.rollback()

    fio = threading.Thread(target=no_fio)
    fio.start()
    esperou = False
    for _ in range(100):          # a segunda tem de estar ESPERANDO
        if banco(vigia).valor(
                "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)):
            esperou = True
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    return saida.get("erro"), esperou


def _minuta(cg_casa, minuta_id: int) -> dict:
    con = sqlite3.connect(cg_casa["banco"])
    try:
        return dict(banco(con).um(
            "SELECT situacao, ato_id, teor FROM ri_minutas WHERE id=%s", (minuta_id,)))
    finally:
        con.close()


@sem_a_ponte
def test_a_revisao_que_chega_durante_a_lavratura_nao_escreve_na_minuta_lavrada(cg_casa):
    _, minuta_id, ato_id = _ficha_com_minuta(cg_casa)

    def lavra(c):
        RIMIN.marcar_lavrada(c, minuta_id, ato_id=ato_id, agora=AGORA)

    def revisa(c):
        RIMIN.atualizar(c, minuta_id, teor=TEOR_REVISTO, agora=AGORA)

    erro, esperou = _ao_mesmo_tempo(cg_casa, lavra, revisa)
    assert esperou, "a revisão não esperou a lavratura que estava no meio"
    assert isinstance(erro, RIMIN.MinutaError) and "saiu da fila de revisão" in str(erro), erro
    assert _minuta(cg_casa, minuta_id) == {"situacao": RIMIN.LAVRADA, "ato_id": ato_id,
                                           "teor": TEOR}, (
        "a revisão escreveu na minuta que foi ao livro")


@sem_a_ponte
def test_o_descarte_que_chega_durante_a_lavratura_nao_descarta_a_minuta_lavrada(cg_casa):
    _, minuta_id, ato_id = _ficha_com_minuta(cg_casa)

    def lavra(c):
        RIMIN.marcar_lavrada(c, minuta_id, ato_id=ato_id, agora=AGORA)

    def descarta(c):
        RIMIN.descartar(c, minuta_id, motivo="Texto refeito em outra minuta",
                        agora=AGORA)

    erro, esperou = _ao_mesmo_tempo(cg_casa, lavra, descarta)
    assert esperou, "o descarte não esperou a lavratura que estava no meio"
    assert isinstance(erro, RIMIN.MinutaError) and "já virou ato" in str(erro), erro
    minuta = _minuta(cg_casa, minuta_id)
    assert (minuta["situacao"], minuta["ato_id"]) == (RIMIN.LAVRADA, ato_id), (
        "a minuta lavrada foi marcada como descartada")

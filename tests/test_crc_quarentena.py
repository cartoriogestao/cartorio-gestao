"""A QUARENTENA DA CARGA DA CRC — decisao do oficial em 12/09/2026.

    «os que foram importados sem elemento essencial para a CRC, deixar em
     quarentena pendente de complemento. nao entra nas cargas de envio»

O QUE ESTES TESTES GUARDAM

    **Que o assento sem elemento essencial NAO entra na carga.** Antes ele
    aparecia na lista e ia no lote; a recusa da Central chegava dias depois,
    sem ninguem por perto, e **levava o lote junto**.

    **Que ele SAI DA QUARENTENA SOZINHO quando o dado entra.** A quarentena e
    derivada de `o_que_falta`, medida na hora — nao ha marca gravada para
    alguem esquecer de tirar. E a licao de `inacabados`: uma lente, e nao uma
    segunda gaveta.

    **Que ela NAO usa `situacao`.** Aquela coluna e `ATIVO | CANCELADO`, e
    `rc_assento` recusa lancamento e correcao fora de ATIVO — pôr a quarentena
    ali trancaria justamente o que precisa ser completado.

    **Que a lista diz O QUE falta**, e nao so que falta. «Nao entrou» sem o
    motivo manda o balcao procurar as cegas.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import crc_carga as CRC                                          # noqa: E402


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _assento(con, **extra) -> int:
    valores = {"serie": "RC_A", "especie": "NASCIMENTO", "numero": 11309,
               "nome": "AUGUSTO SILVA LIMA",
               "matricula": "00000001551998100012158001130981",
               "data_ato": "1998-11-17", "data_fato": "1994-10-16",
               "dados_json": "{}", "teor_formato": "TEXTO",
               "situacao": "ATIVO", "origem": "TESTE",
               "criado_em": "2026-09-12T10:00"}
    valores.update(extra)
    nomes = list(valores)
    cur = con.execute(
        f"INSERT INTO rc_assentos ({', '.join(nomes)}) "
        f"VALUES ({', '.join('?' for _ in nomes)})",
        [valores[n] for n in nomes])
    return int(cur.lastrowid)


def _pessoa(con, assento_id, papel, nome, **extra):
    valores = {"assento_id": assento_id, "papel": papel, "nome": nome,
               "ordem": 1, "origem": "TESTE", "criado_em": "2026-09-12T10:00"}
    valores.update(extra)
    nomes = list(valores)
    con.execute(
        f"INSERT INTO rc_pessoas ({', '.join(nomes)}) "
        f"VALUES ({', '.join('?' for _ in nomes)})",
        [valores[n] for n in nomes])


def test_assento_sem_o_registrado_fica_em_quarentena(con):
    """Sem o registrado nao ha sexo nem municipio — os dois retem na Central."""
    _assento(con)
    retidos = CRC.em_quarentena(con)
    assert len(retidos) == 1
    assert retidos[0]["o_que_falta"]


def test_o_assento_sem_data_do_ato_vem_primeiro_como_no_sqlite(con):
    """No SQLite o NULL vinha primeiro no `ORDER BY data_ato`; no PostgreSQL vai
    por ultimo, e com o `LIMIT` o assento sem data sairia da lista (revisao do
    L004)."""
    com_data = _assento(con)
    sem_data = _assento(con, numero=11310, data_ato=None,
                        matricula="00000001551998100012158001131081")
    con.commit()
    assert [r["id"] for r in CRC.em_quarentena(con)] == [sem_data, com_data]
    assert [r["id"] for r in CRC.em_quarentena(con, limite=1)] == [sem_data]


def test_quem_esta_em_quarentena_NAO_entra_no_ARQUIVO(con):
    """**A quarentena e no ARQUIVO, e nao na lista de candidatos.**

    Eu comecei retendo em `pendentes_de_carga`, e aquilo tirou da carga **o
    acervo historico inteiro** — os 244 assentos do E-Oficio sao justamente os
    sem sexo e sem municipio, e a carga existe *para* subi-los. Quem retem e
    `montar`, que os deixa fora do XML e os devolve em `retidos`.
    """
    assento_id = _assento(con)
    # O candidato continua aparecendo: e ali que o balcao o ve para completar.
    assert assento_id in {a["id"] for a in CRC.pendentes_de_carga(con)}
    quadro = CRC.montar(con, [assento_id], cns="000000")
    assert {r["assento_id"] for r in quadro["retidos"]} == {assento_id}


def test_completar_o_dado_TIRA_da_quarentena_sozinho(con):
    """Nao ha marca para alguem lembrar de desmarcar."""
    assento_id = _assento(con)
    assert CRC.em_quarentena(con)

    _pessoa(con, assento_id, "REGISTRADO", "AUGUSTO SILVA LIMA", sexo="M",
            naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA")
    con.commit()

    retidos = CRC.em_quarentena(con)
    assert retidos == [], [r["o_que_falta"] for r in retidos]
    quadro = CRC.montar(con, [assento_id], cns="000000")
    assert quadro["retidos"] == []


def test_a_quarentena_diz_O_QUE_falta(con):
    """«Nao entrou» sem o motivo manda o balcao procurar as cegas."""
    _assento(con)
    faltas = CRC.em_quarentena(con)[0]["o_que_falta"]
    junto = " ".join(faltas).lower()
    assert "sexo" in junto or "nome" in junto or "município" in junto


def test_a_quarentena_NAO_mexe_na_situacao(con):
    """`situacao` e ATIVO|CANCELADO, e fora de ATIVO o assento nao recebe
    lancamento nem correcao — seria trancar o que precisa ser completado."""
    assento_id = _assento(con)
    CRC.em_quarentena(con)
    linha = con.execute("SELECT situacao FROM rc_assentos WHERE id=?",
                        (assento_id,)).fetchone()
    assert linha["situacao"] == "ATIVO"


def test_assento_completo_continua_indo_para_a_carga(con):
    """A quarentena nao pode reter quem esta em ordem."""
    assento_id = _assento(con)
    _pessoa(con, assento_id, "REGISTRADO", "AUGUSTO SILVA LIMA", sexo="M",
            naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA")
    con.commit()
    assert assento_id in {a["id"] for a in CRC.pendentes_de_carga(con)}
    assert CRC.em_quarentena(con) == []


def test_a_lista_de_candidatos_NAO_perde_o_acervo(con):
    """**O guarda que me pegou, agora escrito aqui também.**

    «A carga é *justamente* a subida do acervo histórico à Central — excluí-lo
    apagaria a razão de ela existir.» O assento do acervo é incompleto por
    natureza, e continua aparecendo para ser escolhido e completado.
    """
    assento_id = _assento(con, origem="EOFICIO")
    assert CRC.em_quarentena(con)                      # ele falta, sim
    assert assento_id in {a["id"] for a in CRC.pendentes_de_carga(con)}

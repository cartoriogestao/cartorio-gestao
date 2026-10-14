"""Quando o contador do E-Ofício discorda do que a carga trouxe.

O ACHADO, MEDIDO EM 29/08/2026
    A carga semeia o contador pelo **maior número que trouxe**. Conferido contra
    o contador do próprio E-Ofício, em `tbPropriedadeRCPN`:

    | espécie    | a carga semearia | o E-Ofício dizia |          |
    |------------|------------------|------------------|----------|
    | nascimento |           19.552 |           19.552 | bate     |
    | óbito      |            1.976 |            1.976 | bate     |
    | **casamento** |         1.011 |           **39** | NÃO bate |

    E o porquê aparece na FOLHA: no nascimento o registro é 19.552 e a folha
    166; no óbito, 1.976 contra 275 — **o número corre pela série e a folha
    reinicia a cada livro**. No casamento registro e folha são os dois 39, e os
    números dos casamentos do acervo reiniciam a cada livro (o livro 01 vai de
    315 a 405; o livro 6, de 111 a 659).

POR QUE ISSO NÃO SE RESOLVE MEDINDO
    Se o número do casamento for por LIVRO, semear pelo maior poria o próximo em
    **1012** onde deveria ser **40** — e o livro pularia 972 números. Número alto
    demais não repete nada, mas **livro com salto é o que a correição pergunta**.

    Um `max()` calado escolheria um lado sem dizer que havia conflito. O
    contador continua sendo semeado — a casa não pode ficar sem número —, **e a
    divergência vira pendência declarada**, com os dois números.
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

import acervo_carga as AC                                        # noqa: E402
import implantacao as IMP                                        # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-29T09:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _acervo_de_ensaio(tmp_path, **contadores):
    """Um acervo mínimo, com a tabela de propriedade do RCPN."""
    caminho = tmp_path / "acervo.sqlite3"
    ac = sqlite3.connect(caminho)
    campos = {"intRegistroAtualNascimento": 0,
              "intRegistroAtualCasamento": 0,
              "intRegistroAtualObito": 0}
    campos.update(contadores)
    colunas = ", ".join(f"{k} INTEGER" for k in campos)
    ac.execute(f"CREATE TABLE tbPropriedadeRCPN ({colunas})")
    ac.execute(f"INSERT INTO tbPropriedadeRCPN VALUES "
               f"({', '.join('?' for _ in campos)})", tuple(campos.values()))
    ac.commit()
    ac.row_factory = sqlite3.Row
    return ac


def _numeracao(con, serie, *, maior, proximo=None):
    con.execute(
        """INSERT INTO nu_numeracao (serie, proximo, maior_em_uso, semeado_de,
               fixado_em) VALUES (?,?,?,?,?)
           ON CONFLICT(serie) DO UPDATE SET proximo=excluded.proximo,
               maior_em_uso=excluded.maior_em_uso""",
        (serie, proximo or (maior + 1), maior, "ensaio", AGORA))


# ------------------------------------------------ o catálogo


def test_as_tres_especies_que_o_eoficio_numerava_estao_declaradas():
    assert set(AC.CONTADOR_DECLARADO_PELO_EOFICIO) == {"RC_A", "RC_B", "RC_C"}
    assert (AC.CONTADOR_DECLARADO_PELO_EOFICIO["RC_B"]
            == "intRegistroAtualCasamento")


def test_o_contador_declarado_nao_e_fonte_de_semeadura():
    """Ele entra como CONFERÊNCIA, e não como mais uma fonte — senão o `max()`
    o engoliria e a divergência sumiria."""
    assert set(AC.CONTADOR_DECLARADO_PELO_EOFICIO).isdisjoint(
        AC.CONTADOR_NA_PROPRIEDADE_DO_RCPN)


# ------------------------------------------------ quando batem, silêncio


def test_quando_batem_nao_ha_pendencia(casa, tmp_path):
    """Nascimento e óbito batem exatos no acervo real — e alarme que soa sempre
    é alarme que ninguém ouve."""
    con = _con(casa)
    acervo = _acervo_de_ensaio(tmp_path, intRegistroAtualNascimento=19552,
                               intRegistroAtualObito=1976)
    with con:
        _numeracao(con, "RC_A", maior=19552)
        _numeracao(con, "RC_C", maior=1976)
    assert AC._divergencias_do_contador_do_rcpn(con, acervo) == []


def test_serie_sem_numeracao_nao_gera_divergencia(casa, tmp_path):
    """Sem contador semeado não há o que comparar — e isso já é outra pendência,
    a de série sem contador."""
    con = _con(casa)
    acervo = _acervo_de_ensaio(tmp_path, intRegistroAtualCasamento=39)
    assert AC._divergencias_do_contador_do_rcpn(con, acervo) == []


# ------------------------------------------------ quando não batem, pergunta


def test_a_divergencia_do_casamento_aparece(casa, tmp_path):
    """O caso real: a carga traz 1.011 e o E-Ofício diz 39."""
    con = _con(casa)
    acervo = _acervo_de_ensaio(tmp_path, intRegistroAtualCasamento=39)
    with con:
        _numeracao(con, "RC_B", maior=1011)
    achadas = AC._divergencias_do_contador_do_rcpn(con, acervo)
    assert len(achadas) == 1
    d = achadas[0]
    assert d["serie"] == "RC_B"
    assert d["do_acervo"] == 1011
    assert d["do_eoficio"] == 39
    assert d["semeado"] == 1012


def test_a_divergencia_vira_pendencia_declarada_com_os_dois_numeros(casa,
                                                                    tmp_path):
    """Devolver a divergência numa lista que aparece na tela da carga e em lugar
    nenhum depois é o mesmo que não avisar: quem roda a carga lê a lista, e quem
    informa o número é o oficial, semanas depois."""
    con = _con(casa)
    acervo = _acervo_de_ensaio(tmp_path, intRegistroAtualCasamento=39)
    with con:
        _numeracao(con, "RC_B", maior=1011)
        AC.semear_numeracao(con, agora=AGORA, usuario="jean", acervo=acervo)
    abertas = IMP.abertas(con)
    doc = " ".join(str(x.get("motivo") or "") for x in abertas)
    assert "1011" in doc or "1.011" in doc
    assert "39" in doc
    assert "livro de papel" in doc


def test_a_pendencia_diz_quantos_numeros_o_livro_pularia(casa, tmp_path):
    """Número alto demais não repete nada — mas livro com salto é o que a
    correição pergunta, e o oficial precisa do tamanho do salto para decidir."""
    con = _con(casa)
    acervo = _acervo_de_ensaio(tmp_path, intRegistroAtualCasamento=39)
    with con:
        _numeracao(con, "RC_B", maior=1011)
        AC.semear_numeracao(con, agora=AGORA, usuario="jean", acervo=acervo)
    doc = " ".join(str(x.get("motivo") or "") for x in IMP.abertas(con))
    assert "972" in doc                      # 1012 − 39 − 1


def test_o_contador_continua_semeado_apesar_da_divergencia(casa, tmp_path):
    """A casa não pode ficar sem número enquanto a dúvida não se resolve — e
    semear pelo maior é a regra segura contra REPETIR, que é o defeito pior."""
    con = _con(casa)
    acervo = _acervo_de_ensaio(tmp_path, intRegistroAtualCasamento=39)
    with con:
        _numeracao(con, "RC_B", maior=1011)
        AC.semear_numeracao(con, agora=AGORA, usuario="jean", acervo=acervo)
    linha = con.execute("SELECT * FROM nu_numeracao WHERE serie='RC_B'"
                        ).fetchone()
    assert int(linha["proximo"]) == 1012


def test_rodar_a_carga_duas_vezes_nao_reabre_o_que_o_oficial_resolveu(casa,
                                                                      tmp_path):
    """`declarar_numeracao` é repetível por construção — é a mesma regra das
    outras pendências, e ela existe porque a carga pode rodar de novo."""
    con = _con(casa)
    acervo = _acervo_de_ensaio(tmp_path, intRegistroAtualCasamento=39)
    with con:
        _numeracao(con, "RC_B", maior=1011)
        AC.semear_numeracao(con, agora=AGORA, usuario="jean", acervo=acervo)
        antes = len(IMP.abertas(con))
        AC.semear_numeracao(con, agora=AGORA, usuario="jean", acervo=acervo)
    assert len(IMP.abertas(con)) == antes


# ------------------------------------------------ não estoura


def test_acervo_sem_a_tabela_nao_derruba_a_carga(casa, tmp_path):
    """A carga inteira não pode morrer porque uma tabela de propriedade mudou de
    forma entre versões do E-Ofício."""
    con = _con(casa)
    vazio = sqlite3.connect(tmp_path / "vazio.sqlite3")
    assert AC._divergencias_do_contador_do_rcpn(con, vazio) == []
    assert AC._divergencias_do_contador_do_rcpn(con, None) == []

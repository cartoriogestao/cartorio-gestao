# -*- coding: utf-8 -*-
"""O selo isento SEM TEXTO — G005 (achado G-5 da auditoria G002, 18/11/2026).

O QUE SE MEDIU: seis averbações do RCPN, isentas no TJ, com `sd_selos.texto`
NULL. Todas com o selo DIGITADO no lançamento (sem `sid`, sem `caminho`, sem
saldo; `obtido_em` = `usado_em`). A régua do isento era só o texto
(`ILIKE '%Selo Isento%'`), e elas sumiram do aviso do comprovante, da fila do
Portal, dos isentos do dia e da conferência — e entraram na lista dos selos
PAGOS sem cobertura.

O QUE SE PROVA AQUI:
  - a régua central (`selo_isento`): com texto, vale só o texto; sem texto,
    vale o TJ e, sem resposta dele, a marca da casa;
  - os cinco lugares que liam o texto passam a ver o selo vazio isento no TJ
    — o caso dos seis, sem mexer em dado nenhum;
  - a causa: o selo digitado com «ato / selo gratuito» marcado não é tratado
    como pago (a gratuidade não trava) e guarda a marca.

Nenhum dado de pessoa real: CNS genérico (000000) e nomes de exemplo.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ato_selado as AS  # noqa: E402
import gestor_fiscal as GF  # noqa: E402
import gratuidade_comprovante as GC  # noqa: E402
import selo_isento as SI  # noqa: E402
import selo_portal as SP  # noqa: E402
from bd_nativo import banco  # noqa: E402
from gestor_schema import init_gestor_schema  # noqa: E402
from selador_config import init_selador_schema  # noqa: E402
from test_fluxo_rcpn import balcao  # noqa: E402,F401 — a casa do balcão do RCPN

ESCREVENTE = "BEATRIZ EXEMPLO DE SOUZA"
ISENTO = ("Poder Judiciário – TJMA. Selo: {n}, 16/10/2026 11:38:33, Ato: 14.4.1, "
          "Total R$ 43,37 Emol R$ 38,72 Selo Isento, Consulte em https://selo.tjma.jus.br")
PAGO = ("Poder Judiciário – TJMA. Selo: {n}, 16/10/2026 11:38:33, Ato: 14.4.1, "
        "Total R$ 43,37 Emol R$ 38,72, Consulte em https://selo.tjma.jus.br")


def _n(i: int) -> str:
    return f"AVERBA000000{i:016d}"


def _selo(bd, i, *, texto=None, obtido="2026-10-16T11:38:33", tabela="rc_atos",
          ato_id=None, declarado=None) -> int:
    numero = _n(i)
    return int(bd.escrever(
        """INSERT INTO sd_selos (numero, texto, atribuicao, referencia, tabela, ato_id,
                                 ambiente, obtido_em, obtido_por, usado_em, isento_declarado)
           VALUES (%s, %s, 'RCPN', %s, %s, %s, 'PRODUCAO', %s, %s, %s, %s) RETURNING id""",
        (numero, texto.format(n=numero) if texto else texto,
         f"{tabela}:{ato_id or i}", tabela, ato_id or i, obtido, ESCREVENTE, obtido,
         declarado))[0]["id"])


def _tj(bd, i, *, isento: bool, situacao="ACHADO", codigo="14.4.1"):
    bd.escrever(
        """INSERT INTO ge_portal_selos (numero, consultado_em, situacao, cancelado, isento,
                                        motivo_isencao, analise, codigo_ato, valor_ato)
           VALUES (%s, '2026-11-15T14:00:00', %s, 0, %s, %s, %s, %s, 43.37)""",
        (_n(i), situacao, int(isento), "mandado judicial" if isento else None,
         "DEFERIDA" if isento else None, codigo))


# ------------------------------------------------------------- a régua


@pytest.fixture
def bd():
    con = conexao_de_teste()
    init_selador_schema(con)
    init_gestor_schema(con)
    b = banco(con)
    b.escrever("CREATE TABLE ri_atos (id INTEGER PRIMARY KEY, isento INTEGER)")
    return b


def _isento(bd, selo_id) -> bool:
    return SI.selo_e_isento(bd, selo_id)


def test_com_texto_vale_so_o_texto(bd):
    """Nada muda para o selo que o aparelho escreveu — nem quando o TJ ou a
    casa dizem outra coisa: essa divergência é do agente fiscal."""
    isento = _selo(bd, 1, texto=ISENTO)
    pago = _selo(bd, 2, texto=PAGO, declarado=1)
    _tj(bd, 1, isento=False)
    _tj(bd, 2, isento=True)
    assert _isento(bd, isento) and not _isento(bd, pago)


def test_sem_texto_e_sem_nenhuma_marca_nao_e_isento(bd):
    assert not _isento(bd, _selo(bd, 1))
    assert not _isento(bd, _selo(bd, 2, texto="   "))


def test_sem_texto_vale_a_resposta_do_tj(bd):
    """O caso dos seis: texto NULL, isento no TJ."""
    sim, nao = _selo(bd, 1), _selo(bd, 2)
    _tj(bd, 1, isento=True)
    _tj(bd, 2, isento=False)
    assert _isento(bd, sim) and not _isento(bd, nao)


def test_o_tj_vem_antes_da_marca_da_casa(bd):
    """A gratuidade presumida (14.a) o TJ devolve com `isento` falso; e o que
    o TJ disse do selo vale mais do que a caixinha marcada no balcão."""
    s = _selo(bd, 1, declarado=1)
    _tj(bd, 1, isento=False, codigo="14.a")
    assert not _isento(bd, s)


def test_sem_resposta_do_tj_vale_a_marca_da_casa(bd):
    declarado = _selo(bd, 1, declarado=1)
    bd.escrever("INSERT INTO ri_atos (id, isento) VALUES (7, 1), (8, 0)")
    do_ato = _selo(bd, 2, tabela="ri_atos", ato_id=7)
    ato_pago = _selo(bd, 3, tabela="ri_atos", ato_id=8)
    # a consulta que deu ERRO não é resposta: a marca da casa continua valendo
    _tj(bd, 1, isento=False, situacao="ERRO")
    assert _isento(bd, declarado) and _isento(bd, do_ato) and not _isento(bd, ato_pago)


def test_a_condicao_vai_atras_de_not_sem_virar_null(bd):
    """`selos_pagos_sem_cobertura` usa `NOT condicao`: NULL ali sumiria com
    o selo das duas listas."""
    vazio = _selo(bd, 1)
    sql, args = SI.condicao(bd, "s")
    ids = [r["id"] for r in bd.ler(f"SELECT s.id FROM sd_selos s WHERE NOT {sql}", args)]
    assert ids == [vazio]


def test_isentos_sem_texto_so_olha_os_vazios(bd):
    com_texto = _selo(bd, 1, texto=ISENTO)
    vazio = _selo(bd, 2)
    _tj(bd, 1, isento=True)
    _tj(bd, 2, isento=True)
    assert SI.isentos_sem_texto(bd, [com_texto, vazio, None]) == {vazio}
    assert SI.isentos_sem_texto(bd, []) == set()


def test_banco_sem_as_tabelas_cai_para_a_regua_do_texto():
    """Os testes de unidade montam `sd_selos` à mão: sem o TJ e sem a coluna,
    a régua é a de antes."""
    con = conexao_de_teste()
    b = banco(con)
    b.escrever("CREATE TABLE sd_selos (id INTEGER PRIMARY KEY, numero TEXT, texto TEXT, "
               "tabela TEXT, ato_id INTEGER)")
    b.escrever("INSERT INTO sd_selos VALUES (1, 'A', %s, NULL, NULL), (2, 'B', NULL, NULL, NULL)",
               (ISENTO,))
    assert SI.condicao(b, "s") == ("(coalesce(s.texto, '') ILIKE %s)", ("%Selo Isento%",))
    assert SI.selo_e_isento(b, 1) and not SI.selo_e_isento(b, 2)
    assert SI.isentos_sem_texto(b, [1, 2]) == set()


# ------------------------------------------- os cinco lugares, com os seis


@pytest.fixture
def casa(cg_casa):
    """O caso medido: averbação de 16/10 com texto NULL, isenta no TJ, e uma
    de controle com texto, para provar que a de sempre continua lá."""
    with cg_casa["db"].transaction() as con:
        bd = banco(con)
        # 16/10 já está depois do «desde» padrão do comprovante (13/10).
        vazio = _selo(bd, 27009, obtido="2026-10-16T13:14:42")
        _tj(bd, 27009, isento=True)
        com_texto = _selo(bd, 1, texto=ISENTO, obtido="2026-10-16T10:00:00")
        pago_vazio = _selo(bd, 2, obtido="2026-10-16T12:00:00")
        _tj(bd, 2, isento=False)
    return {**cg_casa, "vazio": vazio, "com_texto": com_texto, "pago_vazio": pago_vazio}


def test_o_aviso_do_comprovante_cobra_o_selo_sem_texto(casa):
    with casa["db"].connect() as con:
        ids = [p["id"] for p in GC.pendentes(con, nome=ESCREVENTE)]
        vencidos = GC.sem_comprovante_por_escrevente(con, hoje="2026-11-19")
    assert ids == [casa["com_texto"], casa["vazio"]]
    assert [s["id"] for g in vencidos for s in g["selos"]] == ids


def test_o_comprovante_do_selo_sem_texto_se_guarda(casa, tmp_path):
    """Sem isto o aviso cobrava e a tela recusava: «não é de ato gratuito»."""
    with casa["db"].transaction() as con:
        GC.guardar(con, casa["vazio"], nome_arquivo="comprovante.pdf",
                   conteudo=b"%PDF-1.4\n%%EOF\n", pasta=tmp_path, usuario_id=None,
                   agora="2026-11-19T10:00:00", fundamento="ISENCAO_LEGAL")
        with pytest.raises(GC.ComprovanteError, match="não é de ato gratuito"):
            GC.guardar(con, casa["pago_vazio"], nome_arquivo="c.pdf",
                       conteudo=b"%PDF-1.4\n%%EOF\n", pasta=tmp_path, usuario_id=None,
                       agora="2026-11-19T10:00:00")
    with casa["db"].connect() as con:
        assert [p["id"] for p in GC.pendentes(con, nome=ESCREVENTE)] == [casa["com_texto"]]
        assert [c["id"] for c in GC.comprovados(con, nome=ESCREVENTE)] == [casa["vazio"]]


def test_a_fila_do_portal_traz_o_selo_sem_texto(casa):
    with casa["db"].connect() as con:
        ids = [g["id"] for g in SP.gratuitos(con)]
        SP._selo_isento(banco(con), casa["vazio"])
        with pytest.raises(SP.PortalError):
            SP._selo_isento(banco(con), casa["pago_vazio"])
    assert ids == [casa["com_texto"], casa["vazio"]]


def test_os_isentos_do_dia_contam_o_selo_sem_texto(casa):
    with casa["db"].connect() as con:
        achados = GF._isentos_do_dia(banco(con), date(2026, 10, 16))
    assert len(achados) == 1
    assert achados[0]["titulo"].startswith("2 selo(s) isento(s)")
    assert _n(27009) in achados[0]["detalhe"] and _n(2) not in achados[0]["detalhe"]


def test_o_selo_sem_texto_isento_no_tj_nao_e_pago_sem_cobertura(casa):
    with casa["db"].connect() as con:
        ids = [s["id"] for s in AS.selos_pagos_sem_cobertura(con, desde="2026-10-01")]
    assert casa["vazio"] not in ids and casa["com_texto"] not in ids
    assert casa["pago_vazio"] in ids


def test_a_conferencia_nao_acusa_gratuidade_no_selo_sem_texto(cg_casa_logada):
    """O analítico diz ISENTO; o selo local não tem texto, e o TJ o confirma.
    A gratuidade bate. O emolumento continua acusado: sem texto a casa não
    sabe o valor, e a conferência tem de dizer isso."""
    from test_conferencia_selos import arquivo, conferir, importar, registro
    casa = cg_casa_logada
    numero = "AVERBA000000TESTE00000000009"
    with casa["db"].transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO sd_selos (numero, texto, ambiente, obtido_em, usado_em)
                       VALUES (%s, NULL, 'PRODUCAO', '2026-10-16', '2026-10-16')""", (numero,))
        bd.escrever("""INSERT INTO ge_portal_selos (numero, consultado_em, situacao, isento)
                       VALUES (%s, '2026-11-15', 'ACHADO', 1)""", (numero,))
    importar(casa, arquivo([registro(**{"NÚMERO DO SELO": numero, "ATO": "14.4.1",
                                        "QTDE.": "1", "ISENTO": "Sim",
                                        "EMOLUMENTO": "38.72", "FERJ": "0"})]))
    q = conferir(casa)
    assert q["contagens"]["gratuidade"] == 0
    assert [d["tipos"] for d in q["diferencas"]] == [["emolumentos"]]


# --------------------------------------------------------------- a causa


def test_o_selo_digitado_marcado_gratuito_passa_pela_trava_e_guarda_a_marca():
    """A trava do selo pago está LIGADA na casa: sem a marca, o selo isento
    digitado era tratado como pago e recusado sem protocolo."""
    from test_selo_a_mao_passa_pela_cobertura import _casa, _registrar, _selos, _cobertura
    from test_ato_selado import SELO_BOM, SELO_OUTRO
    con = _casa()
    with pytest.raises(AS.SeloSemCobertura):
        AS.registrar_selo_obtido_a_mao(
            con, SELO_OUTRO, tabela="pt_atos", ato_id=2, atribuicao="PROTESTO",
            agora="2026-10-23T10:00:00", cns="000000", usuario=ESCREVENTE, texto=None)
    con.rollback()
    AS.registrar_selo_obtido_a_mao(
        con, SELO_BOM, tabela="pt_atos", ato_id=1, atribuicao="PROTESTO",
        agora="2026-10-23T10:00:00", cns="000000", usuario=ESCREVENTE, texto=None,
        isento=True)
    con.commit()
    assert [s["numero"] for s in _selos(con)] == [SELO_BOM]
    assert _cobertura(con) is None, "a gratuidade não reserva nem debita nada"
    linha = banco(con).um("SELECT id, texto, isento_declarado FROM sd_selos")
    assert linha["texto"] is None and linha["isento_declarado"] == 1
    assert SI.selo_e_isento(con, linha["id"])


def test_com_texto_a_marca_do_formulario_nao_e_gravada():
    """O texto, quando vem, decide sozinho — a marca só vale no vazio."""
    from test_selo_a_mao_passa_pela_cobertura import TEXTO_PAGO, _casa, _item, _ligar, _protocolo
    from test_ato_selado import SELO_BOM
    con = _casa()
    p = _protocolo(con)
    _ligar(con, _item(con, p["protocolo_id"], quitado=1), ato_id=1)
    AS.registrar_selo_obtido_a_mao(
        con, SELO_BOM, tabela="pt_atos", ato_id=1, atribuicao="PROTESTO",
        agora="2026-10-23T10:00:00", cns="000000", usuario=ESCREVENTE, texto=TEXTO_PAGO,
        isento=True)
    con.commit()
    assert banco(con).um("SELECT isento_declarado FROM sd_selos")["isento_declarado"] is None


def test_a_averbacao_com_selo_digitado_e_ato_gratuito_entra_isenta(balcao):
    """O caminho dos seis, pela tela: averbação lançada com o número do selo
    tirado fora do sistema e «Ato / selo gratuito» marcado."""
    from test_fluxo_rcpn import (FOLHAS, OFICIAL, _avisos, _form_nascimento,  # noqa: F401
                                 _lavrar, _pedidos_de_selo, _post, _um)
    assento, _ato, _ = _lavrar(balcao, "NASCIMENTO", _form_nascimento(), folha=FOLHAS[0])
    pedidos_antes = len(_pedidos_de_selo(balcao))
    numero = "AVERBA000000TESTE00000000077"
    r = _post(balcao, f"/rcpn/{assento['id']}/averbar", f"/rcpn/{assento['id']}/lancar",
              tipo="AVERBACAO", selo=numero,
              teor="Averbação gratuita de teste: retificação por mandado judicial.",
              natureza_averbacao="alteracao_nome", ato_gratuito="1",
              gratuidade_codigo="HIPOSSUFICIENCIA", motivo_gratuidade="mandado judicial")
    selo = _um(balcao, "SELECT id, texto, tabela, isento_declarado FROM sd_selos "
                       "WHERE numero = %s", (numero,))
    assert selo, _avisos(r.get_data(as_text=True))
    assert selo["tabela"] == "rc_atos" and selo["texto"] is None
    assert selo["isento_declarado"] == 1
    assert len(_pedidos_de_selo(balcao)) == pedidos_antes, "o selo digitado não pede outro"
    with balcao["db"].connect() as con:
        assert [p["id"] for p in GC.pendentes(con, nome=OFICIAL)] == [selo["id"]]


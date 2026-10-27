"""O TRÍDUO DO PROTESTO — tarefa 56, «impedir lavratura fora do termo final».

O QUE ESTES TESTES GUARDAM
      - **três dias úteis da protocolização, sem o dia do apontamento**
        (CN-MA art. 913, I e § 2º), pulando fim de semana e feriado (§ 3º);
      - **antes do termo inicial o protesto não se lavra** — o devedor está no
        prazo que o aviso lhe deu (art. 925, § 4º) —, e não há motivo que
        destrave;
      - **o prazo-limite e o dia do protesto são dois dias** (decisão do
        oficial em 27/10/2026, «no dia útil seguinte»): no próprio
        prazo-limite o devedor ainda paga e o protesto não se lavra; no dia
        útil seguinte ele se lavra NO PRAZO, e o atraso só começa depois;
      - **por edital, só do final do primeiro dia útil depois da publicação**
        (art. 922, § 1º);
      - **intimação no último dia ou depois: só no dia útil seguinte**
        (art. 913, II e III; art. 924);
      - **sustação revogada: até o dia útil seguinte ao recebimento**
        (art. 913, IV);
      - **depois do termo final, lavra-se com o motivo escrito**, que fica no
        ato e sai no instrumento (art. 913, § 1º);
      - **as duas rotas que protestam pedem a conferência** — o padrão do
        domínio é desligado, e a guarda que se pode esquecer se varre.
"""
from __future__ import annotations

import ast
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto as PT
import protesto_instrumento as PI
import protesto_triduo as TRI
from as_schema import init_as_schema
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
SERVENTIA = "Ofício Único de Cidade Exemplo/MA"

# 24/08/2026 é uma segunda-feira, e a semana não tem feriado nacional: o
# terceiro dia útil depois dela é a quinta, 27/08.
APONTADO = "2026-08-24"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    init_as_schema(con)
    con.execute("""CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT, entity_id INTEGER,
        original_name TEXT, stored_path TEXT, sha256 TEXT, size_bytes INTEGER,
        description TEXT, uploaded_at TEXT)""")
    return con


def intimado(con, *, intimado_em: str, modo: str = "PESSOAL",
             apontado_em: str = APONTADO, numero: str = "9911/1") -> int:
    dados = {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO EXEMPLO",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1.200,00", "saldo": "1.310,45",
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA CENTRAL LTDA", "documento": "00000017000149"},
        "devedores": [{"nome": "JOSÉ DA SILVA", "CPF": "04785512388",
                       "enderecos": [{"endereco": "RUA GRANDE, 10",
                                      "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    tid = PT.cadastrar_titulo(con, dados, origem="CRA",
                              origem_chave=f"lote:{numero}",
                              agora=f"{apontado_em}T09:00:00")
    PT.lancar_apontamento(con, tid, sv=SV, agora=f"{apontado_em}T09:00:00",
                          data_extenso="x")
    PT.lancar_intimacao(con, tid, modo=modo, agora=f"{intimado_em}T10:00:00",
                        codigo_edital="ED-2026-0001" if modo == "EDITAL" else None)
    return tid


def protestar(con, tid, dia: str, **kw):
    return PT.lancar_protesto(con, tid, sv=SV, agora=f"{dia}T17:00:00",
                              data_extenso="x", conferir_triduo=True, **kw)


def detalhe_do_protesto(con, tid) -> dict:
    linha = con.execute(
        "SELECT detalhe_json FROM pt_atos WHERE titulo_id=? AND tipo='PROTESTO'",
        (tid,)).fetchone()
    return json.loads(linha[0] or "{}")


# ------------------------------------------------------------- a conta


def test_tres_dias_uteis_sem_o_dia_do_apontamento():
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    conta = TRI.contar(con, tid, feriados=set())
    assert conta["protocolizado_em"] == APONTADO
    assert conta["termo_legal"] == "2026-08-27"
    # O devedor paga até a quinta 27/08; o protesto é na sexta 28/08 — e até
    # 27/10/2026 as duas pontas eram a mesma quinta.
    assert conta["prazo_limite"] == "2026-08-27"
    assert (conta["termo_inicial"], conta["termo_final"]) == (
        "2026-08-28", "2026-08-28")


def test_fim_de_semana_feriado_nacional_e_feriado_da_casa_nao_contam():
    # Quinta 03/09: sexta 04 conta; sábado, domingo e o 7 de setembro não;
    # terça 08 é feriado da casa; quarta 09 e quinta 10 contam. O protesto é
    # o dia útil seguinte ao prazo-limite.
    con = banco()
    tid = intimado(con, apontado_em="2026-09-03", intimado_em="2026-09-04")
    sem = TRI.contar(con, tid, feriados=set())
    assert (sem["prazo_limite"], sem["termo_final"]) == ("2026-09-09", "2026-09-10")
    com = TRI.contar(con, tid, feriados={date(2026, 9, 8)})
    assert (com["prazo_limite"], com["termo_final"]) == ("2026-09-10", "2026-09-11")


def test_o_dia_util_seguinte_pula_fim_de_semana_e_feriado_da_casa():
    # Apontado na terça 25/08: o prazo-limite é a sexta 28/08, e o dia útil
    # seguinte não é «amanhã» (sábado): é a segunda 31/08 — ou a terça 01/09,
    # se a segunda for feriado da casa.
    con = banco()
    tid = intimado(con, apontado_em="2026-08-25", intimado_em="2026-08-26")
    sem = TRI.contar(con, tid, feriados=set())
    assert (sem["prazo_limite"], sem["termo_inicial"]) == ("2026-08-28", "2026-08-31")
    com = TRI.contar(con, tid, feriados={date(2026, 8, 31)})
    assert com["termo_inicial"] == "2026-09-01"


# ------------------------------------------------- antes do termo inicial


def test_antes_do_termo_inicial_nao_se_protesta_nem_com_motivo():
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    with pytest.raises(PT.ProtestoError) as erro:
        protestar(con, tid, "2026-08-26", motivo_atraso="motivo comprido bastante")
    assert "27/08/2026" in str(erro.value)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "INTIMADO"


def test_no_proprio_prazo_limite_nao_se_protesta_e_a_frase_diz_quando():
    """Decisão do oficial em 27/10/2026: «no dia útil seguinte». Até essa data
    o sistema aceitava lavrar no prazo-limite, antes de o devedor terminar o
    prazo de pagar (CN-MA art. 925, § 4º)."""
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    with pytest.raises(PT.ProtestoError) as erro:
        protestar(con, tid, "2026-08-27",
                  motivo_atraso="motivo comprido bastante")
    frase = str(erro.value)
    assert "até o final de 27/08/2026" in frase
    assert "a partir de 28/08/2026" in frase
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "INTIMADO"


def test_no_dia_util_seguinte_se_protesta_no_prazo_e_a_conta_fica_no_ato():
    """O protesto do dia útil seguinte ao prazo-limite é NO PRAZO: não pede
    motivo, e o instrumento não declara atraso. Até 27/10/2026 ele saía
    ATRASADO."""
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    protestar(con, tid, "2026-08-28")
    t = detalhe_do_protesto(con, tid)["triduo"]
    assert t["situacao"] == TRI.NO_PRAZO
    assert (t["prazo_limite"], t["termo_final"]) == ("2026-08-27", "2026-08-28")
    assert "motivo" not in t
    assert TRI.mencao_no_instrumento(json.dumps({"triduo": t})) is None


# ---------------------------------------------------------- os casos da norma


def test_edital_so_do_final_do_primeiro_dia_util_depois_da_publicacao():
    # Publicado no último dia do tríduo (quinta 27/08): o devedor paga até o
    # final da sexta 28/08 (art. 922, § 1º, o prazo que o edital imprime), e o
    # protesto é na segunda 31/08 — o dia útil seguinte (27/10/2026).
    con = banco()
    tid = intimado(con, intimado_em="2026-08-27", modo="EDITAL")
    conta = TRI.contar(con, tid, feriados=set())
    assert conta["prazo_limite"] == "2026-08-28"
    assert (conta["termo_inicial"], conta["termo_final"]) == (
        "2026-08-31", "2026-08-31")
    assert "922" in conta["regra"]
    for cedo in ("2026-08-27", "2026-08-28"):
        with pytest.raises(PT.ProtestoError):
            protestar(con, tid, cedo)
    protestar(con, tid, "2026-08-31")


def test_intimacao_no_ultimo_dia_so_no_dia_util_seguinte():
    # Sexta 28/08 é o último dia de um apontamento de terça; a intimação
    # pessoal nesse dia passa o prazo do devedor à segunda, 31/08 (art. 924),
    # e o protesto à terça, 01/09 (o dia útil seguinte, 27/10/2026).
    con = banco()
    tid = intimado(con, apontado_em="2026-08-25", intimado_em="2026-08-28")
    conta = TRI.contar(con, tid, feriados=set())
    assert conta["termo_legal"] == "2026-08-28"
    assert conta["prazo_limite"] == "2026-08-31"
    assert (conta["termo_inicial"], conta["termo_final"]) == (
        "2026-09-01", "2026-09-01")
    assert "924" in conta["regra"]


def test_o_prazo_limite_da_regua_e_o_que_o_aviso_imprime():
    """O papel e a régua não podem discordar: o prazo-limite do tríduo é o
    `prazo_de_pagamento` do aviso, contado da mesma intimação."""
    import protesto_aviso as AV
    con = banco()
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    for apontado, intimado_em in (("2026-08-24", "2026-08-25"),
                                  ("2026-08-25", "2026-08-28"),
                                  ("2026-08-25", "2026-08-31")):
        tid = intimado(con, apontado_em=apontado, intimado_em=intimado_em,
                       numero=f"77{apontado[-2:]}{intimado_em[-2:]}/1")
        conta = TRI.contar(con, tid)
        titulo = dict(con.execute("SELECT * FROM pt_titulos WHERE id=?",
                                  (tid,)).fetchone())
        assert conta["prazo_limite"] == AV.prazo_de_pagamento(
            con, titulo, intimado_em), (apontado, intimado_em)


def test_sustacao_revogada_estende_o_termo_final_ate_o_dia_util_seguinte():
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    PT.lancar_sustacao(con, tid, juizo="1ª Vara Cível de Cidade Exemplo/MA",
                       processo="0800001-00.2026.8.10.0000",
                       agora="2026-08-26T10:00:00", recebido_em="2026-08-26")
    PT.lancar_revogacao_sustacao(con, tid, agora="2026-09-02T10:00:00",
                                 recebido_em="2026-09-02")
    conta = TRI.contar(con, tid, feriados=set())
    assert conta["termo_final"] == "2026-09-03"
    assert "913, IV" in conta["regra"]
    protestar(con, tid, "2026-09-03")


# ----------------------------------------------- depois do termo final


def test_depois_do_termo_final_exige_o_motivo():
    # Prazo-limite na quinta 27/08, protesto na sexta 28/08: a segunda 31/08
    # já é depois do dia útil seguinte.
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    with pytest.raises(PT.ProtestoError) as erro:
        protestar(con, tid, "2026-08-31")
    assert "913, § 1º" in str(erro.value)
    assert "28/08/2026" in str(erro.value)
    with pytest.raises(PT.ProtestoError):
        protestar(con, tid, "2026-08-31", motivo_atraso="curto")


def test_com_o_motivo_lavra_e_o_instrumento_declara_o_atraso():
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    motivo = "Comprovante da intimação devolvido depois do prazo"
    protestar(con, tid, "2026-08-31", motivo_atraso=f"  {motivo}  ")
    t = detalhe_do_protesto(con, tid)["triduo"]
    assert (t["situacao"], t["motivo"]) == (TRI.ATRASADO, motivo)
    teor = PI.emitir(con, tid, serventia=SERVENTIA,
                     agora="2026-08-31T17:30:00")["teor"]
    assert "depois do termo final do tríduo legal" in teor
    # O termo final é o dia útil seguinte ao prazo-limite (28/08), e não mais
    # o prazo-limite (27/08), desde 27/10/2026.
    assert "28/08/2026" in teor and "31/08/2026" in teor
    assert motivo in teor


def test_no_prazo_o_instrumento_nao_fala_de_atraso():
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    protestar(con, tid, "2026-08-28")
    teor = PI.emitir(con, tid, serventia=SERVENTIA,
                     agora="2026-08-28T17:30:00")["teor"]
    assert "tríduo" not in teor


def test_sem_data_da_protocolizacao_pede_o_motivo_em_vez_de_inventar_prazo():
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    con.execute("UPDATE pt_atos SET cancelado=1 WHERE titulo_id=? "
                "AND tipo='APONTAMENTO'", (tid,))
    con.execute("UPDATE pt_titulos SET protocolo='SEM' WHERE id=?", (tid,))
    conta = TRI.contar(con, tid, feriados=set())
    assert conta["termo_final"] is None and conta["sem_conta"]
    with pytest.raises(PT.ProtestoError) as erro:
        protestar(con, tid, "2026-08-27")
    assert "não conseguiu contar" in str(erro.value)
    protestar(con, tid, "2026-08-27",
              motivo_atraso="Título do acervo sem data de apontamento")
    t = detalhe_do_protesto(con, tid)["triduo"]
    assert t["situacao"] == TRI.SEM_CONTA and t["motivo"]


def test_a_lista_traz_a_conta_de_cada_titulo():
    con = banco()
    tid = intimado(con, intimado_em="2026-08-25")
    linha = TRI.para_a_lista(con, [{"id": tid}], hoje="2026-08-26")[0]
    assert linha["triduo_situacao"] == TRI.ANTES
    assert linha["triduo"]["prazo_limite_br"] == "27/08/2026"
    assert linha["triduo"]["termo_final_br"] == "28/08/2026"
    # A LISTA «A PROTESTAR» OFERECE O TÍTULO A PARTIR DO DIA ÚTIL SEGUINTE:
    # no prazo-limite ele ainda é ANTES (sem caixa de marcar), no dia
    # seguinte é NO PRAZO, e depois dele é ATRASADO.
    for hoje, onde in (("2026-08-27", TRI.ANTES), ("2026-08-28", TRI.NO_PRAZO),
                       ("2026-08-31", TRI.ATRASADO)):
        assert TRI.para_a_lista(con, [{"id": tid}], hoje=hoje)[0][
            "triduo_situacao"] == onde, hoje


# ------------------------------------------------- quem pede a conferência


def test_as_rotas_que_protestam_pedem_a_conferencia_do_triduo():
    """O padrão do domínio é desligado (as montagens de cenário lavram tudo no
    mesmo instante); por isso TODA chamada de produção tem de ligá-lo."""
    chamadas = 0
    for arquivo in RAIZ.glob("*.py"):
        if arquivo.name in ("protesto.py", "protesto_triduo.py"):
            continue
        texto = arquivo.read_text(encoding="utf-8")
        if "lancar_protesto(" not in texto:
            continue
        for no in ast.walk(ast.parse(texto)):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "lancar_protesto"):
                chamadas += 1
                kw = {k.arg: k.value for k in no.keywords}
                assert isinstance(kw.get("conferir_triduo"), ast.Constant) \
                    and kw["conferir_triduo"].value is True, \
                    f"{arquivo.name}:{no.lineno} lavra protesto sem conferir o tríduo"
                assert "motivo_atraso" in kw, f"{arquivo.name}:{no.lineno}"
    assert chamadas >= 2

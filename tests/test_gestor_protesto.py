"""O agente do Protesto (`gestor_protesto`) — pedido do oficial em 09/10/2026.

O que se prova aqui: a conta do tríduo é a da inspeção 0000524 (protocolo
2603190001), o protesto devido não lavrado vira prazo, o protesto indevido vira
CRÍTICO, o acervo anterior ao corte não vira tarefa, o falso positivo medido na
produção (remessa cuja confirmação não ficou na pasta) não volta, e o módulo
não escreve nada.
"""
from __future__ import annotations

import ast
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import gestor_conferencia as GC  # noqa: E402
import gestor_protesto as GP  # noqa: E402
import gestor_rotina as GR  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

HOJE = date(2026, 10, 9)


def _fluxo(**kw) -> dict:
    base = {"remessa": {}, "confirmado": {}, "retorno": {}, "desistencia": {},
            "respondido": set(), "arquivos": 0, "ilegiveis": []}
    base.update(kw)
    from collections import defaultdict
    base["retorno"] = defaultdict(list, base["retorno"])
    return base


def _conf(apontado: date, **kw) -> dict:
    t = {"apresentante": "1LV", "nosso_numero": "N1", "numero_do_titulo": "T1",
         "devedor": "FULANO", "documento": "", "tipo_documento": "",
         "vencimento": None, "especie": "DMI", "arquivo": "C1LV.261",
         "dia_remessa": apontado, "gerado_em": apontado, "apontado": apontado,
         "ocorrencia": ""}
    t.update(kw)
    return t


def _ret(oc: str, quando: date, enviado: date | None = None) -> dict:
    return {"ocorrencia": oc, "data": quando, "enviado": enviado or quando,
            "arquivo": "R.261", "apresentante": "1LV", "apontado": None}


def _banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def _regras(achados) -> dict:
    saida: dict = {}
    for a in achados:
        saida.setdefault(a["regra"], []).append(a)
    return saida


# --------------------------------------------------------------- a conta

def test_o_triduo_e_a_conta_que_a_inspecao_fez():
    """Protocolo 2603190001: protocolizado numa quinta (19/03/2026), o tríduo
    termina na terça, 24/03 — palavras do relatório da inspeção 0000524."""
    assert GP._uteis(date(2026, 3, 19), 3, set()) == date(2026, 3, 24)
    # e o de 05/08/2026 (quarta) termina em 10/08 (segunda)
    assert GP._uteis(date(2026, 8, 5), 3, set()) == date(2026, 8, 10)


def test_a_data_do_apontamento_sai_do_protocolo():
    assert GP._data_do_protocolo(2610070015) == date(2026, 10, 7)
    assert GP._data_do_protocolo("", "2026-09-15") == date(2026, 9, 15)


# ------------------------------------------------- o fluxo da CRA

def test_triduo_vencido_sem_retorno_e_protesto_devido():
    fluxo = _fluxo(confirmado={"2610020001": _conf(date(2026, 10, 2))})
    r = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))
    [a] = r["PROTESTO_SEM_RESPOSTA"]
    assert a["gravidade"] == "VENCIDO" and a["setor"] == "PROTESTO"
    assert a["prazo"] == "2026-10-08"        # retorno até o dia útil seguinte ao tríduo


def test_dentro_do_triduo_nao_cobra():
    fluxo = _fluxo(confirmado={"2610070001": _conf(date(2026, 10, 7))})
    assert "PROTESTO_SEM_RESPOSTA" not in _regras(
        GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))


def test_pago_retirado_ou_sustado_nao_cobra():
    for oc in ("1", "3", "4", "C"):
        fluxo = _fluxo(confirmado={"2610020001": _conf(date(2026, 10, 2))},
                       retorno={"2610020001": [_ret(oc, date(2026, 10, 5))]})
        assert "PROTESTO_SEM_RESPOSTA" not in _regras(
            GP._regras_do_fluxo(_banco(), fluxo, HOJE, set())), oc


def test_antes_do_corte_nao_vira_tarefa():
    fluxo = _fluxo(confirmado={"2607200001": _conf(date(2026, 7, 20))})
    r = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))
    assert "PROTESTO_SEM_RESPOSTA" not in r
    assert "PROTESTO_ANTES_DO_CORTE" in GP.REGRAS_SEM_TAREFA
    assert "2607200001" in r["PROTESTO_ANTES_DO_CORTE"][0]["detalhe"]


def test_protesto_depois_de_pago_e_indevido():
    p = "2609210001"
    fluxo = _fluxo(confirmado={p: _conf(date(2026, 9, 21))},
                   retorno={p: [_ret("1", date(2026, 9, 22)), _ret("C", date(2026, 9, 24))]})
    [a] = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))["PROTESTO_INDEVIDO"]
    assert a["gravidade"] == "CRITICO" and "pago" in a["detalhe"]


def test_protesto_depois_da_desistencia_e_indevido():
    p = "2609210001"
    fluxo = _fluxo(confirmado={p: _conf(date(2026, 9, 21))},
                   retorno={p: [_ret("C", date(2026, 9, 24))]},
                   desistencia={p: {"dia": date(2026, 9, 23), "arquivo": "DP.261"}})
    [a] = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))["PROTESTO_INDEVIDO"]
    assert "desistiu" in a["detalhe"]


def test_protesto_no_dia_do_apontamento_e_antes_do_vencimento():
    p = "2609210001"
    fluxo = _fluxo(confirmado={p: _conf(date(2026, 9, 21), vencimento=date(2026, 9, 30))},
                   retorno={p: [_ret("C", date(2026, 9, 21))]})
    [a] = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))["PROTESTO_INDEVIDO"]
    assert "dia do apontamento" in a["detalhe"] and "vencia" in a["detalhe"]


def test_protesto_regular_nao_acusa():
    p = "2609210001"
    fluxo = _fluxo(confirmado={p: _conf(date(2026, 9, 21))},
                   retorno={p: [_ret("C", date(2026, 9, 24), date(2026, 9, 25))]})
    r = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))
    assert not ({"PROTESTO_INDEVIDO", "PROTESTO_FORA_DO_TRIDUO",
                 "PROTESTO_RETORNO_TARDIO", "PROTESTO_SEM_RESPOSTA"} & set(r))


def test_protesto_depois_do_triduo_e_relatado_sem_tarefa():
    p = "2609140001"
    fluxo = _fluxo(confirmado={p: _conf(date(2026, 9, 14))},
                   retorno={p: [_ret("C", date(2026, 9, 18))]})
    r = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))
    assert r["PROTESTO_FORA_DO_TRIDUO"][0]["gravidade"] == "ATENCAO"
    assert "PROTESTO_FORA_DO_TRIDUO" in GP.REGRAS_SEM_TAREFA


def test_remessa_sem_resposta_vira_prazo_e_o_andamento_a_resolve():
    """O falso positivo medido em 09/10/2026: a remessa 987 de 10/09 não tem
    confirmação salva na pasta, e aparece no andamento e no retorno."""
    chave = ("987", "25516588364")
    t = {"apresentante": "987", "nosso_numero": "25516588364", "numero_do_titulo": "X",
         "devedor": "D", "dia": date(2026, 9, 22), "arquivo": "B987.261"}
    r = _regras(GP._regras_do_fluxo(_banco(), _fluxo(remessa={chave: t}), HOJE, set()))
    assert r["PROTESTO_REMESSA_SEM_CONFIRMACAO"][0]["gravidade"] == "VENCIDO"
    r = _regras(GP._regras_do_fluxo(_banco(), _fluxo(remessa={chave: t}, respondido={chave}),
                                    HOJE, set()))
    assert "PROTESTO_REMESSA_SEM_CONFIRMACAO" not in r


def test_le_os_arquivos_reais_da_cra(tmp_path):
    """Os exemplos reais da pasta de testes, com o nome que a CRA dá (.261)."""
    for nome, novo in (("cra_remessa_exemplo.txt", "B0011108.261"),
                       ("cra_confirmacao_exemplo.txt", "C0011108.261"),
                       ("cra_retorno_exemplo.txt", "R0011108.261"),
                       ("cra_desistencia_exemplo.txt", "DP0011108.261")):
        shutil.copy(RAIZ / "tests" / nome, tmp_path / novo)
    fluxo = GP.ler_fluxo_da_cra(tmp_path, HOJE)
    assert fluxo["ilegiveis"] == []
    assert fluxo["arquivos"] == 4
    assert fluxo["confirmado"] and fluxo["retorno"] and fluxo["desistencia"]


def test_pasta_que_nao_existe_e_nao_mediu(tmp_path):
    achados = GP.conferir(_banco(), HOJE, pasta_cra=tmp_path / "nao_ha")
    [a] = _regras(achados)["PROTESTO_PASTA_CRA"]
    assert a["gravidade"] == "NAO_MEDIU"


# ------------------------------------------------- o que se lavra aqui

def _titulo(con, protocolo, situacao="APONTADO", vencimento=None) -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, protocolo, situacao,
               data_vencimento, criado_em) VALUES ('DMI','T',?,?,?,'2026-10-01')""",
        (protocolo, situacao, vencimento))
    return cur.lastrowid


def _ato(con, tid, tipo, dia, detalhe="{}") -> int:
    cur = con.execute("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                             criado_em) VALUES (?,?,?,?,'2026-10-01')""",
                      (tid, tipo, dia, detalhe))
    return cur.lastrowid


def test_protesto_sem_intimacao_e_com_sustacao_e_indevido():
    con = _banco()
    tid = _titulo(con, "2609210001", "PROTESTADO")
    _ato(con, tid, "APONTAMENTO", "2026-09-21")
    _ato(con, tid, "SUSTACAO", "2026-09-22", '{"juizo":"1a Vara","processo":"1"}')
    _ato(con, tid, "PROTESTO", "2026-09-24")
    [a] = _regras(GP._regras_do_sistema(con, HOJE, set()))["PROTESTO_INDEVIDO"]
    assert a["gravidade"] == "CRITICO"
    assert "intimação" in a["detalhe"] and "sustação" in a["detalhe"]


def test_titulo_parado_depois_do_triduo_e_o_que_a_cra_ja_recebeu_nao():
    con = _banco()
    tid = _titulo(con, "2609210001")
    _ato(con, tid, "APONTAMENTO", "2026-09-21")
    r = _regras(GP._regras_do_sistema(con, HOJE, set()))
    assert r["PROTESTO_TITULO_PARADO"][0]["gravidade"] == "VENCIDO"
    r = _regras(GP._regras_do_sistema(con, HOJE, set(), frozenset({"2609210001"})))
    assert "PROTESTO_TITULO_PARADO" not in r


def test_certidao_negativa_sobre_quem_tinha_protesto():
    con = _banco()
    tid = _titulo(con, "2609210001", "PROTESTADO")
    con.execute("""INSERT INTO pt_devedores(titulo_id, nome, documento_numero)
                   VALUES (?, 'FULANO', '000.000.048-55')""", (tid,))
    _ato(con, tid, "APONTAMENTO", "2026-09-21")
    _ato(con, tid, "INTIMACAO", "2026-09-22", '{"modo":"PESSOAL"}')
    _ato(con, tid, "PROTESTO", "2026-09-24")
    con.execute("""INSERT INTO pt_certidoes(numero, ano, tipo, nome, documento, teor,
                       emitida_em) VALUES (1, 2026, 'NEGATIVA', 'FULANO', '00000004855',
                       'x', '2026-10-01T10:00:00')""")
    r = _regras(GP._regras_do_sistema(con, HOJE, set()))
    assert r["PROTESTO_CERTIDAO_NEGATIVA_INDEVIDA"][0]["gravidade"] == "CRITICO"


# ------------------------------------------------- a ligação com o gestor

def test_esta_ligado_na_conferencia_e_na_rotina():
    assert any(nome == "PROTESTO" for nome, _ in GC.REGRAS)
    assert GP.REGRAS_SEM_TAREFA <= GR.REGRAS_SEM_TAREFA
    for regra in GP.ROTULOS:
        assert GR.ROTULOS.get(regra) == GP.ROTULOS[regra]


def test_o_agente_nao_escreve_nada():
    arvore = ast.parse((RAIZ / "gestor_protesto.py").read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            texto = no.value.upper()
            for verbo in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
                assert verbo not in texto, (verbo, no.value[:60])

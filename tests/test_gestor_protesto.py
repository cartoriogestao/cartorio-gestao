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

import pytest

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
    # Apontado na segunda 14/09: prazo-limite na quinta 17/09, protesto na
    # sexta 18/09 (o dia útil seguinte, decisão do oficial de 27/10/2026).
    # O de segunda, 21/09, já é depois.
    p = "2609140001"
    fluxo = _fluxo(confirmado={p: _conf(date(2026, 9, 14))},
                   retorno={p: [_ret("C", date(2026, 9, 21))]})
    r = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))
    assert r["PROTESTO_FORA_DO_TRIDUO"][0]["gravidade"] == "ATENCAO"
    assert "PROTESTO_FORA_DO_TRIDUO" in GP.REGRAS_SEM_TAREFA


def test_protesto_no_dia_util_seguinte_ao_prazo_limite_nao_e_fora_do_triduo():
    """Decisão do oficial em 27/10/2026: «no dia útil seguinte». Até essa data
    o protesto da sexta 18/09 (apontado na segunda 14/09) era acusado — e ele
    é, agora, o protesto no dia certo."""
    p = "2609140001"
    fluxo = _fluxo(confirmado={p: _conf(date(2026, 9, 14))},
                   retorno={p: [_ret("C", date(2026, 9, 18))]})
    r = _regras(GP._regras_do_fluxo(_banco(), fluxo, HOJE, set()))
    assert "PROTESTO_FORA_DO_TRIDUO" not in r


def test_o_protesto_lavrado_aqui_segue_a_regua_do_triduo():
    """Apontado na segunda 21/09, intimado na terça: o devedor paga até a
    quinta 24/09 e o protesto é na sexta 25/09 — no prazo. O de segunda, 28/09,
    é depois. E quando o ato gravou a conta do tríduo, vale a conta dele."""
    con = _banco()
    no_dia = _titulo(con, "2609210001", "PROTESTADO")
    _ato(con, no_dia, "APONTAMENTO", "2026-09-21")
    _ato(con, no_dia, "INTIMACAO", "2026-09-22", '{"modo":"PESSOAL"}')
    _ato(con, no_dia, "PROTESTO", "2026-09-25")
    depois = _titulo(con, "2609210002", "PROTESTADO")
    _ato(con, depois, "APONTAMENTO", "2026-09-21")
    _ato(con, depois, "INTIMACAO", "2026-09-22", '{"modo":"PESSOAL"}')
    _ato(con, depois, "PROTESTO", "2026-09-28")
    revogada = _titulo(con, "2609210003", "PROTESTADO")
    _ato(con, revogada, "APONTAMENTO", "2026-09-21")
    _ato(con, revogada, "INTIMACAO", "2026-09-22", '{"modo":"PESSOAL"}')
    _ato(con, revogada, "PROTESTO", "2026-09-30",
         '{"triduo": {"situacao": "NO_PRAZO", "termo_final": "2026-09-30"}}')
    r = _regras(GP._regras_do_sistema(con, HOJE, set()))
    acusados = {a["chave"] for a in r.get("PROTESTO_FORA_DO_TRIDUO", [])}
    ids = {int(c.split(":")[1]) for c in acusados}
    linha = {int(x[0]) for x in con.execute(
        "SELECT id FROM pt_atos WHERE tipo='PROTESTO' AND titulo_id=?", (depois,))}
    assert ids == linha


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


def test_pasta_que_nao_existe_so_segura_o_acervo(tmp_path):
    """Desde a virada a pasta é só o acervo do E-Ofício: sem ela, o dia da CRA
    continua medido no banco, e o que só a pasta media fica SEGURO — e não
    resolvido (PR004)."""
    achados = GP.conferir(_banco(), HOJE, pasta_cra=tmp_path / "nao_ha")
    [a] = _regras(achados)["PROTESTO_PASTA_CRA"]
    assert a["gravidade"] == "ATENCAO"
    assert "PROTESTO_PASTA_CRA" in GP.REGRAS_SEM_TAREFA
    assert GC.esta_segurado(a["segura"], "PROTESTO_INDEVIDO", "PT_INDEVIDO:2609210001")
    assert not GC.esta_segurado(a["segura"], "PROTESTO_INDEVIDO", "PT_INDEVIDO_ATO:7")
    assert not GC.esta_segurado(a["segura"], "PROTESTO_SEM_RESPOSTA", "PT_RESPOSTA_ATO:7")
    assert not any(x["gravidade"] == "NAO_MEDIU" for x in achados)


def test_sem_pasta_configurada_nao_ha_achado_da_pasta():
    assert "PROTESTO_PASTA_CRA" not in _regras(GP.conferir(_banco(), HOJE))


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


# ---------------------------------- PR004: o fluxo da CRA lido do banco

DEPOIS = date(2026, 11, 17)       # uma terça, bem depois da virada


def _titulo_da_cra(con, protocolo, situacao="PROTESTADO", *, remessa_id=None,
                   nosso="N" + "1") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero, protocolo,
               situacao, origem, apresentante_codigo, remessa_id, criado_em)
           VALUES ('DMI', 'T', ?, ?, ?, 'CRA', '001', ?, '2026-10-20')""",
        (nosso, protocolo, situacao, remessa_id))
    return cur.lastrowid


def _retorno(con, tipo="SDTBFORTP", *, enviado=None, recusado=None,
             gerado="2026-10-27T10:00:00", ambiente=None) -> int:
    cur = con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia, nome_arquivo, conteudo,
               gerado_em, cra_enviado_em, cra_recusado_em, cra_enviado_ambiente)
           VALUES (?, '001', ?, 'R001.261', 'x', ?, ?, ?, ?)""",
        (tipo, gerado[:10], gerado, enviado, recusado, ambiente))
    return cur.lastrowid


def _ato_ligado(con, tid, tipo, dia, *, retorno_id=None, selo=None, origem="MANUAL",
                cancelado=0) -> int:
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, retorno_id, selo, origem,
               cancelado, criado_em, criado_por)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Escrevente Exemplo')""",
        (tid, tipo, dia, retorno_id, selo, origem, cancelado, dia))
    return cur.lastrowid


def _cra(con, hoje=DEPOIS) -> dict:
    return _regras(GP._regras_da_cra_no_banco(con, hoje, set()))


def test_a_virada_e_a_do_roteiro():
    import protesto_roteiro as PRT
    assert GP.VIRADA == PRT.VIRADA_DO_PROTESTO


def test_ato_final_que_a_cra_nao_tem_e_sem_resposta():
    """O protesto de 26/10 sem arquivo, e o de 27/10 num arquivo que a CRA não
    aceitou: os dois vencidos. O do arquivo aceito, não."""
    con = _banco()
    sem_arquivo = _ato_ligado(con, _titulo_da_cra(con, "2610209901"), "PROTESTO", "2026-10-26")
    preso = _ato_ligado(con, _titulo_da_cra(con, "2610209902"), "PROTESTO", "2026-10-27",
                        retorno_id=_retorno(con))
    _ato_ligado(con, _titulo_da_cra(con, "2610209903"), "PROTESTO", "2026-10-27",
                retorno_id=_retorno(con, enviado="2026-10-28T10:00:00"))
    r = _cra(con)
    chaves = {a["chave"]: a for a in r["PROTESTO_SEM_RESPOSTA"]}
    assert set(chaves) == {f"PT_RESPOSTA_ATO:{sem_arquivo}", f"PT_RESPOSTA_ATO:{preso}"}
    assert all(a["gravidade"] == "VENCIDO" for a in chaves.values())
    assert chaves[f"PT_RESPOSTA_ATO:{sem_arquivo}"]["prazo"] == "2026-10-27"
    assert "não foi aceito" in chaves[f"PT_RESPOSTA_ATO:{preso}"]["detalhe"]


def test_sem_resposta_espera_o_dia_util_seguinte_e_a_virada():
    con = _banco()
    _ato_ligado(con, _titulo_da_cra(con, "2611169901"), "PROTESTO", "2026-11-16")
    _ato_ligado(con, _titulo_da_cra(con, "2610059901"), "PROTESTO", "2026-10-05")
    assert "PROTESTO_SEM_RESPOSTA" not in _cra(con, date(2026, 11, 17))
    assert [a["chave"] for a in _cra(con, date(2026, 11, 18))["PROTESTO_SEM_RESPOSTA"]] \
        == ["PT_RESPOSTA_ATO:1"]


def test_marca_manual_e_titulo_que_nao_veio_da_cra_nao_cobram():
    con = _banco()
    tid = _titulo_da_cra(con, "2610209901")
    a = _ato_ligado(con, tid, "PROTESTO", "2026-10-26")
    con.execute("UPDATE pt_atos SET cra_ja_informado_em='2026-10-27T09:00:00' WHERE id=?", (a,))
    balcao = _titulo_da_cra(con, "2610209902")
    con.execute("UPDATE pt_titulos SET origem='MANUAL' WHERE id=?", (balcao,))
    _ato_ligado(con, balcao, "PROTESTO", "2026-10-26")
    assert "PROTESTO_SEM_RESPOSTA" not in _cra(con)
    assert GP.informados_a_cra(con) == frozenset({"2610209901"})


def _remessa(con, recebida="2026-10-27T10:00:00", confirmacao_id=None) -> int:
    cur = con.execute(
        """INSERT INTO pt_remessas(tipo, apresentante_codigo, dia, nome_arquivo, conteudo,
               hash_arquivo, recebida_em, confirmacao_id)
           VALUES ('BFOSDTTPR', '001', ?, 'B001.261', 'x', ?, ?, ?)""",
        (recebida[:10], f"h{recebida}{confirmacao_id}", recebida, confirmacao_id))
    return cur.lastrowid


def test_remessa_sem_confirmacao_aceita_ou_titulo_nao_apontado():
    con = _banco()
    sem_conf = _remessa(con)
    _titulo_da_cra(con, "2610279901", "APONTADO", remessa_id=sem_conf, nosso="A1")
    recusada = _remessa(con, "2026-10-27T11:00:00",
                        _retorno(con, "SDTBFOCRT", recusado="2026-10-27T14:00:00"))
    _titulo_da_cra(con, "2610279902", "APONTADO", remessa_id=recusada, nosso="A2")
    certa = _remessa(con, "2026-10-27T12:00:00",
                     _retorno(con, "SDTBFOCRT", enviado="2026-10-27T13:00:00"))
    _titulo_da_cra(con, "2610279903", "APONTADO", remessa_id=certa, nosso="A3")
    _titulo_da_cra(con, None, "RECEBIDO", remessa_id=certa, nosso="A4")
    assert "PROTESTO_REMESSA_SEM_CONFIRMACAO" not in _cra(con, date(2026, 10, 27))
    r = {a["chave"]: a for a in _cra(con, date(2026, 10, 28))["PROTESTO_REMESSA_SEM_CONFIRMACAO"]}
    assert set(r) == {"PT_REMESSA:001:A1", "PT_REMESSA:001:A2", "PT_REMESSA:001:A4"}
    assert "não foi apontado" in r["PT_REMESSA:001:A4"]["detalhe"]
    assert r["PT_REMESSA:001:A1"]["gravidade"] == "VENCIDO"


def _pedido(con, tipo, estado, recebido, titulo_id=None, protocolo="2611109901") -> int:
    c = con.execute(
        """INSERT INTO pt_cra_consultas(tipo, operacao, pedida_em, resultado)
           VALUES (?, 'Desistencia', ?, 'RECEBIDO')""", (tipo, recebido)).lastrowid
    return con.execute(
        """INSERT INTO pt_cra_pedidos(consulta_id, tipo, chave, protocolo, titulo_id,
               estado, recebido_em) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (c, tipo, f"{tipo}:{protocolo}:{estado}", protocolo, titulo_id, estado,
         recebido)).lastrowid


def test_desistencia_da_cra_aberta_depois_do_dia_util_seguinte():
    con = _banco()
    tid = _titulo_da_cra(con, "2611109901", "APONTADO")
    _pedido(con, "DP", "PENDENTE", "2026-11-13T13:16:00", tid)
    _pedido(con, "DP", "APLICADO", "2026-11-13T13:16:00", None, "2611109909")
    assert "PROTESTO_DESISTENCIA_SEM_BAIXA" not in _cra(con, date(2026, 11, 16))
    [a] = _cra(con, date(2026, 11, 17))["PROTESTO_DESISTENCIA_SEM_BAIXA"]
    assert a["chave"] == "PT_DESIST:2611109901" and a["gravidade"] == "VENCIDO"
    assert a["prazo"] == "2026-11-16"


def test_retorno_aceito_depois_das_11h30_do_dia_util_seguinte_e_tardio():
    con = _banco()
    _ato_ligado(con, _titulo_da_cra(con, "2610289901"), "PROTESTO", "2026-10-28",
                retorno_id=_retorno(con, enviado="2026-10-30T10:12:00"))
    _ato_ligado(con, _titulo_da_cra(con, "2610289902"), "PROTESTO", "2026-10-28",
                retorno_id=_retorno(con, enviado="2026-10-29T11:29:00"))
    _ato_ligado(con, _titulo_da_cra(con, "2610289903"), "PROTESTO", "2026-10-28",
                retorno_id=_retorno(con, enviado="2026-10-29T11:41:00"))
    [a] = _cra(con)["PROTESTO_RETORNO_TARDIO"]
    assert a["titulo"].startswith("2 ato(s)")
    assert "2610289901" in a["detalhe"] and "2610289903" in a["detalhe"]
    assert "2610289902" not in a["detalhe"]
    assert "PROTESTO_RETORNO_TARDIO" in GP.REGRAS_SEM_TAREFA


def test_o_banco_alimenta_o_titulo_parado():
    """O protocolo que a CRA já tem não está parado, como antes com a pasta."""
    con = _banco()
    tid = _titulo_da_cra(con, "2610209901", "APONTADO")
    _ato(con, tid, "APONTAMENTO", "2026-10-20")
    outro = _titulo_da_cra(con, "2610209901", "PAGO", nosso="N2")
    _ato_ligado(con, outro, "PAGAMENTO", "2026-10-21",
                retorno_id=_retorno(con, enviado="2026-10-22T10:00:00"))
    assert "PROTESTO_TITULO_PARADO" not in _regras(GP.conferir(con, DEPOIS))


def test_o_fluxo_que_quebra_segura_os_achados_dele(monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("coluna errada")
    monkeypatch.setattr(GP, "_regras_da_cra_no_banco", quebra)
    [a] = _regras(GP.conferir(_banco(), DEPOIS))["PROTESTO_CRA"]
    assert a["gravidade"] == "NAO_MEDIU" and "coluna errada" in a["detalhe"]
    for regra in GP.REGRAS_DA_CRA:
        assert GC.esta_segurado(a["segura"], regra, "qualquer")
    assert not GC.esta_segurado(a["segura"], "PROTESTO_INDEVIDO", "PT_INDEVIDO_ATO:1")


def test_tabela_que_falta_e_nao_mediu_e_nao_zero(monkeypatch):
    con = _banco()
    real = GP._tem_tabela
    monkeypatch.setattr(GP, "_tem_tabela", lambda c, t: t != "pt_cra_pedidos" and real(c, t))
    [a] = _regras(GP.conferir(con, DEPOIS))["PROTESTO_CRA"]
    assert "pt_cra_pedidos" in a["detalhe"]


# ---------------------------------- PR004: não medir não é resolver

def _rotina() -> sqlite3.Connection:
    from gestor_schema import init_gestor_schema
    con = _banco()
    init_gestor_schema(con)
    return con


def _achado(chave, regra="PROTESTO_SEM_RESPOSTA", gravidade="VENCIDO"):
    return GC._achado(chave, regra, gravidade, "PROTESTO", "t", "d")


def _abertos(con) -> set:
    return {r[0] for r in con.execute(
        "SELECT chave FROM ge_achados WHERE resolvido_em IS NULL ORDER BY id")}


def test_o_achado_aberto_nao_se_resolve_quando_a_regra_deixa_de_medir():
    """O 29/10/2026 que não se repete: a regra parou de medir, e os achados
    dela foram dados por resolvidos (auditoria PR003, achado P5)."""
    con = _rotina()
    GR.gravar_achados(con, [_achado("PT_RESPOSTA_ATO:1"), _achado("OUTRO", "PROTESTO_INDEVIDO")],
                      DEPOIS)
    nao_mediu = GC.segura(GC._achado("NAO_MEDIU:PROTESTO_CRA", "PROTESTO_CRA", "NAO_MEDIU",
                                     "TI", "t"), *GP.REGRAS_DA_CRA)
    r = GR.gravar_achados(con, [nao_mediu], DEPOIS)
    assert r["segurados"] == 1 and r["resolvidos"] == 1
    assert _abertos(con) == {"PT_RESPOSTA_ATO:1", "NAO_MEDIU:PROTESTO_CRA"}
    # voltou a medir, e não achou: aí sim está resolvido
    GR.gravar_achados(con, [], DEPOIS)
    assert _abertos(con) == set()


@pytest.fixture()
def casa_con(cg_casa):
    """O banco inteiro da casa (tarefas, caixa, selo) — o dos testes legados.
    Fecha no fim: conexão aberta segura o banco que o teste seguinte restaura."""
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    yield con
    con.rollback()
    con.close()


def test_a_tarefa_da_regra_que_nao_mediu_nao_fecha(casa_con):
    con = casa_con
    item = _achado("PT_RESPOSTA_ATO:1")
    GR.sincronizar_tarefas(con, [item], {}, DEPOIS)
    ref = "GESTOR:PROTESTO_SEM_RESPOSTA:PROTESTO"
    situacao = lambda: con.execute(  # noqa: E731
        "SELECT status FROM tasks WHERE source_ref=?", (ref,)).fetchone()[0]
    assert situacao() == "ABERTA"
    nao_mediu = GC.segura(GC._achado("NAO_MEDIU:PROTESTO_CRA", "PROTESTO_CRA", "NAO_MEDIU",
                                     "TI", "t"), *GP.REGRAS_DA_CRA)
    GR.sincronizar_tarefas(con, [nao_mediu], {}, DEPOIS)
    assert situacao() == "ABERTA"
    GR.sincronizar_tarefas(con, [], {}, DEPOIS)
    assert situacao() == "CONCLUIDA"


def test_a_tarefa_da_regra_com_achado_seguro_pela_chave_nao_fecha(casa_con):
    """O sistema do Protesto que quebra segura pelas chaves (`PT_PARADO:*`), e
    a regra do título parado também nasce de outras partes."""
    con = casa_con
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    item = _achado("PT_PARADO:1", "PROTESTO_TITULO_PARADO")
    GR.gravar_achados(con, [item], DEPOIS)
    GR.sincronizar_tarefas(con, [item], {}, DEPOIS)
    nao_mediu = GC.segura(GC._achado("NAO_MEDIU:PROTESTO_SISTEMA", "PROTESTO_SISTEMA",
                                     "NAO_MEDIU", "TI", "t"), *GP.CHAVES_DO_SISTEMA)
    GR.gravar_achados(con, [nao_mediu], DEPOIS)
    GR.sincronizar_tarefas(con, [nao_mediu], {}, DEPOIS)
    [(status,)] = con.execute("SELECT status FROM tasks WHERE source_ref=?",
                              ("GESTOR:PROTESTO_TITULO_PARADO:PROTESTO",)).fetchall()
    assert status == "ABERTA"
    assert "PT_PARADO:1" in _abertos(con)


def test_regra_da_conferencia_que_quebra_segura_o_que_ela_aponta(monkeypatch):
    def quebra(con, hoje):
        raise RuntimeError("caiu")
    regras = [("PROTESTO", quebra), ("SIRC", quebra)]
    monkeypatch.setattr(GC, "REGRAS", tuple(regras))
    achados = {a["regra"]: a for a in GC.conferir(_rotina(), DEPOIS)}
    assert GC.esta_segurado(achados["PROTESTO"]["segura"], "PROTESTO_ATO_SEM_SELO", "x")
    assert GC.esta_segurado(achados["SIRC"]["segura"], "SIRC", "x")
    assert not GC.esta_segurado(achados["SIRC"]["segura"], "SIRC_CANCELAMENTO", "x")


# ---------------------------------- PR004: o selo dos atos de protesto

def test_ato_de_protesto_vivo_sem_selo_nem_cobertura_e_achado(casa_con):
    con = casa_con
    tid = _titulo_da_cra(con, "2610279901", "INTIMADO")
    sem = _ato_ligado(con, tid, "INTIMACAO", "2026-10-27")
    desist = _ato_ligado(con, tid, "DESISTENCIA", "2026-10-30")
    _ato_ligado(con, tid, "APONTAMENTO", "2026-10-27")                  # não sela
    _ato_ligado(con, tid, "AVERBACAO_RETIFICACAO", "2026-10-29")         # não sela
    _ato_ligado(con, tid, "INTIMACAO", "2026-10-27", selo="ABC12345")
    _ato_ligado(con, tid, "INTIMACAO", "2026-10-27", origem="EOFICIO")
    _ato_ligado(con, tid, "INTIMACAO", "2026-10-27", cancelado=1)
    _ato_ligado(con, tid, "INTIMACAO", "2026-09-30")                     # antes da virada
    no_razao = _ato_ligado(con, tid, "INTIMACAO", "2026-10-28")
    con.execute("""INSERT INTO sd_selos(numero, tabela, ato_id, obtido_em)
                   VALUES ('SELO1', 'pt_atos', ?, '2026-10-28')""", (no_razao,))
    razao_cancelado = _ato_ligado(con, tid, "INTIMACAO", "2026-10-28")
    con.execute("""INSERT INTO sd_selos(numero, tabela, ato_id, obtido_em, cancelado_em)
                   VALUES ('SELO2', 'pt_atos', ?, '2026-10-28', '2026-10-28')""",
                (razao_cancelado,))
    coberto = _ato_ligado(con, tid, "PAGAMENTO", "2026-10-28")
    con.execute("""INSERT INTO cx_selo_coberturas(referencia, tabela, ato_id, forma, criado_em)
                   VALUES ('ref-1', 'pt_atos', ?, 'PAGO', '2026-10-28')""", (coberto,))
    achados = _regras(GP.conferir(con, DEPOIS))["PROTESTO_ATO_SEM_SELO"]
    assert {a["chave"] for a in achados} == {
        f"SEM_SELO:pt_atos:{sem}", f"SEM_SELO:pt_atos:{desist}",
        f"SEM_SELO:pt_atos:{razao_cancelado}"}
    assert all(a["setor"] == "PROTESTO" for a in achados)
    # vira tarefa (é o selo que falta), e o corte do «ato lavrado» não o tira
    assert "PROTESTO_ATO_SEM_SELO" not in GR.REGRAS_SEM_TAREFA
    assert "PROTESTO_ATO_SEM_SELO" not in GC.RETIRADAS_DO_ATO_LAVRADO
    assert GC.so_o_essencial(con, achados) == achados

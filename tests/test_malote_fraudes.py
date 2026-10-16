"""Do malote para a lista de fraudes — 13/10/2026.

O que se guarda: a proposta leva a referência inteira do aviso (pedido do
oficial: «guarde a referência de onde veio o aviso de fraude»); nada entra na
lista sem aprovação; descartar exige motivo; aplicar usa a porta da casa e não
repete o alerta.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import malote_fraudes as MF                                      # noqa: E402

AVISO = {"codigo_malote": "81020265958952", "documento_malote": "CIRC-CSERVCOGEX_0002026.pdf",
         "assunto": "Suspeita de fraude em procuração pública", "remetente": "Coordenadoria Exemplo — TJMA",
         "enviado_em": "2026-10-13 10:59:18", "processos": "717762026; 0002737-02.2026.2.00.0806",
         "arquivo": r"arquivos\malote\entrada\CIRC\x.pdf", "resumo": "Procuração falsa em Cidade Exemplo/CE."}


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _p(**kw):
    p = dict(AVISO)
    p.update({"nome": "FULANO DE TAL EXEMPLO", "documento": None, "papel": "ENVOLVIDO",
              "trecho": "inquérito em face de FULANO DE TAL EXEMPLO"})
    p.update(kw)
    return p


def test_a_referencia_leva_codigo_documento_processo_e_trecho():
    r = MF.referencia(_p())
    assert r["origem"].startswith("Malote Digital nº 81020265958952")
    assert "CIRC-CSERVCOGEX_0002026.pdf" in r["origem"] and "717762026" in r["origem"]
    assert r["origem_data"] == "2026-10-13" and r["origem_orgao"].startswith("Coordenadoria")
    assert "Trecho: «inquérito em face de" in r["observacao"] and "Arquivo nesta casa" in r["observacao"]


def test_proposta_nao_entra_na_lista_sem_aprovacao(con):
    assert MF.carregar(con, [_p(), _p()]) == {"novas": 1, "repetidas": 1}
    assert MF.aplicar(con, usuario="mario") == {"incluidos": 0, "ja_havia": 0}
    assert con.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 0


def test_aprovada_vira_alerta_com_a_referencia_e_nao_repete(con):
    MF.carregar(con, [_p(), _p(nome="BELTRANA EXEMPLO", papel="VITIMA", documento="000.000.001-91")])
    ids = [r[0] for r in con.execute("SELECT id FROM mt_alertas_propostos")]
    assert MF.revisar(con, ids, aprovar=True, revisor="mario") == 2
    assert MF.aplicar(con, usuario="mario") == {"incluidos": 2, "ja_havia": 0}
    a = con.execute("SELECT * FROM fr_alertas WHERE papel='VITIMA'").fetchone()
    assert a["documento"] == "00000000191" and a["origem"].startswith("Malote Digital nº 81020265958952")
    assert a["origem_data"] == "2026-10-13" and "Trecho:" in a["observacao"]
    assert con.execute("SELECT count(*) FROM mt_alertas_propostos WHERE situacao='APLICADO' "
                       "AND alerta_id IS NOT NULL").fetchone()[0] == 2
    # a mesma pessoa do mesmo aviso, proposta e aprovada de novo, não vira segundo alerta
    con.execute("DELETE FROM mt_alertas_propostos")
    MF.carregar(con, [_p()])
    MF.revisar(con, [con.execute("SELECT id FROM mt_alertas_propostos").fetchone()[0]], aprovar=True, revisor="mario")
    assert MF.aplicar(con, usuario="mario") == {"incluidos": 0, "ja_havia": 1}
    assert con.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 2


def test_descartar_exige_motivo(con):
    MF.carregar(con, [_p()])
    i = con.execute("SELECT id FROM mt_alertas_propostos").fetchone()[0]
    with pytest.raises(MF.PropostaError, match="motivo"):
        MF.revisar(con, [i], aprovar=False, revisor="mario")
    assert MF.revisar(con, [i], aprovar=False, revisor="mario", motivo="homônimo, não é a pessoa") == 1


def test_papel_desconhecido_recusa(con):
    with pytest.raises(MF.PropostaError, match="Papel"):
        MF.carregar(con, [_p(papel="SUSPEITO")])


def test_a_pagina_mostra_a_referencia_e_o_trecho():
    html = MF.pagina_de_revisao([_p(id=1)])
    assert "Malote Digital nº 81020265958952" in html and "inquérito em face de" in html


# ================================================== PELA IA INTERNA (13/10/2026)
# «quando for fraude, apenas cadastrar em fraudes, sem tarefa» … «nem tarefa,
# nem expediente» … «pode ser a ia interna». O que se guarda: banco não entra;
# marca que não volta a ser nome não entra; documento que não confere entra só
# pelo nome; o que sai para a IA vai mascarado e volta com o número.

import json                                                       # noqa: E402
import re                                                         # noqa: E402


def test_a_regua_de_quem_entra():
    boas, fora = MF.pessoas_validas([
        {"nome": "FULANO DE TAL EXEMPLO", "documento": "000.000.001-91", "papel": "ENVOLVIDO", "trecho": "t"},
        {"nome": "Banco Bradesco S/A", "documento": "", "papel": "VITIMA"},
        {"nome": "SANTANDER", "papel": "DOCUMENTO"},
        {"nome": "[PESSOA_09]", "papel": "VITIMA"},
        {"nome": "BELTRANA EXEMPLO", "documento": "111.222.333-44", "papel": "vitima"},
        {"nome": "CICRANO EXEMPLO", "papel": "TESTEMUNHA"},
        {"nome": "FRAUDE", "papel": "DOCUMENTO"},
        {"nome": "FULANO DE TAL EXEMPLO", "documento": "00000000191", "papel": "ENVOLVIDO"},
    ])
    assert [(p["nome"], p["documento"], p["papel"]) for p in boas] == [
        ("FULANO DE TAL EXEMPLO", "00000000191", "ENVOLVIDO"), ("BELTRANA EXEMPLO", "", "VITIMA")]
    texto = " ".join(fora)
    assert "Bradesco" in texto and "SANTANDER" in texto and "[PESSOA_09]" in texto
    assert "TESTEMUNHA" in texto and "111" in texto and "«FRAUDE»: uma palavra só" in texto


def test_a_porta_da_ia_e_a_palavra_de_fraude():
    assert MF.parece_fraude("Suspeição de fraude.")
    assert MF.parece_fraude("", "procuração falsa lavrada em outra comarca")
    assert MF.parece_fraude("Comunica golpe com selo")
    assert not MF.parece_fraude("Circular sobre o recesso forense", "PORTARIA-COGEX_1942026.pdf")


def _ia_que_responde(pessoas, aviso=True, enviados=None):
    def conversar(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida):
        texto = conversa[0]["texto"]
        if enviados is not None:
            enviados.append(texto)
        cpf = re.search(r"\[CPF_\d+\]", texto)
        saida = [dict(p, documento=(cpf.group(0) if p.get("documento") == "CPF" and cpf else p.get("documento")))
                 for p in pessoas]
        return {"texto": json.dumps({"aviso_de_fraude": aviso, "resumo": "Procuração falsa.",
                                     "processos": ["0001/2026"], "pessoas": saida}),
                "modelo": "claude-sonnet-5", "entrada": 100, "saida": 50, "provedor": "claude"}
    return conversar


def test_o_que_sai_vai_mascarado_e_volta_com_o_numero(tmp_path):
    enviados = []
    ia = _ia_que_responde([{"nome": "FULANO DE TAL EXEMPLO", "documento": "CPF", "papel": "ENVOLVIDO",
                            "trecho": "em face de FULANO"}], enviados=enviados)
    r = MF.ler_aviso(tmp_path, "Inquérito em face de FULANO DE TAL EXEMPLO, CPF 000.000.001-91, por fraude.",
                     conversar=ia, provedor="claude")
    assert "000.000.001-91" not in enviados[0] and "00000000191" not in enviados[0]
    # o nome vai por extenso: a máscara inteira juntava duas pessoas numa marca só
    assert "FULANO DE TAL EXEMPLO" in enviados[0]
    assert r["aviso"] and r["pessoas"][0]["documento"] == "00000000191"
    assert r["processos"] == ["0001/2026"] and r["modelo"] == "claude-sonnet-5"


def test_sem_chave_a_ia_recusa_e_nao_inventa(tmp_path):
    with pytest.raises(MF.PropostaError):
        MF.ler_aviso(tmp_path, "fraude", conversar=lambda *a, **k: pytest.fail("não podia chamar"))

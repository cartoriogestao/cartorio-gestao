"""RC006 — a checklist do Registro Civil cobrava o que não é ato novo, e a CRC
recusava o que a régua deixava passar.

    «verifique e resolva os problemas da conferencia por areas do RCPN»
    — o oficial, 26/11/2026

O QUE ESTES TESTES GUARDAM
    **O acervo se separa pela ORIGEM, e não só pela data.** O lançamento direto
    do livro (origem `ACERVO`, 16/11/2026) grava a data da digitação: o
    casamento 134 de 1958 virou «ato novo» no SIRC, na CRC e no dado
    obrigatório. A cobrança do SIRC e da CRC, os arquivos do dia e a central de
    automação deixam o acervo de fora — as listas da carga (`sirc_remessa`,
    `crc_carga`) continuam com ele.

    **O assento ativo sem número de termo não se cobra no SIRC nem na CRC**: não
    houve termo, e mandar seria informação inexata (§ 4º do art. 225). Quem
    cobra a decisão sobre ele é o `RCPN_INACABADO`, CRÍTICO.

    **O óbito sem tipo da morte ou sem estado civil fica retido** — a CRC o
    recusa («TIPO_MORTE inexistente», «ESTADO_CIVIL inexistente», 24/11/2026);
    e o pai «IGNORADO» não sobe como nome («NOMEPAI está inválido»).
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automacao_processos as PROC                                 # noqa: E402
import automacao_schema as SCH                                     # noqa: E402
import compliance as CP                                            # noqa: E402
import crc_carga as CRC                                            # noqa: E402
import gestor_cargas_rcpn as GCR                                   # noqa: E402
import gestor_conferencia as GC                                    # noqa: E402
from gestor_schema import init_gestor_schema                       # noqa: E402

AGORA = "2026-11-26T08:00:00"
HOJE = date(2026, 11, 26)
M32 = "00000001552026100002269100086802"


@pytest.fixture()
def casa(cg_casa, tmp_path):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)",
                ("ri_cns", "000000"))
    init_gestor_schema(con)
    con.commit()
    yield {"con": con, "db": cg_casa["db"], "tmp": tmp_path}
    con.close()


def _assento(con, *, especie="NASCIMENTO", numero=19600, nome="FULANO DE TAL",
             data_ato="2026-11-25T10:00:00", origem="MANUAL", **extra) -> int:
    serie = {"NASCIMENTO": "RC_A", "CASAMENTO": "RC_B", "OBITO": "RC_C"}[especie]
    campos = {"serie": serie, "especie": especie, "numero": numero, "nome": nome,
              "data_ato": data_ato, "data_fato": "2026-11-20", "situacao": "ATIVO",
              "origem": origem, "origem_chave": f"t:{especie}:{numero}:{nome}:{origem}",
              "criado_em": AGORA, **extra}
    cur = con.execute(
        f"INSERT INTO rc_assentos({', '.join(campos)}) "
        f"VALUES({', '.join('?' * len(campos))})", tuple(campos.values()))
    con.commit()
    return int(cur.lastrowid)


def _pessoa(con, assento_id, papel, nome, **extra):
    campos = {"assento_id": assento_id, "papel": papel, "nome": nome,
              "nome_norm": nome.lower(), "criado_em": AGORA, **extra}
    con.execute(f"INSERT INTO rc_pessoas({', '.join(campos)}) "
                f"VALUES({', '.join('?' * len(campos))})", tuple(campos.values()))
    con.commit()


def _ids(achados):
    return {int(a["chave"].split(":")[2]) for a in achados}


# ------------------------------------------------- a origem ACERVO é acervo

def test_acervo_e_acervo_no_gestor_e_no_compliance():
    assert "ACERVO" in GC.ORIGENS_DO_ACERVO
    assert tuple(CP.ORIGENS_DO_ACERVO) == tuple(GC.ORIGENS_DO_ACERVO)


def test_o_acervo_com_a_data_da_digitacao_nao_vira_ato_novo(casa):
    con = casa["con"]
    novo = _assento(con, numero=19601, nome="ATO NOVO")
    livro = _assento(con, especie="CASAMENTO", numero=134, nome="DO LIVRO DE 1958",
                     origem="ACERVO")
    assert novo in _ids(GC.regra_sirc(con, HOJE))
    assert livro not in _ids(GC.regra_sirc(con, HOJE))
    assert novo in _ids(GC.regra_crc(con, HOJE))
    assert livro not in _ids(GC.regra_crc(con, HOJE))
    # a lista da CARGA continua com ele: o acervo sobe por lote
    assert livro in {p["id"] for p in CRC.pendentes_de_carga(con)}


def test_o_sem_numero_nao_se_cobra_no_sirc_nem_na_crc(casa):
    con = casa["con"]
    sem = _assento(con, numero=None, nome="PRIMEIRA TENTATIVA")
    assert sem in GC.assentos_fora_da_cobranca(con)
    assert sem not in _ids(GC.regra_sirc(con, HOJE))
    assert sem not in _ids(GC.regra_crc(con, HOJE))


def test_o_arquivo_do_dia_deixa_o_acervo_de_fora(casa):
    con = casa["con"]
    livro = _assento(con, especie="CASAMENTO", numero=134, nome="DO LIVRO DE 1958",
                     origem="ACERVO")
    s = GCR._settings(con)
    sirc = GCR.preparar_sirc(con, HOJE, s=s, ret={})
    crc = GCR.preparar_crc(con, HOJE, s=s, ret={})
    assert livro not in {f["assento_id"] for f in sirc["faltas"]}
    assert livro not in {f["assento_id"] for f in crc["faltas"]}
    assert crc["fora_pelo_corte"] >= 1


def _ctx(casa):
    return PROC.Contexto(db=casa["db"], agora=datetime(2026, 11, 26, 8, 0),
                         pasta_dados=casa["tmp"], raiz=RAIZ,
                         processo={"codigo": "T", "parametros": {}})


def test_a_automacao_nao_conta_o_acervo_como_vencido(casa):
    con = casa["con"]
    _assento(con, numero=4466, nome="DE 1982", data_ato="1982-11-11", origem="ACERVO")
    _assento(con, especie="CASAMENTO", numero=134, nome="DE 1958", origem="ACERVO")
    assert PROC.verificar_sirc(_ctx(casa))["situacao"] == SCH.OK
    assert PROC.verificar_crc(_ctx(casa))["situacao"] == SCH.OK
    _assento(con, numero=19601, nome="ATO NOVO", data_ato="2026-11-20T10:00:00")
    assert PROC.verificar_sirc(_ctx(casa))["situacao"] == SCH.ERRO
    assert PROC.verificar_crc(_ctx(casa))["situacao"] == SCH.AVISO


# ------------------------------------------------- o óbito que a CRC recusa

def _obito(con, **extra) -> int:
    campos = {"numero": 1996, "nome": "FALECIDO EXEMPLO", "matricula": M32,
              "obito_possui_bens": "N", "ibge_natureza_obito": "1", **extra}
    aid = _assento(con, especie="OBITO", **campos)
    return aid


def _faltas(con, aid):
    a = dict(con.execute("SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    pessoas = CRC._pessoas_do_assento(con, aid)
    return " | ".join(CRC.o_que_falta(con, a, pessoas, cns="000000"))


def _retido_por(con, aid):
    r = CRC.montar(con, [aid], cns="000000")["retidos"]
    return " | ".join(f for x in r for f in x["faltas"])


def test_obito_sem_tipo_da_morte_fica_retido_na_carga(casa):
    con = casa["con"]
    aid = _obito(con, ibge_natureza_obito=None)
    _pessoa(con, aid, "FALECIDO", "FALECIDO EXEMPLO", sexo="M", estado_civil="solteiro")
    assert "o tipo da morte" not in _faltas(con, aid)       # a lavratura passa
    assert "o tipo da morte" in _retido_por(con, aid)       # a carga retém


def test_obito_sem_estado_civil_fica_retido_na_carga_e_ignorado_passa(casa):
    con = casa["con"]
    branco = _obito(con)
    _pessoa(con, branco, "FALECIDO", "FALECIDO EXEMPLO", sexo="M", estado_civil="")
    # não recusa a lavratura (a régua da lavratura é `o_que_falta`)...
    assert "o estado civil do falecido" not in _faltas(con, branco)
    # ...mas a carga o retém
    assert "o estado civil do falecido — o campo está em branco" in _retido_por(con, branco)
    ignorado = _obito(con, numero=1997, nome="OUTRO FALECIDO")
    _pessoa(con, ignorado, "FALECIDO", "OUTRO FALECIDO", sexo="M", estado_civil="ignorado")
    texto = _retido_por(con, ignorado)
    assert "o estado civil do falecido — o campo está em branco" not in texto
    assert "o tipo da morte" not in texto


def test_pai_ignorado_nao_sobe_como_nome_no_obito(casa):
    con = casa["con"]
    aid = _obito(con)
    _pessoa(con, aid, "FALECIDO", "FALECIDO EXEMPLO", sexo="M", estado_civil="solteiro")
    _pessoa(con, aid, "PAI", "IGNORADO")
    _pessoa(con, aid, "MAE", "MAE EXEMPLO DA SILVA", sexo="F")
    xml = CRC.montar(con, [aid], cns="000000")["xml"]
    assert "IGNORADO" not in xml
    assert "<NOMEMAE>MAE EXEMPLO DA SILVA</NOMEMAE>" in xml

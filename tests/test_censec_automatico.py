"""O envio automático à CENSEC — pedido do oficial em 09/10/2026 («quero»)."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import censec_automatico as AUTO  # noqa: E402


def test_quinzenas_abertas_levam_a_anterior_so_ate_o_prazo():
    # dia 3/10: a 2ª de setembro ainda está no prazo (dia 5)
    assert AUTO.quinzenas_abertas(date(2026, 10, 3)) == [(2026, 9, 2), (2026, 10, 1)]
    # dia 6/10: o prazo dela venceu, não se tenta mais
    assert AUTO.quinzenas_abertas(date(2026, 10, 6)) == [(2026, 10, 1)]
    # dia 18/10: a 1ª de outubro vai até o dia 20
    assert AUTO.quinzenas_abertas(date(2026, 10, 18)) == [(2026, 10, 1), (2026, 10, 2)]
    # virada do ano
    assert AUTO.quinzenas_abertas(date(2027, 1, 2)) == [(2026, 12, 2), (2027, 1, 1)]


def _ato(con, **c):
    campos = {"tipo": "PROCURACAO", "data": "2026-10-08", "livro": "28", "folha": "46",
              "situacao": "LAVRADO", "criado_em": "2026-10-08T09:00:00", **c}
    cur = con.execute(f"INSERT INTO nt_atos({','.join(campos)}) VALUES "
                      f"({','.join('?' * len(campos))})", tuple(campos.values()))
    return cur.lastrowid


def _parte(con, aid, nome, qualificacao):
    con.execute("""INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, qualificacao,
                                              ordem, criado_em)
                   VALUES (?,?,?,?,1,'2026-10-08T09:00:00')""",
                (aid, nome, nome.lower(), qualificacao))


def test_a_regra_aponta_o_impedido_e_o_lembrete_de_fechar(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    ok = _ato(con)
    _parte(con, ok, "ANTONIO", "OUTORGANTE")
    ruim = _ato(con, folha="47")
    _parte(con, ruim, "IVANISE", None)
    con.execute("""INSERT INTO nt_remessas(central, competencia, ano_referencia,
                       mes_referencia, quinzena, situacao, quantidade, gerada_em,
                       enviada_em, criado_em)
                   VALUES ('CEP','2026-10',2026,10,1,'ENVIADA',1,'2026-10-09','2026-10-09',
                           '2026-10-09')""")
    con.commit()
    achados = AUTO.regra(con, date(2026, 10, 18))
    chaves = {a["chave"] for a in achados}
    assert f"CENSEC_IMPEDIDO:CEP:{ruim}" in chaves
    assert f"CENSEC_IMPEDIDO:CEP:{ok}" not in chaves
    assert "CENSEC_FECHAR:2026-10-Q1" in chaves
    impedido = next(a for a in achados if a["chave"].endswith(f":{ruim}"))
    assert "IVANISE" in impedido["detalhe"] and impedido["setor"] == "NOTAS"
    con.close()


def test_apto_que_perdeu_o_prazo_vira_achado_de_portal(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    aid = _ato(con, data="2026-09-17", tipo="ATA", folha="48")
    _parte(con, aid, "SOLICITANTE X", "SOLICITANTE")
    con.commit()
    achados = AUTO.regra(con, date(2026, 10, 9))
    assert any(a["chave"] == "CENSEC_APTO_FORA_DO_PRAZO:2026-09-Q2"
               and "portal" in a["detalhe"] for a in achados)
    con.close()


def test_a_falha_do_envio_vira_achado_critico_e_some_com_o_sucesso(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row

    def log(acao, det):
        con.execute("""INSERT INTO audit_logs(ts, username_snapshot, action, entity_type,
                                              details)
                       VALUES ('2026-10-10T02:00:00','envio-automatico',?, 'NT_REMESSA', ?)""",
                    (acao, json.dumps(det)))
        con.commit()

    log(AUTO.ACAO_FALHOU, {"motivo": "A CENSEC recusou a carga (HTTP 401)"})
    assert any(a["chave"] == "CENSEC_ENVIO_AUTOMATICO_FALHOU" and "401" in a["detalhe"]
               for a in AUTO.regra(con, date(2026, 10, 10)))
    log(AUTO.ACAO_ENVIOU, {"situacao": "ENVIADA"})
    assert not any(a["chave"] == "CENSEC_ENVIO_AUTOMATICO_FALHOU"
                   for a in AUTO.regra(con, date(2026, 10, 10)))
    con.close()


def test_enviar_manda_so_quinzena_com_apto_e_sempre_em_producao(cg_casa, monkeypatch):
    import censec_api as CAPI
    db = cg_casa["db"]
    con = sqlite3.connect(cg_casa["banco"])
    aid = _ato(con)
    _parte(con, aid, "ANTONIO", "OUTORGANTE")
    con.commit()
    con.close()
    chamadas = []

    def falso(db_, ano, mes, q, *, cns, ambiente, por):
        chamadas.append((ano, mes, q, ambiente, por))
        return {"por_central": {"CEP": {"sucesso": True, "situacao": "AguardandoValidacao"}}}

    monkeypatch.setattr(CAPI, "enviar_quinzena", falso)
    r = AUTO.enviar(db, date(2026, 10, 10), cns="000000")
    assert chamadas == [(2026, 10, 1, "PRODUCAO", AUTO.POR)]
    assert [x["situacao"] for x in r] == ["ENVIADA"]


def test_carga_enviada_pede_conferir_a_validacao_por_tres_dias(cg_casa):
    """13/10/2026: aceita na hora não quer dizer aprovada na validação."""
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    con.execute("""INSERT INTO nt_remessas(central, competencia, ano_referencia,
                       mes_referencia, quinzena, situacao, quantidade, protocolo_central,
                       gerada_em, enviada_em, criado_em)
                   VALUES ('CEP','2026-07',2026,7,2,'ENVIADA',4,'dd7aa758',
                           '2026-10-13T16:58:00','2026-10-13T16:58:00','2026-10-13')""")
    con.commit()
    perto = AUTO.regra(con, date(2026, 10, 14))
    assert any(a["chave"].startswith("CENSEC_CONFERIR_VALIDACAO:")
               and "dd7aa758" in a["detalhe"] for a in perto)
    longe = AUTO.regra(con, date(2026, 10, 20))
    assert not any(a["chave"].startswith("CENSEC_CONFERIR_VALIDACAO:") for a in longe)
    con.close()


def test_o_modulo_so_conhece_a_producao():
    """O automático é a comunicação de verdade; teste se faz pelo botão."""
    codigo = (RAIZ / "censec_automatico.py").read_text(encoding="utf-8").split('"""', 2)[2]
    assert "HOMOLOGACAO" not in codigo
    assert "CRED.PRODUCAO" in codigo

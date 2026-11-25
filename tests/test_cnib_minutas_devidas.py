"""Minuta só na averbação DEVIDA; o resto é aviso na ficha — ordem do oficial, 24/11/2026.

«só prepara a minuta de averbação nos casos devidos, e nos demais segue o padrão
do sistema e cria apenas um aviso para o escrevente verificar quando abrir a
matrícula se corresponde» (tarefa 486: 1.669 casos «sem decisão», quase todos
homônimos, cobrados todo dia útil desde 27/10).

Devida = o CPF/CNPJ da ordem é o de quem é dono hoje, em matrícula não encerrada.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import automacao_processos as AP
import automacao_schema as SCH
import ri_cnib as CNIB
from ri_schema import normalizar_busca
from test_cnib_pendentes import casa, _con, _ordem, _token  # noqa: F401  (fixture)

CPF = "00012345678"


def _matricula(con, *, numero, partes, situacao="ATIVA"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, criado_em)
           VALUES (?, '2', '2', ?, '2026-08-28T09:00')""", (numero, situacao))
    mid = int(cur.lastrowid)
    for nome, documento, papel, ativo in partes:
        con.execute(
            """INSERT INTO ri_partes (matricula_id, nome, nome_norm, documento_numero,
                   papel, proprietario_ativo) VALUES (?,?,?,?,?,?)""",
            (mid, nome, normalizar_busca(nome), documento, papel, ativo))
    return mid


def _cenario(casa):
    """Uma devida e três avisos, um de cada tipo."""
    con = _con(casa)
    with con:
        _ordem(con, nome="FULANO DOCUMENTO", documento=CPF, protocolo="DEVIDA-1")
        _matricula(con, numero="10", partes=[("FULANO DOCUMENTO", CPF, "proprietario", 1)])
        _ordem(con, nome="JOAO HOMONIMO DA SILVA", documento="00099999999", protocolo="NOME-1")
        _matricula(con, numero="20", partes=[("JOAO HOMONIMO DA SILVA", None, "proprietario", 1)])
        _ordem(con, nome="BELTRANO VENDEU", documento="00011111111", protocolo="ANTIGO-1")
        _matricula(con, numero="30", partes=[("BELTRANO VENDEU", "00011111111", "transmitente", 0),
                                             ("COMPRADOR NOVO", "00022222222", "adquirente", 1)])
        _ordem(con, nome="CICRANO ENCERRADA", documento="00033333333", protocolo="ENC-1")
        _matricula(con, numero="40", situacao="ENCERRADA",
                   partes=[("CICRANO ENCERRADA", "00033333333", "proprietario", 1)])


def _por_protocolo(casa):
    return {p["ordem"]["protocolo_cnib"]: p for p in CNIB.pendentes(_con(casa), com_teor=False)}


def _minutas(casa):
    return [dict(r) for r in _con(casa).execute(
        "SELECT id, situacao, origem_chave, tipo, teor FROM ri_minutas ORDER BY id").fetchall()]


def test_so_o_documento_do_dono_de_hoje_em_matricula_ativa_e_devida(casa):
    _cenario(casa)
    p = _por_protocolo(casa)
    assert p["DEVIDA-1"]["devida"] is True
    assert {k for k, v in p.items() if not v["devida"]} == {"NOME-1", "ANTIGO-1", "ENC-1"}
    assert "nome" in p["NOME-1"]["ordem"]["motivo_do_aviso"]
    assert "não é dona hoje" in p["ANTIGO-1"]["ordem"]["motivo_do_aviso"]
    assert "encerrada" in p["ENC-1"]["ordem"]["motivo_do_aviso"]
    # a devida vem primeiro na lista
    assert CNIB.pendentes(_con(casa), com_teor=False)[0]["ordem"]["protocolo_cnib"] == "DEVIDA-1"


def test_preparar_cria_minuta_so_da_devida_e_nao_repete(casa):
    _cenario(casa)
    con = _con(casa)
    with con:
        r = CNIB.preparar_minutas_devidas(con, agora="2026-11-24T10:00", usuario="mario")
    assert len(r["preparadas"]) == 1
    m = _minutas(casa)
    assert len(m) == 1 and m[0]["situacao"] == "A_REVISAR" and m[0]["tipo"] == "AV"
    assert "DEVIDA-1" in m[0]["origem_chave"] and "DEVIDA-1" in m[0]["teor"]
    assert "{{" not in m[0]["teor"]
    con = _con(casa)
    with con:
        assert CNIB.preparar_minutas_devidas(con, agora="2026-11-24T11:00", usuario="mario")["preparadas"] == []
    assert len(_minutas(casa)) == 1
    # a devida continua na lista, agora com a minuta à espera da lavratura
    assert _por_protocolo(casa)["DEVIDA-1"]["ordem"]["minuta"]["situacao"] == "A_REVISAR"


def test_minuta_descartada_nao_volta_sozinha_mas_volta_pelo_botao(casa):
    _cenario(casa)
    con = _con(casa)
    with con:
        CNIB.preparar_minutas_devidas(con, agora="2026-11-24T10:00", usuario="mario")
        con.execute("UPDATE ri_minutas SET situacao='DESCARTADA'")
    con = _con(casa)
    with con:
        r = CNIB.preparar_minutas_devidas(con, agora="2026-11-24T11:00", usuario="mario")
    assert r["preparadas"] == [] and r["descartadas"] == 1
    c = casa["cliente"]
    html = c.get("/registro-imoveis/cnib/pendentes").get_data(as_text=True)
    assert "Preparar a minuta de novo" in html
    c.post("/registro-imoveis/cnib/pendentes/preparar", data={
        "csrf_token": _token(html), "matricula_id": _por_protocolo(casa)["DEVIDA-1"]["matricula_id"],
        "protocolo_cnib": "DEVIDA-1", "pessoa_nome": "FULANO DOCUMENTO", "pessoa_documento": CPF})
    assert [m["situacao"] for m in _minutas(casa)] == ["DESCARTADA", "A_REVISAR"]


def test_o_botao_da_tela_prepara_as_que_faltam(casa):
    _cenario(casa)
    c = casa["cliente"]
    html = c.get("/registro-imoveis/cnib/pendentes").get_data(as_text=True)
    assert "1 averbação(ões) devida(s)" in html and "3 aviso(s)" in html
    assert "Preparar as 1 minuta(s) que faltam" in html
    r = c.post("/registro-imoveis/cnib/pendentes/preparar", data={"csrf_token": _token(html)},
               follow_redirects=True)
    assert "1 minuta(s) de averbação preparada(s)" in r.get_data(as_text=True)
    assert len(_minutas(casa)) == 1
    assert _con(casa).execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='RI_CNIB_MINUTAS_PREPARADAS'").fetchone()[0] == 1


def test_escrevente_nao_prepara_em_lote(casa):
    _cenario(casa)
    db, c = casa["db"], casa["cliente"]
    db.create_user("ana", "ANA ESCREVENTE", "Senha#12345", "USER")
    c.get("/logout")
    c.post("/login", data={"username": "ana", "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))})
    html = c.get("/registro-imoveis/cnib/pendentes").get_data(as_text=True)
    assert "Preparar as" not in html
    r = c.post("/registro-imoveis/cnib/pendentes/preparar", data={"csrf_token": _token(html)})
    assert r.status_code in (302, 403)
    assert _minutas(casa) == []


def test_a_ficha_diz_devida_ou_aviso_para_conferir(casa):
    _cenario(casa)
    p = _por_protocolo(casa)
    c = casa["cliente"]
    devida = c.get(f"/registro-imoveis/{p['DEVIDA-1']['matricula_id']}").get_data(as_text=True)
    assert "Averbação devida" in devida
    aviso = c.get(f"/registro-imoveis/{p['NOME-1']['matricula_id']}").get_data(as_text=True)
    assert "Aviso — verifique se corresponde" in aviso
    assert "POSSÍVEL INDISPONIBILIDADE PENDENTE" in aviso  # o quadro de sempre continua


def _ctx(casa, pode_agir, estado=None):
    return AP.Contexto(db=casa["db"], agora=datetime(2026, 11, 26, 7, 45),
                       pasta_dados=Path(casa["banco"]).parent, raiz=RAIZ,
                       processo={"codigo": "RI_CNIB", "pode_agir": pode_agir, "estado": estado or {}})


# Ordem do oficial, 25/11/2026: «é só se continuar esses 1669 docs. se tiver
# qualquer outro doc novo, é para abrir tarefa de rotina».

def test_a_primeira_rodada_grava_a_base_e_nao_cobra_os_conhecidos(casa):
    _cenario(casa)
    r = AP.verificar_cnib(_ctx(casa, 0))
    assert r["situacao"] == SCH.OK
    assert len(r["estado"]["conhecidos"]) == 4 and r["estado"]["base_tamanho"] == 4
    assert "base gravada com os 4 caso(s)" in r["relato"]
    assert "1 averbação(ões) devida(s) (0 com minuta pronta, 1 sem minuta) e 3 aviso(s)" in r["relato"]
    assert _minutas(casa) == []  # desligada, só conta
    # a rodada seguinte, com a base, também não cobra
    r2 = AP.verificar_cnib(_ctx(casa, 0, r["estado"]))
    assert r2["situacao"] == SCH.OK and "nenhum caso novo" in r2["relato"]
    assert "estado" not in r2  # a base não é regravada


def _caso_novo(casa, *, documento="00077777777", nome="NOVA DEVEDORA", protocolo="NOVA-1", dona=True):
    con = _con(casa)
    with con:
        _ordem(con, nome=nome, documento=documento, protocolo=protocolo)
        _matricula(con, numero="50", partes=[(nome, documento if dona else None, "proprietario", 1)])


def test_caso_novo_abre_tarefa_e_continua_novo_ate_ser_decidido(casa):
    _cenario(casa)
    base = AP.verificar_cnib(_ctx(casa, 0))["estado"]
    _caso_novo(casa)
    r = AP.verificar_cnib(_ctx(casa, 0, base))
    assert r["situacao"] == SCH.AVISO
    assert "1 caso(s) novo(s)" in r["relato"] and "1 averbação(ões) devida(s)" in r["relato"]
    assert [a["protocolo"] for a in r["achados"]] == ["NOVA-1"]
    assert "Dos 4 já conhecidos" in r["relato"]
    # não entra na base sozinho: no dia seguinte ainda é novo
    assert AP.verificar_cnib(_ctx(casa, 0, base))["situacao"] == SCH.AVISO
    # decidido, sai da lista, e a rodada volta ao normal
    con = _con(casa)
    with con:
        mid = con.execute("SELECT id FROM ri_matriculas WHERE numero='50'").fetchone()[0]
        con.execute("""INSERT INTO ri_cnib_decisoes (matricula_id, protocolo_cnib, pessoa_nome,
                           pessoa_documento, decisao, motivo, decidido_por, decidido_em)
                       VALUES (?, 'NOVA-1', 'NOVA DEVEDORA', '00077777777', 'NAO_E_A_PESSOA',
                               'teste', 'mario', '2026-11-26T08:00')""", (mid,))
    assert AP.verificar_cnib(_ctx(casa, 0, base))["situacao"] == SCH.OK


def test_caso_novo_so_por_nome_tambem_abre_tarefa(casa):
    _cenario(casa)
    base = AP.verificar_cnib(_ctx(casa, 0))["estado"]
    _caso_novo(casa, dona=False)
    r = AP.verificar_cnib(_ctx(casa, 0, base))
    assert r["situacao"] == SCH.AVISO
    assert "1 caso(s) novo(s)" in r["relato"] and "0 averbação(ões) devida(s) e 1 aviso(s)" in r["relato"]


def test_a_rotina_com_pode_agir_prepara_a_minuta(casa):
    _cenario(casa)
    r = AP.verificar_cnib(_ctx(casa, 1))
    assert len(_minutas(casa)) == 1
    assert r["acoes"] and r["acoes"][0]["minutas"]
    assert "1 com minuta pronta" in r["relato"]


def test_sem_nada_pendente_e_ok(casa):
    r = AP.verificar_cnib(_ctx(casa, 0))
    assert r["situacao"] == SCH.OK and r["estado"]["conhecidos"] == []
    _caso_novo(casa)
    assert AP.verificar_cnib(_ctx(casa, 0, r["estado"]))["situacao"] == SCH.AVISO

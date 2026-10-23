"""O agente de cargas do RCPN — SIRC, CRC, FUNAI, óbitos do mês e IBGE.

O QUE ESTES TESTES GUARDAM
    **Que o assento duplicado e o sem número não vão em arquivo nenhum.**
    Medido em 09/10/2026: o óbito de JOELMIR lavrado duas vezes e o assento
    8362, sem número, na fila do SIRC como «nº None». O § 4º do art. 225 pune
    informação inexata — e a régua é a do agente do RCPN quando ele existir.

    **Que a pasta da carga fica com os arquivos de hoje, e só os do agente
    saem dela**: arquivo posto à mão não se apaga.

    **Que o que a tela das comunicações registrou deixa de ser cobrado** — até
    09/10/2026 a regra do gestor só olhava `ge_envios`.

    **Que o arquivo pronto vira UMA tarefa do Registro Civil, com o prazo mais
    apertado**, e o agente parado vira achado de TI — nunca silêncio.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import types
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_cargas_rcpn as G                                      # noqa: E402
import gestor_conferencia as GC                                     # noqa: E402
import gestor_rotina as GR                                          # noqa: E402
from gestor_schema import init_gestor_schema                        # noqa: E402

AGORA = "2026-10-09T08:00:00"
HOJE = date(2026, 10, 9)


@pytest.fixture()
def casa(cg_casa, tmp_path):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    for chave, valor in (("ri_cns", "000000"), (G.CHAVE_PASTA, str(tmp_path / "CARGAS"))):
        con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)", (chave, valor))
    init_gestor_schema(con)
    con.commit()
    yield {"con": con, "tmp": tmp_path, "pasta": tmp_path / "CARGAS"}
    con.close()


def _assento(con, *, especie="NASCIMENTO", numero=19600, nome="FULANO DE TAL",
             data_ato="2026-10-08T10:00:00", data_fato="2026-10-01",
             situacao="ATIVO", origem="MANUAL") -> int:
    serie = {"NASCIMENTO": "RC_A", "CASAMENTO": "RC_B", "OBITO": "RC_C"}[especie]
    cur = con.execute(
        "INSERT INTO rc_assentos(serie, especie, numero, nome, data_ato, data_fato, "
        "situacao, origem, origem_chave, criado_em) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (serie, especie, numero, nome, data_ato, data_fato, situacao, origem,
         f"t:{especie}:{numero}:{nome}:{data_ato}", AGORA))
    con.commit()
    return int(cur.lastrowid)


@pytest.fixture()
def sem_agente_do_rcpn(monkeypatch):
    """Força a régua provisória, mesmo se o módulo do agente do RCPN existir."""
    monkeypatch.setitem(sys.modules, "gestor_rcpn", None)


# ------------------------------------------------------------ o que não vai

def test_a_regua_provisoria_retem_o_duplicado_e_o_sem_numero(casa, sem_agente_do_rcpn):
    con = casa["con"]
    a = _assento(con, especie="OBITO", numero=1983, nome="MOACIR SILVA PEREIRA")
    b = _assento(con, especie="OBITO", numero=1984, nome="Moacir Silva Pereira")
    sem = _assento(con, numero=None, nome="PAULO RICARDO")
    bom = _assento(con, numero=19578, nome="OUTRA PESSOA")
    ret = G.retidos(con)
    assert a in ret and b in ret and "1983, 1984" in ret[a]
    assert "sem número" in ret[sem]
    assert bom not in ret


def test_o_cancelado_e_o_acervo_nao_contam_como_duplicado(casa, sem_agente_do_rcpn):
    con = casa["con"]
    _assento(con, especie="OBITO", numero=1983, nome="JOELMIR", situacao="CANCELADO")
    vivo = _assento(con, especie="OBITO", numero=1984, nome="JOELMIR")
    _assento(con, especie="OBITO", numero=10, nome="JOELMIR", origem="EOFICIO")
    assert vivo not in G.retidos(con)


def test_a_regua_e_a_do_agente_do_rcpn_quando_ele_existe(casa, monkeypatch):
    falso = types.ModuleType("gestor_rcpn")
    falso.duplicidades = lambda con: [{"especie": "OBITO", "ids": [7, 8],
                                       "numeros": [1983, 1984]}]
    falso.inacabados = lambda con: [{"id": 9, "especie": "NASCIMENTO"}]
    monkeypatch.setitem(sys.modules, "gestor_rcpn", falso)
    ret = G.retidos(casa["con"])
    assert set(ret) == {7, 8, 9}
    assert "1983, 1984" in ret[7] and "sem número" in ret[9]


# ------------------------------------------------------------------ a pasta

def test_a_pasta_fica_com_os_arquivos_de_hoje_e_o_alheio_fica(tmp_path):
    raiz = tmp_path / "CARGAS"
    (raiz / "SIRC").mkdir(parents=True)
    (raiz / "SIRC" / "SIRC_VELHO_01.mrc").write_bytes(b"ontem")
    (raiz / "SIRC" / "anotacao_da_debora.txt").write_text("minha nota")
    saida = G.escrever_na_pasta(raiz, "SIRC", [{"nome": "SIRC_NASCIMENTO_01.xml",
                                               "dados": b"<x/>", "quantos": 1}])
    nomes = sorted(p.name for p in (raiz / "SIRC").iterdir())
    assert nomes == ["SIRC_NASCIMENTO_01.xml", "anotacao_da_debora.txt"]
    assert saida[0]["sha256"] and "dados" not in saida[0]


# ------------------------------------------------------------- a rodada

def _prepara_fixo(arquivos=1, prazo="2026-09-22", **extra):
    def preparar(con, hoje, *, s, ret, **kw):
        r = G._vazio()
        r["arquivos"] = [{"nome": f"SIRC_NASCIMENTO_{i:02d}.xml", "dados": b"<x/>",
                          "quantos": 2} for i in range(1, arquivos + 1)]
        r["quantos"] = 2 * arquivos
        r["prazo"] = date.fromisoformat(prazo) if prazo else None
        r.update(extra)
        return r
    return preparar


def test_a_rodada_grava_o_livro_e_escreve_a_pauta(casa, monkeypatch, sem_agente_do_rcpn):
    vazio = lambda con, hoje, *, s, ret, **kw: G._vazio()           # noqa: E731
    monkeypatch.setattr(G, "PREPARA", {c: vazio for c in G.CANAIS}
                        | {"SIRC": _prepara_fixo()})
    resumo = G.rodada(casa["con"], hoje=HOJE, escrever=lambda *_: None)
    assert len(resumo["SIRC"]["arquivos"]) == 1
    assert (casa["pasta"] / "SIRC" / "SIRC_NASCIMENTO_01.xml").exists()
    leia = (casa["pasta"] / "LEIA-ME - O QUE SUBIR HOJE.txt").read_text(encoding="utf-8-sig")
    assert "SIRC: 1 arquivo(s)" in leia and "CRC: nada a subir." in leia
    linhas = casa["con"].execute(
        "SELECT canal, situacao FROM ge_rcpn_cargas ORDER BY id").fetchall()
    assert [tuple(x) for x in linhas] == [(c, "OK") for c in G.CANAIS]


def test_uma_carga_que_quebra_nao_segura_as_outras(casa, monkeypatch, sem_agente_do_rcpn):
    def quebra(*a, **k):
        raise RuntimeError("montador caiu")
    vazio = lambda con, hoje, *, s, ret, **kw: G._vazio()           # noqa: E731
    monkeypatch.setattr(G, "PREPARA", {c: vazio for c in G.CANAIS} | {"CRC": quebra})
    resumo = G.rodada(casa["con"], hoje=HOJE, escrever=lambda *_: None)
    assert "montador caiu" in resumo["CRC"]["erro"]
    assert "erro" not in resumo["IBGE"]
    achados = G.conferir(casa["con"], HOJE)
    parado = [a for a in achados if a["regra"] == "CARGAS_RCPN_AGENTE_PARADO"]
    assert [a["chave"] for a in parado] == ["CARGAS_RCPN_AGENTE:CRC"]
    assert parado[0]["setor"] == "TI" and parado[0]["gravidade"] == "CRITICO"


# ----------------------------------------------------------- a conferência

def test_arquivo_pronto_vira_achado_do_rcpn_com_o_prazo(casa, monkeypatch, sem_agente_do_rcpn):
    vazio = lambda con, hoje, *, s, ret, **kw: G._vazio()           # noqa: E731
    monkeypatch.setattr(G, "PREPARA", {c: vazio for c in G.CANAIS} | {
        "SIRC": _prepara_fixo(fora=[{"nome": "PAULO RICARDO", "motivo": "sem número"}],
                              faltas=[{"assento_id": 5, "nome": "JOELMIR",
                                       "faltas": ["se possuía bens"]}])})
    G.rodada(casa["con"], hoje=HOJE, escrever=lambda *_: None)
    achados = {a["chave"]: a for a in G.conferir(casa["con"], HOJE)}
    pronta = achados["CARGAS_RCPN_PRONTA:SIRC"]
    assert pronta["setor"] == "RCPN" and pronta["gravidade"] == "VENCIDO"
    assert pronta["prazo"] == "2026-09-22"
    assert "SIRC_NASCIMENTO_01.xml" in pronta["detalhe"]
    assert "Ficou fora: PAULO RICARDO" in pronta["detalhe"]
    falta = achados["CARGAS_RCPN_FALTA:SIRC:rc_assentos:5"]
    assert "possuía bens" in falta["detalhe"]


def test_sem_rodada_o_agente_e_achado_e_nao_silencio(casa):
    achados = G.conferir(casa["con"], HOJE)
    assert {a["regra"] for a in achados} == {"CARGAS_RCPN_AGENTE_PARADO"}
    assert len(achados) == len(G.CANAIS)


def test_o_ibge_que_atravessa_o_eoficio_e_decisao_sem_tarefa(casa, monkeypatch,
                                                              sem_agente_do_rcpn):
    vazio = lambda con, hoje, *, s, ret, **kw: G._vazio()           # noqa: E731
    monkeypatch.setattr(G, "PREPARA", {c: vazio for c in G.CANAIS} | {
        "IBGE": _prepara_fixo(prazo="2026-10-08",
                              transicao=[{"competencia": "2026-T3", "do_acervo": 42,
                                          "linhas": 53}])})
    G.rodada(casa["con"], hoje=HOJE, escrever=lambda *_: None)
    decisao = [a for a in G.conferir(casa["con"], HOJE) if a["regra"] == "CARGAS_RCPN_DECISAO"]
    assert decisao and decisao[0]["setor"] == "GESTAO" and "42" in decisao[0]["detalhe"]
    assert "CARGAS_RCPN_DECISAO" in GR.REGRAS_SEM_TAREFA
    # 13/10/2026: era «not in». As cargas saíram das tarefas por ordem do oficial
    # («não crie mais tarefas para os escreventes»): vão ao despacho dele.
    assert "CARGAS_RCPN_PRONTA" in GR.REGRAS_SEM_TAREFA


# --------------------------------------------------------- óbitos do mês

def test_o_mes_fechado_abre_as_cinco_e_prepara_os_cinco_arquivos(casa, sem_agente_do_rcpn):
    con = casa["con"]
    r = G.preparar_obitos(con, HOJE, s=G._settings(con), ret={})
    nomes = sorted(a["nome"] for a in r["arquivos"])
    assert nomes == sorted(f"OBITOS_2026-09_{d}.txt" for d in G.CENTRAL_DO_DESTINO)
    assert con.execute("SELECT COUNT(*) FROM rc_comunicacoes WHERE competencia='2026-09' "
                       "AND situacao='PENDENTE'").fetchone()[0] == 5
    # repetível: rodar de novo não abre outras cinco
    G.preparar_obitos(con, HOJE, s=G._settings(con), ret={})
    assert con.execute("SELECT COUNT(*) FROM rc_comunicacoes "
                       "WHERE competencia='2026-09'").fetchone()[0] == 5


def test_o_mes_com_obito_retido_nao_se_prepara(casa):
    con = casa["con"]
    aid = _assento(con, especie="OBITO", numero=1984, data_ato="2026-09-25T10:00:00")
    r = G.preparar_obitos(con, HOJE, s=G._settings(con), ret={aid: "lançado duas vezes"})
    assert r["arquivos"] == [] and "lançado duas vezes" in r["problemas"][0]


def test_o_registrado_na_tela_das_comunicacoes_deixa_de_ser_cobrado(casa):
    con = casa["con"]
    antes = {a["chave"] for a in GC.regra_obitos_do_mes(con, HOJE)}
    assert "OBITO_TRE:2026-09" in antes
    con.execute("INSERT INTO rc_comunicacoes(destino, competencia, situacao, criado_em) "
                "VALUES('ELEITORAL','2026-09','ENVIADA',?)", (AGORA,))
    con.execute("INSERT INTO rc_comunicacoes(destino, competencia, situacao, criado_em) "
                "VALUES('JUNTA_MILITAR','2026-09','DISPENSADA',?)", (AGORA,))
    con.commit()
    depois = {a["chave"] for a in GC.regra_obitos_do_mes(con, HOJE)}
    assert "OBITO_TRE:2026-09" not in depois and "JUNTA_MILITAR:2026-09" not in depois
    assert "OBITO_RFB:2026-09" in depois


# ------------------------------------------------------------------ o IBGE

def test_os_trimestres_comecam_no_do_corte_e_so_os_fechados():
    assert G._trimestres(date(2026, 10, 9)) == [(2026, 3)]
    assert G._trimestres(date(2026, 9, 30)) == []
    assert G._trimestres(date(2027, 1, 2)) == [(2026, 3), (2026, 4)]


# ------------------------------------------------------- a linha de comando

@pytest.fixture()
def fora_do_sistema(monkeypatch):
    """O Agendador roda `--banco` fora do sistema: ninguém instala o desvio do
    `sqlite3.connect`, e o `sqlite3` cru é recusado pelo acesso nativo."""
    banco_pg = pytest.importorskip("banco_pg")
    if not banco_pg.ativo():
        pytest.skip("o módulo é nativo: só roda no PostgreSQL")
    monkeypatch.setattr(sqlite3, "connect", banco_pg._CONNECT_ORIGINAL)


#: o cabeçalho fictício de `test_ibge_geracao` — sem ele o IBGE recusa a remessa.
IBGE_FICTICIO = {"ibge_uf": "21", "ibge_municipio": "98765",
                 "ibge_distrito": "05", "ibge_cartorio": "01"}


def test_a_linha_de_comando_mede_pela_porta_do_banco(cg_casa, casa, fora_do_sistema,
                                                     capsys, sem_agente_do_rcpn):
    """Revisão do L004: o `main()` abria `sqlite3.connect` cru. E a medição
    roda as cinco cargas num `con` sem `row_factory`, como o do Agendador."""
    cg_casa["db"].set_settings(IBGE_FICTICIO)
    assert G.main(["--banco", str(cg_casa["banco"]), "--so-medir",
                   "--hoje", HOJE.isoformat()]) == 0
    medido = json.loads(capsys.readouterr().out)
    assert {c: medido[c].get("erro") for c in G.CANAIS} == {c: None for c in G.CANAIS}


def test_a_linha_de_comando_roda_pela_porta_do_banco(cg_casa, casa, fora_do_sistema,
                                                     sem_agente_do_rcpn):
    cg_casa["db"].set_settings(IBGE_FICTICIO)
    assert G.main(["--banco", str(cg_casa["banco"]), "--hoje", HOJE.isoformat()]) == 0
    linhas = casa["con"].execute(
        "SELECT canal, situacao FROM ge_rcpn_cargas ORDER BY id").fetchall()
    assert [tuple(x) for x in linhas] == [(c, "OK") for c in G.CANAIS]


# ------------------------------------------------------- ligado no gestor

def test_o_agente_esta_ligado_no_gestor():
    assert ("CARGAS_RCPN", GC.regra_rcpn_cargas) in GC.REGRAS
    for regra in G.ROTULOS:
        assert regra in GR.ROTULOS and regra in GR._REGRAS_DE_CENTRAL
    fonte = Path(GR.__file__).read_text(encoding="utf-8")
    assert "GCRC.rodada(con, banco, hoje" in fonte


def test_o_agente_nao_manda_nada_a_central_nenhuma():
    """Preparar e fiscalizar, sim; enviar, não — decisão do oficial em aberto."""
    fonte = Path(G.__file__).read_text(encoding="utf-8")
    for proibido in ("sirc_cliente", "crc_soap", "SC.enviar", "registrar_envio(",
                     "registrar_entrega("):
        assert proibido not in fonte.split('"""', 2)[2], proibido

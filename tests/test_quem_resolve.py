"""Quem está resolvendo — a marca que impede duas pessoas de fazer o mesmo trabalho.

Pedido do titular (26/11/2026): «marcar quem está resolvendo cada problema na
Checklist do dia e nos Projetos, para duas pessoas não fazerem o mesmo trabalho».
Os testes provam:

  * assumir, recusar o segundo (com o nome e desde quando), assumir no lugar
    (TOMADO), largar (só quem está), encerrar (CONCLUIU) — e o índice único
    parcial segura a disputa, até quando a conferência do código é furada;
  * o «Feito» da rotina e a fase CONCLUIDA ou DISPENSADA (também pela carga)
    fecham a marca, e a auditoria leva QUEM_RESOLVE_CONCLUIU;
  * a Checklist do dia (rotina e achados), «Minha rotina» e os Projetos
    mostram a marca, os botões certos para cada papel e quantos estão em
    resolução; o auditor e o robô nunca assumem; o POST sem token é recusado.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import dev_projetos as DP                     # noqa: E402
import quem_resolve as QR                     # noqa: E402
import rotina_da_casa as RT                   # noqa: E402
from bd_nativo import ERROS_DO_BANCO, banco   # noqa: E402
from conftest import cg_login                 # noqa: E402

SENHA = "Senha#12345"
CHECKLIST = "/administrativo/gestor/checklist"
ASSUMIR = "/administrativo/quem-resolve/assumir"
LARGAR = "/administrativo/quem-resolve/largar"


def _pessoa(db, login, papel="USER") -> int:
    return db.create_user(login, f"{login.upper()} EXEMPLO LIMA", SENHA, papel)


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _auditoria(db, acao) -> list[dict]:
    with db.connect() as con:
        return [json.loads(r["details"]) for r in banco(con).ler(
            "SELECT details FROM audit_logs WHERE action = %s ORDER BY id", (acao,))]


def _linhas(db, tipo=None) -> list[dict]:
    with db.connect() as con:
        return banco(con).ler(
            "SELECT tipo, chave, usuario_id, por, ate, fim_por, motivo_fim FROM ge_quem_resolve "
            + ("WHERE tipo = %s " if tipo else "") + "ORDER BY id", (tipo,) if tipo else ())


def _rotina_de_hoje(db, codigo="TI_BACKUP", area="TI", **mais) -> tuple[int, str]:
    """Um item diário que vale do último dia útil: a referência de hoje, sem faltas."""
    _, ultimo = RT.ocorrencia_atual({"periodicidade": "DIARIA"}, date.today())
    with db.transaction() as con:
        rid = RT.criar(con, {"codigo": codigo, "area": area, "titulo": f"Conferir {codigo}",
                             "como_fazer": "Abra a tela.\nConfira.", "periodicidade": "DIARIA",
                             **mais}, por="Fulano", agora=datetime.combine(ultimo, time(7, 0)))
    with db.connect() as con:
        [x] = [y for y in RT.do_dia(con, date.today()) if y["id"] == rid]
    return rid, x["referencia"]


def _achado(db, chave="T:1", titulo="Remessa da quinzena") -> int:
    hoje = date.today().isoformat()
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("INSERT INTO ge_execucoes(iniciada_em, terminada_em, hoje) VALUES (%s,%s,%s)",
                    (hoje + "T07:30:00", hoje + "T07:35:00", hoje))
        return int(bd.escrever(
            "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, primeiro_visto_em, "
            "ultimo_visto_em) VALUES (%s,'CENSEC','VENCIDO','NOTAS',%s,%s,%s) RETURNING id",
            (chave, titulo, hoje + "T07:30:00", hoje + "T07:30:00"))[0]["id"])


def _fase(db) -> tuple[int, int]:
    with db.transaction() as con:
        pid = DP.criar_projeto(con, {"titulo": "PRJ-QR — Projeto de ensaio"}, por="ensaio")
        fid = DP.adicionar_fase(con, pid, {"titulo": "Homologar com a Central"}, por="ensaio")
    return pid, fid


# ------------------------------------------------------------ o domínio


def test_assumir_recusar_tomar_largar_e_encerrar(cg_casa):
    db = cg_casa["db"]
    ana, bia, gil = _pessoa(db, "ana"), _pessoa(db, "bia"), _pessoa(db, "gil", "MANAGER")
    manha = datetime(2026, 11, 26, 14, 40)
    with db.transaction() as con:
        r = QR.assumir(con, QR.ACHADO, "T:1", usuario_id=ana, por="Ana", nota="liguei para a Central",
                       agora=manha)
        assert r["gravou"] and r["tomado_de"] is None
        assert not QR.assumir(con, QR.ACHADO, "T:1", usuario_id=ana, por="Ana")["gravou"]
        with pytest.raises(QR.QuemResolveError, match="Ana já está resolvendo isto desde 26/11 às 14:40"):
            QR.assumir(con, QR.ACHADO, "T:1", usuario_id=bia, por="Bia")
        with pytest.raises(QR.QuemResolveError, match="Quem larga é quem está resolvendo"):
            QR.largar(con, QR.ACHADO, "T:1", usuario_id=bia, por="Bia")
        tomado = QR.assumir(con, QR.ACHADO, "T:1", usuario_id=gil, por="Gil", tomar=True,
                            agora=datetime(2026, 11, 26, 15, 0))
        assert tomado["gravou"] and tomado["tomado_de"]["por"] == "Ana"
        quem = QR.ativos(con, QR.ACHADO, ["T:1", "T:2"], agora=datetime(2026, 11, 28, 9, 0))
        assert list(quem) == ["T:1"]
        assert (quem["T:1"]["por"], quem["T:1"]["ha_dias"], quem["T:1"]["rotulo"]) == (
            "Gil", 2, "desde 26/11, há 2 dia(s)")
        assert QR.ativos(con, QR.ACHADO, ["T:1"], agora=datetime(2026, 11, 26, 16, 0))[
            "T:1"]["rotulo"] == "desde 15:00"
        assert QR.largar(con, QR.ACHADO, "T:1", usuario_id=gil, por="Gil")["por"] == "Gil"
        assert QR.largar(con, QR.ACHADO, "T:1", usuario_id=gil, por="Gil") is None
        QR.assumir(con, QR.FASE, "7", usuario_id=bia, por="Bia")
        assert QR.encerrar(con, QR.FASE, "7", por="Fulano")["por"] == "Bia"
        assert QR.encerrar(con, QR.FASE, "7", por="Fulano") is None
        assert QR.ativos(con, QR.FASE, ["7"]) == {}
        with pytest.raises(QR.QuemResolveError, match="curta"):
            QR.assumir(con, QR.FASE, "8", usuario_id=bia, por="Bia", nota="x" * 201)
        with pytest.raises(QR.QuemResolveError, match="desconhecido"):
            QR.assumir(con, "OUTRO", "8", usuario_id=bia, por="Bia")
    assert [(x["por"], x["motivo_fim"], x["fim_por"]) for x in _linhas(db)] == [
        ("Ana", "TOMADO", "Gil"), ("Gil", "LARGOU", "Gil"), ("Bia", "CONCLUIU", "Fulano")]


def test_o_achado_resolvido_pelo_gestor_fecha_a_marca_e_reabre_sem_ela(cg_casa):
    import gestor_rotina as GROT
    db = cg_casa["db"]
    ana = _pessoa(db, "ana", "MANAGER")
    _achado(db)
    with db.transaction() as con:
        QR.assumir(con, QR.ACHADO, "T:1", usuario_id=ana, por="Ana")
    with db.transaction() as con:      # a rodada não vê mais o achado: resolvido
        assert GROT.gravar_achados(con, [], date.today())["resolvidos"] == 1
        assert QR.ativos(con, QR.ACHADO, ["T:1"]) == {}
    [linha] = _linhas(db, QR.ACHADO)
    assert (linha["motivo_fim"], linha["fim_por"]) == (QR.CONCLUIU, "gestor (achado resolvido)")
    volta = {"chave": "T:1", "regra": "CENSEC", "gravidade": "VENCIDO", "setor": "NOTAS",
             "titulo": "Remessa da quinzena", "detalhe": None, "prazo": None, "fundamento": None}
    with db.transaction() as con:      # reabre com a mesma chave: ninguém «resolvendo»
        GROT.gravar_achados(con, [volta], date.today())
        assert QR.ativos(con, QR.ACHADO, ["T:1"]) == {}


def test_o_auditor_o_robo_e_a_conta_inativa_nao_assumem(cg_casa):
    db = cg_casa["db"]
    carla, robo, velho = _pessoa(db, "carla", "AUDITOR"), _pessoa(db, "robozinho"), _pessoa(db, "velho")
    with db.transaction() as con:
        banco(con).escrever("UPDATE users SET eh_robo = 1 WHERE id = %s", (robo,))
        banco(con).escrever("UPDATE users SET active = 0 WHERE id = %s", (velho,))
        for uid, frase in ((carla, "auditor"), (robo, "robô"), (velho, "inativa"), (999999, "inativa")):
            with pytest.raises(QR.QuemResolveError, match=frase):
                QR.assumir(con, QR.ACHADO, "T:1", usuario_id=uid, por="x")
    assert _linhas(db) == []
    assert not QR.pode_assumir(QR.ACHADO, "AUDITOR")
    assert not QR.pode_assumir(QR.ACHADO, "ADMIN", eh_robo=True)
    assert not QR.pode_assumir(QR.FASE, "USER")
    assert QR.pode_assumir(QR.ROTINA, "USER", pode_marcar_a_rotina=True)
    assert not QR.pode_tomar("USER") and QR.pode_tomar("MANAGER")


def test_o_indice_unico_segura_a_disputa(cg_casa, monkeypatch):
    db = cg_casa["db"]
    ana, bia = _pessoa(db, "ana"), _pessoa(db, "bia")
    with db.transaction() as con:
        QR.assumir(con, QR.ROTINA, "1:2026-11-26", usuario_id=ana, por="Ana")
    # o banco recusa a segunda marca aberta, e a marca fechada sem motivo
    for comando, parametros in (
            ("INSERT INTO ge_quem_resolve (tipo, chave, usuario_id, por, desde) "
             "VALUES ('ROTINA', '1:2026-11-26', %s, 'Bia', '2026-11-26T10:00:00')", (bia,)),
            ("INSERT INTO ge_quem_resolve (tipo, chave, usuario_id, por, desde, ate) "
             "VALUES ('ROTINA', '2:2026-11-26', %s, 'Bia', '2026-11-26T10:00:00', "
             "'2026-11-26T11:00:00')", (bia,)),
            ("INSERT INTO ge_quem_resolve (tipo, chave, usuario_id, por, desde) "
             "VALUES ('OUTRO', 'x', %s, 'Bia', '2026-11-26T10:00:00')", (bia,))):
        with pytest.raises(ERROS_DO_BANCO):
            with db.transaction() as con:
                banco(con).escrever(comando, parametros)
    # o clique que chega junto: a conferência do código não vê a marca, e o índice decide
    chamadas = []
    original = QR._ativo

    def cego(bd, tipo, chave):
        chamadas.append(1)
        return None if len(chamadas) == 1 else original(bd, tipo, chave)

    monkeypatch.setattr(QR, "_ativo", cego)
    with db.transaction() as con:
        with pytest.raises(QR.QuemResolveError, match="Ana acabou de assumir isto"):
            QR.assumir(con, QR.ROTINA, "1:2026-11-26", usuario_id=bia, por="Bia")
        # a transação continua viva depois da recusa do índice
        assert banco(con).valor("SELECT count(*) FROM ge_quem_resolve") == 1


# ------------------------------------------------------------ o fim automático


def test_o_feito_da_rotina_fecha_a_marca_daquela_referencia(cg_casa):
    db = cg_casa["db"]
    ana = _pessoa(db, "ana")
    rid, ref = _rotina_de_hoje(db, responsavel_id=ana)
    chave = QR.chave_da_rotina(rid, ref)
    with db.transaction() as con:
        QR.assumir(con, QR.ROTINA, chave, usuario_id=ana, por="Ana")
        QR.assumir(con, QR.ROTINA, QR.chave_da_rotina(rid, "2026-01-02"), usuario_id=ana, por="Ana")
        r = RT.marcar_feito(con, rid, ref, resultado="OK", observacao="", por="Ana",
                            usuario_id=ana)
    assert r["quem_resolvia"]["por"] == "Ana"
    with db.connect() as con:
        assert QR.ativos(con, QR.ROTINA, [chave]) == {}
        # a de outra referência não se fecha com este feito
        assert list(QR.ativos(con, QR.ROTINA, [QR.chave_da_rotina(rid, "2026-01-02")]))
    assert _linhas(db)[0]["motivo_fim"] == "CONCLUIU"


@pytest.mark.parametrize("situacao, campos", [
    ("CONCLUIDA", {"observacao": "Homologado no portal, protocolo de exemplo"}),
    ("DISPENSADA", {"observacao": "A Central dispensou a homologação"}),
])
def test_a_fase_concluida_ou_dispensada_fecha_a_marca(cg_casa, situacao, campos):
    db = cg_casa["db"]
    ana = _pessoa(db, "ana", "MANAGER")
    _, fid = _fase(db)
    with db.transaction() as con:
        QR.assumir(con, QR.FASE, str(fid), usuario_id=ana, por="Ana")
        feito = DP.alterar_fase(con, fid, {"situacao": situacao, **campos}, por="ana")
    assert feito["quem_resolvia"]["por"] == "Ana"
    assert [x["motivo_fim"] for x in _linhas(db, "FASE")] == ["CONCLUIU"]


def test_a_carga_dos_projetos_que_conclui_a_fase_fecha_a_marca(cg_casa):
    db = cg_casa["db"]
    ana = _pessoa(db, "ana", "MANAGER")
    spec = {"codigo": "PRJ-QR", "titulo": "PRJ-QR — Projeto de ensaio",
            "fases": [{"titulo": "Homologar com a Central"}]}
    with db.transaction() as con:
        DP.importar(con, spec, por="agente 11")
        fid = int(banco(con).valor("SELECT id FROM dev_projetos_fases WHERE titulo = %s",
                                   ("Homologar com a Central",)))
        QR.assumir(con, QR.FASE, str(fid), usuario_id=ana, por="Ana")
        spec["fases"][0].update(situacao="CONCLUIDA", observacao="Homologada (exemplo)")
        r = DP.importar(con, spec, por="agente 11")
    assert [(x["fase_id"], x["por"]) for x in r["quem_resolve_encerrados"]] == [(fid, "Ana")]
    assert [x["motivo_fim"] for x in _linhas(db, "FASE")] == ["CONCLUIU"]


# ------------------------------------------------------------ as telas


def test_a_checklist_marca_quem_resolve_a_rotina_e_o_achado(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    rid, ref = _rotina_de_hoje(db, codigo="NOTAS_CENSEC", area="NOTAS")
    aid = _achado(db)
    html = c.get(CHECKLIST).get_data(as_text=True)
    rotina = html[html.index('id="rotina"'):html.index('id="achados"')]
    achados = html[html.index('id="achados"'):html.index('id="fora"')]
    assert "Eu resolvo</button>" in rotina and "Eu resolvo</button>" in achados
    assert "em resolução" not in html

    r = c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "ROTINA", "rotina_id": rid,
                              "referencia": ref, "voltar": "checklist", "area": "NOTAS",
                              "nota": "abrindo o portal"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"{CHECKLIST}?area=NOTAS#rotina")
    r = c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "ACHADO", "achado_id": aid,
                              "voltar": "checklist"})
    assert r.headers["Location"].endswith(f"{CHECKLIST}#achados")
    [rot, ach] = _auditoria(db, "QUEM_RESOLVE_ASSUMIU")
    assert (rot["tipo"], rot["chave"], rot["titulo"], rot["nota"]) == (
        "ROTINA", f"{rid}:{ref}", "Conferir NOTAS_CENSEC", "abrindo o portal")
    assert (ach["tipo"], ach["chave"], ach["titulo"]) == ("ACHADO", "T:1", "Remessa da quinzena")

    html = c.get(CHECKLIST).get_data(as_text=True)
    rotina = html[html.index('id="rotina"'):html.index('id="achados"')]
    achados = html[html.index('id="achados"'):html.index('id="fora"')]
    for bloco in (rotina, achados):
        assert "MARIO EXEMPLO DOS SANTOS está resolvendo desde" in bloco
        assert "Largar</button>" in bloco and "1 em resolução" in bloco
    assert "— abrindo o portal" in rotina

    # o «Feito» fecha a marca da rotina, com auditoria
    c.post(f"/administrativo/rotina/{rid}/feito", data={
        "csrf_token": _token(c), "referencia": ref, "voltar": "checklist", "area": "NOTAS",
        "resultado": "OK", "observacao": ""})
    [fim] = _auditoria(db, "QUEM_RESOLVE_CONCLUIU")
    assert (fim["tipo"], fim["chave"], fim["de"]) == ("ROTINA", f"{rid}:{ref}",
                                                     "MARIO EXEMPLO DOS SANTOS")
    # largar o achado
    r = c.post(LARGAR, data={"csrf_token": _token(c), "tipo": "ACHADO", "achado_id": aid,
                             "voltar": "checklist"})
    assert r.status_code == 302 and _auditoria(db, "QUEM_RESOLVE_LARGOU")[0]["chave"] == "T:1"
    html = c.get(CHECKLIST).get_data(as_text=True)
    assert "está resolvendo" not in html and "em resolução" not in html
    # o POST sem token é recusado
    assert c.post(ASSUMIR, data={"tipo": "ACHADO", "achado_id": aid}).status_code == 400
    assert c.post(LARGAR, data={"tipo": "ACHADO", "achado_id": aid}).status_code == 400
    assert c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "ACHADO",
                                 "achado_id": 999999}).status_code == 404
    assert c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "NADA"}).status_code == 400


def test_o_gerente_assume_no_lugar_com_confirmacao(cg_casa):
    db = cg_casa["db"]
    aid = _achado(db)
    ana = _pessoa(db, "ana", "ADMIN")
    with db.transaction() as con:
        QR.assumir(con, QR.ACHADO, "T:1", usuario_id=ana, por="ANA EXEMPLO LIMA",
                   agora=datetime(2026, 11, 24, 9, 0))
    _pessoa(db, "gilda", "MANAGER")
    c = cg_casa["c"]
    cg_login(c, "gilda", SENHA)
    html = c.get(CHECKLIST).get_data(as_text=True)
    achados = html[html.index('id="achados"'):html.index('id="fora"')]
    assert "ANA EXEMPLO LIMA está resolvendo desde 24/11, há" in achados
    assert "Assumir no lugar</button>" in achados and "Confirmo que assumo no lugar de ANA" in achados
    assert "Eu resolvo</button>" not in achados and "Largar</button>" not in achados
    dados = {"tipo": "ACHADO", "achado_id": aid, "tomar": "1", "voltar": "checklist"}
    c.post(ASSUMIR, data={**dados, "csrf_token": _token(c)})                 # sem confirmar
    assert not _auditoria(db, "QUEM_RESOLVE_TOMOU")
    c.post(ASSUMIR, data={**dados, "confirmo": "1", "csrf_token": _token(c)})
    [det] = _auditoria(db, "QUEM_RESOLVE_TOMOU")
    assert det["de"] == "ANA EXEMPLO LIMA" and det["chave"] == "T:1"
    assert [x["motivo_fim"] for x in _linhas(db)] == ["TOMADO", None]


def test_o_escrevente_resolve_a_propria_rotina_e_nada_mais(cg_casa):
    db = cg_casa["db"]
    bruno, outro = _pessoa(db, "bruno"), _pessoa(db, "outro")
    meu, ref = _rotina_de_hoje(db, codigo="RCPN_SIRC", area="RCPN", responsavel_id=bruno)
    alheio, ref2 = _rotina_de_hoje(db, codigo="FIN_GUIA", area="FINANCEIRO", responsavel_id=outro)
    aid = _achado(db)
    _, fid = _fase(db)
    with db.transaction() as con:
        QR.assumir(con, QR.ROTINA, QR.chave_da_rotina(alheio, ref2), usuario_id=outro, por="Outro")
    c = cg_casa["c"]
    cg_login(c, "bruno", SENHA)
    html = c.get("/minha-rotina").get_data(as_text=True)
    assert "Eu resolvo</button>" in html
    r = c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "ROTINA", "rotina_id": meu,
                              "referencia": ref, "voltar": "minha"})
    assert r.headers["Location"].endswith(f"/minha-rotina#rotina-{meu}")
    html = c.get("/minha-rotina").get_data(as_text=True)
    assert "BRUNO EXEMPLO LIMA está resolvendo desde" in html and "1 em resolução" in html
    nega = [
        {"tipo": "ROTINA", "rotina_id": alheio, "referencia": ref2},                 # não é dele
        {"tipo": "ROTINA", "rotina_id": alheio, "referencia": ref2, "tomar": "1", "confirmo": "1"},
        {"tipo": "ACHADO", "achado_id": aid},
        {"tipo": "FASE", "fase_id": fid},
    ]
    for dados in nega:
        assert c.post(ASSUMIR, data={**dados, "csrf_token": _token(c)}).status_code == 403, dados
    assert [x["usuario_id"] for x in _linhas(db, "ROTINA") if x["ate"] is None] == [outro, bruno]


def test_o_auditor_ve_a_marca_e_nao_assume(cg_casa):
    db = cg_casa["db"]
    aid = _achado(db)
    ana = _pessoa(db, "ana", "ADMIN")
    with db.transaction() as con:
        QR.assumir(con, QR.ACHADO, "T:1", usuario_id=ana, por="ANA EXEMPLO LIMA")
    _pessoa(db, "carla", "AUDITOR")
    c = cg_casa["c"]
    cg_login(c, "carla", SENHA)
    html = c.get(CHECKLIST).get_data(as_text=True)
    assert "ANA EXEMPLO LIMA está resolvendo" in html
    assert "Eu resolvo</button>" not in html and "Assumir no lugar</button>" not in html
    assert c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "ACHADO",
                                 "achado_id": aid, "tomar": "1", "confirmo": "1"}).status_code == 403
    assert c.post(LARGAR, data={"csrf_token": _token(c), "tipo": "ACHADO",
                                "achado_id": aid}).status_code == 403


def test_os_projetos_marcam_quem_cuida_da_fase(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    pid, fid = _fase(db)
    ficha = c.get(f"/desenvolvimento/projetos/{pid}").get_data(as_text=True)
    assert "Eu cuido desta fase</button>" in ficha
    r = c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "FASE", "fase_id": fid,
                              "voltar": "projeto"})
    assert r.headers["Location"].endswith(f"/desenvolvimento/projetos/{pid}#fase-{fid}")
    [det] = _auditoria(db, "QUEM_RESOLVE_ASSUMIU")
    assert (det["tipo"], det["chave"]) == ("FASE", str(fid))
    assert det["titulo"] == "PRJ-QR — Projeto de ensaio — Homologar com a Central"
    ficha = c.get(f"/desenvolvimento/projetos/{pid}").get_data(as_text=True)
    assert "MARIO EXEMPLO DOS SANTOS está cuidando desde" in ficha and "Largar</button>" in ficha
    lista = c.get("/desenvolvimento/projetos").get_data(as_text=True)
    assert "(MARIO EXEMPLO DOS SANTOS está nela)" in lista
    # a fase concluída fecha a marca, com auditoria
    r = c.post(f"/desenvolvimento/projetos/{pid}/fases/{fid}/alterar", data={
        "csrf_token": _token(c), "formulario": "situacao", "situacao": "CONCLUIDA",
        "observacao": "Homologada no portal (exemplo)"})
    assert r.status_code == 302
    [fim] = _auditoria(db, "QUEM_RESOLVE_CONCLUIU")
    assert (fim["tipo"], fim["chave"]) == ("FASE", str(fid))
    ficha = c.get(f"/desenvolvimento/projetos/{pid}").get_data(as_text=True)
    assert "está cuidando" not in ficha and "Eu cuido desta fase</button>" not in ficha
    # a fase feita não se assume
    c.post(ASSUMIR, data={"csrf_token": _token(c), "tipo": "FASE", "fase_id": fid})
    assert len(_auditoria(db, "QUEM_RESOLVE_ASSUMIU")) == 1

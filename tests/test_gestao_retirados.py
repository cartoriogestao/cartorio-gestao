"""O que não cabe à gestão — retirar da Checklist do dia e dos Projetos (T019).

Pedido do oficial em 25/11/2026: «permitir que retiremos do checklist do dia e
dos projetos itens que nao cabem a gestao ou admin». Os testes provam:

  * retirar exige motivo (texto curto); o motivo pronto é opcional e fechado;
  * o achado retirado sai da lista e da contagem da checklist, aparece em «Ver
    os retirados» com quem, quando e o motivo, e «Devolver à lista» o traz de
    volta — nada se apaga nem se resolve em `ge_achados`;
  * a marca se prende à CHAVE do achado: a rodada seguinte do gestor (a mesma
    chave, até depois de fechado e reaberto) não o traz de volta; chave nova
    é achado novo e aparece;
  * a COR OFICIAL não muda (é a do painel e do retrato); a checklist e o
    cartão do painel mostram também a cor «sem os retirados» e quantos são;
  * o oficial e o gerente retiram e devolvem, com auditoria; o auditor vê os
    retirados e não grava; o balcão não entra;
  * nos Projetos, o retirado sai da lista principal, a ficha continua abrindo,
    o histórico fica, e «Devolver à lista» o traz de volta.

Datas fixas em novembro de 2026: terça 10/11 é «hoje» nos testes de função.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conformidade as CF                     # noqa: E402
import dev_projetos as DP                     # noqa: E402
import gestao_retirados as GR                 # noqa: E402
import gestor_checklist as CK                 # noqa: E402
import gestor_rotina as GROT                  # noqa: E402
from bd_nativo import banco                   # noqa: E402
from conftest import cg_login                 # noqa: E402

HOJE = date(2026, 11, 10)
SENHA = "Senha#12345"
CHECKLIST = "/administrativo/gestor/checklist"


def _rodada_de_hoje(db) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_execucoes(iniciada_em, terminada_em, hoje) VALUES (%s,%s,%s)",
            (date.today().isoformat() + "T07:30:00", date.today().isoformat() + "T07:35:00",
             date.today().isoformat()))


def _achado(db, chave, regra, gravidade, setor, visto=None, titulo="Achado de teste") -> int:
    visto = visto or date.today().isoformat() + "T07:30:00"
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, "
            "primeiro_visto_em, ultimo_visto_em) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (chave, regra, gravidade, setor, titulo, visto, visto))
        return int(bd.valor("SELECT id FROM ge_achados WHERE chave = %s", (chave,)))


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _retirar(c, achado_id, motivo="É do escrevente das notas", codigo="ESCREVENTE", area=""):
    return c.post(f"{CHECKLIST}/retirar", data={
        "achado_id": achado_id, "motivo": motivo, "motivo_codigo": codigo, "area": area,
        "csrf_token": _token(c)})


def _devolver(c, achado_id, area=""):
    return c.post(f"{CHECKLIST}/devolver", data={
        "achado_id": achado_id, "area": area, "csrf_token": _token(c)})


def _entrar(cg_casa, nome, papel):
    cg_casa["db"].create_user(nome, f"{nome.upper()} EXEMPLO LIMA", SENHA, papel)
    c = cg_casa["c"]
    cg_login(c, nome, SENHA)
    return c


def _auditoria(db, acao) -> list[dict]:
    with db.connect() as con:
        return [json.loads(r["details"]) for r in banco(con).ler(
            "SELECT details FROM audit_logs WHERE action = %s ORDER BY id", (acao,))]


# ------------------------------------------------------------ a função


def test_retirar_exige_motivo_e_aceita_motivo_pronto(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        for vazio in ("", "  ", "ok"):
            with pytest.raises(GR.RetiradaError, match="obrigatório"):
                GR.retirar(con, GR.CHECKLIST, "T:1", motivo=vazio, motivo_codigo="TI",
                           por="Fulano", usuario_id=None)
        with pytest.raises(GR.RetiradaError, match="curto"):
            GR.retirar(con, GR.CHECKLIST, "T:1", motivo="x" * (GR.MOTIVO_MAXIMO + 1),
                       por="Fulano", usuario_id=None)
        with pytest.raises(GR.RetiradaError, match="desconhecido"):
            GR.retirar(con, GR.CHECKLIST, "T:1", motivo="É do TI", motivo_codigo="NAO_EXISTE",
                       por="Fulano", usuario_id=None)
        with pytest.raises(GR.RetiradaError):
            GR.retirar(con, "OUTRA_TELA", "T:1", motivo="É do TI", por="F", usuario_id=None)
        assert GR.ativas(con, GR.CHECKLIST) == {}
        # sem motivo pronto também vale: o texto é que é obrigatório
        r = GR.retirar(con, GR.CHECKLIST, "T:1", motivo="  É   do TI  ", por="Fulano",
                       usuario_id=7)
        assert r["gravou"] and r["retirada"]["motivo"] == "É do TI"
        assert r["retirada"]["motivo_codigo"] is None
        # o segundo pedido não abre outra linha
        de_novo = GR.retirar(con, GR.CHECKLIST, "T:1", motivo="outra vez", motivo_codigo="TI",
                             por="Beltrano", usuario_id=8)
        assert not de_novo["gravou"] and de_novo["retirada"]["por"] == "Fulano"
        # a mesma chave na outra tela é outra coisa
        assert GR.ativas(con, GR.PROJETOS) == {}


def test_devolver_guarda_o_historico(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        GR.retirar(con, GR.PROJETOS, "3", motivo="É de fora da serventia", motivo_codigo="FORA",
                   por="Fulano", usuario_id=1)
        assert GR.devolver(con, GR.PROJETOS, "3", por="Beltrano", usuario_id=2)["por"] == "Fulano"
        assert GR.devolver(con, GR.PROJETOS, "3", por="Beltrano", usuario_id=2) is None
        assert GR.ativas(con, GR.PROJETOS) == {}
        GR.retirar(con, GR.PROJETOS, "3", motivo="Retirado de novo", por="Fulano", usuario_id=1)
        linhas = banco(con).ler(
            "SELECT motivo, devolvido_por FROM ge_retirados_da_gestao ORDER BY id")
    assert [(x["motivo"], x["devolvido_por"]) for x in linhas] == [
        ("É de fora da serventia", "Beltrano"), ("Retirado de novo", None)]


def test_a_retirada_se_prende_a_chave_do_achado(cg_casa):
    """A rodada do gestor regrava pela chave: o retirado continua retirado, até
    fechado e reaberto; o achado de chave nova aparece."""
    db = cg_casa["db"]
    _achado(db, "SIRC:1", "SIRC", "PRAZO", "RCPN", visto="2026-11-10T07:30:00")
    with db.transaction() as con:
        GR.retirar(con, GR.CHECKLIST, "SIRC:1", motivo="É do escrevente do RCPN",
                   por="Fulano", usuario_id=None)
    novo = {"chave": "SIRC:1", "regra": "SIRC", "gravidade": "VENCIDO", "setor": "RCPN",
            "titulo": "Achado de teste", "detalhe": "", "prazo": None, "fundamento": None}
    outro = {**novo, "chave": "SIRC:2"}
    with db.transaction() as con:
        GROT.gravar_achados(con, [novo, outro], HOJE)     # a rodada seguinte
    with db.connect() as con:
        g = CK.achados_por_area(con, HOJE, papel="ADMIN", retiradas=GR.ativas(con, GR.CHECKLIST))
    marcados = {a["id"]: bool(a["retirada"]) for a in g["RCPN"]}
    assert sorted(marcados.values()) == [False, True]
    with db.transaction() as con:
        GROT.gravar_achados(con, [outro], HOJE)           # o SIRC:1 fecha…
        GROT.gravar_achados(con, [novo, outro], HOJE)     # …e volta, com a mesma chave
    with db.connect() as con:
        g = CK.achados_por_area(con, HOJE, papel="ADMIN", retiradas=GR.ativas(con, GR.CHECKLIST))
        n = banco(con).valor("SELECT count(*) FROM ge_achados")
    assert sorted(bool(a["retirada"]) for a in g["RCPN"]) == [False, True]
    assert n == 2                                        # nada se apagou


def test_a_cor_oficial_conta_o_retirado_e_a_outra_nao(cg_casa):
    db = cg_casa["db"]
    _rodada_de_hoje(db)
    _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS")
    _achado(db, "T:2", "QUALQUER", "ATENCAO", "NOTAS")
    with db.transaction() as con:
        GR.retirar(con, GR.CHECKLIST, "T:1", motivo="É do escrevente das notas",
                   por="Fulano", usuario_id=None)
        oficial = CF.medir(con)
        sem = CF.medir(con, excluir_chaves=frozenset({"T:1"}))
    assert oficial["areas"]["NOTAS"]["cor"] == CF.VERMELHO
    assert oficial["areas"]["NOTAS"]["abertos"] == 2
    assert "retirados" not in oficial                   # o retrato não muda de forma
    assert sem["areas"]["NOTAS"]["cor"] == CF.VERDE
    assert sem["areas"]["NOTAS"]["abertos"] == 1
    assert sem["retirados"] == {"NOTAS": 1}
    ck = CK.montar(db, papel="ADMIN")
    assert ck["total_achados"] == 1 and ck["total_retirados"] == 1
    assert ck["retirados_por_area"] == {"NOTAS": 1}
    assert ck["cor_sem_retirados"]["NOTAS"] == CF.VERDE
    assert ck["medicao"]["areas"]["NOTAS"]["cor"] == CF.VERMELHO
    assert ck["cor_da_rotina"]["NOTAS"] == CF.VERDE      # a fila de trabalho, sem o retirado


# ------------------------------------------------------------ a tela da checklist


def test_o_oficial_retira_e_devolve_pela_tela_com_auditoria(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _rodada_de_hoje(db)
    aid = _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS", titulo="Remessa da quinzena")
    _achado(db, "T:2", "SIRC", "PRAZO", "RCPN", titulo="Envio do mês")
    html = c.get(CHECKLIST).get_data(as_text=True)
    assert "Retirar da checklist</button>" in html and "Remessa da quinzena" in html

    # sem motivo: não grava, avisa
    r = _retirar(c, aid, motivo="", area="NOTAS")
    assert r.status_code == 302
    with db.connect() as con:
        assert GR.ativas(con, GR.CHECKLIST) == {}
    assert not _auditoria(db, "GESTOR_CHECKLIST_RETIRADO")

    r = _retirar(c, aid, area="NOTAS")
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"{CHECKLIST}?area=NOTAS#achados")
    [det] = _auditoria(db, "GESTOR_CHECKLIST_RETIRADO")
    assert det["chave"] == "T:1" and det["motivo_codigo"] == "ESCREVENTE"
    assert det["motivo"] == "É do escrevente das notas"
    with db.connect() as con:                            # não resolveu
        assert banco(con).valor(
            "SELECT count(*) FROM ge_achados WHERE resolvido_em IS NULL") == 2

    html = c.get(CHECKLIST).get_data(as_text=True)
    principal = html[html.index('id="achados"'):html.index('id="conferencias"')]
    assert "Remessa da quinzena" not in principal and "Envio do mês" in principal
    assert "Achados abertos da TI e da administração (1)" in html
    assert "Ver os retirados (1)" in html and "1 retirado(s) não conta(m) aqui" in html
    assert 'id="retirados"' not in html
    assert "sem os retirados: Verde" in html             # ao lado da oficial…
    assert "Vermelho</span>" in html                      # …que continua vermelha

    html = c.get(f"{CHECKLIST}?ver=retirados").get_data(as_text=True)
    retirados = html[html.index('id="retirados"'):]
    assert "Remessa da quinzena" in retirados
    assert "É do escrevente da área" in retirados and "É do escrevente das notas" in retirados
    assert "MARIO EXEMPLO DOS SANTOS" in retirados.upper() or "mario" in retirados
    assert "Devolver à lista</button>" in retirados

    r = _devolver(c, aid, area="NOTAS")
    assert r.headers["Location"].endswith(f"{CHECKLIST}?area=NOTAS&ver=retirados#achados")
    [det] = _auditoria(db, "GESTOR_CHECKLIST_DEVOLVIDO")
    assert det["chave"] == "T:1"
    html = c.get(CHECKLIST).get_data(as_text=True)
    assert "Achados abertos da TI e da administração (2)" in html and "Ver os retirados" not in html
    # devolver de novo não grava outra auditoria
    _devolver(c, aid)
    assert len(_auditoria(db, "GESTOR_CHECKLIST_DEVOLVIDO")) == 1
    assert _retirar(c, 999999).status_code == 404
    assert _retirar(c, "abc").status_code == 400


def test_o_cartao_do_painel_mostra_as_duas_cores(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _rodada_de_hoje(db)
    aid = _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS")
    html = c.get("/").get_data(as_text=True)
    assert "retirado(s) por não caber(em) à gestão" not in html
    _retirar(c, aid)
    html = c.get("/").get_data(as_text=True)
    cartao = html[html.index('href="/administrativo/gestor/checklist?area=NOTAS"'):]
    cartao = cartao[:cartao.index("</a>")]
    assert "Vermelho" in cartao                           # a oficial
    assert "1 retirado(s) por não caber(em) à gestão" in cartao
    assert re.search(r"sem eles: <span class=\"badge ok\">Verde", cartao)


def test_o_auditor_ve_os_retirados_e_nao_grava(cg_casa):
    db = cg_casa["db"]
    _rodada_de_hoje(db)
    aid = _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS", titulo="Remessa da quinzena")
    with db.transaction() as con:
        GR.retirar(con, GR.CHECKLIST, "T:1", motivo="É do escrevente das notas",
                   por="Fulano", usuario_id=None)
    c = _entrar(cg_casa, "carla", "AUDITOR")
    html = c.get(f"{CHECKLIST}?ver=retirados").get_data(as_text=True)
    assert "Ver os retirados (1)" in html
    retirados = html[html.index('id="retirados"'):]
    assert "Remessa da quinzena" in retirados and "É do escrevente das notas" in retirados
    assert "Devolver à lista</button>" not in html and "Retirar da checklist" not in html
    assert _devolver(c, aid).status_code == 403
    assert _retirar(c, aid).status_code == 403
    with db.connect() as con:
        assert "T:1" in GR.ativas(con, GR.CHECKLIST)


def test_o_gerente_retira_e_o_balcao_nao(cg_casa):
    db = cg_casa["db"]
    aid = _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS")
    c = _entrar(cg_casa, "gilda", "MANAGER")
    assert _retirar(c, aid).status_code == 302
    assert _auditoria(db, "GESTOR_CHECKLIST_RETIRADO")
    c.get("/logout")
    c = _entrar(cg_casa, "bruno", "USER")
    assert _devolver(c, aid).status_code == 403


# ------------------------------------------------------------ os projetos


def _um_projeto(db) -> int:
    with db.transaction() as con:
        DP.seed_sandbox_exemplo(con)
        projetos = DP.listar_projetos(con)
        pid = int(projetos[0]["id"])
        DP.registrar_andamento(con, pid, "Andamento que fica", autor="mario")
        return pid


def _post_projeto(c, pid, acao, **dados):
    return c.post(f"/desenvolvimento/projetos/{pid}/{acao}",
                  data={"csrf_token": _token(c), **dados})


def test_o_projeto_retirado_sai_da_lista_e_nada_se_apaga(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    pid = _um_projeto(db)
    with db.connect() as con:
        titulo = DP.obter_projeto(con, pid)["titulo"]
        total = len(DP.listar_projetos(con))
    ficha = c.get(f"/desenvolvimento/projetos/{pid}").get_data(as_text=True)
    assert "Retirar dos projetos da gestão</button>" in ficha

    r = _post_projeto(c, pid, "retirar", motivo="")
    assert r.headers["Location"].endswith(f"/desenvolvimento/projetos/{pid}")
    assert not _auditoria(db, "DEV_PROJETO_RETIRADO")

    r = _post_projeto(c, pid, "retirar", motivo="É do TI, não da gestão", motivo_codigo="TI")
    assert r.status_code == 302 and r.headers["Location"].endswith("/desenvolvimento/projetos")
    [det] = _auditoria(db, "DEV_PROJETO_RETIRADO")
    assert det["motivo_codigo"] == "TI" and det["titulo"] == titulo

    lista = c.get("/desenvolvimento/projetos").get_data(as_text=True)
    principal = lista[:lista.index("Ver os retirados (1)")] + lista[lista.index("<table"):]
    assert f">{titulo}</a>" not in principal
    assert f"Projetos ({total - 1})" in lista
    lista = c.get("/desenvolvimento/projetos?ver=retirados").get_data(as_text=True)
    retirados = lista[lista.index('id="retirados"'):]
    assert titulo in retirados and "É do TI, não da gestão" in retirados
    assert "Devolver à lista</button>" in retirados

    # a ficha continua abrindo, com o aviso e o histórico
    ficha = c.get(f"/desenvolvimento/projetos/{pid}").get_data(as_text=True)
    assert "Retirado dos projetos da gestão" in ficha and "Andamento que fica" in ficha
    with db.connect() as con:
        assert len(DP.listar_projetos(con)) == total
        assert DP.listar_andamento(con, pid)

    r = _post_projeto(c, pid, "devolver")
    assert r.headers["Location"].endswith("/desenvolvimento/projetos?ver=retirados")
    assert len(_auditoria(db, "DEV_PROJETO_DEVOLVIDO")) == 1
    lista = c.get("/desenvolvimento/projetos").get_data(as_text=True)
    assert f">{titulo}</a>" in lista and "Ver os retirados" not in lista
    assert _post_projeto(c, 999999, "retirar", motivo="Qualquer").status_code == 404


@pytest.mark.parametrize("papel", ["USER", "AUDITOR"])
def test_quem_nao_cuida_dos_projetos_nao_retira(cg_casa, papel):
    db = cg_casa["db"]
    pid = _um_projeto(db)
    c = _entrar(cg_casa, f"pessoa_{papel.lower()}", papel)
    assert _post_projeto(c, pid, "retirar", motivo="É do TI").status_code == 403
    assert _post_projeto(c, pid, "devolver").status_code == 403
    with db.connect() as con:
        assert GR.ativas(con, GR.PROJETOS) == {}


def test_o_gerente_retira_projeto(cg_casa):
    db = cg_casa["db"]
    pid = _um_projeto(db)
    c = _entrar(cg_casa, "gilda", "MANAGER")
    assert _post_projeto(c, pid, "retirar", motivo="É de fora da serventia",
                         motivo_codigo="FORA").status_code == 302
    with db.connect() as con:
        assert str(pid) in GR.ativas(con, GR.PROJETOS)

"""A checklist de gestão do dia — os achados por área e as conferências de hoje.

Pedido do oficial em 19/11/2026, diante do semáforo de conformidade: «não
consigo clicar nos itens e não vejo checklist». Os testes provam:

  * os achados abertos se agrupam pela MESMA área do semáforo (o caixa cai no
    Financeiro pela regra), na ordem da gravidade, com o link da tela onde se
    resolvem; o resolvido não aparece; o filtro `?area=` mostra só aquela;
  * o achado de PLD/COAF é sigiloso para quem não é o oficial;
  * «conferido hoje» grava quem e quando, uma vez por dia, com auditoria — e
    NÃO resolve o achado nem muda a cor do semáforo;
  * sem rodada válida do gestor, a tela diz no topo e não mostra nada como
    «em dia»; a contagem que quebra mostra «não deu para contar», e não zero;
  * o oficial, o gerente e o auditor abrem; o auditor não marca; o balcão não
    entra;
  * os cartões do painel geral e as áreas do painel do celular viram links
    para a checklist filtrada, e o retrato que sai da casa continua só com
    códigos e contagens.

Datas fixas em novembro de 2026, longe de feriado: terça 10/11 é «hoje».
Dados inventados: «Beatriz Exemplo de Souza» no título de um achado.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conformidade as CF                     # noqa: E402
import gestor_checklist as CK                 # noqa: E402
import navegacao as NAV                       # noqa: E402
import painel_numeros as PN                   # noqa: E402
import painel_retrato as PR                   # noqa: E402
from bd_nativo import banco                   # noqa: E402
from conftest import cg_login                 # noqa: E402

HOJE = date(2026, 11, 10)
SENHA = "Senha#12345"
NOME = "BEATRIZ EXEMPLO DE SOUZA"


def _rodada(db, terminada: str | None, erro: str | None = None) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_execucoes(iniciada_em, terminada_em, hoje, erro) "
            "VALUES (%s,%s,%s,%s)",
            ((terminada or "2026-11-10T14:00:00")[:10] + "T07:30:00", terminada,
             (terminada or "2026-11-10")[:10], erro))


def _rodada_de_hoje(db) -> None:
    _rodada(db, date.today().isoformat() + "T07:35:00")


def _achado(db, chave, regra, gravidade, setor, visto="2026-11-10T07:30:00",
            prazo=None, resolvido=None, titulo="Achado de teste") -> None:
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, prazo, "
            "primeiro_visto_em, ultimo_visto_em, resolvido_em) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (chave, regra, gravidade, setor, titulo, prazo, visto, visto, resolvido))


def _por_area(db, papel="ADMIN", area=None) -> dict:
    with db.connect() as con:
        return CK.achados_por_area(con, HOJE, papel=papel, area=area)


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _conferir(c, item, area=""):
    return c.post("/administrativo/gestor/checklist/conferido",
                  data={"item": item, "area": area, "csrf_token": _token(c)})


def _entrar(cg_casa, nome, papel):
    cg_casa["db"].create_user(nome, f"{nome.upper()} EXEMPLO LIMA", SENHA, papel)
    c = cg_casa["c"]
    cg_login(c, nome, SENHA)
    return c


# ------------------------------------------------------------ os achados


def test_os_achados_se_agrupam_pela_area_do_semaforo(cg_casa):
    db = cg_casa["db"]
    _achado(db, "T:1", "ATENCAO_QUALQUER", "ATENCAO", "NOTAS")
    _achado(db, "T:2", "ATO_SEM_SELO", "CRITICO", "NOTAS_QUALIFICACAO",
            visto="2026-11-06T07:30:00")
    _achado(db, "T:3", "CENSEC", "VENCIDO", "NOTAS", prazo="2026-11-05")
    _achado(db, "T:4", "CAIXA_ABERTO", "CRITICO", "RCPN")      # o caixa é Financeiro
    _achado(db, "T:5", "SIRC", "PRAZO", "RCPN", prazo="2026-11-12")
    _achado(db, "T:6", "CENSEC", "VENCIDO", "NOTAS", resolvido="2026-11-10T07:30:00")
    _achado(db, "T:7", "REGRA_NOVA", "ATENCAO", "SETOR_NOVO")
    g = _por_area(db)
    assert list(g) == ["NOTAS", "RCPN", "FINANCEIRO", CF.OUTROS]   # a ordem do semáforo
    assert [a["gravidade"] for a in g["NOTAS"]] == ["VENCIDO", "CRITICO", "ATENCAO"]
    assert g["NOTAS"][1]["dias_em_aberto"] == 4
    assert g["NOTAS"][0]["prazo"] == "2026-11-05"
    assert [a["regra"] for a in g["FINANCEIRO"]] == ["CAIXA_ABERTO"]
    # a mesma régua do semáforo: o que a tela lista é o que o cartão conta
    with db.connect() as con:
        m = CF.medir(con, HOJE)
    for area, lista in g.items():
        assert m["areas"][area]["abertos"] == len(lista)


def test_cada_achado_leva_a_tela_onde_se_resolve(cg_casa):
    db = cg_casa["db"]
    _achado(db, "SIRC:x", "SIRC", "PRAZO", "RCPN", prazo="2026-11-12")
    _achado(db, "CAIXA_CONF:9", "CAIXA_PRONTO_PARA_VISTO", "ATENCAO", "GESTAO")
    _achado(db, "T:sem", "REGRA_SEM_TELA", "ATENCAO", "TI")
    g = _por_area(db)
    assert g["RCPN"][0]["link"] == "/rcpn/sirc"
    assert g["FINANCEIRO"][0]["link"] == "/administrativo/gestor/caixas"
    assert g["ADMINISTRACAO"][0]["link"] is None


def test_o_filtro_mostra_so_a_area_pedida(cg_casa):
    db = cg_casa["db"]
    _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS")
    _achado(db, "T:2", "SIRC", "PRAZO", "RCPN")
    assert list(_por_area(db, area="NOTAS")) == ["NOTAS"]
    assert _por_area(db, area="RI") == {}


def test_o_pld_e_sigiloso_para_quem_nao_e_o_oficial(cg_casa):
    db = cg_casa["db"]
    _achado(db, "PLD:7", "PLD_COAF", "PRAZO", "GESTAO", prazo="2026-11-20",
            titulo="PLD/COAF: caso nº 7 (NOTAS) para analisar e decidir")
    oficial = _por_area(db, "ADMIN")["ADMINISTRACAO"][0]
    gerente = _por_area(db, "MANAGER")["ADMINISTRACAO"][0]
    assert "caso nº 7" in oficial["titulo"] and oficial["link"] == "/administrativo/pld"
    assert gerente["titulo"] == CK.TITULO_SIGILOSO and gerente["link"] is None


# ------------------------------------------------------------ o «conferido hoje»


def test_conferir_grava_uma_vez_por_dia_e_nao_resolve_o_achado(cg_casa):
    db = cg_casa["db"]
    _rodada(db, "2026-11-10T07:35:00")
    _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS")
    with db.connect() as con:
        antes = CF.medir(con, HOJE)
    with db.transaction() as con:
        r1 = CK.marcar_conferido(con, "ENVIOS", HOJE, por="mario", usuario_id=1,
                                 agora=datetime(2026, 11, 10, 9, 15))
        r2 = CK.marcar_conferido(con, "ENVIOS", HOJE, por="carla", usuario_id=2,
                                 agora=datetime(2026, 11, 10, 10, 0))
    assert r1["gravou"] is True and r2["gravou"] is False
    assert r2["por"] == "mario" and r2["em"] == "2026-11-10T09:15"
    with db.connect() as con:
        assert CK.conferidos_hoje(con, HOJE) == {
            "ENVIOS": {"por": "mario", "em": "2026-11-10T09:15"}}
        assert CK.conferidos_hoje(con, date(2026, 11, 11)) == {}
        # conferir NÃO é resolver: o achado segue aberto, e a cor não muda
        assert banco(con).valor(
            "SELECT count(*) FROM ge_achados WHERE resolvido_em IS NULL") == 1
        assert CF.medir(con, HOJE)["areas"] == antes["areas"]


def test_item_desconhecido_nao_se_grava(cg_casa):
    with cg_casa["db"].transaction() as con:
        with pytest.raises(CK.ChecklistError):
            CK.marcar_conferido(con, "QUALQUER", HOJE, por="mario", usuario_id=1)


def test_todo_item_tem_rota_e_codigo_unico():
    import app as APP  # noqa: F401  (só para garantir que o módulo importa)
    codigos = [c for c, *_ in CK.CONFERENCIAS]
    assert len(codigos) == len(set(codigos))
    assert CK.DEPENDEM_DO_GESTOR <= CK.CODIGOS
    rotulos = {r for _, r, *_ in CK.CONFERENCIAS}
    assert {"Envios às Centrais", "Automação", "Robôs", "Leitura dos textos (IA)",
            "Caixas para o visto", "Selos cancelados", "Gratuidades",
            "Problemas do sistema", "Correções de ofício", "Avisos", "Tarefas"} == rotulos


# ------------------------------------------------------------ a tela


def test_sem_rodada_a_tela_avisa_e_nada_aparece_em_dia(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS")
    r = c.get("/administrativo/gestor/checklist")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    topo = html.index("Sem medição")
    assert topo < html.index("Achados abertos")
    assert CF.ROTULO_DO_MOTIVO[CF.SEM_RODADA] in html
    assert "Nenhum achado aberto" not in html
    # o zero dos envios sai do gestor: sem rodada, ele não vale como «em dia»
    assert "zero aqui não quer dizer em dia" in html
    html_ri = c.get("/administrativo/gestor/checklist?area=RI").get_data(as_text=True)
    assert "não dá para dizer se Registro de Imóveis está em dia" in html_ri


def test_com_rodada_a_tela_lista_por_area_e_filtra(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _rodada_de_hoje(db)
    _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS", titulo="CENSEC: quinzena sem envio")
    _achado(db, "SIRC:x", "SIRC", "PRAZO", "RCPN", titulo=f"Nascimento de {NOME} fora do SIRC")
    html = c.get("/administrativo/gestor/checklist").get_data(as_text=True)
    assert "Sem medição:" not in html
    assert "CENSEC: quinzena sem envio" in html and 'href="/rcpn/sirc"' in html
    for _, rotulo, *_ in CK.CONFERENCIAS:
        assert rotulo in html
    so_notas = c.get("/administrativo/gestor/checklist?area=NOTAS").get_data(as_text=True)
    assert "CENSEC: quinzena sem envio" in so_notas
    assert "fora do SIRC" not in so_notas
    vazio = c.get("/administrativo/gestor/checklist?area=RI").get_data(as_text=True)
    assert "Nenhum achado aberto em Registro de Imóveis" in vazio
    # área que não existe é como sem filtro
    torta = c.get("/administrativo/gestor/checklist?area=XYZ").get_data(as_text=True)
    assert "fora do SIRC" in torta


def test_contagem_que_quebra_nao_vira_zero(cg_casa_logada, monkeypatch):
    def quebra(con, hoje):
        raise RuntimeError("tabela que não existe")

    conferencias = tuple((cod, rot, end, quebra if cod == "TAREFAS" else conta, olhar)
                         for cod, rot, end, conta, olhar in CK.CONFERENCIAS)
    monkeypatch.setattr(CK, "CONFERENCIAS", conferencias)
    r = cg_casa_logada["c"].get("/administrativo/gestor/checklist")
    assert r.status_code == 200
    assert "não deu para contar" in r.get_data(as_text=True)


def test_o_oficial_marca_conferido_pela_tela_com_auditoria(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _achado(db, "T:1", "CENSEC", "VENCIDO", "NOTAS")
    r = _conferir(c, "AUTOMACAO", area="NOTAS")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/administrativo/gestor/checklist?area=NOTAS")
    with db.connect() as con:
        linha = banco(con).um(
            "SELECT details FROM audit_logs WHERE action = 'GESTOR_CHECKLIST_CONFERIDO' "
            "ORDER BY id DESC LIMIT 1")
        assert banco(con).valor(
            "SELECT count(*) FROM ge_achados WHERE resolvido_em IS NULL") == 1
    assert json.loads(linha["details"])["item"] == "AUTOMACAO"
    html = c.get("/administrativo/gestor/checklist").get_data(as_text=True)
    linha_automacao = html[html.index(">Automação<"):html.index(">Robôs<")]
    assert "Conferido hoje</button>" not in linha_automacao
    assert "às " in linha_automacao
    # o segundo clique do dia não grava de novo
    _conferir(c, "AUTOMACAO")
    with db.connect() as con:
        assert banco(con).valor(
            "SELECT count(*) FROM audit_logs WHERE action = 'GESTOR_CHECKLIST_CONFERIDO'") == 1
    assert _conferir(c, "QUALQUER").status_code == 400


def test_o_auditor_ve_e_nao_marca(cg_casa):
    c = _entrar(cg_casa, "carla", "AUDITOR")
    html = c.get("/administrativo/gestor/checklist").get_data(as_text=True)
    assert "Checklist de gestão do dia" in html
    assert "Conferido hoje</button>" not in html
    assert _conferir(c, "ENVIOS").status_code == 403


def test_o_gerente_marca(cg_casa):
    c = _entrar(cg_casa, "gilda", "MANAGER")
    assert c.get("/administrativo/gestor/checklist").status_code == 200
    assert _conferir(c, "ENVIOS").status_code == 302


def test_o_balcao_nao_entra(cg_casa):
    c = _entrar(cg_casa, "bruno", "USER")
    assert c.get("/administrativo/gestor/checklist").status_code == 403


def test_a_checklist_esta_no_menu_da_gestao():
    secoes = dict(next(m for m in NAV.MODULOS_DA_BARRA if m["chave"] == "GESTAO")["secoes"])
    itens = secoes["Checklist do dia"]
    assert itens[0]["endpoint"] == "gestor_checklist"
    assert set(itens[0]["papeis"]) == set(CK.QUEM_VE)


# ------------------------------------------------------------ os cartões viram links


def test_os_cartoes_do_painel_geral_levam_a_checklist(cg_casa_logada):
    html = cg_casa_logada["c"].get("/").get_data(as_text=True)
    for codigo, _ in CF.AREAS:
        assert f'href="/administrativo/gestor/checklist?area={codigo}"' in html


def test_o_celular_leva_a_checklist_e_o_retrato_nao(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _rodada_de_hoje(db)
    _achado(db, "T:1", "PRENOTACAO_VENCIDA", "VENCIDO", "RI_QUALIFICACAO",
            titulo=f"Prenotação de {NOME}")
    mario = next(u for u in db.list_users() if u["username"] == "mario")
    PR.definir_titular(db, novo_id=mario["id"], quem=mario)
    html = c.get("/painel").get_data(as_text=True)
    assert 'href="/administrativo/gestor/checklist?area=RI"' in html
    assert NOME not in html.upper()
    retrato = json.dumps(PN.montar(db), ensure_ascii=False)
    assert "checklist" not in retrato and NOME not in retrato.upper()
    assert not re.search(r"/administrativo", retrato)
    PR.conferir_que_e_so_agregado(PN.montar(db))

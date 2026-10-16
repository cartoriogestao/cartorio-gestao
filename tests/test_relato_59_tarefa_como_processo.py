"""O relato #59 — a tarefa como processo.

    «quando atualizar o andamento nas tarefas, inserir botão para informar que o
     responsável deu andamento e informar quem criou ou o substituto para novo
     andamento»
    «permitir um sistema de processamento e trânsito de responsabilidades durante
     a tarefa. A obrigação como processo para ao final chegar na prática do ato.
     Podemos revisar o geral das tarefas e expedientes para todos funcionarem
     como processos.»
    — Mario Exemplo dos Santos, na tela `task_detail`, `/tarefas/85`, 14/09/2026

MEDIDO NA PRODUÇÃO EM 17/09/2026, antes de escrever qualquer linha — 95 tarefas:
**89** `ABERTA`, **5** `CONCLUIDA` e **1** `PENDENTE`. A única `PENDENTE` é a
tarefa **#85** — o próprio relato: concluída em 08/09 com o carimbo gravado, e
com uma palavra que não pertence ao vocabulário do sistema
(`app.TASK_STATUSES`). Ela saía do filtro «Abertas» e não voltava a nenhum.

E três defeitos latentes, nenhum visível no dado:

· o histórico gravaria o **número** da pessoa no lugar do nome —
  `ALTEROU_*USER*` tem **zero** linhas hoje, e a passagem de responsabilidade o
  alcançaria no primeiro uso;
· a linha do tempo saía em jargão — as **7** palavras de ação medidas na
  produção (`ALTEROU_STATUS`, `ESCALONAMENTO_AUTOMATICO`, `NOTA`…);
· o carimbo de conclusão era reescrito a cada edição, porque bastava a situação
  INFORMADA ser `CONCLUIDA`: nas cinco concluídas a última edição foi a própria
  conclusão, e por isso o defeito também não aparece no dado — ele aparece no
  código.

A SEGUNDA METADE DO PEDIDO — o processo — ficou no desenho que o oficial
escolheu em 17/09/2026: **passagem manual, com motivo escrito e rastro**. O
expediente fica declarado como não revisado: ele tem responsável e substituto
gravados e **nenhuma tabela de histórico**, e dar a ele o mesmo trânsito é
revisão de outro módulo.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import tarefa_processo as TP

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa_logada):
    """A casa com o mario (ADMIN) logado, e mais duas pessoas.

    São três porque o relato é sobre PASSAGEM: sem um segundo nome para
    receber, não há o que testar — e a terceira é o destino que não é o
    substituto nem quem criou, que é o que a lista oferece.
    """
    casa = cg_casa_logada
    casa["db"].create_user("gisele", "GISELE SOUZA LIMA", SENHA, "USER")
    casa["db"].create_user("beatriz", "BEATRIZ COSTA", SENHA, "USER")
    return casa


def _con(casa) -> sqlite3.Connection:
    con = sqlite3.connect(str(casa["banco"]))
    con.row_factory = sqlite3.Row
    return con


def _uid(casa, login: str) -> int:
    con = _con(casa)
    try:
        return int(con.execute("SELECT id FROM users WHERE username=?",
                               (login,)).fetchone()["id"])
    finally:
        con.close()


def _tarefa(casa, criada_por: int | None = None, **campos) -> int:
    """Uma tarefa pela porta de verdade (`create_task`), com quem a criou."""
    dados = {"title": "Enviar declaração", "sector": "Malote",
             "evidence_required": 0}
    dados.update(campos)
    return casa["db"].create_task(dados, criada_por)


def _linha(casa, task_id: int) -> sqlite3.Row:
    con = _con(casa)
    try:
        return con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        con.close()


def _historico(casa, task_id: int, acao: str | None = None) -> list[sqlite3.Row]:
    con = _con(casa)
    try:
        if acao:
            return con.execute(
                "SELECT * FROM task_history WHERE task_id=? AND action=? ORDER BY id",
                (task_id, acao)).fetchall()
        return con.execute(
            "SELECT * FROM task_history WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()
    finally:
        con.close()


# ============================================================ reabrir a tarefa
#
# A palavra `PENDENTE` não existe neste sistema, e usá-la prendia a tarefa fora
# de todos os filtros — com o carimbo de conclusão ainda dentro dela.


def test_reabrir_devolve_a_tarefa_ao_filtro_das_abertas(casa):
    uid = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=uid, assigned_user_id=uid)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, uid)   # carimba
    assert _linha(casa, tid)["completed_at"] is not None

    con = _con(casa)
    try:
        with con:
            volta = TP.reabrir(con, tid, "O documento voltou com erro de digitação.",
                               uid, casa["db"].now())
    finally:
        con.close()

    assert volta["status"] == "ABERTA"
    linha = _linha(casa, tid)
    assert linha["status"] == "ABERTA"
    assert linha["completed_at"] is None and linha["completed_by"] is None, (
        "o carimbo afirma o dia em que o serviço terminou, e o serviço voltou a "
        "andar")
    abertas = {r["id"] for r in casa["db"].list_tasks(
        TP.VISTA_ABERTAS, None, usuario_id=uid)}
    assert tid in abertas, (
        "a tarefa reaberta tem de voltar à lista — era isto que `PENDENTE` "
        "impedia")


def test_a_reabertura_fica_na_linha_do_tempo_com_quem_e_por_que(casa):
    uid = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=uid)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, uid)
    con = _con(casa)
    try:
        with con:
            TP.reabrir(con, tid, "Concluí por engano — falta a procuração.",
                       uid, casa["db"].now())
    finally:
        con.close()
    historico = _historico(casa, tid, "REABERTA")
    assert len(historico) == 1
    assert historico[0]["note"] == "Concluí por engano — falta a procuração."
    assert historico[0]["user_id"] == uid
    assert historico[0]["old_value"] == "CONCLUIDA"
    assert historico[0]["new_value"] == "ABERTA"


@pytest.mark.parametrize("motivo", ["", "   ", "ok", "erro"])
def test_reabrir_sem_motivo_de_verdade_e_recusado(casa, motivo):
    """O piso de dez letras é o mesmo da recusa de certidão e da linha do
    problema resolvido (relato #82): «ok» não responde à pergunta que a
    correição faz — e a pergunta aqui é por que a tarefa voltou."""
    uid = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=uid)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, uid)
    con = _con(casa)
    try:
        with pytest.raises(TP.ProcessoError) as erro, con:
            TP.reabrir(con, tid, motivo, uid, casa["db"].now())
    finally:
        con.close()
    assert "motivo" in str(erro.value).lower()
    assert _linha(casa, tid)["status"] == "CONCLUIDA", (
        "a recusa não pode deixar a tarefa no meio do caminho")


def test_reabrir_o_que_esta_andando_e_recusado(casa):
    uid = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=uid)
    con = _con(casa)
    try:
        with pytest.raises(TP.ProcessoError) as erro, con:
            TP.reabrir(con, tid, "Quero reabrir uma tarefa que está aberta.",
                       uid, casa["db"].now())
    finally:
        con.close()
    assert "concluída" in str(erro.value)


# ==================================================== passar de mão em mão
#
# «um sistema de processamento e trânsito de responsabilidades durante a tarefa»


def test_passar_nao_muda_a_situacao_e_grava_nomes_e_nao_numeros(casa):
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    con = _con(casa)
    try:
        with con:
            r = TP.passar_para(con, tid, gisele,
                               "Ela responde pelo malote nesta semana.",
                               mario, casa["db"].now())
    finally:
        con.close()
    assert r["de"] == "MARIO EXEMPLO DOS SANTOS"
    assert r["para"] == "GISELE SOUZA LIMA"
    linha = _linha(casa, tid)
    assert linha["assigned_user_id"] == gisele
    assert linha["status"] == "ABERTA", (
        "passar a tarefa não é começar a fazê-la — quem recebe decide se "
        "começa, aguarda ou conclui")
    h = _historico(casa, tid, "PASSAGEM")[0]
    assert h["old_value"] == "MARIO EXEMPLO DOS SANTOS"
    assert h["new_value"] == "GISELE SOUZA LIMA", (
        "a ficha perguntava «passou para 5», e número não responde a quem lê "
        "meses depois")
    assert h["note"] == "Ela responde pelo malote nesta semana."


def test_o_substituto_nao_se_move_junto_com_o_responsavel(casa):
    """Ele é o segundo de quem responde — trocar os dois deixaria a tarefa sem
    ninguém atrás, e é o substituto que o escalonamento automático avisa."""
    mario, gisele, lei = (_uid(casa, "mario"), _uid(casa, "gisele"),
                        _uid(casa, "beatriz"))
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario,
                  backup_user_id=gisele)
    con = _con(casa)
    try:
        with con:
            TP.passar_para(con, tid, lei, "Eu entro de férias amanhã.",
                           mario, casa["db"].now())
    finally:
        con.close()
    linha = _linha(casa, tid)
    assert linha["assigned_user_id"] == lei
    assert linha["backup_user_id"] == gisele


def test_passar_para_tarefa_concluida_e_recusado(casa):
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, mario)
    con = _con(casa)
    try:
        with pytest.raises(TP.ProcessoError) as erro, con:
            TP.passar_para(con, tid, gisele, "Passando o que já terminou.",
                           mario, casa["db"].now())
    finally:
        con.close()
    assert "reabra" in str(erro.value).lower(), (
        "a recusa tem de dizer onde se resolve, e não só que não dá")


def test_passar_para_quem_esta_desligado_e_recusado(casa):
    """Entregar ao vazio: a tarefa sai da mão de quem responde e não entra na de
    ninguém."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    con = _con(casa)
    try:
        with con:
            con.execute("UPDATE users SET active=0 WHERE id=?", (gisele,))
        with pytest.raises(TP.ProcessoError) as erro, con:
            TP.passar_para(con, tid, gisele, "Passando para quem saiu ontem.",
                           mario, casa["db"].now())
    finally:
        con.close()
    assert "não está ativo" in str(erro.value)
    assert _linha(casa, tid)["assigned_user_id"] == mario


def test_passar_para_o_mesmo_responsavel_e_recusado(casa):
    mario = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    con = _con(casa)
    try:
        with pytest.raises(TP.ProcessoError) as erro, con:
            TP.passar_para(con, tid, mario, "Passando para mim mesmo agora.",
                           mario, casa["db"].now())
    finally:
        con.close()
    assert "já está com" in str(erro.value)


def test_tarefa_sem_responsavel_diz_o_que_fazer(casa):
    """Medido: **79 das 95** tarefas da produção não têm responsável. A recusa
    aponta o formulário em vez de mandar pedir ao ADMIN."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario)
    con = _con(casa)
    try:
        with pytest.raises(TP.ProcessoError) as erro, con:
            TP.passar_para(con, tid, gisele, "Passando tarefa sem dono aqui.",
                           mario, casa["db"].now())
    finally:
        con.close()
    assert "responsável" in str(erro.value)


# ===================================================== as vistas da lista


def test_as_vistas_do_relato_59(casa):
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    minha = _tarefa(casa, title="Minha", criada_por=mario, assigned_user_id=mario)
    passada = _tarefa(casa, title="Passada", criada_por=mario,
                      assigned_user_id=mario)
    con = _con(casa)
    try:
        with con:
            TP.passar_para(con, passada, gisele, "Ficou com ela esta semana.",
                           mario, casa["db"].now())
    finally:
        con.close()

    def ids(vista):
        return {r["id"] for r in casa["db"].list_tasks(vista, None,
                                                       usuario_id=mario)}

    assert minha in ids(TP.VISTA_COMIGO)
    assert passada not in ids(TP.VISTA_COMIGO)
    assert passada in ids(TP.VISTA_PASSOU_POR_MIM), (
        "«o que passou por mim» é a outra metade da pergunta de quem trabalha "
        "no balcão")
    assert minha not in ids(TP.VISTA_PASSOU_POR_MIM)
    assert {minha, passada} <= ids(TP.VISTA_ABERTAS)


def test_o_que_terminou_sai_da_lista_do_que_passou(casa):
    """O que foi concluído não pede acompanhamento — e continuar ali faria a
    lista crescer para sempre."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    con = _con(casa)
    try:
        with con:
            TP.passar_para(con, tid, gisele, "Ficou com ela esta semana.",
                           mario, casa["db"].now())
    finally:
        con.close()
    assert tid in {r["id"] for r in casa["db"].list_tasks(
        TP.VISTA_PASSOU_POR_MIM, None, usuario_id=mario)}
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, gisele)
    assert tid not in {r["id"] for r in casa["db"].list_tasks(
        TP.VISTA_PASSOU_POR_MIM, None, usuario_id=mario)}


def test_a_vista_sem_saber_de_quem_e_a_lista_e_recusada(casa):
    """Zero por engano é o defeito que a casa mais paga: uma lista vazia se
    leria como «você não tem nada»."""
    with pytest.raises(TP.ProcessoError):
        TP.filtro_da_vista(TP.VISTA_COMIGO, None)


def test_a_contagem_e_a_mesma_lista(casa):
    """Contagem que não acompanha o próprio filtro é o carimbo que mente sobre
    ele — e aqui o setor entra junto, porque a lista tem dois filtros."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    _tarefa(casa, title="Minha", criada_por=mario, assigned_user_id=mario)
    passada = _tarefa(casa, title="Passada", criada_por=mario,
                      assigned_user_id=mario, sector="Protocolo")
    con = _con(casa)
    try:
        with con:
            TP.passar_para(con, passada, gisele, "Ficou com ela esta semana.",
                           mario, casa["db"].now())
        for setor in (None, "Malote", "Protocolo"):
            contagem = TP.contagem_por_vista(con, mario, setor)
            for vista, n in contagem.items():
                lista = casa["db"].list_tasks(vista, setor, usuario_id=mario)
                assert n == len(lista), (
                    f"«{vista}» com o setor {setor!r}: o botão diz {n} e a "
                    f"lista tem {len(lista)}")
    finally:
        con.close()


# ============================================== a linha do tempo em português


def test_as_acoes_que_o_sistema_grava_tem_frase():
    """Medido na produção em 17/09/2026: sete palavras de ação, todas em
    jargão na tela. A lista é declarada — e a propriedade que protege de
    verdade é a do teste seguinte."""
    producao = ("CRIADA", "NOTA", "PASSAGEM", "REABERTA", "PRAZO_CALCULADO",
                "ATRIBUICAO_EM_LOTE", "ESCALONAMENTO_AUTOMATICO")
    faltam = [a for a in producao if a not in TP.ACOES]
    assert not faltam, f"estas ações sairiam cruas na linha do tempo: {faltam}"


def test_a_linha_do_tempo_nunca_mostra_a_palavra_crua():
    for acao in [*TP.ACOES, "ALTEROU_STATUS", "ALTEROU_EVIDENCE_REQUIRED"]:
        assert TP.rotulo_da_acao(acao) != acao
    # Ação desconhecida NÃO some: volta como está. Melhor uma palavra técnica
    # na tela do que um fato escondido por falta de rótulo.
    assert TP.rotulo_da_acao("QUALQUER_COISA") == "QUALQUER_COISA"
    assert TP.rotulo_da_acao(None) == "—"
    assert TP.rotulo_da_acao("ALTEROU_COISA_NOVA") == "Mudou coisa nova"


def test_toda_coluna_editavel_tem_rotulo():
    """Coluna nova no formulário não escapa para a linha do tempo.

    A lista de colunas é MEDIDA do `database.update_task`, e não escrita à mão:
    escrita à mão, ela envelheceria na tarde em que a tela ganhasse um campo, e
    a linha do tempo voltaria a mostrar a palavra do sistema.
    """
    fonte = (RAIZ / "database.py").read_text(encoding="utf-8")
    achado = re.search(r"allowed = \{([^}]*)\}", fonte, re.DOTALL)
    assert achado, "não achei a lista das colunas editáveis da tarefa"
    colunas = {nome.upper() for nome in re.findall(r'"(\w+)"', achado.group(1))}
    assert len(colunas) > 8, "a lista das colunas editáveis encolheu demais"
    faltam = sorted(colunas - set(TP.COLUNAS))
    assert not faltam, (
        "estas colunas da tarefa são editáveis e não têm rótulo em português "
        f"para a linha do tempo: {faltam}")


def test_o_historico_grava_nome_quando_o_campo_e_pessoa(casa):
    """Zero linhas assim na produção — o defeito era latente, e a passagem de
    responsabilidade o alcançaria no primeiro uso."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    casa["db"].update_task(tid, {"assigned_user_id": gisele}, mario)
    h = _historico(casa, tid, "ALTEROU_ASSIGNED_USER_ID")[0]
    assert h["old_value"] == "MARIO EXEMPLO DOS SANTOS"
    assert h["new_value"] == "GISELE SOUZA LIMA"


def test_editar_a_tarefa_concluida_nao_move_o_carimbo(casa):
    """O carimbo afirma o dia em que o serviço terminou. Quem corrige uma
    vírgula no título de uma tarefa concluída em março não pode ver a ficha
    dizer que o serviço terminou no dia da correção."""
    mario = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=mario)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, mario)
    carimbo = _linha(casa, tid)["completed_at"]
    assert carimbo
    casa["db"].update_task(tid, {"title": "Enviar a declaração anual"}, mario)
    linha = _linha(casa, tid)
    assert linha["completed_at"] == carimbo
    assert linha["completed_by"] == mario


def test_mudar_a_situacao_para_fora_da_conclusao_apaga_o_carimbo(casa):
    """O outro lado: `PENDENTE` na #85 guardava o carimbo de uma conclusão que
    a tarefa já não tinha."""
    mario = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=mario)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, mario)
    casa["db"].update_task(tid, {"status": "EM_ANDAMENTO"}, mario)
    linha = _linha(casa, tid)
    assert linha["completed_at"] is None and linha["completed_by"] is None


def test_a_escalada_automatica_avisa_o_substituto_pelo_nome(casa):
    """As **13** linhas da produção dizem «Responsável substituto **#2** deve
    acompanhar» — número em prosa que fala com gente."""
    gisele = _uid(casa, "gisele")
    tid = _tarefa(casa, backup_user_id=gisele, due_date="2020-01-01",
                  assigned_user_id=gisele)
    casa["db"].ensure_overdue_escalations()
    h = _historico(casa, tid, "ESCALONAMENTO_AUTOMATICO")
    assert h, "a tarefa vencida não gerou escalonamento"
    assert "GISELE SOUZA LIMA" in h[0]["note"]
    assert f"#{gisele}" not in h[0]["note"]


# ======================================================= as telas


def test_a_tela_da_tarefa_mostra_o_historico_em_portugues(casa):
    mario = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    casa["db"].update_task(tid, {"status": "EM_ANDAMENTO"}, mario)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Tarefa criada" in html
    assert "Mudou a situação" in html
    assert "ALTEROU_STATUS" not in html


def test_reabrir_pela_tela_exige_o_motivo(casa):
    mario = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=mario)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, mario)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    r = casa["cliente"].post(f"/tarefas/{tid}",
                             data={"action": "reabrir", "motivo": "",
                                   "csrf_token": _token(html)},
                             follow_redirects=True)
    assert "motivo" in r.get_data(as_text=True).lower()
    assert _linha(casa, tid)["status"] == "CONCLUIDA"


def test_reabrir_pela_tela_apaga_o_carimbo_e_volta_para_a_lista(casa):
    mario = _uid(casa, "mario")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, mario)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={"action": "reabrir",
              "motivo": "O documento voltou com erro de digitação.",
              "csrf_token": _token(html)},
        follow_redirects=True)
    linha = _linha(casa, tid)
    assert linha["status"] == "ABERTA" and linha["completed_at"] is None
    lista = casa["cliente"].get("/tarefas?status=COMIGO").get_data(as_text=True)
    assert "Enviar declaração" in lista


def test_passar_pela_tela(casa):
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/tarefas/{tid}",
        data={"action": "passar", "para_user_id": str(gisele),
              "motivo": "Ela responde pelo malote nesta semana.",
              "csrf_token": _token(html)},
        follow_redirects=True)
    assert _linha(casa, tid)["assigned_user_id"] == gisele
    texto = r.get_data(as_text=True)
    assert "Passou para outro responsável" in texto
    assert "Ela responde pelo malote nesta semana." in texto


def test_as_tres_portas_da_passagem_estao_na_tela(casa):
    """A lista, o substituto e quem criou — as três escrevem o motivo."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario,
                  backup_user_id=gisele)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Passar para outro responsável" in html
    assert "Para o substituto (GISELE SOUZA LIMA)" in html
    assert "Devolver a quem criou (MARIO EXEMPLO DOS SANTOS)" in html


def test_devolver_a_quem_criou_e_a_mesma_porta(casa):
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=gisele)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={"action": "devolver", "motivo": "Voltou para quem abriu o pedido.",
              "csrf_token": _token(html)},
        follow_redirects=True)
    assert _linha(casa, tid)["assigned_user_id"] == mario


def test_tarefa_concluida_nao_oferece_passagem(casa):
    """Não há serviço para passar adiante."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa, criada_por=mario, assigned_user_id=mario,
                  backup_user_id=gisele)
    casa["db"].update_task(tid, {"status": "CONCLUIDA"}, mario)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Passar para outro responsável" not in html


def test_a_lista_de_tarefas_tem_as_vistas_no_alto(casa):
    html = casa["cliente"].get("/tarefas").get_data(as_text=True)
    assert "Comigo (" in html
    assert "Passou por mim (" in html
    assert TP.AJUDA_DA_VISTA[TP.VISTA_ABERTAS] in html
    comigo = casa["cliente"].get("/tarefas?status=COMIGO").get_data(as_text=True)
    assert TP.AJUDA_DA_VISTA[TP.VISTA_COMIGO] in comigo, (
        "vista que não se explica sozinha faz a pessoa procurar o que não está "
        "ali")


def test_o_numero_ao_lado_do_botao_e_o_da_lista(casa):
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    _tarefa(casa, title="Minha", criada_por=mario, assigned_user_id=mario)
    passada = _tarefa(casa, title="Passada", criada_por=mario,
                      assigned_user_id=mario)
    con = _con(casa)
    try:
        with con:
            TP.passar_para(con, passada, gisele, "Ficou com ela esta semana.",
                           mario, casa["db"].now())
        contagem = TP.contagem_por_vista(con, mario)
    finally:
        con.close()
    html = casa["cliente"].get("/tarefas").get_data(as_text=True)
    assert f"Comigo ({contagem[TP.VISTA_COMIGO]})" in html
    assert f"Passou por mim ({contagem[TP.VISTA_PASSOU_POR_MIM]})" in html


def test_a_lista_mostra_o_que_esta_comigo(casa):
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    _tarefa(casa, title="Enviar a declaração do IBGE", criada_por=mario,
            assigned_user_id=mario)
    _tarefa(casa, title="Conferir o malote de ontem", criada_por=mario,
            assigned_user_id=gisele)
    html = casa["cliente"].get("/tarefas?status=COMIGO").get_data(as_text=True)
    assert "Enviar a declaração do IBGE" in html
    assert "Conferir o malote de ontem" not in html


def test_a_vista_sobrevive_ao_filtro_de_setor(casa):
    """As três vistas também estão no `<select>`: quem escolhe um setor e clica
    «Filtrar» perderia a vista se ela só existisse nos botões de cima."""
    html = casa["cliente"].get("/tarefas?status=COMIGO&sector=Malote"
                               ).get_data(as_text=True)
    assert 'value="COMIGO" selected' in html
    assert "Comigo (" in html


# ================================================== o vocabulário, e a palavra
#
# A LISTA DAS SITUAÇÕES MORA NO MÓDULO, e `app.TASK_STATUSES` é apelido dela.
# Ela estava escrita em `app.py`, e de lá era inalcançável sem carregar o Flask
# inteiro: quem precisa dela fora da tela — o script que conserta a palavra
# torta no banco da produção — teria de reescrevê-la à mão, que é como duas
# listas divergem. As duas têm de ser a mesma coisa, e é isto que o guarda exige.


def test_o_vocabulario_das_situacoes_mora_num_lugar_so(casa):
    import app as APP

    assert APP.TASK_STATUSES == list(TP.SITUACOES), (
        "as duas listas divergiram: a tela ofereceria uma situação que o módulo "
        "não conhece, ou o contrário")
    assert len(set(TP.SITUACOES)) == len(TP.SITUACOES)


def test_reabrir_devolve_palavra_conhecida_e_sem_carimbo():
    """A palavra da reabertura tem de estar no vocabulário — foi a que faltou —
    e não pode ser uma das que carimbam, senão o carimbo voltaria pela porta."""
    assert TP.STATUS_DE_REABERTURA in TP.SITUACOES
    assert not TP.carimba_o_status(TP.STATUS_DE_REABERTURA)
    assert [s for s in TP.SITUACOES if TP.carimba_o_status(s)] == ["CONCLUIDA"]


def test_nenhuma_acao_do_modulo_sai_em_jargao(casa):
    """`rotulo_da_acao` devolve a própria palavra quando não a conhece — é por
    ali que `PASSAGEM` chegaria à ficha, e é o que o relato reclamou."""
    for acao in ("PASSAGEM", "REABERTA", "NORMALIZADA"):
        assert acao in TP.ACOES, f"{acao} ficaria em jargão na linha do tempo"
        assert TP.rotulo_da_acao(acao) != acao


def _script_da_palavra_torta():
    """O `tools/normalizar_situacao_das_tarefas.py`, carregado sem executar."""
    import importlib.util

    caminho = RAIZ / "tools" / "normalizar_situacao_das_tarefas.py"
    assert caminho.exists(), (
        "o script que tira a #85 do limbo não está onde a nota diz que está")
    spec = importlib.util.spec_from_file_location("_norm_tarefas", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_o_script_da_palavra_torta_so_conhece_palavra_fora_do_vocabulario():
    """O mapa dele é a única coisa que ele converte. Palavra que o mapa não
    conhece não é adivinhada — adivinhar mostraria serviço andando que talvez
    esteja concluído, ou esconderia o que está em andamento."""
    script = _script_da_palavra_torta()

    assert set(script.SINONIMOS.values()) <= set(TP.SITUACOES), (
        "o script converte para palavra que o sistema não conhece")
    assert not (set(script.SINONIMOS) & set(TP.SITUACOES)), (
        "palavra que já está no vocabulário não precisa de sinônimo")
    assert script.SINONIMOS["PENDENTE"] == TP.STATUS_DE_REABERTURA


def _tarefa_pendente(casa, criada_por: int) -> int:
    """A #85 como ela está na produção: palavra fora do vocabulário **e** o
    carimbo de conclusão dentro. Feita por INSERT direto de propósito — o
    `update_task` recusaria, e é essa a diferença entre o banco e a tela."""
    tid = _tarefa(casa, criada_por=criada_por, assigned_user_id=criada_por)
    con = _con(casa)
    try:
        with con:
            con.execute(
                "UPDATE tasks SET status='PENDENTE', completed_at=?, "
                "completed_by=? WHERE id=?",
                (casa["db"].now(), criada_por, tid))
            con.execute(
                "INSERT INTO task_history(task_id,ts,user_id,action,old_value,"
                "new_value,note) VALUES (?,?,?,?,?,?,?)",
                (tid, casa["db"].now(), criada_por, "ALTEROU_STATUS",
                 "CONCLUIDA", "PENDENTE", "reaberta como pendente"))
    finally:
        con.close()
    return tid


def test_o_script_da_palavra_torta_nao_escreve_sem_confirmacao(casa, monkeypatch):
    script = _script_da_palavra_torta()
    mario = _uid(casa, "mario")
    tid = _tarefa_pendente(casa, mario)
    monkeypatch.setattr(script, "BANCO", Path(casa["banco"]))
    monkeypatch.setattr(sys, "argv", ["normalizar_situacao_das_tarefas.py"])

    assert script.main() == 0

    linha = _linha(casa, tid)
    assert linha["status"] == "PENDENTE", "o script escreveu sem --confirmar"
    assert linha["completed_at"] is not None, (
        "o carimbo saiu sem --confirmar")


def test_o_script_da_palavra_torta_tira_a_tarefa_do_limbo(casa, monkeypatch, tmp_path):
    """A prova do conserto da #85, contra um banco de verdade: a palavra volta ao
    vocabulário, o carimbo de uma conclusão que a tarefa já não tem sai, e as
    duas coisas ficam registradas — na linha do tempo e na auditoria."""
    script = _script_da_palavra_torta()
    mario = _uid(casa, "mario")
    tid = _tarefa_pendente(casa, mario)
    monkeypatch.setattr(script, "BANCO", Path(casa["banco"]))
    monkeypatch.setattr(script, "PASTA_DAS_COPIAS", tmp_path)
    monkeypatch.setattr(sys, "argv",
                        ["normalizar_situacao_das_tarefas.py", "--confirmar"])

    assert script.main() == 0

    linha = _linha(casa, tid)
    assert linha["status"] == TP.STATUS_DE_REABERTURA
    assert linha["completed_at"] is None and linha["completed_by"] is None

    h = _historico(casa, tid, "NORMALIZADA")
    assert len(h) == 1, "a mudança não ficou na linha do tempo da tarefa"
    assert h[0]["old_value"] == "PENDENTE" and h[0]["new_value"] == "ABERTA"
    assert "vocabulário" in h[0]["note"]
    assert h[0]["user_id"] is None, (
        "quem fez isto não foi gente no sistema — o nome do script vai na nota")

    con = _con(casa)
    try:
        aud = con.execute(
            "SELECT * FROM audit_logs WHERE entity_id=? AND entity_type='tasks'",
            (tid,)).fetchall()
    finally:
        con.close()
    assert aud, "a escrita por fora da rota não deixou rastro de auditoria"
    assert any("normalizar" in (a["details"] or "") for a in aud)

    # A CÓPIA MUDOU DE LUGAR EM 11/10/2026, por ordem do oficial: ela não nasce
    # mais ao lado do banco (foi assim que o banco se perdeu numa limpeza), e
    # sim em `copias/antes_de_mexer/` — ver `pasta_das_copias`. O que este
    # teste cobra continua o mesmo: que a cópia sai antes de mexer.
    pasta = Path(casa["banco"]).parent / "copias" / "antes_de_mexer"
    assert list(pasta.glob("*.sqlite3")), "não tirou cópia do banco antes"
    assert not list(Path(casa["banco"]).parent.glob("*antes_da_situacao*.sqlite3")), \
        "a cópia voltou a nascer ao lado do banco"


def test_a_tarefa_fora_do_vocabulario_nao_some_da_lista(casa):
    """Ela sai do filtro «Abertas» se a lista olhar só as situações conhecidas —
    e a vista «Todas» é a que ainda a mostra, com a palavra como ela é. É a
    mesma regra do problema #77: palavra desconhecida não é chutada em vista
    nenhuma, e também não se esconde."""
    mario = _uid(casa, "mario")
    tid = _tarefa_pendente(casa, mario)

    abertas = casa["cliente"].get("/tarefas").get_data(as_text=True)
    assert "Enviar declaração" not in abertas, (
        "a palavra fora do vocabulário entrou na vista dos abertos: o sistema "
        "não sabe se ela está concluída ou esperando")
    # O NÚMERO DELA PRECISA APARECER. Sair de todas as vistas sem dizer que
    # saiu deixaria a linha invisível — que é o defeito que a #77 consertou na
    # lista de problemas.
    assert "fora das vistas" in abertas, (
        "a tarefa saiu das vistas e a tela não disse que há uma fora delas")

    todas = casa["cliente"].get("/tarefas?status=").get_data(as_text=True)
    assert "Enviar declaração" in todas, (
        "a vista «Todas» deixou de mostrar a tarefa: a palavra desapareceu do "
        "sistema em vez de sair da vista")
    assert "PENDENTE" in todas, "a palavra não saiu como ela é"
    assert "palavra fora do vocabulário" in todas, (
        "a palavra saiu sem o aviso: quem lê «PENDENTE» não sabe o que fazer")

    con = _con(casa)
    try:
        fora = con.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='PENDENTE'").fetchone()[0]
    finally:
        con.close()
    assert fora == 1, f"a tarefa {tid} saiu do banco em vez de sair da vista"


def test_a_contagem_das_vistas_nao_conta_a_palavra_desconhecida(casa):
    """Contagem que não acompanha o próprio filtro é o carimbo que mente sobre
    ele: o botão diria que há trabalho na vista que a lista não mostra."""
    mario = _uid(casa, "mario")
    _tarefa_pendente(casa, mario)  # fora do vocabulário, e com o carimbo dentro
    _tarefa(casa, criada_por=mario, assigned_user_id=mario)

    con = _con(casa)
    try:
        contagem = TP.contagem_por_vista(con, mario)
        fora = TP.tarefas_fora_do_vocabulario(con)
    finally:
        con.close()

    assert contagem[TP.VISTA_ABERTAS] == 1, (
        "a palavra desconhecida foi contada como serviço em aberto")
    assert contagem[TP.VISTA_COMIGO] == 1
    assert fora == 1, "o número do que ficou fora das vistas não foi medido"


def test_o_painel_conta_pela_mesma_regua_da_lista(casa):
    """O painel contava «Tarefas abertas» com o filtro negativo
    (`NOT IN ('CONCLUIDA','CANCELADA')`), e a palavra que o sistema não conhece
    entrava na conta: a primeira tela da casa dizia haver serviço de hoje onde
    havia uma linha que ninguém sabe ler. Duas telas discordando sobre a mesma
    palavra é o carimbo que mente — a contagem e a lista usam a MESMA régua."""
    condicao, params = TP.condicao_aberta("t.status")
    filtros, params_da_vista = TP.filtro_da_vista(TP.VISTA_ABERTAS, None)

    assert filtros == [condicao], (
        "a contagem e a lista montaram o filtro cada uma por si — é assim que "
        "elas divergem no primeiro conserto")
    assert params_da_vista == params


def test_o_painel_nao_infla_o_numero_e_declara_o_que_ficou_fora(casa):
    """A prova na tela: com uma tarefa de palavra desconhecida e uma de verdade,
    o painel conta **uma aberta** — e diz que existe outra fora das vistas. O
    número menor sem essa frase seria a mentira do outro lado: quem lê conclui
    que não há nada ali."""
    mario = _uid(casa, "mario")
    _tarefa_pendente(casa, mario)
    _tarefa(casa, criada_por=mario, assigned_user_id=mario)

    stats = casa["db"].dashboard_stats()
    assert stats["open_tasks"] == 1, "a palavra desconhecida inflou o painel"
    assert stats["overdue"] == 0, (
        "a tarefa sem situação conhecida entrou na conta das vencidas")
    assert stats["tarefas_fora_do_vocabulario"] == 1, (
        "a tarefa saiu da conta e o painel não disse que ela existe")

    html = casa["cliente"].get("/").get_data(as_text=True)
    assert "Fora das vistas" in html, (
        "o painel escondeu a tarefa: o número de cima ficou menor sem dizer "
        "por quê")
    assert "não é nenhuma das que o sistema conhece" in html, (
        "a marca saiu sem explicar o que ela quer dizer")

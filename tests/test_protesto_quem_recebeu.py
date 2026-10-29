"""QUEM RECEBEU O AVISO — decisões do oficial de 29/10/2026.

«canhoto de entrega precisa ter o campo pra botar o nome de quem recebeu. se
faltar, avisar escrevente pra completar».

O QUE ESTES TESTES GUARDAM
      - o canhoto impresso tem as linhas «Nome de quem recebeu», «Documento»,
        «Data» e «Assinatura» — e continua com três linhas, para caber no pé
        da folha do aviso;
      - a entrega registrada sem o nome (só por afirmação expressa) abre, NA
        HORA, uma tarefa para quem a registrou, no setor do Protesto — painel
        e tarefa, sem e-mail;
      - o nome se completa depois, na tela dos avisos (ou na ficha), lido do
        canhoto anexado; a auditoria diz quem completou e quando, e a tarefa
        fecha sozinha;
      - o nome que já existe não se sobrescreve: corrigir exige afirmação;
      - completado o nome, o protesto passa sem afirmação.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_protesto_aviso_web import (_con, _token, aviso_id, emitir,  # noqa: E402,F401
                                     registrar, s, titulo_apontado)

AFIRMACAO = ("o canhoto voltou assinado, mas o nome está ilegível e será "
             "conferido com o entregador amanhã")


def _completar(s, aid: int, **campos):
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    return s["c"].post(f"/protesto/avisos/{aid}/recebido-por",
                       data={"csrf_token": _token(tela), **campos},
                       follow_redirects=True).get_data(as_text=True)


def _entregue_sem_nome(s) -> tuple[int, int]:
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    html = registrar(s, aid, entregue="1", recebido_por="", afirmo="1",
                     afirmacao=AFIRMACAO).get_data(as_text=True)
    assert "FALTA O NOME DE QUEM RECEBEU" in html
    return tid, aid


def _tarefas(s, aid: int) -> list:
    con = _con(s)
    linhas = con.execute(
        "SELECT * FROM tasks WHERE source_type='PT_AVISO_SEM_RECEBEDOR' "
        "AND source_ref=? ORDER BY id", (f"pt_avisos:{aid}",)).fetchall()
    con.close()
    return linhas


def test_o_canhoto_impresso_tem_as_quatro_linhas_e_continua_com_tres():
    import modelos_da_casa as MOD
    campos = MOD.padrao_de("PT_AVISO_CANHOTO_CAMPOS").split("\n")
    assert len(campos) == 3
    texto = "\n".join(campos)
    for rotulo in ("Nome de quem recebeu:", "Documento:", "Data:", "Assinatura:"):
        assert rotulo in texto, rotulo
    assert campos[0].startswith("Nome de quem recebeu:")


def test_a_entrega_sem_nome_abre_a_tarefa_na_hora_para_quem_registrou(s):
    tid, aid = _entregue_sem_nome(s)
    [tarefa] = _tarefas(s, aid)
    assert tarefa["status"] == "ABERTA"
    assert tarefa["sector"] == "PROTESTO"
    assert tarefa["assigned_user_id"]                  # quem registrou
    assert "Completar quem recebeu" in tarefa["title"]
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "falta o nome de quem recebeu" in tela
    assert f"/protesto/avisos/{aid}/recebido-por" in tela
    # a ficha do título também oferece completar
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert f"/protesto/avisos/{aid}/recebido-por" in ficha


def test_completar_grava_a_auditoria_fecha_a_tarefa_e_libera_o_protesto(s):
    import protesto_prova as PROVA
    tid, aid = _entregue_sem_nome(s)
    con = _con(s)
    assert PROVA.conferir(con, tid, hoje="2026-10-29")["falta_quem_recebeu"]
    [linha] = [x for x in PROVA.intimacoes_sem_prova(con, hoje="2026-10-29")
               if x["titulo_id"] == tid]
    con.close()
    assert "falta o nome de quem recebeu" in linha["explicacao"]
    assert "complete em" in linha["explicacao"]
    assert linha["link"] == f"/protesto/avisos#aviso-{aid}"

    html = _completar(s, aid, recebido_por="MARIA EXEMPLO")
    assert "Nome completado" in html
    con = _con(s)
    assert con.execute("SELECT recebido_por FROM pt_avisos WHERE id=?",
                       (aid,)).fetchone()[0] == "MARIA EXEMPLO"
    auditoria = con.execute(
        "SELECT * FROM audit_logs WHERE action='PROTESTO_AVISO_RECEBIDO_POR'"
    ).fetchall()
    assert len(auditoria) == 1 and auditoria[0]["user_id"]
    assert json.loads(auditoria[0]["details"])["recebido_por"] == "MARIA EXEMPLO"
    prova = PROVA.conferir(con, tid, hoje="2026-10-29")
    con.close()
    assert prova["completa"], prova                # o protesto passa sem afirmação
    assert [t["status"] for t in _tarefas(s, aid)] == ["CONCLUIDA"]


def test_o_nome_que_existe_so_se_corrige_com_afirmacao(s):
    _, aid = _entregue_sem_nome(s)
    _completar(s, aid, recebido_por="MARIA EXEMPLO")
    html = _completar(s, aid, recebido_por="JOSÉ EXEMPLO")
    assert "exige afirmação expressa" in html
    con = _con(s)
    assert con.execute("SELECT recebido_por FROM pt_avisos WHERE id=?",
                       (aid,)).fetchone()[0] == "MARIA EXEMPLO"
    con.close()
    html = _completar(s, aid, recebido_por="JOSÉ EXEMPLO", afirmo="1",
                      afirmacao=AFIRMACAO)
    assert "Nome corrigido" in html
    con = _con(s)
    assert con.execute("SELECT recebido_por FROM pt_avisos WHERE id=?",
                       (aid,)).fetchone()[0] == "JOSÉ EXEMPLO"
    regras = [json.loads(x["details"])["regra"] for x in con.execute(
        "SELECT details FROM audit_logs WHERE action='AFIRMACAO_EXPRESSA' "
        "ORDER BY id").fetchall()]
    con.close()
    # a primeira é a da entrega sem o nome; a última, a da correção
    assert regras[-1] == "CORRECAO_DE_QUEM_RECEBEU"
    assert regras.count("CORRECAO_DE_QUEM_RECEBEU") == 1


def test_sem_o_comprovante_o_nome_nao_se_completa(s):
    """O nome se lê no canhoto anexado — sem ele, nada a completar de
    memória. (Entrega sem arquivo e sem nome, por afirmação.)"""
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="1", recebido_por="", sem_comprovante=True,
              afirmo="1", afirmacao=AFIRMACAO)
    html = _completar(s, aid, recebido_por="MARIA EXEMPLO")
    assert "Anexe primeiro o canhoto assinado" in html
    con = _con(s)
    assert not con.execute("SELECT recebido_por FROM pt_avisos WHERE id=?",
                           (aid,)).fetchone()[0]
    con.close()


def test_a_entrega_com_nome_nao_abre_tarefa(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="1", recebido_por="MARIA EXEMPLO")
    assert _tarefas(s, aid) == []

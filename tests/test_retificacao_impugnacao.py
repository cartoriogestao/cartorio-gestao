"""O caminho da impugnação na retificação — art. 600 do Código de Normas (RI021).

O QUE ESTES TESTES GUARDAM
    - a rejeição de plano da impugnação infundada é decisão DO OFICIAL (§ 4º):
      texto obrigatório, quem decidiu e quando; a hipótese do § 6º é só apoio;
    - os prazos saem do núcleo, com os feriados da casa: recurso em 10 dias
      úteis da intimação (§ 4º), contrarrazões em 10 dias úteis (§ 5º, decisão do titular),
      transação em 15 dias úteis prorrogáveis uma única vez (§ 2º);
    - sem recurso no prazo o procedimento prossegue; com recurso, contrarrazões
      e remessa ao Juiz;
    - a remessa ao Juiz prorroga a prenotação (§ 3º), sem esconder a vencida;
    - o painel mostra cada prazo com o artigo.

    Calendário de setembro de 2026: o dia 7 é feriado nacional (Independência)
    e os dias 5–6, 12–13, 19–20 e 26–27 são fim de semana. Sem feriado local
    (a fixture limpa os de Configurações), salvo no teste que põe um.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import retificacao as RT                                         # noqa: E402
import rt_tjma as NORMA                                          # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-09-01T10:00"
HOJE = "2026-09-01"
OFICIAL = "mario"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    # O CALENDÁRIO DESTES TESTES É SÓ O NACIONAL: o seed traz um feriado local
    # em 08/09, e o teste do feriado local põe o dele.
    db.set_settings({"ri_feriados_locais": ""})
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _impugnado(con, *, nome="VIZINHO EXEMPLO"):
    """Um processo com um confrontante que impugnou. Devolve (pid, cid, m)."""
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, situacao, criado_em)
           VALUES ('1083', '2', 'ATIVA', ?)""", (AGORA,))
    m = int(cur.lastrowid)
    pid = RT.autuar(con, numero="1/2026", especie=NORMA.GEORREFERENCIADA,
                    fundamento=NORMA.A_REQUERIMENTO, matricula_id=m,
                    rural=True, agora=AGORA,
                    requerente_nome="REQUERENTE EXEMPLO", usuario=OFICIAL)
    cid = RT.anotar_confrontante(con, pid, nome=nome, agora=AGORA,
                                 endereco="Rua Exemplo, 1")
    RT.notificar(con, cid, forma="PESSOAL", quando="2026-08-10", agora=AGORA,
                 prazo_ate="2026-08-31")
    RT.responder(con, cid, resposta=RT.IMPUGNOU, agora=AGORA,
                 impugnacao="diz que a cerca avança sobre o terreno dele")
    return pid, cid, m


def _rejeitar(con, pid, cid, **extra):
    return RT.rejeitar_impugnacao(
        con, pid, cid, hipotese="II", agora=AGORA, usuario=OFICIAL,
        fundamento="não indica onde nem como a cerca avançaria", **extra)


def _andamento(con, pid) -> str:
    return " ".join(x["o_que"] for x in RT.andamento(con, pid))


# ------------------------------------------------ a rejeição de plano (§ 4º)


def test_a_rejeicao_e_decisao_do_oficial_com_texto_quem_e_quando(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        _rejeitar(con, pid, cid)
    i = RT.impugnacoes(con, pid, hoje=HOJE)[0]
    assert i["rejeitada_em"] == AGORA
    assert i["rejeitada_por"] == OFICIAL
    assert i["rejeicao_hipotese"] == "II"
    assert "não indica onde" in i["rejeicao_fundamento"]
    assert i["etapa"] == "INTIMAR_REJEICAO"
    texto = _andamento(con, pid)
    assert "rejeitada de plano pelo oficial" in texto
    assert "art. 600, § 6º, II" in texto


def test_rejeitar_sem_fundamento_e_recusado_mesmo_com_a_hipotese(casa):
    """A hipótese do § 6º é apoio; o fundamento é o texto do oficial."""
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.rejeitar_impugnacao(con, pid, cid, hipotese="V", fundamento="não",
                               agora=AGORA, usuario=OFICIAL)
    assert "FUNDAMENTADA" in str(erro.value)


def test_a_hipotese_sai_do_paragrafo_6(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.rejeitar_impugnacao(con, pid, cid, hipotese="VI",
                               fundamento="fundamento bem escrito",
                               agora=AGORA, usuario=OFICIAL)
    assert "§ 6º" in str(erro.value)
    assert [h["inciso"] for h in NORMA.HIPOTESES_DE_IMPUGNACAO_INFUNDADA] == [
        "I", "II", "III", "IV", "V"]


def test_a_rejeicao_precisa_de_quem_decidiu(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.rejeitar_impugnacao(con, pid, cid, hipotese="III",
                               fundamento="sem exposição dos motivos",
                               agora=AGORA, usuario=None)
    assert "quem a tomou" in str(erro.value)


def test_so_se_rejeita_quem_impugnou(casa):
    con = _con(casa)
    with con:
        pid, _, _ = _impugnado(con)
        outro = RT.anotar_confrontante(con, pid, nome="OUTRO EXEMPLO",
                                       agora=AGORA)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        _rejeitar(con, pid, outro)
    assert "não impugnou" in str(erro.value)


def test_quem_tem_impugnacao_em_andamento_nao_se_exclui(casa):
    con = _con(casa)
    with con:
        pid, _, _ = _impugnado(con)
        outro = RT.anotar_confrontante(con, pid, nome="OUTRO EXEMPLO",
                                       agora=AGORA)
        RT.responder(con, outro, resposta=RT.IMPUGNOU, agora=AGORA,
                     impugnacao="diz que a divisa está errada")
        _rejeitar(con, pid, outro)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.excluir_confrontante(con, pid, outro, agora=AGORA)
    assert "impugnação dele tem andamento" in str(erro.value)


# ------------------------------------------------ o prazo do recurso (§ 4º)


def test_o_recurso_tem_10_dias_uteis_da_intimacao_contados_pelo_nucleo(casa):
    """Intimado numa terça, 01/09: o dia 7 é feriado, e os 10 dias úteis
    terminam em 16/09."""
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        saida = _rejeitar(con, pid, cid, intimado_em="2026-09-01")
    assert saida["recurso_prazo_ate"] == "2026-09-16"
    from ri_schema import soma_dias_uteis
    from datetime import date
    assert saida["recurso_prazo_ate"] == soma_dias_uteis(
        date(2026, 9, 1), 10).isoformat()


def test_o_feriado_local_de_configuracoes_entra_na_conta(casa):
    casa["db"].set_settings({"ri_feriados_locais": "2026-09-15 # municipal"})
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        _rejeitar(con, pid, cid)
        saida = RT.intimar_da_rejeicao(con, pid, cid, intimado_em="2026-09-01",
                                       agora=AGORA, usuario=OFICIAL)
    assert saida["recurso_prazo_ate"] == "2026-09-17"


def test_sem_recurso_no_prazo_o_procedimento_prossegue(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        _rejeitar(con, pid, cid, intimado_em="2026-09-01")
    # No último dia do prazo, ele ainda pode recorrer.
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.prosseguir_sem_recurso(con, pid, cid, hoje="2026-09-16",
                                  agora="2026-09-16T17:00")
    assert "ainda pode recorrer" in str(erro.value)
    assert RT.impugnacoes(con, pid, hoje="2026-09-17")[0]["etapa"] == \
        "RECURSO_VENCIDO"
    with con:
        saida = RT.prosseguir_sem_recurso(con, pid, cid, hoje="2026-09-17",
                                          agora="2026-09-17T09:00",
                                          usuario=OFICIAL)
    assert saida == {"desfecho": RT.SEM_RECURSO, "fase": "DECISAO"}
    assert RT.processo(con, pid)["fase"] == "DECISAO"
    faltas = " ".join(RT.o_que_falta_para_decidir(con, pid, hoje="2026-09-17"))
    assert "impugnação" not in faltas


def test_a_impugnacao_rejeitada_trava_a_decisao_ate_o_prazo_passar(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        for item in RT.conferencia(con, pid):
            RT.marcar_item(con, pid, item["item"], situacao="ATENDIDO",
                           agora=AGORA)
        _rejeitar(con, pid, cid, intimado_em="2026-09-01")
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.decidir(con, pid, sentido=RT.PROCEDENTE,
                   fundamento="planta e memorial conferem", agora=AGORA,
                   hoje="2026-09-10")
    assert "sem desfecho" in str(erro.value)


def test_recurso_depois_do_prazo_e_recusado(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        _rejeitar(con, pid, cid, intimado_em="2026-09-01")
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.registrar_recurso(con, pid, cid, em="2026-09-17",
                             razoes="a cerca avança, sim, no lado norte",
                             agora="2026-09-17T09:00")
    assert "venceu em 2026-09-16" in str(erro.value)


# ------------------------------------------------ recurso e contrarrazões (§ 5º)


def test_com_recurso_contrarrazoes_em_10_dias_e_depois_o_juiz(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        _rejeitar(con, pid, cid, intimado_em="2026-09-01")
        RT.registrar_recurso(con, pid, cid, em="2026-09-16",
                             razoes="a cerca avança dois metros no lado norte",
                             agora="2026-09-16T10:00", usuario=OFICIAL)
    # Sem recurso não se prossegue; e o recurso não vai ao Juiz sem
    # contrarrazões.
    with con, pytest.raises(RT.RetificacaoError):
        RT.prosseguir_sem_recurso(con, pid, cid, hoje="2026-09-20",
                                  agora="2026-09-20T10:00")
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.remeter_ao_juiz(con, pid, cid, informacoes="informações do oficial",
                           hoje="2026-09-18", agora="2026-09-18T10:00")
    assert "contrarrazões" in str(erro.value)
    with con:
        saida = RT.intimar_para_contrarrazoes(
            con, pid, cid, intimado_em="2026-09-18", agora="2026-09-18T10:00")
    # «10 (dez) dias», em dias úteis por decisão do titular (27/11/2026): da
    # sexta 18/09, passam dois fins de semana.
    assert saida["contrarrazoes_prazo_ate"] == "2026-10-02"
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.remeter_ao_juiz(con, pid, cid, informacoes="informações do oficial",
                           hoje="2026-10-02", agora="2026-10-02T10:00")
    assert "corre até 2026-10-02" in str(erro.value)
    with con:
        saida = RT.remeter_ao_juiz(
            con, pid, cid, hoje="2026-10-05", agora="2026-10-05T10:00",
            usuario=OFICIAL,
            informacoes="certidões das matrículas e planta juntadas")
    assert saida["desfecho"] == RT.AO_JUIZ and saida["fase"] == "AO_JUIZ"
    i = RT.impugnacoes(con, pid, hoje="2026-10-05")[0]
    assert i["remessa_paragrafo"] == "art. 600, § 5º"


def test_as_contrarrazoes_juntadas_liberam_a_remessa_antes_do_prazo(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        _rejeitar(con, pid, cid, intimado_em="2026-09-01")
        RT.registrar_recurso(con, pid, cid, em="2026-09-02",
                             razoes="a cerca avança dois metros",
                             agora="2026-09-02T10:00")
        RT.intimar_para_contrarrazoes(con, pid, cid, intimado_em="2026-09-03",
                                      agora="2026-09-03T10:00")
        RT.registrar_contrarrazoes(con, pid, cid, em="2026-09-04",
                                   texto="a planta segue o marco antigo",
                                   agora="2026-09-04T10:00")
        RT.remeter_ao_juiz(con, pid, cid, hoje="2026-09-04",
                           agora="2026-09-04T11:00",
                           informacoes="informações complementares do oficial")
    assert RT.processo(con, pid)["fase"] == "AO_JUIZ"


def test_rejeitada_sem_recurso_nao_vai_ao_juiz(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        _rejeitar(con, pid, cid, intimado_em="2026-09-01")
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.remeter_ao_juiz(con, pid, cid, informacoes="informações do oficial",
                           hoje="2026-09-20", agora="2026-09-20T10:00")
    assert "só vai ao Juiz com recurso" in str(erro.value)


# ------------------------------------------------ a conciliação (§ 2º)


def test_a_transacao_tem_15_dias_uteis_prorrogaveis_uma_unica_vez(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        saida = RT.pedir_transacao(con, pid, cid, quem_pediu=RT.PROFISSIONAL,
                                   em="2026-09-01", agora=AGORA)
    assert saida["transacao_prazo_ate"] == "2026-09-23"
    assert RT.processo(con, pid)["fase"] == "MEDIACAO"
    with con:
        saida = RT.prorrogar_transacao(con, pid, cid, em="2026-09-20",
                                       agora="2026-09-21T10:00")
    # Conta do fim do prazo original; 12/10 é feriado nacional.
    assert saida["transacao_prazo_ate"] == "2026-10-15"
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.prorrogar_transacao(con, pid, cid, em="2026-10-10",
                               agora="2026-10-10T10:00")
    assert "uma prorrogação" in str(erro.value)


def test_so_o_requerente_ou_o_profissional_pedem_a_transacao(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
    with con, pytest.raises(RT.RetificacaoError):
        RT.pedir_transacao(con, pid, cid, quem_pediu="IMPUGNANTE",
                           em="2026-09-01", agora=AGORA)


def test_o_acordo_resolve_a_impugnacao(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        RT.pedir_transacao(con, pid, cid, quem_pediu=RT.REQUERENTE,
                           em="2026-09-01", agora=AGORA)
        saida = RT.registrar_acordo(con, pid, cid, agora=AGORA,
                                    texto="as partes recuaram a cerca um metro")
    assert saida == {"desfecho": RT.ACORDO, "fase": "DECISAO"}


# ------------------------------------------------ a remessa e a prenotação (§ 3º)


def _prenotacao(con, pid, m, *, data_limite):
    cur = con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               data_limite, situacao, matricula_id, criado_em)
           VALUES (77, '1A', '2026-08-01', ?, 'ABERTO', ?, ?)""",
        (data_limite, m, AGORA))
    pre = int(cur.lastrowid)
    RT.atualizar_atendimento(con, pid, prenotacao_id=pre, prenotacao="77",
                             protocolo_id=None, protocolo_numero=None,
                             agora=AGORA)
    return pre


def test_fundada_com_controversia_vai_ao_juiz_e_a_prenotacao_fica_suspensa(casa):
    con = _con(casa)
    with con:
        pid, cid, m = _impugnado(con)
        pre = _prenotacao(con, pid, m, data_limite="2026-09-30")
        saida = RT.remeter_ao_juiz(
            con, pid, cid, hoje=HOJE, agora=AGORA, usuario=OFICIAL,
            informacoes="a controvérsia sobre a divisa norte permanece")
    linha = con.execute("SELECT * FROM ri_protocolos WHERE id = ?",
                        (pre,)).fetchone()
    assert linha["prazo_suspenso_desde"][:10] == HOJE
    assert linha["prazo_suspenso_motivo"] == "RETIFICACAO"
    assert "ficou suspenso" in saida["prenotacao"]
    assert RT.impugnacoes(con, pid, hoje=HOJE)[0]["remessa_paragrafo"] == \
        "art. 600, § 3º"
    assert "ficou suspenso" in _andamento(con, pid)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.decidir(con, pid, sentido=RT.PROCEDENTE, fundamento="tudo certo",
                   agora=AGORA, hoje=HOJE)
    assert "com o Juiz corregedor" in str(erro.value)


def test_a_prenotacao_vencida_nao_e_suspensa_e_o_aviso_diz(casa):
    """Suspensa, nenhuma tela a conta como vencida — e suspender agora
    esconderia o vencimento."""
    con = _con(casa)
    with con:
        pid, cid, m = _impugnado(con)
        pre = _prenotacao(con, pid, m, data_limite="2026-08-25")
        saida = RT.remeter_ao_juiz(con, pid, cid, hoje=HOJE, agora=AGORA,
                                   informacoes="a controvérsia permanece")
    linha = con.execute("SELECT * FROM ri_protocolos WHERE id = ?",
                        (pre,)).fetchone()
    assert not linha["prazo_suspenso_desde"]
    assert "venceu em 2026-08-25" in saida["prenotacao"]


def test_sem_prenotacao_ligada_a_remessa_avisa(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        saida = RT.remeter_ao_juiz(con, pid, cid, hoje=HOJE, agora=AGORA,
                                   informacoes="a controvérsia permanece")
    assert "não tem prenotação ligada" in saida["prenotacao"]


def test_a_remessa_e_ato_fundamentado(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.remeter_ao_juiz(con, pid, cid, informacoes="ok", hoje=HOJE,
                           agora=AGORA)
    assert "art. 601" in str(erro.value)


def test_o_retorno_do_juiz_libera_a_decisao(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        RT.remeter_ao_juiz(con, pid, cid, hoje=HOJE, agora=AGORA,
                           informacoes="a controvérsia permanece")
        saida = RT.registrar_retorno_do_juiz(
            con, pid, cid, em="2026-09-01", agora=AGORA,
            decisao="o Juiz afastou a impugnação")
    assert saida["fase"] == "DECISAO"


# ------------------------------------------------ o painel: cada prazo com o artigo


def test_os_proximos_passos_mostram_cada_prazo_com_o_artigo(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        outro = RT.anotar_confrontante(con, pid, nome="SEGUNDO EXEMPLO",
                                       agora=AGORA, endereco="Rua Exemplo, 2")
        RT.notificar(con, outro, forma="PESSOAL", quando="2026-08-10",
                     agora=AGORA, prazo_ate="2026-08-31")
        RT.responder(con, outro, resposta=RT.IMPUGNOU, agora=AGORA,
                     impugnacao="diz que a divisa sul está errada")
        _rejeitar(con, pid, cid, intimado_em="2026-09-01")
        RT.pedir_transacao(con, pid, outro, quem_pediu=RT.REQUERENTE,
                           em="2026-09-01", agora=AGORA)
    passos = RT.proximos_passos(con, pid, hoje="2026-09-02")
    por_artigo = {p["artigo"]: p for p in passos}
    assert "2026-09-16" in por_artigo["art. 600, § 4º"]["o_que"]
    assert "2026-09-23" in por_artigo["art. 600, § 2º"]["o_que"]
    assert "prorrogáveis uma única vez" in por_artigo["art. 600, § 2º"]["o_que"]


def test_o_passo_do_juiz_diz_que_a_prenotacao_fica_prorrogada(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
        RT.remeter_ao_juiz(con, pid, cid, hoje=HOJE, agora=AGORA,
                           informacoes="a controvérsia permanece")
    passos = RT.proximos_passos(con, pid, hoje=HOJE)
    juiz = [p for p in passos if p["artigo"] == "art. 600, § 3º"]
    assert juiz and "prenotação ficam prorrogados" in juiz[0]["o_que"]


def test_a_impugnacao_aberta_lembra_os_dois_caminhos(casa):
    con = _con(casa)
    with con:
        pid, _, _ = _impugnado(con)
    passos = RT.proximos_passos(con, pid, hoje=HOJE)
    abertas = [p for p in passos if p["artigo"] == "art. 600"]
    assert abertas and "5 dias úteis" in abertas[0]["o_que"]
    assert "rejeite-a de plano" in abertas[0]["o_que"]


# ------------------------------------------------ a tela


def test_a_tela_rejeita_de_plano_com_o_token_que_ela_deu(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
    url = f"/registro-imoveis/retificacoes/{pid}"
    html = casa["cliente"].get(url).get_data(as_text=True)
    assert "As impugnações" in html
    for h in NORMA.HIPOTESES_DE_IMPUGNACAO_INFUNDADA:
        assert f'value="{h["inciso"]}"' in html
    r = casa["cliente"].post(
        f"{url}/impugnacao",
        data={"csrf_token": _token(html), "acao": "rejeitar",
              "confrontante_id": str(cid), "hipotese": "IV",
              "fundamento": "trata de servidão de passagem, estranha à retificação"},
        follow_redirects=True)
    assert r.status_code == 200
    pagina = " ".join(r.get_data(as_text=True).split())
    assert "Rejeitada de plano" in pagina
    assert "art. 600, § 6º, IV" in pagina
    assert "Impugnante intimado da rejeição em" in pagina


def test_a_tela_mostra_a_recusa_do_dominio(casa):
    con = _con(casa)
    with con:
        pid, cid, _ = _impugnado(con)
    url = f"/registro-imoveis/retificacoes/{pid}"
    html = casa["cliente"].get(url).get_data(as_text=True)
    r = casa["cliente"].post(
        f"{url}/impugnacao",
        data={"csrf_token": _token(html), "acao": "prosseguir",
              "confrontante_id": str(cid)}, follow_redirects=True)
    assert "intimação do impugnante" in r.get_data(as_text=True)


def test_a_tela_das_normas_mostra_o_art_600():
    import retificacao_web  # noqa: F401  (a rota importa)
    tela = (RAIZ / "templates" / "ri_retificacao_normas.html").read_text(
        encoding="utf-8")
    assert "HIPOTESES_DE_IMPUGNACAO_INFUNDADA" in tela
    assert "CAMINHOS_DA_IMPUGNACAO" in tela

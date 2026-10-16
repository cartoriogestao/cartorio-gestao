"""O agente do RCPN — fiscaliza o assento, orienta o balcão, resolve o objetivo.

O QUE ESTES TESTES GUARDAM, e cada um saiu de um caso medido na produção em
09/10/2026:

    **Que a mesma pessoa em dois assentos ativos aparece** — o óbito de um falecido
    lavrado duas vezes em 87 segundos, e o nascimento de uma criança com a
    mesma DNV em dois assentos.

    **Que gêmeos não são duplicidade** — cada um tem a sua DNV.

    **Que assento ativo sem número aparece, e diz de quem é a sobra.**

    **Que casamento lavrado sem termo aparece** — o 1013, livro B-4, fl. 41.

    **Que a anotação do art. 367 vence em cinco dias CORRIDOS**, e que a de
    assento cancelado não é cobrada: é dispensada sozinha, com motivo e rastro,
    e só com o interruptor ligado.

    **Que o acervo não vira achado** — o corte de 10/09/2026.

    **Que a habilitação aberta para casal que já casou aparece.**

    **Que o boletim do dia junta os achados do RCPN e renova sem duplicar.**

    **Que regra que quebra vira NAO_MEDIU, e não zero.**
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_rcpn as G                                            # noqa: E402

HOJE = date(2026, 10, 9)
AGORA = "2026-10-09T08:00:00"


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('ri_cns','000000')")
    c.commit()
    yield c
    c.close()


def _assento(con, especie="NASCIMENTO", numero=1, nome="FULANO DE TAL",
             data_ato="2026-10-01T10:00:00", situacao="ATIVO", origem="MANUAL",
             teor="TERMO ESCRITO", **campos):
    serie = {"NASCIMENTO": "RC_A", "CASAMENTO": "RC_B", "OBITO": "RC_C"}[especie]
    dados = {"serie": serie, "especie": especie, "numero": numero, "nome": nome,
             "data_ato": data_ato, "situacao": situacao, "origem": origem,
             "teor": teor, "criado_em": data_ato, "matricula": "X" * 32}
    dados.update(campos)
    cols = ", ".join(dados)
    cur = con.execute(f"INSERT INTO rc_assentos ({cols}) VALUES "
                      f"({', '.join('?' * len(dados))})", tuple(dados.values()))
    return cur.lastrowid


def _pessoa(con, assento_id, papel, nome="ALGUEM"):
    con.execute("INSERT INTO rc_pessoas (assento_id, papel, nome, criado_em) "
                "VALUES (?,?,?,?)", (assento_id, papel, nome, AGORA))


def _nascimento_completo(con, **k):
    k.setdefault("dnv", "30-11111111-1")
    k.setdefault("cpf_registrado", "12345678909")
    k.setdefault("hora_fato", "10:00")
    k.setdefault("cor_raca", "PARDA")
    a = _assento(con, **k)
    for papel in ("REGISTRADO", "MAE", "PAI", "DECLARANTE"):
        _pessoa(con, a, papel)
    return a


def _regras(achados):
    return [a["regra"] for a in achados]


# ------------------------------------------------------------- o assento

def test_obito_lavrado_duas_vezes_aparece(con):
    a = _assento(con, "OBITO", 1983, "MOACIR SILVA PEREIRA", data_fato="2026-09-26",
                 data_ato="2026-10-09T13:58:35")
    b = _assento(con, "OBITO", 1984, "Moacir Silva Pereira", data_fato="2026-09-26",
                 data_ato="2026-10-09T14:00:02")
    grupos = G.duplicidades(con)
    assert [g["ids"] for g in grupos] == [[a, b]]
    achados = G.conferir_assentos(con, HOJE)
    dup = [x for x in achados if x["regra"] == "RCPN_DUPLICIDADE"]
    assert len(dup) == 1 and dup[0]["gravidade"] == "CRITICO"
    assert f"rc_assentos:{b}" in dup[0]["chave"]


def test_nascimento_pela_mesma_dnv_com_e_sem_traco(con):
    _nascimento_completo(con, numero=19578, dnv="30-96542060-6")
    _nascimento_completo(con, numero=19579, nome="OUTRO NOME", dnv="30965420606")
    assert len(G.duplicidades(con)) == 1


def test_gemeos_nao_sao_duplicidade(con):
    _nascimento_completo(con, numero=10, nome="ANA", dnv="30-11111111-1", data_fato="2026-10-01")
    _nascimento_completo(con, numero=11, nome="ANA", dnv="30-22222222-2", data_fato="2026-10-01")
    assert G.duplicidades(con) == []


def test_cancelado_nao_e_duplicidade(con):
    _assento(con, "OBITO", 1981, "BELTRANO EXEMPLO", data_fato="2026-09-16", situacao="CANCELADO")
    _assento(con, "OBITO", 1981, "BELTRANO EXEMPLO", data_fato="2026-09-16")
    assert G.duplicidades(con) == []


def test_acervo_nao_vira_achado(con):
    _assento(con, "OBITO", 5, "VELHO", data_fato="1990-01-01", data_ato="1990-01-02",
             origem="EOFICIO")
    _assento(con, "OBITO", 6, "VELHO", data_fato="1990-01-01", data_ato="1990-01-03",
             origem="IMPORTACAO")
    _assento(con, "NASCIMENTO", 7, data_ato="2026-08-01", teor=None, matricula=None)
    assert G.conferir_assentos(con, HOJE) == []


def test_assento_ativo_sem_numero_diz_de_quem_e_a_sobra(con):
    bom = _nascimento_completo(con, numero=19578, dnv="30-96542060-6")
    sobra = _nascimento_completo(con, numero=None, dnv="30-96542060-6", matricula=None)
    i = G.inacabados(con)
    assert [x["id"] for x in i] == [sobra] and i[0]["gemeo_de"] == bom
    inac = [x for x in G.conferir_assentos(con, HOJE) if x["regra"] == "RCPN_INACABADO"]
    assert "19578" in inac[0]["detalhe"]


def test_casamento_sem_termo(con):
    a = _assento(con, "CASAMENTO", 1013, "A e B", teor=None, regime_bens="COMUNHAO PARCIAL")
    _pessoa(con, a, "NUBENTE1")
    _pessoa(con, a, "NUBENTE2")
    achados = G.conferir_assentos(con, HOJE)
    assert _regras(achados) == ["RCPN_SEM_TERMO"]
    assert f"/rcpn/assentos/{a}/termo" in achados[0]["detalhe"]


def test_dado_obrigatorio_e_matricula_proposta(con):
    a = _assento(con, "NASCIMENTO", 19578, matricula=None, dnv=None,
                 data_ato="2026-10-07T10:46:24")
    _pessoa(con, a, "REGISTRADO")
    livro = con.execute(
        "INSERT INTO nu_livros (serie, atribuicao, numero, folhas, criado_em) "
        "VALUES ('RC_A', 6, '24', 300, ?)", (AGORA,)).lastrowid
    con.execute("INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em, livro_id, "
                "folha, numero_ordem) VALUES (?, 'REGISTRO', ?, ?, ?, 192, 19578)",
                (a, AGORA, AGORA, livro))
    dado = [x for x in G.conferir_assentos(con, HOJE) if x["regra"] == "RCPN_DADO_OBRIGATORIO"]
    assert len(dado) == 1
    t = dado[0]["titulo"]
    assert "matrícula" in t and "DNV" in t and "a mãe" in t
    # a mesma conta que a produção gravou no 8363: livro 24, fl. 192, termo 19578
    assert "00000001552026100024192001957843" in dado[0]["detalhe"]


def test_complementar_nao_vira_tarefa(con):
    _nascimento_completo(con, numero=1, cpf_registrado="000.000.018-30")
    compl = [x for x in G.conferir_assentos(con, HOJE)]
    assert _regras(compl) == ["RCPN_DADO_COMPLEMENTAR"]
    assert "RCPN_DADO_COMPLEMENTAR" in G.REGRAS_SEM_TAREFA


# ------------------------------------------------------------- as anotações

def _anotacao(con, assento_id, alvo="NASCIMENTO"):
    return con.execute("INSERT INTO rc_anotacoes (assento_id, especie_alvo, situacao, "
                       "criado_em) VALUES (?,?,'PENDENTE',?)",
                       (assento_id, alvo, AGORA)).lastrowid


def test_anotacao_vence_em_cinco_dias_corridos(con):
    velho = _assento(con, "OBITO", 1982, "ALDERICO", data_ato="2026-09-24")
    novo = _assento(con, "OBITO", 1985, "OUTRO", data_ato="2026-10-08T09:00:00")
    _anotacao(con, velho)
    _anotacao(con, novo)
    an = {x["chave"].split(":")[2]: x for x in G.conferir_anotacoes(con, HOJE)}
    assert an[str(velho)]["gravidade"] == "VENCIDO" and an[str(velho)]["prazo"] == "2026-09-29"
    assert an[str(novo)]["gravidade"] == "PRAZO" and an[str(novo)]["prazo"] == "2026-10-13"


def test_anotacao_de_assento_cancelado_e_dispensada_sozinha_com_rastro(con):
    canc = _assento(con, "OBITO", 1981, "BELTRANO EXEMPLO", situacao="CANCELADO", data_ato="2026-09-23")
    vale = _assento(con, "OBITO", 1981, "BELTRANO EXEMPLO", data_ato="2026-09-24")
    n1 = _anotacao(con, canc)
    n2 = _anotacao(con, vale)
    regras = _regras(G.conferir_anotacoes(con, HOJE))
    assert sorted(regras) == ["RCPN_ANOTACAO", "RCPN_ANOTACAO_DE_CANCELADO"]
    feito = G.resolver(con, HOJE, agora=AGORA)
    assert feito["ligado"] and feito["dispensadas"] == 1
    sit = dict(con.execute("SELECT id, situacao FROM rc_anotacoes").fetchall())
    assert sit == {n1: "DISPENSADA", n2: "PENDENTE"}
    rastro = con.execute("SELECT * FROM ge_rcpn_resolvidos").fetchall()
    assert len(rastro) == 1 and rastro[0]["registro_id"] == n1
    assert "CANCELADO" in rastro[0]["motivo"]
    assert _regras(G.conferir_anotacoes(con, HOJE)) == ["RCPN_ANOTACAO"]


def test_interruptor_desligado_nao_mexe(con):
    canc = _assento(con, "OBITO", 1981, "BELTRANO EXEMPLO", situacao="CANCELADO", data_ato="2026-09-23")
    _anotacao(con, canc)
    con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, 'DESLIGADO')",
                (G.CHAVE_RESOLVER,))
    assert G.resolver(con, HOJE, agora=AGORA)["dispensadas"] == 0
    assert con.execute("SELECT situacao FROM rc_anotacoes").fetchone()[0] == "PENDENTE"


# ------------------------------------------------------------- os processos

def _hab(con, situacao, n1="AMARO ARAÚJO DA SILVA", n2="EMILIO DA COSTA ROCHEDO", **k):
    dados = {"numero": k.pop("numero", 1), "ano": 2026, "data_entrada": "2026-10-07",
             "tipo": "CIVIL", "situacao": situacao, "nubente1_nome": n1,
             "nubente2_nome": n2, "criado_em": AGORA, **k}
    return con.execute(f"INSERT INTO hc_habilitacoes ({', '.join(dados)}) VALUES "
                       f"({', '.join('?' * len(dados))})", tuple(dados.values())).lastrowid


def test_habilitacao_de_casal_ja_casado(con):
    _hab(con, "CELEBRADO", numero=1, celebrado_em="2026-10-08", casamento_assento_id=1)
    dup = _hab(con, "EM_ANALISE", numero=2, n1="Emilio da Costa Rochedo",
               n2="Amaro Araujo da Silva")
    h = G.conferir_habilitacoes(con, HOJE)
    assert len(h) == 1 and f"hc_habilitacoes:{dup}" in h[0]["chave"]


def test_habilitacao_vencida_e_critica(con):
    _hab(con, "HABILITADO", n1="X", n2="Y", habilitacao_vale_ate="2026-10-01")
    _hab(con, "HABILITADO", numero=2, n1="Z", n2="W", habilitacao_vale_ate="2026-10-15")
    gravs = sorted(a["gravidade"] for a in G.conferir_habilitacoes(con, HOJE))
    assert gravs == ["CRITICO", "PRAZO"]


# ------------------------------------------------------------- o todo

def test_parte_que_quebra_vira_nao_mediu(con, monkeypatch):
    def quebra(con, hoje):
        raise RuntimeError("coluna sumiu")
    monkeypatch.setattr(G, "PARTES", (("RCPN_X", quebra),))
    a = G.conferir(con, HOJE)
    assert a[0]["gravidade"] == "NAO_MEDIU" and "coluna sumiu" in a[0]["detalhe"]


def test_rodada_registra_e_agente_deixa_de_estar_parado(con):
    assert "RCPN_AGENTE_PARADO" in _regras(G.conferir_o_agente(con, HOJE))
    G.rodada(con, None, HOJE)
    assert G.conferir_o_agente(con, HOJE) == []


def test_boletim_junta_e_renova_sem_duplicar(con, cg_casa):
    import gestor_rotina as GR
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    cg_casa["db"].create_user("mario", "MARIO", "Senha#12345", "ADMIN")
    cg_casa["db"].create_user("elisa", "Elisa", "Senha#12345", "USER")
    cg_casa["db"].create_user("debora", "Debora", "Senha#12345", "USER")
    GR.aplicar_distribuicao(con)
    GR.gravar_achados(con, [G._achado("RCPN_TERMO:rc_assentos:1", "RCPN_SEM_TERMO",
                                      "CRITICO", "casamento nº 1013: lavrado sem termo")]
                      + [{"chave": "SIRC:x", "regra": "SIRC", "gravidade": "VENCIDO",
                          "setor": "RCPN", "titulo": "SIRC: registro não enviado",
                          "detalhe": "", "prazo": "2026-10-01", "fundamento": ""}], HOJE)
    # CONTRATO MUDADO EM 12/10/2026: o boletim é um RELATO do dia para o
    # responsável do RCPN (painel → Relatos do dia), e não mais tarefa.
    t1 = G.publicar_boletim(con, HOJE)
    assert t1 is not None
    dono = con.execute("SELECT u.username FROM rd_relatos r JOIN users u ON u.id = "
                       "r.destinatario_id WHERE r.id=?", (t1,)).fetchone()[0]
    assert dono in ("elisa", "debora")      # o rodízio do RCPN, e não o oficial
    t2 = G.publicar_boletim(con, HOJE)
    assert t1 == t2
    texto = con.execute("SELECT corpo FROM rd_relatos WHERE id=?", (t1,)).fetchone()[0]
    assert "lavrado sem termo" in texto and "SIRC: registro não enviado" in texto
    assert "Como:" in texto
    t3 = G.publicar_boletim(con, date(2026, 10, 10))
    assert t3 != t1                          # o de ontem fica no histórico
    assert con.execute("SELECT count(*) FROM tasks WHERE source_type=?",
                       (G.SOURCE_BOLETIM,)).fetchone()[0] == 0


# ------------------------------------------- a conferência dos dados (11/10/2026)

def test_dado_contraditorio_de_assento_lavrado_aparece(con):
    a = _nascimento_completo(con, numero=30, nome="CICLANO EXEMPLO")
    _pessoa(con, a, "TESTEMUNHA", "CICLANO EXEMPLO")
    dados = [x for x in G.conferir_dados(con, HOJE) if x["regra"] == "RCPN_DADOS_CONTRADITORIOS"]
    assert len(dados) == 1 and "testemunha" in dados[0]["detalhe"]


def test_termo_reescrito_depois_de_lavrado_aparece(con):
    a = _nascimento_completo(con, numero=31, nome="CICLANO EXEMPLO",
                             teor="Termo do CICLANO EXEMPLO, lido e achado conforme.")
    G.registrar_termos(con, AGORA)
    assert not [x for x in G.conferir_dados(con, HOJE) if x["regra"] == "RCPN_TERMO_ALTERADO"]
    con.execute("UPDATE rc_assentos SET teor=? WHERE id=?",
                ("Termo do CICLANO EXEMPLO, CPF 000.000.001-91, lido e achado conforme.", a))
    alt = [x for x in G.conferir_dados(con, HOJE) if x["regra"] == "RCPN_TERMO_ALTERADO"]
    assert len(alt) == 1 and "CPF 000" in alt[0]["detalhe"]
    G.aceitar_termo_atual(con, a, quem="o oficial", agora=AGORA)
    assert not [x for x in G.conferir_dados(con, HOJE) if x["regra"] == "RCPN_TERMO_ALTERADO"]

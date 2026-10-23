"""O gestor: a conferência diária, as tarefas que ela abre e fecha, e a cobrança.

O QUE ESTES TESTES GUARDAM
    **Que regra quebrada não vira zero.** No panorama de 02/10/2026 o painel dizia
    «zero» com dois óbitos no mês. Aqui a regra que quebra vira achado NAO_MEDIU.

    **Que o envio registrado apaga a cobrança, e só ele.** Sem `ge_envios` a
    conferência cobraria para sempre o que o balcão já mandou pelo portal.

    **Que a tarefa fecha sozinha e reabre sozinha.** Concluir no balcão o que a
    conferência ainda acha não fecha nada — é isso que é cobrar cumprimento.

    **Que o óbito cancelado não entra na comunicação do mês.** O termo 1981 saía
    duas vezes.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from bd_nativo import banco                                      # noqa: E402
import gestor_conferencia as GC                                  # noqa: E402
import gestor_envios as GE                                       # noqa: E402
import gestor_rotina as GR                                       # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-06T08:00:00"
HOJE = date(2026, 10, 6)


@pytest.fixture()
def con(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("debora", "DEBORA EXEMPLO REIS", SENHA, "USER")
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _assento(con, *, especie="NASCIMENTO", numero=1, nome="FULANO",
             data_ato="2026-09-15", situacao="ATIVO", cor="Parda"):
    return int(con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, cor_raca)
           VALUES ('RC_A',?,?,?,?,?,?,'SISTEMA',?,?)""",
        (especie, numero, nome, data_ato, data_ato, situacao, AGORA, cor)).lastrowid)


def _regras(achados, regra):
    return [a for a in achados if a["regra"] == regra]


@pytest.fixture()
def sirc_como_tarefa(monkeypatch):
    """A MECÂNICA DAS TAREFAS (abrir, fechar, reabrir, cobrar, revezar) é a mesma
    para toda regra que vira tarefa, e o SIRC é o achado mais fácil de montar.
    Desde 13/10/2026 o SIRC NÃO vira tarefa — as Centrais e as cargas saíram das
    tarefas por ordem do oficial (`test_gestor_essencial`) —, e por isso estes
    testes o põem de volta só para exercitar a mecânica."""
    monkeypatch.setattr(GR, "REGRAS_SEM_TAREFA", GR.REGRAS_SEM_TAREFA - {"SIRC"})


# ------------------------------------------------------ nada vira zero


def test_banco_vazio_nao_quebra_regra_nenhuma(con):
    achados = GC.conferir(con, HOJE)
    nao_medidos = [a for a in achados if a["gravidade"] == "NAO_MEDIU"]
    # Banco vazio não fornece pasta da CRA nem preço de selo pago. As regras
    # novas devem declarar essas lacunas, sem esconder uma exceção como zero.
    assert {a["chave"] for a in nao_medidos} == {
        "PT_PASTA_CRA", "FISCAL_SALDO:NAO_MEDIU",
    }
    assert not [a for a in nao_medidos if a["chave"].startswith("NAO_MEDIU:")]


def test_regra_que_quebra_vira_nao_mediu_e_nao_lista_vazia(con, monkeypatch):
    def quebra(con, hoje):
        raise RuntimeError("coluna sumiu")
    monkeypatch.setattr(GC, "REGRAS", (("SIRC", quebra),))
    achados = GC.conferir(con, HOJE)
    assert len(achados) == 1
    assert achados[0]["gravidade"] == "NAO_MEDIU"
    assert "coluna sumiu" in achados[0]["detalhe"]


# ------------------------------------------------------ SIRC e envios


def test_nascimento_lavrado_e_nao_enviado_vence_em_um_dia_util(con):
    aid = _assento(con, data_ato="2026-09-15")
    sirc = _regras(GC.conferir(con, HOJE), "SIRC")
    assert [a["chave"] for a in sirc] == [f"SIRC:rc_assentos:{aid}:2026-09-15"]
    assert sirc[0]["gravidade"] == "VENCIDO"
    assert sirc[0]["prazo"] == "2026-09-16"


def test_envio_registrado_apaga_a_cobranca(con):
    aid = _assento(con, data_ato="2026-09-15")
    GE.registrar(con, "SIRC", protocolo="SIRC-123", registrado_por="debora",
                 referencias=[f"rc_assentos:{aid}"])
    assert _regras(GC.conferir(con, HOJE), "SIRC") == []


def test_envio_sem_protocolo_nao_se_registra(con):
    with pytest.raises(GE.EnvioError, match="protocolo"):
        GE.registrar(con, "SIRC", protocolo=" ", registrado_por="debora",
                     referencias=["rc_assentos:1"])


def test_chave_torta_e_recusada_em_vez_de_gravada(con):
    with pytest.raises(GE.EnvioError, match="formato"):
        GE.registrar(con, "CENSEC", protocolo="X", registrado_por="debora",
                     competencia="2026-09")


# ------------------------------------------------------ óbitos do mês


def test_obito_cancelado_nao_entra_na_comunicacao_do_mes(con):
    _assento(con, especie="OBITO", numero=1981, nome="ISAIAS",
             data_ato="2026-09-23", situacao="CANCELADO")
    _assento(con, especie="OBITO", numero=1981, nome="ISAIAS", data_ato="2026-09-24")
    obitos = _regras(GC.conferir(con, HOJE), "OBITO_MENSAL")
    assert len(obitos) == 5                       # quatro do art. 226 + Junta
    assert all(a["detalhe"].startswith("1 óbito(s)") for a in obitos)
    assert all(a["prazo"] == "2026-10-07" for a in obitos)


def test_mes_sem_obito_tambem_cobra_a_comunicacao_negativa(con):
    obitos = _regras(GC.conferir(con, HOJE), "OBITO_MENSAL")
    assert obitos and all("negativa" in a["detalhe"] for a in obitos)


def test_destino_enviado_sai_e_os_outros_ficam(con):
    GE.registrar(con, "OBITO_TRE", protocolo="TRE-9", registrado_por="debora",
                 competencia="2026-09")
    chaves = {a["chave"] for a in _regras(GC.conferir(con, HOJE), "OBITO_MENSAL")}
    assert "OBITO_TRE:2026-09" not in chaves
    assert "OBITO_RFB:2026-09" in chaves


# ------------------------------------------------------ IBGE


def test_ibge_do_terceiro_trimestre_vence_dia_8_de_outubro(con):
    ibge = _regras(GC.conferir(con, HOJE), "IBGE")
    assert [(a["chave"], a["prazo"], a["gravidade"]) for a in ibge] == [
        ("IBGE:2026-T3", "2026-10-08", "PRAZO")]


# ------------------------------------------------------ tarefas


def test_rodada_abre_uma_tarefa_por_regra_e_nao_uma_por_achado(con, sirc_como_tarefa):
    for n in range(3):
        _assento(con, numero=100 + n, data_ato="2026-09-15")
    GR.rodar(con, HOJE)
    tarefas = con.execute(
        """SELECT * FROM tasks WHERE source_ref = 'GESTOR:SIRC:RCPN'""").fetchall()
    assert len(tarefas) == 1
    assert "(3)" in tarefas[0]["title"]
    assert tarefas[0]["priority"] == "CRITICA"


def test_tarefa_fecha_sozinha_quando_a_lista_zera(con, sirc_como_tarefa):
    aid = _assento(con, data_ato="2026-09-15")
    GR.rodar(con, HOJE)
    GE.registrar(con, "SIRC", protocolo="P", registrado_por="debora",
                 referencias=[f"rc_assentos:{aid}"])
    resumo = GR.rodar(con, HOJE)
    t = con.execute("SELECT status FROM tasks WHERE source_ref='GESTOR:SIRC:RCPN'"
                    ).fetchone()
    assert t["status"] == "CONCLUIDA"
    assert resumo["fechadas"] >= 1
    assert con.execute(
        "SELECT resolvido_em FROM ge_achados WHERE regra='SIRC'").fetchone()[0]


def test_concluir_no_balcao_o_que_ainda_esta_pendente_reabre(con, sirc_como_tarefa):
    _assento(con, data_ato="2026-09-15")
    GR.rodar(con, HOJE)
    con.execute("UPDATE tasks SET status='CONCLUIDA' WHERE source_ref='GESTOR:SIRC:RCPN'")
    resumo = GR.rodar(con, HOJE)
    t = con.execute("SELECT id, status FROM tasks WHERE source_ref='GESTOR:SIRC:RCPN'"
                    ).fetchone()
    assert t["status"] == "ABERTA" and resumo["reabertas"] == 1
    assert con.execute(
        "SELECT 1 FROM task_history WHERE task_id=? AND action='REABERTA'",
        (t["id"],)).fetchone()


def test_cobranca_sai_uma_vez_por_dia(con, sirc_como_tarefa):
    # CONTRATO MUDADO EM 12/10/2026, por ordem do oficial («os relatos diários
    # ficarem num campo próprio»): a cobrança deixou de ser NOTA na tarefa e
    # virou UM relato por pessoa por dia, renovado a cada rodada.
    _assento(con, data_ato="2026-09-15")
    GR.rodar(con, HOJE)
    GR.rodar(con, HOJE)
    tid, dono = con.execute("SELECT id, assigned_user_id FROM tasks "
                            "WHERE source_ref='GESTOR:SIRC:RCPN'").fetchone()
    assert con.execute(
        """SELECT count(*) FROM task_history WHERE task_id=? AND action='NOTA'
              AND note LIKE '[Cobrança]%'""", (tid,)).fetchone()[0] == 0
    assert con.execute(
        "SELECT count(*) FROM rd_relatos WHERE origem='GESTOR_COBRANCA' AND dia=? "
        "AND destinatario_id=?", (HOJE.isoformat(), dono)).fetchone()[0] == 1


def test_responsavel_definido_pelo_oficial_nao_e_sobrescrito(con):
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    debora = con.execute("SELECT id FROM users WHERE username='debora'").fetchone()[0]
    con.execute("""INSERT INTO ge_responsaveis (setor, user_id, origem, definido_em,
                       definido_por) VALUES ('RCPN', ?, 'OFICIAL', ?, 'mario')""",
                (debora, AGORA))
    GR.aplicar_distribuicao(con)
    resp = GR.inferir_responsaveis(con)
    assert resp["RCPN"]["titular"] == debora
    mario = con.execute("SELECT id FROM users WHERE username='mario'").fetchone()[0]
    assert resp["TI"]["titular"] == mario


# ------------------------------------------------------ a distribuição de 06/10


@pytest.fixture()
def casa_inteira(con, cg_casa):
    db = cg_casa["db"]
    for login, nome in (("elisa", "ELISA EXEMPLO LIMA"),
                        ("carla", "CARLA EXEMPLO LIMA"),
                        ("beatriz", "BEATRIZ EXEMPLO DE SOUZA")):
        db.create_user(login, nome, SENHA, "USER")
    db.create_user("alberto", "ANALISTA DE SISTEMAS", SENHA, "ADMIN")
    return con


def _id(con, login):
    return con.execute("SELECT id FROM users WHERE username=?", (login,)).fetchone()[0]


def test_a_distribuicao_do_oficial_entra_como_ele_ditou(casa_inteira):
    con = casa_inteira
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    assert GR.aplicar_distribuicao(con) == []
    resp = GR.inferir_responsaveis(con)
    assert resp["RCPN"] == {"titular": _id(con, "elisa"),
                            "substituto": _id(con, "debora"),
                            "rodizio": True, "origem": "OFICIAL"}
    for setor in ("RI", "NOTAS", "RCPJ_RTD"):
        assert (resp[setor]["titular"], resp[setor]["substituto"]) == (
            _id(con, "carla"), _id(con, "beatriz")), setor
    for setor in ("RI_QUALIFICACAO", "NOTAS_QUALIFICACAO", "RCPJ_RTD_QUALIFICACAO"):
        assert (resp[setor]["titular"], resp[setor]["substituto"]) == (
            _id(con, "beatriz"), _id(con, "mario")), setor
    assert (resp["PROTESTO"]["titular"], resp["PROTESTO"]["substituto"]) == (
        _id(con, "elisa"), _id(con, "mario"))
    assert (resp["GESTAO"]["titular"], resp["GESTAO"]["substituto"]) == (
        _id(con, "mario"), None)
    assert (resp["TI"]["titular"], resp["TI"]["substituto"]) == (
        _id(con, "alberto"), _id(con, "mario"))


# ------------------------------------------------------ a trava do cancelamento


def test_cancelamento_com_a_matricula_de_um_termo_vivo_fica_retido(con, monkeypatch):
    """Mesmo com um `sirc_remessa` que não traga a trava (a versão instalada)."""
    import sirc_remessa
    vivo = _assento(con, especie="OBITO", numero=1981, data_ato="2026-09-24")
    morto = _assento(con, especie="OBITO", numero=1981, data_ato="2026-09-23",
                     situacao="CANCELADO")
    con.execute("UPDATE rc_assentos SET matricula='M' WHERE id IN (?, ?)", (vivo, morto))
    monkeypatch.setattr(sirc_remessa, "pendentes_de_cancelamento", lambda c: [
        {"id": morto, "numero": 1981, "nome": "ISAIAS", "matricula": "M",
         "data_ato": "2026-09-23"}])
    canc = _regras(GC.conferir(con, HOJE), "SIRC_CANCELAMENTO")
    assert len(canc) == 1 and canc[0]["gravidade"] == "ATENCAO"
    assert "RETIDO" in canc[0]["detalhe"] and str(vivo) in canc[0]["detalhe"]


# ------------------------------------------------------ camada 2: cada ato


def _matricula(con, numero="9001"):
    return int(con.execute(
        "INSERT INTO ri_matriculas (numero, criado_em) VALUES (?, ?)",
        (numero, AGORA)).lastrowid)


def _ri_ato(con, mid, *, tipo="R", numero=1, h="h1", anterior=None,
            lavrado="2026-09-20T10:00:00", auditado=True):
    aid = int(con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, hash_ato, hash_anterior,
               lavrado_em, natureza_titulo) VALUES (?,?,?,?,?,?, 'COMPRA E VENDA')""",
        (mid, tipo, numero, h, anterior, lavrado)).lastrowid)
    if auditado:
        con.execute("INSERT INTO audit_logs (ts, action, entity_id) VALUES (?, 'RI_ATO_LAVRADO', ?)",
                    (lavrado, aid))
    return aid


def test_termo_repetido_entre_vivos_e_critico_e_o_cancelado_nao_conta(con):
    _assento(con, numero=500, data_ato="2026-09-20")
    _assento(con, numero=500, data_ato="2026-09-21", situacao="CANCELADO")
    assert _regras(GC.conferir(con, HOJE), "NUMERACAO") == []
    _assento(con, numero=500, data_ato="2026-09-22")
    rep = [a for a in _regras(GC.conferir(con, HOJE), "NUMERACAO") if ":rep:" in a["chave"]]
    assert len(rep) == 1 and rep[0]["gravidade"] == "CRITICO"


def test_salto_na_serie_do_rcpn(con):
    _assento(con, numero=700, data_ato="2026-09-20")
    _assento(con, numero=702, data_ato="2026-09-21")
    salto = [a for a in _regras(GC.conferir(con, HOJE), "NUMERACAO") if ":salto:" in a["chave"]]
    assert salto and "701" in salto[0]["titulo"]


def test_corrente_de_hash_quebrada_no_ri(con):
    mid = _matricula(con)
    _ri_ato(con, mid, numero=1, h="AAA")
    _ri_ato(con, mid, tipo="AV", numero=2, h="BBB", anterior="AAA")
    assert _regras(GC.conferir(con, HOJE), "CORRENTE_RI") == []
    _ri_ato(con, mid, tipo="AV", numero=3, h="CCC", anterior="XXX")
    assert len(_regras(GC.conferir(con, HOJE), "CORRENTE_RI")) == 1


def test_numero_repetido_na_matricula(con):
    mid = _matricula(con)
    _ri_ato(con, mid, numero=1, h="A")
    _ri_ato(con, mid, tipo="AV", numero=1, h="B", anterior="A")
    num = [a for a in _regras(GC.conferir(con, HOJE), "NUMERACAO") if a["chave"].startswith("NUM_RI")]
    assert len(num) == 1 and num[0]["setor"] == "RI_QUALIFICACAO"


def test_ato_sem_auditoria_entrou_por_fora(con):
    mid = _matricula(con)
    _ri_ato(con, mid, numero=1, h="A")
    _ri_ato(con, mid, tipo="AV", numero=2, h="B", anterior="A", auditado=False)
    # 06/10/2026: regra RETIRADA da conferência por ordem do oficial («deixe apenas os
    # fundamentais»). A regra continua sabendo achar; a conferência é que não a entrega mais.
    assert [a["titulo"][:4] for a in GC.regra_ato_por_fora(con, HOJE)] == ["AV-2"]
    assert _regras(GC.conferir(con, HOJE), "ATO_POR_FORA") == []


def test_registro_sem_prenotacao_amarrada(con):
    mid = _matricula(con)
    aid = _ri_ato(con, mid, numero=1, h="A")
    # 06/10/2026: regra RETIRADA da conferência por ordem do oficial («deixe apenas os
    # fundamentais»). A regra continua sabendo achar; a conferência é que não a entrega mais.
    assert len(GC.regra_registro_sem_prenotacao(con, HOJE)) == 1
    assert _regras(GC.conferir(con, HOJE), "REGISTRO_SEM_PRENOTACAO") == []
    con.execute("""INSERT INTO ri_protocolos (numero, data_prenotacao, ato_id, criado_em)
                   VALUES (11600, '2026-09-15', ?, ?)""", (aid, AGORA))
    assert GC.regra_registro_sem_prenotacao(con, HOJE) == []


def test_selo_que_o_razao_nao_conhece(con):
    aid = _assento(con, data_ato="2026-09-20")
    con.execute("""INSERT INTO rc_atos (assento_id, tipo, selo, data_ato, criado_em)
                   VALUES (?, 'AVERBACAO', 'AVERBA000000XXXXXXXXXXXXXX99', '2026-09-20', ?)""",
                (aid, AGORA))
    # 06/10/2026: regra RETIRADA da conferência por ordem do oficial («deixe apenas os
    # fundamentais»). A regra continua sabendo achar; a conferência é que não a entrega mais.
    orfaos = GC.regra_selo_orfao(con, HOJE)
    assert len(orfaos) == 1 and orfaos[0]["setor"] == "RCPN"
    assert _regras(GC.conferir(con, HOJE), "SELO_ORFAO") == []


def test_etiqueta_inteira_na_coluna_confere_cada_codigo_de_dentro(con):
    """A escritura 780: a célula guarda o texto de dois selos que ESTÃO no razão."""
    aid = _assento(con, data_ato="2026-09-20")
    for n in ("ATANOT000000MNLIR1DE5DYD6047", "ATANOT000000HJOK3CMTG0WMBU02"):
        con.execute("INSERT INTO sd_selos (numero, obtido_em) VALUES (?, ?)", (n, AGORA))
    etiqueta = ("PODER JUDICIÁRIO – TJMA SELO: ATANOT000000MNLIR1DE5DYD6047 17/09/2026; "
                "PODER JUDICIÁRIO – TJMA SELO: ATANOT000000HJOK3CMTG0WMBU02 17/09/2026")
    con.execute("""INSERT INTO rc_atos (assento_id, tipo, selo, data_ato, criado_em)
                   VALUES (?, 'AVERBACAO', ?, '2026-09-20', ?)""", (aid, etiqueta, AGORA))
    assert _regras(GC.conferir(con, HOJE), "SELO_ORFAO") == []


def test_cpf_que_nao_fecha_o_digito(con):
    mid = _matricula(con)
    aid = _ri_ato(con, mid, numero=1, h="A")
    for nome, doc in (("BOM", "000.000.044-21"), ("RUIM", "123.456.789-00")):
        con.execute("""INSERT INTO ri_partes (matricula_id, ato_id, nome, documento_tipo,
                       documento_numero) VALUES (?, ?, ?, 'CPF', ?)""", (mid, aid, nome, doc))
    docs = _regras(GC.conferir(con, HOJE), "DOCUMENTO_INVALIDO")
    assert [a["titulo"] for a in docs] == ["CPF inválido de RUIM"]


# ------------------------------------------------------ camada 3: o dinheiro


def _caixa(con, *, data="2026-09-20", fechado=True, conferido=None, dif="0,00", just=None):
    return int(con.execute(
        """INSERT INTO cx_caixas (data, operador_nome, aberto_em, fechado_em, situacao,
               conferido_por, diferenca, justificativa) VALUES (?,?,?,?,?,?,?,?)""",
        (data, "ELISA", data + "T08:00:00", data + "T17:00:00" if fechado else None,
         "FECHADO" if fechado else "ABERTO", conferido, dif, just)).lastrowid)


def test_caixa_fechado_que_fecha_vai_para_o_visto_do_oficial(con):
    _caixa(con)
    _caixa(con, data="2026-09-21", conferido=1)
    conf = _regras(GC.conferir(con, HOJE), "CAIXA_PRONTO_PARA_VISTO")
    assert len(conf) == 1 and conf[0]["setor"] == "GESTAO"
    assert _regras(GC.conferir(con, HOJE), "CAIXA_COM_PONTOS") == []


def test_o_agente_refaz_a_conta_e_aponta_o_troco_guardado(con):
    cid = _caixa(con, dif="-300,00", just="retirei o troco")
    con.execute("""UPDATE cx_caixas SET saldo_inicial='300,00', valor_esperado='300,00',
                       valor_contado='0,00' WHERE id=?""", (cid,))
    con.execute("""INSERT INTO cx_lancamentos (caixa_id, data, natureza, sentido, descricao,
                       valor, criado_em) VALUES (?, '2026-09-20', 'RECEBIMENTO', 'ENTRADA',
                       'CERTIDAO', '50,00', ?)""", (cid, AGORA))
    pontos = _regras(GC.conferir(con, HOJE), "CAIXA_COM_PONTOS")[0]["titulo"]
    assert "igual ao troco inicial" in pontos and "retirei o troco" in pontos
    assert "sem forma de pagamento" in pontos
    assert _regras(GC.conferir(con, HOJE), "CAIXA_PRONTO_PARA_VISTO") == []


def test_diferenca_de_caixa_sem_justificativa(con):
    _caixa(con, conferido=1, dif="-300,00")
    _caixa(con, data="2026-09-21", conferido=1, dif="-300,00", just="saldo inicial")
    assert len(_regras(GC.conferir(con, HOJE), "CAIXA_DIFERENCA")) == 1


def test_caixa_esquecido_aberto(con):
    _caixa(con, fechado=False)
    assert len(_regras(GC.conferir(con, HOJE), "CAIXA_ABERTO")) == 1


def _selo(con, numero, total, *, isento=False, dia="2026-09-20", atr="RCPN"):
    marca = " Selo Isento" if isento else ""
    texto = (f"Poder Judiciário – TJMA. Selo: {numero}, 20/09/2026 10:00:00, Ato: 14.5.1,"
             f"{marca} Total R$ {total} Emol R$ {total} Consulte em https://selo.tjma.jus.br")
    con.execute("""INSERT INTO sd_selos (numero, texto, atribuicao, obtido_em, usado_em)
                   VALUES (?,?,?,?,?)""", (numero, texto, atr, dia, dia + "T10:00:00"))


def test_fechamento_do_mes_selos_contra_caixa(con):
    _selo(con, "CERTID000000AAAAAAAAAAAAAA01", "500,00")
    _selo(con, "CERTID000000AAAAAAAAAAAAAA02", "900,00", isento=True)
    fech = _regras(GC.conferir(con, HOJE), "FECHAMENTO_DO_MES")
    assert len(fech) == 1 and "R$ 500,00" in fech[0]["titulo"] and fech[0]["setor"] == "GESTAO"
    con.execute("""INSERT INTO cx_lancamentos (data, natureza, sentido, valor, criado_em)
                   VALUES ('2026-09-20', 'RECEBIMENTO', 'ENTRADA', '500,00', ?)""", (AGORA,))
    assert _regras(GC.conferir(con, HOJE), "FECHAMENTO_DO_MES") == []


# ------------------------------------------------------ o corte de 10/09/2026


def test_ato_anterior_a_10_de_setembro_nao_vira_tarefa(con):
    """«não crie tarefas para atos praticados antes de 10 de setembro de 2026»."""
    _assento(con, numero=1, data_ato="2026-09-09", cor="Indígena")
    _assento(con, numero=2, data_ato="2026-09-10")
    achados = GC.conferir(con, HOJE)
    sirc = _regras(achados, "SIRC")
    assert [a["chave"].split(":")[2] for a in sirc] == [
        str(con.execute("SELECT id FROM rc_assentos WHERE numero=2").fetchone()[0])]
    assert _regras(achados, "FUNAI") == []
    assert [a for a in _regras(achados, "CRC") if "acervo" in a["chave"]] == []


def test_prenotacao_anterior_ao_corte_nao_vira_tarefa(con):
    con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, data_limite,
               situacao, criado_em) VALUES (11534, '1A', '2026-07-17',
               '2026-08-06', 'ABERTO', ?)""", (AGORA,))
    assert _regras(GC.conferir(con, HOJE), "PRENOTACAO_VENCIDA") == []


def test_a_doi_comeca_em_setembro_e_nao_em_agosto(con):
    chaves = {a["chave"] for a in GC.conferir(con, date(2026, 10, 25))
              if a["regra"] == "DOI"}
    assert chaves == {"DOI:2026-09"}


def _doi_de_setembro(con) -> dict:
    doi = [a for a in GC.conferir(con, date(2026, 10, 25)) if a["regra"] == "DOI"]
    assert len(doi) == 1
    return doi[0]


def test_a_doi_conta_o_registro_do_ri_e_nao_sugere_negativa(con):
    """21/10/2026: setembro tinha compra e venda e doações registradas no RI,
    e o achado mandava «conferir se cabe declaração negativa» — ele só
    contava as escrituras das Notas. O registro (R) conta; a averbação não."""
    bd = banco(con)
    mid = _matricula(con, "9002")
    bd.escrever(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, hash_ato,
               lavrado_em, natureza_titulo) VALUES (%s, 'R', 1, '2026-09-28',
               'hx', '2026-09-28T10:00:00', 'COMPRA E VENDA')""", (mid,))
    bd.escrever(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, hash_ato,
               hash_anterior, lavrado_em, natureza_titulo) VALUES (%s, 'AV', 2,
               '2026-09-28', 'hy', 'hx', '2026-09-28T11:00:00',
               'CANCELAMENTO DE HIPOTECA')""", (mid,))
    doi = _doi_de_setembro(con)
    assert "1 registro(s) no Registro de Imóveis" in doi["detalhe"]
    assert "negativa" not in doi["detalhe"].replace("não cabe negativa", "")
    assert doi["setor"] == "RI"


def test_so_averbacao_e_registro_cancelado_no_mes_ainda_pedem_a_negativa(con):
    """A averbação não transmite e o registro cancelado não vale: com só eles
    no mês, o achado continua mandando conferir a negativa, e é das Notas."""
    bd = banco(con)
    mid = _matricula(con, "9003")
    bd.escrever(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, hash_ato,
               lavrado_em, natureza_titulo, cancelado) VALUES (%s, 'R', 1,
               '2026-09-28', 'hc', '2026-09-28T10:00:00', 'DOACAO', 1)""", (mid,))
    bd.escrever(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, hash_ato,
               hash_anterior, lavrado_em, natureza_titulo) VALUES (%s, 'AV', 2,
               '2026-09-29', 'hd', 'hc', '2026-09-29T10:00:00',
               'CANCELAMENTO DE HIPOTECA')""", (mid,))
    doi = _doi_de_setembro(con)
    assert "conferir se cabe declaração negativa" in doi["detalhe"]
    assert "registro(s)" not in doi["detalhe"]
    assert doi["setor"] == "NOTAS"


def test_escritura_com_imovel_em_lavratura_no_mes_vira_aviso_e_nao_conta(con):
    """A escritura «em lavratura» pode ter sido assinada no papel: não conta
    como ato, mas o achado avisa. Com escritura lavrada e registro no RI no
    mesmo mês, os dois aparecem e o achado continua das Notas."""
    bd = banco(con)
    for situacao in ("EM_LAVRATURA", "LAVRADO"):
        bd.escrever(
            """INSERT INTO nt_atos (tipo, data, situacao, com_imovel, criado_em)
               VALUES ('ESCRITURA', '2026-09-20', %s, 1, %s)""", (situacao, AGORA))
    mid = _matricula(con, "9004")
    bd.escrever(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, hash_ato,
               lavrado_em, natureza_titulo) VALUES (%s, 'R', 1, '2026-09-28',
               'he', '2026-09-28T10:00:00', 'COMPRA E VENDA')""", (mid,))
    doi = _doi_de_setembro(con)
    assert "1 registro(s) no Registro de Imóveis" in doi["detalhe"]
    assert "1 escritura(s) com imóvel lavrada(s) nas Notas" in doi["detalhe"]
    assert "Há 1 escritura(s) com imóvel ainda «em lavratura»" in doi["detalhe"]
    assert doi["setor"] == "NOTAS"


def test_obito_anterior_ao_corte_fica_fora_da_lista_do_mes(con):
    _assento(con, especie="OBITO", numero=1979, nome="ANTES", data_ato="2026-09-05")
    _assento(con, especie="OBITO", numero=1980, nome="DEPOIS", data_ato="2026-09-20")
    detalhe = _regras(GC.conferir(con, HOJE), "OBITO_MENSAL")[0]["detalhe"]
    assert "DEPOIS" in detalhe and "ANTES" not in detalhe


def test_rcpn_reveza_entre_elisa_e_debora(casa_inteira, sirc_como_tarefa):
    """Duas tarefas do RCPN, uma para cada — e a outra de substituta."""
    con = casa_inteira
    # 06/10/2026: a FUNAI deixou de virar tarefa (só o que pode gerar responsabilidade
    # civil), e era ela a segunda tarefa do RCPN aqui. A segunda agora é o CPF inválido.
    GR.aplicar_distribuicao(con)
    resp = GR.inferir_responsaveis(con)
    achados = [GC._achado("SIRC:1", "SIRC", "VENCIDO", "RCPN", "SIRC"),
               GC._achado("DOC:rc_pessoas:1", "DOCUMENTO_INVALIDO", "ATENCAO", "RCPN", "CPF")]
    GR.sincronizar_tarefas(con, achados, resp, HOJE)
    donos = {r["source_ref"]: (r["assigned_user_id"], r["backup_user_id"])
             for r in con.execute(
                 """SELECT source_ref, assigned_user_id, backup_user_id FROM tasks
                     WHERE source_type='GESTOR' AND sector='RCPN'""")}
    elisa, debora = _id(con, "elisa"), _id(con, "debora")
    assert {d for d, _ in donos.values()} == {elisa, debora}
    for dono, substituto in donos.values():
        assert {dono, substituto} == {elisa, debora}


def test_titulo_e_ato_final_vao_para_a_qualificacao(casa_inteira):
    con = casa_inteira
    con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, data_limite,
               situacao, criado_em) VALUES (11570, '1A', '2026-09-11',
               '2026-10-01', 'ABERTO', ?)""", (AGORA,))
    GR.rodar(con, HOJE)
    t = con.execute(
        """SELECT assigned_user_id, backup_user_id, sector FROM tasks
            WHERE source_ref='GESTOR:PRENOTACAO_VENCIDA:RI_QUALIFICACAO'""").fetchone()
    assert (t["assigned_user_id"], t["backup_user_id"]) == (
        _id(con, "beatriz"), _id(con, "mario"))
    assert t["sector"] == "Registro de Imóveis"


def test_a_cobranca_diz_quem_substitui(casa_inteira, sirc_como_tarefa):
    con = casa_inteira
    _assento(con, data_ato="2026-09-15")
    GR.rodar(con, HOJE)
    # desde 12/10/2026 a cobrança é o relato do dia, e não nota na tarefa
    nota = con.execute(
        "SELECT corpo FROM rd_relatos WHERE origem='GESTOR_COBRANCA'").fetchone()[0]
    assert "cobre:" in nota


def test_login_que_nao_existe_nao_vira_palpite_calado(con):
    """Sem a Elisa no cadastro, o RCPN não é distribuído — e o relatório diz."""
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    faltou = GR.aplicar_distribuicao(con)
    assert any("elisa" in f for f in faltou)
    assert con.execute(
        "SELECT 1 FROM ge_responsaveis WHERE setor='RCPN' AND origem='OFICIAL'"
    ).fetchone() is None


def test_tarefa_com_quem_saiu_do_setor_passa_adiante(casa_inteira, sirc_como_tarefa):
    con = casa_inteira
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    mario = _id(con, "mario")
    con.execute(
        """INSERT INTO tasks (source_type, source_ref, title, priority, status,
               assigned_user_id, created_at, updated_at)
           VALUES ('GESTOR', 'GESTOR:SIRC:RCPN', 'x', 'MEDIA', 'ABERTA', ?, ?, ?)""",
        (mario, AGORA, AGORA))
    _assento(con, data_ato="2026-09-15")
    GR.rodar(con, HOJE)
    dono = con.execute("SELECT assigned_user_id FROM tasks WHERE source_ref='GESTOR:SIRC:RCPN'"
                       ).fetchone()[0]
    assert dono in (_id(con, "elisa"), _id(con, "debora"))


def test_relatorio_sai_com_os_achados(con, tmp_path):
    _assento(con, data_ato="2026-09-15", nome="OLIVIA")
    resumo = GR.rodar(con, HOJE, pasta_relatorio=tmp_path)
    texto = Path(resumo["relatorio"]).read_text(encoding="utf-8")
    assert "OLIVIA" in texto and "Conferência da casa" in texto


def test_minuta_pendurada_em_ficha_encerrada(con):
    viva = _matricula(con, "4020")
    fechada = _matricula(con, "904020")
    con.execute("UPDATE ri_matriculas SET encerrada = 1, situacao = 'ENCERRADA' WHERE id = ?",
                (fechada,))
    for mid in (viva, fechada):
        con.execute("""INSERT INTO ri_minutas (matricula_id, tipo, numero_pretendido, teor,
                           criado_em) VALUES (?, 'AV', 3, 'TEOR', ?)""", (mid, AGORA))
    achados = _regras(GC.conferir(con, HOJE), "MINUTA_EM_FICHA_ENCERRADA")
    assert len(achados) == 1 and "904020" in achados[0]["titulo"]
    assert achados[0]["setor"] == "RI_QUALIFICACAO"
    con.execute("UPDATE ri_minutas SET situacao = 'DESCARTADA'")
    assert _regras(GC.conferir(con, HOJE), "MINUTA_EM_FICHA_ENCERRADA") == []


def test_disco_quase_cheio_vira_achado_da_ti_e_nao_apaga_nada(con, tmp_path, monkeypatch):
    import shutil
    from collections import namedtuple
    Uso = namedtuple("Uso", "total used free")
    (tmp_path / "cartorio_gestao.sqlite3.bak_x").write_bytes(b"0" * 2048)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Uso(500 * 1024 ** 3, 0, 1 * 1024 ** 3))
    achados = _regras(GC.conferir(con, HOJE, pasta_dados=tmp_path), "DISCO")
    assert len(achados) == 1 and achados[0]["gravidade"] == "CRITICO"
    assert achados[0]["setor"] == "TI" and "bak_x" in achados[0]["detalhe"]
    assert (tmp_path / "cartorio_gestao.sqlite3.bak_x").exists()
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Uso(500 * 1024 ** 3, 0, 80 * 1024 ** 3))
    assert _regras(GC.conferir(con, HOJE, pasta_dados=tmp_path), "DISCO") == []


def test_o_usuario_teste_que_o_oficial_mandou_manter_nao_e_cobrado(con):
    con.execute("""INSERT INTO users (username, full_name, password_salt, password_hash, role,
                       active, created_at) VALUES ('teste', 'teste', 's', 'h', 'USER', 1, ?)""",
                (AGORA,))
    con.execute("""INSERT INTO users (username, full_name, password_salt, password_hash, role,
                       active, created_at) VALUES ('test', 'test', 's', 'h', 'USER', 1, ?)""",
                (AGORA,))
    achados = _regras(GC.conferir(con, HOJE), "DADO_DE_TESTE")
    assert [a["titulo"] for a in achados] == ["Usuário de teste «test» ativo na produção"]


def test_caixa_esquecido_e_cobrado_de_quem_o_abriu(con):
    vid = con.execute("""INSERT INTO users (username, full_name, password_salt, password_hash,
                             role, active, created_at)
                         VALUES ('elisa', 'ELISA EXEMPLO LIMA', 's', 'h', 'USER', 1, ?)""",
                      (AGORA,)).lastrowid
    _caixa(con, fechado=False)                      # operador «ELISA», só o primeiro nome
    achado = _regras(GC.conferir(con, HOJE), "CAIXA_ABERTO")[0]
    assert achado["setor"] == f"PESSOA:{vid}" and achado["gravidade"] == "CRITICO"
    GR.rodar(con, HOJE)
    # 06/10/2026: caixa é dinheiro da casa, não dano a terceiro — continua achado
    # (relatório e aviso vermelho da tela), mas não vira mais tarefa.
    assert con.execute("""SELECT count(*) FROM tasks
                           WHERE source_ref LIKE 'GESTOR:CAIXA_ABERTO:%'""").fetchone()[0] == 0


def test_as_14h_o_caixa_de_hoje_aberto_vira_tarefa_critica(con, monkeypatch):
    from datetime import datetime as dt
    hoje = date.today()
    _caixa(con, data=hoje.isoformat(), fechado=False)
    monkeypatch.setattr(GC, "_relogio", lambda: dt(hoje.year, hoje.month, hoje.day, 13, 59))
    assert _regras(GC.conferir(con, hoje), "CAIXA_DO_DIA_ABERTO") == []
    monkeypatch.setattr(GC, "_relogio", lambda: dt(hoje.year, hoje.month, hoje.day, 14, 0))
    achados = _regras(GC.conferir(con, hoje), "CAIXA_DO_DIA_ABERTO")
    assert len(achados) == 1 and achados[0]["gravidade"] == "CRITICO"
    assert "14:00" in achados[0]["titulo"]
    # conferência de outro dia não sabe que horas eram
    assert _regras(GC.conferir(con, date(2026, 9, 20)), "CAIXA_DO_DIA_ABERTO") == []


def test_nome_com_acento_acha_a_pessoa_do_caixa(con):
    lid = con.execute("""INSERT INTO users (username, full_name, password_salt, password_hash,
                             role, active, created_at)
                         VALUES ('beatriz', 'Beatriz Exemplo de Souza', 's', 'h',
                                 'USER', 1, ?)""", (AGORA,)).lastrowid
    assert GC._pessoa_do_operador(con, "Beatriz Exemplo de Souza") == f"PESSOA:{lid}"
    assert GC._pessoa_do_operador(con, "BEATRIZ EXEMPLO DE SOUZA") == f"PESSOA:{lid}"
    assert GC._pessoa_do_operador(con, "Ninguém") == "GESTAO"


def test_prenotacao_e_cobrada_antes_de_vencer(con):
    for numero, limite in ((1, "2026-10-09"), (2, "2026-11-30"), (3, "2026-10-05")):
        con.execute("""INSERT INTO ri_protocolos (numero, data_prenotacao, data_limite,
                           situacao, apresentante, criado_em)
                       VALUES (?, '2026-09-15', ?, 'ABERTO', 'FULANO', ?)""",
                    (numero, limite, AGORA))
    a_vencer = _regras(GC.conferir(con, HOJE), "PRENOTACAO_A_VENCER")
    assert [a["chave"] for a in a_vencer] == ["PRENOT_VENCE:1"]
    assert a_vencer[0]["setor"] == "RI_QUALIFICACAO" and "09/10" in a_vencer[0]["titulo"]


def test_cobra_a_tarefa_manual_vencida_da_equipe_sem_mudar_a_prioridade(con):
    def usuario(login, papel):
        return con.execute("""INSERT INTO users (username, full_name, password_salt,
                                 password_hash, role, active, created_at)
                              VALUES (?, ?, 's', 'h', ?, 1, ?)""",
                           (login, login.upper(), papel, AGORA)).lastrowid
    gente, chefe = usuario("escrevente_x", "USER"), usuario("chefe_x", "ADMIN")
    for dono in (gente, chefe):
        con.execute("""INSERT INTO tasks (source_type, title, priority, status, due_date,
                           assigned_user_id, created_at, updated_at)
                       VALUES ('MANUAL', 'pedir certidão', 'MEDIA', 'ABERTA', '2026-10-01', ?, ?, ?)""",
                    (dono, AGORA, AGORA))
    assert GR.cobrar_vencidas(con, HOJE) == 1
    t = con.execute("SELECT priority FROM tasks WHERE assigned_user_id = ?", (gente,)).fetchone()
    assert t[0] == "MEDIA"
    # desde 12/10/2026 a segunda rodada RENOVA o relato do dia em vez de anotar
    # de novo: continua um relato só por pessoa, e nenhuma nota na tarefa
    GR.cobrar_vencidas(con, HOJE)
    assert con.execute("SELECT count(*) FROM rd_relatos WHERE origem='GESTOR_COBRANCA'"
                       ).fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM task_history WHERE action='NOTA'").fetchone()[0] == 0


def test_a_mesma_chave_com_regra_nova_atualiza_a_regra_gravada(con):
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    velho = {"chave": "CAIXA_CONF:1", "regra": "CAIXA_NAO_CONFERIDO", "gravidade": "ATENCAO",
             "setor": "GESTAO", "titulo": "t", "detalhe": "", "prazo": None, "fundamento": ""}
    GR.gravar_achados(con, [velho], HOJE)
    GR.gravar_achados(con, [dict(velho, regra="CAIXA_PRONTO_PARA_VISTO")], HOJE)
    assert con.execute("SELECT regra FROM ge_achados WHERE chave='CAIXA_CONF:1'"
                       ).fetchone()[0] == "CAIXA_PRONTO_PARA_VISTO"


def test_ato_sem_imagem_nova_cobra_em_7_dias_e_notifica_o_administrador(con, tmp_path):
    import os
    mid = _matricula(con, "4020")
    _ri_ato(con, mid, numero=1, lavrado="2026-09-28T15:00:00")
    # a imagem existe, mas é ANTERIOR ao ato — a «Importação pasta 7» de 03/10
    # regravou a data do cadastro; a do arquivo é a que vale
    img = tmp_path / "atual.pdf"
    img.write_bytes(b"%PDF")
    antes = __import__("datetime").datetime(2026, 9, 27, 17, 0).timestamp()
    os.utime(img, (antes, antes))
    con.execute("UPDATE ri_matriculas SET digi_em='2026-10-03T12:51:00', digi_path=? WHERE id=?",
                (str(img), mid))
    dentro = _regras(GC.conferir(con, date(2026, 10, 4)), "DIGITALIZACAO_DA_FICHA")
    assert len(dentro) == 1 and dentro[0]["gravidade"] == "PRAZO" and "05/10" in dentro[0]["titulo"]
    assert _regras(GC.conferir(con, date(2026, 10, 4)), "DIGITALIZACAO_ATRASADA") == []
    fora = GC.conferir(con, HOJE)
    assert _regras(fora, "DIGITALIZACAO_DA_FICHA")[0]["gravidade"] == "CRITICO"
    adm = _regras(fora, "DIGITALIZACAO_ATRASADA")
    assert len(adm) == 1 and adm[0]["setor"] == "GESTAO"
    # imagem nova, depois do ato: sai tudo
    depois = __import__("datetime").datetime(2026, 10, 6, 9, 0).timestamp()
    os.utime(img, (depois, depois))
    assert _regras(GC.conferir(con, HOJE), "DIGITALIZACAO_DA_FICHA") == []


def test_marcador_inserir_no_teor_da_ficha_e_critico(con):
    mid = _matricula(con, "4019")
    con.execute("""UPDATE ri_matriculas SET data_abertura='2026-09-23',
                       teor='CCIR: [INSERIR APÓS APRESENTAÇÃO DO DOCUMENTO]. CAR: 123' WHERE id=?""",
                (mid,))
    achados = [a for a in _regras(GC.conferir(con, HOJE), "MODELO_NAO_PREENCHIDO")
               if a["chave"] == f"MARCADOR:ri_matriculas:{mid}"]
    assert len(achados) == 1 and "[INSERIR" in achados[0]["detalhe"]

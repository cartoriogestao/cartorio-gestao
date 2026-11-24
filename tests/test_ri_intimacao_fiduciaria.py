"""A INTIMAÇÃO DO DEVEDOR FIDUCIANTE NO RI (RI013-I1, 24/11/2026).

O QUE ESTES TESTES GUARDAM
    - autuar suspende a prenotação com `INTIMACAO_FIDUCIARIA`; ela continua ABERTA e na cláusula
      das certidões da matrícula (TJMA 723, § 3º), e não se retoma à mão;
    - cada intimando traz o endereço do contrato e o do imóvel, tirados do acervo (TJMA 724, § 5º);
    - avalista e fiador só a pedido expresso (722, § 5º); a Central dispensa a representação (722, § 4º);
    - pelo correio, 3 tentativas (724, § 2º); hora certa só depois de duas procuras e da suspeita;
    - a purga: 15 dias corridos da última intimação, começando no primeiro dia útil e terminando em
      dia útil (art. 26, § 1º; Lei 6.015, art. 9º, § 3º); ou úteis, se o titular escolher;
    - o edital: só depois das negativas em todos os endereços, 15 dias depois do e-mail, 3 publicações;
    - purga abaixo da projeção é recusada; aviso ao credor em 3 dias úteis (725);
    - a certidão de purgação ou de não purgação encerra a prenotação (723);
    - o `GetDetalhesIN_V3` da Central entra no modelo pelos nomes do contrato.

Dados fictícios: Cidade Exemplo, Banco Exemplo, Maria Exemplo.
"""
from __future__ import annotations

from datetime import date

import pytest

import ri_intimacao_fiduciaria as INT
import ri_prenotacao_prazo as PRAZO
from bd_nativo import banco
from ri_web import clausula_html_prenotacoes_abertas, prenotacoes_abertas_da_matricula

AGORA = "2026-11-24T10:00:00"
HOJE = date(2026, 11, 24)
COMUM = {"agora": AGORA, "usuario": "mario"}
TODOS = [r["chave"] for r in INT.REQUISITOS if r["chave"] != "pj"]


@pytest.fixture()
def db(cg_casa):
    return cg_casa["db"]


def _matricula(con, numero="5001") -> int:
    bd = banco(con)
    mid = int(bd.escrever(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha, origem, criado_em,
               logradouro, numero_predial, bairro, cidade, uf, cep)
           VALUES (%s,'2','2','ATIVA','ESTRUTURADA','MANUAL',%s,'Rua das Flores','120','Centro',
                   'Cidade Exemplo','MA','65000-000') RETURNING id""", (numero, AGORA))[0]["id"])
    ato = int(bd.escrever(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, natureza_titulo, teor, hash_ato, lavrado_em)
           VALUES (%s,'R',2,'2024-03-10','Alienação Fiduciária','R-2 ALIENAÇÃO FIDUCIÁRIA','h',%s)
           RETURNING id""", (mid, AGORA))[0]["id"])
    bd.escrever(
        """INSERT INTO ri_partes (matricula_id, ato_id, nome, nome_norm, documento_numero, qualificacao, papel,
               proprietario, proprietario_ativo)
           VALUES (%s,%s,'MARIA EXEMPLO','MARIA EXEMPLO','11122233344',
                   'brasileira, solteira, professora, residente e domiciliada na Rua do Contrato, 45, Bairro Novo, Cidade Exemplo/MA; e',
                   'DEVEDOR',1,1)""", (mid, ato))
    bd.escrever(
        """INSERT INTO ri_partes (matricula_id, ato_id, nome, nome_norm, documento_numero, papel, proprietario,
               proprietario_ativo) VALUES (%s,NULL,'JOSE PROPRIETARIO','JOSE PROPRIETARIO','55566677788',
               'PROPRIETARIO',1,1)""", (mid,))
    return mid


def _prenotacao(con, mid, numero=12001) -> int:
    return int(banco(con).escrever(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, data_limite, situacao, natureza_titulo,
               matricula_id, matricula_numero, criado_em)
           VALUES (%s,'1A','2026-11-20','2026-12-10','ABERTO','Requerimento de intimação',%s,'5001',%s)
           RETURNING id""", (numero, mid, AGORA))[0]["id"])


def _procedimento(db, *, ate="autuado", **kw):
    with db.transaction() as con:
        mid = _matricula(con)
        pid = _prenotacao(con, mid)
        iid = INT.autuar(con, protocolo_id=pid, credor_nome="BANCO EXEMPLO S.A.", ano=2026, hoje=HOJE,
                         contrato="CT-001", demonstrativo_valor="3.000,00", demonstrativo_data="2026-11-15",
                         projecao="31/12/2026; 3.500,00", **COMUM, **kw)["id"]
        if ate == "autuado":
            return iid, pid, mid
        INT.adicionar_intimando(con, iid, nome="Maria Exemplo", documento="111.222.333-44", papel="DEVEDOR",
                                enderecos="Rua Indicada, 10, Cidade Exemplo/MA", **COMUM)
        if ate == "com_devedor":
            return iid, pid, mid
        INT.qualificar(con, iid, resultado="POSITIVA", itens=TODOS, dia="2026-11-24", **COMUM)
    return iid, pid, mid


def _um(db, iid):
    with db.connect() as con:
        return INT.um(con, iid), INT.intimandos_de(con, iid)


def _protocolo(db, pid):
    with db.connect() as con:
        return dict(banco(con).um("SELECT * FROM ri_protocolos WHERE id=%s", (pid,)))


# ------------------------------------------------------------ a prenotação


def test_autuar_suspende_a_prenotacao_que_continua_aberta_nas_certidoes(db):
    iid, pid, mid = _procedimento(db)
    p = _protocolo(db, pid)
    assert p["situacao"] == "ABERTO" and p["prazo_suspenso_motivo"] == PRAZO.INTIMACAO_FIDUCIARIA
    with db.connect() as con:
        abertas = prenotacoes_abertas_da_matricula(con, mid, "5001")
    assert [x["id"] for x in abertas] == [pid]
    assert "12001" in clausula_html_prenotacoes_abertas(abertas)
    assert _um(db, iid)[0]["rotulo"] == "1/2026"


def test_a_prenotacao_nao_se_retoma_nem_se_suspende_a_mao_por_este_motivo(db):
    iid, pid, mid = _procedimento(db)
    with db.transaction() as con, pytest.raises(PRAZO.PrazoError):
        PRAZO.retomar(con, pid, quem="mario", hoje=HOJE)
    with db.transaction() as con:
        outra = _prenotacao(con, mid, numero=12002)
    with db.transaction() as con, pytest.raises(PRAZO.PrazoError):
        PRAZO.suspender(con, outra, motivo=PRAZO.INTIMACAO_FIDUCIARIA, quem="mario", hoje=HOJE)
    assert PRAZO.INTIMACAO_FIDUCIARIA not in PRAZO.MOTIVOS_MANUAIS


def test_prenotacao_ja_suspensa_por_outro_motivo_nao_recebe_o_procedimento(db):
    with db.transaction() as con:
        mid = _matricula(con)
        pid = _prenotacao(con, mid)
        PRAZO.suspender(con, pid, motivo="DUVIDA", quem="mario", hoje=HOJE)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="outro motivo"):
        INT.autuar(con, protocolo_id=pid, credor_nome="BANCO EXEMPLO", ano=2026, hoje=HOJE, **COMUM)


def test_uma_prenotacao_tem_um_procedimento_so(db):
    iid, pid, mid = _procedimento(db)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="já tem"):
        INT.autuar(con, protocolo_id=pid, credor_nome="BANCO EXEMPLO", ano=2026, hoje=HOJE, **COMUM)


# ------------------------------------------------------------ os intimandos e o acervo


def test_o_intimando_traz_o_endereco_do_contrato_e_o_do_imovel_do_acervo(db):
    iid, _, _ = _procedimento(db, ate="com_devedor")
    x = _um(db, iid)[1][0]
    origens = {e["origem"]: e["endereco"] for e in x["enderecos"]}
    assert origens[INT.CREDOR] == "Rua Indicada, 10, Cidade Exemplo/MA"
    assert origens[INT.CONTRATO].startswith("residente e domiciliada na Rua do Contrato, 45")
    assert origens[INT.IMOVEL] == "Rua das Flores, 120, Centro, Cidade Exemplo/MA, CEP 65000-000"


def test_o_proprietario_diverso_do_devedor_e_sugerido(db):
    iid, _, _ = _procedimento(db, ate="com_devedor")
    with db.connect() as con:
        sugeridos = INT.sugerir_proprietarios(con, iid)
    assert [s["nome"] for s in sugeridos] == ["JOSE PROPRIETARIO"]


def test_avalista_so_a_pedido_expresso_do_credor(db):
    iid, _, _ = _procedimento(db)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="722, § 5º"):
        INT.adicionar_intimando(con, iid, nome="Avalista Exemplo", papel="AVALISTA", enderecos="Rua A, 1", **COMUM)
    iid2, _, _ = _procedimento_outro(db, avalistas_a_pedido=True)
    with db.transaction() as con:
        INT.adicionar_intimando(con, iid2, nome="Avalista Exemplo", papel="AVALISTA", enderecos="Rua A, 1", **COMUM)


def _procedimento_outro(db, **kw):
    with db.transaction() as con:
        mid = _matricula(con, numero="5002")
        pid = _prenotacao(con, mid, numero=13001)
        iid = INT.autuar(con, protocolo_id=pid, credor_nome="BANCO EXEMPLO", ano=2026, hoje=HOJE, **COMUM, **kw)["id"]
    return iid, pid, mid


# ------------------------------------------------------------ a qualificação


def test_positiva_exige_os_requisitos_e_o_devedor(db):
    iid, _, _ = _procedimento(db)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="Faltam"):
        INT.qualificar(con, iid, resultado="POSITIVA", itens=TODOS[1:], dia="2026-11-24", **COMUM)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="devedor fiduciante"):
        INT.qualificar(con, iid, resultado="POSITIVA", itens=TODOS, dia="2026-11-24", **COMUM)


def test_pessoa_juridica_pede_o_representante_e_o_contrato_social(db):
    iid, _, _ = _procedimento(db, ate="com_devedor")
    with db.transaction() as con:
        pj = INT.adicionar_intimando(con, iid, nome="Empresa Exemplo Ltda", papel="TERCEIRO_FIDUCIANTE",
                                     pessoa_juridica=True, enderecos="Av. B, 2", **COMUM)["id"]
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="724, § 4º"):
        INT.qualificar(con, iid, resultado="POSITIVA", itens=TODOS, dia="2026-11-24", **COMUM)
    with db.transaction() as con:
        INT.corrigir_intimando(con, iid, pj, representante="Sócio Exemplo", **COMUM)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="724, § 4º"):
        INT.qualificar(con, iid, resultado="POSITIVA", itens=TODOS, dia="2026-11-24", **COMUM)
    with db.transaction() as con:
        INT.qualificar(con, iid, resultado="POSITIVA", itens=TODOS + ["pj"], dia="2026-11-24", **COMUM)
    assert _um(db, iid)[0]["situacao"] == INT.INTIMANDO


def test_a_exigencia_volta_a_qualificacao_e_a_negativa_recusa_a_prenotacao(db):
    iid, pid, _ = _procedimento(db, ate="com_devedor")
    with db.transaction() as con:
        INT.qualificar(con, iid, resultado="EXIGENCIA", motivo="Falta a planilha de projeção.", dia="2026-11-24", **COMUM)
    assert _um(db, iid)[0]["situacao"] == INT.EXIGENCIA
    with db.transaction() as con:
        INT.qualificar(con, iid, resultado="NEGATIVA", motivo="Contrato registrado em outra serventia.",
                       dia="2026-11-25", **COMUM)
    p = _protocolo(db, pid)
    assert _um(db, iid)[0]["situacao"] == INT.RECUSADO
    assert p["situacao"] == "RECUSADO" and not p["prazo_suspenso_desde"]


# ------------------------------------------------------------ as diligências e o prazo


def _endereco(x, origem):
    return next(e["id"] for e in x["enderecos"] if e["origem"] == origem)


def test_pelo_correio_o_ausente_pede_as_tres_tentativas(db):
    iid, _, _ = _procedimento(db, ate="qualificado")
    x = _um(db, iid)[1][0]
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="3 do carteiro"):
        INT.diligencia(con, iid, x["id"], meio="CORREIO", dia="2026-11-25", resultado="AUSENTE_3",
                       endereco_id=_endereco(x, INT.CREDOR), tentativas_carteiro=2, **COMUM)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="deste meio"):
        INT.diligencia(con, iid, x["id"], meio="CORREIO", dia="2026-11-25", resultado="NAO_ENCONTRADO",
                       endereco_id=_endereco(x, INT.CREDOR), **COMUM)
    with db.transaction() as con:
        INT.diligencia(con, iid, x["id"], meio="CORREIO", dia="2026-11-25", resultado="AUSENTE_3",
                       endereco_id=_endereco(x, INT.CREDOR), tentativas_carteiro=3, rastreio="AA123456789BR", **COMUM)


def test_hora_certa_so_depois_de_duas_procuras_e_da_suspeita(db):
    iid, _, _ = _procedimento(db, ate="qualificado")
    x = _um(db, iid)[1][0]
    e = _endereco(x, INT.CREDOR)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="duas procuras"):
        INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia="2026-11-25", resultado="SUSPEITA_OCULTACAO",
                       endereco_id=e, detalhe="Vizinhos dizem que se esconde.", **COMUM)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="suspeita de ocultação"):
        INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia="2026-11-25", resultado="HORA_CERTA",
                       endereco_id=e, quem_recebeu="Irmã", **COMUM)
    with db.transaction() as con:
        for d in ("2026-11-25", "2026-11-26"):
            INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia=d, resultado="NAO_ENCONTRADO", endereco_id=e, **COMUM)
        INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia="2026-11-26", resultado="SUSPEITA_OCULTACAO",
                       endereco_id=e, detalhe="Vizinhos dizem que se esconde; volta amanhã às 9h.", **COMUM)
        INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia="2026-11-27", resultado="HORA_CERTA",
                       endereco_id=e, quem_recebeu="Irmã, Joana Exemplo", **COMUM)
    i, lista = _um(db, iid)
    assert lista[0]["situacao"] == INT.INTIMADO and lista[0]["intimado_em"] == "2026-11-27"
    assert i["situacao"] == INT.PRAZO_PURGA


def test_o_prazo_conta_da_intimacao_do_ultimo_e_acaba_em_dia_util(db):
    iid, _, _ = _procedimento(db, ate="qualificado")
    with db.transaction() as con:
        INT.adicionar_intimando(con, iid, nome="João Exemplo", papel="CONJUGE", enderecos="Rua Indicada, 10", **COMUM)
    a, b = _um(db, iid)[1]
    with db.transaction() as con:
        INT.diligencia(con, iid, a["id"], meio="PESSOAL", dia="2026-12-01", resultado="INTIMADO",
                       endereco_id=_endereco(a, INT.CREDOR), quem_recebeu="A própria", **COMUM)
    assert _um(db, iid)[0]["situacao"] == INT.INTIMANDO
    with db.transaction() as con:
        INT.diligencia(con, iid, b["id"], meio="PESSOAL", dia="2026-12-10", resultado="INTIMADO",
                       endereco_id=_endereco(b, INT.CREDOR), quem_recebeu="O próprio", **COMUM)
    i = _um(db, iid)[0]
    # dia 1 = 11/12 (sexta); 15 corridos acabam em 25/12, Natal: passa a 28/12 (segunda).
    assert i["situacao"] == INT.PRAZO_PURGA and i["prazo_ate"] == "2026-12-28"


def test_a_contagem_em_dias_uteis_quando_o_titular_escolher():
    assert INT.fim_da_purga(date(2026, 12, 10), contagem="UTEIS") == date(2027, 1, 4)
    assert INT.fim_da_purga(date(2026, 12, 2)) == date(2026, 12, 17)


def test_intimando_novo_depois_do_prazo_volta_a_esperar_a_ultima_intimacao(db):
    iid, _, _ = _procedimento(db, ate="qualificado")
    x = _um(db, iid)[1][0]
    with db.transaction() as con:
        INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia="2026-12-01", resultado="INTIMADO",
                       endereco_id=_endereco(x, INT.CREDOR), quem_recebeu="A própria", **COMUM)
    assert _um(db, iid)[0]["situacao"] == INT.PRAZO_PURGA
    with db.transaction() as con:
        INT.adicionar_intimando(con, iid, nome="Pedro Exemplo", papel="CONJUGE", enderecos="Rua C, 3", **COMUM)
    i = _um(db, iid)[0]
    assert i["situacao"] == INT.INTIMANDO and not i["prazo_ate"]


# ------------------------------------------------------------ o edital


def test_o_edital_pede_as_negativas_o_email_e_tres_publicacoes(db):
    iid, _, _ = _procedimento(db, ate="qualificado")
    x = _um(db, iid)[1][0]
    with db.transaction() as con:
        INT.corrigir_intimando(con, iid, x["id"], email="maria@site-exemplo.invalid", **COMUM)
    x = _um(db, iid)[1][0]
    assert len(INT.faltas_para_o_edital(x)) == 3
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="não cabe"):
        INT.publicar_edital(con, iid, x["id"], dia="2026-12-01", veiculo="Jornal Exemplo", **COMUM)
    with db.transaction() as con:
        INT.diligencia(con, iid, x["id"], meio="CORREIO", dia="2026-11-25", resultado="MUDOU_SE",
                       endereco_id=_endereco(x, INT.CREDOR), **COMUM)
    assert len(INT.faltas_para_o_edital(_um(db, iid)[1][0])) == 3, "o correio que falha não basta (724, § 2º)"
    with db.transaction() as con:
        for origem in (INT.CREDOR, INT.CONTRATO, INT.IMOVEL):
            INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia="2026-11-26", resultado="NAO_ENCONTRADO",
                           endereco_id=_endereco(x, origem), **COMUM)
    assert INT.faltas_para_o_edital(_um(db, iid)[1][0]) == []
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="e-mail"):
        INT.publicar_edital(con, iid, x["id"], dia="2026-12-01", veiculo="Jornal Exemplo", **COMUM)
    with db.transaction() as con:
        INT.email_enviado(con, iid, x["id"], dia="2026-11-27", **COMUM)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="12/12/2026"):
        INT.publicar_edital(con, iid, x["id"], dia="2026-12-01", veiculo="Jornal Exemplo", **COMUM)
    with db.transaction() as con:
        for d in ("2026-12-14", "2026-12-15", "2026-12-16"):
            INT.publicar_edital(con, iid, x["id"], dia=d, veiculo="Jornal Exemplo", **COMUM)
    i, lista = _um(db, iid)
    assert lista[0]["situacao"] == INT.INTIMADO_EDITAL and lista[0]["intimado_em"] == "2026-12-16"
    assert i["situacao"] == INT.PRAZO_PURGA and i["prazo_ate"] == "2026-12-31"


def test_o_acervo_sem_endereco_dispensa_a_procura_com_o_motivo_escrito(db):
    iid, _, _ = _procedimento(db, ate="qualificado")
    with db.transaction() as con:
        novo = INT.adicionar_intimando(con, iid, nome="Pessoa Sem Acervo", papel="CONJUGE", enderecos="Rua D, 4",
                                       buscar_no_acervo=False, **COMUM)["id"]
    x = next(y for y in _um(db, iid)[1] if y["id"] == novo)
    assert any("contrato" in f for f in INT.faltas_para_o_edital(x))
    with db.transaction() as con:
        INT.acervo_sem_endereco(con, iid, novo, motivo="O contrato não traz o domicílio do cônjuge.", **COMUM)
    x = next(y for y in _um(db, iid)[1] if y["id"] == novo)
    assert not any("contrato" in f or "imóvel" in f for f in INT.faltas_para_o_edital(x))


# ------------------------------------------------------------ a purga e as certidões


def _intimar_todos(db, iid, dia="2026-12-01"):
    with db.transaction() as con:
        for x in INT.intimandos_de(con, iid):
            INT.diligencia(con, iid, x["id"], meio="PESSOAL", dia=dia, resultado="INTIMADO",
                           endereco_id=_endereco(x, INT.CREDOR), quem_recebeu="O próprio", **COMUM)


def test_a_purga_abaixo_da_projecao_e_recusada_e_a_certidao_encerra_a_prenotacao(db):
    iid, pid, mid = _procedimento(db, ate="qualificado")
    _intimar_todos(db, iid)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="projeção"):
        INT.purgar(con, iid, dia="2026-12-03", valor="3.000,00", forma="TRANSFERENCIA", **COMUM)
    with db.transaction() as con:
        feito = INT.purgar(con, iid, dia="2026-12-03", valor="3.500,00", forma="TRANSFERENCIA",
                           conta="Conta exemplo", **COMUM)
    assert feito["avisar_ate"] == "2026-12-08"   # 3 dias úteis: 04, 07 e 08/12
    i = _um(db, iid)[0]
    assert i["situacao"] == INT.PURGADA and "RECIBO" in INT.pecas_disponiveis(i, [])
    with db.transaction() as con:
        INT.certificar(con, iid, tipo="PURGACAO", dia="2026-12-03", hoje="2026-12-03", **COMUM)
    i = _um(db, iid)[0]
    p = _protocolo(db, pid)
    assert i["situacao"] == INT.ENCERRADO_PURGACAO
    assert p["situacao"] == "ENCERRADO" and not p["prazo_suspenso_desde"]
    assert "723" in p["motivo_encerramento"]
    with db.connect() as con:
        assert prenotacoes_abertas_da_matricula(con, mid, "5001") == []
        painel = INT.painel(con, hoje="2026-12-09")
    assert [x["id"] for x in painel["repasses"]] == [iid] and painel["repasses"][0]["atrasado"]
    with db.transaction() as con:
        INT.repassar(con, iid, dia="2026-12-09", forma="ENTREGA_DIRETA", valor="3.400,00", despesas="100,00", **COMUM)
    with db.connect() as con:
        assert INT.painel(con, hoje="2026-12-09")["repasses"] == []


def test_a_nao_purgacao_so_depois_do_prazo_e_mostra_os_marcos_do_credor(db):
    iid, pid, _ = _procedimento(db, ate="qualificado", habitacional=True)
    _intimar_todos(db, iid, dia="2026-12-02")
    i = _um(db, iid)[0]
    assert i["prazo_ate"] == "2026-12-17"
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="dia seguinte"):
        INT.certificar(con, iid, tipo="NAO_PURGACAO", dia="2026-12-17", hoje="2026-12-17", **COMUM)
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="terminou"):
        INT.purgar(con, iid, dia="2026-12-18", valor="9.000,00", forma="DEPOSITO", **COMUM)
    with db.transaction() as con:
        INT.certificar(con, iid, tipo="NAO_PURGACAO", dia="2026-12-18", hoje="2026-12-18",
                       sv={"serventia_titular": "MARIO EXEMPLO"}, **COMUM)
    i, lista = _um(db, iid)
    assert i["situacao"] == INT.ENCERRADO_NAO_PURGACAO and _protocolo(db, pid)["situacao"] == "ENCERRADO"
    texto = " ".join(INT.texto_da_peca(i, "CERTIDAO_NAO_PURGACAO", lista, sv={}))
    assert "17/12/2026" in texto and "120 (cento e vinte)" in texto and "Maria Exemplo" in texto
    marcos = INT.depois_da_nao_purgacao(i)
    assert marcos["pedir_ate"] == "2027-04-17"
    assert marcos["averbar_desde"] > "2027-01-28"


def test_desistencia_cancela_a_prenotacao_e_fecha_o_procedimento(db):
    iid, pid, _ = _procedimento(db, ate="qualificado")
    with db.transaction() as con:
        INT.encerrar_sem_certidao(con, iid, motivo=INT.DESISTENCIA, texto="O credor desistiu por petição.",
                                  dia="2026-11-30", **COMUM)
    assert _protocolo(db, pid)["situacao"] == "CANCELADO"
    with db.transaction() as con, pytest.raises(INT.IntimacaoError, match="encerrou"):
        INT.adicionar_intimando(con, iid, nome="X", papel="CONJUGE", **COMUM)


def test_a_carta_de_intimacao_cientifica_da_consolidacao_e_do_leilao(db):
    iid, _, _ = _procedimento(db, ate="qualificado")
    i, lista = _um(db, iid)
    texto = " ".join(INT.texto_da_peca(i, "INTIMACAO", lista, sv={}, intimando=lista[0], conta="Conta exemplo"))
    assert "15 (quinze) dias" in texto and "leilão" in texto and "R$ 3.500,00" in texto and "Conta exemplo" in texto


# ------------------------------------------------------------ a Central


PEDIDO = {
    "IDPedido": 987, "IDStatus": 1, "Protocolo": "IN-2026-000123", "NumeroContrato": "CT-777",
    "DataRemessa": "2026-11-23T09:15:00", "Solicitante": "ESCRITORIO EXEMPLO", "SolicitanteCPFCNPJ": "00.000.000/0001-00",
    "Credor": "BANCO EXEMPLO S.A.", "CredorCPFCNPJ": "11.111.111/0001-11", "CredorEmail": "credor@site-exemplo.invalid",
    "Prenotacoes": {"GetDetalhesIN_Prenotacao_WSResp": [{"Numero": "", "Data": "", "DataVencimento": "", "ValorServico": 0}]},
    "Devedores": {"GetDetalhesIN_Devedor_v2_WSResp": [
        {"Nome": "MARIA EXEMPLO", "Participacao": "Devedor", "CPFCNPJ": "111.222.333-44", "Email": "maria@site-exemplo.invalid"},
        {"Nome": "JOAO EXEMPLO", "Participacao": "Cônjuge", "CPFCNPJ": "222.333.444-55", "Email": ""},
        {"Nome": "AVAL EXEMPLO", "Participacao": "Avalista", "CPFCNPJ": "333.444.555-66", "Email": ""}]},
    "Imoveis": {"GetDetalhesIN_Imovel_WSResp": [{"Matricula": "5001"}]},
    "EnderecosIntimacoes": {"GetDetalhesIN_EnderecoIntimacao_WSResp": [
        {"NomeDevedor": "MARIA EXEMPLO", "EnderecoCompleto": "Rua Indicada, 10, Cidade Exemplo/MA"},
        {"NomeDevedor": "JOAO EXEMPLO", "EnderecoCompleto": "Rua Indicada, 10, Cidade Exemplo/MA"},
        {"NomeDevedor": "AVAL EXEMPLO", "EnderecoCompleto": "Rua do Aval, 1"}]},
    "PrestacoesVencidas": {"GetDetalhesIN_PrestacaoVencida_WSResp": [
        {"Numero": "10", "DataVencimento": "10/09/2026", "Valor": 1000.5},
        {"Numero": "11", "DataVencimento": "10/10/2026", "Valor": 1000.5}]},
    "Purgas": {"GetDetalhesIN_Purga_WSResp": [{"DataVencimento": "15/12/2026", "Valor": 3900.0},
                                               {"DataVencimento": "31/12/2026", "Valor": 4100.0}]},
    "Boletos": {"GetDetalhesIN_Boleto_WSResp": []}, "Reingressos": None, "TipoCobranca": 1,
}


def test_o_pedido_da_central_entra_pelos_nomes_do_contrato():
    t = INT.da_central(PEDIDO)
    r = t["requerimento"]
    assert r["origem"] == INT.CENTRAL_ONR and r["protocolo_central"] == "IN-2026-000123"
    assert r["data_remessa"] == "2026-11-23" and r["contrato"] == "CT-777" and r["avalistas_a_pedido"]
    assert r["projecao"] == [{"vencimento": "2026-12-15", "centavos": 390000},
                             {"vencimento": "2026-12-31", "centavos": 410000}]
    assert [x["papel"] for x in t["intimandos"]] == ["DEVEDOR", "CONJUGE", "AVALISTA"]
    assert t["intimandos"][0]["enderecos"] == ["Rua Indicada, 10, Cidade Exemplo/MA"]
    assert t["matriculas"] == ["5001"]


def test_autuar_da_central_dispensa_a_representacao_e_poe_os_devedores(db):
    with db.transaction() as con:
        mid = _matricula(con)
        pid = int(banco(con).escrever(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, data_limite, situacao, criado_em)
               VALUES (14001,'1A','2026-11-24','2026-12-15','ABERTO',%s) RETURNING id""", (AGORA,))[0]["id"])
        iid = INT.autuar_da_central(con, protocolo_id=pid, resp=PEDIDO, ano=2026, agora=AGORA, hoje=HOJE)["id"]
    i, lista = _um(db, iid)
    assert i["matricula_id"] == mid and "representacao" in i["requisitos_ok"]
    assert [x["nome"] for x in lista] == ["MARIA EXEMPLO", "JOAO EXEMPLO", "AVAL EXEMPLO"]
    assert lista[0]["email"] == "maria@site-exemplo.invalid"


# ------------------------------------------------------------ a configuração


def test_a_configuracao_tem_o_padrao_mais_seguro_e_recusa_o_que_nao_e_escolha():
    cfg = INT.configuracao(lambda k, v: "")
    assert cfg["ri_intimacao_meio_padrao"] == INT.PESSOAL and cfg["ri_intimacao_purga_contagem"] == "CORRIDOS"
    assert INT.configuracao(lambda k, v: "FAX")["ri_intimacao_meio_padrao"] == INT.PESSOAL
    with pytest.raises(INT.IntimacaoError):
        INT.conferir_configuracao({"ri_intimacao_meio_padrao": "FAX"})


def test_os_atos_cobrados_nao_inventam_valor():
    for a in INT.ATOS_COBRADOS:
        assert "R$" not in a["selo"] + a["pendencia"]
    assert {a["codigo_tj"] for a in INT.ATOS_COBRADOS} >= {"16.1", "16.23", "16.24.1"}

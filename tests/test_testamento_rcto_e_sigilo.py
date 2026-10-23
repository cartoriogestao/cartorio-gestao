"""O testamento público e o cerrado, de ponta a ponta — LG04, 19/10/2026.

O QUE ESTES TESTES PROTEGEM, e o que estava quebrado antes deles:

    o selo          o testamento não tinha caminho de selo: todo testamento
                    lançado ia a SUSPENSO_SELO, com livro e folha reservados.
                    Agora sela por `/selo/notas/testamento`, e o cerrado não sai
                    cobrado pelo item do público (13.10.3 × 13.10.1/2)

    o RCTO          o ato nascia sem `tipo_testamento`, e a central o recusava
                    («sem o tipo do testamento»); o cerrado nem entrava na
                    lista. O art. 785, I, do Código de Normas manda alimentar o
                    RCTO — os dois vão, cada um com o seu tipo

    o sigilo        a certidão saía a qualquer um. Enquanto vive o testador, só
                    a ele, por requerimento escrito; com a certidão de óbito, a
                    qualquer pessoa (art. 851, §§ 4º e 5º) — e a busca que
                    alcança testamento não emite positiva nem negativa

Dados fictícios: nomes «DE EXEMPLO», CPF de teste que passa no dígito.
Nenhum teste daqui fala com o selador, com a CENSEC ou com a rede.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS
import notas_censec as NC
import notas_certidao as NCE
import notas_modelos as NM
from bd_nativo import banco
from conftest import cg_login
from protocolo_de_teste import cobrir_o_ato

SENHA = "Senha#12345"
AGORA = "2026-10-19T10:00:00"
HOJE = "2026-10-19"
# CPFs de teste: passam no dígito verificador e não são de ninguém daqui.
CPF_TESTADOR = "00000004936"
CPF_OUTRO = "12345678909"


@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].create_user("tabeliao", "TABELIAO DE EXEMPLO", SENHA, "ADMIN")
    cg_login(cg_casa["c"], "tabeliao", SENHA)
    return cg_casa


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _testamento(db, *, tipo="TESTAMENTO", tipo_testamento=4,
                situacao="LAVRADO", com_cartao=True, livro="T-1",
                folha="7", data=HOJE) -> int:
    """Um testamento lançado, com o testador e duas testemunhas."""
    with db.transaction() as con:
        bd = banco(con)
        ato_id = int(bd.escrever(
            """INSERT INTO nt_atos (tipo, serie, data, situacao, livro, folha,
                   termo, tipo_testamento, teor, teor_formato, origem, criado_em)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, 'html', 'MANUAL', %s)
               RETURNING id""",
            (tipo, tipo, data, situacao, livro, folha, tipo_testamento,
             "<p>TEOR DE EXEMPLO DO TESTAMENTO.</p>", AGORA))[0]["id"])
        cartao = None
        if com_cartao:
            cartao = int(bd.escrever(
                """INSERT INTO nt_cartoes (nome, documento, nascimento, sexo, mae,
                       criado_em)
                   VALUES ('FULANO DE EXEMPLO', %s, '1950-03-04', 'M',
                           'MAE DE EXEMPLO', %s) RETURNING id""",
                (CPF_TESTADOR, AGORA))[0]["id"])
        bd.escrever(
            """INSERT INTO nt_ato_partes (ato_id, cartao_id, nome, documento,
                   qualificacao, testemunha, ordem, criado_em)
               VALUES (%s, %s, 'FULANO DE EXEMPLO', %s, 'TESTADOR', 0, 1, %s)""",
            (ato_id, cartao, CPF_TESTADOR, AGORA))
        for ordem, nome in ((2, "TESTEMUNHA UM DE EXEMPLO"),
                            (3, "TESTEMUNHA DOIS DE EXEMPLO")):
            bd.escrever(
                """INSERT INTO nt_ato_partes (ato_id, nome, qualificacao,
                       testemunha, ordem, criado_em)
                   VALUES (%s, %s, 'TESTEMUNHA', 1, %s, %s)""",
                (ato_id, nome, ordem, AGORA))
    return ato_id


def _emitir(db, **campos):
    with db.transaction() as con:
        return NCE.emitir(con, hoje=HOJE, agora=AGORA, usuario="TABELIAO",
                          **campos)


# ------------------------------------------------------------------ o selo


def test_o_testamento_publico_e_o_cerrado_selam_pelo_caminho_do_testamento():
    assert AS.caminho_do_ato_de_livro_das_notas("TESTAMENTO") == \
        "/selo/notas/testamento"
    assert AS.caminho_do_ato_de_livro_das_notas("TESTAMENTO_CERRADO") == \
        "/selo/notas/testamento"


def test_o_cerrado_nao_se_cobra_pelo_item_do_publico_nem_o_contrario():
    assert AS.conferir_item_do_testamento("TESTAMENTO_CERRADO", "13.10.3") is None
    assert "13.10.3" in AS.conferir_item_do_testamento(
        "TESTAMENTO_CERRADO", "13.10.1")
    assert AS.conferir_item_do_testamento("TESTAMENTO", "13.10.2") is None
    assert "13.10.1" in AS.conferir_item_do_testamento("TESTAMENTO", "13.10.3")
    # ato que não é testamento não passa por esta régua
    assert AS.conferir_item_do_testamento("ESCRITURA", "13.10.3") is None


def test_os_itens_do_testamento_sao_os_da_tabela_de_2026():
    """Conferidos contra a tabela real (serviços 391 a 394), e não lembrados."""
    import json
    tabela = json.loads((RAIZ / "tests" / "custas_reais.json").read_text("utf-8"))
    descricao = {v["tj"]: v["descricao"] for v in tabela["valores_2026"]}
    for itens in AS.ITENS_DO_TESTAMENTO.values():
        for codigo, _ in itens:
            assert descricao[codigo].startswith("Testamento:"), codigo
    assert "Cerrado" in descricao["13.10.3"]


def test_o_envelope_do_testamento_leva_livro_folha_e_as_partes():
    envelope, caminho = AS.envelope_do_ato_de_livro_das_notas(
        tipo="TESTAMENTO_CERRADO", codigo_tj="13.10.3",
        escrevente="ESCREVENTE DE EXEMPLO", versao_tabela="10022",
        livro="TC-1", folha="4", termo="2",
        partes=[{"nome": "FULANO DE EXEMPLO", "documento": CPF_TESTADOR}])
    assert caminho == "/selo/notas/testamento"
    assert envelope["selo"] == {"escrevente": "ESCREVENTE DE EXEMPLO",
                                "livro": "TC-1", "folha": "4", "termo": "2"}
    assert envelope["quantidade"] == 1
    assert envelope["ato"]["codigo"] == "13.10.3"
    assert envelope["partes"]["parteAto"] == [
        {"nome": "FULANO DE EXEMPLO", "documento": CPF_TESTADOR}]
    # O testamento não é «ato declarado sem valor»: não leva a natureza «Outros»
    assert "natureza" not in envelope


def test_o_cerrado_lancado_sem_selo_oferece_o_item_do_cerrado_para_selar(casa):
    """O caso de quem tinha testamento parado em SUSPENSO_SELO: lançado, sem
    selo, e a ficha sem caminho para pedi-lo."""
    db = casa["db"]
    with db.transaction() as con:
        for servico, codigo, descricao in (
                (391, "13.10.1", "Testamento: Público sem conteúdo patrimonial"),
                (393, "13.10.3", "Testamento: Cerrado, incluindo todos os atos necessários.")):
            banco(con).escrever(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
                   VALUES (%s, %s, %s, 1) ON CONFLICT DO NOTHING""",
                (servico, codigo, descricao))
    ato_id = _testamento(db, tipo="TESTAMENTO_CERRADO", tipo_testamento=2,
                         situacao="SUSPENSO_SELO")
    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert "Ainda não há caminho de selo configurado" not in html
    assert 'value="13.10.3"' in html
    assert "Cerrado, incluindo todos os atos" in html
    assert 'value="13.10.1"' not in html


def _selador_de_mentira(monkeypatch, pedidos: list):
    """O aparelho da rede local não existe no teste: este grava no razão como o
    de verdade (`selador_cliente.selar`) e devolve um selo."""
    import selador
    import selador_cliente as CL

    def falso(con, pasta, caminho, dados, *, referencia, atribuicao, agora,
              cns, usuario=None, **_):
        numero = f"SELOTESTE{len(pedidos) + 1:04d}"
        pedidos.append({"caminho": caminho, "dados": dados})
        banco(con).escrever(
            """INSERT INTO sd_selos (numero, texto, caminho, atribuicao,
                   referencia, ambiente, obtido_em, obtido_por)
               VALUES (%s, 'SELO DE TESTE', %s, %s, %s, 'HOMOLOGACAO', %s, %s)""",
            (numero, caminho, atribuicao, str(referencia), agora, usuario))
        return [selador.SeloGerado(numero=numero, texto="SELO DE TESTE")]

    monkeypatch.setattr(CL, "selar", falso)


def test_o_cerrado_suspenso_sela_pela_ficha_com_o_item_dele(casa, monkeypatch):
    db, c = casa["db"], casa["c"]
    db.set_settings({"selo_tabela_custas_em": "2026-01-01", "ri_cns": "000000"})
    pedidos: list = []
    _selador_de_mentira(monkeypatch, pedidos)
    ato_id = _testamento(db, tipo="TESTAMENTO_CERRADO", tipo_testamento=2,
                         situacao="SUSPENSO_SELO")
    token = _token(c.get(f"/notas/atos/{ato_id}").get_data(as_text=True))
    # o item do público é recusado ANTES de pedir — nenhum selo comprado
    html = c.post(f"/notas/atos/{ato_id}",
                  data={"acao": "selar", "codigo_tj": "13.10.1",
                        "csrf_token": token},
                  follow_redirects=True).get_data(as_text=True)
    assert "não é de testamento cerrado" in html
    assert pedidos == []
    # Selo pago só sai coberto (LX16): a ficha do ato já está ligada ao item
    # 13.10.3 de um protocolo pago, como o balcão a deixa.
    with db.transaction() as con:
        cobrir_o_ato(con, tabela="nt_atos", ato_id=ato_id, codigo="13.10.3")
    c.post(f"/notas/atos/{ato_id}",
           data={"acao": "selar", "codigo_tj": "13.10.3", "csrf_token": token})
    assert [p["caminho"] for p in pedidos] == ["/selo/notas/testamento"]
    assert pedidos[0]["dados"]["ato"]["codigo"] == "13.10.3"
    assert pedidos[0]["dados"]["selo"]["livro"] == "T-1"
    with db.connect() as con:
        linha = banco(con).um("SELECT selo, situacao FROM nt_atos WHERE id = %s",
                              (ato_id,))
    assert dict(linha) == {"selo": "SELOTESTE0001", "situacao": "LAVRADO"}


# ------------------------------------------------------------------ o RCTO


def test_o_testamento_aberto_na_tela_nasce_com_o_tipo_do_rcto(casa):
    c = casa["c"]
    for tipo, esperado in (("TESTAMENTO", 4), ("TESTAMENTO_CERRADO", 2)):
        token = _token(c.get("/notas/atos/novo").get_data(as_text=True))
        r = c.post("/notas/atos/novo",
                   data={"tipo": tipo, "csrf_token": token,
                         "natureza": "Testamento de exemplo"})
        assert r.status_code == 302
        ato_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with casa["db"].connect() as con:
            linha = banco(con).um(
                "SELECT tipo, tipo_testamento FROM nt_atos WHERE id = %s",
                (ato_id,))
        assert (linha["tipo"], linha["tipo_testamento"]) == (tipo, esperado)


def test_ato_que_nao_e_testamento_nasce_sem_tipo_do_rcto():
    assert NC.tipo_testamento_ao_abrir("ESCRITURA") is None
    assert NC.tipo_testamento_ao_abrir("PROCURACAO_PREVIDENCIARIA", 4) is None
    # o tipo da minuta vale se couber na espécie; senão, o padrão dela
    assert NC.tipo_testamento_ao_abrir("TESTAMENTO", 6) == 6
    assert NC.tipo_testamento_ao_abrir("TESTAMENTO_CERRADO", 4) == 2


def test_o_cerrado_lavrado_vai_ao_rcto_como_cerrado(casa):
    db = casa["db"]
    _testamento(db, tipo="TESTAMENTO_CERRADO", tipo_testamento=2)
    with db.connect() as con:
        quinzena = 2 if int(HOJE[8:10]) > 15 else 1
        r = NC.separar(con, "RCTO", int(HOJE[:4]), int(HOJE[5:7]), quinzena)
    assert [x["ato"]["tipo"] for x in r["aptos"]] == ["TESTAMENTO_CERRADO"], \
        r["impedidos"]
    assert r["aptos"][0]["linha"]["tipoTestamento"] == 2


def test_o_testamento_novo_nao_vai_a_cep(casa):
    db = casa["db"]
    _testamento(db)
    with db.connect() as con:
        quinzena = 2 if int(HOJE[8:10]) > 15 else 1
        cep = NC.separar(con, "CEP", int(HOJE[:4]), int(HOJE[5:7]), quinzena)
    assert cep["aptos"] == [] and cep["impedidos"] == []


def test_a_ficha_troca_o_tipo_do_rcto_e_recusa_o_que_nao_cabe(casa):
    db, c = casa["db"], casa["c"]
    ato_id = _testamento(db)
    html = c.get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert "Testamento — RCTO e sigilo" in html
    token = _token(html)
    c.post(f"/notas/atos/{ato_id}",
           data={"acao": "tipo_testamento", "tipo_testamento": "6",
                 "csrf_token": token})
    c.post(f"/notas/atos/{ato_id}",
           data={"acao": "tipo_testamento", "tipo_testamento": "2",
                 "csrf_token": token})
    with db.connect() as con:
        bd = banco(con)
        assert bd.valor("SELECT tipo_testamento FROM nt_atos WHERE id = %s",
                        (ato_id,)) == 6
        assert bd.valor(
            """SELECT count(*) AS n FROM audit_logs
                WHERE action = 'NT_ATO_TIPO_TESTAMENTO'""") == 1


def test_o_tipo_do_rcto_nao_muda_depois_de_informado(casa):
    db, c = casa["db"], casa["c"]
    ato_id = _testamento(db)
    with db.transaction() as con:
        bd = banco(con)
        remessa = bd.escrever(
            """INSERT INTO nt_remessas (central, competencia, situacao,
                   criado_em)
               VALUES ('RCTO', '2026-10', 'ENVIADA', %s) RETURNING id""",
            (AGORA,))[0]["id"]
        bd.escrever(
            """INSERT INTO nt_remessa_itens (remessa_id, ato_id, situacao,
                   criado_em)
               VALUES (%s, %s, 'ENVIADA', %s)""", (remessa, ato_id, AGORA))
    token = _token(c.get(f"/notas/atos/{ato_id}").get_data(as_text=True))
    html = c.post(f"/notas/atos/{ato_id}",
                  data={"acao": "tipo_testamento", "tipo_testamento": "6",
                        "csrf_token": token},
                  follow_redirects=True).get_data(as_text=True)
    assert "já foi informado ao RCTO" in html
    with db.connect() as con:
        assert banco(con).valor(
            "SELECT tipo_testamento FROM nt_atos WHERE id = %s", (ato_id,)) == 4


# ------------------------------------------------------------------ o sigilo


def test_a_certidao_do_testamento_nao_sai_a_qualquer_um(casa):
    ato_id = _testamento(casa["db"])
    with pytest.raises(NCE.CertidaoNotasError, match="Sigilo do testamento"):
        _emitir(casa["db"], ato_id=ato_id)
    with pytest.raises(NCE.CertidaoNotasError, match="Sigilo do testamento"):
        _emitir(casa["db"], ato_id=ato_id, requerente="OUTRA PESSOA DE EXEMPLO",
                requerente_documento=CPF_OUTRO, requerimento_escrito=True)
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT count(*) AS n FROM nt_certidoes") == 0


def test_o_testador_precisa_do_requerimento_escrito(casa):
    ato_id = _testamento(casa["db"])
    with pytest.raises(NCE.CertidaoNotasError, match="requerimento ESCRITO"):
        _emitir(casa["db"], ato_id=ato_id, requerente="FULANO DE EXEMPLO",
                requerente_documento="000.000.049-36")


def test_o_testador_com_requerimento_escrito_recebe_a_certidao(casa):
    ato_id = _testamento(casa["db"])
    r = _emitir(casa["db"], ato_id=ato_id, requerente="FULANO DE EXEMPLO",
                requerente_documento="000.000.049-36",
                requerimento_escrito=True)
    with casa["db"].connect() as con:
        fundamento = banco(con).valor(
            "SELECT sigilo_fundamento FROM nt_certidoes WHERE id = %s",
            (r["certidao_id"],))
    assert "§ 4º" in fundamento and "testador" in fundamento


def test_com_a_certidao_de_obito_qualquer_pessoa_recebe_a_certidao(casa):
    ato_id = _testamento(casa["db"])
    r = _emitir(casa["db"], ato_id=ato_id, requerente="HERDEIRO DE EXEMPLO",
                requerente_documento=CPF_OUTRO,
                obito_apresentado="Matrícula 000000 01 55 2026 4 00001 001 0000001 00")
    with casa["db"].connect() as con:
        fundamento = banco(con).valor(
            "SELECT sigilo_fundamento FROM nt_certidoes WHERE id = %s",
            (r["certidao_id"],))
    assert "óbito" in fundamento and "§ 5º" in fundamento


def test_o_testamento_do_acervo_guardado_como_escritura_tambem_tem_sigilo(casa):
    """A carga do E-Ofício grava testamento como ESCRITURA com o tipo do RCTO."""
    ato_id = _testamento(casa["db"], tipo="ESCRITURA", tipo_testamento=4)
    with pytest.raises(NCE.CertidaoNotasError, match="Sigilo do testamento"):
        _emitir(casa["db"], ato_id=ato_id)


def test_a_busca_que_alcanca_testamento_nao_emite_positiva_nem_negativa(casa):
    _testamento(casa["db"])
    with pytest.raises(NCE.CertidaoNotasError, match="Sigilo do testamento"):
        _emitir(casa["db"], documento=CPF_TESTADOR)
    with pytest.raises(NCE.CertidaoNotasError):
        _emitir(casa["db"], documento=CPF_TESTADOR, tipo="NEGATIVA")
    # o próprio testador, com o requerimento, recebe a positiva
    r = _emitir(casa["db"], documento=CPF_TESTADOR,
                requerente_documento=CPF_TESTADOR, requerimento_escrito=True)
    assert r["tipo"] == "POSITIVA"


def test_a_tela_de_certidao_pede_o_requerimento_so_quando_ha_testamento(casa):
    ato_id = _testamento(casa["db"])
    html = casa["c"].get(f"/notas/certidoes?ato_id={ato_id}").get_data(as_text=True)
    assert "certidão sob sigilo" in html
    assert 'name="requerimento_escrito"' in html
    assert 'name="obito_apresentado"' in html
    vazia = casa["c"].get("/notas/certidoes").get_data(as_text=True)
    assert 'name="requerimento_escrito"' not in vazia


def test_a_rota_recusa_a_certidao_do_testamento_sem_o_fundamento(casa):
    ato_id = _testamento(casa["db"])
    c = casa["c"]
    token = _token(c.get(f"/notas/certidoes?ato_id={ato_id}").get_data(as_text=True))
    html = c.post("/notas/certidoes/emitir",
                  data={"ato_id": str(ato_id), "csrf_token": token,
                        "requerente_documento": CPF_OUTRO},
                  follow_redirects=True).get_data(as_text=True)
    assert "Sigilo do testamento" in html
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT count(*) AS n FROM nt_certidoes") == 0


# ------------------------------------------------------------------ a minuta


def test_a_minuta_do_cerrado_e_auto_de_aprovacao_e_vai_ao_rcto():
    m = NM.por_codigo("NT-TESTAMENTO-CERRADO")
    assert m["tipo"] == "TESTAMENTO_CERRADO" and m["tipo_testamento"] == 2
    assert m["corpo"].startswith("<p>AUTO DE APROVAÇÃO DE TESTAMENTO CERRADO.")
    # o tabelião aprova, cerra e cose — e não escreve disposição nenhuma
    assert "cerrei e cosi" in m["corpo"]
    assert "DISPOSIÇÕES TESTAMENTÁRIAS" not in m["corpo"]
    assert "1.874" in m["corpo"] and "1.868" in m["corpo"]


def test_a_minuta_do_cerrado_entra_na_biblioteca_das_notas(casa):
    with casa["db"].connect() as con:
        linha = banco(con).um(
            """SELECT tipo, central_censec, tipo_testamento FROM nt_modelos
                WHERE codigo = 'NT-TESTAMENTO-CERRADO' ORDER BY id LIMIT 1""")
    assert dict(linha) == {"tipo": "TESTAMENTO_CERRADO",
                           "central_censec": "RCTO", "tipo_testamento": 2}

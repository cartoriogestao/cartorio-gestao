"""A procuração do INSS e a firma do documento de veículo — LG04, 19/10/2026.

O QUE ESTES TESTES PROTEGEM:

    a procuração previdenciária   o tipo existia e a minuta não: quem lavrava
                                  partia da procuração comum, e o ato ia à CEP
                                  como procuração comum. Agora há minuta (com o
                                  prazo de doze meses do art. 109 da Lei
                                  8.213/1991), o caminho de selo do INSS como
                                  quarta escolha — só dela —, e a isenção com o
                                  motivo escrito no envelope

    a firma do veículo            a caixa «Documento de veículo» só trocava o
                                  item (13.17.3), e a semelhança passava. O
                                  art. 865, II, do Código de Normas manda
                                  autenticidade no CRV, no DUT, na ATPV e na
                                  procuração para transferir

Dados fictícios. Nenhum teste daqui fala com o selador ou com a CENSEC.
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
import notas_modelos as NM
from bd_nativo import banco
from conftest import cg_login
from notas_schema import (DOCUMENTOS_DE_VEICULO, SERVICOS,
                          recusa_da_firma_do_veiculo, servico_do_reconhecimento)

SENHA = "Senha#12345"
AGORA = "2026-10-19T10:00:00"


@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].create_user("tabeliao", "TABELIAO DE EXEMPLO", SENHA, "ADMIN")
    cg_login(cg_casa["c"], "tabeliao", SENHA)
    return cg_casa


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


# ---------------------------------------------- a procuração previdenciária


def test_a_minuta_da_previdenciaria_tem_o_tipo_certo_e_o_prazo_de_doze_meses():
    m = NM.por_codigo("NT-PROC-PREVIDENCIARIA")
    assert m["tipo"] == "PROCURACAO_PREVIDENCIARIA"
    assert m["tipo_ato_cep"] == 3
    assert "INSTITUTO NACIONAL DO SEGURO SOCIAL" in m["corpo"]
    assert "artigo 109 da Lei nº 8.213" in m["corpo"]
    assert "NÃO SUPERIOR A DOZE MESES" in m["corpo"]
    # o «prazo indeterminado» da procuração comum não cabe aqui
    assert "indeterminado" not in m["corpo"]
    assert any("DOZE MESES" in r for r in m["requisitos"])


def test_o_ato_aberto_pela_minuta_e_previdenciario_e_nao_procuracao_comum(casa):
    c = casa["c"]
    token = _token(c.get("/notas/atos/novo").get_data(as_text=True))
    r = c.post("/notas/atos/novo",
               data={"tipo": "PROCURACAO", "csrf_token": token,
                     "modelo_codigo": "NT-PROC-PREVIDENCIARIA"})
    assert r.status_code == 302
    ato_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
    with casa["db"].connect() as con:
        linha = banco(con).um(
            "SELECT tipo, tipo_testamento FROM nt_atos WHERE id = %s", (ato_id,))
    assert dict(linha) == {"tipo": "PROCURACAO_PREVIDENCIARIA",
                           "tipo_testamento": None}


def test_a_previdenciaria_vai_a_cep_como_previdenciaria():
    ato = {"tipo": "PROCURACAO_PREVIDENCIARIA", "tipo_cesdi": None,
           "tipo_testamento": None}
    assert NC.central_do_ato(ato) == "CEP"
    assert NC.TIPO_SISTEMA_PARA_CEP["PROCURACAO_PREVIDENCIARIA"] == 3


def test_o_caminho_do_inss_e_so_da_previdenciaria():
    assert AS.caminho_do_ato_de_livro_das_notas(
        "PROCURACAO_PREVIDENCIARIA", especie_procuracao="INSS") == \
        "/selo/notas/procuracao/inss"
    # a procuração comum que pedisse o caminho do INSS seria selo do INSS em
    # ato que não é — recusa, como qualquer escolha que não existe
    with pytest.raises(AS.AtoError):
        AS.caminho_do_ato_de_livro_das_notas(
            "PROCURACAO", especie_procuracao="INSS")
    # os três da decisão de 15/10/2026 continuam valendo para ela
    assert AS.caminho_do_ato_de_livro_das_notas(
        "PROCURACAO_PREVIDENCIARIA", especie_procuracao="SIMPLES") == \
        AS.CAMINHO_DA_PROCURACAO["SIMPLES"]


def test_o_envelope_do_inss_isento_leva_o_motivo_escrito():
    envelope, caminho = AS.envelope_do_ato_de_livro_das_notas(
        tipo="PROCURACAO_PREVIDENCIARIA", codigo_tj="13.9.3",
        escrevente="ESCREVENTE DE EXEMPLO", versao_tabela="0120260101",
        livro="P-3", folha="12", especie_procuracao="INSS",
        partes=[{"nome": "SEGURADO DE EXEMPLO"}], isento=True,
        motivo_isencao="Procuração para fins previdenciários — isenção legal")
    assert caminho == "/selo/notas/procuracao/inss"
    assert envelope["isento"] == {
        "value": True,
        "motivo": "Procuração para fins previdenciários — isenção legal"}
    assert envelope["quantidade"] == 1
    with pytest.raises(AS.AtoError, match="motivo escrito"):
        AS.envelope_do_ato_de_livro_das_notas(
            tipo="PROCURACAO_PREVIDENCIARIA", codigo_tj="13.9.3",
            escrevente="ESCREVENTE DE EXEMPLO", versao_tabela="0120260101",
            livro="P-3", folha="12", especie_procuracao="INSS", isento=True)


def test_a_ficha_da_previdenciaria_oferece_o_inss_primeiro(casa):
    db = casa["db"]
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
               VALUES (387, '13.9.3', 'Outras procurações', 1)
               ON CONFLICT DO NOTHING""")
        ato_id = int(bd.escrever(
            """INSERT INTO nt_atos (tipo, serie, data, situacao, livro, folha,
                   termo, teor, teor_formato, origem, criado_em)
               VALUES ('PROCURACAO_PREVIDENCIARIA', 'PROCURACAO', '2026-10-19',
                       'SUSPENSO_SELO', 'P-3', '12', 1, '<p>TEOR</p>', 'html',
                       'MANUAL', %s) RETURNING id""", (AGORA,))[0]["id"])
    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    opcoes = re.findall(r'<option value="(INSS|PODERES_ESPECIFICOS|SIMPLES|VENDA)"',
                        html)
    assert opcoes[:4] == ["INSS", "PODERES_ESPECIFICOS", "SIMPLES", "VENDA"]
    assert "/selo/notas/procuracao/inss" in html


def test_a_procuracao_comum_nao_oferece_o_caminho_do_inss(casa):
    with casa["db"].transaction() as con:
        ato_id = int(banco(con).escrever(
            """INSERT INTO nt_atos (tipo, serie, data, situacao, livro, folha,
                   termo, teor, teor_formato, origem, criado_em)
               VALUES ('PROCURACAO', 'PROCURACAO', '2026-10-19',
                       'SUSPENSO_SELO', 'P-3', '13', 2, '<p>TEOR</p>', 'html',
                       'MANUAL', %s) RETURNING id""", (AGORA,))[0]["id"])
    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert '<option value="INSS"' not in html
    assert '<option value="SIMPLES"' in html


# ---------------------------------------------------------- a firma do veículo


def test_a_transferencia_de_veiculo_nao_admite_semelhanca():
    for documento in ("CRV", "ATPV", "PROCURACAO", "", None):
        recusa = recusa_da_firma_do_veiculo("SEMELHANCA", True, documento)
        assert recusa and "AUTENTICIDADE" in recusa and "865" in recusa, documento
    assert recusa_da_firma_do_veiculo("AUTENTICIDADE", True, "ATPV") is None


def test_o_documento_de_veiculo_que_nao_transfere_e_o_que_nao_e_veiculo_passam():
    assert recusa_da_firma_do_veiculo("SEMELHANCA", True, "OUTRO") is None
    assert recusa_da_firma_do_veiculo("SEMELHANCA", False, "CRV") is None
    # e o item continua o mesmo: 13.17.3 para todo documento de veículo
    assert servico_do_reconhecimento("AUTENTICIDADE", veiculo=True) == \
        SERVICOS["VEICULO"]
    assert set(DOCUMENTOS_DE_VEICULO) == {"CRV", "ATPV", "PROCURACAO", "OUTRO"}


def _cartao(db) -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO nt_cartoes (nome, documento, criado_em)
               VALUES ('VENDEDOR DE EXEMPLO', '11144477735', %s) RETURNING id""",
            (AGORA,))[0]["id"])


def test_o_balcao_recusa_a_semelhanca_no_crv_sem_comprar_selo(casa):
    c, db = casa["c"], casa["db"]
    cid = _cartao(db)
    html_tela = c.get("/notas/reconhecimento?busca=11144477735").get_data(as_text=True)
    assert 'name="veiculo_documento"' in html_tela
    html = c.post("/notas/reconhecimento",
                  data={"acao": "reconhecer", "cartao_id": [str(cid)],
                        "especie": "SEMELHANCA", "veiculo": "1",
                        "veiculo_documento": "CRV",
                        "csrf_token": _token(html_tela)},
                  follow_redirects=True).get_data(as_text=True)
    assert "só admite reconhecimento por" in html and "AUTENTICIDADE" in html
    with db.connect() as con:
        bd = banco(con)
        assert bd.valor("SELECT count(*) AS n FROM nt_reconhecimentos") == 0
        assert bd.valor("SELECT count(*) AS n FROM sd_selos") == 0


def test_a_quitacao_de_veiculo_por_semelhanca_segue_para_o_selo(casa):
    """Passou a régua do veículo: o que barra agora é só o selo, que não existe
    no teste — e o recado é o dele, e não o do art. 865."""
    c, db = casa["c"], casa["db"]
    cid = _cartao(db)
    token = _token(c.get("/notas/reconhecimento").get_data(as_text=True))
    html = c.post("/notas/reconhecimento",
                  data={"acao": "reconhecer", "cartao_id": [str(cid)],
                        "especie": "SEMELHANCA", "veiculo": "1",
                        "veiculo_documento": "OUTRO", "csrf_token": token},
                  follow_redirects=True).get_data(as_text=True)
    assert "art. 865" not in html
    assert "Reconhecimento NÃO lavrado" in html

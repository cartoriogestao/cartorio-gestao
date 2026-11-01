"""O PIX NÃO SAI SE O FAVORECIDO NÃO CONFERE.

Pedido do oficial (31/10/2026): o pagamento de um foi para a chave de outro, com o CPF do
outro também no cadastro. A API do Inter não diz de quem é a chave antes de pagar: antes,
a casa confere contra ela mesma; depois, confere o recebedor que o banco informa.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP
import despesas_inter as INTER
import despesas_recorrentes as RC

AGORA = datetime(2026, 10, 30, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
CPF_DA_BEATRIZ = "00000000191"   # fictícios da casa
CPF_DA_CARLA = "00000000272"


def _despesa(con, nome="BEATRIZ EXEMPLO", documento=CPF_DA_BEATRIZ, chave=CPF_DA_BEATRIZ):
    return DP.cadastrar(
        con, agora=AGORA, por="mario", origem="MANUAL", chave_origem=None,
        beneficiario_nome=nome, beneficiario_documento=documento, valor_centavos=193532,
        vencimento="2026-10-30", forma=DP.PIX_CHAVE, codigo=chave,
        descricao="Folha de pagamento, salário líquido", categoria="PESSOAL",
        documento_especie="Recibo de pagamento")


# ------------------------------------------------------ o que se calcula

@pytest.mark.parametrize("um, outro, igual", [
    ("BEATRIZ EXEMPLO DOS SANTOS", "Beatriz Exemplo", True),
    ("JOSÉ EXEMPLO", "jose", True),
    ("BEATRIZEXEMPLODOSSANTOS", "BEATRIZ EXEMPLO", True),
    ("BEATRIZ EXEMPLO", "CARLA EXEMPLO", False),
    ("", "CARLA", False),
])
def test_mesmo_nome(um, outro, igual):
    assert DP.mesmo_nome(um, outro) is igual


@pytest.mark.parametrize("esperado, recebido, resposta", [
    ("00000000191", "***.000.001-**", True),
    ("00000000191", "***.777.888-**", False),
    ("00000010000127", "00000010000127", True),
    ("00000010000127", "***.000.001-**", False),
    ("", "***.000.001-**", None),
    ("00000000191", "", None),
])
def test_documento_confere_com_a_mascara_do_banco(esperado, recebido, resposta):
    assert DP.documento_confere(esperado, recebido) is resposta


def test_o_recebedor_diverge_pelo_documento_ou_pelo_nome():
    d = {"beneficiario_nome": "MARIO EXEMPLO", "beneficiario_documento": "00000000191"}
    assert DP.recebedor_diverge(d, "Mario Exemplo", "***.000.001-**") == ""
    assert "CARLA EXEMPLO" in DP.recebedor_diverge(d, "CARLA EXEMPLO", "***.777.888-**")
    assert "CARLA EXEMPLO" in DP.recebedor_diverge(d, "CARLA EXEMPLO", "***.000.001-**")
    assert DP.recebedor_diverge(d, "", "") == "", "o banco não disse: não há o que acusar"
    empresa = {"beneficiario_nome": "NOME FANTASIA", "beneficiario_documento": "00000010000127"}
    assert DP.recebedor_diverge(empresa, "RAZAO SOCIAL LTDA", "00000010000127") == ""


# ------------------------------------------------------ antes de pagar

def test_pix_por_chave_exige_o_documento(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con, pytest.raises(DP.DespesaError, match="exige o CPF/CNPJ"):
        _despesa(con, documento="", chave="beatriz@example.com")


def test_chave_de_cpf_diferente_do_documento_e_recusada(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con, pytest.raises(DP.DespesaError, match="diferente do documento"):
        _despesa(con, documento=CPF_DA_CARLA, chave=CPF_DA_BEATRIZ)


def test_o_caso_de_30_10_mesmo_cpf_e_mesma_chave_com_outro_nome(cg_casa_logada):
    """Chave e documento batiam entre si: quem acusa é o outro nome com o mesmo CPF."""
    with cg_casa_logada["db"].transaction() as con:
        _despesa(con)
        with pytest.raises(DP.DespesaError, match="já está cadastrado para BEATRIZ"):
            _despesa(con, nome="CARLA EXEMPLO")


def test_mesma_chave_de_celular_para_outra_pessoa_e_recusada(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con:
        _despesa(con, chave="+5599999000000")
        with pytest.raises(DP.DespesaError, match="Esta chave Pix já está cadastrada"):
            _despesa(con, nome="CARLA EXEMPLO", documento=CPF_DA_CARLA, chave="+5599999000000")


def test_a_mesma_pessoa_paga_duas_vezes_passa(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con:
        _despesa(con)
        _despesa(con, nome="Beatriz Exemplo dos Santos")


def test_linha_ja_conciliada_nao_prende_o_dono_da_chave(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con:
        i = _despesa(con, nome="CARLA EXEMPLO")
        DP.banco(con).escrever("UPDATE dp_despesas SET situacao = %s WHERE id = %s", (DP.CONCILIADA, i))
        _despesa(con)


def test_a_recorrente_que_nao_confere_nao_se_carrega_nem_segura_as_outras(cg_casa_logada):
    base = {"descricao": "Folha de pagamento, salário líquido", "categoria": "PESSOAL",
            "forma": DP.PIX_CHAVE, "valor": 193532, "dia_vencimento": 30, "antecedencia_dias": 25,
            "documento_especie": "Recibo de pagamento", "primeiro_mes": "2026-10"}
    with cg_casa_logada["db"].transaction() as con:
        boa = RC.cadastrar(con, {**base, "beneficiario_nome": "BEATRIZ EXEMPLO", "chave_pix": "000.000.001-91",
                                 "beneficiario_documento": CPF_DA_BEATRIZ}, por="mario", agora=AGORA)
        with pytest.raises(DP.DespesaError, match="já está cadastrado"):
            RC.cadastrar(con, {**base, "beneficiario_nome": "CARLA EXEMPLO", "chave_pix": "000.000.001-91",
                               "beneficiario_documento": CPF_DA_BEATRIZ}, por="mario", agora=AGORA)
        DP.banco(con).escrever(
            "INSERT INTO dp_recorrentes (descricao, categoria, beneficiario_nome, forma, chave_pix, valor, "
            "dia_vencimento, antecedencia_dias, documento_especie, primeiro_mes, criada_em, criada_por) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (base["descricao"], "PESSOAL", "CARLA EXEMPLO", DP.PIX_CHAVE, "+5599999000000", 100, 30, 25,
             "Recibo", "2026-10", "2026-10-30T09:00:00", "antes da trava"))
        [i] = RC.gerar(con, hoje=AGORA.date(), agora=AGORA, por="automação")
        assert DP.despesa(con, i)["chave_origem"] == f"{boa}:2026-10"
        [travada] = RC.do_mes(con, AGORA.date())
    assert "exige o CPF/CNPJ" in travada["impedimento"] and not travada["carrega_sozinho"]


def test_autorizar_e_pagar_conferem_de_novo(cg_casa_logada):
    """Duas despesas que nasceram antes da trava: nenhuma das duas passa."""
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        i = _despesa(con)
        DP.autorizar(con, i, agora=AGORA, por="mario", papel="ADMIN")
        outra = _despesa(con, nome="BEATRIZ EXEMPLO", chave="beatriz@example.com")
        DP.banco(con).escrever("UPDATE dp_despesas SET beneficiario_nome = %s WHERE id = %s",
                               ("CARLA EXEMPLO", outra))
        with pytest.raises(DP.DespesaError, match="já está cadastrado"):
            DP.autorizar(con, outra, agora=AGORA, por="mario", papel="ADMIN")
        assert [d["pendencia"] for d in DP.para_autorizar(con)] == ["favorecido não confere"]
    with db.transaction() as con:
        DP.gravar_configuracao(con, {**DP.PADRAO, "despesas_pagamento_ligado": "1",
                                     "despesas_ambiente": "sandbox"})

    class Banco:
        ambiente = "sandbox"

        def pagar_pix(self, *a, **k):
            pytest.fail("não devia ir ao banco")

    r = INTER.pagar(db, i, cliente=Banco(), por="automação", agora=AGORA)
    assert r["situacao"] == DP.FALHOU and "já está cadastrado" in r["mensagem"]


# ------------------------------------------------------ depois de pagar

def test_o_recebedor_que_nao_confere_nao_vai_ao_livro(cg_casa_logada):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        i = _despesa(con)
        DP.banco(con).escrever("UPDATE dp_despesas SET situacao = %s, banco_codigo = %s, ambiente = %s WHERE id = %s",
                               (DP.ENVIADA, "abc", "sandbox", i))

    class Banco:
        ambiente = "sandbox"

        def extrato(self, inicio, fim):
            return [{"idTransacao": "1", "valor": "1935.32", "dataTransacao": "2026-10-30",
                     "detalhes": {"codigoSolicitacao": "abc", "nomeRecebedor": "CARLA EXEMPLO",
                                  "cpfCnpjRecebedor": "***.000.002-**"}}]

    assert INTER.conciliar(db, cliente=Banco(), por="automação", agora=AGORA)["conciliadas"] == []
    with db.connect() as con:
        d = DP.despesa(con, i)
        assert d["situacao"] == DP.PAGA and d["ld_despesa_id"] is None
        assert "CARLA EXEMPLO" in d["recebedor_divergente"]
        assert [x["id"] for x in DP.recebedor_em_duvida(con)] == [i]
    assert "O recebedor não confere" in cg_casa_logada["c"].get("/administrativo/despesas").get_data(as_text=True)

    with db.transaction() as con, pytest.raises(DP.DespesaError, match="Só o oficial"):
        DP.aceitar_recebedor(con, i, agora=AGORA, por="carla", papel="MANAGER", motivo="Conferi e devolveram")
    with db.transaction() as con:
        DP.aceitar_recebedor(con, i, agora=AGORA, por="mario", papel="ADMIN",
                             motivo="Conferi no banco: o valor foi devolvido e pago de novo.")
    assert INTER.conciliar(db, cliente=Banco(), por="automação", agora=AGORA)["conciliadas"] == [i]
    with db.connect() as con:
        assert DP.recebedor_em_duvida(con) == []


def test_o_recebedor_que_confere_segue_para_o_livro(cg_casa_logada):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        i = _despesa(con)
        DP.banco(con).escrever("UPDATE dp_despesas SET situacao = %s, banco_codigo = %s, ambiente = %s WHERE id = %s",
                               (DP.ENVIADA, "abc", "sandbox", i))

    class Banco:
        ambiente = "sandbox"

        def extrato(self, inicio, fim):
            return [{"idTransacao": "1", "valor": "1935.32", "dataTransacao": "2026-10-30",
                     "detalhes": {"codigoSolicitacao": "abc", "nomeRecebedor": "Beatriz Exemplo",
                                  "cpfCnpjRecebedor": "***.000.001-**"}}]

    assert INTER.conciliar(db, cliente=Banco(), por="automação", agora=AGORA)["conciliadas"] == [i]

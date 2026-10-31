"""A FOLHA COMO RECORRENTE — último dia útil, valor ajustável e chave Pix no formato do banco.

Ordem do oficial (30/10/2026): «é uma despesa recorrente, valores podem mudar, mas
deixemos sempre pré-carregado» e «pagar último dia útil do mês». As chaves fictícias
usam o CPF de exemplo da casa (tests/fixtures/anti_vazamento/documentos_ficticios.txt).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP
import despesas_recorrentes as RC

AGORA = datetime(2026, 10, 30, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
FOLHA = {"descricao": "Folha de pagamento, salário líquido", "categoria": "PESSOAL",
         "beneficiario_nome": "BEATRIZ EXEMPLO", "beneficiario_documento": "",
         "forma": DP.PIX_CHAVE, "chave_pix": "(99)90000-0000", "valor": 193532,
         "ultimo_dia_util": "1", "dia_vencimento": "", "antecedencia_dias": 10,
         "documento_especie": "Recibo de pagamento", "primeiro_mes": "2026-10", "ultimo_mes": ""}


# ------------------------------------------------------------ a chave Pix

@pytest.mark.parametrize("digitada, certa", [
    ("(99)985000000", "+5599985000000"),
    ("(99) 98500-0000", "+5599985000000"),
    ("99985000000", "+5599985000000"),
    ("+55 99 98500-0000", "+5599985000000"),
    ("5599985000000", "+5599985000000"),
    ("000.000.001-91", "00000000191"),
    ("00000000191", "00000000191"),
    ("Fulano@Example.com", "fulano@example.com"),
    ("123E4567-E89B-12D3-A456-426614174000", "123e4567-e89b-12d3-a456-426614174000"),
])
def test_a_chave_vai_no_formato_que_o_inter_pede(digitada, certa):
    assert DP.normalizar_chave_pix(digitada) == certa


@pytest.mark.parametrize("torta", ["", "12345", "000.000.001-92", "+55 99 1234", "chave solta"])
def test_a_chave_que_nao_se_reconhece_e_recusada(torta):
    with pytest.raises(DP.DespesaError):
        DP.normalizar_chave_pix(torta)


def test_onze_digitos_que_podem_ser_cpf_ou_celular_nao_se_adivinham(monkeypatch):
    """Chave errada é dinheiro na conta de outra pessoa: a pessoa desempata."""
    monkeypatch.setattr(DP.cpf_cnpj, "documento_valido", lambda _d: True)
    with pytest.raises(DP.DespesaError, match="podem ser CPF ou celular"):
        DP.normalizar_chave_pix("99985000000")


# ------------------------------------------------------- o último dia útil

@pytest.mark.parametrize("mes, dia", [
    ("2026-10", date(2026, 10, 30)),     # o dia 31 é sábado
    ("2026-11", date(2026, 11, 30)),
    ("2027-01", date(2027, 1, 29)),      # o dia 31 é domingo
])
def test_o_vencimento_e_o_ultimo_dia_util(mes, dia):
    assert RC.vencimento_do_mes({"ultimo_dia_util": 1, "dia_vencimento": 31}, mes) == dia


def test_o_feriado_local_sai_da_conta():
    r = {"ultimo_dia_util": 1, "dia_vencimento": 31}
    assert RC.vencimento_do_mes(r, "2026-11", {date(2026, 11, 30)}) == date(2026, 11, 27)


def test_sem_a_marca_vale_o_dia_fixo():
    assert RC.vencimento_do_mes({"dia_vencimento": 31}, "2026-10") == date(2026, 10, 31)


def test_com_a_marca_o_dia_nao_e_exigido_e_a_chave_se_padroniza():
    r = RC.conferir(FOLHA)
    assert (r["ultimo_dia_util"], r["dia_vencimento"], r["chave_pix"]) == (1, 31, "+5599900000000")
    with pytest.raises(DP.DespesaError, match="dia do vencimento"):
        RC.conferir({**FOLHA, "ultimo_dia_util": ""})


# ------------------------------------------------------- o valor ajustável

def _carregar(db):
    with db.transaction() as con:
        RC.cadastrar(con, FOLHA, por="beatriz", agora=AGORA)
        [i] = RC.gerar(con, hoje=AGORA.date(), agora=AGORA, por="automação")
    return i


def test_a_folha_se_carrega_no_ultimo_dia_util_e_o_valor_se_ajusta(cg_casa_logada):
    db = cg_casa_logada["db"]
    i = _carregar(db)
    with db.transaction() as con:
        d = DP.ajustar_valor(con, i, valor_centavos=200000, agora=AGORA, por="mario", papel="ADMIN")
    assert (d["valor"], d["vencimento"], d["situacao"]) == (200000, "2026-10-30", DP.AGUARDANDO)
    with db.connect() as con:
        assert "1.935,32" in [e for e in DP.eventos(con, i) if e["operacao"] == "AJUSTAR_VALOR"][0]["mensagem"]
        assert RC.lista(con)[0]["valor"] == 193532, "a recorrente não muda"


def test_autorizada_nao_se_ajusta_e_quem_so_cadastra_nao_ajusta(cg_casa_logada):
    db = cg_casa_logada["db"]
    i = _carregar(db)
    with db.transaction() as con, pytest.raises(DP.DespesaError, match="oficial ou o gerente"):
        DP.ajustar_valor(con, i, valor_centavos=100, agora=AGORA, por="carla", papel="USER")
    with db.transaction() as con:
        DP.autorizar(con, i, agora=AGORA, por="mario", papel="ADMIN", acima_do_teto=True)
    with db.transaction() as con, pytest.raises(DP.DespesaError, match="espera a autorização"):
        DP.ajustar_valor(con, i, valor_centavos=100, agora=AGORA, por="mario", papel="ADMIN")

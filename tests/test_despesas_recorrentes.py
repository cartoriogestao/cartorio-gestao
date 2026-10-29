"""AS DESPESAS RECORRENTES — o Pix que se carrega sozinho e o boleto que se avisa.

Pedido do oficial (28/10/2026): «o sistema me avisa todo mês para pagar; as que
é só Pix, já deixa carregado pendente de confirmação». Pendente de confirmação
é AGUARDANDO a autorização: nada aqui autoriza nem paga.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP
import despesas_automacao as AUT
import despesas_recorrentes as RC

FAVORECIDO = "00000010000127"     # 00.000.010/0001-27, fictício (o de test_despesas)
AGORA = datetime(2026, 10, 28, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
HOJE = AGORA.date()

ALUGUEL = {"descricao": "Aluguel do prédio da serventia", "categoria": "LOCACAO",
           "beneficiario_nome": "LOCADOR FICTICIO", "beneficiario_documento": FAVORECIDO,
           "forma": DP.PIX_CHAVE, "chave_pix": "locador@example.com", "valor": 150000,
           "dia_vencimento": 5, "antecedencia_dias": 10, "documento_especie": "Contrato",
           "primeiro_mes": "2026-10", "ultimo_mes": ""}
ENERGIA = {**ALUGUEL, "descricao": "Energia elétrica do prédio", "categoria": "CONCESSIONARIAS",
           "beneficiario_nome": "DISTRIBUIDORA FICTICIA", "forma": DP.BOLETO, "chave_pix": "",
           "valor": 0, "dia_vencimento": 30, "antecedencia_dias": 7, "documento_especie": "Fatura"}


def _mod11(numero: str) -> int:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(numero)))
    dv = 11 - soma % 11
    return 1 if dv in (0, 10, 11) else dv


def boleto(valor_centavos: int, vencimento: str) -> str:
    """Um código de barras (44) válido, com o fator do calendário novo (o de test_despesas)."""
    fator = (date.fromisoformat(vencimento) - date(2025, 2, 22)).days + 1000
    sem_dv = f"0779{fator:04d}{valor_centavos:010d}7777011657373795603057629"
    return sem_dv[:4] + str(_mod11(sem_dv)) + sem_dv[4:]


@pytest.fixture
def casa(cg_casa_logada):
    return cg_casa_logada


def _gravar(db, dados):
    with db.transaction() as con:
        return RC.cadastrar(con, dados, por="beatriz", agora=AGORA)


def _do_mes(db, hoje=HOJE):
    with db.connect() as con:
        return RC.do_mes(con, hoje)


def _gerar(db, hoje=HOJE):
    with db.transaction() as con:
        return RC.gerar(con, hoje=hoje, agora=AGORA, por="automação")


# ------------------------------------------------------------- o calendário

def test_o_mes_abre_na_antecedencia_e_o_dia_31_cabe_no_mes_curto():
    r = {**ALUGUEL, "id": 1, "primeiro_mes": "2026-11"}
    assert RC.meses_abertos(r, date(2026, 10, 24)) == []
    assert RC.meses_abertos(r, date(2026, 10, 26)) == [("2026-11", date(2026, 11, 5))]
    curto = {**r, "dia_vencimento": 31, "antecedencia_dias": 0}
    assert RC.vencimento_do_mes(curto, "2027-02") == date(2027, 2, 28)


def test_a_vigencia_limita_os_meses():
    r = {**ALUGUEL, "id": 1, "primeiro_mes": "2026-12", "antecedencia_dias": 25}
    assert RC.meses_abertos(r, date(2026, 11, 20)) == [("2026-12", date(2026, 12, 5))]
    acabou = {**ALUGUEL, "id": 1, "ultimo_mes": "2026-10", "antecedencia_dias": 25}
    assert [m for m, _ in RC.meses_abertos(acabou, date(2026, 10, 20))] == ["2026-10"]


def test_o_mes_que_ja_vencia_no_cadastro_nao_abre():
    """Cadastrada em 28/10, a de dia 5 não pede o aluguel de outubro, já pago por fora."""
    r = {**ALUGUEL, "id": 1, "criada_em": "2026-10-28T09:00:00"}
    assert [m for m, _ in RC.meses_abertos(r, date(2026, 10, 28))] == ["2026-11"]


def test_pix_recorrente_sem_chave_ou_sem_valor_e_recusado():
    with pytest.raises(DP.DespesaError, match="chave Pix"):
        RC.conferir({**ALUGUEL, "chave_pix": ""})
    with pytest.raises(DP.DespesaError, match="valor fixo"):
        RC.conferir({**ALUGUEL, "valor": 0})
    with pytest.raises(DP.DespesaError, match="detalhe"):
        RC.conferir({**ALUGUEL, "descricao": "aluguel"})


# ------------------------------------------------ o Pix que se carrega sozinho

def test_o_pix_do_mes_se_carrega_esperando_a_autorizacao_e_uma_vez_so(casa):
    db = casa["db"]
    rid = _gravar(db, ALUGUEL)
    novas = _gerar(db, date(2026, 10, 27))
    assert len(novas) == 1
    with db.connect() as con:
        d = DP.despesa(con, novas[0])
    assert d["situacao"] == DP.AGUARDANDO, "pendente de confirmação, e não autorizada"
    assert (d["valor"], d["vencimento"], d["forma"], d["codigo"]) == \
        (150000, "2026-11-05", DP.PIX_CHAVE, "locador@example.com")
    assert d["origem"] == RC.ORIGEM and d["chave_origem"] == f"{rid}:2026-11"
    assert d["descricao"].endswith("11/2026")
    assert _gerar(db, date(2026, 10, 27)) == [], "o mesmo mês não entra duas vezes"
    assert _do_mes(db, date(2026, 10, 27)) == []


def test_mudar_a_recorrente_nao_mexe_na_despesa_ja_carregada(casa):
    db = casa["db"]
    rid = _gravar(db, ALUGUEL)
    [i] = _gerar(db, date(2026, 10, 27))
    with db.transaction() as con:
        RC.alterar(con, rid, {**ALUGUEL, "valor": 170000}, por="mario", agora=AGORA)
    with db.connect() as con:
        assert DP.despesa(con, i)["valor"] == 150000


def test_encerrada_nao_avisa_nem_carrega(casa):
    db = casa["db"]
    rid = _gravar(db, ALUGUEL)
    with db.transaction() as con:
        RC.encerrar(con, rid, por="mario", agora=AGORA)
    assert _do_mes(db, date(2026, 10, 27)) == [] and _gerar(db, date(2026, 10, 27)) == []


# ------------------------------------------------- o boleto que se avisa

def test_o_boleto_nao_se_carrega_avisa_e_sai_do_aviso_quando_cadastrado(casa):
    db = casa["db"]
    rid = _gravar(db, ENERGIA)
    assert _gerar(db) == []
    [aviso] = _do_mes(db)
    assert (aviso["competencia"], aviso["vencimento"], aviso["carrega_sozinho"]) == \
        ("2026-10", "2026-10-30", False)
    with db.connect() as con:
        r = RC.recorrente(con, rid)
    f = RC.para_o_formulario(r, "2026-10")
    with db.transaction() as con:
        origem, chave = RC.origem_do_formulario(con, f["recorrente_id"], f["competencia"])
        DP.cadastrar(con, agora=AGORA, por="beatriz", origem=origem, chave_origem=chave,
                     beneficiario_nome=f["beneficiario_nome"],
                     beneficiario_documento=f["beneficiario_documento"], valor_centavos=23456,
                     vencimento=f["vencimento"], forma=DP.BOLETO,
                     codigo=boleto(23456, f["vencimento"]), descricao=f["descricao"],
                     categoria=f["categoria"], documento_especie=f["documento_especie"])
    assert _do_mes(db) == []


def test_o_formulario_sem_recorrente_continua_manual(casa):
    with casa["db"].connect() as con:
        assert RC.origem_do_formulario(con, "", "") == ("MANUAL", None)


# ------------------------------------------------------------ a automação

class _Contexto:
    def __init__(self, db, pode_agir=True, agora=AGORA):
        self.db, self.agora, self.pasta_dados = db, agora, None
        self.processo = {"pode_agir": pode_agir}


def test_sem_pode_agir_o_processo_so_conta(casa):
    db = casa["db"]
    _gravar(db, ALUGUEL)
    r = AUT.recorrentes(_Contexto(db, pode_agir=False,
                                  agora=AGORA.replace(day=27)))
    assert r["situacao"] == "AVISO" and r["acoes"] == []
    with db.connect() as con:
        assert DP.listar(con) == []


def test_o_processo_carrega_o_pix_e_avisa_o_boleto(casa):
    db = casa["db"]
    _gravar(db, ALUGUEL)
    _gravar(db, ENERGIA)
    r = AUT.recorrentes(_Contexto(db, agora=AGORA.replace(day=27)))
    assert r["situacao"] == "AVISO" and len(r["acoes"]) == 1
    assert [a["tipo"] for a in r["achados"]] == ["RECORRENTE_A_CADASTRAR"]


def test_o_processo_entra_no_catalogo_da_automacao():
    import automacao_processos as PROC
    assert "DESPESAS_RECORRENTES" in {s["codigo"] for s in PROC.todas_as_sementes()}


# ------------------------------------------------------------------ telas

def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def test_as_telas_abrem_e_a_recorrente_se_cadastra_pela_tela(casa):
    c, db = casa["c"], casa["db"]
    for url in ("/administrativo/despesas/recorrentes",
                "/administrativo/despesas/recorrentes/nova", "/administrativo/despesas"):
        assert c.get(url).status_code == 200, url
    dados = {**ENERGIA, "valor": "", "dia_vencimento": "30", "antecedencia_dias": "7"}
    r = c.post("/administrativo/despesas/recorrentes/nova",
               data={"csrf_token": _token(c, "/administrativo/despesas/recorrentes/nova"),
                     **dados}, follow_redirects=True)
    assert r.status_code == 200 and "Energia elétrica do prédio" in r.get_data(as_text=True)
    with db.connect() as con:
        [rec] = RC.lista(con)
    pagina = c.get(f"/administrativo/despesas/nova?recorrente_id={rec['id']}&competencia=2026-10")
    texto = pagina.get_data(as_text=True)
    assert "DISTRIBUIDORA FICTICIA" in texto and "2026-10-30" in texto
    assert f'name="recorrente_id" value="{rec["id"]}"' in texto

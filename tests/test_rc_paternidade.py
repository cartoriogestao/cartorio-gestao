"""O termo de paternidade no nascimento sem o pai — 23/10/2026.

Lei nº 8.560/1992, art. 2º: no registro só com a maternidade estabelecida, o
oficial remete ao juiz o nome, a profissão, a identidade e a residência do
suposto pai. O código de normas dá a forma — o termo de alegação, e o termo
negativo quando a mãe se recusa a indicar.

O QUE ESTES TESTES GUARDAM
      - nascimento do balcão com a mãe declarada e o pai IGNORADO **não se
        lavra** sem um dos dois termos, e nada fica gravado;
      - o termo nasce **na mesma transação** do assento, citando livro, folha
        e número;
      - a alegação exige o nome do suposto pai; o negativo não guarda dados de
        suposto pai nenhum;
      - pai declarado, ou carga do acervo, não são alcançados;
      - só a alegação se remete ao juiz, uma vez, e o painel a mostra até lá;
      - a TERCEIRA saída (27/10/2026, decisão do oficial): a mãe não
        compareceu — exige o motivo, recusa quando a declarante é a própria
        mãe, não guarda suposto pai, não tem termo para assinar, não se
        remete e não entra no painel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import inacabados as IN                           # noqa: E402
import rc_assento as RC                           # noqa: E402
import rc_paternidade as RP                       # noqa: E402
from ex_schema import init_ex_schema              # noqa: E402
from test_rc_assento import banco, nascimento     # noqa: E402

PAI_DECLARADO = [
    {"papel": "REGISTRADO", "nome": "JOÃO DA SILVA", "sexo": "M"},
    {"papel": "MAE", "nome": "MARIA DA SILVA"},
    {"papel": "PAI", "nome": "JOSÉ DA SILVA"},
    {"papel": "DECLARANTE", "nome": "MARIA DA SILVA"},
]
ALEGACAO = {"tipo": "ALEGACAO", "suposto_pai_nome": "PEDRO EXEMPLO",
            "suposto_pai_profissao": "lavrador",
            "suposto_pai_documento": "0000000 SSP/MA",
            "suposto_pai_residencia": "Povoado Exemplo, zona rural"}


def _quantos(con, tabela: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


# ------------------------------------------------------------- a trava


def test_sem_o_termo_o_nascimento_sem_pai_nao_se_lavra():
    con = banco()
    with pytest.raises(RC.RcError, match="termo de alegação de paternidade"):
        nascimento(con, paternidade=None)
    assert _quantos(con, "rc_assentos") == 0
    assert _quantos(con, "rc_termos_paternidade") == 0


def test_a_alegacao_exige_o_nome_do_suposto_pai():
    con = banco()
    with pytest.raises(RC.RcError, match="nome do suposto pai"):
        nascimento(con, paternidade={"tipo": "ALEGACAO"})
    assert _quantos(con, "rc_assentos") == 0


def test_o_termo_de_alegacao_nasce_com_o_assento_e_cita_o_livro():
    con = banco()
    r = nascimento(con, paternidade=ALEGACAO)
    termo = RP.do_assento(con, r["assento_id"])
    assert termo["tipo"] == "ALEGACAO"
    assert termo["suposto_pai_nome"] == "PEDRO EXEMPLO"
    assert "TERMO DE ALEGAÇÃO DE PATERNIDADE" in termo["teor"]
    assert "MARIA DA SILVA, mãe de JOÃO DA SILVA" in termo["teor"]
    assert "nascido(a) em 20/08/2026" in termo["teor"]
    assert f"sob o n.º {r['numero_ordem']}" in termo["teor"]
    assert "PEDRO EXEMPLO, profissão lavrador" in termo["teor"]
    assert "Lei nº 8.560/1992, art. 2º" in termo["teor"]
    assert termo["remetido_em"] is None


def test_o_termo_negativo_nao_guarda_suposto_pai():
    con = banco()
    r = nascimento(con, paternidade={"paternidade_tipo": "NEGATIVO",
                                     "suposto_pai_nome": "QUALQUER"})
    termo = RP.do_assento(con, r["assento_id"])
    assert termo["tipo"] == "NEGATIVO"
    assert termo["suposto_pai_nome"] is None
    assert "TERMO NEGATIVO DE ALEGAÇÃO DE PATERNIDADE" in termo["teor"]
    assert "recusou-se a fazê-lo" in termo["teor"]
    assert "pasta própria" in termo["teor"]


def test_pai_declarado_nao_exige_termo_e_recusa_o_que_vier():
    con = banco()
    r = nascimento(con, pessoas=PAI_DECLARADO)
    assert RP.do_assento(con, r["assento_id"]) is None
    with pytest.raises(RC.RcError, match="o pai está declarado"):
        nascimento(con, nome="OUTRO", pessoas=PAI_DECLARADO,
                   paternidade={"tipo": "NEGATIVO"})


def test_a_carga_do_acervo_nao_e_alcancada():
    assert not RP.exige_termo("NASCIMENTO", [
        {"papel": "MAE", "nome": "MARIA"}, {"papel": "PAI", "nome": "IGNORADO"}],
        "EOFICIO")
    assert not RP.exige_termo("OBITO", [
        {"papel": "MAE", "nome": "MARIA"}, {"papel": "PAI", "nome": "IGNORADO"}],
        "MANUAL")
    # mãe também ignorada (criança achada): não há quem alegue
    assert not RP.exige_termo("NASCIMENTO", [
        {"papel": "MAE", "nome": "IGNORADO"}, {"papel": "PAI", "nome": "IGNORADO"}],
        "MANUAL")


# ------------------------------------------------------------ a remessa


def test_so_a_alegacao_se_remete_e_uma_vez():
    con = banco()
    r = nascimento(con, paternidade=ALEGACAO)
    feito = RP.registrar_remessa(con, r["assento_id"], processo="0800000-00.2026.8.10.0000",
                                 data="2026-08-25", agora="2026-08-25T10:00:00",
                                 usuario="MARIO EXEMPLO DOS SANTOS")
    assert feito["remetido_em"] == "2026-08-25"
    assert RP.do_assento(con, r["assento_id"])["remessa_processo"].startswith("0800000")
    with pytest.raises(RP.PaternidadeError, match="já foi remetido"):
        RP.registrar_remessa(con, r["assento_id"], processo="X", data="2026-08-26",
                             agora="2026-08-26T10:00:00")
    negativo = nascimento(con, nome="MARIA", paternidade={"tipo": "NEGATIVO"})
    with pytest.raises(RP.PaternidadeError, match="não se remete"):
        RP.registrar_remessa(con, negativo["assento_id"], processo="X",
                             data="2026-08-26", agora="2026-08-26T10:00:00")


def test_a_alegacao_nao_remetida_aparece_no_painel_ate_ser_remetida():
    con = banco()
    init_ex_schema(con)
    r = nascimento(con, paternidade=ALEGACAO)
    itens = [x for x in IN.lista(con, hoje="2026-09-20", chave="RCPN_ALEGACAO_PATERNIDADE")
             if x["chave"] == "RCPN_ALEGACAO_PATERNIDADE"]
    assert len(itens) == 1
    assert itens[0]["id"] == r["assento_id"]
    assert itens[0]["parado"] is True                # passou dos 20 dias
    RP.registrar_remessa(con, r["assento_id"], processo="0800000",
                         data="2026-09-20", agora="2026-09-20T10:00:00")
    assert not [x for x in IN.lista(con, hoje="2026-09-20", chave="RCPN_ALEGACAO_PATERNIDADE")
                if x["chave"] == "RCPN_ALEGACAO_PATERNIDADE"]


# ------------------------------------- a mãe não compareceu (27/10/2026)
#
#   Quem declara é a avó (ou o hospital, ou o próprio registrado no tardio):
#   a mãe não está no balcão, e nem a alegação nem o negativo são verdade.

AVO_DECLARA = [
    {"papel": "REGISTRADO", "nome": "JOÃO DA SILVA", "sexo": "M"},
    {"papel": "MAE", "nome": "MARIA DA SILVA"},
    {"papel": "PAI", "nome": "IGNORADO"},
    {"papel": "DECLARANTE", "nome": "ANA AVÓ EXEMPLO"},
]
MAE_AUSENTE = {"paternidade_tipo": "MAE_AUSENTE",
               "motivo_ausencia_mae": "mãe falecida no parto"}


def test_a_mae_ausente_exige_o_motivo_e_nada_fica_gravado():
    con = banco()
    for motivo in ("", "  ", "x"):
        with pytest.raises(RC.RcError, match="precisa do motivo"):
            nascimento(con, pessoas=AVO_DECLARA,
                       paternidade={"tipo": "MAE_AUSENTE",
                                    "motivo_ausencia_mae": motivo})
    assert _quantos(con, "rc_assentos") == 0
    assert _quantos(con, "rc_termos_paternidade") == 0


def test_o_motivo_e_texto_curto():
    con = banco()
    with pytest.raises(RC.RcError, match="texto curto"):
        nascimento(con, pessoas=AVO_DECLARA,
                   paternidade={"tipo": "MAE_AUSENTE",
                                "motivo_ausencia_mae": "a" * 301})
    assert _quantos(con, "rc_assentos") == 0


def test_se_a_declarante_e_a_mae_ela_esta_no_balcao():
    con = banco()
    # o ajudante `nascimento` monta a mãe como declarante
    with pytest.raises(RC.RcError, match="a própria mãe"):
        nascimento(con, paternidade=dict(MAE_AUSENTE))
    assert _quantos(con, "rc_assentos") == 0


def test_a_mae_ausente_grava_o_motivo_sem_suposto_pai_nem_termo_a_assinar():
    con = banco()
    r = nascimento(con, pessoas=AVO_DECLARA,
                   paternidade={**MAE_AUSENTE, "suposto_pai_nome": "QUALQUER"})
    termo = RP.do_assento(con, r["assento_id"])
    assert termo["tipo"] == "MAE_AUSENTE"
    assert termo["motivo_ausencia_mae"] == "mãe falecida no parto"
    assert termo["suposto_pai_nome"] is None
    assert termo["tem_termo"] is False
    assert termo["nome_do_tipo"] == "Mãe não compareceu — averiguação não iniciada"
    assert termo["anotacao"] == ("mãe não compareceu — averiguação não "
                                 "iniciada: mãe falecida no parto")
    assert "MÃE NÃO COMPARECEU — AVERIGUAÇÃO NÃO INICIADA" in termo["teor"]
    assert "Motivo informado: mãe falecida no parto." in termo["teor"]
    assert "Declarante: ANA AVÓ EXEMPLO." in termo["teor"]
    assert f"sob o n.º {r['numero_ordem']}" in termo["teor"]
    # não é termo: não há quem assine
    assert "assina com o oficial" not in termo["teor"]


def test_os_dois_termos_continuam_tendo_papel_e_sem_anotacao():
    con = banco()
    r = nascimento(con, paternidade=ALEGACAO)
    termo = RP.do_assento(con, r["assento_id"])
    assert termo["tem_termo"] is True
    assert termo["anotacao"] == ""
    assert termo["motivo_ausencia_mae"] is None
    neg = nascimento(con, nome="OUTRO", paternidade={
        "tipo": "NEGATIVO", "motivo_ausencia_mae": "não vale aqui"})
    assert RP.do_assento(con, neg["assento_id"])["motivo_ausencia_mae"] is None


def test_a_mae_ausente_nao_se_remete_e_nao_entra_no_painel():
    con = banco()
    init_ex_schema(con)
    r = nascimento(con, pessoas=AVO_DECLARA, paternidade=dict(MAE_AUSENTE))
    with pytest.raises(RP.PaternidadeError, match="mãe não compareceu"):
        RP.registrar_remessa(con, r["assento_id"], processo="X",
                             data="2026-09-20", agora="2026-09-20T10:00:00")
    assert not [x for x in IN.lista(con, hoje="2026-12-31",
                                    chave="RCPN_ALEGACAO_PATERNIDADE")
                if x["chave"] == "RCPN_ALEGACAO_PATERNIDADE"]


def test_a_recusa_sem_escolha_oferece_as_tres_saidas():
    con = banco()
    with pytest.raises(RC.RcError) as erro:
        nascimento(con, paternidade=None)
    assert "a mãe não compareceu" in str(erro.value)


def test_o_assento_cancelado_tira_a_alegacao_do_painel():
    # 27/10/2026: o selo do nascimento falhou, a rota cancelou o assento, e o
    # termo ficava no painel de inacabados para sempre.
    con = banco()
    init_ex_schema(con)
    r = nascimento(con, paternidade=ALEGACAO)
    con.execute("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=?", (r["assento_id"],))
    assert not [x for x in IN.lista(con, hoje="2026-09-20", chave="RCPN_ALEGACAO_PATERNIDADE")
                if x["chave"] == "RCPN_ALEGACAO_PATERNIDADE"]

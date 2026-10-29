"""
Ato DESFEITO não vai à CRA — e o que já foi informado e depois desfeito
aparece na tela, como aviso.

POR QUE ESTES TESTES EXISTEM (28/10/2026)
    `protesto_retorno.pendentes` não olhava `pt_atos.cancelado`. No título
    1353 da produção o CANCELAMENTO foi lavrado e desfeito às 13h57 porque o
    selo não saiu; às 14h32 o retorno saiu dizendo «A — protesto cancelado»,
    a CRA aceitou, e hoje a Central diz «cancelado» enquanto o livro diz
    «protestado». Medido no mesmo dia: 19 atos desfeitos já informados.

O QUE ELES CONFEREM
    - o ato desfeito sai da lista do RETORNO e da do ANDAMENTO;
    - `gerar` não o marca como informado nem o põe no arquivo;
    - o apontamento desfeito não dá a data de entrada;
    - `informados_e_desfeitos` acha o ato que foi num arquivo e depois foi
      desfeito, diz se o título tem outro ato válido do mesmo tipo, e NÃO
      escreve nada (não reenvia nada sozinho).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import juntar_prova  # noqa: E402

import protesto as PT  # noqa: E402
import protesto_retorno as PR  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-10-28T13:57:00"
HOJE = "2026-10-28"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, numero="1/1", apresentante="001") -> int:
    dados = {
        "apresentante_codigo": apresentante,
        "apresentante_nome": "BANCO EXEMPLO",
        "especie": "DMI", "numero_titulo": numero,
        "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1.200,00", "saldo": "1.310,45",
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA EXEMPLO LTDA",
                    "documento": "00000001000055"},
        "devedores": [{"nome": "FULANO DE TAL EXEMPLO", "CPF": "00000000191",
                       "enderecos": [{"endereco": "RUA EXEMPLO, 10",
                                      "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    return PT.cadastrar_titulo(con, dados, origem="CRA",
                               origem_chave=f"lote:{numero}", agora=AGORA)


def ate_o_protesto(con, titulo_id: int) -> None:
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA)
    juntar_prova(con, titulo_id)   # a prova da intimação (29/10/2026)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")


def ato_id(con, titulo_id: int, tipo: str) -> int:
    return int(con.execute(
        "SELECT id FROM pt_atos WHERE titulo_id=? AND tipo=? ORDER BY id DESC",
        (titulo_id, tipo)).fetchone()[0])


def desfazer(con, ato: int, motivo="Selo não emitido: teste") -> None:
    # Como a tela desfaz quando o selo não sai (atribuicoes_web).
    con.execute("UPDATE pt_atos SET cancelado=1, motivo_cancelamento=? "
                "WHERE id=?", (motivo, ato))


# --------------------------------------------------- a lista de pendentes


def test_o_ato_desfeito_nao_entra_no_retorno():
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    desfazer(con, ato_id(con, tid, "PROTESTO"))
    assert PR.pendentes(con) == []
    assert PR.apresentantes_pendentes(con) == []


def test_o_apontamento_desfeito_nao_entra_no_andamento():
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    desfazer(con, ato_id(con, tid, "APONTAMENTO"))
    assert PR.pendentes(con, tipo="SDTBFOAND") == []


def test_so_o_desfeito_sai_e_o_valido_continua():
    con = banco()
    a = titulo(con, numero="1/1")
    b = titulo(con, numero="2/1")
    ate_o_protesto(con, a)
    ate_o_protesto(con, b)
    desfazer(con, ato_id(con, a, "PROTESTO"))
    assert [p["titulo_id"] for p in PR.pendentes(con)] == [b]


def test_o_caso_do_titulo_1353_cancelamento_desfeito_nao_sai_como_A():
    # O caso real: protesto informado, cancelamento lavrado e desfeito porque
    # o selo não saiu. O retorno seguinte NÃO pode dizer «A».
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    # O cancelamento como ficou depois de desfeito: lavrado, e anulado.
    con.execute(
        "INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em, cancelado, "
        "motivo_cancelamento) VALUES (?, 'CANCELAMENTO', ?, ?, 1, ?)",
        (tid, AGORA, AGORA, "Selo não emitido: teste"))
    assert PR.pendentes(con) == []
    with pytest.raises(PR.RetornoError) as erro:
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    assert "Não há ato novo" in str(erro.value)


def test_gerar_nao_marca_nem_leva_o_ato_desfeito():
    con = banco()
    a = titulo(con, numero="1/1")
    b = titulo(con, numero="2/1")
    ate_o_protesto(con, a)
    ate_o_protesto(con, b)
    desfeito = ato_id(con, a, "PROTESTO")
    desfazer(con, desfeito)
    r = PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                 marca="A", tipos=("SDTBFORTP",))
    assert [x["ato_id"] for x in r["atos"]] == [ato_id(con, b, "PROTESTO")]
    assert len(r["arquivo"].titulos) == 1
    assert con.execute("SELECT retorno_id FROM pt_atos WHERE id=?",
                       (desfeito,)).fetchone()[0] is None


def test_o_apontamento_desfeito_nao_da_a_data_de_entrada():
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    apontamento = ato_id(con, tid, "APONTAMENTO")
    con.execute("UPDATE pt_atos SET data_ato='2026-01-01' WHERE id=?",
                (apontamento,))
    desfazer(con, apontamento)
    [p] = PR.pendentes(con)
    # Sem apontamento válido não há data de entrada; `montar` cai na do ato.
    assert p["data_entrada"] is None


# ------------------------------- informado à CRA e depois desfeito: o aviso


def test_o_ato_informado_e_depois_desfeito_aparece_no_aviso():
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    r = PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                 marca="A", tipos=("SDTBFORTP",))
    protesto = ato_id(con, tid, "PROTESTO")
    assert PR.informados_e_desfeitos(con) == []
    desfazer(con, protesto, motivo="TORNADO SEM EFEITO — teste")
    [d] = PR.informados_e_desfeitos(con)
    assert d["ato_id"] == protesto
    assert d["tipo"] == "PROTESTO"
    assert d["retorno_id"] == r["retorno_id"]
    assert d["nome_arquivo"] == r["nome_arquivo"]
    assert d["cra_enviado_em"] is None          # gerado e ainda não enviado
    assert d["ato_valido_id"] is None           # nenhum outro protesto válido
    assert d["motivo_cancelamento"].startswith("TORNADO SEM EFEITO")


def test_o_aviso_diz_quando_ha_outro_ato_valido_do_mesmo_tipo():
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
             marca="A", tipos=("SDTBFORTP",))
    velho = ato_id(con, tid, "PROTESTO")
    desfazer(con, velho, motivo="TORNADO SEM EFEITO — teste")
    con.execute(
        "INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em) "
        "VALUES (?, 'PROTESTO', ?, ?)", (tid, AGORA, AGORA))
    novo = ato_id(con, tid, "PROTESTO")
    [d] = PR.informados_e_desfeitos(con)
    assert d["ato_id"] == velho
    assert d["ato_valido_id"] == novo
    assert d["ato_valido_retorno_id"] is None   # o novo ainda não foi
    # O ARQUIVO SEM RESPOSTA SEGURA O NOVO — decisão do oficial, 29/10/2026.
    # Até aqui o novo seguia direto para o próximo retorno; mas o arquivo do
    # velho ainda não subiu e leva o «C» do mesmo título — se subir, a CRA o
    # grava, e o segundo «C» seria recusado com 2161. Recusado aquele
    # arquivo, o novo se solta; o velho não volta nunca.
    assert PR.pendentes(con) == []
    assert novo in [p["ato_id"] for p in PR.ja_aceitas_fora_da_fila(con)]
    con.execute(
        """UPDATE pt_retornos SET cra_recusado_em=?, cra_recusa_codigo='2161'
            WHERE tipo='SDTBFORTP'""", (AGORA,))
    assert [p["ato_id"] for p in PR.pendentes(con)] == [novo]


def test_o_aviso_filtra_por_apresentante():
    con = banco()
    a = titulo(con, numero="1/1", apresentante="001")
    ate_o_protesto(con, a)
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
             marca="A", tipos=("SDTBFORTP",))
    desfazer(con, ato_id(con, a, "PROTESTO"))
    assert len(PR.informados_e_desfeitos(con, apresentante_codigo="001")) == 1
    assert PR.informados_e_desfeitos(con, apresentante_codigo="002") == []


def test_o_aviso_so_le_e_nao_reenvia_nada():
    # Nada se reenvia sozinho: a função não grava retorno nem mexe em ato.
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
             marca="A", tipos=("SDTBFORTP",))
    desfazer(con, ato_id(con, tid, "PROTESTO"))
    antes_ret = con.execute("SELECT count(*) FROM pt_retornos").fetchone()[0]
    antes_atos = [tuple(r) for r in con.execute(
        "SELECT id, cancelado, retorno_id FROM pt_atos ORDER BY id")]
    PR.informados_e_desfeitos(con)
    assert con.execute("SELECT count(*) FROM pt_retornos").fetchone()[0] \
        == antes_ret
    assert [tuple(r) for r in con.execute(
        "SELECT id, cancelado, retorno_id FROM pt_atos ORDER BY id")] \
        == antes_atos

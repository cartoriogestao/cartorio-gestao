"""Selo da intimação já lavrada e selo do desfecho só depois do caixa."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from banco_de_teste import conexao_de_teste  # noqa: E402

import ato_selado as AS  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_selo_do_desfecho as PSD  # noqa: E402
import protesto_selo_intimacao as PSI  # noqa: E402
import rotas_do_robo as RR  # noqa: E402
import selador_config as SC  # noqa: E402
from bd_nativo import banco as nativo  # noqa: E402
from caixa_schema import init_caixa_schema  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-11-07T16:00:00"
HOJE = "2026-11-07"
VIGENCIA = 9401


def _tabela(bd) -> None:
    bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
                   VALUES (%s, 'tabela do selo da intimação', 1,
                           '2026-01-02', NULL)""", (VIGENCIA,))
    bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                   VALUES (9402, '17.2', 'Intimação ou edital por título')""")
    bd.escrever(
        """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
               ferc, femp, fadep, ferrfis, total)
           VALUES (9402,%s,'11,96','0,00','0,00','0,00','0,00','11,96')""",
        (VIGENCIA,))
    bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                   VALUES (9404, '17.4.6', 'Desistência — faixa')""")
    bd.escrever(
        """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
               ferc, femp, fadep, ferrfis, total)
           VALUES (9404,%s,'84,25','0,00','0,00','0,00','0,00','84,25')""",
        (VIGENCIA,))


def _banco():
    con = conexao_de_teste()
    init_nucleo_schema(con)
    for tabela in ("users", "ri_protocolos", "ri_matriculas"):
        con.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    init_pt_schema(con)
    SC.init_selador_schema(con)
    AS.init_trava_do_selo_schema(con)
    _tabela(nativo(con))
    return con


def _dados(numero: str) -> dict:
    return {"especie": "DMI", "numero_titulo": numero,
            "data_emissao": "2025-12-01", "data_vencimento": "2025-12-20",
            "valor": "1482.78", "saldo": "1482.78",
            "praca_protesto": "CIDADE EXEMPLO", "tipo_moeda": "1",
            "tipo_protesto": "C", "motivo_protesto": "1",
            "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                        "cidade": "Cidade Exemplo", "uf": "MA"},
            "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": "00000000000",
                           "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}]}


def _titulo(con, *, origem: str, chave: str) -> int:
    return PT.cadastrar_titulo(
        con, _dados(f"TINT/{chave}"), origem=origem,
        origem_chave=None if origem == "MANUAL" else f"TINT:{chave}",
        agora=AGORA)


def _intimacao(con, tid, *, origem="MANUAL", selo=None) -> int:
    novo = nativo(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               selo, cancelado, criado_em)
           VALUES (%s,'INTIMACAO',%s,'{"modo": "EDITAL"}',%s,%s,0,%s)
           RETURNING id""",
        (tid, HOJE, origem, selo, AGORA))
    nativo(con).escrever(
        "UPDATE pt_titulos SET situacao='PROTESTADO' WHERE id=%s", (int(tid),))
    return int(novo[0]["id"])


def test_a_intimacao_da_casa_entra_e_o_acervo_fica_de_fora():
    con = _banco()
    casa = _intimacao(con, _titulo(con, origem="CRA", chave="casa"))
    acervo = _intimacao(con, _titulo(con, origem="CRA", chave="acervo"),
                        origem="EOFICIO")
    quadro = PSI.pendentes(con, hoje=HOJE)
    assert {p["ato_id"] for p in quadro["selaveis"]} == {casa}
    assert acervo in {p["ato_id"] for p in quadro["de_fora"]}
    assert quadro["selaveis"][0]["codigo_tj"] == "17.2"


def test_preparar_deixa_o_17_2_devido_e_recusa_o_robo():
    con = _banco()
    casa = _intimacao(con, _titulo(con, origem="CRA", chave="devido"))
    with pytest.raises(PSI.SeloIntimacaoError, match="Robô não sela"):
        PSI.preparar(con, eh_robo=True, usuario="Robo", agora=AGORA, hoje=HOJE)
    pronto = PSI.preparar(con, eh_robo=False, usuario="MARIO EXEMPLO",
                          agora=AGORA, hoje=HOJE, ato_id=casa)
    assert [p["ato_id"] for p in pronto["prontos"]] == [casa]
    devido = nativo(con).ler(
        "SELECT ato_id, situacao FROM pt_emolumentos_diferidos")
    assert devido == [{"ato_id": casa, "situacao": "PENDENTE"}]
    assert nativo(con).ler("SELECT id FROM cx_lancamentos") == []
    assert "protesto_selar_intimacoes" not in RR.ROTAS_PERMITIDAS_AO_ROBO


def _desistencia(con, tid) -> int:
    novo = nativo(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               cancelado, criado_em)
           VALUES (%s,'DESISTENCIA',%s,'{}','CRA',0,%s) RETURNING id""",
        (tid, HOJE, AGORA))
    nativo(con).escrever(
        "UPDATE pt_titulos SET situacao='DESISTIDO' WHERE id=%s", (int(tid),))
    return int(novo[0]["id"])


def _pagar(con, ato_id: int) -> None:
    bd = nativo(con)
    bd.escrever(
        """INSERT INTO pt_emolumentos_diferidos(
               titulo_id, ato_id, tipo_ato, servico, quantidade, descricao,
               data_do_ato, situacao, criado_em)
           SELECT titulo_id, id, 'DESISTENCIA', 9404, 1, '17.4.6',
                  %s, 'COBRADO', %s
             FROM pt_atos WHERE id=%s""",
        (HOJE, AGORA, ato_id))
    bd.escrever(
        """INSERT INTO cx_lancamentos(
               data, natureza, sentido, valor, origem, origem_chave, criado_em)
           VALUES (%s,'RECEITA','ENTRADA','84,25','ATO',%s,%s)""",
        (HOJE, f"pt_atos:{ato_id}:9404", AGORA))


def test_o_desfecho_so_entra_na_fila_depois_do_caixa():
    con = _banco()
    sem = _desistencia(con, _titulo(con, origem="CRA", chave="sem"))
    com = _desistencia(con, _titulo(con, origem="CRA", chave="com"))
    _pagar(con, com)
    quadro = PSD.pendentes(con)
    assert {p["ato_id"] for p in quadro["esperando"]} == {sem}
    assert {p["ato_id"] for p in quadro["selaveis"]} == {com}
    with pytest.raises(PSD.SeloDesfechoError, match="pagamento no caixa"):
        PSD.preparar(con, eh_robo=False, usuario="MARIO", agora=AGORA,
                     ato_id=sem)
    pronto = PSD.preparar(con, eh_robo=False, usuario="MARIO", agora=AGORA,
                          ato_id=com)
    assert pronto["prontos"][0]["codigo_tj"] == "17.4.6"
    assert nativo(con).valor(
        "SELECT COUNT(*) FROM pt_emolumentos_diferidos WHERE situacao='PENDENTE'"
    ) == 0
    assert "protesto_selar_desfecho" not in RR.ROTAS_PERMITIDAS_AO_ROBO

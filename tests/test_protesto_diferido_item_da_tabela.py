"""
O título da CRA e da CENPROT lança sem caixa e sem protocolo do balcão (#272).

O RELATO (03/11/2026)
    «Ato NÃO lançado, e nada foi gravado: o protesto sela pelos itens da
    tabela de emolumentos, e este lançamento não tem item marcado para
    cobrança nem protocolo do balcão com item» — num título que veio pela
    CRA. O balcão: «entrada de protocolo que vem pela CRA e CENPROT não tem
    protocolo, e os emolumentos são diferidos». A trava do selo prévio (#103)
    pedia item no caixa ou protocolo do balcão, e a tela não deixava marcar
    (sem caixa aberto a caixa de marcar fica apagada; o 17.1 é cabeçalho de
    faixa, sem caixa nenhuma).

O QUE ESTES TESTES GUARDAM
      - o item sai da TABELA: o protesto, pelo 17.1.N da faixa do valor do
        título; a intimação, pelo 17.2 — na CRA e na CENPROT;
      - o título do balcão (antecipado, pago na hora) não ganha item nenhum:
        a trava dele fica como está;
      - valor acima do teto, sem faixa, ou sem vigência: lista vazia, e a
        trava continua — lista vazia é «não sei», não é zero;
      - pela tela: o protesto do título da CRA e o da CENPROT, sem caixa
        aberto e sem nada marcado, LAVRA, sela pelo 17.1, fica DEVIDO pelo
        17.1.N e não entra no caixa — com a trava do selo pago LIGADA e sem
        protocolo de bancada nenhum;
      - o título do balcão, sem item, continua recusado e nada se grava;
      - o robô não ganha item da tabela e não sela.

Dados todos fictícios.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import juntar_prova  # noqa: E402

import protesto as PT                            # noqa: E402
import protesto_posteriori as POST               # noqa: E402
import protesto_selo_previo as PSELO             # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from caixa_schema import init_caixa_schema       # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-08-31T15:00:00"
HOJE = "2026-11-03"
MOTIVO = "Cenário de teste: tríduo vencido"
VIGENCIA = 9301
#: serviço, código do TJ, descrição, preço — a faixa do 17.1 e o 17.2.
SERVICOS = ((9314, "17.1.4", "Protesto — faixa 4", "40,00"),
            (9315, "17.1.5", "Protesto — faixa 5", "55,00"),
            (9316, "17.1.6", "Protesto — faixa 6", "70,00"),
            (9320, "17.2", "Intimação ou edital por título", "9,00"))
#: de, até, código — em reais, como a tabela importada guarda.
FAIXAS = (("500,01", "1.000,00", "17.1.4"),
          ("1.000,01", "2.000,00", "17.1.5"),
          ("2.000,01", "5.000,00", "17.1.6"))


def _tabela(bd) -> None:
    bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
                   VALUES (%s, 'tabela de teste', 1, '2026-01-02', NULL)""",
                (VIGENCIA,))
    for codigo, tj, descricao, preco in SERVICOS:
        bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                       VALUES (%s,%s,%s)""", (codigo, tj, descricao))
        bd.escrever(
            """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (%s,%s,%s,'0,00','0,00','0,00','0,00',%s)""",
            (codigo, VIGENCIA, preco, preco))
    for de, ate, tj in FAIXAS:
        bd.escrever("""INSERT INTO cx_faixas(tabela, vigencia, de, ate, codigo_tj)
                       VALUES (17, %s, %s, %s, %s)""", (VIGENCIA, de, ate, tj))


# ------------------------------------------------------------- de domínio


def _banco():
    con = conexao_de_teste()
    init_nucleo_schema(con)
    for tabela in ("users", "ri_protocolos", "ri_matriculas"):
        con.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    init_pt_schema(con)
    _tabela(nativo(con))
    return con


def _dados(numero: str, valor: str, vencimento: str) -> dict:
    return {"especie": "DMI", "numero_titulo": numero,
            "data_emissao": "2025-12-01", "data_vencimento": vencimento,
            "valor": valor, "saldo": valor, "praca_protesto": "CIDADE EXEMPLO",
            "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
            "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                        "cidade": "Cidade Exemplo", "uf": "MA"},
            "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": "00000000000",
                           "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}]}


def _titulo(con, *, origem: str, valor: str = "1482.78",
            vencimento: str = "2025-12-20") -> int:
    numero = f"T272/{origem}/{valor}"
    return PT.cadastrar_titulo(
        con, _dados(numero, valor, vencimento), origem=origem,
        origem_chave=None if origem == "MANUAL" else f"T272:{origem}:{valor}",
        agora=AGORA)


@pytest.mark.parametrize("origem", ["CRA", "CENPROT"])
def test_o_protesto_do_titulo_da_central_tira_o_17_1_da_faixa_do_valor(origem):
    con = _banco()
    tid = _titulo(con, origem=origem)
    assert POST.itens_do_ato_pela_tabela(con, tid, "PROTESTO", data=HOJE) == [
        {"servico": 9315, "codigo_tj": "17.1.5",
         "descricao": "Protesto — faixa 5", "quantidade": 1}]


@pytest.mark.parametrize("origem", ["CRA", "CENPROT"])
def test_a_intimacao_do_titulo_da_central_tira_o_17_2(origem):
    con = _banco()
    tid = _titulo(con, origem=origem)
    [item] = POST.itens_do_ato_pela_tabela(con, tid, "INTIMACAO", data=HOJE)
    assert (item["servico"], item["codigo_tj"]) == (9320, "17.2")


def test_a_faixa_compara_em_centavos_nas_bordas():
    con = _banco()
    no_teto = _titulo(con, origem="CRA", valor="2000.00")
    logo_acima = _titulo(con, origem="CRA", valor="2000.01")
    assert [i["codigo_tj"] for i in POST.itens_do_ato_pela_tabela(
        con, no_teto, "PROTESTO", data=HOJE)] == ["17.1.5"]
    assert [i["codigo_tj"] for i in POST.itens_do_ato_pela_tabela(
        con, logo_acima, "PROTESTO", data=HOJE)] == ["17.1.6"]


def test_o_titulo_do_balcao_nao_ganha_item_da_tabela():
    """Manual, vencido há mais de um ano: antecipado — pago na hora. Quem diz
    o item é o caixa ou o protocolo, e a trava fica como está."""
    con = _banco()
    tid = _titulo(con, origem="MANUAL", vencimento="2022-09-05")
    assert POST.cobranca_do_ato(con, tid, "PROTESTO", hoje=HOJE)["diferir"] is False
    assert POST.itens_do_ato_pela_tabela(con, tid, "PROTESTO", data=HOJE) == []
    assert POST.itens_do_ato_pela_tabela(con, tid, "INTIMACAO", data=HOJE) == []


def test_acima_do_teto_ou_sem_faixa_nao_adivinha():
    con = _banco()
    acima = _titulo(con, origem="CRA", valor="9000.00")
    assert POST.itens_do_ato_pela_tabela(con, acima, "PROTESTO", data=HOJE) == []
    nativo(con).escrever("DELETE FROM cx_faixas")
    tid = _titulo(con, origem="CENPROT")
    assert POST.itens_do_ato_pela_tabela(con, tid, "PROTESTO", data=HOJE) == []


def test_os_outros_atos_nao_tiram_item_da_tabela():
    con = _banco()
    tid = _titulo(con, origem="CRA")
    for tipo in ("APONTAMENTO", "PAGAMENTO", "DESISTENCIA", "CANCELAMENTO"):
        assert POST.itens_do_ato_pela_tabela(con, tid, tipo, data=HOJE) == []


def test_a_recusa_do_titulo_diferido_nao_manda_abrir_caixa():
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar("PROTESTO", [], diferido=True)
    texto = str(erro.value)
    assert "a posteriori (diferido)" in texto
    assert "sem precisar de caixa aberto" in texto
    assert "com o seu caixa aberto" not in texto
    # o balcão continua com a frase de antes
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar("PROTESTO", [])
    assert "com o seu caixa aberto" in str(erro.value)


def test_a_cobertura_do_selo_so_aceita_o_devido_do_mesmo_item_e_ato_vivo():
    """`ato_selado` cobre o selo pelo devido do PRÓPRIO ato — só na tabela do
    Protesto, só no ato não cancelado, e só pelo item do código do envelope
    (a faixa conta: o 17.1.5 paga o 17.1; o 17.2 da intimação não)."""
    import ato_selado as AS
    con = _banco()
    bd = nativo(con)
    tid = _titulo(con, origem="CRA")
    ato = bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               criado_em) VALUES (%s,'PROTESTO',%s,'{}','MANUAL',%s)
           RETURNING id""", (tid, HOJE, AGORA))[0]["id"]
    POST.diferir(con, titulo_id=tid, ato_id=ato, tipo_ato="PROTESTO",
                 itens=POST.itens_do_ato_pela_tabela(con, tid, "PROTESTO",
                                                     data=HOJE),
                 data_do_ato=HOJE, agora=AGORA)
    assert AS._devido_do_proprio_ato(bd, "pt_atos", ato, "17.1")["servico"] == 9315
    assert AS._devido_do_proprio_ato(bd, "pt_atos", ato, "17.2") is None
    assert AS._devido_do_proprio_ato(bd, "pt_atos", ato, None)["servico"] == 9315
    assert AS._devido_do_proprio_ato(bd, "lv_atos", ato, "17.1") is None
    bd.escrever("UPDATE pt_atos SET cancelado=1 WHERE id=%s", (ato,))
    assert AS._devido_do_proprio_ato(bd, "pt_atos", ato, "17.1") is None


# ---------------------------------------------------------------- de tela


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture()
def s(cg_casa_logada):
    cg_casa_logada["db"].set_settings({"modulo_protesto_ligado": "1"})
    with cg_casa_logada["db"].transaction() as con:
        _tabela(nativo(con))
    return cg_casa_logada


def _ler(s, sql, parametros=None):
    with s["db"].connect() as con:
        return nativo(con).ler(sql, parametros)


def _intimado(s, *, origem: str, vencimento: str = "2025-12-20") -> int:
    """Um título intimado por edital, com a prova juntada — gravado direto."""
    with s["db"].transaction() as con:
        tid = _titulo(con, origem=origem, vencimento=vencimento)
        bd = nativo(con)
        bd.escrever("UPDATE pt_titulos SET situacao='INTIMADO', protocolo=%s "
                    "WHERE id=%s", (f"26083{tid:05d}", tid))
        for tipo, data, detalhe in (("APONTAMENTO", "2026-08-18", "{}"),
                                    ("INTIMACAO", "2026-08-20",
                                     '{"modo": "EDITAL"}')):
            bd.escrever(
                """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                       origem, criado_em) VALUES (%s,%s,%s,%s,'MANUAL',%s)""",
                (tid, tipo, data, detalhe, AGORA))
        juntar_prova(con, tid)
    return tid


def _lancar(s, titulo_id, **campos) -> str:
    html = s["c"].get(f"/protesto/{titulo_id}").get_data(as_text=True)
    return s["c"].post(f"/protesto/{titulo_id}/lancar",
                       data={"csrf_token": _token(html), **campos},
                       follow_redirects=True).get_data(as_text=True)


def _afirmacao(origem: str) -> dict:
    """A CENPROT sem número de pedido pede a afirmação de quem conferiu no
    portal — outra trava, que fica como está."""
    if origem != "CENPROT":
        return {}
    return {"afirmo": "1", "afirmacao": (
        "Afirmo, sob minha responsabilidade, que conferi o pedido no portal "
        "da CENPROT antes de lavrar este protesto de teste.")}


def _protestos(s, tid) -> list[dict]:
    return _ler(s, "SELECT id, cancelado, selo, motivo_cancelamento FROM pt_atos "
                   "WHERE titulo_id=%s AND tipo='PROTESTO' ORDER BY id", (tid,))


@pytest.mark.parametrize("origem", ["CRA", "CENPROT"])
def test_o_protesto_da_central_lavra_sem_caixa_e_sem_protocolo(s, origem):
    from selador_de_bancada import ligar_o_selador
    tid = _intimado(s, origem=origem)
    assert _ler(s, "SELECT id FROM cx_caixas WHERE situacao='ABERTO'") == []
    ficha = " ".join(s["c"].get(f"/protesto/{tid}").get_data(as_text=True).split())
    assert "data-diferido" in ficha
    # SEM PROTOCOLO DE BANCADA: a cobertura do selo tem de vir do devido.
    with ligar_o_selador(s, protocolo_pago=False) as aparelho:
        html = " ".join(_lancar(s, tid, ato="PROTESTO", motivo_atraso=MOTIVO,
                                **_afirmacao(origem)).split())
    assert "Ato NÃO lançado" not in html
    [ato] = _protestos(s, tid)
    assert ato["cancelado"] == 0 and str(ato["selo"] or "").strip()
    devido = _ler(s, "SELECT servico, tipo_ato, situacao FROM "
                     "pt_emolumentos_diferidos WHERE ato_id=%s", (ato["id"],))
    assert devido == [{"servico": 9315, "tipo_ato": "PROTESTO",
                       "situacao": "PENDENTE"}]
    assert _ler(s, "SELECT id FROM cx_lancamentos") == []
    assert "17.1.5" in html and "NÃO entrou no caixa" in html
    # o selo foi pedido pelo item do tribunal, e não pela faixa
    selos = [p for p in aparelho.pedidos if "/selo/protesto/" in p["caminho"]]
    assert selos and all("17.1.5" not in p["corpo"] for p in selos)
    assert any('"17.1"' in p["corpo"] for p in selos)
    [cob] = _ler(s, "SELECT forma, situacao FROM cx_selo_coberturas "
                    "WHERE tabela='pt_atos' AND ato_id=%s", (ato["id"],))
    assert cob["forma"] == "DIFERIDO"


def test_o_protesto_do_balcao_sem_item_continua_recusado(s):
    from selador_de_bancada import ligar_o_selador
    tid = _intimado(s, origem="MANUAL", vencimento="2022-09-05")
    with ligar_o_selador(s, protocolo_pago=False):
        html = " ".join(_lancar(s, tid, ato="PROTESTO",
                                motivo_atraso=MOTIVO).split())
    assert "Ato NÃO lançado, e nada foi gravado" in html
    assert "com o seu caixa aberto" in html
    assert _protestos(s, tid) == []
    assert _ler(s, "SELECT id FROM pt_emolumentos_diferidos") == []


def test_o_robo_nao_ganha_item_da_tabela_e_nao_sela(s, monkeypatch):
    import selo_robo as SR
    from selador_de_bancada import ligar_o_selador
    monkeypatch.setattr(SR, "pode_selar_automatico", lambda *a, **k: False)
    tid = _intimado(s, origem="CRA")
    with ligar_o_selador(s, protocolo_pago=False) as aparelho:
        _lancar(s, tid, ato="PROTESTO", motivo_atraso=MOTIVO)
    assert not [p for p in aparelho.pedidos if "/selo/protesto/" in p["caminho"]]
    assert _ler(s, "SELECT id FROM pt_emolumentos_diferidos") == []
    assert all(not str(a["selo"] or "").strip() for a in _protestos(s, tid))

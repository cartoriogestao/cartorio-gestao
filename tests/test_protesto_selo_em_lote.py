"""Selo do protesto já lavrado, pelo clique do escrevente, com o valor devido.

O lote «Gerar protesto» e o robô lavram sem selo. Este botão sela depois e
lança a faixa 17.1.N como devida: não entra dinheiro, não há recibo de zero,
e o robô leva 403. O escrevente vê a lista antes do clique. Nenhum id de ato
está cravado — os cenários nascem aqui.

O domínio não sela. Quem fala com o aparelho é só o POST
`/protesto/selar-pendentes`.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import juntar_prova  # noqa: E402

import ato_selado as AS                         # noqa: E402
import protesto as PT                           # noqa: E402
import protesto_selo_em_lote as PSL             # noqa: E402
import rotas_do_robo as RR                      # noqa: E402
import selador_config as SC                     # noqa: E402
from bd_nativo import banco as nativo           # noqa: E402
from caixa_schema import init_caixa_schema      # noqa: E402
from nucleo_schema import init_nucleo_schema    # noqa: E402
from pt_schema import init_pt_schema            # noqa: E402

AGORA = "2026-11-05T15:00:00"
HOJE = "2026-11-05"
SENHA = "Senha#12345"
MOTIVO = "Cenário de teste: tríduo vencido"
VIGENCIA = 9301
SERVICOS = ((9314, "17.1.4", "Protesto — faixa 4", "40,00"),
            (9315, "17.1.5", "Protesto — faixa 5", "55,00"),
            (9316, "17.1.6", "Protesto — faixa 6", "70,00"))
FAIXAS = (("500,01", "1.000,00", "17.1.4"),
          ("1.000,01", "2.000,00", "17.1.5"),
          ("2.000,01", "5.000,00", "17.1.6"))


def _tabela(bd) -> None:
    bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
                   VALUES (%s, 'tabela de teste do selo em lote', 1,
                           '2026-01-02', NULL)""", (VIGENCIA,))
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
            vencimento: str = "2025-12-20", chave: str | None = None) -> int:
    numero = f"TSELO/{origem}/{chave or valor}"
    return PT.cadastrar_titulo(
        con, _dados(numero, valor, vencimento), origem=origem,
        origem_chave=None if origem == "MANUAL" else (chave or f"TSELO:{origem}:{numero}"),
        agora=AGORA)


def _ato(con, tid, *, origem="MANUAL", selo=None, cancelado=0) -> int:
    bd = nativo(con)
    novo = bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               selo, cancelado, criado_em)
           VALUES (%s,'PROTESTO',%s,'{}',%s,%s,%s,%s) RETURNING id""",
        (tid, HOJE, origem, selo, cancelado, AGORA))
    bd.escrever("UPDATE pt_titulos SET situacao='PROTESTADO' WHERE id=%s",
                (int(tid),))
    return int(novo[0]["id"])


def _ids(quadro, chave) -> set[int]:
    return {int(p["ato_id"]) for p in quadro[chave]}


# ---------------------------------------------------------------- domínio


def test_pendentes_separa_o_que_da_para_selar_do_que_fica_de_fora():
    con = _banco()
    bd = nativo(con)
    casa = _ato(con, _titulo(con, origem="CRA", chave="casa"))
    balcao = _ato(con, _titulo(con, origem="MANUAL", vencimento="2022-09-05",
                               chave="balcao"))
    acervo = _ato(con, _titulo(con, origem="CRA", chave="acervo"),
                  origem="EOFICIO")
    cancelado = _ato(con, _titulo(con, origem="CRA", chave="cancelado"),
                     cancelado=1)
    com_selo = _ato(con, _titulo(con, origem="CRA", chave="com-selo"),
                    selo="SELOEXEMPLO0001")
    no_razao = _ato(con, _titulo(con, origem="CRA", chave="razao"))
    bd.escrever(
        """INSERT INTO sd_selos(numero, tabela, ato_id, obtido_em, ambiente)
           VALUES ('SELOEXEMPLO0002','pt_atos',%s,%s,'PRODUCAO')""",
        (no_razao, AGORA))
    coberto = _ato(con, _titulo(con, origem="CRA", chave="coberto"))
    bd.escrever(
        """INSERT INTO cx_selo_coberturas(referencia, tabela, ato_id, forma,
               criado_em, situacao)
           VALUES (%s,'pt_atos',%s,'DIFERIDO',%s,'RESERVADA')""",
        (f"pt_atos:{coberto}", coberto, AGORA))
    sem_faixa = _ato(con, _titulo(con, origem="CRA", valor="9000.00",
                                  chave="teto"))

    quadro = PSL.pendentes(con, hoje=HOJE)
    assert _ids(quadro, "selaveis") == {casa}
    fora = _ids(quadro, "de_fora")
    assert {balcao, acervo, no_razao, coberto, sem_faixa} <= fora
    assert cancelado not in fora and com_selo not in fora
    assert quadro["limite"] == 10
    motivos = {int(p["ato_id"]): p["motivo"] for p in quadro["de_fora"]}
    assert "acervo ou E-Ofício" in motivos[acervo]
    assert "antecipado (balcão)" in motivos[balcao]
    assert "razão" in motivos[no_razao]
    assert "cobertura" in motivos[coberto]
    assert "tabela não gerou" in motivos[sem_faixa]
    assert PSL.pendentes(con, titulo_id=_titulo_do(con, casa), hoje=HOJE)[
        "selaveis"][0]["ato_id"] == casa


def _titulo_do(con, ato_id: int) -> int:
    return int(nativo(con).valor(
        "SELECT titulo_id FROM pt_atos WHERE id=%s", (ato_id,)))


def test_preparar_recusa_o_robo_e_nao_escreve():
    con = _banco()
    casa = _ato(con, _titulo(con, origem="CRA", chave="robo"))
    with pytest.raises(PSL.SeloEmLoteError, match="Robô não sela"):
        PSL.preparar(con, eh_robo=True, usuario="Robo do Protesto",
                     agora=AGORA, hoje=HOJE)
    assert nativo(con).ler("SELECT id FROM pt_emolumentos_diferidos") == []
    assert nativo(con).valor("SELECT selo FROM pt_atos WHERE id=%s",
                             (casa,)) in (None, "")


def test_preparar_deixa_devido_sem_selo_e_sem_caixa_e_trava_a_linha():
    con = _banco()
    casa = _ato(con, _titulo(con, origem="CRA", chave="devido"))
    outro = _ato(con, _titulo(con, origem="CRA", chave="fica"))
    pronto = PSL.preparar(con, eh_robo=False, usuario="MARIO EXEMPLO",
                          agora=AGORA, hoje=HOJE, ato_id=casa)
    assert [p["ato_id"] for p in pronto["prontos"]] == [casa]
    assert pronto["prontos"][0]["codigo_tj"] == "17.1.5"
    devido = nativo(con).ler(
        "SELECT ato_id, servico, situacao FROM pt_emolumentos_diferidos")
    assert devido == [{"ato_id": casa, "servico": 9315, "situacao": "PENDENTE"}]
    assert nativo(con).ler("SELECT id FROM cx_lancamentos") == []
    assert nativo(con).valor("SELECT COALESCE(selo,'') FROM pt_atos WHERE id=%s",
                             (casa,)) == ""
    # sem selo, os dois continuam na fila; o devido não tira o ato da lista
    ainda = PSL.pendentes(con, hoje=HOJE)
    assert _ids(ainda, "selaveis") == {casa, outro}
    import inspect
    assert "FOR UPDATE" in inspect.getsource(PSL._travar)


def test_o_clique_prepara_no_maximo_dez():
    con = _banco()
    ids = [_ato(con, _titulo(con, origem="CRA", chave=f"n{i}"))
           for i in range(12)]
    pronto = PSL.preparar(con, eh_robo=False, usuario="MARIO EXEMPLO",
                          agora=AGORA, hoje=HOJE)
    assert len(pronto["prontos"]) == PSL.LIMITE_POR_CLIQUE == 10
    preparados = {p["ato_id"] for p in pronto["prontos"]}
    assert preparados == set(ids[:10])
    # Sem selo, o clique seguinte continua nos mesmos dez — não duplica o devido.
    de_novo = PSL.preparar(con, eh_robo=False, usuario="MARIO EXEMPLO",
                           agora=AGORA, hoje=HOJE)
    assert {p["ato_id"] for p in de_novo["prontos"]} == set(ids[:10])
    assert len(nativo(con).ler("SELECT id FROM pt_emolumentos_diferidos")) == 10
    for ato in ids[:10]:
        nativo(con).escrever("UPDATE pt_atos SET selo=%s WHERE id=%s",
                             (f"SELO{ato}", ato))
    resto = PSL.preparar(con, eh_robo=False, usuario="MARIO EXEMPLO",
                         agora=AGORA, hoje=HOJE)
    assert {p["ato_id"] for p in resto["prontos"]} == set(ids[10:])
    assert nativo(con).ler("SELECT id FROM cx_lancamentos") == []


def test_a_rota_nao_esta_na_lista_do_robo():
    assert "protesto_selar_pendentes" not in RR.ROTAS_PERMITIDAS_AO_ROBO


# ---------------------------------------------------------------- tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                              SENHA, "ADMIN")
    cg_casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    c = cg_casa["app"].test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    cg_casa["c"] = c
    with cg_casa["db"].transaction() as con:
        _tabela(nativo(con))
    return cg_casa


def _con(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _intimado(s, numero="84713/1") -> int:
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
                   valor_centavos, saldo_centavos, situacao, protocolo,
                   origem, criado_em, motivo_protesto)
               VALUES ('DMI',?,'00200000991',148278,148278,'INTIMADO',
                       '2608310001','CRA',?,'1')""", (numero, AGORA))
        tid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
                   documento_numero) VALUES (?,?,'CPF','00000000000')""",
            (tid, "DEVEDOR FICTICIO"))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, criado_em) VALUES (?,'APONTAMENTO',?,'{}','MANUAL',?)""",
            (tid, "2026-08-18", AGORA))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, criado_em)
               VALUES (?,'INTIMACAO',?,'{"modo": "EDITAL"}','MANUAL',?)""",
            (tid, "2026-08-20", AGORA))
        juntar_prova(con, tid)
    con.close()
    return tid


def _lavrar(s, tid) -> str:
    tela = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    return s["c"].post(
        "/protesto/a-protestar/lavrar",
        data={"csrf_token": _token(tela), "titulo_id": str(tid),
              f"motivo_atraso_{tid}": MOTIVO},
        follow_redirects=True).get_data(as_text=True)


def _ler(s, sql, params=()):
    with s["db"].connect() as con:
        return nativo(con).ler(sql, params)


def test_o_lote_continua_sem_selar_e_aponta_o_botao(s):
    tid = _intimado(s)
    html = _lavrar(s, tid)
    assert "ainda não têm selo nem cobrança" in html
    assert "Selar e lançar no caixa (devido) todos os protestos pendentes" in html
    [ato] = _ler(s, "SELECT selo, lancamento_id FROM pt_atos "
                    "WHERE titulo_id=%s AND tipo='PROTESTO'", (tid,))
    assert not str(ato["selo"] or "").strip()
    assert ato["lancamento_id"] is None
    assert _ler(s, "SELECT id FROM cx_lancamentos") == []
    assert _ler(s, "SELECT id FROM pt_emolumentos_diferidos") == []


def test_a_lista_e_a_ficha_mostram_o_pendente_e_o_clique_sela_sem_dinheiro(s):
    from selador_de_bancada import ligar_o_selador
    tid = _intimado(s, numero="lote-1")
    _lavrar(s, tid)
    lista = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "Protestos lavrados sem selo" in lista
    assert 'data-protestos-sem-selo' in lista
    assert "Selar e lançar no caixa (devido) todos os protestos pendentes" in lista
    assert "até <strong>10</strong>" in lista or ">10<" in lista
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Selar e lançar no caixa (devido) este protesto" in ficha
    with ligar_o_selador(s, protocolo_pago=False) as aparelho:
        s["c"].get("/protesto/a-protestar")
        assert not [p for p in aparelho.pedidos if "/selo/" in p["caminho"]]
        tela = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
        resposta = s["c"].post(
            "/protesto/selar-pendentes",
            data={"csrf_token": _token(tela)},
            follow_redirects=True).get_data(as_text=True)
    assert "não entrou no caixa" in resposta
    [ato] = _ler(s, "SELECT id, selo FROM pt_atos WHERE titulo_id=%s "
                    "AND tipo='PROTESTO'", (tid,))
    assert str(ato["selo"] or "").strip()
    assert _ler(s, "SELECT servico, situacao FROM pt_emolumentos_diferidos "
                    "WHERE ato_id=%s", (ato["id"],)) == [
        {"servico": 9315, "situacao": "PENDENTE"}]
    assert _ler(s, "SELECT id FROM cx_lancamentos") == []
    [cob] = _ler(s, "SELECT forma, situacao FROM cx_selo_coberturas "
                    "WHERE tabela='pt_atos' AND ato_id=%s", (ato["id"],))
    assert cob["forma"] == "DIFERIDO"
    [aud] = _ler(s, "SELECT details FROM audit_logs "
                    "WHERE action=%s AND entity_id=%s",
                 (PSL.ACAO_DA_AUDITORIA, ato["id"]))
    detalhe = json.loads(aud["details"])
    assert detalhe["entrou_no_caixa"] is False
    assert detalhe["titulo_id"] == tid
    depois = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert f'data-protesto-sem-selo="{ato["id"]}"' not in depois


def test_o_robo_leva_403_e_nao_ve_o_botao(s):
    from conftest import cg_login
    tid = _intimado(s, numero="do-robo")
    _lavrar(s, tid)
    s["db"].create_user("robo_protesto", "Robo do Protesto", SENHA, "USER",
                        eh_robo=1)
    s["db"].set_settings({"modulo_protesto_alcance": "TODOS"})
    robo = s["app"].test_client()
    cg_login(robo, "robo_protesto", SENHA)
    ficha = robo.get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Protestos lavrados sem selo" in ficha
    assert "Selar e lançar no caixa (devido)" not in ficha
    r = robo.post("/protesto/selar-pendentes",
                  data={"csrf_token": _token(ficha), "titulo_id": str(tid)})
    assert r.status_code == 403
    assert _ler(s, "SELECT id FROM pt_emolumentos_diferidos") == []
    assert all(not str(a["selo"] or "").strip()
               for a in _ler(s, "SELECT selo FROM pt_atos WHERE titulo_id=%s "
                               "AND tipo='PROTESTO'", (tid,)))

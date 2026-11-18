"""As custas dos títulos à CRA — a operação `CustasTitulo` (18/11/2026).

O contrato é o do manual da P21 («Emolumentos dos títulos») e o do exemplo
oficial `EXEMPLO_CUSTAS_TITULO.zip`. A rede é simulada; o que se prova é a
regra da casa: o XML na forma do exemplo, os valores da tabela (os mesmos do
retorno e da CENPROT), só o que mudou, a rede fora da transação, e o nome que
a queda de rede não gasta.
"""
from __future__ import annotations

import sqlite3
import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import centrais_cred as CRED  # noqa: E402
import cra21_api as API  # noqa: E402
import protesto_cenprot as CENP  # noqa: E402
import protesto_cra_custas as CC  # noqa: E402
import protesto_retorno as PRE  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-11-18T09:00:00"
HOJE = date(2026, 11, 18)
OK = ('<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>'
      "<mensagem><codigo>2291</codigo>"
      "<descricao>Custas do título atualizadas com sucesso.</descricao></mensagem>")


def banco():
    from fixtures.emolumentos_cenprot import carregar
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    carregar(con)
    con.commit()
    return con


def titulo(con, *, situacao="APONTADO", valor=10160, protocolo="2611170001",
           apresentante="237", documento="000.000.001-91", origem="CRA",
           numero="DM-1", nosso="555") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, protocolo,
               apresentante_codigo, origem, criado_em)
           VALUES ('DMI',?,?,?,?,?,?,?,?,?)""",
        (numero, nosso, valor, valor, situacao, protocolo, apresentante,
         origem, AGORA))
    tid = int(cur.lastrowid)
    if documento is not None:
        con.execute(
            "INSERT INTO pt_devedores(titulo_id, nome, documento_numero) VALUES (?,?,?)",
            (tid, "DEVEDOR EXEMPLO", documento))
    con.commit()
    return tid


def transacao_de(con):
    @contextmanager
    def transacao():
        yield con
        con.commit()
    return transacao


@pytest.fixture()
def credencial(monkeypatch):
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)


# ------------------------------------------------------------------ formas


def test_o_nome_e_o_do_manual():
    assert CC.nome_do_arquivo(date(2022, 4, 4), 1) == "E0000404.221"
    assert CC.nome_do_arquivo(HOJE, 9) == "E0001811.269"
    assert API.NOME_DAS_CUSTAS.match(CC.nome_do_arquivo(HOJE, 3))
    with pytest.raises(CC.CustasCraError, match="no máximo 9"):
        CC.nome_do_arquivo(HOJE, 10)


def test_a_data_do_protocolo_e_a_do_apontamento_e_depois_a_do_protocolo():
    assert CC.data_do_protocolo("2026-11-17T10:00:00", "2611180001") == "17/11/2026"
    assert CC.data_do_protocolo(None, "2611180001") == "18/11/2026"
    # Protocolo de outra forma não vira data inventada.
    assert CC.data_do_protocolo(None, "0000123456") == ""
    assert CC.data_do_protocolo("", "") == ""


def test_os_precos_sao_os_mesmos_do_retorno_e_da_cenprot():
    """Dois números para a mesma retirada fariam a CRA mostrar um e o retorno
    dizer outro: a conta lida uma vez tem de bater com a de cada título."""
    con = banco()
    tabela = CC.tabela_do_dia(con, "2026-11-18")
    assert tabela["vigencia"] == CENP.VIGENCIA_MEDIDA
    folha = CENP._preco_do_item(con, CENP.ITEM_POR_FOLHA, CENP.VIGENCIA_MEDIDA)
    a_menos = (CENP.FOLHAS_ARQUIVADAS - PRE.FOLHAS_DA_RETIRADA_NO_RETORNO) * folha
    for valor in (10160, 22000, 22008, 99999, 500000):
        um = CENP.precos_do_titulo(con, valor, vigencia=CENP.VIGENCIA_MEDIDA)
        p = CC.precos(tabela, valor)
        assert p["cancelamento"] == um["cancelamento"]
        assert p["retirada"] == um["retirada"] - a_menos
    # R$ 101,60: a retirada do retorno (4 folhas) e o cancelamento da CENPROT.
    assert CC.precos(tabela, 10160) == {"retirada": 9654 - a_menos,
                                         "cancelamento": 24826}


# ------------------------------------------------------------------ o que vai


def test_apontado_leva_retirada_e_protestado_leva_cancelamento():
    con = banco()
    a = titulo(con, situacao="APONTADO", protocolo="2611170001")
    p = titulo(con, situacao="PROTESTADO", protocolo="2610010002", numero="DM-2")
    titulo(con, situacao="PROTESTADO", origem="MANUAL", protocolo="2610010003")
    titulo(con, situacao="PAGO", protocolo="2610010004")
    r = CC.pendentes(con, hoje="2026-11-18")
    por_id = {i["titulo_id"]: i for i in r["itens"]}
    assert set(por_id) == {a, p}, "só os da CRA, apontados ou protestados"
    assert [e["tipo"] for e in por_id[a]["emolumentos"]] == ["1"]
    assert [e["tipo"] for e in por_id[p]["emolumentos"]] == ["2"]
    assert por_id[p]["emolumentos"][0]["total_centavos"] == 24826
    assert por_id[a]["data_protocolo"] == "17/11/2026"
    assert por_id[a]["documento"] == "00000000191"
    # A vigência da fixture não tem fim: vai vazia, «indefinida» no manual.
    assert por_id[a]["emolumentos"][0]["vigencia"] == ""


def test_titulo_sem_dado_fica_de_fora_dizendo_por_que():
    con = banco()
    titulo(con, documento=None)
    titulo(con, protocolo="0000999999", numero="DM-2")
    titulo(con, apresentante="", protocolo="2611170003", numero="DM-3")
    r = CC.pendentes(con, hoje="2026-11-18")
    assert not r["itens"]
    motivos = sorted(f["motivo"] for f in r["fora"])
    assert any("CPF/CNPJ" in m for m in motivos)
    assert any("data do protocolo" in m for m in motivos)
    assert any("apresentante" in m for m in motivos)


def test_o_xml_tem_a_forma_do_exemplo_oficial():
    con = banco()
    titulo(con, apresentante="237", protocolo="2611170001")
    titulo(con, apresentante="237", protocolo="2611170002", numero="DM-2")
    titulo(con, apresentante="001", protocolo="2611170003", numero="DM-3",
           situacao="PROTESTADO")
    xml = CC.montar_xml(CC.pendentes(con, hoje="2026-11-18")["itens"])
    assert xml.startswith('<?xml version="1.0" encoding="ISO-8859-1"?>')
    assert xml.isascii()
    raiz = ET.fromstring(xml.encode("iso-8859-1"))
    assert raiz.tag == "custas_titulo"
    apresentantes = raiz.findall("./apresentantes/apresentante")
    assert [a.findtext("codigo") for a in apresentantes] == ["001", "237"]
    t = apresentantes[1].find("./titulos/titulo")
    assert [c.tag for c in t] == ["protocolo", "documento_devedor", "data_protocolo",
                                  "numero_titulo", "nosso_numero", "valor",
                                  "emolumentos"]
    assert t.findtext("valor") == "101.60"
    e = t.find("./emolumentos/emolumento")
    assert [c.tag for c in e] == ["tipo", "vigencia", "total"]
    assert e.findtext("tipo") == "1"
    assert e.findtext("total") == f"{CC.precos(CC.tabela_do_dia(con, '2026-11-18'), 10160)['retirada'] / 100:.2f}"


# ------------------------------------------------------------------ a resposta


def test_2291_e_aceito_e_2196_e_2292_sao_recusa():
    lido = CC.interpretar_resposta(OK)
    assert lido["ok"] and lido["protocolos_aceitos"] is None
    with pytest.raises(API.CraRecusou) as e:
        CC.interpretar_resposta(
            "<mensagem><codigo>2196</codigo><descricao>Título não encontrado."
            "</descricao></mensagem>")
    assert e.value.codigo == "2196"
    with pytest.raises(API.CraRecusou) as e:
        CC.interpretar_resposta(
            "<mensagem><codigo>2292</codigo><descricao>Campos inválidos ou não "
            "informados (TIPO)</descricao></mensagem>")
    assert e.value.codigo == "2292" and "TIPO" in e.value.motivo
    with pytest.raises(API.CraRecusou):
        CC.interpretar_resposta("")
    with pytest.raises(API.CraRecusou):
        CC.interpretar_resposta("<qualquer/>")


def test_resposta_por_titulo_aceita_so_os_2291():
    texto = ("<mensagens>"
             "<mensagem><protocolo>2611170001</protocolo><codigo>2291</codigo></mensagem>"
             "<mensagem><protocolo>2611170002</protocolo><codigo>2196</codigo>"
             "<descricao>Título não encontrado.</descricao></mensagem></mensagens>")
    lido = CC.interpretar_resposta(texto)
    assert not lido["ok"]
    assert lido["protocolos_aceitos"] == {"2611170001"}
    assert "2611170002" in lido["recusas"][0]


# ------------------------------------------------------------------ o envio


def test_envia_grava_e_a_segunda_rodada_nao_repete(monkeypatch, credencial):
    con = banco()
    a = titulo(con)
    enviados = []

    def falso(nome, conteudo, ambiente, *, pasta=None):
        assert not con.in_transaction, "a rede não roda dentro de transação"
        enviados.append((nome, conteudo, ambiente))
        return OK

    monkeypatch.setattr(API, "enviar_custas_titulo", falso)
    r = CC.enviar(transacao_de(con), hoje=HOJE, usuario="OFICIAL")
    assert r["enviado"] and r["informados"] == 1
    assert enviados[0][0] == "E0001811.261" and enviados[0][2] == CRED.PRODUCAO
    linha = con.execute("SELECT * FROM pt_cra_custas_envios").fetchone()
    assert linha["enviado_em"] and linha["codigo"] == "2291"
    assert linha["gerado_por"] == "OFICIAL"
    inf = con.execute("SELECT * FROM pt_cra_custas_informadas WHERE titulo_id=?",
                      (a,)).fetchone()
    assert inf["tipo"] == "1" and inf["total_centavos"] > 0

    r2 = CC.enviar(transacao_de(con), hoje=HOJE)
    assert not r2["enviado"] and len(enviados) == 1, "nada mudou, nada vai"

    # PROTESTADO: vai o cancelamento, e a retirada sai VAZIA (exemplo oficial).
    con.execute("UPDATE pt_titulos SET situacao='PROTESTADO' WHERE id=?", (a,))
    con.commit()
    r3 = CC.enviar(transacao_de(con), hoje=HOJE)
    assert r3["enviado"] and enviados[1][0] == "E0001811.262"
    em = ET.fromstring(enviados[1][1].encode("iso-8859-1")).findall(".//emolumento")
    assert [(e.findtext("tipo"), e.findtext("total"), e.findtext("vigencia"))
            for e in em] == [("1", "", ""), ("2", "248.26", "")]
    tipos = {r["tipo"]: r["total_centavos"] for r in con.execute(
        "SELECT tipo, total_centavos FROM pt_cra_custas_informadas WHERE titulo_id=?",
        (a,)).fetchall()}
    assert tipos == {"1": None, "2": 24826}
    assert not CC.enviar(transacao_de(con), hoje=HOJE)["enviado"]


def test_a_queda_de_rede_grava_o_erro_e_nao_gasta_o_nome(monkeypatch, credencial):
    con = banco()
    titulo(con)

    def caiu(*a, **k):
        raise API.CraError("Não consegui falar com a CRA.")

    monkeypatch.setattr(API, "enviar_custas_titulo", caiu)
    with pytest.raises(API.CraError):
        CC.enviar(transacao_de(con), hoje=HOJE)
    linha = con.execute("SELECT * FROM pt_cra_custas_envios").fetchone()
    assert linha["erro"] and not linha["enviado_em"]
    assert not con.execute("SELECT 1 FROM pt_cra_custas_informadas").fetchone()

    nomes = []
    monkeypatch.setattr(API, "enviar_custas_titulo",
                        lambda nome, *a, **k: nomes.append(nome) or OK)
    CC.enviar(transacao_de(con), hoje=HOJE)
    assert nomes == ["E0001811.261"], "o nome que não chegou à CRA se reaproveita"
    assert con.execute("SELECT COUNT(*) FROM pt_cra_custas_envios").fetchone()[0] == 1


def test_a_recusa_da_cra_nao_marca_nada_como_informado(monkeypatch, credencial):
    con = banco()
    titulo(con)
    monkeypatch.setattr(
        API, "enviar_custas_titulo",
        lambda *a, **k: "<mensagem><codigo>2292</codigo><descricao>Campos inválidos"
                        "</descricao></mensagem>")
    with pytest.raises(API.CraRecusou):
        CC.enviar(transacao_de(con), hoje=HOJE)
    linha = con.execute("SELECT * FROM pt_cra_custas_envios").fetchone()
    assert linha["codigo"] == "2292" and not linha["enviado_em"]
    assert not con.execute("SELECT 1 FROM pt_cra_custas_informadas").fetchone()
    # A CRA respondeu: o próximo arquivo leva a sequência seguinte.
    nomes = []
    monkeypatch.setattr(API, "enviar_custas_titulo",
                        lambda nome, *a, **k: nomes.append(nome) or OK)
    CC.enviar(transacao_de(con), hoje=HOJE)
    assert nomes == ["E0001811.262"]


def test_sem_credencial_nao_comeca(monkeypatch):
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: False)
    con = banco()
    titulo(con)
    with pytest.raises(CC.CustasCraError, match="credencial"):
        CC.enviar(transacao_de(con), hoje=HOJE)


# ------------------------------------------------------------------ o transporte


def test_o_transporte_confere_o_nome_e_manda_userarq_e_userdados(monkeypatch):
    with pytest.raises(API.CraError, match="E000DDMM"):
        API.enviar_custas_titulo("C2371811.261", "<x/>")
    with pytest.raises(API.CraError, match="vazio"):
        API.enviar_custas_titulo("E0001811.261", "  ")
    visto = {}

    def chamar(operacao, ambiente, **k):
        visto.update(k, operacao=operacao)
        return OK

    monkeypatch.setattr(API, "chamar", chamar)
    API.enviar_custas_titulo("E0001811.261", "<custas_titulo/>")
    assert visto["operacao"] == "CustasTitulo"
    assert visto["userArq"] == "E0001811.261"
    assert visto["userDados"] == "<custas_titulo/>"
    assert "CustasTitulo" not in API.OPERACOES_SEM_SENTIDO_MEDIDO
    assert "CustasTitulo" not in API.OPERACOES_QUE_ESCREVEM, (
        "reenviar só atualiza: a falha de rede pode se repetir")


# ------------------------------------------------------------------ a rotina


class _Db:
    def __init__(self, con):
        self.con = con
        self.logs = []

    @contextmanager
    def connect(self):
        yield self.con

    def transaction(self):
        return transacao_de(self.con)()

    def log(self, *a, **k):
        self.logs.append((a, k))


class _Ctx:
    def __init__(self, con, pode_agir):
        self.db = _Db(con)
        self.agora = datetime(2026, 11, 18, 12, 0)
        self.pasta_dados = None
        self.processo = {"pode_agir": pode_agir}


def test_a_rotina_sem_pode_agir_so_conta(monkeypatch, credencial):
    con = banco()
    titulo(con)
    monkeypatch.setattr(API, "enviar_custas_titulo",
                        lambda *a, **k: pytest.fail("não podia enviar"))
    r = CC.rodar(_Ctx(con, pode_agir=False))
    assert r["situacao"] == "AVISO" and "1 título" in r["relato"]


def test_a_rotina_com_pode_agir_envia_e_audita(monkeypatch, credencial):
    import identidade_do_robo  # noqa: F401 — a auditoria do robô o usa
    con = banco()
    titulo(con)
    monkeypatch.setattr(API, "enviar_custas_titulo", lambda *a, **k: OK)
    ctx = _Ctx(con, pode_agir=True)
    r = CC.rodar(ctx)
    assert r["situacao"] == "OK", r
    assert r["acoes"][0]["arquivo"] == "E0001811.261"
    assert ctx.db.logs and ctx.db.logs[0][0][2] == "PROTESTO_CRA_CUSTAS_ENVIADAS"
    assert CC.rodar(ctx)["situacao"] == "OK"


def test_a_rotina_esta_no_catalogo_da_automacao():
    import automacao_processos as AP
    codigos = {s["codigo"]: s for s in AP.todas_as_sementes()}
    assert CC.CODIGO_DA_ROTINA in codigos
    assert codigos[CC.CODIGO_DA_ROTINA]["alvo"] == "protesto_cra_custas:rodar"


# ------------------------------------------------------------------ a tela


def test_a_tela_mostra_o_quadro_e_o_botao_envia(cg_casa, monkeypatch):
    from test_cra21_web import _sessao, _token
    s = _sessao(cg_casa)
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    assert "Custas dos títulos" in html and "CustasTitulo" in html
    assert "Enviar as custas à CRA" in html
    # Sem título nem tabela, o envio volta frase, e não HTTP 500.
    monkeypatch.setattr(API, "enviar_custas_titulo",
                        lambda *a, **k: pytest.fail("não havia o que enviar"))
    r = s["c"].post("/protesto/cra/api/custas/enviar",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200

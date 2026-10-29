"""A conferência CENPROT × sistema — o domínio (29/10/2026).

POR QUE ELA EXISTE
    O pedido 3597193 (título 350574/1) ficou PAGO no portal da CENPROT por uma
    «Liquidação» feita lá, e aqui o título foi protestado no dia seguinte; o
    irmão 350574/2, pago no balcão em 11/08, continuou «apontado» na Central.
    Os dois têm o mesmo protocolo. Nada avisou ninguém. Ordem do oficial: o
    sistema tem de impedir que a mão de obra erre, e quem insistir afirma por
    escrito, com log. Os números daqui são fictícios.

O QUE ESTES TESTES GUARDAM
      - a rede NÃO acontece dentro da transação — o `db` de mentira grita;
      - o número do pedido sai da origem do título OU da identificação do
        E-Ofício (15 dígitos com zeros), e título de banco não é CENPROT;
      - «Aguardando Pagamento» NÃO é pago, e status que não se lê não vira
        «em andamento»;
      - o que se guarda é só o que a conferência usa: nem o devedor nem o PDF;
      - a falha de rede não apaga o que a Central disse antes, e a consulta
        para na primeira falha — sem martelar a Central;
      - o caso do 350574 aparece INTEIRO, nos dois títulos;
      - a liquidação registrada no pedido errado aparece nos dois títulos;
      - a trava recusa o «pago» da Central e o «não deu para conferir», e só
        passa com a afirmação expressa — que no lote não se faz, e robô não faz;
      - nenhuma função daqui corrige, lavra, cancela ou manda nada à Central.
"""
from __future__ import annotations

import ast
import inspect
import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import cenprot_api as API  # noqa: E402
import cenprot_conferencia as C  # noqa: E402
import cenprot_pendencias as PEND  # noqa: E402
import centrais_cred as CRED  # noqa: E402
import cn_schema as CN  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-10-29T10:00:00"
CPF = "00000000191"                 # fictício (tests/fixtures/anti_vazamento)
OUTRO_CPF = "00000000272"           # fictício
PROTOCOLO = "2610210001"

CONTRATO = (RAIZ.parent.parent / "FONTES_EXTERNAS" / "cra21"
            / "cenprot_swagger_v2.1.0.yaml")
tem_contrato = pytest.mark.skipif(
    not CONTRATO.is_file(),
    reason="o swagger.yaml só existe na máquina de desenvolvimento")


# ------------------------------------------------------------ o banco de mesa


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_pt_schema(con)
    CN.init_cn_schema(con)
    con.commit()
    return con


class BancoDeMesa:
    """O `db` que `consultar` e `trava_do_protesto` recebem — e o guarda: ele
    GRITA se a Central for chamada com uma transação aberta."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.dentro = False

    @contextmanager
    def transaction(self):
        assert not self.dentro, "transação dentro de transação"
        self.dentro = True
        try:
            self.con.execute("BEGIN IMMEDIATE")
            yield self.con
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise
        finally:
            self.dentro = False

    def now(self) -> str:
        return AGORA


def titulo(con, *, numero="123/1", situacao="INTIMADO", origem="CENPROT",
           origem_chave=None, cra=None, apresentante="TAB",
           protocolo=PROTOCOLO, valor=10000, cedente="EMPRESA FICTICIA LTDA",
           documento=CPF) -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos
               (especie, numero_titulo, situacao, origem, origem_chave,
                cra_identificacao, apresentante_codigo, protocolo,
                valor_centavos, saldo_centavos, cedente_nome, criado_em)
           VALUES ('DMI',?,?,?,?,?,?,?,?,?,?,?)""",
        (numero, situacao, origem, origem_chave or f"t-{numero}", cra,
         apresentante, protocolo, valor, valor, cedente, AGORA))
    tid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero) VALUES (?,?,'CPF',?)""",
        (tid, "DEVEDOR FICTICIO", documento))
    con.commit()
    return tid


def ato(con, titulo_id, tipo, *, origem="MANUAL", data="2026-08-11",
        detalhe="{}") -> int:
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em) VALUES (?,?,?,?,?,?)""",
        (titulo_id, tipo, data, detalhe, origem, AGORA))
    con.commit()
    return int(cur.lastrowid)


def pedido(numero="9900001", *, status="Apontado / em andamento",
           ocorrencia="", codigo="", numero_titulo="123/1", valor=100.0,
           devedor="000.000.001-91", cedente="EMPRESA FICTICIA LTDA",
           protocolo=PROTOCOLO) -> dict:
    """Um pedido na forma do `GET /pedidos/consulta` (valores fictícios)."""
    return {
        "dados_pedido": {
            "cd_pedido_protesto": int(numero), "nr_cartorio": "01",
            "dt_pedido": "2026-10-20", "ds_status": status,
            "ocorrencia": ocorrencia, "ds_ocorrencia": codigo,
            "nm_nr_protocolo": protocolo, "dt_ocorrencia": "2026-10-27",
            "dados_titulo": {"nm_nr_titulo": numero_titulo,
                             "vl_titulo": valor}},
        "devedor": {"nm_devedor": "DEVEDOR FICTICIO",
                    "nm_nr_identificacao": devedor,
                    "nm_endereco": "RUA DO TESTE, 1"},
        "dados_cedente": {"nm_cedente": cedente},
        "arquivos": {"pedido_pdf_b64": "JVBERi0xLjQKJQ==", "anexo_b64": None},
    }


def central(monkeypatch, respostas: dict, *, db=None) -> list:
    """Troca a Central por uma que responde `respostas[numero]` — um pedido,
    uma exceção ou nada. Confere que NÃO é chamada dentro de transação."""
    chamadas: list = []

    def falsa(ambiente=CRED.PRODUCAO, *, numero="", data="", pasta=None):
        if db is not None:
            assert not db.dentro, (
                "a Central foi chamada DENTRO da transação — o BEGIN "
                "IMMEDIATE segurado pela rede põe todo outro balcão no "
                "busy_timeout")
        chamadas.append(numero)
        r = respostas.get(numero)
        if isinstance(r, Exception):
            raise r
        return [] if r is None else [r]

    monkeypatch.setattr(API, "pedidos_de_protesto", falsa)
    return chamadas


def linha_de(con, titulo_id) -> dict:
    return C.da_ficha(con, titulo_id)


def regras(con, titulo_id) -> set[str]:
    return {a["regra"] for a in linha_de(con, titulo_id)["achados"]}


# --------------------------------------------- de onde vem o pedido


def test_o_prefixo_e_o_apresentante_sao_os_das_pendencias():
    """Duas constantes com o mesmo nome em dois módulos divergem no primeiro
    conserto — e aqui o prefixo é o que acha o pedido do título."""
    assert C.PREFIXO_DA_ORIGEM_DO_PEDIDO == PEND.PREFIXO_DA_ORIGEM_DO_PEDIDO
    assert C.APRESENTANTE_DOS_PEDIDOS == PEND.APRESENTANTE_DOS_PEDIDOS


def test_o_pedido_sai_da_origem_e_da_identificacao_do_eoficio():
    assert C.pedidos_do_titulo(
        {"origem_chave": "CENPROT-PEDIDO:9900001"}) == [
            ("9900001", C.FONTE_ORIGEM)]
    # O E-Ofício guardava o pedido em `tbSDT.Campo03`, com zeros à esquerda.
    assert C.pedidos_do_titulo(
        {"origem_chave": "tbAvisoProtesto:1.0",
         "cra_identificacao": "000000009900002"}) == [("9900002", C.FONTE_CRA)]
    # Dois números diferentes no mesmo título é achado — não se escolhe calado.
    dois = C.pedidos_do_titulo({"origem_chave": "CENPROT-PEDIDO:9900001",
                                "cra_identificacao": "000000009900002"})
    assert [n for n, _ in dois] == ["9900001", "9900002"]
    assert C.pedidos_do_titulo({"cra_identificacao": "NF-123"}) == []


def test_titulo_de_banco_nao_e_de_origem_cenprot():
    assert not C.e_de_origem_cenprot({"apresentante_codigo": "001",
                                      "origem": "CRA", "origem_chave": "CRA:1:1"})
    assert C.e_de_origem_cenprot({"apresentante_codigo": "TAB", "origem": "CRA"})
    assert C.e_de_origem_cenprot({"origem": "CENPROT"})
    assert C.e_de_origem_cenprot({"origem": "MANUAL",
                                  "origem_chave": "CENPROT-PEDIDO:1"})


# --------------------------------------------- o que a Central diz


def test_o_codigo_da_ocorrencia_e_o_da_cra():
    import protesto_cra as CRA
    assert set(C.ESTADO_DO_CODIGO) <= set(CRA.OCORRENCIAS)
    assert C.estado_da_central("", "", "1") == C.PAGO
    assert C.estado_da_central("", "", "A") == C.CANCELADO


def test_o_exemplo_do_contrato_se_le_como_protestado():
    assert C.estado_da_central("Apontado / em andamento", "Protestado",
                               "2") == C.PROTESTADO
    assert C.estado_da_central("Apontado / em andamento", "", "") == (
        C.EM_ANDAMENTO)


def test_aguardando_pagamento_nao_e_pago():
    """É o status da RENEGOCIAÇÃO na mesma API. Ler «pagamento» como «pago»
    travaria o título que ninguém pagou."""
    assert C.estado_da_central("Aguardando Pagamento", "", "") == C.EM_ANDAMENTO
    assert C.estado_da_central("Pago", "", "") == C.PAGO
    assert C.estado_da_central("Liquidado", "", "") == C.LIQUIDADO


def test_quando_brigam_ganha_o_que_tira_o_titulo_do_protesto():
    assert C.estado_da_central("Apontado / em andamento", "Pago", "") == C.PAGO
    assert C.estado_da_central("Protestado", "", "A") == C.CANCELADO


def test_status_que_nao_se_le_nao_vira_em_andamento():
    assert C.estado_da_central("Situação 99", "", "") == C.DESCONHECIDO
    assert C.estado_da_central("", "", "") == C.DESCONHECIDO


@tem_contrato
def test_os_campos_lidos_estao_na_resposta_do_contrato():
    texto = CONTRATO.read_text(encoding="utf-8")
    bloco = texto.split("/pedidos/consulta:", 1)[1].split("/pedidos/protocolar:", 1)[0]
    for campo in ("dados_pedido", "cd_pedido_protesto", "ds_status",
                  "ocorrencia", "ds_ocorrencia", "dt_ocorrencia",
                  "nm_nr_protocolo", "dados_titulo", "nm_nr_titulo",
                  "vl_titulo", "devedor", "nm_nr_identificacao",
                  "dados_cedente", "nm_cedente", "nm_nr_documento"):
        assert re.search(rf"\b{campo}:", bloco), campo


@tem_contrato
def test_a_api_nao_tem_caminho_de_liquidacao():
    """MEDIDO em 29/10/2026: nada no contrato fala de liquidação, TED, boleto
    ou repasse — por isso a liquidação se registra à mão. Se a CENPROT
    publicar o caminho, este teste fica vermelho para alguém o ligar."""
    texto = CONTRATO.read_text(encoding="utf-8").lower()
    for palavra in ("liquid", "boleto", "repasse", "comprovante"):
        assert palavra not in texto, palavra


# --------------------------------------------- consultar e guardar


def test_a_rede_nao_acontece_dentro_da_transacao(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    chamadas = central(monkeypatch, {"9900001": pedido()}, db=db)
    r = C.consultar(db, quem="teste")
    assert chamadas == ["9900001"]
    assert r["achados"] == 1


def test_guarda_so_o_que_a_conferencia_usa(monkeypatch):
    """O devedor só se COMPARA, e o PDF não se guarda."""
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido()}, db=db)
    C.consultar(db)
    linha = dict(con.execute(
        "SELECT * FROM cn_conferencias WHERE titulo_id = ?", (tid,)).fetchone())
    guardado = json.dumps(linha, ensure_ascii=False, default=str)
    assert "000.000.001-91" not in guardado and CPF not in guardado
    assert "JVBERi0x" not in guardado and "RUA DO TESTE" not in guardado
    assert linha["central_devedor_confere"] == 1
    assert linha["central_estado"] == C.EM_ANDAMENTO
    assert linha["resultado"] == C.ACHOU


def test_a_falha_de_rede_nao_apaga_o_que_a_central_disse(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, situacao="PROTESTADO",
                 origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido(status="Pago")}, db=db)
    C.consultar(db)
    central(monkeypatch, {"9900001": API.CenprotError("fora do ar")}, db=db)
    r = C.consultar(db)
    assert r["parou"] == "fora do ar"
    linha = con.execute("SELECT * FROM cn_conferencias WHERE titulo_id = ?",
                        (tid,)).fetchone()
    assert linha["central_estado"] == C.PAGO
    assert linha["erro"] == "fora do ar" and linha["tentada_em"] == AGORA


def test_a_consulta_para_na_primeira_falha_de_rede(monkeypatch):
    """Quase cem pedidos, um por chamada: com a Central fora do ar, insistir
    faria o balcão esperar um minuto por título."""
    con = banco()
    db = BancoDeMesa(con)
    for n in ("9900001", "9900002", "9900003"):
        titulo(con, numero=f"{n}/1", protocolo=n + "000",
               origem_chave=f"CENPROT-PEDIDO:{n}")
    chamadas = central(monkeypatch,
                       {"9900001": API.CenprotError("sem internet")}, db=db)
    r = C.consultar(db)
    assert chamadas == ["9900001"]
    assert r["nao_perguntados"] == 2 and r["parou"]


def test_a_recusa_da_central_num_pedido_nao_para_os_outros(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    titulo(con, numero="1/1", protocolo="1", origem_chave="CENPROT-PEDIDO:9900001")
    titulo(con, numero="2/1", protocolo="2", origem_chave="CENPROT-PEDIDO:9900002")
    chamadas = central(monkeypatch, {
        "9900001": API.CenprotRecusou("recusou este"),
        "9900002": pedido("9900002", numero_titulo="2/1", protocolo="2")}, db=db)
    r = C.consultar(db)
    assert chamadas == ["9900001", "9900002"]
    assert r["achados"] == 1 and r["com_erro"] == 1 and not r["parou"]


def test_titulo_sem_numero_de_pedido_nao_consulta_e_aparece(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem="CENPROT", origem_chave="tbAvisoProtesto:7.0",
                 cra=None)
    chamadas = central(monkeypatch, {}, db=db)
    r = C.consultar(db)
    assert chamadas == [] and r["sem_pedido"] == 1
    assert "SEM_PEDIDO" in regras(con, tid)


# --------------------------------------------- o caso do 350574


def _o_caso(con, monkeypatch, db):
    """Dois títulos com o mesmo protocolo, valor e devedor: A protestado aqui
    e PAGO na Central; B pago no balcão (E-Ofício) e «apontado» na Central."""
    a = titulo(con, numero="123/1", situacao="PROTESTADO",
               origem_chave="CENPROT-PEDIDO:9900001")
    ato(con, a, "PROTESTO", data="2026-10-28")
    b = titulo(con, numero="123/2", situacao="PAGO",
               origem_chave="tbAvisoProtesto:9.0", cra="000000009900002")
    ato(con, b, "PAGAMENTO", origem="EOFICIO", data="2026-08-11")
    central(monkeypatch, {
        "9900001": pedido("9900001", status="Pago"),
        "9900002": pedido("9900002", numero_titulo="123/2")}, db=db)
    C.consultar(db)
    return a, b


def test_o_caso_do_350574_aparece_inteiro(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    a, b = _o_caso(con, monkeypatch, db)
    la = linha_de(con, a)
    assert la["nivel"] == C.DIVERGE
    pago = next(x for x in la["achados"] if x["regra"] == "CENTRAL_ENCERROU_PAGO")
    assert "nunca lavrou pagamento" in pago["frase"]
    assert "PROTOCOLO_EM_DOIS_TITULOS" in regras(con, a)
    lb = linha_de(con, b)
    saiu = next(x for x in lb["achados"]
                if x["regra"] == "SAIU_AQUI_E_A_CENTRAL_NAO_SABE")
    assert "E-Ofício" in saiu["caminho"] and "Liquidação" in saiu["caminho"]
    assert C.quantos_divergem(con) == 2


def test_o_cedente_divergente_aparece_e_nao_trava(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001",
                 cedente="CEDENTE GRAVADO AQUI")
    central(monkeypatch, {"9900001": pedido(cedente="OUTRO CEDENTE")}, db=db)
    C.consultar(db)
    [ced] = [x for x in linha_de(con, tid)["achados"]
             if x["regra"] == "CEDENTE_DIFERENTE"]
    assert ced["nivel"] == C.CONFERIR and not ced["trava"]
    assert "OUTRO CEDENTE" in ced["frase"]


def test_pedido_de_outro_titulo_ou_de_outro_devedor_trava(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido(numero_titulo="999/9",
                                            devedor=OUTRO_CPF)}, db=db)
    C.consultar(db)
    travas = {x["regra"] for x in linha_de(con, tid)["trava"]}
    assert {"PEDIDO_DE_OUTRO_TITULO", "DEVEDOR_DIFERENTE"} <= travas


# --------------------------------------------- a liquidação do portal


def test_a_liquidacao_no_pedido_errado_aparece_nos_dois(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    a, b = _o_caso(con, monkeypatch, db)
    with db.transaction() as c:
        r = C.registrar_liquidacao(
            c, pedido="9900001", titulo_id=b, liquidada_em="2026-10-27",
            afirmo=True, afirmacao=("Afirmo, sob minha responsabilidade, que "
                                    "liquidei este pedido no portal."),
            quem="ESCREVENTE DE TESTE", agora=AGORA)
    assert "LIQUIDACAO_EM_PEDIDO_DE_OUTRO_TITULO" in {x["regra"] for x in r["achados"]}
    assert "LIQUIDACAO_DESTE_PEDIDO_POR_OUTRO_TITULO" in regras(con, a)


def test_a_liquidacao_exige_a_afirmacao_e_titulo_cenprot(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    banco_tid = titulo(con, numero="9/9", origem="CRA", apresentante="001",
                       protocolo="9", origem_chave="CRA:1:1")
    texto = "Afirmo, sob minha responsabilidade, que liquidei no portal."
    with db.transaction() as c:
        with pytest.raises(C.ConferenciaError, match="Afirmo"):
            C.registrar_liquidacao(c, pedido="9900001", titulo_id=tid,
                                   afirmo=False, afirmacao=texto, agora=AGORA)
        with pytest.raises(C.ConferenciaError, match="30 letras"):
            C.registrar_liquidacao(c, pedido="9900001", titulo_id=tid,
                                   afirmo=True, afirmacao="." * 60, agora=AGORA)
        with pytest.raises(C.ConferenciaError, match="não veio da CENPROT"):
            C.registrar_liquidacao(c, pedido="9900001", titulo_id=banco_tid,
                                   afirmo=True, afirmacao=texto, agora=AGORA)
        C.registrar_liquidacao(c, pedido="9900001", titulo_id=tid, afirmo=True,
                               afirmacao=texto, agora=AGORA)
        with pytest.raises(C.ConferenciaError, match="já está"):
            C.registrar_liquidacao(c, pedido="9900001", titulo_id=tid,
                                   afirmo=True, afirmacao=texto, agora=AGORA)


def test_anular_exige_motivo_e_nao_apaga(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    with db.transaction() as c:
        r = C.registrar_liquidacao(
            c, pedido="9900001", titulo_id=tid, afirmo=True,
            afirmacao="Afirmo, sob minha responsabilidade, que liquidei no portal.",
            agora=AGORA)
        with pytest.raises(C.ConferenciaError, match="motivo"):
            C.anular_liquidacao(c, r["id"], motivo="curto")
        C.anular_liquidacao(c, r["id"], motivo="registrado no título errado",
                            quem="ESCREVENTE DE TESTE", agora=AGORA)
    linha = con.execute("SELECT * FROM cn_liquidacoes_portal WHERE id = ?",
                        (r["id"],)).fetchone()
    assert linha is not None and linha["anulada_em"] == AGORA


# --------------------------------------------- a trava do protesto


TEXTO = ("Afirmo, sob minha responsabilidade, que conferi o pedido no portal "
         "da CENPROT e que o título não foi pago.")


def test_titulo_de_banco_nao_chama_a_central(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem="CRA", apresentante="001", origem_chave="CRA:1:1")
    chamadas = central(monkeypatch, {}, db=db)
    assert C.trava_do_protesto(db, tid) is None
    assert chamadas == []


def test_titulo_nao_intimado_nao_chama_a_central(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, situacao="APONTADO", origem_chave="CENPROT-PEDIDO:9900001")
    chamadas = central(monkeypatch, {}, db=db)
    assert C.trava_do_protesto(db, tid) is None and chamadas == []


def test_a_central_confere_e_o_protesto_passa_sem_afirmacao(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido()}, db=db)
    assert C.trava_do_protesto(db, tid, quem="teste") is None


def test_a_central_da_por_pago_e_o_protesto_nao_sai(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido(status="Pago")}, db=db)
    with pytest.raises(C.ConferenciaError, match="NÃO lavrado") as e:
        C.trava_do_protesto(db, tid)
    assert e.value.regra == C.REGRA_DIVERGENTE
    # E a consulta da trava fica guardada para a tela.
    assert con.execute("SELECT central_estado FROM cn_conferencias "
                       "WHERE titulo_id = ?", (tid,)).fetchone()[0] == C.PAGO


def test_com_a_afirmacao_passa_e_devolve_o_contrato(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido(status="Pago")}, db=db)
    r = C.trava_do_protesto(db, tid, afirmo=True, afirmacao=TEXTO)
    assert r["regra"] == C.REGRA_DIVERGENTE and r["afirmacao"] == TEXTO
    assert "pago" in r["o_que_faltava"] and r["pedido"] == "9900001"
    assert set(C.detalhe_da_auditoria(r)) == {"regra", "afirmacao",
                                              "o_que_faltava", "pedido"}


def test_sem_rede_recusa_dizendo_que_nao_deu_para_conferir(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": API.CenprotError("sem internet")}, db=db)
    with pytest.raises(C.ConferenciaError, match="não deu para") as e:
        C.trava_do_protesto(db, tid)
    assert e.value.regra == C.REGRA_NAO_CONFERIDO and e.value.sem_rede
    r = C.trava_do_protesto(db, tid, afirmo=True, afirmacao=TEXTO)
    assert r["regra"] == C.REGRA_NAO_CONFERIDO


def test_sem_credencial_tambem_nao_confere(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": CRED.CredencialError("sem senha")}, db=db)
    with pytest.raises(C.ConferenciaError) as e:
        C.trava_do_protesto(db, tid)
    assert e.value.regra == C.REGRA_NAO_CONFERIDO


def test_sem_numero_de_pedido_nao_confere(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="tbAvisoProtesto:3.0", cra=None)
    central(monkeypatch, {}, db=db)
    with pytest.raises(C.ConferenciaError, match="número do pedido") as e:
        C.trava_do_protesto(db, tid)
    assert e.value.regra == C.REGRA_NAO_CONFERIDO


def test_no_lote_nao_se_afirma(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido(status="Pago")}, db=db)
    with pytest.raises(C.ConferenciaError, match="ficha"):
        C.trava_do_protesto(db, tid, afirmo=True, afirmacao=TEXTO, em_lote=True)


def test_no_lote_caida_a_rede_os_seguintes_nao_esperam(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    chamadas = central(monkeypatch, {}, db=db)
    with pytest.raises(C.ConferenciaError) as e:
        C.trava_do_protesto(db, tid, em_lote=True, perguntar=False)
    assert chamadas == [] and e.value.sem_rede


def test_robo_nao_afirma(monkeypatch):
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    central(monkeypatch, {"9900001": pedido(status="Pago")}, db=db)
    with pytest.raises(C.ConferenciaError, match="robô"):
        C.trava_do_protesto(db, tid, afirmo=True, afirmacao=TEXTO, robo=True)


def test_afirmacao_sem_letras_nao_vale():
    with pytest.raises(C.ConferenciaError):
        C.validar_afirmacao(True, "." * 80)
    with pytest.raises(C.ConferenciaError, match="Afirmo"):
        C.validar_afirmacao(False, TEXTO)
    assert C.validar_afirmacao("1", "  " + TEXTO + "  ") == TEXTO


def test_a_liquidacao_registrada_trava_o_protesto_do_titulo(monkeypatch):
    """Para a Central, o pedido liquidado está pago — mesmo que a consulta
    não tenha sido feita depois."""
    con = banco()
    db = BancoDeMesa(con)
    tid = titulo(con, origem_chave="CENPROT-PEDIDO:9900001")
    outro = titulo(con, numero="5/5", protocolo="5",
                   origem_chave="CENPROT-PEDIDO:9900005")
    with db.transaction() as c:
        C.registrar_liquidacao(c, pedido="9900001", titulo_id=outro,
                               afirmo=True, afirmacao=TEXTO, agora=AGORA)
    central(monkeypatch, {"9900001": pedido()}, db=db)
    with pytest.raises(C.ConferenciaError) as e:
        C.trava_do_protesto(db, tid)
    assert e.value.regra == C.REGRA_DIVERGENTE


def test_a_afirmacao_vai_ao_detalhe_do_ato_sem_apagar_o_que_havia():
    con = banco()
    tid = titulo(con)
    aid = ato(con, tid, "PROTESTO", detalhe=json.dumps({"triduo": {"x": 1}}))
    afirm = {"regra": C.REGRA_DIVERGENTE, "afirmacao": TEXTO,
             "o_que_faltava": "a Central dá por pago", "pedido": "9900001"}
    db = BancoDeMesa(con)
    with db.transaction() as c:
        C.anotar_afirmacao_no_ato(c, aid, afirm, quem="ESCREVENTE", agora=AGORA)
        C.anotar_afirmacao_no_ato(c, aid, dict(afirm, regra="OUTRA"), agora=AGORA)
    detalhe = json.loads(con.execute(
        "SELECT detalhe_json FROM pt_atos WHERE id = ?", (aid,)).fetchone()[0])
    assert detalhe["triduo"] == {"x": 1}
    assert [x["regra"] for x in detalhe[C.CHAVE_NO_DETALHE]] == [
        C.REGRA_DIVERGENTE, "OUTRA"]
    assert detalhe[C.CHAVE_NO_DETALHE][0]["afirmacao"] == TEXTO


# --------------------------------------------- a forma do módulo


def test_o_modulo_nao_tem_funcao_que_corrija():
    """Ele compara e trava; quem corrige é gente, na ficha ou no portal."""
    arvore = ast.parse((RAIZ / "cenprot_conferencia.py").read_text(encoding="utf-8"))
    publicas = [n.name for n in arvore.body
                if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
    for nome in publicas:
        for proibido in ("lavrar", "protestar", "cancelar", "pagar", "selar",
                         "cobrar", "enviar", "protocolar", "processar", "corrigir"):
            assert proibido not in nome, (nome, proibido)
    # E não usa caminho que escreve na Central.
    texto = (RAIZ / "cenprot_conferencia.py").read_text(encoding="utf-8")
    for escreve in API.CAMINHOS_QUE_ESCREVEM:
        assert f'"{escreve}"' not in texto


def test_quem_fala_com_a_rede_recebe_db_e_quem_le_recebe_con():
    for f in (C.consultar, C.trava_do_protesto):
        assert next(iter(inspect.signature(f).parameters)) == "db", f.__name__
    for f in (C.quadro, C.da_ficha, C.quantos_divergem, C.registrar_liquidacao,
              C.anular_liquidacao, C.anotar_afirmacao_no_ato, C.liquidacoes):
        assert next(iter(inspect.signature(f).parameters)) == "con", f.__name__


def test_o_painel_do_protesto_conta_as_divergencias(monkeypatch):
    import protesto_roteiro as PR
    con = banco()
    db = BancoDeMesa(con)
    assert PR.medir_o_dia(con, hoje="2026-10-29")["cenprot_divergencias"] == 0
    _o_caso(con, monkeypatch, db)
    assert PR.medir_o_dia(con, hoje="2026-10-29")["cenprot_divergencias"] == 2

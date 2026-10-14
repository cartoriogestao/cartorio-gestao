"""O que a CENPROT manda, e o que a casa responde — o domínio.

O QUE ESTES TESTES GUARDAM
      - **a chamada de rede NÃO acontece dentro da transação** — é a regra
        desde o selador, e aqui ela se prova: o `db` de mentira grita se a
        API for chamada com uma transação aberta;
      - **`vieram`, `entraram` e `repetidas` são três contadores**, e somá-los
        é o defeito que a carga do acervo já cometeu;
      - **o ambiente entra na chave** — a anuência 1 da homologação e a
        anuência 1 da produção são duas linhas, e não uma;
      - **os nomes dos campos são os do contrato**, conferidos contra o
        `swagger.yaml` e não contra a minha lembrança;
      - **o teor congela** e a pendência já respondida não se redecide;
      - **dispensar exige motivo escrito**;
      - **a decisão judicial não sobe por aqui** — o sistema não julga ordem
        de juiz.
"""
from __future__ import annotations

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

import cenprot_pendencias as P
import centrais_cred as CRED
import cn_schema as CN
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-09-02T10:00:00"

CONTRATO = (RAIZ.parent.parent / "FONTES_EXTERNAS" / "cra21"
            / "cenprot_swagger_v2.1.0.yaml")
tem_contrato = pytest.mark.skipif(
    not CONTRATO.is_file(),
    reason="o swagger.yaml só existe na máquina de desenvolvimento")


# ------------------------------------------------------------ o banco de mesa


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_pt_schema(con)
    CN.init_cn_schema(con)
    return con


class BancoDeMesa:
    """O `db` que `baixar` e `enviar` recebem — **e o guarda desta suíte.**

    Ele **grita se a rede for chamada com uma transação aberta**. Sem isto o
    teste passaria com um `BEGIN IMMEDIATE` segurado por trinta segundos de
    rede, que é o defeito que põe todo outro balcão no `busy_timeout` — e é
    exatamente o tipo de coisa que nenhuma releitura pega.
    """

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


def titulo(con, *, chave="", protocolo="", numero="00123") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos
               (especie, numero_titulo, chave_cenprot, protocolo,
                origem, origem_chave, criado_em)
           VALUES ('DMI', ?, ?, ?, 'CENPROT', ?, ?)""",
        (numero, chave or None, protocolo or None,
         f"t-{numero}-{protocolo}", AGORA))
    return int(cur.lastrowid)


CHAVE_DA_CASA = "21987650141243301260417"      # medida, 175 de 175


def anuencia(codigo=1, **mudar) -> dict:
    item = {"cd_anuencia": codigo, "nm_chave": CHAVE_DA_CASA,
            "nm_nr_protocolo": "2604170001", "nm_devedor": "FULANO DA SILVA",
            "nm_nr_titulo": "00123", "vl_protesto": 200.95}
    item.update(mudar)
    return item


def api_devolve(monkeypatch, itens, *, db=None):
    """Troca a chamada de rede por uma que devolve os itens — **e confere que
    ela NÃO está sendo feita de dentro de uma transação.**"""
    def falsa(ambiente, pasta=None, **filtros):
        if db is not None:
            assert not db.dentro, (
                "a chamada de rede aconteceu DENTRO da transação — é o "
                "`BEGIN IMMEDIATE` segurado pela rede, que põe todo outro "
                "balcão no busy_timeout")
        return itens
    monkeypatch.setitem(P.BAIXA_DA_ESPECIE, CN.ANUENCIA, falsa)


# ------------------------------------------- os nomes vêm do contrato


@tem_contrato
def test_o_codigo_de_cada_especie_e_o_que_a_resposta_traz():
    """**Eu já inventei estes nomes uma vez, e errei em quase todos.**

    O caso que mais importa é o do cancelamento: o `POST` exige `cd_pedido` e
    a resposta do `GET` **não tem campo com esse nome** — tem `nr_pedido` e
    `cd_pedido_cartorio`. Este teste prova que cada nome escrito no módulo
    aparece na resposta daquela rota, e não na de outra.
    """
    y = CONTRATO.read_text(encoding="utf-8", errors="replace")
    corpo = y[re.search(r"^paths:$", y, re.MULTILINE).end():]
    rotas = [(m.group(1), m.start())
             for m in re.finditer(r"^  (/\S+):\s*$", corpo, re.MULTILINE)]
    trechos = {}
    for i, (nome, pos) in enumerate(rotas):
        fim = rotas[i + 1][1] if i + 1 < len(rotas) else len(corpo)
        trechos[nome] = corpo[pos:fim]

    onde = {CN.ANUENCIA: "/v2/anuencias",
            CN.CERTIDAO: "/v2/certidoes",
            CN.CANCELAMENTO: "/cancelamento/pedidos",
            CN.DECISAO_JUDICIAL: "/decisao-judicial/pendentes",
            CN.PEDIDO_PROTESTO: "/pedidos/consulta"}
    for especie, rota in onde.items():
        campo = P.CODIGO_DA_ESPECIE[especie]
        resposta = trechos[rota][trechos[rota].find("responses:"):]
        assert re.search(rf"^\s+{campo}:\s*$", resposta, re.MULTILINE), (
            f"«{campo}» não aparece na resposta de {rota}")


@tem_contrato
def test_o_cancelamento_NAO_usa_cd_pedido_porque_a_resposta_nao_o_tem():
    """A metade que o teste de cima não prova: que o nome ÓBVIO está errado."""
    assert P.CODIGO_DA_ESPECIE[CN.CANCELAMENTO] == "nr_pedido"
    y = CONTRATO.read_text(encoding="utf-8", errors="replace")
    trecho = y[y.find("  /cancelamento/pedidos:"):y.find("  /cancelamento/cancelar-protesto:")]
    resposta = trecho[trecho.find("responses:"):]
    assert not re.search(r"^\s+cd_pedido:\s*$", resposta, re.MULTILINE), (
        "a resposta passou a trazer `cd_pedido` — releia o contrato: a "
        "escolha do `nr_pedido` foi feita porque ele NÃO existia ali")


# ------------------------------------------- ler a resposta da Central


def test_o_campo_se_acha_aninhado_e_o_de_fora_ganha():
    """A Central devolve em blocos — `dados_pedido`, `dados_anuencia` —, e o
    `nm_chave` do pedido vale mais que o da anuência citada dentro dele."""
    item = {"nm_chave": "111", "dados_anuencia": {"nm_chave": "222"}}
    assert P._procurar(item, "nm_chave") == "111"
    fundo = {"dados_pedido": {"dados_do_titulo": {"nm_nr_titulo": "00123"}}}
    assert P._procurar(fundo, "nm_nr_titulo") == "00123"
    assert P._procurar({"a": 1}, "nao_existe") is None


def test_a_lista_se_le_crua_e_embrulhada():
    """**Ler só um jeito faria metade das telas dizer «nada pendente» com a
    Central cheia** — o pior tipo de zero, o que tem cara de medição."""
    assert len(P._lista_da_resposta([{"cd_anuencia": 1}])) == 1
    assert len(P._lista_da_resposta({"data": [{"cd_anuencia": 1}]})) == 1
    assert len(P._lista_da_resposta({"pedidos": [{"cd_pedido": 1}]})) == 1
    assert len(P._lista_da_resposta({"cd_anuencia": 9})) == 1     # item só
    assert P._lista_da_resposta(None) == []
    assert P._lista_da_resposta({"mensagem": "sem pendências"}) == []


# ------------------------------------------- a baixa


def test_a_baixa_conta_tres_coisas_diferentes(monkeypatch):
    """**`vieram`, `entraram` e `repetidas` são três**, e somá-los é o defeito
    que fez a carga do acervo dizer «entraram 20» com a tabela em zero."""
    db = BancoDeMesa(banco())
    api_devolve(monkeypatch, [anuencia(1), anuencia(2)], db=db)
    r = P.baixar(db, CN.ANUENCIA, quem="teste")
    assert (r["vieram"], r["entraram"], r["repetidas"]) == (2, 2, 0)

    api_devolve(monkeypatch, [anuencia(1), anuencia(2), anuencia(3)], db=db)
    r = P.baixar(db, CN.ANUENCIA, quem="teste")
    assert (r["vieram"], r["entraram"], r["repetidas"]) == (3, 1, 2)
    assert db.con.execute("SELECT COUNT(*) FROM cn_pendencias").fetchone()[0] == 3


def test_a_rede_nao_acontece_dentro_da_transacao(monkeypatch):
    """O guarda mora no `BancoDeMesa`: ele grita se a API for chamada com o
    `BEGIN IMMEDIATE` aberto. Este teste existe para dizer que ele é o ponto."""
    db = BancoDeMesa(banco())
    api_devolve(monkeypatch, [anuencia(1)], db=db)
    P.baixar(db, CN.ANUENCIA)
    assert db.dentro is False


def test_o_ambiente_faz_parte_da_chave(monkeypatch):
    """**`cd_anuencia = 1` existe na homologação E na produção.** Sem o
    ambiente na chave, a de teste ocuparia o lugar da de verdade — e a de
    verdade não entraria, sem erro em lugar nenhum."""
    db = BancoDeMesa(banco())
    api_devolve(monkeypatch, [anuencia(1)], db=db)
    P.baixar(db, CN.ANUENCIA, ambiente=CRED.HOMOLOGACAO)
    P.baixar(db, CN.ANUENCIA, ambiente=CRED.PRODUCAO)
    linhas = db.con.execute(
        "SELECT ambiente FROM cn_pendencias ORDER BY ambiente").fetchall()
    assert [r[0] for r in linhas] == [CRED.HOMOLOGACAO, CRED.PRODUCAO]


def test_pendencia_sem_codigo_nao_entra(monkeypatch):
    """**Não se inventa código.** Sem ele não há como responder à Central, e
    uma linha sem saída é pior que a ausência dela: o balcão a olharia todo
    dia sem ter o que fazer."""
    db = BancoDeMesa(banco())
    api_devolve(monkeypatch, [anuencia(1), {"nm_devedor": "SEM CODIGO"}], db=db)
    r = P.baixar(db, CN.ANUENCIA)
    assert (r["entraram"], r["sem_codigo"]) == (1, 1)


def test_o_teor_congela_como_a_Central_mandou(monkeypatch):
    """É o que ela mandou **naquele dia**; ela muda o dado dela amanhã, e o
    que a casa respondeu foi sobre isto aqui."""
    db = BancoDeMesa(banco())
    api_devolve(monkeypatch, [anuencia(1, vl_protesto=200.95)], db=db)
    P.baixar(db, CN.ANUENCIA)
    guardado = json.loads(db.con.execute(
        "SELECT teor FROM cn_pendencias").fetchone()[0])
    assert guardado["vl_protesto"] == 200.95
    assert guardado["nm_chave"] == CHAVE_DA_CASA


# ------------------------------------------- achar o título desta casa


def test_a_pendencia_acha_o_titulo_pela_chave(monkeypatch):
    db = BancoDeMesa(banco())
    tid = titulo(db.con, chave=CHAVE_DA_CASA)
    db.con.commit()
    api_devolve(monkeypatch, [anuencia(1)], db=db)
    r = P.baixar(db, CN.ANUENCIA)
    assert r["sem_titulo"] == 0
    assert db.con.execute(
        "SELECT titulo_id FROM cn_pendencias").fetchone()[0] == tid


def test_e_pelo_protocolo_quando_nao_ha_chave(monkeypatch):
    db = BancoDeMesa(banco())
    tid = titulo(db.con, protocolo="2604170001")
    db.con.commit()
    api_devolve(monkeypatch, [anuencia(1, nm_chave="")], db=db)
    P.baixar(db, CN.ANUENCIA)
    assert db.con.execute(
        "SELECT titulo_id FROM cn_pendencias").fetchone()[0] == tid


def test_nao_achar_o_titulo_NAO_derruba_a_baixa(monkeypatch):
    """**Pendência sem título é o que o balcão precisa olhar primeiro** — pode
    ser título que não entrou, ou pedido de outra casa. Deixá-la de fora a
    esconderia."""
    db = BancoDeMesa(banco())
    api_devolve(monkeypatch, [anuencia(1)], db=db)
    r = P.baixar(db, CN.ANUENCIA)
    assert (r["entraram"], r["sem_titulo"]) == (1, 1)
    assert db.con.execute(
        "SELECT titulo_id FROM cn_pendencias").fetchone()[0] is None


def test_chave_repetida_em_dois_titulos_nao_escolhe_no_escuro(monkeypatch):
    """Duas linhas com a mesma chave é defeito de dado, e escolher uma seria
    escolher no escuro — a pendência fica sem casar, e à vista."""
    db = BancoDeMesa(banco())
    titulo(db.con, chave=CHAVE_DA_CASA, numero="A")
    titulo(db.con, chave=CHAVE_DA_CASA, numero="B")
    db.con.commit()
    api_devolve(monkeypatch, [anuencia(1)], db=db)
    P.baixar(db, CN.ANUENCIA)
    assert db.con.execute(
        "SELECT titulo_id FROM cn_pendencias").fetchone()[0] is None


# ------------------------------------------- decidir, dispensar, enviar


def uma_pendencia(db, monkeypatch, codigo=1):
    api_devolve(monkeypatch, [anuencia(codigo)], db=db)
    P.baixar(db, CN.ANUENCIA)
    return db.con.execute("SELECT id FROM cn_pendencias").fetchone()[0]


def test_decidir_nao_manda_nada(monkeypatch):
    """**Decidir e enviar são dois passos** — a forma de conferir/receber da
    remessa, e pela mesma razão: o que sobe muda coisa na Central."""
    db = BancoDeMesa(banco())
    pid = uma_pendencia(db, monkeypatch)
    with db.transaction() as con:
        P.decidir(con, pid, decisao={"cd_anuencia": 1, "ic_aprovado": True},
                  quem="oficial", agora=AGORA)
    linha = db.con.execute(
        "SELECT situacao, decisao, enviada_em FROM cn_pendencias").fetchone()
    assert linha["situacao"] == CN.DECIDIDA
    assert linha["enviada_em"] is None
    assert json.loads(linha["decisao"])["ic_aprovado"] is True


def test_a_pendencia_ja_respondida_nao_se_redecide(monkeypatch):
    """**Nada sai duas vezes** — a regra do retorno à CRA. Redecidir o que já
    subiu faria a segunda resposta contradizer a primeira lá dentro."""
    db = BancoDeMesa(banco())
    pid = uma_pendencia(db, monkeypatch)
    db.con.execute("UPDATE cn_pendencias SET situacao = ?", (CN.ENVIADA,))
    db.con.commit()
    with db.transaction() as con, pytest.raises(P.PendenciaError) as e:
        P.decidir(con, pid, decisao={"x": 1}, quem="o", agora=AGORA)
    assert "já foi respondida" in str(e.value)


def test_dispensar_exige_motivo_escrito(monkeypatch):
    """Dispensar é decisão de quem responde pela serventia; ignorar não é."""
    db = BancoDeMesa(banco())
    pid = uma_pendencia(db, monkeypatch)
    with db.transaction() as con, pytest.raises(P.PendenciaError) as e:
        P.dispensar(con, pid, motivo="  ", quem="o", agora=AGORA)
    assert "por que" in str(e.value)
    with db.transaction() as con:
        P.dispensar(con, pid, motivo="pedido é de outra serventia",
                    quem="o", agora=AGORA)
    linha = db.con.execute(
        "SELECT situacao, dispensa_motivo FROM cn_pendencias").fetchone()
    assert linha["situacao"] == CN.DISPENSADA
    assert "outra serventia" in linha["dispensa_motivo"]


def test_o_dispensado_sai_da_fila_do_balcao(monkeypatch):
    """**Aviso sem saída é aviso que fica para sempre** — na terceira vez
    ninguém lê mais."""
    db = BancoDeMesa(banco())
    pid = uma_pendencia(db, monkeypatch)
    assert len(P.abertas(db.con)) == 1
    with db.transaction() as con:
        P.dispensar(con, pid, motivo="não é desta casa", quem="o", agora=AGORA)
    assert P.abertas(db.con) == []


def test_enviar_marca_o_que_subiu_e_guarda_a_resposta(monkeypatch):
    """**A resposta da Central fica gravada**, e não só o «deu certo»: quando
    ela reclamar de uma anuência, é esse texto que se lê."""
    db = BancoDeMesa(banco())
    pid = uma_pendencia(db, monkeypatch)
    with db.transaction() as con:
        P.decidir(con, pid, decisao={"cd_anuencia": 1, "ic_aprovado": True},
                  quem="o", agora=AGORA)

    def mandar(corpos, ambiente, *, pasta=None):
        assert not db.dentro, "o envio aconteceu DENTRO da transação"
        assert corpos == [{"cd_anuencia": 1, "ic_aprovado": True}]
        return {"message": "Processamento realizado com sucesso"}

    monkeypatch.setitem(P._MANDA_DA_ESPECIE, CN.ANUENCIA, mandar)
    r = P.enviar(db, CN.ANUENCIA, quem="o")
    assert r["enviadas"] == 1
    linha = db.con.execute(
        "SELECT situacao, enviada_em, resposta FROM cn_pendencias").fetchone()
    assert linha["situacao"] == CN.ENVIADA
    assert linha["enviada_em"] == AGORA
    assert "sucesso" in linha["resposta"]


def test_enviar_sem_nada_decidido_recusa_e_diz_o_que_fazer():
    db = BancoDeMesa(banco())
    with pytest.raises(P.PendenciaError) as e:
        P.enviar(db, CN.ANUENCIA)
    assert "Decida na lista" in str(e.value)


def test_a_decisao_judicial_nao_sobe_por_aqui():
    """**O sistema não julga ordem de juiz.** Quem registra a sustação, com o
    juízo, o processo e a data do recebimento, é o oficial."""
    db = BancoDeMesa(banco())
    with pytest.raises(P.PendenciaError) as e:
        P.enviar(db, CN.DECISAO_JUDICIAL)
    assert "oficial" in str(e.value)
    assert CN.DECISAO_JUDICIAL in P.ESPECIES_QUE_SO_SE_BAIXAM
    assert CN.DECISAO_JUDICIAL not in P._MANDA_DA_ESPECIE


def test_toda_especie_que_se_baixa_esta_declarada():
    """Espécie nova que nasça sem caminho de baixa fica vermelha aqui — em vez
    de a tela mostrar uma aba vazia no balcão, meses depois."""
    assert set(P.BAIXA_DA_ESPECIE) == set(CN.ESPECIES)
    assert set(P.CODIGO_DA_ESPECIE) == set(CN.ESPECIES)
    assert set(P._MANDA_DA_ESPECIE) | P.ESPECIES_QUE_SO_SE_BAIXAM == set(
        CN.ESPECIES)


# ------------------------------------------- as regras da casa


def test_o_painel_conta_e_nao_julga(monkeypatch):
    """Um zero pode ser «nada chegou» ou «ainda não baixei», e o sistema não
    sabe qual — por isso ele mostra o número E a última baixa."""
    db = BancoDeMesa(banco())
    uma_pendencia(db, monkeypatch)
    linhas = {li["especie"]: li for li in P.painel(db.con)}
    assert linhas[CN.ANUENCIA]["esperando"] == 1
    assert linhas[CN.ANUENCIA]["ultima_baixa"] == AGORA
    assert linhas[CN.CERTIDAO]["esperando"] == 0
    assert linhas[CN.CERTIDAO]["ultima_baixa"] is None
    for nome in dir(P):
        for palavra in ("atrasad", "vencid"):
            assert palavra not in nome.lower()


def test_quem_fala_com_a_rede_recebe_db_e_quem_le_recebe_con():
    """**A assinatura É o guarda.** Recebendo `db`, não há como chamar a rede
    de dentro de uma transação sem reparar nisso."""
    for nome in ("baixar", "enviar"):
        p = set(inspect.signature(getattr(P, nome)).parameters)
        assert "db" in p and "con" not in p, f"`{nome}` tem de receber `db`"
    for nome in ("abertas", "uma", "painel", "decidir", "dispensar",
                 "decididas"):
        p = set(inspect.signature(getattr(P, nome)).parameters)
        assert "con" in p and "db" not in p, f"`{nome}` tem de receber `con`"


def test_o_modulo_nao_tem_funcao_que_lavre_ato():
    """A regra do CNIB pela quarta vez: **avisar e preparar, ficando pendente
    o okay do cartório.**"""
    for nome in vars(P):
        if nome.startswith("_"):
            continue
        for palavra in ("lavrar", "protestar", "apontar", "numerar", "selar",
                        "averbar", "cobrar", "intimar"):
            assert palavra not in nome.lower(), (
                f"`{nome}` tem cara de quem lavra ato — quem lavra é a ficha "
                f"do título")


def test_o_codigo_do_cancelamento_esta_declarado_como_A_CONFERIR():
    """**Item declarado é diferente de item esquecido.** A escolha do
    `nr_pedido` saiu de dois exemplos do contrato, e não de um teste contra a
    Central — e isso tem de estar escrito onde alguém leia."""
    assert "homologação" in P.CODIGO_DO_CANCELAMENTO_A_CONFERIR
    assert "nr_pedido" in P.CODIGO_DO_CANCELAMENTO_A_CONFERIR


# ============================================================================
# O VALOR DA RETIRADA — sugerido, e não digitado.
# ============================================================================


def test_sem_titulo_nao_ha_faixa_e_a_sugestao_diz_isso():
    """**`None` não vira zero.** Zero num campo de dinheiro é uma afirmação —
    «não custa nada» —, e o devedor viria ao balcão com ela."""
    db = BancoDeMesa(banco())
    r = P.retirada_sugerida(db.con, {"titulo_id": None}, hoje=AGORA)
    assert r["centavos"] is None
    assert r["reais"] == ""
    assert "não casou" in r["motivo"]


def test_a_sugestao_usa_a_funcao_QUE_JA_EXISTE_e_nao_uma_parecida(monkeypatch):
    """**Uma segunda conta «parecida» divergiria no primeiro conserto** — e o
    que ela calcula é o que o devedor paga. A retirada é a constante somada da
    tabela mais a faixa do item 17.4, medida em 166 de 173 no centavo."""
    db = BancoDeMesa(banco())
    chamou = {}

    def preco_falso(con, valor_centavos, *, vigencia):
        chamou["valor"] = valor_centavos
        chamou["vigencia"] = vigencia
        return {"retirada": 8264, "cancelamento": 22468}

    monkeypatch.setattr(P.PC, "precos_do_titulo", preco_falso)
    monkeypatch.setattr(P.custas, "vigencia_do_dia",
                        lambda con, data: {"codigo": 10022})
    r = P.retirada_sugerida(
        db.con, {"titulo_id": 1, "titulo_valor_centavos": 20095}, hoje=AGORA)
    assert chamou == {"valor": 20095, "vigencia": 10022}
    assert r["centavos"] == 8264
    # **O ARQUIVO USA PONTO DECIMAL**, e não vírgula — medido nas 375 linhas.
    assert r["reais"] == "82.64"
    assert "17.4" in r["motivo"], "a sugestão diz de onde veio"


def test_valor_fora_de_faixa_nao_vira_zero(monkeypatch):
    db = BancoDeMesa(banco())
    monkeypatch.setattr(P.PC, "precos_do_titulo",
                        lambda con, v, *, vigencia: {"retirada": None,
                                                     "cancelamento": None})
    monkeypatch.setattr(P.custas, "vigencia_do_dia",
                        lambda con, data: {"codigo": 10022})
    r = P.retirada_sugerida(
        db.con, {"titulo_id": 1, "titulo_valor_centavos": 999999999},
        hoje=AGORA)
    assert r["centavos"] is None
    assert "faixa" in r["motivo"]


def test_a_falha_do_calculo_volta_como_MOTIVO_e_nao_como_zero(monkeypatch):
    """**`except` largo que devolve zero é zero com cara de medição** — a
    regra que este projeto já pagou três vezes."""
    db = BancoDeMesa(banco())

    def estoura(con, data):
        raise P.custas.CustasError("não há tabela de custas vigente")

    monkeypatch.setattr(P.custas, "vigencia_do_dia", estoura)
    r = P.retirada_sugerida(
        db.con, {"titulo_id": 1, "titulo_valor_centavos": 20095}, hoje=AGORA)
    assert r["centavos"] is None
    assert "tabela de custas" in r["motivo"]


def test_uma_traz_o_valor_do_titulo_para_a_sugestao_ter_de_onde_sair(
        monkeypatch):
    """Sem esta coluna na consulta, a sugestão nunca teria o que calcular — e
    falharia **calada**, sempre devolvendo «não casou»."""
    db = BancoDeMesa(banco())
    tid = titulo(db.con, chave=CHAVE_DA_CASA)
    db.con.execute("UPDATE pt_titulos SET valor_centavos = 20095 WHERE id = ?",
                   (tid,))
    db.con.commit()
    api_devolve(monkeypatch, [anuencia(1)], db=db)
    P.baixar(db, CN.ANUENCIA)
    pid = db.con.execute("SELECT id FROM cn_pendencias").fetchone()[0]
    p = P.uma(db.con, pid)
    assert p["titulo_valor_centavos"] == 20095


def test_o_roteiro_conta_o_que_ENTROU_hoje_da_cenprot(monkeypatch):
    """**O roteiro conta o que JÁ ACONTECEU; o painel conta o que ESPERA.**
    São duas perguntas, e responder uma com a outra faria a coluna «hoje»
    mostrar um número que nunca zera.

    Sem esta contagem, os três passos que ganharam tela em 02/09/2026
    ficariam com a coluna vazia — tela nova com medida em branco é o roteiro
    dizendo que não sabe de um passo que ele passou a fazer.
    """
    import protesto_roteiro as R

    db = BancoDeMesa(banco())
    api_devolve(monkeypatch, [anuencia(1), anuencia(2)], db=db)
    P.baixar(db, CN.ANUENCIA)

    hoje = R.o_que_ja_aconteceu_hoje(db.con, hoje=AGORA[:10])
    assert hoje["anuencia_baixada"] == 2
    assert hoje["cancelamento_cenprot_baixado"] == 0
    assert hoje["pedido_protesto_baixado"] == 0
    # **O DIA SEGUINTE COMEÇA EM ZERO** — a faixa é do dia, e não «tudo o que
    # existe». Se contasse tudo, a coluna nunca zeraria e o escrevente
    # deixaria de olhar.
    assert R.o_que_ja_aconteceu_hoje(
        db.con, hoje="2026-09-03")["anuencia_baixada"] == 0

    # e o roteiro aponta para as medidas que existem
    medidas = {p.get("medida") for p in R.ROTEIRO_DA_CENPROT if p.get("medida")}
    assert medidas <= set(hoje), (
        f"o roteiro cita medida que ninguém conta: {medidas - set(hoje)}")


def test_a_decidida_e_nao_enviada_aparece_no_QUE_FICOU_PELO_CAMINHO(
        monkeypatch):
    """**Ela é exatamente «o que começou e não terminou»:** alguém olhou,
    decidiu, e a Central ainda não sabe. Sem esta fonte ela ficaria esperando
    numa tela que só quem se lembra dela abre — e o roteiro das Centrais tem
    hora marcada.
    """
    import inacabados as INAC
    from ex_schema import init_ex_schema

    db = BancoDeMesa(banco())
    init_ex_schema(db.con)      # a tabela do que o oficial ajustou na tela
    pid = uma_pendencia(db, monkeypatch)

    # ainda sem decisão: não é «inacabado», é «não começado»
    assert not [x for x in INAC.lista(db.con, hoje="2026-09-03",
                                      chave="CENPROT_DECIDIDA")]

    with db.transaction() as con:
        P.decidir(con, pid, decisao={"cd_anuencia": 1, "ic_aprovado": True},
                  quem="o", agora=AGORA)
    achados = INAC.lista(db.con, hoje="2026-09-03", chave="CENPROT_DECIDIDA")
    assert len(achados) == 1
    # **O `id` DA FONTE TEM DE SERVIR À TELA DELA** — devolver outro produziria
    # um link que abre a ficha errada, e ninguém desconfia de uma ficha que
    # abre.
    assert achados[0]["id"] == pid

    # enviada: sai da lista sozinha, como todo ato concluído
    db.con.execute("UPDATE cn_pendencias SET situacao = ?", (CN.ENVIADA,))
    db.con.commit()
    assert not INAC.lista(db.con, hoje="2026-09-03",
                          chave="CENPROT_DECIDIDA")

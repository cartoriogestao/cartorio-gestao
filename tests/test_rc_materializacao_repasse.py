"""O valor de terceiro da materialização — F010, 25/11/2026 (solução B da CR004).

O QUE ESTES TESTES GUARDAM
    **O dinheiro do outro cartório entra no caixa numa natureza própria**,
    ligado ao protocolo da materialização e ao pedido da CRC, sem emolumento
    nem fundo desta casa e com «receita do titular = não».
    **Nenhum leitor o conta como receita**: relatório financeiro, carnê-leão,
    NFS-e (base do ISS e descrição da nota) e «selos × caixa» do mês.
    **O saldo de repasse da CRC** é o recebido (lançamento vivo) menos o
    destinado, e se destina no valor que o oficial quiser, até o saldo:
    ENVIAR À CRC exige despesa paga da categoria própria (natureza REPASSE:
    fora do Livro Diário e do SIAFERJ) e comprovante; TRANSFORMAR EM CAIXA não
    lança nada no caixa e é só do oficial. O mesmo pedido não se recebe duas
    vezes; o lançamento desfeito sai do saldo e vira aviso; o que o saldo já
    não cobre não se devolve nem se estorna.
    **O recibo do cliente leva o valor de terceiro em bloco separado** do
    emolumento desta casa.
    **O selo da materialização não muda**: o envelope é o mesmo, com ou sem
    pedido da CRC.

Nomes, cartórios e números fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import carne_leao as CL                                               # noqa: E402
import despesas as DP                                                 # noqa: E402
import gestor_conferencia as GC                                       # noqa: E402
import gestor_financeiro as GF                                        # noqa: E402
import nfse as NF                                                     # noqa: E402
import rc_materializacao as RCM                                       # noqa: E402
import rc_materializacao_repasse as RMR                               # noqa: E402
from bd_nativo import banco                                           # noqa: E402
from caixa_schema import NATUREZAS, NATUREZAS_DO_BALCAO, reais        # noqa: E402

HOJE = "2026-11-18"
AGORA = HOJE + "T10:00:00"
OPERADOR = "MARIO EXEMPLO DOS SANTOS"
PEDIDO = {"pedido_crc": "crc 2026/000123", "cartorio_nome": "CARTORIO EXEMPLO DO 1 OFICIO",
          "cartorio_cidade": "CIDADE EXEMPLO", "cartorio_uf": "pi",
          "emolumentos_origem": "40,00", "fundos_origem": "5,50",
          "forma_pagamento": "PIX", "pagador": "CARLA EXEMPLO"}


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


def _protocolo(db, numero="2026.11.901", atribuicao="RCPN", item="14.5.1") -> int:
    with db.transaction() as con:
        bd = banco(con)
        pid = int(bd.escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, interessado,
                   criado_em) VALUES (%s,%s,%s,'CARLA EXEMPLO',%s) RETURNING id""",
            (numero, HOJE, atribuicao, AGORA))[0]["id"])
        if item:
            bd.escrever(
                """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                       valor_total, emolumentos, ferc, fadep, femp, ferrfis)
                   VALUES (%s,'Materialização de certidão',%s,'53,58','47,84','1,44',
                           '1,91','1,91','0,48')""", (pid, item))
    return pid


def _caixa(db, operador=OPERADOR) -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO cx_caixas (data, operador_nome, saldo_inicial, aberto_em, situacao)
               VALUES (%s,%s,'0',%s,'ABERTO') RETURNING id""",
            (HOJE, operador, AGORA))[0]["id"])


def _receber(db, pid, caixa_id, hoje=HOJE, **mudar) -> dict:
    with db.transaction() as con:
        return RMR.receber(con, pid, {**PEDIDO, **mudar}, caixa_id=caixa_id, hoje=hoje,
                           hora="10:00", agora=hoje + "T10:00:00", usuario=OPERADOR)


def _lan(db, lid) -> dict:
    with db.connect() as con:
        return dict(banco(con).um("SELECT * FROM cx_lancamentos WHERE id=%s", (lid,)))


def _pend(db) -> dict:
    with db.connect() as con:
        return RMR.pendentes(con)


def _saldo(db) -> int:
    with db.connect() as con:
        return RMR.saldo(con)["saldo_centavos"]


def _destinar(db, destino, valor, **kw) -> dict:
    with db.transaction() as con:
        return RMR.destinar(con, destino=destino, valor=valor, dia=kw.pop("dia", HOJE),
                            hoje=HOJE, agora=AGORA, usuario="mario", **kw)


def _despesa(db, *, valor=4550, categoria=RMR.CATEGORIA_DA_DESPESA, pagar=True) -> int:
    agora = datetime(2026, 11, 18, 10, 0, tzinfo=timezone(timedelta(hours=-3)))
    with db.transaction() as con:
        i = DP.cadastrar(
            con, agora=agora, por="mario", origem="MANUAL", chave_origem=None,
            beneficiario_nome="CARTORIO EXEMPLO DO 1 OFICIO",
            beneficiario_documento="00000010000127", valor_centavos=valor,
            vencimento="2026-11-30", forma=DP.MANUAL, codigo="",
            descricao="Repasse do pedido CRC", categoria=categoria,
            documento_especie="Boleto da CRC", documento_numero="1")
        if pagar:
            DP.registrar_pago_fora(con, i, agora=agora, hoje=HOJE, por="mario",
                                   papel="ADMIN", data_pagamento=HOJE)
    return i


# ----------------------------------------------------------- a entrada


def test_o_valor_entra_numa_natureza_propria_ligado_ao_protocolo_e_ao_pedido(casa):
    db = casa["db"]
    pid, cx = _protocolo(db), _caixa(db)
    res = _receber(db, pid, cx)
    assert res["valor_centavos"] == 4550 and "prazo" not in res
    lan = _lan(db, res["lancamento_id"])
    assert (lan["natureza"], lan["sentido"]) == ("VALOR_DE_TERCEIRO", "ENTRADA")
    assert lan["protocolo_id"] == pid and lan["caixa_id"] == cx
    assert lan["valor"] == "45,50"
    assert lan["emolumentos"] is None and lan["ferc"] is None   # nada desta casa
    assert lan["receita_do_titular"] == 0
    assert lan["origem"] == RMR.ORIGEM
    assert lan["origem_chave"] == f"{RMR.TABELA}:{res['repasse_id']}"
    assert "CRC 2026/000123" in lan["descricao"] and "não é emolumento" in lan["descricao"]
    assert "CARTORIO EXEMPLO DO 1 OFICIO" in lan["descricao"]
    assert lan["hash_lancamento"] and lan["numero"]
    with db.connect() as con:
        r = RMR.registro(con, res["repasse_id"])
    assert r["pedido_crc"] == "CRC 2026/000123" and r["cartorio_uf"] == "PI"
    assert (r["emolumentos_origem_centavos"], r["fundos_origem_centavos"],
            r["taxa_crc_centavos"]) == (4000, 550, 0)
    assert r["situacao"] == RMR.RECEBIDO


def test_o_mesmo_pedido_nao_se_recebe_duas_vezes(casa):
    db = casa["db"]
    pid, cx = _protocolo(db), _caixa(db)
    _receber(db, pid, cx)
    with pytest.raises(RMR.RepasseTerceiroError, match="já foi recebido"):
        _receber(db, pid, cx)


@pytest.mark.parametrize("mudar, frase", [
    ({"pedido_crc": ""}, "número do pedido na CRC"),
    ({"cartorio_nome": ""}, "nome do cartório de origem"),
    ({"emolumentos_origem": ""}, "emolumentos cobrados lá"),
    ({"cartorio_uf": "PIA"}, "duas letras"),
    ({"forma_pagamento": "DEPOSITO_PREVIO"}, "não serve para valor de terceiro"),
    ({"forma_pagamento": "PG_CRC"}, "não serve para valor de terceiro"),
    ({"taxa_crc": "3,00"}, "taxa da CRC não entra"),
])
def test_o_que_falta_ou_nao_cabe_se_recusa_sem_gravar(casa, mudar, frase):
    db = casa["db"]
    pid, cx = _protocolo(db), _caixa(db)
    with pytest.raises(RMR.RepasseTerceiroError, match=frase):
        _receber(db, pid, cx, **mudar)
    with db.connect() as con:
        assert not banco(con).valor("SELECT count(*) AS n FROM cx_lancamentos "
                                    "WHERE natureza='VALOR_DE_TERCEIRO'")


def test_a_taxa_da_crc_so_entra_com_a_chave_ligada(casa):
    db = casa["db"]
    db.set_settings({RMR.CHAVE_DA_TAXA_CRC: "1"})
    pid, cx = _protocolo(db), _caixa(db)
    res = _receber(db, pid, cx, taxa_crc="3,00")
    assert res["valor_centavos"] == 4850


def test_o_protocolo_tem_de_ser_da_materializacao(casa):
    db = casa["db"]
    cx = _caixa(db)
    with pytest.raises(RMR.RepasseTerceiroError, match="não é do Registro Civil"):
        _receber(db, _protocolo(db, "2026.11.902", atribuicao="RI"), cx)
    with pytest.raises(RMR.RepasseTerceiroError, match="não tem o item 14.5.1"):
        _receber(db, _protocolo(db, "2026.11.903", item="14.5.6"), cx)
    with pytest.raises(RMR.RepasseTerceiroError, match="caixa aberto"):
        _receber(db, _protocolo(db, "2026.11.904"), 0)


# ---------------------------------------------- nenhum leitor conta como receita


def test_o_relatorio_financeiro_poe_o_valor_em_bloco_proprio_fora_da_receita(casa):
    db = casa["db"]
    pid, cx = _protocolo(db), _caixa(db)
    _receber(db, pid, cx)
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    try:
        r = GF.apurar_mes(con, 2026, 11)
    finally:
        con.close()
    assert r["valores_de_terceiros"] == [1, 45.5]
    assert sum(r["receita"].values()) == 0
    assert r["outras_entradas"] == [0, 0.0]
    assert any("terceiros" in k for k in r["entrou"])


def test_o_carne_leao_nao_conta_o_valor_de_terceiro(casa):
    db = casa["db"]
    pid, cx = _protocolo(db), _caixa(db)
    _receber(db, pid, cx)
    with db.connect() as con:
        bd = banco(con)
        for criterio in (CL.SELO, CL.PAGAMENTO):
            assert CL._recebido_no_caixa(bd, "2026-11", "PIX", 1000, criterio) == ([], [], [])
        apurado = CL.apurar(con, "2026-11")
    assert not apurado.get("receitas")
    assert not apurado.get("outras_entradas")


def test_a_base_do_iss_ignora_o_valor_de_terceiro_e_a_nota_diz_por_que():
    recibo = {"id": 1, "numero": 7, "ano": 2026, "valor_total": "99,08",
              "protocolo_numero": "2026.11.901",
              "discriminacao": json.dumps({"itens": [{"codigo_ato": "14.5.1",
                                                      "descricao": "Materialização"}],
                                           "terceiros": [{"valor": "45,50"}]})}
    lancamentos = [
        {"id": 1, "sentido": "ENTRADA", "natureza": "RECEBIMENTO", "valor": "53,58",
         "emolumentos": "47,84", "ferc": "1,44", "fadep": "1,91", "femp": "1,91",
         "ferrfis": "0,48"},
        {"id": 2, "sentido": "ENTRADA", "natureza": "VALOR_DE_TERCEIRO", "valor": "45,50"}]
    base, pend = NF.base_do_recibo(recibo, lancamentos, 1200)
    assert pend == []
    assert base == 4784 - NF.ferj_do_emolumento(4784, 1200)       # 42,10
    texto = NF.descricao_do_servico(recibo, base)
    assert "R$ 45,50 de valores de terceiros" in texto
    # o total do recibo menos o de terceiros é o que a frase dos fundos explica
    assert f"Valor total do recibo R$ 53,58, dos quais R$ {reais(5358 - base)}" in texto
    # o recibo só de valor de terceiro tem base zero, e não pendência
    assert NF.base_do_recibo(recibo, lancamentos[1:], 1200) == (0, [])


def test_selos_contra_caixa_do_mes_nao_conta_o_valor_de_terceiro(casa):
    db = casa["db"]
    pid, cx = _protocolo(db), _caixa(db)
    # Um valor grande, para passar da régua de R$ 50 e 5% se ele entrasse.
    _receber(db, pid, cx, emolumentos_origem="900,00", fundos_origem="")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    try:
        achados = GC.regra_fechamento_do_mes(con, date(2026, 11, 25))
    finally:
        con.close()
    assert [a for a in achados if "2026-11" in a["chave"]] == []


def test_a_natureza_nao_aparece_no_lancamento_avulso_do_balcao():
    assert "VALOR_DE_TERCEIRO" in NATUREZAS
    assert "VALOR_DE_TERCEIRO" not in NATUREZAS_DO_BALCAO


# ------------------------------------------------- o saldo de repasse da CRC


def test_o_saldo_e_o_recebido_menos_o_destinado_e_nao_tem_prazo(casa):
    db = casa["db"]
    cx = _caixa(db)
    a = _receber(db, _protocolo(db), cx)
    b = _receber(db, _protocolo(db, "2026.11.905"), cx, pedido_crc="CRC 2026/000124")
    p = _pend(db)
    assert [x["id"] for x in p["no_saldo"]] == [a["repasse_id"], b["repasse_id"]]
    assert p["saldo"]["saldo_centavos"] == 9100 and p["saldo"]["recebido"] == "91,00"
    assert all("prazo" not in x and "vencido" not in x for x in p["no_saldo"])
    with db.connect() as con:
        assert RMR.achados(con) == []                 # dinheiro no saldo não é aviso
    _destinar(db, RMR.CAIXA, "50,00")
    _destinar(db, RMR.ENVIO_CRC, "30,00", despesa_id=str(_despesa(db, valor=3000)),
              comprovante="AUT 123456")
    with db.connect() as con:
        s = RMR.saldo(con)
        destinos = RMR.destinacoes(con)
    assert (s["em_caixa_centavos"], s["enviado_crc_centavos"], s["saldo_centavos"]) \
        == (5000, 3000, 1100)
    assert [d["destino"] for d in destinos] == [RMR.ENVIO_CRC, RMR.CAIXA]
    # o pedido continua no saldo, sabendo de onde veio: a destinação não é por pedido
    assert [x["situacao"] for x in _pend(db)["no_saldo"]] == [RMR.RECEBIDO] * 2


def test_enviar_a_crc_exige_despesa_da_categoria_paga_e_comprovante(casa):
    db = casa["db"]
    _receber(db, _protocolo(db), _caixa(db))

    def enviar(**kw):
        base = {"despesa_id": None, "comprovante": "AUT 123456"}
        return _destinar(db, RMR.ENVIO_CRC, kw.pop("valor", "45,50"), **{**base, **kw})

    with pytest.raises(RMR.RepasseTerceiroError, match="número da despesa"):
        enviar()
    errada = _despesa(db, categoria="OUTRAS")
    with pytest.raises(RMR.RepasseTerceiroError, match="Livro Diário e ao SIAFERJ"):
        enviar(despesa_id=str(errada))
    nao_paga = _despesa(db, pagar=False)
    with pytest.raises(RMR.RepasseTerceiroError, match="ainda não foi paga"):
        enviar(despesa_id=str(nao_paga))
    pequena = _despesa(db, valor=1000)
    with pytest.raises(RMR.RepasseTerceiroError, match="não cabem nela"):
        enviar(despesa_id=str(pequena))
    certa = _despesa(db)
    with pytest.raises(RMR.RepasseTerceiroError, match="comprovante"):
        enviar(despesa_id=str(certa), comprovante="")
    with pytest.raises(RMR.RepasseTerceiroError, match="futuro"):
        enviar(despesa_id=str(certa), dia="2026-12-01")
    with pytest.raises(RMR.RepasseTerceiroError, match="não se destina"):
        enviar(despesa_id=str(certa), valor="50,00")
    feito = enviar(despesa_id=str(certa))
    assert feito["despesa_id"] == certa and feito["saldo_centavos"] == 0
    assert _saldo(db) == 0


def test_transformar_em_caixa_nao_lanca_nada_nem_vira_receita(casa):
    db = casa["db"]
    _receber(db, _protocolo(db), _caixa(db))
    with db.connect() as con:
        antes = banco(con).ler("SELECT * FROM cx_lancamentos ORDER BY id")
    with pytest.raises(RMR.RepasseTerceiroError, match="maior que zero"):
        _destinar(db, RMR.CAIXA, "")
    with pytest.raises(RMR.RepasseTerceiroError, match="destino do saldo"):
        _destinar(db, "CREDITOS_CRC", "10,00")
    feito = _destinar(db, RMR.CAIXA, "45,50", observacao="o saldo da CRC se pagou")
    assert feito["saldo_centavos"] == 0 and feito["despesa_id"] is None
    with db.connect() as con:
        depois = banco(con).ler("SELECT * FROM cx_lancamentos ORDER BY id")
    assert [dict(x) for x in depois] == [dict(x) for x in antes]
    with pytest.raises(RMR.RepasseTerceiroError, match="não se destina"):
        _destinar(db, RMR.CAIXA, "0,01")


def test_a_categoria_do_envio_e_repasse_e_nao_vai_ao_livro_diario_nem_ao_siaferj(casa):
    db = casa["db"]
    assert DP.CATEGORIAS[RMR.CATEGORIA_DA_DESPESA][1] == DP.REPASSE
    i = _despesa(db)
    with db.connect() as con:
        d = DP.despesa(con, i)
        assert d["natureza"] == DP.REPASSE and d["situacao"] == DP.PAGA_FORA
        assert d["ld_despesa_id"] is None
        assert not banco(con).valor("SELECT count(*) AS n FROM ld_despesas")
        rel = DP.relatorio_do_mes(con, "2026-11")
    assert [d["id"] for d in rel["linhas"]] == [i]       # entra no relatório...
    assert rel["total"][DP.REPASSE] == 4550 and rel["total"][DP.DESPESA] == 0
    assert DP.lancamentos_para_o_siaferj(rel) == []      # ...e não no SIAFERJ


def test_o_lancamento_desfeito_sai_do_saldo_e_vira_aviso_ate_encerrar(casa):
    db = casa["db"]
    res = _receber(db, _protocolo(db), _caixa(db))
    with db.transaction() as con:
        banco(con).escrever("UPDATE cx_lancamentos SET estornado=1 WHERE id=%s",
                            (res["lancamento_id"],))
    p = _pend(db)
    assert p["no_saldo"] == [] and [x["id"] for x in p["desfeitos"]] == [res["repasse_id"]]
    assert p["saldo"]["saldo_centavos"] == 0
    with db.connect() as con:
        [aviso] = RMR.achados(con)
    assert aviso["chave"] == f"REPASSE_TERCEIRO_DESFEITO:{res['repasse_id']}"
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    try:
        [g] = GC.regra_repasse_de_terceiro(con, date(2026, 11, 23))
    finally:
        con.close()
    assert g["regra"] == "REPASSE_DE_TERCEIRO" and g["gravidade"] == "ATENCAO"
    with db.transaction() as con:
        assert RMR.encerrar_sem_repasse(con, res["repasse_id"], agora=AGORA,
                                        motivo="Lançado no protocolo errado")["situacao"] \
            == RMR.CANCELADO
    assert _pend(db)["desfeitos"] == []
    # o pedido cancelado solta a vaga: pode ser recebido de novo
    _receber(db, _protocolo(db, "2026.11.905"), _caixa(db, "OUTRA PESSOA"))


def test_pedido_negado_so_sai_do_saldo_com_a_devolucao_lancada_no_caixa(casa):
    db = casa["db"]
    pid, cx = _protocolo(db), _caixa(db)
    res = _receber(db, pid, cx)

    def encerrar(dev):
        with db.transaction() as con:
            return RMR.encerrar_sem_repasse(con, res["repasse_id"], agora=AGORA,
                                            motivo="Pedido negado pela CRC", devolucao=dev)

    with pytest.raises(RMR.RepasseTerceiroError, match="Lance antes a devolução"):
        encerrar("")
    with db.transaction() as con:
        bd = banco(con)
        parcial = bd.escrever(
            """INSERT INTO cx_lancamentos (numero, ano, caixa_id, protocolo_id, data,
                   natureza, sentido, valor, criado_em)
               VALUES (900, 2026, %s, %s, %s, 'DEVOLUCAO', 'SAIDA', '20,00', %s)
               RETURNING id""", (cx, pid, HOJE, AGORA))
        inteira = bd.escrever(
            """INSERT INTO cx_lancamentos (numero, ano, caixa_id, protocolo_id, data,
                   natureza, sentido, valor, criado_em)
               VALUES (901, 2026, %s, %s, %s, 'DEVOLUCAO', 'SAIDA', '45,50', %s)
               RETURNING id""", (cx, pid, HOJE, AGORA))
    assert parcial and inteira
    with pytest.raises(RMR.RepasseTerceiroError, match="devolução parcial"):
        encerrar("900/2026")
    assert encerrar("901/2026")["situacao"] == RMR.DEVOLVIDO
    assert _saldo(db) == 0
    with db.connect() as con:
        assert RMR.ids_de_devolucao(con) == {int(inteira[0]["id"])}


def test_o_que_o_saldo_ja_nao_cobre_nao_se_devolve_nem_se_estorna(casa):
    db = casa["db"]
    res = _receber(db, _protocolo(db), _caixa(db))
    with db.connect() as con:
        assert RMR.recusa_ao_desfazer(con, res["lancamento_id"]) is None
    _destinar(db, RMR.CAIXA, "10,00")
    with db.connect() as con:
        assert "já não está no saldo" in RMR.recusa_ao_desfazer(con, res["lancamento_id"])
    with pytest.raises(RMR.RepasseTerceiroError, match="já não está no saldo"):
        with db.transaction() as con:
            RMR.encerrar_sem_repasse(con, res["repasse_id"], agora=AGORA,
                                     motivo="Pedido negado pela CRC", devolucao="1/2026")


# ------------------------------------------------------------- as telas


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _avisos(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", a).strip() for a in re.findall(
        r'<div class="flash[^"]*"[^>]*>(.*?)</div>', html, flags=re.DOTALL))


def _post(c, url, tela, **dados):
    html = c.get(tela).get_data(as_text=True)
    return c.post(url, data={"csrf_token": _token(html), **dados},
                  follow_redirects=True).get_data(as_text=True)


def test_o_balcao_recebe_pela_tela_e_o_recibo_separa_o_valor_de_terceiro(casa):
    db, c = casa["db"], casa["c"]
    html = _post(c, "/caixa", "/caixa", acao="abrir", saldo_inicial="0")
    pid = _protocolo(db)
    html = _post(c, "/rcpn/materializacoes/terceiros", "/rcpn/materializacoes",
                 protocolo="2026.11.901", **PEDIDO)
    assert "Valor de terceiro recebido: R$ 45,50" in _avisos(html), _avisos(html)
    # a materialização desta casa, quitada como qualquer item do protocolo
    with db.transaction() as con:
        bd = banco(con)
        caixa_id = bd.valor("SELECT id FROM cx_caixas WHERE situacao='ABERTO' "
                            "ORDER BY id DESC LIMIT 1")
        item = bd.valor("SELECT id FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))
        from caixa_schema import cobrar_item_do_protocolo
        cobrar_item_do_protocolo(con, item, caixa_id=caixa_id, forma_pagamento="PIX",
                                 hoje=date.today().isoformat(), hora="10:00",
                                 agora=AGORA, usuario="mario", usuario_id=None)
    ficha = c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Valores de terceiros (repasse a outro cartório)" in ficha
    assert "CRC 2026/000123" in ficha
    resp = c.post(f"/caixa/protocolos/{pid}/recibo",
                  data={"csrf_token": _token(ficha)})
    assert resp.status_code in (302, 303), resp.get_data(as_text=True)[:500]
    with db.connect() as con:
        bd = banco(con)
        r = bd.um("SELECT * FROM cx_recibos WHERE protocolo_id=%s", (pid,))
        sem_recibo = bd.valor("SELECT count(*) AS n FROM cx_lancamentos "
                              "WHERE protocolo_id=%s AND recibo_id IS NULL", (pid,))
    assert r["valor_total"] == "99,08" and sem_recibo == 0
    dados = json.loads(r["discriminacao"])
    assert dados["total_serventia"] == "53,58" and dados["total_terceiros"] == "45,50"
    assert dados["fundos"]["emolumentos"] == "47,84"          # só o desta casa
    [t] = dados["terceiros"]
    assert t["pedido_crc"] == "CRC 2026/000123" and t["valor"] == "45,50"
    # o papel: bloco próprio, com a frase de que não é emolumento desta casa
    import caixa_web
    with db.connect() as con:
        papel = caixa_web.html_do_recibo(
            con, r, settings=db.get_settings(), emitido_por="MARIO", funcao="",
            data_extenso="18 de novembro de 2026", agora="18/11/2026 10:00")
    assert "VALORES DE TERCEIROS — não são emolumentos nem fundos desta serventia" in papel
    assert "De terceiros, a repassar:</b> R$ 45,50" in papel
    # e a NFS-e: a base é só a do 14.5.1 desta casa
    with db.connect() as con:
        [item_nf] = NF.avaliar(banco(con), [dict(r)], db.get_settings())
    assert item_nf["base"] == 4784 - NF.ferj_do_emolumento(4784, 1200)


def test_o_bloco_do_recibo_e_o_mesmo_no_padrao_e_no_modelo_ajustado():
    import caixa_web
    padrao = (RAIZ / "modelos_padrao" / "caixa" / "CAIXA_RECIBO.txt").read_text(encoding="utf-8")
    assert "{% if terceiros %}" + caixa_web.BLOCO_DE_TERCEIROS_DO_RECIBO + "{% endif %}" in padrao


def test_o_lancamento_avulso_recusa_o_valor_de_terceiro(casa):
    c = casa["c"]
    _post(c, "/caixa", "/caixa", acao="abrir", saldo_inicial="0")
    html = _post(c, "/caixa", "/caixa", acao="lancar", natureza="VALOR_DE_TERCEIRO",
                 valor="45,50", forma_pagamento="PIX")
    assert "se recebe na tela da materialização" in _avisos(html)
    with casa["db"].connect() as con:
        assert not banco(con).valor("SELECT count(*) AS n FROM cx_lancamentos "
                                    "WHERE natureza='VALOR_DE_TERCEIRO'")


def test_a_tela_do_saldo_mostra_de_onde_veio_e_destina(casa):
    db, c = casa["db"], casa["c"]
    _receber(db, _protocolo(db), _caixa(db), hoje=date.today().isoformat())
    html = c.get("/rcpn/materializacoes/repasses").get_data(as_text=True)
    assert "Saldo — R$ 45,50" in html and "CRC 2026/000123" in html
    assert "CARTORIO EXEMPLO DO 1 OFICIO" in html
    assert "Enviar à CRC" in html and "Transformar em caixa" in html
    tela = c.get("/rcpn/materializacoes").get_data(as_text=True)
    assert "Saldo de repasse da CRC:</strong> R$ 45,50" in tela
    assert "Receber o valor do outro cartório" in tela
    html = _post(c, "/rcpn/materializacoes/repasses/virar-caixa",
                 "/rcpn/materializacoes/repasses", valor="20,00",
                 dia=date.today().isoformat())
    assert "R$ 20,00 transformado em caixa" in _avisos(html), _avisos(html)
    despesa = _despesa(db, valor=2550)
    html = _post(c, "/rcpn/materializacoes/repasses/enviar-crc",
                 "/rcpn/materializacoes/repasses", valor="25,50",
                 dia=date.today().isoformat(), despesa_id=str(despesa),
                 comprovante="AUT 777")
    assert "R$ 25,50 enviado à CRC" in _avisos(html), _avisos(html)
    assert "Saldo — R$ 0,00" in html and "Para onde foi" in html
    # transformar em caixa é decisão do oficial; enviar à CRC, de quem responde pelo caixa
    vistas = casa["app"].view_functions
    assert vistas["rcpn_materializacao_virar_caixa"].papeis_exigidos == ("ADMIN",)
    assert vistas["rcpn_materializacao_enviar_crc"].papeis_exigidos == ("ADMIN", "MANAGER")


# ------------------------------------------------------------- o selo


def test_o_envelope_do_selo_nao_muda_com_o_pedido_da_crc():
    campos = {"nome_parte": "BEATRIZ EXEMPLO", "cartorio_nome": "CARTORIO EXEMPLO",
              "cartorio_cidade": "CIDADE EXEMPLO", "cartorio_uf": "PI",
              "funcionario_expedidor": "MARIO EXEMPLO", "valor_emolumentos": "45,50"}
    sem = RCM.envelope(RCM.conferir(campos), escrevente="E", versao_tabela="0120260101")
    com = RCM.envelope(RCM.conferir({**campos, "pedido_crc": "CRC 1"}),
                       escrevente="E", versao_tabela="0120260101")
    assert sem == com
    assert com["codigoAto"] == "14.5.1"
    assert "CRC 1" not in json.dumps(com) and "pedido_crc" not in json.dumps(com)


def test_a_materializacao_selada_se_liga_ao_valor_recebido_pelo_pedido(casa):
    db = casa["db"]
    res = _receber(db, _protocolo(db), _caixa(db))
    with db.transaction() as con:
        mid = RCM.registrar(con, {"nome_parte": "BEATRIZ EXEMPLO",
                                  "cartorio_nome": "CARTORIO EXEMPLO",
                                  "cartorio_cidade": "CIDADE EXEMPLO",
                                  "cartorio_uf": "PI", "funcionario_expedidor": "MARIO",
                                  "valor_emolumentos": "40,00",
                                  "pedido_crc": "crc 2026/000123"},
                            agora=AGORA, usuario="mario")
        assert RMR.vincular_materializacao(con, mid, "crc 2026/000123") == 1
    with db.connect() as con:
        assert RMR.registro(con, res["repasse_id"])["materializacao_id"] == mid
        [m] = [x for x in RCM.listar(con) if x["id"] == mid]
    assert m["pedido_crc"] == "CRC 2026/000123" and m["repasse_situacao"] == RMR.RECEBIDO

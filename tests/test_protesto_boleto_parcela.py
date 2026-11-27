# -*- coding: utf-8 -*-
"""A cobrança da intimação pela Parcela Express (PR007): um boleto híbrido
registrado (linha digitável e Pix no mesmo documento), com o prazo do aviso,
uma viva por título, baixa pela venda paga e cancelamento do que não vale mais.

A PARCELA AQUI É DE MENTIRA, E SEM REDE: `ParcelaDeMentira` responde como a
API dos boletos (`protesto_boleto_parcela`, cabeçalho) e guarda o estado em memória.
Nenhum teste fala com o sandbox nem com a produção da Parcela; o transporte
recusa qualquer endereço que não seja um dos dois e não abre conexão.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import apoio_protesto_lg06 as APOIO  # noqa: E402
import boleto_api as BAPI  # noqa: E402
import cobranca_parcela as CP  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_aviso as AV  # noqa: E402
import protesto_boleto as BOL  # noqa: E402
import protesto_boleto_parcela as PBP  # noqa: E402
import protesto_integracoes as INTEG  # noqa: E402
from bd_nativo import banco  # noqa: E402
from despesas_inter import Resposta  # noqa: E402

HOJE = "2026-10-19"
SELLER = "seller-exemplo-0001"
CAMPOS = {"email": "teste@site-exemplo.invalid", "senha": "x" * 8, "seller_id": SELLER}
PRODUCAO = {"modo": "PRODUCAO", "ambiente": "PRODUCAO", "provedor": "PARCELA",
            "tarifa_centavos": 0}
HOMOLOGACAO = {**PRODUCAO, "modo": "HOMOLOGACAO", "ambiente": "HOMOLOGACAO"}


class ParcelaDeMentira:
    """A API de boletos da Parcela, em memória. Só os caminhos que o protesto usa.

    `taxa` é o que a Parcela soma por cima na linha digitável; `em_reais`
    simula a Parcela lendo o `value` como real (a linha volta cem vezes maior).
    """

    def __init__(self, *, sem_linha: bool = False, com_metadata: bool = True,
                 taxa: int = 0, em_reais: bool = False):
        self.boletos: dict[str, dict] = {}
        self.vendas: dict[str, dict] = {}
        self.chamadas: list[tuple[str, str]] = []
        self.sem_linha = sem_linha
        self.com_metadata = com_metadata
        self.taxa = taxa
        self.em_reais = em_reais
        self.seq = 0

    @staticmethod
    def linha(valor: int) -> str:
        return "0019" + "0" * 33 + f"{int(valor):010d}"

    def _publico(self, b: dict) -> dict:
        fora = {k: v for k, v in b.items() if k != "corpo"}
        if not self.com_metadata:
            fora.pop("metadata", None)
        return fora

    def __call__(self, metodo, url, *, json_corpo=None, cabecalhos=None):
        base = next((b for b in CP.ENDERECOS.values() if url.startswith(b)), None)
        assert base, f"endereço fora da Parcela: {url}"
        caminho = url[len(base):]
        self.chamadas.append((metodo, caminho))
        if caminho == CP.CAMINHO_DO_TOKEN:
            return Resposta(200, {"id_token": "jwt-de-teste"}, "application/json")
        if metodo == "POST" and caminho == f"/v2/billets/{SELLER}/hybrid":
            assert isinstance(json_corpo, list) and len(json_corpo) == 1
            corpo = json_corpo[0]
            self.seq += 1
            ident = f"bol-{self.seq}"
            valor = int(corpo["value"]) * (100 if self.em_reais else 1) + self.taxa
            b = {"id": ident, "status": "pending", "sale_id": None,
                 "url": f"https://boleto.site-exemplo.invalid/{ident}.pdf",
                 "barcode": "" if self.sem_linha else self.linha(valor),
                 "barcode_raw": "" if self.sem_linha else "0019" + "0" * 40,
                 "billet_data": {"qrcode_data": f"00020126PIX-{ident}",
                                 "nosso_numero": f"000{self.seq}"},
                 "metadata": corpo.get("metadata"), "corpo": corpo, "_valor": valor}
            self.boletos[ident] = b
            return Resposta(201, [self._publico(b)], "application/json")
        if metodo == "GET" and caminho.startswith("/v1/billets/"):
            b = self.boletos.get(caminho.split("/")[-1])
            if b is None:
                return Resposta(404, {}, "application/json")
            return Resposta(201, self._publico(b), "application/json")
        if metodo == "GET" and caminho.startswith(f"/v1/sellers/{SELLER}/billets?"):
            linhas = [self._publico(b) for b in self.boletos.values()]
            return Resposta(200, {"results": linhas, "has_more": False}, "application/json")
        if metodo == "GET" and caminho.startswith(f"/v1/sellers/{SELLER}/sales/"):
            v = self.vendas.get(caminho.split("/")[-1])
            return Resposta(200 if v else 404, v or {}, "application/json")
        if metodo == "POST" and caminho.endswith("/void"):
            b = self.boletos[caminho.split("/")[-2]]
            if b["status"] == "succeeded":
                return Resposta(400, {"message": "Boleto já pago."}, "application/json")
            b["status"] = "canceled"
            return Resposta(200, {}, "application/json")
        if metodo == "POST" and caminho.endswith("/pay"):
            self.pagar(caminho.split("/")[-2], forma="BILLET")
            return Resposta(201, {}, "application/json")
        raise AssertionError(f"caminho não previsto: {metodo} {caminho}")

    def pagar(self, ident, *, forma="PIX", valor=None, venda=None,
              quando="2026-10-20T13:00:00Z"):
        b = self.boletos[ident]
        venda = venda or f"venda-{ident}"
        b["status"] = "succeeded"
        b["sale_id"] = venda
        principal = int(b["corpo"]["value"])
        self.vendas[venda] = {"id": venda, "status": "SUCCEEDED", "form_payment": forma,
                              "amount": principal if valor is None else valor,
                              "original_amount": b["_valor"], "updated_at": quando}

    def so(self, ident):
        return self.boletos[ident]


@pytest.fixture()
def casa(cg_casa, monkeypatch):
    return {"db": cg_casa["db"],
            "relogio": APOIO.Relogio(cg_casa["db"], monkeypatch, HOJE)}


def _parcela(ambiente="PRODUCAO", **kw):
    falsa = ParcelaDeMentira(**kw)
    return PBP.BancoParcela(ambiente, transporte=falsa, campos=CAMPOS), falsa


def _ligar_no_aviso(db, valor="SIM"):
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO settings(key, value) VALUES (%s, %s)
               ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
            (BOL.CHAVE_DO_AVISO, valor))


def _boleto(db, boleto_id):
    return APOIO.um(db, "SELECT * FROM pt_boletos WHERE id=%s", (boleto_id,))


def _do_aviso(casa, aviso_id, transporte, cfg=PRODUCAO, emolumentos="45,10"):
    return BOL.emitir_com_o_aviso(casa["db"], aviso_id, emolumentos=emolumentos,
                                  hoje=HOJE, quem="escrevente",
                                  transporte=transporte, cfg=cfg)


def _pagamentos(casa, transporte, cfg=PRODUCAO, hoje="2026-10-21"):
    casa["relogio"].ir_para(hoje)
    return BOL.buscar_pagamentos(casa["db"], sv=APOIO.SV,
                                 data_extenso="vinte e um de outubro", hoje=hoje,
                                 quem="escrevente", transporte=transporte, cfg=cfg)


# ----------------------------------------------------------- a configuração


def test_a_parcela_e_provedor_do_boleto_e_tudo_nasce_desligado(casa):
    db = casa["db"]
    assert "PARCELA" in BAPI.PROVEDORES
    with db.connect() as con:
        assert INTEG.configuracao(con, INTEG.BOLETO)["modo"] == INTEG.DESLIGADO
        assert BOL.ligada_no_aviso(con) is False
    # a combinação vale nos dois modos: não é simulador, e o transporte existe
    assert INTEG.conferir_escolha(INTEG.BOLETO, "HOMOLOGACAO", "PARCELA") == (
        "HOMOLOGACAO", "PARCELA")
    assert INTEG.conferir_escolha(INTEG.BOLETO, "PRODUCAO", "PARCELA") == (
        "PRODUCAO", "PARCELA")
    # e a fábrica não fala com ninguém ao nascer
    t = BAPI.PROVEDORES["PARCELA"]["fabrica"]("HOMOLOGACAO", None)
    assert isinstance(t, PBP.BancoParcela) and t._cliente is None


def test_homologacao_vai_ao_sandbox(casa):
    t, falsa = _parcela("HOMOLOGACAO")
    assert t.cliente().base == CP.ENDERECOS["sandbox"]
    t2, _ = _parcela("PRODUCAO")
    assert t2.cliente().base == CP.ENDERECOS["producao"]


# ------------------------------------------------ a cobrança que vai com o aviso


def test_a_cobranca_do_aviso_e_um_boleto_hibrido_registrado_com_o_prazo_do_aviso(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    t, falsa = _parcela()
    r = _do_aviso(casa, aviso, t)
    assert r["acao"] == "CRIADA"
    b = _boleto(db, r["boleto_id"])
    with db.connect() as con:
        esperado = AV.prazo_de_pagamento(con, PT.titulo(con, tid),
                                         AV.ler(con, aviso)["emitido_em"])
    assert b["vencimento"] == esperado and b["aviso_id"] == aviso
    assert b["provedor"] == "PARCELA" and b["situacao"] == BOL.EMITIDO
    assert b["valor_centavos"] == 131045 + 4510
    # O BOLETO JÁ SAI REGISTRADO: linha digitável e Pix no mesmo documento
    assert b["nosso_numero"] == "bol-1"
    assert PBP.valor_da_linha(b["linha_digitavel"]) == 135555
    assert b["pix_copia_e_cola"] == "00020126PIX-bol-1"
    assert b["link_pagamento"].endswith("bol-1.pdf")
    # UM POST SÓ, um boleto só, no CPF/CNPJ do devedor, sem cartão
    posts = [c for c in falsa.chamadas if c[0] == "POST" and c[1].endswith("/hybrid")]
    assert len(posts) == 1 and not any("payment-links" in c[1] for c in falsa.chamadas)
    corpo = falsa.so("bol-1")["corpo"]
    assert "payment_methods" not in corpo
    assert corpo["value"] == 135555 and corpo["delivery_date"].startswith(esperado)
    assert len(corpo["social_security_number"]) in (11, 14)
    assert corpo["metadata"] == {"protesto": b["identificador"]}
    assert corpo["protocol"] == b["identificador"]


def test_a_taxa_que_a_parcela_soma_fica_com_o_devedor_e_vai_ao_papel(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    t, _ = _parcela(taxa=110)
    b = _boleto(db, _do_aviso(casa, aviso, t)["boleto_id"])
    assert json.loads(b["resposta"])["taxa_do_devedor_centavos"] == 110
    with db.transaction() as con:
        INTEG.gravar_configuracao(con, INTEG.BOLETO, modo="PRODUCAO", provedor="PARCELA")
    _ligar_no_aviso(db)
    with db.connect() as con:
        texto = "\n".join(BOL.bloco_de_pagamento(con, AV.ler(con, aviso))["linhas"])
    assert "R$ 1.356,65" in texto and "taxa do boleto R$ 1,10" in texto


def test_linha_com_valor_errado_baixa_o_boleto_e_recusa(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela(em_reais=True)
    with pytest.raises(BOL.BoletoDominioError, match="baixado na hora"):
        _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    assert falsa.so("bol-1")["status"] == "canceled"
    assert APOIO.um(db, "SELECT situacao FROM pt_boletos")["situacao"] == BOL.RECUSADO


def test_linha_que_nao_veio_na_emissao_se_busca_antes_de_imprimir(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela(sem_linha=True)
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    assert _boleto(db, r["boleto_id"])["linha_digitavel"] is None
    falsa.so("bol-1")["barcode"] = falsa.linha(135555)
    with db.connect() as con:
        assert BOL.boleto_sem_linha_do_titulo(con, tid) is None  # integração desligada
    assert BOL.completar_linha(db, r["boleto_id"], transporte=t, cfg=PRODUCAO)
    assert PBP.valor_da_linha(_boleto(db, r["boleto_id"])["linha_digitavel"]) == 135555
    assert not BOL.completar_linha(db, r["boleto_id"], transporte=t, cfg=PRODUCAO)


def test_emolumentos_em_branco_nao_saem(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    t, falsa = _parcela()
    with pytest.raises(BOL.BoletoDominioError, match="não se presume"):
        _do_aviso(casa, aviso, t, emolumentos="")
    assert falsa.chamadas == []


def test_aviso_reemitido_reaproveita_a_mesma_cobranca(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    primeiro = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    segundo_aviso = APOIO.aviso_emitido(db, tid)
    segundo = _do_aviso(casa, segundo_aviso, t)
    assert segundo["acao"] == "REAPROVEITADA"
    assert segundo["boleto_id"] == primeiro["boleto_id"]
    assert len(falsa.boletos) == 1
    assert _boleto(db, primeiro["boleto_id"])["aviso_id"] == segundo_aviso


def test_aviso_reemitido_com_outro_valor_baixa_o_boleto_antes(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    primeiro = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    segundo = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t, emolumentos="50,00")
    assert segundo["acao"] == "SUBSTITUIDA"
    assert segundo["cancelado_id"] == primeiro["boleto_id"]
    assert _boleto(db, primeiro["boleto_id"])["situacao"] == BOL.CANCELADO
    vivos = APOIO.ler(db, """SELECT id FROM pt_boletos WHERE titulo_id=%s
                              AND situacao IN ('PENDENTE','EMITIDO','SEM_RESPOSTA')""", (tid,))
    assert [v["id"] for v in vivos] == [segundo["boleto_id"]]
    assert [x["status"] for x in falsa.boletos.values()] == ["canceled", "pending"]


def test_cobranca_sem_resposta_trava_o_aviso_novo(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_boletos SET situacao='SEM_RESPOSTA' WHERE id=%s",
                            (r["boleto_id"],))
    with pytest.raises(BOL.BoletoDominioError, match="Conferir no banco"):
        _do_aviso(casa, APOIO.aviso_emitido(db, tid), t, emolumentos="50")
    assert len(falsa.boletos) == 1


def test_sem_resposta_se_confere_pelo_metadata_do_boleto(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, _ = _parcela()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_boletos SET situacao='SEM_RESPOSTA' WHERE id=%s",
                            (r["boleto_id"],))
    assert BOL.conferir_no_banco(db, r["boleto_id"], transporte=t,
                                 cfg=PRODUCAO)["situacao"] == BOL.EMITIDO


def test_sem_o_metadata_a_conferencia_nao_libera_outra(casa):
    t, falsa = _parcela(com_metadata=False)
    falsa.boletos["x"] = {"id": "x", "status": "pending", "corpo": {}}
    with pytest.raises(BAPI.BoletoError, match="portal"):
        t.consultar("PT1-1")


# -------------------------------------------------------------- a baixa


def test_boleto_pago_por_pix_da_baixa_uma_vez_e_cai_no_repasse(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("bol-1", forma="PIX")
    res = _pagamentos(casa, t)
    assert len(res["baixadas"]) == 1 and res["conferir"] == []
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s", (tid,))["situacao"] == "PAGO"
    b = _boleto(db, r["boleto_id"])
    ato = APOIO.um(db, "SELECT * FROM pt_atos WHERE id=%s", (b["ato_id"],))
    detalhe = json.loads(ato["detalhe_json"])
    assert detalhe["forma_pagamento"] == "BOLETO"
    assert "Parcela Express" in detalhe["forma_identificacao"]
    assert "por Pix" in detalhe["forma_identificacao"]
    assert detalhe["valor_pago_centavos"] == 131045
    assert detalhe["emolumentos_centavos"] == 4510
    # a segunda busca não paga de novo
    de_novo = _pagamentos(casa, t, hoje="2026-10-22")
    assert de_novo["baixadas"] == [] and de_novo["ja_vistas"] == 0
    assert APOIO.um(db, "SELECT count(*) AS n FROM pt_atos WHERE titulo_id=%s "
                        "AND tipo='PAGAMENTO'", (tid,))["n"] == 1
    # o repasse nasce do Livro de Pagamentos, como em todo pagamento
    import protesto_repasse as REP
    with db.connect() as con:
        pend = REP.pendentes(con, hoje="2026-10-22")
    assert any(int(p.get("titulo_id") or 0) == tid for p in pend)
    # e o caixa não ganha cobrança: o boleto do protesto não é `cb_cobrancas`
    assert APOIO.um(db, "SELECT count(*) AS n FROM cb_cobrancas")["n"] == 0


def test_a_mesma_venda_lida_de_novo_entra_uma_vez(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("bol-1", forma="BILLET")
    _pagamentos(casa, t)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_boletos SET situacao='EMITIDO'")
    segunda = _pagamentos(casa, t, hoje="2026-10-22")
    assert segunda["baixadas"] == [] and segunda["ja_vistas"] == 1


def test_boleto_do_caixa_na_mesma_conta_nao_e_consultado(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.boletos["do-caixa"] = {"id": "do-caixa", "status": "succeeded",
                                 "sale_id": "venda-caixa", "corpo": {"value": 999},
                                 "_valor": 999}
    falsa.vendas["venda-caixa"] = {"id": "venda-caixa", "status": "SUCCEEDED",
                                   "form_payment": "PIX", "amount": 999,
                                   "updated_at": "2026-10-20T10:00:00Z"}
    res = _pagamentos(casa, t)
    assert res["vistas"] == 0 and res["conferir"] == []
    assert ("GET", "/v1/billets/do-caixa") not in falsa.chamadas


def test_valor_pago_diferente_vira_conferir(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("bol-1", valor=100)
    res = _pagamentos(casa, t)
    assert res["baixadas"] == [] and len(res["conferir"]) == 1
    assert _boleto(db, r["boleto_id"])["situacao"] == BOL.CONFERIR
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s", (tid,))["situacao"] != "PAGO"


def test_boleto_pago_sem_a_venda_vira_aviso_e_nao_baixa(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.so("bol-1")["status"] = "succeeded"
    res = _pagamentos(casa, t)
    assert res["baixadas"] == [] and len(res["avisos"]) == 1


def test_na_homologacao_o_titulo_nao_muda(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela("HOMOLOGACAO")
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t, cfg=HOMOLOGACAO)
    falsa.pagar("bol-1")
    res = _pagamentos(casa, t, cfg=HOMOLOGACAO)
    assert len(res["baixadas"]) == 1 and res["baixadas"][0]["situacao"] == BOL.ENSAIO
    assert _boleto(db, r["boleto_id"])["situacao"] == BOL.PAGO
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s", (tid,))["situacao"] == "APONTADO"


# ---------------------------------------------- o que não pode mais ser pago


def test_desistido_e_sustado_tem_o_boleto_baixado(casa):
    db = casa["db"]
    desistido = APOIO.titulo_apontado(db, numero="PR7/1")
    sustado = APOIO.titulo_apontado(db, numero="PR7/2", protocolo="2610190002")
    vivo = APOIO.titulo_apontado(db, numero="PR7/3", protocolo="2610190003")
    t, falsa = _parcela()
    for tid in (desistido, sustado, vivo):
        _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    with db.transaction() as con:
        PT.lancar_desistencia(con, desistido, motivo="pedido do apresentante",
                              agora=db.now(), usuario="escrevente")
        PT.lancar_sustacao(con, sustado, juizo="1ª Vara de Cidade Exemplo",
                           processo="0000001-00.2026.8.10.0001", agora=db.now(),
                           usuario="escrevente")
    with db.connect() as con:
        lista = BOL.a_cancelar(con, ambiente="PRODUCAO")
    assert sorted(int(x["titulo_id"]) for x in lista) == sorted([desistido, sustado])
    r = BOL.cancelar_os_encerrados(db, quem="escrevente", transporte=t, cfg=PRODUCAO)
    assert len(r["cancelados"]) == 2 and r["recusados"] == []
    estados = [b["status"] for b in falsa.boletos.values()]
    assert sorted(estados) == ["canceled", "canceled", "pending"]


def test_boleto_ja_pago_nao_se_baixa_e_fica_na_lista(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("bol-1")
    with db.transaction() as con:
        PT.lancar_desistencia(con, tid, motivo="pedido do apresentante",
                              agora=db.now(), usuario="escrevente")
    r = BOL.cancelar_os_encerrados(db, quem="escrevente", transporte=t, cfg=PRODUCAO)
    assert r["cancelados"] == [] and len(r["recusados"]) == 1
    # o pagamento chega pela busca e vira CONFERIR — o dinheiro entrou
    res = _pagamentos(casa, t)
    assert len(res["conferir"]) == 1


# ------------------------------------------------------ o que vai no papel


def test_o_papel_so_leva_a_cobranca_com_a_chave_ligada(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    t, _ = _parcela()
    _do_aviso(casa, aviso, t)
    with db.transaction() as con:
        INTEG.gravar_configuracao(con, INTEG.BOLETO, modo="PRODUCAO", provedor="PARCELA")
    with db.connect() as con:
        assert BOL.bloco_de_pagamento(con, AV.ler(con, aviso)) is None
    _ligar_no_aviso(db)
    with db.connect() as con:
        bloco = BOL.bloco_de_pagamento(con, AV.ler(con, aviso))
    assert bloco and bloco["qr"] == "00020126PIX-bol-1"
    texto = "\n".join(bloco["linhas"])
    assert "R$ 1.355,55" in texto and "Linha digitável: 0019" in texto
    assert "cartão" not in texto and ".pdf" not in texto
    assert "NÃO PAGUE" not in texto


def test_o_papel_da_homologacao_diz_que_nao_se_paga(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    t, _ = _parcela("HOMOLOGACAO")
    _do_aviso(casa, aviso, t, cfg=HOMOLOGACAO)
    with db.transaction() as con:
        INTEG.gravar_configuracao(con, INTEG.BOLETO, modo="HOMOLOGACAO", provedor="PARCELA")
    _ligar_no_aviso(db)
    with db.connect() as con:
        bloco = BOL.bloco_de_pagamento(con, AV.ler(con, aviso))
    assert bloco["homologacao"] and "NÃO PAGUE" in bloco["linhas"][0]
    # com o Pix na mão, o QR é o do Pix — paga-se em qualquer banco
    assert bloco["qr"] == "00020126PIX-bol-1"


# ---------------------------------------------------------------- as telas


def _token(html: str) -> str:
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def tela(cg_casa_logada, monkeypatch):
    db = cg_casa_logada["db"]
    APOIO.Relogio(db, monkeypatch, HOJE)
    db.set_settings({"modulo_protesto_ligado": "1",
                     "serventia_horario": "segunda a sexta, das 8h às 17h"})
    falsa = ParcelaDeMentira()
    monkeypatch.setattr(PBP, "fabrica", lambda ambiente, pasta: PBP.BancoParcela(
        ambiente, pasta, transporte=falsa, campos=CAMPOS))
    with db.transaction() as con:
        INTEG.gravar_configuracao(con, INTEG.BOLETO, modo="HOMOLOGACAO",
                                  provedor="PARCELA")
    return {"db": db, "c": cg_casa_logada["c"], "falsa": falsa}


def _emitir_aviso_pela_ficha(tela, tid, **campos):
    c = tela["c"]
    html = c.get(f"/protesto/{tid}").get_data(as_text=True)
    return c.post(f"/protesto/{tid}/aviso",
                  data={"csrf_token": _token(html), **campos},
                  follow_redirects=True), html


def test_desligada_no_aviso_a_ficha_nao_pede_emolumentos_e_nada_sai(tela):
    tid = APOIO.titulo_apontado(tela["db"])
    resp, html = _emitir_aviso_pela_ficha(tela, tid, emolumentos_cobranca="45,10")
    assert resp.status_code == 200
    assert "emolumentos_cobranca" not in html
    assert tela["falsa"].chamadas == []
    assert APOIO.ler(tela["db"], "SELECT id FROM pt_boletos") == []


def test_ligada_o_aviso_sai_com_a_cobranca_e_o_papel_com_o_qr(tela):
    import io
    import zipfile
    db = tela["db"]
    _ligar_no_aviso(db)
    tid = APOIO.titulo_apontado(db)
    resp, html = _emitir_aviso_pela_ficha(tela, tid, emolumentos_cobranca="45,10")
    assert "emolumentos_cobranca" in html
    texto = resp.get_data(as_text=True)
    assert "Cobrança do aviso criada" in texto and "HOMOLOGAÇÃO" in texto
    b = APOIO.um(db, "SELECT * FROM pt_boletos ORDER BY id DESC LIMIT 1")
    assert b["provedor"] == "PARCELA" and b["aviso_id"]
    # o papel: o bloco de pagamento e as DUAS imagens de QR
    odt = tela["c"].get(f"/protesto/avisos/{b['aviso_id']}.odt?formato=odt")
    assert odt.status_code == 200
    with zipfile.ZipFile(io.BytesIO(odt.data)) as z:
        nomes = z.namelist()
        conteudo = z.read("content.xml").decode("utf-8")
    assert "Pictures/qr-de-pagar.png" in nomes and "Pictures/qr-do-papel.png" in nomes
    assert "NÃO PAGUE" in conteudo and "Linha digitável" in conteudo


def test_ligada_sem_emolumentos_o_aviso_sai_sem_cobranca_e_diz(tela):
    db = tela["db"]
    _ligar_no_aviso(db)
    tid = APOIO.titulo_apontado(db)
    resp, _ = _emitir_aviso_pela_ficha(tela, tid)
    assert "SEM a cobrança" in resp.get_data(as_text=True)
    assert APOIO.ler(db, "SELECT id FROM pt_avisos WHERE titulo_id=%s", (tid,))
    assert tela["falsa"].chamadas == []

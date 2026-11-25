# -*- coding: utf-8 -*-
"""A cobrança da intimação pela Parcela Express (PR007): um link só, com o
prazo do aviso, uma viva por título, baixa pela venda paga e cancelamento do
que não vale mais.

A PARCELA AQUI É DE MENTIRA, E SEM REDE: `ParcelaDeMentira` responde como a
API dos links (`cobranca_parcela`, cabeçalho) e guarda o estado em memória.
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
    """A API de links da Parcela, em memória. Só os caminhos que o protesto usa."""

    def __init__(self, *, com_linha: bool = False, com_titulo: bool = True):
        self.links: dict[str, dict] = {}
        self.chamadas: list[tuple[str, str]] = []
        self.com_linha = com_linha
        self.com_titulo = com_titulo
        self.seq = 0

    def __call__(self, metodo, url, *, json_corpo=None, cabecalhos=None):
        base = next((b for b in CP.ENDERECOS.values() if url.startswith(b)), None)
        assert base, f"endereço fora da Parcela: {url}"
        caminho = url[len(base):]
        self.chamadas.append((metodo, caminho))
        if caminho == CP.CAMINHO_DO_TOKEN:
            return Resposta(200, {"id_token": "jwt-de-teste"}, "application/json")
        if metodo == "POST" and caminho == "/v1/payment-links":
            self.seq += 1
            ident = f"link-{self.seq}"
            link = {"id": ident, "token": f"tok-{self.seq}", "status": "ACTIVE",
                    "url": f"https://pagar.site-exemplo.invalid/{ident}",
                    "amount": json_corpo["amount"], "seller": {"id": SELLER},
                    "expires_in": json_corpo["expires_in"], "corpo": json_corpo}
            if self.com_titulo:
                link["link_title"] = json_corpo["link_title"]
            if self.com_linha:
                link["billet_data"] = {"barcode": "00190000090000000000000000000000000000000000000"}
                link["pix"] = {"qrcode_data": "00020126PIX-DE-TESTE"}
            self.links[ident] = link
            return Resposta(201, {k: link[k] for k in ("id", "token", "url", "status")},
                            "application/json")
        if metodo == "GET" and "/payment-links?" in caminho:
            linhas = [{k: v for k, v in x.items() if k != "corpo"} for x in self.links.values()]
            return Resposta(200, {"results": linhas, "has_more": False}, "application/json")
        if metodo == "POST" and caminho.endswith("/cancel"):
            ident = caminho.split("/")[-2]
            self.links[ident]["status"] = "CANCELED"
            return Resposta(200, {}, "application/json")
        raise AssertionError(f"caminho não previsto: {metodo} {caminho}")

    def pagar(self, ident, *, forma="PIX", valor=None, venda="venda-1",
              quando="2026-10-20T13:00:00Z"):
        link = self.links[ident]
        link["status"] = "PAID"
        link["sale"] = {"id": venda, "status": "SUCCEEDED", "form_payment": forma,
                        "amount": link["amount"] if valor is None else valor,
                        "updated_at": quando}


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


def test_a_cobranca_do_aviso_e_um_link_so_com_o_prazo_do_aviso(casa):
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
    assert b["link_pagamento"].startswith("https://pagar.")
    # UM POST SÓ, com as três formas no mesmo link
    posts = [c for c in falsa.chamadas if c == ("POST", "/v1/payment-links")]
    assert len(posts) == 1
    corpo = next(iter(falsa.links.values()))["corpo"]
    assert corpo["payment_methods"] == ["pix", "billet", "card"]
    assert corpo["amount"] == 135555 and corpo["expires_in"].startswith(esperado)
    assert corpo["link_title"] == f"Protesto {b['identificador']}"


def test_linha_e_pix_entram_quando_a_consulta_os_traz(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    t, _ = _parcela(com_linha=True)
    b = _boleto(db, _do_aviso(casa, aviso, t)["boleto_id"])
    assert b["linha_digitavel"].startswith("0019")
    assert b["pix_copia_e_cola"] == "00020126PIX-DE-TESTE"


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
    assert len(falsa.links) == 1
    assert _boleto(db, primeiro["boleto_id"])["aviso_id"] == segundo_aviso


def test_aviso_reemitido_com_outro_valor_cancela_o_link_antes(casa):
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
    assert [x["status"] for x in falsa.links.values()] == ["CANCELED", "ACTIVE"]


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
    assert len(falsa.links) == 1


def test_sem_resposta_se_confere_pelo_titulo_do_link(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, _ = _parcela()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_boletos SET situacao='SEM_RESPOSTA' WHERE id=%s",
                            (r["boleto_id"],))
    assert BOL.conferir_no_banco(db, r["boleto_id"], transporte=t,
                                 cfg=PRODUCAO)["situacao"] == BOL.EMITIDO


def test_sem_o_titulo_do_link_a_conferencia_nao_libera_outra(casa):
    t, falsa = _parcela(com_titulo=False)
    falsa.links["x"] = {"id": "x", "status": "ACTIVE", "seller": {"id": SELLER}}
    with pytest.raises(BAPI.BoletoError, match="portal"):
        t.consultar("PT1-1")


# -------------------------------------------------------------- a baixa


def test_link_pago_por_pix_da_baixa_uma_vez_e_cai_no_repasse(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("link-1", forma="PIX")
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
    # e o caixa não ganha cobrança: o link do protesto não é `cb_cobrancas`
    assert APOIO.um(db, "SELECT count(*) AS n FROM cb_cobrancas")["n"] == 0


def test_a_mesma_venda_lida_de_novo_entra_uma_vez(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("link-1", forma="BILLET")
    _pagamentos(casa, t)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_boletos SET situacao='EMITIDO'")
    segunda = _pagamentos(casa, t, hoje="2026-10-22")
    assert segunda["baixadas"] == [] and segunda["ja_vistas"] == 1


def test_link_do_caixa_na_mesma_conta_nao_vira_pendencia(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.links["do-caixa"] = {"id": "do-caixa", "status": "PAID", "amount": 999,
                               "seller": {"id": SELLER},
                               "sale": {"id": "venda-caixa", "status": "SUCCEEDED",
                                        "form_payment": "PIX", "amount": 999,
                                        "updated_at": "2026-10-20T10:00:00Z"}}
    res = _pagamentos(casa, t)
    assert res["vistas"] == 0 and res["conferir"] == []


def test_valor_pago_diferente_vira_conferir(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("link-1", valor=100)
    res = _pagamentos(casa, t)
    assert res["baixadas"] == [] and len(res["conferir"]) == 1
    assert _boleto(db, r["boleto_id"])["situacao"] == BOL.CONFERIR
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s", (tid,))["situacao"] != "PAGO"


def test_link_pago_sem_dados_da_venda_vira_aviso_e_nao_baixa(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.links["link-1"]["status"] = "PAID"
    res = _pagamentos(casa, t)
    assert res["baixadas"] == [] and len(res["avisos"]) == 1


def test_na_homologacao_o_titulo_nao_muda(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela("HOMOLOGACAO")
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t, cfg=HOMOLOGACAO)
    falsa.pagar("link-1")
    res = _pagamentos(casa, t, cfg=HOMOLOGACAO)
    assert len(res["baixadas"]) == 1 and res["baixadas"][0]["situacao"] == BOL.ENSAIO
    assert _boleto(db, r["boleto_id"])["situacao"] == BOL.PAGO
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s", (tid,))["situacao"] == "APONTADO"


# ---------------------------------------------- o que não pode mais ser pago


def test_desistido_e_sustado_tem_o_link_cancelado(casa):
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
    estados = {lk["corpo"]["link_title"]: lk["status"] for lk in falsa.links.values()}
    assert sorted(estados.values()) == ["ACTIVE", "CANCELED", "CANCELED"]


def test_link_ja_pago_nao_se_cancela_e_fica_na_lista(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falsa = _parcela()
    _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falsa.pagar("link-1")
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
    assert bloco and bloco["qr"].startswith("https://pagar.")
    texto = "\n".join(bloco["linhas"])
    assert "R$ 1.355,55" in texto and "Pix, boleto ou cartão" in texto
    assert "NÃO PAGUE" not in texto


def test_o_papel_da_homologacao_diz_que_nao_se_paga(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    t, _ = _parcela("HOMOLOGACAO", com_linha=True)
    _do_aviso(casa, aviso, t, cfg=HOMOLOGACAO)
    with db.transaction() as con:
        INTEG.gravar_configuracao(con, INTEG.BOLETO, modo="HOMOLOGACAO", provedor="PARCELA")
    _ligar_no_aviso(db)
    with db.connect() as con:
        bloco = BOL.bloco_de_pagamento(con, AV.ler(con, aviso))
    assert bloco["homologacao"] and "NÃO PAGUE" in bloco["linhas"][0]
    # com o Pix na mão, o QR é o do Pix — paga-se em qualquer banco
    assert bloco["qr"] == "00020126PIX-DE-TESTE"


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
    assert "NÃO PAGUE" in conteudo and "pagar.site-exemplo.invalid" in conteudo


def test_ligada_sem_emolumentos_o_aviso_sai_sem_cobranca_e_diz(tela):
    db = tela["db"]
    _ligar_no_aviso(db)
    tid = APOIO.titulo_apontado(db)
    resp, _ = _emitir_aviso_pela_ficha(tela, tid)
    assert "SEM a cobrança" in resp.get_data(as_text=True)
    assert APOIO.ler(db, "SELECT id FROM pt_avisos WHERE titulo_id=%s", (tid,))
    assert tela["falsa"].chamadas == []

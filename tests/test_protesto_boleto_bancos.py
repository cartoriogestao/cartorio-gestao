# -*- coding: utf-8 -*-
"""O boleto do devedor pelo Banco Inter e pela Unicred (PR007, 25/11/2026), e a
cobrança de teste do Gestor.

OS BANCOS AQUI SÃO DE MENTIRA, E SEM REDE: `AdaptadorDeMentira` cumpre o
contrato de `cobranca_banco` (emitir, consultar, procurar, cancelar) em
memória, como `cobranca_inter` e `cobranca_unicred` o cumprem com o banco.
Nenhum teste fala com sandbox nem com produção de banco nenhum.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import apoio_protesto_lg06 as APOIO  # noqa: E402
import boleto_api as BAPI  # noqa: E402
import cobranca as CB  # noqa: E402
import protesto_boleto as BOL  # noqa: E402
import protesto_boleto_banco as PBB  # noqa: E402
import protesto_integracoes as INTEG  # noqa: E402
from cobranca_banco import Indisponivel, Recusa  # noqa: E402
from test_protesto_boleto_parcela import ParcelaDeMentira, _parcela, _token, tela  # noqa: E402,F401

HOJE = "2026-10-19"
INTER = {"modo": "PRODUCAO", "ambiente": "PRODUCAO", "provedor": "INTER",
         "tarifa_centavos": 0}
UNICRED = {**INTER, "provedor": "UNICRED"}
LINHA = "0779" + "0" * 33 + f"{135555:010d}"


class AdaptadorDeMentira:
    """Um banco do caixa em memória. `atraso` = consultas antes de a linha vir."""

    def __init__(self, banco=CB.INTER, *, atraso=0, procura=True):
        self.banco = banco
        self.ambiente = "producao"
        self.atraso = atraso
        self.procura = procura
        self.titulos: dict[str, dict] = {}
        self.cancelados: list[tuple[str, str]] = []
        self.seq = 0

    def emitir(self, c):
        self.seq += 1
        ident = f"sol-{self.seq}"
        self.titulos[ident] = {"c": dict(c), "consultas": 0, "situacao": CB.ABERTA}
        return ident

    def consultar(self, c):
        t = self.titulos.get(c["banco_id"])
        if t is None:
            return None
        t["consultas"] += 1
        if t["consultas"] <= self.atraso:
            return {"banco_status": "EM_PROCESSAMENTO", "situacao": CB.EMITINDO}
        fora = {"banco_status": "A_RECEBER", "situacao": t["situacao"],
                "linha_digitavel": LINHA, "codigo_barras": "0779" + "0" * 40,
                "pix_copia_e_cola": f"00020126PIX-{c['banco_id']}", "nosso_numero": "123"}
        fora.update(t.get("pago") or {})
        return fora

    def procurar(self, c, *, data_inicial, data_final):
        if not self.procura:
            return None
        for ident, t in self.titulos.items():
            if t["c"]["seu_numero"] == c["seu_numero"]:
                return ident
        return None

    def cancelar(self, c, motivo):
        t = self.titulos[c["banco_id"]]
        if t["situacao"] == CB.RECEBIDA:
            raise Recusa("Cobrança já recebida.")
        t["situacao"] = CB.CANCELADA
        self.cancelados.append((c["banco_id"], motivo))
        return ""

    def pagar(self, ident, *, valor=135555, quando="2026-10-20", forma="PIX"):
        t = self.titulos[ident]
        t["situacao"] = CB.RECEBIDA
        t["pago"] = {"situacao": CB.RECEBIDA, "valor_recebido": valor,
                     "data_pagamento": quando, "forma_recebida": forma}

    def token(self):
        return "token-de-teste"


@pytest.fixture()
def casa(cg_casa, monkeypatch):
    return {"db": cg_casa["db"],
            "relogio": APOIO.Relogio(cg_casa["db"], monkeypatch, HOJE)}


def _banco(qual=CB.INTER, **kw):
    falso = AdaptadorDeMentira(qual, **kw)
    return PBB.BancoDaCobranca(qual, "PRODUCAO", cliente=falso,
                               dormir=lambda _s: None), falso


def _do_aviso(casa, aviso_id, transporte, cfg=INTER, emolumentos="45,10"):
    return BOL.emitir_com_o_aviso(casa["db"], aviso_id, emolumentos=emolumentos,
                                  hoje=HOJE, quem="escrevente",
                                  transporte=transporte, cfg=cfg)


def _boleto(db, boleto_id):
    return APOIO.um(db, "SELECT * FROM pt_boletos WHERE id=%s", (boleto_id,))


def test_inter_e_unicred_sao_provedores_e_nascem_sem_falar_com_ninguem():
    for qual in ("INTER", "UNICRED"):
        assert INTEG.conferir_escolha(INTEG.BOLETO, "PRODUCAO", qual) == ("PRODUCAO", qual)
        t = BAPI.PROVEDORES[qual]["fabrica"]("HOMOLOGACAO", None)
        assert isinstance(t, PBB.BancoDaCobranca) and t._cliente is None
        assert t.banco == qual


def test_inter_emite_o_boleto_com_pix_e_espera_a_linha(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falso = _banco(atraso=1)
    b = _boleto(db, _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)["boleto_id"])
    assert b["provedor"] == "INTER" and b["situacao"] == BOL.EMITIDO
    assert b["nosso_numero"] == "sol-1" and b["linha_digitavel"] == LINHA
    assert b["pix_copia_e_cola"] == "00020126PIX-sol-1"
    c = falso.titulos["sol-1"]["c"]
    assert c["valor"] == 135555 and c["dias_apos_vencimento"] == 0
    assert len(c["seu_numero"]) <= CB.LIMITE_SEU_NUMERO
    assert c["pagador_documento"].isdigit()


def test_linha_que_demora_se_completa_antes_de_imprimir(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, _ = _banco(atraso=PBB.TENTATIVAS_DA_LINHA)
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    assert _boleto(db, r["boleto_id"])["linha_digitavel"] is None
    assert BOL.completar_linha(db, r["boleto_id"], transporte=t, cfg=INTER)
    assert _boleto(db, r["boleto_id"])["linha_digitavel"] == LINHA


def test_baixa_pela_consulta_um_a_um_e_uma_vez(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    t, falso = _banco()
    r = _do_aviso(casa, APOIO.aviso_emitido(db, tid), t)
    falso.pagar("sol-1", forma="PIX")
    casa["relogio"].ir_para("2026-10-21")
    res = BOL.buscar_pagamentos(db, sv=APOIO.SV, data_extenso="vinte e um de outubro",
                                hoje="2026-10-21", quem="escrevente", transporte=t,
                                cfg=INTER)
    assert len(res["baixadas"]) == 1 and res["conferir"] == []
    b = _boleto(db, r["boleto_id"])
    assert b["situacao"] == BOL.PAGO
    ato = APOIO.um(db, "SELECT detalhe_json FROM pt_atos WHERE id=%s", (b["ato_id"],))
    assert "Banco Inter" in ato["detalhe_json"] and "por Pix" in ato["detalhe_json"]
    de_novo = BOL.buscar_pagamentos(db, sv=APOIO.SV, data_extenso="vinte e dois",
                                    hoje="2026-10-22", quem="escrevente",
                                    transporte=t, cfg=INTER)
    assert de_novo["perguntou"] is False


def test_consulta_que_falha_vira_aviso_e_nao_derruba_a_busca(casa):
    t, falso = _banco()
    falso.consultar = lambda c: (_ for _ in ()).throw(Indisponivel("sem rede"))
    assert t.liquidacoes("2026-10-01", "2026-10-31", nossos=["sol-9"]) == []
    assert t.avisos and "sem rede" in t.avisos[0]


def test_cancelar_vai_com_o_motivo(casa):
    t, falso = _banco()
    t.registrar({"valor_centavos": 1000, "vencimento": "2026-10-25",
                 "identificador": "PT1-1", "pagador": APOIO_PAGADOR})
    t.cancelar("sol-1", "título desistido")
    assert falso.cancelados == [("sol-1", "título desistido")]


def test_inter_confere_o_sem_resposta_pelo_seu_numero(casa):
    t, _ = _banco()
    t.registrar({"valor_centavos": 1000, "vencimento": "2026-10-25",
                 "identificador": "PT1-1", "pagador": APOIO_PAGADOR})
    assert t.consultar("PT1-1")["nosso_numero"] == "sol-1"
    assert t.consultar("PT1-2") is None


def test_unicred_sem_busca_nao_diz_que_nao_tem(casa):
    t, _ = _banco(CB.UNICRED, procura=False)
    with pytest.raises(BAPI.BoletoError, match="internet banking"):
        t.consultar("PT1-1")


APOIO_PAGADOR = {"nome": "Devedor de Exemplo", "documento": APOIO.CNPJ_CREDOR,
                 "endereco": "Rua Exemplo, 1", "bairro": "Centro", "cep": "65000000",
                 "cidade": "Cidade Exemplo", "uf": "MA"}


# ------------------------------------------------------- a cobrança de teste

HOMOLOGACAO_PARCELA = {"modo": "HOMOLOGACAO", "ambiente": "HOMOLOGACAO",
                       "provedor": "PARCELA", "tarifa_centavos": 0}


def test_cobranca_de_teste_so_na_homologacao():
    t, falsa = _parcela("PRODUCAO")
    with pytest.raises(BOL.BoletoDominioError, match="homologação"):
        BOL.cobranca_de_teste(cfg={**HOMOLOGACAO_PARCELA, "ambiente": "PRODUCAO"},
                              transporte=t, pagador=APOIO_PAGADOR, hoje=HOJE)
    assert falsa.chamadas == []


def test_cobranca_de_teste_emite_le_e_baixa_sem_tocar_no_banco_da_casa(casa):
    t, falsa = _parcela("HOMOLOGACAO", taxa=110)
    r = BOL.cobranca_de_teste(cfg=HOMOLOGACAO_PARCELA, transporte=t,
                              pagador=APOIO_PAGADOR, hoje=HOJE)
    assert r["registrado"] and r["tem_pix"] and r["baixado"] and not r["pago"]
    assert r["valor_da_linha_centavos"] == BOL.VALOR_DO_TESTE + 110
    assert r["taxa_do_devedor_centavos"] == 110
    assert falsa.so("bol-1")["status"] == "canceled"
    assert APOIO.ler(casa["db"], "SELECT id FROM pt_boletos") == []


def test_cobranca_de_teste_paga_no_sandbox_e_mostra_o_que_entra(casa):
    t, falsa = _parcela("HOMOLOGACAO")
    r = BOL.cobranca_de_teste(cfg=HOMOLOGACAO_PARCELA, transporte=t,
                              pagador=APOIO_PAGADOR, hoje=HOJE, pagar=True)
    assert r["pago"] and not r["baixado"]
    assert ("POST", "/v1/billets/bol-1/pay") in falsa.chamadas
    assert [x["valor_pago_centavos"] for x in r["liquidacoes"]] == [BOL.VALOR_DO_TESTE]


def test_a_tela_do_gestor_roda_a_cobranca_de_teste_e_audita(tela):
    c = tela["c"]
    html = c.get("/administrativo/gestor/protesto-integracoes").get_data(as_text=True)
    # sem o cadastro da serventia, a tela diz onde completar, e nada sai
    sem = c.post("/administrativo/gestor/protesto-integracoes/cobranca-de-teste",
                 data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "cadastro dela está incompleto" in sem.get_data(as_text=True)
    assert tela["falsa"].chamadas == []
    tela["db"].set_settings({"serventia_cnpj": APOIO.CNPJ_CREDOR,
                             "serventia_endereco": "Rua Exemplo, 1",
                             "serventia_cep": "65000000", "ri_cidade": "Cidade Exemplo",
                             "ri_uf": "MA"})
    assert "Cobrança de teste" in html and "Qual provedor sai mais em conta" in html
    resp = c.post("/administrativo/gestor/protesto-integracoes/cobranca-de-teste",
                  data={"csrf_token": _token(html)}, follow_redirects=True)
    texto = resp.get_data(as_text=True)
    assert "boleto registrado, com linha digitável" in texto and "baixado no sandbox" in texto
    assert tela["falsa"].so("bol-1")["status"] == "canceled"
    assert APOIO.ler(tela["db"], "SELECT id FROM pt_boletos") == []
    assert APOIO.um(tela["db"], "SELECT count(*) AS n FROM audit_logs "
                                "WHERE action='PROTESTO_BOLETO_TESTE'")["n"] == 1

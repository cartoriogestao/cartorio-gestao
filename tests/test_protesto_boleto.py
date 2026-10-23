# -*- coding: utf-8 -*-
"""O boleto do devedor (LG06): emitir com o prazo-limite como vencimento,
cancelar, e dar baixa SÓ no pagamento que bate por inteiro.

O banco aqui é o serviço falso (homologação) ou o dublê da produção — nunca a
rede. Ver `apoio_protesto_lg06`.
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
import protesto as PT  # noqa: E402
import protesto_boleto as BOL  # noqa: E402
import protesto_integracoes as INTEG  # noqa: E402

HOJE = "2026-10-19"


@pytest.fixture()
def casa(cg_casa, tmp_path, monkeypatch):
    return {"db": cg_casa["db"], "pasta": tmp_path / "sim",
            "relogio": APOIO.Relogio(cg_casa["db"], monkeypatch, HOJE)}


def _banco(casa, cfg):
    if cfg["ambiente"] == "PRODUCAO":
        return APOIO.BancoDeTeste(pasta=casa["pasta"])
    return BAPI.BancoFalso(pasta=casa["pasta"])


def _emitir(casa, tid, *, cfg=None, transporte=None, emolumentos="45,10"):
    cfg = cfg or APOIO.PRODUCAO
    transporte = transporte or _banco(casa, cfg)
    r = BOL.emitir(casa["db"], tid, emolumentos=emolumentos, hoje=HOJE,
                   quem="escrevente", transporte=transporte, cfg=cfg)
    return r, transporte


def _pagamentos(casa, transporte, cfg=None, hoje="2026-10-21"):
    casa["relogio"].ir_para(hoje)
    return BOL.buscar_pagamentos(casa["db"], sv=APOIO.SV,
                                 data_extenso="vinte e um de outubro",
                                 hoje=hoje, quem="escrevente",
                                 transporte=transporte, cfg=cfg or APOIO.PRODUCAO)


def _situacao(db, tid):
    return APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s",
                    (tid,))["situacao"]


# -------------------------------------------------------------------- emitir


def test_a_integracao_do_banco_nasce_desligada(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    with pytest.raises(INTEG.IntegracaoDesligada):
        BOL.emitir(db, tid, emolumentos="10", hoje=HOJE, quem="escrevente")
    assert APOIO.ler(db, "SELECT id FROM pt_boletos ORDER BY id") == []


def test_o_vencimento_e_o_prazo_limite_e_a_composicao_soma(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    cfg = {**APOIO.PRODUCAO, "tarifa_centavos": 350}
    r, _ = _emitir(casa, tid, cfg=cfg)
    b = APOIO.um(db, "SELECT * FROM pt_boletos WHERE id=%s", (r["boleto_id"],))
    assert b["situacao"] == BOL.EMITIDO
    assert b["vencimento"] == APOIO.prazo(db, tid)          # CN-MA art. 925, § 4º
    assert b["valor_titulo_centavos"] == 131045             # o saldo
    assert b["emolumentos_centavos"] == 4510
    assert b["tarifa_centavos"] == 350
    assert b["valor_centavos"] == 131045 + 4510 + 350
    assert b["nosso_numero"] and json.loads(b["pagador_json"])["documento"] == APOIO.CPF


def test_emolumentos_em_branco_nao_se_presumem(casa):
    tid = APOIO.titulo_apontado(casa["db"])
    with pytest.raises(BOL.BoletoDominioError) as e:
        _emitir(casa, tid, emolumentos="")
    assert "não se presume" in str(e.value)


def test_zero_digitado_vale(casa):
    tid = APOIO.titulo_apontado(casa["db"])
    r, _ = _emitir(casa, tid, emolumentos="0")
    assert r["emolumentos_centavos"] == 0


def test_dois_boletos_vivos_do_mesmo_titulo_nao(casa):
    tid = APOIO.titulo_apontado(casa["db"])
    r, banco_ = _emitir(casa, tid)
    with pytest.raises(BOL.BoletoDominioError) as e:
        _emitir(casa, tid, transporte=banco_)
    assert "já tem boleto em aberto" in str(e.value)
    BOL.cancelar(casa["db"], r["boleto_id"], motivo="pago no balcão",
                 transporte=banco_, cfg=APOIO.PRODUCAO)
    novo, _ = _emitir(casa, tid, transporte=banco_)
    assert novo["boleto_id"] != r["boleto_id"]


def test_titulo_sustado_nao_ganha_boleto(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    with db.transaction() as con:
        PT.lancar_sustacao(con, tid, juizo="1ª Vara Exemplo",
                           processo="0000001-00.2026.8.10.0001", agora=db.now())
    with pytest.raises(BOL.BoletoDominioError) as e:
        _emitir(casa, tid)
    assert "sustado" in str(e.value)


def test_prazo_limite_que_ja_passou_nao_ganha_boleto(casa):
    tid = APOIO.titulo_apontado(casa["db"], protocolo="2609010001")
    with pytest.raises(BOL.BoletoDominioError) as e:
        _emitir(casa, tid)
    assert "já passou" in str(e.value)


def test_devedor_sem_cpf_nao_ganha_boleto_registrado(casa):
    # A CRA não manda devedor sem documento, mas o acervo do E-Ofício tem.
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    with db.transaction() as con:
        from bd_nativo import banco
        banco(con).escrever("UPDATE pt_devedores SET documento_numero=NULL "
                            "WHERE titulo_id=%s", (tid,))
    with pytest.raises(BOL.BoletoDominioError) as e:
        _emitir(casa, tid)
    assert "CPF ou CNPJ" in str(e.value)


def test_recusa_do_banco_libera_o_titulo_e_a_resposta_perdida_nao(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)

    class Recusa(APOIO.BancoDeTeste):
        def registrar(self, pedido):
            raise BAPI.BoletoRecusado("convênio inativo")

    class Caiu(APOIO.BancoDeTeste):
        def registrar(self, pedido):
            super().registrar(pedido)           # o banco registrou...
            raise BAPI.BoletoError("a conexão caiu")   # ...e a resposta se perdeu

    with pytest.raises(BOL.BoletoDominioError):
        _emitir(casa, tid, transporte=Recusa(pasta=casa["pasta"]))
    assert APOIO.um(db, "SELECT situacao FROM pt_boletos")["situacao"] == BOL.RECUSADO

    caiu = Caiu(pasta=casa["pasta"])
    with pytest.raises(BOL.BoletoDominioError) as e:
        _emitir(casa, tid, transporte=caiu)
    assert "Conferir no banco" in str(e.value)
    sem = APOIO.um(db, "SELECT * FROM pt_boletos WHERE situacao='SEM_RESPOSTA'")
    # SEM RESPOSTA É VIVO: o banco pode ter, e outro boleto seria cobrança dobrada.
    with pytest.raises(BOL.BoletoDominioError):
        _emitir(casa, tid, transporte=caiu)
    r = BOL.conferir_no_banco(db, sem["id"], transporte=caiu, cfg=APOIO.PRODUCAO)
    assert r["situacao"] == BOL.EMITIDO
    assert APOIO.um(db, "SELECT nosso_numero FROM pt_boletos WHERE id=%s",
                    (sem["id"],))["nosso_numero"]


def test_o_boleto_da_homologacao_nao_se_paga(casa):
    tid = APOIO.titulo_apontado(casa["db"])
    r, _ = _emitir(casa, tid, cfg=APOIO.HOMOLOGACAO)
    b = APOIO.um(casa["db"], "SELECT * FROM pt_boletos WHERE id=%s", (r["boleto_id"],))
    assert "NAO PAGAR" in b["linha_digitavel"]
    assert "NAO-PAGAR" in b["pix_copia_e_cola"]
    assert not any(c.isdigit() for c in b["linha_digitavel"].split()[0])


# ------------------------------------------------------------------ a baixa


def test_pagamento_que_bate_da_baixa_com_lugar_no_livro(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    r, banco_ = _emitir(casa, tid)
    banco_.simular_pagamento(r["nosso_numero"], pago_em="2026-10-20")
    res = _pagamentos(casa, banco_)
    assert len(res["baixadas"]) == 1 and res["conferir"] == []
    assert _situacao(db, tid) == "PAGO"
    b = APOIO.um(db, "SELECT * FROM pt_boletos WHERE id=%s", (r["boleto_id"],))
    assert b["situacao"] == BOL.PAGO and b["ato_id"]
    ato = APOIO.um(db, "SELECT * FROM pt_atos WHERE id=%s", (b["ato_id"],))
    detalhe = json.loads(ato["detalhe_json"])
    assert ato["tipo"] == "PAGAMENTO" and ato["livro_id"] and ato["folha"]
    assert detalhe["forma_pagamento"] == "BOLETO"
    assert r["nosso_numero"] in detalhe["forma_identificacao"]
    # O VALOR É O DO TÍTULO, EM CENTAVOS — e não cem vezes ele: inteiro pequeno
    # passado a `caixa_schema.centavos` seria lido como reais.
    assert detalhe["valor_pago_centavos"] == 131045
    assert detalhe["emolumentos_centavos"] == 4510


def test_buscar_de_novo_nao_paga_duas_vezes(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    r, banco_ = _emitir(casa, tid)
    banco_.simular_pagamento(r["nosso_numero"], pago_em="2026-10-20")
    _pagamentos(casa, banco_)
    # o boleto já está pago, mas a liquidação continua no banco
    with db.transaction() as con:
        from bd_nativo import banco
        banco(con).escrever("UPDATE pt_boletos SET situacao='EMITIDO' WHERE id=%s",
                            (r["boleto_id"],))
    segunda = _pagamentos(casa, banco_)
    assert segunda["ja_vistas"] == 1 and segunda["baixadas"] == []
    assert len(APOIO.ler(db, "SELECT id FROM pt_atos WHERE titulo_id=%s AND "
                             "tipo='PAGAMENTO' ORDER BY id", (tid,))) == 1


def test_valor_diferente_vira_pendencia_e_nao_baixa(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    r, banco_ = _emitir(casa, tid)
    banco_.simular_pagamento(r["nosso_numero"], pago_em="2026-10-20",
                             valor_centavos=100000)
    res = _pagamentos(casa, banco_)
    assert len(res["conferir"]) == 1
    assert _situacao(db, tid) == "APONTADO"
    with db.connect() as con:
        pend = BOL.pendencias(con)
    assert len(pend) == 1 and "decisão do oficial" in pend[0]["motivo"]
    assert APOIO.um(db, "SELECT situacao FROM pt_boletos")["situacao"] == BOL.CONFERIR
    with pytest.raises(BOL.BoletoDominioError):
        BOL.resolver_pendencia(db, pend[0]["id"], conferencia="ok")
    BOL.resolver_pendencia(db, pend[0]["id"], quem="oficial",
                           conferencia="Devolvido ao devedor pelo caixa.")
    with db.connect() as con:
        assert BOL.pendencias(con) == []


def test_titulo_pago_no_balcao_aparece_para_cancelar_e_o_pagamento_dobrado_vira_pendencia(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    r, banco_ = _emitir(casa, tid)
    with db.transaction() as con:
        PT.lancar_pagamento(con, tid, sv=APOIO.SV, agora=db.now(),
                            data_extenso="vinte de outubro", valor_pago="1310.45",
                            forma_pagamento="ESPECIE")
    with db.connect() as con:
        assert [b["id"] for b in BOL.vivos_de_titulo_encerrado(con)] == [r["boleto_id"]]
    banco_.simular_pagamento(r["nosso_numero"], pago_em="2026-10-21")
    res = _pagamentos(casa, banco_)
    assert len(res["conferir"]) == 1 and "PAGO" in res["conferir"][0]["motivo"]
    assert len(APOIO.ler(db, "SELECT id FROM pt_atos WHERE titulo_id=%s AND "
                             "tipo='PAGAMENTO' ORDER BY id", (tid,))) == 1


def test_titulo_sustado_depois_do_boleto_nao_recebe_baixa(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    r, banco_ = _emitir(casa, tid)
    with db.transaction() as con:
        PT.lancar_sustacao(con, tid, juizo="1ª Vara Exemplo",
                           processo="0000001-00.2026.8.10.0001", agora=db.now())
    banco_.simular_pagamento(r["nosso_numero"], pago_em="2026-10-21")
    res = _pagamentos(casa, banco_)
    assert "SUSTADO" in res["conferir"][0]["motivo"]
    assert _situacao(db, tid) == "APONTADO"


def test_liquidacao_de_boleto_que_a_casa_nao_conhece(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    _emitir(casa, tid)                          # há boleto vivo: pergunta-se

    class Estranho(APOIO.BancoDeTeste):
        def liquidacoes(self, desde, ate):
            return [{"evento_id": "EVX", "nosso_numero": "9999999999",
                     "valor_pago_centavos": 500, "pago_em": "2026-10-20"}]

    res = _pagamentos(casa, Estranho(pasta=casa["pasta"]))
    assert res["conferir"][0]["situacao"] == BOL.SEM_BOLETO
    with db.connect() as con:
        assert BOL.pendencias(con)[0]["evento_id"] == "EVX"


def test_em_homologacao_o_pagamento_nao_muda_o_titulo(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    r, falso = _emitir(casa, tid, cfg=APOIO.HOMOLOGACAO)
    BOL.simular_pagamento(db, r["boleto_id"], pago_em="2026-10-20",
                          transporte=falso, cfg=APOIO.HOMOLOGACAO)
    res = _pagamentos(casa, falso, cfg=APOIO.HOMOLOGACAO)
    assert res["baixadas"][0]["situacao"] == BOL.ENSAIO
    assert _situacao(db, tid) == "APONTADO"
    assert APOIO.um(db, "SELECT situacao FROM pt_boletos")["situacao"] == BOL.PAGO
    with db.connect() as con:
        assert BOL.pendencias(con) == []


def test_simular_pagamento_so_existe_na_homologacao(casa):
    tid = APOIO.titulo_apontado(casa["db"])
    r, banco_ = _emitir(casa, tid)
    with pytest.raises(BOL.BoletoDominioError):
        BOL.simular_pagamento(casa["db"], r["boleto_id"], pago_em=HOJE,
                              transporte=banco_, cfg=APOIO.PRODUCAO)


def test_sem_boleto_vivo_nao_se_pergunta_ao_banco(casa):
    class Proibido(APOIO.BancoDeTeste):
        def liquidacoes(self, desde, ate):
            raise AssertionError("não devia perguntar")

    res = _pagamentos(casa, Proibido(pasta=casa["pasta"]))
    assert res["perguntou"] is False

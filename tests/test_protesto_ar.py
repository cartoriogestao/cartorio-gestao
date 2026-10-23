# -*- coding: utf-8 -*-
"""O AR digital da intimação (LG06): a postagem do aviso pelos Correios, o
retorno que lavra pelo caminho da entrega da casa, e o tríduo do AR.

Os Correios aqui são o serviço falso (homologação) ou o dublê da produção —
nunca a rede. Ver `apoio_protesto_lg06`.
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
import correios_api as CAPI  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_ar as AR  # noqa: E402
import protesto_aviso as AV  # noqa: E402
import protesto_integracoes as INTEG  # noqa: E402


@pytest.fixture()
def casa(cg_casa, tmp_path):
    return {"db": cg_casa["db"], "pasta": tmp_path / "sim",
            "arquivos": tmp_path / "arquivos"}


def _postar(casa, aviso_id, cfg=None, transporte=None):
    cfg = cfg or APOIO.PRODUCAO
    transporte = transporte or APOIO.CorreiosDeTeste(pasta=casa["pasta"])
    return AR.solicitar_postagem(casa["db"], aviso_id, quem="escrevente",
                                 transporte=transporte, cfg=cfg), transporte


def _buscar(casa, transporte, cfg=None):
    return AR.buscar_retornos(casa["db"], quem="escrevente",
                              pasta_de_arquivos=casa["arquivos"],
                              transporte=transporte, cfg=cfg or APOIO.PRODUCAO)


# ---------------------------------------------------------------- desligado


def test_a_integracao_nasce_desligada_e_nada_se_posta(casa):
    db = casa["db"]
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db))
    with db.connect() as con:
        assert INTEG.configuracao(con, INTEG.AR)["modo"] == INTEG.DESLIGADO
    with pytest.raises(INTEG.IntegracaoDesligada) as e:
        AR.solicitar_postagem(db, aviso, quem="escrevente")
    assert "DESLIGADA" in str(e.value)
    assert APOIO.ler(db, "SELECT id FROM pt_ar_postagens ORDER BY id") == []


# ----------------------------------------------------------------- postagem


def test_a_postagem_guarda_o_objeto_e_o_prazo_limite_do_aviso(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    r, _ = _postar(casa, aviso)
    p = APOIO.um(db, "SELECT * FROM pt_ar_postagens WHERE id=%s",
                 (r["postagem_id"],))
    assert p["situacao"] == AR.POSTADA
    assert p["codigo_objeto"].startswith("ZZ") and p["codigo_objeto"].endswith("BR")
    # O MESMO PRAZO QUE VAI IMPRESSO NO AVISO, e não outra conta.
    assert p["prazo_limite"] == APOIO.prazo(db, tid)
    assert p["ambiente"] == "PRODUCAO" and p["titulo_id"] == tid
    assert json.loads(p["destinatario_json"])["cep"] == "65000000"


def test_o_digito_do_objeto_e_o_do_padrao_postal():
    # O exemplo do padrão S10 da UPU: 47312482 tem dígito 9.
    assert CAPI.digito_do_objeto("47312482") == 9


def test_um_aviso_nao_tem_duas_postagens_vivas(casa):
    db = casa["db"]
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db))
    _postar(casa, aviso)
    with pytest.raises(AR.ArError):
        _postar(casa, aviso)
    assert len(APOIO.ler(db, "SELECT id FROM pt_ar_postagens ORDER BY id")) == 1


def test_cep_torto_e_recusado_antes_da_rede(casa):
    db = casa["db"]
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db, cep="650"))
    with pytest.raises(AR.ArError) as e:
        _postar(casa, aviso)
    assert "CEP" in str(e.value)
    assert APOIO.ler(db, "SELECT id FROM pt_ar_postagens ORDER BY id") == []


def test_titulo_sustado_nao_vai_pelo_correio(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    with db.transaction() as con:
        PT.lancar_sustacao(con, tid, juizo="1ª Vara Exemplo",
                           processo="0000001-00.2026.8.10.0001", agora=db.now())
    with pytest.raises(AR.ArError) as e:
        _postar(casa, aviso)
    assert "sustado" in str(e.value)


def test_a_falha_dos_correios_fica_registrada_e_libera_o_aviso(casa):
    db = casa["db"]
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db))

    class Fora(APOIO.CorreiosDeTeste):
        def postar(self, pedido):
            raise CAPI.CorreiosError("os Correios não responderam")

    with pytest.raises(AR.ArError) as e:
        _postar(casa, aviso, transporte=Fora(pasta=casa["pasta"]))
    assert "Nada foi postado" in str(e.value)
    p = APOIO.um(db, "SELECT situacao, observacao FROM pt_ar_postagens")
    assert p["situacao"] == AR.FALHOU and "não responderam" in p["observacao"]
    r, _ = _postar(casa, aviso)              # a vaga ficou livre
    assert r["codigo_objeto"]


def test_o_servico_falso_nao_vale_em_producao(casa):
    db = casa["db"]
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db))
    with pytest.raises(INTEG.IntegracaoError):
        _postar(casa, aviso, transporte=CAPI.CorreiosFalso(pasta=casa["pasta"]))


# ------------------------------------------------------------------ retorno


def test_ar_entregue_lavra_a_intimacao_pessoal_e_anexa_o_canhoto(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    r, transporte = _postar(casa, aviso)
    transporte.simular_retorno(r["codigo_objeto"], entregue=True,
                               data="2026-10-20", recebedor="BELTRANO EXEMPLO")
    voltou = _buscar(casa, transporte)
    assert voltou["olhadas"] == 1 and len(voltou["voltaram"]) == 1

    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s",
                    (tid,))["situacao"] == "INTIMADO"
    av = APOIO.um(db, "SELECT * FROM pt_avisos WHERE id=%s", (aviso,))
    assert av["situacao"] == "ENTREGUE" and av["entregador"] == "CORREIOS"
    assert av["entrega_em"] == "2026-10-20"
    ato = APOIO.um(db, "SELECT * FROM pt_atos WHERE id=%s", (av["ato_id"],))
    detalhe = json.loads(ato["detalhe_json"])
    assert ato["tipo"] == "INTIMACAO" and detalhe["modo"] == "PESSOAL"
    assert "CORREIOS" in detalhe["comprovante"]
    p = APOIO.um(db, "SELECT * FROM pt_ar_postagens WHERE id=%s",
                 (r["postagem_id"],))
    assert p["situacao"] == AR.ENTREGUE and p["ato_id"] == av["ato_id"]
    anexo = APOIO.um(db, "SELECT * FROM attachments WHERE id=%s", (p["anexo_id"],))
    assert anexo["entity_type"] == AV.ENTIDADE_DO_COMPROVANTE
    assert anexo["entity_id"] == aviso
    assert Path(anexo["stored_path"]).read_bytes().startswith(b"\x89PNG")


def test_buscar_de_novo_nao_assenta_duas_vezes(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    r, transporte = _postar(casa, aviso)
    transporte.simular_retorno(r["codigo_objeto"], entregue=True,
                               data="2026-10-20")
    _buscar(casa, transporte)
    segundo = _buscar(casa, transporte)
    assert segundo["olhadas"] == 0
    assert len(APOIO.ler(db, "SELECT id FROM pt_atos WHERE titulo_id=%s AND "
                             "tipo='INTIMACAO' ORDER BY id", (tid,))) == 1
    # e o mesmo retorno mandado de novo à mão também não
    de_novo = AR.registrar_retorno(db, r["postagem_id"],
                                   transporte.consultar(r["codigo_objeto"]),
                                   pasta_de_arquivos=casa["arquivos"])
    assert de_novo.get("ja_estava") is True


def test_ar_ausente_vai_para_a_fila_do_aviso_nao_entregue(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    r, transporte = _postar(casa, aviso)
    transporte.simular_retorno(r["codigo_objeto"], entregue=False,
                               data="2026-10-21", motivo="AUSENTE")
    _buscar(casa, transporte)
    av = APOIO.um(db, "SELECT * FROM pt_avisos WHERE id=%s", (aviso,))
    assert av["situacao"] == "NAO_ENTREGUE" and av["motivo"] == 11
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s",
                    (tid,))["situacao"] == "APONTADO"
    with db.connect() as con:
        assert aviso in [a["id"] for a in AV.esperando_edital(con)]
    assert APOIO.um(db, "SELECT situacao FROM pt_ar_postagens")["situacao"] \
        == AR.NAO_ENTREGUE


def test_mudou_se_dos_correios_e_o_motivo_que_vai_direto_ao_edital(casa):
    db = casa["db"]
    aviso = APOIO.aviso_emitido(db, APOIO.titulo_apontado(db))
    r, transporte = _postar(casa, aviso)
    transporte.simular_retorno(r["codigo_objeto"], entregue=False,
                               data="2026-10-21", motivo="MUDOU_SE")
    _buscar(casa, transporte)
    av = APOIO.um(db, "SELECT motivo FROM pt_avisos WHERE id=%s", (aviso,))
    assert AV.vai_direto_para_edital(av["motivo"])


def test_todo_motivo_dos_correios_tem_lugar_no_catalogo_da_casa():
    assert set(AR.MOTIVO_DA_CASA) == set(CAPI.MOTIVOS)
    for codigo in AR.MOTIVO_DA_CASA.values():
        assert codigo in AV.TODOS_OS_MOTIVOS


def test_ar_de_titulo_pago_no_meio_do_caminho_fica_para_conferir(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    r, transporte = _postar(casa, aviso)
    with db.transaction() as con:
        PT.lancar_pagamento(con, tid, sv=APOIO.SV, agora=db.now(),
                            data_extenso="vinte de outubro", valor_pago="1310.45")
    transporte.simular_retorno(r["codigo_objeto"], entregue=True,
                               data="2026-10-21")
    voltou = _buscar(casa, transporte)
    assert voltou["voltaram"][0]["situacao"] == AR.CONFERIR
    p = APOIO.um(db, "SELECT * FROM pt_ar_postagens")
    assert p["situacao"] == AR.CONFERIR and "PAGO" in p["observacao"]
    # NADA PELA METADE: sem intimação, aviso como estava.
    assert APOIO.um(db, "SELECT situacao FROM pt_avisos WHERE id=%s",
                    (aviso,))["situacao"] == "EMITIDO"
    assert APOIO.ler(db, "SELECT id FROM pt_atos WHERE titulo_id=%s AND "
                         "tipo='INTIMACAO' ORDER BY id", (tid,)) == []


def test_ar_que_volta_depois_do_prazo_avisa_o_art_924(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    r, transporte = _postar(casa, aviso)
    transporte.simular_retorno(r["codigo_objeto"], entregue=True,
                               data="2026-12-01")
    _buscar(casa, transporte)
    obs = APOIO.um(db, "SELECT observacao FROM pt_ar_postagens")["observacao"]
    assert "art. 924" in obs


def test_em_homologacao_o_retorno_nao_lavra_nem_anexa(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    aviso = APOIO.aviso_emitido(db, tid)
    falso = CAPI.CorreiosFalso(pasta=casa["pasta"])
    r, _ = _postar(casa, aviso, cfg=APOIO.HOMOLOGACAO, transporte=falso)
    falso.simular_retorno(r["codigo_objeto"], entregue=True, data="2026-10-20")
    _buscar(casa, falso, cfg=APOIO.HOMOLOGACAO)
    p = APOIO.um(db, "SELECT * FROM pt_ar_postagens")
    assert p["situacao"] == AR.ENTREGUE and p["ambiente"] == "HOMOLOGACAO"
    assert p["ato_id"] is None and p["anexo_id"] is None
    assert APOIO.um(db, "SELECT situacao FROM pt_titulos WHERE id=%s",
                    (tid,))["situacao"] == "APONTADO"
    assert APOIO.um(db, "SELECT situacao FROM pt_avisos WHERE id=%s",
                    (aviso,))["situacao"] == "EMITIDO"


# ------------------------------------------------------------------- tríduo


def test_o_ar_que_chegou_ao_prazo_sem_voltar_aparece_no_proprio_dia(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    _postar(casa, APOIO.aviso_emitido(db, tid))
    limite = APOIO.prazo(db, tid)
    with db.connect() as con:
        assert AR.sem_retorno(con, hoje="2026-10-19") == []
        no_dia = AR.sem_retorno(con, hoje=limite)
    assert [p["titulo_id"] for p in no_dia] == [tid]


def test_postagem_de_homologacao_nao_conta_no_triduo(casa):
    db = casa["db"]
    tid = APOIO.titulo_apontado(db)
    _postar(casa, APOIO.aviso_emitido(db, tid), cfg=APOIO.HOMOLOGACAO,
            transporte=CAPI.CorreiosFalso(pasta=casa["pasta"]))
    with db.connect() as con:
        assert AR.sem_retorno(con, hoje="2026-12-31") == []

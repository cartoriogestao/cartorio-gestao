"""Integração com sessão, CSRF, transação, anexo e idempotência (PostgreSQL isolado)."""
import io
from unittest.mock import patch
import pytest
from datetime import datetime

from bd_nativo import banco
import automacao as AU
import despesas as DP
import despesas_inter as INTER
import despesas_portal_selo as PS
from tests.test_despesas import InterFalso, CAMPOS
from tests.test_despesas_fluidez import _token
from tests.test_despesas_portal_selo_unidade import texto

BASE = '/administrativo/despesas/portal-selo'


def _post(c, fundo='FERJ', **extras):
    dados = {'csrf_token': _token(c, BASE), 'documento': (io.BytesIO(b'%PDF ficticio'), 'guia.pdf'), **extras}
    with patch.object(PS, 'ler_pdf', return_value=PS.ler_texto(texto(fundo))):
        return c.post(BASE, data=dados, headers={'Accept': 'application/json'})


def test_conferir_nao_cadastra_e_commit_e_idempotente_com_anexo(cg_casa_logada):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        lido = _post(c, conferir='1', valor_esperado_centavos='999999').get_json()
        assert lido['valor_esperado_centavos'] == 12345  # o cliente não decide a conferência
        assert 'codigo' not in lido and 'beneficiario_documento' not in lido
        a, b = _post(c).get_json(), _post(c).get_json()
    assert a['id'] == b['id'] and a['novo'] and not b['novo']
    with db.connect() as con:
        d = DP.despesa(con, a['id'])
        assert d['situacao'] == DP.AUTORIZADA
        assert len(DP.anexos(con, a['id'])) == 1


@pytest.mark.parametrize('fundo', ['FADEP', 'FEMP', 'FERRFIS'])
def test_fundos_do_bb_nao_pedem_execucao_bancaria(cg_casa_logada, fundo):
    c = cg_casa_logada['c']
    with patch('automacao.pedir_rodada') as pedir:
        r = _post(c, fundo)
        assert r.status_code == 200
        assert r.get_json()['situacao'] == DP.AGUARDANDO
        assert not r.get_json()['envio_solicitado']
        pedir.assert_not_called()


def test_csrf_continua_obrigatorio(cg_casa_logada):
    c = cg_casa_logada['c']
    assert c.post(BASE, data={'documento': (io.BytesIO(b'%PDF'), 'guia.pdf')}).status_code == 400


def _preparar_executor(db):
    with db.transaction() as con:
        AU.semear(con)
        p = AU.por_codigo(con, 'DESPESAS_PAGAR')
        AU.definir_pode_agir(con, p['id'], True, papel='ADMIN', usuario='mario')
        DP.gravar_configuracao(con, {**DP.PADRAO, 'despesas_pagamento_ligado': '1',
                                     'despesas_ambiente': 'sandbox'})


@pytest.mark.parametrize('fundo', ['FERJ', 'FERC'])
def test_ferj_ferc_enfileiram_e_executor_envia_apenas_ao_banco_falso(cg_casa_logada, fundo):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345), \
            patch.object(INTER, 'cliente_da_casa', side_effect=AssertionError('A rota não fala com o banco')):
        resposta = _post(c, fundo)
    assert resposta.status_code == 200
    r = resposta.get_json()
    assert r['situacao'] == DP.AUTORIZADA and r['envio_solicitado']
    with db.connect() as con:
        pedido = AU.por_codigo(con, 'DESPESAS_PAGAR')
        assert pedido['pedido_manual_em'] and pedido['pedido_manual_por']
        assert len(DP.anexos(con, r['id'])) == 1
    falso = InterFalso()
    cliente = INTER.ClienteInter('sandbox', falso, CAMPOS)
    enviado = INTER.pagar(db, r['id'], cliente=cliente, por='automação', agora=datetime(2026, 11, 9))
    assert enviado['situacao'] == DP.ENVIADA
    assert len(falso.posts('/banking/v2/pagamento')) == 1
    with db.connect() as con:
        assert DP.despesa(con, r['id'])['situacao'] == DP.ENVIADA  # pedido não é confirmação


@pytest.mark.parametrize('fundo', ['FADEP', 'FEMP', 'FERRFIS'])
def test_banco_do_brasil_nao_sai_no_inter_mesmo_se_autorizado_a_mao(cg_casa_logada, fundo):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    r = _post(c, fundo).get_json()
    assert r['situacao'] == DP.AGUARDANDO and not r['envio_solicitado']
    with db.transaction() as con:
        DP.autorizar(con, r['id'], agora=datetime(2026, 11, 9), por='mario', papel='ADMIN')
    falso = InterFalso()
    resultado = INTER.pagar(db, r['id'], cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                            por='automação', agora=datetime(2026, 11, 9))
    assert 'Banco do Brasil' in resultado['mensagem']
    assert falso.chamadas == []


def test_falha_ao_pedir_rodada_reverte_cadastro_e_anexo_no_banco(cg_casa_logada, monkeypatch):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    monkeypatch.setitem(cg_casa_logada['app'].config, 'PROPAGATE_EXCEPTIONS', True)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345), \
            patch.object(AU, 'pedir_rodada', side_effect=RuntimeError('fila indisponível')):
        with pytest.raises(RuntimeError, match='fila indisponível'):
            _post(c)
    with db.connect() as con:
        assert banco(con).valor('SELECT count(*) FROM dp_despesas') == 0
        assert banco(con).valor("SELECT count(*) FROM attachments WHERE entity_type = 'DESPESA'") == 0


@pytest.mark.parametrize('esperado', [None, 12000])
def test_cliente_nao_forca_autorizacao_sem_conferencia_servidor(cg_casa_logada, esperado):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    with patch.object(PS, 'esperado_dos_selos', return_value=esperado):
        r = _post(c, valor_esperado_centavos='12345').get_json()
    assert r['situacao'] == DP.AGUARDANDO and not r['envio_solicitado']

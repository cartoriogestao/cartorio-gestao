"""Integração com sessão, CSRF, transação, anexo e idempotência (PostgreSQL isolado)."""
import io
from unittest.mock import patch
import pytest

from bd_nativo import banco
import despesas as DP
import despesas_portal_selo as PS
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

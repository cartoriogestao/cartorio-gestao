"""Regressao: consulta sem remessa encerra a cobranca; falhas nao encerram."""
import json
from datetime import datetime
import pytest
import cra21_api as API
import protesto_roteiro as R
from test_protesto_aviso_web import s, _con, _token

SEM_REMESSA = ('<?xml version="1.0"?><relatorio><codigo>0003</codigo>'
               '<ocorrencia>SEM REMESSAS PENDENTES</ocorrencia></relatorio>')


def test_sem_remessa_preserva_codigo_motivo_e_resposta():
    with pytest.raises(API.CraSemRemessa) as e:
        API._remessa_ou_aviso(SEM_REMESSA)
    assert e.value.codigo == '0003'
    assert e.value.motivo == 'SEM REMESSAS PENDENTES'
    assert e.value.bruto == SEM_REMESSA


@pytest.mark.parametrize('texto', [
    '<erro><mensagem>Falha na autenticacao</mensagem><codigo>1</codigo></erro>',
    '<relatorio><codigo>0002</codigo><ocorrencia>NOME INVALIDO</ocorrencia></relatorio>',
    '<relatorio><codigo>10000</codigo><ocorrencia>XML CORROMPIDO</ocorrencia></relatorio>',
    '<relatorio>SEM CODIGO</relatorio>',
])
def test_erro_nao_e_consulta_sem_movimento(texto):
    with pytest.raises(API.CraRecusou) as e:
        API._remessa_ou_aviso(texto)
    assert not isinstance(e.value, API.CraSemRemessa)


@pytest.mark.parametrize('caminho,acao', [
    ('/protesto/remessas/da-cra', 'cra_baixar_e_conferir'),
    ('/protesto/cra/api/baixar', 'cra_baixar'),
])
@pytest.mark.parametrize('qual', ['pendentes', 'remessa'])
def test_sem_remessa_fica_feito_sem_importar_titulos(s, monkeypatch, caminho, acao, qual):
    import cra21_web as WEB
    monkeypatch.setattr(API, '_bater', lambda *a, **kw:
                        '<return>' + SEM_REMESSA.replace('<', '&lt;').replace('>', '&gt;') + '</return>')
    tela = s['c'].get('/protesto/remessas').get_data(as_text=True)
    resposta = s['c'].post(caminho, data={'csrf_token': _token(tela),
                         'o_que': qual, 'nome': 'B0000311.261'}, follow_redirects=True)
    assert resposta.status_code == 200
    assert 'SEM REMESSAS PENDENTES' in resposta.get_data(as_text=True)
    with _con(s) as con:
        auditoria = con.execute('SELECT details FROM audit_logs WHERE action=? ORDER BY id DESC LIMIT 1', (acao,)).fetchone()
        assert json.loads(auditoria[0])['resultado'] == 'SEM_REMESSA'
        assert json.loads(auditoria[0])['codigo'] == '0003'
        assert con.execute('SELECT COUNT(*) FROM pt_remessas').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 0
        ctx = R._contexto(con, datetime.now().isoformat(timespec='seconds'))
        assert R._remessa_do_dia(con, ctx)['situacao'] == 'FEITO'


@pytest.mark.parametrize('caminho', ['/protesto/remessas/da-cra', '/protesto/cra/api/baixar'])
@pytest.mark.parametrize('falha', ['credencial', 'rede', 'nome', 'desconhecido'])
def test_falha_continua_pendente(s, monkeypatch, caminho, falha):
    import cra21_web as WEB
    def trazer(*a, **kw):
        if falha == 'rede':
            raise API.CraError('Falha de comunicacao')
        codigo = {'credencial': '1', 'nome': '0002', 'desconhecido': '9999'}[falha]
        if falha == 'credencial':
            texto = '<erro><mensagem>Falha na autenticacao</mensagem><codigo>1</codigo></erro>'
        else:
            texto = f'<relatorio><codigo>{codigo}</codigo><ocorrencia>RECUSA</ocorrencia></relatorio>'
        return API._remessa_ou_aviso(texto)
    monkeypatch.setattr(WEB, '_trazer', trazer)
    tela = s['c'].get('/protesto/remessas').get_data(as_text=True)
    resposta = s['c'].post(caminho, data={'csrf_token': _token(tela),
                         'o_que': 'pendentes'}, follow_redirects=True)
    assert resposta.status_code == 200
    with _con(s) as con:
        ctx = R._contexto(con, datetime.now().isoformat(timespec='seconds'))
        assert R._remessa_do_dia(con, ctx)['situacao'] != 'FEITO'
        assert con.execute("SELECT COUNT(*) FROM audit_logs WHERE action IN ('cra_baixar','cra_baixar_e_conferir') AND details LIKE '%SEM_REMESSA%'").fetchone()[0] == 0

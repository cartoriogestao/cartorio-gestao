"""Recusas recuperaveis sem duplicar despesas, enviar dinheiro ou perder autoria."""
import json
import re
from datetime import date

import pytest

import despesas as DP
import despesas_fluxo as DF
import despesas_inter as INTER
from bd_nativo import banco
from tests.conftest import cg_login
from tests.test_despesas import (
    AGORA,
    VENCIMENTO,
    _autorizar,
    _cadastrar,
    _d,
    boleto,
    pix,
)

BASE = '/administrativo/despesas'


def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)


def _dados(db, i, **mudancas):
    d = _d(db, i)
    return {**{k: d[k] for k in DF.CAMPOS if k != 'codigo_barras'},
            'valor': DP.reais(d['valor']), 'motivo': 'Corrigir dados conforme a fatura',
            'revisao': DF.revisao(d), **mudancas}


def _corrigir(db, i, dados, **extras):
    with db.transaction() as con:
        uid = banco(con).um("SELECT id FROM users WHERE username='mario'")['id']
        return DF.corrigir(con, i, dados=dados, motivo=dados['motivo'], versao=dados['revisao'],
                           agora=AGORA, por='mario', papel=extras.get('papel', 'ADMIN'), usuario_id=uid)


def test_leitura_do_boleto_reduz_digitacao_e_sugere_calendario_atual():
    lido = DF.ler_codigo(boleto(12345), hoje=date(2026, 11, 4))
    assert (lido['forma'], lido['valor'], lido['vencimento']) == (DP.BOLETO, '123,45', VENCIMENTO)
    assert 'nao consulta' in lido['aviso']


def test_pix_dinamico_nao_inventa_valor_que_nao_esta_no_texto():
    import binascii
    p = pix(None)
    # Troca a subtag da chave por URL, mantendo os comprimentos TLV e recalculando o CRC.
    p = p.replace('0122fornecedor@example.com', '2522fornecedor@example.com')
    p = p[:-4] + f'{binascii.crc_hqx(p[:-4].encode(), 0xFFFF):04X}'
    lido = DF.ler_codigo(p, hoje=date(2026, 11, 4))
    assert lido['valor'] == '' and 'dinamico' in lido['aviso']


@pytest.mark.parametrize('codigo', ['000201corrompido', '123', 'x' * 4097])
def test_leitura_recusa_codigo_invalido(codigo):
    with pytest.raises(DP.DespesaError):
        DF.ler_codigo(codigo, hoje=date(2026, 11, 4))


def test_correcao_revoga_autorizacao_preserva_numero_documentos_e_audita(cg_casa_logada):
    db = cg_casa_logada['db']
    i = _cadastrar(db)
    _autorizar(db, i)
    antes = _d(db, i)
    novo = _corrigir(db, i, _dados(db, i, forma=DP.PIX_COPIA_E_COLA, codigo=pix('123.45')))
    assert novo['id'] == i and novo['situacao'] == DP.AGUARDANDO
    assert novo['autorizada_em'] is None and novo['autorizada_por'] is None
    assert novo['acima_do_teto'] == 0 and novo['tentativas'] == 0
    for k in ('documento_especie', 'documento_numero', 'origem', 'cadastrada_em', 'cadastrada_por'):
        assert novo[k] == antes[k]
    with db.connect() as con:
        a = banco(con).um("SELECT * FROM audit_logs WHERE action='DESPESA_PAGAMENTO_CORRIGIDO' AND entity_id=%s", (i,))
        detalhe = json.loads(a['details'])
        assert detalhe['antes']['forma'] == DP.BOLETO
        assert detalhe['depois']['forma'] == DP.PIX_COPIA_E_COLA
        assert detalhe['autorizacao_revogada']['por'] == antes['autorizada_por']
        assert banco(con).valor('SELECT count(*) FROM dp_despesas') == 1


def test_recusa_definitiva_pode_ser_corrigida_sem_recriar(cg_casa_logada):
    db = cg_casa_logada['db']; i = _cadastrar(db)
    with db.transaction() as con:
        banco(con).escrever("UPDATE dp_despesas SET situacao='FALHOU',banco_status='RECUSADO',tentativas=1,enviada_em=%s,mensagem='Data de vencimento' WHERE id=%s", (AGORA.isoformat(), i))
    novo = _corrigir(db, i, _dados(db, i, forma=DP.PIX_COPIA_E_COLA, codigo=pix('123.45')))
    assert novo['situacao'] == DP.AGUARDANDO and not novo['banco_status']


@pytest.mark.parametrize('situacao,status,codigo,tentativas', [
    (DP.ENVIADA, 'AGENDADO', 'T1', 1), (DP.FALHOU, 'SEM_RESPOSTA', '', 1),
    (DP.FALHOU, 'RECUSADO', 'T1', 1), (DP.PAGA, 'REALIZADO', 'T1', 1),
    (DP.CONCILIADA, 'PAGO', 'T1', 1), (DP.CANCELADA, '', '', 0),
    (DP.AGUARDANDO, '', '', 1), (DP.FALHOU, 'FALHA', 'P1', 1),
])
def test_correcao_bloqueia_resultado_incerto_pago_cancelado_ou_com_referencia(cg_casa_logada, situacao,status,codigo,tentativas):
    db = cg_casa_logada['db']; i = _cadastrar(db)
    with db.transaction() as con:
        banco(con).escrever('UPDATE dp_despesas SET situacao=%s,banco_status=%s,banco_codigo=%s,tentativas=%s WHERE id=%s', (situacao,status,codigo or None,tentativas,i))
    antes = _d(db, i)
    with pytest.raises(DP.DespesaError, match='Nao e seguro'):
        _corrigir(db, i, _dados(db, i, valor='100,00'))
    assert _d(db, i) == antes


def test_formulario_antigo_nao_sobrescreve_correcao_e_nao_autoriza_outro_codigo(cg_casa_logada):
    db = cg_casa_logada['db']; i = _cadastrar(db)
    velho = _dados(db, i, forma=DP.PIX_COPIA_E_COLA, codigo=pix('123.45'))
    _corrigir(db, i, velho)
    with pytest.raises(DP.DespesaError, match='mudou'):
        _corrigir(db, i, velho)
    with pytest.raises(DP.DespesaError, match='Recarregue'), db.transaction() as con:
        DF.conferir_revisao(con, i, velho['revisao'])


def test_valor_incompativel_motivo_curto_e_perfil_nao_alteram_despesa(cg_casa_logada):
    db = cg_casa_logada['db']; i = _cadastrar(db); antes = _d(db, i)
    for dados, papel in [(_dados(db, i, valor='100,00'), 'ADMIN'),
                         (_dados(db, i, motivo='x'), 'ADMIN'),
                         (_dados(db, i, valor='100,00'), 'MANAGER')]:
        with pytest.raises(DP.DespesaError): _corrigir(db, i, dados, papel=papel)
        assert _d(db, i) == antes


def test_falha_na_auditoria_reverte_toda_a_correcao(cg_casa_logada, monkeypatch):
    db = cg_casa_logada['db']; i = _cadastrar(db); antes = _d(db, i)
    def falhar(*a, **kw): raise RuntimeError('auditoria indisponivel')
    monkeypatch.setattr(DF.IDR, 'registrar', falhar)
    with pytest.raises(RuntimeError):
        _corrigir(db, i, _dados(db, i, forma=DP.PIX_COPIA_E_COLA, codigo=pix('123.45')))
    assert _d(db, i) == antes
    with db.connect() as con:
        assert not [e for e in DP.eventos(con, i) if e['operacao'] == 'CORRIGIR_PAGAMENTO']


def test_tela_corrige_sem_chamar_banco_e_exige_nova_autorizacao(cg_casa_logada, monkeypatch):
    db, c = cg_casa_logada['db'], cg_casa_logada['c']; i = _cadastrar(db)
    def proibido(*a, **kw): raise AssertionError('Nao deve acessar o banco Inter')
    monkeypatch.setattr(INTER, 'cliente_da_casa', proibido)
    dados = _dados(db, i, forma=DP.PIX_COPIA_E_COLA, codigo=pix('123.45'))
    dados['csrf_token'] = _token(c, f'{BASE}/{i}')
    r = c.post(f'{BASE}/{i}/corrigir-pagamento', data=dados, follow_redirects=True)
    assert r.status_code == 200 and 'Nenhum pagamento foi enviado' in r.get_data(as_text=True)
    assert _d(db, i)['situacao'] == DP.AGUARDANDO
    html = c.get(f'{BASE}/{i}').get_data(as_text=True)
    assert 'Ler código' in html and 'Salvar correção' in html
    assert c.post(f'{BASE}/{i}/autorizar', data={'csrf_token':dados['csrf_token'], 'revisao':dados['revisao']}).status_code == 302
    assert _d(db, i)['situacao'] == DP.AGUARDANDO
    c.post(f'{BASE}/{i}/autorizar', data={'csrf_token':dados['csrf_token'], 'revisao':DF.revisao(_d(db, i))})
    assert _d(db, i)['situacao'] == DP.AUTORIZADA


def test_leitura_nao_expoe_despesas_e_correcao_nao_libera_outros_usuarios(cg_casa_logada):
    casa = cg_casa_logada; db = casa['db']; i = _cadastrar(db)
    db.create_user('balcao', 'BALCAO EXEMPLO', 'Senha#12345', 'USER')
    c = casa['app'].test_client(); cg_login(c, 'balcao', 'Senha#12345')
    csrf = _token(c, BASE + '/nova')
    lido = c.post(BASE + '/ler-codigo', data={'csrf_token':csrf,'codigo':boleto(12345)})
    assert lido.status_code == 200 and lido.json['valor'] == '123,45'
    assert 'beneficiario_nome' not in lido.json
    assert c.post(f'{BASE}/{i}/corrigir-pagamento', data={'csrf_token':csrf}).status_code == 403
    assert c.post(BASE + '/ler-codigo', data={'codigo':boleto(12345)}).status_code in (400,403)


def test_agendado_tem_orientacao_e_nao_oferece_correcao(cg_casa_logada):
    db, c = cg_casa_logada['db'], cg_casa_logada['c']; i = _cadastrar(db)
    with db.transaction() as con:
        banco(con).escrever("UPDATE dp_despesas SET situacao='ENVIADA',banco_status='AGENDADO',banco_codigo='T1' WHERE id=%s", (i,))
    html = c.get(f'{BASE}/{i}').get_data(as_text=True)
    assert 'Pagamento agendado' in html and 'nao cadastre outra' in html
    assert 'Salvar correção' not in html

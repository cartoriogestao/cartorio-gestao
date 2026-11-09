"""Confirmação bancária, caixa único e consentimento ANTES do POST.

APIs falsas; dados fictícios. Contratos: Parcela v1 OpenAPI
GET /v1/sellers/{sellerId}/payment-links e inter-co/pj-sdk-python,
BankingPixClient (include_pix/retrieve_pix, sem identificação prévia).
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

import cobranca as CB
import cobranca_automacao as CA
import cobranca_banco as CBB
import cobranca_parcela as PX
import despesas as DP
import despesas_inter as INTER
from bd_nativo import banco
from tests.test_despesas import _autorizar, _cadastrar, _d, InterFalso, CAMPOS as INTER_CAMPOS

AGORA = datetime(2026, 11, 9, 19, 0, tzinfo=timezone(timedelta(hours=-3)))
CAMPOS = {'email': 'caixa@exemplo.test', 'senha': 'senha-ficticia', 'seller_id': 'seller-ficticio'}


@pytest.fixture
def casa(cg_casa_logada):
    with cg_casa_logada['db'].transaction() as con:
        DP.gravar_configuracao(con, {**DP.PADRAO, 'despesas_pagamento_ligado': '1',
                                     'despesas_ambiente': 'sandbox'})
    falso = InterFalso()
    return {**cg_casa_logada, 'inter': falso,
            'cliente': INTER.ClienteInter('sandbox', falso, INTER_CAMPOS)}


def _pago(**campos):
    return {'id': 'link-ficticio', 'token': 'token-ficticio', 'status': 'paid',
            'seller': {'id': CAMPOS['seller_id']}, 'amount': 12345,
            'sale': {'id': 'venda-ficticia', 'status': 'succeeded', 'form_payment': 'pix',
                     'amount': 12345, 'original_amount': 12345,
                     'updated_at': '2026-11-10T01:30:00Z'}, **campos}


def _cliente(paginas):
    chamadas = []
    def transporte(metodo, url, *, json_corpo=None, cabecalhos=None):
        chamadas.append((metodo, url))
        if url.endswith(PX.CAMINHO_DO_TOKEN):
            return INTER.Resposta(200, {'access_token': 'token-teste'})
        assert metodo == 'GET'
        assert urlsplit(url).path == '/v1/sellers/seller-ficticio/payment-links'
        assert cabecalhos['Authorization'] == 'Bearer token-teste'
        n = int(parse_qs(urlsplit(url).query)['current_page'][0])
        return INTER.Resposta(200, {'results': paginas[n-1], 'current_page': n,
                                   'total_pages': len(paginas), 'has_more': n < len(paginas)})
    return PX.ClienteCobrancaParcela('sandbox', transporte, CAMPOS), chamadas


def test_link_pago_localizado_por_token_na_pagina_seguinte():
    cliente, chamadas = _cliente([[_pago(id='outro', token='outro')], [_pago()]])
    r = cliente.consultar({'banco_id': 'token-ficticio', 'valor': 12345})
    assert r['situacao'] == CB.RECEBIDA and r['forma_recebida'] == 'PIX'
    assert r['data_pagamento'] == '2026-11-09'  # UTC -> dia da serventia
    assert len(chamadas) == 3


@pytest.mark.parametrize('status,esperada', [('expired', CB.BAIXADA), ('canceled', CB.CANCELADA), ('active', CB.ABERTA)])
def test_consulta_autenticada_tambem_acha_link_expirado(status, esperada):
    cliente, _ = _cliente([[_pago(status=status, sale=None)]])
    assert cliente.consultar({'banco_id': 'link-ficticio', 'valor': 12345})['situacao'] == esperada


@pytest.mark.parametrize('mudanca', [
    {'sale': None}, {'sale': {'status': 'pending'}},
    {'sale': {**_pago()['sale'], 'id': ''}},
    {'sale': {**_pago()['sale'], 'form_payment': 'pending'}},
    {'sale': {**_pago()['sale'], 'updated_at': 'invalida'}},
    {'sale': {**_pago()['sale'], 'amount': 0, 'original_amount': 0}},
])
def test_link_pago_sem_prova_de_liquidacao_nao_gera_caixa(mudanca):
    with pytest.raises(PX.Recusa):
        PX.ler(_pago(**mudanca))


def test_valor_diferente_ou_link_ambiguo_nao_baixa():
    cliente, _ = _cliente([[_pago()]])
    with pytest.raises(PX.Recusa, match='valor'):
        cliente.consultar({'banco_id': 'token-ficticio', 'valor': 999})
    cliente, _ = _cliente([[_pago(), _pago()]])
    with pytest.raises(PX.Recusa, match='duplicadas'):
        cliente.consultar({'banco_id': 'token-ficticio', 'valor': 12345})


def test_pos_e_centavos_numericos_e_validacao_detalhada():
    assert PX._centavos(12345.0) == 12345
    assert PX._centavos(123.45) is None
    assert PX.FORMA['PIX_POS'] == 'PIX'
    msg = PX._frase({'message': 'Bad Request Exception', 'errors': [
        {'property': 'terminal_id', 'constraints': {'isString': 'terminal_id deve ser texto'},
         'value': 'SEGREDO', 'target': {'password': 'SEGREDO'}}]})
    assert 'terminal_id deve ser texto' in msg and 'SEGREDO' not in msg


def _recebimento(db, *, valor_item=12345, data='2026-11-09', numero='2026.11.99999', resposta=None):
    with db.transaction() as con:
        b = banco(con)
        p = b.escrever("""INSERT INTO cx_protocolos (numero, data_abertura, interessado, criado_em)
                         VALUES (%s, '2026-11-09', 'Cliente Ficticio', %s) RETURNING id""",
                       (numero, AGORA.isoformat()))[0]['id']
        b.escrever("INSERT INTO cx_protocolo_atos (protocolo_id, descricao, valor_total) VALUES (%s,'Certidao ficticia',%s)",
                   (p, CB.reais(valor_item)))
        i = CB.cadastrar(con, agora=AGORA, por='Atendente Ficticio', banco_codigo=CB.PARCELA,
                         ambiente='sandbox', protocolo_id=p, valor_centavos=12345,
                         vencimento='2026-11-20', pagador={'nome': 'Cliente Ficticio', 'documento': '00000000191',
                         'logradouro': 'Rua Um', 'numero': '1', 'bairro': 'Centro', 'cidade': 'Cidade Exemplo',
                         'uf': 'MA', 'cep': '65000000'}, mensagem='Servico ficticio')
        CB.gravar_resposta(con, i, {'banco_id': 'token-ficticio', 'situacao': CB.RECEBIDA,
                          'valor_recebido': 12345, 'forma_recebida': 'PIX', 'data_pagamento': data,
                          **(resposta or {})},
                          por='automacao', agora=AGORA)
    return i, p


def test_sem_gaveta_aberta_recebimento_entra_uma_vez_e_quita_protocolo(cg_casa_logada):
    db = cg_casa_logada['db']
    i, pid = _recebimento(db, data='2026-11-08')
    with db.transaction() as con:
        CB.gravar_resposta(con, i, {'situacao': CB.RECEBIDA}, por='automacao', agora=AGORA)
        assert CB.recolher_no_caixa_geral(con, por='automacao', agora=AGORA) == []
    with db.connect() as con:
        b = banco(con); c = CB.cobranca(con, i)
        dep = b.um('SELECT * FROM cx_depositos WHERE id=%s', (c['deposito_id'],))
        lanc = b.um('SELECT * FROM cx_lancamentos WHERE id=%s', (dep['lancamento_id'],))
        cx = b.um('SELECT * FROM cx_caixas WHERE id=%s', (lanc['caixa_id'],))
        assert c['situacao'] == CB.LANCADA and cx['operador_nome'] == CB.OPERADOR_DO_CAIXA_BANCARIO
        assert dep['data'] == '2026-11-08' and lanc['data'] == '2026-11-09'
        assert b.valor('SELECT count(*) FROM cx_depositos WHERE protocolo_id=%s', (pid,)) == 1
        assert b.valor('SELECT count(*) FROM cx_lancamentos WHERE protocolo_id=%s', (pid,)) == 1
        assert b.valor('SELECT situacao FROM cx_protocolos WHERE id=%s', (pid,)) == 'PAGO'
        assert b.valor('SELECT count(*) FROM cx_deposito_usos WHERE deposito_id=%s', (dep['id'],)) == 1
    html = cg_casa_logada['c'].get('/caixa/recebimentos-bancarios?dia=2026-11-09')
    assert html.status_code == 200 and b'2026-11-08' in html.data and b'123,45' in html.data


def test_mesmo_recebimento_em_outra_cobranca_nao_duplica_dinheiro(cg_casa_logada):
    db = cg_casa_logada['db']
    _recebimento(db)
    i, pid = _recebimento(db, numero='2026.11.99998')
    with db.connect() as con:
        assert CB.cobranca(con, i)['situacao'] == CB.RECEBIDA
        assert banco(con).valor('SELECT count(*) FROM cx_depositos WHERE protocolo_id=%s', (pid,)) == 0


@pytest.mark.parametrize('resposta', [{'forma_recebida': 'DESCONHECIDA'}, {'data_pagamento': 'invalida'}])
def test_dados_incompletos_nao_inventam_forma_ou_data_e_rodada_consulta_de_novo(cg_casa_logada, monkeypatch, tmp_path, resposta):
    from types import SimpleNamespace
    db = cg_casa_logada['db']
    i, pid = _recebimento(db, resposta=resposta)
    with db.connect() as con:
        assert CB.cobranca(con, i)['situacao'] == CB.RECEBIDA
        assert i in [c['id'] for c in CB.para_acompanhar(con, banco_codigo=CB.PARCELA, ambiente='sandbox')]
    cliente = SimpleNamespace(banco=CB.PARCELA, ambiente='sandbox', fornece_pdf=False,
                              consultar=lambda c: {'situacao': CB.RECEBIDA, 'forma_recebida': 'PIX',
                                                   'data_pagamento': '2026-11-09', 'valor_recebido': 12345})
    monkeypatch.setattr(CBB, 'cliente_da_casa', lambda *a, **kw: cliente)
    r = CA.acompanhar(SimpleNamespace(db=db, agora=AGORA, pasta_dados=tmp_path, processo={'pode_agir': 1}))
    assert r['situacao'] == 'OK'
    with db.connect() as con:
        assert CB.cobranca(con, i)['situacao'] == CB.LANCADA
        assert banco(con).valor('SELECT count(*) FROM cx_depositos WHERE protocolo_id=%s', (pid,)) == 1


def test_duas_confirmacoes_concorrentes_so_criam_uma_entrada(cg_casa_logada, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    db = cg_casa_logada['db']; entrar = CB.entrar_no_caixa_geral
    with monkeypatch.context() as m:
        m.setattr(CB, 'entrar_no_caixa_geral', lambda *a, **kw: None)
        i, pid = _recebimento(db)
    barreira = Barrier(2)
    def confirmar(_):
        barreira.wait(timeout=15)
        with db.transaction() as con:
            return entrar(con, i, por='automacao', agora=AGORA)
    with ThreadPoolExecutor(max_workers=2) as pool:
        feitos = list(pool.map(confirmar, range(2)))
    assert sum(f is not None for f in feitos) == 1
    with db.connect() as con:
        assert banco(con).valor('SELECT count(*) FROM cx_depositos WHERE protocolo_id=%s', (pid,)) == 1


def test_preco_alterado_preserva_credito_sem_quitar_itens_errados(cg_casa_logada):
    db = cg_casa_logada['db']; i, pid = _recebimento(db, valor_item=13000)
    with db.connect() as con:
        b = banco(con)
        assert CB.cobranca(con, i)['situacao'] == CB.LANCADA
        assert b.valor('SELECT coalesce(quitado,0) FROM cx_protocolo_atos WHERE protocolo_id=%s', (pid,)) == 0
        assert CB.centavos_do_banco('123.45') == 12345


def test_caixa_bancario_fechado_nao_reabre_nem_perde_confirmacao(cg_casa_logada):
    db = cg_casa_logada['db']
    with db.transaction() as con:
        banco(con).escrever("INSERT INTO cx_caixas (data,operador_nome,aberto_em,situacao) VALUES (%s,%s,%s,'FECHADO')",
                           ('2026-11-09', CB.OPERADOR_DO_CAIXA_BANCARIO, AGORA.isoformat()))
    i, pid = _recebimento(db)
    with db.connect() as con:
        assert CB.cobranca(con, i)['situacao'] == CB.RECEBIDA
        assert banco(con).valor('SELECT count(*) FROM cx_depositos WHERE protocolo_id=%s', (pid,)) == 0
    with db.transaction() as con:
        assert len(CB.recolher_no_caixa_geral(con, por='automacao', agora=AGORA+timedelta(days=1))) == 1


def test_falha_na_aplicacao_desfaz_toda_entrada(cg_casa_logada, monkeypatch):
    import caixa_depositos as DEP
    db = cg_casa_logada['db']
    def falhar(*a, **kw):
        raise RuntimeError('Falha simulada depois do deposito')
    monkeypatch.setattr(DEP, 'quitar_itens_com_o_deposito', falhar)
    with pytest.raises(RuntimeError):
        _recebimento(db)
    with db.connect() as con:
        assert banco(con).valor('SELECT count(*) FROM cb_cobrancas') == 0
        assert banco(con).valor('SELECT count(*) FROM cx_depositos') == 0


def test_autorizacao_antiga_e_aceite_posterior_nao_enviam_dinheiro(casa):
    db = casa['db']; i = _cadastrar(db)
    with db.transaction() as con:
        banco(con).escrever("UPDATE dp_despesas SET situacao='AUTORIZADA',recebedor_aceito_em=%s WHERE id=%s", (AGORA.isoformat(), i))
    r = INTER.pagar(db, i, cliente=casa['cliente'], por='automacao', agora=AGORA)
    assert r['situacao'] == DP.AUTORIZADA and 'bloqueado' in r['mensagem']
    assert casa['inter'].chamadas == [] and _d(db, i)['tentativas'] == 0


@pytest.mark.parametrize('nome,doc', [('OUTRO FAVORECIDO', '00000010000127'),
                                    ('FORNECEDOR FICTICIO', '00000000191')])
def test_divergencia_exige_marca_e_motivo_antes_do_post(casa, nome, doc):
    db = casa['db']; i = _cadastrar(db)
    dados = {'nome': nome, 'documento': doc, 'ciencia': True, 'evidencia': 'Consulta ficticia no banco'}
    for extras in ({}, {'autoriza_divergencia': True, 'motivo': 'x'}, {'motivo': 'Motivo ficticio suficiente'}):
        with pytest.raises(DP.DespesaError, match='expressa'):
            _autorizar(db, i, recebedor_previo={**dados, **extras})
        assert _d(db, i)['situacao'] == DP.AGUARDANDO
    _autorizar(db, i, recebedor_previo={**dados, 'autoriza_divergencia': True, 'motivo': 'Justificativa ficticia conferida'})
    r = INTER.pagar(db, i, cliente=casa['cliente'], por='automacao', agora=AGORA)
    assert r['situacao'] == DP.ENVIADA
    assert casa['inter'].posts('/banking/v2/pagamento')[0]['json']['cpfCnpjBeneficiario'] == doc
    with db.connect() as con:
        assert banco(con).valor("SELECT count(*) FROM dp_eventos WHERE despesa_id=%s AND operacao='AUTORIZAR_DESTINATARIO' AND resultado='expressa'", (i,)) == 1


@pytest.mark.parametrize('campo,novo', [('valor', 999), ('codigo', 'outro'), ('beneficiario_nome', 'outro'), ('beneficiario_documento', '00000000191')])
def test_mudanca_no_destino_ou_valor_invalida_autorizacao(casa, campo, novo):
    db = casa['db']; i = _cadastrar(db); _autorizar(db, i)
    with db.transaction() as con:
        banco(con).escrever(f'UPDATE dp_despesas SET {campo}=%s WHERE id=%s', (novo, i))
    INTER.pagar(db, i, cliente=casa['cliente'], por='automacao', agora=AGORA)
    assert casa['inter'].chamadas == []


def test_envio_direto_interno_sem_autorizacao_tambem_e_bloqueado(casa):
    i = _cadastrar(casa['db'])
    INTER._enviar(casa['db'], _d(casa['db'], i), cliente=casa['cliente'], por='automacao', hoje='2026-11-09')
    assert casa['inter'].chamadas == []


def test_destinatario_previamente_aprovado_nao_exige_aceite_posterior(casa):
    db = casa['db']; i = _cadastrar(db)
    dados = {'nome': 'OUTRO DESTINATARIO FICTICIO', 'documento': '00000000191',
             'evidencia': 'Consulta ficticia no banco', 'ciencia': True,
             'autoriza_divergencia': True, 'motivo': 'Justificativa ficticia do ordenador'}
    _autorizar(db, i, recebedor_previo=dados)
    INTER.pagar(db, i, cliente=casa['cliente'], por='automacao', agora=AGORA)
    with db.transaction() as con:
        b = banco(con); d = DP.despesa(con, i)
        assert not INTER._anotar_recebedor(b, d, dados['nome'], dados['documento'], por='automacao', quando=AGORA)
        assert INTER._anotar_recebedor(b, d, 'TERCEIRO FICTICIO', '00000000272', por='automacao', quando=AGORA)


def test_tela_e_post_sem_conferencia_nao_autorizam(casa):
    db = casa['db']; i = _cadastrar(db); c = casa['c']
    html = c.get(f'/administrativo/despesas/{i}').get_data(as_text=True)
    assert 'Nome apresentado pelo banco' in html and 'Autorizo expressamente' in html
    campos = {n: v for n, v in re.findall(r'name="([^"]+)"[^>]*value="([^"]*)"', html)}
    r = c.post(f'/administrativo/despesas/{i}/autorizar', data=campos, follow_redirects=True)
    assert r.status_code == 200 and _d(db, i)['situacao'] == DP.AGUARDANDO
    assert casa['inter'].chamadas == []

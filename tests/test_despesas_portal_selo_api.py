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
from tests.test_despesas_portal_selo_unidade import texto, pdf_original, pix, CHAVE_DO_FUNDO, DOMINIO_DO_QR, CIDADE_DO_QR

BASE = '/administrativo/despesas/portal-selo'


def _post(c, fundo='FERJ', *, pdf=None, **extras):
    dados = {'csrf_token': _token(c, BASE),
             'documento': (io.BytesIO(pdf or pdf_original(fundo)), 'guia.pdf'), **extras}
    return c.post(BASE, data=dados, headers={'Accept': 'application/json'})


def _recebedores(db, ferj=CHAVE_DO_FUNDO, ferc=CHAVE_DO_FUNDO, cidade=CIDADE_DO_QR):
    with db.transaction() as con:
        DP.gravar_configuracao(con, {**DP.configuracao(con), 'despesas_pix_ferj': ferj,
                                     'despesas_pix_ferc': ferc, 'despesas_pix_cidade': cidade})


def test_conferir_nao_cadastra_e_commit_e_idempotente_com_anexo(cg_casa_logada):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _recebedores(db)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        lido = _post(c, conferir='1', valor_esperado_centavos='999999').get_json()
        assert lido['valor_esperado_centavos'] == 12345  # o cliente não decide a conferência
        assert 'codigo' not in lido and 'beneficiario_documento' not in lido and 'pix' not in lido
        assert lido['tem_pix'] and lido['pix_conferido'] and not lido['motivo_pix']
        a, b = _post(c).get_json(), _post(c).get_json()
    assert a['id'] == b['id'] and a['novo'] and not b['novo']
    with db.connect() as con:
        d = DP.despesa(con, a['id'])
        assert d['situacao'] == DP.AUTORIZADA
        assert (d['forma'], d['codigo'], d['codigo_barras']) == (DP.PIX_COPIA_E_COLA, pix(), '')
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
                                     'despesas_ambiente': 'sandbox',
                                     'despesas_pix_ferj': CHAVE_DO_FUNDO,
                                     'despesas_pix_ferc': CHAVE_DO_FUNDO})


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
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        enviado = INTER.pagar(db, r['id'], cliente=cliente, por='automação', agora=datetime(2026, 11, 9))
    assert enviado['situacao'] == DP.ENVIADA
    # Pelo Pix do QR code da guia, no dia (09/11), e não agendado para o vencimento (10/11).
    assert falso.posts('/banking/v2/pagamento') == []
    [envio] = falso.posts('/banking/v2/pix')
    assert envio['json']['destinatario'] == {'tipo': 'PIX_COPIA_E_COLA', 'pixCopiaECola': pix()}
    assert envio['json']['valor'] == 123.45 and envio['json']['dataPagamento'] == '2026-11-09'
    with db.connect() as con:
        assert DP.despesa(con, r['id'])['situacao'] == DP.ENVIADA  # pedido não é confirmação


@pytest.mark.parametrize('fundo', ['FADEP', 'FEMP', 'FERRFIS'])
def test_banco_do_brasil_nao_sai_no_inter_mesmo_se_autorizado_a_mao(cg_casa_logada, fundo):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    r = _post(c, fundo).get_json()
    assert r['situacao'] == DP.AGUARDANDO and not r['envio_solicitado']
    with db.transaction() as con:
        DP.autorizar(con, r['id'], agora=datetime(2026, 11, 9), por='mario', papel='ADMIN',
                     recebedor_previo={'nome': PS.ler_texto(texto(fundo))['beneficiario_nome'],
                                      'documento': '00000010000127', 'ciencia': True,
                                      'evidencia': 'Conferência fictícia no banco de teste'})
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


@pytest.mark.parametrize('mudanca', [
    {'origem': 'MANUAL'}, {'valor_esperado': 1}, {'autorizada_pela_regra': ''},
    {'beneficiario_documento': '00000000191'}, {'beneficiario_nome': 'Carla Exemplo'},
    {'chave_origem': 'outra-guia'}, {'documento_numero': 'outra-guia'}, {'codigo': 'outro'},
])
def test_excecao_nao_cobre_cadastro_manual_ou_guia_alterada(cg_casa_logada, mudanca):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        r = _post(c).get_json()
        with db.transaction() as con:
            # Campos fixos da parametrização; nunca entrada da API.
            for campo, valor in mudanca.items():
                banco(con).escrever(f'UPDATE dp_despesas SET {campo}=%s WHERE id=%s', (valor, r['id']))
        falso = InterFalso()
        resultado = INTER.pagar(db, r['id'], cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                                por='automação', agora=datetime(2026, 11, 9))
    assert resultado['situacao'] == DP.AUTORIZADA
    assert falso.chamadas == []


@pytest.mark.parametrize('defeito', ['ausente', 'alterado', 'sem_base', 'divergente', 'teto_guia', 'teto_pagamento', 'teto_dia'])
def test_antes_do_banco_reconfere_original_base_e_tetos(cg_casa_logada, defeito):
    from pathlib import Path
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        r = _post(c).get_json()
    with db.transaction() as con:
        if defeito in ('ausente', 'alterado'):
            arquivo = Path(DP.anexos(con, r['id'])[0]['stored_path'])
            if defeito == 'ausente':
                arquivo.unlink()
            else:
                arquivo.write_bytes(b'%PDF-alterado')
        if defeito.startswith('teto_'):
            campo = {'teto_guia': 'despesas_teto_guia', 'teto_pagamento': 'despesas_teto_por_pagamento',
                     'teto_dia': 'despesas_teto_por_dia'}[defeito]
            DP.gravar_configuracao(con, {**DP.configuracao(con), campo: '1,00'})
    esperado = None if defeito == 'sem_base' else 12344 if defeito == 'divergente' else 12345
    falso = InterFalso()
    with patch.object(PS, 'esperado_dos_selos', return_value=esperado):
        resultado = INTER.pagar(db, r['id'], cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                                por='automação', agora=datetime(2026, 11, 9))
    assert resultado['situacao'] == DP.AUTORIZADA
    assert falso.chamadas == []


def test_cadastro_manual_recebe_pdf_sem_autorizacao_e_sem_duplicar_anexo(cg_casa_logada):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        r = _post(c).get_json()
        with db.transaction() as con:
            banco(con).escrever("UPDATE dp_despesas SET situacao=%s, origem='MANUAL', autorizada_por=NULL, "
                                "autorizada_em=NULL, autorizada_pela_regra='' WHERE id=%s", (DP.AGUARDANDO, r['id']))
            banco(con).escrever("DELETE FROM attachments WHERE entity_type='DESPESA' AND entity_id=%s", (r['id'],))
        with patch('automacao.pedir_rodada') as pedir:
            for _ in range(2):
                retomada = _post(c).get_json()
                assert retomada['id'] == r['id'] and not retomada['novo']
                assert retomada['situacao'] == DP.AGUARDANDO and not retomada['envio_solicitado']
            pedir.assert_not_called()
    with db.connect() as con:
        assert len(DP.anexos(con, r['id'])) == 1
        assert banco(con).valor('SELECT count(*) FROM dp_despesas') == 1


def test_pdf_alterado_entre_preparar_e_enviar_falha_sem_contato_bancario(cg_casa_logada):
    from pathlib import Path
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    enviar = INTER._enviar
    def alterar_antes_do_post(db, d, **kw):
        with db.connect() as con:
            Path(DP.anexos(con, d['id'])[0]['stored_path']).write_bytes(b'%PDF-alterado')
        return enviar(db, d, **kw)
    falso = InterFalso()
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        r = _post(c).get_json()
        with patch.object(INTER, '_enviar', side_effect=alterar_antes_do_post):
            resultado = INTER.pagar(db, r['id'], cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                                    por='automação', agora=datetime(2026, 11, 9))
    assert resultado['situacao'] == DP.FALHOU
    assert falso.chamadas == []
    with db.connect() as con:
        assert DP.despesa(con, r['id'])['banco_status'] == 'BLOQUEADO_ANTES_DO_ENVIO'


def test_excecao_nao_permite_enviar_sem_passar_pela_preparacao_e_tetos(cg_casa_logada):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    falso = InterFalso()
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        r = _post(c).get_json()
        with db.connect() as con:
            d = DP.despesa(con, r['id'])
        INTER._enviar(db, d, cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                       por='automação', hoje='2026-11-09')
    assert falso.chamadas == []


# --- O Pix do QR code da guia (FERJ/FERC, 10/11/2026) -------------------------------

@pytest.mark.parametrize('caso', ['sem_qr', 'outra_chave', 'sem_recebedor_conferido', 'dinamico_outro_dominio',
                                  'dinamico_outra_conta'])
def test_pix_sem_recebedor_conferido_espera_o_oficial_e_nao_vai_ao_banco(cg_casa_logada, caso):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    pdf = {'sem_qr': pdf_original('FERJ', None),
           'outra_chave': pdf_original('FERJ', pix(chave='fundo@outro.test')),
           'sem_recebedor_conferido': pdf_original('FERJ'),
           'dinamico_outro_dominio': pdf_original('FERJ', pix(valor=None, url='qr.outro-banco.test/cobv/1')),
           'dinamico_outra_conta': pdf_original('FERJ', pix(url=DOMINIO_DO_QR + '/cobv/1', nome='LOJA EXEMPLO',
                                                            cidade=CIDADE_DO_QR)),
           }[caso]
    if caso == 'sem_recebedor_conferido':
        _recebedores(db, ferj='')
    if caso == 'dinamico_outra_conta':   # o domínio do banco confere; o nome não
        _recebedores(db, ferj=DOMINIO_DO_QR)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345), patch('automacao.pedir_rodada') as pedir:
        r = _post(c, pdf=pdf).get_json()
        pedir.assert_not_called()
    assert r['situacao'] == DP.AGUARDANDO and not r['envio_solicitado']
    with db.connect() as con:
        d = DP.despesa(con, r['id'])
    assert d['forma'] == (DP.ARRECADACAO if caso == 'sem_qr' else DP.PIX_COPIA_E_COLA)
    falso = InterFalso()
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        INTER.pagar(db, r['id'], cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                    por='automação', agora=datetime(2026, 11, 9))
    assert falso.chamadas == []


def test_qr_dinamico_do_dominio_conferido_sai_sozinho(cg_casa_logada):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    _recebedores(db, ferj=DOMINIO_DO_QR)
    dinamico = pix(valor=None, url=DOMINIO_DO_QR + '/cobv/guia-ficticia', nome='FERJ', cidade=CIDADE_DO_QR)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345), patch('automacao.pedir_rodada'):
        r = _post(c, pdf=pdf_original('FERJ', dinamico)).get_json()
    assert r['situacao'] == DP.AUTORIZADA
    falso = InterFalso()
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        INTER.pagar(db, r['id'], cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                    por='automação', agora=datetime(2026, 11, 9))
    [envio] = falso.posts('/banking/v2/pix')
    assert envio['json']['destinatario']['pixCopiaECola'] == dinamico
    assert envio['json']['valor'] == 123.45  # o valor da guia, conferido com os selos


@pytest.mark.parametrize('qrs', [(12346,), (None, 'outro')])
def test_guia_com_pix_de_outro_valor_ou_dois_pix_nao_entra(cg_casa_logada, qrs):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    pdf = (pdf_original('FERJ', pix(valor=qrs[0])) if len(qrs) == 1 else
           pdf_original('FERJ', pix(), pix(chave='fundo@outro.test')))
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        r = _post(c, pdf=pdf)
    assert r.status_code == 400
    with db.connect() as con:
        assert banco(con).valor('SELECT count(*) FROM dp_despesas') == 0


def test_recebedor_trocado_depois_do_cadastro_bloqueia_o_envio(cg_casa_logada):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345), patch('automacao.pedir_rodada'):
        r = _post(c).get_json()
    assert r['situacao'] == DP.AUTORIZADA
    _recebedores(db, ferj='fundo@outro.test')
    falso = InterFalso()
    with patch.object(PS, 'esperado_dos_selos', return_value=12345):
        resultado = INTER.pagar(db, r['id'], cliente=INTER.ClienteInter('sandbox', falso, CAMPOS),
                                por='automação', agora=datetime(2026, 11, 9))
    assert resultado['situacao'] == DP.AUTORIZADA and 'bloqueado' in resultado['mensagem']
    assert falso.chamadas == []


def test_pix_sem_resposta_reenvia_uma_vez_com_a_mesma_chave(cg_casa_logada):
    c, db = cg_casa_logada['c'], cg_casa_logada['db']
    _preparar_executor(db)
    falso = InterFalso()
    cliente = INTER.ClienteInter('sandbox', falso, CAMPOS)
    with patch.object(PS, 'esperado_dos_selos', return_value=12345), patch('automacao.pedir_rodada'):
        r = _post(c).get_json()
        falso.perder_resposta = True
        assert INTER.pagar(db, r['id'], cliente=cliente, por='automação',
                           agora=datetime(2026, 11, 9))['situacao'] == DP.ENVIADA
        INTER.atualizar(db, r['id'], cliente=cliente, por='automação', agora=datetime(2026, 11, 9, 1))
    envios = falso.posts('/banking/v2/pix')
    assert len(envios) == 2
    assert envios[0]['cab']['x-id-idempotente'] == envios[1]['cab']['x-id-idempotente']

"""Fontes ficticias: conciliacao nao altera atos, nem compensa diferencas."""
import json
import zipfile
from io import BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

import conferencia_selos as CS
import custas
import despesas as DP
import faturamento_portal as FP
import livro_diario as LD
from bd_nativo import banco
from tests.conftest import cg_login
from tests.test_despesas_fluidez import _token

BASE = '/administrativo/despesas/conferencia'
NUM = 'CERELE0000000000000000000001'


def registro(**kw):
    return {'CNS': '000000', 'NÚMERO DO SELO': NUM, 'DATA DA SELAGEM': '2026-10-05',
            'ATO': '16.24.4.1', 'QTDE.': '17', 'CANCELADO': 'Não', 'ISENTO': 'Não',
            'GRATUITO': 'Não', 'DIFERIDO': 'Não', 'EMOLUMENTO': '154.02', 'FERJ': '18.53', **kw}


def arquivo(registros=None, periodo='01/10/2026 até 31/10/2026'):
    registros = [registro()] if registros is None else registros
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheet = Element('worksheet', xmlns=ns)
    # A dimensao incorreta do exportador nao pode esconder linhas.
    SubElement(sheet, 'dimension', ref='A1:A1')
    data = SubElement(sheet, 'sheetData')
    headers = list(registro())
    rows = [['RELATÓRIO DE FISCALIZAÇÃO DE SELOS'], ['Período: ' + periodo], headers]
    rows += [[r[n] for n in headers] for r in registros]
    for i, values in enumerate(rows, 1):
        row = SubElement(data, 'row', r=str(i))
        for j, v in enumerate(values):
            cell = SubElement(row, 'c', r=f'{chr(65+j)}{i}', t='inlineStr')
            SubElement(SubElement(cell, 'is'), 't').text = str(v)
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('xl/worksheets/sheet1.xml', tostring(sheet))
    return buf.getvalue()


def inserir(casa, *, numero=NUM, quantidade=None, cancelado=None, emol='154,02', marca='', dia='2026-10-05'):
    with casa['db'].transaction() as con:
        return banco(con).escrever('''INSERT INTO sd_selos(numero,texto,ambiente,obtido_em,usado_em,quantidade,cancelado_em)
            VALUES(%s,%s,'PRODUCAO',%s,%s,%s,%s) RETURNING id''',
            (numero, f'Ato: 16.24.4.1, Total R$ {emol} Emol R$ {emol} {marca}', dia, dia, quantidade, cancelado))[0]['id']


def importar(casa, dados=None):
    with casa['db'].transaction() as con:
        uid = banco(con).valor("SELECT id FROM users WHERE username='mario'")
        return CS.registrar(con, arquivo() if dados is None else dados, cns='000000',
                            pasta=casa['acervo']/'analiticos', usuario_id=uid, por='mario', agora='2026-11-04T12:00:00')


def conferir(casa):
    with casa['db'].connect() as con:
        return CS.conferir(con, '2026-10', cns='000000')


def aplicar(casa, q, motivo='Conferido com o relatorio oficial'):
    with casa['db'].transaction() as con:
        uid = banco(con).valor("SELECT id FROM users WHERE username='mario'")
        return CS.aplicar_quantidades(con, '2026-10', cns='000000', revisao=q['revisao'], motivo=motivo,
                                      usuario_id=uid, agora='2026-11-04T13:00:00')


def test_ler_mes_completo_quantidade_flags_e_dimensao_incorreta():
    r = CS.ler(arquivo(), cns='000000')
    assert r['competencia'] == '2026-10' and r['registros'][0]['quantidade'] == 17
    assert r['registros'][0]['ferj'] == 1853


@pytest.mark.parametrize('kw', [
    {'CNS': '999998'}, {'NÚMERO DO SELO': 'CERTID9999980000000000000001'},
    {'NÚMERO DO SELO': 'codigo-invalido'}, {'DATA DA SELAGEM': '2026-11-01'},
    {'DATA DA SELAGEM': 'NaN'}, {'QTDE.': '0'}, {'QTDE.': '1.5'}, {'QTDE.': 'Infinity'},
    {'CANCELADO': ''}, {'ISENTO': 'talvez'}, {'EMOLUMENTO': ''}, {'FERJ': '155.00'},
])
def test_rejeita_dados_ambiguos_ou_de_outra_serventia(kw):
    with pytest.raises(DP.DespesaError):
        CS.ler(arquivo([registro(**kw)]), cns='000000')


def test_rejeita_repeticao_mes_parcial_e_analitico_vazio():
    for dados in (arquivo([registro(), registro()]), arquivo(periodo='02/10/2026 até 31/10/2026'), arquivo([])):
        with pytest.raises(DP.DespesaError):
            CS.ler(dados, cns='000000')


def test_data_excel_com_hora_e_flags_com_espacos():
    r = CS.ler(arquivo([registro(**{'DATA DA SELAGEM': '46300.75', 'GRATUITO': ' Sim '})]), cns='000000')
    assert r['registros'][0]['gratuito'] and r['registros'][0]['dia'].startswith('2026-10')


@pytest.mark.parametrize('emol,q,esperado', [(15402, 17, 1853), (1238, 2, 148), (15403, 17, 1848), (10000, None, 1200)])
def test_ferj_por_unidade_quando_base_exata_sem_inventar_centavos(emol, q, esperado):
    assert custas.ferj_do_emolumento(emol, 1200, quantidade=q) == esperado


def test_importacao_idempotente_preserva_original_e_nao_corrige_cadastro(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa)
    dados = arquivo()
    a = importar(casa, dados)
    assert importar(casa, dados) == a
    with casa['db'].connect() as con:
        assert banco(con).valor('SELECT quantidade FROM sd_selos WHERE numero=%s', (NUM,)) is None
        assert banco(con).valor('SELECT count(*) FROM sd_selos') == 1
        assert banco(con).valor("SELECT count(*) FROM audit_logs WHERE action='CONFERENCIA_SELOS_IMPORTADA'") == 1
    assert CS.Path(a['fonte']).read_bytes() == dados


def test_quantidade_verificada_corrige_ferj_sem_alterar_emol_ou_cancelar(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa)
    importar(casa)
    q = conferir(casa)
    assert q['contagens']['arredondamento_ferj'] == 1 and len(q['candidatos']) == 1
    with casa['db'].connect() as con:
        assert LD.apurar(con, '2026-10')['fundos']['FERJ'] == 1848
    assert aplicar(casa, q) == 1
    with casa['db'].connect() as con:
        livro = LD.apurar(con, '2026-10')
        assert livro['receita_bruta'] == 15402 and livro['fundos']['FERJ'] == 1853
        assert banco(con).valor('SELECT cancelado_em FROM sd_selos WHERE numero=%s', (NUM,)) is None
        a = json.loads(banco(con).valor("SELECT details FROM audit_logs WHERE action='CONFERENCIA_SELOS_QUANTIDADES'"))
        assert a['alteracoes'][0]['ferj_antes'] == 1848 and a['alteracoes'][0]['ferj_depois'] == 1853
    assert not conferir(casa)['diferencas']


def test_versao_gerada_preservada_ao_completar_quantidade(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa)
    importar(casa)
    with casa['db'].transaction() as con:
        g = LD.gerar(con, '2026-10', hoje='2026-11-04', agora='2026-11-04T12:00:00', por='mario')
    aplicar(casa, conferir(casa))
    with casa['db'].connect() as con:
        assert LD.geracao(con, g['id'])['livro']['fundos']['FERJ'] == 1848
        assert LD.situacao_do_mes(con, '2026-10', hoje='2026-11-04')['movimento_mudou']


def test_estado_mudou_recusa_formulario_antigo(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa)
    importar(casa)
    q = conferir(casa)
    with casa['db'].transaction() as con:
        banco(con).escrever('UPDATE sd_selos SET cancelado_em=%s WHERE numero=%s', ('2026-11-04', NUM))
    with pytest.raises(DP.DespesaError, match='mudou'):
        aplicar(casa, q)


def test_conflitos_nao_sao_completados_nem_compensados(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa, cancelado='2026-10-05')
    importar(casa)
    q = conferir(casa)
    assert q['contagens']['cancelamento'] == 1 and not q['candidatos'] and not q['conferido']


def test_cancelamento_vazio_tem_a_mesma_regua_no_razao_e_no_livro(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa, cancelado='  ', quantidade=17)
    importar(casa)
    q = conferir(casa)
    assert q['contagens']['cancelamento'] == 0
    with casa['db'].connect() as con:
        assert LD.apurar(con, '2026-10')['receita_bruta'] == 15402


def test_gratuito_no_portal_equivale_a_marca_local_isento(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa, quantidade=17, marca='Selo Isento')
    importar(casa, arquivo([registro(GRATUITO='Sim')]))
    q = conferir(casa)
    assert q['contagens']['gratuidade'] == 0 and q['totais']['bruto'] == 0


def test_residuo_entre_relatorios_fica_visivel_e_impede_status_conferido(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa, quantidade=17)
    importar(casa)
    with casa['db'].transaction() as con:
        ref = {'bruto': 15402, 'ferj': 1852, 'liquido': 13550, 'atos': 1, 'cancelados': 0}
        banco(con).escrever('INSERT INTO settings(key,value) VALUES(%s,%s)', (FP._chave('2026-10', '000000'), json.dumps(ref)))
    q = conferir(casa)
    assert not q['diferencas'] and q['diferenca_relatorios']['liquido'] == 1 and not q['conferido']
    with casa['db'].transaction() as con:
        ref.update(ferj=1853, liquido=13549)
        banco(con).escrever('UPDATE settings SET value=%s WHERE key=%s', (json.dumps(ref), FP._chave('2026-10', '000000')))
    assert conferir(casa)['conferido']


def test_rollback_se_auditoria_da_quantidade_falhar(cg_casa_logada, monkeypatch):
    casa = cg_casa_logada
    inserir(casa)
    importar(casa)
    q = conferir(casa)
    def falhar(*a, **kw):
        raise RuntimeError('auditoria indisponivel')
    monkeypatch.setattr(CS.IDR, 'registrar', falhar)
    with pytest.raises(RuntimeError):
        aplicar(casa, q)
    with casa['db'].connect() as con:
        assert banco(con).valor('SELECT quantidade FROM sd_selos WHERE numero=%s', (NUM,)) is None


def test_importacao_falha_sem_auditoria_e_preserva_referencia_anterior(cg_casa_logada, monkeypatch):
    casa = cg_casa_logada
    antes = importar(casa)
    def falhar(*a, **kw):
        raise RuntimeError('auditoria indisponivel')
    monkeypatch.setattr(CS.IDR, 'registrar', falhar)
    with pytest.raises(RuntimeError):
        importar(casa, arquivo([registro(CANCELADO='Sim')]))
    with casa['db'].connect() as con:
        assert CS.referencia(con, '2026-10', cns='000000')['sha256'] == antes['sha256']


def test_tela_upload_csrf_permissoes_e_confirmacao(cg_casa_logada):
    casa = cg_casa_logada
    inserir(casa)
    c = casa['c']
    assert c.post(BASE+'/importar', data={'analitico': (BytesIO(arquivo()), 'ficticio.xlsx')}).status_code == 400
    r = c.post(BASE+'/importar', data={'csrf_token': _token(c, BASE), 'analitico': (BytesIO(arquivo()), 'ficticio.xlsx')}, follow_redirects=True)
    assert r.status_code == 200 and 'arredondamento por unidade' in r.get_data(as_text=True)
    q = conferir(casa)
    c.post(BASE+'/quantidades', data={'csrf_token': _token(c, BASE), 'mes': '2026-10', 'revisao': q['revisao'], 'motivo': 'Conferencia ficticia'})
    assert conferir(casa)['candidatos']
    casa['db'].create_user('gerente', 'GERENTE EXEMPLO', 'Senha#12345', 'MANAGER')
    outro = casa['app'].test_client()
    cg_login(outro, 'gerente', 'Senha#12345')
    assert outro.get(BASE).status_code == 403
    assert outro.post(BASE+'/quantidades', data={'csrf_token': _token(outro, '/administrativo/despesas/nova')}).status_code == 403

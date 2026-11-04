"""Referencia oficial por mes, sem alterar a escrituracao nem calcular receita ficticia."""
import json
import zipfile
from io import BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

import despesas as DP
import faturamento_portal as FP
from bd_nativo import banco
from tests.conftest import cg_login
from tests.test_despesas_fluidez import BASE, _token


def relatorio(*,cns='000000',periodo='01/10/2026 até 31/10/2026',bruto='12345.00',ferj='1481.40',faturamento='12345.00',protesto='0'):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheet=Element('worksheet',xmlns=ns); data=SubElement(sheet,'sheetData')
    linhas=[['RELATÓRIO DE FATURAMENTO DAS SERVENTIAS'],['Período: '+periodo],
        ['CNS','Qtde. Atos','Qtde. Cancelados','EMOLUMENTO (A)','RECOLHIMENTO DE PROTESTO DIFERIDO (B)','FATURAMENTO (A+B)','FERJ'],
        [cns,'100','2',bruto,protesto,faturamento,ferj]]
    for i,values in enumerate(linhas,1):
        row=SubElement(data,'row',r=str(i))
        for j,v in enumerate(values):
            cell=SubElement(row,'c',r=f'{chr(65+j)}{i}',t='inlineStr')
            SubElement(SubElement(cell,'is'),'t').text=v
    buf=BytesIO()
    with zipfile.ZipFile(buf,'w') as z: z.writestr('xl/worksheets/sheet1.xml',tostring(sheet))
    return buf.getvalue()


def test_ler_conserva_bruto_ferj_liquido_e_periodo():
    r=FP.ler(relatorio(),cns='000000')
    assert (r['bruto'],r['ferj'],r['liquido'])==(1234500,148140,1086360)
    assert (r['competencia'],r['atos'],r['cancelados'])==('2026-10',100,2)


def test_emolumentos_menos_ferj_nao_incluem_protesto_diferido():
    r=FP.ler(relatorio(protesto='100.00',faturamento='12445.00'),cns='000000')
    assert r['faturamento']==1244500 and r['liquido']==1086360


@pytest.mark.parametrize('kw',[
    {'cns':'000001'},{'periodo':'02/10/2026 até 31/10/2026'},
    {'periodo':'01/10/2026 até 30/10/2026'}, {'ferj':''},
    {'ferj':'99999.00'},{'bruto':'NaN'},{'faturamento':'100.00'},
])
def test_recusa_outro_cartorio_mes_incompleto_valor_ausente_ou_total_inconsistente(kw):
    with pytest.raises(DP.DespesaError): FP.ler(relatorio(**kw),cns='000000')


def test_recusa_arquivo_ilegivel_zip_excessivo_e_xml_com_entidade():
    buf=BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('xl/worksheets/sheet1.xml',b'<!DOCTYPE a [<!ENTITY x "teste">]><a>&x;</a>')
    for dados in (b'nao e XLSX',buf.getvalue(),b'x'*(FP.MAX_BYTES+1)):
        with pytest.raises(DP.DespesaError): FP.ler(dados,cns='000000')


def _registrar(casa,conteudo):
    with casa['db'].transaction() as con:
        uid=banco(con).um("SELECT id FROM users WHERE username='mario'")['id']
        return FP.registrar(con,conteudo,cns='000000',pasta=casa['acervo']/'faturamento_portal',
            por='mario',usuario_id=uid,agora='2026-11-04T10:00:00')


def test_importa_idempotente_com_auditoria_sem_criar_selos_ou_receitas(cg_casa_logada):
    casa=cg_casa_logada; db=casa['db']
    with db.connect() as con:
        antes=[banco(con).valor(f'SELECT count(*) FROM {t}') for t in ('sd_selos','cx_lancamentos','cl_lancamentos')]
    conteudo=relatorio()
    primeiro=_registrar(casa,conteudo); segundo=_registrar(casa,conteudo)
    assert primeiro==segundo and primeiro['liquido']==1086360
    with db.connect() as con:
        assert FP.referencia(con,'2026-10',cns='000000')==primeiro
        depois=[banco(con).valor(f'SELECT count(*) FROM {t}') for t in ('sd_selos','cx_lancamentos','cl_lancamentos')]
        assert depois==antes
        a=banco(con).ler("SELECT details FROM audit_logs WHERE action='FATURAMENTO_PORTAL_IMPORTADO'")
        assert len(a)==1 and json.loads(a[0]['details'])['depois']['sha256']==primeiro['sha256']
        c=FP.conferencia(con,'2026-10',cns='000000')
        assert c['local_bruto']==0 and c['diferenca_bruto']==1234500


def test_falha_da_auditoria_reverte_a_referencia(cg_casa_logada,monkeypatch):
    def falhar(*a,**kw): raise RuntimeError('auditoria indisponivel')
    monkeypatch.setattr(FP.IDR,'registrar',falhar)
    with pytest.raises(RuntimeError): _registrar(cg_casa_logada,relatorio())
    with cg_casa_logada['db'].connect() as con:
        assert FP.referencia(con,'2026-10',cns='000000') is None


def test_tela_importa_com_csrf_titular_e_guarda_mes_do_relatorio(cg_casa_logada):
    casa=cg_casa_logada; c=casa['c']; db=casa['db']
    dados={'csrf_token':_token(c,BASE),'relatorio':(BytesIO(relatorio()),'faturamento-ficticio.xlsx')}
    r=c.post(BASE+'/faturamento-portal',data=dados,follow_redirects=True)
    assert r.status_code==200 and '10.863,60' in r.get_data(as_text=True)
    with db.connect() as con: assert FP.referencia(con,'2026-10',cns='000000')['bruto']==1234500
    db.create_user('balcao','BALCAO EXEMPLO','Senha#12345','USER')
    outro=casa['app'].test_client(); cg_login(outro,'balcao','Senha#12345')
    assert outro.post(BASE+'/faturamento-portal',data={'csrf_token':_token(outro,BASE+'/nova')}).status_code==403

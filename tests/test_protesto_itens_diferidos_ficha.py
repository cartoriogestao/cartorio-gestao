"""Item de faixa selecionavel e emolumento diferido sem caixa aberto."""
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from werkzeug.datastructures import MultiDict
from test_protesto_a_protestar_web import s, intimado, _con, _token


def quadro(*, diferir=False, caixa=None, faixa=False, form=None):
    env=Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent/'templates')),autoescape=True)
    env.filters['centavos_reais']=lambda v:f'{v/100:.2f}'
    item={'codigo_tj':'17.1','servico':901,'descricao':'Item de teste','preco':None if faixa else 1200,'vezes':1}
    if faixa:item['faixas']=[{'servico':902,'codigo_tj':'17.1.3','descricao':'Faixa de teste','preco':1200}]
    r={'itens':[item],'total_centavos':0,'medido_em':'teste','por_faixa':['17.1'] if faixa else []}
    return str(env.get_template('_cobrar.html').module.quadro(r,caixa,form=form,diferir=diferir))


def test_diferido_sem_caixa_permite_marcar_item():
    html=quadro(diferir=True)
    campo=re.search(r'<input[^>]+name="cobrar"[^>]*>',html).group()
    assert 'disabled' not in campo
    assert 'emolumentos a posteriori' in html
    assert 'Você não tem caixa aberto' not in html
    assert 'name="forma_pagamento"' not in html


def test_antecipado_sem_caixa_continua_sem_recebimento():
    html=quadro()
    assert 'disabled' in re.search(r'<input[^>]+name="cobrar"[^>]*>',html).group()
    assert 'Você não tem caixa aberto' in html


def test_faixa_selecionavel_sem_caixa_no_diferido_e_preservada():
    html=quadro(diferir=True,faixa=True,form=MultiDict([('cobrar','902')]))
    assert 'disabled' not in re.search(r'<select[^>]*name="cobrar"[^>]*>',html).group()
    assert re.search(r'<option value="902"[^>]*selected',html)
    assert 'por isso não dá para marcar aqui' not in html


def test_diferido_com_caixa_aberto_nao_oferece_recebimento():
    html=quadro(diferir=True,caixa={'id':1,'data':'2026-11-03'})
    assert 'name="pagador"' not in html
    assert 'name="forma_pagamento"' not in html


def semear(s):
    with _con(s) as con:
        con.execute('UPDATE cx_vigencias SET vigente=0')
        con.execute("INSERT INTO cx_vigencias(codigo,descricao,vigente,inicio) VALUES(990001,'Tabela ficticia',1,'2026-01-01')")
        for codigo,tj,descricao,valor in [(990001,'17.1','Cabecalho ficticio','0,00'),(990002,'17.1.901','Faixa ficticia de teste','12,00')]:
            con.execute('INSERT INTO cx_servicos(codigo,codigo_tj,descricao,ativo) VALUES(?,?,?,1)',(codigo,tj,descricao))
            con.execute("INSERT INTO cx_servico_valores(servico,vigencia,emolumentos,ferc,femp,fadep,ferrfis,total) VALUES(?,990001,?,'0,00','0,00','0,00','0,00',?)",(codigo,valor,valor))


def formulario(html):return re.search(r'<form[^>]*id="lancar-PROTESTO".*?</form>',html,re.S).group()


def test_ficha_diferida_resolve_cabecalho_em_faixa_sem_caixa(s):
    semear(s)
    tid=intimado(s)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    form=formulario(html)
    assert 'value="990002"' in form
    assert 'disabled' not in re.search(r'<select[^>]*name="cobrar"[^>]*>',form).group()
    assert 'emolumentos a posteriori' in form
    assert 'name="forma_pagamento"' not in form


def test_escolha_da_faixa_volta_na_recusa(s,monkeypatch):
    import protesto as PT
    semear(s)
    tid=intimado(s)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    def recusar(*a,**kw):raise PT.ProtestoError('Recusa de teste')
    monkeypatch.setattr(PT,'lancar_protesto',recusar)
    r=s['c'].post(f'/protesto/{tid}/lancar',data={'csrf_token':_token(html),'ato':'PROTESTO','cobrar':'990002'},follow_redirects=True)
    assert r.status_code==200
    assert re.search(r'<option value="990002"[^>]*selected',formulario(r.get_data(as_text=True)))
    with _con(s) as con:
        assert con.execute("SELECT COUNT(*) FROM pt_atos WHERE tipo='PROTESTO'").fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM cx_lancamentos').fetchone()[0]==0


def test_rascunho_com_receita_de_faixa_reabre_sem_erro(s):
    semear(s)
    tid=intimado(s,provado=False)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    r=s['c'].post(f'/protesto/{tid}/preenchimento',data={'csrf_token':_token(html),'ato':'PROTESTO','afirmacao':'Texto ficticio de preparo para conferir os campos desta tela.'},follow_redirects=True)
    assert r.status_code==200 and 'Texto ficticio de preparo' in r.get_data(as_text=True)

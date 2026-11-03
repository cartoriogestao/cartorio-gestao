"""Relato 157: comprovantes na ficha e preenchimento preservado sem lavrar."""
import io
import json
import re
import pytest
from flask import url_for
from test_protesto_a_protestar_web import s, intimado, _con, _token, MOTIVO, atos
import protesto_preparo as PRE
import protesto_aviso as AV
import rascunho_de_tela as RASC

TEXTO = 'O envio foi conferido no comprovante guardado no arquivo da serventia.'
OUTRO = 'A situacao consultada foi conferida com os documentos apresentados neste atendimento.'


def form_protesto(html):
    return re.search(r'<form[^>]*id="lancar-PROTESTO".*?</form>', html, re.S).group()


def salvar(s, tid, **extra):
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    return s['c'].post(f'/protesto/{tid}/preenchimento',
                       data={'csrf_token':_token(html),'ato':'PROTESTO',**extra},follow_redirects=True)


def test_a_ficha_oferece_os_dois_uploads_e_mostra_os_anexos(s):
    tid=intimado(s)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    assert 'data-comprovantes-da-ficha' in html
    assert 'Anexar comprovante do aviso' in html
    assert 'Anexar comprovante da CENPROT' in html
    assert 'comprovante.pdf' in html
    assert f'name="titulo_id" value="{tid}"' in html
    form=form_protesto(html)
    assert 'Salvar preenchimento' in form and 'formnovalidate' in form
    assert f'formaction="/protesto/{tid}/preenchimento"' in form


def test_salvar_nao_lavra_e_ao_reabrir_nao_confirma_por_pessoa(s):
    tid=intimado(s,provado=False)
    r=salvar(s,tid,afirmo='1',afirmacao=TEXTO,motivo_atraso=MOTIVO)
    assert r.status_code==200
    html=r.get_data(as_text=True)
    assert 'Preenchimento salvo' in html
    form=form_protesto(html)
    assert TEXTO in form and MOTIVO in form
    assert re.search(r'name="afirmo"[^>]*checked',form) is None
    assert atos(s,tid)==0
    with _con(s) as con:
        row=con.execute('SELECT * FROM rascunhos_de_tela ORDER BY id DESC LIMIT 1').fetchone()
        dados=json.loads(row['dados_json'])
        assert dados['afirmacao']==TEXTO and 'afirmo' not in dados
        assert con.execute("SELECT COUNT(*) FROM audit_logs WHERE action='AFIRMACAO_EXPRESSA'").fetchone()[0]==0
        assert con.execute("SELECT COUNT(*) FROM audit_logs WHERE action='PROTESTO_PREENCHIMENTO_SALVO'").fetchone()[0]==1
        assert PRE.ler(con,tid,99999) is None


def test_salvar_de_novo_atualiza_o_mesmo_rascunho(s):
    tid=intimado(s,provado=False)
    salvar(s,tid,afirmacao=TEXTO)
    salvar(s,tid,afirmacao=OUTRO)
    with _con(s) as con:
        rows=con.execute('SELECT dados_json FROM rascunhos_de_tela').fetchall()
        assert len(rows)==1 and json.loads(rows[0][0])['afirmacao']==OUTRO


def test_erro_da_prova_preserva_texto_e_caixa_sem_gravar_ato(s,monkeypatch):
    import cenprot_conferencia as CC
    import protesto as PT
    tid=intimado(s,provado=False)
    monkeypatch.setattr(CC,'trava_do_ato',lambda *a,**k:None)
    def recusar(*a,**k):raise PT.ProtestoError('Prova recusada no teste')
    monkeypatch.setattr(PT,'lancar_protesto',recusar)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    r=s['c'].post(f'/protesto/{tid}/lancar',data={'csrf_token':_token(html),'ato':'PROTESTO','motivo_atraso':MOTIVO,'afirmo':'1','afirmacao':TEXTO},follow_redirects=True)
    form=form_protesto(r.get_data(as_text=True))
    assert TEXTO in form and re.search(r'name="afirmo"[^>]*checked',form)
    assert atos(s,tid)==0


def test_recusa_cenprot_preserva_cada_texto_no_seu_campo(s,monkeypatch):
    import cenprot_conferencia as CC
    tid=intimado(s,provado=False)
    monkeypatch.setitem(s['app'].jinja_env.globals,'conferencia_cenprot_da_ficha',lambda t:{'pedido':'123','trava':[],'contraria_o_pago':[],'achados':[],'conferencia':None})
    def recusar(*a,**k):raise CC.ConferenciaError('CENPROT recusou no teste')
    monkeypatch.setattr(CC,'trava_do_ato',recusar)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    r=s['c'].post(f'/protesto/{tid}/lancar',data={'csrf_token':_token(html),'ato':'PROTESTO','motivo_atraso':MOTIVO,'afirmo_prova':'1','afirmacao_prova':TEXTO,'afirmo_cenprot':'1','afirmacao_cenprot':OUTRO},follow_redirects=True)
    form=form_protesto(r.get_data(as_text=True))
    assert TEXTO in re.search(r'<textarea name="afirmacao_prova".*?</textarea>',form,re.S).group()
    assert OUTRO in re.search(r'<textarea name="afirmacao_cenprot".*?</textarea>',form,re.S).group()
    assert re.search(r'name="afirmo_cenprot"[^>]*checked',form)
    assert atos(s,tid)==0


def test_texto_salvo_e_escapado_no_html(s):
    tid=intimado(s,provado=False)
    html=salvar(s,tid,afirmacao='</textarea><script>alert(1)</script>').get_data(as_text=True)
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<script>alert(1)</script>' not in html


def test_robo_nao_salva_afirmacao_em_nome_proprio(s,monkeypatch):
    import selo_robo as SR
    tid=intimado(s)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    monkeypatch.setattr(SR,'usuario_e_robo',lambda *a,**k:True)
    r=s['c'].post(f'/protesto/{tid}/preenchimento',data={'csrf_token':_token(html),'ato':'PROTESTO','afirmacao':TEXTO})
    assert r.status_code==403


def test_upload_do_aviso_volta_para_a_ficha_e_mantem_vinculo(s):
    tid=intimado(s)
    with _con(s) as con:
        aviso=con.execute('SELECT id FROM pt_avisos WHERE titulo_id=?',(tid,)).fetchone()[0]
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    r=s['c'].post(f'/protesto/avisos/{aviso}/comprovante',data={'csrf_token':_token(html),'de':'ficha','comprovante':(io.BytesIO(b'%PDF-1.4 canhoto separado'),'canhoto.pdf')},content_type='multipart/form-data')
    assert r.status_code==302 and r.location.endswith(f'/protesto/{tid}#comprovantes-intimacao')
    with _con(s) as con:
        assert con.execute("SELECT COUNT(*) FROM attachments WHERE entity_type='PT_AVISO' AND entity_id=? AND original_name='canhoto.pdf'",(aviso,)).fetchone()[0]==1
    assert atos(s,tid)==0


def test_upload_cenprot_na_ficha_anexa_ao_dia_correspondente(s):
    tid=intimado(s)
    with _con(s) as con:
        edital=con.execute('SELECT id,publicado_em FROM pt_editais WHERE titulo_id=?',(tid,)).fetchone()
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    r=s['c'].post('/protesto/editais/comprovante-cenprot',data={'csrf_token':_token(html),'titulo_id':str(tid),'dia':edital['publicado_em'],'comprovante':(io.BytesIO(b'%PDF-1.4 envio cenprot separado'),'envio.pdf')},content_type='multipart/form-data')
    assert r.status_code==302 and r.location.endswith(f'/protesto/{tid}#comprovantes-intimacao')
    with _con(s) as con:
        assert con.execute("SELECT COUNT(*) FROM attachments WHERE entity_type='PT_EDITAL_CENPROT' AND entity_id=? AND original_name='envio.pdf'",(edital['id'],)).fetchone()[0]==1
    assert atos(s,tid)==0


def test_upload_cenprot_nao_aceita_dia_de_outro_titulo(s):
    tid=intimado(s)
    html=s['c'].get(f'/protesto/{tid}').get_data(as_text=True)
    r=s['c'].post('/protesto/editais/comprovante-cenprot',data={'csrf_token':_token(html),'titulo_id':str(tid),'dia':'2026-01-02','comprovante':(io.BytesIO(b'%PDF-1.4 envio'),'envio.pdf')},content_type='multipart/form-data')
    assert r.status_code==400


def test_rascunho_tem_link_e_so_o_proprio_preparo_e_concluido(s):
    tid=intimado(s)
    salvar(s,tid,afirmacao=TEXTO)
    with _con(s) as con:
        row=con.execute('SELECT * FROM rascunhos_de_tela').fetchone()
        with s['app'].test_request_context():
            assert RASC.endereco_de_abrir(dict(row),url_for).startswith(f'/protesto/{tid}?')
        uid=int(row['chave'].rsplit(':',1)[1])
        assert PRE.concluir(con,tid,uid,99999,agora='2026-11-03T16:00:00',por='teste',endereco=f'/protesto/{tid}') is None
        assert PRE.concluir(con,tid,uid,row['id'],agora='2026-11-03T16:00:00',por='teste',endereco=f'/protesto/{tid}')==row['id']
        assert PRE.ler(con,tid,uid) is None


def test_as_duas_afirmacoes_salvas_reabrem_separadas_sem_confirmacao(s,monkeypatch):
    tid=intimado(s,provado=False)
    monkeypatch.setitem(s['app'].jinja_env.globals,'conferencia_cenprot_da_ficha',lambda t:{'pedido':'123','trava':[],'contraria_o_pago':[],'achados':[],'conferencia':None})
    html=salvar(s,tid,afirmo_prova='1',afirmacao_prova=TEXTO,afirmo_cenprot='1',afirmacao_cenprot=OUTRO).get_data(as_text=True)
    form=form_protesto(html)
    assert TEXTO in re.search(r'<textarea name="afirmacao_prova".*?</textarea>',form,re.S).group()
    assert OUTRO in re.search(r'<textarea name="afirmacao_cenprot".*?</textarea>',form,re.S).group()
    assert re.search(r'name="afirmo_prova"[^>]*checked',form) is None
    assert re.search(r'name="afirmo_cenprot"[^>]*checked',form) is None


def test_juntada_posterior_continua_pedindo_prova_ou_afirmacao(s):
    import protesto_prova as PROVA
    tid=intimado(s)
    with _con(s) as con:
        edital=con.execute('SELECT id,ato_id FROM pt_editais WHERE titulo_id=?',(tid,)).fetchone()
        con.execute("UPDATE pt_editais SET publicado_em='2026-10-29' WHERE id=?",(edital['id'],))
        con.execute("UPDATE pt_atos SET data_ato='2026-10-29' WHERE id=?",(edital['ato_id'],))
        con.execute("UPDATE attachments SET uploaded_at='2026-10-30T10:00:00' WHERE entity_type='PT_EDITAL_CENPROT' AND entity_id=?",(edital['id'],))
        con.execute("UPDATE settings SET value='' WHERE key='ri_feriados_locais'")
        prova=PROVA.conferir(con,tid,hoje='2026-11-03')
        assert not prova['completa'] and any('04/11/2026' in f for f in prova['faltas'])
    assert atos(s,tid)==0

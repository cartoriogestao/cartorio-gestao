"""Exclusao da nota pela conta autenticada, conservando o historico."""
import json
import sqlite3
from pathlib import Path
import pytest
import ri_nota_devolutiva as RND
import ri_pedidos as PED
from test_ri_nota_devolutiva_anexo import casa, _prenotar, _anexar, _um, _todos, _token

MOTIVO = 'Nota cadastrada com erro; manter a outra nota correta.'

def notas(casa, quantidade=3):
    p = _prenotar(casa)
    for i in range(quantidade):_anexar(casa, p, 'NOTA_DEVOLUTIVA', nome=f'nota-ficticia-{i+1}.pdf')
    ns = _todos(casa, 'SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=? ORDER BY numero', p['id'])
    return p, ns

def url(p,n):return f"/registro-imoveis/protocolo/{p['id']}/nota/{n['id']}/excluir"

def excluir(casa,p,n,**extra):
    c=casa['cliente'];html=c.get(url(p,n)).get_data(as_text=True)
    dados={'csrf_token':_token(html),'confirmar':'1','motivo':MOTIVO};dados.update(extra)
    return c.post(url(p,n),data=dados,follow_redirects=True)

def test_excluir_1_e_2_mantem_3_e_historico(casa):
    p,ns=notas(casa)
    anexo3=_um(casa,"SELECT * FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=? ORDER BY id DESC LIMIT 1",p['id'])
    for n in ns[:2]:assert excluir(casa,p,n).status_code==200
    todos=_todos(casa,'SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=? ORDER BY numero',p['id'])
    assert [n['situacao'] for n in todos]==['EXCLUIDA','EXCLUIDA','ABERTA']
    with casa['db'].connect() as con:
        assert RND.nota_aberta(con,p['id'])['numero']==3
        assert [q['nota_id'] for q in PED.qualificacoes_de(con,p['id'])]==[ns[2]['id']]
    atual=_um(casa,'SELECT * FROM attachments WHERE id=?',anexo3['id'])
    assert dict(atual)==dict(anexo3) and Path(atual['stored_path']).is_file()
    assert _um(casa,'SELECT situacao FROM ri_protocolos WHERE id=?',p['id'])[0]=='DEVOLVIDO'
    assert _um(casa,"SELECT count(*) FROM audit_logs WHERE action='RI_NOTA_EXCLUIDA' AND entity_id=?",p['id'])[0]==2
    assert _um(casa,"SELECT count(*) FROM onr_at_eventos WHERE protocolo_id=? AND evento='EXIGENCIA' AND situacao='PENDENTE'",p['id'])[0]==1
    assert _um(casa,"SELECT count(*) FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=? AND retirado_em IS NULL",p['id'])[0]==1
    assert casa['cliente'].get(f"/registro-imoveis/notas/{ns[0]['id']}.odt").status_code==410

def test_ultima_nota_reabre_sem_reusar_numero(casa):
    p,ns=notas(casa,1);excluir(casa,p,ns[0])
    assert _um(casa,'SELECT situacao FROM ri_protocolos WHERE id=?',p['id'])[0]=='ABERTO'
    _anexar(casa,p,'NOTA_DEVOLUTIVA',nome='segunda-ficticia.pdf')
    assert _um(casa,'SELECT max(numero) FROM ri_notas_devolutivas WHERE protocolo_id=?',p['id'])[0]==2

def test_exige_confirmacao_motivo_csrf_e_protocolo_certo(casa):
    p,ns=notas(casa,1);n=ns[0]
    assert excluir(casa,p,n,confirmar='').status_code==200
    assert excluir(casa,p,n,motivo='erro').status_code==200
    assert casa['cliente'].post(url(p,n),data={'confirmar':'1','motivo':MOTIVO}).status_code==400
    assert casa['cliente'].get(url({'id':p['id']+99999},n)).status_code==404
    assert _um(casa,'SELECT situacao FROM ri_notas_devolutivas WHERE id=?',n['id'])[0]=='ABERTA'

@pytest.mark.parametrize('caso',['reingresso','ato','enviado'])
def test_recusa_nota_cumprida_ato_lavrado_e_onr_enviado(casa,caso):
    p,ns=notas(casa,1);n=ns[0]
    with casa['db'].transaction() as con:
        if caso=='reingresso':con.execute("UPDATE ri_notas_devolutivas SET situacao='CUMPRIDA' WHERE id=?",(n['id'],))
        elif caso=='ato':con.execute("UPDATE ri_protocolos SET situacao='REGISTRADO' WHERE id=?",(p['id'],))
        else:con.execute("UPDATE onr_at_eventos SET situacao='ENVIADO' WHERE origem_tabela='ri_notas_devolutivas' AND origem_id=?",(n['id'],))
    excluir(casa,p,n)
    assert _um(casa,'SELECT situacao FROM ri_notas_devolutivas WHERE id=?',n['id'])[0]!='EXCLUIDA'

def test_robo_sem_responsavel_nao_exclui(casa):
    p,ns=notas(casa,1)
    uid=_um(casa,"SELECT id FROM users WHERE username='mario'")[0]
    with casa['db'].transaction() as con:
        con.execute('UPDATE users SET eh_robo=1,robo_responsavel_id=NULL WHERE id=?',(uid,))
    r=excluir(casa,p,ns[0]);assert r.status_code==200
    assert 'responsável humano' in r.get_data(as_text=True)
    assert _um(casa,'SELECT situacao FROM ri_notas_devolutivas WHERE id=?',ns[0]['id'])[0]=='ABERTA'

def test_auditor_nao_exclui(casa):
    p,ns=notas(casa,1)
    with casa['db'].transaction() as con:con.execute("UPDATE users SET role='AUDITOR' WHERE username='mario'")
    assert casa['cliente'].get(url(p,ns[0])).status_code==403

def test_falha_de_auditoria_desfaz_exclusao_e_descarte(casa,monkeypatch):
    import identidade_do_robo as IDR
    p,ns=notas(casa,1);uid=_um(casa,"SELECT id FROM users WHERE username='mario'")[0]
    def falhar(*a,**k):raise RuntimeError('auditoria indisponivel')
    monkeypatch.setattr(IDR,'registrar',falhar)
    with pytest.raises(RuntimeError):
        with casa['db'].transaction() as con:RND.excluir(con,p['id'],ns[0]['id'],motivo=MOTIVO,usuario_id=uid,agora='2026-11-04T13:00:00')
    assert _um(casa,'SELECT situacao FROM ri_notas_devolutivas WHERE id=?',ns[0]['id'])[0]=='ABERTA'
    assert _um(casa,"SELECT count(*) FROM attachments WHERE entity_type='RI_PROTOCOLO' AND entity_id=? AND retirado_em IS NOT NULL",p['id'])[0]==0


@pytest.mark.parametrize('robo', [False, True])
def test_usuario_e_robo_com_responsavel_excluem_com_autoria(casa, robo):
    p,ns=notas(casa,1)
    if robo:
        casa['db'].create_user('responsavel-ficticio','PESSOA RESPONSAVEL FICTICIA','Senha#12345','USER')
        rid=_um(casa,"SELECT id FROM users WHERE username='responsavel-ficticio'")[0]
    else:rid=None
    with casa['db'].transaction() as con:
        con.execute("UPDATE users SET role='USER',eh_robo=?,robo_responsavel_id=? WHERE username='mario'",(int(robo),rid))
    r=excluir(casa,p,ns[0]);assert r.status_code==200
    assert _um(casa,'SELECT situacao FROM ri_notas_devolutivas WHERE id=?',ns[0]['id'])[0]=='EXCLUIDA'
    log=_um(casa,"SELECT user_id,agente,a_mando_de FROM audit_logs WHERE action='RI_NOTA_EXCLUIDA' AND entity_id=? ORDER BY id DESC LIMIT 1",p['id'])
    assert log['user_id'] is not None
    if robo:assert log['agente'] and 'RESPONSAVEL' in log['a_mando_de']

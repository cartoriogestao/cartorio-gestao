"""PDF original, vínculo aos alertas, retomada e API sem acesso a segredos."""
import io
import json
import re
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import fraude as FR
import malote_documentos as MD
import malote_fluxo as FL
import automacao as AU
from bd_nativo import banco

PRINCIPAL = '81000000000001'
ANEXO = '81000000000002'


def pdf(codigo=PRINCIPAL):
    w = PdfWriter()
    p = w.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica'), NameObject('/Encoding'): NameObject('/WinAnsiEncoding')})
    p[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): w._add_object(font)})})
    texto = f'Código de rastreabilidade: {codigo}'
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 12 Tf 30 700 Td (' + texto + ') Tj ET').encode('cp1252'))
    p[NameObject('/Contents')] = w._add_object(stream)
    out = io.BytesIO(); w.write(out)
    return out.getvalue()


def token(c, tela='/automacao/malote/documentos'):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c.get(tela).get_data(as_text=True))[1]


@pytest.fixture
def casa(cg_casa_logada):
    db = cg_casa_logada['db']
    uid = db.get_user(1)['id']
    db.set_settings({'malote_cadastra_em_nome_de': 'mario'})
    with db.transaction() as con:
        for nome in ('Mario Exemplo dos Santos', 'Carla Exemplo'):
            FR.incluir(con, nome=nome, papel='VITIMA', origem=f'Malote {PRINCIPAL} e anexo {ANEXO}',
                       agora=db.now(), usuario='mario')
    return {**cg_casa_logada, 'uid': uid}


def enviar(casa, codigo=PRINCIPAL, grupo=PRINCIPAL, *, conferir=False, conteudo=None):
    c = casa['c']
    return c.post('/automacao/malote/documentos', data={'csrf_token': token(c), 'grupo': grupo,
                  'conferir': '1' if conferir else '0', 'documento': (io.BytesIO(conteudo or pdf(codigo)), '../../fora.pdf')},
                  headers={'Accept': 'application/json'})


def test_dois_pdfs_se_ligam_a_todos_alertas_sem_duplicar_ou_criar_processo(casa):
    r = enviar(casa); a = r.get_json()
    assert r.status_code == 200 and a['alertas'] == 2 and len(a['anexos']) == 2
    assert enviar(casa).get_json()['anexos'] == a['anexos']
    b = enviar(casa, ANEXO).get_json()
    assert len(set(a['anexos']+b['anexos'])) == 4
    with casa['db'].connect() as con:
        bd = banco(con)
        assert bd.valor('SELECT count(*) FROM fr_alertas') == 2
        assert not bd.valor('SELECT count(*) FROM expedientes')
        assert not bd.valor('SELECT count(*) FROM tasks')
        rows = bd.ler('SELECT * FROM attachments')
        assert len(rows) == 4
        assert all(Path(x['stored_path']).is_relative_to(casa['acervo']) for x in rows)
        assert all(Path(x['stored_path']).read_bytes() == pdf(PRINCIPAL if x['sha256'] == a['sha256'] else ANEXO) for x in rows)
    pagina = casa['c'].get('/fraudes').get_data(as_text=True)
    assert 'Juntar PDFs do Malote' in pagina and '/arquivo/' in pagina
    assert casa['c'].get('/arquivo/'+str(a['anexos'][0])).data == pdf()


def test_conferencia_nao_grava_arquivo_nem_vinculo(casa):
    r = enviar(casa, conferir=True)
    assert r.status_code == 200 and r.get_json()['conferir'] is True
    assert not list(casa['acervo'].rglob('*.pdf'))
    with casa['db'].connect() as con:
        assert not banco(con).valor('SELECT count(*) FROM attachments')


@pytest.mark.parametrize('grupo,codigo,dados', [(PRINCIPAL,'81000000000003',None), ('../fora',PRINCIPAL,None),
                                                (PRINCIPAL,PRINCIPAL,b'nao e pdf'),(PRINCIPAL,PRINCIPAL,b'%PDF-quebrado')])
def test_pdf_ou_referencia_divergente_recusado(casa, grupo, codigo, dados):
    assert enviar(casa,codigo,grupo,conteudo=dados).status_code == 400
    with casa['db'].connect() as con:
        assert not banco(con).valor('SELECT count(*) FROM attachments')


def test_hash_no_disco_divergente_nao_e_sobrescrito(casa):
    enviar(casa)
    with casa['db'].connect() as con:
        r = banco(con).um('SELECT stored_path FROM attachments LIMIT 1')
    Path(r['stored_path']).write_bytes(b'arquivo divergente')
    assert enviar(casa).status_code == 400
    assert Path(r['stored_path']).read_bytes() == b'arquivo divergente'


def test_csrf_admin_e_acesso_do_balcao(casa):
    c = casa['c']
    assert c.post('/automacao/malote/documentos', data={}).status_code == 400
    aid = enviar(casa).get_json()['anexos'][0]
    uid = casa['db'].create_user('carla', 'Carla Exemplo', 'Senha#12345', 'USER')
    with c.session_transaction() as s:s.clear()
    c.post('/login', data={'username':'carla','password':'Senha#12345','csrf_token':token(c,'/login')})
    assert c.get('/automacao/malote/documentos').status_code == 403
    assert c.get('/arquivo/'+str(aid)).status_code == 200
    with c.session_transaction() as s:s.clear()
    assert '/login' in c.get('/arquivo/'+str(aid)).location


def configurar(casa):
    db = casa['db']; dono = casa['uid']
    nomes = ['Carla Exemplo', 'Mario Exemplo dos Santos', 'Beatriz Exemplo de Souza', 'Pedro Exemplo dos Santos', 'Carla Exemplo']
    distrib = {r: {'principal': db.create_user('setor'+str(i), nomes[i], 'Senha#12345', 'USER'), 'substituto': dono}
               for i, r in enumerate(FL.ROTAS)}
    with db.transaction() as con:
        p = AU.por_codigo(con, FL.CODIGO)
        bd = banco(con)
        bd.escrever('UPDATE au_processos SET ativo=1,pode_agir=1,parametros=%s WHERE id=%s',
                     (json.dumps({'triar_recebidos':True}),p['id']))
        bd.escrever('INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',
                     (FL.CONFIG,json.dumps(distrib)))
    return p['id'], distrib


def test_pedido_idempotente_nao_mexe_em_outras_automacoes(casa):
    pid,_ = configurar(casa); c = casa['c']; csrf = token(c,'/automacao/malote/agente')
    data={'csrf_token':csrf,'chave':'rodada-2026-11-10-0800','modo':'executar'}
    r=c.post('/automacao/malote/agente/rodada',data=data,headers={'Accept':'application/json'})
    assert r.status_code==202 and not r.json['repetido']
    assert c.post('/automacao/malote/agente/rodada',data=data,headers={'Accept':'application/json'}).json['repetido']
    estado=c.get('/automacao/malote/agente',headers={'Accept':'application/json'}).json
    assert estado['versao_fluxo']==1 and estado['processo']['pedido_pendente']
    assert 'mario' not in repr(estado) and 'senha' not in repr(estado)
    with casa['db'].connect() as con:
        bd=banco(con)
        assert bd.valor('SELECT count(*) FROM mt_pedidos_locais')==1
        assert bd.valor('SELECT count(*) FROM au_processos WHERE pedido_manual_em IS NOT NULL AND id<>%s',(pid,))==0
    assert c.post('/automacao/malote/agente/rodada',data={**data,'chave':'outra-rodada'},headers={'Accept':'application/json'}).status_code==409


def test_consultar_nao_pode_dar_ciencia(casa):
    configurar(casa);c=casa['c']
    r=c.post('/automacao/malote/agente/rodada',data={'csrf_token':token(c,'/automacao/malote/agente'),
             'modo':'consultar','chave':'consulta-2026-11-10'},headers={'Accept':'application/json'})
    assert r.status_code==409


@pytest.mark.parametrize('setor,natureza,rota',[('RI_QUALIFICACAO','TECNICA','RI_NOTAS'),('RI','MANUAL','RI_NOTAS_MANUAL'),
 ('NOTAS','DIGITALIZACAO','DIGITALIZACAO'),('RCPN','LIVRO_E','PROTESTO_LIVRO_E'),('RCPN','TECNICA','RCPN'),
 ('PROTESTO','TECNICA','PROTESTO_LIVRO_E')])
def test_distribuicao_por_natureza(casa,setor,natureza,rota):
    _,d=configurar(casa)
    with casa['db'].connect() as con:
        assert FL.responsaveis(con,{'setor':setor,'natureza':natureza})==(d[rota]['principal'],d[rota]['substituto'])


def test_falha_apos_copiar_conserva_original_e_retomada_recupera(casa,monkeypatch):
    original=MD.vincular
    def falha(*a,**kw):raise RuntimeError('falha simulada')
    monkeypatch.setattr(MD,'vincular',falha)
    with pytest.raises(RuntimeError):
        with casa['db'].transaction() as con:
            MD.receber(con,pdf(),PRINCIPAL,raiz=casa['acervo'],usuario_id=casa['uid'],agora=casa['db'].now())
    with casa['db'].connect() as con:
        assert not banco(con).valor('SELECT count(*) FROM attachments')
    assert len(list(casa['acervo'].rglob('*.pdf')))==1
    monkeypatch.setattr(MD,'vincular',original)
    assert enviar(casa).status_code==200
    assert len(list(casa['acervo'].rglob('*.pdf')))==1


def test_configuracao_de_usuarios_nao_ativa_a_ciencia(casa):
    _,dist=configurar(casa);c=casa['c']
    with casa['db'].transaction() as con:
        banco(con).escrever("UPDATE au_processos SET ativo=0,pode_agir=0 WHERE codigo=%s",(FL.CODIGO,))
    dados={'csrf_token':token(c,'/automacao/malote/agente'),'triar':'1'}
    for k,v in dist.items():dados[k]=v['principal'];dados[k+'_sub']=v['substituto']
    assert c.post('/automacao/malote/agente',data=dados).status_code==302
    with casa['db'].connect() as con:
        p=AU.por_codigo(con,FL.CODIGO)
        assert not p['ativo'] and not p['pode_agir']
        assert p['parametros']['triar_recebidos']


def test_usuario_inativo_trava_distribuicao(casa):
    _,dist=configurar(casa)
    casa['db'].set_user_active(dist['RCPN']['principal'],False)
    with casa['db'].connect() as con:
        with pytest.raises(FL.FluxoMaloteError):FL.conferir_distribuicao(con)


def test_fraude_com_leitura_incompleta_nao_chega_a_ia(casa,tmp_path):
    import malote_agente as MA
    import malote_fraudes as MF
    entrada=tmp_path/'entrada';entrada.mkdir();(entrada/'fraude.pdf').write_bytes(pdf())
    with casa['db'].transaction() as con:
        MA.init_schema(con)
    def nao_deve_ser_chamada(*a,**k):raise AssertionError('leitura incompleta enviada para IA')
    with casa['db'].connect() as con:
        r=MF.tratar_grupo(con,MA.varrer([entrada])[0],casa['dados'],casa['acervo'],'mario',
                         ler_texto=lambda ps:'[LEITURA_INCOMPLETA: precisa de OCR] suspeita de fraude',conversar=nao_deve_ser_chamada)
    assert r['caminho']=='PENDENTE' and not r['leu']

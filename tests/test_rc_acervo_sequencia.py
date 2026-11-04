import json,re
from pathlib import Path
import pytest
from bd_nativo import banco
import rc_acervo_sequencia as S
from test_rc_acervo_lote import lote,usuario


class SemThread:
    def __init__(self,**kw):pass
    def start(self):pass


def indice(casa):
    a,_,pa=lote(casa,numero=101)
    b,_,pb=lote(casa,numero=102)
    p=pa.parent.parent/'indice.json'
    d={'formato':S.FORMATO,'versao':1,'lotes':[
        {'livro':'A-09','manifesto':'101/lote.json','sha256':a['sha256']},
        {'livro':'A-09','manifesto':'102/lote.json','sha256':b['sha256']}]}
    p.write_text(json.dumps(d),encoding='utf-8')
    return p,pb


def test_sequencia_preserva_blocos_commitados_e_retoma_por_recibo(cg_casa_logada,monkeypatch):
    casa=cg_casa_logada;monkeypatch.setattr(S,'Thread',SemThread)
    p,pb=indice(casa);i=S.carregar(p);u=usuario(casa)
    original=pb.read_bytes();pb.write_bytes(original+b' ')
    identificador=S.iniciar(casa['db'],i,usuario_id=u['id'],usuario=u['full_name'])
    S.executar(casa['db'],identificador);d=S.estado(casa['db'],identificador)
    assert d['situacao']=='INTERROMPIDA' and d['concluidos']==1
    with casa['db'].connect() as c:assert banco(c).valor('SELECT count(*) FROM rc_assentos')==1
    pb.write_bytes(original)
    segundo=S.iniciar(casa['db'],S.carregar(p),usuario_id=u['id'],usuario=u['full_name'])
    S.executar(casa['db'],segundo);d=S.estado(casa['db'],segundo)
    assert d['situacao']=='CONCLUIDA' and d['concluidos']==2 and d['incluidos']==2
    assert d['resultados'][0]['recibo_anterior'] is True
    with casa['db'].connect() as c:
        assert banco(c).valor('SELECT count(*) FROM rc_assentos')==2
        assert banco(c).valor("SELECT count(*) FROM audit_logs WHERE action='RCPN_ACERVO_TRANSCRITO'")==2


def test_indice_recusa_escape_repeticao_e_hash_divergente(cg_casa_logada):
    casa=cg_casa_logada;p,_=indice(casa);d=json.loads(p.read_text(encoding='utf-8'))
    d['lotes'][1]=dict(d['lotes'][0]);p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(ValueError,match='repetido'):S.carregar(p)
    d['lotes']=d['lotes'][:1];d['lotes'][0]['manifesto']='../fora.json';p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(ValueError,match='fora'):S.carregar(p)
    d['lotes'][0]['manifesto']='101/lote.json';d['lotes'][0]['sha256']='0'*64;p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(ValueError,match='mudou'):S.carregar(p)


def test_tela_sequencia_confirma_csrf_e_restringe_andamento_ao_solicitante(cg_casa_logada,monkeypatch):
    casa=cg_casa_logada;monkeypatch.setattr(S,'Thread',SemThread)
    p,_=indice(casa);c=casa['c'];url='/rcpn/acervo-transcrito/sequencia'
    assert c.post(url,data={'indice':str(p),'acao':'iniciar'}).status_code==400
    html=c.get(url).get_data(as_text=True);token=re.search('name="csrf_token"[^>]*value="([^"]+)"',html)[1]
    r=c.post(url,data={'csrf_token':token,'indice':str(p),'acao':'iniciar'})
    assert 'Confirme a execução' in r.get_data(as_text=True)
    r=c.post(url,data={'csrf_token':token,'indice':str(p),'acao':'iniciar','confirmar':'1'})
    assert r.status_code==302 and 'execucao=' in r.location
    assert 'EM_EXECUCAO' in c.get(r.location).get_data(as_text=True)
    ident=r.location.split('execucao=')[1]
    estado=S._pasta(casa['db'],ident)/'andamento.json';d=json.loads(estado.read_text(encoding='utf-8'))
    d['usuario_id']+=10000;estado.write_text(json.dumps(d),encoding='utf-8')
    assert c.get(r.location).status_code==403


def test_consulta_escolhe_pasta_existente_sem_usar_caminho_da_url(tmp_path,monkeypatch):
    monkeypatch.setattr(S.D,'raiz_arquivos',lambda db:tmp_path)
    ident='a'*32
    pasta=tmp_path/'rc'/'acervo_lotes'/'execucoes'/ident;pasta.mkdir(parents=True)
    (pasta/'andamento.json').write_text('{"situacao":"CONCLUIDA"}',encoding='utf-8')
    assert S.estado(None,ident)['situacao']=='CONCLUIDA'
    with pytest.raises(ValueError,match='não encontrada'):S.estado(None,'../fora')

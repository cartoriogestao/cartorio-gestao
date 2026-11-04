"""Lotes pela tela: identidade, prevalência, cópias e rollback."""
import json
from hashlib import sha256
from pathlib import Path
import re

import pytest
from PIL import Image
from bd_nativo import banco
import rc_acervo_lote as L
import rc_digitalizacao as D
import identidade_do_robo as IDR

AGORA = '2026-11-04T14:00:00'
URL = '/rcpn/acervo-transcrito/lote'


def lote(casa, *, numero=101, nome='ANA EXEMPLO', livro='A-09', extra=None):
    pasta = Path(casa['dados'])/'entrada'/str(numero)
    pasta.mkdir(parents=True, exist_ok=True)
    pdf = pasta/'termo.pdf'
    Image.new('RGB', (20, 30), 'white').save(pdf, format='PDF')
    v = {'livro_volume':livro, 'numero':numero, 'nome':nome,
         'teor':'Transcrição integral do termo de ANA EXEMPLO.', 'teor_formato':'texto',
         'data_ato':'1995-01-02', 'dados_json':json.dumps({'folha':'1v', 'acervo_transcrito':{'avos_paternos':'JOÃO EXEMPLO e MARIA EXEMPLO','duvidas':'Conferir uma rubrica.'}}),
         'pessoas':[{'papel':'REGISTRADO','nome':nome,'sexo':'F'}, {'papel':'MAE','nome':'MAE NOVA'}]}
    v.update(extra or {})
    item = {'valores':v,'pdf':pdf.name,'sha256':sha256(pdf.read_bytes()).hexdigest(),'bytes':pdf.stat().st_size}
    arquivo = pasta/'lote.json'
    arquivo.write_text(json.dumps({'formato':L.FORMATO,'versao':1,'registros':[item]},ensure_ascii=False),encoding='utf-8')
    return L.carregar(arquivo), item, arquivo


def usuario(casa):
    with casa['db'].connect() as c:
        return banco(c).um("SELECT * FROM users WHERE username='mario'")


def aplicar(casa, carregado, assinatura=None):
    u = usuario(casa)
    with casa['db'].transaction() as c:
        q = L.conferir(c, carregado)
        return L.aplicar(c,carregado,assinatura=assinatura or q['assinatura'],
            raiz=D.raiz_arquivos(casa['db']),usuario_id=u['id'],usuario=u['full_name'],agora=AGORA)


def antigo(casa, *, nome='NOME ANTERIOR', livro='A-9', origem='IMPORTACAO', numero=101):
    with casa['db'].transaction() as c:
        bd = banco(c)
        aid=bd.valor("INSERT INTO rc_assentos(serie,especie,numero,nome,livro_volume,teor,dados_json,origem,origem_chave,criado_em) VALUES ('RC_A','NASCIMENTO',%s,%s,%s,'TEOR ANTERIOR','{\"preservar\":\"sim\"}',%s,%s,%s) RETURNING id",(numero,nome,livro,origem,f'antigo:{numero}:{nome}',AGORA))
        bd.escrever("INSERT INTO rc_pessoas(assento_id,papel,nome,nome_norm,origem,criado_em) VALUES (%s,'MAE','MAE ANTERIOR','mae anterior','IMPORTACAO',%s)",(aid,AGORA))
        return aid


def test_inclui_em_lote_com_pessoas_teor_pdf_e_autoria(cg_casa_logada):
    casa=cg_casa_logada; carregado,_,_=lote(casa)
    r=aplicar(casa,carregado)
    assert (r['incluir'],r['complementar'])==(1,0)
    aid=r['resultados'][0]['id']
    with casa['db'].connect() as c:
        bd=banco(c); a=bd.um('SELECT * FROM rc_assentos WHERE id=%s',(aid,))
        assert a['numero']==101 and a['livro_volume']=='A-9' and a['origem']=='IMPORTACAO'
        assert a['teor'].startswith('Transcrição integral')
        assert sha256(Path(a['digi_path']).read_bytes()).hexdigest()==a['digi_sha256']
        assert len(bd.ler('SELECT * FROM rc_pessoas WHERE assento_id=%s',(aid,)))==2
        aud=bd.um("SELECT * FROM audit_logs WHERE action='RCPN_ACERVO_TRANSCRITO' AND entity_id=%s",(aid,))
        assert aud['user_id']==usuario(casa)['id']
    assert Path(r['backup']).is_file()
    assert casa['c'].get(f'/rcpn/{aid}').status_code==200


def test_complementa_prevalece_transcricao_e_preserva_antes(cg_casa_logada):
    casa=cg_casa_logada; aid=antigo(casa)
    carregado,_,_=lote(casa)
    r=aplicar(casa,carregado)
    assert r['resultados'][0]['id']==aid and (r['incluir'],r['complementar'])==(0,1)
    with casa['db'].connect() as c:
        bd=banco(c); a=bd.um('SELECT * FROM rc_assentos WHERE id=%s',(aid,))
        assert a['nome']=='ANA EXEMPLO' and a['teor']!='TEOR ANTERIOR'
        assert json.loads(a['dados_json'])['preservar']=='sim'
        assert bd.valor("SELECT nome FROM rc_pessoas WHERE assento_id=%s AND papel='MAE'",(aid,))=='MAE NOVA'
        assert bd.valor('SELECT count(*) FROM rc_assentos')==1
    antes=json.loads(Path(r['backup']).read_text(encoding='utf-8'))
    assert antes['assentos'][0]['teor']=='TEOR ANTERIOR'
    assert antes['pessoas'][0]['nome']=='MAE ANTERIOR'
    r2=aplicar(casa,carregado)
    assert r2['incluir']==0 and r2['resultados'][0]['id']==aid


def test_identifica_sem_volume_por_termo_e_nome_mas_nao_adivinha(cg_casa_logada):
    casa=cg_casa_logada; aid=antigo(casa,nome='ANA EXEMPLO',livro=None)
    carregado,_,_=lote(casa)
    r=aplicar(casa,carregado); assert r['resultados'][0]['id']==aid
    antigo(casa,nome='OUTRA PESSOA',livro=None,numero=102)
    outro,_,_=lote(casa,numero=102)
    with casa['db'].connect() as c:
        q=L.conferir(c,outro)
    assert not q['aceitos'] and 'nome diferente' in q['recusados'][0]['porque']


def test_numero_duplicado_no_lote_nao_entra(cg_casa_logada):
    casa=cg_casa_logada; carregado,_,arquivo=lote(casa)
    d=carregado['dados'];d['registros']*=2
    arquivo.write_text(json.dumps(d),encoding='utf-8');carregado=L.carregar(arquivo)
    with casa['db'].connect() as c:q=L.conferir(c,carregado)
    assert not q['aceitos'] and len(q['recusados'])==2


@pytest.mark.parametrize('caso',['manual','cancelado','duas_pessoas'])
def test_recusa_registro_novo_cancelado_ou_papel_ambiguo(cg_casa_logada,caso):
    casa=cg_casa_logada; aid=antigo(casa,origem='MANUAL' if caso=='manual' else 'IMPORTACAO')
    with casa['db'].transaction() as c:
        if caso=='cancelado':banco(c).escrever("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=%s",(aid,))
        if caso=='duas_pessoas':banco(c).escrever("INSERT INTO rc_pessoas(assento_id,papel,nome,origem,criado_em) VALUES (%s,'MAE','SEGUNDA MAE','IMPORTACAO',%s)",(aid,AGORA))
    carregado,_,_=lote(casa)
    with casa['db'].connect() as c:q=L.conferir(c,carregado)
    assert not q['aceitos'] and q['recusados']


def test_falha_auditoria_desfaz_dados_e_preserva_pdf_anterior(cg_casa_logada,monkeypatch):
    casa=cg_casa_logada; aid=antigo(casa)
    pdf=Path(casa['dados'])/'anterior.pdf'; Image.new('RGB',(30,40),'black').save(pdf,format='PDF')
    D.anexar_digitalizacao(casa['db'],aid,pdf,'CARGA',agente='teste',a_mando_de='MARIO EXEMPLO')
    with casa['db'].connect() as c:antes=banco(c).um('SELECT * FROM rc_assentos WHERE id=%s',(aid,))
    bytes_antes=Path(antes['digi_path']).read_bytes()
    carregado,_,_=lote(casa)
    def falhar(*a,**k):raise RuntimeError('falha simulada')
    monkeypatch.setattr(IDR,'registrar',falhar)
    with pytest.raises(RuntimeError):aplicar(casa,carregado)
    with casa['db'].connect() as c:depois=banco(c).um('SELECT * FROM rc_assentos WHERE id=%s',(aid,))
    assert depois==antes and Path(antes['digi_path']).read_bytes()==bytes_antes


def test_recusa_pdf_alterado_previa_antiga_e_caminho_fora(cg_casa_logada):
    casa=cg_casa_logada; antigo(casa);carregado,item,_=lote(casa)
    with casa['db'].connect() as c:q=L.conferir(c,carregado)
    with casa['db'].transaction() as c:banco(c).escrever("UPDATE rc_assentos SET teor='edição posterior'")
    with pytest.raises(L.LoteError,match='mudou'):aplicar(casa,carregado,q['assinatura'])
    p=carregado['pasta']/'termo.pdf';d=p.read_bytes();p.write_bytes(d[:-1]+bytes([d[-1]^1]))
    with pytest.raises(L.LoteError,match='PDF'):aplicar(casa,carregado)
    carregado['dados']['registros'][0]['pdf']='../termo.pdf'
    with casa['db'].connect() as c:q=L.conferir(c,carregado)
    assert not q['aceitos']


def test_tela_exige_login_csrf_confirmacao_e_pasta_da_casa(cg_casa_logada):
    casa=cg_casa_logada; _,_,arquivo=lote(casa);c=casa['c']
    assert c.post(URL,data={'manifesto':str(arquivo)}).status_code==400
    html=c.get(URL).get_data(as_text=True)
    token=re.search('name="csrf_token"[^>]*value="([^"]+)"',html)[1]
    r=c.post(URL,data={'csrf_token':token,'manifesto':str(arquivo),'acao':'conferir'})
    assert 'Prévia do lote' in r.get_data(as_text=True)
    r=c.post(URL,data={'csrf_token':token,'manifesto':str(arquivo),'acao':'importar'})
    assert 'Confirme a prevalência' in r.get_data(as_text=True)
    r=c.post(URL,data={'csrf_token':token,'manifesto':str(Path(casa['dados']).parent/'fora.json'),'acao':'conferir'})
    assert 'fora das pastas da casa' in r.get_data(as_text=True)


def test_robo_sem_responsavel_recusado_no_dominio(cg_casa_logada):
    casa=cg_casa_logada;u=usuario(casa);carregado,_,_=lote(casa)
    with casa['db'].transaction() as c:banco(c).escrever('UPDATE users SET eh_robo=1,robo_responsavel_id=NULL WHERE id=%s',(u['id'],))
    with pytest.raises(L.LoteError,match='responsável humano'):aplicar(casa,carregado)


def test_avos_transcritos_prevalecem_sem_inferir_sexo(cg_casa_logada):
    from rc_certidao_quadro import quadro_da_certidao
    casa=cg_casa_logada;carregado,_,_=lote(casa);r=aplicar(casa,carregado)
    with casa['db'].connect() as c:
        q=quadro_da_certidao(c,{'assento_id':r['resultados'][0]['id'],'especie':'NASCIMENTO'}, {})
    assert q['avos_paternos']=='JOÃO EXEMPLO e MARIA EXEMPLO'


def test_tela_importa_confirma_e_mostra_recibo(cg_casa_logada):
    casa=cg_casa_logada; _,_,arquivo=lote(casa);c=casa['c']
    html=c.get(URL).get_data(as_text=True)
    token=re.search('name="csrf_token"[^>]*value="([^"]+)"',html)[1]
    html=c.post(URL,data={'csrf_token':token,'manifesto':str(arquivo),'acao':'conferir'}).get_data(as_text=True)
    assinatura=re.search('name="assinatura"[^>]*value="([^"]+)"',html)[1]
    r=c.post(URL,data={'csrf_token':token,'manifesto':str(arquivo),'acao':'importar',
                       'assinatura':assinatura,'confirmar':'1'},follow_redirects=True)
    assert r.status_code==200 and 'Lote concluído' in r.get_data(as_text=True)
    assert '1 incluído(s)' in r.get_data(as_text=True)


@pytest.mark.parametrize('robo',[False,True])
def test_escrevente_e_robo_responsavel_importam_pela_sessao(cg_casa_logada,robo):
    casa=cg_casa_logada;u=usuario(casa);carregado,_,_=lote(casa)
    casa['db'].create_user('laura','LAURA RESPONSAVEL','Senha#12345','MANAGER')
    with casa['db'].transaction() as c:
        bd=banco(c);rid=bd.valor("SELECT id FROM users WHERE username='laura'")
        bd.escrever("UPDATE users SET role='USER',eh_robo=%s,robo_responsavel_id=%s WHERE id=%s",(int(robo),rid if robo else None,u['id']))
    r=aplicar(casa,carregado)
    with casa['db'].connect() as c:
        aud=banco(c).um("SELECT * FROM audit_logs WHERE action='RCPN_ACERVO_TRANSCRITO' AND entity_id=%s",(r['resultados'][0]['id'],))
    assert aud['user_id']==u['id']
    if robo:assert 'LAURA' in aud['a_mando_de']


def test_falha_ao_salvar_recibo_informa_que_lote_foi_gravado(cg_casa_logada,monkeypatch):
    casa=cg_casa_logada;_,_,arquivo=lote(casa);c=casa['c']
    token=re.search('name="csrf_token"[^>]*value="([^"]+)"',c.get(URL).get_data(as_text=True))[1]
    html=c.post(URL,data={'csrf_token':token,'manifesto':str(arquivo),'acao':'conferir'}).get_data(as_text=True)
    assinatura=re.search('name="assinatura"[^>]*value="([^"]+)"',html)[1]
    original=Path.write_text
    def falhar(self,*a,**k):
        if self.name=='resultado.json':raise OSError('falha simulada de recibo')
        return original(self,*a,**k)
    monkeypatch.setattr(Path,'write_text',falhar)
    r=c.post(URL,data={'csrf_token':token,'manifesto':str(arquivo),'acao':'importar','assinatura':assinatura,'confirmar':'1'})
    html=r.get_data(as_text=True)
    assert 'O lote foi gravado' in html and 'Lote concluído' in html
    with casa['db'].connect() as con:assert banco(con).valor('SELECT count(*) FROM rc_assentos')==1


def test_matricula_valida_identifica_volume_ausente_e_separa_outra_serventia(cg_casa_logada):
    import rc_matricula as M
    casa=cg_casa_logada;aid=antigo(casa,nome='NOME COM ERRO',livro=None)
    casa['db'].set_settings({'ri_cns':'999999'})
    m=M.compor(cns='999999',ano=1995,livro_tipo='1',livro=9,folha=1,termo=101)
    with casa['db'].transaction() as c:banco(c).escrever('UPDATE rc_assentos SET matricula=%s WHERE id=%s',(m,aid))
    carregado,_,_=lote(casa);r=aplicar(casa,carregado)
    assert r['complementar']==1 and r['resultados'][0]['id']==aid
    outro=antigo(casa,nome='OUTRA SERVENTIA',livro='A-9',numero=102)
    m=M.compor(cns='999998',ano=1995,livro_tipo='1',livro=9,folha=1,termo=102)
    with casa['db'].transaction() as c:banco(c).escrever('UPDATE rc_assentos SET matricula=%s WHERE id=%s',(m,outro))
    carregado,_,_=lote(casa,numero=102);r=aplicar(casa,carregado)
    assert r['incluir']==1 and r['resultados'][0]['id']!=outro
    with casa['db'].connect() as c:assert banco(c).valor('SELECT nome FROM rc_assentos WHERE id=%s',(outro,))=='OUTRA SERVENTIA'


def test_matricula_contraditoria_nao_cria_nem_complementa(cg_casa_logada):
    import rc_matricula as M
    casa=cg_casa_logada;aid=antigo(casa,livro='A-8')
    casa['db'].set_settings({'ri_cns':'999999'})
    m=M.compor(cns='999999',ano=1995,livro_tipo='1',livro=9,folha=1,termo=101)
    with casa['db'].transaction() as c:banco(c).escrever('UPDATE rc_assentos SET matricula=%s WHERE id=%s',(m,aid))
    carregado,_,_=lote(casa)
    with casa['db'].connect() as c:q=L.conferir(c,carregado)
    assert not q['aceitos'] and 'contradiz a matrícula' in q['recusados'][0]['porque']

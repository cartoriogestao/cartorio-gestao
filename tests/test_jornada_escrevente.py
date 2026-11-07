"""Um escrevente USER percorre os formulários, com pessoas e valores fictícios."""
import io
import json
import os
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest

from bd_nativo import banco
from test_fluxo_caixa import (casa, aparelho, Balcao, abrir_protocolo, abrir_caixa,
    acrescentar, _deposito, _um, _ler, _matricula, INTERESSADO, texto_do_odt)


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__();self.links=[];self.atual=None;self.feed(html)
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.atual=[dict(attrs).get('href',''),'']
    def handle_data(self,data):
        if self.atual is not None:self.atual[1]+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.atual is not None:
            self.links.append(self.atual);self.atual=None


def destino(html,texto):
    return next((u for u,t in Links(html).links if texto.casefold() in t.casefold()),None)


@pytest.fixture
def jornada(casa,aparelho,monkeypatch):
    # Somente a matrícula histórica e a tabela de ENSAIO são dados prévios.
    # Todo fato do atendimento em exame nasce por POST autenticado abaixo.
    import agente_provedores as AP
    monkeypatch.setattr(AP,'conversar',lambda *a,**kw:pytest.fail('A jornada chamou a API real'))
    with casa['db'].transaction() as con:
        bd=banco(con)
        for codigo,tj,valor in ((990108,'16.9','50,00'),(990109,'16.39','20,00')):
            bd.escrever("""INSERT INTO cx_servicos(codigo,codigo_tj,descricao,descricao_norm,ativo)
                VALUES (%s,%s,'Serviço fictício da jornada','servico ficticio',1)""",(codigo,tj))
            bd.escrever("""INSERT INTO cx_servico_valores
                (servico,vigencia,emolumentos,ferc,fadep,femp,ferrfis,total)
                VALUES (%s,99001,%s,'0,00','0,00','0,00','0,00',%s)""",(codigo,valor,valor))
    return casa


@pytest.mark.parametrize('layout',['novo','antigo'])
def test_jornada_atendimento_nota_reingresso_caixa_e_entrega(jornada,layout):
    casa=jornada;casa['db'].set_settings({'layout_padrao':layout})
    b=Balcao(casa['app'],'elisa',casa);mid=_matricula(casa)
    registros=[];problemas=[]
    saida=Path(os.environ['CG_JORNADA_OUT'])/layout if os.environ.get('CG_JORNADA_OUT') else None
    if saida:saida.mkdir(parents=True,exist_ok=True)
    def ver(nome,url):
        r=b.get(url,follow_redirects=True);assert r.status_code==200,(nome,r.status_code)
        h=r.get_data(as_text=True);registros.append({'etapa':nome,'url':url,'status':r.status_code})
        if saida:(saida/(nome+'.html')).write_text(h,'utf-8')
        return h
    def exigir(condicao,mensagem):
        if not condicao:problemas.append(mensagem)

    inicio=ver('01_entrada','/atendimentos')
    exigir('Entrada de caixa e protocolo geral' in inicio,'O nome do módulo não explica caixa e protocolo geral.')
    novo=destino(inicio,'Novo atendimento');assert novo
    ver('02_novo',novo)
    pid=abrir_protocolo(b,atribuicao='RI',previsao_entrega=date.today().isoformat())
    ficha=f'/atendimentos/{pid}';geral=f'/caixa/protocolos/{pid}'
    h=ver('03_atendimento',ficha)
    b.post(ficha+'/responsavel')
    dono=_um(casa,'SELECT u.username FROM at_responsaveis a JOIN users u ON u.id=a.usuario_id WHERE protocolo_id=%s',(pid,))
    assert dono['username']=='elisa'
    prenotar=destino(h,'Prenotar este título');assert prenotar
    ver('04_prenotar',prenotar)
    r=b.post('/registro-imoveis/protocolo',{'apresentante':INTERESSADO,
        'natureza_titulo':'AVERBAÇÃO','objeto':'Averbação fictícia de conferência',
        'livro_destino':'2','telefone':'(99) 98888-7777','matricula_numero':'4099',
        'cx_protocolo_id':str(pid)},seguir=False)
    assert r.status_code==302
    rp=_um(casa,'SELECT * FROM ri_protocolos ORDER BY id DESC LIMIT 1');rid=rp['id']
    assert _um(casa,'SELECT count(*) n FROM cx_protocolos')['n']==1
    assert _um(casa,'SELECT ri_protocolo_id FROM cx_protocolos WHERE id=%s',(pid,))['ri_protocolo_id']==rid
    ver('05_documentos',ficha+'?aba=documentos')
    pdf=b'%PDF-1.4\n% Documento ficticio para ensaio\n'
    b.post(geral+'/documentos',{'tipo':'TITULO','documento':(io.BytesIO(pdf),'titulo-ficticio.pdf')})
    ver('06_analise',ficha+'?aba=analise')
    nota=f'/registro-imoveis/protocolo/{rid}/nota'
    ver('07_nota',nota)
    r=b.post(nota,{'exigencias':'Apresentar documento complementar fictício.\nConferir a informação documental fictícia.',
        'fundamentacao':'Fundamento fictício do ensaio, sem efeito real.','data_nota':date.today().isoformat()},seguir=False)
    assert r.status_code==302
    n=_um(casa,'SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=%s',(rid,))
    documento=b.get(r.headers['Location']+('?formato=odt' if '?' not in r.headers['Location'] else '&formato=odt'))
    assert 'Apresentar documento complementar' in texto_do_odt(documento.data)
    h=ver('08_em_exigencia',ficha)
    assert 'Conferir cumprimento' in h
    recusada=b.post(ficha+'/entrega',{'recebido_por':'RECEBEDOR FICTÍCIO','observacao':'Tentativa fictícia antes do cumprimento.',
        'documentos_conferidos':'1','assinaturas_selos':'1','arquivamento_conferido':'1'})
    assert 'Há exigência aguardando cumprimento' in recusada.get_data(as_text=True)
    b.post(geral+'/documentos',{'tipo':'OUTRO','descricao':'Documento complementar fictício do cumprimento.',
        'documento':(io.BytesIO(pdf+b'complemento'),'complemento-ficticio.pdf')})
    arquivo=_um(casa,"SELECT id,original_name FROM attachments WHERE entity_type='PROTOCOLO' AND entity_id=%s ORDER BY id DESC LIMIT 1",(pid,))
    assert arquivo['original_name']=='complemento-ficticio.pdf'
    anexo=arquivo['id']
    for ordem in (1,2):
        b.post(ficha+'/exigencia',{'origem':'RI','nota_id':str(n['id']),'ordem':str(ordem),
            'estado':'CONFERIDO','anexo_id':str(anexo),'observacao':'Evidência fictícia conferida no ensaio.'})
    ver('09_conferencias',ficha+'?aba=analise')
    b.post(f"/registro-imoveis/notas/{n['id']}/reingresso",{'data_reingresso':date.today().isoformat(),
        'observacao':'Documentos fictícios apresentados e conferidos.'})
    assert _um(casa,'SELECT situacao FROM ri_notas_devolutivas WHERE id=%s',(n['id'],))['situacao']=='CUMPRIDA'
    ver('10_requalificacao',ficha+'?aba=analise')
    b.post(f'/registro-imoveis/protocolo/{rid}/qualificar',{'fundamentacao':'Conferência fictícia concluída.'})
    h=ver('11_apto',ficha)
    exigir(destino(h,'Preparar o ato')==f'/registro-imoveis/{mid}','A ficha apta não oferece o caminho correto para preparar o ato.')
    acrescentar(b,pid,990108);acrescentar(b,pid,990109);abrir_caixa(b)
    p=_um(casa,'SELECT * FROM cx_protocolos WHERE id=%s',(pid,));numero=p['numero']
    _deposito(b,'50,00',protocolo=numero)
    d=_um(casa,'SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1')
    b.post('/caixa/depositos',{'acao':'usar','deposito_id':str(d['id']),'valor_usar':'50,00','protocolo':numero})
    h=ver('12_saldo',ficha+'?aba=financeiro')
    exigir('R$ 50,00' in h and 'R$ 20,00' in h,'A ficha não explica os R$ 50,00 aplicados e o saldo de R$ 20,00.')
    b.post(geral+'/itens',{'acao':'quitar_todos','forma_pagamento':'PIX'})
    ver('13_pago',ficha+'?aba=financeiro')
    recibo=b.post(geral+'/recibo',{'formato':'odt'})
    assert recibo.mimetype=='application/vnd.oasis.opendocument.text'
    # Os R$ 50,00 do depósito já entraram antes; o recebimento direto é R$ 20,00.
    assert _um(casa,'SELECT valor_total FROM cx_recibos WHERE protocolo_id=%s',(pid,))['valor_total']=='20,00'
    recibo_deposito=b.post(f"/caixa/recibo/{d['lancamento_id']}",{'formato':'odt'})
    assert recibo_deposito.mimetype=='application/vnd.oasis.opendocument.text'
    assert '50,00' in texto_do_odt(recibo_deposito.data)
    caixa_antes=_ler(casa,'SELECT id,valor,hash_lancamento FROM cx_lancamentos ORDER BY id')
    itens=_ler(casa,'SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id',(pid,))
    assert all(i['quitado'] for i in itens)
    r=b.post(f'/registro-imoveis/{mid}/atos',{'tipo':'AV','data_ato':date.today().isoformat(),
        'natureza_titulo':'AVERBAÇÃO','teor':'Averbação inteiramente fictícia da jornada de treinamento.',
        'protocolo':str(rp['numero']),'protocolo_id':str(pid),'protocolo_selo':str(pid),
        'protocolo_item_id':str(itens[0]['id']),'codigo_tj':'16.9',
        'gerar_arquivamento':'1','folhas_arquivamento':'1'})
    ato=_um(casa,'SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1',(mid,))
    assert ato and not ato['cancelado'],r.get_data(as_text=True)[-2000:]
    assert ato['selo_texto'] and ato['selo_arquivamento']
    assert _um(casa,'SELECT situacao FROM ri_protocolos WHERE id=%s',(rid,))['situacao']=='ENCERRADO'
    h=ver('14_registrado',ficha)
    exigir('Conferir arquivamento e entrega' in h,'O próximo passo se perde após o ato ser registrado.')
    h=ver('15_entrega',ficha+'?aba=atos')
    exigir('name="recebido_por"' in h,'O serviço pago não tem formulário claro para registrar a entrega.')
    if not problemas:
        b.post(ficha+'/entrega',{'recebido_por':'RECEBEDOR FICTÍCIO DO ENSAIO',
            'observacao':'Falta confirmar as conferências obrigatórias.'})
        assert _um(casa,"SELECT count(*) n FROM audit_logs WHERE action='ATENDIMENTO_ENTREGUE'")['n']==0
        r=b.post(ficha+'/entrega',{'recebido_por':'RECEBEDOR FICTÍCIO DO ENSAIO',
            'documentos_conferidos':'1','assinaturas_selos':'1','arquivamento_conferido':'1',
            'observacao':'Entrega fictícia dos documentos e do resultado do serviço.'})
        assert r.status_code==200
        assert _um(casa,'SELECT situacao FROM cx_protocolos WHERE id=%s',(pid,))['situacao']=='ENTREGUE'
        ver('16_entregue',ficha)
        h=ver('17_historico',ficha+'?aba=historico')
        assert 'Entrega registrada' in h
        # Repetir o mesmo POST não cria outra entrega ou movimento.
        b.post(ficha+'/entrega',{'recebido_por':'OUTRO RECEBEDOR FICTÍCIO','documentos_conferidos':'1',
            'assinaturas_selos':'1','arquivamento_conferido':'1','observacao':'Repetição fictícia da confirmação.'})
        assert _um(casa,"SELECT count(*) n FROM audit_logs WHERE action='ATENDIMENTO_ENTREGUE'")['n']==1
    # O depósito entrou uma vez; sua aplicação não vira outra entrada.
    assert caixa_antes==_ler(casa,'SELECT id,valor,hash_lancamento FROM cx_lancamentos ORDER BY id')
    assert len(_ler(casa,'SELECT id FROM cx_depositos'))==1
    assert _um(casa,'SELECT saldo FROM cx_depositos WHERE id=%s',(d['id'],))['saldo']=='0,00'
    assert len(_ler(casa,'SELECT id FROM ri_qualificacoes WHERE protocolo_id=%s',(rid,)))==2
    if saida:(saida/'resultado.json').write_text(json.dumps({'etapas':registros,'problemas':problemas},ensure_ascii=False,indent=2),'utf-8')
    assert not problemas,'\n'.join(problemas)


def test_entrega_recusa_item_a_quitar_sem_mover_o_caixa(casa):
    b=Balcao(casa['app'],'elisa',casa)
    pid=abrir_protocolo(b,atribuicao='NOTAS');acrescentar(b,pid,990101)
    r=b.post(f'/atendimentos/{pid}/entrega',{'recebido_por':'RECEBEDOR FICTÍCIO',
        'observacao':'Tentativa fictícia antes da quitação do item.',
        'documentos_conferidos':'1','assinaturas_selos':'1','arquivamento_conferido':'1'})
    assert 'Há itens a quitar' in r.get_data(as_text=True)
    assert not _ler(casa,'SELECT id FROM cx_lancamentos')
    assert _um(casa,'SELECT situacao FROM cx_protocolos WHERE id=%s',(pid,))['situacao']=='A_PAGAR'


def test_entrega_e_auditoria_sao_atomicas(casa,monkeypatch):
    import identidade_do_robo as IDR
    b=Balcao(casa['app'],'elisa',casa)
    pid=abrir_protocolo(b,atribuicao='NOTAS');acrescentar(b,pid,990101);abrir_caixa(b)
    b.post(f'/caixa/protocolos/{pid}/itens',{'acao':'quitar_todos','forma_pagamento':'PIX'})
    original=IDR.registrar
    def falhar(con,**kw):
        if kw.get('action')=='ATENDIMENTO_ENTREGUE':raise RuntimeError('Falha fictícia de auditoria')
        return original(con,**kw)
    monkeypatch.setattr(IDR,'registrar',falhar)
    monkeypatch.setitem(casa['app'].config,'PROPAGATE_EXCEPTIONS',True)
    with pytest.raises(RuntimeError,match='fictícia'):
        b.post(f'/atendimentos/{pid}/entrega',{'recebido_por':'RECEBEDOR FICTÍCIO',
            'observacao':'Entrega fictícia para provar a transação da auditoria.',
            'documentos_conferidos':'1','assinaturas_selos':'1','arquivamento_conferido':'1'})
    assert _um(casa,'SELECT situacao FROM cx_protocolos WHERE id=%s',(pid,))['situacao']=='PAGO'
    assert _um(casa,"SELECT count(*) n FROM audit_logs WHERE action='ATENDIMENTO_ENTREGUE'")['n']==0


def test_auditor_nao_confirma_entrega_e_post_exige_csrf(casa):
    pid=abrir_protocolo(Balcao(casa['app'],'elisa',casa),atribuicao='NOTAS')
    c=Balcao(casa['app'],'elisa',casa)
    assert c.c.post(f'/atendimentos/{pid}/entrega',data={}).status_code in (400,403)
    casa['db'].create_user('conferente','LEITOR FICTÍCIO','Senha#12345','AUDITOR')
    leitor=Balcao(casa['app'],'conferente',casa)
    assert leitor.post(f'/atendimentos/{pid}/entrega').status_code==403

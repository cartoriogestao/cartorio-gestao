"""Fluxo e aprendizagem com pessoas e registros fictícios em banco de teste."""
import json
import re
from datetime import date,timedelta

import pytest

import atendimento_fluxo as FL
import treinamento as TR
from bd_nativo import banco
from conftest import cg_login


def token(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',html).group(1)


@pytest.fixture
def con(cg_casa):
    with cg_casa["db"].connect() as c:
        yield c


def cliente(casa):
    return casa["c"]


def atendimento(con,numero="EX-001",ri=False,**extras):
    bd=banco(con)
    rid=None
    if ri:
        rid=bd.escrever("""INSERT INTO ri_protocolos
            (numero,livro,data_prenotacao,data_limite,apresentante,situacao,criado_em)
            VALUES (999901,'1A',%s,%s,'Pessoa Fictícia','ABERTO',%s) RETURNING id""",
            (date.today().isoformat(),(date.today()+timedelta(days=10)).isoformat(),date.today().isoformat()))[0]["id"]
    pid=bd.escrever("""INSERT INTO cx_protocolos
        (numero,data_abertura,atribuicao,interessado,assunto,ri_protocolo_id,criado_em)
        VALUES (%s,%s,'RI','Pessoa Fictícia','Serviço Fictício',%s,%s) RETURNING id""",
        (numero,date.today().isoformat(),rid,date.today().isoformat()))[0]["id"]
    for k,v in extras.items():
        assert k in ("situacao","valor_total","valor_pago","tipo","origem")
        bd.escrever(f"UPDATE cx_protocolos SET {k}=%s WHERE id=%s",(v,pid))
    con.commit()
    return pid,rid


def test_catalogo_cobre_funcoes_modelos_e_papeis_com_roteiro_e_pratica():
    aulas=TR.aulas("ADMIN")
    assert len([a for a in aulas if a["tipo"]=="funcao"])>=200
    assert len([a for a in aulas if a["tipo"]=="ato"])>=50
    assert len({a["id"] for a in aulas})==len(aulas)
    for a in aulas:
        completa=TR.aula(a["id"],"ADMIN")
        assert len(completa["passos"])==4 and len(completa["questoes"])==3
        assert completa["versao"] and completa["objetivo"]
        if completa['tipo']=='ato':
            assert len(completa['estrutura_modelo'])>40
            assert '{{' not in completa['estrutura_modelo']


def test_permissoes_do_catalogo_e_busca_com_acentos():
    assert TR.aulas("USER","procuracao")
    pld=[a for a in TR.aulas("ADMIN") if a.get("endpoint","").startswith("pld_")]
    assert pld
    assert all(TR.aula(a["id"],"USER") is None for a in pld)
    assert TR.aulas("QUALQUER") == []


def test_portal_aula_e_legislacao_nao_chamam_api(cg_casa_logada,monkeypatch):
    import agente_provedores as AP
    monkeypatch.setattr(AP,"conversar",lambda *a,**k:pytest.fail("abriu a API"))
    c=cliente(cg_casa_logada)
    for url in ("/treinamento","/treinamento?busca=procuração","/treinamento/aula/roteiro-qualificacao","/treinamento/normas?busca=prenotação"):
        r=c.get(url);assert r.status_code==200
    html=c.get("/treinamento/aula/roteiro-caixa").get_data(as_text=True)
    assert "R$ 280,00" in html
    assert "resposta_0" in html and "não cria cliente" in html


def test_simulacao_so_grava_aprendizagem_e_auditoria(cg_casa_logada,con):
    c=cliente(cg_casa_logada);bd=banco(con)
    tabelas=("cx_protocolos","ri_atos","cx_lancamentos","rc_assentos")
    antes={t:bd.valor(f"SELECT count(*) FROM {t}") for t in tabelas}
    a=TR.aula("roteiro-caixa","ADMIN")
    html=c.get("/treinamento/aula/roteiro-caixa").get_data(as_text=True)
    r=c.post("/treinamento/aula/roteiro-caixa/pratica",data={"csrf_token":token(html),"versao":a["versao"],"resposta_0":"0","resposta_1":"1","resposta_2":"2"})
    assert r.status_code==200 and "Prática concluída" in r.get_data(as_text=True)
    assert antes=={t:bd.valor(f"SELECT count(*) FROM {t}") for t in tabelas}
    assert bd.valor("SELECT count(*) FROM tr_tentativas WHERE aprovado") == 1
    assert bd.valor("SELECT count(*) FROM audit_logs WHERE action='TREINAMENTO_PRATICA'") == 1


@pytest.mark.parametrize("respostas",[[0,0,0],[0,None,2]])
def test_pratica_incompleta_ou_errada_nao_conclui(con,cg_casa_logada,respostas):
    a=TR.aula("roteiro-nota","ADMIN")
    uid=banco(con).valor("SELECT id FROM users WHERE username='mario'")
    if None in respostas:
        with pytest.raises(ValueError):TR.avaliar(con,a,respostas,usuario_id=uid,agora="2026-11-07",versao=a["versao"])
    else:
        assert not TR.avaliar(con,a,respostas,usuario_id=uid,agora="2026-11-07",versao=a["versao"])["aprovado"]


def test_troca_de_versao_recusa_pratica_antiga(con,cg_casa_logada):
    with pytest.raises(ValueError,match="atualizada"):
        TR.avaliar(con,TR.aula("roteiro-nota","ADMIN"),[0,1,2],usuario_id=1,agora="2026",versao="antiga")


def test_ficha_tem_tres_eixos_abas_e_proxima_acao(cg_casa_logada,con):
    pid,rid=atendimento(con,ri=True,valor_total="480,00",valor_pago="200,00")
    c=cliente(cg_casa_logada)
    for aba in ("resumo","documentos","analise","atos","financeiro","historico"):
        r=c.get(f"/atendimentos/{pid}?aba={aba}");assert r.status_code==200,(aba,r.get_data(as_text=True)[-800:])
    html=c.get(f"/atendimentos/{pid}").get_data(as_text=True)
    assert "Registrar resultado da qualificação" in html and "R$ 280,00" in html
    assert "999901" in html and "Atendimento EX-001" in html
    assert '/treinamento/aula/roteiro-qualificacao' in html
    assert c.get(f"/atendimentos/{pid}?aba=inventada").status_code==404


def test_pago_nao_e_entregue_e_qualificacao_vem_do_motor_nativo(con):
    pid,rid=atendimento(con,ri=True,situacao="PAGO",valor_total="480,00",valor_pago="480,00")
    p=banco(con).um("SELECT * FROM cx_protocolos WHERE id=%s",(pid,))
    assert FL.etapa(con,p)[0]=="A_QUALIFICAR"
    assert FL.financeiro(p)["rotulo"]=="Pago"


def test_gets_sao_leitura_e_nao_designam_responsavel(cg_casa_logada,con):
    pid,_=atendimento(con,ri=True)
    c=cliente(cg_casa_logada);bd=banco(con)
    antes=(bd.valor("SELECT count(*) FROM at_responsaveis"),bd.valor("SELECT count(*) FROM at_exigencia_itens"),bd.valor("SELECT count(*) FROM tr_tentativas"))
    c.get("/atendimentos");c.get(f"/atendimentos/{pid}");c.get("/treinamento")
    depois=(bd.valor("SELECT count(*) FROM at_responsaveis"),bd.valor("SELECT count(*) FROM at_exigencia_itens"),bd.valor("SELECT count(*) FROM tr_tentativas"))
    assert antes==depois


def test_assumir_registra_responsavel_e_meu_trabalho(cg_casa_logada,con):
    pid,_=atendimento(con,ri=True);c=cliente(cg_casa_logada)
    r=c.post(f"/atendimentos/{pid}/responsavel",data={"csrf_token":token(c.get(f"/atendimentos/{pid}").get_data(as_text=True))})
    assert r.status_code==302
    assert FL.responsavel(con,pid)["full_name"]
    assert "EX-001" in c.get("/atendimentos?vista=meus").get_data(as_text=True)
    p=banco(con).um("SELECT * FROM cx_protocolos WHERE id=%s",(pid,))
    assert FL.etapa(con,p)[1]=="Em qualificação"


def test_usuario_nao_redistribui_terceiro_e_auditor_nao_grava(con,cg_casa_logada):
    pid,_=atendimento(con)
    bd=banco(con);m=bd.valor("SELECT id FROM users WHERE username='mario'")
    cg_casa_logada["db"].create_user("aluno","Aluno Fictício","Senha#12345","USER")
    aluno=bd.valor("SELECT id FROM users WHERE username='aluno'")
    FL.assumir(con,pid,usuario_id=m,autor_id=m,agora="2026",gerencia=True);con.commit()
    with pytest.raises(FL.FluxoError):FL.assumir(con,pid,usuario_id=aluno,autor_id=aluno,agora="2026")
    with pytest.raises(FL.FluxoError):FL.assumir(con,pid,usuario_id=m,autor_id=aluno,agora="2026")
    con.rollback()
    cg_casa_logada["db"].create_user("leitor","Leitor Fictício","Senha#12345","AUDITOR")
    c=cliente(cg_casa_logada);c.post("/logout",data={"csrf_token":token(c.get('/treinamento').get_data(as_text=True))})
    cg_login(c,"leitor","Senha#12345")
    html=c.get(f"/atendimentos/{pid}").get_data(as_text=True)
    assert c.post(f"/atendimentos/{pid}/responsavel",data={"csrf_token":token(html)}).status_code==403
    a=TR.aula("roteiro-caixa","AUDITOR")
    assert c.post("/treinamento/aula/roteiro-caixa/pratica",data={"csrf_token":token(html),"versao":a['versao']}).status_code==403
    assert c.get('/treinamento/equipe').status_code==403


def test_busca_e_paginacao_respeitam_filtro_antes_do_limite(con):
    for i in range(42):atendimento(con,numero=f"FICTICIO-{i:03}")
    assert len(FL.listar(con)["pedidos"])==40
    dados=FL.listar(con,busca="FICTICIO-041")
    assert dados["total"]==1 and dados["pedidos"][0]["numero"]=="FICTICIO-041"
    assert FL.listar(con,pagina=2)["pagina"]==2


def test_item_exige_evidencia_pertencente_e_preserva_decisao(con,cg_casa_logada):
    pid,rid=atendimento(con,ri=True);bd=banco(con)
    nid=bd.escrever("""INSERT INTO ri_notas_devolutivas
        (protocolo_id,numero,data_nota,exigencias,emitida_em)
        VALUES (%s,1,'2026-11-07',%s,'2026-11-07') RETURNING id""",(rid,json.dumps(["Apresentar documento fictício."])))[0]["id"]
    uid=bd.valor("SELECT id FROM users WHERE username='mario'")
    kwargs=dict(origem="RI",nota_id=nid,ordem=1,estado="APRESENTADO",anexo_id=None,observacao="Documento original conferido presencialmente.",usuario_id=uid,agora="2026-11-07")
    with pytest.raises(FL.FluxoError):FL.conferir_item(con,pid,**{**kwargs,"observacao":"ok"})
    with pytest.raises(FL.FluxoError):FL.conferir_item(con,pid,**{**kwargs,"nota_id":999999})
    FL.conferir_item(con,pid,**kwargs)
    assert bd.valor("SELECT estado FROM at_exigencia_itens WHERE protocolo_id=%s",(pid,))=="APRESENTADO"
    assert bd.valor("SELECT situacao FROM ri_notas_devolutivas WHERE id=%s",(nid,))=="ABERTA"
    assert bd.valor("SELECT count(*) FROM ri_qualificacoes WHERE protocolo_id=%s",(rid,))==0


def test_conteudo_alterado_invalida_conferencia_de_item(con,cg_casa_logada):
    pid,rid=atendimento(con,ri=True);bd=banco(con)
    nid=bd.escrever("""INSERT INTO ri_notas_devolutivas
        (protocolo_id,numero,data_nota,exigencias,emitida_em)
        VALUES (%s,1,'2026-11-07',%s,'2026-11-07') RETURNING id""",(rid,json.dumps(["Exigência fictícia original."])))[0]["id"]
    uid=bd.valor("SELECT id FROM users WHERE username='mario'")
    FL.conferir_item(con,pid,origem="RI",nota_id=nid,ordem=1,estado="CONFERIDO",anexo_id=None,observacao="Conferência presencial fictícia.",usuario_id=uid,agora="2026")
    assert FL.ficha(con,pid)["exigencias"][0]["controle"][0]["atual"]
    bd.escrever("UPDATE ri_notas_devolutivas SET exigencias=%s WHERE id=%s",(json.dumps(["Exigência fictícia alterada."]),nid))
    assert FL.ficha(con,pid)["exigencias"][0]["controle"][0]["atual"] is None


def test_documento_retirado_ou_de_outro_pedido_nao_comprova_cumprimento(con,cg_casa_logada):
    pid,rid=atendimento(con,ri=True);bd=banco(con)
    nid=bd.escrever("""INSERT INTO ri_notas_devolutivas
        (protocolo_id,numero,data_nota,exigencias,emitida_em)
        VALUES (%s,1,'2026-11-07',%s,'2026-11-07') RETURNING id""",
        (rid,json.dumps(['Documento fictício de cumprimento.'])))[0]['id']
    uid=bd.valor("SELECT id FROM users WHERE username='mario'")
    def anexo(entidade,eid,retirado=None):
        return bd.escrever("""INSERT INTO attachments
            (entity_type,entity_id,original_name,stored_name,stored_path,sha256,size_bytes,uploaded_at,retirado_em)
            VALUES (%s,%s,'Fictício.pdf','ficticio.pdf','inexistente','ficticio',0,'2026-11-07',%s) RETURNING id""",
            (entidade,eid,retirado))[0]['id']
    retirado=anexo('RI_PROTOCOLO',rid,'2026-11-07')
    estranho=anexo('PROTOCOLO',pid+9999)
    ativo=anexo('RI_PROTOCOLO',rid)
    dados=dict(origem='RI',nota_id=nid,ordem=1,estado='CONFERIDO',observacao='',usuario_id=uid,agora='2026')
    with pytest.raises(FL.FluxoError,match='retirado'):
        FL.conferir_item(con,pid,anexo_id=retirado,**dados)
    with pytest.raises(FL.FluxoError,match='pertencer'):
        FL.conferir_item(con,pid,anexo_id=estranho,**dados)
    FL.conferir_item(con,pid,anexo_id=ativo,**dados)
    assert [a['id'] for a in FL.ficha(con,pid)['anexos_ri']]==[ativo]


def test_anotacao_de_responsavel_existente_permanece_visivel_sem_vinculo_automatico(con,cg_casa_logada):
    pid,rid=atendimento(con,ri=True);bd=banco(con)
    bd.escrever("""INSERT INTO ex_anotacoes (tabela,item_id,texto,responsavel,criado_em)
        VALUES ('ri_protocolos',%s,'Revisão fictícia pendente.','Escrevente do acompanhamento','2026')""",(rid,))
    con.commit()
    c=cliente(cg_casa_logada)
    for url in ('/atendimentos',f'/atendimentos/{pid}'):
        assert 'Escrevente do acompanhamento' in c.get(url).get_data(as_text=True)
    assert FL.responsavel(con,pid) is None
    assert bd.valor('SELECT count(*) FROM at_responsaveis')==0


def test_rotas_exigem_login_e_csrf(cg_casa):
    c=cliente(cg_casa)
    assert c.get('/treinamento').status_code==302
    assert c.get('/atendimentos').status_code==302


def test_post_sem_csrf_nao_registra_pratica(cg_casa_logada,con):
    c=cliente(cg_casa_logada)
    r=c.post('/treinamento/aula/roteiro-caixa/pratica',data={
        'versao':TR.aula('roteiro-caixa','ADMIN')['versao'],
        'resposta_0':'0','resposta_1':'1','resposta_2':'2'})
    assert r.status_code in (400,403)
    assert banco(con).valor('SELECT count(*) FROM tr_tentativas')==0


def test_modelo_didatico_ensina_o_texto_sem_executar_marcadores(cg_casa_logada):
    a=next(a for a in TR.aulas('ADMIN') if a['tipo']=='ato')
    html=cliente(cg_casa_logada).get('/treinamento/aula/'+a['id']).get_data(as_text=True)
    assert 'Como se organiza o texto deste ato' in html and a['modelo'] in html
    assert 'referência didática' in html.lower()
    assert '[DATA DA ESCRITURA]' in html


def test_contexto_das_duas_molduras_oferece_aprendizagem(cg_casa_logada,con):
    pid,_=atendimento(con)
    c=cliente(cg_casa_logada)
    for layout in ('novo','antigo'):
        cg_casa_logada['db'].set_settings({'layout_padrao':layout})
        html=c.get(f'/caixa/protocolos/{pid}').get_data(as_text=True)
        assert 'Voltar à ficha do atendimento' in html
        assert 'Aprender esta função' in html


def test_trilhas_agrupam_o_primeiro_dia_e_as_atribuicoes(cg_casa_logada):
    c=cliente(cg_casa_logada)
    for t in ('primeiro-dia','notas','civil','imoveis','protesto','rtd-rpj'):
        r=c.get('/treinamento/trilha/'+t)
        assert r.status_code==200 and 'etapas concluídas' in r.get_data(as_text=True)
    assert c.get('/treinamento/trilha/externa').status_code==404


def test_orientacao_publicada_e_versionada_escapada_e_idempotente(cg_casa_logada,con):
    c=cliente(cg_casa_logada);bd=banco(con)
    antiga=TR.aula_corrente(con,'roteiro-caixa','ADMIN')
    url='/treinamento/aula/roteiro-caixa/orientacao'
    dados={'csrf_token':token(c.get(url).get_data(as_text=True)),
           'conteudo':'Orientação fictícia revisada. <script>alert("invalido")</script>',
           'fontes':'Procedimento fictício de conferência da casa.',
           'motivo':'Revisão de treinamento fictícia.','acao':'previa'}
    assert c.post(url,data=dados).status_code==200
    assert bd.valor('SELECT count(*) FROM tr_orientacoes')==0
    dados['acao']='publicar'
    assert c.post(url,data=dados).status_code==302
    atual=TR.aula_corrente(con,'roteiro-caixa','ADMIN')
    assert antiga['versao']!=atual['versao']
    html=c.get('/treinamento/aula/roteiro-caixa').get_data(as_text=True)
    assert '&lt;script&gt;' in html and '<script>alert(' not in html
    assert c.post(url,data=dados).status_code==302
    assert bd.valor('SELECT count(*) FROM tr_orientacoes')==1
    with pytest.raises(ValueError,match='atualizada'):
        TR.avaliar(con,atual,[0,1,2],usuario_id=1,agora='2026',versao=antiga['versao'])


def test_conferencia_concorrente_nao_sobrescreve_item_sem_revisao(con,cg_casa_logada):
    pid,rid=atendimento(con,ri=True);bd=banco(con)
    nid=bd.escrever("""INSERT INTO ri_notas_devolutivas
        (protocolo_id,numero,data_nota,exigencias,emitida_em)
        VALUES (%s,1,'2026-11-07',%s,'2026-11-07') RETURNING id""",(rid,json.dumps(['Exigência fictícia.'])))[0]['id']
    uid=bd.valor("SELECT id FROM users WHERE username='mario'")
    dados=dict(origem='RI',nota_id=nid,ordem=1,estado='APRESENTADO',anexo_id=None,
        observacao='Apresentação fictícia conferida.',usuario_id=uid,agora='2026')
    FL.conferir_item(con,pid,**dados)
    with pytest.raises(FL.FluxoError,match='atualizado'):
        FL.conferir_item(con,pid,**{**dados,'estado':'PENDENTE'})


def test_exporta_telas_ficticias_para_conferencia_visual(cg_casa_logada,con,tmp_path):
    import os
    from pathlib import Path
    saida=os.environ.get('CG_VISUAL_OUT')
    if not saida:
        return
    raiz=Path(saida);raiz.mkdir(parents=True,exist_ok=True)
    pid,rid=atendimento(con,ri=True,valor_total='480,00',valor_pago='200,00')
    c=cliente(cg_casa_logada)
    urls={'atendimentos':'/atendimentos','ficha':f'/atendimentos/{pid}',
          'analise':f'/atendimentos/{pid}?aba=analise','financeiro':f'/atendimentos/{pid}?aba=financeiro',
          'treinamento':'/treinamento','aula':'/treinamento/aula/roteiro-caixa',
          'trilha':'/treinamento/trilha/primeiro-dia'}
    static=Path(__file__).resolve().parents[1]/'static'
    for nome,url in urls.items():
        r=c.get(url);assert r.status_code==200
        html=r.get_data(as_text=True).replace('/static/',static.as_uri()+'/')
        (raiz/(nome+'.html')).write_text(html,encoding='utf-8')

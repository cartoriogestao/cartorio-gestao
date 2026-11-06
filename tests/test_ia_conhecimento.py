"""Fontes pertinentes, cobertura, literalidade e nota sem emitir dado real."""
from unittest.mock import Mock
import json

import pytest
import ia_conhecimento as C
import normativa as N
import ri_qualificacao_ia as Q
import ri_qualificacao_nota as NOTA


def test_nucleo_pronto_e_cedulas_disponiveis():
    s = C.situacao()
    assert s['pronta'] and s['normas'] >= 35 and s['artigos'] > 5000
    assert N.norma('Lei 10.931')['artigos']
    assert N.norma('credito rural')['artigos']


def test_busca_especial_nao_se_limita_as_quatro_normas_do_ri():
    resultados = C.selecionar('Cédula de crédito bancário e cancelamento de hipoteca')
    assert any('10.931' in a['norma'] for a in resultados)
    assert len(C.contexto('cancelamento de hipoteca')) <= C.LIMITE_DE_CONTEXTO


def test_entrada_malformada_e_limitada_antes_da_busca():
    # Nenhuma remoção de tags nem busca nos caracteres que excedem o teto.
    assert C.selecionar('<' * 100_000 + 'cédula de crédito bancário') == []


def test_ocr_e_transcricao_nao_recebem_instrucoes_de_qualificacao():
    for finalidade in C.SEM_ANALISE_JURIDICA:
        assert C.enriquecer('Transcreva literalmente.', [{'tipo':'user','texto':'hipoteca'}],
                            finalidade=finalidade) == 'Transcreva literalmente.'


def test_ajuda_e_robo_recebem_contexto_sem_duplica_lo():
    for finalidade in ('ajuda','robo','ri_qualificacao_ia','gestor_leitura'):
        a = C.enriquecer('Leia as fontes.', [{'tipo':'user','texto':'cancelamento de hipoteca'}],
                        finalidade=finalidade)
        assert C.MARCA in a
        assert C.enriquecer(a, [], finalidade=finalidade) == a
    assert C.enriquecer('Instrução.', [{'tipo':'user','texto':C.MARCA}],
                        finalidade='ri_qualificacao_ia') == 'Instrução.'


def test_artigo_inexistente_e_trecho_inventado_nao_sao_conferidos():
    assert not C.conferir_referencia({'norma':'LRP','artigo':'99999','trecho':'texto inventado'})['conferida']
    assert not C.conferir_referencia({'norma':'LRP','artigo':'198','trecho':'texto inventado que nao existe na lei'})['conferida']
    a = N.artigo('LRP','198',inteiro=True)
    r = C.conferir_referencia({'norma':'LRP','artigo':'198','trecho':a['texto'][:120]})
    assert r['conferida'] and 'art. 198' in r['citacao']


def test_qualificacao_retomada_depende_do_acervo(monkeypatch):
    assert Q.SUSPENSA_POR_BASE_NORMATIVA is False
    assert Q.motivo_da_suspensao() is None
    monkeypatch.setattr(C,'situacao',lambda:{'pronta':False})
    assert 'incompleta' in Q.motivo_da_suspensao()


def test_formato_estruturado_preserva_referencia_para_validar():
    refs=[{'norma':'LRP','artigo':'198','trecho':'trecho sintético'}]
    r=Q._ler_resposta(json.dumps({'exigencias':[{'exigencia':'Apresentar título.',
        'referencias_normativas':refs}],'conferidos':[]}))
    assert r['exigencias'][0]['referencias_normativas']==refs


def test_fundamento_nao_conferido_exige_confirmacao_humana(monkeypatch):
    p={'situacao':Q.PRONTA,'resultado':{'exigencias':[{'exigencia':'Apresentar título.',
       'fundamento':'A conferir','fundamento_conferido':False}]}}
    bd=Mock()
    monkeypatch.setattr(Q,'banco',lambda c:bd)
    monkeypatch.setattr(Q,'mostrar',lambda *a:p)
    with pytest.raises(Q.QualificacaoIAError,match='fonte oficial'):
        Q.levar(None,1,[(0,'')],usuario='Teste')
    bd.escrever.assert_not_called()
    assert Q.levar(None,1,[(0,'')],usuario='Teste',fundamentos_confirmados=[0])
    assert bd.escrever.call_count==1


def test_previa_usa_modelo_da_casa_sem_numerar_nem_assinar(monkeypatch):
    bd=Mock()
    bd.um.return_value={'numero':'123','data_prenotacao':'2026-11-06',
                        'data_limite':'2026-12-01','apresentante':'<script>alert(1)</script>'}
    monkeypatch.setattr(NOTA,'banco',lambda c:bd)
    ler_modelo=Mock(return_value='MODELO DA CASA {{ nota.numero }} {{ protocolo.numero }} '
        '{{ protocolo.apresentante }} {{ exigencias_odf }} {{ serventia.substituta }}')
    monkeypatch.setattr(NOTA.MODELOS,'corpo_de',ler_modelo)
    texto=NOTA.previa(None,{'protocolo_id':1,'resultado':{'exigencias':[
        {'exigencia':'Apresentar <b>original</b>.','fundamento':'LRP, art. 198'}]}},
        lambda:{'unit_name':'Cartório Exemplo','ri_substituta':'PESSOA QUE NAO ASSINOU'})
    assert 'MODELO DA CASA' in texto and 'RASCUNHO' in texto
    assert '<script>' not in texto and '&lt;b&gt;' in texto
    assert 'PESSOA QUE NAO ASSINOU' not in texto
    ler_modelo.assert_called_once_with(None,'RI_NOTA')
    bd.escrever.assert_not_called()

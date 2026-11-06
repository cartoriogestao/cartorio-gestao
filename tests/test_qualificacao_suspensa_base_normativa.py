"""Suspensao no codigo: aviso, bloqueio do dominio, da fila e dos botoes."""
from pathlib import Path
from unittest.mock import Mock
import pytest
from jinja2 import Environment, FileSystemLoader, ChoiceLoader, DictLoader
import ri_qualificacao_ia as QIA


@pytest.fixture(autouse=True)
def simular_suspensao_expressa(monkeypatch):
    """O bloqueio de emergência continua testado após a retomada autorizada."""
    monkeypatch.setattr(QIA, 'SUSPENSA_POR_BASE_NORMATIVA', True)


def test_suspensao_padrao_e_aviso_antes_de_banco_ou_chave(monkeypatch):
    monkeypatch.setattr(QIA, 'banco', Mock(side_effect=AssertionError('nao consulta')))
    assert QIA.SUSPENSA_POR_BASE_NORMATIVA is True
    aviso = QIA.por_que_nao(None, None)
    for trecho in ['suspensa', 'normativas estaduais', 'Lei de Registros Públicos',
                   'demais leis', 'cédulas de crédito', 'manualmente']:
        assert trecho in aviso

@pytest.mark.parametrize('acao', ['pedir', 'levar'])
def test_pedido_e_aproveitamento_recusados_antes_de_gravar(monkeypatch, acao):
    bd = Mock(side_effect=AssertionError('nao consulta nem grava'))
    monkeypatch.setattr(QIA, 'banco', bd)
    with pytest.raises(QIA.QualificacaoIAError, match='temporariamente suspensa'):
        if acao == 'pedir':QIA.pedir(None, 42, anexos_ids=[1])
        else:QIA.levar(None, 42, [(0, 'Texto ficticio')], usuario='Teste')
    bd.assert_not_called()

@pytest.mark.parametrize('funcao', [QIA.preenchimento, QIA.preenchimento_positiva])
def test_rascunho_antigo_nao_preenche_formulario(monkeypatch, funcao):
    mostrar = Mock(side_effect=AssertionError('nao consulta'))
    monkeypatch.setattr(QIA, 'mostrar', mostrar)
    assert funcao(None, '42', 1) is None
    mostrar.assert_not_called()


def test_pedido_pendente_nao_e_enviado_ao_provedor(monkeypatch, tmp_path):
    con, bd, ia = Mock(), Mock(), Mock()
    bd.um.return_value = {'id': 42, 'situacao': QIA.PENDENTE}
    monkeypatch.setattr(QIA.banco_pg, 'conectar', lambda *a, **k: con)
    monkeypatch.setattr(QIA, 'Banco', lambda c: bd)
    monkeypatch.setattr(QIA, 'init_schema', lambda c: None)
    montar = Mock(side_effect=AssertionError('nao le documentos'))
    monkeypatch.setattr(QIA, '_montar_conversa', montar)
    QIA.executar('banco-ficticio', tmp_path, 42, conversar=ia)
    ia.assert_not_called();montar.assert_not_called()
    assert "situacao='ERRO'" in bd.escrever.call_args.args[0]
    assert 'cédulas de crédito' in bd.escrever.call_args.args[1][1]


def ambiente():
    raiz = Path(__file__).resolve().parent.parent / 'templates'
    env = Environment(loader=ChoiceLoader([DictLoader({'base.html': '{% block content %}{% endblock %}'}), FileSystemLoader(str(raiz))]), autoescape=True)
    env.globals['url_for'] = lambda nome, **kw: '/' + nome
    return env


def test_quadro_mostra_aviso_e_nao_oferece_pedir():
    qa = {'suspensao': QIA.AVISO_DA_SUSPENSAO, 'cabe': True,
          'bloqueio': QIA.AVISO_DA_SUSPENSAO, 'andamento': None,
          'historico': [], 'teto': None, 'papeis': ['ADMIN']}
    html = ambiente().get_template('_qualificacao_ia.html').render(qualificacao_ia=qa, user={'role': 'ADMIN'})
    assert 'qualificacao-ia-suspensao' in html and 'cédulas de crédito' in html
    assert '<form' not in html

@pytest.mark.parametrize('exigencias', [[], [{'exigencia': 'Texto ficticio'}]])
def test_historico_fica_legivel_sem_aproveitar_rascunho(exigencias):
    p = {'id': 42, 'protocolo_id': 1, 'versao': 1, 'situacao': 'PRONTA',
         'resultado': {'exigencias': exigencias}, 'documentos': []}
    html = ambiente().get_template('ri_qualificacao_ia.html').render(p=p,
        linhas=['Texto ficticio'], suspensao=QIA.AVISO_DA_SUSPENSAO,
        user={'role':'ADMIN'}, papeis_que_pedem=['ADMIN'])
    assert 'cédulas de crédito' in html
    assert '<button' not in html and 'Levar para a qualificação positiva</a>' not in html

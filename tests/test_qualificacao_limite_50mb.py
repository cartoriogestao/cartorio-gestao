"""Fronteiras dos 50 MB da qualificacao e tamanho real do envio em base64."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
import agente_provedores as AP
import minuta_ia as MI
import ri_qualificacao_ia as QIA

MB = 1024 * 1024

@pytest.mark.parametrize('tamanhos', [(50 * MB,), (20 * MB, 30 * MB)])
def test_aceita_50_mb_no_total_sem_chamar_a_ia(monkeypatch, tamanhos):
    bd = preparar(monkeypatch, tamanhos)
    assert QIA.pedir(None, 42, anexos_ids=list(range(1, len(tamanhos) + 1))) == 123
    bd.escrever.assert_called_once()

@pytest.mark.parametrize('tamanhos', [(50 * MB + 1,), (20 * MB, 30 * MB + 1)])
def test_recusa_um_byte_acima_antes_de_gravar(monkeypatch, tamanhos):
    bd = preparar(monkeypatch, tamanhos)
    with pytest.raises(QIA.QualificacaoIAError, match='50 MB por pedido'):
        QIA.pedir(None, 42, anexos_ids=list(range(1, len(tamanhos) + 1)))
    bd.escrever.assert_not_called()
    bd.travar.assert_not_called()

def preparar(monkeypatch, tamanhos):
    bd = Mock()
    bd.um.return_value = None
    bd.escrever.return_value = [{'id': 123}]
    monkeypatch.setattr(QIA, 'banco', lambda _: bd)
    monkeypatch.setattr(QIA, 'init_schema', lambda _: None)
    monkeypatch.setattr(QIA, 'prenotacao', lambda *a: {'id': 42})
    monkeypatch.setattr(QIA, 'em_andamento', lambda *a: None)
    monkeypatch.setattr(QIA, 'matricula_da_prenotacao', lambda *a: None)
    monkeypatch.setattr(QIA, 'passou_do_teto_do_dia', lambda *a: None)
    docs = [{'anexo_id': i, 'nome': f'documento-ficticio-{i}.pdf',
             'tamanho': n, 'sha256': f'ficticio-{i}', 'origem': 'prenotacao'}
            for i, n in enumerate(tamanhos, 1)]
    monkeypatch.setattr(QIA, 'documentos', lambda *a: docs)
    return bd

def test_pdf_de_50_mb_cabe_no_transporte_com_contexto(tmp_path):
    caminho = tmp_path / 'ficticio.pdf'
    with caminho.open('wb') as f:
        f.write(b'%PDF-1.4\n')
        f.truncate(50 * MB)
    lido = MI._ler_arquivo(caminho, caminho.name)
    pedido = AP.montar_pedido(QIA.PROVEDOR, sistema=QIA.INSTRUCAO,
        conversa=[{'tipo': 'user', 'texto': 'Contexto ficticio ' * 10000,
                   'documentos': lido['documentos']}], ferramentas=[],
        modelo=QIA.MODELO, maximo_de_saida=QIA.MAXIMO_DE_SAIDA)
    corpo = json.dumps(pedido['corpo'], ensure_ascii=False).encode('utf-8')
    assert MI.LIMITE_DE_ENVIO < len(corpo) < QIA.LIMITE_DE_ENVIO
    assert QIA.LIMITE_DE_ENVIO < 128 * MB
    assert QIA.LIMITE_DOS_DOCUMENTOS == 50 * MB
    assert MI.LIMITE_DOS_DOCUMENTOS == 21 * MB

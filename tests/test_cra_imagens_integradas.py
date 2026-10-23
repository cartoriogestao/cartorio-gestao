"""Contrato t51 e fluxo completo com rede simulada e dados fictícios.

Veio com o hotfix 3.6.293.3 da produção; na migração (LH01, 21/10/2026) roda
no PostgreSQL e ganhou os testes da trava do recebimento e do lote antigo.
"""
import base64
from io import BytesIO
import re
from pathlib import Path
import threading
import time
import xml.etree.ElementTree as ET
import zipfile

import pytest
import banco_pg
import bd_nativo
import protesto_cra_imagens as IMG
import protesto_cra_xml as XML
import protesto_remessa as REM
from test_protesto_cra_xml import _arquivo_xml
from test_protesto_imagens import banco
from test_protesto_aviso_web import _con, _token, s  # noqa: F401

PDF = b'%PDF-1.4\n documento ficticio de teste\n%%EOF'


@pytest.fixture()
def con():
    """O banco do teste, FECHADO no fim. O recebimento pega a trava
    `pt_remessas.recebimento`, que vale para o banco inteiro: uma conexão
    esquecida aberta (num `pytest.raises`, por exemplo) a seguraria para os
    testes do outro processo do xdist."""
    c = banco()
    yield c
    c.close()


def _zip(*itens):
    mem = BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as z:
        for nome, bruto in itens:
            z.writestr(zipfile.ZipInfo(nome, date_time=(2026, 1, 1, 0, 0, 0)), bruto)
    return mem.getvalue()


def _xml(imagem=True, segundo_lote=False):
    root = ET.fromstring(_arquivo_xml())
    tr = root.find('.//tr')
    if imagem:
        tr.set('t51', base64.b64encode(_zip(('documento.pdf', PDF))).decode())
    if segundo_lote:
        root2 = ET.fromstring(_arquivo_xml())
        root2.find('.//hd').set('h08', '000002')
        root2.find('.//tr').set('t11', '000000000000002')
        root2.find('.//tr').set('t13', 'SEGUNDO')
        root2.find('.//tr').set('t51', base64.b64encode(_zip(('outro.pdf', PDF + b'2'))).decode())
        root.append(root2.find('comarca'))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _receber(con, bruto, pasta):
    return REM.receber_xml(con, bruto, ambiente='PRODUCAO', agora='2026-10-19T12:00:00',
        data_extenso='19 de outubro de 2026', sv={}, apontar=False, confirmar=False,
        pasta_de_arquivos=pasta)


def test_leitura_de_zip_nao_injeta_base64_nas_600_posicoes():
    previa = XML.ler(_xml())
    assert previa.titulos == 1 and len(previa.imagens) == 1
    assert previa.imagens[0]['arquivos'][0]['conteudo'] == PDF
    assert all(len(linha) == 600 for linha in previa.conteudo_fixo.splitlines())
    assert previa.hashes_lotes == XML.ler(_xml(False)).hashes_lotes


def test_anexa_a_cada_titulo_do_xml_sem_depender_do_nome_do_pdf(con, tmp_path):
    r = _receber(con, _xml(segundo_lote=True), tmp_path)
    assert r['recebidos'] == 2 and r['imagens_anexadas'] == 2
    rows = con.execute('SELECT * FROM attachments ORDER BY id').fetchall()
    assert [x['entity_id'] for x in rows] == [l['entraram'][0]['titulo_id'] for l in r['lotes']]
    assert [Path(x['stored_path']).read_bytes() for x in rows] == [PDF, PDF + b'2']


def test_mesmo_lote_com_e_sem_imagem_nao_cria_titulos_duplicados(con, tmp_path):
    _receber(con, _xml(False), tmp_path)
    with pytest.raises(REM.RemessaError, match='já entrou'):
        _receber(con, _xml(), tmp_path)
    assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 1


def test_lote_recebido_antes_do_293_3_nao_entra_de_novo_quando_volta_com_imagem(con, tmp_path):
    """Antes do 3.6.293.3 a chave do lote contava o t51; o lote que entrou
    assim tem outra chave, e só o conteúdo sem as 19 posições da imagem o
    reconhece. Sem isso, a CRA mandando de novo com a imagem apontaria os
    mesmos títulos outra vez."""
    _receber(con, _xml(False), tmp_path)
    bd = bd_nativo.banco(con)
    inicio = sum(XML.LARGURAS['tr'][:50])
    antigo = bd.um('SELECT id, conteudo FROM pt_remessas ORDER BY id')
    linhas = [l[:inicio] + 'X' * 19 + l[inicio + 19:] if l.startswith('1') else l
              for l in antigo['conteudo'].splitlines()]
    assert linhas != antigo['conteudo'].splitlines()
    bd.escrever("UPDATE pt_remessas SET origem_xml_chave='chave-de-antes-do-293-3', "
                'hash_arquivo=%s, conteudo=%s WHERE id=%s',
                ('hash-de-antes-do-293-3', '\n'.join(linhas), antigo['id']))
    with pytest.raises(REM.RemessaError, match='já entrou'):
        _receber(con, _xml(), tmp_path)
    assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 1
    assert con.execute('SELECT COUNT(*) FROM attachments').fetchone()[0] == 0


def _sem_a_ponte(con, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte — como a
    transação vai ficar quando a ponte sair (a trava única não existe)."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{con.schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def test_dois_cliques_no_receber_o_segundo_ve_o_primeiro_e_nao_o_erro_do_indice(con, tmp_path):
    """O segundo clique chega enquanto o primeiro ainda grava. Sem a trava
    antes da conferência, ele também não via o lote e ia ao INSERT — e o
    índice único devolvia um erro de banco (tela de erro), e não a frase de
    «já entrou» que diz ao balcão o que aconteceu."""
    con.commit()
    um, dois = _sem_a_ponte(con), _sem_a_ponte(con)
    vigia = _sem_a_ponte(con, autocommit=True)
    pid = dois.execute('SELECT pg_backend_pid()').fetchone()[0]
    dois.rollback()
    _receber(um, _xml(False), tmp_path)
    saida = {}

    def segundo():
        try:
            saida['r'] = _receber(dois, _xml(False), tmp_path)
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida['erro'] = erro
            dois.rollback()

    fio = threading.Thread(target=segundo)
    fio.start()
    for _ in range(200):       # o segundo tem de estar ESPERANDO (ou já ter ido)
        if not fio.is_alive() or vigia.execute(
                'SELECT count(*) FROM pg_locks WHERE pid=%s AND NOT granted',
                (pid,)).fetchone()[0]:
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    assert not fio.is_alive(), 'o segundo clique ficou preso'
    assert isinstance(saida.get('erro'), REM.RemessaError), saida
    assert 'já entrou' in str(saida['erro'])
    assert con.execute('SELECT COUNT(*) FROM pt_remessas').fetchone()[0] == 1


def test_imagens_nao_entram_antes_de_receber(con, tmp_path):
    visto = REM.conferir_xml(con, _xml(), 'PRODUCAO')
    assert visto['imagens'] == 1
    assert con.execute('SELECT COUNT(*) FROM attachments').fetchone()[0] == 0
    assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('nome,conteudo', [
    ('../fora.pdf', PDF), ('/fora.pdf', PDF), ('C:/fora.pdf', PDF),
    ('programa.exe', b'MZ'), ('documento.pdf', b'<html>conteudo indevido</html>'),
])
def test_zip_com_caminho_ou_formato_invalido_e_recusado(nome, conteudo):
    with pytest.raises(IMG.ImagemCraError):
        IMG.ler_zip(base64.b64encode(_zip((nome, conteudo))).decode())


def test_zip_muito_grande_e_recusado_antes_de_descompactar(monkeypatch):
    monkeypatch.setattr(IMG, 'LIMITE_TOTAL', 5)
    with pytest.raises(IMG.ImagemCraError, match='descompactadas'):
        IMG.ler_zip(base64.b64encode(_zip(('documento.pdf', PDF))).decode())


def test_base64_invalido_e_recusado():
    with pytest.raises(IMG.ImagemCraError, match='ZIP/base64'):
        IMG.ler_zip('!' * 200)


def test_falha_ao_salvar_imagens_desfaz_recebimento(con, tmp_path, monkeypatch):
    con.commit()
    def falhar(*args):
        raise OSError('disco indisponivel')
    monkeypatch.setattr(IMG, '_gravar', falhar)
    with pytest.raises(IMG.ImagemCraError):
        with con:
            _receber(con, _xml(), tmp_path)
    assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 0
    assert con.execute('SELECT COUNT(*) FROM pt_remessas').fetchone()[0] == 0


def test_cache_nao_aceita_caminho_forjado_nem_arquivo_alterado(tmp_path):
    token = IMG.guardar_xml(tmp_path, _xml())
    path = IMG.caminho_xml(tmp_path, token)
    assert path.read_bytes() == _xml()
    with pytest.raises(IMG.ImagemCraError):
        IMG.caminho_xml(tmp_path, '../arquivo')
    path.write_bytes(b'alterado')
    with pytest.raises(IMG.ImagemCraError, match='integridade'):
        IMG.caminho_xml(tmp_path, token)


def test_botao_pede_imagens_salva_xml_e_recebe_anexos(s, monkeypatch):
    import cra21_web as CRAW
    chamadas = []
    def trazer(qual, nome, amb, com_imagem=False):
        chamadas.append((qual, com_imagem))
        return _xml().decode()
    monkeypatch.setattr(CRAW, '_trazer', trazer)
    c = s['c']
    tela = c.get('/protesto/remessas').get_data(as_text=True)
    r = c.post('/protesto/remessas/da-cra', data={'csrf_token': _token(tela), 'o_que': 'pendentes'}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert chamadas == [('pendentes', True)]
    token = re.search(r'name="origem_xml_token" value="([0-9a-f]+)"', html).group(1)
    assert 'documento(s)/imagem(ns)' in html
    assert 'name="conteudo"' not in html
    with _con(s) as con:
        assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM attachments').fetchone()[0] == 0
    saved = c.get('/protesto/remessas/salvas/' + token)
    assert saved.status_code == 200 and saved.data == _xml()
    listado = c.get('/protesto/remessas').get_data(as_text=True)
    assert 'Conferir cópia salva' in listado
    r = c.post('/protesto/remessas/salvas/' + token + '/conferir',
        data={'csrf_token': _token(listado)}, follow_redirects=True)
    assert chamadas == [('pendentes', True)]  # retomada não consulta a CRA
    html = r.get_data(as_text=True)
    r = c.post('/protesto/remessas/receber', data={
        'csrf_token': _token(html), 'origem_xml_token': token, 'apontar': '0'}, follow_redirects=True)
    assert r.status_code == 200
    with _con(s) as con:
        anexo = con.execute("SELECT * FROM attachments WHERE entity_type='PT_TITULO'").fetchone()
        assert anexo and Path(anexo['stored_path']).read_bytes() == PDF
        aid = anexo['id']
    assert c.get('/protesto/imagens/' + str(aid)).data == PDF
    assert c.get('/protesto/remessas/salvas/' + token).data == _xml()


def test_falha_na_conferencia_preserva_copia_para_retomada(s, monkeypatch):
    import cra21_web as CRAW
    xml = _xml().replace(b' t18="', b' t18="X', 1)
    monkeypatch.setattr(CRAW, '_trazer', lambda *a, **k: xml.decode())
    tela = s['c'].get('/protesto/remessas').get_data(as_text=True)
    html = s['c'].post('/protesto/remessas/da-cra', data={
        'csrf_token': _token(tela), 'o_que': 'pendentes'}, follow_redirects=True).get_data(as_text=True)
    assert 'Conferir cópia salva' in html
    with _con(s) as con:
        assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 0


def test_usuario_sem_login_nao_abre_copia_salva(s):
    c = s['app'].test_client()
    assert c.get('/protesto/remessas/salvas/' + 'a' * 64).status_code in (302, 401, 403)


def test_sem_permissao_para_copia_nao_chama_a_cra(s, monkeypatch):
    import cra21_web as CRAW
    chamadas = []
    monkeypatch.setattr(CRAW, '_trazer', lambda *a, **k: chamadas.append(1))
    def falhar(*a):
        raise IMG.ImagemCraError('Não foi possível preparar a cópia local')
    monkeypatch.setattr(IMG, 'preparar_pasta', falhar)
    tela = s['c'].get('/protesto/remessas').get_data(as_text=True)
    s['c'].post('/protesto/remessas/da-cra', data={'csrf_token': _token(tela), 'o_que': 'pendentes'})
    assert chamadas == []


def test_falha_no_disco_devolve_xml_ao_navegador_sem_repetir_download(s, monkeypatch):
    import cra21_web as CRAW
    bruto = _xml()
    monkeypatch.setattr(CRAW, '_trazer', lambda *a, **k: bruto.decode())
    def falhar(*a):
        raise IMG.ImagemCraError('Sem espaço para a cópia')
    monkeypatch.setattr(IMG, 'guardar_xml', falhar)
    tela = s['c'].get('/protesto/remessas').get_data(as_text=True)
    r = s['c'].post('/protesto/remessas/da-cra', data={'csrf_token': _token(tela), 'o_que': 'pendentes'})
    assert r.status_code == 200 and r.data == bruto
    assert 'attachment' in r.headers['Content-Disposition']
    with _con(s) as con:
        assert con.execute('SELECT COUNT(*) FROM pt_titulos').fetchone()[0] == 0

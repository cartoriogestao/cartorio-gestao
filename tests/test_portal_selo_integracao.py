"""Worker Node -> PDF original fictício -> API Flask -> PostgreSQL isolado.

A navegação do portal é simulada; não substitui homologação do Chrome/SafeID.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server

from bd_nativo import banco
import despesas as DP
import despesas_portal_selo as PS
from tests.test_despesas_portal_selo_api import BASE, _preparar_executor
from tests.test_despesas_portal_selo_unidade import pdf_original
from tests.test_despesas_fluidez import _token


@pytest.mark.parametrize('fundo', ['FERJ', 'FERC', 'FADEP', 'FEMP', 'FERRFIS'])
def test_worker_confere_cadastra_pdf_e_retomada_nao_repete(cg_casa_logada, tmp_path, fundo):
    node = os.environ.get('CG_TEST_NODE') or shutil.which('node')
    if not node:
        pytest.skip('Node necessário para a integração do executor local')
    casa = cg_casa_logada
    _preparar_executor(casa['db'])
    csrf = _token(casa['c'], BASE)
    cookie = casa['c'].get_cookie(casa['app'].config['SESSION_COOKIE_NAME'])
    servidor = make_server('127.0.0.1', 0, casa['app'])
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        entrada = {'origem': f'http://127.0.0.1:{servidor.server_port}',
                   'pastaDados': str(tmp_path / 'worker'), 'fundo': fundo,
                   'pdf': base64.b64encode(pdf_original(fundo)).decode(),
                   'csrf': csrf, 'cookie': cookie.key + '=' + cookie.value}
        with patch.object(PS, 'esperado_dos_selos', return_value=12345):
            processo = subprocess.run([node, str(Path(__file__).with_name('portal_selo_integracao.mjs'))],
                input=json.dumps(entrada), text=True, capture_output=True, timeout=30)
        assert processo.returncode == 0, processo.stderr
        resultado = json.loads(processo.stdout)
        assert resultado['primeiro']['concluido'] and resultado['segundo']['concluido']
        assert resultado['posts'] == 2 and resultado['emissoes'] == 1
        with casa['db'].connect() as con:
            assert banco(con).valor('SELECT count(*) FROM dp_despesas') == 1
            d = dict(banco(con).um('SELECT * FROM dp_despesas'))
            assert d['situacao'] == (DP.AUTORIZADA if fundo in ('FERJ', 'FERC') else DP.AGUARDANDO)
            anexos = DP.anexos(con, d['id'])
            assert len(anexos) == 1
            assert Path(anexos[0]['stored_path']).read_bytes() == pdf_original(fundo)
    finally:
        servidor.shutdown()
        thread.join(timeout=5)
        servidor.server_close()

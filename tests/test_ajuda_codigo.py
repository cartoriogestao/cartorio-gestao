"""Lote 2: conferir código é leitura limitada, nunca execução ou escrita."""
from __future__ import annotations

import hashlib

import ajuda_codigo as CODIGO


def test_localiza_a_funcao_da_tela_no_arquivo_sugerido():
    trecho = CODIGO.inspecionar(
        {"onde": "ajuda_consultar", "titulo": "a tela falhou", "detalhe": ""},
        arquivo_sugerido="ajuda_web.py",
    )
    assert trecho is not None
    assert trecho.arquivo == "ajuda_web.py"
    assert "def ajuda_consultar" in trecho.texto
    assert trecho.sintaxe == "Python válido"


def test_usa_o_ultimo_ponto_da_casa_do_rastro():
    caminho = CODIGO.RAIZ / "ajuda.py"
    detalhe = (
        '  File "C:\\Python\\Lib\\urllib.py", line 10, in externo\n'
        f'  File "{caminho}", line 520, in consultar\n'
    )
    trecho = CODIGO.inspecionar({"detalhe": detalhe, "titulo": "", "onde": ""})
    assert trecho is not None
    assert trecho.arquivo == "ajuda.py"
    assert trecho.linha_central == 520


def test_caminho_de_fora_do_projeto_e_recusado(tmp_path):
    fora = tmp_path / "fora.py"
    fora.write_text("raise RuntimeError('nao ler')", encoding="utf-8")
    trecho = CODIGO.inspecionar({
        "detalhe": f'File "{fora}", line 1, in x',
        "titulo": "",
        "onde": "",
    })
    assert trecho is None


def test_a_leitura_nao_muda_o_arquivo():
    caminho = CODIGO.RAIZ / "ajuda_web.py"
    antes = hashlib.sha256(caminho.read_bytes()).hexdigest()
    trecho = CODIGO.inspecionar(
        {"onde": "ajuda_consultar", "titulo": "", "detalhe": ""},
        arquivo_sugerido="ajuda_web.py",
    )
    depois = hashlib.sha256(caminho.read_bytes()).hexdigest()
    assert trecho is not None
    assert antes == depois == trecho.sha256
    assert "SOMENTE LEITURA" in CODIGO.contexto_para_consulta(trecho)


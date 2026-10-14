"""
Testes do casamento entre a ficha no banco e o arquivo no disco.

O QUE ELES DEFENDEM
    O defeito que derrubou as 3.689 fichas de uma vez: o banco guarda
    `00003967.0001`, onde o `.0001` e o numero da PAGINA, e o disco guarda
    `00003967.0001.TIF`. Casar por igualdade exata falha em todas.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ri_imagens as IMG          # noqa: E402


def montar(tmp_path: Path, arquivos: list[str]) -> Path:
    for rel in arquivos:
        alvo = tmp_path / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(b"II*\x00")      # cabeçalho de TIFF, só para existir
    return tmp_path


# ------------------------------------------------------------------ chaves

def test_o_ponto_zero_zero_um_nao_e_extensao():
    # É o número da página. Mas como PODE ser lido como extensão, as duas
    # formas entram no índice.
    assert IMG.chaves("00003967.0001") == ["00003967.0001", "00003967"]


def test_chaves_ignoram_a_caixa():
    assert IMG.chaves("00003967.0001.TIF") == ["00003967.0001.tif", "00003967.0001"]


def test_nome_vazio_nao_gera_chave():
    assert IMG.chaves("") == [] and IMG.chaves(None) == []


# ---------------------------------------------------------------- o defeito

def test_arquivo_com_extensao_e_encontrado(tmp_path):
    # ESTE É O DEFEITO. Antes, nenhuma das imagens era localizada.
    raiz = montar(tmp_path, ["00000000/00003967.0001.TIF"])
    indice, _, _ = IMG.indexar(raiz)
    assert IMG.achar("00003967.0001", indice) is not None


def test_arquivo_sem_extensao_continua_sendo_encontrado(tmp_path):
    raiz = montar(tmp_path, ["00000000/00003967.0001"])
    indice, _, _ = IMG.indexar(raiz)
    assert IMG.achar("00003967.0001", indice) is not None


def test_extensao_em_caixa_alta_ou_baixa_da_no_mesmo(tmp_path):
    raiz = montar(tmp_path, ["a/00000002.0001.tif", "b/00000003.0001.TIF"])
    indice, _, _ = IMG.indexar(raiz)
    assert IMG.achar("00000002.0001", indice) is not None
    assert IMG.achar("00000003.0001", indice) is not None


def test_a_varredura_desce_mais_de_um_nivel(tmp_path):
    # A primeira versão descia um nível só, e a pasta do E-Ofício nem sempre
    # é plana.
    raiz = montar(tmp_path, ["00000000/lote1/sub/00003967.0001.TIF"])
    indice, arquivos, _ = IMG.indexar(raiz)
    assert arquivos == 1
    assert IMG.achar("00003967.0001", indice) is not None


def test_paginas_diferentes_da_mesma_matricula_nao_se_confundem(tmp_path):
    # O risco de casar pelo nome sem extensão: as páginas .0001 e .0002 da
    # mesma matrícula compartilham o prefixo 00000002.
    raiz = montar(tmp_path, ["p/00000002.0001.TIF", "p/00000002.0002.TIF"])
    indice, _, _ = IMG.indexar(raiz)
    a = IMG.achar("00000002.0001", indice)
    b = IMG.achar("00000002.0002", indice)
    assert a and b and a != b
    assert a.endswith("00000002.0001.TIF")
    assert b.endswith("00000002.0002.TIF")


def test_o_que_nao_existe_continua_nao_existindo(tmp_path):
    raiz = montar(tmp_path, ["p/00000002.0001.TIF"])
    indice, _, _ = IMG.indexar(raiz)
    assert IMG.achar("00009999.0001", indice) is None


# ------------------------------------------------------------ diagnóstico

def test_o_diagnostico_mostra_os_dois_lados(tmp_path):
    raiz = montar(tmp_path, ["00000000/00003967.0001.TIF",
                             "00000000/00000002.0001.TIF"])
    d = IMG.diagnostico(["00003967.0001", "00000002.0001", "00009999.0001"], raiz)
    assert d["raiz_existe"] is True
    assert d["arquivos"] == 2
    assert d["achadas"] == 2 and d["perdidas"] == 1
    assert d["exemplos_perdidos"] == ["00009999.0001"]
    assert any(x.endswith(".TIF") for x in d["exemplos_disco"])


def test_pasta_errada_se_explica_sozinha(tmp_path):
    # Nenhum casamento esperto acha arquivo que não está lá. O diagnóstico
    # precisa dizer isso, e não devolver zero calado.
    d = IMG.diagnostico(["00003967.0001"], tmp_path / "nao-existe")
    assert d["raiz_existe"] is False
    assert d["achadas"] == 0 and d["perdidas"] == 1
    assert d["exemplos_perdidos"] == ["00003967.0001"]


def test_nome_repetido_em_duas_pastas_e_denunciado(tmp_path):
    # A carga assume nome único entre as pastas — é a razão de indexar por
    # nome, já que o id_path não foi exportado. Se a suposição quebrar, melhor
    # descobrir aqui do que por uma ficha que abre a matrícula errada.
    raiz = montar(tmp_path, ["a/00003967.0001.TIF", "b/00003967.0001.TIF"])
    dup = IMG.duplicados(raiz)
    assert "00003967.0001.tif" in dup
    assert len(dup["00003967.0001.tif"]) == 2


def test_pasta_sem_duplicado_nao_acusa(tmp_path):
    raiz = montar(tmp_path, ["a/00000002.0001.TIF", "b/00000003.0001.TIF"])
    assert IMG.duplicados(raiz) == {}


def test_pillow_e_conferido_a_parte():
    # Ficha que não abre por falta do Pillow e ficha que não abre por caminho
    # errado são dois defeitos com o mesmo sintoma. A tela precisa separar.
    assert IMG.pillow_disponivel() in (True, False)

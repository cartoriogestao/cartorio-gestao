"""Leitor e identidade da remessa XML da CRA (prévia e recepção)."""
from __future__ import annotations

import html
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protesto_cra_xml as XML


def _arquivo_xml() -> bytes:
    linhas = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()
    linhas = linhas.decode("iso-8859-1").splitlines()
    partes = ['<?xml version="1.0" encoding="utf-8"?><remessa>',
              "<nome_arquivo>exemplo.xml</nome_arquivo><comarca CodMun=\"000001\">"]
    for tag, linha in zip(("hd", "tr", "tl"), linhas):
        inicio = 0
        atributos = []
        prefixo = "h" if tag == "hd" else "t"
        for i, largura in enumerate(XML.LARGURAS[tag], 1):
            valor = linha[inicio:inicio + largura].rstrip()
            atributos.append(f'{prefixo}{i:02}="{html.escape(valor, quote=True)}"')
            inicio += largura
        partes.append(f"<{tag} {' '.join(atributos)}/>")
    partes.append("</comarca></remessa>")
    return "".join(partes).encode("utf-8")


def test_xml_realista_projeta_600_posicoes_sem_gravar():
    previa = XML.ler(_arquivo_xml())
    assert previa.lotes == 1
    assert previa.titulos == 1
    assert all(len(linha) == 600 for linha in previa.conteudo_fixo.splitlines())
    assert len(previa.sha256) == 64
    assert len(previa.hashes_lotes) == 1


def test_identidade_do_lote_separa_ambientes_e_nao_depende_da_projecao():
    hash_lote = XML.ler(_arquivo_xml()).hashes_lotes[0]
    homolog = XML.chave_idempotencia("HOMOLOGACAO", hash_lote)
    producao = XML.chave_idempotencia("PRODUCAO", hash_lote)
    assert len(homolog) == 64
    assert homolog != producao
    with pytest.raises(XML.RemessaXmlError, match="Ambiente"):
        XML.chave_idempotencia("OUTRO", hash_lote)


def test_lote_xml_duplicado_no_mesmo_arquivo_e_recusado():
    bruto = _arquivo_xml()
    bloco = bruto.split(b'<comarca CodMun="000001">')[1].split(b'</comarca>')[0]
    bruto = bruto.replace(b'</comarca>', bloco + b'</comarca>')
    with pytest.raises(XML.RemessaXmlError, match="repete outro lote"):
        XML.ler(bruto)


def test_xml_com_delimitadores_escapados_da_cra():
    bruto = _arquivo_xml().replace(b'="', b'=&quot;').replace(b'" ', b'&quot; ')
    bruto = bruto.replace(b'"/>', b'&quot;/>')
    assert XML.ler(bruto).titulos == 1


def test_xml_com_soma_do_trailer_errada_e_recusado():
    bruto = _arquivo_xml().replace(b't05="00003"', b't05="00004"')
    with pytest.raises(XML.RemessaXmlError, match="somatório"):
        XML.ler(bruto)


def test_xml_com_dtd_e_recusado():
    bruto = _arquivo_xml().replace(b'<remessa>', b'<!DOCTYPE remessa><remessa>')
    with pytest.raises(XML.RemessaXmlError, match="DTD"):
        XML.ler(bruto)


@pytest.mark.parametrize("bruto,esperado", [
    (b'<?xml version="1.0"?><relatorio><codigo>0003</codigo><ocorrencia>SEM REMESSAS PENDENTES</ocorrencia></relatorio>', '0003'),
    (b'<?xml version="1.0"?><erro><codigo>1</codigo><mensagem>Falha na autenticacao</mensagem></erro>', 'autenticacao'),
])
def test_aviso_da_cra_em_arquivo_mostra_o_motivo_e_nao_erro_de_raiz(bruto, esperado):
    with pytest.raises(XML.RemessaXmlError, match=esperado) as erro:
        XML.ler(bruto)
    assert 'não contém remessas' in str(erro.value)


def test_atributo_desconhecido_na_raiz_continua_recusado():
    bruto = _arquivo_xml().replace(b'<remessa>', b'<remessa inesperado="1">')
    with pytest.raises(XML.RemessaXmlError, match='atributos não previstos.*inesperado'):
        XML.ler(bruto)

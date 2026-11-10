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


# O cabeçalho conta títulos; o corpo mantém uma linha por devedor.
def _xml_com_dois_devedores():
    from copy import deepcopy
    import xml.etree.ElementTree as ET
    raiz = ET.fromstring(_arquivo_xml())
    comarca = raiz.find("comarca")
    hd, primeiro, tl = list(comarca)
    primeiro.set("t22", "1")
    segundo = deepcopy(primeiro)
    segundo.set("t22", "2")
    segundo.set("t23", "BEATRIZ EXEMPLO DE SOUZA")
    segundo.set("t52", str(int(primeiro.get("t52")) + 1).zfill(4))
    comarca.insert(2, segundo)
    tl.set("t06", str(int(primeiro.get("t18")) * 2).zfill(18))
    tl.set("t08", str(int(segundo.get("t52")) + 1).zfill(4))
    return raiz, hd, primeiro, segundo, tl


@pytest.mark.parametrize("original", [False, True])
def test_cabecalho_conta_um_titulo_com_dois_devedores(original):
    import xml.etree.ElementTree as ET
    raiz, hd, _, _, tl = _xml_com_dois_devedores()
    hd.set("h11", "0000" if original else "0001")
    hd.set("h12", "0001" if original else "0000")
    tl.set("t05", str(sum(int(hd.get(f"h{i:02}")) for i in range(9, 13))).zfill(5))
    previa = XML.ler(ET.tostring(raiz))
    assert previa.titulos == 2  # registros preservados para o agrupador existente
    assert len(previa.conteudo_fixo.splitlines()) == 4
    assert previa.conteudo_fixo.splitlines()[2][296] == "2"


@pytest.mark.parametrize("campo", ["h10", "h11"])
def test_cabecalho_nao_pode_contar_devedor_seguinte_como_titulo(campo):
    import xml.etree.ElementTree as ET
    raiz, hd, _, _, tl = _xml_com_dois_devedores()
    hd.set(campo, "0002")
    tl.set("t05", str(sum(int(hd.get(f"h{i:02}")) for i in range(9, 13))).zfill(5))
    with pytest.raises(XML.RemessaXmlError, match="h10|indicações"):
        XML.ler(ET.tostring(raiz))


def test_cabecalho_conta_titulos_distintos_com_seus_devedores():
    from copy import deepcopy
    import xml.etree.ElementTree as ET
    raiz, hd, primeiro, segundo, tl = _xml_com_dois_devedores()
    outro = deepcopy(primeiro)
    outro.set("t22", "1")
    outro.set("t09", "TITULO-EXEMPLO-2")
    outro.set("t52", str(int(segundo.get("t52")) + 1).zfill(4))
    raiz.find("comarca").insert(3, outro)
    hd.set("h10", "0002")
    hd.set("h11", "0002")
    tl.set("t05", str(sum(int(hd.get(f"h{i:02}")) for i in range(9, 13))).zfill(5))
    tl.set("t06", str(int(primeiro.get("t18")) * 3).zfill(18))
    tl.set("t08", str(int(outro.get("t52")) + 1).zfill(4))
    assert XML.ler(ET.tostring(raiz)).titulos == 3

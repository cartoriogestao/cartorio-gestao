"""O arquivo do CCN contra o XSD v4 do CNB — 13/10/2026.

O que se guarda: o arquivo passa no XSD (o validador é o lxml, e não este
código); a ordem é a do `xs:sequence`; bloco sem o campo que o XSD exige não
vai (endereço sem IBGE, RG sem data de emissão, ficha sem imagem); e arquivo
que não valida é recusado antes de ir ao disco.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ccn_xml as CX  # noqa: E402

pytestmark = pytest.mark.skipif(not CX.situacao_do_formato()["pronto"],
                                reason="XSD ou lxml ausente")


def _pessoa(tmp_path, **campos):
    ficha = tmp_path / "ficha.jpg"
    ficha.write_bytes(b"\xff\xd8\xff\xe0ensaio")
    base = {"cpf": "00000000191", "nome": "MARIA DAS DORES", "dataRegistro": "2026-10-01",
            "estadoCivil": "Casado", "sexo": "F", "politicamenteexposta": False,
            "investigadaAcusadaTerrorismo": False, "fichaBloqueada": False,
            "ficha": {"dataficha": "2026-10-01", "numeroFicha": "963526"},
            "endereco": {"endereco": "RUA GRANDE", "cidade": "CIDADE EXEMPLO", "uf": "MA",
                         "ibgeCidade": "2198765"}}
    base.update(campos)
    return {"campos": base, "imagens": {"ficha": [str(ficha)], "foto": None, "digitais": []}}


def test_o_arquivo_passa_no_xsd_e_segue_a_ordem(tmp_path):
    xml = CX.montar([_pessoa(tmp_path)]).decode()
    assert xml.index("<estadoCivil>2</estadoCivil>") < xml.index("<cpf>") < xml.index("<endereco>") \
        < xml.index("<ficha>") < xml.index("<politicamenteExposta>")
    assert "<dataFicha>2026-10-01</dataFicha>" in xml


def test_bloco_incompleto_nao_vai_e_o_arquivo_continua_valido(tmp_path):
    p = _pessoa(tmp_path, endereco={"endereco": "RUA GRANDE", "uf": "MA"},
                documento={"tipo": "RG", "docIdentidade": "123", "orgaoEmissor": "SSP"})
    p["imagens"]["ficha"] = []
    xml = CX.montar([p]).decode()
    assert "<endereco>" not in xml and "<documento>" not in xml and "<ficha>" not in xml


def test_arquivo_invalido_nao_sai(tmp_path):
    with pytest.raises(CX.ArquivoInvalido):
        CX.validar(b"<pessoas><pessoa><nome>SEM CPF</nome></pessoa></pessoas>")


def test_o_xsd_que_viaja_e_o_mesmo_baixado_do_cnb():
    import hashlib
    sha = hashlib.sha256(CX.XSD.read_bytes()).hexdigest()
    assert sha == "1d63dfca48df18f040c9c73a6b713886951f97f52d85aa23ac8daa2bb0c915f3"

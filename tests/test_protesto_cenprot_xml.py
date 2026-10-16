"""O XML diário da CENPROT — o escritor, na forma medida (15/10/2026).

A prova grande é a ida e volta contra os 28 arquivos reais da casa (28 de 28
byte a byte), que não entram aqui porque trazem dados de devedores. Estes
testes guardam as regras que aquela medição fixou, com um título fictício.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

import protesto_cenprot_xml as X


def _titulo(**extra) -> dict:
    t = {
        "id": "21999990141243301260417",
        "cedente": {"nome": "LOJA EXEMPLO LTDA"},
        "sacador": {"nome": "LOJA EXEMPLO LTDA", "documento": "00000001000055",
                    "endereco": {"endereco": "RUA A, 1", "cep": "65000000",
                                 "cidade": "SAO LUIS", "uf": "MA"}},
        "nosso_numero": "123", "especie": "DMI", "numero_titulo": "77/1",
        "data_emissao": "2026-09-01", "data_vencimento": "2026-09-30",
        "tipo_moeda": "001", "valor": X.valor(108360), "saldo": X.valor(108360),
        "praca_protesto": "CIDADE EXEMPLO", "endosso": "G", "tipo_endosso": "M",
        "aceite": "N",
        "devedores": [{"nome": "MARIO EXEMPLO", "documento": "04785512388",
                       "intimado": True, "edital": False,
                       "endereco": {"endereco": "RUA GRANDE, 10",
                                    "bairro": "CENTRO",
                                    "cidade": "CIDADE EXEMPLO", "uf": "MA",
                                    "cep": "65936000"}}],
        "data_apresentacao": "2026-10-13", "protocolo": "2610130001",
        "data_protocolo": "2026-10-13", "ocorrencia": "2",
        "data_ocorrencia": "2026-10-16", "tipo_protesto": "C",
        "motivo_protesto": "1", "tipo_livro": "G", "num_livro": "9",
        "num_folha": "183", "acervo_herdado": False, "anuencia": False,
        "instrumento": b"0\x82PKCS7",
    }
    t.update(extra)
    return t


def _arquivo(letra="P", **extra) -> bytes:
    return X.escrever(letra=letra, uf="MA", comarca="2199999", cartorio="01",
                      apresentantes=[{"codigo": "748", "nome": "BANCO EXEMPLO",
                                      "documento": "00000001000055",
                                      "tipo_apresentante": "0",
                                      "titulos": [_titulo(**extra)]}])


def test_a_forma_do_arquivo_e_a_medida():
    b = _arquivo()
    assert b.startswith("﻿".encode("utf-8") +
                        b'<?xml version="1.0" encoding="utf-8"?>\r\n')
    assert b"\n" not in b.replace(b"\r\n", b"")      # só CRLF
    assert not b.endswith(b"\r\n")                   # termina sem quebra
    assert b"  <estado uf=\"MA\">" in b              # dois espaços
    assert b'<estados total="1" versao="1.23-geral">' in b
    assert b"<complemento />" in b                   # vazio auto-fechado


def test_a_ordem_dos_campos_do_titulo_e_a_medida():
    raiz = ET.fromstring(_arquivo())
    t = raiz.find(".//titulo")
    assert [f.tag for f in t] == [
        "cedente", "sacador", "nosso_numero", "especie", "numero_titulo",
        "data_emissao", "data_vencimento", "tipo_moeda", "valor", "saldo",
        "praca_protesto", "endosso", "tipo_endosso", "aceite", "devedores",
        "data_apresentacao", "protocolo", "data_protocolo", "ocorrencia",
        "data_ocorrencia", "tipo_protesto", "motivo_protesto", "tipo_livro",
        "num_livro", "num_folha", "acervo_herdado", "anuencia",
        "instrumento_eletronico"]
    dv = t.find("devedores/devedor")
    assert [f.tag for f in dv] == ["nome", "CPF", "intimado", "edital",
                                   "edital_motivo", "enderecos"]


def test_o_D_nao_leva_motivo_livro_nem_instrumento_e_o_cancelamento_leva_a_averbacao():
    raiz = ET.fromstring(_arquivo("D", ocorrencia="A",
                                  data_averbacao="2026-10-15"))
    tags = [f.tag for f in raiz.find(".//titulo")]
    assert "motivo_protesto" not in tags and "tipo_livro" not in tags
    assert "instrumento_eletronico" not in tags
    assert tags.index("data_averbacao") == tags.index("acervo_herdado") + 1


def test_cedente_sem_documento_vai_sem_a_tag():
    ced = ET.fromstring(_arquivo()).find(".//titulo/cedente")
    assert ced.find("CNPJ") is None and ced.find("CPF") is None
    sac = ET.fromstring(_arquivo()).find(".//titulo/sacador")
    assert sac.findtext("CNPJ") == "00000001000055"


def test_o_instrumento_vai_em_base64():
    import base64
    t = ET.fromstring(_arquivo()).find(".//titulo")
    assert base64.b64decode(t.findtext("instrumento_eletronico")) == b"0\x82PKCS7"


def test_valor_tem_quatro_casas():
    assert X.valor(108360) == "1083.6000"
    assert X.valor(5) == "0.0500"


def test_nome_do_arquivo():
    assert X.nome_do_arquivo(uf="MA", comarca="2199999", cartorio="01",
                             letra="P", dia="2026-10-16") == \
        "MA-2199999-01-P-20261016-01.xml"
    with pytest.raises(X.CenprotXmlError):
        X.nome_do_arquivo(uf="MA", comarca="2199999", cartorio="01",
                          letra="A", dia="2026-10-16")


def test_escape_de_nome_com_e_comercial():
    b = _arquivo(cedente={"nome": "A & B LTDA"})
    assert b"A &amp; B LTDA" in b

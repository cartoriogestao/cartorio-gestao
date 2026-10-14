"""Envio SOAP de confirmação e retorno à CRA (mock de rede)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED
import cra21_api as API
import protesto_cra_envio as ENV


def test_user_dados_e_o_arquivo_em_xml():
    """Mudou em 13/10/2026: o texto de 600 posições a CRA recusa («10000 —
    arquivo XML corrompido», homologação, 11/10); vai o XML."""
    texto = (Path(__file__).parent / "cra_confirmacao_exemplo.txt").read_text(
        encoding="latin-1")
    xml = ENV.user_dados_do_arquivo(texto, "SDTBFOCRT")
    assert xml.splitlines()[1] == "<confirmacao>"
    with pytest.raises(ENV.CraEnvioError):
        ENV.user_dados_do_arquivo("linha\n")
    with pytest.raises(ENV.CraEnvioError):
        ENV.user_dados_do_arquivo("   ")


def test_interpretar_codigo_ok():
    r = ENV.interpretar_resposta_envio(
        "<relatorio><codigo>0000</codigo></relatorio>", o_que="teste")
    assert r["ok"] and r["codigo"] == "0000"


def test_interpretar_codigo_recusado():
    with pytest.raises(API.CraRecusou) as e:
        ENV.interpretar_resposta_envio(
            "<relatorio><codigo>0002</codigo></relatorio>", o_que="teste")
    assert "0002" in str(e.value)


def test_auto_homolog_ligado_por_padrao():
    assert ENV.auto_envio_ligado(CRED.HOMOLOGACAO, lambda k, d: d)
    assert not ENV.auto_envio_ligado(
        CRED.HOMOLOGACAO, lambda k, d: "0" if k == "cra_auto_enviar_homolog" else d)


def test_enviar_confirmacao_monta_envelope(monkeypatch, tmp_path):
    capturado = {}

    class Resposta:
        def read(self):
            return b"<return><relatorio><codigo>0000</codigo></relatorio></return>"

        @property
        def status(self):
            return 200

        # O transporte comum (`centrais_http`, 05/10/2026) lê os cabeçalhos da
        # resposta; o falso de 30/09 não os tinha, e o teste caía antes de
        # chegar ao que ele confere — o envelope.
        def getheaders(self):
            return []

    class Conexao:
        ultimo_corpo = b""

        def __init__(self, *a, **k):
            pass

        def request(self, metodo, caminho, body=None, headers=None):
            Conexao.ultimo_corpo = body

        def getresponse(self):
            return Resposta()

        def close(self):
            pass

    import http.client as hc

    monkeypatch.setattr(hc, "HTTPSConnection", Conexao)
    CRED.gravar(CRED.CRA, usuario="u", senha="s", pasta=tmp_path,
                ambiente=CRED.HOMOLOGACAO)
    API.enviar_confirmacao("C0013110.141", "0" * 600 + "\n", CRED.HOMOLOGACAO,
                           pasta=tmp_path)
    corpo = Conexao.ultimo_corpo.decode()
    assert "<userArq>C0013110.141</userArq>" in corpo
    assert "<userDados>" in corpo
    assert re.search(r"Confirmacao", corpo)


def test_pos_remessa_respeita_auto_desligado():
    import sqlite3
    from pt_schema import init_pt_schema

    con = sqlite3.connect(":memory:")
    init_pt_schema(con)
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em)
           VALUES ('SDTBFOCRT','001','2026-09-30',1,'C001.141','x','now')""")
    rid = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
    r = ENV.enviar_pos_remessa(
        con, lotes=[{"confirmacao_id": rid}], andamentos=[],
        ambiente=CRED.HOMOLOGACAO,
        ler_config=lambda k, d: "0" if k == "cra_auto_enviar_homolog" else d)
    assert not r["enviados"] and "desligado" in r["motivo"]

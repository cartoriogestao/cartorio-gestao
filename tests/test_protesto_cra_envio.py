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


def test_o_ambiente_vazio_e_producao_e_desligado_por_padrao():
    """**14/10/2026** — «agora é tudo produção». O vazio era homologação (com
    o envio automático ligado de fábrica); agora é produção, cujo envio
    automático continua desligado até o oficial ligar a caixa."""
    assert not ENV.auto_envio_ligado("", lambda k, d: d)
    assert ENV.auto_envio_ligado(
        "", lambda k, d: "1" if k == "cra_auto_enviar_producao" else d)
    assert ENV.ambiente_da_remessa({}) == CRED.PRODUCAO
    assert ENV.ambiente_da_remessa({"origem_xml_ambiente": "x"}) == CRED.PRODUCAO


def test_a_hora_do_envio_e_a_local_e_nao_a_utc_do_sqlite():
    """14/10/2026: `cra_enviado_em` saía de `datetime('now')` do SQLite, que é
    UTC, ao lado de `gerado_em` em hora local — o arquivo aparecia enviado
    três horas «antes» de gerado. Agora é a hora local, na forma da casa."""
    import sqlite3
    from datetime import datetime, timedelta
    from pt_schema import init_pt_schema

    con = sqlite3.connect(":memory:")
    init_pt_schema(con)
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em)
           VALUES ('SDTBFOCRT','001','2026-09-30',1,'C001.141','x','now')""")
    rid = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
    ENV._gravar_envio(con, {"retorno_id": rid, "operacao": "Confirmacao",
                            "nome_arquivo": "C001.141"},
                      {"resposta": "ok"}, qual=CRED.PRODUCAO, usuario="t")
    gravado = con.execute("SELECT cra_enviado_em FROM pt_retornos WHERE id=?",
                          (rid,)).fetchone()[0]
    assert "T" in gravado
    quando = datetime.strptime(gravado, "%Y-%m-%dT%H:%M:%S")
    assert abs(datetime.now() - quando) < timedelta(minutes=2)
    import inspect
    assert "datetime('now')" not in inspect.getsource(ENV)


def test_lote_de_homologacao_nao_se_envia_a_lugar_nenhum():
    """Lote gravado como de homologação antes da virada não sobe para a
    produção em silêncio: a recusa vem com a frase, antes da rede."""
    assert ENV.ambiente_da_remessa(
        {"origem_xml_ambiente": "HOMOLOGACAO"}) == CRED.HOMOLOGACAO
    with pytest.raises(CRED.CredencialError) as e:
        ENV.enviar_pos_remessa(
            None, lotes=[], andamentos=[], ambiente=CRED.HOMOLOGACAO,
            ler_config=lambda k, d: "1")
    assert "só em produção" in str(e.value)


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
        # 14/10/2026: era HOMOLOGACAO com a caixa da homologação; o envio
        # agora é só de produção, e é a caixa dela que se respeita.
        ambiente=CRED.PRODUCAO,
        ler_config=lambda k, d: "0" if k == "cra_auto_enviar_producao" else d)
    assert not r["enviados"] and "desligado" in r["motivo"]

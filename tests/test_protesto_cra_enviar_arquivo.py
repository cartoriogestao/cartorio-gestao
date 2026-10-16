"""O botão «Enviar à CRA» de um arquivo já gerado — 14/10/2026.

Até esta data o RETORNO não subia pela API: o envio só rodava junto com a
remessa (confirmação e andamento). A homologação aceitou o retorno pela
operação `Retorno` em 13/10 (código 0000); faltava o caminho de um arquivo só.
A rede é simulada aqui (`_transmitir`); o que se prova é a regra da casa — a
rede fora da transação, nada enviado duas vezes, a falha gravada.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED
import cra21_api as API
import protesto_cra_envio as ENV
from pt_schema import init_pt_schema

EXEMPLO = Path(__file__).parent / "cra_retorno_exemplo.txt"


def banco_com_retorno(ambiente_marcado=None):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_pt_schema(con)
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em,
               cra_enviado_ambiente)
           VALUES ('SDTBFORTP','237','2026-10-14',1,'R2371410.261',?,
                   '2026-10-14T10:00:00',?)""",
        (EXEMPLO.read_text(encoding="latin-1"), ambiente_marcado))
    con.commit()
    rid = int(con.execute("SELECT MAX(id) FROM pt_retornos").fetchone()[0])

    @contextmanager
    def transacao():
        yield con
        con.commit()
    return con, rid, transacao


@pytest.fixture()
def credencial(monkeypatch):
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)


def test_o_retorno_sobe_e_fica_marcado(monkeypatch, credencial):
    con, rid, transacao = banco_com_retorno()
    chamadas = []

    def falso(preparado, qual, pasta=None):
        # A REDE NÃO RODA DENTRO DE TRANSAÇÃO: nada pendente na conexão.
        assert not con.in_transaction
        chamadas.append((preparado["operacao"], qual))
        return {"ok": True, "codigo": "0000", "resposta": "<codigo>0000</codigo>"}

    monkeypatch.setattr(ENV, "_transmitir", falso)
    r = ENV.enviar_arquivo(transacao, rid, usuario="OFICIAL")
    assert r["codigo"] == "0000" and r["operacao"] == "Retorno"
    assert chamadas == [("Retorno", CRED.PRODUCAO)]
    linha = con.execute("SELECT * FROM pt_retornos WHERE id=?", (rid,)).fetchone()
    assert linha["cra_enviado_em"] and linha["cra_enviado_ambiente"] == CRED.PRODUCAO
    assert linha["cra_enviado_por"] == "OFICIAL"
    # NADA SAI DUAS VEZES sem conferir na Central.
    with pytest.raises(ENV.CraEnvioError, match="já foi enviado"):
        ENV.enviar_arquivo(transacao, rid)


def test_a_recusa_da_cra_fica_gravada_e_volta_como_frase(monkeypatch, credencial):
    con, rid, transacao = banco_com_retorno()

    def recusa(preparado, qual, pasta=None):
        raise API.CraRecusou("A CRA recusou (código 0002): nome inválido")

    monkeypatch.setattr(ENV, "_transmitir", recusa)
    with pytest.raises(ENV.CraEnvioError, match="0002"):
        ENV.enviar_arquivo(transacao, rid)
    linha = con.execute("SELECT * FROM pt_retornos WHERE id=?", (rid,)).fetchone()
    assert linha["cra_enviado_em"] is None
    assert "0002" in linha["cra_envio_erro"]


def test_o_registro_da_virada_nao_e_arquivo_e_nao_se_envia(monkeypatch, credencial):
    con, rid, transacao = banco_com_retorno(ambiente_marcado="EOFICIO")
    monkeypatch.setattr(ENV, "_transmitir",
                        lambda *a, **k: pytest.fail("não podia ir à rede"))
    with pytest.raises(ENV.CraEnvioError, match="E-Ofício já informou"):
        ENV.enviar_arquivo(transacao, rid)


def test_sem_credencial_de_producao_diz_onde_informar(monkeypatch):
    con, rid, transacao = banco_com_retorno()
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: False)
    with pytest.raises(ENV.CraEnvioError, match="credencial de PRODUÇÃO"):
        ENV.enviar_arquivo(transacao, rid)

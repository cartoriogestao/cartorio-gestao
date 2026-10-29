"""A CRA RECUSOU, E A TELA DIZIA «ENVIADO» — 28/10/2026.

Oito retornos subiram à CRA nesse dia, e seis voltaram RECUSADOS. A resposta
da recusa é um `<relatorio>` com DOIS pares código/ocorrência: primeiro `0000`
com o apresentante (marcado em vermelho) e depois `2161 — NENHUM REGISTRO FOI
GRAVADO`. O leitor olhava só o primeiro `<codigo>`, lia `0000`, e o arquivo
ficava como enviado — com os atos dele dados por informados.

O que estes testes conferem:

- a recusa se lê em QUALQUER par do relatório, e não só no primeiro;
- o arquivo recusado ganha situação própria (`cra_recusado_em`, o código e o
  motivo da Central) e NÃO fica como enviado;
- os atos dele NÃO saem como informados: continuam presos ao arquivo, a tela
  diz que não foram informados, e o balcão os devolve à fila quando decidir;
- o arquivo aceito continua como sempre;
- e os arquivos já gravados como «enviado» se reclassificam pela resposta que
  ficou gravada neles — só com código de recusa à vista.

A rede é simulada (`cra21_api.enviar_retorno`); os dados são de ensaio.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import juntar_prova  # noqa: E402

import centrais_cred as CRED
import cra21_api as API
import protesto as PT
import protesto_cra_envio as ENV
import protesto_retorno as PR
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-10-28T14:31:30"
HOJE = "2026-10-28"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}

# A FORMA DA RESPOSTA É A MEDIDA em 28/10/2026 nos seis recusados (os nomes e
# o município aqui são de ensaio): o par do apresentante em vermelho, e o par
# da recusa depois dele.
CABECALHO = ('<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>'
             "<relatorio><nome_arquivo>{nome}</nome_arquivo>"
             '<comarca CodMun="0000000"><datahora>202610281432</datahora>'
             "<dataoperacao>20261029</dataoperacao>"
             "<total_registros>1</total_registros>")
RECUSADO = (CABECALHO + "<codigo>0000</codigo><ocorrencia>&lt;FONT COLOR="
            "&apos;RED&apos;&gt;APRESENTANTE: 001 - BANCO DE ENSAIO (1 TÍTULOS)."
            "&lt;/FONT&gt;</ocorrencia><codigo>2161</codigo><ocorrencia>"
            "NENHUM REGISTRO FOI GRAVADO.</ocorrencia></comarca></relatorio>")
ACEITO = (CABECALHO + "<codigo>0000</codigo><ocorrencia>APRESENTANTE: 001 - "
          "BANCO DE ENSAIO (1 TÍTULOS).</ocorrencia></comarca></relatorio>")
SO_VERMELHO = (CABECALHO + "<codigo>0000</codigo><ocorrencia>&lt;FONT COLOR="
               "&apos;RED&apos;&gt;APRESENTANTE: 001 - BANCO DE ENSAIO (2 "
               "TÍTULOS).&lt;</ocorrencia></comarca></relatorio>")


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo_protestado(con, numero="9911/1") -> int:
    dados = {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO DE ENSAIO",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1.200,00", "saldo": "1.310,45",
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA DE ENSAIO LTDA",
                    "documento": "00000001000055"},
        "devedores": [{"nome": "PESSOA DE ENSAIO", "CPF": "00000000191",
                       "enderecos": [{"endereco": "RUA DE ENSAIO, 10",
                                      "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    tid = PT.cadastrar_titulo(con, dados, origem="CRA",
                              origem_chave=f"lote:{numero}", agora=AGORA)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=AGORA)
    juntar_prova(con, tid)   # a prova da intimação (29/10/2026)
    PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    return tid


def com_retorno_gerado():
    """Um retorno do apresentante 001 gerado, com o protesto dentro."""
    con = banco()
    titulo_protestado(con)
    r = PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                 marca="A", usuario="OFICIAL")
    con.commit()

    @contextmanager
    def transacao():
        yield con
        con.commit()
    return con, int(r["retorno_id"]), transacao


@pytest.fixture()
def rede(monkeypatch):
    """Credencial presente e o XML do arquivo simulado; quem lê a resposta é
    o `_transmitir` de verdade."""
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)
    monkeypatch.setattr(ENV, "user_dados_do_arquivo",
                        lambda conteudo, tipo="SDTBFOCRT": "<x/>")

    def responde(texto):
        monkeypatch.setattr(API, "enviar_retorno", lambda *a, **k: texto)
    return responde


def linha(con, rid):
    return con.execute("SELECT * FROM pt_retornos WHERE id=?",
                       (rid,)).fetchone()


# ------------------------------------------------------------- a leitura


def test_o_segundo_codigo_do_relatorio_e_a_recusa():
    """O PRIMEIRO `<codigo>` É `0000` E NÃO DECIDE — o defeito de 28/10/2026."""
    with pytest.raises(API.CraRecusou) as e:
        ENV.interpretar_resposta_envio(RECUSADO.format(nome="R0012810.261"),
                                       o_que="enviar o retorno")
    assert e.value.codigo == "2161"
    assert e.value.motivo == "NENHUM REGISTRO FOI GRAVADO"
    assert "(código 2161): NENHUM REGISTRO FOI GRAVADO." in str(e.value)
    # O bruto inteiro vai à parte, para o campo de erro.
    assert "</relatorio>" in e.value.bruto


def test_o_relatorio_com_um_par_so_e_sem_cor_e_aceito():
    r = ENV.interpretar_resposta_envio(ACEITO.format(nome="R0012810.261"),
                                       o_que="enviar o retorno")
    assert r["ok"] and r["codigo"] == "0000"


def test_a_marca_vermelha_sem_codigo_de_recusa_tambem_recusa():
    """Medida só em resposta recusada; sozinha, recusa sem código."""
    recusa = ENV.recusa_no_relatorio(SO_VERMELHO.format(nome="R0012310.261"))
    assert recusa is not None and recusa["codigo"] is None
    assert "vermelho" in recusa["motivo"]
    with pytest.raises(API.CraRecusou) as e:
        ENV.interpretar_resposta_envio(SO_VERMELHO.format(nome="R0012310.261"),
                                       o_que="enviar o retorno")
    assert e.value.codigo is None and e.value.motivo


def test_a_ocorrencia_sai_sem_a_marcacao_html():
    recusa = ENV.recusa_no_relatorio(RECUSADO.format(nome="R0012810.261"))
    assert recusa["ocorrencias"][0] == "APRESENTANTE: 001 - BANCO DE ENSAIO (1 TÍTULOS)."
    assert all("FONT" not in o for o in recusa["ocorrencias"])


def test_resposta_vazia_nao_e_recusa_da_central():
    """Sem conteúdo não se sabe o que a Central gravou: é erro, sem código."""
    with pytest.raises(API.CraRecusou) as e:
        ENV.interpretar_resposta_envio("   ", o_que="enviar o retorno")
    assert ENV._recusa_da_central(e.value) is None


# --------------------------------------------------- o envio do arquivo


def test_o_retorno_recusado_fica_recusado_e_nao_enviado(rede):
    con, rid, transacao = com_retorno_gerado()
    rede(RECUSADO.format(nome="R0012810.261"))
    with pytest.raises(ENV.CraEnvioRecusado) as e:
        ENV.enviar_arquivo(transacao, rid, usuario="OFICIAL")
    assert e.value.codigo == "2161"
    assert "NENHUM REGISTRO FOI GRAVADO" in str(e.value)
    ln = linha(con, rid)
    assert ln["cra_enviado_em"] is None
    assert ln["cra_recusado_em"]
    assert ln["cra_recusa_codigo"] == "2161"
    assert ln["cra_recusa_motivo"] == "NENHUM REGISTRO FOI GRAVADO"
    assert "</relatorio>" in ln["cra_envio_erro"]   # a resposta inteira, à parte


def test_os_atos_do_recusado_nao_estao_informados_e_nao_voltam_sozinhos(rede):
    con, rid, transacao = com_retorno_gerado()
    rede(RECUSADO.format(nome="R0012810.261"))
    with pytest.raises(ENV.CraEnvioRecusado):
        ENV.enviar_arquivo(transacao, rid)
    presos = PR.atos_do_retorno(con, rid)
    assert [a["tipo"] for a in presos] == ["PROTESTO"]
    # Não voltam sozinhos à fila (ver `_registrar_recusa`)...
    assert PR.pendentes(con) == []
    # ...e a tela os conta como presos num arquivo recusado.
    [gerado] = [g for g in PR.listar(con) if g["id"] == rid]
    assert gerado["cra_recusado_em"] and gerado["atos_presos"] == 1
    assert not gerado["cra_enviado_em"]


def test_o_retorno_aceito_continua_como_hoje(rede):
    con, rid, transacao = com_retorno_gerado()
    rede(ACEITO.format(nome="R0012810.261"))
    r = ENV.enviar_arquivo(transacao, rid, usuario="OFICIAL")
    assert r["codigo"] == "0000"
    ln = linha(con, rid)
    assert ln["cra_enviado_em"] and ln["cra_recusado_em"] is None
    assert ln["cra_recusa_codigo"] is None


def test_o_reenvio_aceito_apaga_a_recusa_anterior(rede):
    con, rid, transacao = com_retorno_gerado()
    rede(RECUSADO.format(nome="R0012810.261"))
    with pytest.raises(ENV.CraEnvioRecusado):
        ENV.enviar_arquivo(transacao, rid)
    rede(ACEITO.format(nome="R0012810.261"))
    ENV.enviar_arquivo(transacao, rid)
    ln = linha(con, rid)
    assert ln["cra_enviado_em"]
    assert ln["cra_recusado_em"] is None and ln["cra_recusa_motivo"] is None


def test_a_falha_de_rede_continua_erro_e_nao_recusa(rede, monkeypatch):
    con, rid, transacao = com_retorno_gerado()

    def cai(*a, **k):
        raise API.CraError("Falha de comunicação com a CRA de ensaio.")
    monkeypatch.setattr(API, "enviar_retorno", cai)
    with pytest.raises(ENV.CraEnvioError) as e:
        ENV.enviar_arquivo(transacao, rid)
    assert not isinstance(e.value, ENV.CraEnvioRecusado)
    ln = linha(con, rid)
    assert ln["cra_recusado_em"] is None and ln["cra_enviado_em"] is None
    assert "comunicação" in ln["cra_envio_erro"]


def test_no_envio_automatico_a_recusa_tambem_se_grava(monkeypatch):
    """O caminho de `enviar_pos_remessa`: a confirmação recusada com 2161."""
    con = banco()
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em)
           VALUES ('SDTBFOCRT','001','2026-10-28',1,'C0012810.261','x',
                   '2026-10-28T10:00:00')""")
    con.commit()
    rid = int(con.execute("SELECT MAX(id) FROM pt_retornos").fetchone()[0])

    @contextmanager
    def transacao():
        yield con
        con.commit()

    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)
    monkeypatch.setattr(ENV, "user_dados_do_arquivo", lambda c, t: "<x/>")
    monkeypatch.setattr(API, "enviar_confirmacao",
                        lambda *a, **k: RECUSADO.format(nome="C0012810.261"))
    r = ENV.enviar_pos_remessa(
        transacao, lotes=[{"confirmacao_id": rid}], andamentos=[],
        ambiente=CRED.PRODUCAO, ler_config=lambda k, d: "1")
    [falha] = r["falhas"]
    assert falha["recusado"] and falha["codigo"] == "2161"
    ln = linha(con, rid)
    assert ln["cra_recusado_em"] and ln["cra_enviado_em"] is None


# ---------------------------------------------- devolver os atos à fila


def test_devolver_os_atos_do_recusado_os_poe_de_volta_na_fila(rede):
    con, rid, transacao = com_retorno_gerado()
    rede(RECUSADO.format(nome="R0012810.261"))
    with pytest.raises(ENV.CraEnvioRecusado):
        ENV.enviar_arquivo(transacao, rid)
    r = PR.devolver_atos_do_recusado(con, rid, agora=AGORA, usuario="OFICIAL")
    assert len(r["atos"]) == 1
    assert [a["tipo"] for a in PR.pendentes(con)] == ["PROTESTO"]
    assert PR.atos_do_retorno(con, rid) == []
    # O arquivo recusado fica gravado como foi, com a recusa.
    assert linha(con, rid)["cra_recusa_codigo"] == "2161"
    # Devolver de novo não tem o que devolver.
    with pytest.raises(PR.RetornoError, match="já voltaram"):
        PR.devolver_atos_do_recusado(con, rid, agora=AGORA)
    # E o arquivo recusado não se reenvia: os atos irão no próximo.
    with pytest.raises(ENV.CraEnvioError, match="Gere um retorno novo"):
        ENV.enviar_arquivo(transacao, rid)


def test_so_se_devolve_ato_de_arquivo_recusado(rede):
    con, rid, transacao = com_retorno_gerado()
    # Ainda sem resposta da Central.
    with pytest.raises(PR.RetornoNaoRecusadoError, match="ainda não teve"):
        PR.devolver_atos_do_recusado(con, rid, agora=AGORA)
    # Aceito: os atos estão informados.
    rede(ACEITO.format(nome="R0012810.261"))
    ENV.enviar_arquivo(transacao, rid)
    with pytest.raises(PR.RetornoNaoRecusadoError, match="aceitou"):
        PR.devolver_atos_do_recusado(con, rid, agora=AGORA)
    assert PR.atos_do_retorno(con, rid)


def test_a_recusa_e_um_valueerror_com_frase_para_o_balcao():
    assert issubclass(PR.RetornoNaoRecusadoError, ValueError)


# ------------------------------------- os já gravados como «enviado»


def _gravado_como_enviado(con, nome, resumo):
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em,
               cra_enviado_em, cra_enviado_ambiente, cra_envio_resumo)
           VALUES ('SDTBFORTP','001','2026-10-28',1,?,'x',
                   '2026-10-28T14:31:55','2026-10-28T14:32:29','PRODUCAO',?)""",
        (nome, resumo[:500]))
    return int(con.execute("SELECT MAX(id) FROM pt_retornos").fetchone()[0])


def test_os_ja_gravados_como_enviado_se_reclassificam_pela_resposta():
    con = banco()
    recusado = _gravado_como_enviado(con, "R0012810.261",
                                     RECUSADO.format(nome="R0012810.261"))
    aceito = _gravado_como_enviado(con, "R3412810.261",
                                   ACEITO.format(nome="R3412810.261"))
    # Vermelho e cortado antes do código: não se prova, e fica como está.
    so_vermelho = _gravado_como_enviado(con, "R0012310.261",
                                        SO_VERMELHO.format(nome="R0012310.261"))
    assert ENV.reclassificar_recusas_gravadas(con) == 1
    r = linha(con, recusado)
    assert r["cra_enviado_em"] is None
    assert r["cra_recusado_em"] == "2026-10-28T14:32:29"
    assert r["cra_recusa_codigo"] == "2161"
    assert r["cra_recusa_motivo"] == "NENHUM REGISTRO FOI GRAVADO"
    assert "dera por enviado" in r["cra_envio_erro"]
    assert linha(con, aceito)["cra_enviado_em"]
    assert linha(con, so_vermelho)["cra_enviado_em"]
    # Idempotente.
    assert ENV.reclassificar_recusas_gravadas(con) == 0


def test_a_reclassificacao_roda_ao_abrir_o_esquema():
    con = banco()
    rid = _gravado_como_enviado(con, "R0012810.261",
                                RECUSADO.format(nome="R0012810.261"))
    init_pt_schema(con)
    assert linha(con, rid)["cra_recusado_em"]

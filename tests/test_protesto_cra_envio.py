"""Envio SOAP de confirmação e retorno à CRA (mock de rede)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

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


def test_a_recusa_traz_a_ocorrencia_que_vem_depois_do_cabecalho():
    """RTAB2110.261, 21/10/2026: o motivo da CRA vinha depois dos 240
    primeiros caracteres e não chegava à tela nem ao banco."""
    cabecalho = ('<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>'
                 "<relatorio><nome_arquivo>RTAB2110.261</nome_arquivo>"
                 '<comarca CodMun="2107001"><datahora>202610211320</datahora>'
                 "<dataoperacao>20261022</dataoperacao>"
                 "<total_registros>0</total_registros>")
    with pytest.raises(API.CraRecusou) as e:
        ENV.interpretar_resposta_envio(
            cabecalho + "<codigo>2154</codigo><ocorrencia>MOTIVO\n   DE TESTE"
            "</ocorrencia></comarca></relatorio>", o_que="enviar o retorno")
    assert "(código 2154): MOTIVO DE TESTE." in str(e.value)
    # LH08 (revisão do LH07): a resposta inteira vai À PARTE, para o campo de
    # erro do arquivo — e não mais na frase, que vai à tela.
    assert "</relatorio>" in e.value.bruto
    assert "</relatorio>" not in str(e.value)
    assert "RTAB2110.261" in str(e.value)       # o trecho curto do começo


def _relatorio_comprido(motivo: str = "MOTIVO DE TESTE", titulos: int = 200) -> str:
    """Um relatório de recusa como os da CRA, com a lista dos títulos depois
    da ocorrência — passa fácil dos 4.000 caracteres. Dados de ensaio."""
    cauda = "".join(f"<titulo><protocolo>{n:06d}</protocolo>"
                    f"<situacao>RECUSADO</situacao></titulo>"
                    for n in range(titulos))
    return ('<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>'
            "<relatorio><nome_arquivo>R0012110.261</nome_arquivo>"
            '<comarca CodMun="0000000"><datahora>202610211320</datahora>'
            f"<codigo>2154</codigo><ocorrencia>{motivo}</ocorrencia>"
            f"<titulos>{cauda}</titulos></comarca></relatorio>")


def test_a_frase_da_recusa_e_curta_e_a_resposta_inteira_vai_a_parte():
    """A frase vai ao `flash` — que mora no cookie da sessão — e à auditoria:
    o motivo, o código e um trecho curto do começo. A resposta inteira fica em
    `bruto`, sem corte, para o campo de erro."""
    bruto = _relatorio_comprido()
    assert len(bruto) > 10_000
    with pytest.raises(API.CraRecusou) as e:
        ENV.interpretar_resposta_envio(bruto, o_que="enviar o retorno")
    frase = str(e.value)
    assert frase.startswith(
        "A CRA recusou ao enviar o retorno (código 2154): MOTIVO DE TESTE. "
        "Início da resposta: <relatorio><nome_arquivo>R0012110.261")
    assert "<?xml" not in frase
    assert "000199" not in frase                   # a cauda não vai à tela
    assert len(frase) <= (len("A CRA recusou ao enviar o retorno (código 2154): "
                              ". Início da resposta: ")
                          + ENV.TRECHO_NA_TELA + ENV.TRECHO_DA_RESPOSTA)
    assert e.value.bruto == bruto


def test_a_ocorrencia_comprida_sai_cortada_na_tela():
    motivo = "DIVERGENCIA NO TITULO " * 60
    with pytest.raises(API.CraRecusou) as e:
        ENV.interpretar_resposta_envio(_relatorio_comprido(motivo, titulos=1),
                                       o_que="enviar o retorno")
    achado = re.search(r"\(código 2154\): (.*?)\. Início da resposta", str(e.value))
    assert achado
    assert len(achado.group(1)) <= ENV.TRECHO_NA_TELA
    assert achado.group(1).startswith("DIVERGENCIA NO TITULO DIVERGENCIA")
    assert achado.group(1).endswith("…")
    assert " ".join(motivo.split()) in " ".join(e.value.bruto.split())


def test_no_envio_automatico_a_falha_diz_a_frase_e_o_arquivo_guarda_a_resposta(
        monkeypatch):
    """O caminho de `enviar_pos_remessa` (a confirmação depois da remessa): a
    falha devolvida à rota — que vira `flash` e auditoria — é a frase curta;
    `pt_retornos.cra_envio_erro` guarda a frase e a resposta até 4.000."""
    from contextlib import contextmanager
    from nucleo_schema import init_nucleo_schema
    from pt_schema import init_pt_schema

    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_pt_schema(con)
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em)
           VALUES ('SDTBFOCRT','001','2026-10-21',1,'C0012110.261','x',
                   '2026-10-21T10:00:00')""")
    con.commit()
    rid = int(con.execute("SELECT MAX(id) FROM pt_retornos").fetchone()[0])

    @contextmanager
    def transacao():
        yield con
        con.commit()

    bruto = _relatorio_comprido()
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)
    monkeypatch.setattr(ENV, "user_dados_do_arquivo", lambda conteudo, tipo: "<x/>")
    monkeypatch.setattr(API, "enviar_confirmacao", lambda *a, **k: bruto)
    r = ENV.enviar_pos_remessa(
        transacao, lotes=[{"confirmacao_id": rid}], andamentos=[],
        ambiente=CRED.PRODUCAO, ler_config=lambda k, d: "1")
    [falha] = r["falhas"]
    assert "MOTIVO DE TESTE" in falha["erro"]
    assert "000199" not in falha["erro"] and len(falha["erro"]) < 600
    guardado = con.execute("SELECT cra_envio_erro FROM pt_retornos WHERE id=?",
                           (rid,)).fetchone()[0]
    assert len(guardado) == ENV.CORTE_DO_ERRO
    assert guardado.startswith(falha["erro"] + " Resposta: <?xml")
    assert guardado == (falha["erro"] + " Resposta: " + bruto)[:ENV.CORTE_DO_ERRO]


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
    from nucleo_schema import init_nucleo_schema
    from pt_schema import init_pt_schema

    con = conexao_de_teste()
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(con)
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
    from nucleo_schema import init_nucleo_schema
    from pt_schema import init_pt_schema

    con = conexao_de_teste()
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(con)
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

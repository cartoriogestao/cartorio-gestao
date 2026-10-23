"""
O EDITAL ELETRONICO do CENPROT — o terceiro arquivo, medido em 01/09/2026.

Dois exemplares que o oficial salvou, dos MESMOS 6 titulos:
`Edital_Eletronico_2198765_14082026_001.xml` (o que se manda) e `E140826.XML`
(o rico, com o bloco `<custas>` que fechou a decomposicao dos emolumentos).

O QUE ESTES TESTES GUARDAM
      - **o `documento` VAI COM MASCARA**, e so neste arquivo. Quem puser
        `so_digitos` ali quebra o arquivo sem ver;
      - **o valor vai de DUAS formas no mesmo registro** — `243,4400` com
        virgula e `243.4400` com ponto, os dois com quatro casas;
      - a mascara sai do `documento_tipo`, e NAO do tamanho do numero — «o
        tipo diz onde esta o documento, e nao o tamanho do que esta escrito»;
      - **`numerotitulo` e o NUMERO DO TITULO**, decidido pelo unico dos seis
        titulos em que ele difere do nosso numero: o edital publica `00123`;
      - `finalidade` e o motivo da nao-entrega, e **sem motivo fica vazio** —
        um motivo inventado afirma sobre a pessoa o que ninguem apurou;
      - **a data do nome vai DDMMAAAA**, ao contrario do arquivo de
        emolumentos, que a escreve AAAAMMDD. Dois arquivos da mesma Central
        com duas convencoes;
      - a fonte sao os editais JA PUBLICADOS no dia: o ato vem antes do
        arquivo.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto_cenprot as CP
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-09-01T10:00:00"
DIA = "2026-08-14"

# O arquivo real, achado pela forma do nome (o código IBGE da casa está nele).
_REAIS = sorted((Path.home() / "Downloads").glob("Edital_Eletronico_*_14082026_001.xml"))
ARQUIVO_REAL = _REAIS[0] if _REAIS else Path.home() / "Downloads" / "_inexistente_edital.xml"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo_com_edital(con, *, nome="FULANO EXEMPLO DOS REIS",
                      documento="00000002054", tipo="CPF",
                      numero="31000005739", nosso="31000005739",
                      valor=24344, motivo="Falecido", numero_edital=1,
                      bairro="VAQUEJADA", cep="65936000",
                      cidade="CIDADE EXEMPLO") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, protocolo,
               data_emissao, data_vencimento, cedente_nome, cedente_documento,
               origem, criado_em)
           VALUES ('DMI',?,?,?,?,'INTIMADO','2608120002','2026-06-02',
                   '2026-06-10','EQUATORIAL MARANHAO','','CRA',?)""",
        (numero, nosso, valor, valor, AGORA))
    tid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero, bairro, cep, cidade, uf)
           VALUES (?,?,?,?,?,?,?,'MA')""",
        (tid, nome, tipo, documento, bairro, cep, cidade))
    if motivo is not None:
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, criado_em)
               VALUES (?,'INTIMACAO',?,?,'MANUAL',?)""",
            (tid, DIA, json.dumps({"modo": "EDITAL", "motivo": motivo}), AGORA))
    aviso = con.execute(
        """INSERT INTO pt_avisos(titulo_id, numero, ano, devedor_nome,
               situacao, emitido_em, entregue, criado_em)
           VALUES (?,?,2026,?,'EDITAL',?,0,?)""",
        (tid, numero_edital, nome, DIA, AGORA))
    con.execute(
        """INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id,
               publicado_em, teor, criado_em)
           VALUES (?,2026,?,?,?,'teor',?)""",
        (numero_edital, int(aviso.lastrowid), tid, DIA, AGORA))
    return tid


def gerar(con, **kw):
    return CP.gerar_edital_eletronico(con, dia=DIA, comarca="2198765", **kw)


def campos(conteudo: str) -> dict:
    raiz = ET.fromstring(conteudo)
    return {c.tag: (c.text or "") for c in next(raiz.iter("edital"))}


# ------------------------------------------------------------------ o nome


def test_o_nome_do_arquivo_leva_a_data_DDMMAAAA():
    """AO CONTRARIO DO ARQUIVO DE EMOLUMENTOS, que a escreve AAAAMMDD.

    Trocar uma convencao pela outra faz o nome parecer certo e a data ficar
    errada — e e a Central que o le pelo nome.
    """
    assert CP.nome_do_edital(comarca="2198765", dia="2026-08-14") == \
        "Edital_Eletronico_2198765_14082026_001.xml"
    assert CP.nome_do_arquivo(uf="MA", comarca="2198765", cartorio="01",
                              data="2026-08-31").endswith("20260831-01.txt")


def test_o_sequencial_vai_com_tres_digitos():
    assert CP.nome_do_edital(comarca="2198765", dia="2026-08-14",
                             sequencial=12).endswith("_012.xml")


# ------------------------------------------------------------------ a mascara


def test_o_documento_vai_COM_mascara():
    """E SO NESTE ARQUIVO — em todo o resto do modulo o documento vai cru."""
    assert CP._mascara_do_documento("00000002054", "CPF") == "000.000.020-54"
    assert CP._mascara_do_documento("00000016000102", "CNPJ") == \
        "00.000.016/0001-02"


def test_a_mascara_sai_do_TIPO_e_nao_do_tamanho():
    """«O tipo diz onde esta o documento, e nao o tamanho do que esta
    escrito» — a regra que a carga do Protesto ja seguia."""
    assert CP._mascara_do_documento("00000002054", "F") == "000.000.020-54"
    # Onze digitos marcados como CNPJ nao viram CPF por parecerem um.
    assert CP._mascara_do_documento("00000002054", "CNPJ") == "00000002054"


def test_documento_com_tamanho_errado_sai_COMO_ESTA():
    """Melhor um numero cru que um numero remontado errado."""
    assert CP._mascara_do_documento("123", "CPF") == "123"
    assert CP._mascara_do_documento("", "CPF") == ""


# ------------------------------------------------------------------ o valor


def test_o_valor_vai_de_DUAS_formas_no_mesmo_registro():
    """`valortitulo` com VIRGULA e `valorfinal` com PONTO — nos 6 do arquivo
    real. Nao e engano do exemplar."""
    con = banco()
    titulo_com_edital(con)
    c = campos(gerar(con)["conteudo"])
    assert c["valortitulo"] == "243,4400"
    assert c["valorfinal"] == "243.4400"


def test_o_valor_leva_QUATRO_casas():
    con = banco()
    titulo_com_edital(con, valor=200000)
    c = campos(gerar(con)["conteudo"])
    assert c["valortitulo"] == "2000,0000" and c["valorfinal"] == "2000.0000"


# ------------------------------------------------------------------ os campos


def test_os_dezoito_campos_saem_na_ordem_medida():
    con = banco()
    titulo_com_edital(con)
    raiz = ET.fromstring(gerar(con)["conteudo"])
    assert [c.tag for c in next(raiz.iter("edital"))] == \
        list(CP.CAMPOS_DO_EDITAL)


def test_numerotitulo_e_o_NUMERO_e_nao_o_nosso_numero():
    """DECIDIDO POR UM TITULO — o unico dos seis em que os dois diferem.

    O protocolo 2608110001 tem numero `00123` e nosso numero
    `009620400000035`, e o edital real publica **`00123`**. Nos outros cinco
    os dois sao iguais e nao decidiriam nada: **um caso que separa vale mais
    que cinco que concordam.**
    """
    con = banco()
    titulo_com_edital(con, numero="00123", nosso="009620400000035")
    c = campos(gerar(con)["conteudo"])
    assert c["numerotitulo"] == "00123"


def test_a_finalidade_e_o_motivo_da_nao_entrega():
    """«Falecido» e «Ausente» sao literais do catalogo do E-Oficio."""
    con = banco()
    titulo_com_edital(con, motivo="Ausente")
    assert campos(gerar(con)["conteudo"])["finalidade"] == "Ausente"


def test_sem_motivo_a_finalidade_fica_VAZIA_e_nao_inventada():
    """Motivo errado no edital afirma sobre a pessoa o que ninguem apurou."""
    con = banco()
    titulo_com_edital(con, motivo=None)
    raiz = ET.fromstring(gerar(con)["conteudo"])
    fin = next(raiz.iter("edital")).find("finalidade")
    assert (fin.text or "") == ""


def test_campo_vazio_sai_fechado_em_si():
    """`<numres />` — e como o arquivo real escreve os seis `numres`."""
    con = banco()
    titulo_com_edital(con)
    assert "<numres />" in gerar(con)["conteudo"]


def test_a_dataApresentacao_e_a_da_publicacao_do_edital():
    con = banco()
    titulo_com_edital(con)
    assert campos(gerar(con)["conteudo"])["dataApresentacao"] == DIA


# ------------------------------------------------------------------ a fonte


def test_a_fonte_sao_os_editais_JA_PUBLICADOS_no_dia():
    """O ATO VEM ANTES DO ARQUIVO: publicar e do modulo do aviso, que numera,
    congela o teor e o amarra. Aqui so se escreve o que ja foi lavrado."""
    con = banco()
    titulo_com_edital(con, numero_edital=1)
    con.execute("UPDATE pt_editais SET publicado_em='2026-08-13'")
    assert gerar(con)["editais"] == 0


def test_dois_editais_no_dia_viram_dois_registros():
    con = banco()
    titulo_com_edital(con, numero_edital=1)
    titulo_com_edital(con, numero_edital=2, nome="OUTRA PESSOA",
                      documento="04785512388", numero="99999")
    r = gerar(con)
    assert r["editais"] == 2
    assert len(list(ET.fromstring(r["conteudo"]).iter("edital"))) == 2


def test_titulo_sem_devedor_sai_da_lista_com_o_motivo():
    """O edital identifica uma PESSOA; registro sem nome avisaria ninguem."""
    con = banco()
    tid = titulo_com_edital(con)
    con.execute("DELETE FROM pt_devedores WHERE titulo_id=?", (tid,))
    r = gerar(con)
    assert r["editais"] == 0
    assert "nao tem devedor com nome" in r["fora"][0]["motivo"]


def test_dia_sem_edital_gera_arquivo_vazio_e_nao_estoura():
    con = banco()
    r = gerar(con)
    assert r["editais"] == 0
    assert "<editais>" in r["conteudo"]


def test_o_arquivo_sai_em_CRLF():
    con = banco()
    titulo_com_edital(con)
    assert "\r\n" in gerar(con)["conteudo"]


def test_o_XML_gerado_e_lido_de_volta_sem_erro():
    """IDA E VOLTA: o que sai daqui tem de ser XML valido."""
    con = banco()
    titulo_com_edital(con, nome="JOSE & MARIA <LTDA>")
    raiz = ET.fromstring(gerar(con)["conteudo"])
    assert next(raiz.iter("edital")).findtext("nome") == "JOSE & MARIA <LTDA>"


# ------------------------------------------------------------------ o ensaio


@pytest.mark.skipif(not ARQUIVO_REAL.exists(),
                    reason="o edital do CENPROT so existe na maquina do oficial")
def test_ensaio_a_forma_do_arquivo_real():
    """Os 18 campos, a ordem, e as duas formas do valor — no arquivo que a
    Central aceitou."""
    raiz = ET.parse(ARQUIVO_REAL).getroot()
    eds = list(raiz.iter("edital"))
    assert raiz.tag == "editais"
    assert len(eds) == 6
    for e in eds:
        assert [c.tag for c in e] == list(CP.CAMPOS_DO_EDITAL)
        assert "," in (e.findtext("valortitulo") or "")
        assert "." in (e.findtext("valorfinal") or "")
        assert "." in (e.findtext("documento") or ""), "o documento vai com mascara"


@pytest.mark.skipif(not ARQUIVO_REAL.exists(),
                    reason="o edital do CENPROT so existe na maquina do oficial")
def test_ensaio_a_casa_reproduz_um_registro_do_arquivo_real():
    """Montado o titulo como o arquivo real o descreve, o registro que sai
    daqui tem de ser o mesmo — campo a campo."""
    real = next(ET.parse(ARQUIVO_REAL).getroot().iter("edital"))
    con = banco()
    # A PESSOA VEM DO PRÓPRIO ARQUIVO REAL, e não de um literal aqui: o que
    # este ensaio prova é o formato, e o devedor de verdade não vai ao
    # repositório público (sanitização B3, 10/10/2026).
    so_digitos = lambda s: "".join(c for c in (s or "") if c.isdigit())
    titulo_com_edital(con, nome=real.findtext("nome") or "",
                      documento=so_digitos(real.findtext("documento")),
                      bairro=real.findtext("bairro") or "",
                      cep=so_digitos(real.findtext("cep")),
                      cidade=real.findtext("cidade") or "")
    meu = campos(gerar(con)["conteudo"])
    for campo in ("nome", "documento", "cep", "bairro", "cidade", "estado",
                  "numerotitulo", "valortitulo", "emissaotitulo",
                  "vencimentotitulo", "Especie", "Protocolo", "valorfinal",
                  "finalidade"):
        assert meu[campo] == (real.findtext(campo) or ""), campo

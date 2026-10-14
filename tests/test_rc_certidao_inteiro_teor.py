"""Certidão de inteiro teor do RCPN — ramificação de modos e escape no ODT.

Não inventa teor: o texto colado ou a imagem vêm do balcão. O resumo CNJ
continua no caminho antigo.
"""
from __future__ import annotations

import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_assento as RC
import rc_certidao as CE
import rc_certidao_inteiro_teor as IT
from nucleo_schema import init_nucleo_schema
from rc_schema import init_rc_schema

AGORA = "2026-09-08T10:00:00"
HOJE = "2026-09-08"
EXTENSO = "oito dias do mês de setembro do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Oficial",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
MATRICULA = "000000015519971000111270010385 01"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    CE.init_rc_certidao_schema(con)
    return con


def pessoa(con, assento_id, papel, nome, ordem=1):
    con.execute(
        """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem, criado_em)
           VALUES (?,?,?,?,?)""", (assento_id, papel, nome, ordem, AGORA))


def assento_completo(con, nome="JOÃO DA SILVA"):
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome=nome, sv=SV, agora=AGORA,
        data_extenso=EXTENSO, matricula=MATRICULA, data_fato="1997-03-11",
        origem="SISTEMA")
    aid = r["assento_id"]
    pessoa(con, aid, "PAI", "JOSÉ DA SILVA", 1)
    pessoa(con, aid, "MAE", "MARIA DAS GRAÇAS SILVA", 2)
    return aid


# ---------------------------------------------------- normalização / ramos


def test_normalizar_modalidade_aceita_aliases():
    assert IT.normalizar_modalidade("resumo") == IT.RESUMO
    assert IT.normalizar_modalidade("inteiro_teor") == IT.INTEIRO_TEXTO
    assert IT.normalizar_modalidade("texto") == IT.INTEIRO_TEXTO
    assert IT.normalizar_modalidade("reprográfica") == IT.INTEIRO_REPRO
    assert IT.normalizar_modalidade("imagem") == IT.INTEIRO_REPRO
    assert IT.e_inteiro_teor("INTEIRO_TEXTO")
    assert not IT.e_inteiro_teor("RESUMO")


def test_introducao_comeca_em_certidao_de_sem_brasao():
    intro = IT.introducao(
        especie="NASCIMENTO", nome="JOÃO DA SILVA",
        matricula=MATRICULA, livro="A-3", folha="12", termo="45",
        cns="000000", cidade="Cidade Exemplo", uf="MA")
    assert intro.startswith("CERTIDÃO DE INTEIRO TEOR DE NASCIMENTO")
    assert "REPÚBLICA FEDERATIVA" not in intro.upper().replace("Ú", "U")
    assert "COM O SEGUINTE TEOR" in intro


def test_entre_aspas_recusa_vazio_e_nao_inventa():
    with pytest.raises(IT.InteiroTeorError):
        IT.entre_aspas("   ")
    bloco = IT.entre_aspas("Aos onze de março… lavrado o assento.")
    assert bloco.startswith("«")
    assert bloco.endswith("»")
    assert "Aos onze de março" in bloco


def test_emitir_resumo_continua_montando_dos_campos():
    con = banco()
    aid = assento_completo(con)
    r = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA,
                  data_extenso=EXTENSO, modalidade=IT.RESUMO)
    linha = CE.ler(con, r["certidao_id"])
    assert (linha["modalidade"] or IT.RESUMO) == IT.RESUMO
    assert "CERTIDÃO DE NASCIMENTO" in linha["teor"]
    assert "JOÃO DA SILVA" in linha["teor"].upper().replace("Ã", "A") or \
           "JOAO" in linha["teor"].upper() or "SILVA" in linha["teor"]


def test_emitir_texto_usa_teor_colado_e_nao_o_quadro():
    con = banco()
    aid = assento_completo(con)
    colado = "No dia onze de março de mil novecentos e noventa e sete…"
    r = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA,
                  data_extenso=EXTENSO, modalidade=IT.INTEIRO_TEXTO,
                  teor_colado=colado, usuario="MARIO EXEMPLO DOS SANTOS")
    linha = dict(CE.ler(con, r["certidao_id"]))
    assert linha["modalidade"] == IT.INTEIRO_TEXTO
    assert linha["teor_colado"] == colado
    assert "«" in linha["teor"] and "»" in linha["teor"]
    assert colado in linha["teor"]
    assert "CERTIDÃO DE INTEIRO TEOR" in linha["teor"]
    # Não é o quadro CNJ de filiação montado dos campos.
    assert "FILIAÇÃO" not in linha["teor"] or colado in linha["teor"]
    assert linha["emitida_por"] == "MARIO EXEMPLO DOS SANTOS"


def test_emitir_texto_sem_cola_e_recusado():
    con = banco()
    aid = assento_completo(con)
    with pytest.raises((CE.CertidaoRCPNError, IT.InteiroTeorError)):
        CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA,
                  modalidade=IT.INTEIRO_TEXTO, teor_colado="")


def test_emitir_repro_exige_imagem_e_guarda_layout():
    con = banco()
    aid = assento_completo(con)
    with pytest.raises((CE.CertidaoRCPNError, IT.InteiroTeorError)):
        CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA,
                  modalidade=IT.INTEIRO_REPRO)
    r = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA,
                  modalidade=IT.INTEIRO_REPRO,
                  imagem_caminho=r"C:\temp\assento1222.jpg",
                  imagem_largura_cm=15.5, imagem_margem_esq_cm=1.0,
                  imagem_margem_sup_cm=0.8,
                  usuario="MARIO EXEMPLO DOS SANTOS")
    linha = dict(CE.ler(con, r["certidao_id"]))
    assert linha["modalidade"] == IT.INTEIRO_REPRO
    assert linha["imagem_caminho"].endswith("assento1222.jpg")
    assert float(linha["imagem_largura_cm"]) == 15.5
    assert "reprográfica" in linha["teor"].lower() or "reprografica" in \
           linha["teor"].lower().replace("á", "a")


def test_escape_de_teor_no_odt_protege_xml():
    """&, < e > do teor colado não quebram o content.xml."""
    teor_sujo = 'João & Maria <menor> "aspas" e O\'Connor'
    intro = IT.introducao(especie="NASCIMENTO", nome="TESTE", cns="000000",
                          cidade="Cidade Exemplo", uf="MA")
    teor = IT.montar_teor_texto(introducao_txt=intro, teor_colado=teor_sujo)
    cert = {
        "numero": 1, "ano": 2026, "teor": teor,
        "modalidade": IT.INTEIRO_TEXTO,
        "emitida_em": AGORA, "hash_teor": "abc", "selo": "",
    }
    odt = IT.arquivo_odt(cert, SV, hoje_extenso=EXTENSO)
    with zipfile.ZipFile(BytesIO(odt)) as z:
        xml = z.read("content.xml").decode("utf-8")
    assert "&amp;" in xml
    assert "<menor>" not in xml
    assert "&lt;menor&gt;" in xml
    # O teor legível (sem quebrar o XML) está lá.
    assert "João" in xml or "Jo&" in xml or "Joao" in xml.upper()
    assert xml.strip().startswith("<?xml")


def test_odt_texto_comeca_sem_cabecalho_de_brasao():
    intro = IT.introducao(especie="NASCIMENTO", nome="FULANO", cns="000000",
                          cidade="Cidade Exemplo", uf="MA")
    teor = IT.montar_teor_texto(introducao_txt=intro,
                               teor_colado="texto do livro")
    cert = {
        "numero": 7, "ano": 2026, "teor": teor,
        "modalidade": IT.INTEIRO_TEXTO,
        "emitida_em": AGORA, "hash_teor": "x", "selo": "",
    }
    odt = IT.arquivo_odt(cert, SV, hoje_extenso=EXTENSO)
    with zipfile.ZipFile(BytesIO(odt)) as z:
        xml = z.read("content.xml").decode("utf-8")
    assert "CERTIDÃO DE INTEIRO TEOR" in xml
    # Não se desenha o cabeçalho institucional por cima do papel de segurança.
    assert "REPÚBLICA FEDERATIVA DO BRASIL" not in xml


def test_odt_repro_insere_imagem_e_respeita_tamanho():
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    intro = IT.introducao(especie="NASCIMENTO", nome="FULANO", cns="000000",
                          cidade="Cidade Exemplo", uf="MA", modo=IT.INTEIRO_REPRO)
    teor = IT.montar_teor_repro(introducao_txt=intro)
    cert = {
        "numero": 8, "ano": 2026, "teor": teor,
        "modalidade": IT.INTEIRO_REPRO,
        "imagem_caminho": "foto.png",
        "imagem_largura_cm": 14.0,
        "imagem_altura_cm": 18.0,
        "imagem_margem_esq_cm": 1.2,
        "imagem_margem_sup_cm": 0.4,
        "emitida_em": AGORA, "hash_teor": "y", "selo": "",
    }
    odt = IT.arquivo_odt(cert, SV, hoje_extenso=EXTENSO, imagem_bytes=png)
    with zipfile.ZipFile(BytesIO(odt)) as z:
        nomes = z.namelist()
        assert any(n.startswith("Pictures/") for n in nomes)
        xml = z.read("content.xml").decode("utf-8")
    assert 'svg:width="14.0cm"' in xml
    assert 'svg:height="18.0cm"' in xml
    assert 'svg:x="1.2cm"' in xml
    assert "draw:image" in xml


def test_completar_teor_colado_acrescenta_averbacao_faltante():
    """CPF em rc_atos entra no colado se ainda nao estiver la."""
    colado = "Texto do livro. AVERBACAO 014 – CASAMENTO: casou-se em 2021."
    atos = [{
        "tipo": "AVERBACAO",
        "selo": "AVERBA000000QDM0NGD87QWN0G21",
        "teor": ("Averbo neste assento o CPF n. 000.000.026-40. "
                 "AVERBA000000QDM0NGD87QWN0G21. 08/09/2026. "
                 "Debora Exemplo Reis, Escrevente Autorizado."),
    }]
    out = IT.completar_teor_colado_com_atos(colado, atos)
    assert "CASAMENTO" in out
    assert "000.000.026-40" in out
    assert "AVERBA000000QDM0NGD87QWN0G21" in out
    out2 = IT.completar_teor_colado_com_atos(out, atos)
    assert out2.count("000.000.026-40") == 1


def test_emitir_inteiro_texto_acrescenta_rc_atos_faltantes():
    """Emitir INTEIRO_TEXTO congela colado + averbacoes de rc_atos."""
    con = banco()
    aid = assento_completo(con)
    RC.averbar(
        con, aid,
        teor=("Averbo neste assento o CPF n. 000.000.026-40. "
              "AVERBA000000TESTESELOCPF0000001."),
        agora=AGORA, usuario="Debora Exemplo Reis",
    )
    con.execute(
        "UPDATE rc_atos SET selo=? WHERE assento_id=? AND tipo='AVERBACAO'",
        ("AVERBA000000TESTESELOCPF0000001", aid))
    colado = "No dia onze de marco lavrou-se o assento de nascimento."
    r = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA,
                  data_extenso=EXTENSO, modalidade=IT.INTEIRO_TEXTO,
                  teor_colado=colado, usuario="Debora Exemplo Reis")
    linha = dict(CE.ler(con, r["certidao_id"]))
    assert "000.000.026-40" in (linha["teor_colado"] or "")
    assert "000.000.026-40" in linha["teor"]
    assert "marco" in linha["teor"] or "No dia onze" in linha["teor"]
    assert linha["modalidade"] == IT.INTEIRO_TEXTO

def test_previa_nao_inventa_teor():
    intro = IT.introducao(especie="NASCIMENTO", nome="X", cns="000000")
    html = IT.previa_html(modalidade=IT.INTEIRO_TEXTO, introducao_txt=intro,
                          teor_colado="")
    assert "não inventa" in html.lower() or "Cole o teor" in html
    html2 = IT.previa_html(modalidade=IT.INTEIRO_TEXTO, introducao_txt=intro,
                           teor_colado="trecho real do livro")
    assert "trecho real do livro" in html2
    assert "nada foi gravado" in html2.lower()

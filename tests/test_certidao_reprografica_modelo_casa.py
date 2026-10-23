"""Certidão reprográfica no MODELO DA CASA — pedido da substituta, 20/10/2026.

A substituta entregou o modelo da casa e pediu que todas as certidões
reprográficas saiam nele, inclusive as já emitidas (o leiaute é do papel).
HOTFIX-2026-10-20-02, na produção desde a 3.6.293.4 (21/10/2026).

NA BRANCH DO POSTGRESQL (LH02)
    Os testes são os do servidor, com os números de matrícula fictícios e
    coerentes (a máscara do servidor trocou a saída, 3.367 → 9.003, e deixou a
    entrada). Duas diferenças, que são as do código e não enfraquecem nada:
    o cabeçalho e a cidade da data vêm do CADASTRO DA SERVENTIA (`serventia`),
    e não de nomes escritos no módulo — o teste passa uma serventia fictícia e
    confere que, sem ela, nenhum nome sai; e o texto do modelo vem da base dos
    padrões (`RI_REPROGRAFICA_CAPA`, `RI_REPROGRAFICA_FECHO_DO_PAPEL`).
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CORPO = (
    '<p align="center"><b>CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA</b></p>'
    '<p>Certidão de inteiro teor da matrícula <strong>9003</strong> por '
    'reprodução da digitalização oficial (2 página(s); sha256=abc).</p>'
    '<p>O documento impresso reproduz as páginas digitalizadas e traz o selo '
    'de certidão ao final.</p><p>Era o que nela continha.</p>'
    '<p>CERTIFICO ainda que, nesta data, <b>não há</b> título prenotado nem '
    'protocolo em aberto referente a esta matrícula.</p>'
    '<p><b>VALIDADE: </b>30 (trinta) dias contados da data de expedição. '
    'Certidão emitida em 20 de outubro de 2026. Dou fé.</p>')
ETIQUETA = (
    "Poder Judiciário – TJMA. Selo: CERINT000000TESTEAAAA000001, 20/10/2026 "
    "11:33:22, Ato: 16.24.4, Total R$ 101,88 Emol R$ 90,96\n"
    "Poder Judiciário – TJMA. Selo: CERELE000000TESTEBBBB000002, 20/10/2026 "
    "11:33:22, Ato: 16.24.4.1, Total R$ 40,56 Emol R$ 36,24")
# A serventia do ensaio — fictícia, a mesma forma do cadastro da casa.
SERVENTIA = {"unit_name": "Ofício Único de Cidade Exemplo/MA",
             "serventia_titular": "Mario Exemplo dos Santos",
             "ri_substituta": "Beatriz Exemplo de Souza",
             "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def _pdf_de_duas_paginas(tmp_path) -> Path:
    from PIL import Image
    a = Image.new("RGB", (1240, 1754), "white")
    b = Image.new("RGB", (1240, 1754), "white")
    arq = tmp_path / "ficha.tif"
    a.save(arq, save_all=True, append_images=[b])
    return arq


def _xml(odt: bytes) -> tuple[str, str]:
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        return (z.read("content.xml").decode("utf-8"),
                z.read("styles.xml").decode("utf-8"))


def test_modelo_completo_com_dados(tmp_path):
    import ri_digitalizacao as RDIGI
    odt = RDIGI.odt_da_digitalizacao(
        _pdf_de_duas_paginas(tmp_path), selo_texto=ETIQUETA, nome="t",
        corpo_html=CORPO,
        identificacao=RDIGI.identificacao_da_matricula(
            "9003", "2S", None, "000000.2.0009003-00"),
        data_emissao="2026-10-20",
        signatario=("Fulana Exemplo de Souza", "Substituta"),
        serventia=SERVENTIA)
    xml, _ = _xml(odt)
    for trecho in ("REPÚBLICA FEDERATIVA DO BRASIL", "ESTADO DO MARANHÃO",
                   "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO/MA",
                   "Mario Exemplo dos Santos — Tabelião e Registrador Oficial",
                   "Beatriz Exemplo de Souza — Tabeliã e Registradora Substituta",
                   "CERTIDÃO REPROGRÁFICA",
                   "CERTIFICO, a requerimento da parte interessada",
                   "Matrícula nº 9.003 do Livro nº 2-S – Registro Geral, CNM "
                   "000000.2.0009003-00, em 2 (duas) páginas.",
                   "ressalvadas as características de legibilidade",
                   "Era o que constava no documento/assento reproduzido. Nada "
                   "mais. Certifico e dou fé.",
                   "CERTIFICO ainda que",
                   "Cidade Exemplo/MA, 20 de outubro de 2026.",
                   "Fulana Exemplo de Souza — Tabeliã e Registradora "
                   "Substituta",
                   "Selos digitais: CERINT000000TESTEAAAA000001 e "
                   "CERELE000000TESTEBBBB000002"):
        assert trecho in xml, trecho
    # A GRAFIA DO NOME É A DO CADASTRO (no servidor, a do cabeçalho foi
    # corrigida no código em 20/10): cada nome sai uma vez, como foi escrito.
    for nome in ("Mario Exemplo dos Santos", "Beatriz Exemplo de Souza"):
        assert xml.count(nome) == 1, nome
    assert "Era o que nela continha" not in xml
    assert "________" not in xml               # ordem de 22/09: sem traço
    assert "Certidão emitida em" not in xml        # a data vai na linha do lugar
    assert "sha256" not in xml.lower()
    assert "[" not in re.sub(r"<[^>]+>", "", xml)  # nenhum colchete do modelo
    assert xml.count('draw:name="digi') == 2
    assert "brasao_repro" not in xml           # o brasão vai no cabeçalho da página


def test_sem_dados_de_quem_chama_le_o_resumo(tmp_path):
    import ri_digitalizacao as RDIGI
    assinatura = ('<text:p text:style-name="P-centro">Fulana de Tal</text:p>'
                  '<text:p text:style-name="P-centro">Escrevente Autorizada'
                  '</text:p>')
    odt = RDIGI.odt_da_digitalizacao(
        _pdf_de_duas_paginas(tmp_path), selo_texto="CERELE000000TESTEBBBB000002",
        nome="t", corpo_html=CORPO, assinatura_odf=assinatura,
        serventia=SERVENTIA)
    xml, _ = _xml(odt)
    assert "Matrícula nº 9.003, em 2 (duas) páginas." in xml
    assert "Cidade Exemplo/MA, 20 de outubro de 2026." in xml
    assert "Fulana de Tal — Escrevente Autorizada" in xml
    assert "Selo digital: CERELE000000TESTEBBBB000002" in xml


def test_ultima_pagina_deixa_lugar_para_o_fecho(tmp_path):
    import ri_digitalizacao as RDIGI
    odt = RDIGI.odt_da_digitalizacao(
        _pdf_de_duas_paginas(tmp_path), selo_texto="X", nome="t",
        corpo_html=CORPO)
    xml, styles = _xml(odt)
    alturas = [float(h) for h in re.findall(
        r'draw:name="digi\d+\.png"[^>]*svg:height="([0-9.]+)cm"', xml)]
    assert len(alturas) == 2
    # A4 com as margens do modelo (topo 0,51 + brasão 2,06; pé 2,0)
    area = 29.7 - 0.51 - 2.06 - 0.15 - 2.0 - 0.6
    assert all(h <= area + 0.01 for h in alturas)
    assert alturas[0] <= area - 9.0 + 0.01       # folha 1 divide com o cabeçalho
    assert alturas[1] <= area - 12.6 + 0.01      # a última, com o fecho
    assert 'fo:keep-with-next="always"' in xml   # o fecho não se parte
    assert 'fo:margin-top="0.51cm"' in styles   # distância do cabeçalho no modelo
    assert 'fo:margin-bottom="2cm"' in styles
    assert "brasao_repro" in styles             # brasão em todas as páginas
    assert 'font-size="12pt"' in xml or 'font-size="12pt"' in styles


def test_identificacao_e_qualificacao():
    import ri_digitalizacao as RDIGI
    assert RDIGI.identificacao_da_matricula("9004", "2F", "192", None) == (
        "Matrícula nº 9.004 do Livro nº 2-F – Registro Geral, fl. 192")
    assert RDIGI.qualificacao_do_signatario("Substituta") == (
        "Tabeliã e Registradora Substituta")
    assert RDIGI.qualificacao_do_signatario("Escrevente Autorizada") == (
        "Escrevente Autorizada")
    assert RDIGI.data_por_extenso_repro("2026-10-05") == "05 de outubro de 2026"


# ------------------------------------------ o que é da branch (LH02)


def test_sem_o_cadastro_o_cabecalho_nao_inventa_quem_responde_pela_casa(tmp_path):
    """No servidor, o nome do oficial e o da substituta estavam ESCRITOS no
    cabeçalho do módulo. Aqui eles são do cadastro: sem ele, o papel sai sem
    nome nenhum — nem o da serventia, nem a cidade da data — e não com o de
    quem um dia respondeu pela casa."""
    import ri_digitalizacao as RDIGI
    odt = RDIGI.odt_da_digitalizacao(
        _pdf_de_duas_paginas(tmp_path), selo_texto="", nome="t",
        corpo_html=CORPO, data_emissao="2026-10-20")
    xml, _ = _xml(odt)
    cabecalho = re.findall(
        r'<text:p text:style-name="P-repro-cab\d">([^<]*)</text:p>', xml)
    assert cabecalho == ["REPÚBLICA FEDERATIVA DO BRASIL", "ESTADO DO MARANHÃO"]
    assert "SERVENTIA EXTRAJUDICIAL" not in xml
    assert ('<text:p text:style-name="P-repro-fecho-centro">20 de outubro de '
            '2026.</text:p>') in xml
    # e o módulo não guarda nome de pessoa; a cidade da casa tem os dois
    # testes de baixo (a da data é a do cadastro; a da lista local não está
    # escrita no módulo)
    fonte = (RAIZ / "ri_digitalizacao.py").read_text(encoding="utf-8")
    assert "<NOME" not in fonte


def test_a_cidade_da_data_e_a_do_cadastro_e_muda_com_ele(tmp_path):
    """A cidade e a UF da linha da data saem do cadastro da serventia
    (`ri_cidade`, `ri_uf`): com outra cidade no cadastro, o papel traz a outra,
    e nenhuma das duas está escrita no módulo."""
    import ri_digitalizacao as RDIGI
    outra = dict(SERVENTIA, unit_name="Ofício Único de Vila Fictícia do Norte",
                 ri_cidade="Vila Fictícia do Norte", ri_uf="PI")
    odt = RDIGI.odt_da_digitalizacao(
        _pdf_de_duas_paginas(tmp_path), selo_texto="", nome="t",
        corpo_html=CORPO, data_emissao="2026-10-20", serventia=outra)
    xml, _ = _xml(odt)
    assert ('<text:p text:style-name="P-repro-fecho-centro">Vila Fictícia do '
            'Norte/PI, 20 de outubro de 2026.</text:p>') in xml
    assert "Cidade Exemplo" not in xml
    fonte = (RAIZ / "ri_digitalizacao.py").read_text(encoding="utf-8")
    assert "Vila Fictícia" not in fonte and "Cidade Exemplo" not in fonte


def test_o_modulo_nao_traz_termo_da_lista_local_da_casa():
    """QUEM SABE O QUE É DA CASA É A LISTA LOCAL DO VARREDOR — 21/10/2026.
    Este teste escrevia a cidade da casa por extenso para provar que o módulo
    não a tinha, e o portão `ci/anti_vazamento.py` do servidor acusou o próprio
    teste. A cidade, os nomes e o CNS ficam em `ci/denylist.local.txt` (fora do
    git; na CI, o segredo `CG_DENYLIST_LOCAL`); sem a lista nesta máquina, não
    há o que conferir."""
    from ci import anti_vazamento as AV
    deny = AV.denylist_ativa(RAIZ)
    if not deny:
        pytest.skip("sem ci/denylist.local.txt nem $CG_DENYLIST_LOCAL nesta máquina")
    fonte = (RAIZ / "ri_digitalizacao.py").read_text(encoding="utf-8")
    achados = [str(a) for a in AV.varrer_texto(
        fonte, arquivo="ri_digitalizacao.py", denylist=deny) if a.tipo == "DENYLIST"]
    assert not achados, achados


def test_o_titular_pela_chave_antiga_do_cadastro_tambem_sai(tmp_path):
    """A tela de Configurações grava o titular como `ri_registrador`; o
    `serventia.dados` o unifica com `serventia_titular` — e o cabeçalho é o
    que `dados` devolve, e não uma leitura própria de chave."""
    import ri_digitalizacao as RDIGI
    import serventia
    sv = serventia.dados({"unit_name": "Serventia Extrajudicial de Cidade Exemplo",
                          "ri_registrador": "Mario Exemplo dos Santos",
                          "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    linhas = RDIGI.cabecalho_do_modelo_repro(sv)
    assert linhas == [
        ("REPÚBLICA FEDERATIVA DO BRASIL", "P-repro-cab1"),
        ("ESTADO DO MARANHÃO", "P-repro-cab1"),
        # a serventia que já se chama «Serventia…» não ganha o prefixo duas vezes
        ("SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO", "P-repro-cab2"),
        ("Mario Exemplo dos Santos — Tabelião e Registrador Oficial",
         "P-repro-cab3")]


def test_o_texto_do_modelo_e_o_da_base_e_nao_uma_copia_no_codigo(tmp_path, monkeypatch):
    """O CERTIFICO, a ressalva e o fecho do modelo são as frases da base
    (`RI_REPROGRAFICA_CAPA`, `RI_REPROGRAFICA_FECHO_DO_PAPEL`): o papel monta
    o que `ri_frases` devolve. Uma cópia no código imprimiria o texto de
    antes depois de a casa o ajustar na tela de Modelos."""
    import ri_digitalizacao as RDIGI
    import ri_frases
    texto_de_verdade = ri_frases.texto
    pedidas = []

    def texto(chave, con=None):
        pedidas.append(chave)
        if chave == "RI_REPROGRAFICA_CAPA":
            return "<p>CERTIFICO DA CASA: <i>{{ identificacao }}</i></p>"
        if chave == "RI_REPROGRAFICA_FECHO_DO_PAPEL":
            return "<p>FECHO DA CASA &amp; DO PAPEL.</p>"
        return texto_de_verdade(chave, con)
    monkeypatch.setattr(ri_frases, "texto", texto)
    odt = RDIGI.odt_da_digitalizacao(
        _pdf_de_duas_paginas(tmp_path), selo_texto="", nome="t",
        corpo_html=CORPO, identificacao="Matrícula nº 9.003 & anexo")
    xml, _ = _xml(odt)
    assert ('<text:p text:style-name="P-repro-texto">CERTIFICO DA CASA: '
            '<text:span text:style-name="T-italico">Matrícula nº 9.003 &amp; '
            'anexo, em 2 (duas) páginas.</text:span></text:p>') in xml
    assert ('<text:p text:style-name="P-repro-fecho">FECHO DA CASA &amp; DO '
            'PAPEL.</text:p>') in xml
    assert "ressalvadas as características" not in xml
    assert "Era o que constava" not in xml
    assert {"RI_REPROGRAFICA_CAPA", "RI_REPROGRAFICA_FECHO_DO_PAPEL"} <= set(pedidas)


def test_o_fecho_do_livro_ajustado_pela_casa_nao_sai_ao_lado_do_fecho_do_modelo(
        tmp_path, monkeypatch):
    """O corpo congelado leva o `RI_REPROGRAFICA_FECHO` que valia na emissão.
    O servidor tirava do papel só a redação de antes («Era o que nela
    continha.»); com a frase na base, a certidão emitida depois de um ajuste
    traz o texto ajustado no corpo, e ele sairia no papel junto do fecho do
    modelo."""
    import ri_digitalizacao as RDIGI
    import ri_frases
    texto_de_verdade = ri_frases.texto

    def texto(chave, con=None):
        if chave == "RI_REPROGRAFICA_FECHO":
            return "<p>Fecho do livro ajustado pela casa.</p>"
        return texto_de_verdade(chave, con)
    monkeypatch.setattr(ri_frases, "texto", texto)
    corpo = CORPO.replace("<p>Era o que nela continha.</p>",
                          "<p>Fecho do livro ajustado pela casa.</p>")
    odt = RDIGI.odt_da_digitalizacao(
        _pdf_de_duas_paginas(tmp_path), selo_texto="", nome="t",
        corpo_html=corpo)
    xml, _ = _xml(odt)
    assert "Fecho do livro ajustado" not in xml
    assert "CERTIFICO ainda que" in xml
    assert "Era o que constava no documento/assento reproduzido" in xml

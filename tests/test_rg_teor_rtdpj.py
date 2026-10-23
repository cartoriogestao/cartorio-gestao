"""Teor RTDPJ — modelo editável (piso + mo_modelos) e PDF.

Confere:
  - atribuição PJ vs TD pela série;
  - AVERBADO vs REGISTRADO;
  - cabeçalho em TODAS as folhas; sem livro/folha;
  - lavrante obrigatório;
  - leitura do modelo do banco (ajuste) com fallback ao piso;
  - chaves no catálogo modelos_da_casa.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import modelos_da_casa as CASA  # noqa: E402
import rg_teor_averbacao as TEOR_OLD  # noqa: E402
import rg_teor_rtdpj as TEOR  # noqa: E402
from ri_schema import SCHEMA as RI_SCHEMA  # noqa: E402


def _folha(cor=(240, 240, 240), size=(800, 1100)) -> Image.Image:
    return Image.new("RGB", size, cor)


def _con_com_mo():
    con = conexao_de_teste()
    con.executescript(RI_SCHEMA)
    return con


# ------------------------------------------------ API antiga compatível


def test_reexport_mantem_api_antiga():
    assert TEOR_OLD.intro is TEOR.intro
    assert TEOR_OLD.TeorAverbacaoError is TEOR.TeorRtdpjError
    frase = TEOR_OLD.intro(148)
    assert "AVERBADO" in frase


def test_intro_averbado_antes_do_registro():
    frase = TEOR.intro(148)
    assert "AVERBADO" in frase
    assert "Registro nº 148" in frase
    assert frase.index("AVERBADO") < frase.index("Registro nº")
    assert "Termo" not in frase
    assert frase.startswith("CERTIFICO que me foi apresentado para ser")
    assert ", hoje," not in frase
    assert " hoje" not in frase.lower()


def test_intro_registrado():
    frase = TEOR.intro(99, tipo_ato="REGISTRO")
    assert "REGISTRADO" in frase
    assert "AVERBADO" not in frase
    assert "Registro nº 99" in frase


def test_atribuicao_pj_vs_td():
    pj = TEOR.linhas_cabecalho(cns="000000", serie="PJ_A")
    td = TEOR.linhas_cabecalho(cns="000000", serie="TD_B")
    assert "Registro Civil das Pessoas Jurídicas" in "\n".join(pj)
    assert "Registro de Títulos e Documentos" in "\n".join(td)
    assert "de Pessoas" not in "\n".join(pj)
    assert TEOR.cabecalho_tem_livro_ou_folha(pj) is False
    assert TEOR.cabecalho_tem_livro_ou_folha(td) is False
    for linhas in (pj, td):
        junto = "\n".join(linhas).lower()
        for proibido in ("livro", "folha", "fl.", "série", "ficha"):
            assert proibido not in junto


def test_chaves_do_catalogo():
    for chave in TEOR.PADROES_POR_CHAVE:
        assert chave in CASA.POR_CHAVE, chave
        assert CASA.formato_de(chave) == CASA.CHAVES
        assert CASA.padrao_de(chave).strip()
        assert "===CABECALHO===" in CASA.padrao_de(chave)
        assert "{numero}" in CASA.padrao_de(chave)
        assert "{full_name}" in CASA.padrao_de(chave)


def test_chave_por_serie_e_tipo():
    assert TEOR.chave_do_modelo(serie="PJ_A", tipo_ato="AVERBACAO") == (
        "RCPJ_TEOR_AVERBACAO")
    assert TEOR.chave_do_modelo(serie="TD_C", tipo_ato="REGISTRO") == (
        "RTD_TEOR_REGISTRO")


def test_encerramento_com_lavrante_da_sessao():
    texto = TEOR.encerramento(
        lavrante_nome="MARIA DA SILVA", lavrante_funcao="Escrevente")
    assert "Eu, MARIA DA SILVA, Escrevente, o subscrevo e assino." in texto
    assert "averbação" in texto
    reg = TEOR.encerramento(
        lavrante_nome="MARIA DA SILVA", lavrante_funcao="Escrevente",
        tipo_ato="REGISTRO")
    assert "para registro" in reg
    data = TEOR.linha_data(cidade="Cidade Exemplo", uf="MA")
    assert data.startswith("Cidade Exemplo/MA,")


def test_flags_cabecalho_em_todas_encerramento_so_na_ultima():
    assert TEOR.flags_das_paginas(1) == [(True, True)]
    assert TEOR.flags_das_paginas(3) == [
        (True, False), (True, False), (True, True)]
    with pytest.raises(TEOR.TeorRtdpjError):
        TEOR.flags_das_paginas(0)


def test_gerar_pdf_averbacao_e_registro_pj_td():
    pdf_av = TEOR.gerar_pdf(
        numero_registro=148, imagens=[_folha()],
        lavrante_nome="MARIO EXEMPLO DOS SANTOS",
        lavrante_funcao="Tabelião e Oficial de Registro",
        serie="PJ_A", tipo_ato="AVERBACAO",
    )
    assert pdf_av.startswith(b"%PDF")

    pdf_reg = TEOR.gerar_pdf(
        numero_registro=50, imagens=[_folha(), _folha((200, 200, 200))],
        lavrante_nome="MARIA DA SILVA", lavrante_funcao="Escrevente",
        serie="TD_B", tipo_ato="REGISTRO",
    )
    assert pdf_reg.startswith(b"%PDF")
    assert pdf_reg.count(b"/Type /Page /Parent") == 2


def test_recusa_sem_lavrante_ou_sem_numero():
    with pytest.raises(TEOR.TeorRtdpjError, match="número"):
        TEOR.intro("")
    with pytest.raises(TEOR.TeorRtdpjError, match="nome"):
        TEOR.encerramento(lavrante_nome="", lavrante_funcao="Escrevente")
    with pytest.raises(TEOR.TeorRtdpjError, match="função"):
        TEOR.encerramento(lavrante_nome="X", lavrante_funcao="")


def test_modelo_lido_do_banco_com_fallback():
    con = _con_com_mo()
    # Sem linha → piso
    textos = TEOR.textos_prontos(
        numero_registro=148, lavrante_nome="MARIO",
        lavrante_funcao="Oficial", serie="PJ_A", tipo_ato="AVERBACAO",
        con=con)
    assert "AVERBADO" in textos["intro"]
    assert "Registro Civil das Pessoas Jurídicas" in textos["linhas_cabecalho"][1]

    # Ajuste no banco altera a intro
    CASA.salvar(
        con, "RCPJ_TEOR_AVERBACAO",
        corpo=(
            "===CABECALHO===\n"
            "{unit_short} — CNS {cns}\n"
            "{atribuicao}\n"
            "===INTRO===\n"
            "TEXTO AJUSTADO pela casa: AVERBADO no Registro nº {numero}.\n"
            "===ENCERRAMENTO===\n"
            "Eu, {full_name}, {funcao}, o subscrevo e assino.\n"
            "===DATA===\n"
            "{cidade}/{uf}, {data_extenso}.\n"
        ),
        quem="teste", agora="2026-09-11T12:00:00")
    textos2 = TEOR.textos_prontos(
        numero_registro=148, lavrante_nome="MARIO",
        lavrante_funcao="Oficial", serie="PJ_A", tipo_ato="AVERBACAO",
        con=con)
    assert "TEXTO AJUSTADO pela casa" in textos2["intro"]
    assert "148" in textos2["intro"]

    # Voltar ao padrão = apagar
    CASA.restaurar(con, "RCPJ_TEOR_AVERBACAO")
    textos3 = TEOR.textos_prontos(
        numero_registro=148, lavrante_nome="MARIO",
        lavrante_funcao="Oficial", serie="PJ_A", tipo_ato="AVERBACAO",
        con=con)
    assert "TEXTO AJUSTADO" not in textos3["intro"]
    assert "CERTIFICO" in textos3["intro"]


def test_teor_texto_curto():
    assert "AVERBADO" in TEOR.teor_texto_curto(361)
    assert "REGISTRADO" in TEOR.teor_texto_curto(10, tipo_ato="REGISTRO")


def test_intro_nao_leva_a_palavra_hoje():
    """Correção do oficial (11/09/2026): sem «apresentado, hoje, para»."""
    for tipo in ("AVERBACAO", "REGISTRO"):
        frase = TEOR.intro(148, tipo_ato=tipo)
        assert "hoje" not in frase.lower()
        assert "apresentado para ser" in frase


def test_intro_com_natureza_e_data_assinatura():
    """Oficial 11/09/2026: diferenciar averbações com tipo do ato + data."""
    frase = TEOR.intro(
        148, tipo_ato="AVERBACAO",
        natureza_ato="Estatuto social consolidado",
        data_assinatura="08/05/2026")
    assert "Tipo do ato: Estatuto social consolidado." in frase
    assert "Data da assinatura: 08/05/2026." in frase
    assert "AVERBADO" in frase
    assert "Registro nº 148" in frase
    assert "hoje" not in frase.lower()
    # Sem os campos → intro curta (compat)
    curta = TEOR.intro(148, tipo_ato="AVERBACAO")
    assert "Tipo do ato:" not in curta
    assert "Data da assinatura:" not in curta
    assert "hoje" not in curta.lower()


def test_piso_dos_modelos_sem_hoje():
    for chave, corpo in TEOR.PADROES_POR_CHAVE.items():
        assert "hoje" not in corpo.lower(), chave
        assert "apresentado para ser" in corpo, chave
        assert "{natureza_ato}" in corpo, chave
        assert "{data_assinatura}" in corpo, chave


def test_pdf_ultima_folha_reserva_faixa_do_selo():
    """Rodapé da ÚLTIMA folha tem faixa para colar a etiqueta (não no topo)."""
    pagina = TEOR.montar_pagina(
        _folha(), textos={
            "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
            "intro": TEOR.intro(148),
            "encerramento": TEOR.encerramento(
                lavrante_nome="MARIO", lavrante_funcao="Oficial"),
            "data": TEOR.linha_data(),
            "ctx": {"funcao": "Oficial"},
        },
        with_header=True, with_closing=True, com_faixa_selo=True)
    assert pagina.size == (TEOR.A4_W, TEOR.A4_H)
    # Topo NÃO é mais a faixa: margem lateral no alto permanece branca limpa
    # (a faixa centrada ficava no meio). Amostra no rodapé, centro da faixa.
    y_faixa = TEOR.A4_H - TEOR.SELO_FAIXA_H // 2
    amostra = pagina.getpixel((TEOR.A4_W // 2, y_faixa))
    assert amostra[0] > 140, f"faixa do selo no rodapé parece ocupada: {amostra}"
    # Confirma que a faixa NÃO está no topo: y=40 no centro costumava ser
    # a área clara da faixa; agora o cabeçalho ocupa o alto — a reserva
    # de rodapé inclui encerramento + faixa.
    assert TEOR._rodape_reservado(with_closing=True, com_faixa_selo=True) == (
        TEOR.FOOTER_H + TEOR.SELO_FAIXA_H)
    assert TEOR.SELO_FAIXA_H >= 170
    assert TEOR.SELO_FAIXA_ROTULO == "selo averbação"


def test_pdf_faixa_so_na_ultima_pagina():
    """Multi: 1ª sem faixa; última com faixa no rodapé (com_faixa_selo)."""
    textos = {
        "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
        "intro": TEOR.intro(148),
        "encerramento": TEOR.encerramento(
            lavrante_nome="MARIO", lavrante_funcao="Oficial"),
        "data": TEOR.linha_data(),
        "ctx": {"funcao": "Oficial"},
    }
    p_meio = TEOR.montar_pagina(
        _folha(), textos=textos, with_header=True, with_closing=False,
        com_faixa_selo=False)
    p_ult = TEOR.montar_pagina(
        _folha(), textos=textos, with_header=True, with_closing=True,
        com_faixa_selo=True)
    assert p_ult.size == p_meio.size
    y_faixa = TEOR.A4_H - TEOR.SELO_FAIXA_H // 2
    amostra_ult = p_ult.getpixel((TEOR.A4_W // 2, y_faixa))
    assert amostra_ult[0] > 140
    # Página do meio: rodapé sem faixa reservada (só margem 40).
    assert TEOR._rodape_reservado(with_closing=False, com_faixa_selo=False) == 40


def test_pdf_com_arquivamento_duas_areas():
    """1ª averbação: duas áreas rotuladas no rodapé (averbação + arquivamento)."""
    pagina = TEOR.montar_pagina(
        _folha(), textos={
            "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
            "intro": TEOR.intro(148),
            "encerramento": TEOR.encerramento(
                lavrante_nome="MARIO", lavrante_funcao="Oficial"),
            "data": TEOR.linha_data(),
            "ctx": {"funcao": "Oficial"},
        },
        with_header=True, with_closing=True,
        com_faixa_selo=True, com_arquivamento=True)
    assert pagina.size == (TEOR.A4_W, TEOR.A4_H)
    # Duas caixas lado a lado no rodapé: amostra no centro de cada metade.
    gap = 16
    faixa_w = min((TEOR.A4_W - 2 * TEOR.SIDE - gap) // 2, 600)
    total_w = 2 * faixa_w + gap
    x_start = (TEOR.A4_W - total_w) // 2
    y = TEOR.A4_H - TEOR.SELO_FAIXA_H // 2
    for x in (x_start + faixa_w // 2, x_start + faixa_w + gap + faixa_w // 2):
        amostra = pagina.getpixel((x, y))
        assert amostra[0] > 140, f"área do selo ocupada em x={x}: {amostra}"
    assert "arquivamento" in TEOR.SELO_FAIXA_ROTULO_ARQUIVAMENTO


def test_gerar_pdf_com_arquivamento_aceita_parametro():
    pdf = TEOR.gerar_pdf(
        numero_registro=148, imagens=[_folha(), _folha((200, 200, 200))],
        lavrante_nome="MARIO", lavrante_funcao="Oficial",
        serie="PJ_A", tipo_ato="AVERBACAO",
        com_arquivamento=True)
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page /Parent") == 2

def test_gerar_pdf_escala_individual_por_pagina():
    """Multi: cada imagem cabe na área útil da própria página (sem baliza comum)."""
    pequena = _folha(size=(400, 600))
    grande = _folha(cor=(180, 180, 180), size=(1200, 1600))
    textos = {
        "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
        "intro": TEOR.intro(148),
        "encerramento": TEOR.encerramento(
            lavrante_nome="MARIO", lavrante_funcao="Oficial"),
        "data": TEOR.linha_data(),
        "ctx": {"funcao": "Oficial"},
    }
    p1 = TEOR.montar_pagina(
        pequena, textos=textos, with_header=True, with_closing=False,
        com_faixa_selo=False)
    p2 = TEOR.montar_pagina(
        grande, textos=textos, with_header=True, with_closing=True,
        com_faixa_selo=True)
    assert p1.size == p2.size == (TEOR.A4_W, TEOR.A4_H)
    assert not hasattr(TEOR, "_caixa_baliza_pela_menor")
    pdf = TEOR.gerar_pdf(
        numero_registro=148, imagens=[pequena, grande],
        lavrante_nome="MARIO", lavrante_funcao="Oficial",
        serie="PJ_A", tipo_ato="AVERBACAO")
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page /Parent") == 2


def _selo_de_teste(numero="AVERBA000000CARIMBOTESTE0001"):
    return {
        "numero": numero,
        "texto": (f"Poder Judiciário – TJMA. Selo: {numero}, "
                  "11/09/2026 15:43:18, Ato: 15.9.1, Parte(s): TESTE, "
                  "Total R$ 40,99 Emol R$ 36,60 FERC R$ 1,10 FADEP R$ 1,46 "
                  "FEMP R$ 1,46 FERRFIS R$ 0,37 Consulte em "
                  "https://selo.tjma.jus.br"),
        "qr_texto": numero,
    }


def test_com_selo_o_carimbo_sai_no_papel_no_modelo_do_ri():
    """Pedido do oficial (11/09/2026): «colocar automaticamente a etiqueta

    no livro quando o selo é emitido, no modelo do selo do RI» — com selo,
    a área deixa de ser a moldura tracejada («cole aqui») e ganha o número,
    o QR e a linha de valores, no mesmo pixel onde antes só havia branco.
    """
    textos = {
        "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
        "intro": TEOR.intro(148),
        "encerramento": TEOR.encerramento(
            lavrante_nome="MARIO", lavrante_funcao="Oficial"),
        "data": TEOR.linha_data(),
        "ctx": {"funcao": "Oficial"},
    }
    sem_selo = TEOR.montar_pagina(
        _folha(), textos=textos, with_header=True, with_closing=True,
        com_faixa_selo=True)
    com_selo = TEOR.montar_pagina(
        _folha(), textos=textos, with_header=True, with_closing=True,
        com_faixa_selo=True, selo_averbacao=_selo_de_teste())
    assert sem_selo.size == com_selo.size == (TEOR.A4_W, TEOR.A4_H)

    # Amostra na área do QR (canto esquerdo da faixa, onde o carimbo
    # desenha o quadrado de módulos): escuro com selo, claro sem ele.
    y_faixa = TEOR.A4_H - TEOR.SELO_FAIXA_H + 40
    faixa_w = min(TEOR.A4_W - 2 * TEOR.SIDE, 600)
    x0 = (TEOR.A4_W - faixa_w) // 2
    x_qr = x0 + 20
    pixel_sem = sem_selo.getpixel((x_qr, y_faixa))
    pixel_com = com_selo.getpixel((x_qr, y_faixa))
    assert pixel_sem[0] > 200, f"sem selo devia estar em branco: {pixel_sem}"
    assert pixel_com[0] < pixel_sem[0], (
        f"com selo o QR devia ter escurecido a área: {pixel_com} vs "
        f"{pixel_sem}")


def test_o_qr_do_selo_nao_toma_quase_toda_a_faixa():
    """Relato do oficial (11/09/2026): «o modelo do selo pode diminuir

    bastante o tamanho do QR code e ocupar menos espaço». O QR ocupava até
    140 px (~24 mm) de um quadro de 200 px de altura — quase 80% dela.
    Reduzido a 90 px, sobra altura para o número e a linha de valores, e a
    área além do novo lado deve continuar em branco (o carimbo não estica
    o QR para preencher o espaço que sobrou).
    """
    textos = {
        "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
        "intro": TEOR.intro(148),
        "encerramento": TEOR.encerramento(
            lavrante_nome="MARIO", lavrante_funcao="Oficial"),
        "data": TEOR.linha_data(),
        "ctx": {"funcao": "Oficial"},
    }
    com_selo = TEOR.montar_pagina(
        _folha(), textos=textos, with_header=True, with_closing=True,
        com_faixa_selo=True, selo_averbacao=_selo_de_teste())
    y_faixa = TEOR.A4_H - TEOR.SELO_FAIXA_H + 40
    faixa_w = min(TEOR.A4_W - 2 * TEOR.SIDE, 600)
    x0 = (TEOR.A4_W - faixa_w) // 2
    pixel_perto = com_selo.getpixel((x0 + 20, y_faixa))
    pixel_longe = com_selo.getpixel((x0 + 110, y_faixa))
    assert pixel_perto[0] < 200, (
        f"o QR devia continuar perto da borda esquerda: {pixel_perto}")
    assert pixel_longe[0] > 200, (
        "o QR encolhido não devia mais alcançar 110 px da borda — "
        f"pixel: {pixel_longe}")


def test_gerar_pdf_aceita_selo_averbacao_e_arquivamento():
    """`gerar_pdf` só desenha o que já saiu — não pede selo a ninguém."""
    pdf = TEOR.gerar_pdf(
        numero_registro=148, imagens=[_folha(), _folha((200, 200, 200))],
        lavrante_nome="MARIO", lavrante_funcao="Oficial",
        serie="PJ_A", tipo_ato="AVERBACAO", com_arquivamento=True,
        selo_averbacao=_selo_de_teste("AVERBA000000UM0000000000001"),
        selo_arquivamento=_selo_de_teste("ARQUIV000000DOIS000000002"))
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page /Parent") == 2


def test_sem_selo_continua_a_moldura_tracejada_de_sempre():
    """API antiga (sem os parâmetros novos) continua produzindo a mesma

    reserva em branco — quem já chamava `gerar_pdf`/`montar_pagina` sem
    saber do selo não regride.
    """
    pdf = TEOR.gerar_pdf(
        numero_registro=148, imagens=[_folha()],
        lavrante_nome="MARIO", lavrante_funcao="Oficial",
        serie="PJ_A", tipo_ato="AVERBACAO")
    assert pdf.startswith(b"%PDF")


def test_parse_campos_do_teor_das_linhas():
    teor = (
        "CERTIFICO que me foi apresentado para ser AVERBADO no Registro nº 148 "
        "o documento digitalizado abaixo:\n"
        "Tipo do ato: Edital de convocação.\n"
        "Data da assinatura: 08/05/2026."
    )
    nat, data = TEOR.parse_campos_do_teor(teor)
    assert nat == "Edital de convocação"
    assert data == "08/05/2026"
    assert TEOR.parse_campos_do_teor("") == ("", "")
    assert TEOR.parse_campos_do_teor(None) == ("", "")


def test_com_arquivamento_nao_supoe_primeira_averbacao():
    """Correção do oficial (11/09/2026): «não tem nada que ligue 1 averbação

    a arquivamento, foi algo que o projeto entendeu errado». A versão
    anterior marcava `com_arquivamento=True` para a averbação de MENOR id do
    registro mesmo sem selo 15.22 nenhum. Agora só reserva a faixa quando o
    próprio ato tem o selo — nem a 1ª, nem qualquer outra, ganha de graça.
    """
    con = conexao_de_teste()
    con.executescript(
        """
        CREATE TABLE rg_atos(
            id INTEGER PRIMARY KEY, registro_id INTEGER, tipo TEXT);
        CREATE TABLE sd_selos(
            id INTEGER PRIMARY KEY, numero TEXT, texto TEXT,
            referencia TEXT, tabela TEXT, ato_id INTEGER);
        INSERT INTO rg_atos VALUES (10, 1, 'REGISTRO');
        INSERT INTO rg_atos VALUES (75, 1, 'AVERBACAO');
        INSERT INTO rg_atos VALUES (76, 1, 'AVERBACAO');
        """
    )
    # A "1ª averbação" (75) NÃO ganha a faixa só por ser a primeira.
    assert TEOR.com_arquivamento_para_ato(con, 1, 75) is False
    assert TEOR.com_arquivamento_para_ato(con, 1, 76) is False
    con.execute(
        """INSERT INTO sd_selos(numero, texto, referencia, tabela, ato_id)
           VALUES ('ARQUIV000000X', 'Ato: 15.22', 'rg_atos:76:15.22:0',
                   'rg_atos', 76)""")
    assert TEOR.tem_selo_arquivamento(con, 76) is True
    # A SEGUNDA (76) ganha, porque foi ELA que teve o selo 15.22 — não por
    # ordem, e sim porque o operador marcou aquele item para este ato.
    assert TEOR.com_arquivamento_para_ato(con, 1, 76) is True
    assert TEOR.com_arquivamento_para_ato(con, 1, 75) is False


def test_sem_sd_selos_a_transacao_de_quem_chama_continua():
    """Revisão do L018: o `except` em volta da consulta a `sd_selos` deixaria a
    transação do PostgreSQL abortada? Não: com a transação aberta, o
    `bd_nativo` põe o comando num SAVEPOINT e volta a ele quando falha. O que
    se gravou antes e o que se grava depois saem confirmados juntos."""
    con = conexao_de_teste()
    con.execute("CREATE TABLE rg_atos (id INTEGER PRIMARY KEY, tipo TEXT)")
    con.commit()
    con.execute("INSERT INTO rg_atos (id, tipo) VALUES (1, 'REGISTRO')")
    assert TEOR.tem_selo_arquivamento(con, 1) is False
    con.execute("INSERT INTO rg_atos (id, tipo) VALUES (2, 'AVERBACAO')")
    con.commit()
    assert [r[0] for r in con.execute(
        "SELECT id FROM rg_atos ORDER BY id")] == [1, 2]


def test_selos_extra_nao_quebra_e_reserva_mais_altura():
    """Achado do oficial (11/09/2026): «preciso que todos os selos estejam

    no ato da averbação». Um ato pode ter mais itens do que as duas caixas
    nomeadas (averbação + arquivamento) — `selos_extra` desenha o resto em
    linhas extras, sem estourar nem sobrepor o encerramento.
    """
    textos = {
        "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
        "intro": TEOR.intro(148),
        "encerramento": TEOR.encerramento(
            lavrante_nome="MARIO", lavrante_funcao="Oficial"),
        "data": TEOR.linha_data(),
        "ctx": {"funcao": "Oficial"},
    }
    extras = [
        {"rotulo": "15.1", **_selo_de_teste("PRENOT000000UM0000000000A")},
        {"rotulo": "15.9.2", **_selo_de_teste("AVERBA000000DOIS00000000B")},
        {"rotulo": "15.9.2", **_selo_de_teste("AVERBA000000TRES00000000C")},
    ]
    im = TEOR.montar_pagina(
        _folha(), textos=textos, with_header=True, with_closing=True,
        com_faixa_selo=True, selo_averbacao=_selo_de_teste(),
        selos_extra=extras)
    assert im.size == (TEOR.A4_W, TEOR.A4_H)
    assert TEOR._linhas_reservadas_extra(extras) == 2  # 3 extras, 2 por linha
    assert TEOR._linhas_reservadas_extra([]) == 0
    assert TEOR._linhas_reservadas_extra(None) == 0


def test_selos_extra_aparecem_de_verdade_dentro_da_pagina():
    """Achado do oficial (11/09/2026), ao abrir o PDF de verdade: «por que a

    averbação não foi com os 3 selos com QR code dentro do PDF?» — a
    primeira versão de `selos_extra` reservava a altura certa mas desenhava
    as linhas extras a partir de `y1` (o fim da linha nomeada, já perto do
    fim da página) em vez de a partir de `y0` (o topo do bloco reservado) —
    as caixas extras caíam FORA da folha, invisíveis. Este teste amostra
    pixel de verdade na posição de cada linha extra, e não só o tamanho da
    imagem ou a ausência de erro.
    """
    textos = {
        "linhas_cabecalho": TEOR.linhas_cabecalho(serie="PJ_A"),
        "intro": TEOR.intro(148),
        "encerramento": TEOR.encerramento(
            lavrante_nome="MARIO", lavrante_funcao="Oficial"),
        "data": TEOR.linha_data(),
        "ctx": {"funcao": "Oficial"},
    }
    extras = [
        {"rotulo": "15.1", **_selo_de_teste("PRENOT000000UM0000000000A")},
        {"rotulo": "15.9.2", **_selo_de_teste("AVERBA000000DOIS00000000B")},
    ]
    im = TEOR.montar_pagina(
        _folha(), textos=textos, with_header=True, with_closing=True,
        com_faixa_selo=True, selo_averbacao=_selo_de_teste(),
        selos_extra=extras)
    linhas_extra = TEOR._linhas_reservadas_extra(extras)
    assert linhas_extra == 1  # 2 extras cabem numa linha (2 por linha)

    faixa_w = min((TEOR.A4_W - 2 * TEOR.SIDE - 16) // 2, 600)
    x_start = (TEOR.A4_W - (2 * faixa_w + 16)) // 2
    y0_bloco = TEOR.A4_H - TEOR.SELO_FAIXA_H * (1 + linhas_extra) + 4

    def _tem_pixel_escuro(x0: int, x1: int, y0: int, y1: int) -> bool:
        for x in range(x0, x1, 3):
            for y in range(y0, y1, 3):
                if im.getpixel((x, y))[0] < 200:
                    return True
        return False

    for coluna, x0 in enumerate((x_start, x_start + faixa_w + 16)):
        assert _tem_pixel_escuro(x0, x0 + faixa_w, y0_bloco,
                                 y0_bloco + TEOR.SELO_FAIXA_H - 16), (
            f"o selo extra da coluna {coluna} tinha de estar DENTRO da "
            f"página, com algo desenhado (número/QR) — veio tudo em branco")


def test_gerar_pdf_com_selos_extra_produz_pdf_valido(tmp_path):
    caminho = tmp_path / "folha.png"
    _folha().save(caminho)
    extras = [{"rotulo": "15.1", **_selo_de_teste("PRENOT000000UM0000000000A")}]
    pdf = TEOR.gerar_pdf(
        numero_registro=148, imagens=[caminho],
        lavrante_nome="MARIO", lavrante_funcao="Oficial",
        serie="PJ_A", tipo_ato="AVERBACAO",
        selo_averbacao=_selo_de_teste(),
        selos_extra=extras)
    assert pdf.startswith(b"%PDF-1.4")


# ---------------------------------- o que o termo declara além do teor (LD09)


def _intro_de_cada_folha(monkeypatch, **kw) -> list[str]:
    """A intro que `gerar_pdf` manda desenhar em cada folha, na ordem."""
    vistas: list[str] = []
    montar = TEOR.montar_pagina

    def capturar(src, *, textos, **resto):
        vistas.append(textos["intro"])
        return montar(src, textos=textos, **resto)

    monkeypatch.setattr(TEOR, "montar_pagina", capturar)
    assert TEOR.gerar_pdf(lavrante_nome="FULANO DE EXEMPLO",
                          lavrante_funcao="Escrevente", **kw).startswith(b"%PDF")
    return vistas


def test_a_linha_de_declaracao_vazia_sai_inteira_e_a_do_certifico_fica():
    """A linha só de claros do LD09 sai quando falta um deles — «Protocolizado
    em , sob o nº .» seria rótulo sem valor no papel assinado. A que tem também
    um claro de sempre fica: o ajuste da casa que pôs o apresentante dentro do
    CERTIFICO não perde a frase do CERTIFICO no ato sem título."""
    molde = ("CERTIFICO, apresentado por {apresentante}, o Registro nº {numero}:\n"
             "Protocolizado em {data_protocolo}, sob o nº {protocolo}.\n"
             "Texto sem claro nenhum.\n"
             "Valor: {valor}.")
    vazio = {"numero": "12", "apresentante": "", "data_protocolo": "02/10/2026",
             "protocolo": "", "valor": ""}
    assert TEOR._sem_declaracao_vazia(molde, vazio) == (
        "CERTIFICO, apresentado por {apresentante}, o Registro nº {numero}:\n"
        "Texto sem claro nenhum.")
    cheio = dict(vazio, apresentante="SICRANO DE EXEMPLO", protocolo="7",
                 valor="R$ 1,00")
    assert TEOR._sem_declaracao_vazia(molde, cheio) == molde


def test_as_declaracoes_saem_na_primeira_folha_e_nao_em_todas(monkeypatch):
    """O extrato no alto de CADA folha encolheria a imagem de todas: da
    segunda em diante, a intro de antes delas — o CERTIFICO e a natureza."""
    folhas = _intro_de_cada_folha(
        monkeypatch, numero_registro=9, imagens=[_folha(), _folha(), _folha()],
        serie="TD_C", tipo_ato="REGISTRO", natureza_ato="Contrato de exemplo",
        protocolo="7", data_protocolo="02/10/2026", apresentante="SICRANO DE EXEMPLO",
        declaracoes={"valor": "R$ 1,00", "prazo": "doze meses"})
    assert len(folhas) == 3
    assert "Protocolizado em 02/10/2026, sob o nº 7." in folhas[0]
    assert "Apresentante: SICRANO DE EXEMPLO." in folhas[0]
    assert "Valor: R$ 1,00." in folhas[0] and "Prazo: doze meses." in folhas[0]
    for seguinte in folhas[1:]:
        assert seguinte == TEOR.intro(9, tipo_ato="REGISTRO",
                                      natureza_ato="Contrato de exemplo")
        assert "Valor" not in seguinte and "Apresentante" not in seguinte


def test_o_total_de_paginas_sai_no_livro_f_e_so_nele(monkeypatch):
    """LRP art. 127-A, § 3º: o termo do registro para conservação diz o total
    de páginas registradas — a conta das folhas que o PDF traslada. Nos livros
    B e C a lei não o pede, e o termo deles não muda."""
    tres = [_folha(), _folha(), _folha()]
    f = _intro_de_cada_folha(monkeypatch, numero_registro=5, imagens=tres,
                             serie="TD_F", tipo_ato="REGISTRO")
    assert "Total de páginas registradas: 3 páginas." in f[0]
    um = _intro_de_cada_folha(monkeypatch, numero_registro=5, imagens=[_folha()],
                              serie="TD_F", tipo_ato="REGISTRO")
    assert "Total de páginas registradas: 1 página." in um[0]
    b = _intro_de_cada_folha(monkeypatch, numero_registro=5, imagens=tres,
                             serie="TD_B", tipo_ato="REGISTRO")
    assert not any("páginas" in x for x in b)


def test_o_cabecalho_da_averbacao_diz_o_numero_dela_e_a_previa_nao_inventa():
    """O número de ordem da própria averbação (LRP arts. 149 e 153) no alto da
    folha; a prévia da averbação ainda sem número não ganha «Averbação nº »."""
    com = TEOR.textos_prontos(numero_registro=4321, lavrante_nome="F",
                              lavrante_funcao="E", serie="TD_B",
                              tipo_ato="AVERBACAO", numero_averbacao=4322)
    assert "Averbação nº 4322" in com["linhas_cabecalho"]
    sem = TEOR.textos_prontos(numero_registro=4321, lavrante_nome="F",
                              lavrante_funcao="E", serie="TD_B",
                              tipo_ato="AVERBACAO")
    assert not any("Averbação" in ln for ln in sem["linhas_cabecalho"])
    # a intro, que vai ao livro, é a mesma com e sem o número
    assert com["intro"] == sem["intro"] == TEOR.intro(4321)

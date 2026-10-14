"""Certidão PDF RCPJ/RTD — capa + faixa + modelos + montar_teor."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import atrib_certidao as CE  # noqa: E402
import modelos_da_casa as CASA  # noqa: E402
import rg_certidao_pdf as CERT  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from rg_schema import init_rg_schema  # noqa: E402
from ri_schema import init_ri_schema  # noqa: E402


def _folha(cor=(230, 230, 230), size=(800, 1100)) -> Image.Image:
    return Image.new("RGB", size, cor)


def test_chaves_no_catalogo():
    for chave in CERT.PADROES_POR_CHAVE:
        assert chave in CASA.POR_CHAVE, chave
        assert CASA.formato_de(chave) == CASA.CHAVES
        corpo = CASA.padrao_de(chave)
        assert corpo.strip()
        assert "{numero}" in corpo
        assert "{cns}" in corpo or "{atribuicao}" in corpo


def test_piso_capa_tem_certifico_e_cns():
    corpo = CERT.MODELO_RCPJ_CERTIDAO_CAPA
    assert "Certifico e dou fé" in corpo
    assert "{cns}" in corpo
    assert "{atribuicao}" in corpo
    assert "===CABECALHO===" in corpo
    assert "Registro Civil das Pessoas Jurídicas" in CERT.ATRIBUICAO_RCPJ
    # Sem branding SP
    junto = corpo.lower()
    for proibido in ("3107-0111", "3777-8680", "8rtd", "cdtsp", "tjsp"):
        assert proibido not in junto


def test_piso_faixa_placeholders():
    corpo = CERT.MODELO_RCPJ_CERTIDAO_FAIXA
    assert "{protocolo}" in corpo
    assert "{numero}" in corpo
    assert "{full_name}" in corpo


def test_gerar_pdf_capa_e_paginas():
    pdf = CERT.gerar_pdf(
        numero=148,
        imagens=[_folha(), _folha((200, 200, 200))],
        lavrante_nome="MARIO EXEMPLO DOS SANTOS",
        lavrante_funcao="Tabelião e Oficial de Registro",
        denominacao="CAIXA ESCOLAR SANTA ISABEL",
        natureza="Ata de assembleia geral de constituição",
        protocolo="2026.09.17",
        data_apresentacao="2026-09-11",
        data_registro="2011-12-23",
        serie="PJ_A",
        volume="3",
        cns="000000",
    )
    assert pdf.startswith(b"%PDF")
    # **A 1ª FOLHA CABE NA CAPA** — pedido do oficial (11/09/2026): «fazer
    # caber a primeira página dos atos já na primeira folha da certidão».
    # Com capa curta (denominação/natureza pequenas) sobra espaço de sobra
    # abaixo do quadro de emolumentos, e a 1ª folha entra ali — a certidão
    # sai com 2 páginas (capa+1ª folha fundidas, + a 2ª folha), e não 3.
    assert pdf.count(b"/Type /Page /Parent") == 2

    # OCR leve: renderizar capa e procurar CNS / CERTIFICO / atribuição
    import pypdfium2 as pdfium
    from io import BytesIO
    doc = pdfium.PdfDocument(pdf)
    try:
        pil = doc[0].render(scale=72 / 72).to_pil()
        # Não temos OCR fácil; confere tamanho A4-ish e que gerou
        assert pil.size[0] > 500 and pil.size[1] > 700
        # Capa com a 1ª folha fundida + a 2ª folha interna == 2 páginas.
        assert len(doc) == 2
    finally:
        doc.close()


def test_textos_prontos_contem_certifico_cns():
    t = CERT.textos_prontos(
        numero=148, lavrante_nome="MARIO EXEMPLO DOS SANTOS",
        lavrante_funcao="Tabelião e Oficial de Registro",
        denominacao="CAIXA", natureza="ATA", protocolo="2026.09.17",
        paginas=2, serie="PJ_A", cns="000000")
    junto = "\n".join([t["cabecalho"], t["titulo"], t["corpo"], t["fecho"],
                       t["faixa"]])
    assert "000000" in junto
    assert "Certifico e dou fé" in junto or "CERTIFICO" in junto.upper()
    assert "Registro Civil das Pessoas Jurídicas" in junto
    for proibido in ("3107-0111", "3777-8680", "8rtd.com", "cdtsp"):
        assert proibido not in junto.lower()
    assert "000001" in t["ctx"]["pagina"] or t["ctx"]["pagina"]


def test_faixa_tem_pagina_formatada():
    ctx = CERT.contexto_certidao(
        numero=56, lavrante_nome="X", lavrante_funcao="Y",
        pagina=3, total_paginas=7)
    assert ctx["pagina"] == "000003"
    assert ctx["total_paginas"] == "000007"


def test_anexo_padrao_exclui_pacotes():
    assert CERT.anexo_padrao_marcado("0148_folha_067.png") is True
    assert CERT.anexo_padrao_marcado("01_edital_ata_lista.pdf") is True
    assert CERT.anexo_padrao_marcado("DOCUMENTOS PARA AVERBAÇÃO.pdf") is False
    assert CERT.anexo_padrao_marcado(
        "registro_originario_pacote.pdf",
        "PDF do pacote Registro Originário") is False


def test_montar_teor_inclui_averbacoes():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_rg_schema(con)
    init_ri_schema(con)
    CE.init_atrib_certidao_schema(con)
    cur = con.execute(
        """INSERT INTO rg_registros(atribuicao, serie, volume, numero, natureza,
               requerente_nome, situacao, teor, origem, criado_em)
           VALUES (3,'PJ_A','3',148,'Ata','CAIXA','ATIVO',
                   'TEOR DO REGISTRO AQUI','MANUAL','2026-09-11T12:00:00')""")
    rid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'REGISTRO',67,148,'2011-12-23','TEOR DO REGISTRO AQUI',
                   'MANUAL','2026-09-11T12:00:00')""", (rid,))
    con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'AVERBACAO',1,374,'2026-09-11',
                   'CERTIFICO averbacao edital.','MANUAL','2026-09-11T15:00:00')""",
        (rid,))
    con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'AVERBACAO',2,375,'2026-09-11',
                   'CERTIFICO averbacao estatuto.','MANUAL','2026-09-11T15:00:00')""",
        (rid,))
    dados = CE.registro(con, "RCPJ_RTD", rid)
    teor = CE.montar_teor("RCPJ_RTD", dados)
    assert "TEOR DO REGISTRO AQUI" in teor
    assert "--- AVERBAÇÃO n. 374 ---" in teor
    assert "CERTIFICO averbacao edital." in teor
    assert "--- AVERBAÇÃO n. 375 ---" in teor
    assert "CERTIFICO averbacao estatuto." in teor


def test_recusa_sem_lavrante():
    with pytest.raises(CERT.CertidaoPdfError, match="nome"):
        CERT.gerar_pdf(
            numero=1, imagens=[_folha()], lavrante_nome="",
            lavrante_funcao="Escrevente")


def test_piso_capa_sem_frase_integrante():
    """Oficial: capa sem «parte integrante e inseparável…»."""
    corpo = CERT.MODELO_RCPJ_CERTIDAO_CAPA + CERT.MODELO_RTD_CERTIDAO_CAPA
    assert "integrante" not in corpo.lower()
    # Comentário de remoção pode existir no fonte; o piso não.
    src = Path(CERT.__file__).read_text(encoding="utf-8")
    vivos = [
        ln for ln in src.splitlines()
        if "integrante" in ln.lower()
        and not ln.lstrip().startswith("#")
        and "removid" not in ln.lower()
    ]
    assert vivos == [], vivos
    t = CERT.textos_prontos(
        numero=148, lavrante_nome="JEAN", lavrante_funcao="Oficial",
        denominacao="CAIXA", natureza="Ata", paginas=1, serie="PJ_A")
    assert "integrante" not in t["fecho"].lower()


def test_montar_teor_filtra_averbacoes_por_ato_ids():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_rg_schema(con)
    init_ri_schema(con)
    CE.init_atrib_certidao_schema(con)
    cur = con.execute(
        """INSERT INTO rg_registros(atribuicao, serie, volume, numero, natureza,
               requerente_nome, situacao, teor, origem, criado_em)
           VALUES (3,'PJ_A','3',148,'Ata','CAIXA','ATIVO',
                   'TEOR DO REGISTRO AQUI','MANUAL','2026-09-11T12:00:00')""")
    rid = int(cur.lastrowid)
    cur_reg = con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'REGISTRO',67,148,'2011-12-23','TEOR DO REGISTRO AQUI',
                   'MANUAL','2026-09-11T12:00:00')""", (rid,))
    id_registro = int(cur_reg.lastrowid)
    cur374 = con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'AVERBACAO',1,374,'2026-09-11',
                   'CERTIFICO averbacao edital.','MANUAL','2026-09-11T15:00:00')""",
        (rid,))
    id374 = int(cur374.lastrowid)
    cur375 = con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'AVERBACAO',2,375,'2026-09-11',
                   'CERTIFICO averbacao estatuto.','MANUAL','2026-09-11T15:00:00')""",
        (rid,))
    id375 = int(cur375.lastrowid)
    dados = CE.registro(con, "RCPJ_RTD", rid)
    # REGISTRO + averbação 374 marcados: inclui os dois, como sempre.
    teor = CE.montar_teor("RCPJ_RTD", dados, ato_ids=[id_registro, id374])
    assert "TEOR DO REGISTRO AQUI" in teor
    assert "--- AVERBAÇÃO n. 374 ---" in teor
    assert "CERTIFICO averbacao edital." in teor
    assert "AVERBAÇÃO n. 375" not in teor
    assert "estatuto" not in teor

    # **SÓ A 374, SEM O REGISTRO** — achado do oficial (11/09/2026): «apesar
    # de ter escolhido duas averbações para constar na certidão, foi
    # erroneamente como objeto o registro da assembleia de constituição».
    # Desmarcar o REGISTRO tem de tirar o corpo dele da certidão — o objeto
    # vira só a(s) averbação(ões) marcada(s).
    so_av = CE.montar_teor("RCPJ_RTD", dados, ato_ids=[id374])
    assert "TEOR DO REGISTRO AQUI" not in so_av
    assert "--- AVERBAÇÃO n. 374 ---" in so_av
    assert "CERTIFICO averbacao edital." in so_av
    assert "AVERBAÇÃO n. 375" not in so_av
    # E o objeto certificado precisa dizer que é averbação, e não «encontrei
    # o seguinte registro» (a frase que afirmava o objeto errado).
    assert "encontrei o seguinte registro" not in so_av.lower()
    assert "averbações" in so_av.lower()

    # **MESMO COM `modelo` PREENCHIDO** — achado do oficial em 12/09/2026,
    # depois do primeiro conserto: a certidão de produção CONTINUAVA
    # dizendo «encontrei o seguinte registro», porque `emitir()` sempre
    # busca um modelo no catálogo (`modelos_da_casa.corpo_de`), e sem
    # ajuste salvo em `mo_modelos` o catálogo devolve, como PISO, o texto
    # de SEMPRE (`MODELO_CERTIDAO_RCPJ_RTD`) — que chega aqui como
    # `modelo` já preenchido, e `modelo or MODELO_..._SO_AVERBACOES` nunca
    # alcançava o texto novo. Este teste simula exatamente isso: passa
    # `modelo` com o texto antigo, e exige que ele seja ignorado quando
    # `so_averbacoes` for o caso.
    so_av_com_modelo = CE.montar_teor(
        "RCPJ_RTD", dados, ato_ids=[id374], modelo=CE.MODELO_CERTIDAO_RCPJ_RTD)
    assert "encontrei o seguinte registro" not in so_av_com_modelo.lower(), (
        "um `modelo` vindo do catálogo (o piso de sempre) não pode "
        "sobrepor o texto de só-averbações — ele nunca foi escrito para "
        "este caso")
    assert "TEOR DO REGISTRO AQUI" not in so_av_com_modelo


def test_imagens_dos_atos_preferem_rg_ato_e_ordenam():
    from pathlib import Path as P
    import tempfile
    tmp = P(tempfile.mkdtemp())
    f1 = tmp / "a.png"; f1.write_bytes(b"x")
    f2 = tmp / "b.png"; f2.write_bytes(b"y")
    f3 = tmp / "c.png"; f3.write_bytes(b"z")
    # Touch as files that look like images — carregar_folhas needs real images;
    # aqui só testamos resolução de caminhos (is_file + extensão).
    atos = [
        {"id": 73, "tipo": "REGISTRO", "numero_ordem": 148},
        {"id": 75, "tipo": "AVERBACAO", "numero_ordem": 374},
        {"id": 76, "tipo": "AVERBACAO", "numero_ordem": 375},
    ]
    anexos_por_ato = {
        75: [{"id": 39, "stored_path": str(f1), "original_name": "01.pdf"}],
        76: [{"id": 40, "stored_path": str(f2), "original_name": "02.pdf"}],
    }
    anexos_reg = [
        {"id": 33, "stored_path": str(f3), "original_name": "folha.png",
         "description": ""},
        {"id": 37, "stored_path": str(f1), "original_name": "01.pdf",
         "description": ""},
    ]
    # Só 75 e 76 → ordem 75 depois 76; sem 73 (sem RG_ATO; fallback 73→33
    # só entra se 73 estiver selecionado).
    caminhos = CERT.imagens_dos_atos(
        [atos[1], atos[2]],
        anexos_por_ato=anexos_por_ato,
        anexos_registro=anexos_reg,
    )
    assert [c.name for c in caminhos] == ["a.png", "b.png"]

    # Com REGISTRO selecionado e sem RG_ATO: fallback 73→33
    caminhos2 = CERT.imagens_dos_atos(
        atos,
        anexos_por_ato={75: anexos_por_ato[75], 76: anexos_por_ato[76]},
        anexos_registro=anexos_reg,
    )
    assert [c.name for c in caminhos2] == ["c.png", "a.png", "b.png"]

    # Sem RG_ATO em nenhum: cai nos anexo_id
    caminhos3 = CERT.imagens_dos_atos(
        atos,
        anexos_por_ato={},
        anexos_registro=anexos_reg,
        anexo_ids_override=[33],
    )
    # Sem RG_ATO e sem fallback hit... wait, fallback still applies for 73/75/76
    # To test pure override, use atos without fallback ids
    caminhos4 = CERT.imagens_dos_atos(
        [{"id": 999, "tipo": "REGISTRO"}],
        anexos_por_ato={},
        anexos_registro=anexos_reg,
        anexo_ids_override=[33],
    )
    assert [c.name for c in caminhos4] == ["c.png"]


def test_emitir_grava_atos_ids():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_rg_schema(con)
    init_ri_schema(con)
    CE.init_atrib_certidao_schema(con)
    cur = con.execute(
        """INSERT INTO rg_registros(atribuicao, serie, volume, numero, natureza,
               requerente_nome, situacao, teor, origem, criado_em)
           VALUES (3,'PJ_A','3',148,'Ata','CAIXA','ATIVO',
                   'TEOR','MANUAL','2026-09-11T12:00:00')""")
    rid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'REGISTRO',67,148,'2011-12-23','TEOR','MANUAL',
                   '2026-09-11T12:00:00')""", (rid,))
    cur_av = con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'AVERBACAO',1,374,'2026-09-11','AV1','MANUAL',
                   '2026-09-11T15:00:00')""", (rid,))
    id_av = int(cur_av.lastrowid)
    r = CE.emitir(con, "RCPJ_RTD", rid, hoje="2026-09-11",
                  agora="2026-09-11T16:00:00", usuario="teste",
                  ato_ids=[id_av])
    row = CE.certidao(con, r["certidao_id"])
    assert row["atos_ids"]
    import json
    assert json.loads(row["atos_ids"]) == [id_av]
    assert "AV1" in row["teor"]


def test_quadro_emolumentos_usa_fundos_do_maranhao_e_nao_de_sp():
    """Achado do oficial (11/09/2026): «a tabela que está na certidão

    também não faz sentido pra o Maranhão, de emolumentos». O quadro
    nasceu com as categorias de SP (Estado, Secretaria da Fazenda,
    Registro Civil, Tribunal de Justiça, Ministério Público) — esta casa
    recolhe para FERC, FADEP, FEMP e FERRFIS, que é o que o resto do
    sistema já usa em toda custa.
    """
    chaves = {chave for chave, _ in CERT.CAMPOS_EMOL}
    assert chaves == {"emolumentos", "ferc", "fadep", "femp", "ferrfis",
                       "total"}
    for proibido in ("estado", "secretaria", "registro_civil", "tribunal",
                     "mp", "iss", "conducao", "outras"):
        assert proibido not in chaves, (
            f"{proibido!r} é categoria de SP, e não um fundo desta casa")


def test_primeira_folha_entra_na_capa_quando_ha_espaco():
    """Achado do oficial (11/09/2026): «precisamos fazer caber a primeira

    página dos atos já na primeira folha da certidão». Com capa curta,
    sobra espaço abaixo do quadro de emolumentos — a 1ª folha do documento
    entra ali, em vez de abrir uma página só para ela.
    """
    textos = CERT.textos_prontos(
        numero=148, lavrante_nome="JEAN", lavrante_funcao="Oficial",
        denominacao="CAIXA", natureza="Ata", paginas=1, serie="PJ_A")
    primeira = _folha((50, 50, 50))  # cinza escuro — fácil de detectar
    capa, colou = CERT.montar_capa(textos, primeira_folha=primeira)
    assert colou is True, "com capa curta, tinha de caber a 1ª folha"

    # Confirma que o cinza escuro da folha realmente foi colado (e não só
    # que a função devolveu True sem desenhar nada).
    achou_escuro = False
    for y in range(300, CERT.A4_H - 200, 10):
        if capa.getpixel((CERT.A4_W // 2, y))[0] < 100:
            achou_escuro = True
            break
    assert achou_escuro, "a imagem da 1ª folha não apareceu de verdade na capa"


def test_primeira_folha_nao_colada_sem_espaco_suficiente():
    """Sem espaço (capa longa), a 1ª folha cai para a página interna de

    sempre — nunca se força um encaixe que cortaria a imagem.
    """
    # `denominacao`/`natureza` desenham uma LINHA por `\n` (sem quebra
    # automática) — muitas linhas é o que de fato consome altura da capa.
    texto_longo = "\n".join(["linha bem comprida de denominação"] * 40)
    textos = CERT.textos_prontos(
        numero=148, lavrante_nome="JEAN", lavrante_funcao="Oficial",
        denominacao=texto_longo, natureza=texto_longo, paginas=1, serie="PJ_A")
    _, colou = CERT.montar_capa(textos, primeira_folha=_folha())
    assert colou is False


def test_sem_emolumentos_nenhum_quadro_e_desenhado():
    """Pedido do oficial (12/09/2026): «retire a tabela». A rota que emite

    a certidão passou a chamar `com_emolumentos=False` — este teste prende
    o comportamento de `montar_capa` que faz isso funcionar: com a flag
    desligada, nenhuma linha do quadro é desenhada.
    """
    textos = CERT.textos_prontos(
        numero=148, lavrante_nome="JEAN", lavrante_funcao="Oficial",
        denominacao="CAIXA", natureza="Ata", paginas=1, serie="PJ_A")
    com_quadro, _ = CERT.montar_capa(textos, com_emolumentos=True)
    sem_quadro, _ = CERT.montar_capa(textos, com_emolumentos=False)

    def _pixels_pretos(im) -> int:
        # Tudo o mais (cabeçalho/título/corpo/denominação/fecho) é igual
        # nas duas capas — a única diferença possível de pixel preto é o
        # quadro de emolumentos (retângulos com outline="black").
        return sum(
            1 for x in range(CERT.SIDE, CERT.A4_W - CERT.SIDE, 4)
            for y in range(0, CERT.A4_H, 4)
            if im.getpixel((x, y)) == (0, 0, 0))

    assert _pixels_pretos(com_quadro) > _pixels_pretos(sem_quadro), (
        "sem com_emolumentos, a capa não pode ter mais pixel preto que "
        "sem o quadro — «retire a tabela» pedia exatamente isso")


def _selo_de_teste(numero="CERTID000000TESTECARIMBO0001"):
    return {
        "numero": numero,
        "texto": (f"Poder Judiciário – TJMA. Selo: {numero}, "
                  "12/09/2026 00:03:39, Ato: 15.10.1, Parte(s): TESTE, "
                  "Total R$ 53,58 Emol R$ 47,84 FERC R$ 1,44 FADEP R$ 1,91 "
                  "FEMP R$ 1,91 FERRFIS R$ 0,48 Consulte em "
                  "https://selo.tjma.jus.br"),
        "qr_texto": numero,
    }


def test_selo_real_aparece_na_capa_e_nao_a_moldura_vazia():
    """Achado do oficial (12/09/2026): «segue sem selo a certidão que

    emiti». O selo saía certo no banco — só nunca tinha como chegar ao
    PDF visual, que sempre desenhava a moldura tracejada («selo /
    verificação», «QR / autenticação»), mesmo com a certidão já selada.
    """
    textos = CERT.textos_prontos(
        numero=148, lavrante_nome="JEAN", lavrante_funcao="Oficial",
        denominacao="CAIXA", natureza="Ata", paginas=1, serie="PJ_A")
    sem_selo, _ = CERT.montar_capa(textos)
    com_selo, _ = CERT.montar_capa(textos, selo=_selo_de_teste())

    # Varre o rodapé inteiro (onde a área do selo sempre fica) procurando
    # pixel escuro — mais robusto que acertar a coordenada exata do QR.
    def _pixels_escuros_no_rodape(im) -> int:
        return sum(
            1 for x in range(CERT.SIDE, CERT.A4_W - CERT.SIDE, 3)
            for y in range(CERT.A4_H - 220, CERT.A4_H - 10, 3)
            if im.getpixel((x, y))[0] < 150)

    escuros_sem = _pixels_escuros_no_rodape(sem_selo)
    escuros_com = _pixels_escuros_no_rodape(com_selo)
    assert escuros_com > escuros_sem, (
        f"com selo real, o rodapé tinha de ter mais pixel escuro (número/QR "
        f"desenhados): sem={escuros_sem} com={escuros_com}")


def test_objeto_certificado_aparece_no_corpo_e_na_faixa():
    """Achado do oficial (12/09/2026): «no PDF precisa arrumar a parte

    introdutória, não está com os dados do serviço efetivo de certidão
    de averbações e o cabeçalho que fica em cima de todas páginas também
    precisa acompanhar isso». O corpo da capa e a faixa de toda folha
    interna sempre descreviam o REGISTRO original — `objeto_certificado`
    é o que a rota manda quando a certidão é, de fato, sobre averbações.
    """
    t_padrao = CERT.textos_prontos(
        numero=148, lavrante_nome="JEAN", lavrante_funcao="Oficial",
        denominacao="CAIXA", natureza="Ata de constituição", paginas=1,
        serie="PJ_A")
    assert "o registro de Ata de constituição" in t_padrao["corpo"]
    assert "o registro de Ata de constituição" in t_padrao["faixa"]

    t_averb = CERT.textos_prontos(
        numero=148, lavrante_nome="JEAN", lavrante_funcao="Oficial",
        denominacao="CAIXA", natureza="Ata de constituição", paginas=1,
        serie="PJ_A",
        objeto_certificado=("a(s) averbação(ões) nº 378 (Ata de Assembleia "
                            "Geral Extraordinária)"))
    assert "a(s) averbação(ões) nº 378" in t_averb["corpo"]
    assert "a(s) averbação(ões) nº 378" in t_averb["faixa"]
    assert "o registro de Ata de constituição" not in t_averb["corpo"]
    assert "o registro de Ata de constituição" not in t_averb["faixa"]

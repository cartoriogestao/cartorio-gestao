"""
Testes da biblioteca de modelos do Tabelionato de Notas.

O QUE ESTES TESTES DEFENDEM
    A regra do art. 795, § 2º, do Codigo de Normas — escrituracao seguida, sem
    claros ou espacos em branco — e os requisitos essenciais que, faltando,
    tornam o ato defeituoso na forma.

    Sao testes de FORMA, nao de merito. Nenhum deles substitui a leitura do
    tabeliao: a qualificacao do ato e indelegavel.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import notas_modelos as NM                       # noqa: E402
from notas_schema import init_notas_schema        # noqa: E402
from ri_modelos_atos import campos_do_modelo, preencher   # noqa: E402


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")      # como a producao
    init_notas_schema(con)
    return con


def limpo(texto: str) -> str:
    return re.sub(r"<[^>]+>", "", texto)


# ------------------------------------------------- texto corrido, sem claros

def test_nenhum_modelo_tem_quebra_de_linha():
    # Art. 795, § 2º: a escrituracao deve ser seguida. Quebra de linha no corpo
    # vira claro no papel.
    for m in NM.MODELOS:
        assert "\n" not in m["corpo"], m["codigo"]


def test_nenhum_modelo_tem_espaco_duplo_nem_espaco_antes_de_pontuacao():
    for m in NM.MODELOS:
        assert "  " not in m["corpo"], m["codigo"]
        assert not re.search(r"\s[,.;:]", m["corpo"]), m["codigo"]


def test_a_clausula_que_sai_nao_deixa_buraco():
    # E o caso que motiva `texto_corrido`: sem ele, a clausula condicional
    # removida deixa o espaco que a cercava.
    m = NM.por_codigo("NT-ESC-DOACAO")
    saida = NM.texto_corrido(preencher(m, {}))
    assert "  " not in saida
    assert not re.search(r"\s[,.;:]", saida)
    assert "«" not in saida and "»" not in saida


def test_texto_corrido_fecha_os_claros_conhecidos():
    assert NM.texto_corrido("um  dois") == "um dois"
    assert NM.texto_corrido("palavra , frase") == "palavra, frase"
    assert NM.texto_corrido("linha\n  seguinte") == "linha seguinte"
    assert NM.texto_corrido("<p>  texto  </p>") == "<p>texto</p>"
    assert NM.texto_corrido("frase. . outra") == "frase. outra"


def test_claros_restantes_acusa_o_que_falta():
    m = NM.por_codigo("NT-PROC-PUBLICA")
    faltando = NM.claros_restantes(preencher(m, {}))
    assert faltando, "modelo sem marcador nenhum não pode ser"
    assert any("DIA POR EXTENSO" in x for x in faltando)


# --------------------------------------------- a tecnica que a norma exige

def test_data_e_numeros_saem_por_extenso_com_repeticao_em_algarismos():
    # Art. 795, § 4º: a data e os numeros de dimensao ou quantidade por extenso,
    # com repeticao em algarismos.
    for m in NM.MODELOS:
        corpo = m["corpo"]
        assert "[DIA POR EXTENSO] ([DIA EM ALGARISMOS])" in corpo, m["codigo"]
        assert "[ANO POR EXTENSO] ([ANO EM ALGARISMOS])" in corpo, m["codigo"]


def test_o_preco_sai_por_extenso_e_em_algarismos():
    for codigo in ("NT-ESC-COMPRA-VENDA", "NT-ESC-COMPRA-VENDA-RURAL"):
        corpo = NM.por_codigo(codigo)["corpo"]
        assert "[PREÇO POR EXTENSO] ([PREÇO EM ALGARISMOS])" in corpo, codigo


def test_a_ata_notarial_registra_a_hora():
    # Art. 847, § 1º, I: local, data da lavratura E HORA.
    for codigo in ("NT-ATA-NOTARIAL", "NT-ATA-USUCAPIAO", "NT-ATA-ADJUDICACAO",
                   "NT-TESTAMENTO-PUBLICO"):
        corpo = NM.por_codigo(codigo)["corpo"]
        assert "[HORA POR EXTENSO] ([HORA EM ALGARISMOS])" in corpo, codigo
        assert "ENCERRAMENTO" in corpo, codigo


def test_todo_modelo_declara_a_leitura():
    # CC, art. 215, § 1º, e art. 1.864, II. Ato que nao registra a leitura tem
    # defeito de forma.
    for m in NM.MODELOS:
        assert re.search(r"\bli\b.{0,40}voz alta|leu|lida|lido", limpo(m["corpo"]), re.I), \
            m["codigo"]


# ------------------------------------------------- o que a lei nao perdoa

def test_o_testamento_traz_os_tres_requisitos_essenciais():
    # CC, art. 1.864: escrito pelo tabeliao conforme as declaracoes; lido em voz
    # alta ao testador E A DUAS TESTEMUNHAS A UM SO TEMPO; assinado em seguida
    # pelo testador, pelas testemunhas e pelo tabeliao.
    corpo = limpo(NM.por_codigo("NT-TESTAMENTO-PUBLICO")["corpo"])
    assert "1.864, I" in corpo
    assert "DUAS TESTEMUNHAS, A UM SÓ TEMPO" in corpo
    assert "1.864, II" in corpo
    assert "1.864, III" in corpo


def test_o_testamento_cobre_o_cego_o_surdo_e_quem_nao_assina():
    corpo = limpo(NM.por_codigo("NT-TESTAMENTO-PUBLICO")["corpo"])
    assert "1.867" in corpo and "DUAS VEZES" in corpo      # cego
    assert "1.866" in corpo                                # surdo
    assert "1.865" in corpo                                # nao assina


def test_o_testamento_avisa_da_legitima_e_exige_justa_causa():
    m = NM.por_codigo("NT-TESTAMENTO-PUBLICO")
    corpo = limpo(m["corpo"])
    assert "1.846" in corpo                                # legitima
    assert "1.848" in corpo and "JUSTA CAUSA" in corpo
    requisitos = " ".join(m["requisitos"])
    assert "1.801" in requisitos                           # testemunha impedida
    assert "RCTO" in requisitos                            # remessa obrigatoria


def test_o_testamento_nao_vai_a_cep():
    # A CEP recebe escrituras, procuracoes e atas — testamento so no RCTO.
    m = NM.por_codigo("NT-TESTAMENTO-PUBLICO")
    assert m.get("tipo_ato_cep") is None
    assert m.get("tipo_testamento") == 4


def test_poderes_especiais_da_procuracao_sao_expressos():
    # CC, art. 661, § 1º: alienar, gravar, transigir e afins nao se presumem.
    corpo = limpo(NM.por_codigo("NT-PROC-PUBLICA")["corpo"])
    assert "661" in corpo
    assert "não se presumem" in corpo


def test_procuracao_para_alienar_imovel_exige_a_certidao_do_art_833():
    m = NM.por_codigo("NT-PROC-PUBLICA")
    assert "833" in limpo(m["corpo"])
    assert any("833" in r for r in m["requisitos"])


def test_revogacao_de_mandato_adverte_sobre_a_notificacao():
    # CN, art. 831, § 2º, e CC, arts. 683 e 686.
    corpo = limpo(NM.por_codigo("NT-REVOGACAO-MANDATO")["corpo"])
    assert "IMPRESCINDÍVEL notificar" in corpo
    assert "686" in corpo and "683" in corpo


def test_substabelecimento_distingue_com_e_sem_reserva():
    corpo = limpo(NM.por_codigo("NT-SUBSTABELECIMENTO")["corpo"])
    assert "COM reserva" in corpo and "SEM reserva" in corpo
    assert "667" in corpo


def test_imovel_rural_transcreve_o_ccir_e_o_itr():
    m = NM.por_codigo("NT-ESC-COMPRA-VENDA-RURAL")
    corpo = limpo(m["corpo"])
    assert "Certificado de Cadastro de Imóvel Rural" in corpo
    assert "802, § 5º" in corpo
    assert "Territorial Rural" in corpo
    assert any("SOB PENA DE NULIDADE" in r for r in m["requisitos"])


def test_a_ata_de_usucapiao_nao_declara_a_propriedade():
    # A ata atesta o tempo de posse. Quem reconhece a usucapiao e o registrador.
    m = NM.por_codigo("NT-ATA-USUCAPIAO")
    corpo = limpo(m["corpo"])
    assert "ATESTA O TEMPO DE POSSE, e não declara a propriedade" in corpo
    assert "216-A" in corpo


def test_a_ata_de_adjudicacao_exige_quitacao_notificacao_e_inercia():
    m = NM.por_codigo("NT-ATA-ADJUDICACAO")
    corpo = limpo(m["corpo"])
    for exigencia in ("QUITAÇÃO", "NOTIFICAÇÃO", "INÉRCIA",
                      "INEXISTÊNCIA DE LITÍGIO"):
        assert exigencia in corpo, exigencia
    assert "216-B" in corpo


def test_a_doacao_lembra_da_legitima_e_da_subsistencia():
    m = NM.por_codigo("NT-ESC-DOACAO")
    corpo = limpo(m["corpo"])
    assert "548 e 549" in corpo
    assert "1.848" in corpo


# --------------------------------------------------------- contra o banco

def test_instalar_e_repetivel():
    con = banco()
    agora = "2026-08-15T09:00:00"
    primeira = NM.instalar(con, agora)
    con.commit()
    assert primeira["novos"] == len(NM.MODELOS)

    segunda = NM.instalar(con, agora)
    con.commit()
    assert segunda["novos"] == 0
    assert segunda["ja_existentes"] == len(NM.MODELOS)
    assert con.execute("SELECT COUNT(*) FROM nt_modelos").fetchone()[0] == len(NM.MODELOS)


def test_instalar_nao_desfaz_o_que_a_serventia_editou():
    # `atualizado_em` É A MARCA DE QUE UMA TELA GRAVOU POR CIMA — não há
    # tela hoje que edite `nt_modelos.corpo`, mas o dia em que ela existir
    # tem de gravar esta coluna: é o que faz `instalar()` parar de tocar na
    # linha. Sem isso, o teste simularia uma edição que nenhum caminho real
    # produz.
    con = banco()
    agora = "2026-08-15T09:00:00"
    NM.instalar(con, agora)
    con.execute("UPDATE nt_modelos SET corpo='<p>texto da serventia</p>', "
                "atualizado_em=? WHERE codigo='NT-PROC-PUBLICA'", (agora,))
    con.commit()

    NM.instalar(con, agora)
    con.commit()
    corpo = con.execute("SELECT corpo FROM nt_modelos WHERE codigo='NT-PROC-PUBLICA'"
                        ).fetchone()[0]
    assert corpo == "<p>texto da serventia</p>"


def test_instalar_ATUALIZA_o_que_ninguem_editou():
    """O defeito real de 07/09/2026: o código da escritura mudou, a linha da
    instalação de agosto continuou com o texto velho, e nada além da carga
    do acervo — que ninguém ia repetir — chamava `instalar()` de novo.
    `atualizado_em` seguia NULL (nenhuma tela grava nela hoje), e é essa a
    marca que autoriza o código a corrigir a própria linha."""
    con = banco()
    NM.instalar(con, "2026-08-15T09:00:00")
    con.execute("UPDATE nt_modelos SET corpo='<p>texto de fábrica de um mês atrás</p>' "
                "WHERE codigo='NT-ESC-COMPRA-VENDA-RURAL'")
    con.commit()

    resultado = NM.instalar(con, "2026-09-07T00:00:00")
    con.commit()

    assert resultado["atualizados"] == 1
    corpo = con.execute(
        "SELECT corpo FROM nt_modelos WHERE codigo='NT-ESC-COMPRA-VENDA-RURAL'"
    ).fetchone()[0]
    assert corpo == NM.por_codigo("NT-ESC-COMPRA-VENDA-RURAL")["corpo"]


def test_o_modelo_guarda_a_central_certa():
    con = banco()
    NM.instalar(con, "2026-08-15T09:00:00")
    con.commit()
    linhas = {r["codigo"]: r for r in con.execute(
        "SELECT codigo, central_censec, tipo_ato_censec, tipo_testamento "
        "FROM nt_modelos")}
    assert linhas["NT-TESTAMENTO-PUBLICO"]["central_censec"] == "RCTO"
    assert linhas["NT-TESTAMENTO-PUBLICO"]["tipo_testamento"] == 4
    assert linhas["NT-ESC-COMPRA-VENDA"]["central_censec"] == "CEP"
    assert linhas["NT-ESC-COMPRA-VENDA"]["tipo_ato_censec"] == 1
    assert linhas["NT-PROC-PUBLICA"]["tipo_ato_censec"] == 2


# ------------------------------------------- família, sucessões e a CESDI

def test_todo_modelo_da_cesdi_usa_um_tipo_que_a_central_conhece():
    # Liga o modelo ao layout: tipo fora do dominio faz a carga ser recusada.
    import notas_censec as NC
    for m in NM.MODELOS:
        if m.get("tipo_cesdi"):
            assert m["tipo_cesdi"] in NC.TIPO_ATO_CESDI, m["codigo"]
            assert m["tipo_cesdi"] in NC.MINIMO_PARTES_CESDI, m["codigo"]
            # Ato da CESDI nao vai tambem a CEP.
            assert m.get("tipo_ato_cep") is None, m["codigo"]
            assert m.get("natureza_censec") is None, m["codigo"]


def test_os_atos_da_cesdi_pedem_advogado_no_proprio_texto():
    # CN, arts. 808, § 1º, 819 e 822, § 5º: sem advogado o tabeliao nao lavra, e
    # a CESDI exige a parte Advogado no minimo de partes.
    import notas_censec as NC
    for m in NM.MODELOS:
        if not m.get("tipo_cesdi"):
            continue
        _, exigidas = NC.MINIMO_PARTES_CESDI[m["tipo_cesdi"]]
        if "Advogado" in exigidas:
            assert "OAB" in limpo(m["corpo"]), m["codigo"]
            assert any("advogado" in r.lower() for r in m["requisitos"]), m["codigo"]


def test_divorcio_e_separacao_trazem_casamento_regime_e_nome():
    # A CESDI exige dataCasamento e regimeBens nos tipos 1, 3 e 4, e o art. 822
    # do Codigo de Normas manda dispor sobre partilha, alimentos e nome.
    for codigo in ("NT-ESC-DIVORCIO", "NT-ESC-SEPARACAO",
                   "NT-ESC-CONVERSAO-DIVORCIO"):
        corpo = limpo(NM.por_codigo(codigo)["corpo"])
        assert "[DATA DO CASAMENTO]" in corpo, codigo
        assert "[REGIME DE BENS]" in corpo, codigo
        assert "PENSÃO ALIMENTÍCIA" in corpo or "ALIMENTOS" in corpo, codigo
        assert "DO NOME" in corpo, codigo


def test_filho_incapaz_barra_guarda_visitacao_e_alimentos():
    # CN, art. 822, § 1º, com a redacao do Provimento 23/2024: pode lavrar, mas
    # e VEDADA previsao sobre guarda, visitacao e alimentos desses filhos, e a
    # escritura consigna o compromisso de levar a questao ao Judiciario.
    for codigo in ("NT-ESC-DIVORCIO", "NT-ESC-SEPARACAO",
                   "NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL"):
        corpo = limpo(NM.por_codigo(codigo)["corpo"])
        assert "NÃO CONTÉM E NÃO PODE CONTER" in corpo, codigo
        assert "guarda, visitação e alimentos" in corpo, codigo
        assert "PODER JUDICIÁRIO" in corpo, codigo


def test_a_separacao_avisa_que_nao_dissolve_o_vinculo():
    corpo = limpo(NM.por_codigo("NT-ESC-SEPARACAO")["corpo"])
    assert "NÃO O VÍNCULO MATRIMONIAL" in corpo
    assert "novo casamento" in corpo


def test_a_conversao_dispensa_a_certidao_do_processo():
    # CN, art. 830: basta a certidao da averbacao da separacao no assento.
    m = NM.por_codigo("NT-ESC-CONVERSAO-DIVORCIO")
    assert "averbação da separação" in limpo(m["corpo"])
    assert any("DISPENSAVEL" in r for r in m["requisitos"])


def test_o_restabelecimento_orienta_anota_e_comunica():
    # CN, art. 829, I, II e III.
    m = NM.por_codigo("NT-ESC-RESTABELECIMENTO")
    corpo = limpo(m["corpo"])
    assert "NECESSIDADE DE APRESENTAR O TRASLADO" in corpo      # inciso I
    assert "anotação" in corpo                                  # inciso II
    assert "juízo da separação judicial" in corpo               # inciso III


def test_a_cessao_hereditaria_avisa_das_dividas_do_espolio():
    # CN, art. 803: o tabeliao DEVE cientificar o adquirente e consignar no ato.
    m = NM.por_codigo("NT-ESC-CESSAO-HEREDITARIA")
    corpo = limpo(m["corpo"])
    assert "DÍVIDAS DO ESPÓLIO" in corpo
    assert "limite das forças da herança" in corpo
    assert "1.795" in corpo                                     # preferencia
    assert any("ANULAVEL" in r for r in m["requisitos"])        # outorga uxoria


def test_a_cessao_de_bem_individualizado_nao_entra_no_registro():
    # CN, art. 805: o titulo nao e habil ate que se faca a partilha.
    corpo = limpo(NM.por_codigo("NT-ESC-CESSAO-HEREDITARIA")["corpo"])
    assert "NÃO É HÁBIL" in corpo and "até que seja feita a partilha" in corpo


def test_o_inventario_segue_a_ordem_por_titulos_do_art_812():
    # A ordem nao e gosto: e o art. 812 do Codigo de Normas.
    corpo = limpo(NM.por_codigo("NT-ESC-INVENTARIO-PARTILHA")["corpo"])
    ordem = ["DO AUTOR DA HERANÇA", "DO ÓBITO", "DA INEXISTÊNCIA DE TESTAMENTO",
             "DO CÔNJUGE SUPÉRSTITE", "DOS HERDEIROS",
             "DA NOMEAÇÃO DE INVENTARIANTE", "DOS ADVOGADOS", "DOS BENS IMÓVEIS",
             "DOS LITÍGIOS", "DAS DÍVIDAS", "DAS RENÚNCIAS E CESSÕES",
             "DA PARTILHA", "DAS CERTIDÕES E DOCUMENTOS APRESENTADOS",
             "DOS IMPOSTOS PAGOS", "DAS DECLARAÇÕES FINAIS"]
    posicoes = [corpo.find(t) for t in ordem]
    assert all(p >= 0 for p in posicoes), [t for t, p in zip(ordem, posicoes) if p < 0]
    assert posicoes == sorted(posicoes), "os títulos saíram fora da ordem do art. 812"


def test_o_inventario_exige_a_certidao_da_censec_e_a_declaracao():
    # CN, art. 811, X e XI: as duas coisas, e nao uma delas.
    m = NM.por_codigo("NT-ESC-INVENTARIO-PARTILHA")
    corpo = limpo(m["corpo"])
    assert "CENSEC" in corpo
    assert "não deixou testamento" in corpo and "SOB AS PENAS DA LEI" in corpo
    assert any("Ministerio Publico" in r or "Ministério Público" in r
               for r in m["requisitos"])


def test_a_nomeacao_de_inventariante_avisa_que_nao_substitui_o_inventario():
    corpo = limpo(NM.por_codigo("NT-ESC-NOMEACAO-INVENTARIANTE")["corpo"])
    assert "NÃO SUBSTITUI o inventário" in corpo
    assert "NÃO CONSTITUI título hábil" in corpo


def test_a_uniao_estavel_cai_na_comunhao_parcial_por_omissao():
    # CC, art. 1.725: nao havendo contrato escrito, comunhao parcial.
    corpo = limpo(NM.por_codigo("NT-ESC-UNIAO-ESTAVEL")["corpo"])
    assert "COMUNHÃO PARCIAL" in corpo and "1.725" in corpo


# ------------------------------------------------- garantia, dívida e mais

def test_a_hipoteca_traz_os_quatro_itens_da_especializacao():
    # CC, art. 1.424: sem valor, prazo, juros e bem especificado, a garantia
    # nao vale.
    m = NM.por_codigo("NT-ESC-HIPOTECA")
    corpo = limpo(m["corpo"])
    assert "[VALOR DA DÍVIDA POR EXTENSO]" in corpo
    assert "TAXA DE JUROS" in corpo
    assert "PRAZO DA HIPOTECA POR EXTENSO" in corpo
    assert any("1.424" in r for r in m["requisitos"])


def test_a_hipoteca_recusa_o_pacto_comissorio():
    # CC, art. 1.428: e nula a clausula que autoriza o credor a ficar com o
    # imovel. O modelo diz isso no proprio ato, no lugar onde alguem tentaria
    # escrever o contrario.
    corpo = limpo(NM.por_codigo("NT-ESC-HIPOTECA")["corpo"])
    assert "1.428" in corpo
    assert "É NULA a cláusula" in corpo


def test_a_alienacao_fiduciaria_traz_os_sete_incisos_do_art_24():
    # Lei 9.514/1997, art. 24. Faltando um, a propriedade fiduciaria nao se
    # constitui.
    m = NM.por_codigo("NT-ESC-ALIENACAO-FIDUCIARIA")
    corpo = limpo(m["corpo"])
    for titulo in ("DO PRINCIPAL DA DÍVIDA", "DO PRAZO E DAS CONDIÇÕES",
                   "DA TAXA DE JUROS E DOS ENCARGOS",
                   "DA CONSTITUIÇÃO DA PROPRIEDADE FIDUCIÁRIA",
                   "DA LIVRE UTILIZAÇÃO PELO FIDUCIANTE",
                   "DO VALOR DO IMÓVEL PARA LEILÃO",
                   "DO PROCEDIMENTO EM CASO DE INADIMPLEMENTO"):
        assert titulo in corpo, titulo
    assert "QUINZE DIAS" in corpo and "PÚBLICO LEILÃO" in corpo
    assert any("art. 24" in r for r in m["requisitos"])


def test_a_dacao_avisa_do_efeito_da_evicao():
    # CC, art. 359: evicto o credor, restabelece-se a obrigacao primitiva e a
    # quitacao fica sem efeito.
    corpo = limpo(NM.por_codigo("NT-ESC-CONFISSAO-DACAO")["corpo"])
    assert "359" in corpo and "RESTABELECER-SE-Á a obrigação primitiva" in corpo
    assert "357" in corpo          # rege-se pela compra e venda


def test_a_permuta_divide_as_despesas_e_protege_o_descendente():
    # CC, art. 533, I e II.
    corpo = limpo(NM.por_codigo("NT-ESC-PERMUTA")["corpo"])
    assert "533, I" in corpo and "partes iguais" in corpo
    assert "533, II" in corpo


def test_a_quitacao_traz_os_requisitos_do_art_320():
    # Valor e especie da divida, nome de quem pagou, tempo e lugar do pagamento.
    m = NM.por_codigo("NT-ESC-QUITACAO")
    corpo = limpo(m["corpo"])
    assert "[VALOR DA DÍVIDA POR EXTENSO]" in corpo
    assert "[ESPÉCIE E ORIGEM DA DÍVIDA]" in corpo
    assert "[DATA DO PAGAMENTO]" in corpo and "[LUGAR DO PAGAMENTO]" in corpo
    assert any("320" in r for r in m["requisitos"])


def test_o_distrato_se_faz_pela_mesma_forma_do_contrato():
    m = NM.por_codigo("NT-ESC-DISTRATO")
    assert "472" in limpo(m["corpo"])
    assert any("MESMA FORMA" in r for r in m["requisitos"])


def test_a_emancipacao_so_vale_depois_do_registro():
    # Lei 6.015/73, arts. 89 a 91. O ato notarial sozinho nao emancipa.
    m = NM.por_codigo("NT-ESC-EMANCIPACAO")
    corpo = limpo(m["corpo"])
    assert "SOMENTE PRODUZIRÁ EFEITO DEPOIS DE REGISTRADA" in corpo
    assert "Livro E" in corpo
    assert any("DEZESSEIS ANOS" in r for r in m["requisitos"])


def test_o_pacto_antenupcial_avisa_das_tres_nulidades():
    # CC, arts. 1.653, 1.655 e 1.657: ineficaz sem casamento, nulo se contraria
    # lei, sem efeito contra terceiros sem registro.
    corpo = limpo(NM.por_codigo("NT-ESC-PACTO-ANTENUPCIAL")["corpo"])
    assert "INEFICAZ SE NÃO LHE SEGUIR O CASAMENTO" in corpo and "1.653" in corpo
    assert "1.655" in corpo
    assert "1.657" in corpo and "PERANTE TERCEIROS" in corpo


def test_a_dav_comunica_ao_rcduv():
    # CN, art. 880: comunicacao obrigatoria, gratuita e sigilosa.
    m = NM.por_codigo("NT-ESC-DIRETIVAS-VONTADE")
    corpo = limpo(m["corpo"])
    assert "880" in corpo
    assert "OBRIGATÓRIA" in corpo and "GRATUITA E SIGILOSA" in corpo
    assert "Registro Central de Disposições de Última Vontade" in corpo


def test_o_rcduv_esta_nas_centrais_mas_nao_nas_que_tem_remessa_pronta():
    # Existe e obriga a serventia; a carga ainda nao foi construida. Manter as
    # duas listas separadas evita a tela oferecer um botao que geraria arquivo
    # em branco.
    from notas_schema import CENTRAIS, CENTRAIS_COM_REMESSA
    assert "RCDUV" in CENTRAIS
    assert "RCDUV" not in CENTRAIS_COM_REMESSA
    assert set(CENTRAIS_COM_REMESSA) <= set(CENTRAIS)


def test_o_usufruto_nao_se_transfere_por_alienacao():
    # CC, art. 1.393: so o exercicio pode ser cedido.
    m = NM.por_codigo("NT-ESC-USUFRUTO")
    corpo = limpo(m["corpo"])
    assert "NÃO SE TRANSFERE por alienação" in corpo and "1.393" in corpo
    assert "1.411" in corpo         # acrescimo ao sobrevivente
    assert any("1.410, III" in r for r in m["requisitos"])


def test_todo_modelo_tem_campo_para_preencher():
    for m in NM.MODELOS:
        campos = campos_do_modelo(m)
        assert campos, m["codigo"]

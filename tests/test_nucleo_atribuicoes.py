"""
O vocabulario das seis atribuicoes e a geometria do livro.

POR QUE ESTES TESTES EXISTEM
    `atribuicoes.py` e `livro_nucleo.py` nao gravam nada e nao tem tela — sao a
    base sobre a qual RCPN, Protesto, RCPJ e RTD vao ser construidos. Um erro
    aqui nao aparece como defeito: aparece como quatro modulos concordando na
    coisa errada.

    Cada teste abaixo prende um fato do acervo do E-Oficio ou uma exigencia da
    inspecao de 12/08/2026. Se alguem reescrever o gerador e o numero mudar, o
    teste cai — que e exatamente o que se quer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import atribuicoes as ATR      # noqa: E402
import livro_nucleo as LN      # noqa: E402


# ============================================================ atribuicoes


def test_as_seis_atribuicoes_com_os_codigos_do_tribunal():
    assert {k: v["sigla"] for k, v in ATR.ATRIBUICOES.items()} == {
        1: "NOTAS", 2: "PROTESTO", 3: "RCPJ", 4: "RTD", 5: "RI", 6: "RCPN"}


def test_o_catalogo_de_atos_tem_o_que_o_acervo_tinha():
    assert len(ATR.ATOS) == 72, "73 linhas no acervo, uma delas repetida"
    esperado = {"NOTAS": 18, "PROTESTO": 10, "RCPJ": 14, "RTD": 9, "RI": 16, "RCPN": 5}
    for sigla, quantos in esperado.items():
        assert len(ATR.atos_da(sigla, so_liberados=False)) == quantos, sigla


def test_os_dois_atos_desativados_continuam_desativados():
    """No acervo: Apostila de Haia no Protesto e Certidao Unificada."""
    bloqueados = {k for k, v in ATR.ATOS.items() if not v["liberado"]}
    assert bloqueados == {101, 106}
    assert 101 not in ATR.atos_da("PROTESTO")
    assert len(ATR.atos_da("PROTESTO")) == 8


@pytest.mark.parametrize("codigo,sigla", [
    (110, "PROTESTO"), (214, "NOTAS"), (323, "RCPJ"), (305, "RTD"),
    (416, "RI"), (502, "RCPN"),
])
def test_cada_ato_sabe_de_que_atribuicao_e(codigo, sigla):
    assert ATR.ato(codigo)["atribuicao_sigla"] == sigla


def test_todo_ato_resolve_para_selo_eletronico():
    """A armadilha dos dois espacos de codigo.

    67 atos gravaram o codigo do CADASTRO de selo (10); os cinco do RCPN
    gravaram o TIPO (20). Sem o alias, esses cinco sairiam sem tipo de selo — e
    a inspecao ja apontou exatamente isso no Livro C.
    """
    for codigo in ATR.ATOS:
        a = ATR.ato(codigo)
        assert a["eletronico"] is True, f"ato {codigo} não resolveu para selo eletrônico"
        assert a["tipo_selo"] == ATR.SELO_ELETRONICO
        assert a["tipo_selo_nome"] == "Selo Eletrônico"


def test_os_cinco_atos_do_rcpn_sao_os_que_gravaram_o_tipo_no_lugar_do_codigo():
    assert {k for k, v in ATR.ATOS.items() if v["selo"] == 20} == {501, 502, 503, 504, 505}
    assert {k for k, v in ATR.ATOS.items() if v["selo"] == 10} == set(ATR.ATOS) - {
        501, 502, 503, 504, 505}


def test_os_conflitos_do_acervo_ficam_registrados_e_nao_escondidos():
    codigos = {c["codigo"] for c in ATR.CONFLITOS_NO_ACERVO}
    assert 305 in codigos, "o código repetido entre RTD e RCPJ tem de ficar dito"
    assert 501 in codigos, "o tipo gravado no lugar do código tem de ficar dito"
    for c in ATR.CONFLITOS_NO_ACERVO:
        assert c["observacao"], "conflito sem explicação é conflito que ninguém entende"


def test_ato_desconhecido_levanta_erro_em_vez_de_devolver_vazio():
    with pytest.raises(KeyError):
        ATR.ato(99999)
    with pytest.raises(KeyError):
        ATR.atos_da("CARTORIO_INVENTADO")


def test_os_cinco_fundos_do_maranhao_com_os_percentuais_do_acervo():
    assert {f["sigla"]: f["percentual"] for f in ATR.FUNDOS} == {
        "FERC": 3, "FEMP": 4, "FADP": 4, "ISS": 5, "FERRFIS": 1}


@pytest.mark.parametrize("escrito,sigla", [
    ("FADEP", "FADP"), ("FADP", "FADP"), ("fadep", "FADP"),
    ("FERMOJUPI", "FERC"), ("FERC", "FERC"),
    ("MP", "FEMP"), ("DP", "FADP"), ("FERRFIS", "FERRFIS"), ("ISS", "ISS"),
])
def test_o_fundo_e_reconhecido_como_o_selo_o_escreve(escrito, sigla):
    """O cadastro diz FADP; o selo do Tribunal imprime FADEP. É o mesmo fundo."""
    achado = ATR.fundo(escrito)
    assert achado is not None, f"não reconheceu {escrito!r}"
    assert achado["sigla"] == sigla


def test_fundo_inexistente_devolve_nada_em_vez_de_chutar():
    assert ATR.fundo("FUNDO_QUE_NAO_EXISTE") is None
    assert ATR.fundo("") is None


def test_papel_de_seguranca_tem_os_doze_do_acervo():
    assert len(ATR.TIPOS_DE_PAPEL) == 12
    assert ATR.papel(0) == "Sem papel"
    assert "TJMA" in ATR.papel(3)
    assert "desconhecido" in ATR.papel(99)


def test_a_coluna_por_servico_so_tinha_caminho_de_rtdpj():
    """O fato da coluna — e NÃO uma conclusão sobre o que a casa selava.

    Este teste se chamava `..._sao_todos_de_rtdpj` e a sua docstring dizia
    "nesta serventia só RTD/RCPJ selavam automaticamente". A asserção estava
    certa e a conclusão estava ERRADA: o oficial, que operou o sistema,
    corrigiu em 24/08/2026 — o E-Ofício selava automático no RCPN e no RI
    também. `strURL_Selador` era só onde o caminho ficava guardado POR
    SERVIÇO; nas outras atribuições ele vinha de outro lugar do programa.

    Fica o fato, sem a conclusão. Quem quer saber o que a casa selou olha
    `CAMINHOS_USADOS_POR_ESTA_CASA`, medido em 26.123 selos reais.
    """
    assert ATR.CAMINHOS_OBSERVADOS_DO_SELADOR
    for u in ATR.CAMINHOS_OBSERVADOS_DO_SELADOR:
        assert u.startswith("/selo/rtdpj/"), u


def test_a_casa_selava_automatico_nas_cinco_atribuicoes():
    """A medida que desfez a conclusão errada.

    26.123 selos com caminho gravado em `tbSeloIndividual.strURLAto`, em 34
    caminhos, cobrindo Notas, RI, RCPN, Protesto e RTD/RCPJ.
    """
    familias = {c.split("/")[2] for c in ATR.CAMINHOS_USADOS_POR_ESTA_CASA}
    assert familias == {"notas", "imovel", "civil", "protesto", "rtdpj"}
    assert len(ATR.CAMINHOS_USADOS_POR_ESTA_CASA) == 34
    assert sum(ATR.CAMINHOS_USADOS_POR_ESTA_CASA.values()) == 26123


# O único caminho que a casa usou e que a documentação de 2017 não traz.
# Medido: 46 selos, e o payload tem `ato`, `partes` e `selo` — este último com
# escrevente, folha, livro e termo. É a variante "com livro" do
# `/selo/rtdpj/atos-em-geral`, que leva `escrevente` e `quantidade` e nada de
# livro. Não foi acrescentado a `selador.ENDPOINTS` de propósito: aquela tabela
# é gerada da documentação oficial, e misturar medição com documentação
# apagaria a procedência de ambas.
FORA_DO_CONTRATO_DE_2017 = "/selo/rtdpj/atos-em-geral-com-livro"


def test_o_contrato_cobre_tudo_que_a_casa_usa_menos_um_caso_conhecido():
    """33 dos 34 caminhos usados estão no contrato; o 34º está documentado aqui.

    Se um caminho NOVO sair do contrato, este teste cai — e é o que se quer:
    ou o contrato foi editado sem olhar o uso, ou a casa passou a usar algo
    que ninguém conferiu.
    """
    import selador
    conhecidos = set(selador.ENDPOINTS)
    faltando = sorted(set(ATR.CAMINHOS_USADOS_POR_ESTA_CASA) - conhecidos)
    assert faltando == [FORA_DO_CONTRATO_DE_2017], faltando


def test_a_variante_com_livro_e_irma_da_que_esta_no_contrato():
    """As duas existem, e a diferença entre elas é o livro.

    Guarda o que a medição achou: quem for implementar o RTD/RCPJ precisa das
    duas, e a de livro não tem schema oficial para conferir contra.
    """
    import selador
    assert "/selo/rtdpj/atos-em-geral" in selador.ENDPOINTS
    assert FORA_DO_CONTRATO_DE_2017 not in selador.ENDPOINTS
    # e a casa usou as duas
    assert ATR.CAMINHOS_USADOS_POR_ESTA_CASA["/selo/rtdpj/atos-em-geral"] == 53
    assert ATR.CAMINHOS_USADOS_POR_ESTA_CASA[FORA_DO_CONTRATO_DE_2017] == 46


def test_os_caminhos_de_uma_atribuicao_saem_pela_familia():
    protesto = ATR.caminhos_da_atribuicao("PROTESTO")
    assert protesto
    assert all(c.startswith("/selo/protesto/") for c in protesto)
    # O mais usado do Protesto é o pagamento — 465 selos.
    assert max(protesto, key=protesto.get) == "/selo/protesto/pagamento"

    # RTD e RCPJ dividem a família: o selador não os separa, nem o acervo.
    assert ATR.caminhos_da_atribuicao(3) == ATR.caminhos_da_atribuicao(4)
    assert all(c.startswith("/selo/rtdpj/")
               for c in ATR.caminhos_da_atribuicao("RCPJ"))


def test_o_reconhecimento_de_firma_e_metade_do_movimento_da_casa():
    """Serve para escolher o que fazer primeiro, e não é curiosidade."""
    total = sum(ATR.CAMINHOS_USADOS_POR_ESTA_CASA.values())
    firma = ATR.CAMINHOS_USADOS_POR_ESTA_CASA["/selo/notas/reconhecimento-firma"]
    assert firma / total > 0.5


# ------------------------------ os itens de custa que cada ato cobra


def test_um_ato_cobra_varios_itens_de_custa():
    """O modelo que a medição revelou, e que não é o óbvio.

    O CAMINHO é o ato; o código TJ é o ITEM DE CUSTA. Procurar um de-para de um
    para um seria procurar o que não existe.
    """
    # A prova mais limpa: na retirada de título protestado, os três itens
    # aparecem 49 vezes CADA — sempre juntos, no mesmo ato.
    retirada = ATR.itens_de_custa_do_ato("/selo/protesto/retirada")
    assert retirada == {"17.10.1": 49, "17.4": 49, "17.2": 49}


def test_o_item_de_custa_e_o_codigo_da_tabela_do_tribunal():
    """É o mesmo `codigo_tj` de `cx_servicos` — daí sai o preço.

    Conferido em 24.048 de 24.360 selos (98,7%): o código que foi no payload
    ao selador é o `strCodigoTJ` do serviço.
    """
    for caminho, itens in ATR.ITENS_DE_CUSTA_POR_CAMINHO.items():
        for codigo in itens:
            # Forma de item da tabela: números separados por ponto.
            assert all(p.isdigit() for p in codigo.split(".")), (caminho, codigo)


def test_a_secao_do_item_casa_com_a_atribuicao_do_caminho():
    """13 = Notas, 14 = RCPN, 15 = RTD/RCPJ, 16 = RI, 17 = Protesto.

    Não é regra absoluta — há ato que cobra item de outra seção, e por isso o
    teste olha o item MAIS USADO de cada caminho, que é o que manda.
    """
    secao_da_familia = {"notas": "13", "civil": "14", "rtdpj": "15",
                        "imovel": "16", "protesto": "17"}
    for caminho, itens in ATR.ITENS_DE_CUSTA_POR_CAMINHO.items():
        familia = caminho.split("/")[2]
        principal = max(itens, key=itens.get)
        assert principal.split(".")[0] == secao_da_familia[familia], (
            caminho, principal)


def test_caminho_sem_historico_devolve_vazio_e_nao_erro():
    # Ato novo não tem histórico, e não ter histórico não é defeito.
    assert ATR.itens_de_custa_do_ato("/selo/imovel/nunca-usado") == {}
    assert ATR.itens_de_custa_do_ato("") == {}
    assert ATR.itens_de_custa_do_ato(None) == {}


def test_todo_caminho_com_itens_e_um_caminho_que_a_casa_usou():
    # A tabela de itens sai dos mesmos selos que a de caminhos: uma não pode
    # falar de ato que a outra não conhece.
    assert set(ATR.ITENS_DE_CUSTA_POR_CAMINHO) <= set(
        ATR.CAMINHOS_USADOS_POR_ESTA_CASA)


# =========================================================== livro nucleo


def test_as_series_das_quatro_atribuicoes_novas_existem():
    assert len(LN.series_da("PROTESTO")) == 4
    assert len(LN.series_da("RCPJ")) == 3
    assert len(LN.series_da("RTD")) == 4
    assert len(LN.series_da("RCPN")) == 7
    assert len(LN.series_da("NOTAS")) == 6


@pytest.mark.parametrize("codigo,folhas", [
    ("RC_A", 300), ("RC_B", 300), ("RC_C", 300), ("RC_D", 300), ("RC_E", 150),
    ("PJ_A", 300), ("TD_B", 300), ("NT_ESCRITURA", 200),
])
def test_a_capacidade_de_cada_serie_veio_do_acervo(codigo, folhas):
    assert LN.serie(codigo).folhas == folhas


def test_o_rcpn_e_um_registro_por_folha():
    """`tbPropriedadeRCPN`: intRegistrosFolha = 1 em todos os livros."""
    for codigo in LN.series_da("RCPN"):
        assert LN.serie(codigo).por_face == 1, codigo
        assert LN.serie(codigo).folha_nova is True, codigo


def test_o_apontamento_do_protesto_cabe_varios_por_folha():
    ap = LN.serie("PT_APONTAMENTO")
    assert ap.por_face == 52          # medido no acervo, nao estimado
    assert ap.folha_nova is False
    assert ap.capacidade == 200 * 52  # exatamente as 10.400 linhas pre-criadas
    assert "NAF=52" in ap.observacao, "o número tem de dizer de onde veio"


def test_os_livros_de_protocolo_sao_diarios():
    diarios = {k for k, v in LN.SERIES.items() if v.diario}
    assert diarios == {"PT_PROTOCOLO", "PJ_PROTOCOLO", "TD_PROTOCOLO"}


def test_rtd_e_rcpj_transbordam_e_o_rcpn_nao():
    """`bitPassarDoLimiteDoLivro` era verdadeiro no controlador de TD/PJ."""
    for codigo in ("PJ_A", "PJ_B", "TD_B", "TD_C", "TD_F"):
        assert LN.serie(codigo).transborda is True, codigo
    for codigo in LN.series_da("RCPN"):
        assert LN.serie(codigo).transborda is False, codigo


def test_so_as_notas_exigem_paginas_pares():
    pares = {k for k, v in LN.SERIES.items() if v.paginas_pares}
    assert pares == set(LN.series_da("NOTAS"))


# ---- a geometria


def test_a_folha_tem_frente_e_verso():
    assert LN.rotulo_folha(12) == "12"
    assert LN.rotulo_folha(12, verso=True) == "12v"


def test_as_faces_de_um_registro_saem_na_ordem():
    e = LN.serie("NT_ESCRITURA")
    assert LN.faces_de(e, 14, 1) == ["14"]
    assert LN.faces_de(e, 14, 2) == ["14", "14v"]
    assert LN.faces_de(e, 14, 3) == ["14", "14v", "15"]
    assert LN.faces_de(e, 14, 4) == ["14", "14v", "15", "15v"]


def test_o_verso_que_sobra_e_apontado_para_inutilizacao():
    """A exigência que a inspeção fez às QUATRO atribuições novas."""
    e = LN.serie("NT_ESCRITURA")
    assert LN.sobra_de(e, 14, 1) == ["14v"]
    assert LN.sobra_de(e, 14, 3) == ["15v"]
    assert LN.sobra_de(e, 14, 2) == [], "página par não deixa sobra"
    assert LN.sobra_de(e, 14, 4) == []


def test_serie_de_varios_por_folha_nao_deixa_sobra():
    """Onde o registro seguinte continua na mesma folha, não há o que riscar."""
    assert LN.sobra_de(LN.serie("PT_APONTAMENTO"), 5, 1) == []
    assert LN.sobra_de(LN.serie("PT_PAGAMENTO"), 5, 1) == []


def test_paginas_pares_gastam_a_folha_inteira():
    e = LN.serie("NT_ESCRITURA")
    assert LN.folhas_para(e, 1) == 1
    assert LN.folhas_para(e, 2) == 1
    assert LN.folhas_para(e, 3) == 2
    assert LN.folhas_para(e, 4) == 2


def test_capacidade_em_registros_e_zero_onde_manda_o_tamanho_do_teor():
    assert LN.serie("NT_ESCRITURA").capacidade == 0
    assert LN.serie("RC_A").capacidade == 300
    assert LN.serie("PT_APONTAMENTO").capacidade == 200 * 52


def test_serie_desconhecida_levanta_erro():
    with pytest.raises(LN.LivroError, match="desconhecida"):
        LN.serie("LIVRO_QUE_NAO_EXISTE")


# ---- as regras que se contradizem sao recusadas na declaracao da serie


def test_serie_nao_pode_pedir_paginas_pares_sem_verso():
    with pytest.raises(LN.LivroError, match="se contradizem"):
        LN.Serie(codigo="X", atribuicao=1, nome="x", usa_verso=False, paginas_pares=True)


def test_serie_nao_pode_ter_varios_por_folha_e_folha_nova():
    with pytest.raises(LN.LivroError, match="folha nova"):
        LN.Serie(codigo="X", atribuicao=1, nome="x", por_face=5, folha_nova=True)


@pytest.mark.parametrize("folhas,por_face", [(0, 1), (-1, 1), (200, 0)])
def test_serie_com_tamanho_impossivel_e_recusada(folhas, por_face):
    with pytest.raises(LN.LivroError):
        LN.Serie(codigo="X", atribuicao=1, nome="x", folhas=folhas,
                 por_face=por_face, folha_nova=(por_face == 1))


# ---- o elo com a inspecao


def test_toda_exigencia_da_inspecao_esta_amarrada_a_uma_serie():
    ex = LN.exigencias_da_inspecao()
    todas = " ".join(t for v in ex.values() for t in v).lower()
    assert "inutilizar" in todas, "as quatro atribuições precisam disso"
    assert "assinatura" in todas, "RCPN e RCPJ"
    assert "termo de abertura" in todas, "Protesto"
    assert "rubricar" in todas, "Protesto"
    assert "encerramento diário" in todas, "Protesto e RCPJ"
    assert "continuidade da numeração" in todas, "RCPN, ao encerrar os auxiliares"


def test_as_series_de_inutilizacao_cobrem_as_quatro_atribuicoes_novas():
    ex = LN.exigencias_da_inspecao()
    com_inutilizacao = {LN.serie(k).atribuicao for k, v in ex.items()
                        if any("inutiliz" in t.lower() for t in v)}
    for sigla in ("PROTESTO", "RCPJ", "RTD"):
        assert ATR.codigo_da_atribuicao(sigla) in com_inutilizacao, sigla

"""
Testes do leitor do arquivo da CRA.

DE ONDE VEM A CONFIANCA NESTES TESTES
    O layout de 600 posicoes nao veio de manual — nao ha manual dele na
    maquina. Foi MEDIDO em 99 arquivos reais, 1.058 registros de titulo, com
    cada campo conferido contra o que o E-Oficio gravou para o MESMO titulo.
    A taxa de acerto de cada campo esta escrita no proprio modulo.

    A fixture `cra_remessa_exemplo.txt` e um arquivo real — o `B0011209.221`,
    de 12/09/2022 — com os NOMES trocados por «mascarado». As posicoes, os
    valores, as datas, os documentos das empresas e o CEP sao os de verdade,
    porque e disso que o teste precisa.

A ARMADILHA QUE ESTES TESTES GUARDAM
    As pastas do E-Oficio nao dizem o que o arquivo e. Ha arquivo de REMESSA
    dentro da pasta `Retorno`. Quem se guiar pela pasta le com o layout
    errado. Guia-se pelas posicoes 53 a 61 do cabecalho.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protesto_arquivo as A                     # noqa: E402

EXEMPLO = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_text("latin-1")


def linhas(texto: str) -> list[str]:
    return [x for x in texto.replace("\r\n", "\n").split("\n") if x.strip()]


def remontar(ls: list[str]) -> str:
    return "\r\n".join(ls) + "\r\n"


# --------------------------------------------------------------- o layout

def test_o_layout_cobre_as_600_posicoes_sem_buraco_e_sem_sobra():
    for campos, nome in ((A.TITULO_NA_REMESSA, "título da remessa"),
                         (A.TITULO_NO_RETORNO, "título do retorno"),
                         (A.CABECALHO, "cabeçalho"), (A.RODAPE, "rodapé")):
        pos = 1
        for c in campos:
            assert c.inicio == pos, f"{nome}: {c.nome} começa em {c.inicio}, " \
                                    f"esperado {pos}"
            pos = c.fim + 1
        assert pos - 1 == A.TAMANHO_DO_REGISTRO, nome


def test_todo_campo_medido_diz_quanto_conferiu():
    # Campo com taxa e campo medido. Campo sem taxa e campo que nao deu para
    # conferir — e isso tem de estar dito, nao suposto.
    medidos = [c for c in A.TITULO_NA_REMESSA if c.conferido is not None]
    assert len(medidos) >= 15
    for c in medidos:
        assert 0.0 <= c.conferido <= 100.0


def test_o_campo_nao_identificado_se_chama_reservado():
    # Nome bonito em campo desconhecido finge conhecimento que nao existe.
    for campos in (A.TITULO_NA_REMESSA, A.TITULO_NO_RETORNO):
        for c in campos:
            if c.conferido is None and not c.observacao:
                assert c.nome.startswith("reservado_"), c.nome


def test_o_que_ficou_a_conferir_esta_escrito():
    bairro = next(c for c in A.TITULO_NA_REMESSA if c.nome == "devedor_bairro")
    assert "A CONFERIR" in bairro.observacao


# ------------------------------------------------------------- os quatro tipos

def test_os_quatro_tipos_de_arquivo_e_o_sentido_de_cada_um():
    assert set(A.TIPOS) == {"BFOSDTTPR", "SDTBFORTP", "SDTBFOCRT", "SDTBFOAND"}
    assert A.TIPOS["BFOSDTTPR"]["sentido"] == "ENTRADA"
    for t in ("SDTBFORTP", "SDTBFOCRT", "SDTBFOAND"):
        assert A.TIPOS[t]["sentido"] == "SAIDA"


def test_o_tipo_vem_do_cabecalho_e_nao_da_pasta():
    a = A.ler(EXEMPLO)
    assert a.tipo == "BFOSDTTPR"
    assert a.sentido == "ENTRADA"
    assert a.nome_do_tipo == "Remessa de títulos para protesto"


def test_tipo_desconhecido_e_lido_assim_mesmo_com_o_achado():
    # Recusar o arquivo inteiro porque o tipo e novo perderia titulos bons.
    ls = linhas(EXEMPLO)
    ls[0] = ls[0][:52] + "XXXYYYZZZ" + ls[0][61:]
    a = A.ler(remontar(ls))
    assert len(a.titulos) == 1
    assert any("não está no catálogo" in x for x in a.achados)


# ----------------------------------------------------------------- a leitura

def test_o_arquivo_real_e_lido_inteiro_e_sem_achado():
    a = A.ler(EXEMPLO)
    assert a.em_ordem, a.achados
    assert len(a.titulos) == 1
    assert a.cabecalho["data_do_movimento"] == "2022-09-12"
    # O rodape da REMESSA conta REGISTROS — cabecalho + titulo + rodape = 3 —,
    # e nao titulos. Este teste dizia `quantidade_de_titulos == 1`, o que
    # passava porque o campo era lido com a largura errada (8 digitos a partir
    # de 53) e ninguem conferiu o valor contra a realidade. Medido em 191
    # remessas: 278 dos 370 arquivos batem exato com a contagem de registros.
    assert a.rodape["quantidade_de_registros"] == 3


def test_os_campos_do_titulo_saem_com_o_valor_certo():
    t = A.ler(EXEMPLO).titulos[0]
    assert t["especie"] == "DMI"
    assert t["numero_do_titulo"] == "84713/1"
    assert t["data_de_emissao"] == "2022-07-21"
    assert t["data_de_vencimento"] == "2022-09-05"
    assert t["valor_do_titulo"] == 148278          # centavos, sempre inteiro
    assert t["saldo_a_protestar"] == 148278
    assert t["praca_de_protesto"] == "VILA EXEMPLO"
    assert t["tipo_de_endosso"] == "M"
    assert t["aceite"] == "N"
    assert t["motivo_do_protesto"] == "1"
    assert t["devedor_cidade"] == "VILA EXEMPLO"
    assert t["cedente_uf"] == "SP"                 # o cedente é de fora
    assert t["devedor_uf"] == "MA"                 # o devedor é daqui
    assert t["sequencial"] == 2


def test_o_valor_e_lido_em_centavos_inteiros():
    # Em ponto flutuante, 1.482,78 vira 1482.7799999. Emolumento e protesto
    # nao aceitam centavo perdido no arredondamento.
    t = A.ler(EXEMPLO).titulos[0]
    assert isinstance(t["saldo_a_protestar"], int)


def test_o_arquivo_e_latin1_e_nao_utf8():
    # Ler como UTF-8 estoura no primeiro nome com cedilha. Ja estourou.
    bruto = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()
    a = A.ler(bruto)
    assert len(a.titulos) == 1


# ------------------------------------------------------- o que o arquivo diz

def test_rodape_da_remessa_que_declara_mais_registros_do_que_ha_e_denunciado():
    # A remessa conta REGISTROS. Declarar mais do que há é a assinatura de
    # arquivo que perdeu pedaço — e é o único caso em que se reclama, porque
    # comparar por igualdade fazia a conferência gritar em 191 remessas boas.
    ls = linhas(EXEMPLO)
    ls[-1] = ls[-1][:52] + "00007" + ls[-1][57:]
    a = A.ler(remontar(ls))
    assert any("declara 7 registro" in x for x in a.achados)
    assert len(a.titulos) == 1        # e mesmo assim leu o que havia


def test_rodape_da_remessa_que_declara_menos_nao_grita():
    # 92 dos 370 arquivos reais declaram MENOS registros do que trazem, e são
    # arquivos bons. Quem gerou contou de outro jeito; não é defeito nosso.
    ls = linhas(EXEMPLO)
    ls[-1] = ls[-1][:52] + "00001" + ls[-1][57:]
    a = A.ler(remontar(ls))
    assert not any("registro" in x for x in a.achados), a.achados


def test_rodape_do_retorno_que_erra_a_contagem_de_titulos_e_denunciado():
    # No RETORNO o campo conta TÍTULOS e confere exato nos 188 arquivos
    # medidos — logo, ali diferença é defeito, e se cobra por igualdade.
    ls = linhas(EXEMPLO_RETORNO)
    ls[-1] = ls[-1][:52] + "00007" + ls[-1][57:]
    a = A.ler(remontar(ls))
    assert any("declara 7 título" in x for x in a.achados)


def test_rodape_com_soma_errada_e_denunciado():
    ls = linhas(EXEMPLO)
    ls[-1] = ls[-1][:60] + "000000000999999" + ls[-1][75:]
    a = A.ler(remontar(ls))
    assert any("de saldo e os títulos somam" in x for x in a.achados)


def test_sequencial_fora_de_ordem_e_denunciado():
    ls = linhas(EXEMPLO)
    ls[1] = ls[1][:596] + "0099"
    a = A.ler(remontar(ls))
    assert any("sequencial 99" in x for x in a.achados)


# ------------------------------------------------------------- o que recusa

def test_linha_de_tamanho_errado_recusa_o_arquivo_dizendo_qual():
    ls = linhas(EXEMPLO)
    ls[1] = ls[1][:400]
    with pytest.raises(A.ArquivoError) as erro:
        A.ler(remontar(ls))
    assert "linha 2 tem 400" in str(erro.value)


def test_arquivo_sem_cabecalho_e_recusado():
    with pytest.raises(A.ArquivoError) as erro:
        A.ler(remontar(linhas(EXEMPLO)[1:]))
    assert "cabeçalho" in str(erro.value)


def test_arquivo_sem_rodape_e_recusado():
    with pytest.raises(A.ArquivoError) as erro:
        A.ler(remontar(linhas(EXEMPLO)[:-1]))
    assert "rodapé" in str(erro.value)


def test_arquivo_vazio_e_recusado():
    with pytest.raises(A.ArquivoError):
        A.ler("")


def test_linha_de_tipo_estranho_no_meio_vira_achado_e_nao_excecao():
    ls = linhas(EXEMPLO)
    ls.insert(2, "5" + " " * 599)
    a = A.ler(remontar(ls))
    assert any("começa com «5»" in x for x in a.achados)
    assert len(a.titulos) == 1


# --------------------------------------------------------------- as datas

def test_a_marca_de_sem_vencimento_vira_vazio_e_nao_data_de_9999():
    ls = linhas(EXEMPLO)
    ls[1] = ls[1][:235] + A.SEM_VENCIMENTO + ls[1][243:]
    t = A.ler(remontar(ls)).titulos[0]
    assert t["data_de_vencimento"] is None


def test_data_torta_nao_derruba_o_arquivo():
    # Um titulo com data torta nao pode fazer perder os outros mil.
    ls = linhas(EXEMPLO)
    ls[1] = ls[1][:235] + "32132022" + ls[1][243:]
    t = A.ler(remontar(ls)).titulos[0]
    assert t["data_de_vencimento"] is None
    assert t["numero_do_titulo"] == "84713/1"


# ---------------------------------------------------------- o documento

def test_o_cnpj_nao_perde_o_zero_da_frente():
    # Cortar zero por zero tira o primeiro dígito de todo CNPJ que começa com
    # zero — e há muitos. O tipo, ao lado, é que diz quantos dígitos são.
    assert A.documento_do_devedor(
        {"devedor_documento": "00000019000138",
         "devedor_tipo_de_documento": 1}) == {"CNPJ": "00000019000138"}


def test_o_cpf_sai_com_onze_digitos_e_nao_com_quatorze():
    assert A.documento_do_devedor(
        {"devedor_documento": "00012345678901",
         "devedor_tipo_de_documento": 2}) == {"CPF": "12345678901"}


def test_documento_em_branco_nao_inventa_numero():
    assert A.documento_do_devedor(
        {"devedor_documento": "", "devedor_tipo_de_documento": 1}) == {"CNPJ": ""}


# ------------------------------------------------ do arquivo para o ato

def test_o_titulo_do_arquivo_vira_apontamento_no_vocabulario_do_protesto():
    a = A.ler(EXEMPLO)
    ap = A.para_apontamento(a.titulos[0])
    assert ap["especie"] == "DMI"
    assert ap["valor"] == "1482.78"
    assert ap["saldo"] == "1482.78"
    assert ap["devedores"][0]["CNPJ"] == "00000019000138"
    assert ap["devedores"][0]["enderecos"][0]["cidade"] == "VILA EXEMPLO"
    assert ap["cedente"]["uf"] == "SP"


# ------------------------------------------------------------- o retorno
#
# `cra_retorno_exemplo.txt` e o arquivo real `R2371208 (1).221`, de
# `C:\ProgramData\CartorioGestao\arquivos\eoficio\CRA\Cancelamentos` — apesar do nome da pasta, o cabecalho diz
# SDTBFORTP, e e por ai que se sabe. Nao ha nome nem endereco de pessoa na
# linha de titulo do retorno (vem tudo em branco), entao nao ha o que
# mascarar: os valores, o protocolo e as datas sao os de verdade.

EXEMPLO_RETORNO = (Path(__file__).parent / "cra_retorno_exemplo.txt").read_text("latin-1")


def test_o_tipo_do_retorno_vem_do_cabecalho():
    a = A.ler(EXEMPLO_RETORNO)
    assert a.tipo == "SDTBFORTP"
    assert a.sentido == "SAIDA"
    assert len(a.titulos) == 1


def test_o_retorno_nao_repete_especie_nem_partes():
    # Metade do registro da remessa vem sempre em branco no retorno — o
    # retorno nao repete o que ja foi enviado, so diz o que aconteceu.
    t = A.ler(EXEMPLO_RETORNO).titulos[0]
    assert t["branco_20"].strip() == ""
    assert t["branco_275"].strip() == ""


def test_o_retorno_traz_protocolo_ocorrencia_e_data_medidos():
    # Este arquivo real e um cancelamento — e um dos casos em que a posicao
    # da ocorrencia leva a letra de `strOcorrenciaCancelamento` («A») em vez
    # do codigo numerico, e a data e a do cancelamento, nao a da ocorrencia
    # original. Ver LAYOUT_RETORNO_MEDIDO.md.
    t = A.ler(EXEMPLO_RETORNO).titulos[0]
    assert t["nosso_numero"] == "002000009917281"
    assert t["protocolo"] == 7793010003
    assert t["ocorrencia"] == "A"
    assert t["data_ocorrencia"] == "2022-08-12"
    assert t["valor_do_titulo"] == 55392
    assert t["saldo_a_protestar"] == 55392


def test_o_rodape_do_retorno_nao_e_o_da_remessa():
    # Ler a quantidade de titulos do retorno com a largura da remessa (8
    # digitos) sempre dava "1000" — medido em 194 arquivos reais. A largura
    # certa e 4.
    a = A.ler(EXEMPLO_RETORNO)
    assert a.rodape["quantidade_de_titulos"] == 1
    assert not any("Arquivo truncado ou emendado" in x for x in a.achados)


def test_o_que_nao_fechou_no_retorno_fica_reservado_e_nao_adivinhado():
    t = A.ler(EXEMPLO_RETORNO).titulos[0]
    # A letra de posicao 566 e um zero de posicao 568 nao tem hipotese que
    # tenha fechado — ver LAYOUT_RETORNO_MEDIDO.md. Ficam gravados, sem nome
    # bonito.
    assert t["reservado_566"] == "P"
    assert t["reservado_568"] == "0000000000"


def test_a_data_de_entrada_foi_identificada_e_e_lida_como_data():
    # Medida em 443 registros: 65,5% contra dtmE_Cartorio, e nunca anterior a
    # data da remessa que trouxe o titulo. Ver LAYOUT_RETORNO_MEDIDO.md.
    t = A.ler(EXEMPLO_RETORNO).titulos[0]
    assert t["data_entrada"] == "2022-05-31"


def test_a_data_de_entrada_nao_e_posterior_a_da_ocorrencia_neste_exemplo():
    # O titulo entra, e depois acontece a ocorrencia. A ordem importa: se
    # algum dia a leitura destas duas posicoes se inverter, isto pega.
    t = A.ler(EXEMPLO_RETORNO).titulos[0]
    assert t["data_entrada"] <= t["data_ocorrencia"]


def test_os_campos_constantes_do_retorno_dizem_que_sao_constantes():
    # 486 e 568 sao preenchimento FIXO — constantes em 443 registros de 2022
    # a 2026 —, e nao campo de dado que esta casa nunca usou. A observacao
    # tem de dizer isso, senao alguem tenta "descobrir" o que ja se sabe.
    campos = {c.nome: c for c in A.TITULO_NO_RETORNO}
    for nome in ("reservado_486", "reservado_568"):
        assert "constante" in campos[nome].observacao, nome


def test_a_marca_de_arquivo_esta_documentada_como_marca_de_arquivo():
    # 566 e constante DENTRO de cada arquivo (194 de 194). Quem a tratar como
    # atributo do titulo vai procurar sentido onde nao ha.
    campo = next(c for c in A.TITULO_NO_RETORNO if c.nome == "reservado_566")
    assert "arquivo" in campo.observacao


def test_arquivo_de_tipo_ainda_nao_medido_traz_a_linha_crua():
    # Os quatro tipos do catalogo estao medidos. Um tipo NOVO, que apareca
    # amanha, nao pode ser lido com o layout de outro — seria inventar. A
    # linha crua fica disponivel, com o achado.
    ls = linhas(EXEMPLO_RETORNO)
    ls[0] = ls[0][:52] + "XXXYYYZZZ" + ls[0][61:]
    a = A.ler(remontar(ls))
    assert a.titulos[0] == {"bruto": ls[1]}
    assert any("ainda não foi medido" in x for x in a.achados)


# ------------------------------------- a confirmacao e o andamento
#
# Medidos em 24/08/2026: 371 registros de confirmacao e 105 de andamento, do
# lote de 2026 que o oficial indicou no Proton Drive. Nos dois, a especie de
# TODOS os 476 confere com o acervo, casando por numero do titulo.

EXEMPLO_CONFIRMACAO = (Path(__file__).parent
                       / "cra_confirmacao_exemplo.txt").read_text("latin-1")
EXEMPLO_ANDAMENTO = (Path(__file__).parent
                     / "cra_andamento_exemplo.txt").read_text("latin-1")


def test_a_confirmacao_e_o_andamento_usam_o_layout_da_remessa_mais_o_bloco_do_retorno():
    # Nao sao um terceiro layout: sao o da remessa — com cedente, devedor e
    # especie preenchidos — mais o bloco 446-485, que traz protocolo,
    # ocorrencia e datas. Faz sentido: devolvem ao apresentante o titulo que
    # ele mandou, dizendo o que a casa fez com ele.
    nomes = {c.nome for c in A.TITULO_NA_CONFIRMACAO}
    assert {"cedente_nome", "devedor_nome", "especie"} <= nomes   # da remessa
    assert {"protocolo", "ocorrencia", "data_entrada"} <= nomes   # do retorno
    # E o bloco entrou no lugar exato do `reservado_446` da remessa, que ia de
    # 446 a 485 — nao em cima de outro campo.
    bloco = [c for c in A.TITULO_NA_CONFIRMACAO if 446 <= c.inicio <= 485]
    assert bloco[0].inicio == 446 and bloco[-1].fim == 485


def test_le_confirmacao_real():
    a = A.ler(EXEMPLO_CONFIRMACAO)
    assert a.tipo == "SDTBFOCRT"
    assert a.sentido == "SAIDA"
    t = a.titulos[0]
    assert t["especie"] == "DMI"                     # veio da remessa
    assert t["devedor_cidade"] == "VILA EXEMPLO"      # idem
    assert t["protocolo"] == 2608110002               # veio do retorno
    assert t["data_entrada"] == "2026-08-11"
    assert "bruto" not in t


def test_le_andamento_real():
    a = A.ler(EXEMPLO_ANDAMENTO)
    assert a.tipo == "SDTBFOAND"
    t = a.titulos[0]
    assert t["especie"] == "DMI"
    assert t["protocolo"] == 2607150001
    assert t["saldo_a_protestar"] == 30250
    assert "bruto" not in t


def test_a_composicao_do_layout_recusa_faixa_que_nao_cobre():
    # Layout com buraco ou sobreposicao le campo errado em silencio. A
    # composicao recusa na construcao, e nao depois.
    with pytest.raises(A.ArquivoError, match="não cobre"):
        A._compor(A.TITULO_NA_REMESSA, "reservado_446",
                  (A.Campo("curto", 446, 5),))


def test_os_quatro_tipos_do_catalogo_tem_layout():
    # Nenhum dos quatro cai mais na linha crua.
    assert set(A._CAMPOS_DO_TITULO) == set(A.TIPOS)


# ------------------------------------------------------------- a escrita
#
# ESCREVER e o que fecha o ciclo do Protesto — o item 8 do roteiro. E a prova
# de que esta certo nao e conferir campo a campo: e o IDA E VOLTA. Ler um
# arquivo real e reescreve-lo tem de sair identico byte a byte, inclusive nos
# campos que ninguem identificou.
#
# Medido em 24/08/2026 contra os 572 arquivos reais de C:\ProgramData\CartorioGestao\arquivos\eoficio\CRA:
#   BFOSDTTPR  191 identicos, 6 recusados (multi-lote), 0 diferentes
#   SDTBFOCRT  179 identicos de 179
#   SDTBFORTP  188 identicos, 6 recusados, 0 diferentes
#   SDTBFOAND  2 diferentes, e os dois trazem `ddMMyyyy` literal na origem
# Total: 566 dos 572 voltam identicos.


@pytest.mark.parametrize("exemplo,nome", [
    (EXEMPLO, "remessa"),
    (EXEMPLO_RETORNO, "retorno"),
    (EXEMPLO_CONFIRMACAO, "confirmação"),
    (EXEMPLO_ANDAMENTO, "andamento"),
])
def test_ida_e_volta_sai_identico_byte_a_byte(exemplo, nome):
    # O teste que prova a escrita. Um arquivo que volta identico prova que a
    # escrita conhece cada posicao, cada alinhamento e cada preenchimento —
    # inclusive os campos reservados, que tambem tem de voltar como estavam.
    devolvido = A.escrever(A.ler(exemplo))
    assert linhas(devolvido) == linhas(exemplo), nome


def test_sem_vencimento_volta_como_a_marca_e_nao_como_zeros():
    # `99999999` e a marca da CRA para titulo sem vencimento. A leitura a
    # traduz para vazio, que esta certo — nao ha data. Mas na volta o vazio
    # tem de virar a marca outra vez: zeros ali seriam data invalida onde o
    # arquivo dizia "nao tem". Sem isto, 22 arquivos reais voltavam diferentes.
    ls = linhas(EXEMPLO)
    ls[1] = ls[1][:235] + A.SEM_VENCIMENTO + ls[1][243:]
    original = remontar(ls)
    lido = A.ler(original)
    assert lido.titulos[0]["data_de_vencimento"] is None
    assert linhas(A.escrever(lido)) == linhas(original)


def test_escrever_recusa_tipo_sem_layout_medido():
    # Escrever com o layout de outro tipo produziria arquivo que a Central le
    # errado, e a casa nao teria como saber.
    a = A.ler(EXEMPLO_RETORNO)
    a.tipo = "XXXYYYZZZ"
    with pytest.raises(A.ArquivoError, match="não foi medido"):
        A.escrever(a)


def test_escrever_recusa_arquivo_com_lotes_emendados():
    # 12 dos 572 arquivos reais trazem mais de um lote no mesmo arquivo.
    # Reescrever deixaria os lotes de tras faltando, e calado.
    ls = linhas(EXEMPLO_RETORNO)
    emendado = remontar(ls + ls)          # dois lotes, um atras do outro
    a = A.ler(emendado)
    with pytest.raises(A.ArquivoError, match="mais de um lote"):
        A.escrever(a)


def test_escrever_recusa_titulo_que_so_foi_lido_como_linha_crua():
    ls = linhas(EXEMPLO_RETORNO)
    ls[0] = ls[0][:52] + "XXXYYYZZZ" + ls[0][61:]
    a = A.ler(remontar(ls))
    a.tipo = "SDTBFORTP"                  # finge tipo conhecido
    with pytest.raises(A.ArquivoError, match="linha crua"):
        A.escrever(a)


def test_monta_retorno_novo_com_rodape_calculado():
    a = A.montar_retorno(
        apresentante_codigo="237", apresentante_nome="BRADESCO SA",
        dia="2026-08-24",
        titulos=[{"nosso_numero": "002000009917281", "protocolo": 7793010003,
                  "ocorrencia": "1", "saldo_a_protestar": 55392,
                  "valor_do_titulo": 55392, "data_ocorrencia": "2026-08-24"},
                 {"nosso_numero": "002000009917282", "protocolo": 7793010004,
                  "ocorrencia": "1", "saldo_a_protestar": 10000,
                  "valor_do_titulo": 10000, "data_ocorrencia": "2026-08-24"}])
    assert a.rodape["quantidade_de_titulos"] == 2
    assert a.rodape["soma_dos_valores"] == 65392

    # e o que se escreveu se le de volta, com os mesmos numeros
    relido = A.ler(A.escrever(a))
    assert relido.tipo == "SDTBFORTP"
    assert len(relido.titulos) == 2
    assert relido.titulos[0]["protocolo"] == 7793010003
    assert relido.rodape["quantidade_de_titulos"] == 2
    assert relido.rodape["soma_dos_valores"] == 65392
    # e nao sobra achado: o rodape confere com o que foi escrito
    assert relido.em_ordem, relido.achados


def test_o_retorno_montado_leva_os_campos_de_preenchimento_fixo():
    # 486 traz "00", 446 traz "01" e 467 sai zero — medidos em 443 registros
    # de quatro anos. Escrever branco ali seria escrever o que o arquivo real
    # nunca trouxe. O 467 zerado e o que o E-Oficio fez em 416 dos 443.
    a = A.montar_retorno(apresentante_codigo="237", apresentante_nome="X",
                         dia="2026-08-24",
                         titulos=[{"nosso_numero": "1", "saldo_a_protestar": 1}])
    t = A.ler(A.escrever(a)).titulos[0]
    assert t["reservado_486"] == "00"
    assert t["reservado_446"] == "01"
    assert t["reservado_467"] == "0000000000"


# ------------------------------------- a marca do apresentante (posicao 566)
#
# "Na duvida, como o E-Oficio fazia, ou um padrao aceito antes" — decisao do
# oficial em 24/08/2026. A letra da 566 nao se deduz do titulo; deduz-se do
# APRESENTANTE, e cada linha de MARCA_POR_APRESENTANTE e uma letra que a
# Central ja aceitou daquele apresentante.


def test_a_marca_sai_do_historico_do_apresentante():
    # Bradesco (237) sempre mandou «P»; Armazem Mateus (949) sempre «A».
    assert A.marca_do_apresentante("237") == "P"
    assert A.marca_do_apresentante("949") == "A"
    assert A.marca_do_apresentante("  237 ") == "P"      # aceita sujo
    assert A.marca_do_apresentante("ZZZ") is None        # sem historico


@pytest.mark.parametrize("codigo,letra", [("237", "P"), ("949", "A")])
def test_o_retorno_montado_usa_a_letra_que_o_apresentante_ja_aceitou(codigo, letra):
    a = A.montar_retorno(apresentante_codigo=codigo, apresentante_nome="X",
                         dia="2026-08-24",
                         titulos=[{"nosso_numero": "1", "saldo_a_protestar": 1}])
    assert A.ler(A.escrever(a)).titulos[0]["reservado_566"] == letra


def test_apresentante_sem_historico_e_recusado_em_vez_de_chutado():
    # Dos 148 arquivos medidos, 74 levam «A» e 74 levam «P». Num empate exato
    # nao ha "o que o E-Oficio fazia" para imitar, e chutar seria inventar.
    with pytest.raises(A.ArquivoError, match="não há retorno anterior"):
        A.montar_retorno(apresentante_codigo="ZZZ", apresentante_nome="NOVO",
                         dia="2026-08-24",
                         titulos=[{"nosso_numero": "1", "saldo_a_protestar": 1}])


def test_a_letra_pode_ser_informada_a_mao_para_apresentante_novo():
    # E o caminho que a mensagem de recusa manda seguir: conferir num retorno
    # recente aceito e informar.
    a = A.montar_retorno(apresentante_codigo="ZZZ", apresentante_nome="NOVO",
                         dia="2026-08-24", marca="A",
                         titulos=[{"nosso_numero": "1", "saldo_a_protestar": 1}])
    assert A.ler(A.escrever(a)).titulos[0]["reservado_566"] == "A"


def test_toda_letra_da_tabela_e_A_ou_P():
    # Sao as duas unicas letras vistas em 234 retornos reais. Uma terceira
    # entrando na tabela e sinal de erro de transcricao.
    assert set(A.MARCA_POR_APRESENTANTE.values()) == {"A", "P"}


def test_o_apontamento_passa_no_contrato_da_cra():
    # Fecha o circuito: arquivo real -> estrutura -> contrato oficial.
    a = A.ler(EXEMPLO)
    assert A.conferir_remessa(a) == []


def test_titulo_torto_e_apontado_sem_derrubar_os_outros():
    ls = linhas(EXEMPLO)
    ls[1] = ls[1][:213] + "XXX" + ls[1][216:]       # espécie inventada
    a = A.ler(remontar(ls))
    problemas = A.conferir_remessa(a)
    assert len(problemas) == 1
    assert problemas[0]["numero_do_titulo"] == "84713/1"
    assert any("XXX" in f for f in problemas[0]["faltas"])


def test_o_layout_sai_em_tabela_para_a_tela_e_para_o_manual():
    tabela = A.descrever_layout()
    assert len(tabela) == len(A.TITULO_NA_REMESSA)
    assert tabela[0]["nome"] == "tipo_registro"
    assert all("inicio" in x and "fim" in x for x in tabela)


def test_a_letra_da_566_so_e_exigida_no_retorno():
    """CORRECAO DE 25/08/2026, achada quando a tela da remessa foi construida.

    `_montar_saida` exigia a letra da posicao 566 dos TRES arquivos de saida,
    porque ela e a mesma funcao para os tres. Mas `reservado_566` so existe no
    layout do RETORNO: na confirmacao e no andamento a posicao 566 cai dentro
    de `reservado_546` (546-596), medido como "zeros e brancos nos 343".

    O preco disso apareceu no balcao: a remessa de um apresentante NOVO nao
    podia ser recebida, porque a confirmacao pedia uma letra que so se aprende
    num retorno anterior — e apresentante novo nao tem retorno anterior.
    """
    titulo = {"numero_do_titulo": "9911/1", "saldo_a_protestar": 100}
    # Sem marca, e com apresentante que esta casa nunca respondeu:
    novo = "ZZZ"
    assert A.marca_do_apresentante(novo) is None

    confirmacao = A.montar_confirmacao(
        apresentante_codigo=novo, apresentante_nome="BANCO NOVO",
        dia="2026-08-25", titulos=[dict(titulo)])
    assert A.ler(A.escrever(confirmacao)).tipo == "SDTBFOCRT"

    andamento = A.montar_andamento(
        apresentante_codigo=novo, apresentante_nome="BANCO NOVO",
        dia="2026-08-25", titulos=[dict(titulo)])
    assert A.ler(A.escrever(andamento)).tipo == "SDTBFOAND"

    # O RETORNO continua recusando: ali o campo existe, e chutar a letra seria
    # inventar. Nos arquivos medidos o empate e exato, 74 «A» e 74 «P».
    with pytest.raises(A.ArquivoError) as erro:
        A.montar_retorno(apresentante_codigo=novo, apresentante_nome="BANCO NOVO",
                         dia="2026-08-25", titulos=[dict(titulo)])
    assert "posição 566" in str(erro.value)

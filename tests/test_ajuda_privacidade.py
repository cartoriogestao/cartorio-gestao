"""A barreira que nenhum envio da Ajuda pode contornar."""
from __future__ import annotations

import hashlib

import pytest

import ajuda_privacidade as PRIV


def test_o_envelope_inteiro_e_sanitizado_com_marcadores_estaveis():
    instrucao = (
        "Usuário em C:\\Users\\fulano\\Cartorio. "
        "Titular: Maria da Silva. Contato maria.silva@example.com."
    )
    pergunta = (
        "Maria da Silva informou CPF 000.000.048-55 e telefone "
        "(99) 98888-7777. Endereço: Rua das Flores, 10. "
        "Matrícula 8.471. Saúde: cardiopatia."
    )

    pacote = PRIV.preparar_saida(instrucao=instrucao, pergunta=pergunta)

    for proibido in (
        "fulano", "Maria da Silva", "maria.silva@example.com",
        "000.000.048-55", "(99) 98888-7777", "Rua das Flores",
        "8.471", "cardiopatia",
    ):
        assert proibido not in pacote.auditavel
    assert pacote.auditavel.count("[PESSOA_01]") == 2
    assert pacote.contagens["CPF"] == 1
    assert pacote.contagens["EMAIL"] == 1
    assert pacote.contagens["TELEFONE"] == 1
    assert pacote.contagens["DADO_SENSIVEL"] == 1
    assert pacote.sha256 == hashlib.sha256(
        pacote.auditavel.encode("utf-8")).hexdigest()


def test_a_tabela_de_correspondencia_nao_integra_o_pacote():
    pacote = PRIV.preparar_saida(
        instrucao="Nome: João da Silva", pergunta="João da Silva perguntou")
    assert "João da Silva" not in repr(pacote)
    assert set(pacote.__dict__) == {
        "instrucao", "pergunta", "auditavel", "sha256", "versao",
        "contagens",
    }


# «NADA SAI SEM PASSAR AQUI» MUDOU DE LUGAR EM 14/09/2026, e não desapareceu.
#
# A garantia morava no cliente da Anthropic, que era o único transporte da
# ajuda e recusava qualquer coisa que não fosse o objeto da barreira. Com o
# transporte virando UM só na casa — o mesmo que serve o agente —, pôr a
# barreira dentro dele faria a regra depender de quem chama, e um chamador novo
# nasceria fora da cerca. Ela ficou onde sempre deveria estar: na AJUDA, que é
# quem monta o envelope.
#
# A PROVA ESTÁ EM `test_ajuda.py::test_nada_sai_sem_ter_passado_pela_barreira`,
# e é mais forte que a de antes: aquela conferia que o transporte RECUSARIA
# texto solto; esta confere que o texto que sai já está mascarado.


def test_regras_de_alta_confianca_nao_deixam_residuo():
    pacote = PRIV.preparar_saida(
        instrucao="token=segredo-supersecreto",
        pergunta="contato a@exemplo.com CPF 000.000.043-40 IP 192.168.0.12")
    assert "segredo-supersecreto" not in pacote.auditavel
    assert "a@exemplo.com" not in pacote.auditavel
    assert "000.000.043-40" not in pacote.auditavel
    assert "192.168.0.12" not in pacote.auditavel


# --------------------- O SISTEMA MASCARAVA A PRÓPRIA PERGUNTA — 08/09/2026
#
# Achado medindo `aj_consultas` na produção: perguntas como "protocolo RCPN" e
# "titulo RCPJ" saíam mascaradas em "protocolo [REFERENCIA_REGISTRAL_09]" — o
# balcão perguntava pelo módulo (a sigla da atribuição) e o sanitizador tratava
# a sigla como se fosse o NÚMERO de um protocolo real. A resposta do Claude
# então dizia "não consegui identificar uma pergunta clara". Nesta casa toda
# referência de verdade (matrícula, livro, folha, selo, protocolo, processo,
# título) tem pelo menos um dígito — nenhuma é uma sigla de três ou quatro
# letras.

@pytest.mark.parametrize("pergunta", [
    "protocolo RCPN", "titulo RCPJ", "protocolo de atendimento",
    "termo de abertura", "livro de casamento",
])
def test_SIGLA_DE_ATRIBUICAO_NAO_E_REFERENCIA_REGISTRAL(pergunta):
    pacote = PRIV.preparar_saida(instrucao="", pergunta=pergunta)
    assert pacote.auditavel.strip().endswith(pergunta) or pergunta in pacote.auditavel
    assert "REFERENCIA_REGISTRAL" not in pacote.auditavel


@pytest.mark.parametrize("pergunta,valor", [
    ("protocolo 4256", "4256"),
    ("matricula 8421", "8421"),
    ("livro 2-A", "2-A"),
    ("selo REGIST000000ABCDEFGHIJKLMNO01", "REGIST000000ABCDEFGHIJKLMNO01"),
])
def test_REFERENCIA_REGISTRAL_DE_VERDADE_CONTINUA_SENDO_MASCARADA(pergunta, valor):
    pacote = PRIV.preparar_saida(instrucao="", pergunta=pergunta)
    assert valor not in pacote.auditavel
    assert "[REFERENCIA_REGISTRAL_01]" in pacote.auditavel


def test_A_INSTRUCAO_FIXA_DA_AJUDA_SOBREVIVE_A_SANITIZACAO():
    """As duas linhas de `ajuda_mapa.resumo()` que citam "nome" e "tela"/
    "tabela"/"arquivo" não podem sumir dentro da barreira de privacidade —
    é o mesmo defeito do `protocolo RCPN`, pelo lado da INSTRUÇÃO em vez da
    pergunta do operador."""
    import ajuda_mapa as MAPA
    resumo = MAPA.resumo({"versao": "3.6.72", "quantas_telas": 1,
                          "quantas_tabelas": 1, "quantos_arquivos": 1,
                          "menu": [], "fatias": {}}, None)
    pacote = PRIV.preparar_saida(instrucao=resumo, pergunta="teste")
    assert "diga qual é a tela" in pacote.auditavel
    assert "Não invente" in pacote.auditavel
    assert "PESSOA" not in pacote.auditavel


def test_foto_e_digital_do_cadastro_nao_saem_na_ajuda():
    """Caminho de foto.jpg / digital_N.png é dado biométrico, não nome de arquivo."""
    pacote = PRIV.preparar_saida(
        instrucao="biometria: molde-legado-XYZ",
        pergunta="fotografia: o rosto colhido; arquivos foto.jpg e digital_1.png",
    )
    assert "molde-legado-XYZ" not in pacote.auditavel
    assert "o rosto colhido" not in pacote.auditavel
    assert "foto.jpg" not in pacote.auditavel
    assert "digital_1.png" not in pacote.auditavel


# ------------------------------------------ a pergunta em maiúsculas (23/09/2026)
#
# Das 51 consultas da ajuda até 23/09/2026, 15 saíram da serventia sem uma
# palavra da pergunta, porque o balcão escreve em maiúsculas e a régua via
# nome de pessoa em toda sequência maiúscula. As frases abaixo são as que o
# balcão escreveu de verdade — é a frase que diz o que se esperava.

@pytest.mark.parametrize("pergunta", [
    "COMO FAÇO PRA IMPRIMIR UMA CERTIDÃO DE OBITO",
    "NAÕ TO CONSEGUINDO IMPRIMIR A CERTIDÃO DE OBITO, COMO FAÇO PRA IMPRIMIR",
    "COMO FAZER CERTIDÃO COM SELO ISENTO COM DECLARAÇÃO DE HIPOSSUFICIENCIA",
    "TEM COMO PUXAR O RELATORIO DO CAIXA",
    "QUERO VER O RELATORIO DA ENTRADA DOS ATOS NO CAIXA NO FINAL DO DIA",
    "COMO APAGAR DEPOSITO PREVIO",
    "NÃO ESTOU CONSEGUINDO CALCULAR EMOLUMENTOS NO PROTOCOLO DE ORÇAMENTO",
    "COMO FAÇO PARA SELA O PRIMEIRO REGISTRO DE NASCIMENTO",
    "ONDE ENCONTRO OS OFICIOS QUE GEREI PARA DAR CIENCIA AO ESTADO, MUNICIPIO E UNIAO?",
    "NÃO ESTOU CONSEGUINDO FAZER ORÇAMENTO NO PROTOCOLO GERAL",
    "FAZER CALCULOS DE EMOLUMENTOS",
])
def test_A_PERGUNTA_DO_BALCAO_EM_MAIUSCULAS_CHEGA_INTEIRA(pergunta):
    pacote = PRIV.preparar_saida(instrucao="", pergunta=pergunta)
    assert pacote.pergunta == pergunta
    assert "PESSOA" not in pacote.contagens


@pytest.mark.parametrize("pergunta, nome, sobra", [
    ("A CERTIDÃO DE JOSÉ DA SILVA NÃO SAI", "JOSÉ DA SILVA", "A CERTIDÃO DE"),
    ("REGISTRO DE ANTONIO CARLOS DOS SANTOS", "ANTONIO CARLOS", "REGISTRO DE"),
    ("CERTIDAO DE OBITO DE FRANCISCO DAS CHAGAS", "CHAGAS", "CERTIDAO DE OBITO"),
    # NASCIMENTO e DIAS são palavra do balcão E sobrenome de gente (2.532 e
    # 2.407 vezes nos nomes do banco): ao lado de nome, são nome.
    ("CERTIDÃO DE NASCIMENTO DE MARIA DO NASCIMENTO", "MARIA DO NASCIMENTO",
     "CERTIDÃO DE NASCIMENTO DE"),
    ("JOSÉ DIAS NÃO CONSEGUE", "JOSÉ DIAS", "NÃO CONSEGUE"),
    ("NASCIMENTO SILVA PEDIU CERTIDÃO", "NASCIMENTO SILVA", "CERTIDÃO"),
    ("MARIA DAS DORES DIAS DO NASCIMENTO", "DORES", ""),
])
def test_O_NOME_NO_MEIO_DA_PERGUNTA_CONTINUA_MASCARADO(pergunta, nome, sobra):
    pacote = PRIV.preparar_saida(instrucao="", pergunta=pergunta)
    assert nome not in pacote.pergunta
    assert pacote.pergunta.startswith(sobra) or sobra in pacote.pergunta
    assert pacote.contagens.get("PESSOA", 0) >= 1


def test_o_nome_inteiro_vira_UM_marcador():
    """«JOSÉ DA SILVA» é uma pessoa: um marcador, e o DA vai junto."""
    pacote = PRIV.preparar_saida(instrucao="",
                                 pergunta="A CERTIDÃO DE JOSÉ DA SILVA NÃO SAI")
    assert pacote.pergunta == "A CERTIDÃO DE [PESSOA_01] NÃO SAI"


def test_palavra_digitada_errado_continua_mascarada():
    """O erro é para o lado seguro: o que não está na lista não passa."""
    pacote = PRIV.preparar_saida(instrucao="", pergunta="PEDIDO DE CERTIFDAO")
    assert "CERTIFDAO" not in pacote.pergunta


def test_o_vocabulario_esta_escrito_na_forma_em_que_se_compara():
    """Palavra com acento ou minúscula na lista nunca casaria com nada — e a
    lista pareceria maior do que é. As duas listas se comparam SEM ACENTO."""
    for palavra in PRIV._VOCABULARIO_COMUM | PRIV._VOCABULARIO_QUE_TAMBEM_E_NOME:
        assert palavra == PRIV._chave_da_palavra(palavra), palavra


def test_o_que_tambem_e_nome_esta_no_vocabulario():
    """O segundo nível é um recorte do primeiro; fora dele não teria efeito."""
    assert PRIV._VOCABULARIO_QUE_TAMBEM_E_NOME <= PRIV._VOCABULARIO_COMUM

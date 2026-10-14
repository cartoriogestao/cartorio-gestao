"""
Biblioteca de modelos de atos do Registro de Imoveis.

FUNDAMENTO NORMATIVO
    Lei 6.015/1973 (Lei de Registros Publicos), com as alteracoes da
        Lei 14.382/2022
    Codigo Civil (Lei 10.406/2002)
    Provimento CNJ n. 149/2023 - Codigo Nacional de Normas do Foro
        Extrajudicial, com as alteracoes dos Provimentos 171/2024, 174/2024,
        189/2025, 190/2025, 192/2025, 195/2025 e 224/2026
    Codigo de Normas da CGJ/TJMA, com destaque para o art. 479 (requisitos de
        qualificacao) e o art. 436 (prazos em dias uteis)

ADVERTENCIA QUE ACOMPANHA ESTE ARQUIVO
    Estes sao MODELOS DE TRABALHO, nao pareceres. Cada ato registral produz
    efeito juridico proprio e a qualificacao do titulo e indelegavel: cabe ao
    registrador conferir o texto contra o titulo apresentado antes de lavrar.
    Nenhum modelo substitui a leitura do titulo.

    Os requisitos listados em cada modelo servem de conferencia previa. Nao sao
    exaustivos, e a ausencia de exigencia na lista nao dispensa a analise.

COMO O MODELO FUNCIONA
    O campo `corpo` usa os mesmos marcadores das demais telas do sistema. O que
    estiver entre [colchetes maiusculos] e preenchimento manual: o sistema nao
    tem esses dados e nao deve inventa-los.
"""
from __future__ import annotations

# Qualificacao completa exigida pelo art. 479 do Codigo de Normas da CGJ/TJMA.
QUALIF_PF = ("nome civil completo sem abreviaturas, nacionalidade, estado civil "
             "(se casado: nome e qualificacao do conjuge, regime de bens, data do "
             "casamento e identificacao do assento), profissao, residencia e "
             "domicilio, e CPF")
QUALIF_PJ = ("nome empresarial, endereco da sede com logradouro, numero, cidade e "
             "estado, e CNPJ da matriz; em imovel rural, a nacionalidade de quem "
             "detem a maioria do capital social (Lei 5.709/1971)")

# Requisitos que valem para todo ato de registro.
COMUNS = [
    f"Qualificacao completa das partes — pessoa fisica: {QUALIF_PF}",
    f"Qualificacao completa das partes — pessoa juridica: {QUALIF_PJ}",
    "Continuidade: o transmitente deve ser o titular constante da matricula "
    "(Lei 6.015/73, art. 195)",
    "Especialidade objetiva: descricao do imovel conforme a matricula",
    "Disponibilidade: a area transmitida nao pode exceder a registrada",
    "Consulta previa a CNIB — indisponibilidade de bens",
    "Prenotacao valida (20 dias uteis; 40 em REURB-S)",
]

# Aquisicao ORIGINARIA nao tem transmitente na matricula, e por isso nao se
# submete a continuidade nem a disponibilidade. Usucapiao adquire-se contra o
# titular, nao dele; e o titulo de dominio destaca a area do patrimonio
# publico. O proprio Codigo de Normas da CGJ/TJMA prevê, no art. 761, o caso
# de a area usucapida ser MAIOR do que a matriculada — o que seria impossivel
# se a disponibilidade se aplicasse.
COMUNS_ORIGINARIA = [
    f"Qualificacao completa das partes — pessoa fisica: {QUALIF_PF}",
    f"Qualificacao completa das partes — pessoa juridica: {QUALIF_PJ}",
    "Especialidade objetiva: descricao do imovel com planta e memorial",
    "Nao se aplica a continuidade: a aquisicao e originaria, nao deriva do "
    "titular anterior",
    "Confrontacoes conferidas contra as matriculas vizinhas, para afastar "
    "sobreposicao",
    "Consulta previa a CNIB — indisponibilidade de bens",
    "Prenotacao valida (20 dias uteis; 40 em REURB-S)",
]


import re as _re_corpo


def _corpo(texto: str) -> str:
    """Junta o modelo escrito em varias linhas num paragrafo unico.

    O modelo e escrito quebrado no codigo, para caber na tela de quem o
    mantem; o ato sai corrido, sem claros nem espacos em branco (Codigo de
    Normas da CGJ/TJMA, art. 795, § 2º — a mesma regra, e a mesma funcao, de
    `notas_modelos._corpo`). Achado em 07/09/2026: esta era a unica biblioteca
    de modelos de ato que nao a aplicava — o `\\n` do codigo-fonte sobrevivia
    ate a matricula impressa, onde `ri_odt.texto_para_odf` transforma cada
    quebra em um paragrafo novo.
    """
    return _re_corpo.sub(r"\s*\n\s*", " ", texto.strip())


MODELOS: list[dict] = [

    # ---------------------------------------------------------------- REGISTROS

    {
        "codigo": "R-COMPRA-VENDA",
        "tipo": "R",
        "nome": "Compra e venda",
        "natureza": "Compra e venda",
        "fundamentacao": "Lei 6.015/73, art. 167, I, 29; CC, arts. 481 a 532 e 1.245",
        "requisitos": COMUNS + [
            "Escritura publica quando o valor exceder 30 salarios minimos (CC, art. 108)",
            "Comprovacao do recolhimento do ITBI",
            "Outorga conjugal, salvo separacao absoluta (CC, art. 1.647, I)",
            "CND do INSS quando exigivel",
            "Declaracao de Operacao Imobiliaria — DOI",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>COMPRA E VENDA.</b> {{ protocolo_frase }}
Pela escritura publica lavrada em [DATA DA ESCRITURA], no Livro [LIVRO], folhas
[FOLHAS], do [TABELIONATO], {{ transmitentes }}, na qualidade de OUTORGANTE(S)
VENDEDOR(ES), transmitiu(ram) a {{ adquirentes }}, na qualidade de OUTORGADO(S)
COMPRADOR(ES), o imovel objeto desta matricula, pelo preco certo e ajustado de
[PRECO POR EXTENSO E EM ALGARISMOS], ja pago e quitado.
{{ area_frase }}
<b>ITBI:</b> guia n. [NUMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI], no valor
de [VALOR DO ITBI].
<b>VALOR DECLARADO PARA FINS DE EMOLUMENTOS:</b> [VALOR PARA EMOLUMENTOS].
Apresentados e arquivados os documentos exigidos para o ato.</p>"""),
    },
    {
        "codigo": "R-DOACAO",
        "tipo": "R",
        "nome": "Doação",
        "natureza": "Doação",
        "fundamentacao": "Lei 6.015/73, art. 167, I, 33; CC, arts. 538 a 564",
        "requisitos": COMUNS + [
            "Escritura publica de doacao",
            "Comprovacao do ITCMD",
            "Se houver reserva de usufruto, registrar tambem o usufruto",
            "Se houver clausulas restritivas, averba-las (CC, art. 1.911)",
            "Aceitacao do donatario, expressa ou presumida",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>DOACAO.</b> {{ protocolo_frase }}
Pela escritura publica lavrada em [DATA DA ESCRITURA], no Livro [LIVRO], folhas
[FOLHAS], do [TABELIONATO], {{ transmitentes }}, na qualidade de DOADOR(ES), transmitiu(ram)
por doacao, a titulo gratuito, a {{ adquirentes }}, na qualidade de
DONATARIO(S), o imovel objeto desta matricula.
{{ area_frase }}
<b>VALOR ATRIBUIDO:</b> [VALOR ATRIBUIDO]. <b>ITCMD:</b> guia n.
[NUMERO DA GUIA DE ITCMD], recolhida em [DATA DO ITCMD].
«SE HOUVER RESERVA DE USUFRUTO: A doacao e feita com reserva de usufruto
vitalicio em favor do(s) doador(es), objeto de registro proprio.»
«SE HOUVER CLAUSULAS RESTRITIVAS: Gravam o imovel as clausulas de
INALIENABILIDADE, IMPENHORABILIDADE e INCOMUNICABILIDADE, objeto de averbacao
propria.»</p>"""),
    },
    {
        "codigo": "R-PERMUTA",
        "tipo": "R",
        "nome": "Permuta",
        "natureza": "Permuta",
        "fundamentacao": "Lei 6.015/73, art. 167, I, 30; CC, art. 533",
        "requisitos": COMUNS + [
            "Escritura publica de permuta",
            "ITBI sobre cada transmissao",
            "Descricao de ambos os imoveis permutados",
            "Se houver torna, indicar o valor e o respectivo tributo",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>PERMUTA.</b> {{ protocolo_frase }}
Pela escritura publica lavrada em [DATA DA ESCRITURA], no Livro [LIVRO], folhas
[FOLHAS], do [TABELIONATO], {{ transmitentes }} transmitiu(ram) a {{ adquirentes }} o imovel
objeto desta matricula, recebendo em permuta o imovel [DESCRICAO E MATRICULA DO
IMOVEL DADO EM TROCA].
{{ area_frase }}
«SE HOUVER TORNA: Houve torna de [VALOR DA TORNA], paga por [QUEM PAGOU A TORNA].»
<b>ITBI:</b> guia n. [NUMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI].</p>"""),
    },
    {
        "codigo": "R-HIPOTECA",
        "tipo": "R",
        "nome": "Hipoteca",
        "natureza": "Hipoteca",
        "fundamentacao": "Lei 6.015/73, art. 167, I, 2; CC, arts. 1.473 a 1.505",
        "requisitos": COMUNS + [
            "Titulo com o valor da divida, prazo, juros e forma de pagamento (CC, art. 1.424)",
            "Outorga conjugal do devedor (CC, art. 1.647, I)",
            "Grau da hipoteca, se houver anterior",
            "Nao se exige saneamento previo de especialidade para garantia real "
            "(Codigo TJMA, art. 479, § 3o, I)",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>HIPOTECA {GRAU: de primeiro grau | de segundo grau | de terceiro grau}.</b> {{ protocolo_frase }}
Por forca de {TITULO: escritura publica | cedula de credito | contrato particular} de [DATA DO TITULO],
{{ transmitentes }}, na qualidade de DEVEDOR(ES) HIPOTECANTE(S), deu(deram) em
hipoteca a {{ adquirentes }}, na qualidade de CREDOR(ES) HIPOTECARIO(S), o imovel
objeto desta matricula, em garantia da divida de [VALOR POR EXTENSO E EM
ALGARISMOS].
<b>CONDICOES:</b> prazo de [PRAZO], juros de [TAXA], vencimento em [DATA DE VENCIMENTO], demais
condicoes constantes do titulo.
{{ area_frase }}</p>"""),
    },
    {
        "codigo": "R-ALIENACAO-FIDUCIARIA",
        "tipo": "R",
        "nome": "Alienação fiduciária em garantia",
        "natureza": "Alienação fiduciária",
        "fundamentacao": "Lei 9.514/1997, arts. 22 a 33; Lei 6.015/73, art. 167, I, 35",
        "requisitos": COMUNS + [
            "Valor do principal da divida (Lei 9.514/97, art. 24, I)",
            "Prazo e condicoes de reposicao do emprestimo",
            "Taxa de juros e encargos",
            "Clausula de constituicao da propriedade fiduciaria",
            "Valor do imovel para efeito de venda em leilao e criterio de reajuste",
            "Clausula dispondo sobre os procedimentos do art. 27",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>ALIENACAO FIDUCIARIA EM GARANTIA.</b>
{{ protocolo_frase }}
Por forca de {TITULO: escritura publica | contrato particular | cedula de credito} de [DATA DO TITULO], {{ transmitentes }}, na qualidade de
FIDUCIANTE(S) DEVEDOR(ES), alienou(aram) fiduciariamente a {{ adquirentes }}, na
qualidade de FIDUCIARIO(A) CREDOR(A), o imovel objeto desta matricula, em garantia
da divida de [VALOR DA DIVIDA].
<b>CONDICOES (Lei 9.514/97, art. 24):</b> principal de [VALOR DO PRINCIPAL]; prazo de
[PRAZO]; juros de [TAXA]; encargos de [ENCARGOS]; valor do imovel para leilao de
[VALOR DO IMOVEL PARA LEILAO], reajustavel por [CRITERIO DE REAJUSTE]; aplicando-se os procedimentos do art. 27 da mesma lei.
{{ area_frase }}</p>"""),
    },
    {
        "codigo": "R-USUFRUTO",
        "tipo": "R",
        "nome": "Usufruto",
        "natureza": "Usufruto",
        "fundamentacao": "Lei 6.015/73, art. 167, I, 7; CC, arts. 1.390 a 1.411",
        "requisitos": COMUNS + [
            "Indicacao se vitalicio ou por prazo certo",
            "Qualificacao do usufrutuario e do nu-proprietario",
            "ITCMD quando instituido por doacao",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>USUFRUTO {ESPECIE: VITALICIO | POR PRAZO CERTO}.</b>
{{ protocolo_frase }}
Por forca de {TITULO: escritura publica | testamento | instrumento particular} de [DATA DO TITULO], fica instituido usufruto sobre o imovel objeto
desta matricula em favor de {{ adquirentes }}, na qualidade de USUFRUTUARIO(S),
permanecendo {{ transmitentes }} na condicao de NU-PROPRIETARIO(S).
«SE POR PRAZO CERTO: O usufruto vigora ate [DATA FINAL DO USUFRUTO].»
<b>VALOR ATRIBUIDO:</b> [VALOR].</p>"""),
    },
    {
        "codigo": "R-TITULO-DOMINIO",
        "tipo": "R",
        "nome": "Título de domínio (INCRA / regularização fundiária)",
        "natureza": "Título de domínio",
        "fundamentacao": ("Lei 11.952/2009, arts. 15 e seguintes; Lei 6.383/1976, art. 29; "
                          "Codigo de Normas CGJ/TJMA, arts. 742 a 746"),
        "requisitos": COMUNS_ORIGINARIA + [
            "Titulo expedido pelo orgao competente (INCRA, ITERMA, GETAT ou sucessor)",
            "Numero do processo administrativo de origem",
            "Clausulas resolutivas e prazo de inalienabilidade, quando houver",
            "Memorial descritivo georreferenciado e certificacao SIGEF, se exigivel",
            "CCIR e CAR do imovel rural",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>TITULO DE DOMINIO.</b>
{{ protocolo_frase }}
Pelo Titulo de Dominio n. [NUMERO DO TITULO], expedido em [DATA DO TITULO] no
Processo Administrativo n. [PROCESSO], o [ORGAO EXPEDIDOR], na condicao de OUTORGANTE, transmitiu a
propriedade do imovel objeto desta matricula a {{ adquirentes }}.
{{ area_frase }}
<b>VALOR DO TITULO:</b> [VALOR DO TITULO]. <b>CONDICOES DE PAGAMENTO:</b>
[PARCELAS, VALORES, VENCIMENTOS E ENCARGOS].
«SE HOUVER CONDICOES RESOLUTIVAS: <b>CONDICOES RESOLUTIVAS:</b> a aquisicao
sujeita-se as clausulas resolutivas, a inalienabilidade temporaria e a
possibilidade de reversao ao poder publico, nos termos do titulo e da
Lei 11.952/2009, objeto de averbacao propria.»
Apresentados e arquivados o titulo, plantas, memoriais descritivos, documentos
pessoais e demais pecas do procedimento.</p>"""),
    },
    {
        "codigo": "R-USUCAPIAO",
        "tipo": "R",
        "nome": "Usucapião",
        "natureza": "Usucapião",
        "fundamentacao": "CC, arts. 1.238 a 1.244; Lei 6.015/73, arts. 167, I, 28, e 216-A",
        "requisitos": COMUNS_ORIGINARIA + [
            "Sentenca transitada em julgado ou ata notarial no procedimento extrajudicial",
            "Planta e memorial descritivo assinados por profissional habilitado e "
            "pelos confrontantes (art. 216-A, II)",
            "Certidoes negativas dos distribuidores",
            "Justo titulo ou prova da posse mansa e pacifica pelo prazo legal",
            "Modalidade de usucapiao e prazo correspondente",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>USUCAPIAO [MODALIDADE DA USUCAPIAO].</b> {{ protocolo_frase }}
Por forca {ORIGEM: da sentenca proferida nos autos n. [PROCESSO], da [VARA], transitada em julgado em [DATA DO TRANSITO EM JULGADO] | da ata notarial e do procedimento extrajudicial concluido nos termos do art. 216-A da Lei 6.015/73}, fica reconhecida a aquisicao
originaria da propriedade do imovel objeto desta matricula por {{ adquirentes }},
pela usucapiao [MODALIDADE DA USUCAPIAO], exercida a posse desde [DATA DE INICIO DA POSSE].
{{ area_frase }}
<b>VALOR ATRIBUIDO:</b> [VALOR].</p>"""),
    },
    {
        "codigo": "R-ARREMATACAO",
        "tipo": "R",
        "nome": "Arrematação",
        "natureza": "Arrematação",
        "fundamentacao": "CPC, arts. 901 e 903; Lei 6.015/73, art. 167, I, 26",
        "requisitos": COMUNS + [
            "Carta de arrematacao expedida pelo juizo, com os requisitos do CPC, art. 901, § 2o",
            "Comprovacao do ITBI",
            "Prova de intimacao dos interessados e do credor hipotecario, se houver",
            "Auto de arrematacao assinado",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>ARREMATACAO.</b> {{ protocolo_frase }}
Pela Carta de Arrematacao expedida em [DATA DA CARTA] pelo Juizo da [VARA], nos autos
n. [PROCESSO], movidos por [EXEQUENTE] em face de [EXECUTADO], foi arrematado por
{{ adquirentes }} o imovel objeto desta matricula, pelo valor de [VALOR DA ARREMATACAO],
em hasta publica realizada em [DATA DA HASTA].
{{ area_frase }}
<b>ITBI:</b> guia n. [NUMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI].</p>"""),
    },
    {
        "codigo": "R-ADJUDICACAO",
        "tipo": "R",
        "nome": "Adjudicação",
        "natureza": "Adjudicação",
        "fundamentacao": "CPC, art. 877; Lei 6.015/73, art. 167, I, 26; Lei 6.766/79, art. 26, § 6o",
        "requisitos": COMUNS + [
            "Carta de adjudicacao ou decisao de adjudicacao compulsoria",
            "ITBI",
            "Na adjudicacao compulsoria extrajudicial, ata notarial e prova da quitacao",
            "Dispensa de regularidade fiscal do promitente vendedor (Codigo TJMA, art. 709)",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>ADJUDICACAO.</b> {{ protocolo_frase }}
Por forca {ORIGEM: da carta de adjudicacao expedida em [DATA DA CARTA] pelo Juizo da [VARA], autos n. [PROCESSO] | da ata notarial de adjudicacao compulsoria lavrada em [DATA DA ATA] no [TABELIONATO]}, foi adjudicado a {{ adquirentes }} o imovel objeto
desta matricula, pelo valor de [VALOR DA ADJUDICACAO].
{{ area_frase }}
<b>ITBI:</b> guia n. [NUMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI].</p>"""),
    },
    {
        "codigo": "R-PARTILHA",
        "tipo": "R",
        "nome": "Partilha (inventário, divórcio ou dissolução)",
        "natureza": "Partilha",
        "fundamentacao": "CPC, arts. 610 e 659; Lei 6.015/73, art. 167, I, 25",
        "requisitos": COMUNS + [
            "Formal de partilha, carta de sentenca ou escritura publica",
            "ITCMD na transmissao causa mortis; ITBI no excedente da meacao",
            "Certidao de obito e qualificacao dos herdeiros, no inventario",
            "Quinhoes de cada herdeiro sobre o imovel",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>PARTILHA.</b> {{ protocolo_frase }}
Por forca {ORIGEM: do formal de partilha expedido em [DATA DO FORMAL] nos autos n. [PROCESSO] da [VARA] | da escritura publica de inventario e partilha lavrada em [DATA DA ESCRITURA] no [TABELIONATO] | da escritura publica de divorcio lavrada em [DATA DA ESCRITURA] no [TABELIONATO]}, coube a {{ adquirentes }} o imovel objeto desta matricula«SE FRACAO:, na proporcao de [FRACAO]».
{{ area_frase }}
<b>VALOR ATRIBUIDO:</b> [VALOR ATRIBUIDO]. <b>TRIBUTO:</b> {TRIBUTO: ITCMD | ITBI} guia n.
[NUMERO DA GUIA], recolhida em [DATA DO RECOLHIMENTO].</p>"""),
    },
    {
        "codigo": "R-INTEGRALIZACAO",
        "tipo": "R",
        "nome": "Integralização de capital social",
        "natureza": "Integralização de capital",
        "fundamentacao": "CC, arts. 997 e 1.055; Lei 6.015/73, art. 167, I, 32",
        "requisitos": COMUNS + [
            "Contrato ou alteracao contratual registrada na Junta Comercial ou no RCPJ",
            "Descricao e identificacao completa do imovel no contrato "
            "(Codigo TJMA, § 3o do dispositivo correspondente)",
            "Certidao de inteiro teor expedida ha no maximo 30 dias, quando de outra "
            "circunscricao",
            "Certidao negativa de onus reais expedida ha no maximo 30 dias",
            "Anuencia do conjuge quando exigida",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>INTEGRALIZACAO DE CAPITAL SOCIAL.</b>
{{ protocolo_frase }}
Por forca de {INSTRUMENTO: contrato social | alteracao contratual} de [DATA DO CONTRATO],
registrado(a) na {ORGAO DE REGISTRO: Junta Comercial | RCPJ} sob o n. [NUMERO DO REGISTRO] em
[DATA DO REGISTRO], {{ transmitentes }}
transferiu(ram) a {{ adquirentes }}, para integralizacao de capital social, o
imovel objeto desta matricula, pelo valor de [VALOR].
{{ area_frase }}
<b>ITBI:</b> {ITBI: guia n. [NUMERO DA GUIA DE ITBI] | imune na forma do art. 156, § 2o, I, da CF}.</p>"""),
    },

    # -------------------------------------------------------------- AVERBACOES

    {
        "codigo": "AV-CONSTRUCAO",
        "tipo": "AV",
        "nome": "Construção (habite-se)",
        "natureza": "Construção",
        "fundamentacao": "Lei 6.015/73, art. 167, II, 4",
        "requisitos": [
            "Certidao de conclusao da obra (habite-se) expedida pelo municipio",
            "CND de obra do INSS ou prova de dispensa",
            "Area construida e numero de pavimentos ou unidades",
            "Inscricao no cadastro imobiliario municipal",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>CONSTRUCAO.</b> {{ protocolo_frase }}
Nos termos da Certidao de Conclusao de Obra (habite-se) n. [NUMERO DO HABITE-SE], expedida em
[DATA] pela Prefeitura Municipal de [MUNICIPIO], fica averbada a construcao de
[DESCRICAO] com area construida de [AREA] m2, edificada sobre o imovel objeto desta
matricula.
<b>CND/INSS:</b> [NUMERO DA CND OU DISPENSA].
<b>INSCRICAO MUNICIPAL:</b> [INSCRICAO MUNICIPAL].</p>"""),
    },
    {
        "codigo": "AV-GEORREFERENCIAMENTO",
        "tipo": "AV",
        "nome": "Georreferenciamento (certificação SIGEF/INCRA)",
        "natureza": "Georreferenciamento",
        "fundamentacao": "Lei 10.267/2001; Decreto 4.449/2002; Lei 6.015/73, art. 176, § 3o",
        "requisitos": [
            "Certificacao do INCRA pelo SIGEF, com codigo",
            "Planta e memorial descritivo assinados por profissional credenciado",
            "ART/TRT do responsavel tecnico",
            "Anuencia dos confrontantes ou declaracao de respeito a divisas",
            "CCIR e CAR atualizados",
            "Nao altera a titularidade: e retificacao de descricao",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>GEORREFERENCIAMENTO.</b> {{ protocolo_frase }}
Nos termos da certificacao expedida pelo Instituto Nacional de Colonizacao e
Reforma Agraria — INCRA, sob o codigo SIGEF n. [CODIGO SIGEF], em [DATA DA CERTIFICACAO],
fica averbada a
descricao georreferenciada do imovel objeto desta matricula, passando a constar:
<b>AREA:</b> [AREA] ha; <b>PERIMETRO:</b> [PERIMETRO] m, com limites e confrontacoes
descritos conforme coordenadas referenciadas ao Sistema Geodesico Brasileiro,
Sistema de Referencia SIRGAS 2000, na forma do memorial descritivo arquivado.
<b>RESPONSAVEL TECNICO:</b> [NOME DO RESPONSAVEL], [TITULO PROFISSIONAL], conselho
profissional n. [NUMERO DO CONSELHO], credenciado no INCRA sob o codigo
[CODIGO DO CREDENCIAMENTO], documento de responsabilidade tecnica n. [NUMERO DA ART].
<b>CCIR:</b> [NUMERO DO CCIR]. <b>CAR:</b> [NUMERO DO CAR].
A presente averbacao nao altera a titularidade do imovel.</p>"""),
    },
    {
        "codigo": "AV-INDISPONIBILIDADE",
        "tipo": "AV",
        "nome": "Indisponibilidade de bens (CNIB)",
        "natureza": "Indisponibilidade",
        "fundamentacao": "Provimento CNJ 149/2023, arts. 500 e seguintes; Lei 6.015/73, art. 167, II, 12",
        "requisitos": [
            "Ordem oriunda da CNIB, com numero de protocolo",
            "Identificacao do orgao, juizo e processo",
            "CPF ou CNPJ do atingido — em pessoa juridica, os oito primeiros digitos "
            "alcancam matriz e filiais (Codigo TJMA)",
            "Nao se exige saneamento previo de especialidade (Codigo TJMA, art. 479, § 3o, II)",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>INDISPONIBILIDADE DE BENS.</b> {{ protocolo_frase }}
Nos termos da ordem de indisponibilidade registrada na Central Nacional de
Indisponibilidade de Bens — CNIB sob o protocolo n. [PROTOCOLO CNIB], determinada
em [DATA] pelo(a) [ORGAO / JUIZO], nos autos n. [PROCESSO], fica averbada a
INDISPONIBILIDADE do imovel objeto desta matricula, em razao de atingir
[NOME DO ATINGIDO], [CPF/CNPJ].
A indisponibilidade impede a pratica de atos de disposicao, permanecendo o imovel
sujeito as restricoes ate ordem de cancelamento pela mesma via.</p>"""),
    },
    {
        "codigo": "AV-PENHORA",
        "tipo": "AV",
        "nome": "Penhora, arresto ou sequestro",
        "natureza": "Penhora",
        # A penhora e AVERBADA. O Codigo de Normas da CGJ/TJMA e expresso: o
        # art. 502 manda averbar, e o art. 532, "k", repete a penhora na lista
        # de averbacoes. A Lei 6.015/73 arrola a penhora no inciso I do art. 167
        # (que e o inciso de registro) e o CPC, art. 844, fala em averbacao — a
        # divergencia e antiga. Nesta serventia se averba, e a fundamentacao
        # abaixo cita as tres fontes para que a nota devolutiva e a certidao
        # tenham onde se apoiar.
        "fundamentacao": ("Codigo de Normas CGJ/TJMA, arts. 502 e 532, \"k\"; "
                          "CPC, arts. 799, IX, e 844; Lei 6.015/73, art. 167, I, 5"),
        "requisitos": [
            "Mandado, certidao ou ordem eletronica do juizo",
            "Identificacao do processo, exequente e executado",
            "Valor da execucao",
            "Basta requerimento instruido com copia do auto ou do termo, "
            "independentemente de mandado (Codigo TJMA, art. 502)",
            "Havendo causa de impenhorabilidade no assento (bem de familia, "
            "hipoteca cedular), informar o juizo antes de averbar "
            "(Codigo TJMA, art. 502, § 3o)",
            "A partir de 2026, ordens judiciais de constricao tramitam pelo Constrijud "
            "(Provimento CNJ 224)",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>[TIPO DE CONSTRICAO: penhora, arresto ou sequestro].</b>
{{ protocolo_frase }}
Nos termos do [mandado / certidao / ordem eletronica] expedido(a) em [DATA DA ORDEM] pelo
Juizo da [VARA], nos autos n. [PROCESSO], movidos por [EXEQUENTE] em face de
[EXECUTADO], fica averbada a constricao sobre o imovel objeto desta matricula, no
valor de [VALOR DA EXECUCAO].
<b>DEPOSITARIO:</b> [NOME].</p>"""),
    },
    {
        "codigo": "AV-CANCELAMENTO-HIPOTECA",
        "tipo": "AV",
        "nome": "Cancelamento de hipoteca ou de garantia",
        "natureza": "Cancelamento de garantia",
        "fundamentacao": "Lei 6.015/73, arts. 250 e 251; CC, art. 1.499",
        "requisitos": [
            "Requerimento do credor com firma reconhecida, ou termo de quitacao",
            "Instrumento de cancelamento pela mesma forma do titulo constitutivo",
            "Identificacao do registro que se cancela",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>CANCELAMENTO DE [TIPO DE GARANTIA: hipoteca ou alienacao fiduciaria].</b>
{{ protocolo_frase }}
Nos termos de [termo de quitacao / requerimento com firma reconhecida / escritura
publica] de [DATA DA QUITACAO], firmado(a) por [CREDOR], fica cancelado o registro
[ATO CANCELADO, ex.: R-03], que constituira a garantia sobre o
imovel objeto desta matricula, por estar integralmente quitada a divida garantida.</p>"""),
    },
    {
        "codigo": "AV-ESTADO-CIVIL",
        "tipo": "AV",
        "nome": "Alteração de nome ou estado civil",
        "natureza": "Alteração de qualificação",
        "fundamentacao": "Lei 6.015/73, art. 167, II, 5; Codigo TJMA, art. 479, § 1o, II",
        "requisitos": [
            "Certidao do registro civil comprovando a alteracao",
            "Qualificacao completa do conjuge, regime de bens e data do casamento, "
            "quando o caso (Codigo TJMA, art. 479, I, c)",
            "Alteracoes de estado civil sao averbadas INDIVIDUALMENTE, respeitando a "
            "continuidade (Codigo TJMA, art. 479, § 2o)",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>ALTERACAO DE {O QUE MUDOU: NOME | ESTADO CIVIL}.</b>
{{ protocolo_frase }}
Nos termos da certidao de {ESPECIE DA CERTIDAO: casamento | obito | divorcio | averbacao} expedida em
[DATA DA CERTIDAO] pelo [CARTORIO], matricula n. [MATRICULA CRC], fica averbado que
[NOME ANTERIOR], titular de direito nesta matricula, passou a
[NOVO NOME E/OU NOVO ESTADO CIVIL].
«SE CASAMENTO: Casou-se em [DATA DO CASAMENTO] com [NOME E QUALIFICACAO COMPLETA DO CONJUGE], sob o regime de [REGIME DE BENS].»</p>"""),
    },
    {
        "codigo": "AV-CLAUSULAS",
        "tipo": "AV",
        "nome": "Cláusulas de inalienabilidade, impenhorabilidade e incomunicabilidade",
        "natureza": "Cláusulas restritivas",
        "fundamentacao": "CC, arts. 1.848 e 1.911; Lei 6.015/73, art. 167, II, 11",
        "requisitos": [
            "Titulo que institui as clausulas — doacao ou testamento",
            "Na doacao, justa causa quando incidir sobre a legitima (CC, art. 1.848)",
            "Prazo, se temporarias",
            "A inalienabilidade importa impenhorabilidade e incomunicabilidade (CC, art. 1.911)",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>CLAUSULAS RESTRITIVAS.</b> {{ protocolo_frase }}
Nos termos de {TITULO: escritura publica de doacao | testamento} de [DATA DO TITULO], ficam averbadas
sobre o imovel objeto desta matricula as clausulas de
[CLAUSULAS GRAVADAS],
{VIGENCIA: vitalicias | pelo prazo de [PRAZO]}, em favor de [BENEFICIARIO].
«SE HOUVER JUSTA CAUSA: JUSTA CAUSA declarada no titulo: [JUSTA CAUSA].»
Durante a vigencia da restricao o imovel nao podera ser alienado, onerado ou
transferido, salvo nas hipoteses admitidas em lei.</p>"""),
    },
    {
        "codigo": "AV-UNIFICACAO",
        "tipo": "AV",
        "nome": "Unificação, fusão ou desmembramento",
        "natureza": "Unificação / desmembramento",
        "fundamentacao": "Lei 6.015/73, arts. 234 e 235; Codigo TJMA (abertura de nova matrícula)",
        "requisitos": [
            "Requerimento do proprietario com firma reconhecida",
            "Imoveis contiguos e do mesmo proprietario, na unificacao",
            "Planta e memorial descritivo da nova configuracao",
            "Anuencia municipal no desmembramento urbano (Lei 6.766/79)",
            "Abertura de nova matricula com remissoes reciprocas",
            "Encerramento das matriculas de origem, quando o caso",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>[UNIFICACAO / FUSAO / DESMEMBRAMENTO].</b>
{{ protocolo_frase }}
A requerimento de {{ proprietarios_frase }}, e nos termos da planta e do memorial
descritivo arquivados, fica averbado o [DESMEMBRAMENTO / A UNIFICACAO] do imovel
objeto desta matricula, do qual resulta(m) [NUMERO] novo(s) imovel(is), objeto da(s)
matricula(s) [NUMEROS], abertas nesta data, com as remissoes reciprocas.
{{ area_frase }}
[SE ENCERRAMENTO: Fica esta matricula encerrada, na forma de averbacao propria.]</p>"""),
    },
    {
        "codigo": "AV-RESERVA-LEGAL",
        "tipo": "AV",
        "nome": "Reserva legal / Cadastro Ambiental Rural",
        "natureza": "Reserva legal",
        "fundamentacao": "Lei 12.651/2012, arts. 18 e 29; Lei 6.015/73, art. 167, II, 22",
        "requisitos": [
            "Inscricao no CAR com numero e data",
            "Planta e memorial da area de reserva legal",
            "Percentual conforme o bioma",
            "Registro no CAR desobriga a averbacao (Lei 12.651/12, art. 18, § 4o), "
            "mas a averbacao permanece admissivel a requerimento",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>RESERVA LEGAL.</b> {{ protocolo_frase }}
Nos termos da inscricao no Cadastro Ambiental Rural — CAR n. [NUMERO], efetuada em
[DATA], e do memorial descritivo arquivado, fica averbada a area de Reserva Legal do
imovel objeto desta matricula, com [AREA] ha, correspondente a [PERCENTUAL]% da area
total, localizada conforme planta arquivada.
A area gravada nao pode ter a destinacao alterada, nos termos da Lei 12.651/2012.</p>"""),
    },
    {
        "codigo": "AV-EXTINCAO-USUFRUTO",
        "tipo": "AV",
        "nome": "Extinção de usufruto",
        "natureza": "Extinção de usufruto",
        "fundamentacao": "CC, art. 1.410; Lei 6.015/73, art. 167, II, 2",
        "requisitos": [
            "Certidao de obito, na extincao por morte",
            "Termo de renuncia com firma reconhecida, na renuncia",
            "Decurso do prazo, no usufruto temporario",
            "Identificacao do registro do usufruto que se extingue",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>EXTINCAO DE USUFRUTO.</b> {{ protocolo_frase }}
Nos termos {CAUSA DA EXTINCAO: da certidao de obito expedida em [DATA DA CERTIDAO] pelo [CARTORIO], matricula n. [MATRICULA CRC] | do termo de renuncia de [DATA DA RENUNCIA] | do decurso do prazo}, fica averbada a
EXTINCAO do usufruto constituido pelo registro [ATO DO USUFRUTO] em favor de
[USUFRUTUARIO], consolidando-se a propriedade plena em nome de
{{ proprietarios_frase }}.</p>"""),
    },
    {
        "codigo": "AV-CANCELAMENTO",
        "tipo": "AV",
        "nome": "Cancelamento de ato",
        "natureza": "Cancelamento de ato",
        "fundamentacao": "Lei 6.015/73, arts. 248 a 259",
        "requisitos": [
            "Ordem judicial, requerimento do interessado ou documento habil",
            "Identificacao precisa do ato cancelado",
            "O ato cancelado permanece na ficha — cancelamento nao apaga assento",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>CANCELAMENTO DE ATO.</b> {{ protocolo_frase }}
Nos termos {ORIGEM: da decisao judicial proferida nos autos n. [PROCESSO] da [VARA] | do requerimento de [INTERESSADO] instruido com [DOCUMENTO]}, fica cancelado o ato
[ATO CANCELADO], pelos fundamentos ali expostos.
O ato cancelado permanece constando desta matricula, na forma dos arts. 248 e
seguintes da Lei 6.015/73.</p>"""),
    },
    {
        "codigo": "AV-ENCERRAMENTO",
        "tipo": "AV",
        "nome": "Encerramento de matrícula",
        "natureza": "Encerramento de matrícula",
        "fundamentacao": "Lei 6.015/73, arts. 233 a 235",
        "requisitos": [
            "Causa do encerramento: unificacao, fusao, desmembramento total ou decisao judicial",
            "Indicacao da(s) matricula(s) de destino",
            "Remissoes reciprocas entre origem e destino",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>ENCERRAMENTO DE MATRICULA.</b> {{ protocolo_frase }}
Em razao de [CAUSA: unificacao / fusao / desmembramento total / decisao judicial],
fica ENCERRADA esta matricula, passando o imovel a constar da(s) matricula(s)
[NUMEROS], desta Serventia, com as remissoes reciprocas.
Nao serao praticados novos atos nesta matricula.</p>"""),
    },
    {
        "codigo": "AV-ALTERACAO-LOGRADOURO",
        "tipo": "AV",
        "nome": "Alteração de logradouro ou numeração",
        "natureza": "Alteração de endereço",
        "fundamentacao": "Lei 6.015/73, art. 167, II, 13",
        "requisitos": [
            "Certidao ou lei municipal que alterou a denominacao ou a numeracao",
            "Requerimento do interessado",
            "Nao altera a descricao do imovel, apenas a localizacao",
        ],
        "corpo": _corpo("""<p><b>{{ rotulo }} —</b> <b>ALTERACAO DE {O QUE MUDOU: DENOMINACAO DE LOGRADOURO | NUMERACAO}.</b>
{{ protocolo_frase }}
Nos termos {ORIGEM: da Lei Municipal n. [NUMERO DA LEI] | da certidao expedida em [DATA DA CERTIDAO] pela Prefeitura Municipal de [MUNICIPIO]}, fica averbado que o imovel objeto desta
matricula, antes situado em [ENDERECO ANTERIOR], passou a ser designado como
[NOVO ENDERECO].
A presente averbacao nao altera a descricao nem a titularidade do imovel.</p>"""),
    },
]


def por_codigo(codigo: str) -> dict | None:
    for m in MODELOS:
        if m["codigo"] == codigo:
            return m
    return None


def por_tipo(tipo: str) -> list[dict]:
    return [m for m in MODELOS if m["tipo"] == tipo.upper()]


# --------------------------------------------------------- campos do modelo
#
# Cada [MARCADOR] do corpo vira um campo de formulario. A extracao e
# automatica para que nenhum modelo fique para tras quando alguem
# acrescentar um marcador novo — a metadata abaixo so refina rotulo e tipo.

import re as _re
import unicodedata as _ud

# ------------------------------------------------------------- notacoes
#
# O modelo usa TRES notacoes, e cada uma vira um controle diferente na tela.
# Antes havia so o colchete, servindo para as tres coisas ao mesmo tempo — e
# quando uma engolia a outra o ato saia com colchete solto e com as duas
# alternativas impressas juntas.
#
#   [CAMPO]                     preencher            -> caixa de texto
#   {ROTULO: opcao A | opcao B} escolher uma         -> lista suspensa
#   «SE ROTULO: trecho»         clausula que pode    -> caixa de marcar;
#                               nao existir             desmarcada, some
#
# Campo dentro de clausula opcional so e cobrado quando a clausula entra.

_MARCADOR = _re.compile(r"\[([^\[\]]{2,120})\]")
_ESCOLHA = _re.compile(r"\{([^{}]{2,300})\}")
_OPCIONAL = _re.compile(r"«([^«»]{2,1500})»", _re.S)

# Palavra encontrada no marcador -> tipo de campo e rotulo melhor.
_PISTAS = (
    ("DATA",        "data",  "Data"),
    ("VENCIMENTO",  "data",  "Vencimento"),
    ("VALOR",       "moeda", "Valor"),
    ("PRECO",       "moeda", "Preço"),
    ("AREA",        "texto", "Área"),
    ("PERIMETRO",   "texto", "Perímetro"),
    ("PERCENTUAL",  "texto", "Percentual"),
    ("PRAZO",       "texto", "Prazo"),
    ("TAXA",        "texto", "Taxa"),
    ("PROCESSO",    "texto", "Processo"),
    ("PROTOCOLO",   "texto", "Protocolo"),
    ("MATRICULA",   "texto", "Matrícula"),
    ("NUMERO",      "texto", "Número"),
    ("CODIGO",      "texto", "Código"),
    ("LIVRO",       "texto", "Livro"),
    ("FOLHAS",      "texto", "Folhas"),
    ("TABELIONATO", "texto", "Tabelionato"),
    ("VARA",        "texto", "Vara / juízo"),
    ("QUALIFICAR",  "longo", "Qualificação"),
    ("DESCRICAO",   "longo", "Descrição"),
    ("DESCREVER",   "longo", "Descrição"),
    ("SE HOUVER",   "longo", "Trecho opcional"),
    ("SE ",         "longo", "Trecho condicional"),
    ("CAUSA",       "longo", "Causa"),
    ("FUNDAMENTO",  "longo", "Fundamento"),
    ("JUSTA CAUSA", "longo", "Justa causa"),
    ("CONDICOES",   "longo", "Condições"),
    ("PARCELAS",    "longo", "Parcelas"),
    ("ENCARGOS",    "texto", "Encargos"),
    ("NOME",        "texto", "Nome"),
    ("ORGAO",       "texto", "Órgão"),
    ("MUNICIPIO",   "texto", "Município"),
    ("TITULO",      "texto", "Título"),
    ("GRAU",        "texto", "Grau"),
    ("MODALIDADE",  "texto", "Modalidade"),
    ("EXEQUENTE",   "texto", "Exequente"),
    ("EXECUTADO",   "texto", "Executado"),
    ("CREDOR",      "texto", "Credor"),
    ("DEPOSITARIO", "texto", "Depositário"),
    ("BENEFICIARIO","texto", "Beneficiário"),
    ("INTERESSADO", "texto", "Interessado"),
    ("USUFRUTUARIO","texto", "Usufrutuário"),
    ("PARTE",       "texto", "Parte"),
    ("ENDERECO",    "longo", "Endereço"),
    ("CRITERIO",    "texto", "Critério"),
    ("DOCUMENTO",   "texto", "Documento"),
    ("CARTORIO",    "texto", "Cartório"),
)

# Em que aba cada campo aparece.
_ABAS = (
    ("Título e documento", ("DATA","LIVRO","FOLHAS","TABELIONATO","TITULO","PROCESSO",
                            "VARA","ORGAO","DOCUMENTO","CARTORIO","MUNICIPIO","CODIGO",
                            "MODALIDADE","GRAU","MATRICULA")),
    ("Partes",             ("QUALIFICAR","NOME","EXEQUENTE","EXECUTADO","CREDOR",
                            "DEPOSITARIO","BENEFICIARIO","INTERESSADO","USUFRUTUARIO","PARTE")),
    ("Valores e tributos", ("VALOR","PRECO","NUMERO","PRAZO","TAXA","ENCARGOS",
                            "PARCELAS","CONDICOES","CRITERIO")),
)


def _chave(bruto: str) -> str:
    """'VALOR POR EXTENSO E EM ALGARISMOS' -> 'valor_por_extenso_e_em_algarismos'."""
    sem = "".join(c for c in _ud.normalize("NFD", bruto)
                  if _ud.category(c) != "Mn")
    return _re.sub(r"[^a-z0-9]+", "_", sem.lower()).strip("_")[:60]


def _parte_rotulo(bruto: str) -> tuple[str, str]:
    """Separa 'ROTULO: resto' quando houver rotulo antes dos dois pontos."""
    if ":" in bruto:
        cabeca, resto = bruto.split(":", 1)
        if len(cabeca.split()) <= 6:
            return cabeca.strip(), resto.strip()
    return "", bruto.strip()


def _le_escolha(bruto: str) -> tuple[str, list[str]] | None:
    """Le '{ROTULO: opcao A | opcao B}'. Devolve None se nao for escolha.

    O ROTULO com dois pontos e OBRIGATORIO, e nao por capricho: sem ele, um
    filtro do proprio Jinja — {{ nome|upper }} — seria lido como escolha entre
    'nome' e 'upper'. Exigir o rotulo separa marcacao de modelo de sintaxe de
    template.
    """
    limpo = " ".join(bruto.split())
    if ":" not in limpo:
        return None
    cabeca, resto = limpo.split(":", 1)
    if "|" in cabeca or len(cabeca.split()) > 6:
        return None
    opcoes = [o.strip() for o in resto.split("|") if o.strip()]
    if len(opcoes) < 2:
        return None
    return cabeca.strip(), opcoes


def _bonito(texto: str) -> str:
    """Rotulo legivel, preservando as siglas."""
    r = texto.strip()
    r = r[:1].upper() + r[1:].lower()
    for sigla in ("ITBI", "ITCMD", "INSS", "CND", "CCIR", "CAR", "SIGEF", "INCRA",
                  "ART", "CPF", "CNPJ", "RCPJ", "CF", "IPTU", "CNM", "ONR", "REURB"):
        r = _re.sub(rf"\b{sigla}\b", sigla, r, flags=_re.I)
    return r


def campos_do_modelo(modelo: dict) -> list[dict]:
    """Extrai da marcacao do corpo os controles da tela, na ordem em que aparecem.

    Devolve tres naturezas: `texto` (preencher), `escolha` (uma entre varias) e
    `condicao` (clausula que pode nao existir).
    """
    corpo = modelo["corpo"]
    vistos: dict[str, dict] = {}

    # 1. clausulas opcionais — e o que decide se os campos de dentro contam
    dentro_de_opcional: set[str] = set()
    for bruto in _OPCIONAL.findall(corpo):
        rotulo, texto = _parte_rotulo(" ".join(bruto.split()))
        rotulo = rotulo or texto[:40]
        chave = "se_" + _chave(rotulo)
        for campo in _MARCADOR.findall(bruto):
            dentro_de_opcional.add(_chave(" ".join(campo.split())))
        if chave not in vistos:
            vistos[chave] = {
                "chave": chave, "marcador": rotulo, "rotulo": _bonito(rotulo),
                "tipo": "condicao", "natureza": "condicao", "aba": "Cláusulas",
                "opcional": True, "opcoes": [], "trecho": texto,
            }

    # 2. escolhas
    for bruto in _ESCOLHA.findall(corpo):
        lido = _le_escolha(bruto)
        if not lido:
            continue
        rotulo, opcoes = lido
        limpo = " ".join(bruto.split())
        chave = "op_" + _chave(rotulo)
        if chave not in vistos:
            vistos[chave] = {
                "chave": chave, "marcador": limpo, "rotulo": _bonito(rotulo),
                "tipo": "escolha", "natureza": "escolha", "aba": "Título e documento",
                "opcional": False, "opcoes": opcoes, "trecho": "",
            }

    # 3. campos de preencher
    for bruto in _MARCADOR.findall(corpo):
        limpo = " ".join(bruto.split())
        chave = _chave(limpo)
        if not chave or chave in vistos:
            continue
        # O TIPO vem da pista; o ROTULO vem do proprio marcador. Usar o rotulo
        # da pista faria "DATA DA ESCRITURA" e "DATA DO ITBI" virarem dois
        # campos chamados "Data" — indistinguiveis na tela.
        tipo = "texto"
        for pista, t, _ in _PISTAS:
            if pista in limpo.upper():
                tipo = t
                break
        rotulo = _bonito(limpo)
        aba = "Outros"
        for nome_aba, pistas in _ABAS:
            if any(pi in limpo.upper() for pi in pistas):
                aba = nome_aba
                break
        vistos[chave] = {
            "chave": chave, "marcador": limpo, "rotulo": rotulo,
            "tipo": tipo, "natureza": "texto", "aba": aba,
            # Campo que so existe dentro de clausula opcional nao e cobrado
            # enquanto a clausula estiver desmarcada.
            "opcional": chave in dentro_de_opcional,
            "opcoes": [], "trecho": "",
        }
    return list(vistos.values())


def abas_do_modelo(modelo: dict) -> list[tuple[str, list[dict]]]:
    campos = campos_do_modelo(modelo)
    ordem = [nome for nome, _ in _ABAS] + ["Cláusulas", "Outros"]
    agrupado = {nome: [c for c in campos if c["aba"] == nome] for nome in ordem}
    return [(nome, lista) for nome, lista in agrupado.items() if lista]


def _marcado(valor) -> bool:
    return str(valor).strip().lower() in ("1", "true", "on", "sim", "s")


def preencher(modelo: dict, valores: dict) -> str:
    """Aplica os valores ao corpo do modelo.

    ORDEM, E ELA IMPORTA
        1. clausulas opcionais — a desmarcada some inteira, com os campos que
           tinha dentro; a marcada abre e o conteudo segue para as etapas
           seguintes;
        2. escolhas — fica so a opcao escolhida;
        3. campos.

    O que ficar por preencher CONTINUA visivel na marcacao de origem. Campo
    vazio precisa saltar aos olhos de quem confere, nao sumir do texto.
    """
    def troca_opcional(m):
        bruto = m.group(1)
        rotulo, texto = _parte_rotulo(" ".join(bruto.split()))
        rotulo = rotulo or texto[:40]
        if _marcado(valores.get("se_" + _chave(rotulo))):
            return texto
        return ""

    def troca_escolha(m):
        lido = _le_escolha(m.group(1))
        if not lido:
            return m.group(0)   # nao e escolha: Jinja, por exemplo
        rotulo, opcoes = lido
        escolhido = (valores.get("op_" + _chave(rotulo)) or "").strip()
        return escolhido if escolhido in opcoes else m.group(0)

    def troca_campo(m):
        limpo = " ".join(m.group(1).split())
        valor = (valores.get(_chave(limpo)) or "").strip()
        return valor if valor else f"[{limpo}]"

    corpo = _OPCIONAL.sub(troca_opcional, modelo["corpo"])
    corpo = _ESCOLHA.sub(troca_escolha, corpo)
    corpo = _MARCADOR.sub(troca_campo, corpo)
    # Espaco duplo e pontuacao solta que sobram quando uma clausula sai.
    corpo = _re.sub(r"[ \t]{2,}", " ", corpo)
    return _re.sub(r"\n{3,}", "\n\n", corpo)


def pendencias(texto: str) -> list[str]:
    """O que ficou por resolver no texto ja renderizado.

    Serve a tela e a conferencia antes de lavrar: campo em branco, escolha nao
    feita. Clausula opcional nao entra — nao escolher e uma escolha.
    """
    achados = [f"[{' '.join(m.split())}]" for m in _MARCADOR.findall(texto)]
    for bruto in _ESCOLHA.findall(texto):
        lido = _le_escolha(bruto)
        if lido:
            achados.append("{" + lido[0] + "}")
    return sorted(set(achados))

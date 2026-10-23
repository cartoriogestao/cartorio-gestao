"""
Biblioteca de modelos de atos do Tabelionato de Notas.

FUNDAMENTO NORMATIVO
    Codigo Civil (Lei 10.406/2002), com destaque para o art. 215, § 1º
        (requisitos da escritura publica) e os arts. 1.857 a 1.867 (testamento)
    Lei 8.935/1994 (Lei dos Notarios e Registradores)
    Lei 7.433/1985 e Decreto 93.240/1986 (requisitos da escritura de imovel)
    Provimento CNJ 149/2023 - Codigo Nacional de Normas do Foro Extrajudicial
    Codigo de Normas do Foro Extrajudicial do Maranhao - Provimento TJMA
        n. 28, de 23/04/2026, Capitulo IV, arts. 774 a 880

COMO SE ESCREVE UM ATO NOTARIAL, E POR QUE ESTES MODELOS SAO ASSIM
    Art. 795 do Codigo de Normas, que e a regra de ouro da lavratura:

      caput  redacao em linguagem clara, precisa e logica, em ordem cronologica
      § 1º   palavras no sentido usual e corrente, que nao originem duvida
      § 2º   "A escrituracao deve ser seguida, SEM CLAROS OU ESPACOS EM BRANCO"
      § 3º   sem abreviatura em palavra ou nome de pessoa, salvo autorizada em lei
      § 4º   a data e os numeros de dimensao ou quantidade por extenso, COM
             REPETICAO EM ALGARISMOS
      § 5º   medidas no sistema metrico decimal, SOB PENA DE NULIDADE
      § 6º   emenda, rasura, borrao, riscadura e entrelinha ressalvados no fim
             do texto e antes da subscricao

    Daqui vem a forma destes modelos: TEXTO CORRIDO. Um so fluxo, sem linha em
    branco, sem tabulacao, sem lista com marcador, sem campo pontilhado a
    esperar preenchimento a mao. Espaco em branco em ato notarial nao e questao
    de estetica: e o lugar por onde se acrescenta o que ninguem declarou.

    Por isso `texto_corrido()` roda depois do preenchimento, e nao antes: se uma
    clausula condicional sair, o buraco que ela deixaria e fechado.

O QUE OS MODELOS NAO FAZEM
    Nao qualificam por voce, nao decidem a natureza do ato e nao dispensam a
    leitura do titulo. Sao MODELOS DE TRABALHO. A funcao notarial e indelegavel
    (Lei 8.935/1994, art. 3º): cabe ao tabeliao conferir cada linha contra o que
    as partes declararam e contra os documentos apresentados.

    A lista de `requisitos` de cada modelo serve de conferencia previa. Nao e
    exaustiva, e a ausencia de uma exigencia na lista nao dispensa a analise.

MARCADORES, OS MESMOS DO RESTO DO SISTEMA
    [CAMPO]                      preencher              -> caixa de texto
    {ROTULO: opcao A | opcao B}  escolher uma            -> lista suspensa
    «SE ROTULO: trecho»          clausula que pode nao   -> caixa de marcar;
                                 existir                    desmarcada, some
    {{ variavel }}               vem do cadastro do ato

    O que esta entre [colchetes] o sistema NAO TEM e NAO DEVE INVENTAR.
"""
from __future__ import annotations

import re

from bd_nativo import banco

# --------------------------------------------------------- a qualificacao

# Art. 34 do Codigo de Normas do TJMA, combinado com o art. 215, § 1º, do
# Codigo Civil. Sai INTEIRA no traslado e na certidao: a qualificacao completa
# das partes nao e dado acessorio do ato — e o ato.
QUALIF_PF = ("nome completo, com prenome e sobrenome por extenso e sem "
             "abreviatura; nacionalidade e naturalidade; profissao; data de "
             "nascimento quando exigida; CPF; estado civil, e sendo casado o "
             "nome do conjuge, o regime de bens, a data do casamento e o livro, "
             "folha e serventia do assento; e o endereco completo, com "
             "logradouro, numero, unidade, condominio, bairro, municipio, "
             "estado, pais e CEP")
QUALIF_PJ = ("nome empresarial; CNPJ; endereco completo da sede; e a "
             "qualificacao de quem a representa, com o documento societario ou "
             "a procuracao que confere o poder, arquivada na serventia")

# Requisitos do art. 798 do Codigo de Normas, que valem para toda escritura.
COMUNS_ESCRITURA = [
    "Data do ato, com indicacao de local, dia, mes e ano (CN, art. 798, I)",
    "Lugar onde foi lida e assinada, com endereco completo, se fora da sede "
    "(CN, art. 798, II)",
    "Reconhecimento da identidade e da capacidade das partes e de quantos "
    "compareceram; nao sendo o comparecente conhecido do notario nem podendo "
    "identificar-se por documento, duas testemunhas que o conhecam devem "
    "participar do ato (CN, art. 798, III)",
    "Manifestacao das partes e dos intervenientes (CN, art. 798, IV)",
    f"Qualificacao completa — pessoa fisica: {QUALIF_PF} (CN, arts. 34 e 798, V)",
    f"Qualificacao completa — pessoa juridica: {QUALIF_PJ}",
    "Sendo parte representada, mencao ao livro, folha e serventia da procuracao "
    "e do substabelecimento, que ficam arquivados (CN, art. 798, VI)",
    "Havendo interesse de menor ou incapaz, mencao expressa a data de "
    "nascimento, com livro, folha, termo e serventia do assento, e por quem "
    "esta assistido ou representado (CN, art. 798, VII)",
    "Indicacao clara e precisa da natureza do negocio juridico e do seu objeto "
    "(CN, art. 798, VIII)",
    "Declaracao da forma de pagamento, se em especie, transferencia bancaria, "
    "transferencia eletronica, PIX ou cheque, este identificado (CN, art. 798, IX)",
    "Leitura do ato as partes, e a declaracao de que foi lido (CC, art. 215, "
    "§ 1º, VI e VII)",
    "Assinatura das partes e dos comparecentes, e o sinal publico do tabeliao",
]

# O que se acrescenta quando o ato versa sobre imovel (CN, arts. 800 a 802).
COMUNS_IMOVEL = [
    "Caracteristicas, confrontacoes e localizacao do imovel, de modo a permitir "
    "a perfeita individualizacao (CN, art. 800, I; Lei 6.015/73, art. 225; "
    "Lei 7.433/1985, art. 2º, § 1º)",
    "Certidao atualizada da matricula, apresentada e arquivada",
    "Comprovacao do recolhimento do imposto de transmissao, ou o reconhecimento "
    "de imunidade ou isencao pela autoridade fazendaria",
    "Certidao negativa de debito ou de regularidade do INSS, ou a declaracao de "
    "que as partes nao estao sujeitas a contribuicao (CN, art. 800, III)",
    "Numero da inscricao cadastral do imovel na Prefeitura ou no INCRA "
    "(CN, art. 800, IV)",
    "Numero predial e rua, sendo imovel edificado (CN, art. 800, V)",
    "Havendo pacto antenupcial, expressa referencia a serventia, data, livro, "
    "folhas e registro no Registro de Imoveis (CN, art. 800, VI)",
    "Referencia a emissao da DOI (CN, arts. 797 e 800, VII; Lei 10.426/2002, "
    "art. 8º)",
    "Outorga do conjuge, salvo no regime de separacao absoluta (CC, art. 1.647, I)",
    "Consulta previa a Central Nacional de Indisponibilidade de Bens",
]

# Imovel rural tem exigencia propria, e a falta anula (CN, arts. 801 e 802).
COMUNS_IMOVEL_RURAL = COMUNS_IMOVEL + [
    "Certificado de Cadastro de Imovel Rural (CCIR) apresentado — sem ele o "
    "proprietario nao pode desmembrar, arrendar, hipotecar, vender nem prometer "
    "em venda, SOB PENA DE NULIDADE (CN, art. 802, § 3º; Lei 4.947/1966, "
    "art. 22, § 1º)",
    "Transcricao resumida do CCIR com codigo do imovel, nome e nacionalidade do "
    "detentor, denominacao, modulo, area e localizacao (CN, arts. 801, V, e "
    "802, § 5º)",
    "Comprovacao do pagamento do ITR dos cinco ultimos exercicios, transcrita "
    "resumidamente no ato (CN, art. 802); na falta dos recibos, Certidao de "
    "Quitacao de Tributos e Contribuicoes Federais (§ 1º)",
    "Em desmembramento, a area desmembrada e a remanescente devem ser iguais ou "
    "superiores a fracao minima de parcelamento (CN, art. 801, I)",
    "Georreferenciamento e certificacao pelo INCRA, quando exigivel pelo "
    "cronograma do Decreto 4.449/2002",
    "Sendo adquirente estrangeiro, os limites e a autorizacao do INCRA "
    "(Lei 5.709/1971; CN, art. 801, § 1º)",
]

# O advogado nao e formalidade nestes atos: sem ele o tabeliao nao lavra, e a
# escritura nao serve de titulo (CN, arts. 808, § 1º, 819 e 822, § 5º).
ADVOGADO_OBRIGATORIO = (
    "Assistencia de advogado comum, de advogado de cada parte ou de defensor "
    "publico, ou parte atuando em causa propria, com qualificacao E ASSINATURA "
    "no proprio ato; e VEDADO ao tabeliao indicar advogado as partes"
)

# Inventario, partilha e sobrepartilha (CN, arts. 806 a 821; Resolucao CNJ
# 35/2007).
COMUNS_SUCESSAO = [
    ADVOGADO_OBRIGATORIO + " (CN, art. 808, § 1º)",
    "Todos os herdeiros CAPAZES e CONCORDES (CN, art. 808; CPC, art. 610)",
    "Certidao de obito do autor da heranca (CN, art. 811, III)",
    "Certidao da CENSEC sobre inexistencia de testamento (RCTO), E a declaracao "
    "das partes no corpo da escritura de que o autor da heranca nao deixou "
    "testamento nem outros herdeiros (CN, art. 811, X e XI, e art. 812, § 2º)",
    "Certidoes negativas de tributos do espolio — Federal, Estadual e Municipal "
    "— resumidas no ato (CN, arts. 808, § 3º, e 811, II)",
    "Recolhimento do ITCD, PREVIO a lavratura (CN, arts. 808, § 2º, e 819, "
    "paragrafo unico)",
    "Certidoes de propriedade dos imoveis e documentos de titularidade dos bens "
    "moveis e direitos, inclusive cotas de empresa e bens trazidos a colacao "
    "(CN, art. 811, VII e VIII)",
    "Havendo imovel rural, o CCIR com a certidao de quitacao do ITR "
    "(CN, art. 811, IX)",
    "Certidao de casamento do conjuge sobrevivente e dos herdeiros casados, e "
    "do pacto antenupcial registrado, se houver (CN, art. 811, V)",
    "Certidao comprobatoria do vinculo de parentesco dos herdeiros "
    "(CN, art. 811, VI)",
    "Indicacao do inventariante (CN, art. 811, XV)",
    "HAVENDO INCAPAZ OU CURATELADO, a minuta final vai ao Ministerio Publico "
    "para parecer em cinco dias, e a versao assinada menciona expressamente a "
    "aprovacao do Juizo, com o numero do procedimento no PJe (CN, art. 809, "
    "I, II e § 2º)",
    "Havendo processo judicial com o mesmo objeto, declarar na escritura que o "
    "ato so se registra com a comprovacao da extincao do processo, e cientificar "
    "as partes da faculdade de suspender ou desistir (CN, art. 821)",
    "Havendo disposicao testamentaria de reconhecimento de filho ou outra "
    "declaracao irrevogavel, a solucao extrajudicial e VEDADA (CN, art. 808, § 7º)",
    "A estrutura da escritura segue a ordem por titulos do art. 812 do Codigo "
    "de Normas",
]

# Separacao, divorcio, conversao e restabelecimento (CN, arts. 822 a 830).
COMUNS_FAMILIA = [
    ADVOGADO_OBRIGATORIO + " (CN, art. 822, § 5º)",
    "Manifestacao de vontade espontanea e isenta de vicios (CN, art. 823, I)",
    "Certidao de casamento com expedicao de no maximo noventa dias "
    "(CN, art. 826, I, com a redacao do Provimento 34/2023)",
    "Certidao do pacto antenupcial, se houver (CN, art. 824, IV)",
    "Numero de inscricao do advogado na OAB, com secao e unidade da federacao "
    "(CN, art. 824, V)",
    "Havendo processo em andamento, certidao do juizo informando a suspensao ou "
    "a desistencia (CN, art. 824, VI)",
    "Havendo partilha de imovel, certidao atualizada da matricula, de onus e de "
    "acoes reais e pessoais reipersecutorias, com no maximo trinta dias "
    "(CN, art. 825, VI)",
    "HAVENDO FILHO INCAPAZ OU NASCITURO a escritura pode ser lavrada, mas E "
    "VEDADA qualquer previsao sobre guarda, visitacao e alimentos desses "
    "filhos, e a escritura deve consignar EXPRESSAMENTE que as partes se "
    "comprometem a levar essas questoes ao Poder Judiciario (CN, art. 822, § 1º, "
    "com a redacao do Provimento 23/2024)",
    "Havendo duvida sobre o cabimento diante de filho incapaz ou nascituro, o "
    "tabeliao suscita duvida diretamente ao Juizo Corregedor Permanente "
    "(CN, art. 822, § 3º)",
    "A escritura NAO depende de homologacao judicial e e titulo habil para o "
    "registro civil, o registro de imoveis e o levantamento de deposito "
    "bancario (CN, art. 822, § 4º)",
    "Remessa a CESDI na quinzena da lavratura",
]

COMUNS_PROCURACAO = [
    f"Qualificacao completa do outorgante — {QUALIF_PF} (CN, art. 34)",
    "Qualificacao completa do outorgado, ainda que ausente do ato",
    "Poderes descritos de forma clara e precisa; poder para alienar, gravar, "
    "transigir, renunciar, dar quitacao e receber citacao exige mencao expressa "
    "(CC, art. 661, § 1º)",
    "Para poderes de alienar ou gravar imovel com onus real, certidao "
    "atualizada do registro de imoveis, exigida e arquivada, com validade de "
    "trinta dias da expedicao (CN, art. 833)",
    "Outorga do conjuge, quando os poderes alcancarem ato que a exija "
    "(CC, art. 1.647)",
    "Sendo o outorgante analfabeto ou impossibilitado de assinar, assinatura a "
    "rogo e impressao digital, com duas testemunhas",
]


# O TEXTO DAS MINUTAS SAIU DAQUI NO LF06D (19/10/2026) — e o nome delas junto.
#
#     «Nao deveriamos ter modelos no codigo; deveriam estar no banco, para
#      editar com mais facilidade.» — o oficial, 19/10/2026.
#
# O corpo de cada minuta mora em `modelos_padrao/notas/minutas/<codigo>.txt`, ja
# CORRIDO (um paragrafo so, art. 795, § 2º — o que o `_corpo()` daqui fazia ao
# juntar as linhas do codigo), com os mesmos bytes que esta lista montava; o
# nome mora na ficha `<codigo>.json` ao lado. A subida carrega a pasta na base
# dos padroes, e `minutas()` le de la (`modelos_da_casa.minuta_de_fabrica`).
#
# AQUI FICA O QUE E DO CODIGO: o tipo, a natureza e os codigos da CENSEC, os
# requisitos da conferencia previa e a fundamentacao. Os comentarios dentro de
# cada minuta continuam onde estavam e falam do texto dela, que esta no arquivo
# de mesmo codigo. O AJUSTE DA CASA continua em `nt_modelos`, como sempre:
# `instalar` so atualiza a linha que ninguem editou.
MINUTAS: list[dict] = [

    # =================================================== ESCRITURAS

    {
        "codigo": "NT-ESC-COMPRA-VENDA",
        "tipo": "ESCRITURA",
        "natureza": "Compra e venda",
        "natureza_censec": 6,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": ("CC, arts. 108, 215, 481 a 532 e 1.245; Lei 6.015/1973; "
                          "Lei 7.433/1985; Decreto 93.240/1986; Codigo Nacional de "
                          "Normas do CNJ (Provimento 149/2023); CN/TJMA, arts. 795, "
                          "798 e 800"),
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL + [
            "Modalidade da venda (ad corpus ou ad mensuram) expressa no ato",
            "Declaracao de tratamento de dados pessoais (LGPD, Lei 13.709/2018)",
        ],
        # A ORDEM POR TITULOS (I a X) E O PADRAO DE MINUTA que o oficial trouxe
        # em 07/09/2026 — «MINUTA_ESCRITURA_MATRICULA para modelo.docx», uma
        # escritura real de compra e venda rural — e que ele pediu para
        # imitar. O texto continua CORRIDO (art. 795, § 2º): os títulos são
        # marca dentro do mesmo parágrafo, e não linha em branco nem lista.
    },

    {
        "codigo": "NT-ESC-COMPRA-VENDA-RURAL",
        "tipo": "ESCRITURA",
        "natureza": "Compra e venda",
        "natureza_censec": 6,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": ("CC, arts. 108, 215, 481 a 532 e 1.245; Lei 6.015/1973; "
                          "Lei 7.433/1985; Decreto 93.240/1986; Lei 4.947/1966, "
                          "art. 22; Lei 9.393/1996, art. 20; Decreto 4.449/2002; "
                          "Codigo Nacional de Normas do CNJ (Provimento 149/2023); "
                          "CN/TJMA, arts. 801 e 802"),
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL_RURAL + [
            "Modalidade da venda (ad corpus ou ad mensuram) expressa no ato",
            "Recibo de inscricao no Cadastro Ambiental Rural (CAR), quando "
            "exigivel",
            "Declaracao de tratamento de dados pessoais (LGPD, Lei 13.709/2018)",
        ],
        # A ORDEM POR TITULOS (I a XIII) E O PADRAO DE MINUTA que o oficial
        # trouxe em 07/09/2026 — «MINUTA_ESCRITURA_MATRICULA para
        # modelo.docx», uma escritura real de compra e venda de imóvel rural
        # desta serventia — e que ele pediu para imitar. O texto continua
        # CORRIDO (art. 795, § 2º): os títulos são marca dentro do mesmo
        # parágrafo, e não linha em branco nem lista. O que o modelo real
        # trazia preenchido (nome das partes, matrícula, CCIR, CNIB) volta
        # como marcador — o sistema não inventa esse dado.
    },

    {
        "codigo": "NT-ESC-DOACAO",
        "tipo": "ESCRITURA",
        "natureza": "Doação",
        "natureza_censec": 22,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": ("CC, arts. 538 a 564, 1.846, 1.911 e 1.912; "
                          "CN/TJMA, arts. 795, 798 e 800"),
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL + [
            "Comprovacao do ITCMD, ou o reconhecimento de isencao",
            "Aceitacao do donatario, expressa no ato",
            "Havendo descendente ou conjuge, conferir se a doacao excede a parte "
            "de que o doador poderia dispor em testamento — o excesso e nulo "
            "(CC, art. 549) — e se e caso de adiantamento de legitima "
            "(CC, art. 544)",
            "A doacao de todos os bens sem reserva de parte da renda para a "
            "subsistencia do doador e nula (CC, art. 548)",
            "Clausula de inalienabilidade, impenhorabilidade e "
            "incomunicabilidade sobre a legitima exige justa causa declarada no "
            "proprio ato (CC, art. 1.848)",
        ],
    },

    # =================================================== PROCURAÇÕES

    {
        "codigo": "NT-PROC-PUBLICA",
        "tipo": "PROCURACAO",
        "natureza": "Procuração",
        "tipo_ato_cep": 2,
        "fundamentacao": ("CC, arts. 653 a 692, com destaque para o art. 661, "
                          "§ 1º; CN/TJMA, arts. 831 a 833"),
        "requisitos": COMUNS_PROCURACAO,
    },

    {
        "codigo": "NT-PROC-CAUSA-PROPRIA",
        "tipo": "PROCURACAO",
        "natureza": "Procuração em causa própria",
        "tipo_ato_cep": 2,
        "fundamentacao": ("CC, arts. 481 e seguintes e 685; CN/TJMA, arts. 834 e 835"),
        "requisitos": COMUNS_PROCURACAO + [
            "A procuracao em causa propria e ato unilateral e NAO RECEPTICIO "
            "(CN, art. 834)",
            "Incluida operacao onerosa, ela se rege pelas normas da compra e "
            "venda e exige a coisa, o preco e o consentimento (CN, art. 834, "
            "paragrafo unico; CC, art. 481)",
            "Nao se extingue pela morte de qualquer das partes e nao admite "
            "revogacao (CC, art. 685)",
            "Havendo transmissao onerosa de imovel, exigir o ITBI e a DOI: o "
            "ato produz efeito de alienacao",
        ],
    },

    {
        "codigo": "NT-SUBSTABELECIMENTO",
        "tipo": "SUBSTABELECIMENTO",
        "natureza": "Substabelecimento",
        "tipo_ato_cep": 7,
        "fundamentacao": "CC, arts. 655 e 667, §§ 1º a 4º; CN/TJMA, art. 831",
        "requisitos": [
            "Identificacao completa do mandato substabelecido: livro, folha, "
            "data e serventia",
            "O substabelecimento de mandato lavrado por instrumento publico se "
            "faz por instrumento publico (CC, art. 655)",
            "Declarar se e COM ou SEM reserva de poderes — a diferenca define "
            "quem responde pelos atos do substabelecido (CC, art. 667)",
            "Os poderes substabelecidos nao podem exceder os do mandato "
            "original",
            "Sendo o mandato lavrado nesta serventia, anotar imediatamente a "
            "margem do ato originario, sem onus e sem selo (CN, art. 831); "
            "sendo de outra, comunicar ao tabeliao que o lavrou, com "
            "comprovante de recebimento (CN, art. 831, § 1º)",
        ],
    },

    {
        "codigo": "NT-REVOGACAO-MANDATO",
        "tipo": "REVOGACAO_PROCURACAO",
        "natureza": "Revogação de procuração",
        "tipo_ato_cep": 6,
        "fundamentacao": "CC, arts. 682, I, 683, 686 e 687; CN/TJMA, arts. 831 e 832",
        "requisitos": [
            "Identificacao completa do mandato revogado: livro, folha, data, "
            "serventia e CNS — a CENSEC exige esses dados como 'referentes'",
            "O ato pode ser lavrado SEM a presenca do mandatario, devendo o "
            "outorgante ser alertado de que a notificacao e imprescindivel e de "
            "que responde por perdas e danos havendo clausula de "
            "irrevogabilidade (CN, art. 831, § 2º; CC, art. 683)",
            "A revogacao so produz efeito perante terceiros de boa-fe depois de "
            "conhecida (CC, art. 686)",
            "Sendo o mandato lavrado nesta serventia, anotar imediatamente a "
            "margem do ato originario, sem onus e sem selo (CN, art. 831); "
            "sendo de outra, comunicar ao tabeliao que o lavrou (§ 1º)",
            "Nao se revoga por este ato a procuracao em causa propria nem a que "
            "contenha clausula de irrevogabilidade nas hipoteses do art. 684 do "
            "Codigo Civil",
        ],
    },

    {
        "codigo": "NT-RENUNCIA-MANDATO",
        "tipo": "RENUNCIA_PROCURACAO",
        "natureza": "Renúncia de procuração",
        "tipo_ato_cep": 5,
        "fundamentacao": "CC, arts. 682, I, e 688; CN/TJMA, arts. 831 e 832",
        "requisitos": [
            "Identificacao completa do mandato renunciado: livro, folha, data, "
            "serventia e CNS",
            "A renuncia deve ser comunicada ao mandante; o renunciante responde "
            "pelos prejuizos da renuncia intempestiva, salvo provando que nao "
            "podia continuar sem prejuizo proprio (CC, art. 688)",
            "Cabe renuncia dos poderes substabelecidos mesmo no "
            "substabelecimento sem reserva (CN, art. 831, § 4º)",
            "Anotar a margem do ato originario, ou comunicar a serventia de "
            "origem (CN, art. 831 e § 1º)",
        ],
    },

    # =================================================== ATAS NOTARIAIS

    {
        "codigo": "NT-ATA-NOTARIAL",
        "tipo": "ATA_NOTARIAL",
        "natureza": "Ata notarial",
        "tipo_ato_cep": 8,
        "fundamentacao": ("Lei 8.935/1994, art. 7º, III; CPC, art. 384; "
                          "CN/TJMA, arts. 846 e 847"),
        "requisitos": [
            "Local, data da lavratura e HORA (CN, art. 847, § 1º, I)",
            "Nome e qualificacao do solicitante (II)",
            "Narracao circunstanciada dos fatos, objetiva, em livro proprio "
            "(caput e III)",
            "Declaracao de haver sido lida ao solicitante e, sendo o caso, as "
            "testemunhas (IV)",
            "Assinatura do solicitante ou de alguem a seu rogo e, sendo o caso, "
            "das testemunhas (V); recusando-se a assinar, anotar a "
            "circunstancia no campo da assinatura (§ 2º)",
            "Assinatura e sinal publico do tabeliao (VI)",
            "Referindo-se a documento, TRANSCREVER o teor integralmente, ou "
            "inserir a imagem diretamente no livro (§ 4º)",
            "Copia arquivada em ordem cronologica, em pasta especial (§ 3º); "
            "documentos anexos numerados sequencialmente (§ 5º)",
            "A diligencia respeita os limites da circunscricao da delegacao "
            "(art. 846, paragrafo unico, III)",
            "O tabeliao narra o que percebeu com os proprios sentidos; NAO "
            "emite juizo de valor nem conclusao juridica sobre o fato",
        ],
    },

    {
        "codigo": "NT-ATA-USUCAPIAO",
        "tipo": "ATA_USUCAPIAO",
        "natureza": "Ata notarial de usucapião",
        "tipo_ato_cep": 9,
        "fundamentacao": ("Lei 6.015/1973, art. 216-A; CPC, art. 384; "
                          "CN/TJMA, arts. 846, parágrafo único, V, e 847"),
        "requisitos": [
            "Todos os requisitos do art. 847, § 1º, do Codigo de Normas",
            "Atestacao do TEMPO DE POSSE do requerente E DE SEUS ANTECESSORES, "
            "conforme o caso e as circunstancias (CN, art. 846, paragrafo "
            "unico, V)",
            "A ata ATESTA O TEMPO DE POSSE; nao declara a propriedade nem "
            "reconhece a usucapiao — quem decide o registro e o registrador "
            "de imoveis (Lei 6.015/73, art. 216-A)",
            "Identificacao da modalidade de usucapiao pretendida e do prazo "
            "correspondente",
            "Descricao do imovel com planta e memorial descritivo assinados por "
            "profissional habilitado, com ART ou RRT, e pelos titulares de "
            "direitos registrados",
            "Indicacao dos confrontantes e da matricula, se houver",
            "Justo titulo ou quaisquer documentos que demonstrem a origem, a "
            "continuidade, a natureza e o tempo da posse",
            "Certidoes negativas dos distribuidores da comarca da situacao do "
            "imovel e do domicilio do requerente",
        ],
    },

    {
        "codigo": "NT-ATA-ADJUDICACAO",
        "tipo": "ATA_NOTARIAL",
        "natureza": "Ata notarial",
        "tipo_ato_cep": 8,
        "fundamentacao": ("Lei 6.015/1973, art. 216-B; CN/TJMA, art. 848"),
        "requisitos": [
            "Qualificacao completa do requerente, promitente comprador ou "
            "cessionario (CN, art. 848, § 1º, I)",
            "Identificacao do imovel conforme a matricula e o cadastro "
            "imobiliario (II)",
            "Prova da existencia do contrato de promessa de compra e venda ou "
            "de cessao, E DE SUA QUITACAO (III)",
            "Prova da NOTIFICACAO do promitente vendedor para outorga da "
            "escritura, E DE SUA INERCIA (IV)",
            "Certidao de inexistencia de litigio judicial ou arbitral "
            "envolvendo o contrato ou o imovel (V)",
            "A ata atesta o preenchimento dos requisitos e serve de titulo "
            "habil para ingresso no Registro de Imoveis, independentemente de "
            "homologacao judicial (§ 2º)",
            "Comprovacao do ITBI: a adjudicacao transmite a propriedade",
        ],
    },

    # A PROCURAÇÃO PARA FINS PREVIDENCIÁRIOS — LG04, 19/10/2026. O tipo de ato
    # existia desde 15/10 (`notas_schema.TIPOS_ATO`, CEP tipo 3), e a minuta
    # não: quem lavrava partia da procuração comum e o ato saía PROCURACAO, com
    # o tipo errado na CEP. A regra que pesa é a do art. 109 da Lei 8.213/1991
    # — o mandato do INSS não passa de doze meses, renovável —, e por isso a
    # minuta pede a data de validade em vez de oferecer o «prazo indeterminado».
    {
        "codigo": "NT-PROC-PREVIDENCIARIA",
        "tipo": "PROCURACAO_PREVIDENCIARIA",
        "natureza": "Procuração para fins previdenciários",
        "tipo_ato_cep": 3,
        "fundamentacao": ("Lei 8.213/1991, art. 109; CC, arts. 653 a 692; "
                          "CN/TJMA, arts. 831 a 833 (conferir no texto oficial "
                          "a gratuidade e o termo de responsabilidade do INSS)"),
        "requisitos": COMUNS_PROCURACAO + [
            "O beneficio so se paga a procurador em caso de AUSENCIA, MOLESTIA "
            "CONTAGIOSA ou IMPOSSIBILIDADE DE LOCOMOCAO do segurado — o motivo "
            "vai escrito no ato (Lei 8.213/1991, art. 109)",
            "Mandato com prazo NAO SUPERIOR A DOZE MESES, podendo ser renovado "
            "(Lei 8.213/1991, art. 109): sem prazo indeterminado",
            "O procurador assina no INSS o termo de responsabilidade; o ato "
            "diz que ele tem poder para isso",
            "Selo pelo caminho do INSS (/selo/notas/procuracao/inss) ou pelos "
            "tres da procuracao; isencao so com o motivo escrito",
            "Vai a CEP da CENSEC como «Procuracao para fins previdenciarios» "
            "(tipo 3), e nao como procuracao comum",
        ],
    },

    # =================================================== TESTAMENTO

    {
        "codigo": "NT-TESTAMENTO-PUBLICO",
        "tipo": "TESTAMENTO",
        "natureza": "Testamento",
        "tipo_testamento": 4,
        "fundamentacao": ("CC, arts. 1.857 a 1.867, 1.846 a 1.849 e 1.900 a 1.911; "
                          "Lei 8.935/1994, art. 7º; Provimento CNJ 149/2023"),
        "requisitos": [
            "REQUISITO ESSENCIAL — ser escrito pelo tabeliao ou seu substituto "
            "legal em seu livro de notas, de acordo com as declaracoes do "
            "testador, que pode servir-se de minuta, notas ou apontamentos "
            "(CC, art. 1.864, I)",
            "REQUISITO ESSENCIAL — lavrado o instrumento, ser LIDO EM VOZ ALTA "
            "pelo tabeliao ao testador E A DUAS TESTEMUNHAS, A UM SO TEMPO; ou "
            "pelo testador, se o quiser, na presenca destas e do oficial "
            "(CC, art. 1.864, II)",
            "REQUISITO ESSENCIAL — em seguida a leitura, ser assinado pelo "
            "testador, PELAS TESTEMUNHAS e pelo tabeliao (CC, art. 1.864, III)",
            "DUAS testemunhas, presentes ao ato inteiro, capazes e nao "
            "impedidas — nao podem ser herdeiro, legatario, seus conjuges, "
            "ascendentes, descendentes e irmaos (CC, arts. 228 e 1.801)",
            "Testador maior de dezesseis anos e em pleno discernimento "
            "(CC, arts. 1.860 e 1.861); a capacidade se afere NO MOMENTO DA "
            "LAVRATURA",
            "Nao sabendo ou nao podendo o testador assinar, o tabeliao o "
            "declara e assina por ele, a seu rogo, UMA DAS TESTEMUNHAS "
            "INSTRUMENTARIAS (CC, art. 1.865)",
            "AO CEGO so se permite o testamento publico, LIDO EM VOZ ALTA DUAS "
            "VEZES, uma pelo tabeliao e outra por testemunha designada pelo "
            "testador, com mencao circunstanciada de tudo (CC, art. 1.867)",
            "Surdo que saiba ler, le o proprio testamento; nao sabendo, designa "
            "quem o leia, na presenca das testemunhas (CC, art. 1.866)",
            "Havendo herdeiro necessario, a LEGITIMA e a metade dos bens da "
            "heranca e nao pode ser tocada; o testamento so dispoe da outra "
            "metade (CC, arts. 1.789, 1.846 e 1.857, § 1º)",
            "Clausula de inalienabilidade, impenhorabilidade ou "
            "incomunicabilidade sobre a LEGITIMA exige JUSTA CAUSA declarada no "
            "proprio testamento; sem ela, a clausula nao vale (CC, art. 1.848)",
            "Deserdacao de herdeiro necessario so por testamento, com "
            "declaracao expressa da causa (CC, arts. 1.964 e 1.965)",
            "Nao vale disposicao em favor de quem escreveu o testamento a rogo "
            "nem do tabeliao, seu conjuge ou parentes (CC, art. 1.801, I e III)",
            "Remessa obrigatoria ao RCTO da CENSEC na quinzena da lavratura",
            "O testamento NAO se informa a CEP — so ao RCTO",
        ],
    },

    # O TESTAMENTO CERRADO — LG04, 19/10/2026. O tipo de ato e o livro existiam
    # (`notas_schema`: «Testamento cerrado — auto de aprovação», «Livro de
    # Registro de Testamentos Cerrados») e a minuta não. **O TABELIÃO NÃO
    # ESCREVE O TESTAMENTO, APROVA-O**: o que entra no livro é o auto e a nota
    # da aprovação e da entrega (CC, arts. 1.869 e 1.874), e o conteúdo fica
    # cerrado com o testador — por isso a minuta não tem disposição nenhuma.
    {
        "codigo": "NT-TESTAMENTO-CERRADO",
        "tipo": "TESTAMENTO_CERRADO",
        "natureza": "Testamento cerrado",
        "tipo_testamento": 2,
        "fundamentacao": ("CC, arts. 1.868 a 1.875; Lei 8.935/1994, art. 7º, II; "
                          "CN/TJMA, arts. 777, VII, 778, II, 785, I, 788, II, "
                          "e 851, §§ 4º e 5º"),
        "requisitos": [
            "O testamento e ESCRITO pelo testador, ou por outra pessoa a seu "
            "rogo, e ASSINADO pelo testador (CC, art. 1.868, caput)",
            "Entregue pelo testador ao tabeliao NA PRESENCA DE DUAS "
            "TESTEMUNHAS, declarando que aquele e o seu testamento e que quer "
            "que seja aprovado (CC, art. 1.868, I e II)",
            "O auto de aprovacao comeca IMEDIATAMENTE DEPOIS DA ULTIMA PALAVRA "
            "do testador; sem espaco na ultima folha, o tabeliao apoe o sinal "
            "publico e menciona a circunstancia (CC, art. 1.869)",
            "O auto e LIDO ao testador e as testemunhas e assinado pelo "
            "tabeliao, pelas testemunhas e pelo testador (CC, art. 1.868, III "
            "e IV)",
            "O tabeliao NAO le o conteudo nem o guarda: o instrumento e cerrado "
            "e cosido e entregue ao testador (CC, arts. 1.869 e 1.874)",
            "Nao pode testar em cerrado quem nao saiba ou nao possa ler "
            "(CC, art. 1.872); o surdo-mudo pode, escrevendo na face externa "
            "que aquele e o seu testamento (CC, art. 1.873)",
            "No livro, a NOTA do lugar, dia, mes e ano da aprovacao e da "
            "entrega (CC, art. 1.874)",
            "Remessa obrigatoria ao RCTO da CENSEC, tipo «Cerrado» "
            "(CN, art. 785, I)",
            "Certidao so ao testador, por requerimento escrito, ou a qualquer "
            "pessoa com a certidao de obito (CN, art. 851, §§ 4º e 5º)",
        ],
    },

    # =================================================== SUCESSÕES

    {
        "codigo": "NT-ESC-CESSAO-HEREDITARIA",
        "tipo": "ESCRITURA",
        "natureza": "Cessão de direitos hereditários",
        "natureza_censec": 5,
        "tipo_ato_cep": 1,
        "fundamentacao": ("CC, arts. 1.793 a 1.795, 1.805, 1.647, 1.649 e 2.013; "
                          "CN/TJMA, arts. 803 a 805"),
        "requisitos": COMUNS_ESCRITURA + [
            "CIENTIFICAR O ADQUIRENTE, E CONSIGNAR NO ATO, que a cessao "
            "compreende nao so o quinhao ou a quota ideal atribuivel ao cedente "
            "nos bens, MAS TAMBEM, PROPORCIONALMENTE, AS DIVIDAS DO ESPOLIO ate "
            "o limite das forcas da heranca (CN, art. 803)",
            "Recolhimento do imposto de transmissao, havendo previsao legal de "
            "exacao (CN, art. 804)",
            "IMPRESCINDIVEL a ciencia dos demais coerdeiros, com especificacao "
            "de valor, forma de pagamento e demais condicoes oferecidas a "
            "terceiro — e o direito de preferencia do art. 1.795 do Codigo "
            "Civil (CN, art. 804, caput e § 1º)",
            "OUTORGA UXORIA no proprio ato, salvo separacao total convencional "
            "ou participacao final nos aquestos com dispensa em pacto; a falta "
            "torna a cessao ANULAVEL por ate dois anos apos a extincao da "
            "sociedade conjugal (CN, art. 804, §§ 4º e 5º; CC, arts. 1.647, I, "
            "e 1.649)",
            "Renuncia da heranca EM FAVOR DE OUTRO HERDEIRO equivale a cessao; "
            "cessao gratuita pura e simples em favor de todos os herdeiros e "
            "renuncia abdicativa em favor do monte (CN, art. 804, § 6º; CC, "
            "art. 1.805, § 2º)",
            "Sendo cessao de BEM INDIVIDUALIZADO, o titulo NAO INGRESSA no "
            "Registro de Imoveis ate que se faca a partilha, e os quinhoes "
            "ideais se expressam em fracao decimal, ordinaria ou equivalencia "
            "em medida de superficie, VEDADA a especificacao em valor "
            "pecuniario (CN, art. 805 e paragrafo unico)",
        ],
    },

    {
        "codigo": "NT-ESC-INVENTARIO-PARTILHA",
        "tipo": "ESCRITURA",
        "natureza": "Inventário e partilha",
        "tipo_cesdi": 5,
        "fundamentacao": ("CPC, arts. 610 e 733; Lei 11.441/2007; Resolução CNJ "
                          "35/2007, arts. 20 a 25; CN/TJMA, arts. 806 a 813 e 821"),
        "requisitos": COMUNS_SUCESSAO,
    },

    {
        "codigo": "NT-ESC-SOBREPARTILHA",
        "tipo": "ESCRITURA",
        "natureza": "Sobrepartilha",
        "tipo_cesdi": 6,
        "fundamentacao": ("CPC, arts. 669 e 670; Resolução CNJ 35/2007, art. 25; "
                          "CN/TJMA, arts. 813 a 821"),
        "requisitos": COMUNS_SUCESSAO + [
            "Cabe sobrepartilha por escritura AINDA QUE o inventario e a "
            "partilha tenham sido judiciais e ja findos, e MESMO QUE o herdeiro, "
            "hoje maior e capaz, fosse menor ou incapaz ao tempo do obito ou do "
            "processo judicial (CN, art. 813)",
            "Identificar o inventario anterior: se judicial, o processo e o "
            "juizo; se extrajudicial, o livro, folha, data e serventia",
        ],
    },

    {
        "codigo": "NT-ESC-PARTILHA-ADJUDICACAO",
        "tipo": "ESCRITURA",
        "natureza": "Partilha",
        "tipo_cesdi": 9,
        "fundamentacao": ("CPC, arts. 659 e 660; Resolução CNJ 35/2007; "
                          "CN/TJMA, arts. 814 a 821"),
        "requisitos": COMUNS_SUCESSAO + [
            "Havendo HERDEIRO UNICO, o ato e de ADJUDICACAO, e nao de partilha "
            "(CN, art. 814)",
            "A renuncia de herdeiro pode constar da propria escritura; "
            "comprovada em declaracao anterior, judicial ou por escritura "
            "publica, DISPENSA A PRESENCA do renunciante (CN, art. 815)",
            "Havendo direito de representacao ou herdeiro de classe posterior "
            "na ordem de vocacao, exigir certidao de obito do representado e "
            "dos herdeiros premortos (CN, art. 816)",
            "Avaliacao dos bens e recolhimento do imposto de transmissao, "
            "PREVIAMENTE (CN, art. 819, paragrafo unico)",
        ],
    },

    {
        "codigo": "NT-ESC-NOMEACAO-INVENTARIANTE",
        "tipo": "ESCRITURA",
        "natureza": "Nomeação de inventariante",
        "tipo_cesdi": 8,
        "fundamentacao": "CPC, arts. 617 e 618; CN/TJMA, art. 810",
        "requisitos": [
            ADVOGADO_OBRIGATORIO,
            "Certidao de obito do autor da heranca",
            "Serve para representar o espolio perante estabelecimentos "
            "bancarios e instituicoes fiscais, e para viabilizar a "
            "transferencia de titularidade de conta bancaria, ANTES da "
            "escritura definitiva de partilha (CN, art. 810)",
            "NAO substitui o inventario nem transfere bens: e ato de "
            "representacao e de declaracao",
            "Qualificacao completa do meeiro e de todos os herdeiros",
        ],
    },

    # =================================================== FAMÍLIA

    {
        "codigo": "NT-ESC-DIVORCIO",
        "tipo": "ESCRITURA",
        "natureza": "Divórcio consensual",
        "tipo_cesdi": 4,
        "fundamentacao": ("CF, art. 226, § 6º, com a redação da EC 66/2010; CPC, "
                          "art. 733; Lei 11.441/2007; Resolução CNJ 35/2007; "
                          "CN/TJMA, arts. 822, 826 e 827"),
        "requisitos": COMUNS_FAMILIA + [
            "Constam da escritura as disposicoes sobre a DESCRICAO E A PARTILHA "
            "dos bens comuns, a PENSAO ALIMENTICIA entre os conjuges e a "
            "ALTERACAO OU MANUTENCAO DO NOME (CN, art. 822, caput; CPC, art. 733)",
            "Havendo partilha de imovel, o recolhimento do imposto de "
            "transmissao quando a divisao for desigual",
        ],
    },

    {
        "codigo": "NT-ESC-SEPARACAO",
        "tipo": "ESCRITURA",
        "natureza": "Separação consensual",
        "tipo_cesdi": 1,
        "fundamentacao": ("CC, arts. 1.571 a 1.578; CPC, art. 733; Resolução CNJ "
                          "35/2007; CN/TJMA, arts. 822 a 825"),
        "requisitos": COMUNS_FAMILIA + [
            "Manifestacao da vontade espontanea e isenta de vicios em NAO MAIS "
            "MANTER A SOCIEDADE CONJUGAL e desejar a separacao conforme as "
            "clausulas ajustadas (CN, art. 823, I)",
            "Ausencia de filhos menores nao emancipados ou incapazes do casal "
            "(CN, art. 823, II) — observada a ressalva do art. 822, § 1º",
            "A separacao dissolve a SOCIEDADE conjugal, nao o VINCULO: os "
            "separados nao podem casar novamente ate a conversao em divorcio",
        ],
    },

    {
        "codigo": "NT-ESC-CONVERSAO-DIVORCIO",
        "tipo": "ESCRITURA",
        "natureza": "Conversão de separação em divórcio",
        "tipo_cesdi": 3,
        "fundamentacao": ("CF, art. 226, § 6º; Resolução CNJ 35/2007, art. 52; "
                          "CN/TJMA, arts. 822, § 2º, 826, 827 e 830"),
        "requisitos": COMUNS_FAMILIA + [
            "E DISPENSAVEL a certidao atualizada do processo judicial: basta a "
            "CERTIDAO DA AVERBACAO DA SEPARACAO no assento do casamento "
            "(CN, art. 830; Resolucao CNJ 35/2007, art. 52)",
            "Cabe a conversao com ou sem partilha de bens MESMO HAVENDO filhos "
            "incapazes ou nascituros, DESDE QUE nao haja nenhuma alteracao do "
            "que foi convencionado e homologado na separacao quanto aos "
            "direitos desses filhos (CN, art. 822, § 2º)",
            "As condicoes da separacao podem ser mantidas ou alteradas "
            "(CN, art. 830)",
        ],
    },

    {
        "codigo": "NT-ESC-RESTABELECIMENTO",
        "tipo": "ESCRITURA",
        "natureza": "Restabelecimento da sociedade conjugal",
        "tipo_cesdi": 2,
        "fundamentacao": ("CC, art. 1.577; Resolução CNJ 35/2007, arts. 49 e 51; "
                          "CN/TJMA, arts. 828 e 829"),
        "requisitos": [
            ADVOGADO_OBRIGATORIO,
            "E NECESSARIA E SUFICIENTE a certidao da sentenca de separacao ou "
            "da averbacao da separacao no assento de casamento (CN, art. 828)",
            "A averbacao do restabelecimento so se efetiva DEPOIS da averbacao "
            "da separacao no registro civil, podendo ser simultaneas "
            "(CN, art. 828, paragrafo unico)",
            "FAZER CONSTAR no ato que as partes foram orientadas sobre a "
            "necessidade de apresentar o traslado no registro civil do assento "
            "de casamento (CN, art. 829, I)",
            "ANOTAR o restabelecimento a margem da escritura de separacao "
            "consensual, sendo desta serventia; sendo de outra, COMUNICAR para "
            "a anotacao (CN, art. 829, II)",
            "COMUNICAR o restabelecimento ao juizo da separacao judicial, se "
            "for o caso (CN, art. 829, III)",
            "So se restabelece o que foi SEPARACAO: divorcio dissolve o "
            "vinculo e nao se restabelece — os divorciados casam de novo",
        ],
    },

    {
        "codigo": "NT-ESC-UNIAO-ESTAVEL",
        "tipo": "ESCRITURA",
        "natureza": "Declaratória de união estável",
        "natureza_censec": 15,
        "tipo_ato_cep": 1,
        "fundamentacao": ("CF, art. 226, § 3º; CC, arts. 1.723 a 1.727; "
                          "Provimento CNJ 149/2023"),
        "requisitos": COMUNS_ESCRITURA + [
            "Convivencia publica, continua e duradoura, estabelecida com o "
            "objetivo de constituicao de familia (CC, art. 1.723)",
            "Nao se constitui uniao estavel havendo os impedimentos do art. "
            "1.521 do Codigo Civil, salvo se a pessoa casada se achar separada "
            "de fato ou judicialmente (CC, art. 1.723, § 1º)",
            "Nao havendo contrato escrito, aplica-se o regime da COMUNHAO "
            "PARCIAL de bens (CC, art. 1.725) — o regime diverso deve ser "
            "expresso no ato",
            "Sendo declarado regime diverso da comunhao parcial, a CEP exige o "
            "campo regimeBens",
            "Havendo filhos, declara-los; a declaracao nao supre o registro de "
            "nascimento",
        ],
    },

    {
        "codigo": "NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL",
        "tipo": "ESCRITURA",
        "natureza": "Dissolução de união estável",
        "natureza_censec": 20,
        "tipo_ato_cep": 1,
        "fundamentacao": ("CC, arts. 1.723 a 1.727; CPC, art. 733; "
                          "CN/TJMA, art. 822"),
        "requisitos": COMUNS_ESCRITURA + [
            ADVOGADO_OBRIGATORIO + " (CN, art. 822, § 5º)",
            "A extincao consensual da uniao estavel pode ser feita por "
            "escritura publica quando nao houver interesse de filhos menores, "
            "incapazes ou nascituros, com as disposicoes sobre descricao e "
            "partilha de bens comuns, pensao alimenticia e nome "
            "(CN, art. 822, caput)",
            "Havendo filho incapaz ou nascituro, vale a mesma ressalva do "
            "art. 822, § 1º: nada sobre guarda, visitacao e alimentos, e o "
            "compromisso expresso de levar essas questoes ao Judiciario",
            "A dissolucao NAO se averba em assento de casamento; havendo "
            "escritura declaratoria anterior, anota-se a margem dela",
        ],
    },

    # =================================================== GARANTIA E DÍVIDA

    {
        "codigo": "NT-ESC-HIPOTECA",
        "tipo": "ESCRITURA",
        "natureza": "Hipoteca",
        "natureza_censec": 24,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": ("CC, arts. 1.419 a 1.430 e 1.473 a 1.505, com destaque "
                          "para os arts. 1.424, 1.485 e 1.492; CN/TJMA, arts. 798 "
                          "e 800"),
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL + [
            "ESPECIALIZACAO — sob pena de nao valer a garantia, o titulo deve "
            "declarar: o valor total da divida ou sua estimacao; o prazo fixado "
            "para pagamento; a taxa de juros, se houver; e o bem dado em "
            "garantia, com as especificacoes de praxe (CC, art. 1.424)",
            "So pode hipotecar quem pode alienar, e so se hipoteca o que se pode "
            "alienar (CC, art. 1.420)",
            "Outorga do conjuge, salvo separacao absoluta (CC, art. 1.647, I)",
            "A hipoteca vale entre as partes desde a escritura, mas SO VALE "
            "CONTRA TERCEIROS depois de registrada no Registro de Imoveis "
            "(CC, arts. 1.227 e 1.492)",
            "O prazo maximo e de TRINTA ANOS da data do contrato; vencido, so "
            "se restabelece por novo titulo e novo registro (CC, art. 1.485)",
            "E NULA a clausula que autoriza o credor a ficar com o imovel se a "
            "divida nao for paga no vencimento — o pacto comissorio e vedado "
            "(CC, art. 1.428)",
            "Havendo hipoteca anterior, indicar o grau da nova",
        ],
    },

    {
        "codigo": "NT-ESC-ALIENACAO-FIDUCIARIA",
        "tipo": "ESCRITURA",
        "natureza": "Alienação fiduciária",
        "natureza_censec": 4,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": ("Lei 9.514/1997, arts. 22 a 33, com destaque para os "
                          "arts. 24, 26 e 27; CC, arts. 1.361 a 1.368-B; "
                          "CN/TJMA, arts. 798 e 800"),
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL + [
            "O CONTRATO DEVE CONTER, sob pena de nao se constituir a "
            "propriedade fiduciaria (Lei 9.514/1997, art. 24): I o valor do "
            "principal da divida; II o prazo e as condicoes de reposicao do "
            "emprestimo ou do credito do fiduciario; III a taxa de juros e os "
            "encargos incidentes; IV a clausula de constituicao da propriedade "
            "fiduciaria, com a descricao do imovel e a indicacao do titulo e "
            "modo de aquisicao; V a clausula assegurando ao fiduciante a livre "
            "utilizacao do imovel, por sua conta e risco, enquanto adimplente; "
            "VI a indicacao, para efeito de venda em publico leilao, do VALOR "
            "DO IMOVEL e dos criterios para a respectiva revisao; VII a "
            "clausula dispondo sobre os procedimentos dos arts. 26 e 27",
            "A propriedade fiduciaria se constitui com o REGISTRO no Registro "
            "de Imoveis (Lei 9.514/1997, art. 23)",
            "Vencida e nao paga a divida, a consolidacao da propriedade depende "
            "de INTIMACAO do fiduciante para purgar a mora em quinze dias "
            "(art. 26), seguida de DOIS LEILOES (art. 27) — o procedimento nao "
            "e dispensavel por clausula",
            "Outorga do conjuge do fiduciante, salvo separacao absoluta",
        ],
    },

    {
        "codigo": "NT-ESC-CONFISSAO-DACAO",
        "tipo": "ESCRITURA",
        "natureza": "Confissão de dívida ou dação em pagamento",
        "natureza_censec": 10,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": ("CC, arts. 356 a 359, 1.245 e 1.647; CN/TJMA, arts. 798 "
                          "e 800"),
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL + [
            "A dacao exige o CONSENTIMENTO DO CREDOR em receber prestacao "
            "diversa da que lhe e devida (CC, art. 356)",
            "Determinado o preco da coisa dada em pagamento, as relacoes entre "
            "as partes regem-se pelas normas do CONTRATO DE COMPRA E VENDA "
            "(CC, art. 357) — e por isso incide o ITBI",
            "Se o credor for EVICTO da coisa recebida em pagamento, RESTABELECE-"
            "SE a obrigacao primitiva, ficando sem efeito a quitacao dada, "
            "ressalvados os direitos de terceiros (CC, art. 359)",
            "A confissao de divida SEM dacao nao e titulo para o Registro de "
            "Imoveis: e titulo executivo extrajudicial (CPC, art. 784, II e III)",
            "Outorga do conjuge do devedor, havendo imovel",
        ],
    },

    {
        "codigo": "NT-ESC-PERMUTA",
        "tipo": "ESCRITURA",
        "natureza": "Permuta",
        "natureza_censec": 6,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": "CC, arts. 481 a 532 e 533; CN/TJMA, arts. 798 e 800",
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL + [
            "Aplicam-se a permuta as disposicoes da COMPRA E VENDA, com duas "
            "modificacoes (CC, art. 533)",
            "Salvo disposicao em contrario, as DESPESAS DO INSTRUMENTO correm "
            "por conta dos dois contratantes, EM PARTES IGUAIS (CC, art. 533, I)",
            "E ANULAVEL a permuta de valores desiguais entre ASCENDENTE E "
            "DESCENDENTE sem consentimento dos outros descendentes E DO CONJUGE "
            "do alienante (CC, art. 533, II)",
            "ITBI sobre as duas transmissoes, e DOI para cada uma",
            "Havendo torna, declarar o valor e a forma de pagamento",
            "Na CENSEC a permuta e informada na natureza 6, COMPRA E VENDA, que "
            "a contempla expressamente",
        ],
    },

    {
        "codigo": "NT-ESC-QUITACAO",
        "tipo": "ESCRITURA",
        "natureza": "Quitação",
        "natureza_censec": 34,
        "tipo_ato_cep": 1,
        "fundamentacao": "CC, arts. 319 a 324 e 1.500",
        "requisitos": COMUNS_ESCRITURA + [
            "A quitacao designara: o VALOR e a ESPECIE da divida quitada; o "
            "NOME DO DEVEDOR ou de quem por este pagou; o TEMPO e o LUGAR do "
            "pagamento; e a ASSINATURA DO CREDOR ou de seu representante "
            "(CC, art. 320)",
            "Sendo quitacao de divida garantida por hipoteca, serve de titulo "
            "para o CANCELAMENTO do registro (CC, art. 1.500)",
            "Presume-se o pagamento das prestacoes anteriores quando se paga a "
            "ultima, ate prova em contrario (CC, art. 322)",
            "Sendo a quitacao de imovel, conferir se o caso e de quitacao ou de "
            "cancelamento de gravame — sao atos distintos",
        ],
    },

    {
        "codigo": "NT-ESC-DISTRATO",
        "tipo": "ESCRITURA",
        "natureza": "Distrato",
        "natureza_censec": 21,
        "tipo_ato_cep": 1,
        "fundamentacao": "CC, arts. 472 e 473",
        "requisitos": COMUNS_ESCRITURA + [
            "O DISTRATO FAZ-SE PELA MESMA FORMA EXIGIDA PARA O CONTRATO "
            "(CC, art. 472) — contrato por escritura publica se desfaz por "
            "escritura publica",
            "Identificar o contrato desfeito: data, livro, folha e serventia, "
            "ou o instrumento particular e seu registro",
            "Havendo transmissao ja registrada, o distrato produz NOVA "
            "transmissao e pode gerar incidencia de ITBI — conferir com a "
            "Fazenda municipal antes de lavrar",
            "Declarar o que cada parte restitui, e dar quitacao reciproca",
        ],
    },

    # =================================================== PESSOA E FAMÍLIA

    {
        "codigo": "NT-ESC-EMANCIPACAO",
        "tipo": "ESCRITURA",
        "natureza": "Emancipação",
        "natureza_censec": 23,
        "tipo_ato_cep": 1,
        "fundamentacao": ("CC, art. 5º, parágrafo único, I; Lei 6.015/1973, "
                          "arts. 89, 90 e 91"),
        "requisitos": COMUNS_ESCRITURA + [
            "Menor com DEZESSEIS ANOS COMPLETOS — abaixo disso a emancipacao "
            "voluntaria nao cabe (CC, art. 5º, paragrafo unico, I)",
            "Concessao pelos DOIS PAIS, ou por um deles NA FALTA DO OUTRO; "
            "havendo divergencia, a via e judicial",
            "Independe de homologacao judicial (CC, art. 5º, paragrafo unico, I)",
            "Certidao de nascimento do menor, para conferir a idade e a "
            "filiacao",
            "A emancipacao SO PRODUZ EFEITO depois do REGISTRO no Registro "
            "Civil das Pessoas Naturais do domicilio do emancipado, no Livro E, "
            "e da anotacao no assento de nascimento (Lei 6.015/1973, arts. 89, "
            "90 e 91) — advertir as partes disso no ato",
            "O menor deve comparecer e ser ouvido",
        ],
    },

    {
        "codigo": "NT-ESC-PACTO-ANTENUPCIAL",
        "tipo": "ESCRITURA",
        "natureza": "Pacto antenupcial",
        "natureza_censec": 30,
        "tipo_ato_cep": 1,
        "fundamentacao": ("CC, arts. 1.639 a 1.657, com destaque para os arts. "
                          "1.653, 1.655 e 1.657"),
        "requisitos": COMUNS_ESCRITURA + [
            "E NULO o pacto antenupcial que nao for feito por escritura "
            "publica, e INEFICAZ se nao lhe seguir o casamento (CC, art. 1.653)",
            "E NULA a convencao ou clausula que contravenha disposicao absoluta "
            "de lei (CC, art. 1.655)",
            "So produz efeito PERANTE TERCEIROS depois de REGISTRADO em livro "
            "especial no Registro de Imoveis do DOMICILIO DOS CONJUGES "
            "(CC, art. 1.657) — advertir as partes disso no ato",
            "Sendo o regime o de PARTICIPACAO FINAL NOS AQUESTOS, pode-se "
            "convencionar a livre disposicao dos imoveis particulares "
            "(CC, art. 1.656)",
            "Sendo caso de SEPARACAO OBRIGATORIA de bens (CC, art. 1.641), o "
            "pacto nao pode afastar o regime imposto por lei",
            "O pacto e ANTEnupcial: lavrado antes do casamento",
        ],
    },

    {
        "codigo": "NT-ESC-DIRETIVAS-VONTADE",
        "tipo": "ESCRITURA",
        "natureza": "Diretivas antecipadas de vontade",
        "natureza_censec": 55,
        "tipo_ato_cep": 1,
        "fundamentacao": ("CF, art. 5º, III; CC, art. 15; Resolução CFM 1.995/2012; "
                          "CN/TJMA, arts. 876 a 880"),
        "requisitos": COMUNS_ESCRITURA + [
            "Declarante CAPAZ, no exercicio de sua autonomia, expressando "
            "diretrizes sobre os cuidados e tratamentos de saude que deseja, ou "
            "nao, receber quando estiver incapacitado de expressar-se de forma "
            "livre e autonoma (CN, art. 876)",
            "Pode, FACULTATIVAMENTE, nomear PROCURADOR DE SAUDE para "
            "representa-lo perante medicos e instituicoes de saude, com o fim "
            "especifico de dar fiel cumprimento as diretrizes (CN, art. 877)",
            "A nomeacao do procurador de saude E PARTE INTEGRANTE do ato de "
            "disposicao de vontade sobre o corpo e NAO ENSEJA EMOLUMENTOS "
            "ADICIONAIS (CN, art. 878)",
            "Se o declarante quiser, no mesmo instrumento, outorgar mandato "
            "para administracao patrimonial ou outros negocios (Mandato "
            "Duradouro), esse e NEGOCIO JURIDICO DISTINTO E AUTONOMO e enseja "
            "os emolumentos do ato de procuracao (CN, art. 879)",
            "COMUNICACAO OBRIGATORIA, GRATUITA E SIGILOSA a CENSEC, no modulo "
            "Registro Central de Disposicoes de Ultima Vontade (RCDUV) — "
            "CN, art. 880",
            "O tabeliao NAO avalia o merito medico das diretrizes: colhe a "
            "declaracao de vontade de pessoa capaz",
        ],
    },

    {
        "codigo": "NT-ESC-USUFRUTO",
        "tipo": "ESCRITURA",
        "natureza": "Usufruto",
        "natureza_censec": 46,
        "tipo_ato_cep": 1,
        "com_imovel": 1,
        "fundamentacao": ("CC, arts. 1.390 a 1.411, com destaque para os arts. "
                          "1.393, 1.410 e 1.411; CN/TJMA, arts. 798 e 800"),
        "requisitos": COMUNS_ESCRITURA + COMUNS_IMOVEL + [
            "O usufruto de imovel constitui-se com o REGISTRO no Registro de "
            "Imoveis (CC, art. 1.391)",
            "O usufruto NAO SE TRANSFERE por alienacao; so o seu EXERCICIO pode "
            "ser cedido, a titulo gratuito ou oneroso (CC, art. 1.393)",
            "Constituido em favor de PESSOA JURIDICA, extingue-se com ela ou em "
            "TRINTA ANOS da data em que comecou a exercer (CC, art. 1.410, III)",
            "Constituido em favor de duas ou mais pessoas, extingue-se parte a "
            "parte em relacao a cada uma que falecer, SALVO se houver "
            "estipulacao expressa de acrescimo ao sobrevivente (CC, art. 1.411)",
            "A renuncia do usufruto e ato do usufrutuario, e extingue o direito "
            "com a AVERBACAO ou o CANCELAMENTO no registro (CC, art. 1.410, I)",
            "Havendo reserva na doacao, o usufruto e objeto de REGISTRO PROPRIO, "
            "distinto do registro da doacao",
            "Na CENSEC, a natureza 46 contempla reserva, instituicao E renuncia",
        ],
    },
]


# ----------------------------------------------------------------- carga

def instalar(con, agora: str) -> dict:
    """Poe os modelos no banco, sem atropelar o que a serventia escreveu.

    REPETIVEL POR CONSTRUCAO, COMO O RESTO DO PROJETO
        Entram com origem 'SISTEMA', que e o que o indice unico parcial
        `ux_nt_modelos_origem` cobre. Rodar duas vezes nao duplica.

        O modelo que a serventia editar a mao passa a valer, e o ON CONFLICT
        DO NOTHING nao o desfaz: o texto de quem lavra ganha do texto de fabrica.

    E O QUE JA ESTAVA INSTALADO SE ATUALIZA SOZINHO, SE NINGUEM O EDITOU —
    achado em 07/09/2026, ao ajustar o modelo da escritura ao padrao da
    minuta: a linha de `NT-ESC-COMPRA-VENDA-RURAL` tinha entrado em
    17/08/2026, e o `ON CONFLICT DO NOTHING` a deixou parada ali, com o texto
    ANTIGO, enquanto o codigo ja tinha o novo — porque esta funcao so roda
    dentro da carga do acervo, e o oficial nao ia reimportar o acervo so
    para pegar um modelo mais novo. Ninguem tinha editado a linha — nao ha
    tela para isso ainda —, e mesmo assim ela ficou presa no texto de
    fabrica de um mes atras.

    `atualizado_em` e a marca de que uma tela gravou por cima: enquanto ela
    for NULL, a linha ainda e o que o SISTEMA escreveu, e o codigo pode
    corrigi-la. No dia em que existir uma tela para o oficial editar o
    modelo, ela tem de gravar essa coluna — e a partir dai esta funcao para
    de tocar na linha, exatamente como ja faz hoje com o que ela supoe
    editado.
    """
    resultado = {"novos": 0, "ja_existentes": 0, "atualizados": 0}
    bd = banco(con)
    for m in minutas():
        novo = bd.escrever(
            """INSERT INTO nt_modelos
               (codigo, tipo, nome, nome_norm, corpo, fundamento,
                central_censec, natureza_censec, tipo_ato_censec,
                tipo_cesdi, tipo_testamento, com_imovel, ativo,
                origem, origem_chave, criado_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'SISTEMA',%s,%s)
               ON CONFLICT DO NOTHING RETURNING id""",
            (m["codigo"], m["tipo"], m["nome"],
             _norm_nome(m["nome"]), m["corpo"], m.get("fundamentacao"),
             "RCTO" if m.get("tipo_testamento") else
             ("CESDI" if m.get("tipo_cesdi") else "CEP"),
             m.get("natureza_censec"), m.get("tipo_ato_cep"),
             m.get("tipo_cesdi"), m.get("tipo_testamento"),
             m.get("com_imovel", 0), m["codigo"], agora))
        if novo:
            resultado["novos"] += 1
            continue
        linha = bd.um(
            "SELECT corpo, fundamento, atualizado_em FROM nt_modelos "
            "WHERE codigo = %s AND origem = 'SISTEMA'", (m["codigo"],))
        corpo_gravado, fundamento_gravado, editado_em = (
            linha["corpo"], linha["fundamento"], linha["atualizado_em"])
        if editado_em is not None:
            resultado["ja_existentes"] += 1     # a serventia editou — intocado
            continue
        if corpo_gravado == m["corpo"] and \
                (fundamento_gravado or None) == (m.get("fundamentacao") or None):
            resultado["ja_existentes"] += 1     # já está no que o código diz
            continue
        bd.escrever(
            "UPDATE nt_modelos SET corpo = %s, fundamento = %s WHERE codigo = %s",
            (m["corpo"], m.get("fundamentacao"), m["codigo"]))
        resultado["atualizados"] += 1
    return resultado


def _norm_nome(texto: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto or "").upper())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


# ------------------------------------------------------------- utilidades

def minutas() -> list[dict]:
    """As minutas de fábrica, inteiras — o que é do código mais o nome e o
    corpo, LIDOS DA BASE (LF06D). Só lê. Na ordem desta lista."""
    import modelos_da_casa as MODELOS_DA_CASA
    saida = []
    for m in MINUTAS:
        de_fabrica = MODELOS_DA_CASA.minuta_de_fabrica(m["codigo"])
        saida.append({**m, "nome": de_fabrica["nome"], "corpo": de_fabrica["corpo"]})
    return saida


def por_codigo(codigo: str) -> dict | None:
    for m in MINUTAS:
        if m["codigo"] == codigo:
            import modelos_da_casa as MODELOS_DA_CASA
            de_fabrica = MODELOS_DA_CASA.minuta_de_fabrica(codigo)
            return {**m, "nome": de_fabrica["nome"], "corpo": de_fabrica["corpo"]}
    return None


def por_tipo(tipo: str) -> list[dict]:
    return [m for m in minutas() if m["tipo"] == tipo]


# Um espaco antes de pontuacao, dois espacos seguidos, ou espaco logo depois de
# abrir tag: o que sobra quando uma clausula condicional sai do texto.
_SOBRAS = (
    (re.compile(r"[ \t]*\n[ \t]*"), " "),      # nao existe quebra em ato corrido
    (re.compile(r"\s{2,}"), " "),              # nem espaco duplo
    (re.compile(r"\s+([,.;:!?])"), r"\1"),     # nem espaco antes de pontuacao
    (re.compile(r"([(«])\s+"), r"\1"),         # nem depois de abrir
    (re.compile(r"\s+([)»])"), r"\1"),         # nem antes de fechar
    (re.compile(r"(<p>)\s+"), r"\1"),
    (re.compile(r"\s+(</p>)"), r"\1"),
    (re.compile(r"([,;])\s*\1+"), r"\1"),      # virgula que ficou orfa e dobrou
    (re.compile(r"\.\s*\."), "."),
)


def texto_corrido(texto: str) -> str:
    """Fecha os claros que o preenchimento deixaria.

    POR QUE ISSO E REGRA E NAO ACABAMENTO
        Art. 795, § 2º, do Codigo de Normas: "A escrituracao deve ser seguida,
        sem claros ou espacos em branco." Espaco em branco em ato notarial e o
        lugar por onde se acrescenta o que ninguem declarou.

        Quando uma clausula condicional nao entra, ela deixa para tras o espaco
        que a cercava, e as vezes a virgula que a ligava a frase anterior. Sem
        esta limpeza o ato sairia com buraco — e o buraco passaria despercebido
        justamente por ser pequeno.

    RODA DEPOIS DO PREENCHIMENTO, NUNCA ANTES.
    """
    for padrao, troca in _SOBRAS:
        texto = padrao.sub(troca, texto)
    return texto.strip()


def claros_restantes(texto: str) -> list[str]:
    """O que ainda esta por preencher no ato.

    Devolve os marcadores que sobraram. Nenhum ato deve ser lavrado com um
    destes de pe: o marcador nao preenchido E o espaco em branco que o art. 795,
    § 2º, proibe — so que visivel.
    """
    achados = re.findall(r"\[([^\[\]]{2,120})\]", texto)
    achados += re.findall(r"\{([^{}]{2,300})\}", texto)
    achados += re.findall(r"«([^«»]{2,1500})»", texto, re.S)
    return [re.sub(r"\s+", " ", a).strip()[:120] for a in achados]


def __getattr__(nome: str):
    """`MODELOS` — o nome antigo da lista — continua respondendo, lido da base.

    Até o LF06D (19/10/2026) ela trazia o corpo de cada minuta escrito aqui;
    quem ainda a lê (a ferramenta do inventário, os testes) recebe as mesmas
    minutas, com o corpo da base. Nome que não existe continua sendo
    `AttributeError`.
    """
    if nome == "MODELOS":
        return minutas()
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
